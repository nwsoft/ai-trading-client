#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""증권 자동매매 리스크 거버넌스 평가 엔진."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List


DEFAULT_STOCK_RISK_GOVERNANCE: Dict[str, Any] = {
    "risk_governance_enabled": True,
    "global_kill_switch": False,
    "daily_max_loss": 500_000.0,
    "weekly_max_loss": 1_500_000.0,
    "monthly_max_loss": 4_000_000.0,
    "max_symbol_weight_percent": 35.0,
    # 브로커별 개별 오버라이드: {"kiwoom": {"daily_max_loss": 300000.0}, ...}
    "broker_overrides": {},
}


def normalize_stock_risk_governance(policy: Dict[str, Any] | None) -> Dict[str, Any]:
    merged = dict(DEFAULT_STOCK_RISK_GOVERNANCE)
    if isinstance(policy, dict):
        merged.update(policy)

    merged["risk_governance_enabled"] = bool(merged.get("risk_governance_enabled", True))
    merged["global_kill_switch"] = bool(merged.get("global_kill_switch", False))

    for key, default in (
        ("daily_max_loss", 500_000.0),
        ("weekly_max_loss", 1_500_000.0),
        ("monthly_max_loss", 4_000_000.0),
        ("max_symbol_weight_percent", 35.0),
    ):
        try:
            merged[key] = float(merged.get(key, default) or default)
        except Exception:
            merged[key] = default
    return merged


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _parse_trade_time(raw_ts: Any) -> datetime | None:
    if raw_ts is None:
        return None
    text = str(raw_ts).strip()
    if not text:
        return None

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        pass

    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 14:
        try:
            return datetime.strptime(digits, "%Y%m%d%H%M%S")
        except Exception:
            return None
    if len(digits) == 8:
        try:
            return datetime.strptime(digits, "%Y%m%d")
        except Exception:
            return None
    return None


def _apply_broker_override(policy: Dict[str, Any], broker: str | None) -> Dict[str, Any]:
    """브로커별 오버라이드를 병합한 최종 policy 반환."""
    if not broker:
        return policy
    overrides = policy.get("broker_overrides", {})
    if not isinstance(overrides, dict):
        return policy
    broker_key = str(broker).strip().lower()
    broker_override = overrides.get(broker_key) or overrides.get(broker) or {}
    if not isinstance(broker_override, dict) or not broker_override:
        return policy
    merged = dict(policy)
    merged.update(broker_override)
    return merged


def evaluate_stock_risk_governance(
    *,
    symbol: str,
    signal: str,
    positions: List[Dict[str, Any]],
    recent_trades: List[Dict[str, Any]],
    daily_realized_pnl: float,
    policy: Dict[str, Any] | None = None,
    broker: str | None = None,
) -> Dict[str, Any]:
    normalized = normalize_stock_risk_governance(policy)
    # 브로커별 오버라이드 적용
    normalized = _apply_broker_override(normalized, broker)
    if not normalized.get("risk_governance_enabled", True):
        return {"allowed": True, "reasons": [], "metrics": {}, "policy_snapshot": normalized}

    reasons: List[str] = []
    now = datetime.now()

    if normalized.get("global_kill_switch", False):
        reasons.append("global_kill_switch_enabled")

    # 일별 손실 한도 검사 (daily_realized_pnl은 호출 측에서 당일 실현손익 합산 전달)
    daily_max_loss = max(0.0, float(normalized.get("daily_max_loss", 0.0) or 0.0))
    if daily_max_loss > 0 and float(daily_realized_pnl) <= -daily_max_loss:
        reasons.append(f"daily_loss_limit:{float(daily_realized_pnl):.0f} <= -{daily_max_loss:.0f}")

    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    weekly_realized = 0.0
    monthly_realized = 0.0
    for trade in recent_trades or []:
        pnl = _to_float(trade.get("pnl", trade.get("realized_pnl", trade.get("profit", 0.0))), default=0.0)
        ts = _parse_trade_time(
            trade.get("timestamp") or trade.get("filled_at") or trade.get("time") or trade.get("order_time")
        )
        if ts is None:
            continue
        if ts >= week_start:
            weekly_realized += pnl
        if ts >= month_start:
            monthly_realized += pnl

    weekly_max_loss = max(0.0, float(normalized.get("weekly_max_loss", 0.0) or 0.0))
    monthly_max_loss = max(0.0, float(normalized.get("monthly_max_loss", 0.0) or 0.0))

    if weekly_max_loss > 0 and weekly_realized <= -weekly_max_loss:
        reasons.append(f"weekly_loss_limit:{weekly_realized:.0f} <= -{weekly_max_loss:.0f}")
    if monthly_max_loss > 0 and monthly_realized <= -monthly_max_loss:
        reasons.append(f"monthly_loss_limit:{monthly_realized:.0f} <= -{monthly_max_loss:.0f}")

    # 집중도 제한은 신규 진입(BUY)일 때만 평가
    symbol_weight_percent = 0.0
    if str(signal or "").upper() == "BUY":
        total_eval = 0.0
        target_eval = 0.0
        target_symbol = str(symbol or "").strip().upper()
        for pos in positions or []:
            pos_symbol = str(pos.get("code") or pos.get("symbol") or "").strip().upper()
            eval_amount = _to_float(pos.get("eval_amount"), default=0.0)
            if eval_amount <= 0:
                qty = _to_float(pos.get("quantity"), default=0.0)
                cur = _to_float(pos.get("current_price"), default=0.0)
                eval_amount = qty * cur
            if eval_amount <= 0:
                continue
            total_eval += eval_amount
            if pos_symbol == target_symbol:
                target_eval += eval_amount

        if total_eval > 0:
            symbol_weight_percent = (target_eval / total_eval) * 100.0
            max_symbol_weight_percent = max(0.0, float(normalized.get("max_symbol_weight_percent", 0.0) or 0.0))
            if max_symbol_weight_percent > 0 and symbol_weight_percent >= max_symbol_weight_percent:
                reasons.append(
                    f"symbol_concentration:{symbol_weight_percent:.1f}% >= {max_symbol_weight_percent:.1f}%"
                )

    metrics = {
        "daily_realized_pnl": float(daily_realized_pnl),
        "weekly_realized_pnl": weekly_realized,
        "monthly_realized_pnl": monthly_realized,
        "symbol_weight_percent": symbol_weight_percent,
        "broker": broker or "",
    }
    return {
        "allowed": len(reasons) == 0,
        "reasons": reasons,
        "metrics": metrics,
        "policy_snapshot": normalized,
    }
