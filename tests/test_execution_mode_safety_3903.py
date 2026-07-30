from pathlib import Path
from types import SimpleNamespace

from trading.advanced_layer_config import deep_merge_policy, policy_changes
from trading.execution_mode import (
    ExecutionMode,
    resolve_crypto_execution_mode,
    resolve_stock_execution_mode,
)
from trading.stock_analysis_service import StockAnalysisService
from trading.trader import Trader
from trading.unified_trader import UnifiedTrader


ROOT = Path(__file__).resolve().parents[1]


class _Logger:
    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass


class _NoOrderAdapter:
    api_type = "real"

    def __init__(self):
        self.order_calls = 0

    def place_order(self, **_kwargs):
        self.order_calls += 1
        raise AssertionError("PAPER에서 실제 주문 어댑터가 호출되면 안 됩니다")


def test_execution_mode_priority_and_scope_contract():
    paper = {
        "paper_trading": True,
        "trade_enabled_exchanges": ["binance"],
    }
    assert resolve_crypto_execution_mode(paper, "binance") == ExecutionMode.PAPER
    assert resolve_crypto_execution_mode(paper, "bybit") == ExecutionMode.PAPER

    learning = {"paper_trading": False, "trade_enabled_exchanges": []}
    assert resolve_crypto_execution_mode(learning, "binance") == ExecutionMode.LEARNING

    live = {
        "paper_trading": False,
        "trade_enabled_exchanges": ["binance"],
        "_trade_scope_user_confirmed_v3904": True,
    }
    assert resolve_crypto_execution_mode(live, "binance") == ExecutionMode.LIVE
    assert resolve_crypto_execution_mode(live, "okx") == ExecutionMode.LEARNING
    unconfirmed = {"paper_trading": False, "trade_enabled_exchanges": ["binance"]}
    assert resolve_crypto_execution_mode(unconfirmed, "binance") == ExecutionMode.LEARNING

    assert resolve_stock_execution_mode(paper, allow_live_order=True) == ExecutionMode.PAPER
    assert resolve_stock_execution_mode({}, allow_live_order=False) == ExecutionMode.LEARNING
    assert resolve_stock_execution_mode({}, allow_live_order=True) == ExecutionMode.LIVE


def test_binance_low_level_order_guard_is_fail_closed_in_paper():
    trader = Trader.__new__(Trader)
    trader.settings = {
        "paper_trading": True,
        "trade_enabled_exchanges": ["binance"],
    }
    trader.binance_client = _NoOrderAdapter()
    trader.log_event = lambda *_args, **_kwargs: None

    success, result, errors = trader._place_binance_order_once(
        "BTCUSDT", "BUY", 0.01, "MARKET"
    )

    assert success is False
    assert result["status"] == "BLOCKED"
    assert errors
    assert trader.binance_client.order_calls == 0


def test_binance_paper_position_does_not_touch_live_store(monkeypatch):
    trader = Trader.__new__(Trader)
    trader.settings = {
        "paper_trading": True,
        "trade_enabled_exchanges": ["binance"],
        "max_positions": 3,
    }
    trader.binance_client = SimpleNamespace(get_current_price=lambda _symbol: 100.0)
    trader.active_positions = {"ETHUSDT": object()}
    trader.paper_active_positions = {}
    trader.paper_trade_stats = {
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "total_pnl": 0.0,
    }
    trader.log_event = lambda *_args, **_kwargs: None
    monkeypatch.setattr(
        "trading.trader.emit_position_opened",
        lambda **_kwargs: (False, "paper-position"),
    )

    result = trader._execute_paper_trade(
        "BTCUSDT",
        {"side": "BUY", "qty": 0.1, "price": 100.0, "tp": 0.01, "sl": 0.01},
    )

    assert result["simulated"] is True
    assert "BTCUSDT" in trader.paper_active_positions
    assert set(trader.active_positions) == {"ETHUSDT"}
    assert trader.get_active_positions() is trader.paper_active_positions


def test_unified_paper_restore_and_tp_repair_never_query_exchange():
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.settings = {"paper_trading": True, "trade_enabled_exchanges": ["bybit"]}
    trader.trade_enabled_exchanges = ["bybit"]
    trader.active_positions = {"bybit": {"LIVE": object()}}
    trader.paper_positions = {"bybit": {}}
    trader.logger = _Logger()
    trader.get_exchange_client = lambda _exchange: (_ for _ in ()).throw(
        AssertionError("실거래 클라이언트를 조회하면 안 됩니다")
    )

    trader._restore_positions_from_exchange("bybit")
    trader._verify_and_repair_tp_sl("bybit", interval_sec=0)

    assert trader.active_positions["bybit"] == {"LIVE": trader.active_positions["bybit"]["LIVE"]}
    assert trader._position_store("bybit") is trader.paper_positions["bybit"]


def test_stock_paper_order_uses_internal_store_only():
    adapter = _NoOrderAdapter()
    service = StockAnalysisService(adapter, broker_name="paper-test", recorder=None)
    service._paper_positions_by_broker.pop("paper-test", None)

    success, result, errors = service._place_paper_stock_order(
        symbol="005930",
        side="BUY",
        quantity=2,
        price=70000,
        order_type="MARKET",
    )

    assert success is True
    assert errors == []
    assert result["simulated"] is True
    assert service._paper_positions()["005930"]["quantity"] == 2
    assert adapter.order_calls == 0


def test_advanced_preset_deep_merge_applies_detailed_values():
    current = {
        "profitability_validation": {"enabled": False, "min_win_rate": 0.9},
        "strategy_engine": {"enabled": False, "cooldown_sec": 60},
    }
    preset = {
        "profitability_validation": {"enabled": True, "min_win_rate": 0.45},
        "strategy_engine": {"enabled": True, "consensus_threshold": 0.7},
    }

    merged = deep_merge_policy(current, preset)
    changes = policy_changes(current, merged)

    assert merged["profitability_validation"]["min_win_rate"] == 0.45
    assert merged["strategy_engine"]["cooldown_sec"] == 60
    assert merged["strategy_engine"]["consensus_threshold"] == 0.7
    assert {item["path"] for item in changes} >= {
        "profitability_validation.min_win_rate",
        "strategy_engine.consensus_threshold",
    }


def test_always_on_top_default_is_consistently_off_and_stock_layers_are_wired():
    settings_source = (ROOT / "ui" / "settings_modern.py").read_text(encoding="utf-8")
    dashboard_source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")

    assert "get('always_on_top', True)" not in settings_source
    assert "get('always_on_top', True)" not in dashboard_source
    assert "auto_risk_policy=auto_risk_policy" in dashboard_source
    assert "execution_mode_override=stock_execution_mode.value" in dashboard_source
