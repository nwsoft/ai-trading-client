"""Bounded parameter fitting on past candles, then untouched chronological tests.

This fits a declared entry parameter, not LLM weights. Results are review
proposals; they never edit an approved strategy or grant trading permission.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import math
import time


def _parameter(rules):
    bounds = {'rsi': (0., 100.), 'adx': (0., 100.), 'volume_ratio': (.05, 100.), 'atr_percent': (.01, 100.)}
    def find(node, path):
        if isinstance(node, dict):
            field, value = node.get('field'), node.get('value')
            if (isinstance(field, str) and field in bounds and node.get('operator') in {'lt', 'lte', 'gt', 'gte'}
                and not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)):
                return path + ['value'], field, float(value), bounds[field]
            for key, child in node.items():
                result = find(child, path + [key])
                if result: return result
        elif isinstance(node, list):
            for index, child in enumerate(node):
                result = find(child, path + [index])
                if result: return result
        return None
    for group in ('executable_entry', 'independent_entries'):
        result = find(rules.get(group), [group])
        if result: return result
    return None


def run_retrained_evaluation(rules, rows, *, timeframe_rows=None, base_timeframe='15m',
                             cost_profile=None, horizon=12, runner=None, budget_seconds=15., entry_start_ms=None):
    result = {'method': 'expanding_window_entry_parameter_refit', 'status': 'not_evaluated',
              'auto_applied': False, 'live_permission_granted': False, 'review_required': True,
              'model_training': 'local_declared_parameter_grid_not_llm_weights', 'folds': [],
              'maximum_replay_calls': 12, 'future_performance_guaranteed': False}
    parameter = _parameter(rules)
    if not parameter:
        return {**result, 'status': 'declared_adjustable_entry_parameter_required'}
    if len(rows) < 400 or len(rows) > 3000:
        return {**result, 'status': 'bounded_history_required', 'required_candles': '400..3000'}
    if any(len(row) < 7 for row in rows) or any(a[0] >= b[0] or a[6] >= b[0] for a,b in zip(rows, rows[1:])):
        return {**result, 'status': 'ordered_closed_candle_evidence_required'}
    if not cost_profile or not isinstance(cost_profile.get('rates'), dict):
        return {**result, 'status': 'estimated_cost_profile_required'}
    if runner is None:
        from .custom_strategy_validator import run_historical_replay
        runner = run_historical_replay
    from .custom_strategy_validator import _required_history
    path, field, original, bounds = parameter
    values = sorted({round(max(bounds[0], min(bounds[1], original * factor)), 6) for factor in (.9, 1., 1.1)})
    start = max(_required_history(rules) + horizon + 10, len(rows)//2)
    span = (len(rows) - start)//2
    if span < max(40, horizon+10):
        return {**result, 'status': 'training_or_test_history_insufficient'}
    started = time.perf_counter()
    calls = 0
    def replay(value, end, test_start=None, cost_multiple=1.):
        nonlocal calls
        if calls >= 12 or time.perf_counter() - started > budget_seconds:
            raise TimeoutError('evaluation_resource_budget_exceeded')
        calls += 1
        variant = deepcopy(rules)
        node = variant
        for key in path[:-1]: node = node[key]
        node[path[-1]] = value
        cut = rows[end-1][6]
        scoped = {tf: [list(r) for r in candles if len(r)>=7 and r[6]<=cut]
                  for tf, candles in (timeframe_rows or {}).items()}
        costs = deepcopy(cost_profile)
        costs['rates'] = {k: v * cost_multiple if isinstance(v,(float,int)) and not isinstance(v,bool) else v
                          for k,v in costs['rates'].items()}
        return runner(variant, rows[:end], timeframe_klines=scoped, base_timeframe=base_timeframe,
                      cost_profile=costs, horizon=horizon,
                      entry_start_ms=rows[test_start][0] if test_start is not None else entry_start_ms)
    def quality(metrics):
        try:
            n, pnl, dd = (float(metrics[key]) for key in ('decisions','net_pnl_percent','max_drawdown_percent'))
            if not all(math.isfinite(v) for v in (n,pnl,dd)) or n<3 or dd<0 or dd>10:
                return None
            return pnl - dd
        except (KeyError, TypeError, ValueError): return None
    try:
        for fold in range(2):
            boundary, end = start+fold*span, start+(fold+1)*span
            fitted = [(value, replay(value, boundary)) for value in values]
            candidates = [(value, metrics) for value,metrics in fitted if quality(metrics) is not None]
            if not candidates:
                result['status'] = 'training_quality_or_sample_insufficient'
                break
            # Ties prefer the unchanged baseline. Test results cannot affect fit.
            selected, training = max(candidates, key=lambda pair:(quality(pair[1]), -abs(pair[0]-original)))
            baseline, tested = replay(original,end,boundary), replay(selected,end,boundary)
            stress = replay(selected,end,boundary,2.)
            test_ok = quality(tested) is not None and quality(baseline) is not None and quality(stress) is not None
            nondegraded = bool(test_ok and tested['net_pnl_percent']>=baseline['net_pnl_percent']
                               and stress['net_pnl_percent']>0)
            result['folds'].append({'training_end_ms': rows[boundary-1][6], 'test_start_ms':rows[boundary][0],
                'test_end_ms':rows[end-1][6], 'training_candles':boundary, 'test_candles':end-boundary,
                'chosen_value':selected, 'training_net_percent':training.get('net_pnl_percent'),
                'baseline_test_net_percent':baseline.get('net_pnl_percent'), 'candidate_test_net_percent':tested.get('net_pnl_percent'),
                'cost_2x_test_net_percent':stress.get('net_pnl_percent'), 'test_trades':tested.get('decisions'),
                'passed':nondegraded, 'train_and_test_entries_disjoint':True})
        if len(result['folds'])==2:
            improved = any(f['candidate_test_net_percent']>f['baseline_test_net_percent'] for f in result['folds'])
            acceptable = all(f['passed'] for f in result['folds']) and improved
            result['status'] = 'candidate_ready_for_paper_review' if acceptable else 'candidate_not_better_than_baseline'
            result['proposal'] = {'parameter_path':path,'field':field,'original_value':original,
                                  'candidate_value':result['folds'][-1]['chosen_value'], 'accepted_for_review':acceptable,
                                  'apply_path':'create_new_version_review_approve_then_paper', 'risk_fields_changed':False}
    except TimeoutError:
        result['status'] = 'evaluation_resource_budget_exceeded'
    except (ValueError, KeyError, TypeError):
        result['status'] = 'replay_or_evidence_not_supported'
    if time.perf_counter() - started > budget_seconds:
        result['status'] = 'evaluation_resource_budget_exceeded'
        if result.get('proposal'): result['proposal']['accepted_for_review'] = False
    result.update({'replay_calls':calls, 'elapsed_ms':round((time.perf_counter()-started)*1000,2),
                   'input_sha256':hashlib.sha256(json.dumps({'rules':rules,'rows':rows,'timeframes':timeframe_rows},
                                                           sort_keys=True,allow_nan=False).encode()).hexdigest()})
    return result
