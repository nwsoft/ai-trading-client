"""Safety constraints and configured thresholds, without account/order access."""
import json
from pathlib import Path

import pytest

from trading.portfolio_orchestrator import PortfolioOrchestrator
from trading.ops_automation import OpsAutomationEngine


@pytest.mark.parametrize('count', [1, 2, 5, 30])
@pytest.mark.parametrize('cap', [0, .1, .35, 1])
def test_concentration_limit_survives_allocation_and_quantity(count, cap):
    engine = PortfolioOrchestrator()
    rows = [{'symbol': f'QA{i}', 'asset_class': 'crypto', 'volatility': .01 + i * .02,
             'signal_strength': .8, 'avg_correlation': .1} for i in range(count)]
    allocation = engine.allocate(rows, 1000, {'max_symbol_weight': cap, 'max_portfolio_risk': .8})
    weights = [row['weight'] for row in allocation['allocations'].values()]
    assert all(0 <= weight <= cap for weight in weights)
    assert sum(weights) <= .8 + 1e-12
    for candidate in rows:
        qty = engine.quantity_from_allocation(candidate['symbol'], 10, 999, allocation)
        assert qty * 10 <= cap * 1000 + 1e-12


def test_shipped_portfolio_policy_and_legacy_names_have_same_meaning():
    policy = json.loads(Path('config/settings_template.json').read_text())['advanced_trading_layers']['portfolio_orchestration']
    engine = PortfolioOrchestrator()
    rows = [{'symbol': 'QA', 'asset_class': 'stock', 'signal_strength': .8, 'volatility': .02}]
    configured = engine.allocate(rows, 1000, policy)
    legacy = engine.allocate(rows, 1000, {'risk_budgets': policy['risk_budget'],
        'max_symbol_weight': policy['max_single_asset_weight'], 'correlation_penalty': policy['correlation_penalty']})
    assert configured == legacy
    assert configured['allocations']['QA']['weight'] <= policy['max_single_asset_weight']


@pytest.mark.parametrize('price', [0, None, 'unknown'])
@pytest.mark.parametrize('capital', [0, 350])
def test_known_allocation_never_borrows_quantity_when_price_is_missing(price, capital):
    assert PortfolioOrchestrator().quantity_from_allocation('QA', price, 999,
        {'allocations': {'QA': {'capital': capital}}}) == 0


def test_unallocated_legacy_quantity_fallback_is_preserved():
    assert PortfolioOrchestrator().quantity_from_allocation('QA', 10, 3, {'allocations': {}}) == 3


def test_explicit_legacy_override_takes_precedence_without_mutating_policy():
    policy = {'risk_budget': {'crypto': .1}, 'risk_budgets': {'crypto': .3},
              'max_single_asset_weight': .8, 'max_symbol_weight': .2}
    before = json.dumps(policy, sort_keys=True)
    result = PortfolioOrchestrator().allocate([{'symbol': 'QA', 'asset_class': 'crypto'}], 1000, policy)
    assert result['allocations']['QA']['weight'] <= .2
    assert result['allocations']['QA']['budget'] == .3
    assert json.dumps(policy, sort_keys=True) == before


def test_template_operating_thresholds_are_actually_applied():
    policy = json.loads(Path('config/settings_template.json').read_text())['advanced_trading_layers']['ops_automation']
    engine = OpsAutomationEngine()
    assert engine.detect_anomalies({'reject_rate': .3, 'avg_slippage_bps': 40, 'quality_score': 50}, policy) == []
    assert set(engine.detect_anomalies({'reject_rate': .36, 'avg_slippage_bps': 46, 'quality_score': 44}, policy)) == {'high_reject_rate', 'high_slippage', 'low_execution_quality'}
    assert engine.detect_anomalies({'reject_rate': .1}, dict(policy, max_reject_rate=.05)) == ['high_reject_rate']


def test_disabled_operating_monitor_does_not_act_and_rollback_remains_a_proposal():
    assert OpsAutomationEngine().detect_anomalies({'reject_rate': 1}, {'enabled': False}) == []
    proposal = OpsAutomationEngine().build_rollback_action(['high_reject_rate'], {'auto_rollback': False})
    assert proposal['should_rollback'] is False and proposal['action'] == 'none'
