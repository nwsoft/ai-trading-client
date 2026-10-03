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
        assert result["data"]["status"] == "needs_input"
        assert result["data"]["best"] is None
        assert isinstance(result.get("data"), dict)

    def test_process_command_compare_insurance(self, tmp_path):
        assistant = _build_assistant(tmp_path)
        result = asyncio.run(assistant.process_command("보험 추천해줘"))

        assert result["intent"] == "compare_insurance"
        assert result["action_taken"] == "compare_insurance"
        assert "보험 자료 확인" in result["response"]
        assert "직접 입력" in result["response"]
        assert result["data"]["best"] is None
        assert isinstance(result.get("data"), dict)

    def test_process_command_compare_savings(self, tmp_path):
        assistant = _build_assistant(tmp_path)
        result = asyncio.run(assistant.process_command("예금 상품 비교해줘"))

        assert result["intent"] == "compare_savings_product"
        assert result["action_taken"] == "compare_savings_product"
        assert result["data"]["status"] == "needs_input"
        assert result["data"]["best"] is None
        assert isinstance(result.get("data"), dict)


class TestCreditAdjustmentEvidence:
    """Credit bands must never invent personal quotes or mutate supplied evidence."""
    def test_no_credit_band_invents_a_quote(self, tmp_path):
        assistant = _build_assistant(tmp_path)
        for question in ("대출 비교해줘", "예금 상품 비교해줘"):
            for credit in ("좋음 (750~900)", "보통 (650~750)", "낮음 (~650)"):
                result = asyncio.run(assistant.process_command(question, credit_score=credit))
                assert result["data"]["best"] is None
                assert "예상 금리" not in result["response"]

    def test_quote_is_not_adjusted_or_mutated(self):
        from trading.life_finance_products import FinanceProductAdvisor
        advisor = FinanceProductAdvisor(auto_refresh_interval=0)
        original = {"best": {"annual_rate": 3.5}, "summary": "confirmed quote"}
        for function in (advisor.apply_credit_adjustment_to_loans, advisor.apply_credit_adjustment_to_savings):
            for credit in ("좋음 (750~900)", "낮음 (~650)"):
                adjusted = function(original, credit)
                assert adjusted == original
                adjusted["best"]["annual_rate"] = 99
                assert original["best"]["annual_rate"] == 3.5
