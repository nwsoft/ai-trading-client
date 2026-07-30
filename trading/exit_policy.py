#!/usr/bin/env python3
"""모든 자산의 청산값을 한 단위와 세 계층으로 기록한다."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping


INTERNAL_UNIT = "fraction"


def _fraction(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    return parsed if parsed >= 0.0 else float(default)


def _insurance_prices(
    *,
    entry_price: float,
    side: str,
    tp_fraction: float,
    sl_fraction: float,
) -> tuple[float, float]:
    entry = _fraction(entry_price)
    if entry <= 0:
        return 0.0, 0.0
    is_long = str(side or "").strip().upper() in {"BUY", "LONG"}
    if is_long:
        return entry * (1.0 + tp_fraction), entry * (1.0 - sl_fraction)
    return entry * (1.0 - tp_fraction), entry * (1.0 + sl_fraction)


def build_exit_policy(
    *,
    settings: Mapping[str, Any] | None,
    exit_plan: Mapping[str, Any] | None,
    effective_tp_fraction: Any,
    effective_sl_fraction: Any,
    effective_reason: str,
    entry_price: Any = 0.0,
    side: str = "",
    asset_class: str = "crypto",
    target: str = "",
    symbol: str = "",
) -> Dict[str, Any]:
    """기본 폴백·현재 적용값·보험 주문값을 서로 덮어쓰지 않고 만든다."""

    cfg = dict(settings or {})
    intent = dict(exit_plan or {})
    fallback_tp = _fraction(cfg.get("default_tp", 0.0018), 0.0018)
    fallback_sl = _fraction(cfg.get("default_sl", 0.0020), 0.0020)
    effective_tp = _fraction(effective_tp_fraction, fallback_tp)
    effective_sl = _fraction(effective_sl_fraction, fallback_sl)
    requested_tp, requested_sl = _insurance_prices(
        entry_price=_fraction(entry_price),
        side=side,
        tp_fraction=effective_tp,
        sl_fraction=effective_sl,
    )
    strategy_owned = bool(intent.get("strategy_owned", False))
    source = str(intent.get("source") or "noah_dynamic")

    return {
        "schema_version": 1,
        "unit": INTERNAL_UNIT,
        "asset_class": str(asset_class or ""),
        "target": str(target or "").strip().lower(),
        "symbol": str(symbol or "").strip().upper(),
        "strategy_owned": strategy_owned,
        "fallback": {
            "tp_fraction": fallback_tp,
            "sl_fraction": fallback_sl,
            "source": "settings.default_tp/default_sl",
        },
        "effective": {
            "tp_fraction": effective_tp,
            "sl_fraction": effective_sl,
            "source": source if strategy_owned else "noah_dynamic",
            "reason": str(effective_reason or source),
        },
        "insurance": {
            "requested_tp_price": requested_tp,
            "requested_sl_price": requested_sl,
            "submitted_tp_price": 0.0,
            "submitted_sl_price": 0.0,
            "status": "pending" if requested_tp and requested_sl else "not_calculated",
            "order_ids": {},
        },
    }


def record_insurance_submission(
    policy: Mapping[str, Any] | None,
    *,
    submitted_tp_price: Any = 0.0,
    submitted_sl_price: Any = 0.0,
    status: str,
    order_ids: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    result = deepcopy(dict(policy or {}))
    insurance = dict(result.get("insurance") or {})
    insurance["submitted_tp_price"] = _fraction(submitted_tp_price)
    insurance["submitted_sl_price"] = _fraction(submitted_sl_price)
    insurance["status"] = str(status or "unknown")
    insurance["order_ids"] = dict(order_ids or {})
    result["insurance"] = insurance
    return result


def format_exit_policy(policy: Mapping[str, Any] | None) -> str:
    values = dict(policy or {})
    fallback = dict(values.get("fallback") or {})
    effective = dict(values.get("effective") or {})
    insurance = dict(values.get("insurance") or {})
    return (
        "청산정책[단위=fraction] "
        f"기본폴백 TP={_fraction(fallback.get('tp_fraction')):.6f} "
        f"SL={_fraction(fallback.get('sl_fraction')):.6f} | "
        f"현재적용 TP={_fraction(effective.get('tp_fraction')):.6f} "
        f"SL={_fraction(effective.get('sl_fraction')):.6f} "
        f"근거={effective.get('reason') or '-'} | "
        f"보험제출 TP={_fraction(insurance.get('submitted_tp_price')):.8f} "
        f"SL={_fraction(insurance.get('submitted_sl_price')):.8f} "
        f"상태={insurance.get('status') or '-'}"
    )
