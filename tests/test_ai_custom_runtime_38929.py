from trading.custom_strategy_runtime import (
    apply_engine_settings_to_trade_config,
    limited_live_engine_settings,
    normalize_engine_settings,
)
from trading.custom_strategy_validator import run_historical_replay
from trading.declarative_strategy_engine import DeclarativeStrategyEngine


def test_percent_points_are_converted_once_to_order_fractions():
    runtime = normalize_engine_settings({
        "_unit": "percent_points", "tp_percent": 2.0, "sl_percent": 1.0,
        "position_size": 0.05, "leverage": 2,
    })
    assert runtime["tp_percent"] == 0.02
    assert runtime["sl_percent"] == 0.01
    applied = apply_engine_settings_to_trade_config({"qty": 1.0}, runtime)
    assert applied["tp"] == 0.02
    assert applied["sl"] == 0.01
    assert applied["position_size_factor"] == 0.5
    assert applied["qty"] == 0.5


def test_limited_live_forces_one_x_and_one_percent_without_changing_tp_sl():
    limited = limited_live_engine_settings({
        "_unit": "percent_points", "leverage": 8, "position_size": 0.25,
        "tp_percent": 2.0, "sl_percent": 1.0,
    })
    assert limited["leverage"] == 1
    assert limited["position_size"] == 0.01
    assert limited["tp_percent"] == 0.02
    assert limited["sl_percent"] == 0.01
    applied = apply_engine_settings_to_trade_config({"qty": 10.0}, limited)
    assert round(applied["qty"], 8) == 1.0


def test_independent_strategy_can_create_signal_from_hold_but_confirm_cannot():
    common = {
        "target_scope": "exchange:okx", "market_regimes": ["range"], "priority": 8,
        "entry_signal": "LONG",
        "rules": {"executable_entry": {"all": [{"field": "rsi", "operator": "lt", "value": 40}]}},
    }
    independent = DeclarativeStrategyEngine.evaluate_strategy_pool(
        [{**common, "name": "독립", "signal_mode": "independent"}],
        {"signal": "HOLD", "rsi": 30}, asset_class="crypto", target="okx", market_regime="range",
    )
    assert independent["allowed"] is True
    assert independent["entry_signal"] == "LONG"
    confirm = DeclarativeStrategyEngine.evaluate_strategy_pool(
        [{**common, "name": "확인", "signal_mode": "confirm"}],
        {"signal": "HOLD", "rsi": 30}, asset_class="crypto", target="okx", market_regime="range",
    )
    assert confirm["bypassed"] is True
    assert "selected_strategy_name" not in confirm


def test_historical_replay_uses_real_candle_shape_and_reports_cost_pnl_mdd():
    klines = []
    price = 100.0
    for index in range(140):
        price *= 1.001
        klines.append([index, price * 0.999, price * 1.01, price * 0.998, price, 1000 + index])
    rules = {
        "signal_mode": "independent",
        "entry_signal": "LONG",
        "entry": "MA20 above MA50",
        "stop_loss": "1%",
        "engine_settings": {"_unit": "percent_points", "tp_percent": 0.5, "sl_percent": 1.0},
        "executable_entry": {"all": [{"field": "current_price", "operator": "gt_field", "value_field": "ma50"}]},
    }
    metrics = run_historical_replay(rules, klines, fee_rate=0.001)
    assert metrics["decisions"] > 0
    assert metrics["wins"] > 0
    assert metrics["net_pnl_percent"] > 0
    assert metrics["max_drawdown_percent"] >= 0
    assert metrics["fee_rate_percent"] == 0.1


def test_historical_replay_accepts_stock_adapter_scalar_price_history():
    prices = []
    price = 50000.0
    for _index in range(140):
        price *= 1.001
        prices.append(price)
    rules = {
        "signal_mode": "independent",
        "entry_signal": "LONG",
        "engine_settings": {"_unit": "percent_points", "tp_percent": 0.5, "sl_percent": 1.0},
        "executable_entry": {
            "all": [{"field": "current_price", "operator": "gt_field", "value_field": "ma50"}],
        },
    }
    metrics = run_historical_replay(rules, prices, fee_rate=0.001)
    assert metrics["candles"] == 140
    assert metrics["decisions"] > 0
    assert metrics["net_pnl_percent"] > 0
