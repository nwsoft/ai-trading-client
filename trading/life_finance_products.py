#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
생활금융 상품 비교 모듈
- 대출 비교
- 보험 비교
- 예적금 비교
"""

from dataclasses import dataclass
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class LoanProduct:
    name: str
    provider: str
    annual_rate: float
    max_amount: float
    term_months: int
    fee_rate: float
    loan_type: str = ""  # 주택담보 | 신용 | 전세자금 | 마이너스통장 | 사업자


@dataclass
class InsuranceProduct:
    name: str
    provider: str
    monthly_premium: float
    coverage_score: float
    deductible: float
    category: str


@dataclass
class SavingsProduct:
    name: str
    provider: str
    annual_rate: float
    term_months: int
    tax_free: bool
    min_amount: float


class FinanceProductAdvisor:
    """생활금융 상품 비교 및 추천"""

    # 기본 자동 갱신 주기 (초) — 0이면 비활성
    DEFAULT_REFRESH_INTERVAL: int = 3600  # 1시간

    def __init__(self, catalog_paths: Optional[Dict[str, str]] = None,
                 auto_refresh_interval: int = DEFAULT_REFRESH_INTERVAL):
        self._custom_catalog_types = {
            product_type
            for product_type, raw_path in (catalog_paths or {}).items()
            if raw_path
        }
        self.catalog_paths = self._resolve_catalog_paths(catalog_paths)
        self.catalog_sources: Dict[str, str] = {}
        self._file_mtimes: Dict[str, float] = {}
        self._refresh_lock = threading.Lock()
        self._refresh_interval = auto_refresh_interval
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self.loan_products = self._load_loan_catalog()
        self.insurance_products = self._load_insurance_catalog()
        self.savings_products = self._load_savings_catalog()
        self._snapshot_mtimes()

        if auto_refresh_interval > 0:
            self._start_auto_refresh()

    # ── 자동 갱신 ──────────────────────────────────────────────────
    def _snapshot_mtimes(self) -> None:
        """현재 파일 수정 시각 스냅샷"""
        for product_type, path in self.catalog_paths.items():
            try:
                self._file_mtimes[product_type] = path.stat().st_mtime if path.exists() else 0.0
            except OSError:
                self._file_mtimes[product_type] = 0.0

    def _start_auto_refresh(self) -> None:
        """백그라운드 주기적 갱신 스레드 시작"""
        self._stop_event.clear()
        self._refresh_thread = threading.Thread(
            target=self._refresh_loop, daemon=True, name="CatalogAutoRefresh"
        )
        self._refresh_thread.start()
        logger.debug("생활금융 카탈로그 자동 갱신 시작 (주기: %ds)", self._refresh_interval)

    def stop_auto_refresh(self) -> None:
        """자동 갱신 정지"""
        self._stop_event.set()

    def _refresh_loop(self) -> None:
        while not self._stop_event.wait(timeout=self._refresh_interval):
            self.refresh_if_changed()

    def refresh_if_changed(self) -> bool:
        """파일 변경 시 카탈로그 재로드. 갱신 여부 반환."""
        changed = []
        for product_type, path in self.catalog_paths.items():
            try:
                current_mtime = path.stat().st_mtime if path.exists() else 0.0
            except OSError:
                current_mtime = 0.0
            if current_mtime != self._file_mtimes.get(product_type, 0.0):
                changed.append(product_type)

        if not changed:
            return False

        with self._refresh_lock:
            try:
                if "loan" in changed:
                    self.loan_products = self._load_loan_catalog()
                    logger.info("📂 대출 카탈로그 재로드: %s", self.catalog_sources.get("loan"))
                if "insurance" in changed:
                    self.insurance_products = self._load_insurance_catalog()
                    logger.info("📂 보험 카탈로그 재로드: %s", self.catalog_sources.get("insurance"))
                if "savings" in changed:
                    self.savings_products = self._load_savings_catalog()
                    logger.info("📂 예적금 카탈로그 재로드: %s", self.catalog_sources.get("savings"))
                self._snapshot_mtimes()
                return True
            except Exception as exc:
                logger.warning("카탈로그 재로드 실패: %s", exc)
                return False

    def force_refresh(self) -> bool:
        """강제 전체 재로드"""
        with self._refresh_lock:
            try:
                self.loan_products = self._load_loan_catalog()
                self.insurance_products = self._load_insurance_catalog()
                self.savings_products = self._load_savings_catalog()
                self._snapshot_mtimes()
                logger.info("📂 카탈로그 강제 재로드 완료")
                return True
            except Exception as exc:
                logger.warning("카탈로그 강제 재로드 실패: %s", exc)
                return False

    def get_catalog_status(self) -> Dict[str, object]:
        """카탈로그 상태 요약.

        실제 경로는 운영 진단을 위해 내부에 유지하지만 일반 사용자 UI는
        source_kind만 사용해 로컬 파일 구조를 노출하지 않는다.
        """
        result: Dict[str, object] = {}
        for product_type, path in self.catalog_paths.items():
            mtime = self._file_mtimes.get(product_type, 0.0)
            result[product_type] = {
                "source": self.catalog_sources.get(product_type, "unknown"),
                "source_kind": self._catalog_source_kind(product_type),
                "path": str(path),
                "exists": path.exists(),
                "mtime": mtime,
                "mtime_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)) if mtime else "N/A",
            }
        return result

    def _catalog_source_kind(self, product_type: str) -> str:
        source = self.catalog_sources.get(product_type, "unknown")
        if source == "built_in_sample":
            return "built_in_fallback"
        if product_type in self._custom_catalog_types:
            return "operator_catalog"
        return "bundled_catalog"

    @staticmethod
    def _resolve_catalog_paths(catalog_paths: Optional[Dict[str, str]]) -> Dict[str, Path]:
        base_dir = Path(__file__).resolve().parent.parent / "data" / "finance_products"
        default_paths = {
            "loan": base_dir / "loans.json",
            "insurance": base_dir / "insurances.json",
            "savings": base_dir / "savings.json",
        }
        resolved = dict(default_paths)
        for product_type, raw_path in (catalog_paths or {}).items():
            if raw_path:
                resolved[product_type] = Path(raw_path).expanduser()
        return resolved

    def _load_catalog_records(self, product_type: str) -> List[Dict[str, object]]:
        path = self.catalog_paths.get(product_type)
        if path and path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    self.catalog_sources[product_type] = str(path)
                    return [record for record in payload if isinstance(record, dict)]
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                logger.warning("생활금융 상품 데이터 읽기 실패, 앱 내장 예비 데이터 사용 (%s): %s", product_type, exc)
        self.catalog_sources[product_type] = "built_in_sample"
        return []

    def _load_loan_catalog(self) -> List[LoanProduct]:
        """대출 상품 목록 로드"""
        records = self._load_catalog_records("loan")
        if records:
            return [
                LoanProduct(
                    str(record["name"]),
                    str(record["provider"]),
                    float(record["annual_rate"]),
                    float(record["max_amount"]),
                    int(record["term_months"]),
                    float(record.get("fee_rate", 0.0)),
                    str(record.get("loan_type", "")),
                )
                for record in records
            ]
        return [
            LoanProduct("KB 주택담보대출 안심",     "KB국민은행",   3.85, 900_000_000, 360, 0.20, "주택담보"),
            LoanProduct("신한 그린 주담대",         "신한은행",     4.05, 800_000_000, 360, 0.15, "주택담보"),
            LoanProduct("하나 우리집 담보대출",      "하나은행",     4.15, 700_000_000, 240, 0.18, "주택담보"),
            LoanProduct("우리 스마트 신용대출",      "우리은행",     5.20, 130_000_000,  84, 0.20, "신용"),
            LoanProduct("카카오 마이너스 통장",      "카카오뱅크",   4.90, 150_000_000,  12, 0.00, "마이너스통장"),
            LoanProduct("토스 비상금 대출",          "토스뱅크",     5.50,  50_000_000,  12, 0.00, "신용"),
            LoanProduct("SC 직장인 플러스",          "SC제일은행",   5.10, 100_000_000, 120, 0.25, "신용"),
            LoanProduct("농협 NH 보금자리론",        "NH농협은행",   3.70, 800_000_000, 360, 0.10, "주택담보"),
        ]

    def _load_insurance_catalog(self) -> List[InsuranceProduct]:
        """보험 상품 목록 로드"""
        records = self._load_catalog_records("insurance")
        if records:
            return [
                InsuranceProduct(
                    str(record["name"]),
                    str(record["provider"]),
                    float(record["monthly_premium"]),
                    float(record["coverage_score"]),
                    float(record["deductible"]),
                    str(record["category"]),
                )
                for record in records
            ]
        return [
            InsuranceProduct("삼성 생활안심 종합보험",   "삼성생명",    58_000, 88,  100_000, "종합"),
            InsuranceProduct("현대해상 건강보험 플래티넘", "현대해상",   48_000, 82,  150_000, "건강"),
            InsuranceProduct("DB손보 실손의료비보험",     "DB손해보험",  42_000, 76,  200_000, "건강"),
            InsuranceProduct("한화 가족사랑 종합보험",    "한화생명",    79_000, 92,  100_000, "가족"),
            InsuranceProduct("KB 희망플러스 건강보험",    "KB손해보험",  55_000, 85,  150_000, "건강"),
            InsuranceProduct("메트라이프 보장보험",       "메트라이프",  65_000, 90,  100_000, "종합"),
            InsuranceProduct("흥국생명 간편가입 보험",    "흥국생명",    38_000, 70,  300_000, "건강"),
        ]

    def _load_savings_catalog(self) -> List[SavingsProduct]:
        """예적금 상품 목록 로드"""
        records = self._load_catalog_records("savings")
        if records:
            return [
                SavingsProduct(
                    str(record["name"]),
                    str(record["provider"]),
                    float(record["annual_rate"]),
                    int(record["term_months"]),
                    bool(record.get("tax_free", False)),
                    float(record["min_amount"]),
                )
                for record in records
            ]
        return [
            SavingsProduct("KB 국민 정기예금",      "KB국민은행",  3.45, 12, False,  1_000_000),
            SavingsProduct("신한 청년 희망적금",     "신한은행",    4.20, 24,  True,    100_000),
            SavingsProduct("카카오 세이프 박스",     "카카오뱅크",  3.90, 12, False,     10_000),
            SavingsProduct("토스 자유적금 플러스",   "토스뱅크",    4.00,  6, False,     10_000),
            SavingsProduct("우리 WON 정기예금",      "우리은행",    3.60, 12, False,    500_000),
            SavingsProduct("NH 올원 e-적금",         "NH농협은행",  3.80, 12, False,    100_000),
            SavingsProduct("하나 주거래 적금",        "하나은행",    3.70, 24, False,    100_000),
            SavingsProduct("케이뱅크 코드K 정기예금", "케이뱅크",   4.10, 12, False,    100_000),
        ]

    @staticmethod
    def _calc_monthly_payment(principal: float, annual_rate: float, term_months: int) -> float:
        """원리금균등상환 월 납입액 계산."""
        if annual_rate <= 0 or term_months <= 0:
            return principal / max(term_months, 1)
        r = annual_rate / 100.0 / 12.0
        return round(principal * r * (1 + r) ** term_months / ((1 + r) ** term_months - 1), 0)

    def compare_loans(
        self,
        amount: float,
        term_months: int,
        loan_type: Optional[str] = None,
    ) -> Dict[str, object]:
        return self._unverified_comparison("loan", amount, term_months)

    def _unverified_comparison(self, kind, amount, months):
        from trading.finance_product_intelligence import number
        try:
            number(amount, minimum=1)
            term = number(months, minimum=1, maximum=600)
            valid = term == int(term)
        except ValueError:
            valid = False
        return {"best": None, "alternatives": [], "status": "insufficient_evidence" if valid else "needs_input",
                "recommendation_available": False, "catalog_source_kind": self._catalog_source_kind(kind),
                "summary": "기존 카탈로그는 현재 판매 조건과 개인 적용 조건이 검증되지 않았습니다. 금융상품의 맞춤 비교에서 출처·유효기간이 있는 자료 또는 직접 받은 조건을 비교하세요." if valid else "금액과 기간을 직접 입력해 주세요. 임의의 조건을 대신 사용하지 않습니다."}

    def compare_insurances(self, budget_monthly: float | None, category: Optional[str] = None) -> Dict[str, object]:
        """Legacy catalogs are unverified examples, never suitability recommendations."""
        import math
        result = {
            "schema_version": "2.0.0", "best": None, "alternatives": [],
            "catalog_source_kind": self._catalog_source_kind("insurance"),
            "evidence_status": "unverified_catalog", "recommendation_available": False,
        }
        try:
            valid = not isinstance(budget_monthly, bool) and math.isfinite(float(budget_monthly)) and float(budget_monthly) > 0
        except (TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            return {**result, "status": "needs_input",
                    "summary": "월 보험 예산을 직접 입력하세요. 미입력 값을 임의로 채우지 않습니다."}
        candidates = [p for p in self.insurance_products
                      if math.isfinite(p.monthly_premium) and p.monthly_premium > 0
                      and p.monthly_premium <= float(budget_monthly)
                      and (category is None or p.category == category)]
        if not candidates:
            return {**result, "status": "no_matching_candidates",
                    "summary": "조건에 맞는 자료가 없습니다. 예산·종류 필터를 자동으로 완화하지 않습니다."}
        return {**result, "status": "insufficient_evidence",
                "matching_example_count": len(candidates),
                "summary": "기존 카탈로그는 약관·개인 보험료가 검증되지 않은 예시입니다. 보장 점수로 추천하지 않습니다. 내 보험 이해·비교에서 본인 자료를 등록해 확인하세요."}


    def compare_savings(self, principal: float, term_months: int) -> Dict[str, object]:
        return self._unverified_comparison("savings", principal, term_months)

    def apply_credit_adjustment_to_loans(self, result: Dict, credit_score: str) -> Dict:
        # Credit bands cannot establish a lender's personal offer.
        from copy import deepcopy
        return deepcopy(result)

    def apply_credit_adjustment_to_savings(self, result: Dict, credit_score: str) -> Dict:
        from copy import deepcopy
        return deepcopy(result)

    @staticmethod
    def _format_credit_label(credit_score: str) -> str:
        """신용도를 친화적 텍스트로 포맷"""
        if "좋음" in credit_score:
            return "좋음 🟢"
        elif "낮음" in credit_score:
            return "낮음 🔴"
        else:
            return "보통 🟡"
