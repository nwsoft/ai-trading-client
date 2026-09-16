#!/usr/bin/env python3
"""AI 커스텀 전략의 저장 단위와 실제 주문 단위를 한 경계에서 통일한다."""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping


PERCENT_POINTS = "percent_points"
FRACTION = "fraction"
LIMITED_LIVE_MAX_POSITION_SIZE = 0.01
EXIT_RATE_UNIT_KEY = "_exit_rate_unit"
EXIT_RATE_SOURCE_KEY = "_exit_rate_source"
TP_FRACTION_MIN = 0.0005
TP_FRACTION_MAX = 0.05
SL_FRACTION_MIN = 0.0005
SL_FRACTION_MAX = 0.03
TP_PERCENT_POINTS_MIN = TP_FRACTION_MIN * 100.0
TP_PERCENT_POINTS_MAX = TP_FRACTION_MAX * 100.0
SL_PERCENT_POINTS_MIN = SL_FRACTION_MIN * 100.0
SL_PERCENT_POINTS_MAX = SL_FRACTION_MAX * 100.0


class ExitRateContractError(ValueError):
    """TP/SL 실행값의 단위·출처·별칭이 서로 모순될 때 발생한다."""


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def stamp_trade_exit_rates(
    values: Mapping[str, Any] | None,
    *,
    tp_fraction: Any,
    sl_fraction: Any,
    source: str,
) -> Dict[str, Any]:
    """검증된 fraction TP/SL을 모든 실행 별칭에 동일하게 기록한다.

    이 함수는 값의 크기로 percent point 여부를 추정하지 않는다. 호출자는
    저장/표시 경계에서 단위 변환을 끝낸 fraction만 전달해야 한다.
    """
    result = dict(values or {})
    try:
        tp = float(tp_fraction)
        sl = float(sl_fraction)
    except (TypeError, ValueError) as exc:
        raise ExitRateContractError("TP/SL 실행값은 숫자 fraction이어야 합니다.") from exc
    if not math.isfinite(tp) or not math.isfinite(sl):
        raise ExitRateContractError("TP/SL 실행값은 유한한 숫자여야 합니다.")
    if not (TP_FRACTION_MIN <= tp <= TP_FRACTION_MAX):
        raise ExitRateContractError(f"TP fraction 실행 범위 위반: {tp}")
    if not (SL_FRACTION_MIN <= sl <= SL_FRACTION_MAX):
        raise ExitRateContractError(f"SL fraction 실행 범위 위반: {sl}")
    normalized_source = str(source or "").strip()
    if not normalized_source:
        raise ExitRateContractError("TP/SL 실행값 출처가 없습니다.")
    result["tp"] = tp
    result["tp_percent"] = tp
    result["sl"] = sl
    result["sl_percent"] = sl
    result[EXIT_RATE_UNIT_KEY] = FRACTION
    result[EXIT_RATE_SOURCE_KEY] = normalized_source
    return result


def validate_trade_exit_rates(values: Mapping[str, Any] | None) -> tuple[float, float]:
    """주문 직전 TP/SL 단일 권위 계약을 검증하고 fraction 쌍을 반환한다."""
    raw = dict(values or {})
    if str(raw.get(EXIT_RATE_UNIT_KEY) or "").lower() != FRACTION:
        raise ExitRateContractError("TP/SL 실행 단위 표식이 없거나 fraction이 아닙니다.")
    if not str(raw.get(EXIT_RATE_SOURCE_KEY) or "").strip():
        raise ExitRateContractError("TP/SL 실행값 출처가 없습니다.")
    required = ("tp", "tp_percent", "sl", "sl_percent")
    missing = [key for key in required if raw.get(key) is None]
    if missing:
        raise ExitRateContractError("TP/SL 실행 필드 누락: " + ",".join(missing))
    try:
        tp = float(raw["tp"])
        tp_alias = float(raw["tp_percent"])
        sl = float(raw["sl"])
        sl_alias = float(raw["sl_percent"])
    except (TypeError, ValueError) as exc:
        raise ExitRateContractError("TP/SL 실행 필드가 숫자가 아닙니다.") from exc
    if not math.isclose(tp, tp_alias, rel_tol=0.0, abs_tol=1e-12):
        raise ExitRateContractError(f"TP 실행 필드 충돌: tp={tp}, tp_percent={tp_alias}")
    if not math.isclose(sl, sl_alias, rel_tol=0.0, abs_tol=1e-12):
        raise ExitRateContractError(f"SL 실행 필드 충돌: sl={sl}, sl_percent={sl_alias}")
    # 범위·유한성 검증을 한 곳에서 재사용한다.
    checked = stamp_trade_exit_rates({}, tp_fraction=tp, sl_fraction=sl, source="validation")
    return float(checked["tp"]), float(checked["sl"])


def require_explicit_stored_exit_unit(values: Mapping[str, Any] | None) -> None:
    """사용자 전략 저장값은 크기 추정 없이 명시 단위를 요구한다."""
    raw = dict(values or {})
    if not ({"tp_percent", "sl_percent"} & set(raw)):
        return
    unit = str(raw.get("_unit", raw.get("unit", "")) or "").strip().lower()
    if unit not in {PERCENT_POINTS, FRACTION}:
        raise ExitRateContractError(
            "저장된 AI 커스텀 TP/SL 단위가 없습니다. 전략을 다시 검토해 새 버전으로 저장하세요."
        )


def validate_stored_exit_rates(values: Mapping[str, Any] | None) -> tuple[float | None, float | None]:
    """저장·분석·PAPER·LIVE가 공유하는 TP/SL 단위와 범위를 검증한다.

    표시/저장값은 percent point 또는 fraction 중 하나를 명시해야 하며 값은
    보정하지 않는다. 호출자는 오류를 사용자 확인 사유로 노출해야 한다.
    """
    raw = dict(values or {})
    require_explicit_stored_exit_unit(raw)
    unit = str(raw.get("_unit", raw.get("unit", "")) or "").strip().lower()
    limits = {
        PERCENT_POINTS: {
            "tp_percent": (TP_PERCENT_POINTS_MIN, TP_PERCENT_POINTS_MAX),
            "sl_percent": (SL_PERCENT_POINTS_MIN, SL_PERCENT_POINTS_MAX),
        },
        FRACTION: {
            "tp_percent": (TP_FRACTION_MIN, TP_FRACTION_MAX),
            "sl_percent": (SL_FRACTION_MIN, SL_FRACTION_MAX),
        },
    }.get(unit)
    if limits is None and ({"tp_percent", "sl_percent"} & set(raw)):
        raise ExitRateContractError(f"지원하지 않는 TP/SL 저장 단위입니다: {unit or 'missing'}")
    checked: Dict[str, float | None] = {"tp_percent": None, "sl_percent": None}
    for field in ("tp_percent", "sl_percent"):
        if raw.get(field) is None:
            continue
        try:
            value = float(raw[field])
        except (TypeError, ValueError) as exc:
            raise ExitRateContractError(f"{field} 값은 숫자여야 합니다.") from exc
        if not math.isfinite(value):
            raise ExitRateContractError(f"{field} 값은 유한한 숫자여야 합니다.")
        minimum, maximum = limits[field]  # type: ignore[index]
        if not minimum <= value <= maximum:
            raise ExitRateContractError(
                f"{field}={value}는 승인 범위 {minimum}~{maximum} {unit} 밖입니다."
            )
        checked[field] = value
    return checked["tp_percent"], checked["sl_percent"]


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
    validate_stored_exit_rates(raw)
    unit = str(raw.pop("_unit", raw.pop("unit", PERCENT_POINTS)) or PERCENT_POINTS).lower()
    result: Dict[str, Any] = {}
    if "leverage" in raw:
        leverage = _float(raw["leverage"], math.nan)
        if not math.isfinite(leverage) or not leverage.is_integer() or not 1 <= leverage <= int(max_leverage):
            raise ExitRateContractError(f"leverage={raw['leverage']}는 승인 범위 1~{int(max_leverage)} 밖입니다.")
        result["leverage"] = int(leverage)
    if "position_size" in raw:
        position_size = _float(raw["position_size"], math.nan)
        if not math.isfinite(position_size) or not 0.01 <= position_size <= float(max_position_size):
            raise ExitRateContractError(
                f"position_size={raw['position_size']}는 승인 범위 0.01~{float(max_position_size)} 밖입니다."
            )
        result["position_size"] = position_size
    if "signal_threshold" in raw:
        threshold = _float(raw["signal_threshold"], math.nan)
        if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
            raise ExitRateContractError(
                f"signal_threshold={raw['signal_threshold']}는 승인 범위 0~1 밖입니다."
            )
        result["signal_threshold"] = threshold
    for key in ("tp_percent", "sl_percent"):
        if key not in raw:
            continue
        rate = _float(raw[key], 0.0)
        if unit != FRACTION:
            rate /= 100.0
        result[key] = rate
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
    selected_has_exit = "tp_percent" in selected or "sl_percent" in selected
    if selected_has_exit:
        tp = selected.get("tp_percent", result.get("tp"))
        sl = selected.get("sl_percent", result.get("sl"))
        result = stamp_trade_exit_rates(
            result,
            tp_fraction=tp,
            sl_fraction=sl,
            source="ai_custom_strategy",
        )
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
