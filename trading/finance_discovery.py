"""Situation-first education and bounded local routing; no underwriting decisions."""
import re
from copy import deepcopy
from datetime import datetime, timezone

from trading.finance_product_intelligence import instant, number

VERSION = 'discovery-20261005-1'
# Cards describe types, not offered products. Reasons must follow explicit goals.
GUIDES = {
 'insurance': {
  'medical': ('병원비가 걱정돼요', '실손·의료비 보장', '병원비 부담을 먼저 살펴보려는 목적입니다.', '실손은 실제 부담 의료비를 약관 범위에서, 정액형은 약정한 사건·금액을 기준으로 봅니다.', '자기부담·비급여·보장 제외·갱신 조건', 'insurance_kind', 'medical'),
  'driver': ('운전을 해요', '자동차보험과 운전자 보장', '운전 중 사고 비용을 대비하려는 목적입니다.', '자동차보험의 배상·차량 보장과 운전자보험의 형사합의·벌금·변호사 비용은 확인할 항목이 다릅니다.', '운전 용도·기존 자동차보험 특약·사건별 지급 조건·제외 사유', 'insurance_kind', 'driver'),
  'family': ('가족 생활비가 걱정돼요', '정기·소득 공백 대비', '가족이 의존하는 생활비와 필요한 부양 기간을 먼저 확인합니다.', '정기와 종신은 보장 기간이 다릅니다. 공적·직장 보장도 함께 확인하고 유지 가능한 보험료를 봅니다.', '부양 기간·생활비·보장 종료·소득 공백·납입 부담', 'insurance_kind', 'income'),
  'health': ('큰 질병이 걱정돼요', '암·건강 정액 보장', '진단·치료 중 큰 지출이나 소득 공백을 확인하려는 목적입니다.', '진단 이름만 같아도 약관의 진단 정의와 지급 조건은 다를 수 있습니다.', '진단 정의·면책·감액 기간·재진단·보장 기간', 'insurance_kind', 'cancer'),
 },
 'loan': {
  'living': ('생활자금이 필요해요', '신용·정책자금 조건 확인', '필요한 금액과 매달 갚을 여력을 먼저 정합니다.', '소득·기존 부채·자격에 따라 개인 한도와 금리가 달라집니다. 광고 최저금리로 상환 부담을 확정하지 않습니다.', '필요 금액·월 상환 여력·실제 금리·수수료', 'method', 'annuity'),
  'housing': ('집·전세 자금이 필요해요', '주거 목적 대출', '주거 목적과 자금이 필요한 날짜부터 구분합니다.', '구입과 전세는 담보·보증·계약 요건이 다릅니다. 주거 형태와 보증 가능 여부를 기관에 확인합니다.', '구입/전세·입주일·자기자금·담보/보증·변동금리', 'method', 'annuity'),
  'policy': ('정책 지원 대상인지 알아보고 싶어요', '정책 지원 대출', '대상 요건과 신청 기간을 먼저 확인합니다.', '상품별 소득·자산·용도·보증 요건이 다릅니다. 자격과 승인 금리는 기관 확인 전 확정하지 않습니다.', '지원 대상·용도·공급 기간·보증료·중복 지원 제한', 'method', 'annuity'),
  'refinance': ('기존 대출 부담을 줄이고 싶어요', '대환·상환 방식 비교', '현재 대출을 유지할 때와 바꿀 때의 총비용을 같은 남은 기간으로 비교합니다.', '금리가 낮아져도 중도상환수수료와 신규 비용 때문에 이득이 줄 수 있습니다.', '남은 원금·기간·기존 금리·종료 비용·새 견적', 'method', 'annuity'),
 },
 'savings': {
  'deposit': ('지금 목돈이 있어요', '정기예금', '지금 가진 돈을 일정 기간 맡기는 목적입니다.', '원금 전체의 예치 기간을 기준으로 이자를 봅니다. 사용할 날짜와 만기를 맞춰 확인합니다.', '맡길 금액·사용 날짜·실제 우대금리·중도해지 조건', 'method', 'deposit'),
  'installment': ('매달 조금씩 모으고 싶어요', '정기·자유적금', '매달 유지 가능한 납입액부터 정합니다.', '각 납입금의 예치 기간이 달라 예금과 같은 금리라도 이자가 다릅니다.', '월 납입액·목표 날짜·납입 누락·우대 조건·한도', 'method', 'installment'),
  'liquid': ('곧 쓰거나 비상금이에요', '수시 입출금·단기 보관', '돈을 꺼낼 수 있는 시점과 원금 보관 조건을 먼저 봅니다.', '만기 전에 쓸 돈은 높은 만기 금리만으로 고르기 어렵습니다. 입출금 조건과 적용 금리 구간을 확인합니다.', '사용 시점·인출 제한·적용 금액 구간·보호 대상', None, None),
 },
}
PATTERNS = {
 'insurance': {'medical':r'병원비|의료비|실손', 'driver':r'운전|자동차', 'family':r'부양|가족\s*생활비|소득\s*공백', 'health':r'암보험|큰\s*질병|암\s*보장'},
 'loan': {'policy':r'정책\s*(?:대출|지원|자금)|지원\s*대상', 'living':r'생활\s*자금', 'housing':r'전세|주택|집\s*구입', 'refinance':r'대환|갈아타|기존\s*대출'},
 'savings': {'deposit':r'목돈|예금', 'installment':r'매달|매월|적금', 'liquid':r'비상금|곧\s*쓸|곧\s*쓰|수시\s*입출금'},
}


def discover(payload, catalog=None):
    if not isinstance(payload, dict) or payload.get('kind') not in GUIDES:
        raise ValueError('finance_discovery_kind')
    kind = payload['kind']
    profile = payload.get('profile') or {}
    question = payload.get('question') or ''
    if not isinstance(profile, dict) or not isinstance(question, str) or len(question) > 2000:
        raise ValueError('finance_discovery_input')
    # Only these fields are needed by discovery; never echo arbitrary private fields.
    fields = {'discovery_goal','insurance_state','insurance_budget','amount','months','method','insurance_kind','declined_conditions','loan_purpose','liquid_days','reference_product_ids','discovery_product_ids'}
    profile = deepcopy({k:v for k,v in profile.items() if k in fields})
    if any(not isinstance(v, str) for k,v in profile.items() if k not in {'declined_conditions','reference_product_ids','discovery_product_ids'}):
        raise ValueError('finance_discovery_profile')
    conditions=profile.get('declined_conditions',[])
    if not isinstance(conditions,list) or len(conditions)>50 or not all(isinstance(v,str) and len(v)<=200 for v in conditions):
        raise ValueError('finance_discovery_profile')
    for key in ('reference_product_ids','discovery_product_ids'):
        ids=profile.get(key,[])
        if not isinstance(ids,list) or len(ids)>20 or not all(isinstance(v,str) and len(v)<=250 for v in ids):raise ValueError('finance_invalid_product_selection')
    if len(str(profile)) > 4000:
        raise ValueError('finance_discovery_profile_limit')
    if profile.get('insurance_state', 'unknown') not in {'unknown','none','existing'}:
        raise ValueError('finance_invalid_insurance_state')
    goal = profile.get('discovery_goal', 'unknown')
    if goal not in {'unknown', *GUIDES[kind]}:
        raise ValueError('finance_discovery_goal')
    from trading.finance_profile_parser import interpret
    profile, changes, unresolved = interpret(profile, question, kind)
    if re.search(r'보험.{0,10}(?:있는지|없는지|여부).{0,5}(?:몰|모르)',question):
        profile['insurance_state']='unknown'
    for field in ('insurance_budget','amount','months'):
        if profile.get(field):number(profile[field],minimum=1,maximum=600 if field=='months' else 1e12)
    matches = [key for key, pattern in PATTERNS[kind].items() if re.search(pattern, question)]
    # Negation, alternatives and multiple goals require a user's choice, not a guess.
    ambiguous = len(matches)>1 or (bool(matches) and bool(re.search(r'안\s*해|안\s*하|않|말고|아니|필요\s*없|하지\s*마|말아', question)))
    if ambiguous:
        unresolved.append('목적'); goal='unknown'
        profile.pop('insurance_kind', None)
    elif len(matches)==1:
        goal=matches[0]
    profile['discovery_goal'] = goal
    if goal=='unknown':profile.pop('insurance_kind',None)
    if kind=='loan' and goal!='unknown':
        if goal!='housing':profile['loan_purpose']=goal
        elif profile.get('loan_purpose') not in {'housing','mortgage','jeonse'}:profile['loan_purpose']='jeonse' if '전세' in question else 'mortgage' if re.search(r'구입|매매',question) else 'housing'
    profile.setdefault('insurance_state', 'unknown')
    selected = [goal] if goal!='unknown' else list(GUIDES[kind])
    cards=[]
    for key in selected:
        label,title,reason,explanation,checks,field,value=GUIDES[kind][key]
        cards.append(dict(id=key,label=label,title=title,reason=reason,explanation=explanation,checks=checks))
        if goal!='unknown' and field:
            if field=='method' and kind=='savings' and profile.get('method') not in (None,value) and not any(c['field']=='amount' for c in changes):
                profile.pop('amount',None)
            profile[field]=value
    if goal=='liquid':profile['method']='liquid'
    state=profile['insurance_state']
    answer = ('보험이 없어도 상품명이나 증권 없이 시작할 수 있습니다.' if state=='none' else
              '가입 여부를 몰라도 괜찮습니다. 보장이 없는 것으로 단정하지 않고 확인할 목록을 만듭니다.' if state=='unknown' else
              '기존 보험은 유지한 채 보장·면책·갱신 내역을 먼저 확인합니다.') if kind=='insurance' else '상품 이름을 몰라도 돈이 필요한 목적과 사용할 시점부터 정할 수 있습니다.'
    if ambiguous:
        answer+=' 여러 목적 또는 부정 표현이 있어 하나로 결정하지 않았습니다. 아래에서 먼저 알아볼 목적을 골라주세요.'
    elif goal=='unknown':
        answer+=' 아래 설명을 읽고 지금 가장 걱정되는 상황 하나를 골라주세요.'
    else:
        answer+=' '+cards[0]['reason']+' '+cards[0]['explanation']
    if question.strip() and not matches and not changes and not unresolved:
        from trading.finance_explanations import explain_terms
        terms=explain_terms(question)
        answer+=' '+(' '.join(terms) if terms else '이 문장은 현재 빠른 안내로 해석하지 못했습니다. 목적 버튼을 선택하거나 아래 AI 설명을 이용해 주세요.')
    questions = {
     'insurance':['매달 부담 없이 유지할 수 있는 보험료는 얼마인가요? 모르면 나중에 정해도 됩니다.', '기존 보장이 있다면 같은 항목의 지급 조건부터 확인하세요.'],
     'loan':['필요한 금액과 갚을 기간은 어느 정도인가요?', '생활비와 기존 상환액을 뺀 뒤 매달 갚을 수 있는 금액은 얼마인가요?'],
     'savings':['얼마를 맡기거나 매달 모을 수 있나요?', '이 돈을 언제 쓸 예정인가요? 중간에 꺼내야 하나요?'],
    }[kind]
    products=[]
    for row in (catalog or {}).get('products',[]):
        if row.get('kind')!=kind or row.get('evidence_status')!='current':continue
        try:
            if instant(row.get('valid_until')) <= datetime.now(timezone.utc):continue
        except (ValueError,TypeError,AttributeError):continue
        terms=row.get('terms') or {}
        if kind=='loan':
            from trading.finance_journey import loan_match
            if loan_match(profile,terms) is False:continue
        if goal!='unknown' and kind=='insurance' and terms.get('category')!=profile.get('insurance_kind'):continue
        if goal!='unknown' and kind=='savings' and terms.get('method')!=profile.get('method'):continue
        products.append({k:row.get(k) for k in ('id','source_id','name','provider','version','verified_at','valid_until','source_url')})
    from trading.finance_journey import reference_rows,reference_summary
    references=reference_rows(profile,catalog,question) if kind=='insurance' else []
    detail=reference_summary(references) if references and (profile.get('reference_product_ids') or any(r.get('provider','?') in question for r in references)) else ''
    return dict(reference_answer=detail,kind=kind,profile=profile,cards=cards,answer=answer,questions=questions,
                goal_options=[{'id':key,'label':value[0]} for key,value in GUIDES[kind].items()],
                products=products,reference_products=[r for r in (catalog or {}).get('reference_products',[]) if r.get('evidence_status')!='withdrawn'] if kind=='insurance' else [],unresolved=unresolved,rule_version=VERSION,
                decision=dict(route='local_rules',provider_called=False,next_action='clarify' if goal=='unknown' else 'review_types',reason='명시된 상황과 검증 자료만 사용'),
                catalog_notice='선택한 유형의 유효 자료입니다. 개인별 가입 자격·보험료·금리는 기관 확인이 필요합니다.' if products else
                '현재 이 목적에 연결된 유효 상품 자료가 없습니다. 회사·상품 순위를 만들지 않고 유형과 확인할 질문을 먼저 안내합니다.',
                can_compare=goal!='unknown', can_prepare=True, saved=False, application_submitted=False)
