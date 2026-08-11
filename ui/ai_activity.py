"""Shared AI activity ledger used by dashboard and assistant surfaces."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, Iterable, List


class AIActivityLedger:
    """Thread-safe request lifecycle ledger with bounded retention."""

    def __init__(self, max_size: int = 30) -> None:
        self.max_size = max(1, int(max_size))
        self.events: List[Dict[str, Any]] = []
        self.lock = threading.RLock()
        self._sequence = 0

    def record(
        self,
        *,
        action: str,
        title: str,
        plan_lines: Iterable[str],
        risk_level: str,
        risk_reasons: Iterable[str],
        result: str,
        status: str = "completed",
    ) -> str:
        now = datetime.now()
        with self.lock:
            self._sequence += 1
            event_id = f"ai-{now.strftime('%Y%m%d%H%M%S%f')}-{self._sequence}"
            self.events.append({
                "id": event_id,
                "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                "action": str(action),
                "title": str(title),
                "plan_lines": list(plan_lines or []),
                "risk_level": str(risk_level),
                "risk_reasons": list(risk_reasons or []),
                "result": str(result),
                "status": str(status or "completed"),
            })
            if len(self.events) > self.max_size:
                del self.events[:-self.max_size]
        return event_id

    def finish(self, event_id: str, *, result: str, failed: bool = False) -> bool:
        if not event_id:
            return False
        with self.lock:
            for event in reversed(self.events):
                if str(event.get("id", "")) != str(event_id):
                    continue
                event["status"] = "failed" if failed else "completed"
                event["result"] = str(result or ("오류" if failed else "응답 완료"))
                event["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                return True
        return False

    def snapshot(self, limit: int | None = None) -> List[Dict[str, Any]]:
        with self.lock:
            selected = self.events[-max(0, int(limit)):] if limit is not None else self.events
            return [dict(item) for item in selected]
