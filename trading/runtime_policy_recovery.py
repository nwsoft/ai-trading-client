"""Reduction-only runtime execution recovery; user settings/risk/mode stay intact."""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import json
import time
import threading
import math
from pathlib import Path
import sqlite3
from contextlib import contextmanager, closing
from config.app_version import RELEASE_VERSION
from .strategy_scope import canonical_venue

_lock = threading.RLock()
FIELDS = {'max_retries', 'timeout_ms', 'fallback_market', 'max_slippage_bps'}


def _hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _validated_override(base, override):
    if not isinstance(override, dict) or set(override) - FIELDS:
        raise ValueError('unsupported_recovery_field')
    for key, value in override.items():
        if key == 'fallback_market':
            if not isinstance(value, bool) or (value and not base.get(key, True)):
                raise ValueError('recovery_would_enable_fallback')
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('invalid_recovery_number')
        elif key == 'timeout_ms' and not (300 <= value <= 30000 and int(value) == value):
            raise ValueError('invalid_timeout')
        elif key == 'max_retries' and not (0 <= value <= min(3, base.get(key, 1)) and int(value) == value):
            raise ValueError('recovery_would_increase_retries')
        elif key == 'max_slippage_bps' and not (0 < value <= base.get(key, 35)):
            raise ValueError('recovery_would_increase_slippage_limit')
    return deepcopy(override)


@contextmanager
def _transaction(owner):
    with _lock:
        path = getattr(getattr(owner, 'recorder', None), 'db_path', None)
        if not isinstance(path, (str, Path)) or not str(path):
            state = getattr(owner, '_policy_recovery_state', {})
            owner._policy_recovery_state = state
            yield state
            return
        store_path = Path(path).resolve().parent / 'runtime_execution_recovery.db'
        store_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(store_path, timeout=2)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS execution_recovery (id INTEGER PRIMARY KEY, state TEXT NOT NULL)')
            db.execute('BEGIN IMMEDIATE')
            saved = db.execute('SELECT state FROM execution_recovery WHERE id=1').fetchone()
            state = json.loads(saved[0]) if saved else {}
            yield state
            db.execute('INSERT OR REPLACE INTO execution_recovery VALUES (1, ?)',
                       (json.dumps(state, sort_keys=True, allow_nan=False),))
            owner._policy_recovery_state = deepcopy(state)


def apply_runtime_policy(owner, source, mode, layers):
    source = canonical_venue(source)
    original = deepcopy(layers or {})
    try:
        from .opportunity_coordinator import account_scope_for
        key = account_scope_for(owner, mode) + ':' + source
        with _transaction(owner) as state:
            row = state.get(key) or {}
            active = row.get('active') or {}
            if (active.get('version') == RELEASE_VERSION and active.get('base_hash') == _hash(original)
                and 0 <= time.time() - float(active.get('at', 0)) <= 86400):
                original.setdefault('execution_optimizer', {}).update(
                    _validated_override(original.get('execution_optimizer') or {}, active.get('override') or {}))
        return original
    except Exception:
        # Missing/corrupt recovery evidence never disables normal hard guards.
        return original


def _observe_execution_policy(owner, source, mode, layers, metrics, anomalies):
    source = canonical_venue(source)
    """Called at the actual cycle end, not by UI polling or diagnostic reads."""
    result = {'should_rollback': False, 'action': 'none', 'status': 'not_requested',
              'automatic_live_resume': False, 'user_settings_changed': False,
              'risk_policy_changed': False, 'reason': ','.join(anomalies)}
    ops = dict((layers or {}).get('ops_automation') or {})
    if not ops.get('enabled') or not ops.get('auto_rollback', True): return result
    attempts = int(metrics.get('attempted_orders', 0) or 0)
    if attempts <= 0:
        result['status'] = 'no_execution_sample'
        return result
    try:
        from .opportunity_coordinator import account_scope_for
        key = account_scope_for(owner, mode) + ':' + source
        policy = {k: v for k, v in dict((layers or {}).get('execution_optimizer') or {}).items() if k in FIELDS}
        with _transaction(owner) as state:
            row = state.setdefault(key, {})
            digest = _hash(policy)
            if not anomalies:
                healthy = row.get('healthy') or {}
                count = int(healthy.get('attempts', 0)) if healthy.get('hash') == digest else 0
                row['healthy'] = {'hash': digest, 'attempts': min(100, count + attempts)}
                if count + attempts >= 3:
                    row['stable'] = {'policy': policy, 'hash': digest, 'at': time.time(), 'version': RELEASE_VERSION}
                    result.update(status='stable_snapshot_recorded', snapshot_hash=digest)
                else: result['status'] = 'stable_sample_accumulating'
                return result
            result.update(should_rollback=True, action='restore_reduction_only_execution_policy')
            stable = row.get('stable') or {}
            if stable.get('version') != RELEASE_VERSION or not 0 <= time.time() - float(stable.get('at', 0)) <= 7*86400:
                result['status'] = 'compatible_stable_snapshot_required'
                return result
            previous = stable.get('policy') or {}
            if stable.get('hash') != _hash(previous):
                result['status'] = 'snapshot_integrity_failed'
                return result
            override = {}
            if 'max_retries' in previous and 'max_retries' in policy:
                override['max_retries'] = min(int(previous['max_retries']), int(policy['max_retries']))
            if 'max_slippage_bps' in previous and 'max_slippage_bps' in policy:
                override['max_slippage_bps'] = min(float(previous['max_slippage_bps']), float(policy['max_slippage_bps']))
            if 'fallback_market' in previous and 'fallback_market' in policy:
                override['fallback_market'] = bool(previous['fallback_market']) and bool(policy['fallback_market'])
            if 'timeout_ms' in previous:
                override['timeout_ms'] = max(300, min(30000, int(previous['timeout_ms'])))
            override = {k: v for k, v in override.items() if policy.get(k) != v}
            override = _validated_override(policy, override)
            if not override:
                result['status'] = 'no_safe_policy_change_available'
                return result
            # Explicitly bounded once per base policy, not an oscillating loop.
            base_hash = _hash(layers)
            if row.get('cancelled_base_hash') == base_hash:
                result['status'] = 'cancelled_by_user'
                return result
            if (row.get('active') or {}).get('base_hash') == base_hash:
                result['status'] = 'already_restored_recheck_required'
                return result
            row['active'] = {'override': override, 'base_hash': base_hash, 'at': time.time(), 'version': RELEASE_VERSION}
            row['last_result'] = {**result, 'status': 'restored', 'fields': list(override), 'snapshot_hash': stable['hash'], 'at': time.time()}
            return deepcopy(row['last_result'])
    except Exception:
        return {**result, 'status': 'recovery_storage_or_validation_failed'}


def observe_execution_policy(owner, source, mode, layers, metrics, anomalies):
    source = canonical_venue(source)
    result = _observe_execution_policy(owner, source, mode, layers, metrics, anomalies)
    normalized_mode = str(getattr(mode, 'value', mode)).lower()
    normalized_mode = {'mock': 'paper', 'live_api': 'live'}.get(normalized_mode, normalized_mode)
    with _lock:
        store = getattr(owner, '_last_policy_recovery_results', {})
        store[(source, normalized_mode)] = {**result, 'observed_at': time.time()}
        owner._last_policy_recovery_results = store
    return result


def cancel_runtime_policy(owner, source, mode):
    source = canonical_venue(source)
    from .opportunity_coordinator import account_scope_for
    key = account_scope_for(owner, mode) + ':' + source
    with _transaction(owner) as state:
        row = state.setdefault(key, {})
        active = row.pop('active', {})
        if active.get('base_hash'):
            row['cancelled_base_hash'] = active['base_hash']
    result = {'status': 'cancelled_by_user', 'user_settings_changed': False, 'risk_policy_changed': False,
              'automatic_live_resume': False, 'orders_submitted': False, 'observed_at': time.time()}
    normalized_mode = str(getattr(mode, 'value', mode)).lower()
    normalized_mode = {'mock': 'paper', 'live_api': 'live'}.get(normalized_mode, normalized_mode)
    owner._last_policy_recovery_results = {**getattr(owner, '_last_policy_recovery_results', {}),
                                           (source, normalized_mode): result}
    return result
