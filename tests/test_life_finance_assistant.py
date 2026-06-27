#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
생활금융 어시스턴트 회귀 테스트
- 의도 우선순위(리포트/목표조회/보험추천)
- 금액 단위 파싱(천/만/억)
- 금융상품 비교 커맨드 실행
"""

import asyncio
from pathlib import Path

from trading.life_finance import LifeFinanceManager
from trading.life_finance_assistant import FinanceIntentParser, FinanceIntentType, LifeFinanceAssistant


def _build_assistant(tmp_path: Path) -> LifeFinanceAssistant:
    data_dir = tmp_path / "lf_data"
    backup_dir = tmp_path / "lf_backup"
    sync_dir = tmp_path / "lf_sync"
    manager = LifeFinanceManager(
        data_dir=str(data_dir),
        backup_dir=str(backup_dir),
        external_sync_dir=str(sync_dir),
    )
    return LifeFinanceAssistant(manager)


class TestFinanceIntentParserRegression:
    def test_extract_amount_unit_thousand(self):
        assert FinanceIntentParser._extract_amount("카페에서 5천원 썼어") == 5000

    def test_extract_amount_unit_ten_thousand(self):
        assert FinanceIntentParser._extract_amount("적금에 15.5만 넣을래") == 155000

    def test_extract_amount_unit_hundred_million(self):
        assert FinanceIntentParser._extract_amount("대출은 3억 필요해") == 300000000

    def test_monthly_report_priority_over_expense(self):
        parsed = FinanceIntentParser.parse("이번 달 리포트 보여줘")
        assert parsed.intent == FinanceIntentType.MONTHLY_REPORT

    def test_goal_list_priority_over_goal_create(self):
        parsed = FinanceIntentParser.parse("목표는 뭐가 있어?")
        assert parsed.intent == FinanceIntentType.LIST_GOALS

    def test_compare_insurance_priority_over_spending_advice(self):
        parsed = FinanceIntentParser.parse("보험 추천해줘")
        assert parsed.intent == FinanceIntentType.COMPARE_INSURANCE


class TestLifeFinanceAssistantCompareCommands:
    def test_process_command_compare_loan(self, tmp_path):
        assistant = _build_assistant(tmp_path)
        result = asyncio.run(assistant.process_command("대출 비교해줘"))

        assert result["intent"] == "compare_loan"
        assert result["action_taken"] == "compare_loan"
        assert "대출 상품 비교 결과" in result["response"]
        assert isinstance(result.get("data"), dict)

    def test_process_command_compare_insurance(self, tmp_path):
        assistant = _build_assistant(tmp_path)
        result = asyncio.run(assistant.process_command("보험 추천해줘"))

        assert result["intent"] == "compare_insurance"
        assert result["action_taken"] == "compare_insurance"
        assert "보험 상품 비교 결과" in result["response"]
        assert isinstance(result.get("data"), dict)

    def test_process_command_compare_savings(self, tmp_path):
        assistant = _build_assistant(tmp_path)
        result = asyncio.run(assistant.process_command("예금 상품 비교해줘"))

        assert result["intent"] == "compare_savings_product"
        assert result["action_taken"] == "compare_savings_product"
        assert "예적금 상품 비교 결과" in result["response"]
        assert isinstance(result.get("data"), dict)


class TestPhase1CreditAdjustment:
    """Phase 1: 신용도/위험도 개인화 회귀 테스트"""

    def test_loan_credit_good_lowers_rate(self, tmp_path):
        """신용도 좋음 → 대출 금리 인하(-0.5%) 반영"""
        assistant = _build_assistant(tmp_path)
        result = asyncio.run(
            assistant.process_command("대출 비교해줘", credit_score="좋음 (750~900)")
        )
        assert result["action_taken"] == "compare_loan"
        best = result["data"]["best"]
        assert "adjusted_annual_rate" in best
        assert best["adjusted_annual_rate"] == best["annual_rate"] - 0.5
        assert "좋음 🟢" in result["response"] or "신용도" in result["response"]

    def test_loan_credit_low_raises_rate(self, tmp_path):
        """신용도 낮음 → 대출 금리 인상(+0.5%) 반영"""
        assistant = _build_assistant(tmp_path)
        result = asyncio.run(
            assistant.process_command("대출 비교해줘", credit_score="낮음 (~650)")
        )
        best = result["data"]["best"]
        assert "adjusted_annual_rate" in best
        assert best["adjusted_annual_rate"] == best["annual_rate"] + 0.5

    def test_loan_credit_normal_no_adjustment(self, tmp_path):
        """신용도 보통 → 금리 조정 없음(adjusted_annual_rate 없음)"""
        assistant = _build_assistant(tmp_path)
        result = asyncio.run(
            assistant.process_command("대출 비교해줘", credit_score="보통 (650~750)")
        )
        best = result["data"]["best"]
        # 보통은 adjustment=0.0 → adjusted_annual_rate 키 없음
        assert "adjusted_annual_rate" not in best

    def test_savings_credit_good_raises_rate(self, tmp_path):
        """신용도 좋음 → 예적금 우대 금리(+0.3%) 반영"""
        assistant = _build_assistant(tmp_path)
        result = asyncio.run(
            assistant.process_command("예금 상품 비교해줘", credit_score="좋음 (750~900)")
        )
        best = result["data"]["best"]
        assert "adjusted_annual_rate" in best
        assert best["adjusted_annual_rate"] == best["annual_rate"] + 0.3

    def test_savings_credit_low_lowers_rate(self, tmp_path):
        """신용도 낮음 → 예적금 금리 불이익(-0.1%) 반영"""
        assistant = _build_assistant(tmp_path)
        result = asyncio.run(
            assistant.process_command("예금 상품 비교해줘", credit_score="낮음 (~650)")
        )
        best = result["data"]["best"]
        assert "adjusted_annual_rate" in best
        assert best["adjusted_annual_rate"] == best["annual_rate"] - 0.1

    def test_credit_adjustment_no_credit_score(self, tmp_path):
        """신용도 미전달 → 조정 없이 일반 결과 반환"""
        assistant = _build_assistant(tmp_path)
        result = asyncio.run(assistant.process_command("대출 비교해줘"))
        best = result["data"]["best"]
        assert "adjusted_annual_rate" not in best

    def test_product_advisor_credit_adjustment_directly(self):
        """FinanceProductAdvisor.apply_credit_adjustment_to_loans 직접 검증"""
        from trading.life_finance_products import FinanceProductAdvisor
        advisor = FinanceProductAdvisor()
        base = advisor.compare_loans(amount=100_000_000, term_months=24)
        base_rate = base["best"]["annual_rate"]

        good = advisor.apply_credit_adjustment_to_loans(base, "좋음 (750~900)")
        assert good["best"]["adjusted_annual_rate"] == base_rate - 0.5

        low = advisor.apply_credit_adjustment_to_loans(base, "낮음 (~650)")
        assert low["best"]["adjusted_annual_rate"] == base_rate + 0.5
