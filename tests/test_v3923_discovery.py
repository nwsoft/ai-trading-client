from copy import deepcopy
from types import SimpleNamespace
import pytest
from trading.finance_discovery import discover, GUIDES
from trading.finance_product_intelligence import compare_scenario, product_question_answer
from web_platform.finance_ai import preview, explain


def run(kind='insurance',question='',profile=None,catalog=None):
    return discover({'kind':kind,'question':question,'profile':profile or {}},catalog)

@pytest.mark.parametrize('kind',GUIDES)
def test_novice_needs_no_product_or_money(kind):
    r=run(kind)
    assert r['cards'] and r['goal_options'] and not r['products']
    assert r['can_compare'] is False and r['decision']['provider_called'] is False
    assert r['saved'] is False and r['application_submitted'] is False
    assert '유효 상품 자료가 없습니다' in r['catalog_notice']

@pytest.mark.parametrize('state',['none','unknown','existing'])
@pytest.mark.parametrize('goal',GUIDES['insurance'])
def test_insurance_choices_have_reason_and_transfer_without_invented_budget(state,goal):
    r=run(profile={'insurance_state':state,'discovery_goal':goal})
    assert r['cards'][0]['id']==goal and r['cards'][0]['reason'] and r['cards'][0]['checks']
    assert r['profile']['insurance_state']==state and not r['profile'].get('insurance_budget')
    compared=compare_scenario({'kind':'insurance','profile':r['profile']})
    assert compared['insurance_type']['id']==r['profile']['insurance_kind']
    assert compared['best'] is None

def test_conversation_retains_state_and_budget():
    a=run(question='보험이 없고 운전을 해요')
    b=run(question='보험 예산 2만원',profile=a['profile'])
    assert b['profile']['insurance_state']=='none' and b['profile']['insurance_kind']=='driver'
    assert float(b['profile']['insurance_budget'])==20000
    assert '자동차보험' in b['answer']

@pytest.mark.parametrize('q',['운전을 안 해요','운전보험 말고 병원비','운전과 의료비 둘 다','운전자 필요 없어요'])
def test_ambiguous_or_negated_intent_is_not_recommendation(q):
    r=run(question=q,profile={'discovery_goal':'driver','insurance_kind':'driver'})
    assert r['decision']['next_action']=='clarify' and r['can_compare'] is False
    assert not r['products'] and '목적' in r['unresolved']

def test_unknown_insurance_is_not_none():
    assert run(question='보험이 없는지 모르겠어요')['profile']['insurance_state']=='unknown'

@pytest.mark.parametrize('kind,q,goal',[('loan','전세 자금이 필요해요','housing'),('loan','기존 대출 갈아타고 싶어요','refinance'),('savings','매달 30만원 기간 1년','installment'),('savings','비상금이고 곧 써요','liquid')])
def test_purpose_routing(kind,q,goal):
    r=run(kind,q)
    assert r['profile']['discovery_goal']==goal
    if goal=='installment':assert float(r['profile']['amount'])==300000 and r['profile']['months']=='12'
    if goal=='liquid':assert not r['can_compare'] and not r['products']

def test_switching_monthly_to_lump_sum_does_not_reuse_money():
    r=run('savings',profile={'method':'installment','amount':'300000','discovery_goal':'deposit'})
    assert r['profile']['method']=='deposit' and not r['profile'].get('amount')

def test_unknown_free_text_does_not_pretend_understanding():
    assert '해석하지 못했습니다' in run(question='아무 상품이나 무조건 가입시켜')['answer']

@pytest.mark.parametrize('profile',[{'amount':[]},{'declined_conditions':'card'},{'months':'601'},{'discovery_goal':'invented'},{'insurance_state':'invented'}])
def test_invalid_profile_rejected(profile):
    with pytest.raises(ValueError):run(profile=profile)

def catalog():
    return {'products':[dict(id=id,source_id='test',kind='insurance',name='합성 '+id,provider='합성 보험사',version='test',source_url='https://example.org/product',verified_at='2026-10-01T00:00:00Z',valid_until=until,evidence_status=status,terms={'category':category}) for id,until,status,category in [('driver','2099-01-01T00:00:00Z','current','driver'),('old','2020-01-01T00:00:00Z','current','driver'),('withdrawn','2099-01-01T00:00:00Z','withdrawn','driver'),('medical','2099-01-01T00:00:00Z','current','medical')]]}

def test_only_matching_current_products_and_selection_reaches_comparator():
    c=catalog();r=run(profile={'discovery_goal':'driver'},catalog=c)
    assert [p['id'] for p in r['products']]==['driver']
    profile={**r['profile'],'discovery_product_ids':['test:driver']}
    result=compare_scenario({'kind':'insurance','profile':profile},c)
    assert [p['name'] for p in result['candidates']]==['합성 driver']
    assert result['best'] is None
    assert {p['id'] for p in run(catalog=c)['products']}=={'driver','medical'}

def test_assistant_explains_types_for_first_time_user():
    answer=product_question_answer('보험이 없고 운전을 해요. 어떤 걸 비교해야 해요?')
    assert '상품명이나 증권 없이' in answer and '자동차보험과 운전자 보장' in answer


def test_discovery_ai_fast_route_consent_binding_and_privacy():
    calls=[];routes=[]
    def router(settings,**kwargs):
        routes.append(kwargs['workload']);return SimpleNamespace(spec=SimpleNamespace(provider='synthetic'),adapter=SimpleNamespace(model='fixture'))
    def ask(**kwargs):
        calls.append(kwargs);return {'answer':'지급 조건을 확인하세요.','provider_called':True}
    service=SimpleNamespace(router_factory=router,ask=ask)
    scenario={'kind':'insurance','mode':'discovery','profile':{'discovery_goal':'driver','insurance_state':'none','private_health':'NEVER_SEND'}}
    payload={'scenario':scenario,'question':'뭘 비교할까요?','scopes':['numeric_results'],'workload':'frequent_cheap'}
    p=preview(service,{},scenario,payload['question'],{},payload['scopes'],'frequent_cheap')
    assert not calls and routes==['frequent_cheap'] and 'NEVER_SEND' not in str(p)
    with pytest.raises(ValueError,match='consent'):explain(service,{},payload,{})
    payload['consent']={'confirmed':True,'payload_hash':p['payload_hash']}
    assert explain(service,{},payload,{})['status']=='explanation_draft'
    assert calls[0]['workload']=='frequent_cheap' and calls[0]['persist_response'] is False
    changed=deepcopy(payload);changed['workload']='assistant'
    with pytest.raises(ValueError,match='consent'):explain(service,{},changed,{})
    assert len(calls)==1


def test_discovery_application_route_does_not_refresh_remote_sources(tmp_path,monkeypatch):
    from threading import RLock
    from web_platform.application_services import ApplicationServices
    from trading.finance_product_intelligence import ProductCatalog
    service=ApplicationServices.__new__(ApplicationServices)
    service._lock=RLock();service.account='synthetic';service.data_dir=tmp_path
    def forbidden(*a,**kw):raise AssertionError('discovery must not poll remote feeds')
    monkeypatch.setattr(ProductCatalog,'refresh_feeds',forbidden)
    response=service.product_intelligence({'action':'discover','kind':'insurance','question':'보험이 없고 운전해요'})
    assert response['profile']['insurance_kind']=='driver'
    service.account='local'
    with pytest.raises(ValueError,match='login_required'):
        service.product_intelligence({'action':'discover','kind':'insurance'})
