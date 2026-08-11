#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
실시간 거래 실행 및 포지션 모니터링
조건: 수익률 ≥ 슬리피지+수수료 시 자동청산
TP/SL 백업용 조건도 포함
"""

import time
import logging
import threading
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
import re, math, json, os

from trading.tp_sl_manager import TpSlManager
from .execution_optimizer import ExecutionOptimizer
from .ops_automation import OpsAutomationEngine
from .portfolio_orchestrator import PortfolioOrchestrator
from .opportunity_coordinator import (
    get_opportunity_coordinator,
    policy_from_settings,
)
from .profitability_validation import ProfitabilityValidator
from .strategy_engine import StrategyEngine
from .custom_strategy_runtime import apply_engine_settings_to_trade_config
from .custom_strategy_order_plan import (
    confirm_order_plan_action,
    evaluate_order_plan,
)
from .trade_candidate import apply_trade_candidate, evaluate_trade_candidate
from .exit_policy import (
    build_exit_policy,
    format_exit_policy,
    record_insurance_submission,
)
from .execution_mode import ExecutionMode, resolve_crypto_execution_mode
from .leverage_policy import exchange_leverage_cap, resolve_effective_leverage
from .market_data_utils import kline_number
from .position_ownership import (
    NOAH_POSITION_OWNER,
    is_noah_managed_position,
    managed_trade_map,
    normalize_position_symbol,
    parse_entry_time,
)
from api.kpi_client import emit_kpi_event, flush_kpi_events
from api.position_kpi import emit_position_closed, emit_position_opened, utc_now


class PositionSide(Enum):
    """포지션 방향"""
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class Position:
    """포지션 정보"""
    symbol: str
    side: PositionSide
    entry_price: float
    current_price: float
    quantity: float
    leverage: int
    unrealized_pnl: float
    unrealized_pnl_percent: float
    entry_time: datetime
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    position_id: Optional[str] = None
    entry_order_id: Optional[str] = None
    entry_order_ids: List[str] = field(default_factory=list)
    entry_time_source: str = "execution"
    execution_mode: str = "live"
    position_owner: str = "legacy_unknown"
    custom_strategy_id: Optional[str] = None
    custom_strategy_name: Optional[str] = None
    custom_strategy_rules: Dict[str, Any] = field(default_factory=dict)
    exit_policy: Dict[str, Any] = field(default_factory=dict)
    custom_order_plan_state: Dict[str, Any] = field(default_factory=dict)
    # 현물 자동매매가 시작되기 전부터 있던 잔고. 청산 시 이 수량은 절대
    # 매도하지 않고 앱이 체결한 증가분만 관리한다.
    spot_baseline_quantity: float = 0.0


@dataclass
class TradeSignal:
    """거래 신호"""
    symbol: str
    side: PositionSide
    confidence: float
    entry_price: float
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    quantity: Optional[float] = None
    leverage: Optional[int] = None
    reason: str = ""


from .recorder import TradeLog
from .advanced_orders import AdvancedOrderManager, OCOConfig, TrailingStopConfig, OrderType
# 바이낸스는 자체 API 사용 (api/binance_client.py)
# 안전한 log_adapter import (stdlib 'logging' 패키지와의 충돌 회피)
try:
    from log_system.log_adapter import log_exception  # type: ignore
except Exception:
    import os, sys
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _base_dir = os.path.dirname(_this_dir)  # noahai_client
    _logging_dir = os.path.join(_base_dir, 'log_system')
    if _logging_dir not in sys.path:
        sys.path.insert(0, _logging_dir)
    from log_adapter import log_exception  # type: ignore


def format_percent(value: float, decimal_places: int = 2) -> str:
    """✅ 퍼센트 변환 함수 통일"""
    return f"{value * 100:.{decimal_places}f}%"


def _as_utc(value: datetime) -> datetime:
    """Normalize persisted legacy timestamps and new aware timestamps to UTC."""
    if not isinstance(value, datetime):
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _elapsed_minutes(value: datetime) -> float:
    return max(0.0, (datetime.now(timezone.utc) - _as_utc(value)).total_seconds() / 60.0)


def _elapsed_milliseconds(value: datetime) -> int:
    return max(0, int((datetime.now(timezone.utc) - _as_utc(value)).total_seconds() * 1000))


class Trader:
    """실시간 거래 실행 및 포지션 모니터링"""
    # 클래스 수준 타입 힌트로 인스턴스 속성 타입을 명시 (정적 분석기 경고 감소)
    binance_client: Any
    analyzer: Any
    optimizer: Any
    recorder: Any
    ai_manager: Optional[Any]
    risk_manager: Optional[Any]
    websocket_manager: Any
    dashboard: Any
    settings: Dict
    active_positions: Dict[str, Position]
    trade_entered: Dict[str, bool]
    monitoring_flags: Dict[str, threading.Event]
    monitoring_threads: Dict[str, threading.Thread]
    monitoring_interval: int
    price_data_points: Dict[str, List]
    ai_pattern_analysis_cache: Dict[str, Dict]
    current_trading_coins: List[str]
    selected_coins: List[Any]
    tp_sl_watchdog_state: Dict[str, Dict]

    def __init__(self, binance_client: Any, analyzer: Any, optimizer: Any, recorder: Any, ai_manager: Optional[Any] = None,
                 risk_manager: Optional[Any] = None, websocket_manager: Any = None, dashboard: Any = None, logger: Any = None, settings: Optional[Dict] = None, main_app: Any = None):
        # 🔥 바이낸스는 자체 API 사용 (CCXT 사용 안함)
        self.binance_client = binance_client
        self.analyzer = analyzer
        self.optimizer = optimizer
        self.recorder = recorder
        self.ai_manager = ai_manager
        self.risk_manager = risk_manager
        self.websocket_manager = websocket_manager
        self.dashboard = dashboard  # 대시보드 참조 추가
        # 🔥 main.py에서 전달받은 logger 사용 (loguru)
        if logger:
            self.logger = logger
            print(f"🔧 Trader logger를 main.py logger로 설정: {type(self.logger).__name__}")
        else:
            self.logger = logging.getLogger(__name__)
            # 🔥 Logger 레벨을 INFO로 강제 설정 (DEBUG 로그 출력 보장)
            self.logger.setLevel(logging.INFO)

        # 🔥 로그 시스템 통일을 위한 헬퍼 메서드
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO', exchange='binance': log_event(category, msg, exchange=exchange, level=level)
        print(f"🔧 Trader logger 레벨을 INFO로 설정: {self.logger.level}")
        # 기본 settings 적용
        self.settings = settings or {}
        self.main_app = main_app
        self.strategy_customizer = None
        self.ai_trading_chatbot = None
        self._runtime_profile_applied = None
        self._learning_manager = None

        # TP/SL 매니저 초기화 (역할 분리 1단계)
        try:
            self.tp_sl_manager = TpSlManager(self)
        except Exception:
            # 초기화 실패 시에도 기존 동작을 유지하기 위해 무시
            self.tp_sl_manager = None

        # 활성 포지션 관리
        self.active_positions = {}
        self.paper_active_positions = {}

        # 🔥 autotrade.py와 동일: 거래 진입 여부 추적
        self.trade_entered = {}

        # 고급 주문 관리자 초기화
        self.advanced_order_manager = AdvancedOrderManager(
            binance_client=self.binance_client,
            websocket_manager=self.websocket_manager
        )

        # 실시간 모니터링 설정
        # 모니터링 관련 (심볼별 개별 관리로 개선)
        self.monitoring_flags = {}  # 심볼별 모니터링 플래그
        self.monitoring_threads = {}  # 심볼별 모니터링 스레드 핸들
        # settings.json의 auto_trade_interval을 사용 (기본 10초)
        self.monitoring_interval = int(self.settings.get("auto_trade_interval", 10))
        self.price_data_points = {}  # 실시간 가격 데이터 저장

        # AI 최적화 캐시 (기존 시스템 스타일)
        self.pattern_analysis_cache = {}
        self.portfolio_allocation_cache = {}
        self.cycle_execution_metrics = {}
        self.last_order_execution_metrics = {}
        self.external_position_symbols = set()

        # 동적 임계값 캐시 (모니터링 중 optimizer 호출 최적화)
        self.dynamic_thresholds_cache = {}  # {symbol: {'thresholds': {...}, 'timestamp': time}}

        # 거래 설정 - 외부 설정을 우선하고 기본값은 폴백으로만 사용
        DEFAULTS = {
            'default_leverage': 10,      # 스캘핑 기본 10x (수익률 증대)
            'default_tp': 0.0018,        # 0.18%
            'default_sl': 0.0020,        # 0.20%
            'max_positions': 3,          # 🔥 설정값과 일치 (기본값 3)
            'min_trade_amount': 5.0,
            'slippage_tolerance': 0.08,  # 스캘핑용 0.08% (기존 0.5%에서 대폭 하향)
            'include_fees': True,
            'taker_fee_percent_per_side': 0.02,  # 0.02% (계정 수수료에 맞춰 수정)
            'slippage_estimate_percent': 0.03,   # 0.03% 기본 추정치
            # 🔍 모니터링 로그 최적화 기본값
            'monitor_log_interval_sec': 60,      # 요약 로그 최소 간격(초)
            'monitor_pnl_delta_threshold': 0.05  # PnL 변화 임계값(%)
        }
        # 외부 설정을 우선하고, 없는 값만 기본값 사용
        self.settings = {**DEFAULTS, **(self.settings or {})}

        # ✅ 안전가드: 설정값이 퍼센트로 들어와도 자동 소수 변환
        self._normalize_tp_sl_settings()

        # 거래 통계 (DB에서 로드)
        self.trade_stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0
        }
        self.paper_trade_stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0,
        }

        # DB에서 이전 통계 로드
        if self._execution_mode() == ExecutionMode.LIVE:
            self._load_trade_stats_from_db()

        # 🔍 모니터링 로그 상태(최근 출력 시각/수치) 추적용
        # 예: { 'BTCUSDT': { 'last_log_ts': 0.0, 'last_pnl': 0.0 } }
        self.monitor_log_state = {}

        # 포지션 복구 (실제 거래소에서 조회)
        if self._execution_mode() == ExecutionMode.LIVE:
            self._restore_positions_from_exchange()
        elif self._execution_mode() == ExecutionMode.PAPER:
            self.log_event('system', "🧪 BINANCE PAPER 초기화 - 실제 포지션 복구 생략")

        # 현재 거래 코인 목록
        self.current_trading_coins = []
        # selected_coins가 다른 컴포넌트에서 주입되지 않는 경우를 대비하여 기본값 설정
        self.selected_coins = []

        # 🔥 Optimizer 설정 동기화 (TP/SL/레버리지 등)
        if self.optimizer and hasattr(self.optimizer, "update_settings"):
            # ✅ 최소주문금액/TP/SL/레버리지 등 동기화
            self.optimizer.update_settings(self.settings)
            self.log_event('system', "✅ Optimizer 설정을 Trader 설정으로 동기화 완료")

        # 🔥 설정값 검증 및 로깅
        min_trade_amount = self.settings.get('min_trade_amount', 5.0)
        self.log_event('system', f"✅ Trader 설정값 검증: min_trade_amount={min_trade_amount}")

        if min_trade_amount < 5.0:
            self.log_event('system', f"⚠️ min_trade_amount가 너무 작음: {min_trade_amount} → 5.0으로 조정", level='WARNING')
            self.settings['min_trade_amount'] = 5.0

        self.log_event('system', "Trader 초기화 완료 (고급 주문 기능 포함)")

        # 🔥 TP/SL 워치독 상태 저장용 딕셔너리 추가
        self.tp_sl_watchdog_state = {}  # {symbol: {"last_fix": 0, "checks": 0}}
        
        # 🔥 TP/SL 워치독 상태 파일 백업 경로 설정
        try:
            from path_utils import get_app_data_dir
            import os
            backup_dir = os.path.join(get_app_data_dir(), 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            self.tp_sl_watchdog_backup_path = os.path.join(backup_dir, 'tp_sl_watchdog_state.json')
            # 기존 백업 파일 로드 시도
            self._load_tp_sl_watchdog_backup()
        except Exception as e:
            self.log_event('system', f"⚠️ TP/SL watchdog 백업 경로 설정 실패: {e}", level='WARNING')
            self.tp_sl_watchdog_backup_path = None

    def _schedule_delayed_balance_update(self, delay_seconds: float = 2.0) -> None:
        """거래 직후 거래소 반영을 기다린 뒤 대시보드 잔고를 한 번 더 갱신한다.

        일부 포지션 처리 함수 안의 지역 ``import time`` 때문에 중첩 함수가
        아직 바인딩되지 않은 ``time``을 캡처하던 v3.9.0.3 회귀를 피하기 위해
        지연 갱신의 스레드 수명주기를 이 메서드 하나로 통합한다.
        """
        dashboard = getattr(self, "dashboard", None)
        if dashboard is None or not hasattr(dashboard, "update_balance_on_trade_completion"):
            return

        def delayed_balance_update():
            try:
                time.sleep(max(0.0, float(delay_seconds)))
                if hasattr(dashboard, "winfo_exists") and not dashboard.winfo_exists():
                    return
                if hasattr(dashboard, "thread_safe_after"):
                    dashboard.thread_safe_after(
                        0,
                        dashboard.update_balance_on_trade_completion,
                    )
                elif hasattr(dashboard, "after"):
                    dashboard.after(0, dashboard.update_balance_on_trade_completion)
                else:
                    dashboard.update_balance_on_trade_completion()
            except Exception as exc:
                try:
                    self.log_event(
                        "trade",
                        f"지연 잔고 갱신 실패: {exc}",
                        level="WARNING",
                    )
                except Exception:
                    pass

        threading.Thread(
            target=delayed_balance_update,
            daemon=True,
            name="delayed_balance_update",
        ).start()

    def configure_strategy_runtime(self, strategy_customizer: Any = None, ai_trading_chatbot: Any = None):
        """미연결 전략 모듈을 런타임 거래 루프에 연결한다."""
        self.strategy_customizer = strategy_customizer
        self.ai_trading_chatbot = ai_trading_chatbot

    def update_runtime_strategy_settings(self, new_settings: Dict):
        """전략 런타임 오버라이드 전용 설정 업데이트(재초기화 없음)."""
        if not isinstance(new_settings, dict) or not new_settings:
            return
        previous_mode = self._execution_mode()
        self.settings.update(new_settings)
        self.log_event('settings', f"전략 런타임 설정 업데이트: {new_settings}")
        if previous_mode != self._execution_mode():
            for flag in self.monitoring_flags.values():
                if hasattr(flag, 'set'):
                    flag.set()
            self.log_event(
                'settings',
                f"실행 모드 변경: {previous_mode.value} → {self._execution_mode().value}; 기존 모니터링 안전 중지",
            )

    def _apply_connected_strategy_runtime(self):
        """연결된 StrategyCustomizer/AITradingChatbot을 실제 거래 루프에 반영."""
        try:
            profile = str(self.settings.get('strategy_runtime_profile', '') or '').strip().lower()
            mode = str(self.settings.get('strategy_runtime_mode', 'adaptive') or 'adaptive').strip().lower()

            if self.ai_trading_chatbot and self._runtime_profile_applied != profile:
                if profile in getattr(self.ai_trading_chatbot, 'strategy_presets', {}):
                    self.ai_trading_chatbot.apply_strategy_changes({
                        'type': 'strategy_change',
                        'parameters': self.ai_trading_chatbot.strategy_presets[profile].parameters,
                    })
                    self._runtime_profile_applied = profile
                    self.log_event('strategy', f"전략 프로파일 적용: {profile}")
                elif not profile:
                    self._runtime_profile_applied = ''

            if mode == 'adaptive' and self.strategy_customizer:
                market_regime = 'NORMAL'
                try:
                    market_regime = str(self._analyze_market_regime_binance_fast() or 'NORMAL').upper()
                except Exception:
                    market_regime = 'NORMAL'

                performance = {
                    'recent_win_rate': 0.5,
                    'consecutive_losses': int(getattr(self.risk_manager, 'consecutive_losses', 0) or 0),
                }
                try:
                    if self.recorder and hasattr(self.recorder, 'get_recent_trades'):
                        rows = self.recorder.get_recent_trades(coin='', exchange='binance', days=14) or []
                        if isinstance(rows, list) and rows:
                            wins = 0
                            total = 0
                            for row in rows[-30:]:
                                if isinstance(row, dict):
                                    pnl = float(row.get('pnl_percent', row.get('pnl', 0.0)) or 0.0)
                                    total += 1
                                    if pnl > 0:
                                        wins += 1
                            if total > 0:
                                performance['recent_win_rate'] = wins / total
                except Exception:
                    pass

                # 과거 경로는 선택된 한 전략의 조정값을 글로벌 TP/SL·
                # 레버리지·Analyzer 임계값에 써서 다른 전략까지 오염시켰다.
                # 이제 컨텍스트만 보관하고 DeclarativeStrategyEngine이 실제로
                # 선택한 후보의 선언 규칙에만 적용한다.
                self._custom_strategy_runtime_context = {
                    'market_regime': market_regime,
                    'performance': dict(performance),
                }
                self.log_event(
                    'strategy',
                    f"adaptive 후보 컨텍스트 갱신: regime={market_regime}, "
                    f"win_rate={performance.get('recent_win_rate', 0.0):.2f}",
                    level='DEBUG',
                )
        except Exception as e:
            self.log_event('strategy', f"전략 런타임 반영 오류: {e}", level='WARNING')

    def _net_pnl_percent(self, raw_pnl_percent: float, leverage: int) -> float:
        """실질 수익률 계산 (수수료 + 슬리피지 차감)"""
        try:
            # 퍼센트 단위 사용 (코드 로그와 동일 스케일)
            fee_rt = float(self.settings.get('taker_fee_percent_per_side', 0.02))  # 0.02% per side
            slip_rt = float(self.settings.get('slippage_estimate_percent', 0.03))  # 0.03%

            # 왕복 수수료(%) + 슬리피지(%) 차감
            roundtrip_cost = (fee_rt * 2) + slip_rt

            # 실질 수익률 = 원시 수익률 - 왕복 비용
            net_pnl = raw_pnl_percent - roundtrip_cost

            # 🔇 과다 출력 방지: 상세 계산 로그는 verbose 모드에서만 노출
            self._log_trade_event('analysis', f"실질 수익률 계산: 원시 {raw_pnl_percent:.4f}% - 왕복비용 {roundtrip_cost:.4f}% = {net_pnl:.4f}%", verbose_only=True)

            return net_pnl

        except Exception as e:
            self.log_event('analysis', f"실질 수익률 계산 오류: {e}", level='ERROR')
            return raw_pnl_percent  # 오류 시 원시 수익률 반환

    def _tp_sl_watchdog(self, symbol: str, position: Position, check_idx: int) -> bool:
        """
        실시간 모니터링 중 주기적으로 TP/SL 존재여부를 점검하고,
        비정상(없거나 개수가 1:1이 아님)이면 즉시 복구한다.
        """
        try:
            # 과도한 재설정 방지(디바운스) - 더 짧게 조정
            st = self.tp_sl_watchdog_state.get(symbol, {"last_fix": 0, "checks": 0})
            now = time.time()
            if now - st.get("last_fix", 0) < 5:  # 최근 5초 내 조치했으면 skip (10초 → 5초)
                self.log_event('monitor', f"[{symbol}] ⏳ TP/SL watchdog cool-down 중")
                return True

            # 🔥 Algo Order API로 생성된 TP/SL은 별도 조회 필요
            open_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)
            open_algo_orders = self.binance_client.get_open_algo_orders(symbol=symbol)
            
            # 🔥 주문 타입 필터링 통일: 검증 로직과 동일하게 처리
            tp_orders = [o for o in open_orders if o.get('type') in ('TAKE_PROFIT', 'TAKE_PROFIT_MARKET')]
            sl_orders = [o for o in open_orders if o.get('type') in ('STOP', 'STOP_MARKET')]
            
            # Algo Order에서 TP/SL 추가
            for algo_order in open_algo_orders:
                # 🔥 Binance Algo Order API는 'type' 대신 'orderType' 필드 사용
                algo_type = (algo_order.get('orderType') or algo_order.get('type', '')).upper()
                if algo_type in ('TAKE_PROFIT_MARKET', 'TAKE_PROFIT'):
                    tp_orders.append(algo_order)
                elif algo_type in ('STOP_MARKET', 'STOP'):
                    sl_orders.append(algo_order)

            if len(tp_orders) == 1 and len(sl_orders) == 1:
                # 🔥 추가 검증: 주문 상태 확인 (Algo Order는 status가 없을 수 있음)
                tp_order = tp_orders[0]
                sl_order = sl_orders[0]
                tp_status_ok = tp_order.get('status') in ('NEW', 'PENDING') or 'status' not in tp_order
                sl_status_ok = sl_order.get('status') in ('NEW', 'PENDING') or 'status' not in sl_order
                if tp_status_ok and sl_status_ok:
                    self.log_event('order', f"[{symbol}] 🛡️ TP/SL watchdog OK (check#{check_idx}): TP 1, SL 1")
                    st["checks"] = st.get("checks", 0) + 1
                    self.tp_sl_watchdog_state[symbol] = st
                    return True
                else:
                    self.log_event('order', f"[{symbol}] ⚠️ TP/SL watchdog: 주문 상태 이상 (TP:{tp_order.get('status', 'N/A')}, SL:{sl_order.get('status', 'N/A')})", level='WARNING')

            # 비정상 → TP/SL만 선별 취소 후 재설정 (다른 주문 보호)
            self.log_event('order', f"[{symbol}] ⚠️ TP/SL watchdog detected abnormal state (check#{check_idx}): TP={len(tp_orders)}, SL={len(sl_orders)} → 중복 주문 감지! 재설정 시도", level='WARNING')
            try:
                if open_orders:
                    # 🔥 TP/SL만 선별 취소 (다른 주문 보호) - 문제 1 해결
                    tp_sl_to_cancel = [o for o in open_orders if o.get('type') in ('TAKE_PROFIT', 'TAKE_PROFIT_MARKET', 'STOP', 'STOP_MARKET')]
                    if tp_sl_to_cancel:
                        for order in tp_sl_to_cancel:
                            try:
                                self.binance_client.client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                                self.log_event('order', f"[{symbol}] TP/SL watchdog: 기존 주문 취소 {order['orderId']} ({order.get('type')})")
                            except Exception as e:
                                self.log_event('order', f"[{symbol}] TP/SL 주문 취소 실패: {e}", level='WARNING')
                        time.sleep(0.5)
                    else:
                        self.log_event('order', f"[{symbol}] TP/SL watchdog: 취소할 TP/SL 주문 없음")
            except Exception as e:
                self.log_event('order', f"[{symbol}] TP/SL 정리 실패(무시하고 재설정 진행): {e}", level='WARNING')

            # 재설정 가격 계산 (position 저장값 우선, 없으면 설정값으로 계산)
            try:
                info = self.binance_client.get_symbol_info_direct(symbol) or {}
                # 🔥 get_symbol_info_direct는 camelCase (pricePrecision)를 반환하므로 둘 다 시도
                price_prec = int(info.get('pricePrecision') or info.get('price_precision') or 2)
                # 저가 코인 보호
                entry = float(position.entry_price)
                if 0.001 <= entry <= 0.02:
                    min_prec_needed = max(4, len(str(entry).split('.')[-1].rstrip('0')))
                    if price_prec < min_prec_needed:
                        price_prec = min_prec_needed
            except Exception:
                price_prec = 2
                # 예외 시에도 진입가 기반 최소 정밀도 계산
                try:
                    entry = float(position.entry_price)
                    if 0.001 <= entry <= 0.02:
                        price_prec = max(4, len(str(entry).split('.')[-1].rstrip('0')))
                except:
                    pass

            entry = float(position.entry_price)
            
            # 🔥 백업 TP/SL 계산 (동적 임계값보다 높게)
            if position.tp_price is not None and position.sl_price is not None:
                # 이미 백업 TP/SL이 설정되어 있으면 그대로 사용
                tp_price = float(position.tp_price)
                sl_price = float(position.sl_price)
            else:
                # 백업 TP/SL이 없으면 동적으로 계산 (백업용이므로 넓게)
                try:
                    # settings.json에서 백업 TP/SL 설정 읽기
                    backup_cfg = self.settings.get('backup_tp_sl_settings', {})
                    multipliers = backup_cfg.get('multipliers', {})
                    safety_limits = backup_cfg.get('safety_limits', {})
                    volatility_thresholds = backup_cfg.get('volatility_thresholds', {})
                    
                    # 기본값 (폴백)
                    high_mult = float(multipliers.get('high_volatility', 3.0))
                    medium_mult = float(multipliers.get('medium_volatility', 2.5))
                    low_mult = float(multipliers.get('low_volatility', 2.0))
                    tp_min = float(safety_limits.get('tp_min', 0.01))
                    tp_max = float(safety_limits.get('tp_max', 0.05))
                    sl_min = float(safety_limits.get('sl_min', 0.008))
                    sl_max = float(safety_limits.get('sl_max', 0.03))
                    high_threshold = float(volatility_thresholds.get('high', 0.02))
                    medium_threshold = float(volatility_thresholds.get('medium', 0.01))
                    
                    # 동적 임계값 가져오기 (실시간 모니터링용)
                    dynamic_thresholds = self._calculate_dynamic_thresholds(symbol)
                    base_tp = dynamic_thresholds.get('profit_threshold', 0.0018)  # 소수 단위
                    base_sl = dynamic_thresholds.get('loss_threshold', 0.002)    # 소수 단위
                    
                    # 시장 변동성 기반 백업 multiplier (settings.json에서 읽음)
                    volatility = dynamic_thresholds.get('volatility', 0.01)
                    if volatility > high_threshold:  # 높은 변동성
                        backup_multiplier = high_mult
                    elif volatility > medium_threshold:  # 중간 변동성
                        backup_multiplier = medium_mult
                    else:  # 낮은 변동성
                        backup_multiplier = low_mult
                    
                    # 백업 TP/SL 계산 (동적 임계값보다 높게)
                    backup_tp = base_tp * backup_multiplier
                    backup_sl = base_sl * backup_multiplier
                    
                    # 안전 범위 제한 (settings.json에서 읽음)
                    backup_tp = max(tp_min, min(backup_tp, tp_max))
                    backup_sl = max(sl_min, min(backup_sl, sl_max))
                    
                    if position.side == PositionSide.LONG:
                        tp_price = entry * (1 + backup_tp)
                        sl_price = entry * (1 - backup_sl)
                    else:
                        tp_price = entry * (1 - backup_tp)
                        sl_price = entry * (1 + backup_sl)
                    
                    self.log_event('order', f"[{symbol}] 🔧 watchdog 백업 TP/SL 계산: 동적임계값 TP={base_tp:.4f}, SL={base_sl:.4f} → 백업 TP={backup_tp:.4f}, SL={backup_sl:.4f} (multiplier={backup_multiplier:.1f}x, 설정: high={high_mult}x/{high_threshold:.2%}, medium={medium_mult}x/{medium_threshold:.2%}, low={low_mult}x)")
                except Exception as e:
                    # 폴백: 기본값 2배
                    self.log_event('order', f"[{symbol}] ⚠️ watchdog 백업 TP/SL 계산 실패, 기본 2배 사용: {e}", level='WARNING')
                    tp_pct = float(self.settings.get('default_tp', 0.0018)) * 2.0  # 기본값 2배
                    sl_pct = float(self.settings.get('default_sl', 0.0020)) * 2.0
                    if position.side == PositionSide.LONG:
                        tp_price = entry * (1 + tp_pct)
                        sl_price = entry * (1 - sl_pct)
                    else:
                        tp_price = entry * (1 - tp_pct)
                        sl_price = entry * (1 + sl_pct)

            # 틱/정밀도 스냅
            tp_price = round(tp_price, price_prec)
            sl_price = round(sl_price, price_prec)

            qty = float(position.quantity)
            position_side = 'LONG' if position.side == PositionSide.LONG else 'SHORT'

            # 🔥 BinanceClient.place_tp_sl_orders() 사용 (Algo Order API 대응, v3.8.9.5+)
            tp_sl_result = []
            try:
                # side 인자는 엔트리 관점: LONG이면 BUY, SHORT면 SELL
                entry_side = 'BUY' if position_side == 'LONG' else 'SELL'
                
                # 🔥 BinanceClient.place_tp_sl_orders() 사용 (재시도 로직 포함)
                for retry in range(3):  # 최대 3회 재시도
                    try:
                        self.log_event('order', f"[{symbol}] 🔄 TP/SL 주문 생성 시도 (재시도 {retry+1}/3): TP={tp_price:.8f}, SL={sl_price:.8f}")
                        tp_order_result, sl_order_result = self.binance_client.place_tp_sl_orders(
                            symbol=symbol,
                            position_side=position_side,
                            take_profit=tp_price,
                            stop_loss=sl_price,
                            quantity=None,  # closePosition=True이므로 수량 불필요
                            price_precision=price_prec
                        )
                        
                        # 결과 파싱
                        tp_order = tp_order_result.get('order', {}) if isinstance(tp_order_result, dict) else tp_order_result
                        sl_order = sl_order_result.get('order', {}) if isinstance(sl_order_result, dict) else sl_order_result
                        
                        # 성공 여부 확인
                        tp_success = self.binance_client.is_order_success(tp_order_result) if tp_order_result else False
                        sl_success = self.binance_client.is_order_success(sl_order_result) if sl_order_result else False
                        
                        if tp_success and sl_success:
                            # orderId 추출 (Algo Order는 algoId 사용)
                            tp_order_id = tp_order_result.get('order_id') if isinstance(tp_order_result, dict) else None
                            sl_order_id = sl_order_result.get('order_id') if isinstance(sl_order_result, dict) else None
                            if not tp_order_id and isinstance(tp_order, dict):
                                tp_order_id = tp_order.get('orderId') or tp_order.get('algoId')
                            if not sl_order_id and isinstance(sl_order, dict):
                                sl_order_id = sl_order.get('orderId') or sl_order.get('algoId')
                            self.log_event('order', f"[{symbol}] ✅ TP/SL 주문 성공: TP={tp_order_id}, SL={sl_order_id}")
                            tp_sl_result = [tp_order, sl_order]
                            break
                        else:
                            error_msg = ""
                            if not tp_success:
                                error_msg += f"TP: {tp_order_result.get('error', 'Unknown')} "
                            if not sl_success:
                                error_msg += f"SL: {sl_order_result.get('error', 'Unknown')} "
                            position_closed = any(
                                isinstance(result, dict)
                                and result.get("code") == "position_not_open"
                                for result in (tp_order_result, sl_order_result)
                            )
                            if position_closed:
                                self.log_event(
                                    'order',
                                    f"[{symbol}] ⚠️ 열린 포지션 미확인 - 불필요한 TP/SL 재시도 중단",
                                    level='WARNING',
                                )
                                break
                            self.log_event('order', f"[{symbol}] ❌ TP/SL 주문 실패 (재시도 {retry+1}/3): {error_msg}", level='ERROR')
                            if retry < 2:
                                time.sleep(1.0)  # 재시도 전 대기
                    except Exception as e:
                        self.log_event('order', f"[{symbol}] ❌ TP/SL 주문 생성 예외 (재시도 {retry+1}/3): {e}", level='ERROR')
                        import traceback
                        self.log_event('order', f"[{symbol}] 상세 오류: {traceback.format_exc()}", level='ERROR')
                        if retry < 2:
                            time.sleep(1.0)
                
                # 최종 결과 확인
                if not tp_sl_result or len(tp_sl_result) < 2 or not tp_sl_result[0] or not tp_sl_result[1]:
                    tp_sl_result = [None, None]
            except Exception as e:
                self.log_event('order', f"[{symbol}] ❌ TP/SL 주문 설정 실패: {e}", level='ERROR')
                import traceback
                self.log_event('order', f"[{symbol}] ❌ TP/SL 주문 상세 오류: {traceback.format_exc()}", level='ERROR')
                tp_sl_result = [None, None]

            # 🔥 재설정 후 즉시 재검증 (재시도 로직)
            verification_passed = False
            for verify_attempt in range(2):  # 최대 2회 재검증
                wait_time = 1.0 + (verify_attempt * 0.5)  # 1초, 1.5초
                time.sleep(wait_time)
                
                # 🔥 Algo Order API로 생성된 TP/SL은 별도 조회 필요
                open_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)
                open_algo_orders = self.binance_client.get_open_algo_orders(symbol=symbol)
                
                tp_orders = [o for o in open_orders if o.get('type') in ('TAKE_PROFIT', 'TAKE_PROFIT_MARKET')]
                sl_orders = [o for o in open_orders if o.get('type') in ('STOP', 'STOP_MARKET')]
                
                # Algo Order에서 TP/SL 추가
                for algo_order in open_algo_orders:
                    # 🔥 Binance Algo Order API는 'type' 대신 'orderType' 필드 사용
                    algo_type = (algo_order.get('orderType') or algo_order.get('type', '')).upper()
                    if algo_type in ('TAKE_PROFIT_MARKET', 'TAKE_PROFIT'):
                        tp_orders.append(algo_order)
                    elif algo_type in ('STOP_MARKET', 'STOP'):
                        sl_orders.append(algo_order)

                if len(tp_orders) == 1 and len(sl_orders) == 1:
                    # 추가 검증: 주문 상태 확인 (Algo Order는 status가 없을 수 있음)
                    tp_order = tp_orders[0]
                    sl_order = sl_orders[0]
                    tp_status_ok = tp_order.get('status') in ('NEW', 'PENDING') or 'status' not in tp_order
                    sl_status_ok = sl_order.get('status') in ('NEW', 'PENDING') or 'status' not in sl_order
                    if tp_status_ok and sl_status_ok:
                        self.log_event('order', f"[{symbol}] ✅ TP/SL watchdog 복구 완료 (TP:{tp_orders[0].get('stopPrice', tp_orders[0].get('triggerPrice', '?'))}, SL:{sl_orders[0].get('stopPrice', sl_orders[0].get('triggerPrice', '?'))}) [검증 시도 {verify_attempt+1}/2]")
                        st["last_fix"] = now
                        st["checks"] = st.get("checks", 0) + 1
                        self.tp_sl_watchdog_state[symbol] = st
                        # 🔥 상태 변경 시 파일 백업 시도
                        self._save_tp_sl_watchdog_backup()
                        # position에도 저장(다음에 계산 없이 재사용)
                        position.tp_price = tp_price
                        position.sl_price = sl_price
                        verification_passed = True
                        break
            
            if not verification_passed:
                self.log_event('order', f"[{symbol}] ❌ TP/SL watchdog 복구 실패: TP={len(tp_orders)}, SL={len(sl_orders)}", level='ERROR')
                st["last_fix"] = now
                self.tp_sl_watchdog_state[symbol] = st
                # 🔥 상태 변경 시 파일 백업 시도
                self._save_tp_sl_watchdog_backup()
                return False
            
            return True

        except Exception as e:
            self.log_event('order', f"[{symbol}] TP/SL watchdog 오류: {e}", level='ERROR')
            return False

    def _start_monitoring(self, symbol: str, position: Position, manual: bool = False):
        """모니터링 시작 헬퍼 함수 (심볼별 개별 관리)"""
        try:
            self.log_event('monitor', f"[{symbol}] 🔍 모니터링 시작 시도 - position: {position.symbol if position else 'None'}")
            # 안전망: 모니터링 시작 시점에도 WebSocket 구독 보장
            try:
                self._ensure_ws_subscriptions(symbol)
            except Exception:
                pass

            # 심볼별 개별 모니터링 플래그 설정
            if symbol not in self.monitoring_flags:
                self.monitoring_flags[symbol] = threading.Event()

            # 🔥 모니터링 시작 전 플래그 명확히 클리어
            self.monitoring_flags[symbol].clear()
            self.log_event('monitor', f"[{symbol}] 🔧 모니터링 플래그 클리어 완료")

            monitoring_thread = threading.Thread(
                target=self.start_realtime_monitoring,
                args=(symbol, position),
                daemon=True
            )
            monitoring_thread.start()

            # 스레드 핸들 저장 (깔끔한 종료를 위해)
            self.monitoring_threads[symbol] = monitoring_thread

            mode_text = " (수동 모니터링)" if manual else ""
            self.log_event('monitor', f"[{symbol}] 실시간 모니터링 스레드 시작됨{mode_text}")
            self.log_event('monitor', f"[{symbol}] ✅ 모니터링 스레드 시작 완료{mode_text}")

            # 🔥 모니터링 시작 후 거래 플래그 해제 (다른 코인 거래 허용)
            self._reset_trade_flag(symbol)

        except Exception as e:
            self.log_event('monitor', f"[{symbol}] ❌ 모니터링 시작 실패: {e}", level='ERROR')

    def _is_dual_side(self):
        """포지션 모드 감지 (헤지/원웨이)"""
        try:
            r = self.binance_client.client.futures_get_position_mode()
            # {'dualSidePosition': True/False}
            return bool(r.get('dualSidePosition'))
        except Exception:
            return True  # 기본적으로 헤지모드 가정

    def _retry_tp_sl_setup(self, symbol: str, side: str, tp_price: float, sl_price: float, price_prec: int):
        """TP/SL 재설정 (검증 실패 시 호출) - 원자성 보장 강화"""
        try:
            self.logger.info(f"[{symbol}] 🔄 TP/SL 재설정 시작...")
            tp_order_id = None
            sl_order_id = None

            # 🔥 TP/SL만 선별 취소 (다른 주문은 유지)
            try:
                open_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)
                tp_sl_to_cancel = [o for o in open_orders if o.get('type') in ('TAKE_PROFIT', 'TAKE_PROFIT_MARKET', 'STOP', 'STOP_MARKET')]
                
                if tp_sl_to_cancel:
                    for order in tp_sl_to_cancel:
                        try:
                            self.binance_client.client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                            self.logger.info(f"[{symbol}] 기존 TP/SL 주문 취소: {order['orderId']} ({order.get('type')})")
                        except Exception as e:
                            self.logger.warning(f"[{symbol}] TP/SL 주문 취소 실패: {e}")
                    time.sleep(1.0)
                else:
                    self.logger.info(f"[{symbol}] 취소할 TP/SL 주문 없음")
            except Exception as e:
                self.logger.warning(f"[{symbol}] TP/SL 주문 조회 실패: {e}")
                # 폴백: 전체 취소 (최후의 수단)
                try:
                    self.binance_client.cancel_all_orders(symbol)
                    time.sleep(1.0)
                except:
                    pass

            position_side = 'LONG' if side == 'BUY' else 'SHORT'

            # 🔥 BinanceClient.place_tp_sl_orders() 사용 (Algo Order API 대응, v3.8.9.5+)
            try:
                tp_order_result, sl_order_result = self.binance_client.place_tp_sl_orders(
                    symbol=symbol,
                    position_side=position_side,
                    take_profit=tp_price,
                    stop_loss=sl_price,
                    quantity=None,  # closePosition=True이므로 수량 불필요
                    price_precision=price_prec
                )
                
                # 결과 파싱
                tp_order = tp_order_result.get('order', {}) if isinstance(tp_order_result, dict) else tp_order_result
                sl_order = sl_order_result.get('order', {}) if isinstance(sl_order_result, dict) else sl_order_result
                
                # 성공 여부 확인
                tp_success = self.binance_client.is_order_success(tp_order_result) if tp_order_result else False
                sl_success = self.binance_client.is_order_success(sl_order_result) if sl_order_result else False
                
                if tp_success and sl_success:
                    # orderId 추출 (Algo Order는 algoId 사용)
                    tp_order_id = tp_order_result.get('order_id') if isinstance(tp_order_result, dict) else None
                    sl_order_id = sl_order_result.get('order_id') if isinstance(sl_order_result, dict) else None
                    if not tp_order_id and isinstance(tp_order, dict):
                        tp_order_id = tp_order.get('orderId') or tp_order.get('algoId')
                    if not sl_order_id and isinstance(sl_order, dict):
                        sl_order_id = sl_order.get('orderId') or sl_order.get('algoId')
                    self.logger.info(f"[{symbol}] ✅ TP/SL 재설정 완료 (TP:{tp_order_id}, SL:{sl_order_id})")
                    return True
                else:
                    error_msg = ""
                    if not tp_success:
                        error_msg += f"TP: {tp_order_result.get('error', 'Unknown')} "
                    if not sl_success:
                        error_msg += f"SL: {sl_order_result.get('error', 'Unknown')} "
                    raise Exception(f"TP/SL 주문 생성 실패: {error_msg}")

            except Exception as create_e:
                self.logger.error(f"[{symbol}] ❌ TP/SL 재설정 중 주문 생성 실패: {create_e}")
                import traceback
                self.logger.error(f"[{symbol}] 상세 오류: {traceback.format_exc()}")
                # 🔥 원자성 보장: 부분 생성된 주문이 있으면 최후 방어로 취소 시도
                for rollback_id, label in ((tp_order_id, "TP"), (sl_order_id, "SL")):
                    if not rollback_id:
                        continue
                    try:
                        self.binance_client.client.futures_cancel_order(symbol=symbol, orderId=rollback_id)
                        self.logger.info(f"[{symbol}] {label} 주문 롤백 완료: {rollback_id}")
                    except Exception as cancel_e:
                        self.logger.warning(f"[{symbol}] {label} 주문 롤백 실패: {cancel_e}")
                return False

        except Exception as e:
            self.logger.error(f"[{symbol}] ❌ TP/SL 재설정 실패: {e}")
            return False

    def _tp_sl_order_params(self, side, tp_price, sl_price, price_prec, quantity=None):
        """
        TP/SL 주문 파라미터 생성 (포지션 모드 자동 감지)
        
        ⚠️ DEPRECATED: 이 메서드는 더 이상 사용되지 않습니다.
        대신 BinanceClient.place_tp_sl_orders() 또는 place_futures_order()를 사용하세요.
        """
        is_dual = self._is_dual_side()
        working_type = 'MARK_PRICE'
        try:
            if hasattr(self, 'settings') and isinstance(self.settings, dict):
                working_type = self.settings.get('tp_sl_working_type', 'MARK_PRICE') or 'MARK_PRICE'
        except Exception:
            pass

        # 🔥 closePosition=True 사용 시 reduceOnly 파라미터 제거 (바이낸스 API 규칙)
        # 타입 힌트를 위해 Dict[str, Any] 사용
        base: Dict[str, Any] = {}
        if is_dual:
            position_side = 'LONG' if side == 'BUY' else 'SHORT'
            base = {'positionSide': position_side, 'workingType': working_type}
        else:
            base = {'workingType': working_type}  # positionSide와 reduceOnly 모두 제거

        # 🔥 closePosition=True 사용 (전량 청산, 수량 문제 방지)
        base['closePosition'] = True
        # quantity 파라미터 제거 - closePosition이 더 안전함

        # 🔥 Precision 오류 방지: tickSize 기반 정밀도 스냅 강화
        # price_prec만으로는 부족할 수 있으므로 실제 tickSize로 스냅
        try:
            # 현재 심볼 정보 조회 (side에서 심볼 추출 불가하므로 호출 시점에서 전달받아야 함)
            # 임시로 price_prec 기반 안전한 반올림 사용
            from decimal import Decimal, ROUND_DOWN, ROUND_UP
            import math
            
            # price_prec를 기반으로 최소 단위 계산 (예: price_prec=4면 0.0001)
            min_tick = 10 ** (-price_prec)
            
            # TP는 올림, SL은 내림 (안전한 방향으로)
            tp_decimal = Decimal(str(tp_price))
            sl_decimal = Decimal(str(sl_price))
            tick_decimal = Decimal(str(min_tick))
            
            # TP: 올림 (더 높은 가격으로)
            tp_snapped = float((tp_decimal / tick_decimal).quantize(Decimal('1'), rounding=ROUND_UP) * tick_decimal)
            # SL: 내림 (더 낮은 가격으로)
            sl_snapped = float((sl_decimal / tick_decimal).quantize(Decimal('1'), rounding=ROUND_DOWN) * tick_decimal)
            
            # 최종 포맷팅 (price_prec 자릿수로 제한)
            tp_final = round(tp_snapped, price_prec)
            sl_final = round(sl_snapped, price_prec)
            
        except Exception as snap_err:
            # 폴백: 기본 반올림
            self.logger.warning(f"TP/SL 가격 스냅 실패, 기본 반올림 사용: {snap_err}")
            tp_final = round(tp_price, price_prec)
            sl_final = round(sl_price, price_prec)

        return (
            {'type': 'TAKE_PROFIT_MARKET', 'stopPrice': tp_final, **base},
            {'type': 'STOP_MARKET', 'stopPrice': sl_final, **base},
        )

    def _get_position_info_with_retry(self, symbol: str, attempts: int = 3, delay: float = 0.2):
        info = None
        for _ in range(max(1, attempts)):
            try:
                info = self.binance_client.get_position_info(symbol)
                if info and abs(float(info.get('positionAmt', 0))) != 0:
                    return info
            except Exception:
                pass
            time.sleep(max(0.0, delay))
        return info

    # WS 책임 이관: 클라이언트 보장 API 호출만 사용
    def _ensure_ws_subscriptions(self, symbol: str) -> bool:
        try:
            if hasattr(self, 'binance_client') and hasattr(self.binance_client, 'ensure_ws_for'):
                ok = self.binance_client.ensure_ws_for(symbol)
                # 상태 로그 보강(클라이언트가 이미 로그를 내더라도 트레이더 관점에서 1줄 남김)
                self.log_event('monitor', f"[{symbol}] WS 보장 호출 결과: {'OK' if ok else 'NG'}")
                return ok
            # 폴백: 기존 매니저가 직접 주입된 경우
            if hasattr(self, 'websocket_manager') and hasattr(self.websocket_manager, 'subscribe_symbol'):
                return bool(self.websocket_manager.subscribe_symbol(symbol))
            self.log_event('monitor', f"[{symbol}] ⚠️ WS 보장 불가: 클라이언트/매니저 미탑재", level='WARNING')
            return False
        except Exception as e:
            self.log_event('monitor', f"[{symbol}] ⚠️ WS 보장 호출 오류: {e}", level='WARNING')
            return False

    def _reset_trade_flag(self, symbol: str):
        """거래 진행 플래그 해제 헬퍼 함수 (중복 제거)"""
        if symbol and symbol in self.trade_entered:
            self.trade_entered[symbol] = False
            self.log_event('trade', f"[{symbol}] 거래 집중 모드 완료")

    def _cleanup_zombie_flags(self):
        """좀비 플래그 정리 (포지션 없는데 trade_entered=True인 경우)"""
        try:
            self.log_event('trade', "🔍 좀비 플래그 정리 시작")
            zombie_symbols = []

            # 1. 포지션 없는데 거래 플래그가 True인 경우
            for symbol, is_trading in self.trade_entered.items():
                if is_trading and symbol not in self.active_positions:
                    # 모니터링 스레드도 확인
                    has_monitoring_thread = symbol in self.monitoring_threads
                    if has_monitoring_thread:
                        thread = self.monitoring_threads[symbol]
                        if not thread.is_alive():
                            zombie_symbols.append(symbol)
                            self.log_event('trade', f"[{symbol}] 좀비 플래그 감지 - 자동 정리 (포지션 없음, 스레드 종료됨)", level='WARNING')
                    else:
                        zombie_symbols.append(symbol)
                        self.log_event('trade', f"[{symbol}] 좀비 플래그 감지 - 자동 정리 (포지션 없음, 스레드 없음)", level='WARNING')

            self.log_event('trade', f"🔍 1차 좀비 플래그 발견: {len(zombie_symbols)}개 - {zombie_symbols}")

            # 2. 실제 거래소에서 포지션 조회해서 확인
            try:
                if hasattr(self, 'binance_client') and self.binance_client:
                    actual_positions = self.binance_client.get_positions()
                    # BinanceClient.get_positions()는 Position 객체 리스트를 반환함
                    # 혹시 dict 형태가 섞여 오더라도 안전하게 symbol을 추출하도록 처리
                    actual_symbols = {
                        (pos['symbol'] if isinstance(pos, dict) else getattr(pos, 'symbol', None))
                        for pos in actual_positions
                        if (isinstance(pos, dict) and 'symbol' in pos) or hasattr(pos, 'symbol')
                    }

                    for symbol, is_trading in self.trade_entered.items():
                        if is_trading and symbol not in actual_symbols and symbol not in zombie_symbols:
                            zombie_symbols.append(symbol)
                            self.log_event('trade', f"[{symbol}] 좀비 플래그 감지 - 자동 정리 (실제 거래소에 포지션 없음)", level='WARNING')
            except Exception as e:
                self.log_event('trade', f"⚠️ 실제 포지션 조회 실패: {e}", level='WARNING')

            self.log_event('trade', f"🔍 2차 검증 후 좀비 플래그: {len(zombie_symbols)}개 - {zombie_symbols}")

            # 3. 좀비 플래그 정리
            for symbol in zombie_symbols:
                self._reset_trade_flag(symbol)
                # 모니터링 스레드 핸들도 정리
                if symbol in self.monitoring_threads:
                    del self.monitoring_threads[symbol]
                if symbol in self.monitoring_flags:
                    del self.monitoring_flags[symbol]

            if zombie_symbols:
                self.log_event('trade', f"✅ 좀비 플래그 정리 완료: {len(zombie_symbols)}개 심볼 - {zombie_symbols}")
            else:
                self.log_event('trade', "✅ 좀비 플래그 없음 - 정리 작업 완료")

        except Exception as e:
            self.log_event('trade', f"❌ 좀비 플래그 정리 중 오류: {e}", level='ERROR')

    def _cleanup_all_open_orders(self):
        """거래 사이클 시작 전 모든 오픈오더 정리"""
        try:
            self.log_event('trade', "🔍 전체 오픈오더 정리 시작")

            if not hasattr(self, 'binance_client') or not self.binance_client:
                self.log_event('trade', "⚠️ binance_client 없음 - 오픈오더 정리 건너뜀")
                return

            # 모든 오픈오더 조회
            open_orders = self.binance_client.client.futures_get_open_orders()

            if not open_orders:
                self.log_event('trade', "✅ 거래 사이클 시작: 오픈오더 없음")
                return

            # 심볼별로 그룹화
            symbol_orders = {}
            for order in open_orders:
                symbol = order['symbol']
                if symbol not in symbol_orders:
                    symbol_orders[symbol] = []
                symbol_orders[symbol].append(order)

            self.log_event('trade', f"⚠️ 거래 사이클 시작: {len(open_orders)}개 오픈오더 발견 ({len(symbol_orders)}개 심볼)")

            # 각 심볼별로 오픈오더 정리 (TP/SL 제외)
            cleaned_count = 0
            for symbol, orders in symbol_orders.items():
                try:
                    # 🔥 TP/SL 타입 필터링 (보호해야 할 주문 유형)
                    tp_sl_types = ('TAKE_PROFIT', 'TAKE_PROFIT_MARKET', 'STOP', 'STOP_MARKET', 'STOP_LOSS', 'STOP_LOSS_LIMIT')
                    other_orders = [o for o in orders if o.get('type') not in tp_sl_types]
                    tp_sl_orders = [o for o in orders if o.get('type') in tp_sl_types]

                    if tp_sl_orders:
                        self.log_event('trade', f"[{symbol}] TP/SL 주문 {len(tp_sl_orders)}개 보호 (정리 제외)")

                    if not other_orders:
                        self.log_event('trade', f"[{symbol}] TP/SL만 존재 - 정리 건너뜀")
                        continue

                    self.log_event('trade', f"[{symbol}] TP/SL 외 오픈오더 정리: {len(other_orders)}개 (전체 {len(orders)}개 중)")

                    # 🔥 TP/SL이 아닌 주문만 개별 취소
                    success_count = 0
                    for order in other_orders:
                        try:
                            order_id = order['orderId']
                            order_type = order.get('type', 'UNKNOWN')
                            cancel_result = self.binance_client.client.futures_cancel_order(symbol=symbol, orderId=order_id)

                            if cancel_result.get('status') == 'CANCELED':
                                self.log_event('trade', f"[{symbol}] 개별 주문 취소 완료: {order_id} (타입: {order_type})")
                                success_count += 1
                            else:
                                self.log_event('trade', f"[{symbol}] 개별 주문 취소 실패: {order_id} - 상태: {cancel_result.get('status', 'UNKNOWN')}", level='WARNING')
                        except Exception as e:
                            self.log_event('trade', f"[{symbol}] 개별 주문 취소 실패: {order.get('orderId', 'N/A')} - {e}", level='WARNING')

                    if success_count > 0:
                        cleaned_count += success_count
                        self.log_event('trade', f"[{symbol}] ✅ 오픈오더 정리 완료: {success_count}개 취소")

                    time.sleep(0.2)  # API 호출 간격 증가
                except Exception as e:
                    self.log_event('trade', f"[{symbol}] ❌ 오픈오더 정리 실패: {e}", level='WARNING')

            if cleaned_count > 0:
                self.log_event('trade', f"✅ 거래 사이클 시작: 총 {cleaned_count}개 오픈오더 정리 완료")
            else:
                self.log_event('trade', "⚠️ 거래 사이클 시작: 오픈오더 정리 실패")

        except Exception as e:
            self.log_event('trade', f"❌ 전체 오픈오더 정리 중 오류: {e}", level='ERROR')

    def _is_verbose_logging(self) -> bool:
        try:
            return bool(self.settings.get('verbose_trade_logging', False))
        except Exception:
            return False

    def _log_trade_event(self, category: str, message: str, exchange: str = 'binance', level: str = 'INFO', verbose_only: bool = False):
        """대시보드/파일 동시 전송용 표준 로그 헬퍼.
        verbose_only=True이면 설정 플래그가 켜진 경우에만 출력.
        """
        try:
            if verbose_only and not self._is_verbose_logging():
                return
            # 🔥 중복 제거: self.log_event로 통일
            self.log_event(category, message, exchange=exchange, level=level)
        except Exception:
            pass

    def _log_trade_entry(
        self,
        symbol: str,
        side: str,
        actual_entry_price: float,
        tp_price: float,
        sl_price: float,
        leverage: int,
        mode: str,
        manual: bool = False,
        *,
        order_id: Optional[str] = None,
        fees: float = 0.0,
        fee_asset: Optional[str] = None,
        fee_source: Optional[str] = None,
        model_version: Optional[str] = None,
        strategy_variant: Optional[str] = None,
    ):
        """거래 진입 로그 저장 헬퍼 함수 (중복 제거)"""
        try:
            mode_suffix = "_manual" if manual else ""
            reason_suffix = " (TP/SL 실패, 수동 모니터링)" if manual else ""

            # 🔥 TP/SL 값 검증 및 기본값 적용 (문제 2 해결)
            default_tp = float(self.settings.get('default_tp', 0.0018))
            default_sl = float(self.settings.get('default_sl', 0.0020))
            
            # tp_price 검증 및 기본값 적용
            if tp_price is None or tp_price <= 0:
                if str(side).upper() == 'BUY' or str(side).upper() == 'LONG':
                    tp_price = actual_entry_price * (1 + default_tp)
                else:  # SHORT
                    tp_price = actual_entry_price * (1 - default_tp)
                self.log_event('trade', f"⚠️ {symbol} TP 가격이 없어 기본값 사용: {tp_price:.8f}", level='WARNING')
            
            # sl_price 검증 및 기본값 적용
            if sl_price is None or sl_price <= 0:
                if str(side).upper() == 'BUY' or str(side).upper() == 'LONG':
                    sl_price = actual_entry_price * (1 - default_sl)
                else:  # SHORT
                    sl_price = actual_entry_price * (1 + default_sl)
                self.log_event('trade', f"⚠️ {symbol} SL 가격이 없어 기본값 사용: {sl_price:.8f}", level='WARNING')

            # TradeLog 객체 생성 (recorder.py의 insert_trade_log 함수가 TradeLog 객체를 요구함)
            from trading.recorder import TradeLog

            # 실제 포지션 수량 계산 (position 객체에서 가져오기)
            actual_quantity = 0.0
            if symbol in self.active_positions:
                actual_quantity = self.active_positions[symbol].quantity

            trade_log = TradeLog(
                id=None,
                symbol=symbol,
                entry_price=actual_entry_price,
                exit_price=None,  # 진입 시에는 미청산 상태 유지
                quantity=actual_quantity,  # 🔥 실제 포지션 수량 사용
                leverage=leverage,
                pnl=None,  # 청산 시에만 설정
                pnl_percent=None,
                entry_time=datetime.now(timezone.utc),
                exit_time=None,  # 청산 시에만 설정
                reason=f"AI {mode} mode{reason_suffix}",
                side=side,
                tp_price=tp_price,  # 🔥 검증된 값 사용
                sl_price=sl_price,  # 🔥 검증된 값 사용
                fees=max(0.0, float(fees or 0.0)),
                slippage=0.0,
                exchange=self.settings.get('selected_exchange', 'binance'),
                order_id=str(order_id) if order_id is not None else None,
                model_version=model_version,
                strategy_variant=strategy_variant,
                fee_asset=fee_asset,
                fee_source=fee_source,
                position_owner=NOAH_POSITION_OWNER,
                execution_mode=str(mode or 'live'),
            )

            self.recorder.insert_trade_log(trade_log)
            self.log_event('trade', f"{symbol} {side} 진입 완료{' (수동 모니터링)' if manual else ''} - 진입가: {actual_entry_price}, 레버리지: {leverage}x")

            # 대시보드 요약 로그 전송
            pretty_side = 'LONG' if str(side).upper() == 'BUY' else 'SHORT'
            msg = (
                f"{symbol} {pretty_side} 진입 | entry {actual_entry_price:.4f}, TP {tp_price:.4f}, SL {sl_price:.4f}, lev {leverage}x, mode {mode}"
            )
            self._log_trade_event('trade', msg, exchange='binance', level='INFO')

        except Exception as e:
            self.log_event('trade', f"[{symbol}] 거래 로그 저장 실패: {e}", level='ERROR')

    def _record_binance_execution(
        self,
        symbol: str,
        side: str,
        order_result: Optional[Dict[str, Any]],
        *,
        source: str,
        fallback_quantity: float = 0.0,
        fallback_price: float = 0.0,
        fee: float = 0.0,
        fee_asset: Optional[str] = None,
    ) -> bool:
        """Binance 네이티브 체결도 공통 실제 체결 원장에 기록한다.

        CCXT 거래소와 달리 기존 Binance 경로는 ``trade_log``만 갱신하고
        ``exchange_execution_log``를 전혀 생산하지 않아 거래소 대시보드의
        실제 체결 목록과 공통 동기화 진단에서 누락됐다.
        """
        if not isinstance(order_result, dict):
            return False
        recorder = getattr(self, 'recorder', None)
        receipt_saver = getattr(recorder, 'save_exchange_order_receipt', None)
        execution_saver = getattr(recorder, 'save_exchange_execution_history', None)
        if not callable(receipt_saver) and not callable(execution_saver):
            return False
        try:
            raw = order_result.get('order')
            payload = dict(raw) if isinstance(raw, dict) else {}
            order_id = (
                payload.get('orderId') or payload.get('id')
                or order_result.get('order_id') or order_result.get('orderId')
                or order_result.get('id')
            )
            status = str(
                payload.get('status') or order_result.get('status') or ''
            ).upper()
            quantity = float(
                payload.get('executedQty') or order_result.get('executed_qty')
                or order_result.get('filled') or fallback_quantity or 0.0
            )
            price = float(
                payload.get('avgPrice') or order_result.get('avg_price')
                or order_result.get('average') or order_result.get('price')
                or fallback_price or 0.0
            )
            cost = float(
                payload.get('cumQuote') or order_result.get('cum_quote')
                or order_result.get('cost') or 0.0
            )
            if cost <= 0 and price > 0 and quantity > 0:
                cost = price * quantity
            confirmed = quantity > 0 and status in {
                'FILLED', 'PARTIALLY_FILLED', 'SUCCESS', 'CLOSED'
            }
            payload.update({
                'id': str(order_id or ''),
                'order': str(order_id or ''),
                'symbol': str(symbol or '').upper(),
                'side': str(side or '').lower(),
                'average': price,
                'price': price,
                'amount': quantity,
                'filled': quantity,
                'cost': cost,
                'timestamp': payload.get('updateTime') or payload.get('time') or int(time.time() * 1000),
                'status': status,
                'fee': {'cost': max(0.0, float(fee or 0.0)), 'currency': fee_asset or 'USDT'},
                '_execution_confirmed': confirmed,
            })
            if callable(receipt_saver):
                receipt_saver('binance', payload, source=source)
            if confirmed and callable(execution_saver):
                result = execution_saver('binance', [payload], source=source)
                return int((result or {}).get('inserted', 0) or 0) > 0 or int(
                    (result or {}).get('skipped', 0) or 0
                ) > 0
            self.log_event(
                'trade',
                f"[{symbol}] Binance 주문 접수 원장 저장 · 실제 체결 확인 대기 ({status or 'UNKNOWN'})",
                level='WARNING',
            )
            return False
        except Exception as exc:
            self.log_event(
                'trade',
                f"[{symbol}] Binance 공통 체결 원장 기록 실패: {exc}",
                level='ERROR',
            )
            return False

    def _get_order_commission(
        self,
        symbol: str,
        order_id: Optional[Any],
        *,
        attempts: int = 2,
    ) -> tuple[float, Optional[str], str]:
        """거래소 체결내역에서 주문 수수료를 조회한다. 추정값은 저장하지 않는다."""
        if order_id in (None, "") or not self.binance_client:
            return 0.0, None, "unavailable"
        target = str(order_id)
        for attempt in range(max(1, attempts)):
            try:
                rows = self.binance_client.get_trade_history(symbol, limit=200) or []
                fills = [row for row in rows if str(row.get("order_id", "")) == target]
                if fills:
                    assets = {
                        str(row.get("commission_asset", "") or "").upper()
                        for row in fills
                        if row.get("commission_asset")
                    }
                    asset = next(iter(assets)) if len(assets) == 1 else ("MIXED" if assets else None)
                    return (
                        sum(max(0.0, float(row.get("commission", 0.0) or 0.0)) for row in fills),
                        asset,
                        "exchange_fill",
                    )
            except Exception:
                pass
            if attempt + 1 < attempts:
                time.sleep(0.25)
        return 0.0, None, "unavailable"

    def _normalize_tp_sl_settings(self):
        """TP/SL 설정값을 공통 fraction 범위로 정규화한다."""
        try:
            from config.settings import normalize_trade_rate
            old_tp = self.settings.get('default_tp', 0.0018)
            old_sl = self.settings.get('default_sl', 0.002)
            self.settings['default_tp'], tp_changed = normalize_trade_rate(old_tp, kind="tp")
            self.settings['default_sl'], sl_changed = normalize_trade_rate(old_sl, kind="sl")
            if tp_changed or sl_changed:
                self.log_event(
                    'settings',
                    f"TP/SL 비정상 단위·범위 차단: tp={old_tp}, sl={old_sl} "
                    f"→ tp={self.settings['default_tp']}, sl={self.settings['default_sl']}",
                    level='WARNING',
                )

            self.log_event(
                'settings',
                "✅ TP/SL 설정 확인 완료 (주문 단위 fraction): "
                f"tp={self.settings['default_tp']:.6f}, "
                f"sl={self.settings['default_sl']:.6f}",
            )

        except Exception as e:
            self.log_event('settings', f"TP/SL 설정 정규화 오류: {e}", level='ERROR')

    def create_oco_order(self, symbol: str, side: str, quantity: float, tp_price: float, sl_price: float) -> str:
        """OCO 주문 생성"""
        try:
            oco_config = OCOConfig(
                take_profit_price=tp_price,
                stop_loss_price=sl_price
            )

            order_id = self.advanced_order_manager.create_oco_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                oco_config=oco_config
            )

            self.log_event('order', f"OCO 주문 생성: {symbol}, TP: {tp_price}, SL: {sl_price}")
            return order_id

        except Exception as e:
            self.log_event('order', f"OCO 주문 생성 실패: {e}", level='ERROR')
            raise

    def create_trailing_stop_order(self, symbol: str, side: str, quantity: float, entry_price: float, callback_rate: float = 0.02) -> str:
        """트레일링 스탑 주문 생성"""
        try:
            trailing_config = TrailingStopConfig(
                callback_rate=callback_rate  # 기본 2% 트레일링
            )

            order_id = self.advanced_order_manager.create_trailing_stop_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                trailing_config=trailing_config,
                entry_price=entry_price
            )

            self.log_event('order', f"트레일링 스탑 생성: {symbol}, 콜백: {callback_rate*100:.1f}%")
            return order_id

        except Exception as e:
            self.log_event('order', f"트레일링 스탑 생성 실패: {e}", level='ERROR')
            raise

    def get_advanced_orders_status(self) -> List[Dict]:
        """고급 주문 상태 조회"""
        try:
            return self.advanced_order_manager.get_active_orders()
        except Exception as e:
            self.log_event('order', f"고급 주문 상태 조회 실패: {e}", level='ERROR')
            return []

    def cancel_advanced_order(self, order_id: str) -> bool:
        """고급 주문 취소"""
        try:
            return self.advanced_order_manager.cancel_order(order_id, "사용자 요청")
        except Exception as e:
            self.log_event('order', f"고급 주문 취소 실패: {e}", level='ERROR')
            return False

    def update_settings(self, new_settings: Dict):
        """설정 업데이트"""
        sanitized = dict(new_settings or {})
        from config.settings import normalize_trade_rate
        for key, kind in (("default_tp", "tp"), ("default_sl", "sl")):
            if key in sanitized:
                fallback, _ = normalize_trade_rate(
                    self.settings.get(key, 0.0018 if kind == "tp" else 0.0020),
                    kind=kind,
                )
                sanitized[key], changed = normalize_trade_rate(
                    sanitized[key], kind=kind, fallback=fallback
                )
                if changed:
                    try:
                        raw_rate = float(new_settings[key])
                        maximum = 0.05 if kind == "tp" else 0.03
                        legacy_percent = (
                            math.isfinite(raw_rate) and maximum < raw_rate <= 5.0
                        )
                    except Exception:
                        legacy_percent = False
                    if legacy_percent:
                        self.log_event(
                            'settings',
                            f"{key} 레거시 퍼센트 단위 자동 변환: "
                            f"{new_settings[key]} → {sanitized[key]}",
                            level='INFO',
                        )
                    else:
                        self.log_event(
                            'settings',
                            f"{key} 비정상 입력 안전값 복구: "
                            f"{new_settings[key]} → {sanitized[key]}",
                            level='WARNING',
                        )
        self.settings.update(sanitized)
        self.log_event('settings', f"거래 설정 업데이트: {sanitized}")

    def _check_and_reselect_coins_optimized(self):
        """최적화된 코인 재선택 로직 (빠른 시장 분석)"""
        try:
            self.log_event('coin_selection', "_check_and_reselect_coins_optimized 함수 시작")

            # 1. 코인이 비어있으면 선택
            # 🔥 main_app.selected_coins를 확인 (실제 코인 저장 위치)
            selected_coins = getattr(self.main_app, 'selected_coins', []) if hasattr(self, 'main_app') and self.main_app else []
            if not selected_coins:
                self.log_event('coin_selection', "선택된 코인 없음 - 코인 선택 실행")
                # 🔥 코인이 비어있을 때는 즉시 코인 선택 실행
                if hasattr(self, 'main_app') and self.main_app and hasattr(self.main_app, 'select_trading_coins'):
                    self.main_app.select_trading_coins()
                    self.log_event('coin_selection', f"코인 선택 완료: {len(getattr(self.main_app, 'selected_coins', []))}개")
                else:
                    self.log_event('coin_selection', "main_app 또는 select_trading_coins 없음 - 코인 선택 불가", level='WARNING')
                return

            self.log_event('coin_selection', f"선택된 코인 수: {len(selected_coins)}")

            # 2. 시장 상황 변화 체크 (1시간마다) - 최적화
            import time
            current_time = time.time()

            if not hasattr(self, 'last_market_analysis_time'):
                # 첫 실행 시 시간 기록 (거래 시작 시점) - 정상 시장 분석 수행
                self.last_market_analysis_time = current_time
                regime = self._analyze_market_regime_binance_fast()
                self.last_market_regime = regime
                self.log_event('analysis', f"시장 분석 시작 - 기준 시간: {time.strftime('%H:%M:%S', time.localtime(current_time))}")
                self.log_event('analysis', f"시장 상황 분석 결과: {regime}")
                return

            # 1시간 경과 체크 (거래 시작 시점 기준)
            time_elapsed = current_time - self.last_market_analysis_time
            if time_elapsed > 3600:  # 1시간
                self.log_event('analysis', f"1시간 경과 - 시장 재분석 시작 (경과: {time_elapsed/3600:.1f}시간)")

                current_regime = self._analyze_market_regime_binance_fast()

                # 🔥 시간 업데이트 플래그: 재선택 실행/연기 여부에 따라 결정
                should_update_time = False

                if hasattr(self, 'last_market_regime') and current_regime != self.last_market_regime:
                    self.logger.info(f"시장 상황 변경 감지: {self.last_market_regime} → {current_regime}")

                    # 3. 거래 진행 중인지 확인
                    active_positions = self.get_active_positions()
                    max_positions = self.settings.get('max_positions', 3)
                    
                    # 🔥 개선: 활성 포지션이 있어도 최대 포지션 수의 50% 이하일 때는 재선택 허용
                    if active_positions and len(active_positions) >= max_positions * 0.5:
                        # 활성 포지션이 많으면 재선택 연기
                        self.logger.warning(f"거래 진행 중 - 코인 재선택 연기 (활성 포지션: {len(active_positions)}개 >= {max_positions * 0.5:.1f}개)")
                        self.logger.info("활성 포지션이 많아 재선택 연기 - 다음 사이클에서 재선택 예정")
                        should_update_time = True  # 재선택 연기 시 시간 업데이트 (다음 사이클에서 재체크)
                    else:
                        # 활성 포지션이 적거나 없으면 재선택 실행
                        self.logger.info(f"거래 없음 또는 적음 - 코인 재선택 실행 (활성 포지션: {len(active_positions)}개 < {max_positions * 0.5:.1f}개)")
                        self._reselect_coins()
                        should_update_time = True  # 재선택 실행 시 시간 업데이트
                else:
                    # 🔥 시장 상황이 유지되어도 3시간마다 강제 재선택 (코인 다양성 확보)
                    if time_elapsed > 10800:  # 3시간
                        active_positions = self.get_active_positions()
                        max_positions = self.settings.get('max_positions', 3)
                        if len(active_positions) < max_positions * 0.7:  # 70% 미만일 때만 재선택
                            self.logger.info(f"3시간 경과 - 코인 다양성 확보를 위한 강제 재선택 (활성 포지션: {len(active_positions)}개)")
                            self._reselect_coins()
                            should_update_time = True  # 재선택 실행 시 시간 업데이트
                        else:
                            self.logger.info(f"3시간 경과했으나 활성 포지션 많음 - 재선택 연기 (활성 포지션: {len(active_positions)}개 >= {max_positions * 0.7:.1f}개)")
                            should_update_time = True  # 재선택 연기 시 시간 업데이트
                    else:
                        # 🔥 시장 상황 유지 + 1시간 < 경과 < 3시간: 시간 업데이트 안 함 (다음 사이클에서 계속 1시간 체크)
                        self.logger.info(f"시장 상황 유지: {current_regime} (1시간 경과, 3시간 미만 - 재선택 대기)")
                        should_update_time = False  # 시간 업데이트 안 함

                # 🔥 조건부 시간 업데이트: 재선택 실행/연기한 경우에만 시간 업데이트
                if should_update_time:
                    self.last_market_regime = current_regime
                    self.last_market_analysis_time = current_time

        except Exception as e:
            self.logger.error(f"코인 재선택 체크 오류: {e}")

    def _reselect_coins(self):
        """실제 코인 재선택 실행"""
        try:
            self.logger.info("🔄 코인 재선택 시작...")

            # 1. 현재 시장 상황 분석
            current_regime = self._analyze_market_regime_binance()
            self.logger.info(f"현재 시장 상황: {current_regime}")

            # 2. 기존 코인 백업
            # 🔥 main_app.selected_coins를 확인 (실제 코인 저장 위치)
            old_coins = getattr(self.main_app, 'selected_coins', []) if hasattr(self, 'main_app') and self.main_app else []
            if isinstance(old_coins, list):
                old_coins = old_coins.copy()
            self.logger.info(f"기존 코인: {len(old_coins)}개")

            # 3. 새로운 코인 선택 (main.py의 select_trading_coins 호출)
            if hasattr(self, 'main_app') and self.main_app:
                self.main_app.select_trading_coins()
                new_coins = self.main_app.selected_coins if hasattr(self.main_app, 'selected_coins') else []

                # 4. 코인 변경 로그
                if new_coins != old_coins:
                    self.logger.info(f"코인 변경 완료: {len(old_coins)}개 → {len(new_coins)}개")
                    self.logger.info(f"새로운 코인: {[coin['symbol'] for coin in new_coins]}")

                    # 5. API 기반 분석으로 변경 (WebSocket 구독 제거)
                    # 코인 분석은 API로 수행, WebSocket은 실제 포지션 진입 시에만 사용
                    self.log_event('coin_selection', "API 기반 코인 분석으로 변경 - WebSocket 구독 제거")
                else:
                    self.log_event('coin_selection', "코인 변경 없음 - 동일한 코인 유지")
            else:
                self.log_event('coin_selection', "main_app 객체 없음 - 코인 재선택 불가", level='WARNING')

        except Exception as e:
            self.log_event('coin_selection', f"코인 재선택 실행 오류: {e}", level='ERROR')
            import traceback
            self.log_event('coin_selection', f"코인 재선택 상세 오류: {traceback.format_exc()}", level='ERROR')

    def _analyze_market_regime_binance_fast(self):
        """빠른 바이낸스 시장 상황 분석 (BTC+ETH 가중 멀티 심볼, 최적화+캐싱)"""
        try:
            # BTC 70% + ETH 30% 가중 평균으로 시장 레짐 결정
            # BTC 단일 의존 제거: ETH가 BTC와 괴리될 때 레짐 신뢰도 향상
            REGIME_SYMBOLS = [('BTCUSDT', 0.70), ('ETHUSDT', 0.30)]

            if not self.binance_client:
                return 'normal'

            # 🔥 캐싱 체크 (5분간 유효)
            import time
            current_time = time.time()
            cache_key = "market_analysis_multi"

            if hasattr(self, '_market_analysis_cache'):
                cache_data = self._market_analysis_cache.get(cache_key)
                if cache_data and current_time - cache_data['timestamp'] < 300:  # 5분
                    self.log_event('analysis', f"캐시된 시장 분석 결과: {cache_data['regime']}")
                    return cache_data['regime']

            # 심볼별 지표 수집
            symbol_rsi: list = []
            symbol_trend: list = []
            symbol_volume_ratio: list = []
            symbol_change_30m: list = []

            for symbol, weight in REGIME_SYMBOLS:
                klines = self.binance_client.get_klines(symbol, '15m', 10)
                if not klines or len(klines) < 5:
                    continue

                prices = [kline_number(k, "close") for k in klines]
                volumes = [kline_number(k, "volume") for k in klines]

                # RSI(5)
                gains, losses = [], []
                for i in range(1, len(prices)):
                    change = prices[i] - prices[i - 1]
                    gains.append(max(change, 0))
                    losses.append(max(-change, 0))
                if len(gains) >= 5:
                    ag, al = sum(gains[-5:]) / 5, sum(losses[-5:]) / 5
                    rsi = 100 if al == 0 else 100 - (100 / (1 + ag / al))
                else:
                    rsi = 50

                # 트렌드 슬로프
                recent = prices[-5:]
                slope = (recent[-1] - recent[0]) / recent[0] if len(recent) >= 2 else 0.0

                # 거래량 비율
                vol_ratio = (volumes[-1] / (sum(volumes[-5:]) / 5)) if len(volumes) >= 5 and sum(volumes[-5:]) > 0 else 1.0

                # 30분 가격변화
                change_30m = ((prices[-1] - prices[-2]) / prices[-2] * 100) if len(prices) >= 2 else 0.0

                symbol_rsi.append((rsi, weight))
                symbol_trend.append((slope, weight))
                symbol_volume_ratio.append((vol_ratio, weight))
                symbol_change_30m.append((change_30m, weight))

            if not symbol_rsi:
                return 'normal'

            # 가중 평균 계산
            total_w = sum(w for _, w in symbol_rsi)
            rsi = sum(v * w for v, w in symbol_rsi) / total_w
            trend_slope = sum(v * w for v, w in symbol_trend) / total_w
            volume_ratio = sum(v * w for v, w in symbol_volume_ratio) / total_w
            price_change_30m = sum(v * w for v, w in symbol_change_30m) / total_w

            # 임계값 (settings.json 또는 기본값)
            analysis_thresholds = self.settings.get('market_analysis_thresholds', {})
            if not isinstance(analysis_thresholds, dict):
                analysis_thresholds = {}
            normal_thresholds = analysis_thresholds.get('normal', {
                'trend_slope_threshold': 0.05,
                'volume_ratio_threshold': 1.5,
                'volatility_threshold': 3.0,
                'rsi_overbought': 70,
                'rsi_oversold': 30
            })
            if not isinstance(normal_thresholds, dict):
                normal_thresholds = {}
            normal_thresholds = {
                'trend_slope_threshold': 0.05,
                'volume_ratio_threshold': 1.5,
                'volatility_threshold': 3.0,
                'rsi_overbought': 70,
                'rsi_oversold': 30,
                **normal_thresholds,
            }
            fast_trend_threshold = normal_thresholds['trend_slope_threshold'] * 0.2
            fast_volume_threshold = normal_thresholds['volume_ratio_threshold'] * 0.8
            fast_volatility_threshold = normal_thresholds['volatility_threshold'] * 0.67
            fast_rsi_overbought = normal_thresholds['rsi_overbought'] - 5
            fast_rsi_oversold = normal_thresholds['rsi_oversold'] + 5

            if trend_slope > fast_trend_threshold:
                trend = 'UPTREND'
            elif trend_slope < -fast_trend_threshold:
                trend = 'DOWNTREND'
            else:
                trend = 'SIDEWAYS'

            if rsi > fast_rsi_overbought and trend == 'UPTREND' and volume_ratio > fast_volume_threshold:
                regime = 'bull'
            elif rsi < fast_rsi_oversold and trend == 'DOWNTREND' and volume_ratio > fast_volume_threshold:
                regime = 'bear'
            elif abs(price_change_30m) > fast_volatility_threshold:
                regime = 'volatile'
            else:
                regime = 'normal'

            # 캐시 저장
            if not hasattr(self, '_market_analysis_cache'):
                self._market_analysis_cache = {}
            self._market_analysis_cache[cache_key] = {'regime': regime, 'timestamp': current_time}

            self.log_event('analysis', f"멀티심볼 시장 분석: RSI={rsi:.1f} 트렌드={trend} 거래량비={volume_ratio:.2f} 30m변화={price_change_30m:.2f}% → {regime}")
            return regime

        except Exception as e:
            self.logger.error(f"빠른 시장 분석 오류: {e}")
            return 'normal'

    def _analyze_market_regime_binance(self):
        """바이낸스용 시장 상황 분석 (기술적 지표 기반)"""
        try:
            # BTCUSDT를 기준으로 시장 분석 (시장 대표 코인)
            symbol = 'BTCUSDT'

            # 1. 시장 데이터 수집
            if not self.binance_client:
                return 'normal'

            klines = self.binance_client.get_klines(symbol, '15m', 50)  # 50개 캔들로 최적화
            if not klines or len(klines) < 50:
                return 'normal'

            # 2. 가격 데이터 추출
            prices = [float(k[4]) for k in klines]  # close price (리스트 형식)
            volumes = [float(k[5]) for k in klines]  # volume (리스트 형식)

            # 3. RSI 계산 (14기간)
            gains = []
            losses = []
            for i in range(1, len(prices)):
                change = prices[i] - prices[i-1]
                if change > 0:
                    gains.append(change)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(-change)

            avg_gain = sum(gains[-14:]) / 14 if len(gains) >= 14 else 0
            avg_loss = sum(losses[-14:]) / 14 if len(losses) >= 14 else 0

            if avg_loss == 0:
                rsi = 100
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))

            # 4. 트렌드 분석 (20기간) - 동적 임계값 적용
            recent_prices = prices[-20:]
            if len(recent_prices) >= 2:
                trend_slope = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]

                # 🔥 설정 파일에서 트렌드 임계값 가져오기
                analysis_thresholds = self.settings.get('market_analysis_thresholds', {})
                normal_thresholds = analysis_thresholds.get('normal', {
                    'trend_slope_threshold': 0.05,
                    'volume_ratio_threshold': 1.5,
                    'volatility_threshold': 3.0,
                    'rsi_overbought': 70,
                    'rsi_oversold': 30
                })
                trend_threshold = normal_thresholds['trend_slope_threshold']

                if trend_slope > trend_threshold:
                    trend = 'UPTREND'
                elif trend_slope < -trend_threshold:
                    trend = 'DOWNTREND'
                else:
                    trend = 'SIDEWAYS'
            else:
                trend = 'SIDEWAYS'

            # 5. 거래량 분석
            avg_volume = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else volumes[-1] if volumes else 1
            current_volume = volumes[-1] if volumes else 1
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

            # 6. 변동성 분석 (1시간 가격 변화율)
            price_change_1h = (prices[-1] - prices[-4]) / prices[-4] * 100 if len(prices) >= 4 else 0.0

            # 7. 시장 상황 판단 - 동적 임계값 적용
            # 🔥 설정 파일에서 분석 임계값 가져오기
            analysis_thresholds = self.settings.get('market_analysis_thresholds', {})
            normal_thresholds = analysis_thresholds.get('normal', {
                'trend_slope_threshold': 0.05,
                'volume_ratio_threshold': 1.5,
                'volatility_threshold': 3.0,
                'rsi_overbought': 70,
                'rsi_oversold': 30
            })

            volume_threshold = normal_thresholds['volume_ratio_threshold']
            volatility_threshold = normal_thresholds['volatility_threshold']
            rsi_overbought = normal_thresholds['rsi_overbought']
            rsi_oversold = normal_thresholds['rsi_oversold']

            if rsi > rsi_overbought and trend == 'UPTREND' and volume_ratio > volume_threshold:
                return 'bull'  # 강한 상승장
            elif rsi < rsi_oversold and trend == 'DOWNTREND' and volume_ratio > volume_threshold:
                return 'bear'  # 강한 하락장
            elif abs(price_change_1h) > volatility_threshold:  # 동적 변동성 임계값
                return 'volatile'  # 변동성 높음
            else:
                return 'normal'  # 정상 시장

        except Exception as e:
            self.logger.error(f"바이낸스 시장 분석 오류: {e}")
            return 'normal'

    def _get_advanced_layers_settings_binance(self) -> Dict[str, Any]:
        try:
            root = self.settings.get('advanced_trading_layers', {}) if isinstance(self.settings, dict) else {}
            overrides = (root.get('exchange_overrides', {}) or {}).get('binance', {})
            merged = dict(root or {})
            merged.update(overrides or {})
            return merged
        except Exception:
            return {}

    def _execution_mode(self) -> ExecutionMode:
        return resolve_crypto_execution_mode(
            self.settings if isinstance(self.settings, dict) else {},
            'binance',
        )

    def _is_live_entry_enabled(self, exchange_name: str = 'binance') -> bool:
        """신규 실주문 허용 범위를 확인한다.

        키가 없는 구버전 설정만 selected_exchange 한 곳을 허용한다. 명시적인
        빈 목록은 학습 전용이며 주문 경로의 최종 방어선에서도 False다.
        """
        return resolve_crypto_execution_mode(
            self.settings if isinstance(self.settings, dict) else {},
            exchange_name,
        ) == ExecutionMode.LIVE

    def _get_recent_trade_samples_binance(self, days: int = 45, limit: int = 300) -> List[Dict[str, Any]]:
        try:
            if hasattr(self, 'recorder') and self.recorder and hasattr(self.recorder, 'get_trade_history'):
                rows = self.recorder.get_trade_history(days=days) or []
                filtered = [dict(r) for r in rows if isinstance(r, dict) and str(r.get('exchange', 'binance')).lower() == 'binance']
                return filtered[:limit]
        except Exception:
            pass
        return []

    def _build_strategy_runtime_state_binance(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        runtime_state: Dict[str, Any] = {}
        for trade in trades or []:
            symbol = str(trade.get('symbol') or '').strip().upper()
            if not symbol:
                continue
            ts_raw = trade.get('exit_time') or trade.get('entry_time')
            parsed = None
            try:
                if isinstance(ts_raw, str) and ts_raw:
                    parsed = datetime.fromisoformat(ts_raw.replace('Z', '+00:00')).replace(tzinfo=None)
                elif isinstance(ts_raw, (int, float)):
                    parsed = datetime.fromtimestamp(float(ts_raw) / 1000.0 if float(ts_raw) > 1e12 else float(ts_raw))
            except Exception:
                parsed = None
            if parsed is None:
                continue
            key = f'last_trade_at::{symbol}'
            if key not in runtime_state or parsed > runtime_state[key]:
                runtime_state[key] = parsed
        return runtime_state

    def _build_portfolio_allocation_binance(self, symbol: str, signal_data: Dict[str, Any], layer_settings: Dict[str, Any]) -> Dict[str, Any]:
        policy = dict(layer_settings.get('portfolio_orchestration', {}) or {})
        if not bool(policy.get('enabled', False)):
            return {'allocations': {}, 'portfolio_risk': 0.0, 'risk_scale': 1.0}

        capital = 0.0
        try:
            if hasattr(self, 'binance_client') and self.binance_client and hasattr(self.binance_client, 'get_futures_balance'):
                capital = float(self.binance_client.get_futures_balance() or 0.0)
        except Exception:
            capital = 0.0
        if capital <= 0:
            capital = 1000.0

        candidate = {
            'symbol': str(symbol).upper(),
            'asset_class': 'crypto',
            'signal_strength': max(0.0, min(1.0, float(signal_data.get('confidence', 0.0) or 0.0))),
            'volatility': max(0.005, abs(float(signal_data.get('volatility', 0.5) or 0.5)) / 100.0),
            'avg_correlation': float(((policy.get('correlation_overrides', {}) or {}).get(str(symbol).upper(), 0.25)) or 0.25),
        }
        return PortfolioOrchestrator().allocate(candidates=[candidate], total_capital=capital, policy=policy)

    def _place_entry_order_with_quality_control_binance(self, symbol: str, side: str, quantity: float, layer_settings: Dict[str, Any], trade_params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._is_live_entry_enabled('binance'):
            self.log_event(
                'trade',
                f"🧠 {symbol} 학습 전용 - 신규 실주문 제출 차단",
                exchange='binance',
                level='INFO',
            )
            return {'status': 'BLOCKED', 'error': 'learning_only', 'errors': ['learning_only']}
        policy = dict(layer_settings.get('execution_optimizer', {}) or {})
        if not bool(policy.get('enabled', False)):
            result = self.binance_client.place_futures_order(symbol=symbol, side=side, order_type='MARKET', quantity=quantity)
            if isinstance(result, dict):
                result.setdefault('latency_ms', 0.0)
                result.setdefault('slippage_bps', 0.0)
                result.setdefault('errors', [])
            return result

        optimizer = ExecutionOptimizer()
        preferred_order_type = str(policy.get('preferred_order_type', 'MARKET') or 'MARKET').upper()
        chosen_order_type = optimizer.choose_order_type(
            preferred=preferred_order_type,
            signal_strength=float(policy.get('signal_strength', trade_params.get('confidence', 0.5)) or 0.5),
            volatility=float(policy.get('volatility', trade_params.get('volatility', 0.02)) or 0.02),
            spread_bps=float(policy.get('spread_bps', 12.0) or 12.0),
        )
        request_price = None
        try:
            raw_price = trade_params.get('price', trade_params.get('entry_price', 0.0))
            parsed_price = float(raw_price or 0.0)
            if parsed_price > 0:
                request_price = parsed_price
            elif hasattr(self, 'binance_client') and self.binance_client:
                live_price = float(self.binance_client.get_current_price(symbol) or 0.0)
                request_price = live_price if live_price > 0 else None
        except Exception:
            request_price = None

        success, result, errors, latency_ms, slippage_bps = optimizer.execute_with_quality_control(
            place_order_fn=lambda dyn_order_type, dyn_price: self._place_binance_order_once(symbol, side, quantity, dyn_order_type, dyn_price),
            order_type=chosen_order_type,
            request_price=request_price,
            fallback_market=bool(policy.get('fallback_market', True)),
            max_retries=max(0, int(policy.get('max_retries', 1) or 1)),
            timeout_ms=max(300, int(policy.get('timeout_ms', 3000) or 3000)),
            max_slippage_bps=max(0.1, float(policy.get('max_slippage_bps', 35.0) or 35.0)),
        )
        payload = dict(result or {})
        payload['status'] = 'FILLED' if success and str(payload.get('status', '')).upper() in ('', 'NEW', 'PENDING', 'FILLED') else payload.get('status', 'FAILED')
        payload['latency_ms'] = latency_ms
        payload['slippage_bps'] = slippage_bps
        payload['errors'] = errors
        payload['order_type'] = payload.get('order_type') or chosen_order_type
        return payload

    def _place_binance_order_once(self, symbol: str, side: str, quantity: float, order_type: str, request_price: Optional[float] = None) -> tuple[bool, Dict[str, Any], List[str]]:
        if not self._is_live_entry_enabled('binance'):
            return False, {'status': 'BLOCKED', 'error': 'learning_only'}, ['learning_only']
        normalized_order_type = str(order_type).upper()
        order_price = request_price if normalized_order_type == 'LIMIT' and request_price is not None and request_price > 0 else None
        result = self.binance_client.place_futures_order(
            symbol=symbol,
            side=side,
            order_type=normalized_order_type,
            quantity=quantity,
            price=order_price,
        )
        status = str((result or {}).get('status', '')).upper()
        success = status in ('NEW', 'PENDING', 'FILLED')
        errors = [] if success else [str((result or {}).get('error') or 'order_failed')]
        return success, (result if isinstance(result, dict) else {}), errors

    def execute_trading_cycle(self):
        """거래 사이클 실행 (리스크 관리 통합)"""
        try:
            execution_mode = self._execution_mode()
            live_orders_enabled = execution_mode == ExecutionMode.LIVE
            paper_mode = execution_mode == ExecutionMode.PAPER
            decision_execution_enabled = live_orders_enabled or paper_mode
            self.log_event('trade', "🔄 거래 사이클 시작...")
            if paper_mode:
                self.log_event(
                    'system',
                    "🧪 BINANCE 페이퍼 사이클 - 실시간 시세·분석, 가상 주문만 수행",
                    exchange='binance',
                )
                self._monitor_paper_positions()
            elif not live_orders_enabled:
                self.log_event(
                    'system',
                    "🧠 BINANCE 학습 전용 사이클 - 시세·분석·학습 수행, 신규 실주문 0건",
                    exchange='binance',
                )

            # 🔥 좀비 플래그만 정리 (오픈오더는 진입 직전에 정리)
            if live_orders_enabled:
                self._cleanup_zombie_flags()
                self.log_event('trade', "✅ 거래 사이클 시작 - 좀비 플래그 정리 완료")

            # 0. 코인 재선택 로직 (시장 상황 변화 체크) - 최적화
            self.log_event('analysis', "시장 분석 시작...")
            self._check_and_reselect_coins_optimized()
            self.log_event('analysis', "시장 분석 완료")

            # 1. 일일 손실 한도 체크
            if live_orders_enabled and self.risk_manager and self.risk_manager.check_daily_loss_limit():
                self.log_event('trade', "🛑 일일 손실 한도 초과 - 거래 중단", level='ERROR')
                try:
                    log_exception('trade', '일일 손실 한도 초과 - 거래 중단', exchange='binance')
                except Exception:
                    pass
                return

            # 🤖 AI 자동 학습: 거래 성과에 따라 신호 기준 조절
            self._auto_adjust_threshold_from_performance()
            self._apply_connected_strategy_runtime()

            layer_settings = self._get_advanced_layers_settings_binance()
            recent_trades = self._get_recent_trade_samples_binance(days=45, limit=300)
            profitability_report = ProfitabilityValidator().evaluate_strategy(
                recent_trades=recent_trades,
                policy=dict(layer_settings.get('profitability_validation', {}) or {}),
            )
            profitability_blocked = bool(
                bool((layer_settings.get('profitability_validation', {}) or {}).get('enabled', False))
                and not bool(profitability_report.get('enabled', True))
            )
            if profitability_blocked:
                self.log_event(
                    'trade',
                    f"⚠️ 바이낸스 기본/confirm 후보 수익성 정책 차단: "
                    f"{profitability_report.get('reasons', [])} · independent 전략은 버전별 검증 사용",
                    level='WARNING',
                )
                # 독립 커스텀 전략이 없으면 이후 후보는 모두 기본/confirm
                # 경로이므로 기존처럼 사이클을 즉시 종료할 수 있다.
                if live_orders_enabled and not (getattr(self, 'active_custom_strategy_pool', []) or []):
                    self.cycle_execution_metrics['binance'] = {
                        'attempted_orders': 0,
                        'failed_orders': 0,
                        'avg_latency_ms': 0.0,
                        'avg_slippage_bps': 0.0,
                        'quality_score': 0.0,
                        'anomalies': [],
                        'profitability_validation': profitability_report,
                        'blocked_scope': 'base_and_confirm',
                    }
                    return
            cold_start_profile = (
                dict(profitability_report)
                if profitability_report.get('stage') in {'limited_live_learning', 'recovery_learning'}
                else {}
            )
            if cold_start_profile:
                stage_label = (
                    '성과회복 제한 운용'
                    if cold_start_profile.get('stage') == 'recovery_learning'
                    else '신규/데이터부족 제한 운용'
                )
                self.log_event(
                    'trade',
                    f"🌱 바이낸스 {stage_label}: 거래 "
                    f"{cold_start_profile.get('total_trades', 0)}/{cold_start_profile.get('next_review_at_trades')} · "
                    f"위험배수 {cold_start_profile.get('risk_multiplier', 0.1):.2f} · "
                    f"최대포지션 {cold_start_profile.get('max_positions', 1)} · "
                    f"최대레버리지 {cold_start_profile.get('max_leverage', 1)}x",
                    exchange='binance',
                )

            strategy_runtime_state = self._build_strategy_runtime_state_binance(recent_trades)
            strategy_engine = StrategyEngine()
            cycle_metrics = {'attempted': 0, 'failed': 0, 'latencies': [], 'slippages': []}

            # 1. 현재 포지션 상태 확인 (실시간 모니터링은 별도 스레드에서 처리)
            # 🔥 실제 거래소에서 포지션 조회하여 동기화 (메모리와 실제 상태 불일치 방지)
            # 문제: close_position에서 포지션을 제거했지만, 실제 거래소에서는 이미 청산되어 메모리와 불일치 발생
            memory_positions_before = len(self.get_active_positions())
            memory_symbols_before = set(self.get_active_positions().keys())
            
            try:
                if live_orders_enabled and hasattr(self, 'binance_client') and self.binance_client:
                    self.log_event('trade', f"🔍 실제 거래소에서 포지션 조회 시작 (메모리: {memory_positions_before}개)")
                    actual_positions = self.binance_client.get_positions()
                    actual_symbols = {pos.symbol for pos in actual_positions}
                    getter = getattr(self.recorder, 'get_open_managed_trades', None)
                    managed_rows = getter('binance') if callable(getter) else []
                    managed_by_symbol = managed_trade_map(managed_rows or [])
                    self.external_position_symbols = {
                        pos.symbol
                        for pos in actual_positions
                        if normalize_position_symbol(pos.symbol) not in managed_by_symbol
                    }
                    self.log_event('trade', f"🔍 실제 거래소 포지션: {len(actual_positions)}개, 심볼={list(actual_symbols)}")
                    
                    # 메모리에 있지만 실제로는 없는 포지션 제거 (청산되었지만 메모리에 남아있는 경우)
                    removed_symbols = []
                    for symbol in list(self.active_positions.keys()):
                        if symbol not in actual_symbols:
                            removed_symbols.append(symbol)
                            self.log_event('trade', f"[{symbol}] ⚠️ 실제 포지션 없음 - 메모리에서 제거 (청산되었지만 메모리에 남아있음)", level='WARNING')
                            if symbol in self.active_positions:
                                del self.active_positions[symbol]
                            if symbol in self.trade_entered:
                                self.trade_entered[symbol] = False
                    
                    if removed_symbols:
                        self.log_event('trade', f"✅ 포지션 동기화 완료: {len(removed_symbols)}개 제거 (메모리 {memory_positions_before}개 → {len(self.active_positions)}개)")
                    
                    # 실제 포지션이 있으면 메모리에 추가/업데이트 (복구된 포지션) - max_positions 제한 적용
                    max_positions = self.settings.get('max_positions', 3)
                    added_symbols = []
                    skipped_count = 0
                    for pos in actual_positions:
                        if pos.symbol not in self.active_positions:
                            managed_row = managed_by_symbol.get(normalize_position_symbol(pos.symbol))
                            if managed_row is None:
                                self.log_event(
                                    'trade',
                                    f"[{pos.symbol}] 수동/외부 포지션 감지 - 자동 모니터링·청산 제외",
                                    level='WARNING',
                                )
                                continue
                            # 🔥 max_positions 제한 체크
                            if len(self.active_positions) >= max_positions:
                                skipped_count += 1
                                self.log_event('trade', f"⚠️ 포지션 복구 중단: 최대 포지션 수 도달 ({len(self.active_positions)}/{max_positions}) - {pos.symbol} 스킵", level='WARNING')
                                break  # ✅ 제한 도달 시 복구 중단
                            
                            added_symbols.append(pos.symbol)
                            # Position과 PositionSide는 이 파일에 정의되어 있음
                            position = Position(
                                symbol=pos.symbol,
                                side=PositionSide.LONG if pos.side == "LONG" else PositionSide.SHORT,
                                quantity=pos.size,
                                entry_price=pos.entry_price,
                                current_price=pos.mark_price,
                                unrealized_pnl=pos.unrealized_pnl,
                                unrealized_pnl_percent=0.0,
                                entry_time=parse_entry_time(managed_row.get('entry_time')),
                                leverage=pos.leverage,
                                tp_price=float(managed_row.get('tp_price') or 0.0) or None,
                                sl_price=float(managed_row.get('sl_price') or 0.0) or None,
                                position_id=str(managed_row.get('id') or ''),
                                entry_order_id=str(managed_row.get('order_id') or ''),
                                entry_order_ids=list(managed_row.get('_entry_order_ids') or []),
                                entry_time_source="execution",
                                execution_mode=str(managed_row.get('execution_mode') or 'live'),
                                position_owner=NOAH_POSITION_OWNER,
                            )
                            self.active_positions[pos.symbol] = position
                            self.log_event('trade', f"[{pos.symbol}] 실제 포지션 발견 - 메모리에 추가", level='INFO')
                    
                    if added_symbols:
                        if skipped_count > 0:
                            self.log_event('trade', f"✅ 포지션 복구 완료: {len(added_symbols)}개 추가 (최대: {max_positions}개, {skipped_count}개 제한 초과로 스킵)", level='WARNING')
                        else:
                            self.log_event('trade', f"✅ 포지션 복구 완료: {len(added_symbols)}개 추가 (최대: {max_positions}개)")
                    
                    # 동기화 결과 요약
                    if not removed_symbols and not added_symbols:
                        self.log_event('trade', f"✅ 포지션 동기화: 메모리와 실제 상태 일치 ({len(actual_positions)}개)")
                elif live_orders_enabled:
                    self.log_event('trade', f"⚠️ binance_client 없음 - 포지션 동기화 건너뜀", level='WARNING')
                else:
                    self.log_event('trade', f"🧪 {execution_mode.value} 모드 - 실제 포지션 동기화 생략")
            except Exception as sync_err:
                self.log_event('trade', f"❌ 포지션 동기화 실패: {sync_err}", level='ERROR')
                import traceback
                self.log_event('trade', f"❌ 상세 오류: {traceback.format_exc()}", level='ERROR')
            
            active_positions = self.get_active_positions()
            memory_positions_after = len(active_positions)
            self.logger.info(f"현재 활성 포지션: {memory_positions_after}개 (동기화 전: {memory_positions_before}개, ex=binance)")

            # 2. 스킵 로직 보강 (단일모드/다중모드 구분 처리)
            # 직후 사용될 설정 파싱
            position_mode = self.settings.get('position_mode', 'multi')
            max_positions = int(self.settings.get('max_positions', 3))
            if cold_start_profile:
                max_positions = min(max_positions, int(cold_start_profile.get('max_positions', 1) or 1))

            # 단일모드(집중모드)일 때: 포지션이 있으면 전체 스킵
            effective_position_count = len(active_positions) + len(getattr(self, 'external_position_symbols', set()))
            if decision_execution_enabled and (position_mode == 'single' or max_positions == 1) and effective_position_count > 0:
                self.log_event('trade', f"집중모드 - 포지션 모니터링 중 (관리+수동/외부: {effective_position_count}개)")
                return

            # 🔥 필터링 먼저 실행 (보유 심볼 제외)
            # get_active_positions()는 Dict[str, Position]를 반환하므로 키 집합을 직접 사용
            open_symbols = set(active_positions.keys()) if decision_execution_enabled else set()
            self.log_event('trade', f"🔍 포지션 필터링 시작: 활성 포지션 심볼={list(open_symbols)}, 개수={len(open_symbols)}")

            # 🔥 코인 소스 단일화: main_app.selected_coins만 사용
            selected_coins = getattr(self.main_app, 'selected_coins', []) if hasattr(self, 'main_app') else []
            self.log_event('trade', f"🔍 선택된 코인 수: {len(selected_coins)}개")

            def coin_symbol(coin):
                if isinstance(coin, dict):
                    return coin.get('symbol')
                return coin  # 문자열 등

            filtered = [c for c in selected_coins if coin_symbol(c) not in open_symbols]
            self.log_event('trade', f"🔍 필터링 후 코인 수: {len(filtered)}개 (보유 심볼 제외)")

            if not filtered:
                self.log_event('trade', f"다중포지션 모드 - 보유 심볼 제외 후 신규 대상 없음 (활성 {len(active_positions)}개, 선택된 코인: {len(selected_coins)}개, 필터링 후: {len(filtered)}개)")
                return

            # 🔥 필터링 후 최대 포지션 수 확인
            if decision_execution_enabled and effective_position_count >= max_positions:
                self.log_event('trade', f"최대 포지션 수 도달 - 신규 대상 없음 (관리+수동/외부: {effective_position_count}개 >= 최대: {max_positions}개)", level='INFO')
                return

            # 이후 로직은 filtered를 사용
            selected_coins = filtered

            # 🔍 디버깅: selected_coins 상태 확인
            self.log_event('debug', f"selected_coins type: {type(selected_coins)}", exchange='binance', level='DEBUG')
            self.log_event('debug', f"selected_coins length: {len(selected_coins)}", exchange='binance', level='DEBUG')
            self.log_event('debug', f"selected_coins content: {selected_coins[:2] if selected_coins else 'EMPTY'}", exchange='binance', level='DEBUG')
            self.log_event('debug', f"hasattr(self, 'main_app'): {hasattr(self, 'main_app')}", exchange='binance', level='DEBUG')
            if hasattr(self, 'main_app'):
                self.log_event('debug', f"main_app type: {type(self.main_app)}", exchange='binance', level='DEBUG')
                self.log_event('debug', f"main_app.selected_coins: {getattr(self.main_app, 'selected_coins', 'NO_ATTR')}", exchange='binance', level='DEBUG')

            if selected_coins:
                self.log_event('system', f'선택된 코인 수: {len(selected_coins)}개')
                for coin in selected_coins:
                    if isinstance(coin, dict):
                        symbol = coin.get('symbol', 'N/A')
                        overall_score = coin.get('overall_score', 0)
                        is_major = coin.get('is_major', False)
                        coin_type = "메이저" if is_major else "알트"
                        self.log_event('system', f'   • {symbol} ({coin_type}: {is_major}, 종합점수: {overall_score:.2f})')
                    else:
                        # 🔥 coin이 딕셔너리가 아닌 경우에도 안전하게 처리
                        if isinstance(coin, str):
                            self.logger.info(f"   • {coin}")
                        else:
                            # K-line 데이터가 포함된 coin 전체를 로그로 출력하지 않음
                            coin_summary = f"코인 객체 (타입: {type(coin).__name__})"
                            self.logger.info(f"   • {coin_summary}")

                for i, coin in enumerate(selected_coins):
                    # 🔥 분석 사이 딜레이 (과도한 API 호출 방지) - 첫 번째 코인 제외
                    if i > 0:  # 첫 번째 코인이 아닐 때만 딜레이 적용
                        self.log_event('system', f'⏱️ 코인 분석 사이 딜레이 적용: 3초 대기 중... ({i}/{len(selected_coins)})')
                        time.sleep(3)  # 3초 딜레이

                    # 🔥 중지 신호 확인 (각 코인 처리 전)
                    if hasattr(self.main_app, 'trading_worker') and self.main_app.trading_worker:
                        if not self.main_app.trading_worker.running:
                            self.log_event('system', '🔥 중지 신호 감지 - 코인 분석 중단', exchange='binance')
                            break
                    symbol = 'UNKNOWN'
                    try:
                        # coin이 딕셔너리인지 문자열인지 확인
                        if isinstance(coin, dict):
                            symbol = coin.get('symbol', 'N/A')
                        else:
                            symbol = str(coin)

                        # USDT가 이미 포함되어 있으면 그대로 사용, 아니면 추가
                        if not symbol.endswith('USDT'):
                            symbol = f"{symbol}USDT"

                        # 리스크 관리: 코인 스킵 체크
                        if live_orders_enabled and self.risk_manager and self.risk_manager.should_skip_coin(symbol):
                            self.logger.info(f"⏸️ {symbol} 리스크 관리로 스킵")
                            continue

                        self.logger.info(f"📊 {symbol} 실시간 거래 신호 분석 중...")

                        # 포지션 진입 직전에 거래 신호 생성
                        self._log_trade_event('analysis', f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", exchange='binance', verbose_only=True)
                        self._log_trade_event('analysis', f"📊 {symbol} 분석 시작", exchange='binance', verbose_only=True)

                        self._log_trade_event('analysis', f"🔍 {symbol} 신호 생성 시작...", verbose_only=True)
                        self._log_trade_event('analysis', f"🔍 {symbol} analyzer 객체 확인: {hasattr(self, 'analyzer')}", verbose_only=True)
                        if hasattr(self, 'analyzer'):
                            self._log_trade_event('analysis', f"🔍 {symbol} analyzer 타입: {type(self.analyzer)}", verbose_only=True)

                        inference_started = time.perf_counter()
                        try:
                            analysis_config = self.settings
                            if (
                                isinstance(coin, dict)
                                and str(coin.get("_selection_pipeline") or "") == "advanced"
                            ):
                                analysis_config = dict(self.settings or {})
                                analysis_config["_skip_ai_enhancement"] = True
                            signal_data = self.analyzer.generate_trading_signal(
                                symbol,
                                config=analysis_config,
                            )
                            if isinstance(signal_data, dict) and isinstance(coin, dict):
                                signal_data["_selection_pipeline"] = str(
                                    coin.get("_selection_pipeline") or "general"
                                )
                                signal_data["_eligible_strategy_modes"] = list(
                                    coin.get("_eligible_strategy_modes") or []
                                )
                                signal_data["_eligible_strategy_ids"] = list(
                                    coin.get("_eligible_strategy_ids") or []
                                )
                            inference_ms = (time.perf_counter() - inference_started) * 1000.0
                            emit_kpi_event(
                                event_type='ai_inference_completed',
                                category='learning',
                                asset_class='crypto',
                                status='success',
                                source='noahai_client_trader',
                                metric_value=float(inference_ms),
                                metadata={
                                    'exchange': 'binance',
                                    'symbol': symbol,
                                    'signal': str(signal_data.get('signal', 'HOLD')),
                                    'ai_call_mode': str(signal_data.get('ai_call_mode', 'unknown')),
                                    'ai_model': str(signal_data.get('ai_model', '')),
                                    'strategy_variant': str(signal_data.get('strategy_variant', 'unknown')),
                                    'input_tokens': int((signal_data.get('ai_usage', {}) or {}).get('input_tokens', 0) or 0),
                                    'output_tokens': int((signal_data.get('ai_usage', {}) or {}).get('output_tokens', 0) or 0),
                                },
                            )
                            self._log_trade_event('analysis', f"✅ {symbol} 신호 생성 성공: {signal_data}", verbose_only=True)
                        except Exception as e:
                            emit_kpi_event(
                                event_type='ai_inference_completed',
                                category='learning',
                                asset_class='crypto',
                                status='failed',
                                source='noahai_client_trader',
                                metadata={
                                    'exchange': 'binance',
                                    'symbol': symbol,
                                    'reason': str(e),
                                },
                            )
                            self.logger.error(f"❌ {symbol} 신호 생성 실패: {str(e)}")
                            import traceback
                            self.logger.error(f"❌ {symbol} 예외 상세: {traceback.format_exc()}")
                            self.logger.error(f"❌ {symbol} analyzer 상태: {getattr(self, 'analyzer', 'None')}")
                            continue

                        signal = signal_data.get('signal', 'HOLD')
                        confidence = signal_data.get('confidence', 0)
                        reason = signal_data.get('reason', '')

                        self._log_trade_event('analysis', f"🔍 {symbol} 신호 데이터 파싱 완료: signal={signal}, confidence={confidence}", verbose_only=True)

                        # 🔥 상세 분석 과정 로깅 (통합 로그 시스템 사용)
                        self._log_trade_event('analysis', f"[{symbol}] 분석 과정 상세", verbose_only=True)
                        self._log_trade_event('analysis', f"   • 시그널: {signal}", verbose_only=True)
                        self._log_trade_event('analysis', f"   • 신뢰도: {confidence:.2f}", verbose_only=True)

                        # 트렌드 정보
                        trend = signal_data.get('trend', 'UNKNOWN')
                        if trend:
                            trend_str = str(trend).split('.')[-1] if hasattr(trend, 'value') else str(trend)
                            self._log_trade_event('analysis', f"   • 트렌드: {trend_str}", verbose_only=True)

                        # 변동성 정보
                        volatility = signal_data.get('volatility', 0)
                        self._log_trade_event('analysis', f"   • 변동성: {volatility:.2f}%", verbose_only=True)

                        # 지지/저항 레벨
                        support_level = signal_data.get('support_level', 0)
                        resistance_level = signal_data.get('resistance_level', 0)
                        self._log_trade_event('analysis', f"   • 지지 레벨: {support_level:.4f}", verbose_only=True)
                        self._log_trade_event('analysis', f"   • 저항 레벨: {resistance_level:.4f}", verbose_only=True)

                        # 기술적 지표들
                        rsi = signal_data.get('rsi', 0)
                        macd = signal_data.get('macd', 0)
                        bb_position = signal_data.get('bb_position', 0)
                        ma20 = signal_data.get('ma20', 0)
                        ma50 = signal_data.get('ma50', 0)

                        self._log_trade_event('analysis', f"   • RSI: {rsi:.2f}", verbose_only=True)
                        self._log_trade_event('analysis', f"   • MACD: {macd:.4f}", verbose_only=True)
                        self._log_trade_event('analysis', f"   • 볼린저밴드 위치: {bb_position:.2f}", verbose_only=True)
                        self._log_trade_event('analysis', f"   • 이동평균 20: {ma20:.4f}", verbose_only=True)
                        self._log_trade_event('analysis', f"   • 이동평균 50: {ma50:.4f}", verbose_only=True)

                        # 추론 정보
                        if reason:
                            self._log_trade_event('analysis', f"   • 추론: {reason}", verbose_only=True)

                        self.log_event('analysis', f"📊 {symbol} 분석 완료 - 시그널: {signal}", exchange='binance')
                        self._log_trade_event('analysis', f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", exchange='binance', verbose_only=True)

                        from .custom_strategy_validator import enrich_advanced_indicator_context
                        strategy_pool = getattr(self, 'active_custom_strategy_pool', []) or []
                        signal_data = enrich_advanced_indicator_context(
                            signal_data,
                            strategy_pool,
                            lambda timeframe, limit: self.binance_client.get_klines(
                                symbol, timeframe, limit
                            ),
                        )
                        runtime_strategy_context = dict(
                            getattr(self, '_custom_strategy_runtime_context', {}) or {}
                        )
                        signal_data['_strategy_performance'] = dict(
                            runtime_strategy_context.get('performance', {}) or {}
                        )
                        candidate = evaluate_trade_candidate(
                            symbol=symbol,
                            context=signal_data,
                            strategy_pool=strategy_pool,
                            asset_class="crypto",
                            target="binance",
                            market_regime=str(getattr(self, 'last_market_regime', 'range') or 'range'),
                        )
                        signal_data = apply_trade_candidate(signal_data, candidate)
                        signal = candidate.final_signal
                        def record_learning_decision(
                            decision: str,
                            reason_text: str = "",
                            trade_plan: Optional[Dict[str, Any]] = None,
                        ) -> None:
                            """LEARNING 결과를 최종 게이트 상태와 함께 한 번 기록한다."""
                            if execution_mode != ExecutionMode.LEARNING:
                                return
                            learning_payload = dict(signal_data)
                            learning_payload['_learning_decision'] = str(decision)
                            learning_payload['_learning_block_reason'] = str(reason_text or "")
                            if trade_plan is not None:
                                learning_payload['_learning_trade_plan'] = dict(trade_plan)
                            self._generate_ai_learning_data('binance', symbol, learning_payload)

                        # LIVE/PAPER의 일반 학습 표본은 기존 시점에 유지한다.
                        # LEARNING은 아래의 최종 판단 지점에서 차단 사유·계획까지
                        # 포함해 한 번만 기록한다.
                        if execution_mode != ExecutionMode.LEARNING:
                            self._generate_ai_learning_data('binance', symbol, signal_data)
                        if not candidate.allowed:
                            record_learning_decision('candidate_blocked', candidate.reason)
                            self.log_event(
                                'trade',
                                f"⏸️ {symbol} AI 커스텀 HOLD - 현재 범위·국면·진입조건 미충족: {candidate.reason}",
                                exchange='binance', level='INFO',
                            )
                            continue
                        if candidate.strategy_name:
                            self.log_event(
                                'strategy',
                                f"🧠 {symbol} AI 커스텀 선택: {candidate.strategy_name} "
                                f"(버전={candidate.strategy_version_id or '-'}, 방식={candidate.strategy_role}, "
                                f"운용={candidate.operation_mode}, 국면={candidate.market_regime}, "
                                f"국면기준={candidate.regime_scope}, "
                                f"후보출처={candidate.signal_source}, "
                                f"위험예산={candidate.engine_settings.get('risk_per_trade_percent', '-')}, "
                                f"TP={candidate.engine_settings.get('tp_percent', '-')}, "
                                f"SL={candidate.engine_settings.get('sl_percent', '-')})",
                                exchange='binance',
                            )

                        if profitability_blocked and candidate.requires_noah_strategy_policy:
                            record_learning_decision(
                                'profitability_blocked',
                                str(profitability_report.get('reasons', [])),
                            )
                            self.log_event(
                                'trade',
                                f"⛔ {symbol} 기본/confirm 후보 수익성 검증 차단: "
                                f"{profitability_report.get('reasons', [])}",
                                exchange='binance',
                                level='WARNING',
                            )
                            continue

                        if signal in ['LONG', 'SHORT'] and candidate.requires_noah_strategy_policy:
                            strategy_allowed, strategy_meta = strategy_engine.should_trade(
                                symbol=symbol,
                                analysis_result={
                                    'score': float(confidence or 0.0) * 100.0,
                                    'momentum': float(signal_data.get('price_change_1h', signal_data.get('volatility', 0.0)) or 0.0),
                                },
                                runtime_state=strategy_runtime_state,
                                policy=dict(layer_settings.get('strategy_engine', {}) or {}),
                            )
                            if not strategy_allowed:
                                record_learning_decision(
                                    'strategy_guardrail_blocked',
                                    str(strategy_meta.get('reasons', [])),
                                )
                                custom_name = signal_data.get('_selected_custom_strategy', '기본 AI')
                                self.log_event(
                                    'trade',
                                    f"⛔ {symbol} {custom_name} HOLD - 후행 전략 가드레일 차단: {strategy_meta.get('reasons', [])}",
                                    exchange='binance', level='WARNING',
                                )
                                continue

                        if signal in ['LONG', 'SHORT']:
                            # 🔥 거래 실행 전 중지 신호 재확인
                            if hasattr(self.main_app, 'trading_worker') and self.main_app.trading_worker:
                                if not self.main_app.trading_worker.running:
                                    self.log_event('system', f'🔥 중지 신호 감지 - {symbol} 거래 실행 중단', exchange='binance')
                                    break

                            self.log_event('trade', f"[{symbol}] 신호 검증 시작 - 시그널: {signal}", exchange='binance')
                        else:
                            record_learning_decision(
                                'hold',
                                f"final_signal={signal}, confidence={confidence:.4f}",
                            )
                            self.log_event('trade', f"[{symbol}] 거래 시그널 없음 - {signal} (거래 실행 생략)", exchange='binance')
                            self.log_event('trade', f"⏸️ {symbol} 거래 조건 미충족 (신호: {signal}, 신뢰도: {confidence:.2f})")
                            # HOLD는 정책상 미진입 경로이므로 pre-entry 검증을 생략한다.
                            self._log_trade_event('trade', f"{symbol} HOLD | 신호 {signal}, 신뢰도 {confidence:.2f}", exchange='binance', level='INFO')
                            continue

                        # independent는 사용자 전략 원형이 진입 판단을 소유한다.
                        # 기본 AI 패턴·신뢰도 검증으로 재심사하지 않고 이후 계좌·주문
                        # 안전 경계만 유지한다.
                        if candidate.is_independent:
                            pre_entry_analysis = {
                                'proceed': True,
                                'reason': 'custom_independent_strategy_preserved',
                                'strategy_integrity': True,
                            }
                        else:
                            try:
                                pre_entry_analysis = self._perform_pre_entry_analysis(symbol, signal_data)
                            except Exception as e:
                                record_learning_decision('pre_entry_error', str(e))
                                self.log_event('trade', f"❌ {symbol} Pre-entry 분석 오류: {e}", level='ERROR')
                                import traceback
                                self.log_event('trade', f"❌ {symbol} Pre-entry 분석 상세 오류: {traceback.format_exc()}", level='ERROR')
                                continue

                            if not pre_entry_analysis['proceed']:
                                record_learning_decision(
                                    'pre_entry_blocked',
                                    str(pre_entry_analysis.get('reason', '')),
                                )
                                self.log_event('trade', f"⚠️ {symbol} AI 진입 전 분석 실패: {pre_entry_analysis['reason']}", level='WARNING')
                                continue

                        # 🔥 _perform_pre_entry_analysis에서 이미 완화된 임계값으로 검증 완료
                        # 추가 검증 단계는 pre_entry_analysis의 결과를 신뢰
                        # (첫 거래 완화, 코인별 첫 거래 완화 등이 이미 적용됨)
                        
                        # AI 기반 동적 신뢰도 기준 계산 (로깅 및 참고용)
                        if candidate.is_independent:
                            dynamic_confidence_threshold = 0.0
                        else:
                            try:
                                dynamic_confidence_threshold = self._calculate_dynamic_confidence_threshold(symbol, signal_data)
                            except Exception as e:
                                record_learning_decision('dynamic_confidence_error', str(e))
                                self.log_event('trade', f"❌ {symbol} 동적 신뢰도 기준 계산 오류: {e}", level='ERROR')
                                import traceback
                                self.log_event('trade', f"❌ {symbol} 동적 신뢰도 기준 상세 오류: {traceback.format_exc()}", level='ERROR')
                                continue

                        # 🔥 pre_entry_analysis에서 이미 검증 완료되었으므로, 그 결과를 사용
                        # (첫 거래 완화, 코인별 첫 거래 완화 등이 이미 적용된 상태)
                        if pre_entry_analysis['proceed']:
                            # 🔥 거래 실행 직전 중지 신호 최종 확인
                            if hasattr(self.main_app, 'trading_worker') and self.main_app.trading_worker:
                                if not self.main_app.trading_worker.running:
                                    self.log_event('system', f'🔥 중지 신호 감지 - {symbol} 거래 실행 최종 중단', exchange='binance')
                                    break

                            self.log_event('trade', f"🎯 {symbol} AI 동적 거래 조건 충족! (신뢰도: {confidence:.3f} >= {dynamic_confidence_threshold:.3f})")

                            # AI 강화 파라미터 최적화 (기존 시스템 스타일)
                            optimized_params = self._get_ai_enhanced_parameters(symbol, signal_data, pre_entry_analysis)
                            if cold_start_profile and candidate.requires_noah_strategy_policy:
                                optimized_params['risk_multiplier'] = float(cold_start_profile.get('risk_multiplier', 0.10) or 0.10)
                                policy = resolve_effective_leverage(
                                    configured_leverage=(
                                        (optimized_params.get('_leverage_policy') or {}).get(
                                            'configured', self.settings.get('default_leverage', 1)
                                        )
                                    ),
                                    exchange='binance',
                                    market_level=(
                                        (optimized_params.get('_leverage_policy') or {}).get(
                                            'market_level', 'NORMAL'
                                        )
                                    ),
                                    exchange_max_leverage=exchange_leverage_cap(self.settings, 'binance'),
                                    cold_start_max_leverage=cold_start_profile.get('max_leverage', 1),
                                )
                                optimized_params['leverage'] = int(policy['effective'])
                                optimized_params['_leverage_policy'] = dict(policy)
                            self.last_effective_trade_params = getattr(
                                self, 'last_effective_trade_params', {}
                            )
                            self.last_effective_trade_params[symbol] = {
                                'exchange': 'binance',
                                'symbol': symbol,
                                'configured_leverage': int(
                                    (optimized_params.get('_leverage_policy') or {}).get(
                                        'configured', self.settings.get('default_leverage', 1)
                                    )
                                ),
                                'effective_leverage': int(optimized_params.get('leverage', 1) or 1),
                                'leverage_reason': str(
                                    (optimized_params.get('_leverage_policy') or {}).get('reason', '')
                                ),
                                'tp_percent': float(optimized_params.get('tp_percent', 0.0) or 0.0),
                                'sl_percent': float(optimized_params.get('sl_percent', 0.0) or 0.0),
                                'recorded_at': datetime.now(timezone.utc).isoformat(),
                            }
                            optimized_params['confidence'] = float(confidence or 0.0)
                            optimized_params['volatility'] = max(0.005, abs(float(signal_data.get('volatility', 0.5) or 0.5)) / 100.0)
                            optimized_params['model_version'] = str(signal_data.get('ai_model', '') or 'local')
                            optimized_params['strategy_variant'] = str(
                                signal_data.get('strategy_variant', 'unknown') or 'unknown'
                            )

                            allocation_result = self._build_portfolio_allocation_binance(symbol, signal_data, layer_settings)
                            self.portfolio_allocation_cache[symbol] = allocation_result
                            try:
                                spot_price = float(signal_data.get('current_price', signal_data.get('price', 0.0)) or 0.0)
                                fallback_qty = float(optimized_params.get('qty', 0.0) or 0.0)
                                if spot_price <= 0:
                                    spot_price = float(self.binance_client.get_current_price(symbol) or 0.0)
                                allocated_qty = PortfolioOrchestrator().quantity_from_allocation(
                                    symbol=symbol,
                                    price=spot_price,
                                    fallback_qty=fallback_qty,
                                    allocation_result=allocation_result,
                                )
                                optimized_params['qty'] = (
                                    min(fallback_qty, allocated_qty)
                                    if candidate.is_independent and fallback_qty > 0 and allocated_qty > 0
                                    else allocated_qty
                                )
                            except Exception:
                                pass

                            # ✅ 전략 확정 로그는 execute_trades 내부의 trade_config 기준으로 통일

                            # 거래 실행 (execute_trades 직접 호출)
                            self.log_event('trade', f"🔍 {symbol} 거래 실행 시작...")

                            try:
                                # execute_trades 직접 호출로 중복 제거
                                candidates = [{ 'symbol': symbol }]
                                optimized_params_wrapped = { symbol: optimized_params }
                                if execution_mode == ExecutionMode.LEARNING:
                                    dry_run_result = self.execute_trades(
                                        candidates,
                                        optimized_params_wrapped,
                                        dry_run=True,
                                    )
                                    learning_allowed = bool(dry_run_result)
                                    learning_plan = dict(optimized_params)
                                    learning_plan['order_validation_passed'] = learning_allowed
                                    record_learning_decision(
                                        'order_blocked_after_full_pipeline'
                                        if learning_allowed
                                        else 'order_spec_or_final_safety_blocked',
                                        'LEARNING 모드이므로 실제 주문 제출 차단'
                                        if learning_allowed
                                        else '최종 주문 규격 또는 안전 게이트 미통과',
                                        learning_plan,
                                    )
                                    self.log_event(
                                        'trade',
                                        f"🧠 {symbol} LEARNING 전체 판단 완료 - 후보={signal}, "
                                        f"출처={candidate.signal_source}, 전략={candidate.strategy_name or '기본 AI'}, "
                                        f"최종주문검증={'통과' if learning_allowed else '차단'} · 실제 주문 0건",
                                        exchange='binance',
                                    )
                                    continue
                                if paper_mode:
                                    paper_auth = get_opportunity_coordinator().authorize(
                                        policy=policy_from_settings(
                                            self.settings,
                                            authorized_targets=list(
                                                self.settings.get("enabled_exchanges", []) or ["binance"]
                                            ),
                                        ),
                                        asset_class="crypto",
                                        target="binance",
                                        symbol=symbol,
                                        direction=str(optimized_params.get("side") or signal),
                                        quantity=float(optimized_params.get("qty", 0.0) or 0.0),
                                        price=float(
                                            optimized_params.get("price")
                                            or signal_data.get("current_price")
                                            or 0.0
                                        ),
                                        stop_fraction=float(
                                            optimized_params.get("sl")
                                            or optimized_params.get("sl_percent")
                                            or 0.0
                                        ),
                                        strategy_version=str(
                                            candidate.strategy_version_id or "noah_base"
                                        ),
                                        account_scope="binance-paper",
                                    )
                                    if not paper_auth.allowed:
                                        self.log_event(
                                            "trade",
                                            f"🧪 {symbol} PAPER 기회 정책 차단: {paper_auth.reason}",
                                            exchange="binance",
                                        )
                                        trade_result = False
                                    else:
                                        paper_params = dict(optimized_params)
                                        paper_params["qty"] = float(
                                            paper_auth.authorized_quantity or 0.0
                                        )
                                        paper_params["_opportunity"] = paper_auth.to_dict()
                                        trade_result = self._execute_paper_trade(
                                            symbol,
                                            paper_params,
                                        )
                                        if trade_result:
                                            get_opportunity_coordinator().record_result(
                                                paper_auth,
                                                status="paper_filled",
                                            )
                                        else:
                                            get_opportunity_coordinator().release(paper_auth)
                                else:
                                    trade_result = self.execute_trades(candidates, optimized_params_wrapped)
                                self.log_event('trade', f"🔍 {symbol} 거래 실행 결과: {trade_result}")
                                cycle_metrics['attempted'] += 1
                                metric = self.last_order_execution_metrics.get(symbol, {}) if isinstance(self.last_order_execution_metrics, dict) else {}
                                latency_ms = float(metric.get('latency_ms', 0.0) or 0.0)
                                slippage_bps = float(metric.get('slippage_bps', 0.0) or 0.0)
                                if latency_ms > 0:
                                    cycle_metrics['latencies'].append(latency_ms)
                                if slippage_bps != 0.0:
                                    cycle_metrics['slippages'].append(slippage_bps)
                                if not trade_result:
                                    cycle_metrics['failed'] += 1
                                else:
                                    strategy_runtime_state[f'last_trade_at::{symbol.upper()}'] = datetime.now()
                            except Exception as e:
                                self.log_event('trade', f"❌ {symbol} 거래 실행 오류: {e}", level='ERROR')
                                import traceback
                                self.log_event('trade', f"❌ {symbol} 거래 실행 상세 오류: {traceback.format_exc()}", level='ERROR')
                                cycle_metrics['attempted'] += 1
                                cycle_metrics['failed'] += 1
                                continue

                            if trade_result:
                                self.log_event('trade', f"✅ {symbol} 포지션 진입 완료 - 모니터링 시작")
                            else:
                                self.log_event('trade', f"⏭️ {symbol} 거래 미실행(후행 게이트 차단 또는 조건 미충족)")
                        else:
                            self.log_event('trade', f"⏸️ {symbol} 거래 조건 미충족 (신호: {signal}, 신뢰도: {confidence:.2f})")

                    except Exception as e:
                        self.log_event('debug', f"코인 처리 중 예외 발생 - symbol: {symbol}, error: {e}", exchange='binance', level='DEBUG')
                        import traceback
                        self.log_event('debug', f"예외 상세: {traceback.format_exc()}", exchange='binance', level='DEBUG')
                        # symbol이 미리 정의되어 있으므로 그대로 사용
                        self.logger.error(f"❌ {symbol} 거래 신호 분석 오류: {e}")
                        continue
            else:
                self.logger.warning("선택된 코인이 없습니다")
                try:
                    self.logger.warning('선택된 코인이 없습니다')
                except Exception:
                    pass

            avg_latency = (sum(cycle_metrics['latencies']) / len(cycle_metrics['latencies'])) if cycle_metrics['latencies'] else 0.0
            avg_slippage = (sum(cycle_metrics['slippages']) / len(cycle_metrics['slippages'])) if cycle_metrics['slippages'] else 0.0
            attempts = int(cycle_metrics['attempted'] or 0)
            failed = int(cycle_metrics['failed'] or 0)
            reject_rate = (failed / attempts) if attempts > 0 else 0.0
            success_rate = ((attempts - failed) / attempts) if attempts > 0 else 0.0
            quality_score = max(0.0, min(100.0, round((success_rate * 100.0) - min(30.0, avg_latency / 40.0) - min(25.0, abs(avg_slippage) / 0.8), 2)))
            ops_engine = OpsAutomationEngine()
            anomalies = ops_engine.detect_anomalies(
                {'reject_rate': reject_rate, 'avg_slippage_bps': avg_slippage, 'quality_score': quality_score},
                dict(layer_settings.get('ops_automation', {}) or {}),
            )
            self.cycle_execution_metrics['binance'] = {
                'attempted_orders': attempts,
                'failed_orders': failed,
                'avg_latency_ms': round(avg_latency, 2),
                'avg_slippage_bps': round(avg_slippage, 2),
                'quality_score': quality_score,
                'anomalies': anomalies,
                'rollback_action': ops_engine.build_rollback_action(anomalies, dict(layer_settings.get('ops_automation', {}) or {})),
                'daily_briefing': ops_engine.build_daily_briefing(
                    {
                        'orders_executed': attempts - failed,
                        'execution_metrics': {
                            'quality_score': quality_score,
                            'reject_rate': reject_rate,
                            'avg_slippage_bps': avg_slippage,
                        },
                    },
                    anomalies,
                ),
                'profitability_validation': profitability_report,
            }

            # 사이클 완료 (예외 없이 정상 종료 시)
            try:
                self.logger.info('거래 사이클 완료')
            except Exception:
                pass

        except Exception as e:
            self.logger.error(f"거래 사이클 실행 오류: {e}")
            import traceback
            self.logger.error(f"상세 오류: {traceback.format_exc()}")
            try:
                log_exception('trade', '거래 사이클 실행 오류', exchange='binance', exc=e)
            except Exception:
                pass

    def execute_trades(self, candidates: List[Dict], optimized_params: Dict, dry_run: bool = False):
        """거래 실행. dry_run은 모든 최종 게이트를 평가하되 주문을 제출하지 않는다."""
        try:
            results = []
            self.log_event('trade', f"🔍 execute_trades 시작 - candidates: {len(candidates)}개, optimized_params 키: {list(optimized_params.keys()) if optimized_params else 'None'}")

            for candidate in candidates:
                symbol = candidate.get('symbol')
                if not symbol:
                    continue

                # 🔥 optimized_params에서 직접 거래 파라미터 가져오기
                trade_config = optimized_params.get(symbol, {})
                self.log_event('trade', f"[{symbol}] 🔍 trade_config 존재 여부: {bool(trade_config)}")

                # 🔥 중첩된 구조 처리: optimized_params[symbol]이 또 다른 딕셔너리일 수 있음
                if isinstance(trade_config, dict) and symbol in trade_config:
                    # 중첩된 구조: {'ADAUSDT': {'ADAUSDT': {...}}}
                    trade_config = trade_config[symbol]
                    self.log_event('trade', f"[{symbol}] 🔧 중첩된 구조 감지 - 내부 딕셔너리 사용")

                self.log_event('trade', f"[{symbol}] 🔍 최종 trade_config: {trade_config}")

                # 🔒 단일 소스 정책: Optimizer가 tp/sl을 반드시 제공해야 함 (없으면 스킵)
                if not trade_config or ('tp' not in trade_config) or ('sl' not in trade_config) or \
                   trade_config.get('tp') is None or trade_config.get('sl') is None:
                    self.log_event('trade', f"[{symbol}] ❌ trade_config에 tp/sl 누락 - Optimizer 출력 불완전. 거래 스킵", level='ERROR')
                    continue
                # 숫자 타입 보장
                if not isinstance(trade_config.get('tp'), (int, float)) or not isinstance(trade_config.get('sl'), (int, float)):
                    self.log_event('trade', f"[{symbol}] ❌ tp/sl 타입 오류 - 숫자 아님: tp={type(trade_config.get('tp'))}, sl={type(trade_config.get('sl'))}", level='ERROR')
                    continue
                raw_tp = float(trade_config.get('tp'))
                raw_sl = float(trade_config.get('sl'))
                if not (0.0005 <= raw_tp <= 0.05 and 0.0005 <= raw_sl <= 0.03):
                    self.log_event(
                        'trade',
                        f"[{symbol}] ❌ TP/SL 실행 범위 위반 - tp={raw_tp}, sl={raw_sl}. 거래 스킵",
                        level='ERROR',
                    )
                    continue

                # ✅ 통일된 로그 출력 (trade_config 기준) - 거래 실행 전에 출력
                if trade_config:
                    final_lev = trade_config.get('leverage', 1)
                    final_tp = float(trade_config.get('tp') or 0.0)
                    final_sl = float(trade_config.get('sl') or 0.0)
                    final_qty = trade_config.get('qty', 0)
                    final_price = trade_config.get('price', 0)

                    # 거래 파라미터 상세 로그 (trade_config 기준으로 통일)
                    self.log_event('trade', f"[{symbol}] 거래 파라미터 상세 (trade_config 기준):")
                    self.log_event('trade', f"  - 신호: {trade_config.get('side', 'BUY')}")
                    self.log_event('trade', f"  - 레버리지: {final_lev}x")
                    self.log_event('trade', f"  - 수량: {final_qty}")
                    self.log_event('trade', f"  - 가격: {final_price}")
                    self.log_event('trade', f"  - 거래금액: {final_qty * final_price:.2f} USDT")
                    self.log_event('trade', f"  - TP: {final_tp:.4f} ({format_percent(final_tp)})")
                    self.log_event('trade', f"  - SL: {final_sl:.4f} ({format_percent(final_sl)})")

                    # 전략 확정 로그도 trade_config 기준으로 통일
                    self._log_trade_event('strategy', (
                        f"{symbol} 전략 확정 (trade_config 기준): "
                        f"side={trade_config.get('side', 'BUY')}, "
                        f"lev={final_lev}x, "
                        f"qty={final_qty}, "
                        f"tp={format_percent(final_tp, 3)}, "
                        f"sl={format_percent(final_sl, 3)}"
                    ), verbose_only=True)

                if trade_config:
                    # 🔥 파라미터 검증 (삭제된 execute_enhanced_trade에서 이동)
                    leverage = trade_config.get('leverage', int(self.settings.get('default_leverage', 1)))
                    qty = trade_config.get('qty', 0)

                    if not leverage or leverage <= 0:
                        self.log_event('trade', f"❌ {symbol} 잘못된 레버리지: {leverage}", level='ERROR')
                        continue

                    if not qty or qty <= 0:
                        self.log_event('trade', f"❌ {symbol} 잘못된 수량: {qty}", level='ERROR')
                        continue

                    # 🔥 이제 Optimizer에서 완성된 파라미터를 받음
                    exit_plan = dict(trade_config.get('_exit_plan') or {})
                    exit_policy = build_exit_policy(
                        settings=self.settings,
                        exit_plan=exit_plan,
                        effective_tp_fraction=float(trade_config.get('tp') or 0.0),
                        effective_sl_fraction=float(trade_config.get('sl') or 0.0),
                        effective_reason=(
                            'AI 커스텀 전략 원형'
                            if exit_plan.get('strategy_owned')
                            else '종목·변동성 기반 동적 청산'
                        ),
                        entry_price=float(trade_config.get('price') or 0.0),
                        side=str(trade_config.get('side', candidate.get('side', 'BUY'))),
                        asset_class='crypto',
                        target='binance',
                        symbol=symbol,
                    )
                    trade_params = {
                        'symbol': symbol,
                        'side': trade_config.get('side', candidate.get('side', 'BUY')),
                        'qty': qty,
                        'price': trade_config.get('price', 0),  # ✅ price 필드 추가
                        'leverage': leverage,
                        'tp': float(trade_config.get('tp') or 0.0),
                        'sl': float(trade_config.get('sl') or 0.0),
                        'confidence': float(trade_config.get('confidence', 0.0) or 0.0),
                        'volatility': float(trade_config.get('volatility', 0.02) or 0.02),
                        'mode': trade_config.get('mode', 'optimized'),
                        'orderType': trade_config.get('orderType', 'MARKET'),
                        'filters': trade_config.get('filters'),  # ✅ 추가
                        'risk_multiplier': float(trade_config.get('risk_multiplier', 1.0) or 1.0),
                        'model_version': str(trade_config.get('model_version', '') or 'local'),
                        'strategy_variant': str(trade_config.get('strategy_variant', 'unknown') or 'unknown'),
                        '_selected_custom_strategy': trade_config.get('_selected_custom_strategy'),
                        '_selected_custom_strategy_id': trade_config.get('_selected_custom_strategy_id'),
                        '_selected_custom_strategy_key': trade_config.get('_selected_custom_strategy_key'),
                        '_selected_custom_strategy_version_id': trade_config.get('_selected_custom_strategy_version_id'),
                        '_custom_signal_mode': trade_config.get('_custom_signal_mode'),
                        '_custom_operation_mode': trade_config.get('_custom_operation_mode'),
                        '_exit_plan': dict(trade_config.get('_exit_plan') or {}),
                        '_exit_policy': exit_policy,
                        '_custom_strategy_rules': dict(trade_config.get('_custom_strategy_rules') or {}),
                    }

                    self.log_event(
                        'trade',
                        f"[{symbol}] {format_exit_policy(exit_policy)}",
                        exchange='binance',
                    )
                    self.log_event('trade', f"[{symbol}] 🔍 최종 거래 파라미터: {trade_params}")
                    self.log_event('trade', f"[{symbol}] 🔍 qty 값: {trade_params['qty']} (원본: {trade_config.get('qty', 'N/A')})")

                    # 거래 실행
                    self.log_event('trade', f"[{symbol}] 🔍 should_execute_trade 호출 전")
                    should_execute = self.should_execute_trade(trade_params)
                    self.log_event('trade', f"[{symbol}] 🔍 should_execute_trade 결과: {should_execute}")

                    if should_execute:
                        authorized_targets = (
                            list(self.settings.get("enabled_exchanges", []) or [])
                            if dry_run
                            else list(self.settings.get("trade_enabled_exchanges", []) or [])
                        )
                        if not authorized_targets:
                            authorized_targets = ["binance"]
                        opportunity_auth = get_opportunity_coordinator().authorize(
                            policy=policy_from_settings(
                                self.settings,
                                authorized_targets=authorized_targets,
                            ),
                            asset_class="crypto",
                            target="binance",
                            symbol=symbol,
                            direction=str(trade_params.get("side") or "BUY"),
                            quantity=float(trade_params.get("qty", 0.0) or 0.0),
                            price=float(trade_params.get("price", 0.0) or 0.0),
                            stop_fraction=float(trade_params.get("sl", 0.0) or 0.0),
                            strategy_version=str(
                                trade_params.get("_selected_custom_strategy_version_id")
                                or "noah_base"
                            ),
                            account_scope=str(
                                self.settings.get("account_id")
                                or self.settings.get("user_id")
                                or f"binance:{id(self)}"
                            ),
                            reserve=not dry_run,
                        )
                        trade_params["_opportunity"] = opportunity_auth.to_dict()
                        trade_params["_opportunity_quantity_factor"] = float(
                            opportunity_auth.quantity_factor or 0.0
                        )
                        trade_params["qty"] = float(
                            opportunity_auth.authorized_quantity or 0.0
                        )
                        if not opportunity_auth.allowed:
                            self.log_event(
                                "trade",
                                f"[{symbol}] 다중 거래소 기회 정책 차단: "
                                f"{opportunity_auth.reason} "
                                f"(id={opportunity_auth.opportunity_id})",
                                exchange="binance",
                                level="INFO",
                            )
                            continue
                        self.log_event(
                            "trade",
                            f"[{symbol}] 🔗 기회연결 id={opportunity_auth.opportunity_id}, "
                            f"mode={opportunity_auth.execution_mode}, "
                            f"qty_factor={opportunity_auth.quantity_factor:.4f}, "
                            f"aggregate_targets={opportunity_auth.aggregate_targets}, "
                            f"aggregate_loss={opportunity_auth.aggregate_estimated_loss:.4f} "
                            f"{opportunity_auth.quote_currency}",
                            exchange="binance",
                        )
                        if dry_run:
                            self.log_event(
                                'trade',
                                f"[{symbol}] 🧠 LEARNING 최종 주문 규격 검증 통과 - 주문 제출 생략",
                                exchange='binance',
                            )
                            results.append({'status': 'learning_planned', 'trade_params': dict(trade_params)})
                            continue
                        self.log_event('trade', f"[{symbol}] 🔍 거래 실행 조건 충족 - execute_single_trade 호출")
                        try:
                            trade_result = self.execute_single_trade(trade_params)
                        except Exception as trade_exc:
                            get_opportunity_coordinator().release(opportunity_auth)
                            get_opportunity_coordinator().record_result(
                                opportunity_auth,
                                status="failed",
                                detail=str(trade_exc),
                            )
                            raise
                        if trade_result:
                            get_opportunity_coordinator().record_result(
                                opportunity_auth,
                                status="submitted",
                                order_id=str(
                                    trade_result.get("order_id")
                                    or trade_result.get("id")
                                    or ""
                                ) if isinstance(trade_result, dict) else "",
                            )
                            self.log_event('trade', f"[{symbol}] ✅ 거래 실행 성공 - results에 추가")
                            results.append(trade_result)
                        else:
                            get_opportunity_coordinator().release(opportunity_auth)
                            get_opportunity_coordinator().record_result(
                                opportunity_auth,
                                status="failed",
                                detail="execute_single_trade returned no result",
                            )
                            self.log_event('trade', f"[{symbol}] ⏭️ 거래 미실행 - execute_single_trade 반환값: {trade_result}")
                    else:
                        self.log_event('trade', f"[{symbol}] ⏭️ 거래 스킵 - should_execute_trade=False")
                else:
                    self.log_event('trade', f"[{symbol}] ❌ trade_config 없음 - optimized_params에서 {symbol} 키 없음")

            # 🔥 실제 거래 결과가 있을 때만 True 반환
            if results:
                if dry_run:
                    self.logger.info(f"🧠 LEARNING 최종 주문 계획 검증 완료: {len(results)}개")
                else:
                    self.logger.info(f"✅ 포지션 진입 완료: {len(results)}개 포지션 생성")
                return results
            else:
                self.logger.info("⏭️ 거래 실행 결과 없음(조건 미충족/게이트 차단)")
                self._log_trade_event('trade', f"no_fill summary: candidates={len(candidates)}, optimized_keys={list(optimized_params.keys()) if optimized_params else 'None'}", level='INFO', verbose_only=True)
                return False

        except Exception as e:
            self.logger.error(f"거래 실행 중 오류: {e}")
            return False
    def should_execute_trade(self, trade_params: Dict) -> bool:
        """거래 실행 여부 판단 (폴백 플랜 지원)"""
        try:
            symbol = trade_params['symbol']
            self.log_event('trade', f"[{symbol}] 🔍 거래 실행 조건 검증 시작")

            # 🔥 필터 정규화 방어 코드 (이중 안전장치)
            if 'filters' in trade_params and trade_params['filters']:
                filters = trade_params['filters']

                # camelCase → snake_case 정규화
                if 'step_size' not in filters and ('stepSize' in filters or 'minQty' in filters):
                    normalized_filters = {
                        'step_size': filters.get('stepSize'),
                        'min_qty': filters.get('minQty'),
                        'quantity_precision': filters.get('quantity_precision') or filters.get('quantityPrecision'),
                        'price_precision': filters.get('price_precision') or filters.get('pricePrecision'),
                        'min_notional': filters.get('min_notional') or filters.get('minNotional'),
                    }
                    trade_params['filters'] = normalized_filters
                    self.log_event('trade', f"[{symbol}] 🔧 필터 정규화 완료: {normalized_filters}")

            # 🔥 새로운 파라미터 구조에 맞춘 검증
            # 수량 확인
            qty = trade_params.get('qty', 0)
            self.log_event('trade', f"[{symbol}] 🔍 수량 검증: {qty} (타입: {type(qty)})")
            if qty <= 0:
                self.log_event('trade', f"[{symbol}] ❌ 거래 차단 사유: 수량 부족 ({qty})", level='WARNING')
                self.log_event('trade', f"[{symbol}] 🔍 전체 trade_params: {trade_params}", level='WARNING')
                return False

            # 🔥 새로운 수량 보정 로직: 스텝 스냅 → 최저금액 보장 (올림 방향)
            price = trade_params.get('price', 0)

            # 🔥 price가 0/None일 때 현재가 조회
            if not price or price <= 0:
                try:
                    if hasattr(self, 'binance_client') and self.binance_client:
                        price = float(self.binance_client.get_current_price(symbol)) or 0
                        trade_params['price'] = price  # trade_params 업데이트
                        self.log_event('trade', f"[{symbol}] 🔧 현재가 조회로 price 보정: {price}")
                except Exception as e:
                    self.log_event('trade', f"[{symbol}] 현재가 조회 실패: {e} - 거래 차단", level='WARNING')
                    return False

            if price > 0:
                # 🔥 1단계: Optimizer에서 전달받은 필터 정보 우선 사용 (재조회 방지)
                step_size = 1.0  # 기본값 (보수적)
                quantity_precision = 8  # 기본값
                min_notional = self.settings.get('min_trade_amount', 5.0)  # 🔥 설정값 사용

                # 🔥 Optimizer의 filters 정보 확인 (snake_case 키 사용)
                if 'filters' in trade_params and trade_params['filters']:
                    filters = trade_params['filters']
                    step_size = filters.get('step_size', 1.0)
                    quantity_precision = filters.get('quantity_precision', 8)
                    min_qty = filters.get('min_qty', 0.01)

                    # 🔥 바이낸스 API의 min_notional과 설정값 중 더 큰 값 사용 (안전성)
                    api_min_notional = None
                    if isinstance(filters, dict):
                        api_min_notional = filters.get('min_notional', filters.get('minNotional'))
                    if api_min_notional is None:
                        api_min_notional = 0.0
                    config_min_notional = float(self.settings.get('min_trade_amount', 5.0))
                    min_notional = max(float(api_min_notional), config_min_notional)

                    self.log_event('trade', f"[{symbol}] 🔍 Optimizer 필터 사용: step_size={step_size}, precision={quantity_precision}, min_notional={min_notional}")

                    # 🔥 잔고/레버리지/최소수량으로 "거래 가능성" 사전 필터
                    leverage = trade_params.get('leverage', int(self.settings.get('default_leverage', 1)))
                    min_cost = price * min_qty / leverage
                    try:
                        if hasattr(self, 'binance_client') and self.binance_client:
                            account_info = self.binance_client.get_account_info()
                            if account_info:
                                available_balance = float(account_info.get('available_balance', 0))
                                if min_cost > available_balance * 0.8:  # 잔고의 80% 초과 시 스킵
                                    self.log_event('trade', f"[{symbol}] ❌ 거래 차단 사유: 최소수량 기준 잔고 부족 (필요: {min_cost:.2f} USDT, 보유: {available_balance:.2f} USDT)", level='WARNING')
                                    return False
                    except Exception as e:
                        self.log_event('trade', f"[{symbol}] 잔고 확인 실패: {e} - 거래 계속 진행", level='WARNING')

                else:
                    # 🔥 폴백: Optimizer 필터가 없을 때만 재조회 (안전장치)
                    self.log_event('trade', f"[{symbol}] ⚠️ Optimizer 필터 정보 없음 - 재조회 시도", level='WARNING')
                    try:
                        if hasattr(self, 'binance_client') and self.binance_client:
                            if hasattr(self.binance_client, 'get_symbol_info_direct'):
                                symbol_info = self.binance_client.get_symbol_info_direct(symbol)
                                if symbol_info:
                                    step_size = symbol_info.get('step_size', 1.0)
                                    quantity_precision = symbol_info.get('quantity_precision', 8)
                                    # 🔥 바이낸스 API의 min_notional과 설정값 중 더 큰 값 사용 (안전성)
                                    api_min_notional = symbol_info.get('min_notional', 5.0)
                                    config_min_notional = self.settings.get('min_trade_amount', 5.0)
                                    min_notional = max(api_min_notional, config_min_notional)

                                    self.log_event('trade', f"[{symbol}] 🔍 재조회 심볼 정보: step_size={step_size}, precision={quantity_precision}, min_notional={min_notional}")
                    except Exception as e:
                        self.log_event('trade', f"[{symbol}] 심볼 정보 재조회 실패: {e} - 보수적 기본값 사용", level='WARNING')

                # 🔥 수량 계산 단일화: binance_client.calculate_precise_quantity 사용
                if hasattr(self, 'binance_client') and self.binance_client:
                    if hasattr(self.binance_client, 'calculate_precise_quantity'):
                        # 목표 거래 금액으로 정확한 수량 계산
                        target_value = max(qty * price, float(min_notional) * 1.01)
                        precise_qty = self.binance_client.calculate_precise_quantity(symbol, target_value)
                        if precise_qty and precise_qty > 0:
                            self.log_event('trade', f"[{symbol}] 🔧 정밀도 수량 계산: {qty} → {precise_qty} (목표: {target_value:.2f} USDT)")
                            qty = precise_qty
                            trade_params['qty'] = precise_qty
                        else:
                            self.log_event('trade', f"[{symbol}] ⚠️ 정밀도 수량 계산 실패, 기존 값 사용: {qty}", level='WARNING')
                    else:
                        self.log_event('trade', f"[{symbol}] ⚠️ calculate_precise_quantity 메서드 없음, 기존 로직 사용", level='WARNING')
                else:
                    self.log_event('trade', f"[{symbol}] ⚠️ binance_client 없음, 기존 로직 사용", level='WARNING')

            # 이미 해당 심볼에 포지션이 있는지 확인
            if symbol in self.active_positions:
                self.log_event('trade', f"[{symbol}] ❌ 거래 차단 사유: 활성 포지션 존재", level='WARNING')
                return False

            # 최대 포지션 수 확인
            effective_position_count = len(self.active_positions) + len(
                getattr(self, 'external_position_symbols', set())
            )
            if effective_position_count >= self.settings['max_positions']:
                self.log_event(
                    'trade',
                    f"[{symbol}] ✅ 최대 포지션 수 도달로 거래 제한 - 정상 동작 "
                    f"(관리+수동/외부: {effective_position_count}개, 최대: {self.settings['max_positions']}개)"
                )
                return False

            # 🔥 잔고 확인 (거래 실행 전에 미리 체크)
            try:
                if hasattr(self, 'binance_client') and self.binance_client:
                    account_info = self.binance_client.get_account_info()
                    if account_info:
                        available_balance = float(account_info.get('available_balance', 0))
                        required_amount = qty * price

                        if available_balance < required_amount:
                            self.log_event('trade', f"[{symbol}] ❌ 거래 차단 사유: 잔고 부족 (필요: {required_amount:.2f} USDT, 보유: {available_balance:.2f} USDT)", level='WARNING')
                            return False
                        else:
                            self.log_event('trade', f"[{symbol}] 💰 잔고 확인 완료: {available_balance:.2f} USDT (필요: {required_amount:.2f} USDT)")
            except Exception as e:
                self.log_event('trade', f"[{symbol}] 잔고 확인 실패: {e} - 거래 실행 계속 진행", level='WARNING')

            self.log_event('trade', f"[{symbol}] ✅ 모든 거래 실행 조건 통과")

            # AI 사전 검증은 기본·일반 경로에만 적용한다. 고급 커스텀의
            # 방향·조건·수량·레버리지를 후단에서 다시 바꾸면 전략 원형이 깨진다.
            if (
                trade_params.get('_custom_signal_mode') != 'independent'
                and self.ai_manager
                and getattr(
                    self.ai_manager,
                    'enabled_for_role',
                    lambda _role: self.ai_manager.enabled(),
                )('pattern_similarity')
            ):
                try:
                    current_signal_data = {
                        'signal_type': trade_params.get('side', 'UNKNOWN'),
                        'signal_reason': trade_params.get('reason', ''),
                        'rsi_15m': None,
                        'rsi_1h': None,
                        'market_trend': '',
                        'volatility': 0.0
                    }

                    # 기술적 지표 추가
                    try:
                        rsi = self.analyzer.calculate_rsi_for_symbol(symbol)
                        current_signal_data['rsi_15m'] = rsi
                        current_signal_data['rsi_1h'] = rsi
                    except Exception:
                        pass

                    try:
                        state = self.analyzer.get_market_state(symbol)
                        if state:
                            current_signal_data['volatility'] = getattr(state, 'volatility', 0.0)
                    except Exception:
                        pass

                    # 최근 손실 패턴 조회
                    recent_patterns = self.recorder.get_recent_loss_patterns(symbol, limit=5)

                    if recent_patterns:
                        decision = self.ai_manager.analyze_pattern_similarity(symbol, current_signal_data, recent_patterns)
                        if decision:
                            action = (decision.get('action') or 'PROCEED').upper()

                            if action == 'SKIP':
                                self.log_event('trade', f"[{symbol}] ❌ AI 패턴 분석: SKIP - {decision.get('reason', '')}")
                                return False

                            elif action == 'ADJUST':
                                # 보수적 조정: 수량 20% 감소, 레버리지 20% 감소
                                if 'qty' in trade_params and isinstance(trade_params['qty'], (int, float)):
                                    trade_params['qty'] = max(0, trade_params['qty'] * 0.8)
                                if 'leverage' in trade_params and isinstance(trade_params['leverage'], int):
                                    trade_params['leverage'] = max(1, int(trade_params['leverage'] * 0.8))

                                self.log_event('trade', f"[{symbol}] 🔧 AI 패턴 분석: ADJUST - {decision.get('reason', '')}")
                    else:
                        self.log_event('trade', f"[{symbol}] ℹ️ AI 패턴 분석: 최근 손실 패턴 없음 - 거래 진행")

                except Exception as e:
                    self.log_event('trade', f"[{symbol}] AI 패턴 분석 오류: {e}", level='ERROR')
            elif trade_params.get('_custom_signal_mode') == 'independent':
                self.log_event(
                    'trade',
                    f"[{symbol}] 🛡️ 고급 AI 커스텀 전략 원형 유지 - 후단 AI 패턴 재심사 생략",
                )
            else:
                self.log_event('trade', f"[{symbol}] ℹ️ AI 매니저 비활성화 - 거래 진행")

            self.log_event('trade', f"[{symbol}] ✅ should_execute_trade 최종 승인")
            return True

        except Exception as e:
            self.log_event('trade', f"거래 실행 판단 중 오류: {e}", level='ERROR')
            return False

    def execute_single_trade(self, trade_params: Dict):
        """단일 거래 실행 (폴백 플랜 지원)"""
        symbol = trade_params['symbol']

        try:
            if not self._is_live_entry_enabled('binance'):
                self.log_event(
                    'trade',
                    f"🧠 {symbol} 학습 전용 - execute_single_trade 신규 진입 차단",
                    exchange='binance',
                    level='INFO',
                )
                return False
            side = trade_params['side']
            qty = trade_params.get('qty', 0)
            leverage = trade_params.get('leverage', int(self.settings.get('default_leverage', 1)))

            # 🔥 TP/SL 검증 플래그 초기화
            tp_sl_verified = False

            # 🔥 재시도 횟수 체크 (무한 루프 방지)
            retry_count = trade_params.get('retry_count', 0)
            if retry_count > 0:
                self.log_event('trade', f"[{symbol}] 🔄 재시도 #{retry_count} 시작")

            self.log_event('trade', f"[{symbol}] 🔍 execute_single_trade 시작 - side: {side}, qty: {qty}, leverage: {leverage}")

            # 🔥 동적 TP/SL 조정 (소수 단위로 통일)
            # 이미 trade_params에 tp/sl이 있으면 재계산 생략하여 중복/충돌 방지
            tp_val = trade_params.get('tp') if 'tp' in trade_params else None
            sl_val = trade_params.get('sl') if 'sl' in trade_params else None
            if tp_val is not None and sl_val is not None:
                tp = float(tp_val)
                sl = float(sl_val)
            else:
                self.log_event('trade', f"[{symbol}] ❌ execute_single_trade: tp/sl 누락 - Optimizer 단일 소스 정책 위반", level='ERROR')
                return False
            if not (0.0005 <= tp <= 0.05 and 0.0005 <= sl <= 0.03):
                self.log_event(
                    'trade',
                    f"[{symbol}] ❌ execute_single_trade TP/SL 범위 위반: tp={tp}, sl={sl}",
                    level='ERROR',
                )
                return False
            mode = trade_params.get('mode', 'optimized')

            self.log_event('trade', f"[{symbol}] 🔍 TP/SL 설정 - tp: {tp}, sl: {sl}, mode: {mode}")

            if qty <= 0:
                self.log_event('trade', f"[{symbol}] ❌ 수량 부족: {qty}", level='WARNING')
                return False

            # 🔥 autotrade.py와 동일: 거래 진입 플래그 체크
            if self.trade_entered.get(symbol, False):
                self.log_event('trade', f"[{symbol}] ℹ️ 이미 거래 중인 코인 - 스킵")
                return False

            # 🔥 거래 진입 플래그 설정
            self.trade_entered[symbol] = True
            self.log_event('trade', f"[{symbol}] 🔍 거래 진입 플래그 설정 완료")

            # 🔥 집중모드 시작 로그
            try:
                self._log_trade_event('monitor', f"{symbol} 집중모드 시작 - 포지션 모니터링 활성화")
            except Exception:
                pass

            # 리스크 분석 로그 (verbose)
            if self.settings.get('verbose_trade_logging', False):
                try:
                    # 포지션 크기 비율 계산
                    balance_info = self.binance_client.get_balance()
                    if isinstance(balance_info, dict):
                        balance = balance_info.get('USDT', {}).get('free', 0)
                    else:
                        balance = float(balance_info) if balance_info else 0
                    position_value = qty * trade_params.get('entry_price', 0)
                    position_ratio = (position_value / balance) * 100 if balance > 0 else 0

                    # 청산 거리 계산 (대략적)
                    liquidation_distance = (1 / leverage) * 100 if leverage > 0 else 0

                    self._log_trade_event('analysis', f"{symbol} Risk analysis: position_ratio={position_ratio:.2f}%, leverage={leverage}x, liquidation_distance={liquidation_distance:.1f}%, tp={tp*100:.2f}%, sl={sl*100:.2f}%")
                except Exception as e:
                    self._log_trade_event('analysis', f"{symbol} Risk analysis failed: {str(e)}")

            # 🔥 신규 주문 전 기존 오픈오더 정리 (autotrade.py와 동일한 안전한 방식)
            self.log_event('trade', f"[{symbol}] 🔍 기존 오픈오더 정리 시작")
            try:
                position_info = self._get_position_info_with_retry(symbol)
                if not position_info or abs(float(position_info.get('positionAmt', 0))) == 0:
                    # 포지션이 없을 때만 오픈오더 정리 (안전함)
                    open_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)
                    if open_orders:
                        self.log_event('trade', f"[{symbol}] ⚠️ 포지션 없는데 미체결 주문 발견: {len(open_orders)}개", level='WARNING')
                        self.log_event('trade', f"[{symbol}] 🔍 주문 상세: {[(order['type'], order['side'], order.get('stopPrice', 'N/A')) for order in open_orders]}")

                        # 포지션 없을 때만: TP/SL 외 주문 선별 취소 우선
                        try:
                            others0 = [o for o in open_orders if o.get('type') not in ('TAKE_PROFIT','TAKE_PROFIT_MARKET','STOP','STOP_MARKET')]
                            if others0:
                                if hasattr(self.binance_client, 'cancel_orders'):
                                    self.binance_client.cancel_orders(symbol, [o['orderId'] for o in others0])
                                else:
                                    self.binance_client.cancel_all_orders(symbol)
                        except Exception:
                            pass
                            self.log_event('trade', f"[{symbol}] ✅ 신규 주문 전 기존 주문 정리 완료")
                            time.sleep(0.5)

                            # 정리 확인
                            remaining_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)
                            if remaining_orders:
                                self.log_event('trade', f"[{symbol}] ❌ 주문 정리 실패 - 신규 주문 중단", level='ERROR')
                                return False
                        else:
                            self.log_event('trade', f"[{symbol}] ❌ 기존 주문 정리 실패", level='ERROR')
                            return False
                else:
                    # 포지션이 있는 경우 오픈오더 보호 (TP/SL 주문이므로)
                    self.log_event('trade', f"[{symbol}] ℹ️ 포지션 존재 - 오픈오더 보호 (TP/SL 주문)")
            except Exception as e:
                self.log_event('trade', f"[{symbol}] ⚠️ 오픈오더 정리 중 오류: {e}", level='WARNING')
                # 오류 발생 시에도 거래 계속 진행

            # 🔥 거래 실행 전 잔고 검증 추가
            self.log_event('trade', f"[{symbol}] 🔍 잔고 검증 시작")
            current_price = 0.0  # 초기화 (타입 안전성)
            try:
                balance = self.binance_client.get_balance()
                usdt_info = balance.get('USDT') if isinstance(balance, dict) else None
                available_usdt = 0.0

                if isinstance(usdt_info, dict):
                    available_usdt = float(usdt_info.get('available_balance', 0))
                elif isinstance(balance, (int, float)):
                    available_usdt = float(balance)

                self.log_event('trade', f"[{symbol}] 🔍 사용 가능한 USDT: {available_usdt}")

                # 현재가 조회
                current_price = self.binance_client.get_current_price(symbol)
                if not current_price or current_price <= 0:
                    self.log_event('trade', f"[{symbol}] ❌ 현재가 조회 실패", level='ERROR')
                    return False

                self.log_event('trade', f"[{symbol}] 🔍 현재가: {current_price}")

                # 필요한 거래 금액 계산 (레버리지 반영)
                leverage = trade_params.get('leverage', int(self.settings.get('default_leverage', 1)))
                fee_buf = 1.002  # 0.2% 수수료 버퍼
                required_margin = (qty * current_price / max(leverage, 1)) * fee_buf

                self.log_event('trade', f"[{symbol}] 🔍 필요한 마진: {required_margin:.2f} USDT (레버리지: {leverage}x)")

                if available_usdt < required_margin:
                    self.log_event('trade', f"[{symbol}] ❌ 잔고 부족 - 사용가능: {available_usdt:.2f} USDT, 필요: {required_margin:.2f} USDT", level='ERROR')
                    return False

                self.log_event('trade', f"[{symbol}] ✅ 잔고 검증 통과")
            except Exception as e:
                self.log_event('trade', f"[{symbol}] ⚠️ 잔고 검증 중 오류: {e}", level='WARNING')
                # 오류 발생 시에도 거래 계속 진행 (current_price가 0이면 나중에 재조회)

            # 레버리지 설정
            self.log_event('trade', f"[{symbol}] 🔍 레버리지 설정: {leverage}x")
            self.binance_client.set_leverage(symbol, leverage)

            # 🔥 보정된 수량 사용 (should_execute_trade에서 수정된 값)
            quantity = trade_params.get('qty', qty)
            self.log_event('trade', f"[{symbol}] 🔍 최종 거래 수량: {quantity}")

            # 🔥 보수적 참조 가격으로 최종 검증 (BUY: +0.5% 슬리피지, SELL: -0.5% 슬리피지)
            self.log_event('trade', f"[{symbol}] 🔍 참조가격 계산 시작 (current_price={current_price})")
            try:
                # current_price가 0이면 재조회
                if current_price <= 0:
                    self.log_event('trade', f"[{symbol}] 🔍 current_price가 0 이하 - 재조회 시도")
                    current_price = self.binance_client.get_current_price(symbol)
                    if not current_price or current_price <= 0:
                        self.log_event('trade', f"[{symbol}] ❌ 참조가격 계산용 현재가 조회 실패", level='ERROR')
                        self._reset_trade_flag(symbol)
                        return False
                    self.log_event('trade', f"[{symbol}] ✅ 현재가 재조회 완료: {current_price}")

                if side == 'BUY':
                    # BUY: 현재가 + 0.5% 슬리피지 버퍼 (체결가 상승 대비)
                    ref_price = current_price * 1.005
                    self.log_event('trade', f"[{symbol}] 🔍 BUY 참조가격: {current_price:.6f} → {ref_price:.6f} (+0.5% 슬리피지 버퍼)")
                else:
                    # SELL: 현재가 - 0.5% 슬리피지 버퍼 (체결가 하락 대비)
                    ref_price = current_price * 0.995
                    self.log_event('trade', f"[{symbol}] 🔍 SELL 참조가격: {current_price:.6f} → {ref_price:.6f} (-0.5% 슬리피지 버퍼)")

                # 🔥 수량 계산 단일화: 슬리피지 버퍼를 고려한 정확한 수량 계산
                # _compute_quantity_once가 min_notional을 고려하여 수량을 조정하므로
                # 슬리피지 적용 후에도 min_notional을 만족하는 수량을 보장함
                self.log_event('trade', f"[{symbol}] 🔍 _compute_quantity_once 호출 시작 (symbol={symbol}, side={side}, leverage={leverage}, ref_price={ref_price:.6f})")
                computed_qty, computed_price = self._compute_quantity_once(
                    symbol, side, leverage, ref_price,
                    risk_multiplier=float(trade_params.get('risk_multiplier', 1.0) or 1.0),
                )

                if computed_qty is None or computed_price is None:
                    self.log_event('trade', f"[{symbol}] ❌ 수량 계산 실패: computed_qty={computed_qty}, computed_price={computed_price}", level='ERROR')
                    self._reset_trade_flag(symbol)
                    return False

                self.log_event('trade', f"[{symbol}] ✅ _compute_quantity_once 완료: qty={computed_qty}, price={computed_price:.6f}")

                # 계산된 수량으로 업데이트
                opportunity_factor = max(
                    0.0,
                    min(
                        1.0,
                        float(
                            trade_params.get("_opportunity_quantity_factor", 1.0)
                            or 0.0
                        ),
                    ),
                )
                authorized_quantity_cap = max(
                    0.0,
                    float(trade_params.get("qty", 0.0) or 0.0),
                )
                quantity = computed_qty * opportunity_factor
                if authorized_quantity_cap > 0.0:
                    quantity = min(quantity, authorized_quantity_cap)
                ref_price = computed_price
                if opportunity_factor < 1.0:
                    self.log_event(
                        "trade",
                        f"[{symbol}] 다중 거래소 총위험 분할 적용: "
                        f"qty {computed_qty} × {opportunity_factor:.4f} = {quantity}",
                    )
                
                # 🔥 최종 검증: _compute_quantity_once 결과로 min_notional 재확인
                min_notional = self.settings.get('min_trade_amount', 5.0)
                final_amount = quantity * ref_price
                self.log_event('trade', f"[{symbol}] 🔍 최종 거래금액 검증: qty={quantity}, ref_price={ref_price:.6f}, final_amount={final_amount:.2f}, min_notional={min_notional}")
                
                if final_amount < min_notional:
                    self.log_event('trade', f"[{symbol}] ❌ 최종 검증 실패: {final_amount:.2f} USDT < {min_notional} USDT (이론적으로 발생하지 않아야 함)", level='ERROR')
                    self._reset_trade_flag(symbol)
                    return False

                self.log_event('trade', f"[{symbol}] 🔍 최종 주문 파라미터: qty={quantity}, amount={final_amount:.2f} USDT (참조가: {ref_price:.6f})")

            except Exception as e:
                self.log_event('trade', f"[{symbol}] ❌ 참조가격 계산 예외 발생: {e}", level='ERROR')
                import traceback
                self.log_event('trade', f"[{symbol}] 🔍 예외 상세: {traceback.format_exc()}", level='ERROR')
                # 폴백: 기본 검증
                min_notional = self.settings.get('min_trade_amount', 5.0)
                final_amount = quantity * current_price
                if final_amount < min_notional:
                    self.log_event('trade', f"[{symbol}] ❌ 폴백 검증 실패: {final_amount:.2f} USDT < {min_notional} USDT", level='ERROR')
                    self._reset_trade_flag(symbol)
                    return False

            # 🔥 포지션 진입 전 최종 검증
            self.log_event('trade', f"[{symbol}] 🔍 포지션 진입 전 최종 검증:")
            self.log_event('trade', f"[{symbol}]   - 심볼: {symbol}")
            self.log_event('trade', f"[{symbol}]   - 방향: {side}")
            self.log_event('trade', f"[{symbol}]   - 수량: {quantity}")
            self.log_event('trade', f"[{symbol}]   - 레버리지: {leverage}x")
            self.log_event('trade', f"[{symbol}]   - 거래금액: {final_amount:.2f} USDT")
            self.log_event('trade', f"[{symbol}]   - TP: {tp:.6f}")
            self.log_event('trade', f"[{symbol}]   - SL: {sl:.6f}")

            # 🔥 진입 직전 오픈오더 정리 (TP/SL 제외)
            self.log_event('trade', f"[{symbol}] 🧹 진입 직전 오픈오더 정리 시작...")
            try:
                self._cleanup_all_open_orders()
                self.log_event('trade', f"[{symbol}] ✅ 진입 직전 오픈오더 정리 완료")
            except Exception as cleanup_error:
                self.log_event('trade', f"[{symbol}] ⚠️ 오픈오더 정리 실패: {cleanup_error}", level='WARNING')

            # 🔥 주문 실행 직전 중지 신호 최종 확인
            if hasattr(self.main_app, 'trading_worker') and self.main_app.trading_worker:
                if not self.main_app.trading_worker.running:
                    self.log_event('trade', f"[{symbol}] 🚫 주문 실행 직전 중지 신호 감지 - 주문 취소")
                    self._reset_trade_flag(symbol)
                    return False

            # 시장가 진입
            self.log_event('trade', f"[{symbol}] 🚀 바이낸스 주문 실행 시작 - {side} {quantity} {symbol}")
            layer_settings = self._get_advanced_layers_settings_binance()
            order_result = self._place_entry_order_with_quality_control_binance(
                symbol=symbol,
                side=side,
                quantity=quantity,
                layer_settings=layer_settings,
                trade_params=trade_params,
            )
            try:
                self.last_order_execution_metrics[symbol] = {
                    'latency_ms': float(order_result.get('latency_ms', 0.0) or 0.0),
                    'slippage_bps': float(order_result.get('slippage_bps', 0.0) or 0.0),
                    'errors': list(order_result.get('errors', []) or []),
                }
            except Exception:
                pass

            self.log_event('trade', f"[{symbol}] 🔍 주문 결과: {order_result}")

            # 🔥 주문 결과 검증
            if not order_result:
                self.log_event('trade', f"[{symbol}] ❌ 주문 결과가 None입니다", level='ERROR')
                return False

            order_status = order_result.get('status', '').upper() if isinstance(order_result.get('status'), str) else str(order_result.get('status', '')).upper()
            
            # 🔥 주문 상태 확인 및 체결 대기
            # PENDING, NEW 상태 모두 체결 대기 대상으로 처리
            if order_status in ['NEW', 'PENDING']:
                self.log_event('trade', f"[{symbol}] ⏳ 주문 체결 대기 중... (status: {order_status}, order_id: {order_result.get('order_id')})")

                # 최대 10초 동안 체결 대기
                for attempt in range(10):
                    time.sleep(1)
                    try:
                        order_status_check = self.binance_client.client.futures_get_order(
                            symbol=symbol,
                            orderId=order_result.get('order_id')
                        )

                        if order_status_check.get('status') == 'FILLED':
                            self.log_event('trade', f"[{symbol}] ✅ 주문 체결 완료!")
                            order_result['status'] = 'FILLED'
                            order_result['avg_price'] = float(order_status_check.get('avgPrice', 0))
                            order_result['executed_qty'] = float(order_status_check.get('executedQty', 0))
                            order_status = 'FILLED'
                            break
                        elif order_status_check.get('status') in ['CANCELED', 'REJECTED', 'EXPIRED']:
                            self.log_event('trade', f"[{symbol}] ❌ 주문 취소/거부됨: {order_status_check.get('status')}", level='ERROR')
                            order_result['status'] = order_status_check.get('status')
                            order_status = order_status_check.get('status')
                            break
                    except Exception as e:
                        self.log_event('trade', f"[{symbol}] ⚠️ 주문 상태 확인 실패: {e}")

                if order_status in ['NEW', 'PENDING']:
                    self.log_event('trade', f"[{symbol}] ⚠️ 주문 체결 타임아웃 - 포지션 확인으로 진행 (status: {order_status})", level='WARNING')
                    # 타임아웃이어도 포지션이 생성되었을 수 있으므로 계속 진행

            # 🔥 주문 실패 시 검증만 수행 (보정 비활성화)
            # PENDING, NEW, FILLED 모두 성공으로 처리 (PENDING은 체결 대기 후 FILLED로 전환됨)
            if order_status not in ['NEW', 'FILLED', 'PENDING']:
                # 에러 메시지가 비어있을 때 order_result 전체를 로깅
                error_msg = str(order_result.get('error', '')) if order_result else ''
                if not error_msg and order_result:
                    error_msg = f"주문 결과: {order_result}"
                self.log_event('trade', f"[{symbol}] ❌ 주문 실패 - 에러: {error_msg}", level='ERROR')

                # MIN_NOTIONAL 에러 (-4164) 검증만 수행 (자동 재시도 비활성화)
                if 'no smaller than' in error_msg:
                    # 에러 메시지에서 필요한 최소 명목가 추출
                    match = re.search(r'no smaller than\s*([0-9.]+)', error_msg)
                    if match:
                        required_min_notional = float(match.group(1))  # 예: 20.0

                        # 현재 거래 파라미터에서 필터 정보 가져오기
                        filters = trade_params.get('filters', {})
                        current_qty = trade_params.get('qty', 0)

                        # 참조가격으로 현재 거래금액 계산
                        if 'ref_price' in locals():
                            ref_price = locals()['ref_price']
                        elif 'current_price' in locals():
                            ref_price = locals()['current_price']
                        else:
                            # 현재가를 다시 조회
                            try:
                                ref_price = self.binance_client.get_current_price(symbol)
                                self.log_event('trade', f"[{symbol}] 🔍 MIN_NOTIONAL 검증용 현재가 조회: {ref_price}")
                            except Exception as e:
                                self.log_event('trade', f"[{symbol}] ❌ 현재가 조회 실패: {e}", level='ERROR')
                                return False

                        # 🔥 검증만 수행: 현재 거래금액이 최소 노셔널 미달인지 확인
                        current_notional = current_qty * ref_price
                        if current_notional < required_min_notional:
                            self.log_event('trade', f"[{symbol}] ⚠️ MIN_NOTIONAL 미달 검증: 현재={current_notional:.2f} < 필요={required_min_notional:.2f} USDT", level='WARNING')
                            self.log_event('trade', f"[{symbol}] 💡 해결방법: Optimizer에서 수량을 {required_min_notional/ref_price:.6f} 이상으로 설정 필요", level='INFO')

                            # 🔥 Optimizer에서 이미 보정했는데도 에러가 발생한다면 다른 원인 분석
                            self.log_event('trade', f"[{symbol}] 🔍 원인 분석: Optimizer 보정 후에도 MIN_NOTIONAL 에러 발생", level='WARNING')
                            self.log_event('trade', f"[{symbol}] 🔍 가능한 원인: 1) 가격 변동 2) 거래소 정책 변경 3) Optimizer 보정 로직 문제", level='INFO')

                            # 🔥 자동 재시도 비활성화 - 검증 실패 시 거래 중단
                            self.log_event('trade', f"[{symbol}] ❌ MIN_NOTIONAL 검증 실패 - 거래 중단 (자동 재시도 비활성화)", level='ERROR')
                            return False
                        else:
                            # 🔥 현재 거래금액이 충분한데도 에러가 발생한 경우
                            self.log_event('trade', f"[{symbol}] 🔍 이상 상황: 거래금액 충분({current_notional:.2f} >= {required_min_notional:.2f})인데 MIN_NOTIONAL 에러 발생", level='WARNING')
                            self.log_event('trade', f"[{symbol}] 🔍 가능한 원인: 1) 거래소 일시적 오류 2) 다른 파라미터 문제 3) API 버전 차이", level='INFO')
                            self.log_event('trade', f"[{symbol}] ❌ 예상치 못한 MIN_NOTIONAL 에러 - 거래 중단", level='ERROR')
                            return False
                    else:
                        self.log_event('trade', f"[{symbol}] ❌ MIN_NOTIONAL 에러 메시지 파싱 실패: {error_msg}", level='ERROR')
                        return False
                else:
                    # 다른 에러의 경우 - 하지만 실제 포지션이 생성되었을 수 있으므로 확인
                    self.log_event('trade', f"[{symbol}] ❌ 주문 실패: {error_msg} - 실제 포지션 확인 중...", level='ERROR')
                    # 🔥 주문 실패로 처리되었지만 실제 포지션이 생성되었을 수 있음
                    try:
                        position_info = self._get_position_info_with_retry(symbol)
                        if position_info and abs(float(position_info.get('positionAmt', 0))) > 0:
                            self.log_event('trade', f"[{symbol}] ⚠️ 주문 실패 처리되었지만 실제 포지션 확인됨 - 포지션 복구 진행", level='WARNING')
                            # 포지션이 있으면 성공으로 처리하고 계속 진행
                            order_status = 'FILLED'  # 포지션이 있으면 성공으로 간주
                            order_result['status'] = 'FILLED'
                            actual_entry_price = float(position_info.get('entryPrice', 0))
                            if actual_entry_price > 0:
                                order_result['avg_price'] = actual_entry_price
                                order_result['executed_qty'] = abs(float(position_info.get('positionAmt', 0)))
                        else:
                            # 실제 포지션도 없으면 진짜 실패
                            return False
                    except Exception as e:
                        self.log_event('trade', f"[{symbol}] ⚠️ 포지션 확인 중 오류: {e} - 거래 실패로 처리", level='WARNING')
                        return False
            # 🔥 autotrade.py와 동일한 검증 로직 추가
            # PENDING 상태도 성공으로 처리 (체결 대기 후 FILLED로 전환됨)
            if order_status in ['NEW', 'FILLED', 'PENDING']:
                self.log_event('order', f"[{symbol}] 🔍 주문 제출 성공 (status: {order_status}) - 포지션 확인 시작")
                # 주문이 제출되었으므로 포지션 확인
                position_info = self._get_position_info_with_retry(symbol)
                self.log_event('order', f"[{symbol}] 🔍 포지션 정보: {position_info}")

                if position_info and abs(float(position_info.get('positionAmt', 0))) > 0:
                    self.log_event('order', f"[{symbol}] ✅ 진입 성공 - 포지션 확인됨 (수량: {position_info.get('positionAmt', 0)})")

                    # 실제 진입 가격 확인 (positionAmt로 검증된 포지션에서)
                    actual_entry_price = float(position_info.get('entryPrice', 0))
                    if actual_entry_price <= 0:
                        self.log_event('order', f"[{symbol}] ❌ 유효하지 않은 진입가: {actual_entry_price}", level='ERROR')
                        return False

                    # 🔥 포지션 확인 성공 후 TP/SL 설정 (백업/보험용 - 동적 임계값보다 높게)
                    # 🔥 TP/SL은 백업 역할이므로 동적 임계값보다 넓게 설정 (settings.json에서 설정 가능)
                    # 시장 변동성 및 코인 특성에 따라 동적으로 조정
                    try:
                        # settings.json에서 백업 TP/SL 설정 읽기
                        backup_cfg = self.settings.get('backup_tp_sl_settings', {})
                        if not backup_cfg:
                            self.logger.warning(f"[{symbol}] ⚠️ backup_tp_sl_settings가 없습니다. 기본값 사용")
                        
                        multipliers = backup_cfg.get('multipliers', {}) if backup_cfg else {}
                        safety_limits = backup_cfg.get('safety_limits', {}) if backup_cfg else {}
                        volatility_thresholds = backup_cfg.get('volatility_thresholds', {}) if backup_cfg else {}
                        
                        # 기본값 (폴백) - settings.json이 없거나 값이 없을 때 사용
                        high_mult = float(multipliers.get('high_volatility', 3.0)) if multipliers else 3.0
                        medium_mult = float(multipliers.get('medium_volatility', 2.5)) if multipliers else 2.5
                        low_mult = float(multipliers.get('low_volatility', 2.0)) if multipliers else 2.0
                        tp_min = float(safety_limits.get('tp_min', 0.01)) if safety_limits else 0.01
                        tp_max = float(safety_limits.get('tp_max', 0.05)) if safety_limits else 0.05
                        sl_min = float(safety_limits.get('sl_min', 0.008)) if safety_limits else 0.008
                        sl_max = float(safety_limits.get('sl_max', 0.03)) if safety_limits else 0.03
                        high_threshold = float(volatility_thresholds.get('high', 0.02)) if volatility_thresholds else 0.02
                        medium_threshold = float(volatility_thresholds.get('medium', 0.01)) if volatility_thresholds else 0.01
                        
                        # 시장 변동성 계산 (메서드가 없으면 기본값 사용)
                        try:
                            volatility = self._calculate_market_volatility(symbol)
                        except (AttributeError, Exception) as e:
                            self.logger.warning(f"[{symbol}] 변동성 계산 실패, 기본값 사용: {e}")
                            volatility = 0.01  # 기본값: 중간 변동성
                        
                        # 변동성 기반 백업 TP/SL multiplier (settings.json에서 읽음)
                        if volatility > high_threshold:  # 높은 변동성
                            backup_multiplier = high_mult
                        elif volatility > medium_threshold:  # 중간 변동성
                            backup_multiplier = medium_mult
                        else:  # 낮은 변동성
                            backup_multiplier = low_mult
                        
                        # 최근 거래 패턴 기반 추가 조정 (메서드가 없으면 기본값 사용)
                        try:
                            pattern_adjustment = self._get_pattern_based_adjustment(symbol)
                            pattern_tp_multiplier = pattern_adjustment.get('tp_multiplier', 1.0) if pattern_adjustment else 1.0
                            pattern_sl_multiplier = pattern_adjustment.get('sl_multiplier', 1.0) if pattern_adjustment else 1.0
                        except (AttributeError, Exception) as e:
                            self.logger.warning(f"[{symbol}] 패턴 기반 조정 실패, 기본값 사용: {e}")
                            pattern_tp_multiplier = 1.0
                            pattern_sl_multiplier = 1.0
                        
                        # 백업 TP/SL 계산 (동적 임계값보다 높게)
                        backup_tp = tp * backup_multiplier * pattern_tp_multiplier
                        backup_sl = sl * backup_multiplier * pattern_sl_multiplier
                        
                        # 안전 범위 제한 (settings.json에서 읽음)
                        backup_tp = max(tp_min, min(backup_tp, tp_max))
                        backup_sl = max(sl_min, min(backup_sl, sl_max))
                        
                        self.logger.info(f"[{symbol}] 🔧 백업 TP/SL 계산: 동적임계값 TP={tp:.4f}, SL={sl:.4f} → 백업 TP={backup_tp:.4f}, SL={backup_sl:.4f} (multiplier={backup_multiplier:.1f}x, 변동성={volatility:.4f}, 설정: high={high_mult}x/{high_threshold:.2%}, medium={medium_mult}x/{medium_threshold:.2%}, low={low_mult}x)")
                        
                    except Exception as e:
                        # 폴백: 기본 2배 확대
                        self.logger.warning(f"[{symbol}] 백업 TP/SL 계산 실패, 기본 2배 사용: {e}")
                        import traceback
                        self.logger.error(f"[{symbol}] 백업 TP/SL 계산 예외 상세: {traceback.format_exc()}")
                        backup_tp = tp * 2.0
                        backup_sl = sl * 2.0
                        backup_tp = max(0.01, min(backup_tp, 0.05))  # 최소 1%, 최대 5%
                        backup_sl = max(0.008, min(backup_sl, 0.03))  # 최소 0.8%, 최대 3%

                    # AI 커스텀 전략이 명시한 TP/SL은 통계적 전략의 일부다.
                    # 거래소 보험 주문도 같은 값을 사용하며 배수·클램프로 몰래 변경하지 않는다.
                    if trade_params.get('_selected_custom_strategy'):
                        backup_tp = tp
                        backup_sl = sl
                        self.logger.info(
                            f"[{symbol}] 🛡️ AI 커스텀 전략 보험 주문값 원형 유지: "
                            f"전략={trade_params.get('_selected_custom_strategy')}, "
                            f"버전={trade_params.get('_selected_custom_strategy_version_id') or '-'}, "
                            f"TP={backup_tp:.6f}, SL={backup_sl:.6f}"
                        )
                    
                    # 백업 TP/SL 가격 계산
                    if side == 'BUY':  # LONG
                        tp_price = actual_entry_price * (1 + backup_tp)
                        sl_price = actual_entry_price * (1 - backup_sl)
                    else:  # SELL (SHORT)
                        tp_price = actual_entry_price * (1 - backup_tp)
                        sl_price = actual_entry_price * (1 + backup_sl)
                    
                    # 🔥 TP/SL 가격 유효성 검증 (음수 또는 잘못된 값 방지)
                    # SHORT 포지션: TP는 entry보다 낮아야 하고, SL은 entry보다 높아야 함
                    # LONG 포지션: TP는 entry보다 높아야 하고, SL은 entry보다 낮아야 함
                    if side == 'BUY':  # LONG
                        if tp_price <= actual_entry_price:
                            self.logger.warning(f"[{symbol}] ⚠️ TP 가격이 진입가보다 낮거나 같음: TP={tp_price}, Entry={actual_entry_price}, backup_tp={backup_tp:.6f}. 기본값으로 재계산.")
                            tp_price = actual_entry_price * 1.01  # 기본 1% 수익
                        if sl_price >= actual_entry_price:
                            self.logger.warning(f"[{symbol}] ⚠️ SL 가격이 진입가보다 높거나 같음: SL={sl_price}, Entry={actual_entry_price}, backup_sl={backup_sl:.6f}. 기본값으로 재계산.")
                            sl_price = actual_entry_price * 0.99  # 기본 1% 손절
                    else:  # SELL (SHORT)
                        if tp_price >= actual_entry_price:
                            self.logger.warning(f"[{symbol}] ⚠️ TP 가격이 진입가보다 높거나 같음: TP={tp_price}, Entry={actual_entry_price}, backup_tp={backup_tp:.6f}. 기본값으로 재계산.")
                            tp_price = actual_entry_price * 0.99  # 기본 1% 수익
                        if sl_price <= actual_entry_price:
                            self.logger.warning(f"[{symbol}] ⚠️ SL 가격이 진입가보다 낮거나 같음: SL={sl_price}, Entry={actual_entry_price}, backup_sl={backup_sl:.6f}. 기본값으로 재계산.")
                            sl_price = actual_entry_price * 1.01  # 기본 1% 손절
                    
                    # 최종 검증: 가격이 0보다 큰지 확인
                    if tp_price <= 0 or sl_price <= 0:
                        self.logger.error(f"[{symbol}] ❌ TP/SL 가격이 0 이하: TP={tp_price}, SL={sl_price}, Entry={actual_entry_price}. 기본값 사용.")
                        if side == 'BUY':  # LONG
                            tp_price = actual_entry_price * 1.01
                            sl_price = actual_entry_price * 0.99
                        else:  # SELL (SHORT)
                            tp_price = actual_entry_price * 0.99
                            sl_price = actual_entry_price * 1.01

                    # 🔥 TP/SL 가격 스냅: tickSize 기반 스냅 + price_precision 포맷
                    price_prec = 2  # 기본값
                    try:
                        info = self.binance_client.get_symbol_info_direct(symbol) or {}
                        # 🔥 get_symbol_info_direct는 camelCase (pricePrecision, tickSize)를 반환하므로 둘 다 시도
                        price_prec = info.get('pricePrecision') or info.get('price_precision') or 2
                        tick_size = float(info.get('tickSize') or info.get('tick_size') or (10 ** (-int(price_prec))))
                        
                        # 🔥 저가 코인 보호: 진입가가 0.001~0.02 범위면 price_prec를 최소 4~5로 강제
                        if 0.001 <= actual_entry_price <= 0.02:
                            # 진입가에 맞는 최소 정밀도 계산 (예: 0.0067 → 최소 4자리, 0.0005 → 최소 5자리)
                            min_prec_needed = max(4, len(str(actual_entry_price).split('.')[-1].rstrip('0')))
                            if price_prec < min_prec_needed:
                                self.logger.info(f"[{symbol}] 🔧 저가 코인 감지 (entry={actual_entry_price:.8f}): price_prec {price_prec} → {min_prec_needed}로 강제 조정")
                                price_prec = min_prec_needed
                        
                        entry = actual_entry_price

                        def snap(price, is_buy):
                            return math.ceil(price / tick_size) * tick_size if is_buy else math.floor(price / tick_size) * tick_size

                        if side == 'BUY':  # LONG
                            tp_price = snap(tp_price, True)
                            sl_price = snap(sl_price, False)
                            if sl_price >= entry:
                                sl_price = math.floor((entry - tick_size) / tick_size) * tick_size
                        else:  # SHORT
                            tp_price = snap(tp_price, False)
                            sl_price = snap(sl_price, True)
                            if sl_price <= entry:
                                sl_price = math.ceil((entry + tick_size) / tick_size) * tick_size

                        tp_price = float(format(tp_price, f'.{price_prec}f'))
                        sl_price = float(format(sl_price, f'.{price_prec}f'))
                        
                        # 🔥 스냅 후 최종 검증: 가격이 0보다 큰지 확인 (저가 코인 대응)
                        if tp_price <= 0 or sl_price <= 0:
                            self.logger.error(f"[{symbol}] ❌ TP/SL 스냅 후 가격이 0 이하: TP={tp_price}, SL={sl_price}, Entry={actual_entry_price}, tick={tick_size}. 기본값으로 재계산.")
                            if side == 'BUY':  # LONG
                                tp_price = actual_entry_price * 1.01
                                sl_price = actual_entry_price * 0.99
                            else:  # SELL (SHORT)
                                tp_price = actual_entry_price * 0.99
                                sl_price = actual_entry_price * 1.01
                            # 다시 스냅 적용
                            tp_price = float(format(tp_price, f'.{price_prec}f'))
                            sl_price = float(format(sl_price, f'.{price_prec}f'))

                        self.logger.info(f"[{symbol}] TP/SL 스냅 완료: TP={tp_price} (tick={tick_size}), SL={sl_price} (tick={tick_size}), precision={price_prec}")

                    except Exception as e:
                        self.logger.warning(f"[{symbol}] 가격 스냅 실패, 기본값 사용: {e}")
                        # 🔥 예외 처리에서도 price_prec 사용 (2 고정 제거)
                        # price_prec를 다시 계산 시도 (예외 발생 전에 이미 계산했을 수 있음)
                        try:
                            info_fallback = self.binance_client.get_symbol_info_direct(symbol) or {}
                            price_prec_fallback = info_fallback.get('pricePrecision') or info_fallback.get('price_precision') or 2
                            # 저가 코인 보호
                            if 0.001 <= actual_entry_price <= 0.02:
                                min_prec_needed = max(4, len(str(actual_entry_price).split('.')[-1].rstrip('0')))
                                if price_prec_fallback < min_prec_needed:
                                    price_prec_fallback = min_prec_needed
                            price_prec = price_prec_fallback
                        except:
                            # 최종 폴백: 진입가 기반으로 최소 정밀도 계산
                            if 0.001 <= actual_entry_price <= 0.02:
                                price_prec = max(4, len(str(actual_entry_price).split('.')[-1].rstrip('0')))
                            else:
                                price_prec = 2
                        
                        tp_price = round(tp_price, price_prec)
                        sl_price = round(sl_price, price_prec)
                        
                        # 🔥 기본값 적용 후에도 0 이하 검증
                        if tp_price <= 0 or sl_price <= 0:
                            self.logger.error(f"[{symbol}] ❌ 기본값 적용 후에도 TP/SL 가격이 0 이하: TP={tp_price}, SL={sl_price}, Entry={actual_entry_price}. 강제 재계산.")
                            if side == 'BUY':  # LONG
                                tp_price = max(actual_entry_price * 1.01, 0.0001)  # 최소 0.0001
                                sl_price = max(actual_entry_price * 0.99, 0.0001)
                            else:  # SELL (SHORT)
                                tp_price = max(actual_entry_price * 0.99, 0.0001)
                                sl_price = max(actual_entry_price * 1.01, 0.0001)

                    # TP/SL 주문 설정 (보험용)
                    # 🔥 BUY/SELL을 LONG/SHORT로 변환
                    position_side = 'LONG' if side == 'BUY' else 'SHORT'

                    # TP/SL 주문 원자적 실행 (포지션 모드 자동 감지)
                    tp_sl_result = []
                    tp_order_id = None
                    sl_order_id = None

                    try:
                        # 🔥 BinanceClient.place_tp_sl_orders() 사용 (Algo Order API 대응, v3.8.9.5+)
                        # 이 메서드는 closePosition=True와 workingType을 올바르게 처리합니다
                        tp_order_result, sl_order_result = self.binance_client.place_tp_sl_orders(
                            symbol=symbol,
                            position_side=position_side,
                            take_profit=tp_price,
                            stop_loss=sl_price,
                            quantity=None,  # closePosition=True이므로 수량 불필요
                            price_precision=price_prec
                        )
                        
                        # 결과 파싱 (place_tp_sl_orders는 Dict를 반환)
                        tp_order = tp_order_result.get('order', {}) if isinstance(tp_order_result, dict) else tp_order_result
                        sl_order = sl_order_result.get('order', {}) if isinstance(sl_order_result, dict) else sl_order_result
                        
                        # orderId 추출 (Algo Order는 algoId 사용)
                        # 1. 최상위 레벨에서 order_id 확인 (Algo Order 응답)
                        tp_order_id = tp_order_result.get('order_id') if isinstance(tp_order_result, dict) else None
                        sl_order_id = sl_order_result.get('order_id') if isinstance(sl_order_result, dict) else None
                        
                        # 2. order 딕셔너리에서 orderId 또는 algoId 확인
                        if not tp_order_id and isinstance(tp_order, dict):
                            tp_order_id = tp_order.get('orderId') or tp_order.get('algoId')
                        if not sl_order_id and isinstance(sl_order, dict):
                            sl_order_id = sl_order.get('orderId') or sl_order.get('algoId')
                        
                        # 성공 여부 확인
                        if tp_order_id and sl_order_id:
                            tp_sl_result = [tp_order, sl_order]
                        else:
                            # 실패 시 None으로 설정
                            tp_sl_result = [None, None]
                            if not tp_order_id:
                                self.log_event('trade', f"[{symbol}] ❌ TP 주문 생성 실패: {tp_order_result}", level='ERROR')
                            if not sl_order_id:
                                self.log_event('trade', f"[{symbol}] ❌ SL 주문 생성 실패: {sl_order_result}", level='ERROR')

                    except Exception as e:
                        import traceback
                        self.log_event('trade', f"[{symbol}] TP/SL 주문 설정 실패: {e}", level='ERROR')
                        self.log_event('trade', f"[{symbol}] TP/SL 주문 설정 상세 오류: {traceback.format_exc()}", level='ERROR')
                        # 🔥 원자성 확보 강화: TP/SL 중 하나라도 실패하면 둘 다 취소
                        if tp_order_id:
                            try:
                                self.binance_client.client.futures_cancel_order(symbol=symbol, orderId=tp_order_id)
                                self.logger.info(f"[{symbol}] TP 주문 롤백 완료: {tp_order_id}")
                            except Exception as cancel_e:
                                self.logger.warning(f"[{symbol}] TP 주문 롤백 실패: {cancel_e}")
                        if sl_order_id:
                            try:
                                self.binance_client.client.futures_cancel_order(symbol=symbol, orderId=sl_order_id)
                                self.logger.info(f"[{symbol}] SL 주문 롤백 완료: {sl_order_id}")
                            except Exception as cancel_e:
                                self.logger.warning(f"[{symbol}] SL 주문 롤백 실패: {cancel_e}")
                        tp_sl_result = [None, None]

                    # 🔥 TP/SL 주문 생성 결과 확인
                    if tp_sl_result and tp_sl_result[0] and tp_sl_result[1]:
                        self.logger.info(f"[{symbol}] TP/SL 주문 API 호출 완료 (TP:{tp_price:.8f}, SL:{sl_price:.8f}) - 검증 대기 중...")

                        # 🔥 TP/SL 사후 검증 강화: 재시도 로직으로 개선
                        try:
                            # 재시도 로직: 최대 3회, 각 시도마다 대기 시간 증가
                            verification_passed = False
                            for verify_attempt in range(3):
                                wait_time = 2.0 + (verify_attempt * 1.0)  # 2초, 3초, 4초
                                time.sleep(wait_time)
                                
                                # 🔥 Algo Order API로 생성된 TP/SL은 별도 조회 필요
                                open_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)
                                open_algo_orders = self.binance_client.get_open_algo_orders(symbol=symbol)
                                
                                # 일반 주문에서 TP/SL 필터링
                                tp_orders = [o for o in open_orders if o.get('type') in ('TAKE_PROFIT', 'TAKE_PROFIT_MARKET')]
                                sl_orders = [o for o in open_orders if o.get('type') in ('STOP', 'STOP_MARKET')]
                                
                                # Algo Order에서 TP/SL 필터링 (orderType 필드 확인)
                                for algo_order in open_algo_orders:
                                    # 🔥 Binance Algo Order API는 'type' 대신 'orderType' 필드 사용
                                    algo_type = (algo_order.get('orderType') or algo_order.get('type', '')).upper()
                                    if algo_type in ('TAKE_PROFIT_MARKET', 'TAKE_PROFIT'):
                                        tp_orders.append(algo_order)
                                    elif algo_type in ('STOP_MARKET', 'STOP'):
                                        sl_orders.append(algo_order)
                                
                                other_orders = [o for o in open_orders if o.get('type') not in ('TAKE_PROFIT', 'TAKE_PROFIT_MARKET', 'STOP', 'STOP_MARKET')]

                                # 🔥 엄격한 검증: 정확히 1:1 + 모든 옵션 확인
                                if len(tp_orders) == 1 and len(sl_orders) == 1:
                                    # 각 주문의 상세 옵션 검증
                                    tp_order = tp_orders[0]
                                    sl_order = sl_orders[0]

                                    # 필수 옵션 검증 (Algo Order는 status가 없거나 PENDING일 수 있음)
                                    # Algo Order는 'status' 필드가 없을 수 있으므로 유연하게 처리
                                    tp_status_ok = tp_order.get('status') in ('NEW', 'PENDING') or 'status' not in tp_order
                                    sl_status_ok = sl_order.get('status') in ('NEW', 'PENDING') or 'status' not in sl_order
                                    
                                    # workingType은 Algo Order에서 다를 수 있으므로 유연하게 처리
                                    tp_working_type_ok = tp_order.get('workingType') == 'MARK_PRICE' or 'workingType' not in tp_order
                                    sl_working_type_ok = sl_order.get('workingType') == 'MARK_PRICE' or 'workingType' not in sl_order
                                    
                                    tp_valid = tp_status_ok and tp_working_type_ok
                                    sl_valid = sl_status_ok and sl_working_type_ok

                                    if tp_valid and sl_valid:
                                        self.logger.info(f"[{symbol}] ✅ TP/SL 완벽 설정 완료 - 검증 통과 (TP:{tp_price:.5f}, SL:{sl_price:.5f}) [시도 {verify_attempt+1}/3]")
                                        tp_sl_verified = True
                                        verification_passed = True
                                        break  # 검증 성공 시 루프 종료
                                    else:
                                        self.logger.warning(f"[{symbol}] ⚠️ TP/SL 옵션 검증 실패 (시도 {verify_attempt+1}/3): TP_valid={tp_valid}, SL_valid={sl_valid}")
                                else:
                                    self.logger.warning(f"[{symbol}] ⚠️ TP/SL 수량 검증 실패 (시도 {verify_attempt+1}/3): TP {len(tp_orders)}개, SL {len(sl_orders)}개 (정확히 1:1 필요)")
                            
                            # 모든 재시도 실패 시 재설정 시도
                            if not verification_passed:
                                self.logger.warning(f"[{symbol}] ⚠️ TP/SL 검증 실패 (3회 시도 후) - 재설정 시도")
                                retry_success = self._retry_tp_sl_setup(symbol, side, tp_price, sl_price, price_prec)
                                if retry_success:
                                    # 재설정 후 재검증 (1회)
                                    time.sleep(2.0)
                                    open_orders_retry = self.binance_client.client.futures_get_open_orders(symbol=symbol)
                                    open_algo_orders_retry = self.binance_client.get_open_algo_orders(symbol=symbol)
                                    
                                    tp_orders_retry = [o for o in open_orders_retry if o.get('type') in ('TAKE_PROFIT', 'TAKE_PROFIT_MARKET')]
                                    sl_orders_retry = [o for o in open_orders_retry if o.get('type') in ('STOP', 'STOP_MARKET')]
                                    
                                    # Algo Order에서도 TP/SL 추가
                                    for algo_order in open_algo_orders_retry:
                                        # 🔥 Binance Algo Order API는 'type' 대신 'orderType' 필드 사용
                                        algo_type = (algo_order.get('orderType') or algo_order.get('type', '')).upper()
                                        if algo_type in ('TAKE_PROFIT_MARKET', 'TAKE_PROFIT'):
                                            tp_orders_retry.append(algo_order)
                                        elif algo_type in ('STOP_MARKET', 'STOP'):
                                            sl_orders_retry.append(algo_order)
                                    if len(tp_orders_retry) == 1 and len(sl_orders_retry) == 1:
                                        tp_sl_verified = True
                                        self.logger.info(f"[{symbol}] ✅ TP/SL 재설정 후 검증 통과")
                                    else:
                                        self.logger.warning(f"[{symbol}] ⚠️ TP/SL 재설정 후 검증 실패: TP {len(tp_orders_retry)}개, SL {len(sl_orders_retry)}개")

                            # 기타 주문이 있으면 정리
                            if len(other_orders) > 0:
                                self.logger.warning(f"""
                                [{symbol}] ⚠️ 기타 주문 발견:
                                - TP 주문: {len(tp_orders)}개 {[o.get('stopPrice', 'N/A') for o in tp_orders]}
                                - SL 주문: {len(sl_orders)}개 {[o.get('stopPrice', 'N/A') for o in sl_orders]}
                                - 기타 주문: {len(other_orders)}개
                                """)
                                # 🚧 안전 조치: 기타 주문 존재 시 전체 취소 후 TP/SL 재설정 시도
                                try:
                                    if len(other_orders) > 0:
                                        self.logger.info(f"[{symbol}] 🔄 비정상 주문 정리 후 TP/SL 재설정 시도")
                                        # 기타 주문만 선별 취소
                                        try:
                                            open_orders2 = self.binance_client.client.futures_get_open_orders(symbol=symbol)
                                            others2 = [o for o in open_orders2 if o.get('type') not in ('TAKE_PROFIT','TAKE_PROFIT_MARKET','STOP','STOP_MARKET')]
                                            if others2:
                                                if hasattr(self.binance_client, 'cancel_orders'):
                                                    self.binance_client.cancel_orders(symbol, [o['orderId'] for o in others2])
                                                else:
                                                    self.binance_client.cancel_all_orders(symbol)
                                        except Exception:
                                            pass
                                        time.sleep(0.5)
                                        # 재설정 - 기존 TP/SL 취소 후 새로 생성
                                        self.logger.info(f"[{symbol}] 🔄 기존 TP/SL 취소 후 재설정 시작")
                                        try:
                                            # 🔥 TP/SL만 선별 취소 (다른 주문은 유지)
                                            open_orders_before = self.binance_client.client.futures_get_open_orders(symbol=symbol)
                                            tp_sl_to_cancel = [o for o in open_orders_before if o.get('type') in ('TAKE_PROFIT', 'TAKE_PROFIT_MARKET', 'STOP', 'STOP_MARKET')]
                                            
                                            if tp_sl_to_cancel:
                                                for order in tp_sl_to_cancel:
                                                    try:
                                                        self.binance_client.client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                                                        self.logger.info(f"[{symbol}] 기존 TP/SL 주문 취소: {order['orderId']} ({order.get('type')})")
                                                    except Exception as e:
                                                        self.logger.warning(f"[{symbol}] TP/SL 주문 취소 실패: {e}")
                                                time.sleep(0.5)
                                            else:
                                                self.logger.info(f"[{symbol}] 취소할 TP/SL 주문 없음")
                                        except Exception as e:
                                            self.logger.warning(f"[{symbol}] 기존 주문 취소 실패: {e}")

                                        # TP/SL 재설정 직접 실행 (BinanceClient.place_tp_sl_orders() 사용, v3.8.9.5+)
                                        tp_reset = []
                                        try:
                                                # 🔥 BinanceClient.place_tp_sl_orders() 사용 (Algo Order API 대응)
                                                tp_order_result, sl_order_result = self.binance_client.place_tp_sl_orders(
                                                    symbol=symbol,
                                                    position_side=position_side,
                                                    take_profit=tp_price,
                                                    stop_loss=sl_price,
                                                    quantity=None,  # closePosition=True이므로 수량 불필요
                                                    price_precision=price_prec
                                                )
                                                
                                                # 결과 파싱
                                                tp_order = tp_order_result.get('order', {}) if isinstance(tp_order_result, dict) else tp_order_result
                                                sl_order = sl_order_result.get('order', {}) if isinstance(sl_order_result, dict) else sl_order_result
                                                
                                                if tp_order and sl_order:
                                                    tp_reset = [tp_order, sl_order]
                                                else:
                                                    tp_reset = [None, None]
                                                    if not tp_order:
                                                        self.logger.error(f"[{symbol}] TP 재설정 실패: {tp_order_result}")
                                                    if not sl_order:
                                                        self.logger.error(f"[{symbol}] SL 재설정 실패: {sl_order_result}")
                                        except Exception as e:
                                                self.logger.error(f"[{symbol}] TP/SL 재설정 실패: {e}")
                                                import traceback
                                                self.logger.error(f"[{symbol}] TP/SL 재설정 상세 오류: {traceback.format_exc()}")
                                                tp_reset = [None, None]
                                        # 재설정 결과 확인
                                        if tp_reset and tp_reset[0] and tp_reset[1]:
                                            self.logger.info(f"[{symbol}] ✅ TP/SL 재설정 성공")
                                            tp_sl_verified = True
                                        else:
                                            self.logger.warning(f"[{symbol}] ⚠️ TP/SL 재설정 실패: {tp_reset}")
                                    else:
                                        pass
                                except Exception as e:
                                    self.logger.warning(f"[{symbol}] TP/SL 재설정 중 오류: {e}")
                                # 유지: 초기값 False에서만 갱신

                        except Exception as e:
                            self.logger.warning(f"[{symbol}] TP/SL 사후 검증 중 오류: {e}")
                            # 유지: 초기값 False에서만 갱신

                        # 🔍 모듈화 전환 준비: TpSlManager 기반의 비파괴적 상태 점검 결과를 함께 로그로 남김 (동작에는 영향 X)
                        try:
                            if getattr(self, "tp_sl_manager", None):
                                audit_ok = self.tp_sl_manager.audit_tp_sl_state(symbol=symbol)
                                self.logger.info(
                                    f"[{symbol}] [TP_SL_VERIFY] legacy_ok={bool(tp_sl_verified)}, "
                                    f"manager_audit_ok={bool(audit_ok)}"
                                )
                        except Exception as e:
                            self.logger.warning(f"[{symbol}] TP/SL audit 상태 점검 중 오류: {e}")

                        # 🔥 3단계: TP/SL 주문 생성 실패 시 실제 거래소에서 주문 조회하여 포지션 객체 동기화
                        final_tp_price = tp_price
                        final_sl_price = sl_price
                        
                        # TP/SL 주문 생성이 실패한 경우 실제 거래소에서 조회
                        if not tp_sl_verified or (not tp_sl_result or not tp_sl_result[0] or not tp_sl_result[1]):
                            try:
                                self.logger.info(f"[{symbol}] 🔍 TP/SL 주문 생성 실패 또는 검증 실패 - 실제 거래소에서 주문 조회 중...")
                                
                                # 일반 주문 조회
                                open_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)
                                # Algo Order 조회
                                open_algo_orders = self.binance_client.get_open_algo_orders(symbol=symbol)
                                
                                # TP/SL 주문 필터링
                                tp_orders_actual = [o for o in open_orders if o.get('type') in ('TAKE_PROFIT', 'TAKE_PROFIT_MARKET')]
                                sl_orders_actual = [o for o in open_orders if o.get('type') in ('STOP', 'STOP_MARKET')]
                                
                                # Algo Order에서 TP/SL 추가
                                for algo_order in open_algo_orders:
                                    # 🔥 Binance Algo Order API는 'type' 대신 'orderType' 필드 사용
                                    algo_type = (algo_order.get('orderType') or algo_order.get('type', '')).upper()
                                    if algo_type in ('TAKE_PROFIT_MARKET', 'TAKE_PROFIT'):
                                        tp_orders_actual.append(algo_order)
                                    elif algo_type in ('STOP_MARKET', 'STOP'):
                                        sl_orders_actual.append(algo_order)
                                
                                # 실제 주문에서 TP/SL 가격 추출
                                if len(tp_orders_actual) == 1:
                                    tp_order_actual = tp_orders_actual[0]
                                    actual_tp_price = tp_order_actual.get('stopPrice') or tp_order_actual.get('triggerPrice') or tp_order_actual.get('price')
                                    if actual_tp_price and float(actual_tp_price) > 0:
                                        final_tp_price = float(actual_tp_price)
                                        self.logger.info(f"[{symbol}] ✅ 실제 거래소에서 TP 주문 발견: {final_tp_price}")
                                
                                if len(sl_orders_actual) == 1:
                                    sl_order_actual = sl_orders_actual[0]
                                    actual_sl_price = sl_order_actual.get('stopPrice') or sl_order_actual.get('triggerPrice') or sl_order_actual.get('price')
                                    if actual_sl_price and float(actual_sl_price) > 0:
                                        final_sl_price = float(actual_sl_price)
                                        self.logger.info(f"[{symbol}] ✅ 실제 거래소에서 SL 주문 발견: {final_sl_price}")
                                
                                # TP/SL 중 하나라도 발견되면 성공으로 표시
                                if len(tp_orders_actual) == 1 and len(sl_orders_actual) == 1:
                                    self.logger.info(f"[{symbol}] ✅ 실제 거래소에서 TP/SL 주문 모두 발견 - 포지션 객체 동기화 완료")
                            except Exception as sync_e:
                                self.logger.warning(f"[{symbol}] ⚠️ 실제 거래소 주문 조회 중 오류 (계속 진행): {sync_e}")

                        # 🔥 포지션 정보 저장 (TP/SL은 보조 장치, 실패해도 거래 진행)
                        # 원래 설계: TP/SL은 보험 기능, 실시간 모니터링이 주 역할
                        # watchdog가 주기적으로 TP/SL 재설정 시도
                        entry_order_id = order_result.get('order_id') if isinstance(order_result, dict) else None
                        position = Position(
                            symbol=symbol,
                            side=PositionSide.LONG if side == 'BUY' else PositionSide.SHORT,  # 🔥 BUY/SELL에 맞춤
                            entry_price=actual_entry_price,
                            current_price=actual_entry_price,
                            quantity=quantity,
                            leverage=leverage,
                            unrealized_pnl=0.0,
                            unrealized_pnl_percent=0.0,
                            entry_time=utc_now(),
                            tp_price=final_tp_price,  # 🔥 실제 거래소에서 조회한 값 또는 계산된 값
                            sl_price=final_sl_price,  # 🔥 실제 거래소에서 조회한 값 또는 계산된 값
                            position_id=None,
                            entry_order_id=str(entry_order_id or '') or None,
                            execution_mode=str(mode or 'live'),
                            position_owner=NOAH_POSITION_OWNER,
                            custom_strategy_id=trade_params.get('_selected_custom_strategy_id'),
                            custom_strategy_name=trade_params.get('_selected_custom_strategy'),
                            custom_strategy_rules=dict(trade_params.get('_custom_strategy_rules') or {}),
                            exit_policy=record_insurance_submission(
                                trade_params.get('_exit_policy'),
                                submitted_tp_price=final_tp_price,
                                submitted_sl_price=final_sl_price,
                                status=(
                                    'verified_on_exchange'
                                    if tp_sl_verified
                                    else 'submitted_unverified_watchdog_active'
                                ),
                                order_ids={
                                    'tp': tp_order_id,
                                    'sl': sl_order_id,
                                },
                            ),
                        )

                        self.active_positions[symbol] = position
                        self.log_event(
                            'trade',
                            f"[{symbol}] {format_exit_policy(position.exit_policy)}",
                            exchange='binance',
                            level='INFO' if tp_sl_verified else 'WARNING',
                        )
                        _, position.position_id = emit_position_opened(
                            asset_class='crypto',
                            venue='binance',
                            symbol=symbol,
                            side=position.side.value,
                            opened_at=position.entry_time,
                            entry_price=position.entry_price,
                            quantity=position.quantity,
                            position_id=position.position_id,
                            entry_order_id=entry_order_id,
                            execution_mode=str(mode or 'live'),
                            source='noahai_client_trader_position',
                            extra={'leverage': int(leverage or 1)},
                        )

                        # 🔥 거래 로그 저장 (포지션 생성 직후, TP/SL 성공 여부와 무관하게 저장)
                        # 포지션이 생성되었으면 거래 로그는 반드시 저장되어야 함
                        # 동기화된 TP/SL 가격 사용 (실제 거래소에서 조회한 값 또는 계산된 값)
                        try:
                            entry_fee, entry_fee_asset, entry_fee_source = self._get_order_commission(
                                symbol, entry_order_id
                            )
                            self._record_binance_execution(
                                symbol,
                                side,
                                order_result,
                                source='noahai_entry_order',
                                fallback_quantity=position.quantity,
                                fallback_price=actual_entry_price,
                                fee=entry_fee,
                                fee_asset=entry_fee_asset,
                            )
                            self._log_trade_entry(
                                symbol,
                                side,
                                actual_entry_price,
                                final_tp_price,
                                final_sl_price,
                                leverage,
                                mode,
                                manual=False,
                                order_id=entry_order_id,
                                fees=entry_fee,
                                fee_asset=entry_fee_asset,
                                fee_source=entry_fee_source,
                                model_version=str(trade_params.get('model_version', '') or 'local'),
                                strategy_variant=str(trade_params.get('strategy_variant', 'unknown') or 'unknown'),
                            )
                            self.log_event('trade', f"[{symbol}] ✅ 거래 로그 DB 저장 완료 (TP:{final_tp_price:.6f}, SL:{final_sl_price:.6f})")
                        except Exception as e:
                            self.log_event('trade', f"[{symbol}] ❌ 거래 로그 저장 실패: {e}", level='ERROR')
                            import traceback
                            self.log_event('trade', f"[{symbol}] ❌ 거래 로그 저장 상세 오류: {traceback.format_exc()}", level='ERROR')

                        # 🔥 TP/SL 설정 결과 로깅
                        if tp_sl_verified:
                            self.log_event('trade', f"[{symbol}] ✅ TP/SL 설정 완료 - 모니터링 시작")
                        else:
                            # 🔥 TP/SL 검증 실패 시 경고만 (포지션 유지, watchdog가 재시도)
                            self.log_event('trade', f"[{symbol}] ⚠️ TP/SL 검증 실패 - 재시도 완료 후에도 실패 (모니터링 계속)", level='WARNING')
                            # 원래 설계: TP/SL은 보조 장치, 실시간 모니터링이 주 역할
                            # watchdog가 주기적으로 TP/SL을 재설정 시도하므로 포지션 유지

                        # 🔄 실시간 모니터링 자동 시작 (헬퍼 함수 사용)
                        self.log_event('monitor', f"[{symbol}] 🔍 모니터링 시작 호출 - position: {position.symbol if position else 'None'}")
                        try:
                            self._start_monitoring(symbol, position, manual=False)
                            self.log_event('monitor', f"[{symbol}] ✅ 모니터링 시작 호출 성공")
                        except Exception as e:
                            self.log_event('monitor', f"[{symbol}] ❌ 모니터링 시작 호출 실패: {e}", level='ERROR')
                            import traceback
                            self.log_event('monitor', f"[{symbol}] ❌ 모니터링 시작 상세 오류: {traceback.format_exc()}", level='ERROR')

                        # 🔥 집중모드 유지: 모니터링 종료 시점에 플래그 해제
                        # self._reset_trade_flag(symbol)  # 모니터링 종료 시점으로 이동

                        # 거래 완료 후 대시보드 업데이트
                        if self.dashboard:
                            try:
                                # 잔고 업데이트
                                if hasattr(self.dashboard, 'update_balance_on_trade_completion'):
                                    self.dashboard.update_balance_on_trade_completion()

                                # 상태정보 업데이트 (포지션 진입)
                                if hasattr(self.dashboard, 'update_status_display'):
                                    self.dashboard.update_status_display(force_refresh=True)

                            except Exception as e:
                                self.logger.warning(f"대시보드 업데이트 실패: {e}")

                        # 🔥 TP/SL 검증 결과 확인 (로그는 이미 위에서 출력됨)
                        if tp_sl_verified:

                            # 🔥 실제 주문 존재 확인 및 내부 상태 동기화
                            try:
                                time.sleep(0.5)  # 주문 처리 대기
                                open_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)
                                tp_orders = [o for o in open_orders if o.get('type') in ('TAKE_PROFIT', 'TAKE_PROFIT_MARKET')]
                                sl_orders = [o for o in open_orders if o.get('type') in ('STOP', 'STOP_MARKET')]

                                if tp_orders and sl_orders:
                                    position.tp_price = float(tp_orders[0]['stopPrice'])
                                    position.sl_price = float(sl_orders[0]['stopPrice'])
                                    self.log_event('monitor', f"[{symbol}] ✅ TP/SL 실제 주문 확인: TP={position.tp_price:.5f}, SL={position.sl_price:.5f}")

                                    # 대시보드 강제 리프레시
                                    if hasattr(self.dashboard, 'update_status_display'):
                                        self.dashboard.update_status_display(force_refresh=True)
                                else:
                                    self.log_event('monitor', f"[{symbol}] ⚠️ TP/SL 주문이 실제로 생성되지 않음", level='WARNING')
                            except Exception as e:
                                self.log_event('monitor', f"[{symbol}] ⚠️ TP/SL 주문 확인 중 오류: {e}", level='WARNING')
                        else:
                            self.log_event('monitor', f"[{symbol}] ⚠️ TP/SL 검증 실패했지만 모니터링 시작", level='WARNING')

                        # 🔥 거래 성공 시 WebSocket 구독 보장
                        self._ensure_ws_subscriptions(symbol)

                        # 🔥 모니터링 시작 후 플래그 해제 (모니터링이 정상 시작되면 해제)
                        self._reset_trade_flag(symbol)  # 모니터링 시작 후 플래그 해제

                        return True  # 🔥 모든 과정이 성공해야 True 반환

                    else:
                        # 🔥 TP/SL 주문 생성 실패 시 재시도 (최대 3회)
                        self.log_event('trade', f"[{symbol}] ❌ TP/SL 주문 생성 실패 - 재시도 시작", level='ERROR')
                        
                        # 재시도 로직: 최대 3회 시도
                        retry_success = False
                        for retry_attempt in range(3):
                            wait_time = 1.0 + (retry_attempt * 0.5)  # 1초, 1.5초, 2초
                            time.sleep(wait_time)
                            
                            try:
                                retry_success = self._retry_tp_sl_setup(symbol, side, tp_price, sl_price, price_prec)
                                if retry_success:
                                    self.log_event('trade', f"[{symbol}] ✅ TP/SL 재시도 성공 (시도 {retry_attempt+1}/3)", level='INFO')
                                    tp_sl_result = [True, True]  # 재시도 성공으로 표시
                                    break
                                else:
                                    self.log_event('trade', f"[{symbol}] ⚠️ TP/SL 재시도 실패 (시도 {retry_attempt+1}/3)", level='WARNING')
                            except Exception as retry_e:
                                self.log_event('trade', f"[{symbol}] ⚠️ TP/SL 재시도 중 오류 (시도 {retry_attempt+1}/3): {retry_e}", level='WARNING')
                        
                        if not retry_success:
                            # 🔥 모든 재시도 실패 시에도 포지션 유지 (watchdog가 계속 재시도)
                            # 원래 설계: TP/SL은 보조 장치, 실시간 모니터링이 주 역할
                            self.log_event('trade', f"[{symbol}] ⚠️ TP/SL 재시도 모두 실패 - 모니터링 계속 (watchdog가 재시도)", level='WARNING')
                            # 즉시 청산 제거: watchdog가 주기적으로 재시도하므로 포지션 유지
                            # 거래는 계속 진행 (TP/SL 없이 모니터링)
                            tp_sl_result = [None, None]  # 실패로 표시하지만 거래는 계속

                else:
                    # 🔥 포지션 생성 실패 시 상세 로그
                    if position_info:
                        position_amt = position_info.get('positionAmt', 0)
                        self.logger.error(f"[{symbol}] ❌ 포지션 생성 실패 - positionAmt: {position_amt}")
                    else:
                        self.logger.error(f"[{symbol}] ❌ 포지션 정보 조회 실패")
                    return False
            else:
                self.logger.error(f"[{symbol}] ❌ 진입 주문 실패: {order_result}")
                # 🔥 주문 실패 시 플래그 해제 (헬퍼 함수 사용)
                try:
                    self._reset_trade_flag(trade_params.get('symbol', ''))
                except Exception:
                    pass
                return False

        except Exception as e:
            self.log_event('trade', f"[{symbol}] ❌ 거래 실행 중 오류: {e}", level='ERROR')
            # 🔥 오류 발생 시 플래그 해제 (헬퍼 함수 사용)
            try:
                self._reset_trade_flag(trade_params.get('symbol', ''))
            except Exception:
                pass
            return False

    def check_and_cleanup_orders(self, symbol: str) -> bool:
        """주문 정리 및 정리 (autotrade.py와 동일한 로직)"""
        try:
            self.logger.info(f"[{symbol}] 주문 정리 시작")
            max_attempts = 3
            wait_time = 1.0

            for attempt in range(max_attempts):
                position_info = self.binance_client.get_position_info(symbol)
                if position_info is None:
                    self.logger.error(f"[{symbol}] 포지션 정보 조회 실패")
                    return False

                position_amt = abs(float(position_info.get('positionAmt', 0)))
                open_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)

                # 포지션이 없는 경우의 처리
                if position_amt == 0:
                    if not open_orders:
                        self.logger.info(f"[{symbol}] 정상 상태: 포지션 없음, 미체결 주문 없음")
                        return True

                    self.logger.warning(f"""
                    [{symbol}] 비정상 상태 감지 (시도 {attempt + 1}/{max_attempts}):
                    - 포지션: 없음
                    - 미체결 주문: {len(open_orders)}개
                    주문 상세:
                    {[(order['orderId'], order['type'], order['side'], order.get('stopPrice', 'N/A')) for order in open_orders]}
                    """)

                    # 비정상 상태: 전체 취소 대신 TP/SL 외 주문 선별 취소 시도
                    try:
                        others_wd = [o for o in open_orders if o.get('type') not in ('TAKE_PROFIT','TAKE_PROFIT_MARKET','STOP','STOP_MARKET')]
                        if others_wd:
                            if hasattr(self.binance_client, 'cancel_orders'):
                                self.binance_client.cancel_orders(symbol, [o['orderId'] for o in others_wd])
                            else:
                                self.binance_client.cancel_all_orders(symbol)
                    except Exception:
                        pass
                    self.logger.info(f"[{symbol}] 비정상 주문 취소 처리 완료")
                    time.sleep(wait_time)
                    remaining_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)
                    if not remaining_orders:
                        self.logger.info(f"[{symbol}] 주문 정리 성공")
                        return True

                    if attempt == max_attempts - 1:
                        self.logger.error(f"[{symbol}] 최대 시도 횟수 초과 - {len(remaining_orders)}개 주문 잔존")
                        return False
                    else:
                        self.logger.error(f"[{symbol}] 전체 주문 취소 실패")
                        if attempt == max_attempts - 1:
                            return False

                    time.sleep(wait_time)
                    continue

                # 포지션이 있는 경우
                else:
                    if open_orders:
                        tp_orders = [o for o in open_orders if o['type'] == 'TAKE_PROFIT_MARKET']
                        sl_orders = [o for o in open_orders if o['type'] == 'STOP_MARKET']
                        other_orders = [o for o in open_orders if o['type'] not in ['TAKE_PROFIT_MARKET', 'STOP_MARKET']]

                        if len(tp_orders) > 1 or len(sl_orders) > 1 or other_orders:
                            self.logger.warning(f"""
                            [{symbol}] 비정상 TP/SL 상태:
                            - 포지션: {position_amt}
                            - TP 주문: {len(tp_orders)}개 {[o['stopPrice'] for o in tp_orders]}
                            - SL 주문: {len(sl_orders)}개 {[o['stopPrice'] for o in sl_orders]}
                            - 기타 주문: {len(other_orders)}개
                            """)

                            try:
                                others_wd2 = [o for o in open_orders if o.get('type') not in ('TAKE_PROFIT','TAKE_PROFIT_MARKET','STOP','STOP_MARKET')]
                                if others_wd2:
                                    if hasattr(self.binance_client, 'cancel_orders'):
                                        self.binance_client.cancel_orders(symbol, [o['orderId'] for o in others_wd2])
                                    else:
                                        self.binance_client.cancel_all_orders(symbol)
                            except Exception:
                                pass
                            self.logger.info(f"[{symbol}] 비정상 주문 취소 성공")
                            time.sleep(wait_time)
                            # TP/SL 재설정 시도 (기본값 사용)
                            try:
                                entry_price = float(position_info.get('entryPrice', 0))
                                if entry_price > 0:
                                    # 기본 TP/SL 설정 (0.18%, 0.20%)
                                    tp_price = entry_price * 1.0018 if position_amt > 0 else entry_price * 0.9982
                                    sl_price = entry_price * 0.9980 if position_amt > 0 else entry_price * 1.0020

                                    # tickSize 스냅 적용
                                    try:
                                        info2 = self.binance_client.get_symbol_info_direct(symbol) or {}
                                        price_prec2 = int(info2.get('price_precision', 2))
                                        tick_size2 = float(info2.get('tick_size', 10 ** (-price_prec2)))
                                        if position_amt > 0:  # LONG
                                            tp_price = math.ceil(tp_price / tick_size2) * tick_size2
                                            sl_price = math.floor(sl_price / tick_size2) * tick_size2
                                        else:  # SHORT
                                            tp_price = math.floor(tp_price / tick_size2) * tick_size2
                                            sl_price = math.ceil(sl_price / tick_size2) * tick_size2
                                        tp_price = float(format(tp_price, f'.{price_prec2}f'))
                                        sl_price = float(format(sl_price, f'.{price_prec2}f'))
                                    except Exception:
                                        # 실패 시 기존 값 유지
                                        pass

                                        # TP/SL 주문 재설정 (BinanceClient.place_tp_sl_orders() 사용, v3.8.9.5+)
                                        tp_result = []
                                        try:
                                            pos_side = 'LONG' if position_amt > 0 else 'SHORT'
                                            info = self.binance_client.get_symbol_info_direct(symbol) or {}
                                            # 🔥 get_symbol_info_direct는 camelCase (pricePrecision)를 반환하므로 둘 다 시도
                                            price_prec = int(info.get('pricePrecision') or info.get('price_precision') or 2)
                                            # 저가 코인 보호 (tp_price가 있으면 사용, 없으면 기본값)
                                            if tp_price and 0.001 <= tp_price <= 0.02:
                                                min_prec_needed = max(4, len(str(tp_price).split('.')[-1].rstrip('0')))
                                                if price_prec < min_prec_needed:
                                                    price_prec = min_prec_needed
                                            
                                            # 🔥 BinanceClient.place_tp_sl_orders() 사용 (Algo Order API 대응)
                                            tp_order_result, sl_order_result = self.binance_client.place_tp_sl_orders(
                                                symbol=symbol,
                                                position_side=pos_side,
                                                take_profit=tp_price,
                                                stop_loss=sl_price,
                                                quantity=None,  # closePosition=True이므로 수량 불필요
                                                price_precision=price_prec
                                            )
                                            
                                            # 결과 파싱
                                            tp_order = tp_order_result.get('order', {}) if isinstance(tp_order_result, dict) else tp_order_result
                                            sl_order = sl_order_result.get('order', {}) if isinstance(sl_order_result, dict) else sl_order_result
                                            
                                            if tp_order and sl_order:
                                                tp_result = [tp_order, sl_order]
                                            else:
                                                tp_result = [None, None]
                                                if not tp_order:
                                                    self.logger.error(f"[{symbol}] TP 재설정 실패: {tp_order_result}")
                                                if not sl_order:
                                                    self.logger.error(f"[{symbol}] SL 재설정 실패: {sl_order_result}")
                                        except Exception as e:
                                            self.logger.error(f"[{symbol}] TP/SL 재설정 실패: {e}")
                                            import traceback
                                            self.logger.error(f"[{symbol}] TP/SL 재설정 상세 오류: {traceback.format_exc()}")
                                            tp_result = [None, None]
                                        if tp_result and tp_result[0] and tp_result[1]:
                                            self.logger.info(f"[{symbol}] TP/SL 재설정 완료")
                                        else:
                                            self.logger.error(f"[{symbol}] TP/SL 재설정 실패")
                            except Exception as e:
                                self.logger.error(f"[{symbol}] TP/SL 재설정 실패: {str(e)}")
                                if attempt == max_attempts - 1:
                                    return False
                        else:
                                self.logger.error(f"[{symbol}] 비정상 주문 취소 실패")
                                if attempt == max_attempts - 1:
                                    return False
                                continue

                # 최종 확인 로직
                if attempt == max_attempts - 1:
                    final_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)

                    self.logger.info(f"""
                    [{symbol}] 최종 상태 확인:
                    - 포지션 수량: {position_amt}
                    - 미체결 주문 수: {len(final_orders)}
                    - 주문 상세: {[(o['type'], o['side'], o.get('stopPrice', 'N/A')) for o in final_orders]}
                    """)

                    if position_amt == 0:
                        if final_orders:
                            self.logger.error(f"[{symbol}] 최종 확인 실패 - 포지션 없는데 {len(final_orders)}개 주문 잔존")
                            return False
                    else:
                        tp_orders = [o for o in final_orders if o['type'] == 'TAKE_PROFIT_MARKET']
                        sl_orders = [o for o in final_orders if o['type'] == 'STOP_MARKET']
                        other_orders = [o for o in final_orders if o['type'] not in ['TAKE_PROFIT_MARKET', 'STOP_MARKET']]

                        if len(tp_orders) != 1 or len(sl_orders) != 1 or other_orders:
                            self.logger.error(f"""
                            [{symbol}] 최종 확인 실패 - 비정상 TP/SL 상태:
                            - TP 주문: {len(tp_orders)}개 {[o['stopPrice'] for o in tp_orders]}
                            - SL 주문: {len(sl_orders)}개 {[o['stopPrice'] for o in sl_orders]}
                            - 기타 주문: {len(other_orders)}개
                            """)
                            return False

                return True

        except Exception as e:
            self.logger.error(f"[{symbol}] 주문 정리 중 오류: {str(e)}")
            return False

        # 안전 폴백: 모든 경로에서 bool 반환 보장
        return True

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Backward-compat: 일부 외부 코드가 기대하는 이름을 지원 (main.py 호환용)"""
        try:
            data = self.get_active_positions()  # dict or something else
            if isinstance(data, dict):
                # Position 객체에 to_dict가 있으면 병합, 없으면 심볼만
                out = []
                for sym, pos in data.items():
                    row = {'symbol': sym}
                    try:
                        row.update(asdict(pos))
                    except Exception:
                        pass
                    out.append(row)
                return out
            return data if isinstance(data, list) else []
        except AttributeError:
            self.logger.warning("get_active_positions 메서드가 없어 폴백 방식 사용")
            return self._get_open_positions_fallback()

    def _get_open_positions_fallback(self) -> List[Dict[str, Any]]:
        """폴백 방식으로 포지션 목록 조회"""
        try:
            open_positions = []

            # 모든 심볼에 대해 포지션 확인
            symbols = getattr(self, 'trading_symbols', []) or []
            for symbol in symbols:
                try:
                    position_info = self._get_position_info_with_retry(symbol)
                    if position_info and abs(float(position_info.get('positionAmt', 0))) > 0:
                        # 포지션 정보 정리
                        position_data = {
                            'symbol': symbol,
                            'side': 'LONG' if float(position_info.get('positionAmt', 0)) > 0 else 'SHORT',
                            'size': abs(float(position_info.get('positionAmt', 0))),
                            'entry_price': float(position_info.get('entryPrice', 0)),
                            'current_price': float(position_info.get('markPrice', 0)),
                            'unrealized_pnl': float(position_info.get('unRealizedProfit', 0)),
                            'leverage': int(position_info.get('leverage', 1)),
                            'margin_type': position_info.get('marginType', 'isolated'),
                            'notional': float(position_info.get('notional', 0))
                        }
                        open_positions.append(position_data)

                except Exception as e:
                    self.logger.warning(f"[{symbol}] 포지션 정보 조회 실패: {e}")
                    continue

            self.logger.info(f"폴백 방식으로 열린 포지션 조회 완료: {len(open_positions)}개")
            return open_positions

        except Exception as e:
            self.logger.error(f"폴백 방식 포지션 목록 조회 중 오류: {e}")
            return []

    def monitor_positions(self):
        """포지션 모니터링"""
        try:
            for symbol, position in list(self.active_positions.items()):
                # 현재가 업데이트
                current_price = self.binance_client.get_current_price(symbol)
                position.current_price = current_price

                # 수익률 계산
                self.calculate_pnl(position)

                # 청산 조건 확인
                if self.should_close_position(position):
                    self.close_position(position, "자동청산")

        except Exception as e:
            self.logger.error(f"포지션 모니터링 중 오류: {e}")

    def calculate_pnl(self, position: Position):
        """수익률 계산"""
        try:
            # 🔥 안전성 검사 추가
            if not position.entry_price or position.entry_price <= 0:
                self.logger.warning(f"{position.symbol} 진입가가 유효하지 않음: {position.entry_price}")
                return

            if not position.current_price or position.current_price <= 0:
                self.logger.warning(f"{position.symbol} 현재가가 유효하지 않음: {position.current_price}")
                return

            if position.side == PositionSide.LONG:
                pnl_percent = ((position.current_price - position.entry_price) / position.entry_price) * 100
            else:  # SHORT
                pnl_percent = ((position.entry_price - position.current_price) / position.entry_price) * 100

            position.unrealized_pnl_percent = pnl_percent
            position.unrealized_pnl = (pnl_percent / 100) * position.quantity * position.entry_price * position.leverage

        except Exception as e:
            self.logger.error(f"수익률 계산 중 오류: {e}")
            # 🔥 오류 발생 시 기본값 설정
            position.unrealized_pnl_percent = 0.0
            position.unrealized_pnl = 0.0

    def _custom_strategy_exit_triggered(self, position: Position) -> bool:
        """진입 때 선택된 커스텀 버전의 명시적 청산 조건을 같은 지표 계약으로 평가한다."""
        rules = dict(getattr(position, "custom_strategy_rules", {}) or {})
        exit_spec = dict(rules.get("executable_exit", {}) or {})
        if not (exit_spec.get("all") or exit_spec.get("any")):
            return False
        try:
            from .custom_strategy_validator import (
                build_indicator_context,
                enrich_advanced_indicator_context,
            )
            from .declarative_strategy_engine import DeclarativeStrategyEngine
            market_data = self.analyzer.get_market_data(position.symbol) if self.analyzer else None
            rows = [
                {
                    "timestamp": item.timestamp,
                    "open": item.open,
                    "high": item.high,
                    "low": item.low,
                    "close": item.close,
                    "volume": item.volume,
                }
                for item in (market_data or [])
            ]
            context = build_indicator_context(rows, signal=position.side.value)
            context.update({
                "current_price": position.current_price,
                "price": position.current_price,
                "close": position.current_price,
                "signal": position.side.value,
            })
            context = enrich_advanced_indicator_context(
                context,
                rules,
                lambda timeframe, limit: self.binance_client.get_klines(
                    position.symbol, timeframe, limit
                ),
            )
            result = DeclarativeStrategyEngine.evaluate_exit(rules, context)
            if result.get("allowed", False):
                self.log_event(
                    "monitor",
                    f"[{position.symbol}] AI 커스텀 명시 청산 조건 충족: "
                    f"{position.custom_strategy_name or position.custom_strategy_id or '사용자 전략'}",
                )
                return True
        except Exception as exc:
            self.logger.warning(f"{position.symbol} AI 커스텀 청산 조건 평가 실패(기존 TP/SL 유지): {exc}")
        return False

    def should_close_position(self, position: Position) -> bool:
        """AI 모니터링 중심 포지션 청산 여부 판단"""
        try:
            # 명시적 사용자 청산은 포지션 축소 동작이므로 진입 가드레일을 우회하지 않는다.
            if self._custom_strategy_exit_triggered(position):
                return True

            # 🔥 1. AI 모니터링 중심 청산 판단 (주력)
            ai_exit_decision = self._get_ai_exit_decision(position)
            if ai_exit_decision.get('should_exit', False):
                reason = ai_exit_decision.get('reason', 'AI 분석 기반 청산')
                confidence = ai_exit_decision.get('confidence', 0.0)
                self.logger.info(f"{position.symbol} AI 모니터링 청산: {reason} (신뢰도: {confidence:.2f})")
                try:
                    self._log_trade_event('exit', f"{position.symbol} AI 모니터링 청산: {reason} (신뢰도: {confidence:.2f})")
                except Exception:
                    pass
                return True

            # 🔥 2. 동적 임계값 기반 실시간 모니터링 청산
            current_pnl_percent = position.unrealized_pnl_percent
            net_pnl_percent = self._net_pnl_percent(current_pnl_percent, position.leverage)
            advanced_plan = dict(
                (getattr(position, 'custom_strategy_rules', {}) or {}).get('advanced_order_plan') or {}
            )
            partial_plan_active = bool(advanced_plan.get('partial_take_profits'))

            # 동적 임계값 계산 (시장 변동성 기반)
            dynamic_thresholds = self._calculate_dynamic_thresholds(position.symbol)

            # 수익 청산 (동적 임계값) - 소수 단위로 통일
            profit_threshold_percent = dynamic_thresholds['profit_threshold'] * 100  # 소수를 퍼센트로 변환
            if not partial_plan_active and net_pnl_percent >= profit_threshold_percent:
                self.logger.info(f"{position.symbol} 동적 수익 청산: {net_pnl_percent:.4f}% >= {profit_threshold_percent:.4f}%")
                try:
                    self._log_trade_event('exit', f"{position.symbol} 동적 수익 청산: {net_pnl_percent:.4f}% >= {profit_threshold_percent:.4f}%")
                except Exception:
                    pass
                return True

            # 손실 청산 (동적 임계값) - 소수 단위로 통일
            loss_threshold_percent = dynamic_thresholds['loss_threshold'] * 100  # 소수를 퍼센트로 변환
            if net_pnl_percent <= -loss_threshold_percent:  # 손실은 음수로 비교
                self.logger.info(f"{position.symbol} 동적 손실 청산: {net_pnl_percent:.4f}% <= -{loss_threshold_percent:.4f}%")
                try:
                    self._log_trade_event('exit', f"{position.symbol} 동적 손실 청산: {net_pnl_percent:.4f}% <= -{loss_threshold_percent:.4f}%")
                except Exception:
                    pass
                return True

            # 🔥 3. TP/SL 안전장치 (최후의 보호막)
            if position.tp_price and not partial_plan_active:
                if position.side == PositionSide.LONG:
                    if position.current_price >= position.tp_price:
                        self.logger.info(f"{position.symbol} TP 안전장치 발동: {position.current_price} >= {position.tp_price}")
                        try:
                            self._log_trade_event('exit', f"{position.symbol} TP 안전장치 발동: {position.current_price} >= {position.tp_price}")
                        except Exception:
                            pass
                        return True
                else:  # SHORT
                    if position.current_price <= position.tp_price:
                        self.logger.info(f"{position.symbol} TP 안전장치 발동: {position.current_price} <= {position.tp_price}")
                        try:
                            self._log_trade_event('exit', f"{position.symbol} TP 안전장치 발동: {position.current_price} <= {position.tp_price}")
                        except Exception:
                            pass
                        return True

            if position.sl_price:
                if position.side == PositionSide.LONG:
                    if position.current_price <= position.sl_price:
                        self.logger.info(f"{position.symbol} SL 안전장치 발동: {position.current_price} <= {position.sl_price}")
                        try:
                            self._log_trade_event('exit', f"{position.symbol} SL 안전장치 발동: {position.current_price} <= {position.sl_price}")
                        except Exception:
                            pass
                        return True
                else:  # SHORT
                    if position.current_price >= position.sl_price:
                        self.logger.info(f"{position.symbol} SL 안전장치 발동: {position.current_price} >= {position.sl_price}")
                        try:
                            self._log_trade_event('exit', f"{position.symbol} SL 안전장치 발동: {position.current_price} >= {position.sl_price}")
                        except Exception:
                            pass
                        return True

            return False

        except Exception as e:
            self.logger.error(f"포지션 청산 판단 중 오류: {e}")
            return False

    def _advanced_order_plan_decision(self, position: Position) -> Dict[str, Any]:
        rules = dict(getattr(position, 'custom_strategy_rules', {}) or {})
        plan = dict(rules.get('advanced_order_plan') or {})
        if not plan:
            return {'action': 'hold', 'reason': 'advanced_order_plan_not_set'}
        decision = evaluate_order_plan(
            plan,
            getattr(position, 'custom_order_plan_state', {}) or None,
            pnl_percent=self._net_pnl_percent(
                float(position.unrealized_pnl_percent or 0.0), int(position.leverage or 1),
            ),
            current_quantity=float(position.quantity or 0.0),
        )
        position.custom_order_plan_state = dict(decision.get('next_state') or {})
        return decision

    def _execute_advanced_partial_close_binance(
        self, position: Position, decision: Dict[str, Any],
    ) -> bool:
        quantity = min(
            float(position.quantity or 0.0), float(decision.get('quantity', 0.0) or 0.0),
        )
        if quantity <= 0:
            return False
        side = 'SELL' if position.side == PositionSide.LONG else 'BUY'
        try:
            result = self.binance_client.place_futures_order(
                symbol=position.symbol, side=side, order_type='MARKET',
                quantity=quantity, reduce_only=True,
            ) or {}
            status = str(result.get('status') or '').upper()
            order_id = result.get('order_id') or result.get('orderId') or result.get('id')
            executed = float(result.get('executed_qty', result.get('executedQty', 0.0)) or 0.0)
            if status in {'NEW', 'PENDING', 'PARTIALLY_FILLED'} and order_id:
                try:
                    receipt = self.binance_client.client.futures_get_order(
                        symbol=position.symbol, orderId=order_id,
                    ) or {}
                    status = str(receipt.get('status') or status).upper()
                    executed = float(receipt.get('executedQty', executed) or executed)
                    result.update(receipt)
                except Exception as exc:
                    self.log_event(
                        'trade', f"[{position.symbol}] 부분청산 주문 확인 보류: {exc}",
                        level='WARNING',
                    )
            confirmed = status == 'FILLED' or (
                status == 'PARTIALLY_FILLED' and executed > 0
            )
            if not confirmed:
                self.log_event(
                    'trade', f"[{position.symbol}] 부분청산 체결 미확정: {status}",
                    level='WARNING',
                )
                return False
            closed_quantity = min(quantity, executed if executed > 0 else quantity)
            self._record_binance_execution(
                position.symbol, side, result,
                source='noahai_custom_partial_exit',
                fallback_quantity=closed_quantity,
                fallback_price=float(position.current_price or 0.0),
            )
            remaining = max(0.0, float(position.quantity) - closed_quantity)
            position.quantity = remaining
            position.custom_order_plan_state = confirm_order_plan_action(
                decision, remaining_quantity=remaining,
            )
            self.log_event(
                'trade',
                f"[{position.symbol}] AI 커스텀 부분청산 확인: {closed_quantity:g}, "
                f"잔여 {remaining:g}, 사유={decision.get('reason')}",
            )
            return True
        except Exception as exc:
            self.log_event(
                'trade', f"[{position.symbol}] AI 커스텀 부분청산 실패: {exc}",
                level='WARNING',
            )
            return False

    def _calculate_dynamic_profit_threshold(self, position: Position) -> float:
        """동적 수익 청산 임계값 계산"""
        try:
            # 기본 임계값 (기존 시스템 참고: 슬리피지 + 수수료)
            # 바이낸스 선물 수수료: 진입 0.02% + 청산 0.02% = 총 0.04%
            # 최소 수익: 0.15% (수수료 0.04% 제외 시 실제 수익 0.11%)
            base_threshold = 0.15  # 0.15%

            # 변동성 기반 조정
            if self.analyzer:
                try:
                    # 현재 변동성 조회
                    market_data = self.analyzer._analyze_current_market_conditions()
                    market_level = market_data.get('level', 'NORMAL')

                    if market_level == 'HIGH':
                        volatility_multiplier = 1.5  # 고변동성: 더 큰 수익 기대
                    elif market_level == 'LOW':
                        volatility_multiplier = 0.8  # 저변동성: 작은 수익도 확보
                    else:
                        volatility_multiplier = 1.0

                    base_threshold *= volatility_multiplier
                except Exception:
                    pass

            # 보유 시간 기반 조정
            holding_time = _elapsed_minutes(position.entry_time)
            if holding_time > 20:  # 20분 이상 보유 시 임계값 낮춤
                time_factor = max(0.5, 1.0 - (holding_time - 20) * 0.01)
                base_threshold *= time_factor

            # Evaluator에서 사용하는 메이저 코인 리스트와 동기화
            major_coins_evaluator = ['BTC', 'ETH', 'BNB', 'SOL', 'ADA', 'XRP', 'DOT', 'LINK', 'AVAX', 'MATIC']
            coin = position.symbol.replace('USDT', '')

            # AI 기반 코인 특성 분석 (향후 확장 가능)
            if hasattr(self, 'ai_manager') and self.ai_manager:
                try:
                    # AI가 코인의 변동성 특성을 분석하여 분류
                    coin_characteristics = self.ai_manager.analyze_coin_characteristics(position.symbol)
                    volatility_level = coin_characteristics.get('volatility_level', 'medium')

                    if volatility_level == 'low':
                        coin_factor = 0.8  # 낮은 변동성 → 보수적
                    elif volatility_level == 'high':
                        coin_factor = 1.2  # 높은 변동성 → 공격적
                    else:
                        coin_factor = 1.0  # 중간 변동성 → 기본

                    self.log_event('analysis', f"[{position.symbol}] AI 코인 특성 분석: {volatility_level} → factor {coin_factor}")
                except Exception as e:
                    self.log_event('analysis', f"[{position.symbol}] AI 분석 실패, 기본 분류 사용: {e}", level='WARNING')
                    # AI 분석 실패 시 기본 분류 사용
                    if coin in major_coins_evaluator:
                        coin_factor = 0.8  # 메이저 코인: 더 보수적
                    else:
                        coin_factor = 1.2  # 알트 코인: 더 공격적
            else:
                # AI 매니저가 없을 때 기본 분류
                if coin in major_coins_evaluator:
                    coin_factor = 0.8  # 메이저 코인: 더 보수적
                else:
                    coin_factor = 1.2  # 알트 코인: 더 공격적

            final_threshold = base_threshold * coin_factor

            # 최소/최대 제한 (수수료 0.04% 고려하여 최소값 상향)
            # 바이낸스 선물 수수료: 진입 0.02% + 청산 0.02% = 총 0.04%
            # 최소 수익: 0.10% (수수료 제외 시 실제 수익 0.06%)
            return max(0.10, min(final_threshold, 0.5))  # 0.10% ~ 0.5%

        except Exception as e:
            self.logger.error(f"동적 수익 임계값 계산 오류: {e}")
            return 0.15  # 기본값

    def _calculate_dynamic_loss_threshold(self, position: Position) -> float:
        """동적 손실 청산 임계값 계산"""
        try:
            # 기본 손실 임계값 (기존 시스템 참고)
            base_threshold = 0.20  # 0.20%

            # 연속 손실 고려
            if self.risk_manager:
                coin = position.symbol.replace('USDT', '')
                consecutive_losses = self.risk_manager.coin_consecutive_losses.get(coin, 0)

                # 연속 손실이 있으면 더 빠른 손절
                if consecutive_losses >= 2:
                    base_threshold *= 0.7  # 30% 더 빠른 손절
                elif consecutive_losses >= 1:
                    base_threshold *= 0.85  # 15% 더 빠른 손절

            # 변동성 기반 조정
            if self.analyzer:
                try:
                    market_data = self.analyzer._analyze_current_market_conditions()
                    market_level = market_data.get('level', 'NORMAL')

                    if market_level == 'HIGH':
                        volatility_multiplier = 1.3  # 고변동성: 더 큰 손실 허용
                    elif market_level == 'LOW':
                        volatility_multiplier = 0.7  # 저변동성: 빠른 손절
                    else:
                        volatility_multiplier = 1.0

                    base_threshold *= volatility_multiplier
                except Exception:
                    pass

            # 최소/최대 제한
            return max(0.10, min(base_threshold, 0.40))  # 0.10% ~ 0.40%

        except Exception as e:
            self.logger.error(f"동적 손실 임계값 계산 오류: {e}")
            return 0.20  # 기본값

    def _get_ai_exit_decision(self, position: Position) -> Dict:
        """AI 기반 청산 결정"""
        try:
            if not self.ai_manager:
                return {'should_exit': False}

            # 현재 시장 상황과 포지션 정보를 AI에 전달
            position_data = {
                'symbol': position.symbol,
                'side': position.side.value,
                'entry_price': position.entry_price,
                'current_price': position.current_price,
                'unrealized_pnl_percent': position.unrealized_pnl_percent,
                'holding_time_minutes': _elapsed_minutes(position.entry_time),
                'leverage': position.leverage
            }

            # AI 분석 요청 (간단한 구현)
            # 실제로는 ai_manager의 analyze_exit_conditions 메서드 호출
            holding_time = position_data['holding_time_minutes']
            pnl_percent = position_data['unrealized_pnl_percent']

            # 기본 AI 로직 (추후 OpenAI API 연동 가능)
            should_exit = False
            reason = ""

            # 장기 보유 + 작은 수익 → 청산 권장
            if holding_time > 25 and pnl_percent > 0.08:
                should_exit = True
                reason = f"장기보유({holding_time:.1f}분) + 작은수익({pnl_percent:.3f}%) → 이익실현 권장"

            # 급격한 손실 → 청산 권장
            elif pnl_percent < -1.0:
                should_exit = True
                reason = f"급격한 손실({pnl_percent:.3f}%) → 손절 권장"

            return {
                'should_exit': should_exit,
                'reason': reason,
                'confidence': 0.8 if should_exit else 0.2
            }

        except Exception as e:
            self.logger.error(f"AI 청산 결정 오류: {e}")
            return {'should_exit': False}

    def _perform_pre_entry_analysis(self, symbol: str, signal_data: Dict) -> Dict:
        """기존 시스템 스타일: 진입 전 패턴 분석 + AI 검증"""
        try:
            coin = symbol.replace('USDT', '')

            # 1. 최근 거래 이력 분석 (기존 시스템 스타일)
            pattern_analysis = self._analyze_recent_trading_patterns(coin)

            # 2. 현재 시장 조건 평가
            market_conditions = self._evaluate_current_market_conditions(symbol)

            # WebSocket 데이터 체크 (verbose)
            if self.settings.get('verbose_trade_logging', False):
                depth_available = hasattr(self.binance_client, 'websocket_manager') and hasattr(self.binance_client.websocket_manager, 'orderbooks') and symbol in self.binance_client.websocket_manager.orderbooks
                ticker_available = hasattr(self.binance_client, 'websocket_manager') and hasattr(self.binance_client.websocket_manager, 'tickers') and symbol in self.binance_client.websocket_manager.tickers
                self._log_trade_event('analysis', f"{symbol} WebSocket data check: depth={'✓' if depth_available else '✗'}, ticker={'✓' if ticker_available else '✗'}")

            # 3. AI 기반 종합 판단
            ai_validation = self._ai_validate_entry_conditions(
                symbol, signal_data, pattern_analysis, market_conditions
            )

            # 4. 🔥 동적 임계값 기반 최종 결정
            dynamic_thresholds = self._get_dynamic_entry_thresholds(symbol, market_conditions)
            try:
                base_snapshot = dynamic_thresholds.get('_base', {}) if isinstance(dynamic_thresholds, dict) else {}
                source = dynamic_thresholds.get('_source', 'unknown') if isinstance(dynamic_thresholds, dict) else 'unknown'
                self.log_event(
                    'analysis',
                    (
                        f"[{symbol}] 학습 반영 임계값(before->after): "
                        f"min_ai_confidence {base_snapshot.get('min_ai_confidence', 'N/A')} -> {dynamic_thresholds.get('min_ai_confidence', 'N/A')}, "
                        f"max_loss_rate {base_snapshot.get('max_loss_rate', 'N/A')} -> {dynamic_thresholds.get('max_loss_rate', 'N/A')}, "
                        f"min_trades_history {base_snapshot.get('min_trades_history', 'N/A')} -> {dynamic_thresholds.get('min_trades_history', 'N/A')} "
                        f"(source={source})"
                    )
                )
            except Exception:
                pass

            # 동적 임계값 사용 (데이터 충분 여부와 무관하게 일관된 기준 적용)
            dynamic_confidence_threshold = self._calculate_dynamic_confidence_threshold(symbol, signal_data)

            # 🔥 초기 거래를 위한 조건 완화: 전체 거래 이력 + 코인별 거래 이력 확인
            all_trades_count = 0
            if self.risk_manager and hasattr(self.risk_manager, 'coin_trade_history'):
                all_trades_count = sum(len(history) for history in self.risk_manager.coin_trade_history.values())
            # 메모리 이력은 재시작 때 비워지므로 실제 DB 종료 거래를 함께 사용한다.
            # 장기 사용자에게 매번 첫 사용자 완화 정책이 적용되는 문제를 막는다.
            try:
                if self.recorder and hasattr(self.recorder, 'count_closed_trades'):
                    persisted_count = self.recorder.count_closed_trades(exchange='binance')
                    all_trades_count = max(all_trades_count, persisted_count)
            except Exception as history_error:
                self.logger.debug(f"지속 거래 이력 조회 실패, 메모리 이력 사용: {history_error}")
            
            # 해당 코인의 거래 이력 확인
            coin_trades_count = pattern_analysis.get('recent_trades', 0)
            coin = symbol.replace('USDT', '')
            is_first_coin_trade = coin_trades_count == 0  # 해당 코인 첫 거래 여부
            is_first_overall_trade = all_trades_count == 0  # 전체 첫 거래 여부
            
            # 🔍 디버깅: 거래 이력 상태 로그(기본 숨김)
            self._log_trade_event(
                'analysis',
                f"🔍 {symbol} 거래 이력 상태: 전체={all_trades_count}회, 코인={coin_trades_count}회, 첫전체거래={is_first_overall_trade}, 첫코인거래={is_first_coin_trade}",
                verbose_only=True,
            )

            # 🔥 스마트한 점진적 학습 시스템: 전체 거래 이력 + 코인별 거래 이력에 따라 임계값 점진적 조정
            # AI가 이미 시그널 강도를 반영하여 AI 신뢰도를 조정하므로, AI 판단을 신뢰
            # 약한 시그널이라도 AI가 시장 조건을 종합 분석하여 높은 신뢰도를 줄 수 있음
            # 코인별 첫 거래도 완화 적용하여 새로운 코인 거래 가능
            
            # 실제 사용된 임계값 추적 (로그 및 결정 사유에 사용)
            actual_threshold_used = dynamic_confidence_threshold
            
            if is_first_overall_trade:
                # 🆕 첫 거래: AI 신뢰도 기반 완화 (시그널 강도는 AI가 이미 반영함)
                # AI가 약한 시그널에 대해 이미 페널티를 주었으므로, AI 판단을 신뢰
                first_trade_threshold = max(dynamic_confidence_threshold - 0.15, 0.55)  # 최대 -0.15, 최소 0.55
                actual_threshold_used = first_trade_threshold
                
                proceed = (
                    market_conditions.get('volatility_suitable', True) and
                    ai_validation['confidence'] >= first_trade_threshold
                )
                self.log_event('analysis', f"🔍 {symbol} 첫 거래 감지 - 스마트 완화 적용 (전체 거래: {all_trades_count}회, 코인 거래: {coin_trades_count}회, 시그널 신뢰도: {signal_data.get('confidence', 0.5):.2f}, AI 신뢰도: {ai_validation['confidence']:.2f}, 임계값: {first_trade_threshold:.2f}, 기본 임계값: {dynamic_confidence_threshold:.2f})")
            elif is_first_coin_trade and all_trades_count <= 10:
                # 🆕 코인별 첫 거래: 전체 거래 이력이 적으면 완화 적용
                # 새로운 코인 거래를 위해 완화된 임계값 사용
                first_coin_threshold = max(dynamic_confidence_threshold - 0.12, 0.58)  # 최대 -0.12, 최소 0.58
                actual_threshold_used = first_coin_threshold
                
                proceed = (
                    market_conditions.get('volatility_suitable', True) and
                    ai_validation['confidence'] >= first_coin_threshold
                )
                self.log_event('analysis', f"🔍 {symbol} 코인별 첫 거래 감지 - 완화 적용 (전체 거래: {all_trades_count}회, 코인 거래: {coin_trades_count}회, 시그널 신뢰도: {signal_data.get('confidence', 0.5):.2f}, AI 신뢰도: {ai_validation['confidence']:.2f}, 임계값: {first_coin_threshold:.2f}, 기본 임계값: {dynamic_confidence_threshold:.2f})")
            elif all_trades_count <= 5:
                # 2-5 거래: 점진적 완화
                early_trade_threshold = max(dynamic_confidence_threshold - 0.10, 0.60)  # 최대 -0.10, 최소 0.60
                actual_threshold_used = early_trade_threshold
                
                proceed = (
                    market_conditions.get('volatility_suitable', True) and
                    ai_validation['confidence'] >= early_trade_threshold
                )
                self.log_event('analysis', f"🔍 {symbol} 초기 거래 단계 - 점진적 완화 (전체 거래: {all_trades_count}회, 시그널 신뢰도: {signal_data.get('confidence', 0.5):.2f}, AI 신뢰도: {ai_validation['confidence']:.2f}, 임계값: {early_trade_threshold:.2f}, 기본 임계값: {dynamic_confidence_threshold:.2f})")
            elif all_trades_count <= 10:
                # 6-10 거래: 약간 완화 (정상 임계값에 근접)
                mid_trade_threshold = max(dynamic_confidence_threshold - 0.05, 0.65)  # 최대 -0.05, 최소 0.65
                actual_threshold_used = mid_trade_threshold
                
                proceed = (
                    market_conditions.get('volatility_suitable', True) and
                    ai_validation['confidence'] >= mid_trade_threshold
                )
                self.log_event('analysis', f"🔍 {symbol} 중기 거래 단계 - 약간 완화 (전체 거래: {all_trades_count}회, 시그널 신뢰도: {signal_data.get('confidence', 0.5):.2f}, AI 신뢰도: {ai_validation['confidence']:.2f}, 임계값: {mid_trade_threshold:.2f}, 기본 임계값: {dynamic_confidence_threshold:.2f})")
            else:
                # 11 거래 이상: 정상 임계값 사용 (충분한 학습 데이터 확보)
                # 데이터 충분 여부와 관계없이 정상 임계값 적용
                if not pattern_analysis.get('data_insufficient', False) and not pattern_analysis.get('used_defaults', False):
                    # 데이터 충분: 전체 조건 검증 (실제 거래 이력이 있을 때만)
                    actual_threshold_used = dynamic_confidence_threshold
                    proceed = (
                        pattern_analysis['loss_rate'] < dynamic_thresholds['max_loss_rate'] and
                        pattern_analysis['recent_trades'] >= dynamic_thresholds['min_trades_history'] and
                        market_conditions['volatility_suitable'] and
                        ai_validation['confidence'] >= dynamic_confidence_threshold
                    )
                    self.log_event('analysis', f"🔍 {symbol} 정상 거래 단계 - 전체 조건 검증 (전체 거래: {all_trades_count}회, 시그널 신뢰도: {signal_data.get('confidence', 0.5):.2f}, AI 신뢰도: {ai_validation['confidence']:.2f}, 임계값: {dynamic_confidence_threshold:.2f})")
                else:
                    # 데이터 부족: user_signal_threshold 기반 + 소폭 보정 (최대 0.70)
                    # ⚠️ 기본값 사용 시 loss_rate=50.0은 무시하고 신뢰도만 체크
                    # AI가 이미 시그널 강도를 반영했으므로 AI 판단을 신뢰
                    conservative_threshold = min(dynamic_confidence_threshold + 0.05, 0.70)
                    actual_threshold_used = conservative_threshold
                    proceed = (
                        market_conditions.get('volatility_suitable', True) and
                        ai_validation['confidence'] >= conservative_threshold
                    )
                    if pattern_analysis.get('used_defaults'):
                        self._log_trade_event('analysis', f"🔍 {symbol} 기본값 사용 - 손실률 무시, 신뢰도만 체크 (임계값: {conservative_threshold:.2f}, AI 신뢰도: {ai_validation['confidence']:.2f}, 시그널 신뢰도: {signal_data.get('confidence', 0.5):.2f})", verbose_only=True)
                    else:
                        self._log_trade_event('analysis', f"🔍 {symbol} 데이터 부족 - 완화된 임계값 적용 (임계값: {conservative_threshold:.2f}, 동적 임계값: {dynamic_confidence_threshold:.2f}, 시그널 신뢰도: {signal_data.get('confidence', 0.5):.2f})", verbose_only=True)

            # 디버깅 로그 추가(기본 숨김)
            self._log_trade_event('analysis', f"🔍 {symbol} Pre-entry 분석 세부사항:", verbose_only=True)
            self._log_trade_event('analysis', f"  - 패턴 분석: {pattern_analysis}", verbose_only=True)
            self._log_trade_event('analysis', f"  - 시장 조건: {market_conditions}", verbose_only=True)
            self._log_trade_event('analysis', f"  - AI 검증: {ai_validation}", verbose_only=True)
            self._log_trade_event('analysis', f"  - 동적 임계값: {dynamic_thresholds}", verbose_only=True)
            self._log_trade_event('analysis', f"  - 최종 proceed: {proceed}", verbose_only=True)

            reason = ai_validation.get('reasoning', '진입 조건 분석 완료')
            # 표본 부족/기본값 사용 주석 추가
            try:
                data_notes = []
                if pattern_analysis.get('data_insufficient'):
                    data_notes.append('성과 표본 없음(진입 차단 사유 아님)')
                if pattern_analysis.get('used_defaults'):
                    data_notes.append('중립 기본값 사용')
                if data_notes:
                    reason = f"{reason} | 데이터: {', '.join(data_notes)}"
            except Exception:
                pass
            if not proceed:
                # ⚠️ 첫 거래이거나 기본값 사용 시 loss_rate는 무시
                if all_trades_count == 0 or pattern_analysis.get('used_defaults', False):
                    # 기본값 손실률은 진입 금지 사유로 사용하지 않음
                    if not market_conditions['volatility_suitable']:
                        reason = "변동성 부적절"
                    else:
                        # 실제 사용된 임계값으로 비교 (완화된 임계값 반영)
                        reason = f"AI 신뢰도 부족 ({ai_validation['confidence']:.2f} < {actual_threshold_used:.2f})"
                elif pattern_analysis['loss_rate'] >= 50.0:
                    reason = f"높은 손실률 ({pattern_analysis['loss_rate']:.1f}%)"
                elif pattern_analysis['recent_trades'] < 1:
                    reason = f"거래 이력 부족 ({pattern_analysis['recent_trades']}회)"
                elif not market_conditions['volatility_suitable']:
                    reason = "변동성 부적절"
                else:
                    reason = f"AI 신뢰도 부족 ({ai_validation['confidence']:.1f})"

            self.log_event(
                'analysis',
                (
                    f"[{symbol}] 진입 전 분석 결과: proceed={proceed}, "
                    f"loss_rate={pattern_analysis['loss_rate']:.1f}%, trades={pattern_analysis['recent_trades']}, "
                    f"vol_ok={market_conditions['volatility_suitable']}, ai_conf={ai_validation['confidence']:.2f}, reason={reason}"
                )
            )

            return {
                'proceed': proceed,
                'reason': reason,
                'pattern_analysis': pattern_analysis,
                'market_conditions': market_conditions,
                'ai_validation': ai_validation
            }

        except Exception as e:
            self.log_event('analysis', f"진입 전 분석 오류: {e}", level='ERROR')
            return {
                'proceed': False,
                'reason': f'분석 오류: {str(e)}',
                'pattern_analysis': {},
                'market_conditions': {},
                'ai_validation': {}
            }

    def _analyze_recent_trading_patterns(self, coin: str) -> Dict:
        """
        확장된 거래 패턴 분석 (최근 50회, 시장 상황별 분석)
        
        ⚠️ 중요: 이 함수는 코인 선택 시가 아니라 거래 실행 시 호출됩니다.
        - 호출 경로: execute_trading_cycle() → 각 코인 분석 → _perform_pre_entry_analysis() → 이 함수
        - 코인 선택 과정(_analyze_candidate_coins)에서는 호출되지 않습니다.
        """
        try:
            # 🔥 1단계: RiskManager 메모리 이력 확인
            memory_trades = []
            if self.risk_manager and coin in self.risk_manager.coin_trade_history:
                memory_trades = self.risk_manager.coin_trade_history[coin][-50:]  # 최근 50회
            
            # 🔥 성능 최적화: 메모리 이력이 충분하면 (20회 이상) DB 조회 생략
            if len(memory_trades) >= 20:
                recent_trades = memory_trades[-50:] if len(memory_trades) > 50 else memory_trades
                # 메모리 이력만으로 분석 가능
            else:
                # 🔥 2단계: DB에서 거래 이력 조회 (메모리 이력이 부족한 경우만)
                # 🔥 신규 거래자 최적화: 메모리 이력이 0이고 recorder가 없으면 즉시 기본값 반환
                if len(memory_trades) == 0 and (not hasattr(self, 'recorder') or not self.recorder):
                    # 신규 거래자이고 recorder가 없으면 DB 조회 없이 기본값 반환
                    return {
                        'recent_trades': 0,
                        'loss_rate': 50.0,
                        'win_rate': 50.0,
                        'avg_profit_rate': 0.0,
                        'avg_loss_rate': 0.0,
                        'profit_count': 0,
                        'loss_count': 0,
                        'data_insufficient': True,
                        'used_defaults': True
                    }
                
                # 🔥 캐싱 추가: DB 조회 결과를 5분간 캐싱하여 반복 조회 방지
                symbol = f"{coin}USDT"
                cache_key = f"pattern_analysis_{symbol}"
                
                # 캐시 확인
                if not hasattr(self, '_pattern_analysis_cache'):
                    self._pattern_analysis_cache = {}
                
                import time
                current_time = time.time()
                cached_data = self._pattern_analysis_cache.get(cache_key)
                
                if cached_data and current_time - cached_data['timestamp'] < 300:  # 5분 캐시
                    db_trades = cached_data['db_trades']
                    self.logger.debug(f"[{coin}] 패턴 분석 캐시 사용 (DB 조회 생략)")
                else:
                    # DB 조회 수행 (신규 거래자는 빈 결과 반환)
                    db_trades = []
                    if hasattr(self, 'recorder') and self.recorder:
                        try:
                            # 🔥 간단한 DB 조회 (타임아웃은 recorder.execute_query에서 처리)
                            db_history = self.recorder.get_trade_history(symbol=symbol, days=30)
                            if isinstance(db_history, list) and len(db_history) > 0:
                                # DB 데이터를 RiskManager 형식으로 변환
                                for trade in db_history[:50]:  # 최근 50회만
                                    pnl_percent = float(trade.get('pnl_percent', 0) or 0)
                                    db_trades.append({
                                        'symbol': symbol,
                                        'result': 'PROFIT' if pnl_percent > 0 else 'LOSS',
                                        'profit_rate': pnl_percent,
                                        'timestamp': trade.get('exit_time'),
                                        'entry_price': float(trade.get('entry_price', 0) or 0),
                                        'exit_price': float(trade.get('exit_price', 0) or 0),
                                        'position_size': float(trade.get('quantity', 0) or 0) * float(trade.get('entry_price', 0) or 0),
                                        'holding_time': 0  # DB에는 보유 시간 정보가 없을 수 있음
                                    })
                            # 캐시 저장 (빈 결과도 캐싱하여 반복 조회 방지)
                            self._pattern_analysis_cache[cache_key] = {
                                'db_trades': db_trades,
                                'timestamp': current_time
                            }
                        except Exception as db_err:
                            self.logger.warning(f"[{coin}] DB 거래 이력 조회 실패: {db_err}")
                            db_trades = []
                            # 오류도 캐싱하여 반복 시도 방지
                            self._pattern_analysis_cache[cache_key] = {
                                'db_trades': [],
                                'timestamp': current_time
                            }
                
                # 🔥 3단계: 메모리 + DB 이력 통합 (중복 제거)
                all_trades = memory_trades.copy()
                memory_timestamps = {t.get('timestamp') for t in memory_trades if t.get('timestamp')}
                for db_trade in db_trades:
                    if db_trade.get('timestamp') not in memory_timestamps:
                        all_trades.append(db_trade)
                
                # 최근 50회만 유지
                recent_trades = all_trades[-50:] if len(all_trades) > 50 else all_trades

            if len(recent_trades) == 0:
                # 거래 이력이 없는 경우 기본값 반환
                return {
                    'recent_trades': 0,
                    'loss_rate': 50.0,  # 70.0 → 50.0 (완화)
                    'win_rate': 50.0,   # 30.0 → 50.0 (완화)
                    'avg_profit_rate': 0.0,
                    'avg_loss_rate': 0.0,
                    'profit_count': 0,
                    'loss_count': 0,
                    'data_insufficient': True,
                    'used_defaults': True
                }
            else:
                # 거래 이력이 있는 경우 분석 수행
                profit_trades = [t for t in recent_trades if t['result'] == 'PROFIT']
                loss_trades = [t for t in recent_trades if t['result'] in ['LOSS', 'FORCE_CLOSE']]

                # 🔍(옵션) 시장/시간대/추세 분석은 unified_trader 전용 기능입니다.
                # trader(Binance)에서는 의사결정에 사용하지 않아 비용 절감을 위해 생략합니다.

                # 라플라스 스무딩으로 극단값 완화 (더 정교한 스무딩)
                total = len(recent_trades)
                wins = len(profit_trades)
                losses = len(loss_trades)

                # 더 정교한 라플라스 스무딩 (α=2)
                alpha = 2
                win_rate = ((wins + alpha) / (total + 2*alpha)) * 100.0
                loss_rate = ((losses + alpha) / (total + 2*alpha)) * 100.0

                avg_profit_rate = sum(t['profit_rate'] for t in profit_trades) / len(profit_trades) if profit_trades else 0.0
                avg_loss_rate = abs(sum(t['profit_rate'] for t in loss_trades) / len(loss_trades)) if loss_trades else 0.0

                # 🔍(옵션) 최근 성과 추세 분석은 unified_trader 전용 기능입니다.

                return {
                    'recent_trades': total,
                    'loss_rate': loss_rate,
                    'win_rate': win_rate,
                    'avg_profit_rate': avg_profit_rate,
                    'avg_loss_rate': avg_loss_rate,
                    'profit_count': wins,
                    'loss_count': losses,
                    'data_insufficient': bool(total < 20),  # 최소 20회 필요
                    'used_defaults': False
                }

        except Exception as e:
            self.logger.error(f"거래 패턴 분석 오류: {e}")
            return {
                'recent_trades': 0,
                'loss_rate': 50.0,  # 70.0 → 50.0 (완화)
                'win_rate': 50.0,   # 30.0 → 50.0 (완화)
                'avg_profit_rate': 0.0,
                'avg_loss_rate': 0.0,
                'data_insufficient': True,
                'used_defaults': True
            }

    def _evaluate_current_market_conditions(self, symbol: str) -> Dict:
        """현재 시장 조건 평가"""
        try:
            # 기본 시장 조건 평가 (초기값 명시해 정적 분석기 경고 제거)
            market_level = 'NORMAL'
            volatility_suitable = True  # 기본값 - 초기 거래를 위해 True로 설정
            trend_strength = 'MEDIUM'   # 기본값

            if self.analyzer:
                try:
                    # 현재 변동성 확인
                    market_data = self.analyzer._analyze_current_market_conditions()
                    market_level = market_data.get('level', 'NORMAL')

                    # 변동성 조건 완화 (초기 거래를 위해)
                    volatility_suitable = True  # 모든 시장 상황에서 거래 허용

                    if market_level == 'HIGH':
                        trend_strength = 'STRONG'
                    elif market_level == 'LOW':
                        trend_strength = 'WEAK'

                except Exception:
                    pass

            return {
                'volatility_suitable': volatility_suitable,
                'trend_strength': trend_strength,
                'market_level': market_level
            }

        except Exception as e:
            self.logger.error(f"시장 조건 평가 오류: {e}")
            return {
                'volatility_suitable': True,
                'trend_strength': 'MEDIUM',
                'market_level': 'NORMAL'
            }

    def _ai_validate_entry_conditions(self, symbol: str, signal_data: Dict,
                                    pattern_analysis: Dict, market_conditions: Dict) -> Dict:
        """AI 기반 진입 조건 검증 (기존 시스템 스타일)"""
        try:
            # 기본 AI 검증 로직
            confidence = 0.7  # 기본 신뢰도
            reasoning = "기본 AI 검증 완료"
            has_completed_history = not (
                pattern_analysis.get('data_insufficient', False)
                or pattern_analysis.get('used_defaults', False)
            )
            if not has_completed_history:
                reasoning = "완료 거래 없음·제한 학습 허용"

            # 패턴 분석 기반 신뢰도 조정 (실제 데이터가 있을 때만 적용)
            if not pattern_analysis.get('data_insufficient', False) and not pattern_analysis.get('used_defaults', False):
                if pattern_analysis.get('loss_rate', 0) > 30:
                    confidence -= 0.2  # 손실률 높으면 신뢰도 하락
                    reasoning = f"높은 손실률({pattern_analysis.get('loss_rate', 0):.1f}%)로 신뢰도 하락"
                elif pattern_analysis.get('loss_rate', 0) < 20:
                    confidence += 0.1  # 손실률 낮으면 신뢰도 상승
                    reasoning = f"낮은 손실률({pattern_analysis.get('loss_rate', 0):.1f}%)로 신뢰도 상승"

            # 시장 조건 기반 조정
            if not market_conditions.get('volatility_suitable', True):
                confidence -= 0.3
                reasoning += " + 부적절한 변동성"

            # 신호 데이터 기반 조정 (시그널 강도에 따른 스마트 조정)
            signal_confidence = signal_data.get('confidence', 0.5)
            if signal_confidence > 0.8:
                confidence += 0.15  # 매우 강한 시그널: 더 큰 보너스
                reasoning += " + 매우 강한 신호"
            elif signal_confidence > 0.7:
                confidence += 0.10  # 강한 시그널: 보너스
                reasoning += " + 강한 신호"
            elif signal_confidence > 0.6:
                confidence += 0.05  # 중간 이상 시그널: 소폭 보너스
                reasoning += " + 중간 이상 신호"
            elif signal_confidence < 0.5:
                confidence -= 0.15  # 약한 시그널: 더 큰 페널티
                reasoning += " + 약한 신호"
            elif signal_confidence < 0.6:
                confidence -= 0.05  # 중간 이하 시그널: 소폭 페널티
                reasoning += " + 중간 이하 신호"

            # 최종 신뢰도 범위 제한
            confidence = max(0.0, min(confidence, 1.0))

            threshold = self._calculate_dynamic_confidence_threshold(symbol, signal_data)
            return {
                'confidence': confidence,
                'reasoning': f"{reasoning} | threshold={threshold:.2f}",
                'validation': 'APPROVED' if confidence >= threshold else 'REJECTED',
                'cold_start': not has_completed_history,
                'history_gate_blocked': False,
            }

        except Exception as e:
            self.logger.error(f"AI 검증 오류: {e}")
            return {
                'confidence': 0.5,
                'reasoning': f'AI 검증 오류: {str(e)}',
                'validation': 'ERROR'
            }

    def _calculate_dynamic_confidence_threshold(self, symbol: str, signal_data: Dict) -> float:
        """AI 기반 동적 신뢰도 임계값 계산 (시장 상황 + 승률 기반 자동 조정)"""
        try:
            # 1) 분석기 임계값을 신뢰도 기준에 반영 (50~90 → 0.50~0.90)
            analyzer_th = 0
            try:
                if hasattr(self, 'analyzer') and self.analyzer:
                    analyzer_th = int(self.analyzer.get_user_signal_threshold())
            except Exception:
                analyzer_th = 0

            # 기본 맵핑: 50 → 0.50, 60 → 0.60, 70 → 0.70, 80 → 0.80, 90 → 0.90
            # user_signal_threshold를 그대로 신뢰도로 사용 (50~90 → 0.50~0.90)
            base_threshold = analyzer_th / 100.0 if analyzer_th > 0 else 0.65

            # 2) 시장 상황에 따른 소폭 가감 (곱이 아닌 가/감산으로 과도한 완화 방지)
            try:
                if hasattr(self, 'analyzer') and self.analyzer:
                    market_data = self.analyzer._analyze_current_market_conditions()
                    market_level = (market_data or {}).get('level', 'NORMAL')
                    if market_level == 'HIGH':
                        base_threshold += 0.02  # 고변동성 → 더 보수적
                    elif market_level == 'LOW':
                        base_threshold -= 0.02  # 저변동성 → 약간 완화
            except Exception:
                pass

            # 3) 연속 성과 기반 미세 조정(±0.03 이내)
            try:
                if hasattr(self, 'risk_manager') and self.risk_manager:
                    coin = symbol.replace('USDT', '')
                    consecutive_wins = int(self.risk_manager.coin_consecutive_wins.get(coin, 0))
                    consecutive_losses = int(self.risk_manager.coin_consecutive_losses.get(coin, 0))
                    if consecutive_wins >= 2:
                        base_threshold -= 0.03
                    elif consecutive_wins == 1:
                        base_threshold -= 0.015
                    elif consecutive_losses >= 2:
                        base_threshold += 0.03
                    elif consecutive_losses == 1:
                        base_threshold += 0.015
            except Exception:
                pass

            # 🔥 4) 승률 기반 자동 조정 (AI 학습 반영)
            try:
                coin = symbol.replace('USDT', '')
                all_trades = []
                
                # RiskManager 메모리 이력
                if self.risk_manager and coin in self.risk_manager.coin_trade_history:
                    all_trades.extend(self.risk_manager.coin_trade_history[coin][-30:])
                
                # DB 이력 (메모리 보완)
                if hasattr(self, 'recorder') and self.recorder and len(all_trades) < 10:
                    try:
                        db_trades = self.recorder.get_recent_trades(coin=coin, exchange='binance', days=30)
                        memory_timestamps = {t.get('timestamp') for t in all_trades if t.get('timestamp')}
                        for trade in db_trades:
                            if trade.get('exit_time') not in memory_timestamps:
                                pnl_percent = float(trade.get('pnl_percent', 0) or 0)
                                all_trades.append({
                                    'result': 'PROFIT' if pnl_percent > 0 else 'LOSS',
                                    'profit_rate': pnl_percent,
                                    'timestamp': trade.get('exit_time')
                                })
                    except Exception:
                        pass
                
                # 승률 계산 및 조정
                if len(all_trades) >= 10:
                    wins = sum(1 for t in all_trades if t.get('result') == 'PROFIT' or (t.get('profit_rate', 0) or 0) > 0)
                    win_rate = wins / len(all_trades)
                    
                    # 승률에 따라 신뢰도 임계값 조정
                    if win_rate > 0.7:  # 높은 승률 → 더 공격적 (임계값 낮춤)
                        base_threshold -= 0.05  # 최대 -0.05
                        self.logger.info(f"[{symbol}] 🎯 높은 승률 기반 조정: {win_rate*100:.1f}% → 임계값 -0.05")
                    elif win_rate < 0.3:  # 낮은 승률 → 더 보수적 (임계값 높임)
                        base_threshold += 0.05  # 최대 +0.05
                        self.logger.warning(f"[{symbol}] ⚠️ 낮은 승률 기반 조정: {win_rate*100:.1f}% → 임계값 +0.05")
                    else:  # 중간 승률 → 비례 조정
                        adjustment = (win_rate - 0.5) * 0.1  # 0.3~0.7 승률 → -0.02~+0.02 조정
                        base_threshold -= adjustment
                        self.logger.info(f"[{symbol}] ℹ️ 중간 승률 기반 조정: {win_rate*100:.1f}% → 임계값 {adjustment:+.3f}")
            except Exception as win_rate_err:
                self.logger.debug(f"[{symbol}] 승률 기반 조정 실패 (무시): {win_rate_err}")

            # 5) 안전 가드레일
            base_threshold = max(0.30, min(base_threshold, 0.95))
            return base_threshold

        except Exception as e:
            self.logger.error(f"동적 신뢰도 임계값 계산 오류: {e}")
            return 0.65

    def _get_ai_enhanced_parameters(self, symbol: str, signal_data: Dict, pre_entry_analysis: Optional[Dict] = None) -> Dict:
        """AI 강화 거래 파라미터 생성 (기존 시스템 스타일)"""
        try:
            # 기존 최적화 결과 가져오기 (optimizer.py의 AI 캐싱 시스템 사용)
            optimizer_result = self.optimizer.optimize_parameters(symbol, signal_data)
            if isinstance(optimizer_result, dict) and isinstance(optimizer_result.get(symbol), dict):
                base_params = dict(optimizer_result[symbol])
            else:
                base_params = dict(optimizer_result or {})

            # AI 기반 강화 적용
            enhanced_params = base_params.copy()
            selected_custom = dict(signal_data.get('_custom_engine_settings', {}) or {})

            # 1. 모든 파생 거래소가 공유하는 실효 레버리지 정책.
            # 설정값은 상한이며 시장 안전상한(HIGH 1/NORMAL 2/LOW 3)이
            # 실제 주문값을 결정한다. XAI에는 두 값을 분리해 남긴다.
            market_level = 'NORMAL'
            if self.analyzer:
                try:
                    market_data = self.analyzer._analyze_current_market_conditions()
                    market_level = str(market_data.get('level', 'NORMAL')).upper()
                except Exception:
                    market_level = 'NORMAL'
            leverage_policy = resolve_effective_leverage(
                configured_leverage=base_params.get(
                    'leverage', self.settings.get('default_leverage', 1)
                ),
                exchange='binance',
                market_level=market_level,
                exchange_max_leverage=exchange_leverage_cap(self.settings, 'binance'),
            )
            enhanced_params['leverage'] = int(leverage_policy['effective'])
            enhanced_params['_leverage_policy'] = dict(leverage_policy)

            # 2. 동적 포지션 크기 (기존: 고정 → 개선: 시장 상황별)
            confidence = signal_data.get('confidence', 0.5)
            base_position_size = 0.1  # 10% 기본

            # 신뢰도 기반 조정
            confidence_factor = min(confidence * 1.5, 1.0)

            # 연속 성공 이력 기반 조정
            if self.risk_manager:
                coin = symbol.replace('USDT', '')
                consecutive_wins = self.risk_manager.coin_consecutive_wins.get(coin, 0)
                consecutive_losses = self.risk_manager.coin_consecutive_losses.get(coin, 0)

                if consecutive_wins >= 2:
                    success_factor = 1.2  # 연속 성공 시 포지션 크기 증가
                elif consecutive_losses >= 1:
                    success_factor = 0.7  # 연속 실패 시 포지션 크기 감소
                else:
                    success_factor = 1.0
            else:
                success_factor = 1.0

            final_position_size = base_position_size * confidence_factor * success_factor
            enhanced_params['position_size'] = max(0.05, min(final_position_size, 0.2))  # 5%~20%

            # 3. 동적 TP/SL (기존 시스템 스타일 적용)
            signal = signal_data.get('signal', 'HOLD')
            if signal in ['LONG', 'SHORT']:
                # 기존 시스템과 동일한 동적 TP/SL 로직 적용
                dynamic_tp = enhanced_params.get('tp_percent', 0.0018)  # 기본 0.18%
                dynamic_sl = enhanced_params.get('sl_percent', 0.0020)  # 기본 0.20%

                # 변동성 기반 조정
                if self.analyzer:
                    try:
                        market_data = self.analyzer._analyze_current_market_conditions()
                        market_level = market_data.get('level', 'NORMAL')

                        if market_level == 'HIGH':
                            tp_factor, sl_factor = 1.5, 1.3  # 고변동성: 더 큰 목표/손실
                        elif market_level == 'LOW':
                            tp_factor, sl_factor = 0.8, 0.8  # 저변동성: 작은 목표/손실
                        else:
                            tp_factor, sl_factor = 1.0, 1.0

                        enhanced_params['tp_percent'] = dynamic_tp * tp_factor
                        enhanced_params['sl_percent'] = dynamic_sl * sl_factor
                    except Exception:
                        pass

            # 상황 매칭으로 선택된 승인 전략의 설정값을 최종 사용자 전략 오버레이로 적용한다.
            enhanced_params = apply_engine_settings_to_trade_config(enhanced_params, selected_custom)
            enhanced_params['_selected_custom_strategy'] = signal_data.get('_selected_custom_strategy')
            enhanced_params['_selected_custom_strategy_id'] = signal_data.get('_selected_custom_strategy_id')
            enhanced_params['_selected_custom_strategy_key'] = signal_data.get('_selected_custom_strategy_key')
            enhanced_params['_selected_custom_strategy_version_id'] = signal_data.get('_selected_custom_strategy_version_id')
            enhanced_params['_custom_signal_mode'] = signal_data.get('_custom_signal_mode')
            enhanced_params['_custom_operation_mode'] = signal_data.get('_custom_operation_mode')
            enhanced_params['_exit_plan'] = dict(signal_data.get('_exit_plan') or {})
            enhanced_params['_custom_strategy_rules'] = dict(signal_data.get('_custom_strategy_rules') or {})
            self.logger.info(f"{symbol} AI 강화 파라미터: 레버리지={enhanced_params.get('leverage', 1)}x, "
                            f"포지션={format_percent(enhanced_params.get('position_size', 0.1), 1)}, "
                            f"TP={format_percent(enhanced_params.get('tp_percent', 0.0018), 3)}, "
                            f"SL={format_percent(enhanced_params.get('sl_percent', 0.0020), 3)}")

            return enhanced_params

        except Exception as e:
            self.logger.error(f"AI 강화 파라미터 생성 오류: {e}")
            return self.optimizer.optimize_parameters(symbol, signal_data)

    # execute_enhanced_trade 메서드 제거됨 - execute_trades가 모든 기능을 포함

    def start_realtime_monitoring(self, symbol: str, position: Position):
        """실시간 포지션 모니터링: PnL 추적, TP/SL 워치독, 사용자 임의 청산 감지"""
        try:
            # 🔥 WebSocket 보장 및 간격 조정
            ws_success = False
            if hasattr(self, 'binance_client') and hasattr(self.binance_client, 'ensure_ws_for'):
                ws_success = self.binance_client.ensure_ws_for(symbol)
                self.log_event('monitor', f"[{symbol}] 🔧 WebSocket 보장 시도: {'성공' if ws_success else '실패'}")

            # WebSocket 성공 여부에 따른 간격 조정
            if ws_success:
                interval = 2  # WebSocket 사용 시 빠른 간격
                has_websocket = True
            else:
                interval = 20  # WebSocket 실패 시 REST 폴백 주기 완화 (10초 → 20초)
                has_websocket = False
                self.log_event('monitor', f"[{symbol}] ⚠️ WebSocket 실패, REST 폴백 모드 (간격: {interval}초)", level='WARNING')

            self.log_event('monitor', f"[{symbol}] 실시간 모니터링 시작 ({interval}초 간격, WebSocket: {'✓' if has_websocket else '✗'})")

            # 실시간 가격 데이터 초기화
            self.price_data_points[symbol] = []
            data_count = 0
            start_time = datetime.now()

            # 🔥 모니터링 중지 신호 체크 (심볼별 개별 관리)
            while symbol in self.active_positions and not self.monitoring_flags.get(symbol, threading.Event()).is_set():
                try:
                    # 🔥 포지션 존재 여부 추가 확인 (사용자 임의 청산 대응)
                    current_position_info = self._get_position_info_with_retry(symbol)
                    if not current_position_info or abs(float(current_position_info.get('positionAmt', 0))) == 0:
                        self.log_event('monitor', f"[{symbol}] 포지션이 없음 - 사용자 임의 청산 감지", level='WARNING')

                        # 🔥 남은 오픈오더 자동 정리 (autotrade.py와 동일)
                        try:
                            open_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)
                            if open_orders:
                                self.log_event('monitor', f"[{symbol}] 포지션 없음, 남은 오픈오더 정리: {len(open_orders)}개")
                                for order in open_orders:
                                    try:
                                        cancel_result = self.binance_client.client.futures_cancel_order(
                                            symbol=symbol,
                                            orderId=order['orderId']
                                        )
                                        # 🔥 실제 취소 결과 확인
                                        if cancel_result.get('status') == 'CANCELED':
                                            self.log_event('monitor', f"[{symbol}] 오더 삭제 완료: {order['orderId']}")
                                        else:
                                            self.log_event('monitor', f"[{symbol}] 오더 삭제 실패: {cancel_result.get('status', 'UNKNOWN')}", level='WARNING')
                                    except Exception as e:
                                        self.log_event('monitor', f"[{symbol}] 오더 삭제 실패: {str(e)}", level='ERROR')
                        except Exception as e:
                            self.log_event('monitor', f"[{symbol}] 오더 정리 중 오류: {str(e)}", level='ERROR')

                        # 🔥 TP/SL 청산 감지 시 통계 업데이트
                        if symbol in self.active_positions:
                            position = self.active_positions[symbol]

                            # 안전한 현재가 확보 (정적 분석기 경고 제거)
                            try:
                                current_price = position.current_price if getattr(position, 'current_price', 0) else self.binance_client.get_current_price(symbol)
                            except Exception:
                                current_price = getattr(position, 'current_price', 0) or getattr(position, 'entry_price', 0) or 0.0

                            # PnL 계산
                            pnl_percent = self._calc_pnl_percent(position, current_price)

                            # 🔥 PnL USDT 계산 (통계용)
                            pnl_usdt = (pnl_percent / 100.0) * position.quantity * position.entry_price

                            # 거래 통계 업데이트
                            self.trade_stats['total_trades'] += 1
                            self.trade_stats['total_pnl'] += pnl_usdt  # 🔥 USDT 단위로 누적

                            if pnl_percent > 0:
                                self.trade_stats['winning_trades'] += 1
                            else:
                                self.trade_stats['losing_trades'] += 1

                            # DB에 통계 저장
                            if hasattr(self, 'recorder') and self.recorder:
                                self.recorder.save_exchange_trade_stats('binance', self.trade_stats)
                                
                                # 🔥 개별 거래 로그 업데이트 (exit_time 설정, position 객체 전달) - 문제 1 해결
                                try:
                                    # datetime은 이미 모듈 레벨에서 임포트되어 있음 (Line 13)
                                    exit_time = datetime.now()
                                    result = self.recorder.update_trade_log(
                                        symbol=symbol,
                                        exit_price=current_price,
                                        exit_time=exit_time,
                                        pnl_percent=pnl_percent,
                                        pnl_usdt=pnl_usdt,
                                        exit_reason="TP/SL 청산",
                                        position=position  # 🔥 position 객체 전달하여 TP/SL 판단 정확도 향상
                                    )
                                    if not result:
                                        self.log_event('trade', f"⚠️ {symbol} 거래 로그 업데이트 실패 (TP/SL 청산)", level='WARNING')
                                except Exception as e:
                                    self.log_event('trade', f"❌ {symbol} 거래 로그 업데이트 오류: {e}", level='ERROR')

                            # 🔥 대시보드 업데이트 (문제 3, 4 해결)
                            if self.dashboard:
                                try:
                                    # 거래 통계 업데이트
                                    if hasattr(self.dashboard, '_refresh_trading_summary'):
                                        # CustomTkinter 스레드 안전성을 위해 after() 사용
                                        if hasattr(self.dashboard, 'after'):
                                            self.dashboard.after(0, lambda: self.dashboard._refresh_trading_summary())
                                        else:
                                            self.dashboard._refresh_trading_summary()
                                    
                                    # 잔고 갱신 (즉시 + 지연 재갱신)
                                    if hasattr(self.dashboard, 'update_balance_on_trade_completion'):
                                        # 즉시 갱신 시도
                                        self.dashboard.update_balance_on_trade_completion()
                                        
                                        # 지연 후 재갱신 (거래소 반영 시간 고려)
                                        self._schedule_delayed_balance_update()
                                except Exception as e:
                                    self.log_event('trade', f"대시보드 업데이트 실패: {e}", level='WARNING')

                            # 거래 진입 플래그 해제
                            self.trade_entered[symbol] = False

                            self.logger.info(f"✅ {symbol} TP/SL 청산 감지: PnL {pnl_percent:.2f}%")

                            # active_positions에서 제거
                            # 참고: 오픈오더 정리는 이미 위에서 포지션 없음 감지 시 처리됨 (3864-3883줄)
                            self.active_positions.pop(symbol, None)

                        # 🔥 포지션 종료 (플래그는 모니터링 시작 시점에 이미 해제됨)
                        break

                    # 🔥 가격 조회 (WebSocket 보장 후)
                    current_price = self.binance_client.get_current_price_ws(symbol)

                    # 가격 조회 실패 시 재시도 로직 강화
                    if current_price <= 0:
                        self.log_event('monitor', f"[{symbol}] ⚠️ 가격 조회 실패 (가격: {current_price}) - REST 폴백 시도", level='WARNING')
                        # REST API 직접 호출
                        try:
                            current_price = self.binance_client.get_current_price(symbol)
                            if current_price <= 0:
                                self.log_event('monitor', f"[{symbol}] ❌ REST 폴백도 실패 - 모니터링 일시 중단", level='ERROR')
                                time.sleep(5)  # 실패 시 더 긴 대기
                                continue
                            else:
                                self.log_event('monitor', f"[{symbol}] ✅ REST 폴백 성공: {current_price}")
                        except Exception as e:
                            self.log_event('monitor', f"[{symbol}] ❌ REST 폴백 예외: {e}", level='ERROR')
                            time.sleep(5)
                            continue

                    current_time = datetime.now(timezone.utc)

                    # 데이터 포인트 저장 (기존 시스템 스타일)
                    self.price_data_points[symbol].append({
                        'time': current_time,
                        'price': current_price
                    })
                    data_count += 1

                    # 🔇 과다 출력 방지: 데이터 포인트 추가 로그는 verbose 모드에서만
                    self._log_trade_event('monitor', f"[{symbol}] Added data point: time={current_time}, price={current_price}", verbose_only=True)

                    # 🔥 더 자주 TP/SL 워치독 점검 (3번째, 5번째, 10번째마다)
                    if data_count in (3, 5, 10):
                        self._tp_sl_watchdog(symbol, position, check_idx=data_count)

                    # 포지션 업데이트
                    position.current_price = current_price
                    self.calculate_pnl(position)

                    advanced_decision = self._advanced_order_plan_decision(position)
                    if advanced_decision.get('action') == 'partial_close':
                        self._execute_advanced_partial_close_binance(position, advanced_decision)
                        continue
                    if advanced_decision.get('action') == 'close_all':
                        self.close_position(position, str(advanced_decision.get('reason') or 'AI 커스텀 고급 청산'))
                        break

                    # 10개마다 상태 체크 (요약 출력 + 스로틀링/임계값 적용)
                    if data_count % 10 == 0:
                        holding_time = _elapsed_minutes(position.entry_time)
                        profit_rate = position.unrealized_pnl_percent

                        # 🔍 개발/상세 모드에서는 항상 전체 로그 출력 (스로틀링 비활성화)
                        if self._is_verbose_logging():
                            self.log_event('monitor', f"[{symbol}] Monitoring - Entry: {position.entry_price:.4f}, Current: {current_price:.4f}, Profit: {profit_rate:.4f}%, Loss: {-profit_rate:.4f}% ({data_count}/999999)")
                        else:
                            # 🔍 요약 로그 스로틀링/임계값: 시간 간격 또는 PnL 변화가 임계값을 넘을 때만 출력
                            interval_sec = float(self.settings.get('monitor_log_interval_sec', 60))
                            delta_threshold = float(self.settings.get('monitor_pnl_delta_threshold', 0.05))
                            st = self.monitor_log_state.get(symbol, {'last_log_ts': 0.0, 'last_pnl': None})
                            now_ts = time.time()
                            pnl_changed = (st['last_pnl'] is None) or (abs(profit_rate - float(st['last_pnl'])) >= delta_threshold)
                            time_elapsed = (now_ts - float(st['last_log_ts'])) >= interval_sec
                            # 0 교차(손익 전환) 시에도 무조건 출력
                            crossed_zero = (st['last_pnl'] is not None) and ((profit_rate > 0) != (float(st['last_pnl']) > 0))
                            if pnl_changed or time_elapsed or crossed_zero:
                                self.log_event('monitor', f"[{symbol}] Monitoring - Entry: {position.entry_price:.4f}, Current: {current_price:.4f}, Profit: {profit_rate:.4f}%, Loss: {-profit_rate:.4f}% ({data_count}/999999)")
                                # 상태 갱신
                                self.monitor_log_state[symbol] = {'last_log_ts': now_ts, 'last_pnl': float(profit_rate)}

                        # 🔇 진행률 관련 상세 로그는 verbose에서만
                        try:
                            self._log_trade_event('monitor', f"[{symbol}] Data collection progress: {data_count} data points collected", verbose_only=True)
                            self._log_trade_event('monitor', f"[{symbol}] Additional data collection for potential position…", verbose_only=True)
                        except Exception:
                            pass

                        # AI 기반 조기 청산 체크 (기존 시스템 스타일)
                        ai_exit_decision = self._check_ai_early_exit(position, holding_time)
                        if ai_exit_decision['should_exit']:
                            self.log_event('monitor', f"[{symbol}] {ai_exit_decision['reason']}")
                            self.close_position(position, "AI 조기 청산")
                            break

                        # 일반 청산 조건 확인 (10개마다만 체크 - optimizer 호출 최적화)
                        if self.should_close_position(position):
                            self.log_event('monitor', f"[{symbol}] should_close_position returned True, preparing to close position")
                            exit_reason = self._determine_exit_reason(position)
                            self.log_event('monitor', f"[{symbol}] Exit reason determined: {exit_reason}")
                            self.close_position(position, exit_reason)
                            self.log_event('monitor', f"[{symbol}] close_position call completed")
                            break

                    # 🔥 WebSocket 기반 간격으로 대기
                    time.sleep(interval)

                except Exception as e:
                    self.log_event('monitor', f"[{symbol}] 모니터링 오류: {e}", level='ERROR')
                    time.sleep(1)

            self.log_event('monitor', f"[{symbol}] 실시간 모니터링 종료")
            try:
                self._log_trade_event('monitor', f"{symbol} 실시간 모니터링 종료")
            except Exception:
                pass

            # 🔥 모니터링 종료 (플래그는 모니터링 시작 시점에 이미 해제됨)

        except Exception as e:
            self.log_event('monitor', f"실시간 모니터링 시작 오류: {e}", level='ERROR')
            # 🔥 모니터링 예외 발생 시에도 플래그 해제 (모니터링 시작 시점에 이미 해제됨)

    def _check_ai_early_exit(self, position: Position, holding_time: float) -> Dict:
        """AI 기반 조기 청산 체크 (기존 시스템 스타일)"""
        try:
            symbol = position.symbol
            current_pnl = position.unrealized_pnl_percent

            # AI 설정에서 값 가져오기
            ai_settings = self.settings.get('ai_exit_settings', {})
            # 바이낸스 선물 수수료: 진입 0.02% + 청산 0.02% = 총 0.04%
            # 최소 수익: 0.20% (수수료 0.04% 제외 시 실제 수익 0.16%)
            # 설정은 비율(0.0020=0.20%), Position 값은 퍼센트 포인트
            # (0.20=0.20%)이므로 비교 전에 단위를 명시적으로 통일한다.
            min_profit = float(ai_settings.get('min_profit_for_exit', 0.0020)) * 100.0
            max_profit = float(ai_settings.get('max_profit_for_exit', 0.0030)) * 100.0
            min_loss = float(ai_settings.get('min_loss_for_exit', -0.01)) * 100.0
            max_loss = float(ai_settings.get('max_loss_for_exit', -0.0005)) * 100.0

            # 기존 시스템 스타일: AI 리스크 관리
            should_exit = False
            reason = ""

            # 1. 작은 손실이지만 추가 손실 방지
            if min_loss <= current_pnl <= max_loss and holding_time >= 2:  # 2분 이상 보유
                prevented_loss = abs(current_pnl) * 2  # 추가 손실 예상
                should_exit = True
                reason = f"AI risk management: early exit at {current_pnl:.4f}% " \
                        f"(prevented {prevented_loss:.4f}% additional loss), " \
                        f"PnL: {position.unrealized_pnl:.2f} USDT"

            # 2. 작은 수익 확보 (수수료 고려하여 최소 수익 보장)
            # 최소 보유 시간: 2분 (수수료 회수 시간 고려)
            elif min_profit <= current_pnl <= max_profit and holding_time >= 2:  # 2분 이상 보유
                should_exit = True
                reason = f"AI profit securing: quick profit at {current_pnl:.4f}% " \
                        f"(holding: {holding_time:.1f}min), " \
                        f"PnL: {position.unrealized_pnl:.2f} USDT"

            # 3. 트렌드 반전 감지 (가격 데이터 기반)
            elif len(self.price_data_points.get(symbol, [])) >= 5:
                recent_prices = [p['price'] for p in self.price_data_points[symbol][-5:]]
                price_trend = self._analyze_price_trend(recent_prices, position.side)

                if price_trend['reversal_detected'] and abs(current_pnl) > 0.03:
                    should_exit = True
                    reason = f"AI trend reversal: {price_trend['direction']} detected, " \
                            f"PnL: {position.unrealized_pnl:.2f} USDT"

            return {
                'should_exit': should_exit,
                'reason': reason,
                'holding_time': holding_time,
                'current_pnl': current_pnl
            }

        except Exception as e:
            self.logger.error(f"AI 조기 청산 체크 오류: {e}")
            return {'should_exit': False, 'reason': ''}

    def _analyze_price_trend(self, prices: List[float], position_side: PositionSide) -> Dict:
        """가격 트렌드 분석 (단순 구현)"""
        try:
            if len(prices) < 3:
                return {'reversal_detected': False, 'direction': 'UNKNOWN'}

            # 최근 3개 가격의 평균과 이전 2개 가격의 평균 비교
            recent_avg = sum(prices[-3:]) / 3
            previous_avg = sum(prices[-5:-2]) / 3

            change_rate = (recent_avg - previous_avg) / previous_avg

            # 임계값 0.05% 변화 감지
            if abs(change_rate) > 0.0005:
                if position_side == PositionSide.LONG and change_rate < -0.0005:
                    return {'reversal_detected': True, 'direction': 'DOWNWARD'}
                elif position_side == PositionSide.SHORT and change_rate > 0.0005:
                    return {'reversal_detected': True, 'direction': 'UPWARD'}

            return {'reversal_detected': False, 'direction': 'SIDEWAYS'}

        except Exception as e:
            self.logger.error(f"가격 트렌드 분석 오류: {e}")
            return {'reversal_detected': False, 'direction': 'ERROR'}

    def _determine_exit_reason(self, position: Position) -> str:
        """청산 이유 결정"""
        try:
            if position.tp_price and position.current_price >= position.tp_price:
                return "이익 목표 달성"
            elif position.sl_price and position.current_price <= position.sl_price:
                return "손실 제한 도달"
            elif position.unrealized_pnl_percent >= 0.15:
                return "수익률 기반 청산"
            elif position.unrealized_pnl_percent <= -0.20:
                return "손실률 기반 청산"
            else:
                return "자동청산"

        except Exception as e:
            self.logger.error(f"청산 이유 결정 오류: {e}")
            return "시스템 청산"
    def _calculate_dynamic_thresholds(self, symbol: str) -> Dict:
        """AI 기반 동적 임계값 계산 (프로그램 취지에 맞는 실시간 최적화)"""
        try:
            # 🔥 캐시 확인 (10분간 유효)
            import time
            current_time = time.time()
            cached = self.dynamic_thresholds_cache.get(symbol)
            if cached and (current_time - cached.get('timestamp', 0)) < 600:  # 10분
                return cached.get('thresholds', {})
            # 캐시 miss - optimizer 호출됨
            self.log_event('monitor', f"[{symbol}] 동적 임계값 계산: 캐시 미스 - optimizer 호출", level='INFO')

            # 🔥 AI 기반 최적화 (프로그램의 핵심 취지)
            # optimizer.py의 AI 캐싱 시스템을 활용한 실시간 최적화
            signal_data = {'symbol': symbol, 'confidence': 0.5}  # 기본 신호 데이터
            ai_result = self.optimizer.optimize_parameters(symbol, signal_data)

            # Optimizer는 {symbol: trade_cfg} 형태를 반환하며, trade_cfg에 'tp'/'sl' (소수)가 포함됨
            profit_threshold = float(self.settings.get('default_tp', 0.0018))
            loss_threshold = float(self.settings.get('default_sl', 0.002))
            if isinstance(ai_result, dict) and symbol in ai_result:
                trade_cfg = ai_result.get(symbol) or {}
                tp_val = trade_cfg.get('tp')
                sl_val = trade_cfg.get('sl')
                if isinstance(tp_val, (int, float)):
                    profit_threshold = float(tp_val)
                if isinstance(sl_val, (int, float)):
                    loss_threshold = float(sl_val)

            # 시장 변동성 계산 (AI 분석 보조 정보)
            volatility = self._calculate_market_volatility(symbol)

            # 최근 거래 패턴 기반 AI 보정
            pattern_adjustment = self._get_pattern_based_adjustment(symbol)
            tp_multiplier = pattern_adjustment.get('tp_multiplier', 1.0)
            sl_multiplier = pattern_adjustment.get('sl_multiplier', 1.0)

            # AI 최적화 결과에 패턴 보정 적용
            profit_threshold *= tp_multiplier
            loss_threshold *= sl_multiplier

            # 안전 범위 제한 (AI 결과 보호)
            profit_threshold = max(0.0005, min(profit_threshold, 0.01))  # 0.05% ~ 1%
            loss_threshold = max(0.0005, min(loss_threshold, 0.02))      # 0.05% ~ 2%

            thresholds = {
                'profit_threshold': profit_threshold,  # AI 최적화된 소수 단위
                'loss_threshold': loss_threshold,      # AI 최적화된 소수 단위
                'volatility': volatility,
                'tp_multiplier': tp_multiplier,
                'sl_multiplier': sl_multiplier,
                'ai_optimized': True  # AI 최적화 사용 표시
            }

            # 🔥 캐시에 저장
            self.dynamic_thresholds_cache[symbol] = {
                'thresholds': thresholds,
                'timestamp': current_time
            }

            return thresholds

        except Exception as e:
            self.logger.error(f"AI 동적 임계값 계산 오류: {e}")
            # 오류 시 기본값 반환 (소수 단위)
            return {
                'profit_threshold': self.settings.get('default_tp', 0.0018),
                'loss_threshold': self.settings.get('default_sl', 0.002),
                'volatility': 0.01,
                'tp_multiplier': 1.0,
                'sl_multiplier': 1.0,
                'ai_optimized': False  # AI 최적화 실패 표시
            }

    def close_position(self, position: Position, reason: str):
        """포지션 청산"""
        try:
            symbol = position.symbol
            if not is_noah_managed_position(position):
                self.log_event(
                    'trade',
                    f"[{symbol}] 수동/외부 포지션 보호: NoahAI 진입 원장이 없어 청산 차단",
                    level='WARNING',
                )
                return False
            self.log_event('trade', f"[{symbol}] close_position called with reason: {reason}")
            current_price = self.binance_client.get_current_price(symbol)
            self.log_event('trade', f"[{symbol}] Current price retrieved: {current_price}")

            # 실제 청산 주문 실행
            if position.side == PositionSide.LONG:
                order_result = self.binance_client.place_futures_order(
                    symbol=symbol,
                    side='SELL',
                    order_type='MARKET',
                    quantity=position.quantity,
                    reduce_only=True  # closePosition 대신 reduceOnly 사용
                )
            else:
                order_result = self.binance_client.place_futures_order(
                    symbol=symbol,
                    side='BUY',
                    order_type='MARKET',
                    quantity=position.quantity,
                    reduce_only=True  # closePosition 대신 reduceOnly 사용
                )

            # 🔥 주문 상태 확인 및 체결 대기 (execute_single_trade와 동일한 로직)
            if order_result and order_result.get('status') == 'NEW':
                self.log_event('trade', f"[{symbol}] ⏳ 청산 주문 체결 대기 중... (order_id: {order_result.get('order_id')})")
                
                # 최대 10초 동안 체결 대기
                for attempt in range(10):
                    time.sleep(1)
                    try:
                        order_status_check = self.binance_client.client.futures_get_order(
                            symbol=symbol,
                            orderId=order_result.get('order_id')
                        )
                        
                        if order_status_check.get('status') == 'FILLED':
                            self.log_event('trade', f"[{symbol}] ✅ 청산 주문 체결 완료!")
                            order_result['status'] = 'FILLED'
                            order_result['avg_price'] = float(order_status_check.get('avgPrice', 0))
                            order_result['executed_qty'] = float(order_status_check.get('executedQty', 0))
                            break
                        elif order_status_check.get('status') in ['CANCELED', 'REJECTED', 'EXPIRED']:
                            self.log_event('trade', f"[{symbol}] ❌ 청산 주문 취소/거부됨: {order_status_check.get('status')}", level='ERROR')
                            order_result['status'] = order_status_check.get('status')
                            break
                    except Exception as e:
                        self.log_event('trade', f"[{symbol}] ⚠️ 청산 주문 상태 확인 실패: {e}")
                
                if order_result.get('status') == 'NEW':
                    self.log_event('trade', f"[{symbol}] ⚠️ 청산 주문 체결 타임아웃 - 포지션 상태로 재확인", level='WARNING')
                    # 타임아웃 시 포지션 상태로 재확인
                    try:
                        position_info = self.binance_client.get_position_info(symbol)
                        if position_info:
                            position_amt = float(position_info.get('positionAmt', 0))
                            if abs(position_amt) < 1e-8:
                                # 포지션이 없으면 청산 성공으로 간주
                                self.log_event('trade', f"[{symbol}] ✅ 포지션 확인: 청산 완료 (포지션 수량: {position_amt})")
                                order_result['status'] = 'FILLED'
                                order_result['executed_qty'] = position.quantity
                            else:
                                self.log_event('trade', f"[{symbol}] ⚠️ 포지션 확인: 청산 미완료 (포지션 수량: {position_amt})", level='WARNING')
                    except Exception as pos_check_err:
                        self.log_event('trade', f"[{symbol}] ⚠️ 포지션 확인 실패: {pos_check_err}", level='WARNING')

            order_status = str(order_result.get('status', '')).upper() if order_result else 'UNKNOWN'
            executed_qty = None
            try:
                executed_qty = float(order_result.get('executed_qty', 0) or 0.0) if order_result else 0.0
            except (TypeError, ValueError):
                executed_qty = 0.0

            if hasattr(self.binance_client, 'is_order_success'):
                order_success = self.binance_client.is_order_success(order_result)
            else:
                order_success = bool(order_result and (
                    order_status == 'SUCCESS' or
                    order_status == 'FILLED' or
                    (order_status in {'PARTIALLY_FILLED', 'NEW', 'PENDING'} and executed_qty and executed_qty > 0)
                ))

            if order_success:
                exit_order_id = order_result.get('order_id') if isinstance(order_result, dict) else None
                exit_fee, exit_fee_asset, exit_fee_source = self._get_order_commission(
                    symbol, exit_order_id
                )
                self._record_binance_execution(
                    symbol,
                    'SELL' if position.side == PositionSide.LONG else 'BUY',
                    order_result,
                    source='noahai_exit_order',
                    fallback_quantity=position.quantity,
                    fallback_price=float(current_price or 0.0),
                    fee=exit_fee,
                    fee_asset=exit_fee_asset,
                )
                # PnL 계산
                pnl_percent = self._calc_pnl_percent(position, current_price)
                closed_at = utc_now()

                # 🔥 PnL USDT 계산 (통계용)
                pnl_usdt = (pnl_percent / 100.0) * position.quantity * position.entry_price

                # 거래 통계 업데이트
                self.trade_stats['total_trades'] += 1
                self.trade_stats['total_pnl'] += pnl_usdt  # 🔥 USDT 단위로 누적

                emit_kpi_event(
                    event_type='trade_order_executed',
                    category='trade',
                    asset_class='crypto',
                    status='success',
                    source='noahai_client_trader_close',
                    metric_value=float(position.quantity),
                    metadata={
                        'exchange': 'binance',
                        'symbol': symbol,
                        'quote_currency': 'USDT',
                        'side': 'CLOSE',
                        'close': True,
                        'reason': reason,
                        'executed_price': float(current_price or 0.0),
                        'notional_estimate': float(position.quantity) * float(current_price or 0.0),
                    },
                )
                if getattr(position, 'entry_time_source', 'execution') == 'execution':
                    emit_position_closed(
                        asset_class='crypto',
                        venue='binance',
                        symbol=symbol,
                        side=position.side.value,
                        opened_at=position.entry_time,
                        closed_at=closed_at,
                        entry_price=position.entry_price,
                        exit_price=float(current_price or 0.0),
                        closed_quantity=position.quantity,
                        close_reason=str(reason or 'auto_close'),
                        position_id=position.position_id,
                        exit_order_id=exit_order_id,
                        execution_mode='live',
                        source='noahai_client_trader_position',
                        gross_pnl=pnl_usdt,
                        net_pnl=pnl_usdt - float(exit_fee or 0.0),
                        fees=float(exit_fee or 0.0),
                        extra={
                            'leverage': int(position.leverage or 1),
                            'fee_asset': exit_fee_asset,
                            'fee_source': exit_fee_source,
                        },
                    )

                if pnl_percent > 0:
                    self.trade_stats['winning_trades'] += 1
                else:
                    self.trade_stats['losing_trades'] += 1

                # DB에 통계 저장
                if hasattr(self, 'recorder') and self.recorder:
                    self.recorder.save_exchange_trade_stats('binance', self.trade_stats)

                    # 개별 거래 로그 업데이트 (종료 정보)
                    try:
                        # datetime은 이미 모듈 레벨에서 임포트되어 있음 (Line 13)
                        exit_time = datetime.now()
                        pnl_usdt = pnl_percent * position.quantity * position.entry_price / 100  # 대략적 계산

                        self.log_event('debug', f"🔍 [DEBUG] close_position에서 update_trade_log 호출 전:")
                        self.log_event('debug', f"  - symbol: {symbol}")
                        self.log_event('debug', f"  - current_price: {current_price}")
                        self.log_event('debug', f"  - exit_time: {exit_time}")
                        self.log_event('debug', f"  - pnl_percent: {pnl_percent}")
                        self.log_event('debug', f"  - pnl_usdt: {pnl_usdt}")
                        self.log_event('debug', f"  - exit_reason: {reason}")
                        self.log_event('debug', f"  - position.entry_price: {position.entry_price}")
                        self.log_event('debug', f"  - position.quantity: {position.quantity}")
                        self.log_event('debug', f"  - position.side: {position.side}")

                        result = self.recorder.update_trade_log(
                            symbol=symbol,
                            exit_price=current_price,
                            exit_time=exit_time,
                            pnl_percent=pnl_percent,
                            pnl_usdt=pnl_usdt,
                            exit_reason=reason,
                            position=position,  # 🔥 position 객체 전달 (문제 1 해결)
                            additional_fees=exit_fee,
                            exit_order_id=str(exit_order_id) if exit_order_id is not None else None,
                            fee_asset=exit_fee_asset,
                            fee_source=exit_fee_source,
                        )

                        self.log_event('debug', f"🔍 [DEBUG] update_trade_log 결과: {result}")

                    except Exception as e:
                        self.log_event('error', f"개별 거래 로그 업데이트 실패: {e}", level='ERROR')
                        import traceback
                        self.log_event('error', f"상세 오류: {traceback.format_exc()}", level='ERROR')

                # 🔥 대시보드 업데이트 (문제 3, 4 해결)
                if self.dashboard:
                    try:
                        # 거래 통계 업데이트
                        if hasattr(self.dashboard, '_refresh_trading_summary'):
                            if hasattr(self.dashboard, 'after'):
                                self.dashboard.after(0, lambda: self.dashboard._refresh_trading_summary())
                            else:
                                self.dashboard._refresh_trading_summary()
                        
                        # 잔고 갱신 (즉시 + 지연 재갱신)
                        if hasattr(self.dashboard, 'update_balance_on_trade_completion'):
                            self.dashboard.update_balance_on_trade_completion()
                            
                            self._schedule_delayed_balance_update()
                    except Exception as e:
                        self.log_event('trade', f"대시보드 업데이트 실패: {e}", level='WARNING')

                # 포지션 제거
                if symbol in self.active_positions:
                    self.active_positions.pop(symbol, None)

                # 거래 진입 플래그 해제
                self.trade_entered[symbol] = False

                # 🔥 청산 직후 해당 심볼의 오픈오더 정리 (TP/SL 포함 모두)
                self.log_event('trade', f"[{symbol}] 🧹 청산 후 오픈오더 정리 시작...")
                try:
                    # 청산 직후에는 TP/SL 포함 모든 오픈오더 제거
                    open_orders = self.binance_client.get_open_orders(symbol)
                    if open_orders:
                        for order in open_orders:
                            try:
                                cancel_result = self.binance_client.client.futures_cancel_order(
                                    symbol=symbol,
                                    orderId=order['orderId']
                                )
                                self.log_event('trade', f"[{symbol}] 청산 후 주문 취소: {order['orderId']} ({order.get('type', 'UNKNOWN')})")
                            except Exception as cancel_err:
                                self.log_event('trade', f"[{symbol}] 주문 취소 실패: {order['orderId']} - {cancel_err}", level='WARNING')
                        self.log_event('trade', f"[{symbol}] ✅ 청산 후 오픈오더 정리 완료: {len(open_orders)}개")
                    else:
                        self.log_event('trade', f"[{symbol}] 청산 후 정리할 오픈오더 없음")
                except Exception as cleanup_error:
                    self.log_event('trade', f"[{symbol}] ⚠️ 청산 후 오픈오더 정리 실패: {cleanup_error}", level='WARNING')

                # 🔥 RiskManager에 거래 이력 업데이트 (패턴 분석용)
                if hasattr(self, 'risk_manager') and self.risk_manager:
                    try:
                        # datetime, timezone은 이미 모듈 레벨에서 임포트되어 있음 (Line 13)
                        entry_time = position.entry_time if hasattr(position, 'entry_time') else datetime.now(timezone.utc)
                        exit_time = datetime.now(timezone.utc)
                        holding_time_ms = _elapsed_milliseconds(entry_time) if isinstance(entry_time, datetime) else 0
                        
                        # 거래 결과 판단
                        trade_result = 'PROFIT' if pnl_percent > 0 else 'LOSS'
                        
                        # RiskManager에 거래 이력 저장
                        self.risk_manager.update_coin_trade_history(
                            symbol=symbol,
                            trade_result=trade_result,
                            profit_rate=pnl_percent,
                            entry_price=position.entry_price,
                            exit_price=current_price,
                            position_size=position.quantity * position.entry_price,
                            holding_time=holding_time_ms,
                            exchange='binance'
                        )
                        self.log_event('trade', f"[{symbol}] ✅ RiskManager 거래 이력 업데이트 완료: {trade_result}, PnL: {pnl_percent:.2f}%")
                    except Exception as rm_err:
                        self.log_event('trade', f"[{symbol}] ⚠️ RiskManager 거래 이력 업데이트 실패: {rm_err}", level='WARNING')

                # 청산 후 AI 분석 + XAI 저장
                try:
                    if pnl_percent > 0:
                        self._perform_profit_analysis_binance(symbol, position, current_price, pnl_percent, reason)
                    else:
                        self._perform_loss_analysis_binance(symbol, position, current_price, pnl_percent, reason)
                except Exception as ai_err:
                    self.log_event('trade', f"[{symbol}] ⚠️ 청산 AI 분석 실패: {ai_err}", level='WARNING')
                
                self.logger.info(f"✅ {symbol} 포지션 청산 완료: {reason}, PnL: {pnl_percent:.2f}%")
            else:
                emit_kpi_event(
                    event_type='trade_order_failed',
                    category='trade',
                    asset_class='crypto',
                    status='failed',
                    source='noahai_client_trader_close',
                    metadata={
                        'exchange': 'binance',
                        'symbol': symbol,
                        'side': 'CLOSE',
                        'close': True,
                        'reason': f"status={order_status}",
                    },
                )
                # 🔥 주문이 실패했지만 포지션이 실제로 청산되었는지 재확인
                self.log_event(
                    'trade',
                    f"[{symbol}] ⚠️ 청산 주문 미확정 - status={order_status}, executed_qty={executed_qty}",
                    level='WARNING'
                )
                
                # 포지션 상태로 재확인
                position_actually_closed = False
                try:
                    position_info = self.binance_client.get_position_info(symbol)
                    if position_info:
                        position_amt = float(position_info.get('positionAmt', 0))
                        if abs(position_amt) < 1e-8:
                            position_actually_closed = True
                            # 포지션이 없으면 청산 성공으로 간주 (주문은 실패했지만 실제로는 청산됨)
                            self.log_event('trade', f"[{symbol}] ✅ 포지션 확인: 청산 완료 (주문 상태는 실패했지만 포지션은 청산됨)")
                            
                            # PnL 계산 및 DB 저장 (정상 청산과 동일하게 처리)
                            pnl_percent = self._calc_pnl_percent(position, current_price)
                            pnl_usdt = (pnl_percent / 100.0) * position.quantity * position.entry_price
                            
                            # 거래 통계 업데이트
                            self.trade_stats['total_trades'] += 1
                            self.trade_stats['total_pnl'] += pnl_usdt
                            closed_at = utc_now()

                            emit_kpi_event(
                                event_type='trade_order_executed',
                                category='trade',
                                asset_class='crypto',
                                status='success',
                                source='noahai_client_trader_close',
                                metric_value=float(position.quantity),
                                metadata={
                                    'exchange': 'binance',
                                    'symbol': symbol,
                                    'quote_currency': 'USDT',
                                    'side': 'CLOSE',
                                    'close': True,
                                    'reason': f"{reason}_position_confirmed",
                                    'executed_price': float(current_price or 0.0),
                                    'notional_estimate': float(position.quantity) * float(current_price or 0.0),
                                },
                            )
                            if getattr(position, 'entry_time_source', 'execution') == 'execution':
                                emit_position_closed(
                                    asset_class='crypto',
                                    venue='binance',
                                    symbol=symbol,
                                    side=position.side.value,
                                    opened_at=position.entry_time,
                                    closed_at=closed_at,
                                    entry_price=position.entry_price,
                                    exit_price=float(current_price or 0.0),
                                    closed_quantity=position.quantity,
                                    close_reason=f"{reason}_position_confirmed",
                                    position_id=position.position_id,
                                    execution_mode='live',
                                    source='noahai_client_trader_position',
                                    gross_pnl=pnl_usdt,
                                    net_pnl=pnl_usdt,
                                    fees=0.0,
                                    extra={'leverage': int(position.leverage or 1)},
                                )
                            if pnl_percent > 0:
                                self.trade_stats['winning_trades'] += 1
                            else:
                                self.trade_stats['losing_trades'] += 1
                            
                            # DB에 통계 저장
                            if hasattr(self, 'recorder') and self.recorder:
                                self.recorder.save_exchange_trade_stats('binance', self.trade_stats)
                                
                                # 개별 거래 로그 업데이트
                                try:
                                    # datetime은 이미 모듈 레벨에서 임포트되어 있음 (Line 13)
                                    exit_time = datetime.now()
                                    pnl_usdt = pnl_percent * position.quantity * position.entry_price / 100
                                    
                                    result = self.recorder.update_trade_log(
                                        symbol=symbol,
                                        exit_price=current_price,
                                        exit_time=exit_time,
                                        pnl_percent=pnl_percent,
                                        pnl_usdt=pnl_usdt,
                                        exit_reason=reason,
                                        position=position  # 🔥 position 객체 전달 (문제 1 해결)
                                    )
                                    self.log_event('trade', f"[{symbol}] ✅ 포지션 확인 기반 DB 저장 완료: {result}")
                                except Exception as e:
                                    self.log_event('error', f"개별 거래 로그 업데이트 실패: {e}", level='ERROR')
                            
                            # 🔥 대시보드 업데이트 (문제 3, 4 해결)
                            if self.dashboard:
                                try:
                                    if hasattr(self.dashboard, '_refresh_trading_summary'):
                                        if hasattr(self.dashboard, 'after'):
                                            self.dashboard.after(0, lambda: self.dashboard._refresh_trading_summary())
                                        else:
                                            self.dashboard._refresh_trading_summary()
                                    
                                    if hasattr(self.dashboard, 'update_balance_on_trade_completion'):
                                        self.dashboard.update_balance_on_trade_completion()
                                        
                                        self._schedule_delayed_balance_update()
                                except Exception as e:
                                    self.log_event('trade', f"대시보드 업데이트 실패: {e}", level='WARNING')
                            
                            # 포지션 제거 및 플래그 해제
                            if symbol in self.active_positions:
                                self.active_positions.pop(symbol, None)
                            self.trade_entered[symbol] = False
                            
                            # 오픈오더 정리
                            try:
                                open_orders = self.binance_client.get_open_orders(symbol)
                                if open_orders:
                                    for order in open_orders:
                                        try:
                                            self.binance_client.client.futures_cancel_order(
                                                symbol=symbol,
                                                orderId=order['orderId']
                                            )
                                            self.log_event('trade', f"[{symbol}] 청산 후 주문 취소: {order['orderId']}")
                                        except Exception:
                                            pass
                                    self.log_event('trade', f"[{symbol}] ✅ 청산 후 오픈오더 정리 완료: {len(open_orders)}개")
                            except Exception:
                                pass
                            
                            # 🔥 RiskManager에 거래 이력 업데이트 (패턴 분석용)
                            if hasattr(self, 'risk_manager') and self.risk_manager:
                                try:
                                    # datetime, timezone은 이미 모듈 레벨에서 임포트되어 있음 (Line 13)
                                    entry_time = position.entry_time if hasattr(position, 'entry_time') else datetime.now(timezone.utc)
                                    exit_time = datetime.now(timezone.utc)
                                    holding_time_ms = _elapsed_milliseconds(entry_time) if isinstance(entry_time, datetime) else 0
                                    
                                    trade_result = 'PROFIT' if pnl_percent > 0 else 'LOSS'
                                    
                                    self.risk_manager.update_coin_trade_history(
                                        symbol=symbol,
                                        trade_result=trade_result,
                                        profit_rate=pnl_percent,
                                        entry_price=position.entry_price,
                                        exit_price=current_price,
                                        position_size=position.quantity * position.entry_price,
                                        holding_time=holding_time_ms,
                                        exchange='binance'
                                    )
                                    self.log_event('trade', f"[{symbol}] ✅ RiskManager 거래 이력 업데이트 완료 (포지션 확인 기반): {trade_result}, PnL: {pnl_percent:.2f}%")
                                except Exception as rm_err:
                                    self.log_event('trade', f"[{symbol}] ⚠️ RiskManager 거래 이력 업데이트 실패: {rm_err}", level='WARNING')

                            # 청산 후 AI 분석 + XAI 저장
                            try:
                                if pnl_percent > 0:
                                    self._perform_profit_analysis_binance(symbol, position, current_price, pnl_percent, reason)
                                else:
                                    self._perform_loss_analysis_binance(symbol, position, current_price, pnl_percent, reason)
                            except Exception as ai_err:
                                self.log_event('trade', f"[{symbol}] ⚠️ 청산 AI 분석 실패(포지션 확인 기반): {ai_err}", level='WARNING')
                            
                            self.logger.info(f"✅ {symbol} 포지션 청산 완료 (포지션 확인 기반): {reason}, PnL: {pnl_percent:.2f}%")
                        else:
                            self.log_event('trade', f"[{symbol}] ❌ 포지션 확인: 청산 실패 (포지션 수량: {position_amt})", level='ERROR')
                except Exception as pos_check_err:
                    self.log_event('trade', f"[{symbol}] ⚠️ 포지션 확인 실패: {pos_check_err}", level='WARNING')

        except Exception as e:
            self.logger.error(f"❌ {position.symbol} 포지션 청산 중 오류: {e}")

    def _save_ai_trade_analysis_binance(self, symbol: str, analysis: Dict[str, Any], analysis_type: str) -> None:
        """바이낸스 청산 AI 분석 결과를 Recorder에 저장"""
        try:
            if hasattr(self, 'recorder') and self.recorder:
                self.recorder.save_ai_trade_analysis(None, symbol, analysis, analysis_type)
        except Exception as e:
            self.log_event('trade', f"[{symbol}] AI 거래 분석 저장 실패: {e}", level='WARNING')

    def _perform_profit_analysis_binance(self, symbol: str, position: Position, exit_price: float, pnl_percent: float, reason: str) -> None:
        """바이낸스 익절 분석 + XAI 저장"""
        try:
            if (
                not hasattr(self, 'ai_manager')
                or not self.ai_manager
                or not getattr(
                    self.ai_manager,
                    'enabled_for_role',
                    lambda _role: self.ai_manager.enabled(),
                )('profit_analysis')
            ):
                return

            holding_minutes = 0.0
            try:
                holding_minutes = _elapsed_minutes(position.entry_time)
            except Exception:
                holding_minutes = 0.0

            profit_analysis_request = {
                'symbol': symbol,
                'exchange': 'binance',
                'side': position.side.value,
                'entry_price': position.entry_price,
                'exit_price': exit_price,
                'quantity': position.quantity,
                'pnl_percent': pnl_percent,
                'holding_time_minutes': holding_minutes,
                'leverage': getattr(position, 'leverage', 1),
                'reason': reason or '익절'
            }

            ai_result = self.ai_manager.analyze_profit_trade(symbol, profit_analysis_request)
            if ai_result:
                self._save_ai_trade_analysis_binance(symbol, ai_result, 'PROFIT')
                self.log_event('analysis', f"[{symbol}] 🎯 바이낸스 익절 AI 분석 저장 완료")
        except Exception as e:
            self.log_event('analysis', f"[{symbol}] 바이낸스 익절 AI 분석 오류: {e}", level='WARNING')

    def _perform_loss_analysis_binance(self, symbol: str, position: Position, exit_price: float, pnl_percent: float, reason: str) -> None:
        """바이낸스 손절 분석 + XAI 저장"""
        try:
            if (
                not hasattr(self, 'ai_manager')
                or not self.ai_manager
                or not getattr(
                    self.ai_manager,
                    'enabled_for_role',
                    lambda _role: self.ai_manager.enabled(),
                )('loss_analysis')
            ):
                return

            holding_minutes = 0.0
            try:
                holding_minutes = _elapsed_minutes(position.entry_time)
            except Exception:
                holding_minutes = 0.0

            loss_analysis_request = {
                'symbol': symbol,
                'exchange': 'binance',
                'side': position.side.value,
                'entry_price': position.entry_price,
                'exit_price': exit_price,
                'quantity': position.quantity,
                'pnl_percent': pnl_percent,
                'holding_time_minutes': holding_minutes,
                'leverage': getattr(position, 'leverage', 1),
                'reason': reason or '손절'
            }

            ai_result = self.ai_manager.analyze_loss_trade(symbol, loss_analysis_request)
            if ai_result:
                self._save_ai_trade_analysis_binance(symbol, ai_result, 'LOSS')
                self.log_event('analysis', f"[{symbol}] 🛑 바이낸스 손절 AI 분석 저장 완료")
        except Exception as e:
            self.log_event('analysis', f"[{symbol}] 바이낸스 손절 AI 분석 오류: {e}", level='WARNING')

    def _execute_paper_trade(self, symbol: str, trade_params: Dict[str, Any]):
        """실시간 시세를 사용하되 Binance 주문 API를 호출하지 않는 가상 진입."""
        try:
            if self._execution_mode() != ExecutionMode.PAPER:
                return False
            if symbol in self.paper_active_positions:
                return False
            if len(self.paper_active_positions) >= int(self.settings.get('max_positions', 3) or 3):
                return False

            price = float(
                trade_params.get('price')
                or trade_params.get('current_price')
                or self.binance_client.get_current_price(symbol)
                or 0.0
            )
            quantity = float(trade_params.get('qty', 0.0) or 0.0)
            if price <= 0 or quantity <= 0:
                self.log_event('trade', f"[{symbol}] PAPER 진입 실패 - 가격/수량 없음", level='WARNING')
                return False

            signal = str(trade_params.get('side') or trade_params.get('signal') or 'BUY').upper()
            side = PositionSide.SHORT if signal in {'SELL', 'SHORT'} else PositionSide.LONG
            tp = float(trade_params.get('tp', self.settings.get('default_tp', 0.0018)) or 0.0018)
            sl = float(trade_params.get('sl', self.settings.get('default_sl', 0.0020)) or 0.0020)
            tp_price = price * (1 + tp) if side == PositionSide.LONG else price * (1 - tp)
            sl_price = price * (1 - sl) if side == PositionSide.LONG else price * (1 + sl)
            opened_at = datetime.now(timezone.utc)
            position = Position(
                symbol=symbol,
                side=side,
                entry_price=price,
                current_price=price,
                quantity=quantity,
                leverage=max(1, int(trade_params.get('leverage', 1) or 1)),
                unrealized_pnl=0.0,
                unrealized_pnl_percent=0.0,
                entry_time=opened_at,
                tp_price=tp_price,
                sl_price=sl_price,
                execution_mode='paper',
                position_owner=NOAH_POSITION_OWNER,
                custom_strategy_id=trade_params.get('_selected_custom_strategy_id'),
                custom_strategy_name=trade_params.get('_selected_custom_strategy'),
                custom_strategy_rules=dict(trade_params.get('_custom_strategy_rules') or {}),
            )
            self.paper_active_positions[symbol] = position
            _, position.position_id = emit_position_opened(
                asset_class='crypto',
                venue='binance',
                symbol=symbol,
                side=position.side.value,
                opened_at=opened_at,
                entry_price=price,
                quantity=quantity,
                execution_mode='paper',
                source='noahai_client_binance_paper',
                extra={'leverage': position.leverage, 'simulated': True},
            )
            self.log_event(
                'trade',
                f"🧪 [PAPER] {symbol} {position.side.value} 가상 진입: {quantity} @ {price:.8f} "
                f"(TP {tp_price:.8f}, SL {sl_price:.8f})",
            )
            return {'status': 'PAPER_FILLED', 'simulated': True, 'symbol': symbol, 'price': price, 'quantity': quantity}
        except Exception as exc:
            self.log_event('trade', f"[{symbol}] PAPER 진입 오류: {exc}", level='ERROR')
            return False

    def _monitor_paper_positions(self) -> None:
        """가상 포지션을 현재가로 평가하고 TP/SL 도달 시 가상 청산한다."""
        for symbol, position in list(self.paper_active_positions.items()):
            try:
                current_price = float(self.binance_client.get_current_price(symbol) or 0.0)
                if current_price <= 0:
                    continue
                position.current_price = current_price
                direction = 1.0 if position.side == PositionSide.LONG else -1.0
                raw_return = ((current_price - position.entry_price) / position.entry_price) * direction
                pnl_usdt = (current_price - position.entry_price) * position.quantity * direction
                position.unrealized_pnl = pnl_usdt
                position.unrealized_pnl_percent = raw_return * 100.0 * max(1, position.leverage)
                tp_hit = current_price >= float(position.tp_price or 0.0) if position.side == PositionSide.LONG else current_price <= float(position.tp_price or 0.0)
                sl_hit = current_price <= float(position.sl_price or 0.0) if position.side == PositionSide.LONG else current_price >= float(position.sl_price or 0.0)
                if not (tp_hit or sl_hit):
                    continue

                self.paper_active_positions.pop(symbol, None)
                self.paper_trade_stats['total_trades'] += 1
                self.paper_trade_stats['total_pnl'] += pnl_usdt
                result_key = 'winning_trades' if pnl_usdt > 0 else 'losing_trades'
                self.paper_trade_stats[result_key] += 1
                emit_position_closed(
                    asset_class='crypto',
                    venue='binance',
                    symbol=symbol,
                    side=position.side.value,
                    opened_at=position.entry_time,
                    closed_at=utc_now(),
                    entry_price=position.entry_price,
                    exit_price=current_price,
                    closed_quantity=position.quantity,
                    close_reason='paper_tp' if tp_hit else 'paper_sl',
                    position_id=position.position_id,
                    execution_mode='paper',
                    source='noahai_client_binance_paper',
                    gross_pnl=pnl_usdt,
                    net_pnl=pnl_usdt,
                    extra={'simulated': True, 'leverage': position.leverage},
                )
                self.log_event(
                    'trade',
                    f"🧪 [PAPER] {symbol} 가상 청산 ({'TP' if tp_hit else 'SL'}): "
                    f"{current_price:.8f}, PnL {pnl_usdt:.4f} USDT",
                )
            except Exception as exc:
                self.log_event('trade', f"[{symbol}] PAPER 모니터링 오류: {exc}", level='WARNING')

    def get_active_positions(self) -> Dict[str, Position]:
        """활성 포지션 조회 (바이낸스용)"""
        if self._execution_mode() == ExecutionMode.PAPER:
            return self.paper_active_positions
        return self.active_positions

    def stop_trading(self):
        """바이낸스 거래 중지"""
        try:
            # 모든 모니터링 플래그 중지
            for symbol in list(self.monitoring_flags.keys()):
                if hasattr(self.monitoring_flags[symbol], 'set'):
                    self.monitoring_flags[symbol].set()

            # 모든 모니터링 스레드 종료 대기
            for symbol, thread in list(self.monitoring_threads.items()):
                if thread and thread.is_alive():
                    thread.join(timeout=5)

            # 모니터링 관련 데이터 정리
            self.monitoring_flags.clear()
            self.monitoring_threads.clear()

            if hasattr(self, 'logger') and self.logger:
                self.logger.info("⏹️ 바이낸스 거래 중지 완료")

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"❌ 바이낸스 거래 중지 실패: {e}")
            else:
                print(f"❌ 바이낸스 거래 중지 실패: {e}")

    def stop_trading_gracefully(self):
        """
        1) 신규 진입 차단
        2) 모든 실시간 모니터링 중지
        3) 열린 포지션/오더 정리(조건: 이미 모니터링 중이면 TP/SL 있나 확인, 없으면 지정가/시장가로 강제청산)
        4) 로컬 버퍼/통계 DB flush 보장
        5) 마지막으로 WebSocket 정리
        """
        try:
            self.log_event('system', "🔄 우아한 정지 시작...")

            # 1) 신규 진입 차단
            self.allow_new_entries = False  # 신규 진입 가드 (필요시 속성 추가)
            self.running = False            # 기존 running 플래그 병행

            # 2) 모든 실시간 모니터링 중지
            self.log_event('system', "🔄 실시간 모니터링 중지 중...")
            for symbol in list(self.monitoring_flags.keys()):
                if hasattr(self.monitoring_flags[symbol], 'set'):
                    self.monitoring_flags[symbol].set()
                    self.log_event('system', f"[{symbol}] 모니터링 중지 신호 전송")

            # 모든 모니터링 스레드 종료 대기
            for symbol, thread in list(self.monitoring_threads.items()):
                if thread and thread.is_alive():
                    self.log_event('system', f"[{symbol}] 모니터링 스레드 종료 대기 중...")
                    thread.join(timeout=5)
                    if thread.is_alive():
                        self.log_event('system', f"[{symbol}] ⚠️ 모니터링 스레드 종료 타임아웃", level='WARNING')
                    else:
                        self.log_event('system', f"[{symbol}] ✅ 모니터링 스레드 종료 완료")

            # 3) 포지션/오더 정리
            self.log_event('system', "🔄 포지션/오더 정리 시작...")
            self._close_all_positions_and_orders_blocking()

            # 4) DB flush (없다면 안전한 no-op 구현)
            self._flush_db_safe()

            self.log_event('system', "✅ 우아한 정지 완료")

        except Exception as e:
            self.log_event('system', f"❌ 우아한 정지 실패: {e}", level='ERROR')
            import traceback
            self.log_event('system', f"❌ 우아한 정지 실패 상세: {traceback.format_exc()}", level='ERROR')
        finally:
            # 5) WS 안전 종료 (아래 4항 참조)
            if hasattr(self.binance_client, "unsubscribe_all_safely"):
                self.binance_client.unsubscribe_all_safely()


    def _close_all_positions_and_orders_blocking(self):
        """모든 포지션과 오더 정리 (블로킹) - 폴백용"""
        try:
            positions = self.get_open_positions()  # List[Dict[str, Any]] 반환
            self.log_event('system', f"🔍 열린 포지션 조회: {len(positions)}개")
            
            if not positions:
                self.log_event('system', "✅ 열린 포지션 없음 - 정리 작업 완료")
                return
            
            for row in positions:
                symbol = row.get('symbol') if isinstance(row, dict) else None
                if not symbol:
                    continue
                
                # TP/SL 확인
                has_tp_sl = self._has_attached_tp_sl(symbol)
                self.log_event('system', f"[{symbol}] TP/SL 확인: {'있음' if has_tp_sl else '없음'}")
                
                # TP/SL 없는 포지션은 즉시 시장가 청산
                if not has_tp_sl:
                    self.log_event('system', f"[{symbol}] TP/SL 없음 - 시장가 청산 시작...")
                    tracked_position = self.active_positions.get(symbol)
                    if (
                        tracked_position is not None
                        and getattr(tracked_position, 'entry_time_source', 'execution') == 'execution'
                    ):
                        # 일반 청산과 같은 단일 경로를 사용해야 거래로그와 포지션 종료 KPI가 함께 남는다.
                        self.close_position(tracked_position, reason='graceful_stop')
                    else:
                        self.log_event(
                            'system',
                            f"[{symbol}] 수동/외부 포지션 보호 - 우아한 정지 자동청산 제외",
                            level='WARNING',
                        )
                else:
                    self.log_event('system', f"[{symbol}] ✅ TP/SL 정상 설정됨 - 포지션은 TP/SL 체결까지 유지 (정상 동작)")
                # TP/SL이 있으면 체결 대기/폴백 타임아웃 후 시장가 강제청산 로직도 가능

            # 열린 오더도 모두 취소
            self.log_event('system', "🔄 열린 오더 취소 시작...")
            self.cancel_all_open_orders()
            self.log_event('system', "✅ 포지션/오더 정리 완료")

        except Exception as e:
            self.log_event('system', f"❌ 포지션/오더 정리 실패: {e}", level='ERROR')
            import traceback
            self.log_event('system', f"❌ 포지션/오더 정리 실패 상세: {traceback.format_exc()}", level='ERROR')

    def _has_attached_tp_sl(self, symbol: str) -> bool:
        """TP/SL이 연결되어 있는지 확인 (Algo Order 포함)"""
        try:
            # 일반 주문 조회
            open_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)
            tp_orders = [o for o in open_orders if o.get('type') in ('TAKE_PROFIT', 'TAKE_PROFIT_MARKET')]
            sl_orders = [o for o in open_orders if o.get('type') in ('STOP', 'STOP_MARKET')]
            
            # Algo Order 조회 추가
            open_algo_orders = self.binance_client.get_open_algo_orders(symbol=symbol)
            for algo_order in open_algo_orders:
                # 🔥 Binance Algo Order API는 'type' 대신 'orderType' 필드 사용
                algo_type = (algo_order.get('orderType') or algo_order.get('type', '')).upper()
                if algo_type in ('TAKE_PROFIT_MARKET', 'TAKE_PROFIT'):
                    tp_orders.append(algo_order)
                elif algo_type in ('STOP_MARKET', 'STOP'):
                    sl_orders.append(algo_order)
            
            return len(tp_orders) > 0 and len(sl_orders) > 0
        except Exception:
            return False

    def _close_position_market(self, symbol: str):
        """시장가로 포지션 청산"""
        try:
            tracked = self.active_positions.get(symbol)
            if tracked is None or not is_noah_managed_position(tracked):
                self.logger.warning(f"{symbol} 수동/외부 포지션 보호 - 시장가 청산 차단")
                return False
            # 포지션 정보 조회
            position_info = self.binance_client.client.futures_position_information(symbol=symbol)
            if not position_info:
                return

            position = position_info[0]
            position_amt = float(position.get('positionAmt', 0))

            if abs(position_amt) == 0:
                return  # 포지션 없음

            # 시장가 청산 주문
            side = 'SELL' if position_amt > 0 else 'BUY'
            self.binance_client.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=abs(position_amt),
                reduceOnly=True
            )

            self.logger.info(f"✅ {symbol} 시장가 청산 주문 완료")

        except Exception as e:
            self.logger.error(f"❌ {symbol} 시장가 청산 실패: {e}")

    def cancel_all_open_orders(self):
        """모든 열린 오더 취소"""
        try:
            # 활성 포지션이 있는 심볼들의 오더만 취소
            for symbol in self.active_positions.keys():
                try:
                    self.binance_client.cancel_all_orders(symbol)
                    self.logger.info(f"✅ {symbol} 모든 오더 취소 완료")
                except Exception as e:
                    self.logger.error(f"❌ {symbol} 오더 취소 실패: {e}")
        except Exception as e:
            self.logger.error(f"❌ 오더 취소 실패: {e}")

    def _flush_db_safe(self):
        """DB flush 안전 장치"""
        try:
            if hasattr(self, "recorder") and hasattr(self.recorder, "flush_to_db"):
                self.recorder.flush_to_db()
                self.logger.info("✅ DB flush 완료")
            else:
                self.logger.warning("⚠️ recorder.flush_to_db 메서드 없음 - 건너뜀")
        except Exception as e:
            self.logger.warning(f"⚠️ flush_to_db 실패 (무시됨): {e}")
        try:
            if flush_kpi_events(timeout=5.0):
                self.logger.info("✅ KPI 이벤트 큐 flush 완료")
            else:
                self.logger.warning("⚠️ KPI 이벤트 큐 일부가 제한시간 안에 전송되지 못했습니다")
        except Exception as e:
            self.logger.warning(f"⚠️ KPI 이벤트 큐 flush 실패 (무시됨): {e}")

    def _compute_quantity_once(self, symbol: str, side: str, leverage: float, ref_price: float, risk_multiplier: float = 1.0):
        """수량 계산 단일화 (한 번만 계산하고 하위로 전달) - 정밀도 규칙 강화"""
        try:
            # 기존 로직 그대로 오지만, 이 함수만이 "단일 권위"
            # step_size 반올림 포함
            target_value = float(self.settings.get('min_trade_amount', 5.0) or 5.0)
            target_value *= max(0.01, min(float(risk_multiplier or 1.0), 1.0))

            # 심볼 정보 조회
            symbol_info = self.binance_client.get_symbol_info_direct(symbol)
            if not symbol_info:
                # 🔥 log_event로 통일 (일관성) - self.log_event는 클래스 내부에서 사용 가능
                self.log_event('trade', f"[{symbol}] ❌ _compute_quantity_once: 심볼 정보 조회 실패", level='ERROR')
                return None, None

            step_size = float(symbol_info.get('step_size', 0.001))
            qty_precision = int(symbol_info.get('qty_precision', 3))
            min_qty = float(symbol_info.get('min_qty', 0.001))

            # 목표 USDT 값으로 수량 계산
            quantity = target_value / ref_price

            # 🔥 min_notional 검증 및 보정 (2% 버퍼 적용)
            # get_symbol_info_direct는 'minNotional' (camelCase)로 반환하므로 둘 다 확인
            min_notional = symbol_info.get('minNotional') or symbol_info.get('min_notional')
            if min_notional is None or min_notional <= 0:
                # 🔥 Binance 선물 거래소는 대부분 20 USDT를 요구하므로 안전한 기본값 사용
                min_notional = 20.0
                self.logger.warning(f"[{symbol}] ⚠️ MIN_NOTIONAL API 조회 실패 - 안전한 기본값 사용: {min_notional} USDT")
            min_notional = float(min_notional)
            target_notional = min_notional * 1.02  # 2% 버퍼 (시장가 변동성 대응)

            actual_notional = quantity * ref_price

            if actual_notional < target_notional:
                # min_notional을 만족하도록 수량 증가 (올림 사용)
                required_qty = target_notional / ref_price
                if step_size > 0:
                    required_qty = math.ceil(required_qty / step_size) * step_size  # 🔥 ceil로 수량 증가
                quantity = max(quantity, required_qty)
                self.logger.info(f"[{symbol}] min_notional 보정: {actual_notional:.2f} < {target_notional:.2f} → {quantity} (notional: {quantity * ref_price:.2f})")

            # 🔥 정밀도 규칙 강화 - 반드시 step_size와 precision을 준수
            if step_size > 0:
                # step_size에 맞게 보정 (ceil로 올림하여 min_notional 보장)
                quantity = math.ceil(quantity / step_size) * step_size

            # min_qty 보장
            quantity = max(quantity, min_qty)

            # 🔥 quantity_precision 자리수로 강제 포맷팅
            quantity = float(f"{quantity:.{qty_precision}f}")

            # 🔥 최종 검증 - min_notional 재확인
            final_notional = quantity * ref_price
            if final_notional < min_notional:
                # 최종 수량이 min_notional 미만이면 다시 상향 조정
                required_qty = min_notional / ref_price
                if step_size > 0:
                    required_qty = math.ceil(required_qty / step_size) * step_size
                quantity = max(quantity, required_qty)
                quantity = float(f"{quantity:.{qty_precision}f}")
                self.logger.warning(f"[{symbol}] 🔥 최종 수량 재보정: {final_notional:.2f} < {min_notional} → {quantity * ref_price:.2f} USDT")

            self.logger.info(f"[{symbol}] 수량 계산 단일화: {target_value:.2f} USDT → {quantity} (stepSize: {step_size}, precision: {qty_precision}, minQty: {min_qty}, minNotional: {min_notional})")
            return quantity, ref_price

        except Exception as e:
            # 🔥 log_event로 통일 (일관성) + 상세 정보 추가
            import traceback
            self.log_event('trade', f"[{symbol}] ❌ _compute_quantity_once 예외 발생: {e}", level='ERROR')
            self.log_event('trade', f"[{symbol}] 🔍 _compute_quantity_once 예외 상세: {traceback.format_exc()}", level='ERROR')
            return None, None

    def _calc_pnl_percent(self, position: Position, exit_price: float) -> float:
        """PnL 퍼센트 계산"""
        try:
            if position.side == PositionSide.LONG:
                return ((exit_price - position.entry_price) / position.entry_price) * 100
            else:  # SHORT
                return ((position.entry_price - exit_price) / position.entry_price) * 100
        except Exception:
            return 0.0

    def _load_trade_stats_from_db(self):
        """DB에서 바이낸스 거래 통계 로드 (문서 기준: 바이낸스는 Trader에서 관리)"""
        try:
            if hasattr(self, 'recorder') and self.recorder:
                # recorder를 통해 DB에서 바이낸스 거래 통계 로드
                db_stats = self.recorder.load_exchange_trade_stats('binance')
                if db_stats:
                    # DB 통계를 현재 trade_stats에 업데이트
                    self.trade_stats.update(db_stats)
                    if hasattr(self, 'logger') and self.logger:
                        self.logger.info(f"✅ 바이낸스 거래 통계 DB 로드 완료: {db_stats.get('total_trades', 0)}건")
                else:
                    if hasattr(self, 'logger') and self.logger:
                        self.logger.info("📊 바이낸스 거래 통계 DB에서 로드할 데이터 없음")
            else:
                if hasattr(self, 'logger') and self.logger:
                    self.logger.warning("⚠️ recorder가 없어 바이낸스 거래 통계 DB 로드 불가")
        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"❌ 바이낸스 거래 통계 DB 로드 실패: {e}")
            else:
                print(f"❌ 바이낸스 거래 통계 DB 로드 실패: {e}")

    def _restore_positions_from_exchange(self):
        """실제 바이낸스 포지션 중 NoahAI 진입 원장과 일치하는 것만 복구."""
        try:
            if self._execution_mode() != ExecutionMode.LIVE:
                self.log_event('system', f"🧪 {self._execution_mode().value} 모드 - 실제 포지션 복구 차단")
                return
            if hasattr(self, 'binance_client') and self.binance_client:
                # 실제 거래소에서 포지션 조회
                actual_positions = self.binance_client.get_positions()

                getter = getattr(self.recorder, 'get_open_managed_trades', None)
                rows = getter('binance') if callable(getter) else []
                managed = managed_trade_map(rows or [])
                self.external_position_symbols = set()
                restored_count = 0
                for pos in actual_positions or []:
                    symbol = str(pos.symbol)
                    row = managed.get(normalize_position_symbol(symbol))
                    if row is None:
                        self.external_position_symbols.add(symbol)
                        continue
                    position = Position(
                        symbol=symbol,
                        side=PositionSide.LONG if pos.side == "LONG" else PositionSide.SHORT,
                        quantity=float(pos.size),
                        entry_price=float(pos.entry_price or row.get('entry_price') or 0.0),
                        current_price=float(pos.mark_price or 0.0),
                        unrealized_pnl=float(pos.unrealized_pnl or 0.0),
                        unrealized_pnl_percent=0.0,
                        entry_time=parse_entry_time(row.get('entry_time')),
                        leverage=int(pos.leverage or row.get('leverage') or 1),
                        tp_price=float(row.get('tp_price') or 0.0) or None,
                        sl_price=float(row.get('sl_price') or 0.0) or None,
                        position_id=str(row.get('id') or ''),
                        entry_order_id=str(row.get('order_id') or ''),
                        entry_order_ids=list(row.get('_entry_order_ids') or []),
                        entry_time_source="execution",
                        execution_mode=str(row.get('execution_mode') or 'live'),
                        position_owner=NOAH_POSITION_OWNER,
                    )
                    self.calculate_pnl(position)
                    self.active_positions[symbol] = position
                    restored_count += 1
                if hasattr(self, 'logger') and self.logger:
                    self.logger.info(
                        f"✅ 바이낸스 소유권 대조 복구: NoahAI {restored_count}개, "
                        f"수동/외부 {len(self.external_position_symbols)}개(자동청산 제외)"
                    )
            else:
                if hasattr(self, 'logger') and self.logger:
                    self.logger.warning("⚠️ binance_client가 없어 포지션 복구 불가")
        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"❌ 바이낸스 포지션 복구 실패: {e}")
            else:
                print(f"❌ 바이낸스 포지션 복구 실패: {e}")

    def _auto_adjust_threshold_from_performance(self):
        """🤖 AI 기반 신호 기준 자동 조절 (OpenAI API 활용)"""
        try:
            # 1. 필수 요소 체크
            if not self.risk_manager or not self.analyzer or not self.ai_manager:
                return

            # 2. AI Manager 활성화 체크
            if not getattr(
                self.ai_manager,
                'enabled_for_role',
                lambda _role: self.ai_manager.enabled(),
            )('parameter_optimization'):
                self.logger.warning("⚠️ AI Manager 비활성화 상태 - 자동 조절 생략")
                return

            # 3. 거래 데이터 수집 (메모리 + DB)
            all_trades = []
            # 🔥 RiskManager 메모리 이력
            for coin_trades in self.risk_manager.coin_trade_history.values():
                all_trades.extend(coin_trades)
            
            # 🔥 DB 이력 보완 (메모리 이력이 부족한 경우)
            if hasattr(self, 'recorder') and self.recorder and len(all_trades) < 10:
                try:
                    # 모든 코인의 DB 거래 이력 조회
                    memory_timestamps = {t.get('timestamp') for t in all_trades if t.get('timestamp')}
                    for coin in self.risk_manager.coin_trade_history.keys():
                        db_trades = self.recorder.get_recent_trades(coin=coin, exchange='binance', days=30)
                        for trade in db_trades:
                            if trade.get('exit_time') not in memory_timestamps:
                                pnl_percent = float(trade.get('pnl_percent', 0) or 0)
                                all_trades.append({
                                    'result': 'PROFIT' if pnl_percent > 0 else 'LOSS',
                                    'profit': pnl_percent,
                                    'profit_rate': pnl_percent,
                                    'timestamp': trade.get('exit_time')
                                })
                except Exception as db_err:
                    self.logger.warning(f"DB 거래 이력 조회 실패: {db_err}")

            total_count = len(all_trades)

            # 4. 최소 거래 수 체크 (10거래 미만은 학습 부족)
            if total_count < 10:
                return

            # 5. 조절 빈도 제어 (5거래마다 한 번씩만)
            if not hasattr(self, '_last_adjust_count'):
                self._last_adjust_count = 0

            if total_count - self._last_adjust_count < 5:
                return

            # 6. 거래 성과 분석
            context = self._collect_trading_context_for_ai(all_trades)

            # 성공 여부와 무관하게 같은 거래 표본은 한 번만 요청한다.
            # 응답 오류 때 매 거래 사이클마다 재호출되는 비용 폭주를 막는다.
            self._last_adjust_count = total_count

            # 7. AI에게 최적값 질문
            ai_result = self._ask_ai_for_optimal_threshold(context)

            if not ai_result:
                self.logger.warning("⚠️ AI 응답 없음 - 조절 생략")
                return

            # 8. AI 추천값 적용
            self._apply_ai_threshold_recommendation(ai_result, context)

        except Exception as e:
            self.logger.error(f"AI 자동 조절 오류: {e}")

    def _collect_trading_context_for_ai(self, all_trades: list) -> dict:
        """AI에게 전달할 거래 상황 데이터 수집"""
        try:
            # 최근 30거래 분석
            recent = all_trades[-30:] if len(all_trades) >= 30 else all_trades
            wins = [t for t in recent if t.get('result') == 'PROFIT']
            losses = [t for t in recent if t.get('result') == 'LOSS']

            # 수익/손실 계산
            total_profit = sum(t.get('profit', 0) for t in wins)
            total_loss = sum(abs(t.get('profit', 0)) for t in losses)
            avg_profit = total_profit / len(wins) if wins else 0
            avg_loss = total_loss / len(losses) if losses else 0

            # 시장 변동성 (BTCUSDT 기준)
            try:
                volatility = self._calculate_market_volatility('BTCUSDT')
            except:
                volatility = 0.01

            # 7개 주요 수치 모두 context에 포함
            thresholds = self.settings.get('signal_thresholds', {})
            return {
                'total_trades': len(all_trades),
                'recent_trades': len(recent),
                'win_count': len(wins),
                'loss_count': len(losses),
                'win_rate': (len(wins) / len(recent) * 100) if recent else 0,
                'avg_profit_percent': avg_profit,
                'avg_loss_percent': avg_loss,
                'profit_loss_ratio': (avg_profit / avg_loss) if avg_loss > 0 else 0,
                'user_signal_threshold': self.analyzer.get_user_signal_threshold(),
                'rsi_extreme_oversold': thresholds.get('rsi_extreme_oversold'),
                'rsi_oversold': thresholds.get('rsi_oversold'),
                'rsi_overbought': thresholds.get('rsi_overbought'),
                'rsi_extreme_overbought': thresholds.get('rsi_extreme_overbought'),
                'momentum_threshold': thresholds.get('momentum_threshold'),
                'trend_momentum_threshold': thresholds.get('trend_momentum_threshold'),
                'market_volatility': volatility,
                'consecutive_losses': getattr(self.risk_manager, 'consecutive_losses', 0)
            }
        except Exception as e:
            self.logger.error(f"거래 상황 수집 오류: {e}")
            return {}

    def _ask_ai_for_optimal_threshold(self, context: dict) -> Optional[dict]:
        """AI에게 최적 threshold 질문"""
        try:
            system_prompt = "You are an expert cryptocurrency trading system optimizer. Analyze trading performance and recommend optimal values for all key signal/analysis thresholds."

            # context 안전 접근 (KeyError 방지)
            c = context or {}
            user_prompt = f"""
Analyze the current trading performance and recommend optimal values for the following 7 key thresholds:
- user_signal_threshold (30~90): 신호 민감도, 높을수록 보수적
- rsi_extreme_oversold (10~30): 극단적 과매도 RSI, 낮을수록 신호 적게 발생
- rsi_oversold (15~40): 과매도 RSI, 낮을수록 신호 적게 발생
- rsi_overbought (60~90): 과매수 RSI, 높을수록 신호 적게 발생
- rsi_extreme_overbought (70~95): 극단적 과매수 RSI, 높을수록 신호 적게 발생
- momentum_threshold (0.0005~0.01): 모멘텀 임계값, 높을수록 신호 적게 발생
- trend_momentum_threshold (0.001~0.02): 트렌드 모멘텀 임계값, 높을수록 신호 적게 발생

Current Trading Data:
- Total Trades: {c.get('total_trades', 0)}
- Recent 30 Trades: {c.get('recent_trades', 0)}
- Win Rate: {c.get('win_rate', 0):.1f}%
- Wins/Losses: {c.get('win_count', 0)}/{c.get('loss_count', 0)}
- Average Profit: {c.get('avg_profit_percent', 0):.2f}%
- Average Loss: {c.get('avg_loss_percent', 0):.2f}%
- Profit/Loss Ratio: {c.get('profit_loss_ratio', 0):.2f}
- Market Volatility: {c.get('market_volatility', 0):.2%}
- Consecutive Losses: {c.get('consecutive_losses', 0)}

Current Thresholds:
- user_signal_threshold: {c.get('user_signal_threshold', 'N/A')}
- rsi_extreme_oversold: {c.get('rsi_extreme_oversold', 'N/A')}
- rsi_oversold: {c.get('rsi_oversold', 'N/A')}
- rsi_overbought: {c.get('rsi_overbought', 'N/A')}
- rsi_extreme_overbought: {c.get('rsi_extreme_overbought', 'N/A')}
- momentum_threshold: {c.get('momentum_threshold', 'N/A')}
- trend_momentum_threshold: {c.get('trend_momentum_threshold', 'N/A')}

Guidelines:
- If win rate < 50% OR profit/loss ratio < 1.0 OR consecutive losses > 3 → make thresholds more conservative.
- If win rate ≥ 60% AND profit/loss ratio ≥ 1.2 → you can make thresholds slightly more aggressive.
- All values must be within the ranges above.

You MUST respond with valid JSON only (no markdown, no additional text). Do not wrap in code fences. Do not add any explanation outside JSON.
Use Korean for \"reasoning\" and \"expected_outcome\".
Keep \"reasoning\" within 3-5 sentences and \"expected_outcome\" within 2-3 sentences.

Response in JSON format:
{{
    "user_signal_threshold": integer (30-90),
    "rsi_extreme_oversold": integer (10-30),
    "rsi_oversold": integer (15-40),
    "rsi_overbought": integer (60-90),
    "rsi_extreme_overbought": integer (70-95),
    "momentum_threshold": float (0.0005-0.01),
    "trend_momentum_threshold": float (0.001-0.02),
    "reasoning": "한국어 3~5문장",
    "expected_outcome": "한국어 2~3문장",
    "risk_level": "LOW" | "MEDIUM" | "HIGH",
    "adjustment_type": "AGGRESSIVE" | "MODERATE" | "CONSERVATIVE" | "MAINTAIN"
}}
"""

            # AI에게 질문
            role_call = getattr(self.ai_manager, 'chat_json_for_role', None)
            if callable(role_call):
                result = role_call(
                    'parameter_optimization',
                    system_prompt,
                    user_prompt,
                    temperature=0.3,
                    max_tokens=512,
                )
            else:
                result = self.ai_manager.client.chat_json(
                    system=system_prompt,
                    user=user_prompt,
                    temperature=0.3,
                    max_tokens=512
                )

            return result

        except Exception as e:
            self.logger.error(f"AI 질문 오류: {e}")
            return None

    def _apply_ai_threshold_recommendation(self, ai_result: dict, context: dict):
        """AI 추천값을 시스템에 적용"""
        try:
            # AI 응답이 dict가 아니면 무시
            if not isinstance(ai_result, dict):
                self.logger.warning("⚠️ AI 응답이 JSON dict 형식이 아님 - 조절 생략")
                return

            # 클램프 함수 정의
            def _clamp(val, lo, hi):
                try:
                    return max(lo, min(val, hi))
                except Exception:
                    return lo

            # 7개 주요 수치 모두 적용
            keys = [
                'user_signal_threshold',
                'rsi_extreme_oversold',
                'rsi_oversold',
                'rsi_overbought',
                'rsi_extreme_overbought',
                'momentum_threshold',
                'trend_momentum_threshold'
            ]
            # 각 키별 범위
            key_ranges = {
                'user_signal_threshold': (30, 90),
                'rsi_extreme_oversold': (10, 30),
                'rsi_oversold': (15, 40),
                'rsi_overbought': (60, 90),
                'rsi_extreme_overbought': (70, 95),
                'momentum_threshold': (0.0005, 0.01),
                'trend_momentum_threshold': (0.001, 0.02)
            }
            changed = False
            for key in keys:
                new_val = ai_result.get(key)
                if new_val is not None:
                    lo, hi = key_ranges[key]
                    # float/int 변환 및 클램프
                    if key in ['momentum_threshold', 'trend_momentum_threshold']:
                        try:
                            new_val = float(new_val)
                        except Exception:
                            continue
                        new_val = _clamp(new_val, lo, hi)
                    else:
                        try:
                            new_val = int(new_val)
                        except Exception:
                            continue
                        new_val = _clamp(new_val, lo, hi)
                    # 기존값과 다르면 적용
                    if key == 'user_signal_threshold':
                        cur_val = context.get('user_signal_threshold')
                        if new_val != cur_val:
                            self.analyzer.set_user_signal_threshold(new_val)
                            # analyzer_settings 안에 저장
                            if 'analyzer_settings' not in self.settings:
                                self.settings['analyzer_settings'] = {}
                            self.settings['analyzer_settings']['user_signal_threshold'] = new_val
                            changed = True
                    else:
                        # signal_thresholds dict에 반영
                        if 'signal_thresholds' not in self.settings:
                            self.settings['signal_thresholds'] = {}
                        cur_val = self.settings['signal_thresholds'].get(key)
                        if new_val != cur_val:
                            self.settings['signal_thresholds'][key] = new_val
                            changed = True

            if changed:
                from config.settings import save_settings
                save_settings(self.settings)

            # context 안전 접근
            c = context or {}
            # 상세 로그 출력
            self.logger.info(f"""
╔══════════════════════════════════════════════════════════════╗
║           🤖 AI 기반 신호/분석 기준 자동 조절 완료           ║
╠══════════════════════════════════════════════════════════════╣
║ [AI 추천값]
║ user_signal_threshold: {ai_result.get('user_signal_threshold', 'N/A')}
║ rsi_extreme_oversold: {ai_result.get('rsi_extreme_oversold', 'N/A')}
║ rsi_oversold: {ai_result.get('rsi_oversold', 'N/A')}
║ rsi_overbought: {ai_result.get('rsi_overbought', 'N/A')}
║ rsi_extreme_overbought: {ai_result.get('rsi_extreme_overbought', 'N/A')}
║ momentum_threshold: {ai_result.get('momentum_threshold', 'N/A')}
║ trend_momentum_threshold: {ai_result.get('trend_momentum_threshold', 'N/A')}
║
║ [거래 성과]
║ - 총 거래: {c.get('total_trades', 0)}회
║ - 승률: {c.get('win_rate', 0):.1f}%
║ - 손익비: {c.get('profit_loss_ratio', 0):.2f}
║ - 연속 손실: {c.get('consecutive_losses', 0)}회
║
║ [AI 분석]
║ {ai_result.get('reasoning', 'N/A')}
║
║ [예상 효과]
║ {ai_result.get('expected_outcome', 'N/A')}
╚══════════════════════════════════════════════════════════════╝
            """)

        except Exception as e:
            self.logger.error(f"AI 추천값 적용 오류: {e}")

    def _generate_ai_learning_data(self, exchange_name: str, symbol: str, signal_data: Dict[str, Any]):
        """AI 학습 데이터 생성 (바이낸스용)"""
        try:
            # datetime, timezone은 이미 모듈 레벨에서 임포트되어 있음 (Line 13)
            perf = self._collect_symbol_performance_snapshot(symbol=symbol, exchange_name=exchange_name)

            # 학습 데이터 생성
            learning_data = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'exchange': exchange_name,
                'symbol': symbol,
                'signal': signal_data.get('signal', 'HOLD'),
                'confidence': signal_data.get('confidence', 0.0),
                'reason': signal_data.get('reason', ''),
                'market_volatility': signal_data.get('market_volatility', 0.0),
                'trend_strength': signal_data.get('trend_strength', 0.0),
                'entry_price': signal_data.get('entry_price', 0.0),
                'tp_percent': signal_data.get('tp_percent', 0.0),
                'sl_percent': signal_data.get('sl_percent', 0.0),
                'leverage': signal_data.get('leverage', 1.0),
                'source': 'analyzer_cycle',
                'signal_source': signal_data.get('_signal_source', 'noah_base'),
                'custom_signal_mode': signal_data.get('_custom_signal_mode', 'none'),
                'custom_operation_mode': signal_data.get('_custom_operation_mode', 'standard'),
                'selected_custom_strategy': signal_data.get('_selected_custom_strategy'),
                'selected_custom_strategy_id': signal_data.get('_selected_custom_strategy_id'),
                'selected_custom_strategy_key': signal_data.get('_selected_custom_strategy_key'),
                'selected_custom_strategy_version_id': signal_data.get('_selected_custom_strategy_version_id'),
                'trade_candidate': dict(signal_data.get('_trade_candidate') or {}),
                'recent_win_rate': perf.get('recent_win_rate', 0.0),
                'recent_loss_rate': perf.get('recent_loss_rate', 0.0),
                'recent_trade_count': perf.get('recent_trade_count', 0),
            }

            # AI 학습 데이터 저장: 거래소별 학습 매니저로 직접 기록
            try:
                from .exchange_learning_manager import ExchangeLearningManager
                if self._learning_manager is None:
                    self._learning_manager = ExchangeLearningManager(exchange_name)
                elm = self._learning_manager
                elm.add_learning_data(learning_data)
            except Exception:
                # 조용히 패스(학습 저장 실패가 거래 흐름을 막지 않도록)
                pass

        except Exception as e:
            # 조용히 패스(학습 데이터 생성 실패가 거래 흐름을 막지 않도록)
            pass

    def _get_dynamic_entry_thresholds(self, symbol: str, market_conditions: Dict) -> Dict:
        """시장 상황 기반 동적 진입 임계값 계산 (바이낸스용) - AI 학습 기반"""
        try:
            base_thresholds = {
                'max_loss_rate': 50.0,
                'min_trades_history': 0,
                'min_ai_confidence': 0.4,
            }

            # AI 학습 데이터 기반 임계값 계산
            learned_thresholds = self._get_ai_learned_thresholds(symbol)
            if learned_thresholds:
                learned_thresholds['_source'] = 'learning_store'
                learned_thresholds['_base'] = dict(base_thresholds)
                return learned_thresholds

            # 시장 변동성 기반 조정 (AI가 학습할 기준점)
            volatility = market_conditions.get('volatility', 0.01)

            if volatility > 0.02:  # 높은 변동성 (AI 학습 기준점)
                return {
                    'max_loss_rate': base_thresholds['max_loss_rate'] * 0.8,  # AI가 학습할 조정 계수
                    'min_trades_history': base_thresholds['min_trades_history'],
                    'min_ai_confidence': min(0.8, base_thresholds['min_ai_confidence'] * 1.5),
                    '_source': 'market_base',
                    '_base': dict(base_thresholds),
                }
            elif volatility > 0.01:  # 중간 변동성 (AI 학습 기준점)
                return {
                    'max_loss_rate': base_thresholds['max_loss_rate'] * 0.9,  # AI가 학습할 조정 계수
                    'min_trades_history': base_thresholds['min_trades_history'],
                    'min_ai_confidence': min(0.7, base_thresholds['min_ai_confidence'] * 1.25),
                    '_source': 'market_base',
                    '_base': dict(base_thresholds),
                }
            else:  # 낮은 변동성 (AI 학습 기준점)
                return {
                    'max_loss_rate': base_thresholds['max_loss_rate'] * 1.2,  # AI가 학습할 조정 계수
                    'min_trades_history': base_thresholds['min_trades_history'],
                    'min_ai_confidence': max(0.2, base_thresholds['min_ai_confidence'] * 0.75),
                    '_source': 'market_base',
                    '_base': dict(base_thresholds),
                }

        except Exception as e:
            # 오류 시 기본값 반환
            return {
                'max_loss_rate': 50.0,
                'min_trades_history': 0,
                'min_ai_confidence': 0.4,
                '_source': 'fallback',
                '_base': {'max_loss_rate': 50.0, 'min_trades_history': 0, 'min_ai_confidence': 0.4},
            }

    def _get_ai_learned_thresholds(self, symbol: str) -> Optional[Dict]:
        """AI 학습 데이터 기반 임계값 계산(저장된 learning_data 단일 소스)."""
        try:
            entries = self._get_recent_learning_entries(symbol=symbol, exchange_name='binance', limit=80)
            if len(entries) < 10:
                return None

            win_rates = []
            conf_values = []
            observed_trade_counts = []
            for item in entries:
                try:
                    recent_trade_count = max(0, int(item.get('recent_trade_count', 0) or 0))
                except Exception:
                    recent_trade_count = 0
                observed_trade_counts.append(recent_trade_count)
                try:
                    if recent_trade_count > 0:
                        win_rates.append(float(item.get('recent_win_rate', 0.0) or 0.0))
                except Exception:
                    pass
                try:
                    conf_values.append(float(item.get('confidence', 0.0) or 0.0))
                except Exception:
                    pass

            avg_conf = max(0.2, min(0.9, (sum(conf_values) / len(conf_values)) if conf_values else 0.5))
            min_ai_conf = max(0.25, min(0.75, avg_conf - 0.05))
            if win_rates:
                avg_win_rate = max(0.0, min(1.0, sum(win_rates) / len(win_rates)))
                max_loss = max(35.0, min(65.0, 60.0 - (avg_win_rate * 30.0)))
                target_min_trades = 3 if len(entries) >= 30 else 5
                min_trades = min(target_min_trades, max(observed_trade_counts or [0]))
            else:
                avg_win_rate = 0.0
                max_loss = 60.0
                min_trades = 0

            self.logger.info(
                f"[{symbol}] 학습저장소 임계값 반영: n={len(entries)}, "
                f"closed_samples={max(observed_trade_counts or [0])}, "
                f"avg_win={avg_win_rate*100:.1f}%, avg_conf={avg_conf:.2f}"
            )
            return {
                'max_loss_rate': max_loss,
                'min_trades_history': min_trades,
                'min_ai_confidence': min_ai_conf,
            }

            return None  # 학습 데이터 부족

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"AI 학습 임계값 계산 오류: {e}")
            return None

    def _collect_symbol_performance_snapshot(self, symbol: str, exchange_name: str) -> Dict[str, Any]:
        """학습데이터 저장 시점의 최근 성과 스냅샷을 수집한다."""
        try:
            coin = str(symbol or '').replace('USDT', '')
            rows = []
            if self.recorder and hasattr(self.recorder, 'get_recent_trades'):
                rows = self.recorder.get_recent_trades(coin=coin, exchange=exchange_name, days=30) or []
            if not isinstance(rows, list) or not rows:
                return {'recent_win_rate': 0.0, 'recent_loss_rate': 0.0, 'recent_trade_count': 0}

            win = 0
            loss = 0
            total = 0
            for row in rows[-50:]:
                if not isinstance(row, dict):
                    continue
                pnl = float(row.get('pnl_percent', row.get('pnl', 0.0)) or 0.0)
                total += 1
                if pnl > 0:
                    win += 1
                elif pnl < 0:
                    loss += 1
            if total == 0:
                return {'recent_win_rate': 0.0, 'recent_loss_rate': 0.0, 'recent_trade_count': 0}
            return {
                'recent_win_rate': win / total,
                'recent_loss_rate': loss / total,
                'recent_trade_count': total,
            }
        except Exception:
            return {'recent_win_rate': 0.0, 'recent_loss_rate': 0.0, 'recent_trade_count': 0}

    def _get_recent_learning_entries(self, symbol: str, exchange_name: str, limit: int = 80) -> List[Dict[str, Any]]:
        """저장된 learning_data에서 심볼 기준 최근 항목을 읽는다."""
        try:
            from .exchange_learning_manager import ExchangeLearningManager
            if self._learning_manager is None:
                self._learning_manager = ExchangeLearningManager(exchange_name)
            history = list(getattr(self._learning_manager, 'learning_history', []) or [])
            target = str(symbol or '').upper()
            filtered = [
                h for h in history
                if isinstance(h, dict) and str(h.get('symbol', '')).upper() == target
            ]
            return filtered[-max(1, int(limit)):]
        except Exception:
            return []

    def _calculate_market_volatility(self, symbol: str) -> float:
        """시장 변동성 계산 (바이낸스용)"""
        try:
            # settings.json에서 변동성 계산 설정 읽기
            volatility_settings = self.settings.get('volatility_calculation', {
                'timeframe': '1h',
                'periods': 24,
                'default_volatility': 0.01
            })

            # 최근 가격 데이터로 변동성 계산
            klines = []
            try:
                if hasattr(self, 'binance_client') and self.binance_client:
                    klines = self.binance_client.get_klines(
                        symbol,
                        interval=volatility_settings['timeframe'],
                        limit=volatility_settings['periods']
                    )
            except Exception:
                pass

            if not klines or len(klines) < volatility_settings['periods']:
                return volatility_settings['default_volatility']

            # 가격 변화율 계산
            prices = [kline_number(k, "close") for k in klines]
            price_changes = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]

            # 변동성 (표준편차)
            import statistics
            volatility = statistics.stdev(price_changes)

            return float(volatility)

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"변동성 계산 오류: {e}")
            # settings.json에서 기본값 읽기
            volatility_settings = self.settings.get('volatility_calculation', {
                'default_volatility': 0.01
            })
            return volatility_settings['default_volatility']

    def _get_pattern_based_adjustment(self, symbol: str) -> Dict:
        """최근 거래 패턴 기반 임계값 조정 (바이낸스용)"""
        try:
            # settings.json에서 패턴 분석 설정 읽기
            pattern_settings = self.settings.get('pattern_analysis', {
                'analysis_periods': 20,
                'analysis_days': 30,
                'high_win_rate_threshold': 0.7,
                'low_win_rate_threshold': 0.3,
                'high_win_rate_multipliers': {
                    'tp_multiplier': 1.2,
                    'sl_multiplier': 0.8
                },
                'low_win_rate_multipliers': {
                    'tp_multiplier': 0.8,
                    'sl_multiplier': 1.2
                }
            })

            # 최근 거래 분석
            coin = symbol.replace('USDT', '')
            recent_trades = []

            if hasattr(self, 'recorder') and self.recorder:
                try:
                    method = getattr(self.recorder, 'get_recent_trades', None)
                    if callable(method):
                        rt = method(coin=coin, exchange='binance', days=pattern_settings['analysis_days'])
                        recent_trades = rt if isinstance(rt, list) else []
                    else:
                        symbol_full = f"{coin}USDT"
                        rt = self.recorder.get_trade_history(symbol=symbol_full, days=pattern_settings['analysis_days'])
                        recent_trades = rt if isinstance(rt, list) else []
                except Exception:
                    recent_trades = []

            if len(recent_trades) < pattern_settings['analysis_periods']:
                return {'tp_multiplier': 1.0, 'sl_multiplier': 1.0}

            # 승률 계산
            wins = sum(1 for t in recent_trades if t.get('pnl', 0) > 0)
            win_rate = wins / len(recent_trades)

            # 평균 수익률 계산
            avg_profit = sum(t.get('pnl', 0) for t in recent_trades if t.get('pnl', 0) > 0)
            avg_profit = avg_profit / max(wins, 1)

            # 패턴 기반 조정 계수
            tp_multiplier = 1.0
            sl_multiplier = 1.0

            if win_rate > pattern_settings['high_win_rate_threshold']:
                # 높은 승률
                tp_multiplier = pattern_settings['high_win_rate_multipliers']['tp_multiplier']
                sl_multiplier = pattern_settings['high_win_rate_multipliers']['sl_multiplier']
            elif win_rate < pattern_settings['low_win_rate_threshold']:
                # 낮은 승률
                tp_multiplier = pattern_settings['low_win_rate_multipliers']['tp_multiplier']
                sl_multiplier = pattern_settings['low_win_rate_multipliers']['sl_multiplier']

            return {
                'tp_multiplier': tp_multiplier,
                'sl_multiplier': sl_multiplier,
                'win_rate': win_rate,
                'avg_profit': avg_profit
            }

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"패턴 기반 조정 계산 오류: {e}")
            return {'tp_multiplier': 1.0, 'sl_multiplier': 1.0}
    
    def _save_tp_sl_watchdog_backup(self):
        """TP/SL watchdog 상태를 파일로 백업"""
        if not hasattr(self, 'tp_sl_watchdog_backup_path') or not self.tp_sl_watchdog_backup_path:
            return
        
        try:
            import json
            import os
            
            # 상태 데이터 준비 (timestamp는 float이므로 JSON 직렬화 가능)
            backup_data = {
                'version': '1.0',
                'timestamp': time.time(),
                'state': self.tp_sl_watchdog_state.copy()
            }
            
            # 임시 파일에 먼저 저장 (원자성 보장)
            temp_path = self.tp_sl_watchdog_backup_path + '.tmp'
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            
            # 원자적 교체
            if os.path.exists(self.tp_sl_watchdog_backup_path):
                os.replace(temp_path, self.tp_sl_watchdog_backup_path)
            else:
                os.rename(temp_path, self.tp_sl_watchdog_backup_path)
            
            self.log_event('system', f"✅ TP/SL watchdog 상태 백업 완료: {len(self.tp_sl_watchdog_state)}개 심볼")
        except Exception as e:
            self.log_event('system', f"⚠️ TP/SL watchdog 상태 백업 실패: {e}", level='WARNING')
    
    def _load_tp_sl_watchdog_backup(self):
        """TP/SL watchdog 상태를 파일에서 복원"""
        if not hasattr(self, 'tp_sl_watchdog_backup_path') or not self.tp_sl_watchdog_backup_path:
            return
        
        try:
            import json
            import os
            
            if not os.path.exists(self.tp_sl_watchdog_backup_path):
                return  # 백업 파일이 없으면 무시
            
            with open(self.tp_sl_watchdog_backup_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            # 상태 복원 (타임스탬프는 유지)
            if 'state' in backup_data:
                self.tp_sl_watchdog_state = backup_data['state']
                self.log_event('system', f"✅ TP/SL watchdog 상태 복원 완료: {len(self.tp_sl_watchdog_state)}개 심볼")
        except Exception as e:
            self.log_event('system', f"⚠️ TP/SL watchdog 상태 복원 실패: {e}", level='WARNING')
