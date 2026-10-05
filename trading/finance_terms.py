"""Reviewed provider terms. No statutory ratios, personal rates or taxes guessed."""
from datetime import date
from trading.finance_product_intelligence import number, public_url


def current_rule(rule, at=None):
    if not isinstance(rule,dict):raise ValueError('finance_rule_invalid')
    for field in ('id','version','scope'):
        if not isinstance(rule.get(field),str) or not rule[field].strip():raise ValueError('finance_rule_metadata_required')
    public_url(rule.get('source_url'))
    start=date.fromisoformat(rule['effective_from']);end=date.fromisoformat(rule['valid_until'])
    if end<start:raise ValueError('finance_rule_dates_invalid')
    return rule.get('reviewed') is True and start<=(at or date.today())<=end


def rate_terms(terms, profile):
    """Base plus individually earned bonuses, capped at published total ceiling."""
    confirmed=profile.get('confirmed_conditions') or []
    if isinstance(confirmed,str):confirmed=[s.strip() for s in confirmed.split(',') if s.strip()]
    if not isinstance(confirmed,list) or not all(isinstance(c,str) for c in confirmed):raise ValueError('finance_conditions_invalid')
    base=number(terms.get('base_rate'),maximum=100,optional=True)
    if base is None:return {'annual_rate':terms.get('annual_rate'),'basis':'provided_applicable_rate','unearned_bonuses':[]}
    bonuses=terms.get('rate_bonuses') or []
    if not isinstance(bonuses,list) or len(bonuses)>30:raise ValueError('finance_rate_bonuses_invalid')
    earned=0;unearned=[]
    for bonus in bonuses:
        if not isinstance(bonus,dict) or not isinstance(bonus.get('condition'),str) or not bonus['condition']:raise ValueError('finance_rate_bonus_invalid')
        delta=number(bonus.get('percentage_points'),maximum=100)
        if bonus['condition'] in confirmed:earned+=delta
        else:unearned.append({'condition':bonus['condition'],'percentage_points':delta})
    cap=number(terms.get('max_rate'),maximum=100,optional=True)
    if cap is not None and cap<base:raise ValueError('finance_rate_cap_invalid')
    applicable=min(base+earned,cap if cap is not None else 100)
    return {'annual_rate':applicable,'basis':'base_plus_confirmed_bonuses','base_rate':base,'earned_bonus':applicable-base,'maximum_rate':cap,'unearned_bonuses':unearned}


def tax_terms(terms,profile,at=None):
    rule=terms.get('tax_rule')
    if rule is None:return {'rate':terms.get('tax_rate'),'status':'user_or_provider_supplied','rule':None}
    active=current_rule(rule,at)
    required=rule.get('required_confirmations') or []
    if not isinstance(required,list) or not all(isinstance(k,str) for k in required):raise ValueError('finance_tax_conditions_invalid')
    confirmed=profile.get('confirmed_conditions') or []
    if isinstance(confirmed,str):confirmed=[s.strip() for s in confirmed.split(',') if s.strip()]
    rate=number(rule.get('tax_rate'),maximum=100)
    ready=active and all(k in confirmed for k in required)
    return {'rate':rate if ready else None,'status':'reviewed_rule_applied' if ready else 'rule_or_eligibility_required','rule':rule}


def lending_rules(terms, profile, estimate, at=None):
    """Applies only a reviewed, dated, exact-scope rule and confirmed annual inputs.

    Regulated annual debt service is a separate input: a generic monthly-payment
    multiplier is never substituted for jurisdiction-specific DSR methodology.
    """
    rules=terms.get('lending_rules') or []
    if not isinstance(rules,list) or len(rules)>10:raise ValueError('finance_lending_rules_invalid')
    output=[]
    for rule in rules:
        active=current_rule(rule,at);metric=rule.get('metric')
        if metric not in {'dsr','ltv'}:raise ValueError('finance_lending_metric_invalid')
        cap=number(rule.get('cap_percent'),maximum=100)
        context=rule.get('context')
        if not isinstance(context,dict) or not context or any(k not in {'borrower_type','region','loan_purpose','institution_sector','rate_type'} or not isinstance(v,str) or not v for k,v in context.items()):raise ValueError('finance_lending_context_required')
        missing=[k for k,v in context.items() if profile.get(k)!=v]
        value=None
        if active and not missing and profile.get('regulatory_inputs_confirmed') in (True,'true'):
            if metric=='dsr':
                income=number(profile.get('annual_income'),minimum=1,optional=True)
                annual=number(profile.get('regulated_annual_debt_service'),optional=True)
                if income is not None and annual is not None:value=100*annual/income
            else:
                collateral=number(profile.get('collateral_value'),minimum=1,optional=True)
                secured=number(profile.get('total_secured_debt'),optional=True)
                if collateral is not None and secured is not None:value=100*secured/collateral
        output.append({'rule':rule,'value_percent':value,'cap_percent':cap,'within_reference':None if value is None else value<=cap,
                       'status':'input_based_reference' if value is not None else 'rule_context_or_inputs_required','mismatched_context':missing,
                       'approval':False,'note':'기관이 확인한 규정상 부채 산정액·적용 예외를 입력한 참고 비교. 개인 승인 한도나 확정 심사 결과가 아님.'})
    return output


def validate_terms(terms):
    rate_terms(terms,{})
    if terms.get('coverage_details') is not None:
        from trading.finance_coverage import normalize
        normalize(terms['coverage_details'])
    if terms.get('rate_tiers') is not None:
        from trading.finance_liquidity import liquid_interest
        liquid_interest(1,1,terms)
    if terms.get('loan_purposes') is not None:
        from trading.finance_journey import loan_match
        loan_match({'loan_purpose':'living'},terms)
    tax_terms(terms,{})
    lending_rules(terms,{}, {})
    for key in ('documents','channels'):
        values=terms.get(key,[])
        if not isinstance(values,list) or len(values)>30 or not all(isinstance(v,str) and len(v)<=500 for v in values):raise ValueError('finance_terms_list_invalid')
    for key in ('application_url',):
        if terms.get(key):public_url(terms[key])
