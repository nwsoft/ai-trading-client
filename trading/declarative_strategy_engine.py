#!/usr/bin/env python3
"""AI 커스텀 전략의 제한된 선언형 조건을 안전하게 평가한다."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from .user_indicator_language import UserIndicatorLanguage


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
    ADVANCED_EXIT_KEYS = {
        "partial_take_profits", "trailing_stop", "break_even", "reentry", "pyramiding",
    }
    EXPRESSION_GRAPH_MAX_DEPTH = 8
    EXPRESSION_GRAPH_MAX_NODES = 96

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
            if "user_indicator" in reference:
                name = str(reference.get("user_indicator") or "").strip().lower()
                if not UserIndicatorLanguage._NAME_RE.fullmatch(name):
                    return "", f"invalid_user_indicator:{name}"
                return UserIndicatorLanguage.field_key(name), "supported"
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
            if spec.get("expression") is not None:
                graph_validation = cls.validate_expression_graph(spec.get("expression"))
                errors.extend(
                    f"{section}.expression:{reason}"
                    for reason in graph_validation.get("errors", [])
                )
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
        indicator_validation = UserIndicatorLanguage.validate_definitions(
            (rules or {}).get("user_indicators")
        )
        errors.extend(indicator_validation.get("errors") or [])
        errors.extend(cls.validate_advanced_order_plan((rules or {}).get("advanced_order_plan")))
        return {"valid": not errors, "errors": errors}

    @classmethod
    def validate_expression_graph(cls, root: Any) -> Dict[str, Any]:
        errors: List[str] = []
        count = 0

        def visit(node: Any, path: str, depth: int) -> None:
            nonlocal count
            count += 1
            if count > cls.EXPRESSION_GRAPH_MAX_NODES:
                errors.append("node_limit_exceeded")
                return
            if depth > cls.EXPRESSION_GRAPH_MAX_DEPTH:
                errors.append(f"{path}:depth_limit_exceeded")
                return
            if not isinstance(node, dict):
                errors.append(f"{path}:invalid_node")
                return
            node_type = str(node.get("type") or "condition").lower()
            if node_type == "condition":
                condition = dict(node.get("condition") or {
                    key: value for key, value in node.items() if key != "type"
                })
                valid, reason = cls.validate_condition_spec(condition)
                if not valid:
                    errors.append(f"{path}:{reason}")
                return
            if node_type != "group":
                errors.append(f"{path}:unsupported_node_type:{node_type}")
                return
            operator = str(node.get("operator") or node.get("op") or "").lower()
            if operator not in {"and", "or"}:
                errors.append(f"{path}:unsupported_group_operator:{operator}")
            children = node.get("children")
            if not isinstance(children, list) or not 1 <= len(children) <= 32:
                errors.append(f"{path}:invalid_children")
                return
            for index, child in enumerate(children):
                visit(child, f"{path}.children[{index}]", depth + 1)

        visit(root, "root", 1)
        return {"valid": not errors, "errors": sorted(set(errors)), "node_count": count}

    @classmethod
    def _evaluate_expression_node(
        cls, node: Dict[str, Any], context: Dict[str, Any], path: str = "root"
    ) -> Tuple[bool, Dict[str, Any]]:
        node_type = str(node.get("type") or "condition").lower()
        if node_type == "condition":
            condition = dict(node.get("condition") or {
                key: value for key, value in node.items() if key != "type"
            })
            passed, reason = cls._condition(condition, context)
            return passed, {"path": path, "type": "condition", "passed": passed, "reason": reason}
        operator = str(node.get("operator") or node.get("op") or "").lower()
        child_results = [
            cls._evaluate_expression_node(child, context, f"{path}.children[{index}]")
            for index, child in enumerate(node.get("children") or [])
        ]
        passed = (
            all(result[0] for result in child_results)
            if operator == "and" else any(result[0] for result in child_results)
        )
        return passed, {
            "path": path, "type": "group", "operator": operator,
            "passed": passed, "children": [result[1] for result in child_results],
        }

    @classmethod
    def _prepare_user_indicator_context(
        cls, rules: Dict[str, Any], context: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], str]:
        definitions = (rules or {}).get("user_indicators")
        if not definitions:
            return dict(context or {}), "supported"
        enriched = dict(context or {})
        previous = dict(enriched.get("_previous") or {})
        try:
            enriched.update(UserIndicatorLanguage.evaluate_definitions(definitions, enriched))
            if previous:
                previous.update(UserIndicatorLanguage.evaluate_definitions(definitions, previous))
                enriched["_previous"] = previous
        except (ValueError, TypeError, ZeroDivisionError) as exc:
            return enriched, f"user_indicator_evaluation_failed:{exc}"
        return enriched, "supported"

    @classmethod
    def validate_advanced_order_plan(cls, raw_plan: Any) -> List[str]:
        """부분청산·트레일링·재진입 계획을 허용 목록과 수치 범위로 검증한다."""
        if raw_plan in (None, {}):
            return []
        if not isinstance(raw_plan, dict):
            return ["advanced_order_plan:invalid_spec"]
        errors: List[str] = []
        unknown = sorted(set(raw_plan) - cls.ADVANCED_EXIT_KEYS)
        errors.extend(f"advanced_order_plan:unsupported_key:{key}" for key in unknown)

        partials = raw_plan.get("partial_take_profits", []) or []
        if not isinstance(partials, list) or len(partials) > 5:
            errors.append("advanced_order_plan.partial_take_profits:invalid_group")
        else:
            total_fraction = 0.0
            previous_target = -1.0
            for index, item in enumerate(partials):
                if not isinstance(item, dict):
                    errors.append(f"advanced_order_plan.partial_take_profits[{index}]:invalid_step")
                    continue
                try:
                    target = float(item.get("target_percent"))
                    fraction = float(item.get("close_fraction"))
                except (TypeError, ValueError):
                    errors.append(f"advanced_order_plan.partial_take_profits[{index}]:invalid_number")
                    continue
                if not 0.05 <= target <= 100.0:
                    errors.append(f"advanced_order_plan.partial_take_profits[{index}]:target_out_of_range")
                if target <= previous_target:
                    errors.append(f"advanced_order_plan.partial_take_profits[{index}]:target_not_increasing")
                if not 0.01 <= fraction <= 1.0:
                    errors.append(f"advanced_order_plan.partial_take_profits[{index}]:fraction_out_of_range")
                total_fraction += fraction
                previous_target = target
            if total_fraction > 1.0000001:
                errors.append("advanced_order_plan.partial_take_profits:total_fraction_exceeds_one")

        numeric_contracts = {
            "trailing_stop": {
                "activation_percent": (0.0, 100.0), "distance_percent": (0.05, 20.0),
            },
            "break_even": {
                "trigger_percent": (0.05, 100.0), "offset_percent": (0.0, 5.0),
            },
            "reentry": {"cooldown_bars": (1, 10000), "max_reentries": (0, 20)},
            "pyramiding": {"max_entries": (1, 10), "add_fraction": (0.01, 1.0)},
        }
        for section, fields in numeric_contracts.items():
            payload = raw_plan.get(section)
            if payload in (None, {}):
                continue
            if not isinstance(payload, dict):
                errors.append(f"advanced_order_plan.{section}:invalid_spec")
                continue
            unexpected = sorted(set(payload) - set(fields) - {"enabled"})
            errors.extend(
                f"advanced_order_plan.{section}:unsupported_key:{key}" for key in unexpected
            )
            for field, (lower, upper) in fields.items():
                if field not in payload:
                    errors.append(f"advanced_order_plan.{section}:missing_{field}")
                    continue
                try:
                    value = float(payload[field])
                except (TypeError, ValueError):
                    errors.append(f"advanced_order_plan.{section}:{field}_invalid")
                    continue
                if not lower <= value <= upper:
                    errors.append(f"advanced_order_plan.{section}:{field}_out_of_range")
        return errors

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
        context, indicator_status = cls._prepare_user_indicator_context(rules, context)
        if indicator_status != "supported":
            return {
                "allowed": False, "bypassed": False,
                "reason": indicator_status,
            }
        expression = spec.get("expression")
        if expression is not None:
            validation = cls.validate_expression_graph(expression)
            if not validation["valid"]:
                return {
                    "allowed": False, "bypassed": False,
                    "reason": "invalid_expression_graph",
                    "errors": validation["errors"],
                }
            allowed, trace = cls._evaluate_expression_node(dict(expression), context)
            return {
                "allowed": allowed,
                "bypassed": False,
                "expression": trace,
                "reason": (
                    ("custom_entry_passed" if allowed else "custom_entry_not_met")
                    if section == "executable_entry"
                    else ("custom_exit_passed" if allowed else "custom_exit_not_met")
                ),
            }
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
        matched_results: List[Dict[str, Any]] = []
        demotions: List[Dict[str, Any]] = []
        improvement_proposals: List[Dict[str, Any]] = []
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
            strategy_performance_map = dict(context.get("_strategy_performance_by_id", {}) or {})
            strategy_performance = dict(
                strategy_performance_map.get(strategy_identity)
                or item.get("performance")
                or context.get("_strategy_performance")
                or {}
            )
            orchestration_policy = dict(item.get("orchestration_policy") or {})
            performance_trades = int(strategy_performance.get("trades", 0) or 0)
            min_samples = int(orchestration_policy.get("min_samples", 10) or 10)
            loss_limit = int(orchestration_policy.get("max_consecutive_losses", 0) or 0)
            min_win_rate = float(orchestration_policy.get("min_recent_win_rate", 0.0) or 0.0)
            recent_losses = int(strategy_performance.get("consecutive_losses", 0) or 0)
            recent_win_rate = float(strategy_performance.get("recent_win_rate", 0.0) or 0.0)
            demotion_reasons = []
            if performance_trades >= min_samples:
                if loss_limit > 0 and recent_losses >= loss_limit:
                    demotion_reasons.append("consecutive_loss_limit")
                if min_win_rate > 0 and recent_win_rate < min_win_rate:
                    demotion_reasons.append("recent_win_rate_below_policy")
            if demotion_reasons:
                demotion = {
                    "strategy_identity": strategy_identity,
                    "strategy_name": item.get("name", "사용자 전략"),
                    "action": "demote_to_paper",
                    "reasons": demotion_reasons,
                    "auto_changed": False,
                }
                demotions.append(demotion)
                improvement_proposals.append({
                    "strategy_identity": strategy_identity,
                    "action": "propose_new_version",
                    "reason": ",".join(demotion_reasons),
                    "requires_user_approval": True,
                })
                evaluated.append({
                    "name": item.get("name", "사용자 전략"),
                    "result": {"allowed": False, "reason": "strategy_demoted_to_paper"},
                })
                continue
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

                performance = strategy_performance
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
                matched_results.append({
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
                    "priority": int(item.get("priority", 5) or 5),
                })
        if matched_results:
            resolved_signals = {
                str(item.get("entry_signal") or "").upper()
                for item in matched_results
                if str(item.get("entry_signal") or "").upper() in {"LONG", "SHORT"}
            }
            if len(resolved_signals) > 1:
                return {
                    "allowed": False,
                    "bypassed": False,
                    "reason": "strategy_signal_conflict",
                    "transition_action": "hold",
                    "conflicting_strategies": [
                        {
                            "name": item.get("selected_strategy_name"),
                            "version_id": item.get("selected_version_id"),
                            "signal": item.get("entry_signal"),
                            "priority": item.get("priority"),
                        }
                        for item in matched_results
                    ],
                    "demotions": demotions,
                    "improvement_proposals": improvement_proposals,
                    "evaluated": evaluated,
                }
            winner = matched_results[0]
            winner["eligible_alternatives"] = [
                {
                    "name": item.get("selected_strategy_name"),
                    "version_id": item.get("selected_version_id"),
                    "priority": item.get("priority"),
                }
                for item in matched_results[1:]
            ]
            winner["demotions"] = demotions
            winner["improvement_proposals"] = improvement_proposals
            return winner
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
            "demotions": demotions,
            "improvement_proposals": improvement_proposals,
            "evaluated": evaluated,
        }
