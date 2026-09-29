"""Bounded account-owner memory projection; no I/O, inference or order APIs."""
import threading
import time
import math
from copy import deepcopy
from uuid import uuid4
from .strategy_scope import canonical_venue

_lock = threading.RLock()


def mode_for(owner, source):
    try:
        from .exchanges.venue_capabilities import CRYPTO_VENUE_ORDER
        from .execution_mode import resolve_crypto_execution_mode
        if source in CRYPTO_VENUE_ORDER:
            return resolve_crypto_execution_mode(getattr(owner, 'settings', {}), source).value
        mode = str(getattr(owner, '_active_execution_mode', 'unknown'))
        return {'mock': 'paper', 'live_api': 'live'}.get(mode, mode)
    except Exception:
        return 'unknown'


def generation(owner, source):
    try:
        with _lock:
            return (getattr(owner, '_operation_generations', {}) or {}).get(canonical_venue(source), 0)
    except Exception:
        return None


def publish(owner, source, kind, *, mode=None, expected_generation=None, **evidence):
    try:
        if kind not in {'regime', 'candidate', 'runtime'}:
            return
        source = canonical_venue(source)
        mode = str(getattr(mode, 'value', mode) or mode_for(owner, source))
        mode = {'mock': 'paper', 'live_api': 'live'}.get(mode, mode)
        if mode not in {'paper', 'live', 'learning'}:
            return
        allowed = {'observed', 'confirmed', 'changed', 'symbol', 'signal', 'reason',
                   'strategy_key', 'version_id', 'strategy_name', 'timeframe',
                   'bar_timestamp', 'allowed', 'code', 'basis', 'base_signal'}
        row = {k: (v[:300] if isinstance(v, str) else v)
               for k,v in evidence.items() if k in allowed and
               (v is None or isinstance(v, (str, bool, int, float))) and
               (not isinstance(v, float) or math.isfinite(v))}
        row['observed_at'] = time.time()
        if isinstance(evidence.get('checks'), list):
            row['checks'] = [{'passed': item.get('passed') is True,
                              'reason': str(item.get('reason') or '')[:300]}
                             for item in evidence['checks'][:20] if isinstance(item, dict)]
        with _lock:
            if expected_generation is not None and expected_generation != generation(owner, source):
                return
            store = getattr(owner, '_operation_evidence', None)
            if not isinstance(store, dict):
                store = {}
                owner._operation_evidence = store
            key = (source, mode)
            if key not in store:
                if len(store) >= 33:
                    store.pop(next(iter(store)))
                store[key] = {'session': uuid4().hex, 'source': source, 'mode': mode}
            if kind == 'regime' and (row.get('observed') or row.get('confirmed')):
                # Bounded session-only state transitions, not a price/probability series.
                point = {name: str(row.get(name) or '')[:80]
                         for name in ('observed', 'confirmed', 'symbol', 'timeframe')}
                history = store[key].setdefault('regime_history', [])
                if not history or any(history[-1].get(name) != point[name] for name in point):
                    history.append({**point, 'observed_at': row['observed_at']})
                    del history[:-24]
            store[key][kind] = row
    except Exception:
        # Presentation failure must never interrupt execution/protection.
        return


def candidate(owner, result, context, mode, expected_generation=None):
    try:
        rules = result.selected_rules or {}
        timeframe = str(rules.get('decision_timeframe') or rules.get('timeframe') or '')
        scoped = (context.get('_strategy_timeframe_contexts') or {}).get(timeframe) or {}
        checks = []
        evaluation = result.evaluation or {}
        pending = [evaluation.get('expression')]
        visited = 0
        while pending and len(checks) < 20 and visited < 100:
            node = pending.pop()
            visited += 1
            if not isinstance(node, dict):
                continue
            if 'reason' in node:
                checks.append({'passed': node.get('passed'), 'reason': node.get('reason')})
            pending.extend(list(node.get('children') or [])[:20])
        for group in ('all', 'any'):
            for item in list(evaluation.get(group) or [])[:20-len(checks)]:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    checks.append({'passed': item[0], 'reason': item[1]})
        publish(owner, result.target, 'candidate', mode=mode, expected_generation=expected_generation,
                symbol=result.symbol, signal=result.final_signal, base_signal=result.base_signal,
                reason=result.reason, allowed=result.allowed,
                strategy_key=result.strategy_key, version_id=result.strategy_version_id,
                strategy_name=result.strategy_name, timeframe=timeframe,
                bar_timestamp=scoped.get('_bar_timestamp'), checks=checks)
    except Exception:
        return


def snapshot(owner, source, mode):
    with _lock:
        result = deepcopy((getattr(owner, '_operation_evidence', {}) or {}).get(
            (canonical_venue(source), mode), {})) if owner is not None else {}
    return {'schema_version': 1, 'source': canonical_venue(source), 'mode': mode,
            'status': 'observed' if result else 'unavailable',
            'protection_status': 'not_projected', 'read_only': True, **result}


def reset(owner, source):
    with _lock:
        if owner is None:
            return
        epochs = getattr(owner, '_operation_generations', None)
        if not isinstance(epochs, dict):
            epochs = {}
            owner._operation_generations = epochs
        venue = canonical_venue(source)
        epochs[venue] = epochs.get(venue, 0) + 1
        store = getattr(owner, '_operation_evidence', {}) or {}
        for key in list(store):
            if key[0] == venue:
                store.pop(key, None)
