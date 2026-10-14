"""Public .13 feedback: real broker candle contract, PAPER and Studio pause."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from trading.stock_analysis_service import StockAnalysisService

KST=timezone(timedelta(hours=9))

def candles(n=40):
    return [dict(date=(datetime(2026,8,1)+timedelta(days=i)).strftime('%Y%m%d'),open=100+i,high=102+i,low=99+i,close=101+i,volume=1000+i) for i in range(n)]

class DailyAdapter:
    api_type='mock'
    exchange_name='test'
    def get_stock_list(self,market):return [{'code':'005930','market':market,'status':'normal'}]
    def get_etf_list(self):return []
    def get_daily_candles(self,symbol,limit=100):return candles()
    def get_stock_info(self,symbol):return dict(name='fixture',current_price=160,prev_close=150,volume=5000,is_etf=False)
    def get_realtime_price(self,symbol):return dict(current_price=160,volume=5000)
    def is_etf(self,symbol):return False

def test_actual_broker_candles_reach_analysis_without_trade_history(tmp_path):
    svc=StockAnalysisService(DailyAdapter(),broker_name='kis',paper_settings={})
    with patch.object(svc,'get_market_regime',return_value='bull'),patch.object(svc,'_get_recent_trade_feedback',return_value={'pnl_rate':0,'trade_count':0,'win_rate':0}),patch.object(svc,'_persist_xai_decision'):
        result=svc.analyze_symbol('005930')
    assert result['status']=='ok'
    assert result['ma20']>0
    assert result['technical_history']['bars']==40
    assert result['technical_history']['source']=='get_daily_candles'
    assert result['technical_history']['average_volume']>0
    assert result['feedback_trade_count']==0

@pytest.mark.parametrize('broker',['kiwoom','kis','mirae','shinhan'])
def test_common_history_contract_all_brokers(broker):
    svc=StockAnalysisService(DailyAdapter(),broker_name=broker,paper_settings={})
    prices,evidence=svc._load_analysis_history('005930',now=datetime(2026,10,14,10,tzinfo=KST))
    assert len(prices)==40 and prices==sorted(prices)
    assert evidence['status']=='ready'


def test_history_is_completed_ordered_and_does_not_invent_invalid_bars():
    rows=candles()+[dict(date='20261014',close=999,volume=2000),dict(date='20261015',close=9999,volume=3000)]
    svc=StockAnalysisService(SimpleNamespace(get_daily_candles=lambda *a,**k:list(reversed(rows))),broker_name='kis',paper_settings={})
    prices,evidence=svc._load_analysis_history('005930',now=datetime(2026,10,14,10,tzinfo=KST))
    assert prices==[float(r['close']) for r in candles()]
    assert evidence['bars']==40

@pytest.mark.parametrize('rows',[[],[dict(date='bad',close=1)], [dict(date='20261013',close=float('nan'))], [dict(date='20261013',close=0)], [dict(date='20261013',close=1),dict(date='20261013',close=2)]])
def test_missing_or_invalid_history_is_explicit_not_zero(rows):
    svc=StockAnalysisService(SimpleNamespace(get_daily_candles=lambda *a,**k:rows),broker_name='kis',paper_settings={})
    prices,evidence=svc._load_analysis_history('005930',now=datetime(2026,10,14,10,tzinfo=KST))
    assert not prices
    assert evidence['status']!='ready'
    assert evidence['average_volume'] is None


def prepared_pipeline(tmp_path):
    from trading.custom_strategy_pipeline import CustomStrategyPipeline
    p=CustomStrategyPipeline(str(tmp_path/'strategies.json'))
    v=p.submit(name='fixture',rules={'entry':'RSI < 30','exit':'MACD dead cross','stop_loss':1.0,'take_profit':2.0,'position_size':0.05,'market_conditions':['trend','range']})
    p.approve(v['strategy_key'],v['version_id'],approved_by='fixture')
    return p,v


def test_period_goal_is_neither_promotion_nor_paper_start_gate(tmp_path):
    p,v=prepared_pipeline(tmp_path);k,vid=v['strategy_key'],v['version_id']
    started=p.start_paper_observation(k,vid)
    assert started['status']=='paper_observing'
    incomplete=p.record_paper_validation(k,vid,trades=2,metrics={'require_forward_days':True,'observation_days':7.0})
    assert not incomplete['paper_validation']['passed']
    with pytest.raises(ValueError):p.activate(k,vid,live_confirmation=True)
    complete=p.record_paper_validation(k,vid,trades=3,metrics={'require_forward_days':True,'observation_days':0.01})
    assert complete['paper_validation']['passed']
    with pytest.raises(ValueError):p.activate(k,vid,live_confirmation=False)


def test_validated_strategy_deactivation_restart_and_reactivation_preserve_evidence(tmp_path):
    from trading.custom_strategy_pipeline import CustomStrategyPipeline
    p,v=prepared_pipeline(tmp_path);k,vid=v['strategy_key'],v['version_id']
    p.start_paper_observation(k,vid)
    p.record_paper_validation(k,vid,trades=3,metrics={'require_forward_days':True,'observation_days':7.0})
    before=p.get_version(k,vid)['paper_validation']
    p.activate(k,vid,live_confirmation=True)
    p.deactivate(k,vid,approved_by='fixture')
    restored=CustomStrategyPipeline(str(tmp_path/'strategies.json'))
    assert not restored.active_versions
    assert restored.get_version(k,vid)['paper_validation']==before
    with pytest.raises(ValueError):restored.activate(k,vid,live_confirmation=True,guardrail_check=lambda v:False)
    restored.activate(k,vid,live_confirmation=True)
    assert restored.active_versions[k]==vid
    assert restored.get_version(k,vid)['paper_validation']==before


def test_diagnosis_explains_score_and_history_without_claiming_data_wait():
    from trading.stock_runtime_controller import stock_cycle_diagnosis
    msg=stock_cycle_diagnosis({'effective_buy_threshold':70,'decisions':[{'reason':'threshold_not_met','score':43,'technical_history':{'bars':0,'status':'unavailable'}}]})
    assert '43.0' in msg and '70.0' in msg and '일봉 0개' in msg
    assert '데이터를 쌓' not in msg


def test_offline_support_answers_the_feedback_questions():
    from config.assistant_support_knowledge import support_topic
    for q in ['전략 7일 기다림은 왜 있나요?', '검증된 전략 일시 적용 일시 정지가 가능한가요?', '코인과 주식 날짜 제한은 왜 있나요?']:
        answer=support_topic(q)
        assert answer and answer.key=='studio_wait_pause'
        assert '최소 3건' in answer.ko and '기관 거래 정지' in answer.ko
        assert '3거래일' in answer.ko and '결과 점검 시점' in answer.ko
    assert support_topic('증권사 거래가 안 이루어져요').key=='stock_no_trade'


def test_history_cache_is_scoped_and_expires_without_stale_error_fallback(monkeypatch):
    calls=[];bad=[False]
    def getter(*a,**k):
        calls.append(1)
        if bad[0]:raise TimeoutError('fixture')
        return candles()
    svc=StockAnalysisService(SimpleNamespace(get_daily_candles=getter),broker_name='kis')
    now=datetime(2026,10,14,10,tzinfo=KST)
    with patch('trading.stock_analysis_service.pytime.monotonic',return_value=1):
        assert svc._load_analysis_history('005930',now=now)[0]
        assert svc._load_analysis_history('005930',now=now)[0]
    assert len(calls)==1
    bad[0]=True
    with patch('trading.stock_analysis_service.pytime.monotonic',return_value=62):
        prices,evidence=svc._load_analysis_history('005930',now=now)
    assert prices is None and evidence['status']=='unavailable'


@pytest.mark.parametrize('broker',['kiwoom','kis'])
def test_zero_personal_history_can_place_paper_order_without_broker_order(tmp_path, monkeypatch, broker):
    from unittest.mock import Mock
    adapter=DailyAdapter()
    adapter.place_order=Mock(side_effect=AssertionError('PAPER must not call broker order'))
    adapter.get_etf_list=lambda:[]
    adapter.get_stock_list=lambda market:[{'code':'005930','status':'normal','market':market}]
    adapter.get_balance=lambda:{'total_equity':10000000,'cash_balance':10000000}
    adapter.get_positions=lambda:[]
    adapter.get_stock_info=lambda s:dict(current_price=160,prev_close=150,volume=10000,foreign_net_buy=2000000000,is_etf=False)
    # The existing threshold is kept; deliberately strong synthetic bars isolate routing.
    # A crossover in the fixture gives the existing 15-point crossover contribution.
    adapter.get_daily_candles=lambda *a,**k:[{**row,'close':p} for row,p in zip(candles(21),[1000]+[100]*5+[1000]+[1]+[20+20*i for i in range(13)])]
    svc=StockAnalysisService(adapter,broker_name=broker,paper_settings={'paper_position_store_path_stock':str(tmp_path/'positions.json')})
    svc._get_recent_paper_trade_samples=lambda **k:[]
    with patch.object(svc,'get_market_regime',return_value='range'),patch.object(svc,'_get_recent_trade_feedback',return_value={'pnl_rate':0,'trade_count':0,'win_rate':0}),patch.object(svc,'_persist_xai_decision'):
        result=svc.run_auto_trade_cycle(symbols=['005930'],buy_threshold=70,execution_mode_override='paper',allow_live_order=False,guardrails={'enabled':False},auto_risk_policy={'strategy_engine':{'enabled':False}},exit_policy={'enable_exit_policy':False})
    assert result['execution_mode']=='paper'
    assert result['orders_executed']==1, result['decisions']
    adapter.place_order.assert_not_called()


def test_deactivating_strategy_keeps_existing_paper_exit_plan(tmp_path):
    p,v=prepared_pipeline(tmp_path);k,vid=v['strategy_key'],v['version_id']
    p.start_paper_observation(k,vid)
    p.record_paper_validation(k,vid,trades=3,metrics={'require_forward_days':True,'observation_days':7.0})
    p.activate(k,vid,live_confirmation=True)
    svc=StockAnalysisService(DailyAdapter(),broker_name='kis',paper_settings={'paper_position_store_path_stock':str(tmp_path/'positions.json')})
    opened,_,errors=svc._place_paper_stock_order(symbol='005930',side='BUY',quantity=1,price=100,order_type='MARKET')
    assert opened, errors
    plan={'strategy_key':k,'strategy_version_id':vid,'engine_settings':{'tp_percent':0.02,'sl_percent':0.01},'rules':v['rules']}
    svc._custom_exit_plans()['005930']=plan
    p.deactivate(k,vid,approved_by='fixture')
    assert svc._restore_custom_exit_plan('005930')==plan
    svc._record_stock_paper_outcome=lambda **kwargs:True
    with patch.object(svc,'analyze_symbol',return_value={'status':'ok','current_price':110,'is_etf':False,'signal':'HOLD'}),patch.object(svc,'_persist_xai_decision'):
        decisions,orders=svc._run_auto_exit_cycle(asset_mode='all',allow_live_order=False,execution_mode='paper',remaining_order_budget=1,exit_policy={'enable_exit_policy':True},market_regime='range')
    assert orders==1 and not svc._paper_positions(), decisions


@pytest.mark.parametrize('price,orders',[(110,1),(90,1),(100,0)])
@pytest.mark.parametrize('broker',['kiwoom','kis'])
def test_paper_tp_sl_receives_actual_net_percentage(tmp_path,price,orders,broker):
    svc=StockAnalysisService(DailyAdapter(),broker_name=broker,paper_settings={'paper_position_store_path_stock':str(tmp_path/'positions.json')})
    ok,_,errors=svc._place_paper_stock_order(symbol='005930',side='BUY',quantity=1,price=100,order_type='MARKET')
    assert ok,errors
    svc._record_stock_paper_outcome=lambda **k:True
    with patch.object(svc,'analyze_symbol',return_value={'status':'ok','current_price':price,'is_etf':False}),patch.object(svc,'_persist_xai_decision'):
        decisions,executed=svc._run_auto_exit_cycle(asset_mode='all',allow_live_order=False,execution_mode='paper',remaining_order_budget=1,exit_policy={'enable_exit_policy':True,'take_profit_percent':5,'stop_loss_percent':5},market_regime='range')
    assert executed==orders,decisions
    assert bool(svc._paper_positions()) == (orders==0)


def test_unverified_paper_exit_value_preserves_position(tmp_path):
    svc=StockAnalysisService(DailyAdapter(),broker_name='kis',paper_settings={'paper_position_store_path_stock':str(tmp_path/'positions.json')})
    ok,_,errors=svc._place_paper_stock_order(symbol='005930',side='BUY',quantity=1,price=100,order_type='MARKET')
    assert ok,errors
    with patch.object(svc,'analyze_symbol',return_value={'status':'ok','current_price':110}),patch.object(svc,'_refresh_paper_position_valuation',return_value={'calculation_status':'invalid'}):
        decisions,orders=svc._run_auto_exit_cycle(asset_mode='all',allow_live_order=False,execution_mode='paper',remaining_order_budget=1,exit_policy={'enable_exit_policy':True})
    assert orders==0 and svc._paper_positions()['005930']['quantity']==1
    assert decisions[0]['reason']=='paper_exit_valuation_unavailable'


def test_legacy_numeric_history_and_conflicting_volume_are_handled_explicitly():
    now=datetime(2026,10,14,10,tzinfo=KST)
    legacy=StockAnalysisService(SimpleNamespace(get_price_history=lambda *a,**k:list(range(1,22))),broker_name='kis')
    prices,evidence=legacy._load_analysis_history('005930',now=now)
    assert prices==list(range(1,22)) and evidence['source']=='get_price_history'
    rows=candles(20);rows.append({**rows[-1],'volume':999999})
    conflict=StockAnalysisService(SimpleNamespace(get_daily_candles=lambda *a,**k:rows),broker_name='kis')
    assert conflict._load_analysis_history('005930',now=now)[0] is None


def test_worker_publishes_the_current_inactivity_diagnosis(monkeypatch):
    import threading
    from trading.stock_runtime_controller import StockRuntimeController
    controller=StockRuntimeController(settings_provider=lambda:{})
    stopped=threading.Event();messages=[]
    def run_once(broker):
        stopped.set()
        return {'execution_mode':'paper','candidate_count':1,'orders_executed':0,'effective_buy_threshold':70,'decisions':[{'reason':'threshold_not_met','score':43,'technical_history':{'bars':20,'status':'ready'}}]},60
    controller._run_once=run_once
    monkeypatch.setattr('trading.runtime_observability.emit_runtime_status',lambda owner,broker,key,message,**kw:messages.append((key,message)))
    controller._worker('kis',stopped)
    cycle=next(item for item in messages if isinstance(item[0],tuple))
    assert '43.0 / 매수 기준 70.0' in cycle[1]
    assert '완료 일봉 20개' in cycle[1]
    assert '43.0' in str(cycle[0])


@pytest.mark.parametrize('requested',[20,220,500])
def test_kis_pages_past_official_hundred_bar_limit(requested):
    from trading.exchanges.adapters.korea_investment_stock_adapter import KoreaInvestmentStockAdapter
    adapter=KoreaInvestmentStockAdapter.__new__(KoreaInvestmentStockAdapter)
    adapter.is_connected=True;adapter.sandbox=True
    history=candles(500);requests=[]
    def get(path,params):
        requests.append(params['FID_INPUT_DATE_2'])
        return {'output2':list(reversed([r for r in history if r['date']<=params['FID_INPUT_DATE_2']]))[:100]}
    # Keep all fixture dates before today while preserving a 500-row request boundary.
    start=datetime(2024,1,1)
    for n,row in enumerate(history):row['date']=(start+timedelta(days=n)).strftime('%Y%m%d')
    adapter._get=get
    with patch('trading.exchanges.adapters.korea_investment_stock_adapter.time.sleep') as paced:
        rows=adapter.get_daily_candles('005930',requested)
    assert len(rows)==requested
    assert [r['date'] for r in rows]==sorted(r['date'] for r in rows)
    assert len(requests)==(requested+99)//100
    assert len(set(requests))==len(requests)
    assert paced.call_count==len(requests)-1


def test_kis_failed_or_repeated_page_is_not_silently_complete():
    from trading.exchanges.adapters.korea_investment_stock_adapter import KoreaInvestmentStockAdapter
    adapter=KoreaInvestmentStockAdapter.__new__(KoreaInvestmentStockAdapter)
    adapter.is_connected=True;adapter.sandbox=False
    first=candles(100)
    for second in ({}, {'output2':first}):
        responses=iter([{'output2':first},second]);adapter._get=lambda *a,**k:next(responses)
        with patch('trading.exchanges.adapters.korea_investment_stock_adapter.time.sleep'),pytest.raises(ValueError):
            adapter.get_daily_candles('005930',220)


@pytest.mark.parametrize('explicit,master,expected,source',[
    (None,'71100',71100.0,'GetMasterLastPrice'),
    ('71100','50000',71100.0,'quote'),
    ('-71100','50000',71100.0,'quote'),
    ('0','-71100',71100.0,'GetMasterLastPrice'),
    (None,'nan',None,'unavailable'),
    (None,'0',None,'unavailable'),
    (None,RuntimeError('fixture'),None,'unavailable'),
])
def test_kiwoom_missing_quote_previous_close_uses_documented_master_method(explicit,master,expected,source):
    from trading.exchanges.adapters.kiwoom_stock_adapter import KiwoomStockAdapter
    from unittest.mock import Mock
    record={'현재가':'72000','거래량':'1234','등락율':'1.25'}
    if explicit is not None:record['전일종가']=explicit
    getter=Mock(side_effect=master) if isinstance(master,Exception) else Mock(return_value=master)
    backend=SimpleNamespace(GetMasterCodeName=lambda s:'fixture',GetMasterLastPrice=getter,block_request=lambda *a,**k:[record])
    adapter=KiwoomStockAdapter('','','',backend_client=backend)
    adapter.is_connected=True
    info=adapter.get_stock_info('005930')
    assert info['status']=='ok'
    assert info['prev_close']==expected
    assert info['prev_close_source']==source
    if source=='quote':getter.assert_not_called()


def test_kiwoom_master_price_reaches_momentum_analysis_without_personal_trades():
    from trading.exchanges.adapters.kiwoom_stock_adapter import KiwoomStockAdapter
    backend=SimpleNamespace(GetMasterCodeName=lambda s:'fixture',GetMasterLastPrice=lambda s:'150',block_request=lambda *a,**k:[{'현재가':'160','거래량':'5000','등락율':'6.67'}])
    adapter=KiwoomStockAdapter('','','',backend_client=backend)
    adapter.is_connected=True
    adapter.get_daily_candles=lambda *a,**k:candles()
    svc=StockAnalysisService(adapter,broker_name='kiwoom')
    with patch.object(svc,'get_market_regime',return_value='range'),patch.object(svc,'_get_recent_trade_feedback',return_value={'pnl_rate':0,'trade_count':0,'win_rate':0}),patch.object(svc,'_persist_xai_decision'):
        result=svc.analyze_symbol('005930')
    assert result['status']=='ok'
    assert result['momentum']==6.67
    assert result['prev_close_source']=='GetMasterLastPrice'
