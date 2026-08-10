from pathlib import Path

from trading.exchanges.adapters.bithumb_spot_adapter import BithumbSpotAdapter
from trading.recorder import Recorder
from trading.unified_trader import UnifiedTrader


ROOT = Path(__file__).resolve().parents[1]


def test_ccxt_closed_order_is_successful():
    trader = UnifiedTrader.__new__(UnifiedTrader)
    assert trader._is_order_success(
        {
            "id": "bithumb-order-1",
            "symbol": "XRP/KRW",
            "status": "closed",
        }
    )
    assert not trader._is_order_success(
        {
            "id": "bithumb-order-2",
            "symbol": "XRP/KRW",
            "status": "canceled",
        }
    )


def test_bithumb_execution_normalizer_preserves_dynamic_symbol_and_fill():
    adapter = BithumbSpotAdapter("", "")
    normalized = adapter._normalize_execution_trade(
        {
            "id": "trade-1",
            "order": "order-1",
            "symbol": "XRP/KRW",
            "side": "buy",
            "price": 845.5,
            "amount": 12.0,
            "timestamp": 1785416400000,
        }
    )
    assert normalized["symbol"] == "XRP/KRW"
    assert normalized["amount"] == 12.0
    assert normalized["cost"] == 10146.0


def test_bithumb_empty_history_does_not_permanently_disable_future_sync():
    class _Exchange:
        has = {"fetchMyTrades": False, "fetchClosedOrders": True}

        def __init__(self):
            self.calls = 0

        def fetch_closed_orders(self, symbol, limit=100):
            self.calls += 1
            if self.calls == 1:
                return []
            return [{
                "id": "later-fill-1",
                "symbol": symbol or "RLC/KRW",
                "side": "buy",
                "status": "closed",
                "filled": 2,
                "average": 400,
                "cost": 800,
            }]

    adapter = BithumbSpotAdapter("key", "secret")
    adapter.exchange = _Exchange()
    adapter.is_connected = True

    assert adapter.get_trade_history(symbol="RLC/KRW") == []
    assert adapter._trade_history_mode == "orders_fallback"

    rows = adapter.get_trade_history(symbol="RLC/KRW")
    assert [row["id"] for row in rows] == ["later-fill-1"]
    assert adapter.get_execution_capabilities()["history_available"] is True


def test_exchange_execution_history_is_separate_and_deduplicated(tmp_path):
    db_path = tmp_path / "trading.db"
    log_path = tmp_path / "trading.log"
    recorder = Recorder(
        db_path=str(db_path),
        log_path=str(log_path),
        exchange="bithumb",
    )
    trade = {
        "id": "trade-1",
        "order": "order-1",
        "symbol": "XRP/KRW",
        "side": "buy",
        "price": 845.5,
        "amount": 12.0,
        "cost": 10146.0,
        "timestamp": 1785416400000,
        "fee": {"cost": 2.54, "currency": "KRW"},
        "status": "closed",
    }

    first = recorder.save_exchange_execution_history("bithumb", [trade])
    second = recorder.save_exchange_execution_history("bithumb", [trade])

    assert first == {"received": 1, "inserted": 1, "skipped": 0}
    assert second == {"received": 1, "inserted": 0, "skipped": 1}
    rows = recorder.execute_query(
        """
        SELECT exchange, symbol, side, price, quantity, cost, fee, fee_currency
        FROM exchange_execution_log
        """
    )
    assert rows == [
        ("bithumb", "XRP/KRW", "buy", 845.5, 12.0, 10146.0, 2.54, "KRW")
    ]
    assert recorder.execute_query("SELECT COUNT(*) FROM trade_log") == [(0,)]


def test_order_receipt_can_be_reconciled_by_order_id_without_history_api(tmp_path):
    recorder = Recorder(
        db_path=str(tmp_path / "trading.db"),
        log_path=str(tmp_path / "trading.log"),
        exchange="bithumb",
    )
    assert recorder.save_exchange_order_receipt(
        "bithumb",
        {
            "id": "order-restore-1",
            "order": "order-restore-1",
            "symbol": "RLC/KRW",
            "side": "buy",
            "status": "open",
            "amount": 2,
            "_execution_confirmed": False,
        },
        source="noahai_entry_order",
    )

    class _Exchange:
        def fetch_order(self, order_id, symbol=None):
            return {
                "id": order_id,
                "symbol": symbol,
                "side": "buy",
                "status": "closed",
                "filled": 2,
                "average": 400,
                "cost": 800,
                "timestamp": 1785502800000,
            }

    class _Adapter:
        exchange = _Exchange()

        @staticmethod
        def _display_symbol(value):
            return value

    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.recorder = recorder
    trader.logger = type("_Logger", (), {"warning": lambda *args, **kwargs: None})()
    trader.get_exchange_client = lambda exchange: _Adapter()

    result = trader.reconcile_exchange_order_receipts("bithumb")
    assert result == {"checked": 1, "confirmed": 1, "pending": 0, "failed": 0}
    assert recorder.execute_query(
        "SELECT exchange, order_id, cost, confirmation_status FROM exchange_execution_log"
    ) == [("bithumb", "order-restore-1", 800.0, "confirmed")]


def test_trade_exit_matches_exchange_and_order_id(tmp_path):
    from datetime import datetime, timezone
    from trading.recorder import TradeLog

    recorder = Recorder(
        db_path=str(tmp_path / "trading.db"),
        log_path=str(tmp_path / "trading.log"),
    )
    now = datetime.now(timezone.utc)
    for exchange, order_id in (("upbit", "u-1"), ("bithumb", "b-1")):
        recorder.insert_trade_log(TradeLog(
            id=None, symbol="RLC/KRW", entry_price=400, exit_price=None,
            quantity=2, leverage=1, pnl=None, pnl_percent=None,
            entry_time=now, exit_time=None, reason="entry", side="LONG",
            tp_price=None, sl_price=None, fees=0, slippage=0,
            exchange=exchange, order_id=order_id,
        ))

    assert recorder.update_trade_on_exit(
        "RLC/KRW", now, exit_price=410, pnl=20, pnl_percent=2.5,
        fees=1, slippage=0, reason="exit", side="LONG",
        exchange="bithumb", entry_order_id="b-1", exit_order_id="b-2",
    )
    assert recorder.execute_query(
        "SELECT exchange, exit_time IS NOT NULL, exit_order_id FROM trade_log ORDER BY exchange"
    ) == [("bithumb", 1, "b-2"), ("upbit", 0, None)]


def test_settings_save_synchronizes_existing_unified_trader():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    block = source.split(
        "# UnifiedTrader가 매니저 참조를 가진 경우 갱신", 1
    )[1].split("# 테마 설정 처리 제거됨", 1)[0]
    assert "update_trader_settings(self.settings)" in block


def test_service_switch_keeps_dashboard_dispatch_queue_alive():
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    block = source.split("    def switch_service(", 1)[1].split(
        "    def _get_ops_kpi_specs_for_service", 1
    )[0]
    assert "self.cleanup_after_jobs()" not in block
    assert "self.cleanup_all_widgets()" not in block
    assert "self._destroy_all_service_tabs_except_protected()" in block


def test_trading_stats_supports_non_binance_execution_ledger():
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    assert "def _get_crypto_trade_history_adapter" in source
    assert "save_exchange_execution_history" in source
    assert "def _render_exchange_execution_history" in source
    assert "승률·PnL은 NoahAI가 추적한 청산 완료 거래만 계산합니다." in source


def test_runtime_trade_samples_reconcile_exchange_history_into_ledger():
    class _Client:
        def get_trade_history(self, limit=100):
            return [{"id": "fill-1", "symbol": "SOL/USDT", "amount": 1}]

    class _Recorder:
        def __init__(self):
            self.calls = []

        def save_exchange_execution_history(self, exchange, rows, source=""):
            self.calls.append((exchange, rows, source))

    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.recorder = _Recorder()
    trader.get_exchange_client = lambda exchange: _Client()
    rows = trader._get_recent_trade_samples_unified("okx", limit=20)

    assert rows == [{"id": "fill-1", "symbol": "SOL/USDT", "amount": 1}]
    assert trader.recorder.calls == [
        ("okx", rows, "runtime_exchange_backfill")
    ]
