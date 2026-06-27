"""trading/tax_calculation_service.py 단위 테스트 (2026년 세법 기준)."""

import pytest
from trading.tax_calculation_service import (
    calc_earned_income_deduction,
    calc_income_tax,
    calc_card_income_deduction,
    calc_medical_tax_credit,
    calc_education_tax_credit,
    calc_donation_tax_credit,
    calc_year_end_tax_settlement,
    check_financial_income_comprehensive_tax,
    calc_financial_investment_tax,
    compare_tax_saving_accounts,
    generate_tax_optimization_summary,
)


# ─────────────────────────────────────────────────────────────
# 근로소득공제
# ─────────────────────────────────────────────────────────────

class TestEarnedIncomeDeduction:
    def test_below_5m(self):
        # 3,000,000원 × 100% = 3,000,000
        assert calc_earned_income_deduction(3_000_000) == 3_000_000.0

    def test_at_15m(self):
        # 5,000,000 + (15,000,000 - 5,000,000) × 50% = 10,000,000
        assert calc_earned_income_deduction(15_000_000) == 10_000_000.0

    def test_at_45m(self):
        # 10,000,000 + (45,000,000 - 15,000,000) × 30% = 19,000,000
        assert calc_earned_income_deduction(45_000_000) == 19_000_000.0

    def test_at_100m(self):
        # 16,000,000 + (100,000,000 - 45,000,000) × 20% = 27,000,000
        assert calc_earned_income_deduction(100_000_000) == 27_000_000.0

    def test_negative_salary_returns_zero(self):
        assert calc_earned_income_deduction(-1_000_000) == 0.0

    def test_zero_salary(self):
        assert calc_earned_income_deduction(0) == 0.0


# ─────────────────────────────────────────────────────────────
# 산출세액
# ─────────────────────────────────────────────────────────────

class TestIncomeTax:
    def test_zero(self):
        assert calc_income_tax(0) == 0.0

    def test_6pct_bracket(self):
        # 10,000,000 × 6% = 600,000
        assert calc_income_tax(10_000_000) == 600_000.0

    def test_15pct_bracket(self):
        # 30,000,000 × 15% - 1,260,000 = 3,240,000
        assert calc_income_tax(30_000_000) == 3_240_000.0

    def test_35pct_bracket(self):
        # 100,000,000 × 35% - 15,440,000 = 19,560,000
        assert calc_income_tax(100_000_000) == 19_560_000.0

    def test_negative_returns_zero(self):
        assert calc_income_tax(-1) == 0.0


# ─────────────────────────────────────────────────────────────
# 신용카드 소득공제
# ─────────────────────────────────────────────────────────────

class TestCardIncomeDeduction:
    def test_below_threshold_no_deduction(self):
        # 총급여 4000만, 25% = 1000만. 사용액 800만 → 공제 없음
        result = calc_card_income_deduction(40_000_000, credit_card_amount=8_000_000)
        assert result['deduction_amount'] == 0.0

    def test_credit_card_excess(self):
        # 총급여 4000만, threshold=1000만
        # 신용카드 1500만 → 초과 500만 × 15% = 75만
        result = calc_card_income_deduction(40_000_000, credit_card_amount=15_000_000)
        assert result['deduction_amount'] == 750_000.0

    def test_debit_higher_rate(self):
        # 총급여 4000만, threshold=1000만
        # 체크카드만 1500만 → 초과 500만 × 30% = 150만
        result = calc_card_income_deduction(40_000_000, debit_cash_amount=15_000_000)
        assert result['deduction_amount'] == 1_500_000.0

    def test_max_limit_applied(self):
        # 한도 초과 시 300만으로 cap
        result = calc_card_income_deduction(40_000_000, debit_cash_amount=50_000_000)
        assert result['deduction_amount'] == 3_000_000.0


# ─────────────────────────────────────────────────────────────
# 의료비 세액공제
# ─────────────────────────────────────────────────────────────

class TestMedicalTaxCredit:
    def test_below_min_threshold(self):
        # 총급여 4000만, 3% = 120만. 의료비 100만 → 공제 없음
        result = calc_medical_tax_credit(40_000_000, 1_000_000)
        assert result['tax_credit'] == 0.0

    def test_above_threshold(self):
        # 총급여 4000만, min=120만. 의료비 220만 → 초과 100만 × 15% = 15만
        result = calc_medical_tax_credit(40_000_000, 2_200_000)
        assert result['tax_credit'] == 150_000.0

    def test_large_expense(self):
        result = calc_medical_tax_credit(50_000_000, 5_000_000)
        # min = 1,500,000. 초과 3,500,000 × 15% = 525,000
        assert result['tax_credit'] == 525_000.0


# ─────────────────────────────────────────────────────────────
# 교육비 세액공제
# ─────────────────────────────────────────────────────────────

class TestEducationTaxCredit:
    def test_college(self):
        # 500만 × 15% = 75만
        result = calc_education_tax_credit(5_000_000, 'college')
        assert result['tax_credit'] == 750_000.0

    def test_college_limit(self):
        # 한도 900만 초과 → 900만 × 15% = 135만
        result = calc_education_tax_credit(12_000_000, 'college')
        assert result['tax_credit'] == 1_350_000.0
        assert result['deductible_amount'] == 9_000_000.0

    def test_elementary_limit(self):
        # 500만 → 한도 300만 적용 → 300만 × 15% = 45만
        result = calc_education_tax_credit(5_000_000, 'elementary')
        assert result['tax_credit'] == 450_000.0


# ─────────────────────────────────────────────────────────────
# 기부금 세액공제
# ─────────────────────────────────────────────────────────────

class TestDonationTaxCredit:
    def test_below_10m(self):
        # 500만 × 15% = 75만
        result = calc_donation_tax_credit(5_000_000)
        assert result['tax_credit'] == 750_000.0

    def test_above_10m(self):
        # 1000만 × 15% + 500만 × 30% = 150만 + 150만 = 300만
        result = calc_donation_tax_credit(15_000_000)
        assert result['tax_credit'] == 3_000_000.0

    def test_zero_donation(self):
        result = calc_donation_tax_credit(0)
        assert result['tax_credit'] == 0.0


# ─────────────────────────────────────────────────────────────
# 연말정산 종합
# ─────────────────────────────────────────────────────────────

class TestYearEndTaxSettlement:
    def test_returns_all_keys(self):
        result = calc_year_end_tax_settlement(annual_salary=50_000_000)
        expected_keys = {
            'annual_salary', 'earned_income_deduction', 'personal_deduction',
            'card_income_deduction', 'taxable_income', 'base_tax',
            'medical_tax_credit', 'education_tax_credit', 'donation_tax_credit',
            'pension_tax_credit', 'total_tax_credit', 'final_tax',
            'total_deduction_effect', 'disclaimer',
        }
        assert expected_keys.issubset(result.keys())

    def test_final_tax_nonnegative(self):
        result = calc_year_end_tax_settlement(
            annual_salary=30_000_000,
            pension_savings=6_000_000,
            irp_contribution=3_000_000,
            medical_expense=3_000_000,
        )
        assert result['final_tax'] >= 0.0

    def test_more_deductions_lower_tax(self):
        base = calc_year_end_tax_settlement(annual_salary=50_000_000)
        with_pension = calc_year_end_tax_settlement(
            annual_salary=50_000_000, pension_savings=6_000_000
        )
        assert with_pension['final_tax'] <= base['final_tax']

    def test_pension_credit_rate_high_earner(self):
        # 총급여 6000만 → 13.2%
        result = calc_year_end_tax_settlement(
            annual_salary=60_000_000, pension_savings=6_000_000
        )
        # 6,000,000 × 13.2% = 792,000
        assert result['pension_tax_credit'] == pytest.approx(792_000, rel=0.01)

    def test_pension_credit_rate_low_earner(self):
        # 총급여 4000만 → 16.5%
        result = calc_year_end_tax_settlement(
            annual_salary=40_000_000, pension_savings=6_000_000
        )
        # 6,000,000 × 16.5% = 990,000
        assert result['pension_tax_credit'] == pytest.approx(990_000, rel=0.01)

    def test_disclaimer_present(self):
        result = calc_year_end_tax_settlement(annual_salary=40_000_000)
        assert '참고용' in result['disclaimer']


# ─────────────────────────────────────────────────────────────
# 금융소득종합과세
# ─────────────────────────────────────────────────────────────

class TestFinancialIncomeTax:
    def test_below_threshold(self):
        result = check_financial_income_comprehensive_tax(
            interest_income=10_000_000, dividend_income=5_000_000
        )
        assert result['subject_to_comprehensive_tax'] is False
        assert result['excess_amount'] == 0.0

    def test_above_threshold(self):
        result = check_financial_income_comprehensive_tax(
            interest_income=15_000_000, dividend_income=10_000_000
        )
        assert result['subject_to_comprehensive_tax'] is True
        assert result['total_financial_income'] == 25_000_000.0
        assert result['excess_amount'] == 5_000_000.0

    def test_message_includes_amount(self):
        result = check_financial_income_comprehensive_tax(5_000_000, 0)
        assert '5,000,000' in result['message'] or '5000000' in result['message']

    def test_exactly_at_threshold_not_subject(self):
        result = check_financial_income_comprehensive_tax(20_000_000, 0)
        assert result['subject_to_comprehensive_tax'] is False

    def test_withholding_tax_calculation(self):
        result = check_financial_income_comprehensive_tax(10_000_000, 0)
        # 10,000,000 × 15.4% = 1,540,000
        assert result['withholding_tax'] == pytest.approx(1_540_000, rel=0.01)


# ─────────────────────────────────────────────────────────────
# 금융투자소득세
# ─────────────────────────────────────────────────────────────

class TestFinancialInvestmentTax:
    def test_zero_profit(self):
        result = calc_financial_investment_tax()
        assert result['total_tax'] == 0.0
        assert result['effective_rate'] == 0.0

    def test_within_domestic_deduction(self):
        # 국내 주식 500만 이하 → 기본공제로 세금 0
        result = calc_financial_investment_tax(domestic_stock_profit=5_000_000)
        assert result['domestic_tax'] == 0.0

    def test_domestic_basic_deduction(self):
        # 국내 주식 1500만 → 과세표준 1000만 × 20% = 200만
        result = calc_financial_investment_tax(domestic_stock_profit=15_000_000)
        assert result['domestic_tax'] == 2_000_000.0

    def test_overseas_basic_deduction(self):
        # 해외 주식 1000만 → 공제 250만, 과세 750만 × 20% = 150만
        result = calc_financial_investment_tax(overseas_stock_profit=10_000_000)
        assert result['overseas_tax'] == 1_500_000.0

    def test_high_rate_bracket(self):
        # 국내 3.5억 → 3억 × 20% + 0.5억 × 25% - 기본공제500만 적용
        result = calc_financial_investment_tax(domestic_stock_profit=355_000_000)
        # 과세표준 = 355,000,000 - 5,000,000 = 350,000,000
        # 300,000,000 × 20% + 50,000,000 × 25% = 60,000,000 + 12,500,000 = 72,500,000
        assert result['domestic_tax'] == 72_500_000.0

    def test_returns_disclaimer(self):
        result = calc_financial_investment_tax(domestic_stock_profit=10_000_000)
        assert '참고용' in result['disclaimer']


# ─────────────────────────────────────────────────────────────
# ISA / 연금저축 / IRP 비교
# ─────────────────────────────────────────────────────────────

class TestTaxSavingAccountComparison:
    def test_returns_three_scenarios(self):
        result = compare_tax_saving_accounts(
            annual_salary=50_000_000,
            annual_investment=5_000_000,
            investment_years=5,
            expected_return_rate=0.05,
        )
        assert set(result['scenarios'].keys()) == {'ISA', '연금저축', 'IRP'}

    def test_best_scenario_in_result(self):
        result = compare_tax_saving_accounts(50_000_000, 9_000_000, 5, 0.04)
        assert result['best_scenario'] in {'ISA', '연금저축', 'IRP'}

    def test_high_earner_lower_credit_rate(self):
        result = compare_tax_saving_accounts(60_000_000, 6_000_000, 3, 0.04)
        assert result['salary_tax_credit_rate'] == pytest.approx(0.132)

    def test_low_earner_higher_credit_rate(self):
        result = compare_tax_saving_accounts(40_000_000, 6_000_000, 3, 0.04)
        assert result['salary_tax_credit_rate'] == pytest.approx(0.165)

    def test_preferential_isa_higher_exempt(self):
        r_general = compare_tax_saving_accounts(40_000_000, 5_000_000, 3, 0.05, 'general')
        r_pref = compare_tax_saving_accounts(40_000_000, 5_000_000, 3, 0.05, 'preferential')
        isa_benefit_general = r_general['scenarios']['ISA']['total_benefit']
        isa_benefit_pref = r_pref['scenarios']['ISA']['total_benefit']
        assert isa_benefit_pref >= isa_benefit_general


# ─────────────────────────────────────────────────────────────
# 절세 시나리오 종합 요약
# ─────────────────────────────────────────────────────────────

class TestTaxOptimizationSummary:
    def test_returns_required_keys(self):
        result = generate_tax_optimization_summary(annual_salary=50_000_000)
        assert 'current_tax_credit_total' in result
        assert 'suggestions' in result
        assert 'disclaimer' in result

    def test_unused_pension_room_calculated(self):
        # 연금저축 0 → 미활용 여지 6,000,000
        result = generate_tax_optimization_summary(annual_salary=50_000_000)
        assert result['unused_pension_savings_room'] == 6_000_000.0

    def test_full_pension_no_pension_suggestion(self):
        result = generate_tax_optimization_summary(
            annual_salary=50_000_000,
            pension_savings=6_000_000,
            irp_contribution=3_000_000,
        )
        categories = [s['category'] for s in result['suggestions']]
        assert 'pension' not in categories

    def test_financial_income_alert_triggered(self):
        result = generate_tax_optimization_summary(
            annual_salary=50_000_000,
            interest_income=15_000_000,
            dividend_income=10_000_000,
        )
        assert result['financial_income_alert'] is True

    def test_financial_income_no_alert(self):
        result = generate_tax_optimization_summary(
            annual_salary=50_000_000,
            interest_income=5_000_000,
            dividend_income=3_000_000,
        )
        assert result['financial_income_alert'] is False

    def test_suggestions_are_list(self):
        result = generate_tax_optimization_summary(annual_salary=30_000_000)
        assert isinstance(result['suggestions'], list)

    def test_disclaimer_in_result(self):
        result = generate_tax_optimization_summary(annual_salary=40_000_000)
        assert '참고용' in result['disclaimer']
