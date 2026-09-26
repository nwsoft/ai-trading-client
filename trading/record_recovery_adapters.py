"""Read-only recovery adapters. Unsupported != no trades != verified zero PnL."""
import sqlite3
import math
import time
from contextlib import closing
from trading.binance_close_evidence import BinanceCloseEvidence
from trading.record_recovery import validate_fills
from trading.exchanges.execution_history import normalize_execution
from trading.exchanges.venue_capabilities import STOCK_VENUES
from trading.binance_history_recovery import BinanceHistoryRecovery


class RecoveryResolver:
    def __init__(self, recorder, client, venue):
        # ExchangeManager normally injects BinanceClient; its fallback returns
        # BinanceFuturesAdapter, which wraps the same native client. Reuse the
        # connected instance without reconnecting or creating another engine.
        native = getattr(client, 'client', None)
        if venue == 'binance' and callable(getattr(native, 'get_recovery_history_page', None)):
            client = native
        self.recorder, self.client, self.venue = recorder, client, venue
        self.query_count = 0
        self.history = None
        self.common_history = None
        self.job_id = ''
        self.discovering = set()
        self._position_snapshot = None
        self._position_snapshot_at = 0.0

    def begin_job(self, job_id):
        if self.job_id != job_id:
            self._position_snapshot = None
        self.job_id = job_id

    def _queried(self):
        self.query_count += 1

    def retry_pending_evidence(self):
        if self.history is not None:
            with self.history.db() as db:
                db.execute("""UPDATE recovery_history_sessions SET attempt_job=''
                    WHERE scope=? AND refresh_kinds!='' AND (symbol,start) IN
                    (SELECT symbol,start FROM recovery_history_job_sessions WHERE scope=? AND job_id=?)""",
                           (self.history.scope,self.history.scope,self.job_id))

    def repaired_identity(self, before, after):
        """Recognize our atomic provider correction after a process interruption."""
        if self.venue!='binance' or not callable(getattr(self.client,'get_recovery_history_page',None)):
            return False
        if self.history is None:
            self.history=BinanceHistoryRecovery(self.recorder,self.client,self._queried)
        import json
        with self.history.db() as db:
            row=db.execute('SELECT before_json,after_json FROM recovery_cycle_repairs WHERE scope=? AND trade_id=?',
                           (self.history.scope,after['id'])).fetchone()
        if not row: return False
        original=json.loads(row['before_json'])
        return json.loads(row['after_json'])==after and all(original.get(k)==before.get(k) for k in (
            'exchange','symbol','order_id','entry_time','quantity','entry_price','execution_mode','position_owner'))

    def _discover_close(self, trade):
        if self.venue != 'binance' or not callable(getattr(self.client, 'get_recovery_history_page', None)):
            return 'missing_exit_order_evidence'
        self.discovering.add(trade['id'])
        if self.history is None:
            self.history = BinanceHistoryRecovery(self.recorder, self.client, self._queried)
        self.history.begin_job(self.job_id)
        return self.history.recover(trade)

    def _expand_incomplete_order(self, trade, reason):
        # Exact order quantities are not necessarily the whole position: one
        # position can have several closing orders. Expand evidence, never
        # weaken quantity/ownership checks or match by proximity.
        if (self.venue == 'binance' and reason in {'partial_or_quantity_mismatch', 'exchange_fill_not_found'}
                and callable(getattr(self.client, 'get_recovery_history_page', None))):
            self.discovering.add(trade['id'])
            return self._discover_close(trade)
        return reason

    def _restore_linked_close_time(self, venue, trade):
        """Restore a lost close marker, not PnL, from an already owned order.

        No matching by proximity and no provider calls while holding the writer.
        Costs/PnL are deliberately invalidated and reverified by the existing
        exact-order resolver afterwards; legacy stored fee defaults are not proof.
        """
        if not trade.get('exit_order_id'):
            return None, 'open_position_history_unsupported'
        with self.recorder._write_connection(operation='recover_linked_close_time') as db:
            db.row_factory = sqlite3.Row
            current = db.execute('SELECT * FROM trade_log WHERE id=?', (trade['id'],)).fetchone()
            if not current or dict(current) != trade:
                return None, 'record_identity_changed'
            conflict = db.execute('''SELECT 1 FROM trade_log WHERE id!=? AND LOWER(exchange)=?
                AND (exit_order_id=? OR order_id=?) LIMIT 1''',
                (trade['id'], venue, str(trade['exit_order_id']), str(trade['exit_order_id']))).fetchone()
            if conflict or str(trade['order_id']) == str(trade['exit_order_id']):
                return None, 'order_attribution_conflict'
            saved = db.execute('''SELECT * FROM exchange_execution_log
                WHERE exchange=? AND order_id=? AND confirmation_status='confirmed'
                ORDER BY id LIMIT 1000''', (venue, str(trade['exit_order_id']))).fetchall()
            rows = [{'id':r['trade_id'] or r['execution_key'], 'order':r['order_id'],
                     'symbol':r['symbol'], 'side':r['side'], 'amount':r['quantity'],
                     'price':r['price'], 'timestamp':r['executed_at'],
                     '_execution_confirmed':True} for r in saved]
            fills, reason = validate_fills(trade, rows, require_costs=False)
            if reason:
                return None, reason
            entry = self.recorder._ledger_time_epoch(trade['entry_time'])
            epochs = [self.recorder._ledger_time_epoch(r['timestamp']) for r in fills]
            if entry is None or any(t < entry or t > time.time()+5 for t in epochs):
                return None, 'execution_time_outside_position'
            close = max(fills, key=lambda r:self.recorder._ledger_time_epoch(r['timestamp']))['timestamp']
            price = sum(float(r['amount'])*float(r['price']) for r in fills)/float(trade['quantity'])
            db.execute('''UPDATE trade_log SET exit_time=?,exit_price=?,pnl=NULL,net_pnl=NULL,
                gross_pnl=NULL,pnl_percent=NULL,pnl_source='linked_close_pending_costs',
                reconciliation_status='pending_exchange_reconciliation' WHERE id=?''',
                (close, price, trade['id']))
            return dict(db.execute('SELECT * FROM trade_log WHERE id=?', (trade['id'],)).fetchone()), ''

    def __call__(self, venue, trade):
        if venue != self.venue:
            raise ValueError('recovery_scope_mismatch')
        if str(trade.get('execution_mode') or '').lower() in {'live','live_api','optimized','manual'}:
            from trading.recovery_statement import recover_from_statements
            statement = recover_from_statements(self.recorder,venue,trade)
            # An incomplete imported file must not disable the existing API
            # recovery path. With no connected client retain its exact reason.
            if statement == '' or (statement is not None and self.client is None):
                return statement
        if trade.get('exit_time') is None:
            if self.client is None:
                return 'provider_connection_required'
            if str(trade.get('execution_mode') or '').lower() not in {'live','live_api','optimized','manual'}:
                return 'execution_mode_evidence_missing'
            if venue != 'binance' and trade.get('exit_order_id'):
                restored, reason = self._restore_linked_close_time(venue, trade)
                if restored is not None:
                    return self(venue, restored)
                # Do not discard conflicting/incomplete execution evidence just
                # because today's position happens to have the same quantity.
                return reason
            # A real open position must not be closed merely to clear a warning.
            # Reuse the same normalized position/ownership contract as risk.
            getter = getattr(self.client, 'get_positions_result', None)
            if callable(getter) and venue in {'binance','bybit','okx','bitget'}:
                try:
                    if self._position_snapshot is None or time.monotonic()-self._position_snapshot_at > 5:
                        self._queried()
                        self._position_snapshot_at = time.monotonic()
                        try:
                            self._position_snapshot = getter()
                        except Exception:
                            self._position_snapshot = {'status':'error'}
                    snapshot = self._position_snapshot
                    if not isinstance(snapshot, dict) or snapshot.get('status') != 'success' or not isinstance(snapshot.get('positions'), list):
                        return 'provider_query_failed'
                    key = lambda value: str(value).upper().split(':')[0].replace('/','').replace('-','')
                    side = 'SHORT' if str(trade['side']).upper() in {'SELL','SHORT'} else 'LONG'
                    field = lambda p, name: p.get(name) if isinstance(p, dict) else getattr(p, name, None)
                    actual = [p for p in snapshot['positions'] if key(field(p,'symbol')) == key(trade['symbol']) and str(field(p,'side')).upper() == side]
                    owned = [r for r in self.recorder.get_open_managed_trades(venue, strict=True)
                             if key(r['symbol']) == key(trade['symbol']) and
                             ('SHORT' if str(r['side']).upper() in {'SELL','SHORT'} else 'LONG') == side and
                             str(r.get('execution_mode') or '').lower() in {'live','live_api','optimized','manual'}]
                    if len(actual) == 1:
                        raw_size = field(actual[0], 'size')
                        if isinstance(raw_size, bool):
                            return 'provider_query_failed'
                        size = float(raw_size)
                        qty = sum(float(r['quantity']) for r in owned)
                        if math.isfinite(size) and math.isfinite(qty) and size > 0 and math.isclose(size, qty, rel_tol=1e-6, abs_tol=1e-8):
                            return 'position_verified_open'
                except Exception:
                    return 'provider_query_failed'
            # Missing exit_time is precisely what this path repairs. Only the
            # full native cycle proof can establish the missing close time;
            # a flat snapshot or a guessed 'now' timestamp is not evidence.
            if venue == 'binance':
                return self._discover_close(trade)
            return self._discover_common_close(trade)
        if venue in STOCK_VENUES:
            if not trade.get('exit_order_id'):
                return self._discover_common_close(trade)
            from trading.stock_history_recovery import recover_exact_orders
            return recover_exact_orders(self.recorder,self.client,venue,trade,self._queried)
        if trade['id'] in self.discovering:
            return self._discover_close(trade) if venue == 'binance' else self._discover_common_close(trade)
        if not trade.get('exit_order_id'):
            if venue == 'binance' and self.client is not None:
                proof = BinanceCloseEvidence(self.recorder, self.client)
                with proof.connect() as db:
                    exists = db.execute('SELECT 1 FROM binance_close_evidence WHERE entry_order_id=? AND symbol=? LIMIT 1',
                                        (str(trade.get('order_id') or ''), str(trade['symbol']).upper())).fetchone()
                if exists:
                    self.query_count += 4  # at most two protection + fill queries
                    result = proof.sync(limit=2, trade_id=trade['id'])
                    if result['failed']:
                        return 'provider_query_failed'
                    with closing(sqlite3.connect(self.recorder.db_path)) as db:
                        db.row_factory = sqlite3.Row
                        updated = dict(db.execute('SELECT * FROM trade_log WHERE id=?', (trade['id'],)).fetchone())
                    if updated.get('exit_order_id'):
                        return self(venue, updated)
                    return self._discover_close(trade)
            return self._discover_close(trade) if venue=='binance' else self._discover_common_close(trade)
        # Never match by price/time/quantity alone, or invent entry costs.
        if venue in STOCK_VENUES:
            # Current broker history wrappers are today-only and omit fees/tax
            # and lot attribution. Do not advertise them as historical repair.
            fetch = getattr(self.client, 'get_recovery_order_fills', None)
            if not callable(fetch):
                return 'broker_historical_evidence_unsupported'
        if self.client is None:
            return 'provider_connection_required'
        if trade.get('entry_fee') is None:
            if not trade.get('order_id'):
                return 'entry_fee_evidence_missing'
            with closing(sqlite3.connect(self.recorder.db_path)) as db:
                # Shared entry orders require a separately proven lot allocation.
                owners = db.execute('SELECT COUNT(*) FROM trade_log WHERE LOWER(exchange)=? AND symbol=? AND order_id=?',
                                    (venue, trade['symbol'], trade['order_id'])).fetchone()[0]
            if owners != 1:
                return 'entry_order_allocation_required'
            entry = {**trade, 'exit_order_id': trade['order_id'], 'exit_time': trade['entry_time'],
                     'side': 'SHORT' if str(trade['side']).upper() in {'LONG','BUY'} else 'LONG'}
            entry_rows, reason = self._fetch(entry)
            if reason:
                return reason
            entry_rows, reason = validate_fills(entry, entry_rows)
            if reason:
                return self._expand_incomplete_order(trade, reason)
            costs = [(float(row['fee']['cost']), str(row['fee'].get('currency') or '').upper())
                     if isinstance(row.get('fee'), dict)
                     else (float(row['commission']), str(row.get('commission_asset') or row.get('commissionAsset') or '').upper())
                     for row in entry_rows]
            currency = str(trade.get('settlement_currency') or self.recorder._settlement_currency(trade['symbol'], venue)).upper()
            if any(value != 0 and asset != currency for value, asset in costs) or not currency:
                return 'entry_fee_conversion_required'
            self.recorder.save_exchange_execution_history(venue, entry_rows, source='maintenance_entry_order', reconcile=False)
            with closing(sqlite3.connect(self.recorder.db_path, timeout=2)) as db, db:
                updated = db.execute('''UPDATE trade_log SET entry_fee=?,entry_fee_asset=?
                    WHERE id=? AND entry_fee IS NULL AND exchange=? AND symbol=?
                    AND order_id=? AND quantity=? AND entry_time=?''',
                    (sum(value for value, _ in costs), currency, trade['id'], trade['exchange'],
                     trade['symbol'], trade['order_id'], trade['quantity'], trade['entry_time']))
                if not updated.rowcount:
                    return 'record_identity_changed'
        rows, reason = self._fetch(trade)
        if reason:
            return reason
        fills, reason = validate_fills(trade, rows)
        if reason:
            return self._expand_incomplete_order(trade, reason)
        self.recorder.save_exchange_execution_history(venue, fills, source='maintenance_exact_order', reconcile=False)
        self.recorder.reconcile_trade_log_with_executions(venue, trade_ids=[trade['id']])
        return 'provider_pnl_or_cost_evidence_incomplete'

    def _discover_common_close(self,trade):
        if self.venue not in {'okx','bybit','bitget','upbit','bithumb','coinone'}|STOCK_VENUES:
            return 'open_position_history_unsupported'
        if self.common_history is None:
            if self.venue in STOCK_VENUES|{'upbit','bithumb','coinone'}:
                from trading.cash_history_recovery import CashHistoryRecovery
                self.common_history=CashHistoryRecovery(self.recorder,self.client,self.venue,self._queried)
            else:
                from trading.common_history_recovery import CommonHistoryRecovery
                self.common_history=CommonHistoryRecovery(self.recorder,self.client,self.venue,self._queried)
        self.common_history.job_id=self.job_id
        try:
            return self.common_history.recover(trade)
        except Exception as exc:
            if isinstance(exc,RuntimeError) and str(exc) in {
                'recovery_credential_required','position_anchor_unavailable','history_api_permission_required',
                'history_page_incomplete','history_identity_mismatch','history_time_invalid',
                'broker_historical_contract_required','provider_historical_evidence_unsupported',
                'history_fill_identity_missing','partial_or_quantity_mismatch','exchange_fill_not_found'}:
                return str(exc)
            if isinstance(exc,ValueError) and str(exc).startswith('statement_number_'):
                return 'provider_pnl_or_cost_evidence_incomplete'
            if type(exc).__name__ == 'OrderNotFound':
                return 'order_history_incomplete'
            if type(exc).__name__ == 'NotSupported':
                return 'provider_historical_evidence_unsupported'
            raise

    def _fetch(self, trade):
        closed = self.recorder._ledger_time_epoch(trade['exit_time'])
        if closed is None:
            return [], 'execution_time_missing'
        fetch = getattr(self.client, 'get_recovery_order_fills', None)
        if callable(fetch):
            self.query_count += 1
            rows = fetch(trade['symbol'], str(trade['exit_order_id']), closed)
        else:
            exchange = getattr(self.client, 'exchange', None)
            # Use native CCXT errors, not adapters which turn errors into [].
            if exchange is None or not (getattr(exchange, 'has', {}) or {}).get('fetchMyTrades'):
                return [], 'provider_historical_evidence_unsupported'
            normalizer = getattr(self.client, '_normalize_symbol', None)
            symbol = normalizer(trade['symbol']) if callable(normalizer) else trade['symbol']
            if self.venue in {'bybit','okx','bitget'}:
                market = (getattr(exchange, 'markets', {}) or {}).get(symbol, {})
                # Current local legacy ledgers have no per-row contract-size
                # basis. Never compare base units with contracts by accident.
                if market.get('linear') is not True or market.get('contractSize') != 1:
                    return [], 'contract_unit_verification_required'
            self.query_count += 1
            raw = exchange.fetch_my_trades(symbol, int((closed-86400)*1000), 1000, {'paginate': False})
            if not isinstance(raw, list) or len(raw) >= 1000:
                return [], 'history_page_incomplete'
            formatter = getattr(self.client, '_display_symbol', None)
            rows = [normalize_execution(row, symbol_formatter=formatter) for row in raw]
        return rows, ''
