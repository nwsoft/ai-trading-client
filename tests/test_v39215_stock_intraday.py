"""Synthetic provider/IPC/strategy tests; no credentials, real orders or OCX."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from trading.stock_candles import KST, candle, aggregate_minutes, completed
from trading.exchanges.adapters.kiwoom_stock_adapter import KiwoomStockAdapter
from trading.exchanges.adapters.korea_investment_stock_adapter import KoreaInvestmentStockAdapter


def minute_rows(day='20261013', count=390):
    dt=datetime.strptime(day+'090000','%Y%m%d%H%M%S')
    return [candle((dt+timedelta(minutes=i)).strftime('%Y%m%d%H%M%S'),
                   {'open':100+i*.1,'high':101+i*.1,'low':99+i*.1,'close':100.5+i*.1,'volume':10}) for i in range(count)]


@pytest.mark.parametrize('tf,n',[('1m',390),('3m',130),('5m',78),('15m',26),('30m',13),('1h',7)])
def test_exact_timeframe_session_alignment_and_volume(tf,n):
    rows=aggregate_minutes(minute_rows(),tf)
    assert len(rows)==n and rows[0]['open']==100 and rows[-1]['close']==139.4
    assert sum(r['volume'] for r in rows)==3900
    assert datetime.fromtimestamp(rows[0]['timestamp'],KST).hour==9
    assert datetime.fromtimestamp(rows[-1]['close_timestamp'],KST).strftime('%H%M')=='1530'


def test_incomplete_missing_and_cross_day_bars_are_not_fabricated():
    rows=minute_rows(count=10)
    assert len(aggregate_minutes(rows,'5m',now=rows[7]['timestamp']))==1
    assert len(aggregate_minutes(rows[:2]+rows[3:],'5m'))==1
    assert len(aggregate_minutes(minute_rows(count=3)+minute_rows('20261014',count=2),'5m'))==0
    with pytest.raises(ValueError,match='conflicting'):
        completed([rows[0],{**rows[0],'close':100.7}])


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),0,'broken'])
def test_invalid_prices_are_rejected(bad):
    with pytest.raises(ValueError):
        candle('20261013090000',{'open':bad,'high':102,'low':99,'close':101,'volume':1})


def test_non_krx_session_and_unsupported_timeframe():
    for ts in ('20261013085900','20261013153000','20261017090000'):
        assert candle(ts,dict(open=100,high=101,low=99,close=100,volume=1)) is None
    with pytest.raises(ValueError,match='unsupported'):
        aggregate_minutes([],'2h')


def test_kiwoom_native_minutes_pagination_completion_and_cache():
    def page(offset):
        return [{'체결시간':(datetime(2026,10,13,9)+timedelta(minutes=3*i)).strftime('%Y%m%d%H%M%S'),
                 '시가':'-100','고가':'-102','저가':'-99','현재가':'-101','거래량':'10'} for i in range(offset,offset+45)]
    backend=SimpleNamespace(block_request=Mock(side_effect=[page(45),page(0)]),tr_remained=True)
    a=KiwoomStockAdapter('synthetic','','',backend_client=backend);a.is_connected=True
    rows=a.get_intraday_candles('005930','3m',80)
    assert len(rows)==80 and rows[0]['timestamp']<rows[-1]['timestamp']
    assert [c.kwargs['next'] for c in backend.block_request.call_args_list]==[0,2]
    assert all(c.kwargs['틱범위']=='3' and c.args[0]=='opt10080' for c in backend.block_request.call_args_list)
    assert a.get_intraday_candles('005930','3m',80)==rows
    assert backend.block_request.call_count==2


def test_kiwoom_failed_page_never_returns_partial_success():
    b=SimpleNamespace(block_request=Mock(side_effect=TimeoutError('synthetic')),tr_remained=True)
    a=KiwoomStockAdapter('synthetic','','',backend_client=b);a.is_connected=True
    with pytest.raises(TimeoutError):a.get_intraday_candles('005930','5m')
    assert not a._intraday_cache


def kis(sandbox=False):
    a=KoreaInvestmentStockAdapter('synthetic','','',sandbox=sandbox)
    a.is_connected=True
    return a


def provider_rows(rows):
    return [{'stck_bsop_date':datetime.fromtimestamp(r['timestamp'],KST).strftime('%Y%m%d'),
             'stck_cntg_hour':datetime.fromtimestamp(r['timestamp'],KST).strftime('%H%M%S'),
             'stck_oprc':r['open'],'stck_hgpr':r['high'],'stck_lwpr':r['low'],
             'stck_prpr':r['close'],'cntg_vol':r['volume']} for r in reversed(rows)]


def test_kis_incremental_history_pagination_reused_between_timeframes(monkeypatch):
    import trading.kis_intraday_history as m
    monkeypatch.setattr(m.time,'sleep',lambda _:None)
    a=kis();allrows=minute_rows('20261012')+minute_rows()
    a._get=Mock(side_effect=[{'rt_cd':'0','output2':provider_rows(allrows[i:j])} for i,j in [(660,780),(540,660),(420,540),(300,420)]])
    result=a.get_intraday_candles('005930','5m',100)
    assert len(result)==96 and a._get.call_count==4
    assert a.last_history_issue=='intraday_history_warming_or_insufficient'
    cursors=[c.kwargs['params']['FID_INPUT_DATE_1']+c.kwargs['params']['FID_INPUT_HOUR_1'] for c in a._get.call_args_list]
    assert cursors==sorted(cursors,reverse=True)
    assert a._tr_id(a._get.call_args.args[0],method='GET')=='FHKST03010230'
    assert len(a.get_intraday_candles('005930','3m',100))==100 and a._get.call_count==4


def test_kis_bad_page_is_not_masked_by_cached_history(monkeypatch):
    import trading.kis_intraday_history as m
    monkeypatch.setattr(m.time,'sleep',lambda _:None)
    a=kis();a._get=Mock(return_value={'rt_cd':'1','output2':[]})
    with pytest.raises(ValueError,match='page_unavailable'):
        a.get_intraday_candles('005930','5m')


def test_kis_nonadvancing_cursor_rejected(monkeypatch):
    import trading.kis_intraday_history as m
    monkeypatch.setattr(m.time,'sleep',lambda _:None)
    a=kis();a._get=Mock(return_value={'rt_cd':'0','output2':provider_rows(minute_rows())})
    with pytest.raises(ValueError,match='cursor_ignored'):
        a.get_intraday_candles('005930','1h',200)


def test_kis_demo_is_current_day_only_no_silent_real_server_switch(monkeypatch):
    import trading.kis_intraday_history as m
    class FixedDate(datetime):
        @classmethod
        def now(cls,tz=None):return cls(2026,10,13,16,tzinfo=KST)
    monkeypatch.setattr(m,'datetime',FixedDate);monkeypatch.setattr(m.time,'sleep',lambda _:None)
    a=kis(True);a._get=Mock(return_value={'rt_cd':'0','output2':provider_rows(minute_rows())})
    rows=a.get_intraday_candles('005930','5m',80)
    assert len(rows)==78 and a.last_history_issue
    assert all(c.args[0].endswith('inquire-time-itemchartprice') for c in a._get.call_args_list)
    assert a._tr_id(a._get.call_args.args[0],method='GET')=='FHKST03010200'
    assert 'FID_INPUT_DATE_1' not in a._get.call_args.kwargs['params']


def test_proxy_transports_timeframe_limit_without_order_calls():
    from trading.exchanges.adapters.kiwoom_process_proxy import KiwoomProcessProxy
    p=KiwoomProcessProxy('synthetic','','');p._call=Mock(return_value=[])
    assert p.get_intraday_candles('005930','15m',205)==[]
    p._call.assert_called_once_with('get_intraday_candles','005930','15m',205)


def test_stock_context_routes_exact_minutes_daily_and_exit_state_scope():
    from trading.stock_analysis_service import StockAnalysisService
    a=Mock();a.get_intraday_candles.return_value=aggregate_minutes(minute_rows()+minute_rows('20261014'),'3m')
    s=StockAnalysisService(a,broker_name='kiwoom',recorder=Mock());s._get_recorder=lambda:None
    r=s._enrich_strategy_context({'signal':'LONG'},[{'rules':{'decision_timeframe':'3m'}}],'005930','paper')
    assert '3m' in r['_strategy_timeframe_contexts']
    a.get_intraday_candles.assert_called_once_with('005930','3m',205)
    a.get_daily_candles.assert_not_called();a.place_order.assert_not_called()


def test_read_probe_reports_warming_and_failure_without_private_text():
    from scripts.probe_stock_intraday import inspect
    a=SimpleNamespace(get_intraday_candles=Mock(side_effect=[minute_rows(count=3),RuntimeError('private-secret')]))
    result=inspect(a,'005930',['3m','5m'])
    assert [r['status'] for r in result]==['WARMING_OR_INSUFFICIENT','FAIL_READ']
    assert 'private' not in str(result)


def test_negative_volume_never_becomes_valid_evidence():
    with pytest.raises(ValueError,match='invalid_stock_intraday'):
        candle('20261013090000',dict(open=100,high=101,low=99,close=100,volume=-1))


def test_partial_fetch_history_explained_without_adapter_private_messages():
    from trading.custom_strategy_validator import enrich_advanced_indicator_context
    def failure(*args):raise TimeoutError('private-provider-response')
    out=enrich_advanced_indicator_context({}, {'decision_timeframe':'5m'},failure)
    assert out['_strategy_timeframe_history']['5m']['status']=='fetch_failed'
    assert out['_strategy_timeframe_history']['5m']['error_type']=='TimeoutError'
    assert 'private' not in str(out)


def test_read_probe_has_no_order_mutation_calls():
    import ast
    from pathlib import Path
    tree=ast.parse(Path('scripts/probe_stock_intraday.py').read_text())
    attrs={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
    assert not attrs & {'place_order','cancel_order','SendOrder','_post','close_position','save_settings'}


@pytest.mark.usefixtures('listed_instrument_transport')
@pytest.mark.parametrize('broker',['kiwoom','kis'])
@pytest.mark.parametrize('read_fails',[False,True])
def test_real_stock_cycle_delivers_intraday_context_to_paper_observer_without_live_orders(broker,read_fails):
    from tests.test_stock_analysis_service import _make_mock_adapter
    from trading.stock_analysis_service import StockAnalysisService
    from unittest.mock import patch
    a=_make_mock_adapter();a.api_type='real'
    a.get_intraday_candles=Mock(side_effect=TimeoutError('synthetic') if read_fails else None,
                                return_value=aggregate_minutes(minute_rows()+minute_rows('20261014'),'3m'))
    s=StockAnalysisService(a,broker_name=broker,recorder=Mock());s._get_recorder=lambda:None
    s._persist_paper_positions=lambda:None;s._restore_paper_positions=lambda:None
    s._paper_positions().clear();s._get_recent_paper_trade_samples=lambda limit=50:[]
    observer=Mock();s.parallel_paper_observer=observer
    s.paper_validation_strategy_pool=[{'rules':{'target_scope':'asset:stock','decision_timeframe':'3m'}},
        {'rules':{'target_scope':'asset:crypto','decision_timeframe':'2h'}},
        {'rules':{'target_scope':'broker:shinhan','decision_timeframe':'15m'}}]
    analysis={'status':'ok','symbol':'005930','score':55,'momentum':0,'current_price':100,
              'is_etf':False,'rsi':45,'trend':'range','technical_history':{'status':'ready','bars':220}}
    with patch.object(s,'get_market_regime',return_value='range'),patch.object(s,'analyze_symbol',return_value=analysis):
        result=s.run_auto_trade_cycle(symbols=['005930'],quantity=1,max_orders=1,allow_live_order=False,
            execution_mode_override='paper',guardrails={'enabled':False},exit_policy={'enable_exit_policy':False},
            auto_risk_policy={'profitability_validation':{'enabled':False},'strategy_engine':{'enabled':False}})
    assert result['execution_mode']=='paper' and result['orders_executed']==0
    ctx=observer.observe.call_args.kwargs['context']
    assert ('3m' in ctx['_strategy_timeframe_contexts']) is not read_fails
    assert observer.observe.call_args.kwargs['primary_execution_mode']=='paper'
    assert observer.observe.call_args.kwargs['target']==broker
    assert len(observer.observe.call_args.kwargs['strategy_pool'])==1
    a.get_intraday_candles.assert_called_once_with('005930','3m',205)
    a.place_order.assert_not_called()


@pytest.mark.parametrize('status,label',[('fetch_failed','조회 실패'),('insufficient_history','수집 중·부족')])
def test_stock_runtime_explains_actual_timeframe_bar_progress(status,label):
    from trading.stock_runtime_controller import stock_cycle_diagnosis
    report={'decisions':[{'reason':'custom_strategy_not_matched','evaluation':{
        'reason':'strategy_timeframe_data_unavailable:5m','timeframe_history':{'bars':48,'requested':207,'status':status,'error_type':'private-secret'}}}]}
    text=stock_cycle_diagnosis(report)
    assert '5m 48/207봉' in text and label in text and 'private' not in text
