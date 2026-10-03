"""Effective-dated rule evidence. Never turns a reference ratio into approval."""
from datetime import date
from trading.finance_product_intelligence import number

DEPOSIT_RULE={
    'id':'kr-general-deposit-protection-20250901', 'effective_from':'2025-09-01',
    'verified_at':'2026-10-03','review_after':'2026-11-02','limit_krw':100000000,
    'source_url':'https://www.fsc.go.kr/no040101?cnId=2869',
    'scope':'확인된 일반 예금보호 대상에 대한 1인·동일 금융회사 원금과 소정의 이자 합산 참고',
}


def protection_check(profile,terms,principal,as_of=None):
    at=as_of or date.today()
    rule=dict(DEPOSIT_RULE);result={'rule':rule,'status':'evidence_required','protected_total':None,'excess':None}
    if not date.fromisoformat(rule['effective_from'])<=at<=date.fromisoformat(rule['review_after']):
        result['status']='rule_review_required';return result
    institution=terms.get('institution_id')
    holdings=profile.get('institution_balances') or {}
    if not isinstance(holdings,dict):raise ValueError('finance_institution_balances_invalid')
    known=holdings.get(institution) if institution else None
    if known is None and institution and profile.get('balance_institution_id')==institution:
        known={'confirmed':profile.get('balance_confirmed') in (True,'true'),
               'principal_and_eligible_interest':profile.get('balance_total')}
    if terms.get('protection_scheme')!='kr_general_deposit' or terms.get('protection_confirmed') is not True or not isinstance(known,dict) or known.get('confirmed') is not True:
        result['missing']=['상품의 보호 대상 여부','동일 금융회사 식별자','본인의 해당 회사 보호상품 원금·소정 이자 전체'];return result
    prior=number(known.get('principal_and_eligible_interest'),optional=True)
    eligible_interest=number(terms.get('eligible_protection_interest'),optional=True)
    if prior is None or eligible_interest is None:
        result['missing']=['기존 보호상품 합산액','새 상품의 소정 이자 확인액'];return result
    total=prior+principal+eligible_interest
    result.update(status='input_based_estimate',institution_id=institution,aggregate=total,
                  protected_total=min(total,rule['limit_krw']),excess=max(0,total-rule['limit_krw']),
                  note='입력한 동일 회사 합산액 기준 참고치. 이자 전액·특별 보호 범위·가입 자격을 자동 확정하지 않음.')
    return result


def eligibility_check(profile,terms):
    """Declared provider constraints only, with missing values kept conditional."""
    constraints=terms.get('eligibility') or {}
    if not isinstance(constraints,dict):raise ValueError('finance_eligibility_invalid')
    missing=[];failed=[]
    for field,bounds in constraints.items():
        if field not in {'age','annual_income','credit_score','housing_count'} or not isinstance(bounds,dict) or set(bounds)-{'min','max'}:
            raise ValueError('finance_eligibility_rule_unsupported')
        if not bounds:raise ValueError('finance_eligibility_empty_bounds')
        low=number(bounds.get('min'),optional=True);high=number(bounds.get('max'),optional=True)
        if ('min' in bounds and low is None) or ('max' in bounds and high is None) or (low is not None and high is not None and low>high):
            raise ValueError('finance_eligibility_invalid_bounds')
        value=number(profile.get(field),optional=True)
        if value is None:missing.append(field);continue
        if ('min' in bounds and value<number(bounds['min'])) or ('max' in bounds and value>number(bounds['max'])):failed.append(field)
    return {'status':'excluded' if failed else 'needs_confirmation' if missing else 'declared_constraints_checked' if constraints else 'not_checked',
            'missing':missing,'failed':failed,'approval':False}
