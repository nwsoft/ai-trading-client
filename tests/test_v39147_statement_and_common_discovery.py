"""Real local recovery/DB pipeline, synthetic read-only venue responses."""
import base64
import csv
import io
import json
import sqlite3
import time
from decimal import Decimal
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from test_v39143_record_recovery import make
from trading.record_recovery import RecordRecovery
from trading.record_recovery_adapters import RecoveryResolver
from trading.recovery_statement import FIELDS, import_statement, read_statement

VENUES=['binance','okx','bybit','bitget','upbit','bithumb','coinone','kis','kiwoom','shinhan','mirae']
STOCKS={'kis','kiwoom','shinhan','mirae'}


def prepared(tmp_path,venue='okx'):
    r,tid,fill,c,job=make(tmp_path,venue)
    stamp=int(time.time())-1000
    entry=datetime.fromtimestamp(stamp,timezone.utc).isoformat()
    with sqlite3.connect(r.db_path) as db:
        db.execute('UPDATE trade_log SET entry_time=?,exit_time=NULL,exit_order_id=NULL,exit_price=NULL,pnl=NULL,net_pnl=NULL WHERE id=?',(entry,tid))
    currency='KRW' if venue in STOCKS|{'upbit','bithumb','coinone'} else 'USDT'
    rows=[{'execution_id':'entry-fill','order_id':'entry-1','symbol':fill['symbol'],'side':'buy',
           'quantity':'2','price':'100','fee':'0.1','fee_currency':currency,'timestamp':entry,'tax':'0','position_side':'BOTH'},
          {'execution_id':'exit-fill','order_id':'close-discovered','symbol':fill['symbol'],'side':'sell',
           'quantity':'2','price':'95','fee':'0.2','fee_currency':currency,
           'timestamp':datetime.fromtimestamp(stamp+10,timezone.utc).isoformat(),'tax':'0.05' if venue in STOCKS else '0','position_side':'BOTH'}]
    return r,tid,rows,c,job


def payload(venue,rows):
    output=io.StringIO(); writer=csv.DictWriter(output,fieldnames=FIELDS)
    writer.writeheader(); writer.writerows(rows)
    return {'source':venue,'content_base64':base64.b64encode(output.getvalue().encode()).decode(),
            'mapping':{k:k for k in FIELDS},'timezone':'UTC','encoding':'utf-8-sig','delimiter':',',
            'complete_cycles':True,'linear_contract':True,'contract_size':'1'}


def commit(r,p):
    review=import_statement(r,p)
    return import_statement(r,{**p,'reviewed_digest':review['digest'],'confirmed_own_account':True},commit=True)


@pytest.mark.parametrize('venue',VENUES)
def test_offline_statement_missing_order_discovery_and_recovery_all_venues(tmp_path,venue):
    r,tid,rows,c,job=prepared(tmp_path,venue)
    before=r.execute_query('SELECT * FROM trade_log')
    p=payload(venue,rows)
    assert read_statement(p)['ready']
    assert commit(r,p)['stored'] and commit(r,p)['already_imported']
    assert before==r.execute_query('SELECT * FROM trade_log')  # import is not application
    recovery=RecordRecovery(r,RecoveryResolver(r,None,venue),delay=0)
    result=recovery.start(venue,background=False)
    assert result['recovered']==1 and result['remaining']==0,result
    row=r.execute_query('SELECT exit_order_id,net_pnl,pnl_source FROM trade_log')[0]
    assert row[0]=='close-discovered'
    assert row[1]==pytest.approx(-10.35 if venue in STOCKS else -10.3)
    assert row[2]=='statement_isolated_cycle'
    assert not result['auto_started'] and not result['resume_authorized']
    snapshot=r.execute_query('SELECT * FROM trade_log')
    recovery.now=lambda:time.time()+31
    assert recovery.start(venue,background=False)['total']==0
    assert snapshot==r.execute_query('SELECT * FROM trade_log')


@pytest.mark.parametrize('fault',['missing_fee','formula','wrong_side','bad_time','nan','ambiguous_number','duplicate','tax_missing'])
def test_statement_preview_rejects_bad_inputs(tmp_path,fault):
    r,tid,rows,c,job=prepared(tmp_path,'kis')
    if fault=='missing_fee': rows[1]['fee']=''
    if fault=='formula': rows[1]['quantity']='=2'
    if fault=='wrong_side': rows[1]['side']='입고'
    if fault=='bad_time': rows[1]['timestamp']='09/10/2026'
    if fault=='nan': rows[1]['price']='NaN'
    if fault=='ambiguous_number': rows[1]['price']='1,000'
    if fault=='duplicate': rows.append({**rows[1],'price':'96'})
    if fault=='tax_missing': rows[1]['tax']=''
    p=payload('kis',rows); result=read_statement(p)
    assert not result['ready'] and result['error_count']>0
    with pytest.raises(ValueError,match='statement_review_required'): commit(r,p)


def test_review_digest_and_account_attestation_required(tmp_path):
    r,tid,rows,c,job=prepared(tmp_path)
    p=payload('okx',rows);review=import_statement(r,p)
    with pytest.raises(ValueError,match='statement_review_required'):
        import_statement(r,{**p,'reviewed_digest':review['digest']},commit=True)
    with pytest.raises(ValueError,match='statement_review_required'):
        import_statement(r,{**p,'reviewed_digest':review['digest'],'confirmed_own_account':True,'timezone':'Asia/Seoul'},commit=True)


def test_statement_partial_or_mixed_cycle_not_applied(tmp_path):
    r,tid,rows,c,job=prepared(tmp_path)
    rows.insert(1,{**rows[0],'execution_id':'manual','order_id':'manual-entry','timestamp':datetime.fromtimestamp(time.time()-995,timezone.utc).isoformat()})
    commit(r,payload('okx',rows));before=r.execute_query('SELECT * FROM trade_log')
    result=job.start('okx',background=False)
    assert result['remaining']==1 and result['recovered']==0
    assert before==r.execute_query('SELECT * FROM trade_log')


def api_client(venue,rows):
    fills=[{'id':r['execution_id'],'order':r['order_id'],'symbol':'BTC/USDT:USDT','side':r['side'],
            'amount':float(r['quantity']),'price':float(r['price']),
            'fee':{'cost':float(r['fee']),'currency':r['fee_currency']},
            'timestamp':int(datetime.fromisoformat(r['timestamp']).timestamp()*1000)} for r in rows]
    calls=[]
    def fetch(symbol,start,limit,params):
        calls.append(('fills',start,params['until']))
        return [r for r in fills if start<=r['timestamp']<=params['until']][:limit]
    def order(oid,symbol):
        group=[r for r in fills if r['order']==oid];calls.append(('order',oid))
        return {'id':oid,'symbol':symbol,'status':'closed','filled':str(sum((Decimal(str(r['amount'])) for r in group),Decimal(0))),
                'side':group[0]['side'],'info':{'posSide':'net','positionIdx':0,'posMode':'one_way_mode'}}
    ex=SimpleNamespace(apiKey='fake-offline-key',markets={'BTC/USDT:USDT':{'linear':True,'contractSize':1}},
        fetch_positions=lambda symbols:[],fetch_my_trades=fetch,fetch_order=order)
    client=SimpleNamespace(exchange=ex,_normalize_symbol=lambda s:'BTC/USDT:USDT',
                           get_positions_result=lambda:{'status':'success','positions':[]})
    return client,calls,fills


@pytest.mark.parametrize('venue',['okx','bybit','bitget'])
def test_api_discovers_missing_exit_with_complete_cycle(tmp_path,venue):
    r,tid,rows,c,job=prepared(tmp_path,venue)
    client,calls,fills=api_client(venue,rows)
    recovery=RecordRecovery(r,RecoveryResolver(r,client,venue),delay=0,request_budget=1000)
    result=recovery.start(venue,background=False)
    assert result['recovered']==1 and result['remaining']==0,result
    assert r.execute_query('SELECT net_pnl,pnl_source FROM trade_log')[0]==(pytest.approx(-10.3),'api_isolated_cycle')
    assert any(c[0]=='order' for c in calls) and not result['auto_started']


def test_api_resume_pages_after_restart_without_requerying_completed_pages(tmp_path):
    r,tid,rows,c,job=prepared(tmp_path)
    client,calls,fills=api_client('okx',rows)
    recovery=RecordRecovery(r,RecoveryResolver(r,client,'okx'),delay=0,request_budget=2)
    first=recovery.start('okx',background=False)
    assert first['state']=='paused'
    before=list(calls)
    resumed=RecordRecovery(r,RecoveryResolver(r,client,'okx'),delay=0,request_budget=1000)
    result=resumed.start('okx',background=False)
    assert result['recovered']==1 and result['job_id']==first['job_id']
    for call in before: assert calls.count(call)==1


def test_incomplete_statement_does_not_block_available_api_evidence(tmp_path):
    r,tid,rows,c,job=prepared(tmp_path)
    client,calls,fills=api_client('okx',rows)
    commit(r,payload('okx',rows[:1]))
    recovery=RecordRecovery(r,RecoveryResolver(r,client,'okx'),delay=0,request_budget=1000)
    result=recovery.start('okx',background=False)
    assert result['recovered']==1 and result['remaining']==0,result
    assert r.execute_query('SELECT pnl_source FROM trade_log')[0][0]=='api_isolated_cycle'


@pytest.mark.parametrize('fault',['cost','contract','partial_order','position_mode','api_failure'])
def test_api_discovery_fails_closed(tmp_path,fault):
    r,tid,rows,c,job=prepared(tmp_path)
    client,calls,fills=api_client('okx',rows)
    if fault=='cost': fills[1]['fee']['cost']=None
    if fault=='contract': client.exchange.markets['BTC/USDT:USDT']['linear']=False
    if fault in {'partial_order','position_mode'}:
        original=client.exchange.fetch_order
        client.exchange.fetch_order=lambda *args:{**original(*args),**({'filled':99} if fault=='partial_order' else {'info':{}})}
    if fault=='api_failure':
        def fail(*args):raise TimeoutError()
        client.exchange.fetch_my_trades=fail
    before=r.execute_query('SELECT * FROM trade_log')
    recovery=RecordRecovery(r,RecoveryResolver(r,client,'okx'),delay=0,request_budget=1000)
    result=recovery.start('okx',background=False)
    assert result['recovered']==0 and result['remaining']==1
    assert before==r.execute_query('SELECT * FROM trade_log')


def test_gateway_preview_import_recover_without_api_or_runtime_start(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from web_platform.gateway import create_gateway_app
    from web_platform.runtime_bridge import HeadlessRuntimeBridge
    import path_utils
    r,tid,rows,c,job=prepared(tmp_path,'kis')
    monkeypatch.setattr(path_utils,'get_db_file_path',lambda:r.db_path)
    monkeypatch.setattr(path_utils,'get_log_dir',lambda:str(tmp_path/'logs'))
    bridge=HeadlessRuntimeBridge(account='offline-test',factory=lambda *_:pytest.fail('must not initialize trading'))
    bridge._settings=lambda:{}
    service=SimpleNamespace(runtime_snapshot=lambda:{},runtime_bridge=bridge)
    app=create_gateway_app(token='x'*40,application_services=service)
    with TestClient(app) as client:
        path='/api/v1/maintenance/trade-statements'; p={**payload('kis',rows),'action':'preview'}
        assert client.post(path,json=p).status_code==401
        auth={'Authorization':'Bearer '+'x'*40}
        assert client.post(path,headers=auth,json=p).status_code==428
        auth['X-NoahAI-Intent']='confirmed'
        review=client.post(path,headers=auth,json=p)
        assert review.status_code==200,review.text
        request={**p,'action':'import','reviewed_digest':review.json()['digest'],'confirmed_own_account':True}
        response=client.post(path,headers=auth,json=request)
        assert response.status_code==200 and response.json()['stored']
        assert r.execute_query('SELECT exit_time FROM trade_log')[0][0] is None
        assert client.post(path,headers=auth,json={**request,'start_live':True}).status_code==400
        started=client.post('/api/v1/maintenance/trade-records',headers=auth,json={'source':'kis'})
        assert started.status_code==200,started.text
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            result=bridge.record_recovery('kis')
            if result['state'] not in {'running','retry_wait'}: break
            time.sleep(0.01)
        assert result['recovered']==1,result
        assert bridge._app is None


def test_changed_execution_in_second_document_does_not_override_evidence(tmp_path):
    r,tid,rows,c,job=prepared(tmp_path)
    p=payload('okx',rows);commit(r,p)
    rows[1]['price']='96'
    with pytest.raises(ValueError,match='statement_existing_evidence_conflict'): commit(r,payload('okx',rows))
    assert r.execute_query('SELECT count(*) FROM recovery_statements')[0][0]==1


def test_changed_contract_unit_cannot_override_same_execution(tmp_path):
    r,tid,rows,c,job=prepared(tmp_path)
    p=payload('okx',rows);commit(r,p)
    with pytest.raises(ValueError,match='statement_existing_evidence_conflict'):
        commit(r,{**p,'contract_size':'0.01'})


@pytest.mark.parametrize('time_format',['epoch_ms','epoch_seconds'])
def test_explicit_numeric_time_and_grouped_numbers(tmp_path,time_format):
    r,tid,rows,c,job=prepared(tmp_path)
    for row in rows:
        row['timestamp']=str(int(datetime.fromisoformat(row['timestamp']).timestamp())*(1000 if time_format=='epoch_ms' else 1))
        row['price']='1,234.50'
    p={**payload('okx',rows),'time_format':time_format,'number_format':'grouped'}
    preview=read_statement(p)
    assert preview['ready'] and preview['rows'][0]['price']=='1234.50'
    assert preview['rows'][0]['timestamp'].endswith('+00:00')
    assert not read_statement({**p,'number_format':'plain'})['ready']
    rows[0]['price']='12,34.50'
    assert not read_statement({**payload('okx',rows),'time_format':time_format,'number_format':'grouped'})['ready']


def test_linear_contract_multiplier_is_applied_not_assumed_one(tmp_path):
    r,tid,rows,c,job=prepared(tmp_path)
    client,calls,fills=api_client('okx',rows)
    client.exchange.markets['BTC/USDT:USDT']['contractSize']=0.01
    recovery=RecordRecovery(r,RecoveryResolver(r,client,'okx'),delay=0,request_budget=1000)
    assert recovery.start('okx',background=False)['recovered']==1
    assert r.execute_query('SELECT net_pnl FROM trade_log')[0][0]==pytest.approx(-0.4)


def test_changed_anchor_and_complete_roundtrip_after_coverage_hold_recovery(tmp_path):
    r,tid,rows,c,job=prepared(tmp_path)
    client,calls,fills=api_client('okx',rows)
    original=client.exchange.fetch_my_trades
    def fetch(symbol,start,limit,params):
        if start>max(f['timestamp'] for f in fills):
            return [{**fills[0],'id':'later-manual','timestamp':start}]
        return original(symbol,start,limit,params)
    client.exchange.fetch_my_trades=fetch
    recovery=RecordRecovery(r,RecoveryResolver(r,client,'okx'),delay=0,request_budget=1000)
    assert recovery.start('okx',background=False)['recovered']==0
    assert r.execute_query('SELECT exit_time FROM trade_log')[0][0] is None


def test_full_page_is_split_without_losing_same_order_partial_fills(tmp_path):
    from datetime import timedelta
    r,tid,rows,c,job=prepared(tmp_path)
    expanded=[]
    for row in rows:
        for i in range(50):
            expanded.append({**row,'quantity':'0.04','fee':'0.001',
                'execution_id':row['execution_id']+str(i),
                'timestamp':(datetime.fromisoformat(row['timestamp'])+timedelta(milliseconds=i)).isoformat()})
    client,calls,fills=api_client('okx',expanded)
    recovery=RecordRecovery(r,RecoveryResolver(r,client,'okx'),delay=0,request_budget=1000)
    result=recovery.start('okx',background=False)
    assert result['recovered']==1,result
    assert r.execute_query('SELECT net_pnl FROM trade_log')[0][0]==pytest.approx(-10.1)
    assert len([x for x in calls if x[0]=='fills'])>4


def test_common_api_commit_then_restart_does_not_duplicate_pnl(tmp_path,monkeypatch):
    import trading.common_history_recovery as module
    r,tid,rows,c,job=prepared(tmp_path)
    client,calls,fills=api_client('okx',rows)
    original=module.apply_cycle
    def interrupted(*args):
        result=original(*args)
        assert result==''
        raise RuntimeError('simulated_exit_after_atomic_commit')
    monkeypatch.setattr(module,'apply_cycle',interrupted)
    recovery=RecordRecovery(r,RecoveryResolver(r,client,'okx'),delay=0,request_budget=1000)
    assert recovery.start('okx',background=False)['state']=='failed'
    snapshot=r.execute_query('SELECT * FROM trade_log')
    monkeypatch.setattr(module,'apply_cycle',original)
    resumed=RecordRecovery(r,RecoveryResolver(r,client,'okx'),delay=0,now=lambda:time.time()+31)
    assert resumed.start('okx',background=False)['recovered']==1
    assert snapshot==r.execute_query('SELECT * FROM trade_log')
    assert r.execute_query('SELECT count(*) FROM common_recovery_claims')[0][0]==2
