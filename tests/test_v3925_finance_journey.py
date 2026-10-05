from copy import deepcopy
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
import json
import pytest
from trading.finance_product_intelligence import ProductCatalog,compare_scenario,product_question_answer
from trading.finance_discovery import discover
from trading.finance_liquidity import liquid_interest
from trading.finance_followup import review_saved_plans
from trading.insurance_reference_directory import BUNDLED,import_rows
from trading.insurance_workspace import InsuranceWorkspace,InsuranceError
from trading.finance_reference_feed import apply,refresh,status,rollback
from trading.finance_connections import digest
from trading.finance_consultation_result import validate
from trading.finance_ledger import dispatch as ledger
from trading.life_finance import LifeFinanceManager
from web_platform.finance_ai import preview,explain

NOW=datetime.now(timezone.utc)
FUTURE=(NOW+timedelta(days=20)).isoformat()
PAST=(NOW-timedelta(days=20)).isoformat()
def reference():
    row=deepcopy(BUNDLED[0]);row.update(observed_at=NOW.isoformat(),review_due=FUTURE);return row

def product(id,purpose):
    return {'id':id,'source_id':'fixture','source_kind':'operator_verified','kind':'loan','name':id,'provider':'test','version':'1','source_url':'https://example.org/p','verified_at':PAST,'valid_until':FUTURE,'evidence_status':'current','terms':{'category':purpose,'annual_rate':3,'fees':0}}

def test_purpose_filter_in_discovery_and_actual_comparison():
    catalog={'products':[product('housing','housing'),product('living','living'),product('unknown',None)]}
    result=discover({'kind':'loan','profile':{'discovery_goal':'housing'}},catalog)
    assert [r['id'] for r in result['products']]==['housing']
    compared=compare_scenario({'kind':'loan','profile':{**result['profile'],'amount':1000000,'months':12}},catalog)
    assert [r['name'] for r in compared['candidates']]==['housing']
    assert len(compared['excluded'])==2

@pytest.mark.parametrize('purpose',['mortgage','jeonse','policy','refinance'])
def test_specific_purpose_does_not_match_other_purposes(purpose):
    catalog={'products':[product(v,v) for v in ['mortgage','jeonse','policy','refinance','living']]}
    result=compare_scenario({'kind':'loan','profile':{'loan_purpose':purpose,'amount':1000000,'months':12}},catalog)
    assert [r['name'] for r in result['candidates']]==[purpose]

@pytest.mark.parametrize('kind',['insurance','loan','savings'])
def test_unknown_purpose_can_prepare_without_decision(kind):
    result=discover({'kind':kind})
    assert result['can_prepare'] and not result['can_compare'] and not result['products']
    assert compare_scenario({'kind':kind,'profile':result['profile']})['best'] is None

def test_reference_answer_and_assistant_read_same_names(tmp_path):
    catalog=ProductCatalog(tmp_path/'p.db').snapshot()
    p={'insurance_kind':'driver','reference_product_ids':['samsung-driver','hyundai-driver']}
    r=discover({'kind':'insurance','profile':p,'question':'선택한 두 상품의 차이'},catalog)
    assert '삼성화재' in r['reference_answer'] and '현대해상' in r['reference_answer']
    answer=product_question_answer('삼성화재와 현대해상 운전자보험 차이가 뭐야?',catalog=catalog)
    assert '갱신' in answer and '삼성화재' in answer and '현대해상' in answer

@pytest.mark.parametrize('change',['expired','version','withdrawn','missing'])
def test_saved_reference_review(change,tmp_path):
    catalog=ProductCatalog(tmp_path/'p.db').snapshot();ref=catalog['reference_products'][0]
    plan={'id':'p','result':{'reference_products':[deepcopy(ref)]}}
    if change=='missing':catalog['reference_products']=[]
    elif change=='version':ref['version']='new'
    elif change=='withdrawn':ref['evidence_status']='withdrawn'
    else:ref['review_due']=PAST
    assert review_saved_plans([plan],catalog)[0]['review_due']

def test_ai_bundled_editorial_allowed_but_imports_need_permission(tmp_path):
    store=ProductCatalog(tmp_path/'p.db');catalog=store.snapshot();calls=[]
    router=SimpleNamespace(spec=SimpleNamespace(provider='synthetic'),adapter=SimpleNamespace(model='fixture'))
    ai=SimpleNamespace(router_factory=lambda *a,**k:router)
    s={'kind':'insurance','mode':'discovery','profile':{'reference_product_ids':['samsung-driver']}}
    r=preview(ai,{},s,'이 상품 설명',catalog,['numeric_results','public_evidence'])
    assert r['packet']['facts']['reference_products'][0]['id']=='samsung-driver'
    first=r['payload_hash'];ref=reference();ref['version']='operator';import_rows(store.path,[ref]);catalog=store.snapshot()
    r=preview(ai,{},s,'이 상품 설명',catalog,['numeric_results','public_evidence'])
    assert r['packet']['facts']['reference_products']==[] and r['payload_hash']!=first

def test_liquid_tier_known_values_and_tax_unknown():
    t={'rate_tiers':[{'up_to':1000000,'annual_rate':3},{'up_to':None,'annual_rate':1}],'tax_rate':0}
    assert liquid_interest(2000000,365,t)['interest']==40000
    assert liquid_interest(2000000,365,{**t,'tier_mode':'whole_balance'})['interest']==20000
    assert liquid_interest(1000000,365,{**t,'tier_mode':'whole_balance'})['interest']==30000
    del t['tax_rate'];assert liquid_interest(2000000,365,t)['maturity'] is None

@pytest.mark.parametrize('tiers',[
    [{'up_to':100,'annual_rate':1},{'up_to':50,'annual_rate':2}],
    [{'up_to':None,'annual_rate':1},{'up_to':50,'annual_rate':2}],
    [{'up_to':100,'annual_rate':1}],
    [{'up_to':None,'annual_rate':-1}],
    [{'up_to':None,'annual_rate':101}],
])
def test_liquid_bad_tiers_fail(tiers):
    with pytest.raises(ValueError):liquid_interest(1000000,30,{'rate_tiers':tiers})

def test_liquid_plan_saves_and_unlocks_without_rates(tmp_path):
    w=InsuranceWorkspace(tmp_path,'synthetic');w.unlock('synthetic-password-123')
    s={'kind':'savings','profile':{'method':'liquid'}}
    assert w.finance_plan('save',s)['plans'][0]['result']['status']=='planning'
    w.lock();w.unlock('synthetic-password-123')
    assert w.finance_plan()['plans'][0]['scenario']==s
    w.lock()

def test_reusable_profile_is_explicit_isolated_encrypted_and_resettable(tmp_path):
    w=InsuranceWorkspace(tmp_path,'a');w.unlock('synthetic-password-123')
    with pytest.raises(InsuranceError):w.finance_profile('save',{'monthly_income':123456})
    with pytest.raises(InsuranceError):w.finance_profile('save',{'private_health':'x'},True)
    r=w.finance_profile('save',{'monthly_income':'123456','monthly_expenses':'0'},True)
    assert r['profile']['values']['monthly_expenses']=='0.0'
    assert b'123456' not in w.path.read_bytes()
    other=InsuranceWorkspace(tmp_path,'b');other.unlock('synthetic-password-123');assert other.finance_profile()['profile'] is None
    w.finance_profile('reset',confirmed=True);assert w.finance_profile()['profile'] is None
    w.lock();other.lock()


def cfg():return {'id':'editor','api_url':'https://example.org/feed','enabled':True,'interval_seconds':900,'owner':'fixture owner','contact_url':'https://example.org/contact','editorial_rights_reference':'authored test text','ai_processing_allowed':True}
def packet(sequence=1,rows=None):return {'schema':'noah-insurance-reference-v1','source_id':'editor','sequence':sequence,'published_at':NOW.isoformat(),'products':[reference()] if rows is None else rows}

def test_feed_atomic_replay_withdrawal_failure_and_rollback(tmp_path):
    path=ProductCatalog(tmp_path/'p.db').path;c=cfg();a=apply(path,c,packet(),100)
    with pytest.raises(ValueError):apply(path,c,packet(1,[]),101)
    with pytest.raises(ValueError):apply(path,c,packet(0,[]),101)
    assert next(r for r in ProductCatalog(path).snapshot()['reference_products'] if r['id']=='samsung-driver')['evidence_status']=='reference'
    apply(path,c,packet(2,[]),200)
    assert next(r for r in ProductCatalog(path).snapshot()['reference_products'] if r['id']=='samsung-driver')['evidence_status']=='withdrawn'
    rollback(path,a['revision']);assert status(path)[0]['status']=='paused_after_rollback'
    (tmp_path/'finance_reference_source.json').write_text(json.dumps(c))
    refresh(path,tmp_path,True,transport=lambda _:pytest.fail('paused must not fetch'),stamp=300)


def test_feed_failure_preserves_dates_and_throttles_retry(tmp_path):
    path=ProductCatalog(tmp_path/'p.db').path;c=cfg();apply(path,c,packet(),100)
    (tmp_path/'finance_reference_source.json').write_text(json.dumps(c));calls=[]
    def fail(_):calls.append(1);raise RuntimeError('do not expose credential')
    result=refresh(path,tmp_path,True,fail,stamp=110)
    assert result[0]['status']=='refresh_failed' and result[0]['sequence']==1
    refresh(path,tmp_path,True,fail,stamp=111);assert len(calls)==1
    row=next(r for r in ProductCatalog(path).snapshot()['reference_products'] if r['id']=='samsung-driver')
    assert row['review_due']==FUTURE and 'credential' not in json.dumps(result)

def returned():return {'assigned_advisor':'합성 상담사','expected_reply_at':FUTURE,'quotes':[{'id':'q','provider':'test','name':'개인 견적','source_url':'https://example.org/q','valid_until':FUTURE,'terms':{'annual_rate':3,'fees':0}}]}
def test_recipient_result_validated_and_never_autoconfirmed():
    r=validate(returned(),'loan');assert not r['quotes'][0]['terms']['confirmed'] and r['quotes'][0]['quote_hash']
    wrong=returned();wrong['quotes'][0]['terms']['annual_rate']=-1
    with pytest.raises(ValueError):validate(wrong,'loan')
    wrong=returned();wrong['quotes'].append(deepcopy(wrong['quotes'][0]))
    with pytest.raises(ValueError):validate(wrong,'loan')

def test_normalized_coverage_retains_unknown_and_confirmed_existing():
    details=[{'name':'진단비','amount':None,'benefit_kind':'fixed','conditions':'확인한 정의','deductible':'미확인'}]
    s={'kind':'insurance','profile':{'insurance_state':'existing','required_coverages':'진단비','existing_coverage_details':details},'offers':[{'name':'new','terms':{'coverage_details':details}}]}
    result=compare_scenario(s);matrix=result['coverage_matrix'][0]
    assert matrix['existing']['amount'] is None and matrix['offers'][0]['structured']['amount'] is None and result['best'] is None

def test_breakeven_requires_costs_and_uses_interest_not_principal():
    s={'kind':'loan','profile':{'amount':1200000,'months':12,'method':'bullet','existing_rate':12,'existing_exit_fee':10000},'offers':[{'name':'new','terms':{'annual_rate':6,'fees':10000}}]}
    r=compare_scenario(s)['candidates'][0]['refinance'];assert r['breakeven_month']==4 and r['estimated_saving']==52000
    s['profile'].pop('existing_exit_fee');assert compare_scenario(s)['candidates'][0]['refinance']['breakeven_month'] is None

def tx():return {'date':'2026-10-01','amount':10000,'type':'지출','description':'합성 식비','method':'카드'}
def test_ledger_preview_duplicate_conflict_and_edit(tmp_path):
    manager=LifeFinanceManager(str(tmp_path));rows=[tx(),tx()]
    preview=ledger(manager,{'operation':'preview_import','rows':rows});assert len(preview['rows'])==1 and preview['duplicate_rows']==[2]
    assert not manager.get_transactions()
    with pytest.raises(ValueError):ledger(manager,{'operation':'import','rows':rows,'confirmed':True,'preview_hash':'changed'})
    assert ledger(manager,{'operation':'import','rows':rows,'confirmed':True,'preview_hash':preview['preview_hash']})['imported']==1
    assert ledger(manager,{'operation':'preview_import','rows':rows})['duplicate_rows']==[1,2]
    row=ledger(manager,{'query':'식비'})['rows'][0]
    changed={**tx(),'amount':20000};ledger(manager,{'operation':'update','id':row['id'],'row':changed,'expected_revision':row['revision']})
    with pytest.raises(ValueError):ledger(manager,{'operation':'update','id':row['id'],'row':tx(),'expected_revision':row['revision']})
    assert ledger(manager,{'start':'2026-10-02'})['total']==0
    with pytest.raises(ValueError):ledger(manager,{'operation':'preview_import','rows':[{**tx(),'amount':-1}]})

def test_liquidity_priority_does_not_pick_inaccessible_high_rate():
    s={'kind':'savings','profile':{'amount':1000000,'months':12,'method':'deposit','priority':'liquidity','planned_start_date':'2026-10-05','use_date':'2027-03-01'},'offers':[{'name':'high','terms':{'annual_rate':10,'tax_rate':0}}]}
    r=compare_scenario(s);assert r['best'] is None and r['candidates'][0]['liquidity']['fits_use_date'] is False
    s['profile']['use_date']='2027-10-05';assert compare_scenario(s)['best']=='high'
    del s['profile']['planned_start_date'];assert compare_scenario(s)['best'] is None

def test_liquid_withdrawal_and_amount_eligibility():
    s={'kind':'savings','profile':{'amount':2000000,'liquid_days':365,'method':'liquid','priority':'liquidity'},'offers':[{'name':'x','terms':{'annual_rate':2,'tax_rate':0}}]}
    assert compare_scenario(s)['best'] is None
    s['offers'][0]['terms']['immediate_withdrawal_confirmed']=True;assert compare_scenario(s)['best']=='x'
    s['offers'][0]['terms']['max_amount']=1000000;assert not compare_scenario(s)['candidates']

def test_korean_fixed_journey_cases():
    from scripts.evaluate_finance_journey import evaluate
    report=evaluate();assert report['passed']==report['total']==15 and report['provider_calls']==0

def test_tax_year_is_requested_context_not_applied_law_claim():
    from web_platform.application_services import ApplicationServices
    service=ApplicationServices.__new__(ApplicationServices)
    service.advanced=SimpleNamespace(calculate_tax=lambda **k:{'result':{}})
    service._audit=lambda *a:None
    result=service.calculate_life_tax(calculation='year_end',values={},tax_year=2026)
    assert result['year_context']['requested_year']==2026 and result['year_context']['applied_law_year'] is None
    with pytest.raises(ValueError):service.calculate_life_tax(calculation='year_end',values={},tax_year=9999)

def test_ledger_gateway_does_not_echo_private_invalid_input(tmp_path):
    from fastapi.testclient import TestClient
    from web_platform.gateway import create_gateway_app
    manager=LifeFinanceManager(str(tmp_path))
    services=SimpleNamespace(account='synthetic',runtime_snapshot=lambda:{},life_ledger=lambda payload:ledger(manager,payload))
    client=TestClient(create_gateway_app(token='synthetic-long-token-for-tests-only',application_services=services))
    headers={'Authorization':'Bearer synthetic-long-token-for-tests-only','X-NoahAI-Intent':'confirmed'}
    payload={'operation':'preview_import','rows':[{**tx(),'amount':-1,'description':'PRIVATE_TEST_DESCRIPTION'}]}
    response=client.post('/api/v1/life-finance/ledger',json=payload,headers=headers)
    assert response.status_code==400 and 'PRIVATE_TEST_DESCRIPTION' not in response.text
    assert client.post('/api/v1/life-finance/ledger',json={'operation':'list'}).status_code==401
    response=client.post('/api/v1/life-finance/ledger',json={'operation':'list'},headers=headers)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'

def test_imported_recipient_quote_requires_current_condition_confirmation():
    s={'kind':'loan','profile':{'amount':1000000,'months':12},'offers':[{'name':'reply','returned_quote_key':'receipt:hash','terms':{'annual_rate':3,'fees':0,'confirmed':False}}]}
    r=compare_scenario(s);assert r['best'] is None and r['candidates'][0]['quote_confirmation_required']
    s['offers'][0]['terms']['confirmed']=True;assert compare_scenario(s)['best']=='reply'

def test_feed_can_expand_supported_types_without_client_patch(tmp_path):
    row=reference();row.update(id='fixture-travel',category='travel',name='합성 여행 상품')
    path=ProductCatalog(tmp_path/'p.db').path;apply(path,cfg(),packet(rows=[row]))
    assert next(r for r in ProductCatalog(path).snapshot()['reference_products'] if r['id']=='fixture-travel')['category_label']=='여행'

def test_received_quote_type_cannot_mix_insurance_categories():
    s={'kind':'insurance','profile':{'insurance_kind':'driver'},'offers':[{'name':'wrong type','terms':{'category':'medical','monthly_premium':10000,'confirmed':True}}]}
    r=compare_scenario(s);assert not r['candidates'] and r['excluded'][0]['reason']=='보험 종류 불일치'
