"""End-to-end local contracts only: no customer writes, account calls or orders."""
import json
import sqlite3
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest
from trading.numeric_strategy_state import NumericStateStore,validate,identity,enrich_states
from trading.strategy_source_ingestor import StrategySourceIngestor
from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.custom_strategy_validator import enrich_advanced_indicator_context,run_historical_replay
from trading.declarative_strategy_engine import DeclarativeStrategyEngine as Engine
from web_platform.application_services import ApplicationServices
from test_v39147_completion_contracts import shared_case
from test_v39147_statement_and_common_discovery import prepared,payload,commit
from trading.record_recovery import RecordRecovery
from trading.record_recovery_adapters import RecoveryResolver

VENUES=['binance','okx','bybit','bitget','upbit','bithumb','coinone','kis','kiwoom','shinhan','mirae']
PROGRAM={'initial':{'counter':0,'previous':0},'updates':{'counter':'counter + 1 if close > 0 else 0','previous':'counter'}}
SOURCE='''TIMEFRAME: 15m
STATE counter = 0
UPDATE counter = counter + 1 if close > 0 else 0
LONG 전략
ENTRY: counter >= 2 and close > 0
EXIT: counter >= 5
END
손절 1%, 익절 2%, 자산 5%. 횡보장에서 사용.'''

def bar(i,close=100):return {'_bar_timestamp':i*900,'close':close}

def test_state_persistence_atomic_simultaneous_and_namespaces(tmp_path):
    path=tmp_path/'state.sqlite3';s=NumericStateStore(path);scope={'venue':'okx','symbol':'BTC','mode':'live','strategy':'v1'}
    first=s.advance(PROGRAM,scope,[bar(1)])
    assert first['values']=={'counter':1,'previous':0}
    with ThreadPoolExecutor(max_workers=8) as executor:
        results=list(executor.map(lambda _:NumericStateStore(path).advance(PROGRAM,scope,[bar(1),bar(2)]),range(8)))
    assert all(r['values']=={'counter':2,'previous':1} for r in results)
    assert NumericStateStore(path).advance(PROGRAM,scope,[bar(1),bar(2)])==results[0]
    for key,value in [('venue','kis'),('symbol','ETH'),('mode','paper'),('strategy','v2')]:
        assert s.advance(PROGRAM,{**scope,key:value},[bar(1),bar(2)])['values']['counter']==1
    assert NumericStateStore(tmp_path/'other.sqlite3').advance(PROGRAM,scope,[bar(2)])['values']['counter']==1
    with pytest.raises(ValueError,match='revision'):s.advance(PROGRAM,scope,[bar(2,101)])
    with pytest.raises(ValueError,match='gap'):s.advance(PROGRAM,scope,[bar(4)])
    with pytest.raises(ValueError,match='reversed'):s.advance(PROGRAM,scope,[bar(1)])
    assert s.advance(PROGRAM,scope,[bar(2),bar(3),bar(4)])['values']['counter']==4

@pytest.mark.parametrize('expression',["__import__('os')",'counter.__class__','[counter]','counter ** 999','missing + 1','open("x")','min(counter)','abs(counter,1)','counter + min'])
def test_state_rejects_unbounded_or_unknown_language(expression):
    assert validate({'initial':{'counter':0},'updates':{'counter':expression}})

def test_state_failure_does_not_advance_then_retry(tmp_path):
    program={'initial':{'x':0,'y':0},'updates':{'x':'x + 1','y':'1 / close'}}
    s=NumericStateStore(tmp_path/'state.sqlite3')
    old=s.advance(program,'scope',[bar(1)])
    with pytest.raises(ArithmeticError):s.advance(program,'scope',[bar(1),bar(2,0)])
    assert s.advance(program,'scope',[bar(1)])==old
    assert s.advance(program,'scope',[bar(1),bar(2,2)])['values']=={'x':2,'y':.5}


def test_state_numeric_transport_canonicalization(tmp_path):
    store=NumericStateStore(tmp_path/'state.sqlite3')
    before=store.advance(PROGRAM,'s',[bar(1)])
    transported=deepcopy(PROGRAM);transported['initial']={k:float(v) for k,v in transported['initial'].items()}
    assert store.advance(transported,'s',[{'_bar_timestamp':900.0,'close':100.0}])==before


def test_numeric_indicator_window_roll_is_not_a_candle_revision(tmp_path):
    import math
    rules=source_rules()
    rules['numeric_state']['updates']['counter']='counter + 1 if ema200 > 0 else 0'
    item={'rules':rules,'version_id':'v1','strategy_key':'s1'}
    now=int(datetime.now(timezone.utc).timestamp())
    rows=[[(now-(720-i)*900)*1000,100,120,80,100+10*math.sin(i/17),10] for i in range(710)]
    store=NumericStateStore(tmp_path/'state.sqlite3')
    def ctx(end):return enrich_advanced_indicator_context({'signal':'LONG'},[item],lambda tf,n:rows[:end][-n:],
        state_scope={'venue':'binance','symbol':'BTC','mode':'paper'},state_store=store)
    key=identity(rules,item)
    assert ctx(605)['_numeric_state_results'][key]['values']['counter']==1
    advanced=ctx(606)['_numeric_state_results'][key]
    assert advanced['status']=='ready' and advanced['values']['counter']==2
    assert advanced['inputs']['ema200']>0
    rows[605][4]+=1
    assert ctx(606)['_numeric_state_results'][key]['reason']=='state_candle_revision'


def test_parallel_paper_does_not_attribute_base_fallback(tmp_path,monkeypatch):
    import trading.parallel_strategy_paper as module
    from test_v39122_parallel_strategy_paper import _settings,_strategy
    monkeypatch.setattr(module,'get_app_data_dir',lambda:tmp_path)
    item=_strategy();item['rules']={'executable_entry':{'all':[{'field':'rsi','operator':'lt','value':30}]}}
    engine=module.ParallelStrategyPaperEngine(settings_provider=_settings)
    result=engine.observe(target='binance',symbol='BTCUSDT',asset_class='crypto',primary_execution_mode='live',
        context={'signal':'LONG','current_price':100,'rsi':80},strategy_pool=[item],market_regime='range')
    assert result['opened']==0 and not engine.snapshot()

def source_rules():
    result=StrategySourceIngestor().analyze(SOURCE,kind='text')
    assert result['ready_for_execution'],result.get('missing_conditions')
    return result['rules']

@pytest.mark.parametrize('level',range(1,6))
def test_source_saved_approved_paper_without_backtest_and_legacy_preserved(tmp_path,level):
    rules=source_rules();assert ApplicationServices.validate_strategy_draft(None,rules=rules)['ready']
    from trading.noah_strategy_ir import NoahStrategyIR
    assert NoahStrategyIR.project(NoahStrategyIR.compile(rules),level)['level']==level
    path=tmp_path/'strategies.json';p=CustomStrategyPipeline(storage_path=path)
    old=p.submit(name='legacy',rules={**rules,'source_grounding':{'status':'user_declared_override','confirmed_by_user':True},'executable_entry':{'all':[],'any':[]}})
    before=deepcopy(old)
    new=p.submit(name='repaired',rules=rules,strategy_key=old['strategy_key'])
    p.approve(new['strategy_key'],new['version_id'],approved_by='fixture')
    p=CustomStrategyPipeline(storage_path=path)
    assert p.get_version(old['strategy_key'],old['version_id'])==before
    assert p.start_paper_observation(new['strategy_key'],new['version_id'])['status']=='paper_observing'
    edited=deepcopy(rules);edited['numeric_state']['updates']['counter']='counter + 100'
    assert not ApplicationServices.validate_strategy_draft(None,rules=edited)['ready']

@pytest.mark.parametrize('venue',VENUES)
def test_state_source_to_candles_to_actual_decision_and_mode_isolation(tmp_path,venue):
    rules=source_rules();item={'rules':rules,'version_id':'v1','strategy_key':'s1','target_scope':'all','market_conditions':['all']}
    now=int(datetime.now(timezone.utc).timestamp())
    rows=[[(now-(610-i)*900)*1000,100,101,99,100,10] for i in range(605)]
    store=NumericStateStore(tmp_path/'state.sqlite3');scope={'venue':venue,'symbol':'BTC','mode':'live'}
    def ctx(end):return enrich_advanced_indicator_context({'signal':'LONG'},[item],lambda tf,n:rows[:end][-n:],state_scope=scope,state_store=store)
    a=ctx(603);key=identity(rules,item)
    assert a['_numeric_state_results'][key]['values']['counter']==1
    assert ctx(603)['_numeric_state_results'][key]['values']['counter']==1
    b=ctx(604);b['_numeric_state_identity']=key
    assert Engine.evaluate_entry(rules,b)['allowed']
    assert not Engine.evaluate_entry(rules,a)['allowed']
    independent=enrich_states(dict(b),[item],{**scope,'mode':'paper'},store)
    assert independent['_numeric_state_results'][key]['values']['counter']==1


def test_replay_state_is_isolated_and_deterministic():
    rules=source_rules();now=int(datetime.now(timezone.utc).timestamp())
    rows=[[(now-(320-i)*900)*1000,100,100.1,99.9,100,10] for i in range(310)]
    a=run_historical_replay(rules,rows,horizon=3)
    b=run_historical_replay(rules,rows,horizon=3)
    assert a['decisions']>0
    for key in ('decisions','net_pnl_percent','trades'):assert a[key]==b[key]


@pytest.mark.parametrize('venue',['kis','kiwoom','shinhan','mirae'])
@pytest.mark.parametrize('is_etf',[False,True])
def test_stock_actual_exit_uses_entry_state_and_frozen_version(tmp_path,venue,is_etf):
    from types import SimpleNamespace
    from trading.stock_analysis_service import StockAnalysisService
    svc=StockAnalysisService.__new__(StockAnalysisService);svc.broker_name=venue
    rules=StrategySourceIngestor().analyze(SOURCE.replace('15m','1d'),kind='text')['rules']
    item={'rules':rules,'strategy_key':'s1','version_id':'v1'}
    rows=[{'date':(datetime.now(timezone.utc)-timedelta(days=700-i)).strftime('%Y%m%d'),
           'open':100,'high':101,'low':99,'close':100,'volume':10} for i in range(610)]
    end=[603];svc.adapter=SimpleNamespace(get_daily_candles=lambda symbol,limit:rows[:end[0]][-limit:])
    recorder=SimpleNamespace(db_path=str(tmp_path/'account.sqlite3'));svc._get_recorder=lambda:recorder
    analysis={'status':'ok','current_price':100,'signal':'BUY','is_etf':is_etf}
    for count in range(600,604):
        end[0]=count;svc._enrich_strategy_context(dict(analysis),[item],'005930','live')
    svc._confirmed_positions=lambda:[{'symbol':'005930','quantity':1,'pnl_rate':0,'is_etf':is_etf}]
    svc.analyze_symbol=lambda symbol:dict(analysis)
    svc._restore_custom_exit_plan=lambda symbol:{**item,'strategy_name':'counter','strategy_version_id':'v1'}
    def run():return svc._run_auto_exit_cycle(asset_mode='all',allow_live_order=False,execution_mode='live',
        remaining_order_budget=1,exit_policy={'enable_exit_policy':True,'take_profit_percent':99,'stop_loss_percent':99},market_regime='range')
    assert run()==([],0)  # Same completed bar: no fifth increment.
    end[0]=604
    decisions,orders=run()
    assert orders==0 and decisions[0]['exit_reason']=='custom_exit:counter:v1'
    assert run()==(decisions,orders)  # Repeat must neither reset nor double-advance.


def test_parallel_paper_state_restart_does_not_share_live(tmp_path,monkeypatch):
    import trading.parallel_strategy_paper as module
    from test_v39122_parallel_strategy_paper import _settings,_strategy
    monkeypatch.setattr(module,'get_app_data_dir',lambda:tmp_path)
    monkeypatch.setattr(module,'record_paper_strategy_outcome',lambda **kw:kw)
    engine=module.ParallelStrategyPaperEngine(settings_provider=_settings)
    rules=source_rules();item={**_strategy(),'rules':rules}
    def observe(instance,i):
        ctx={'signal':'LONG','current_price':100,'_strategy_timeframe_contexts':{'15m':{'_closed_bar_contexts':[bar(n) for n in range(1,i+1)]}}}
        return instance.observe(target='binance',symbol='BTCUSDT',asset_class='crypto',primary_execution_mode='live',context=ctx,strategy_pool=[item],market_regime='range')
    assert observe(engine,1)['opened']==0
    engine=module.ParallelStrategyPaperEngine(settings_provider=_settings)
    assert observe(engine,1)['opened']==0
    assert observe(engine,2)['opened']==1
    assert observe(engine,3)['closed']==0
    assert observe(engine,5)['closed']==1


@pytest.mark.parametrize('source',[SOURCE.replace('STATE counter','STATE Counter'),SOURCE.replace('ENTRY:','WRONG:'),SOURCE.replace('UPDATE counter','UPDATE missing')])
def test_malformed_state_never_silently_dropped(source):
    assert not StrategySourceIngestor().analyze(source,kind='text')['ready_for_execution']

@pytest.mark.parametrize('venue',VENUES)
def test_same_order_shared_records_exact_original_quantities(tmp_path,venue):
    r,target,rows=shared_case(tmp_path,venue)
    with sqlite3.connect(r.db_path) as db:
        db.execute("UPDATE trade_log SET order_id='entry-1' WHERE order_id='entry-2'")
    records=r.execute_query('SELECT id,entry_price FROM trade_log ORDER BY id');a,b=[str(t[0]) for t in records]
    rows[1]['order_id']='entry-1'
    rows[0]['ledger_allocations']={a:'2'};rows[1]['ledger_allocations']={b:'2'}
    rows[-1]['ledger_allocations']={a:'2',b:'2'}
    encoded=[{**row,'ledger_allocations':json.dumps(row['ledger_allocations'])} for row in rows]
    commit(r,payload(venue,encoded))
    job=RecordRecovery(r,RecoveryResolver(r,None,venue),delay=0)
    result=job.start(venue,background=False)
    assert result['recovered']==2 and result['remaining']==0,result
    saved=r.execute_query('SELECT * FROM trade_log');job.now=lambda:datetime.now().timestamp()+31
    assert job.start(venue,background=False)['total']==0
    assert r.execute_query('SELECT * FROM trade_log')==saved

@pytest.mark.parametrize('venue',VENUES)
@pytest.mark.parametrize('flat_between',[False,True])
def test_same_order_fills_interleave_with_its_exits(tmp_path,venue,flat_between):
    r,tid,rows,_,_=prepared(tmp_path,venue)
    start=datetime.fromisoformat(rows[0]['timestamp']);stamp=lambda seconds:(start+timedelta(seconds=seconds)).isoformat()
    entry={**rows[0],'quantity':'1'}
    first={**rows[-1],'quantity':'1' if flat_between else '.5','timestamp':stamp(10)}
    second={**entry,'execution_id':'entry-again','timestamp':stamp(20)}
    last={**rows[-1],'execution_id':'exit-again','quantity':'1' if flat_between else '1.5','timestamp':stamp(30)}
    commit(r,payload(venue,[entry,first,second,last]))
    result=RecordRecovery(r,RecoveryResolver(r,None,venue),delay=0).start(venue,background=False)
    assert result['recovered']==1 and result['remaining']==0,result
    assert not result['auto_started']
