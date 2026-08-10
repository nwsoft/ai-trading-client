"""AI 커스텀 숙련도 프로필과 개별 기능 게이트.

프로필은 화면 복잡도의 기본값일 뿐 안전 게이트를 우회하지 않는다.
사용자는 개별 기능을 다시 켜거나 끌 수 있고, 유료 마켓은 법무/결제
준비 전까지 이 클라이언트 설정으로 열 수 없다.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping


PROFILE_FEATURES: Dict[str, Dict[str, bool]] = {
    "beginner": {
        "replay_analytics": True,
        "monthly_yearly_table": False,
        "expression_graph": False,
        "user_indicator_language": False,
        "strategy_package": False,
        "team_sharing": False,
        "quality_report": True,
        "signed_webhook": False,
        "b2b_audit": False,
    },
    "standard": {
        "replay_analytics": True,
        "monthly_yearly_table": True,
        "expression_graph": False,
        "user_indicator_language": False,
        "strategy_package": True,
        "team_sharing": False,
        "quality_report": True,
        "signed_webhook": False,
        "b2b_audit": False,
    },
    "advanced": {
        "replay_analytics": True,
        "monthly_yearly_table": True,
        "expression_graph": True,
        "user_indicator_language": True,
        "strategy_package": True,
        "team_sharing": True,
        "quality_report": True,
        "signed_webhook": False,
        "b2b_audit": True,
    },
    "lab": {
        "replay_analytics": True,
        "monthly_yearly_table": True,
        "expression_graph": True,
        "user_indicator_language": True,
        "strategy_package": True,
        "team_sharing": True,
        "quality_report": True,
        "signed_webhook": True,
        "b2b_audit": True,
    },
}

PROFILE_VIEW_LEVEL = {"beginner": 1, "standard": 2, "advanced": 3, "lab": 3}
PROFILE_LABELS = {
    "beginner": "초보자",
    "standard": "일반",
    "advanced": "고급",
    "lab": "실험실",
}
FEATURE_KEYS = tuple(next(iter(PROFILE_FEATURES.values())).keys())


def normalize_ai_custom_feature_settings(raw: Any) -> Dict[str, Any]:
    payload = dict(raw or {}) if isinstance(raw, Mapping) else {}
    profile = str(payload.get("profile") or "standard").strip().lower()
    if profile not in PROFILE_FEATURES:
        profile = "standard"
    overrides = payload.get("overrides")
    if not isinstance(overrides, Mapping):
        overrides = {}
    clean_overrides = {
        key: bool(value) for key, value in overrides.items() if key in FEATURE_KEYS
    }
    return {"profile": profile, "overrides": clean_overrides}


def resolve_ai_custom_features(settings_or_feature_settings: Any) -> Dict[str, Any]:
    raw = settings_or_feature_settings
    if isinstance(raw, Mapping) and "ai_custom_features" in raw:
        raw = raw.get("ai_custom_features")
    normalized = normalize_ai_custom_feature_settings(raw)
    profile = normalized["profile"]
    features = deepcopy(PROFILE_FEATURES[profile])
    features.update(normalized["overrides"])

    # 종속 기능은 기반 기능이 꺼지면 실패 폐쇄한다.
    if not features["replay_analytics"]:
        features["monthly_yearly_table"] = False
        features["quality_report"] = False
    if not features["strategy_package"]:
        features["team_sharing"] = False
    # webhook은 외부 신호 입력용 운영 기능이다. 운영 endpoint와 실제 E2E를
    # 이해하는 실험실 프로필에서만 노출하며 지정 거래소 연결을 대체하지 않는다.
    if profile != "lab":
        features["signed_webhook"] = False
    return {
        "profile": profile,
        "profile_label": PROFILE_LABELS[profile],
        "view_level": PROFILE_VIEW_LEVEL[profile],
        "features": features,
        "overrides": normalized["overrides"],
        "marketplace": False,
        "marketplace_reason": "payment_legal_operations_not_ready",
    }
