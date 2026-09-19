from __future__ import annotations

import logging

import pytest

from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.noah_strategy_ir import NoahStrategyIR
from trading.trader import Trader


class _SymbolClient:
    def get_symbol_info_direct(self, _symbol: str):
        # BinanceClient의 실제 camelCase 반환 계약을 사용한다.
        return {
            "stepSize": 0.01,
            "quantityPrecision": 2,
            "minQty": 0.01,
            "minNotional": 5.0,
        }


def _trader_for_quantity() -> Trader:
    trader = object.__new__(Trader)
    trader.settings = {"min_trade_amount": 20.0}
    trader.binance_client = _SymbolClient()
    trader.logger = logging.getLogger("v39115-order-contract")
    trader.log_event = lambda *_args, **_kwargs: None
    return trader


def _complete_rules() -> dict:
    return {
        "entry": "RSI 30 이하 LONG",
        "exit": "RSI 55 이상 청산",
        "stop_loss": "1%",
        "take_profit": "2%",
        "position_size": "5%",
        "market_conditions": "횟보장",
        "signal_mode": "independent",
        "entry_signal": "LONG",
        "executable_entry": {
            "all": [{"field": "rsi", "operator": "lte", "value": 30}]
        },
        "executable_exit": {
            "all": [{"field": "rsi", "operator": "gte", "value": 55}]
        },
    }


def test_risk_scaled_target_uses_exchange_minimum_not_configured_target():
    trader = _trader_for_quantity()

    quantity, price, constraints = trader._compute_quantity_once(
        "AVAXUSDT", "BUY", 1, 10.0, risk_multiplier=0.10
    )

    assert price == 10.0
    assert quantity == pytest.approx(0.51)
    assert quantity * price == pytest.approx(5.10)
    assert constraints["configured_target_notional"] == 20.0
    assert constraints["exchange_min_notional"] == 5.0

    final = Trader._reconcile_authorized_quantity(
        computed_quantity=quantity,
        opportunity_factor=1.0,
        authorized_quantity_cap=2.0,
        reference_price=price,
        exchange_min_notional=constraints["exchange_min_notional"],
        step_size=constraints["step_size"],
        quantity_precision=constraints["quantity_precision"],
    )
    assert final["allowed"] is True
    assert final["notional"] == pytest.approx(5.10)


def test_split_authorization_is_not_applied_twice_and_never_raises_cap():
    allowed = Trader._reconcile_authorized_quantity(
        computed_quantity=0.51,
        opportunity_factor=0.5,
        authorized_quantity_cap=1.0,  # factor가 이미 반영된 coordinator 상한
        reference_price=10.0,
        exchange_min_notional=5.0,
        step_size=0.01,
        quantity_precision=2,
    )
    assert allowed["quantity"] == pytest.approx(0.51)
    assert allowed["allowed"] is True

    blocked = Trader._reconcile_authorized_quantity(
        computed_quantity=0.51,
        opportunity_factor=0.5,
        authorized_quantity_cap=0.40,
        reference_price=10.0,
        exchange_min_notional=5.0,
        step_size=0.01,
        quantity_precision=2,
    )
    assert blocked["quantity"] == pytest.approx(0.40)
    assert blocked["allowed"] is False
    assert "거래소 최소 주문" in blocked["reason"]

    zero_cap = Trader._reconcile_authorized_quantity(
        computed_quantity=0.51,
        opportunity_factor=1.0,
        authorized_quantity_cap=0.0,
        reference_price=10.0,
        exchange_min_notional=5.0,
        step_size=0.01,
        quantity_precision=2,
    )
    assert zero_cap["quantity"] == 0.0
    assert zero_cap["allowed"] is False


def test_level4_policy_normalizes_legacy_webui_fields(tmp_path):
    rules = _complete_rules()
    rules["risk_budget"] = {
        "risk_per_trade_percent": 0.5,
        "max_margin_percent": 10,
        "leverage_cap": 3,
    }
    rules["risk_policy_preset"] = "standard"
    pipeline = CustomStrategyPipeline(storage_path=str(tmp_path / "strategies.json"))

    version = pipeline.submit(name="Level 4 test", rules=rules)

    stored = version["rules"]
    assert "risk_budget" not in stored
    assert stored["risk_model"] == {
        "risk_per_trade_percent": 0.5,
        "max_margin_usage_percent": 10.0,
        "max_leverage": 3,
    }
    projection = NoahStrategyIR.project(version["strategy_ir"], 4)
    assert projection["level"] == 4
    assert projection["expert_operation_policy"]["risk_policy_preset"] == "standard"
    assert "daily_loss_stop" in projection["expert_operation_policy"]["immutable_guardrails"]


def test_level4_cannot_disable_hard_guardrails(tmp_path):
    rules = _complete_rules()
    rules["risk_model"] = {
        "risk_per_trade_percent": 0.5,
        "max_margin_usage_percent": 10,
        "max_leverage": 3,
        "disable_daily_loss_stop": True,
    }
    pipeline = CustomStrategyPipeline(storage_path=str(tmp_path / "strategies.json"))

    with pytest.raises(ValueError, match="하드 가드레일 해제"):
        pipeline.submit(name="unsafe", rules=rules)


def test_level4_cannot_hide_guardrail_disable_inside_nested_rules(tmp_path):
    rules = _complete_rules()
    rules["advanced"] = {"execution": [{"disable_emergency_stop": True}]}
    pipeline = CustomStrategyPipeline(storage_path=str(tmp_path / "strategies.json"))

    with pytest.raises(ValueError, match="하드 가드레일 해제"):
        pipeline.submit(name="nested-unsafe", rules=rules)
