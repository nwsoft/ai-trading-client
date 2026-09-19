"""Durable entry -> submitted protection -> exchange actual order evidence.

Never infer ownership from a nearby fill, symbol, price, or quantity alone.
All network operations here are read-only and bounded; no order is submitted.
"""
import json
import math
import sqlite3
import time


class BinanceCloseEvidence:
    def __init__(self, recorder, client):
        self.recorder, self.client = recorder, client
        with self.connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS binance_close_evidence (
                entry_order_id TEXT NOT NULL, symbol TEXT NOT NULL,
                protection_id TEXT NOT NULL, kind TEXT NOT NULL,
                close_side TEXT NOT NULL, actual_order_id TEXT,
                checked_at REAL NOT NULL DEFAULT 0, response_json TEXT,
                PRIMARY KEY(symbol, protection_id, kind))''')

    def connect(self):
        return sqlite3.connect(self.recorder.db_path, timeout=10)

    def remember(self, entry_id, symbol, close_side, results):
        if not entry_id:
            return 0
        saved = 0
        with self.connect() as conn:
            for result in results:
                if not isinstance(result, dict):
                    continue
                raw = result.get('order') if isinstance(result.get('order'), dict) else result
                algo = raw.get('algoId')
                oid = algo or raw.get('orderId')
                if not oid or str(raw.get('symbol') or '').upper() != symbol.upper():
                    continue
                if str(raw.get('side') or '').upper() != close_side.upper():
                    continue
                # INSERT OR IGNORE preserves the original owner on retries.
                cur = conn.execute('''INSERT OR IGNORE INTO binance_close_evidence
                    (entry_order_id,symbol,protection_id,kind,close_side) VALUES (?,?,?,?,?)''',
                    (str(entry_id), symbol.upper(), str(oid), 'algo' if algo else 'order', close_side.upper()))
                saved += cur.rowcount
        return saved

    def sync(self, limit=2, now=None):
        now = time.time() if now is None else now
        result = {'checked': 0, 'linked': 0, 'failed': 0}
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('''SELECT p.* FROM binance_close_evidence p
                WHERE p.checked_at <= ? AND EXISTS (
                    SELECT 1 FROM trade_log t WHERE t.exchange='binance'
                    AND UPPER(t.symbol)=p.symbol AND t.order_id=p.entry_order_id
                    AND t.position_owner='noahai'
                    AND t.execution_mode IN ('live','live_api','optimized','manual')
                    AND (t.exit_order_id IS NULL OR t.exit_order_id=p.actual_order_id)
                    AND COALESCE(t.reconciliation_status,'') != 'exchange_confirmed')
                ORDER BY p.checked_at,p.rowid LIMIT ?''', (now-30, max(1,min(int(limit),10)))).fetchall()
        for row in rows:
            result['checked'] += 1
            with self.connect() as conn:
                conn.execute('UPDATE binance_close_evidence SET checked_at=? WHERE symbol=? AND protection_id=? AND kind=?',
                             (now,row['symbol'],row['protection_id'],row['kind']))
            try:
                if row['kind'] == 'algo':
                    response = self.client.get_algo_order_evidence(row['protection_id'])
                    if str(response.get('algoId')) != row['protection_id']:
                        raise ValueError('algo identity mismatch')
                    actual = str(response.get('actualOrderId') or '')
                else:
                    response = self.client.client.futures_get_order(symbol=row['symbol'], orderId=row['protection_id'])
                    actual = str(response.get('orderId') or '')
                    if actual != row['protection_id']:
                        raise ValueError('order identity mismatch')
                if not actual or actual == '0':
                    continue
                if str(response.get('symbol') or '').upper() != row['symbol'] or str(response.get('side') or '').upper() != row['close_side']:
                    raise ValueError('protection symbol/side mismatch')
                fills = self.client.get_recent_trades(symbol=row['symbol'], limit=1000, order_id=actual)
                fills = [f for f in fills if str(f.get('order_id') or f.get('order')) == actual]
                if not fills:
                    continue
                # Native API's missing fee must not be persisted as a zero fee.
                if any(f.get('commission') is None and not isinstance(f.get('fee'), dict) for f in fills):
                    continue
                if any(not math.isfinite(float(f.get('commission') if 'commission' in f else f['fee'].get('cost')))
                       for f in fills):
                    continue
                self.recorder.save_exchange_execution_history('binance', fills, source='owned_protection_order')
                with self.connect() as conn:
                    conn.row_factory = sqlite3.Row
                    trades = conn.execute('''SELECT id,side,quantity,exit_time FROM trade_log
                        WHERE exchange='binance' AND UPPER(symbol)=? AND order_id=?
                        AND position_owner='noahai' AND execution_mode IN ('live','live_api','optimized','manual')''',
                        (row['symbol'],row['entry_order_id'])).fetchall()
                    if len(trades) != 1:
                        continue
                    trade = trades[0]
                    expected_side = 'SELL' if trade['side'].upper() in ('LONG','BUY') else 'BUY'
                    if expected_side != row['close_side']:
                        continue
                    detail = conn.execute('''SELECT side,quantity,executed_at FROM exchange_execution_log
                        WHERE exchange='binance' AND symbol=? AND order_id=? AND confirmation_status='confirmed' ''',
                        (row['symbol'], actual)).fetchall()
                    qty = sum(float(f['quantity']) for f in detail)
                    if not detail or any(f['side'].upper() != expected_side for f in detail):
                        continue
                    if abs(qty-float(trade['quantity'])) > max(1e-8,float(trade['quantity'])*0.001):
                        continue  # partial fills retry later; never certify a full close
                    epochs = [self.recorder._ledger_time_epoch(f['executed_at']) for f in detail]
                    if any(t is None for t in epochs):
                        continue
                    from datetime import datetime, timezone
                    closed_at = datetime.fromtimestamp(max(epochs), timezone.utc).isoformat()
                    cur = conn.execute('''UPDATE trade_log SET exit_order_id=?,exit_time=?,
                        reconciliation_status='pending_exchange_reconciliation'
                        WHERE id=? AND (exit_order_id IS NULL OR exit_order_id=?)''',
                        (actual,closed_at,trade['id'],actual))
                    conn.execute('''UPDATE binance_close_evidence SET actual_order_id=?,response_json=?
                        WHERE symbol=? AND protection_id=? AND kind=?''',
                        (actual,json.dumps(response),row['symbol'],row['protection_id'],row['kind']))
                    result['linked'] += cur.rowcount
                self.recorder.reconcile_trade_log_with_executions('binance')
            except Exception:
                result['failed'] += 1
        return result
