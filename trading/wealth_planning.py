"""Household planning from explicit assumptions; no bank, provider or order calls."""
from __future__ import annotations
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import calendar
import json
import re
import uuid

VERSION = 'wealth-plan-1'
ISA_SOURCE = 'https://law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1033166111'
PENSION_SOURCE = 'https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1032884269'
RULES = {'version': 'kr-2026-10-11', 'year': 2026, 'verified_at': '2026-10-11',
         'review_after': '2026-11-10', 'sources': [ISA_SOURCE, PENSION_SOURCE]}


def amount(v, *, optional=False, maximum=10**12, minimum=0):
    if optional and v in ('', None): return None
    if v in ('', None) or isinstance(v, bool): raise ValueError('wealth_amount_required')
    try: n = Decimal(str(v))
    except (InvalidOperation, ValueError): raise ValueError('wealth_invalid_amount') from None
    if not n.is_finite() or n < Decimal(str(minimum)) or n > Decimal(str(maximum)):
        raise ValueError('wealth_invalid_amount')
    return n


def integer(v, maximum=600, minimum=1):
    n = amount(v, maximum=maximum, minimum=minimum)
    if n != int(n): raise ValueError('wealth_integer_required')
    return int(n)


def fields(row, allowed, required=()):
    if not isinstance(row, dict) or set(row) - set(allowed) or set(required) - set(row):
        raise ValueError('wealth_invalid_fields')


def label(v):
    if not isinstance(v, str) or not v.strip() or len(v) > 80 or any(ord(c)<32 for c in v):
        raise ValueError('wealth_invalid_label')
    return v.strip()


def dated(v, today):
    try: d = date.fromisoformat(v)
    except (ValueError, TypeError): raise ValueError('wealth_invalid_date') from None
    if d > today: raise ValueError('wealth_future_observation')
    return d


def money(n):
    return None if n is None else float(n.quantize(Decimal('.01')))


def _rows(payload, key):
    rows = payload.get(key, [])
    if not isinstance(rows, list) or len(rows)>30: raise ValueError('wealth_row_limit')
    ids=[]
    for row in rows:
        if not isinstance(row, dict): raise ValueError('wealth_invalid_fields')
        name=label(row.get('name')); ids.append(name.casefold())
    if len(set(ids)) != len(ids): raise ValueError('wealth_duplicate_row')
    return rows


def tax_review(raw, today):
    fields(raw, {'income_kind','annual_income','pension','irp','remaining_tax','resident','age','isa_months','isa_low_income','financial_income_excluded','year'})
    result={'rules': deepcopy(RULES), 'status':'conditions_required', 'approval':False,
            'isa': {'minimum_months':36,'general_exemption':2000000,'low_income_exemption':4000000,
                    'separate_tax_including_local':.099,'annual_contribution_limit':20000000,'total_contribution_limit':100000000},
            'pension_credit_cap':None,
            'notes':['예금 기간만 길다고 비과세가 되지 않습니다. ISA는 가입·유지·소득 조건을 함께 확인합니다.',
                     '연금 세액공제는 현재 절세액의 상한입니다. 중도 인출·연금 수령 세금과 별개이며 월 배분 자금에 더하지 않습니다.',
                     '비과세종합저축은 2026년 가입 자격을 기관에 확인하세요. 나이만으로 자격을 확정하지 않습니다.']}
    year=integer(raw.get('year') or today.year, maximum=2100,minimum=2000)
    fresh = today.isoformat() <= RULES['review_after'] and today.isoformat() >= RULES['verified_at'] and year==RULES['year']
    if not fresh: result['status']='rules_reconfirmation_required'; return result
    income=amount(raw.get('annual_income'),optional=True)
    pension=amount(raw.get('pension'),optional=True); irp=amount(raw.get('irp'),optional=True)
    capacity=amount(raw.get('remaining_tax'),optional=True)
    kind=raw.get('income_kind')
    if kind not in (None,'','salary_only','comprehensive'): raise ValueError('wealth_invalid_income_kind')
    if kind and all(n is not None for n in (income,pension,irp,capacity)):
        rate=Decimal('.165') if income <= (55000000 if kind=='salary_only' else 45000000) else Decimal('.132')
        eligible=min(min(pension,Decimal(6000000))+irp,Decimal(9000000))
        result['pension_credit_cap']=money(min(eligible*rate,capacity))
        result['credit_rate_including_local']=float(rate)
        result['status']='input_based_conditions'
    # Age below 19 may qualify with earned income; leave this branch to institution review.
    age=integer(raw['age'],maximum=120,minimum=0) if raw.get('age') not in ('',None) else None
    months=integer(raw['isa_months'],minimum=0) if raw.get('isa_months') not in ('',None) else None
    for key in ('resident','isa_low_income','financial_income_excluded'):
        if raw.get(key) not in (None,'',True,False) or (key in raw and isinstance(raw[key],(int,float)) and not isinstance(raw[key],bool)):
            raise ValueError('wealth_invalid_confirmation')
    result['isa']['condition_review'] = ('institution_review_required' if age is None or months is None or raw.get('resident') is not True or raw.get('financial_income_excluded') is not True or age<19
        else 'minimum_term_not_met' if months<36 else 'entered_basic_conditions_met')
    # Do not grant enhanced exemption on the basis of a checkbox or arbitrary salary assumption.
    result['isa']['applicable_exemption']=None
    return result


def preview(payload, *, today=None):
    today=today or date.today()
    fields(payload, {'name','as_of','income','expenses','annual_irregular','emergency_months','assets','debts','bills','goals','tax'},
           {'name','as_of','income','expenses','annual_irregular','emergency_months'})
    name=label(payload['name']); observed=dated(payload['as_of'],today)
    income=amount(payload['income']); expenses=amount(payload['expenses']); irregular=amount(payload['annual_irregular'])/12
    emergency_months=integer(payload['emergency_months'],maximum=24,minimum=0)
    warnings=[]; assets={}; cash=Decimal(0); omitted=[]
    if (today-observed).days>31: warnings.append('월 예산 기준일이 31일을 넘었습니다. 현재 금액을 다시 확인하세요.')
    for row in _rows(payload,'assets'):
        fields(row,{'name','amount','currency','kind','mode','as_of','confirmed'}, {'name','amount','currency','kind','mode','as_of','confirmed'})
        n=amount(row['amount']); currency=row['currency']
        if not isinstance(currency,str) or not re.fullmatch('[A-Z]{3,6}',currency): raise ValueError('wealth_invalid_currency')
        if row['kind'] not in {'cash','deposit','investment','property','other'} or row['mode'] not in {'real','paper'} or not isinstance(row['confirmed'],bool): raise ValueError('wealth_invalid_asset')
        at=dated(row['as_of'],today)
        if row['mode']=='paper' or not row['confirmed'] or (today-at).days>31:
            omitted.append({'name':row['name'],'reason':'paper' if row['mode']=='paper' else 'unconfirmed_or_stale'}); continue
        assets[currency]=assets.get(currency,Decimal(0))+n
        if currency=='KRW' and row['kind']=='cash': cash+=n
    debt_totals={}; payment=Decimal(0); debt_rows=[]
    for row in _rows(payload,'debts'):
        fields(row,{'name','principal','annual_rate','payment','early_fee','as_of'}, {'name','principal','annual_rate','payment','early_fee','as_of'})
        principal=amount(row['principal']); rate=amount(row['annual_rate'],maximum=100); p=amount(row['payment']); fee=amount(row['early_fee'],optional=True)
        at=dated(row['as_of'],today); payment+=p; debt_totals['KRW']=debt_totals.get('KRW',Decimal(0))+principal
        stale=(today-at).days>31
        debt_rows.append({'name':row['name'],'principal':money(principal),'annual_rate':float(rate),'payment':money(p),'early_fee':money(fee),'stale':stale,
                          'annual_interest_reference':money(principal*rate/100), 'action':'현재 잔액·수수료 재확인' if stale or fee is None else '금리·중도상환비용과 비상금 확보 후 추가 상환 검토'})
        if stale: warnings.append('부채 기준일이 지난 항목이 있습니다. 잠정 월 상환액으로 계산했습니다.')
    bill_rows=[]; potential=Decimal(0); confirmed=Decimal(0); upfront=Decimal(0)
    for row in _rows(payload,'bills'):
        fields(row,{'name','current','target','change_cost','confirmed'}, {'name','current','target','change_cost','confirmed'})
        current=amount(row['current']); target=amount(row['target']); cost=amount(row['change_cost'],optional=True)
        if not isinstance(row['confirmed'],bool) or target>current: raise ValueError('wealth_invalid_reduction')
        saving=current-target; potential+=saving
        # Confirmed means the user has checked terms, not that savings were realized.
        if row['confirmed'] and cost is not None: confirmed+=saving; upfront+=cost
        bill_rows.append({'name':row['name'],'potential_monthly':money(saving),'terms_confirmed':row['confirmed'] and cost is not None,
                         'break_even_months':None if cost is None or not saving else int((cost/saving).to_integral_value(rounding='ROUND_CEILING'))})
    if sum((amount(r['current']) for r in payload.get('bills',[])),Decimal(0))>expenses: raise ValueError('wealth_bills_exceed_expenses')
    base=income-expenses-payment-irregular; projected=base+confirmed
    reserve=(expenses+payment+irregular)*emergency_months
    allocatable=max(Decimal(0),cash-reserve-upfront)
    if cash<reserve+upfront: warnings.append('현금이 비상금 목표·변경 비용보다 부족합니다. 목표 배분 전에 부족액부터 확인하세요.')
    goal_rows=[]; opening_total=Decimal(0); monthly_total=Decimal(0)
    for row in _rows(payload,'goals'):
        fields(row,{'name','target','months','opening','monthly','annual_rate','tax_rate','fees','inflation'}, {'name','target','months','opening','monthly','annual_rate','tax_rate','fees','inflation'})
        target=amount(row['target'],minimum=1); months=integer(row['months']); opening=amount(row['opening']); monthly=amount(row['monthly'])
        rate=amount(row['annual_rate'],minimum=-99,maximum=100,optional=True); tax=amount(row['tax_rate'],maximum=100,optional=True)
        fees=amount(row['fees'],optional=True); inflation=amount(row['inflation'],minimum=0,maximum=100,optional=True)
        opening_total+=opening; monthly_total+=monthly; principal=opening+monthly*months
        scenarios=[]
        for key,assumption in [('principal_only',Decimal(0)),('entered',rate),('lower',None if rate is None else max(Decimal(-99),rate-5))]:
            gross=None
            if assumption is not None:
                # Monthly end contributions, effective annual return; no dividend/tax reinvestment invented.
                r=(1+float(assumption)/100)**(1/12)-1
                gross=float(opening)*(1+r)**months+float(monthly)*(months if abs(r)<1e-12 else ((1+r)**months-1)/r)
            net=None if gross is None or tax is None or fees is None else gross-max(0,gross-float(principal))*float(tax)/100-float(fees)
            real=None if net is None or inflation is None else net/(1+float(inflation)/100)**(months/12)
            scenarios.append({'id':key,'annual_rate':None if assumption is None else float(assumption),'gross':None if gross is None else round(gross,2),
                              'after_tax':None if net is None else round(net,2),'today_value':None if real is None else round(real,2),'gap':None if net is None else round(float(target)-net,2)})
        y=today.year+(today.month-1+months)//12; m=(today.month-1+months)%12+1
        end=date(y,m,min(today.day,calendar.monthrange(y,m)[1]))
        goal_rows.append({'name':row['name'],'target':money(target),'months':months,'use_date':end.isoformat(),'principal':money(principal),'scenarios':scenarios})
    violations=[]
    if opening_total>allocatable: violations.append('초기 목표 배분이 비상금·변경 비용을 제외한 확인 현금보다 큽니다.')
    if monthly_total>max(Decimal(0),base): violations.append('월 목표 배분이 현재 잉여금보다 큽니다. 예상 절약액은 실제 기록 확인 전 배분 재원에 넣지 않습니다.')
    if base<0: violations.append('현재 월 예산이 적자입니다. 저축·투자를 늘리기 전에 지출과 상환액을 조정하세요.')
    currencies=set(assets)|set(debt_totals)
    return {'version':VERSION,'name':name,'as_of':observed.isoformat(),'calculated_at':today.isoformat(),'currency':'KRW','status':'allocation_conflict' if violations else 'input_based_plan',
            'budget':{'income':money(income),'expenses_including_bills':money(expenses),'debt_payment':money(payment),'irregular_provision':money(irregular),
                      'current_surplus':money(base),'potential_saving':money(potential),'terms_checked_saving':money(confirmed),'projected_surplus':money(projected),
                      'confirmed_cash':money(cash),'emergency_target':money(reserve),'emergency_gap':money(max(Decimal(0),reserve-cash)),
                      'change_cost':money(upfront),'allocatable_cash':money(allocatable),'opening_allocated':money(opening_total),'monthly_allocated':money(monthly_total),
                      'remaining_monthly':money(base-monthly_total)},
            'recorded_net_worth_by_currency':{c:{'recorded_assets':money(assets.get(c,Decimal(0))),'recorded_debts':money(debt_totals.get(c,Decimal(0))),
                                              'partial_net':money(assets.get(c,Decimal(0))-debt_totals.get(c,Decimal(0)))} for c in sorted(currencies)},
            'omitted_assets':omitted,'bills':bill_rows,'debts':sorted(debt_rows,key=lambda r:r['annual_rate'],reverse=True),
            'goals':goal_rows,'tax':tax_review(payload.get('tax',{}),today),'violations':violations,'warnings':warnings,
            'basis':['사용자가 입력·확인한 가정의 계획입니다. 전체 금융기관 자산이나 실제 잔액 대조 결과가 아닙니다.',
                     '전체 생활비에 반복 결제를 포함하고 부채 상환액은 별도 입력합니다. 연간 비정기 지출은 12개월로 나눠 유보합니다.',
                     '현금만 목표에 배분합니다. 예금·투자자산·외화·PAPER는 원화 현금으로 재사용하지 않습니다.',
                     '목표 시나리오는 월말 납입·연 유효수익률·수익에만 입력 세율 적용·만기 비용 차감 가정입니다. 원금도 손실될 수 있습니다.']}


def dispatch(vault, operation='list', **kwargs):
    from trading.insurance_workspace import InsuranceError
    try:
        if operation=='preview':
            fields(kwargs,{'input'},{'input'})
            return preview(kwargs['input'])
        with vault._mutex:
            vault._require(); data=deepcopy(vault._data); plans=data.setdefault('wealth_plans',{})
            if operation=='list':
                fields(kwargs,set())
                return {'state':'unlocked','plans':list(plans.values()),'external_notification':False, 'remaining_seconds':max(0,vault._expires_at-__import__('time').monotonic())}
            allowed={'save':{'id','revision','confirmed','input'},'delete':{'id','revision','confirmed'},'actual':{'id','revision','confirmed','month','actual'}}
            if operation not in allowed: raise ValueError('wealth_invalid_operation')
            fields(kwargs, allowed[operation], {'confirmed'})
            if kwargs['confirmed'] is not True: raise ValueError('wealth_confirmation_required')
            pid=kwargs.get('id'); existing=plans.get(pid) if isinstance(pid,str) else None
            if operation!='save' and existing is None: raise ValueError('wealth_plan_missing')
            if existing and (type(kwargs.get('revision')) is not int or kwargs['revision']!=existing['revision']): raise ValueError('wealth_revision_conflict')
            if operation=='save':
                if pid and not existing: raise ValueError('wealth_plan_missing')
                result=preview(kwargs.get('input'))
                if result['violations']: raise ValueError('wealth_allocation_conflict')
                if not existing and len(plans)>=30: raise ValueError('wealth_plan_limit')
                pid=pid or uuid.uuid4().hex
                plans[pid]={'id':pid,'revision':(existing['revision'] if existing else 0)+1,'input':deepcopy(kwargs['input']),
                            'result':result,'saved_at':datetime.now(timezone.utc).isoformat(),'actuals':existing.get('actuals',{}) if existing else {}}
            elif operation=='delete': del plans[pid]
            elif operation=='actual':
                month=kwargs.get('month')
                if not isinstance(month,str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',month) or month<'2000-01' or month>date.today().strftime('%Y-%m'): raise ValueError('wealth_invalid_month')
                actual=kwargs.get('actual'); fields(actual,{'income','expenses','debt_payment','saving','goal_balances'}, {'income','expenses','debt_payment','saving'})
                values={k:money(amount(actual[k])) for k in ('income','expenses','debt_payment','saving')}
                balances=actual.get('goal_balances',{})
                targets={g['name']:g['target'] for g in existing['result']['goals']}
                if not isinstance(balances,dict) or set(balances)-set(targets):raise ValueError('wealth_unknown_goal')
                values['goal_progress']={name:{'observed_balance':money(amount(balances[name])) if balances.get(name) not in ('',None) else None,
                    'gap':money(Decimal(str(target))-amount(balances[name])) if balances.get(name) not in ('',None) else None,'target_at_record':target} for name,target in targets.items()}
                actuals=existing.setdefault('actuals',{})
                if month not in actuals and len(actuals)>=120: raise ValueError('wealth_actual_limit')
                values['remaining']=round(values['income']-values['expenses']-values['debt_payment']-values['saving'],2)
                values['basis']='user_entered_actual_not_bank_reconciled'
                values['plan_revision']=existing['revision']
                values['planned_surplus']=existing['result']['budget']['current_surplus']
                values['planned_monthly']=existing['result']['budget']['monthly_allocated']
                actuals[month]=values; existing['revision']+=1
            else: raise ValueError('wealth_invalid_operation')
            if len(json.dumps(plans,ensure_ascii=False).encode())>4_000_000: raise ValueError('wealth_storage_limit')
            vault._persist(data)
            return {'state':'unlocked','plans':list(plans.values()),'external_notification':False, 'remaining_seconds':max(0,vault._expires_at-__import__('time').monotonic())}
    except InsuranceError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError):
        # Never echo private financial values or labels in HTTP errors.
        raise InsuranceError('wealth_invalid_or_conflicting_plan') from None
