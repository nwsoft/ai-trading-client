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
    """수익 단정 없이 사용자 여건에 맞는 검토 후보 2~3개를 설명한다."""
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
    results = []
    for key in keys[:3]:
        preset = get_beginner_preset(key) or {}
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
            "source_text": preset.get("source_text", ""),
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
