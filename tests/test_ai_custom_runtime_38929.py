from trading.custom_strategy_runtime import (
    apply_engine_settings_to_trade_config,
    limited_live_engine_settings,
    normalize_engine_settings,
)
from trading.custom_strategy_validator import run_historical_replay
from trading.declarative_strategy_engine import DeclarativeStrategyEngine
from trading.trader import Position, PositionSide, Trader
from types import SimpleNamespace
from datetime import datetime, timezone


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


def test_historical_replay_supports_ema200_and_realistic_round_trip_costs():
    klines = []
    price = 100.0
    for index in range(280):
        price *= 1.001
        klines.append([index * 900_000, price, price * 1.002, price * 0.999, price, 1000 + index])
    rules = {
        "signal_mode": "independent",
        "entry_signal": "LONG",
        "engine_settings": {"_unit": "percent_points", "tp_percent": 1.0, "sl_percent": 1.0},
        "executable_entry": {
            "all": [{"field": "current_price", "operator": "gt_field", "value_field": "ema200"}],
        },
    }
    metrics = run_historical_replay(
        rules, klines, fee_rate=0.001, slippage_bps=2.0, spread_bps=1.0,
    )
    assert metrics["warmup_candles"] == 200
    assert metrics["decisions"] > 0
    assert metrics["round_trip_cost_percent"] == 0.25
    assert metrics["total_cost_percent"] > 0
    assert metrics["profit_factor"] != 0
    assert metrics["trades"]
    assert metrics["assumptions"]["position_model"] == "single_non_overlapping"


def test_historical_replay_applies_declarative_exit_and_rejects_unsupported_fields():
    prices = [100.0 * (1.001 ** index) for index in range(180)]
    rules = {
        "signal_mode": "independent",
        "entry_signal": "LONG",
        "engine_settings": {"_unit": "percent_points", "tp_percent": 10.0, "sl_percent": 10.0},
        "executable_entry": {
            "all": [{"field": "current_price", "operator": "gt_field", "value_field": "ma50"}],
        },
        "executable_exit": {
            "all": [{"field": "rsi", "operator": "gt", "value": 70}],
        },
    }
    metrics = run_historical_replay(rules, prices, fee_rate=0.0, slippage_bps=0.0, spread_bps=0.0)
    assert any(trade["exit_reason"] == "declarative_exit" for trade in metrics["trades"])

    invalid = {
        **rules,
        "executable_entry": {
            "all": [{"field": "secret_indicator", "operator": "gt", "value": 1}],
        },
    }
    try:
        run_historical_replay(invalid, prices)
        assert False, "unsupported field must fail closed"
    except ValueError as exc:
        assert "미지원 선언형 조건" in str(exc)

    missing_value = DeclarativeStrategyEngine.validate_rule_spec({
        "executable_entry": {"all": [{"field": "rsi", "operator": "lt"}]}
    })
    malformed_group = DeclarativeStrategyEngine.validate_rule_spec({
        "executable_entry": {"all": {"field": "rsi", "operator": "lt", "value": 30}}
    })
    assert missing_value["valid"] is False
    assert "missing_value" in missing_value["errors"][0]
    assert malformed_group["valid"] is False
    assert "invalid_group" in malformed_group["errors"][0]


def test_cross_operator_requires_previous_bar_and_detects_real_cross():
    rules = {
        "executable_entry": {
            "all": [{
                "field": "current_price",
                "operator": "crosses_above",
                "value_field": "ema20",
            }]
        }
    }
    crossed = DeclarativeStrategyEngine.evaluate_entry(
        rules,
        {
            "current_price": 101.0,
            "ema20": 100.0,
            "_previous": {"current_price": 99.0, "ema20": 100.0},
        },
    )
    already_above = DeclarativeStrategyEngine.evaluate_entry(
        rules,
        {
            "current_price": 102.0,
            "ema20": 100.0,
            "_previous": {"current_price": 101.0, "ema20": 100.0},
        },
    )
    assert crossed["allowed"] is True
    assert already_above["allowed"] is False


def test_binance_position_keeps_selected_custom_exit_rule_for_live_monitor():
    rows = [
        SimpleNamespace(
            timestamp=datetime.fromtimestamp(index * 300, tz=timezone.utc),
            open=100.0 + index,
            high=100.5 + index,
            low=99.5 + index,
            close=100.0 + index,
            volume=1000.0 + index,
        )
        for index in range(220)
    ]
    trader = object.__new__(Trader)
    trader.analyzer = SimpleNamespace(get_market_data=lambda _symbol: rows)
    trader.log_event = lambda *_args, **_kwargs: None
    trader.logger = SimpleNamespace(warning=lambda *_args, **_kwargs: None)
    position = Position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        entry_price=200.0,
        current_price=319.0,
        quantity=0.01,
        leverage=1,
        unrealized_pnl=0.0,
        unrealized_pnl_percent=0.0,
        entry_time=datetime.now(timezone.utc),
        custom_strategy_id="strategy-test",
        custom_strategy_name="RSI 청산",
        custom_strategy_rules={
            "executable_exit": {
                "all": [{"field": "rsi", "operator": "gt", "value": 70}],
            },
        },
    )
    assert trader._custom_strategy_exit_triggered(position) is True
