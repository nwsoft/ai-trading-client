#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""갑작스런 종료를 재현 가능하게 만드는 세션·예외 진단."""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
import faulthandler
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


_LOCK = threading.Lock()
_SESSION_MARKER: Optional[Path] = None
_CRASH_LOG: Optional[Path] = None
_FATAL_EXCEPTION_SEEN = False
_FAULT_FILE = None
_FAULT_HANDLER_OWNED = False
_PREVIOUS_SYS_HOOK = sys.excepthook
_PREVIOUS_THREAD_HOOK = getattr(threading, "excepthook", None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_dir() -> Path:
    try:
        from path_utils import get_log_dir

        path = Path(get_log_dir())
    except Exception:
        path = Path.cwd() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _append_event(payload: Dict[str, Any]) -> None:
    path = _CRASH_LOG or (_runtime_dir() / "runtime_stability.jsonl")
    safe_payload = dict(payload)
    safe_payload.setdefault("recorded_at", _now())
    with _LOCK:
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(safe_payload, ensure_ascii=False) + "\n")


def record_exception(
    exc_type,
    exc_value,
    exc_traceback,
    *,
    source: str,
    fatal: bool,
) -> None:
    global _FATAL_EXCEPTION_SEEN
    if fatal:
        _FATAL_EXCEPTION_SEEN = True
    try:
        trace = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        _append_event({
            "event": "unhandled_exception",
            "source": str(source),
            "fatal": bool(fatal),
            "exception_type": getattr(exc_type, "__name__", str(exc_type)),
            "message": str(exc_value or ""),
            "traceback": trace[-20000:],
            "pid": os.getpid(),
        })
    except Exception:
        pass


def install_exception_hooks() -> None:
    """메인·백그라운드 스레드의 처리되지 않은 예외를 계정 로그에 남긴다."""
    def _sys_hook(exc_type, exc_value, exc_traceback):
        record_exception(
            exc_type, exc_value, exc_traceback, source="main_thread", fatal=True,
        )
        if callable(_PREVIOUS_SYS_HOOK):
            _PREVIOUS_SYS_HOOK(exc_type, exc_value, exc_traceback)

    def _thread_hook(args):
        record_exception(
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
            source=f"thread:{getattr(args.thread, 'name', 'unknown')}",
            fatal=False,
        )
        if callable(_PREVIOUS_THREAD_HOOK):
            _PREVIOUS_THREAD_HOOK(args)

    sys.excepthook = _sys_hook
    if hasattr(threading, "excepthook"):
        threading.excepthook = _thread_hook


def begin_runtime_session() -> Dict[str, Any]:
    """이전 비정상 종료 표식을 읽고 현재 세션 표식을 원자적으로 생성한다."""
    global _SESSION_MARKER, _CRASH_LOG, _FATAL_EXCEPTION_SEEN
    global _FAULT_FILE, _FAULT_HANDLER_OWNED
    runtime_dir = _runtime_dir()
    _SESSION_MARKER = runtime_dir / "runtime_session.active.json"
    _CRASH_LOG = runtime_dir / "runtime_stability.jsonl"
    _FATAL_EXCEPTION_SEEN = False

    previous: Dict[str, Any] = {}
    if _SESSION_MARKER.exists():
        try:
            previous = json.loads(_SESSION_MARKER.read_text(encoding="utf-8"))
        except Exception:
            previous = {"unreadable": True}
        _append_event({
            "event": "previous_unclean_shutdown_detected",
            "previous_session": previous,
            "pid": os.getpid(),
        })

    current = {
        "started_at": _now(),
        "pid": os.getpid(),
        "platform": sys.platform,
        "python": sys.version.split()[0],
    }
    temp = _SESSION_MARKER.with_suffix(".tmp")
    temp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(_SESSION_MARKER)
    _FAULT_HANDLER_OWNED = False
    _FAULT_FILE = None
    try:
        # pytest 등 상위 런타임이 이미 관리 중이면 가로채지 않는다.
        if not faulthandler.is_enabled():
            _FAULT_FILE = (runtime_dir / "runtime_faulthandler.log").open(
                "a", encoding="utf-8",
            )
            _FAULT_FILE.write(f"\n[{_now()}] session pid={os.getpid()}\n")
            _FAULT_FILE.flush()
            faulthandler.enable(file=_FAULT_FILE, all_threads=True)
            _FAULT_HANDLER_OWNED = True
    except Exception:
        try:
            if _FAULT_FILE is not None:
                _FAULT_FILE.close()
        except Exception:
            pass
        _FAULT_FILE = None
        _FAULT_HANDLER_OWNED = False
    install_exception_hooks()
    return {
        "previous_unclean": bool(previous),
        "previous_session": previous,
        "marker": str(_SESSION_MARKER),
    }


def mark_clean_shutdown(reason: str = "normal_shutdown") -> bool:
    """치명 예외가 없었던 명시적 종료에서만 세션 표식을 제거한다."""
    global _FAULT_FILE, _FAULT_HANDLER_OWNED
    if _FATAL_EXCEPTION_SEEN:
        return False
    marker = _SESSION_MARKER
    if marker is None:
        return False
    try:
        marker.unlink(missing_ok=True)
        _append_event({
            "event": "clean_shutdown",
            "reason": str(reason or "normal_shutdown"),
            "pid": os.getpid(),
        })
        if _FAULT_HANDLER_OWNED:
            try:
                faulthandler.disable()
            except Exception:
                pass
        try:
            if _FAULT_FILE is not None:
                _FAULT_FILE.close()
        except Exception:
            pass
        _FAULT_FILE = None
        _FAULT_HANDLER_OWNED = False
        return True
    except Exception:
        return False


def install_tk_exception_hook(root) -> None:
    """Tk callback 예외도 프로세스 종료 여부와 별개로 진단 파일에 남긴다."""
    def _tk_hook(exc_type, exc_value, exc_traceback):
        record_exception(
            exc_type, exc_value, exc_traceback, source="tk_callback", fatal=False,
        )

    try:
        root.report_callback_exception = _tk_hook
    except Exception:
        pass
