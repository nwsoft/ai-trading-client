"""Per-ledger in-process write admission, with bounded maintenance slices.

SQLite still arbitrates other processes. No API or order submission belongs
inside this boundary. Read-only connections are deliberately not serialized.
"""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading
import time

_registry_lock = threading.Lock()
_gates = {}


class Gate:
    def __init__(self):
        self.condition = threading.Condition(threading.RLock())
        self.owner = None
        self.depth = 0
        self.waiters = []
        self.completed = 0
        self.last_operation = None
        self.max_hold_ms = 0.0
        self.slowest_operation = None
        self.max_wait_ms = 0.0
        self.active_operation = None


def gate(path):
    key = str(Path(path).resolve())
    with _registry_lock:
        return _gates.setdefault(key, Gate())


@contextmanager
def admission(path, operation, *, priority=0, timeout=5):
    state = gate(path)
    thread = threading.get_ident()
    requested = time.monotonic()
    ticket = (priority, requested, object())
    with state.condition:
        if state.owner == thread:
            state.depth += 1
        else:
            state.waiters.append(ticket)
            try:
                while state.owner is not None or min(state.waiters, key=lambda t:t[:2]) is not ticket:
                    remaining = timeout - (time.monotonic()-requested)
                    if remaining <= 0:
                        raise sqlite3.OperationalError('database is locked: write admission timeout')
                    state.condition.wait(remaining)
                state.owner, state.depth = thread, 1
                state.active_operation = operation
                state.max_wait_ms = max(state.max_wait_ms, (time.monotonic()-requested)*1000)
            finally:
                state.waiters.remove(ticket)
                state.condition.notify_all()
    started = time.monotonic()
    try:
        yield
    finally:
        with state.condition:
            state.depth -= 1
            if state.depth == 0:
                state.completed += 1
                state.last_operation = operation
                elapsed = (time.monotonic()-started)*1000
                if elapsed > state.max_hold_ms:
                    state.max_hold_ms = elapsed
                    state.slowest_operation = operation
                state.owner = None
                state.active_operation = None
                state.condition.notify_all()


@contextmanager
def connection(path, *, operation, priority=0, timeout=5, budget_seconds=None):
    with admission(path, operation, priority=priority, timeout=timeout):
        conn = sqlite3.connect(path, timeout=timeout)
        try:
            if budget_seconds is not None:
                deadline = time.monotonic()+budget_seconds
                conn.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
            try:
                yield conn
            except BaseException:
                conn.set_progress_handler(None, 0)
                conn.rollback()
                raise
            else:
                conn.set_progress_handler(None, 0)
                conn.commit()
        finally:
            conn.close()


def snapshot(path):
    state = gate(path)
    with state.condition:
        return {'active_operation':state.active_operation, 'waiting_writers':len(state.waiters),
                'completed':state.completed, 'last_operation':state.last_operation,
                'max_hold_ms':round(state.max_hold_ms,2), 'max_wait_ms':round(state.max_wait_ms,2),
                'slowest_operation':state.slowest_operation,
                'scope':'process'}
