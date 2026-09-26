"""Synthetic sources/providers only. No real orders or original store writes."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from trading.source_condition_compiler import ConditionCompiler, compile_sections
from trading.declarative_strategy_engine import DeclarativeStrategyEngine as Engine
from trading.strategy_source_ingestor import StrategySourceIngestor
from trading.custom_strategy_pipeline import CustomStrategyPipeline
from web_platform.application_services import ApplicationServices


SOURCE = '''trend_ok = close >= ema20 AND ema20 > ema50
pullback_ok = rsi <= 35 OR (rsi < 45 AND volume_ratio >= 1.2)
ENTRY:
signal == LONG AND trend_ok AND pullback_ok
EXIT:
rsi >= 65 OR close < ema20
RISK:
15분봉, 손절 1%, 익절 2%, 자산 5%, 횡보장.
'''


def test_named_compound_source_repair_save_reload_and_actual_decisions(tmp_path):
    original = SOURCE.replace('rsi <= 35 OR (rsi < 45 AND volume_ratio >= 1.2)', 'undefined_signal')
    parser = StrategySourceIngestor()
    before = parser.analyze(original,kind='text')
    assert not before['ready_for_execution']
    after = parser.analyze(SOURCE,kind='text')
    assert after['ready_for_execution'], after['blocking_details']
    rules = after['rules']
    assert ApplicationServices.validate_strategy_draft(None,rules=rules)['ready']
    pipeline = CustomStrategyPipeline(storage_path=tmp_path/'strategies.json')
    old = pipeline.submit(name='old source',rules=before['rules'])
    preserved = deepcopy(old)
    new = pipeline.submit(name='repaired source',rules=rules,strategy_key=old['strategy_key'])
    pipeline.approve(new['strategy_key'],new['version_id'],approved_by='fixture')
    loaded = CustomStrategyPipeline(storage_path=tmp_path/'strategies.json')
    assert loaded.get_version(old['strategy_key'],old['version_id']) == preserved
    current = loaded.get_version(new['strategy_key'],new['version_id'])
    assert not current.get('execution_validation') and not current.get('paper_validation')
    context = {'signal':'LONG','close':100,'ema20':100,'ema50':90,'rsi':40,'volume_ratio':1.3}
    assert Engine.evaluate_entry(current['rules'],context)['allowed']
    assert not Engine.evaluate_entry(current['rules'],{**context,'volume_ratio':1})['allowed']
    assert Engine.evaluate_entry(current['rules'],{**context,'rsi':30,'volume_ratio':1})['allowed']
    assert not Engine.evaluate_entry(current['rules'],{**context,'signal':'SHORT'})['allowed']
    assert not loaded.active_versions


def test_missing_named_definition_can_be_completed_without_rewriting_original():
    original = 'ENTRY:\nconfirmed_setup\nEXIT:\nrsi >= 65\nRISK:\n15분봉, 손절 1%, 익절 2%, 자산 5%, 횡보장.'
    parser=StrategySourceIngestor()
    before=parser.analyze(original,kind='text')
    assert not before['ready_for_execution']
    assert any('confirmed_setup = ...' in item['action'] for item in before['blocking_details'])
    question = next(q for q in before['clarification_questions'] if q.get('answer_target') == 'confirmed_setup')
    assert question['resolution'] == 'user_answer'
    assert question['answer_kind'] == 'condition_definition'
    assert question['auto_executable'] is False
    after=parser.analyze(original,kind='text',supplemental_text='confirmed_setup = signal == LONG AND rsi <= 35')
    assert after['ready_for_execution'],after['blocking_details']
    assert original in after['rules']['source_evidence']['text']
    assert after['rules']['source_evidence']['evidence']['user_confirmation_present']
    assert Engine.evaluate_entry(after['rules'],{'signal':'LONG','rsi':30})['allowed']
    assert not Engine.evaluate_entry(after['rules'],{'signal':'LONG','rsi':40})['allowed']


def test_missing_definition_interview_is_deduplicated_and_does_not_hide_engine_gaps():
    parser = StrategySourceIngestor()
    result = parser.analyze('ENTRY:\nsetup_ok\nsetup_ok\nunsupported(close)\nEXIT:\nrsi >= 65\nRISK:\n15분봉, 손절 1%, 익절 2%, 자산 5%, 횡보장.', kind='text')
    questions = result['clarification_questions']
    definitions = [q for q in questions if q.get('answer_target') == 'setup_ok']
    assert len(definitions) == 1 and definitions[0]['resolution'] == 'user_answer'
    assert any(q['resolution'] == 'source_rewrite' and 'unsupported(close)' in q['title'] for q in questions)
    assert not result['ready_for_execution']


def test_user_supplement_repair_remains_blocked_for_invalid_or_incomplete_answers():
    source = 'ENTRY:\nsetup_ok\nEXIT:\nrsi >= 65\nRISK:\n15분봉, 손절 1%, 익절 2%, 자산 5%, 횡보장.'
    for answer in ['setup_ok = unknown_value', 'setup_ok = close > rolling_max(5)', 'setup_ok = True', 'setup_ok = rsi <= 35\nsetup_ok = rsi > 50']:
        result = StrategySourceIngestor().analyze(source, kind='text', supplemental_text=answer)
        assert not result['ready_for_execution'], answer


def test_recovery_exposes_required_evidence_without_authorizing_start(tmp_path):
    from test_v39143_record_recovery import make
    recorder,tid,fill,client,job=make(tmp_path,exit_id=None)
    result=job.start('binance',background=False)
    assert result['remaining']==1
    action=result['next_actions']['missing_exit_order_evidence']
    assert 'entry_exit_order_ids' in action['required_evidence']
    assert not action['retry_without_new_evidence']
    assert not result['resume_authorized']
    from trading.record_recovery import RecordRecovery
    assert RecordRecovery.read_status(recorder.db_path,'binance')['next_actions']==result['next_actions']


def test_runtime_rejection_audit_records_correlation_not_raw_exception():
    audit=Mock()
    service=SimpleNamespace(_audit=audit)
    ApplicationServices.record_runtime_rejection(service,'request-12345678','trading.start','okx',RuntimeError('trading_candidates_unavailable:okx'))
    assert audit.call_args.args[1]=={'command_id':'request-12345678','command':'trading.start','source':'okx','reason_code':'trading_candidates_unavailable'}
    ApplicationServices.record_runtime_rejection(service,'request-12345678','trading.start','okx',RuntimeError('private-credential-fixture'))
    assert audit.call_args.args[1]['reason_code']=='runtime_command_failed'
    audit.side_effect=OSError('disk full')
    ApplicationServices.record_runtime_rejection(service,'request-12345678','trading.start','okx',RuntimeError('risk_data_unavailable'))


@pytest.mark.parametrize('venue',['binance','okx','bybit','bitget','upbit','bithumb','coinone','kis','kiwoom','shinhan','mirae'])
def test_real_recovery_then_risk_reevaluation_keeps_confirmed_losses(tmp_path,monkeypatch,venue):
    from test_v39143_record_recovery import make
    from trading.risk_manager import RiskManager
    import trading.notifications as notifications
    recorder,tid,fill,client,job=make(tmp_path,venue=venue)
    if venue in {'kis','kiwoom','shinhan','mirae'}:
        # Brokers require BOTH entry and exit evidence, unlike a crypto close
        # with an already proven entry fee. Model their actual adapter contract.
        client.get_recovery_order_fills=lambda symbol,order,epoch:[{
            **fill,'id':f'fill-{order}','order':order,
            'side':'buy' if order=='entry-1' else 'sell',
            'price':100 if order=='entry-1' else 95,
            'fee':{'cost':0 if order=='entry-1' else .2,'currency':'KRW'}}]
    manager=RiskManager(object(),recorder)
    manager.daily_initial_balance=1000
    manager.max_daily_loss_percent=30
    monkeypatch.setattr(manager,'_get_live_equity_snapshot',lambda _: {'valid':True,'equity':1000})
    monkeypatch.setattr(manager,'_managed_unrealized_pnl',lambda *a,**kw:(True,0,''))
    monkeypatch.setattr(notifications,'publish_notification',lambda *a,**kw:True)
    before=manager.evaluate_daily_loss_limit(venue,execution_mode='live')
    assert before.blocked and before.status=='risk_data_unavailable'
    result=job.start(venue,background=False)
    assert result['recovered']==1
    after=manager.evaluate_daily_loss_limit(venue,execution_mode='live')
    assert not after.blocked
    assert after.realized_pnl==pytest.approx(-10.2)
    # Recovery did not discard the loss: a tighter existing risk threshold
    # still blocks. This is not an unconditional resume test.
    manager.max_daily_loss_percent=.1
    assert manager.evaluate_daily_loss_limit(venue,execution_mode='live').blocked
    assert not result['auto_started'] and not result['resume_authorized']


@pytest.mark.parametrize('expression',[
    'rsi < 30 OR undefined_sweep', '__import__("os").system("id")',
    'rsi < True', 'rsi < 1e999', 'not rsi < 30', 'rsi < [1]',
    'signal == 1', 'close >= absent_price', 'rsi < 30; print(1)',
])
def test_unsupported_conditions_are_not_partially_executed(expression):
    result = compile_sections(f'ENTRY:\n{expression}\nEXIT:\nrsi > 60')
    assert result['gaps'] and 'entry' not in result


@pytest.mark.parametrize('op,expected',[('>',False),('>=',True),('<',False),('<=',True),('==',True),('!=',False)])
def test_field_equality_boundaries(op,expected):
    graph=ConditionCompiler().compile(f'close {op} ema20')
    assert Engine._evaluate_expression_node(graph,{'close':10,'ema20':10})[0] is expected
    assert not Engine._evaluate_expression_node(graph,{'close':10})[0]


@pytest.mark.parametrize('bad',['NaN','bad',True,None,float('inf')])
@pytest.mark.parametrize('op',['gt_field','lt_field','gte_field','lte_field','eq_field','ne_field','crosses_above','crosses_below'])
def test_invalid_indicator_values_never_pass_field_comparison(bad,op):
    condition={'field':'close','operator':op,'value_field':'ema20'}
    assert not Engine._condition(condition,{'close':bad,'ema20':bad})[0]
    if op.startswith('crosses_'):
        assert not Engine._condition(condition,{'close':10,'ema20':9,'_previous':{'close':bad,'ema20':bad}})[0]


def test_precedence_chains_cycles_and_redefined_fields():
    graph=ConditionCompiler().compile('rsi < 30 OR close > ema20 > ema50')
    assert Engine._evaluate_expression_node(graph,{'rsi':20,'close':1,'ema20':2,'ema50':3})[0]
    for definitions,expression in [({'a':'b','b':'a'},'a'),({'ema20':'ema(close,99)'},'close > ema20')]:
        with pytest.raises(ValueError): ConditionCompiler(definitions).compile(expression)
    result=compile_sections('ENTRY:\nrsi < 30\nFILTER:\nundefined_condition')
    assert result['gaps'] and 'entry' not in result


@pytest.mark.parametrize('venue',['upbit','bithumb','coinone','okx','bybit','bitget'])
@pytest.mark.parametrize('reason',['runtime_source_not_enabled','exchange_initialization_failed','trading_candidates_unavailable','runtime_start_exception'])
def test_unified_start_reason_survives_false_legacy_contract(venue,reason):
    from trading.unified_trader import UnifiedTrader
    trader=UnifiedTrader.__new__(UnifiedTrader)
    trader.logger=Mock(); trader.settings={}; trader.monitoring_flags={}
    trader.selected_coins={venue:[]}
    trader._is_trade_enabled=lambda _:reason != 'runtime_source_not_enabled'
    trader._is_learning_enabled=lambda _:False
    trader._ensure_exchange_initialized=lambda _:reason != 'exchange_initialization_failed'
    trader._evaluate_current_market_conditions_unified_fast=Mock(side_effect=RuntimeError('private details') if reason=='runtime_start_exception' else None,return_value='normal')
    trader._regime_stabilizer=SimpleNamespace(observe=lambda *a,**kw:('normal',False))
    trader.last_market_regime_by_exchange={}
    trader.select_trading_coins_unified=lambda _:[]
    assert trader.start_trading(venue) is False
    with pytest.raises(RuntimeError,match=f'^{reason}:{venue}$'):
        trader.start_trading_checked(venue)
