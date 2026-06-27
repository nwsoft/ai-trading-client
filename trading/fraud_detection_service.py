#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""금융 이상 탐지 서비스 — 사기 패턴 경고 및 거래 이상 감지.

책임 경계:
- NoahAI는 패턴 인식·경고·교육 정보 제공까지만 담당한다.
- 실제 사기 여부 확정, 법적 조치, 신고 행위는 사용자 책임이다.
- 모든 탐지 결과는 참고용이며, 오탐(False Positive) 가능성이 있다.

탐지 항목:
1. 보이스피싱 / 문자 사기(스미싱) 패턴 분석
2. 이상 거래 패턴 감지 (자신의 거래 내역 대비)
3. 약탈적 대출·투자 사기 경고 (상품 내용 기반)
4. 종합 리스크 점수 및 조치 가이드
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────
# 공통 데이터 구조
# ─────────────────────────────────────────────────────────────

@dataclass
class FraudAlert:
    alert_type: str          # 'voice_phishing' | 'smishing' | 'abnormal_tx' | 'predatory_loan'
    risk_level: str          # 'low' | 'medium' | 'high' | 'critical'
    score: float             # 0.0 ~ 1.0
    matched_patterns: List[str]
    description: str
    recommended_actions: List[str]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec='seconds'))


@dataclass
class TransactionRecord:
    """거래 이상 탐지용 트랜잭션 DTO."""
    amount: float
    tx_date: date
    counterpart: str = ""     # 상대방 계좌/명칭
    category: str = ""
    description: str = ""
    is_transfer: bool = False  # 계좌이체 여부


# ─────────────────────────────────────────────────────────────
# 1. 보이스피싱 / 스미싱 패턴 탐지
# ─────────────────────────────────────────────────────────────

# 고위험 키워드 그룹 (패턴 / 설명)
_VOICE_PHISHING_PATTERNS: List[Tuple[re.Pattern, str, float]] = [
    (re.compile(r'검찰|경찰청|금감원|금융감독원|국세청|법원'), '기관 사칭', 0.85),
    (re.compile(r'계좌.*동결|동결.*예방|안전계좌|보호계좌'), '안전계좌 유도', 0.90),
    (re.compile(r'범죄.*연루|명의.*도용|사기.*피해자'), '범죄 연루 협박', 0.90),
    (re.compile(r'즉시.*이체|바로.*송금|지금.*입금'), '즉시 이체 강요', 0.80),
    (re.compile(r'대출.*전환|저금리.*대환|기존.*대출.*상환'), '대출 전환 사기', 0.75),
    (re.compile(r'앱.*설치|원격.*제어|팀뷰어|anydesk'), '원격제어 앱 유도', 0.95),
    (re.compile(r'비밀번호.*알려|OTP.*전달|OTP.*알려|인증번호.*말해|인증번호.*알려'), '인증정보 탈취 시도', 0.95),
    (re.compile(r'카드.*배송|택배.*미수령.*결제'), '택배 사기', 0.75),
    (re.compile(r'[0-9]{3,4}-[0-9]{4}-[0-9]{4}.*클릭|http[s]?://[^\s]{5,}.*무료'), '스미싱 URL', 0.85),
    (re.compile(r'정부.*지원금|코로나.*지원|재난.*지원금'), '정부지원금 사칭', 0.80),
    (re.compile(r'투자.*수익률.*[2-9][0-9]%|월.*수익.*[1-9][0-9]%'), '고수익 투자 사기', 0.85),
    (re.compile(r'전화.*끊지|상담원.*연결.*유지'), '통화 유지 강요', 0.75),
]

_SMISHING_PATTERNS: List[Tuple[re.Pattern, str, float]] = [
    (re.compile(r'http[s]?://[a-z0-9\-]{3,15}\.(xyz|top|click|link|site)/'), '의심 단축 도메인', 0.90),
    (re.compile(r'\[.*국민은행.*\]|\[.*카카오.*\]|\[.*금감원.*\]'), '금융기관 사칭 문자', 0.85),
    (re.compile(r'본인확인.*클릭|인증.*링크.*클릭|계좌.*확인.*바랍'), '인증 유도', 0.80),
    (re.compile(r'미환급.*세금|환급.*신청.*클릭'), '세금 환급 사기', 0.85),
    (re.compile(r'당첨.*무료|선물.*수령.*클릭'), '당첨 사기', 0.80),
]


def analyze_voice_phishing(text: str) -> FraudAlert:
    """입력 텍스트(전화 내용/문자)에서 보이스피싱·스미싱 패턴 분석.

    Parameters
    ----------
    text: 분석할 텍스트 (전화 통화 내용, 문자 메시지 등)

    Returns
    -------
    FraudAlert
    """
    text_lower = text.lower()
    matched = []
    max_score = 0.0

    for pattern, desc, score in _VOICE_PHISHING_PATTERNS + _SMISHING_PATTERNS:
        if pattern.search(text):
            matched.append(f'{desc} (위험도 {score:.0%})')
            max_score = max(max_score, score)

    # 복수 패턴 매칭 시 점수 상승
    combined_score = min(1.0, max_score + len(matched) * 0.03)

    if combined_score >= 0.90:
        risk_level = 'critical'
        desc_text = '매우 높은 확률의 사기 시도가 감지되었습니다. 즉시 통화를 끊고 공식 번호로 확인하세요.'
        actions = [
            '즉시 통화/문자 차단',
            '절대 계좌이체·앱설치·인증번호 제공 금지',
            '경찰청 사이버수사대 신고: 182',
            '금융감독원 금융사기 신고: 1332',
            '실제 해당 기관 공식 번호로 직접 확인',
        ]
    elif combined_score >= 0.75:
        risk_level = 'high'
        desc_text = '사기 가능성이 높습니다. 요청에 응하기 전 반드시 공식 채널로 확인하세요.'
        actions = [
            '공식 홈페이지에서 전화번호 확인 후 직접 전화',
            '개인정보 및 금융정보 제공 금지',
            '가족·지인에게 상황 공유',
        ]
    elif combined_score >= 0.50:
        risk_level = 'medium'
        desc_text = '일부 의심 패턴이 감지되었습니다. 주의가 필요합니다.'
        actions = [
            '요청 내용의 진위 공식 확인',
            '즉각적인 금전 요구에 응하지 않기',
        ]
    elif combined_score > 0:
        risk_level = 'low'
        desc_text = '낮은 수준의 의심 패턴이 감지되었습니다.'
        actions = ['요청 내용의 진위 여부 확인 권장']
    else:
        risk_level = 'low'
        combined_score = 0.0
        desc_text = '사기 패턴이 감지되지 않았습니다.'
        actions = []
        matched = []

    return FraudAlert(
        alert_type='voice_phishing',
        risk_level=risk_level,
        score=round(combined_score, 3),
        matched_patterns=matched,
        description=desc_text,
        recommended_actions=actions,
    )


# ─────────────────────────────────────────────────────────────
# 2. 거래 이상 감지
# ─────────────────────────────────────────────────────────────

def detect_abnormal_transactions(
    history: List[TransactionRecord],
    new_tx: TransactionRecord,
    z_threshold: float = 2.5,
) -> FraudAlert:
    """기존 거래 내역 대비 신규 거래의 이상 여부 판정.

    Parameters
    ----------
    history: 과거 거래 내역 (최소 5건 권장)
    new_tx: 검사할 신규 거래
    z_threshold: z-score 임계값 (기본 2.5)
    """
    matched = []
    scores = []

    # ── 1) 금액 이상 탐지 (z-score) ─────────────────────────
    if len(history) >= 5:
        amounts = [tx.amount for tx in history]
        mean_amt = sum(amounts) / len(amounts)
        variance = sum((a - mean_amt) ** 2 for a in amounts) / len(amounts)
        std_amt = variance ** 0.5

        if std_amt > 0:
            z = (new_tx.amount - mean_amt) / std_amt
            if z > z_threshold:
                scores.append(min(0.9, 0.5 + (z - z_threshold) * 0.1))
                matched.append(
                    f'금액 이상: {new_tx.amount:,.0f}원 (평균 {mean_amt:,.0f}원의 {new_tx.amount/mean_amt:.1f}배)'
                )
        elif new_tx.amount > 5_000_000:
            scores.append(0.4)
            matched.append(f'고액 거래: {new_tx.amount:,.0f}원')

    # ── 2) 심야/새벽 고액 이체 탐지 ─────────────────────────
    if new_tx.is_transfer and new_tx.amount >= 1_000_000:
        tx_hour = 0
        if hasattr(new_tx.tx_date, 'hour'):
            tx_hour = new_tx.tx_date.hour
        else:
            now_hour = datetime.now().hour
            tx_hour = now_hour

        if 0 <= tx_hour < 6:
            scores.append(0.65)
            matched.append(f'심야 고액 이체: {new_tx.amount:,.0f}원')

    # ── 3) 동일 상대방 반복 소액 이체 (쪼개기) 탐지 ─────────
    if new_tx.counterpart:
        recent_same = [
            tx for tx in history[-20:]
            if tx.counterpart == new_tx.counterpart and tx.is_transfer
        ]
        if len(recent_same) >= 3:
            total = sum(tx.amount for tx in recent_same) + new_tx.amount
            if total >= 3_000_000:
                scores.append(0.70)
                matched.append(
                    f'동일 계좌 반복 이체 ({len(recent_same)+1}회, 합계 {total:,.0f}원)'
                )

    # ── 4) 처음 거래 상대방 고액 이체 ─────────────────────────
    if new_tx.counterpart and new_tx.is_transfer and new_tx.amount >= 500_000:
        known = {tx.counterpart for tx in history if tx.counterpart}
        if new_tx.counterpart not in known:
            scores.append(0.55)
            matched.append(f'신규 거래 상대방 고액 이체: {new_tx.counterpart}')

    # ── 5) 단기 대규모 현금 인출 ─────────────────────────────
    if new_tx.category in ('현금인출', '출금') and new_tx.amount >= 2_000_000:
        recent_cash = [
            tx for tx in history[-10:]
            if tx.category in ('현금인출', '출금')
        ]
        if recent_cash:
            recent_total = sum(tx.amount for tx in recent_cash) + new_tx.amount
            if recent_total >= 5_000_000:
                scores.append(0.60)
                matched.append(f'단기 대규모 현금 인출: 합계 {recent_total:,.0f}원')

    combined_score = min(1.0, sum(scores) * 0.7 + (max(scores) if scores else 0) * 0.3) if scores else 0.0

    if combined_score >= 0.80:
        risk_level = 'critical'
        desc = '매우 높은 이상 거래 패턴. 즉시 거래를 중단하고 금융기관에 문의하세요.'
        actions = ['금융기관 즉시 연락', '해당 이체 취소 또는 지연 요청', '경찰 신고 112']
    elif combined_score >= 0.60:
        risk_level = 'high'
        desc = '이상 거래 패턴이 감지되었습니다. 거래 전 신중히 확인하세요.'
        actions = ['거래 상대방 신원 재확인', '이체 전 전화 통화로 확인', '금융기관 상담 권장']
    elif combined_score >= 0.40:
        risk_level = 'medium'
        desc = '일부 이상 패턴이 감지되었습니다. 확인 후 진행하세요.'
        actions = ['거래 목적 및 상대방 재확인']
    elif combined_score > 0:
        risk_level = 'low'
        desc = '소규모 이상 패턴이 감지되었습니다.'
        actions = ['거래 내역 주기적 점검 권장']
    else:
        risk_level = 'low'
        desc = '이상 거래 패턴이 감지되지 않았습니다.'
        actions = []

    return FraudAlert(
        alert_type='abnormal_tx',
        risk_level=risk_level,
        score=round(combined_score, 3),
        matched_patterns=matched,
        description=desc,
        recommended_actions=actions,
    )


# ─────────────────────────────────────────────────────────────
# 3. 약탈적 대출·투자 사기 경고
# ─────────────────────────────────────────────────────────────

def check_predatory_loan(
    annual_rate: float,
    requested_amount: float,
    loan_type: str = '',
    upfront_fee_required: bool = False,
    no_credit_check: bool = False,
    promises_guaranteed_return: bool = False,
) -> FraudAlert:
    """대출·투자 상품의 약탈적 특성 여부 검사.

    Parameters
    ----------
    annual_rate: 연이율 (%)
    requested_amount: 대출/투자 요청 금액
    loan_type: 대출 종류 힌트
    upfront_fee_required: 선납 수수료 요구 여부
    no_credit_check: 신용조회 없이 대출 가능 여부
    promises_guaranteed_return: 원금·수익률 보장 약속 여부
    """
    matched = []
    scores = []

    # 법정 최고금리 초과 (2026년 기준: 20%)
    LEGAL_MAX_RATE = 20.0
    if annual_rate > LEGAL_MAX_RATE:
        excess = annual_rate - LEGAL_MAX_RATE
        score = min(1.0, 0.7 + excess * 0.02)
        scores.append(score)
        matched.append(f'법정 최고금리({LEGAL_MAX_RATE}%) 초과: 연 {annual_rate}%')

    # 비정상적 고금리 구간 경고
    elif annual_rate > 15.0:
        scores.append(0.55)
        matched.append(f'고금리 대출: 연 {annual_rate}% (법정 최고금리 접근)')

    # 선납 수수료
    if upfront_fee_required:
        scores.append(0.85)
        matched.append('선납 수수료 요구 (불법 선취 수수료 의심)')

    # 신용조회 없이 대출 가능 사기
    if no_credit_check and annual_rate < 10.0:
        scores.append(0.90)
        matched.append('신용조회 없이 저금리 대출 (사기 가능성 매우 높음)')

    # 원금·수익률 보장 약속 (불법 투자사기)
    if promises_guaranteed_return:
        scores.append(0.92)
        matched.append('원금·수익률 보장 약속 (자본시장법 위반 가능성)')

    # 소액 초고금리 (불법 사채)
    if requested_amount < 1_000_000 and annual_rate > 50.0:
        scores.append(0.95)
        matched.append(f'소액 초고금리 대출: {requested_amount:,.0f}원 @ {annual_rate}% (불법 사채 의심)')

    combined_score = min(1.0, max(scores)) if scores else 0.0

    if combined_score >= 0.85:
        risk_level = 'critical'
        desc = '불법·사기성 금융 상품 가능성이 매우 높습니다. 즉시 거부하고 신고하세요.'
        actions = [
            '절대 계약 체결 금지',
            '금융감독원 신고: 1332',
            '경찰청 신고: 182',
            '금융소비자 정보 포털(파인) 확인: fine.fss.or.kr',
        ]
    elif combined_score >= 0.65:
        risk_level = 'high'
        desc = '위험한 금융 상품 특성이 감지되었습니다. 계약 전 전문가 검토가 필요합니다.'
        actions = [
            '금융감독원 금융상품 조회 (fine.fss.or.kr)',
            '무료 법률상담 (법률구조공단 132)',
            '계약서 충분한 검토 후 결정',
        ]
    elif combined_score >= 0.45:
        risk_level = 'medium'
        desc = '주의가 필요한 금융 상품입니다. 조건을 꼼꼼히 확인하세요.'
        actions = ['금리 비교 사이트에서 동일 조건 비교', '약관 전문 검토']
    elif combined_score > 0:
        risk_level = 'low'
        desc = '일부 주의 사항이 있습니다.'
        actions = ['상품 약관 주의 깊게 확인']
    else:
        risk_level = 'low'
        desc = '특별한 위험 특성이 감지되지 않았습니다.'
        actions = []

    return FraudAlert(
        alert_type='predatory_loan',
        risk_level=risk_level,
        score=round(combined_score, 3),
        matched_patterns=matched,
        description=desc,
        recommended_actions=actions,
    )


# ─────────────────────────────────────────────────────────────
# 4. 종합 리스크 점수 및 요약
# ─────────────────────────────────────────────────────────────

def compute_fraud_risk_summary(alerts: List[FraudAlert]) -> Dict[str, Any]:
    """여러 FraudAlert를 종합하여 최종 리스크 점수와 액션 플랜 반환.

    Parameters
    ----------
    alerts: analyze_voice_phishing / detect_abnormal_transactions /
            check_predatory_loan 결과 목록

    Returns
    -------
    {
      'overall_score': float,        # 0~1
      'overall_risk_level': str,     # low/medium/high/critical
      'top_alert': FraudAlert | None,
      'all_patterns': list[str],
      'all_actions': list[str],
      'summary': str,
      'disclaimer': str,
    }
    """
    if not alerts:
        return {
            'overall_score': 0.0,
            'overall_risk_level': 'low',
            'top_alert': None,
            'all_patterns': [],
            'all_actions': [],
            'summary': '분석된 위험 요소가 없습니다.',
            'disclaimer': '본 분석은 참고용이며 오탐 가능성이 있습니다.',
        }

    scores = [a.score for a in alerts]
    overall_score = min(1.0, max(scores) * 0.7 + sum(scores) / len(scores) * 0.3)
    top_alert = max(alerts, key=lambda a: a.score)

    all_patterns: List[str] = []
    all_actions: List[str] = []
    seen_actions = set()
    for alert in alerts:
        all_patterns.extend(alert.matched_patterns)
        for action in alert.recommended_actions:
            if action not in seen_actions:
                all_actions.append(action)
                seen_actions.add(action)

    _risk_map = {0.90: 'critical', 0.70: 'high', 0.45: 'medium'}
    overall_risk = 'low'
    for threshold, level in sorted(_risk_map.items(), reverse=True):
        if overall_score >= threshold:
            overall_risk = level
            break

    return {
        'overall_score': round(overall_score, 3),
        'overall_risk_level': overall_risk,
        'top_alert': top_alert,
        'all_patterns': all_patterns,
        'all_actions': all_actions,
        'summary': (
            f'종합 위험 점수 {overall_score:.0%} ({overall_risk.upper()}): '
            f'{len(all_patterns)}개 패턴 감지. {top_alert.description}'
        ),
        'disclaimer': (
            '본 분석은 패턴 기반 참고 정보입니다. '
            '실제 피해 발생 또는 의심 시 금융감독원(1332)·경찰청(182)에 신고하세요.'
        ),
    }
