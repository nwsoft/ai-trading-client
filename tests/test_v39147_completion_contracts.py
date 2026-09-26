import json
import sqlite3
import time
from datetime import datetime,timezone
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import parse_qs,urlparse

import pytest

from trading.source_condition_compiler import ConditionCompiler
from trading.declarative_strategy_engine import DeclarativeStrategyEngine as Engine
from trading.temporal_strategy_conditions import required_bars
from trading.drive_authorization import DriveAuthorization,SCOPE
from trading.cash_history_recovery import CashHistoryRecovery
from trading.binance_history_recovery import HistoryPending
from trading.recovery_allocation import recover_shared_cycle
from test_v39147_statement_and_common_discovery import prepared, payload, commit


@pytest.mark.parametrize('document',[
    [], {'installed':[]}, {'installed':{'client_id':{}}}, {'public_api_key':[]},
])
def test_drive_deployment_config_rejects_invalid_shapes(tmp_path,monkeypatch,document):
    from trading.drive_authorization import deployment_config
    path=tmp_path/'drive.json'
    path.write_text(json.dumps(document),encoding='utf-8')
    monkeypatch.setenv('NOAHAI_DRIVE_CLIENT_CONFIG',str(path))
    with pytest.raises(ValueError,match='운영자 연결 설정'):
        deployment_config()


@pytest.mark.parametrize('expr,values,expected',[
    ('any_within(became_true(rsi < 30),3)',[50,20,25,40],True),
    ('all_for(any_within(rsi < 30,2),3)',[20,50,20,50],True),
    ('all_for(became_true(rsi < 30),2)',[40,20,20],False),
    ('latched(rsi < 30,rsi > 70,4)',[20,40,50,60],True),
    ('latched(rsi < 30,rsi > 70,4)',[20,80,50,60],False),
    ('latched(rsi < 50,rsi > 20,2)',[10,30],False),
    ('latched(became_true(rsi < 30),rsi > 70,3)',[50,20,40,50],True),
])
def test_nested_temporal_state_restart_and_no_future(expr,values,expected):
    node=ConditionCompiler().compile(expr)
    assert required_bars(node)==len(values)
    context={'_closed_bar_contexts':[{'rsi':v,'_bar_timestamp':i+1} for i,v in enumerate(values)]}
    before=json.dumps(context)
    for _ in range(3):assert Engine._evaluate_expression_node(node,context)[0] is expected
    assert json.dumps(context)==before
    context['_closed_bar_contexts'][0]['rsi']=None
    assert not Engine._evaluate_expression_node(node,context)[0]


def test_nested_window_total_bound_and_named_state():
    with pytest.raises(ValueError):ConditionCompiler().compile('all_for(all_for(all_for(all_for(rsi < 30,100),100),100),100)')
    node=ConditionCompiler({'armed':'latched(rsi < 30,rsi > 70,10)'}).compile('armed and rsi > 40')
    assert required_bars(node)==10


def test_drive_authorization_state_pkce_refresh_cancel_no_token_exposure():
    posts=[];urls=[]
    def post(url,**kw):
        posts.append(kw)
        return SimpleNamespace(status_code=200,json=lambda:{'access_token':'private-token','refresh_token':'private-refresh',
            'expires_in':3600,'token_type':'Bearer','scope':SCOPE})
    auth=DriveAuthorization({'client_id':'fixture','api_key':'public-app-key'},SimpleNamespace(post=post))
    try:
        state=auth.start(lambda url:urls.append(url) or True)
        query=parse_qs(urlparse(urls[0]).query)
        assert query['code_challenge_method']==['S256'] and query['scope']==[SCOPE]
        assert query['redirect_uri'][0].startswith('http://127.0.0.1:')
        assert not auth.complete('wrong','code','',0) and not posts
        assert auth.complete(query['state'][0],'code','',0)
        assert not auth.complete(query['state'][0],'code','',0)  # One-use state.
        assert auth.access_token()=='private-token'
        assert 'private-' not in json.dumps(auth.status())
        auth.tokens['expires_at']=0
        assert auth.access_token()=='private-token'
        assert posts[-1]['data']['grant_type']=='refresh_token'
        auth.disconnect();assert auth.access_token()==''
    finally:auth.disconnect()


def test_drive_no_deployment_config_does_not_open_browser():
    auth=DriveAuthorization({})
    with pytest.raises(ValueError,match='운영자'):auth.start(lambda url:pytest.fail('unexpected browser'))
    assert not auth.status()['connected']


def shared_case(tmp_path,venue='okx'):
    recorder,tid,rows,client,job=prepared(tmp_path,venue)
    with sqlite3.connect(recorder.db_path) as db:
        db.row_factory=sqlite3.Row
        original=dict(db.execute('SELECT * FROM trade_log WHERE id=?',(tid,)).fetchone())
        clone={k:v for k,v in original.items() if k!='id'}
        clone.update(order_id='entry-2',entry_price=110)
        keys=list(clone)
        db.execute(f'INSERT INTO trade_log({",".join(keys)}) VALUES({",".join("?" for _ in keys)})',tuple(clone.values()))
    second={**rows[0],'execution_id':'entry-2-fill','order_id':'entry-2','price':'110'}
    rows.insert(1,second)
    rows[-1]['quantity']='4'
    return recorder,original,rows


@pytest.mark.parametrize('venue',['binance','okx','bybit','bitget','upbit','bithumb','coinone','kis','kiwoom','shinhan','mirae'])
def test_shared_fill_atomic_quantity_fee_sum_all_venues(tmp_path,venue):
    recorder,target,rows=shared_case(tmp_path,venue)
    assert recover_shared_cycle(recorder,venue,target,rows,{'kind':'statement'})==''
    values=recorder.execute_query('SELECT quantity,net_pnl,entry_fee,exit_fee FROM trade_log ORDER BY id')
    assert values[0][1]==pytest.approx(-10.2 if venue not in {'kis','kiwoom','shinhan','mirae'} else -10.225)
    assert values[1][1]==pytest.approx(-30.2 if venue not in {'kis','kiwoom','shinhan','mirae'} else -30.225)
    allocations=recorder.execute_query("SELECT quantity,fee FROM common_recovery_allocations WHERE execution_id='exit-fill'")
    assert sum(Decimal(a[0]) for a in allocations)==4
    assert sum(Decimal(a[1]) for a in allocations)==Decimal('0.2')
    snapshot=recorder.execute_query('SELECT * FROM trade_log')
    assert recover_shared_cycle(recorder,venue,target,rows,{'kind':'statement'})=='order_attribution_conflict'
    assert snapshot==recorder.execute_query('SELECT * FROM trade_log')


def test_shared_fill_rollback_and_explicit_different_exit_prices(tmp_path):
    r,target,rows=shared_case(tmp_path)
    first={**rows[-1],'quantity':'2','entry_allocations':{'entry-1':'2'}}
    second={**first,'execution_id':'exit-fill-2','price':'96','entry_allocations':{'entry-2':'2'}}
    rows=rows[:-1]+[first,second]
    before=r.execute_query('SELECT * FROM trade_log')
    with sqlite3.connect(r.db_path) as db:
        db.execute("CREATE TRIGGER simulate_failure BEFORE UPDATE ON trade_log WHEN NEW.order_id='entry-2' BEGIN SELECT RAISE(ABORT,'fixture crash'); END")
    with pytest.raises(sqlite3.IntegrityError):recover_shared_cycle(r,'okx',target,rows,{'kind':'statement'})
    assert before==r.execute_query('SELECT * FROM trade_log')
    assert not r.execute_query('SELECT * FROM common_recovery_allocations')
    with sqlite3.connect(r.db_path) as db:db.execute('DROP TRIGGER simulate_failure')
    assert recover_shared_cycle(r,'okx',target,rows,{'kind':'statement'})==''


def test_ambiguous_manual_and_different_price_not_guessed(tmp_path):
    r,target,rows=shared_case(tmp_path)
    rows[-1]['quantity']='2'
    rows.append({**rows[-1],'execution_id':'exit-2','price':'96'})
    before=r.execute_query('SELECT * FROM trade_log')
    assert recover_shared_cycle(r,'okx',target,rows,{'kind':'statement'})=='exit_lot_allocation_required'
    assert before==r.execute_query('SELECT * FROM trade_log')


@pytest.mark.parametrize('venue',['binance','okx','bybit','bitget','upbit','bithumb','coinone','kis','kiwoom','shinhan','mirae'])
def test_explicit_interleaved_entry_and_partial_exit(tmp_path,venue):
    from datetime import timedelta
    r,target,rows=shared_case(tmp_path,venue)
    start=datetime.fromisoformat(rows[0]['timestamp'])
    stamp=lambda seconds:(start+timedelta(seconds=seconds)).isoformat()
    first,second,exit_row=rows
    second={**second,'timestamp':stamp(120)}
    partial={**exit_row,'quantity':'1','timestamp':stamp(60),'entry_allocations':{'entry-1':'1'}}
    final={**exit_row,'execution_id':'exit-later','quantity':'3','timestamp':stamp(180),
           'price':'96','entry_allocations':{'entry-1':'1','entry-2':'2'}}
    rows=[first,partial,second,final]
    before=r.execute_query('SELECT * FROM trade_log')
    # No original allocation: never invent FIFO even with a complete flat cycle.
    missing=[{k:v for k,v in row.items() if k!='entry_allocations'} for row in rows]
    assert recover_shared_cycle(r,venue,target,missing,{'kind':'statement'})=='exit_lot_allocation_required'
    # Attribution to a not-yet-open lot must not pass just because totals match.
    future=[first,{**partial,'entry_allocations':{'entry-2':'1'}},second,
            {**final,'entry_allocations':{'entry-1':'2','entry-2':'1'}}]
    assert recover_shared_cycle(r,venue,target,future,{'kind':'statement'})
    assert before==r.execute_query('SELECT * FROM trade_log')
    from trading.record_recovery import RecordRecovery
    from trading.record_recovery_adapters import RecoveryResolver
    serialized=[{**row,**({'entry_allocations':json.dumps(row['entry_allocations'])} if row.get('entry_allocations') else {})} for row in rows]
    commit(r,payload(venue,serialized))
    recovery=RecordRecovery(r,RecoveryResolver(r,None,venue),delay=0)
    result=recovery.start(venue,background=False)
    assert result['recovered']==2 and result['remaining']==0,result
    assert not result['auto_started'] and not result['resume_authorized']
    total_net=r.execute_query('SELECT SUM(net_pnl) FROM trade_log')[0][0]
    assert total_net==pytest.approx(-37.7 if venue in {'kis','kiwoom','shinhan','mirae'} else -37.6)
    allocations=r.execute_query('SELECT execution_id,quantity,fee FROM common_recovery_allocations')
    for row in rows:
        selected=[a for a in allocations if a[0]==row['execution_id']]
        assert sum((Decimal(a[1]) for a in selected),Decimal(0))==Decimal(row['quantity'])
        assert sum((Decimal(a[2]) for a in selected),Decimal(0))==Decimal(row['fee'])
    repaired=r.execute_query('SELECT * FROM trade_log')
    assert recover_shared_cycle(r,venue,target,rows,{'kind':'statement'})=='order_attribution_conflict'
    assert repaired==r.execute_query('SELECT * FROM trade_log')


@pytest.mark.parametrize('venue',['upbit','bithumb','coinone','kis','kiwoom','shinhan','mirae'])
def test_missing_close_discovery_resumes_and_preserves_unknown(tmp_path,venue):
    r,tid,rows,_,_=prepared(tmp_path,venue)
    with sqlite3.connect(r.db_path) as db:
        db.row_factory=sqlite3.Row;target=dict(db.execute('SELECT * FROM trade_log').fetchone())
    normalized=[{'id':row['execution_id'],'order':row['order_id'],'symbol':row['symbol'],'side':row['side'],
                 'amount':row['quantity'],'price':row['price'],'timestamp':row['timestamp'],
                 'fee':{'cost':str(Decimal(row['fee'])+Decimal(row['tax'])),'currency':row['fee_currency']},'_execution_confirmed':True} for row in rows]
    client=SimpleNamespace(api_key='fixture',account_no='fixture',_normalize_symbol=lambda s:'BTC/KRW',
        get_positions_result=lambda:{'status':'success','positions':[]},exchange=SimpleNamespace(fetch_balance=lambda:{'total':{'BTC':0}}),
        get_recovery_day_fills=lambda symbol,epoch:[n for n in normalized if epoch<=datetime.fromisoformat(n['timestamp']).timestamp()<epoch+86400],
        get_recovery_order_fills=lambda symbol,oid,epoch:[n for n in normalized if epoch<=datetime.fromisoformat(n['timestamp']).timestamp()<epoch+86400])
    for _ in range(5):
        recovery=CashHistoryRecovery(r,client,venue,lambda:None);recovery.job_id='same-job'
        try:reason=recovery.recover(target);break
        except HistoryPending:pass
    else:pytest.fail('did not resume')
    assert reason==''
    assert r.execute_query('SELECT exit_order_id FROM trade_log')[0][0]=='close-discovered'


@pytest.mark.parametrize('venue',['upbit','bithumb'])
def test_native_spot_completed_cancelled_orders_and_api_signature(monkeypatch,venue):
    from trading.spot_history_discovery import day_fills
    import base64,hashlib,hmac
    from urllib.parse import unquote
    monkeypatch.setattr('trading.spot_history_discovery.time.sleep',lambda _:None)
    epoch=1700000000
    stamp=datetime.fromtimestamp(epoch+10,timezone.utc).isoformat()
    detail={'uuid':'order-1','order_id':'order-1','side':'bid','state':'cancel','market':'KRW-BTC',
            'executed_volume':'2','paid_fee':'0.1','trades':[
                {'uuid':'f1','market':'KRW-BTC','side':'bid','price':'100','volume':'1','created_at':stamp},
                {'uuid':'f2','market':'KRW-BTC','side':'bid','price':'102','volume':'1','created_at':stamp}]}
    summary={k:v for k,v in detail.items() if k!='trades'};summary['created_at']=stamp
    calls=[]
    def get(url,**kw):
        calls.append(url);query=parse_qs(urlparse(url).query)
        signed=kw['headers']['Authorization'][7:]
        head,body,signature=signed.split('.')
        assert json.loads(base64.urlsafe_b64decode(head+'=='))['alg']=='HS256'
        assert hmac.compare_digest(base64.urlsafe_b64decode(signature+'=='),hmac.new(b'fixture-secret',(head+'.'+body).encode(),hashlib.sha256).digest())
        token=json.loads(base64.urlsafe_b64decode(body+'=='))
        raw=unquote(urlparse(url).query)
        assert token['query_hash']==hashlib.sha512(raw.encode()).hexdigest()
        assert kw['allow_redirects'] is False
        if urlparse(url).path=='/v1/order':data=detail
        elif venue=='bithumb':data={'data':[summary],'has_next':False,'next_key':None}
        else:data=[] if query['state']==['done'] else [summary]
        return SimpleNamespace(status_code=200,json=lambda:data)
    adapter=SimpleNamespace(exchange_name=venue,api_key='fixture-key',secret_key='fixture-secret',_normalize_symbol=lambda s:'BTC/KRW')
    rows=day_fills(adapter,'BTC/KRW',epoch,SimpleNamespace(get=get))
    assert len(rows)==1 and rows[0]['price']=='101' and rows[0]['amount']=='2' and rows[0]['fee']['cost']=='0.1'
    assert any('/v1/order?' in url for url in calls)
    assert all(url.startswith(f'https://api.{venue}.com/') for url in calls)


def test_cash_failed_position_not_zero_and_invalid_cost_never_saved(tmp_path):
    r,tid,rows,_,_=prepared(tmp_path,'kis')
    with sqlite3.connect(r.db_path) as db:
        db.row_factory=sqlite3.Row;target=dict(db.execute('SELECT * FROM trade_log').fetchone())
    client=SimpleNamespace(account_no='fixture',get_positions_result=lambda:{'status':'error','positions':[]})
    before=r.execute_query('SELECT * FROM trade_log')
    with pytest.raises(RuntimeError,match='provider_history_query_failed'):
        CashHistoryRecovery(r,client,'kis',lambda:None).recover(target)
    assert before==r.execute_query('SELECT * FROM trade_log')


def test_statement_shared_allocation_import_to_recovery(tmp_path):
    from trading.record_recovery import RecordRecovery
    from trading.record_recovery_adapters import RecoveryResolver
    r,target,rows=shared_case(tmp_path,'binance')
    commit(r,payload('binance',rows))
    job=RecordRecovery(r,RecoveryResolver(r,None,'binance'),delay=0)
    result=job.start('binance',background=False)
    assert result['recovered']==2 and result['remaining']==0,result
    saved=r.execute_query('SELECT * FROM trade_log')
    job.now=lambda:time.time()+31
    assert job.start('binance',background=False)['total']==0
    assert r.execute_query('SELECT * FROM trade_log')==saved


def test_nested_evaluation_computation_is_bounded():
    node=ConditionCompiler().compile('all_for(all_for(all_for(rsi < 30,100),100),100)')
    count=required_bars(node)
    before=time.monotonic()
    assert Engine._evaluate_expression_node(node,{'_closed_bar_contexts':[{'rsi':20,'_bar_timestamp':i} for i in range(count)]})[0]
    assert time.monotonic()-before<2


def test_google_refresh_failure_drops_credentials_without_logging():
    auth=DriveAuthorization({'client_id':'fixture'},SimpleNamespace(post=lambda *a,**k:SimpleNamespace(status_code=400)))
    auth.tokens={'access_token':'secret','refresh_token':'private','expires_at':0}
    with pytest.raises(ValueError,match='다시 연결'):auth.access_token()
    assert auth.tokens=={} and auth.status()['result']=='reconnect_required'


def test_drive_gateway_requires_auth_and_explicit_intent():
    from fastapi.testclient import TestClient
    from web_platform.gateway import create_gateway_app
    calls=[]
    services=SimpleNamespace(runtime_snapshot=lambda:{},drive_authorization=lambda action='status':calls.append(action) or {'connected':False})
    with TestClient(create_gateway_app(token='x'*32,application_services=services)) as client:
        assert client.post('/api/v1/strategies/drive/connect').status_code==401
        auth={'Authorization':'Bearer '+'x'*32}
        assert client.post('/api/v1/strategies/drive/connect',headers=auth).status_code==428
        assert not calls
        auth['X-NoahAI-Intent']='confirmed'
        assert client.post('/api/v1/strategies/drive/connect',headers=auth).status_code==200
        assert calls==['connect']


def test_native_account_absent_currency_is_zero_only_for_valid_complete_list():
    from trading.spot_history_discovery import holding_quantity
    adapter=SimpleNamespace(exchange_name='upbit',api_key='fixture',secret_key='secret',_normalize_symbol=lambda s:'BTC/KRW')
    session=SimpleNamespace(get=lambda *a,**k:SimpleNamespace(status_code=200,json=lambda:[{'currency':'KRW','balance':'10','locked':'0'}]))
    assert holding_quantity(adapter,'BTC/KRW',session)==0
    session.get=lambda *a,**k:SimpleNamespace(status_code=200,json=lambda:{'error':'failure'})
    with pytest.raises(RuntimeError,match='position_anchor_unavailable'):holding_quantity(adapter,'BTC/KRW',session)
