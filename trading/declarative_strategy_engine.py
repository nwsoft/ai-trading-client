#!/usr/bin/env python3
"""AI 커스텀 전략의 제한된 선언형 조건을 안전하게 평가한다."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple


class DeclarativeStrategyEngine:
    ALLOWED_INDICATORS = {"sma", "ema", "rsi", "atr", "volume_sma"}
    ALLOWED_TIMEFRAMES = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}
    ALLOWED_SOURCES = {"open", "high", "low", "close", "volume"}
    ALLOWED_FIELDS = {
        "signal", "confidence",
        "open", "high", "low", "close", "current_price", "price",
        "rsi", "macd", "macd_signal", "macd_histogram",
        "bb_position", "bb_width",
        "ma20", "ma50", "ma200", "sma20", "sma50", "sma200",
        "ema20", "ema50", "ema200",
        "adx", "atr", "atr_percent",
        "trend_strength", "market_volatility",
        "volume", "volume_sma20", "volume_ratio",
        "hour", "weekday",
    }
    OPERATORS = {
        "eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in",
        "gt_field", "lt_field", "crosses_above", "crosses_below",
    }
    REGIME_ALIASES = {
        "BULL": "bull", "BULLISH": "bull", "UPTREND": "bull", "TREND": "trend",
        "BEAR": "bear", "BEARISH": "bear", "DOWNTREND": "bear",
        "SIDEWAYS": "range", "RANGE": "range", "NORMAL": "range",
        "VOLATILE": "volatile", "HIGH_VOLATILITY": "volatile",
        "CALM": "calm", "LOW_VOLATILITY": "calm",
    }

    @staticmethod
    def _number(value: Any) -> Any:
        try:
            number = float(value)
            return number if math.isfinite(number) else value
        except Exception:
            return value

    @classmethod
    def indicator_field_key(cls, reference: Any) -> str:
        if not isinstance(reference, dict):
            return str(reference or "").strip()
        name = str(reference.get("indicator") or reference.get("name") or "").strip().lower()
        timeframe = str(reference.get("timeframe") or "5m").strip().lower()
        source = str(reference.get("source") or ("volume" if name == "volume_sma" else "close")).strip().lower()
        try:
            period = int(reference.get("period"))
        except Exception:
            period = 0
        return f"custom_{name}_{period}_{timeframe}_{source}"

    @classmethod
    def validate_indicator_reference(cls, reference: Any) -> Tuple[bool, str]:
        if not isinstance(reference, dict):
            return False, "invalid_indicator_reference"
        name = str(reference.get("indicator") or reference.get("name") or "").strip().lower()
        timeframe = str(reference.get("timeframe") or "5m").strip().lower()
        source = str(reference.get("source") or ("volume" if name == "volume_sma" else "close")).strip().lower()
        try:
            period = int(reference.get("period"))
        except Exception:
            return False, "invalid_indicator_period"
        if name not in cls.ALLOWED_INDICATORS:
            return False, f"unsupported_indicator:{name}"
        if timeframe not in cls.ALLOWED_TIMEFRAMES:
            return False, f"unsupported_timeframe:{timeframe}"
        if source not in cls.ALLOWED_SOURCES:
            return False, f"unsupported_indicator_source:{source}"
        if not 2 <= period <= 500:
            return False, f"indicator_period_out_of_range:{period}"
        if name == "atr" and source not in {"close", "high", "low"}:
            return False, f"invalid_atr_source:{source}"
        return True, "supported"

    @classmethod
    def _field_key(cls, reference: Any) -> Tuple[str, str]:
        if isinstance(reference, dict):
            valid, reason = cls.validate_indicator_reference(reference)
            return (cls.indicator_field_key(reference), "supported") if valid else ("", reason)
        field = str(reference or "").strip()
        if field not in cls.ALLOWED_FIELDS:
            return "", f"unsupported_field:{field}"
        return field, "supported"

    @classmethod
    def validate_condition_spec(cls, condition: Dict[str, Any]) -> Tuple[bool, str]:
        field, field_reason = cls._field_key(condition.get("field"))
        operator = str(condition.get("operator") or "").strip().lower()
        if not field:
            return False, field_reason
        if operator not in cls.OPERATORS:
            return False, f"unsupported_operator:{operator}"
        if operator in {"gt_field", "lt_field", "crosses_above", "crosses_below"}:
            raw_value_field = condition.get("value_field", condition.get("value"))
            value_field, value_reason = cls._field_key(raw_value_field)
            if not value_field:
                return False, f"unsupported_value_field:{value_reason}"
        elif "value" not in condition or condition.get("value") is None:
            return False, f"missing_value:{field}/{operator}"
        elif operator in {"in", "not_in"} and not isinstance(
            condition.get("value"), (list, tuple, set)
        ):
            return False, f"invalid_collection:{field}/{operator}"
        return True, "supported"

    @classmethod
    def validate_rule_spec(cls, rules: Dict[str, Any]) -> Dict[str, Any]:
        """저장 전에 미지원 선언형 조건을 찾아 조용히 무시되는 일을 막는다."""
        errors: List[str] = []
        for section in ("executable_entry", "executable_exit"):
            raw_spec = (rules or {}).get(section, {}) or {}
            if not isinstance(raw_spec, dict):
                errors.append(f"{section}:invalid_spec")
                continue
            spec = dict(raw_spec)
            for group in ("all", "any"):
                raw_conditions = spec.get(group) or []
                if not isinstance(raw_conditions, list):
                    errors.append(f"{section}.{group}:invalid_group")
                    continue
                for index, condition in enumerate(raw_conditions):
                    if not isinstance(condition, dict):
                        errors.append(f"{section}.{group}[{index}]:invalid_condition")
                        continue
                    supported, reason = cls.validate_condition_spec(condition)
                    if not supported:
                        errors.append(f"{section}.{group}[{index}]:{reason}")
        return {"valid": not errors, "errors": errors}

    @classmethod
    def _condition(cls, condition: Dict[str, Any], context: Dict[str, Any]) -> Tuple[bool, str]:
        field, _field_reason = cls._field_key(condition.get("field"))
        operator = str(condition.get("operator") or "").strip().lower()
        supported, reason = cls.validate_condition_spec(condition)
        if not supported:
            return False, reason
        actual = context.get(field)
        if actual is None and field == "current_price":
            actual = context.get("price")
        if actual is None and field == "close":
            actual = context.get("current_price", context.get("price"))
        expected = condition.get("value")
        value_field = ""
        if operator in {"gt_field", "lt_field", "crosses_above", "crosses_below"}:
            value_field, value_reason = cls._field_key(
                condition.get("value_field", expected)
            )
            if not value_field:
                return False, f"unsupported_value_field:{value_reason}"
            expected = context.get(value_field)
        if actual is None or expected is None:
            return False, f"missing:{field}"
        left = cls._number(actual)
        right = cls._number(expected)
        if isinstance(left, float) and not math.isfinite(left):
            return False, f"missing:{field}"
        if isinstance(right, float) and not math.isfinite(right):
            return False, f"missing:{field}"
        try:
            if operator in {"crosses_above", "crosses_below"}:
                previous = context.get("_previous")
                if not isinstance(previous, dict):
                    return False, "missing:previous_context"
                previous_actual = previous.get(field)
                if previous_actual is None and field == "current_price":
                    previous_actual = previous.get("price")
                if previous_actual is None and field == "close":
                    previous_actual = previous.get("current_price", previous.get("price"))
                previous_expected = previous.get(value_field)
                if previous_actual is None or previous_expected is None:
                    return False, f"missing:previous_{field}/{value_field}"
                previous_left = cls._number(previous_actual)
                previous_right = cls._number(previous_expected)
                passed = (
                    previous_left <= previous_right and left > right
                    if operator == "crosses_above"
                    else previous_left >= previous_right and left < right
                )
                return bool(passed), (
                    f"{field} {operator} {value_field} "
                    f"(prev={previous_actual}/{previous_expected}, now={actual}/{expected})"
                )
            passed = {
                "eq": lambda: str(left).upper() == str(right).upper(),
                "ne": lambda: str(left).upper() != str(right).upper(),
                "gt": lambda: left > right,
                "gte": lambda: left >= right,
                "lt": lambda: left < right,
                "lte": lambda: left <= right,
                "in": lambda: left in right,
                "not_in": lambda: left not in right,
                "gt_field": lambda: left > right,
                "lt_field": lambda: left < right,
            }[operator]()
            return bool(passed), f"{field}={actual} {operator} {expected}"
        except Exception:
            return False, f"invalid:{field}/{operator}"

    @classmethod
    def evaluate_entry(cls, rules: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        return cls._evaluate_spec(
            rules, context, section="executable_entry",
            empty_reason="no_declarative_entry", empty_allowed=True,
        )

    @classmethod
    def evaluate_exit(cls, rules: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """명시적 청산 규칙을 평가한다. 코인 런타임과 과거재생이 이 계약을 공유한다."""
        return cls._evaluate_spec(
            rules, context, section="executable_exit",
            empty_reason="no_declarative_exit", empty_allowed=False,
        )

    @classmethod
    def _evaluate_spec(
        cls,
        rules: Dict[str, Any],
        context: Dict[str, Any],
        *,
        section: str,
        empty_reason: str,
        empty_allowed: bool,
    ) -> Dict[str, Any]:
        spec = dict((rules or {}).get(section, {}) or {})
        if not spec:
            return {"allowed": empty_allowed, "bypassed": True, "reason": empty_reason}
        all_conditions = [item for item in (spec.get("all") or []) if isinstance(item, dict)]
        any_conditions = [item for item in (spec.get("any") or []) if isinstance(item, dict)]
        if not all_conditions and not any_conditions:
            return {"allowed": empty_allowed, "bypassed": True, "reason": empty_reason}
        all_results = [cls._condition(item, context) for item in all_conditions]
        any_results = [cls._condition(item, context) for item in any_conditions]
        all_pass = all(result[0] for result in all_results) if all_results else True
        any_pass = any(result[0] for result in any_results) if any_results else True
        allowed = all_pass and any_pass
        return {
            "allowed": allowed,
            "bypassed": False,
            "all": all_results,
            "any": any_results,
            "reason": (
                ("custom_entry_passed" if allowed else "custom_entry_not_met")
                if section == "executable_entry"
                else ("custom_exit_passed" if allowed else "custom_exit_not_met")
            ),
        }

    @classmethod
    def _scope_matches(cls, scope: str, *, asset_class: str, target: str) -> bool:
        normalized = str(scope or "asset:crypto").strip().lower()
        asset = str(asset_class or "").strip().lower()
        current = str(target or "").strip().lower()
        if normalized == "asset:all":
            return True
        if normalized == f"asset:{asset}":
            return True
        if normalized.startswith("exchange:"):
            return asset == "crypto" and normalized.split(":", 1)[1] == current
        if normalized.startswith("broker:"):
            return asset == "stock" and normalized.split(":", 1)[1] == current
        return False

    @classmethod
    def evaluate_strategy_pool(
        cls,
        strategies: List[Dict[str, Any]],
        context: Dict[str, Any],
        *,
        asset_class: str,
        target: str,
        market_regime: str = "range",
    ) -> Dict[str, Any]:
        """최대 10개 활성 전략 중 범위·국면·모드·진입조건이 맞는 한 전략을 선택한다."""
        if not strategies:
            return {"allowed": True, "bypassed": True, "reason": "no_active_strategy_pool"}
        from .selection_policy import (
            normalize_regime_scope,
            resolve_effective_market_regime,
            resolve_market_regimes,
        )

        regimes_context = resolve_market_regimes(context, market_regime)
        candidates = sorted(
            [item for item in strategies if isinstance(item, dict)],
            key=lambda item: int(item.get("priority", 5) or 5),
            reverse=True,
        )[:10]
        evaluated = []
        scoped = []
        eligible_modes = {
            str(value or "").strip().lower()
            for value in (context.get("_eligible_strategy_modes") or [])
            if str(value or "").strip()
        }
        eligible_strategy_ids = {
            str(value or "").strip()
            for value in (context.get("_eligible_strategy_ids") or [])
            if str(value or "").strip()
        }
        for item in candidates:
            if not cls._scope_matches(item.get("target_scope", ""), asset_class=asset_class, target=target):
                continue
            rules = dict(item.get("rules") or {})
            signal_mode = str(item.get("signal_mode") or rules.get("signal_mode") or "confirm").lower()
            strategy_identity = str(
                item.get("version_id")
                or item.get("id")
                or item.get("strategy_key")
                or ""
            )
            if eligible_modes and signal_mode not in eligible_modes:
                continue
            if (
                eligible_strategy_ids
                and signal_mode == "independent"
                and strategy_identity
                and strategy_identity not in eligible_strategy_ids
            ):
                continue
            scoped.append(item)
            allowed_regimes = [
                str(value).strip().lower()
                for value in (item.get("market_regimes") or rules.get("market_regimes") or ["all"])
            ]
            regime_scope = normalize_regime_scope(
                item.get("regime_scope") or rules.get("regime_scope") or "market"
            )
            effective_regime, regime_source = resolve_effective_market_regime(
                context,
                market_regime,
                regime_scope,
            )
            market_value = regimes_context["market"]
            symbol_value = regimes_context["symbol"] or market_value
            if regime_scope == "none" or "all" in allowed_regimes:
                regime_matches = True
            elif regime_scope == "both":
                regime_matches = (
                    market_value in allowed_regimes
                    and symbol_value in allowed_regimes
                )
            elif regime_scope == "symbol":
                regime_matches = symbol_value in allowed_regimes
            else:
                regime_matches = market_value in allowed_regimes
            if not regime_matches:
                continue
            entry_signal = str(item.get("entry_signal") or rules.get("entry_signal") or "").upper()
            evaluation_context = dict(context or {})
            evaluation_context["_market_regime"] = market_value
            evaluation_context["_symbol_market_regime"] = symbol_value
            evaluation_context["market_regime"] = effective_regime
            evaluation_context["_market_regime_source"] = regime_source
            evaluation_context["_regime_scope"] = regime_scope
            base_signal = str(evaluation_context.get("signal") or "HOLD").upper()
            if signal_mode == "independent":
                if entry_signal not in {"LONG", "SHORT"}:
                    evaluated.append({
                        "name": item.get("name", "사용자 전략"),
                        "result": {"allowed": False, "reason": "independent_entry_signal_missing"},
                    })
                    continue
                evaluation_context["signal"] = entry_signal
            elif "signal" in evaluation_context and base_signal not in {"LONG", "SHORT"}:
                continue
            entry = cls.evaluate_entry(rules, evaluation_context)
            evaluated.append({"name": item.get("name", "사용자 전략"), "result": entry})
            if entry.get("allowed", False):
                from .custom_strategy_runtime import (
                    derive_strategy_risk_settings,
                    normalize_engine_settings,
                )
                engine_values = dict(item.get("engine_settings") or {})

                # 국면·성과 조정은 선택된 전략 후보 안에서만 적용한다.
                # 글로벌 Trader/Analyzer 설정을 바꾸면 다른 활성 전략의
                # 통계적 성격까지 오염되므로 금지한다.
                regime_parameters = dict(
                    rules.get(
                        "regime_parameters",
                        rules.get("market_condition_parameters", {}),
                    )
                    or {}
                )
                regime_override = regime_parameters.get(
                    symbol_value if regime_scope == "symbol" else market_value,
                    {},
                )
                if isinstance(regime_override, dict) and regime_override:
                    engine_values.update(normalize_engine_settings(regime_override))

                performance = dict(
                    evaluation_context.get("_strategy_performance", {}) or {}
                )
                consecutive_losses = int(performance.get("consecutive_losses", 0) or 0)
                recent_win_rate = float(performance.get("recent_win_rate", 0.5) or 0.5)
                for adjustment in list(rules.get("performance_adjustments", []) or []):
                    if not isinstance(adjustment, dict):
                        continue
                    condition = dict(adjustment.get("when", {}) or {})
                    loss_min = int(condition.get("consecutive_losses_gte", -1) or -1)
                    win_min = float(condition.get("recent_win_rate_gte", -1) or -1)
                    matched = (
                        (loss_min >= 0 and consecutive_losses >= loss_min)
                        or (win_min >= 0 and recent_win_rate >= win_min)
                    )
                    if matched:
                        engine_values.update(
                            normalize_engine_settings(dict(adjustment.get("set", {}) or {}))
                        )
                        break
                engine_settings = derive_strategy_risk_settings(
                    engine_values,
                    rules.get("risk_model"),
                    evaluation_context,
                )
                return {
                    **entry,
                    "selected_strategy_id": item.get("id"),
                    "selected_strategy_key": item.get("strategy_key"),
                    "selected_version_id": item.get("version_id"),
                    "selected_strategy_name": item.get("name", "사용자 전략"),
                    "selected_rules": rules,
                    "engine_settings": engine_settings,
                    "target_scope": item.get("target_scope"),
                    "market_regime": effective_regime,
                    "overall_market_regime": market_value,
                    "symbol_market_regime": symbol_value,
                    "regime_scope": regime_scope,
                    "market_regime_source": regime_source,
                    "signal_mode": signal_mode,
                    "entry_signal": entry_signal if signal_mode == "independent" else base_signal,
                    "operation_mode": str(item.get("operation_mode") or "standard"),
                    "runtime_indicator_values": list(
                        evaluation_context.get("_advanced_indicator_values") or []
                    ),
                    "evaluated": evaluated,
                }
        if not evaluated:
            transition = "delegate_to_noah"
            for item in scoped:
                item_rules = dict(item.get("rules") or {})
                policy = str(item_rules.get("regime_transition", "delegate_to_noah") or "delegate_to_noah").lower()
                if policy == "pause":
                    transition = "pause"
                    break
            if transition == "pause":
                return {
                    "allowed": False,
                    "bypassed": False,
                    "reason": "custom_paused_outside_selected_regime",
                    "transition_action": "pause",
                    "market_regime": regimes_context["market"],
                    "evaluated": [],
                }
            return {
                "allowed": True,
                "bypassed": True,
                "reason": "delegated_to_noah_outside_selected_regime",
                "transition_action": "delegate_to_noah",
                "market_regime": regimes_context["market"],
                "evaluated": [],
            }
        return {
            "allowed": False,
            "bypassed": False,
            "reason": "no_strategy_matched_current_scope_regime_and_entry",
            "market_regime": regimes_context["market"],
            "evaluated": evaluated,
        }
