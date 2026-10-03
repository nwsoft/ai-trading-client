"""Local saved-plan review. Reminders do not imply application or contract status."""
from datetime import datetime, timezone
from trading.finance_product_intelligence import instant


def review_saved_plans(plans,catalog,at=None):
    at=at or datetime.now(timezone.utc)
    products={p['source_id']+':'+p['id']:p for p in catalog.get('products',[])}
    reviews=[]
    for plan in plans:
        reasons=[]
        if plan.get('reminder_date') and plan['reminder_date']<=at.date().isoformat():reasons.append('예약한 재점검일')
        for candidate in plan.get('result',{}).get('candidates',[]):
            name=candidate['name']
            if candidate.get('valid_until') and instant(candidate['valid_until'])<=at:reasons.append(name+': 견적·자료 기한 만료')
            if candidate.get('source_kind')=='operator_verified':
                current=products.get(candidate.get('id'))
                if not current:reasons.append(name+': 현재 공급 자료에서 확인되지 않음')
                elif current.get('evidence_status')!='current':reasons.append(name+': 만료·판매 종료')
                elif current.get('version')!=candidate.get('version'):reasons.append(name+': 상품 조건 버전 변경')
        reviews.append({'plan_id':plan['id'],'review_due':bool(reasons),'reasons':list(dict.fromkeys(reasons)),
                        'reminder_date':plan.get('reminder_date'),'automatic_external_notification':False,'contract_status':'not_asserted'})
    return reviews
