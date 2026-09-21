"""Account-scoped incremental learning storage, content-addressed XAI and archives.

SQLite serializes writers across processes. Legacy files are never overwritten.
Archives are committed to the catalog before hot rows are removed in one transaction.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import time
from collections.abc import Sequence
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from trading.event_contract import canonical_json


def iter_legacy(path: Path):
    if path.name.endswith('.jsonl'):
        with path.open(encoding='utf-8') as handle:
            for line in handle:
                if line.strip():
                    value = json.loads(line)  # damaged input is reported, never silently skipped
                    if not isinstance(value,dict): raise ValueError('legacy_object_required')
                    yield value
        return
    decoder = json.JSONDecoder()
    with path.open(encoding='utf-8-sig') as handle:
        buffer = ''; started = False; ended = False
        expect_value = True; allow_end = True
        while True:
            chunk = handle.read(65536)
            buffer += chunk
            while True:
                buffer = buffer.lstrip()
                if not started:
                    if not buffer: break
                    if not buffer.startswith('['): raise ValueError('legacy_array_required')
                    buffer = buffer[1:]; started = True; continue
                if buffer.startswith(']'):
                    if expect_value and not allow_end: raise ValueError('legacy_trailing_comma')
                    ended = True; buffer = buffer[1:]; break
                if not buffer: break
                if not expect_value:
                    if not buffer.startswith(','): raise ValueError('legacy_separator_required')
                    buffer = buffer[1:]; expect_value = True; allow_end = False; continue
                try: value, end = decoder.raw_decode(buffer)
                except json.JSONDecodeError:
                    if not chunk: raise
                    break
                buffer = buffer[end:]
                if not isinstance(value,dict): raise ValueError('legacy_object_required')
                expect_value = False
                yield value
            if ended:
                if buffer.strip() or handle.read().strip(): raise ValueError('legacy_trailing_data')
                return
            if not chunk: raise ValueError('legacy_truncated_array')


class LearningStore:
    def __init__(self, root, *, initialize=True):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'learning.sqlite3'
        if not initialize: return
        with closing(self.connect()) as conn, conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS evidence(hash TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL,
                    exchange TEXT NOT NULL, event_time TEXT, body TEXT NOT NULL, symbol TEXT);
                CREATE INDEX IF NOT EXISTS learning_venue_recent ON events(exchange,event_time DESC,id DESC);
                CREATE INDEX IF NOT EXISTS learning_symbol_recent ON events(exchange,symbol,event_time DESC,id DESC);
                CREATE TABLE IF NOT EXISTS identities(event_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS imports(path TEXT PRIMARY KEY, signature TEXT NOT NULL, row_count INTEGER NOT NULL, complete INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS segments(name TEXT PRIMARY KEY, sha256 TEXT NOT NULL, records INTEGER NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            ''')

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute('PRAGMA busy_timeout=10000')
        return conn

    def append(self, exchange, entry, *, conn=None, historical=False):
        if conn is None:
            with closing(self.connect()) as connection, connection:
                return self.append(exchange, entry, conn=connection, historical=historical)
        from trading.event_contract import input_issues
        issues = input_issues('analysis', entry, exchange)
        if issues:
            from trading.contract_rejections import preserve
            preserve(conn, 'historical_learning' if historical else 'learning', entry, issues,
                     exchange=exchange, symbol=entry.get('symbol'))
            return False
        event_id = entry['_learning_event_id']
        payload_hash = hashlib.sha256(canonical_json(entry).encode()).hexdigest()
        prior = conn.execute('SELECT payload_hash FROM identities WHERE event_id=?', (event_id,)).fetchone()
        if prior:
            if prior[0] != payload_hash: raise ValueError('learning_identity_conflict')
            return
        inserted = conn.execute('INSERT OR IGNORE INTO identities VALUES(?,?)', (event_id,payload_hash)).rowcount
        if not inserted:
            prior = conn.execute('SELECT payload_hash FROM identities WHERE event_id=?', (event_id,)).fetchone()
            if prior[0] != payload_hash: raise ValueError('learning_identity_conflict')
            return
        compact = {}; references = {}
        for key, value in entry.items():
            if key == '_xai_refs': raise ValueError('reserved_learning_field')
            if isinstance(value, (dict, list)) or (isinstance(value,str) and len(value)>256):
                body = canonical_json(value)
                digest = hashlib.sha256(body.encode()).hexdigest()
                conn.execute('INSERT OR IGNORE INTO evidence VALUES (?,?)', (digest, body))
                references[key] = digest
            else: compact[key] = value
        compact['_xai_refs'] = references
        timestamp = entry.get('timestamp')
        try:
            parsed = datetime.fromisoformat(str(timestamp).replace('Z','+00:00'))
            if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
            event_time = parsed.astimezone(timezone.utc).isoformat()
        except (ValueError,TypeError): event_time = ''
        conn.execute('INSERT OR IGNORE INTO events(event_id,exchange,event_time,body,symbol) VALUES(?,?,?,?,?)',
                     (event_id, exchange, event_time, canonical_json(compact), str(entry.get('symbol') or '').upper()))

    def expand(self, compact, conn):
        value = dict(compact)
        for key, digest in value.pop('_xai_refs', {}).items():
            row = conn.execute('SELECT body FROM evidence WHERE hash=?', (digest,)).fetchone()
            if not row or hashlib.sha256(row[0].encode()).hexdigest() != digest:
                raise ValueError('learning_evidence_missing_or_corrupt')
            value[key] = json.loads(row[0])
        return value

    def recent(self, exchange='', limit=10000, offset=0, symbol=None):
        with closing(self.connect()) as conn:
            where, args = ('WHERE exchange=?', [exchange]) if exchange else ('', [])
            if symbol is not None:
                where += ' AND symbol=?' if where else 'WHERE symbol=?'
                args.append(str(symbol).upper())
            rows = conn.execute(f'SELECT body FROM events {where} ORDER BY event_time DESC,id DESC LIMIT ? OFFSET ?', [*args, limit, offset]).fetchall()
            return [self.expand(json.loads(row[0]), conn) for row in reversed(rows)]

    def count(self, exchange=''):
        with closing(self.connect()) as conn:
            return conn.execute('SELECT count(*) FROM events' + (' WHERE exchange=?' if exchange else ''),
                                [exchange] if exchange else []).fetchone()[0]

    def import_legacy(self, path, exchange):
        path = Path(path)
        if not path.exists(): return 0
        signature = f'{path.stat().st_size}:{path.stat().st_mtime_ns}'
        with closing(self.connect()) as conn:
            state = conn.execute('SELECT signature,row_count,complete FROM imports WHERE path=?', (str(path.resolve()),)).fetchone()
            if state and state[0] == signature and state[2]: return 0
            skip = state[1] if state and state[0] == signature else 0
            count = 0; imported = 0
            for count, value in enumerate(iter_legacy(path), 1):
                if count <= skip: continue
                # Identity includes record ordinal, preserving repeated equal legacy rows.
                value.setdefault('_learning_event_id', 'legacy_' + hashlib.sha256(
                    canonical_json([path.name, count, value]).encode()).hexdigest())
                self.append(exchange, value, conn=conn, historical=True)
                imported += 1
                if count % 100 == 0:
                    conn.execute('INSERT OR REPLACE INTO imports VALUES(?,?,?,0)', (str(path.resolve()), signature, count))
                    conn.commit()
            with conn:
                conn.execute('INSERT OR REPLACE INTO imports VALUES(?,?,?,1)', (str(path.resolve()), signature, count))
            return imported

    def archive(self, keep=10000, batch=1000):
        """One bounded archival transaction. gzip includes compact events; evidence stays durable."""
        folder = self.root / 'learning_segments'
        folder.mkdir(exist_ok=True)
        with closing(self.connect()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            rows = []
            for (venue,) in conn.execute('SELECT DISTINCT exchange FROM events'):
                rows.extend(conn.execute('SELECT id,event_id,exchange,event_time,body FROM events WHERE exchange=? ORDER BY event_time DESC,id DESC LIMIT ? OFFSET ?',
                                         (venue, batch-len(rows), keep)).fetchall())
                if len(rows) >= batch: break
            if not rows: conn.rollback(); return 0
            day = str(rows[0][3])[:10]
            rows = [row for row in rows if str(row[3])[:10] == day]
            content = ('\n'.join(canonical_json(row) for row in rows)+'\n').encode()
            digest = hashlib.sha256(content).hexdigest()
            name = f'{day or "undated"}-{digest}.jsonl.gz'
            fd, temporary = tempfile.mkstemp(prefix='.segment-', dir=folder)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(gzip.compress(content, mtime=0)); handle.flush(); os.fsync(handle.fileno())
                if gzip.decompress(Path(temporary).read_bytes()) != content: raise ValueError('archive_verification_failed')
                os.replace(temporary, folder / name)
                if os.name == 'posix':
                    directory_fd = os.open(folder, os.O_RDONLY)
                    try: os.fsync(directory_fd)
                    finally: os.close(directory_fd)
                conn.execute('INSERT OR IGNORE INTO segments VALUES(?,?,?,?)', (name,digest,len(rows),datetime.now(timezone.utc).isoformat()))
                conn.executemany('DELETE FROM events WHERE id=?', [(row[0],) for row in rows])
                conn.execute("INSERT OR REPLACE INTO state VALUES('last_compression',?)", (datetime.now(timezone.utc).isoformat(),))
                conn.commit()
                return len(rows)
            finally:
                if os.path.exists(temporary): os.unlink(temporary)

    def read_segment(self, name):
        with closing(self.connect()) as conn:
            row = conn.execute('SELECT sha256,records FROM segments WHERE name=?', (name,)).fetchone()
            if not row: raise ValueError('unknown_segment')
            body = gzip.decompress((self.root / 'learning_segments' / name).read_bytes())
            if hashlib.sha256(body).hexdigest() != row[0]: raise ValueError('archive_checksum_mismatch')
            values = [json.loads(line) for line in body.splitlines()]
            if len(values) != row[1]: raise ValueError('archive_record_count_mismatch')
            return [self.expand(json.loads(value[4]), conn) for value in values]


class RecentHistory(Sequence):
    """List-compatible bounded view; no full JSON parsing during construction."""
    def __init__(self, store, exchange, limit):
        self.store, self.exchange, self.limit = store, exchange, limit

    def __len__(self): return min(self.limit, self.store.count(self.exchange))
    def __getitem__(self, key): return self.store.recent(self.exchange, self.limit)[key]
    def __iter__(self): return iter(self.store.recent(self.exchange, self.limit))
    def append(self, entry): pass  # The manager commits once through _persist_increment.


_ARCHIVE_JOBS = set()
_ARCHIVE_LOCK = threading.RLock()
ARCHIVE_ERRORS = {}


def schedule_archive(store):
    key = str(store.path.resolve())
    with _ARCHIVE_LOCK:
        if key in _ARCHIVE_JOBS: return
        _ARCHIVE_JOBS.add(key)
    def run():
        try:
            start = time.monotonic()
            while time.monotonic()-start < 10 and store.archive():
                time.sleep(.01)
            ARCHIVE_ERRORS.pop(key,None)
        except Exception as exc:
            ARCHIVE_ERRORS[key] = type(exc).__name__
        finally:
            with _ARCHIVE_LOCK: _ARCHIVE_JOBS.discard(key)
    threading.Thread(target=run,daemon=True,name='learning-archive').start()
