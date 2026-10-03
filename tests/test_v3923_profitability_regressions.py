from copy import deepcopy
import pytest
from trading.profitability_validation import ProfitabilityValidator
from trading.trader import Trader
from trading.unified_trader import UnifiedTrader


def test_partial_exchange_policy_preserves_mode_and_does_not_mutate():
    settings = {'advanced_trading_layers': {'profitability_validation': {'enabled': True, 'underperformance_mode': 'limited_learning', 'hard_stop_mdd': .45}, 'exchange_overrides': {'binance': {'profitability_validation': {'enabled': True}}, 'bybit': {'profitability_validation': {'enabled': True}}}}}
    before = deepcopy(settings)
    for cls, venue in [(Trader, 'binance'), (UnifiedTrader, 'bybit')]:
        engine = cls.__new__(cls); engine.settings = settings
        layers = engine._get_advanced_layers_settings_binance() if venue == 'binance' else engine._get_advanced_layers_settings(venue)
        assert layers['profitability_validation']['underperformance_mode'] == 'limited_learning'
        layers['profitability_validation']['hard_stop_mdd'] = .9
        assert settings == before


def test_hard_loss_precedes_cold_start():
    result = ProfitabilityValidator().evaluate_strategy([{'return_fraction': -.5}], {'underperformance_mode': 'limited_learning'})
    assert not result['enabled']
    assert 'hard_stop_mdd_exceeded' in result['reasons']


@pytest.mark.parametrize('row', [{'net_pnl': -10}, {'return_fraction': float('nan')}, {'return_fraction': 'bad'}, {'return_fraction': float('inf')}, {'quantity': 1, 'price': 10}])
def test_incomplete_return_is_not_new_customer_or_zero(row):
    result = ProfitabilityValidator().evaluate_strategy([row])
    assert not result['enabled']
    assert result['reason'] == 'return_evidence_required'


def test_latest_binance_sample_is_evaluated_oldest_first():
    class Recorder:
        def get_trade_history(self, **kw):
            return [{'id': i, 'exit_time': f'2026-10-0{i}T00:00:00+00:00'} for i in (3, 2, 1)]
    engine = Trader.__new__(Trader); engine.recorder = Recorder()
    assert [r['id'] for r in engine._get_recent_trade_samples_binance(limit=2)] == [2, 3]


def test_strict_stop_and_reconciliation_remain_blocked():
    validator = ProfitabilityValidator()
    rows = [{'return_fraction': -.001}] * 20
    assert not validator.evaluate_strategy(rows, {'underperformance_mode': 'strict_stop'})['enabled']
    assert validator.evaluate_strategy(rows, {'underperformance_mode': 'limited_learning'})['enabled']
    assert not validator.evaluate_strategy(rows + [{'performance_evidence_ready': False}], {'underperformance_mode': 'limited_learning'})['enabled']
    assert validator.evaluate_strategy([])['stage'] == 'limited_live_learning'


def test_unified_read_failure_is_not_cold_start():
    from types import SimpleNamespace
    class FailedRecorder:
        def get_recent_trades(self, **kwargs): raise OSError('synthetic')
        def get_recent_exchange_executions(self, *args, **kwargs): return []
    engine=UnifiedTrader.__new__(UnifiedTrader);engine.recorder=FailedRecorder();engine.logger=SimpleNamespace(warning=lambda message:None)
    rows=engine._get_local_trade_samples_unified('bybit',limit=200)
    assert not ProfitabilityValidator().evaluate_strategy(rows)['enabled']


def test_diagnostic_recomputes_without_start_or_policy_mutation():
    from types import SimpleNamespace
    from web_platform.runtime_bridge import HeadlessRuntimeBridge
    bridge=HeadlessRuntimeBridge(account='synthetic',factory=lambda _:pytest.fail('must not initialize runtime'))
    assert bridge.profitability_diagnostic('binance')['status']=='engine_evidence_unavailable'
    engine=Trader.__new__(Trader)
    engine.settings={'advanced_trading_layers':{'enabled':True,'profitability_validation':{'underperformance_mode':'limited_learning'}}}
    engine.recorder=SimpleNamespace(get_trade_history=lambda **kw:[{'return_fraction':-.001,'exit_time':'2026-10-02'}]*20)
    before=deepcopy(engine.settings);bridge._app=SimpleNamespace(trader=engine)
    report=bridge.profitability_diagnostic('binance')
    assert report['diagnostic_state']=='recovery_learning'
    assert report['policy_origins']['underperformance_mode']=='global'
    assert report['order_permission_granted'] is False
    assert engine.settings==before


def test_offline_repair_preserves_explicit_stop_and_unrelated_settings():
    from scripts.repair_profitability_policy import repair_plan
    for explicit in ({'enabled':True},{'underperformance_mode':'strict_stop'}):
        original={'private':'preserve','advanced_trading_layers':{'profitability_validation':{'underperformance_mode':'limited_learning','hard_stop_mdd':.45},'exchange_overrides':{'binance':{'profitability_validation':explicit,'strategy_engine':{'enabled':False}}}}}
        updated,changes=repair_plan(original,'binance')
        assert updated['private']=='preserve'
        actual=updated['advanced_trading_layers']['exchange_overrides']['binance']
        assert actual['profitability_validation']['underperformance_mode']==explicit.get('underperformance_mode','limited_learning')
        assert actual['strategy_engine']=={'enabled':False}
        assert original['advanced_trading_layers']['exchange_overrides']['binance']['profitability_validation']==explicit
