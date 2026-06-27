#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from trading.stock_risk_governance import evaluate_stock_risk_governance


def test_governance_kill_switch_blocks():
    result = evaluate_stock_risk_governance(
        symbol="005930",
        signal="BUY",
        positions=[],
        recent_trades=[],
        daily_realized_pnl=0.0,
        policy={"risk_governance_enabled": True, "global_kill_switch": True},
    )
    assert result["allowed"] is False
    assert any("global_kill_switch" in x for x in result["reasons"])


def test_governance_weekly_monthly_limits_block():
    recent = [
        {"timestamp": "20990101010101", "pnl": -900000.0},
        {"timestamp": "20990102010101", "pnl": -900000.0},
        {"timestamp": "20990103010101", "pnl": -900000.0},
    ]
    result = evaluate_stock_risk_governance(
        symbol="005930",
        signal="BUY",
        positions=[],
        recent_trades=recent,
        daily_realized_pnl=-100000.0,
        policy={
            "risk_governance_enabled": True,
            "weekly_max_loss": 1_000_000.0,
            "monthly_max_loss": 2_000_000.0,
        },
    )
    assert result["allowed"] is False
    assert any("weekly_loss_limit" in x for x in result["reasons"])
    assert any("monthly_loss_limit" in x for x in result["reasons"])


def test_governance_concentration_blocks_on_buy():
    positions = [
        {"code": "005930", "eval_amount": 8000000},
        {"code": "000660", "eval_amount": 2000000},
    ]
    result = evaluate_stock_risk_governance(
        symbol="005930",
        signal="BUY",
        positions=positions,
        recent_trades=[],
        daily_realized_pnl=0.0,
        policy={
            "risk_governance_enabled": True,
            "max_symbol_weight_percent": 60.0,
        },
    )
    assert result["allowed"] is False
    assert any("symbol_concentration" in x for x in result["reasons"])


def test_governance_daily_loss_blocks():
    result = evaluate_stock_risk_governance(
        symbol="005930",
        signal="BUY",
        positions=[],
        recent_trades=[],
        daily_realized_pnl=-600000.0,
        policy={
            "risk_governance_enabled": True,
            "daily_max_loss": 500000.0,
        },
    )
    assert result["allowed"] is False
    assert any("daily_loss_limit" in x for x in result["reasons"])


def test_governance_daily_loss_allows_under_limit():
    result = evaluate_stock_risk_governance(
        symbol="005930",
        signal="BUY",
        positions=[],
        recent_trades=[],
        daily_realized_pnl=-100000.0,
        policy={
            "risk_governance_enabled": True,
            "daily_max_loss": 500000.0,
        },
    )
    assert result["allowed"] is True


def test_governance_broker_override_tighter_daily():
    """브로커 오버라이드가 글로벌 한도보다 타이트할 때 브로커 한도로 차단."""
    result = evaluate_stock_risk_governance(
        symbol="005930",
        signal="BUY",
        positions=[],
        recent_trades=[],
        daily_realized_pnl=-250000.0,
        policy={
            "risk_governance_enabled": True,
            "daily_max_loss": 500000.0,
            "broker_overrides": {
                "kiwoom": {"daily_max_loss": 200000.0},
            },
        },
        broker="kiwoom",
    )
    assert result["allowed"] is False
    assert any("daily_loss_limit" in x for x in result["reasons"])
    assert result["metrics"]["broker"] == "kiwoom"


def test_governance_broker_override_looser_daily():
    """브로커 오버라이드가 더 넓을 때 통과."""
    result = evaluate_stock_risk_governance(
        symbol="005930",
        signal="BUY",
        positions=[],
        recent_trades=[],
        daily_realized_pnl=-400000.0,
        policy={
            "risk_governance_enabled": True,
            "daily_max_loss": 300000.0,
            "broker_overrides": {
                "shinhan": {"daily_max_loss": 600000.0},
            },
        },
        broker="shinhan",
    )
    assert result["allowed"] is True


def test_governance_broker_not_in_override_uses_global():
    """오버라이드 없는 브로커는 글로벌 정책 사용."""
    result = evaluate_stock_risk_governance(
        symbol="005930",
        signal="BUY",
        positions=[],
        recent_trades=[],
        daily_realized_pnl=-600000.0,
        policy={
            "risk_governance_enabled": True,
            "daily_max_loss": 500000.0,
            "broker_overrides": {
                "kiwoom": {"daily_max_loss": 200000.0},
            },
        },
        broker="mirae",
    )
    assert result["allowed"] is False
    assert any("daily_loss_limit" in x for x in result["reasons"])
