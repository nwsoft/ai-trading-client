from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from trading.runtime_policy_recovery import observe_execution_policy,apply_runtime_policy,cancel_runtime_policy
from trading.strategy_validation_lab import run_validation_lab


def owner(tmp_path):
    return SimpleNamespace(settings={'account_id':'fixture'}, recorder=SimpleNamespace(db_path=tmp_path/'trading.db'))


def policy(**changes):
    return {'execution_optimizer':{'enabled':True,'max_retries':1,'timeout_ms':3000,
            'max_slippage_bps':20.,'fallback_market':False,**changes},
            'ops_automation':{'enabled':True,'auto_rollback':True},
            'profitability_validation':{'hard_stop_mdd':.2},
            'position_sizing_policy':{'risk_per_trade_percent':.1}}


@pytest.mark.parametrize('source', ['binance','bybit','okx','bitget','upbit','bithumb','coinone','kiwoom','shinhan','mirae','kis'])
def test_recovery_reaches_real_policy_getter_without_raising_risk_or_changing_settings(tmp_path,source):
    o=owner(tmp_path); healthy=policy(); baseline=deepcopy(healthy)
    recorded=observe_execution_policy(o,source,'live',healthy,{'attempted_orders':3},[])
    assert recorded['status']=='stable_snapshot_recorded'
    risky=policy(max_retries=3,timeout_ms=500,max_slippage_bps=80.,fallback_market=True)
    changed=observe_execution_policy(o,source,'live',risky,{'attempted_orders':3},['high_slippage'])
    assert changed['status']=='restored'
    effective=apply_runtime_policy(o,source,'live',risky)
    assert effective['execution_optimizer']==healthy['execution_optimizer']
    assert effective['profitability_validation']==risky['profitability_validation']
    assert healthy==baseline and risky['execution_optimizer']['max_retries']==3
    assert changed['automatic_live_resume'] is False
    # Different mode, account and venue cannot inherit this restore.
    assert apply_runtime_policy(o,source,'paper',risky)==risky
    other=owner(tmp_path);other.settings={'account_id':'other'}
    assert apply_runtime_policy(other,source,'live',risky)==risky
    restarted=owner(tmp_path)
    assert apply_runtime_policy(restarted,source,'live',risky)==effective
    cancel_runtime_policy(restarted,source,'live')
    assert apply_runtime_policy(restarted,source,'live',risky)==risky
    assert observe_execution_policy(restarted,source,'live',risky,{'attempted_orders':3},['high_slippage'])['status']=='cancelled_by_user'


def test_no_attempts_no_rollback_or_false_stable_baseline(tmp_path):
    o=owner(tmp_path)
    assert observe_execution_policy(o,'okx','live',policy(),{'attempted_orders':0},[])['status']=='no_execution_sample'
    result=observe_execution_policy(o,'okx','live',policy(),{'attempted_orders':1},['high_slippage'])
    assert result['status']=='compatible_stable_snapshot_required'


def test_old_version_and_stale_snapshot_refused(tmp_path):
    o=owner(tmp_path)
    with patch('trading.runtime_policy_recovery.time.time', return_value=1.):
        observe_execution_policy(o,'okx','live',policy(),{'attempted_orders':3},[])
    assert observe_execution_policy(o,'okx','live',policy(max_retries=3),{'attempted_orders':1},['high_reject_rate'])['status']=='compatible_stable_snapshot_required'


def test_restore_is_read_only_and_tampered_override_cannot_change_protected_fields(tmp_path):
    o=SimpleNamespace(settings={'account_id':'fixture'})
    observe_execution_policy(o,'okx','live',policy(),{'attempted_orders':3},[])
    risky=policy(max_retries=3)
    observe_execution_policy(o,'okx','live',risky,{'attempted_orders':1},['high_reject_rate'])
    row=next(iter(o._policy_recovery_state.values()))
    row['active']['override']['enabled']=False
    assert apply_runtime_policy(o,'okx','live',risky)==risky


def test_replay_percentages_and_costs_are_not_zero_or_double_charged():
    rows=[{'gross_pnl_percent':2.,'net_pnl_percent':1.,'cost_percent':1.} for _ in range(10)]
    result=run_validation_lab(rows,initial_capital=10000)
    assert result['train_net_pnl']==600
    assert result['out_of_sample_net_pnl']==400
    assert result['cost_sensitivity']['base']==1000
    assert result['cost_sensitivity']['cost_2x']==0
    assert result['walkforward']['method']=='closed_trade_window_stability_not_retrained_oos'
    assert not result['auto_promoted']


def test_missing_cost_composition_is_unknown_not_zero():
    result=run_validation_lab([{'return_percent':1.}]*5)
    assert result['cost_sensitivity']['base']==500
    assert result['cost_sensitivity']['cost_2x'] is None
    assert result['cost_sensitivity_status']=='cost_components_unavailable'


def test_missing_cost_evidence_cannot_become_promotion_ready_after_paper(tmp_path):
    from trading.custom_strategy_pipeline import CustomStrategyPipeline
    from tests.test_ai_custom_completion_3906 import _rules
    pipeline=CustomStrategyPipeline(storage_path=str(tmp_path/'strategies.json'),min_paper_trades=3)
    row=pipeline.submit(name='missing-cost-fixture',rules=_rules())
    pipeline.approve(row['strategy_key'],row['version_id'],approved_by='fixture')
    report=run_validation_lab([{'pnl':1.} for _ in range(20)],paper_trades=[{'pnl':1.} for _ in range(3)])
    assert not report['promotion_ready'] and report['cost_sensitivity']['cost_2x'] is None
    pipeline.record_validation_lab(row['strategy_key'],row['version_id'],report)
    updated=pipeline.record_paper_validation(row['strategy_key'],row['version_id'],trades=3,metrics={'net_pnl':3.})
    assert not updated['validation_lab']['promotion_ready']
