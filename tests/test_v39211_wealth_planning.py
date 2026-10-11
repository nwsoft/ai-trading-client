from copy import deepcopy
from datetime import date
import json
import time
import os
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from trading.wealth_planning import preview, tax_review
from trading.insurance_workspace import InsuranceWorkspace, InsuranceError
from web_platform.gateway import create_gateway_app

TODAY=date(2026,10,11)
def sample():
    return {'name':'synthetic private plan','as_of':'2026-10-11','income':'4000000','expenses':'2000000','annual_irregular':'1200000','emergency_months':'3',
            'assets':[{'name':'cash','amount':'20000000','currency':'KRW','kind':'cash','mode':'real','as_of':'2026-10-11','confirmed':True}],
            'debts':[{'name':'loan','principal':'10000000','annual_rate':'6','payment':'300000','early_fee':'0','as_of':'2026-10-11'}],
            'bills':[{'name':'subscription','current':'50000','target':'20000','change_cost':'60000','confirmed':True}],
            'goals':[{'name':'home','target':'20000000','months':'12','opening':'10000000','monthly':'1000000','annual_rate':'0','tax_rate':'15.4','fees':'0','inflation':'0'}],
            'tax':{'income_kind':'salary_only','annual_income':'50000000','pension':'6000000','irp':'3000000','remaining_tax':'1000000'}}


def test_budget_cash_no_double_count_and_no_expected_saving_allocation():
    r=preview(sample(),today=TODAY);b=r['budget']
    assert b['current_surplus']==1600000
    assert b['projected_surplus']==1630000
    assert b['emergency_target']==7200000
    assert b['allocatable_cash']==12740000
    assert b['remaining_monthly']==600000
    assert r['bills'][0]['break_even_months']==2
    assert r['recorded_net_worth_by_currency']['KRW']['partial_net']==10000000
    assert r['goals'][0]['scenarios'][1]['after_tax']==22000000
    assert r['goals'][0]['scenarios'][1]['gap']==-2000000
    assert r['tax']['pension_credit_cap']==1000000
    p=sample();p['goals'][0]['monthly']='1610000'
    assert preview(p,today=TODAY)['status']=='allocation_conflict'


def test_currency_paper_stale_and_deposit_not_reused_as_cash():
    p=sample();a=p['assets'][0]
    p['assets'] += [{**a,'name':'usd','currency':'USD','amount':'100'}, {**a,'name':'paper','mode':'paper'},
                    {**a,'name':'old','as_of':'2026-01-01'}, {**a,'name':'unconfirmed','confirmed':False}, {**a,'name':'deposit','kind':'deposit'}]
    r=preview(p,today=TODAY)
    assert r['budget']['confirmed_cash']==20000000
    assert r['recorded_net_worth_by_currency']['USD']['partial_net']==100
    assert r['recorded_net_worth_by_currency']['KRW']['recorded_assets']==40000000
    assert len(r['omitted_assets'])==3


@pytest.mark.parametrize('field,value',[('income',''),('income',None),('income',True),('income','NaN'),('income','Infinity'),('income','-1'),('income','1e30'),('emergency_months','3.5'),('emergency_months','25'),('as_of','2026-12-01')])
def test_invalid_budget_never_becomes_zero(field,value):
    p=sample();p[field]=value
    with pytest.raises(ValueError): preview(p,today=TODAY)


@pytest.mark.parametrize('key',['assets','debts','bills','goals'])
def test_duplicate_and_bounded_rows(key):
    p=sample();p[key]*=2
    with pytest.raises(ValueError,match='duplicate'):preview(p,today=TODAY)
    p[key]=p[key]*20
    with pytest.raises(ValueError,match='limit'):preview(p,today=TODAY)


def test_tax_capacity_income_kind_unknown_and_expired_rules():
    raw=sample()['tax'];raw['annual_income']='46000000';raw['remaining_tax']='9000000'
    assert tax_review(raw,TODAY)['pension_credit_cap']==1485000
    raw['income_kind']='comprehensive'
    assert tax_review(raw,TODAY)['pension_credit_cap']==1188000
    raw['remaining_tax']=''
    assert tax_review(raw,TODAY)['pension_credit_cap'] is None
    assert tax_review({},TODAY)['pension_credit_cap'] is None
    assert tax_review(raw,date(2026,11,11))['status']=='rules_reconfirmation_required'
    assert tax_review({'year':'2027'},TODAY)['status']=='rules_reconfirmation_required'
    assert tax_review({'year':''},TODAY)['status']=='conditions_required'


def test_unknown_cost_tax_inflation_do_not_create_after_tax_claim():
    for key in ['tax_rate','fees']:
        p=sample();p['goals'][0][key]=''
        assert all(r['after_tax'] is None for r in preview(p,today=TODAY)['goals'][0]['scenarios'])
    p=sample();p['goals'][0]['inflation']=''
    assert preview(p,today=TODAY)['goals'][0]['scenarios'][0]['today_value'] is None
    p['bills'][0]['change_cost']=''
    r=preview(p,today=TODAY)
    assert r['budget']['terms_checked_saving']==0 and r['bills'][0]['break_even_months'] is None


def test_loss_and_expenses_boundary_and_impossible_cash():
    p=sample();p['goals'][0]['annual_rate']='-50';r=preview(p,today=TODAY)
    assert r['goals'][0]['scenarios'][1]['after_tax']<r['goals'][0]['principal']
    p['bills'][0]['current']='2000001'
    with pytest.raises(ValueError,match='exceed'):preview(p,today=TODAY)
    p=sample();p['assets']=[]
    assert preview(p,today=TODAY)['status']=='allocation_conflict'


@pytest.fixture
def vault(tmp_path):
    v=InsuranceWorkspace(tmp_path,'wealth-synthetic');yield v;v.lock()


def test_preview_never_creates_private_store(vault):
    r=vault.dispatch('wealth_plan',{'operation':'preview','input':sample()})
    assert r['version']=='wealth-plan-1'
    assert not vault.directory.exists()
    with pytest.raises(InsuranceError,match='locked'):vault.dispatch('wealth_plan',{'operation':'list'})


def test_encrypted_lifecycle_revision_actual_history_and_lock(vault):
    vault.unlock('synthetic-password-wealth')
    with pytest.raises(InsuranceError):vault.dispatch('wealth_plan',{'operation':'save','input':sample(),'confirmed':False})
    p=vault.dispatch('wealth_plan',{'operation':'save','input':sample(),'confirmed':True})['plans'][0]
    assert b'synthetic private plan' not in vault.path.read_bytes()
    if os.name != 'nt':
        assert vault.path.stat().st_mode & 0o077==0
    assert vault.dispatch('wealth_plan',{'operation':'list'})['remaining_seconds']<=900
    with pytest.raises(InsuranceError):vault.dispatch('wealth_plan',{'operation':'save','input':sample(),'id':p['id'],'revision':True,'confirmed':True})
    r=vault.dispatch('wealth_plan',{'operation':'actual','id':p['id'],'revision':1,'confirmed':True,'month':'2026-10','actual':{'income':'4000000','expenses':'1900000','debt_payment':'300000','saving':'1000000','goal_balances':{'home':'11000000'}}})['plans'][0]
    assert r['actuals']['2026-10']['remaining']==800000
    assert r['actuals']['2026-10']['goal_progress']['home']['gap']==9000000
    assert r['actuals']['2026-10']['planned_surplus']==1600000
    with pytest.raises(InsuranceError):vault.dispatch('wealth_plan',{'operation':'delete','id':p['id'],'revision':1,'confirmed':True})
    vault.lock();vault.unlock('synthetic-password-wealth')
    assert vault.dispatch('wealth_plan',{'operation':'list'})['plans'][0]['revision']==2
    vault.dispatch('wealth_plan',{'operation':'delete','id':p['id'],'revision':2,'confirmed':True})
    assert vault.dispatch('wealth_plan',{'operation':'list'})['plans']==[]
    vault._expires_at=time.monotonic()-1
    with pytest.raises(InsuranceError,match='locked'):vault.dispatch('wealth_plan',{'operation':'list'})


def test_account_isolation_and_conflict_on_other_writer(vault):
    vault.unlock('synthetic-password-wealth');other=InsuranceWorkspace(vault.directory.parents[1],'wealth-synthetic')
    other.unlock('synthetic-password-wealth')
    try:
        vault.dispatch('wealth_plan',{'operation':'save','input':sample(),'confirmed':True})
        with pytest.raises(InsuranceError,match='changed'):other.dispatch('wealth_plan',{'operation':'save','input':sample(),'confirmed':True})
        isolated=InsuranceWorkspace(vault.directory.parents[1],'other-wealth-user')
        assert isolated.path!=vault.path and isolated.snapshot()['state']=='locked'
    finally:other.lock()


def test_gateway_auth_origin_private_error_and_no_cache(vault):
    services=SimpleNamespace(insurance_workspace=lambda:vault,runtime_snapshot=lambda:{})
    route='/api/v1/life-finance/insurance';headers={'Authorization':'Bearer synthetic-gateway-token-wealth-39211','X-NoahAI-Intent':'confirmed'}
    with TestClient(create_gateway_app(token='synthetic-gateway-token-wealth-39211',application_services=services)) as c:
        body={'action':'wealth_plan','payload':{'operation':'preview','input':sample()}}
        assert c.post(route,json=body).status_code==401
        assert c.post(route,json=body,headers={'Authorization':headers['Authorization']}).status_code==428
        assert c.post(route,json=body,headers={**headers,'Origin':'https://evil.invalid'}).status_code==403
        r=c.post(route,json=body,headers=headers)
        assert r.status_code==200 and r.headers['cache-control']=='no-store'
        body['payload']['input']['income']='PRIVATE-INVALID-INCOME'
        r=c.post(route,json=body,headers=headers)
        assert r.status_code==400 and 'PRIVATE-INVALID-INCOME' not in r.text and 'synthetic private plan' not in r.text
        assert not vault.directory.exists()
