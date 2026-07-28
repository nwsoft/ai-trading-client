#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI 성능 메트릭 로거

- 운영 로그(실시간 표시)와 별도로 JSONL 파일에 성능 이벤트를 적재한다.
- 개인정보/사용자 입력값은 기록하지 않고, 위젯 동작 이벤트와 소요 시간/캐시 여부만 기록한다.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict

_lock = threading.Lock()
_MAX_LOG_BYTES = 20 * 1024 * 1024
_BACKUP_COUNT = 3


def _safe_iso_now() -> str:
    try:
        return datetime.now(timezone.utc).isoformat()
    except Exception:
        return datetime.utcnow().isoformat() + "Z"


def _rotate_if_needed(file_path: str, incoming_bytes: int) -> None:
    """Keep diagnostic JSONL files bounded so telemetry cannot exhaust the disk."""
    try:
        if not os.path.exists(file_path):
            return
        if os.path.getsize(file_path) + max(0, int(incoming_bytes)) <= _MAX_LOG_BYTES:
            return

        oldest = f"{file_path}.{_BACKUP_COUNT}"
        if os.path.exists(oldest):
            os.remove(oldest)
        for index in range(_BACKUP_COUNT - 1, 0, -1):
            source = f"{file_path}.{index}"
            if os.path.exists(source):
                os.replace(source, f"{file_path}.{index + 1}")
        os.replace(file_path, f"{file_path}.1")
    except Exception:
        # Rotation is best-effort; metric collection itself must stay non-fatal.
        return


def log_ui_perf_metric(widget: str, event: str, **fields: Any) -> None:
    """UI 성능 메트릭을 logs/ui_perf_metrics.jsonl 에 한 줄(JSON)로 기록한다."""
    try:
        from path_utils import get_log_dir

        payload: Dict[str, Any] = {
            "ts": _safe_iso_now(),
            "widget": str(widget or "unknown"),
            "event": str(event or "unknown"),
        }
        if fields:
            payload.update(fields)

        log_dir = get_log_dir()
        file_path = os.path.join(log_dir, "ui_perf_metrics.jsonl")

        line = json.dumps(payload, ensure_ascii=False)
        with _lock:
            os.makedirs(log_dir, exist_ok=True)
            _rotate_if_needed(file_path, len((line + "\n").encode("utf-8")))
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        # 성능 메트릭 실패가 앱 동작에 영향을 주면 안 된다.
        return
