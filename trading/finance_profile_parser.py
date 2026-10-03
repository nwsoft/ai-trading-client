"""Bounded Korean multi-field interpretation with explicit unresolved ambiguity."""
import re
from copy import deepcopy
from trading.finance_product_intelligence import number

MONEY=r'(\d+(?:\.\d+)?)\s*(억|천만|백만|십만|만|천)?\s*원'
UNITS={'억':100000000,'천만':10000000,'백만':1000000,'십만':100000,'만':10000,'천':1000,None:1}
ANCHORS={
 'target_amount':r'목표(?:금액| 금액)?',
 'insurance_budget':r'(?:보험료?\s*예산|월\s*보험료|보험\s*예산|예산)',
 'monthly_income':r'(?:월\s*소득|월급|소득)',
 'monthly_expenses':r'(?:월\s*생활비|생활비)',
 'other_repayments':r'(?:기존\s*월\s*상환액|기존\s*상환액)',
 'amount':r'(?:빌릴\s*금액|대출\s*금액|예금\s*원금|납입액|매달|매월|목돈|대출|예금|적금|금액)',
}


def interpret(profile,question,kind):
    result=deepcopy(profile);updates={};unresolved=[];q=question.replace(',','')
    if re.search(r'-\s*\d',q):raise ValueError('finance_negative_question_value')
    consumed=[]
    for key,label in ANCHORS.items():
        matches=list(re.finditer(label+r'\s*(?:은|는|을|를|이|가|:)?\s*'+MONEY,q))
        matches=[m for m in matches if not any(a<=m.start(1)<b for a,b in consumed)]
        if len(matches)>1:unresolved.append(key);continue
        if matches:
            m=matches[0];updates[key]=str(number(float(m[1])*UNITS[m[2]],minimum=1));consumed.append((m.start(1),m.end()))
    all_money=list(re.finditer(MONEY,q))
    unmatched=[m for m in all_money if not any(a<=m.start()<b for a,b in consumed)]
    if len(all_money)==1 and unmatched and not updates:
        m=all_money[0];updates['insurance_budget' if kind=='insurance' else 'amount']=str(number(float(m[1])*UNITS[m[2]],minimum=1))
    elif unmatched:
        # Do not quietly take only one side of '100만원에서 200만원으로'.
        unresolved.append('금액');updates={k:v for k,v in updates.items() if k not in ANCHORS}
    term_matches=list(re.finditer(r'(\d+)\s*(개월|년)',q))
    used=[]
    for key,label in (('grace_months','거치'),('months','기간|만기')):
        matches=list(re.finditer(r'(?:'+label+r')\s*(?:를|을|은|는|:)?\s*(\d+)\s*(개월|년)',q))
        if len(matches)>1:unresolved.append(key);continue
        if matches:
            m=matches[0];n=int(m[1])*(12 if m[2]=='년' else 1);number(n,minimum=0 if key=='grace_months' else 1,maximum=600);updates[key]=str(n);used.append(m.start(1))
    remaining=[m for m in term_matches if m.start() not in used]
    if len(term_matches)==1 and remaining:updates['months']=str(int(remaining[0][1])*(12 if remaining[0][2]=='년' else 1))
    elif remaining:
        unresolved.append('기간');updates.pop('months',None);updates.pop('grace_months',None)
    if kind=='loan':
        for word,method in (('원리금균등','annuity'),('원금균등','principal'),('만기일시','bullet')):
            if word in q:updates['method']=method
    if kind=='savings':
        method='installment' if any(w in q for w in ('적금','매달','매월')) else 'deposit' if any(w in q for w in ('예금','목돈')) else None
        if method and method!=profile.get('method'):
            updates['method']=method
            if 'amount' not in updates:updates['amount']='';unresolved.append('목돈 또는 월 납입액')
        if '복리' in q:updates['compounding']='annual' if '연복리' in q else 'monthly'
        elif '단리' in q:updates['compounding']='simple'
        if '분산' in q:updates['ladder']='false' if any(w in q for w in ('안','취소','말')) else 'true'
    if kind=='insurance':
        if re.search(r'보험(?:이|은|도)?\s*없',q) or '미가입' in q:updates['insurance_state']='none'
        if re.search(r'보험(?:이|은|도)?\s*(?:있|가입했)',q):updates['insurance_state']='existing'
        if any(w in q for w in ('가입 여부 몰','가입했는지 몰','보험 있는지 몰')):updates['insurance_state']='unknown'
        for word,category in (('운전자','driver'),('실손','medical'),('암보험','cancer'),('자동차보험','auto'),('여행보험','travel'),('종신','whole_life'),('정기보험','term'),('상해보험','accident'),('소득보험','income'),('주택보험','home'),('연금보험','pension'),('저축성보험','saving')):
            if word in q:updates['insurance_kind']=category
        m=re.search(r'부양(?:가족)?\s*(\d+)명',q)
        if m:updates['dependents']=str(number(m[1],maximum=30))
    declined=list(profile.get('declined_conditions') or [])
    excluding=any(w in q for w in ('싫','안 할','안할','못 맞','못맞','제외')) and not any(w in q for w in ('제외하지','제외하지마','제외 안'))
    including=any(w in q for w in ('다시 포함','제외 취소'))
    for keyword in ('카드','급여','첫 거래','자동이체'):
        if keyword in q:
            if excluding and not including:declined.append(keyword)
            elif including:declined=[v for v in declined if v!=keyword]
    if declined!=list(profile.get('declined_conditions') or []):updates['declined_conditions']=list(dict.fromkeys(declined))
    result.update(updates)
    changes=[{'field':k,'before':profile.get(k),'after':v} for k,v in updates.items() if str(profile.get(k))!=str(v)]
    return result,changes,unresolved
