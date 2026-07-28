#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""초보자용 AI 커스텀 시작 프리셋.

프리셋은 검토용 초안이며 저장·승인·자동검증·최종 적용 전에는 실행되지 않는다.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


PRESET_CATALOG: Dict[str, Dict[str, Any]] = {
    "auto_regime": {
        "name": "AI가 시장에 맞춰 자동 대응",
        "short_name": "AI 자동 대응",
        "risk": "상대적 위험도: 국면별 변동",
        "regimes": ["all"],
        "executable_template": False,
        "summary": (
            "NoahAI 기본 판단이 시장 국면을 먼저 확인하고 추세·눌림목·횡보·돌파 중 "
            "조건이 맞는 방식만 후보로 검토합니다. 맞는 전략이 없거나 신호가 충돌하면 HOLD합니다."
        ),
    },
    "trend_follow": {
        "name": "추세 따라가기",
        "short_name": "이평선 추세",
        "risk": "상대적 위험도: 낮음~중간",
        "regimes": ["bull", "bear", "trend"],
        "executable_template": True,
        "summary": "EMA 20·50·200 정렬과 가격·RSI·거래량을 확인해 명확한 추세 방향만 따릅니다.",
        "source_text": """전략명: 추세 따라가기
목적: 명확한 추세에서만 이동평균 정렬 방향으로 진입한다.
시장상황: 상승장, 하락장, 추세장. 횡보장과 HIGH 고변동에서는 신규 진입하지 않는다.
LONG 진입: EMA20 > EMA50 > EMA200, 현재 가격 > EMA20, RSI는 50 이상 75 이하, 거래량은 최근 평균 이상.
SHORT 진입: EMA20 < EMA50 < EMA200, 현재 가격 < EMA20, RSI는 25 이상 50 이하, 거래량은 최근 평균 이상.
청산: EMA20과 EMA50 정렬이 반대로 바뀌거나 가격이 EMA50을 반대 방향으로 확정 이탈할 때.
손절: ATR 기반 또는 최근 스윙 지점 밖. 익절: 최소 예상 손익비 1.8 이상.
포지션: 1회 위험예산 0.5%, 증거금 최대 10%, 레버리지 상한 3배.
공통 안전: 큰 시간대와 진입 신호가 충돌하거나 유동성·스프레드·손익비 기준 미달이면 HOLD한다.
이 초안은 성과를 보장하지 않으며 사용자 검토·자동검증 전에는 실행하지 않는다.""",
    },
    "trend_pullback": {
        "name": "눌림목 진입",
        "short_name": "추세 눌림목",
        "risk": "상대적 위험도: 중간",
        "regimes": ["bull", "bear", "trend"],
        "executable_template": True,
        "summary": "EMA50·EMA200으로 큰 추세를 확인한 뒤 EMA20·EMA50 부근 조정이 끝날 때만 재진입합니다.",
        "source_text": """전략명: 눌림목 진입
목적: 확인된 추세 중 되돌림이 끝날 때 추세 방향으로 재진입한다.
시장상황: 완만한 상승·하락 추세와 NORMAL 변동성. 횡보장과 급격한 HIGH 국면에서는 HOLD한다.
LONG 진입: EMA50 > EMA200, 가격이 EMA20 또는 EMA50 부근까지 조정, RSI가 40~55에서 다시 상승, 가격이 EMA20을 재돌파, 거래량 회복.
SHORT 진입: EMA50 < EMA200, 가격이 EMA20 또는 EMA50 부근까지 반등, RSI가 45~60에서 다시 하락, 가격이 EMA20 아래로 재진입, 거래량 회복.
청산: EMA50 반대 이탈 또는 추세 정렬 해제.
손절: 최근 스윙 지점 밖 또는 ATR 기반. 익절: 최소 예상 손익비 1.8 이상, 추세 유지 시 추적손절 검토.
포지션: 1회 위험예산 0.5%, 증거금 최대 10%, 레버리지 상한 3배.
공통 안전: 큰 시간대 방향과 진입 신호가 충돌하거나 조건이 부족하면 HOLD한다.
이 초안은 성과를 보장하지 않으며 사용자 검토·자동검증 전에는 실행하지 않는다.""",
    },
    "range_rsi": {
        "name": "횡보장 저점·고점 대응",
        "short_name": "박스권 RSI",
        "risk": "상대적 위험도: 중간",
        "regimes": ["range", "calm"],
        "executable_template": True,
        "summary": "평평한 추세와 박스권이 확인된 경우에만 RSI 반전을 사용하고 돌파가 시작되면 중지합니다.",
        "source_text": """전략명: 횡보장 저점·고점 대응
목적: 방향성이 낮은 박스권에서만 RSI 평균회귀 후보를 만든다.
시장상황: 횡보장, LOW 또는 NORMAL 변동성. 상승·하락 추세와 HIGH 변동성에서는 신규 진입하지 않는다.
LONG 진입: 가격이 박스권 하단에 접근, RSI 28~35 이하에서 상향 전환, 하락 모멘텀 둔화, 반등 거래량 확인.
SHORT 진입: 가격이 박스권 상단에 접근, RSI 65~72 이상에서 하향 전환, 상승 모멘텀 둔화.
청산: 박스권 중앙에서 일부, 반대편에서 나머지. 박스권 경계를 거래량과 함께 이탈하면 즉시 전략 중지 또는 손절.
손절: 박스권 경계 밖 또는 ATR 기반. 익절: 최소 예상 손익비 1.8 이상.
포지션: 1회 위험예산 0.5%, 증거금 최대 10%, 레버리지 상한 2배.
공통 안전: 추세가 강해지거나 여러 시간대 방향이 충돌하면 HOLD한다.
이 초안은 성과를 보장하지 않으며 사용자 검토·자동검증 전에는 실행하지 않는다.""",
    },
    "volume_breakout": {
        "name": "강한 거래량 돌파",
        "short_name": "거래량 돌파",
        "risk": "상대적 위험도: 중간~높음",
        "regimes": ["trend", "volatile"],
        "executable_template": True,
        "summary": "가격 범위가 축소된 뒤 거래량을 동반한 20봉 고점·저점 돌파만 검토합니다.",
        "source_text": """전략명: 강한 거래량 돌파
목적: 좁은 가격 범위 이후 거래량을 동반한 확정 돌파만 추종한다.
시장상황: LOW에서 NORMAL로 변동성이 확대되는 구간. 이미 과도한 HIGH 변동성이면 HOLD한다.
LONG 진입: 최근 20개 봉 최고가 돌파, 거래량이 최근 평균의 1.5배 이상, 모멘텀 양수, RSI 55 이상 75 이하, 돌파선 위 유지.
SHORT 진입: 최근 20개 봉 최저가 돌파, 거래량이 최근 평균의 1.5배 이상, 모멘텀 음수, RSI 25 이상 45 이하, 돌파선 아래 유지.
청산: 가격이 돌파선 안으로 복귀하거나 거래량과 모멘텀이 동시에 약화될 때.
손절: 돌파 기준선 반대편 또는 ATR 1.5배. 익절: 최소 예상 손익비 2.0 이상, 변동성 유지 시 추적손절 검토.
포지션: 1회 위험예산 0.5%, 증거금 최대 8%, 레버리지 상한 2배.
공통 안전: 유동성 부족·스프레드 확대·큰 시간대 역방향·가짜 돌파 의심 시 HOLD한다.
이 초안은 성과를 보장하지 않으며 사용자 검토·자동검증 전에는 실행하지 않는다.""",
    },
}


def list_beginner_presets() -> List[Dict[str, Any]]:
    return [{"key": key, **deepcopy(value)} for key, value in PRESET_CATALOG.items()]


def get_beginner_preset(key: str) -> Optional[Dict[str, Any]]:
    item = PRESET_CATALOG.get(str(key or "").strip().lower())
    return deepcopy(item) if item else None


def preset_key_from_text(message: str) -> Optional[str]:
    normalized = str(message or "").lower().replace(" ", "")
    aliases = (
        ("auto_regime", ("ai자동대응", "시장에맞춰자동", "자동대응")),
        ("trend_pullback", ("눌림목", "되돌림진입")),
        ("range_rsi", ("박스권", "횡보장", "rsi반전", "저점고점")),
        ("volume_breakout", ("거래량돌파", "돌파매매")),
        ("trend_follow", ("이평선", "이동평균", "추세따라가기", "추세추종", "골든크로스")),
    )
    for key, tokens in aliases:
        if any(token in normalized for token in tokens):
            return key
    return None


def recommend_preset_for_regime(
    regime: str,
    *,
    signal_conflict: bool = False,
    volume_expansion: bool = False,
) -> str:
    """초보자 설명용 추천. 실제 주문은 기존 가드레일과 활성 전략만 사용한다."""
    if signal_conflict:
        return "hold"
    normalized = str(regime or "").strip().lower()
    if normalized in {"range", "sideways", "calm", "low"}:
        return "range_rsi"
    if normalized in {"bull", "bear", "trend", "normal"}:
        return "trend_pullback"
    if normalized in {"volatile", "high"} and volume_expansion:
        return "volume_breakout"
    return "hold"

