"""Account-local, resumable maintenance. Never a trading permission override.

The durable queue spans all unresolved LIVE outcomes in a 45-day window (not
the policy's 300-row sample). Each row is checkpointed; requests are read-only,
outside SQLite transactions. Unknown ownership is never inferred from time or
quantity. API support and accounting/strategy readiness are separate facts.
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from contextlib import contextmanager, closing

from trading.pnl_evidence import performance_evidence
from trading.exchanges.venue_capabilities import normalize_venue, SUPPORTED_VENUES
from trading.binance_history_recovery import HistoryPending


def recovery_hint(report):
    if 'pnl_reconciliation_required' not in report.get('reasons', []):
        return '수익성 검증 기준과 전략 성과를 확인하세요.'
    return ('설정 → 업데이트 → 유지관리 → 거래 기록 점검·복구에서 확인하세요. '
            '거래 통계에서도 같은 점검을 열 수 있습니다. 주문 근거가 없으면 추가 확인이 필요합니다. '
            '기록 초기화나 전략 전환으로 우회하지 마세요.')


class RecordRecovery:
    _locks_guard = threading.Lock()
    _locks: dict[str, threading.Lock] = {}

    def __init__(self, recorder, resolver, *, now=time.time, request_budget=60, delay=0.25):
        self.recorder, self.resolver, self.now = recorder, resolver, now
        self.request_budget, self.delay = request_budget, delay
        self.cancelled = threading.Event()
        self.path = Path(recorder.db_path).resolve()
        self.journal = self.path.with_name('record_recovery.sqlite3')
        with self._locks_guard:
            self.lock = self._locks.setdefault(str(self.path), threading.Lock())
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS jobs (
                    venue TEXT PRIMARY KEY, job_id TEXT NOT NULL, state TEXT NOT NULL,
                    updated REAL NOT NULL, lease_until REAL NOT NULL DEFAULT 0,
                    since REAL NOT NULL, backup TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS items (
                    job_id TEXT NOT NULL, trade_id INTEGER NOT NULL, state TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '', before_json TEXT, after_json TEXT,
                    PRIMARY KEY(job_id,trade_id));
            ''')
            columns = {r[1] for r in db.execute('PRAGMA table_info(jobs)')}
            for name, definition in (('retry_count','INTEGER NOT NULL DEFAULT 0'),('next_retry_at','REAL NOT NULL DEFAULT 0'),('retryable','INTEGER NOT NULL DEFAULT 0')):
                if name not in columns: db.execute(f'ALTER TABLE jobs ADD COLUMN {name} {definition}')
        self.journal.chmod(0o600)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.journal, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @classmethod
    def read_status(cls, db_path, venue):
        """Read persisted progress after restart, without opening the engine."""
        reader = cls.__new__(cls)
        reader.path = Path(db_path).resolve()
        reader.journal = reader.path.with_name('record_recovery.sqlite3')
        reader.now = time.time
        if not reader.journal.exists():
            return {'source': cls.venue(venue), 'state': 'idle', 'total': 0,
                    'processed': 0, 'recovered': 0, 'remaining': 0, 'reasons': {}, 'auto_started': False}
        return reader.status(venue)

    @contextmanager
    def _ledger(self):
        db = sqlite3.connect(self.path, timeout=2)
        db.row_factory = sqlite3.Row
        db.create_function('recovery_epoch', 1, self.recorder._ledger_time_epoch)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def venue(value):
        value = normalize_venue(value)
        if value not in SUPPORTED_VENUES:
            raise ValueError('unsupported_recovery_source')
        return value

    def status(self, venue):
        venue = self.venue(venue)
        with self._connect() as db:
            job = db.execute('SELECT * FROM jobs WHERE venue=?', (venue,)).fetchone()
            if not job:
                return {'source': venue, 'state': 'idle', 'total': 0, 'processed': 0,
                        'recovered': 0, 'remaining': 0, 'reasons': {}, 'auto_started': False}
            rows = db.execute('SELECT state,reason,COUNT(*) AS n FROM items WHERE job_id=? GROUP BY state,reason', (job['job_id'],)).fetchall()
        total = sum(r['n'] for r in rows)
        recovered = sum(r['n'] for r in rows if r['state'] == 'recovered')
        pending = sum(r['n'] for r in rows if r['state'] == 'pending')
        state = job['state']
        if state in {'running','retry_wait'} and job['lease_until'] < self.now():
            state = 'interrupted'
        history_pages = {}
        if venue == 'binance':
            with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True, timeout=2)) as ledger:
                if ledger.execute("SELECT 1 FROM sqlite_master WHERE name='recovery_history_job_sessions'").fetchone():
                    counts = ledger.execute('''SELECT state,COUNT(*) FROM (
                        SELECT DISTINCT p.scope,p.symbol,p.kind,p.start,p.end,p.state FROM recovery_history_pages p
                        JOIN recovery_history_session_pages s USING(scope,symbol,kind,start,end)
                        JOIN recovery_history_job_sessions j ON j.scope=s.scope AND j.symbol=s.symbol AND j.start=s.session_start
                        WHERE j.job_id=? AND p.state!='split') GROUP BY state''',
                        (job['job_id'],)).fetchall()
                    history_pages = dict(counts)
        return {'source': venue, 'job_id': job['job_id'], 'state': state,
                'background_continuation': True,
                'retry_count': job['retry_count'] if 'retry_count' in job.keys() else 0,
                'retryable': bool(job['retryable']) if 'retryable' in job.keys() else False,
                'next_retry_at': job['next_retry_at'] if 'next_retry_at' in job.keys() else 0,
                'total': total, 'processed': total-pending, 'recovered': recovered,
                'remaining': total-recovered, 'pending': pending,
                'reasons': {r['reason']: r['n'] for r in rows if r['reason'] and r['state'] != 'recovered'},
                'since': job['since'], 'updated': job['updated'], 'error': job['error'] or '',
                'backup_created': bool(job['backup']), 'auto_started': False,
                'account_pnl_verified': False, 'resume_authorized': False, 'history_pages': history_pages}

    def start(self, venue, *, background=True):
        venue = self.venue(venue)
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('recovery_already_running')
        handed_off = False
        try:
            with self._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute("SELECT 1 FROM jobs WHERE state IN ('running','retry_wait') AND lease_until>?", (self.now(),)).fetchone():
                    raise RuntimeError('recovery_already_running')
                old = db.execute('SELECT * FROM jobs WHERE venue=?', (venue,)).fetchone()
                if old and self.now()-old['updated'] < 30 and old['state'] not in {'paused', 'running', 'retry_wait'}:
                    raise RuntimeError('recovery_cooldown')
                continuation = old and old['state'] in {'paused', 'running', 'failed', 'retry_wait'}
                job_id = old['job_id'] if continuation else uuid.uuid4().hex
                since = old['since'] if continuation else self.now()-45*86400
                if not continuation:
                    # Keep previous per-row before/after audit evidence too.
                    db.execute('INSERT OR REPLACE INTO jobs(venue,job_id,state,updated,lease_until,since,backup,error) VALUES (?,?,?,?,?,?,NULL,NULL)',
                               (venue, job_id, 'running', self.now(), self.now()+120, since))
                else:
                    db.execute("UPDATE jobs SET state='running',updated=?,lease_until=?,error=NULL WHERE venue=?",
                               (self.now(), self.now()+120, venue))
            if background:
                threading.Thread(target=self._background, args=(venue, job_id), daemon=True, name='record-recovery').start()
                handed_off = True
            else:
                handed_off = True
                self._run(venue, job_id)
        except BaseException:
            if not handed_off:
                self.lock.release()
            raise
        return self.status(venue)

    def cancel(self):
        self.cancelled.set()

    def _background(self, venue, job_id):
        """One account lock for the entire explicitly requested operation.
        Request budgets yield, transient failures retry at most twice. No UI
        polling or open Settings window is required to advance the queue.
        """
        retries = 0
        transient = {'income_reconciliation_required','position_anchor_changed','provider_query_failed'}
        try:
            while not self.cancelled.is_set():
                self._run(venue,job_id,keep_lock=True)
                state = self.status(venue)
                pause = state['state']=='paused'
                reasons = set(state['reasons'])
                retry = (state['state']=='failed' and state['retryable']) or (
                    state['state']=='needs_evidence' and bool(reasons & transient))
                if not pause and (not retry or retries>=2): break
                if retry:
                    retries += 1
                    delay = (5,15)[retries-1]
                    with self._connect() as db:
                        db.execute("UPDATE jobs SET state='retry_wait',retry_count=?,next_retry_at=?,lease_until=?,updated=? WHERE job_id=?",
                                   (retries,self.now()+delay,self.now()+delay+120,self.now(),job_id))
                        if state['state']=='needs_evidence':
                            db.execute("UPDATE items SET state='pending' WHERE job_id=? AND state='unresolved' AND reason IN (?,?,?)",
                                       (job_id,*sorted(transient)))
                    if callable(getattr(self.resolver,'retry_pending_evidence',None)):
                        self.resolver.retry_pending_evidence()
                else:
                    delay = 2
                    # Keep the cross-process lease while yielding between
                    # batches; this is still the same active operation.
                    with self._connect() as db:
                        db.execute("UPDATE jobs SET state='running',lease_until=?,updated=? WHERE job_id=?",
                                   (self.now()+120,self.now(),job_id))
                if self.cancelled.wait(delay): break
                with self._connect() as db:
                    db.execute("UPDATE jobs SET state='running',next_retry_at=0,lease_until=?,updated=? WHERE job_id=?",
                               (self.now()+120,self.now(),job_id))
        finally:
            if self.cancelled.is_set(): self._finish(venue,'paused')
            self.lock.release()

    def _prepare(self, venue, job_id):
        with self._connect() as db:
            job = db.execute('SELECT * FROM jobs WHERE job_id=?', (job_id,)).fetchone()
        if job['backup']:
            return
        folder = self.path.parent / 'backups' / 'record_recovery'
        folder.mkdir(parents=True, exist_ok=True)
        backup = folder / f'{venue}-before.sqlite3'
        # Preserve the initial baseline; later runs append before/after rows to
        # the journal rather than overwriting recovery evidence or making a
        # full account DB copy on every button press.
        started = time.monotonic()
        def progress(_status, _remaining, _total):
            if time.monotonic()-started > 30:
                raise TimeoutError('backup_timeout')
        if not backup.exists():
            temporary = backup.with_suffix('.incomplete')
            with self._ledger() as src, closing(sqlite3.connect(temporary)) as dest:
                src.backup(dest, pages=256, progress=progress, sleep=0.05)
            temporary.replace(backup)
            backup.chmod(0o600)
        with self._ledger() as src, self._connect() as db:
            for row in src.execute('''SELECT * FROM trade_log WHERE LOWER(exchange)=?
                AND exit_time IS NOT NULL AND recovery_epoch(exit_time)>=?
                AND recovery_epoch(exit_time)<=?
                AND LOWER(execution_mode) IN ('live','live_api','optimized','manual')
                AND (LOWER(position_owner)='noahai' OR LOWER(reason) LIKE 'ai %'
                     OR LOWER(reason) LIKE 'stock_auto_%') ORDER BY id''', (venue, job['since'], self.now())):
                record = dict(row)
                if not performance_evidence(record)['performance_evidence_ready']:
                    db.execute('INSERT OR IGNORE INTO items(job_id,trade_id,state,before_json) VALUES (?,?,?,?)',
                               (job_id, row['id'], 'pending', json.dumps(record)))
            db.execute('UPDATE jobs SET backup=? WHERE job_id=?', (str(backup), job_id))

    def _run(self, venue, job_id, *, keep_lock=False):
        try:
            if callable(getattr(self.resolver, 'begin_job', None)):
                self.resolver.begin_job(job_id)
            self._prepare(venue, job_id)
            requests = 0
            initial_queries = getattr(self.resolver, 'query_count', 0)
            started = time.monotonic()
            while time.monotonic()-started < 90 and not self.cancelled.is_set():
                with self._connect() as db:
                    item = db.execute("SELECT trade_id,before_json FROM items WHERE job_id=? AND state='pending' ORDER BY trade_id DESC LIMIT 1", (job_id,)).fetchone()
                    db.execute('UPDATE jobs SET lease_until=?,updated=? WHERE job_id=?', (self.now()+120, self.now(), job_id))
                if not item:
                    self._finish(venue, 'needs_evidence' if self.status(venue)['remaining'] else 'checked')
                    return
                if requests >= self.request_budget:
                    break
                with self._ledger() as db:
                    row = db.execute('SELECT * FROM trade_log WHERE id=?', (item['trade_id'],)).fetchone()
                if not row:
                    reason = 'record_missing'
                else:
                    trade = dict(row)
                    before = json.loads(item['before_json'])
                    identity_changed = any(trade.get(key) != before.get(key) for key in (
                        'exchange','symbol','order_id','entry_time','quantity','entry_price','execution_mode','position_owner'))
                    if (identity_changed and performance_evidence(trade)['performance_evidence_ready']
                            and callable(getattr(self.resolver,'repaired_identity',None))
                            and self.resolver.repaired_identity(before,trade)):
                        identity_changed = False
                    if identity_changed:
                        reason = 'record_identity_changed'
                    elif performance_evidence(trade)['performance_evidence_ready']:
                        reason = ''
                    else:
                        # Resolver is pinned to this account's runtime & adapter.
                        # It must not make a network request while a DB lock is held.
                        before_queries = getattr(self.resolver, 'query_count', requests)
                        try:
                            reason = self.resolver(venue, trade)
                        except HistoryPending:
                            requests = self.resolver.query_count - initial_queries
                            with self._connect() as db:
                                db.execute("UPDATE items SET reason='provider_history_collecting' WHERE job_id=? AND trade_id=?",
                                           (job_id,item['trade_id']))
                            if self.delay:
                                # Income pages cost more request weight than
                                # fills. Leave capacity for the trading engine.
                                time.sleep(max(self.delay, 1.5))
                            continue  # page checkpointed; do not mark the trade unresolved
                        requests = (self.resolver.query_count - initial_queries
                                    if hasattr(self.resolver, 'query_count') else requests+1)
                        if self.delay and getattr(self.resolver, 'query_count', requests) > before_queries:
                            time.sleep(self.delay)
                    with self._ledger() as db:
                        after = dict(db.execute('SELECT * FROM trade_log WHERE id=?', (item['trade_id'],)).fetchone())
                    ready = not identity_changed and performance_evidence(after)['performance_evidence_ready']
                    reason = '' if ready else reason or after.get('reconciliation_status') or 'evidence_incomplete'
                with self._connect() as db:
                    db.execute('UPDATE items SET state=?,reason=?,after_json=? WHERE job_id=? AND trade_id=?',
                               ('unresolved' if reason else 'recovered', reason,
                                json.dumps(after) if row else None, job_id, item['trade_id']))
            self._finish(venue, 'paused')
        except Exception as exc:
            # No raw provider response, key, account number or traceback in UI.
            transient = (isinstance(exc,(TimeoutError,ConnectionError)) or
                         type(exc).__name__ in {'ReadTimeout','ConnectTimeout'} or
                         getattr(exc,'code',None) in {-1001,-1003,-1007} or
                         getattr(exc,'status_code',None) in {429,500,502,503,504} or
                         (isinstance(exc,RuntimeError) and str(exc)=='provider_history_query_failed'))
            self._finish(venue, 'failed', type(exc).__name__, retryable=transient)
        finally:
            if not keep_lock: self.lock.release()

    def _finish(self, venue, state, error='', *, retryable=False):
        with self._connect() as db:
            db.execute('UPDATE jobs SET state=?,updated=?,lease_until=0,next_retry_at=0,error=?,retryable=? WHERE venue=?', (state, self.now(), error, int(retryable), venue))


def validate_fills(trade, rows):
    """Only complete, exact-order, dated, finite provider evidence is writable."""
    if not isinstance(rows, list) or len(rows) >= 1000:
        return [], 'history_page_incomplete'
    try:
        expected_quantity = float(trade['quantity'])
        entry_price = float(trade['entry_price'])
        if not all(math.isfinite(n) and n > 0 for n in (expected_quantity, entry_price)):
            raise ValueError()
    except (TypeError, ValueError, KeyError):
        return [], 'local_trade_data_invalid'
    oid, symbol = str(trade['exit_order_id']), str(trade['symbol']).upper()
    fills = [r for r in rows if str(r.get('order') or r.get('order_id') or '') == oid]
    if not fills:
        return [], 'exchange_fill_not_found'
    expected = {'LONG':'sell', 'BUY':'sell', 'SHORT':'buy', 'SELL':'buy'}.get(str(trade['side']).upper())
    ids = set()
    quantity = 0.0
    for row in fills:
        if str(row.get('symbol') or '').upper() != symbol or str(row.get('side') or '').lower() != expected:
            return [], 'order_identity_mismatch'
        identity = str(row.get('id') or row.get('trade_id') or '')
        if not identity or identity in ids:
            return [], 'execution_identity_incomplete'
        ids.add(identity)
        if row.get('_execution_confirmed') is False or str(row.get('status', '')).lower() in {'open','new','pending'}:
            return [], 'partial_or_quantity_mismatch'
        fee = row.get('fee')
        cost = fee.get('cost') if isinstance(fee, dict) else row.get('commission')
        try:
            amount = float(row.get('amount') or row.get('quantity') or 0)
            price = float(row.get('price'))
            fee_value = float(cost)
            if not all(math.isfinite(n) for n in (amount, price, fee_value)) or amount <= 0 or price <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            return [], 'fee_or_fill_data_incomplete'
        from trading.recorder import Recorder
        epoch = Recorder._ledger_time_epoch(row.get('timestamp') or row.get('time') or row.get('datetime'))
        if epoch is None or not math.isfinite(epoch) or epoch <= 0:
            return [], 'execution_time_missing'
        quantity += amount
    if abs(quantity-expected_quantity) > max(1e-8, expected_quantity*1e-8):
        return [], 'partial_or_quantity_mismatch'
    return fills, ''
