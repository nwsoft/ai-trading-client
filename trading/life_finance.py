#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
생활금융 통합 관리 시스템
- 수입/지출 자동 분류
- 재정 목표 관리  
- 재무 시뮬레이션
- 통계 및 인사이트 제공
"""

import json
import os
import shutil
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
import statistics
from abc import ABC, abstractmethod

# ============================================================================
# 1. Enums & DataClasses
# ============================================================================

class TransactionType(Enum):
    """거래 유형"""
    INCOME = "수입"
    EXPENSE = "지출"


class ExpenseCategory(Enum):
    """지출 카테고리 (AI 분류 기반)"""
    FOOD = "식비"  # 식당, 카페, 배달, 마트 식료품
    TRANSPORT = "교통비"  # 대중교통, 택시, 자동차 관련
    HOUSING = "주거비"  # 월세, 전기, 수도, 인터넷
    ENTERTAINMENT = "문화생활"  # 영화, 공연, 게임, 스포츠
    SHOPPING = "쇼핑"  # 의류, 신발, 액세서리
    HEALTH = "건강/의료"  # 병원, 약국, 피트니스
    EDUCATION = "교육"  # 학원, 교재, 강의료
    FINANCE = "금융"  # 이자, 수수료, 보험료
    SUBSCRIPTION = "구독"  # 넷플릭스, 스포티파이, 구독 서비스
    TRANSFER = "송금"  # 계좌이체, 개인 송금
    OTHER = "기타"  # 분류 안 된 항목

    @classmethod
    def from_string(cls, value: str) -> 'ExpenseCategory':
        """문자열에서 카테고리 생성"""
        try:
            return cls[value.upper()]
        except KeyError:
            # 유사 매칭 시도
            for category in cls:
                if category.value == value:
                    return category
            return cls.OTHER


class IncomeType(Enum):
    """수입 유형"""
    SALARY = "급여"  # 월급
    BONUS = "보너스"  # 상여금
    PART_TIME = "아르바이트"  # 부업
    INVESTMENT = "투자수익"  # 배당금, 이자
    TRANSFER = "송금"  # 개인 송금
    OTHER = "기타"  # 기타 수입


@dataclass
class Transaction:
    """거래 기록"""
    id: str  # UUID
    date: date  # 거래 날짜
    amount: float  # 금액
    type: TransactionType  # 수입/지출
    category: str  # 카테고리 (지출일 경우 ExpenseCategory, 수입일 경우 IncomeType)
    description: str  # 설명/메모
    method: str = "기타"  # 결제 수단 (카드, 현금, 계좌이체)
    ai_confidence: float = 1.0  # AI 분류 신뢰도 (0-1)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'amount': self.amount,
            'type': self.type.value,
            'category': self.category,
            'description': self.description,
            'method': self.method,
            'ai_confidence': self.ai_confidence,
        }


@dataclass
class FinanceGoal:
    """재정 목표"""
    id: str  # UUID
    name: str  # 목표명 (예: "여행 경비", "신차 구입")
    target_amount: float  # 목표 금액
    current_amount: float = 0.0  # 현재 저축액
    deadline: Optional[date] = None  # 달성 기한
    category: str = "기타"  # 목표 카테고리
    priority: str = "중간"  # 우선순위 (높음, 중간, 낮음)
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def progress_rate(self) -> float:
        """진행률 (0-100%)"""
        if self.target_amount == 0:
            return 0
        return (self.current_amount / self.target_amount) * 100
    
    @property
    def remaining_amount(self) -> float:
        """남은 금액"""
        return max(0, self.target_amount - self.current_amount)
    
    @property
    def is_completed(self) -> bool:
        """완료 여부"""
        return self.current_amount >= self.target_amount
    
    @property
    def days_until_deadline(self) -> Optional[int]:
        """마감까지 남은 날수"""
        if not self.deadline:
            return None
        return (self.deadline - date.today()).days
    
    @property
    def monthly_target(self) -> Optional[float]:
        """월간 목표 저축액"""
        if not self.deadline or self.is_completed:
            return None
        days_left = self.days_until_deadline
        if days_left <= 0:
            return None
        months_left = max(1, days_left / 30)
        return self.remaining_amount / months_left
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'target_amount': self.target_amount,
            'current_amount': self.current_amount,
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'category': self.category,
            'priority': self.priority,
            'description': self.description,
            'progress_rate': self.progress_rate,
            'remaining_amount': self.remaining_amount,
            'is_completed': self.is_completed,
            'days_until_deadline': self.days_until_deadline,
            'monthly_target': self.monthly_target,
        }


@dataclass
class MonthlyReport:
    """월간 재무 보고서"""
    year: int
    month: int
    total_income: float = 0.0
    total_expense: float = 0.0
    category_breakdown: Dict[str, float] = field(default_factory=dict)
    net_savings: float = 0.0
    
    @property
    def savings_rate(self) -> float:
        """저축률 (%)"""
        if self.total_income == 0:
            return 0
        return (self.net_savings / self.total_income) * 100
    
    @property
    def date_str(self) -> str:
        return f"{self.year}-{self.month:02d}"
    
    def to_dict(self) -> dict:
        return {
            'year': self.year,
            'month': self.month,
            'date_str': self.date_str,
            'total_income': self.total_income,
            'total_expense': self.total_expense,
            'net_savings': self.net_savings,
            'savings_rate': self.savings_rate,
            'category_breakdown': self.category_breakdown,
        }


@dataclass
class FinanceAlert:
    """생활금융 알림"""
    level: str
    title: str
    message: str
    action_hint: str = ""

    def to_dict(self) -> dict:
        return {
            'level': self.level,
            'title': self.title,
            'message': self.message,
            'action_hint': self.action_hint,
        }


# ============================================================================
# 2. 지출 분류 엔진 (AI 기반)
# ============================================================================

class ExpenseClassifier:
    """지출 설명을 기반으로 자동 분류"""
    
    # 키워드 기반 분류 규칙
    CLASSIFICATION_RULES = {
        ExpenseCategory.FOOD: [
            '식당', '카페', '커피', '치킨', '피자', '라면', '밥', '점심', '저녁',
            '배달', '음식', '반찬', '마트', '편의점', '베이커리', '제과', '햄버거',
            '스시', '회', '국밥', '국수', '덮밥', '쌀', '야채', '과일',
        ],
        ExpenseCategory.TRANSPORT: [
            '지하철', '버스', '택시', '우버', '기차', '기름', '휘발유', '경유',
            '교통', '차', '자동차', '부산', '서울', '주차', '톨게이트', '항공',
            '비행기', '기차역', '기차 표',
        ],
        ExpenseCategory.HOUSING: [
            '월세', '전세', '전기', '수도', '가스', '인터넷', '통신', '수도료',
            '보증금', '주택', '아파트', '집', '렌트', '기숙사', '호텔', '숙박',
        ],
        ExpenseCategory.ENTERTAINMENT: [
            '영화', '공연', '콘서트', '티켓', '게임', '영화관', '유튜브', '넷플릭스',
            '스포츠', '관광', '여행', '박물관', '전시', '놀이공원', '스키장',
        ],
        ExpenseCategory.SHOPPING: [
            '옷', '신발', '가방', '액세서리', '옷가게', '백화점', '쇼핑', '의류',
            '향수', '화장품', '미용', '헤어', '네일', '드레스', '정장',
        ],
        ExpenseCategory.HEALTH: [
            '병원', '약국', '의료', '건강', '피트니스', '헬스', '요가', '의약품',
            '치과', '안과', '피부', '감기', '진료', '예방접종',
        ],
        ExpenseCategory.EDUCATION: [
            '학원', '교재', '책', '강의', '수강료', '수업', '교육', '코스',
            '자격증', '온라인 강의', '영어', '수학', '과학', '한국어',
        ],
        ExpenseCategory.FINANCE: [
            '이자', '수수료', '보험료', '보험', '펀드', '투자', '세금', '통장',
            '카드', '대출', '이체료', '송금', '계좌이체',
        ],
        ExpenseCategory.SUBSCRIPTION: [
            '구독', '월간 요금', '구독료', '멤버십', '프리미엄', 'spotify',
            'netflix', 'disney', '구독 서비스', 'subscription',
        ],
        ExpenseCategory.TRANSFER: [
            '송금', '이체', '개인 송금', '계좌이체', '지인', '친구', '가족',
            '입금', 'transfer', '송금액',
        ],
    }
    
    @classmethod
    def classify(cls, description: str) -> Tuple[ExpenseCategory, float]:
        """
        지출 설명을 분류
        
        Returns:
            (카테고리, 신뢰도 0-1)
        """
        desc_lower = description.lower()
        
        # 키워드 매칭 스코어 계산
        scores = {}
        for category, keywords in cls.CLASSIFICATION_RULES.items():
            score = sum(1 for keyword in keywords if keyword in desc_lower)
            if score > 0:
                scores[category] = score
        
        if not scores:
            return ExpenseCategory.OTHER, 0.3
        
        # 최고 점수 카테고리 선택
        best_category = max(scores, key=scores.get)
        confidence = min(scores[best_category] / 3.0, 1.0)  # 최대 3개 키워드
        
        return best_category, confidence
    
    @classmethod
    def suggest_categories(cls, description: str, top_k: int = 3) -> List[Tuple[ExpenseCategory, float]]:
        """상위 K개 후보 카테고리 제시"""
        desc_lower = description.lower()
        scores = {}
        
        for category, keywords in cls.CLASSIFICATION_RULES.items():
            score = sum(1 for keyword in keywords if keyword in desc_lower)
            if score > 0:
                scores[category] = score
        
        if not scores:
            return [(ExpenseCategory.OTHER, 0.3)]
        
        # 상위 K개
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        
        # 신뢰도 정규화
        max_score = max(s[1] for s in sorted_scores)
        return [
            (category, score / max_score * 0.95)
            for category, score in sorted_scores
        ]


# ============================================================================
# 3. 재무 시뮬레이션 엔진
# ============================================================================

class FinanceSimulator:
    """재무 시나리오 분석 및 시뮬레이션"""
    
    @staticmethod
    def project_savings(
        monthly_income: float,
        monthly_expenses: float,
        months: int = 12,
        inflation_rate: float = 0.02,
    ) -> List[float]:
        """
        월간 저축 프로젝션
        
        Args:
            monthly_income: 월 수입
            monthly_expenses: 월 지출
            months: 시뮬레이션 기간 (개월)
            inflation_rate: 연간 인플레이션율
        
        Returns:
            월별 누적 저축액 리스트
        """
        projections = []
        cumulative = 0
        monthly_inflation = (1 + inflation_rate) ** (1/12)
        
        for month in range(1, months + 1):
            # 인플레이션 적용
            adjusted_expenses = monthly_expenses * (monthly_inflation ** month)
            monthly_savings = monthly_income - adjusted_expenses
            cumulative += monthly_savings
            projections.append(cumulative)
        
        return projections
    
    @staticmethod
    def goal_achievement_timeline(
        current_savings: float,
        monthly_savings: float,
        goal_amount: float,
    ) -> Optional[int]:
        """
        목표 달성까지 필요한 개월 수
        
        Returns:
            필요한 개월 수 (달성 불가능하면 None)
        """
        if monthly_savings <= 0:
            return None
        
        remaining = goal_amount - current_savings
        if remaining <= 0:
            return 0
        
        return int((remaining / monthly_savings) + 0.5)
    
    @staticmethod
    def scenario_comparison(
        scenarios: Dict[str, Dict[str, float]],
        months: int = 12,
    ) -> Dict[str, Dict[str, float]]:
        """
        다중 시나리오 비교
        
        Args:
            scenarios: {'시나리오명': {'monthly_income': 값, 'monthly_expenses': 값}}
        """
        results = {}
        
        for scenario_name, params in scenarios.items():
            projections = FinanceSimulator.project_savings(
                monthly_income=params.get('monthly_income', 0),
                monthly_expenses=params.get('monthly_expenses', 0),
                months=months,
            )
            
            results[scenario_name] = {
                'final_savings': projections[-1] if projections else 0,
                'average_monthly_savings': sum(projections) / len(projections) if projections else 0,
                'max_savings': max(projections) if projections else 0,
            }
        
        return results


# ============================================================================
# 4. 메인 생활금융 관리자
# ============================================================================

class LifeFinanceManager:
    """생활금융 통합 관리"""
    
    def __init__(self, data_dir: str = "data", backup_dir: Optional[str] = None, external_sync_dir: Optional[str] = None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

        self.backup_dir = Path(backup_dir) if backup_dir else self.data_dir / "backups"
        self.backup_dir.mkdir(exist_ok=True)

        sync_from_env = os.getenv("LIFE_FINANCE_SYNC_DIR", "").strip()
        sync_dir = external_sync_dir or sync_from_env
        self.external_sync_dir = Path(sync_dir).expanduser() if sync_dir else None
        if self.external_sync_dir:
            self.external_sync_dir.mkdir(parents=True, exist_ok=True)
        
        self.transactions_file = self.data_dir / "life_finance_transactions.json"
        self.goals_file = self.data_dir / "life_finance_goals.json"
        self.monthly_cache_file = self.data_dir / "life_finance_monthly_cache.json"
        
        self.transactions: List[Transaction] = []
        self.goals: List[FinanceGoal] = []
        self.monthly_reports: Dict[str, MonthlyReport] = {}
        
        self._load_data()
    
    # ========== 데이터 로드/저장 ==========
    
    def _load_data(self):
        """파일에서 데이터 로드"""
        # 거래 로드
        if self.transactions_file.exists():
            try:
                with open(self.transactions_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.transactions = [
                        Transaction(
                            id=t['id'],
                            date=datetime.fromisoformat(t['date']).date(),
                            amount=t['amount'],
                            type=self._parse_transaction_type(t.get('type', '지출')),
                            category=t['category'],
                            description=t['description'],
                            method=t.get('method', '기타'),
                            ai_confidence=t.get('ai_confidence', 1.0),
                        )
                        for t in data
                    ]
            except Exception as e:
                print(f"⚠️ 거래 로드 실패: {e}")
                self.transactions = []
        
        # 목표 로드
        if self.goals_file.exists():
            try:
                with open(self.goals_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.goals = [
                        FinanceGoal(
                            id=g['id'],
                            name=g['name'],
                            target_amount=g['target_amount'],
                            current_amount=g.get('current_amount', 0),
                            deadline=datetime.fromisoformat(g['deadline']).date() if g.get('deadline') else None,
                            category=g.get('category', '기타'),
                            priority=g.get('priority', '중간'),
                            description=g.get('description', ''),
                        )
                        for g in data
                    ]
            except Exception as e:
                print(f"⚠️ 목표 로드 실패: {e}")
                self.goals = []

    def _parse_transaction_type(self, value: str) -> TransactionType:
        """거래 타입 문자열을 안전하게 파싱"""
        raw = str(value or '').strip()
        if raw in (TransactionType.INCOME.value, 'income', 'INCOME', '수입'):
            return TransactionType.INCOME
        if raw in (TransactionType.EXPENSE.value, 'expense', 'EXPENSE', '지출'):
            return TransactionType.EXPENSE
        try:
            normalized = raw.split('_')[0].upper()
            if normalized in TransactionType.__members__:
                return TransactionType[normalized]
        except Exception:
            pass
        return TransactionType.EXPENSE

    def _invalidate_monthly_cache(self) -> None:
        self.monthly_reports = {}

    def _backup_files(self) -> None:
        """저장 시점의 스냅샷을 백업 디렉터리에 보관"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for src in (self.transactions_file, self.goals_file):
            try:
                if src.exists():
                    dst = self.backup_dir / f"{timestamp}_{src.name}"
                    shutil.copy2(src, dst)
            except Exception:
                # 백업 실패는 서비스 동작을 막지 않는다.
                pass

    def _sync_external_files(self) -> None:
        """외부 동기화 폴더(예: SynologyDrive)에 최신 파일 복사"""
        if not self.external_sync_dir:
            return
        for src in (self.transactions_file, self.goals_file):
            try:
                if src.exists():
                    shutil.copy2(src, self.external_sync_dir / src.name)
            except Exception:
                pass
    
    def _save_data(self):
        """데이터를 파일에 저장"""
        # 거래 저장
        with open(self.transactions_file, 'w', encoding='utf-8') as f:
            json.dump([t.to_dict() for t in self.transactions], f, ensure_ascii=False, indent=2)
        
        # 목표 저장
        with open(self.goals_file, 'w', encoding='utf-8') as f:
            json.dump([g.to_dict() for g in self.goals], f, ensure_ascii=False, indent=2)

        self._invalidate_monthly_cache()
        self._backup_files()
        self._sync_external_files()
    
    # ========== 거래 관리 ==========
    
    def add_transaction(
        self,
        date: date,
        amount: float,
        type_: TransactionType,
        description: str,
        method: str = "기타",
        category: Optional[str] = None,
        auto_classify: bool = True,
    ) -> Transaction:
        """
        거래 추가
        
        Args:
            date: 거래 날짜
            amount: 금액
            type_: 수입/지출
            description: 설명
            method: 결제 수단
            category: 카테고리 (None이면 자동 분류)
            auto_classify: 자동 분류 여부
        """
        # ID 생성
        tx_id = f"tx_{int(datetime.now().timestamp() * 1000)}"
        
        # 카테고리 결정
        if category is None and auto_classify and type_ == TransactionType.EXPENSE:
            category, confidence = ExpenseClassifier.classify(description)
            category = category.value
        elif category is None:
            category = "기타"
        
        # 신뢰도 계산
        if type_ == TransactionType.EXPENSE and auto_classify:
            _, confidence = ExpenseClassifier.classify(description)
        else:
            confidence = 1.0
        
        # 거래 생성
        transaction = Transaction(
            id=tx_id,
            date=date,
            amount=amount,
            type=type_,
            category=category,
            description=description,
            method=method,
            ai_confidence=confidence,
        )
        
        self.transactions.append(transaction)
        self._save_data()
        
        return transaction
    
    def update_transaction(
        self,
        tx_id: str,
        **kwargs,
    ) -> Optional[Transaction]:
        """거래 수정"""
        tx = self._find_transaction(tx_id)
        if not tx:
            return None
        
        for key, value in kwargs.items():
            if key == 'date' and isinstance(value, str):
                value = datetime.fromisoformat(value).date()
            if hasattr(tx, key):
                setattr(tx, key, value)
        
        self._save_data()
        return tx
    
    def delete_transaction(self, tx_id: str) -> bool:
        """거래 삭제"""
        original_len = len(self.transactions)
        self.transactions = [t for t in self.transactions if t.id != tx_id]
        
        if len(self.transactions) < original_len:
            self._save_data()
            return True
        return False
    
    def get_transactions(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        category: Optional[str] = None,
        type_: Optional[TransactionType] = None,
    ) -> List[Transaction]:
        """거래 조회 (필터링)"""
        result = self.transactions
        
        if start_date:
            result = [t for t in result if t.date >= start_date]
        if end_date:
            result = [t for t in result if t.date <= end_date]
        if category:
            result = [t for t in result if t.category == category]
        if type_:
            result = [t for t in result if t.type == type_]
        
        return sorted(result, key=lambda t: t.date, reverse=True)
    
    def _find_transaction(self, tx_id: str) -> Optional[Transaction]:
        """ID로 거래 찾기"""
        for tx in self.transactions:
            if tx.id == tx_id:
                return tx
        return None
    
    # ========== 목표 관리 ==========
    
    def add_goal(
        self,
        name: str,
        target_amount: float,
        deadline: Optional[date] = None,
        category: str = "기타",
        priority: str = "중간",
        description: str = "",
    ) -> FinanceGoal:
        """목표 추가"""
        goal_id = f"goal_{int(datetime.now().timestamp() * 1000)}"
        
        goal = FinanceGoal(
            id=goal_id,
            name=name,
            target_amount=target_amount,
            deadline=deadline,
            category=category,
            priority=priority,
            description=description,
        )
        
        self.goals.append(goal)
        self._save_data()
        return goal
    
    def update_goal(
        self,
        goal_id: str,
        **kwargs,
    ) -> Optional[FinanceGoal]:
        """목표 수정"""
        goal = self._find_goal(goal_id)
        if not goal:
            return None
        
        for key, value in kwargs.items():
            if hasattr(goal, key):
                setattr(goal, key, value)
        
        self._save_data()
        return goal
    
    def add_goal_savings(self, goal_id: str, amount: float) -> Optional[FinanceGoal]:
        """목표에 저축 추가"""
        goal = self._find_goal(goal_id)
        if not goal:
            return None
        
        goal.current_amount += amount
        goal.current_amount = min(goal.current_amount, goal.target_amount)  # 상한선
        
        self._save_data()
        return goal
    
    def delete_goal(self, goal_id: str) -> bool:
        """목표 삭제"""
        original_len = len(self.goals)
        self.goals = [g for g in self.goals if g.id != goal_id]
        
        if len(self.goals) < original_len:
            self._save_data()
            return True
        return False
    
    def get_goals(self, completed: Optional[bool] = None) -> List[FinanceGoal]:
        """목표 조회"""
        result = self.goals
        
        if completed is not None:
            result = [g for g in result if g.is_completed == completed]
        
        # 우선순위 정렬
        priority_order = {"높음": 0, "중간": 1, "낮음": 2}
        return sorted(
            result,
            key=lambda g: (priority_order.get(g.priority, 3), g.deadline or date.max)
        )
    
    def _find_goal(self, goal_id: str) -> Optional[FinanceGoal]:
        """ID로 목표 찾기"""
        for goal in self.goals:
            if goal.id == goal_id:
                return goal
        return None
    
    # ========== 통계 및 리포트 ==========
    
    def get_monthly_report(self, year: int, month: int) -> MonthlyReport:
        """월간 재무 보고서"""
        key = f"{year}-{month:02d}"
        
        # 캐시 확인
        if key in self.monthly_reports:
            return self.monthly_reports[key]
        
        # 계산
        report = MonthlyReport(year=year, month=month)
        
        # 해당 월의 거래 필터링
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        
        month_transactions = self.get_transactions(start_date=start, end_date=end)
        
        # 수입/지출 계산
        for tx in month_transactions:
            if tx.type == TransactionType.INCOME:
                report.total_income += tx.amount
            else:
                report.total_expense += tx.amount
                # 카테고리별 분류
                if tx.category not in report.category_breakdown:
                    report.category_breakdown[tx.category] = 0
                report.category_breakdown[tx.category] += tx.amount
        
        report.net_savings = report.total_income - report.total_expense
        
        self.monthly_reports[key] = report
        return report
    
    def get_category_stats(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Dict[str, float]]:
        """카테고리별 통계"""
        txs = self.get_transactions(start_date=start_date, end_date=end_date, type_=TransactionType.EXPENSE)
        
        stats = {}
        for tx in txs:
            if tx.category not in stats:
                stats[tx.category] = {'total': 0, 'count': 0, 'avg': 0}
            
            stats[tx.category]['total'] += tx.amount
            stats[tx.category]['count'] += 1
        
        # 평균 계산
        for category in stats:
            if stats[category]['count'] > 0:
                stats[category]['avg'] = stats[category]['total'] / stats[category]['count']
        
        return dict(sorted(stats.items(), key=lambda x: x[1]['total'], reverse=True))
    
    def get_monthly_stats(self, months: int = 12) -> Dict[str, float]:
        """월간 통계"""
        today = date.today()
        stats = {}
        
        for i in range(months):
            current_date = date(today.year, today.month, 1)
            # i개월 이전로 이동
            for _ in range(i):
                if current_date.month == 1:
                    current_date = date(current_date.year - 1, 12, 1)
                else:
                    current_date = date(current_date.year, current_date.month - 1, 1)
            
            report = self.get_monthly_report(current_date.year, current_date.month)
            key = report.date_str
            stats[key] = report.net_savings
        
        return dict(reversed(sorted(stats.items())))
    
    def get_spending_trend(self, months: int = 12) -> Dict[str, float]:
        """지출 추세"""
        today = date.today()
        trend = {}
        
        for i in range(months):
            current_date = date(today.year, today.month, 1)
            # i개월 이전로 이동
            for _ in range(i):
                if current_date.month == 1:
                    current_date = date(current_date.year - 1, 12, 1)
                else:
                    current_date = date(current_date.year, current_date.month - 1, 1)
            
            report = self.get_monthly_report(current_date.year, current_date.month)
            key = report.date_str
            trend[key] = report.total_expense
        
        return dict(reversed(sorted(trend.items())))
    
    # ========== 종합 대시보드 ==========
    
    def get_dashboard_summary(self) -> Dict[str, Any]:
        """대시보드 요약 정보"""
        today = date.today()
        this_month_report = self.get_monthly_report(today.year, today.month)
        
        # 이전 달과 비교
        if today.month == 1:
            last_month_date = date(today.year - 1, 12, 1)
        else:
            last_month_date = date(today.year, today.month - 1, 1)
        last_month_report = self.get_monthly_report(last_month_date.year, last_month_date.month)
        
        # 현재까지의 누적
        total_savings = sum(t.amount for t in self.transactions if t.type == TransactionType.INCOME)
        total_spent = sum(t.amount for t in self.transactions if t.type == TransactionType.EXPENSE)
        
        # 목표 진행
        active_goals = [g for g in self.get_goals() if not g.is_completed]
        completed_goals = [g for g in self.get_goals() if g.is_completed]
        
        return {
            'this_month': this_month_report.to_dict(),
            'last_month': last_month_report.to_dict(),
            'comparison': {
                'income_change': this_month_report.total_income - last_month_report.total_income,
                'expense_change': this_month_report.total_expense - last_month_report.total_expense,
                'savings_change': this_month_report.net_savings - last_month_report.net_savings,
            },
            'cumulative': {
                'total_income': total_savings,
                'total_expenses': total_spent,
                'net_position': total_savings - total_spent,
            },
            'goals': {
                'active_count': len(active_goals),
                'completed_count': len(completed_goals),
                'top_goals': [g.to_dict() for g in active_goals[:3]],
            },
            'top_expenses': [
                (cat, amount) 
                for cat, amount in this_month_report.category_breakdown.items()
            ][:5],
            'alerts': [a.to_dict() for a in self.get_finance_alerts()],
        }

    def get_finance_alerts(self, monthly_income_hint: Optional[float] = None) -> List[FinanceAlert]:
        """예산·목표 기반 알림 생성"""
        alerts: List[FinanceAlert] = []
        today = date.today()
        report = self.get_monthly_report(today.year, today.month)

        baseline_income = monthly_income_hint if monthly_income_hint and monthly_income_hint > 0 else report.total_income
        if baseline_income > 0:
            expense_ratio = report.total_expense / baseline_income
            if expense_ratio >= 1.0:
                alerts.append(FinanceAlert(
                    level='critical',
                    title='지출 한도 초과',
                    message=f"이번 달 지출이 수입 대비 {expense_ratio * 100:.1f}%입니다.",
                    action_hint='지출 상위 2개 카테고리를 즉시 조정하세요.',
                ))
            elif expense_ratio >= 0.85:
                alerts.append(FinanceAlert(
                    level='warning',
                    title='지출 주의 구간',
                    message=f"이번 달 지출이 수입 대비 {expense_ratio * 100:.1f}%입니다.",
                    action_hint='남은 기간 변동비 지출을 20% 절감해보세요.',
                ))

        for goal in self.get_goals(completed=False):
            if goal.days_until_deadline is None:
                continue
            if goal.days_until_deadline < 0:
                alerts.append(FinanceAlert(
                    level='critical',
                    title='목표 기한 경과',
                    message=f"'{goal.name}' 목표 기한이 지났습니다.",
                    action_hint='기한을 재설정하거나 목표 금액을 조정하세요.',
                ))
            elif goal.days_until_deadline <= 30:
                monthly_target = goal.monthly_target if goal.monthly_target else 0
                alerts.append(FinanceAlert(
                    level='info',
                    title='목표 마감 임박',
                    message=f"'{goal.name}' 목표까지 {goal.days_until_deadline}일 남았습니다.",
                    action_hint=f"월 {monthly_target:,.0f}원 이상 저축이 필요합니다.",
                ))

        return alerts


# ============================================================================
# 5. 도우미 함수
# ============================================================================

def create_demo_data(manager: LifeFinanceManager):
    """데모 데이터 생성"""
    from uuid import uuid4
    
    # 최근 3개월 거래 추가
    today = date.today()
    
    # 월급 (매월 첫째 날)
    for month_offset in range(3):
        salary_date = today - timedelta(days=today.day - 1 + month_offset * 30)
        manager.add_transaction(
            date=salary_date,
            amount=3500000,
            type_=TransactionType.INCOME,
            description="월급",
            category="급여",
            auto_classify=False,
        )
    
    # 지출
    sample_expenses = [
        (today, 15000, "카페에서 아메리카노", True),
        (today - timedelta(days=1), 45000, "마트 장보기", True),
        (today - timedelta(days=2), 8500, "지하철 카드 충전", True),
        (today - timedelta(days=3), 120000, "영화표 2장", True),
        (today - timedelta(days=4), 350000, "월세", True),
        (today - timedelta(days=5), 25000, "헬스장 회원비", True),
    ]
    
    for exp_date, amount, description, auto in sample_expenses:
        manager.add_transaction(
            date=exp_date,
            amount=amount,
            type_=TransactionType.EXPENSE,
            description=description,
            auto_classify=auto,
        )
    
    # 목표
    manager.add_goal(
        name="여름 휴가",
        target_amount=2000000,
        deadline=date(2026, 7, 1),
        priority="높음",
        description="해외 여행 경비",
    )
    
    manager.add_goal(
        name="신차 구입",
        target_amount=30000000,
        deadline=date(2027, 12, 31),
        priority="중간",
        description="차량 교체 자금",
    )


if __name__ == "__main__":
    # 테스트
    manager = LifeFinanceManager()
    
    # 데모 데이터 (선택)
    # create_demo_data(manager)
    
    # 대시보드 출력
    summary = manager.get_dashboard_summary()
    print("=" * 60)
    print("생활금융 대시보드")
    print("=" * 60)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
