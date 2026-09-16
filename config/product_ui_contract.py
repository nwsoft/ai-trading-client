"""NoahAI v3.9.1.12 product UI contract shared by legacy and Web UI.

This module intentionally contains data only.  It is safe for the headless
runtime to import and prevents the legacy dashboard, Web inventory, settings
and manual from maintaining divergent copies of the visible information
architecture.
"""

from __future__ import annotations


SERVICE_ORDER = (
    ("blockchain", "블록체인"),
    ("stock", "주식/증권"),
    ("portfolio", "자산 통합"),
    ("personal_finance", "생활금융"),
    ("ai_analyst", "AI애널리스트"),
)

SERVICE_SOURCES = {
    "blockchain": ("binance", "upbit", "bithumb", "coinone", "bybit", "okx", "bitget"),
    "stock": ("kiwoom", "shinhan", "mirae", "kis"),
    "portfolio": (),
    "personal_finance": (),
    "ai_analyst": (),
}

SERVICE_FEATURE_LABELS = {
    "blockchain": (
        "실시간 거래 로그",
        "코인 정보",
        "거래 통계",
        "시장 트렌드",
        "AI 학습",
        "AI 리포트",
        "AI 어시스턴트",
        "전략 스튜디오",
        "금융 인텔리전스",
        "AlphaArena",
        "거래소 운영",
    ),
    "stock": (
        "실시간 거래 로그",
        "종목 정보",
        "거래 통계",
        "시장 트렌드",
        "AI 학습",
        "AI 리포트",
        "AI 어시스턴트",
        "전략 스튜디오",
        "금융 인텔리전스",
        "증권사 운영",
    ),
    "portfolio": (
        "자산 통합 인사이트",
        "자산 배분 진단",
        "리스크 브리핑",
        "성과·위험 분석",
    ),
    "personal_finance": (
        "생활금융 서비스",
        "현금흐름 분석",
        "생활금융 목표",
        "보안 경고",
        "세금 계산",
    ),
    "ai_analyst": (
        "AI 애널리스트",
        "AI 어시스턴트",
        "AI 요약 리포트",
        "시나리오 점검",
        "금융 인텔리전스 허브",
    ),
}

SETTINGS_SECTION_LABELS = (
    "일반",
    "거래소 선택",
    "거래소 API",
    "AI 엔진/API",
    "알림·리포트",
    "고급 매매 계층",
    "AlphaArena",
    "AI 시스템 상태",
    "업데이트",
)

MANUAL_SECTION_LABELS = (
    "NoahAI 소개",
    "실거래 준비",
    "시작·설정",
    "금융 인텔리전스",
    "NoahAI 작동 원리",
    "자산별 사용 가이드",
    "증권/주식/ETF",
    "AI 어시스턴트",
    "전략 스튜디오",
    "AlphaArena",
    "업데이트",
)

# Nested contracts that exist inside a top-level feature.  These are kept here
# because a top-level tab match alone is not feature parity.
LIFE_FINANCE_INNER_TABS = (
    "대시보드",
    "거래",
    "목표",
    "분석",
    "차트",
    "금융상품",
    "AI 어시스턴트",
)

LIFE_FINANCE_QUICK_ACTIONS = (
    "대시보드",
    "지출 추가",
    "수입 추가",
    "목표 관리",
    "금융상품",
)

PORTFOLIO_INSIGHT_SECTIONS = (
    "통합 자산 현황",
    "자산군별 비중",
    "리스크 요약",
    "추천 액션",
)

AI_ANALYST_CARDS = (
    "포트폴리오 종합 분석",
    "시장 신호 & 매매 타이밍",
    "리스크 평가 & 경고",
    "AI 맞춤 투자 조언",
    "성과 분석 & 비교",
    "뉴스 & 감성 분석",
)

# Source-workspace labels are inventory routes; the visible tabs are the
# source names themselves.  The remaining labels must appear in this order.
SOURCE_WORKSPACE_LABELS = {"거래소 운영", "증권사 운영"}


def visible_feature_labels(service: str) -> tuple[str, ...]:
    return tuple(
        label
        for label in SERVICE_FEATURE_LABELS[service]
        if label not in SOURCE_WORKSPACE_LABELS
    )
