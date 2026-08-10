"""인증 사용자 주문·체결 스트림의 공통 큐·건강·재연결 계약."""

from __future__ import annotations

import time
from collections import deque
from threading import RLock
from typing import Any, Deque, Dict, List, Mapping, Optional


class AuthenticatedExecutionStream:
    """거래소 SDK가 전달한 개인 체결만 보존하며 공개 시세와 분리한다."""

    def __init__(self, venue: str, *, max_events: int = 2000, stale_after_seconds: int = 90):
        self.venue = str(venue or "").strip().lower()
        self.max_events = max(10, int(max_events))
        self.stale_after_seconds = max(10, int(stale_after_seconds))
        self._events: Deque[Dict[str, Any]] = deque(maxlen=self.max_events)
        self._seen: Deque[str] = deque(maxlen=self.max_events * 2)
        self._seen_set = set()
        self._lock = RLock()
        self._connected = False
        self._connected_at = 0.0
        self._last_event_at = 0.0
        self._last_disconnect_reason = ""
        self._reconnect_attempts = 0
        self._next_reconnect_at = 0.0

    @staticmethod
    def _event_key(event: Mapping[str, Any]) -> str:
        return "|".join(str(event.get(key) or "") for key in (
            "exchange", "trade_id", "id", "order_id", "symbol", "timestamp", "filled",
        ))

    def mark_connected(self) -> None:
        with self._lock:
            self._connected = True
            self._connected_at = time.monotonic()
            self._last_disconnect_reason = ""
            self._reconnect_attempts = 0
            self._next_reconnect_at = 0.0

    def mark_disconnected(self, reason: str) -> None:
        with self._lock:
            self._connected = False
            self._last_disconnect_reason = str(reason or "unknown")
            self._reconnect_attempts += 1
            backoff = min(60.0, float(2 ** min(self._reconnect_attempts, 6)))
            self._next_reconnect_at = time.monotonic() + backoff

    def reconnect_due(self, now: Optional[float] = None) -> bool:
        current = time.monotonic() if now is None else float(now)
        with self._lock:
            return not self._connected and current >= self._next_reconnect_at

    def push(self, event: Mapping[str, Any]) -> bool:
        payload = dict(event or {})
        if not payload:
            return False
        payload.setdefault("exchange", self.venue)
        key = self._event_key(payload)
        if not key.strip("|"):
            return False
        with self._lock:
            if key in self._seen_set:
                return False
            if len(self._seen) == self._seen.maxlen:
                expired = self._seen.popleft()
                self._seen_set.discard(expired)
            self._seen.append(key)
            self._seen_set.add(key)
            self._events.append(payload)
            self._last_event_at = time.monotonic()
        return True

    def drain_execution_events(self, limit: int = 200) -> List[Dict[str, Any]]:
        rows = []
        with self._lock:
            for _ in range(min(max(1, int(limit)), len(self._events))):
                rows.append(self._events.popleft())
        return rows

    def execution_stream_healthy(self, now: Optional[float] = None) -> bool:
        current = time.monotonic() if now is None else float(now)
        with self._lock:
            if not self._connected:
                return False
            reference = self._last_event_at or self._connected_at
            return bool(reference and current - reference <= self.stale_after_seconds)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "venue": self.venue,
                "connected": self._connected,
                "healthy": self.execution_stream_healthy(),
                "queued": len(self._events),
                "reconnect_attempts": self._reconnect_attempts,
                "last_disconnect_reason": self._last_disconnect_reason,
                "next_reconnect_at_monotonic": self._next_reconnect_at,
            }
