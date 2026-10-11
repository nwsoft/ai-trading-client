"""Financial companion boundaries exercised with real local stores/calculators."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from threading import RLock
import hashlib
import json
import sqlite3
import time
import pytest
from fastapi.testclient import TestClient
from web_platform import companion as c
from web_platform.application_services import ApplicationServices
from web_platform.gateway import create_gateway_app
from trading.insurance_workspace import InsuranceWorkspace
from trading.finance_product_dialogue import revise_scenario

NOW=datetime(2026,10,10,12,tzinfo=timezone.utc)
TOKEN='synthetic-companion-test-token-long-enough'
HEADERS={'Authorization':'Bearer '+TOKEN,'X-NoahAI-Intent':'confirmed'}

def hashes(path):
    return {str(p.relative_to(path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob('*') if p.is_file()}

def service(directory,bridge=None):
    # No production initializer/configuration/network dependencies.
    obj=ApplicationServices.__new__(ApplicationServices)
    obj.account='synthetic-user';obj.data_dir=directory;obj._lock=RLock()
    obj._insurance_workspace=None;obj._latest_account_snapshot=None
    obj.runtime_bridge=bridge or SimpleNamespace(operation_overview_snapshot=lambda **kw:{})
    return obj

def briefing(**kw):
    defaults=dict(operations={},account={},finance=None,catalog={},market={},plans={},now=NOW)
    return c.build_briefing(**{**defaults,**kw})

@pytest.mark.parametrize('stamp,expiry,status',[
    (None,None,'unknown_time'),('2026-10-10T12:00:00Z',None,'recent'),
    ('2026-10-10T11:00:00Z',None,'stale'),('2026-10-11T12:00:00Z',None,'future_time'),
    ('2026-10-10T12:00:00Z','2026-10-10T11:00:00Z','expired'),
    ('2026-10-10T12:00:00',None,'unknown_time'),(None,'bad','unknown_expiry'),
    (False,None,'unknown_time'),(float('inf'),None,'unknown_time')])
def test_original_evidence_time_never_replaced(stamp,expiry,status):
    assert c.evidence('fixture',stamp,valid_until=expiry,now=NOW)['freshness']==status


def test_readonly_empty_directory_never_created(tmp_path):
    directory=tmp_path/'not-created'
    s=service(directory)
    r=s.companion_briefing()
    assert not directory.exists()
    assert r['catalog_coverage']['reference_count']==7
    assert r['catalog_coverage']['providers']==4
    assert r['read_only'] and not r['provider_called'] and not r['orders_submitted']
    text=json.dumps(r,ensure_ascii=False)
    assert '실제 수입·지출 0원이 아닙니다' in text
    assert r['vault_state']=='locked'


def test_catalog_tombstone_readonly_and_market_account_provenance(tmp_path):
    db=sqlite3.connect(tmp_path/'finance_product_catalog.sqlite3')
    db.execute('create table products(payload text)')
    db.execute('create table insurance_references(payload text)')
    db.execute('insert into insurance_references values (?)',(json.dumps({'id':'removed','provider':'fixture','status':'withdrawn','review_due':'2090-01-01T00:00:00Z'}),))
    db.commit();db.close()
    directory=tmp_path/'financial_intelligence';directory.mkdir()
    db=sqlite3.connect(directory/'web_ui.sqlite3')
    db.execute('create table fi_records(record_type text,payload_json text,as_of text,source text)')
    for name,symbols in [('exact',['BTCUSDT']),('title BTCUSDT',[]),('other',['BTC'])]:
        db.execute('insert into fi_records values (?,?,?,?)',('news',json.dumps({'title':name,'symbols':symbols,'secret':'NOT_PROJECTED'}),'2026-10-09T10:00:00Z','stored-fixture'))
    db.commit();db.close()
    s=service(tmp_path)
    s._latest_account_snapshot={'sources':{'okx':{'status':'success','captured_at':'2026-10-08T00:00:00Z','positions':[{'symbol':'BTC/USDT','secret':'NOT_PROJECTED'}]},'evil':{'status':'success','positions':[{'symbol':'BTC'}]}}}
    before=hashes(tmp_path);r=s.companion_briefing()
    assert hashes(tmp_path)==before
    catalog=c.read_catalog(tmp_path,NOW)
    assert len(catalog['reference_products'])==1 and catalog['reference_products'][0]['evidence_status']=='withdrawn'
    assert [r['title'] for r in r['holding_news']]==['exact']
    proof=r['holding_news'][0]['holding_evidence'][0]
    assert proof['freshness']=='stale' and proof['data_class']=='live_account_cache'
    assert 'NOT_PROJECTED' not in json.dumps(r)
    assert r['holding_news'][0]['evidence']['observed_at'].startswith('2026-10-09')


def test_corrupt_sections_are_unavailable_not_zero_and_other_sections_survive(tmp_path):
    (tmp_path/'finance_product_catalog.sqlite3').write_bytes(b'bad sqlite')
    (tmp_path/'life_finance_transactions.json').write_text('{')
    s=service(tmp_path,SimpleNamespace(operation_overview_snapshot=lambda **kw:{'okx':{'mode':'paper','entry_health':{'label':'목록 조회 실패','action':'공개 연결 확인','observed_at':NOW.timestamp()},'pre_entry':{'confidence':.65,'required_confidence':.7}}}))
    r=s.companion_briefing()
    assert set(r['unavailable_sections'])=={'catalog','finance'}
    assert r['catalog_coverage']['reference_count'] is None
    assert r['catalog_coverage']['current_products'] is None
    answer=s.companion_query(question='okx 왜 거래가 없지?')
    assert '0.65 / 필요 0.7' in answer['answer'] and 'PAPER' in answer['answer']
    assert 'bad sqlite' not in json.dumps(answer)


@pytest.mark.parametrize('question,status,kind',[
    ('보험이 없는데 보험 예산은 2만원','review','insurance'),
    ('대출 120만원 기간 12개월','review','loan'),
    ('월 30만원 적금 24개월','review','savings'),
    ('월 부담을 줄여줘','clarification',None),
    ('보험과 대출을 비교해줘','clarification',None),
    ('은행 송금해줘','briefing',None),
    ('손절 2%로 전략 비교해줘','review',None)])
def test_query_proposes_existing_work_without_execution(question,status,kind,tmp_path):
    s=service(tmp_path);before=hashes(tmp_path)
    r=s.companion_query(question=question)
    assert r['status']==status and not r['provider_called'] and not r['saved'] and not r['orders_submitted']
    assert hashes(tmp_path)==before
    if kind:assert r['actions'][0]['kind']==kind
    if '손절' in question:assert [a['id'] for a in r['actions']]==['strategy','strategy_consultation']


def test_discovery_profile_handoff_existing_recalculation_and_missing_cost(tmp_path):
    r=service(tmp_path).companion_query(question='대출 120만원 기간 12개월')
    profile=r['actions'][0]['profile']
    assert float(profile['amount'])==1200000 and int(profile['months'])==12
    scenario={'kind':'loan','profile':profile,'offers':[{'name':'synthetic','terms':{'annual_rate':6,'fees':0}}]}
    original=deepcopy(scenario);changed=revise_scenario(scenario,'기간 24개월로')
    assert changed['scenario']['profile']['months']=='24' and changed['deltas'][0]['difference']>0
    assert scenario==original
    scenario['offers'][0]['terms'].pop('fees')
    changed=revise_scenario(scenario,'기간 24개월로')
    assert changed['result']['best'] is None


def test_vault_peek_neither_unlocks_nor_extends_timeout(tmp_path):
    vault=InsuranceWorkspace(tmp_path,'synthetic')
    assert vault.peek_finance_reviews({})=={'state':'locked','reviews':[]}
    vault.unlock('synthetic-password-only')
    try:
        vault._data['finance_plans']={'p':{'id':'p','reminder_date':'2026-10-01','reminder_kind':'renewal'}}
        expires,last=vault._expires_at,vault._last_use
        before=hashes(tmp_path)
        result=vault.peek_finance_reviews({},at=NOW)
        assert result['state']=='unlocked' and result['reviews'][0]['review_due']
        assert (vault._expires_at,vault._last_use)==(expires,last)
        assert hashes(tmp_path)==before
        vault._expires_at=time.monotonic()-1
        assert vault.peek_finance_reviews({},at=NOW)=={'state':'locked','reviews':[]}
    finally:vault.lock()


def test_registered_month_review_excludes_transfers_future_and_does_not_modify(tmp_path):
    (tmp_path/'life_finance_transactions.json').write_text(json.dumps([
        {'amount':100000,'type':'수입','date':'2026-10-01'},
        {'amount':10000,'type':'지출','date':'2026-10-02'},
        {'amount':50000,'type':'지출','date':'2026-10-11'}]))
    (tmp_path/'life_finance_transfers.json').write_text(json.dumps([{'amount':500000,'type':'내 계좌 이체','date':'2026-10-01'}]))
    before=hashes(tmp_path);r=c.local_finance(tmp_path,NOW)
    assert r['recorded_difference']==90000 and r['transfer_count']==1 and r['future_count']==1
    assert hashes(tmp_path)==before


def allocation(**kw):
    return {'currency':'KRW','rows':[{'symbol':'A','before':80,'after':50},{'symbol':'B','before':20,'after':50}],**kw}

def test_allocation_cost_and_cash_deltas_and_no_unknown_zero():
    r=c.allocation_preview(allocation(total_value=1000000,fee_bps=10))
    assert r['turnover_percent']==60 and r['estimated_cost']==600
    assert [x['delta_value'] for x in r['rows']]==[-300000,300000]
    assert r['before_hhi']==pytest.approx(.68) and r['after_hhi']==.5
    r=c.allocation_preview(allocation());assert r['estimated_cost'] is None
    assert all(x['delta_value'] is None for x in r['rows']) and not r['orders_submitted']

@pytest.mark.parametrize('change',[
    {'currency':'KRW+USD'}, {'total_value':float('nan')},{'fee_bps':float('inf')},{'total_value':True},
    {'rows':[{'symbol':'A','before':50,'after':100}]},
    {'rows':[{'symbol':'A','before':50,'after':50},{'symbol':'a','before':50,'after':50}]},
    {'rows':[{'symbol':'A','before':True,'after':100}]},
    {'rows':[{'symbol':'A','before':100,'after':100,'currency':'USD'}]}])
def test_invalid_allocation_rejected(change):
    with pytest.raises(ValueError):c.allocation_preview(allocation(**change))


def versions():
    basis=c.replay_comparison_basis([[1,2,3]],{'15m':[[1,2,3]]},source='okx',symbol='BTC/USDT',interval='15m',horizon=3,entry_start_ms=1,costs={'fee_rate':.001})
    return [{'scope':'unified','strategy_key':'s','version_id':str(i),'mode':'historical_replay','recorded_at':NOW.isoformat(),
             'metrics':{'comparison_basis':deepcopy(basis),'net_pnl_percent':i,'max_drawdown_percent':None,'decisions':i+3}} for i in (1,2)]

def ref(v):return {k:v[k] for k in ('scope','strategy_key','version_id')}

def test_strategy_compare_same_actual_inputs_and_unknown_metrics():
    rows=versions();r=c.compare_experiments(rows,ref(rows[0]),ref(rows[1]))
    assert r['comparable'] and r['metrics'][0]['delta']==1
    assert r['evidence']['observed_at']==NOW.isoformat()
    assert r['metrics'][1]['before'] is None and r['metrics'][1]['delta'] is None
    assert not r['auto_approved'] and not r['saved']

@pytest.mark.parametrize('change',['missing','hash','cost','mode'])
def test_strategy_compare_rejects_legacy_or_different_inputs(change):
    rows=versions();metric=rows[1]['metrics']
    if change=='missing':metric.pop('comparison_basis')
    if change=='hash':metric['comparison_basis']['input_sha256']='0'*64
    if change=='cost':metric['comparison_basis']['costs']['fee_rate']=.002
    if change=='mode':rows[1]['mode']='paper'
    r=c.compare_experiments(rows,ref(rows[0]),ref(rows[1]))
    assert not r['comparable'] and not r['metrics']


def test_readonly_strategy_version_projection_and_account_isolation(tmp_path):
    directory=tmp_path/'custom_strategies';directory.mkdir()
    rows=versions()
    (directory/'unified_private.json').write_text(json.dumps({'strategies':{'s':[
        {'version_id':v['version_id'],'name':'variant','rules':{'private':'NOT_PROJECTED'},'execution_validation':{'mode':v['mode'],'recorded_at':v['recorded_at'],'metrics':v['metrics']}} for v in rows]}}))
    before=hashes(tmp_path);s=service(tmp_path)
    assert len(s.companion_experiments()['versions'])==2
    assert 'NOT_PROJECTED' not in json.dumps(s.companion_experiments())
    assert s.companion_experiments(ref(rows[0]),ref(rows[1]))['comparable']
    assert hashes(tmp_path)==before
    other=service(tmp_path/'other-user');assert other.companion_experiments()['versions']==[]
    other.account='local'
    for call in (other.companion_briefing,other.companion_experiments,lambda:other.companion_allocation(allocation())):
        with pytest.raises(ValueError,match='login_required'):call()


def test_gateway_auth_intent_strict_contract_no_private_echo(tmp_path):
    s=service(tmp_path);s.runtime_snapshot=lambda:{}
    with TestClient(create_gateway_app(token=TOKEN,application_services=s)) as client:
        root='/api/v1/companion'
        assert client.get(root+'/briefing').status_code==401
        assert client.post(root+'/query',headers={'Authorization':'Bearer '+TOKEN},json={'question':'질문'}).status_code==428
        assert client.get(root+'/briefing',headers={**HEADERS,'Origin':'https://external.invalid'}).status_code==403
        assert client.get(root+'/briefing',headers=HEADERS).headers['cache-control']=='no-store'
        assert client.post(root+'/query',headers=HEADERS,json={'question':'보험이 없어요'}).status_code==200
        for body in ({'question':'질문','raw_private':'DO_NOT_ECHO'},{'question':'질문','service':'invalid'}):
            r=client.post(root+'/query',headers=HEADERS,json=body)
            assert r.status_code==422 and 'DO_NOT_ECHO' not in r.text
        body=allocation(total_value=True)
        assert client.post(root+'/allocation',headers=HEADERS,json=body).status_code==422
        assert client.post(root+'/allocation',headers=HEADERS,json=allocation()).status_code==200
        assert client.get(root+'/experiments',headers=HEADERS).json()['versions']==[]
        assert client.post(root+'/experiment-compare',headers=HEADERS,json={'baseline':{'scope':'other','strategy_key':'s','version_id':'1'},'candidate':ref(versions()[1])}).status_code==422


def test_reminders_and_allocation_have_specific_review_paths():
    b=briefing(plans={'state':'unlocked','reviews':[{'plan_id':'p','review_due':True,'reasons':['예약한 재점검일']}]})
    r=c.query('보험 갱신 재확인 항목 알려줘',b,{})
    assert r['status']=='observed' and [x['id'] for x in r['cards']]==['plan:p']
    r=c.query('만기·갱신·재확인 항목 알려줘',briefing(),{})
    assert r['status']=='insufficient_data' and not r['cards']
    r=c.query('보유 자산 배분 조정안을 보고 싶어',b,{})
    assert r['status']=='preview_required' and r['actions'][0]['id']=='allocation'


def test_existing_guide_assistant_reuses_live_diagnostics_without_provider(tmp_path):
    s=service(tmp_path,SimpleNamespace(operation_overview_snapshot=lambda **kw:{'okx':{'mode':'paper','entry_health':{'label':'현재 종목 목록 조회 실패','action':'공개 연결 확인','observed_at':NOW.timestamp()}}}))
    r=s.ask_assistant(question='okx 왜 거래가 없지?',service='blockchain',explanation_level='beginner')
    assert r['source']=='local_companion_evidence' and not r['provider_called']
    assert 'OKX · PAPER' in r['answer'] and '목록 조회 실패' in r['answer']
