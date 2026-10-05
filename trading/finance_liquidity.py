"""Constant-balance, daily simple-interest comparison with explicit tier semantics."""
from decimal import Decimal, ROUND_HALF_UP
from trading.finance_product_intelligence import number, instant
from datetime import datetime, timezone


def liquid_interest(balance, days, terms):
    balance=Decimal(str(number(balance,minimum=1)));days=number(days,minimum=1,maximum=3660)
    if days!=int(days):raise ValueError('finance_liquid_days_integer')
    tiers=terms.get('rate_tiers')
    if tiers is None:
        rate=number(terms.get('annual_rate'),maximum=100,optional=True)
        if rate is None:return None
        tiers=[{'up_to':None,'annual_rate':rate}]
    if not isinstance(tiers,list) or not 1<=len(tiers)<=20:raise ValueError('finance_liquid_tiers')
    mode=terms.get('tier_mode','marginal')
    if mode not in {'marginal','whole_balance'}:raise ValueError('finance_liquid_tier_mode')
    previous=Decimal(0);annual=Decimal(0);parts=[];closed=False
    for i,t in enumerate(tiers):
        if not isinstance(t,dict) or set(t)!={'up_to','annual_rate'}:raise ValueError('finance_liquid_tiers')
        rate=Decimal(str(number(t['annual_rate'],maximum=100)))
        cap=None if t['up_to'] is None else Decimal(str(number(t['up_to'],minimum=1)))
        if closed or (cap is not None and cap<=previous) or (cap is None and i!=len(tiers)-1):raise ValueError('finance_liquid_tier_order')
        portion=max(Decimal(0),min(balance,cap if cap is not None else balance)-previous)
        if mode=='marginal':annual+=portion*rate/100
        elif balance>previous and (cap is None or balance<=cap):annual=balance*rate/100
        parts.append({'from':float(previous),'up_to':float(cap) if cap is not None else None,'annual_rate':float(rate)})
        if cap is None:closed=True
        else:previous=cap
    if not closed and balance>previous:raise ValueError('finance_liquid_tier_uncovered')
    tax=number(terms.get('tax_rate'),maximum=100,optional=True)
    rounding=lambda v:float(v.quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
    interest=annual*Decimal(int(days))/365
    net=None if tax is None else interest*(1-Decimal(str(tax))/100)
    return {'principal':float(balance),'interest':rounding(interest),'net_interest':None if net is None else rounding(net),
            'maturity':None if net is None else rounding(balance+net),'days':int(days),'tiers':parts,'tier_mode':mode,
            'assumptions':'같은 잔액 유지·365일 기준 단리 가정. 실제 일별 잔액·이자 지급일·원 단위 처리·향후 금리 변경에 따라 달라질 수 있습니다.'}


def compare_liquidity(result,profile,offers,catalog):
    balance=number(profile.get('amount'),minimum=1,optional=True)
    days=number(profile.get('liquid_days'),minimum=1,maximum=3660,optional=True)
    result.update(status='planning',questions=['얼마를 며칠 동안 보관하나요? 모르면 계획을 먼저 저장할 수 있습니다.',
                  '즉시 인출 가능 여부·잔액 구간별 금리·세금·보호 대상·이체 한도를 확인하세요.'],
                  ranking_basis='같은 잔액·기간에서 확인한 세후 이자 비교',monthly_remaining=None,
                  budget_note='비상금은 사용할 시점과 인출 가능 여부를 먼저 확인하세요.')
    if balance is None or days is None:return result
    rows=[dict(r,source_kind='user_quote') for r in offers]
    rows += [r for r in (catalog or {}).get('products',[]) if r.get('kind')=='savings' and r.get('terms',{}).get('method')=='liquid']
    for i,r in enumerate(rows):
        terms=r.get('terms',{})
        if r.get('source_kind')!='user_quote' and r.get('evidence_status')!='current':continue
        if r.get('valid_until') and instant(r['valid_until'])<=datetime.now(timezone.utc):continue
        if terms.get('method','liquid')!='liquid':continue
        from trading.finance_rule_evidence import eligibility_check, protection_check
        from trading.finance_terms import rate_terms,tax_terms
        eligibility=eligibility_check(profile,terms)
        conditions=terms.get('conditions') or []
        if not isinstance(conditions,list) or not all(isinstance(c,str) for c in conditions):raise ValueError('finance_invalid_conditions')
        if number(terms.get('min_amount',0))>balance or number(terms.get('max_amount',1e12))<balance:
            result['excluded'].append({'name':r.get('name','받은 조건'),'reason':'금액 구간 가입 조건 불일치'});continue
        if eligibility['failed'] or any(tag in c for tag in profile.get('declined_conditions',[]) for c in conditions):
            result['excluded'].append({'name':r.get('name','받은 조건'),'reason':'가입 조건 불충족 또는 원하지 않는 조건'});continue
        rate=rate_terms(terms,profile);tax=tax_terms(terms,profile)
        if terms.get('rate_tiers') and terms.get('rate_bonuses'):raise ValueError('finance_tier_bonus_requires_applicable_rates')
        from trading.finance_use_date import availability
        liquidity=availability(profile,0,terms,liquid=True)
        estimate=liquid_interest(balance,days,{**terms,'annual_rate':rate['annual_rate'],'tax_rate':tax['rate']})
        if estimate is None:
            result['excluded'].append({'name':r.get('name','받은 조건'),'reason':'적용 금리 미확인'});continue
        result['candidates'].append({'id':f'quote-{i}' if r.get('source_kind')=='user_quote' else f"{r.get('source_id')}:{r.get('id')}",
            'name':r.get('name','받은 조건'),'provider':r.get('provider',''),'estimate':estimate,'annual_rate':rate['annual_rate'],
            'source_kind':r.get('source_kind'),'source_url':r.get('source_url'),'version':r.get('version'),
            'verified_at':r.get('verified_at'),'valid_until':r.get('valid_until'),'unconfirmed_conditions':[c for c in conditions if c not in profile.get('confirmed_conditions',[])],
            'quote_confirmation_required':bool(r.get('returned_quote_key') and terms.get('confirmed') is not True),'liquidity':liquidity,'eligibility':eligibility['status'],'rate_detail':rate,'tax_detail':tax,'deposit_protection':protection_check(profile,terms,balance)})
    ranked=[r for r in result['candidates'] if r['estimate']['net_interest'] is not None and not r['unconfirmed_conditions'] and r['eligibility']!='needs_confirmation' and not r.get('quote_confirmation_required')]
    if profile.get('priority')=='liquidity':ranked=[r for r in ranked if r['liquidity']['fits_use_date'] is True]
    if ranked:result['best']=max(ranked,key=lambda r:r['estimate']['net_interest'])['name']
    result['status']='compared' if result['candidates'] else 'no_matching_candidates'
    return result
