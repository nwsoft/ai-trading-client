#!/usr/bin/env python3
"""AI 커스텀 전략의 제한된 선언형 조건을 안전하게 평가한다."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


class DeclarativeStrategyEngine:
    ALLOWED_FIELDS = {
        "signal", "confidence", "rsi", "macd", "bb_position", "ma20", "ma50",
        "current_price", "price", "trend_strength", "market_volatility", "volume_ratio",
    }
    OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "gt_field", "lt_field"}
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
            return float(value)
        except Exception:
            return value

    @classmethod
    def _condition(cls, condition: Dict[str, Any], context: Dict[str, Any]) -> Tuple[bool, str]:
        field = str(condition.get("field") or "").strip()
        operator = str(condition.get("operator") or "").strip().lower()
        if field not in cls.ALLOWED_FIELDS or operator not in cls.OPERATORS:
            return False, f"unsupported:{field}/{operator}"
        actual = context.get(field)
        if actual is None and field == "current_price":
            actual = context.get("price")
        expected = condition.get("value")
        if operator in {"gt_field", "lt_field"}:
            value_field = str(condition.get("value_field") or expected or "")
            if value_field not in cls.ALLOWED_FIELDS:
                return False, f"unsupported_value_field:{value_field}"
            expected = context.get(value_field)
        if actual is None or expected is None:
            return False, f"missing:{field}"
        left = cls._number(actual)
        right = cls._number(expected)
        try:
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
        spec = dict((rules or {}).get("executable_entry", {}) or {})
        if not spec:
            return {"allowed": True, "bypassed": True, "reason": "no_declarative_entry"}
        all_conditions = [item for item in (spec.get("all") or []) if isinstance(item, dict)]
        any_conditions = [item for item in (spec.get("any") or []) if isinstance(item, dict)]
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
            "reason": "custom_entry_passed" if allowed else "custom_entry_not_met",
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
        regime = cls.REGIME_ALIASES.get(str(market_regime or "").upper(), str(market_regime or "range").lower())
        candidates = sorted(
            [item for item in strategies if isinstance(item, dict)],
            key=lambda item: int(item.get("priority", 5) or 5),
            reverse=True,
        )[:10]
        evaluated = []
        scoped = []
        for item in candidates:
            if not cls._scope_matches(item.get("target_scope", ""), asset_class=asset_class, target=target):
                continue
            scoped.append(item)
            regimes = [str(value).strip().lower() for value in (item.get("market_regimes") or ["all"])]
            if "all" not in regimes and regime not in regimes:
                continue
            rules = dict(item.get("rules") or {})
            signal_mode = str(item.get("signal_mode") or rules.get("signal_mode") or "confirm").lower()
            entry_signal = str(item.get("entry_signal") or rules.get("entry_signal") or "").upper()
            evaluation_context = dict(context or {})
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
                from .custom_strategy_runtime import derive_strategy_risk_settings
                engine_settings = derive_strategy_risk_settings(
                    item.get("engine_settings"),
                    rules.get("risk_model"),
                    evaluation_context,
                )
                return {
                    **entry,
                    "selected_strategy_id": item.get("id"),
                    "selected_strategy_name": item.get("name", "사용자 전략"),
                    "engine_settings": engine_settings,
                    "target_scope": item.get("target_scope"),
                    "market_regime": regime,
                    "signal_mode": signal_mode,
                    "entry_signal": entry_signal if signal_mode == "independent" else base_signal,
                    "operation_mode": str(item.get("operation_mode") or "standard"),
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
                    "market_regime": regime,
                    "evaluated": [],
                }
            return {
                "allowed": True,
                "bypassed": True,
                "reason": "delegated_to_noah_outside_selected_regime",
                "transition_action": "delegate_to_noah",
                "market_regime": regime,
                "evaluated": [],
            }
        return {
            "allowed": False,
            "bypassed": False,
            "reason": "no_strategy_matched_current_scope_regime_and_entry",
            "market_regime": regime,
            "evaluated": evaluated,
        }
