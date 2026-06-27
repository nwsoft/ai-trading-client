#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""단일 전역 로그 스트림 (Draft v2 Step2)
- 목적: 모든 거래/AI/시스템 이벤트를 한 버퍼에 적재 후 필터링된 뷰 제공
- 교체 범위: 기존 RealtimeLogWidget 직접 add_log 호출 경로 → LogStreamService.add_event
"""
from __future__ import annotations
import threading
import time
from dataclasses import dataclass, asdict
from collections import deque
from typing import Deque, List, Optional, Callable, Iterable, Dict, Any

@dataclass
class LogEvent:
    ts: float
    exchange: str
    level: str
    category: str
    message: str

    def format_line(self) -> str:
        t = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.ts))
        ex_part = self.exchange if self.exchange else 'global'
        return f"{t} | {self.level:8} - {self.message} (ex={ex_part})"

class LogStreamService:
    """In-memory ring buffer + optional subscribers."""
    def __init__(self, maxlen: int = 8000):
        self._buf: Deque[LogEvent] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._subs: List[Callable[[LogEvent], None]] = []
        self._maxlen = maxlen

    def add_event(self, exchange: str, level: str, category: str, message: str) -> LogEvent:
        ev = LogEvent(time.time(), exchange or '', level.upper(), category, message)
        with self._lock:
            self._buf.append(ev)
            subs = list(self._subs)
        # 구독자 호출 (락 밖)
        for cb in subs:
            try:
                cb(ev)
            except Exception:
                pass
        return ev

    def subscribe(self, callback: Callable[[LogEvent], None]):
        with self._lock:
            self._subs.append(callback)

    def unsubscribe(self, callback: Callable[[LogEvent], None]):
        with self._lock:
            try:
                self._subs.remove(callback)
            except ValueError:
                pass

    def query(self, *, exchange: Optional[str] = None, level: Optional[str] = None,
              category: Optional[str] = None, since: Optional[float] = None,
              limit: Optional[int] = None) -> List[LogEvent]:
        with self._lock:
            items: Iterable[LogEvent] = list(self._buf)
        if since is not None:
            items = [e for e in items if e.ts >= since]
        if exchange:
            items = [e for e in items if e.exchange == exchange]
        if level:
            items = [e for e in items if e.level == level.upper()]
        if category:
            items = [e for e in items if e.category == category]
        if limit:
            return list(items)[-limit:]
        return list(items)

    def to_dicts(self, **filters) -> List[Dict[str, Any]]:
        return [asdict(e) for e in self.query(**filters)]

# 전역 싱글톤 (간단 접근)
_global_log_stream: Optional[LogStreamService] = None

def get_log_stream() -> LogStreamService:
    global _global_log_stream
    if _global_log_stream is None:
        _global_log_stream = LogStreamService()
    return _global_log_stream
