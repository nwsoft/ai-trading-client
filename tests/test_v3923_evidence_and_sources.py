from copy import deepcopy
import json
import pytest
from trading.finance_profile_parser import interpret
from trading.finance_product_intelligence import ProductCatalog, product_question_answer
from trading.finance_evidence import search_evidence
from trading.finance_source_connector import refresh_sources

def source():return {'id':'fixture','url':'https://example.org','rights_verified':True,'rights_reference':'synthetic test','api_url':'https://example.org/products','enabled':True,'interval_seconds':900}
def product():return {'id':'one','kind':'savings','name':'합성 예금','provider':'fixture','version':'v1','source_url':'https://example.org/p','verified_at':'2020-01-01T00:00:00Z','valid_until':'2090-01-01T00:00:00Z','status':'active','terms':{'annual_rate':3,'tax_rate':0},'evidence':[{'id':'clause1','text':'중도해지 금리는 별도 조건을 확인한다.','page':3,'clause':'중도해지'}]}

def test_named_multiple_conditions_and_no_overlapping_money():
    profile,changes,missing=interpret({},'목표 금액 200만원, 월소득 300만원, 매달 10만원 기간 24개월','savings')
    assert profile['amount']=='100000.0' and profile['monthly_income']=='3000000.0' and profile['target_amount']=='2000000.0'
    assert profile['months']=='24' and not missing

def test_switch_deposit_to_installment_requires_new_cashflow_amount():
    profile,_,missing=interpret({'amount':'10000000','method':'deposit'},'적금으로 바꾸면?','savings')
    assert profile['amount']=='' and profile['method']=='installment' and missing

def test_negation_does_not_exclude_and_can_restore_condition():
    assert not interpret({},'카드 조건은 제외하지 마','savings')[0].get('declined_conditions')
    assert interpret({'declined_conditions':['카드']},'카드 조건 다시 포함','savings')[0]['declined_conditions']==[]

def test_evidence_search_excludes_expired_and_keeps_original_clause(tmp_path):
    store=ProductCatalog(tmp_path/'p.db');store.ingest(source(),[product()]);catalog=store.snapshot()
    rows=search_evidence(catalog,'중도해지 조건','savings');assert rows[0]['page']==3 and rows[0]['version']=='v1'
    catalog['products'][0]['evidence_status']='stale';assert search_evidence(catalog,'중도해지 조건')==[]
    bad=product();bad['evidence'][0]['source_url']='javascript:alert(1)'
    with pytest.raises(ValueError):store.ingest(source(),[bad])

def test_snapshot_api_refresh_failure_and_rollback_are_bounded(tmp_path):
    (tmp_path/'finance_product_sources.json').write_text(json.dumps([source()]))
    store=ProductCatalog(tmp_path/'catalog.db');calls=[]
    def fetch(config):calls.append(config['id']);return {'source_id':'fixture','products':[product()]}
    first=refresh_sources(store,tmp_path,transport=fetch,clock=1000);revision=first['imports'][0]['revision']
    refresh_sources(store,tmp_path,transport=fetch,clock=1001);assert len(calls)==1
    def fail(config):raise TimeoutError('DO_NOT_EXPOSE_SECRET')
    failed=refresh_sources(store,tmp_path,transport=fail,clock=2000)
    assert failed['products'][0]['name']=='합성 예금' and failed['feeds'][0]['status']=='refresh_failed'
    assert 'SECRET' not in json.dumps(failed)
    store.rollback(revision)
    refresh_sources(store,tmp_path,transport=fetch,clock=9000,force=True);assert len(calls)==1

def test_assistant_uses_current_question_and_prior_numeric_conditions(tmp_path):
    store=ProductCatalog(tmp_path/'catalog.db');store.ingest(source(),[product()])
    answer=product_question_answer('기간을 24개월로 하면?', [{'role':'user','content':'목돈 100만원 12개월 예금 비교해줘'}],catalog=store.snapshot())
    assert '24개월' in answer and '1,060,000.00원' in answer and '합성 예금' in answer

def test_new_topic_does_not_reuse_old_loan_amount():
    answer=product_question_answer('보험이 없는데 운전자보험은?', [{'role':'user','content':'대출 5000만원 24개월'}])
    assert '증권 업로드 없이' in answer and '50000000' not in answer
