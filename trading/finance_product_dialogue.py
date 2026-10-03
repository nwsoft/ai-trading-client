"""Natural-language scenario edits resolve to validated fields before recalculation."""
from copy import deepcopy
import re
from trading.finance_product_intelligence import compare_scenario, number

_MONEY=r'(\d+(?:\.\d+)?)\s*(억|천만|백만|십만|만|천)?\s*원'
FIELD_LABELS={'months':'기간(개월)','amount':'금액(원)','target_amount':'목표 금액(원)','insurance_budget':'월 보험료 예산(원)','monthly_income':'월 소득(원)','compounding':'이자 계산','ladder':'만기 분산','insurance_state':'보험 가입 상태','insurance_kind':'보장 종류','declined_conditions':'제외할 우대 조건'}
_UNIT={'억':100000000,'천만':10000000,'백만':1000000,'십만':100000,'만':10000,'천':1000,None:1}


def revise_scenario(scenario, question, catalog=None):
    if not isinstance(question,str) or not question.strip() or len(question)>2000:
        raise ValueError('finance_question_required')
    if not isinstance(scenario,dict) or scenario.get('kind') not in {'loan','savings','insurance'}:
        raise ValueError('finance_invalid_scenario')
    original=deepcopy(scenario); updated=deepcopy(scenario)
    from trading.finance_profile_parser import interpret
    updated['profile'],changes,unresolved=interpret(updated.get('profile') or {},question,updated['kind'])
    ambiguous=bool(unresolved)
    # All numbers come from the deterministic calculator, not generated prose.
    before=compare_scenario(original,catalog);result=compare_scenario(updated,catalog)
    from trading.finance_explanations import explain_terms
    summary=explain_terms(question)
    if ambiguous:summary.append('금액이나 기간이 여러 개여서 자동 변경하지 않았습니다. 바꿀 항목을 한 번에 하나씩 알려주세요.')
    if changes:
        summary.append('변경한 조건: '+', '.join(f"{FIELD_LABELS.get(r['field'], r['field'])} {r['before'] if r['before'] not in (None,'') else '미입력'} → {r['after']}" for r in changes))
    if result['best']:
        summary.append(f"현재 입력 조건에서 먼저 비교할 후보는 {result['best']}입니다. 기준은 {result['ranking_basis']}입니다.")
    elif updated['kind']=='insurance':
        summary.append(result['explanation'])
    else:
        summary.append('순위를 확정할 근거가 부족합니다. 비용·세율·우대 조건·유효한 상품 자료를 확인하세요.')
    deltas=[]
    for index,row in enumerate(result['candidates']):
        old=next((r for r in before['candidates'] if r.get('id')==row.get('id')),None)
        metric='total_cost' if updated['kind']=='loan' else 'maturity'
        value=row.get('estimate',{}).get(metric);prior=(old or {}).get('estimate',{}).get(metric)
        if value is not None and prior is not None:deltas.append({'name':row['name'],'metric':metric,'before':prior,'after':value,'difference':round(value-prior,2)})
    if not changes:summary.append('조건을 바꾸려면 “기간을 24개월로”, “매월 30만원으로”, “보험 예산 2만원”, “카드 조건은 제외”처럼 적어주세요.')
    evidence=[]
    for row in result['candidates']:
        estimate=row.get('estimate') or {}
        evidence.append({'name':row['name'],'source_kind':row.get('source_kind'),'source_url':row.get('source_url'),
                         'verified_at':row.get('verified_at'),'valid_until':row.get('valid_until'),'version':row.get('version')})
        if updated['kind']=='insurance':
            summary.append(f"{row['name']}: 월 보험료 {row['monthly_premium'] if row['monthly_premium'] is not None else '미확인'}, 보장 {row['coverage']}, 제외 {row['exclusions']}, 갱신 {row['renewal']}.")
        else:
            fields=[('전체 이자','interest'),('총비용','total_cost'),('최대 월 상환','max_payment')] if updated['kind']=='loan' else [('세전 이자','interest'),('세후 이자','net_interest'),('만기 금액','maturity')]
            summary.append(row['name']+': '+', '.join(label+' '+(f"{estimate[key]:,.2f}원" if estimate.get(key) is not None else '미확인') for label,key in fields)+'.')
            if row['unconfirmed_conditions']:summary.append('충족 확인이 필요한 조건: '+', '.join(row['unconfirmed_conditions']))
        summary.append('근거: '+str(row.get('source_url') or '확인 경로 미입력')+' · '+('사용자 입력 견적' if row.get('source_kind')=='user_quote' else '등록 상품 자료')+' · 유효 기한 '+str(row.get('valid_until') or '미확인'))
    from trading.finance_evidence import search_evidence
    clauses=search_evidence(catalog,question,updated['kind'])
    if clauses:summary.append('현재 유효한 상품 근거 '+str(len(clauses))+'건을 찾았습니다. 적용 버전·조항은 아래 근거에서 확인하세요.')
    summary.extend(result['questions'][:3])
    return {'scenario':updated,'result':result,'changes':changes,'deltas':deltas,'answer':'\n'.join(summary),
            'clauses':clauses,'unresolved':unresolved,'evidence':evidence,'provider_called':False,'source':'local_scenario_recalculation','saved':False}
