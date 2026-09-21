"""Structured operational evidence survives diagnostic log rotation."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from trading.event_contract import metadata, canonical_json

_LOCK = threading.RLock()
_INITIALIZED = set()
_ERRORS = {}


def is_important(category, level, message):
    return category in {'order','position','exit','risk','strategy','config'} or level in {'ERROR','CRITICAL'} or any(
        word in message.lower() for word in ('차단','청산','체결','주문','blocked','filled','rejected'))


def persist(category, message, level, exchange, execution_mode='unknown', details=None, *, root=None):
    from path_utils import get_app_data_dir
    root = Path(root or get_app_data_dir()).resolve()
    event = dict(details or {})
    event.update(exchange=exchange, execution_mode=execution_mode)
    event.setdefault('event_kind',category)
    meta = metadata(category, event, exchange=exchange)
    payload = {**event, **meta, 'message': message, 'level': level, 'symbol': event.get('symbol')}
    path = root / 'event_audit.sqlite3'
    try:
        root.mkdir(parents=True, exist_ok=True)
        with _LOCK, closing(sqlite3.connect(path, timeout=3)) as conn, conn:
            if str(path) not in _INITIALIZED or not conn.execute("SELECT 1 FROM sqlite_master WHERE name='events'").fetchone():
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,exchange TEXT,execution_mode TEXT,event_time TEXT,body TEXT NOT NULL)')
                conn.execute('CREATE INDEX IF NOT EXISTS audit_venue_time ON events(exchange,event_time DESC)')
                _INITIALIZED.add(str(path))
            conn.execute('INSERT INTO events(exchange,execution_mode,event_time,body) VALUES(?,?,?,?)',
                         (meta['exchange'],meta['execution_mode'],meta['event_time'],canonical_json(payload)))
        _ERRORS.pop(str(root), None)
        payload['_audit_persisted'] = True
    except (OSError, sqlite3.Error, ValueError) as exc:
        _ERRORS[str(root)] = type(exc).__name__
        payload['_audit_persisted'] = False
        # Avoid logging recursion; caller still emits the original text to diagnostics.
    return payload


def failure(root): return _ERRORS.get(str(Path(root).resolve()))
