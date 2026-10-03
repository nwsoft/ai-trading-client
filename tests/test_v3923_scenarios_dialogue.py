from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from trading.finance_scenarios import loan_projection, saving_projection
from trading.finance_product_intelligence import compare_scenario
from trading.finance_product_dialogue import revise_scenario
from trading.stock_analysis_service import StockAnalysisService


def test_grace_principal_schedule_and_rounding():
    r=loan_projection(1200000,12,12,'principal',0,{'grace_months':2,'rounding':'won'})
    assert [x['principal_paid'] for x in r['schedule'][:3]]==[0,0,120000]
    assert sum(x['principal_paid'] for x in r['schedule'])==1200000
    assert r['schedule'][-1]['balance']==0
    assert r['first_payment']==12000


def test_actual_days_handles_leap_february_and_original_day_anchor():
    r=loan_projection(1000000,2,36.5,'bullet',0,{'start_date':'2024-01-31','day_count':'actual365'})
    assert [x['date'] for x in r['schedule']]==['2024-02-29','2024-03-31']
    assert r['interest']==60000 # 29 + 31 days, 1000 per day


def test_early_repayment_cost_unknown_blocks_total_cost_and_reduces_interest():
    base=loan_projection(1200000,12,12,'bullet',0,{})
    r=loan_projection(1200000,12,12,'bullet',0,{'early_month':6,'early_amount':600000})
    assert r['interest']==108000 and r['interest']<base['interest']
    assert r['total_cost'] is None
    r=loan_projection(1200000,12,12,'bullet',0,{'early_month':6,'early_amount':600000,'early_fee':10000})
    assert r['total_cost']==118000


@pytest.mark.parametrize('profile',[{'grace_months':12},{'day_count':'actual365'},{'early_month':3},{'early_amount':50000},{'rounding':'invented'}])
def test_invalid_advanced_loan_conditions_not_silently_ignored(profile):
    with pytest.raises(ValueError):loan_projection(1200000,12,5,'annuity',0,profile)


def test_compound_savings_goal_and_ladder():
    r=saving_projection(1000000,24,10,'deposit',0,{'compounding':'annual','target_amount':2420000,'ladder':'true'})
    assert r['maturity']==1210000
    assert r['required_contribution']==2000000
    assert sum(p['principal'] for p in r['ladder'])==pytest.approx(1000000)
    assert [p['months'] for p in r['ladder']]==[8,16,24]


def test_installment_timing_and_unknown_early_rate():
    a=saving_projection(100000,12,12,'installment',0,{'deposit_timing':'beginning'})
    b=saving_projection(100000,12,12,'installment',0,{'deposit_timing':'end','withdraw_month':6})
    assert a['interest']==78000 and b['interest']==66000
    assert b['early_withdrawal']['after_tax'] is None


def test_dialogue_changes_actual_scenario_and_returns_recomputed_delta():
    scenario={'kind':'loan','profile':{'amount':'1200000','months':'12'},'offers':[{'name':'known','terms':{'annual_rate':6,'fees':0}}]}
    before=deepcopy(scenario)
    r=revise_scenario(scenario,'기간을 24개월로 바꾸면?')
    assert r['scenario']['profile']['months']=='24'
    assert r['deltas'][0]['difference']>0
    assert scenario==before and r['provider_called'] is False and r['saved'] is False


def test_dialogue_budget_and_no_invented_product():
    r=revise_scenario({'kind':'insurance','profile':{},'offers':[]},'보험이 없어요. 운전자 보험 예산은 2만원')
    assert float(r['scenario']['profile']['insurance_budget'])==20000
    assert r['result']['insurance_state']=='none'
    assert all(not p['candidate_ids'] for p in r['result']['design_options'])


def test_insurance_three_designs_require_verified_personal_quote_and_budget():
    def quote(name,premium,confirmed):return {'name':name,'terms':{'monthly_premium':premium,'coverage':'벌금 약관 참조','exclusions':'제외 원문 참조','renewal':'갱신 계약','confirmed':confirmed,'benefits':{'벌금':'확인한 약관 한도'}}}
    r=compare_scenario({'kind':'insurance','profile':{'insurance_state':'none','insurance_kind':'driver','insurance_budget':20000,'required_coverages':'벌금'},'offers':[quote('confirmed',18000,True),quote('unverified',1000,False),quote('overbudget',30000,True)]})
    assert r['best'] is None
    assert all(p['candidate_ids']==['quote-0'] for p in r['design_options'])
    assert r['change_scenarios'][0]['first_year_cash_difference'] is None


def test_stock_diagnostic_preserves_paper_and_has_no_broker_calls():
    s=StockAnalysisService.__new__(StockAnalysisService)
    s._last_profitability_context={'mode':'paper','policy':{'enabled':True},'report':{}}
    s._get_recent_paper_trade_samples=lambda **kw:[{'return_fraction':.01}]
    s._get_recent_trade_samples=lambda **kw:pytest.fail('no broker call')
    r=s.profitability_diagnostic()
    assert r['sample_scope']=='paper_closed_trades' and r['order_permission_granted'] is False
    s.broker_name='kiwoom';s.recorder=SimpleNamespace(get_recent_trades=lambda **kw:(_ for _ in ()).throw(OSError()))
    assert s._profitability_samples('live')[0]['performance_evidence_ready'] is False


def test_feed_failure_retains_last_good_and_rollback_pauses(tmp_path):
    import json,time
    from trading.finance_product_intelligence import ProductCatalog
    now=datetime.now(timezone.utc)
    source={'id':'test','url':'https://example.org','rights_verified':True,'rights_reference':'test fixture'}
    product={'id':'one','name':'v1','provider':'fixture','kind':'loan','version':'1','source_url':'https://example.org/a','verified_at':'2020-01-01T00:00:00Z','valid_until':'2090-01-01T00:00:00Z','status':'active','terms':{'annual_rate':3}}
    feed=tmp_path/'private-feed-path.json';feed.write_text(json.dumps({'source':source,'products':[product]}))
    catalog=ProductCatalog(tmp_path/'catalog.db');first=catalog.register_feed('test',feed)
    feed.write_text('{invalid')
    snapshot=catalog.refresh_feeds(now_epoch=time.time()+1000)
    assert snapshot['feeds'][0]['status']=='refresh_failed'
    assert snapshot['products'][0]['name']=='v1'
    assert 'private-feed-path' not in json.dumps(snapshot)
    feed.write_text(json.dumps({'source':source,'products':[{**product,'name':'v2','version':'2'}]}))
    catalog.refresh_feeds(now_epoch=time.time()+5000)
    assert catalog.snapshot()['products'][0]['name']=='v2'
    catalog.rollback(first['revision'])
    assert catalog.snapshot()['products'][0]['name']=='v1'
    assert catalog.refresh_feeds(force=True,now_epoch=time.time()+10000)['feeds'][0]['status']=='paused_after_rollback'
    assert catalog.snapshot()['products'][0]['name']=='v1'


@pytest.mark.parametrize('kind',['loan','savings','insurance'])
def test_expired_personal_quotes_are_excluded(kind):
    result=compare_scenario({'kind':kind,'profile':{'amount':10000,'months':12},'offers':[{'name':'expired','valid_until':'2020-01-01T00:00:00Z','terms':{'annual_rate':2,'fees':0,'tax_rate':0,'monthly_premium':1000}}]})
    assert result['best'] is None and result['candidates']==[]
    assert result['excluded'][0]['reason']=='견적 유효기간 만료'


def test_advanced_refinance_requires_existing_amortization_terms():
    result=compare_scenario({'kind':'loan','profile':{'amount':1000000,'months':12,'grace_months':3,'existing_rate':8,'existing_exit_fee':0},'offers':[{'name':'new','terms':{'annual_rate':3,'fees':0}}]})
    assert result['candidates'][0]['refinance']['estimated_saving'] is None


def test_dialogue_explanation_preserves_unknown_cost_and_source():
    result=revise_scenario({'kind':'loan','profile':{'amount':1000000,'months':12},'offers':[{'name':'quote','source_url':'기관 견적 1','terms':{'annual_rate':3}}]},'왜 이 조건인지 설명해 줘')
    assert '총비용 미확인' in result['answer'] and '기관 견적 1' in result['answer']
    assert result['changes']==[] and result['result']['best'] is None
    assert result['evidence'][0]['source_kind']=='user_quote'


def test_invalid_insurance_terms_fail_as_validation_error():
    with pytest.raises(ValueError):compare_scenario({'kind':'insurance','offers':[{'terms':['invalid']} ]})


def test_ambiguous_or_negative_dialogue_never_changes_to_unintended_positive():
    scenario={'kind':'loan','profile':{'amount':1000000,'months':12}}
    result=revise_scenario(scenario,'100만원에서 200만원으로 변경')
    assert result['scenario']==scenario and '여러 개' in result['answer']
    with pytest.raises(ValueError):revise_scenario(scenario,'금액을 -100만원으로')


def test_duplicate_quote_names_do_not_mix_before_after_costs():
    scenario={'kind':'loan','profile':{'amount':1000000,'months':12},'offers':[{'name':'동일 이름','terms':{'annual_rate':2,'fees':0}},{'name':'동일 이름','terms':{'annual_rate':8,'fees':0}}]}
    before=compare_scenario(scenario)
    result=revise_scenario(scenario,'기간을 24개월로')
    assert len(result['deltas'])==2
    assert [r['before'] for r in result['deltas']]==[r['estimate']['total_cost'] for r in before['candidates']]
