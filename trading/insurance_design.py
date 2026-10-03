"""Evidence-bounded coverage comparison. Never infers underwriting or cancellation suitability."""
from trading.finance_product_intelligence import number, instant
from datetime import datetime, timezone

TYPES = {
 'driver':('운전자','운전 용도·기존 자동차보험 특약·벌금/형사합의/변호사 비용의 사건별 지급 조건'),
 'medical':('의료비','실손/정액 지급 방식·자기부담·비급여/제외·갱신 조건'),
 'cancer':('암·건강','진단 정의·병기/종류별 지급액·면책/감액·재진단 조건'),
 'accident':('상해','상해의 약관 정의·직업/활동 제외·후유장해 지급 조건'),
 'auto':('자동차','차량/운전자 범위·대인/대물/자차·자기부담·운전 용도'),
 'income':('가족·소득','부양기간·소득 공백·공적/직장 보장·정기/종신의 보장기간 차이'),
 'term':('정기','부양이 필요한 기간·사망 지급 조건·보장 종료 시점'),
 'whole_life':('종신','평생 보장 목적·보험료 지속 가능성·해약환급금·저축 목적과의 구분'),
 'travel':('여행','국내/해외·여행기간·기존 질환/위험활동 제외·휴대품/배상 한도'),
 'home':('주택','주택 소유/임차·화재/배상 범위·재물 평가·자기부담'),
 'pension':('연금','연금 개시/수령기간·보증 여부·사업비·세제 자격·중도해지'),
 'saving':('저축성','납입/유지기간·사업비·해약환급금·보장과 적립금의 구분'),
}


def enrich_insurance(result, profile, offers, catalog):
    category=profile.get('insurance_kind','medical')
    if category not in TYPES:raise ValueError('finance_insurance_kind_unsupported')
    label,checks=TYPES[category]
    result['insurance_type']={'id':category,'label':label,'check':checks}
    budget=number(profile.get('insurance_budget'),optional=True)
    required=profile.get('required_coverages') or []
    if isinstance(required,str):required=[s.strip() for s in required.split(',') if s.strip()]
    if not isinstance(required,list) or len(required)>30 or not all(isinstance(v,str) and len(v)<200 for v in required):
        raise ValueError('finance_invalid_coverages')
    rows=[]
    facts=[]
    for raw in offers:
        if not isinstance(raw,dict) or not isinstance(raw.get('terms',{}),dict):raise ValueError('finance_invalid_offer')
        row=dict(raw);row['source_kind']='user_quote';rows.append(row)
    for row in (catalog or {}).get('products',[]):
        if row.get('kind')!='insurance' or row.get('terms',{}).get('category')!=category:continue
        if row.get('evidence_status')!='current':
            result['excluded'].append({'name':row['name'],'reason':'자료 만료·판매 종료'});continue
        rows.append(row)
    result['candidates']=[]
    for index,row in enumerate(rows):
        if row.get('source_kind')=='user_quote' and row.get('valid_until') and instant(row['valid_until'])<=datetime.now(timezone.utc):
            result['excluded'].append({'name':str(row.get('name','받은 견적'))[:200],'reason':'견적 유효기간 만료'});continue
        terms=row.get('terms') or {}
        premium=number(terms.get('monthly_premium'),optional=True)
        benefits=terms.get('benefits') or {}
        if not isinstance(benefits,dict) or len(benefits)>50:raise ValueError('finance_invalid_benefits')
        confirmed=terms.get('confirmed') is True and row.get('source_kind')=='user_quote'
        missing=[key for key in required if not benefits.get(key)]
        known=[key for key in required if benefits.get(key)]
        entry={'id':f'quote-{index}' if row.get('source_kind')=='user_quote' else f"{row.get('source_id')}:{row.get('id')}",'name':str(row.get('name','받은 견적'))[:200], 'monthly_premium':premium,
               'coverage':str(terms.get('coverage') or '미확인')[:2000], 'exclusions':str(terms.get('exclusions') or '미확인')[:2000],
               'renewal':str(terms.get('renewal') or '미확인')[:300], 'source_url':row.get('source_url'),
               'source_kind':row.get('source_kind'),'version':row.get('version'),'verified_at':row.get('verified_at'),'valid_until':row.get('valid_until'),
               'status':'user_confirmed_quote' if confirmed else 'quote_confirmation_required',
               'budget_fit':None if budget is None or premium is None else premium<=budget,
               'known_required_coverages':known,'unconfirmed_required_coverages':missing,
               'terms_complete':all(terms.get(k) for k in ('coverage','exclusions','renewal')),
               'representative_premium_only':row.get('source_kind')!='user_quote'}
        result['candidates'].append(entry);facts.append(benefits)
    result['coverage_matrix']=[{'coverage':name,'offers':[{'id':row['id'],'facts':facts[i].get(name),'status':'document_check_required' if facts[i].get(name) else 'unknown'} for i,row in enumerate(result['candidates'])]} for name in required]
    comparable=[r for r in result['candidates'] if r['monthly_premium'] is not None and r['status']=='user_confirmed_quote' and r['terms_complete']]
    affordable=[r for r in comparable if r['budget_fit'] is True]
    by_cost=sorted(affordable,key=lambda r:r['monthly_premium'])
    balanced=[r for r in by_cost if not r['unconfirmed_required_coverages'] and required]
    coverage_first=sorted(affordable,key=lambda r:(len(r['unconfirmed_required_coverages']),r['monthly_premium'])) if required else []
    result['design_options']=[
      {'id':'minimum_cost','title':'최소 부담','candidate_ids':[r['id'] for r in by_cost[:2]],'basis':'확인한 견적 중 월 예산 이내 보험료 순. 보장 손실은 비교표 확인.'},
      {'id':'balanced','title':'요구 보장과 예산 균형','candidate_ids':[r['id'] for r in balanced[:2]],'basis':'입력한 요구 보장 항목이 모두 기록되고 월 예산 이내인 견적. 지급 가능 여부는 약관 확인.'},
      {'id':'coverage_priority','title':'요구 보장 확인 우선','candidate_ids':[r['id'] for r in coverage_first[:2]],'basis':'예산 내 요구 보장 미확인 항목이 적은 견적부터 검토. 보장 품질 점수나 가입 순위가 아님.'},
    ]
    existing=number(profile.get('existing_premium'),optional=True)
    exit_cost=number(profile.get('cancellation_loss'),optional=True)
    result['change_scenarios']=[{'id':r['id'],'keep_monthly':existing,'add_monthly':None if existing is None or r['monthly_premium'] is None else existing+r['monthly_premium'],
      'replace_monthly':r['monthly_premium'],'cancellation_loss':exit_cost,
      'first_year_cash_difference':None if existing is None or r['monthly_premium'] is None or exit_cost is None else 12*(existing-r['monthly_premium'])-exit_cost,
      'unresolved':['새 면책·감액 기간','재심사·인수 여부','기존 환급 손실','갱신 보험료·보장 축소']} for r in result['candidates']]
    result['questions'].append(label+'에서 확인할 항목: '+checks)
    if budget is None:result['questions'].append('월 보험료 예산을 알려주세요. 예산을 임의로 정하지 않고 설계 후보를 보류합니다.')
    if not required:result['questions'].append('필요한 보장 항목을 정하세요. 요구 보장이 없으면 균형·보장 우선 설계를 확정하지 않습니다.')
    if not comparable:result['questions'].append('보장·제외·갱신 조건과 개인별 보험료를 확인한 견적이 있어야 세 설계안을 비교할 수 있습니다.')
    result['duplicate_note']='같은 보장명이 있다고 불필요한 중복으로 판정하지 않습니다. 실제 비용 비례보상인지 정액 지급인지, 지급 사건과 가입 시점별 약관을 대조하세요.'
    dependents=number(profile.get('dependents'),maximum=30,optional=True)
    if dependents is not None and dependents>0:
        result['priorities'].insert(0,'부양가족의 생활비·부양 기간과 소득 중단 대비를 먼저 확인')
        result['questions'].append('부양가족이 의존하는 월 생활비와 필요한 보장 기간은 얼마인가요?')
    occupation=str(profile.get('occupation_group') or 'unknown')
    if occupation in {'driving','physical','self_employed'}:
        result['questions'].append('직업·업무 중 운전/활동과 소득 공백을 약관이 어떻게 다루는지 확인하세요. 직업으로 인수나 보험료를 임의 추정하지 않습니다.')
    existing_coverages=profile.get('existing_coverages') or []
    if isinstance(existing_coverages,str):existing_coverages=[s.strip() for s in existing_coverages.split(',') if s.strip()]
    if not isinstance(existing_coverages,list) or len(existing_coverages)>50 or not all(isinstance(s,str) and len(s)<200 for s in existing_coverages):raise ValueError('finance_existing_coverages_invalid')
    if profile.get('insurance_state')=='none' and existing_coverages:raise ValueError('finance_insurance_state_conflict')
    checked=profile.get('existing_coverages_confirmed') in (True,'true') or profile.get('insurance_state')=='none'
    result['coverage_needs']=[{'coverage':name,'status':'existing_evidence_recorded' if name in existing_coverages else 'potential_gap' if checked else 'unknown',
                              'explanation':'보장 이름 기준 확인 목록이며 지급 여부·충분한 한도·불필요한 중복은 약관 대조가 필요합니다.'} for name in required]
    result['best']=None
    return result
