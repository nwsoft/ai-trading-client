from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest


def test_optimizer_history_is_proposal_only_persists_and_coalesces(tmp_path):
    from trading.ai.auto_optimizer import AIAutoOptimizer
    settings={'default_tp':.01,'default_sl':.01,'default_leverage':4,'rsi_period':14}
    original=deepcopy(settings);path=tmp_path/'proposals.jsonl'
    optimizer=AIAutoOptimizer(None,None,settings,history_path=path)
    stats={'win_rate':.2,'avg_profit_percent':-.02,'max_drawdown':-.1}
    optimizer._maybe_adjust_parameters(stats);optimizer._maybe_adjust_parameters(stats)
    assert settings==original and len(path.read_text().splitlines())==1
    reloaded=AIAutoOptimizer(None,None,settings,history_path=path)
    row=reloaded.proposal_history[0]
    assert row['requires_approval'] is True and row['applied'] is False
    assert row['current_parameters']['default_tp']==.01
    assert row['evidence']['win_rate']==.2 and row['source']=='verified_live_outcomes'
    assert 'rsi_period' not in row


def test_invalid_parallel_snapshot_blocks_new_entries_without_overwriting_file(tmp_path,monkeypatch):
    import trading.parallel_strategy_paper as m
    monkeypatch.setattr(m,'get_app_data_dir',lambda:tmp_path)
    path=tmp_path/'parallel_strategy_paper_positions.json';path.write_text('{broken')
    engine=m.ParallelStrategyPaperEngine(settings_provider=lambda:{'paper_trading':False,'parallel_strategy_paper_validation':{'enabled':True}})
    assert engine.enabled() is False
    assert engine.status()['state']=='needs_attention'
    assert engine.status()['reason_code']=='parallel_paper_snapshot_invalid'
    assert path.read_text()=='{broken'


@pytest.mark.parametrize('working_type',['MARK_PRICE','CONTRACT_PRICE'])
def test_existing_protection_keeps_both_supported_trigger_types(working_type):
    from trading.tp_sl_manager import TpSlManager
    assert TpSlManager._protective_order_is_open({'orderType':'STOP_MARKET','algoStatus':'NEW','workingType':working_type})


def test_native_margin_already_set_ack_is_success_and_unknown_error_is_failure():
    from api.binance_client import BinanceClient
    client=object.__new__(BinanceClient);client._has_api_keys=lambda:True
    client.get_synced_timestamp=lambda:123;client.config=SimpleNamespace(recv_window=5000);client.logger=Mock()
    class Already(Exception):code=-4046
    client.client=SimpleNamespace(futures_change_margin_type=Mock(side_effect=Already()))
    assert client.set_margin_type('TESTUSDT','ISOLATED') is True
    client.client.futures_change_margin_type.side_effect=TimeoutError()
    assert client.set_margin_type('TESTUSDT','ISOLATED') is False


@pytest.mark.parametrize('trigger',['MARK_PRICE','CONTRACT_PRICE','LAST'])
def test_native_protection_propagates_selected_trigger_to_both_orders(trigger):
    # Exercise the actual request-construction function with a visible position,
    # empty existing protection and mocked order submission; no exchange calls.
    from api.binance_client import BinanceClient
    from unittest.mock import MagicMock
    client=object.__new__(BinanceClient)
    client.log_event=lambda *a,**k:None;client.logger=Mock();client._has_api_keys=lambda:True
    client.get_symbol_filters=lambda symbol:{'tickSize':.01}
    client.get_open_algo_orders=lambda *a,**k:[]
    client.client=MagicMock()
    client.client.futures_get_position_mode.return_value={'dualSidePosition':False}
    client.client.futures_position_information.return_value=[{'positionAmt':'1','positionSide':'BOTH'}]
    client.client.futures_get_open_orders.return_value=[]
    client.place_futures_order=Mock(side_effect=[{'status':'success','order_id':'tp'},{'status':'success','order_id':'sl'}])
    client.place_tp_sl_orders('TESTUSDT','LONG',110.,90.,price_precision=2,working_type=trigger)
    assert client.place_futures_order.call_count==2
    assert {c.kwargs['working_type'] for c in client.place_futures_order.call_args_list}==({'CONTRACT_PRICE'} if trigger=='LAST' else {trigger})


def test_runtime_capital_snapshots_do_not_fragment_filters_or_invent_fixed_equity():
    from trading.paper_statistics_cohorts import cohort
    rows=[cohort({'capital_basis':'runtime_virtual_account','capital_reference':value}) for value in (1000.,1001.,999.)]
    assert len({r['cohort_key'] for r in rows})==1
    assert all(r['capital_reference'] is None for r in rows)
    assert [r['capital_observed_at_entry'] for r in rows]==[1000.,1001.,999.]
