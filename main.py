#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQt5 진입점
로그인 완료 후 dashboard 실행, API 초기화, 트레이딩 루프 실행
"""

# 표준 라이브러리
import atexit
import importlib.util
import json
import math
import os
import signal
import sys
import sysconfig
import time
import traceback
import warnings
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Mapping, Sequence, Union

# 표준 logging 모듈 import (프로젝트 log_system과 분리되어 충돌 없음)
import logging
from logging.handlers import RotatingFileHandler

# 서드파티 라이브러리
try:
    from loguru import logger as _loguru_logger  # type: ignore[import]
except ImportError:  # pragma: no cover - 선택적 의존성
    _loguru_logger = None

# --- Simple Trading State Manager (sync) ---
class TradingState:
    IDLE = "IDLE"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOP_PENDING = "STOP_PENDING"  # 포지션 청산 대기 중
    STOPPED = "STOPPED"

class TradingStateManager:
    def __init__(self):
        self.state = TradingState.IDLE
        self.exchange = None  # 'binance' | 'bybit' | ...
        self.is_auto = False
        self.stop_requested = False  # 🔥 정지 요청 플래그 추가

    def can_start(self):
        return self.state in (TradingState.IDLE, TradingState.STOPPED)

    def can_stop(self):
        return self.state in (TradingState.RUNNING,)

    def mark_starting(self, exchange, is_auto: bool):
        self.state = TradingState.STARTING
        self.exchange = exchange
        self.is_auto = is_auto
        self.stop_requested = False  # 🔥 시작 시 정지 요청 초기화

    def mark_running(self):
        self.state = TradingState.RUNNING
        self.stop_requested = False  # 🔥 실행 시 정지 요청 초기화

    def mark_stop_pending(self):
        """정지 대기 상태로 변경 (포지션 청산 대기)"""
        self.state = TradingState.STOP_PENDING
        self.stop_requested = True  # 🔥 정지 요청 플래그 설정

    def mark_stopped(self):
        """완전 정지 상태로 변경"""
        self.state = TradingState.STOPPED
        self.stop_requested = True

    def mark_idle(self):
        self.state = TradingState.IDLE
        self.exchange = None
        self.is_auto = False
        self.stop_requested = False  # 🔥 유휴 상태에서 정지 요청 초기화
# --- end ---

# 프로젝트 모듈
from trading.trading_worker import TradingWorker

# 프로젝트 로깅 모듈 (log_system으로 변경되어 충돌 없음)
try:
    from log_system.log_adapter import log_event, log_exception
except ImportError:
    # 개발 환경 fallback
    import sys
    _CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    _LOG_SYSTEM_DIR = os.path.join(_CURRENT_DIR, 'log_system')
    if _LOG_SYSTEM_DIR not in sys.path:
        sys.path.insert(0, _LOG_SYSTEM_DIR)
    from log_adapter import log_event, log_exception  # type: ignore


def _get_fallback_logger(name: str = "NoahAI") -> logging.Logger:
    """loguru가 없을 때 사용할 표준 logging 로거를 준비"""
    fallback = logging.getLogger(name)
    if not fallback.handlers:
        # 콘솔 핸들러는 log_adapter가 담당 — 여기서는 기본 핸들러를 비워두고
        # 파일 핸들러는 setup_logging에서 설정
        fallback.addHandler(logging.NullHandler())
    fallback.setLevel(logging.INFO)
    return fallback


def _get_loguru_logger():
    """loguru logger가 있으면 반환하고, 없으면 표준 logging 로거를 전달"""
    return _loguru_logger if _loguru_logger is not None else _get_fallback_logger()

# 전역 참조(종료 핸들러에서 접근)
# 타입 추론 오류 방지를 위해 명시적으로 Any로 주석 처리
_DASHBOARD_REF: Dict[str, Any] = {"obj": None}
_SHUTDOWN_IN_PROGRESS = False

def _graceful_shutdown():
    """인터프리터 종료/크래시 등 모든 종료 경로에서 마지막 안전 정리"""
    try:
        d = _DASHBOARD_REF.get("obj")
        if d and d.winfo_exists():
            # UI 스레드에서 안전하게 종료 (원래 방식 복원)
            try:
                d.after(0, d.on_closing)
            except:
                # after 실패 시 직접 호출 (최후의 수단)
                try:
                    d.on_closing()
                except:
                    pass
    except:
        pass

    # 🔥 중요: atexit 핸들러에서 재시작하지 않도록 플래그 설정
    global _SHUTDOWN_IN_PROGRESS
    _SHUTDOWN_IN_PROGRESS = True

# atexit 등록은 프로그램 시작 후에 수행 (atexit.register 제거)

# Ctrl+C(SIGINT) 처리: 터미널에서 강제 중단도 안전 종료
def _sigint_handler(signum, frame):
    _graceful_shutdown()
    # 즉시 프로세스 종료(대기 안 함)
    os._exit(0)

signal.signal(signal.SIGINT, _sigint_handler)

# Windows 콘솔 종료 이벤트 처리 (CTRL_CLOSE_EVENT 등)
if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    HandlerFunc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    # dwCtrlType: 0=CTRL_C_EVENT, 1=CTRL_BREAK_EVENT, 2=CTRL_CLOSE_EVENT, 5=LOGOFF, 6=SHUTDOWN
    def _console_ctrl_handler(dwCtrlType):
        _graceful_shutdown()
        # CTRL_C / CTRL_BREAK 도 여기서 즉시 종료
        import os
        os._exit(0)

    _handler = HandlerFunc(_console_ctrl_handler)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_handler, True)

# Python 모듈 경로 보정: 이 파일이 있는 폴더를 sys.path 최우선으로
try:
    _THIS_DIR = os.path.dirname(os.path.abspath(__file__))
    if _THIS_DIR not in sys.path:
        sys.path.insert(0, _THIS_DIR)
except Exception:
    pass

# 🔥 PyQt5 deprecation warning 억제
warnings.filterwarnings("ignore", message="sipPyTypeDict.*deprecated", category=DeprecationWarning)

# 타입 별칭 (모듈 전역): 선정 코인은 문자열 심볼 또는 메타정보 dict 모두 허용
SelectedCoin = Union[str, Mapping[str, Any]]

# 계정 정보 확인 및 설정
try:
    from path_utils import get_account_info_from_token, set_current_user_account, print_path_info

    # 🔥 1단계: 토큰 파일에서 사용자 ID 읽기
    user_id, token_path = get_account_info_from_token()

    if user_id:
        # 2단계: 사용자 계정 설정 (반드시 성공해야 함)
        set_current_user_account(user_id)
        logger = _get_loguru_logger()
        logger.info(f'기존 계정 정보 발견: {user_id}')
        logger.info(f'토큰 파일 경로: {token_path}')

        # 3단계: 경로 정보 확인 (디버깅)
        logger.info('경로 정보 확인 시작')
        print_path_info()

        # 4단계: 시간 동기화 확인 (바이낸스 API 요구사항)
        try:
            from utils.time_sync import ensure_time_sync
            logger.info('⏰ 시스템 시간 동기화 확인 중...')
            ensure_time_sync(max_retries=3)
        except Exception as e:
            logger.warning(f'시간 동기화 확인 중 오류 (계속 진행): {e}')

    else:
        logger = _get_loguru_logger()
        logger.info('기존 계정 정보 없음 - 로그인 필요')
        # 사용자 계정이 없어도 경로 정보는 확인
        logger.info('현재 경로 정보 확인')
        print_path_info()

except ImportError as e:
    logger = _get_loguru_logger()
    logger.error(f'path_utils 모듈을 찾을 수 없습니다: {e}')
    sys.exit(1)
except Exception as e:
    logger = _get_loguru_logger()
    logger.error(f'계정 정보 확인 중 오류: {e}')
    logger.error(traceback.format_exc())
    # 🔥 오류 발생 시에도 계속 진행 (로그인 화면으로)

# 지역/서드파티/로컬 모듈 임포트 (sys.path 보정 이후)
from ui.login_modern import LoginWindow
try:
    logger = _get_loguru_logger()
    logger.info(f'LoginWindow import 완료: {LoginWindow}')
    logger.info(f'LoginWindow.login_success 존재: {hasattr(LoginWindow, "login_success")}')
except Exception:
    pass

from ui.dashboard_modern import ModernDashboard
from api.backend_api import BackendAPI
from api.binance_client import BinanceClient, BinanceConfig
from trading.trader import Trader
from trading.analyzer import Analyzer
from trading.optimizer import Optimizer
from trading.evaluator import Evaluator
from trading.recorder import Recorder
from trading.ai.ai_manager import AIManager
from trading.ai.auto_optimizer import AIAutoOptimizer
from trading.market_state import MarketStateAnalyzer
from config.settings import load_settings, save_settings
from trading.risk_manager import RiskManager
from trading.unified_trader import UnifiedTrader
from trading.exchange_manager import ExchangeManager
from trading.unified_trading_manager import UnifiedTradingManager
from trading.federated_learning_preparation import FederatedLearningPreparationService
from utils.auto_update_manager import AutoUpdateManager

class NoahAIClient:
    """Noah AI 클라이언트 메인 클래스"""

    ALLOWED_USER_GRADES = {"normal", "pro", "premium"}


    def __init__(self):
        """초기화"""

        # 환경변수 설정
        os.environ['AUTO_COIN_SELECTION'] = 'true'

        # 경로 일관성 디버깅 (개발 시에만)
        if not getattr(sys, 'frozen', False):
            self.debug_path_consistency()

        # 로그 파일 초기화 (앱 시작 시)
        self.initialize_logs()

        # 테마 설정 파일만 초기화 (로그인 전에 필요한 최소한의 파일)
        self.initialize_theme_config()

        # 설정은 로그인 후에 로드 (사용자별 폴더 사용)
        # 설정은 항상 Dict로 취급 (Optional 경고 제거 및 호출부 안정화)
        self.settings: Dict[str, Any] = {}
        self.auto_update_manager: Optional[AutoUpdateManager] = None
        self.current_user_grade: str = "normal"

        # 🔥 로그인 성공 처리 플래그 초기화
        self._login_success_processed = False

        # 정적 분석기(Pylance) 지원: 속성 타입을 명시적으로 선언
        # 런타임에는 지연 초기화되므로 None으로 시작
        self.unified_trader: Optional[UnifiedTrader] = None
        self.fl_preparation_service: Optional[FederatedLearningPreparationService] = None

        # 선택된 코인 목록 초기화
        self.selected_coins: List[Dict[str, Any]] = []

        # 로그인 전에는 설정 확인 생략
        logger = self._get_main_logger()
        logger.info('설정은 로그인 후에 로드됩니다.')

        # 로깅 설정
        self.setup_logging()

    def setup_logging(self):
        """앱 공통 로깅 초기화 (초기 부팅용 메인 로거).
        - 사용자 로그인/계정 설정 이전 단계에서도 동작해야 하므로, 경로 유효성은 안전하게 처리
        - settings.log_level, 환경변수, 기본값 순으로 레벨 결정
        - loguru 존재 시 loguru 우선 사용, 없으면 표준 logging + RotatingFileHandler 사용
        - 중복 핸들러 제거 및 서드파티 로거 노이즈 억제
        """
        try:
            # 1) 로그 레벨 결정
            lvl_str = None
            try:
                if isinstance(getattr(self, 'settings', None), dict):
                    lvl_str = (self.settings.get('log_level') or '').strip()
            except Exception:
                lvl_str = None
            lvl_str = (lvl_str or os.environ.get('NOAHAI_LOG_LEVEL') or 'INFO').upper()

            # 2) 로그 파일 경로 확보 (안전)
            log_path = None
            try:
                from path_utils import get_log_file_path
                log_path = get_log_file_path()
            except Exception:
                # 폴백: ./logs/noahai.log
                try:
                    base_dir = os.path.abspath(os.getcwd())
                    logs_dir = os.path.join(base_dir, 'logs')
                    os.makedirs(logs_dir, exist_ok=True)
                    log_path = os.path.join(logs_dir, 'noahai.log')
                except Exception:
                    # 최후 폴백: 현재 디렉토리
                    log_path = os.path.abspath('noahai.log')

            # 3) loguru 우선
            if _loguru_logger is not None:
                logger = _loguru_logger
                try:
                    # 중복 방지: 기존 핸들러 모두 제거
                    logger.remove()
                except Exception:
                    pass

                # 콘솔 핸들러는 log_adapter가 담당 → 중복 출력 방지 위해 추가하지 않음

                # 파일 핸들러
                try:
                    logger.add(
                        log_path,
                        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} - {message}",
                        level=lvl_str,
                        rotation="200 MB",
                        retention="30 days",
                        encoding="utf-8"
                    )
                except Exception as e:
                    # 구성 중 경고는 래퍼를 통해 기록하되 변수 재정의로 인한 타입 혼동을 피한다
                    self._get_main_logger().warning(f'파일 로거 추가 실패(무시 가능): {e}')

                # 실제 표준 로거 보관 (UnifiedLogger가 참조)
                self._root_std_logger = logger
                self.logger = logger
            else:
                # 4) 표준 logging
                logger = _get_fallback_logger("NoahAI")
                # 기존 핸들러 제거 후 재설정(중복 방지)
                try:
                    for h in list(logger.handlers):
                        logger.removeHandler(h)
                except Exception:
                    pass

                # 콘솔 핸들러는 log_adapter가 담당 → 중복 출력 방지 위해 추가하지 않음

                # 파일 핸들러
                try:
                    file_handler = RotatingFileHandler(
                        log_path,
                        maxBytes=200 * 1024 * 1024,
                        backupCount=30,
                        encoding='utf-8'
                    )
                    file_handler.setFormatter(logging.Formatter("[%(asctime)s] | %(levelname)s | %(message)s"))
                    logger.addHandler(file_handler)
                except Exception as e:
                    self._get_main_logger().warning(f'파일 핸들러 설정 실패(무지 가능): {e}')

                # 레벨 설정 및 실제 표준 로거 보관 (UnifiedLogger가 참조)
                try:
                    logger.setLevel(getattr(logging, lvl_str, logging.INFO))
                except Exception:
                    logger.setLevel(logging.INFO)
                self._root_std_logger = logger
                self.logger = logger

            # 5) 서드파티 로거 소음 억제
            try:
                logging.getLogger("urllib3").setLevel(logging.WARNING)
                logging.getLogger("websockets").setLevel(logging.WARNING)
                logging.getLogger("asyncio").setLevel(logging.WARNING)
            except Exception:
                pass

            # 6) 초기 로그 한 줄
            try:
                logger = self._get_main_logger()
                if logger:
                    logger.info(f"로그 초기화 완료 — level={lvl_str}, file={log_path}")
            except Exception:
                pass

        except Exception as e:
            # 절대 크래시하지 않도록 방어
            logger = self._get_main_logger(); logger.warning(f'setup_logging 실패: {e}')

    def debug_path_consistency(self):
        """경로 일관성 디버깅"""
        try:
            from path_utils import print_path_info, get_current_user_account

            logger = self._get_main_logger()
            logger.info('경로 일관성 디버깅 시작')
            logger.info(f'현재 사용자 계정: {get_current_user_account()}')
            # 경로 정보는 앱 시작 시 한 번만 출력 (중복 방지)

            # 실제 파일 존재 여부 확인
            from path_utils import get_config_dir, get_app_data_dir
            config_dir = get_config_dir()
            data_dir = get_app_data_dir()

            logger = self._get_main_logger(); logger.info('실제 파일 존재 여부 확인')
            logger.info(f'설정 디렉토리: {config_dir} (존재: {os.path.exists(config_dir)})')
            logger.info(f'데이터 디렉토리: {data_dir} (존재: {os.path.exists(data_dir)})')

            settings_file = os.path.join(config_dir, 'settings.json')
            logger.info(f'설정 파일: {settings_file} (존재: {os.path.exists(settings_file)})')

            token_file = os.path.join(data_dir, 'token.json')
            logger.info(f'토큰 파일: {token_file} (존재: {os.path.exists(token_file)})')

        except Exception as e:
            logger = self._get_main_logger(); logger.error(f'경로 일관성 디버깅 오류: {e}')

    def initialize_logs(self):
        """로그 파일 초기화 (앱 시작 시)"""
        try:
            from path_utils import get_log_file_path, get_app_data_dir
            import os

            # 로그 파일 경로 가져오기
            log_file_path = get_log_file_path()

            # 🔥 로그 파일 크기 확인 후 조건부 초기화
            if os.path.exists(log_file_path):
                file_size = os.path.getsize(log_file_path)
                max_size = 50 * 1024 * 1024  # 50MB

                if file_size > max_size:
                    with open(log_file_path, 'w', encoding='utf-8') as f:
                        f.write('')
                    logger = self._get_main_logger(); logger.info(f'로그 파일 초기화 (크기 초과: {file_size/1024/1024:.1f}MB): {os.path.basename(log_file_path)}')
                else:
                    logger = self._get_main_logger(); logger.info(f'로그 파일 유지 (크기: {file_size/1024/1024:.1f}MB): {os.path.basename(log_file_path)}')

            # 🔥 로그 디렉토리의 오래된 로그 파일들 조건부 삭제
            logs_dir = os.path.join(get_app_data_dir(), 'logs')
            if os.path.exists(logs_dir):
                for filename in os.listdir(logs_dir):
                    if filename.endswith('.log') and filename != 'trading.log':
                        old_file = os.path.join(logs_dir, filename)
                        try:
                            # 파일 크기 확인
                            file_size = os.path.getsize(old_file)
                            max_size = 10 * 1024 * 1024  # 10MB

                            if file_size > max_size:
                                os.remove(old_file)
                                logger = self._get_main_logger(); logger.info(f'오래된 로그 파일 삭제 (크기 초과: {file_size/1024/1024:.1f}MB): {filename}')
                            else:
                                logger = self._get_main_logger(); logger.info(f'로그 파일 유지 (크기: {file_size/1024/1024:.1f}MB): {filename}')
                        except Exception as e:
                            logger = self._get_main_logger(); logger.warning(f'로그 파일 처리 실패 {filename}: {e}')

        except Exception as e:
            logger = self._get_main_logger(); logger.warning(f'로그 초기화 실패: {e}')

    def initialize_theme_config(self):
        """테마 시스템 제거됨: 더 이상 아무 작업도 수행하지 않음."""
        # 과거 테마 관련 설정은 완전히 제거되었습니다. (로그도 출력하지 않음)
        return

    def setup_user_account(self, user_info):
        """사용자 계정 설정 및 실제 사용 파일들 생성"""
        try:
            from path_utils import set_current_user_account, get_app_data_dir, get_config_dir, get_log_dir

            # 디버깅: user_info 내용 확인 (민감정보 마스킹)
            safe_info = dict(user_info)
            if 'access_token' in safe_info and isinstance(safe_info['access_token'], str):
                t = safe_info['access_token']
                safe_info['access_token'] = f"{t[:4]}...{t[-4:]}" if len(t) > 8 else "***"
            logger = self._get_main_logger(); logger.debug(f'user_info 내용: {safe_info}')

            # 사용자 계정 설정 (여러 가능한 키 확인)
            username = (user_info.get('username') or
                        user_info.get('user_id') or
                        user_info.get('id') or
                        user_info.get('user') or
                        'unknown')

            # user_info에 username 필드 추가 (다른 모듈에서 사용)
            user_info['username'] = username
            user_info['user_grade'] = self._normalize_user_grade(user_info.get('user_grade', 'normal'))
            self.current_user_grade = user_info['user_grade']

            set_current_user_account(username)
            logger = self._get_main_logger(); logger.info(f'사용자 계정 설정: {username}')

            # 이제 설정 로드 (사용자별 폴더 사용)
            from config.settings import load_settings
            self.settings = load_settings()
            changed = self._apply_membership_feature_limits(self.current_user_grade)
            if changed:
                try:
                    save_settings(self.settings)
                except Exception as e:
                    logger = self._get_main_logger(); logger.warning(f"회원등급 제한 저장 실패(계속 진행): {e}")
            logger = self._get_main_logger(); logger.info('사용자별 설정 로드 완료')
            self._initialize_auto_update_manager()

            # 계정별 폴더 생성
            account_dir = get_app_data_dir()
            logger = self._get_main_logger(); logger.info(f'계정별 데이터 폴더: {account_dir}')

            # token.json과 credentials.json을 사용자 폴더에 직접 생성
            # access_token은 user_info에 없으므로 별도로 전달
            access_token = user_info.get('access_token', '')
            if not access_token:
                # user_info에 access_token이 없으면 로그인 응답에서 가져오기
                # 이 부분은 로그인 성공 후 호출되므로 access_token이 있어야 함
                logger = self._get_main_logger(); logger.warning(f'access_token이 user_info에 없습니다: {user_info}')
            self.create_user_files_in_account_folder(username, user_info, access_token)

            # 실제 사용되는 모든 파일들 생성
            logger = self._get_main_logger(); logger.info('파일 초기화 시작...')
            self.initialize_user_files(username)
            logger = self._get_main_logger(); logger.info('파일 초기화 완료')

        except Exception as e:
            logger = self._get_main_logger(); logger.error(f'사용자 계정 설정 실패: {e}')
            try:
                import traceback
                logger = self._get_main_logger()
                logger.error(traceback.format_exc())
            except Exception:
                pass

    def _normalize_user_grade(self, raw_grade: Any) -> str:
        grade = str(raw_grade or "").strip().lower()
        alias_map = {
            "general": "normal",
            "basic": "normal",
            "coin_start": "normal",
            "coin-start": "normal",
            "alltrading": "pro",
            "all_trading": "pro",
            "all-trading": "pro",
            "middle": "pro",
            "signature": "premium",
            "signature_federated": "premium",
        }
        grade = alias_map.get(grade, grade)
        if grade not in self.ALLOWED_USER_GRADES:
            return "normal"
        return grade

    def _apply_membership_feature_limits(self, user_grade: Any) -> bool:
        """회원등급에 따라 런타임 기능 제한을 강제한다."""
        grade = self._normalize_user_grade(user_grade)
        self.current_user_grade = grade
        if not isinstance(self.settings, dict):
            return False

        changed = False

        # 공통 컨테이너 보장
        if not isinstance(self.settings.get('stock_broker_configs'), dict):
            self.settings['stock_broker_configs'] = {}
            changed = True
        if not isinstance(self.settings.get('stock_auto_trading'), dict):
            self.settings['stock_auto_trading'] = {}
            changed = True
        if not isinstance(self.settings.get('federated_learning'), dict):
            self.settings['federated_learning'] = {}
            changed = True
        if not isinstance(self.settings.get('saas_preparation'), dict):
            self.settings['saas_preparation'] = {}
            changed = True

        stock_broker_configs = self.settings.get('stock_broker_configs', {})
        stock_auto_trading = self.settings.get('stock_auto_trading', {})
        federated_learning = self.settings.get('federated_learning', {})
        saas_prep = self.settings.get('saas_preparation', {})

        if grade == 'normal':
            if self.settings.get('enabled_stock_brokers') != []:
                self.settings['enabled_stock_brokers'] = []
                changed = True
            if bool(self.settings.get('enable_stock_live_order', False)):
                self.settings['enable_stock_live_order'] = False
                changed = True

            for broker_key, broker_cfg in stock_broker_configs.items():
                if isinstance(broker_cfg, dict):
                    if bool(broker_cfg.get('enabled', False)):
                        broker_cfg['enabled'] = False
                        changed = True
                    if bool(broker_cfg.get('allow_live_order', False)):
                        broker_cfg['allow_live_order'] = False
                        changed = True
                    stock_broker_configs[broker_key] = broker_cfg

            if bool(stock_auto_trading.get('enabled', False)):
                stock_auto_trading['enabled'] = False
                changed = True
            if bool(stock_auto_trading.get('auto_start', False)):
                stock_auto_trading['auto_start'] = False
                changed = True

        if grade in {'normal', 'pro'}:
            for key in ('enabled', 'batch_enabled', 'upload_enabled'):
                if bool(federated_learning.get(key, False)):
                    federated_learning[key] = False
                    changed = True

        target_tier = 'starter' if grade == 'normal' else 'plus' if grade == 'pro' else 'pro'
        if str(saas_prep.get('subscription_tier', '') or '') != target_tier:
            saas_prep['subscription_tier'] = target_tier
            changed = True

        self.settings['stock_broker_configs'] = stock_broker_configs
        self.settings['stock_auto_trading'] = stock_auto_trading
        self.settings['federated_learning'] = federated_learning
        self.settings['saas_preparation'] = saas_prep

        if changed:
            logger = self._get_main_logger()
            if logger:
                logger.info(f"회원등급 기능 제한 적용: {grade}")
        return changed

    def create_user_files_in_account_folder(self, username, user_info, access_token=None):
        """token.json을 사용자 폴더에 생성 (credentials.json은 login_modern.py에서 처리)"""
        try:
            from path_utils import get_app_data_dir, get_app_base_dir, set_current_user_account
            import json

            # 사용자 계정 설정
            set_current_user_account(username)

            # 사용자 계정 폴더 - path_utils 사용
            from path_utils import get_app_data_dir
            account_dir = get_app_data_dir()
            os.makedirs(account_dir, exist_ok=True)

            # 1. token.json 생성 (사용자 폴더에)
            token_data = {
                "access_token": access_token or user_info.get('access_token', ''),
                "user_info": user_info,
                "saved_at": user_info.get('saved_at', '')
            }
            token_path = os.path.join(account_dir, 'token.json')
            with open(token_path, 'w', encoding='utf-8') as f:
                json.dump(token_data, f, ensure_ascii=False, indent=2)
            logger = self._get_main_logger(); logger.info(f'token.json 생성 완료: {token_path}')

            # 2. 기본 경로의 파일들 정리 (있다면 삭제) - data/ 폴더의 파일만 정리
            # path_utils 사용하여 기본 디렉토리 생성
            from path_utils import get_app_base_dir
            base_data_dir = os.path.join(get_app_base_dir(), 'data')
            for filename in ['token.json']:  # credentials.json은 login_modern.py에서 처리
                old_path = os.path.join(base_data_dir, filename)
                if os.path.exists(old_path):
                    os.remove(old_path)
                    logger = self._get_main_logger(); logger.info(f'기존 파일 정리: {old_path}')


        except Exception as e:
            logger = self._get_main_logger(); logger.error(f'사용자 파일 생성 실패: {e}')
            try:
                import traceback
                logger = self._get_main_logger()
                logger.error(traceback.format_exc())
            except Exception:
                pass

    def initialize_user_files(self, username):
        """사용자별 필수 파일들 초기화"""
        try:
            from path_utils import get_app_data_dir, get_log_dir

            # 사용자 계정 설정
            from path_utils import set_current_user_account
            set_current_user_account(username)

            # 데이터 및 로그 디렉토리 생성
            user_data_path = get_app_data_dir()
            user_log_path = get_log_dir()

            import os
            os.makedirs(user_data_path, exist_ok=True)
            os.makedirs(user_log_path, exist_ok=True)

            logger = self._get_main_logger()
            if logger:
                logger.info(f"사용자 파일 초기화 완료: {username}")
                logger.info(f"데이터 경로: {user_data_path}")
                logger.info(f"로그 경로: {user_log_path}")

        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                logger.error(f"사용자 파일 초기화 오류: {e}")

    def setup_user_logging(self):
        """사용자 계정 설정 후 로그 경로 재설정 (거래소별 로그 파일 분리)"""
        try:
            from path_utils import get_exchange_log_file_path
            log_level = self.settings.get('log_level', 'INFO') if self.settings else 'INFO'

            # 거래소 목록 추출: enabled_exchanges 우선, 없으면 selected_exchange 폴백
            exchanges = []
            if isinstance(self.settings, dict):
                raw_enabled = self.settings.get('enabled_exchanges', []) or []
                for ex in raw_enabled:
                    ex_name = str(ex).strip().lower()
                    if ex_name:
                        exchanges.append(ex_name)

                if not exchanges:
                    selected = str(self.settings.get('selected_exchange', 'binance')).strip().lower()
                    if selected:
                        exchanges.append(selected)

            if not exchanges:
                exchanges = ['binance']

            # 순서 유지 + 중복 제거
            exchanges = list(dict.fromkeys(exchanges))

            self.exchange_loggers = {}

            if _loguru_logger is not None:
                # 모든 기존 핸들러 제거는 루프 바깥에서 1회만 수행
                try:
                    _loguru_logger.remove()
                except Exception:
                    pass

            for exchange_name in exchanges:
                if _loguru_logger is not None:
                    # 콘솔 추가는 하지 않음 — 터미널 중복 방지
                    log_path = get_exchange_log_file_path(exchange_name)
                    # 거래소별 파일에는 해당 거래소 로그만 기록되도록 필터 적용
                    _loguru_logger.add(
                        log_path,
                        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} - {message}",
                        level=log_level,
                        rotation="200 MB",
                        retention="30 days",
                        encoding="utf-8",
                        filter=(lambda record, ex=exchange_name: f"(ex={ex})" in str(record.get("message", "")))
                    )
                    logger = _loguru_logger
                else:
                    logger = _get_fallback_logger(f"NoahAI.{exchange_name}")
                    for handler in list(logger.handlers):
                        logger.removeHandler(handler)
                    # 콘솔 핸들러 추가하지 않음 — 터미널 중복 방지
                    log_path = get_exchange_log_file_path(exchange_name)
                    file_handler = RotatingFileHandler(
                        log_path,
                        maxBytes=200 * 1024 * 1024,
                        backupCount=30,
                        encoding='utf-8'
                    )
                    file_handler.setFormatter(logging.Formatter("[%(asctime)s] | %(levelname)s | %(message)s"))
                    try:
                        # 표준 로깅에도 거래소별 메시지 라우팅을 위한 필터 추가
                        class _ExchangeFilter(logging.Filter):
                            def __init__(self, ex: str):
                                super().__init__()
                                self.ex = ex
                            def filter(self, record: logging.LogRecord) -> bool:
                                msg = str(getattr(record, 'msg', ''))
                                return f"(ex={self.ex})" in msg
                        file_handler.addFilter(_ExchangeFilter(exchange_name))
                    except Exception:
                        pass
                    logger.addHandler(file_handler)
                    logger.setLevel(getattr(logging, str(log_level).upper(), logging.INFO))
                self.exchange_loggers[exchange_name] = logger

            # 기존 self.logger는 실제 표준 로거를 유지하여 하위 모듈에 전달

        except Exception as e:
            logger = self._get_main_logger(); logger.error(f'거래소별 로깅 설정 오류: {e}')
            try:
                import traceback
                logger = self._get_main_logger()
                logger.error(traceback.format_exc())
            except Exception:
                pass

    def _analyze_market_regime(self):
        """시장 상황 분석"""
        try:
            # 기본 시장 상황 분석 (향후 AI로 개선 가능)
            return "normal"  # normal, bullish, bearish, volatile
        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                logger.error(f"시장 상황 분석 오류: {e}")
            return "normal"

    def _create_fallback_plan(self, candidates):
        """Optimizer 실패 시 폴백 계획 생성"""
        try:
            fallback_params = {}
            for candidate in candidates:
                symbol = candidate.get('symbol', 'UNKNOWN')
                fallback_params[symbol] = {
                    'qty': 0.001,  # 최소 수량
                    'price': candidate.get('price', 0),
                    'side': candidate.get('side', 'BUY')
                }
            return fallback_params
        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                logger.error(f"폴백 계획 생성 오류: {e}")
            return {}

    def _get_main_logger(self):
        class UnifiedLogger:
            def __init__(self, parent):
                self.parent = parent

            def _std(self):
                # 항상 실제 표준 로거를 참조하여 래퍼 재귀 방지
                return getattr(self.parent, '_root_std_logger', None)

            def info(self, msg):
                std = self._std()
                # 단일 경로로 기록: log_event가 스트림(+표준 로거) 모두 처리
                try:
                    log_event('system', str(msg), level='INFO', logger=std)
                except Exception:
                    pass

            def warning(self, msg):
                std = self._std()
                try:
                    log_event('system', str(msg), level='WARNING', logger=std)
                except Exception:
                    pass

            def debug(self, msg):
                std = self._std()
                try:
                    log_event('system', str(msg), level='DEBUG', logger=std)
                except Exception:
                    pass

            def error(self, msg):
                std = self._std()
                try:
                    log_event('system', str(msg), level='ERROR', logger=std)
                except Exception:
                    pass

            def critical(self, msg):
                std = self._std()
                try:
                    log_event('system', str(msg), level='CRITICAL', logger=std)
                except Exception:
                    pass

            def exception(self, msg):
                # 실시간 + 표준 로거에 traceback 포함: log_event로 파일/스트림 기록, 표준 로거의 exception은 log_event 내부에서 처리하지 않으므로 메시지 기록만 수행
                std = self._std()
                try:
                    log_event('system', str(msg), level='ERROR', logger=std)
                except Exception:
                    pass

        if not hasattr(self, '_unified_logger'):
            self._unified_logger = UnifiedLogger(self)
        return self._unified_logger

    def start(self):
        """애플리케이션 시작 (CustomTkinter 방식)"""
        try:
            # 🔥 재시작 방지 체크 및 플래그 초기화
            global _SHUTDOWN_IN_PROGRESS
            if _SHUTDOWN_IN_PROGRESS:
                logger = self._get_main_logger()
                if logger:
                    if logger is not None:
                        logger.info("프로그램 종료 중 - 재시작 방지")
                return

            # 프로그램 시작 시 플래그 초기화
            _SHUTDOWN_IN_PROGRESS = False

            # atexit 핸들러 등록 (프로그램 시작 후)
            atexit.register(_graceful_shutdown)

            # Windows UI 일관성을 위한 CustomTkinter 전역 초기화
            try:
                import customtkinter as ctk
                # ✅ CustomTkinter 5.1.3으로 다운그레이드 완료!
                # 이 버전은 dark 모드에서도 corner_radius가 정상 작동합니다
                ctk.set_appearance_mode("dark")
                try:
                    print("[UI] CTk 5.1.3 - appearance_mode=dark, corner_radius 정상 작동")
                except Exception:
                    pass
                # 고해상도(HiDPI) 환경에서 위젯/윈도우 스케일을 통일
                if hasattr(ctk, 'set_widget_scaling'):
                    ctk.set_widget_scaling(1.0)
                if hasattr(ctk, 'set_window_scaling'):
                    ctk.set_window_scaling(1.0)
            except Exception as _e:
                logger = self._get_main_logger()
                if logger:
                    if logger is not None:
                        logger.warning(f"CustomTkinter 초기화 실패(무시 가능): {_e}")

            # Noah AI Client 시작 (INFO 레벨)
            # 개발 편의: 환경변수로 로그인 건너뛰기 허용
            try:
                skip_login = str(os.environ.get('NOAHAI_SKIP_LOGIN', '')).lower() in ('1', 'true', 'yes')
            except Exception:
                skip_login = False

            if skip_login:
                logger = self._get_main_logger()
                logger.warning("개발 모드: 로그인 건너뛰기 활성화 (NOAHAI_SKIP_LOGIN)")
                # 최소 사용자 정보로 바로 진행
                user_info = {
                    'id': os.environ.get('NOAHAI_DEV_USER', 'dev'),
                    'email': 'dev@local',
                    'session_id': 'dev-session',
                    'token_type': 'Bearer'
                }
                self.on_login_success('dev-skip-login-token', user_info)
            else:
                self.show_login()
        # CustomTkinter는 별도 exec_() 불필요
        except Exception as e:
            logger = self._get_main_logger()
            logger.error(f"애플리케이션 시작 오류: {e}")
            sys.exit(1)

    def cleanup_and_exit(self):
        """안전한 종료"""
        try:
            logger = self._get_main_logger()
            if logger:
                if logger is not None:
                    logger.warning("프로그램 안전 종료 시작...")

            # 트레이딩 중지 (Optional 가드) - stop() 메서드 사용
            tw = getattr(self, 'trading_worker', None)
            if tw and hasattr(tw, 'stop'):
                try:
                    tw.stop()  # 🔥 중복 제거: stop_trading() → stop() 통합
                except Exception as e:
                    logger = self._get_main_logger()
                    if logger:
                        if logger is not None:
                            logger.warning(f"trading_worker.stop() 실패: {e}")

            # 메모리 정리
            import gc
            gc.collect()

            # 로그 정리
            logger2 = self._get_main_logger()
            if logger2:
                if logger2 is not None:
                    logger2.info("프로그램 정상 종료")
                if logger2 is not None:
                    logger2.warning("안전 종료 완료")
        except Exception as e:
            logger = self._get_main_logger(); logger.error(f'종료 중 오류: {e}')
        finally:
            os._exit(0)

    def show_login(self):
        """로그인 창 표시"""
        try:
            self.login_window = LoginWindow()
            self.login_window.connect_login_success(self.on_login_success)
            print("main.py: login_success 콜백 연결 완료")
            self.login_window.run()
        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                if logger is not None:
                    logger.error(f"로그인 창 표시 오류: {e}")

    def on_login_success(self, token, user_info):
        """로그인 성공 처리 - 백엔드 승인 후 계정별 폴더 생성"""
        # 중복 호출 방지 가드
        if getattr(self, '_login_success_processed', False):
            logger = self._get_main_logger()
            if logger:
                logger.debug("로그인 성공 처리가 이미 진행 중이므로 건너뜁니다.")
            return

        self._login_success_processed = True

        try:
            print("main.py: on_login_success 진입")
            logger = self._get_main_logger()
            if logger:
                if logger is not None:
                    logger.info("로그인 성공, 백엔드 승인 완료")
                    logger.info("on_login_success: 초기화 시작")

            # user_info에 access_token 추가 (마스킹된 로그)
            user_info['access_token'] = token
            masked_token = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else "***"
            logger = self._get_main_logger(); logger.debug(f'user_info에 access_token 추가: {masked_token}')

            # 백엔드 승인 후 사용자 계정 설정 및 계정별 폴더 생성
            self.setup_user_account(user_info)

            # 사용자 계정 설정 후 로그 경로 재설정
            self.setup_user_logging()

            # 로그인창 닫기 (안전 종료)
            if hasattr(self, 'login_window') and self.login_window:
                try:
                    root = self.login_window.root
                    if root and root.winfo_exists():
                        # 1) 예약된 after 들을 전부 수집 → 개별 취소
                        try:
                            tk = root.tk
                            # 모든 after 식별자 나열
                            pending = tk.call('after', 'info')
                            # Tk가 문자열 한 덩어리로 줄 수 있어 splitlist 필요
                            try:
                                after_ids = tk.splitlist(pending)
                            except Exception:
                                after_ids = pending if isinstance(pending, (list, tuple)) else []
                            # 디버깅: 몇 개 지우는지 확인하고 싶으면 다음 줄 주석 해제
                            for aid in after_ids:
                                try:
                                    tk.call('after', 'cancel', aid)
                                except Exception:
                                    pass
                        except Exception as e:
                            # 취소 실패는 무시해도 됨 (일부 환경에서 info가 빈 리스트일 수 있음)
                            # self.logger.debug(f"after 취소 스킵: {e}")
                            pass

                        # 2) 창 숨김 → 루프 중단 → 파괴 (순서 매우 중요)
                        try:
                            root.withdraw()
                            root.update_idletasks()  # 대기 큐 비우기
                            root.quit()
                        except Exception:
                            pass
                        try:
                            root.destroy()
                        except Exception:
                            pass

                        logger = self._get_main_logger(); logger.info('로그인창 안전 종료 완료')
                    else:
                        logger = self._get_main_logger(); logger.info('로그인창 이미 닫힘')
                except Exception as e:
                    logger = self._get_main_logger(); logger.warning(f'로그인창 닫기 실패: {e}')

            # 백엔드 API 초기화
            self.backend_api = BackendAPI(token)

            # 사용자 정보 설정 (token.json에서 불러온 user_info 사용)
            user_id = user_info.get('id', 'Unknown')
            user_grade = self._normalize_user_grade(user_info.get('user_grade', 'normal'))
            user_email = user_info.get('email', '')
            user_info['user_grade'] = user_grade
            self.current_user_grade = user_grade

            # 🔥 사용자별 DB 경로 설정 (Recorder 초기화 전에 반드시 설정)
            from path_utils import set_current_user_account
            set_current_user_account(user_id)
            logger = self._get_main_logger(); logger.info(f'사용자 계정 설정 완료: {user_id}')

            self.backend_api.set_user_info(user_id, user_grade, user_email)
            logger = self._get_main_logger(); logger.info(f'사용자 정보 설정: {user_id} ({user_grade}) - {user_email}')

            # API 키 필수 검증 (OpenAI은 필수, 거래소 키는 선택: 있으면 사용)
            selected_exchange = self.settings.get('selected_exchange', 'binance')
            openai_api_key = self.settings.get('openai_api_key', '').strip()

            # OpenAI API 키 검증 (필수: 없으면 설정 창으로 유도)
            try:
                _masked = (openai_api_key[:4] + "***" + openai_api_key[-4:]) if openai_api_key else "<EMPTY>"
                _len = len(openai_api_key) if openai_api_key else 0
                logger = self._get_main_logger(); logger.info(f"OpenAI API Key 상태: len={_len}, masked={_masked}")
            except Exception as _e:
                try:
                    import traceback as _tb
                    _lg = self._get_main_logger(); _lg.error(f"OpenAI 키 상태 로그 중 예외: {_e}")
                    _lg.error(_tb.format_exc())
                except Exception:
                    pass
            if not openai_api_key:
                logger = self._get_main_logger()
                if logger:
                    if logger is not None:
                        logger.info("OpenAI API 키가 설정되지 않음 - 설정 화면 표시")
                self.show_api_setup_dialog()
                return

            # 하나 이상의 거래소 API 키가 있는지 비차단 확인 (없어도 진행)
            def _has_any_exchange_keys(s):
                pairs = [
                    (s.get('binance_api_key', ''), s.get('binance_secret_key', '')),
                    (s.get('upbit_api_key', ''), s.get('upbit_secret_key', '')),
                    (s.get('bithumb_api_key', ''), s.get('bithumb_secret_key', '')),
                    (s.get('bybit_api_key', ''), s.get('bybit_secret_key', '')),
                    (s.get('okx_api_key', ''), s.get('okx_secret_key', '')),
                    (s.get('bitget_api_key', ''), s.get('bitget_secret_key', '')),
                ]
                for k, sec in pairs:
                    if str(k).strip() and str(sec).strip():
                        return True
                return False

            if not _has_any_exchange_keys(self.settings):
                # 거래소 키가 없어도 초기 진입을 허용하되, 안내 로그만 남김
                try:
                    logger = self._get_main_logger()
                    if logger:
                        if logger is not None:
                            logger.info("거래소 API 키가 없습니다. 대시보드에서 환경설정 → 거래소 탭에서 언제든 입력/활성화할 수 있습니다.")
                except Exception:
                    pass

            # 🔥 자격 검증 완료(필수: OpenAI) - 초기화 진입
            logger = self._get_main_logger()
            if logger:
                if logger is not None:
                    logger.info("자격 검증 완료(OpenAI), 초기화 시작")

            self.initialize_after_api_setup()

            # 대시보드 표시 (정상 흐름)
            try:
                # 로그인창 종료 후 즉시 대시보드 표시 (깜빡임 방지를 위해 약간의 지연)
                import time
                time.sleep(0.1)  # 100ms 대기로 깜빡임 방지
                self.show_dashboard()
            except Exception as _e2:
                try:
                    import traceback as _tb
                    _lg = self._get_main_logger(); _lg.error(f"show_dashboard 호출 실패: {_e2}")
                    _lg.error(_tb.format_exc())
                except Exception:
                    pass

        except Exception as e:
            print(f"❌ on_login_success 오류: {e}")
            import traceback
            print("❌ on_login_success 오류 상세:")
            print(traceback.format_exc())
            logger = self._get_main_logger()
            if logger:
                if logger is not None:
                    logger.error(f"로그인 성공 처리 오류: {e}")
                    import traceback as _tb
                    logger.error(_tb.format_exc())
            # QMessageBox.critical(None, "초기화 오류", f"시스템 초기화 중 오류가 발생했습니다:\n{str(e)}")
        finally:
            # 로그인 성공 처리 완료 후 가드 초기화
            self._login_success_processed = False

    def show_api_setup_dialog(self):
        """API 키 설정 다이얼로그 표시 (CustomTkinter 설정 창 사용)"""
        try:
            logger = self._get_main_logger(); logger.info('API 키 설정 창을 표시합니다...')
            logger = self._get_main_logger(); logger.warning('API 키를 입력하지 않으면 프로그램이 종료됩니다.')

            # CustomTkinter 설정 창 사용
            from ui.settings_modern import ModernSettingsWindow
            logger = self._get_main_logger(); logger.debug('ModernSettingsWindow import 완료')

            settings_window = ModernSettingsWindow(
                current_settings=self.settings,
                on_save_callback=self.on_settings_saved
            )
            logger = self._get_main_logger(); logger.debug('ModernSettingsWindow 인스턴스 생성 완료')

            # 설정 창을 모달로 실행하고 완료까지 대기
            logger = self._get_main_logger(); logger.info('설정 창 실행 중...')
            # CustomTkinter에서는 mainloop() 사용
            settings_window.root.mainloop()
            logger = self._get_main_logger(); logger.info('설정 창 실행 완료')

            # 설정 창이 닫힌 후 API 키 재검증
            logger = self._get_main_logger(); logger.info('설정 창 닫힘')
            self.verify_api_keys_after_setup()

        except Exception as e:
            logger = self._get_main_logger(); logger.error(f'API 설정 화면 표시 오류: {e}')
            try:
                import traceback
                logger = self._get_main_logger(); logger.error(traceback.format_exc())
            except Exception:
                pass

    def verify_api_keys_after_setup(self):
        """설정 후 API 키 재검증 (OpenAI 필수, 거래소 키는 선택)"""
        try:
            # 설정 다시 로드
            from config.settings import load_settings
            self.settings = load_settings()

            # OpenAI 키만 필수 검증
            openai_api_key = self.settings.get('openai_api_key', '').strip()
            if not openai_api_key:
                logger = self._get_main_logger(); logger.error('OpenAI API 키가 설정되지 않음 - 프로그램을 종료합니다.')
                logger = self._get_main_logger(); logger.info('환경설정에서 OpenAI 키를 입력한 후 다시 실행해주세요.')
                import sys
                sys.exit()
                return

            # 거래소 키는 비차단: 있으면 사용, 없으면 경고만 로그
            def _has_any_exchange_keys(s):
                pairs = [
                    (s.get('binance_api_key', ''), s.get('binance_secret_key', '')),
                    (s.get('upbit_api_key', ''), s.get('upbit_secret_key', '')),
                    (s.get('bithumb_api_key', ''), s.get('bithumb_secret_key', '')),
                    (s.get('bybit_api_key', ''), s.get('bybit_secret_key', '')),
                    (s.get('okx_api_key', ''), s.get('okx_secret_key', '')),
                    (s.get('bitget_api_key', ''), s.get('bitget_secret_key', '')),
                ]
                for k, sec in pairs:
                    if str(k).strip() and str(sec).strip():
                        return True
                return False

            if not _has_any_exchange_keys(self.settings):
                logger = self._get_main_logger(); logger.warning('거래소 API 키가 없어도 계속 진행합니다. 대시보드 설정에서 언제든 추가할 수 있습니다.')

            logger = self._get_main_logger(); logger.info('필수 키 확인 완료(OpenAI)). 초기화 진행')
            self.initialize_after_api_setup()

        except Exception:
            logger = self._get_main_logger()
            if logger:
                logger.exception("API 키 재검증 오류")

    def on_settings_saved(self, *args, **kwargs):
        """설정 저장 콜백: 설정 갱신 및 매니저/대시보드 재초기화"""
        try:
            # args 호환 처리: ('settings_saved', dict) 또는 (dict)
            if len(args) == 1 and isinstance(args[0], dict):
                new_settings = args[0]
            elif len(args) >= 2 and isinstance(args[1], dict):
                new_settings = args[1]
            else:
                new_settings = kwargs.get('new_settings') or {}

            if not isinstance(new_settings, dict):
                logger = self._get_main_logger()
                if logger:
                    if logger is not None:
                        logger.warning("설정 저장 콜백에 유효한 설정 딕셔너리가 전달되지 않음")
                return

            # Diff 계산(적용 전)
            try:
                from config.diff_engine import compute_settings_diff
                _merged = {**self.settings, **new_settings}
                diff_plan = compute_settings_diff(self.settings, _merged)
            except Exception:
                diff_plan = None

            # 메모리 설정 갱신 및 디스크 저장
            self.settings.update(new_settings)
            self._apply_membership_feature_limits(self.current_user_grade)
            if self.auto_update_manager is not None:
                self.auto_update_manager.update_settings(self.settings)
            try:
                from config.settings import save_settings
                save_settings(self.settings)
            except Exception as e:
                logger = self._get_main_logger()
                if logger:
                    if logger is not None:
                        logger.warning(f"설정 파일 저장 실패(계속 진행): {e}")

            logger = self._get_main_logger()
            if logger:
                if logger is not None:
                    logger.info("✅ 설정 저장됨 — 런타임 구성 갱신 시작")

            # 로그 레벨 등 로깅 설정이 바뀐 경우 즉시 재설정
            try:
                if 'log_level' in new_settings:
                    self.setup_logging()
                    logger = self._get_main_logger()
                    if logger:
                        if logger is not None:
                            logger.info(f"로깅 레벨 재설정: {self.settings.get('log_level')}")
            except Exception as _le:
                try:
                    logger = self._get_main_logger()
                    if logger:
                        if logger is not None:
                            logger.warning(f"로깅 재설정 경고: {_le}")
                except Exception:
                    pass

            # UnifiedTradingManager 재사용/재초기화 (변경사항이 있을 때만)
            if hasattr(self, 'unified_manager') and self.unified_manager:
                try:
                    # 🔥 거래/거래소/AI 설정이 변경된 경우에만 재초기화
                    if diff_plan and (diff_plan.get('trading_changed') or diff_plan.get('exchanges_changed') or diff_plan.get('ai_changed')):
                        logger = self._get_main_logger()
                        if logger:
                            logger.info("🔄 거래 설정 변경 감지 - UnifiedTradingManager 재초기화")
                        self.unified_manager.reload_settings(self.settings)
                    else:
                        # 변경사항이 없으면 설정만 업데이트 (빠름)
                        self.unified_manager.settings = self.settings
                        logger = self._get_main_logger()
                        if logger:
                            logger.debug("설정 업데이트 (재초기화 불필요)")
                except Exception as e:
                    logger = self._get_main_logger()
                    if logger:
                        if logger is not None:
                            logger.warning(f"UnifiedTradingManager 재초기화 실패: {e}")
                    from trading.unified_trading_manager import UnifiedTradingManager
                    self.unified_manager = UnifiedTradingManager(self.settings)
            else:
                from trading.unified_trading_manager import UnifiedTradingManager
                self.unified_manager = UnifiedTradingManager(self.settings)

            # AIManager 재설정 (AI 설정이 변경된 경우에만)
            try:
                if diff_plan and diff_plan.get('ai_changed'):
                    logger = self._get_main_logger()
                    if logger:
                        logger.info("🔄 AI 설정 변경 감지 - AIManager 재초기화")
                    from trading.ai.ai_manager import AIManager as _AIManager
                    api_key = str(self.settings.get('openai_api_key', '') or '')
                    model = str(self.settings.get('openai_model', '') or '')
                    self.ai_manager = _AIManager(api_key=api_key, model=model)
            except Exception as e:
                logger = self._get_main_logger()
                if logger:
                    if logger is not None:
                        logger.warning(f"AIManager 재설정 경고: {e}")

            # Binance 키 변경 시 python-binance 클라이언트 재생성 및 교체
            try:
                if diff_plan and ('binance_api_key' in diff_plan.get('changed_keys', set()) or 'binance_secret_key' in diff_plan.get('changed_keys', set())):
                    logger = self._get_main_logger()
                    if logger:
                        logger.info("🔄 바이낸스 API 키 변경 감지 - 클라이언트 재생성")
                    from api.binance_client import BinanceClient, BinanceConfig
                    new_api = str(self.settings.get('binance_api_key', '') or '')
                    new_sec = str(self.settings.get('binance_secret_key', '') or '')
                    cfg = BinanceConfig(api_key=new_api, secret_key=new_sec, testnet=False)
                    self.binance_client = BinanceClient(cfg)
                    # ExchangeManager에 주입 및 캐시 초기화
                    try:
                        if hasattr(self, 'exchange_manager') and self.exchange_manager:
                            setattr(self.exchange_manager, 'binance_client', self.binance_client)
                            if hasattr(self.exchange_manager, 'clear_cache'):
                                self.exchange_manager.clear_cache()
                            try:
                                invalid = getattr(self.exchange_manager, 'invalid_api_keys', set())
                                if 'binance' in invalid:
                                    invalid.discard('binance')
                            except Exception:
                                pass
                    except Exception as _be:
                        logger = self._get_main_logger()
                        if logger:
                            if logger is not None:
                                logger.warning(f"Binance 클라이언트 교체 경고: {_be}")
            except Exception as e:
                logger = self._get_main_logger()
                if logger:
                    if logger is not None:
                        logger.warning(f"Binance 키 변경 반영 경고: {e}")

            # ExchangeManager 설정 업데이트 및 UnifiedTradingManager 주입 (필요 시)
            if hasattr(self, 'exchange_manager') and self.exchange_manager:
                try:
                    if hasattr(self.exchange_manager, 'update_settings'):
                        if not diff_plan or diff_plan.get('exchanges_changed') or diff_plan.get('trading_changed'):
                            self.exchange_manager.update_settings(self.settings, unified_manager=self.unified_manager)
                    else:
                        from trading.exchange_manager import ExchangeManager
                        self.exchange_manager = ExchangeManager(self.settings, self.binance_client, unified_manager=self.unified_manager)
                except Exception as e:
                    if getattr(self, 'logger', None) is not None:
                        if self.logger:
                            self.logger.warning(f"ExchangeManager 재초기화 실패: {e}")
                    from trading.exchange_manager import ExchangeManager
                    self.exchange_manager = ExchangeManager(self.settings, self.binance_client, unified_manager=self.unified_manager)
            else:
                from trading.exchange_manager import ExchangeManager
                self.exchange_manager = ExchangeManager(self.settings, self.binance_client, unified_manager=self.unified_manager)

            # UnifiedTrader가 매니저 참조를 가진 경우 갱신
            if hasattr(self, 'unified_trader') and self.unified_trader:
                try:
                    self.unified_trader.exchange_manager = self.exchange_manager
                    self.unified_trader.unified_manager = self.unified_manager
                    # UnifiedTrader에 AIManager 주입 메서드가 있을 경우에만 시도
                    try:
                        if hasattr(self, 'ai_manager') and self.ai_manager:
                            setter = getattr(self.unified_trader, 'set_ai_manager', None)
                            if callable(setter):
                                setter(self.ai_manager)
                    except Exception:
                        pass
                    logger = self._get_main_logger()
                    if logger:
                        if logger is not None:
                            logger.info("UnifiedTrader 참조 갱신 완료")
                except Exception as e:
                    logger = self._get_main_logger()
                    if logger:
                        if logger is not None:
                            logger.warning(f"UnifiedTrader 참조 갱신 실패: {e}")

            # 테마 설정 처리 제거됨 (고정 스킨 사용)
            # 테마 관련 코드는 더 이상 필요하지 않음

            # 대시보드에 변경사항 반영
            if hasattr(self, 'dashboard') and self.dashboard:
                if hasattr(self.dashboard, 'refresh_after_settings_change'):
                    self.dashboard.refresh_after_settings_change(self.settings, self.exchange_manager, self.unified_manager)
                else:
                    # 최소한의 교체
                    self.dashboard.settings = self.settings
                    self.dashboard.exchange_manager = self.exchange_manager
                    if hasattr(self.dashboard, 'update_exchange_info'):
                        try:
                            self.dashboard.update_exchange_info()
                        except Exception:
                            pass

                # enabled_exchanges 변경 시 전역 상태 라벨/버튼 즉시 갱신
                try:
                    if diff_plan and diff_plan.get('enabled_exchanges_changed') and hasattr(self.dashboard, '_update_global_status_ui'):
                        self.dashboard.enabled_exchanges = self.settings.get('enabled_exchanges', ['binance'])
                        self.dashboard._update_global_status_ui()
                except Exception:
                    pass

                # AI 상태 배지 즉시 갱신 보강 (대시보드 측 로직 보완)
                try:
                    if hasattr(self.dashboard, 'update_ai_status_badges'):
                        self.dashboard.update_ai_status_badges()
                except Exception:
                    pass

                # 설정 저장 완료 토스트/스낵바(있는 경우) 표시
                try:
                    _toast = getattr(self.dashboard, 'show_toast', None)
                    if callable(_toast):
                        _toast("설정이 저장되었습니다.")
                    else:
                        _notify = getattr(self.dashboard, 'notify', None)
                        if callable(_notify):
                            _notify("설정이 저장되었습니다.")
                except Exception:
                    pass

                # 잔고 즉시 새로고침 시도 (캐시 무시)
                try:
                    if hasattr(self, 'exchange_manager') and self.exchange_manager:
                        self.exchange_manager.get_exchange_balance('binance', force_refresh=True)
                except Exception:
                    pass

            logger = self._get_main_logger()
            if logger:
                if logger is not None:
                    logger.info("✅ 설정 변경이 런타임에 반영되었습니다")
        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                if logger is not None:
                    logger.error(f"설정 저장 처리 오류: {e}")

    def initialize_after_api_setup(self):
        """API 키 설정 후 초기화"""
        try:
            # settings.json에서 API 키 로드
            binance_api_key = self.settings.get('binance_api_key', '')
            binance_secret_key = self.settings.get('binance_secret_key', '')

            # 바이낸스 클라이언트 초기화 (하위 호환성 유지)
            try:
                binance_config = BinanceConfig(
                    api_key=binance_api_key,
                    secret_key=binance_secret_key,
                    testnet=False # 실제 거래소 사용
                )
                self.binance_client = BinanceClient(binance_config)
                logger = self._get_main_logger()
                if logger:
                    logger.info("✅ BinanceClient 초기화 완료")
            except Exception as e:
                logger = self._get_main_logger()
                if logger:
                    logger.error(f"❌ BinanceClient 초기화 실패: {e}")
                # BinanceClient 초기화 실패해도 계속 진행 (WebSocket 없이도 작동 가능)
                self.binance_client = None

            # 🔥 거래소 관리자 초기화 (새로운 모듈화 시스템)
            try:
                from trading.exchange_manager import ExchangeManager
                from trading.unified_trading_manager import UnifiedTradingManager
                from trading.unified_trader import UnifiedTrader
                from trading.api_signal_manager import APISignalManager

                # 먼저 UnifiedTradingManager 생성 후 ExchangeManager에 주입하여 중복 생성을 방지
                self.unified_manager = UnifiedTradingManager(self.settings)
                self.exchange_manager = ExchangeManager(self.settings, self.binance_client, unified_manager=self.unified_manager)

                # API 신호 관리자 초기화
                self.api_signal_manager = APISignalManager(self.exchange_manager, self.settings)
                self.api_signal_manager.start_signal_collection()
                logger = self._get_main_logger()
                if logger:
                    if logger is not None:
                        logger.info("✅ 거래소 관리자 및 API 신호 관리자 초기화 완료")
            except Exception as e:
                logger = self._get_main_logger()
                if logger:
                    if logger is not None:
                        logger.error(f"❌ 거래소 관리자 초기화 실패: {e}")
                self.exchange_manager = None
                self.unified_manager = None
                self.api_signal_manager = None

            # 트레이딩 컴포넌트 초기화
            self.initialize_trading_components()

            logger = self._get_main_logger()
            if logger:
                if logger is not None:
                    logger.info("API 키 설정 후 초기화 완료")
        except Exception as e:
            print(f"❌ initialize_after_api_setup 오류: {e}")
            import traceback
            print("❌ initialize_after_api_setup 오류 상세:")
            print(traceback.format_exc())
            logger = self._get_main_logger()
            if logger:
                if logger is not None:
                    logger.error(f"API 키 설정 후 초기화 오류: {e}")
                    import traceback as _tb
                    logger.error(_tb.format_exc())
            # QMessageBox.critical(None, "초기화 오류", f"시스템 초기화 중 오류가 발생했습니다:\n{str(e)}")

    def initialize_trading_components(self):
        """트레이딩 컴포넌트 초기화"""
        try:
            logger = self._get_main_logger()
            if logger:
                if logger is not None:
                    logger.info("트레이딩 컴포넌트 초기화 시작")
            
            # 🔥 빌드 환경 대응: 설정 파일을 다시 로드하여 최신 설정 보장
            # (사용자 계정이 설정된 후 올바른 경로에서 로드)
            try:
                from config.settings import load_settings
                from path_utils import get_current_user_account
                current_user = get_current_user_account()
                if current_user:
                    # 사용자 계정이 설정되어 있으면 설정 파일 다시 로드
                    reloaded_settings = load_settings()
                    if reloaded_settings:
                        # 기존 설정과 병합 (API 키 등은 새로 로드한 것으로 덮어쓰기)
                        self.settings.update(reloaded_settings)
                        if logger:
                            logger.info(f"✅ 설정 파일 재로드 완료 (사용자: {current_user})")
                    else:
                        if logger:
                            logger.warning("⚠️ 설정 파일 재로드 실패, 기존 설정 사용")
                else:
                    if logger:
                        logger.warning("⚠️ 사용자 계정이 설정되지 않아 설정 파일 재로드 생략")
            except Exception as reload_err:
                if logger:
                    logger.warning(f"⚠️ 설정 파일 재로드 중 오류 (기존 설정 사용): {reload_err}")
                import traceback
                if logger:
                    logger.debug(traceback.format_exc())

            # UnifiedTrader import (여기서 import)
            from trading.unified_trader import UnifiedTrader

            # 🔥 트레이딩 스레드 초기화
            self.trading_thread = None
            self.trading_worker = None

            # Recorder 초기화 (바이낸스 클라이언트 주입)
            self.recorder = Recorder(binance_client=self.binance_client)

            # 데이터베이스 스키마 마이그레이션 실행
            try:
                self.recorder.migrate_database_schema()
            except Exception as e:
                logger = self._get_main_logger()
                if logger:
                    if logger is not None:
                        logger.warning(f"데이터베이스 마이그레이션 실패 (계속 진행): {e}")

            # Analyzer 초기화 (ExchangeManager 주입으로 점진적 다중 거래소 데이터 지원)
            self.analyzer = Analyzer(self.binance_client, exchange_manager=self.exchange_manager)

            # 🔥 Optimizer 초기화 (설정값 우선 전달)
            from inspect import signature, Parameter
            opt_init_params = signature(Optimizer.__init__).parameters
            opt_kwargs = {}

            # 🔥 settings를 우선적으로 전달 (중요!)
            if 'settings' in opt_init_params:
                opt_kwargs['settings'] = self.settings
                logger = self._get_main_logger()
                if logger:
                    if logger is not None:
                        logger.info(f"✅ Optimizer에 settings 전달: min_trade_amount={self.settings.get('min_trade_amount', 5.0)}")

            for name in ('recorder', 'binance_client', 'logger'):
                if name in opt_init_params:
                    opt_kwargs[name] = getattr(self, name) if name != 'logger' else self.logger

            self.optimizer = Optimizer(**opt_kwargs)
            if getattr(self, 'logger', None) is not None:
                logger = self._get_main_logger()
                if logger:
                    logger.info(f"Optimizer init kwargs: {list(opt_kwargs.keys())}")
                    logger.info(f"Optimizer 상태: {type(self.optimizer).__name__}")
                    logger.info(f"Recorder 상태: {type(self.recorder).__name__}")

            # 🔥 Optimizer 설정값 검증 (강화)
            if hasattr(self.optimizer, 'settings') and self.optimizer.settings:
                optimizer_min_trade = self.optimizer.settings.get('min_trade_amount', 'N/A')
                logger = self._get_main_logger()
                if logger:
                    if logger is not None:
                        logger.info(f"✅ Optimizer 설정값 확인: min_trade_amount={optimizer_min_trade}")

                # 🔥 설정값 일치 확인
                main_min_trade = self.settings.get('min_trade_amount', 5.0)
                if optimizer_min_trade != main_min_trade:
                    logger = self._get_main_logger()
                    if logger:
                        if logger is not None:
                            logger.warning(f"⚠️ 설정값 불일치: main={main_min_trade}, optimizer={optimizer_min_trade}")
            else:
                logger = self._get_main_logger()
                if logger:
                    if logger is not None:
                        logger.error("❌ Optimizer에 settings가 전달되지 않음 - 심각한 문제!")

            # 🔥 Optimizer 자체 상태 확인 (바로 넣을 수 있는 진단 로그)
            logger = self._get_main_logger()
            if logger:
                if logger is not None:
                    logger.info(f"Optimizer 클래스: {type(self.optimizer).__name__}")
            for attr in ('risk_limits', 'min_notional', 'min_qty', 'position_sizer', 'config'):
                if hasattr(self.optimizer, attr):
                    logger = self._get_main_logger()
                    if logger:
                        if logger is not None:
                            logger.info(f"Optimizer.{attr} = {getattr(self.optimizer, attr)}")

            # Evaluator 초기화 (settings 객체 전달)
            self.evaluator = Evaluator(self.analyzer, self.recorder, self.settings)

            # AI 매니저 초기화
            openai_api_key = self.settings.get('openai_api_key', '')
            openai_model = self.settings.get('openai_model', 'gpt-4o-mini')

            # 🔥 빌드 환경 대응: API 키가 없으면 설정 파일에서 다시 시도
            if not openai_api_key:
                try:
                    from config.settings import load_settings
                    from path_utils import get_current_user_account, get_config_dir
                    current_user = get_current_user_account()
                    if current_user:
                        if logger:
                            logger.info(f"⚠️ self.settings에 API 키 없음, 설정 파일에서 재시도 (사용자: {current_user})")
                        reloaded_settings = load_settings()
                        if reloaded_settings:
                            openai_api_key = reloaded_settings.get('openai_api_key', '')
                            if openai_api_key:
                                openai_model = reloaded_settings.get('openai_model', openai_model)
                                # 재로드한 설정으로 업데이트
                                self.settings.update(reloaded_settings)
                                if logger:
                                    logger.info(f"✅ 설정 파일에서 API 키 로드 성공 (키 길이: {len(openai_api_key)})")
                            else:
                                config_path = os.path.join(get_config_dir(), 'settings.json')
                                if logger:
                                    logger.warning(f"⚠️ 설정 파일에도 API 키 없음: {config_path}")
                        else:
                            if logger:
                                logger.warning("⚠️ 설정 파일 재로드 실패")
                except Exception as reload_err:
                    if logger:
                        logger.warning(f"⚠️ 설정 파일 재로드 중 오류: {reload_err}")
                    import traceback
                    if logger:
                        logger.debug(traceback.format_exc())

            if openai_api_key:
                # 🔥 설정 파일에서 모델을 우선적으로 사용
                self.ai_manager = AIManager(openai_api_key, openai_model, settings=self.settings)
                # AI 매니저 초기화 로그는 AIManager 클래스에서 자동 출력됨

                # 🔥 Optimizer에 AI 매니저 전달
                self.optimizer.ai_manager = self.ai_manager
                logger = self._get_main_logger()
                if logger:
                    if logger is not None:
                        logger.info("✅ Optimizer에 AI 매니저 전달 완료")
            else:
                self.ai_manager = None
                logger = self._get_main_logger()
                if logger:
                    if logger is not None:
                        logger.warning("OpenAI API 키가 설정되지 않아 AI 기능이 비활성화됩니다")
                        # 빌드 환경 디버깅 정보
                        try:
                            from path_utils import get_config_dir, get_current_user_account
                            config_path = os.path.join(get_config_dir(), 'settings.json')
                            current_user = get_current_user_account()
                            logger.warning(f"  - 설정 파일 경로: {config_path}")
                            logger.warning(f"  - 현재 사용자: {current_user or '없음'}")
                            logger.warning(f"  - 설정 파일 존재: {os.path.exists(config_path)}")
                        except Exception:
                            pass

            # Risk Manager 초기화 (binance_client와 database_manager 필요)
            self.risk_manager = RiskManager(self.binance_client, self.recorder)

            # 🔥 UnifiedTrader 초기화 (다중 거래소 지원)
            if hasattr(self, 'unified_manager') and self.unified_manager:
                self.unified_trader = UnifiedTrader(
                    settings=self.settings,
                    exchange_manager=self.exchange_manager if self.exchange_manager else ExchangeManager(self.settings, self.binance_client, unified_manager=self.unified_manager),
                    unified_manager=self.unified_manager,
                    analyzer=self.analyzer,
                    optimizer=self.optimizer,
                    recorder=self.recorder,
                    ai_manager=self.ai_manager,
                    risk_manager=self.risk_manager,
                    logger=self.logger,
                    dashboard=None  # dashboard는 나중에 설정
                )
                # 🔥 main_app 참조는 생성 후 명시적으로 설정 (Pylance 호환: 세터 사용)
                setter = getattr(self.unified_trader, 'set_main_app', None)
                if callable(setter):
                    setter(self)

                # evaluator 설정
                if hasattr(self, 'evaluator') and self.evaluator:
                    self.unified_trader.set_evaluator(self.evaluator)
                    logger = self._get_main_logger()
                    if logger:
                        logger.info("✅ UnifiedTrader에 Evaluator 설정 완료")

                # selected_coins 설정 (바이낸스와 동일한 방식) - 타입 정규화
                if hasattr(self, 'selected_coins') and self.selected_coins:
                    normalized_for_trader: List[Dict[str, Any]] = []
                    for c in self.selected_coins:
                        if isinstance(c, str):
                            normalized_for_trader.append({'symbol': c, 'is_major': False})  # 🔥 is_major 기본값 추가
                        elif isinstance(c, dict):
                            normalized_for_trader.append(c)  # 🔥 dict인 경우 모든 정보(including is_major) 유지
                    self.unified_trader.set_selected_coins(normalized_for_trader)
                    logger = self._get_main_logger()
                    if logger:
                        logger.info("✅ UnifiedTrader에 선택된 코인 설정 완료")

                logger = self._get_main_logger()
                if logger:
                    logger.info("✅ UnifiedTrader 초기화 완료 - 다중 거래소 지원")
            else:
                self.unified_trader = None
                logger = self._get_main_logger()
                if logger:
                    logger.warning("UnifiedTradingManager가 없어 UnifiedTrader 초기화 실패")

            # 기존 Trader 초기화 (하위 호환성)
            self.trader = Trader(
                binance_client=self.binance_client,
                analyzer=self.analyzer,
                optimizer=self.optimizer,
                recorder=self.recorder,
                ai_manager=self.ai_manager,
                logger=self.logger,  # 🔥 main.py의 logger 전달
                settings=self.settings  # 🔥 settings 전달
            )

            # 🔥 Trader 초기화 후 설정값 동기화 확인
            if hasattr(self.trader, 'settings') and self.trader.settings:
                trader_min_trade = self.trader.settings.get('min_trade_amount', 'N/A')
                logger = self._get_main_logger()
                if logger:
                    logger.info(f"✅ Trader 설정값 확인: min_trade_amount={trader_min_trade}")

                # 🔥 모든 컴포넌트 설정값 일치 확인
                main_min_trade = self.settings.get('min_trade_amount', 5.0)
                optimizer_min_trade = self.optimizer.settings.get('min_trade_amount', 'N/A') if self.optimizer.settings else 'N/A'

                if main_min_trade == trader_min_trade == optimizer_min_trade:
                    logger = self._get_main_logger()
                    if logger:
                        logger.info(f"✅ 모든 컴포넌트 설정값 일치: {main_min_trade}")
                else:
                    logger = self._get_main_logger()
                    if logger:
                        logger.error(f"❌ 설정값 불일치: main={main_min_trade}, trader={trader_min_trade}, optimizer={optimizer_min_trade}")
            else:
                logger = self._get_main_logger()
                if logger:
                    logger.error("❌ Trader에 settings가 설정되지 않음")

            # Dynamic Coin Replacer 기능은 RiskManager와 Evaluator 상호작용으로 대체됨

            # Market State Analyzer 초기화
            self.market_state_analyzer = MarketStateAnalyzer(self.binance_client)

            # Analyzer에 AI 매니저 전달
            if hasattr(self.analyzer, 'ai_manager'):
                self.analyzer.ai_manager = self.ai_manager

            # WebSocket 연결 초기화 (BinanceClient 생성 시 이미 초기화됨)
            # WebSocket 연결은 BinanceClient 생성 시 자동으로 처리됨

            # AI 자동 최적화 시스템 초기화
            self.auto_optimizer = AIAutoOptimizer(
                ai_manager=self.ai_manager,
                recorder=self.recorder,
                settings=self.settings,
                logger=self.logger
            )
            self.auto_optimizer.start()
            logger = self._get_main_logger()
            if logger:
                logger.info("AI 자동 최적화 시스템 시작")

            # FL/SaaS 사전 준비 구조 초기화 (기본값 OFF, 기존 경로 영향 없음)
            self.initialize_federated_learning_preparation()

            # 🔥 상태 관리자 초기화 (모든 컴포넌트 초기화 후)
            self.state = TradingStateManager()
            logger = self._get_main_logger()
            if logger:
                logger.info("✅ 상태 관리자 초기화 완료")

            logger = self._get_main_logger()
            if logger:
                logger.info("트레이딩 컴포넌트 초기화 완료")
        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                logger.error(f"트레이딩 컴포넌트 초기화 오류: {e}")
            raise

    def initialize_federated_learning_preparation(self):
        """연합학습/사전 SaaS 준비 구조 초기화 (안전 모드)."""
        try:
            logger = self._get_main_logger()
            self.fl_preparation_service = FederatedLearningPreparationService(
                settings=self.settings,
                logger=logger,
            )
            result = self.fl_preparation_service.bootstrap()
            if logger:
                logger.info(
                    f"FL 준비 구조 상태: enabled={result.get('enabled')} "
                    f"batch_enabled={result.get('batch_enabled')} "
                    f"upload_enabled={result.get('upload_enabled')}"
                )
        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                logger.warning(f"FL 준비 구조 초기화 실패(운영 영향 없이 계속): {e}")


    def manage_trading_websocket_subscriptions(self, selected_coins: Sequence[SelectedCoin]):
        """🔥 거래용 웹소켓 구독 관리 (5개씩 순차적으로 진행)"""
        try:
            logger = self._get_main_logger()
            if not self.binance_client or not hasattr(self.binance_client, 'websocket_manager'):
                if logger:
                    logger.warning("웹소켓 매니저가 초기화되지 않음")
                return

            if not getattr(self, 'binance_client', None) or not hasattr(self.binance_client, 'websocket_manager'):
                return
            websocket_manager: Any = self.binance_client.websocket_manager

            # 현재 구독 중인 코인들 확인
            current_subscriptions = getattr(websocket_manager, 'active_subscriptions', set())
            if not current_subscriptions:
                current_subscriptions = set()
            # Normalize current subscriptions to UPPER symbols
            current_subscriptions = set(str(s).upper() for s in current_subscriptions)

            # 거래 대상 코인들 (USDT 접미사 처리) — 항상 문자열 보장
            trading_coins = set()
            def _to_symbol_str(item):
                # item can be dict, str, or other; normalize to upper-case string symbol
                if isinstance(item, dict):
                    # common keys we might see
                    for k in ("symbol", "base", "ticker"):
                        v = item.get(k)
                        if isinstance(v, str) and v.strip():
                            return v.strip().upper()
                if isinstance(item, str):
                    return item.strip().upper()
                # Fallback: stringified
                return str(item).strip().upper()

            for coin_data in selected_coins:
                sym = _to_symbol_str(coin_data)
                if not sym:
                    continue
                # If coin_data nested dicts accidentally appear as stringified JSON, re-normalize
                if sym.startswith("{") and sym.endswith("}"):
                    try:
                        import json as _json
                        parsed = _json.loads(sym)
                        sym = _to_symbol_str(parsed)
                    except Exception:
                        pass
                # Append USDT suffix if missing
                if not sym.endswith("USDT"):
                    sym = f"{sym}USDT"
                trading_coins.add(sym)

            if logger:
                logger.info(f"현재 구독: {len(current_subscriptions)}개, 거래 대상: {len(trading_coins)}개")

            # 🔥 구독 해제: 이전 거래 대상이었지만 현재는 아닌 코인들
            # 동적 코인 선택 결과에 따라 구독 관리
            if hasattr(self, 'previous_trading_coins'):
                previous_trading = set(self.previous_trading_coins) if self.previous_trading_coins else set()
                coins_to_unsubscribe = previous_trading - trading_coins
            else:
                coins_to_unsubscribe = set()

            if coins_to_unsubscribe:
                if logger:
                    logger.info(f"구독 해제 대상: {len(coins_to_unsubscribe)}개 - {list(coins_to_unsubscribe)}")

                for coin in coins_to_unsubscribe:
                    try:
                        # 웹소켓 구독 해제
                        if hasattr(websocket_manager, 'unsubscribe_symbol'):
                            websocket_manager.unsubscribe_symbol(coin)
                            if logger:
                                logger.info(f"🔴 이전 거래 대상 해제: {coin}")
                        else:
                            if logger:
                                logger.warning(f"구독 해제 메서드를 찾을 수 없음: {coin}")
                    except Exception as e:
                        if logger:
                            logger.warning(f"구독 해제 실패: {coin} - {e}")
            else:
                if logger:
                    logger.info("구독 해제할 코인이 없음")

            # 🔥 구독 추가: 거래 대상이지만 현재 구독되지 않은 코인들
            coins_to_subscribe = trading_coins - current_subscriptions
            if coins_to_subscribe:
                if logger:
                    logger.info(f"구독 추가 대상: {len(coins_to_subscribe)}개 - {list(coins_to_subscribe)}")

                # 🔥 5개씩 구독 진행 (바이낸스 제한 최적화)
                coins_list = list(coins_to_subscribe)
                batch_size = 5

                for i in range(0, len(coins_list), batch_size):
                    batch = coins_list[i:i + batch_size]
                    if logger:
                        logger.info(f"구독 배치 {i//batch_size + 1}: {batch}")

                    for coin in batch:
                        try:
                            # 웹소켓 구독 추가
                            if hasattr(websocket_manager, 'subscribe_symbol'):
                                success = websocket_manager.subscribe_symbol(coin)
                                if success:
                                    if logger:
                                        logger.info(f"거래 진입으로 구독 추가: {coin}")
                                else:
                                    if logger:
                                        logger.warning(f"{coin} 구독 추가 실패")
                            else:
                                if logger:
                                    logger.warning(f"구독 추가 메서드를 찾을 수 없음: {coin}")
                        except Exception as e:
                            if logger:
                                logger.warning(f"구독 추가 실패: {coin} - {e}")

                    # 🔥 배치 간 안전한 대기 (3개씩 구독 후 1초 대기)
                    if i + batch_size < len(coins_list):
                        if logger:
                            logger.info("⏳ 다음 배치 대기 중... (1초)")
                        time.sleep(1.0)

            # 🔥 포지션 관리 및 거래 대기 로직 통합
            self._manage_subscription_retention_policy(trading_coins)

            if logger:
                logger.info(f"웹소켓 구독 관리 완료: 총 {len(trading_coins)}개 코인")

            # 🔥 이전 거래 대상 저장 (다음 구독 관리 시 사용)
            self.previous_trading_coins = list(trading_coins)

            # 🔥 대시보드 업데이트 (원본 selected_coins 사용)
            if hasattr(self, 'dashboard') and self.dashboard:
                # trading_coins는 문자열 set이므로, 원본 selected_coins 사용
                if hasattr(self, 'selected_coins') and self.selected_coins:
                    self.dashboard.update_selected_coins(self.selected_coins)
                    if logger:
                        logger.info("대시보드 코인 정보 업데이트 완료")
                else:
                    if logger:
                        logger.warning("선택된 코인 정보가 없어 대시보드 업데이트 생략")

        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                logger.error(f"웹소켓 구독 관리 오류: {e}")

    def _manage_subscription_retention_policy(self, trading_coins: set):
        """🔥 포지션 관리 및 거래 대기 로직 (구독 유지 정책)"""
        try:
            logger = self._get_main_logger()
            # 안전한 웹소켓 매니저 접근
            binance_client = getattr(self, 'binance_client', None)
            if not binance_client or not hasattr(binance_client, 'websocket_manager'):
                if logger:
                    logger.warning("WebSocket 매니저가 없어 구독 유지 정책을 건너뜁니다")
                return
            websocket_manager = getattr(binance_client, 'websocket_manager', None)
            if not websocket_manager:
                if logger:
                    logger.warning("WebSocket 매니저가 None 입니다 - 정책 생략")
                return
            current_subscriptions = getattr(websocket_manager, 'active_subscriptions', set())

            # 🔥 포지션 관리가 필요한 경우 구독 유지
            should_keep_subscription = {}

            for coin_symbol in trading_coins:
                should_keep_subscription[coin_symbol] = False

                # 1) 열린 포지션이 있는지 확인 (집중 모드 에러 핸들링 완화)
                if hasattr(self, 'trader') and self.trader:
                    try:
                        open_positions = []

                        # 🔥 get_open_positions 시도, 실패 시 get_active_positions로 대체
                        try:
                            if hasattr(self.trader, 'get_open_positions'):
                                open_positions = self.trader.get_open_positions()
                            elif hasattr(self.trader, 'get_active_positions'):
                                open_positions = self.trader.get_active_positions()
                                if logger:
                                    logger.debug(f"[{coin_symbol}] get_active_positions로 대체 성공")
                            else:
                                if logger:
                                    logger.debug(f"[{coin_symbol}] get_active_positions도 없음 - 빈 리스트 사용")
                                open_positions = []
                        except Exception as e:
                            # 기본 조회 실패 시 마지막으로 get_active_positions 재시도
                            try:
                                if hasattr(self.trader, 'get_active_positions'):
                                    open_positions = self.trader.get_active_positions()
                                    if logger:
                                        logger.debug(f"[{coin_symbol}] 예외 후 get_active_positions로 대체 성공: {e}")
                                else:
                                    if logger:
                                        logger.debug(f"[{coin_symbol}] 예외 후에도 대체 불가 - 빈 리스트 사용: {e}")
                                    open_positions = []
                            except Exception as e3:
                                if logger:
                                    logger.debug(f"[{coin_symbol}] get_active_positions 호출 실패: {e3} - 빈 리스트 사용")
                                open_positions = []

                        # 🔥 포지션 타입을 명시적으로 체크하고 안전하게 처리
                        positions_type = 'list' if isinstance(open_positions, list) else 'dict' if isinstance(open_positions, dict) else 'unknown'
                        if positions_type == 'unknown':
                            open_positions = []
                            positions_type = 'list'

                        # 🔥 타입에 따라 안전하게 멤버십 체크
                        has_pos = False
                        if positions_type == 'list':
                            # 리스트 요소가 dict 또는 str 양쪽 가능성을 모두 케어
                            has_pos = any(
                                ((p.get('symbol') if isinstance(p, dict) else p) == coin_symbol)
                                for p in open_positions
                            )
                        else:
                            # dict
                            has_pos = coin_symbol in open_positions

                        if has_pos:
                            should_keep_subscription[coin_symbol] = True
                            if logger:
                                logger.debug(f"[{coin_symbol}] 열린 포지션 존재 - 구독 유지 (타입: {positions_type})")
                    except Exception as e:
                        if logger:
                            logger.debug(f"[{coin_symbol}] 포지션 확인 중 오류 (무시): {e}")

                # 2) 최근 거래 발생 시 일정 시간 구독 유지
                if not should_keep_subscription[coin_symbol]:
                    if not hasattr(self, '_subscription_keep_times'):
                        self._subscription_keep_times = {}

                    keep_time = self._subscription_keep_times.get(coin_symbol)
                    if keep_time:
                        time_diff = (datetime.now() - keep_time).total_seconds()
                        if time_diff < 300:  # 5분 (300초)
                            should_keep_subscription[coin_symbol] = True
                            if logger:
                                logger.debug(f"[{coin_symbol}] 구독 유지 중 ({300 - time_diff:.0f}초 남음)")
                        else:
                            # 5분 경과 시 구독 해제
                            del self._subscription_keep_times[coin_symbol]
                            if logger:
                                logger.info(f"[{coin_symbol}] 구독 유지 시간 경과 - 해제 예정")

                # 3) 거래 신호 발생 시 5분간 구독 유지 설정
                if not should_keep_subscription[coin_symbol]:
                    # 거래 신호가 발생한 코인은 5분간 구독 유지
                    if coin_symbol in getattr(self, '_recent_trading_signals', set()):
                        self._subscription_keep_times[coin_symbol] = datetime.now()
                        should_keep_subscription[coin_symbol] = True
                        if logger:
                            logger.info(f"[{coin_symbol}] 거래 신호 발생 - 5분간 구독 유지")

            # 🔥 구독 해제 결정 및 실행
            for coin_symbol in current_subscriptions:
                if coin_symbol in trading_coins:
                    # 현재 거래 대상이면 유지
                    continue


                if should_keep_subscription.get(coin_symbol, False):
                    # 포지션 관리/거래 대기로 구독 유지
                    if logger:
                        logger.debug(f"[{coin_symbol}] 포지션 관리/거래 대기로 구독 유지")
                    continue

                # 구독 해제 실행
                if logger:
                    logger.info(f"[{coin_symbol}] 구독 해제 시도...")
                try:
                    if hasattr(websocket_manager, 'unsubscribe_symbol'):
                        websocket_manager.unsubscribe_symbol(coin_symbol)
                        if logger:
                            logger.info(f"[{coin_symbol}] 웹소켓 구독 해제 성공")
                    else:
                        if logger:
                            logger.error(f"[{coin_symbol}] 구독 해제 메서드 없음 (unsubscribe_symbol 미구현)")
                except Exception as e:
                    if logger:
                        logger.error(f"[{coin_symbol}] 구독 해제 오류: {e}")

        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                logger.error(f"구독 유지 정책 관리 오류: {e}")

    def show_dashboard(self):
        """대시보드 표시"""
        try:
            logger = self._get_main_logger()
            if logger:
                logger.info("대시보드 표시 시작")

            # 🔥 중복 호출 방지 가드
            if getattr(self, '_dashboard_initialized', False):
                if logger:
                    logger.debug('대시보드가 이미 초기화되어 표시 요청을 건너뜁니다.')
                return

            # 🔥 대시보드 생성 전 사용자 계정 확인/설정
            from path_utils import get_current_user_account, get_account_info_from_token, set_current_user_account
            current_user = get_current_user_account()
            if not current_user:
                # 계정이 설정되지 않았으면 토큰에서 읽기
                user_id, _ = get_account_info_from_token()
                if user_id:
                    set_current_user_account(user_id)
                    if logger:
                        logger.info(f"대시보드 생성 전 사용자 계정 설정: {user_id}")
                else:
                    if logger:
                        logger.warning("사용자 계정 정보를 찾을 수 없습니다")
            else:
                if logger:
                    logger.debug(f"대시보드 생성 - 현재 사용자: {current_user}")

            # 대시보드 생성 (UnifiedTrader 전달)
            if logger:
                logger.info("show_dashboard: ModernDashboard 생성 시도")
            self.dashboard = ModernDashboard(
                self.settings,
                self.exchange_manager,
                self,  # main_app 전달
                unified_trader=self.unified_trader  # UnifiedTrader 전달
            )
            if logger:
                logger.info("show_dashboard: ModernDashboard 생성 완료")

            # 전역 참조 설정 (종료 핸들러에서 접근)
            _DASHBOARD_REF["obj"] = self.dashboard
            self._dashboard_initialized = True

            # 창 표시 강제 (숨김/최소화 상태 대비)
            try:
                if hasattr(self.dashboard, 'deiconify'):
                    self.dashboard.deiconify()
                if hasattr(self.dashboard, 'lift'):
                    self.dashboard.lift()
                if hasattr(self.dashboard, 'focus_force'):
                    self.dashboard.focus_force()
            except Exception as _e:
                if logger:
                    logger.warning(f"show_dashboard: 창 표시 강제 중 경고: {_e}")

            # 상태 점검 로그
            try:
                exists = bool(self.dashboard.winfo_exists()) if hasattr(self.dashboard, 'winfo_exists') else None
                state = str(self.dashboard.state()) if hasattr(self.dashboard, 'state') else 'unknown'
                geometry = str(self.dashboard.geometry()) if hasattr(self.dashboard, 'geometry') else 'unknown'
                if logger:
                    logger.info(f"show_dashboard: window exists={exists}, state={state}, geometry={geometry}")
            except Exception as _e2:
                if logger:
                    logger.warning(f"show_dashboard: 창 상태 확인 경고: {_e2}")

            # 🔥 거래소 관리자를 대시보드에 연결
            if hasattr(self, 'exchange_manager') and self.exchange_manager:
                self.dashboard.exchange_manager = self.exchange_manager
                if logger:
                    logger.info("✅ 대시보드에 거래소 관리자 연결 완료")

            if hasattr(self, 'api_signal_manager') and self.api_signal_manager:
                self.dashboard.api_signal_manager = self.api_signal_manager
                if logger:
                    logger.info("✅ 대시보드에 API 신호 관리자 연결 완료")

            # 컴포넌트 설정
            # 🔥 컴포넌트 None 체크 및 방어적 처리

            if not all([self.binance_client, self.analyzer, self.evaluator, self.trader, self.recorder]):
                missing = []
                if not self.binance_client: missing.append("binance_client")
                if not self.analyzer: missing.append("analyzer")
                if not self.evaluator: missing.append("evaluator")
                if not self.trader: missing.append("trader")
                if not self.recorder: missing.append("recorder")
                raise Exception(f"필수 컴포넌트 누락: {', '.join(missing)}")

            self.dashboard.set_components(
                binance_client=self.binance_client,
                analyzer=self.analyzer,
                evaluator=self.evaluator,
                trader=self.trader,
                recorder=self.recorder
            )

            # 추가 컴포넌트 설정
            self.dashboard.optimizer = self.optimizer
            self.dashboard.ai_manager = self.ai_manager
            self.dashboard.risk_manager = self.risk_manager
            # dynamic_coin_replacer는 None이므로 제거
            # self.dashboard.dynamic_coin_replacer = self.dynamic_coin_replacer
            self.dashboard.market_state_analyzer = self.market_state_analyzer

            # Trader에 대시보드 참조 전달 (잔고 업데이트용)
            if self.trader:
                self.trader.dashboard = self.dashboard

            # UnifiedTrader에 대시보드 참조 전달
            if hasattr(self, 'unified_trader') and self.unified_trader:
                self.unified_trader.dashboard = self.dashboard
                if logger:
                    logger.info("✅ UnifiedTrader에 대시보드 연결 완료")

            # 대시보드에 main.py 참조 전달 (자동거래 토글용)
            self.dashboard.main_app = self

            # 자동 업데이트 백그라운드 체크 시작
            try:
                if self.auto_update_manager is not None:
                    self.auto_update_manager.start_scheduler(
                        ui_root=self.dashboard,
                        notify_callback=self._notify_auto_update,
                    )
            except Exception as _up_e:
                if logger:
                    logger.warning(f"자동 업데이트 스케줄러 시작 실패: {_up_e}")

            # 대시보드 종료 시 정리 메서드 연결
            self.dashboard.protocol("WM_DELETE_WINDOW", self.dashboard.on_closing)

            # 대시보드 표시 (CustomTkinter는 mainloop 사용)
            # mainloop()는 메인 이벤트 루프를 시작하므로 여기서 멈춤
            try:
                # CustomTkinter mainloop 사용 (신호 처리는 전역 핸들러에서)
                self.dashboard.mainloop()
            except KeyboardInterrupt:
                try:
                    if logger:
                        logger.info("프로그램이 중단되었습니다.")
                except Exception:
                    logger = self._get_main_logger(); logger.info('프로그램이 중단되었습니다.')
            except Exception as e:
                try:
                    if logger:
                        logger.error(f"대시보드 실행 오류: {e}")
                except Exception:
                    logger = self._get_main_logger(); logger.error(f'대시보드 실행 오류: {e}')
            finally:
                try:
                    if self.auto_update_manager is not None:
                        self.auto_update_manager.stop_scheduler()
                except Exception:
                    pass
                # 대시보드 종료 시 정리
                if hasattr(self.dashboard, 'on_closing'):
                    self.dashboard.on_closing()

                self._dashboard_initialized = False

        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                logger.error(f"대시보드 표시 오류: {e}")
            # 🔥 콘솔에 예외 강제 노출 (디버깅용)
            print(f"❌ 대시보드 표시 오류: {e}")
            import traceback
            print("❌ 대시보드 오류 상세:")
            print(traceback.format_exc())
            try:
                # QMessageBox.critical(None, "오류", f"대시보드를 표시할 수 없습니다:\n{str(e)}")
                pass  # PyQt5 의존성 제거로 인해 비활성화
            except Exception as e2:
                if logger:
                    logger.error(f"오류 대화상자 표시 실패: {e2}")
                    logger.error(f'치명적 오류: {e}')
                    logger.error(f'대화상자 오류: {e2}')

    def _initialize_auto_update_manager(self):
        """자동 업데이트 매니저를 초기화한다."""
        try:
            logger = self._get_main_logger()
            if self.auto_update_manager is None:
                self.auto_update_manager = AutoUpdateManager(settings=self.settings, logger=logger)
            else:
                self.auto_update_manager.update_settings(self.settings)
        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                logger.warning(f"자동 업데이트 매니저 초기화 실패: {e}")

    def _notify_auto_update(self, message: str):
        """자동 업데이트 알림을 대시보드 토스트/로그로 전달한다."""
        logger = self._get_main_logger()
        if logger:
            logger.info(f"[AUTO_UPDATE] {message}")
        try:
            if hasattr(self, 'dashboard') and self.dashboard and hasattr(self.dashboard, '_show_toast'):
                self.dashboard._show_toast(message, duration_ms=5000)
        except Exception:
            pass

    def prepare_update_apply_on_exit(self) -> bool:
        """앱 종료 직전에 다운로드된 업데이트를 적용하고 재시작을 예약한다."""
        try:
            if self.auto_update_manager is None:
                return False
            return bool(self.auto_update_manager.apply_pending_update_and_restart())
        except Exception:
            return False

    def on_toggle_trading(self, is_running: bool):
        """자동거래 토글 처리 (상태 매니저 우선)"""
        try:
            logger = self._get_main_logger()
            logger.info(f"🔍 main.py on_toggle_trading 호출됨 - is_running: {is_running}")

            if is_running:
                # 🔥 상태 머신 기반 시작
                if hasattr(self, 'state') and self.state.can_start():
                    self.state.mark_starting('binance', True)

                    # 코인 선택 및 트레이딩 루프 시작
                    if logger:
                        logger.info("🔍 코인 선택 시작")
                    self.select_trading_coins()
                    if logger:
                        logger.info("🔍 코인 선택 완료")

                    if logger:
                        logger.info("🔍 트레이딩 루프 시작")
                    self.start_trading_loop()
                    if logger:
                        logger.info("🔍 트레이딩 루프 시작 완료")

                    # 상태를 RUNNING으로 변경
                    self.state.mark_running()

                    # UI 동기화
                    if hasattr(self, 'dashboard') and self.dashboard:
                        self.dashboard.is_auto_trading = True
                        self.dashboard.update_status_display(force_refresh=True)
                        if logger:
                            logger.info("🔍 대시보드 자동거래 상태를 True로 설정")

                    if logger:
                        logger.info("✅ 자동거래 시작 성공")
                else:
                    logger.warning(f"Cannot start: current state={getattr(self.state, 'state', 'NO_STATE')}")
            else:
                # 🔥 상태 머신 기반 정지
                if hasattr(self, 'state') and self.state.can_stop():
                    self.state.mark_stop_pending()

                    # UI 동기화
                    if hasattr(self, 'dashboard') and self.dashboard:
                        self.dashboard.is_auto_trading = False
                        self.dashboard.update_status_display(force_refresh=True)
                        if logger:
                            logger.info(f"✅ 대시보드 자동거래 상태 설정: {self.dashboard.is_auto_trading}")

                    self.stop_trading_loop()

                    # 상태를 IDLE로 변경
                    self.state.mark_idle()

                    logger.info("✅ 자동거래 정지 성공")
                else:
                    logger.warning(f"Cannot stop: current state={getattr(self.state, 'state', 'NO_STATE')}")

        except Exception as e:
            logger = self._get_main_logger()
            logger.error(f"❌ 자동거래 토글 오류: {e}")
            logger.error(traceback.format_exc())
            # 오류 시 상태를 IDLE로 복구
            if hasattr(self, 'state'):
                self.state.mark_idle()

    def _validate_exchange_keys(self, exchange: str) -> bool:
        """거래소별 API 키 기본 검증(비어있음/placeholder 등)"""
        try:
            ex = (exchange or '').lower().strip()
            if not ex:
                return False
            # 공통: api/secret
            api = str(self.settings.get(f"{ex}_api_key", '') or '').strip()
            sec = str(self.settings.get(f"{ex}_secret_key", '') or '').strip()
            if not api or not sec:
                return False
            # OKX: passphrase 필요
            if ex == 'okx':
                p = str(self.settings.get(f"{ex}_passphrase", '') or '').strip()
                if not p:
                    return False
            # 간단 placeholder 패턴 필터
            bads = {'xxxx', 'xxxxx', 'your', 'paste', 'secret', 'api'}
            low = (api + sec).lower()
            if any(b in low for b in bads):
                return False
            return True
        except Exception:
            return False

    def on_start_exchange(self, exchange: str, auto: bool = True) -> bool:
        """거래소별 시작 (상태 매니저 우선)"""
        try:
            logger = self._get_main_logger()
            ex = (exchange or "").lower().strip() or "binance"
            logger.info(f"🚀 거래소별 시작 요청: {ex}")

            # 이미 실행 중인 거래소는 성공으로 간주(중복 시작 방지)
            try:
                if ex == 'binance':
                    if bool(getattr(self, 'trading_thread', None)) and self.trading_thread.is_alive():
                        logger.info(f"ℹ️ {ex} 이미 실행 중 - 중복 시작 생략")
                        return True
                else:
                    flags = getattr(getattr(self, 'unified_trader', None), 'monitoring_flags', {}) or {}
                    if bool(flags.get(ex, False)):
                        logger.info(f"ℹ️ {ex} 이미 실행 중 - 중복 시작 생략")
                        return True
            except Exception:
                pass

            # 증권/ETF는 현재 자동거래 워커 루프 대상이 아님 (분석/조회 경로로 운영)
            stock_brokers = {'kiwoom', 'shinhan', 'miraeasset', 'mirae_asset'}
            if ex in stock_brokers:
                logger.warning(
                    f"{ex} 자동거래 시작은 지원되지 않습니다. 증권 탭에서 연결/분석 기능을 사용하세요."
                )
                try:
                    if hasattr(self, 'dashboard') and self.dashboard and hasattr(self.dashboard, 'set_trading_status'):
                        self.dashboard.set_trading_status("IDLE")
                except Exception:
                    pass
                return False

            # 🔥 상태 우선 검사 (다중 거래소 병렬 시작 허용)
            allow_parallel_start = False
            if hasattr(self, 'state') and self.state:
                state_name = str(getattr(self.state, 'state', '') or '').upper()
                current_ex = str(getattr(self.state, 'exchange', '') or '').strip().lower()
                if state_name in ('RUNNING', 'STARTING') and current_ex and current_ex != ex:
                    allow_parallel_start = True

            if not hasattr(self, 'state') or (not self.state.can_start() and not allow_parallel_start):
                logger.warning(f"Cannot start: current state={getattr(self.state, 'state', 'NO_STATE')}")
                return False

            # 최소 API 키 검증
            if not self._validate_exchange_keys(ex):
                if logger:
                    logger.warning(f"{ex} API 키 미설정 또는 유효하지 않음 - 시작 불가")
                # 대시보드에 invalid_key 상태 반영(가능 시)
                try:
                    if hasattr(self, 'dashboard') and self.dashboard and hasattr(self.dashboard, '_update_exchange_status'):
                        self.dashboard._update_exchange_status(ex, 'invalid_key')
                except Exception:
                    pass
                return False

            # 단일 실행 시작인 경우에만 상태머신 전이
            if not allow_parallel_start:
                self.state.mark_starting(ex, auto)

            # 1) 컴포넌트 보장
            if not getattr(self, "trader", None):
                self.initialize_trading_components()

            # 2) 거래소 분기 → 상태가 보유
            if ex == 'binance':
                ok = self._start_binance_trading()
            else:
                ok = self._start_unified_trading(ex)

            if ok:
                if not allow_parallel_start:
                    self.state.mark_running()
                # UI 동기화는 상태에서 내려주기
                if hasattr(self, 'dashboard') and self.dashboard:
                    self.dashboard.is_auto_trading = auto
                    if hasattr(self.dashboard, 'set_trading_status'):
                        self.dashboard.set_trading_status("RUNNING")
                logger.info(f"✅ {ex} 거래 시작 성공")
            else:
                if not allow_parallel_start:
                    self.state.mark_idle()
                if hasattr(self, 'dashboard') and self.dashboard:
                    if hasattr(self.dashboard, 'set_trading_status'):
                        self.dashboard.set_trading_status("IDLE")
                logger.warning(f"❌ {ex} 거래 시작 실패")

            return ok

        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                logger.error(f"❌ 거래소 시작 실패: {e}")
            # 오류 시 상태를 IDLE로 복구
            if hasattr(self, 'state'):
                self.state.mark_idle()
            return False

    def _start_binance_trading(self) -> bool:
        """바이낸스 거래 시작 (trader.py 사용)"""
        logger = self._get_main_logger()
        try:
            # Trader 객체 보장
            if not hasattr(self, 'trader') or not self.trader:
                if logger:
                    logger.warning("Trader 객체가 초기화되지 않음")
                return False

            # 코인 선택 (selected_coins가 비어있으면)
            if not self.selected_coins:
                if logger:
                    logger.info("코인 선택 시작")
                self.select_trading_coins()
                if logger:
                    logger.info(f"코인 선택 완료: {len(self.selected_coins)}개")

            # 바이낸스 거래 루프 시작
            if hasattr(self, 'start_trading_loop'):
                result = self.start_trading_loop()
                if result:
                    if logger:
                        logger.info("✅ 바이낸스 거래 루프 시작 성공")
                    return True
                else:
                    if logger:
                        logger.warning("⚠️ 바이낸스 거래 루프 시작 실패")
                    return False
            else:
                if logger:
                    logger.warning("start_trading_loop 메서드가 없음")
                return False

        except Exception as e:
            if logger:
                logger.error(f"❌ 바이낸스 거래 시작 오류: {e}")
            return False

    def _start_unified_trading(self, exchange: str) -> bool:
        """통합 거래소 거래 시작 (unified_trader.py 사용)"""
        logger = self._get_main_logger()
        try:
            # UnifiedTrader 인스턴스 보장
            if not hasattr(self, 'unified_trader') or not self.unified_trader:
                try:
                    # 필수 매니저 준비 확인
                    if not hasattr(self, 'exchange_manager') or not self.exchange_manager:
                        self.exchange_manager = ExchangeManager(self.settings)
                    if not hasattr(self, 'unified_manager') or not self.unified_manager:
                        self.unified_manager = UnifiedTradingManager(self.settings)
                    self.unified_trader = UnifiedTrader(
                        settings=self.settings,
                        exchange_manager=self.exchange_manager,
                        unified_manager=self.unified_manager,
                        analyzer=getattr(self, 'analyzer', None),
                        optimizer=getattr(self, 'optimizer', None),
                        recorder=getattr(self, 'recorder', None),
                        ai_manager=getattr(self, 'ai_manager', None),
                        risk_manager=getattr(self, 'risk_manager', None),
                        websocket_manager=None,
                        dashboard=getattr(self, 'dashboard', None),
                        logger=logging.getLogger(__name__),
                    )
                except Exception as ie:
                    if logger:
                        logger.error(f"UnifiedTrader 생성 실패: {ie}")
                    return False

            # Evaluator 연결 보장
            if hasattr(self, 'evaluator') and self.evaluator and hasattr(self.unified_trader, 'set_evaluator'):
                try:
                    self.unified_trader.set_evaluator(self.evaluator)
                except Exception:
                    pass

            # 통합 거래소 거래 시작
            if hasattr(self.unified_trader, 'start_trading'):
                result = self.unified_trader.start_trading(exchange)
                if result:
                    logger.info(f"✅ {exchange} 거래 시작 성공")
                    return True
                else:
                    logger.warning(f"⚠️ {exchange} 거래 시작 실패")
                    return False
            else:
                logger.warning("UnifiedTrader에 start_trading 메서드가 없음")
                return False

        except Exception as e:
            if logger:
                logger.error(f"❌ {exchange} 거래 시작 오류: {e}")
            return False

    def on_stop_exchange(self, exchange: str) -> bool:
        """거래소별 정지 (상태 매니저 우선)"""
        try:
            logger = self._get_main_logger()
            ex = (exchange or "").lower().strip() or "binance"
            logger.info(f"⏹️ 거래소별 정지 요청: {ex}")

            # 🔥 상태 우선 검사 - 워커 실행 중이면 정지 허용
            can_stop = True
            if hasattr(self, 'state') and hasattr(self.state, 'can_stop'):
                can_stop = self.state.can_stop()

            # 🔥 워커가 실행 중이면 상태와 무관하게 정지 허용
            if not can_stop and hasattr(self, 'trading_worker') and self.trading_worker and self.trading_worker.running:
                can_stop = True
                logger.info(f"🔥 워커 실행 중 - 강제 정지 허용")

            if not can_stop:
                logger.warning(f"Cannot stop: current state={getattr(self.state, 'state', 'NO_STATE')}")
                return False

            # 🔥 상태를 STOP_PENDING으로 변경
            self.state.mark_stop_pending()

            # "우아한 정지" 호출
            if ex == 'binance':
                ok = self._stop_binance_trading()
            else:
                ok = self._stop_unified_trading(ex)

            # 모두 끝난 뒤에:
            if ok:
                self.state.mark_stopped()  # 🔥 STOPPED 상태로 변경
                if hasattr(self, 'dashboard') and self.dashboard:
                    self.dashboard.is_auto_trading = False
                    if hasattr(self.dashboard, 'set_trading_status'):
                        self.dashboard.set_trading_status("STOPPED")
                    if hasattr(self.dashboard, 'update_status_display'):
                        self.dashboard.update_status_display(force_refresh=True)
                logger.info(f"✅ {ex} 거래 정지 성공")
            else:
                logger.warning(f"❌ {ex} 거래 정지 실패")

            return ok

        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                logger.error(f"❌ 거래소 정지 실패: {e}")
            # 오류 시 상태를 IDLE로 복구
            if hasattr(self, 'state'):
                self.state.mark_idle()
            return False

    def _stop_binance_trading(self) -> bool:
        """바이낸스 거래 정지 (우아한 정지 사용)"""
        logger = self._get_main_logger()
        try:
            # 🔥 우아한 정지 사용
            if hasattr(self, 'trader') and self.trader:
                self.trader.stop_trading_gracefully()

            # 🔥 반드시 trading_worker도 정지 (워커 루프 중단)
            self.stop_trading_loop()

            if logger:
                logger.info("✅ 바이낸스 거래 정지 성공")
            return True

        except Exception as e:
            if logger:
                logger.error(f"❌ 바이낸스 거래 정지 실패: {e}")
            return False

    def _stop_unified_trading(self, exchange: str) -> bool:
        """통합 거래소 거래 정지 (unified_trader.py 사용)"""
        logger = self._get_main_logger()
        try:
            if hasattr(self, 'unified_trader') and self.unified_trader:
                try:
                    self.unified_trader.stop_trading(exchange)
                    logger.info(f"✅ {exchange} 거래 정지 성공")
                    return True
                except Exception as ie:
                    if logger:
                        logger.error(f"UnifiedTrader stop 실패: {ie}")
                    return False
            else:
                logger.warning("UnifiedTrader 객체가 초기화되지 않음")
                return False

            # 대시보드 상태 업데이트 시도 (다른 거래소가 여전히 실행 중일 수 있음)
            try:
                if hasattr(self, 'dashboard') and self.dashboard:
                    # 실행 중인 거래소가 하나라도 있으면 True 유지
                    running_any = False
                    try:
                        flags = getattr(self.unified_trader, 'monitoring_flags', {}) if self.unified_trader else {}
                        running_any = any(flags.values())
                    except Exception:
                        pass
                    self.dashboard.is_auto_trading = bool(running_any)
                    self.dashboard.update_status_display(force_refresh=True)
            except Exception:
                pass

        except Exception as e:
            if logger:
                logger.error(f"❌ {exchange} 거래 정지 오류: {e}")
            return False

    def _check_signal(self):
        """신호 체크 (주기적으로 호출)"""
        try:
            # 대시보드가 존재하는 동안 계속 체크
            if hasattr(self, 'dashboard') and self.dashboard and self.dashboard.winfo_exists():
                self.dashboard.after(1000, self._check_signal)  # 1초 후 다시 체크
        except:
            pass

    def start_trading_loop(self):
        """트레이딩 루프 시작 (별도 스레드에서 실행)"""
        try:
            logger = self._get_main_logger()
            # 거래 시작 전 손실 한도 체크
            if hasattr(self, 'risk_manager') and self.risk_manager:
                if self.risk_manager.check_daily_loss_limit():
                    if logger:
                        logger.error("일일 손실 한도 초과 - 거래 시작 불가")
                    return False
            else:
                if logger:
                    logger.warning("RiskManager가 초기화되지 않음 - 손실 한도 체크 건너뜀")

            # 🔥 거래 시작 로그
            if logger:
                logger.info("🔥 자동거래 시작 - 기존 로그 파일에 계속 기록")

            # 🔥 기존 스레드가 실행 중이면 정지
            if self.trading_thread and self.trading_thread.is_alive():
                self.stop_trading_loop()

            # 🔥 새로운 트레이딩 스레드 생성 (threading 사용)
            import threading
            self.trading_thread = threading.Thread(target=self._trading_loop_thread, daemon=True)
            self.trading_thread.start()
            if logger:
                logger.info("🔥 트레이딩 루프 시작 (별도 스레드에서 실행)")
            return True

        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                logger.error(f"트레이딩 루프 시작 오류: {e}")
            return False

    def _trading_loop_thread(self):
        """트레이딩 루프 스레드 함수"""
        try:
            from log_system.log_adapter import log_event

            # TradingWorker 생성 및 실행
            if not hasattr(self, 'trading_worker') or not self.trading_worker:
                self.trading_worker = TradingWorker(self)

            # 🔥 TradingWorker 시작 (self.running = True 설정)
            self.trading_worker.start()

            # 실제 트레이딩 루프 실행
            self.trading_worker.run_trading_loop()

        except Exception as e:
            from log_system.log_adapter import log_event
            log_event('system', f'❌ 트레이딩 루프 스레드 오류: {e}')
            import traceback
            log_event('system', f'❌ 상세 오류: {traceback.format_exc()}')

    def stop_trading_loop(self):
        """트레이딩 루프 정지 (스레드 정지)"""
        try:
            logger = self._get_main_logger()
            # 🔥 Trader 거래 중지 및 모니터링 정리
            if hasattr(self, 'trader') and self.trader:
                try:
                    self.trader.stop_trading()
                    if logger:
                        logger.info("🔥 Trader 거래 중지 완료")
                except Exception as e:
                    if logger:
                        logger.error(f"🔥 Trader 거래 중지 오류: {e}")

            # 🔥 트레이딩 스레드 정지 (즉시 종료)
            if self.trading_thread and self.trading_thread.is_alive():
                # 워커에 즉시 정지 신호 전송
                if hasattr(self, 'trading_worker') and self.trading_worker:
                    self.trading_worker.stop()  # 🔥 중복 제거: stop_trading() → stop() 통합
                self.trading_thread.join(timeout=2)  # 🔥 2초로 단축 (즉시 종료 메커니즘으로)
                if self.trading_thread.is_alive():
                    if logger:
                        logger.warning("🔥 트레이딩 스레드 강제 종료")
                else:
                    if logger:
                        logger.info("🔥 트레이딩 루프 즉시 정지 (스레드 종료)")
            else:
                if logger:
                    logger.info("트레이딩 루프가 이미 정지됨")
        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                logger.error(f"트레이딩 루프 정지 오류: {e}")


    def select_trading_coins(self):
        """🔥 코인 선택 및 웹소켓 구독 관리"""
        logger = self._get_main_logger()
        try:
            if logger:
                logger.info("🔥 코인 선정 프로세스 시작")
                logger.info("=" * 60)
                logger.info("📊 1단계: 시장 상황 분석 시작")

            # 1) 시장 상황 분석 (trader.py에서 실제 분석 수행)
            market_regime = "normal"  # 기본값
            if hasattr(self, 'trader') and self.trader:
                try:
                    market_regime = self.trader._analyze_market_regime_binance_fast()
                    if logger:
                        logger.info(f"✅ 시장 상황 분석 완료: {market_regime}")
                except Exception as e:
                    if logger:
                        logger.warning(f"⚠️ 시장 상황 분석 실패, 기본값 사용: {e}")
                    market_regime = "normal"
            else:
                if logger:
                    logger.warning("⚠️ trader 객체 없음 - 기본 시장 상황 사용")

            # 2) 시장 상황에 따른 코인 수 결정
            settings = getattr(self, 'settings', {}) or {}
            market_coins_config = settings.get('market_regime_coins', {})
            regime_config = market_coins_config.get(market_regime, {})
            total_coins = int(regime_config.get('min', 15))

            # 🔥 동적 알트코인 비율 적용 (시장 상황별)
            coin_ratios = settings.get('coin_selection_ratios', {})
            regime_ratios = coin_ratios.get(market_regime, {'altcoin_ratio': 0.7, 'major_ratio': 0.3})
            num_alt = int(total_coins * regime_ratios['altcoin_ratio'])
            num_major = int(total_coins * regime_ratios['major_ratio'])

            if logger:
                logger.info(f"📈 시장 상황 '{market_regime}'에 따른 코인 선정 계획:")
                logger.info(f"   • 총 코인 수: {total_coins}개")
                logger.info(f"   • 알트코인: {num_alt}개 ({regime_ratios['altcoin_ratio']*100:.0f}%)")
                logger.info(f"   • 메이저 코인: {num_major}개 ({regime_ratios['major_ratio']*100:.0f}%)")

                # 🔥 설정 파일에서 설명 가져오기
                description = regime_ratios.get('description', f'📊 {market_regime}장')
                logger.info(f"   • 전략: {description}")
                logger.info("📊 3단계: Evaluator를 통한 코인 선택 실행")

            # 3) Evaluator로 코인 선택 (배치 처리)
            selected_coins = []
            evaluator = getattr(self, 'evaluator', None)
            if evaluator and hasattr(evaluator, 'select_trading_coins'):
                try:
                    if logger:
                        logger.info("🔄 코인 선택 실행 중... (UI 응답성 유지)")

                    # 🔥 디버깅: evaluator.select_trading_coins 호출 직전
                    logger.debug("main.py - evaluator.select_trading_coins() 호출 직전")

                    # UI 업데이트를 위한 짧은 지연 (제거 - 불필요한 지연)
                    # import time
                    # time.sleep(0.1)

                    selected_coins = evaluator.select_trading_coins(num_alt, num_major, market_regime) or []

                    # 🔥 디버깅: evaluator.select_trading_coins 호출 직후
                    logger.debug(f"main.py - evaluator.select_trading_coins() 반환 완료: {len(selected_coins)}개")

                    if logger:
                        logger.info("✅ 코인 선택 완료")

                except Exception as e_sel:
                    if logger:
                        logger.warning(f"코인 선택 실패(계속 진행): {e_sel}")

            # 4) 선택 결과 정규화 및 저장
            normalized_selected = []
            for c in selected_coins:
                if isinstance(c, dict):
                    normalized_selected.append(c)
                else:
                    normalized_selected.append({'symbol': str(c)})
            self.selected_coins = normalized_selected

            if not self.selected_coins:
                if logger:
                    logger.warning("⚠️ 선택된 코인이 없음")
                return

            if logger:
                logger.info(f"✅ 최종 선정된 코인: {len(self.selected_coins)}개")
                logger.info("🎯 선정된 코인:")

                # 중복 로그 제거 - evaluator.py에서 이미 상세한 코인 정보 로그를 생성함
                # 배치 처리로 코인 정보 출력 (UI 응답성 유지) - 간소화
                batch_size = 5  # 5개씩 배치 처리
                for i in range(0, len(self.selected_coins), batch_size):
                    batch = self.selected_coins[i:i+batch_size]
                    for j, coin in enumerate(batch):
                        try:
                            cdict = coin if isinstance(coin, dict) else {'symbol': str(coin)}
                            symbol = str(cdict.get('symbol', 'N/A'))
                            # 간단한 요약만 출력 (상세 정보는 evaluator.py에서 이미 로그됨)
                            log_event('system', f"   • {symbol}", exchange='binance')
                        except Exception as e_log:
                            logger.error(f"❌ 코인 정보 출력 오류 (인덱스 {i+j}): {e_log}")
                            logger.error(f"   문제 코인 데이터: {coin}")

                    # 배치 간 UI 업데이트를 위한 짧은 지연
                    if i + batch_size < len(self.selected_coins):
                        import time
                        time.sleep(0.05)  # 50ms 지연

            # 5) 대시보드 / UnifiedTrader 업데이트
            try:
                dashboard = getattr(self, 'dashboard', None)
                if dashboard and hasattr(dashboard, 'update_selected_coins'):
                    dashboard.update_selected_coins(self.selected_coins)
                    if logger:
                        logger.info("✅ 대시보드 코인 정보 업데이트 완료")
                else:
                    if logger:
                        logger.warning("⚠️ 대시보드가 초기화되지 않음")
            except Exception as e_db:
                if logger:
                    logger.warning(f"대시보드 업데이트 경고: {e_db}")

            try:
                unified_trader = getattr(self, 'unified_trader', None)
                if unified_trader and hasattr(unified_trader, 'set_selected_coins'):
                    unified_trader.set_selected_coins(self.selected_coins)
                    if logger:
                        logger.info("✅ UnifiedTrader 코인 정보 업데이트 완료")
                else:
                    if logger:
                        logger.warning("⚠️ UnifiedTrader가 초기화되지 않음")
            except Exception as e_ut:
                if logger:
                    logger.warning(f"UnifiedTrader 업데이트 경고: {e_ut}")

            # 6) API 기반 분석 (WebSocket 구독 제거)
            # 🔥 코인 분석은 API로 수행, WebSocket은 포지션 모니터링에만 사용
            if logger:
                logger.info("📊 4단계: API 기반 코인 분석 (WebSocket 구독 제거)")
            # WebSocket 구독 제거 - 분석은 API로 수행, WebSocket은 실제 포지션 진입 시에만 사용

            if logger:
                logger.info("📊 5단계: 각 코인 분석 및 신호 생성")

            # 7) 각 코인 분석 및 시그널 생성
            for coin in self.selected_coins:
                symbol = coin.get('symbol') if isinstance(coin, dict) else str(coin)
                try:
                    # 중복 로그 제거 - evaluator.py에서 이미 로그 생성됨

                    # 🔥 코인 선택 단계에서는 WebSocket 체크 불필요 - REST API만 사용
                    # WebSocket은 거래 실행 단계에서만 사용

                    # 중복 분석 제거 - 이미 위에서 분석 완료됨

                    # UI 응답성을 위한 짧은 지연
                    import time
                    time.sleep(0.1)  # 100ms 지연으로 변경
                except Exception as e_coin:
                    if logger:
                        logger.error(f"[{symbol}] Processing error: {e_coin}")
                    continue

            if logger:
                logger.info("No trading in all coins - while loop terminated")

        except Exception as e:
            if logger:
                logger.error(f"트레이딩 전략 실행 오류: {e}")

    def _save_analysis_to_database(self, coin_symbol: str, analysis_result, signal_str: str):
        """분석 결과를 데이터베이스에 저장"""
        try:
            if not hasattr(self, 'recorder') or not self.recorder:
                logger = self._get_main_logger()
                if logger:
                    logger.warning(f"[{coin_symbol}] recorder가 초기화되지 않아 데이터베이스 저장 생략")
                return

            # AnalysisResult에서 데이터 추출 (딕셔너리 접근 방식으로 수정)
            confidence = analysis_result.get('confidence', None)
            trend = str(analysis_result.get('trend', 'SIDEWAYS'))
            volatility = analysis_result.get('volatility', 0.0)
            reasoning = analysis_result.get('reason', 'N/A')

            # 🔥 indicators 존재 가정 버그 수정 - 안전한 방식으로 접근 (딕셔너리 접근 방식으로 수정)
            indicators = analysis_result.get('indicators', None)
            rsi = indicators.get('rsi', 50.0) if indicators else analysis_result.get('rsi', 50.0)
            macd = indicators.get('macd', 0.0) if indicators else analysis_result.get('macd', 0.0)
            sma_20 = indicators.get('sma_20', 0.0) if indicators else analysis_result.get('ma20', 0.0)
            sma_50 = indicators.get('sma_50', 0.0) if indicators else analysis_result.get('ma50', 0.0)
            bb_upper = indicators.get('bb_upper', 0.0) if indicators else 0.0
            bb_lower = indicators.get('bb_lower', 0.0) if indicators else 0.0
            volume_ratio = indicators.get('volume_ratio', 1.0) if indicators else 1.0

            # 데이터베이스에 저장
            query = """
            INSERT INTO analysis_log (
                symbol, signal, confidence, rsi, macd, sma_20, sma_50,
                bb_upper, bb_lower, volume_ratio, volatility, trend, reasoning, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            params = (
                coin_symbol, signal_str, confidence, rsi, macd, sma_20, sma_50,
                bb_upper, bb_lower, volume_ratio, volatility, trend, reasoning,
                datetime.now()
            )

            self.recorder.execute_query(query, params)
            # 개발용 로그 (사용자 대시보드에는 표시되지 않음)
            logger = self._get_main_logger()
            if logger:
                logger.debug(f"[{coin_symbol}] 분석 결과를 데이터베이스에 저장 완료")

        except Exception as e:
            logger = self._get_main_logger()
            if logger:
                logger.error(f"[{coin_symbol}] 데이터베이스 저장 오류: {e}")


    def _update_dashboard_analysis(self, coin: str, analysis_result, signal_str: str):
        """대시보드에 분석 결과 전달 (백엔드 데이터만 전달)"""
        safe_coin_symbol = None
        try:
            if hasattr(self, 'dashboard') and self.dashboard:
                # 🔥 coin이 딕셔너리인 경우 symbol만 추출하여 로그 출력
                if isinstance(coin, dict):
                    coin_symbol = coin.get('symbol', 'N/A')
                    overall_score = coin.get('overall_score', 0)
                    is_major = coin.get('is_major', False)
                else:
                    coin_symbol = str(coin)
                safe_coin_symbol = coin_symbol

                # 🔥 AnalysisResult 객체의 실제 존재하는 속성들 사용 (딕셔너리 접근 방식으로 수정)
                raw_confidence = analysis_result.get('confidence', None)

                # 🔥 evaluator에서 계산된 점수들을 모두 가져와서 저장 (딕셔너리 접근 방식으로 수정)
                analysis_data = {
                    'overall_score': analysis_result.get('overall_score', 'N/A'),
                    'technical_score': analysis_result.get('technical_score', 'N/A'),
                    'volatility_score': analysis_result.get('volatility_score', 'N/A'),
                    'volume_score': analysis_result.get('volume_score', 'N/A'),
                    'trend_score': analysis_result.get('trend_score', 'N/A'),
                    'risk_score': analysis_result.get('risk_score', 'N/A'),
                    'signal': signal_str,
                    'confidence': f"{raw_confidence:.0%}" if raw_confidence is not None else 'N/A',
                    'timestamp': analysis_result.get('timestamp', datetime.now()).strftime("%H:%M:%S") if analysis_result.get('timestamp') else 'N/A'
                }

                # 실시간 로그 탭에서 분석 결과 확인 가능
                logger = self._get_main_logger()
                if logger:
                    logger.info(f"[{coin_symbol}] 분석 완료 - 실시간 로그 탭에서 결과 확인")

                # 🔥 분석 완료 후 UI 업데이트 허용
                if hasattr(self, 'dashboard') and self.dashboard:
                    self.dashboard.update_idletasks()  # UI 업데이트 허용

        except Exception as e:
            tag = safe_coin_symbol if safe_coin_symbol else "UNKNOWN"
            logger = self._get_main_logger()
            if logger:
                logger.error(f"[{tag}] 대시보드 분석 결과 전달 오류: {e}")
            import traceback
            logger = self._get_main_logger()
            if logger:
                logger.error(traceback.format_exc())

    def handle_trading_signal(self, signal_data):
        logger = self._get_main_logger()

        # 유틸: 다양한 키 지원
        def _get_val(keys, default=None):
            if isinstance(signal_data, dict):
                for k in keys:
                    if k in signal_data and signal_data[k] is not None:
                        return signal_data[k]
            else:
                for k in keys:
                    try:
                        v = getattr(signal_data, k)
                        if v is not None:
                            return v
                    except Exception:
                        pass
            return default

        try:
            # 1) 데이터 추출 및 정규화
            symbol = _get_val(['symbol', 'ticker', 'coin', 'asset'])
            raw_signal = _get_val(['signal', 'action', 'side', 'type'], 'HOLD')
            confidence = _get_val(['confidence', 'score', 'prob', 'probability'], None)
            price = _get_val(['price', 'current_price'], None)
            reason = _get_val(['reason', 'reasoning', 'message', 'note'], None)
            ts = _get_val(['timestamp', 'time'], None)

            # 타입/기본값 보정
            symbol = str(symbol).upper().strip() if symbol else None
            signal_str = str(raw_signal).upper().strip() if raw_signal else 'HOLD'

            # LONG/SHORT 등 매핑
            if signal_str == 'LONG':
                signal_str = 'BUY'
            elif signal_str == 'SHORT':
                signal_str = 'SELL'
            elif signal_str in {'EXIT', 'CLOSE'}:
                # 내부적으로는 'HOLD'로 처리(포지션 종료 의사 전달일 수 있음)
                signal_str = 'HOLD'

            # 유효성 검사
            if not symbol or signal_str not in {'BUY', 'SELL', 'HOLD'}:
                if logger:
                    logger.warning(f"무시된 신호(형식 오류) - symbol:{symbol}, signal:{signal_str}")
                return False

            # 타임스탬프 정규화
            if ts is None:
                timestamp_dt = datetime.now()
            else:
                try:
                    # epoch(초/밀리초) 숫자인 경우 처리
                    if isinstance(ts, (int, float)):
                        # 밀리초 범위면 초로 환산
                        if ts > 1e12:
                            ts = ts / 1000.0
                        timestamp_dt = datetime.fromtimestamp(ts)
                    else:
                        # datetime 또는 문자열은 최대한 보정
                        if isinstance(ts, str):
                            # 흔한 포맷 시도, 실패시 now
                            try:
                                timestamp_dt = datetime.fromisoformat(ts)
                            except Exception:
                                timestamp_dt = datetime.now()
                        else:
                            timestamp_dt = ts if hasattr(ts, 'isoformat') else datetime.now()
                except Exception:
                    timestamp_dt = datetime.now()

            # confidence/price 숫자 보정
            try:
                confidence = float(confidence) if confidence is not None else None
            except Exception:
                confidence = None
            try:
                price = float(price) if price is not None else None
            except Exception:
                price = None

            normalized = {
                'symbol': symbol,
                'signal': signal_str,
                'confidence': confidence,
                'price': price,
                'reason': reason,
                'timestamp': timestamp_dt,
                'raw': signal_data
            }

            if logger:
                logger.info(f"📥 트레이딩 신호 수신: {normalized}")

            # 2) 최근 신호/구독 유지 힌트 기록(5분)
            try:
                self._recent_signals = getattr(self, '_recent_signals', {})
                self._recent_signals[symbol] = {
                    'timestamp': timestamp_dt,
                    'signal': signal_str,
                    'confidence': confidence,
                    'price': price,
                }
                self._keep_subscription_until = getattr(self, '_keep_subscription_until', {})
                self._keep_subscription_until[symbol] = time.time() + 300  # 5분 유지
            except Exception as e_meta:
                if logger:
                    logger.debug(f"신호 메타 기록 중 경고: {e_meta}")

            # 3) 트레이더/유니파이드트레이더에 전달(존재/메서드 확인 후 안전 호출)
            handled = False

            trader = getattr(self, 'trader', None)
            if trader:
                for m in ('handle_signal', 'on_signal', 'process_signal'):
                    if hasattr(trader, m):
                        try:
                            getattr(trader, m)(normalized)
                            handled = True
                            if logger:
                                logger.info(f"✅ Trader.{m} 처리 완료: {symbol} {signal_str}")
                            break
                        except Exception as e_tr:
                            if logger:
                                logger.warning(f"Trader.{m} 처리 중 오류: {e_tr}")

            if not handled:
                unified = getattr(self, 'unified_trader', None)
                if unified:
                    for m in ('handle_signal', 'on_signal', 'process_signal'):
                        if hasattr(unified, m):
                            try:
                                getattr(unified, m)(normalized)
                                handled = True
                                if logger:
                                    logger.info(f"✅ UnifiedTrader.{m} 처리 완료: {symbol} {signal_str}")
                                break
                            except Exception as e_ut:
                                if logger:
                                    logger.warning(f"UnifiedTrader.{m} 처리 중 오류: {e_ut}")

            if not handled and logger:
                logger.info("ℹ️ 신호를 처리할 트레이더 핸들러가 없어 로그만 기록했습니다.")

            # 5) 대시보드 알림(선택)
            try:
                dashboard = getattr(self, 'dashboard', None)
                if dashboard and hasattr(dashboard, 'update_status_info'):
                    dashboard.update_status_info()
            except Exception:
                pass

            return True

        except Exception as e:
            if logger:
                logger.error(f"❌ 트레이딩 신호 처리 오류: {e}")
                try:
                    import traceback
                    logger.error(traceback.format_exc())
                except Exception:
                    pass
            return False

    def stop_trading(self):
        """전체 트레이딩 정지(안전 종료)"""
        logger = self._get_main_logger()
        try:
            if logger:
                logger.info("⏹️ 트레이딩 전체 정지 요청 수신")

            # 1) 트레이딩 루프/워커/트레이더 안전 정지
            try:
                if hasattr(self, 'stop_trading_loop'):
                    self.stop_trading_loop()  # 내부에서 trader.stop_trading(), 스레드 join 처리
            except Exception as e_loop:
                if logger:
                    logger.warning(f"트레이딩 루프 정지 중 경고: {e_loop}")

            # 2) 웹소켓 구독 정리(기본 심볼은 유지)
            try:
                binance_client = getattr(self, 'binance_client', None)
                if binance_client and hasattr(binance_client, 'websocket_manager'):
                    wm = binance_client.websocket_manager
                    active = set(getattr(wm, 'active_subscriptions', set()) or [])
                    for sym in list(active):
                        su = str(sym).upper()
                        # 심볼별 구독 해제 (있을 때만)
                        try:
                            if hasattr(wm, 'unsubscribe_symbol_depth'):
                                wm.unsubscribe_symbol_depth(su)
                        except Exception:
                            pass
                        try:
                            if hasattr(wm, 'unsubscribe_symbol_ticker'):
                                wm.unsubscribe_symbol_ticker(su)
                        except Exception:
                            pass
                    if logger:
                        logger.info("🧹 웹소켓 구독 정리 완료(기본 심볼 제외)")
            except Exception as e_ws:
                if logger:
                    logger.debug(f"웹소켓 구독 정리 중 경고: {e_ws}")

            # 3) 대시보드 상태 갱신
            try:
                if hasattr(self, 'dashboard') and self.dashboard:
                    # 자동거래 토글 꺼짐 반영 - ModernDashboard 방식 사용
                    self.dashboard.is_auto_trading = False
                    if hasattr(self.dashboard, 'update_status_display'):
                        self.dashboard.update_status_display(force_refresh=True)
                    elif hasattr(self.dashboard, 'update_status_info'):
                        self.dashboard.update_status_info()
            except Exception:
                pass

            # 4) 내부 상태/힌트 초기화(선택)
            try:
                if hasattr(self, '_recent_signals'):
                    self._recent_signals.clear()
                if hasattr(self, '_keep_subscription_until'):
                    self._keep_subscription_until.clear()
            except Exception:
                pass

            if logger:
                logger.info("✅ 트레이딩 정지 완료")
            return True

        except Exception as e:
            if logger:
                logger.error(f"❌ 트레이딩 정지 처리 오류: {e}")
                try:
                    import traceback
                    logger.error(traceback.format_exc())
                except Exception:
                    pass
        return False

    # 🔥 사용되지 않는 거래 실행 함수들 제거됨 (2025-10-20):
    # - _execute_trading_signal() (라인 2975-2988): 정의만 있고 실제로 호출되지 않음
    # - _execute_binance_trade() (라인 2990-3015): 위 함수에서만 호출됨
    # - _execute_unified_trade() (라인 3017-3033): 위 함수에서만 호출됨
    #
    # 현재 실제 사용되는 거래 실행 경로:
    # TradingWorker → trader.execute_trading_cycle → execute_trades (직접 호출)
    #
    # 삭제 이유:
    # 1. 어디서도 호출되지 않는 데드 코드
    # 2. trader.py의 execute_trade, handle_trading_signal 함수가 이미 삭제됨
    # 3. 동일한 기능을 TradingWorker가 수행함
    # 4. 코드 중복 제거 및 혼란 방지

def main():
    try:
        app = NoahAIClient()
        app.start()
    except Exception as e:
        try:
            import logging
            logger = logging.getLogger("NoahAI")
            logger.critical(f"메인 실행 중 치명적인 오류 발생: {e}")
        except:
            print(f"CRITICAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
