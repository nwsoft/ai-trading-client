"""AI 커스텀 초보자 인터뷰·후보 설명·버전 차이 계약."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Mapping

from .custom_strategy_presets import get_beginner_preset


PROFILE_FIELDS = (
    "asset_class", "capital_band", "max_loss_percent", "review_frequency",
    "trade_frequency", "leverage_allowed", "experience_level", "paper_ready",
)


def build_mentor_questions(profile: Mapping[str, Any] | None = None) -> List[Dict[str, Any]]:
    current = dict(profile or {})
    catalog = (
        ("asset_class", "어떤 자산을 운용할까요?", ["crypto", "stock", "both"]),
        ("capital_band", "운용 규모 범위를 선택하세요.", ["small", "medium", "large"]),
        ("max_loss_percent", "한 거래에서 허용할 최대 계좌 손실률은 몇 %인가요?", None),
        ("review_frequency", "계좌를 얼마나 자주 확인할 수 있나요?", ["intraday", "daily", "weekly"]),
        ("trade_frequency", "선호 거래 빈도는 어느 정도인가요?", ["low", "medium", "high"]),
        ("leverage_allowed", "레버리지를 사용할 의향이 있나요?", [False, True]),
        ("experience_level", "전략·주문 경험 수준은 어느 정도인가요?", ["beginner", "intermediate", "advanced"]),
        ("paper_ready", "먼저 PAPER 전진검증을 진행할 수 있나요?", [True, False]),
    )
    return [
        {"field": field, "question": question, "options": options, "answered": field in current}
        for field, question, options in catalog
        if field not in current
    ]


def validate_mentor_profile(profile: Mapping[str, Any] | None) -> Dict[str, Any]:
    values = dict(profile or {})
    missing = [field for field in PROFILE_FIELDS if field not in values]
    errors: List[str] = []
    try:
        max_loss = float(values.get("max_loss_percent", 0.0) or 0.0)
        if not 0.05 <= max_loss <= 5.0:
            errors.append("max_loss_percent_out_of_range")
    except (TypeError, ValueError):
        errors.append("max_loss_percent_invalid")
    return {"valid": not missing and not errors, "missing": missing, "errors": errors}


def recommend_strategy_candidates(profile: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """수익 단정 없이 사용자 여건에 맞는 실행 가능한 검토 초안을 만든다.

    NoahAI가 관리하는 프리셋은 모호한 자연어를 다시 AI에게 추측시키지 않는다.
    실행 필드는 코드로 고정된 선언형 템플릿에서 만들고, 사용자가 직접 검토한
    뒤에만 저장·승인·PAPER로 진행한다.
    """
    validation = validate_mentor_profile(profile)
    if not validation["valid"]:
        return []
    values = dict(profile)
    experience = str(values.get("experience_level") or "beginner")
    review = str(values.get("review_frequency") or "daily")
    frequency = str(values.get("trade_frequency") or "medium")
    keys = ["trend_follow", "trend_pullback"]
    if frequency != "low":
        keys.append("range_rsi")
    if experience == "advanced" and review == "intraday":
        keys[-1:] = ["volume_breakout"]
    max_loss = float(values.get("max_loss_percent") or 0.5)
    asset_class = str(values.get("asset_class") or "crypto").lower()
    leverage_allowed = bool(values.get("leverage_allowed"))
    results = []
    for key in keys[:3]:
        preset = get_beginner_preset(key) or {}
        rules = deepcopy(preset.get("rules_template") or {})
        rules["decision_timeframe"] = "1d" if asset_class == "stock" else "15m"
        rules["execution_timeframe"] = rules["decision_timeframe"]
        engine = dict(rules.get("engine_settings") or {})
        engine["leverage"] = min(int(engine.get("leverage", 1) or 1), 3) if leverage_allowed else 1
        rules["engine_settings"] = engine
        rules["risk_model"] = {
            "risk_per_trade_percent": max_loss,
            "max_margin_usage_percent": float(engine.get("position_size", 0.1) or 0.1) * 100.0,
            "max_leverage": int(engine.get("leverage", 1) or 1),
        }
        rules["risk_policy_preset"] = "custom"
        rules["regime_transition"] = "pause"
        rules["compiler_issues"] = []
        if asset_class == "stock" and isinstance(rules.get("independent_entries"), dict):
            long_spec = deepcopy(dict(rules["independent_entries"]).get("LONG") or {})
            rules.pop("independent_entries", None)
            rules["entry_signal"] = "LONG"
            rules["executable_entry"] = long_spec

        source_text = str(preset.get("source_text") or "") + f"\n판단 시간봉: {rules['decision_timeframe']} (완성된 봉 기준)"
        source_reference = f"noahai://mentor/{key}"
        trace = {
            field: {
                "status": "trusted_template",
                "rule_value": deepcopy(rules.get(field)),
                "evidence": [source_text[:500]],
                "source_kind": "noahai_template",
                "source_reference": source_reference,
            }
            for field in ("entry", "exit", "stop_loss", "take_profit", "position_size", "market_conditions")
        }
        rules["source_rule_trace"] = trace
        rules["source_evidence"] = {
            "kind": "noahai_template", "reference": source_reference,
            "title": str(preset.get("name") or key), "text": source_text,
            "warnings": [], "evidence": {"trusted_template": True},
        }

        from .custom_strategy_pipeline import CustomStrategyPipeline
        from .declarative_strategy_engine import DeclarativeStrategyEngine
        from .noah_strategy_ir import NoahStrategyIR
        from .strategy_source_ingestor import StrategySourceIngestor

        rules["source_grounding"] = {
            "status": "trusted_template",
            "compiler_contract_sha256": StrategySourceIngestor._execution_contract_digest(rules),
            "ai_execution_rules_accepted": False,
            "rejected_ai_paths": [],
        }

        readiness = CustomStrategyPipeline.paper_execution_readiness({
            "rules": rules, "missing_conditions": [],
        })
        executable = DeclarativeStrategyEngine.validate_rule_spec(rules)
        ready = bool(readiness.get("ready") and executable.get("valid"))
        strategy_ir = NoahStrategyIR.compile(
            rules, source_kind="noahai_template", source_reference=source_reference,
            missing_conditions=[] if ready else ["managed_template_validation_failed"],
        )
        analysis = {
            "name": preset.get("name", key),
            "summary": preset.get("summary", ""),
            "source": deepcopy(rules["source_evidence"]),
            "rules": deepcopy(rules),
            "engine_settings": deepcopy(engine),
            "missing_conditions": [] if ready else ["managed_template_validation_failed"],
            "unsupported_conditions": list(executable.get("errors") or []),
            "risks": ["연속 손실 가능", "수수료·슬리피지로 기대값 감소", "국면 전환 지연"],
            "scenarios": [],
            "market_regime_suggestion": {
                "regimes": list(rules.get("market_regimes") or ["all"]),
                "labels": list(rules.get("market_conditions") or []),
                "confidence": "managed_template",
                "evidence": "NoahAI 관리 템플릿에 선언된 실행 국면",
                "auto_select": True,
            },
            "ai_analyzed": False,
            "managed_template": True,
            "ready_for_review": ready,
            "ready_for_execution": ready,
            "execution_readiness": readiness,
            "strategy_ir": strategy_ir,
            "ir_level_1": NoahStrategyIR.project(strategy_ir, 1),
            "ir_level_2": NoahStrategyIR.project(strategy_ir, 2),
        }
        results.append({
            "preset_key": key,
            "name": preset.get("name", key),
            "summary": preset.get("summary", ""),
            "suitable_regimes": list(preset.get("regimes") or []),
            "why_fit": (
                f"확인 주기 {review}, 선호 빈도 {frequency}, "
                f"거래당 최대손실 {max_loss:.2f}% 조건에서 검토할 후보입니다."
            ),
            "when_not_to_trade": "국면 불일치·데이터 부족·비용 급증·신호 충돌 시 HOLD",
            "failure_risks": ["연속 손실 가능", "수수료·슬리피지로 기대값 감소", "국면 전환 지연"],
            "paper_required": True,
            "auto_applied": False,
            "executable_template": bool(preset.get("executable_template") and ready),
            "source_text": source_text,
            "draft_rules": deepcopy(rules),
            "draft_analysis": analysis,
            "venue_note": (
                "주식·ETF 후보는 LONG 진입만 포함합니다."
                if asset_class == "stock"
                else "선물의 LONG/SHORT를 포함하며 KRW 현물은 거래소 능력 계약에 따라 LONG만 실행합니다."
            ),
        })
    return results


def build_version_diff(previous: Mapping[str, Any] | None, current: Mapping[str, Any] | None) -> Dict[str, Any]:
    """변경 전후를 경로 단위로 표시하고 자동 적용하지 않는다."""
    before = dict(previous or {})
    after = dict(current or {})
    changes: List[Dict[str, Any]] = []

    def walk(path: str, left: Any, right: Any) -> None:
        if isinstance(left, Mapping) or isinstance(right, Mapping):
            left_map = dict(left or {}) if isinstance(left, Mapping) else {}
            right_map = dict(right or {}) if isinstance(right, Mapping) else {}
            for key in sorted(set(left_map) | set(right_map)):
                walk(f"{path}.{key}" if path else str(key), left_map.get(key), right_map.get(key))
            return
        if left != right:
            changes.append({"path": path, "before": deepcopy(left), "after": deepcopy(right)})

    walk("", before, after)
    return {
        "changed": bool(changes),
        "change_count": len(changes),
        "changes": changes,
        "requires_user_review": bool(changes),
        "auto_applied": False,
    }
