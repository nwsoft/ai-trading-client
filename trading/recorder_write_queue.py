"""Local durable retry for failed decision/close writes; never submits orders.

The outbox is separate from trading.db so its writer can preserve an intent
while the main DB is busy. A receipt committed with the main write makes a
crash between that commit and outbox deletion safe to replay.
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import uuid
import weakref
from contextlib import contextmanager, closing
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

_lock = threading.Lock()
_running: set[str] = set()
METHODS = {"save_ai_decision", "update_trade_log", "insert_trade_log", "record_partial_trade_close", "save_exchange_execution_history", "save_exchange_order_receipt"}
METHODS.update({'log_risk_event','save_stock_execution_metric','update_crypto_order_command','_close_managed_entry_group'})


def _path(recorder):
    return str(Path(recorder.db_path).with_suffix('.pending_writes.sqlite3'))


@contextmanager
def _connect(recorder):
    with closing(sqlite3.connect(_path(recorder), timeout=5)) as conn:
        with conn:
            conn.execute('CREATE TABLE IF NOT EXISTS pending (token TEXT PRIMARY KEY, method TEXT NOT NULL, payload TEXT NOT NULL, error TEXT)')
            yield conn


def is_busy(exc):
    return isinstance(exc, sqlite3.OperationalError) and any(
        s in str(exc).lower() for s in ('locked', 'busy'))


def begin_receipt(conn, token):
    if not token:
        return False
    conn.execute('BEGIN IMMEDIATE')
    conn.execute('CREATE TABLE IF NOT EXISTS record_write_receipts (token TEXT PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)')
    return conn.execute('SELECT 1 FROM record_write_receipts WHERE token=?', (token,)).fetchone() is not None


def finish_receipt(conn, token):
    if token:
        conn.execute('INSERT INTO record_write_receipts(token) VALUES (?)', (token,))


def enqueue(recorder, method, payload):
    if method not in METHODS:
        raise ValueError('unsupported_record_write')
    payload = dict(payload)
    payload.pop('_write_token', None)
    if method == 'insert_trade_log':
        record = payload.get('trade_log') or {}
        if not record.get('order_id') or not record.get('exchange'):
            raise ValueError('entry_retry_requires_exact_order_identity')
    position = payload.pop('position', None)
    if method == 'update_trade_log':
        # No symbol-only replay: it might hit a later re-entry after restart.
        payload['exchange'] = payload.get('exchange') or recorder.exchange
        payload['entry_order_id'] = payload.get('entry_order_id') or getattr(position, 'entry_order_id', None)
        if not payload['exchange'] or not payload['entry_order_id']:
            raise ValueError('close_retry_requires_exact_entry_identity')
        if position is not None:
            payload['position'] = {k: getattr(position, k, None) for k in ('entry_order_id', 'tp_price', 'sl_price')}
    def encode(value):
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError('unsupported_record_payload')
    raw = json.dumps(payload, ensure_ascii=False, default=encode, allow_nan=False)
    token = uuid.uuid4().hex
    with _connect(recorder) as conn:
        conn.execute('INSERT INTO pending(token,method,payload) VALUES (?,?,?)', (token, method, raw))
    schedule(recorder)
    return token


def drain(recorder, limit=20):
    if not Path(_path(recorder)).exists():
        return 0
    with _connect(recorder) as conn:
        rows = conn.execute('SELECT token,method,payload,error FROM pending WHERE error IS NULL ORDER BY rowid LIMIT ?', (limit,)).fetchall()
        cursor = getattr(recorder, '_record_review_cursor', 0)
        reviews = conn.execute('SELECT rowid,token,method,payload,error FROM pending WHERE error IS NOT NULL AND rowid>? ORDER BY rowid LIMIT ?', (cursor, limit)).fetchall()
        if not reviews and cursor:
            reviews = conn.execute('SELECT rowid,token,method,payload,error FROM pending WHERE error IS NOT NULL ORDER BY rowid LIMIT ?', (limit,)).fetchall()
        recorder._record_review_cursor = reviews[-1][0] if reviews else 0
        rows.extend(row[1:] for row in reviews)
    applied = 0
    for token, method, raw, error in rows:
        if method not in METHODS:
            continue
        payload = json.loads(raw)
        if method == 'insert_trade_log':
            from trading.recorder import TradeLog
            payload['trade_log'] = TradeLog(**payload['trade_log'])
        if isinstance(payload.get('position'), dict):
            payload['position'] = SimpleNamespace(**payload['position'])
        try:
            if error:
                # A later official reconciliation may supersede a deferred
                # local estimate. Never rewrite that verified close.
                if method != 'update_trade_log' or not _verified_close_supersedes(recorder, payload):
                    continue
                result = True
            else:
                result = getattr(recorder, method)(**payload, _write_token=token)
            if result is False:
                # An exact row may already be closed by reconciliation. Do not
                # reinterpret this as success or overwrite newer verified data.
                if method != 'update_trade_log' or not _verified_close_supersedes(recorder, payload):
                    raise ValueError('record_retry_requires_reconciliation')
            with _connect(recorder) as conn:
                conn.execute('DELETE FROM pending WHERE token=?', (token,))
            applied += 1
        except Exception as exc:
            if is_busy(exc):
                break
            with _connect(recorder) as conn:
                conn.execute('UPDATE pending SET error=? WHERE token=?', (type(exc).__name__, token))
    return applied


def _verified_close_supersedes(recorder, payload):
    """Only an exact entry AND exit order can resolve an old close intent."""
    if not payload.get('entry_order_id') or not payload.get('exit_order_id'):
        return False
    with closing(sqlite3.connect(f'file:{recorder.db_path}?mode=ro', uri=True, timeout=1)) as conn:
        rows = conn.execute('''SELECT reconciliation_status, net_pnl, exit_order_id, exit_time
            FROM trade_log WHERE symbol=? AND lower(exchange)=? AND order_id=?''',
            (payload['symbol'], str(payload['exchange']).lower(), str(payload['entry_order_id']))).fetchall()
    if len(rows) != 1:
        return False
    state, pnl, exit_order, exit_time = rows[0]
    return (state == 'exchange_confirmed' and bool(exit_time)
            and str(exit_order) == str(payload['exit_order_id'])
            and pnl is not None and math.isfinite(float(pnl)))


def schedule(recorder):
    if not Path(_path(recorder)).exists():
        return
    path = str(Path(recorder.db_path).resolve())
    with _lock:
        if path in _running:
            return
        _running.add(path)
    reference = weakref.ref(recorder)
    def work():
        again = False
        delay = 10
        try:
            # Bounded work; subsequent saves/startup resume remaining records.
            for _ in range(3):
                owner = reference()
                if owner is None:
                    break
                if not drain(owner):
                    break
            owner = reference()
            if owner is not None:
                remaining = status(owner.db_path)
                again = remaining['pending'] > 0 or remaining['needs_review'] > 0
                delay = 10 if remaining['pending'] else 60
        except Exception:
            again = True  # Keep the outbox; no dropped record on I/O failure.
        finally:
            with _lock:
                _running.discard(path)
            if again:
                def resume():
                    owner = reference()
                    if owner is not None:
                        schedule(owner)
                timer = threading.Timer(delay, resume)
                timer.daemon = True
                timer.start()
    threading.Thread(target=work, name='record-write-retry', daemon=True).start()


def status(db_path):
    path = Path(db_path).with_suffix('.pending_writes.sqlite3')
    if not path.exists():
        return {'pending': 0, 'needs_review': 0}
    with closing(sqlite3.connect(f'file:{path}?mode=ro', uri=True)) as conn:
        row = conn.execute('SELECT count(*),coalesce(sum(error IS NOT NULL),0) FROM pending').fetchone()
    return {'pending': row[0] - row[1], 'needs_review': row[1]}


def unresolved_closes(db_path, venue):
    path = Path(db_path).with_suffix('.pending_writes.sqlite3')
    if not path.exists():
        return 0
    with closing(sqlite3.connect(f'file:{path}?mode=ro', uri=True)) as conn:
        entries = conn.execute('''SELECT count(*) FROM pending WHERE method='insert_trade_log'
            AND lower(json_extract(payload,'$.trade_log.exchange'))=?
            AND lower(COALESCE(json_extract(payload,'$.trade_log.execution_mode'),'unknown')) NOT IN ('paper','mock','learning')''', (venue.lower(),)).fetchone()[0]
        if not conn.execute("SELECT 1 FROM pending WHERE method IN ('update_trade_log','record_partial_trade_close','_close_managed_entry_group') AND lower(json_extract(payload,'$.exchange'))=? LIMIT 1", (venue.lower(),)).fetchone():
            return entries
        conn.execute('ATTACH DATABASE ? AS ledger', (f'file:{Path(db_path).resolve()}?mode=ro',))
        entries += conn.execute('''SELECT count(*) FROM pending p WHERE method='_close_managed_entry_group'
            AND lower(json_extract(payload,'$.exchange'))=?
            AND EXISTS (SELECT 1 FROM json_each(p.payload,'$.entry_order_ids') ids
                WHERE NOT EXISTS (SELECT 1 FROM ledger.trade_log t
                    WHERE t.symbol=json_extract(p.payload,'$.symbol')
                    AND lower(t.exchange)=lower(json_extract(p.payload,'$.exchange'))
                    AND t.order_id=CAST(ids.value AS TEXT)
                    GROUP BY t.order_id HAVING count(*)=count(t.execution_mode)
                    AND min(lower(t.execution_mode)) IN ('paper','mock','learning')
                    AND max(lower(t.execution_mode)) IN ('paper','mock','learning')))''',(venue.lower(),)).fetchone()[0]
        # Confirmed PAPER-only identity cannot block LIVE. Unknown or ambiguous
        # historical identities remain pending instead of being guessed away.
        return entries + conn.execute('''SELECT count(*) FROM pending p
            WHERE method IN ('update_trade_log','record_partial_trade_close') AND lower(json_extract(payload,'$.exchange'))=?
            AND NOT EXISTS (SELECT 1 FROM ledger.trade_log t
                WHERE t.symbol=json_extract(p.payload,'$.symbol')
                AND lower(t.exchange)=lower(json_extract(p.payload,'$.exchange'))
                AND t.order_id=CAST(json_extract(p.payload,'$.entry_order_id') AS TEXT)
                GROUP BY t.symbol,lower(t.exchange),t.order_id
                HAVING count(*)=count(t.execution_mode) AND min(lower(t.execution_mode)) IN ('paper','mock','learning')
                    AND max(lower(t.execution_mode)) IN ('paper','mock','learning'))''', (venue.lower(),)).fetchone()[0]
