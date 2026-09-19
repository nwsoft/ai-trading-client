import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

from trading.trader import Trader
from trading.trading_worker import TradingWorker


def _bare_trader(position_result):
    trader = Trader.__new__(Trader)
    trader.binance_client = SimpleNamespace(get_positions_result=MagicMock(return_value=position_result))
    trader.trade_entered = {}
    trader.active_positions = {}
    trader.monitoring_threads = {}
    trader.monitoring_flags = {}
    trader.log_event = MagicMock()
    return trader


def test_worker_runs_one_immediate_cycle_then_waits(monkeypatch):
    monkeypatch.setattr("log_system.log_adapter.log_event", lambda *args, **kwargs: None)

    worker = TradingWorker.__new__(TradingWorker)
    worker.main_app = SimpleNamespace(settings={"selected_exchange": "binance"})
    worker.running = True
    worker.interval = 60
    worker.stop_event = threading.Event()
    worker.cleanup_memory = MagicMock()
    worker._run_binance_trading = MagicMock()
    worker._run_unified_trading = MagicMock()

    waits = []

    def stop_on_first_wait(timeout):
        waits.append(timeout)
        worker.running = False
        return True

    worker.stop_event.wait = stop_on_first_wait
    worker.run_trading_loop()

    worker._run_binance_trading.assert_called_once_with()
    assert waits == [60.0]


def test_zombie_cleanup_without_flags_does_not_query_exchange():
    trader = _bare_trader({"status": "success", "positions": []})

    trader._cleanup_zombie_flags()

    trader.binance_client.get_positions_result.assert_not_called()


def test_position_query_failure_preserves_live_state():
    trader = _bare_trader({"status": "error", "positions": [], "error": "timeout"})
    trader.trade_entered = {"BTCUSDT": True}
    trader.active_positions = {"BTCUSDT": object()}
    monitor = object()
    trader.monitoring_threads = {"BTCUSDT": monitor}
    trader.monitoring_flags = {"BTCUSDT": True}

    trader._cleanup_zombie_flags()

    assert trader.trade_entered["BTCUSDT"] is True
    assert trader.active_positions["BTCUSDT"] is not None
    assert trader.monitoring_threads["BTCUSDT"] is monitor
    assert trader.monitoring_flags["BTCUSDT"] is True


def test_confirmed_empty_snapshot_clears_stale_flag_and_monitor_handles():
    trader = _bare_trader({"status": "success", "positions": []})
    trader.trade_entered = {"BTCUSDT": True}
    trader.monitoring_threads = {"BTCUSDT": object()}
    trader.monitoring_flags = {"BTCUSDT": True}

    trader._cleanup_zombie_flags()

    assert trader.trade_entered["BTCUSDT"] is False
    assert "BTCUSDT" not in trader.monitoring_threads
    assert "BTCUSDT" not in trader.monitoring_flags


def test_confirmed_exchange_position_keeps_flag():
    position = SimpleNamespace(symbol="BTCUSDT")
    trader = _bare_trader({"status": "success", "positions": [position]})
    trader.trade_entered = {"BTCUSDT": True}
    monitor = object()
    trader.monitoring_threads = {"BTCUSDT": monitor}
    trader.monitoring_flags = {"BTCUSDT": True}

    trader._cleanup_zombie_flags()

    assert trader.trade_entered["BTCUSDT"] is True
    assert trader.monitoring_threads["BTCUSDT"] is monitor
    assert trader.monitoring_flags["BTCUSDT"] is True


def test_snapshot_helper_prefers_statusful_api_over_ambiguous_legacy_list():
    trader = Trader.__new__(Trader)
    statusful = MagicMock(return_value={"status": "error", "positions": [], "error": "clock skew"})
    legacy = MagicMock(return_value=[])
    trader.binance_client = SimpleNamespace(
        get_positions_result=statusful,
        get_positions=legacy,
    )

    result = trader._get_binance_position_snapshot()

    assert result["status"] == "error"
    statusful.assert_called_once_with()
    legacy.assert_not_called()
