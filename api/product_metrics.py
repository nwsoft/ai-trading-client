"""Account-scoped, opt-in durable observations. Never stores credentials.

Commit before returning; retry the same UUID until an explicit server receipt.
SQLite FULL sync protects committed events across ordinary process termination.
Disk/hardware failure is exposed as collection_error, never an invented success.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4
import requests
from config.app_version import RELEASE_VERSION

POLICY = 'product-observation-20261018'
ACTIONS = frozenset({'app_open','studio_open','studio_save','studio_validate','studio_approve',
    'studio_activate','paper_start','paper_pause','paper_complete','live_start','xai_open','review_open'})
UI_ACTIONS = frozenset({'app_open','studio_open','xai_open','review_open'})

class ProductMetrics:
    def __init__(self, *, directory, account, credentials, base_url='https://noahai.net', transport=None):
        if not base_url.startswith('https://'):
            raise ValueError('https_required')
        self.account = account
        self.credentials = credentials
        self.url = base_url.rstrip('/') + '/auth/kpi/product-event'
        self.transport = transport or requests.post
        self.path = Path(directory) / 'product_metrics' / (hashlib.sha256(account.encode()).hexdigest() + '.sqlite3')
        self.lock = threading.RLock()
        self.delivery_lock = threading.Lock()
        self.closed = threading.Event()
        self.wake = threading.Event()
        self.worker = None
        self.error = None
        self.retry_after = 0.0
        self.failures = 0
        # Construction is read-only: no pre-consent file or network request.

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600); os.close(fd)
        os.chmod(self.path, 0o600)
        c = sqlite3.connect(self.path, timeout=1)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA synchronous=FULL')
        c.execute('PRAGMA secure_delete=ON')
        c.execute('CREATE TABLE IF NOT EXISTS consent(id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL, policy TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,payload TEXT NOT NULL,state TEXT NOT NULL DEFAULT \'pending\')')
        c.execute('CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        c.commit()
        return c

    def _enabled(self, c):
        row = c.execute('SELECT enabled,policy FROM consent WHERE id=1').fetchone()
        return bool(row and row['enabled'] and row['policy'] == POLICY and
                    c.execute("SELECT 1 FROM state WHERE key='consent_revision'").fetchone())

    def status(self):
        with self.lock:
            out = dict(enabled=False, policy=POLICY, pending=0, rejected=0,
                       last_received=None, error=self.error, consent_pending=0, consent_rejected=0,
                       consent_reconfirmation_required=False, client_version=RELEASE_VERSION)
            if self.path.exists():
                with self.connect() as c:
                    out['enabled'] = self._enabled(c)
                    prior=c.execute('SELECT enabled FROM consent WHERE id=1').fetchone()
                    out['consent_reconfirmation_required']=bool(prior and prior['enabled'] and not out['enabled'])
                    out['consent_pending']=c.execute("SELECT count(*) FROM outbox WHERE state='pending' AND json_extract(payload,'$.action') IN ('consent_granted','consent_withdrawn')").fetchone()[0]
                    out['consent_rejected']=c.execute("SELECT count(*) FROM outbox WHERE state='rejected' AND json_extract(payload,'$.action') IN ('consent_granted','consent_withdrawn')").fetchone()[0]
                    for row in c.execute("SELECT state,count(*) AS n FROM outbox WHERE json_extract(payload,'$.action') NOT IN ('consent_granted','consent_withdrawn') GROUP BY state"):
                        out[row['state']] = row['n']
                    row = c.execute("SELECT value FROM state WHERE key='last_received'").fetchone()
                    out['last_received'] = row['value'] if row else None
            if (out['rejected'] or out['consent_rejected']) and not out['error']: out['error'] = 'observation_rejected'
            return out

    def configure(self, enabled, policy):
        if type(enabled) is not bool or policy != POLICY:
            raise ValueError('explicit_current_policy_required')
        with self.delivery_lock, self.lock:
            with self.connect() as c:
                c.execute('INSERT OR REPLACE INTO consent VALUES(1,?,?)',(int(enabled),POLICY))
                row=c.execute("SELECT value FROM state WHERE key='installation_id'").fetchone()
                installation=row['value'] if row else str(uuid4())
                row=c.execute("SELECT value FROM state WHERE key='consent_revision'").fetchone()
                revision=int(row['value'])+1 if row else 1
                c.execute("INSERT OR REPLACE INTO state VALUES('installation_id',?)",(installation,))
                c.execute("INSERT OR REPLACE INTO state VALUES('consent_revision',?)",(str(revision),))
                if not enabled:
                    c.execute("DELETE FROM outbox WHERE json_extract(payload,'$.action') NOT IN ('consent_granted','consent_withdrawn')")
                event_id=str(uuid4())
                data=dict(event_id=event_id,action='consent_granted' if enabled else 'consent_withdrawn',
                    mode='none',consent=enabled,consent_version=POLICY,
                    occurred_at=datetime.now(timezone.utc).isoformat(),installation_id=installation,
                    consent_revision=revision,client_version=RELEASE_VERSION)
                c.execute('INSERT INTO outbox(id,payload) VALUES(?,?)',(event_id,json.dumps(data,sort_keys=True)))
                c.commit()
            self.error = None
        self.wake.set()
        self.start()
        return self.status()

    def record(self, action, mode='none', event_id=None):
        if action not in ACTIONS or mode not in {'none','paper','live'}:
            raise ValueError('invalid_product_action')
        if (action.startswith('paper_') and mode!='paper') or (action=='live_start' and mode!='live'):
            raise ValueError('action_mode_mismatch')
        event_id = str(UUID(event_id)) if event_id else str(uuid4())
        with self.lock:
            if self.closed.is_set() or not self.path.exists(): return False
            with self.connect() as c:
                if not self._enabled(c): return False
                # No silent eviction. A full disk/quota is surfaced in consent UI.
                if c.execute('SELECT count(*) FROM outbox').fetchone()[0] >= 100000:
                    self.error='outbox_full'; return False
                existing = c.execute('SELECT payload FROM outbox WHERE id=?',(event_id,)).fetchone()
                if not existing:
                    data = dict(event_id=event_id,action=action,mode=mode,consent=True,
                                consent_version=POLICY,occurred_at=datetime.now(timezone.utc).isoformat(),
                                client_version=RELEASE_VERSION,
                                installation_id=c.execute("SELECT value FROM state WHERE key='installation_id'").fetchone()['value'],
                                consent_revision=int(c.execute("SELECT value FROM state WHERE key='consent_revision'").fetchone()['value']))
                    c.execute('INSERT INTO outbox(id,payload) VALUES(?,?)',(event_id,json.dumps(data,sort_keys=True)))
                    c.commit()
            self.wake.set()
        self.start()
        return True

    def deliver_once(self):
        # Network work holds only the delivery lock. Recording a successful
        # trading/strategy action never waits for an HTTP timeout.
        with self.delivery_lock:
            with self.lock:
                if self.closed.is_set() or not self.path.exists(): return False
                with self.connect() as c:
                    # Latest transition first: offline withdrawal reaches the server before any stale grant.
                    row = c.execute("SELECT id,payload FROM outbox WHERE state='pending' AND json_extract(payload,'$.action') IN ('consent_granted','consent_withdrawn') ORDER BY json_extract(payload,'$.consent_revision') DESC LIMIT 1").fetchone()
                    if not row:
                        if not self._enabled(c): return False
                        row=c.execute("SELECT id,payload FROM outbox WHERE state='pending' ORDER BY rowid LIMIT 1").fetchone()
                    if not row: return False
                token = self.credentials()
                if not token:
                    self.error='authentication_required'; return False
            receipt = {}
            code = None
            try:
                response = self.transport(self.url,json=json.loads(row['payload']),
                    headers={'Authorization':'Bearer '+token},timeout=2,allow_redirects=False)
                code = response.status_code
                if code == 200:
                    parsed = response.json()
                    receipt = parsed if isinstance(parsed,dict) else {}
            except (requests.RequestException,ValueError,TypeError):
                pass
            with self.lock:
                with self.connect() as c:
                    if code==200 and receipt.get('accepted') is True and receipt.get('event_id')==row['id']:
                        c.execute('DELETE FROM outbox WHERE id=?',(row['id'],))
                        c.execute("INSERT OR REPLACE INTO state VALUES('last_received',?)",(datetime.now(timezone.utc).isoformat(),))
                        c.commit(); self.error=None; self.failures=0; self.retry_after=0
                        return True
                    if code in {400,409,413,422}:
                        c.execute("UPDATE outbox SET state='rejected' WHERE id=?",(row['id'],)); c.commit()
                        self.error='observation_rejected'
                        return False
                self.error='authentication_required' if code in {401,403} else 'delivery_pending'
                self.failures += 1
                self.retry_after=time.monotonic()+min(300,2**min(self.failures,8))
                return False

    def start(self):
        with self.lock:
            if self.closed.is_set() or (self.worker and self.worker.is_alive()): return
            if not self.path.exists(): return
            with self.connect() as c:
                if not self._enabled(c) and not c.execute("SELECT 1 FROM outbox WHERE state='pending' AND json_extract(payload,'$.action') IN ('consent_granted','consent_withdrawn')").fetchone(): return
            self.worker=threading.Thread(target=self._run,daemon=True,name='product-observations')
            self.worker.start()

    def _run(self):
        while not self.closed.is_set():
            try:
                if time.monotonic() >= self.retry_after and self.deliver_once(): continue
            except Exception:
                self.error='collection_error'
            self.wake.wait(2); self.wake.clear()

    def close(self):
        # Every accepted event was already committed; never drain-and-drop.
        self.closed.set(); self.wake.set()
        if self.worker and self.worker is not threading.current_thread(): self.worker.join(timeout=2.5)
