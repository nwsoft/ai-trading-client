#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase F 생활금융 회귀 테스트.

커버 대상:
- LifeFinanceQualityTracker.build_quality_report()
- FinanceProductAdvisor 외부 JSON 카탈로그 로드 / 갱신
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from trading.life_finance_quality import LifeFinanceQualityTracker
from trading.life_finance_products import FinanceProductAdvisor


# ──────────────────────────────────────────────────────────
# LifeFinanceQualityTracker 테스트
# ──────────────────────────────────────────────────────────

class TestLifeFinanceQualityTracker:
    """LifeFinanceQualityTracker.build_quality_report() 검증"""

    def test_empty_events_returns_insufficient_data(self):
        tracker = LifeFinanceQualityTracker()
        result = tracker.build_quality_report([])
        assert result["status"] == "insufficient_data"
        assert result["total_events"] == 0
        assert result["recommendation_accuracy"] == 0.0
        assert result["conversion_rate"] == 0.0
        assert result["retention_rate"] == 0.0

    def test_none_events_treated_as_empty(self):
        tracker = LifeFinanceQualityTracker()
        result = tracker.build_quality_report(None)  # type: ignore[arg-type]
        assert result["status"] == "insufficient_data"

    def test_all_correct_recommendations(self):
        events = [
            {"event_type": "recommendation_shown", "session_id": "s1", "metadata": {"is_correct": True}},
            {"event_type": "recommendation_feedback", "session_id": "s2", "metadata": {"is_correct": True}},
        ]
        tracker = LifeFinanceQualityTracker()
        result = tracker.build_quality_report(events)
        assert result["status"] == "ok"
        assert result["recommendation_accuracy"] == 1.0

    def test_partial_correct_recommendations(self):
        events = [
            {"event_type": "recommendation_shown", "session_id": "s1", "metadata": {"is_correct": True}},
            {"event_type": "recommendation_shown", "session_id": "s2", "metadata": {"is_correct": False}},
            {"event_type": "recommendation_shown", "session_id": "s3", "metadata": {"is_correct": True}},
            {"event_type": "recommendation_shown", "session_id": "s4", "metadata": {"is_correct": False}},
        ]
        tracker = LifeFinanceQualityTracker()
        result = tracker.build_quality_report(events)
        assert result["recommendation_accuracy"] == pytest.approx(0.5, abs=1e-4)

    def test_conversion_rate_goal_created(self):
        events = [
            {"event_type": "assistant_response", "session_id": "s1", "metadata": {}},
            {"event_type": "assistant_response", "session_id": "s2", "metadata": {}},
            {"event_type": "goal_created", "session_id": "s3", "metadata": {}},
        ]
        tracker = LifeFinanceQualityTracker()
        result = tracker.build_quality_report(events)
        # 상담_노출=2(assistant_response), 상담_전환=1(goal_created)
        assert result["conversion_rate"] == pytest.approx(0.5, abs=1e-4)

    def test_conversion_rate_product_applied(self):
        events = [
            {"event_type": "recommendation_shown", "session_id": "s1", "metadata": {}},
            {"event_type": "product_applied", "session_id": "s1", "metadata": {}},
        ]
        tracker = LifeFinanceQualityTracker()
        result = tracker.build_quality_report(events)
        # recommendation_shown은 노출 카운트도 되고
        assert result["conversion_rate"] > 0.0

    def test_retention_rate_returning_sessions(self):
        events = [
            {"event_type": "assistant_response", "session_id": "s1", "metadata": {"is_returning": True}},
            {"event_type": "assistant_response", "session_id": "s2", "metadata": {"is_returning": False}},
            {"event_type": "assistant_response", "session_id": "s3", "metadata": {"is_returning": True}},
        ]
        tracker = LifeFinanceQualityTracker()
        result = tracker.build_quality_report(events)
        # 3개 세션 중 2개 재방문 → 2/3
        assert result["retention_rate"] == pytest.approx(2 / 3, abs=1e-4)

    def test_no_session_id_retention_is_zero(self):
        events = [
            {"event_type": "assistant_response", "session_id": "", "metadata": {}},
        ]
        tracker = LifeFinanceQualityTracker()
        result = tracker.build_quality_report(events)
        assert result["retention_rate"] == 0.0

    def test_status_ok_with_data(self):
        events = [
            {"event_type": "assistant_response", "session_id": "s1", "metadata": {}},
        ]
        tracker = LifeFinanceQualityTracker()
        result = tracker.build_quality_report(events)
        assert result["status"] == "ok"

    def test_rounding_precision(self):
        # 1/3 → 0.3333 (4자리)
        events = [
            {"event_type": "recommendation_shown", "session_id": "s1", "metadata": {"is_correct": True}},
            {"event_type": "recommendation_shown", "session_id": "s2", "metadata": {"is_correct": False}},
            {"event_type": "recommendation_shown", "session_id": "s3", "metadata": {"is_correct": False}},
        ]
        tracker = LifeFinanceQualityTracker()
        result = tracker.build_quality_report(events)
        assert result["recommendation_accuracy"] == round(1 / 3, 4)

    def test_to_float_helper_robustness(self):
        tracker = LifeFinanceQualityTracker()
        assert tracker._to_float(None) == 0.0
        assert tracker._to_float("bad_value") == 0.0
        assert tracker._to_float(3.5) == pytest.approx(3.5)
        assert tracker._to_float("2.0") == pytest.approx(2.0)
        assert tracker._to_float(None, default=99.0) == pytest.approx(99.0)


# ──────────────────────────────────────────────────────────
# FinanceProductAdvisor 외부 JSON 카탈로그 로드 테스트
# ──────────────────────────────────────────────────────────

@pytest.fixture
def tmp_catalog_dir(tmp_path: Path) -> Path:
    """임시 카탈로그 디렉터리 — 테스트 격리용"""
    return tmp_path


def _write_loan_catalog(path: Path, records: List[Dict[str, Any]]) -> None:
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


def _write_insurance_catalog(path: Path, records: List[Dict[str, Any]]) -> None:
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


def _write_savings_catalog(path: Path, records: List[Dict[str, Any]]) -> None:
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


class TestFinanceProductAdvisorExternalCatalog:
    """외부 JSON 파일로부터 카탈로그 로드 검증"""

    def test_load_loans_from_json(self, tmp_catalog_dir: Path):
        loan_file = tmp_catalog_dir / "loans.json"
        _write_loan_catalog(loan_file, [
            {"name": "Test대출", "provider": "테스트은행", "annual_rate": 3.0,
             "max_amount": 500_000_000, "term_months": 120, "fee_rate": 0.1},
        ])
        advisor = FinanceProductAdvisor(
            catalog_paths={"loan": str(loan_file)},
            auto_refresh_interval=0,
        )
        assert len(advisor.loan_products) == 1
        assert advisor.loan_products[0].name == "Test대출"
        assert advisor.loan_products[0].annual_rate == pytest.approx(3.0)

    def test_load_insurances_from_json(self, tmp_catalog_dir: Path):
        ins_file = tmp_catalog_dir / "insurances.json"
        _write_insurance_catalog(ins_file, [
            {"name": "Test보험", "provider": "테스트생명", "monthly_premium": 30000,
             "coverage_score": 80, "deductible": 100000, "category": "건강"},
        ])
        advisor = FinanceProductAdvisor(
            catalog_paths={"insurance": str(ins_file)},
            auto_refresh_interval=0,
        )
        assert len(advisor.insurance_products) == 1
        assert advisor.insurance_products[0].category == "건강"

    def test_load_savings_from_json(self, tmp_catalog_dir: Path):
        sav_file = tmp_catalog_dir / "savings.json"
        _write_savings_catalog(sav_file, [
            {"name": "Test예금", "provider": "테스트은행", "annual_rate": 4.5,
             "term_months": 12, "tax_free": True, "min_amount": 100000},
        ])
        advisor = FinanceProductAdvisor(
            catalog_paths={"savings": str(sav_file)},
            auto_refresh_interval=0,
        )
        assert len(advisor.savings_products) == 1
        assert advisor.savings_products[0].tax_free is True

    def test_fallback_to_builtin_when_file_absent(self, tmp_catalog_dir: Path):
        """파일 없으면 내장 샘플 반환"""
        advisor = FinanceProductAdvisor(
            catalog_paths={"loan": str(tmp_catalog_dir / "nonexistent.json")},
            auto_refresh_interval=0,
        )
        # 내장 샘플에 최소 1건 이상
        assert len(advisor.loan_products) >= 1

    def test_catalog_source_reflects_file_when_loaded(self, tmp_catalog_dir: Path):
        loan_file = tmp_catalog_dir / "loans.json"
        _write_loan_catalog(loan_file, [
            {"name": "S대출", "provider": "S은행", "annual_rate": 3.5,
             "max_amount": 200_000_000, "term_months": 60, "fee_rate": 0.0},
        ])
        advisor = FinanceProductAdvisor(
            catalog_paths={"loan": str(loan_file)},
            auto_refresh_interval=0,
        )
        status = advisor.get_catalog_status()
        assert status["loan"]["source"] == str(loan_file)
        assert status["loan"]["source_kind"] == "operator_catalog"
        assert status["loan"]["exists"] is True

    def test_catalog_source_builtin_when_file_absent(self, tmp_catalog_dir: Path):
        advisor = FinanceProductAdvisor(
            catalog_paths={"loan": str(tmp_catalog_dir / "missing.json")},
            auto_refresh_interval=0,
        )
        # _load_catalog_records는 파일 없으면 catalog_sources에 "built_in_sample" 저장
        status = advisor.get_catalog_status()
        assert status["loan"]["source"] == "built_in_sample"
        assert status["loan"]["source_kind"] == "built_in_fallback"

    def test_force_refresh_reloads_products(self, tmp_catalog_dir: Path):
        loan_file = tmp_catalog_dir / "loans.json"
        _write_loan_catalog(loan_file, [
            {"name": "초기대출", "provider": "초기은행", "annual_rate": 3.0,
             "max_amount": 100_000_000, "term_months": 60, "fee_rate": 0.0},
        ])
        advisor = FinanceProductAdvisor(
            catalog_paths={"loan": str(loan_file)},
            auto_refresh_interval=0,
        )
        assert advisor.loan_products[0].name == "초기대출"

        # 파일 내용 교체 후 강제 재로드
        _write_loan_catalog(loan_file, [
            {"name": "갱신대출", "provider": "갱신은행", "annual_rate": 4.0,
             "max_amount": 200_000_000, "term_months": 60, "fee_rate": 0.0},
        ])
        result = advisor.force_refresh()
        assert result is True
        assert advisor.loan_products[0].name == "갱신대출"

    def test_refresh_if_changed_detects_mtime_change(self, tmp_catalog_dir: Path):
        loan_file = tmp_catalog_dir / "loans.json"
        _write_loan_catalog(loan_file, [
            {"name": "원본대출", "provider": "원본은행", "annual_rate": 3.0,
             "max_amount": 100_000_000, "term_months": 60, "fee_rate": 0.0},
        ])
        advisor = FinanceProductAdvisor(
            catalog_paths={"loan": str(loan_file)},
            auto_refresh_interval=0,
        )
        # 파일 내용 교체 + mtime 강제 변경
        time.sleep(0.01)
        _write_loan_catalog(loan_file, [
            {"name": "변경대출", "provider": "변경은행", "annual_rate": 5.0,
             "max_amount": 300_000_000, "term_months": 60, "fee_rate": 0.0},
        ])
        os.utime(loan_file, None)  # mtime 현재 시각으로 갱신

        changed = advisor.refresh_if_changed()
        assert changed is True
        assert advisor.loan_products[0].name == "변경대출"

    def test_refresh_if_changed_no_change(self, tmp_catalog_dir: Path):
        loan_file = tmp_catalog_dir / "loans.json"
        _write_loan_catalog(loan_file, [
            {"name": "안변대출", "provider": "안변은행", "annual_rate": 3.0,
             "max_amount": 100_000_000, "term_months": 60, "fee_rate": 0.0},
        ])
        advisor = FinanceProductAdvisor(
            catalog_paths={"loan": str(loan_file)},
            auto_refresh_interval=0,
        )
        # 파일 변경 없이 호출 → False
        changed = advisor.refresh_if_changed()
        assert changed is False

    def test_compare_loans_uses_external_catalog(self, tmp_catalog_dir: Path):
        loan_file = tmp_catalog_dir / "loans.json"
        _write_loan_catalog(loan_file, [
            {"name": "저금리론", "provider": "A은행", "annual_rate": 2.5,
             "max_amount": 500_000_000, "term_months": 120, "fee_rate": 0.0},
            {"name": "고금리론", "provider": "B은행", "annual_rate": 6.0,
             "max_amount": 500_000_000, "term_months": 120, "fee_rate": 0.0},
        ])
        advisor = FinanceProductAdvisor(
            catalog_paths={"loan": str(loan_file)},
            auto_refresh_interval=0,
        )
        result = advisor.compare_loans(amount=100_000_000, term_months=60)
        assert result["best"]["name"] == "저금리론"
        assert result["catalog_source"] == str(loan_file)

    def test_invalid_json_falls_back_without_stopping_app(self, tmp_catalog_dir: Path):
        """손상된 운영자 파일도 앱을 중단하지 않고 예비 데이터로 대체"""
        loan_file = tmp_catalog_dir / "loans.json"
        loan_file.write_text("NOT_VALID_JSON", encoding="utf-8")

        advisor = FinanceProductAdvisor(
            catalog_paths={"loan": str(loan_file)},
            auto_refresh_interval=0,
        )
        assert advisor.loan_products
        assert advisor.get_catalog_status()["loan"]["source_kind"] == "built_in_fallback"


class TestFinanceProductAdvisorBuiltinCatalog:
    """내장 샘플 카탈로그로 기본 동작 검증"""

    def setup_method(self):
        self.advisor = FinanceProductAdvisor(auto_refresh_interval=0)

    def test_builtin_loans_loaded(self):
        # data/finance_products/loans.json 또는 내장 샘플 중 하나에서 로드
        assert len(self.advisor.loan_products) >= 1

    def test_builtin_insurances_loaded(self):
        assert len(self.advisor.insurance_products) >= 1

    def test_builtin_savings_loaded(self):
        assert len(self.advisor.savings_products) >= 1

    def test_get_catalog_status_has_keys(self):
        status = self.advisor.get_catalog_status()
        assert "loan" in status
        assert "insurance" in status
        assert "savings" in status
        for key in ("source", "path", "exists", "mtime"):
            assert key in status["loan"]

    def test_stop_auto_refresh_no_error(self):
        advisor = FinanceProductAdvisor(auto_refresh_interval=0)
        advisor.stop_auto_refresh()  # 에러 없이 실행되어야 함
