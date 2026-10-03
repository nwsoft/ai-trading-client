"""Explicit assumption scenarios. No statutory thresholds or quoted rates are invented."""
from __future__ import annotations
import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from trading.finance_product_intelligence import number


def _integer(value, maximum, default=0):
    n=number(default if value in (None,'') else value,maximum=maximum)
    if n != int(n): raise ValueError('finance_integer_required')
    return int(n)


def _date_after(start, months):
    year=start.year+(start.month-1+months)//12;month=(start.month-1+months)%12+1
    return date(year,month,min(start.day,calendar.monthrange(year,month)[1]))


def parse_month_values(raw,months,value_key,maximum):
    if raw in (None,'',[]):return []
    if isinstance(raw,str):
        try:
            pairs=[pair.split(':') for pair in raw.replace('\n',',').split(',') if pair.strip()]
            if any(len(pair)!=2 for pair in pairs):raise ValueError('finance_schedule_invalid')
            raw=[{'month':pair[0].strip(),value_key:pair[1].strip()} for pair in pairs]
        except (IndexError,AttributeError):raise ValueError('finance_schedule_invalid') from None
    if not isinstance(raw,list) or len(raw)>600:raise ValueError('finance_schedule_invalid')
    output=[]
    for row in raw:
        if not isinstance(row,dict) or set(row)!={'month',value_key}:raise ValueError('finance_schedule_invalid')
        month=_integer(row['month'],months)
        if not month:raise ValueError('finance_schedule_invalid')
        output.append({'month':month,value_key:number(row[value_key],maximum=maximum)})
    if len({r['month'] for r in output})!=len(output):raise ValueError('finance_schedule_duplicate_month')
    return sorted(output,key=lambda r:r['month'])


def loan_projection(amount, months, rate, method, fees, profile):
    amount=number(amount,minimum=1);months=_integer(months,600);rate=number(rate,maximum=100)
    if not months or method not in {'annuity','principal','bullet'}:raise ValueError('finance_invalid_method_or_term')
    grace=_integer(profile.get('grace_months'),months-1)
    basis=profile.get('day_count') or 'monthly'
    if basis not in {'monthly','actual365','actual360'}:raise ValueError('finance_invalid_day_count')
    start=date.fromisoformat(profile['start_date']) if profile.get('start_date') else None
    if basis!='monthly' and start is None:raise ValueError('finance_start_date_required')
    rounding=profile.get('rounding') or 'cent'
    if rounding not in {'cent','won'}:raise ValueError('finance_invalid_rounding')
    quantum=Decimal('1') if rounding=='won' else Decimal('0.01')
    rounded=lambda n:float(Decimal(str(n)).quantize(quantum,rounding=ROUND_HALF_UP))
    early_month=_integer(profile.get('early_month'),months)
    early_amount=number(profile.get('early_amount'),optional=True)
    early_fee=number(profile.get('early_fee'),optional=True)
    if (early_month>0)!=(early_amount is not None):raise ValueError('finance_early_terms_required')
    steps=parse_month_values(profile.get('rate_steps'),months,'annual_rate',100)
    step_map={r['month']:r['annual_rate'] for r in steps};rates=[];active_rate=rate
    factors=[];units=[];previous=start
    for m in range(1,months+1):
        end=_date_after(start,m) if start else None
        active_rate=step_map.get(m,active_rate);rates.append(active_rate)
        unit=1/12 if basis=='monthly' else (end-previous).days/(365 if basis=='actual365' else 360)
        units.append(unit);factors.append(active_rate/100*unit)
        previous=end
    discount=1;discount_sum=0
    for r in factors[grace:]:discount/=1+r;discount_sum+=discount
    payment=amount/discount_sum
    balance=amount;interest=0;rows=[];total_early=0
    for m,r in enumerate(factors,1):
        cost=rounded(balance*r)
        if steps and method=='annuity' and m>grace and (m==grace+1 or m in step_map):
            factor=1;total_factor=0
            for unit in units[m-1:]:factor/=1+rates[m-1]/100*unit;total_factor+=factor
            payment=balance/total_factor
        principal=(balance if m==months else 0 if m<=grace or method=='bullet' else amount/(months-grace) if method=='principal' else payment-cost)
        principal=min(balance,max(0,rounded(principal)))
        additional=min(max(0,balance-principal),early_amount or 0) if m==early_month else 0
        balance=max(0,rounded(balance-principal-additional));interest+=cost;total_early+=additional
        rows.append({'month':m,'annual_rate':rates[m-1],'date':_date_after(start,m).isoformat() if start else None,
                     'payment':rounded(principal+additional+cost),'principal_paid':rounded(principal+additional),
                     'early_repayment':additional,'interest':cost,'balance':balance})
    fees=number(fees,optional=True)
    costs_known=fees is not None and (not early_month or early_fee is not None)
    return {'principal':amount,'interest':rounded(interest),'fees':fees,
            'total_cost':rounded(interest+fees+(early_fee or 0)) if costs_known else None,
            'first_payment':rows[0]['payment'],'last_payment':rows[-1]['payment'],'max_payment':max(r['payment'] for r in rows),
            'average_payment':rounded(sum(r['payment'] for r in rows)/months),'schedule':rows,
            'closed_at_month':next((r['month'] for r in rows if r['balance']==0),months),
            'early_repayment_total':total_early,'early_fee':early_fee if early_month else None,
            'assumptions':{'grace_months':grace,'day_count':basis,'rounding':rounding,'fixed_rate':None if steps else rate,'rate_steps':steps,'rate_reset_basis':'금리 변경 시 당시 금리를 잔여기간에 적용해 원리금균등액 재산정 가정','start_date':start.isoformat() if start else None}}


def saving_projection(amount, months, rate, method, tax_rate, profile):
    amount=number(amount,minimum=1);months=_integer(months,600);rate=number(rate,maximum=100)
    tax_rate=number(tax_rate,maximum=100,optional=True)
    if not months or method not in {'deposit','installment'}:raise ValueError('finance_invalid_method_or_term')
    compounding=profile.get('compounding') or 'simple'
    if compounding not in {'simple','monthly','annual'}:raise ValueError('finance_invalid_compounding')
    timing=profile.get('deposit_timing') or 'beginning'
    if timing not in {'beginning','end'}:raise ValueError('finance_invalid_deposit_timing')
    def growth(n):
        if compounding=='simple':return 1+rate/1200*n
        if compounding=='monthly':return (1+rate/1200)**n
        years,remaining=divmod(n,12)
        return (1+rate/100)**years*(1+rate/1200*remaining)
    factor=growth(months) if method=='deposit' else sum(growth(m) for m in range(1 if timing=='beginning' else 0,months+(1 if timing=='beginning' else 0)))
    principal=number(amount if method=='deposit' else amount*months)
    contributions=parse_month_values(profile.get('contributions'),months,'amount',1e12)
    if contributions and method!='installment':raise ValueError('finance_contributions_require_installment')
    if contributions:
        principal=number(sum(r['amount'] for r in contributions))
        interest=sum(r['amount']*(growth(months-r['month']+(1 if timing=='beginning' else 0))-1) for r in contributions)
    else:interest=amount*factor-principal
    net=None if tax_rate is None else interest*(1-tax_rate/100)
    target=number(profile.get('target_amount'),optional=True)
    net_factor=None if tax_rate is None else (1 if method=='deposit' else months)+(factor-(1 if method=='deposit' else months))*(1-tax_rate/100)
    required=None if target is None or net_factor is None or contributions else target/net_factor
    early_month=_integer(profile.get('withdraw_month'),months)
    early_rate=number(profile.get('withdraw_rate'),maximum=100,optional=True)
    early=None
    if early_month:
        early_principal=amount if method=='deposit' else amount*early_month
        holding=early_month if method=='deposit' else early_month*(early_month+(1 if timing=='beginning' else -1))/2
        early_interest=None if early_rate is None else amount*early_rate/1200*holding
        if contributions:
            before=[r for r in contributions if r['month']<=early_month]
            early_principal=sum(r['amount'] for r in before)
            early_interest=None if early_rate is None else sum(r['amount']*early_rate/1200*(early_month-r['month']+(1 if timing=='beginning' else 0)) for r in before)
        early={'month':early_month,'principal':early_principal,'interest':early_interest,
               'after_tax':None if early_interest is None or tax_rate is None else early_principal+early_interest*(1-tax_rate/100),
               'basis':'사용자가 확인한 중도해지 금리의 단리 가정. 미확인 금리를 대신 생성하지 않음.'}
    ladder=[]
    if profile.get('ladder') in (True,'true') and method=='deposit':
        # Each tranche is an explicit illustration at the supplied rate, not a
        # claim that a bank offers that rate for every maturity.
        for term in sorted(set((max(1,months//3),max(1,2*months//3),months))):
            part=amount/len(set((max(1,months//3),max(1,2*months//3),months)))
            earned=part*(growth(term)-1)
            ladder.append({'months':term,'principal':part,'maturity':None if tax_rate is None else part+earned*(1-tax_rate/100)})
    partials=parse_month_values(profile.get('partial_withdrawals'),months,'amount',1e12)
    partial_result=None
    if partials:
        if ladder:raise ValueError('finance_choose_ladder_or_partial_withdrawal')
        confirmed=profile.get('partial_withdrawal_confirmed') in (True,'true')
        partial_rate=number(profile.get('partial_withdrawal_rate'),maximum=100,optional=True)
        partial_fee=number(profile.get('partial_withdrawal_fee'),optional=True)
        if early_month:raise ValueError('finance_choose_full_or_partial_withdrawal')
        if not confirmed or partial_rate is None or partial_fee is None:
            partial_result={'status':'terms_required','proceeds':None,'note':'부분인출 가능 여부·인출분 적용 금리·건별 비용 확인 필요'}
            net=None;interest=None
        else:
            deposits=([{'month':1,'amount':amount}] if method=='deposit' else contributions or [{'month':m,'amount':amount} for m in range(1,months+1)])
            lots=[dict(r) for r in deposits];withdrawn=0;released_interest=0;outflows=[]
            for withdrawal in partials:
                needed=withdrawal['amount'];month=withdrawal['month'];earned=0
                if needed<=0:raise ValueError('finance_partial_amount_required')
                for lot in lots:
                    if lot['month']>month:break
                    taken=min(lot['amount'],needed);lot['amount']-=taken;needed-=taken
                    held=month-lot['month']+(1 if method=='deposit' or timing=='beginning' else 0)
                    earned+=taken*partial_rate/1200*held
                    if needed<=0:break
                if needed>0.00001:raise ValueError('finance_partial_exceeds_deposits')
                withdrawn+=withdrawal['amount'];released_interest+=earned
                outflows.append({'month':month,'principal':withdrawal['amount'],'interest':earned,'fee':partial_fee,
                                 'after_tax':None if tax_rate is None else withdrawal['amount']+earned*(1-tax_rate/100)-partial_fee})
            retained=sum(lot['amount']*(growth(months-lot['month']+(1 if method=='deposit' or timing=='beginning' else 0))-1) for lot in lots)
            interest=released_interest+retained
            net=None if tax_rate is None else interest*(1-tax_rate/100)-partial_fee*len(partials)
            partial_result={'status':'input_based_scenario','withdrawals':outflows,'remaining_principal':principal-withdrawn,
                            'maturity_remaining':None if tax_rate is None else principal-withdrawn+retained*(1-tax_rate/100),
                            'proceeds':None if net is None else principal+net,'note':'월말 인출·먼저 납입한 원금부터 인출, 인출분은 확인 금리 단리, 잔액은 선택한 이자 방식 유지 가정. 기관의 실제 인출 규칙과 별도 확인.'}
        required=None
    return {'principal':principal,'interest':None if interest is None else round(interest,2),'tax_rate':tax_rate,'net_interest':None if net is None else round(net,2),
            'maturity':None if net is None else round(partial_result['maturity_remaining'] if partials else principal+net,2),'target_amount':target,'required_contribution':None if required is None else round(required,2),
            'goal_gap':None if target is None or net is None or partials else round(target-principal-net,2),'early_withdrawal':early,'partial_withdrawal':partial_result,'ladder':ladder,'contributions':contributions,
            'assumptions':f'{compounding} 이자 · {timing} 납입 · '+('지정한 월만 납입, 누락 월 0원, 목표 역산은 별도 확인. ' if contributions else '')+f' · 고정 금리. 만기 분산은 동일 금리 가정이며 기관별 기간 금리는 별도 확인.'}


def affordability(profile, estimate):
    income=number(profile.get('monthly_income'),optional=True);debt=number(profile.get('other_repayments'),optional=True)
    collateral=number(profile.get('collateral_value'),minimum=1,optional=True)
    shock=number(profile.get('income_drop_percent'),maximum=100,optional=True)
    return {'income_payment_ratio':None if income in (None,0) or debt is None else (debt+estimate['max_payment'])/income,
            'collateral_ratio':None if collateral is None else estimate['principal']/collateral,
            'income_after_shock':None if income is None or shock is None else income*(1-shock/100),
            'statutory_approval':None,'rule_status':'기관·차주·적용일별 규칙과 부채별 산정 정보 확인 필요',
            'basis':'입력한 월 소득·전체 상환액·담보가치의 단순 비율. 규정상 DSR/LTV 심사값이나 승인 한도가 아님.'}
