from copy import deepcopy
from datetime import date, datetime, timezone
from types import SimpleNamespace
import json
import pytest
from trading.finance_product_intelligence import ProductCatalog, compare_scenario
from trading.finance_scenarios import loan_projection, saving_projection
from trading.finance_rule_evidence import protection_check, eligibility_check
from trading.finance_followup import review_saved_plans
from web_platform.finance_ai import preview, explain
from web_platform.interactive_ai import InteractiveAIService


def scenario():
    return {'kind':'loan','profile':{'amount':1000000,'months':12,'private_health':'NEVER_SEND_HEALTH'},'offers':[{'name':'합성 견적','terms':{'annual_rate':3,'fees':0}}]}

@pytest.fixture
def ai(tmp_path):
    calls=[]
    def chat(*args,**kwargs):
        calls.append(args)
        return SimpleNamespace(ok=True,content='추가 비용을 확인하세요.',provider='synthetic',model='fixture',usage={})
    adapter=SimpleNamespace(is_ready=lambda:True,model='fixture',chat_text=chat)
    router=SimpleNamespace(spec=SimpleNamespace(provider='synthetic'),adapter=adapter)
    service=InteractiveAIService(data_dir=tmp_path,router_factory=lambda *a,**k:router)
    return service,calls,router

def test_ai_requires_exact_preview_and_does_not_cache_private_answer(ai):
    service,calls,_=ai
    p=preview(service,{},scenario(),'비교 결과를 설명해 줘',{},['numeric_results'])
    assert not calls and 'NEVER_SEND_HEALTH' not in json.dumps(p['packet'])
    payload={'scenario':scenario(),'question':'비교 결과를 설명해 줘','scopes':['numeric_results']}
    with pytest.raises(ValueError):explain(service,{},payload,{})
    payload['consent']={'confirmed':True,'payload_hash':p['payload_hash']}
    assert explain(service,{},payload,{})['status']=='explanation_draft'
    assert explain(service,{},payload,{})['status']=='explanation_draft'
    assert len(calls)==2 and not service.cache_path.exists()
    assert '비교 결과' not in service.usage_path.read_text()

def test_ai_change_of_model_or_scenario_invalidates_consent(ai):
    service,calls,router=ai
    p=preview(service,{},scenario(),'설명해 줘',{},['numeric_results'])
    payload={'scenario':scenario(),'question':'설명해 줘','scopes':['numeric_results'],'consent':{'confirmed':True,'payload_hash':p['payload_hash']}}
    router.adapter.model='changed'
    with pytest.raises(ValueError):explain(service,{},payload,{})
    assert not calls
    with pytest.raises(ValueError,match='route_changed'):
        service.ask(settings={},workload='assistant',question='q',context='',system_prompt='',max_tokens=200,expected_route=('synthetic','fixture'))
    assert not calls

def test_ai_unknown_numbers_fail_back_to_local_calculation(ai):
    service,calls,router=ai
    router.adapter.chat_text=lambda *a,**k:SimpleNamespace(ok=True,content='777777777원 수익을 보장합니다.',provider='synthetic',model='fixture',usage={})
    p=preview(service,{},scenario(),'설명해 줘',{},['numeric_results'])
    r=explain(service,{},{'scenario':scenario(),'question':'설명해 줘','scopes':['numeric_results'],'consent':{'confirmed':True,'payload_hash':p['payload_hash']}},{})
    assert r['status']=='local_fallback' and '777777777' not in r['answer'] and r['calculations_changed'] is False

def test_evidence_without_ai_rights_not_in_ai_packet(ai):
    service,_,_=ai
    row={'id':'p','source_id':'s','kind':'loan','name':'합성','provider':'fixture','version':'v1','source_url':'https://example.org/p','verified_at':'2020-01-01T00:00:00Z','valid_until':'2090-01-01T00:00:00Z','evidence_status':'current','terms':{'annual_rate':3,'fees':0},'evidence':[{'id':'c','text':'중도해지 비공개 AI 처리 권한 없음'}]}
    p=preview(service,{},scenario(),'중도해지 설명',{'products':[row]},['public_evidence'])
    assert p['packet']['facts']['clauses']==[]
    row['ai_processing_allowed']=True
    assert preview(service,{},scenario(),'중도해지 설명',{'products':[row]},['public_evidence'])['packet']['facts']['clauses']

def test_variable_rate_and_irregular_contributions_have_known_cashflows():
    r=loan_projection(1200000,12,12,'principal',0,{'rate_steps':'7:24'})
    # First six months 12%, last six 24%, declining monthly principal 100,000.
    assert r['interest']==99000 and r['schedule'][6]['annual_rate']==24
    r=saving_projection(100000,3,12,'installment',0,{'contributions':'1:100000,3:200000','withdraw_month':2,'withdraw_rate':6})
    assert r['principal']==300000 and r['interest']==5000 and r['maturity']==305000
    assert r['early_withdrawal']['after_tax']==101000

@pytest.mark.parametrize('schedule',['1:2,1:3','0:3','13:2','2:-1','2:3:4'])
def test_malformed_or_duplicate_rate_schedule_is_rejected(schedule):
    with pytest.raises(ValueError):loan_projection(1200000,12,3,'annuity',0,{'rate_steps':schedule})

def test_different_existing_contract_can_compare_and_missing_cost_is_not_zero():
    p=scenario();p['profile'].update(existing_rate=12,existing_exit_fee=1000,existing_terms_confirmed=True,existing_method='bullet',existing_remaining_fees=2000)
    r=compare_scenario(p)['candidates'][0]
    assert r['refinance']['estimated_saving']==round(122000-r['estimate']['total_cost']-1000,2)
    del p['profile']['existing_remaining_fees']
    assert compare_scenario(p)['candidates'][0]['refinance']['estimated_saving'] is None

def test_eligibility_invalid_bound_is_rejected_before_missing_profile():
    for rule in ({'age':{'min':90,'max':20}},{'age':{'min':None}},{'age':{}}):
        with pytest.raises(ValueError):eligibility_check({}, {'eligibility':rule})
    assert eligibility_check({}, {'eligibility':{'age':{'min':20}}})['status']=='needs_confirmation'
    assert eligibility_check({'age':19}, {'eligibility':{'age':{'min':20}}})['status']=='excluded'

def test_deposit_protection_needs_complete_holdings_and_current_rule():
    terms={'institution_id':'fixture','protection_scheme':'kr_general_deposit','protection_confirmed':True,'eligible_protection_interest':1000000}
    at=date(2026,10,3)
    assert protection_check({},terms,50000000,at)['excess'] is None
    profile={'institution_balances':{'fixture':{'confirmed':True,'principal_and_eligible_interest':60000000}}}
    r=protection_check(profile,terms,50000000,at)
    assert r['aggregate']==111000000 and r['excess']==11000000
    assert protection_check(profile,terms,50000000,date(2030,1,1))['status']=='rule_review_required'

def test_saved_comparison_reviews_version_expiry_and_due_date():
    plans=[{'id':'p','reminder_date':'2026-10-03','result':{'candidates':[{'id':'s:p','name':'old','version':'1','source_kind':'operator_verified','valid_until':'2026-10-01T00:00:00Z'}]}}]
    current={'products':[{'id':'p','source_id':'s','version':'2','evidence_status':'current'}]}
    r=review_saved_plans(plans,current,datetime(2026,10,3,tzinfo=timezone.utc))[0]
    assert r['review_due'] and len(r['reasons'])==3 and r['automatic_external_notification'] is False


def test_versioned_rules_require_effective_scope_and_explicit_inputs():
    from trading.finance_terms import lending_rules, tax_terms, rate_terms
    rule={'id':'synthetic','version':'1','scope':'합성 시험 전용','source_url':'https://example.org/rule','effective_from':'2026-01-01','valid_until':'2026-12-31','reviewed':True,'metric':'dsr','cap_percent':40,'context':{'borrower_type':'fixture'}}
    profile={'borrower_type':'fixture','annual_income':50000000,'regulated_annual_debt_service':15000000,'regulatory_inputs_confirmed':True}
    assert lending_rules({'lending_rules':[rule]},profile,{},date(2026,10,3))[0]['value_percent']==30
    assert lending_rules({'lending_rules':[rule]},profile,{},date(2027,1,1))[0]['value_percent'] is None
    assert lending_rules({'lending_rules':[rule]},{**profile,'borrower_type':'other'},{},date(2026,10,3))[0]['value_percent'] is None
    assert lending_rules({'lending_rules':[rule]},{**profile,'regulatory_inputs_confirmed':False},{},date(2026,10,3))[0]['value_percent'] is None
    tax={**rule,'tax_rate':0,'required_confirmations':['합성 자격']}
    assert tax_terms({'tax_rule':tax},{},date(2026,10,3))['rate'] is None
    assert tax_terms({'tax_rule':tax},{'confirmed_conditions':['합성 자격']},date(2026,10,3))['rate']==0
    terms={'base_rate':2,'max_rate':4,'rate_bonuses':[{'condition':'급여','percentage_points':1},{'condition':'카드','percentage_points':2}]}
    assert rate_terms(terms,{})['annual_rate']==2
    assert rate_terms(terms,{'confirmed_conditions':['급여']})['annual_rate']==3
    assert rate_terms(terms,{'confirmed_conditions':['급여','카드']})['annual_rate']==4


def test_bad_source_configuration_keeps_local_comparison_available(tmp_path):
    from trading.finance_source_connector import refresh_sources
    (tmp_path/'finance_product_sources.json').write_text('{bad')
    result=refresh_sources(ProductCatalog(tmp_path/'catalog.db'),tmp_path,transport=lambda *_:pytest.fail('no external call'))
    assert result['feeds'][0]['error_code']=='review_source_configuration'
    assert compare_scenario(scenario(),result)['best']=='합성 견적'


def test_rate_shock_also_applies_to_future_rate_steps():
    p=scenario();p['profile']['rate_steps']='1:6'
    r=compare_scenario(p)['candidates'][0]
    assert r['rate_plus_2pp_max_payment']>r['estimate']['max_payment']


def test_insurance_current_product_keeps_identity_for_followup():
    r=compare_scenario({'kind':'insurance','profile':{'insurance_kind':'driver'}},{'products':[{'kind':'insurance','id':'p','source_id':'s','name':'합성','version':'2','evidence_status':'current','terms':{'category':'driver'}}]})
    assert r['candidates'][0]['id']=='s:p' and r['candidates'][0]['version']=='2'
    with pytest.raises(ValueError):compare_scenario({'kind':'insurance','profile':{'insurance_state':'none','existing_coverages':'벌금'}})


def test_partial_withdrawal_distinguishes_intermediate_and_maturity_cash():
    p={'partial_withdrawals':'6:400000','partial_withdrawal_confirmed':True,'partial_withdrawal_rate':6,'partial_withdrawal_fee':1000}
    r=saving_projection(1000000,12,12,'deposit',0,p)
    assert r['interest']==84000 and r['net_interest']==83000
    assert r['maturity']==672000 and r['partial_withdrawal']['proceeds']==1083000
    del p['partial_withdrawal_fee']
    r=saving_projection(1000000,12,12,'deposit',0,p)
    assert r['maturity'] is None and r['interest'] is None
    with pytest.raises(ValueError):saving_projection(100000,12,3,'installment',0,{**p,'partial_withdrawal_fee':0,'partial_withdrawals':'1:200000'})


def test_recovery_unknown_reason_never_grants_reset_or_resume():
    from trading.operational_recovery_contract import recovery_contract
    r=recovery_contract(['made_up_error'])
    assert r['allowed_actions']==['export_diagnostic'] and not r['automatic_local_recheck_allowed']
    r=recovery_contract(['hard_stop_mdd_exceeded'])
    assert r['max_local_rechecks']==3 and not r['automatic_live_resume']
    assert 'review_policy' not in r['allowed_actions']
