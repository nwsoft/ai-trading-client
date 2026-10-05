"""Shared purpose matching and grounded editorial explanations for finance UI/chat."""
from trading.finance_product_intelligence import instant
from datetime import datetime, timezone

LOAN_PURPOSES = {
    'living': {'living','credit','personal'},
    'housing': {'housing','mortgage','jeonse'},
    'mortgage': {'mortgage'}, 'jeonse': {'jeonse'},
    'refinance': {'refinance'}, 'policy': {'policy'},
}


def loan_match(profile, terms):
    purpose=profile.get('loan_purpose') or profile.get('discovery_goal','unknown')
    if purpose in ('unknown',''):return None
    if purpose not in LOAN_PURPOSES:raise ValueError('finance_invalid_loan_purpose')
    declared=terms.get('loan_purposes') or ([terms['category']] if terms.get('category') else [])
    if not isinstance(declared,list) or len(declared)>10 or not all(isinstance(v,str) for v in declared):
        raise ValueError('finance_invalid_loan_purposes')
    if not declared:return False
    return bool(LOAN_PURPOSES[purpose].intersection(declared))


def reference_rows(profile,catalog,question=''):
    from trading.insurance_reference_directory import selected_references
    if profile.get('reference_product_ids'):
        return selected_references(profile,catalog)
    rows=(catalog or {}).get('reference_products',[])
    providers={r['provider'] for r in rows if r.get('provider') and r['provider'] in question}
    category=profile.get('insurance_kind')
    if '운전자' in question:category='driver'
    elif '실손' in question:category='medical'
    elif '암보험' in question or '건강보험' in question:category='cancer'
    elif '정기보험' in question:category='income'
    if not providers and not category:return []
    return [r for r in rows if (not providers or r.get('provider') in providers) and
            (not category or r.get('category')==category) and r.get('evidence_status')!='withdrawn'][:8]


def reference_summary(rows):
    if not rows:return ''
    lines=['앱의 상품 안내 자료로 확인한 차이입니다. 개인 보험료·가입 가능 여부는 아직 확인되지 않았습니다.']
    for r in rows:
        current=r.get('evidence_status')=='reference'
        try:current=current and instant(r.get('review_due'))>datetime.now(timezone.utc)
        except ValueError:current=False
        lines.append(f"{r.get('provider','')} · {r['name']}")
        if not current:
            lines.append('자료 재확인 필요: 이전 정보로 현재 조건을 확정하지 않습니다.');continue
        lines += [f"보장 특징: {r.get('coverage','미확인')}",f"갱신·기간: {r.get('renewal','미확인')}",
                  f"확인할 것: {r.get('checks','미확인')}",f"근거: {r.get('source_url','')} · 확인 {r.get('observed_at','')} · 버전 {r.get('version','')}"]
    lines.append('같은 보장·기간의 개인 견적을 받아 보험료와 제외 조건을 함께 비교하세요. 현재 자료만으로 우열을 확정하지 않습니다.')
    return '\n'.join(lines)


def catalog_coverage(catalog):
    rows=(catalog or {}).get('products',[]);references=(catalog or {}).get('reference_products',[])
    groups=[]
    for kind in ('insurance','loan','savings'):
        current=[r for r in rows if r.get('kind')==kind and r.get('evidence_status')=='current']
        groups.append({'kind':kind,'current_products':len(current),'providers':len({r.get('provider') for r in current}),
                       'reference_products':len([r for r in references if r.get('evidence_status')!='withdrawn']) if kind=='insurance' else 0})
    return groups
