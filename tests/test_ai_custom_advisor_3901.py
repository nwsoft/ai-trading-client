from datetime import datetime
from types import SimpleNamespace

import pytest

from config.settings import _repair_trade_rate
from trading.ai.ai_manager import AIManager
from trading.custom_strategy_advisor import build_improvement_advice, build_strategy_guidance
from trading.custom_strategy_runtime import derive_strategy_risk_settings
from trading.declarative_strategy_engine import DeclarativeStrategyEngine
from trading.strategy_engine import StrategyEngine


REQUIRED = ("entry", "exit", "stop_loss", "take_profit", "position_size", "market_conditions")


def test_missing_strategy_conditions_return_plain_language_questions():
    guidance = build_strategy_guidance({"entry": "RSI 30 이하"}, REQUIRED)

    assert guidance["complete"] is False
    assert "stop_loss" in guidance["missing_conditions"]
    assert any(item["field"] == "stop_loss" and item["example"] for item in guidance["questions"])
    assert guidance["approval_note"].startswith("AI 권장값은 자동 적용하지")


def test_leverage_is_derived_from_risk_budget_stop_and_margin():
    result = derive_strategy_risk_settings(
        {
            "_unit": "percent_points",
            "tp_percent": 2.0,
            "sl_percent": 1.0,
        },
        {
            "risk_per_trade_percent": 0.5,
            "max_margin_usage_percent": 10,
            "max_leverage": 5,
        },
    )

    assert result["leverage"] == 5
    assert result["position_size"] == pytest.approx(0.10)
    assert result["_risk_derivation"]["target_notional_percent"] == pytest.approx(50.0)


def test_regime_transition_is_user_choice():
    base = {
        "id": "s1",
        "name": "상승장 전략",
        "target_scope": "exchange:binance",
        "market_regimes": ["bull"],
        "priority": 5,
        "engine_settings": {"_unit": "percent_points", "tp_percent": 2, "sl_percent": 1},
    }
    paused = DeclarativeStrategyEngine.evaluate_strategy_pool(
        [{**base, "rules": {"regime_transition": "pause"}}],
        {"signal": "LONG"},
        asset_class="crypto",
        target="binance",
        market_regime="bear",
    )
    delegated = DeclarativeStrategyEngine.evaluate_strategy_pool(
        [{**base, "rules": {"regime_transition": "delegate_to_noah"}}],
        {"signal": "LONG"},
        asset_class="crypto",
        target="binance",
        market_regime="bear",
    )

    assert paused["allowed"] is False
    assert paused["transition_action"] == "pause"
    assert delegated["allowed"] is True
    assert delegated["reason"] == "delegated_to_noah_outside_selected_regime"


def test_performance_advice_never_auto_applies():
    advice = build_improvement_advice(
        {"decisions": 12, "net_pnl_percent": -1.2, "profit_factor": 0.8}
    )

    assert advice["auto_applied"] is False
    assert {item["priority"] for item in advice["actions"]} >= {"순기대값 개선", "손익비 개선"}


def test_high_volatility_is_evaluated_unless_user_blocks_it():
    engine = StrategyEngine()
    common = {
        "symbol": "BTCUSDT",
        "analysis_result": {"score": 95, "momentum": 2.5},
        "runtime_state": {"last_trade_at::BTCUSDT": datetime(2000, 1, 1)},
    }
    allowed, _ = engine.should_trade(
        **common,
        policy={
            "enabled": True,
            "allow_regimes": ["trend", "range"],
            "high_vol_action": "evaluate",
            "consensus_threshold": 0.5,
            "cooldown_sec": 0,
        },
    )
    blocked, meta = engine.should_trade(
        **common,
        policy={
            "enabled": True,
            "allow_regimes": ["trend", "range"],
            "high_vol_action": "block",
            "consensus_threshold": 0.5,
            "cooldown_sec": 0,
        },
    )

    assert allowed is True
    assert blocked is False
    assert "regime_blocked:high_vol" in meta["reasons"]


def test_ai_market_prompt_uses_real_volume_ratio_and_fraction_rates():
    class FakeClient:
        def __init__(self):
            self.prompt = ""

        def chat_json(self, system, prompt, **kwargs):
            self.prompt = prompt
            return {
                "confidence": 0.8,
                "tp_percent": 0.2,
                "sl_percent": 0.1,
                "leverage": 3,
                "signal": "LONG",
            }

        def get_last_usage(self):
            return {}

    manager = AIManager(api_key="")
    fake = FakeClient()
    manager.client = fake
    manager.enabled = lambda: True
    rows = [
        SimpleNamespace(close=100.0),
        SimpleNamespace(close=101.0),
        SimpleNamespace(close=99.0),
    ]
    indicators = SimpleNamespace(rsi=40, macd=0.2, volume_ratio=1.7)

    result = manager.analyze_market_conditions("BTCUSDT", rows, indicators)

    assert "Volume Ratio vs moving average: 1.7" in fake.prompt
    assert "0.001 means 0.1%" in fake.prompt
    assert result["entry_confidence"] == pytest.approx(0.8)
    assert result["tp_percent"] == pytest.approx(0.002)
    assert result["sl_percent"] == pytest.approx(0.001)


def test_corrupt_or_percent_point_tp_sl_is_repaired():
    assert _repair_trade_rate(8307.9, 0.0018, 0.05) == (0.0018, True)
    normalized, changed = _repair_trade_rate(0.18, 0.0018, 0.05)
    assert changed is True
    assert normalized == pytest.approx(0.0018)
