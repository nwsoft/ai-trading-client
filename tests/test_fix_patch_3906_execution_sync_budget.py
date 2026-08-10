from types import SimpleNamespace

from trading.execution_mode import ExecutionMode
from trading.recorder import Recorder
from trading.unified_trader import UnifiedTrader


class _RecorderStub:
    def __init__(self, completed=None, executions=None, cursor=None, references=None):
        self.completed = list(completed or [])
        self.executions = list(executions or [])
        self.cursor = dict(cursor or {})
        self.references = list(references or [])
        self.saved = []

    def get_recent_trades(self, coin="", exchange=None, days=30):
        return list(self.completed)

    def get_recent_exchange_executions(self, exchange, limit=200):
        return list(self.executions)[:limit]

    def get_exchange_execution_cursor(self, exchange):
        return dict(self.cursor)

    def get_exchange_order_references(self, exchange, limit=500):
        return list(self.references)[:limit]

    def save_exchange_execution_history(self, exchange, rows, source=""):
        self.saved.append((exchange, list(rows), source))
        self.executions = list(rows) + self.executions
        return {"inserted": len(rows)}


class _HistoryClient:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls = []

    def get_trade_history(self, **kwargs):
        self.calls.append(dict(kwargs))
        return list(self.rows)


def _trader(recorder, client, mode=ExecutionMode.LIVE):
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.settings = {
        "execution_history_sync_interval_seconds": 300,
        "pending_order_poll_interval_seconds": 10,
    }
    trader.recorder = recorder
    trader.logger = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )
    trader._runtime_execution_sync_state = {}
    trader._runtime_receipt_sync_state = {}
    trader._execution_mode = lambda exchange: mode
    trader.get_exchange_client = lambda exchange: client
    trader.reconcile_exchange_order_receipts = lambda exchange, limit=500: {
        "checked": 0,
        "confirmed": 0,
        "pending": 0,
        "failed": 0,
    }
    return trader


def test_ten_second_analysis_does_not_force_full_history_each_cycle():
    recorder = _RecorderStub(
        completed=[{"symbol": "BTCUSDT", "pnl": 1.2, "exit_time": "2026-08-03 12:00:00"}],
        cursor={"since_ms": 1785730000000, "trade_id": "100"},
    )
    client = _HistoryClient([{"id": "101", "symbol": "BTCUSDT", "quantity": 0.1}])
    trader = _trader(recorder, client)

    first = trader._get_recent_trade_samples_unified("binance", limit=200)
    second = trader._get_recent_trade_samples_unified("binance", limit=200)

    assert first == second == recorder.completed
    assert len(client.calls) == 1
    assert client.calls[0]["since_ms"] == 1785730000000
    assert client.calls[0]["from_id"] == "100"


def test_learning_mode_never_reads_private_history_without_pending_order():
    recorder = _RecorderStub(executions=[{"id": "local-1", "symbol": "SOL/USDT:USDT"}])
    client = _HistoryClient([{"id": "remote-1"}])
    trader = _trader(recorder, client, mode=ExecutionMode.LEARNING)

    result = trader.sync_exchange_execution_ledger("okx")

    assert result["skipped_by_mode"] is True
    assert result["history_requested"] is False
    assert client.calls == []
    assert result["trades"][0]["id"] == "local-1"


def test_pending_order_uses_order_id_reconcile_without_full_history_in_learning():
    recorder = _RecorderStub(
        references=[{"order_id": "pending-1", "symbol": "ETH/USDT:USDT"}]
    )
    client = _HistoryClient([{"id": "remote-1"}])
    trader = _trader(recorder, client, mode=ExecutionMode.LEARNING)
    calls = []
    trader.reconcile_exchange_order_receipts = lambda exchange, limit=500: (
        calls.append((exchange, limit))
        or {"checked": 1, "confirmed": 0, "pending": 1, "failed": 0}
    )

    result = trader.sync_exchange_execution_ledger("bitget")

    assert calls == [("bitget", 200)]
    assert result["pending"] == 1
    assert client.calls == []


def test_manual_full_backfill_omits_incremental_cursor():
    recorder = _RecorderStub(cursor={"since_ms": 1785730000000, "trade_id": "100"})
    client = _HistoryClient([])
    trader = _trader(recorder, client)

    result = trader.sync_exchange_execution_ledger(
        "binance", force=True, full_backfill=True, reason="manual_backfill"
    )

    assert result["history_requested"] is True
    assert result["history_incremental"] is False
    assert client.calls == [{"limit": 200, "since_ms": None, "from_id": None}]


def test_healthy_private_execution_stream_is_preferred_to_periodic_rest():
    class _StreamClient(_HistoryClient):
        def drain_execution_events(self, limit=200):
            return [{
                "id": "stream-1",
                "order": "order-stream-1",
                "symbol": "BTC/USDT:USDT",
                "side": "buy",
                "price": 100,
                "amount": 1,
                "status": "closed",
            }]

        @staticmethod
        def execution_stream_healthy():
            return True

    recorder = _RecorderStub()
    client = _StreamClient([{"id": "rest-1"}])
    trader = _trader(recorder, client)

    result = trader.sync_exchange_execution_ledger("bybit")

    assert result["stream_received"] == 1
    assert client.calls == []
    assert recorder.saved[0][2] == "private_execution_stream"


def test_recorder_returns_local_execution_rows_and_incremental_cursor(tmp_path):
    recorder = Recorder(
        db_path=str(tmp_path / "trading.db"),
        log_path=str(tmp_path / "trading.log"),
        exchange="binance",
    )
    saved = recorder.save_exchange_execution_history(
        "binance",
        [{
            "id": "420",
            "order": "order-420",
            "symbol": "ETHUSDT",
            "side": "sell",
            "price": 2000,
            "amount": 0.1,
            "realized_pnl": 3.5,
            "timestamp": 1785730000000,
            "status": "closed",
        }],
    )

    assert saved["inserted"] == 1
    rows = recorder.get_recent_exchange_executions("binance", limit=10)
    assert rows[0]["realized_pnl"] == 3.5
    assert rows[0]["order_id"] == "order-420"
    cursor = recorder.get_exchange_execution_cursor("binance")
    assert cursor["trade_id"] == "420"
    assert isinstance(cursor["since_ms"], int)


def test_terminal_failed_receipt_is_not_polled_forever(tmp_path):
    recorder = Recorder(
        db_path=str(tmp_path / "trading.db"),
        log_path=str(tmp_path / "trading.log"),
        exchange="bybit",
    )
    assert recorder.save_exchange_order_receipt(
        "bybit",
        {
            "id": "rejected-1",
            "symbol": "ETH/USDT:USDT",
            "side": "buy",
            "status": "rejected",
            "amount": 1,
            "_execution_confirmed": False,
        },
        source="test",
    )

    assert recorder.get_exchange_order_references("bybit") == []
