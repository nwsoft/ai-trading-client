#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""통합 로그 어댑터
- 표준 logger + LogStreamService 동시 기록
- 대시보드/트레이딩/AI 모듈 공용 경량 API 제공

사용 예:
    from log_system.log_adapter import log_event
    log_event('system', '대시보드 초기화 완료')

카테고리 권장값:
    system | trade | ws | risk | ai | order | balance | position | config | user
"""
from __future__ import annotations
import logging
import threading
import time
from typing import Optional
import re

# LogStream 모듈 단일화: 어느 경로로 import하더라도 동일한 싱글톤을 사용하도록 강제
import os
import sys
import importlib
try:
    # log_system 경로 우선 시도
    ls_mod = importlib.import_module('log_system.log_stream')
except Exception:
    # 폴백: 현재 디렉토리를 sys.path에 추가 후 로컬 모듈로 로드
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    ls_mod = importlib.import_module('log_stream')

# 모듈 별칭 동기화: 서로 다른 경로명이 동일 모듈 인스턴스를 가리키도록 고정
sys.modules['log_stream'] = ls_mod
sys.modules['log_system.log_stream'] = ls_mod

# --- 이 모듈(log_adapter) 자체의 단일화도 보장 ---
# 다양한 import 경로('log_adapter', 'log_system.log_adapter', 'noahai_client.log_system.log_adapter')로
# 불러와질 수 있으므로 동일한 모듈 객체로 별칭을 모두 등록한다.
try:
    import types as _types
    _this_module = sys.modules.get(__name__)
    if isinstance(_this_module, _types.ModuleType):
        for _alias in (
            'log_adapter',
            'log_system.log_adapter',
            'noahai_client.log_system.log_adapter',
        ):
            sys.modules[_alias] = _this_module
except Exception:
    pass

# 공개 API 바인딩
get_log_stream = ls_mod.get_log_stream

# 전역 기본 로거 (파일 저장 보장)
try:
    from loguru import logger as _loguru_logger
    _base_logger = _loguru_logger

    # 파일 핸들러가 없으면 추가
    from path_utils import get_log_file_path
    log_path = get_log_file_path()

    # 기존 파일 핸들러 확인 (안전한 방법 사용)
    has_file_handler = False
    try:
        # loguru의 내부 구조 안전하게 접근
        from typing import Any
        core = getattr(_base_logger, '_core', None)
        if core is not None:
            handlers = getattr(core, 'handlers', {})
            for handler in handlers.values():
                if hasattr(handler, '_sink') and hasattr(handler._sink, 'name') and log_path in str(handler._sink.name):
                    has_file_handler = True
                    break
    except Exception:
        # 핸들러 확인 실패 시 새로 추가 (안전한 선택)
        has_file_handler = False

    if not has_file_handler:
        # 🔥 로그 레벨을 설정 파일에서 읽어오거나 환경변수에서 확인
        import os
        log_level = os.environ.get('NOAHAI_LOG_LEVEL', 'INFO').upper()
        # 설정 파일에서 로그 레벨 확인 (동적 로드)
        try:
            from path_utils import get_config_dir
            config_dir = get_config_dir()
            settings_path = os.path.join(config_dir, 'settings.json')
            if os.path.exists(settings_path):
                import json
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    log_level = settings.get('log_level', log_level).upper()
        except Exception:
            pass
        
        _base_logger.add(
            log_path,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} - {message}",
            level=log_level,  # 🔥 설정 파일의 로그 레벨 사용
            rotation="200 MB",
            retention="30 days",
            encoding="utf-8",
            enqueue=True,
        )

except ImportError:
    # loguru가 없으면 표준 logging 사용
    _base_logger = logging.getLogger("noahai")
    if not _base_logger.handlers:
        # 메인에서 이미 설정했을 수도 있으므로 중복 핸들러 방지
        _base_logger.addHandler(logging.StreamHandler())
        _base_logger.setLevel(logging.INFO)

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_LEADING_LOG_PREFIX = re.compile(r"^\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s*\|\s*[A-Z]+\s*-\s*")
_DUP_WINDOW_SEC = 2.0
_DUP_STATE_LOCK = threading.Lock()
_DUP_STATE: dict[tuple[str, str, str, str], dict[str, float | int]] = {}


def flush_pending_logs() -> bool:
    """enqueue sink에 남은 로그를 프로세스 종료 전 디스크로 보낸다."""
    try:
        complete = getattr(_base_logger, 'complete', None)
        if callable(complete):
            complete()
        for handler in list(logging.getLogger().handlers):
            try:
                handler.flush()
            except Exception:
                pass
        return True
    except Exception:
        return False


class _StreamForwardHandler(logging.Handler):
    """표준 logging 레코드를 LogStreamService로 전달하는 핸들러.
    - log_event에서 이미 스트림에 넣은 레코드는 중복 방지(_from_log_event 플래그)로 스킵
    - 메시지 접두부의 카테고리([category])와 접미부의 (ex=...)를 파싱
    """
    _cat_pat = re.compile(r"^\[(?P<cat>[^\]]+)\]\s*(?P<rest>.*)$")
    _ex_pat = re.compile(r"\(ex=(?P<ex>[^)]+)\)\s*$")

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # log_event에서 이미 스트림 적재한 레코드는 중복 적재를 피한다.
            if bool(getattr(record, "_from_log_event", False)):
                return

            # 🔥 log_event 경유 메시지도 LogStreamService에 추가 (UI 표시용)
            # 파일 저장은 별도 핸들러가 담당하므로 여기서는 UI용만 처리

            msg = record.getMessage()
            category = "system"
            exchange = ""

            # 카테고리 추출: "[category] 메시지" 형태
            m = self._cat_pat.match(msg)
            if m:
                category = m.group("cat").strip() or category
                msg = m.group("rest").strip()
            else:
                # 휴리스틱 카테고리 매핑: 기존 logger.info 텍스트를 자동 분류
                lower_msg = msg.lower()
                try:
                    if any(k in lower_msg for k in (
                        "분석 시작", "분석 완료", "분석 과정 상세", "진입 전 분석", "analysis", "ai ", "동적 ai",
                    )):
                        category = "analysis"
                    elif any(k in lower_msg for k in (
                        "신호 상세", "전략", "리스크", "전략결정", "strategy", "거래 모드", "레버리지",
                    )):
                        category = "strategy"
                    elif any(k in lower_msg for k in (
                        "거래 시작", "거래 사이클", "신호 없음", "시그널", "허용", "금지", "trade ",
                    )):
                        category = "trade"
                    elif any(k in lower_msg for k in (
                        "거래 실행", "주문", "체결", "미실행", "실패", "취소", "tp/sl", " tp ", " sl ", "order",
                    )):
                        category = "order"
                    elif any(k in lower_msg for k in (
                        "모니터링", "집중", "중단", "중지", "감시", "monitor",
                    )):
                        category = "monitor"
                    elif any(k in lower_msg for k in (
                        "청산", "종료", "포지션 종료", "익절", "손절", "exit",
                    )):
                        category = "exit"
                except Exception:
                    pass

            # exchange 추출: "...(ex=binance)" 형태
            m2 = self._ex_pat.search(msg)
            if m2:
                exchange = (m2.group("ex") or "").strip()
                # 표시용 메시지에서는 (ex=...) 제거
                msg = self._ex_pat.sub("", msg).rstrip()

            lvl = (record.levelname or "INFO").upper()
            if lvl not in _VALID_LEVELS:
                lvl = "INFO"

            try:
                get_log_stream().add_event(exchange, lvl, category, msg)
            except Exception:
                pass
        except Exception:
            # 스트림 전달 중 오류는 무시 (표준 로깅 흐름 방해 금지)
            pass


def log_event(category: str, message: str, *, exchange: Optional[str] = None, level: str = "INFO", logger: Optional[logging.Logger] = None):
    """카테고리 기반 단일 호출 로깅.
    - LogStreamService 버퍼에 이벤트 적재 (UI 표시용)
    - 표준 logger에도 동일 레벨 기록 (파일 저장용)
    - 통일된 형식으로 두 곳 모두 기록
    """
    try:
        lvl = level.upper()
        if lvl not in _VALID_LEVELS:
            lvl = "INFO"

        # 파일 sink(loguru)가 시간/레벨 포맷을 붙이므로 메시지는 본문만 유지한다.
        # (기존 중복 포맷: "YYYY.. | INFO - YYYY.. | INFO - ..." 제거)
        formatted_message = str(message)
        # 상위 로거에서 이미 포맷된 문자열이 전달될 때 시간/레벨 프리픽스를 제거한다.
        while True:
            trimmed = _LEADING_LOG_PREFIX.sub("", formatted_message, count=1)
            if trimmed == formatted_message:
                break
            formatted_message = trimmed
        if exchange and "(ex=" not in formatted_message:
            formatted_message = f"{formatted_message} (ex={exchange})"

        # 동일 메시지 폭주를 짧은 윈도우에서 억제해 UI/파일 I/O 부담을 낮춘다.
        ex_key = str(exchange or '')
        dedup_key = (ex_key, lvl, str(category or 'system'), formatted_message)
        summary_line: Optional[str] = None
        now = time.time()
        with _DUP_STATE_LOCK:
            state = _DUP_STATE.get(dedup_key)
            if state and (now - float(state.get('last_ts', 0.0)) <= _DUP_WINDOW_SEC):
                state['last_ts'] = now
                state['suppressed'] = int(state.get('suppressed', 0)) + 1
                return

            if state and int(state.get('suppressed', 0)) > 0:
                summary_line = (
                    f"(중복 로그 억제) 동일 로그 {int(state.get('suppressed', 0))}회 생략: "
                    f"{formatted_message[:140]}"
                )
            _DUP_STATE[dedup_key] = {'last_ts': now, 'suppressed': 0}

            # 메모리 상한 관리
            if len(_DUP_STATE) > 2000:
                for k, _ in sorted(_DUP_STATE.items(), key=lambda kv: float(kv[1].get('last_ts', 0.0)))[:500]:
                    _DUP_STATE.pop(k, None)

        # LogStream 적재 (UI 표시용) - 원본 메시지 전송
        try:
            if summary_line:
                get_log_stream().add_event(exchange or '', 'WARNING', 'system', summary_line)
            get_log_stream().add_event(exchange or '', lvl, category, message)
        except Exception:
            pass

        # 표준 logger (파일 저장용) - loguru 우선 사용
        lg = logger or _base_logger
        try:
            # loguru인 경우 직접 호출
            if hasattr(lg, 'info') and hasattr(lg, 'bind'):
                # loguru 사용
                if summary_line:
                    getattr(lg, 'warning', lg.info)(f"{summary_line}{f' (ex={exchange})' if exchange else ''}")
                log_fn = getattr(lg, lvl.lower(), lg.info)
                log_fn(formatted_message)
            else:
                # 표준 logging 사용
                if summary_line:
                    getattr(lg, 'warning', lg.info)(
                        f"{summary_line}{f' (ex={exchange})' if exchange else ''}",
                        extra={"_from_log_event": True},
                    )
                log_fn = getattr(lg, lvl.lower(), lg.info)
                log_fn(formatted_message, extra={"_from_log_event": True})
        except Exception:
            pass

        # 🔥 터미널 출력은 개발 시에만 활성화 (환경변수 NOAHAI_DEV_CONSOLE=1)
        try:
            if os.environ.get("NOAHAI_DEV_CONSOLE", "0") == "1":
                print(formatted_message)
        except Exception:
            pass
    except Exception:
        pass


def log_exception(category: str, message: str, *, exchange: Optional[str] = None, exc: Exception | None = None, logger: Optional[logging.Logger] = None):
    """예외 상황 로깅 (ERROR 레벨, traceback은 표준 logger에 맡김)."""
    full_msg = message
    if exc is not None:
        full_msg = f"{message}: {exc}"
    log_event(category, full_msg, exchange=exchange, level="ERROR", logger=logger)

__all__ = ["log_event", "log_exception", "flush_pending_logs"]

# --- 전역 핸들러 장착: 애플리케이션 로거들의 표준 로그를 실시간 스트림으로 포워딩 ---
try:
    _root = logging.getLogger()
    # 동일 핸들러 중복 장착 방지: 클래스 비교 대신 센티넬 플래그 사용(모듈 중복 임포트 대비)
    if not getattr(_root, '_noahai_stream_forward_installed', False):
        _root.addHandler(_StreamForwardHandler())
        try:
            setattr(_root, '_noahai_stream_forward_installed', True)
        except Exception:
            pass
except Exception:
    pass
