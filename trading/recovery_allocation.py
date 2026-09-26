"""Conservative shared-fill allocation with atomic quantity/cost claims.

No FIFO/nearest-price reconstruction. Either original execution allocations
identify lots, or a complete all-owned batch closes at one identical price.
The latter uses disclosed proportional fee allocation, not historical lot IDs.
"""
import json
import hashlib
import sqlite3
from decimal import Decimal

from trading.recovery_statement import decimal, symbol_key, prove_isolated_cycle, schema
from trading.write_coordination import connection


def recover_shared_cycle(recorder,venue,target,rows,evidence,contract_size=1):
    selected=[r for r in rows if symbol_key(r['symbol'])==symbol_key(target['symbol'])]
    own=[r for r in selected if r['order_id']==str(target.get('order_id'))]
    if not own:return 'entry_order_not_in_history'
    lane=own[0].get('position_side','BOTH')
    selected=sorted([r for r in selected if r.get('position_side','BOTH')==lane],key=lambda r:(r['timestamp'],r['execution_id']))
    balance=Decimal(0); chunk=[]; chunks=[]; owned=[]
    for row in selected:
        chunk.append(row)
        balance+=decimal(row['quantity'])*(1 if row['side']=='buy' else -1)
        if balance==0:
            if any(r['order_id']==str(target['order_id']) for r in chunk):owned.append(len(chunks))
            chunks.append(chunk);chunk=[]
    if balance!=0 or not owned:return 'position_cycle_incomplete'
    cycle=[row for part in chunks[owned[0]:owned[-1]+1] for row in part]
    direction='buy' if str(target['side']).upper() in {'LONG','BUY'} else 'sell'
    incoming=[r for r in cycle if r['side']==direction]
    outgoing=[r for r in cycle if r['side']!=direction]
    if not outgoing:return 'exit_lot_allocation_required'
    ids={r['order_id'] for r in incoming}
    if len(ids)>100 or len(cycle)>20000:return 'history_page_incomplete'
    with sqlite3.connect(recorder.db_path) as db:
        db.row_factory=sqlite3.Row
        candidates=[dict(r) for r in db.execute('SELECT * FROM trade_log WHERE lower(exchange)=? AND order_id IN ('+','.join('?' for _ in ids)+')',(venue,*sorted(ids)))
                    if str(r['order_id']) in ids and symbol_key(r['symbol'])==symbol_key(target['symbol'])]
    if not candidates or {str(t['order_id']) for t in candidates}!=ids:return 'order_attribution_conflict'
    candidates.sort(key=lambda t:t['id'])
    if len(candidates)>100:return 'history_page_incomplete'
    from trading.pnl_evidence import performance_evidence
    if any(performance_evidence(t)['performance_evidence_ready'] for t in candidates):return 'order_attribution_conflict'
    if any(str(t.get('execution_mode')).lower() not in {'live','live_api','optimized','manual'} or
           str(t['side']).upper() not in ({'BUY','LONG'} if direction=='buy' else {'SELL','SHORT'}) for t in candidates):
        return 'order_attribution_conflict'
    by_id={str(t['id']):t for t in candidates}
    by_order={oid:[str(t['id']) for t in candidates if str(t['order_id'])==oid] for oid in ids}
    qty={str(t['id']):decimal(t['quantity']) for t in candidates}
    total=sum(qty.values(),Decimal(0))
    if any(n<=0 for n in qty.values()) or sum((decimal(r['quantity']) for r in outgoing),Decimal(0))!=total:
        return 'partial_or_quantity_mismatch'
    explicit_exit=[bool(r.get('entry_allocations') or r.get('ledger_allocations')) for r in outgoing]
    if any(explicit_exit) and not all(explicit_exit):return 'exit_lot_allocation_required'
    equivalent=(max(r['timestamp'] for r in incoming)<min(r['timestamp'] for r in outgoing)
                and len({decimal(r['price']) for r in outgoing})==1)
    allocated={key:[] for key in by_id}
    assigned={key:Decimal(0) for key in qty}
    cumulative=Decimal(0); proportional=False
    for row in cycle:
        is_entry=row['side']==direction
        explicit=row.get('ledger_allocations')
        if explicit:
            if not isinstance(explicit,dict) or set(explicit)-set(by_id):return 'order_attribution_conflict'
            portions={key:decimal(explicit.get(key,'0')) for key in by_id}
            if is_entry and any(n and str(by_id[key]['order_id'])!=row['order_id'] for key,n in portions.items()):
                return 'order_attribution_conflict'
            if row.get('entry_allocations'):
                grouped={oid:sum((portions[key] for key in keys),Decimal(0)) for oid,keys in by_order.items()}
                if {k:v for k,v in grouped.items() if v}!={k:decimal(v) for k,v in row['entry_allocations'].items()}:
                    return 'order_attribution_conflict'
        elif is_entry:
            owners=by_order[row['order_id']]
            if len(owners)!=1:return 'entry_order_allocation_required'
            portions={owners[0]:decimal(row['quantity'])}
        elif row.get('entry_allocations'):
            explicit=row['entry_allocations']
            if not isinstance(explicit,dict) or set(explicit)-ids:return 'order_attribution_conflict'
            if any(len(by_order[oid])!=1 for oid in explicit):return 'entry_order_allocation_required'
            portions={by_order[oid][0]:decimal(n) for oid,n in explicit.items()}
        elif len(candidates)==1:
            portions={next(iter(by_id)):decimal(row['quantity'])}
        else:
            if not equivalent:return 'exit_lot_allocation_required'
            proportional=True
            cumulative+=decimal(row['quantity'])
            portions={};remaining=decimal(row['quantity'])
            for i,key in enumerate(qty):
                desired=qty[key] if cumulative==total else cumulative*qty[key]/total
                part=remaining if i==len(qty)-1 else desired-assigned[key]
                portions[key]=part;remaining-=part;assigned[key]+=part
        if any(n<0 for n in portions.values()) or sum(portions.values(),Decimal(0))!=decimal(row['quantity']):
            return 'partial_or_quantity_mismatch'
        costs={key:decimal(row[key]) for key in ('fee','tax') if row.get(key) not in (None,'')}
        residual=dict(costs);positive=[key for key,n in portions.items() if n>0]
        for i,key in enumerate(positive):
            part={**row,'quantity':str(portions[key]),'realized_pnl':None}
            for name,value in costs.items():
                cost=residual[name] if i==len(positive)-1 else value*portions[key]/decimal(row['quantity'])
                part[name]=str(cost);residual[name]-=cost
            allocated[key].append(part)
    proofs=[]
    for trade in candidates:
        proof,reason=prove_isolated_cycle(trade,allocated[str(trade['id'])],
            opening_quantity=Decimal(0),contract_size=contract_size,attributed_reentries=True)
        if reason:return reason
        for key in ('gross','net','entry_fee','exit_fee','exit_price','notional'):decimal(proof[key])
        proofs.append((trade,proof))
    reported=[r.get('realized_pnl') for r in outgoing]
    if all(v not in (None,'') for v in reported) and abs(sum(map(decimal,reported),Decimal(0))-sum((p['gross'] for _,p in proofs),Decimal(0)))>Decimal('1e-8'):
        return 'cycle_gross_reconciliation_required'
    evidence={**evidence,'allocation_basis':'same_price_complete_batch_proportional_cost' if proportional else 'original_execution_lot_quantities',
              'original_executions':cycle}
    original=json.dumps(evidence,sort_keys=True)
    digest=hashlib.sha256(original.encode()).hexdigest()
    encoded=json.dumps({'evidence_digest':digest,'kind':evidence['kind'],'allocation_basis':evidence['allocation_basis']},sort_keys=True)
    with connection(recorder.db_path,operation='shared_fill_allocation',priority=20,timeout=5) as db:
        schema(db); db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS common_recovery_allocation_evidence(digest TEXT PRIMARY KEY,evidence TEXT)')
        db.execute('''CREATE TABLE IF NOT EXISTS common_recovery_allocations(
            venue TEXT,symbol TEXT,execution_id TEXT,trade_id INTEGER,quantity TEXT,fee TEXT,tax TEXT,evidence TEXT,
            PRIMARY KEY(venue,symbol,execution_id,trade_id))''')
        db.execute('BEGIN IMMEDIATE')
        for trade,proof in proofs:
            current=db.execute('SELECT * FROM trade_log WHERE id=?',(trade['id'],)).fetchone()
            if not current or dict(current)!=trade:return 'record_identity_changed'
            # Never overwrite an already confirmed or separately claimed repair.
            if db.execute('SELECT 1 FROM common_recovery_repairs WHERE venue=? AND trade_id=?',(venue,trade['id'])).fetchone():
                return 'order_attribution_conflict'
        for row in cycle:
            if db.execute('SELECT 1 FROM common_recovery_claims WHERE venue=? AND symbol=? AND execution_id=?',
                          (venue,symbol_key(row['symbol']),row['execution_id'])).fetchone():return 'order_attribution_conflict'
            if venue=='binance' and db.execute("SELECT 1 FROM sqlite_master WHERE name='recovery_cycle_claims'").fetchone():
                if db.execute('SELECT 1 FROM recovery_cycle_claims WHERE symbol=? AND fill_id=?',
                              (target['symbol'],row['execution_id'])).fetchone():return 'order_attribution_conflict'
        db.execute('INSERT OR IGNORE INTO common_recovery_allocation_evidence VALUES(?,?)',(digest,original))
        for row in cycle:
            db.execute('INSERT INTO common_recovery_claims VALUES(?,?,?,?,?)',
                       (venue,symbol_key(row['symbol']),row['execution_id'],-1,encoded))
        for trade,proof in proofs:
            for row in proof['entry']+proof['exit']:
                db.execute('INSERT INTO common_recovery_allocations VALUES(?,?,?,?,?,?,?,?)',
                    (venue,symbol_key(row['symbol']),row['execution_id'],trade['id'],row['quantity'],row['fee'],row.get('tax','0'),encoded))
            exit_ids={r['order_id'] for r in proof['exit']}
            costs=proof['entry_fee']+proof['exit_fee']
            values=(next(iter(exit_ids)) if len(exit_ids)==1 else None,proof['exit'][-1]['timestamp'],float(proof['exit_price']),
                    float(proof['gross']),float(proof['net']),float(proof['net']),float(proof['net']/proof['notional']*100),
                    float(proof['entry_fee']),float(proof['exit_fee']),float(costs),*(proof['currency'],)*4,
                    evidence['kind']+'_shared_fill_allocation',trade['id'])
            db.execute('''UPDATE trade_log SET exit_order_id=?,exit_time=?,exit_price=?,gross_pnl=?,net_pnl=?,pnl=?,pnl_percent=?,
                entry_fee=?,exit_fee=?,fees=?,entry_fee_asset=?,exit_fee_asset=?,fee_asset=?,settlement_currency=?,pnl_source=?,
                reconciliation_status='exact_fill_price_no_provider_pnl' WHERE id=?''',values)
            after=dict(db.execute('SELECT * FROM trade_log WHERE id=?',(trade['id'],)).fetchone())
            db.execute('INSERT INTO common_recovery_repairs VALUES(?,?,?,?,?)',
                       (venue,trade['id'],json.dumps(trade),json.dumps(after),encoded))
    return ''
