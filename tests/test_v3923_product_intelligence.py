from datetime import datetime, timezone
from copy import deepcopy
import pytest
from trading.finance_product_intelligence import ProductCatalog, compare_scenario, loan_cashflow, saving_cashflow, product_question_answer
from trading.insurance_workspace import InsuranceWorkspace, InsuranceError

NOW=datetime(2026,10,3,tzinfo=timezone.utc)
SOURCE={'id':'synthetic','url':'https://example.org/products','rights_verified':True,'rights_reference':'synthetic test fixture'}
def product(**changes):
    return {'id':'one','name':'fixture','provider':'fixture','kind':'savings','version':'1','source_url':'https://example.org/p','verified_at':'2026-10-02T00:00:00Z','valid_until':'2026-10-04T00:00:00Z','status':'active','terms':{'annual_rate':3,'tax_rate':15.4},**changes}

def test_catalog_atomic_refresh_expiry_and_withdrawal(tmp_path):
    catalog=ProductCatalog(tmp_path/'catalog.db')
    assert catalog.snapshot(now=NOW)['status']=='source_not_connected'
    catalog.ingest(SOURCE,[product()],now=NOW)
    assert catalog.snapshot(now=NOW)['current_count']==1
    with pytest.raises(ValueError):catalog.ingest(SOURCE,[product(),product(id='bad',valid_until='bad')],now=NOW)
    assert catalog.snapshot(now=NOW)['current_count']==1
    assert catalog.snapshot(now=datetime(2026,10,5,tzinfo=timezone.utc))['products'][0]['evidence_status']=='stale'
    catalog.ingest(SOURCE,[product(status='withdrawn')],now=NOW)
    assert catalog.snapshot(now=NOW)['current_count']==0
    catalog.ingest(SOURCE,[],now=NOW)
    assert catalog.snapshot(now=NOW)['products']==[]


def test_rights_and_url_validation(tmp_path):
    catalog=ProductCatalog(tmp_path/'catalog.db')
    with pytest.raises(ValueError):catalog.ingest({**SOURCE,'rights_verified':False},[product()],now=NOW)
    with pytest.raises(ValueError):catalog.ingest(SOURCE,[product(source_url='javascript:alert(1)')],now=NOW)


def test_loan_costs_are_amortized_and_stress_does_not_invent_fees():
    annuity=loan_cashflow(12000000,12,6,fees=0)
    bullet=loan_cashflow(12000000,12,6,'bullet',fees=0)
    assert bullet['interest']==720000
    assert annuity['interest']<bullet['interest']
    assert annuity['schedule'][-1]['balance']==0
    assert loan_cashflow(12000000,12,0,fees=None)['total_cost'] is None
    assert loan_cashflow(12000000,12,0,fees=0)['first_payment']==1000000


def test_installment_interest_and_unknown_tax():
    assert saving_cashflow(100000,12,12,'installment',0)['interest']==78000
    assert saving_cashflow(100000,12,12,'deposit',0)['interest']==12000
    assert saving_cashflow(100000,12,12,'deposit',None)['maturity'] is None


def test_exclusions_never_relax_and_unknown_conditions_not_ranked():
    result=compare_scenario({'kind':'loan','profile':{'amount':1000000,'months':12},'offers':[
      {'name':'wrong','terms':{'annual_rate':1,'max_amount':100}},
      {'name':'missing fees','terms':{'annual_rate':1}},
      {'name':'unmet','terms':{'annual_rate':2,'fees':0,'conditions':['salary']}},
      {'name':'eligible assumption','terms':{'annual_rate':3,'fees':0}}]})
    assert result['best']=='eligible assumption'
    assert result['excluded']==[{'name':'wrong','reason':'금액 조건 불일치'}]
    assert result['monthly_remaining'] is None


@pytest.mark.parametrize('state',['none','existing','unknown'])
def test_insurance_needs_without_document_or_fake_winner(state):
    result=compare_scenario({'kind':'insurance','profile':{'insurance_state':state,'insurance_kind':'driver'}})
    assert result['insurance_state']==state and result['best'] is None
    assert '자가용' in result['questions'][0]


def test_saved_plans_are_encrypted_account_bound_and_deleteable(tmp_path):
    vault=InsuranceWorkspace(tmp_path,'alice')
    with pytest.raises(InsuranceError):vault.finance_plan()
    vault.unlock('a-strong-password-123')
    payload={'kind':'loan','profile':{'amount':1200000,'months':12},'offers':[{'name':'private-offer-name','terms':{'annual_rate':0,'fees':0}}]}
    saved=vault.finance_plan(operation='save',scenario=payload)['plans'][0]
    assert b'private-offer-name' not in vault.path.read_bytes()
    vault.lock();vault.unlock('a-strong-password-123')
    assert vault.finance_plan()['plans'][0]['result']['best']=='private-offer-name'
    other=InsuranceWorkspace(tmp_path,'bob');other.unlock('b-strong-password-123')
    assert other.finance_plan()['plans']==[]
    assert vault.finance_plan(operation='delete',plan_id=saved['id'])['plans']==[]
    vault.lock();other.lock()


def test_followup_keeps_insurance_context_without_external_call():
    answer=product_question_answer('그럼 어떤 걸 확인해요?', [{'role':'user','content':'보험이 없어요 운전자 보험부터 알고 싶어요'}])
    assert '증권 업로드 없이' in answer and '변호사' in answer
    assert '0건' in answer


@pytest.mark.parametrize('amount',[float('nan'),float('inf'),-1,True])
def test_reject_invalid_scenario_amounts(amount):
    with pytest.raises(ValueError):compare_scenario({'kind':'loan','profile':{'amount':amount,'months':12}})


def test_gateway_auth_intent_and_no_private_error_echo(tmp_path):
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from web_platform.gateway import create_gateway_app
    token='synthetic-finance-products-v3923-token'
    auth={'Authorization':'Bearer '+token};confirmed={**auth,'X-NoahAI-Intent':'confirmed'}
    services=SimpleNamespace(account='synthetic',runtime_snapshot=lambda:{},product_intelligence=lambda payload=None: {'products':[]} if payload is None else compare_scenario(payload))
    with TestClient(create_gateway_app(token=token,application_services=services)) as client:
        route='/api/v1/life-finance/product-intelligence'
        assert client.get(route).status_code==401
        assert client.post(route,headers=auth,json={}).status_code==428
        assert client.get(route,headers={**auth,'Origin':'https://outside.invalid'}).status_code==403
        assert client.get(route,headers=auth).headers['cache-control']=='no-store'
        response=client.post(route,headers=confirmed,json={'kind':'loan','profile':{'amount':'PRIVATE-BAD-INPUT','months':12}})
        assert response.status_code==400 and 'PRIVATE-BAD-INPUT' not in response.text
        response=client.post(route,headers=confirmed,json={'kind':'loan','profile':{'amount':1200000,'months':12},'offers':[{'name':'synthetic','terms':{'annual_rate':0,'fees':0}}]})
        assert response.status_code==200 and response.json()['best']=='synthetic'
        assert response.headers['cache-control']=='no-store'


def test_refinance_counts_old_exit_and_new_costs_once():
    result=compare_scenario({'kind':'loan','profile':{'amount':1000000,'months':12,'method':'bullet','existing_rate':6,'existing_exit_fee':10000},'offers':[{'name':'new','terms':{'annual_rate':3,'fees':5000}}]})
    assert result['candidates'][0]['refinance']['estimated_saving']==15000
