#!/usr/bin/env python3
"""Noah Strategy IR v1 compiler and capability contract.

The IR wraps the existing fail-closed declarative strategy rules. It never
executes user code and keeps an exact canonical rule payload so the current
runtime remains the execution source while UI, validation, and sharing gain a
stable intermediate representation.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from .declarative_strategy_engine import DeclarativeStrategyEngine
from .user_indicator_language import UserIndicatorLanguage


IR_FORMAT = "noah-strategy-ir"
IR_VERSION = "1.0"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _unique(values: Iterable[Any]) -> List[str]:
    return sorted({str(value).strip().lower() for value in values if str(value).strip()})


class NoahStrategyIR:
    """Compile, validate, and project the bounded NoahAI strategy IR."""

    CAPABILITY_REGISTRY: Dict[str, Any] = {
        "registry_version": "1.0",
        "data_fields": sorted(DeclarativeStrategyEngine.ALLOWED_FIELDS),
        "indicator_names": sorted(DeclarativeStrategyEngine.ALLOWED_INDICATORS),
        "indicator_sources": sorted(DeclarativeStrategyEngine.ALLOWED_SOURCES),
        "timeframes": sorted(DeclarativeStrategyEngine.ALLOWED_TIMEFRAMES),
        "operators": sorted(DeclarativeStrategyEngine.OPERATORS),
        "condition_groups": ["all", "any", "expression", "and", "or"],
        "states": [
            "position",
            "previous_value",
            "cooldown",
            "reentry_count",
            "partial_fill",
            "trailing_peak",
            "break_even",
            "pyramiding_count",
        ],
        "orders": [
            "enter_long",
            "enter_short",
            "hold",
            "exit_all",
            "partial_exit",
            "stop_loss",
            "take_profit",
            "trailing_stop",
            "break_even",
            "reentry",
            "pyramiding",
        ],
        "advanced_order_features": sorted(DeclarativeStrategyEngine.ADVANCED_EXIT_KEYS),
        "user_indicator_language": "bounded-ast-v1",
        "venue_profiles": [
            "asset:crypto",
            "asset:stock",
            "asset:all",
            "exchange:*",
            "broker:*",
        ],
    }

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _reference_capabilities(cls, reference: Any) -> Dict[str, List[str]]:
        if isinstance(reference, Mapping):
            if "user_indicator" in reference:
                return {
                    "data_fields": [], "indicator_names": [],
                    "indicator_sources": [], "timeframes": [],
                }
            return {
                "data_fields": [],
                "indicator_names": [reference.get("indicator") or reference.get("name")],
                "indicator_sources": [reference.get("source") or "close"],
                "timeframes": [reference.get("timeframe") or "5m"],
            }
        return {
            "data_fields": [reference],
            "indicator_names": [],
            "indicator_sources": [],
            "timeframes": [],
        }

    @staticmethod
    def _node_evidence(
        rules: Mapping[str, Any],
        *,
        section: str,
        condition: Mapping[str, Any],
    ) -> Dict[str, Any]:
        trace = dict(rules.get("source_rule_trace") or {})
        trace_key = "entry" if section == "executable_entry" else "exit"
        traced = dict(trace.get(trace_key) or {})
        excerpts = [str(item) for item in (traced.get("evidence") or []) if str(item).strip()]
        if excerpts:
            return {
                "origin": "source_trace",
                "trace_key": trace_key,
                "status": str(traced.get("status") or "matched"),
                "excerpts": excerpts,
            }
        return {
            "origin": "user_declared_rule",
            "trace_key": trace_key,
            "status": "declared",
            "excerpts": [_canonical_json(condition)],
        }

    @classmethod
    def _condition_node(
        cls,
        rules: Mapping[str, Any],
        *,
        section: str,
        group: str,
        index: int,
        condition: Mapping[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, List[str]]]:
        condition_payload = deepcopy(dict(condition))
        supported, reason = DeclarativeStrategyEngine.validate_condition_spec(condition_payload)
        path = f"{section}.{group}[{index}]"
        node_id = f"condition_{_sha256({'path': path, 'condition': condition_payload})[:16]}"
        requirements = {
            "data_fields": [],
            "indicator_names": [],
            "indicator_sources": [],
            "timeframes": [],
            "operators": [condition_payload.get("operator")],
            "states": [],
            "orders": [],
        }
        for reference in (
            condition_payload.get("field"),
            condition_payload.get("value_field")
            if condition_payload.get("value_field") is not None
            else None,
        ):
            if reference is None:
                continue
            reference_caps = cls._reference_capabilities(reference)
            for key, values in reference_caps.items():
                requirements[key].extend(values)
        if str(condition_payload.get("operator") or "").lower() in {
            "crosses_above",
            "crosses_below",
        }:
            requirements["states"].append("previous_value")
        requirements["orders"].append(
            "enter_long" if section == "executable_entry" else "exit_all"
        )
        return (
            {
                "node_id": node_id,
                "node_type": "condition",
                "path": path,
                "section": section,
                "group": group,
                "condition": condition_payload,
                "support_status": "supported" if supported else "unsupported",
                "support_reason": reason,
                "evidence": cls._node_evidence(
                    rules,
                    section=section,
                    condition=condition_payload,
                ),
            },
            requirements,
        )

    @classmethod
    def _advanced_nodes(
        cls, rules: Mapping[str, Any]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]]]:
        raw_plan = rules.get("advanced_order_plan") or {}
        if not isinstance(raw_plan, Mapping):
            raw_plan = {}
        nodes: List[Dict[str, Any]] = []
        requirements = {"states": [], "orders": [], "advanced_order_features": []}
        mapping = {
            "partial_take_profits": ("partial_exit", "partial_fill"),
            "trailing_stop": ("trailing_stop", "trailing_peak"),
            "break_even": ("break_even", "break_even"),
            "reentry": ("reentry", "reentry_count"),
            "pyramiding": ("pyramiding", "pyramiding_count"),
        }
        for key, payload in raw_plan.items():
            order_capability, state_capability = mapping.get(
                str(key), (str(key), str(key))
            )
            nodes.append({
                "node_id": f"order_{_sha256({'feature': key, 'payload': payload})[:16]}",
                "node_type": "advanced_order",
                "path": f"advanced_order_plan.{key}",
                "feature": str(key),
                "payload": deepcopy(payload),
                "support_status": (
                    "supported"
                    if key in DeclarativeStrategyEngine.ADVANCED_EXIT_KEYS
                    else "unsupported"
                ),
                "evidence": {
                    "origin": "user_declared_rule",
                    "status": "declared",
                    "excerpts": [_canonical_json(payload)],
                },
            })
            requirements["advanced_order_features"].append(key)
            requirements["orders"].append(order_capability)
            requirements["states"].append(state_capability)
        return nodes, requirements

    @classmethod
    def _capability_profile(
        cls,
        rules: Mapping[str, Any],
        requirements: Mapping[str, Iterable[Any]],
    ) -> Dict[str, Any]:
        required = {key: _unique(values) for key, values in requirements.items()}
        scope = str(rules.get("target_scope") or "asset:crypto").strip().lower()
        required["venue_profiles"] = [scope]

        unsupported: List[str] = []
        checks = {
            "data_fields": "data_fields",
            "indicator_names": "indicator_names",
            "indicator_sources": "indicator_sources",
            "timeframes": "timeframes",
            "operators": "operators",
            "states": "states",
            "orders": "orders",
            "advanced_order_features": "advanced_order_features",
        }
        for required_key, registry_key in checks.items():
            supported_values = set(cls.CAPABILITY_REGISTRY[registry_key])
            for value in required.get(required_key, []):
                if value not in supported_values:
                    unsupported.append(f"{required_key}:{value}")

        venue_supported = (
            scope in {"asset:crypto", "asset:stock", "asset:all"}
            or scope.startswith("exchange:")
            or scope.startswith("broker:")
        )
        if not venue_supported:
            unsupported.append(f"venue_profiles:{scope}")
        return {
            "registry_version": cls.CAPABILITY_REGISTRY["registry_version"],
            "required": required,
            "unsupported": sorted(set(unsupported)),
            "status": "supported" if not unsupported else "unsupported",
        }

    @classmethod
    def compile(
        cls,
        rules: Mapping[str, Any],
        *,
        source_kind: str = "text",
        source_reference: str = "",
        missing_conditions: Iterable[Any] = (),
    ) -> Dict[str, Any]:
        if not isinstance(rules, Mapping):
            raise ValueError("Noah Strategy IR 입력 규칙은 mapping이어야 합니다.")
        canonical_rules = deepcopy(dict(rules))
        nodes: List[Dict[str, Any]] = []
        requirements: Dict[str, List[Any]] = {
            "data_fields": [],
            "indicator_names": [],
            "indicator_sources": [],
            "timeframes": [],
            "operators": [],
            "states": ["position"],
            "orders": ["hold", "stop_loss", "take_profit"],
            "advanced_order_features": [],
        }

        for section in ("executable_entry", "executable_exit"):
            spec = canonical_rules.get(section) or {}
            if not isinstance(spec, Mapping):
                continue
            for group in ("all", "any"):
                conditions = spec.get(group) or []
                if not isinstance(conditions, list):
                    continue
                for index, condition in enumerate(conditions):
                    if not isinstance(condition, Mapping):
                        continue
                    node, node_requirements = cls._condition_node(
                        canonical_rules,
                        section=section,
                        group=group,
                        index=index,
                        condition=condition,
                    )
                    nodes.append(node)
                    for key, values in node_requirements.items():
                        requirements.setdefault(key, []).extend(values)

            def add_expression_nodes(node: Any, path: str) -> None:
                if not isinstance(node, Mapping):
                    return
                node_type = str(node.get("type") or "condition").lower()
                if node_type == "condition":
                    condition = dict(node.get("condition") or {
                        key: value for key, value in node.items() if key != "type"
                    })
                    compiled_node, node_requirements = cls._condition_node(
                        canonical_rules,
                        section=section,
                        group="expression",
                        index=len(nodes),
                        condition=condition,
                    )
                    compiled_node["path"] = path
                    nodes.append(compiled_node)
                    for key, values in node_requirements.items():
                        requirements.setdefault(key, []).extend(values)
                    return
                nodes.append({
                    "node_id": f"group_{_sha256({'path': path, 'node': node})[:16]}",
                    "node_type": "boolean_group",
                    "path": path,
                    "section": section,
                    "operator": str(node.get("operator") or node.get("op") or "").lower(),
                    "support_status": "supported",
                    "evidence": cls._node_evidence(
                        canonical_rules, section=section, condition=dict(node),
                    ),
                })
                for index, child in enumerate(node.get("children") or []):
                    add_expression_nodes(child, f"{path}.children[{index}]")

            if spec.get("expression") is not None:
                add_expression_nodes(spec.get("expression"), f"{section}.expression")

        user_indicator_validation = UserIndicatorLanguage.validate_definitions(
            canonical_rules.get("user_indicators")
        )
        for name, detail in (user_indicator_validation.get("dependencies") or {}).items():
            nodes.append({
                "node_id": f"indicator_{_sha256({'name': name, 'expression': detail.get('expression')})[:16]}",
                "node_type": "user_indicator_formula",
                "path": f"user_indicators.{name}",
                "name": name,
                "expression": detail.get("expression"),
                "dependencies": list(detail.get("dependencies") or []),
                "indicator_dependencies": list(detail.get("indicator_dependencies") or []),
                "support_status": "supported",
                "evidence": {
                    "origin": "user_declared_rule", "status": "declared",
                    "excerpts": [str(detail.get("expression") or "")],
                },
            })
            requirements["data_fields"].extend(
                dependency for dependency in (detail.get("dependencies") or [])
                if dependency in DeclarativeStrategyEngine.ALLOWED_FIELDS
            )
            for reference in detail.get("indicator_references") or []:
                requirements["indicator_names"].append(reference.get("indicator"))
                requirements["timeframes"].append(reference.get("timeframe"))
                requirements["indicator_sources"].append(reference.get("source"))

        advanced_nodes, advanced_requirements = cls._advanced_nodes(canonical_rules)
        nodes.extend(advanced_nodes)
        for key, values in advanced_requirements.items():
            requirements.setdefault(key, []).extend(values)

        entry_signal = str(canonical_rules.get("entry_signal") or "").upper()
        if entry_signal == "LONG":
            requirements["orders"].append("enter_long")
        elif entry_signal == "SHORT":
            requirements["orders"].append("enter_short")

        capability_profile = cls._capability_profile(canonical_rules, requirements)
        declarative_validation = DeclarativeStrategyEngine.validate_rule_spec(
            canonical_rules
        )
        missing = _unique(missing_conditions)
        unsupported = sorted({
            *list(declarative_validation.get("errors") or []),
            *list(capability_profile.get("unsupported") or []),
            *[
                str(node.get("support_reason") or node.get("path"))
                for node in nodes
                if node.get("support_status") == "unsupported"
            ],
        })
        support_status = (
            "unsupported"
            if unsupported
            else "needs_clarification"
            if missing
            else "supported"
        )
        evidence_nodes = [node for node in nodes if node.get("evidence")]
        ir: Dict[str, Any] = {
            "format": IR_FORMAT,
            "ir_version": IR_VERSION,
            "compiler": "noahai_client",
            "compiled_at": cls._now(),
            "source": {
                "kind": str(source_kind or "text").strip().lower(),
                "reference": str(source_reference or "").strip(),
            },
            "strategy_contract": {
                "signal_mode": str(canonical_rules.get("signal_mode") or "confirm").lower(),
                "entry_signal": entry_signal,
                "target_scope": str(canonical_rules.get("target_scope") or "asset:crypto").lower(),
                "market_regimes": list(canonical_rules.get("market_regimes") or ["all"]),
                "regime_scope": str(canonical_rules.get("regime_scope") or "market").lower(),
                "regime_transition": str(
                    canonical_rules.get("regime_transition") or "delegate_to_noah"
                ).lower(),
            },
            "nodes": nodes,
            "capability_profile": capability_profile,
            "support": {
                "status": support_status,
                "missing_conditions": missing,
                "unsupported_reasons": unsupported,
                "node_count": len(nodes),
                "evidence_node_count": len(evidence_nodes),
            },
            "canonical_rules": canonical_rules,
            "canonical_rules_sha256": _sha256(canonical_rules),
        }
        ir["integrity_sha256"] = _sha256(ir)
        return ir

    @classmethod
    def validate(cls, ir: Mapping[str, Any]) -> Dict[str, Any]:
        errors: List[str] = []
        if not isinstance(ir, Mapping):
            return {"valid": False, "status": "unsupported", "errors": ["invalid_ir"]}
        payload = deepcopy(dict(ir))
        integrity = str(payload.pop("integrity_sha256", "") or "")
        if payload.get("format") != IR_FORMAT:
            errors.append("invalid_format")
        if payload.get("ir_version") != IR_VERSION:
            errors.append(f"unsupported_ir_version:{payload.get('ir_version')}")
        rules = payload.get("canonical_rules")
        if not isinstance(rules, Mapping):
            errors.append("missing_canonical_rules")
        elif str(payload.get("canonical_rules_sha256") or "") != _sha256(rules):
            errors.append("canonical_rules_hash_mismatch")
        if not integrity or integrity != _sha256(payload):
            errors.append("integrity_hash_mismatch")

        support = dict(payload.get("support") or {})
        status = str(support.get("status") or "unsupported")
        if status not in {"supported", "needs_clarification", "unsupported"}:
            errors.append(f"invalid_support_status:{status}")
        if isinstance(rules, Mapping):
            declarative = DeclarativeStrategyEngine.validate_rule_spec(dict(rules))
            # 미지원 규칙도 원본을 잃지 않고 IR로 보존할 수 있어야 한다.
            # 다만 지원 가능하다고 위조된 계약은 무결성 오류로 취급한다.
            if not declarative.get("valid") and status != "unsupported":
                errors.append("support_status_mismatch")
        return {
            "valid": not errors,
            "status": "unsupported" if errors else status,
            "errors": sorted(set(errors)),
            "canonical_rules_sha256": str(payload.get("canonical_rules_sha256") or ""),
            "integrity_sha256": integrity,
        }

    @classmethod
    def to_rules(cls, ir: Mapping[str, Any]) -> Dict[str, Any]:
        validation = cls.validate(ir)
        if not validation["valid"]:
            raise ValueError(
                "Noah Strategy IR 무결성 검증 실패: "
                + ", ".join(validation["errors"])
            )
        return deepcopy(dict(ir.get("canonical_rules") or {}))

    @classmethod
    def project(cls, ir: Mapping[str, Any], level: int) -> Dict[str, Any]:
        validation = cls.validate(ir)
        if not validation["valid"]:
            raise ValueError(
                "Noah Strategy IR 표시 불가: " + ", ".join(validation["errors"])
            )
        normalized_level = int(level)
        if normalized_level not in {1, 2, 3}:
            raise ValueError("Progressive Strategy UI level은 1, 2, 3만 허용합니다.")
        rules = dict(ir.get("canonical_rules") or {})
        support = dict(ir.get("support") or {})
        contract = dict(ir.get("strategy_contract") or {})
        base = {
            "level": normalized_level,
            "format": ir.get("format"),
            "ir_version": ir.get("ir_version"),
            "integrity_sha256": ir.get("integrity_sha256"),
            "support_status": support.get("status"),
            "missing_conditions": list(support.get("missing_conditions") or []),
            "unsupported_reasons": list(support.get("unsupported_reasons") or []),
            "evidence_coverage": {
                "nodes": int(support.get("node_count", 0) or 0),
                "traced": int(support.get("evidence_node_count", 0) or 0),
            },
            "strategy_contract": contract,
        }
        if normalized_level == 1:
            base["summary"] = {
                "entry": rules.get("entry"),
                "exit": rules.get("exit"),
                "stop_loss": rules.get("stop_loss"),
                "take_profit": rules.get("take_profit"),
                "position_size": rules.get("position_size"),
                "market_conditions": rules.get("market_conditions"),
            }
            return base
        base["editable_parameters"] = {
            "engine_settings": deepcopy(dict(rules.get("engine_settings") or {})),
            "risk_model": deepcopy(dict(rules.get("risk_model") or {})),
            "market_regimes": list(rules.get("market_regimes") or ["all"]),
            "regime_scope": rules.get("regime_scope", "market"),
            "conditions": [
                {
                    "node_id": node.get("node_id"),
                    "path": node.get("path"),
                    "condition": deepcopy(node.get("condition")),
                    "support_status": node.get("support_status"),
                }
                for node in (ir.get("nodes") or [])
                if node.get("node_type") == "condition"
            ],
        }
        if normalized_level == 2:
            return base
        base["nodes"] = deepcopy(list(ir.get("nodes") or []))
        base["capability_profile"] = deepcopy(dict(ir.get("capability_profile") or {}))
        base["canonical_rules"] = deepcopy(rules)
        return base

    @classmethod
    def round_trip(cls, ir: Mapping[str, Any]) -> Dict[str, Any]:
        rules = cls.to_rules(ir)
        source = dict(ir.get("source") or {})
        missing = list((ir.get("support") or {}).get("missing_conditions") or [])
        rebuilt = cls.compile(
            rules,
            source_kind=str(source.get("kind") or "text"),
            source_reference=str(source.get("reference") or ""),
            missing_conditions=missing,
        )
        return {
            "equivalent": (
                rebuilt.get("canonical_rules_sha256")
                == ir.get("canonical_rules_sha256")
            ),
            "before_sha256": ir.get("canonical_rules_sha256"),
            "after_sha256": rebuilt.get("canonical_rules_sha256"),
            "rebuilt_ir": rebuilt,
        }
