from trading.trade_candidate import apply_trade_candidate, evaluate_trade_candidate


def _strategy(*, mode: str, signal: str = "LONG"):
    return {
        "id": f"{mode}-id",
        "strategy_key": f"{mode}-key",
        "version_id": f"{mode}-v1",
        "name": f"{mode}-strategy",
        "priority": 9,
        "target_scope": "exchange:binance",
        "market_regimes": ["range"],
        "signal_mode": mode,
        "entry_signal": signal,
        "engine_settings": {
            "_unit": "fraction",
            "tp_percent": 0.02,
            "sl_percent": 0.01,
            "position_size": 0.05,
        },
        "rules": {
            "signal_mode": mode,
            "entry_signal": signal,
            "executable_entry": {
                "all": [{"field": "rsi", "operator": "lt", "value": 40}],
            },
            "executable_exit": {
                "all": [{"field": "rsi", "operator": "gt", "value": 70}],
            },
        },
    }


def test_confirm_never_turns_base_hold_into_entry():
    candidate = evaluate_trade_candidate(
        symbol="BTCUSDT",
        context={"signal": "HOLD", "rsi": 30},
        strategy_pool=[_strategy(mode="confirm")],
        asset_class="crypto",
        target="binance",
        market_regime="range",
    )
    assert candidate.final_signal == "HOLD"
    assert candidate.signal_source == "noah_base"
    assert candidate.requires_noah_strategy_policy is True


def test_independent_preserves_strategy_signal_settings_and_version():
    candidate = evaluate_trade_candidate(
        symbol="BTCUSDT",
        context={"signal": "HOLD", "rsi": 30},
        strategy_pool=[_strategy(mode="independent")],
        asset_class="crypto",
        target="binance",
        market_regime="range",
    )
    assert candidate.final_signal == "LONG"
    assert candidate.signal_source == "custom_independent"
    assert candidate.requires_noah_strategy_policy is False
    assert candidate.strategy_key == "independent-key"
    assert candidate.strategy_version_id == "independent-v1"
    assert candidate.engine_settings["tp_percent"] == 0.02
    assert candidate.engine_settings["sl_percent"] == 0.01
    assert candidate.exit_plan.strategy_owned is True
    assert candidate.exit_plan.insurance_order_policy == "strategy_exact"
    assert candidate.exit_plan.allow_noah_dynamic_adjustment is False

    applied = apply_trade_candidate({"signal": "HOLD", "rsi": 30}, candidate)
    assert applied["signal"] == "LONG"
    assert applied["_custom_signal_mode"] == "independent"
    assert applied["_selected_custom_strategy_version_id"] == "independent-v1"
    assert applied["_custom_strategy_rules"]["executable_exit"]
    assert applied["_exit_plan"]["requested_tp_fraction"] == 0.02


def test_custom_condition_failure_becomes_explicit_hold():
    candidate = evaluate_trade_candidate(
        symbol="BTCUSDT",
        context={"signal": "LONG", "rsi": 60},
        strategy_pool=[_strategy(mode="confirm")],
        asset_class="crypto",
        target="binance",
        market_regime="range",
    )
    assert candidate.allowed is False
    assert candidate.final_signal == "HOLD"
    assert candidate.signal_source == "custom_blocked"


def test_no_pool_preserves_base_candidate_without_custom_metadata():
    candidate = evaluate_trade_candidate(
        symbol="005930",
        context={"signal": "BUY"},
        strategy_pool=[],
        asset_class="stock",
        target="kis",
        market_regime="bull",
    )
    assert candidate.final_signal == "LONG"
    assert candidate.signal_source == "noah_base"
    assert candidate.custom_evaluated is False


def test_active_pool_is_evaluated_exactly_once_per_candidate(monkeypatch):
    from trading.declarative_strategy_engine import DeclarativeStrategyEngine

    calls = []
    original = DeclarativeStrategyEngine.evaluate_strategy_pool.__func__

    def counted(cls, *args, **kwargs):
        calls.append((args, kwargs))
        return original(cls, *args, **kwargs)

    monkeypatch.setattr(
        DeclarativeStrategyEngine,
        "evaluate_strategy_pool",
        classmethod(counted),
    )

    candidate = evaluate_trade_candidate(
        symbol="BTCUSDT",
        context={"signal": "LONG", "rsi": 30},
        strategy_pool=[_strategy(mode="confirm")],
        asset_class="crypto",
        target="binance",
        market_regime="range",
    )

    assert candidate.allowed is True
    assert len(calls) == 1


def test_declared_regime_and_performance_adjustments_are_candidate_local():
    strategy = _strategy(mode="independent")
    strategy["market_regimes"] = ["bull"]
    strategy["rules"]["regime_parameters"] = {
        "bull": {
            "_unit": "percent_points",
            "tp_percent": 3.0,
        }
    }
    strategy["rules"]["performance_adjustments"] = [
        {
            "when": {"consecutive_losses_gte": 2},
            "set": {
                "_unit": "fraction",
                "position_size": 0.02,
                "sl_percent": 0.015,
            },
        }
    ]

    candidate = evaluate_trade_candidate(
        symbol="BTCUSDT",
        context={
            "signal": "HOLD",
            "rsi": 30,
            "_strategy_performance": {
                "consecutive_losses": 3,
                "recent_win_rate": 0.3,
            },
        },
        strategy_pool=[strategy],
        asset_class="crypto",
        target="binance",
        market_regime="bull",
    )

    assert candidate.engine_settings["tp_percent"] == 0.03
    assert candidate.engine_settings["sl_percent"] == 0.015
    assert candidate.engine_settings["position_size"] == 0.02
    # 원본 활성 풀은 다른 후보·거래소가 재사용하므로 절대 변경하지 않는다.
    assert strategy["engine_settings"]["tp_percent"] == 0.02
    assert strategy["engine_settings"]["sl_percent"] == 0.01
    assert strategy["engine_settings"]["position_size"] == 0.05


def test_ai_early_exit_compares_fraction_settings_to_percent_point_pnl():
    from datetime import datetime, timezone

    from trading.trader import Position, PositionSide, Trader

    trader = Trader.__new__(Trader)
    trader.settings = {
        "ai_exit_settings": {
            "min_profit_for_exit": 0.0020,
            "max_profit_for_exit": 0.0030,
            "min_loss_for_exit": -0.01,
            "max_loss_for_exit": -0.0005,
        }
    }
    trader.price_data_points = {}
    position = Position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        entry_price=100.0,
        current_price=100.25,
        quantity=1.0,
        leverage=1,
        unrealized_pnl=0.25,
        unrealized_pnl_percent=0.25,
        entry_time=datetime.now(timezone.utc),
    )

    decision = trader._check_ai_early_exit(position, holding_time=3.0)

    assert decision["should_exit"] is True
    assert "quick profit" in decision["reason"]
