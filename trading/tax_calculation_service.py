#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""세무 계산 및 절세 시나리오 서비스 (2026년 기준).

책임 경계:
- NoahAI는 계산·요약·설명·경고까지만 제공한다.
- 법적 신고·제출·납부 행위는 항상 사용자 또는 세무 전문가 책임이다.
- 본 모듈의 계산 결과는 참고용이며, 정확한 세금은 국세청 홈택스 또는
  세무사 확인을 권장한다.

제공 기능:
1. 근로소득 연말정산 주요 세액공제 계산
2. 금융소득종합과세 해당 여부 판정
3. 금융투자소득세 (금투세) 예상 계산
4. ISA / 연금저축 / IRP 절세 효과 비교
5. 절세 시나리오 종합 요약
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────
# 2026년 기준 세율표 / 공제 한도
# ─────────────────────────────────────────────────────────────

# 근로소득세 기본세율 (과세표준 → (세율, 누진공제액))
INCOME_TAX_BRACKETS = [
    (14_000_000,   0.06,          0),
    (50_000_000,   0.15,   1_260_000),
    (88_000_000,   0.24,   5_760_000),
    (150_000_000,  0.35,  15_440_000),
    (300_000_000,  0.38,  19_940_000),
    (500_000_000,  0.40,  25_940_000),
    (1_000_000_000,0.42,  35_940_000),
    (float('inf'), 0.45,  65_940_000),
]

# 근로소득공제율 (급여 → 공제액 계산)
EARNED_INCOME_DEDUCTION = [
    (5_000_000,    1.00, 0),
    (15_000_000,   0.50, 5_000_000),
    (45_000_000,   0.30, 10_000_000),
    (100_000_000,  0.20, 16_000_000),
    (float('inf'), 0.02, 36_000_000),
]

# 세액공제 한도 (2026년 기준)
CARD_DEDUCTION_RATE_CREDIT = 0.15      # 신용카드 소득공제율
CARD_DEDUCTION_RATE_DEBIT  = 0.30      # 체크카드 / 현금영수증 공제율
CARD_DEDUCTION_BASE_PCT    = 0.25      # 총급여의 25% 초과분 공제
CARD_DEDUCTION_MAX         = 3_000_000 # 소득공제 한도 (총급여 7천만↓ 기준)

MEDICAL_DEDUCTION_RATE     = 0.15      # 의료비 세액공제율
MEDICAL_DEDUCTION_MIN_PCT  = 0.03      # 총급여의 3% 초과분부터

EDUCATION_DEDUCTION_RATE   = 0.15      # 교육비 세액공제율
EDUCATION_DEDUCTION_MAX    = 9_000_000 # 한도 (대학생 1인)

DONATION_DEDUCTION_RATE    = 0.15      # 기부금 세액공제율
DONATION_DEDUCTION_RATE_HI = 0.30      # 1000만원 초과분

PENSION_SAVINGS_MAX        = 6_000_000  # 연금저축 세액공제 한도
IRP_MAX                    = 9_000_000  # IRP 포함 합산 한도
ISA_EXEMPT_GENERAL         = 2_000_000  # ISA 일반형 비과세 한도
ISA_EXEMPT_PREFERENTIAL    = 4_000_000  # ISA 서민형/농어민 비과세 한도
ISA_TERM_MIN_MONTHS        = 36         # ISA 최소 유지기간 (개월)

FINANCIAL_INCOME_TAX_THRESHOLD = 20_000_000  # 금융소득종합과세 기준 금액
FINANCIAL_INCOME_WITHHOLDING   = 0.154       # 금융소득 원천징수세율 (소득세+지방세)

KFIS_TAX_RATE              = 0.20       # 금융투자소득세율 (기본)
KFIS_TAX_RATE_HI           = 0.25       # 금투세 고율 구간
KFIS_TAX_THRESHOLD         = 50_000_000 # 금투세 과세 기준 연간 이익
KFIS_BASIC_DEDUCTION       = 5_000_000  # 금투세 기본공제 (국내 주식)


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


# ─────────────────────────────────────────────────────────────
# 1. 근로소득 세액공제 계산
# ─────────────────────────────────────────────────────────────

def calc_earned_income_deduction(annual_salary: float) -> float:
    """근로소득공제 계산 (급여 → 과세표준에서 빼는 공제액)."""
    s = max(0.0, _to_float(annual_salary))
    for limit, rate, base in EARNED_INCOME_DEDUCTION:
        if s <= limit:
            prev_limit = [0, 5_000_000, 15_000_000, 45_000_000, 100_000_000]
            idx = [lim for lim, _, _ in EARNED_INCOME_DEDUCTION].index(limit)
            prev = prev_limit[idx]
            return round(base + (s - prev) * rate, 0)
    return round(36_000_000 + (s - 100_000_000) * 0.02, 0)


def calc_income_tax(taxable_income: float) -> float:
    """과세표준 → 산출세액 (근로소득세 누진세율 적용)."""
    ti = max(0.0, _to_float(taxable_income))
    for limit, rate, deduction in INCOME_TAX_BRACKETS:
        if ti <= limit:
            return round(ti * rate - deduction, 0)
    return round(ti * 0.45 - 65_940_000, 0)


def calc_card_income_deduction(
    annual_salary: float,
    credit_card_amount: float = 0.0,
    debit_cash_amount: float = 0.0,
) -> Dict[str, float]:
    """신용카드 / 체크카드·현금영수증 소득공제 계산.

    Returns
    -------
    { 'deduction_amount': float, 'threshold': float, 'excess': float }
    """
    salary = max(0.0, _to_float(annual_salary))
    credit = max(0.0, _to_float(credit_card_amount))
    debit = max(0.0, _to_float(debit_cash_amount))
    total_used = credit + debit

    threshold = salary * CARD_DEDUCTION_BASE_PCT
    if total_used <= threshold:
        return {'deduction_amount': 0.0, 'threshold': threshold, 'excess': 0.0}

    excess = total_used - threshold
    # 초과분을 신용카드 → 체크카드 순으로 배분
    credit_excess = max(0.0, min(credit, excess))
    debit_excess = max(0.0, excess - credit_excess)

    deduction = credit_excess * CARD_DEDUCTION_RATE_CREDIT + debit_excess * CARD_DEDUCTION_RATE_DEBIT
    max_limit = CARD_DEDUCTION_MAX if salary <= 70_000_000 else 2_500_000
    deduction = min(deduction, max_limit)

    return {
        'deduction_amount': round(deduction, 0),
        'threshold': round(threshold, 0),
        'excess': round(excess, 0),
    }


def calc_medical_tax_credit(
    annual_salary: float,
    medical_expense: float,
) -> Dict[str, float]:
    """의료비 세액공제 계산.

    Returns
    -------
    { 'tax_credit': float, 'deductible_amount': float, 'min_threshold': float }
    """
    salary = max(0.0, _to_float(annual_salary))
    expense = max(0.0, _to_float(medical_expense))
    min_threshold = salary * MEDICAL_DEDUCTION_MIN_PCT
    deductible = max(0.0, expense - min_threshold)
    tax_credit = round(deductible * MEDICAL_DEDUCTION_RATE, 0)
    return {
        'tax_credit': tax_credit,
        'deductible_amount': round(deductible, 0),
        'min_threshold': round(min_threshold, 0),
    }


def calc_education_tax_credit(
    education_expense: float,
    student_type: str = 'college',  # 'college' | 'elementary' | 'preschool'
) -> Dict[str, float]:
    """교육비 세액공제 계산.

    student_type:
      'college'     → 대학생 1인 한도 900만원
      'elementary'  → 초중고 1인 한도 300만원
      'preschool'   → 취학전 1인 한도 300만원
    """
    expense = max(0.0, _to_float(education_expense))
    limits = {
        'college': 9_000_000,
        'elementary': 3_000_000,
        'preschool': 3_000_000,
    }
    limit = limits.get(student_type, 9_000_000)
    deductible = min(expense, limit)
    tax_credit = round(deductible * EDUCATION_DEDUCTION_RATE, 0)
    return {
        'tax_credit': tax_credit,
        'deductible_amount': round(deductible, 0),
        'limit': limit,
    }


def calc_donation_tax_credit(donation_amount: float) -> Dict[str, float]:
    """기부금 세액공제 계산 (지정기부금 기준).

    1000만원 이하 15%, 초과분 30%.
    """
    amount = max(0.0, _to_float(donation_amount))
    if amount <= 10_000_000:
        credit = round(amount * DONATION_DEDUCTION_RATE, 0)
    else:
        credit = round(
            10_000_000 * DONATION_DEDUCTION_RATE
            + (amount - 10_000_000) * DONATION_DEDUCTION_RATE_HI,
            0
        )
    return {
        'tax_credit': credit,
        'donation_amount': round(amount, 0),
    }


def calc_year_end_tax_settlement(
    annual_salary: float,
    credit_card: float = 0.0,
    debit_cash: float = 0.0,
    medical_expense: float = 0.0,
    education_expense: float = 0.0,
    donation: float = 0.0,
    pension_savings: float = 0.0,
    irp_contribution: float = 0.0,
    personal_deduction_count: int = 1,
) -> Dict[str, Any]:
    """연말정산 종합 계산 (주요 공제 항목만 포함).

    Returns
    -------
    {
      'annual_salary': float,
      'earned_income_deduction': float,
      'personal_deduction': float,
      'card_income_deduction': float,
      'taxable_income': float,
      'base_tax': float,
      'medical_tax_credit': float,
      'education_tax_credit': float,
      'donation_tax_credit': float,
      'pension_tax_credit': float,
      'total_tax_credit': float,
      'final_tax': float,            # 결정세액
      'total_deduction_effect': float,
      'disclaimer': str,
    }
    """
    salary = max(0.0, _to_float(annual_salary))

    # 1) 근로소득공제
    earned_deduction = calc_earned_income_deduction(salary)

    # 2) 인적공제 (1인당 150만원)
    personal_deduction = personal_deduction_count * 1_500_000

    # 3) 신용카드 소득공제
    card_result = calc_card_income_deduction(salary, credit_card, debit_cash)
    card_deduction = card_result['deduction_amount']

    # 4) 과세표준
    taxable_income = max(0.0, salary - earned_deduction - personal_deduction - card_deduction)

    # 5) 산출세액
    base_tax = calc_income_tax(taxable_income)

    # 6) 세액공제
    medical_credit = calc_medical_tax_credit(salary, medical_expense)['tax_credit']
    education_credit = calc_education_tax_credit(education_expense)['tax_credit']
    donation_credit = calc_donation_tax_credit(donation)['tax_credit']

    # 연금저축 + IRP 세액공제
    pension_limit = min(_to_float(pension_savings), PENSION_SAVINGS_MAX)
    irp_limit = min(_to_float(pension_savings) + _to_float(irp_contribution), IRP_MAX)
    pension_eligible = min(irp_limit, IRP_MAX)
    # 세액공제율: 총급여 5500만 이하 16.5%, 초과 13.2%
    pension_credit_rate = 0.165 if salary <= 55_000_000 else 0.132
    pension_credit = round(pension_eligible * pension_credit_rate, 0)

    total_credit = medical_credit + education_credit + donation_credit + pension_credit
    final_tax = max(0.0, base_tax - total_credit)

    return {
        'annual_salary': salary,
        'earned_income_deduction': earned_deduction,
        'personal_deduction': personal_deduction,
        'card_income_deduction': card_deduction,
        'taxable_income': taxable_income,
        'base_tax': base_tax,
        'medical_tax_credit': medical_credit,
        'education_tax_credit': education_credit,
        'donation_tax_credit': donation_credit,
        'pension_tax_credit': pension_credit,
        'total_tax_credit': total_credit,
        'final_tax': final_tax,
        'total_deduction_effect': total_credit,
        'disclaimer': (
            '본 계산은 참고용입니다. 실제 결정세액은 국세청 홈택스 또는 '
            '세무사 확인을 통해 검증하시기 바랍니다.'
        ),
    }


# ─────────────────────────────────────────────────────────────
# 2. 금융소득종합과세 판정
# ─────────────────────────────────────────────────────────────

def check_financial_income_comprehensive_tax(
    interest_income: float,
    dividend_income: float,
    annual_salary: float = 0.0,
) -> Dict[str, Any]:
    """금융소득종합과세 해당 여부 및 예상 추가 세부담 분석.

    금융소득(이자+배당) 합산 2000만원 초과 시 종합과세 대상.

    Returns
    -------
    {
      'total_financial_income': float,
      'threshold': float,
      'subject_to_comprehensive_tax': bool,
      'excess_amount': float,
      'withholding_tax': float,         # 이미 납부한 원천징수세액
      'estimated_additional_tax': float, # 추가 납부 예상 세액 (근사치)
      'message': str,
    }
    """
    interest = max(0.0, _to_float(interest_income))
    dividend = max(0.0, _to_float(dividend_income))
    salary = max(0.0, _to_float(annual_salary))
    total_fi = interest + dividend
    threshold = FINANCIAL_INCOME_TAX_THRESHOLD
    subject = total_fi > threshold
    excess = max(0.0, total_fi - threshold)

    # 이미 납부된 원천징수세액
    withholding = round(total_fi * FINANCIAL_INCOME_WITHHOLDING, 0)

    # 종합과세 시 추가 세부담 (근사치: 초과분을 기존 근로소득에 합산하여 세율 적용)
    additional_tax = 0.0
    if subject and salary > 0:
        combined = salary + excess
        tax_combined = calc_income_tax(
            max(0.0, combined - calc_earned_income_deduction(combined) - 1_500_000)
        )
        tax_base = calc_income_tax(
            max(0.0, salary - calc_earned_income_deduction(salary) - 1_500_000)
        )
        withholding_on_excess = round(excess * FINANCIAL_INCOME_WITHHOLDING, 0)
        additional_tax = max(0.0, tax_combined - tax_base - withholding_on_excess)

    if subject:
        msg = (
            f'금융소득 합계 {total_fi:,.0f}원이 기준액 2,000만원을 초과합니다. '
            '종합소득세 신고 대상입니다.'
        )
    else:
        msg = (
            f'금융소득 합계 {total_fi:,.0f}원으로 종합과세 기준(2,000만원) 미만입니다. '
            '원천징수로 납세 완료.'
        )

    return {
        'total_financial_income': round(total_fi, 0),
        'threshold': threshold,
        'subject_to_comprehensive_tax': subject,
        'excess_amount': round(excess, 0),
        'withholding_tax': withholding,
        'estimated_additional_tax': round(additional_tax, 0),
        'message': msg,
    }


# ─────────────────────────────────────────────────────────────
# 3. 금융투자소득세 (금투세)
# ─────────────────────────────────────────────────────────────

def calc_financial_investment_tax(
    domestic_stock_profit: float = 0.0,
    overseas_stock_profit: float = 0.0,
    etf_profit: float = 0.0,
    other_profit: float = 0.0,
) -> Dict[str, Any]:
    """금융투자소득세 예상 세액 계산 (2026년 기준).

    국내 주식: 기본공제 500만원, 3억 이하 20% / 초과 25%.
    해외주식·ETF·기타: 기본공제 250만원, 동일 세율.

    Returns
    -------
    {
      'domestic_profit': float,
      'overseas_etf_profit': float,
      'domestic_deduction': float,
      'overseas_deduction': float,
      'domestic_taxable': float,
      'overseas_taxable': float,
      'domestic_tax': float,
      'overseas_tax': float,
      'total_tax': float,
      'effective_rate': float,
      'disclaimer': str,
    }
    """
    domestic = max(0.0, _to_float(domestic_stock_profit))
    overseas = max(0.0, _to_float(overseas_stock_profit) + _to_float(etf_profit) + _to_float(other_profit))

    domestic_deduction = min(domestic, KFIS_BASIC_DEDUCTION)  # 500만원
    overseas_deduction = min(overseas, 2_500_000)              # 250만원

    domestic_taxable = max(0.0, domestic - domestic_deduction)
    overseas_taxable = max(0.0, overseas - overseas_deduction)

    def _calc_tax(profit: float) -> float:
        if profit <= 300_000_000:
            return round(profit * KFIS_TAX_RATE, 0)
        else:
            return round(300_000_000 * KFIS_TAX_RATE + (profit - 300_000_000) * KFIS_TAX_RATE_HI, 0)

    domestic_tax = _calc_tax(domestic_taxable)
    overseas_tax = _calc_tax(overseas_taxable)
    total_tax = domestic_tax + overseas_tax
    total_profit = domestic + overseas
    effective_rate = (total_tax / total_profit * 100) if total_profit > 0 else 0.0

    return {
        'domestic_profit': domestic,
        'overseas_etf_profit': overseas,
        'domestic_deduction': domestic_deduction,
        'overseas_deduction': overseas_deduction,
        'domestic_taxable': domestic_taxable,
        'overseas_taxable': overseas_taxable,
        'domestic_tax': domestic_tax,
        'overseas_tax': overseas_tax,
        'total_tax': total_tax,
        'effective_rate': round(effective_rate, 2),
        'disclaimer': '금투세 계산은 참고용입니다. 세법 변경 및 손익통산 규정을 확인하세요.',
    }


# ─────────────────────────────────────────────────────────────
# 4. ISA / 연금저축 / IRP 절세 효과 비교
# ─────────────────────────────────────────────────────────────

def compare_tax_saving_accounts(
    annual_salary: float,
    annual_investment: float,
    investment_years: int = 5,
    expected_return_rate: float = 0.05,
    isa_type: str = 'general',   # 'general' | 'preferential'
) -> Dict[str, Any]:
    """ISA / 연금저축 / IRP 절세 계좌 효과 비교.

    Parameters
    ----------
    annual_salary: 연간 총급여 (세액공제율 결정용)
    annual_investment: 연간 납입액
    investment_years: 납입 기간 (년)
    expected_return_rate: 연간 기대수익률 (소수, 예: 0.05 = 5%)
    isa_type: 'general'(일반형) | 'preferential'(서민형/농어민)
    """
    salary = max(0.0, _to_float(annual_salary))
    invest = max(0.0, _to_float(annual_investment))
    years = max(1, int(investment_years))
    rate = max(0.0, _to_float(expected_return_rate))

    tax_credit_rate = 0.165 if salary <= 55_000_000 else 0.132

    # ── ISA ──────────────────────────────────────────────────
    isa_annual_limit = 20_000_000
    isa_invest = min(invest, isa_annual_limit)
    # 단리 근사 (복리는 별도 계산)
    isa_total_interest = 0.0
    balance = 0.0
    for _ in range(years):
        balance = balance * (1 + rate) + isa_invest
        isa_total_interest += balance * rate  # 근사
    isa_total_interest = balance - isa_invest * years
    isa_exempt = ISA_EXEMPT_PREFERENTIAL if isa_type == 'preferential' else ISA_EXEMPT_GENERAL
    isa_taxable = max(0.0, isa_total_interest - isa_exempt)
    isa_tax = round(isa_taxable * FINANCIAL_INCOME_WITHHOLDING, 0)
    # ISA 없을 경우 세금 (전액 원천징수)
    normal_tax = round(isa_total_interest * FINANCIAL_INCOME_WITHHOLDING, 0)
    isa_tax_saving = round(normal_tax - isa_tax, 0)

    # ── 연금저축 ──────────────────────────────────────────────
    pension_annual_limit = min(invest, PENSION_SAVINGS_MAX)
    pension_annual_credit = round(pension_annual_limit * tax_credit_rate, 0)
    pension_total_credit = pension_annual_credit * years

    # ── IRP (연금저축 포함 합산 한도) ─────────────────────────
    irp_combined = min(invest, IRP_MAX)
    irp_annual_credit = round(irp_combined * tax_credit_rate, 0)
    irp_total_credit = irp_annual_credit * years

    # ── 종합 비교 ─────────────────────────────────────────────
    scenarios = {
        'ISA': {
            'description': f'ISA ({isa_type}형)',
            'annual_investment': isa_invest,
            'estimated_total_interest': round(isa_total_interest, 0),
            'tax_on_interest': isa_tax,
            'tax_saving_vs_normal': isa_tax_saving,
            'annual_tax_credit': 0,
            'total_benefit': isa_tax_saving,
            'note': f'비과세 한도 {isa_exempt:,}원 / 최소 3년 유지 필요',
        },
        '연금저축': {
            'description': '연금저축펀드/보험',
            'annual_investment': pension_annual_limit,
            'estimated_total_interest': 0,
            'tax_on_interest': 0,
            'tax_saving_vs_normal': 0,
            'annual_tax_credit': pension_annual_credit,
            'total_benefit': pension_total_credit,
            'note': f'세액공제율 {tax_credit_rate*100:.1f}% / 55세 이후 수령 시 연금소득세',
        },
        'IRP': {
            'description': 'IRP (연금저축 합산)',
            'annual_investment': irp_combined,
            'estimated_total_interest': 0,
            'tax_on_interest': 0,
            'tax_saving_vs_normal': 0,
            'annual_tax_credit': irp_annual_credit,
            'total_benefit': irp_total_credit,
            'note': f'세액공제율 {tax_credit_rate*100:.1f}% / 연금저축+IRP 합산 최대 900만원 공제 가능',
        },
    }

    best_scenario = max(scenarios.items(), key=lambda x: x[1]['total_benefit'])

    return {
        'scenarios': scenarios,
        'best_scenario': best_scenario[0],
        'best_total_benefit': best_scenario[1]['total_benefit'],
        'salary_tax_credit_rate': tax_credit_rate,
        'summary': (
            f'연간 {invest:,.0f}원 납입 기준, '
            f'{best_scenario[0]}이 {best_scenario[1]["total_benefit"]:,.0f}원으로 가장 유리합니다.'
        ),
    }


# ─────────────────────────────────────────────────────────────
# 5. 절세 시나리오 종합 요약
# ─────────────────────────────────────────────────────────────

def generate_tax_optimization_summary(
    annual_salary: float,
    pension_savings: float = 0.0,
    irp_contribution: float = 0.0,
    credit_card: float = 0.0,
    debit_cash: float = 0.0,
    medical_expense: float = 0.0,
    education_expense: float = 0.0,
    donation: float = 0.0,
    interest_income: float = 0.0,
    dividend_income: float = 0.0,
) -> Dict[str, Any]:
    """절세 시나리오 종합 요약 — 현재 절세 효과 + 미활용 잠재 공제.

    Returns
    -------
    {
      'current_tax_credit_total': float,
      'unused_pension_savings_room': float,  # 연금저축 추가 납입 가능 금액
      'unused_irp_room': float,
      'financial_income_alert': bool,
      'suggestions': [ { 'action': str, 'estimated_saving': float }, ... ],
      'disclaimer': str,
    }
    """
    salary = max(0.0, _to_float(annual_salary))
    tax_credit_rate = 0.165 if salary <= 55_000_000 else 0.132

    # 현재 세액공제 합계
    year_end = calc_year_end_tax_settlement(
        annual_salary=salary,
        credit_card=credit_card,
        debit_cash=debit_cash,
        medical_expense=medical_expense,
        education_expense=education_expense,
        donation=donation,
        pension_savings=pension_savings,
        irp_contribution=irp_contribution,
    )
    current_credit_total = year_end['total_tax_credit']

    # 미활용 연금저축 여지
    used_pension = _to_float(pension_savings)
    used_irp_combined = _to_float(pension_savings) + _to_float(irp_contribution)
    unused_pension = max(0.0, PENSION_SAVINGS_MAX - used_pension)
    unused_irp = max(0.0, IRP_MAX - used_irp_combined)

    # 금융소득 종합과세 알림
    fi_check = check_financial_income_comprehensive_tax(interest_income, dividend_income, salary)
    fi_alert = fi_check['subject_to_comprehensive_tax']

    suggestions = []

    if unused_pension > 0:
        saving = round(min(unused_pension, PENSION_SAVINGS_MAX) * tax_credit_rate, 0)
        suggestions.append({
            'action': f'연금저축 추가 납입 (최대 {unused_pension:,.0f}원)',
            'estimated_saving': saving,
            'category': 'pension',
        })

    if unused_irp > unused_pension:
        extra_irp = unused_irp - unused_pension
        saving_irp = round(extra_irp * tax_credit_rate, 0)
        suggestions.append({
            'action': f'IRP 추가 납입 (최대 {extra_irp:,.0f}원)',
            'estimated_saving': saving_irp,
            'category': 'irp',
        })

    if _to_float(debit_cash) < salary * 0.25:
        suggestions.append({
            'action': '체크카드/현금영수증 사용 확대 (총급여 25% 초과 시 소득공제)',
            'estimated_saving': 0,
            'category': 'card',
        })

    if fi_alert:
        suggestions.append({
            'action': 'ISA 계좌 활용으로 금융소득 분리 과세 구간 관리',
            'estimated_saving': fi_check['estimated_additional_tax'],
            'category': 'isa',
        })

    return {
        'current_tax_credit_total': current_credit_total,
        'unused_pension_savings_room': unused_pension,
        'unused_irp_room': unused_irp,
        'financial_income_alert': fi_alert,
        'suggestions': suggestions,
        'year_end_detail': year_end,
        'disclaimer': (
            '본 요약은 주요 공제 항목 기준의 참고용 분석입니다. '
            '실제 신고는 국세청 홈택스 또는 세무 전문가에게 확인하세요.'
        ),
    }
