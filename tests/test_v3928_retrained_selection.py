"""First eligible leaf contracts; runner fixtures do not grant IR support."""
from copy import deepcopy

import pytest

from trading.declarative_strategy_engine import DeclarativeStrategyEngine as Engine
from trading.noah_strategy_ir import NoahStrategyIR
from trading.retrained_strategy_evaluation import _parameter, run_retrained_evaluation
from tests.test_v3926_retrained_evaluation import candles, rules


def leaf(field='rsi', value=50, operator='lt'):
    return {'field': field, 'operator': operator, 'value': value}


EMA = leaf({'indicator': 'ema', 'period': 17, 'timeframe': '1h', 'source': 'close'}, 100, 'gt')


def at_path(tree, path):
    for key in path:
        tree = tree[key]
    return tree


def evaluate_and_check_only_leaf(original, path, expected_values=None):
    before = deepcopy(original)
    chosen_original = at_path(original, path)
    calls = []
    def runner(variant, rows, **kw):
        value = at_path(variant, path)
        restored = deepcopy(variant)
        node = at_path(restored, path[:-1])
        node[path[-1]] = chosen_original
        # Compare everything: branches, other thresholds, exits and risk settings.
        assert restored == before
        calls.append((value, kw['entry_start_ms']))
        return {'decisions': 5, 'net_pnl_percent': value / 10 + 1, 'max_drawdown_percent': .1}
    result = run_retrained_evaluation(original, candles(), runner=runner,
                                     cost_profile={'rates': {'fee': .001}})
    assert result['proposal']['parameter_path'] == path
    assert result['proposal']['field'] == at_path(original, path[:-1])['field']
    assert result['proposal']['original_value'] == chosen_original
    assert result['proposal']['risk_fields_changed'] is False
    assert original == before
    assert not result['auto_applied'] and not result['live_permission_granted']
    assert result['review_required']
    if expected_values is not None:
        # Check both fitting folds, never infer fit candidates from the holdout.
        assert [v for v, start in calls if start is None] == expected_values * 2
    return result


@pytest.mark.parametrize('field', [None, ['rsi'], 7, True,
    {'indicator': 'rsi', 'period': 14, 'timeframe': '15m', 'source': 'close'},
    {'user_indicator': 'fixture'}, {'state_variable': 'fixture'}],
    ids=['none', 'list', 'number', 'bool', 'structured-rsi', 'user-indicator', 'state-variable'])
def test_nonstring_field_is_skipped_without_hiding_later_numeric_leaf(field):
    original = rules()
    original['executable_entry'] = {'all': [leaf(field), leaf('adx', 25, 'gt')]}
    path = ['executable_entry', 'all', 1, 'value']
    assert _parameter(original) == (path, 'adx', 25., (0., 100.))
    evaluate_and_check_only_leaf(original, path, [22.5, 25., 27.5])


# f209608 already covers [EMA, RSI]; these are the two missing orderings.
@pytest.mark.parametrize('conditions,index', [([leaf(), EMA], 0), ([EMA, leaf(), EMA], 1)],
                         ids=['rsi-ema', 'ema-rsi-ema'])
def test_structured_fields_around_numeric_leaf_preserve_all_other_rules(conditions, index):
    original = rules()
    original['executable_entry'] = {'all': deepcopy(conditions)}
    evaluate_and_check_only_leaf(original, ['executable_entry', 'all', index, 'value'], [45., 50., 55.])


@pytest.mark.parametrize('text,suffix', [
    ('(rsi < 40 or adx > 25) and volume_ratio > 2', ['children', 0, 'children', 0, 'condition', 'value']),
    ('(adx > 25 and rsi < 40) or atr_percent < 2', ['children', 0, 'children', 0, 'condition', 'value']),
    ('signal == LONG or (rsi < 40 and adx > 25)', ['children', 1, 'children', 0, 'condition', 'value']),
])
def test_supported_expression_groups_select_exact_depth_first_leaf(text, suffix):
    from trading.source_condition_compiler import ConditionCompiler
    original = rules()
    expression = ConditionCompiler().compile(text)
    assert Engine.validate_expression_graph(expression)['valid']
    original['executable_entry'] = {'expression': expression}
    assert Engine.validate_rule_spec(original)['valid']
    path = ['executable_entry', 'expression', *suffix]
    assert _parameter(original)[0] == path
    evaluate_and_check_only_leaf(original, path)


@pytest.mark.parametrize('conditions', [
    [leaf(), leaf('adx', 25, 'gt'), leaf('volume_ratio', 2)],
    [leaf('rsi', 40), leaf('rsi', 60)],
    [leaf('adx', 25, 'gt'), leaf('rsi', 50)],
])
def test_multiple_eligible_conditions_change_only_the_first(conditions):
    original = rules()
    original['executable_entry'] = {'all': conditions}
    original['executable_exit'] = {'all': [leaf('rsi', 70, 'gte')]}
    original['advanced_order_plan'] = {'partial_take_profits': [{'target_percent': 1., 'close_fraction': .4}]}
    evaluate_and_check_only_leaf(original, ['executable_entry', 'all', 0, 'value'])


@pytest.mark.parametrize('first_branch', ['LONG', 'SHORT'])
@pytest.mark.parametrize('executable_eligible', [True, False])
def test_executable_priority_and_independent_long_short_branches(first_branch, executable_eligible):
    original = rules()
    second_branch = 'SHORT' if first_branch == 'LONG' else 'LONG'
    # Deliberately insert independent_entries before executable_entry in the dict.
    original = {'independent_entries': {
        first_branch: {'all': [leaf('adx', 25, 'gt')]},
        second_branch: {'all': [leaf('rsi', 70, 'gte')]},
    }, **original}
    original['executable_entry'] = {'all': [leaf() if executable_eligible else deepcopy(EMA)]}
    path = (['executable_entry', 'all', 0, 'value'] if executable_eligible else
            ['independent_entries', first_branch, 'all', 0, 'value'])
    assert _parameter(original)[0] == path
    evaluate_and_check_only_leaf(original, path)


@pytest.mark.parametrize('value', [True, False])
def test_boolean_threshold_is_not_zero_or_one(value):
    original = rules()
    original['executable_entry'] = {'all': [leaf(value=value)]}
    assert _parameter(original) is None
    original['executable_entry']['all'].append(leaf('adx', 25, 'gt'))
    evaluate_and_check_only_leaf(original, ['executable_entry', 'all', 1, 'value'], [22.5, 25., 27.5])


@pytest.mark.parametrize('field,value,bounds,candidates', [
    ('rsi', 50, (0., 100.), [45., 50., 55.]),
    ('adx', 50, (0., 100.), [45., 50., 55.]),
    ('volume_ratio', 2, (.05, 100.), [1.8, 2., 2.2]),
    ('atr_percent', 1, (.01, 100.), [.9, 1., 1.1]),
])
@pytest.mark.parametrize('operator', ['lt', 'lte', 'gt', 'gte'])
def test_supported_numeric_bounds_and_candidate_grid(field, value, bounds, candidates, operator):
    original = rules()
    original['executable_entry'] = {'all': [leaf(field, value, operator)]}
    path = ['executable_entry', 'all', 0, 'value']
    assert _parameter(original) == (path, field, float(value), bounds)
    evaluate_and_check_only_leaf(original, path, candidates)


@pytest.mark.parametrize('field,lower,lower_candidates', [
    ('rsi', 0., [0.]), ('adx', 0., [0.]),
    ('volume_ratio', .05, [.05, .055]), ('atr_percent', .01, [.01, .011]),
])
@pytest.mark.parametrize('edge', ['lower', 'upper', 'below', 'above'])
def test_candidate_clamping_and_deduplication(field, lower, lower_candidates, edge):
    value, candidates = {'lower': (lower, lower_candidates), 'upper': (100., [90., 100.]),
                         'below': (-10., [lower]), 'above': (1000., [100.])}[edge]
    original = rules()
    original['executable_entry'] = {'all': [leaf(field, value)]}
    evaluate_and_check_only_leaf(original, ['executable_entry', 'all', 0, 'value'], candidates)


@pytest.mark.parametrize('operator', ['eq', 'ne', 'crosses_above', 'crosses_below', 'gt_field'])
def test_nonrefittable_comparisons_do_not_shadow_later_eligible_leaf(operator):
    original = rules()
    original['executable_entry'] = {'all': [leaf(operator=operator), leaf('adx', 25, 'gt')]}
    assert _parameter(original)[0] == ['executable_entry', 'all', 1, 'value']


def test_raw_all_any_nesting_remains_unsupported_by_ir_and_real_replay():
    from tests.test_ai_custom_completion_3906 import _rules
    original = _rules()
    original['executable_entry'] = {'all': [{'any': [leaf(), leaf('adx', 25, 'gt')]}]}
    assert not Engine.validate_rule_spec(original)['valid']
    assert NoahStrategyIR.compile(original)['support']['status'] == 'unsupported'
    before = deepcopy(original)
    result = run_retrained_evaluation(original, candles(), cost_profile={'rates': {'fee': .001}})
    assert result['status'] == 'replay_or_evidence_not_supported'
    assert not result.get('proposal', {}).get('accepted_for_review') and original == before


def test_accepted_report_persistence_cannot_change_approved_version_or_activate(tmp_path):
    from trading.custom_strategy_pipeline import CustomStrategyPipeline
    from tests.test_ai_custom_completion_3906 import _rules
    storage = tmp_path / 'strategies.json'
    pipeline = CustomStrategyPipeline(storage_path=str(storage))
    submitted = pipeline.submit(name='accepted-refit-fixture', rules=_rules())
    key, version_id = submitted['strategy_key'], submitted['version_id']
    approved = pipeline.approve(key, version_id, approved_by='fixture-user')
    result = evaluate_and_check_only_leaf(approved['rules'], ['executable_entry', 'all', 0, 'value'])
    assert result['status'] == 'candidate_ready_for_paper_review'
    assert result['proposal']['accepted_for_review'] is True
    assert result['proposal']['candidate_value'] != result['proposal']['original_value']
    report = {'retrained_evaluation': result, 'promotion_ready': False, 'auto_promoted': False}
    saved = pipeline.record_validation_lab(key, version_id, report)
    restarted = CustomStrategyPipeline(storage_path=str(storage))
    assert len(restarted.list_versions(key)) == 1
    assert restarted.get_version(key, version_id) == saved
    allowed_changes = {'validation_lab', 'promotion_history', 'updated_at'}
    assert {k: v for k, v in saved.items() if k not in allowed_changes} == {
        k: v for k, v in approved.items() if k not in allowed_changes}
    for protected in ('rules', 'strategy_ir', 'ir_hash', 'approval', 'status'):
        assert saved[protected] == approved[protected]
    assert saved['status'] == 'approved' and saved['validation_lab'] == report
    assert saved['promotion_history'][-1]['auto_promoted'] is False


def test_budget_exceeded_after_last_replay_revokes_successful_proposal(monkeypatch):
    calls = 0
    def runner(variant, rows, **kw):
        nonlocal calls
        calls += 1
        value = variant['executable_entry']['expression']['condition']['value']
        return {'decisions': 5, 'net_pnl_percent': value / 10, 'max_drawdown_percent': .1}
    monkeypatch.setattr('trading.retrained_strategy_evaluation.time.perf_counter',
                        lambda: 16. if calls == 12 else 0.)
    result = run_retrained_evaluation(rules(), candles(), runner=runner,
                                     cost_profile={'rates': {'fee': .001}}, budget_seconds=15.)
    assert result['status'] == 'evaluation_resource_budget_exceeded'
    assert result['replay_calls'] == 12 and len(result['folds']) == 2
    assert not result['proposal']['accepted_for_review']
    assert not result['auto_applied'] and not result['live_permission_granted']
