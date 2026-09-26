import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from trading.source_condition_compiler import ConditionCompiler
from trading.declarative_strategy_engine import DeclarativeStrategyEngine as Engine
from trading.custom_strategy_validator import enrich_advanced_indicator_context
from trading.strategy_drive_source import DriveCollector
from trading.strategy_source_ingestor import StrategySourceIngestor


@pytest.mark.parametrize('expression,values,expected',[
    ('all_for(rsi < 30, 3)',[20,25,29],True),
    ('all_for(rsi < 30, 3)',[20,35,29],False),
    ('any_within(rsi < 30, 3)',[40,25,39],True),
    ('became_true(rsi < 30)',[40,25],True),
    ('became_false(rsi < 30)',[25,40],True),
    ('after(rsi < 30, rsi > 50, 3)',[20,40,45,60],True),
    ('after(rsi < 30, rsi > 50, 3)',[40,40,45,60],False),
])
def test_temporal_semantics(expression,values,expected):
    node=ConditionCompiler().compile(expression)
    context={'_closed_bar_contexts':[{'rsi':v,'_bar_timestamp':i+1} for i,v in enumerate(values)]}
    for _ in range(2):  # Repeat/restart does not mutate hidden counters.
        actual,trace=Engine._evaluate_expression_node(node,context)
        assert actual is expected
        assert trace['bars']<=100


@pytest.mark.parametrize('expression',[
    'all_for(rsi < 30, 0)','all_for(rsi < 30, 101)','all_for(rsi < 30, True)',
    'all_for(rsi < 30, x)','all_for(signal == LONG, 2)',
    'unknown(rsi < 30)',
])
def test_temporal_invalid_not_silently_accepted(expression):
    with pytest.raises(ValueError): ConditionCompiler().compile(expression)


@pytest.mark.parametrize('history',[
    [],[{'rsi':20,'_bar_timestamp':1}],
    [{'rsi':20,'_bar_timestamp':1},{'rsi':20,'_bar_timestamp':1}],
    [{'_bar_timestamp':1},{'rsi':20,'_bar_timestamp':2}],
])
def test_temporal_unknown_is_not_false_transition(history):
    node=ConditionCompiler().compile('became_true(rsi < 30)')
    assert not Engine._evaluate_expression_node(node,{'_closed_bar_contexts':history})[0]


def test_temporal_requires_declared_timeframe_but_branches_inherit_it():
    spec={'expression':ConditionCompiler().compile('all_for(rsi < 30, 3)')}
    assert not Engine.validate_rule_spec({'executable_entry':spec})['valid']
    assert Engine.validate_rule_spec({'decision_timeframe':'15m','independent_entries':{'LONG':spec}})['valid']


def test_temporal_closed_candles_same_context_all_venues():
    rules={'decision_timeframe':'5m','executable_entry':{'expression':ConditionCompiler().compile('all_for(close > 0, 3)')}}
    now=int(datetime.now(timezone.utc).timestamp())
    rows=[[now*1000-(310-i)*300000,100,101,99,100+i/100,20] for i in range(310)]
    rows.append([now*1000,999,999,999,999,999]) # Unclosed bar excluded.
    calls=[]
    for venue in ('binance','okx','bybit','bitget','upbit','bithumb','coinone','kis','kiwoom','shinhan','mirae'):
        context=enrich_advanced_indicator_context({'exchange':venue},rules,lambda tf,n: calls.append(n) or rows[-n:])
        scoped=context['_strategy_timeframe_contexts']['5m']
        assert len(scoped['_closed_bar_contexts'])==3
        assert set(scoped['_closed_bar_contexts'][0])=={'close','_bar_timestamp','_previous'}
        assert scoped['_closed_bar_contexts'][-1]['close']<999
        assert Engine.evaluate_entry(rules,context)['allowed']
    assert max(calls)==208


def test_temporal_source_ir_and_original_retained(tmp_path):
    text='TIMEFRAME: 15m\nLONG 전략\nENTRY: all_for(rsi < 30, 3)\nEXIT: became_true(rsi > 55)\nEND\n손절 1%, 익절 2%, 자산 5%. 횡보장에서 사용.'
    result=StrategySourceIngestor().analyze(text,kind='text')
    assert result['ready_for_execution'], result['missing_conditions']
    assert result['rules']['decision_timeframe']=='15m'
    assert result['rules']['source_evidence']['text']==text
    assert 'temporal' in json.dumps(result['strategy_ir'])
    from trading.custom_strategy_pipeline import CustomStrategyPipeline
    from web_platform.application_services import ApplicationServices
    checked=ApplicationServices.validate_strategy_draft(None,rules=result['rules'])
    assert checked['ready'], checked
    path=tmp_path/'strategies.json'
    pipeline=CustomStrategyPipeline(storage_path=path)
    version=pipeline.submit(name='temporal',rules=checked['rules'])
    key,vid=version['strategy_key'],version['version_id']
    pipeline.approve(key,vid,approved_by='fixture')
    paper=CustomStrategyPipeline(storage_path=path).start_paper_observation(key,vid)
    assert paper['status']=='paper_observing'
    assert not paper.get('execution_validation')  # No historical pass required.
    changed=dict(result['rules'],decision_timeframe='1h',execution_timeframe='1h')
    assert not ApplicationServices.validate_strategy_draft(None,rules=changed)['ready']


def test_replay_cutoff_includes_decision_close_not_future_bar():
    from trading.custom_strategy_validator import _enrich_replay_context, _decision_close_timestamp
    rules={'decision_timeframe':'5m','executable_entry':{'expression':ConditionCompiler().compile('all_for(close > 99, 2)')}}
    rows=[{'timestamp':1700000000+i*300,'open':100,'high':101,'low':99,'close':100,'volume':1} for i in range(220)]
    rows[-1]['close']=1  # Future candle would invalidate the rule.
    decision=rows[-2]
    enriched=_enrich_replay_context({},rules,rows,timeframe_rows={'5m':rows},cutoff_timestamp=_decision_close_timestamp(decision,rules))
    bars=enriched['_strategy_timeframe_contexts']['5m']['_closed_bar_contexts']
    assert bars[-1]['_bar_timestamp']==decision['timestamp']
    assert Engine.evaluate_entry(rules,enriched)['allowed']


@pytest.mark.parametrize('venue',['upbit','bithumb'])
def test_spot_exact_order_partial_cancelled_fill_contract(venue):
    from trading.exchanges.interfaces.spot_exchange import SpotExchange
    # Call the shared method unbound; no connection or credentials.
    fills=[{'id':'f1','order':'o1','symbol':'BTC/KRW','side':'sell','amount':1,'price':100,
            'timestamp':1700000000000,'fee':{'cost':1,'currency':'KRW'}}]
    order={'id':'o1','symbol':'BTC/KRW','side':'sell','status':'canceled','filled':1,'trades':fills}
    client=SimpleNamespace(exchange=SimpleNamespace(fetch_order=lambda *args:order))
    assert SpotExchange.get_recovery_order_fills(client,'BTC/KRW','o1',1700000000)[0]['_execution_confirmed']
    order['filled']=2
    with pytest.raises(RuntimeError,match='partial_or_quantity_mismatch'):
        SpotExchange.get_recovery_order_fills(client,'BTC/KRW','o1',1700000000)
    order['filled']=1;order['trades'][0]['order']='other'
    with pytest.raises(RuntimeError,match='history_identity_mismatch'):
        SpotExchange.get_recovery_order_fills(client,'BTC/KRW','o1',1700000000)


class Reply:
    def __init__(self,value,status=200):
        self.raw=value if isinstance(value,bytes) else json.dumps(value).encode()
        self.status_code=status
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def iter_content(self,n): yield self.raw


def drive_session(*,fault='',rows=1):
    raw=b'15m RSI 30 LONG. Stop loss 1%, take profit 2%, position size 5%.'
    metadata={'id':'file1','name':'strategy.txt','mimeType':'text/plain','version':'1',
              'modifiedTime':'2026-09-25','md5Checksum':hashlib.md5(raw).hexdigest()}
    calls=[]
    def get(url,**kwargs):
        calls.append((url,kwargs)); p=kwargs['params']
        if url.endswith('/files'):
            if fault=='repeat_cursor': return Reply({'files':[],'nextPageToken':'again'})
            if not p.get('pageToken'): return Reply({'files':[{'id':'child','name':'folder','mimeType':'application/vnd.google-apps.folder'}],'nextPageToken':'page2'})
            return Reply({'files':[metadata],'incompleteSearch':fault=='incomplete'})
        if p.get('alt')=='media': return Reply(raw,403 if fault=='denied' else 200)
        return Reply({k:('2' if fault=='changed' and k=='version' else metadata[k]) for k in ('id','version','modifiedTime')})
    return SimpleNamespace(get=get),calls


def test_drive_paginated_nested_download_and_provenance():
    session,calls=drive_session()
    source=DriveCollector(api_key='secret-key',session=session).extract(StrategySourceIngestor(),'https://drive.google.com/drive/folders/root')
    assert len(source.evidence['drive_files'])==1
    assert source.evidence['drive_files'][0]['sha256']
    assert 'secret-key' not in json.dumps(source.evidence)
    assert all(c[0].startswith('https://www.googleapis.com/drive/v3/files') for c in calls)
    assert all(c[1]['allow_redirects'] is False for c in calls)
    assert any(c[1]['params'].get('pageToken')=='page2' for c in calls)


@pytest.mark.parametrize('fault',['changed','denied','repeat_cursor'])
def test_drive_failures_are_explicit_and_no_secret(fault):
    session,_=drive_session(fault=fault)
    with pytest.raises(ValueError) as exc:
        DriveCollector(access_token='secret-token',session=session).extract(StrategySourceIngestor(),'https://drive.google.com/drive/folders/root')
    assert 'secret-token' not in str(exc.value)


def test_drive_incomplete_search_preserved():
    session,_=drive_session(fault='incomplete')
    result=DriveCollector(api_key='fake',session=session).extract(StrategySourceIngestor(),'https://drive.google.com/drive/folders/root')
    assert result.evidence['drive_omissions'] and result.evidence['coverage_complete'] is False


@pytest.mark.parametrize('url',['http://drive.google.com/drive/folders/id','https://drive.google.com.evil/drive/folders/id','https://drive.google.com/file/d/id'])
def test_drive_url_scope(url):
    with pytest.raises(ValueError): DriveCollector().extract(StrategySourceIngestor(),url)


def test_history_continuation_and_nonprogress():
    from trading.stock_history_recovery import _pages
    calls=[]
    def fetch(cursor):
        calls.append(cursor)
        return {'rows':[{'id':len(calls)}],'nk':'next' if len(calls)==1 else '', '_tr_cont':'M' if len(calls)==1 else 'D'}
    assert _pages(fetch,'rows',(('nk','NK'),))==[{'id':1},{'id':2}]
    assert calls==[{}, {'NK':'next'}]
    with pytest.raises(RuntimeError,match='history_page_incomplete'):
        _pages(lambda c:{'rows':[{'id':1}],'nk':'repeat','_tr_cont':'M'},'rows',(('nk','NK'),))


def test_kis_old_history_tr_and_continuation_header():
    from trading.exchanges.adapters.korea_investment_stock_adapter import KoreaInvestmentStockAdapter
    calls=[]
    response=SimpleNamespace(status_code=200,headers={'tr_cont':'M'})
    def get(url,**kwargs): calls.append(kwargs); return response
    adapter=SimpleNamespace(_get_http=lambda:SimpleNamespace(get=get),
        _tr_id=lambda *a,**kw:'TTTC0081R',_ensure_token=lambda:True,
        _request_headers=lambda tr:{'tr_id':tr,'authorization':'old'},_access_token='fake',
        _base_url=lambda:'https://example.invalid',request_timeout=1,
        _response_to_dict=lambda *a,**kw:{'rt_cd':'0','output1':[]})
    result=KoreaInvestmentStockAdapter._get(adapter,'/uapi/domestic-stock/v1/trading/inquire-daily-ccld',
        {'INQR_END_DT':'20200101','CTX_AREA_NK100':'next'})
    assert calls[0]['headers']['tr_id']=='CTSC9215R'
    assert calls[0]['headers']['tr_cont']=='N'
    assert result['_tr_cont']=='M'


def test_kiwoom_continuation_exact_order_found_on_second_page():
    from trading.stock_history_recovery import order_fills
    calls=[]; state=SimpleNamespace(tr_remained=False)
    def fetch(*args,**kwargs):
        calls.append(kwargs['next']);state.tr_remained=len(calls)==1
        return {'multi':[{'order_id':'other' if len(calls)==1 else 'owned','체결단가':100,
                          'fee':1,'tax':0,'체결시간':'120000'}]}
    adapter=SimpleNamespace(is_connected=True,account_no='fixture',account_password='',exchange_name='kiwoom',
        kiwoom=state,_call_block_request=fetch,_normalize_symbol=lambda s:s,
        _parse_trade_record=lambda raw:{'order_id':raw['order_id'],'symbol':'005930','side':'buy',
                                      'quantity':1,'timestamp':'120000'})
    result=order_fills(adapter,'005930','owned',1700000000)
    assert calls==[0,2] and len(result)==1 and result[0]['order']=='owned'


def test_mixed_partial_exits_require_explicit_file_entry_references(tmp_path):
    from test_v39147_statement_and_common_discovery import prepared,payload,commit
    from trading.recovery_statement import recover_from_statements
    r,tid,rows,_,_=prepared(tmp_path)
    rows[1]['quantity']='1'; rows[1]['entry_order_id']='entry-1'
    rows.append({**rows[1],'execution_id':'second-close','order_id':'close2','timestamp':rows[1]['timestamp'].replace('+00:00','.001000+00:00')})
    rows.append({**rows[0],'execution_id':'manual','order_id':'manual-entry','quantity':'4'})
    rows.append({**rows[1],'execution_id':'manual-close','order_id':'manual-exit','entry_order_id':'manual-entry','quantity':'4'})
    commit(r,payload('okx',rows))
    import sqlite3
    with sqlite3.connect(r.db_path) as db:
        db.row_factory=sqlite3.Row; trade=dict(db.execute('SELECT * FROM trade_log WHERE id=?',(tid,)).fetchone())
    assert recover_from_statements(r,'okx',trade)==''
    assert r.execute_query('SELECT net_pnl FROM trade_log WHERE id=?',(tid,))[0][0]==pytest.approx(-10.5)
    assert r.execute_query('SELECT count(*) FROM common_recovery_claims')[0][0]==3
