"""Runtime helpers for bounded, repeatable market-universe selection.

These helpers deliberately do not know about orders.  They keep slow public
market-data discovery away from duplicate UI/worker requests and stabilise
short-lived regime noise before a candidate universe is replaced.
"""

from __future__ import annotations

import threading
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Dict, Hashable, Optional


class SelectionSingleFlight:
    """One in-flight selection per venue with a short successful-result cache."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: Dict[Hashable, threading.Event] = {}
        self._results: Dict[Hashable, tuple[float, Any]] = {}

    def run(
        self,
        key: Hashable,
        producer: Callable[[], Any],
        *,
        cache_ttl: float = 30.0,
        wait_timeout: float = 20.0,
    ) -> Any:
        now = time.monotonic()
        with self._lock:
            cached = self._results.get(key)
            if cached and now - cached[0] <= max(0.0, float(cache_ttl)):
                return deepcopy(cached[1])
            event = self._events.get(key)
            owner = event is None
            if owner:
                event = threading.Event()
                self._events[key] = event

        if not owner:
            assert event is not None
            if event.wait(max(0.1, float(wait_timeout))):
                with self._lock:
                    completed = self._results.get(key)
                    return deepcopy(completed[1]) if completed else []
            # Never launch a second expensive discovery because one caller was
            # slow.  The previous valid universe is safer than overlapping API
            # bursts; an empty result means no valid universe has completed yet.
            with self._lock:
                previous = self._results.get(key)
                return deepcopy(previous[1]) if previous else []

        try:
            value = producer()
            with self._lock:
                self._results[key] = (time.monotonic(), deepcopy(value))
            return value
        finally:
            with self._lock:
                completed_event = self._events.pop(key, None)
                if completed_event is not None:
                    completed_event.set()

    def invalidate(self, key: Optional[Hashable] = None) -> None:
        with self._lock:
            if key is None:
                self._results.clear()
            else:
                self._results.pop(key, None)


class TTLValueCache:
    """Small thread-safe TTL cache for public market snapshots."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._values: Dict[Hashable, tuple[float, Any]] = {}

    def get(self, key: Hashable, ttl_seconds: float) -> Any:
        with self._lock:
            row = self._values.get(key)
            if row is None or time.monotonic() - row[0] > max(0.0, float(ttl_seconds)):
                return None
            return deepcopy(row[1])

    def set(self, key: Hashable, value: Any) -> Any:
        with self._lock:
            self._values[key] = (time.monotonic(), deepcopy(value))
        return value


@dataclass
class RegimeState:
    confirmed: str
    confirmed_at: float
    pending: str = ""
    pending_count: int = 0


class RegimeStabilizer:
    """Confirm regime transitions without delaying the initial observation."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states: Dict[str, RegimeState] = {}

    def observe(
        self,
        key: str,
        observed: str,
        *,
        confirmations: int = 2,
        min_dwell_seconds: float = 600.0,
        now: Optional[float] = None,
    ) -> tuple[str, bool]:
        timestamp = time.monotonic() if now is None else float(now)
        normalized = str(observed or "unknown").strip().lower() or "unknown"
        required = max(1, int(confirmations or 1))
        with self._lock:
            state = self._states.get(key)
            if normalized == 'unknown':
                if state is not None:
                    state.pending = ''
                    state.pending_count = 0
                return (state.confirmed if state else 'unknown'), False
            if state is None:
                self._states[key] = RegimeState(normalized, timestamp)
                return normalized, False
            if normalized == state.confirmed:
                state.pending = ""
                state.pending_count = 0
                return state.confirmed, False
            if normalized != state.pending:
                state.pending = normalized
                state.pending_count = 1
            else:
                state.pending_count += 1
            dwell_ok = timestamp - state.confirmed_at >= max(0.0, float(min_dwell_seconds))
            if state.pending_count >= required and dwell_ok:
                state.confirmed = normalized
                state.confirmed_at = timestamp
                state.pending = ""
                state.pending_count = 0
                return state.confirmed, True
            return state.confirmed, False

    def current(self, key: str, default: str = "normal") -> str:
        with self._lock:
            state = self._states.get(key)
            return state.confirmed if state is not None else default
