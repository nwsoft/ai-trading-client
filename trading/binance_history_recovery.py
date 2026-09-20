"""Discover missing closes from complete provider history and a position anchor.

This is not a nearest-fill matcher. A known, unique entry must start from flat,
own the entire position cycle, and return to flat without another opening order.
The cycle is reconstructed backwards from a stable exchange position snapshot.
Raw pages, coverage and fill ownership survive restart in the account database.
No order endpoints or profitability/risk bypasses are used.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import sqlite3


class HistoryPending(Exception):
    """One bounded history page was checkpointed; retry this same item."""


def number(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or not math.isfinite(float(result)) or (result and float(result)==0):
            raise ValueError('nonfinite_history_value')
        return result
    except (InvalidOperation, TypeError):
        raise ValueError('invalid_history_value') from None


def reconstruct_cycle(trade, fills, orders, anchors, start, end):
    """Pure proof. Returns exact entry/exit fills or a non-success reason."""
    symbol, oid = str(trade['symbol']).upper(), str(trade.get('order_id') or '')
    quantity = number(trade['quantity'])
    side = str(trade['side']).upper()
    if quantity <= 0 or side not in {'BUY','LONG','SELL','SHORT'}:
        return None, 'local_trade_data_invalid'
    direction = 1 if side in {'BUY','LONG'} else -1
    entries = [r for r in fills if str(r.get('orderId')) == oid]
    if not entries:
        return None, 'entry_order_not_in_history'
    position_side = entries[0].get('positionSide')
    if any(r.get('positionSide') not in {'BOTH','LONG','SHORT'} or r.get('symbol') != symbol
           or not start <= int(r['time']) <= end for r in fills):
        return None, 'history_identity_mismatch'
    if position_side not in {'BOTH','LONG','SHORT'}:
        return None, 'position_anchor_unavailable'
    anchor = [r for r in anchors if r.get('symbol') == symbol and r.get('positionSide') == position_side]
    if len(anchor) != 1 or int(anchor[0].get('updateTime', end+1)) > end:
        return None, 'position_anchor_changed'
    current = number(anchor[0]['positionAmt'])
    selected = [r for r in fills if r.get('positionSide') == position_side]
    selected.sort(key=lambda r: (int(r['time']), int(r['id'])))
    seen = set()
    for row in selected:
        if row.get('symbol') != symbol or not start <= int(row['time']) <= end:
            return None, 'history_identity_mismatch'
        if str(row['id']) in seen or row.get('side') not in {'BUY','SELL'} or number(row['qty']) <= 0:
            return None, 'history_identity_mismatch'
        seen.add(str(row['id']))
    delta = lambda r: number(r['qty']) * (1 if r['side'] == 'BUY' else -1)
    # The complete queried suffix plus a stable present position determines
    # historical position quantities, including other later/manual trades.
    before = current - sum((delta(r) for r in selected), Decimal(0))
    cycle, entry_fills, exit_fills = [], [], []
    started = finished = False
    order_map = {str(r.get('orderId')): r for r in orders}
    for row in selected:
        amount = delta(row)
        if str(row['orderId']) == oid:
            if finished or (not started and before != 0) or amount * direction <= 0 or exit_fills:
                return None, 'position_cycle_ambiguous'
            started = True
            entry_fills.append(row)
        elif started and not finished:
            if amount * direction >= 0:
                return None, 'position_cycle_ambiguous'
            exit_fills.append(row)
        if started and not finished:
            cycle.append(row)
            if (before+amount)*direction < 0:
                return None, 'position_cycle_ambiguous'
            if before+amount == 0:
                finished = True
        before += amount
    if not started or not finished or sum((number(r['qty']) for r in entry_fills), Decimal(0)) != quantity:
        return None, 'position_cycle_incomplete'
    if len(entry_fills) != len(entries) or sum((number(r['qty']) for r in exit_fills), Decimal(0)) != quantity:
        return None, 'position_cycle_ambiguous'
    # Every cycle order must be FILLED and its entire executed quantity present.
    for order_id in {str(r['orderId']) for r in cycle}:
        order = order_map.get(order_id)
        group = [r for r in cycle if str(r['orderId']) == order_id]
        if not order or order.get('status') != 'FILLED' or order.get('symbol') != symbol:
            return None, 'order_history_incomplete'
        if order.get('positionSide') != position_side or any(r['side'] != order.get('side') for r in group):
            return None, 'history_identity_mismatch'
        if number(order['executedQty']) != sum((number(r['qty']) for r in group), Decimal(0)):
            return None, 'partial_or_quantity_mismatch'
    currency = str(trade.get('settlement_currency') or ('USDT' if symbol.endswith('USDT') else '')).upper()
    if not currency or not symbol.endswith(currency):
        return None, 'contract_unit_verification_required'
    for row in cycle:
        if number(row['price']) <= 0 or row.get('realizedPnl') is None or row.get('commission') is None:
            return None, 'provider_pnl_or_cost_evidence_incomplete'
        if number(row['commission']) != 0 and row.get('commissionAsset') != currency:
            return None, 'entry_fee_conversion_required'
        number(row['realizedPnl'])
    if any(number(r['realizedPnl']) != 0 for r in entry_fills):
        return None, 'position_cycle_ambiguous'
    return {'entry': entry_fills, 'exit': exit_fills, 'currency': currency}, ''


class BinanceHistoryRecovery:
    def __init__(self, recorder, client, queried):
        self.recorder, self.client, self.queried = recorder, client, queried
        key = str(getattr(getattr(client, 'config', None), 'api_key', '') or '')
        if not key:
            raise ValueError('recovery_credential_required')
        self.scope = hashlib.sha256(key.encode()).hexdigest()
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS recovery_history_sessions(
                  scope TEXT,symbol TEXT,start INTEGER,end INTEGER,anchor TEXT,verified INTEGER DEFAULT 0,
                  PRIMARY KEY(scope,symbol,start));
                CREATE TABLE IF NOT EXISTS recovery_history_runs(scope TEXT PRIMARY KEY, job_id TEXT);
                CREATE TABLE IF NOT EXISTS recovery_history_pages(
                  scope TEXT,symbol TEXT,kind TEXT,start INTEGER,end INTEGER,state TEXT,rows TEXT,
                  PRIMARY KEY(scope,symbol,kind,start,end));
                CREATE TABLE IF NOT EXISTS recovery_cycle_claims(
                  scope TEXT,symbol TEXT,fill_id TEXT,trade_id INTEGER,evidence TEXT,
                  PRIMARY KEY(scope,symbol,fill_id));
            ''')
            if 'verified' not in {r[1] for r in db.execute('PRAGMA table_info(recovery_history_sessions)')}:
                db.execute('ALTER TABLE recovery_history_sessions ADD COLUMN verified INTEGER DEFAULT 0')

    def begin_job(self, job_id):
        if not job_id:
            return
        with self.db() as db:
            previous = db.execute('SELECT job_id FROM recovery_history_runs WHERE scope=?',(self.scope,)).fetchone()
            if previous and previous[0] == job_id:
                return
            # Explicit new checks refresh provider data, including previously
            # missing/delayed fills. Restarts of the SAME job keep checkpoints.
            db.execute('DELETE FROM recovery_history_sessions WHERE scope=?',(self.scope,))
            db.execute("UPDATE recovery_history_pages SET state='pending' WHERE scope=?",(self.scope,))
            db.execute('INSERT OR REPLACE INTO recovery_history_runs VALUES(?,?)',(self.scope,job_id))

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.recorder.db_path, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def query(self, method, *args):
        self.queried()
        return method(*args)

    def recover(self, trade):
        key = str(getattr(getattr(self.client, 'config', None), 'api_key', '') or '')
        if hashlib.sha256(key.encode()).hexdigest() != self.scope:
            return 'credential_scope_changed'
        epoch = self.recorder._ledger_time_epoch(trade['entry_time'])
        if epoch is None:
            return 'execution_time_missing'
        symbol = str(trade['symbol']).upper()
        # UTC-day buckets make subsequent trades reuse already downloaded pages.
        start = int(epoch // 86400 * 86400000)-86400000
        with self.db() as db:
            session = db.execute('SELECT * FROM recovery_history_sessions WHERE scope=? AND symbol=? AND start=?',
                                 (self.scope,symbol,start)).fetchone()
        if not session:
            anchor = self.query(self.client.get_recovery_position_anchor, symbol)
            end = int(self.client.get_synced_timestamp())
            if start < end - 89*86400000:
                return 'history_retention_exceeded'
            with self.db() as db:
                db.execute('INSERT INTO recovery_history_sessions(scope,symbol,start,end,anchor) VALUES(?,?,?,?,?)',
                           (self.scope,symbol,start,end,json.dumps(anchor)))
                for kind in ('fills','orders','algos','income'):
                    left = start
                    while left <= end:
                        right = min(left+6*86400000-1, end)
                        db.execute('INSERT OR IGNORE INTO recovery_history_pages VALUES(?,?,?,?,?,?,NULL)',
                                   (self.scope,symbol,kind,left,right,'pending'))
                        left = right+1
            raise HistoryPending()
        end = session['end']
        with self.db() as db:
            page = db.execute("SELECT * FROM recovery_history_pages WHERE scope=? AND symbol=? AND start>=? AND end<=? AND state='pending' ORDER BY kind,start LIMIT 1",
                              (self.scope,symbol,start,end)).fetchone()
        if page:
            rows = self.query(self.client.get_recovery_history_page, page['kind'], symbol, page['start'], page['end'])
            if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                raise RuntimeError('provider_history_query_failed')
            with self.db() as db:
                key = (self.scope,symbol,page['kind'],page['start'],page['end'])
                if len(rows) >= 1000:
                    if page['start'] == page['end']:
                        db.execute("UPDATE recovery_history_pages SET state='overflow' WHERE scope=? AND symbol=? AND kind=? AND start=? AND end=?",key)
                        return 'history_page_incomplete'
                    middle = (page['start']+page['end'])//2
                    for left,right in ((page['start'],middle),(middle+1,page['end'])):
                        db.execute('INSERT OR IGNORE INTO recovery_history_pages VALUES(?,?,?,?,?,?,NULL)',
                                   (self.scope,symbol,page['kind'],left,right,'pending'))
                    db.execute("UPDATE recovery_history_pages SET state='split' WHERE scope=? AND symbol=? AND kind=? AND start=? AND end=?",key)
                else:
                    db.execute("UPDATE recovery_history_pages SET state='complete',rows=? WHERE scope=? AND symbol=? AND kind=? AND start=? AND end=?", (json.dumps(rows),*key))
            raise HistoryPending()
        data = {}
        with self.db() as db:
            for kind in ('fills','orders','algos','income'):
                pages = db.execute("SELECT * FROM recovery_history_pages WHERE scope=? AND symbol=? AND kind=? AND start>=? AND end<=? AND state='complete' ORDER BY start,end DESC",
                                   (self.scope,symbol,kind,start,end)).fetchall()
                # Check coverage explicitly: no missing/corrupt cursor = success.
                through = start-1
                result = {}
                for page in pages:
                    if page['start'] > through+1:
                        return 'history_page_incomplete'
                    through = max(through,page['end'])
                    for row in json.loads(page['rows']):
                        identity = str(row.get({'fills':'id','orders':'orderId','algos':'algoId','income':'tranId'}[kind]))
                        if identity in ('None',''):
                            return 'history_identity_mismatch'
                        if kind == 'income':
                            identity += ':'+str(row.get('incomeType'))
                        if identity in result and result[identity] != row:
                            return 'history_identity_mismatch'
                        result[identity] = row
                if through < end:
                    return 'history_page_incomplete'
                data[kind] = list(result.values())
        current = (json.loads(session['anchor']) if session['verified']
                   else self.query(self.client.get_recovery_position_anchor, symbol))
        def fingerprint(rows):
            return sorted((r.get('symbol'),r.get('positionSide'),str(r.get('positionAmt')),int(r.get('updateTime',end+1))) for r in rows)
        if fingerprint(current) != fingerprint(json.loads(session['anchor'])):
            # The provider changed while collecting. Discard only this snapshot
            # plan, not trade records; the next explicit attempt takes a new one.
            with self.db() as db:
                db.execute('DELETE FROM recovery_history_sessions WHERE scope=? AND symbol=? AND start=?', (self.scope,symbol,start))
            return 'position_anchor_changed'
        if not session['verified']:
            with self.db() as db:
                db.execute('UPDATE recovery_history_sessions SET verified=1 WHERE scope=? AND symbol=? AND start=?',
                           (self.scope,symbol,start))
        proof, reason = reconstruct_cycle(trade,data['fills'],data['orders'],current,start,end)
        if reason:
            return reason
        return self.apply(trade, proof, data['income'], start, end)

    def apply(self, trade, proof, income, start, end):
        entry, exits = proof['entry'], proof['exit']
        cycle = entry + exits
        # Income history provides an independent gross-PnL cross-check by tradeId.
        for fill in exits:
            expected = number(fill['realizedPnl'])
            linked = [r for r in income if str(r.get('tradeId')) == str(fill['id'])
                      and r.get('incomeType') == 'REALIZED_PNL' and r.get('symbol') == trade['symbol']]
            if expected != 0 and not linked:
                return 'income_reconciliation_required'
            if any(r.get('asset') != proof['currency'] for r in linked) or sum((number(r['income']) for r in linked),Decimal(0)) != expected:
                return 'income_reconciliation_required'
        gross = sum((number(r['realizedPnl']) for r in exits),Decimal(0))
        entry_fee = sum((number(r['commission']) for r in entry),Decimal(0))
        exit_fee = sum((number(r['commission']) for r in exits),Decimal(0))
        net = gross-entry_fee-exit_fee
        qty = number(trade['quantity'])
        exit_price = sum((number(r['price'])*number(r['qty']) for r in exits),Decimal(0))/qty
        entry_price = sum((number(r['price'])*number(r['qty']) for r in entry),Decimal(0))/qty
        closed = datetime.fromtimestamp(max(int(r['time']) for r in exits)/1000,timezone.utc).isoformat()
        exit_ids = sorted({str(r['orderId']) for r in exits})
        evidence = json.dumps({'start':start,'end':end,'entry_order':str(trade['order_id']),
                               'exit_orders':exit_ids,'entry':entry,'exit':exits,'basis':'isolated_position_cycle'})
        # Populate the existing execution ledger too, so statistics/notifications
        # do not see a certified close with no corresponding provider fills.
        normalized = [{**r,'order':str(r['orderId']),'quantity':r['qty'],
                       'realized_pnl':r['realizedPnl'],'commission_asset':r['commissionAsset']}
                      for r in cycle]
        self.recorder.save_exchange_execution_history('binance',normalized,
            source='maintenance_position_cycle',reconcile=False)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for fill in cycle:
                stored = db.execute('''SELECT quantity,fee,realized_pnl,realized_pnl_present
                    FROM exchange_execution_log WHERE exchange='binance' AND symbol=? AND order_id=?
                    AND trade_id=? AND confirmation_status='confirmed' ''',
                    (trade['symbol'],str(fill['orderId']),str(fill['id']))).fetchall()
                if len(stored)!=1 or stored[0]['realized_pnl_present']!=1 or any(
                    abs(number(stored[0][field])-number(fill[native]))>Decimal('1e-12')
                    for field,native in (('quantity','qty'),('fee','commission'),('realized_pnl','realizedPnl'))):
                    return 'execution_storage_incomplete'
            latest = db.execute('SELECT * FROM trade_log WHERE id=?',(trade['id'],)).fetchone()
            if not latest or any(latest[k] != trade[k] for k in ('exchange','symbol','order_id','entry_time','quantity','side','position_owner','execution_mode','exit_order_id','exit_time')):
                return 'record_identity_changed'
            if db.execute('SELECT COUNT(*) FROM trade_log WHERE exchange=? AND symbol=? AND order_id=?',
                          ('binance',trade['symbol'],trade['order_id'])).fetchone()[0] != 1:
                return 'entry_order_allocation_required'
            for fill in cycle:
                owner = db.execute('SELECT trade_id FROM recovery_cycle_claims WHERE scope=? AND symbol=? AND fill_id=?',
                                   (self.scope,trade['symbol'],str(fill['id']))).fetchone()
                if owner and owner[0] != trade['id']:
                    return 'order_attribution_conflict'
            for oid in exit_ids:
                if db.execute('''SELECT 1 FROM trade_log WHERE id!=? AND exchange='binance' AND symbol=?
                    AND exit_order_id=? AND execution_mode IN ('live','live_api','optimized','manual') LIMIT 1''',
                    (trade['id'],trade['symbol'],oid)).fetchone():
                    return 'order_attribution_conflict'
            for fill in cycle:
                db.execute('INSERT OR IGNORE INTO recovery_cycle_claims VALUES(?,?,?,?,?)',
                           (self.scope,trade['symbol'],str(fill['id']),trade['id'],evidence))
            # Multi-order closes keep the singular column NULL: no fake exchange
            # order ID. The claim table stores every actual order/fill instead.
            db.execute('''UPDATE trade_log SET exit_order_id=?,exit_price=?,exit_time=?,
                gross_pnl=?,net_pnl=?,pnl=?,pnl_percent=?,entry_fee=?,exit_fee=?,fees=?,
                entry_fee_asset=?,exit_fee_asset=?,fee_asset=?,settlement_currency=?,
                pnl_source='exchange_realized_pnl',reconciliation_status='exchange_confirmed'
                WHERE id=?''', (exit_ids[0] if len(exit_ids)==1 else None,float(exit_price),closed,
                float(gross),float(net),float(net),float(net/(entry_price*qty)*100),float(entry_fee),float(exit_fee),
                float(entry_fee+exit_fee),proof['currency'],proof['currency'],proof['currency'],proof['currency'],trade['id']))
        return ''
