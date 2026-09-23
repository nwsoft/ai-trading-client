"""Resumable maintenance without touching trading/PAPER ledgers."""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

from log_system.storage_policy import disk_usage, read_policy, DEFAULT_LOG_BUDGET
from trading.learning_storage import LearningStore

_JOBS = {}; _LOCK = threading.RLock()


class StorageMaintenance:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.state = {'state':'idle', 'decision_rows_checked':0, 'learning_rows_imported':0, 'archived_rows':0,
                      'legacy_archives_compressed':0, 'legacy_bytes_saved':0, 'evidence_compacted':0}
        self.lock = threading.RLock()

    def status(self):
        from log_system.event_audit import failure
        from trading.learning_storage import ARCHIVE_ERRORS
        from trading.exchange_learning_manager import _MANAGERS
        with self.lock: state = dict(self.state)
        policy = read_policy(self.root)
        usage = disk_usage(self.root)
        from trading.learning_archive_compaction import candidates
        legacy = candidates(self.root)
        pending_bytes = 0
        for candidate in legacy:
            try: pending_bytes += candidate.stat().st_size
            except FileNotFoundError: pass
        last = None; storage_error = None
        from trading.recorder_write_queue import status as write_status
        from trading.write_coordination import snapshot
        try:
            writes = write_status(self.root/'trading.db')
        except sqlite3.Error:
            writes = {'pending': None, 'needs_review': None, 'error': 'status_unavailable'}
        rejected = 0
        from trading.contract_rejections import count
        for filename in ('trading.db', 'learning.sqlite3'):
            candidate = self.root/filename
            if candidate.exists():
                try:
                    with closing(sqlite3.connect(f'{candidate.as_uri()}?mode=ro', uri=True, timeout=1)) as conn:
                        rejected += count(conn)
                except sqlite3.Error:
                    storage_error = 'contract_status_unavailable'
        path = self.root/'learning.sqlite3'
        if path.exists():
            try:
                with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True, timeout=1)) as conn:
                    row = conn.execute("SELECT value FROM state WHERE key='last_compression'").fetchone()
                    last = row[0] if row else None
            except sqlite3.Error as exc:
                storage_error = type(exc).__name__
        return {**state, **usage, 'legacy_archives_pending':len(legacy),
                'writer_activity':snapshot(self.root/'trading.db'),
                'record_writes': writes,
                'legacy_archives_pending_bytes':pending_bytes,
                'learning_capacity_warning':usage['learning_bytes'] >= 8*1024**3,
                'last_compression':last, 'debug_expires_at':policy.get('debug_expires_at',0),
                'log_budget_bytes':policy.get('log_budget_bytes',DEFAULT_LOG_BUDGET),
                'last_log_compression':policy.get('last_log_compression'),
                'log_archive_error':policy.get('log_archive_error'),
                'contract_rejected_records':rejected,
                'log_budget_exceeded':usage['log_bytes']>=policy.get('log_budget_bytes',DEFAULT_LOG_BUDGET),
                'audit_error':failure(self.root), 'learning_archive_error':storage_error or ARCHIVE_ERRORS.get(str(path.resolve())),
                'learning_migration_errors':{venue:manager.migration_error for (root,venue),manager in list(_MANAGERS.items())
                    if root==str(self.root) and manager.migration_error},
                'trade_records_deleted':False}

    def start(self):
        with self.lock:
            if self.state['state']=='running': return self.status()
            self.state.update(state='running', error=None)
            threading.Thread(target=self.run, daemon=True, name='storage-maintenance').start()
        return self.status()

    def run(self):
        started = time.monotonic()
        try:
            from log_system.storage_policy import compact_logs
            compact_logs(self.root, force=True)
            # The dominant existing disk usage was not in SQLite: reduce closed
            # legacy archives first, before allocating an imported database.
            from trading.learning_archive_compaction import candidates, compact_one
            for source in candidates(self.root):
                with self.lock:
                    self.state.update(current_file=source.name, current_file_bytes=source.stat().st_size,
                                      current_file_processed=0)
                def progress(size):
                    with self.lock: self.state['current_file_processed'] = size
                result = compact_one(source, progress)
                with self.lock:
                    self.state['legacy_archives_compressed'] += 1
                    self.state['legacy_bytes_saved'] += result['saved_bytes']
                time.sleep(.05)
            with self.lock: self.state['current_file'] = None
            started = time.monotonic()
            path = self.root/'trading.db'
            if path.exists():
                from trading.decision_storage import ensure_schema, backfill_batch
                from trading.write_coordination import connection
                with connection(path, operation='maintenance_schema', priority=20, timeout=.1, budget_seconds=.25) as conn:
                    ensure_schema(conn)
                while time.monotonic()-started < 120:
                    with connection(path, operation='decision_backfill', priority=20, timeout=.1, budget_seconds=.25) as conn:
                        count = backfill_batch(conn, limit=100, budget_seconds=.05)
                    with self.lock: self.state['decision_rows_checked'] += count
                    if not count: break
                    time.sleep(.05)
                else:
                    with self.lock: self.state['state']='paused'
                    return
            store = LearningStore(self.root)
            while time.monotonic()-started < 120:
                count = store.compact_evidence()
                with self.lock: self.state['evidence_compacted'] += count
                if not count: break
                time.sleep(.01)
            else:
                with self.lock: self.state['state']='paused'
                return
            for venue in ('binance','upbit','bithumb','bybit','okx','bitget','coinone'):
                for name in (f'ai_learning_data_{venue}.json', f'ai_learning_data_{venue}.json.journal.jsonl'):
                    count = store.import_legacy(self.root/name,venue)
                    with self.lock: self.state['learning_rows_imported'] += count
                from trading.exchange_learning_manager import _MANAGERS, _MANAGERS_LOCK
                with _MANAGERS_LOCK:
                    manager = _MANAGERS.get((str(self.root), venue))
                    if manager is not None: manager.migration_error = None
            while time.monotonic()-started < 120:
                count = store.archive()
                with self.lock: self.state['archived_rows'] += count
                if not count: break
                time.sleep(.01)
            else:
                with self.lock: self.state['state']='paused'
                return
            from trading.learning_storage import ARCHIVE_ERRORS
            ARCHIVE_ERRORS.pop(str(store.path.resolve()), None)
            with self.lock: self.state['state']='complete'
        except sqlite3.OperationalError as exc:
            transient = any(v in str(exc).lower() for v in ('locked','busy','interrupted'))
            with self.lock: self.state.update(state='paused' if transient else 'failed',
                error='writer_busy_continue_later' if transient else type(exc).__name__)
        except Exception as exc:
            with self.lock: self.state.update(state='failed', error=type(exc).__name__)


def maintenance(root):
    key = str(Path(root).resolve())
    with _LOCK:
        if key not in _JOBS: _JOBS[key] = StorageMaintenance(root)
        return _JOBS[key]
