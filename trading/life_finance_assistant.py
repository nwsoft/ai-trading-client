#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 어시스턴트 - 생활금융 통합 모듈
음성/자연어 명령으로 생활금융 기능 제어
"""

import json
import logging
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod

from trading.life_finance import (
    LifeFinanceManager, 
    TransactionType, 
    ExpenseCategory,
    IncomeType,
    ExpenseClassifier,
    FinanceSimulator,
)
from trading.life_finance_products import FinanceProductAdvisor
import trading.tax_calculation_service as tax_svc
from trading.fraud_detection_service import (
    analyze_voice_phishing,
    detect_abnormal_transactions,
    check_predatory_loan,
    FraudAlert,
    TransactionRecord,
)


class FinanceIntentType(Enum):
    """생활금융 대화 의도"""
    # 거래
    ADD_EXPENSE = "add_expense"
    ADD_INCOME = "add_income"
    LIST_TRANSACTIONS = "list_transactions"
    CATEGORY_ANALYSIS = "category_analysis"
    
    # 목표
    CREATE_GOAL = "create_goal"
    UPDATE_GOAL = "update_goal"
    LIST_GOALS = "list_goals"
    GOAL_PROGRESS = "goal_progress"
    
    # 분석
    MONTHLY_REPORT = "monthly_report"
    SPENDING_TREND = "spending_trend"
    BUDGET_ALERT = "budget_alert"
    
    # 시뮬레이션
    SCENARIO_ANALYSIS = "scenario_analysis"
    SAVINGS_PROJECTION = "savings_projection"

    # 금융상품 비교
    COMPARE_LOAN = "compare_loan"
    COMPARE_INSURANCE = "compare_insurance"
    COMPARE_SAVINGS_PRODUCT = "compare_savings_product"

    # 세무 계산
    TAX_SETTLEMENT = "tax_settlement"
    CHECK_FINANCIAL_INCOME_TAX = "check_financial_income_tax"
    CALC_INVESTMENT_TAX = "calc_investment_tax"
    COMPARE_TAX_ACCOUNTS = "compare_tax_accounts"

    # 금융 이상 탐지
    ANALYZE_FRAUD_MESSAGE = "analyze_fraud_message"
    DETECT_ABNORMAL_TX = "detect_abnormal_tx"
    CHECK_PREDATORY_LOAN = "check_predatory_loan"
    
    # 제안
    SPENDING_ADVICE = "spending_advice"
    SAVINGS_ADVICE = "savings_advice"
    GOAL_RECOMMENDATION = "goal_recommendation"
    
    # 기타
    DASHBOARD = "dashboard"
    HELP = "help"
    GENERAL_QUESTION = "general_question"


@dataclass
class FinanceContext:
    """생활금융 컨텍스트"""
    intent: FinanceIntentType
    extracted_amount: Optional[float] = None
    extracted_date: Optional[date] = None
    extracted_category: Optional[str] = None
    extracted_description: Optional[str] = None
    extracted_goal_name: Optional[str] = None
    confidence: float = 0.0
    raw_input: str = ""
    credit_score: Optional[str] = None  # Phase 1: 신용도 ("좋음 (750~900)" | "보통 (650~750)" | "낮음 (~650)")
    risk_level: Optional[str] = None    # Phase 1: 위험도 ("회피형" | "보수형" | "공격형")
    
    def to_dict(self) -> dict:
        return {
            'intent': self.intent.value,
            'amount': self.extracted_amount,
            'date': self.extracted_date.isoformat() if self.extracted_date else None,
            'category': self.extracted_category,
            'description': self.extracted_description,
            'goal_name': self.extracted_goal_name,
            'confidence': self.confidence,
            'credit_score': self.credit_score,
            'risk_level': self.risk_level,
        }


class FinanceIntentParser:
    """자연어 → 금융 의도 파싱"""
    
    # 의도별 키워드
    INTENT_KEYWORDS = {
        FinanceIntentType.ADD_EXPENSE: [
            '썼어', '지출', '사용', '구매', '샀', '돈', '결제', '매가', '낸',
            '비용', '경비', '소비', '지르다', '썰', '비용 들었어',
        ],
        FinanceIntentType.ADD_INCOME: [
            '받았어', '수입', '급여', '입금', '번', '소득', '얻었', '수령',
            '보너스', '월급', '급여일', '들어왔',
        ],
        FinanceIntentType.LIST_TRANSACTIONS: [
            '거래', '거래 내역', '지출 내역', '최근 거래', '기록', '내역',
            '조회', '확인', '살펴봐', '어떻게', '얼마',
        ],
        FinanceIntentType.MONTHLY_REPORT: [
            '월간 리포트', '월간 리포', '이달', '이번 달', '지난달', '월간',
            '월간 정리', '월간 요약', '한달', '한달간', '이번 한달',
        ],
        FinanceIntentType.CREATE_GOAL: [
            '목표', '목표 설정', '목표 만들', '저축 목표', '목표 생성',
            '계획', '저축 계획', '목표 추가',
        ],
        FinanceIntentType.LIST_GOALS: [
            '목표 확인', '목표 조회', '목표들', '진행 중인 목표', '현재 목표',
            '어떤 목표', '목표가 뭐', '목표 현황',
        ],
        FinanceIntentType.GOAL_PROGRESS: [
            '진행 상황', '진행률', '현황', '얼마나', '목표 진행', '달성률',
            '남은 금액', '목표까지', '이제 남은',
        ],
        FinanceIntentType.SPENDING_TREND: [
            '추이', '트렌드', '변화', '증감', '지출 추세', '지출 변화',
            '점점', '줄었어', '늘었어',
        ],
        FinanceIntentType.SPENDING_ADVICE: [
            '조언', '제안', '추천', '어떻게 줄일', '절약', '효율', '개선',
            '팁', '팁 줄게', '어떻게 할',
        ],
        FinanceIntentType.DASHBOARD: [
            '대시보드', '대시보',  '요약', '한눈에', '전체 현황', '현황',
            '전체 보기', '전체 조회',
        ],
        FinanceIntentType.COMPARE_LOAN: [
            '대출', '대출 비교', '대출 상품', '금리 비교', '대출 추천',
        ],
        FinanceIntentType.COMPARE_INSURANCE: [
            '보험', '보험 비교', '보험 상품', '보장 비교', '보험 추천',
        ],
        FinanceIntentType.COMPARE_SAVINGS_PRODUCT: [
            '예금', '적금', '예적금', '저축 상품', '금리 높은 예금', '적금 추천',
        ],
        FinanceIntentType.TAX_SETTLEMENT: [
            '연말정산', '환급금', '세금 계산', '연말 정산', '소득공제', '세액공제', '세금 얼마',
        ],
        FinanceIntentType.CHECK_FINANCIAL_INCOME_TAX: [
            '금융소득종합과세', '금융소득 종합과세', '이자 배당', '종합과세 해당', '이자소득세',
        ],
        FinanceIntentType.CALC_INVESTMENT_TAX: [
            '금투세', '금융투자소득세', '주식 세금', '투자 세금', '해외주식 세금',
        ],
        FinanceIntentType.COMPARE_TAX_ACCOUNTS: [
            'isa', 'irp', '연금저축', '절세 계좌', '세금 절약', '절세 비교', '절세 방법',
        ],
        FinanceIntentType.ANALYZE_FRAUD_MESSAGE: [
            '사기 문자', '보이스피싱', '스미싱', '사기 전화', '문자 사기', '이 문자', '사기인지',
            '피싱', '의심 문자', '의심 전화',
        ],
        FinanceIntentType.DETECT_ABNORMAL_TX: [
            '이상 거래', '이상한 거래', '이상 이체', '수상한 거래', '거래 이상', '이상 탐지',
        ],
        FinanceIntentType.CHECK_PREDATORY_LOAN: [
            '불법 대출', '약탈적 대출', '고금리 대출', '불법 금리', '대출 사기', '이 대출 괜찮',
        ],
    }
    
    AMOUNT_PATTERNS = [
        r'(\d+(?:,\d{3})*)\s*(?:원|만원|천원|백만원)',
        r'(\d+)\s*만\s*원',
        r'(\d+(?:\.\d+)?)\s*만',
    ]
    
    DATE_PATTERNS = [
        r'(?:어제|yesterday)',
        r'(?:오늘|today)',
        r'(?:내일|tomorrow)',
        r'(\d+)\s*(?:일|일 전|day ago)',
        r'(?:이번주|this week)',
        r'(?:지난주|last week)',
    ]
    
    CATEGORY_KEYWORDS = {
        '식비': ['식당', '카페', '커피', '밥', '점심', '저녁', '마트', '식료품'],
        '교통비': ['지하철', '버스', '택시', '차', '휘발유', '기름'],
        '주거비': ['월세', '전세', '전기', '수도', '가스', '인터넷'],
        '문화생활': ['영화', '공연', '음악', '게임', '스포츠'],
        '쇼핑': ['옷', '신발', '백화점', '옷가게'],
        '건강/의료': ['병원', '약국', '헬스', '피트니스'],
        '교육': ['학원', '교재', '책', '강의'],
        '금융': ['수수료', '보험료', '보험', '이자'],
        '구독': ['구독', '월간', '정기'],
    }
    
    @classmethod
    def parse(cls, user_input: str) -> FinanceContext:
        """사용자 입력 파싱"""
        text_lower = user_input.lower()

        # 개체 추출
        amount = cls._extract_amount(user_input)
        parsed_date = cls._extract_date(text_lower)
        category = cls._extract_category(text_lower)
        description = user_input

        # 의도 분석
        intent = cls._detect_intent(text_lower, amount)
        
        # 신뢰도 계산
        confidence = cls._calculate_confidence(intent, amount, category)
        
        return FinanceContext(
            intent=intent,
            extracted_amount=amount,
            extracted_date=parsed_date or date.today(),
            extracted_category=category,
            extracted_description=description,
            confidence=confidence,
            raw_input=user_input,
        )
    
    @classmethod
    def _detect_intent(cls, text_lower: str, amount: Optional[float] = None) -> FinanceIntentType:
        """의도 감지"""
        # 1) 의문형/요청형 우선 규칙 (충돌 방지)
        if any(k in text_lower for k in ['이번 달', '이달', '월간', '지난달']) and any(
            k in text_lower for k in ['리포트', '보고서', '요약', '얼마']
        ):
            return FinanceIntentType.MONTHLY_REPORT

        if any(k in text_lower for k in ['목표', 'goal']) and any(
            k in text_lower for k in ['뭐', '조회', '확인', '목록', '현황', '보여']
        ):
            if any(k in text_lower for k in ['진행', '달성', '남은']):
                return FinanceIntentType.GOAL_PROGRESS
            return FinanceIntentType.LIST_GOALS

        # 금융 이상 탐지 의도 (대출 비교보다 먼저 체크)
        if any(k in text_lower for k in ['보이스피싱', '스미싱', '사기 문자', '사기 전화', '이 문자', '사기인지', '피싱', '의심 문자', '의심 전화']):
            return FinanceIntentType.ANALYZE_FRAUD_MESSAGE
        if any(k in text_lower for k in ['이상 거래', '이상한 거래', '이상 이체', '수상한 거래', '거래 이상', '이상 탐지']):
            return FinanceIntentType.DETECT_ABNORMAL_TX
        if any(k in text_lower for k in ['불법 대출', '약탈적 대출', '고금리 대출', '대출 사기']) or \
                ('이 대출' in text_lower and '괜찮' in text_lower):
            return FinanceIntentType.CHECK_PREDATORY_LOAN

        # 금융상품 비교 의도 우선
        if '대출' in text_lower and not (
            any(k in text_lower for k in ['불법', '약탈', '대출 사기', '고금리 대출']) or
            ('이 대출' in text_lower and '괜찮' in text_lower)
        ):
            return FinanceIntentType.COMPARE_LOAN
        if '보험' in text_lower:
            return FinanceIntentType.COMPARE_INSURANCE
        if any(k in text_lower for k in ['예금', '적금', '예적금']):
            return FinanceIntentType.COMPARE_SAVINGS_PRODUCT

        # 세무 계산 의도
        if any(k in text_lower for k in ['연말정산', '환급금', '세액공제', '소득공제', '세금 계산', '세금 얼마']):
            return FinanceIntentType.TAX_SETTLEMENT
        if any(k in text_lower for k in ['금융소득종합과세', '금융소득 종합과세', '이자 배당', '종합과세']):
            return FinanceIntentType.CHECK_FINANCIAL_INCOME_TAX
        if any(k in text_lower for k in ['금투세', '금융투자소득세', '주식 세금', '투자 세금', '해외주식 세금']):
            return FinanceIntentType.CALC_INVESTMENT_TAX
        if any(k in text_lower for k in ['isa', 'irp', '연금저축', '절세 계좌', '절세 비교', '절세 방법', '절세']):
            return FinanceIntentType.COMPARE_TAX_ACCOUNTS

        if any(k in text_lower for k in ['어떻게', '절약', '조언', '추천', '팁']):
            return FinanceIntentType.SPENDING_ADVICE

        scores = {}

        for intent, keywords in cls.INTENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[intent] = score

        if not scores:
            # 금액 + 수입/지출 표현 조합 폴백
            if amount:
                if any(k in text_lower for k in ['받았', '수입', '급여', '월급', '입금', '보너스']):
                    return FinanceIntentType.ADD_INCOME
                if any(k in text_lower for k in ['썼', '지출', '결제', '구매', '냈', '사용']):
                    return FinanceIntentType.ADD_EXPENSE
            return FinanceIntentType.GENERAL_QUESTION

        # 2) 목표 생성은 '금액' + 생성형 동사일 때만 우선
        if amount and any(k in text_lower for k in ['목표', '저축']) and any(
            k in text_lower for k in ['만들', '생성', '설정', '추가']
        ):
            return FinanceIntentType.CREATE_GOAL

        return max(scores, key=scores.get)
    
    @classmethod
    def _extract_amount(cls, text: str) -> Optional[float]:
        """금액 추출"""
        normalized = text.replace(',', '')

        # 1) '5천원', '12.5만', '3억' 등 단위 포함 포맷
        unit_match = re.search(r'(\d+(?:\.\d+)?)\s*(천|만|억)\s*원?', normalized)
        if unit_match:
            number = float(unit_match.group(1))
            unit = unit_match.group(2)
            multiplier = {'천': 1_000, '만': 10_000, '억': 100_000_000}.get(unit, 1)
            return int(number * multiplier)

        # 2) '3500000원' 같은 원 단위 금액
        won_match = re.search(r'(\d+(?:\.\d+)?)\s*원', normalized)
        if won_match:
            return int(float(won_match.group(1)))

        # 3) 기존 패턴 폴백
        for pattern in cls.AMOUNT_PATTERNS:
            match = re.search(pattern, normalized)
            if not match:
                continue
            amount_str = match.group(1).replace(',', '')
            try:
                amount = float(amount_str)
                if '만' in normalized[match.start():match.end()] and amount < 10000:
                    amount *= 10000
                return int(amount)
            except ValueError:
                continue

        return None
    
    @classmethod
    def _extract_date(cls, text_lower: str) -> Optional[date]:
        """날짜 추출"""
        today = date.today()
        
        if '어제' in text_lower or 'yesterday' in text_lower:
            return today - timedelta(days=1)
        elif '오늘' in text_lower or 'today' in text_lower:
            return today
        elif '내일' in text_lower or 'tomorrow' in text_lower:
            return today + timedelta(days=1)
        
        # N일 전
        match = re.search(r'(\d+)\s*일\s*전', text_lower)
        if match:
            days = int(match.group(1))
            return today - timedelta(days=days)
        
        return None
    
    @classmethod
    def _extract_category(cls, text_lower: str) -> Optional[str]:
        """카테고리 추출"""
        for category, keywords in cls.CATEGORY_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return category
        return None
    
    @classmethod
    def _calculate_confidence(
        cls, 
        intent: FinanceIntentType, 
        amount: Optional[float],
        category: Optional[str],
    ) -> float:
        """신뢰도 계산"""
        confidence = 0.5  # 기본값
        
        # 의도가 명확하면 상향
        if intent != FinanceIntentType.GENERAL_QUESTION:
            confidence += 0.2
        
        # 금액이 있으면 상향
        if amount:
            confidence += 0.15
        
        # 카테고리가 있으면 상향
        if category:
            confidence += 0.15
        
        return min(confidence, 1.0)


class LifeFinanceAssistant:
    """생활금융 AI 어시스턴트"""
    
    def __init__(self, manager: LifeFinanceManager, logger: Optional[logging.Logger] = None):
        self.manager = manager
        self.logger = logger or logging.getLogger(__name__)
        self.parser = FinanceIntentParser()
        self.product_advisor = FinanceProductAdvisor()
        self.command_history = []
    
    async def process_command(self, user_input: str, credit_score: Optional[str] = None, risk_level: Optional[str] = None) -> Dict[str, Any]:
        """
        사용자 명령 처리 (음성/자연어)
        
        Args:
            user_input: 사용자 입력
            credit_score: Phase 1 신용도 (선택)
            risk_level: Phase 1 위험도 (선택)
        
        Returns:
            {
                'response': 응답 텍스트,
                'intent': 의도,
                'action_taken': 실행된 액션,
                'data': 반환 데이터,
                'requires_confirmation': 확인 필요 여부,
            }
        """
        try:
            # 1. 의도 파싱
            context = self.parser.parse(user_input)
            
            # Phase 1: 신용도/위험도 추가
            context.credit_score = credit_score
            context.risk_level = risk_level
            
            # 2. 명령 실행
            result = await self._execute_intent(context)
            
            # 3. 이력 저장
            self.command_history.append({
                'input': user_input,
                'intent': context.intent.value,
                'timestamp': datetime.now().isoformat(),
            })
            
            return result
            
        except Exception as e:
            self.logger.error(f"명령 처리 오류: {e}")
            return {
                'response': f"죄송합니다. 처리 중 오류가 발생했습니다: {str(e)}",
                'intent': 'error',
                'action_taken': None,
                'data': None,
                'requires_confirmation': False,
            }
    
    async def _execute_intent(self, context: FinanceContext) -> Dict[str, Any]:
        """의도에 따른 액션 실행"""
        intent = context.intent
        
        # 거래 관련
        if intent == FinanceIntentType.ADD_EXPENSE:
            return self._handle_add_expense(context)
        elif intent == FinanceIntentType.ADD_INCOME:
            return self._handle_add_income(context)
        elif intent == FinanceIntentType.LIST_TRANSACTIONS:
            return self._handle_list_transactions(context)
        elif intent == FinanceIntentType.CATEGORY_ANALYSIS:
            return self._handle_category_analysis(context)
        
        # 목표 관련
        elif intent == FinanceIntentType.CREATE_GOAL:
            return self._handle_create_goal(context)
        elif intent == FinanceIntentType.LIST_GOALS:
            return self._handle_list_goals(context)
        elif intent == FinanceIntentType.GOAL_PROGRESS:
            return self._handle_goal_progress(context)
        
        # 분석 관련
        elif intent == FinanceIntentType.MONTHLY_REPORT:
            return self._handle_monthly_report(context)
        elif intent == FinanceIntentType.SPENDING_TREND:
            return self._handle_spending_trend(context)

        # 금융상품 비교
        elif intent == FinanceIntentType.COMPARE_LOAN:
            return self._handle_compare_loan(context)
        elif intent == FinanceIntentType.COMPARE_INSURANCE:
            return self._handle_compare_insurance(context)
        elif intent == FinanceIntentType.COMPARE_SAVINGS_PRODUCT:
            return self._handle_compare_savings_product(context)

        # 세무 계산
        elif intent == FinanceIntentType.TAX_SETTLEMENT:
            return self._handle_tax_settlement(context)
        elif intent == FinanceIntentType.CHECK_FINANCIAL_INCOME_TAX:
            return self._handle_check_financial_income_tax(context)
        elif intent == FinanceIntentType.CALC_INVESTMENT_TAX:
            return self._handle_calc_investment_tax(context)
        elif intent == FinanceIntentType.COMPARE_TAX_ACCOUNTS:
            return self._handle_compare_tax_accounts(context)

        # 금융 이상 탐지
        elif intent == FinanceIntentType.ANALYZE_FRAUD_MESSAGE:
            return self._handle_analyze_fraud_message(context)
        elif intent == FinanceIntentType.DETECT_ABNORMAL_TX:
            return self._handle_detect_abnormal_tx(context)
        elif intent == FinanceIntentType.CHECK_PREDATORY_LOAN:
            return self._handle_check_predatory_loan(context)
        
        # 조언 관련
        elif intent == FinanceIntentType.SPENDING_ADVICE:
            return self._handle_spending_advice(context)
        elif intent == FinanceIntentType.SAVINGS_ADVICE:
            return self._handle_savings_advice(context)
        
        # 대시보드
        elif intent == FinanceIntentType.DASHBOARD:
            return self._handle_dashboard(context)
        
        else:
            return self._handle_general_question(context)
    
    # ========== 거래 핸들러 ==========
    
    def _handle_add_expense(self, context: FinanceContext) -> Dict[str, Any]:
        """지출 추가"""
        if not context.extracted_amount:
            return {
                'response': "금액을 말씀해주세요. 예: '카페에서 5000원 썼어'",
                'intent': context.intent.value,
                'action_taken': None,
                'data': None,
                'requires_confirmation': False,
            }
        
        # 거래 추가
        tx = self.manager.add_transaction(
            date=context.extracted_date or date.today(),
            amount=context.extracted_amount,
            type_=TransactionType.EXPENSE,
            description=context.extracted_description or f"{context.extracted_amount:,}원 지출",
            auto_classify=True,
        )
        
        response = (
            f"✓ 지출 {tx.amount:,}원을 등록했습니다.\n"
            f"분류: {tx.category} (신뢰도: {tx.ai_confidence*100:.0f}%)\n"
            f"메모: {tx.description}"
        )
        
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': 'add_expense',
            'data': tx.to_dict(),
            'requires_confirmation': False,
        }
    
    def _handle_add_income(self, context: FinanceContext) -> Dict[str, Any]:
        """수입 추가"""
        if not context.extracted_amount:
            return {
                'response': "금액을 말씀해주세요. 예: '급여로 350만원 받았어'",
                'intent': context.intent.value,
                'action_taken': None,
                'data': None,
                'requires_confirmation': False,
            }
        
        tx = self.manager.add_transaction(
            date=context.extracted_date or date.today(),
            amount=context.extracted_amount,
            type_=TransactionType.INCOME,
            description=context.extracted_description or f"{context.extracted_amount:,}원 수입",
            category="기타",
            auto_classify=False,
        )
        
        response = (
            f"✓ 수입 {tx.amount:,}원을 등록했습니다.\n"
            f"분류: {tx.category}\n"
            f"메모: {tx.description}"
        )
        
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': 'add_income',
            'data': tx.to_dict(),
            'requires_confirmation': False,
        }
    
    def _handle_list_transactions(self, context: FinanceContext) -> Dict[str, Any]:
        """거래 내역 조회"""
        # 최근 7일 거래
        start_date = date.today() - timedelta(days=7)
        txs = self.manager.get_transactions(start_date=start_date)
        
        if not txs:
            return {
                'response': "지난 7일간 거래 내역이 없습니다.",
                'intent': context.intent.value,
                'action_taken': None,
                'data': None,
                'requires_confirmation': False,
            }
        
        # 응답 작성
        lines = ["📋 최근 7일 거래 내역:\n"]
        for tx in txs[:10]:  # 최근 10개
            icon = "💰" if tx.type == TransactionType.INCOME else "💸"
            sign = "+" if tx.type == TransactionType.INCOME else "-"
            lines.append(
                f"{icon} {tx.date} | {sign}{tx.amount:,}원 | {tx.category} | {tx.description}"
            )
        
        response = "\n".join(lines)
        
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': None,
            'data': [tx.to_dict() for tx in txs],
            'requires_confirmation': False,
        }
    
    def _handle_category_analysis(self, context: FinanceContext) -> Dict[str, Any]:
        """카테고리별 분석"""
        today = date.today()
        month_start = date(today.year, today.month, 1)
        
        stats = self.manager.get_category_stats(start_date=month_start)

        if not stats:
            return {
                'response': "이번 달 지출 데이터가 아직 없습니다.",
                'intent': context.intent.value,
                'action_taken': None,
                'data': {},
                'requires_confirmation': False,
            }
        
        lines = ["📊 이번 달 카테고리별 지출:\n"]
        for category, data in stats.items():
            percentage = (data['total'] / sum(s['total'] for s in stats.values())) * 100
            lines.append(
                f"• {category}: {data['total']:,}원 ({percentage:.1f}%) - "
                f"평균 {data['avg']:,.0f}원 × {data['count']}회"
            )
        
        response = "\n".join(lines)
        
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': None,
            'data': stats,
            'requires_confirmation': False,
        }
    
    # ========== 목표 핸들러 ==========
    
    def _handle_create_goal(self, context: FinanceContext) -> Dict[str, Any]:
        """목표 생성"""
        if not context.extracted_amount:
            return {
                'response': "목표 금액을 말씀해주세요. 예: '여름 휴가 200만원 목표'",
                'intent': context.intent.value,
                'action_taken': None,
                'data': None,
                'requires_confirmation': False,
            }
        
        # 목표명 추출
        goal_name = context.extracted_description or f"{context.extracted_amount:,}원 저축"
        
        goal = self.manager.add_goal(
            name=goal_name,
            target_amount=context.extracted_amount,
            deadline=context.extracted_date,
            category="기타",
            priority="중간",
        )
        
        response = (
            f"✓ 목표 '{goal.name}'을 생성했습니다.\n"
            f"목표 금액: {goal.target_amount:,}원\n"
            f"마감: {goal.deadline or '없음'}"
        )
        
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': 'create_goal',
            'data': goal.to_dict(),
            'requires_confirmation': False,
        }
    
    def _handle_list_goals(self, context: FinanceContext) -> Dict[str, Any]:
        """목표 목록 조회"""
        goals = self.manager.get_goals()
        
        if not goals:
            return {
                'response': "설정된 목표가 없습니다. '여름 휴가 200만원' 같이 말씀해주세요.",
                'intent': context.intent.value,
                'action_taken': None,
                'data': None,
                'requires_confirmation': False,
            }
        
        lines = ["🎯 진행 중인 목표:\n"]
        for goal in goals:
            if goal.is_completed:
                continue
            progress_bar = self._create_progress_bar(goal.progress_rate)
            deadline_str = f"({goal.days_until_deadline}일 남음)" if goal.days_until_deadline else ""
            lines.append(
                f"• {goal.name}\n"
                f"  {goal.current_amount:,}원 / {goal.target_amount:,}원 {progress_bar}\n"
                f"  진행률: {goal.progress_rate:.1f}% {deadline_str}"
            )
        
        response = "\n".join(lines)
        
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': None,
            'data': [g.to_dict() for g in goals],
            'requires_confirmation': False,
        }
    
    def _handle_goal_progress(self, context: FinanceContext) -> Dict[str, Any]:
        """목표 진행률 조회"""
        goals = self.manager.get_goals(completed=False)
        
        if not goals:
            return {
                'response': "진행 중인 목표가 없습니다.",
                'intent': context.intent.value,
                'action_taken': None,
                'data': None,
                'requires_confirmation': False,
            }
        
        lines = ["📈 목표 진행 현황:\n"]
        for goal in goals:
            monthly_target = goal.monthly_target if goal.monthly_target else 0
            lines.append(
                f"🎯 {goal.name}\n"
                f"   달성: {goal.progress_rate:.1f}%\n"
                f"   남은 금액: {goal.remaining_amount:,}원\n"
                f"   월간 목표: {monthly_target:,.0f}원 (마감까지)"
            )
        
        response = "\n".join(lines)
        
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': None,
            'data': [g.to_dict() for g in goals],
            'requires_confirmation': False,
        }
    
    # ========== 분석 핸들러 ==========
    
    def _handle_monthly_report(self, context: FinanceContext) -> Dict[str, Any]:
        """월간 리포트"""
        today = date.today()
        report = self.manager.get_monthly_report(today.year, today.month)
        
        lines = [
            f"📊 {report.date_str} 월간 재무 보고서\n",
            f"💰 수입: {report.total_income:,}원",
            f"💸 지출: {report.total_expense:,}원",
            f"💎 저축: {report.net_savings:,}원",
            f"📈 저축률: {report.savings_rate:.1f}%",
        ]
        
        if report.category_breakdown:
            lines.append("\n💳 주요 지출:\n")
            for cat, amount in sorted(report.category_breakdown.items(), 
                                     key=lambda x: x[1], reverse=True)[:5]:
                lines.append(f"• {cat}: {amount:,}원")
        
        response = "\n".join(lines)
        
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': None,
            'data': report.to_dict(),
            'requires_confirmation': False,
        }
    
    def _handle_spending_trend(self, context: FinanceContext) -> Dict[str, Any]:
        """지출 추세"""
        trend = self.manager.get_spending_trend(months=6)
        
        lines = ["📉 최근 6개월 지출 추세:\n"]
        
        # 간단한 그래프
        max_amount = max(trend.values()) if trend else 0
        for month, amount in trend.items():
            if max_amount > 0:
                bar_length = int((amount / max_amount) * 20)
                bar = "█" * bar_length
            else:
                bar = ""
            lines.append(f"{month}: {bar} {amount:,}원")
        
        response = "\n".join(lines)
        
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': None,
            'data': trend,
            'requires_confirmation': False,
        }
    
    # ========== 조언 핸들러 ==========
    
    def _handle_spending_advice(self, context: FinanceContext) -> Dict[str, Any]:
        """지출 절약 조언"""
        today = date.today()
        month_start = date(today.year, today.month, 1)
        
        stats = self.manager.get_category_stats(start_date=month_start)
        report = self.manager.get_monthly_report(today.year, today.month)
        
        lines = ["💡 지출 절약 조언:\n"]
        
        # 상위 지출 카테고리
        top_categories = sorted(stats.items(), key=lambda x: x[1]['total'], reverse=True)[:3]
        
        if top_categories:
            lines.append("가장 큰 지출 항목:")
            for category, data in top_categories:
                lines.append(f"• {category}: {data['total']:,}원")
                
                # 카테고리별 조언
                advice = self._get_category_advice(category)
                if advice:
                    lines.append(f"  💡 {advice}")
        
        # 저축률 조언
        if report.savings_rate < 10:
            lines.append("\n⚠️ 저축률이 낮습니다. 월간 목표 저축률은 20-30%입니다.")
        elif report.savings_rate > 50:
            lines.append("\n✨ 훌륭한 저축 습관을 유지하고 있습니다!")
        
        response = "\n".join(lines)
        
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': None,
            'data': None,
            'requires_confirmation': False,
        }
    
    def _handle_savings_advice(self, context: FinanceContext) -> Dict[str, Any]:
        """저축 조언"""
        goals = self.manager.get_goals(completed=False)
        today = date.today()
        
        lines = ["💡 저축 최적화 조언:\n"]
        
        if not goals:
            lines.append("• 먼저 저축 목표를 설정해보세요.")
            lines.append("• 예: '새차 구입 3000만원 1년 안에'")
        else:
            # 목표별 조언
            for goal in sorted(goals, key=lambda g: g.days_until_deadline or 365)[:3]:
                if goal.monthly_target:
                    lines.append(f"🎯 {goal.name}")
                    lines.append(f"   월간 저축 목표: {goal.monthly_target:,.0f}원")
                    if goal.days_until_deadline and goal.days_until_deadline < 30:
                        lines.append(f"   ⏰ {goal.days_until_deadline}일 남았습니다!")
        
        response = "\n".join(lines)
        
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': None,
            'data': None,
            'requires_confirmation': False,
        }
    
    # ========== 대시보드 ==========
    
    def _handle_dashboard(self, context: FinanceContext) -> Dict[str, Any]:
        """종합 대시보드"""
        summary = self.manager.get_dashboard_summary()
        
        lines = ["📱 생활금융 대시보드\n"]
        lines.append(f"이번 달 수입: {summary['this_month']['total_income']:,}원")
        lines.append(f"이번 달 지출: {summary['this_month']['total_expense']:,}원")
        lines.append(f"이번 달 저축: {summary['this_month']['net_savings']:,}원")
        lines.append(f"저축률: {summary['this_month']['savings_rate']:.1f}%")
        
        if summary['goals']['active_count'] > 0:
            lines.append(f"\n🎯 활성 목표: {summary['goals']['active_count']}개")
            lines.append(f"완료 목표: {summary['goals']['completed_count']}개")
        
        response = "\n".join(lines)
        
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': None,
            'data': summary,
            'requires_confirmation': False,
        }

    # ========== 금융상품 핸들러 ==========

    def _handle_compare_loan(self, context: FinanceContext) -> Dict[str, Any]:
        amount = context.extracted_amount if context.extracted_amount else 100000000
        result = self.product_advisor.compare_loans(amount=float(amount), term_months=24)
        
        # Phase 1: 신용도 기반 조정 적용
        if context.credit_score:
            result = self.product_advisor.apply_credit_adjustment_to_loans(result, context.credit_score)
        
        best = result['best']
        
        # 신용도가 있으면 추가 설명
        credit_info = ""
        if context.credit_score:
            credit_label = self._format_credit_label(context.credit_score)
            adjusted_rate = best.get('adjusted_annual_rate', best['annual_rate'])
            credit_info = f"\n💡 당신의 신용도({credit_label})를 반영한 예상 금리: {adjusted_rate:.2f}%"

        response = (
            "🏦 대출 상품 비교 결과\n"
            f"추천: {best['provider']} {best['name']}\n"
            f"금리: 연 {best['annual_rate']:.2f}%\n"
            f"예상 총비용(24개월): {best['total_cost']:,.0f}원\n"
            f"요약: {result['summary']}"
            f"{credit_info}"
        )
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': 'compare_loan',
            'data': result,
            'requires_confirmation': False,
        }

    def _handle_compare_insurance(self, context: FinanceContext) -> Dict[str, Any]:
        budget = context.extracted_amount if context.extracted_amount else 70000
        result = self.product_advisor.compare_insurances(budget_monthly=float(budget))
        best = result['best']

        response = (
            "🛡️ 보험 상품 비교 결과\n"
            f"추천: {best['provider']} {best['name']}\n"
            f"월 보험료: {best['monthly_premium']:,.0f}원\n"
            f"보장 점수: {best['coverage_score']:.1f}\n"
            f"요약: {result['summary']}"
        )
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': 'compare_insurance',
            'data': result,
            'requires_confirmation': False,
        }

    def _handle_compare_savings_product(self, context: FinanceContext) -> Dict[str, Any]:
        principal = context.extracted_amount if context.extracted_amount else 5000000
        result = self.product_advisor.compare_savings(principal=float(principal), term_months=12)
        
        # Phase 1: 신용도 기반 조정 적용
        if context.credit_score:
            result = self.product_advisor.apply_credit_adjustment_to_savings(result, context.credit_score)
        
        best = result['best']
        
        # 신용도가 있으면 추가 설명
        credit_info = ""
        if context.credit_score:
            credit_label = self._format_credit_label(context.credit_score)
            adjusted_rate = best.get('adjusted_annual_rate', best['annual_rate'])
            credit_info = f"\n💡 당신의 신용도({credit_label})를 반영한 예상 금리: {adjusted_rate:.2f}%"

        tax_note = "비과세" if best['tax_free'] else "일반과세"
        response = (
            "💳 예적금 상품 비교 결과\n"
            f"추천: {best['provider']} {best['name']}\n"
            f"금리: 연 {best['annual_rate']:.2f}% ({tax_note})\n"
            f"예상 이자(12개월): {best['expected_interest']:,.0f}원\n"
            f"요약: {result['summary']}"
            f"{credit_info}"
        )
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': 'compare_savings_product',
            'data': result,
            'requires_confirmation': False,
        }
    
    # ========== 세무 계산 핸들러 ==========

    def _handle_tax_settlement(self, context: FinanceContext) -> Dict[str, Any]:
        """연말정산 계산 (기본값 안내 후 계산)"""
        salary = context.extracted_amount or 50_000_000
        result = tax_svc.calc_year_end_tax_settlement(
            annual_salary=salary,
        )
        final = result.get('final_tax', 0)
        refund_flag = "환급 예상" if final < 0 else "납부 예상"
        tips = result.get('optimization_tips', [])
        tip_text = "\n".join(f"  • {t}" for t in tips[:3]) if tips else "  • 공제 항목을 입력하면 더 정확한 계산이 됩니다."
        response = (
            f"🧾 연말정산 계산 결과\n"
            f"연봉: {salary:,.0f}원 기준\n"
            f"최종 세액: {abs(final):,.0f}원 {refund_flag}\n\n"
            f"💡 절세 팁:\n{tip_text}\n\n"
            f"※ 의료비·카드·교육비·기부금 등 공제 항목을 알려주시면\n"
            f"  더 정확한 연말정산 계산을 해드립니다."
        )
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': 'tax_settlement',
            'data': result,
            'requires_confirmation': False,
        }

    def _handle_check_financial_income_tax(self, context: FinanceContext) -> Dict[str, Any]:
        """금융소득종합과세 판정"""
        # 금액이 입력되면 이자 소득으로 간주
        income = context.extracted_amount or 0
        result = tax_svc.check_financial_income_comprehensive_tax(
            interest_income=income,
            dividend_income=0,
            annual_salary=0,
        )
        required = result.get('comprehensive_tax_required', False)
        total = result.get('total_financial_income', income)
        threshold = result.get('threshold', 20_000_000)
        status = "⚠️ 종합과세 대상입니다." if required else "✅ 종합과세 대상이 아닙니다."
        response = (
            f"💰 금융소득종합과세 판정\n"
            f"금융소득 합계: {total:,.0f}원\n"
            f"기준: {threshold:,.0f}원 초과 시 종합과세\n"
            f"{status}\n\n"
            f"이자·배당 금액을 알려주시면 정확한 판정이 됩니다.\n"
            f"예: '이자 1000만원 배당 500만원 종합과세 확인'"
        )
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': 'check_financial_income_tax',
            'data': result,
            'requires_confirmation': False,
        }

    def _handle_calc_investment_tax(self, context: FinanceContext) -> Dict[str, Any]:
        """금융투자소득세(금투세) 계산"""
        profit = context.extracted_amount or 0
        result = tax_svc.calc_financial_investment_tax(
            domestic_stock_profit=profit,
            overseas_stock_profit=0,
        )
        total_tax = result.get('total_tax', 0)
        basic_deduction = result.get('domestic_deduction', 5_000_000)
        response = (
            f"📈 금융투자소득세(금투세) 계산\n"
            f"국내주식 수익: {profit:,.0f}원 기준\n"
            f"기본공제: {basic_deduction:,.0f}원\n"
            f"예상 세액: {total_tax:,.0f}원\n\n"
            f"해외주식·ETF 수익도 알려주시면 통합 계산이 됩니다.\n"
            f"예: '국내 2000만 해외 1000만 금투세 계산'"
        )
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': 'calc_investment_tax',
            'data': result,
            'requires_confirmation': False,
        }

    def _handle_compare_tax_accounts(self, context: FinanceContext) -> Dict[str, Any]:
        """ISA / 연금저축 / IRP 절세 효과 비교"""
        salary = context.extracted_amount or 50_000_000
        result = tax_svc.compare_tax_saving_accounts(
            annual_salary=salary,
            annual_investment=3_000_000,
        )
        accounts = result.get('accounts', [])
        lines = []
        for acc in accounts[:3]:
            name = acc.get('name', '')
            tax_benefit = acc.get('annual_tax_benefit', 0)
            lines.append(f"  • {name}: 연 절세 {tax_benefit:,.0f}원")
        best = result.get('best_option', {})
        best_name = best.get('name', '')
        response = (
            f"🏦 절세 계좌 비교 (연봉 {salary/10000:.0f}만원 기준)\n"
            + "\n".join(lines) + "\n\n"
            f"✅ 추천: {best_name}\n"
            f"연봉을 알려주시면 더 정확한 절세 효과를 계산합니다.\n"
            f"예: '연봉 6000만원 ISA IRP 절세 비교'"
        )
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': 'compare_tax_accounts',
            'data': result,
            'requires_confirmation': False,
        }

    # ========== 금융 이상 탐지 핸들러 ==========

    def _handle_analyze_fraud_message(self, context: FinanceContext) -> Dict[str, Any]:
        """보이스피싱·스미싱 문자 분석"""
        text = context.raw_input
        alert = analyze_voice_phishing(text)
        # 반환값은 단일 FraudAlert
        if alert.risk_level == 'low' and alert.score == 0:
            response = (
                "🔍 사기 패턴 분석 결과\n"
                "✅ 탐지된 위험 패턴 없음\n\n"
                "분석할 문자나 전화 내용을 그대로 붙여넣기 해주세요.\n"
                "예: '검찰청입니다. 계좌가 범죄에 연루되었으니 OTP를 알려주세요.'"
            )
        else:
            risk_emoji = {'low': '🟡', 'medium': '🟠', 'high': '🔴', 'critical': '🚨'}.get(alert.risk_level, '⚠️')
            actions = "\n".join(f"  • {a}" for a in alert.recommended_actions[:3])
            response = (
                f"🚨 사기 패턴 분석 결과\n"
                f"{risk_emoji} 위험도: {alert.risk_level.upper()}\n"
                f"탐지 유형: {alert.alert_type}\n"
                f"설명: {alert.description}\n\n"
                f"📋 권고 행동:\n{actions}\n\n"
                f"⚠️ 법적 조치(신고·고발)는 사용자가 직접 처리하십시오."
            )
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': 'analyze_fraud_message',
            'data': alert.__dict__ if hasattr(alert, '__dict__') else str(alert),
            'requires_confirmation': False,
        }

    def _handle_detect_abnormal_tx(self, context: FinanceContext) -> Dict[str, Any]:
        """이상 거래 탐지 안내"""
        response = (
            "🔍 이상 거래 탐지\n"
            "거래 내역을 분석하려면 다음 정보를 알려주세요:\n"
            "  • 최근 거래 내역 (금액, 날짜, 상대방)\n"
            "  • 의심되는 거래 금액\n\n"
            "탐지 기준:\n"
            "  • 평균 대비 비정상적으로 큰 금액 (z-score 2.5 초과)\n"
            "  • 자정~새벽 4시 이체\n"
            "  • 동일 금액 반복 이체 (쪼개기)\n"
            "  • 신규 계좌로 대규모 이체\n"
            "  • 단시간 대량 현금 인출\n\n"
            "⚠️ 법적 조치(신고·고발)는 사용자가 직접 처리하십시오."
        )
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': 'detect_abnormal_tx',
            'data': None,
            'requires_confirmation': False,
        }

    def _handle_check_predatory_loan(self, context: FinanceContext) -> Dict[str, Any]:
        """약탈적 대출 위험도 확인"""
        amount = context.extracted_amount or 0
        response = (
            "🚨 약탈적 대출 경고 확인\n"
            "다음 조건에 해당하면 위험한 대출입니다:\n"
            "  🔴 연이율 20% 초과 (법정 최고금리 위반)\n"
            "  🔴 선납 수수료·보증금 요구\n"
            "  🔴 '원금보장' '수익보장' 언급\n"
            "  🔴 신용조회 없이 즉시 승인\n\n"
            "대출 조건 (금리, 금액, 수수료 여부)을 알려주시면\n"
            "구체적인 위험도를 분석해 드립니다.\n"
            "예: '연 25% 1000만원 선납수수료 있는 대출 괜찮아?'\n\n"
            f"{'💡 조회 금액: ' + f'{amount:,.0f}원' if amount else ''}"
            "\n⚠️ 법적 조치는 사용자가 직접 처리하십시오."
        )
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': 'check_predatory_loan',
            'data': None,
            'requires_confirmation': False,
        }

    # ========== 일반 ==========

    def _handle_general_question(self, context: FinanceContext) -> Dict[str, Any]:
        """일반 질문"""
        response = (
            "생활금융 어시스턴트입니다. 다음과 같이 말씀해주세요:\n"
            "• 지출: '카페에서 5000원 썼어'\n"
            "• 수입: '급여로 350만원 받았어'\n"
            "• 조회: '이번 달 지출이 얼마야?'\n"
            "• 목표: '여름 휴가 200만원 목표'\n"
            "• 조언: '어떻게 절약할까?'\n"
            "• 대출 비교: '대출 비교해줘'\n"
            "• 보험 비교: '보험 추천해줘'\n"
            "• 예적금 비교: '예금 상품 비교해줘'\n"
            "• 연말정산: '연말정산 계산해줘'\n"
            "• 금융소득: '금융소득종합과세 해당돼?'\n"
            "• 금투세: '금투세 얼마 내야 해?'\n"
            "• 절세 비교: 'ISA랑 IRP 중 뭐가 더 유리해?'\n"
            "• 사기 문자: '이 문자 보이스피싱이야?' (내용 붙여넣기)\n"
            "• 이상 거래: '이상한 거래 탐지해줘'\n"
            "• 의심 대출: '이 대출 금리 괜찮아?'"
        )
        
        return {
            'response': response,
            'intent': context.intent.value,
            'action_taken': None,
            'data': None,
            'requires_confirmation': False,
        }
    
    # ========== 유틸리티 ==========
    
    def _create_progress_bar(self, percentage: float, length: int = 10) -> str:
        """진행 바 생성"""
        filled = int(length * percentage / 100)
        bar = "█" * filled + "░" * (length - filled)
        return f"[{bar}]"
    
    def _get_category_advice(self, category: str) -> str:
        """카테고리별 절약 조언"""
        advice_map = {
            '식비': '배달 대신 집에서 요리하면 30-50% 절약할 수 있습니다.',
            '교통비': '정기권 구매로 20% 절약하거나 자전거를 이용해보세요.',
            '주거비': '공과금은 고정적이지만, 에너지 효율 개선으로 절약할 수 있습니다.',
            '문화생활': '월간 문화생활비 예산을 정하고 우선순위를 정해보세요.',
            '쇼핑': '계획적 쇼핑으로 충동구매를 줄일 수 있습니다.',
            '건강/의료': '예방이 최선의 절약입니다. 정기 검진을 받으세요.',
            '교육': '무료 강의나 도서관을 활용하면 교육비를 절약할 수 있습니다.',
        }
        return advice_map.get(category, '')
    
    # ========== Phase 1: 신용도 기반 조정 유틸리티 ==========
    
    @staticmethod
    def _format_credit_label(credit_score: str) -> str:
        """신용도를 친화적 텍스트로 포맷"""
        if "좋음" in credit_score:
            return "좋음 🟢"
        elif "낮음" in credit_score:
            return "낮음 🔴"
        else:
            return "보통 🟡"


if __name__ == "__main__":
    # 테스트
    import asyncio
    
    manager = LifeFinanceManager()
    assistant = LifeFinanceAssistant(manager)
    
    # 테스트 명령들
    test_commands = [
        "어제 카페에서 5천원 썼어",
        "오늘 급여로 350만원 받았어",
        "최근 지출 내역 보여줘",
        "이번 달 리포트",
        "목표는 뭐가 있어?",
    ]
    
    async def run_tests():
        for cmd in test_commands:
            print(f"\n> {cmd}")
            result = await assistant.process_command(cmd)
            print(result['response'])
    
    asyncio.run(run_tests())
