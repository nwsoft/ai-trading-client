"""Strict input evidence must fail before replay, without inventing a hash."""
from copy import deepcopy
import json
from unittest.mock import Mock

import pytest

from trading.retrained_strategy_evaluation import run_retrained_evaluation
from tests.test_v3926_retrained_evaluation import candles, rules


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf')],
                         ids=['nan', 'positive-infinity', 'negative-infinity'])
@pytest.mark.parametrize('location', ['rules', 'rows', 'timeframe_rows'])
def test_nonfinite_evidence_cannot_replay_hash_or_approve(value, location):
    original = rules()
    original['executable_entry'] = {'all': [
        {'field': 'rsi', 'operator': 'lt', 'value': value if location == 'rules' else 50},
        {'field': 'adx', 'operator': 'gt', 'value': 25},
    ]}
    rows, timeframes = candles(), {'1h': candles(800)}
    if location == 'rows':
        rows[20][4] = value
    elif location == 'timeframe_rows':
        # Even evidence outside the replay cut is part of the declared input hash.
        timeframes['1h'][-1][4] = value
    evidence = {'rules': original, 'rows': rows, 'timeframes': timeframes}
    before = json.dumps(evidence, sort_keys=True)
    runner = Mock(return_value={'decisions': 5, 'net_pnl_percent': 1., 'max_drawdown_percent': 1.})
    result = run_retrained_evaluation(original, rows, timeframe_rows=timeframes,
                                     cost_profile={'rates': {'fee': .001}}, runner=runner)
    assert result['status'] == 'input_evidence_not_supported'
    assert result['input_validation_error'] == 'strict_json_evidence_required'
    assert result['input_sha256'] is None and result['replay_calls'] == 0
    assert result['folds'] == [] and not result.get('proposal', {}).get('accepted_for_review')
    assert not result['auto_applied'] and not result['live_permission_granted']
    assert result['review_required']
    runner.assert_not_called()
    assert json.dumps(evidence, sort_keys=True) == before
    # The failure report itself can be persisted by strict JSON writers.
    json.dumps(result, allow_nan=False)


def test_finite_evidence_hash_includes_unselected_rules_and_unused_timeframes():
    import hashlib
    original, rows, timeframes = rules(), candles(), {'1h': candles(800)}
    before = deepcopy(original)
    runner = Mock(return_value={'decisions': 5, 'net_pnl_percent': 1., 'max_drawdown_percent': 1.})
    result = run_retrained_evaluation(original, rows, timeframe_rows=timeframes,
                                     cost_profile={'rates': {'fee': .001}}, runner=runner)
    expected = hashlib.sha256(json.dumps({'rules': original, 'rows': rows, 'timeframes': timeframes},
                                         sort_keys=True, allow_nan=False).encode()).hexdigest()
    assert result['input_sha256'] == expected and original == before
    changed = deepcopy(original)
    changed['risk_model']['stop_loss_percent'] = 2.
    assert run_retrained_evaluation(changed, rows, timeframe_rows=timeframes,
                                   cost_profile={'rates': {'fee': .001}}, runner=runner)['input_sha256'] != expected
    timeframes['1h'][-1][4] = 102.
    assert run_retrained_evaluation(original, rows, timeframe_rows=timeframes,
                                   cost_profile={'rates': {'fee': .001}}, runner=runner)['input_sha256'] != expected


def test_failed_evaluation_report_can_be_saved_without_approval_or_new_version(tmp_path):
    from trading.custom_strategy_pipeline import CustomStrategyPipeline
    from tests.test_ai_custom_completion_3906 import _rules
    storage = tmp_path / 'strategies.json'
    pipeline = CustomStrategyPipeline(storage_path=str(storage))
    submitted = pipeline.submit(name='invalid-evidence-fixture', rules=_rules())
    key, version_id = submitted['strategy_key'], submitted['version_id']
    approved = pipeline.approve(key, version_id, approved_by='fixture-user')
    rows = candles()
    rows[20][4] = float('nan')
    runner = Mock()
    report = run_retrained_evaluation(approved['rules'], rows, runner=runner,
                                     cost_profile={'rates': {'fee': .001}})
    assert report['status'] == 'input_evidence_not_supported'
    saved = pipeline.record_validation_lab(key, version_id, {'retrained_evaluation': report})
    restarted = CustomStrategyPipeline(storage_path=str(storage))
    assert restarted.get_version(key, version_id) == saved
    assert len(restarted.list_versions(key)) == 1
    for protected in ('rules', 'strategy_ir', 'ir_hash', 'approval', 'status'):
        assert saved[protected] == approved[protected]
    assert not saved['promotion_history'][-1]['promotion_ready']
    assert not saved['promotion_history'][-1]['auto_promoted']
    runner.assert_not_called()
