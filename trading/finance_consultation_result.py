"""Bounded recipient-return data. A response is not a confirmed personal quote."""
from copy import deepcopy
import json
from trading.finance_product_intelligence import instant, public_url, number
from trading.finance_connections import digest


def validate(value,kind):
    if not isinstance(value,dict) or set(value)-{'assigned_advisor','expected_reply_at','quotes'}:raise ValueError('finance_reply_invalid')
    result={}
    advisor=value.get('assigned_advisor')
    if advisor is not None:
        if not isinstance(advisor,str) or len(advisor)>200 or '\x00' in advisor:raise ValueError('finance_advisor_invalid')
        result['assigned_advisor']=advisor
    at=value.get('expected_reply_at')
    if at:instant(at);result['expected_reply_at']=at
    quotes=value.get('quotes',[])
    if not isinstance(quotes,list) or len(quotes)>20:raise ValueError('finance_reply_quote_limit')
    output=[]
    allowed={'annual_rate','fees','tax_rate','monthly_premium','coverage','exclusions','renewal','conditions','benefits','method','category','institution_id','protection_scheme','protection_confirmed','eligible_protection_interest','rate_tiers','tier_mode','coverage_details','immediate_withdrawal_confirmed'}
    for row in quotes:
        if not isinstance(row,dict) or set(row)-{'id','name','provider','source_url','valid_until','terms'}:raise ValueError('finance_reply_quote_invalid')
        for key in ('id','name','provider'):
            if not isinstance(row.get(key),str) or not 0<len(row[key])<=200:raise ValueError('finance_reply_quote_invalid')
        public_url(row.get('source_url'));instant(row.get('valid_until'))
        terms=row.get('terms')
        if not isinstance(terms,dict) or set(terms)-allowed:raise ValueError('finance_reply_terms_invalid')
        for k in ('annual_rate','tax_rate'):number(terms.get(k),maximum=100,optional=True)
        for k in ('fees','monthly_premium','eligible_protection_interest'):number(terms.get(k),optional=True)
        for k in ('coverage','exclusions','renewal','institution_id'):
            if k in terms and (not isinstance(terms[k],str) or len(terms[k])>2000):raise ValueError('finance_reply_terms_invalid')
        if len(json.dumps(row,allow_nan=False,ensure_ascii=False))>16000:raise ValueError('finance_reply_quote_limit')
        conditions=terms.get('conditions',[])
        if not isinstance(conditions,list) or len(conditions)>30 or not all(isinstance(c,str) and len(c)<=200 for c in conditions):raise ValueError('finance_reply_terms_invalid')
        benefits=terms.get('benefits',{})
        if not isinstance(benefits,dict) or len(benefits)>50 or not all(isinstance(k,str) and len(k)<=200 and isinstance(v,str) and len(v)<=2000 for k,v in benefits.items()):raise ValueError('finance_reply_terms_invalid')
        clean=deepcopy(row);clean['terms']['confirmed']=False
        from trading.finance_product_intelligence import compare_scenario
        # Exercise the same calculation/shape validation using synthetic amounts,
        # not the user's private profile (which may not have been shared).
        profile={'amount':'1000000','months':'12','method':terms.get('method','annuity' if kind=='loan' else 'deposit'),'liquid_days':'30'}
        compare_scenario({'kind':kind,'profile':profile,'offers':[clean]},{})
        clean['quote_hash']=digest(clean);output.append(clean)
    if len({q['id'] for q in output})!=len(output):raise ValueError('finance_reply_quote_duplicate')
    result['quotes']=output
    return result
