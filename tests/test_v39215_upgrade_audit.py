"""Offline upgrade invariants and direction-aware stock consensus; synthetic data."""
from copy import deepcopy
from unittest.mock import patch,MagicMock
import pytest
from trading.strategy_engine import StrategyEngine

pytestmark=pytest.mark.usefixtures("listed_instrument_transport")


def test_stock_sell_consensus_matches_bearish_score_direction():
    engine=StrategyEngine()
    # Same strength in opposite directions must not turn a low sell score into low conviction.
    assert engine.consensus_score({'score':20,'momentum':-2.5},direction='SELL')==pytest.approx(engine.consensus_score({'score':80,'momentum':2.5},direction='BUY'))


def test_stock_direction_does_not_change_default_crypto_consensus_or_risk_checks():
    engine=StrategyEngine();bear={'score':20,'momentum':-2.5,'rsi':25,'trend':'bear'}
    assert engine.consensus_score(bear)==pytest.approx(.44)
    allowed,meta=engine.should_trade(symbol='SYNTHETIC',analysis_result=bear,runtime_state={},policy={'enabled':True,'consensus_threshold':.99,'allow_regimes':['range'],'cooldown_sec':0},signal_direction='SELL')
    assert not allowed and any(v.startswith('consensus_low') for v in meta['reasons'])


@pytest.mark.parametrize('scope,tf,expected',[('asset:stock','5m',True),('broker:kis,kiwoom','3m',True),('asset:all','15m',True),('asset:stock','1d',False),('exchange:binance,okx','5m',False)])
def test_stock_timeframe_support_is_explained_without_mutating_execution_grants(scope,tf,expected):
    from trading.strategy_scope import strategy_runtime_support
    rules={'target_scope':scope,'decision_timeframe':tf};before=deepcopy(rules)
    result=strategy_runtime_support(rules)
    assert (result['status']=='stock_timeframe_unsupported')==expected
    assert rules==before and result['grants_execution'] is False


def test_stock_cycle_explains_consensus_and_missing_timeframes_without_private_messages():
    from trading.stock_runtime_controller import stock_cycle_diagnosis
    result={'decisions':[{'reason':'strategy_blocked','strategy_reasons':['consensus_low:0.31<0.50','private-secret-value'],'trade_candidate':{'evaluation':{'evaluated':[{'result':{'reason':'strategy_timeframe_data_unavailable:5m'}}]}}}]}
    text=stock_cycle_diagnosis(result)
    assert '0.31 / 필요 0.50' in text and '5m' in text and '일봉' in text and 'private-secret-value' not in text


@pytest.mark.parametrize('legacy',[False,True])
def test_existing_paper_and_active_rules_samples_survive_reload(tmp_path,legacy):
    import json
    from tests.test_v39214_stock_studio import prepared_pipeline
    from trading.custom_strategy_pipeline import CustomStrategyPipeline
    p,v=prepared_pipeline(tmp_path);key,vid=v['strategy_key'],v['version_id']
    p.start_paper_observation(key,vid,trial_days=3)
    p.record_paper_validation(key,vid,trades=2,metrics={'observation_days':2})
    if legacy:
        raw=json.loads(p.storage_path.read_text());ver=raw['strategies'][key][0]
        ver.pop('paper_trial',None);ver.pop('paper_observation_windows',None)
        p.storage_path.write_text(json.dumps(raw))
    original=json.loads(p.storage_path.read_text());loaded=CustomStrategyPipeline(str(p.storage_path));after=loaded.get_version(key,vid)
    assert after['rules']==original['strategies'][key][0]['rules']
    assert after['paper_validation']['trades']==2 and loaded.paper_versions==original['paper_versions']
    assert loaded.active_versions==original['active_versions']


@pytest.mark.parametrize('score,momentum,owned',[(20,-2.5,True),(20,-2.5,False),(55,0,False)])
def test_stock_paper_cycle_direction_hold_and_owned_quantity_boundaries(tmp_path,score,momentum,owned):
    from tests.test_stock_analysis_service import _make_mock_adapter
    from trading.stock_analysis_service import StockAnalysisService
    adapter=_make_mock_adapter();adapter.api_type='real'
    recorder=MagicMock();recorder.execute_query.return_value=[]
    svc=StockAnalysisService(adapter,broker_name='kis',recorder=recorder)
    svc._persist_paper_positions=lambda:None
    svc._restore_paper_positions=lambda:None
    svc._get_recent_paper_trade_samples=lambda limit=50:[]
    svc._paper_positions().clear()
    if owned:
        ok,_,_=svc._place_paper_stock_order(symbol='005930',side='BUY',quantity=2,price=100,order_type='MARKET')
        assert ok
    analysis={'status':'ok','symbol':'005930','score':score,'momentum':momentum,'current_price':99,'is_etf':False,'rsi':45,'trend':'range','technical_history':{'status':'ready','bars':20}}
    with patch.object(svc,'get_market_regime',return_value='range'),patch.object(svc,'analyze_symbol',return_value=analysis):
        result=svc.run_auto_trade_cycle(symbols=['005930'],quantity=1,max_orders=1,allow_live_order=False,execution_mode_override='paper',guardrails={'enabled':False},exit_policy={'enable_exit_policy':False},auto_risk_policy={'profitability_validation':{'enabled':False},'strategy_engine':{'enabled':True,'consensus_threshold':.5,'allow_regimes':['range','bear','bull','trend','high_vol'],'cooldown_sec':0}})
    assert result['execution_mode']=='paper' and not adapter.place_order.called
    if score==55:assert result['decisions'][0]['reason']=='threshold_not_met'
    elif owned:
        assert result['orders_executed']==1 and svc._paper_positions()['005930']['quantity']==1, [(d.get('reason'), d.get('strategy_reasons')) for d in result['decisions']]
    else:
        assert result['orders_executed']==0 and not svc._paper_positions()


def test_kiwoom_cached_connection_flag_is_not_live_readiness(monkeypatch):
    from trading.exchanges.adapters.kiwoom_stock_adapter import KiwoomStockAdapter
    import trading.exchanges.adapters.kiwoom_stock_adapter as m
    monkeypatch.setattr(m.platform,'system',lambda:'Windows')
    adapter=KiwoomStockAdapter('synthetic','','',api_type='real',api_version='pykiwoom',account_no='synthetic')
    adapter.is_connected=True
    adapter.kiwoom=MagicMock();adapter.kiwoom.GetConnectState.return_value=0
    allowed,reason=adapter.get_live_readiness()
    assert not allowed and reason and not adapter.is_connected
    adapter.kiwoom.SendOrder.assert_not_called()


@pytest.mark.parametrize('cooldown,blocked',[(0,False),(60,True)])
def test_explicit_zero_cooldown_is_not_replaced_with_sixty_seconds(cooldown,blocked):
    from datetime import datetime
    engine=StrategyEngine()
    allowed,meta=engine.should_trade(symbol='SYNTHETIC',analysis_result={'score':80,'momentum':0},runtime_state={'last_trade_at::SYNTHETIC':datetime.now()},policy={'enabled':True,'consensus_threshold':.5,'allow_regimes':['range'],'cooldown_sec':cooldown})
    assert any(v.startswith('cooldown:') for v in meta['reasons'])==blocked
