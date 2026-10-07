from datetime import datetime, timezone
import json
import logging
from unittest.mock import patch
import pytest
from trading.trader import Position, PositionSide
from trading.unified_trader import UnifiedTrader
from trading.paper_strategy_ledger import (paper_position_execution_evidence,
    record_paper_strategy_outcome, read_paper_strategy_outcomes,
    paper_outcome_calculation_status, summarize_paper_outcomes)


@pytest.mark.parametrize('contract', [.01, .1, 1., 10., 100., 1000., 100000.])
@pytest.mark.parametrize('side', [PositionSide.LONG, PositionSide.SHORT])
def test_unified_contract_pnl_costs_value_and_percent_share_entry_units(contract, side):
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.settings = {'estimated_round_trip_fee_rate':.0004, 'estimated_slippage_rate':.0002}
    trader.logger = logging.getLogger('contract-unit-test')
    position = Position(symbol='QA/USDT:USDT', side=side, entry_price=100., current_price=110.,
        quantity=2., leverage=5, unrealized_pnl=0., unrealized_pnl_percent=0.,
        entry_time=datetime.now(timezone.utc), entry_evidence={'position_sizing':{'contract_size':contract}})
    pnl = trader._calculate_pnl_unified(position, 110.)
    expected_gross = 20*contract*(1 if side == PositionSide.LONG else -1)
    assert pnl['gross_pnl_ccy'] == pytest.approx(expected_gross)
    assert pnl['entry_value'] == pytest.approx(200*contract)
    assert pnl['position_value'] == pytest.approx(220*contract)
    assert pnl['estimated_fees'] == pytest.approx(.08*contract)
    assert pnl['estimated_slippage'] == pytest.approx(.04*contract)
    assert pnl['net_pnl_ccy'] == pytest.approx(expected_gross-.12*contract)
    assert pnl['net_pnl_percent'] == pytest.approx(9.94 if side == PositionSide.LONG else -10.06)
    assert position.quantity == 2  # order quantities remain contracts, no leverage double-count


def test_reported_okx_100x_case_has_same_contract_after_record_and_reload(tmp_path):
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.settings = {}
    trader.logger = logging.getLogger('contract-unit-test')
    position = Position(symbol='QUANT/USDT:USDT',side=PositionSide.SHORT,entry_price=261.4,
        current_price=256.6,quantity=57.3394495412844,leverage=3,unrealized_pnl=0.,unrealized_pnl_percent=0.,
        entry_time=datetime.now(timezone.utc),entry_evidence={'position_sizing':{
            'contract_size':.01,'final_notional':149.88532110091742}})
    pnl = trader._calculate_pnl_unified(position, 256.6)
    assert pnl['net_pnl_ccy'] == pytest.approx(2.662362385321075)
    ledger = tmp_path/'paper.jsonl'
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=ledger):
        record_paper_strategy_outcome(scope='unified',exchange='okx',symbol=position.symbol,
            strategy_key='qa',version_id='qa-v1',opened_at=position.entry_time,closed_at=position.entry_time,
            net_pnl=pnl['net_pnl_ccy'],gross_pnl=pnl['gross_pnl_ccy'],fees=pnl['estimated_fees'],
            estimated_slippage=pnl['estimated_slippage'],entry_price=position.entry_price,
            exit_price=256.6,quantity=position.quantity,side='SHORT',quote_currency='USDT',
            **paper_position_execution_evidence(position))
    rows = read_paper_strategy_outcomes(path=ledger)
    assert rows[0]['contract_size'] == .01
    assert paper_outcome_calculation_status(rows[0]) == 'valid'
    assert summarize_paper_outcomes(rows,default_currency='USDT')['net_pnl'] == pytest.approx(2.662362385321075)


def test_old_contract_quantity_notional_contradiction_is_excluded_without_rewriting():
    row = dict(scope='unified',exchange='okx',calculation_status='valid',
        cost_calculation_status='recorded_contract',entry_price=100.,quantity=150.,
        sizing_final_notional=150.,net_pnl=266.,fees=9.,quote_currency='USDT')
    original = json.dumps(row)
    assert paper_outcome_calculation_status(row) == 'legacy_unverified'
    summary = summarize_paper_outcomes([row],default_currency='USDT')
    assert summary['unverified_count'] == 1 and summary['closed_count'] == 0
    assert summary['win_rate'] is None
    assert json.dumps(row) == original
    assert paper_outcome_calculation_status({**row,'contract_size':.01}) == 'valid'


@pytest.mark.parametrize('contract',[0.,-1.,float('nan'),float('inf')])
def test_invalid_saved_contract_is_not_a_valid_zero_profit(contract):
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.settings = {}
    trader.logger = logging.getLogger('contract-unit-test')
    position = Position(symbol='QA/USDT:USDT',side=PositionSide.LONG,entry_price=100.,current_price=110.,
        quantity=1.,leverage=1,unrealized_pnl=0.,unrealized_pnl_percent=0.,entry_time=datetime.now(timezone.utc),
        entry_evidence={'position_sizing':{'contract_size':contract}})
    assert trader._calculate_pnl_unified(position,110.)['calculation_status'] == 'invalid'
    assert paper_outcome_calculation_status({'calculation_status':'valid','contract_size':contract}) == 'invalid'


def test_new_saved_contract_survives_entry_price_drift_from_sizing_quote():
    row=dict(scope='unified',exchange='okx',calculation_status='valid',cost_calculation_status='recorded_contract',
        entry_price=110.,quantity=2.,contract_size=.01,sizing_final_notional=2.)
    assert paper_outcome_calculation_status(row)=='valid'


def test_missing_legacy_contract_is_not_guessed_from_current_market_or_notional(tmp_path):
    trader=UnifiedTrader.__new__(UnifiedTrader);trader.settings={};trader.logger=logging.getLogger('contract-unit-test')
    position=Position(symbol='QA/USDT:USDT',side=PositionSide.LONG,entry_price=100.,current_price=110.,quantity=2.,
        leverage=1,unrealized_pnl=0.,unrealized_pnl_percent=0.,entry_time=datetime.now(timezone.utc),
        execution_mode='paper',entry_evidence={'position_sizing':{'final_notional':2.}})
    assert trader._calculate_pnl_unified(position,110.,exchange_name='okx')['calculation_status']=='invalid'
    from trading.paper_capital import paper_available_funds
    assert paper_available_funds(1000,{'QA':position},venue='okx',quote='USDT',ledger_file=tmp_path/'absent')['reason']=='paper_position_margin_unverified'


@pytest.mark.parametrize('method',['_perform_profit_analysis_unified','_perform_loss_analysis_unified'])
def test_ai_close_analysis_receives_unit_price_not_contract_multiplied_value(method):
    from types import SimpleNamespace
    trader=UnifiedTrader.__new__(UnifiedTrader);trader.settings={};trader.logger=logging.getLogger('contract-unit-test')
    calls=[]
    def capture(symbol,payload):calls.append(payload);return None
    trader.ai_manager=SimpleNamespace(enabled_for_role=lambda role:True,analyze_profit_trade=capture,analyze_loss_trade=capture)
    position=Position(symbol='QA/USDT:USDT',side=PositionSide.LONG,entry_price=100.,current_price=110.,quantity=2.,
        leverage=1,unrealized_pnl=0.,unrealized_pnl_percent=0.,entry_time=datetime.now(timezone.utc),
        entry_evidence={'position_sizing':{'contract_size':10.}})
    pnl=trader._calculate_pnl_unified(position,110.,exchange_name='okx')
    getattr(trader,method)('okx',position.symbol,position,pnl)
    assert len(calls)==1 and calls[0]['exit_price']==110.


def test_partial_paper_close_records_closed_contracts_before_releasing_margin(tmp_path):
    from trading.execution_mode import ExecutionMode
    from trading.custom_strategy_order_plan import evaluate_order_plan
    from trading.paper_capital import paper_available_funds
    trader=UnifiedTrader.__new__(UnifiedTrader);trader.settings={'paper_trading':True};trader.logger=logging.getLogger('partial-paper-test')
    trader._execution_mode=lambda venue:ExecutionMode.PAPER
    trader._persist_paper_positions=lambda:None
    position=Position(symbol='QA/USDT:USDT',side=PositionSide.LONG,entry_price=100.,current_price=110.,quantity=10.,
        leverage=1,unrealized_pnl=0.,unrealized_pnl_percent=0.,entry_time=datetime.now(timezone.utc),
        position_id='original',execution_mode='paper',entry_evidence={'position_sizing':{'contract_size':.01,'final_notional':10.}})
    trader.paper_positions={'okx':{position.symbol:position}}
    decision=evaluate_order_plan({'partial_take_profits':[{'target_percent':1.,'close_fraction':.4}]},None,pnl_percent=9.94,current_quantity=10.)
    ledger=tmp_path/'paper.jsonl'
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=ledger):
        assert trader._execute_advanced_partial_close_unified('okx',position.symbol,position,110.,decision)
        assert position.quantity==6.
        assert not trader._execute_advanced_partial_close_unified('okx',position.symbol,position,110.,decision)
        assert position.quantity==6.
        pnl=trader._calculate_pnl_unified(position,120.,exchange_name='okx')
        trader._record_paper_close_unified('okx',position.symbol,position,120.,pnl)
    rows=read_paper_strategy_outcomes(path=ledger)
    assert [r['quantity'] for r in rows]==[4.,6.]
    assert rows[0]['event_id']!=rows[1]['event_id']
    assert all(paper_outcome_calculation_status(r)=='valid' for r in rows)
    assert sum(r['gross_pnl'] for r in rows)==pytest.approx(1.6)
    assert paper_available_funds(1000,{},venue='okx',quote='USDT',ledger_file=ledger)['available_capital']==pytest.approx(1001.594)


def test_partial_paper_ledger_write_failure_keeps_position_and_plan():
    from trading.execution_mode import ExecutionMode
    trader=UnifiedTrader.__new__(UnifiedTrader);trader.settings={};trader.logger=logging.getLogger('partial-paper-test')
    trader._execution_mode=lambda venue:ExecutionMode.PAPER
    position=Position(symbol='QA',side=PositionSide.LONG,entry_price=100.,current_price=110.,quantity=10.,leverage=1,
        unrealized_pnl=0.,unrealized_pnl_percent=0.,entry_time=datetime.now(timezone.utc),
        entry_evidence={'position_sizing':{'contract_size':.01}})
    with patch('trading.unified_trader.record_paper_strategy_outcome',side_effect=OSError('disk full')):
        assert not trader._execute_advanced_partial_close_unified('okx','QA',position,110.,dict(quantity=4.,partial_index=0))
    assert position.quantity==10 and not position.custom_order_plan_state


@pytest.mark.parametrize('field',['entry_price','quantity'])
def test_nonfinite_position_numbers_never_produce_a_valid_pnl(field):
    trader=UnifiedTrader.__new__(UnifiedTrader);trader.settings={};trader.logger=logging.getLogger('finite-test')
    position=Position(symbol='QA',side=PositionSide.LONG,entry_price=100.,current_price=110.,quantity=1.,leverage=1,
        unrealized_pnl=0.,unrealized_pnl_percent=0.,entry_time=datetime.now(timezone.utc))
    setattr(position,field,float('nan'))
    assert trader._calculate_pnl_unified(position,110.)['calculation_status']=='invalid'


def test_unknown_contract_projection_and_restart_keep_unverified_status(tmp_path):
    from types import SimpleNamespace
    from trading.execution_mode import ExecutionMode
    from trading.paper_position_store import save_positions,load_positions
    from web_platform.runtime_bridge import _runtime_safe
    trader=UnifiedTrader.__new__(UnifiedTrader);trader.settings={};trader.logger=logging.getLogger('projection-test')
    position=Position(symbol='QA/USDT:USDT',side=PositionSide.LONG,entry_price=100.,current_price=110.,quantity=1.,
        leverage=1,unrealized_pnl=0.,unrealized_pnl_percent=0.,entry_time=datetime.now(timezone.utc),execution_mode='paper')
    trader._position_store=lambda venue:{position.symbol:position}
    trader._execution_mode=lambda venue:ExecutionMode.PAPER
    trader._verify_and_repair_tp_sl=lambda venue:None
    trader._should_close_position_unified=lambda *args:False
    trader.exchange_manager=SimpleNamespace(get_current_price=lambda *args:110.)
    trader._monitor_exchange_positions('okx')
    assert position.pnl_calculation_status=='invalid'
    assert _runtime_safe(position)['pnl_calculation_status']=='invalid'
    snapshot=tmp_path/'positions.json';save_positions(snapshot,{'okx':{position.symbol:position}})
    assert load_positions(snapshot,Position,PositionSide)['okx'][position.symbol].pnl_calculation_status=='invalid'


@pytest.mark.parametrize('rate',['estimated_round_trip_fee_rate','estimated_slippage_rate'])
def test_nonfinite_cost_setting_is_not_a_valid_zero_cost(rate):
    trader=UnifiedTrader.__new__(UnifiedTrader);trader.settings={rate:float('nan')};trader.logger=logging.getLogger('cost-test')
    position=Position(symbol='QA',side=PositionSide.LONG,entry_price=100.,current_price=110.,quantity=1.,leverage=1,
        unrealized_pnl=0.,unrealized_pnl_percent=0.,entry_time=datetime.now(timezone.utc))
    assert trader._calculate_pnl_unified(position,110.)['calculation_status']=='invalid'


@pytest.mark.parametrize('contract',[None,0.,-1.,float('nan'),float('inf'),True])
def test_unknown_market_contract_cannot_be_saved_as_one(contract):
    from types import SimpleNamespace
    trader=UnifiedTrader.__new__(UnifiedTrader)
    trader.get_exchange_client=lambda venue:SimpleNamespace(exchange=SimpleNamespace(market=lambda symbol:{'contractSize':contract}))
    trader._normalize_symbol_for_adapter=lambda adapter,symbol:symbol
    with pytest.raises(ValueError,match='^market_contract_size_unverified$'):
        trader._ccxt_contract_size('okx','QA/USDT:USDT')


def test_failed_sizing_cannot_fall_back_to_a_minimum_order_quantity():
    trader=UnifiedTrader.__new__(UnifiedTrader);trader.settings={'position_sizing_policy':{'mode':'account_risk'}};trader.logger=logging.getLogger('sizing-failure-test')
    trader._position_sizing_equity=lambda *args,**kwargs:(1000.,'paper_virtual_equity')
    trader._effective_leverage_policy=lambda *args,**kwargs:{'effective':1}
    trader._ccxt_contract_size=lambda *args:(_ for _ in ()).throw(ValueError('market_contract_size_unverified'))
    params={}
    assert trader._calculate_position_size_unified('okx','QA/USDT:USDT',{'price':100},params)==0
    assert params['_position_sizing']=={'allowed':False,'reason':'market_contract_size_unverified'}
