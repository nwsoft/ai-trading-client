from __future__ import annotations

import threading
from pathlib import Path

import pytest

from trading.account_state_contract import classify_spot_holdings
from trading.trading_worker import TradingWorker
from trading.stock_runtime_controller import StockRuntimeController
from trading.unified_trader import UnifiedTrader
from web_platform.headless_runtime import HeadlessTradingRuntime
from web_platform.runtime_bridge import LazyLegacyRuntimeBridge


def test_spot_holdings_keep_tiny_assets_visible_but_classify_automation_scope():
    rows = classify_spot_holdings(
        {
            "KRW": 100_000,
            "BTC": 1.5,
            "ETH": 0.00000001,
            "GAS": 0.001331,
            "VTHO": 14.178887,
        },
        managed_quantities={"BTC": 0.5},
        exchange_tradable_assets={"BTC", "ETH", "GAS"},
        noahai_eligible_assets={"BTC", "ETH"},
    )

    assert set(rows) == {"BTC", "ETH", "GAS", "VTHO"}
    assert rows["BTC"]["ownership"] == "mixed"
    assert rows["BTC"]["managed_quantity"] == pytest.approx(0.5)
    assert rows["BTC"]["external_quantity"] == pytest.approx(1.0)
    assert rows["ETH"]["display_group"] == "external_tradable"
    assert rows["GAS"]["display_group"] == "external_unsupported_market"
    assert rows["VTHO"]["display_group"] == "reference_unavailable"
    assert all(rows[asset]["auto_trade_managed"] is False for asset in ("ETH", "GAS", "VTHO"))


def test_spot_snapshot_uses_noahai_ledger_quantity_not_whole_account_balance():
    class Exchange:
        markets = {
            "BTC/KRW": {"base": "BTC", "quote": "KRW", "spot": True, "active": True},
            "GAS/USDT": {"base": "GAS", "quote": "USDT", "spot": True, "active": True},
        }

    class Client:
        exchange = Exchange()

        @staticmethod
        def get_open_orders():
            return []

    class Manager:
        @staticmethod
        def get_exchange_balance(source, force_refresh=False):
            return {
                "status": "success",
                "balance": {"KRW": 50_000, "BTC": 1.4, "GAS": 0.1, "VTHO": 3.0},
            }

        @staticmethod
        def get_exchange_client(source):
            return Client()

    class Recorder:
        @staticmethod
        def get_open_managed_trades(source):
            assert source == "upbit"
            return [{
                "symbol": "BTC/KRW",
                "quantity": 0.4,
                "spot_baseline_quantity": 1.0,
                "position_owner": "noahai",
                "order_id": "noah-entry-1",
            }]

    class App:
        exchange_manager = Manager()
        recorder = Recorder()

        @staticmethod
        def _running_crypto_exchanges():
            return []

    bridge = LazyLegacyRuntimeBridge(account="tester", factory=lambda account: App())
    bridge._settings = lambda: {"upbit_api_key": "key", "upbit_secret_key": "secret"}

    account = bridge.account_snapshot(sources=["upbit"], force_refresh=True)["sources"]["upbit"]
    by_asset = {row["symbol"]: row for row in account["positions"]}

    assert by_asset["BTC"]["managed_quantity"] == pytest.approx(0.4)
    assert by_asset["BTC"]["external_quantity"] == pytest.approx(1.0)
    assert by_asset["BTC"]["ownership"] == "mixed"
    assert by_asset["GAS"]["display_group"] == "external_unsupported_market"
    assert by_asset["VTHO"]["display_group"] == "reference_unavailable"
    assert account["spot_holding_summary"] == {
        "account_total": 3,
        "noahai_managed": 1,
        "external_tradable": 0,
        "reference_only": 2,
    }


def test_web_worker_stop_can_leave_unified_workers_to_batch_coordinator(monkeypatch):
    unified_calls = []

    class Unified:
        monitoring_flags = {"upbit": True, "bithumb": True}

        @staticmethod
        def stop_trading(source, close_all=False):
            unified_calls.append((source, close_all))

    class App:
        settings = {"asset_stop_position_policy": "keep_with_tp_sl"}
        trader = None
        unified_trader = Unified()

    monkeypatch.setattr("log_system.log_adapter.log_event", lambda *args, **kwargs: None)
    worker = TradingWorker.__new__(TradingWorker)
    worker.main_app = App()
    worker.running = True
    worker.stop_event = threading.Event()

    worker.stop(stop_unified=False)

    assert worker.running is False
    assert worker.stop_event.is_set()
    assert unified_calls == []


def test_web_worker_request_stop_is_non_blocking(monkeypatch):
    calls = []

    class Trader:
        @staticmethod
        def request_stop_trading():
            calls.append("native_signal")

        @staticmethod
        def stop_trading():
            raise AssertionError("blocking stop must not run")

    class App:
        trader = Trader()
        unified_trader = None

    monkeypatch.setattr("log_system.log_adapter.log_event", lambda *args, **kwargs: None)
    worker = TradingWorker.__new__(TradingWorker)
    worker.main_app = App()
    worker.running = True
    worker.stop_event = threading.Event()

    worker.request_stop(stop_unified=False)

    assert worker.running is False
    assert worker.stop_event.is_set()
    assert calls == ["native_signal"]


def test_headless_binance_stop_is_not_sent_twice():
    calls = []

    class Trader:
        @staticmethod
        def stop_trading():
            calls.append("trader")

    class Worker:
        @staticmethod
        def stop(*, stop_unified=True):
            calls.append(("worker", stop_unified))

        @staticmethod
        def request_stop(*, stop_unified=True):
            calls.append(("request", stop_unified))

    runtime = HeadlessTradingRuntime.__new__(HeadlessTradingRuntime)
    runtime.trader = Trader()
    runtime.trading_worker = Worker()
    runtime.trading_thread = None

    runtime.stop_trading_loop()

    assert calls == [("request", False)]


def test_unified_shutdown_broadcasts_before_shared_wait(monkeypatch):
    events = []

    class Thread:
        def __init__(self, venue):
            self.venue = venue
            self.alive = True

        def is_alive(self):
            return self.alive

        def join(self, timeout=None):
            events.append(("join", self.venue, timeout))
            self.alive = False

    class Logger:
        @staticmethod
        def info(*args, **kwargs):
            return None

        @staticmethod
        def warning(*args, **kwargs):
            return None

    trader = UnifiedTrader.__new__(UnifiedTrader)
    venues = ("upbit", "bithumb", "bybit", "bitget", "okx")
    trader.monitoring_flags = {venue: True for venue in venues}
    trader.trading_cycles = {venue: True for venue in venues}
    trader.monitoring_threads = {venue: Thread(venue) for venue in venues}
    trader.logger = Logger()
    monkeypatch.setattr("trading.unified_trader.flush_kpi_events", lambda timeout=0: events.append(("flush", timeout)))

    for venue in venues:
        trader.request_trading_stop(venue)
        events.append(("signal", venue))
    result = trader.wait_for_trading_stops(list(venues), timeout=12.0)

    assert trader.monitoring_flags == {venue: False for venue in venues}
    assert trader.trading_cycles == {venue: False for venue in venues}
    assert [event[:2] for event in events[:2]] == [("signal", "upbit"), ("signal", "bithumb")]
    assert result == {"stopped": list(venues), "alive": []}


def test_timed_out_individual_stop_keeps_thread_for_later_safe_shutdown(monkeypatch):
    class Thread:
        @staticmethod
        def is_alive():
            return True

        @staticmethod
        def join(timeout=None):
            return None

    class Logger:
        warnings = []

        @staticmethod
        def info(*args, **kwargs):
            return None

        @classmethod
        def warning(cls, message, *args, **kwargs):
            cls.warnings.append(message)

        @staticmethod
        def error(*args, **kwargs):
            return None

    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.monitoring_flags = {"upbit": True}
    trader.trading_cycles = {"upbit": True}
    trader.monitoring_threads = {"upbit": Thread()}
    trader.logger = Logger()
    monkeypatch.setattr("trading.unified_trader.flush_kpi_events", lambda timeout=0: None)

    trader.stop_trading("upbit")

    assert trader.monitoring_flags["upbit"] is False
    assert "upbit" in trader.monitoring_threads
    assert any("worker가 현재 API/분석 경계를 정리" in message for message in Logger.warnings)


def test_headless_lifecycle_registry_keeps_stop_requested_live_worker_visible():
    class Thread:
        @staticmethod
        def is_alive():
            return True

    runtime = HeadlessTradingRuntime.__new__(HeadlessTradingRuntime)
    runtime.trading_worker = None
    runtime.trading_thread = None
    runtime.unified_trader = type("Unified", (), {
        "monitoring_flags": {"upbit": False},
        "monitoring_threads": {"upbit": Thread()},
    })()

    assert runtime.running_crypto_exchanges() == []
    assert runtime.live_crypto_workers() == ["upbit"]


def test_stock_stop_timeout_returns_false_and_worker_remains_discoverable():
    class Thread:
        @staticmethod
        def is_alive():
            return True

        @staticmethod
        def join(timeout=None):
            return None

    controller = StockRuntimeController(settings_provider=lambda: {})
    controller._events["koreaInvestment"] = threading.Event()
    controller._threads["koreaInvestment"] = Thread()

    assert controller.stop("kis", timeout=0) is False
    assert controller.running_sources() == []
    assert controller.live_worker_sources() == ["kis"]


@pytest.mark.parametrize("broker", ["kiwoom", "shinhan", "miraeAsset", "koreaInvestment"])
def test_stock_lifecycle_includes_and_releases_adapter_created_by_read_only_view(broker):
    events = []

    class Adapter:
        @staticmethod
        def disconnect():
            events.append("disconnect")
            return True

    controller = StockRuntimeController(settings_provider=lambda: {})
    controller._adapters[broker] = Adapter()

    public = {"miraeAsset": "mirae", "koreaInvestment": "kis"}.get(broker, broker)

    assert controller.running_sources() == []
    assert controller.live_worker_sources() == []
    assert controller.lifecycle_sources() == [public]
    assert controller.stop_all(timeout=1) == {"stopped": [public], "alive": []}
    assert events == ["disconnect"]
    assert controller.lifecycle_sources() == []


def test_headless_shutdown_releases_idle_stock_adapter_without_started_worker(monkeypatch):
    events = []

    class StockController:
        sources = ["kiwoom"]

        @classmethod
        def lifecycle_sources(cls):
            return list(cls.sources)

        @staticmethod
        def live_worker_sources():
            return []

        @staticmethod
        def live_child_sources():
            return []

        @staticmethod
        def request_stop(source):
            events.append(("stock_signal", source))

        @classmethod
        def wait_for_stops(cls, sources, timeout=0):
            events.append(("stock_wait", tuple(sources)))
            cls.sources = []
            return {"stopped": list(sources), "alive": []}

    class Recorder:
        @staticmethod
        def flush_to_db(timeout=0):
            return True

    runtime = HeadlessTradingRuntime.__new__(HeadlessTradingRuntime)
    runtime._shutdown_lock = threading.Lock()
    runtime._shutdown_complete = False
    runtime._accepting_commands = True
    runtime.alpha_arena_runner = None
    runtime.stock_runtime_controller = StockController()
    runtime.unified_trader = None
    runtime.api_signal_manager = None
    runtime.auto_optimizer = None
    runtime.recorder = Recorder()
    runtime.running_crypto_exchanges = lambda: []
    runtime.live_crypto_workers = lambda: []
    monkeypatch.setattr("log_system.log_adapter.flush_pending_logs", lambda: None)
    monkeypatch.setattr("utils.runtime_stability.mark_clean_shutdown", lambda reason: None)

    result = runtime.shutdown()

    assert result["safe_to_exit"] is True
    assert events == [("stock_signal", "kiwoom"), ("stock_wait", ("kiwoom",))]


def test_headless_shutdown_signals_all_unified_workers_before_wait(monkeypatch):
    events = []

    class Unified:
        @staticmethod
        def request_trading_stop(source):
            events.append(("signal", source))

        @staticmethod
        def wait_for_trading_stops(sources, timeout=0):
            events.append(("wait", tuple(sources), timeout))
            return {"stopped": list(sources), "alive": []}

    class StockController:
        @staticmethod
        def running_sources():
            return []

    class Recorder:
        @staticmethod
        def flush_to_db(timeout=0):
            events.append(("recorder_flush", timeout))
            return True

    runtime = HeadlessTradingRuntime.__new__(HeadlessTradingRuntime)
    runtime._shutdown_lock = threading.Lock()
    runtime._shutdown_complete = False
    runtime._accepting_commands = True
    runtime.alpha_arena_runner = None
    runtime.stock_runtime_controller = StockController()
    runtime.unified_trader = Unified()
    runtime.api_signal_manager = None
    runtime.auto_optimizer = None
    runtime.recorder = Recorder()
    runtime.running_crypto_exchanges = lambda: [
        "binance", "upbit", "bithumb", "bybit", "bitget", "okx"
    ]
    runtime.live_crypto_workers = lambda: []
    runtime.request_trading_loop_stop = lambda: events.append(("signal", "binance"))
    runtime.wait_for_trading_loop_stop = lambda timeout: events.append(("wait", "binance", timeout)) or True
    monkeypatch.setattr("log_system.log_adapter.flush_pending_logs", lambda: events.append(("log_flush",)))
    monkeypatch.setattr("utils.runtime_stability.mark_clean_shutdown", lambda reason: events.append(("clean", reason)))

    result = runtime.shutdown()

    assert result["safe_to_exit"] is True
    assert events[:8][0:6] == [
        ("signal", "upbit"),
        ("signal", "bithumb"),
        ("signal", "bybit"),
        ("signal", "bitget"),
        ("signal", "okx"),
        ("signal", "binance"),
    ]
    assert events[6][0:2] == ("wait", "binance")
    assert events[7][0:2] == (
        "wait", ("upbit", "bithumb", "bybit", "bitget", "okx")
    )


def test_failed_shutdown_does_not_write_clean_marker_and_retry_sees_live_worker(monkeypatch):
    events = []

    class Thread:
        @staticmethod
        def is_alive(): return True
        @staticmethod
        def join(timeout=None): events.append(("join", timeout))

    class Unified:
        monitoring_flags = {"upbit": False}
        monitoring_threads = {"upbit": Thread()}
        trading_cycles = {"upbit": False}

        @staticmethod
        def request_trading_stop(source): events.append(("signal", source))
        @staticmethod
        def wait_for_trading_stops(sources, timeout=0):
            return {"stopped": [], "alive": list(sources)}

    class StockController:
        @staticmethod
        def running_sources(): return []

    class Recorder:
        @staticmethod
        def flush_to_db(timeout=0): return True

    runtime = HeadlessTradingRuntime.__new__(HeadlessTradingRuntime)
    runtime._shutdown_lock = threading.Lock()
    runtime._shutdown_complete = False
    runtime._accepting_commands = True
    runtime.alpha_arena_runner = None
    runtime.stock_runtime_controller = StockController()
    runtime.unified_trader = Unified()
    runtime.trading_worker = None
    runtime.trading_thread = None
    runtime.api_signal_manager = None
    runtime.auto_optimizer = None
    runtime.recorder = Recorder()
    monkeypatch.setattr("log_system.log_adapter.flush_pending_logs", lambda: events.append(("log_flush",)))
    monkeypatch.setattr("utils.runtime_stability.mark_clean_shutdown", lambda reason: events.append(("clean", reason)))

    first = runtime.shutdown()
    second = runtime.shutdown()

    assert first["safe_to_exit"] is False
    assert second["safe_to_exit"] is False
    assert first["running_sources"] == ["upbit"]
    assert [event for event in events if event == ("signal", "upbit")] == [
        ("signal", "upbit"), ("signal", "upbit")
    ]
    assert not any(event[0] in {"log_flush", "clean"} for event in events)


def test_electron_shutdown_uses_extended_deadline_and_surfaces_worker_error():
    source = Path("webui/electron/main.cjs").read_text(encoding="utf-8")

    assert "requestSafeGatewayShutdown(timeoutMs = 60000)" in source
    assert "detailPayload?.result?.errors" in source
    assert 'error.name === "AbortError"' in source
    assert "안전 종료가 ${Math.round(timeoutMs / 1000)}초 안에 끝나지 않았습니다" in source
