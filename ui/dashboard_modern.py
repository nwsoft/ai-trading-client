#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modern Dashboard - CustomTkinter 기반
실시간 코인 목록, 포지션 상태, 수익률 표시
"""

import sys
import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
import math
import threading
import time
import queue
from typing import List, Dict, Any, Optional, Tuple, Callable, cast
import webbrowser

# CustomTkinter imports
import customtkinter as ctk
from customtkinter import CTkScrollableFrame
from tkinter import messagebox
import tkinter as tk

# 고정 스킨 - 테마 시스템 제거됨 (2025-10-29)
from utils.fixed_colors import FIXED_COLORS as _FIXED_COLORS, build_widget_palette

# corner_radius 강제 적용 커스텀 위젯
from ui.custom_widgets import RoundedButton, RoundedFrame, create_rounded_button
from ui.visual_system import get_ui_icon, style_tabview
from ui.refresh_lifecycle import schedule_visible_refresh
from ui.widget_lifecycle import (
    cleanup_widget_tree,
    delete_ctk_tab,
    log_windows_gui_resources,
    reorder_ctk_tabs,
    WidgetOwnershipRegistry,
    widget_is_alive,
)
from ui.controllers.account_state_controller import (
    AccountPanelResult,
    account_panel_error,
    account_panel_unavailable,
    build_account_panel_result,
    get_exchange_account_contract,
    normalize_spot_holdings,
    select_paper_position_store,
    summarize_paper_positions,
)

try:
    from PIL import Image, ImageDraw
except Exception:
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore

# CustomTkinter TclError 방지를 위한 안전한 접근법
# 전역 메서드 교체 대신 애플리케이션 레벨에서 처리

# --- 고정 스타일 모드(하드코딩 스킨) -------------------------------------------
# 테마 시스템을 사용하지 않고, 중앙 상수(utils.fixed_colors.FIXED_COLORS)만 사용합니다.
STRICT_FIXED_STYLE = True


# 모듈 내 print() 호출을 로거로 리다이렉트하여 표준 출력 사용을 제거
def _print_to_logger(*args, **kwargs):
    try:
        sep = kwargs.get('sep', ' ')
        end = kwargs.get('end', '')
        level = str(kwargs.get('level', 'INFO')).lower()
        message = sep.join(str(a) for a in args) + end
        # Unicode 문자를 안전하게 인코딩
        try:
            message = message.encode('utf-8', errors='ignore').decode('utf-8')
        except Exception:
            pass
        logger = logging.getLogger(__name__)
        log_fn = getattr(logger, level, logger.info)
        log_fn(message)
    except Exception:
        # 최후 폴백: 표준 로깅으로 정보 레벨 출력
        try:
            msg = " ".join(str(a) for a in args)
            try:
                msg = msg.encode('utf-8', errors='ignore').decode('utf-8')
            except Exception:
                pass
            logging.getLogger(__name__).info(msg)
        except Exception:
            pass

# 이 모듈 범위 내에서만 내장 print를 덮어씁니다.
print = _print_to_logger  # type: ignore

# Theme system 완전 제거 - 하드코딩 사용

# 기존 모듈 imports
from trading.ai_report_manager import AIReportManager
from trading.unified_trading_manager import UnifiedTradingManager
from trading.exchanges.exchange_factory import ExchangeFactory
from config.app_version import (
    DASHBOARD_TITLE,
    RELEASE_BUILD_LABEL,
    RELEASE_HIGHLIGHT,
    RELEASE_NOTICE_ID,
    RELEASE_PATCH,
    RELEASE_VERSION,
)
from ui.live_trading_guidance import build_live_trading_summary

"""
대시보드에서 사용하는 실제 위젯 모듈 임포트 (디버그 필터 제거)
"""
# AI 학습 위젯은 import 시 부작용 가능성이 있어 지연 로드합니다 (메서드 내부에서 import).
AILearningWidgetSafe = None  # 런타임에 _ensure_ai_learning_tab 내부에서 안전하게 로드
from ui.widgets.ai_report_widget import AIReportWidget
from ui.widgets.ai_assistant_widget import AIAssistantWidget
from ui.widgets.user_manual_widget import UserManualWidget

# Alpha Arena 위젯 (선택적 import)
try:
    from ui.widgets.alpha_arena_widget import AlphaArenaWidget
except ImportError:
    AlphaArenaWidget = None  # type: ignore

# 선택 위젯(존재하지 않을 수 있음)은 안전하게 임포트
try:
    from ui.widgets.chart_screenshot_widget import ChartScreenshotWidget  # 선택
except Exception:
    ChartScreenshotWidget = None  # type: ignore

try:
    from ui.widgets.life_finance_widget import LifeFinanceWidget
except Exception:
    LifeFinanceWidget = None  # type: ignore

# 사용자 상태 관리 모듈
try:
    from user_status_manager import UserStatusManager, get_status_manager
    try:
        from log_system.log_adapter import log_event
        log_event('system', '사용자 상태 관리 모듈 로드 완료')
    except Exception:
        logging.getLogger(__name__).info("사용자 상태 관리 모듈 로드 완료")
except ImportError as e:
    try:
        from log_system.log_adapter import log_event
        log_event('system', f'사용자 상태 관리 모듈 로드 실패: {e}', level='WARNING')
    except Exception:
        logging.getLogger(__name__).warning(f"사용자 상태 관리 모듈 로드 실패: {e}")
    UserStatusManager = None
    get_status_manager = None


class ModernDashboard(ctk.CTk):
    """Modern Dashboard - CustomTkinter 기반"""

    def __init__(self, settings, exchange_manager=None, main_app=None, unified_trader=None):
        import os
        print(f"[FILE CHECK] dashboard_modern.py 경로: {os.path.abspath(__file__)}")
        print("DEBUG ModernDashboard __init__ start")
        # CustomTkinter 5.1.3 - dark 모드에서 corner_radius 정상 작동!
        print("CustomTkinter 5.1.3 사용 중 - corner_radius 정상")
        super().__init__()
        try:
            from ui.typography import configure_platform_typography
            from utils.runtime_stability import install_tk_exception_hook

            configure_platform_typography(self)
            install_tk_exception_hook(self)
        except Exception:
            pass
        # 최상위 창 배경을 명확히 지정하여 하위 프레임의 라운드가 시각적으로 드러나도록 함
        try:
            self.configure(fg_color=self._color('background', '#050a13'))
        except Exception:
            pass

        # UI 업데이트 시스템 (간단한 방식)

        # 정적 분석기(Pylance) 경고 감소를 위한 주요 속성 타입 선언 및 초기화
        self.tab_widget: Optional[ctk.CTkTabview] = None
        self.tabview: Optional[ctk.CTkTabview] = None  # 호환용 별칭
        self.realtime_log_widget: Optional[Any] = None
        self.ai_report_widget: Optional[Any] = None
        self.trading_control_widget: Optional[Any] = None
        self.trading_status_label: Optional[ctk.CTkLabel] = None
        self._settings_window: Optional[Any] = None
        self.status_manager: Optional[Any] = None
        self.user_status_manager: Optional[Any] = None  # 구이름 호환
        self.unified_trader: Optional[Any] = unified_trader
        self.unified_manager: Optional[Any] = None
        # 추가: 정적 분석 경고 감소용 선택 속성들
        self.show_signals_only: Optional[Any] = None
        self.show_analysis_only: Optional[Any] = None
        self.show_all_logs: Optional[Any] = None
        self.start_stop_btn: Optional[ctk.CTkButton] = None
        self.ai_learning_widget: Optional[Any] = None
        self.analytics_summary_label: Optional[ctk.CTkLabel] = None
        self.ai_assistant_widget: Optional[Any] = None
        # 위젯/스크롤러 안전 선언 (정적 분석 경고 감소)
        self.evaluator_scroll: Optional[Any] = None
        self.trading_stats_scroll: Optional[Any] = None
        self.demo_widget: Optional[Any] = None
        # main.py에서 주입되는 선택 속성들 (정적분석 경고 방지용)
        self.api_signal_manager: Optional[Any] = None
        self.optimizer: Optional[Any] = None
        self.ai_manager: Optional[Any] = None
        self.risk_manager: Optional[Any] = None
        self.market_state_analyzer: Optional[Any] = None
        self._manual_widget: Optional[Any] = None
        self.chart_action_btn: Optional[ctk.CTkButton] = None
        self.optimize_action_btn: Optional[ctk.CTkButton] = None
        self.optimize_apply_action_btn: Optional[ctk.CTkButton] = None
        self.manual_action_btn: Optional[ctk.CTkButton] = None
        self._chart_widget_modal: Optional[Any] = None
        self._chart_widget: Optional[Any] = None
        self._icon_cache: Dict[str, Optional[ctk.CTkImage]] = {}

        # 기본 설정
        self.settings = settings
        self.exchange_manager = exchange_manager

        # 통합 거래 매니저 재사용(가능 시) 또는 초기화
        if main_app and hasattr(main_app, 'unified_manager') and main_app.unified_manager:
            self.unified_manager = main_app.unified_manager
        else:
            self.unified_manager = UnifiedTradingManager(settings)

        # 거래소별 탭 관리
        self.exchange_tabs = {}
        self.current_exchange_tab = None

        self.main_app: Optional[Any] = main_app  # main.py 인스턴스 참조 (정적 분석 안전)
        self.binance_client = None  # 하위 호환성을 위해 유지
        self.backend_api = None

        # 증권사별 어댑터 캐시 (단일 인스턴스 재사용)
        self.stock_adapters: Dict[str, Optional[Any]] = {
            'kiwoom': None,
            'shinhan': None,
            'miraeAsset': None,
            'koreaInvestment': None,
        }

        # 상태정보 캐시 (API 호출 최적화)
        self.status_cache = {
            'active_positions': 0,
            'today_trades': 0,
            'last_update': None,
            'cache_duration': 30  # 30초 캐시
        }

        # 고정 스킨: 테마 관리자 제거됨 (2025-10-29)
        # ThemeManager 대신 FIXED_COLORS 직접 사용
        self._themable_widgets = []

        # 자동거래 상태
        self.is_auto_trading = False
        self.selected_coins = []
        self.after_jobs = []  # after() 작업 추적
        self._is_destroying = False  # 종료 플래그
        self._stock_auto_loop_running = False
        # 상용 UI 디스패처 계약:
        # - 무제한 큐를 금지해 느린 렌더링 시 메모리 증가를 막는다.
        # - 동일 키 콜백은 최신 값 하나로 병합한다.
        # - 거래소/증권사 조회는 파괴되는 탭이 아니라 대시보드 전역에서 중복 억제한다.
        self._ui_call_queue: "queue.Queue[Any]" = queue.Queue(maxsize=1024)
        self._ui_coalesced_calls: Dict[str, Callable[[], None]] = {}
        self._ui_coalesce_lock = threading.Lock()
        self._ui_dispatch_metrics = {"queued": 0, "coalesced": 0, "dropped": 0}
        self._global_async_refresh_registry: Dict[str, Dict[str, Any]] = {}
        # 동적 탭의 화면 트리와 대시보드 캐시 참조는 반드시 함께 폐기한다.
        # 개별 탭 이름을 하드코딩한 무효화 목록 대신 모든 캐시 위젯이 이
        # 단일 소유권 레지스트리를 통과한다.
        self._widget_ownership = WidgetOwnershipRegistry()

        # 계단식 탭 구조: 서비스별 하위 탭 관리
        self.service_sub_tabs = {
            'blockchain': {},  # 거래소별 탭 레퍼런스 보관
            'stock': {},       # 증권사별 탭 레퍼런스 (미래 확장)
            'real_estate': {}  # 지역별 탭 레퍼런스 (미래 확장)
        }

        # 설정에서 활성화된 거래소 목록 (초기 로드; 이후 변경 시 refresh 메서드로 갱신)
        self.enabled_exchanges = self.settings.get('enabled_exchanges', ['binance'])
        # 런타임 실행 중인 거래소 추적 (Tri-State 전역 컨트롤용)
        self._running_exchanges: set[str] = set()
        # 거래소 상태 라벨 저장소 {exchange: CTkLabel}
        self._exchange_status_labels: dict[str, ctk.CTkLabel] = {}
        # AI 실행 이력/요약 카드 상태
        self.max_ai_execute_history_size: int = 30
        from ui.ai_activity import AIActivityLedger
        self._ai_activity_ledger = AIActivityLedger(self.max_ai_execute_history_size)
        self.ai_execute_history = self._ai_activity_ledger.events
        self._ai_execute_history_lock = self._ai_activity_ledger.lock
        self.ai_execute_summary_label: Optional[ctk.CTkLabel] = None
        # 자산 통합은 종료 거래 체결금액이 아니라 계좌 화면에서 이미
        # 수신한 현재 잔고를 정본으로 사용한다. 통화별로 보관해 KRW/USDT를
        # 환율 없이 임의 합산하지 않는다.
        from ui.asset_insight_data import AssetSnapshotStore
        self._asset_snapshot_store = AssetSnapshotStore()
        self._asset_balance_snapshot_at: Optional[datetime] = None
        self._asset_insight_refresh_inflight = False
        self._asset_insight_refresh_attempt_at = 0.0
        # 성능 최적화: 진단 결과 캐시 (설정이 바뀌지 않으면 재사용)
        self._diagnosis_cache: Optional[List[str]] = None
        self._diagnosis_cache_settings_hash: Optional[int] = None
        self._exchange_toggle_buttons: dict[str, ctk.CTkButton] = {}
        # 거래소 런타임 상태 맵 (토글 버튼 색상 계산용)
        self._exchange_running: dict[str, bool] = {}
        self._replay_position_timeline: Dict[str, Dict[str, Any]] = {}

        # 거래소별 섹션 위젯 레퍼런스 저장소
        self.exchange_section_widgets = {}  # {exchange: {balance_label, positions_text, stats_label}}

        # CustomTkinter 5.2.2의 DPI 스케일링 오류는 라이브러리 자체 문제
        # 이 오류들은 실제 기능에 영향을 주지 않으므로 무시
        self.last_dynamic_check = datetime.now()

        # CustomTkinter 내부 메서드 패치 제거 (2025-10-30)
        # 과거 monkey patch가 둥근 모서리와 텍스트 렌더링을 깨뜨렸으므로 완전히 제거합니다.
        self._last_symbols = []

        # AI 리포트 매니저 초기화
        self.ai_report_manager = AIReportManager(report_interval=300)

        # 설정 변경 이력 추적
        self.settings_change_history = []
        self.max_history_size = 50

        # 사용자 상태 관리자 초기화
        self._init_user_status_manager()

        # 로거 설정
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        # UI 초기화
        self.init_ui()

        # 백그라운드 스레드에서 들어온 UI 반영 콜백을 메인 스레드에서 안전하게 실행
        try:
            self.safe_after(50, self._drain_ui_call_queue)
        except Exception:
            pass

        # 거래소 정보 업데이트
        self.update_exchange_info()
        try:
            if (
                "trade_enabled_exchanges" in self.settings
                and not list(self.settings.get("trade_enabled_exchanges") or [])
                and list(self.settings.get("enabled_exchanges") or [])
            ):
                self.safe_after(
                    1800,
                    self._show_toast,
                    "모든 활성 거래소가 학습 전용입니다. 시작하면 분석·학습은 실행되고 신규 실주문은 차단됩니다.",
                    8000,
                )
        except Exception:
            pass

        # 초기화 중 거래소/탭 재구성 순서에 따라 동적 탭의 자식이 비는 경우를
        # 막기 위해 전체 UI 구성이 끝난 뒤 현재 서비스 화면을 한 번 더 보장한다.
        try:
            self.safe_after(1500, self._ensure_current_financial_intelligence_content)
        except Exception:
            pass

        # _apply_theme_palette 제거됨 - 고정 스킨 사용으로 불필요

        # 타이머 설정
        self.setup_timers()

        # Auto 모드: 시작 시 1회 자동 튜닝 시도(데이터 있으면)
        try:
            op_mode = str(self.settings.get('operation_mode', 'guided')).lower() if isinstance(self.settings, dict) else 'guided'
            if op_mode == 'auto':
                from path_utils import get_db_file_path
                if os.path.exists(get_db_file_path()):
                    from trading.tuning_manager import TuningManager
                    tm = TuningManager(self.settings)
                    tm.apply_recommendations(get_db_file_path(), list(self.enabled_exchanges or []))
        except Exception:
            pass

        try:
            from log_system.log_adapter import log_event
            log_event('system', 'Modern Dashboard 초기화 완료')
        except Exception:
            self.logger.info("Modern Dashboard 초기화 완료")

        # 사용자 상태 모니터링 시작 (초기화 완료 후)
        self.start_user_status_monitoring()

    # 내부 디버그 로깅 (settings.debug_dashboard True일 때만)
    def _dbg(self, msg: str):
        try:
            if bool(self.settings.get('debug_dashboard', False)):
                from log_system.log_adapter import log_event
                log_event('system', msg, level='DEBUG')
        except Exception:
            pass

    # --- 안전 유틸리티: 파괴된 위젯 접근 방지 ---
    def _widget_alive(self, widget: Optional[Any]) -> bool:
        return widget_is_alive(widget) and not getattr(self, '_is_destroying', False)

    def _safe_text_set(self, text_widget: Optional[Any], content: str) -> None:
        try:
            if not self._widget_alive(text_widget):
                return
            tw = cast(ctk.CTkTextbox, text_widget)
            state = getattr(tw, '_state', None)
            try:
                tw.configure(state='normal')
            except Exception:
                pass
            try:
                tw.delete('1.0', 'end')
                tw.insert('1.0', content)
            except Exception:
                pass
            try:
                tw.configure(state=state or 'disabled')
            except Exception:
                pass
        except Exception:
            pass

    # --- 색상 헬퍼 메서드 ---------------------------------------------------
    @staticmethod
    def _shade_color(hex_color: str, factor: float = 0.85) -> str:
        try:
            color = hex_color.lstrip('#')
            if len(color) != 6:
                return hex_color
            r = max(0, min(255, int(int(color[0:2], 16) * factor)))
            g = max(0, min(255, int(int(color[2:4], 16) * factor)))
            b = max(0, min(255, int(int(color[4:6], 16) * factor)))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color

    def _hover_from(self, color_hex: str, factor: float = 0.85) -> str:
        return self._shade_color(color_hex, factor)


    def _measure_button_width(self, text: str, pad: int = 42, minw: int = 150, maxw: int = 280) -> int:
        """Compute a consistent width for CTkButtons that adapts to font metrics."""
        try:
            font = getattr(self, '_start_button_font', None)
            if font and hasattr(font, 'measure'):
                width = font.measure(text)
            else:
                raise AttributeError
        except Exception:
            width = max(len(text) * 10, minw)
        return max(minw, min(maxw, int(width + pad)))


    def _get_icon(self, name: str, size: Tuple[int, int] = (22, 22)) -> Optional[ctk.CTkImage]:
        """Build or retrieve a simple themed icon for buttons."""
        try:
            accent_color = self._color('accent', '#8b5cf6')
            success_color = self._color('success', '#22c55e')
            danger_color = self._color('danger', '#ef4444')
            secondary_color = self._color('button_secondary', '#4a6a8f')
            text_color = self._color('text_primary', '#f9fafb')
            cache_key = f"{name}:{size[0]}x{size[1]}:{accent_color}:{success_color}:{danger_color}:{secondary_color}:{text_color}"
            cached = self._icon_cache.get(cache_key)
            if cached is not None:
                return cached

            shared_icon = get_ui_icon(name, size=size, color=text_color)
            if shared_icon is not None:
                self._icon_cache[cache_key] = shared_icon
                return shared_icon

            if Image is None or ImageDraw is None:
                self._icon_cache[cache_key] = None
                return None

            img = Image.new("RGBA", size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            w, h = size
            inset = max(2, int(min(w, h) * 0.12))

            if name in ('play', 'resume'):
                draw.ellipse([inset, inset, w - inset, h - inset], fill=success_color)
                triangle = [
                    (w * 0.45, h * 0.32),
                    (w * 0.45, h * 0.68),
                    (w * 0.72, h * 0.50),
                ]
                draw.polygon(triangle, fill="#ffffff")
            elif name == 'stop':
                draw.rounded_rectangle([inset, inset, w - inset, h - inset], radius=int(min(w, h) * 0.2), fill=danger_color)
                square_inset = w * 0.32
                draw.rectangle([square_inset, square_inset, w - square_inset, h - square_inset], fill="#ffffff")
            elif name in ('settings', 'gear'):
                draw.ellipse([inset, inset, w - inset, h - inset], fill=secondary_color)
                inner_radius_start = w * 0.35
                inner_radius_end = w * 0.65
                draw.ellipse([inner_radius_start, inner_radius_start, inner_radius_end, inner_radius_end], fill="#ffffff")
                bar_len = min(w, h) * 0.42
                bar_width = max(2, int(min(w, h) * 0.12))
                center = (w / 2, h / 2)
                for angle_deg in (0, 60, 120):
                    angle_rad = math.radians(angle_deg)
                    dx = (bar_len / 2) * math.cos(angle_rad)
                    dy = (bar_len / 2) * math.sin(angle_rad)
                    x0 = center[0] + dx - bar_width / 2
                    y0 = center[1] + dy - bar_width / 2
                    draw.rectangle([x0, y0, x0 + bar_width, y0 + bar_width], fill=secondary_color)
                    x1 = center[0] - dx - bar_width / 2
                    y1 = center[1] - dy - bar_width / 2
                    draw.rectangle([x1, y1, x1 + bar_width, y1 + bar_width], fill=secondary_color)
            elif name in ('chart', 'analytics'):
                draw.rounded_rectangle([inset, inset, w - inset, h - inset], radius=int(min(w, h) * 0.2), fill=accent_color)
                points = [
                    (w * 0.2, h * 0.7),
                    (w * 0.45, h * 0.45),
                    (w * 0.65, h * 0.55),
                    (w * 0.8, h * 0.3),
                ]
                draw.line(points, fill="#ffffff", width=max(2, int(min(w, h) * 0.08)))
                for px, py in points:
                    draw.ellipse([px - 1.5, py - 1.5, px + 1.5, py + 1.5], fill="#ffffff")
            elif name in ('manual', 'book'):
                draw.rounded_rectangle([inset, inset, w - inset, h - inset], radius=int(min(w, h) * 0.2), fill=secondary_color)
                draw.rectangle([w * 0.28, h * 0.2, w * 0.32, h * 0.8], fill=text_color)
                draw.rectangle([w * 0.52, h * 0.2, w * 0.56, h * 0.8], fill=text_color)
                draw.rectangle([w * 0.32, h * 0.2, w * 0.52, h * 0.28], fill=text_color)
            else:
                draw.rounded_rectangle([inset, inset, w - inset, h - inset], radius=int(min(w, h) * 0.22), fill=accent_color)

            icon = ctk.CTkImage(light_image=img, dark_image=img, size=size)
            self._icon_cache[cache_key] = icon
            return icon
        except Exception:
            # 아이콘 생성 실패 시 캐싱 없이 None 반환
            return None

    def _refresh_start_button_appearance(self) -> None:
        """Sync the global start button with the current run state and theme."""
        try:
            btn = getattr(self, 'start_stop_btn', None)
            if not btn:
                return
            enabled = set(self.enabled_exchanges)
            running = set(self._running_exchanges)

            # 활성 거래소가 1개 이하면 전체 제어 의미가 약하므로 비활성화
            if len(enabled) <= 1:
                disabled_text = "전체 제어(2개 이상)"
                muted_fg = self._color('muted', '#475569')
                btn.configure(
                    state='disabled',
                    text=disabled_text,
                    width=self._measure_button_width(disabled_text),
                    fg_color=muted_fg,
                    hover_color=muted_fg,
                    corner_radius=10,
                )
                return

            if not enabled or not running:
                mode = 'start'
                text = "전체 시작"
            elif running == enabled:
                mode = 'stop'
                text = "전체 정지"
            else:
                mode = 'resume'
                text = "미실행 시작"

            primary_blue = self._color('button_primary', '#2563eb')
            stop_color = self._color('danger', '#ef4444')
            fg_color = primary_blue if mode in ('start', 'resume') else stop_color
            hover_color = (
                self._color('button_primary_hover', self._hover_from(primary_blue, 0.92))
                if mode in ('start', 'resume') else self._hover_from(stop_color, 0.92)
            )
            btn.configure(
                state='normal',
                text=text,
                width=self._measure_button_width(text),
                fg_color=fg_color,
                hover_color=hover_color,
                corner_radius=10  # 로그인과 동일
            )
        except Exception:
            pass

    def _assess_ai_execute_risk(self) -> tuple[str, list[str]]:
        """AI 실행 전 위험 조건을 점검해 위험 레벨과 사유를 반환한다."""
        settings_obj = self.settings if isinstance(self.settings, dict) else {}
        reasons: list[str] = []
        level = 'normal'

        # 실주문 플래그 점검 (고위험 조건)
        global_live = bool(settings_obj.get('enable_stock_live_order', False))
        broker_configs = settings_obj.get('stock_broker_configs', {})
        any_broker_live = False
        if isinstance(broker_configs, dict):
            for cfg in broker_configs.values():
                if isinstance(cfg, dict) and bool(cfg.get('allow_live_order', False)):
                    any_broker_live = True
                    break

        if global_live and any_broker_live:
            level = 'high'
            reasons.append('실주문 허용 플래그가 활성화되어 실제 주문 경로가 열려 있습니다.')

        # 자동매매 위험 정책 점검
        stock_auto = settings_obj.get('stock_auto_trading', {})
        if isinstance(stock_auto, dict):
            if not bool(stock_auto.get('risk_guard_enabled', True)) and level != 'high':
                level = 'elevated'
                reasons.append('risk_guard_enabled가 꺼져 있어 손실 방어가 약화될 수 있습니다.')

        return level, reasons

    def _diagnose_ai_execute_readiness(self, live_check: bool = True) -> list[str]:
        """AI 실행 전 준비도(연결/설정/API 조합) 점검 결과를 생성한다.

        성능 최적화:
        - 설정이 변경되지 않았으면 캐시된 결과를 즉시 반환한다 (반복 클릭 시 빠름).
                - live_check=True일 때만 거래소 실연결 검증을 수행한다.
                - 설정 창 진입 경로에서는 live_check=False(빠른 점검)로 UI 응답성을 우선한다.
        """
        import concurrent.futures

        settings_obj = self.settings if isinstance(self.settings, dict) else {}

        # ── 캐시 적중 여부 확인 ───────────────────────────────────────────────
        try:
            # 설정의 간단한 해시로 변경 여부 감지
            _cache_key_parts = (
                str(sorted(getattr(self, 'enabled_exchanges', []) or [])),
                str(sorted(settings_obj.get('enabled_stock_brokers', []) or [])),
                str(settings_obj.get('stock_broker_configs', {})),
            )
            current_hash = hash(_cache_key_parts)
            if (
                getattr(self, '_diagnosis_cache', None) is not None
                and getattr(self, '_diagnosis_cache_settings_hash', None) == current_hash
            ):
                return list(self._diagnosis_cache)
        except Exception:
            pass  # 해시 실패 시 캐시 무시하고 재진단

        lines: list[str] = []

        # ── 거래소 연결 준비도 (병렬 체크) ───────────────────────────────────
        enabled_exchanges = list(getattr(self, 'enabled_exchanges', []) or [])
        if enabled_exchanges and getattr(self, 'exchange_manager', None):
            if not live_check:
                for ex in enabled_exchanges:
                    key_ready = False
                    try:
                        if hasattr(self, 'main_app') and self.main_app and hasattr(self.main_app, '_validate_exchange_keys'):
                            key_ready = bool(self.main_app._validate_exchange_keys(ex))
                        else:
                            api = str(settings_obj.get(f"{ex}_api_key", '') or '').strip()
                            sec = str(settings_obj.get(f"{ex}_secret_key", '') or '').strip()
                            key_ready = bool(api and sec)
                    except Exception:
                        key_ready = False

                    lines.append(
                        f"- 거래소 {ex}: {'키 준비됨(빠른 점검)' if key_ready else '키 확인 필요(빠른 점검)'}"
                    )
                # 설정 창 경로에서는 네트워크 실연결 검증을 수행하지 않는다.
                live_check = False

            if live_check:
                def _check_exchange(ex: str) -> str:
                    try:
                        ok = bool(self.exchange_manager.validate_exchange_connection(ex))
                        return f"- 거래소 {ex}: {'연결 준비됨' if ok else '연결 확인 필요'}"
                    except Exception as e:
                        return f"- 거래소 {ex}: 진단 오류 ({str(e)[:60]})"

                executor = None
                futures: dict[concurrent.futures.Future[str], str] = {}
                results: dict[str, str] = {}
                try:
                    executor = concurrent.futures.ThreadPoolExecutor(
                        max_workers=min(len(enabled_exchanges), 4),
                        thread_name_prefix="diag_exchange",
                    )
                    futures = {executor.submit(_check_exchange, ex): ex
                               for ex in enabled_exchanges}

                    # 순서 유지: 원래 enabled_exchanges 순서대로 결과 수집
                    # 주의: 설정창은 UI 스레드에서 열리므로 진단 대기는 짧게 제한한다.
                    for fut in concurrent.futures.as_completed(futures, timeout=2):
                        ex = futures[fut]
                        try:
                            results[ex] = fut.result()
                        except Exception as e:
                            results[ex] = f"- 거래소 {ex}: 진단 오류 ({str(e)[:60]})"
                except concurrent.futures.TimeoutError:
                    # 일부 거래소 연결 검증이 지연될 수 있으므로 UI 응답성을 우선한다.
                    pass
                except Exception as e:
                    lines.append(f"- 거래소 병렬 진단 오류: {str(e)[:80]}")
                finally:
                    # 핵심: wait=False로 종료해 설정창 오픈 흐름을 블로킹하지 않는다.
                    if executor is not None:
                        try:
                            executor.shutdown(wait=False, cancel_futures=True)
                        except TypeError:
                            executor.shutdown(wait=False)

                for ex in enabled_exchanges:
                    lines.append(results.get(ex, f"- 거래소 {ex}: 연결 확인 시간 초과"))
        elif enabled_exchanges:
            lines.append('- 거래소 진단: exchange_manager가 없어 상세 확인 불가')

        # ── 증권 브로커 준비도(키/조합) ───────────────────────────────────────
        enabled_brokers = list(settings_obj.get('enabled_stock_brokers', []) or [])
        broker_configs = settings_obj.get('stock_broker_configs', {})
        service_name = str(getattr(self, 'current_service', 'blockchain') or 'blockchain').strip().lower()
        if enabled_brokers and isinstance(broker_configs, dict):
            if service_name != 'stock':
                lines.append('- 증권 준비도: 현재 서비스에서는 선택 사항이며 필수 점검 대상이 아닙니다.')
            else:
                for broker in enabled_brokers:
                    cfg = self._get_stock_broker_config(str(broker))
                    api_type = str(cfg.get('api_type', 'openapi') or 'openapi').strip().lower()
                    api_version = str(cfg.get('api_version', 'live_api') or 'live_api').strip().lower()

                    key_ready = bool(
                        (str(cfg.get('app_key', '') or '').strip() and str(cfg.get('app_secret', '') or '').strip())
                        or (str(cfg.get('id', '') or '').strip() and str(cfg.get('password', '') or '').strip())
                    )

                    combo_ok = True
                    try:
                        validator = getattr(ExchangeFactory, 'validate_stock_broker_api_combo', None)
                        if callable(validator):
                            validation_result = validator(str(broker), api_type, api_version)
                            combo_ok = bool(
                                validation_result[0] if isinstance(validation_result, tuple) else validation_result
                            )
                    except Exception:
                        combo_ok = False

                    lines.append(
                        f"- 증권 {broker}: 키 {'준비됨' if key_ready else '미준비'} / "
                        f"API 조합 {'정상' if combo_ok else '확인 필요'} ({api_type}/{api_version})"
                    )

        if not lines:
            lines.append('- 준비도 진단 항목이 없습니다. 설정을 먼저 확인하세요.')

        # ── 결과 캐시 저장 ────────────────────────────────────────────────────
        try:
            self._diagnosis_cache = list(lines)
            self._diagnosis_cache_settings_hash = current_hash  # type: ignore[reportPossiblyUnbound]
        except Exception:
            pass

        return lines

    def _record_ai_execute_event(
        self,
        *,
        action: str,
        title: str,
        plan_lines: list[str],
        risk_level: str,
        risk_reasons: list[str],
        result: str,
        status: str = 'completed',
    ) -> str:
        """AI 실행 이벤트를 이력에 기록하고 요약 카드를 갱신한다."""
        try:
            ledger = self._ai_activity_ledger
            ledger.max_size = max(1, int(self.max_ai_execute_history_size))
            event_id = ledger.record(
                action=action,
                title=title,
                plan_lines=plan_lines,
                risk_level=risk_level,
                risk_reasons=risk_reasons,
                result=result,
                status=status,
            )
            self._refresh_ai_execute_summary_card()
            return event_id
        except Exception as exc:
            logging.getLogger(__name__).exception("AI 활동 이력 기록 실패: %s", exc)
            return ''

    def _record_ai_assistant_request(self, message: str, service_context: str = '') -> str:
        """AI 어시스턴트·애널리스트의 실제 요청을 공용 실행 이력에 연결한다."""
        context = str(service_context or '').strip().lower()
        title = 'AI 애널리스트 심층분석' if context == 'ai_analyst' else 'AI 어시스턴트 질문'
        first_line = str(message or '').strip().splitlines()[0][:180]
        return self._record_ai_execute_event(
            action='ai_analysis_request',
            title=title,
            plan_lines=[first_line or 'AI 분석 요청'],
            risk_level='normal',
            risk_reasons=[],
            result='응답 생성 중',
            status='running',
        )

    def _finish_ai_assistant_request(
        self,
        event_id: str,
        *,
        result: str = '응답 완료',
        failed: bool = False,
    ) -> bool:
        """요청 접수 행을 응답 완료 또는 오류 상태로 원자적으로 마감한다."""
        if not event_id:
            return False
        updated = self._ai_activity_ledger.finish(event_id, result=result, failed=failed)
        if updated:
            self._refresh_ai_execute_summary_card()
        return updated

    def _refresh_ai_execute_summary_card(self) -> None:
        """하단 AI 실행 요약 카드를 최신 이벤트로 갱신한다."""
        try:
            if not getattr(self, 'ai_execute_summary_label', None):
                return
            history_snapshot = self._ai_activity_ledger.snapshot(limit=1)
            last = history_snapshot[-1] if history_snapshot else None
            if last is None:
                self.ai_execute_summary_label.configure(text='AI 실행 기록 없음')
                return
            timestamp = str(last.get('timestamp', '') or '')[-8:]
            title = str(last.get('title', '') or '')[:18]
            result = str(last.get('result', '') or '')[:14]
            text = f"AI 최근 · {timestamp} · {title} · {result}"
            self.ai_execute_summary_label.configure(text=text)
        except Exception:
            pass

    def _show_ai_execute_history_modal(self) -> None:
        """AI 실행 이력 모달을 표시한다."""
        try:
            modal = ctk.CTkToplevel(self)
            modal.title('AI 실행 기록')
            modal.geometry('680x420')
            try:
                modal.transient(self)
            except Exception:
                pass
            modal.grab_set()

            frame = ctk.CTkFrame(modal, fg_color=self._color('surface', '#0b1120'))
            frame.pack(fill='both', expand=True, padx=12, pady=12)

            title = ctk.CTkLabel(
                frame,
                text='AI 실행 기록 (최신순)',
                font=self._get_safe_font('subheading', ctk.CTkFont(size=15, weight='bold')),
                text_color=self._color('text_primary', '#f9fafb')
            )
            title.pack(anchor='w', padx=10, pady=(10, 6))

            box = ctk.CTkTextbox(
                frame,
                fg_color=self._color('background', '#050a13'),
                text_color=self._color('text_primary', '#f9fafb'),
                corner_radius=10,
            )
            box.pack(fill='both', expand=True, padx=10, pady=(0, 10))

            history_snapshot = self._ai_activity_ledger.snapshot(limit=20)
            if not history_snapshot:
                content = '기록이 없습니다.'
            else:
                chunks = []
                for item in reversed(history_snapshot):
                    risk_reasons = item.get('risk_reasons', []) or []
                    reason_text = '\n'.join(f"  - {r}" for r in risk_reasons)
                    plan_text = '\n'.join(f"  {line}" for line in (item.get('plan_lines', []) or []))
                    chunks.append(
                        f"[{item.get('timestamp', '')}] {item.get('title', '')}\n"
                        f"결과: {item.get('result', '')} | 위험도: {item.get('risk_level', 'normal')}\n"
                        f"계획:\n{plan_text}\n"
                        + (f"위험 사유:\n{reason_text}\n" if reason_text else "")
                        + "-" * 56
                    )
                content = '\n'.join(chunks)
            box.insert('1.0', content)
            box.configure(state='disabled')
        except Exception:
            pass


    def _refresh_quick_action_buttons(self) -> None:
        """Update quick action buttons with current theme icons and colors."""
        try:
            optimize_btn = getattr(self, 'optimize_action_btn', None)
            if optimize_btn:
                optimize_btn.configure(
                    image=None,
                    text_color=self._color('text_primary', '#f3f6fb')
                )
            optimize_apply_btn = getattr(self, 'optimize_apply_action_btn', None)
            if optimize_apply_btn:
                optimize_apply_btn.configure(
                    image=None,
                    text_color=self._color('text_primary', '#f3f6fb')
                )
            manual_btn = getattr(self, 'manual_action_btn', None)
            if manual_btn:
                manual_btn.configure(
                    image=self._get_icon("manual", (17, 17)),
                    compound="left",
                    text_color=self._color('text_primary', '#f3f6fb')
                )
        except Exception:
            pass

    # _validate_theme_palette 제거 - 고정 색상 사용


    # 호환용: main.py에서 호출할 수 있는 안전한 잔고 갱신 래퍼

    def set_components(self, binance_client=None, analyzer=None, evaluator=None, trader=None, recorder=None):
        """컴포넌트 설정 (main.py 호환성)"""
        try:
            if binance_client:
                self.binance_client = binance_client
            if analyzer:
                self.analyzer = analyzer
            if evaluator:
                self.evaluator = evaluator
            if trader:
                self.trader = trader
            if recorder:
                self.recorder = recorder
            try:
                from log_system.log_adapter import log_event
                log_event('system', '대시보드 컴포넌트 설정 완료')
            except Exception:
                self._dbg('대시보드 컴포넌트 설정 완료')
        except Exception as e:
            try:
                from log_system.log_adapter import log_exception
                log_exception('system', '대시보드 컴포넌트 설정 오류', exc=e)
            except Exception:
                self._dbg(f"대시보드 컴포넌트 설정 오류: {e}")

    def update_exchange_info(self):
        """활성화된 거래소 UI 섹션을 현재 설정에 맞춰 갱신"""
        try:
            # 현재 활성화된 거래소 목록 기준으로 섹션을 초기 생성/갱신
            enabled = self.settings.get('enabled_exchanges', ['binance']) if isinstance(self.settings, dict) else ['binance']
            selected_exchange = self.settings.get('selected_exchange', 'binance') if isinstance(self.settings, dict) else 'binance'
            exchange_display = str(selected_exchange or '').upper()

            # 거래소 정보 라벨 업데이트
            if hasattr(self, 'exchange_info_label'):
                try:
                    # 기존 스타일 유지하면서 텍스트만 업데이트
                    self.exchange_info_label.configure(
                        text=f"거래소: {exchange_display}",
                        fg_color=self._color('surface', '#0b1120'),
                        corner_radius=8
                    )
                except Exception:
                    self.exchange_info_label.configure(text=f"거래소: {exchange_display}")

            # 현재 서비스의 source 탭만 갱신한다. 주식 화면에서 설정을 저장할 때
            # 블록체인 탭을 강제로 만들던 기존 경로가 거래소/증권사 혼합의 원인이었다.
            if hasattr(self, 'tab_widget') and self.tab_widget is not None:
                try:
                    self.enabled_exchanges = list(enabled)
                    current_service = str(
                        getattr(self, 'current_service', 'blockchain') or 'blockchain'
                    ).strip().lower()
                    target_service = 'stock' if current_service == 'stock' else 'blockchain'
                    if target_service == 'stock':
                        desired_labels = [
                            str(item).upper()
                            for item in self.settings.get('enabled_stock_brokers', [])
                        ]
                    else:
                        desired_labels = [str(item).upper() for item in enabled]
                    rendered = dict(self.service_sub_tabs.get(target_service, {}) or {})
                    rebuild_required = (
                        list(rendered.keys()) != desired_labels
                        or not all(widget_is_alive(frame) for frame in rendered.values())
                    )
                    if rebuild_required:
                        self.clear_service_sub_tabs(target_service)
                    self.create_service_sub_tabs(target_service)
                except Exception as ie:
                    try:
                        self.logger.warning(f"거래소 탭 재구성 중 오류: {ie}")
                    except Exception:
                        pass
            # 현재 서비스의 본문만 동기화한다.
            try:
                if str(getattr(self, 'current_service', 'blockchain')).lower() == 'stock':
                    self.show_stock_content()
                else:
                    self.show_blockchain_content()
            except Exception:
                pass
            # 잔고 등 표시 업데이트
            self.update_balance_display()
        except Exception as e:
            try:
                self.logger.warning(f"update_exchange_info 실행 중 오류: {e}")
            except Exception:
                logging.getLogger(__name__).warning(f"update_exchange_info 실행 중 오류: {e}")

    # --- 대시보드 외부 호출 메서드: 상태/코인 표시 ---
    def update_status_display(self, force_refresh: bool = False) -> None:
        try:
            if not hasattr(self, 'status_display'):
                return
            status_text = self.get_status_info(force_refresh=force_refresh) if hasattr(self, 'get_status_info') else "상태 정보를 불러올 수 없습니다."
            self._safe_text_set(getattr(self, 'status_display', None), status_text)
        except Exception as e:
            self._safe_text_set(getattr(self, 'status_display', None), f"상태 조회 오류\n{str(e)}")

    def _update_replay_status_badge(self) -> None:
        """상단 리플레이 배지는 사용자 노출 방지를 위해 항상 숨김 처리한다."""
        try:
            replay_frame = getattr(self, 'replay_info_frame', None)
            if replay_frame is not None and hasattr(replay_frame, 'pack_forget'):
                try:
                    replay_frame.pack_forget()
                except Exception:
                    pass
        except Exception:
            pass

    def set_trading_status(self, status: str) -> None:
        """외부에서 전달되는 거래 상태 문자열을 받아 대시보드 상태를 갱신합니다.
        - 허용 상태: RUNNING, IDLE, STOPPED, STARTING, STOPPING (대소문자 무시)
        - 내부 플래그: self.is_auto_trading 을 업데이트하고, 관련 표시 위젯을 갱신합니다.
        """
        try:
            s = str(status or '').strip().upper()
            # 상태를 내부 플래그로 매핑
            if s in ('RUNNING', 'STARTING', 'STARTED'):
                self.is_auto_trading = True
            elif s in ('IDLE', 'STOPPED', 'STOPPING'):
                self.is_auto_trading = False
            else:
                # 알 수 없는 상태는 변경 없이 로그만 남김
                try:
                    if hasattr(self, 'logger') and self.logger:
                        self.logger.debug(f"set_trading_status: 알 수 없는 상태 '{s}' — 변경 없음")
                except Exception:
                    pass

            # 증권 자동매매 루프는 AUTO 시작/정지에 종속된다.
            # auto_start(enabled legacy)는 탭 진입 시 자동 예약 시작 여부만 담당.
            try:
                if str(getattr(self, 'current_service', '')).lower() == 'stock':
                    if bool(self.is_auto_trading):
                        self._start_stock_auto_trade_loop(force=True)
                    else:
                        self._stop_stock_auto_trade_loop()
            except Exception:
                pass

            # 컨트롤 위젯과 상태 영역 갱신
            if hasattr(self, 'update_trading_status'):
                self.update_trading_status()
            if hasattr(self, 'update_status_display'):
                self.update_status_display(force_refresh=True)
        except Exception as e:
            # 오류 로깅 및 탭 보장 생성
            try:
                if hasattr(self, 'logger') and self.logger:
                    self.logger.warning(f"set_trading_status 처리 중 오류: {e}")
            except Exception:
                pass
            # 주요 탭들을 초기 생성하여 탭 메뉴가 항상 보이도록 보장
            try:
                self._ensure_coin_info_tab()
                self._ensure_trading_stats_tab()
                self._ensure_trend_tab()
                self._ensure_ai_learning_tab()
                self._ensure_ai_assistant_tab()
                self._ensure_custom_strategy_tab()
            except Exception:
                pass

    def _get_active_exchange_from_tab(self) -> Optional[str]:
        """현재 선택된 탭 이름에서 거래소 코드를 추출"""
        try:
            tv = getattr(self, 'tab_widget', None)
            if tv is None or not hasattr(tv, 'get'):
                return None
            tab_name = str(tv.get() or '').strip().upper()
            # 예: "BITGET"
            for ex in ['BINANCE', 'BITGET', 'BYBIT', 'OKX', 'UPBIT', 'BITHUMB']:
                if ex in tab_name:
                    return ex
        except Exception:
            return None
        return None

    def get_status_info(self, force_refresh: bool = False) -> str:  # noqa: D401
        """현재 상태 텍스트를 반환합니다 (간단 스텁)."""
        try:
            auto = getattr(self, 'is_auto_trading', False)
            exch = getattr(self, 'exchange_manager', None)
            ex_name = getattr(exch, 'settings', {}).get('selected_exchange', 'binance') if exch else 'binance'
            prefix = "NoahAI-AI 금융 동반자"
            mode_text = 'AUTO' if auto else 'MANUAL'
            active_tab_ex = self._get_active_exchange_from_tab()
            ex_text = active_tab_ex or str(ex_name or 'binance').upper()
            time_text = datetime.now().strftime('%H:%M:%S')
            return f"{prefix} | MODE {mode_text} | EXCHANGE {ex_text} | TIME {time_text}"
        except Exception:
            return "상태 정보를 불러올 수 없습니다."

    def update_evaluator_scores_from_selected(self) -> None:
        """선정된 코인으로 평가자 테이블을 갱신하는 선택적 훅(스텁)."""
        try:
            # 실제 구현이 존재하는 경우, 해당 구현이 이 메서드를 대체할 수 있습니다.
            return
        except Exception:
            return

    def update_selected_coins(self, coins: List[Any]) -> None:
        """main.py에서 선정된 코인 리스트를 전달받아 대시보드에 반영.
        coins: ["BTCUSDT", ...] 또는 [{"symbol":"BTCUSDT", ...}, ...]
        """
        try:
            normalized: List[Dict[str, Any]] = []
            for c in coins or []:
                if isinstance(c, str):
                    sym = c.strip().upper()
                    normalized.append({
                        'symbol': sym,
                        'overall_score': 50.0,
                        'technical_score': 50.0,
                        'volatility_score': 50.0,
                        'volume_score': 50.0,
                        'trend_score': 50.0,
                        'risk_score': 50.0,
                        'is_major': False  # 문자열로 전달된 경우 기본값 False
                    })
                elif isinstance(c, dict):
                    sym = c.get('symbol') or c.get('coin') or str(c)
                    try:
                        sym = str(sym).strip().upper()
                    except Exception:
                        pass
                    normalized.append({
                        'symbol': sym,
                        'overall_score': float(c.get('overall_score', 50.0)),
                        'technical_score': float(c.get('technical_score', 50.0)),
                        'volatility_score': float(c.get('volatility_score', 50.0)),
                        'volume_score': float(c.get('volume_score', 50.0)),
                        'trend_score': float(c.get('trend_score', 50.0)),
                        'risk_score': float(c.get('risk_score', 50.0)),
                        'is_major': c.get('is_major', False)  # is_major 정보 전달
                    })
            # 상태 저장 및 화면 반영 (evaluator 테이블 재사용 가능 시)
            setattr(self, 'selected_coins', normalized)
            if hasattr(self, 'update_evaluator_scores_from_selected'):
                try:
                    self.update_evaluator_scores_from_selected()
                except Exception:
                    pass
            # 로그 출력
            if hasattr(self, 'add_log'):
                try:
                    self.add_log(f"선정된 코인 업데이트: {len(normalized)}개")
                except Exception:
                    pass
        except Exception as e:
            if hasattr(self, 'add_log'):
                self.add_log(f"선정된 코인 업데이트 오류: {e}", "ERROR")

    # 타입 검사용 최소 스텁: 실시간 로그 위젯이 없을 때에도 안전
    def add_log(self, message: str, level: str = "INFO") -> None:  # noqa: D401
        """대시보드 로그에 한 줄을 추가합니다 (간단 스텁)."""
        try:
            if hasattr(self, 'realtime_log_widget') and self.realtime_log_widget:
                try:
                    self.realtime_log_widget.add_log(message)
                    return
                except Exception:
                    pass
            # 폴백: 모듈 로거 사용
            try:
                getattr(self.logger, (level or 'info').lower(), self.logger.info)(message)
            except Exception:
                logging.getLogger(__name__).info(message)
        except Exception:
            pass

    # --- 통합 잔고 표시 도우미 ---
    def _format_balance_number(self, value: Any, currency_hint: str = "") -> str:
        """잔고 숫자를 가독성 있게 포맷팅"""
        try:
            n = float(value)
        except Exception:
            return str(value)

        hint = str(currency_hint or '').upper()
        if hint == 'KRW':
            return f"{n:,.0f}"

        abs_n = abs(n)
        if abs_n >= 1000:
            return f"{n:,.2f}"
        if abs_n >= 1:
            return f"{n:.4f}".rstrip('0').rstrip('.')
        if abs_n >= 0.01:
            return f"{n:.6f}".rstrip('0').rstrip('.')
        return f"{n:.8f}".rstrip('0').rstrip('.')


    def _balance_metric_items(self, exchange: str, balance: Any) -> List[tuple[str, str]]:
        """서로 다른 거래소 잔고 응답을 최대 3개의 짧은 지표로 정규화한다."""
        # 방송 리플레이가 켜진 경우, Binance 계열 잔고 표시에 오버레이를 우선 적용한다.
        try:
            ex_l = str(exchange or '').strip().lower()
            override_balance = self._get_broadcast_display_overrides().get('balance_usdt')
            if override_balance is not None and ex_l.startswith('binance') and isinstance(balance, dict):
                patched = dict(balance)
                patched['USDT'] = float(override_balance)
                patched['TOTAL'] = float(override_balance)
                patched['TOTAL_USDT'] = float(override_balance)
                patched['Total'] = float(override_balance)
                balance = patched
        except Exception:
            pass

        if isinstance(balance, (int, float, str)):
            return [("총 자산", self._format_balance_number(balance))]
        if not isinstance(balance, dict) or not balance:
            return []

        normalized: Dict[str, Any] = {}
        aliases = {
            'TOTAL': '총 자산', 'TOTAL_BALANCE': '총 자산', 'TOTAL_ASSETS': '총 자산',
            'EQUITY': '총 자산', 'AVAILABLE_BALANCE': '가용 잔고', 'AVAILABLE': '가용 잔고',
            'FREE': '가용 잔고', 'CASH': '가용 잔고', 'UNREALIZED_PNL': '미실현 PnL',
            'UNREALIZEDPNL': '미실현 PnL',
        }
        for raw_key, raw_value in balance.items():
            key = str(raw_key).upper()
            value = raw_value
            if isinstance(raw_value, dict):
                value = raw_value.get('total', raw_value.get('wallet_balance', raw_value.get('balance', 0)))
            try:
                numeric = float(value)
            except Exception:
                continue
            label = aliases.get(key, key)
            normalized[label] = numeric

        krw_sources = {
            'upbit', 'bithumb', 'kiwoom', 'shinhan', 'miraeasset', 'mirae_asset',
            'koreainvestment', 'korea_investment', 'korea-investment',
        }
        quote = 'KRW' if str(exchange).lower() in krw_sources else 'USDT'
        summary_order = [quote, '총 자산', '가용 잔고', '미실현 PnL']
        ordered_keys = [key for key in summary_order if key in normalized]
        # BTC/ETH를 고정 슬롯으로 두지 않는다. 기준통화·계정 요약 다음에는
        # 실제로 0보다 큰 모든 보유자산을 거래소 응답 순서대로 표시한다.
        ordered_keys.extend(
            key
            for key, value in normalized.items()
            if key not in ordered_keys and float(value or 0) > 0
        )

        result: List[tuple[str, str]] = []
        for key in ordered_keys[:3]:
            value = normalized[key]
            hint = quote if key in {'총 자산', '가용 잔고', '미실현 PnL'} else key
            suffix = f" {quote}" if key in {'총 자산', '가용 잔고', '미실현 PnL'} else ""
            result.append((key, f"{self._format_balance_number(value, hint)}{suffix}"))
        return result

    def _cache_asset_balance_snapshot(self, source: str, balance: Any) -> None:
        """계좌 패널에서 검증된 최신 잔고를 자산 통합용으로 보관한다."""
        store = getattr(self, '_asset_snapshot_store', None)
        if store is not None and store.update(source, balance):
            self._asset_balance_snapshot_at = datetime.now()

    def _update_balance_metric_widgets(self, widgets: Dict[str, Any], exchange: str, balance: Any) -> None:
        """잔고 미니 카드 3개를 동일한 규칙으로 갱신한다."""
        self._cache_asset_balance_snapshot(exchange, balance)
        items = self._balance_metric_items(exchange, balance)
        labels = widgets.get('balance_values', [])
        for index, pair in enumerate(labels):
            title_label, value_label = pair
            if index < len(items):
                title_text, value_text = items[index]
                title_label.configure(text=title_text)
                value_label.configure(text=value_text)
            else:
                title_label.configure(text="보유자산")
                value_label.configure(text="추가 자산 없음")

    def _set_balance_metric_state(self, widgets: Dict[str, Any], message: str) -> None:
        """조회 대기·실패도 영구적인 '로딩 중'으로 남기지 않는다."""
        labels = widgets.get("balance_values", [])
        for title_label, value_label in labels:
            title_label.configure(text="-")
            value_label.configure(text=message)

    @staticmethod
    def _balance_status_message(result: Dict[str, Any]) -> str:
        """거래소별 잔고 응답 상태를 사용자 문구로 정규화한다."""
        status = str((result or {}).get("status") or "").strip().lower()
        return {
            "waiting": "연결 대기",
            "disabled": "거래소 비활성",
            "no_api_keys": "API 키 없음",
            "invalid_api_keys": "API 키 오류",
            "authentication_failed": "인증 실패",
            "connection_failed": "연결 실패",
            "client_unavailable": "연결 미준비",
            "error": "조회 오류",
            "failed": "조회 실패",
        }.get(status, "조회 실패")

    @staticmethod
    def _position_value(position: Any, *keys: str, default: Any = None) -> Any:
        for key in keys:
            try:
                if hasattr(position, key):
                    value = getattr(position, key)
                    if value is not None:
                        return value
                if isinstance(position, dict) and position.get(key) is not None:
                    return position.get(key)
            except Exception:
                continue
        return default

    def _format_position_number(self, value: Any, *, signed: bool = False) -> str:
        try:
            number = float(value or 0)
        except Exception:
            return str(value if value is not None else '-')
        prefix = '+' if signed and number > 0 else ''
        absolute = abs(number)
        if absolute >= 1000:
            return f"{prefix}{number:,.2f}"
        if absolute >= 1:
            return f"{prefix}{number:.4f}".rstrip('0').rstrip('.')
        return f"{prefix}{number:.6f}".rstrip('0').rstrip('.') or '0'

    def _render_position_cards(
        self,
        body: Any,
        count_label: Any,
        positions: Any,
        *,
        empty_text: str = "활성 포지션 없음",
        quote: str = "USDT",
        stock_mode: bool = False,
        mode_label: str = "",
    ) -> None:
        """포지션을 3개가 동시에 읽히는 고정밀 카드 목록으로 그린다."""
        try:
            for child in body.winfo_children():
                child.destroy()
        except Exception:
            pass

        if isinstance(positions, dict):
            rows = list(positions.items())
        elif isinstance(positions, list):
            rows = []
            for index, position in enumerate(positions):
                symbol = self._position_value(position, 'symbol', 'code', default=f"#{index + 1}")
                rows.append((str(symbol), position))
        else:
            rows = []

        rows = sorted(rows, key=lambda item: str(item[0]))
        count_text = f"{len(rows)}개 보유" if stock_mode else f"{len(rows)}개 활성"
        normalized_mode = str(mode_label or "").strip().upper()
        if normalized_mode:
            count_text = f"{normalized_mode} · {count_text}"
        count_label.configure(
            text=count_text,
            text_color="#a78bfa" if normalized_mode == "PAPER" else "#60a5fa",
        )
        if not rows:
            ctk.CTkLabel(
                body, text=empty_text, font=self._get_safe_font("body"),
                text_color=self._color('text_secondary', '#94a3b8'),
            ).pack(expand=True, pady=30)
            return

        for symbol, position in rows:
            side_raw = self._position_value(position, 'side', default='HOLD' if stock_mode else 'NA')
            side = str(getattr(side_raw, 'name', side_raw)).upper()
            quantity = self._position_value(position, 'quantity', 'size', 'qty', 'contracts', default=0)
            entry = self._position_value(position, 'entry_price', 'entryPrice', 'avg_price', default=0)
            pnl = self._position_value(position, 'unrealized_pnl', 'unrealizedPnl', 'pnl', default=0)
            leverage = self._position_value(position, 'leverage', default=None)
            try:
                pnl_number = float(pnl or 0)
            except Exception:
                pnl_number = 0.0

            card = ctk.CTkFrame(
                body, height=58, fg_color="#111827", corner_radius=10,
                border_width=1, border_color="#334155",
            )
            card.pack(fill="x", padx=1, pady=3)
            card.pack_propagate(False)
            card.grid_propagate(False)
            card.grid_columnconfigure(0, weight=2)
            card.grid_columnconfigure(1, weight=3)
            card.grid_columnconfigure(2, weight=2)
            card.grid_rowconfigure((0, 1), weight=1)

            # 카드마다 투명 CTkFrame 3개(각각 Canvas 포함)를 만들던 구조를 제거한다.
            # 직접 grid한 6개 라벨은 Windows 자원 압박 시 빈 카드만 남는 현상을 줄인다.
            ctk.CTkLabel(
                card, text=str(symbol), font=ctk.CTkFont(size=12, weight="bold"),
                text_color=self._color('text_primary', '#f8fafc'), anchor="w",
            ).grid(row=0, column=0, sticky="sw", padx=(9, 3), pady=(3, 0))
            side_color = '#22c55e' if side in {'LONG', 'BUY', 'HOLD'} else '#ef4444'
            ctk.CTkLabel(
                card, text=("보유" if stock_mode else side), font=ctk.CTkFont(size=10, weight="bold"),
                text_color=side_color, anchor="w",
            ).grid(row=1, column=0, sticky="nw", padx=(9, 3), pady=(0, 3))
            ctk.CTkLabel(
                card, text=f"수량 {self._format_position_number(quantity)}",
                font=self._get_safe_font("small"), text_color="#cbd5e1", anchor="w",
            ).grid(row=0, column=1, sticky="sw", padx=3, pady=(3, 0))
            entry_text = self._format_position_number(entry)
            lev_text = f" · {self._format_position_number(leverage)}x" if leverage not in (None, '', 0, '0') else ''
            ctk.CTkLabel(
                card, text=f"진입 {entry_text}{lev_text}", font=self._get_safe_font("small"),
                text_color="#94a3b8", anchor="w",
            ).grid(row=1, column=1, sticky="nw", padx=3, pady=(0, 3))
            ctk.CTkLabel(
                card, text="평가손익" if stock_mode else "미실현 PnL",
                font=self._get_safe_font("small"), text_color="#94a3b8", anchor="e",
            ).grid(row=0, column=2, sticky="se", padx=(3, 9), pady=(3, 0))
            ctk.CTkLabel(
                card, text=f"{self._format_position_number(pnl, signed=True)} {quote}",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=('#22c55e' if pnl_number >= 0 else '#ef4444'), anchor="e",
            ).grid(row=1, column=2, sticky="ne", padx=(3, 9), pady=(0, 3))

    def _display_unified_balances(self, all_balances: Dict[str, Dict[str, float]]) -> None:
        try:
            for source, balance in (all_balances or {}).items():
                self._cache_asset_balance_snapshot(str(source), balance)
            if not hasattr(self, 'balance_display'):
                return
            lines: List[str] = ["통합 잔고 요약", "", "• 거래소/증권사별 현황"]
            display_overrides = self._get_broadcast_display_overrides()
            override_balance = display_overrides.get('balance_usdt')
            override_balance_applied = False
            total_sources = len(all_balances or {})
            valid_sources = 0
            
            total_usdt = 0.0
            total_krw = 0.0
            
            for ex_key, bal in (all_balances or {}).items():
                if not isinstance(bal, dict) or not bal:
                    lines.append(f"  - {ex_key}: 데이터 없음")
                    continue

                valid_sources += 1

                # USDT 잔고 확인 (BinanceFuturesAdapter는 이미 평탄화된 구조)
                usdt_balance = bal.get('USDT') or bal.get('total') or bal.get('Total')
                if (
                    override_balance is not None
                    and not override_balance_applied
                    and str(ex_key or '').strip().lower().startswith('binance')
                ):
                    usdt_balance = override_balance
                    override_balance_applied = True
                
                # KRW 잔고 확인 (현물 거래소용)
                krw_balance = bal.get('KRW') or 0.0

                # 통합 합계 계산
                if usdt_balance is not None:
                    total_usdt += float(usdt_balance)
                if krw_balance:
                    total_krw += float(krw_balance)

                # USDT를 제외한 다른 코인들만 preview에 포함
                other_coins = {k: v for k, v in bal.items() if k.upper() not in ['USDT', 'TOTAL', 'TOTAL_USDT', 'KRW']}

                if usdt_balance is not None:
                    # USDT 잔고가 있으면 메인으로 표시하고, 다른 코인들도 함께 표시
                    if other_coins:
                        preview = ", ".join(
                            f"{str(k).upper()}={self._format_balance_number(v, str(k))}"
                            for k, v in list(other_coins.items())[:2]
                        )
                        lines.append(f"  - {ex_key}: USDT {self._format_balance_number(usdt_balance, 'USDT')} | {preview}")
                    else:
                        lines.append(f"  - {ex_key}: USDT {self._format_balance_number(usdt_balance, 'USDT')}")
                elif krw_balance:
                    # KRW 잔고가 있으면 표시
                    if other_coins:
                        preview = ", ".join(
                            f"{str(k).upper()}={self._format_balance_number(v, str(k))}"
                            for k, v in list(other_coins.items())[:2]
                        )
                        lines.append(f"  - {ex_key}: KRW {self._format_balance_number(krw_balance, 'KRW')} | {preview}")
                    else:
                        lines.append(f"  - {ex_key}: KRW {self._format_balance_number(krw_balance, 'KRW')}")
                else:
                    # USDT/KRW 잔고가 없으면 모든 코인을 표시
                    preview = ", ".join(
                        f"{str(k).upper()}={self._format_balance_number(v, str(k))}"
                        for k, v in list(bal.items())[:3]
                    )
                    lines.append(f"  - {ex_key}: {preview}")

            # 통합 합계 표시
            if override_balance is not None:
                total_usdt = float(override_balance)
            if total_usdt > 0 or total_krw > 0:
                lines.append("")
                lines.append("• 통합 합계(통화별)")
                if total_usdt > 0:
                    lines.append(f"  - USDT 합계: {self._format_balance_number(total_usdt, 'USDT')} USDT")
                if total_krw > 0:
                    lines.append(f"  - KRW 합계: {self._format_balance_number(total_krw, 'KRW')} 원")

            lines.append("")
            lines.append(f"• 연결 상태: {valid_sources}/{total_sources} 소스 수신")

            text = "\n".join(lines) if lines else "통합 잔고 요약 데이터가 없습니다."
            self._safe_text_set(getattr(self, 'balance_display', None), text)
        except Exception as e:
            self._safe_text_set(getattr(self, 'balance_display', None), f"잔고 조회 오류\n{e}")

    def _update_demo_mode_widget(self):
        """데모 모드 위젯 상태 업데이트"""
        try:
            if hasattr(self, 'demo_widget') and self.demo_widget:
                # 데모 모드 설정 확인
                is_demo_mode = bool(self.settings.get('demo_mode', False))
                print(f"데모 모드 위젯 업데이트: demo_mode={is_demo_mode}")

                if is_demo_mode:
                    # 데모 모드가 활성화된 경우, demo_trader 객체 설정
                    try:
                        from trading.demo_trader import DemoTrader
                        demo_trader = DemoTrader(self.settings, self.logger if hasattr(self, 'logger') else None)
                        self.demo_widget.set_demo_trader(demo_trader)
                        print("데모 모드 위젯에 DemoTrader 설정 완료")
                    except Exception as e:
                        print(f"DemoTrader 생성 실패: {e}")
                        self.demo_widget.set_demo_trader(None)
                else:
                    # 데모 모드가 비활성화된 경우
                    self.demo_widget.set_demo_trader(None)
                    print("데모 모드 위젯 비활성화")
        except Exception as e:
            print(f"데모 모드 위젯 업데이트 실패: {e}")

    def refresh_after_settings_change(self, new_settings, exchange_manager=None, unified_manager=None):
        """설정 변경 후 대시보드 내부 상태 갱신"""
        try:
            self.settings = new_settings
            if exchange_manager:
                self.exchange_manager = exchange_manager
            if unified_manager:
                self.unified_manager = unified_manager
            # 활성화 거래소 갱신 및 화면 업데이트 트리거
            self.enabled_exchanges = self.settings.get('enabled_exchanges', ['binance'])

            self.update_exchange_info()
            # 필요한 섹션 갱신 (잔고/포지션 등)
            self.update_balance_display()
            # 항상 최상단 표시 설정 즉시 반영
            self.refresh_always_on_top_setting()

            # 데모 모드 위젯 업데이트
            self._update_demo_mode_widget()
            # 클래식 보기 적용: 토글이 켜졌다면 AI 탭 보장 및 선택
            try:
                if bool(self.settings.get('classic_view', False)):
                    self._ensure_ai_learning_tab()
                    self._ensure_ai_report_tab()
                    self._ensure_ai_assistant_tab()  # AI 어시스턴트도 추가
                    self._ensure_coin_info_tab()     # 코인 정보도 추가
                    self._ensure_trading_stats_tab() # 거래 통계도 추가
                    # 요청된 탭 순서 고정: 거래통계 다음에 시장트렌드
                    self._ensure_trend_tab()
                    if hasattr(self, 'tab_widget') and self.tab_widget is not None:
                        cast(ctk.CTkTabview, self.tab_widget).set("AI 학습")
            except Exception:
                pass
            # AI READY 배지 갱신
            try:
                self.update_ai_status_badges()
            except Exception:
                pass
            # 어시스턴트 탭이 열려 있다면 모델을 즉시 재적용
            try:
                aw = getattr(self, 'ai_assistant_widget', None)
                if aw is not None:
                    new_model = (self.settings or {}).get('assistant_ai_model', 'gpt-4o')
                    # AIAssistantWidget에 런타임 변경 API가 있으면 사용
                    setter = getattr(aw, 'set_assistant_model', None)
                    if callable(setter):
                        setter(new_model, announce=True)
                    else:
                        # 폴백: 속성만 갱신
                        try:
                            aw.assistant_model_name = new_model
                            # 캡션 갱신 시도
                            getattr(aw, 'update_model_caption', lambda: None)()
                        except Exception:
                            pass
            except Exception:
                pass
            # Alpha Arena 탭 갱신 (설정 변경 시 enabled 상태 반영)
            try:
                self._ensure_alpha_arena_tab()
            except Exception as alpha_err:
                # Alpha Arena 탭 생성 실패는 무시 (설정에서 비활성화되었거나 오류)
                self.logger.debug(f"Alpha Arena 탭 갱신 중 오류 (무시): {alpha_err}")
            self.logger.info("대시보드 설정 갱신 반영 완료")
        except Exception as e:
            try:
                self.logger.error(f"대시보드 설정 갱신 오류: {e}")
            except Exception:
                print(f"대시보드 설정 갱신 오류: {e}")

    def _init_user_status_manager(self):
        """사용자 상태 관리자 초기화"""
        try:
            if UserStatusManager and get_status_manager:
                policy_callback = getattr(self.main_app, "apply_server_membership_policy", None)
                self.status_manager = get_status_manager(
                    self.backend_api,
                    self.settings,
                    policy_update_callback=policy_callback,
                )

                # 사용자 상태 관리자만 초기화 (자동 시작하지 않음)
                try:
                    self.logger.info("사용자 상태 관리자 초기화 완료 (수동 시작 필요)")
                except Exception:
                    logging.getLogger(__name__).info("사용자 상태 관리자 초기화 완료 (수동 시작 필요)")
            else:
                try:
                    self.logger.warning("사용자 상태 관리자 모듈을 사용할 수 없습니다.")
                except Exception:
                    logging.getLogger(__name__).warning("사용자 상태 관리자 모듈을 사용할 수 없습니다.")
                self.status_manager = None
        except Exception as e:
            try:
                self.logger.error(f"사용자 상태 관리자 초기화 실패: {e}")
            except Exception:
                logging.getLogger(__name__).error(f"사용자 상태 관리자 초기화 실패: {e}")
            self.status_manager = None

    def start_user_status_monitoring(self):
        """사용자 상태 모니터링 시작"""
        try:
            if self.status_manager:
                try:
                    self.logger.info("사용자 상태 모니터링 시작...")
                except Exception:
                    logging.getLogger(__name__).info("사용자 상태 모니터링 시작...")
                self.status_manager.start_status_checker()
                try:
                    self.logger.info("사용자 상태 모니터링이 시작되었습니다.")
                except Exception:
                    logging.getLogger(__name__).info("사용자 상태 모니터링이 시작되었습니다.")

                # 실시간 로그에 메시지 표시 (안전한 방식)
                if hasattr(self, 'realtime_log_widget') and self.realtime_log_widget:
                    try:
                        self.realtime_log_widget.add_log(f"[{datetime.now().strftime('%H:%M:%S')}] 사용자 상태·회원권한 모니터링 시작 (1분 간격)")
                    except Exception as e:
                        try:
                            self.logger.debug(f"실시간 로그 추가 실패 (정상): {e}")
                        except Exception:
                            logging.getLogger(__name__).debug(f"실시간 로그 추가 실패 (정상): {e}")
            else:
                try:
                    self.logger.warning("사용자 상태 관리자가 없어서 모니터링을 시작할 수 없습니다.")
                except Exception:
                    logging.getLogger(__name__).warning("사용자 상태 관리자가 없어서 모니터링을 시작할 수 없습니다.")
        except Exception as e:
            try:
                self.logger.error(f"사용자 상태 모니터링 시작 실패: {e}")
            except Exception:
                logging.getLogger(__name__).error(f"사용자 상태 모니터링 시작 실패: {e}")


    def _color(self, key: str, fallback: Optional[str] = None) -> str:
        """Return color from the fixed-skin palette only.

        Theme is deprecated. All colors come from utils.fixed_colors.FIXED_COLORS.
        """
        try:
            return _FIXED_COLORS.get(key, fallback if fallback is not None else _FIXED_COLORS.get('info', '#3b82f6'))
        except Exception:
            return fallback if fallback is not None else '#3b82f6'

    def _get_safe_font(self, font_key: str, fallback_font=None):
        """Retrieve registered CTkFont with graceful fallback."""
        try:
            fonts = getattr(self, 'fonts', None)
            if isinstance(fonts, dict):
                font = fonts.get(font_key)
                if font:
                    return font
                # allow lowercase keys
                font = fonts.get(font_key.lower())
                if font:
                    return font
        except Exception:
            pass
        try:
            return fallback_font or ctk.CTkFont(size=13)
        except Exception:
            return None


    # --- 안전한 탭 보장/상태 배지 업데이트 (스텁) -----------------------------
    # 아래 메서드들은 정적 분석 경고 제거 및 런타임 안정성용 no-op 기본 구현입니다.
    # 실제 구현이 별도에 있으면 덮어씌워집니다.

    def _ensure_ai_learning_tab(self) -> None:
        """AI 학습 탭이 없으면 생성하고, 위젯을 안전하게 장착합니다."""
        self.logger.info("[DEBUG] _ensure_ai_learning_tab 시작")
        try:
            if not hasattr(self, 'tab_widget') or self.tab_widget is None:
                self.logger.info("[DEBUG] tab_widget 없음, 반환")
                return
            tab_name = "AI 학습"
            self.logger.info(f"[DEBUG] AI 학습 탭 생성/조회: {tab_name}")
            tab = self._get_or_add_tab(tab_name)
            self.logger.info("[DEBUG] AI 학습 탭 획득 완료")
            cached = self._widget_ownership.resolve_attribute(self, "ai_learning_widget")
            if cached is not None and tab.winfo_children():
                try:
                    cached.set_service_context(
                        str(getattr(self, 'current_service', 'blockchain') or 'blockchain'),
                        announce=False,
                    )
                except TypeError:
                    cached.set_service_context(
                        str(getattr(self, 'current_service', 'blockchain') or 'blockchain')
                    )
                except Exception:
                    pass
                return
            # 기존 내용 초기화 후 재구성 (중복 방지)
            self._clear_tab_children(tab)

            container = ctk.CTkFrame(
                tab,
                fg_color=self._color("content_bg", "#0b1120"),
                corner_radius=0,
            )
            # 아래 여백을 줄여 하단 상태바 공간 확보
            container.pack(fill="both", expand=True, padx=10, pady=(10, 0))

            # 상단 바: 좌측 요약(오늘/주간/신호) + 우측 AI READY 배지 (같은 줄)
            ready = self._ai_ready()
            header_bar = ctk.CTkFrame(
                container,
                fg_color=self._color("card", "#111827"),
                border_color=self._color("border_soft", "#273449"),
                border_width=1,
                corner_radius=12,
            )
            header_bar.pack(fill="x", padx=4, pady=(0, 6))
            # 좌측 요약 바 (초기값 0)
            summary_bar = ctk.CTkFrame(
                header_bar,
                fg_color=self._color("card", "#111827"),
                corner_radius=0,
            )
            summary_bar.pack(side="left", padx=10, pady=7)
            ai_today_lbl = ctk.CTkLabel(summary_bar, text="오늘: 0개", text_color=self._color("info", "#3b82f6"))
            ai_today_lbl.pack(side="left", padx=(0, 10))
            ai_week_lbl = ctk.CTkLabel(summary_bar, text="주간: 0개", text_color=self._color("warning", "#f59e0b"))
            ai_week_lbl.pack(side="left", padx=(0, 10))
            ai_sig_lbl = ctk.CTkLabel(summary_bar, text="신호: LONG(0) SHORT(0) HOLD(0)", text_color=self._color("accent", "#8b5cf6"))
            ai_sig_lbl.pack(side="left")
            self.ai_learning_summary_today = ai_today_lbl
            self.ai_learning_summary_week = ai_week_lbl
            self.ai_learning_summary_signal = ai_sig_lbl
            # 우측 배지
            badge_text = "AI READY" if ready else "AI OFF"
            badge_color = self._color("success", "#22c55e") if ready else self._color("danger", "#ef4444")
            badge = ctk.CTkLabel(header_bar, text=badge_text, fg_color=badge_color, text_color="white", corner_radius=6, padx=8, pady=4)
            badge.pack(side="right", padx=10, pady=7)
            self.ai_learning_badge_label = badge

            # 서비스별 소스 선택 드롭다운 + 첫 번째 소스 기준 위젯 생성
            current_service = str(getattr(self, 'current_service', 'blockchain') or 'blockchain').lower()
            try:
                if current_service == 'stock':
                    source_list = list(self.settings.get('enabled_stock_brokers', []) or [])
                    if not source_list:
                        source_list = ['kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment']
                    selected_broker = str(self.settings.get('selected_stock_broker', '') or '').strip().lower()
                    source_name = selected_broker if selected_broker in source_list else source_list[0]
                    source_label_text = "증권사:"
                else:
                    source_list = list(self.enabled_exchanges or [])
                    if not source_list:
                        source_list = ['binance']
                    source_name = source_list[0]
                    source_label_text = "거래소:"
            except Exception:
                source_list = ['binance']
                source_name = 'binance'
                source_label_text = "거래소:"

            # 상단: 거래소 선택 영역 (요약 바 아래)
            try:
                selector_frame = ctk.CTkFrame(
                    container,
                    fg_color=self._color("card", "#111827"),
                    border_color=self._color("border_soft", "#273449"),
                    border_width=1,
                    corner_radius=12,
                )
                selector_frame.pack(fill="x", padx=4, pady=(0, 8))
                source_label = ctk.CTkLabel(
                    selector_frame,
                    text=source_label_text,
                    text_color=self._color("text_secondary", "#9ca3af"),
                )
                source_label.pack(side="left", padx=(6, 8))
                source_var = ctk.StringVar(value=source_name)
                def _on_exchange_change(choice: str):
                    try:
                        if hasattr(self, 'ai_learning_widget') and self.ai_learning_widget and hasattr(self.ai_learning_widget, 'set_exchange'):
                            self.ai_learning_widget.set_exchange(choice)
                    except Exception as _e:
                        try:
                            self.logger.warning(f"AI 학습 거래소 변경 실패: {_e}")
                        except Exception:
                            pass
                source_menu = ctk.CTkOptionMenu(
                    selector_frame,
                    variable=source_var,
                    values=source_list,
                    command=_on_exchange_change,
                    fg_color=self._color("primary", "#2563eb"),
                    button_color=self._color("primary", "#2563eb"),
                    button_hover_color=self._color("primary_hover", "#1d4ed8"),
                )
                source_menu.pack(side="left", pady=7)
                self.ai_learning_source_label = source_label
                self.ai_learning_source_menu = source_menu
                self.ai_learning_source_var = source_var
            except Exception:
                pass

            # 본 위젯 장착
            try:
                # 위젯 모듈 지연 로드 (import-time 부작용 회피)
                try:
                    from ui.widgets.ai_learning_widget import AILearningWidget as _AILearningWidget
                except Exception as imp_err:
                    self.logger.error(f"AI 학습 위젯 import 실패: {imp_err}")
                    _AILearningWidget = None

                if _AILearningWidget is None:
                    raise RuntimeError("AI 학습 위젯 모듈 로드 실패")

                self.logger.info(f"[DEBUG] AILearningWidget 생성 시작: source={source_name}, service={current_service}")
                ai_widget = _AILearningWidget(
                    container,
                    exchange_name=source_name,
                    service_context=current_service,
                    colors=dict(_FIXED_COLORS),
                )
                self.logger.info("[DEBUG] AILearningWidget 생성 완료")
                try:
                    if hasattr(ai_widget, 'set_service_context'):
                        ai_widget.set_service_context(current_service)
                except Exception:
                    pass
                # 상단 요약 바 업데이트 콜백 연결 (header_bar의 라벨 갱신)
                def _on_ai_summary(payload: dict):
                    try:
                        if hasattr(self, 'ai_learning_summary_today') and self.ai_learning_summary_today:
                            self.ai_learning_summary_today.configure(text=f"오늘: {int(payload.get('today_count', 0))}개")
                        if hasattr(self, 'ai_learning_summary_week') and self.ai_learning_summary_week:
                            self.ai_learning_summary_week.configure(text=f"주간: {int(payload.get('weekly_count', 0))}개")
                        if hasattr(self, 'ai_learning_summary_signal') and self.ai_learning_summary_signal:
                            ls = int(payload.get('long_signals', 0))
                            ss = int(payload.get('short_signals', 0))
                            hs = int(payload.get('hold_signals', 0))
                            self.ai_learning_summary_signal.configure(text=f"신호: LONG({ls}) SHORT({ss}) HOLD({hs})")
                    except Exception:
                        pass
                self.logger.info("[DEBUG] AI 위젯 콜백 설정 시작")
                if hasattr(ai_widget, 'set_summary_callback'):
                    try:
                        ai_widget.set_summary_callback(_on_ai_summary)
                        self.logger.info("[DEBUG] set_summary_callback 설정 완료")
                    except Exception as cb_err:
                        self.logger.warning(f"[DEBUG] set_summary_callback 설정 실패: {cb_err}")
                self.logger.info("[DEBUG] AI 위젯 pack 시작")
                ai_widget.pack(fill="both", expand=True)
                self.logger.info("[DEBUG] AI 위젯 pack 완료")
                self._register_tab_widget("AI 학습", "ai_learning_widget", ai_widget)
                self.logger.info("[DEBUG] AI 학습 위젯 장착 완료")
            except Exception as e:
                # 폴백: 오류 메시지 표시
                err = ctk.CTkLabel(container, text=f"AI 학습 위젯 로드 실패\n{e}")
                err.pack(pady=20)
        except Exception as e:
            try:
                self.logger.error(f"AI 학습 탭 생성 실패: {e}")
            except Exception:
                pass

    def _ensure_ai_report_tab(self) -> None:
        """AI 리포트 탭이 없으면 생성하고, 위젯을 안전하게 장착합니다."""
        try:
            if not hasattr(self, 'tab_widget') or self.tab_widget is None:
                return
            tab_name = "AI 리포트"
            tab = self._get_or_add_tab(tab_name)
            cached = self._widget_ownership.resolve_attribute(self, "ai_report_widget")
            if cached is not None and tab.winfo_children():
                return
            # 기존 내용 초기화 후 재구성 (중복 방지)
            self._clear_tab_children(tab)

            report_palette = build_widget_palette(dict(_FIXED_COLORS))
            container = ctk.CTkFrame(
                tab,
                fg_color=report_palette["content_bg"],
                corner_radius=10,
            )
            container.pack(fill="both", expand=True, padx=10, pady=10)

            # 상단 AI READY 배지
            ready = self._ai_ready()
            badge_text = "AI READY" if ready else "AI OFF"
            badge_color = ("#1d6f42", "#0f4d2d") if ready else ("#6f1d1d", "#4d0f0f")
            badge = ctk.CTkLabel(container, text=badge_text, fg_color=badge_color, text_color="white", corner_radius=6, padx=8, pady=4)
            badge.pack(anchor="ne", padx=4, pady=4)
            # 배지 참조 저장 (동적 갱신용)
            self.ai_report_badge_label = badge

            try:
                ai_report_widget = AIReportWidget(container, colors=report_palette)
                ai_report_widget.pack(fill="both", expand=True)
                self._register_tab_widget("AI 리포트", "ai_report_widget", ai_report_widget)
            except Exception as e:
                try:
                    from ui.widgets.ai_report_widget_safe import AIReportWidgetSafe
                    ai_report_widget = AIReportWidgetSafe(container, colors=report_palette)
                    ai_report_widget.pack(fill="both", expand=True)
                    self._register_tab_widget("AI 리포트", "ai_report_widget", ai_report_widget)
                    self.logger.warning(f"AIReportWidget 로드 실패, 안전 버전으로 대체: {e}")
                except Exception as e2:
                    err = ctk.CTkLabel(container, text=f"AI 리포트 위젯 로드 실패\n{e2}")
                    err.pack(pady=20)
        except Exception as e:
            try:
                self.logger.error(f"AI 리포트 탭 생성 실패: {e}")
            except Exception:
                pass

    def _ensure_ai_assistant_tab(self) -> None:
        """'AI 어시스턴트' 탭을 보장하고 통합된 AIAssistantWidget을 삽입합니다."""
        try:
            if not getattr(self, 'tab_widget', None):
                return
            name = "AI 어시스턴트"
            created = not self._tab_exists(name)
            tab = self._get_or_add_tab(name)
            cached = getattr(self, 'ai_assistant_widget', None)
            cached_input = getattr(cached, 'chat_input', None) if cached is not None else None
            cached_live = self._widget_alive(cached) and self._widget_alive(cached_input)
            if not cached_live:
                self._invalidate_tab_widget_reference(name)
                if not created and tab.winfo_children():
                    self._clear_tab_children(tab)
            if created or not tab.winfo_children():
                widget = None
                try:
                    from ui.widgets.ai_assistant_widget import AIAssistantWidget
                    # 빌드 환경 대응: assistant_ai_model도 path_utils를 통해 로드
                    try:
                        from config.settings import load_settings
                        current_settings = load_settings()
                        model_name = current_settings.get('assistant_ai_model', 'gpt-4o')
                        self.logger.debug(f"설정에서 어시스턴트 모델 로드: {model_name}")
                    except Exception as e:
                        # fallback: self.settings 사용
                        self.logger.warning(f"설정 파일 로드 실패, fallback 사용: {e}")
                        import traceback
                        self.logger.debug(traceback.format_exc())
                        current_settings = self.settings or {}
                        model_name = (self.settings or {}).get('assistant_ai_model', 'gpt-4o')

                    # 어시스턴트는 analyst와 별도 workload 프로필로 라우팅한다.
                    from trading.ai.ai_manager import AIManager
                    ai_manager = AIManager(
                        api_key=str(current_settings.get('openai_api_key', '') or ''),
                        model=str(model_name or ''),
                        base_url=str(current_settings.get('openai_base_url', '') or '') or None,
                        settings=current_settings,
                        workload="assistant",
                    )
                    
                    # 모델명 정규화 (잘못된 모델명 자동 수정)
                    from ui.widgets.ai_assistant_widget import AIAssistantWidget
                    normalized_model = AIAssistantWidget._normalize_model_name(model_name)
                    if normalized_model != model_name:
                        self.logger.info(f"모델명 정규화: '{model_name}' → '{normalized_model}'")
                    
                    widget = AIAssistantWidget(
                        tab,
                        ai_manager=ai_manager,
                        assistant_model_name=normalized_model,
                        colors=dict(_FIXED_COLORS),
                    )
                    # 대시보드 참조 연결 (거래 상황 수집용)
                    widget.parent_dashboard = self
                    # 현재 서비스 컨텍스트 동기화
                    try:
                        widget.set_service_context(getattr(self, 'current_service', 'blockchain'), announce=False)
                    except Exception:
                        pass
                except Exception as e:
                    self.logger.error(f"AI 어시스턴트 위젯 생성 오류: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
                    widget = None
                if widget is not None:
                    try:
                        widget.pack(fill="both", expand=True, padx=12, pady=12)
                        self._register_tab_widget(name, "ai_assistant_widget", widget)
                        return
                    except Exception as e:
                        self.logger.error(f"AI 어시스턴트 위젯 배치 오류: {e}")
                        pass
                frame = self._create_card_frame(tab, corner_radius=16)
                frame.pack(fill="both", expand=True, padx=12, pady=12)
                ctk.CTkLabel(frame, text=name, font=self._get_safe_font("subheading", ctk.CTkFont(size=15, weight="bold")), text_color=self._color('text_primary', '#f9fafb')).pack(anchor="w", padx=12, pady=(12, 6))
                ctk.CTkLabel(frame, text="AI 어시스턴트 위젯을 불러올 수 없습니다. (폴백)", font=self._get_safe_font("body", ctk.CTkFont(size=13)), text_color=self._color('text_secondary', '#cbd5e1')).pack(anchor="w", padx=12, pady=(0, 8))
        except Exception:
            pass

    def _get_live_ai_assistant(self) -> Optional[Any]:
        """파괴된 Tcl 입력창을 재사용하지 않고 살아 있는 어시스턴트를 반환한다."""
        assistant = getattr(self, 'ai_assistant_widget', None)
        chat_input = getattr(assistant, 'chat_input', None) if assistant is not None else None
        if self._widget_alive(assistant) and self._widget_alive(chat_input):
            return assistant

        self._invalidate_tab_widget_reference("AI 어시스턴트")
        self._ensure_ai_assistant_tab()
        assistant = getattr(self, 'ai_assistant_widget', None)
        chat_input = getattr(assistant, 'chat_input', None) if assistant is not None else None
        if self._widget_alive(assistant) and self._widget_alive(chat_input):
            return assistant
        return None

    def _ensure_custom_strategy_tab(self) -> None:
        """AI 커스텀 전략 입력·분석·버전 관리 화면을 보장한다."""
        try:
            if not getattr(self, 'tab_widget', None):
                return
            name = "AI 커스텀"
            tab = self._get_or_add_tab(name)
            self._clear_tab_children(tab)

            from ui.widgets.custom_strategy_widget import CustomStrategyWidget
            widget = CustomStrategyWidget(tab, dashboard=self, settings=self.settings)
            widget.pack(fill="both", expand=True)
            self._register_tab_widget(name, "custom_strategy_widget", widget)
        except Exception as exc:
            try:
                self.logger.warning(f"AI 커스텀 전략 탭 생성 실패: {exc}")
                if os.environ.get('NOAHAI_UI_VERIFY_TAB'):
                    import sys as _sys
                    _sys.__stdout__.write(f"[UI_VERIFY] AI 커스텀 전략 탭 생성 실패: {exc}\n")
                    _sys.__stdout__.flush()
            except Exception:
                pass

    def _ensure_life_finance_tab(self) -> None:
        """'생활금융 서비스' 탭을 보장하고 실행형 위젯을 삽입합니다."""
        try:
            if not getattr(self, 'tab_widget', None):
                return
            name = "생활금융 서비스"
            created = not self._tab_exists(name)
            tab = self._get_or_add_tab(name)
            if created or not tab.winfo_children():
                widget = None
                widget_error = None
                try:
                    life_finance_cls = LifeFinanceWidget
                    # 앱 시작 시 import 실패한 경우, 탭 생성 시점에 한 번 더 지연 import 시도
                    if life_finance_cls is None:
                        try:
                            from ui.widgets.life_finance_widget import LifeFinanceWidget as _LifeFinanceWidget
                            life_finance_cls = _LifeFinanceWidget
                        except Exception as import_err:
                            widget_error = import_err

                    if life_finance_cls is not None:
                        widget = life_finance_cls(tab)
                except Exception as e:
                    self.logger.error(f"생활금융 위젯 생성 오류: {e}")
                    widget_error = e
                    widget = None

                if widget is not None:
                    widget.pack(fill="both", expand=True, padx=10, pady=10)
                    setattr(self, 'life_finance_widget', widget)
                    return

                frame = self._create_card_frame(tab, corner_radius=16)
                frame.pack(fill="both", expand=True, padx=12, pady=12)
                ctk.CTkLabel(
                    frame,
                    text="생활금융 서비스",
                    font=self._get_safe_font("subheading", ctk.CTkFont(size=15, weight="bold")),
                    text_color=self._color('text_primary', '#f9fafb')
                ).pack(anchor="w", padx=12, pady=(12, 6))
                ctk.CTkLabel(
                    frame,
                    text=(
                        "생활금융 위젯을 불러올 수 없습니다.\n"
                        f"오류: {widget_error if widget_error else '원인 미상'}\n\n"
                        "점검 가이드:\n"
                        "1) 앱 재시작 후 다시 시도\n"
                        "2) 설정 > 거래소 선택 탭의 생활금융 관련 항목이 저장되어 있는지 확인\n"
                        "3) 로그에서 '생활금융 위젯 생성 오류' 항목 확인"
                    ),
                    font=self._get_safe_font("body", ctk.CTkFont(size=13)),
                    text_color=self._color('text_secondary', '#cbd5e1')
                ).pack(anchor="w", padx=12, pady=(0, 8))
                ctk.CTkButton(
                    frame,
                    text="생활금융 위젯 다시 시도",
                    height=32,
                    command=lambda: self._retry_life_finance_widget(tab),
                    fg_color=self._color('primary', '#1f6feb'),
                    hover_color=self._color('primary', '#1f6feb'),
                    text_color=self._color('text_primary', '#f9fafb')
                ).pack(anchor="w", padx=12, pady=(0, 10))
        except Exception:
            pass

    def _retry_life_finance_widget(self, tab) -> None:
        """생활금융 위젯 재생성 시도."""
        try:
            for child in tab.winfo_children():
                child.destroy()
        except Exception:
            pass
        self._ensure_life_finance_tab()

    def _ensure_alpha_arena_tab(self) -> None:
        """'AlphaArena' 탭을 보장하고 통합된 AlphaArenaWidget을 삽입합니다.
        설정에서 alpha_arena.enabled가 true일 때만 생성됩니다."""
        try:
            # 설정 파일에서 최신 설정 로드 (self.settings가 최신이 아닐 수 있음)
            try:
                from config.settings import load_settings
                current_settings = load_settings()
                # alpha_arena 설정만 최신으로 업데이트
                if 'alpha_arena' in current_settings:
                    if 'alpha_arena' not in self.settings:
                        self.settings['alpha_arena'] = {}
                    self.settings['alpha_arena'].update(current_settings['alpha_arena'])
            except Exception as reload_err:
                self.logger.debug(f"설정 파일 재로드 실패 (기존 설정 사용): {reload_err}")
            
            # 설정에서 alpha_arena.enabled 확인
            arena_settings = self.settings.get('alpha_arena', {})
            if not arena_settings.get('enabled', False):
                # 설정에서 비활성화되어 있으면 탭 생성하지 않음
                # 기존 탭이 있으면 제거 (선택 사항)
                return
            
            if not getattr(self, 'tab_widget', None):
                return
            name = "AlphaArena"
            created = not self._tab_exists(name)
            tab = self._get_or_add_tab(name)
            if created or not tab.winfo_children():
                widget = None
                try:
                    self.logger.info("AlphaArena 위젯 생성 시작...")
                    from ui.widgets.alpha_arena_widget import AlphaArenaWidget
                    from api.binance_client import BinanceClient
                    from trading.ai.ai_manager import AIManager

                    AlphaArenaRunner = None
                    try:
                        from trading.alpha_arena import AlphaArenaRunner as _AlphaArenaRunner
                        AlphaArenaRunner = _AlphaArenaRunner
                    except Exception as runner_import_err:
                        self.logger.warning(f"AlphaArenaRunner import 실패(위젯 단독 모드로 진행): {runner_import_err}")

                    self.logger.info("AlphaArena 모듈 import 완료")
                    
                    # BinanceClient 초기화 (대시보드의 것을 재사용)
                    binance_client = getattr(self, 'binance_client', None)
                    if binance_client is None:
                        self.logger.warning("BinanceClient가 없어 AlphaArenaWidget에 전달할 수 없습니다.")
                        # Fallback: settings에서 API 키 로드 후 새로 생성 시도
                        try:
                            from config.settings import load_settings
                            current_settings = load_settings()
                            api_key = current_settings.get('binance_api_key', '')
                            secret_key = current_settings.get('binance_secret_key', '')
                            if api_key and secret_key:
                                binance_client = BinanceClient(api_key=api_key, secret_key=secret_key)
                                self.logger.info("AlphaArena용 BinanceClient 재초기화 시도 완료.")
                        except Exception as e:
                            self.logger.error(f"AlphaArena용 BinanceClient 재초기화 실패: {e}")

                    # AIManager 초기화 (Alpha Arena 전용 - 선택한 엔진에 맞는 API 키 사용)
                    ai_manager = None
                    try:
                        from config.settings import load_settings
                        current_settings = load_settings()
                        arena_settings = current_settings.get('alpha_arena', {})
                        engine = arena_settings.get('engine', 'deepseek-v4-flash')
                        
                        # 선택한 엔진에 맞는 API 키 가져오기
                        base_url = None
                        if engine in ('deepseek-3.1', 'deepseek-chat-v3.1', 'deepseek-chat', 'deepseek-v4-flash'):
                            api_key = arena_settings.get('deepseek_api_key', '') or current_settings.get('alphaarena_deepseek_api_key', '')
                            model = 'deepseek-v4-flash'
                            base_url = 'https://api.deepseek.com'  # DeepSeek API 엔드포인트
                        elif engine == 'deepseek-v4-pro':
                            api_key = arena_settings.get('deepseek_api_key', '') or current_settings.get('alphaarena_deepseek_api_key', '')
                            model = 'deepseek-v4-pro'
                            base_url = 'https://api.deepseek.com'
                        elif engine == 'qwen3-max':
                            api_key = arena_settings.get('qwen_api_key', '') or current_settings.get('alphaarena_alibaba_api_key', '')
                            # DashScope OpenAI-compatible 엔드포인트를 기본 사용
                            model = arena_settings.get('qwen_model', 'qwen-plus')
                            base_url = arena_settings.get(
                                'qwen_base_url',
                                'https://dashscope-intl.aliyuncs.com/compatible-mode/v1'
                            )
                        else:
                            # 폴백: OpenAI API 키 사용
                            api_key = current_settings.get('openai_api_key', '')
                            model = current_settings.get('openai_model', 'gpt-4o-mini')
                            base_url = None  # OpenAI는 기본 엔드포인트 사용
                        
                        if api_key:
                            ai_manager = AIManager(api_key=api_key, model=model, base_url=base_url)
                            self.logger.info(f"AlphaArena용 AIManager 초기화 완료 (엔진: {engine}, base_url: {base_url})")
                        else:
                            self.logger.warning(f"AlphaArena용 API 키가 없습니다 (엔진: {engine}). 설정에서 API 키를 입력해주세요.")
                    except Exception as e:
                        self.logger.error(f"AlphaArena용 AIManager 초기화 실패: {e}")
                        import traceback
                        self.logger.error(traceback.format_exc())

                    # Recorder 인스턴스 미리 가져오기 (스코프 문제 해결)
                    recorder = getattr(self, 'recorder', None)
                    
                    # AlphaArenaRunner 초기화
                    alpha_arena_runner = None
                    if AlphaArenaRunner and binance_client and ai_manager:
                        alpha_arena_runner = AlphaArenaRunner(
                            binance_client=binance_client,
                            ai_manager=ai_manager,
                            settings=self.settings, # 전체 설정 전달
                            recorder=recorder  # Recorder 전달
                        )
                        self.logger.info("AlphaArenaRunner 초기화 완료.")
                    elif not AlphaArenaRunner:
                        self.logger.warning("AlphaArenaRunner 모듈이 없어 위젯 단독 모드로 실행합니다.")
                    else:
                        self.logger.warning("BinanceClient 또는 AIManager가 없어 AlphaArenaRunner를 초기화할 수 없습니다.")

                    widget = AlphaArenaWidget(
                        tab, 
                        binance_client=binance_client, 
                        ai_manager=ai_manager, 
                        alpha_arena_runner=alpha_arena_runner,
                        settings=self.settings, # 전체 설정 전달
                        recorder=recorder  # Recorder 전달 (데이터베이스 저장용)
                    )
                    self._register_tab_widget(name, "alpha_arena_widget", widget)
                    self.logger.info("AlphaArena 위젯 생성 완료.")
                except Exception as e:
                    self.logger.error(f"AlphaArena 위젯 생성 오류: {e}")
                    import traceback
                    error_detail = traceback.format_exc()
                    self.logger.error(f"상세 오류 정보:\n{error_detail}")
                    # 빌드 환경에서도 확인 가능하도록 print도 출력
                    print(f"[ERROR] AlphaArena 위젯 생성 실패: {e}")
                    print(f"[ERROR] 상세 정보:\n{error_detail}")
                    widget = None
                if widget is not None:
                    try:
                        widget.pack(fill="both", expand=True, padx=12, pady=12)
                        self.logger.info("AlphaArena 위젯 배치 완료")
                        return
                    except Exception as e:
                        self.logger.error(f"AlphaArena 위젯 배치 오류: {e}")
                        import traceback
                        error_detail = traceback.format_exc()
                        self.logger.error(f"상세 오류 정보:\n{error_detail}")
                        print(f"[ERROR] AlphaArena 위젯 배치 실패: {e}")
                        print(f"[ERROR] 상세 정보:\n{error_detail}")
                        pass
                # 폴백 UI 표시 (위젯 생성 실패 시)
                self.logger.warning("AlphaArena 위젯 생성 실패, 폴백 UI 표시")
                frame = self._create_card_frame(tab, corner_radius=16)
                frame.pack(fill="both", expand=True, padx=12, pady=12)
                ctk.CTkLabel(frame, text=name, font=self._get_safe_font("subheading", ctk.CTkFont(size=15, weight="bold")), text_color=self._color('text_primary', '#f9fafb')).pack(anchor="w", padx=12, pady=(12, 6))
                ctk.CTkLabel(frame, text="AlphaArena 위젯을 불러올 수 없습니다. (폴백)", font=self._get_safe_font("body", ctk.CTkFont(size=13)), text_color=self._color('text_secondary', '#cbd5e1')).pack(anchor="w", padx=12, pady=(0, 8))
        except Exception:
            pass

    # ===== 코인 정보/거래 통계/시장 트렌드 탭 메서드들 =====
    def _ensure_coin_info_tab(self) -> None:
        """코인 정보 탭을 기본 탭으로 보장 (사용자 제공 원본 코드)"""
        try:
            print("[DEBUG] _ensure_coin_info_tab 시작")
            if not hasattr(self, 'tab_widget') or self.tab_widget is None:
                print("[DEBUG] tab_widget이 없음")
                return

            tab_name = "코인 정보"
            tab = self._get_or_add_tab(tab_name)
            self._clear_tab_children(tab)

            # 코인 정보는 여러 독립 분석 영역이 이어지므로 전체를 스크롤한다.
            main_container = ctk.CTkScrollableFrame(
                tab,
                fg_color="#0b1120",
                corner_radius=10,
            )
            main_container.pack(fill="both", expand=True, padx=10, pady=10)

            # 코인 정보 제목
            coin_info_title = ctk.CTkLabel(
                main_container,
                text="선택된 거래 코인 정보 (AI 평가 결과)",
                font=self._get_safe_font("title")
            )
            coin_info_title.pack(pady=10)

            # ===== 코인 직접 검색 & 분석 패널 =====
            coin_search_frame = ctk.CTkFrame(main_container, fg_color="#1a1f2e", corner_radius=12, border_width=2, border_color="#374151")
            coin_search_frame.pack(fill="x", padx=5, pady=(0, 10))

            ctk.CTkLabel(
                coin_search_frame,
                text="심볼 직접 분석",
                font=self._get_safe_font("subtitle"),
                text_color="#f0f0f0"
            ).pack(side="left", padx=15, pady=12)

            self.coin_search_entry = ctk.CTkEntry(
                coin_search_frame,
                placeholder_text="예: BTCUSDT, ETHUSDT",
                font=self._get_safe_font("body"),
                width=220
            )
            self.coin_search_entry.pack(side="left", padx=5, pady=10)
            self.coin_search_entry.bind("<Return>", lambda e: self._search_coin_symbol())

            ctk.CTkButton(
                coin_search_frame,
                text="분석",
                command=self._search_coin_symbol,
                font=self._get_safe_font("button"),
                width=90
            ).pack(side="left", padx=5, pady=10)

            ctk.CTkLabel(
                coin_search_frame,
                text="NoahAI가 실시간 분석합니다",
                font=self._get_safe_font("small"),
                text_color="#9ca3af"
            ).pack(side="right", padx=15, pady=10)

            # 코인 검색 결과 표시 영역
            self.coin_search_results = ctk.CTkScrollableFrame(
                main_container,
                corner_radius=12,
                fg_color="#0b1120",
                border_color="#1f2937",
                border_width=2,
                label_text="코인 분석 결과",
                height=200,
            )
            self.coin_search_results.pack(fill="x", padx=5, pady=(0, 8))
            self._register_tab_widget(tab_name, "coin_search_results", self.coin_search_results)

            # evaluator 점수 테이블 헤더
            evaluator_header_frame = ctk.CTkFrame(main_container)
            evaluator_header_frame.pack(fill="x", pady=(0, 5))

            # AI 평가 결과를 위한 컬럼 구조 (실제 데이터와 일치)
            evaluator_headers = ["코인", "AI종합점수", "변동성점수", "거래량점수", "기술점수", "트렌드점수", "리스크점수"]
            col_widths = [150, 90, 90, 90, 90, 90, 90]
            for i, header in enumerate(evaluator_headers):
                label = ctk.CTkLabel(
                    evaluator_header_frame,
                    text=header,
                    font=self._get_safe_font("table_header"),
                    width=col_widths[i] if i < len(col_widths) else 90
                )
                label.grid(row=0, column=i, padx=3, pady=3, sticky="ew")
                evaluator_header_frame.grid_columnconfigure(i, weight=1)

            # evaluator 점수 테이블 데이터
            self.evaluator_scroll = ctk.CTkScrollableFrame(
                main_container,
                corner_radius=12,
                fg_color="#0b1120",
                border_color="#1f2937",
                border_width=2,
                height=220,
            )
            self.evaluator_scroll.pack(fill="x", pady=5)
            self._register_tab_widget(tab_name, "evaluator_scroll", self.evaluator_scroll)

            # 버튼 행 (코인 선정 실행 + 새로고침 나란히)
            btn_row = ctk.CTkFrame(main_container, fg_color="transparent")
            btn_row.pack(pady=10)

            coin_select_btn = ctk.CTkButton(
                btn_row,
                text="코인 선정 실행",
                command=self._run_coin_selection,
                font=self._get_safe_font("button"),
                fg_color="#1d4ed8",
                hover_color="#1e40af",
            )
            coin_select_btn.pack(side="left", padx=(0, 8))

            refresh_button = ctk.CTkButton(
                btn_row,
                text="코인 정보 새로고침",
                command=self._refresh_coin_info,
                font=self._get_safe_font("button")
            )
            refresh_button.pack(side="left")

            # 초기 데이터
            print("[DEBUG] _update_coin_info 호출 시작")
            self._update_coin_info()
            print("코인 정보 탭 기본 생성 완료")
        except Exception as e:
            print(f"[DEBUG] _ensure_coin_info_tab 오류: {e}")
            import traceback
            print(f"[DEBUG] 상세 오류: {traceback.format_exc()}")
            try:
                self.logger.error(f"_ensure_coin_info_tab 오류: {e}")
            except Exception:
                print(f"_ensure_coin_info_tab 오류: {e}")

    def _ensure_trading_stats_tab(self) -> None:
        """거래 통계 탭을 기본 탭으로 보장 (사용자 제공 원본 코드)"""
        try:
            if not hasattr(self, 'tab_widget') or self.tab_widget is None:
                return

            tab_name = "거래 통계"
            tab = self._get_or_add_tab(tab_name)
            self._clear_tab_children(tab)

            # 표 안쪽만 스크롤한다. 바깥까지 CTkScrollableFrame으로 만들면
            # 중첩 스크롤의 기본 높이에 표가 눌려 2~3행만 보이고 아래 공간이
            # 비는 문제가 생긴다.
            main_container = ctk.CTkFrame(
                tab,
                fg_color="#0b1120",
                corner_radius=10,
            )
            main_container.pack(fill="both", expand=True, padx=10, pady=10)

            # 제목과 거래소 필터를 한 줄에 배치해 표에 더 많은 높이를 확보한다.
            filter_frame = ctk.CTkFrame(main_container, fg_color="transparent")
            filter_frame.pack(fill="x", pady=(4, 8))

            stats_title = ctk.CTkLabel(
                filter_frame,
                text="거래 통계 (데이터베이스 기준)",
                font=self._get_safe_font("title")
            )
            stats_title.pack(side="left", padx=(4, 18))

            filter_label = ctk.CTkLabel(
                filter_frame,
                text="거래소 필터",
                font=self._get_safe_font("body"),
                text_color=self._color('text_secondary', '#9ca3af')
            )
            filter_label.pack(side="left", padx=(0, 8))

            exchange_options = self._get_trading_stats_exchange_options()
            previous_value = None
            if hasattr(self, 'trading_stats_exchange_var'):
                try:
                    previous_value = self.trading_stats_exchange_var.get()
                except Exception:
                    previous_value = None
            default_exchange = previous_value if previous_value in exchange_options else exchange_options[0]
            self.trading_stats_exchange_var = tk.StringVar(value=default_exchange)

            exchange_menu = ctk.CTkOptionMenu(
                filter_frame,
                values=exchange_options,
                variable=self.trading_stats_exchange_var,
                command=lambda _: self._update_trading_statistics(),
                width=160
            )
            exchange_menu.pack(side="left")
            self.trading_stats_exchange_menu = exchange_menu

            # 핵심 지표는 4열 한 줄 카드로 노출해 세로 공간을 아낀다.
            kpi_frame = ctk.CTkFrame(main_container, fg_color="transparent")
            kpi_frame.pack(fill="x", pady=(0, 8))
            self.trading_stats_kpi_labels = {}
            kpi_specs = [
                ("trades", "저장된 실제 체결", "0건", "#3b82f6"),
                ("win_rate", "승률", "0.0%", "#10b981"),
                ("pnl", "누적 PnL", "0.00", "#8b5cf6"),
                ("fees", "누적 Fee", "0.00", "#f59e0b"),
            ]
            for index, (key, title, value, accent) in enumerate(kpi_specs):
                card = ctk.CTkFrame(
                    kpi_frame,
                    height=70,
                    corner_radius=12,
                    fg_color="#111827",
                    border_color=accent,
                    border_width=1,
                )
                card.grid(row=0, column=index, padx=4, pady=3, sticky="nsew")
                card.grid_propagate(False)
                kpi_frame.grid_columnconfigure(index, weight=1, uniform="trade_stats_kpi")
                ctk.CTkLabel(
                    card,
                    text=title,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=self._color('text_secondary', '#9ca3af'),
                ).pack(anchor="w", padx=12, pady=(8, 0))
                value_label = ctk.CTkLabel(
                    card,
                    text=value,
                    font=ctk.CTkFont(size=17, weight="bold"),
                    text_color=accent,
                )
                value_label.pack(anchor="w", padx=12, pady=(0, 7))
                self.trading_stats_kpi_labels[key] = value_label

            # 통화별 체결금액과 평균 보유시간은 기존 4개 카드 아래의 한 줄
            # 운용 지표로 표시한다. 카드 수를 늘려 표 영역을 줄이지 않는다.
            operating_strip = ctk.CTkFrame(
                main_container,
                height=40,
                corner_radius=10,
                fg_color="#111827",
                border_color="#1f2937",
                border_width=1,
            )
            operating_strip.pack(fill="x", pady=(0, 8))
            operating_strip.pack_propagate(False)
            ctk.CTkLabel(
                operating_strip,
                text="실제 운용",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=self._color('info', '#60a5fa'),
            ).pack(side="left", padx=(12, 10))
            self.trading_stats_operating_label = ctk.CTkLabel(
                operating_strip,
                text="체결금액 USDT 0.00 · KRW 0 | 평균 보유시간 수집 대기",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=self._color('text_primary', '#f9fafb'),
            )
            self.trading_stats_operating_label.pack(side="left", fill="x", expand=True)

            # 거래 통계 테이블 헤더
            stats_header_frame = ctk.CTkFrame(main_container, height=42, corner_radius=10, fg_color="#111827")
            stats_header_frame.pack(fill="x", pady=(0, 5))

            # 비용과 순손익을 코인별로도 직접 비교할 수 있는 10개 컬럼 구조
            stats_headers = [
                "코인", "총 거래", "익절", "손절", "승률", "평균 수익률",
                "누적 PnL", "누적 Fee", "최대 수익", "최대 손실",
            ]
            self._stats_header_labels = []
            for i, header in enumerate(stats_headers):
                label = ctk.CTkLabel(
                    stats_header_frame,
                    text=header,
                    font=ctk.CTkFont(size=13, weight="bold")
                )
                label.grid(row=0, column=i, padx=7, pady=9, sticky="ew")
                stats_header_frame.grid_columnconfigure(i, weight=1)
                self._stats_header_labels.append(label)

            # 거래 통계 테이블 데이터
            self.trading_stats_scroll = ctk.CTkScrollableFrame(
                main_container,
                corner_radius=12,
                fg_color="#0b1120",
                border_color="#1f2937",
                border_width=2
            )
            self.trading_stats_scroll.pack(fill="both", expand=True, pady=5)
            self._register_tab_widget(tab_name, "trading_stats_scroll", self.trading_stats_scroll)

            # 버튼 행
            button_row = ctk.CTkFrame(main_container, fg_color="transparent")
            button_row.pack(pady=10)

            refresh_button = ctk.CTkButton(
                button_row,
                text="거래 통계 새로고침",
                command=self._refresh_trading_stats,
                font=self._get_safe_font("button")
            )
            refresh_button.pack(side="left", padx=(0, 6))

            import_button = ctk.CTkButton(
                button_row,
                text="거래 통계 가져오기",
                command=self._import_trading_stats_from_api,
                font=self._get_safe_font("button"),
                fg_color=self._color('info', '#2563eb'),
                hover_color=self._hover_from(self._color('info', '#2563eb')),
                text_color=self._color('text_on_primary', '#ffffff')
            )
            import_button.pack(side="left")
            self.trading_stats_import_button = import_button

            # 상태 라벨
            self.trading_stats_status_label = ctk.CTkLabel(
                main_container,
                text="",
                font=self._get_safe_font("small"),
                text_color=self._color('text_secondary', '#9ca3af')
            )
            self.trading_stats_status_label.pack(pady=(0, 8))

            # 초기 데이터
            self._update_trading_statistics()
            print("거래 통계 탭 기본 생성 완료")
        except Exception as e:
            try:
                self.logger.error(f"_ensure_trading_stats_tab 오류: {e}")
            except Exception:
                print(f"_ensure_trading_stats_tab 오류: {e}")

    def _ensure_trend_tab(self) -> None:
        """시장 트렌드 탭을 기본 탭으로 보장 (사용자 제공 원본 코드)"""
        try:
            if not hasattr(self, 'tab_widget') or self.tab_widget is None:
                return

            tab_name = "시장 트렌드"
            tab = self._get_or_add_tab(tab_name)
            self._clear_tab_children(tab)

            # 새로운 시장 트렌드 위젯 사용
            from ui.widgets.market_trend_widget import MarketTrendWidget
            trend_widget = MarketTrendWidget(tab, dashboard_ref=self, colors=dict(_FIXED_COLORS))
            trend_widget.pack(fill="both", expand=True, padx=10, pady=10)
            self._register_tab_widget(tab_name, "market_trend_widget", trend_widget)
            self.demo_widget = None

            # 탭 생성 직후 1회 강제 갱신으로 '수집 대기' 상태를 빠르게 해소한다.
            try:
                if hasattr(trend_widget, 'refresh_trend_data'):
                    trend_widget.refresh_trend_data(force_refresh=True)
            except Exception:
                pass

        except Exception as e:
            self.logger.error(f"_ensure_trend_tab 오류: {e}")
            print(f"_ensure_trend_tab 오류: {e}")

    def _run_coin_selection(self):
        """코인 선정 실행 버튼 핸들러"""
        import threading
        try:
            main_app = getattr(self, 'main_app', None)
            if main_app and hasattr(main_app, 'select_trading_coins'):
                self.add_log("코인 선정 시작...")
                def _run():
                    try:
                        main_app.select_trading_coins()
                        self.add_log("코인 선정 완료")
                    except Exception as e:
                        self.add_log(f"코인 선정 오류: {e}", "ERROR")
                threading.Thread(target=_run, daemon=True).start()
            else:
                self.add_log("코인 선정을 실행하려면 먼저 자동매매를 시작하세요.", "WARNING")
        except Exception as e:
            print(f"_run_coin_selection 오류: {e}")

    def _refresh_coin_info(self):
        """코인 정보 새로고침"""
        try:
            self._update_coin_info()
        except Exception as e:
            print(f"코인 정보 새로고침 오류: {e}")

    def _search_coin_symbol(self) -> None:
        """코인 심볼 직접 분석"""
        try:
            if not hasattr(self, 'coin_search_entry'):
                return

            raw = self.coin_search_entry.get().strip().upper()
            if not raw:
                return

            # 심볼 정규화 (USDT 미입력 시 자동 추가)
            symbol = raw if raw.endswith('USDT') else raw + 'USDT'

            if not hasattr(self, 'coin_search_results'):
                return

            for w in self.coin_search_results.winfo_children():
                w.destroy()

            ctk.CTkLabel(
                self.coin_search_results,
                text=f"{symbol} 분석 중...",
                font=self._get_safe_font("body"),
                text_color="#cbd5e1"
            ).pack(pady=10)
            self.coin_search_results.update()

            # Analyzer로 분석 실행
            result = None
            if hasattr(self, 'analyzer') and self.analyzer is not None:
                try:
                    result = self.analyzer.analyze_symbol(symbol)
                except Exception as e:
                    print(f"코인 분석 오류: {e}")

            for w in self.coin_search_results.winfo_children():
                w.destroy()

            if result is None:
                ctk.CTkLabel(
                    self.coin_search_results,
                    text=f"'{symbol}' 분석 데이터를 가져올 수 없습니다.\n거래소 연결 상태와 심볼을 확인하세요.",
                    font=self._get_safe_font("body"),
                    text_color="#ef4444",
                    justify="center"
                ).pack(pady=20)
                return

            self._display_coin_analysis_card(symbol, result)

        except Exception as e:
            print(f"코인 검색 오류: {e}")

    def _display_coin_analysis_card(self, symbol: str, result) -> None:
        """코인 분석 결과를 카드 형태로 표시"""
        try:
            if not hasattr(self, 'coin_search_results'):
                return

            card = ctk.CTkFrame(
                self.coin_search_results,
                fg_color="#1a1f2e",
                corner_radius=12,
                border_width=2,
                border_color="#374151"
            )
            card.pack(fill="x", padx=5, pady=8)

            # 상단 헤더
            header = ctk.CTkFrame(card, fg_color="transparent")
            header.pack(fill="x", padx=15, pady=(12, 4))

            ctk.CTkLabel(
                header,
                text=f"{symbol} 코인 분석",
                font=self._get_safe_font("subtitle"),
                text_color="#fbbf24"
            ).pack(side="left", anchor="w")

            # 자동매매 추가 버튼
            ctk.CTkButton(
                header,
                text="자동매매 추가",
                width=130,
                height=30,
                font=self._get_safe_font("small"),
                fg_color="#065f46",
                hover_color="#047857",
                command=lambda s=symbol: self._add_coin_to_auto_trade(s)
            ).pack(side="right", padx=(8, 0))

            # 가격 정보
            market_frame = ctk.CTkFrame(card, fg_color="transparent")
            market_frame.pack(fill="x", padx=15, pady=4)

            # AnalysisResult 또는 dict 처리
            if hasattr(result, 'current_price'):
                current_price = result.current_price
                signal_str = str(result.signal).split('.')[-1] if hasattr(result.signal, 'value') else str(result.signal)
                confidence = result.confidence
                trend_str = str(result.trend).split('.')[-1] if hasattr(result.trend, 'value') else str(result.trend)
                volatility = result.volatility
                reasoning = result.reasoning or ''
                support = result.support_level
                resistance = result.resistance_level
            else:
                current_price = result.get('current_price', 0)
                signal_str = result.get('signal', 'HOLD')
                confidence = result.get('confidence', 0.5)
                trend_str = result.get('trend', 'N/A')
                volatility = result.get('volatility', 0)
                reasoning = result.get('reasoning', '')
                support = result.get('support_level')
                resistance = result.get('resistance_level')

            signal_color = {"LONG": "#22c55e", "SHORT": "#ef4444"}.get(signal_str, "#fbbf24")

            price_text = f"현재가: {current_price:,.4f}" if current_price else "현재가: N/A"
            ctk.CTkLabel(market_frame, text=price_text, font=self._get_safe_font("body"), text_color="#e5e7eb").pack(anchor="w")

            ctk.CTkLabel(
                market_frame,
                text=f"신호: {signal_str}  신뢰도: {confidence*100:.1f}%",
                font=self._get_safe_font("body"),
                text_color=signal_color
            ).pack(anchor="w", pady=(2, 0))

            ctk.CTkLabel(
                market_frame,
                text=f"트렌드: {trend_str}  변동성: {volatility:.2f}%",
                font=self._get_safe_font("small"),
                text_color="#cbd5e1"
            ).pack(anchor="w", pady=(2, 0))

            if support and resistance:
                ctk.CTkLabel(
                    market_frame,
                    text=f"지지: {support:,.4f}  저항: {resistance:,.4f}",
                    font=self._get_safe_font("small"),
                    text_color="#94a3b8"
                ).pack(anchor="w", pady=(2, 0))

            if reasoning:
                ctk.CTkLabel(
                    card,
                    text=f"{str(reasoning)[:180]}",
                    font=self._get_safe_font("small"),
                    text_color="#94a3b8",
                    wraplength=420,
                    justify="left"
                ).pack(anchor="w", padx=15, pady=(0, 10))

        except Exception as e:
            print(f"코인 분석 카드 오류: {e}")

    def _add_coin_to_auto_trade(self, symbol: str) -> None:
        """현재 거래소의 사용자 고정 유니버스에 코인을 추가한다."""
        try:
            symbol = symbol.upper().strip()
            exchange = str(
                self._get_active_exchange_from_tab()
                or (self.settings or {}).get('selected_exchange', 'binance')
                or 'binance'
            ).strip().lower()
            selection = dict((self.settings or {}).get('crypto_selection', {}) or {})
            by_exchange = dict(selection.get('manual_symbols_by_exchange', {}) or {})
            pinned = [
                str(value or '').strip().upper()
                for value in list(by_exchange.get(exchange, []) or [])
                if str(value or '').strip()
            ]
            if symbol in pinned:
                self._show_toast(f"{symbol}은(는) 이미 {exchange.upper()} 고정 종목입니다.")
                return

            pinned.append(symbol)
            by_exchange[exchange] = list(dict.fromkeys(pinned))
            selection['manual_symbols_by_exchange'] = by_exchange
            if not self._persist_runtime_subsettings('crypto_selection', selection):
                self._show_toast("고정 종목 설정 저장에 실패했습니다.")
                return

            current = list(getattr(self, 'selected_coins', []))
            existing = {
                str(c if isinstance(c, str) else c.get('symbol', '')).strip().upper()
                for c in current
            }
            if symbol not in existing:
                current.append({
                    'symbol': symbol,
                    '_selection_source': 'user_pinned',
                    '_selection_target': exchange,
                    '_selection_asset_class': 'crypto',
                })
            self.selected_coins = current
            app = getattr(self, 'main_app', None)
            if app is not None:
                if not hasattr(app, 'selected_coins_by_exchange'):
                    app.selected_coins_by_exchange = {}
                app.selected_coins_by_exchange[exchange] = list(current)
                if exchange == str(getattr(app, 'current_exchange', exchange) or exchange).lower():
                    app.selected_coins = list(current)
            self._show_toast(
                f"{symbol}을(를) {exchange.upper()} 고정 종목에 추가했습니다. "
                "다음 선정부터 자동 후보보다 우선합니다."
            )
            print(f"코인 고정 종목 추가: {exchange}:{symbol}")
        except Exception as e:
            print(f"코인 자동매매 추가 오류: {e}")

    def _add_stock_to_auto_trade(self, symbol: str) -> None:
        """주식/ETF를 실제 자동매매 분석 유니버스 설정에 추가한다."""
        try:
            symbol = symbol.upper().strip()
            stock_settings = dict((self.settings or {}).get('stock_auto_trading', {}) or {})
            symbols = [
                str(value or '').strip().upper()
                for value in list(stock_settings.get('symbols', []) or [])
                if str(value or '').strip()
            ]
            legacy_watchlist = [
                str(value or '').strip().upper()
                for value in list(stock_settings.get('watchlist', []) or [])
                if str(value or '').strip()
            ]
            symbols = list(dict.fromkeys(symbols + legacy_watchlist))
            if symbol in symbols:
                self._show_toast(f"{symbol}은(는) 이미 자동매매 감시 목록에 있습니다.")
                return
            symbols.append(symbol)
            # symbols가 실행 정본이다. watchlist는 기존 설정과의 호환을 위해 동기화한다.
            stock_settings['symbols'] = list(dict.fromkeys(symbols))
            stock_settings['watchlist'] = list(stock_settings['symbols'])
            if not self._persist_runtime_subsettings('stock_auto_trading', stock_settings):
                self._show_toast("주식 자동매매 종목 설정 저장에 실패했습니다.")
                return
            self._show_toast(f"{symbol}을(를) 주식 자동매매 감시 목록에 추가했습니다.")
            print(f"주식 자동매매 추가: {symbol}")
        except Exception as e:
            print(f"주식 자동매매 추가 오류: {e}")

    def _show_toast(self, message: str, duration_ms: int = 3000) -> None:
        """화면 우하단에 간단한 토스트 메시지 표시"""
        try:
            toast = ctk.CTkLabel(
                self,
                text=message,
                fg_color="#1e3a5f",
                corner_radius=8,
                font=self._get_safe_font("small"),
                text_color="#e2e8f0",
                padx=12,
                pady=6
            )
            toast.place(relx=0.98, rely=0.97, anchor="se")
            self.after(duration_ms, lambda: toast.destroy() if toast.winfo_exists() else None)
        except Exception:
            print(f"ℹ{message}")

    def _refresh_trading_stats(self):
        """거래 통계 새로고침"""
        try:
            self._update_trading_statistics()
        except Exception as e:
            print(f"거래 통계 새로고침 오류: {e}")

    # ===== 주식/ETF용 탭 메서드들 =====
    def _get_stock_asset_mode(self) -> str:
        """현재 증권 표시 모드(all/stock/etf)를 반환합니다."""
        mode = str((self.settings or {}).get('stock_asset_mode', 'all') or 'all').strip().lower()
        if mode in {'stock', 'etf'}:
            return mode
        return 'all'

    def _get_stock_asset_mode_label(self) -> str:
        return {
            'all': '통합',
            'stock': '주식만',
            'etf': 'ETF만',
        }.get(self._get_stock_asset_mode(), '통합')

    def _stock_mode_matches(self, is_etf: bool) -> bool:
        mode = self._get_stock_asset_mode()
        if mode == 'stock':
            return not is_etf
        if mode == 'etf':
            return bool(is_etf)
        return True

    def _get_stock_search_placeholder(self) -> str:
        mode = self._get_stock_asset_mode()
        if mode == 'stock':
            return '예: 005930 (삼성전자), 207940 (삼성바이오)'
        if mode == 'etf':
            return '예: 069500 (KODEX 200), 114800 (KODEX 인버스)'
        return '예: 005930 (삼성전자), 069500 (KODEX 200)'

    def _persist_runtime_setting(self, key: str, value: Any) -> bool:
        """런타임 설정을 settings.json과 self.settings에 함께 반영합니다."""
        try:
            from config.settings import load_settings, save_settings

            current_settings = load_settings()
            current_settings[key] = value
            if save_settings(current_settings):
                self.settings[key] = value
                return True
        except Exception as exc:
            self.logger.warning(f"설정 저장 실패 ({key}): {exc}")
        return False

    def _persist_runtime_subsettings(self, key: str, value: Dict[str, Any]) -> bool:
        """중첩 설정(dict)을 settings.json과 self.settings에 함께 반영합니다."""
        try:
            from config.settings import load_settings, save_settings

            current_settings = load_settings()
            current_settings[key] = dict(value or {})
            if save_settings(current_settings):
                self.settings[key] = dict(value or {})
                return True
        except Exception as exc:
            self.logger.warning(f"중첩 설정 저장 실패 ({key}): {exc}")
        return False

    def _get_saved_asset_snapshot(self) -> Dict[str, Any]:
        snapshot = (self.settings or {}).get('asset_insight_snapshot', {}) or {}
        return snapshot if isinstance(snapshot, dict) else {}

    def _save_asset_snapshot(self, snapshot: Dict[str, Any]) -> bool:
        saved = self._persist_runtime_setting('asset_insight_snapshot', snapshot)
        if saved:
            self.settings['asset_insight_snapshot'] = snapshot
        return saved

    def _get_life_finance_profile(self) -> Dict[str, Any]:
        profile = (self.settings or {}).get('life_finance_profile', {}) or {}
        return profile if isinstance(profile, dict) else {}


    def _calculate_asset_concentration(self, asset_breakdown: Dict[str, float], total_assets: float) -> Tuple[float, str]:
        """자산군 집중도(HHI 기반 0~100)와 상태 라벨을 반환합니다."""
        if total_assets <= 0:
            return 0.0, '데이터 부족'

        weights = []
        for amount in (asset_breakdown or {}).values():
            try:
                value = max(0.0, float(amount or 0.0))
            except Exception:
                value = 0.0
            if value > 0:
                weights.append(value / total_assets)

        if not weights:
            return 0.0, '데이터 부족'

        hhi = sum(w * w for w in weights)
        concentration = min(100.0, max(0.0, hhi * 100.0))
        if concentration >= 60:
            level = '높음'
        elif concentration >= 45:
            level = '중간'
        else:
            level = '낮음'
        return concentration, level

    def _compute_two_series_correlation(self, xs: List[float], ys: List[float]) -> Optional[float]:
        if len(xs) != len(ys) or len(xs) < 3:
            return None

        n = len(xs)
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n

        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        var_x = sum((x - mean_x) ** 2 for x in xs)
        var_y = sum((y - mean_y) ** 2 for y in ys)
        if var_x <= 0 or var_y <= 0:
            return None
        return cov / math.sqrt(var_x * var_y)

    def _calculate_asset_correlation(self, db_path: str) -> Tuple[Optional[float], str]:
        """crypto/stock 일별 손익 기반 상관계수와 설명 라벨을 반환합니다."""
        if not db_path or not os.path.exists(db_path):
            return None, '데이터 없음'

        try:
            from ui.asset_insight_data import load_trade_history_metrics

            by_day = dict(load_trade_history_metrics(db_path).get('daily_pnl', {}) or {})

            xs: List[float] = []
            ys: List[float] = []
            for day in sorted(by_day.keys()):
                row = by_day.get(day, {})
                if 'crypto' in row and 'stock' in row:
                    xs.append(float(row.get('crypto', 0.0)))
                    ys.append(float(row.get('stock', 0.0)))

            corr = self._compute_two_series_correlation(xs, ys)
            if corr is None:
                return None, '표본 부족'

            abs_corr = abs(corr)
            if abs_corr >= 0.7:
                label = '강한 연동'
            elif abs_corr >= 0.4:
                label = '보통 연동'
            else:
                label = '분산 양호'
            return corr, label
        except Exception:
            return None, '계산 실패'

    def _build_rebalance_actions(
        self,
        asset_breakdown: Dict[str, float],
        total_assets: float,
        concentration: float,
        corr_value: Optional[float],
    ) -> List[str]:
        actions: List[str] = []
        if total_assets <= 0:
            return ['거래 데이터 축적 후 자산 배분 진단을 다시 실행하세요.']

        crypto_share = (float(asset_breakdown.get('암호화폐', 0.0) or 0.0) / total_assets) * 100.0
        stock_share = (float(asset_breakdown.get('주식', 0.0) or 0.0) / total_assets) * 100.0

        if concentration >= 60:
            actions.append('자산 재균형: 단일 자산군 편중이 높아 목표 비중(예: 60/40) 재조정이 필요합니다.')
        elif concentration >= 45:
            actions.append('비중 모니터링: 편중이 증가하는 구간이라 주간 점검 주기를 유지하세요.')
        else:
            actions.append('분산 유지: 현재 자산군 분산 상태가 양호하므로 급격한 비중 변경은 보류하세요.')

        if corr_value is None:
            actions.append('상관관계 분석: 데이터 표본이 부족합니다. 거래 로그를 더 축적해 연동성을 점검하세요.')
        elif abs(corr_value) >= 0.7:
            actions.append('연동 리스크: 자산군 동조화가 강해 헤지/현금 비중을 일부 확대하는 것이 유리합니다.')
        elif abs(corr_value) >= 0.4:
            actions.append('연동 모니터링: 이벤트 구간에서 동조화가 커질 수 있어 손실 한도를 보수적으로 유지하세요.')
        else:
            actions.append('분산 효과: 자산군 연동성이 낮아 리스크 분산 구조가 비교적 안정적입니다.')

        if crypto_share >= 70:
            actions.append('실행 제안: 암호화폐 비중이 높습니다. 주식/현금 비중을 단계적으로 확대해 변동성을 완화하세요.')
        elif stock_share >= 70:
            actions.append('실행 제안: 주식 비중이 높습니다. 현금성 비중 또는 비상관 자산을 보강해 급락 리스크를 줄이세요.')
        else:
            actions.append('실행 제안: 현재 비중은 균형 구간입니다. 목표 비중과 실제 비중의 괴리율만 정기 관리하세요.')

        return actions[:4]

    def _on_stock_asset_mode_change(self, selected_label: str):
        """주식/ETF 보기 모드 변경 시 저장 후 화면을 갱신합니다."""
        mode = {
            '통합': 'all',
            '주식만': 'stock',
            'ETF만': 'etf',
        }.get(str(selected_label).strip(), 'all')
        if mode == self._get_stock_asset_mode():
            return

        if self._persist_runtime_setting('stock_asset_mode', mode):
            if str(getattr(self, 'current_service', '')).lower() == 'stock':
                self._ensure_stock_info_tab()
                try:
                    self._ensure_ai_assistant_tab()
                except Exception:
                    pass

    def _get_stock_search_profile(self) -> Dict[str, Any]:
        profile = (self.settings or {}).get('stock_search_profile', {}) or {}
        if not isinstance(profile, dict):
            profile = {}

        recent_codes = profile.get('recent_codes', [])
        favorites = profile.get('favorites', [])

        if not isinstance(recent_codes, list):
            recent_codes = []
        if not isinstance(favorites, list):
            favorites = []

        norm_recent = [str(c or '').strip().upper() for c in recent_codes if str(c or '').strip()]
        norm_favorites = [str(c or '').strip().upper() for c in favorites if str(c or '').strip()]

        return {
            'recent_codes': list(dict.fromkeys(norm_recent))[:12],
            'favorites': list(dict.fromkeys(norm_favorites))[:20],
        }

    def _save_stock_search_profile(self, profile: Dict[str, Any]) -> bool:
        normalized = {
            'recent_codes': list(dict.fromkeys([
                str(c or '').strip().upper() for c in (profile.get('recent_codes', []) or []) if str(c or '').strip()
            ]))[:12],
            'favorites': list(dict.fromkeys([
                str(c or '').strip().upper() for c in (profile.get('favorites', []) or []) if str(c or '').strip()
            ]))[:20],
        }
        saved = self._persist_runtime_setting('stock_search_profile', normalized)
        if saved:
            self.settings['stock_search_profile'] = normalized
        return saved

    def _record_recent_stock_search(self, code: str) -> None:
        symbol = str(code or '').strip().upper()
        if not symbol:
            return

        profile = self._get_stock_search_profile()
        recent = [c for c in profile.get('recent_codes', []) if c != symbol]
        recent.insert(0, symbol)
        profile['recent_codes'] = recent[:12]
        self._save_stock_search_profile(profile)
        self._render_stock_search_quick_access()

    def _toggle_stock_favorite(self, code: str) -> None:
        symbol = str(code or '').strip().upper()
        if not symbol:
            return

        profile = self._get_stock_search_profile()
        favorites = list(profile.get('favorites', []))
        if symbol in favorites:
            favorites = [c for c in favorites if c != symbol]
            self._set_stock_order_status(f'즐겨찾기 해제: {symbol}', level='info')
        else:
            favorites.insert(0, symbol)
            favorites = list(dict.fromkeys(favorites))[:20]
            self._set_stock_order_status(f'즐겨찾기 추가: {symbol}', level='success')

        profile['favorites'] = favorites
        self._save_stock_search_profile(profile)
        self._render_stock_search_quick_access()

    def _run_stock_quick_search(self, code: str) -> None:
        symbol = str(code or '').strip().upper()
        if not symbol:
            return

        if hasattr(self, 'stock_search_entry') and self.stock_search_entry is not None:
            try:
                self.stock_search_entry.delete(0, 'end')
                self.stock_search_entry.insert(0, symbol)
            except Exception:
                pass
        self._render_stock_search_suggestions(symbol)
        self._search_stock_symbol()

    def _build_stock_symbol_index(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """증권 검색 자동완성용 심볼 인덱스를 구성하고 캐시합니다."""
        now_ts = time.time()
        cache = getattr(self, '_stock_symbol_index_cache', None)
        if (
            not force_refresh
            and isinstance(cache, dict)
            and float(cache.get('ts', 0) or 0) > 0
            and (now_ts - float(cache.get('ts', 0))) <= 300
        ):
            cached_items = cache.get('items', [])
            return cached_items if isinstance(cached_items, list) else []

        index_items: List[Dict[str, Any]] = []
        seen_codes: set = set()
        enabled_brokers = list((self.settings or {}).get('enabled_stock_brokers', []) or [])

        for broker in enabled_brokers:
            adapter = self._get_stock_adapter(broker)
            if not adapter:
                continue

            for source_kind, is_etf_default in (('stock', False), ('etf', True)):
                try:
                    if source_kind == 'stock' and hasattr(adapter, 'get_stock_list'):
                        raw_items = adapter.get_stock_list('ALL') or []
                    elif source_kind == 'etf' and hasattr(adapter, 'get_etf_list'):
                        raw_items = adapter.get_etf_list() or []
                    else:
                        raw_items = []
                except Exception:
                    raw_items = []

                for item in raw_items[:220]:
                    if not isinstance(item, dict):
                        continue
                    code = str(item.get('code') or item.get('symbol') or '').strip().upper()
                    if not code or code in seen_codes:
                        continue

                    name = str(item.get('name') or code).strip()
                    if not name:
                        name = code

                    is_etf = bool(item.get('is_etf', is_etf_default))
                    if hasattr(adapter, 'is_etf'):
                        try:
                            is_etf = bool(adapter.is_etf(code))
                        except Exception:
                            pass

                    index_items.append({
                        'code': code,
                        'name': name,
                        'is_etf': is_etf,
                    })
                    seen_codes.add(code)

        self._stock_symbol_index_cache = {
            'ts': now_ts,
            'items': index_items,
        }
        return index_items

    def _get_stock_search_suggestions(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        q = str(query or '').strip().upper()
        symbol_index = self._build_stock_symbol_index(force_refresh=False)
        if not symbol_index:
            return []

        if not q:
            profile = self._get_stock_search_profile()
            preferred_codes = list(dict.fromkeys(
                list(profile.get('favorites', []) or []) + list(profile.get('recent_codes', []) or [])
            ))
            preferred_set = set(preferred_codes)
            by_code = {str(item.get('code', '')).upper(): item for item in symbol_index}
            suggestions: List[Dict[str, Any]] = []
            for code in preferred_codes:
                item = by_code.get(str(code or '').upper())
                if item and self._stock_mode_matches(bool(item.get('is_etf'))):
                    suggestions.append(item)
            if len(suggestions) < limit:
                for item in symbol_index:
                    code = str(item.get('code', '')).upper()
                    if code in preferred_set:
                        continue
                    if not self._stock_mode_matches(bool(item.get('is_etf'))):
                        continue
                    suggestions.append(item)
                    if len(suggestions) >= limit:
                        break
            return suggestions[:limit]

        ranked: List[Tuple[int, Dict[str, Any]]] = []
        for item in symbol_index:
            if not self._stock_mode_matches(bool(item.get('is_etf'))):
                continue

            code = str(item.get('code') or '').upper()
            name = str(item.get('name') or '').upper()
            if not code:
                continue

            rank = None
            if code.startswith(q):
                rank = 0
            elif q in code:
                rank = 1
            elif name.startswith(q):
                rank = 2
            elif q in name:
                rank = 3

            if rank is not None:
                ranked.append((rank, item))

        ranked.sort(key=lambda t: (t[0], str(t[1].get('code', ''))))
        return [item for _, item in ranked[:max(1, int(limit))]]

    def _select_stock_search_suggestion(self, code: str) -> None:
        symbol = str(code or '').strip().upper()
        if not symbol:
            return
        if hasattr(self, 'stock_search_entry') and self.stock_search_entry is not None:
            try:
                self.stock_search_entry.delete(0, 'end')
                self.stock_search_entry.insert(0, symbol)
            except Exception:
                pass
        self._search_stock_symbol()

    def _render_stock_search_suggestions(self, query: Optional[str] = None) -> None:
        frame = getattr(self, 'stock_search_suggest_frame', None)
        if frame is None:
            return

        try:
            for child in frame.winfo_children():
                child.destroy()

            query_text = query
            if query_text is None and hasattr(self, 'stock_search_entry') and self.stock_search_entry is not None:
                try:
                    query_text = self.stock_search_entry.get()
                except Exception:
                    query_text = ''

            suggestions = self._get_stock_search_suggestions(str(query_text or ''), limit=8)

            title = ctk.CTkLabel(
                frame,
                text='자동완성',
                font=self._get_safe_font('small'),
                text_color='#9ca3af'
            )
            title.pack(side='left', padx=(10, 8), pady=7)

            if not suggestions:
                empty = ctk.CTkLabel(
                    frame,
                    text='추천 없음',
                    font=self._get_safe_font('small'),
                    text_color='#6b7280'
                )
                empty.pack(side='left', padx=(0, 8), pady=7)
                return

            for item in suggestions:
                code = str(item.get('code') or '').upper()
                name = str(item.get('name') or code)
                tag = 'ETF' if bool(item.get('is_etf')) else '주식'
                btn = ctk.CTkButton(
                    frame,
                    text=f'{code} {name[:8]} ({tag})',
                    width=156,
                    height=28,
                    font=self._get_safe_font('small'),
                    fg_color='#111827',
                    hover_color='#1f2937',
                    command=lambda c=code: self._select_stock_search_suggestion(c)
                )
                btn.pack(side='left', padx=3, pady=6)
        except Exception as exc:
            try:
                self.logger.warning(f'증권 검색 자동완성 렌더 실패: {exc}')
            except Exception:
                pass

    def _render_stock_search_quick_access(self) -> None:
        frame = getattr(self, 'stock_search_quick_frame', None)
        if frame is None:
            return

        try:
            for child in frame.winfo_children():
                child.destroy()

            profile = self._get_stock_search_profile()
            favorites = profile.get('favorites', [])
            recent_codes = profile.get('recent_codes', [])

            fav_label = ctk.CTkLabel(
                frame,
                text='⭐ 즐겨찾기',
                font=self._get_safe_font('small'),
                text_color='#fbbf24'
            )
            fav_label.pack(side='left', padx=(10, 6), pady=8)

            if favorites:
                for code in favorites[:6]:
                    btn = ctk.CTkButton(
                        frame,
                        text=code,
                        width=74,
                        height=28,
                        font=self._get_safe_font('small'),
                        command=lambda c=code: self._run_stock_quick_search(c)
                    )
                    btn.pack(side='left', padx=3, pady=6)
            else:
                empty = ctk.CTkLabel(
                    frame,
                    text='없음',
                    font=self._get_safe_font('small'),
                    text_color='#6b7280'
                )
                empty.pack(side='left', padx=(0, 10), pady=8)

            recent_label = ctk.CTkLabel(
                frame,
                text='최근검색',
                font=self._get_safe_font('small'),
                text_color='#9ca3af'
            )
            recent_label.pack(side='left', padx=(10, 6), pady=8)

            for code in recent_codes[:6]:
                btn = ctk.CTkButton(
                    frame,
                    text=code,
                    width=74,
                    height=28,
                    font=self._get_safe_font('small'),
                    fg_color='#1f2937',
                    hover_color='#374151',
                    command=lambda c=code: self._run_stock_quick_search(c)
                )
                btn.pack(side='left', padx=3, pady=6)
        except Exception as exc:
            try:
                self.logger.warning(f'증권 검색 빠른 접근 렌더 실패: {exc}')
            except Exception:
                pass

    def _ensure_stock_info_tab(self) -> None:
        """종목 정보 탭을 기본 탭으로 보장 (주식/ETF용)"""
        try:
            if not hasattr(self, 'tab_widget') or self.tab_widget is None:
                return

            tab_name = "종목 정보"
            tab = self._get_or_add_tab(tab_name)
            self._clear_tab_children(tab)

            # 검색·분석·보유·시장 미리보기 전체가 창 높이를 넘으면 탭 전체를 스크롤한다.
            main_container = ctk.CTkScrollableFrame(
                tab,
                fg_color="#0b1120",
                corner_radius=10,
            )
            main_container.pack(fill="both", expand=True, padx=10, pady=10)

            # 종목 정보 제목
            stock_info_title = ctk.CTkLabel(
                main_container,
                text=f"종목/ETF 검색 & 분석 ({self._get_stock_asset_mode_label()})",
                font=self._get_safe_font("title")
            )
            stock_info_title.pack(pady=10)

            # ===== 검색 섹션 =====
            search_frame = ctk.CTkFrame(main_container, fg_color="#1a1f2e", corner_radius=12, border_width=2, border_color="#374151")
            search_frame.pack(fill="x", padx=5, pady=10)

            search_label = ctk.CTkLabel(
                search_frame,
                text="종목코드 검색",
                font=self._get_safe_font("subtitle"),
                text_color="#f0f0f0"
            )
            search_label.pack(side="left", padx=15, pady=12)

            self.stock_search_entry = ctk.CTkEntry(
                search_frame,
                placeholder_text=self._get_stock_search_placeholder(),
                font=self._get_safe_font("body"),
                width=300
            )
            self.stock_search_entry.pack(side="left", padx=5, pady=10)
            self.stock_search_entry.bind("<Return>", lambda e: self._search_stock_symbol())
            self.stock_search_entry.bind("<KeyRelease>", lambda e: self._render_stock_search_suggestions())

            self.stock_asset_mode_var = ctk.StringVar(value=self._get_stock_asset_mode_label())
            stock_mode_menu = ctk.CTkOptionMenu(
                search_frame,
                values=["통합", "주식만", "ETF만"],
                variable=self.stock_asset_mode_var,
                command=self._on_stock_asset_mode_change,
                width=110
            )
            stock_mode_menu.pack(side="right", padx=(5, 15), pady=10)

            stock_mode_label = ctk.CTkLabel(
                search_frame,
                text="보기 모드",
                font=self._get_safe_font("small"),
                text_color="#9ca3af"
            )
            stock_mode_label.pack(side="right", padx=(5, 0), pady=10)

            search_btn = ctk.CTkButton(
                search_frame,
                text="검색",
                command=self._search_stock_symbol,
                font=self._get_safe_font("button"),
                width=100
            )
            search_btn.pack(side="left", padx=5, pady=10)

            self.stock_search_quick_frame = ctk.CTkFrame(
                main_container,
                fg_color="#111827",
                corner_radius=10,
                border_width=1,
                border_color="#374151"
            )
            self.stock_search_quick_frame.pack(fill="x", padx=5, pady=(0, 10))
            self._render_stock_search_quick_access()

            self.stock_search_suggest_frame = ctk.CTkFrame(
                main_container,
                fg_color="#0f172a",
                corner_radius=10,
                border_width=1,
                border_color="#334155"
            )
            self.stock_search_suggest_frame.pack(fill="x", padx=5, pady=(0, 10))
            self._render_stock_search_suggestions('')

            ai_note = ctk.CTkFrame(main_container, fg_color="#111827", corner_radius=12, border_width=1, border_color="#334155")
            ai_note.pack(fill="x", padx=5, pady=(0, 10))
            ctk.CTkLabel(
                ai_note,
                text="NoahAI 증권 사용 방식",
                font=self._get_safe_font("subtitle"),
                text_color="#e5e7eb"
            ).pack(anchor="w", padx=14, pady=(10, 4))
            ctk.CTkLabel(
                ai_note,
                text="증권 탭은 종목 검색·분석·설명 중심으로 동작합니다.\n"
                     "조절 요청과 판단 해석은 AI 어시스턴트를 사용하세요.",
                font=self._get_safe_font("small"),
                text_color="#9ca3af",
                justify="left"
            ).pack(anchor="w", padx=14, pady=(0, 10))

            # 검색 결과 표시 영역 (스크롤 가능)
            self.stock_search_results = ctk.CTkScrollableFrame(
                main_container,
                corner_radius=12,
                fg_color="#0b1120",
                border_color="#1f2937",
                border_width=2,
                label_text="분석 결과",
                height=230,
            )
            self.stock_search_results.pack(fill="x", padx=5, pady=10)

            self.stock_user_activity_scroll = ctk.CTkScrollableFrame(
                main_container,
                corner_radius=12,
                fg_color="#101827",
                border_color="#2563eb",
                border_width=2,
                label_text="내 보유·최근 체결 종목",
                height=210,
            )
            self.stock_user_activity_scroll.pack(fill="x", padx=5, pady=(0, 10))
            self._register_tab_widget(tab_name, "stock_user_activity_scroll", self.stock_user_activity_scroll)

            # AI 평가 결과를 위한 컬럼 구조
            evaluator_header_frame = ctk.CTkFrame(main_container)
            evaluator_header_frame.pack(fill="x", pady=(10, 5))

            # 주식/ETF용 컬럼 구조
            evaluator_headers = ["브로커", "종목", "구분", "현재가", "등락률", "거래량", "비고"]
            col_widths = [90, 150, 80, 100, 90, 110, 150]
            for i, header in enumerate(evaluator_headers):
                label = ctk.CTkLabel(
                    evaluator_header_frame,
                    text=header,
                    font=self._get_safe_font("table_header"),
                    width=col_widths[i] if i < len(col_widths) else 90
                )
                label.grid(row=0, column=i, padx=3, pady=3, sticky="ew")
                evaluator_header_frame.grid_columnconfigure(i, weight=1)

            # 종목 정보 테이블 데이터
            self.stock_evaluator_scroll = ctk.CTkScrollableFrame(
                main_container,
                corner_radius=12,
                fg_color="#0b1120",
                border_color="#1f2937",
                border_width=2,
                label_text=f"시장 종목 미리보기 · 검색용 ({self._get_stock_asset_mode_label()})",
                height=220,
            )
            self.stock_evaluator_scroll.pack(fill="x", pady=5)
            self._register_tab_widget(tab_name, "stock_evaluator_scroll", self.stock_evaluator_scroll)

            # 새로고침 버튼
            refresh_button = ctk.CTkButton(
                main_container,
                text="종목 정보 새로고침",
                command=self._refresh_stock_info,
                font=self._get_safe_font("button")
            )
            refresh_button.pack(pady=10)

            # 초기 데이터
            self._update_stock_info()
            print("종목 정보 탭 기본 생성 완료")
        except Exception as e:
            try:
                self.logger.error(f"_ensure_stock_info_tab 오류: {e}")
            except Exception:
                print(f"_ensure_stock_info_tab 오류: {e}")

    def _search_stock_symbol(self):
        """종목 검색 및 분석"""
        try:
            if not hasattr(self, 'stock_search_entry'):
                return

            search_code = self.stock_search_entry.get().strip().upper()
            if not search_code:
                return

            self._record_recent_stock_search(search_code)

            # 검색 결과 영역 초기화
            if hasattr(self, 'stock_search_results'):
                for widget in self.stock_search_results.winfo_children():
                    widget.destroy()

            # 로딩 표시
            loading_label = ctk.CTkLabel(
                self.stock_search_results,
                text="검색 중...",
                font=self._get_safe_font("body"),
                text_color="#cbd5e1"
            )
            loading_label.pack(pady=20)
            self.stock_search_results.update()

            # StockAnalysisService를 이용한 분석
            try:
                from trading.stock_analysis_service import StockAnalysisService
                enabled_brokers = self.settings.get('enabled_stock_brokers', [])
                selected_mode = self._get_stock_asset_mode()

                analysis_results = []
                for broker in enabled_brokers:
                    adapter = self._get_stock_adapter(broker)
                    if not adapter:
                        continue

                    try:
                        svc = StockAnalysisService(adapter, broker_name=broker, recorder=getattr(self, 'recorder', None))
                        result = svc.analyze_symbol(search_code)
                        if result and result.get('status') == 'ok' and self._stock_mode_matches(bool(result.get('is_etf'))):
                            analysis_results.append({
                                'broker': broker,
                                'data': result,
                                'adapter': adapter
                            })
                    except Exception as e:
                        print(f"{broker} 종목 분석 오류: {e}")

                # 검색 결과 표시
                for widget in self.stock_search_results.winfo_children():
                    widget.destroy()

                if not analysis_results:
                    mode_text = {
                        'all': '현재 통합 보기에서',
                        'stock': '현재 주식만 보기에서',
                        'etf': '현재 ETF만 보기에서',
                    }.get(selected_mode, '현재 보기에서')
                    error_label = ctk.CTkLabel(
                        self.stock_search_results,
                        text=f"{mode_text} 종목코드 '{search_code}'를 찾을 수 없습니다.",
                        font=self._get_safe_font("body"),
                        text_color="#ef4444"
                    )
                    error_label.pack(pady=20)
                    return

                for result in analysis_results:
                    self._display_stock_analysis_card(result['broker'], result['data'], result['adapter'])

            except ImportError:
                error_label = ctk.CTkLabel(
                    self.stock_search_results,
                    text="StockAnalysisService를 사용할 수 없습니다.",
                    font=self._get_safe_font("body"),
                    text_color="#fbbf24"
                )
                error_label.pack(pady=20)

        except Exception as e:
            print(f"종목 검색 오류: {e}")
            if hasattr(self, 'stock_search_results'):
                for widget in self.stock_search_results.winfo_children():
                    widget.destroy()
                error_label = ctk.CTkLabel(
                    self.stock_search_results,
                    text=f"검색 오류: {str(e)[:100]}",
                    font=self._get_safe_font("body"),
                    text_color="#ef4444"
                )
                error_label.pack(pady=20)

    def _display_stock_analysis_card(self, broker: str, analysis_data: dict, adapter):
        """종목 분석 결과를 카드 형태로 표시"""
        try:
            if not hasattr(self, 'stock_search_results'):
                return

            # 카드 프레임
            card = ctk.CTkFrame(
                self.stock_search_results,
                fg_color="#1a1f2e",
                corner_radius=12,
                border_width=2,
                border_color="#374151"
            )
            card.pack(fill="x", padx=5, pady=10)

            # 상단: 종목명 및 기본 정보
            header = ctk.CTkFrame(card, fg_color="transparent")
            header.pack(fill="x", padx=15, pady=12)

            code = analysis_data.get('code', 'N/A')
            if code == 'N/A':
                code = analysis_data.get('symbol', 'N/A')
            name = analysis_data.get('name', code)
            is_etf = analysis_data.get('is_etf', False)
            asset_type = "ETF" if is_etf else "주식"

            title_text = f"{name} ({code}) - {asset_type}"
            title_label = ctk.CTkLabel(
                header,
                text=title_text,
                font=self._get_safe_font("subtitle"),
                text_color="#fbbf24"
            )
            title_label.pack(side="left", anchor="w", pady=(0, 8))

            profile = self._get_stock_search_profile()
            is_favorite = str(code).upper() in profile.get('favorites', [])
            favorite_btn = ctk.CTkButton(
                header,
                text="⭐ 즐겨찾기" if not is_favorite else "즐겨찾기",
                width=110,
                height=30,
                font=self._get_safe_font("small"),
                fg_color="#374151" if not is_favorite else "#a16207",
                hover_color="#4b5563" if not is_favorite else "#92400e",
                command=lambda c=code: self._toggle_stock_favorite(c)
            )
            favorite_btn.pack(side="right", padx=(8, 0), pady=(0, 8))

            # 자동매매 감시 목록 추가 버튼
            auto_trade_btn = ctk.CTkButton(
                header,
                text="자동매매 추가",
                width=130,
                height=30,
                font=self._get_safe_font("small"),
                fg_color="#065f46",
                hover_color="#047857",
                command=lambda c=code: self._add_stock_to_auto_trade(c)
            )
            auto_trade_btn.pack(side="right", padx=(0, 6), pady=(0, 8))

            # 중단: 시장 정보
            market_frame = ctk.CTkFrame(card, fg_color="transparent")
            market_frame.pack(fill="x", padx=15, pady=5)

            price = analysis_data.get('current_price', 'N/A')
            change_rate = analysis_data.get('change_rate', 'N/A')
            volume = analysis_data.get('volume', 'N/A')

            try:
                if isinstance(price, (int, float)):
                    price_text = f"현재가: {float(price):,.0f}원"
                else:
                    price_text = f"현재가: {price}"
            except:
                price_text = f"현재가: {price}"

            try:
                if isinstance(change_rate, (int, float)):
                    color = "#22c55e" if float(change_rate) >= 0 else "#ef4444"
                    change_text = f"등락률: {float(change_rate):+.2f}%"
                else:
                    change_text = f"등락률: {change_rate}"
                    color = "#9ca3af"
            except:
                change_text = f"등락률: {change_rate}"
                color = "#9ca3af"

            price_label = ctk.CTkLabel(market_frame, text=price_text, font=self._get_safe_font("body"), text_color="#e5e7eb")
            price_label.pack(anchor="w", padx=0)

            change_label = ctk.CTkLabel(market_frame, text=change_text, font=self._get_safe_font("body"), text_color=color)
            change_label.pack(anchor="w", padx=0)

            # 하단: AI 분석 결과
            analysis_frame = ctk.CTkFrame(card, fg_color="transparent")
            analysis_frame.pack(fill="x", padx=15, pady=10)

            score = analysis_data.get('score', 'N/A')
            reasoning = analysis_data.get('reasoning', '분석 데이터 없음')

            try:
                score_num = float(score)
                if score_num >= 7.0:
                    score_icon = ""
                    score_color = "#22c55e"
                elif score_num >= 5.0:
                    score_icon = ""
                    score_color = "#fbbf24"
                else:
                    score_icon = ""
                    score_color = "#ef4444"
            except:
                score_icon = ""
                score_color = "#9ca3af"

            score_text = f"{score_icon} AI 판단 점수: {score}"
            score_label = ctk.CTkLabel(
                analysis_frame,
                text=score_text,
                font=self._get_safe_font("body"),
                text_color=score_color
            )
            score_label.pack(anchor="w", pady=(0, 8))

            reasoning_label = ctk.CTkLabel(
                analysis_frame,
                text=f"판단 근거:\n{str(reasoning)[:200]}...",
                font=self._get_safe_font("small"),
                text_color="#cbd5e1",
                wraplength=400,
                justify="left"
            )
            reasoning_label.pack(anchor="w", pady=(0, 5))

            # 하단: 추가 정보
            footer_frame = ctk.CTkFrame(card, fg_color="transparent")
            footer_frame.pack(fill="x", padx=15, pady=(0, 10))

            footer_text = f"브로커: {broker.upper()}"
            if is_etf and 'etf_score_detail' in analysis_data:
                etf_detail = analysis_data['etf_score_detail']
                nav_gap = etf_detail.get('nav_gap')
                if nav_gap is not None:
                    footer_text += f" | NAV괴리: {nav_gap}%"

            footer_label = ctk.CTkLabel(
                footer_frame,
                text=footer_text,
                font=self._get_safe_font("small"),
                text_color="#9ca3af"
            )
            footer_label.pack(anchor="w")

        except Exception as e:
            print(f"분석 카드 표시 오류: {e}")


    def _ensure_stock_trading_stats_tab(self) -> None:
        """주식 거래 통계 탭을 기본 탭으로 보장"""
        try:
            if not hasattr(self, 'tab_widget') or self.tab_widget is None:
                return

            tab_name = "거래 통계"
            tab = self._get_or_add_tab(tab_name)
            self._clear_tab_children(tab)

            # 메인 컨테이너
            main_container = ctk.CTkFrame(
                tab,
                fg_color=self._color("content_bg", "#0b1120"),
                corner_radius=10,
            )
            main_container.pack(fill="both", expand=True, padx=10, pady=10)

            # 거래 통계 제목
            stats_title = ctk.CTkLabel(
                main_container,
                text="주식/ETF 거래 통계 (데이터베이스 기준)",
                font=self._get_safe_font("title"),
                text_color=self._color("text_primary", "#f9fafb"),
            )
            stats_title.pack(pady=10)

            # 증권사 필터
            filter_frame = ctk.CTkFrame(main_container, fg_color="transparent")
            filter_frame.pack(fill="x", pady=(0, 8))

            filter_label = ctk.CTkLabel(
                filter_frame,
                text="증권사 필터",
                font=self._get_safe_font("body"),
                text_color=self._color('text_secondary', '#9ca3af')
            )
            filter_label.pack(side="left", padx=(0, 8))

            broker_options = self._get_stock_trading_stats_broker_options()
            previous_value = None
            if hasattr(self, 'stock_trading_stats_broker_var'):
                try:
                    previous_value = self.stock_trading_stats_broker_var.get()
                except Exception:
                    previous_value = None
            default_broker = previous_value if previous_value in broker_options else broker_options[0] if broker_options else "전체"
            self.stock_trading_stats_broker_var = tk.StringVar(value=default_broker)

            broker_menu = ctk.CTkOptionMenu(
                filter_frame,
                values=broker_options,
                variable=self.stock_trading_stats_broker_var,
                command=lambda _: self._update_stock_trading_statistics(),
                width=160,
                fg_color=self._color("secondary", "#263a57"),
                button_color=self._color("primary", "#2563eb"),
                button_hover_color=self._color("primary_hover", "#1d4ed8"),
            )
            broker_menu.pack(side="left")
            self.stock_trading_stats_broker_menu = broker_menu

            # 거래 통계 테이블 헤더
            stats_header_frame = ctk.CTkFrame(
                main_container,
                fg_color=self._color("surface", "#111827"),
                border_color=self._color("border", "#273449"),
                border_width=1,
                corner_radius=10,
            )
            stats_header_frame.pack(fill="x", pady=(0, 5))

            # 주식/ETF용 통계 컬럼 구조
            stats_headers = ["브로커", "총 거래", "매수", "매도", "오늘 거래", "미체결", "실현손익", "상태"]
            self._stock_stats_header_labels = []
            for i, header in enumerate(stats_headers):
                label = ctk.CTkLabel(
                    stats_header_frame,
                    text=header,
                    font=self._get_safe_font("table_header"),
                    text_color=self._color("text_primary", "#f9fafb"),
                )
                label.grid(row=0, column=i, padx=5, pady=5, sticky="ew")
                stats_header_frame.grid_columnconfigure(i, weight=1)
                self._stock_stats_header_labels.append(label)

            # 거래 통계 테이블 데이터
            self.stock_trading_stats_scroll = ctk.CTkScrollableFrame(
                main_container,
                corner_radius=12,
                fg_color=self._color("content_bg", "#0b1120"),
                border_color=self._color("border", "#273449"),
                border_width=2
            )
            self.stock_trading_stats_scroll.pack(fill="both", expand=True, pady=5)
            self._register_tab_widget(tab_name, "stock_trading_stats_scroll", self.stock_trading_stats_scroll)

            # 버튼 행
            button_row = ctk.CTkFrame(main_container, fg_color="transparent")
            button_row.pack(pady=10)

            refresh_button = ctk.CTkButton(
                button_row,
                text="거래 통계 새로고침",
                command=self._refresh_stock_trading_stats,
                font=self._get_safe_font("button"),
                fg_color=self._color("primary", "#2563eb"),
                hover_color=self._color("primary_hover", "#1d4ed8"),
            )
            refresh_button.pack(side="left", padx=(0, 6))

            # 상태 라벨
            self.stock_trading_stats_status_label = ctk.CTkLabel(
                main_container,
                text="",
                font=self._get_safe_font("small"),
                text_color=self._color('text_secondary', '#9ca3af')
            )
            self.stock_trading_stats_status_label.pack(pady=(0, 8))

            # 초기 데이터
            self._update_stock_trading_statistics()
            print("주식 거래 통계 탭 기본 생성 완료")
        except Exception as e:
            try:
                self.logger.error(f"_ensure_stock_trading_stats_tab 오류: {e}")
            except Exception:
                print(f"_ensure_stock_trading_stats_tab 오류: {e}")

    def _ensure_stock_trend_tab(self) -> None:
        """주식 시장 트렌드 탭을 기본 탭으로 보장"""
        try:
            if not hasattr(self, 'tab_widget') or self.tab_widget is None:
                return

            tab_name = "시장 트렌드"
            tab = self._get_or_add_tab(tab_name)
            self._clear_tab_children(tab)

            # 블록체인과 동일한 트렌드 위젯을 재사용하되, 서비스 컨텍스트를 stock으로 설정
            from ui.widgets.market_trend_widget import MarketTrendWidget
            trend_widget = MarketTrendWidget(tab, dashboard_ref=self, colors=dict(_FIXED_COLORS))
            try:
                if hasattr(trend_widget, 'set_service_context'):
                    trend_widget.set_service_context('stock')
            except Exception:
                pass
            trend_widget.pack(fill="both", expand=True, padx=10, pady=10)
            self._register_tab_widget(tab_name, "market_trend_widget", trend_widget)

            print("주식 시장 트렌드 탭 기본 생성 완료")
        except Exception as e:
            try:
                self.logger.error(f"_ensure_stock_trend_tab 오류: {e}")
            except Exception:
                print(f"_ensure_stock_trend_tab 오류: {e}")

    def _refresh_stock_info(self):
        """종목 정보 새로고침"""
        try:
            self._update_stock_info()
        except Exception as e:
            print(f"종목 정보 새로고침 오류: {e}")

    def _set_stock_order_status(self, message: str, level: str = 'info') -> None:
        if not hasattr(self, 'stock_order_status_label'):
            return
        try:
            color_map = {
                'info': self._color('text_secondary', '#9ca3af'),
                'success': self._color('success', '#22c55e'),
                'warning': self._color('warning', '#f59e0b'),
                'error': self._color('danger', '#ef4444'),
            }
            self.stock_order_status_label.configure(
                text=message,
                text_color=color_map.get(level, self._color('text_secondary', '#9ca3af')),
            )
        except Exception:
            try:
                self.stock_order_status_label.configure(text=message)
            except Exception:
                pass

    def _get_stock_order_guardrails(self) -> Dict[str, Any]:
        try:
            from trading.stock_order_guardrails import normalize_stock_order_guardrails
            return normalize_stock_order_guardrails((self.settings or {}).get('stock_order_guardrails', {}))
        except Exception:
            return {
                'enabled': True,
                'enforce_market_hours': True,
                'max_order_value': 50_000_000.0,
                'max_quantity': 10_000,
                'daily_order_limit': 20,
                'allow_market_order': True,
                'allow_limit_order': True,
            }

    def _get_stock_auto_trading_settings(self) -> Dict[str, Any]:
        raw = (self.settings or {}).get('stock_auto_trading', {}) or {}
        if not isinstance(raw, dict):
            raw = {}

        # 하위 호환: legacy key(enabled)를 auto_start로 해석
        auto_start = bool(raw.get('auto_start', raw.get('enabled', False)))

        interval_sec = 60
        try:
            interval_sec = max(5, int(raw.get('interval_sec', 60) or 60))
        except Exception:
            interval_sec = 60

        quantity = 1.0
        try:
            quantity = float(raw.get('quantity', 1.0) or 1.0)
            if quantity <= 0:
                quantity = 1.0
        except Exception:
            quantity = 1.0

        max_orders_per_cycle = 1
        try:
            max_orders_per_cycle = max(1, int(raw.get('max_orders_per_cycle', 1) or 1))
        except Exception:
            max_orders_per_cycle = 1

        # v3.9.0.3 이하 Coin/Stock Info가 watchlist에만 기록하던 값을
        # 실행 정본인 symbols로 읽어 자동 이전한다.
        symbols_raw = list(raw.get('symbols', []) or []) + list(raw.get('watchlist', []) or [])
        symbols: List[str] = []
        if isinstance(symbols_raw, list):
            symbols = [str(s or '').strip().upper() for s in symbols_raw if str(s or '').strip()]

        return {
            'auto_start': auto_start,
            'enabled': bool(raw.get('enabled', auto_start)),
            'interval_sec': interval_sec,
            'buy_threshold': float(raw.get('buy_threshold', 70.0) or 70.0),
            'sell_threshold': float(raw.get('sell_threshold', 30.0) or 30.0),
            'order_type': str(raw.get('order_type', 'MARKET') or 'MARKET').strip().upper(),
            'quantity': quantity,
            'max_orders_per_cycle': max_orders_per_cycle,
            'symbols': list(dict.fromkeys(symbols)),
            'risk_guard_enabled': bool(raw.get('risk_guard_enabled', True)),
            'max_consecutive_losses': max(1, int(raw.get('max_consecutive_losses', 3) or 3)),
            'daily_max_loss': float(raw.get('daily_max_loss', 500000.0) or 500000.0),
            'cooldown_sec_per_symbol': max(0, int(raw.get('cooldown_sec_per_symbol', 300) or 300)),
            'risk_governance_enabled': bool(raw.get('risk_governance_enabled', True)),
            'global_kill_switch': bool(raw.get('global_kill_switch', False)),
            'weekly_max_loss': float(raw.get('weekly_max_loss', 1500000.0) or 1500000.0),
            'monthly_max_loss': float(raw.get('monthly_max_loss', 4000000.0) or 4000000.0),
            'max_symbol_weight_percent': float(raw.get('max_symbol_weight_percent', 35.0) or 35.0),
            'enable_exit_policy': bool(raw.get('enable_exit_policy', True)),
            'take_profit_percent': float(raw.get('take_profit_percent', 5.0) or 5.0),
            'stop_loss_percent': float(raw.get('stop_loss_percent', 8.0) or 8.0),
            'etf_take_profit_percent': float(raw.get('etf_take_profit_percent', 4.0) or 4.0),
            'etf_stop_loss_percent': float(raw.get('etf_stop_loss_percent', 6.0) or 6.0),
            'use_signal_exit': bool(raw.get('use_signal_exit', True)),
            'etf_alert_exit': bool(raw.get('etf_alert_exit', True)),
        }

    def _get_stock_broker_config(self, broker: str) -> Dict[str, Any]:
        settings_obj = self.settings if isinstance(self.settings, dict) else {}
        broker_configs = settings_obj.get('stock_broker_configs', {})
        if not isinstance(broker_configs, dict):
            return {}

        broker_normalized = str(broker or '').strip().lower()
        broker_key_candidates = [
            broker,
            broker_normalized,
            broker_normalized.replace('_', ''),
        ]
        if broker_normalized in ('miraeasset', 'mirae_asset'):
            broker_key_candidates.extend(['miraeAsset', 'mirae_asset', 'miraeasset'])
        if broker_normalized in ('koreainvestment', 'korea_investment', 'kis'):
            broker_key_candidates.extend(['koreaInvestment', 'korea_investment', 'koreainvestment', 'kis'])

        for key in broker_key_candidates:
            if key in broker_configs and isinstance(broker_configs.get(key), dict):
                return broker_configs.get(key, {}) or {}
        return {}

    def _is_stock_live_order_allowed(self, broker: str, adapter: Any) -> Tuple[bool, str]:
        settings_obj = self.settings if isinstance(self.settings, dict) else {}
        broker_config = self._get_stock_broker_config(broker)

        configured_api_type = str(
            broker_config.get('api_type')
            or getattr(adapter, 'api_type', '')
            or 'openapi'
        ).strip().lower()
        is_live_route = configured_api_type not in ('mock',)
        if not is_live_route:
            return True, ''

        configured_api_version = str(
            broker_config.get('api_version')
            or getattr(adapter, 'api_version', '')
            or ''
        ).strip().lower()
        global_live_flag = bool(settings_obj.get('enable_stock_live_order', False))
        broker_live_flag = bool(broker_config.get('allow_live_order', False))
        try:
            from trading.exchanges.exchange_factory import ExchangeFactory

            adapter_ready = None
            adapter_ready_reason = ''
            readiness = getattr(adapter, 'get_live_readiness', None)
            if callable(readiness):
                adapter_ready, adapter_ready_reason = readiness()

            return ExchangeFactory.evaluate_stock_live_order_permission(
                broker=broker,
                api_type=configured_api_type,
                api_version=configured_api_version,
                global_live_flag=global_live_flag,
                broker_live_flag=broker_live_flag,
                adapter_ready=adapter_ready,
                adapter_ready_reason=adapter_ready_reason,
            )
        except Exception as exc:
            return False, f'실주문 차단: 증권 API 성숙도 확인 실패 ({exc})'

    def _resolve_stock_auto_symbols(
        self,
        adapter: Any,
        configured_symbols: List[str],
        asset_mode: str = 'all',
    ) -> List[str]:
        from trading.stock_analysis_service import select_stock_universe

        return select_stock_universe(
            adapter,
            configured_symbols=configured_symbols,
            asset_mode=asset_mode,
            limit=8,
            custom_strategy_pool=list(
                getattr(getattr(self, "main_app", None), "active_custom_strategy_pool", [])
                or []
            ),
        )

    def _start_stock_auto_trade_loop(self, force: bool = False) -> None:
        cfg = self._get_stock_auto_trading_settings()
        # 시작 조건은 start/stop(AUTO) 상태이며,
        # auto_start는 주식 탭 진입 시 자동 예약 시작 여부만 담당한다.
        if str(getattr(self, 'current_service', '')).lower() != 'stock':
            return
        if (not force) and (not cfg.get('auto_start', False)):
            self._stock_auto_loop_running = False
            return
        if self._stock_auto_loop_running:
            return
        self._stock_auto_loop_running = True
        self.thread_safe_after(200, self._run_stock_auto_trade_cycle_once)

    def _stop_stock_auto_trade_loop(self) -> None:
        self._stock_auto_loop_running = False

        # STOP 포지션 처리 정책 적용
        # keep_with_tp_sl (기본/권장): 신규 진입만 차단, 기존 포지션은 TP/SL에 맡김
        # close_all: 신규 진입 차단 + 보유 포지션 즉시 시장가 청산
        try:
            from config.settings import load_settings
            settings = load_settings() or {}
            policy = str(
                settings.get(
                    'asset_stop_position_policy',
                    settings.get('stock_stop_position_policy', 'keep_with_tp_sl')
                )
            )
            if policy == 'close_all':
                self._force_close_all_stock_positions()
        except Exception as e:
            print(f"STOP 정책 확인 오류: {e}")

    def _force_close_all_stock_positions(self) -> None:
        """STOP close_all 정책: 보유 주식/ETF 포지션 즉시 시장가 청산"""
        import threading

        def _do_close():
            try:
                from trading.stock_analysis_service import StockAnalysisService
                cfg = self._get_stock_auto_trading_settings()
                broker_configs = {}
                if hasattr(self, 'settings') and isinstance(self.settings, dict):
                    broker_configs = self.settings.get('stock_broker_configs', {})
                elif hasattr(self, '_app') and hasattr(self._app, 'settings'):
                    broker_configs = self._app.settings.get('stock_broker_configs', {})

                for broker_name, broker_cfg in broker_configs.items():
                    if not broker_cfg.get('enabled', False):
                        continue
                    try:
                        svc = StockAnalysisService(broker_name=broker_name, broker_config=broker_cfg)
                        if not hasattr(svc, 'adapter') or svc.adapter is None:
                            continue
                        positions = []
                        if hasattr(svc.adapter, 'get_positions'):
                            positions = svc.adapter.get_positions() or []
                        for pos in positions:
                            symbol = str(pos.get('code') or pos.get('symbol') or '').strip().upper()
                            qty = float(pos.get('quantity') or 0)
                            if not symbol or qty <= 0:
                                continue
                            try:
                                svc.adapter.place_order(
                                    symbol=symbol,
                                    side='SELL',
                                    quantity=qty,
                                    order_type='MARKET',
                                )
                                print(f"STOP close_all: {broker_name} {symbol} {qty}주 청산 완료")
                            except Exception as oe:
                                print(f"STOP close_all: {broker_name} {symbol} 청산 실패: {oe}")
                    except Exception as be:
                        print(f"STOP close_all: {broker_name} 처리 실패: {be}")
            except Exception as e:
                print(f"STOP close_all: 전체 청산 실패: {e}")

        t = threading.Thread(target=_do_close, daemon=True, name='stock_close_all')
        t.start()

    def _run_stock_auto_trade_cycle_once(self) -> None:
        if not getattr(self, '_stock_auto_loop_running', False):
            return

        cfg = self._get_stock_auto_trading_settings()
        interval_ms = int(max(5, int(cfg.get('interval_sec', 60))) * 1000)

        if str(getattr(self, 'current_service', '')).lower() != 'stock':
            self._stock_auto_loop_running = False
            return

        try:
            if not bool(getattr(self, 'is_auto_trading', False)):
                self._set_stock_order_status('증권 자동매매 대기: AUTO 상태 아님', level='info')
            else:
                from trading.stock_analysis_service import StockAnalysisService

                enabled_brokers = list((self.settings or {}).get('enabled_stock_brokers', []) or [])
                executed_total = 0
                blocked_live_brokers: List[str] = []
                block_reason_counts: Dict[str, int] = {}
                exit_orders_total = 0

                for broker in enabled_brokers:
                    adapter = self._get_stock_adapter(broker)
                    if not adapter:
                        continue

                    try:
                        if hasattr(adapter, 'is_connected') and not getattr(adapter, 'is_connected', False):
                            if hasattr(adapter, 'connect'):
                                adapter.connect()
                    except Exception:
                        pass

                    allow_live_order, blocked_reason = self._is_stock_live_order_allowed(broker, adapter)
                    from trading.execution_mode import (
                        ExecutionMode,
                        resolve_stock_execution_mode,
                    )
                    from trading.advanced_layer_config import deep_merge_policy

                    stock_execution_mode = resolve_stock_execution_mode(
                        self.settings if isinstance(self.settings, dict) else {},
                        allow_live_order=allow_live_order,
                        adapter_api_type=str(getattr(adapter, 'api_type', '') or ''),
                    )
                    if stock_execution_mode == ExecutionMode.LEARNING and not allow_live_order:
                        blocked_live_brokers.append(str(broker).upper())

                    stock_asset_mode = self._get_stock_asset_mode()
                    symbols = self._resolve_stock_auto_symbols(
                        adapter,
                        cfg.get('symbols', []),
                        asset_mode=stock_asset_mode,
                    )
                    if not symbols:
                        continue

                    advanced_root = dict(
                        (self.settings or {}).get('advanced_trading_layers', {}) or {}
                    )
                    broker_override = dict(
                        (advanced_root.get('exchange_overrides', {}) or {}).get(
                            str(broker).lower(), {}
                        ) or {}
                    )
                    advanced_policy = deep_merge_policy(advanced_root, broker_override)
                    advanced_policy.pop('exchange_overrides', None)
                    auto_risk_policy = deep_merge_policy(cfg, advanced_policy)
                    multi_venue_policy = dict(
                        (self.settings or {}).get('multi_venue_execution', {}) or {}
                    )
                    multi_venue_policy['_authorized_targets'] = list(enabled_brokers)
                    auto_risk_policy['multi_venue_execution'] = multi_venue_policy

                    svc = StockAnalysisService(adapter, broker_name=broker, recorder=getattr(self, 'recorder', None))
                    cycle_result = svc.run_auto_trade_cycle(
                        symbols=symbols,
                        quantity=float(cfg.get('quantity', 1.0) or 1.0),
                        order_type=str(cfg.get('order_type', 'MARKET') or 'MARKET'),
                        buy_threshold=float(cfg.get('buy_threshold', 70.0) or 70.0),
                        sell_threshold=float(cfg.get('sell_threshold', 30.0) or 30.0),
                        asset_mode=stock_asset_mode,
                        max_orders=int(cfg.get('max_orders_per_cycle', 1) or 1),
                        allow_live_order=allow_live_order,
                        guardrails=self._get_stock_order_guardrails(),
                        auto_risk_policy=auto_risk_policy,
                        exit_policy=cfg,
                        custom_strategy_pool=list(
                            getattr(getattr(self, 'main_app', None), 'active_custom_strategy_pool', []) or []
                        ),
                        execution_mode_override=stock_execution_mode.value,
                    )
                    executed_total += int(cycle_result.get('orders_executed', 0) or 0)
                    exit_orders_total += int(cycle_result.get('exit_orders_executed', 0) or 0)
                    for decision in (cycle_result.get('decisions') or []):
                        reason_key = str(decision.get('reason') or '').strip()
                        if not reason_key:
                            continue
                        block_reason_counts[reason_key] = block_reason_counts.get(reason_key, 0) + 1

                if executed_total > 0:
                    status_parts = [f'자동매매 실행 완료: {executed_total}건 주문']
                    if exit_orders_total > 0:
                        status_parts.append(f'청산 {exit_orders_total}건')
                    self._set_stock_order_status(' / '.join(status_parts), level='success')
                    self._update_stock_info()
                    self._update_stock_trading_statistics()
                elif blocked_live_brokers:
                    brokers_text = ', '.join(blocked_live_brokers)
                    self._set_stock_order_status(
                        f'자동매매 신호는 생성됐지만 실주문은 차단됨 ({brokers_text})',
                        level='warning'
                    )
                elif block_reason_counts:
                    ordered = sorted(block_reason_counts.items(), key=lambda item: (-item[1], item[0]))
                    top_reasons = ', '.join(f'{name}:{count}' for name, count in ordered[:3])
                    self._set_stock_order_status(
                        f'자동매매 사이클 완료: 실행된 주문 없음 ({top_reasons})',
                        level='info'
                    )
                else:
                    self._set_stock_order_status('자동매매 사이클 완료: 실행된 주문 없음', level='info')
        except Exception as exc:
            self._set_stock_order_status(f'자동매매 사이클 오류: {exc}', level='error')
        finally:
            if getattr(self, '_stock_auto_loop_running', False):
                self.thread_safe_after(interval_ms, self._run_stock_auto_trade_cycle_once)


    def _refresh_stock_trading_stats(self):
        """주식 거래 통계 새로고침"""
        try:
            self._update_stock_trading_statistics()
        except Exception as e:
            print(f"주식 거래 통계 새로고침 오류: {e}")

    def _update_stock_info(self):
        """종목 정보 업데이트"""
        try:
            if not hasattr(self, 'stock_evaluator_scroll'):
                return

            # 기존 위젯 제거
            for widget in self.stock_evaluator_scroll.winfo_children():
                widget.destroy()
            if hasattr(self, 'stock_user_activity_scroll'):
                for widget in self.stock_user_activity_scroll.winfo_children():
                    widget.destroy()

            try:
                from trading.stock_analysis_service import StockAnalysisService
                _analysis_svc_available = True
            except ImportError:
                _analysis_svc_available = False

            enabled_brokers = self.settings.get('enabled_stock_brokers', [])
            selected_mode = self._get_stock_asset_mode()
            rows_rendered = 0
            user_rows: List[dict] = []
            for broker in enabled_brokers:
                adapter = self._get_stock_adapter(broker)
                if not adapter:
                    continue

                try:
                    if hasattr(adapter, 'is_connected') and not getattr(adapter, 'is_connected', False):
                        if hasattr(adapter, 'connect'):
                            adapter.connect()
                except Exception:
                    pass

                user_rows.extend(self._collect_stock_user_activity(broker, adapter))

                # 분석 서비스 경유로 ETF 리스크 평가 수집
                etf_risk: dict = {}
                symbol_analysis: dict = {}
                if _analysis_svc_available:
                    try:
                        svc = StockAnalysisService(adapter, broker_name=broker, recorder=getattr(self, 'recorder', None))
                        for m in svc.get_etf_analysis():
                            etf_risk[m.code] = m.risk_level()

                        # 상단 목록에 표시할 종목은 개수가 적으므로 즉시 분석 캐시 생성
                        preview_codes: List[str] = []
                        try:
                            if hasattr(adapter, 'get_stock_list'):
                                preview_codes.extend([
                                    str((x or {}).get('code', '')).strip()
                                    for x in ((adapter.get_stock_list('KOSPI') or [])[:5])
                                    if str((x or {}).get('code', '')).strip()
                                ])
                        except Exception:
                            pass
                        try:
                            if hasattr(adapter, 'get_etf_list'):
                                preview_codes.extend([
                                    str((x or {}).get('code', '')).strip()
                                    for x in ((adapter.get_etf_list() or [])[:5])
                                    if str((x or {}).get('code', '')).strip()
                                ])
                        except Exception:
                            pass

                        for code in list(dict.fromkeys(preview_codes))[:8]:
                            try:
                                result = svc.analyze_symbol(code)
                                if result.get('status') == 'ok':
                                    symbol_analysis[code] = result
                            except Exception:
                                pass
                    except Exception:
                        pass

                items = []
                try:
                    if hasattr(adapter, 'get_stock_list'):
                        items.extend((adapter.get_stock_list('KOSPI') or [])[:5])
                except Exception:
                    pass
                try:
                    if hasattr(adapter, 'get_etf_list'):
                        items.extend((adapter.get_etf_list() or [])[:5])
                except Exception:
                    pass

                for item in items[:8]:
                    code = str((item or {}).get('code', ''))
                    is_etf = bool((item or {}).get('is_etf', False)) or (hasattr(adapter, 'is_etf') and code and adapter.is_etf(code))
                    if not self._stock_mode_matches(is_etf):
                        continue

                    row = ctk.CTkFrame(self.stock_evaluator_scroll, fg_color='transparent')
                    row.pack(fill='x', padx=4, pady=2)

                    name = str((item or {}).get('name', code))

                    note = ''
                    analysis = symbol_analysis.get(code, {})
                    if is_etf:
                        tracking_error = (item or {}).get('tracking_error')
                        risk = etf_risk.get(code, 'ok')
                        etf_detail = analysis.get('etf_score_detail') or {}
                        score_text = ''
                        if analysis:
                            try:
                                score_text = f"점수 {float(analysis.get('score', 0)):.1f}"
                            except Exception:
                                score_text = ''

                        if tracking_error not in (None, ''):
                            try:
                                note = f"추적오차 {float(tracking_error) * 100:.2f}%"
                            except Exception:
                                note = f"추적오차 {tracking_error}"
                        elif (item or {}).get('base_index'):
                            note = str((item or {}).get('base_index'))
                        if risk == 'alert':
                            note = f"{note}" if note else "리스크 높음"
                        elif risk == 'warn':
                            note = f"{note}" if note else "주의"

                        if score_text:
                            nav_gap = etf_detail.get('nav_gap')
                            nav_text = f", NAV괴리 {nav_gap}%" if nav_gap is not None else ''
                            note = f"{score_text}{nav_text} | {note}" if note else f"{score_text}{nav_text}"
                    else:
                        if analysis:
                            try:
                                note = f"점수 {float(analysis.get('score', 0)):.1f}, 모멘텀 {float(analysis.get('momentum', 0)):+.2f}%"
                            except Exception:
                                note = ''

                    values = [
                        broker.upper(),
                        f"{name} ({code})",
                        'ETF' if is_etf else str((item or {}).get('market', '주식')),
                        f"{float((item or {}).get('current_price', 0) or 0):,.0f}",
                        f"{float((item or {}).get('change_rate', 0) or 0):+.2f}%",
                        f"{int(float((item or {}).get('volume', 0) or 0)):,}",
                        note,
                    ]

                    widths = [90, 150, 80, 100, 90, 110, 150]
                    for idx, value in enumerate(values):
                        label = ctk.CTkLabel(
                            row,
                            text=value,
                            font=self._get_safe_font('body'),
                            width=widths[idx],
                            anchor='w'
                        )
                        label.grid(row=0, column=idx, padx=3, pady=3, sticky='w')
                        row.grid_columnconfigure(idx, weight=1)
                    rows_rendered += 1

            self._render_stock_user_activity(user_rows)

            if rows_rendered == 0:
                placeholder = ctk.CTkLabel(
                    self.stock_evaluator_scroll,
                    text=f"{self._get_stock_asset_mode_label()} 모드에서 표시할 종목/ETF 데이터가 없습니다. 증권사 연결 또는 Mock 설정을 확인하세요.",
                    font=self._get_safe_font("body"),
                    text_color=self._color('text_secondary', '#9ca3af')
                )
                placeholder.pack(pady=20)
        except Exception as e:
            print(f"종목 정보 업데이트 오류: {e}")

    def _collect_stock_user_activity(self, broker: str, adapter) -> List[dict]:
        """증권사별 보유 종목과 최근 체결 종목을 중복 없이 수집한다."""
        rows: List[dict] = []
        seen: set[tuple[str, str]] = set()

        try:
            positions = adapter.get_positions() if hasattr(adapter, 'get_positions') else []
        except Exception:
            positions = []
        for item in positions or []:
            code = str((item or {}).get('code') or (item or {}).get('symbol') or '').strip().upper()
            if not code:
                continue
            key = (str(broker).lower(), code)
            seen.add(key)
            rows.append({
                'broker': str(broker).upper(),
                'code': code,
                'name': str((item or {}).get('name') or code),
                'status': '보유',
                'quantity': float((item or {}).get('quantity') or (item or {}).get('qty') or 0),
                'price': float((item or {}).get('current_price') or (item or {}).get('price') or 0),
                'detail': f"평가손익 {float((item or {}).get('pnl') or 0):+,.0f}",
                'time': str((item or {}).get('timestamp') or '')[:19],
            })

        try:
            trades = adapter.get_trade_history(limit=100) if hasattr(adapter, 'get_trade_history') else []
        except Exception:
            trades = []
        for item in trades or []:
            code = str((item or {}).get('code') or (item or {}).get('symbol') or '').strip().upper()
            key = (str(broker).lower(), code)
            if not code or key in seen:
                continue
            seen.add(key)
            side = str((item or {}).get('side') or '').upper()
            side_label = '매수' if side in {'BUY', '매수'} else ('매도' if side in {'SELL', '매도'} else '체결')
            rows.append({
                'broker': str(broker).upper(),
                'code': code,
                'name': str((item or {}).get('name') or code),
                'status': '최근 체결',
                'quantity': float((item or {}).get('filled_quantity') or (item or {}).get('quantity') or 0),
                'price': float((item or {}).get('filled_price') or (item or {}).get('price') or 0),
                'detail': side_label,
                'time': str(
                    (item or {}).get('filled_at')
                    or (item or {}).get('timestamp')
                    or (item or {}).get('created_at')
                    or ''
                )[:19],
            })
        return rows

    def _render_stock_user_activity(self, rows: List[dict]) -> None:
        """실제 보유·체결 종목을 시장 미리보기와 분리해 표시한다."""
        if not hasattr(self, 'stock_user_activity_scroll'):
            return
        if not rows:
            ctk.CTkLabel(
                self.stock_user_activity_scroll,
                text="현재 연결된 증권사에서 확인된 보유 종목 또는 최근 체결 내역이 없습니다.",
                font=self._get_safe_font("body"),
                text_color=self._color('text_secondary', '#9ca3af'),
            ).pack(pady=24)
            return

        headers = ["브로커", "종목", "상태", "수량", "기준가", "손익/방향", "최근시각"]
        widths = [90, 170, 90, 90, 110, 130, 150]
        header = ctk.CTkFrame(self.stock_user_activity_scroll, fg_color="#172033")
        header.pack(fill="x", padx=4, pady=(2, 4))
        for idx, value in enumerate(headers):
            ctk.CTkLabel(
                header, text=value, font=self._get_safe_font("table_header"),
                width=widths[idx], anchor="w",
            ).grid(row=0, column=idx, padx=3, pady=4, sticky="w")
            header.grid_columnconfigure(idx, weight=1)

        for item in rows[:50]:
            values = [
                item['broker'],
                f"{item['name']} ({item['code']})",
                item['status'],
                f"{item['quantity']:,.4f}".rstrip('0').rstrip('.'),
                f"{item['price']:,.0f}",
                item['detail'],
                item['time'] or '-',
            ]
            row = ctk.CTkFrame(self.stock_user_activity_scroll, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=2)
            for idx, value in enumerate(values):
                ctk.CTkLabel(
                    row, text=value, font=self._get_safe_font("body"),
                    width=widths[idx], anchor="w",
                ).grid(row=0, column=idx, padx=3, pady=3, sticky="w")
                row.grid_columnconfigure(idx, weight=1)

    def _update_stock_trading_statistics(self):
        """주식 거래 통계 업데이트"""
        try:
            if not hasattr(self, 'stock_trading_stats_scroll'):
                return

            # 기존 위젯 제거
            for widget in self.stock_trading_stats_scroll.winfo_children():
                widget.destroy()

            try:
                from trading.stock_analysis_service import StockAnalysisService
                _analysis_svc_available = True
            except ImportError:
                _analysis_svc_available = False

            selected_broker = '전체'
            if hasattr(self, 'stock_trading_stats_broker_var'):
                try:
                    selected_broker = self.stock_trading_stats_broker_var.get()
                except Exception:
                    selected_broker = '전체'

            enabled_brokers = self.settings.get('enabled_stock_brokers', [])
            target_brokers = enabled_brokers
            if selected_broker not in ('전체', 'ALL'):
                target_brokers = [broker for broker in enabled_brokers if broker.upper() == selected_broker.upper()]

            rows_rendered = 0
            for broker in target_brokers:
                adapter = self._get_stock_adapter(broker)
                if not adapter:
                    continue

                # 분석 서비스 경유 통합 요약
                if _analysis_svc_available:
                    try:
                        svc = StockAnalysisService(adapter, broker_name=broker, recorder=getattr(self, 'recorder', None))
                        trade_summary = svc.get_trade_summary()
                        portfolio = svc.get_portfolio_summary()
                        db_summary = svc.get_db_trade_summary(days=30)
                    except Exception:
                        trade_summary = {}
                        portfolio = {}
                        db_summary = {}
                else:
                    trade_summary = {}
                    portfolio = {}
                    db_summary = {}
                    if hasattr(adapter, 'get_trading_stats'):
                        try:
                            s = adapter.get_trading_stats() or {}
                            trade_summary = {
                                'total_trades': s.get('total_trades', 0),
                                'buy_count': s.get('buy_count', 0),
                                'sell_count': s.get('sell_count', 0),
                                'today_count': s.get('today_trades', 0),
                                'open_orders_count': s.get('open_orders', 0),
                                'realized_pnl': float(s.get('realized_pnl', 0)),
                                'status': s.get('status', 'ok'),
                            }
                        except Exception:
                            pass

                row = ctk.CTkFrame(self.stock_trading_stats_scroll, fg_color='transparent')
                row.pack(fill='x', padx=4, pady=2)

                total_pnl = float(portfolio.get('total_pnl', 0) or 0)
                total_pnl_rate = float(portfolio.get('total_pnl_rate', 0) or 0)
                pnl_text = f"{total_pnl:+,.0f} ({total_pnl_rate:+.2f}%)"

                values = [
                    broker.upper(),
                    str(trade_summary.get('total_trades', 0)),
                    str(trade_summary.get('buy_count', 0)),
                    str(trade_summary.get('sell_count', 0)),
                    str(trade_summary.get('today_count', 0)),
                    str(trade_summary.get('open_orders_count', 0)),
                    f"{float(trade_summary.get('realized_pnl', 0) or 0):+,.0f}",
                    pnl_text,
                ]
                widths = [110, 80, 80, 80, 90, 90, 120, 150]
                for idx, value in enumerate(values):
                    label = ctk.CTkLabel(
                        row,
                        text=value,
                        font=self._get_safe_font('body')
                    )
                    label.grid(row=0, column=idx, padx=5, pady=5, sticky='ew')
                    row.grid_columnconfigure(idx, weight=1)
                rows_rendered += 1

                # DB 집계(30일) 기반 자산유형 상세 행 추가
                db_all = db_summary.get('all', {}) if isinstance(db_summary, dict) else {}
                db_stock = db_summary.get('stock', {}) if isinstance(db_summary, dict) else {}
                db_etf = db_summary.get('etf', {}) if isinstance(db_summary, dict) else {}

                if db_all or db_stock or db_etf:
                    detail_rows = [
                        ('DB-ALL', db_all),
                        ('DB-STOCK', db_stock),
                        ('DB-ETF', db_etf),
                    ]
                    for kind, stats in detail_rows:
                        if not stats:
                            continue
                        detail = ctk.CTkFrame(self.stock_trading_stats_scroll, fg_color='transparent')
                        detail.pack(fill='x', padx=20, pady=(0, 2))

                        win_rate = float(stats.get('win_rate', 0) or 0)
                        avg_pnl = float(stats.get('avg_pnl', 0) or 0)
                        dd = float(stats.get('max_drawdown', 0) or 0)

                        detail_values = [
                            f"  └ {kind}",
                            str(int(stats.get('total_trades', 0) or 0)),
                            str(int(stats.get('buy_count', 0) or 0)),
                            str(int(stats.get('sell_count', 0) or 0)),
                            '-',
                            '-',
                            f"{float(stats.get('realized_pnl', 0) or 0):+,.0f}",
                            f"승률 {win_rate:.1f}% | 평균 {avg_pnl:+.2f} | MDD {dd:+.2f}",
                        ]

                        for idx, value in enumerate(detail_values):
                            label = ctk.CTkLabel(
                                detail,
                                text=value,
                                font=self._get_safe_font('small'),
                                text_color=self._color('text_secondary', '#9ca3af')
                            )
                            label.grid(row=0, column=idx, padx=5, pady=2, sticky='ew')
                            detail.grid_columnconfigure(idx, weight=1)
                        rows_rendered += 1

            if hasattr(self, 'stock_trading_stats_status_label'):
                status_text = (
                    f"표시 브로커: {', '.join([b.upper() for b in target_brokers])} | DB 기준(최근 30일)"
                    if target_brokers else '표시 가능한 증권사가 없습니다.'
                )
                self.stock_trading_stats_status_label.configure(text=status_text)

            if rows_rendered == 0:
                placeholder = ctk.CTkLabel(
                    self.stock_trading_stats_scroll,
                    text="표시할 거래 통계가 없습니다. 증권사 연결 또는 Mock 거래를 먼저 확인하세요.",
                    font=self._get_safe_font("body"),
                    text_color=self._color('text_secondary', '#9ca3af')
                )
                placeholder.pack(pady=20)

            # 실행 품질 요약 패널 업데이트
            self._update_stock_execution_quality_summary()

        except Exception as e:
            print(f"주식 거래 통계 업데이트 오류: {e}")

    def _update_stock_execution_quality_summary(self):
        """실행 품질 지표(latency/slippage/성공률)를 통계 패널 하단에 추가."""
        try:
            recorder = getattr(self, 'recorder', None)
            if recorder is None:
                return
            loader = getattr(recorder, 'load_stock_execution_metrics', None)
            if not callable(loader):
                return

            metrics: list = loader(days=7)
            if not metrics:
                return

            total = len(metrics)
            success_count = sum(1 for m in metrics if m.get('success'))
            latency_vals = [float(m['latency_ms']) for m in metrics if m.get('latency_ms') is not None]
            slippage_vals = [float(m['slippage_bps']) for m in metrics if m.get('slippage_bps') is not None]

            success_rate = (success_count / total * 100) if total > 0 else 0.0
            avg_latency = (sum(latency_vals) / len(latency_vals)) if latency_vals else 0.0
            avg_slippage = (sum(slippage_vals) / len(slippage_vals)) if slippage_vals else 0.0

            scroll = getattr(self, 'stock_trading_stats_scroll', None)
            if scroll is None:
                return

            # 구분선
            sep = ctk.CTkFrame(scroll, height=1, fg_color=self._color('border', '#374151'))
            sep.pack(fill='x', padx=4, pady=(8, 4))

            header = ctk.CTkLabel(
                scroll,
                text="[실행 품질 요약 - 최근 7일]",
                font=self._get_safe_font('label'),
                text_color=self._color('text_secondary', '#9ca3af'),
                anchor='w',
            )
            header.pack(fill='x', padx=8, pady=(0, 4))

            quality_color = '#22c55e' if success_rate >= 90.0 else ('#f59e0b' if success_rate >= 70.0 else '#ef4444')
            summary_text = (
                f"  주문 수: {total}  |  성공률: {success_rate:.1f}%"
                f"  |  평균 지연: {avg_latency:.1f}ms"
                f"  |  평균 슬리피지: {avg_slippage:.2f}bps"
            )
            lbl = ctk.CTkLabel(
                scroll,
                text=summary_text,
                font=self._get_safe_font('small'),
                text_color=quality_color,
                anchor='w',
            )
            lbl.pack(fill='x', padx=8, pady=(0, 6))

        except Exception:
            pass



    def _get_stock_trading_stats_broker_options(self) -> List[str]:
        """주식 거래 통계용 증권사 옵션 목록 반환"""
        try:
            enabled_brokers = self.settings.get('enabled_stock_brokers', [])
            options = ["전체"] + [broker.upper() for broker in enabled_brokers]
            return options if options else ["전체"]
        except Exception:
            return ["전체"]

    def _get_crypto_trade_history_adapter(self, exchange_name: str):
        """통계 동기화에 사용할 실제 거래 루프 어댑터를 반환한다."""
        exchange = str(exchange_name or '').strip().lower()
        if not exchange or exchange == 'binance':
            return None
        main_app = getattr(self, 'main_app', None)
        unified_trader = getattr(main_app, 'unified_trader', None) if main_app is not None else None
        if unified_trader is not None:
            getter = getattr(unified_trader, 'get_exchange_client', None)
            if callable(getter):
                try:
                    adapter = getter(exchange)
                    if adapter is not None:
                        return adapter
                except Exception:
                    pass
        manager = getattr(self, 'unified_manager', None)
        if manager is None and main_app is not None:
            manager = getattr(main_app, 'unified_manager', None)
        if manager is None:
            return None
        trading_type = 'futures' if exchange in {'bybit', 'okx', 'bitget'} else 'spot'
        try:
            return manager.get_exchange(exchange, trading_type)
        except Exception:
            return None

    def _import_trading_stats_from_api(self):
        """사용자 계정에서 거래내역을 가져와 DB에 반영"""
        try:
            target_exchange = self._get_selected_trading_stats_exchange()
            if target_exchange in ("전체", "ALL"):
                # 기본 선택 거래소로 대체
                if isinstance(self.settings, dict):
                    target_exchange = str(self.settings.get('selected_exchange', 'binance')).upper()
                else:
                    target_exchange = "BINANCE"

            if target_exchange != "BINANCE":
                adapter = self._get_crypto_trade_history_adapter(target_exchange)
                if adapter is None or not hasattr(adapter, 'get_trade_history'):
                    self._set_trading_stats_status(
                        f"{target_exchange} 거래소 체결내역 어댑터를 찾을 수 없습니다.",
                        level='error',
                    )
                    return

                recorder = getattr(self, 'recorder', None)
                if recorder is None and hasattr(self, 'main_app'):
                    recorder = getattr(self.main_app, 'recorder', None)
                saver = getattr(recorder, 'save_exchange_execution_history', None)
                if not callable(saver):
                    self._set_trading_stats_status(
                        "체결 원장 저장소를 초기화할 수 없습니다. 앱을 재시작한 뒤 다시 시도하세요.",
                        level='error',
                    )
                    return

                # 계정 전체 체결목록 API가 없는 Bithumb/Upbit도 NoahAI가 보존한
                # 주문 ID는 fetch_order로 개별 재조회해 누락 체결을 먼저 복구한다.
                reconcile_result = {'checked': 0, 'confirmed': 0, 'pending': 0, 'failed': 0}
                main_app = getattr(self, 'main_app', None)
                unified_trader = getattr(main_app, 'unified_trader', None) if main_app else None
                if unified_trader is None:
                    unified_trader = getattr(self, 'unified_trader', None)
                reconciler = getattr(unified_trader, 'reconcile_exchange_order_receipts', None)
                if callable(reconciler):
                    reconcile_result = dict(reconciler(target_exchange.lower(), limit=500) or {})

                trades = adapter.get_trade_history(limit=500) or []
                sync_result = saver(
                    target_exchange.lower(),
                    [dict(item) for item in trades if isinstance(item, dict)],
                    source='dashboard_exchange_sync',
                )
                received = int(sync_result.get('received', 0) or 0)
                inserted = int(sync_result.get('inserted', 0) or 0)
                self._update_trading_statistics()
                recovered = int(reconcile_result.get('confirmed', 0) or 0)
                pending = int(reconcile_result.get('pending', 0) or 0)
                failed = int(reconcile_result.get('failed', 0) or 0)
                if recovered > 0:
                    self._set_trading_stats_status(
                        f"{target_exchange} 주문 ID로 확정 체결 {recovered}건을 복구했습니다. "
                        f"확인 대기 {pending}건 · 실패 {failed}건",
                        level='success',
                    )
                elif received <= 0:
                    capabilities = {}
                    try:
                        getter = getattr(adapter, "get_execution_capabilities", None)
                        capabilities = dict(getter() or {}) if callable(getter) else {}
                    except Exception:
                        capabilities = {}
                    if capabilities.get("history_available") is False:
                        self._set_trading_stats_status(
                            f"{target_exchange}는 현재 과거·수동 체결 자동 가져오기를 지원하지 않습니다. "
                            f"NoahAI 주문 ID 재확인: 대기 {pending}건 · 실패 {failed}건",
                            level='warning',
                        )
                    else:
                        self._set_trading_stats_status(
                            f"{target_exchange} 거래소 API에서 조회된 체결내역이 없습니다.",
                            level='info',
                        )
                elif inserted > 0:
                    self._set_trading_stats_status(
                        f"{target_exchange} 실제 체결 {inserted}건을 동기화했습니다. "
                        "승률·PnL은 NoahAI가 추적한 청산 완료 거래만 계산합니다.",
                        level='success',
                    )
                else:
                    self._set_trading_stats_status(
                        f"{target_exchange} 체결 {received}건이 이미 동기화되어 있습니다.",
                        level='info',
                    )
                return

            binance_client = getattr(self, 'binance_client', None)
            if not binance_client and hasattr(self, 'main_app'):
                binance_client = getattr(self.main_app, 'binance_client', None)
            if not binance_client:
                self.logger.error("[거래통계] Binance 클라이언트를 찾을 수 없습니다.")
                self._set_trading_stats_status("Binance 클라이언트를 찾을 수 없습니다.", level='error')
                return
            if hasattr(binance_client, '_has_api_keys') and not binance_client._has_api_keys():
                self.logger.warning("[거래통계] Binance API 키가 설정되어 있지 않습니다.")
                self._set_trading_stats_status("Binance API 키가 설정되어 있지 않습니다.", level='warning')
                return

            trades = binance_client.get_recent_trades(symbol=None, limit=200)
            self.logger.info(f"[거래통계] Binance 거래 내역 조회 완료 - 응답 {len(trades)}건")
            if not trades:
                self._set_trading_stats_status("가져올 거래 내역이 없습니다.", level='info')
                return

            recorder = getattr(self, 'recorder', None)
            if not recorder and hasattr(self, 'main_app'):
                recorder = getattr(self.main_app, 'recorder', None)
            if not recorder:
                self.logger.error("[거래통계] Recorder 인스턴스가 없어 저장 불가")
                self._set_trading_stats_status("Recorder 인스턴스를 찾을 수 없어 저장할 수 없습니다.", level='error')
                return

            execution_sync = {'received': len(trades), 'inserted': 0, 'skipped': 0}
            execution_saver = getattr(recorder, 'save_exchange_execution_history', None)
            if callable(execution_saver):
                execution_sync = execution_saver(
                    'binance',
                    [dict(item) for item in trades if isinstance(item, dict)],
                    source='dashboard_exchange_sync',
                ) or execution_sync

            execution_inserted = int(execution_sync.get('inserted', 0) or 0)
            self._set_trading_stats_status(
                f"{target_exchange} API 최근 {len(trades)}건 조회 · "
                f"체결원장 신규 {execution_inserted}건 · 청산 성과 신규 0건입니다. "
                "개별 체결은 실제 체결 원장에만 저장하며 NoahAI 진입-청산 성과로 만들지 않습니다. "
                "200건은 조회 상한이며 중복 저장 건수가 아닙니다.",
                level='success' if execution_inserted > 0 else 'info',
            )
            self._update_trading_statistics()

        except Exception as e:
            self.logger.error(f"[거래통계] 가져오기 실패: {e}")
            self._set_trading_stats_status(f"거래 통계 가져오기 실패: {e}", level='error')

    def _get_trading_stats_exchange_options(self) -> List[str]:
        options = ["전체"]
        try:
            enabled = ['binance']
            if isinstance(self.settings, dict):
                enabled = self.settings.get('enabled_exchanges', enabled)
            for ex in enabled:
                if not ex:
                    continue
                candidate = str(ex).upper()
                if candidate not in options:
                    options.append(candidate)
        except Exception:
            if "BINANCE" not in options:
                options.append("BINANCE")
        return options

    def _get_selected_trading_stats_exchange(self) -> str:
        try:
            if hasattr(self, 'trading_stats_exchange_var'):
                value = self.trading_stats_exchange_var.get()
                if value:
                    return value.upper()
        except Exception:
            pass
        return "전체"

    def _set_trading_stats_status(self, message: str, level: str = 'info'):
        if not hasattr(self, 'trading_stats_status_label'):
            return
        try:
            color_map = {
                'info': self._color('text_secondary', '#9ca3af'),
                'success': self._color('success', '#22c55e'),
                'warning': self._color('warning', '#f59e0b'),
                'error': self._color('danger', '#ef4444')
            }
            color = color_map.get(level, self._color('text_secondary', '#9ca3af'))
            self.trading_stats_status_label.configure(text=message, text_color=color)
        except Exception:
            self.trading_stats_status_label.configure(text=message)

    def _update_coin_info(self):
        """코인 정보 업데이트 (stub - 실제 구현 필요)"""
        try:
            if not hasattr(self, 'evaluator_scroll') or self.evaluator_scroll is None:
                return

            # 기존 행 제거
            try:
                for child in list(self.evaluator_scroll.winfo_children()):
                    try:
                        child.destroy()
                    except Exception:
                        pass
            except Exception:
                pass

            coins = getattr(self, 'selected_coins', []) or []

            if not coins:
                # 안내 문구
                try:
                    msg = ("선정된 코인이 없습니다.\n"
                           "• 아래 '코인 선정 실행' 버튼을 누르거나\n"
                           "• 자동매매를 시작하면 자동으로 코인이 선정됩니다.")
                    ctk.CTkLabel(
                        self.evaluator_scroll,
                        text=msg,
                        justify="left",
                        text_color="#9ca3af"
                    ).pack(pady=10, padx=10, anchor="w")
                except Exception:
                    pass
                return

            # 데이터 행
            try:
                for r_idx, coin in enumerate(coins):
                    row = ctk.CTkFrame(self.evaluator_scroll)
                    row.pack(fill="x", padx=4, pady=2)

                    # 점수 추출
                    overall_score = float(coin.get('overall_score', 0.0))

                    # AI종합점수 색상 결정
                    if overall_score >= 70:
                        score_color = "green"
                    elif overall_score >= 50:
                        score_color = "orange"
                    else:
                        score_color = "red"

                    vals = [
                        str(coin.get('symbol', '')),
                        f"{overall_score:.1f}",
                        f"{float(coin.get('volatility_score', 0.0)):.1f}",
                        f"{float(coin.get('volume_score', 0.0)):.1f}",
                        f"{float(coin.get('technical_score', 0.0)):.1f}",
                        f"{float(coin.get('trend_score', 0.0)):.1f}",
                        f"{float(coin.get('risk_score', 0.0)):.1f}",
                    ]

                    for c_idx, v in enumerate(vals):
                        # AI종합점수(index 1)는 색상 적용
                        if c_idx == 1:
                            lbl = ctk.CTkLabel(row, text=v, text_color=score_color, font=("", 11, "bold"))
                        else:
                            lbl = ctk.CTkLabel(row, text=v)
                        lbl.grid(row=0, column=c_idx, padx=3, pady=3, sticky="ew")
                        row.grid_columnconfigure(c_idx, weight=1)
            except Exception as e:
                print(f"코인 정보 행 구성 오류: {e}")
        except Exception as e:
            print(f"코인 정보 업데이트 오류: {e}")

    def _update_trading_statistics(self):
        """거래 통계 탭 업데이트 - trade_log에서 직접 집계"""
        try:
            if not hasattr(self, 'trading_stats_scroll') or self.trading_stats_scroll is None:
                return

            # 기존 위젯 제거
            try:
                for child in list(self.trading_stats_scroll.winfo_children()):
                    try:
                        child.destroy()
                    except Exception:
                        pass
            except Exception:
                pass

            # trade_log에서 심볼/거래소별 통계 집계
            import sqlite3, os

            db_path = self._get_dashboard_read_db_path()
            if not os.path.exists(db_path):
                ctk.CTkLabel(self.trading_stats_scroll, text="데이터베이스 파일을 찾을 수 없습니다.").pack(pady=10)
                self._set_trading_stats_status("거래 데이터베이스를 찾을 수 없습니다.", level='error')
                return

            exchange_filter_value = self._get_selected_trading_stats_exchange()
            normalized_filter = None
            if exchange_filter_value not in ("전체", "ALL"):
                normalized_filter = exchange_filter_value.lower()

            try:
                with sqlite3.connect(db_path) as conn:
                    cur = conn.cursor()
                    execution_summary = self._get_exchange_execution_summary(
                        conn,
                        normalized_filter,
                    )

                    # 레거시 DB 호환: fees 컬럼이 없으면 0으로 처리
                    has_fees_column = False
                    try:
                        cur.execute("PRAGMA table_info(trade_log)")
                        table_cols = {str(col[1]).lower() for col in (cur.fetchall() or []) if len(col) > 1}
                        has_fees_column = 'fees' in table_cols
                    except Exception:
                        has_fees_column = False

                    fee_expr = "COALESCE(fees, 0)" if has_fees_column else "0"

                    query = f"""
                        SELECT
                            CASE
                                WHEN exchange IS NULL OR TRIM(exchange) = '' THEN 'BINANCE (LEGACY)'
                                ELSE exchange
                            END as exchange_name,
                            symbol,
                            COUNT(*) as total_trades,
                            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                            AVG(pnl_percent) as avg_profit_rate,
                            SUM(COALESCE(pnl, 0)) as total_pnl,
                            SUM({fee_expr}) as total_fees,
                            AVG({fee_expr}) as avg_fee,
                            MAX(pnl) as max_profit,
                            MIN(pnl) as max_loss,
                            SUM(ABS(COALESCE(entry_price, 0) * COALESCE(quantity, 0))) as total_notional,
                            AVG(
                                CASE
                                    WHEN entry_time IS NOT NULL
                                     AND exit_time IS NOT NULL
                                     AND julianday(exit_time) > julianday(entry_time)
                                    THEN (julianday(exit_time) - julianday(entry_time)) * 1440.0
                                    ELSE NULL
                                END
                            ) as avg_hold_minutes,
                            SUM(
                                CASE
                                    WHEN entry_time IS NOT NULL
                                     AND exit_time IS NOT NULL
                                     AND julianday(exit_time) > julianday(entry_time)
                                    THEN 1 ELSE 0
                                END
                            ) as valid_hold_count
                        FROM trade_log
                        WHERE exit_time IS NOT NULL
                          AND LOWER(COALESCE(reason, '')) != 'binance_import'
                    """
                    params: List[Any] = []
                    if normalized_filter:
                        if normalized_filter == 'binance':
                            query += " AND (LOWER(COALESCE(exchange, 'binance')) = 'binance' OR TRIM(COALESCE(exchange, '')) = '')"
                        else:
                            query += " AND LOWER(COALESCE(exchange, 'unknown')) = ?"
                            params.append(normalized_filter)
                    query += " GROUP BY exchange_name, symbol"
                    query += " ORDER BY exchange_name, total_trades DESC"

                    cur.execute(query, params)
                    rows = cur.fetchall()

                    if not rows:
                        msg = "청산된 거래가 없습니다."
                        if normalized_filter:
                            msg = f"{exchange_filter_value} 거래소에 청산된 거래가 없습니다."
                        ctk.CTkLabel(self.trading_stats_scroll, text=msg).pack(pady=10)
                        execution_count = int(execution_summary.get('count', 0) or 0)
                        self._set_trading_stats_kpis(execution_count, 0, 0.0, 0.0)
                        self._set_trading_stats_operating_metrics(
                            dict(execution_summary.get('notional_by_currency') or {}),
                            None,
                            0,
                            0,
                        )
                        rendered_count = self._render_exchange_execution_history(
                            conn,
                            normalized_filter,
                        )
                        if rendered_count > 0:
                            self._set_trading_stats_status(
                                f"{exchange_filter_value} 실제 체결 {execution_count}건 · "
                                "NoahAI 청산 성과 기록 0건",
                                level='info',
                            )
                        else:
                            self._set_trading_stats_status(msg, level='info')
                        return

                    grand_total = sum(int(row[2] or 0) for row in rows)
                    actual_closed_total = grand_total
                    grand_wins = sum(int(row[3] or 0) for row in rows)
                    grand_pnl = sum(float(row[6] or 0.0) for row in rows)
                    grand_fees = sum(float(row[7] or 0.0) for row in rows)
                    from utils.trade_operating_metrics import infer_quote_currency

                    grand_notional_by_currency: Dict[str, float] = {}
                    grand_hold_weighted_minutes = 0.0
                    grand_valid_hold_count = 0
                    for row in rows:
                        currency = infer_quote_currency(row[0], row[1])
                        grand_notional_by_currency[currency] = (
                            grand_notional_by_currency.get(currency, 0.0)
                            + float(row[11] or 0.0)
                        )
                        valid_count = int(row[13] or 0)
                        if valid_count > 0 and row[12] is not None:
                            grand_hold_weighted_minutes += float(row[12]) * valid_count
                            grand_valid_hold_count += valid_count
                    grand_avg_hold_minutes = (
                        grand_hold_weighted_minutes / grand_valid_hold_count
                        if grand_valid_hold_count
                        else None
                    )
                    display_overrides = self._get_broadcast_display_overrides()
                    override_trades = display_overrides.get('total_trades')
                    override_win_rate = display_overrides.get('win_rate_percent')
                    override_pnl = display_overrides.get('total_pnl_usdt')
                    override_fees = display_overrides.get('total_fees_usdt')

                    if override_trades is not None:
                        grand_total = int(round(float(override_trades)))
                    if override_win_rate is not None and grand_total > 0:
                        # 카드 승률 표시는 wins/total 기반이므로 오버레이 win_rate를 역산하여 적용
                        grand_wins = int(round(grand_total * (float(override_win_rate) / 100.0)))
                    if override_pnl is not None:
                        grand_pnl = float(override_pnl)
                    if override_fees is not None:
                        grand_fees = float(override_fees)

                    exchange_names = {str(row[0] or '').upper() for row in rows}
                    has_krw = bool(exchange_names & {"UPBIT", "BITHUMB"})
                    has_non_krw = bool(exchange_names - {"UPBIT", "BITHUMB"})
                    execution_count = int(execution_summary.get('count', 0) or 0)
                    self._set_trading_stats_kpis(
                        execution_count or grand_total, grand_wins, grand_pnl, grand_fees,
                        mixed_currency=(normalized_filter is None and has_krw and has_non_krw),
                        win_rate_denominator=actual_closed_total,
                    )
                    self._set_trading_stats_operating_metrics(
                        dict(execution_summary.get('notional_by_currency') or grand_notional_by_currency),
                        grand_avg_hold_minutes,
                        grand_valid_hold_count,
                        actual_closed_total,
                    )

                    # 거래소별 그룹 구성
                    sections: Dict[str, List[Tuple[Any, ...]]] = {}
                    for row_data in rows:
                        exchange_name = str(row_data[0] or 'UNKNOWN').upper()
                        sections.setdefault(exchange_name, []).append(row_data[1:])

                    total_symbols = 0
                    all_trades = 0
                    all_fees = 0.0
                    for exchange_name, exchange_rows in sections.items():
                        section_label = ctk.CTkLabel(
                            self.trading_stats_scroll,
                            text=f"{exchange_name}",
                            font=self._get_safe_font("subtitle"),
                            text_color=self._color('text_primary', '#f9fafb')
                        )
                        section_label.pack(anchor="w", padx=4, pady=(6, 2))

                        section_total_trades = sum(int(r[1] or 0) for r in exchange_rows)
                        section_total_pnl = sum(float(r[5] or 0.0) for r in exchange_rows)
                        section_total_fees = sum(float(r[6] or 0.0) for r in exchange_rows)
                        section_total_notional = sum(float(r[10] or 0.0) for r in exchange_rows)
                        section_valid_hold_count = sum(int(r[12] or 0) for r in exchange_rows)
                        section_hold_weighted_minutes = sum(
                            float(r[11] or 0.0) * int(r[12] or 0)
                            for r in exchange_rows
                        )
                        section_avg_hold_minutes = (
                            section_hold_weighted_minutes / section_valid_hold_count
                            if section_valid_hold_count
                            else None
                        )
                        section_avg_fee = (section_total_fees / section_total_trades) if section_total_trades > 0 else 0.0
                        fee_ratio_percent = (section_total_fees / abs(section_total_pnl) * 100.0) if abs(section_total_pnl) > 0 else 0.0

                        all_trades += section_total_trades
                        all_fees += section_total_fees

                        settlement_unit = "KRW" if exchange_name in {"UPBIT", "BITHUMB"} else "USDT"
                        section_summary = ctk.CTkLabel(
                            self.trading_stats_scroll,
                            text=(
                                f"총 {section_total_trades}건 | 누적PnL {section_total_pnl:.2f} {settlement_unit} | "
                                f"누적Fee {section_total_fees:.2f} {settlement_unit} | 평균Fee {section_avg_fee:.4f} {settlement_unit} | "
                                f"Fee/PnL {fee_ratio_percent:.2f}%"
                            ),
                            font=self._get_safe_font("small"),
                            text_color=self._color('text_secondary', '#9ca3af')
                        )
                        section_summary.pack(anchor="w", padx=8, pady=(0, 4))

                        from utils.trade_operating_metrics import (
                            format_hold_duration,
                            format_notional,
                        )
                        section_operating_summary = ctk.CTkLabel(
                            self.trading_stats_scroll,
                            text=(
                                f"실제 체결금액 {format_notional(settlement_unit, section_total_notional)} | "
                                f"평균 보유시간 {format_hold_duration(section_avg_hold_minutes)} "
                                f"(유효 {section_valid_hold_count}/{section_total_trades}건)"
                            ),
                            font=self._get_safe_font("small"),
                            text_color=self._color('info', '#60a5fa'),
                        )
                        section_operating_summary.pack(anchor="w", padx=8, pady=(0, 4))

                        for row_data in exchange_rows:
                            (
                                symbol, total, wins, losses, avg_profit_rate,
                                total_pnl, total_fees, _avg_fee, max_profit,
                                max_loss, _total_notional, _avg_hold_minutes,
                                _valid_hold_count,
                            ) = row_data
                            total_symbols += 1

                            avg_profit_rate = float(avg_profit_rate) if avg_profit_rate is not None else 0.0
                            max_profit = float(max_profit) if max_profit is not None else 0.0
                            max_loss = float(max_loss) if max_loss is not None else 0.0

                            win_rate = (wins / total * 100) if total > 0 else 0.0
                            win_rate_color = "green" if win_rate >= 50 else "red" if win_rate > 0 else "gray"
                            avg_rate_color = "green" if avg_profit_rate > 0 else "red" if avg_profit_rate < 0 else "gray"

                            row_frame = ctk.CTkFrame(self.trading_stats_scroll, height=46, corner_radius=9, fg_color="#111827")
                            row_frame.pack(fill="x", padx=4, pady=3)

                            values = [
                                symbol,
                                str(total),
                                str(wins),
                                str(losses),
                                f"{win_rate:.1f}%",
                                f"{avg_profit_rate:.2f}%",
                                f"{float(total_pnl or 0.0):+.2f}",
                                f"{float(total_fees or 0.0):.2f}",
                                f"{max_profit:.2f}",
                                f"{max_loss:.2f}"
                            ]

                            for col_idx, val in enumerate(values):
                                if col_idx == 4:
                                    lbl = ctk.CTkLabel(row_frame, text=val, text_color=win_rate_color, font=ctk.CTkFont(size=13, weight="bold"))
                                elif col_idx == 5:
                                    lbl = ctk.CTkLabel(row_frame, text=val, text_color=avg_rate_color, font=ctk.CTkFont(size=13, weight="bold"))
                                else:
                                    lbl = ctk.CTkLabel(row_frame, text=val, font=ctk.CTkFont(size=13))
                                lbl.grid(row=0, column=col_idx, padx=7, pady=9, sticky="ew")
                                row_frame.grid_columnconfigure(col_idx, weight=1)

                    if override_trades is not None:
                        all_trades = int(round(float(override_trades)))
                    if override_fees is not None:
                        all_fees = float(override_fees)

                    summary_exchange = exchange_filter_value if exchange_filter_value not in ("전체", "ALL") else "전체"
                    summary_unit = (
                        "KRW" if summary_exchange in {"UPBIT", "BITHUMB"}
                        else "USDT" if summary_exchange != "전체"
                        else "각 거래소 기준통화"
                    )
                    summary_msg = (
                        f"{summary_exchange} 거래소 기준 통계를 갱신했습니다. "
                        f"(코인 {total_symbols}개, 총 {all_trades}건, 누적Fee {all_fees:.2f} {summary_unit})"
                    )
                    self._render_exchange_execution_history(conn, normalized_filter)
                    self._set_trading_stats_status(summary_msg, level='info')

            except Exception as db_err:
                print(f"DB 조회 오류: {db_err}")
                ctk.CTkLabel(self.trading_stats_scroll, text=f"데이터 조회 오류: {db_err}").pack(pady=10)
                self._set_trading_stats_status(f"거래 통계 조회 오류: {db_err}", level='error')

        except Exception as e:
            print(f"거래 통계 업데이트 오류: {e}")

    def _get_exchange_execution_summary(
        self,
        conn,
        normalized_exchange: Optional[str],
    ) -> Dict[str, Any]:
        """확정 체결 원장을 기준으로 건수와 통화별 체결금액을 집계한다."""
        summary: Dict[str, Any] = {'count': 0, 'notional_by_currency': {}}
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='exchange_execution_log'"
            )
            if cur.fetchone() is None:
                return summary
            columns = {
                str(row[1])
                for row in cur.execute("PRAGMA table_info(exchange_execution_log)").fetchall()
            }
            conditions = [
                "confirmation_status = 'confirmed'"
                if 'confirmation_status' in columns
                else "1 = 1"
            ]
            params: List[Any] = []
            if normalized_exchange:
                conditions.append("LOWER(exchange) = ?")
                params.append(str(normalized_exchange).lower())
            cur.execute(
                f"""
                SELECT exchange, COUNT(*), SUM(COALESCE(cost, 0))
                FROM exchange_execution_log
                WHERE {' AND '.join(conditions)}
                GROUP BY exchange
                """,
                tuple(params),
            )
            notional: Dict[str, float] = {}
            for exchange, count, cost in cur.fetchall():
                summary['count'] += int(count or 0)
                currency = 'KRW' if str(exchange).lower() in {'upbit', 'bithumb'} else 'USDT'
                notional[currency] = notional.get(currency, 0.0) + float(cost or 0.0)
            summary['notional_by_currency'] = notional
        except Exception as exc:
            self.logger.warning(f"확정 체결 원장 집계 실패: {exc}")
        return summary

    def _render_exchange_execution_history(
        self,
        conn,
        normalized_exchange: Optional[str],
        *,
        limit: int = 50,
    ) -> int:
        """거래소 원장 체결을 청산 성과와 분리해 표시한다."""
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='exchange_execution_log'"
            )
            if cur.fetchone() is None:
                return 0

            columns = {
                str(row[1])
                for row in cur.execute("PRAGMA table_info(exchange_execution_log)").fetchall()
            }
            params: List[Any] = []
            conditions: List[str] = []
            if 'confirmation_status' in columns:
                conditions.append("confirmation_status = 'confirmed'")
            if normalized_exchange:
                conditions.append("LOWER(exchange) = ?")
                params.append(str(normalized_exchange).lower())
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            cur.execute(
                f"""
                SELECT exchange, symbol, side, price, quantity, cost, fee,
                       fee_currency, executed_at
                FROM exchange_execution_log
                {where}
                ORDER BY COALESCE(executed_at, created_at) DESC, id DESC
                LIMIT ?
                """,
                tuple(params + [max(1, int(limit))]),
            )
            rows = cur.fetchall()
            if not rows:
                return 0

            separator = ctk.CTkFrame(
                self.trading_stats_scroll,
                height=1,
                fg_color=self._color('border', '#334155'),
            )
            separator.pack(fill='x', padx=4, pady=(12, 8))
            ctk.CTkLabel(
                self.trading_stats_scroll,
                text=f"거래소 실제 체결 원장 · 최근 {len(rows)}건",
                font=self._get_safe_font('subtitle'),
                text_color=self._color('text_primary', '#f9fafb'),
            ).pack(anchor='w', padx=4, pady=(0, 2))
            ctk.CTkLabel(
                self.trading_stats_scroll,
                text="수동 주문 포함 거래소 체결입니다. 승률·PnL은 위 청산 완료 통계에서만 계산합니다.",
                font=self._get_safe_font('small'),
                text_color=self._color('info', '#60a5fa'),
            ).pack(anchor='w', padx=4, pady=(0, 6))

            headers = ['거래소', '종목', '방향', '체결가', '수량', '체결금액', '수수료', '시각']
            header = ctk.CTkFrame(self.trading_stats_scroll, fg_color='#172033', corner_radius=8)
            header.pack(fill='x', padx=4, pady=(0, 3))
            for index, value in enumerate(headers):
                ctk.CTkLabel(
                    header,
                    text=value,
                    font=self._get_safe_font('table_header'),
                ).grid(row=0, column=index, padx=5, pady=5, sticky='ew')
                header.grid_columnconfigure(index, weight=1)

            for row in rows:
                exchange, symbol, side, price, quantity, cost, fee, fee_currency, executed_at = row
                quote = 'KRW' if str(exchange).lower() in {'upbit', 'bithumb'} else 'USDT'
                fee_unit = str(fee_currency or quote).upper()
                values = [
                    str(exchange or '').upper(),
                    str(symbol or ''),
                    '매수' if str(side or '').lower() == 'buy' else (
                        '매도' if str(side or '').lower() == 'sell' else str(side or '-')
                    ),
                    f"{float(price or 0):,.4f}".rstrip('0').rstrip('.'),
                    f"{float(quantity or 0):,.8f}".rstrip('0').rstrip('.'),
                    f"{float(cost or 0):,.2f} {quote}",
                    f"{float(fee or 0):,.4f} {fee_unit}",
                    str(executed_at or '-')[:19],
                ]
                row_frame = ctk.CTkFrame(
                    self.trading_stats_scroll,
                    fg_color='#111827',
                    corner_radius=8,
                )
                row_frame.pack(fill='x', padx=4, pady=2)
                for index, value in enumerate(values):
                    ctk.CTkLabel(
                        row_frame,
                        text=value,
                        font=self._get_safe_font('small'),
                    ).grid(row=0, column=index, padx=5, pady=6, sticky='ew')
                    row_frame.grid_columnconfigure(index, weight=1)
            return len(rows)
        except Exception as exc:
            self.logger.warning(f"거래소 실제 체결 원장 표시 실패: {exc}")
            return 0

    def _set_trading_stats_kpis(
        self,
        total: int,
        wins: int,
        pnl: float,
        fees: float,
        *,
        mixed_currency: bool = False,
        win_rate_denominator: Optional[int] = None,
    ) -> None:
        """거래 통계 요약 카드를 갱신한다."""
        try:
            labels = getattr(self, 'trading_stats_kpi_labels', {}) or {}
            denominator = total if win_rate_denominator is None else int(win_rate_denominator)
            win_rate = (float(wins) / float(denominator) * 100.0) if denominator else 0.0
            try:
                override_win_rate = self._get_broadcast_display_overrides().get('win_rate_percent')
                if override_win_rate is not None:
                    win_rate = float(override_win_rate)
            except Exception:
                pass
            values = {
                'trades': f"{int(total):,}건",
                'win_rate': f"{win_rate:.1f}%",
                'pnl': "거래소별 확인" if mixed_currency else f"{float(pnl):+,.2f}",
                'fees': "거래소별 확인" if mixed_currency else f"{float(fees):,.2f}",
            }
            for key, text in values.items():
                label = labels.get(key)
                if label is not None:
                    label.configure(text=text)
        except Exception:
            pass

    def _set_trading_stats_operating_metrics(
        self,
        notional_by_currency: Dict[str, float],
        avg_hold_minutes: Optional[float],
        valid_hold_count: int,
        closed_count: int,
    ) -> None:
        """체결금액과 평균 보유시간을 기존 거래 통계 요약에 표시한다."""
        try:
            label = getattr(self, 'trading_stats_operating_label', None)
            if label is None:
                return
            from utils.trade_operating_metrics import (
                format_hold_duration,
                format_notional,
            )

            amounts = [
                format_notional("USDT", (notional_by_currency or {}).get("USDT", 0.0)),
                format_notional("KRW", (notional_by_currency or {}).get("KRW", 0.0)),
            ]
            for currency in sorted(notional_by_currency or {}):
                if currency not in {"USDT", "KRW"}:
                    amounts.append(
                        format_notional(currency, notional_by_currency[currency])
                    )
            hold_text = format_hold_duration(avg_hold_minutes)
            coverage = (
                f"유효 {int(valid_hold_count):,}/{int(closed_count):,}건"
                if closed_count
                else "청산 기록 없음"
            )
            label.configure(
                text=(
                    f"체결금액 {' · '.join(amounts)} | "
                    f"평균 보유시간 {hold_text} ({coverage})"
                )
            )
        except Exception:
            pass

    def _get_dashboard_read_db_path(self) -> str:
        """대시보드 읽기용 DB 경로를 반환한다 (관리자 방송 리플레이 지원)."""
        try:
            from path_utils import get_current_user_account, get_db_file_path
            from utils.admin_utils import is_admin_account

            default_db_path = get_db_file_path()
            settings = self.settings if isinstance(self.settings, dict) else {}
            replay_enabled = bool(settings.get('broadcast_replay_enabled', False))
            replay_source = str(settings.get('broadcast_replay_source_account', '') or '').strip()

            if not replay_enabled or not replay_source:
                return default_db_path

            current_user = (
                get_current_user_account()
                or settings.get('user_id')
                or settings.get('username')
                or ''
            )
            if not is_admin_account(str(current_user or '').strip()):
                return default_db_path

            current_account_dir = os.path.dirname(default_db_path)
            data_root_dir = os.path.dirname(current_account_dir)
            replay_db_path = os.path.join(data_root_dir, replay_source, 'trading.db')

            if os.path.exists(replay_db_path):
                return replay_db_path
            return default_db_path
        except Exception:
            try:
                from path_utils import get_db_file_path
                return get_db_file_path()
            except Exception:
                return ''

    def _get_dashboard_replay_log_file_path(self, exchange: str) -> Optional[str]:
        """관리자 방송 리플레이용 로그 파일 경로를 반환한다."""
        try:
            from path_utils import get_current_user_account, get_app_base_dir
            from utils.admin_utils import is_admin_account

            settings = self.settings if isinstance(self.settings, dict) else {}
            replay_enabled = bool(settings.get('broadcast_replay_enabled', False))
            replay_source = str(settings.get('broadcast_replay_source_account', '') or '').strip()
            if not replay_enabled or not replay_source:
                return None

            current_user = (
                get_current_user_account()
                or settings.get('user_id')
                or settings.get('username')
                or ''
            )
            if not is_admin_account(str(current_user or '').strip()):
                return None

            base_log_dir = os.path.join(get_app_base_dir(), 'data', replay_source, 'logs')
            ex = str(exchange or '').strip().lower()
            candidates = [
                os.path.join(base_log_dir, f'trading_{ex}.log'),
                os.path.join(base_log_dir, 'trading.log'),
            ]
            for path in candidates:
                if os.path.exists(path):
                    return path
            return None
        except Exception:
            return None

    def _get_replay_positions_for_exchange(
        self,
        replay_db_path: str,
        exchange: str,
        *,
        max_positions: int = 3,
        timeline_step_seconds: int = 120,
        advance_timeline: bool = True,
    ) -> Dict[str, Dict[str, Any]]:
        """리플레이 타임라인 시점 기준으로 포지션을 계산해 반환한다."""
        import sqlite3

        ex_l = str(exchange or '').strip().lower()
        timeline_key = ex_l or 'unknown'

        with sqlite3.connect(replay_db_path) as conn:
            cur = conn.cursor()
            if ex_l == 'binance':
                ex_where = "(LOWER(COALESCE(exchange, 'binance')) = 'binance' OR TRIM(COALESCE(exchange, '')) = '')"
                ex_params: Tuple[Any, ...] = tuple()
            else:
                ex_where = "LOWER(COALESCE(exchange, 'unknown')) = ?"
                ex_params = (ex_l,)

            cur.execute(
                f"""
                SELECT MIN(entry_time), MAX(COALESCE(exit_time, entry_time))
                FROM trade_log
                WHERE {ex_where}
                """,
                ex_params,
            )
            bounds = cur.fetchone() or (None, None)
            start_time = str(bounds[0] or '').strip()
            end_time = str(bounds[1] or '').strip()

            if not start_time or not end_time:
                return {}

            # 리플레이를 초기 구간(포지션 희소)에서 시작하면 1개/0개가 잦아 보이므로,
            # 마지막 2시간 구간을 기본 시작점으로 사용해 변화가 자연스럽게 보이게 한다.
            cur.execute("SELECT datetime(?, '-2 hours')", (end_time,))
            recent_start_row = cur.fetchone() or (None,)
            recent_start = str(recent_start_row[0] or '').strip()
            effective_start = recent_start if recent_start and recent_start > start_time else start_time

            state = self._replay_position_timeline.get(timeline_key)
            if not state:
                state = {'cursor': effective_start, 'start': effective_start, 'end': end_time}
                self._replay_position_timeline[timeline_key] = state
            else:
                state['start'] = effective_start
                state['end'] = end_time
                if str(state.get('cursor') or '').strip() < effective_start:
                    state['cursor'] = effective_start

            cursor = str(state.get('cursor') or start_time)

            cur.execute(
                f"""
                                SELECT id, symbol, side, quantity, entry_price, pnl, leverage
                FROM trade_log
                WHERE {ex_where}
                  AND entry_time <= ?
                  AND (exit_time IS NULL OR exit_time > ?)
                ORDER BY entry_time DESC, id DESC
                LIMIT ?
                """,
                (*ex_params, cursor, cursor, int(max_positions)),
            )
            rows = cur.fetchall() or []

            if advance_timeline:
                cur.execute("SELECT datetime(?, '+" + str(int(timeline_step_seconds)) + " seconds')", (cursor,))
                next_row = cur.fetchone() or (None,)
                next_cursor = str(next_row[0] or '').strip()
                if not next_cursor or next_cursor > end_time:
                    next_cursor = effective_start
                state['cursor'] = next_cursor

        replay_positions: Dict[str, Dict[str, Any]] = {}
        for _row_id, symbol, side, quantity, entry_price, pnl, leverage in rows:
            sym = str(symbol or '').strip()
            if not sym:
                continue

            qty = float(quantity or 0)
            entry_val = float(entry_price or 0)
            fallback_pnl = float(pnl or 0)

            try:
                with sqlite3.connect(replay_db_path) as price_conn:
                    price_cur = price_conn.cursor()
                    if ex_l == 'binance':
                        price_cur.execute(
                            """
                            SELECT COALESCE(
                                (
                                    SELECT exit_price
                                    FROM trade_log
                                    WHERE symbol = ?
                                      AND exit_time IS NOT NULL
                                      AND exit_time <= ?
                                      AND (LOWER(COALESCE(exchange, 'binance')) = 'binance' OR TRIM(COALESCE(exchange, '')) = '')
                                      AND exit_price IS NOT NULL
                                    ORDER BY exit_time DESC, id DESC
                                    LIMIT 1
                                ),
                                (
                                    SELECT entry_price
                                    FROM trade_log
                                    WHERE symbol = ?
                                      AND entry_time <= ?
                                      AND (LOWER(COALESCE(exchange, 'binance')) = 'binance' OR TRIM(COALESCE(exchange, '')) = '')
                                      AND entry_price IS NOT NULL
                                    ORDER BY entry_time DESC, id DESC
                                    LIMIT 1
                                )
                            )
                            """,
                            (sym, cursor, sym, cursor),
                        )
                    else:
                        price_cur.execute(
                            """
                            SELECT COALESCE(
                                (
                                    SELECT exit_price
                                    FROM trade_log
                                    WHERE symbol = ?
                                      AND exit_time IS NOT NULL
                                      AND exit_time <= ?
                                      AND LOWER(COALESCE(exchange, 'unknown')) = ?
                                      AND exit_price IS NOT NULL
                                    ORDER BY exit_time DESC, id DESC
                                    LIMIT 1
                                ),
                                (
                                    SELECT entry_price
                                    FROM trade_log
                                    WHERE symbol = ?
                                      AND entry_time <= ?
                                      AND LOWER(COALESCE(exchange, 'unknown')) = ?
                                      AND entry_price IS NOT NULL
                                    ORDER BY entry_time DESC, id DESC
                                    LIMIT 1
                                )
                            )
                            """,
                            (sym, cursor, ex_l, sym, cursor, ex_l),
                        )
                    mark_row = price_cur.fetchone() or (None,)
                    mark_price = float(mark_row[0]) if mark_row[0] not in (None, '') else entry_val
            except Exception:
                mark_price = entry_val

            side_text = str(side or 'LONG').upper()
            is_long = side_text in {'BUY', 'LONG'}
            dynamic_pnl = (mark_price - entry_val) * qty if is_long else (entry_val - mark_price) * qty

            replay_positions[sym] = {
                'side': side_text,
                'quantity': qty,
                'entry_price': entry_val,
                'unrealized_pnl': dynamic_pnl if abs(dynamic_pnl) > 0 else fallback_pnl,
                'leverage': leverage,
            }

        # 재생 중 포지션이 너무 빨리 사라져 보이지 않도록 짧은 잔류 표시를 적용한다.
        state = self._replay_position_timeline.setdefault(timeline_key, {})
        last_positions = state.get('last_positions') if isinstance(state.get('last_positions'), dict) else {}
        linger = state.get('linger') if isinstance(state.get('linger'), dict) else {}

        if not advance_timeline:
            if last_positions:
                return dict(list(last_positions.items())[:int(max_positions)])
            return replay_positions

        for sym in replay_positions.keys():
            linger[sym] = 4

        display_positions: Dict[str, Dict[str, Any]] = dict(replay_positions)
        if len(display_positions) < int(max_positions):
            for sym, pos in last_positions.items():
                if len(display_positions) >= int(max_positions):
                    break
                if sym in display_positions:
                    continue
                remain = int(linger.get(sym, 0) or 0)
                if remain > 0:
                    display_positions[sym] = pos
                    linger[sym] = remain - 1

        # 사용이 끝난 잔류 카운터 정리
        linger = {k: v for k, v in linger.items() if int(v or 0) > 0 or k in display_positions}
        state['linger'] = linger
        state['last_positions'] = dict(list(display_positions.items())[:int(max_positions)])

        return state['last_positions']

    def _get_broadcast_display_overrides(self) -> Dict[str, Optional[float]]:
        """관리자 방송 시 화면 표시용 잔고/손익 오버레이 값을 반환한다."""
        result: Dict[str, Optional[float]] = {
            'balance_usdt': None,
            'total_pnl_usdt': None,
            'total_trades': None,
            'win_rate_percent': None,
            'total_fees_usdt': None,
        }
        try:
            settings = self.settings if isinstance(self.settings, dict) else {}
            # 방송 리플레이 토글 하나로 오버레이 표시도 함께 ON/OFF 되도록 연동
            replay_enabled = bool(settings.get('broadcast_replay_enabled', False))
            if not replay_enabled:
                return result

            raw_balance = settings.get('broadcast_display_balance_usdt', None)
            raw_pnl = settings.get('broadcast_display_total_pnl_usdt', None)
            raw_trades = settings.get('broadcast_display_total_trades', None)
            raw_win_rate = settings.get('broadcast_display_win_rate_percent', None)
            raw_fees = settings.get('broadcast_display_total_fees_usdt', None)

            if raw_balance not in (None, ''):
                result['balance_usdt'] = float(raw_balance)
            if raw_pnl not in (None, ''):
                result['total_pnl_usdt'] = float(raw_pnl)
            if raw_trades not in (None, ''):
                result['total_trades'] = float(raw_trades)
            if raw_win_rate not in (None, ''):
                result['win_rate_percent'] = float(raw_win_rate)
            if raw_fees not in (None, ''):
                result['total_fees_usdt'] = float(raw_fees)
        except Exception:
            pass
        return result

    # ===== 빠른 이동 메서드들 =====


    # ===== AI 상태 관리 =====
    def _ai_ready(self) -> bool:
        """AI 매니저 준비 상태 확인"""
        try:
            manager = getattr(self, 'ai_manager', None)
            if manager is not None and bool(manager.enabled()):
                return True
            from trading.ai.ai_manager import ai_workload_route_status
            return bool(
                ai_workload_route_status(self.settings, workload="analyst")["ready"]
            )
        except Exception:
            return False

    def update_ai_status_badges(self) -> None:
        """AI READY 배지 상태 계산 및 갱신"""
        try:
            ready = self._ai_ready()
            text = "AI READY" if ready else "AI OFF"
            color = ("#1d6f42", "#0f4d2d") if ready else ("#6f1d1d", "#4d0f0f")
            # 학습 배지
            if hasattr(self, 'ai_learning_badge_label') and getattr(self, 'ai_learning_badge_label'):
                try:
                    self.ai_learning_badge_label.configure(text=text, fg_color=color)
                except Exception:
                    pass
            # 리포트 배지
            if hasattr(self, 'ai_report_badge_label') and getattr(self, 'ai_report_badge_label'):
                try:
                    self.ai_report_badge_label.configure(text=text, fg_color=color)
                except Exception:
                    pass
        except Exception:
            pass

    def _update_exchange_status(self, exchange: str, status: str) -> None:
        # 간단한 안전 업데이트 (존재할 때만)
        try:
            label = self._exchange_status_labels.get(exchange)
            if not label:
                return
            normalized = str(status or "").lower()
            if normalized == "learning_running":
                label.configure(text="학습 실행 중 · 신규 주문 차단", text_color="#38bdf8")
            elif normalized == "paper_running":
                label.configure(text="페이퍼 실행 중 · 실주문 차단", text_color="#a78bfa")
            elif normalized.startswith('run'):
                label.configure(text="진행 중", text_color="#22c55e")
            elif normalized == "learning_only":
                label.configure(text="학습 전용 · 주문 미허용", text_color="#f59e0b")
            elif normalized == "invalid_key":
                label.configure(text="API 키 확인 필요", text_color="#ef4444")
            elif normalized == "error":
                label.configure(text="시작 오류", text_color="#ef4444")
            else:
                label.configure(text="정지", text_color="#94a3b8")
        except Exception:
            pass

    def _runtime_status_for_exchange(self, exchange: str, running: bool) -> str:
        """현재 설정의 실행 모드를 거래소 카드 상태 문자열로 변환한다."""
        if not running:
            return "stopped"
        try:
            from trading.execution_mode import ExecutionMode, resolve_crypto_execution_mode

            mode = resolve_crypto_execution_mode(
                self.settings if isinstance(self.settings, dict) else {},
                str(exchange or "").strip().lower(),
            )
            return {
                ExecutionMode.LIVE: "running",
                ExecutionMode.PAPER: "paper_running",
                ExecutionMode.LEARNING: "learning_running",
            }.get(mode, "running")
        except Exception:
            return (
                "running"
                if self._is_exchange_live_order_enabled(exchange)
                else "learning_running"
            )

    def _exchange_execution_mode_value(self, exchange: str) -> str:
        """거래소별 현재 실행 모드를 UI용 문자열로 반환한다."""
        try:
            from trading.execution_mode import resolve_crypto_execution_mode

            return resolve_crypto_execution_mode(
                self.settings if isinstance(self.settings, dict) else {},
                str(exchange or "").strip().lower(),
            ).value
        except Exception:
            return "live" if self._is_exchange_live_order_enabled(exchange) else "learning"

    def _paper_position_snapshot(self, exchange: str) -> Optional[Dict[str, Any]]:
        """PAPER일 때만 엔진의 가상 포지션 저장소를 읽는다.

        `None`은 PAPER가 아닌 모드, 빈 dict는 PAPER이지만 활성
        가상 포지션이 없음을 뜻한다. 실계정 저장소와는 섞지 않는다.
        """
        ex = str(exchange or "").strip().lower()
        main_app = getattr(self, "main_app", None)
        trader = getattr(main_app, "trader", None) if main_app is not None else None
        if trader is None:
            trader = getattr(self, "trader", None)
        unified_trader = getattr(self, "unified_trader", None)
        if unified_trader is None and main_app is not None:
            unified_trader = getattr(main_app, "unified_trader", None)
        return select_paper_position_store(
            execution_mode=self._exchange_execution_mode_value(ex),
            exchange=ex,
            binance_store=(
                getattr(trader, "paper_active_positions", {})
                if trader is not None
                else {}
            ),
            unified_stores=(
                getattr(unified_trader, "paper_positions", {})
                if unified_trader is not None
                else {}
            ),
        )

    def sync_exchange_runtime_state(
        self,
        exchange: str,
        running: bool,
        status: Optional[str] = None,
    ) -> bool:
        """엔진의 실제 실행 상태를 버튼·배지·전체 제어에 한 번에 반영한다."""
        ex = str(exchange or "").strip().lower()
        if not ex:
            return False
        try:
            if not hasattr(self, "_exchange_running"):
                self._exchange_running = {}
            if not hasattr(self, "_running_exchanges"):
                self._running_exchanges = set()

            is_running = bool(running)
            self._exchange_running[ex] = is_running
            if is_running:
                self._running_exchanges.add(ex)
            else:
                self._running_exchanges.discard(ex)

            self._update_exchange_status(
                ex,
                status or self._runtime_status_for_exchange(ex, is_running),
            )
            self._update_exchange_toggle_button(ex)
            button = getattr(self, "_exchange_toggle_buttons", {}).get(ex)
            if button is not None:
                button.configure(state="normal")
            self._update_global_status_ui()
            return True
        except Exception:
            return False

    def _reconcile_exchange_control_from_engine(self, exchange: str) -> None:
        """누락된 비동기 콜백이 있어도 실제 워커 상태로 거래소 카드를 복구한다."""
        ex = str(exchange or "").strip().lower()
        if not ex:
            return
        try:
            pending = bool(getattr(self, "_exchange_action_pending", {}).get(ex, False))
            if pending:
                return
            actual = self._check_engine_exchange_status(ex)
            # 실행 여부뿐 아니라 설정에서 계산되는 LIVE/PAPER/LEARNING 배지도
            # 다시 맞춰 비동기 콜백 순서나 설정 갱신으로 생긴 표시 차이를 복구한다.
            self.sync_exchange_runtime_state(ex, actual)
        except Exception:
            pass

    def _is_exchange_live_order_enabled(self, exchange: str) -> bool:
        try:
            settings = self.settings if isinstance(self.settings, dict) else {}
            configured = settings.get('trade_enabled_exchanges', [])
            if not isinstance(configured, list):
                configured = []
            if not configured and 'trade_enabled_exchanges' not in settings:
                configured = [settings.get('selected_exchange', 'binance')]
            normalized = {
                str(item or '').strip().lower()
                for item in configured
            }
            return str(exchange or '').strip().lower() in normalized
        except Exception:
            return False

    # _register_themable, _register_text_widget, _register_button_theme 제거됨
    # 고정 스킨 사용으로 동적 테마 적용 불필요

    def _create_card_frame(
        self,
        parent,
        *,
        corner_radius: int = 16,  # 기본값을 16으로 높여 라운드 강조
        border: bool = True,
        color_key: str = 'surface',
        border_key: str = 'border'
    ):
        # 로그인 폼과 동일한 색상 스킴 적용
        frame = ctk.CTkFrame(
            parent,
            fg_color=self._color(color_key, '#0b1120'),  # 로그인 폼과 동일한 표면색
            border_color=self._color(border_key, '#1f2937'),  # 로그인과 동일한 테두리색
            border_width=2 if border else 0,
            corner_radius=corner_radius
        )
        # border 처리는 이미 border_width에서 완료
        return frame

    def _update_exchange_toggle_button(self, exchange: str) -> None:
        try:
            btn = getattr(self, '_exchange_toggle_buttons', {}).get(exchange)
            if not btn:
                return
            running = bool(self._exchange_running.get(exchange, False))
            action_label = "거래" if self._is_exchange_live_order_enabled(exchange) else "학습"
            text_primary = self._color('text_primary', '#f9fafb')
            if running:
                btn.configure(
                    text=f"⏹{exchange.upper()} {action_label} 정지",
                    fg_color=self._color('danger', '#ef4444'),
                    hover_color=self._color('hover', '#ef4444'),
                    text_color=text_primary
                )
            else:
                btn.configure(
                    text=f"▶{exchange.upper()} {action_label} 시작",
                    fg_color=self._color('success', '#10b981'),
                    hover_color=self._color('hover', '#059669'),
                    text_color=text_primary
                )
        except Exception:
            pass

    # _apply_theme_palette 제거됨 - 고정 스킨 사용으로 불필요
    # 모든 색상은 생성 시점에 FIXED_COLORS에서 직접 적용됨

    # on_theme_changed 제거됨 - 고정 스킨에서는 테마 변경 없음

    def init_ui(self):
        """UI 초기화"""
        self.logger.info("[DEBUG] init_ui 시작")

        # 창 설정 버전관리
        self.title(DASHBOARD_TITLE)
        self.logger.info("[DEBUG] 타이틀 설정 완료")

        # 창을 화면 중앙에 배치한다. 세로 900px 고정값은 거래소 탭의
        # 포지션/통계 하단을 자를 수 있어 화면이 허용하는 범위에서 980px까지 확장한다.
        self.update_idletasks()
        screen_width = int(self.winfo_screenwidth() or 1400)
        screen_height = int(self.winfo_screenheight() or 900)
        window_width = max(1280, min(1500, screen_width - 30))
        window_height = max(900, min(980, screen_height - 40))
        x = max(0, (screen_width - window_width) // 2)
        y = max(0, (screen_height - window_height) // 2)
        self.geometry(f"{window_width}x{window_height}+{x}+{y}")
        try:
            self.minsize(min(1280, window_width), min(900, window_height))
        except Exception:
            pass
        self.logger.info(
            f"[DEBUG] 창 크기/위치 설정 완료: {window_width}x{window_height}+{x}+{y}"
        )

        # 창을 최상위로 가져오기 (설정에 따라) - 부드럽게 처리
        try:
            self._apply_always_on_top_setting()
            self.logger.debug("always_on_top 설정 완료")
        except (AttributeError, Exception):
            try:
                self.attributes('-topmost', False)
                self.logger.debug("always_on_top 기본값 사용")
            except Exception as e:
                self.logger.debug(f"always_on_top 설정 실패: {e}")

        # 창 포커스를 부드럽게 설정 (강제 lift 제거)
        try:
            self.focus_set()
            self.logger.debug("포커스 설정 완료")
        except Exception:
            pass

        self.logger.info(f"대시보드 창 생성 완료 - 위치: {x}, {y}")

        # 네이티브 타이틀 아이콘은 UI 단순화를 위해 적용하지 않음

        # 메인 프레임 - 로그인처럼 corner_radius + border 적용
        # 전체 배경도 라운드가 보이고 테두리가 명확히 보이도록 설정
        self.main_frame = ctk.CTkFrame(
            self,
            fg_color="#0b1120",  # 로그인과 동일한 표면색
            border_color="#1f2937",  # 테두리 색상 추가 (로그인과 동일)
            border_width=3,  # 테두리 두께를 살짝 키워 가시성 향상
            corner_radius=16  # 전체 배경도 둥글게(라운드 강조)
        )
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.logger.info("[DEBUG] 메인 프레임 생성 완료")

        # 거래소별 탭 생성 제거됨 - 원래 구조로 복원

    # 상단 상태 바
        self.logger.info("[DEBUG] create_status_bar 호출 시작")
        self.create_status_bar()
        self.logger.info("[DEBUG] create_status_bar 완료")

        # 메인 콘텐츠 영역
        self.logger.info("[DEBUG] create_main_content 호출 시작")
        self.create_main_content()
        self.logger.info("[DEBUG] create_main_content 완료")

    # 하단 상태 바
        self.logger.info("[DEBUG] create_bottom_status 호출 시작")
        self.create_bottom_status()
        self.logger.info("[DEBUG] create_bottom_status 완료")

        # 안전 종료를 위한 프로토콜 설정
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        # 초기 사용자 라벨 즉시 업데이트 시도 (토큰 기반)
        try:
            self.thread_safe_after(150, self.update_status_info)
        except Exception:
            pass

        # 최종 확인: 로그인 창과 동일한 방식으로 스타일 적용


    def create_status_bar(self):
        """상단 상태 바 생성 - 기존 카드형 구조"""
        # 완전 하드코딩 - 로그인 모달처럼 (색상 통일)
        self.status_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color="#0b1120",  # 로그인 폼과 동일한 표면색
            border_color="#1f2937",  # 로그인과 동일한 테두리색
            border_width=2,
            corner_radius=12  # 상단 바 카드도 둥근 모서리 적용
        )
        status_frame = self.status_frame
        status_frame.pack(fill="x", pady=(0, 10))
        try:
            status_frame.grid_columnconfigure(0, weight=0)
            status_frame.grid_columnconfigure(1, weight=1)
            status_frame.grid_columnconfigure(2, weight=0)
        except Exception:
            pass

        # 좌측: 앱 제목과 사용자 정보
        left_frame = ctk.CTkFrame(status_frame, fg_color="#0b1120")
        try:
            left_frame.grid(column=0, row=0, sticky="w", padx=10, pady=10)
        except Exception:
            left_frame.pack(side="left", padx=10, pady=10)

        # 상단 타이틀은 하단 상태 표시줄로 이동하여 중앙 서비스 메뉴 공간을 확보합니다.
        # (기존 title_frame 제거)

        # 하드코딩 - 로그인과 동일한 스타일
        user_frame = ctk.CTkFrame(
            left_frame,
            fg_color="#050a13",  # 로그인 입력 필드와 동일한 배경색
            border_color="#1f2937",  # 로그인과 동일한 테두리색
            border_width=2,
            corner_radius=12
        )
        # 좌측 가장자리에서 사용자 영역을 5px 더 띄워 시각적 여유 확보
        user_frame.pack(side="left", padx=(5, 8))
        self.user_info_label = ctk.CTkLabel(
            user_frame,
            text="사용자: 로딩 중...",
            font=self._get_safe_font("body", ctk.CTkFont(size=14, weight="bold")),
            fg_color="#0b1120",
            text_color="#f9fafb"
        )
        self.user_info_label.pack(fill="both", expand=True)

        # 하드코딩 - 로그인과 동일한 스타일
        exchange_frame = ctk.CTkFrame(
            left_frame,
            fg_color="#050a13",  # 로그인 입력 필드와 동일한 배경색
            border_color="#1f2937",  # 로그인과 동일한 테두리색
            border_width=2,
            corner_radius=12,
            height=32
        )
        exchange_frame.pack(side="left", padx=(0, 8))
        self.exchange_info_label = ctk.CTkLabel(
            exchange_frame,
            text="거래소: binance",
            font=self._get_safe_font("body", ctk.CTkFont(size=14, weight="bold")),
            fg_color="#0b1120",
            text_color="#22c55e"
        )
        self.exchange_info_label.pack(fill="both", expand=True)

        replay_frame = ctk.CTkFrame(
            left_frame,
            fg_color="#050a13",
            border_color="#1f2937",
            border_width=2,
            corner_radius=12,
            height=32
        )
        replay_frame.pack(side="left", padx=(0, 8))
        self.replay_info_frame = replay_frame
        self.replay_info_label = ctk.CTkLabel(
            replay_frame,
            text="리플레이: OFF",
            font=self._get_safe_font("body", ctk.CTkFont(size=14, weight="bold")),
            fg_color="#0b1120",
            text_color="#94a3b8"
        )
        self.replay_info_label.pack(fill="both", expand=True)
        try:
            self._update_replay_status_badge()
        except Exception:
            pass

        # 중앙: 서비스 탭들
        service_tabs_frame = ctk.CTkFrame(status_frame, fg_color="#0b1120")
        try:
            service_tabs_frame.grid(column=1, row=0, sticky="w", padx=8, pady=10)  # padx 20 → 8
        except Exception:
            service_tabs_frame.pack(side="left", padx=8, pady=10)  # padx 20 → 8
        self.create_service_tabs(service_tabs_frame)

        # 우측: 버튼 그룹
        button_frame = ctk.CTkFrame(status_frame, fg_color="#0b1120")
        try:
            button_frame.grid(column=2, row=0, sticky="e", padx=10, pady=10)
        except Exception:
            button_frame.pack(side="right", padx=10, pady=10)

        # 버튼 폰트(상단 우측 액션) 크기 축소: 좌측 거래소 토글(높이 36)에 맞춤
        btn_font = self._get_safe_font("button", ctk.CTkFont(size=13, weight="bold"))

        self._start_button_font = btn_font

        # 전역 전체 시작/정지는 제거하고 거래소별 시작/정지만 제공한다.
        self.start_stop_btn = None

        # 상단 공용 액션: 메뉴얼 버튼(퀵액션 영역 혼잡 완화 목적)
        self.manual_action_btn = ctk.CTkButton(
            button_frame,
            text="메뉴얼",
            image=self._get_icon("manual", (17, 17)),
            compound="left",
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#3b82f6",
            text_color="white",
            hover_color="#2563eb",
            corner_radius=10,
            command=self._open_manual_modal
        )
        self.manual_action_btn.pack(side="left", padx=(2, 4))

        self.settings_btn = ctk.CTkButton(
            button_frame,
            text="설정",
            image=self._get_icon("settings", (17, 17)),
            compound="left",
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#3b82f6",
            text_color="white",
            hover_color="#2563eb",
            corner_radius=10,
            command=self.show_settings_dialog
        )
        self.settings_btn.pack(side="left", padx=2)

        self.exit_btn = ctk.CTkButton(
            button_frame,
            text="종료",
            image=self._get_icon("power", (17, 17)),
            compound="left",
            width=82,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#b91c1c",
            text_color="white",
            hover_color="#991b1b",
            corner_radius=10,
            command=self.on_closing,
        )
        self.exit_btn.pack(side="left", padx=(6, 2))

        # 진단 버튼 비활성화(혼동 방지). 필요 시 debug 플래그로 다시 활성화
        DEBUG_DIAGNOSTIC_BUTTON = False
        if DEBUG_DIAGNOSTIC_BUTTON:
            self._diagnostic_canvas_btn = tk.Canvas(
                button_frame,
                width=120, height=50,
                bg=self._color('background', '#0b1120'),
                highlightthickness=0
            )
            self._diagnostic_canvas_btn.pack(side="left", padx=6)
            self._draw_diagnostic_button()
            self._diagnostic_canvas_btn.bind("<Button-1>", lambda e: self._show_diagnostic_modal())

    def create_service_tabs(self, parent):
        """서비스 탭 버튼들 생성"""
        try:
            parent.configure(fg_color="#0b1120")
        except Exception:
            pass

        # 현재 활성 서비스 (기본값: 블록체인)
        self.current_service = getattr(self, 'current_service', "blockchain")

        # 완전 하드코딩
        active_fg = "#2563eb"
        active_text = "#ffffff"
        active_hover = "#1a5fd1"
        inactive_fg = "#1b304d"
        inactive_text = "#d8e5f4"
        inactive_hover = "#294767"

        # 서비스 메뉴 버튼 폰트 축소 (좌측 거래소 토글 크기에 맞춤)
        tab_font = self._get_safe_font("button", ctk.CTkFont(size=13, weight="bold"))

        def _auto_tab_w(text: str, pad: int = 28, minw: int = 120, maxw: int = 200) -> int:
            try:
                font_obj = tab_font
                if font_obj and hasattr(font_obj, 'measure'):
                    base = font_obj.measure(text)
                else:
                    raise AttributeError
            except Exception:
                base = len(text) * 10
            return max(minw, min(maxw, int(base + pad)))

        def _style(
            btn: Optional[ctk.CTkButton],
            is_active: bool,
            accent: str = active_fg,
        ) -> None:
            if not btn:
                return
            if is_active:
                btn.configure(
                    fg_color=accent,
                    text_color=active_text,
                    hover_color=self._shade_color(accent, 1.08),
                    border_width=2,
                    border_color="#93c5fd",
                    corner_radius=10,
                )
            else:
                btn.configure(
                    fg_color=inactive_fg,
                    text_color=inactive_text,
                    hover_color=inactive_hover,
                    border_width=1,
                    border_color="#3d5877",
                    corner_radius=10,
                )

        self._style_service_button = _style

        def _make_service_button(text: str, icon_name: str, command) -> ctk.CTkButton:
            # 로그인 버튼과 100% 동일
            btn = ctk.CTkButton(
                parent,
                text=text,
                image=self._get_icon(icon_name, (17, 17)),
                compound="left",
                command=command,
                width=_auto_tab_w(text),
                height=36,
                font=tab_font,
                fg_color="#3a5a7f",
                hover_color="#4a6a8f",
                text_color="#ffffff",
                border_width=1,
                border_color="#3d5877",
                corner_radius=10,
            )
            btn.pack(side="left", padx=2)
            return btn

        self.blockchain_btn = _make_service_button(
            "블록체인",
            "blockchain",
            lambda: self.switch_service("blockchain")
        )

        self.stock_btn = _make_service_button(
            "주식/증권",
            "stock",
            lambda: self._on_stock_click()
        )

        self.real_estate_btn = _make_service_button(
            "자산 통합",
            "portfolio",
            lambda: self._on_real_estate_click()
        )

        self.other_investment_btn = _make_service_button(
            "생활금융",
            "wallet",
            lambda: self._on_other_investment_click()
        )

        self.ai_analyst_btn = _make_service_button(
            "AI애널리스트",
            "analyst",
            lambda: self._on_ai_analyst_click()
        )

        # 생성 직후 현재 테마로 버튼 상태 재적용
        try:
            self._update_service_button_styles(self.current_service)
        except Exception:
            pass

    def _on_stock_click(self):
        """주식/증권 버튼 클릭 핸들러"""
        try:
            self.logger.debug("주식/증권 버튼 클릭됨")
        except Exception:
            logging.getLogger(__name__).debug("주식/증권 버튼 클릭됨")

        # 즉시 시각적 피드백 - 버튼 색상 변경 (테마 기반)
        self._update_service_button_styles("stock")

        self.switch_service("stock")

    def _on_real_estate_click(self):
        """자산 통합 버튼 클릭 핸들러"""
        try:
            self.logger.debug("자산 통합 버튼 클릭됨")
        except Exception:
            logging.getLogger(__name__).debug("자산 통합 버튼 클릭됨")

        # 즉시 시각적 피드백 - 버튼 색상 변경 (테마 기반)
        self._update_service_button_styles("real_estate")

        self.switch_service("real_estate")

    def _on_other_investment_click(self):
        """생활금융 버튼 클릭 핸들러"""
        try:
            self.logger.debug("생활금융 버튼 클릭됨")
        except Exception:
            logging.getLogger(__name__).debug("생활금융 버튼 클릭됨")

        # 즉시 시각적 피드백 - 버튼 색상 변경 (테마 기반)
        self._update_service_button_styles("other_investment")

        self.switch_service("other_investment")

    def _on_ai_analyst_click(self):
        """AI 애널리스트 버튼 클릭 핸들러"""
        try:
            self.logger.debug("AI 애널리스트 버튼 클릭됨")
        except Exception:
            logging.getLogger(__name__).debug("AI 애널리스트 버튼 클릭됨")

        # 즉시 시각적 피드백 - 버튼 색상 변경 (테마 기반)
        self._update_service_button_styles("ai_analyst")
        self.switch_service("ai_analyst")

    def _update_service_button_styles(self, active_service: str) -> None:
        """서비스 탭 버튼의 색상을 현재 테마 팔레트에 맞춰 재적용"""
        try:
            # 버튼 전용 팔레트 사용: 활성=button_primary, 비활성=button_secondary
            active_color = self._color('button_primary', '#2563eb')
            active_hover = self._color('button_primary_hover', self._shade_color(active_color, 0.9))
            inactive_color = self._color('button_secondary', '#3a5a7f')
            inactive_hover = self._color('button_secondary_hover', self._shade_color(inactive_color, 0.9))
            text_color = self._color('text_primary', '#f9fafb')
            mapping = {
                "blockchain": self.blockchain_btn,
                "stock": self.stock_btn,
                "real_estate": self.real_estate_btn,
                "other_investment": self.other_investment_btn,
                "ai_analyst": self.ai_analyst_btn,
            }
            accents = {
                "blockchain": "#2563eb",
                "stock": "#0f766e",
                "real_estate": "#6d28d9",
                "other_investment": "#b45309",
                "ai_analyst": "#0369a1",
            }
            style_fn = getattr(self, '_style_service_button', None)
            for key, btn in mapping.items():
                if not btn:
                    continue
                if style_fn:
                    style_fn(btn, key == active_service, accents.get(key, active_color))
                else:
                    if key == active_service:
                        btn.configure(fg_color=active_color, hover_color=active_hover, text_color=text_color, corner_radius=12)
                    else:
                        btn.configure(fg_color=inactive_color, hover_color=inactive_hover, text_color=text_color, corner_radius=12)
        except Exception as e:
            try:
                self.logger.debug(f"서비스 버튼 스타일 업데이트 실패: {e}")
            except Exception:
                pass





    def switch_service(self, service_name):
        """서비스 탭 전환"""
        try:
            log_windows_gui_resources(self.logger, f"service-switch-before:{service_name}")
            try:
                from log_system.log_adapter import log_event
                log_event('system', f'Service 전환 시도: {service_name}')
            except Exception:
                pass

            # 서비스 탭은 아래 destroy 경로에서 각자 정리한다. 여기서 대시보드
            # 전체 after 작업을 취소하면 백그라운드 결과를 메인 스레드로 전달하는
            # _drain_ui_call_queue까지 중단되어, 복귀한 거래소 탭의 잔고가 영구히
            # "조회 중"에 머문다.

            previous_service = str(
                getattr(self, 'current_service', 'blockchain') or 'blockchain'
            ).strip().lower()
            target_service = str(service_name or '').strip().lower()

            # 활성 서비스 버튼을 다시 누르는 것은 화면 전체 재생성 명령이 아니다.
            # 과거에는 같은 버튼 클릭마다 모든 탭/메뉴/after job을 폐기 후 재할당해
            # Windows USER menu 한도와 부분 렌더 실패를 유발했다.
            if previous_service == target_service:
                self._update_service_button_styles(target_service)
                self._apply_service_tab_policy(target_service)
                log_windows_gui_resources(self.logger, f"service-switch-reused:{target_service}")
                return

            if target_service != 'stock':
                self._stop_stock_auto_trade_loop()

            # 이전 서비스의 거래소/증권사 source 탭만 한 번 제거한다.
            # 기본 탭 정리는 마지막 정책 단계 하나에서 수행한다.
            if previous_service != target_service:
                self.clear_service_sub_tabs(previous_service)
            self.current_service = service_name

            try:
                self._refresh_ops_kpi_buttons()
            except Exception:
                pass

            # 서비스별 버튼 색상은 _update_service_button_styles에서 관리
            self._update_service_button_styles(service_name)

            self._dbg(f"버튼 색상 업데이트 완료: {service_name}")

            # 서비스별 메뉴 업데이트 (탭 콘텐츠 생성)
            self.update_service_content(service_name)

            # AI 어시스턴트가 현재 서비스 컨텍스트를 따라가도록 동기화
            try:
                aw = getattr(self, 'ai_assistant_widget', None)
                if aw is not None:
                    setter = getattr(aw, 'set_service_context', None)
                    if callable(setter):
                        setter(service_name, announce=True)
            except Exception:
                pass

            # 시장 트렌드 / AI 학습 위젯 서비스 컨텍스트 동기화
            for widget_attr in ('market_trend_widget', 'ai_learning_widget'):
                try:
                    w = getattr(self, widget_attr, None)
                    if w is not None:
                        setter = getattr(w, 'set_service_context', None)
                        if callable(setter):
                            setter(service_name)
                except Exception:
                    pass

            # AI 학습 소스 선택(거래소/증권사) UI와 실제 데이터 소스 동기화
            try:
                ai_widget = getattr(self, 'ai_learning_widget', None)
                source_menu = getattr(self, 'ai_learning_source_menu', None)
                source_var = getattr(self, 'ai_learning_source_var', None)
                source_label = getattr(self, 'ai_learning_source_label', None)

                source_options: List[str] = []
                selected_source = None
                if str(service_name).lower() == 'stock':
                    source_options = list(self.settings.get('enabled_stock_brokers', []) or [])
                    if not source_options:
                        source_options = ['kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment']
                    preferred = str(self.settings.get('selected_stock_broker', '') or '').strip().lower()
                    selected_source = preferred if preferred in source_options else source_options[0]
                    if source_label is not None and hasattr(source_label, 'configure'):
                        source_label.configure(text='증권사:')
                else:
                    source_options = list(self.settings.get('enabled_exchanges', []) or [])
                    if not source_options:
                        source_options = ['binance']
                    selected_source = source_options[0]
                    if source_label is not None and hasattr(source_label, 'configure'):
                        source_label.configure(text='거래소:')

                if source_menu is not None and hasattr(source_menu, 'configure'):
                    source_menu.configure(values=source_options)
                if source_var is not None and hasattr(source_var, 'set') and selected_source:
                    source_var.set(selected_source)
                if ai_widget is not None and hasattr(ai_widget, 'set_exchange') and selected_source:
                    ai_widget.set_exchange(selected_source)
            except Exception:
                pass

            # 현재 서비스의 하위 탭 생성 (예: 블록체인: 거래소별)
            self.create_service_sub_tabs(service_name)

            try:
                from log_system.log_adapter import log_event
                log_event('system', f'Service 전환 완료: {service_name}')
            except Exception:
                print(f"서비스 전환 완료: {service_name}")  # 디버깅용
            self.logger.info(f"서비스 전환: {service_name}")
            log_windows_gui_resources(self.logger, f"service-switch-after:{service_name}")

        except Exception as e:
            try:
                from log_system.log_adapter import log_exception
                log_exception('system', 'Service 전환 오류', exc=e)
            except Exception:
                print(f"서비스 전환 오류: {e}")  # 디버깅용
            self.logger.error(f"서비스 전환 오류: {e}")

    def _get_ops_kpi_specs_for_service(self) -> List[Tuple[str, str, str]]:
        """현재 서비스에 맞는 KPI 라벨/탭 매핑을 반환한다."""
        service = str(getattr(self, 'current_service', 'blockchain') or 'blockchain').lower()
        if service == 'stock':
            return [
                ('active', '포지션', '종목 정보'),
                ('trades', '체결', '거래 통계'),
                ('pnl', '실현손익', '거래 통계'),
                ('winrate', '승률', '시나리오 점검'),
            ]

        return [
            ('active', '포지션', '코인 정보'),
            ('trades', '거래', '거래 통계'),
            ('pnl', '손익', '거래 통계'),
            ('winrate', '승률', 'AI 어시스턴트'),
        ]

    def _navigate_to_tab_safe(self, tab_name: str) -> None:
        """탭 이동을 안전하게 수행한다."""
        try:
            if not getattr(self, 'tab_widget', None):
                return
            cast(ctk.CTkTabview, self.tab_widget).set(tab_name)
        except Exception:
            pass

    def _on_ops_kpi_click(self, metric_key: str) -> None:
        """운영 KPI 클릭 시 관련 탭으로 이동한다."""
        try:
            target = None
            for key, _label, tab_name in self._get_ops_kpi_specs_for_service():
                if key == metric_key:
                    target = tab_name
                    break

            if target == 'AI 어시스턴트':
                self._ensure_ai_assistant_tab()

            if target == '시나리오 점검':
                self._ensure_scenario_check_tab()

            if target:
                self._navigate_to_tab_safe(target)
        except Exception:
            pass

    def _refresh_ops_kpi_buttons(self) -> None:
        """서비스 전환 시 KPI 버튼 라벨/타깃을 동기화한다."""
        try:
            specs = self._get_ops_kpi_specs_for_service()
            button_map = {
                'active': getattr(self, 'ops_kpi_active_btn', None),
                'trades': getattr(self, 'ops_kpi_trades_btn', None),
                'pnl': getattr(self, 'ops_kpi_pnl_btn', None),
                'winrate': getattr(self, 'ops_kpi_winrate_btn', None),
            }

            for key, label, _tab in specs:
                btn = button_map.get(key)
                if btn is not None:
                    try:
                        btn.configure(text=f"{label}\n-")
                    except Exception:
                        pass
        except Exception:
            pass

    def _classify_ops_alert_level(
        self,
        running: int,
        total_trades: int,
        total_pnl: float,
        win_rate: float,
        active_positions: int,
    ) -> Tuple[str, str]:
        """운영 알림 심각도(level, label)를 산정한다."""
        if total_pnl < 0 or (total_trades >= 20 and win_rate < 35.0):
            return ('danger', '위험')

        if running == 0 or total_trades == 0 or active_positions >= 8:
            return ('warning', '주의')

        return ('normal', '정상')

    def update_service_content(self, service_name):
        """서비스별 콘텐츠 업데이트"""
        try:
            if service_name == "blockchain":
                # 블록체인 서비스 (현재 코인 서비스)
                self.show_blockchain_content()
            elif service_name == "stock":
                # 주식/증권 서비스
                self.show_stock_content()
            elif service_name == "real_estate":
                # 부동산 서비스
                self.show_real_estate_content()
            elif service_name == "other_investment":
                # 기타투자 서비스
                self.show_other_investment_content()
            elif service_name == "ai_analyst":
                # AI 애널리스트 서비스
                self.show_ai_analyst_content()

        except Exception as e:
            self.logger.error(f"서비스 콘텐츠 업데이트 오류: {e}")

    # ----- Tab helpers: 안전한 존재 확인/가져오기/초기화 -----
    def _tab_exists(self, name: str) -> bool:
        try:
            if not hasattr(self, 'tab_widget') or not self.tab_widget:
                return False
            tv = cast(ctk.CTkTabview, self.tab_widget)
            # 존재하면 tab()이 프레임을 반환, 없으면 예외
            _ = tv.tab(name)
            return True
        except Exception:
            return False

    def _get_or_add_tab(self, name: str):
        tv = cast(ctk.CTkTabview, self.tab_widget)
        try:
            tab_frame = tv.tab(name)
        except Exception:
            tab_frame = tv.add(name)
        # 탭 프레임은 투명 배경으로 설정하여 상위 탭뷰의 라운드/배경이 자연스럽게 드러나도록 함
        try:
            if hasattr(tab_frame, 'configure'):
                tab_frame.configure(fg_color="#0b1120")
        except Exception:
            pass
        return tab_frame

    def _apply_tabview_style(self, tv: "ctk.CTkTabview") -> None:
        """CTkTabview의 세그먼티드 버튼 스타일을 강제 적용한다.

        - 1차: Tabview.configure(segmented_button_*)로 적용 (CTk >= 5.1)
        - 2차: 내부 SegmentedButton에 직접 적용 (구버전 호환)
        - 마지막으로 현재 탭을 재선택하여 즉시 리프레시
        """
        try:
            # 색상 계산 (fallback 값을 강하게 지정) - 주변 카드(#0f172a/~#0b1120) 대비를 확실히 주는 네이비 계열
            toolbar_bg = self._color('tabbar_bg', '#0d223d')          # 탭 바 바탕: 네이비 계열로 진하게
            # 비선택 탭도 바탕에서 구분되도록 한 단계 밝은 표면색을 사용한다.
            unselected = self._color('tab_inactive', '#1b3352')
            selected = self._color('button_primary', '#2563eb')       # 선택 탭: 브랜드 블루 유지
            # 요청: 로그인 모달 버튼과 유사하게 hover 시 약간 더 밝아지도록 조정
            selected_hover = self._color('button_primary_hover', self._shade_color(selected, 1.06))
            unselected_hover = self._shade_color(unselected, 1.10)

            # 1) 정식 API 경로 (권장)
            try:
                tv.configure(
                    segmented_button_fg_color=toolbar_bg,
                    segmented_button_selected_color=selected,
                    segmented_button_unselected_color=unselected,
                    segmented_button_selected_hover_color=selected_hover,
                    segmented_button_unselected_hover_color=unselected_hover,
                    # 요청: 텍스트를 더 밝게 (비선택도 거의 흰색에 가깝게)
                    segmented_button_text_color=self._color('tab_text', '#e5edf6'),
                    segmented_button_selected_text_color=self._color('text_primary', '#ffffff'),
                    segmented_button_corner_radius=12
                )
            except Exception:
                pass

            # 2) 내부 위젯 직접 접근 (호환성용)
            try:
                sb = getattr(tv, "_segmented_button", None)
                if sb is not None and hasattr(sb, "configure"):
                    try:
                        sb.configure(
                            fg_color=toolbar_bg,
                            selected_color=selected,
                            unselected_color=unselected,
                            selected_hover_color=selected_hover,
                            unselected_hover_color=unselected_hover,
                            text_color=self._color('tab_text', '#e5edf6'),
                            selected_text_color=self._color('text_primary', '#ffffff'),
                            corner_radius=12
                        )
                    except Exception:
                        # 일부 버전에서는 색상 키 이름이 다를 수 있어 개별 시도
                        for key, val in [
                            ("fg_color", toolbar_bg),
                            ("selected_color", selected),
                            ("unselected_color", unselected),
                            ("selected_hover_color", selected_hover),
                            ("unselected_hover_color", unselected_hover),
                            ("text_color", self._color('text_secondary', "#e4e9ef")),
                            ("selected_text_color", self._color('text_primary', '#ffffff')),
                            ("corner_radius", 12),
                        ]:
                            try:
                                sb.configure(**{key: val})
                            except Exception:
                                pass
            except Exception:
                pass

            # 공용 시각 시스템으로 폰트·테두리·높이를 macOS/Windows 동일하게 마감한다.
            style_tabview(
                tv,
                accent=selected,
                bar_color=toolbar_bg,
                inactive=unselected,
                text_color=self._color('tab_text', '#e5edf6'),
                font_size=11,
                height=34,
            )

            # 3) 현재 탭 재선택으로 즉시 리프레시
            try:
                current = None
                try:
                    getter = getattr(tv, "get", None)
                    if callable(getter):
                        current = getter()
                    if not current:
                        current = getattr(tv, "_current_name", None)
                    if not current and hasattr(tv, "_name_list") and tv._name_list:  # type: ignore[attr-defined]
                        current = tv._name_list[0]
                except Exception:
                    pass
                if current:
                    tv.set(current)
                # idle 업데이트로 그리기 보장
                try:
                    tv.update_idletasks()
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            # 스타일 적용이 실패해도 UI는 계속 진행
            pass

    def _clear_tab_children(self, tab_frame: Any) -> None:
        tab_name = self._tab_name_for_frame(tab_frame)
        if tab_name:
            self._invalidate_tab_widget_reference(tab_name)
        try:
            cleanup_widget_tree(tab_frame, include_root=False)
            for child in tab_frame.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass
        except Exception:
            pass

    def _tab_name_for_frame(self, tab_frame: Any) -> Optional[str]:
        """Resolve the canonical tab owner for an in-place tree rebuild."""
        tabview = getattr(self, 'tab_widget', None)
        for name, frame in (getattr(tabview, '_tab_dict', {}) or {}).items():
            if frame is tab_frame:
                return str(name)
        return None

    def _register_tab_widget(self, tab_name: str, attribute: str, widget: Any) -> Any:
        """Cache a widget under the lifecycle of its owning dynamic tab."""
        return self._widget_ownership.register_attribute(tab_name, self, attribute, widget)

    def _register_tab_mapping_widget(
        self,
        tab_name: str,
        mapping: Dict[Any, Any],
        mapping_key: Any,
        widget: Any,
    ) -> Any:
        """Cache one mapped widget under the lifecycle of its owning tab."""
        return self._widget_ownership.register_mapping(tab_name, mapping, mapping_key, widget)

    def _invalidate_tab_widget_reference(self, tab_name: str) -> None:
        """Release every cached reference owned by a tab, including future ones."""
        self._widget_ownership.invalidate(str(tab_name))

    def _delete_dashboard_tab(self, tab_name: str) -> bool:
        """Single deletion boundary: references, callbacks, menus, then frame."""
        self._invalidate_tab_widget_reference(tab_name)
        tabview = getattr(self, 'tab_widget', None)
        if tabview is None:
            return False
        return delete_ctk_tab(tabview, tab_name)

    def clear_service_sub_tabs(self, service_name: str):
        """서비스별 하위 탭 제거 (동적 교체용)"""
        try:
            if not hasattr(self, 'tab_widget') or not self.tab_widget:
                return
            if service_name not in self.service_sub_tabs:
                return
            # 생성된 하위 탭 라벨 목록
            existing = list(self.service_sub_tabs[service_name].keys())
            for label in existing:
                try:
                    self._delete_dashboard_tab(label)
                except Exception:
                    pass
                # 내부 레퍼런스 제거
                self.service_sub_tabs[service_name].pop(label, None)
        except Exception as e:
            try:
                self.logger.warning(f"하위 탭 제거 오류: {e}")
            except Exception:
                import logging
                logging.getLogger(__name__).warning(f"하위 탭 제거 오류: {e}")


    def _get_service_protected_tabs(self, service_name: str | None = None) -> set[str]:
        """현재 서비스 기준으로 유지할 기본 탭 집합을 반환합니다."""
        try:
            from ui.service_tab_policy import get_service_protected_tabs, normalize_service_name

            current = service_name or getattr(self, 'current_service', 'blockchain')
            service = normalize_service_name(str(current))
            return set(get_service_protected_tabs(service))
        except Exception:
            return {
                "실시간 거래 로그",
                "AI 학습",
                "AI 리포트",
                "AI 어시스턴트",
            }

    def _ensure_service_info_tab(
        self,
        tab_name: str,
        title: str,
        lines: list[str],
        action_text: Optional[str] = None,
        action_cmd: Optional[Callable[[], None]] = None,
    ) -> None:
        """서비스 전용 정보 탭을 생성/갱신합니다."""
        try:
            if not hasattr(self, 'tab_widget') or self.tab_widget is None:
                return

            tab = self._get_or_add_tab(tab_name)
            self._clear_tab_children(tab)

            wrapper = ctk.CTkFrame(tab, fg_color="#0b1120")
            wrapper.pack(fill="both", expand=True, padx=12, pady=12)

            header = ctk.CTkLabel(
                wrapper,
                text=title,
                font=self._get_safe_font("title"),
                text_color=self._color('text_primary', '#f9fafb')
            )
            header.pack(anchor="w", pady=(0, 10))

            body = ctk.CTkFrame(wrapper, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
            body.pack(fill="x", padx=0, pady=0)

            for line in lines:
                label = ctk.CTkLabel(
                    body,
                    text=f"• {line}",
                    justify="left",
                    anchor="w",
                    wraplength=980,
                    font=self._get_safe_font("body"),
                    text_color=self._color('text_secondary', '#cbd5e1')
                )
                label.pack(fill="x", anchor="w", padx=12, pady=5)

            if action_text and action_cmd:
                action_button = ctk.CTkButton(
                    wrapper,
                    text=action_text,
                    command=action_cmd,
                    font=self._get_safe_font("button"),
                    height=32,
                    width=180,
                )
                action_button.pack(anchor="e", pady=(12, 0))
        except Exception as e:
            try:
                self.logger.warning(f"서비스 정보 탭 생성 실패 ({tab_name}): {e}")
            except Exception:
                pass


    def _collect_asset_insight_metrics(self) -> Dict[str, Any]:
        """현재 잔고와 거래 이력을 역할·통화별로 분리해 수집합니다."""
        from ui.asset_insight_data import (
            load_trade_history_metrics,
            normalize_current_balances,
        )

        store = getattr(self, '_asset_snapshot_store', None)
        snapshots = store.snapshot() if store is not None else {'crypto': {}, 'stock': {}}
        current = normalize_current_balances(
            snapshots.get('crypto', {}),
            snapshots.get('stock', {}),
        )
        db_path = self._get_dashboard_read_db_path()
        history = load_trade_history_metrics(db_path)

        asset_breakdown = dict(current.get('asset_breakdown', {}) or {})
        total_assets = float(current.get('total_assets', 0.0) or 0.0)
        display_currency = current.get('comparable_currency')
        pnl_by_currency = dict(history.get('pnl_by_currency', {}) or {})
        total_pnl = (
            float(pnl_by_currency.get(str(display_currency), 0.0) or 0.0)
            if display_currency
            else 0.0
        )
        concentration, concentration_level = self._calculate_asset_concentration(asset_breakdown, total_assets)
        corr_value, corr_label = self._calculate_asset_correlation(db_path)
        actions = self._build_rebalance_actions(asset_breakdown, total_assets, concentration, corr_value)

        if not current.get('has_current_data'):
            actions = ['블록체인 또는 주식/증권 계좌에서 잔고를 조회한 뒤 다시 확인하세요.']
        elif not current.get('allocation_comparable'):
            concentration = 0.0
            concentration_level = '통화 환산 필요'
            actions = [
                'KRW와 USDT는 환율 기준시각 없이 합산하지 않습니다. 통화별 잔고를 각각 점검하세요.',
                *actions,
            ][:4]

        return {
            'asset_breakdown': asset_breakdown,
            'asset_breakdown_by_currency': current.get('asset_breakdown_by_currency', {}),
            'currency_totals': current.get('currency_totals', {}),
            'display_currency': display_currency,
            'allocation_comparable': bool(current.get('allocation_comparable')),
            'has_current_data': bool(current.get('has_current_data')),
            'received_sources': list(current.get('received_sources', []) or []),
            'unvalued_assets': list(current.get('unvalued_assets', []) or []),
            'valuation_complete': bool(current.get('valuation_complete', True)),
            'total_assets': total_assets,
            'total_pnl': total_pnl,
            'pnl_by_currency': pnl_by_currency,
            'history_closed_count': int(history.get('closed_count', 0) or 0),
            'history_error': str(history.get('error', '') or ''),
            'concentration': concentration,
            'concentration_level': concentration_level,
            'corr_value': corr_value,
            'corr_label': corr_label,
            'actions': actions,
            'snapshot': self._get_saved_asset_snapshot(),
        }

    def _refresh_asset_insight_balances_async(self, owner: Any, force: bool = False) -> None:
        """자산 통합 진입 시 활성 계좌 잔고를 UI 밖에서 한 번 갱신한다."""
        now = time.time()
        if self._asset_insight_refresh_inflight:
            return
        if not force and now - float(self._asset_insight_refresh_attempt_at or 0.0) < 15.0:
            return
        self._asset_insight_refresh_inflight = True
        self._asset_insight_refresh_attempt_at = now

        def _load() -> Dict[str, Dict[str, Any]]:
            crypto: Dict[str, Any] = {}
            stock: Dict[str, Any] = {}
            manager = getattr(self, 'unified_manager', None)
            if manager is not None:
                enabled = list((self.settings or {}).get('enabled_exchanges', []) or [])
                for exchange in enabled:
                    name = str(exchange or '').strip().lower()
                    if not name:
                        continue
                    trading_type = 'spot' if name in {'upbit', 'bithumb'} else 'futures'
                    try:
                        adapter = manager.get_exchange(name, trading_type)
                        if adapter is not None and hasattr(adapter, 'get_balance'):
                            crypto[f'{name}_{trading_type}'] = adapter.get_balance()
                    except Exception as exc:
                        self.logger.debug(f'자산 통합 거래소 잔고 생략({name}): {exc}')

            for broker in list((self.settings or {}).get('enabled_stock_brokers', []) or []):
                try:
                    adapter = self._get_stock_adapter(str(broker))
                    if adapter is None:
                        continue
                    if (
                        hasattr(adapter, 'is_connected')
                        and not bool(getattr(adapter, 'is_connected', False))
                        and hasattr(adapter, 'connect')
                    ):
                        adapter.connect()
                    if hasattr(adapter, 'get_balance'):
                        stock[str(broker)] = adapter.get_balance()
                except Exception as exc:
                    self.logger.debug(f'자산 통합 증권사 잔고 생략({broker}): {exc}')
            return {'crypto': crypto, 'stock': stock}

        def _apply(result: Any) -> None:
            self._asset_insight_refresh_inflight = False
            payload = result if isinstance(result, dict) else {}
            for source, balance in dict(payload.get('crypto', {}) or {}).items():
                self._cache_asset_balance_snapshot(source, balance)
            for source, balance in dict(payload.get('stock', {}) or {}).items():
                self._cache_asset_balance_snapshot(source, balance)
            if (
                str(getattr(self, 'current_service', '')).lower() == 'real_estate'
                and (payload.get('crypto') or payload.get('stock'))
            ):
                self.show_real_estate_content()
                self._ensure_asset_allocation_diagnosis_tab()
                self._ensure_risk_briefing_full_tab()

        def _error(exc: Exception) -> None:
            self._asset_insight_refresh_inflight = False
            self.logger.warning(f'자산 통합 잔고 새로고침 실패: {exc}')

        self._run_visible_refresh_async(
            owner,
            'asset_insight_balances',
            _load,
            _apply,
            _error,
        )

    def _build_asset_correlation_service_summary(
        self,
        asset_breakdown: Dict[str, float],
        total_assets: float,
    ) -> Dict[str, Any]:
        """asset_correlation_service 기반 상관관계 요약을 구성합니다."""
        try:
            from trading.asset_correlation_service import AssetCorrelationService

            db_path = self._get_dashboard_read_db_path()
            if not db_path or not os.path.exists(db_path):
                return {'summary': '상관관계 서비스: 데이터 없음', 'top_pair': None}

            from ui.asset_insight_data import load_trade_history_metrics

            history = load_trade_history_metrics(db_path)
            by_day = dict(history.get('daily_pnl', {}) or {})
            paired_days = [
                day for day in sorted(by_day.keys())
                if 'crypto' in by_day.get(day, {}) and 'stock' in by_day.get(day, {})
            ]

            if len(paired_days) < 3:
                return {'summary': '상관관계 서비스: 표본 부족', 'top_pair': None}

            crypto_prices: List[float] = []
            stock_prices: List[float] = []
            c_level = 100.0
            s_level = 100.0
            for day in paired_days:
                row = by_day.get(day, {})
                c_level = max(1.0, c_level + float(row.get('crypto', 0.0)))
                s_level = max(1.0, s_level + float(row.get('stock', 0.0)))
                crypto_prices.append(round(c_level, 4))
                stock_prices.append(round(s_level, 4))

            price_series = {
                'CRYPTO': crypto_prices,
                'STOCK': stock_prices,
            }
            corr_service = AssetCorrelationService()
            matrix = corr_service.compute_correlation_matrix(price_series)
            high_pairs = corr_service.find_high_correlation_pairs(matrix)

            holdings = []
            if total_assets > 0:
                crypto_amount = float(asset_breakdown.get('암호화폐', 0.0) or 0.0)
                stock_amount = float(asset_breakdown.get('주식', 0.0) or 0.0)
                holdings = [
                    {'symbol': 'CRYPTO', 'weight': crypto_amount / total_assets, 'asset_class': 'crypto'},
                    {'symbol': 'STOCK', 'weight': stock_amount / total_assets, 'asset_class': 'stock'},
                ]

            rebalance = corr_service.suggest_rebalancing(holdings, matrix)
            top_pair = high_pairs[0] if high_pairs else None

            return {
                'summary': str(rebalance.get('summary', '상관관계 서비스 계산 완료')),
                'top_pair': top_pair,
            }
        except Exception:
            return {'summary': '상관관계 서비스 계산 실패', 'top_pair': None}


    def _build_risk_briefing_lines(self) -> List[str]:
        metrics = self._collect_asset_insight_metrics()
        concentration = float(metrics.get('concentration', 0.0) or 0.0)
        concentration_level = str(metrics.get('concentration_level', '데이터 부족') or '데이터 부족')
        corr_value = metrics.get('corr_value')
        corr_label = str(metrics.get('corr_label', '데이터 없음') or '데이터 없음')
        actions = list(metrics.get('actions', []) or [])
        has_current_data = bool(metrics.get('has_current_data'))
        allocation_comparable = bool(metrics.get('allocation_comparable'))

        risk_lines: List[str] = []
        if not has_current_data:
            risk_lines.append('편중 위험 미판정: 현재 계좌 잔고가 아직 수신되지 않았습니다.')
        elif not allocation_comparable:
            risk_lines.append('편중 위험 미판정: KRW와 USDT는 기준 환율 없이 합산하지 않습니다.')
        elif concentration >= 60:
            risk_lines.append('편중 위험 높음: 단일 자산군 의존도가 높아 급변동 구간 방어력이 약합니다.')
        elif concentration >= 45:
            risk_lines.append('편중 위험 중간: 비중 변화가 커지는 자산군을 주간 단위로 점검해야 합니다.')
        else:
            risk_lines.append('편중 위험 낮음: 현재 자산 분산 구조는 비교적 안정적입니다.')

        if corr_value is None:
            risk_lines.append(f'연동 위험 점검: 상관관계 계산은 아직 {corr_label} 상태입니다.')
        else:
            abs_corr = abs(float(corr_value))
            if abs_corr >= 0.7:
                risk_lines.append(f'연동 위험 높음: crypto/stock 동조화가 강합니다 ({float(corr_value):+.2f}).')
            elif abs_corr >= 0.4:
                risk_lines.append(f'연동 위험 중간: 이벤트 구간에서 동조화가 확대될 수 있습니다 ({float(corr_value):+.2f}).')
            else:
                risk_lines.append(f'연동 위험 낮음: 자산군 상관관계가 낮아 분산 효과가 유지됩니다 ({float(corr_value):+.2f}).')

        risk_lines.append(f'현재 리스크 라벨: 집중도 {concentration_level}, 상관관계 {corr_label}')

        corr_service_summary = self._build_asset_correlation_service_summary(
            dict(metrics.get('asset_breakdown', {}) or {}),
            float(metrics.get('total_assets', 0.0) or 0.0),
        )
        top_pair = corr_service_summary.get('top_pair')
        if isinstance(top_pair, dict):
            risk_lines.append(
                f"상관관계 경고쌍: {top_pair.get('symbol_a')}↔{top_pair.get('symbol_b')} ({float(top_pair.get('correlation', 0.0)):+.2f})"
            )

        if actions:
            risk_lines.append(f'권장 대응: {actions[0]}')
        return risk_lines

    def _build_life_finance_cashflow_lines(self) -> List[str]:
        profile = self._get_life_finance_profile()

        monthly_income = float(profile.get('monthly_income', 0.0) or 0.0)
        fixed_expense = float(profile.get('monthly_fixed_expense', 0.0) or 0.0)
        variable_expense = float(profile.get('monthly_variable_expense', 0.0) or 0.0)
        total_expense = fixed_expense + variable_expense
        disposable_income = monthly_income - total_expense
        savings_rate = (disposable_income / monthly_income * 100.0) if monthly_income > 0 else 0.0

        if monthly_income <= 0:
            return [
                '월 수입/지출 입력값이 없어 현금흐름을 계산할 수 없습니다.',
                '생활금융 메인 탭에서 월 수입/고정비/변동비를 입력하면 자동 계산됩니다.',
                '입력 완료 후 이 탭에서 저축 가능액과 저축률을 즉시 확인할 수 있습니다.',
            ]

        health = '양호' if disposable_income > 0 else ('주의' if disposable_income == 0 else '위험')
        return [
            f"월 수입 {monthly_income:,.0f}원, 월 지출 {total_expense:,.0f}원 (고정 {fixed_expense:,.0f} / 변동 {variable_expense:,.0f})",
            f"월 저축 가능액 {disposable_income:,.0f}원, 저축률 {savings_rate:.1f}%",
            f"현금흐름 상태: {health} (기준: 0원 초과면 양호)",
            '필요 시 생활금융 메인 탭에서 입력값을 조정해 즉시 재계산하세요.',
        ]

    def _build_life_finance_goal_lines(self) -> List[str]:
        goals_path = ''
        goals: List[Dict[str, Any]] = []

        candidate_paths: List[str] = []
        try:
            from path_utils import get_app_data_dir
            candidate_paths.append(os.path.join(get_app_data_dir(), 'life_finance_goals.json'))
        except Exception:
            pass
        candidate_paths.append(
            os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'life_finance_goals.json'))
        )

        try:
            for candidate in candidate_paths:
                if not candidate or not os.path.exists(candidate):
                    continue
                goals_path = candidate
                with open(candidate, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                if isinstance(raw, list):
                    goals = [g for g in raw if isinstance(g, dict)]
                elif isinstance(raw, dict):
                    nested = raw.get('goals', [])
                    if isinstance(nested, list):
                        goals = [g for g in nested if isinstance(g, dict)]
                if goals:
                    break
        except Exception:
            goals = []

        if not goals:
            return [
                '등록된 생활금융 목표가 없습니다.',
                '생활금융 메인 탭에서 목표를 추가하면 우선순위/진행률이 이 화면에 표시됩니다.',
                '목표 데이터 파일: data/life_finance_goals.json',
            ]

        goal_summary: Dict[str, Any] = {}
        focus_goal: Optional[Dict[str, Any]] = None
        projection_line = ''
        what_if_line = ''
        try:
            from trading.life_finance_goal_service import (
                compute_goal_summary,
                suggest_priority_order,
                simulate_goal_progress,
                goal_what_if,
            )

            goal_summary = compute_goal_summary(goals)
            ranked_goals = suggest_priority_order(goals)
            for g in ranked_goals:
                if str(g.get('status', '')).lower() == 'active':
                    focus_goal = g
                    break

            profile = self._get_life_finance_profile()
            monthly_income = float(profile.get('monthly_income', 0.0) or 0.0)
            fixed_expense = float(profile.get('monthly_fixed_expense', 0.0) or 0.0)
            variable_expense = float(profile.get('monthly_variable_expense', 0.0) or 0.0)
            monthly_savings = max(0.0, monthly_income - fixed_expense - variable_expense)

            if focus_goal and monthly_savings > 0:
                target = float(focus_goal.get('target_amount', 0.0) or 0.0)
                current = float(focus_goal.get('current_amount', 0.0) or 0.0)

                projection = simulate_goal_progress(target, current, monthly_savings, months=12)
                achieved_month = projection.get('achieved_at_month')
                if achieved_month is None:
                    projection_line = (
                        f"시뮬레이션(12개월): 월 {monthly_savings:,.0f}원 저축 시 달성 미완료, 예상 잔액 {float(projection.get('final_balance', 0.0)):,.0f}원"
                    )
                else:
                    projection_line = (
                        f"시뮬레이션(12개월): 월 {monthly_savings:,.0f}원 저축 시 {int(achieved_month) + 1}개월차 목표 달성 예상"
                    )

                scenarios = {
                    '기준': monthly_savings,
                    '+10%': monthly_savings * 1.10,
                    '+20%': monthly_savings * 1.20,
                }
                what_if = goal_what_if(target, current, scenarios, simulation_months=12)
                plus20 = dict(what_if.get('+20%', {}) or {})
                plus20_month = plus20.get('achieved_at_month')
                if plus20_month is None:
                    what_if_line = '+20% 시나리오: 12개월 내 달성 어려움'
                else:
                    what_if_line = f"+20% 시나리오: {int(plus20_month) + 1}개월차 달성 예상"
        except Exception:
            pass

        total_target = 0.0
        total_current = 0.0
        completed_count = 0

        for goal in goals:
            target = float(goal.get('target_amount', 0.0) or 0.0)
            current = float(goal.get('current_amount', 0.0) or 0.0)
            total_target += target
            total_current += current
            if target > 0 and current >= target:
                completed_count += 1

        progress_rate = (total_current / total_target * 100.0) if total_target > 0 else 0.0
        top_goals = sorted(
            goals,
            key=lambda g: float(g.get('target_amount', 0.0) or 0.0) - float(g.get('current_amount', 0.0) or 0.0),
            reverse=True,
        )[:2]

        lines = [
            f"등록 목표 {len(goals)}개, 완료 {completed_count}개, 진행률 {progress_rate:.1f}%",
            f"목표 합계 {total_target:,.0f}원 대비 현재 {total_current:,.0f}원",
        ]

        if goal_summary:
            lines[0] = (
                f"등록 목표 {int(goal_summary.get('total_goals', len(goals)))}개, "
                f"완료 {int(goal_summary.get('completed_count', completed_count))}개, "
                f"진행률 {float(goal_summary.get('overall_progress_pct', progress_rate)):.1f}%"
            )

        for goal in top_goals:
            name = str(goal.get('name', '목표') or '목표').strip()
            target = float(goal.get('target_amount', 0.0) or 0.0)
            current = float(goal.get('current_amount', 0.0) or 0.0)
            remain = max(0.0, target - current)
            lines.append(f"우선 점검: {name} 잔여 {remain:,.0f}원 (현재 {current:,.0f} / 목표 {target:,.0f})")

        if projection_line:
            lines.append(projection_line)
        if what_if_line:
            lines.append(what_if_line)

        return lines

    def _build_ai_summary_report_lines(self) -> List[str]:
        db_path = ''
        try:
            db_path = self._get_dashboard_read_db_path()
        except Exception:
            db_path = ''

        if not db_path or not os.path.exists(db_path):
            return [
                '거래 데이터베이스가 없어 AI 요약 리포트를 계산할 수 없습니다.',
                '점검 순서: 1) 자동매매 시작 2) 최소 1건 이상 포지션 진입/청산 3) 다시 AI 요약 리포트 실행',
            ]

        try:
            with sqlite3.connect(db_path) as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT COUNT(*),
                           SUM(CASE WHEN COALESCE(pnl, 0) > 0 THEN 1 ELSE 0 END),
                           SUM(COALESCE(pnl, 0)),
                           AVG(COALESCE(pnl, 0)),
                           MAX(COALESCE(pnl, 0)),
                           MIN(COALESCE(pnl, 0))
                    FROM trade_log
                    WHERE exit_time IS NOT NULL
                      AND LOWER(COALESCE(reason, '')) != 'binance_import'
                    """
                )
                row = cur.fetchone() or (0, 0, 0.0, 0.0, 0.0, 0.0)

            total_closed = int(row[0] or 0)
            win_count = int(row[1] or 0)
            total_pnl = float(row[2] or 0.0)
            avg_pnl = float(row[3] or 0.0)
            best_trade = float(row[4] or 0.0)
            worst_trade = float(row[5] or 0.0)

            if total_closed <= 0:
                return [
                    '종료된 거래가 없어 AI 요약 리포트를 생성할 수 없습니다.',
                    '포지션 청산 로그가 쌓이면 승률/손익 요약이 자동 갱신됩니다. (체결만 있고 청산이 없으면 계산 불가)',
                ]

            win_rate = (win_count / total_closed) * 100.0
            tone = '공격 억제' if total_pnl < 0 else '현 전략 유지'
            return [
                f"종료 거래 {total_closed}건, 승률 {win_rate:.1f}%",
                f"누적 손익 {total_pnl:+,.0f}원, 건당 평균 {avg_pnl:+,.0f}원",
                f"최대 이익 {best_trade:+,.0f}원 / 최대 손실 {worst_trade:+,.0f}원",
                f"AI 요약 권고: {tone}",
            ]
        except Exception:
            return [
                'AI 요약 리포트 계산 중 오류가 발생했습니다.',
                'DB 접근 가능 여부와 trade_log 스키마를 점검해 주세요.',
            ]

    def _build_ai_scenario_lines(self) -> List[str]:
        stock_auto = dict((self.settings or {}).get('stock_auto_trading', {}) or {})
        buy_th = float(stock_auto.get('buy_threshold', 0.4) or 0.4)
        sell_th = float(stock_auto.get('sell_threshold', 0.6) or 0.6)
        interval_sec = int(stock_auto.get('interval_seconds', 1800) or 1800)
        max_positions = int(stock_auto.get('max_positions', 3) or 3)
        risk_guard = bool(stock_auto.get('risk_guard_enabled', True))

        scenario_conservative = max(0.0, buy_th - 0.05)
        scenario_defensive_sell = min(1.0, sell_th - 0.05)
        interval_min = max(1, int(interval_sec / 60))

        return [
            f"현재 정책: buy {buy_th:.2f}, sell {sell_th:.2f}, 점검주기 {interval_min}분, 동시포지션 {max_positions}개",
            f"보수 시나리오: buy {scenario_conservative:.2f}로 강화하면 진입 빈도를 줄여 변동성 노출을 낮출 수 있습니다.",
            f"방어 시나리오: sell {scenario_defensive_sell:.2f}로 낮추면 손실 구간 이탈이 빨라질 수 있습니다.",
            f"리스크 가드레일: {'활성화' if risk_guard else '비활성화'} (운영 시 활성화 권장)",
        ]

    # ──────────────────────────────────────────────────────────────────────────
    # P1-1: 자산 배분 진단 탭 — 상관계수 히트맵 + 리밸런싱 시각화
    # ──────────────────────────────────────────────────────────────────────────

    def _build_asset_allocation_diagnosis_tab(self, tab) -> None:
        """자산 배분 진단 탭: 상관계수 히트맵 + 집중도 바 + 리밸런싱 제안."""
        import tkinter as tk
        self._clear_tab_children(tab)
        scroll = ctk.CTkScrollableFrame(tab, fg_color="#0b1120")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # ── 데이터 수집
        metrics = self._collect_asset_insight_metrics()
        total_assets = float(metrics.get('total_assets', 0.0) or 0.0)
        asset_breakdown = dict(metrics.get('asset_breakdown', {}) or {})
        concentration = float(metrics.get('concentration', 0.0) or 0.0)
        concentration_level = str(metrics.get('concentration_level', '데이터 없음') or '데이터 없음')
        corr_value = metrics.get('corr_value')
        corr_label = str(metrics.get('corr_label', '데이터 없음') or '데이터 없음')
        corr_service = self._build_asset_correlation_service_summary(asset_breakdown, total_assets)
        display_currency = metrics.get('display_currency')
        has_current_data = bool(metrics.get('has_current_data'))
        allocation_comparable = bool(metrics.get('allocation_comparable'))
        from ui.asset_insight_data import format_money

        # ── 섹션1: 자산군별 비중 바 차트 ──────────────────────────────
        sec1 = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
        sec1.pack(fill="x", padx=4, pady=8)
        ctk.CTkLabel(sec1, text="자산군별 비중", font=self._get_safe_font("subtitle"),
                     text_color="#fbbf24").pack(anchor="w", padx=14, pady=(10, 4))

        if not has_current_data:
            ctk.CTkLabel(sec1, text="현재 계좌 잔고가 아직 수신되지 않았습니다. 블록체인 또는 주식/증권 계좌에서 새로고침하세요.",
                         font=self._get_safe_font("body"), text_color="#6b7280").pack(anchor="w", padx=14, pady=(0, 12))
        elif not allocation_comparable:
            ctk.CTkLabel(sec1, text="KRW와 USDT 잔고가 함께 있어 환율 기준시각 없이는 비중을 계산하지 않습니다.",
                         font=self._get_safe_font("body"), text_color="#f59e0b").pack(anchor="w", padx=14, pady=(0, 12))
        else:
            colors_map = {"암호화폐": "#8b5cf6", "주식": "#06b6d4", "기타": "#84cc16"}
            bar_canvas_w = 500
            bar_canvas = tk.Canvas(sec1, width=bar_canvas_w, height=28, bg="#111827", highlightthickness=0)
            bar_canvas.pack(fill="x", padx=14, pady=(4, 2))
            x = 0
            for asset, color in colors_map.items():
                amt = float(asset_breakdown.get(asset, 0.0) or 0.0)
                pct = (amt / total_assets) if total_assets > 0 else 0.0
                w = int(pct * bar_canvas_w)
                if w > 0:
                    bar_canvas.create_rectangle(x, 4, x + w, 24, fill=color, outline="")
                x += w
            # 범례
            legend_frame = ctk.CTkFrame(sec1, fg_color="transparent")
            legend_frame.pack(anchor="w", padx=14, pady=(0, 10))
            for asset, color in colors_map.items():
                amt = float(asset_breakdown.get(asset, 0.0) or 0.0)
                pct = (amt / total_assets * 100.0) if total_assets > 0 else 0.0
                ctk.CTkLabel(legend_frame, text=f"■ {asset}: {pct:.1f}% ({format_money(amt, display_currency)})",
                             font=self._get_safe_font("small"), text_color=color).pack(side="left", padx=10)

        # ── 섹션2: 집중도(HHI) 미터 ────────────────────────────────────
        sec2 = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
        sec2.pack(fill="x", padx=4, pady=8)
        ctk.CTkLabel(sec2, text="포트폴리오 집중도 (HHI)", font=self._get_safe_font("subtitle"),
                     text_color="#fbbf24").pack(anchor="w", padx=14, pady=(10, 4))

        meter_frame = ctk.CTkFrame(sec2, fg_color="transparent")
        meter_frame.pack(anchor="w", padx=14, pady=(0, 12))
        # 0~100 스케일 바 (레드/옐로/그린)
        meter_w = 420
        seg = meter_w // 3
        meter_canvas = tk.Canvas(meter_frame, width=meter_w, height=28, bg="#111827", highlightthickness=0)
        meter_canvas.pack()
        meter_canvas.create_rectangle(0, 4, seg, 24, fill="#22c55e", outline="")
        meter_canvas.create_rectangle(seg, 4, seg * 2, 24, fill="#f59e0b", outline="")
        meter_canvas.create_rectangle(seg * 2, 4, meter_w, 24, fill="#ef4444", outline="")
        # 마커
        marker_x = int(concentration / 100.0 * meter_w)
        meter_canvas.create_polygon(marker_x, 0, marker_x - 8, 28, marker_x + 8, 28, fill="#ffffff", outline="")
        meter_canvas.create_text(marker_x, 14, text=f"{concentration:.0f}", fill="#0b1120",
                                 font=("Helvetica", 10, "bold"))
        ctk.CTkLabel(meter_frame, text=f"집중도 {concentration:.1f}/100  ({concentration_level})",
                     font=self._get_safe_font("body"),
                     text_color="#ef4444" if concentration >= 60 else "#fbbf24" if concentration >= 45 else "#22c55e"
                     ).pack(anchor="w", pady=(4, 0))

        # ── 섹션3: 상관계수 히트맵 ────────────────────────────────────
        sec3 = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
        sec3.pack(fill="x", padx=4, pady=8)
        ctk.CTkLabel(sec3, text="자산군 상관계수 히트맵", font=self._get_safe_font("subtitle"),
                     text_color="#fbbf24").pack(anchor="w", padx=14, pady=(10, 4))

        if corr_value is None:
            ctk.CTkLabel(sec3, text="표본 데이터 부족 — 거래 이력이 쌓이면 자동 계산됩니다.",
                         font=self._get_safe_font("body"), text_color="#6b7280").pack(anchor="w", padx=14, pady=(0, 12))
        else:
            # 2×2 히트맵 (CRYPTO, STOCK)
            labels = ["암호화폐", "주식"]
            corr_matrix = [[1.0, float(corr_value)], [float(corr_value), 1.0]]

            def _corr_color(v: float) -> str:
                abs_v = abs(v)
                if abs_v >= 0.7:
                    return "#ef4444"
                if abs_v >= 0.4:
                    return "#f59e0b"
                return "#22c55e"

            heat_frame = ctk.CTkFrame(sec3, fg_color="transparent")
            heat_frame.pack(anchor="w", padx=14, pady=(4, 12))
            cell_w, cell_h = 100, 40
            # 헤더 행
            ctk.CTkLabel(heat_frame, text="", width=cell_w, height=cell_h, fg_color="transparent").grid(row=0, column=0)
            for j, lbl in enumerate(labels):
                ctk.CTkLabel(heat_frame, text=lbl, width=cell_w, height=cell_h,
                             font=self._get_safe_font("small"), text_color="#9ca3af",
                             fg_color="#1a1f2e", corner_radius=6).grid(row=0, column=j + 1, padx=2, pady=2)
            for i, lbl in enumerate(labels):
                ctk.CTkLabel(heat_frame, text=lbl, width=cell_w, height=cell_h,
                             font=self._get_safe_font("small"), text_color="#9ca3af",
                             fg_color="#1a1f2e", corner_radius=6).grid(row=i + 1, column=0, padx=2, pady=2)
                for j, _ in enumerate(labels):
                    v = corr_matrix[i][j]
                    bg = _corr_color(v) if i != j else "#2563eb"
                    ctk.CTkLabel(heat_frame, text=f"{v:+.2f}", width=cell_w, height=cell_h,
                                 font=self._get_safe_font("body"), text_color="#ffffff",
                                 fg_color=bg, corner_radius=6).grid(row=i + 1, column=j + 1, padx=2, pady=2)
            # 범례
            ctk.CTkLabel(sec3, text="■ 녹색: 낮은 동조화(분산 양호)  ■ 주황: 중간  ■ 빨강: 높은 동조화(분산 취약)",
                         font=self._get_safe_font("small"), text_color="#6b7280").pack(anchor="w", padx=14, pady=(0, 8))

        # ── 섹션4: 상관관계 서비스 리밸런싱 제안 ──────────────────────
        sec4 = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
        sec4.pack(fill="x", padx=4, pady=8)
        ctk.CTkLabel(sec4, text="리밸런싱 제안", font=self._get_safe_font("subtitle"),
                     text_color="#fbbf24").pack(anchor="w", padx=14, pady=(10, 4))
        top_pair = corr_service.get('top_pair')
        summary_text = str(corr_service.get('summary', '계산 중'))
        ctk.CTkLabel(sec4, text=f"요약: {summary_text}", font=self._get_safe_font("body"),
                     text_color="#cbd5e1", wraplength=880, justify="left").pack(anchor="w", padx=14, pady=(0, 4))
        if top_pair:
            ctk.CTkLabel(sec4, text=f"경고 쌍: {top_pair.get('symbol_a')} ↔ {top_pair.get('symbol_b')} (상관계수 {float(top_pair.get('correlation', 0.0)):+.2f}) — {top_pair.get('message', '')}",
                         font=self._get_safe_font("body"), text_color="#ef4444",
                         wraplength=880, justify="left").pack(anchor="w", padx=14, pady=(0, 12))
        else:
            ctk.CTkLabel(sec4, text="고상관 경고 쌍 없음 — 현재 자산 배분 구조는 분산 관점에서 양호합니다.",
                         font=self._get_safe_font("body"), text_color="#22c55e").pack(anchor="w", padx=14, pady=(0, 12))

    # ──────────────────────────────────────────────────────────────────────────
    # P1-3: 리스크 브리핑 탭 — 시나리오별 손실액 + 심층 경고 시각화
    # ──────────────────────────────────────────────────────────────────────────

    def _build_risk_briefing_tab(self, tab) -> None:
        """리스크 브리핑 탭: 집중도/상관계수/손실 시뮬레이션 + 경고 카드."""
        import tkinter as tk
        self._clear_tab_children(tab)
        scroll = ctk.CTkScrollableFrame(tab, fg_color="#0b1120")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # ── 데이터
        metrics = self._collect_asset_insight_metrics()
        total_assets = float(metrics.get('total_assets', 0.0) or 0.0)
        asset_breakdown = dict(metrics.get('asset_breakdown', {}) or {})
        concentration = float(metrics.get('concentration', 0.0) or 0.0)
        concentration_level = str(metrics.get('concentration_level', '데이터 없음') or '데이터 없음')
        corr_value = metrics.get('corr_value')
        corr_label = str(metrics.get('corr_label', '데이터 없음') or '데이터 없음')
        actions = list(metrics.get('actions', []) or [])
        total_pnl = float(metrics.get('total_pnl', 0.0) or 0.0)
        display_currency = metrics.get('display_currency')
        has_current_data = bool(metrics.get('has_current_data'))
        allocation_comparable = bool(metrics.get('allocation_comparable'))
        from ui.asset_insight_data import format_money

        # ── 섹션1: 리스크 수준 카드 그리드 ─────────────────────────────
        sec1 = ctk.CTkFrame(scroll, fg_color="transparent")
        sec1.pack(fill="x", padx=4, pady=8)
        sec1.grid_columnconfigure((0, 1, 2), weight=1)

        def _risk_card(parent, row, col, icon, label, value, level):
            clr = "#ef4444" if level == "danger" else "#f59e0b" if level == "warning" else "#22c55e"
            card = ctk.CTkFrame(parent, fg_color="#1f2937", corner_radius=12)
            card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=28)).pack(pady=(10, 2))
            ctk.CTkLabel(card, text=label, font=self._get_safe_font("small"),
                         text_color="#9ca3af").pack()
            ctk.CTkLabel(card, text=value, font=self._get_safe_font("subtitle"),
                         text_color=clr).pack(pady=(0, 10))

        conc_level_tag = "danger" if concentration >= 60 else "warning" if concentration >= 45 else "safe"
        corr_abs = abs(float(corr_value)) if corr_value is not None else 0.0
        corr_level_tag = "danger" if corr_abs >= 0.7 else "warning" if corr_abs >= 0.4 else "safe"
        pnl_level_tag = "danger" if total_assets > 0 and total_pnl < -total_assets * 0.1 else "warning" if total_pnl < 0 else "safe"

        _risk_card(sec1, 0, 0, "", "집중도", f"{concentration:.0f}/100\n({concentration_level})", conc_level_tag)
        _risk_card(sec1, 0, 1, "", "상관계수",
                   f"{float(corr_value):+.2f}\n({corr_label})" if corr_value is not None else "N/A\n(데이터 없음)", corr_level_tag)
        pnl_text = format_money(abs(total_pnl), display_currency)
        pnl_text = ("+" if total_pnl >= 0 else "-") + pnl_text
        _risk_card(sec1, 0, 2, "", "실현 손익(가져오기 제외)", pnl_text, pnl_level_tag)

        # ── 섹션2: 시나리오별 손실액 추정 테이블 ────────────────────────
        sec2 = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
        sec2.pack(fill="x", padx=4, pady=8)
        ctk.CTkLabel(sec2, text="시나리오별 손실액 추정", font=self._get_safe_font("subtitle"),
                     text_color="#fbbf24").pack(anchor="w", padx=14, pady=(10, 4))

        if not has_current_data:
            ctk.CTkLabel(sec2, text="현재 잔고가 수신되지 않아 손실액을 계산하지 않습니다.",
                         font=self._get_safe_font("body"), text_color="#6b7280").pack(anchor="w", padx=14, pady=(0, 12))
        elif not allocation_comparable:
            ctk.CTkLabel(sec2, text="KRW와 USDT를 환율 없이 합산하지 않으므로 통합 손실액 추정을 보류합니다.",
                         font=self._get_safe_font("body"), text_color="#f59e0b").pack(anchor="w", padx=14, pady=(0, 12))
        else:
            scenarios = [
                ("하락 -5%", 0.05),
                ("하락 -10%", 0.10),
                ("하락 -20%", 0.20),
                ("하락 -30%", 0.30),
                ("하락 -50%", 0.50),
            ]
            tbl_frame = ctk.CTkFrame(sec2, fg_color="transparent")
            tbl_frame.pack(fill="x", padx=14, pady=(0, 12))
            headers = ["시나리오", "전체 손실액", "암호화폐 손실", "주식 손실", "최대 집중 리스크"]
            for j, h in enumerate(headers):
                ctk.CTkLabel(tbl_frame, text=h, font=self._get_safe_font("small"),
                             text_color="#9ca3af", width=140).grid(row=0, column=j, padx=4, pady=3, sticky="w")
            crypto_amt = float(asset_breakdown.get('암호화폐', 0.0) or 0.0)
            stock_amt = float(asset_breakdown.get('주식', 0.0) or 0.0)
            for i, (label, rate) in enumerate(scenarios):
                total_loss = total_assets * rate
                crypto_loss = crypto_amt * rate
                stock_loss = stock_amt * rate
                dominant = max(crypto_amt, stock_amt)
                max_loss = dominant * rate
                color = "#ef4444" if rate >= 0.30 else "#f59e0b" if rate >= 0.10 else "#cbd5e1"
                vals = [label, f"-{format_money(total_loss, display_currency)}", f"-{format_money(crypto_loss, display_currency)}",
                        f"-{format_money(stock_loss, display_currency)}", f"-{format_money(max_loss, display_currency)}"]
                for j, val in enumerate(vals):
                    ctk.CTkLabel(tbl_frame, text=val, font=self._get_safe_font("small"),
                                 text_color=color, width=140).grid(row=i + 1, column=j, padx=4, pady=2, sticky="w")

        # ── 섹션3: 경고 & 대응 액션 ─────────────────────────────────────
        sec3 = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
        sec3.pack(fill="x", padx=4, pady=8)
        ctk.CTkLabel(sec3, text="리스크 경고 및 대응 방향", font=self._get_safe_font("subtitle"),
                     text_color="#fbbf24").pack(anchor="w", padx=14, pady=(10, 4))

        # 경고 텍스트 생성
        risk_lines = self._build_risk_briefing_lines()
        for line in risk_lines:
            bg = "#450a0a" if "높음" in line or "위험" in line else "#1c1917"
            clr = "#fca5a5" if "높음" in line or "위험" in line else "#cbd5e1"
            ctk.CTkLabel(sec3, text=f"• {line}", font=self._get_safe_font("body"),
                         text_color=clr, fg_color=bg, corner_radius=8,
                         wraplength=900, justify="left").pack(fill="x", anchor="w", padx=12, pady=3)

        if actions:
            ctk.CTkLabel(sec3, text="", height=4).pack()
            ctk.CTkLabel(sec3, text="즉시 권장 액션:", font=self._get_safe_font("body"),
                         text_color="#60a5fa").pack(anchor="w", padx=14, pady=(0, 2))
            for act in actions[:3]:
                ctk.CTkLabel(sec3, text=f"  → {act}", font=self._get_safe_font("body"),
                             text_color="#93c5fd", wraplength=900, justify="left").pack(anchor="w", padx=14, pady=2)
        ctk.CTkLabel(sec3, text="").pack(pady=4)

    # ──────────────────────────────────────────────────────────────────────────
    # P1-2: 시나리오 점검 탭 — 백테스트 엔진 + 3개 시나리오 비교
    # ──────────────────────────────────────────────────────────────────────────

    def _build_scenario_check_tab(self, tab) -> None:
        """시나리오 점검 탭: DB 거래 데이터 기반 시나리오별 수익률 백테스트."""
        self._clear_tab_children(tab)
        scroll = ctk.CTkScrollableFrame(tab, fg_color="#0b1120")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        current_service = str(getattr(self, 'current_service', 'blockchain') or 'blockchain').strip().lower()
        if not hasattr(self, '_scenario_asset_filter_var'):
            default_filter = '전체'
            if current_service == 'stock':
                default_filter = '주식'
            elif current_service == 'blockchain':
                default_filter = '코인'
            self._scenario_asset_filter_var = tk.StringVar(value=default_filter)

        asset_filter_label = str(self._scenario_asset_filter_var.get() or '전체').strip()
        asset_type_filter = {'전체': None, '코인': 'crypto', '주식': 'stock'}.get(asset_filter_label, None)

        # ── 현재 정책값
        stock_auto = dict((self.settings or {}).get('stock_auto_trading', {}) or {})
        buy_th = float(stock_auto.get('buy_threshold', 0.4) or 0.4)
        sell_th = float(stock_auto.get('sell_threshold', 0.6) or 0.6)
        interval_sec = int(stock_auto.get('interval_seconds', 1800) or 1800)
        max_positions = int(stock_auto.get('max_positions', 3) or 3)
        risk_guard = bool(stock_auto.get('risk_guard_enabled', True))
        interval_min = max(1, interval_sec // 60)

        # ── 헤더
        header = ctk.CTkFrame(scroll, fg_color="#0f1f3d", corner_radius=12)
        header.pack(fill="x", padx=4, pady=(4, 8))
        ctk.CTkLabel(header, text="자동매매 시나리오 점검",
                     font=self._get_safe_font("title"), text_color="#60a5fa").pack(anchor="w", padx=14, pady=(10, 2))
        ctk.CTkLabel(header, text="기준: stock_auto_trading 정책값 + 선택 자산군의 종료 거래 데이터를 사용해 보수/기준/공격 3가지 시나리오를 시뮬레이션합니다.",
                     font=self._get_safe_font("body"), text_color="#9ca3af").pack(anchor="w", padx=14, pady=(0, 10))

        basis_frame = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
        basis_frame.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(
            basis_frame,
            text="기준 안내: 정책은 stock_auto_trading(주식 자동매매 정책) 값을 읽고, 시뮬레이션 데이터는 아래 선택한 자산군의 종료 거래를 사용합니다.",
            font=self._get_safe_font("small"),
            text_color="#cbd5e1",
            justify="left",
            wraplength=980,
        ).pack(anchor="w", padx=14, pady=(10, 6))

        basis_filter_row = ctk.CTkFrame(basis_frame, fg_color="transparent")
        basis_filter_row.pack(fill="x", padx=14, pady=(0, 10))
        ctk.CTkLabel(
            basis_filter_row,
            text="데이터 기준",
            font=self._get_safe_font("small"),
            text_color="#9ca3af",
        ).pack(side="left", padx=(0, 8))

        ctk.CTkOptionMenu(
            basis_filter_row,
            values=["전체", "코인", "주식"],
            variable=self._scenario_asset_filter_var,
            width=120,
            command=lambda _v: self._ensure_scenario_check_tab(),
        ).pack(side="left")

        ctk.CTkLabel(
            basis_filter_row,
            text=f"현재 선택: {asset_filter_label}",
            font=self._get_safe_font("small"),
            text_color="#93c5fd",
        ).pack(side="left", padx=(12, 0))

        # ── 현재 정책 표시
        policy_frame = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
        policy_frame.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(policy_frame, text="현재 자동매매 정책",
                     font=self._get_safe_font("subtitle"), text_color="#fbbf24").pack(anchor="w", padx=14, pady=(10, 4))
        policy_grid = ctk.CTkFrame(policy_frame, fg_color="transparent")
        policy_grid.pack(fill="x", padx=14, pady=(0, 10))
        policy_items = [
            ("매수 임계값", f"{buy_th:.2f}"),
            ("매도 임계값", f"{sell_th:.2f}"),
            ("점검 주기", f"{interval_min}분"),
            ("최대 포지션", f"{max_positions}개"),
            ("리스크 가드레일", "활성화" if risk_guard else "비활성화"),
        ]
        for j, (k, v) in enumerate(policy_items):
            ctk.CTkLabel(policy_grid, text=k, font=self._get_safe_font("small"),
                         text_color="#9ca3af").grid(row=0, column=j, padx=12, pady=2)
            ctk.CTkLabel(policy_grid, text=v, font=self._get_safe_font("subtitle"),
                         text_color="#f9fafb").grid(row=1, column=j, padx=12, pady=2)

        # ── 백테스트 엔진: 공통 스키마 어댑터에서 거래 데이터 로드
        db_path = ""
        trades: list = []
        try:
            db_path = self._get_dashboard_read_db_path()
        except Exception:
            pass

        if db_path and os.path.exists(db_path):
            from ui.asset_insight_data import load_closed_trade_records

            loaded_trades = load_closed_trade_records(
                db_path,
                asset_class=asset_type_filter,
                limit=200,
            )
            trades = [
                (
                    float(row.get("pnl", 0.0) or 0.0),
                    float(row.get("notional", 0.0) or 0.0),
                    str(row.get("timestamp", "") or ""),
                    str(row.get("asset_class", "other") or "other"),
                )
                for row in (loaded_trades.get("records", []) or [])
            ]
            if loaded_trades.get("error"):
                self.logger.warning("시나리오 거래 데이터 어댑터: %s", loaded_trades["error"])

        # ── 3가지 시나리오 정의 (현재 정책 기준)
        scenarios_def = [
            {
                "name": "보수적",
                "desc": f"매수 임계값 {max(0.0, buy_th - 0.10):.2f} | 포지션 {max(1, max_positions - 1)}개 | 리스크 가드 ON",
                "buy_adj": -0.10, "sell_adj": 0.0, "pos_ratio": 0.7, "color": "#3b82f6",
            },
            {
                "name": "현재 정책",
                "desc": f"매수 임계값 {buy_th:.2f} | 포지션 {max_positions}개 | 리스크 가드 {'ON' if risk_guard else 'OFF'}",
                "buy_adj": 0.0, "sell_adj": 0.0, "pos_ratio": 1.0, "color": "#22c55e",
            },
            {
                "name": "공격적",
                "desc": f"매수 임계값 {min(1.0, buy_th + 0.10):.2f} | 포지션 {max_positions + 1}개 | 리스크 가드 OFF",
                "buy_adj": 0.10, "sell_adj": 0.0, "pos_ratio": 1.3, "color": "#ef4444",
            },
        ]

        def _simulate(pos_ratio: float) -> dict:
            """간이 시뮬레이션: 실제 거래 기반 포지션 비율 보정."""
            if not trades:
                return {"total": 0, "wins": 0, "win_rate": 0.0, "total_pnl": 0.0,
                        "avg_pnl": 0.0, "max_dd": 0.0}
            total = len(trades)
            total_pnl_sim = sum(pnl * pos_ratio for pnl, _, _, _ in trades)
            wins = sum(1 for pnl, _, _, _ in trades if pnl * pos_ratio > 0)
            avg_pnl = total_pnl_sim / total if total > 0 else 0.0
            # 최대 드로우다운 계산
            cumulative = 0.0
            peak = 0.0
            max_dd = 0.0
            for pnl, _, _, _ in trades[::-1]:
                cumulative += pnl * pos_ratio
                if cumulative > peak:
                    peak = cumulative
                dd = peak - cumulative
                if dd > max_dd:
                    max_dd = dd
            return {
                "total": total, "wins": wins,
                "win_rate": (wins / total * 100.0) if total > 0 else 0.0,
                "total_pnl": total_pnl_sim, "avg_pnl": avg_pnl, "max_dd": max_dd,
            }

        # ── 시나리오 비교 테이블
        tbl_sec = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
        tbl_sec.pack(fill="x", padx=4, pady=8)
        ctk.CTkLabel(tbl_sec, text="시나리오별 시뮬레이션 결과",
                     font=self._get_safe_font("subtitle"), text_color="#fbbf24").pack(anchor="w", padx=14, pady=(10, 4))

        if not trades:
            filter_hint = "전체 종료 거래" if asset_type_filter is None else ("코인 종료 거래" if asset_type_filter == 'crypto' else "주식 종료 거래")
            ctk.CTkLabel(tbl_sec,
                         text=(
                             "종료된 거래 데이터가 없습니다.\n"
                             f"시나리오 점검은 {filter_hint}를 기준으로 계산됩니다.\n"
                             "자동매매 실행 → 최소 1건 이상 청산 후 다시 확인하세요."
                         ),
                         font=self._get_safe_font("body"), text_color="#6b7280").pack(anchor="w", padx=14, pady=(0, 12))
        else:
            tbl_grid = ctk.CTkFrame(tbl_sec, fg_color="transparent")
            tbl_grid.pack(fill="x", padx=14, pady=(0, 12))
            headers = ["시나리오", "기준 거래수", "승률", "누적 손익", "건당 평균", "최대 드로우다운"]
            for j, h in enumerate(headers):
                ctk.CTkLabel(tbl_grid, text=h, font=self._get_safe_font("small"),
                             text_color="#9ca3af", width=120).grid(row=0, column=j, padx=4, pady=3)
            for i, sc in enumerate(scenarios_def):
                result = _simulate(sc["pos_ratio"])
                vals = [
                    sc["name"],
                    f"{result['total']}건",
                    f"{result['win_rate']:.1f}%",
                    f"{result['total_pnl']:+,.0f}원",
                    f"{result['avg_pnl']:+,.0f}원",
                    f"-{result['max_dd']:,.0f}원",
                ]
                for j, val in enumerate(vals):
                    ctk.CTkLabel(tbl_grid, text=val, font=self._get_safe_font("small"),
                                 text_color=sc["color"], width=120
                                 ).grid(row=i + 1, column=j, padx=4, pady=3)
            ctk.CTkLabel(tbl_sec,
                         text=(
                             "※ 보수 시나리오는 포지션 비율 70%, 공격 시나리오는 130%를 적용한 추정값입니다. "
                             f"(데이터 기준: {asset_filter_label})"
                         ),
                         font=self._get_safe_font("small"), text_color="#6b7280").pack(anchor="w", padx=14, pady=(0, 4))

        # ── 기간별 요약 (최근 1개월)
        if trades:
            from datetime import datetime as _dt
            recent = [t for t in trades if t[2][:7] >= (_dt.now().strftime("%Y-%m")[:4] + "-" + _dt.now().strftime("%m"))]
            recent_pnl = sum(pnl for pnl, _, _, _ in recent)
            recent_wins = sum(1 for pnl, _, _, _ in recent if pnl > 0)
            period_sec = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
            period_sec.pack(fill="x", padx=4, pady=8)
            ctk.CTkLabel(period_sec, text="이번 달 성과 요약",
                         font=self._get_safe_font("subtitle"), text_color="#fbbf24").pack(anchor="w", padx=14, pady=(10, 4))
            if recent:
                ctk.CTkLabel(period_sec,
                             text=f"거래수: {len(recent)}건 | 승률: {recent_wins / len(recent) * 100:.1f}% | 손익: {recent_pnl:+,.0f}원",
                             font=self._get_safe_font("body"), text_color="#cbd5e1").pack(anchor="w", padx=14, pady=(0, 12))
            else:
                ctk.CTkLabel(period_sec, text="이번 달 종료 거래 없음",
                             font=self._get_safe_font("body"), text_color="#6b7280").pack(anchor="w", padx=14, pady=(0, 12))

        # ── AI 시나리오 요청 버튼
        ctk.CTkButton(
            scroll, text="AI에 시나리오 심층 분석 요청",
            command=lambda: self._request_ai_analyst("risk"),
            height=36, font=self._get_safe_font("button"),
            fg_color="#2563eb", hover_color="#1d4ed8",
        ).pack(anchor="e", padx=8, pady=8)

    # ──────────────────────────────────────────────────────────────────────────
    # P2-1: 보안 경고 탭 — fraud_detection_service 결과 표시
    # ──────────────────────────────────────────────────────────────────────────

    def _build_fraud_detection_tab(self, tab) -> None:
        """보안 경고 탭: fraud_detection_service 활용 이상 패턴 탐지."""
        self._clear_tab_children(tab)
        scroll = ctk.CTkScrollableFrame(tab, fg_color="#0b1120")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # ── 헤더
        header = ctk.CTkFrame(scroll, fg_color="#1a0a0a", corner_radius=12)
        header.pack(fill="x", padx=4, pady=(4, 8))
        ctk.CTkLabel(header, text="금융 보안 경고 센터",
                     font=self._get_safe_font("title"), text_color="#f87171").pack(anchor="w", padx=14, pady=(10, 2))
        ctk.CTkLabel(header, text="보이스피싱·스미싱·이상거래·약탈적 대출 패턴을 자동 감지합니다. 모든 결과는 참고용이며 오탐이 있을 수 있습니다.",
                     font=self._get_safe_font("body"), text_color="#9ca3af",
                     wraplength=900, justify="left").pack(anchor="w", padx=14, pady=(0, 10))

        # ── 공통 스키마 어댑터에서 거래 이력 로드 + 이상 탐지
        alerts: list = []
        try:
            from trading.fraud_detection_service import detect_abnormal_transactions, TransactionRecord, compute_fraud_risk_summary
            from datetime import date as _date
            db_path = self._get_dashboard_read_db_path()
            tx_records: list = []
            if db_path and os.path.exists(db_path):
                from ui.asset_insight_data import load_closed_trade_records

                loaded_trades = load_closed_trade_records(db_path, limit=100)
                for row in (loaded_trades.get("records", []) or []):
                    try:
                        tx_date = _date.fromisoformat(str(row.get("day", "")))
                    except Exception:
                        tx_date = _date.today()
                    tx_records.append(TransactionRecord(
                        amount=float(row.get("notional", 0.0) or 0.0),
                        tx_date=tx_date,
                        counterpart=str(row.get("symbol", "") or ""),
                        category=str(row.get("asset_class", "trading") or "trading"),
                    ))
            if tx_records:
                alert = detect_abnormal_transactions(tx_records)
                alerts.append(alert)
        except Exception:
            pass

        # ── 리스크 요약 표시
        risk_summary: dict = {}
        if alerts:
            try:
                from trading.fraud_detection_service import compute_fraud_risk_summary
                risk_summary = compute_fraud_risk_summary(alerts)
            except Exception:
                pass

        summary_sec = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
        summary_sec.pack(fill="x", padx=4, pady=8)
        ctk.CTkLabel(summary_sec, text="종합 리스크 점수",
                     font=self._get_safe_font("subtitle"), text_color="#fbbf24").pack(anchor="w", padx=14, pady=(10, 4))

        if risk_summary:
            overall = float(risk_summary.get('overall_risk_score', 0.0) or 0.0)
            risk_level = str(risk_summary.get('risk_level', 'low') or 'low')
            level_color = {"low": "#22c55e", "medium": "#f59e0b", "high": "#ef4444", "critical": "#dc2626"}.get(risk_level, "#9ca3af")
            ctk.CTkLabel(summary_sec,
                         text=f"종합 리스크 점수: {overall:.2f}/1.0 ({risk_level.upper()})",
                         font=self._get_safe_font("subtitle"), text_color=level_color).pack(anchor="w", padx=14, pady=(0, 4))
            actions_list = list(risk_summary.get('recommended_actions', []) or [])
            for act in actions_list[:3]:
                ctk.CTkLabel(summary_sec, text=f"→ {act}", font=self._get_safe_font("body"),
                             text_color="#cbd5e1", wraplength=880, justify="left").pack(anchor="w", padx=14, pady=2)
        else:
            ctk.CTkLabel(summary_sec, text="현재 거래 이력에서 이상 패턴이 감지되지 않았습니다.",
                         font=self._get_safe_font("body"), text_color="#22c55e").pack(anchor="w", padx=14, pady=(0, 12))

        # ── 탐지된 경고 목록
        alert_sec = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
        alert_sec.pack(fill="x", padx=4, pady=8)
        ctk.CTkLabel(alert_sec, text="탐지된 경고 목록",
                     font=self._get_safe_font("subtitle"), text_color="#fbbf24").pack(anchor="w", padx=14, pady=(10, 4))

        if not alerts:
            ctk.CTkLabel(alert_sec, text="탐지된 경고 없음",
                         font=self._get_safe_font("body"), text_color="#6b7280").pack(anchor="w", padx=14, pady=(0, 12))
        else:
            for alert in alerts:
                level = getattr(alert, 'risk_level', 'low')
                score = float(getattr(alert, 'score', 0.0) or 0.0)
                desc = str(getattr(alert, 'description', '') or '')
                patterns = list(getattr(alert, 'matched_patterns', []) or [])
                clr = {"low": "#22c55e", "medium": "#f59e0b", "high": "#ef4444", "critical": "#dc2626"}.get(level, "#9ca3af")
                bg = {"low": "#14532d", "medium": "#451a03", "high": "#450a0a", "critical": "#3f0000"}.get(level, "#1f2937")
                card = ctk.CTkFrame(alert_sec, fg_color=bg, corner_radius=8)
                card.pack(fill="x", padx=10, pady=4)
                ctk.CTkLabel(card, text=f"[{level.upper()}] 점수 {score:.2f} — {desc}",
                             font=self._get_safe_font("body"), text_color=clr,
                             wraplength=860, justify="left").pack(anchor="w", padx=10, pady=4)
                if patterns:
                    ctk.CTkLabel(card, text=f"감지 패턴: {', '.join(patterns[:5])}",
                                 font=self._get_safe_font("small"), text_color="#9ca3af").pack(anchor="w", padx=10, pady=(0, 6))
        ctk.CTkLabel(alert_sec, text="").pack(pady=2)

        # ── 자가 진단 안내
        guide_sec = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
        guide_sec.pack(fill="x", padx=4, pady=8)
        ctk.CTkLabel(guide_sec, text="보이스피싱·스미싱 자가 진단",
                     font=self._get_safe_font("subtitle"), text_color="#fbbf24").pack(anchor="w", padx=14, pady=(10, 4))
        guide_lines = [
            "■ 기관(검찰·금감원·국세청)이 전화로 계좌 이체를 요구하면 즉시 끊으세요.",
            "■ URL 링크가 포함된 문자에서 앱 설치 요청은 스미싱 의심입니다.",
            "■ '안전계좌'·'보호계좌'로 이체 요청은 100% 보이스피싱입니다.",
            "■ 모르는 번호로 수신된 소액결제·해외송금 문자는 즉시 통신사에 신고하세요.",
            "■ 의심 시: 금융감독원 1332 / 경찰 112 즉시 신고",
        ]
        for line in guide_lines:
            ctk.CTkLabel(guide_sec, text=line, font=self._get_safe_font("body"),
                         text_color="#cbd5e1", wraplength=900, justify="left").pack(anchor="w", padx=14, pady=3)
        ctk.CTkLabel(guide_sec, text="").pack(pady=4)

    # ──────────────────────────────────────────────────────────────────────────
    # P2-2: 세금 계산 탭 — tax_calculation_service 결과 표시
    # ──────────────────────────────────────────────────────────────────────────

    def _build_tax_calculation_tab(self, tab) -> None:
        """세금 계산 탭: 연말정산·금투세·ISA 절세 비교."""
        self._clear_tab_children(tab)
        scroll = ctk.CTkScrollableFrame(tab, fg_color="#0b1120")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # ── 헤더
        header = ctk.CTkFrame(scroll, fg_color="#0f2a1a", corner_radius=12)
        header.pack(fill="x", padx=4, pady=(4, 8))
        ctk.CTkLabel(header, text="세금 계산 & 절세 시뮬레이터",
                     font=self._get_safe_font("title"), text_color="#4ade80").pack(anchor="w", padx=14, pady=(10, 2))
        ctk.CTkLabel(header, text="2026년 기준. 결과는 참고용이며 정확한 납세액은 홈택스 또는 세무사를 통해 확인하세요.",
                     font=self._get_safe_font("body"), text_color="#9ca3af").pack(anchor="w", padx=14, pady=(0, 10))

        # ── 입력 패널
        input_frame = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
        input_frame.pack(fill="x", padx=4, pady=8)
        ctk.CTkLabel(input_frame, text="기본 정보 입력",
                     font=self._get_safe_font("subtitle"), text_color="#fbbf24").pack(anchor="w", padx=14, pady=(10, 4))

        inp_grid = ctk.CTkFrame(input_frame, fg_color="transparent")
        inp_grid.pack(fill="x", padx=14, pady=(0, 10))

        entries: dict = {}
        fields = [
            ("연간 급여 (원)", "annual_salary", "50000000"),
            ("신용카드 사용액 (원)", "credit_card", "12000000"),
            ("체크카드 사용액 (원)", "debit_card", "3000000"),
            ("의료비 (원)", "medical", "500000"),
            ("교육비 (원)", "education", "0"),
            ("기부금 (원)", "donation", "0"),
            ("금융소득 (원)", "financial_income", "0"),
            ("주식 차익 (원)", "stock_profit", "0"),
        ]
        for i, (label, key, default) in enumerate(fields):
            row = i // 2
            col = (i % 2) * 2
            ctk.CTkLabel(inp_grid, text=label, font=self._get_safe_font("small"),
                         text_color="#9ca3af").grid(row=row, column=col, padx=(8, 4), pady=4, sticky="w")
            entry = ctk.CTkEntry(inp_grid, width=140, placeholder_text=default)
            entry.insert(0, default)
            entry.grid(row=row, column=col + 1, padx=(0, 16), pady=4, sticky="w")
            entries[key] = entry

        result_frame = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
        result_frame.pack(fill="x", padx=4, pady=8)

        def _run_tax_calc():
            try:
                from trading.tax_calculation_service import (
                    calc_year_end_tax_settlement,
                    check_financial_income_comprehensive_tax,
                    calc_financial_investment_tax,
                    compare_tax_saving_accounts,
                    generate_tax_optimization_summary,
                )
                def _v(key: str) -> float:
                    try:
                        return float(entries[key].get() or "0")
                    except Exception:
                        return 0.0

                for w in result_frame.winfo_children():
                    w.destroy()
                ctk.CTkLabel(result_frame, text="계산 결과",
                             font=self._get_safe_font("subtitle"), text_color="#fbbf24").pack(anchor="w", padx=14, pady=(10, 4))

                # 1. 연말정산
                settlement = calc_year_end_tax_settlement(
                    annual_salary=_v("annual_salary"),
                    credit_card_used=_v("credit_card"),
                    debit_card_used=_v("debit_card"),
                    medical_expense=_v("medical"),
                    education_expense=_v("education"),
                    donation_amount=_v("donation"),
                )
                sec_a = ctk.CTkFrame(result_frame, fg_color="#0f2a1a", corner_radius=8)
                sec_a.pack(fill="x", padx=10, pady=4)
                ctk.CTkLabel(sec_a, text="근로소득 연말정산",
                             font=self._get_safe_font("body"), text_color="#4ade80").pack(anchor="w", padx=12, pady=(8, 2))
                for k, v in [
                    ("산출 세액", f"{float(settlement.get('tax_calculated', 0)):,.0f}원"),
                    ("총 세액공제", f"{float(settlement.get('total_tax_credit', 0)):,.0f}원"),
                    ("예상 납부 세액", f"{float(settlement.get('final_tax', 0)):,.0f}원"),
                    ("실효 세율", f"{float(settlement.get('effective_rate', 0)) * 100:.2f}%"),
                ]:
                    ctk.CTkLabel(sec_a, text=f"{k}: {v}",
                                 font=self._get_safe_font("body"), text_color="#cbd5e1").pack(anchor="w", padx=20, pady=1)
                ctk.CTkLabel(sec_a, text="").pack(pady=2)

                # 2. 금융투자소득세
                fin_income = _v("financial_income")
                stock_profit = _v("stock_profit")
                if stock_profit > 0 or fin_income > 0:
                    fit_result = calc_financial_investment_tax(annual_profit=stock_profit)
                    sec_b = ctk.CTkFrame(result_frame, fg_color="#0a1a2a", corner_radius=8)
                    sec_b.pack(fill="x", padx=10, pady=4)
                    ctk.CTkLabel(sec_b, text="금융투자소득세 (금투세)",
                                 font=self._get_safe_font("body"), text_color="#60a5fa").pack(anchor="w", padx=12, pady=(8, 2))
                    for k, v in [
                        ("연간 수익", f"{stock_profit:,.0f}원"),
                        ("기본공제", f"{float(fit_result.get('deduction', 0)):,.0f}원"),
                        ("과세표준", f"{float(fit_result.get('taxable', 0)):,.0f}원"),
                        ("예상 세액", f"{float(fit_result.get('tax', 0)):,.0f}원"),
                    ]:
                        ctk.CTkLabel(sec_b, text=f"{k}: {v}",
                                     font=self._get_safe_font("body"), text_color="#cbd5e1").pack(anchor="w", padx=20, pady=1)
                    ctk.CTkLabel(sec_b, text="").pack(pady=2)

                # 3. 절세 계좌 비교
                saving_result = compare_tax_saving_accounts(annual_salary=_v("annual_salary"))
                sec_c = ctk.CTkFrame(result_frame, fg_color="#1a1207", corner_radius=8)
                sec_c.pack(fill="x", padx=10, pady=4)
                ctk.CTkLabel(sec_c, text="절세 계좌 비교 (ISA/연금저축/IRP)",
                             font=self._get_safe_font("body"), text_color="#fbbf24").pack(anchor="w", padx=12, pady=(8, 2))
                for product_name, result_dict in (saving_result.get('accounts', {}) or {}).items():
                    benefit = float(result_dict.get('total_benefit', 0) or 0)
                    ctk.CTkLabel(sec_c, text=f"{product_name}: 절세 혜택 {benefit:,.0f}원/년",
                                 font=self._get_safe_font("body"), text_color="#cbd5e1").pack(anchor="w", padx=20, pady=1)
                ctk.CTkLabel(sec_c, text="").pack(pady=2)

                # 4. 최적화 요약
                summary_result = generate_tax_optimization_summary(
                    annual_salary=_v("annual_salary"),
                    financial_income=fin_income,
                    stock_profit=stock_profit,
                )
                sec_d = ctk.CTkFrame(result_frame, fg_color="#111827", corner_radius=8)
                sec_d.pack(fill="x", padx=10, pady=4)
                ctk.CTkLabel(sec_d, text="절세 최적화 요약",
                             font=self._get_safe_font("body"), text_color="#4ade80").pack(anchor="w", padx=12, pady=(8, 2))
                for tip in (summary_result.get('tips', []) or [])[:5]:
                    ctk.CTkLabel(sec_d, text=f"→ {tip}", font=self._get_safe_font("body"),
                                 text_color="#a7f3d0", wraplength=860, justify="left").pack(anchor="w", padx=20, pady=1)
                ctk.CTkLabel(sec_d, text="").pack(pady=4)

            except Exception as e:
                for w in result_frame.winfo_children():
                    w.destroy()
                ctk.CTkLabel(result_frame, text=f"계산 오류: {e}",
                             font=self._get_safe_font("body"), text_color="#ef4444").pack(padx=14, pady=10)

        ctk.CTkButton(input_frame, text="세금 계산하기",
                      command=_run_tax_calc, height=36,
                      font=self._get_safe_font("button"),
                      fg_color="#065f46", hover_color="#064e3b").pack(anchor="e", padx=14, pady=8)

        # 초기 상태 안내
        ctk.CTkLabel(result_frame, text="입력값을 입력하고 [세금 계산하기] 버튼을 눌러 결과를 확인하세요.",
                     font=self._get_safe_font("body"), text_color="#6b7280").pack(padx=14, pady=20)

    # ──────────────────────────────────────────────────────────────────────────
    # Ensure helpers: _get_or_add_tab + build 연결
    # ──────────────────────────────────────────────────────────────────────────

    def _ensure_asset_allocation_diagnosis_tab(self) -> None:
        try:
            tab = self._get_or_add_tab("자산 배분 진단")
            self._build_asset_allocation_diagnosis_tab(tab)
        except Exception as e:
            try:
                self.logger.warning(f"자산 배분 진단 탭 생성 실패: {e}")
            except Exception:
                pass

    def _ensure_risk_briefing_full_tab(self) -> None:
        try:
            tab = self._get_or_add_tab("리스크 브리핑")
            self._build_risk_briefing_tab(tab)
        except Exception as e:
            try:
                self.logger.warning(f"리스크 브리핑 탭 생성 실패: {e}")
            except Exception:
                pass

    def _ensure_scenario_check_tab(self) -> None:
        try:
            tab = self._get_or_add_tab("시나리오 점검")
            self._build_scenario_check_tab(tab)
        except Exception as e:
            try:
                self.logger.warning(f"시나리오 점검 탭 생성 실패: {e}")
            except Exception:
                pass

    def _ensure_fraud_detection_full_tab(self) -> None:
        try:
            tab = self._get_or_add_tab("보안 경고")
            self._build_fraud_detection_tab(tab)
        except Exception as e:
            try:
                self.logger.warning(f"보안 경고 탭 생성 실패: {e}")
            except Exception:
                pass

    def _ensure_tax_calculation_full_tab(self) -> None:
        try:
            tab = self._get_or_add_tab("세금 계산")
            self._build_tax_calculation_tab(tab)
        except Exception as e:
            try:
                self.logger.warning(f"세금 계산 탭 생성 실패: {e}")
            except Exception:
                pass

    def _ensure_financial_intelligence_tab(self, service_name: str) -> None:
        """서비스 컨텍스트에 맞는 금융 인텔리전스 실행형 탭을 생성한다."""
        try:
            from ui.service_tab_policy import normalize_service_name
            from ui.widgets.financial_intelligence_widget import FinancialIntelligenceWidget

            service = normalize_service_name(service_name)
            config = {
                "blockchain": ("금융 인텔리전스", "blockchain"),
                "stock": ("금융 인텔리전스", "stock"),
                "real_estate": ("성과·위험 분석", "asset"),
                "ai_analyst": ("금융 인텔리전스 허브", "ai_analyst"),
            }
            if service not in config:
                return
            tab_name, mode = config[service]
            tab = self._get_or_add_tab(tab_name)

            # 블록체인/주식은 같은 탭 프레임 안에서 서비스별 위젯을 보관하고
            # pack/forget으로 교체한다. 드롭다운 메뉴가 포함된 큰 위젯을 서비스
            # 왕복마다 destroy/rebuild하지 않아 Windows USER 자원 사용이 bounded 된다.
            existing_widgets = getattr(self, "financial_intelligence_widgets", {}) or {}
            existing_widget = existing_widgets.get(service)
            for other_service, other_widget in list(existing_widgets.items()):
                if other_service == service or other_widget is None:
                    continue
                try:
                    if other_widget.winfo_exists() and other_widget.master is tab:
                        other_widget.pack_forget()
                except Exception:
                    pass
            try:
                if (
                    existing_widget is not None
                    and existing_widget.winfo_exists()
                    and existing_widget.master is tab
                    and not getattr(existing_widget, "_cleaned_up", False)
                ):
                    if not existing_widget.winfo_manager():
                        existing_widget.pack(fill="both", expand=True)
                    return
            except Exception:
                pass

            # 이전 서비스 위젯은 파괴하지 않고 숨긴다. 오류 안내처럼 캐시 대상이
            # 아닌 잔여 자식만 숨겨 새 본문과 겹치지 않게 한다.
            try:
                for child in tab.winfo_children():
                    try:
                        child.pack_forget()
                    except Exception:
                        try:
                            child.grid_forget()
                        except Exception:
                            pass
            except Exception:
                pass
            db_path = self._get_dashboard_read_db_path()
            widget = FinancialIntelligenceWidget(
                tab,
                dashboard_ref=self,
                mode=mode,
                db_path=db_path or ":memory:",
            )
            widget.pack(fill="both", expand=True)
            if not hasattr(self, "financial_intelligence_widgets"):
                self.financial_intelligence_widgets = {}
            self._register_tab_mapping_widget(
                tab_name,
                self.financial_intelligence_widgets,
                service,
                widget,
            )
        except Exception as e:
            error_message = f"금융 인텔리전스 화면을 열 수 없습니다: {type(e).__name__}: {e}"
            try:
                self.logger.exception(f"금융 인텔리전스 탭 생성 실패 ({service_name}): {e}")
            except Exception:
                logging.getLogger(__name__).warning(
                    "금융 인텔리전스 탭 생성 실패 (%s): %s",
                    service_name,
                    e,
                )
            try:
                tab = self._get_or_add_tab("금융 인텔리전스")
                self._clear_tab_children(tab)
                ctk.CTkLabel(
                    tab,
                    text=(
                        "금융 인텔리전스 화면을 준비하지 못했습니다.\n"
                        "앱을 다시 시작한 뒤에도 같으면 오류 로그와 함께 관리자에게 문의하세요."
                    ),
                    text_color="#fca5a5",
                    font=self._get_safe_font("body", ctk.CTkFont(size=13)),
                    justify="left",
                ).pack(anchor="w", padx=20, pady=20)
            except Exception:
                pass

    def _ensure_current_financial_intelligence_content(self) -> None:
        """현재 서비스의 금융 인텔리전스 본문이 빈 탭으로 남지 않게 한다."""
        try:
            from ui.service_tab_policy import normalize_service_name

            service = normalize_service_name(getattr(self, "current_service", "blockchain"))
            if service in {"blockchain", "stock", "real_estate", "ai_analyst"}:
                self._ensure_financial_intelligence_tab(service)
        except Exception as exc:
            try:
                self.logger.warning(f"금융 인텔리전스 지연 초기화 실패: {exc}")
            except Exception:
                pass

    def _apply_service_tab_policy(self, service_name: str) -> None:
        """서비스 전환 직후, 서비스 전용 탭 구성으로 강제 동기화합니다."""
        try:
            try:
                from ui.service_tab_policy import normalize_service_name
                service = normalize_service_name(service_name)
            except Exception:
                service = str(service_name or '').lower()

            if service == 'real_estate':
                self._ensure_asset_allocation_diagnosis_tab()
                self._ensure_risk_briefing_full_tab()
                self._ensure_financial_intelligence_tab(service)
            elif service in {'other', 'other_investment'}:
                self._ensure_service_info_tab(
                    "현금흐름 분석",
                    "현금흐름 분석",
                    self._build_life_finance_cashflow_lines(),
                )
                self._ensure_service_info_tab(
                    "생활금융 목표",
                    "생활금융 목표",
                    self._build_life_finance_goal_lines(),
                )
                self._ensure_fraud_detection_full_tab()
                self._ensure_tax_calculation_full_tab()
            elif service == 'ai_analyst':
                self._ensure_ai_assistant_tab()
                self._ensure_service_info_tab(
                    "AI 요약 리포트",
                    "AI 요약 리포트",
                    self._build_ai_summary_report_lines(),
                )
                self._ensure_scenario_check_tab()
                self._ensure_financial_intelligence_tab(service)

            protected_tabs = self._get_service_protected_tabs(service)
            tv = cast(ctk.CTkTabview, self.tab_widget)
            for tab_name in list(getattr(tv, '_tab_dict', {}).keys()):
                is_service_detail_tab = any(
                    tab_name in tabs
                    for tabs in self.service_sub_tabs.values()
                )
                if is_service_detail_tab:
                    if tab_name not in self.service_sub_tabs.get(service, {}):
                        try:
                            self._delete_dashboard_tab(tab_name)
                        except Exception:
                            pass
                    continue

                if tab_name not in protected_tabs:
                    try:
                        self._delete_dashboard_tab(tab_name)
                    except Exception:
                        pass

            from ui.service_tab_policy import get_service_tab_order

            source_tabs = list(self.service_sub_tabs.get(service, {}).keys())
            reorder_ctk_tabs(tv, get_service_tab_order(service, source_tabs))

            # 비거래 서비스는 핵심 탭만 유지하고 안내성 탭/공통 어시스턴트 탭은 강제 생성하지 않는다.
        except Exception as e:
            try:
                self.logger.warning(f"서비스 탭 정책 적용 실패 ({service_name}): {e}")
            except Exception:
                pass

    def _check_actual_exchange_status(self, exchange: str) -> bool:
        """거래소 실제 실행 상태 확인"""
        try:
            ex = str(exchange or '').strip().lower()
            if not ex:
                return False

            # 엔진/워커 상태를 UI 캐시보다 우선한다.
            if self._check_engine_exchange_status(ex):
                return True

            main_app = getattr(self, 'main_app', None)
            if main_app is not None:
                state_mgr = getattr(main_app, 'state', None)
                if state_mgr is not None:
                    state_name = str(getattr(state_mgr, 'state', '') or '').upper()
                    state_exchange = str(getattr(state_mgr, 'exchange', '') or '').strip().lower()
                    return bool(state_name == 'STARTING' and state_exchange == ex)
                return False

            # main_app 연결 전 초기 생성에만 UI 캐시를 폴백으로 사용한다.
            running_set = set(getattr(self, '_running_exchanges', set()) or set())
            if ex in running_set:
                return True

            # 개별 토글 상태 저장소 폴백
            local_running = bool(getattr(self, '_exchange_running', {}).get(ex, False))
            return local_running
        except Exception:
            return False

    def _check_engine_exchange_status(self, exchange: str) -> bool:
        """UI 캐시를 제외한 실제 워커/모니터링 상태를 조회한다."""
        try:
            ex = str(exchange or '').strip().lower()
            app = getattr(self, 'main_app', None)
            if app is None:
                return False
            if ex == 'binance':
                thread = getattr(app, 'trading_thread', None)
                worker = getattr(app, 'trading_worker', None)
                return bool((thread is not None and thread.is_alive()) or getattr(worker, 'running', False))
            unified = getattr(app, 'unified_trader', None)
            if unified is None:
                return False
            if not bool((getattr(unified, 'monitoring_flags', {}) or {}).get(ex, False)):
                return False
            thread = (getattr(unified, 'monitoring_threads', {}) or {}).get(ex)
            return bool(thread is None or thread.is_alive())
        except Exception:
            return False

    def _exchange_custom_strategy_summary(self, exchange: str) -> str:
        """거래소 카드에 실제 활성 전략·실시간 국면·실행 방식을 표시한다."""
        ex = str(exchange or '').strip().lower()
        app = getattr(self, 'main_app', None)
        runtime_cfg = dict((getattr(app, 'settings', {}) or {}).get('ai_custom_runtime', {}) or {}) if app is not None else {}
        if not bool(runtime_cfg.get('enabled', False)):
            return "AI 커스텀 사용 안 함 · 설정에서 활성화"
        customizer = getattr(app, 'strategy_customizer', None) if ex == 'binance' else getattr(app, 'strategy_customizer_unified', None)
        pool = customizer.get_active_strategy_pool() if customizer and hasattr(customizer, 'get_active_strategy_pool') else []
        if ex == 'binance':
            regime = str(getattr(getattr(app, 'trader', None), 'last_market_regime', 'range') or 'range')
        else:
            regimes = getattr(getattr(app, 'unified_trader', None), 'last_market_regime_by_exchange', {}) or {}
            regime = str(regimes.get(ex, 'range') or 'range')
        try:
            from trading.declarative_strategy_engine import DeclarativeStrategyEngine
            matched = [
                item for item in pool
                if DeclarativeStrategyEngine._scope_matches(
                    str(item.get('target_scope', '')), asset_class='crypto', target=ex,
                ) and (
                    'all' in [str(value).lower() for value in (item.get('market_regimes') or ['all'])]
                    or DeclarativeStrategyEngine.REGIME_ALIASES.get(regime.upper(), regime.lower())
                    in [str(value).lower() for value in (item.get('market_regimes') or ['all'])]
                )
            ]
        except Exception:
            matched = []
        if not matched:
            return f"기본 AI · 커스텀 없음 · 현재 국면 {regime}"
        selected = sorted(matched, key=lambda item: int(item.get('priority', 5) or 5), reverse=True)[0]
        mode = '독립 신호' if selected.get('signal_mode') == 'independent' else 'AI 확인·필터'
        operation = '1배/1% 제한운용' if selected.get('operation_mode') == 'limited_live' else '일반운용'
        return f"{selected.get('name', '사용자 전략')} · {mode} · {operation} · 우선 {selected.get('priority', 5)} · 국면 {regime}"

    def create_exchange_control_section(self, parent, exchange: str):
        """거래소별 시작/정지 컨트롤(토글 버튼)"""
        try:
            title = ctk.CTkLabel(
                parent,
                text=f"{exchange.upper()} 제어",
                font=self._get_safe_font("title"),
                text_color=self._color('text_primary', '#f9fafb')
            )
            title.pack(anchor="w", pady=(8, 6), padx=8)

            btn_frame = ctk.CTkFrame(parent, fg_color="#0b1120")
            btn_frame.pack(anchor="w", padx=8, pady=(0, 8))

            # 토글 상태 저장소 (실제 거래 상태와 동기화)
            if not hasattr(self, '_exchange_running'):
                self._exchange_running = {}
            if not hasattr(self, '_exchange_action_pending'):
                self._exchange_action_pending = {}

            # 실제 거래 상태 확인하여 초기값 설정
            actual_running = self._check_actual_exchange_status(exchange)
            # 탭을 다시 만들 때 과거 UI 캐시가 실제 워커 상태를 덮지 않게 한다.
            self._exchange_running[exchange] = actual_running

            # 전역 실행 집합에도 초기 상태 동기화
            if not hasattr(self, '_running_exchanges'):
                self._running_exchanges = set()
            if actual_running:
                self._running_exchanges.add(exchange)
            else:
                self._running_exchanges.discard(exchange)

            def _toggle_exchange(e=exchange):
                try:
                    if self._exchange_action_pending.get(e, False):
                        return

                    running = bool(self._exchange_running.get(e, False))
                    self._exchange_action_pending[e] = True

                    if e in self._exchange_toggle_buttons:
                        self._exchange_toggle_buttons[e].configure(state="disabled", text="⏳ 처리 중")
                    if e in self._exchange_status_labels:
                        if running:
                            pending_text = "정지 중..."
                        else:
                            action_label = "거래" if self._is_exchange_live_order_enabled(e) else "학습"
                            pending_text = f"{action_label} 시작 중..."
                        self._exchange_status_labels[e].configure(text=pending_text)

                    def _worker():
                        started = False
                        stopped = False
                        action_error = None
                        try:
                            if running:
                                if hasattr(self, 'main_app') and self.main_app and hasattr(self.main_app, 'on_stop_exchange'):
                                    stopped = bool(self.main_app.on_stop_exchange(e))
                            else:
                                if hasattr(self, 'main_app') and self.main_app and hasattr(self.main_app, 'on_start_exchange'):
                                    started = bool(self.main_app.on_start_exchange(e))
                        except Exception as ex:
                            action_error = ex

                        def _apply_result():
                            try:
                                if action_error is not None:
                                    self.logger.error(f"토글 실패: {e} - {action_error}")

                                if running:
                                    engine_running = self._check_engine_exchange_status(e)
                                    next_running = not bool(stopped or not engine_running)
                                else:
                                    engine_running = self._check_engine_exchange_status(e)
                                    next_running = bool(started or engine_running)

                                self.sync_exchange_runtime_state(e, next_running)
                            finally:
                                self._exchange_action_pending[e] = False

                        self.thread_safe_after(0, _apply_result)

                    threading.Thread(target=_worker, daemon=True, name=f"toggle_{e}").start()
                except Exception as te:
                    try:
                        self.logger.error(f"토글 실패: {e} - {te}")
                        self._exchange_action_pending[e] = False
                    except Exception:
                        pass

            # 단일 토글 버튼
            toggle_btn = ctk.CTkButton(
                btn_frame,
                text=f"▶{exchange.upper()} 시작",
                width=150,
                height=36,
                fg_color=self._color('success', '#10b981'),
                text_color=self._color('text_primary', '#f9fafb'),
                hover_color=self._color('hover', '#059669'),
                corner_radius=12,
                command=_toggle_exchange
            )
            toggle_btn.pack(side="left", padx=(0, 6))
            self._exchange_toggle_buttons[exchange] = toggle_btn
            self._update_exchange_toggle_button(exchange)

            # API 키 상태 + 실행 상태 배지
            try:
                key_ok = False
                if hasattr(self, 'settings') and isinstance(self.settings, dict):
                    k1 = self.settings.get(f"{exchange}_api_key", "") or self.settings.get(f"{exchange}_api", "")
                    k2 = self.settings.get(f"{exchange}_secret_key", "") or self.settings.get(f"{exchange}_secret", "")
                    key_ok = bool(str(k1).strip() and str(k2).strip())
                api_text = ("API 키 연결됨" if key_ok else "PAPER 권장: API 키 없음")
                api_label = ctk.CTkLabel(
                    parent,
                    text=api_text,
                    font=self._get_safe_font("small"),
                    text_color=(self._color('success', '#22c55e') if key_ok else self._color('warning', '#f59e0b'))
                )
                api_label.pack(anchor="w", padx=8, pady=(2, 2))
            except Exception:
                pass

            # 상태 배지 (Stopped 초기값)
            status_label = ctk.CTkLabel(
                parent,
                text=("진행 중" if actual_running else "정지"),
                font=self._get_safe_font("small"),
                text_color=self._color('text_secondary', '#9ca3af')
            )
            status_label.pack(anchor="w", padx=8, pady=(0, 6))
            self._exchange_status_labels[exchange] = status_label
            self.sync_exchange_runtime_state(
                exchange,
                actual_running,
                self._runtime_status_for_exchange(exchange, actual_running),
            )

            strategy_label = ctk.CTkLabel(
                parent, text=self._exchange_custom_strategy_summary(exchange),
                font=ctk.CTkFont(size=10), text_color="#60a5fa", anchor="w",
            )
            strategy_label.pack(fill="x", padx=8, pady=(0, 7))
            self.exchange_section_widgets.setdefault(exchange, {})['strategy_status'] = strategy_label

            def _refresh_strategy_status():
                try:
                    if strategy_label.winfo_exists():
                        self._reconcile_exchange_control_from_engine(exchange)
                        strategy_label.configure(text=self._exchange_custom_strategy_summary(exchange))
                        self._schedule_visible_refresh(strategy_label, 5000, _refresh_strategy_status)
                except Exception:
                    pass
            self._schedule_visible_refresh(strategy_label, 500, _refresh_strategy_status)
        except Exception as e:
            print(f"제어 섹션 생성 실패: {exchange} - {e}")

    def create_exchange_balance_section(self, parent, exchange: str):
        """거래소별 잔고를 3열 미니 카드로 표시한다."""
        try:
            header = ctk.CTkFrame(parent, fg_color="transparent")
            header.pack(fill="x", padx=10, pady=(7, 3))
            balance_title_label = ctk.CTkLabel(
                header, text="잔고", font=self._get_safe_font("title"),
                text_color=self._color('text_primary', '#f9fafb'),
            )
            balance_title_label.pack(side="left")
            status_label = ctk.CTkLabel(
                header, text="7초 자동 갱신", font=self._get_safe_font("small"),
                text_color=self._color('text_secondary', '#94a3b8'),
            )
            status_label.pack(side="right")

            grid = ctk.CTkFrame(parent, fg_color="transparent")
            grid.pack(fill="x", padx=8, pady=(0, 7))
            grid.grid_columnconfigure((0, 1, 2), weight=1, uniform=f"{exchange}_balance")
            value_pairs = []
            for index in range(3):
                card = ctk.CTkFrame(
                    grid, height=48, fg_color="#111827", corner_radius=9,
                    border_width=1, border_color="#334155",
                )
                card.grid(row=0, column=index, sticky="ew", padx=3)
                card.grid_propagate(False)
                title_label = ctk.CTkLabel(
                    card, text="-", font=self._get_safe_font("small"),
                    text_color=self._color('text_secondary', '#94a3b8'),
                )
                title_label.pack(anchor="w", padx=8, pady=(3, 0))
                value_label = ctk.CTkLabel(
                    card, text="탭 열면 조회", font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="#e2e8f0",
                )
                value_label.pack(anchor="w", padx=8, pady=(0, 3))
                value_pairs.append((title_label, value_label))

            # 레퍼런스 저장
            widgets = self.exchange_section_widgets.setdefault(exchange, {})
            widgets['balance_label'] = status_label
            widgets['balance_status'] = status_label
            widgets['balance_values'] = value_pairs
            self._set_balance_metric_state(widgets, "탭 열면 조회")
            status_label.configure(text="조회 대기", text_color="#94a3b8")

            # 즉시 1회 업데이트
            def refresh_once():
                def _load_balance():
                    paper_positions = self._paper_position_snapshot(exchange)
                    if paper_positions is not None:
                        return {
                            'status': 'paper',
                            'positions': paper_positions,
                        }
                    # 모든 거래소에서 실제 거래 루프와 같은 ExchangeManager를
                    # 우선 사용한다. 화면이 별도 Unified adapter를 만들어 다른
                    # 연결/캐시를 보던 경로를 제거한다.
                    manager = getattr(self, "exchange_manager", None)
                    if manager is None:
                        main_app = getattr(self, "main_app", None)
                        manager = getattr(main_app, "exchange_manager", None)
                    if manager is not None:
                        return manager.get_exchange_balance(
                            exchange_name=exchange,
                            force_refresh=True,
                        )
                    if hasattr(self, 'unified_manager') and self.unified_manager:
                        t = 'futures' if exchange in ['binance','bybit','okx','bitget'] else 'spot'
                        return self.unified_manager.get_exchange_balance(exchange, t)
                    return {'status': 'waiting'}

                def _apply_balance(res):
                    result = res if isinstance(res, dict) else {}
                    if result.get('status') == 'paper':
                        paper_summary = summarize_paper_positions(result.get('positions', {}))
                        quote = 'KRW' if str(exchange).lower() in {'upbit', 'bithumb'} else 'USDT'
                        paper_items = [
                            ("PAPER 모드", "실잔고 미사용"),
                            ("가상 포지션", f"{int(paper_summary['position_count'])}개"),
                            (
                                "가상 미실현 PnL",
                                f"{self._format_position_number(paper_summary['unrealized_pnl'], signed=True)} {quote}",
                            ),
                        ]
                        for index, pair in enumerate(widgets.get('balance_values', [])):
                            title_widget, value_widget = pair
                            title_widget.configure(text=paper_items[index][0])
                            value_widget.configure(text=paper_items[index][1])
                        balance_title_label.configure(text="가상 계좌")
                        status_label.configure(
                            text="PAPER · 실주문·실잔고 미사용",
                            text_color="#a78bfa",
                        )
                    elif result.get('status') == 'success':
                        bal = result.get('balance', {})
                        self._update_balance_metric_widgets(widgets, exchange, bal)
                        balance_title_label.configure(text="잔고")
                        status_label.configure(
                            text=f"{exchange.upper()} · 7초 갱신 · 최대 3개 표시",
                            text_color="#94a3b8",
                        )
                    else:
                        balance_title_label.configure(text="잔고")
                        message = self._balance_status_message(result)
                        self._set_balance_metric_state(widgets, message)
                        detail = str(
                            result.get("message") or result.get("error") or ""
                        ).strip()
                        status_text = message if not detail else f"{message}: {detail[:22]}"
                        status_label.configure(text=status_text, text_color="#f59e0b")

                def _apply_balance_error(ie):
                    self._set_balance_metric_state(widgets, "조회 지연/오류")
                    status_label.configure(text=f"잔고 오류: {str(ie)[:22]}", text_color="#ef4444")

                status_label.configure(text="잔고 조회 중", text_color="#60a5fa")
                started = self._run_visible_refresh_async(
                    parent,
                    f"exchange_balance:{exchange}",
                    _load_balance,
                    _apply_balance,
                    _apply_balance_error,
                )
                if not started:
                    try:
                        registry = getattr(parent, "_noah_async_refresh_registry", {})
                        state = registry.get(f"exchange_balance:{exchange}", {})
                        if not bool(state.get("running", False)):
                            self._set_balance_metric_state(widgets, "조회 예약 실패")
                            status_label.configure(text="조회 예약 실패", text_color="#ef4444")
                    except Exception:
                        pass
                # 잔고는 주기적으로 갱신되어야 사용자 체감이 좋다.
                try:
                    self._schedule_visible_refresh(parent, 7000, refresh_once)
                except Exception:
                    pass
            self._schedule_visible_refresh(parent, 100, refresh_once)
        except Exception as e:
            print(f"잔고 섹션 생성 실패: {exchange} - {e}")

    def create_service_sub_tabs(self, service_name: str):
        """현재 서비스의 거래소/증권사 하위 탭을 한 번만 생성한다."""
        try:
            if not hasattr(self, 'tab_widget') or not self.tab_widget:
                return

            if service_name == 'blockchain':
                desired_labels = [
                    str(exchange).upper()
                    for exchange in self.settings.get('enabled_exchanges', ['binance'])
                ]
            elif service_name == 'stock':
                desired_labels = [
                    str(broker).upper()
                    for broker in self.settings.get('enabled_stock_brokers', [])
                ]
            else:
                desired_labels = []
            existing_tabs = dict(self.service_sub_tabs.get(service_name, {}) or {})
            if (
                list(existing_tabs.keys()) == desired_labels
                and all(widget_is_alive(frame) for frame in existing_tabs.values())
            ):
                self._apply_service_tab_policy(service_name)
                return

            if service_name == 'blockchain':
                # 설정에서 활성화된 거래소만 탭 생성
                enabled_exchanges = self.settings.get('enabled_exchanges', ['binance'])
                for exchange in enabled_exchanges:
                    tab_label = f"{exchange.upper()}"
                    try:
                        # 탭 재사용 또는 생성 (중복 방지)
                        tab = self._get_or_add_tab(tab_label)
                        # 내용 중복 방지 위해 초기화
                        self._clear_tab_children(tab)
                        self.service_sub_tabs['blockchain'][tab_label] = tab

                        # 레이아웃 컨테이너
                        container = ctk.CTkFrame(tab, fg_color="#0b1120")
                        container.pack(fill="both", expand=True, padx=10, pady=10)

                        # 반응형 좌/우 레이아웃: 좌측 스택(제어/잔고/포지션/거래통계), 우측 전체 로그
                        root_split = ctk.CTkFrame(container, fg_color="#0b1120")
                        root_split.pack(fill="both", expand=True)

                        layout = self._get_service_split_layout()
                        left_pane = ctk.CTkFrame(root_split, width=layout["left_width"], fg_color="#0b1120")
                        left_pane.pack(side="left", fill="y", padx=(0, 10))
                        try:
                            left_pane.pack_propagate(False)
                            left_pane.grid_propagate(False)
                        except Exception:
                            pass

                        left_pane.grid_columnconfigure(0, weight=1)
                        left_pane.grid_rowconfigure(2, weight=1, minsize=230)
                        left_pane.grid_rowconfigure(3, minsize=88)

                        # 1) 제어
                        control_frame = self._create_card_frame(left_pane)
                        control_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
                        self.create_exchange_control_section(control_frame, exchange)

                        # 2) 잔고 (가장 낮은 높이)
                        balance_frame = self._create_card_frame(left_pane)
                        balance_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
                        self.create_exchange_balance_section(balance_frame, exchange)

                        # 3) 포지션 (적당한 높이, 확장 가능)
                        positions_frame = self._create_card_frame(left_pane)
                        positions_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
                        try:
                            positions_frame.configure(height=240)
                            positions_frame.pack_propagate(False)
                        except Exception:
                            pass
                        self.create_exchange_positions_section(positions_frame, exchange)

                        # 4) 거래 통계 (포지션 공간을 우선하는 슬림 KPI 바)
                        stats_frame = self._create_card_frame(left_pane)
                        stats_frame.grid(row=3, column=0, sticky="nsew")
                        try:
                            stats_frame.configure(height=88)
                            stats_frame.pack_propagate(False)
                        except Exception:
                            pass
                        self.create_exchange_stats_section(stats_frame, exchange)

                        # 오른쪽: 실시간 로그 전체
                        right_pane = ctk.CTkFrame(root_split, fg_color="#0b1120")
                        right_pane.pack(side="left", fill="both", expand=True)
                        self.create_exchange_logs_section(right_pane, exchange)
                        section_frames = {
                            "control": control_frame,
                            "balance": balance_frame,
                            "positions": positions_frame,
                            "stats": stats_frame,
                            "logs": right_pane,
                        }
                        incomplete = [
                            name for name, frame in section_frames.items()
                            if not list(frame.winfo_children())
                        ]
                        if incomplete:
                            raise RuntimeError(
                                "service_tab_partial_render:" + ",".join(incomplete)
                            )
                    except Exception as e:
                        try:
                            self.logger.exception(f"하위 탭 생성 실패: {exchange} - {e}")
                        except Exception:
                            print(f"하위 탭 생성 실패: {exchange} - {e}")
                        try:
                            self._clear_tab_children(tab)
                            error_card = self._create_card_frame(tab, corner_radius=14)
                            error_card.pack(fill="x", padx=24, pady=24)
                            ctk.CTkLabel(
                                error_card,
                                text=(
                                    f"{exchange.upper()} 화면을 완전하게 만들지 못했습니다.\n"
                                    "부분 화면으로 거래하지 말고 프로그램을 재시작한 뒤 다시 확인하세요."
                                ),
                                text_color="#fca5a5",
                                justify="left",
                            ).pack(anchor="w", padx=16, pady=16)
                        except Exception:
                            pass
            elif service_name == 'stock':
                # 설정에서 활성화된 증권사만 탭 생성
                enabled_brokers = self.settings.get('enabled_stock_brokers', [])
                for broker in enabled_brokers:
                    tab_label = f"{broker.upper()}"
                    try:
                        # 탭 재사용 또는 생성 (중복 방지)
                        tab = self._get_or_add_tab(tab_label)
                        # 내용 중복 방지 위해 초기화
                        self._clear_tab_children(tab)
                        self.service_sub_tabs['stock'][tab_label] = tab

                        # 레이아웃 컨테이너
                        container = ctk.CTkFrame(tab, fg_color="#0b1120")
                        container.pack(fill="both", expand=True, padx=10, pady=10)

                        # 반응형 좌/우 레이아웃: 좌측 스택(제어/잔고/포지션/거래통계), 우측 전체 로그
                        root_split = ctk.CTkFrame(container, fg_color="#0b1120")
                        root_split.pack(fill="both", expand=True)

                        layout = self._get_service_split_layout()
                        left_pane = ctk.CTkFrame(root_split, width=layout["left_width"], fg_color="#0b1120")
                        left_pane.pack(side="left", fill="y", padx=(0, 10))
                        try:
                            left_pane.pack_propagate(False)
                            left_pane.grid_propagate(False)
                        except Exception:
                            pass

                        left_pane.grid_columnconfigure(0, weight=1)
                        left_pane.grid_rowconfigure(2, weight=1, minsize=230)
                        left_pane.grid_rowconfigure(3, minsize=88)

                        # 1) 제어
                        control_frame = self._create_card_frame(left_pane)
                        control_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
                        self.create_broker_control_section(control_frame, broker)

                        # 2) 잔고 (가장 낮은 높이)
                        balance_frame = self._create_card_frame(left_pane)
                        balance_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
                        self.create_broker_balance_section(balance_frame, broker)

                        # 3) 포지션 (적당한 높이, 확장 가능)
                        positions_frame = self._create_card_frame(left_pane)
                        positions_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
                        try:
                            positions_frame.configure(height=240)
                            positions_frame.pack_propagate(False)
                        except Exception:
                            pass
                        self.create_broker_positions_section(positions_frame, broker)

                        # 4) 거래 통계 (보유 종목 공간을 우선하는 슬림 KPI 바)
                        stats_frame = self._create_card_frame(left_pane)
                        stats_frame.grid(row=3, column=0, sticky="nsew")
                        try:
                            stats_frame.configure(height=88)
                            stats_frame.pack_propagate(False)
                        except Exception:
                            pass
                        self.create_broker_stats_section(stats_frame, broker)

                        # 오른쪽: 실시간 로그 전체
                        right_pane = ctk.CTkFrame(root_split, fg_color="#0b1120")
                        right_pane.pack(side="left", fill="both", expand=True)
                        self.create_broker_logs_section(right_pane, broker)
                        section_frames = {
                            "control": control_frame,
                            "balance": balance_frame,
                            "positions": positions_frame,
                            "stats": stats_frame,
                            "logs": right_pane,
                        }
                        incomplete = [
                            name for name, frame in section_frames.items()
                            if not list(frame.winfo_children())
                        ]
                        if incomplete:
                            raise RuntimeError(
                                "service_tab_partial_render:" + ",".join(incomplete)
                            )
                    except Exception as e:
                        try:
                            self.logger.exception(f"하위 탭 생성 실패: {broker} - {e}")
                        except Exception:
                            print(f"하위 탭 생성 실패: {broker} - {e}")
            self.after_idle(self._apply_source_tab_distinction)
            try:
                self._apply_service_tab_policy(service_name)
            except Exception:
                pass
        except Exception as e:
            print(f"하위 탭 생성 오류: {e}")

    def _get_service_split_layout(self) -> Dict[str, int]:
        """대시보드 너비 기준으로 서비스 하위 탭 분할 폭을 계산한다."""
        width = 0
        try:
            width = int(self.winfo_width())
        except Exception:
            width = 0

        # 초기 렌더 단계에서는 실제 너비가 1로 들어올 수 있어 보정
        if width < 600:
            width = 1360

        # 상용 운영 화면에서 로그 가시성을 유지하기 위해 좌측 패널 최대폭을 제한
        if width >= 1800:
            left_width = 620
        elif width >= 1500:
            left_width = 560
        else:
            left_width = 500

        return {"left_width": left_width}

    def create_exchange_positions_section(self, parent, exchange: str):
        """선물 포지션 또는 현물 보유자산을 상태와 함께 표시한다."""
        try:
            account_contract = get_exchange_account_contract(exchange)
            header = ctk.CTkFrame(parent, fg_color="transparent")
            header.pack(fill="x", padx=10, pady=(7, 3))
            position_title_label = ctk.CTkLabel(
                header, text=account_contract.title, font=self._get_safe_font("title"),
                text_color=self._color('text_primary', '#f9fafb'),
            )
            position_title_label.pack(side="left")
            count_label = ctk.CTkLabel(
                header, text="조회 중", font=self._get_safe_font("small"),
                text_color="#60a5fa",
            )
            count_label.pack(side="right")

            body = ctk.CTkScrollableFrame(
                parent, fg_color="#0b1120", corner_radius=9,
                border_width=1, border_color="#1f2937",
            )
            body.pack(fill="both", expand=True, padx=8, pady=(0, 7))

            # 레퍼런스 저장
            widgets = self.exchange_section_widgets.setdefault(exchange, {})
            widgets['positions_body'] = body
            widgets['positions_count'] = count_label
            self._render_position_cards(
                body,
                count_label,
                {},
                empty_text=account_contract.loading_text,
                quote=account_contract.quote_asset,
                stock_mode=account_contract.holding_mode,
            )

            def refresh_once():
                try:
                    # 방송 리플레이 모드에서는 실API 대신 리플레이 DB의 미청산 포지션을 우선 표시
                    try:
                        replay_db_path = self._get_dashboard_read_db_path()
                        settings = self.settings if isinstance(self.settings, dict) else {}
                        replay_enabled = bool(settings.get('broadcast_replay_enabled', False))
                        if replay_enabled and replay_db_path and os.path.exists(replay_db_path):
                            replay_positions = self._get_replay_positions_for_exchange(
                                replay_db_path,
                                exchange,
                                max_positions=3,
                                timeline_step_seconds=8,
                                advance_timeline=bool(self.is_auto_trading),
                            )

                            self._render_position_cards(
                                body,
                                count_label,
                                replay_positions,
                                quote=account_contract.quote_asset,
                                stock_mode=account_contract.holding_mode,
                            )
                            try:
                                self._schedule_visible_refresh(parent, 7000, refresh_once)
                            except Exception:
                                pass
                            return
                    except Exception:
                        pass

                    def _load_positions():
                        positions = {}

                        # PAPER에서는 실거래소 API를 조회하지 않고 엔진의
                        # 분리된 가상 포지션 저장소를 UI 정본으로 사용한다.
                        paper_positions = self._paper_position_snapshot(exchange)
                        if paper_positions is not None:
                            return build_account_panel_result(
                                paper_positions,
                                empty_message="PAPER 가상 포지션 없음",
                                execution_mode="paper",
                            )

                        # 업비트·빗썸 현물은 선물 포지션 API가 아니라 잔고 정본의
                        # 양수 보유자산을 사용한다. 잔고 패널과 같은 ExchangeManager
                        # 캐시를 재사용해 인증 API를 중복 호출하지 않는다.
                        if account_contract.source == 'balance':
                            manager = getattr(self, 'exchange_manager', None)
                            if manager is None:
                                main_app = getattr(self, 'main_app', None)
                                manager = getattr(main_app, 'exchange_manager', None) if main_app else None
                            if manager is None:
                                return account_panel_unavailable('거래소 계좌 연결 미준비')
                            balance_result = manager.get_exchange_balance(
                                exchange_name=exchange,
                                force_refresh=False,
                            )
                            if not isinstance(balance_result, dict):
                                return account_panel_error('잔고 응답 형식 오류', 'invalid_balance_response')
                            status = str(balance_result.get('status') or '').strip().lower()
                            if status != 'success':
                                detail = str(
                                    balance_result.get('message')
                                    or balance_result.get('error')
                                    or self._balance_status_message(balance_result)
                                )
                                return account_panel_error(detail, status or 'balance_read_failed')
                            holdings = normalize_spot_holdings(
                                balance_result.get('balance', {}),
                                quote_asset=account_contract.quote_asset,
                            )
                            return build_account_panel_result(
                                holdings,
                                empty_message=account_contract.empty_text,
                            )

                        # 바이낸스는 거래소 API에서 직접 포지션 조회 (실제 상태 반영)
                        if exchange == 'binance':
                            main_app = getattr(self, 'main_app', None)
                            trader = getattr(main_app, 'trader', None) if main_app is not None else None
                            binance_client = getattr(main_app, 'binance_client', None) if main_app else None
                            if binance_client is None:
                                manager = getattr(self, 'exchange_manager', None)
                                binance_client = getattr(manager, 'binance_client', None) if manager else None
                            if binance_client is None and trader is not None:
                                binance_client = getattr(trader, 'binance_client', None)
                            if binance_client is None:
                                raise RuntimeError('Binance 클라이언트 미연결')

                            result_getter = getattr(binance_client, 'get_positions_result', None)
                            if callable(result_getter):
                                result = dict(result_getter() or {})
                                status = str(result.get('status') or '').lower()
                                if status != 'success':
                                    raise RuntimeError(result.get('error') or f'포지션 조회 {status}')
                                real_positions = result.get('positions') or []
                            else:
                                real_positions = binance_client.get_positions() or []

                            for pos in real_positions:
                                symbol = self._position_value(pos, 'symbol', default='')
                                quantity = float(self._position_value(pos, 'size', 'quantity', default=0) or 0)
                                if symbol and abs(quantity) > 0:
                                    positions[str(symbol)] = {
                                        'side': str(self._position_value(pos, 'side', default='LONG')).upper(),
                                        'quantity': abs(quantity),
                                        'entry_price': float(self._position_value(pos, 'entry_price', 'entryPrice', default=0) or 0),
                                        'unrealized_pnl': float(self._position_value(pos, 'unrealized_pnl', 'unrealizedPnl', default=0) or 0),
                                        'leverage': self._position_value(pos, 'leverage', default=None),
                                    }
                            return build_account_panel_result(
                                positions,
                                empty_message=account_contract.empty_text,
                            )

                        # CCXT 거래소도 실제 거래소 API에서 조회하되 UI 스레드를 막지 않는다.
                        unified_trader = getattr(self, 'unified_trader', None)
                        main_app = getattr(self, 'main_app', None)
                        if unified_trader is None and main_app is not None:
                            unified_trader = getattr(main_app, 'unified_trader', None)
                        try:
                            unified_manager = (
                                getattr(unified_trader, 'unified_manager', None)
                                if unified_trader is not None
                                else None
                            )
                            if unified_manager is None:
                                unified_manager = getattr(self, 'unified_manager', None)
                            if unified_manager is None and main_app is not None:
                                unified_manager = getattr(main_app, 'unified_manager', None)
                            if unified_manager:
                                trading_type = (
                                    'futures'
                                    if exchange.lower() in ['bybit', 'okx', 'bitget']
                                    else 'spot'
                                )
                                adapter = unified_manager.get_exchange(exchange, trading_type)
                                if adapter and hasattr(adapter, 'get_positions'):
                                    for pos in adapter.get_positions() or []:
                                        if not isinstance(pos, dict):
                                            continue
                                        amt = float(pos.get('contracts', pos.get('quantity', 0)) or 0)
                                        if abs(amt) <= 0:
                                            continue
                                        symbol = pos.get('symbol', '')
                                        positions[symbol] = {
                                            'side': str(pos.get('side', 'LONG')).upper(),
                                            'quantity': abs(amt),
                                            'entry_price': float(pos.get('entryPrice', pos.get('entry_price', 0)) or 0),
                                            'unrealized_pnl': float(pos.get('unrealizedPnl', pos.get('unrealized_pnl', 0)) or 0),
                                            'leverage': pos.get('leverage'),
                                        }
                            else:
                                return account_panel_unavailable('공통 거래 어댑터 미연결')
                        except Exception as adapter_error:
                            fallback = getattr(unified_trader, 'active_positions', {}) if unified_trader is not None else {}
                            cached_positions = (
                                dict(fallback.get(exchange, {}) or {})
                                if isinstance(fallback, dict)
                                else {}
                            )
                            if cached_positions:
                                return build_account_panel_result(
                                    cached_positions,
                                    empty_message=account_contract.empty_text,
                                    stale=True,
                                    message=f'실시간 조회 실패 · 로컬 캐시 ({str(adapter_error)[:36]})',
                                )
                            return account_panel_error(
                                f'실시간 조회 실패: {str(adapter_error)[:48]}',
                                'position_read_failed',
                            )
                        return build_account_panel_result(
                            positions,
                            empty_message=account_contract.empty_text,
                        )

                    def _apply_positions(result):
                        snapshot = result if isinstance(result, AccountPanelResult) else build_account_panel_result(
                            result,
                            empty_message=account_contract.empty_text,
                        )
                        empty_text = snapshot.message or account_contract.empty_text
                        paper_mode = snapshot.execution_mode == 'paper'
                        mode_badge = (
                            "PAPER"
                            if paper_mode
                            else self._exchange_execution_mode_value(exchange).upper()
                        )
                        position_title_label.configure(
                            text="PAPER 가상 포지션" if paper_mode else account_contract.title,
                            text_color="#c4b5fd" if paper_mode else self._color('text_primary', '#f9fafb'),
                        )
                        self._render_position_cards(
                            body,
                            count_label,
                            snapshot.rows,
                            empty_text=empty_text,
                            quote=account_contract.quote_asset,
                            stock_mode=account_contract.holding_mode and not paper_mode,
                            mode_label=mode_badge,
                        )
                        if snapshot.state == 'stale':
                            count_label.configure(
                                text=f"캐시 표시 · {datetime.now().strftime('%H:%M:%S')}",
                                text_color='#f59e0b',
                            )
                        elif snapshot.is_error:
                            count_label.configure(
                                text=f"조회 오류 · {datetime.now().strftime('%H:%M:%S')}",
                                text_color='#ef4444',
                            )
                        else:
                            try:
                                current_count = str(count_label.cget('text') or '')
                            except Exception:
                                current_count = f"{len(snapshot.rows)}개"
                            count_label.configure(
                                text=f"{current_count} · {datetime.now().strftime('%H:%M:%S')}"
                            )

                    def _apply_positions_error(ie):
                        position_title_label.configure(
                            text=account_contract.title,
                            text_color=self._color('text_primary', '#f9fafb'),
                        )
                        self._render_position_cards(
                            body,
                            count_label,
                            {},
                            empty_text=f"{account_contract.title} 조회 오류: {str(ie)[:28]}",
                            quote=account_contract.quote_asset,
                            stock_mode=account_contract.holding_mode,
                        )
                        count_label.configure(text="조회 오류", text_color="#ef4444")

                    self._run_visible_refresh_async(
                        parent,
                        f"exchange_positions:{exchange}",
                        _load_positions,
                        _apply_positions,
                        _apply_positions_error,
                    )
                except Exception as ie:
                    self._render_position_cards(
                        body,
                        count_label,
                        {},
                        empty_text=f"{account_contract.title} 조회 오류: {str(ie)[:28]}",
                        quote=account_contract.quote_asset,
                        stock_mode=account_contract.holding_mode,
                    )
                    count_label.configure(text="조회 오류", text_color="#ef4444")
                # 주기 갱신
                try:
                    self._schedule_visible_refresh(parent, 3000, refresh_once)
                except Exception:
                    pass
            self._schedule_visible_refresh(parent, 150, refresh_once)
        except Exception as e:
            print(f"계좌 상태 섹션 생성 실패: {exchange} - {e}")

    def create_exchange_stats_section(self, parent, exchange: str):
        """거래소별 핵심 통계를 항상 읽을 수 있는 한 줄 4열 KPI 카드로 표시한다."""
        try:
            header = ctk.CTkFrame(parent, fg_color="transparent")
            header.pack(fill="x", padx=10, pady=(4, 1))
            ctk.CTkLabel(
                header, text="거래 통계", font=self._get_safe_font("title"),
                text_color=self._color('text_primary', '#f9fafb')
            ).pack(side="left")
            status_label = ctk.CTkLabel(
                header, text="종료 거래 기준", font=self._get_safe_font("small"),
                text_color=self._color('text_secondary', '#9ca3af')
            )
            status_label.pack(side="right")

            grid = ctk.CTkFrame(parent, fg_color="transparent")
            grid.pack(fill="both", expand=True, padx=8, pady=(0, 4))
            grid.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform=f"{exchange}_stats")
            grid.grid_rowconfigure(0, weight=1)

            value_labels = {}
            specs = (
                ("total", "실제 체결", "0건", "#60a5fa"),
                ("win_rate", "승률", "0.0%", "#22c55e"),
                ("pnl", "순손익", "0.00", "#f59e0b"),
                ("fees", "수수료", "0.00", "#c084fc"),
            )
            for index, (key, title_text, initial, accent) in enumerate(specs):
                card = ctk.CTkFrame(
                    grid, fg_color="#111827", corner_radius=10,
                    border_width=1, border_color="#334155"
                )
                card.grid(row=0, column=index, sticky="nsew", padx=3, pady=3)
                ctk.CTkLabel(
                    card, text=title_text, font=ctk.CTkFont(size=10),
                    text_color=self._color('text_secondary', '#9ca3af')
                ).pack(anchor="w", padx=7, pady=(2, 0))
                value = ctk.CTkLabel(
                    card, text=initial, font=ctk.CTkFont(size=13, weight="bold"),
                    text_color=accent
                )
                value.pack(anchor="w", padx=7, pady=(0, 2))
                value_labels[key] = value

            # 레퍼런스 저장
            widgets = self.exchange_section_widgets.setdefault(exchange, {})
            widgets['stats_label'] = status_label
            widgets['stats_values'] = value_labels

            def refresh_once():
                try:
                    import sqlite3
                    import os
                    db_path = self._get_dashboard_read_db_path()
                    if not os.path.exists(db_path):
                        status_label.configure(text="DB 파일 없음", text_color="#f59e0b")
                        return
                    with sqlite3.connect(db_path) as conn:
                        cur = conn.cursor()
                        effective_exchange = exchange.lower()

                        has_fees_column = False
                        try:
                            cur.execute("PRAGMA table_info(trade_log)")
                            table_cols = {str(col[1]).lower() for col in (cur.fetchall() or []) if len(col) > 1}
                            has_fees_column = 'fees' in table_cols
                        except Exception:
                            has_fees_column = False

                        fee_expr = "COALESCE(fees, 0)" if has_fees_column else "0"

                        cur.execute(f"""
                            SELECT
                                COUNT(*) as total_trades,
                                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                                SUM(COALESCE(pnl, 0)) as total_pnl,
                                SUM({fee_expr}) as total_fees
                            FROM trade_log
                            WHERE exit_time IS NOT NULL AND LOWER(COALESCE(exchange, 'unknown')) = ?
                              AND LOWER(COALESCE(reason, '')) != 'binance_import'
                        """, (effective_exchange,))
                        row = cur.fetchone()
                        # 레거시 데이터 보정: binance가 0건이면 exchange=NULL 이력을 포함
                        if row and (row[0] or 0) == 0 and effective_exchange == 'binance':
                            cur.execute(f"""
                                SELECT
                                    COUNT(*) as total_trades,
                                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                                    SUM(COALESCE(pnl, 0)) as total_pnl,
                                    SUM({fee_expr}) as total_fees
                                FROM trade_log
                                WHERE exit_time IS NOT NULL
                                  AND LOWER(COALESCE(reason, '')) != 'binance_import'
                                  AND (LOWER(COALESCE(exchange, 'unknown')) = 'binance' OR exchange IS NULL)
                            """)
                            row = cur.fetchone()
                            prefix = "[legacy포함] "
                        else:
                            prefix = ""

                        if row:
                            closed_trades = int(row[0] or 0)
                            winning_trades = row[1] or 0
                            total_pnl = row[2] or 0.0
                            closed_fees = row[3] or 0.0
                            execution_count = 0
                            execution_fees = 0.0
                            try:
                                cur.execute(
                                    """
                                    SELECT COUNT(*), SUM(COALESCE(fee, 0))
                                    FROM exchange_execution_log
                                    WHERE LOWER(exchange) = ?
                                      AND confirmation_status = 'confirmed'
                                    """,
                                    (effective_exchange,),
                                )
                                execution_row = cur.fetchone() or (0, 0.0)
                                execution_count = int(execution_row[0] or 0)
                                execution_fees = float(execution_row[1] or 0.0)
                            except Exception:
                                execution_count = 0
                                execution_fees = 0.0
                            total_trades = execution_count or closed_trades
                            total_fees = execution_fees if execution_count else closed_fees

                            # 방송 리플레이 표시 오버레이를 거래소 탭 KPI에도 동일 적용
                            try:
                                display_overrides = self._get_broadcast_display_overrides()
                                override_trades = display_overrides.get('total_trades')
                                override_win_rate = display_overrides.get('win_rate_percent')
                                override_pnl = display_overrides.get('total_pnl_usdt')
                                override_fees = display_overrides.get('total_fees_usdt')

                                if override_trades is not None:
                                    total_trades = int(round(float(override_trades)))
                                if override_pnl is not None:
                                    total_pnl = float(override_pnl)
                                if override_fees is not None:
                                    total_fees = float(override_fees)

                                if override_win_rate is not None:
                                    win_rate = float(override_win_rate)
                                else:
                                    win_rate = (winning_trades / closed_trades * 100) if closed_trades > 0 else 0.0
                            except Exception:
                                win_rate = (winning_trades / closed_trades * 100) if closed_trades > 0 else 0.0

                            value_labels['total'].configure(text=f"{total_trades:,}건")
                            value_labels['win_rate'].configure(text=f"{win_rate:.1f}%")
                            value_labels['pnl'].configure(
                                text=f"{total_pnl:+,.2f}",
                                text_color=("#22c55e" if total_pnl >= 0 else "#ef4444"),
                            )
                            value_labels['fees'].configure(text=f"{total_fees:,.2f}")
                            status_label.configure(
                                text=(
                                    f"{prefix}{exchange.upper()} · 실제체결 {execution_count}건 · "
                                    f"청산성과 {closed_trades}건"
                                ),
                                text_color=self._color('text_secondary', '#9ca3af'),
                            )
                        else:
                            status_label.configure(text="통계 데이터 없음", text_color="#9ca3af")
                except Exception as ie:
                    status_label.configure(text=f"통계 오류: {ie}", text_color="#ef4444")
                # 주기 갱신
                try:
                    self._schedule_visible_refresh(parent, 5000, refresh_once)
                except Exception:
                    pass
            self._schedule_visible_refresh(parent, 200, refresh_once)
        except Exception as e:
            print(f"통계 섹션 생성 실패: {exchange} - {e}")

    def create_exchange_logs_section(self, parent, exchange: str):
        """거래소별 로그 영역(간단 출력) - 헤더 제거하고 로그 영역 최대화"""
        try:
            from ui.widgets.realtime_log_widget import RealtimeLogWidget  # 지연 임포트 (순환 방지)
            # 로그 스트림 사용: 대시보드 전역과 동일하게 in-memory 스트림을 기본 사용
            # 파일 tail 폴백 대신 스트림을 사용하여 거래소 탭에서도 즉시 갱신 보장
            try:
                from log_system.log_stream import get_log_stream  # 실시간 스트림
                _stream = get_log_stream()
            except Exception:
                _stream = None  # 폴백: 파일 기반 모드로 동작

            replay_log_file = self._get_dashboard_replay_log_file_path(exchange)
            if replay_log_file:
                # 방송 리플레이 모드에서는 소스 계정 로그 파일을 고정 표시한다.
                _stream = None

            # 로그 영역을 카드 프레임으로 감싸서 둥근 모서리가 명확히 보이도록 처리
            log_card = self._create_card_frame(parent, corner_radius=12)
            log_card.pack(fill="both", expand=True, padx=4, pady=(4, 8))

            # 거래소 필터 적용된 스트림 기반 로그 위젯 (자체 배경 투명/컨테이너투명 처리)
            widget = RealtimeLogWidget(
                log_card,
                logger=self.logger,
                log_stream=_stream,
                stream_exchange=exchange,
                log_file_override_path=replay_log_file,
                replay_playback_active_getter=lambda: bool(self.is_auto_trading),
                on_open_manual=lambda: self._open_manual_modal("업데이트"),
                # 카드 위에 직접 배치되는 프레임(자체)을 투명으로 두어 카드 모서리가 보이도록
                fg_color="#0b1120",
                corner_radius=12
            )
            widget.pack(fill="both", expand=True, padx=4, pady=4)
        except Exception as e:
            try:
                self.logger.warning(f"로그 섹션 생성 실패: {exchange} - {e}")
            except Exception:
                import logging
                logging.getLogger(__name__).warning(f"로그 섹션 생성 실패: {exchange} - {e}")

    # ========== 주식/증권 서비스 섹션 메서드들 (create_broker_*) ==========
    
    def create_broker_control_section(self, parent, broker: str):
        """증권사별 시작/정지 컨트롤 섹션 (블록체인 create_exchange_control_section 참고)"""
        try:
            title = ctk.CTkLabel(
                parent,
                text=f"{broker.upper()} 제어",
                font=self._get_safe_font("title"),
                text_color=self._color('text_primary', '#f9fafb')
            )
            title.pack(anchor="w", pady=(8, 6), padx=8)
            
            # 상태 표시 라벨
            status_label = ctk.CTkLabel(
                parent,
                text="연결 상태: 확인 중...",
                font=self._get_safe_font("body"),
                text_color=self._color('text_secondary', '#9ca3af'),
                justify="left",
                anchor="w",
                wraplength=520
            )
            status_label.pack(anchor="w", padx=8, pady=(0, 8))
            
            # 제어 버튼 프레임
            button_frame = ctk.CTkFrame(parent, fg_color="transparent")
            button_frame.pack(fill="x", padx=8, pady=(0, 8))
            
            # 시작/정지 토글 버튼
            def toggle_broker():
                try:
                    # 어댑터 가져오기
                    adapter = self._get_stock_adapter(broker)
                    if not adapter:
                        self.logger.error(f"어댑터를 찾을 수 없음: {broker}")
                        messagebox.showerror("오류", f"증권사 어댑터를 찾을 수 없습니다: {broker}")
                        return
                    
                    current_text = toggle_btn.cget("text")
                    if "시작" in current_text:
                        # 연결 시도
                        result = adapter.connect()
                        if result:
                            toggle_btn.configure(text="⏸ 정지", fg_color=self._color('danger', '#dc2626'))
                            status_label.configure(text="연결 상태: 연결됨", text_color=self._color('success', '#10b981'))
                            self.logger.info(f"{broker} 연결 성공")
                        else:
                            messagebox.showerror("오류", f"{broker} 연결에 실패했습니다")
                            self.logger.error(f"{broker} 연결 실패")
                    else:
                        # 연결 해제
                        if hasattr(adapter, 'disconnect'):
                            adapter.disconnect()
                        toggle_btn.configure(text="▶ 시작", fg_color=self._color('success', '#10b981'))
                        status_label.configure(text="연결 상태: 미연결", text_color=self._color('text_secondary', '#9ca3af'))
                        self.logger.info(f"{broker} 연결 해제")
                except Exception as e:
                    self.logger.error(f"증권사 토글 오류: {e}")
                    messagebox.showerror("오류", f"작업 처리 중 오류가 발생했습니다: {e}")
            
            toggle_btn = ctk.CTkButton(
                button_frame,
                text="▶ 시작",
                command=toggle_broker,
                fg_color=self._color('success', '#10b981'),
                hover_color=self._hover_from(self._color('success', '#10b981')),
                width=110,
                height=36,
                corner_radius=12
            )
            toggle_btn.pack(side="left", padx=(0, 6))
            
            # 새로고침 버튼
            refresh_btn = ctk.CTkButton(
                button_frame,
                text="새로고침",
                command=lambda: self._refresh_broker_data(broker),
                width=110,
                height=36,
                corner_radius=12
            )
            refresh_btn.pack(side="left")
            
            # 상태 라벨 저장 (나중에 업데이트용)
            if not hasattr(self, 'broker_status_labels'):
                self.broker_status_labels = {}
            self.broker_status_labels[broker] = status_label
            
        except Exception as e:
            print(f"제어 섹션 생성 실패: {broker} - {e}")

    def create_broker_balance_section(self, parent, broker: str):
        """증권사별 잔고를 3열 미니 카드로 표시한다."""
        try:
            header = ctk.CTkFrame(parent, fg_color="transparent")
            header.pack(fill="x", padx=10, pady=(7, 3))
            ctk.CTkLabel(
                header, text="잔고", font=self._get_safe_font("title"),
                text_color=self._color('text_primary', '#f9fafb'),
            ).pack(side="left")
            status_label = ctk.CTkLabel(
                header, text="7초 자동 갱신", font=self._get_safe_font("small"),
                text_color=self._color('text_secondary', '#94a3b8'),
            )
            status_label.pack(side="right")

            grid = ctk.CTkFrame(parent, fg_color="transparent")
            grid.pack(fill="x", padx=8, pady=(0, 7))
            grid.grid_columnconfigure((0, 1, 2), weight=1, uniform=f"{broker}_balance")
            value_pairs = []
            for index in range(3):
                card = ctk.CTkFrame(
                    grid, height=48, fg_color="#111827", corner_radius=9,
                    border_width=1, border_color="#334155",
                )
                card.grid(row=0, column=index, sticky="ew", padx=3)
                card.grid_propagate(False)
                title_label = ctk.CTkLabel(
                    card, text="-", font=self._get_safe_font("small"), text_color="#94a3b8",
                )
                title_label.pack(anchor="w", padx=8, pady=(3, 0))
                value_label = ctk.CTkLabel(
                    card, text="탭 열면 조회", font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="#e2e8f0",
                )
                value_label.pack(anchor="w", padx=8, pady=(0, 3))
                value_pairs.append((title_label, value_label))
            
            # 레퍼런스 저장
            if not hasattr(self, 'broker_section_widgets'):
                self.broker_section_widgets = {}
            widgets = self.broker_section_widgets.setdefault(broker, {})
            widgets['balance_label'] = status_label
            widgets['balance_status'] = status_label
            widgets['balance_values'] = value_pairs
            self._set_balance_metric_state(widgets, "탭 열면 조회")
            status_label.configure(text="조회 대기", text_color="#94a3b8")
            
            # 즉시 1회 업데이트
            def refresh_once():
                def _load_balance():
                    adapter = self._get_stock_adapter(broker)
                    if adapter and hasattr(adapter, 'get_balance'):
                        return {"status": "success", "balance": adapter.get_balance()}
                    return {"status": "client_unavailable", "message": "어댑터 미연결"}

                def _apply_balance(result):
                    payload = result if isinstance(result, dict) else {}
                    if payload.get("status") == "success" and payload.get("balance"):
                        self._update_balance_metric_widgets(
                            widgets,
                            broker,
                            payload.get("balance"),
                        )
                        status_label.configure(
                            text=f"{broker.upper()} · 7초 갱신",
                            text_color="#94a3b8",
                        )
                    else:
                        message = self._balance_status_message(payload)
                        self._set_balance_metric_state(widgets, message)
                        status_label.configure(text=message, text_color="#f59e0b")

                def _apply_balance_error(ie):
                    self._set_balance_metric_state(widgets, "조회 지연/오류")
                    status_label.configure(text=f"잔고 오류: {str(ie)[:22]}", text_color="#ef4444")

                status_label.configure(text="잔고 조회 중", text_color="#60a5fa")
                self._run_visible_refresh_async(
                    parent,
                    f"broker_balance:{broker}",
                    _load_balance,
                    _apply_balance,
                    _apply_balance_error,
                )
                try:
                    self._schedule_visible_refresh(parent, 7000, refresh_once)
                except Exception:
                    pass
            self._schedule_visible_refresh(parent, 100, refresh_once)
            
        except Exception as e:
            print(f"잔고 섹션 생성 실패: {broker} - {e}")

    def create_broker_positions_section(self, parent, broker: str):
        """증권사별 보유 종목을 압축 카드 목록으로 표시한다."""
        try:
            header = ctk.CTkFrame(parent, fg_color="transparent")
            header.pack(fill="x", padx=10, pady=(7, 3))
            ctk.CTkLabel(
                header, text="보유 종목", font=self._get_safe_font("title"),
                text_color=self._color('text_primary', '#f9fafb'),
            ).pack(side="left")
            count_label = ctk.CTkLabel(
                header, text="조회 중", font=self._get_safe_font("small"), text_color="#60a5fa",
            )
            count_label.pack(side="right")

            body = ctk.CTkScrollableFrame(
                parent, fg_color="#0b1120", corner_radius=9,
                border_color="#1f2937", border_width=1,
            )
            body.pack(fill="both", expand=True, padx=8, pady=(0, 7))
            
            # 레퍼런스 저장
            widgets = self.broker_section_widgets.setdefault(broker, {})
            widgets['positions_body'] = body
            widgets['positions_count'] = count_label
            self._render_position_cards(
                body, count_label, [], empty_text="보유 종목 조회 중", quote="KRW", stock_mode=True,
            )
            
            # 즉시 1회 업데이트
            def refresh_once():
                try:
                    def _load_positions():
                        adapter = self._get_stock_adapter(broker)
                        if adapter and hasattr(adapter, 'get_positions'):
                            return adapter.get_positions()
                        return None

                    def _apply_positions(positions):
                        if positions is not None:
                            self._render_position_cards(
                                body, count_label, positions, empty_text="보유 종목 없음",
                                quote="KRW", stock_mode=True,
                            )
                        else:
                            self._render_position_cards(
                                body, count_label, [], empty_text="어댑터 미연결",
                                quote="KRW", stock_mode=True,
                            )

                    def _apply_positions_error(ie):
                        self._render_position_cards(
                            body, count_label, [], empty_text=f"보유 종목 오류: {str(ie)[:28]}",
                            quote="KRW", stock_mode=True,
                        )
                        count_label.configure(text="조회 오류", text_color="#ef4444")

                    self._run_visible_refresh_async(
                        parent,
                        f"broker_positions:{broker}",
                        _load_positions,
                        _apply_positions,
                        _apply_positions_error,
                    )
                except Exception as ie:
                    self._render_position_cards(
                        body, count_label, [], empty_text=f"보유 종목 오류: {str(ie)[:28]}",
                        quote="KRW", stock_mode=True,
                    )
                    count_label.configure(text="조회 오류", text_color="#ef4444")
                # 주기 갱신
                try:
                    self._schedule_visible_refresh(parent, 5000, refresh_once)
                except Exception:
                    pass
            self._schedule_visible_refresh(parent, 200, refresh_once)
            
        except Exception as e:
            print(f"포지션 섹션 생성 실패: {broker} - {e}")

    def create_broker_stats_section(self, parent, broker: str):
        """증권사별 핵심 통계를 슬림한 한 줄 4열 KPI 카드로 표시한다."""
        try:
            header = ctk.CTkFrame(parent, fg_color="transparent")
            header.pack(fill="x", padx=10, pady=(4, 1))
            ctk.CTkLabel(
                header, text="거래 통계", font=self._get_safe_font("title"),
                text_color=self._color('text_primary', '#f9fafb')
            ).pack(side="left")
            status_label = ctk.CTkLabel(
                header, text="체결 기준", font=self._get_safe_font("small"),
                text_color=self._color('text_secondary', '#9ca3af'),
            )
            status_label.pack(side="right")

            grid = ctk.CTkFrame(parent, fg_color="transparent")
            grid.pack(fill="both", expand=True, padx=8, pady=(0, 4))
            grid.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform=f"{broker}_stats")
            grid.grid_rowconfigure(0, weight=1)

            value_labels = {}
            specs = (
                ("total", "총 거래", "0건", "#60a5fa"),
                ("today", "오늘 체결", "0건", "#22c55e"),
                ("pnl", "실현손익", "0", "#f59e0b"),
                ("open_orders", "미체결", "0건", "#c084fc"),
            )
            for index, (key, title_text, initial, accent) in enumerate(specs):
                card = ctk.CTkFrame(
                    grid, fg_color="#111827", corner_radius=10,
                    border_width=1, border_color="#334155",
                )
                card.grid(row=0, column=index, sticky="nsew", padx=3, pady=3)
                ctk.CTkLabel(
                    card, text=title_text, font=ctk.CTkFont(size=10),
                    text_color=self._color('text_secondary', '#9ca3af'),
                ).pack(anchor="w", padx=7, pady=(2, 0))
                value = ctk.CTkLabel(
                    card, text=initial, font=ctk.CTkFont(size=13, weight="bold"),
                    text_color=accent,
                )
                value.pack(anchor="w", padx=7, pady=(0, 2))
                value_labels[key] = value

            # 레퍼런스 저장
            widgets = self.broker_section_widgets.setdefault(broker, {})
            widgets['stats_label'] = status_label
            widgets['stats_values'] = value_labels
            
            # 즉시 1회 업데이트
            def refresh_once():
                try:
                    # 어댑터에서 거래 통계 조회
                    adapter = self._get_stock_adapter(broker)
                    if adapter:
                        stats = adapter.get_trading_stats() if hasattr(adapter, 'get_trading_stats') else {}
                        stats = stats if isinstance(stats, dict) else {}
                        total_trades = int(stats.get('total_trades', 0) or 0)
                        today_count = int(stats.get('today_trades', stats.get('today_count', 0)) or 0)
                        open_orders = int(stats.get('open_orders', stats.get('open_orders_count', 0)) or 0)
                        realized_pnl = float(stats.get('realized_pnl', 0) or 0)
                        if hasattr(adapter, 'get_today_trades'):
                            today_trades = adapter.get_today_trades()
                            if isinstance(today_trades, list):
                                today_count = len(today_trades)

                        value_labels['total'].configure(text=f"{total_trades:,}건")
                        value_labels['today'].configure(text=f"{today_count:,}건")
                        value_labels['pnl'].configure(
                            text=f"{realized_pnl:+,.0f}",
                            text_color=("#22c55e" if realized_pnl >= 0 else "#ef4444"),
                        )
                        value_labels['open_orders'].configure(text=f"{open_orders:,}건")
                        status_label.configure(
                            text=f"{broker.upper()} · 체결 기준",
                            text_color=self._color('text_secondary', '#9ca3af'),
                        )
                    else:
                        status_label.configure(text="어댑터 미연결", text_color="#f59e0b")
                except Exception as ie:
                    status_label.configure(text=f"통계 오류: {ie}", text_color="#ef4444")
                # 주기 갱신
                try:
                    self._schedule_visible_refresh(parent, 5000, refresh_once)
                except Exception:
                    pass
            self._schedule_visible_refresh(parent, 200, refresh_once)
            
        except Exception as e:
            print(f"통계 섹션 생성 실패: {broker} - {e}")

    def create_broker_logs_section(self, parent, broker: str):
        """증권사별 로그 섹션 (블록체인 create_exchange_logs_section 참고)"""
        try:
            from ui.widgets.realtime_log_widget import RealtimeLogWidget  # 지연 임포트 (순환 방지)
            # 로그 스트림 사용: 대시보드 전역과 동일하게 in-memory 스트림을 기본 사용
            try:
                from log_system.log_stream import get_log_stream  # 실시간 스트림
                _stream = get_log_stream()
            except Exception:
                _stream = None  # 폴백: 파일 기반 모드로 동작
            
            # 로그 영역을 카드 프레임으로 감싸서 둥근 모서리가 명확히 보이도록 처리
            log_card = self._create_card_frame(parent, corner_radius=12)
            log_card.pack(fill="both", expand=True, padx=4, pady=(4, 8))

            # 증권사 필터 적용된 스트림 기반 로그 위젯
            widget = RealtimeLogWidget(
                log_card,
                logger=self.logger,
                log_stream=_stream,
                stream_exchange=broker,  # 증권사 필터로 사용
                on_open_manual=lambda: self._open_manual_modal("업데이트"),
                fg_color="#0b1120",
                corner_radius=12
            )
            widget.pack(fill="both", expand=True, padx=4, pady=4)
        except Exception as e:
            try:
                self.logger.warning(f"증권사 로그 섹션 생성 실패: {broker} - {e}")
            except Exception:
                import logging
                logging.getLogger(__name__).warning(f"증권사 로그 섹션 생성 실패: {broker} - {e}")
    
    def _get_stock_adapter(self, broker: str):
        """
        증권사 어댑터를 가져옵니다 (캐싱)
        
        Args:
            broker: 증권사명 ('kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment')
        
        Returns:
            증권사 어댑터 인스턴스 또는 None
        """
        try:
            # 이미 캐시된 어댑터가 있으면 반환
            if self.stock_adapters.get(broker) is not None:
                return self.stock_adapters[broker]
            
            # 설정에서 해당 증권사가 활성화되어 있는지 확인
            enabled_brokers = self.settings.get('enabled_stock_brokers', [])
            if broker not in enabled_brokers:
                self.logger.warning(f"증권사가 비활성화됨: {broker}")
                return None
            
            # 팩토리를 사용해 어댑터 생성
            adapter = ExchangeFactory.create_stock_exchange(broker, self.settings)
            if adapter:
                self.stock_adapters[broker] = adapter
                self.logger.info(f"증권사 어댑터 생성됨: {broker}")
            else:
                self.logger.error(f"증권사 어댑터 생성 실패: {broker}")
            
            return adapter
            
        except Exception as e:
            self.logger.error(f"어댑터 조회 오류 ({broker}): {e}")
            return None
    
    def _refresh_broker_data(self, broker: str):
        """증권사 데이터 새로고침"""
        try:
            if not hasattr(self, 'broker_section_widgets') or broker not in self.broker_section_widgets:
                return

            widgets = self.broker_section_widgets[broker]
            adapter = self._get_stock_adapter(broker)
            if not adapter:
                if 'balance_status' in widgets:
                    widgets['balance_status'].configure(text="어댑터 미연결", text_color="#f59e0b")
                if 'positions_body' in widgets and 'positions_count' in widgets:
                    self._render_position_cards(
                        widgets['positions_body'], widgets['positions_count'], [],
                        empty_text="어댑터 미연결", quote="KRW", stock_mode=True,
                    )
                if 'stats_label' in widgets:
                    widgets['stats_label'].configure(text=f"{broker.upper()} 통계: 어댑터 미연결")
                return

            # 연결 상태가 내려가 있으면 1회 연결 시도
            try:
                if hasattr(adapter, 'is_connected') and not bool(getattr(adapter, 'is_connected', False)) and hasattr(adapter, 'connect'):
                    adapter.connect()
            except Exception:
                pass

            # 잔고
            if 'balance_values' in widgets:
                try:
                    balance = adapter.get_balance() if hasattr(adapter, 'get_balance') else {}
                    if isinstance(balance, dict) and balance:
                        self._update_balance_metric_widgets(widgets, broker, balance)
                        widgets['balance_status'].configure(text=f"{broker.upper()} · 갱신 완료", text_color="#94a3b8")
                    else:
                        widgets['balance_status'].configure(text="조회 불가", text_color="#f59e0b")
                except Exception as e:
                    widgets['balance_status'].configure(text=f"잔고 오류: {str(e)[:22]}", text_color="#ef4444")

            # 포지션
            if 'positions_body' in widgets and 'positions_count' in widgets:
                try:
                    positions = adapter.get_positions() if hasattr(adapter, 'get_positions') else []
                    self._render_position_cards(
                        widgets['positions_body'], widgets['positions_count'], positions,
                        empty_text="보유 종목 없음", quote="KRW", stock_mode=True,
                    )
                except Exception as e:
                    self._render_position_cards(
                        widgets['positions_body'], widgets['positions_count'], [],
                        empty_text=f"보유 종목 오류: {str(e)[:28]}", quote="KRW", stock_mode=True,
                    )
                    widgets['positions_count'].configure(text="조회 오류", text_color="#ef4444")

            # 통계
            if 'stats_label' in widgets:
                try:
                    stats = adapter.get_trading_stats() if hasattr(adapter, 'get_trading_stats') else {}
                    total_trades = 0
                    open_orders = 0
                    realized_pnl = 0.0
                    today_count = 0
                    if isinstance(stats, dict) and stats:
                        total_trades = int(stats.get('total_trades', 0) or 0)
                        open_orders = int(stats.get('open_orders', stats.get('open_orders_count', 0)) or 0)
                        realized_pnl = float(stats.get('realized_pnl', 0) or 0)
                        today_count = int(stats.get('today_trades', stats.get('today_count', 0)) or 0)
                    if hasattr(adapter, 'get_today_trades'):
                        today_trades = adapter.get_today_trades() or []
                        if isinstance(today_trades, list):
                            today_count = len(today_trades)
                    values = widgets.get('stats_values', {})
                    if values:
                        values['total'].configure(text=f"{total_trades:,}건")
                        values['today'].configure(text=f"{today_count:,}건")
                        values['pnl'].configure(
                            text=f"{realized_pnl:+,.0f}",
                            text_color=("#22c55e" if realized_pnl >= 0 else "#ef4444"),
                        )
                        values['open_orders'].configure(text=f"{open_orders:,}건")
                    widgets['stats_label'].configure(
                        text=f"{broker.upper()} · 체결 기준",
                        text_color=self._color('text_secondary', '#9ca3af'),
                    )
                except Exception as e:
                    widgets['stats_label'].configure(text=f"통계 오류: {e}", text_color="#ef4444")

        except Exception as e:
            self.logger.error(f"증권사 데이터 새로고침 실패: {broker} - {e}")

    def show_blockchain_content(self):
        """블록체인 서비스 콘텐츠 표시: 거래통계/시장트렌드 탭 내용을 블록체인용으로 재빌드"""
        try:
            # 공통 메인 탭이 삭제된 경우(다른 서비스 전환 이후) 재생성
            try:
                if not self._tab_exists("실시간 거래 로그"):
                    self.create_main_content()
            except Exception:
                pass

            # 블록체인 서비스 공통 탭 보장
            try:
                self._ensure_coin_info_tab()
                self._ensure_ai_learning_tab()
                self._ensure_ai_report_tab()
                self._ensure_ai_assistant_tab()
            except Exception as e:
                self.logger.warning(f"블록체인 공통 탭 보장 중 일부 실패: {e}")

            # 탭 내용 재빌드 (blockchain→stock→blockchain 전환 시 잘못된 내용 방지)
            self._ensure_trading_stats_tab()
            self._ensure_trend_tab()
            self._ensure_financial_intelligence_tab("blockchain")

            # Alpha Arena 탭 생성 (블록체인 서비스에 포함, 설정에서 활성화된 경우에만)
            try:
                self._ensure_alpha_arena_tab()
            except Exception:
                # Alpha Arena 탭 생성 실패는 무시 (설정에서 비활성화되었거나 오류)
                pass

            if hasattr(self, 'tab_widget') and self.tab_widget is not None:
                tv = cast(ctk.CTkTabview, self.tab_widget)
                preferred = "실시간 거래 로그"
                try:
                    tv.set(preferred)
                except Exception:
                    pass
            self.logger.info("블록체인 서비스 전환 완료 (탭 재빌드)")
        except Exception as e:
            self.logger.error(f"블록체인 서비스 전환 오류: {e}")

    def show_stock_content(self):
        """주식/증권 서비스 콘텐츠 표시: 기본 탭을 주식용으로 교체"""
        try:
            self.logger.info("주식/증권 서비스 콘텐츠 표시 시작")

            # 공통 메인 탭이 삭제된 경우(다른 서비스 전환 이후) 재생성
            try:
                if not self._tab_exists("실시간 거래 로그"):
                    self.create_main_content()
            except Exception:
                pass
            
            # 주식용 기본 탭 생성/교체
            # 주의: CTkTabview는 탭을 직접 제거할 수 없으므로, 
            # "코인 정보"와 "종목 정보"는 별도 탭으로 존재할 수 있음
            # 향후 개선: 탭 이름을 동적으로 변경하거나, 같은 탭 이름을 사용하되 내용만 교체
            try:
                # 공통 탭 보장 (다른 서비스에서 제거되었을 수 있음)
                self._ensure_ai_learning_tab()
                self._ensure_ai_report_tab()
                self._ensure_ai_assistant_tab()

                # "종목 정보" 탭 생성 (기존 "코인 정보"와 별도)
                self._ensure_stock_info_tab()
                # "거래 통계"는 이미 존재하지만 내용을 주식용으로 교체
                self._ensure_stock_trading_stats_tab()
                # "시장 트렌드"는 이미 존재하지만 내용을 주식용으로 교체
                self._ensure_stock_trend_tab()
                # 공통 엔진 기반 재무·가치평가·스크리너·백테스트
                self._ensure_financial_intelligence_tab("stock")
            except Exception as e:
                self.logger.warning(f"주식용 탭 생성 중 일부 실패: {e}")
            
            # 기본 탭 선택
            if hasattr(self, 'tab_widget') and self.tab_widget is not None:
                tv = cast(ctk.CTkTabview, self.tab_widget)
                preferred = "실시간 거래 로그"  # 주식/증권 서비스에서도 공통 로그 탭을 기본으로
                try:
                    tv.set(preferred)
                except Exception:
                    pass  # Fallback to first tab if preferred not found

            # 증권 자동매매 루프 예약 시작
            # - auto_start(enabled legacy)=True: 탭 진입 시 루프 예약 시작
            # - 실주문/실행 자체는 START/STOP(AUTO) 상태에서만 동작
            self._start_stock_auto_trade_loop(force=False)
            self.logger.info("주식/증권 서비스 전환 완료 (탭 교체됨)")
        except Exception as e:
            self.logger.error(f"주식/증권 서비스 전환 오류: {e}")

    def show_real_estate_content(self):
        """자산 통합 인사이트 서비스 콘텐츠 표시 (자산군별 통합 분석)"""
        try:
            if hasattr(self, 'tab_widget') and self.tab_widget is not None:
                tv = cast(ctk.CTkTabview, self.tab_widget)
                tab_name = "자산 통합 인사이트"
                tab = self._get_or_add_tab(tab_name)
                self._clear_tab_children(tab)

                # 탭 내용 생성 (스크롤 가능)
                scroll_frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
                scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
                saved_profile = self._get_life_finance_profile()

                # ===== 1. 통합 자산 현황 =====
                summary_card = ctk.CTkFrame(scroll_frame, fg_color="#1a1f2e", corner_radius=12, border_width=2, border_color="#374151")
                summary_card.pack(fill="x", padx=5, pady=10)

                summary_title = ctk.CTkLabel(
                    summary_card,
                    text="통합 자산 현황",
                    font=self._get_safe_font("subtitle"),
                    text_color="#fbbf24"
                )
                summary_title.pack(anchor="w", padx=15, pady=(12, 0))

                # 현재 계좌 잔고와 종료 거래 손익을 분리해 수집한다.
                metrics = self._collect_asset_insight_metrics()
                self._refresh_asset_insight_balances_async(tab)
                db_path = self._get_dashboard_read_db_path()
                total_assets = float(metrics.get('total_assets', 0.0) or 0.0)
                total_pnl = float(metrics.get('total_pnl', 0.0) or 0.0)
                asset_breakdown = dict(metrics.get('asset_breakdown', {}) or {})
                display_currency = metrics.get('display_currency')
                currency_totals = dict(metrics.get('currency_totals', {}) or {})
                asset_by_currency = dict(metrics.get('asset_breakdown_by_currency', {}) or {})
                has_current_data = bool(metrics.get('has_current_data'))
                allocation_comparable = bool(metrics.get('allocation_comparable'))
                unvalued_assets = list(metrics.get('unvalued_assets', []) or [])
                from ui.asset_insight_data import format_money

                # 통계 표시
                if not has_current_data:
                    stats_content = "현재 잔고 미수신 | 블록체인 또는 주식/증권 계좌에서 잔고를 먼저 조회하세요."
                elif allocation_comparable:
                    sign = '+' if total_pnl >= 0 else '-'
                    stats_content = (
                        f"현재 자산: {format_money(total_assets, display_currency)} | "
                        f"종료 거래 실현손익(가져오기 제외): {sign}{format_money(abs(total_pnl), display_currency)}"
                    )
                else:
                    totals_text = " · ".join(
                        format_money(float(amount or 0.0), currency)
                        for currency, amount in sorted(currency_totals.items())
                    )
                    stats_content = f"현재 자산(통화별): {totals_text} | 환율 없이 통합 합계 미계산"
                if unvalued_assets:
                    stats_content += f" | 시세 미환산 보유자산 {len(unvalued_assets)}종"
                stats_label = ctk.CTkLabel(
                    summary_card,
                    text=stats_content,
                    font=self._get_safe_font("body"),
                    text_color="#cbd5e1"
                )
                stats_label.pack(anchor="w", padx=15, pady=(8, 12))

                snapshot_state = self._get_saved_asset_snapshot()
                snapshot_frame = ctk.CTkFrame(summary_card, fg_color="transparent")
                snapshot_frame.pack(fill="x", padx=15, pady=(0, 12))

                snapshot_status = ctk.CTkLabel(
                    snapshot_frame,
                    text="저장된 자산 스냅샷이 없습니다.",
                    font=self._get_safe_font("small"),
                    text_color="#9ca3af"
                )
                snapshot_status.pack(side="left", padx=(0, 10))

                def refresh_snapshot_label(snapshot: Optional[Dict[str, Any]] = None):
                    current_snapshot = snapshot or self._get_saved_asset_snapshot()
                    saved_at = str(current_snapshot.get('saved_at', '') or '').strip()
                    if not saved_at:
                        snapshot_status.configure(text="저장된 자산 스냅샷이 없습니다.", text_color="#9ca3af")
                        return

                    snapshot_totals = current_snapshot.get('currency_totals', {})
                    if isinstance(snapshot_totals, dict) and snapshot_totals:
                        saved_values = " · ".join(
                            format_money(float(amount or 0.0), currency)
                            for currency, amount in sorted(snapshot_totals.items())
                        )
                        snapshot_text = f"마지막 저장: {saved_at} | {saved_values}"
                    else:
                        snapshot_total = float(current_snapshot.get('total_assets', 0) or 0)
                        snapshot_currency = current_snapshot.get('display_currency') or 'KRW'
                        snapshot_text = f"마지막 저장: {saved_at} | {format_money(snapshot_total, snapshot_currency)}"
                    snapshot_status.configure(text=snapshot_text, text_color="#cbd5e1")

                def save_asset_snapshot():
                    snapshot = {
                        'saved_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'total_assets': total_assets,
                        'total_pnl': total_pnl,
                        'asset_breakdown': dict(asset_breakdown),
                        'asset_breakdown_by_currency': asset_by_currency,
                        'currency_totals': currency_totals,
                        'display_currency': display_currency,
                        'stock_asset_mode': self._get_stock_asset_mode(),
                    }
                    if self._save_asset_snapshot(snapshot):
                        refresh_snapshot_label(snapshot)
                    else:
                        snapshot_status.configure(text="자산 스냅샷 저장 실패", text_color="#ef4444")

                snapshot_button = ctk.CTkButton(
                    snapshot_frame,
                    text="현재 상태 저장",
                    command=save_asset_snapshot,
                    font=self._get_safe_font("button"),
                    width=130
                )
                snapshot_button.pack(side="right")
                refresh_snapshot_label(snapshot_state)

                # ===== 2. 자산군별 비중 =====
                allocation_card = ctk.CTkFrame(scroll_frame, fg_color="#1a1f2e", corner_radius=12, border_width=2, border_color="#374151")
                allocation_card.pack(fill="x", padx=5, pady=10)

                alloc_title = ctk.CTkLabel(
                    allocation_card,
                    text="자산군별 비중",
                    font=self._get_safe_font("subtitle"),
                    text_color="#fbbf24"
                )
                alloc_title.pack(anchor="w", padx=15, pady=(12, 8))

                # 자산군별 비중 표시
                for asset_type, amount in asset_breakdown.items():
                    if total_assets > 0:
                        percentage = (amount / total_assets) * 100
                    else:
                        percentage = 0

                    # 색상 지정
                    if asset_type == "암호화폐":
                        color = "#8b5cf6"
                        icon = "₿"
                    elif asset_type == "주식":
                        color = "#06b6d4"
                        icon = ""
                    else:
                        color = "#84cc16"
                        icon = ""

                    alloc_row = ctk.CTkFrame(allocation_card, fg_color="transparent")
                    alloc_row.pack(fill="x", padx=15, pady=6)

                    if allocation_comparable:
                        amount_text = format_money(amount, display_currency)
                        label_text = f"{icon} {asset_type}: {percentage:.1f}% ({amount_text})"
                    else:
                        per_currency = dict(asset_by_currency.get(asset_type, {}) or {})
                        amount_text = " · ".join(
                            format_money(float(value or 0.0), currency)
                            for currency, value in sorted(per_currency.items())
                        ) or "잔고 없음"
                        label_text = f"{icon} {asset_type}: 비중 미계산 ({amount_text})"
                    alloc_label = ctk.CTkLabel(
                        alloc_row,
                        text=label_text,
                        font=self._get_safe_font("body"),
                        text_color=color
                    )
                    alloc_label.pack(anchor="w")

                    # 진행 바
                    progress_bar = ctk.CTkFrame(alloc_row, fg_color="#0b1120", height=8, corner_radius=4)
                    progress_bar.pack(fill="x", pady=(4, 0))

                    filled_bar = ctk.CTkFrame(progress_bar, fg_color=color, height=8, corner_radius=4)
                    filled_bar.pack(side="left", fill="x", expand=False)
                    filled_bar.configure(width=int(percentage * 2))

                concentration = float(metrics.get('concentration', 0.0) or 0.0)
                concentration_level = str(metrics.get('concentration_level', '데이터 부족') or '데이터 부족')
                corr_value = metrics.get('corr_value')
                corr_label = str(metrics.get('corr_label', '데이터 없음') or '데이터 없음')

                # ===== 3. 포트폴리오 리스크 요약 =====
                risk_card = ctk.CTkFrame(scroll_frame, fg_color="#1a1f2e", corner_radius=12, border_width=2, border_color="#374151")
                risk_card.pack(fill="x", padx=5, pady=10)

                risk_title = ctk.CTkLabel(
                    risk_card,
                    text="리스크 요약",
                    font=self._get_safe_font("subtitle"),
                    text_color="#fbbf24"
                )
                risk_title.pack(anchor="w", padx=15, pady=(12, 8))

                # 리스크 지표
                corr_text = f"{corr_value:+.2f}" if corr_value is not None else "N/A"
                risk_items = [
                    (
                        "포트폴리오 집중도",
                        f"{concentration:.1f}/100 ({concentration_level})",
                        "#ef4444" if concentration >= 60 else "#fbbf24" if concentration >= 45 else "#22c55e",
                    ),
                    (
                        "종료 거래 실현손익(가져오기 제외)",
                        (("+" if total_pnl >= 0 else "-") + format_money(abs(total_pnl), display_currency))
                        if display_currency else "통화별 확인",
                        "#ef4444" if total_pnl < 0 else "#22c55e",
                    ),
                    (
                        "자산군 상관계수(crypto-stock)",
                        f"{corr_text} ({corr_label})",
                        "#ef4444" if corr_value is not None and abs(corr_value) >= 0.7 else "#9ca3af",
                    ),
                ]

                for title, value, color in risk_items:
                    risk_row = ctk.CTkFrame(risk_card, fg_color="transparent")
                    risk_row.pack(fill="x", padx=15, pady=6)

                    risk_label = ctk.CTkLabel(
                        risk_row,
                        text=f"{title}: {value}",
                        font=self._get_safe_font("body"),
                        text_color=color
                    )
                    risk_label.pack(anchor="w")

                # ===== 4. 추천 액션 =====
                action_card = ctk.CTkFrame(scroll_frame, fg_color="#1a1f2e", corner_radius=12, border_width=2, border_color="#374151")
                action_card.pack(fill="x", padx=5, pady=10)

                action_title = ctk.CTkLabel(
                    action_card,
                    text="추천 액션",
                    font=self._get_safe_font("subtitle"),
                    text_color="#fbbf24"
                )
                action_title.pack(anchor="w", padx=15, pady=(12, 8))

                actions = list(metrics.get('actions', []) or [])

                for action in actions:
                    action_label = ctk.CTkLabel(
                        action_card,
                        text=action,
                        font=self._get_safe_font("body"),
                        text_color="#cbd5e1",
                        wraplength=400,
                        justify="left"
                    )
                    action_label.pack(anchor="w", padx=15, pady=5)

                # 탭 선택
                try:
                    tv.set(tab_name)
                except Exception:
                    pass
                self.logger.info("자산 통합 인사이트 실제 데이터 패널 표시")

        except Exception as e:
            self.logger.error(f"자산 통합 인사이트 서비스 화면 표시 오류: {e}")


    def show_other_investment_content(self):
        """생활금융 서비스 콘텐츠 표시 (수입/지출 입력 + 월간 리포트)"""
        try:
            if hasattr(self, 'tab_widget') and self.tab_widget is not None:
                tv = cast(ctk.CTkTabview, self.tab_widget)
                tab_name = "생활금융 서비스"
                self._ensure_life_finance_tab()
                try:
                    tv.set(tab_name)
                except Exception:
                    pass
                self.logger.info("생활금융 실행형 위젯 화면 표시")

        except Exception as e:
            self.logger.error(f"생활금융 서비스 화면 표시 오류: {e}")


    def show_ai_analyst_content(self):
        """AI 애널리스트 서비스 콘텐츠 표시"""
        try:
            if hasattr(self, 'tab_widget') and self.tab_widget is not None:
                tv = cast(ctk.CTkTabview, self.tab_widget)
                tab_name = "AI 애널리스트"
                tab = self._get_or_add_tab(tab_name)
                self._clear_tab_children(tab)

                # 메인 컨테이너 (스크롤 가능)
                scroll = ctk.CTkScrollableFrame(tab, fg_color="#0b1120", corner_radius=0)
                scroll.pack(fill="both", expand=True, padx=0, pady=0)

                # ── 헤더 ──
                header = ctk.CTkFrame(scroll, fg_color="#0f1f3d", corner_radius=12)
                header.pack(fill="x", padx=12, pady=(12, 8))
                ctk.CTkLabel(header, text="AI 통합 애널리스트",
                             font=ctk.CTkFont(size=22, weight="bold"),
                             text_color="#60a5fa").pack(anchor="w", padx=16, pady=(12, 2))
                ctk.CTkLabel(header,
                             text="보유 자산·현재 포지션·시장 지표를 종합하여 AI가 맞춤 투자 분석을 제공합니다.",
                             font=ctk.CTkFont(size=13), text_color="#9ca3af").pack(anchor="w", padx=16, pady=(0, 12))

                # ── 핵심 지표 스냅샷 ──
                snapshot = self._collect_ai_analyst_snapshot_metrics()
                snapshot_grid = ctk.CTkFrame(scroll, fg_color="#0b1120")
                snapshot_grid.pack(fill="x", padx=12, pady=(0, 8))
                snapshot_grid.grid_columnconfigure((0, 1, 2, 3), weight=1)

                def _snapshot_card(parent, row, col, label, value, tone: str = "neutral"):
                    tone_map = {
                        "good": "#22c55e",
                        "warn": "#f59e0b",
                        "bad": "#ef4444",
                        "neutral": "#60a5fa",
                    }
                    card = ctk.CTkFrame(parent, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
                    card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
                    ctk.CTkLabel(
                        card,
                        text=label,
                        font=self._get_safe_font("small"),
                        text_color="#9ca3af",
                    ).pack(anchor="w", padx=10, pady=(8, 2))
                    ctk.CTkLabel(
                        card,
                        text=value,
                        font=self._get_safe_font("subtitle"),
                        text_color=tone_map.get(tone, "#60a5fa"),
                    ).pack(anchor="w", padx=10, pady=(0, 8))

                _snapshot_card(snapshot_grid, 0, 0, "종료 거래", f"{snapshot['closed_trades']}건")
                _snapshot_card(
                    snapshot_grid,
                    0,
                    1,
                    "승률",
                    f"{snapshot['win_rate']:.1f}%",
                    "good" if snapshot['win_rate'] >= 55.0 else "warn" if snapshot['win_rate'] >= 45.0 else "bad",
                )
                _snapshot_card(
                    snapshot_grid,
                    0,
                    2,
                    "누적 손익",
                    f"{snapshot['total_pnl']:+,.0f}원",
                    "good" if snapshot['total_pnl'] >= 0 else "bad",
                )
                _snapshot_card(
                    snapshot_grid,
                    0,
                    3,
                    "리스크 가드",
                    "활성화" if snapshot['risk_guard_enabled'] else "비활성화",
                    "good" if snapshot['risk_guard_enabled'] else "warn",
                )

                # ── 상단 빠른 이동 액션 ──
                jump_row = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
                jump_row.pack(fill="x", padx=12, pady=(0, 8))
                ctk.CTkLabel(
                    jump_row,
                    text="빠른 이동",
                    font=self._get_safe_font("subtitle"),
                    text_color="#fbbf24",
                ).pack(anchor="w", padx=12, pady=(10, 6))

                jump_btns = ctk.CTkFrame(jump_row, fg_color="transparent")
                jump_btns.pack(fill="x", padx=12, pady=(0, 10))
                ctk.CTkButton(
                    jump_btns,
                    text="AI 요약 리포트 탭 열기",
                    height=32,
                    command=self._open_ai_analyst_summary_tab,
                    fg_color="#334155",
                    hover_color="#475569",
                ).pack(side="left", padx=(0, 6))
                ctk.CTkButton(
                    jump_btns,
                    text="시나리오 점검 탭 열기",
                    height=32,
                    command=self._open_ai_analyst_scenario_tab,
                    fg_color="#334155",
                    hover_color="#475569",
                ).pack(side="left", padx=(0, 6))
                ctk.CTkButton(
                    jump_btns,
                    text="AI 어시스턴트 열기",
                    height=32,
                    command=lambda: self._request_ai_analyst("advice"),
                    fg_color="#2563eb",
                    hover_color="#1d4ed8",
                ).pack(side="left")

                # ── 분석 카드 그리드 ──
                grid = ctk.CTkFrame(scroll, fg_color="#0b1120")
                grid.pack(fill="x", padx=12, pady=(0, 8))
                grid.grid_columnconfigure(0, weight=1)
                grid.grid_columnconfigure(1, weight=1)

                def _analyst_card(parent, row, col, icon, title, lines, btn_text=None, btn_cmd=None):
                    card = ctk.CTkFrame(parent, fg_color="#1f2937", corner_radius=12)
                    card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
                    ctk.CTkLabel(card, text=f"{icon}  {title}",
                                 font=ctk.CTkFont(size=14, weight="bold"),
                                 text_color="#f9fafb").pack(anchor="w", padx=12, pady=(10, 4))
                    for line in lines:
                        ctk.CTkLabel(card, text=line, font=ctk.CTkFont(size=12),
                                     text_color="#9ca3af", wraplength=280, justify="left").pack(anchor="w", padx=14, pady=1)
                    if btn_text and btn_cmd:
                        ctk.CTkButton(card, text=btn_text, command=btn_cmd,
                                      height=30, font=ctk.CTkFont(size=12),
                                      fg_color="#2563eb", hover_color="#1d4ed8").pack(anchor="e", padx=12, pady=(6, 10))
                    return card

                _analyst_card(grid, 0, 0, "", "포트폴리오 종합 분석",
                              ["• 보유 종목·코인별 수익률 요약",
                               "• 위험 자산 비중 및 분산 점수",
                               "• 리밸런싱 필요 여부 판단"],
                              "분석 요청", lambda: self._request_ai_analyst("portfolio"))

                _analyst_card(grid, 0, 1, "", "시장 신호 & 매매 타이밍",
                              ["• 기술적 지표 기반 매수/매도 신호",
                               "• 과매수·과매도 구간 감지",
                               "• 단기·중기 추세 전환점 예측"],
                              "신호 확인", lambda: self._request_ai_analyst("signals"))

                _analyst_card(grid, 1, 0, "", "리스크 평가 & 경고",
                              ["• 포지션별 최대 손실 시나리오",
                               "• 집중 위험 자산 알림",
                               "• 변동성 급등 구간 자동 경보"],
                              "리스크 점검", lambda: self._request_ai_analyst("risk"))

                _analyst_card(grid, 1, 1, "", "AI 맞춤 투자 조언",
                              ["• 현재 투자 성향 진단",
                               "• 목표 수익률 달성 전략 제안",
                               "• 설정 최적화 권고사항"],
                              "조언 요청", lambda: self._request_ai_analyst("advice"))

                _analyst_card(grid, 2, 0, "", "성과 분석 & 비교",
                              ["• 전략별 누적 수익률 비교",
                               "• 샤프·소르티노 지수 계산",
                               "• 최대 낙폭(MDD) 분석"],
                              "성과 보기", lambda: self._request_ai_analyst("performance"))

                _analyst_card(grid, 2, 1, "", "뉴스 & 감성 분석",
                              ["• 주요 종목·코인 관련 뉴스 요약",
                               "• 시장 감성 지수(Sentiment Score)",
                               "• 이벤트 캘린더 (실적·공시·이슈)"],
                              "뉴스 분석", lambda: self._request_ai_analyst("news"))

                # ── 요약/시나리오 프리뷰 ──
                preview_wrap = ctk.CTkFrame(scroll, fg_color="#0b1120")
                preview_wrap.pack(fill="both", expand=True, padx=12, pady=(2, 8))
                preview_wrap.grid_columnconfigure(0, weight=1)
                preview_wrap.grid_columnconfigure(1, weight=1)

                summary_preview = ctk.CTkFrame(preview_wrap, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
                summary_preview.grid(row=0, column=0, padx=(0, 6), pady=4, sticky="nsew")
                ctk.CTkLabel(
                    summary_preview,
                    text="AI 요약 리포트 미리보기",
                    font=self._get_safe_font("subtitle"),
                    text_color="#fbbf24",
                ).pack(anchor="w", padx=12, pady=(10, 4))
                self._ai_summary_preview_box = ctk.CTkTextbox(
                    summary_preview,
                    height=160,
                    fg_color="#0b1120",
                    text_color="#d1d5db",
                    corner_radius=8,
                )
                self._ai_summary_preview_box.pack(fill="both", expand=True, padx=12, pady=(0, 8))
                self._register_tab_widget(tab_name, "_ai_summary_preview_box", self._ai_summary_preview_box)

                scenario_preview = ctk.CTkFrame(preview_wrap, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
                scenario_preview.grid(row=0, column=1, padx=(6, 0), pady=4, sticky="nsew")
                ctk.CTkLabel(
                    scenario_preview,
                    text="시나리오 점검 미리보기",
                    font=self._get_safe_font("subtitle"),
                    text_color="#fbbf24",
                ).pack(anchor="w", padx=12, pady=(10, 4))
                self._ai_scenario_preview_box = ctk.CTkTextbox(
                    scenario_preview,
                    height=160,
                    fg_color="#0b1120",
                    text_color="#d1d5db",
                    corner_radius=8,
                )
                self._ai_scenario_preview_box.pack(fill="both", expand=True, padx=12, pady=(0, 8))
                self._register_tab_widget(tab_name, "_ai_scenario_preview_box", self._ai_scenario_preview_box)

                preview_btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
                preview_btn_row.pack(fill="x", padx=12, pady=(0, 8))
                ctk.CTkButton(
                    preview_btn_row,
                    text="미리보기 새로고침",
                    height=30,
                    command=self._refresh_ai_analyst_previews,
                    fg_color="#334155",
                    hover_color="#475569",
                ).pack(anchor="e")

                # ── AI 분석 결과 표시 영역 ──
                result_frame = ctk.CTkFrame(scroll, fg_color="#0f1f3d", corner_radius=12)
                result_frame.pack(fill="both", expand=True, padx=12, pady=(4, 12))
                ctk.CTkLabel(result_frame, text="AI 분석 결과",
                             font=ctk.CTkFont(size=14, weight="bold"),
                             text_color="#f9fafb").pack(anchor="w", padx=12, pady=(10, 4))
                self._ai_analyst_result_box = ctk.CTkTextbox(
                    result_frame, height=200,
                    fg_color="#1f2937", text_color="#d1d5db",
                    font=ctk.CTkFont(size=13), corner_radius=8)
                self._ai_analyst_result_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
                self._register_tab_widget(tab_name, "_ai_analyst_result_box", self._ai_analyst_result_box)
                self._ai_analyst_result_box.insert("end",
                    "위의 분석 카드 버튼을 클릭하면 AI가 현재 거래 상황을 분석하여 결과를 표시합니다.\n\n"
                    "팁: AI 어시스턴트 탭에서 음성으로 분석을 요청할 수도 있습니다.")
                self._ai_analyst_result_box.configure(state="disabled")

                self._refresh_ai_analyst_previews()

                # 탭 선택
                try:
                    tv.set(tab_name)
                except Exception:
                    pass
                self.logger.info("AI 애널리스트 서비스 화면 표시 완료")

        except Exception as e:
            self.logger.error(f"AI 애널리스트 서비스 화면 표시 오류: {e}")

    def _collect_ai_analyst_snapshot_metrics(self) -> Dict[str, Any]:
        """AI 애널리스트 상단에 표시할 핵심 스냅샷 지표를 계산한다."""
        closed_trades = 0
        win_rate = 0.0
        total_pnl = 0.0

        try:
            db_path = self._get_dashboard_read_db_path()
        except Exception:
            db_path = ''

        if db_path and os.path.exists(db_path):
            try:
                with sqlite3.connect(db_path) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        SELECT COUNT(*),
                               SUM(CASE WHEN COALESCE(pnl, 0) > 0 THEN 1 ELSE 0 END),
                               SUM(COALESCE(pnl, 0))
                        FROM trade_log
                        WHERE exit_time IS NOT NULL
                          AND LOWER(COALESCE(reason, '')) != 'binance_import'
                        """
                    )
                    row = cur.fetchone() or (0, 0, 0.0)
                    closed_trades = int(row[0] or 0)
                    win_count = int(row[1] or 0)
                    total_pnl = float(row[2] or 0.0)
                    if closed_trades > 0:
                        win_rate = (win_count / closed_trades) * 100.0
            except Exception:
                pass

        stock_auto = dict((self.settings or {}).get('stock_auto_trading', {}) or {})
        risk_guard_enabled = bool(stock_auto.get('risk_guard_enabled', True))

        return {
            'closed_trades': closed_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'risk_guard_enabled': risk_guard_enabled,
        }

    def _refresh_ai_analyst_previews(self) -> None:
        """AI 요약/시나리오 미리보기 텍스트를 최신 상태로 갱신한다."""
        try:
            box = getattr(self, '_ai_summary_preview_box', None)
            if box is not None:
                self._safe_text_set(box, "\n".join(self._build_ai_summary_report_lines()))
        except Exception:
            pass

        try:
            box = getattr(self, '_ai_scenario_preview_box', None)
            if box is not None:
                self._safe_text_set(box, "\n".join(self._build_ai_scenario_lines()))
        except Exception:
            pass

    def _open_ai_analyst_summary_tab(self) -> None:
        """AI 요약 리포트 탭을 생성/선택한다."""
        try:
            self._ensure_service_info_tab(
                "AI 요약 리포트",
                "AI 요약 리포트",
                self._build_ai_summary_report_lines(),
            )
            if hasattr(self, 'tab_widget') and self.tab_widget is not None:
                cast(ctk.CTkTabview, self.tab_widget).set("AI 요약 리포트")
        except Exception:
            pass

    def _open_ai_analyst_scenario_tab(self) -> None:
        """시나리오 점검 탭을 생성/선택한다."""
        try:
            self._ensure_scenario_check_tab()
            if hasattr(self, 'tab_widget') and self.tab_widget is not None:
                cast(ctk.CTkTabview, self.tab_widget).set("시나리오 점검")
        except Exception:
            pass

    def _request_ai_analyst(self, analysis_type: str):
        """AI 애널리스트 분석 요청 - AI 어시스턴트에 위임"""
        type_labels = {
            "portfolio":   "현재 포트폴리오를 종합 분석해줘. 위험 분산 수준, 수익률, 리밸런싱 필요 여부를 알려줘.",
            "signals":     "현재 보유 자산의 매수/매도 신호를 분석해줘. 기술적 지표와 추세 기준으로 설명해줘.",
            "risk":        "현재 포지션의 리스크를 평가해줘. 집중 위험 자산과 최대 손실 시나리오를 알려줘.",
            "advice":      "내 투자 성향과 현재 상황을 분석해서 맞춤 투자 조언을 해줘. 설정 최적화 방안도 포함해줘.",
            "performance": "지금까지의 투자 성과를 분석해줘. 누적 수익률, 샤프 지수, 최대 낙폭을 계산해줘.",
            "news":        "현재 보유 자산 관련 주요 뉴스와 시장 감성을 분석해줘. 이슈가 될 만한 이벤트도 알려줘.",
        }
        prompt = type_labels.get(analysis_type, "현재 투자 상황을 분석해줘.")
        try:
            fi_widget = (getattr(self, "financial_intelligence_widgets", {}) or {}).get("ai_analyst")
            fi_service = getattr(fi_widget, "service", None)
            if fi_service and hasattr(fi_service, "dashboard_snapshot"):
                snapshot = fi_service.dashboard_snapshot()
                observed = {
                    "market": snapshot.get("market") or [],
                    "upcoming_events": snapshot.get("upcoming_events") or [],
                    "news": snapshot.get("news") or [],
                    "narratives": snapshot.get("narratives") or [],
                }
                if any(observed.values()):
                    prompt += (
                        "\n\n아래는 금융 인텔리전스 허브에 저장된 관측 데이터입니다. "
                        "출처와 기준시각을 유지하고, 없는 값은 추정하거나 생성하지 마세요.\n"
                        + json.dumps(observed, ensure_ascii=False, default=str)[:6000]
                    )
        except Exception as context_error:
            self.logger.warning(f"금융 인텔리전스 컨텍스트 연결 생략: {context_error}")
        try:
            # 서비스 전환 중 파괴된 Tcl 입력창의 캐시 참조는 재사용하지 않는다.
            aw = self._get_live_ai_assistant()
            if aw and hasattr(aw, 'send_quick_question'):
                aw.set_service_context('ai_analyst', announce=False)
                sent = bool(aw.send_quick_question(prompt))
                if not sent:
                    raise RuntimeError('AI 어시스턴트 입력창이 활성 상태가 아닙니다.')
                # AI 어시스턴트 탭으로 전환
                if hasattr(self, 'tab_widget') and self.tab_widget:
                    try:
                        cast(ctk.CTkTabview, self.tab_widget).set("AI 어시스턴트")
                    except Exception:
                        pass
            else:
                # AI 어시스턴트 위젯이 없으면 결과 박스에 직접 표시
                result_box = getattr(self, '_ai_analyst_result_box', None)
                if result_box:
                    result_box.configure(state="normal")
                    result_box.delete("1.0", "end")
                    result_box.insert("end",
                        f"AI 어시스턴트가 연결되지 않았습니다.\n\n"
                        f"분석 요청: {prompt}\n\n"
                        "설정 > AI 엔진/API 탭에서 API 키를 먼저 설정해주세요.")
                    result_box.configure(state="disabled")
                self._record_ai_execute_event(
                    action='ai_analysis_request',
                    title='AI 애널리스트 심층분석',
                    plan_lines=[prompt.splitlines()[0][:180]],
                    risk_level='normal',
                    risk_reasons=['AI 어시스턴트 위젯 연결 실패'],
                    result='요청 실패',
                )
        except Exception as e:
            self.logger.error(f"AI 애널리스트 분석 요청 오류: {e}")
            self._record_ai_execute_event(
                action='ai_analysis_request',
                title='AI 애널리스트 심층분석',
                plan_lines=[prompt.splitlines()[0][:180]],
                risk_level='normal',
                risk_reasons=[str(e)[:180]],
                result='요청 오류',
            )

    def _draw_diagnostic_button(self):
        """진단용 Canvas 둥근 버튼 그리기"""
        try:
            canvas = self._diagnostic_canvas_btn
            canvas.delete("all")

            w, h = 120, 50
            r = 20  # corner_radius
            color = "#ef4444"  # 빨강 (진단용으로 눈에 띄게)

            # 둥근 사각형 그리기
            canvas.create_arc(0, 0, 2*r, 2*r, start=90, extent=90, fill=color, outline=color)
            canvas.create_arc(w-2*r, 0, w, 2*r, start=0, extent=90, fill=color, outline=color)
            canvas.create_arc(0, h-2*r, 2*r, h, start=180, extent=90, fill=color, outline=color)
            canvas.create_arc(w-2*r, h-2*r, w, h, start=270, extent=90, fill=color, outline=color)
            canvas.create_rectangle(r, 0, w-r, h, fill=color, outline="")
            canvas.create_rectangle(0, r, w, h-r, fill=color, outline="")

            # 텍스트
            canvas.create_text(w/2, h/2, text="진단", fill="#ffffff",
                             font=("Segoe UI", 12, "bold"))
        except Exception as e:
            print(f"진단 버튼 그리기 실패: {e}")

    def _show_diagnostic_modal(self):
        """대시보드 내부 corner_radius 진단 모달"""
        try:
            modal = ctk.CTkToplevel(self)
            modal.title("Corner Radius 진단 도구")
            modal.geometry("800x700")
            modal.configure(fg_color="#050a13")

            # 스크롤 가능한 메인 프레임
            scroll_frame = ctk.CTkScrollableFrame(modal,
                                                  fg_color="#0b1120",
                                                  corner_radius=12)
            scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

            # 제목
            title = ctk.CTkLabel(scroll_frame,
                                text="대시보드 내부 Corner Radius 진단",
                                font=ctk.CTkFont(size=18, weight="bold"),
                                text_color="#ef4444")
            title.pack(pady=15)

            desc = ctk.CTkLabel(scroll_frame,
                               text="이 모달은 대시보드(ModernDashboard) 내부에서 실행됩니다.\n"
                                    "아래 버튼들이 둥글게 보이는지 확인하세요.",
                               font=ctk.CTkFont(size=11),
                               text_color="#94a3af")
            desc.pack(pady=10)

            # 섹션 1: CTkButton 테스트
            section1 = ctk.CTkFrame(scroll_frame, fg_color="#1f2937", corner_radius=16, border_width=2, border_color="#334155")
            section1.pack(fill="x", pady=10, padx=10)

            ctk.CTkLabel(section1,
                        text="1⃣ CTkButton (다양한 corner_radius)",
                        font=ctk.CTkFont(size=14, weight="bold"),
                        text_color="#22c55e").pack(pady=10)

            btn_container1 = ctk.CTkFrame(section1, fg_color="#0b1120")
            btn_container1.pack(pady=10)

            test_btn1 = RoundedButton(btn_container1,
                                     text="radius=30 (강제)",
                                     corner_radius=30,
                                     width=180, height=60,
                                     fg_color="#2563eb",
                                     font=ctk.CTkFont(size=12, weight="bold"))
            test_btn1.pack(side="left", padx=5)

            test_btn2 = RoundedButton(btn_container1,
                                     text="radius=15 (강제)",
                                     corner_radius=15,
                                     width=180, height=60,
                                     fg_color="#8b5cf6",
                                     font=ctk.CTkFont(size=12, weight="bold"))
            test_btn2.pack(side="left", padx=5)

            test_btn3 = RoundedButton(btn_container1,
                                     text="radius=5 (강제)",
                                     corner_radius=5,
                                     width=180, height=60,
                                     fg_color="#22c55e",
                                     font=ctk.CTkFont(size=12, weight="bold"))
            test_btn3.pack(side="left", padx=5)

            # 섹션 2: 메인 대시보드의 "모두 시작" 버튼 스타일 복제
            section2 = ctk.CTkFrame(scroll_frame, fg_color="#1f2937", corner_radius=16, border_width=2, border_color="#334155")
            section2.pack(fill="x", pady=10, padx=10)

            ctk.CTkLabel(section2,
                        text="2⃣ 메인 대시보드 '모두 시작' 버튼 스타일 복제",
                        font=ctk.CTkFont(size=14, weight="bold"),
                        text_color="#fbbf24").pack(pady=10)

            clone_btn = RoundedButton(section2,
                                     text="모두 시작 (복제-강제)",
                                     height=50,
                                     width=180,
                                     font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                                     fg_color="#10b981",
                                     text_color="white",
                                     hover_color="#059669",
                                     border_width=0,
                                     corner_radius=20)
            clone_btn.pack(pady=15)

            # 섹션 3: 순수 Canvas 버튼
            section3 = ctk.CTkFrame(scroll_frame, fg_color="#1f2937", corner_radius=16, border_width=2, border_color="#334155")
            section3.pack(fill="x", pady=10, padx=10)

            ctk.CTkLabel(section3,
                        text="3⃣ 순수 Tkinter Canvas 버튼 (수동 렌더링)",
                        font=ctk.CTkFont(size=14, weight="bold"),
                        text_color="#06b6d4").pack(pady=10)

            canvas_container = ctk.CTkFrame(section3, fg_color="#0b1120")
            canvas_container.pack(pady=15)

            # Canvas 버튼 1
            canvas1 = tk.Canvas(canvas_container, width=180, height=60,
                               bg="#1f2937", highlightthickness=0)
            canvas1.pack(side="left", padx=10)
            self._draw_canvas_button(canvas1, 180, 60, 25, "#2563eb", "Canvas r=25")

            # Canvas 버튼 2
            canvas2 = tk.Canvas(canvas_container, width=180, height=60,
                               bg="#1f2937", highlightthickness=0)
            canvas2.pack(side="left", padx=10)
            self._draw_canvas_button(canvas2, 180, 60, 10, "#8b5cf6", "Canvas r=10")

            # 진단 결과
            result_frame = ctk.CTkFrame(scroll_frame, fg_color="#1f2937", corner_radius=16, border_width=2, border_color="#ef4444")
            result_frame.pack(fill="x", pady=20, padx=10)

            ctk.CTkLabel(result_frame,
                        text="진단 결과",
                        font=ctk.CTkFont(size=14, weight="bold"),
                        text_color="#ef4444").pack(pady=10)

            result_text = ctk.CTkTextbox(result_frame, height=120,
                                        fg_color="#0b1120",
                                        text_color="#f9fafb",
                                        font=ctk.CTkFont(size=11))
            result_text.pack(fill="x", padx=15, pady=10)
            result_text.insert("1.0",
                             "CTkButton이 둥글면: 정상\n"
                             "CTkButton이 각지면: dashboard_modern.py 내부의 특정 코드가 corner_radius를 무시\n\n"
                             "Canvas가 둥글면: Tkinter 렌더링 정상\n"
                             "Canvas도 각지면: Windows/DPI 문제\n\n"
                             "→ CTk만 각지면: set_appearance_mode('dark') 또는 내부 테마 시스템 제거 필요\n"
                             "→ 모두 둥글면: 메인 컨테이너의 클리핑 문제 (padding/투명도 조정)")
            result_text.configure(state="disabled")

            # 닫기 버튼
            close_btn = ctk.CTkButton(scroll_frame,
                                     text="닫기",
                                     command=modal.destroy,
                                     width=120,
                                     height=40,
                                     corner_radius=10,
                                     fg_color="#6b7280",
                                     hover_color="#4b5563")
            close_btn.pack(pady=20)

            modal.focus()
        except Exception as e:
            print(f"진단 모달 생성 실패: {e}")
            import traceback
            traceback.print_exc()

    def _draw_canvas_button(self, canvas, w, h, r, color, text):
        """Canvas에 둥근 버튼 그리기"""
        try:
            canvas.delete("all")

            # 둥근 사각형
            canvas.create_arc(0, 0, 2*r, 2*r, start=90, extent=90, fill=color, outline=color)
            canvas.create_arc(w-2*r, 0, w, 2*r, start=0, extent=90, fill=color, outline=color)
            canvas.create_arc(0, h-2*r, 2*r, h, start=180, extent=90, fill=color, outline=color)
            canvas.create_arc(w-2*r, h-2*r, w, h, start=270, extent=90, fill=color, outline=color)
            canvas.create_rectangle(r, 0, w-r, h, fill=color, outline="")
            canvas.create_rectangle(0, r, w, h-r, fill=color, outline="")

            # 텍스트
            canvas.create_text(w/2, h/2, text=text, fill="#ffffff",
                             font=("Segoe UI", 11, "bold"))
        except Exception:
            pass



    def safe_after(self, delay, func, *args, **kwargs):
        """안전한 after() 메서드 - 작업 추적 및 TclError 방지"""
        try:
            # 종료 플래그 확인
            if hasattr(self, '_is_destroying') and self._is_destroying:
                return None

            # 창이 파괴되었는지 확인
            if not self.winfo_exists():
                return None

            # lambda 함수를 안전하게 래핑
            job_ref = {"id": None}

            def safe_callback():
                try:
                    # 콜백 실행 전 다시 한번 확인
                    if hasattr(self, '_is_destroying') and self._is_destroying:
                        return
                    if not self.winfo_exists():
                        return

                    # TclError 방지를 위한 추가 체크
                    try:
                        func(*args, **kwargs)
                    except tk.TclError as e:
                        if "invalid command name" in str(e) or "border_parts" in str(e):
                            # 위젯이 삭제된 경우 무시
                            return
                        else:
                            raise e
                except Exception as e:
                    # 위젯 파괴 오류는 무시
                    if "invalid command name" not in str(e) and "TclError" not in str(e) and "border_parts" not in str(e):
                        print(f"콜백 실행 오류: {e}")
                finally:
                    job_id = job_ref.get("id")
                    if job_id:
                        try:
                            self.after_jobs.remove(job_id)
                        except (ValueError, AttributeError):
                            pass

            job_id = self.after(delay, safe_callback)
            job_ref["id"] = job_id
            if job_id:
                self.after_jobs.append(job_id)
            return job_id
        except tk.TclError as e:
            if "invalid command name" in str(e) or "border_parts" in str(e):
                return None
            raise e
        except Exception as e:
            print(f"safe_after 오류: {e}")
            return None

    def thread_safe_after(
        self,
        delay,
        func,
        *args,
        coalesce_key: Optional[str] = None,
        **kwargs,
    ):
        """백그라운드 콜백을 상한 큐로 전달하며 동일 키는 최신 값으로 병합한다."""
        try:
            current_thread = threading.current_thread()
            main_thread = threading.main_thread()

            # 현재 스레드가 메인 스레드인지 확인
            if current_thread is main_thread:
                # 메인 스레드에서 직접 호출
                return self.safe_after(delay, func, *args, **kwargs)
            else:
                def queued_call():
                    try:
                        self.safe_after(delay, func, *args, **kwargs)
                    except Exception:
                        pass

                marker: Any = queued_call
                normalized_key = str(coalesce_key or "").strip()
                if normalized_key:
                    with self._ui_coalesce_lock:
                        if normalized_key in self._ui_coalesced_calls:
                            self._ui_coalesced_calls[normalized_key] = queued_call
                            self._ui_dispatch_metrics["coalesced"] += 1
                            return None
                        self._ui_coalesced_calls[normalized_key] = queued_call
                        marker = ("coalesced", normalized_key)
                try:
                    self._ui_call_queue.put_nowait(marker)
                    self._ui_dispatch_metrics["queued"] += 1
                except queue.Full:
                    if normalized_key:
                        with self._ui_coalesce_lock:
                            self._ui_coalesced_calls.pop(normalized_key, None)
                    self._ui_dispatch_metrics["dropped"] += 1
                    dropped = int(self._ui_dispatch_metrics["dropped"])
                    if dropped == 1 or dropped % 100 == 0:
                        self.logger.warning(
                            f"UI 콜백 큐 포화: 오래된 읽기 전용 화면 갱신 폐기 "
                            f"(dropped={dropped}, max={self._ui_call_queue.maxsize})"
                        )
                return None
        except Exception as e:
            print(f"thread_safe_after 오류: {e}")
            return None

    def _schedule_visible_refresh(self, owner_widget, delay_ms, callback):
        """화면에 보이는 섹션만 반복 갱신하고 재진입 시 즉시 재개한다.

        CTk 탭 전환 중에는 실제 선택 탭의 자식도 짧게 ``viewable=False``를
        반환할 수 있다. 그 순간 예약을 완전히 버리면 Map 이벤트가 다시 오지
        않는 환경에서 갱신 루프가 영구 정지한다. 숨김 상태에서는 API 호출은
        하지 않되, 저빈도 생존 확인을 계속 예약해 스스로 복구한다.
        """
        return schedule_visible_refresh(self, owner_widget, delay_ms, callback)

    def _kick_visible_refreshes_for_tab(self, tab_name: str) -> None:
        """선택된 탭 아래에서 잠든 가시성 갱신을 즉시 다시 예약한다.

        숨겨진 CTkTabview 탭에서 자식 카드가 먼저 생성되면 최초 예약 시
        ``winfo_viewable``이 False여서 실행되지 않을 수 있다. 일부 Tk/CTk
        조합은 자식 카드에 Map 이벤트를 다시 전달하지 않으므로 탭 선택
        command에서 선택 탭의 예약 큐를 명시적으로 깨운다.
        """
        try:
            tv = cast(ctk.CTkTabview, self.tab_widget)
            root = tv.tab(str(tab_name))
        except Exception:
            return

        pending = [root]
        seen: set[int] = set()
        while pending:
            widget = pending.pop()
            marker = id(widget)
            if marker in seen:
                continue
            seen.add(marker)
            registry = getattr(widget, "_noah_visible_refresh_registry", None)
            if isinstance(registry, dict):
                for state in list(registry.values()):
                    queue_refresh = state.get("queue") if isinstance(state, dict) else None
                    if callable(queue_refresh):
                        queue_refresh(0)
            try:
                pending.extend(widget.winfo_children())
            except Exception:
                pass

    def _run_visible_refresh_async(
        self,
        owner_widget,
        refresh_key: str,
        worker: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Optional[Callable[[Exception], None]] = None,
        timeout_ms: int = 12000,
    ) -> bool:
        """동일 거래소 조회를 대시보드 전체에서 하나만 실행하고 최신 화면에 전달한다."""
        if owner_widget is None or worker is None or on_success is None:
            return False
        key = str(refresh_key)
        try:
            state = self._global_async_refresh_registry.setdefault(
                key,
                {
                    "running": False,
                    "generation": 0,
                    "timeout_job": None,
                    "timed_out": False,
                    "waiter": None,
                },
            )
            # 화면을 빠르게 왕복해도 이미 실행 중인 읽기 API는 재호출하지 않는다.
            # 결과 수신 대상만 가장 최근의 살아 있는 화면으로 교체한다.
            state["waiter"] = {
                "owner": owner_widget,
                "on_success": on_success,
                "on_error": on_error,
            }
            if bool(state.get("running", False)):
                self._ui_dispatch_metrics["coalesced"] += 1
                return True
            state["running"] = True
            state["timed_out"] = False
            state["generation"] = int(state.get("generation", 0)) + 1
            generation = int(state["generation"])
        except Exception:
            return False

        def _timeout():
            if (
                int(state.get("generation", 0)) != generation
                or not bool(state.get("running", False))
            ):
                return
            # 멈춘 거래소 호출이 이 키를 영구 점유하지 않게 세대를 종료한다.
            # 이전 worker의 늦은 결과는 generation 불일치로 폐기되며, 다음 화면
            # 주기에서 새 조회를 시작한다. HTTP 클라이언트 자체 제한시간도 있어
            # 동시에 남는 worker 수는 제한된다.
            state["timed_out"] = True
            state["running"] = False
            state["generation"] = generation + 1
            state["timeout_job"] = None
            try:
                waiter = dict(state.get("waiter") or {})
                current_owner = waiter.get("owner")
                current_error = waiter.get("on_error")
                if (
                    callable(current_error)
                    and not getattr(self, "_is_destroying", False)
                    and self.winfo_exists()
                    and current_owner.winfo_exists()
                    and current_owner.winfo_viewable()
                ):
                    current_error(TimeoutError("거래소 응답 시간이 12초를 초과했습니다"))
            except Exception:
                pass

        try:
            state["timeout_job"] = self.safe_after(
                max(1000, int(timeout_ms)),
                _timeout,
            )
        except Exception:
            state["timeout_job"] = None

        def _worker():
            result = None
            error = None
            try:
                result = worker()
            except Exception as exc:
                error = exc

            def _apply():
                if int(state.get("generation", 0)) != generation:
                    return
                state["running"] = False
                state["timed_out"] = False
                waiter = dict(state.get("waiter") or {})
                current_owner = waiter.get("owner")
                current_success = waiter.get("on_success")
                current_error = waiter.get("on_error")
                timeout_job = state.get("timeout_job")
                if timeout_job is not None:
                    try:
                        self.after_cancel(timeout_job)
                    except Exception:
                        pass
                    try:
                        self.after_jobs.remove(timeout_job)
                    except (ValueError, AttributeError):
                        pass
                    state["timeout_job"] = None
                try:
                    if (
                        getattr(self, "_is_destroying", False)
                        or not self.winfo_exists()
                        or current_owner is None
                        or not current_owner.winfo_exists()
                        or not current_owner.winfo_viewable()
                    ):
                        return
                except Exception:
                    return
                if error is not None:
                    if callable(current_error):
                        current_error(error)
                    return
                if callable(current_success):
                    current_success(result)

            try:
                self.thread_safe_after(
                    0,
                    _apply,
                    coalesce_key=f"async_refresh_apply:{key}",
                )
            except Exception:
                state["running"] = False

        threading.Thread(
            target=_worker,
            daemon=True,
            name=f"dashboard_refresh_{key}",
        ).start()
        return True

    def _drain_ui_call_queue(self):
        """백그라운드 큐에 쌓인 UI 콜백을 메인 스레드에서 순차 실행한다."""
        try:
            processed = 0
            while processed < 200:
                try:
                    queued = self._ui_call_queue.get_nowait()
                except queue.Empty:
                    break
                callback = queued
                if (
                    isinstance(queued, tuple)
                    and len(queued) == 2
                    and queued[0] == "coalesced"
                ):
                    with self._ui_coalesce_lock:
                        callback = self._ui_coalesced_calls.pop(str(queued[1]), None)
                try:
                    if callable(callback):
                        callback()
                except Exception:
                    pass
                processed += 1
        except Exception:
            pass
        finally:
            try:
                if not getattr(self, '_is_destroying', False) and self.winfo_exists():
                    self.safe_after(50, self._drain_ui_call_queue)
            except Exception:
                pass

    def cleanup_after_jobs(self):
        """모든 after() 작업 정리 - TclError 방지"""
        try:
            # Tkinter가 파괴되었는지 확인
            if not self.winfo_exists():
                return

            # 저장된 after() 작업들 취소
            for job_id in self.after_jobs:
                try:
                    self.after_cancel(job_id)
                except tk.TclError as e:
                    if "invalid command name" in str(e) or "border_parts" in str(e):
                        # 위젯이 삭제된 경우 무시
                        continue
                    else:
                        raise e
                except:
                    pass
            self.after_jobs.clear()

        except tk.TclError as e:
            if "invalid command name" in str(e) or "border_parts" in str(e):
                # 위젯이 삭제된 경우 무시
                pass
            else:
                raise e
        except:
            pass

    def on_closing(self):
        """대시보드 종료 시 정리"""
        try:
            print("[DEBUG] dashboard on_closing called")

            # 거래소 어댑터를 멈춘 뒤에는 포지션/미체결 조회가 실패할 수 있다.
            # 업데이트 안전 승인은 반드시 안전 종료보다 먼저, 정확한 staged SHA에
            # 묶어서 수행한다. 적용 단계에서는 이 승인을 재사용한다.
            update_preflight = {"ok": True, "needed": False}
            try:
                if (
                    hasattr(self, 'main_app')
                    and self.main_app
                    and hasattr(self.main_app, 'prepare_update_preflight_on_exit')
                ):
                    update_preflight = dict(
                        self.main_app.prepare_update_preflight_on_exit() or update_preflight
                    )
            except Exception as preflight_e:
                update_preflight = {
                    "ok": False,
                    "needed": True,
                    "reason": "preflight_exception",
                    "error": str(preflight_e),
                }
                print(f"자동 업데이트 사전 승인 실패: {preflight_e}")

            # 거래 중지 -> DB flush -> 로그 flush 후 위젯을 파괴한다.
            try:
                shutdown_ok = True
                if hasattr(self, 'main_app') and self.main_app and hasattr(self.main_app, 'shutdown_for_exit'):
                    shutdown_ok = bool(self.main_app.shutdown_for_exit())
            except Exception as shutdown_e:
                shutdown_ok = False
                print(f"안전 종료 정리 경고: {shutdown_e}")

            # 종료 직전 자동 업데이트 적용(다운로드 완료 + 자동적용 ON인 경우)
            try:
                if (
                    shutdown_ok
                    and update_preflight.get("ok", False)
                    and hasattr(self, 'main_app')
                    and self.main_app
                    and hasattr(self.main_app, 'prepare_update_apply_on_exit')
                ):
                    applied = bool(self.main_app.prepare_update_apply_on_exit())
                    if applied:
                        print("[AUTO_UPDATE] 종료 시 업데이트 적용 스크립트 예약 완료")
                elif not shutdown_ok:
                    print("[AUTO_UPDATE] 안전 종료 또는 DB flush 실패로 업데이트 적용을 연기합니다.")
                elif update_preflight.get("needed"):
                    print(
                        "[AUTO_UPDATE] 종료 전 안전 승인 실패로 업데이트 적용을 연기합니다: "
                        f"{update_preflight.get('reason', 'unknown')}"
                    )
            except Exception as _up_e:
                print(f"자동 업데이트 적용 예약 실패: {_up_e}")

            # 종료 플래그 설정 (새로운 after() 작업 차단)
            self._is_destroying = True

            # 프로세스 동안 재사용하던 설정 창은 대시보드 종료 시에만 파괴한다.
            try:
                settings_controller = getattr(self, '_settings_controller', None)
                if settings_controller is not None:
                    dispose = getattr(settings_controller, 'dispose', None)
                    if callable(dispose):
                        dispose()
                self._settings_controller = None
                self._settings_window = None
            except Exception:
                pass

            # 전역 종료 플래그 설정 (재시작 방지)
            # 종료 플래그는 일시 비활성화(초기 표시 검증 목적)
            # try:
            #     import main
            #     main._SHUTDOWN_IN_PROGRESS = True
            # except:
            #     pass

            # 모든 after() 작업 정리
            self.cleanup_after_jobs()

            # 실시간 로그 모니터링 정지
            if hasattr(self, 'realtime_log_widget') and self.realtime_log_widget and hasattr(self.realtime_log_widget, 'stop_realtime_monitoring'):
                try:
                    self.realtime_log_widget.stop_realtime_monitoring()
                except Exception:
                    pass

            # 사용자 상태 모니터링 정지
            if hasattr(self, 'user_status_manager') and self.user_status_manager and hasattr(self.user_status_manager, 'stop_monitoring'):
                try:
                    self.user_status_manager.stop_monitoring()
                except Exception:
                    pass

            # 모든 위젯의 after() 작업 정리
            self.cleanup_all_widgets()

            # CustomTkinter 위젯 안전 삭제
            self._safe_destroy_widgets()

            # 안전한 종료 순서: withdraw → quit → destroy
            try:
                self.withdraw()  # 창을 숨김
                self.quit()      # 이벤트 루프 종료
                # sys.exit(0) 제거! (중복 종료/재시작/after 에러 원인)
            except:
                pass

            print("대시보드 정리 완료")
        except Exception as e:
            print(f"대시보드 정리 중 오류: {e}")
        finally:
            try:
                self.destroy()  # 마지막에 파괴
            except:
                pass

    def _safe_destroy_widgets(self):
        """CustomTkinter 위젯 안전 삭제 - TclError 방지"""
        try:
            # 모든 CustomTkinter 위젯을 안전하게 삭제
            widgets_to_destroy = []

            # 위젯 찾기 (재귀적으로)
            def find_widgets(parent):
                try:
                    for child in parent.winfo_children():
                        widgets_to_destroy.append(child)
                        find_widgets(child)
                except:
                    pass

            find_widgets(self)

            # 위젯 삭제 (역순으로)
            for widget in reversed(widgets_to_destroy):
                try:
                    if hasattr(widget, 'winfo_exists') and widget.winfo_exists():
                        # CustomTkinter 위젯의 경우 특별 처리
                        if hasattr(widget, '_canvas') and widget._canvas:
                            try:
                                widget._canvas.delete("all")
                            except:
                                pass
                        widget.destroy()
                except Exception as e:
                    # TclError 무시
                    if "invalid command name" not in str(e):
                        print(f"위젯 삭제 오류: {e}")
        except Exception as e:
            print(f"위젯 안전 삭제 오류: {e}")

    def cleanup_all_widgets(self):
        """모든 위젯의 after() 작업 정리"""
        try:
            cleaned_ids = set()

            def cleanup_widget_tree(parent):
                try:
                    children = list(parent.winfo_children())
                except Exception:
                    children = []
                for child in children:
                    cleanup_widget_tree(child)
                    child_id = id(child)
                    if child_id in cleaned_ids:
                        continue
                    cleaned_ids.add(child_id)
                    for method_name in ("cleanup_after_jobs", "_cancel_after_jobs", "cleanup"):
                        cleanup = getattr(child, method_name, None)
                        if callable(cleanup):
                            try:
                                cleanup()
                            except Exception:
                                pass

            cleanup_widget_tree(self)

            # AI 리포트 위젯 정리
            if (
                hasattr(self, 'ai_report_widget')
                and self.ai_report_widget is not None
                and hasattr(self.ai_report_widget, 'cleanup_after_jobs')
            ):
                try:
                    self.ai_report_widget.cleanup_after_jobs()
                except Exception:
                    pass

            # AI 학습 위젯 정리
            if (
                hasattr(self, 'ai_learning_widget')
                and self.ai_learning_widget is not None
                and hasattr(self.ai_learning_widget, 'cleanup_after_jobs')
            ):
                try:
                    self.ai_learning_widget.cleanup_after_jobs()
                except Exception:
                    pass

            # 기타 위젯들 정리
            for widget_name in ['ai_assistant_widget', 'realtime_log_widget', 'trading_control_widget']:
                if hasattr(self, widget_name):
                    widget = getattr(self, widget_name)
                    if hasattr(widget, 'cleanup_after_jobs'):
                        widget.cleanup_after_jobs()

            for widget in (getattr(self, 'financial_intelligence_widgets', {}) or {}).values():
                try:
                    cleanup = getattr(widget, 'cleanup', None)
                    if callable(cleanup):
                        cleanup()
                except Exception:
                    pass

            ownership = getattr(self, '_widget_ownership', None)
            if ownership is not None:
                ownership.clear()

            print("모든 위젯 정리 완료")
        except Exception as e:
            print(f"위젯 정리 중 오류: {e}")

    def update_status_info(self):
        """상태 정보 업데이트 (실제 데이터)"""
        try:
            # 사용자 정보 업데이트 (로그인 데이터에서)
            user_id = self.get_user_id_from_login_data()
            user_grade = self.get_user_grade_from_token()
            normalized_grade = str(user_grade or '').strip().lower()
            if normalized_grade in {'referral', 'free', 'free_referral', 'referral_free', '레퍼럴'}:
                normalized_grade = 'referral'
            elif normalized_grade in {
                'normal', 'basic', 'general', 'coin_start', 'coin-start', 'pro_coin', 'pro-coin'
            }:
                normalized_grade = 'pro_coin'
            elif normalized_grade in {'stock', 'stocks', 'etf', 'pro_stock', 'pro-stock'}:
                normalized_grade = 'pro_stock'
            if normalized_grade in {'signature', 'signature_federated'}:
                normalized_grade = 'premium'
            if normalized_grade in {'pro', 'all_trading', 'all-trading', 'alltrading', 'middle'}:
                normalized_grade = 'premium'

            if normalized_grade == 'referral':
                policy = getattr(getattr(self, 'main_app', None), 'current_membership_policy', {}) or {}
                summary = policy.get('referral_summary', {}) if isinstance(policy, dict) else {}
                usable_count = int(summary.get('usable_count', 0) or 0) if isinstance(summary, dict) else 0
                pending_count = int(summary.get('pending_count', 0) or 0) if isinstance(summary, dict) else 0
                if usable_count > 0:
                    grade_badge = f"레퍼럴 정상 승인 {usable_count}개"
                elif pending_count > 0:
                    grade_badge = "레퍼럴 UID 확인 대기"
                else:
                    grade_badge = "레퍼럴 가입·승인 필요"
            elif normalized_grade == 'premium':
                grade_badge = "프리미엄"
            elif normalized_grade in {'pro_coin', 'pro_stock'}:
                grade_badge = "프로"
            else:
                grade_badge = "프로"
            try:
                # 기존 스타일 유지하면서 텍스트만 업데이트
                self.user_info_label.configure(
                    text=f"{user_id} | {grade_badge}",
                    fg_color=self._color('surface', '#0b1120'),
                    corner_radius=12
                )
            except Exception:
                pass
            self.user_info_label.configure(text=f"{user_id} | {grade_badge}")

            # 거래소 정보는 오른쪽 상태정보에 표시됨

            # 자동거래 상태 업데이트 (실제 상태 확인)
            self.update_trading_status()

            # 잔고 정보 업데이트 (실제 데이터)
            self.update_balance_display()

            # 상태정보 표시 업데이트
            self.update_status_display()
            self._update_replay_status_badge()

            # 주기적 업데이트 제거 - 포지션 진입/종료 시에만 업데이트

        except Exception as e:
            self.logger.exception("상태 정보 업데이트 오류")
            # 오류 발생 시 재시도하지 않음 - 포지션 변경 시에만 업데이트

    def get_user_id_from_login_data(self):
        """로그인 데이터에서 사용자 ID 가져오기"""
        try:            
            # path_utils를 사용하여 현재 사용자 계정의 token.json 읽기
            from path_utils import get_account_info_from_token, get_current_user_account

            # 현재 로그인 계정을 최우선으로 사용
            current_user = str(get_current_user_account() or '').strip()
            if current_user:
                return current_user

            # token.json에서 사용자 계정 확인
            token_user, _ = get_account_info_from_token()
            if token_user:
                return token_user

            # settings.json에서 사용자 정보 확인
            return self.settings.get('user_id', self.settings.get('username', 'Unknown'))

        except Exception as e:
            self.logger.exception("사용자 ID 조회 오류")
            return 'Unknown'

    def get_user_grade_from_token(self):
        """token.json에서 사용자 등급(user_grade) 가져오기"""
        try:
            from path_utils import get_token_file_path
            import json
            token_path = get_token_file_path()
            if token_path and os.path.exists(token_path):
                with open(token_path, 'r', encoding='utf-8') as f:
                    token_data = json.load(f)
                user_info = token_data.get('user_info', {})
                return user_info.get('user_grade', 'pro_coin')
        except Exception:
            pass
        return 'pro_coin'

    def update_trading_status(self):
        """자동거래 상태 업데이트"""
        try:
            # 실제 자동거래 상태 확인 (대시보드 상태에서 읽기)
            is_auto_trading = getattr(self, 'is_auto_trading', False)

            # 오른쪽 상태정보 업데이트는 update_status_info에서 처리
            # self.update_status_display()

            # 모듈화된 위젯을 통해서만 상태 업데이트
            if hasattr(self, 'trading_control_widget') and self.trading_control_widget and hasattr(self.trading_control_widget, 'update_trading_status'):
                self.trading_control_widget.update_trading_status(is_auto_trading)

        except Exception as e:
            print(f"자동거래 상태 업데이트 오류: {e}")

    def update_balance_display(self):
        """잔고 표시 업데이트 (실제 데이터)"""
        try:
            # 디바운스 플래그 초기화
            try:
                self._balance_refresh_scheduled = False
            except Exception:
                pass
            if not hasattr(self, 'balance_display') or self.balance_display is None:
                return

            # 통합 거래 매니저를 통한 잔고 조회
            if hasattr(self, 'unified_manager') and self.unified_manager:
                # 모든 거래소 잔고 조회
                all_balances = self.unified_manager.get_all_balances()
                self._display_unified_balances(all_balances)
                self._refresh_trading_summary()
                return

            # 기존 거래소 관리자를 통한 잔고 조회 (캐시 무시)
            if hasattr(self, 'exchange_manager') and self.exchange_manager:
                # 캐시를 무시하고 최신 잔고 조회
                balance_result = self.exchange_manager.get_exchange_balance(force_refresh=True)

                if balance_result.get('status') == 'success':
                    balance = balance_result.get('balance', {})
                    account_info = balance_result.get('account_info', {})
                    exchange = balance_result.get('exchange', 'unknown')

                    # 디버깅 로그 (빌드 환경에서 문제 진단용)
                    lines = [
                        "나의 계정잔고",
                        f"\n{exchange}:"
                    ]
                    if isinstance(balance, dict):
                        for k, v in list(balance.items())[:10]:
                            try:
                                lines.append(f"  • {k}: {float(v):.4f}")
                            except Exception:
                                lines.append(f"  • {k}: {v}")
                    else:
                        lines.append(str(balance))
                    if isinstance(account_info, dict) and account_info:
                        lines.append("\nℹ계정 정보 요약:")
                        for k, v in list(account_info.items())[:5]:
                            lines.append(f"  - {k}: {v}")
                    self._safe_text_set(self.balance_display, "\n".join(lines))
                else:
                    err = balance_result.get('error') or '잔고 조회 실패'
                    self._safe_text_set(self.balance_display, f"{err}")
            else:
                self._safe_text_set(self.balance_display, "거래소 연결 없음")

            self._refresh_trading_summary()
        except Exception as e:
            self._safe_text_set(getattr(self, 'balance_display', None), f"잔고 조회 오류\n{str(e)}")

    def _apply_always_on_top_setting(self):
        """항상 최상단 표시 설정 적용"""
        try:
            # 설정 파일을 직접 읽어서 ui_settings 확인
            import json
            from path_utils import get_config_dir
            import os

            config_path = os.path.join(get_config_dir(), 'settings.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                always_on_top = settings.get('ui_settings', {}).get('always_on_top', False)
            else:
                # 설정 파일이 없으면 기본값 사용 (False로 변경하여 자연스러운 창 동작)
                always_on_top = False

            self.attributes('-topmost', always_on_top)
            self.logger.info(f"대시보드 항상 최상단 표시: {'ON' if always_on_top else 'OFF'}")
        except Exception as e:
            # 설정 로드 실패 시 기본값으로 자연스러운 창 동작
            self.attributes('-topmost', False)
            self.logger.warning(f"설정 로드 실패, 기본값 사용: {e}")

    def refresh_always_on_top_setting(self):
        """설정 변경 후 항상 최상단 표시 설정 새로고침"""
        self._apply_always_on_top_setting()

    def _build_ai_execute_plan(self) -> tuple[str, str, list[str]]:
        """현재 상태 기반 실행 계획 요약을 생성한다 (개별 거래소 제어 기준)."""
        enabled = set(getattr(self, 'enabled_exchanges', []) or [])
        running = set(getattr(self, '_running_exchanges', set()) or set())

        if not enabled:
            action = "per_exchange"
            title = "거래소별 시작 준비"
            lines = ["- 활성화된 거래소가 없어 실행할 작업이 없습니다.", "- 설정에서 거래소를 먼저 활성화하세요."]
            return action, title, lines

        action = "per_exchange"
        targets = sorted(list(enabled))
        running_targets = sorted(list(running))
        remaining = sorted(list(enabled - running))
        lines = [
            "- 전역 전체 시작/정지 기능은 제거되었습니다.",
            f"- 활성 거래소: {', '.join(targets)}",
            f"- 현재 실행 중: {', '.join(running_targets) if running_targets else '없음'}",
            f"- 미실행 거래소: {', '.join(remaining) if remaining else '없음'}",
            "- 각 거래소 카드의 시작/정지 버튼으로 개별 제어하세요.",
        ]
        return action, "거래소별 제어 계획", lines

    def _build_ai_diagnosis_payload(self, for_settings_dialog: bool = False) -> Dict[str, Any]:
        """설정 창/가이드 UI에서 재사용 가능한 AI 진단 payload를 생성한다."""
        action, title, plan_lines = self._build_ai_execute_plan()
        readiness_lines = self._diagnose_ai_execute_readiness(live_check=not for_settings_dialog)
        risk_level, risk_reasons = self._assess_ai_execute_risk()

        issues: list[str] = []
        warning_keywords = ('미준비', '확인 필요', '오류', '시간 초과', '없어', '없습니다')
        for line in list(plan_lines) + list(readiness_lines):
            text = str(line).strip()
            if text.startswith('- '):
                text = text[2:]
            if any(keyword in text for keyword in warning_keywords):
                issues.append(text)
        for reason in risk_reasons:
            reason_text = str(reason).strip()
            if reason_text:
                issues.append(reason_text)

        if risk_level == 'normal' and not issues:
            status = 'ready'
            summary = '현재 설정 기준 준비도 점검이 완료되었습니다. 아직 AI 실행은 시작되지 않았습니다.'
        elif risk_level == 'high':
            status = 'not_ready'
            summary = '고위험 조건이 감지되었습니다. 설정을 먼저 점검한 뒤 실행 확인을 진행하세요.'
        else:
            status = 'caution'
            summary = '일부 확인이 필요한 항목이 있습니다. 점검 항목을 확인한 뒤 실행 여부를 선택하세요.'

        return {
            'status': status,
            'summary': summary,
            'issues': issues,
            'action': action,
            'title': title,
            'plan_lines': list(plan_lines),
            'readiness_lines': list(readiness_lines),
            'risk_level': risk_level,
            'risk_reasons': list(risk_reasons),
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

    def _on_ai_execute_clicked(self):
        """전역 제어 기능 제거 이후: 개별 거래소 제어 안내만 제공."""
        try:
            try:
                if getattr(self, 'ai_execute_summary_label', None):
                    self.ai_execute_summary_label.configure(text='거래소별 제어 진단 중...')
                self.update_idletasks()
            except Exception:
                pass

            action, title, lines = self._build_ai_execute_plan()
            readiness = self._diagnose_ai_execute_readiness()
            risk_level, risk_reasons = self._assess_ai_execute_risk()
            risk_header = {
                'high': '[고위험]',
                'elevated': '[주의]',
                'normal': '[일반]',
            }.get(risk_level, '[일반]')
            summary = "\n".join(lines + [''] + ['[준비도 진단]'] + readiness)
            if risk_reasons:
                summary += "\n\n" + risk_header + "\n" + "\n".join(f"- {r}" for r in risk_reasons)
            confirm = messagebox.askyesno(
                title,
                (
                    "거래소별 제어 안내\n"
                    "- 전역 전체 시작/정지는 제거되었습니다.\n"
                    "- 거래소 카드의 시작/정지 버튼으로 개별 제어합니다.\n\n"
                    f"아래 상태를 확인하시겠습니까?\n\n{summary}"
                ),
            )
            if not confirm:
                self._record_ai_execute_event(
                    action=action,
                    title=title,
                    plan_lines=lines + readiness,
                    risk_level=risk_level,
                    risk_reasons=risk_reasons,
                    result='사용자 확인 취소',
                )
                return

            self._record_ai_execute_event(
                action=action,
                title=title,
                plan_lines=lines + readiness,
                risk_level=risk_level,
                risk_reasons=risk_reasons,
                result='거래소별 제어 안내 확인',
            )

            # 실행 후 AI 어시스턴트 탭 안내
            try:
                self._ensure_ai_assistant_tab()
                if getattr(self, 'tab_widget', None) is not None:
                    cast(ctk.CTkTabview, self.tab_widget).set("AI 어시스턴트")
            except Exception:
                pass
        except Exception as e:
            try:
                self._record_ai_execute_event(
                    action='error',
                    title='거래소별 제어 안내 실패',
                    plan_lines=[],
                    risk_level='high',
                    risk_reasons=[str(e)],
                    result='오류',
                )
            except Exception:
                pass
            try:
                messagebox.showerror(
                    '전체 제어 오류',
                    '전체 제어 준비 중 오류가 발생했습니다.\n\n'
                    f'오류: {e}\n\n'
                    '설정 > 거래소/API 키를 확인한 뒤 다시 시도해주세요.'
                )
            except Exception:
                pass
            try:
                self.logger.error(f"전체 제어 버튼 처리 오류: {e}")
            except Exception:
                logging.getLogger(__name__).error(f"전체 제어 버튼 처리 오류: {e}")


    def _update_global_status_ui(self):
        """전역 Tri-State 상태 라벨 & 버튼 텍스트 갱신"""
        try:
            enabled = set(self.enabled_exchanges)
            running = set(self._running_exchanges)
            if not enabled:
                state_text = "상태: (거래소 없음)"
            elif not running:
                state_text = "상태: 전체정지"
            elif running == enabled:
                state_text = "상태: 전체실행"
            else:
                state_text = f"상태: 부분실행 ({len(running)}/{len(enabled)})"

            if hasattr(self, 'status_display') and getattr(self, 'status_display', None):
                try:
                    self.status_display.configure(state='normal')
                    self.status_display.delete('1.0', 'end')
                    self.status_display.insert('1.0', state_text)
                    self.status_display.configure(state='disabled')
                except Exception:
                    pass

            self._refresh_start_button_appearance()
            self._refresh_trading_summary()
        except Exception:
            pass

    def _schedule_balance_refresh(self, delay_ms: int = 700):
        """잔고 갱신을 디바운스로 스케줄링"""
        try:
            if getattr(self, '_balance_refresh_scheduled', False):
                return
            self._balance_refresh_scheduled = True
            if hasattr(self, 'after'):
                self.thread_safe_after(delay_ms, self._run_balance_refresh)
        except Exception:
            try:
                self.update_balance_display()
            except Exception:
                pass

    def _run_balance_refresh(self):
        try:
            self._balance_refresh_scheduled = False
        except Exception:
            pass
        try:
            self.update_balance_display()
        except Exception:
            pass

    def update_balance_on_trade_completion(self):
        """거래 완료(청산/체결) 이벤트 후 잔고 강제 갱신 트리거"""
        try:
            # 캐시 무시하고 즉시 잔고 갱신
            if hasattr(self, 'exchange_manager') and self.exchange_manager:
                # 캐시 무시하고 최신 잔고 조회
                self.exchange_manager.get_exchange_balance(force_refresh=True)
            
            # 잔고 표시 업데이트
            self.update_balance_display()
        except Exception:
            try:
                # 폴백: 스케줄링 시도
                self._schedule_balance_refresh(delay_ms=300)
            except Exception:
                pass

    def _refresh_trading_summary(self) -> None:
        """우측 거래 현황 패널 내용을 최신 상태로 반영"""
        try:
            widget = getattr(self, 'trading_summary_text', None)
            if not self._widget_alive(widget):
                return

            total_trades = 0
            total_pnl = 0.0
            active_positions = 0
            win_rate = 0.0
            _wins_sum = 0

            # 통합 통계 수집 (DB + 메모리)
            try:
                # 우선순위: exchange_trade_stats 테이블 (거래소별 통계)
                import sqlite3
                db_path = self._get_dashboard_read_db_path()

                if os.path.exists(db_path):
                    with sqlite3.connect(db_path) as conn:
                        cursor = conn.cursor()
                        
                        # 1. exchange_trade_stats 테이블에서 모든 거래소 통계 합산
                        cursor.execute("""
                            SELECT
                                SUM(total_trades) as total_trades,
                                SUM(winning_trades) as winning_trades,
                                SUM(total_pnl) as total_pnl
                            FROM exchange_trade_stats
                        """)
                        row = cursor.fetchone()
                        
                        if row and row[0] is not None:
                            # exchange_trade_stats에 데이터가 있으면 사용
                            total_trades = row[0] or 0
                            _wins_sum = row[1] or 0
                            total_pnl = row[2] or 0.0
                        else:
                            # 2. 폴백: trade_log에서 직접 집계 (완료된 거래만)
                            cursor.execute("""
                                SELECT
                                    COUNT(*) as total_trades,
                                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                                    SUM(pnl) as total_pnl
                                FROM trade_log
                                WHERE exit_time IS NOT NULL
                                  AND LOWER(COALESCE(reason, '')) != 'binance_import'
                            """)
                            row = cursor.fetchone()
                            if row:
                                total_trades = row[0] or 0
                                _wins_sum = row[1] or 0
                                total_pnl = row[2] or 0.0
            except Exception as e:
                # 오류 발생 시 조용히 넘어감 (기본값 유지)
                pass

            # 전체 승률 계산 (단순 합산 기반)
            try:
                if total_trades > 0:
                    win_rate = (_wins_sum / total_trades) * 100.0
            except Exception:
                pass

            # 관리자 방송 모드에서는 화면 표시용 손익 오버레이를 적용한다.
            try:
                display_overrides = self._get_broadcast_display_overrides()
                override_pnl = display_overrides.get('total_pnl_usdt')
                override_trades = display_overrides.get('total_trades')
                override_win_rate = display_overrides.get('win_rate_percent')

                if override_trades is not None:
                    total_trades = int(round(float(override_trades)))
                if override_pnl is not None:
                    total_pnl = float(override_pnl)
                if override_win_rate is not None:
                    win_rate = float(override_win_rate)
            except Exception:
                pass

            # 메모리에서 활성 포지션 수 조회 (실시간)
            # 바이낸스 포지션
            try:
                main_app = getattr(self, 'main_app', None)
                trader = getattr(main_app, 'trader', None) if main_app is not None else None
                if trader:
                    position_getter = getattr(trader, 'get_active_positions', None)
                    binance_positions = (
                        position_getter()
                        if callable(position_getter)
                        else getattr(trader, 'active_positions', {})
                    )
                    active_positions += len(binance_positions)
            except Exception:
                pass

            # CCXT 거래소 포지션
            try:
                unified_trader = getattr(self, 'unified_trader', None)
                if unified_trader and hasattr(unified_trader, 'get_active_positions'):
                    ccxt_positions = unified_trader.get_active_positions()
                    for exchange_positions in ccxt_positions.values():
                        active_positions += len(exchange_positions)
            except Exception:
                pass
            
            # Alpha Arena 포지션 (실시간)
            try:
                alpha_arena_widget = getattr(self, 'alpha_arena_widget', None)
                if alpha_arena_widget and hasattr(alpha_arena_widget, 'binance_client'):
                    binance_client = alpha_arena_widget.binance_client
                    if binance_client:
                        # Alpha Arena 고정 심볼 6개 확인
                        arena_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'BNBUSDT']
                        for symbol in arena_symbols:
                            try:
                                position_info = binance_client.get_position_info(symbol)
                                if position_info:
                                    position_amt = float(position_info.get('positionAmt', 0))
                                    if abs(position_amt) > 1e-8:
                                        active_positions += 1
                            except Exception:
                                pass
            except Exception:
                pass


            running = len(getattr(self, '_running_exchanges', set()))
            enabled = len(getattr(self, 'enabled_exchanges', []) or [])
            auto_state = "실행 중" if running else "대기"
            if enabled:
                auto_state += f" ({running}/{enabled} 거래소)"

            lines = [
                "거래 현황",
                "",
                f"• 활성 포지션: {active_positions}",
                f"• 총 거래 수: {total_trades}",
                f"• 누적 손익: {total_pnl:.2f} USDT",
                f"• 승률: {win_rate:.2f}%",
                f"• 자동 거래 상태: {auto_state}"
            ]

            self._safe_text_set(widget, "\n".join(lines))

            try:
                pnl_color = self._color('success', '#22c55e') if total_pnl >= 0 else self._color('danger', '#ef4444')
                label_map = {key: label for key, label, _tab in self._get_ops_kpi_specs_for_service()}

                if hasattr(self, 'ops_kpi_active_btn') and self.ops_kpi_active_btn:
                    self.ops_kpi_active_btn.configure(text=f"{label_map.get('active', '포지션')}\n{active_positions}")
                if hasattr(self, 'ops_kpi_trades_btn') and self.ops_kpi_trades_btn:
                    self.ops_kpi_trades_btn.configure(text=f"{label_map.get('trades', '거래')}\n{total_trades}")
                if hasattr(self, 'ops_kpi_pnl_btn') and self.ops_kpi_pnl_btn:
                    self.ops_kpi_pnl_btn.configure(text=f"{label_map.get('pnl', '손익')}\n{total_pnl:.2f}", text_color=pnl_color)
                if hasattr(self, 'ops_kpi_winrate_btn') and self.ops_kpi_winrate_btn:
                    self.ops_kpi_winrate_btn.configure(text=f"{label_map.get('winrate', '승률')}\n{win_rate:.2f}%")
            except Exception:
                pass

            try:
                alerts: List[str] = []
                if running == 0:
                    alerts.append("자동매매가 대기 상태입니다. 거래소 실행 상태를 확인하세요.")
                if total_trades == 0:
                    alerts.append("종료 거래가 없어 성과 판단 신뢰도가 낮습니다.")
                if total_pnl < 0:
                    alerts.append("누적 손익이 음수입니다. 포지션 크기와 신호 임계값 재점검이 필요합니다.")
                if win_rate < 40.0 and total_trades >= 10:
                    alerts.append("승률이 40% 미만입니다. 진입 필터 강화 또는 전략 조정이 필요합니다.")
                if active_positions >= 8:
                    alerts.append("활성 포지션이 많습니다. 동시 리스크 노출 관리가 필요합니다.")
                if not alerts:
                    alerts = [
                        "치명 리스크 신호 없음",
                        "현재 운영 상태는 기준 범위 내입니다.",
                        "변동성 확대 구간에서는 리스크 가드레일을 유지하세요.",
                    ]

                try:
                    level, level_label = self._classify_ops_alert_level(
                        running=running,
                        total_trades=total_trades,
                        total_pnl=total_pnl,
                        win_rate=win_rate,
                        active_positions=active_positions,
                    )
                    if level == 'danger':
                        badge_color = self._color('danger', '#ef4444')
                    elif level == 'warning':
                        badge_color = self._color('warning', '#f59e0b')
                    else:
                        badge_color = self._color('success', '#22c55e')

                    badge = getattr(self, 'ops_alert_badge', None)
                    if badge is not None:
                        badge.configure(text=level_label, fg_color=badge_color)
                except Exception:
                    pass

                alert_lines = [f"• {item}" for item in alerts[:3]]
                self._safe_text_set(getattr(self, 'ops_alert_text', None), "\n".join(alert_lines))
            except Exception:
                pass
        except Exception as e:
            self._safe_text_set(getattr(self, 'trading_summary_text', None), f"거래 현황\n\n갱신 실패: {e}")

    # --- 최소 UI 빌드: 메인/하단 섹션 (호환성용) ---
    def _on_main_tab_changed(self) -> None:
        """선택 시점에 동적 탭 내용을 다시 보장한다."""
        try:
            selected = str(cast(ctk.CTkTabview, self.tab_widget).get() or '')
            self.after_idle(self._apply_source_tab_distinction)
            self.after_idle(
                lambda current=selected: self._kick_visible_refreshes_for_tab(current)
            )
            if selected == "AI 커스텀":
                self.after_idle(self._ensure_custom_strategy_tab)
            elif selected in {"금융 인텔리전스", "금융 인텔리전스 허브", "성과·위험 분석"}:
                service = str(getattr(self, "current_service", "blockchain") or "blockchain")
                self.after_idle(lambda current=service: self._ensure_financial_intelligence_tab(current))
        except Exception:
            pass

    def _apply_source_tab_distinction(self) -> None:
        """거래소·증권사 운영 탭을 일반 기능 탭과 은은하게 구분한다."""
        try:
            tv = cast(ctk.CTkTabview, self.tab_widget)
            segmented = getattr(tv, "_segmented_button", None)
            buttons = getattr(segmented, "_buttons_dict", {}) if segmented is not None else {}
            if not isinstance(buttons, dict):
                return

            service = str(getattr(self, "current_service", "blockchain") or "blockchain").lower()
            source_tabs = set((getattr(self, "service_sub_tabs", {}).get(service, {}) or {}).keys())
            selected_name = str(tv.get() or "")
            if service == "stock":
                accent, tint, border, text = "#0f766e", "#123a3a", "#2dd4bf", "#ccfbf1"
            else:
                accent, tint, border, text = "#0e7490", "#12364a", "#38bdf8", "#e0f2fe"

            for tab_name in source_tabs:
                button = buttons.get(tab_name)
                if button is None:
                    continue
                is_selected = tab_name == selected_name
                button.configure(
                    fg_color=accent if is_selected else tint,
                    hover_color="#0891b2" if service != "stock" else "#0d9488",
                    border_width=1,
                    border_color=border,
                    text_color="#ffffff" if is_selected else text,
                )
        except Exception:
            # 구형 CustomTkinter에서도 탭 기능 자체는 그대로 유지한다.
            pass

    def create_main_content(self):
        self.logger.info("[DEBUG] create_main_content 내부 진입")
        try:
            self.logger.info("[DEBUG] tab_widget 확인 중")
            if not hasattr(self, 'tab_widget') or self.tab_widget is None:
                self.logger.info("[DEBUG] tab_widget 생성 시작")
                # 탭뷰를 카드 래퍼 안에 배치하여 라운드와 테두리 가시성을 보장
                # 탭 래퍼 카드는 본문 배경보다 약간 더 밝은 색상과 두꺼운 테두리로 대비를 키움
                self.tab_wrapper = self._create_card_frame(self.main_frame, corner_radius=16)
                try:
                    self.tab_wrapper.configure(
                        fg_color=self._color('surface', '#0f172a'),
                        border_color=self._color('border', '#334155'),
                        border_width=2
                    )
                except Exception:
                    pass
                self.tab_wrapper.pack(fill="both", expand=True, padx=10, pady=10)
                self.tab_widget = ctk.CTkTabview(
                    self.tab_wrapper,
                    corner_radius=14,
                    fg_color="#0b1120",
                    command=self._on_main_tab_changed,
                )
            self.tabview = self.tab_widget
            self.tab_widget.pack(fill="both", expand=True, padx=6, pady=6)

            try:
                # 탭 바의 대비를 높여 배경과 명확히 구분되도록 색상 재정의 (강제 적용 포함)
                self._apply_tabview_style(self.tab_widget)
            except Exception:
                pass

            dashboard_tab_name = "실시간 거래 로그"
            try:
                dashboard_tab = self._get_or_add_tab(dashboard_tab_name)
            except Exception:
                dashboard_tab = self.tab_widget.add(dashboard_tab_name)

            # 탭 추가 후에도 한 번 더 스타일을 강제 적용 (버전/순서 이슈 대비)
            try:
                self._apply_tabview_style(self.tab_widget)
            except Exception:
                pass

            # 대시보드 기본 탭 컨테이너: 로그인 배경과 동일한 표면 색으로 통일
            self.dashboard_container = ctk.CTkFrame(dashboard_tab, fg_color=self._color('background', '#0b1120'))
            self.dashboard_container.pack(fill='both', expand=True, padx=4, pady=4)

            container = self.dashboard_container
            try:
                container.grid_columnconfigure(0, weight=9, uniform="dashboard")
                container.grid_columnconfigure(1, weight=4, uniform="dashboard")
                container.grid_rowconfigure(0, weight=1)
            except Exception:
                pass

            left_card = self._create_card_frame(container, corner_radius=18)
            left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12), pady=(0, 0))
            left_card.grid_rowconfigure(1, weight=1)
            self.left_content_frame = left_card

            # 상단 헤더 라벨 제거로 로그 표시 공간 극대화 (요청)

            log_container = ctk.CTkFrame(
                left_card,
                fg_color=self._color('panel', '#2c3545'),
                corner_radius=14
            )
            # 상단 여백도 축소해 더 많은 로그가 보이도록 조정
            log_container.pack(fill="both", expand=True, padx=16, pady=(8, 16))
            left = log_container

            right_column = self._create_card_frame(
                container,
                corner_radius=16,
                border=True,
                color_key='surface',
                border_key='border'
            )
            right_column.grid(row=0, column=1, sticky="nsew", padx=(12, 0), pady=(0, 0))
            right_column.grid_rowconfigure(0, weight=1)
            right_column.grid_columnconfigure(0, weight=1)
            self.right_content_frame = right_column

            panel_inner = ctk.CTkScrollableFrame(
                right_column,
                fg_color=self._color('surface_alt', '#202c42'),
                corner_radius=12
            )
            panel_inner.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
            try:
                panel_inner.grid_rowconfigure(0, weight=0)
                panel_inner.grid_rowconfigure(1, weight=0)
                panel_inner.grid_rowconfigure(2, weight=0)
                panel_inner.grid_rowconfigure(3, weight=0)
                panel_inner.grid_rowconfigure(4, weight=0)
                panel_inner.grid_columnconfigure(0, weight=1)
            except Exception:
                pass

            section_bg = self._color('panel', '#1f2b40')
            section_bg_alt = self._color('panel_alt', '#27354d')

            ops_kpi_card = ctk.CTkFrame(
                panel_inner,
                fg_color=section_bg,
                corner_radius=10
            )
            ops_kpi_card.grid(row=0, column=0, sticky="ew", pady=(0, 8))

            try:
                kpi_title = ctk.CTkLabel(
                    ops_kpi_card,
                    text="운영 KPI",
                    font=self._get_safe_font("subheading", ctk.CTkFont(size=14, weight="bold")),
                    text_color=self._color('text_primary', '#f9fafb')
                )
                kpi_title.pack(anchor="w", padx=12, pady=(10, 6))

                kpi_row = ctk.CTkFrame(ops_kpi_card, fg_color="transparent")
                kpi_row.pack(fill="x", padx=12, pady=(0, 10))
                try:
                    kpi_row.grid_columnconfigure((0, 1, 2, 3), weight=1)
                except Exception:
                    pass

                button_base = self._color('button_secondary', '#3a5a7f')
                button_hover = self._color('button_secondary_hover', '#4a6a8f')

                self.ops_kpi_active_btn = ctk.CTkButton(
                    kpi_row,
                    text="포지션\n-",
                    font=self._get_safe_font("small", ctk.CTkFont(size=12)),
                    height=44,
                    corner_radius=10,
                    fg_color=button_base,
                    hover_color=button_hover,
                    command=lambda: self._on_ops_kpi_click('active')
                )
                self.ops_kpi_active_btn.grid(row=0, column=0, padx=4, sticky="nsew")

                self.ops_kpi_trades_btn = ctk.CTkButton(
                    kpi_row,
                    text="거래\n-",
                    font=self._get_safe_font("small", ctk.CTkFont(size=12)),
                    height=44,
                    corner_radius=10,
                    fg_color=button_base,
                    hover_color=button_hover,
                    command=lambda: self._on_ops_kpi_click('trades')
                )
                self.ops_kpi_trades_btn.grid(row=0, column=1, padx=4, sticky="nsew")

                self.ops_kpi_pnl_btn = ctk.CTkButton(
                    kpi_row,
                    text="손익\n-",
                    font=self._get_safe_font("small", ctk.CTkFont(size=12)),
                    height=44,
                    corner_radius=10,
                    fg_color=button_base,
                    hover_color=button_hover,
                    command=lambda: self._on_ops_kpi_click('pnl')
                )
                self.ops_kpi_pnl_btn.grid(row=0, column=2, padx=4, sticky="nsew")

                self.ops_kpi_winrate_btn = ctk.CTkButton(
                    kpi_row,
                    text="승률\n-",
                    font=self._get_safe_font("small", ctk.CTkFont(size=12)),
                    height=44,
                    corner_radius=10,
                    fg_color=button_base,
                    hover_color=button_hover,
                    command=lambda: self._on_ops_kpi_click('winrate')
                )
                self.ops_kpi_winrate_btn.grid(row=0, column=3, padx=4, sticky="nsew")

                self._refresh_ops_kpi_buttons()
            except Exception:
                pass

            right_summary = ctk.CTkFrame(
                panel_inner,
                fg_color=section_bg,
                corner_radius=10
            )
            right_summary.grid(row=1, column=0, sticky="nsew")

            try:
                from ui.widgets.realtime_log_widget import RealtimeLogWidget
                try:
                    from log_system.log_stream import get_log_stream
                    log_stream = get_log_stream()
                except Exception:
                    log_stream = None
                self.realtime_log_widget = RealtimeLogWidget(
                    left,
                    logger=self.logger,
                    log_stream=log_stream,
                    stream_exchange=None,
                    on_open_manual=lambda: self._open_manual_modal("업데이트")
                )
                self.realtime_log_widget.pack(fill="both", expand=True, padx=0, pady=0)
            except Exception as le:
                try:
                    self.logger.warning(f"전역 로그 위젯 초기화 실패: {le}")
                except Exception:
                    print(f"전역 로그 위젯 초기화 실패: {le}")
                fallback_text = ctk.CTkTextbox(left, height=400)
                fallback_text.pack(fill="both", expand=True, padx=0, pady=0)
                fallback_text.insert("0.0", "실시간 로그 위젯 로드 실패\n파일 기반 로그를 확인하세요.")

            try:
                summary_label = ctk.CTkLabel(
                    right_summary,
                    text="거래 현황",
                    font=self._get_safe_font("subheading", ctk.CTkFont(size=15, weight="bold")),
                    text_color=self._color('text_primary', '#f9fafb')
                )
                summary_label.pack(anchor="w", padx=12, pady=(12, 6))

                self.trading_summary_text = ctk.CTkTextbox(
                    right_summary,
                    height=160,
                    fg_color=section_bg_alt,
                    text_color=self._color('text_primary', '#f3f6fb'),
                    corner_radius=12,
                    border_width=0,
                    wrap="word"
                )
                self.trading_summary_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
                self.trading_summary_text.insert(
                    "0.0",
                    "거래 현황\n\n"
                    "• 활성 포지션: 로딩 중...\n"
                    "• 총 거래 수: 로딩 중...\n"
                    "• 누적 손익: 로딩 중...\n"
                    "• 자동 거래 상태: 확인 중..."
                )
            except Exception:
                pass

            try:
                quick_card = ctk.CTkFrame(
                    panel_inner,
                    fg_color=section_bg,
                    corner_radius=10
                )
                quick_card.grid(row=2, column=0, sticky="ew", pady=(8, 8))

                quick_label = ctk.CTkLabel(
                    quick_card,
                    text="Quick Actions",
                    font=self._get_safe_font("subheading", ctk.CTkFont(size=14, weight="bold")),
                    text_color=self._color('text_primary', '#f9fafb')
                )
                quick_label.pack(anchor="w", padx=12, pady=(12, 6))

                quickbar2 = ctk.CTkFrame(quick_card, fg_color="#0b1120")
                # 버튼들이 좌우 여백이 동일하게 보이도록 내부를 grid로 구성해 양쪽에 균등 여백을 둔다
                quickbar2.pack(fill="x", padx=12, pady=(0, 10))
                try:
                    quickbar2.grid_columnconfigure(0, weight=1)
                    quickbar2.grid_columnconfigure(3, weight=1)
                except Exception:
                    pass

                button_base = self._color('button_secondary', '#3a5a7f')
                button_hover = self._color('button_secondary_hover', '#4a6a8f')
                button_text = self._color('text_primary', '#f3f6fb')

                try:
                    optimize_btn = ctk.CTkButton(
                        quickbar2,
                        text="AI 최적화 진단",
                        width=150,
                        height=36,
                        fg_color=button_base,
                        text_color=button_text,
                        hover_color=button_hover,
                        corner_radius=12,
                        command=self._open_ai_optimization_center
                    )
                    optimize_btn.grid(row=0, column=1, padx=4, pady=4, sticky="ew")
                    self.optimize_action_btn = optimize_btn
                except Exception:
                    self.optimize_action_btn = None

                try:
                    apply_btn = ctk.CTkButton(
                        quickbar2,
                        text="AI 최적화 적용",
                        width=150,
                        height=36,
                        fg_color=button_base,
                        text_color=button_text,
                        hover_color=button_hover,
                        corner_radius=12,
                        command=self._open_ai_optimization_apply_center
                    )
                    apply_btn.grid(row=0, column=2, padx=4, pady=4, sticky="ew")
                    self.optimize_apply_action_btn = apply_btn
                except Exception:
                    self.optimize_apply_action_btn = None

                self._refresh_quick_action_buttons()

                alert_card = ctk.CTkFrame(
                    panel_inner,
                    fg_color=section_bg,
                    corner_radius=10
                )
                alert_card.grid(row=3, column=0, sticky="ew", pady=(0, 8))

                alert_label = ctk.CTkLabel(
                    alert_card,
                    text="실시간 운영 알림",
                    font=self._get_safe_font("subheading", ctk.CTkFont(size=14, weight="bold")),
                    text_color=self._color('text_primary', '#f9fafb')
                )
                alert_label.pack(anchor="w", padx=12, pady=(10, 2))

                self.ops_alert_badge = ctk.CTkLabel(
                    alert_card,
                    text="정상",
                    font=self._get_safe_font("small", ctk.CTkFont(size=11, weight="bold")),
                    text_color=self._color('text_primary', '#ffffff'),
                    fg_color=self._color('success', '#22c55e'),
                    corner_radius=8,
                    padx=8,
                    pady=2
                )
                self.ops_alert_badge.pack(anchor="w", padx=12, pady=(0, 6))

                self.ops_alert_text = ctk.CTkTextbox(
                    alert_card,
                    height=96,
                    fg_color=section_bg_alt,
                    text_color=self._color('text_primary', '#f3f6fb'),
                    corner_radius=12,
                    border_width=0,
                    wrap="word"
                )
                self.ops_alert_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
                self._safe_text_set(
                    self.ops_alert_text,
                    "• 운영 상태 분석 준비 중\n• 초기 지표 수집 중\n• 위험 신호는 거래 데이터 수집 후 표시됩니다"
                )

                balance_card = ctk.CTkFrame(
                    panel_inner,
                    fg_color=section_bg,
                    corner_radius=10
                )
                balance_card.grid(row=4, column=0, sticky="nsew")
                try:
                    balance_card.grid_rowconfigure(1, weight=1)
                except Exception:
                    pass

                balance_label = ctk.CTkLabel(
                    balance_card,
                    text="통합 잔고 요약",
                    font=self._get_safe_font("subheading", ctk.CTkFont(size=14, weight="bold")),
                    text_color=self._color('text_primary', '#f9fafb')
                )
                balance_label.pack(anchor="w", padx=12, pady=(12, 6))

                self.balance_display = ctk.CTkTextbox(
                    balance_card,
                    height=110,
                    fg_color=section_bg_alt,
                    text_color=self._color('text_primary', '#f3f6fb'),
                    corner_radius=12,
                    border_width=0
                )
                self.balance_display.pack(fill="both", expand=True, padx=12, pady=(0, 12))
                try:
                    self.update_balance_display()
                except Exception:
                    pass
            except Exception:
                pass

        except Exception as e:
            self._safe_text_set(getattr(self, 'trading_summary_text', None), f"거래 현황\n\n갱신 실패: {e}")

        # 초기 탭들 자동 생성 (classic_view 설정과 무관하게 항상 생성)
        try:
            self._ensure_coin_info_tab()      # 코인 정보
            self._ensure_trading_stats_tab()  # 거래 통계
            self._ensure_trend_tab()          # 시장 트렌드
            self._ensure_ai_learning_tab()    # AI 학습
            self._ensure_ai_report_tab()      # AI 리포트
            self._ensure_ai_assistant_tab()   # AI 어시스턴트
            self._ensure_custom_strategy_tab()  # AI 커스텀
            # Alpha Arena 탭은 설정에서 활성화된 경우에만 생성
            try:
                self._ensure_alpha_arena_tab()    # AlphaArena
            except Exception as alpha_err:
                # Alpha Arena 탭 생성 실패는 무시 (설정에서 비활성화되었거나 오류)
                pass
            self.logger.info("모든 기본 탭 초기 생성 완료")
        except Exception as tab_err:
            self.logger.warning(f"기본 탭 생성 중 일부 실패: {tab_err}")

        # 거래소 탭 생성 (블록체인 서비스)
        try:
            self.create_service_sub_tabs('blockchain')
        except Exception as ex_err:
            self.logger.warning(f"거래소 탭 생성 실패: {ex_err}")

        # 로컬 렌더 검증 전용. 모든 탭/스타일 초기화 뒤 선택한다.
        try:
            verify_tab = str(os.environ.get('NOAHAI_UI_VERIFY_TAB', '') or '').strip()
            if verify_tab and self._tab_exists(verify_tab):
                def _select_verify_tab(target=verify_tab):
                    tv = cast(ctk.CTkTabview, self.tab_widget)
                    tv.set(target)
                    if target == "AI 커스텀":
                        self._ensure_custom_strategy_tab()
                    elif target in {"금융 인텔리전스", "금융 인텔리전스 허브", "성과·위험 분석"}:
                        self._ensure_current_financial_intelligence_content()
                        # 초기화 중 예약된 이전 탭의 grid_forget 콜백보다 뒤에서
                        # 최종 선택을 한 번 더 확정한다.
                        self.after(250, lambda selected=target: tv.set(selected))
                self.after(5000, _select_verify_tab)
                self.logger.info(f"UI 검증 시작 탭 예약: {verify_tab}")
        except Exception as verify_tab_error:
            self.logger.debug(f"UI 검증 시작 탭 선택 생략: {verify_tab_error}")



    def _open_manual_modal(self, initial_tab: Optional[str] = None) -> None:
        """Show the integrated user manual."""
        try:
            if self._manual_widget is None:
                self._manual_widget = UserManualWidget(self)
            self._manual_widget.show_manual(initial_tab=initial_tab)
        except Exception as exc:
            messagebox.showerror("사용자 매뉴얼", f"매뉴얼을 열 수 없습니다.\n{exc}")

    def _acknowledge_live_readiness_notice(self) -> None:
        """현재 패치의 실거래 필수 안내 확인 상태를 사용자 설정에 저장한다."""
        try:
            settings_obj = self.settings if isinstance(self.settings, dict) else {}
            raw_notices = settings_obj.get("acknowledged_client_notices", [])
            notices = list(raw_notices) if isinstance(raw_notices, list) else []
            if RELEASE_NOTICE_ID not in notices:
                notices.append(RELEASE_NOTICE_ID)
            settings_obj["acknowledged_client_notices"] = notices[-20:]
            self.settings = settings_obj
            from config.settings import save_settings

            save_settings(settings_obj)
        except Exception as exc:
            try:
                self.logger.warning(f"실거래 필수 안내 확인 저장 실패: {exc}")
            except Exception:
                pass

    def _show_live_readiness_notice_if_needed(self, force: bool = False) -> None:
        """업데이트 후 최초 한 번, 실거래 조건과 검증 경계를 직접 알린다."""
        try:
            existing = getattr(self, "_live_readiness_notice_window", None)
            if existing is not None and hasattr(existing, "winfo_exists") and existing.winfo_exists():
                existing.focus_force()
                return

            settings_obj = self.settings if isinstance(self.settings, dict) else {}
            raw_notices = settings_obj.get("acknowledged_client_notices", [])
            notices = raw_notices if isinstance(raw_notices, list) else []
            if not force and RELEASE_NOTICE_ID in notices:
                return

            dialog = ctk.CTkToplevel(self)
            self._live_readiness_notice_window = dialog
            dialog.title(f"{RELEASE_BUILD_LABEL} 실거래 시작 전 필수 안내")
            dialog.geometry("780x640")
            dialog.minsize(700, 560)
            dialog.transient(self)
            dialog.grab_set()

            frame = ctk.CTkFrame(
                dialog,
                fg_color="#0b1120",
                border_width=1,
                border_color="#f59e0b",
                corner_radius=14,
            )
            frame.pack(fill="both", expand=True, padx=12, pady=12)
            ctk.CTkLabel(
                frame,
                text="실거래 시작 전 필수 확인",
                font=self._get_safe_font("heading", ctk.CTkFont(size=20, weight="bold")),
                text_color="#fbbf24",
            ).pack(anchor="w", padx=16, pady=(14, 4))
            ctk.CTkLabel(
                frame,
                text="이 안내는 업데이트 후 처음 한 번 표시되며, 메뉴얼 → 실거래 준비에서 언제든 다시 볼 수 있습니다.",
                font=self._get_safe_font("caption", ctk.CTkFont(size=11)),
                text_color="#cbd5e1",
                wraplength=720,
                justify="left",
            ).pack(anchor="w", padx=16, pady=(0, 10))

            text_box = ctk.CTkTextbox(
                frame,
                wrap="word",
                fg_color="#101826",
                text_color="#e5edf6",
                border_width=1,
                border_color="#334155",
                corner_radius=10,
                font=self._get_safe_font("body", ctk.CTkFont(size=12)),
            )
            text_box.pack(fill="both", expand=True, padx=16, pady=(0, 12))
            text_box.insert("1.0", build_live_trading_summary(RELEASE_BUILD_LABEL))
            text_box.configure(state="disabled")

            actions = ctk.CTkFrame(frame, fg_color="transparent")
            actions.pack(fill="x", padx=16, pady=(0, 14))

            def close_and_acknowledge(open_detail: bool = False) -> None:
                self._acknowledge_live_readiness_notice()
                try:
                    dialog.grab_release()
                except Exception:
                    pass
                try:
                    dialog.destroy()
                except Exception:
                    pass
                self._live_readiness_notice_window = None
                if open_detail:
                    self.after(80, lambda: self._open_manual_modal("실거래 준비"))

            ctk.CTkButton(
                actions,
                text="자세한 실거래 준비 보기",
                height=36,
                fg_color="#2563eb",
                hover_color="#1d4ed8",
                command=lambda: close_and_acknowledge(True),
            ).pack(side="left")
            ctk.CTkButton(
                actions,
                text="내용을 확인했습니다",
                height=36,
                fg_color="#0f766e",
                hover_color="#115e59",
                command=lambda: close_and_acknowledge(False),
            ).pack(side="right")
            dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        except Exception as exc:
            try:
                self.logger.warning(f"실거래 필수 안내 표시 실패: {exc}")
            except Exception:
                pass

    def _open_ai_optimization_center(self) -> None:
        """Quick Actions의 AI 최적화 '진단' 워크플로우를 실행한다.

        동작:
        1) AI 어시스턴트 탭 보장 및 이동
        2) 현재 서비스 기준 최적화 진단 질문 자동 전송
        """
        try:
            assistant = self._get_live_ai_assistant()
            if assistant is None:
                messagebox.showwarning("AI 최적화", "AI 어시스턴트를 불러올 수 없습니다.")
                return

            current_service = str(getattr(self, 'current_service', 'blockchain') or 'blockchain').strip().lower()
            try:
                assistant.set_service_context(current_service, announce=False)
            except Exception:
                pass

            try:
                if getattr(self, 'tab_widget', None):
                    cast(ctk.CTkTabview, self.tab_widget).set("AI 어시스턴트")
            except Exception:
                pass

            optimization_prompt = (
                "현재 설정과 최근 운용 상황을 기준으로 AI 최적화 권장 설정을 제안해줘. "
                "리스크/비용/기대효과를 함께 설명하고, 바로 적용 가능한 핵심 변경 3가지만 우선 제시해줘."
            )
            try:
                assistant.send_quick_question(optimization_prompt)
            except Exception:
                try:
                    assistant.add_ai_message("자동 진단 질문 전송에 실패했습니다. 직접 질문해 주세요.")
                except Exception:
                    pass

        except Exception as exc:
            messagebox.showerror("AI 최적화", f"AI 최적화 기능을 열 수 없습니다.\n{exc}")

    def _open_ai_optimization_apply_center(self) -> None:
        """Quick Actions의 AI 최적화 '적용' 워크플로우를 실행한다."""
        try:
            assistant = self._get_live_ai_assistant()
            if assistant is None:
                messagebox.showwarning("AI 최적화 적용", "AI 어시스턴트를 불러올 수 없습니다.")
                return

            current_service = str(getattr(self, 'current_service', 'blockchain') or 'blockchain').strip().lower()
            try:
                assistant.set_service_context(current_service, announce=False)
            except Exception:
                pass

            try:
                if getattr(self, 'tab_widget', None):
                    cast(ctk.CTkTabview, self.tab_widget).set("AI 어시스턴트")
            except Exception:
                pass

            apply_prompt = (
                "지금부터 AI 최적화 적용 절차를 시작해줘. "
                "먼저 현재 설정 diff 요약과 위험도(낮음/중간/높음)를 보여주고, "
                "사용자 최종확인 후에만 적용하도록 진행해줘."
            )
            try:
                assistant.send_quick_question(apply_prompt)
            except Exception:
                pass

            try:
                assistant.show_settings_management_modal()
            except Exception:
                pass
        except Exception as exc:
            messagebox.showerror("AI 최적화 적용", f"AI 최적화 적용 창을 열 수 없습니다.\n{exc}")



    def create_bottom_status(self):
        try:
            # 상태·업데이트·AI 이력을 한 줄로 통합해 본문 세로 공간을 잠식하지 않는다.
            bottom_card = self._create_card_frame(
                self.main_frame,
                corner_radius=10,
                border=True,
                color_key='surface',
                border_key='border'
            )
            bottom_card.pack(side="bottom", fill="x", padx=10, pady=(4, 8))

            inner = ctk.CTkFrame(
                bottom_card,
                fg_color=self._color('surface_alt', '#202c42'),
                corner_radius=8,
            )
            inner.pack(fill="x", padx=6, pady=6)
            inner.grid_columnconfigure(0, weight=3, minsize=330)
            inner.grid_columnconfigure(1, weight=4, minsize=430)
            inner.grid_columnconfigure(2, weight=2, minsize=255)

            self.status_display = ctk.CTkTextbox(
                inner,
                height=34,
                corner_radius=8,
                fg_color=self._color('background', '#050a13'),
                text_color=self._color('text_primary', '#f9fafb'),
                border_width=1,
                border_color="#263b58",
            )
            self.status_display.grid(row=0, column=0, sticky="ew", padx=(0, 5))
            try:
                self.status_display.configure(state='disabled')
            except Exception:
                pass

            update_card = ctk.CTkFrame(
                inner,
                fg_color="#10233f",
                border_color="#2563eb",
                border_width=1,
                corner_radius=8,
            )
            update_card.grid(row=0, column=1, sticky="ew", padx=5)
            ctk.CTkLabel(
                update_card,
                text=f"{RELEASE_BUILD_LABEL}  {RELEASE_HIGHLIGHT}",
                image=self._get_icon("update", (15, 15)),
                compound="left",
                font=self._get_safe_font('caption', ctk.CTkFont(size=10, weight='bold')),
                text_color="#bfdbfe",
                justify="left",
                anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=(8, 4), pady=5)
            ctk.CTkButton(
                update_card,
                text="실거래 필수 · 업데이트·사용법",
                width=176,
                height=27,
                font=self._get_safe_font('caption', ctk.CTkFont(size=10, weight='bold')),
                fg_color="#2563eb",
                hover_color="#1d4ed8",
                command=lambda: self._open_manual_modal("실거래 준비"),
            ).pack(side="right", padx=5, pady=4)

            summary_card = ctk.CTkFrame(
                inner,
                fg_color=self._color('surface', '#0b1120'),
                border_color=self._color('border', '#1f2937'),
                border_width=1,
                corner_radius=8,
            )
            summary_card.grid(row=0, column=2, sticky="ew", padx=(5, 0))

            self.ai_execute_summary_label = ctk.CTkLabel(
                summary_card,
                text='AI 실행 기록 없음',
                font=self._get_safe_font('caption', ctk.CTkFont(size=10, weight='bold')),
                text_color=self._color('text_secondary', '#cbd5e1'),
                justify='left',
                anchor='w',
            )
            self.ai_execute_summary_label.pack(side='left', fill='x', expand=True, padx=(7, 3), pady=5)

            history_btn = ctk.CTkButton(
                summary_card,
                text='기록',
                image=self._get_icon("history", (14, 14)),
                compound="left",
                width=66,
                height=27,
                font=self._get_safe_font('caption', ctk.CTkFont(size=10, weight='bold')),
                fg_color=self._color('secondary', '#3a5a7f'),
                hover_color=self._hover_from(self._color('secondary', '#3a5a7f')),
                command=self._show_ai_execute_history_modal,
            )
            history_btn.pack(side='right', padx=5, pady=4)
            self._refresh_ai_execute_summary_card()

            # 테스트 렌더링에서는 모달을 띄우지 않는다. 실제 사용자는 패치별 최초 한 번 확인한다.
            if not getattr(self, "_live_readiness_notice_scheduled", False):
                self._live_readiness_notice_scheduled = True
                verify_mode = bool(
                    os.environ.get("NOAHAI_UI_VERIFY_TAB")
                    or os.environ.get("NOAHAI_UI_VERIFY")
                    or os.environ.get("PYTEST_CURRENT_TEST")
                )
                if not verify_mode:
                    self.after(1600, self._show_live_readiness_notice_if_needed)
        except Exception as e:
            print(f"create_bottom_status 생성 오류: {e}")

    def setup_timers(self):
        """타이머 설정 - 이벤트 기반으로 동작하므로 비워둠(호환성용)"""
        try:
            return
        except Exception:
            return

    def show_settings_dialog(self):
        try:
            log_windows_gui_resources(self.logger, "settings-open-before")
            # 로그인 상태 확인 (개발환경 대응)
            try:
                from path_utils import get_current_user_account
                current_user = get_current_user_account()
                print(f"설정 창 열기 시도 - 현재 사용자: '{current_user}'")

                if not current_user:
                    print("로그인이 필요합니다. 먼저 로그인해주세요.")
                    return

                # 개발환경에서도 토큰 파일 확인
                try:
                    from path_utils import get_token_file_path, get_account_info_from_token
                    import json
                    import os

                    # path_utils를 사용한 올바른 토큰 파일 경로 확인
                    token_file = get_token_file_path()
                    print(f"토큰 파일 경로: {token_file}")
                    print(f"토큰 파일 존재: {os.path.exists(token_file)}")

                    # get_account_info_from_token 함수 사용 (모든 경로 자동 확인)
                    token_user, token_path = get_account_info_from_token()
                    print(f"path_utils로 찾은 사용자: '{token_user}' (경로: {token_path})")

                    if token_user:
                        # 토큰 파일의 사용자와 현재 사용자가 다르면 경고
                        if token_user != current_user:
                            print(f"사용자 불일치: 현재='{current_user}', 토큰='{token_user}'")
                        else:
                            print(f"사용자 일치 확인: '{current_user}' == '{token_user}'")
                    else:
                        print("토큰 파일에서 사용자 정보를 찾을 수 없습니다.")

                except Exception as e:
                    print(f"토큰 파일 확인 실패: {e}")

            except Exception as e:
                print(f"사용자 계정 확인 실패: {e}")
                # 사용자 확인 실패해도 설정 창은 열어야 함
                pass

            # 이미 만든 설정 컨트롤러가 있으면 같은 widget/menu 트리를 다시 사용한다.
            controller = getattr(self, '_settings_controller', None)
            try:
                if controller is not None and hasattr(controller, 'show'):
                    if controller.show():
                        return
            except Exception:
                self._settings_controller = None
                self._settings_window = None

            # 이전 버전/부분 초기화 호환: 살아 있는 raw window만 있으면 포커스한다.
            existing = getattr(self, '_settings_window', None)
            try:
                if existing is not None and hasattr(existing, 'winfo_exists') and existing.winfo_exists():
                    try:
                        # 설정의 'AI에게 묻기'가 창을 숨긴 경우에도 같은 편집 상태로 복귀한다.
                        if hasattr(existing, 'deiconify'):
                            existing.deiconify()
                        if hasattr(existing, 'lift'):
                            existing.lift()
                        if hasattr(existing, 'grab_set'):
                            existing.grab_set()
                        if hasattr(existing, 'focus_force'):
                            existing.focus_force()
                        elif hasattr(existing, 'focus'):
                            existing.focus()
                        return
                    except Exception:
                        pass
            except Exception:
                pass

            # ModernSettingsWindow만 사용 (임시 폴백 삭제)
            try:
                from ui.settings_modern import ModernSettingsWindow
                def _on_saved(new_settings: Dict[str, Any]):
                    try:
                        if hasattr(self, 'main_app') and self.main_app and hasattr(self.main_app, 'on_settings_saved'):
                            self.main_app.on_settings_saved(new_settings)
                        else:
                            # 폴백: 대시보드 내부 상태만 갱신
                            self.refresh_after_settings_change(new_settings)
                        
                        # 저장 후 AI 진단 다시 실행 (설정 변경 반영)
                        try:
                            # 설정이 바뀌었으므로 진단 캐시 무효화
                            self._diagnosis_cache = None
                            self._diagnosis_cache_settings_hash = None
                            new_diagnosis = self._build_ai_diagnosis_payload(for_settings_dialog=True)
                            self._last_ai_diagnosis = new_diagnosis
                        except Exception as e:
                            print(f"설정 저장 후 AI 진단 갱신 실패: {e}")
                    except Exception as e:
                        try:
                            self.logger.warning(f"설정 반영 중 오류: {e}")
                        except Exception:
                            print(f"설정 반영 중 오류: {e}")

                # AI 실행 준비도 진단 결과 먼저 생성
                try:
                    if getattr(self, 'ai_execute_summary_label', None):
                        self.ai_execute_summary_label.configure(text='설정 창용 AI 진단 준비 중...')
                    self.update_idletasks()
                except Exception:
                    pass
                ai_diagnosis = self._build_ai_diagnosis_payload(for_settings_dialog=True)
                
                # AI 진단 결과를 설정 창에 전달
                win = ModernSettingsWindow(
                    parent=self,
                    current_settings=self.settings,
                    on_save_callback=_on_saved,
                    ai_diagnosis_result=ai_diagnosis
                )
                log_windows_gui_resources(self.logger, "settings-open-after")
                # 열린 창 레퍼런스 저장 (재포커스 용)
                try:
                    self._settings_window = getattr(win, 'root', win)
                    self._settings_controller = win
                except Exception:
                    self._settings_window = None
                    self._settings_controller = None
                # 포커스 이동
                try:
                    if hasattr(win, 'root') and hasattr(win.root, 'focus'):
                        win.root.focus()
                except Exception:
                    pass
                return
            except Exception as e:
                # 설정 창을 열 수 없을 때 사용자에게 알림
                try:
                    from tkinter import messagebox as _mb
                    _mb.showerror("설정", f"설정 창을 열 수 없습니다: {e}")
                except Exception:
                    pass
                try:
                    self.logger.error(f"설정 창 열기 실패: {e}")
                except Exception:
                    print(f"설정 창 열기 실패: {e}")
                return

        except Exception as e:
            try:
                self.logger.error(f"설정 다이얼로그 표시 실패: {e}")
            except Exception:
                pass
            print(f"설정 다이얼로그 표시 실패: {e}")
