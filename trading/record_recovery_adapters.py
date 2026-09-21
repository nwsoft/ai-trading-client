"""Read-only recovery adapters. Unsupported != no trades != verified zero PnL."""
import sqlite3
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
        self.job_id = ''
        self.discovering = set()

    def begin_job(self, job_id):
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

    def __call__(self, venue, trade):
        if venue != self.venue:
            raise ValueError('recovery_scope_mismatch')
        if trade['id'] in self.discovering:
            return self._discover_close(trade)
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
            return self._discover_close(trade)
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
