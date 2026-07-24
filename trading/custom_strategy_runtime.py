#!/usr/bin/env python3
"""AI 커스텀 전략의 저장 단위와 실제 주문 단위를 한 경계에서 통일한다."""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping


PERCENT_POINTS = "percent_points"
FRACTION = "fraction"
LIMITED_LIVE_MAX_POSITION_SIZE = 0.01


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def normalize_engine_settings(
    values: Mapping[str, Any] | None,
    *,
    max_leverage: int = 10,
    max_position_size: float = 0.5,
) -> Dict[str, Any]:
    """XAI 표시값(percent point)을 주문 엔진 fraction으로 변환하고 상한을 강제한다.

    저장/XAI: TP 2% = 2.0, SL 1% = 1.0
    주문 엔진: TP 2% = 0.02, SL 1% = 0.01
    """
    raw = dict(values or {})
    unit = str(raw.pop("_unit", raw.pop("unit", PERCENT_POINTS)) or PERCENT_POINTS).lower()
    result: Dict[str, Any] = {}
    if "leverage" in raw:
        result["leverage"] = max(1, min(int(_float(raw["leverage"], 1)), int(max_leverage)))
    if "position_size" in raw:
        result["position_size"] = max(0.01, min(_float(raw["position_size"], 0.01), max_position_size))
    if "signal_threshold" in raw:
        threshold = _float(raw["signal_threshold"], 0.0)
        result["signal_threshold"] = max(0.0, min(threshold / 100.0 if threshold > 1.0 else threshold, 1.0))
    for key in ("tp_percent", "sl_percent"):
        if key not in raw:
            continue
        rate = _float(raw[key], 0.0)
        if unit != FRACTION:
            rate /= 100.0
        result[key] = max(0.0005, min(rate, 0.50 if key == "tp_percent" else 0.20))
    result["_unit"] = FRACTION
    return result


def display_engine_settings(values: Mapping[str, Any] | None) -> Dict[str, Any]:
    """fraction 런타임 값을 XAI용 percent point로 되돌린다."""
    raw = dict(values or {})
    unit = str(raw.get("_unit", PERCENT_POINTS) or PERCENT_POINTS).lower()
    if unit != FRACTION:
        raw["_unit"] = PERCENT_POINTS
        return raw
    for key in ("tp_percent", "sl_percent"):
        if key in raw:
            raw[key] = round(_float(raw[key]) * 100.0, 8)
    raw["_unit"] = PERCENT_POINTS
    return raw


def limited_live_engine_settings(values: Mapping[str, Any] | None) -> Dict[str, Any]:
    """검증 미통과 전략의 사용자 선택형 최소단위 운용 상한을 강제한다."""
    result = normalize_engine_settings(values)
    result["leverage"] = 1
    result["position_size"] = min(
        max(0.01, _float(result.get("position_size"), LIMITED_LIVE_MAX_POSITION_SIZE)),
        LIMITED_LIVE_MAX_POSITION_SIZE,
    )
    result["_unit"] = FRACTION
    return result


def derive_strategy_risk_settings(
    values: Mapping[str, Any] | None,
    risk_model: Mapping[str, Any] | None,
    context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """사용자 위험예산과 전략 손절거리에서 거래별 레버리지·증거금 비중을 계산한다.

    사용자가 정하는 max_leverage는 목표 레버리지가 아니라 상한이다.
    위험모델이 없으면 기존의 명시적 엔진 설정을 그대로 보존한다.
    """
    result = normalize_engine_settings(values)
    model = dict(risk_model or {})
    if not model:
        return result
    risk_fraction = _float(model.get("risk_per_trade_percent"), 0.0) / 100.0
    margin_fraction = _float(model.get("max_margin_usage_percent"), 0.0) / 100.0
    max_leverage = max(1, int(_float(model.get("max_leverage"), result.get("leverage", 1))))
    max_notional = _float(model.get("max_notional_percent"), 100.0) / 100.0
    stop_fraction = _float(result.get("sl_percent"), 0.0)
    context_values = dict(context or {})
    if str(model.get("stop_mode", "") or "").lower() == "volatility":
        raw_volatility = abs(_float(
            context_values.get("market_volatility", context_values.get("volatility", 0.0)), 0.0
        ))
        volatility_fraction = raw_volatility / 100.0 if raw_volatility > 1.0 else raw_volatility
        stop_fraction = max(
            stop_fraction,
            volatility_fraction * max(0.1, _float(model.get("volatility_multiplier"), 1.0)),
        )
    if risk_fraction <= 0 or margin_fraction <= 0 or stop_fraction <= 0:
        result["_risk_derivation"] = {
            "applied": False,
            "reason": "risk_budget_margin_or_stop_missing",
        }
        return result
    notional_fraction = min(max_notional, risk_fraction / stop_fraction)
    leverage = max(1, min(max_leverage, int(math.ceil(notional_fraction / margin_fraction))))
    actual_notional = min(notional_fraction, margin_fraction * leverage)
    result["leverage"] = leverage
    result["position_size"] = min(0.5, max(0.01, actual_notional / leverage))
    result["_risk_derivation"] = {
        "applied": True,
        "risk_per_trade_percent": round(risk_fraction * 100.0, 6),
        "stop_distance_percent": round(stop_fraction * 100.0, 6),
        "target_notional_percent": round(actual_notional * 100.0, 6),
        "margin_usage_percent": round(result["position_size"] * 100.0, 6),
        "effective_leverage": leverage,
        "max_leverage": max_leverage,
    }
    return result


def apply_engine_settings_to_trade_config(
    trade_config: Mapping[str, Any] | None,
    runtime_settings: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    """선택 전략 설정을 Binance/CCXT 공통 거래 파라미터에 최종 오버레이한다."""
    result = dict(trade_config or {})
    selected = normalize_engine_settings(runtime_settings)
    if "leverage" in selected:
        result["leverage"] = selected["leverage"]
    if "tp_percent" in selected:
        result["tp_percent"] = selected["tp_percent"]
        result["tp"] = selected["tp_percent"]
    if "sl_percent" in selected:
        result["sl_percent"] = selected["sl_percent"]
        result["sl"] = selected["sl_percent"]
    if "position_size" in selected:
        result["position_size"] = selected["position_size"]
        result["position_size_factor"] = min(1.0, selected["position_size"] / 0.10)
        if isinstance(result.get("qty"), (int, float)):
            # 기존 리스크 엔진이 산출한 수량을 늘리지 않고 사용자 비중으로만 축소한다.
            result["qty"] = float(result["qty"]) * result["position_size_factor"]
    if "signal_threshold" in selected:
        result["signal_threshold"] = selected["signal_threshold"]
    result["_custom_strategy_applied"] = bool(runtime_settings)
    return result
