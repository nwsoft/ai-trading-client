#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서비스별 탭 정책 스펙.

대시보드 UI와 테스트에서 동일한 탭 정책을 공유하기 위한 모듈.
"""

from __future__ import annotations

from typing import Dict, List, Set

from config.product_ui_contract import SERVICE_FEATURE_LABELS, visible_feature_labels


COMMON_TRADING_TABS: Set[str] = {
    "실시간 거래 로그",
    "AI 학습",
    "AI 리포트",
    "AI 어시스턴트",
    "전략 스튜디오",
}

SERVICE_TAB_SPECS: Dict[str, Dict[str, List[str]]] = {
    "blockchain": {
        "primary": [
            "코인 정보",
            "거래 통계",
            "시장 트렌드",
            "금융 인텔리전스",
            "AlphaArena",
        ],
        "detail": [],
    },
    "stock": {
        "primary": [
            "종목 정보",
            "거래 통계",
            "시장 트렌드",
            "금융 인텔리전스",
        ],
        "detail": [],
    },
    "real_estate": {
        "primary": ["자산 통합 인사이트"],
        "detail": [
            "자산 배분 진단",
            "리스크 브리핑",
            "성과·위험 분석",
        ],
    },
    "other": {
        "primary": ["생활금융 서비스"],
        "detail": [
            "현금흐름 분석",
            "생활금융 목표",
            "보안 경고",
            "세금 계산",
        ],
    },
    "ai_analyst": {
        "primary": ["AI 애널리스트", "AI 어시스턴트"],
        "detail": [
            "AI 요약 리포트",
            "시나리오 점검",
            "금융 인텔리전스 허브",
        ],
    },
}

_PRODUCT_SERVICE_BY_LEGACY_SERVICE = {
    "blockchain": "blockchain",
    "stock": "stock",
    "real_estate": "portfolio",
    "other": "personal_finance",
    "ai_analyst": "ai_analyst",
}


def _legacy_policy_labels(service: str) -> tuple[str, ...]:
    spec = SERVICE_TAB_SPECS[service]
    if service in {"blockchain", "stock"}:
        info_tab = "코인 정보" if service == "blockchain" else "종목 정보"
        labels = (
            "실시간 거래 로그",
            info_tab,
            "거래 통계",
            "시장 트렌드",
            "AI 학습",
            "AI 리포트",
            "AI 어시스턴트",
            "전략 스튜디오",
            "금융 인텔리전스",
        )
        return labels + (("AlphaArena",) if service == "blockchain" else ())
    return tuple(spec.get("primary", [])) + tuple(spec.get("detail", []))


# Import-time drift guard for all five services.  A label/order change on one
# UI now fails immediately instead of silently producing a different Web app.
for _legacy_service, _product_service in _PRODUCT_SERVICE_BY_LEGACY_SERVICE.items():
    assert _legacy_policy_labels(_legacy_service) == visible_feature_labels(_product_service)


def normalize_service_name(service_name: str | None) -> str:
    service = str(service_name or "").strip().lower()
    if service == "other_investment":
        return "other"
    return service


def get_service_protected_tabs(service_name: str | None) -> Set[str]:
    service = normalize_service_name(service_name)

    if service in {"blockchain", "stock"}:
        spec = SERVICE_TAB_SPECS.get(service, {})
        return set(COMMON_TRADING_TABS) | set(spec.get("primary", []))

    spec = SERVICE_TAB_SPECS.get(service)
    if not spec:
        return set(COMMON_TRADING_TABS)

    return set(spec.get("primary", [])) | set(spec.get("detail", []))


def get_service_detail_tabs(service_name: str | None) -> List[str]:
    service = normalize_service_name(service_name)
    spec = SERVICE_TAB_SPECS.get(service, {})
    return list(spec.get("detail", []))


def get_service_tab_order(
    service_name: str | None,
    source_tabs: List[str] | None = None,
) -> List[str]:
    """Return the single canonical visible-tab order for a service.

    Exchange/broker detail tabs always follow the service's information and
    analysis tabs.  This prevents a tab that was recreated after navigation
    (for example ``코인 정보``) from drifting behind BINANCE/UPBIT.
    """
    service = normalize_service_name(service_name)
    sources = list(dict.fromkeys(source_tabs or []))
    product_service = _PRODUCT_SERVICE_BY_LEGACY_SERVICE.get(service)
    if product_service:
        return list(visible_feature_labels(product_service)) + sources
    return sources


def get_service_tab_snapshot(service_name: str | None) -> Dict[str, object]:
    """서비스별 탭 스냅샷(테스트용)을 반환한다."""
    service = normalize_service_name(service_name)
    spec = SERVICE_TAB_SPECS.get(service, {})
    protected = sorted(get_service_protected_tabs(service))
    primary = list(spec.get("primary", []))
    detail = list(spec.get("detail", []))
    return {
        "service": service,
        "primary_tabs": primary,
        "detail_tabs": detail,
        "protected_tabs": protected,
    }


def format_exchange_scope_label(
    enabled_exchanges: List[str] | None,
    selected_exchange: str | None,
) -> str:
    """Keep analysis scope distinct from the currently selected context."""
    enabled = list(
        dict.fromkeys(
            str(item).strip().lower()
            for item in (enabled_exchanges or [])
            if str(item).strip()
        )
    )
    selected = str(selected_exchange or "").strip().lower()
    if not enabled:
        return "거래소: 없음"
    if selected not in enabled:
        selected = enabled[0]
    if len(enabled) == 1:
        return f"거래소: {enabled[0].upper()}"
    return f"거래소: {len(enabled)}곳 · 기준 {selected.upper()}"


def format_trading_runtime_status(
    enabled_exchanges: Set[str] | List[str] | None,
    running_exchanges: Set[str] | List[str] | None,
) -> str:
    """Describe worker execution, not saved API/enablement configuration."""
    enabled = {str(item).strip().lower() for item in (enabled_exchanges or []) if str(item).strip()}
    running = {
        str(item).strip().lower()
        for item in (running_exchanges or [])
        if str(item).strip()
    } & enabled
    if not enabled:
        return "자율주행: 대상 거래소 없음"
    if not running:
        return f"자율주행: 정지 (0/{len(enabled)} 실행)"
    if running == enabled:
        return f"자율주행: 전체 실행 ({len(running)}/{len(enabled)})"
    return f"자율주행: 부분 실행 ({len(running)}/{len(enabled)})"
