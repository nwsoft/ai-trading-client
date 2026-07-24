from dataclasses import dataclass
from datetime import datetime, timezone

from trading.ai.inference_policy import OpportunityAwareInferencePolicy


@dataclass
class Candle:
    timestamp: datetime
    close: float


@dataclass
class Indicators:
    rsi: float = 50.0
    macd_histogram: float = 0.1
    bb_position: float = 0.5


@dataclass
class Trend:
    direction: str = "SIDEWAYS"


@dataclass
class MarketState:
    trend_data: Trend
    volatility: float = 0.01


def _decision(policy, *, close=100.0, rsi=50.0, signal="HOLD", candle_minute=0):
    return policy.decide(
        exchange="binance",
        symbol="BTCUSDT",
        market_data=[
            Candle(
                timestamp=datetime(2026, 7, 24, 0, candle_minute, tzinfo=timezone.utc),
                close=close,
            )
        ],
        indicators=Indicators(rsi=rsi),
        market_state=MarketState(trend_data=Trend()),
        basic_signal={"signal": signal},
    )


def test_same_market_state_reuses_cached_ai_result(tmp_path):
    clock = [1000.0]
    policy = OpportunityAwareInferencePolicy(
        {"ai_cost_control": {"max_daily_market_calls": 10}},
        state_path=str(tmp_path / "budget.json"),
        clock=lambda: clock[0],
    )

    first = _decision(policy)
    assert first["mode"] == "call"
    policy.store(
        exchange="binance",
        symbol="BTCUSDT",
        fingerprint=first["fingerprint"],
        analysis={"signal": "HOLD"},
    )

    clock[0] += 10
    second = _decision(policy)
    assert second["mode"] == "cache"
    assert second["analysis"]["signal"] == "HOLD"


def test_material_price_move_bypasses_same_candle_cache(tmp_path):
    clock = [1000.0]
    policy = OpportunityAwareInferencePolicy(
        {"ai_cost_control": {"price_change_bps": 15.0, "max_daily_market_calls": 10}},
        state_path=str(tmp_path / "budget.json"),
        clock=lambda: clock[0],
    )
    first = _decision(policy, close=100.0)
    policy.store(
        exchange="binance",
        symbol="BTCUSDT",
        fingerprint=first["fingerprint"],
        analysis={"signal": "HOLD"},
    )

    clock[0] += 10
    moved = _decision(policy, close=100.3)
    assert moved["mode"] == "call"
    assert "price_move" in moved["reason"]


def test_new_candle_and_local_trade_candidate_are_not_hidden(tmp_path):
    clock = [1000.0]
    policy = OpportunityAwareInferencePolicy(
        {"ai_cost_control": {"max_daily_market_calls": 10}},
        state_path=str(tmp_path / "budget.json"),
        clock=lambda: clock[0],
    )
    _decision(policy)

    clock[0] += 10
    new_candle = _decision(policy, candle_minute=1)
    assert new_candle["mode"] == "call"
    assert "new_candle" in new_candle["reason"]

    clock[0] += 10
    candidate = _decision(policy, signal="LONG", candle_minute=1)
    assert candidate["mode"] == "call"
    assert "local_trade_candidate" in candidate["reason"]


def test_budget_exhaustion_falls_back_to_local_signal_instead_of_stopping(tmp_path):
    clock = [1000.0]
    policy = OpportunityAwareInferencePolicy(
        {
            "ai_cost_control": {
                "max_daily_market_calls": 1,
                "max_daily_calls_per_exchange": 1,
                "max_monthly_market_calls": 1,
            }
        },
        state_path=str(tmp_path / "budget.json"),
        clock=lambda: clock[0],
    )
    assert _decision(policy)["mode"] == "call"

    clock[0] += 10
    fallback = _decision(policy, signal="LONG", close=101.0)
    assert fallback["mode"] == "local"
    assert fallback["reason"] in {
        "daily_budget",
        "monthly_budget",
        "exchange_daily_budget",
    }


def test_budget_counter_survives_restart(tmp_path):
    state_path = str(tmp_path / "budget.json")
    first = OpportunityAwareInferencePolicy(
        {"ai_cost_control": {"max_daily_market_calls": 1}},
        state_path=state_path,
        clock=lambda: 1000.0,
    )
    assert _decision(first)["mode"] == "call"

    second = OpportunityAwareInferencePolicy(
        {"ai_cost_control": {"max_daily_market_calls": 1}},
        state_path=state_path,
        clock=lambda: 1010.0,
    )
    decision = _decision(second, close=102.0)
    assert decision["mode"] == "local"
    assert decision["reason"] == "daily_budget"
