"""Measured PAPER rule-evaluation intervals, never inferred application uptime.

Separate SQLite evidence avoids concurrent runtime/UI writes to strategy JSON.
Overlapping symbols/venues are unioned for each account-scoped trial attempt.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
from contextlib import closing
import hashlib
import json
import logging
import math
from pathlib import Path
import sqlite3
import time
import threading

_warning_lock = threading.Lock()
_db_init_lock = threading.Lock()
_last_warning = float("-inf")

def _warn(message):
    global _last_warning
    with _warning_lock:
        now = time.perf_counter()
        if now - _last_warning >= 60:
            _last_warning = now
            logging.getLogger(__name__).warning(message)



def _mark_incomplete(store, items):
    # One empty marker per attempt; no account/trade data or unbounded error log.
    for item in items:
        key = identity({**item, 'paper_observation_attempt_id': item['_paper_attempt_id']})
        try:
            Path(str(evidence_path(store)) + '.' + key + '.incomplete').touch(exist_ok=True)
        except OSError:
            _warn('PAPER time evidence is incomplete; marker could not be saved')


def evidence_path(store):
    return Path(store).with_suffix('.paper-runtime.sqlite3')


def identity(version):
    return hashlib.sha256(json.dumps([
        version.get('strategy_key'), version.get('version_id'),
        version.get('paper_observation_attempt_id'),
    ], separators=(',', ':')).encode()).hexdigest()


def _epoch(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('paper_time_zone_missing')
    return parsed.timestamp()


def _connect(path):
    # WAL conversion can report BUSY immediately on the first concurrent open.
    # Bound only initialization retries; orders are never retried here.
    with _db_init_lock:
        for attempt in range(4):
            db = sqlite3.connect(path, timeout=0.5)
            try:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('PRAGMA synchronous=NORMAL')
                db.execute('CREATE TABLE IF NOT EXISTS spans (key TEXT, start REAL, end REAL)')
                db.execute('CREATE INDEX IF NOT EXISTS span_lookup ON spans(key,start,end)')
                db.execute('CREATE TABLE IF NOT EXISTS totals (key TEXT PRIMARY KEY, count INTEGER, last REAL)')
                return db
            except sqlite3.Error as exc:
                db.close()
                if attempt == 3 or 'locked' not in str(exc).lower():
                    raise
                time.sleep(0.02)


def record_interval(store, strategies, start, end):
    """Clip completed evaluations to persisted permission windows/attempt IDs."""
    if not all(math.isfinite(v) for v in (start, end)) or end < start:
        raise ValueError('invalid_paper_runtime_interval')
    # Read the current, atomically replaced permission file. No stale grant cache.
    payload = json.loads(Path(store).read_text(encoding='utf-8'))
    current = {v.get('version_id'): v for values in payload.get('strategies', {}).values() for v in values}
    records = {}
    for item in strategies:
        version = current.get(item.get('version_id')) or {}
        if (version.get('strategy_key') != item.get('strategy_key')
                or not version.get('paper_observation_attempt_id')
                or version.get('paper_observation_attempt_id') != item.get('_paper_attempt_id')):
            continue
        clipped = []
        for window in version.get('paper_observation_windows') or []:
            lo = max(start, _epoch(window['started_at']))
            hi = min(end, _epoch(window['stopped_at'])) if window.get('stopped_at') else end
            if hi >= lo:
                clipped.append((lo, hi))
        if clipped:
            records[identity(version)] = clipped
    if not records:
        return
    db = _connect(evidence_path(store))
    try:
        with db:
            # Serialize all merges, including concurrent account runtime processes.
            db.execute('BEGIN IMMEDIATE')
            for key, intervals in records.items():
                for lo, hi in intervals:
                    overlaps = db.execute('SELECT rowid,start,end FROM spans WHERE key=? AND start<=? AND end>=?', (key, hi, lo)).fetchall()
                    if overlaps:
                        lo = min(lo, min(row[1] for row in overlaps))
                        hi = max(hi, max(row[2] for row in overlaps))
                        db.executemany('DELETE FROM spans WHERE rowid=?', [(row[0],) for row in overlaps])
                    db.execute('INSERT INTO spans VALUES (?,?,?)', (key, lo, hi))
                db.execute('INSERT INTO totals VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET count=count+1,last=max(last,excluded.last)', (key, 1, end))
    finally:
        db.close()


def runtime_summary(store, version):
    result = {'status': 'not_recorded', 'seconds': None, 'evaluations': None,
              'last_evaluated_at': None, 'basis': 'completed_candidate_rule_evaluation_interval_union'}
    path = evidence_path(store) if store else None
    incomplete = bool(path and Path(str(path) + '.' + identity(version) + '.incomplete').exists())
    if not path or not path.exists() or not version.get('paper_observation_attempt_id'):
        if incomplete:
            result['status'] = 'partial'
        return result
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=0.5)) as db:
            row = db.execute('SELECT count,last FROM totals WHERE key=?', (identity(version),)).fetchone()
            if row:
                seconds = db.execute('SELECT SUM(end-start) FROM spans WHERE key=?', (identity(version),)).fetchone()[0]
                result.update(status='observed', seconds=max(0.0, float(seconds)), evaluations=row[0],
                              last_evaluated_at=datetime.fromtimestamp(row[1], timezone.utc).isoformat())
    except (OSError, sqlite3.Error, ValueError, TypeError):
        result['status'] = 'unavailable'
    if result['status'] != 'unavailable' and incomplete:
        result['status'] = 'partial'
    return result


def measure_paper_pool(function):
    @wraps(function)
    def wrapped(cls, strategies, context, *args, **kwargs):
        # Only internal PAPER grants carry these paths; replay/LIVE/legacy pools
        # are never presented as measured PAPER execution.
        from .strategy_scope import scoped_pool
        eligible = scoped_pool(strategies, asset_class=kwargs.get('asset_class', ''), target=kwargs.get('target', ''))
        modes = {str(v).strip().lower() for v in context.get('_eligible_strategy_modes', []) if v}
        ids = {str(v).strip() for v in context.get('_eligible_strategy_ids', []) if v}
        by_store = {}
        for item in eligible:
            mode = str(item.get('signal_mode') or (item.get('rules') or {}).get('signal_mode') or 'confirm').lower()
            ident = str(item.get('version_id') or item.get('id') or item.get('strategy_key') or '')
            if (modes and mode not in modes) or (ids and mode == 'independent' and ident and ident not in ids):
                continue
            if item.get('operation_mode') == 'paper_validation' and item.get('_paper_store_path') and item.get('_paper_attempt_id'):
                by_store.setdefault(item['_paper_store_path'], []).append(item)
        if not by_store:
            return function(cls, strategies, context, *args, **kwargs)
        started, tick = time.time(), time.monotonic()
        result = function(cls, strategies, context, *args, **kwargs)
        ended = started + max(0.0, time.monotonic() - tick)
        if abs(time.time() - ended) > 1.0:
            for store, items in by_store.items():
                _mark_incomplete(store, items)
            _warn('PAPER execution time skipped after system clock change')
            return result
        for store, items in by_store.items():
            try:
                record_interval(store, items, started, ended)
            except (OSError, ValueError, TypeError, sqlite3.Error, KeyError):
                # Evidence failures cannot create/cancel orders or hide failures
                # from the original strategy evaluation.
                _mark_incomplete(store, items)
                _warn('PAPER execution-time evidence could not be recorded')
        return result
    return wrapped
