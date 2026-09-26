"""Account-local statement staging and exact, isolated-cycle recovery.

CSV is user-supplied evidence, not authenticated exchange API evidence. The
original bytes, mapping and explicit coverage attestation are retained. No
spreadsheet formula is evaluated and importing never starts trading.
"""
import base64
import csv
import hashlib
import io
import json
import math
import re
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from trading.exchanges.venue_capabilities import SUPPORTED_VENUES, STOCK_VENUES
from trading.write_coordination import connection

FIELDS = ('execution_id','order_id','symbol','side','quantity','price','fee','fee_currency','timestamp',
          'realized_pnl','tax','position_side','entry_order_id','entry_allocations','ledger_allocations')
REQUIRED = FIELDS[:9]
MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 20000


def decimal(value):
    if isinstance(value, bool) or value in (None, ''):
        raise ValueError('statement_number_missing')
    try:
        n = Decimal(str(value).strip())
        if not n.is_finite() or not math.isfinite(float(n)):
            raise ValueError('statement_number_invalid')
        return n
    except InvalidOperation:
        raise ValueError('statement_number_invalid') from None


def symbol_key(value):
    return str(value).upper().split(':')[0].replace('/','').replace('-','').removesuffix('SWAP')


def read_statement(payload):
    """Bounded preview, strict mapping; no DB writes or implicit date guessing."""
    source = payload.get('source')
    if source not in SUPPORTED_VENUES:
        raise ValueError('unsupported_recovery_source')
    if source in {'binance','okx','bybit','bitget'} and 'contract_size' not in payload:
        raise ValueError('statement_contract_unit_invalid')
    multiplier=decimal(payload.get('contract_size','1'))
    if multiplier<=0 or (source in STOCK_VENUES|{'upbit','bithumb','coinone'} and multiplier!=1):
        raise ValueError('statement_contract_unit_invalid')
    if source in {'binance','okx','bybit','bitget'} and payload.get('linear_contract') is not True:
        raise ValueError('statement_linear_contract_required')
    encoded = payload.get('content_base64')
    if not isinstance(encoded,str) or len(encoded)>MAX_BYTES*4//3+8:
        raise ValueError('statement_size_limit')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise ValueError('statement_encoding_invalid') from None
    if not raw or len(raw)>MAX_BYTES:
        raise ValueError('statement_size_limit')
    encoding = payload.get('encoding','utf-8-sig')
    if encoding not in {'utf-8-sig','cp949'}:
        raise ValueError('statement_encoding_invalid')
    try: text = raw.decode(encoding)
    except UnicodeError: raise ValueError('statement_encoding_invalid') from None
    delimiter = payload.get('delimiter',',')
    if delimiter not in {',','\t',';'}: raise ValueError('statement_delimiter_invalid')
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = reader.fieldnames or []
    if not headers or len(headers)>64 or len(set(headers))!=len(headers) or any(not h or len(h)>200 for h in headers):
        raise ValueError('statement_headers_invalid')
    mapping = payload.get('mapping') or {}
    if not isinstance(mapping,dict) or any(k not in FIELDS or v not in headers for k,v in mapping.items()):
        raise ValueError('statement_mapping_invalid')
    if len(set(mapping.values())) != len(mapping): raise ValueError('statement_mapping_invalid')
    required = (*REQUIRED, 'tax') if source in STOCK_VENUES else REQUIRED
    missing = [k for k in required if k not in mapping]
    zone = payload.get('timezone','UTC')
    if zone not in {'UTC','Asia/Seoul'}: raise ValueError('statement_timezone_invalid')
    number_format=payload.get('number_format','plain')
    time_format=payload.get('time_format','iso')
    if number_format not in {'plain','grouped'} or time_format not in {'iso','epoch_ms','epoch_seconds'}:
        raise ValueError('statement_format_invalid')
    rows, errors, seen = [], [], {}
    for index, raw_row in enumerate(reader,2):
        if index>MAX_ROWS+1: raise ValueError('statement_row_limit')
        if None in raw_row or any(v is None for v in raw_row.values()):
            errors.append({'line':index,'reason':'statement_column_count_mismatch'}); continue
        if missing: continue
        row = {k:raw_row[v].strip() for k,v in mapping.items()}
        try:
            if any(not row.get(k) for k in required): raise ValueError('statement_required_value_missing')
            if any(len(row.get(k,''))>200 for k in ('execution_id','order_id','symbol','entry_order_id')):
                raise ValueError('statement_identity_invalid')
            row['side']={'매수':'buy','매도':'sell','BUY':'buy','SELL':'sell'}.get(row['side'],row['side'].lower())
            if row['side'] not in {'buy','sell'}: raise ValueError('statement_side_invalid')
            row['symbol']=row['symbol'].upper(); row['fee_currency']=row['fee_currency'].upper()
            for k in ('quantity','price','fee','tax','realized_pnl'):
                if row.get(k) not in (None,''):
                    value=row[k]
                    if ',' in value and number_format=='grouped':
                        if not re.fullmatch(r'[+-]?\d{1,3}(,\d{3})+(\.\d+)?',value):
                            raise ValueError('statement_number_invalid')
                        value=value.replace(',','')
                    row[k]=str(decimal(value))
            if decimal(row['quantity'])<=0 or decimal(row['price'])<=0: raise ValueError('statement_number_invalid')
            if row.get('tax') and decimal(row['tax'])<0: raise ValueError('statement_tax_invalid')
            stamp=(datetime.fromisoformat(row['timestamp'].replace('Z','+00:00')) if time_format=='iso'
                   else datetime.fromtimestamp(float(decimal(row['timestamp']))/(1000 if time_format=='epoch_ms' else 1),timezone.utc))
            if stamp.tzinfo is None: stamp=stamp.replace(tzinfo=ZoneInfo(zone))
            row['timestamp']=stamp.astimezone(timezone.utc).isoformat()
            if stamp.timestamp()<=0 or stamp.timestamp()>time.time()+5: raise ValueError('statement_time_invalid')
            row['position_side']=row.get('position_side') or 'BOTH'
            if row['position_side'].upper() not in {'BOTH','LONG','SHORT'}: raise ValueError('statement_position_side_invalid')
            row['position_side']=row['position_side'].upper()
            if not row.get('entry_order_id'): row.pop('entry_order_id',None)
            for allocation_key in ('entry_allocations','ledger_allocations'):
                if row.get(allocation_key):
                    allocation=json.loads(row[allocation_key])
                    if not isinstance(allocation,dict) or not 1<=len(allocation)<=100 or any(not k or len(k)>200 for k in allocation):
                        raise ValueError('statement_allocation_invalid')
                    if any(decimal(v)<=0 for v in allocation.values()) or sum((decimal(v) for v in allocation.values()),Decimal(0))!=decimal(row['quantity']):
                        raise ValueError('statement_allocation_invalid')
                    row[allocation_key]={k:str(decimal(v)) for k,v in allocation.items()}
                else: row.pop(allocation_key,None)
            identity=(symbol_key(row['symbol']),row['execution_id'])
            if identity in seen:
                if seen[identity]!=row: raise ValueError('statement_duplicate_conflict')
                continue
            seen[identity]=row; rows.append(row)
        except (ValueError,OverflowError,OSError) as exc:
            reason=str(exc) if str(exc).startswith('statement_') else 'statement_time_invalid'
            errors.append({'line':index,'reason':reason})
    metadata={k:payload.get(k) for k in ('source','mapping','timezone','encoding','delimiter','complete_cycles','contract_size','linear_contract','time_format','number_format')}
    digest=hashlib.sha256(raw+json.dumps(metadata,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'digest':digest,'headers':headers,'missing_fields':missing,'errors':errors[:100],
            'error_count':len(errors),'rows':rows,'valid_count':len(rows),
            'ready':bool(rows) and not errors and not missing and payload.get('complete_cycles') is True,
            'raw':raw,'metadata':metadata}


def schema(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS recovery_statements(
        digest TEXT PRIMARY KEY, venue TEXT NOT NULL, original BLOB NOT NULL,
        metadata TEXT NOT NULL, rows_json TEXT NOT NULL, imported_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS common_recovery_claims(
        venue TEXT,symbol TEXT,execution_id TEXT,trade_id INTEGER,evidence TEXT,
        PRIMARY KEY(venue,symbol,execution_id));
      CREATE TABLE IF NOT EXISTS common_recovery_repairs(
        venue TEXT,trade_id INTEGER,before_json TEXT,after_json TEXT,evidence TEXT,
        PRIMARY KEY(venue,trade_id));
    ''')


def import_statement(recorder,payload,*,commit=False):
    preview=read_statement(payload)
    result={k:v for k,v in preview.items() if k not in {'raw','rows','metadata'}}
    result['sample']=preview['rows'][:5]
    result['provenance']='user_supplied_statement_not_api_authenticated'
    result['auto_started']=False
    if not commit: return result
    if payload.get('reviewed_digest')!=preview['digest'] or payload.get('confirmed_own_account') is not True or not preview['ready']:
        raise ValueError('statement_review_required')
    with connection(recorder.db_path,operation='statement_import',priority=20,timeout=5) as db:
        schema(db)
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute('SELECT 1 FROM recovery_statements WHERE digest=?',(preview['digest'],)).fetchone()
        documents=db.execute('SELECT venue,rows_json,metadata FROM recovery_statements').fetchall()
        used=db.execute('SELECT COALESCE(SUM(length(original)+length(rows_json)),0) FROM recovery_statements').fetchone()[0]
        encoded_rows=json.dumps(preview['rows'])
        if not existing and used+len(preview['raw'])+len(encoded_rows.encode())>100*1024*1024:
            raise ValueError('statement_storage_limit')
        identities={(symbol_key(r['symbol']),r['execution_id']):r for r in preview['rows']}
        for venue,old,old_metadata in documents:
            if venue!=payload['source']: continue
            for row in json.loads(old):
                new=identities.get((symbol_key(row['symbol']),row['execution_id']))
                if new is not None and (new!=row or decimal(json.loads(old_metadata).get('contract_size') or '1')!=decimal(preview['metadata'].get('contract_size') or '1')):
                    raise ValueError('statement_existing_evidence_conflict')
        # Keep originals and scope in this account's DB, never a global cache.
        db.execute('INSERT OR IGNORE INTO recovery_statements VALUES(?,?,?,?,?,?)',(
            preview['digest'],payload['source'],preview['raw'],json.dumps(preview['metadata']),
            encoded_rows,datetime.now(timezone.utc).isoformat()))
    result['stored']=True; result['already_imported']=bool(existing)
    return result


def prove_isolated_cycle(trade,rows,*,closing_quantity=Decimal(0), opening_quantity=None,contract_size=Decimal(1), attributed_reentries=False):
    """Complete symbol/position-lane coverage is a caller prerequisite."""
    oid=str(trade.get('order_id') or '')
    selected=[r for r in rows if symbol_key(r['symbol'])==symbol_key(trade['symbol'])]
    own=[r for r in selected if r['order_id']==oid]
    if not own: return None,'entry_order_not_in_history'
    lane=own[0].get('position_side','BOTH')
    if any(r.get('position_side','BOTH')!=lane for r in own): return None,'history_identity_mismatch'
    selected=[r for r in selected if r.get('position_side','BOTH')==lane]
    selected.sort(key=lambda r:(r['timestamp'],r['execution_id']))
    # Distinct order events at the same timestamp have no proven ordering.
    stamps={}
    for row in selected:
        stamps.setdefault(row['timestamp'],set()).add(row['order_id'])
    if any(len(ids)>1 for ids in stamps.values()): return None,'execution_order_ambiguous'
    delta=lambda r:decimal(r['quantity'])*(1 if r['side']=='buy' else -1)
    before=decimal(closing_quantity)-sum((delta(r) for r in selected),Decimal(0))
    if opening_quantity is not None and before!=decimal(opening_quantity): return None,'position_cycle_incomplete'
    direction=1 if str(trade['side']).upper() in {'BUY','LONG'} else -1
    if trade['exchange'] in STOCK_VENUES|{'upbit','bithumb','coinone'} and direction<0:
        return None,'local_trade_data_invalid'
    incoming=[]; outgoing=[]; started=finished=False
    for r in selected:
        change=delta(r)
        if r['order_id']==oid:
            if ((finished or outgoing) and not attributed_reentries) or (not started and before!=0) or change*direction<=0:
                return None,'position_cycle_ambiguous'
            if attributed_reentries: finished=False
            started=True; incoming.append(r)
        elif started and not finished:
            if change*direction>=0: return None,'position_cycle_ambiguous'
            outgoing.append(r)
        if started and not finished:
            if (before+change)*direction<0: return None,'position_cycle_ambiguous'
            if before+change==0: finished=True
        before+=change
    qty=decimal(trade['quantity'])
    if not started or not finished or not outgoing: return None,'position_cycle_incomplete'
    if sum((decimal(r['quantity']) for r in incoming),Decimal(0))!=qty or sum((decimal(r['quantity']) for r in outgoing),Decimal(0))!=qty:
        return None,'partial_or_quantity_mismatch'
    entry=sum((decimal(r['quantity'])*decimal(r['price']) for r in incoming),Decimal(0))/qty
    if abs(entry-decimal(trade['entry_price']))>max(Decimal('1e-8'),abs(entry)*Decimal('1e-8')):
        return None,'entry_price_evidence_mismatch'
    entry_epoch=datetime.fromisoformat(incoming[0]['timestamp']).timestamp()
    from trading.recorder import Recorder
    local_epoch=Recorder._ledger_time_epoch(trade['entry_time'])
    if local_epoch is None or abs(entry_epoch-local_epoch)>300: return None,'entry_time_evidence_mismatch'
    currency=str(trade.get('settlement_currency') or Recorder._settlement_currency(trade['symbol'],trade['exchange'])).upper()
    if not currency or any(r['fee_currency']!=currency for r in incoming+outgoing): return None,'entry_fee_conversion_required'
    is_stock=trade['exchange'] in STOCK_VENUES
    if is_stock and any(r.get('tax') in (None,'') for r in incoming+outgoing): return None,'fee_or_fill_data_incomplete'
    exit_price=sum((decimal(r['quantity'])*decimal(r['price']) for r in outgoing),Decimal(0))/qty
    contract_size=decimal(contract_size)
    if contract_size<=0: return None,'contract_unit_verification_required'
    gross=(exit_price-entry)*qty*direction*contract_size
    reported=[r.get('realized_pnl') for r in outgoing]
    if all(v not in (None,'') for v in reported) and abs(sum(map(decimal,reported),Decimal(0))-gross)>Decimal('1e-8'):
        return None,'cycle_gross_reconciliation_required'
    costs=[sum((decimal(r['fee'])+decimal(r.get('tax') or '0') for r in group),Decimal(0)) for group in (incoming,outgoing)]
    return {'entry':incoming,'exit':outgoing,'gross':gross,'net':gross-sum(costs),
            'entry_fee':costs[0],'exit_fee':costs[1],'currency':currency,'exit_price':exit_price,
            'notional':entry*qty*contract_size},''


def apply_cycle(recorder,venue,trade,proof,evidence):
    """Journal, ownership claims and financial repair share one transaction."""
    incoming,outgoing=proof['entry'],proof['exit']
    all_rows=incoming+outgoing
    # Reject overflow before entering any financial write transaction.
    for key in ('gross','net','entry_fee','exit_fee','exit_price','notional'):
        decimal(proof[key])
    if proof['notional']<=0: return 'contract_unit_verification_required'
    pnl_percent=decimal(proof['net']/proof['notional']*100)
    decimal(proof['entry_fee']+proof['exit_fee'])
    with connection(recorder.db_path,operation='common_cycle_recovery',priority=20,timeout=5) as db:
        schema(db); db.row_factory=sqlite3.Row; db.execute('BEGIN IMMEDIATE')
        latest=db.execute('SELECT * FROM trade_log WHERE id=?',(trade['id'],)).fetchone()
        if not latest or dict(latest)!=trade: return 'record_identity_changed'
        owners=db.execute('SELECT count(*) FROM trade_log WHERE LOWER(exchange)=? AND order_id=?',
                          (venue,str(trade['order_id']))).fetchone()[0]
        if owners!=1: return 'entry_order_allocation_required'
        for r in outgoing:
            if db.execute('SELECT 1 FROM trade_log WHERE LOWER(exchange)=? AND id!=? AND (exit_order_id=? OR order_id=?) LIMIT 1',
                          (venue,trade['id'],r['order_id'],r['order_id'])).fetchone(): return 'order_attribution_conflict'
        for r in all_rows:
            owner=db.execute('SELECT trade_id FROM common_recovery_claims WHERE venue=? AND symbol=? AND execution_id=?',
                             (venue,symbol_key(r['symbol']),r['execution_id'])).fetchone()
            if owner and owner[0]!=trade['id']: return 'order_attribution_conflict'
            if venue=='binance' and db.execute("SELECT 1 FROM sqlite_master WHERE name='recovery_cycle_claims'").fetchone():
                if db.execute('SELECT 1 FROM recovery_cycle_claims WHERE symbol=? AND fill_id=? AND trade_id!=? LIMIT 1',
                              (trade['symbol'],r['execution_id'],trade['id'])).fetchone(): return 'order_attribution_conflict'
        encoded=json.dumps(evidence,sort_keys=True)
        for r in all_rows:
            db.execute('INSERT OR IGNORE INTO common_recovery_claims VALUES(?,?,?,?,?)',
                       (venue,symbol_key(r['symbol']),r['execution_id'],trade['id'],encoded))
        ids=sorted({r['order_id'] for r in outgoing})
        net=proof['net']; costs=proof['entry_fee']+proof['exit_fee']
        db.execute('''UPDATE trade_log SET exit_order_id=?,exit_time=?,exit_price=?,gross_pnl=?,net_pnl=?,pnl=?,
            pnl_percent=?,entry_fee=?,exit_fee=?,fees=?,entry_fee_asset=?,exit_fee_asset=?,fee_asset=?,
            settlement_currency=?,pnl_source=?,reconciliation_status='exact_fill_price_no_provider_pnl' WHERE id=?''',
            (ids[0] if len(ids)==1 else None,outgoing[-1]['timestamp'],float(proof['exit_price']),float(proof['gross']),
             float(net),float(net),float(pnl_percent),
             float(proof['entry_fee']),float(proof['exit_fee']),float(costs),*(proof['currency'],)*4,
             'statement_isolated_cycle' if evidence['kind']=='statement' else 'api_isolated_cycle',trade['id']))
        after=dict(db.execute('SELECT * FROM trade_log WHERE id=?',(trade['id'],)).fetchone())
        db.execute('INSERT OR REPLACE INTO common_recovery_repairs VALUES(?,?,?,?,?)',
                   (venue,trade['id'],json.dumps(trade),json.dumps(after),encoded))
    return ''


def recover_from_statements(recorder,venue,trade):
    with sqlite3.connect(recorder.db_path) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='recovery_statements'").fetchone():
            return None
        documents=db.execute('SELECT digest,rows_json,metadata FROM recovery_statements WHERE venue=? ORDER BY imported_at DESC',(venue,)).fetchall()
    reason=None
    for digest,raw,metadata in documents:
        rows=json.loads(raw)
        if not any(r['order_id']==str(trade.get('order_id')) and symbol_key(r['symbol'])==symbol_key(trade['symbol']) for r in rows): continue
        attributed = [r for r in rows if str(r.get('entry_order_id') or '') == str(trade.get('order_id'))
                      and symbol_key(r['symbol'])==symbol_key(trade['symbol'])]
        basis = 'user_attested_complete_flat_to_flat_cycles'
        candidate_rows = rows
        if attributed:
            # An explicit original-file entry reference is evidence; chronology,
            # FIFO and a nearest price are not. Never invent a lot split.
            incoming = [r for r in rows if r['order_id']==str(trade['order_id'])
                        and symbol_key(r['symbol'])==symbol_key(trade['symbol'])]
            outgoing = [r for r in attributed if r['order_id']!=str(trade['order_id'])]
            if any(r.get('entry_order_id') not in (None,'',str(trade['order_id'])) for r in incoming):
                reason = 'order_attribution_conflict'
                continue
            lane_rows = [r for r in rows if symbol_key(r['symbol'])==symbol_key(trade['symbol'])
                         and r.get('position_side','BOTH')==incoming[0].get('position_side','BOTH')]
            if sum((decimal(r['quantity'])*(1 if r['side']=='buy' else -1) for r in lane_rows),Decimal(0)) != 0:
                reason = 'position_cycle_incomplete'
                continue
            candidate_rows = incoming+outgoing
            basis = 'user_reviewed_explicit_entry_order_references'
            # A shared exit order with unassigned fills needs a separate quantity
            # allocation ledger; do not certify it through the singular order ID.
            exit_ids = {r['order_id'] for r in outgoing}
            if any(r['order_id'] in exit_ids and r not in outgoing for r in rows):
                reason = 'entry_order_allocation_required'
                continue
        proof,reason=prove_isolated_cycle(trade,candidate_rows,opening_quantity=Decimal(0),
                                          contract_size=json.loads(metadata).get('contract_size') or '1')
        if proof:
            return apply_cycle(recorder,venue,trade,proof,{'kind':'statement','digest':digest,
                'basis':basis,'funding_included':False})
        if reason in {'position_cycle_ambiguous','partial_or_quantity_mismatch','execution_order_ambiguous'}:
            from trading.recovery_allocation import recover_shared_cycle
            reason=recover_shared_cycle(recorder,venue,trade,rows,{'kind':'statement','digest':digest},
                                        contract_size=json.loads(metadata).get('contract_size') or '1')
            if not reason:return ''
    return reason
