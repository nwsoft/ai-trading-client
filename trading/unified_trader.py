#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
다중 거래소 통합 거래 시스템
기존 Trader 클래스의 모든 기능을 다중 거래소에 적용
"""

import time
import logging
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
import threading
import math
import os
import csv
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple, cast
from dataclasses import dataclass
from enum import Enum

from .trader import Position, PositionSide, TradeSignal
from .analyzer import Analyzer
from .optimizer import Optimizer
from .recorder import Recorder
from .ai.ai_manager import AIManager
from .risk_manager import RiskManager
from .advanced_orders import AdvancedOrderManager
from .exchange_manager import ExchangeManager
from .unified_trading_manager import UnifiedTradingManager
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
from .selection_policy import (
    SelectionPolicy,
    combine_selection_paths,
    select_advanced_strategy_universe,
)
from .exit_policy import (
    build_exit_policy,
    format_exit_policy,
    record_insurance_submission,
)
from .execution_mode import ExecutionMode, resolve_crypto_execution_mode
from .leverage_policy import exchange_leverage_cap, resolve_effective_leverage
from .order_command_policy import classify_order_error, exchange_client_order_id
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

class UnifiedTrader:
    # 정적 분석기(Pylance) 인지를 위한 클래스 레벨 속성 선언
    main_app: Optional[Any] = None

    def set_main_app(self, main_app: Any) -> None:
        """메인 애플리케이션 참조를 설정 (정적 분석기 호환용 명시적 세터)"""
        try:
            self.main_app = main_app
        except Exception:
            # 방어적: 어떤 예외도 상향 전파하지 않음
            pass
    def _is_verbose_logging(self) -> bool:
        try:
            return bool(self.settings.get('verbose_trade_logging', False))
        except Exception:
            return False

    def _log_trade_event(self, category: str, message: str, exchange: str, level: str = 'INFO', verbose_only: bool = False):
        try:
            if verbose_only and not self._is_verbose_logging():
                return
            # 파일 로깅
            if hasattr(self, 'logger') and self.logger:
                if level == 'ERROR':
                    self.logger.error(message)
                elif level == 'WARNING':
                    self.logger.warning(message)
                else:
                    self.logger.info(message)
            # 대시보드 스트림
            try:
                from log_system.log_stream import get_log_stream
                stream = get_log_stream()
                stream.add_event(exchange, level, category, message)
            except Exception:
                pass
        except Exception:
            pass
    def _get_ai_max_positions(self, exchange_name: str) -> int:
        """Return the configured per-exchange cap, never more than three."""
        try:
            overrides = dict(
                ((self.settings or {}).get('exchange_risk_overrides', {}) or {}).get(
                    str(exchange_name or '').lower(), {}
                ) or {}
            )
            raw = overrides.get('max_positions', (self.settings or {}).get('max_positions', 3))
            return max(1, min(3, int(raw or 3)))
        except (TypeError, ValueError, AttributeError):
            return 3

    def _get_rr_guardrail_config(self) -> Dict[str, Any]:
        """RR 하한 가드레일 설정을 안전하게 조회합니다."""
        default_cfg = {
            'enabled': True,
            'min_rr_ratio': 2.0,
            'strict': True,
            'adaptive': {
                'enabled': True,
                'rr_min': 1.8,
                'rr_max': 2.2,
                'volatility_low': 0.01,
                'volatility_high': 0.02,
                'update_interval_seconds': 21600,
                'hysteresis': 0.10,
                'rollback_mdd_delta': 20.0,
            },
        }
        try:
            cfg = self.settings.get('rr_guardrail', {}) if isinstance(self.settings, dict) else {}
            if not isinstance(cfg, dict):
                cfg = {}
            enabled = bool(cfg.get('enabled', default_cfg['enabled']))
            min_rr = float(cfg.get('min_rr_ratio', default_cfg['min_rr_ratio']) or default_cfg['min_rr_ratio'])
            strict = bool(cfg.get('strict', default_cfg['strict']))
            if min_rr <= 0:
                min_rr = default_cfg['min_rr_ratio']

            adaptive_cfg = cfg.get('adaptive', {})
            if not isinstance(adaptive_cfg, dict):
                adaptive_cfg = {}

            default_adaptive = cast(Dict[str, Any], default_cfg['adaptive'])
            rr_min = float(adaptive_cfg.get('rr_min', default_adaptive['rr_min']) or default_adaptive['rr_min'])
            rr_max = float(adaptive_cfg.get('rr_max', default_adaptive['rr_max']) or default_adaptive['rr_max'])
            if rr_min > rr_max:
                rr_min, rr_max = rr_max, rr_min

            adaptive = {
                'enabled': bool(adaptive_cfg.get('enabled', default_adaptive['enabled'])),
                'rr_min': max(1.0, rr_min),
                'rr_max': max(1.0, rr_max),
                'volatility_low': max(0.0, float(adaptive_cfg.get('volatility_low', default_adaptive['volatility_low']) or default_adaptive['volatility_low'])),
                'volatility_high': max(0.0, float(adaptive_cfg.get('volatility_high', default_adaptive['volatility_high']) or default_adaptive['volatility_high'])),
                'update_interval_seconds': max(300, int(adaptive_cfg.get('update_interval_seconds', default_adaptive['update_interval_seconds']) or default_adaptive['update_interval_seconds'])),
                'hysteresis': max(0.0, float(adaptive_cfg.get('hysteresis', default_adaptive['hysteresis']) or default_adaptive['hysteresis'])),
                'rollback_mdd_delta': max(0.0, float(adaptive_cfg.get('rollback_mdd_delta', default_adaptive['rollback_mdd_delta']) or default_adaptive['rollback_mdd_delta'])),
            }

            if adaptive['volatility_low'] > adaptive['volatility_high']:
                adaptive['volatility_low'], adaptive['volatility_high'] = adaptive['volatility_high'], adaptive['volatility_low']

            return {
                'enabled': enabled,
                'min_rr_ratio': min_rr,
                'strict': strict,
                'adaptive': adaptive,
            }
        except Exception:
            return default_cfg

    def _estimate_recent_mdd_unified(self, exchange_name: str, symbol: str, days: int = 7) -> float:
        """최근 거래 기록 기반 MDD(금액 단위) 추정치."""
        try:
            if not hasattr(self, 'recorder') or not self.recorder:
                return 0.0

            trades: List[Dict[str, Any]] = []
            method = getattr(self.recorder, 'get_recent_trades', None)
            if callable(method):
                rt = method(symbol=symbol, exchange=exchange_name, days=days)
                if isinstance(rt, list):
                    trades = [t for t in rt if isinstance(t, dict)]

            if not trades:
                return 0.0

            equity = 0.0
            peak = 0.0
            max_drawdown = 0.0
            for tr in trades:
                pnl = float(tr.get('pnl', 0.0) or 0.0)
                equity += pnl
                if equity > peak:
                    peak = equity
                drawdown = peak - equity
                if drawdown > max_drawdown:
                    max_drawdown = drawdown

            return float(max_drawdown)
        except Exception:
            return 0.0

    def _resolve_adaptive_min_rr(
        self,
        exchange_name: str,
        symbol: str,
        base_min_rr: float,
        market_volatility: Optional[float] = None,
    ) -> Dict[str, Any]:
        """제한 자율 RR(1.8~2.2) 적용값을 계산합니다."""
        cfg = self._get_rr_guardrail_config()
        adaptive = cast(Dict[str, Any], cfg.get('adaptive', {}))
        if not adaptive.get('enabled', False):
            return {
                'effective_min_rr': float(base_min_rr),
                'adaptive_enabled': False,
                'reason': 'adaptive_disabled',
                'candidate_rr': float(base_min_rr),
            }

        key = f"{exchange_name}:{symbol}"
        now_ts = time.time()
        state = self._rr_adaptive_state.get(key, {}) if isinstance(self._rr_adaptive_state, dict) else {}

        # 업데이트 간격 내에는 기존 RR 유지
        if state:
            last_update = float(state.get('last_update_ts', 0.0) or 0.0)
            if (now_ts - last_update) < float(adaptive.get('update_interval_seconds', 21600)):
                hold_rr = float(state.get('last_rr', base_min_rr) or base_min_rr)
                return {
                    'effective_min_rr': hold_rr,
                    'adaptive_enabled': True,
                    'reason': 'interval_hold',
                    'candidate_rr': hold_rr,
                }

        rr_min = float(adaptive.get('rr_min', 1.8) or 1.8)
        rr_max = float(adaptive.get('rr_max', 2.2) or 2.2)
        vol_low = float(adaptive.get('volatility_low', 0.01) or 0.01)
        vol_high = float(adaptive.get('volatility_high', 0.02) or 0.02)
        hysteresis = float(adaptive.get('hysteresis', 0.10) or 0.10)
        rollback_mdd_delta = float(adaptive.get('rollback_mdd_delta', 20.0) or 20.0)

        vol = float(market_volatility if market_volatility is not None else 0.01)
        if vol_high <= vol_low:
            candidate = max(rr_min, min(base_min_rr, rr_max))
        elif vol <= vol_low:
            candidate = rr_min
        elif vol >= vol_high:
            candidate = rr_max
        else:
            # 저변동(완화)~고변동(강화) 구간을 선형 매핑
            ratio = (vol - vol_low) / max((vol_high - vol_low), 1e-12)
            candidate = rr_min + (rr_max - rr_min) * ratio

        candidate = max(rr_min, min(candidate, rr_max))
        reason = 'adaptive_volatility'

        last_rr = float(state.get('last_rr', base_min_rr) or base_min_rr) if state else float(base_min_rr)
        if state and abs(candidate - last_rr) < hysteresis:
            candidate = last_rr
            reason = 'hysteresis_hold'

        current_mdd = self._estimate_recent_mdd_unified(exchange_name, symbol, days=7)
        last_mdd = float(state.get('last_mdd', current_mdd) or current_mdd) if state else current_mdd

        # RR 하향 조정 시 MDD가 악화되면 롤백(최소 base 이상)
        if state and candidate < last_rr and current_mdd > (last_mdd + rollback_mdd_delta):
            candidate = max(float(base_min_rr), last_rr)
            reason = 'rollback_guard_mdd'

        self._rr_adaptive_state[key] = {
            'last_update_ts': now_ts,
            'last_rr': float(candidate),
            'last_mdd': float(current_mdd),
        }

        return {
            'effective_min_rr': float(candidate),
            'adaptive_enabled': True,
            'reason': reason,
            'candidate_rr': float(candidate),
        }

    def _enforce_rr_floor(
        self,
        tp: float,
        sl: float,
        *,
        min_tp: float,
        max_tp: float,
        min_sl: float,
        max_sl: float,
        exchange_name: str = '',
        symbol: str = '',
        market_volatility: Optional[float] = None,
        context: str = ''
    ) -> Dict[str, Any]:
        """TP/SL 값에 RR 하한(기본 2:1)을 적용합니다."""
        cfg = self._get_rr_guardrail_config()
        eps = 1e-12

        safe_tp = max(min_tp, min(float(tp or 0.0), max_tp))
        safe_sl = max(min_sl, min(float(sl or 0.0), max_sl))
        rr_before = safe_tp / max(safe_sl, eps)

        if not cfg['enabled']:
            return {
                'tp': safe_tp,
                'sl': safe_sl,
                'rr_before': rr_before,
                'rr_after': rr_before,
                'applied': False,
                'passed': True,
                'enabled': False,
                'strict': cfg['strict'],
                'min_rr_ratio': cfg['min_rr_ratio'],
                'reason': 'disabled',
            }

        base_min_rr = float(cfg['min_rr_ratio'])
        adaptive_rr = self._resolve_adaptive_min_rr(
            exchange_name=exchange_name,
            symbol=symbol,
            base_min_rr=base_min_rr,
            market_volatility=market_volatility,
        )
        min_rr = float(adaptive_rr.get('effective_min_rr', base_min_rr) or base_min_rr)

        if rr_before >= min_rr:
            return {
                'tp': safe_tp,
                'sl': safe_sl,
                'rr_before': rr_before,
                'rr_after': rr_before,
                'applied': False,
                'passed': True,
                'enabled': True,
                'strict': cfg['strict'],
                'configured_min_rr_ratio': base_min_rr,
                'min_rr_ratio': min_rr,
                'adaptive_enabled': adaptive_rr.get('adaptive_enabled', False),
                'adaptive_reason': adaptive_rr.get('reason', 'n/a'),
                'reason': 'already_satisfied',
            }

        # 1차: 손절 폭 축소로 RR 보정
        target_sl = safe_tp / min_rr
        adj_sl = max(min_sl, min(target_sl, max_sl))
        adj_tp = safe_tp

        # 2차: 손절 축소만으로 부족하면 익절 폭 확대 시도
        if (adj_tp / max(adj_sl, eps)) < min_rr:
            target_tp = adj_sl * min_rr
            adj_tp = max(min_tp, min(target_tp, max_tp))

        rr_after = adj_tp / max(adj_sl, eps)
        passed = rr_after >= min_rr

        if (not passed) and cfg['strict'] and hasattr(self, 'logger') and self.logger:
            self.logger.warning(
                f"RR 가드레일 미충족({context}): before={rr_before:.3f}, after={rr_after:.3f}, min={min_rr:.3f}"
            )

        return {
            'tp': adj_tp,
            'sl': adj_sl,
            'rr_before': rr_before,
            'rr_after': rr_after,
            'applied': True,
            'passed': passed,
            'enabled': True,
            'strict': cfg['strict'],
            'configured_min_rr_ratio': base_min_rr,
            'min_rr_ratio': min_rr,
            'adaptive_enabled': adaptive_rr.get('adaptive_enabled', False),
            'adaptive_reason': adaptive_rr.get('reason', 'n/a'),
            'reason': 'adjusted',
        }

    def _normalize_symbol_for_adapter(self, exchange_client, symbol: str) -> str:
        """거래소 어댑터별 심볼 정규화 (각 어댑터에서 처리하므로 기본 반환)"""
        if not symbol:
            return ''
        # 🔥 각 어댑터에서 심볼 정규화를 처리하므로 여기서는 기본 반환
        return str(symbol).strip().upper()

    def _lookup_order_by_client_id(
        self, exchange_name: str, exchange_client: Any, symbol: str, client_order_id: str,
    ) -> Optional[Dict[str, Any]]:
        """모호한 응답 뒤 재제출 전에 거래소의 client-order ID로 조회한다."""
        try:
            normalized = str(exchange_name or '').lower()
            if normalized == 'binance':
                native = getattr(exchange_client, 'client', None)
                getter = getattr(native, 'futures_get_order', None)
                if callable(getter):
                    return dict(getter(symbol=symbol, origClientOrderId=client_order_id) or {})
                return None

            ccxt_exchange = getattr(exchange_client, 'exchange', None)
            if ccxt_exchange is None:
                return None
            normalized_symbol = symbol
            normalizer = getattr(exchange_client, '_normalize_symbol', None)
            if callable(normalizer):
                normalized_symbol = normalizer(symbol)

            if normalized == 'bybit':
                getter = getattr(ccxt_exchange, 'privateGetV5OrderRealtime', None)
                if not callable(getter):
                    return None
                response = getter({
                    'category': 'linear',
                    'symbol': str(normalized_symbol).replace('/', '').split(':', 1)[0],
                    'orderLinkId': client_order_id,
                })
                rows = ((response or {}).get('result') or {}).get('list') or []
                if not rows:
                    return None
                row = dict(rows[0])
                return {
                    'status': row.get('orderStatus'),
                    'order_id': row.get('orderId'),
                    'filled': row.get('cumExecQty'),
                    'average': row.get('avgPrice'),
                    'raw_result': row,
                }
            if normalized == 'okx':
                return dict(ccxt_exchange.fetch_order(
                    None, normalized_symbol, {'clOrdId': client_order_id}
                ) or {})
            if normalized == 'bitget':
                return dict(ccxt_exchange.fetch_order(
                    None, normalized_symbol, {'clientOid': client_order_id}
                ) or {})
            if normalized == 'upbit':
                getter = getattr(ccxt_exchange, 'privateGetOrder', None)
                if not callable(getter):
                    return None
                response = getter({'identifier': client_order_id})
                parser = getattr(ccxt_exchange, 'parse_order', None)
                return dict(parser(response) if callable(parser) else response or {})
        except Exception as exc:
            self.logger.warning(
                f"{exchange_name} {symbol} client-order ID 조정 조회 실패: {exc}"
            )
        return None

    def __init__(self, settings: Dict[str, Any], exchange_manager: ExchangeManager,
        unified_manager: UnifiedTradingManager, analyzer: Optional[Analyzer] = None,
        optimizer: Optional[Optimizer] = None, recorder: Optional[Recorder] = None,
        ai_manager: Optional[AIManager] = None, risk_manager: Optional[RiskManager] = None,
        websocket_manager=None, dashboard=None, logger=None, main_app: Optional[Any] = None):
        self.settings = settings
        self.exchange_manager = exchange_manager  # 바이낸스용
        self.unified_manager = unified_manager    # CCXT 거래소용
        self.current_exchange = settings.get('selected_exchange', 'bybit')
        self.analyzer = analyzer
        self.optimizer = optimizer
        self.recorder = recorder
        self.ai_manager = ai_manager
        self.risk_manager = risk_manager
        self.websocket_manager = websocket_manager
        self.dashboard = dashboard
        self.evaluator = None
        # 🔥 main_app 참조 추가 (NoahAIClient 인스턴스를 담기 위한 속성)
        self.main_app: Optional[Any] = main_app
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
        self.active_positions = {}  # 실제 포지션 {exchange: {symbol: Position}}
        self.paper_positions = {}  # 가상 포지션 {exchange: {symbol: Position}}
        self.external_position_symbols: Dict[str, set[str]] = {}
        self.last_trade_decisions: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.last_effective_trade_params: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._close_failure_fingerprints: Dict[str, str] = {}
        self._close_retry_state: Dict[str, Dict[str, Any]] = {}
        self._entry_halts: Dict[str, Dict[str, Any]] = {}
        self.monitoring_flags = {}  # {exchange: bool}
        self.monitoring_threads = {}  # {exchange: Thread}
        self.advanced_order_managers = {}
        # 거래소별 TP/SL 지원 여부 캐시: {'okx': True/False, 'bybit': True/False, ...}
        self._tp_sl_support_cache = {}
        self.monitoring_interval = int(self.settings.get("auto_trade_interval", 10))
        self.price_data_points = {}  # {exchange: {symbol: List}}
        self.ai_optimization_cache = {}  # {exchange: {symbol: Dict}}
        self.pattern_analysis_cache = {}  # {exchange: {symbol: Dict}}
        self._rr_adaptive_state: Dict[str, Dict[str, Any]] = {}
        self.trade_stats = {}  # {exchange: {'total_trades': 0, 'profitable_trades': 0, 'total_pnl': 0.0}}
        self.paper_trade_stats = {}  # PAPER 전용 통계(DB·실거래 통계와 분리)
        self.selected_coins = {}  # {exchange: List[Dict]}
        self.trading_cycles = {}  # {exchange: bool}
        self.trade_entered = {}  # {exchange: {symbol: bool}}
        self._learning_managers = {}  # {exchange: ExchangeLearningManager}
        self.strategy_customizer = None
        self.ai_trading_chatbot = None
        self._runtime_profile_applied = None
        self.position_sizing_snapshots = {}
        self.portfolio_allocation_cache = {}
        self.cycle_execution_metrics = {}
        self.last_market_analysis_time_by_exchange: Dict[str, float] = {}
        self.last_market_regime_by_exchange: Dict[str, str] = {}
        self.enabled_exchanges = self._compute_enabled_exchanges()
        self.trade_enabled_exchanges = self._compute_trade_enabled_exchanges()
        self.learning_enabled_exchanges = self._compute_learning_enabled_exchanges()
        self._initialized_exchanges = set()
        self._runtime_execution_sync_state: Dict[str, float] = {}
        self._runtime_receipt_sync_state: Dict[str, float] = {}
        self._runtime_execution_sync_failures: Dict[str, int] = {}
        try:
            self._winrate_window = max(1, int(self.settings.get('risk_winrate_window', 10)))
        except Exception:
            self._winrate_window = 10

        # 🔥 로그 시스템 통일을 위한 헬퍼 메서드
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO', exchange=None: log_event(category, msg, exchange=exchange or self.current_exchange, level=level)
        self._recent_outcomes = {ex: deque(maxlen=self._winrate_window) for ex in self.enabled_exchanges}
        self.log_event('system', f"UnifiedTrader 초기화 완료 - 현재 거래소: {self.current_exchange}")
        pass

    def configure_strategy_runtime(self, strategy_customizer: Any = None, ai_trading_chatbot: Any = None):
        """미연결 전략 모듈을 통합 거래 루프에 연결한다."""
        self.strategy_customizer = strategy_customizer
        self.ai_trading_chatbot = ai_trading_chatbot

    def update_runtime_strategy_settings(self, new_settings: Dict[str, Any]):
        """재초기화 없이 전략 런타임 설정만 반영한다."""
        if not isinstance(new_settings, dict) or not new_settings:
            return
        self.settings.update(new_settings)
        self.trade_enabled_exchanges = self._compute_trade_enabled_exchanges()
        self.learning_enabled_exchanges = self._compute_learning_enabled_exchanges()
        self.log_event('settings', f"전략 런타임 설정 업데이트: {new_settings}", exchange='binance')

    def _apply_connected_strategy_runtime_unified(self, exchange_name: str):
        """연결된 StrategyCustomizer/AITradingChatbot을 거래소별 루프에 반영."""
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
                    self.log_event('strategy', f"전략 프로파일 적용: {profile}", exchange=exchange_name)
                elif not profile:
                    self._runtime_profile_applied = ''

            if mode == 'adaptive' and self.strategy_customizer:
                market_regime = 'NORMAL'
                try:
                    regime_raw = self._evaluate_current_market_conditions_unified_fast(exchange_name, 'BTCUSDT')
                    market_regime = str(regime_raw or 'NORMAL').upper()
                except Exception:
                    market_regime = 'NORMAL'

                perf = {
                    'recent_win_rate': 0.5,
                    'consecutive_losses': int(getattr(self.risk_manager, 'consecutive_losses', 0) or 0),
                }
                try:
                    if self.recorder and hasattr(self.recorder, 'get_recent_trades'):
                        rows = self.recorder.get_recent_trades(coin='', exchange=exchange_name, days=14) or []
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
                                perf['recent_win_rate'] = wins / total
                except Exception:
                    pass

                runtime_contexts = dict(
                    getattr(self, '_custom_strategy_runtime_context_by_exchange', {}) or {}
                )
                runtime_contexts[exchange_name] = {
                    'market_regime': market_regime,
                    'performance': dict(perf),
                }
                self._custom_strategy_runtime_context_by_exchange = runtime_contexts
                self.log_event(
                    'strategy',
                    f"adaptive 후보 컨텍스트 갱신: regime={market_regime}, "
                    f"win_rate={perf.get('recent_win_rate', 0.0):.2f}",
                    exchange=exchange_name,
                )
        except Exception as e:
            self.logger.warning(f"{exchange_name} 전략 런타임 반영 오류: {e}")

    def _prefilter_supported_coins(self, exchange_name: str, coins: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """거래소별 지원 심볼만 남기는 사전 필터.
        - CCXT 기반(bybit/okx/bitget/upbit/bithumb): adapter.exchange.markets 기준으로 확인
        - Binance: 네이티브 futures_exchange_info 기반으로 확인
        실패/미연결 시 원본을 그대로 반환(보수적)
        """
        try:
            if not coins:
                return coins
            name = str(exchange_name or '').lower()
            filtered: List[Dict[str, Any]] = []

            # 거래 타입 판별 (바이낸스 제외)
            trading_type = 'futures' if name in ['bybit', 'okx', 'bitget'] else 'spot'

            # 어댑터/클라이언트 확보
            adapter = None
            try:
                adapter = self.unified_manager.get_exchange(name, trading_type) if hasattr(self, 'unified_manager') and self.unified_manager else None
            except Exception:
                adapter = None

            # CCXT 계열: markets 기반 필터
            def _ccxt_supported(sym: str) -> bool:
                try:
                    if not adapter or not hasattr(adapter, 'exchange'):
                        return False
                    exch = getattr(adapter, 'exchange')
                    markets = getattr(exch, 'markets', None) or {}
                    if not markets:
                        try:
                            exch.load_markets()  # type: ignore
                            markets = getattr(exch, 'markets', {})
                        except Exception:
                            markets = {}
                    # 어댑터에 심볼 정규화기가 있으면 사용
                    norm = sym
                    try:
                        normalizer = getattr(adapter, '_normalize_symbol', None)
                        if callable(normalizer):
                            norm = normalizer(sym)
                        elif name == 'upbit':
                            upbit_normalizer = getattr(adapter, '_normalize_upbit_symbol', None)
                            if callable(upbit_normalizer):
                                norm = upbit_normalizer(sym)
                        elif name == 'bithumb':
                            bithumb_normalizer = getattr(adapter, '_normalize_bithumb_symbol', None)
                            if callable(bithumb_normalizer):
                                norm = bithumb_normalizer(sym)
                    except Exception:
                        pass
                    return bool(norm and norm in markets)
                except Exception:
                    return True

            def _normalize_for_exchange(sym: str) -> str:
                try:
                    if not adapter:
                        return sym
                    normalizer = getattr(adapter, '_normalize_symbol', None)
                    if callable(normalizer):
                        return str(normalizer(sym) or sym)
                    if name == 'upbit':
                        upbit_normalizer = getattr(adapter, '_normalize_upbit_symbol', None)
                        if callable(upbit_normalizer):
                            return str(upbit_normalizer(sym) or sym)
                    if name == 'bithumb':
                        bithumb_normalizer = getattr(adapter, '_normalize_bithumb_symbol', None)
                        if callable(bithumb_normalizer):
                            return str(bithumb_normalizer(sym) or sym)
                except Exception:
                    pass
                return sym

            # 바이낸스는 unified_trader에서 처리하지 않음

            for c in coins:
                # Evaluator의 극한 폴백은 문자열 목록을 반환할 수 있다.
                # 3.8.9.28에서 dict만 허용해 OKX 10개가 전부 탈락한 회귀를 복구한다.
                sym = c.get('symbol') if isinstance(c, dict) else str(c or '').strip()
                if not sym:
                    continue
                ok = True
                if name in ['bybit', 'okx', 'bitget', 'upbit', 'bithumb']:
                    ok = _ccxt_supported(str(sym))
                elif name == 'binance':
                    # 바이낸스는 unified_trader에서 처리하지 않음
                    self.logger.debug(f"바이낸스는 unified_trader에서 처리하지 않습니다: {name}")
                    continue
                if ok:
                    normalized_symbol = _normalize_for_exchange(str(sym))
                    if isinstance(c, dict):
                        cloned = dict(c)
                        cloned['symbol'] = normalized_symbol
                        filtered.append(cloned)
                    else:
                        filtered.append({
                            'symbol': normalized_symbol,
                            'is_major': self._symbol_base(normalized_symbol) in {
                                'BTC', 'ETH', 'BNB', 'SOL', 'ADA', 'XRP', 'DOT', 'LINK', 'AVAX', 'MATIC'
                            },
                        })

            if len(filtered) != len(coins):
                try:
                    self.logger.info(f"🧹 {exchange_name} 심볼 호환성 필터: {len(coins)} → {len(filtered)}")
                except Exception:
                    pass
            # 모든 심볼이 비호환으로 탈락한 경우 원본을 재사용하면
            # 거래소 비호환 심볼로 데이터 부족 루프가 발생할 수 있다.
            if not filtered and coins and name in ['bybit', 'okx', 'bitget', 'upbit', 'bithumb']:
                try:
                    self.logger.warning(f"⚠️ {exchange_name} 호환 심볼 없음 - 분석 스킵")
                except Exception:
                    pass
                return []
            return filtered if filtered else coins
        except Exception as e:
            try:
                self.logger.warning(f"사전 심볼 필터 오류: {e}")
            except Exception:
                pass
            if str(exchange_name or '').lower() in {
                'bybit', 'okx', 'bitget', 'upbit', 'bithumb',
            }:
                return []
            return coins

    @staticmethod
    def _symbol_base(symbol: str) -> str:
        """거래소 표기에서 기초자산 코드를 안전하게 추출한다."""
        value = str(symbol or '').upper().strip()
        if ':' in value:
            value = value.split(':', 1)[0]
        if '/' in value:
            return value.split('/', 1)[0]
        if '-' in value:
            parts = [part for part in value.split('-') if part]
            if len(parts) >= 2:
                return parts[1] if parts[0] in {'KRW', 'USD', 'USDT'} else parts[0]
        for quote in ('USDT', 'USDC', 'KRW', 'USD'):
            if value.endswith(quote) and len(value) > len(quote):
                return value[:-len(quote)]
        return value

    def get_all_balances_debug(self):
        """모든 거래소 잔고를 디버그용으로 상세 조회 및 로깅. 0, None, 오류, 연결만 됨 등 모든 상황을 명확하게 구분"""
        results = {}
        for ex in self.enabled_exchanges:
            try:
                client = self.get_exchange_client(ex)
                if client is None:
                    self.logger.error(f"[잔고조회] {ex}: 어댑터 연결 실패 (None)")
                    results[ex] = '어댑터 없음'
                    continue
                if hasattr(client, 'get_balance'):
                    try:
                        bal = client.get_balance()
                        if bal is None:
                            self.logger.info(f"[잔고조회] {ex}: API키 연결됨, 잔고 없음")
                            results[ex] = 'API키 연결됨, 잔고 없음'
                        elif isinstance(bal, (int, float)) and bal == 0:
                            self.logger.info(f"[잔고조회] {ex}: 잔고 0")
                            results[ex] = 0
                        else:
                            self.logger.info(f"[잔고조회] {ex}: {bal}")
                            results[ex] = bal
                    except Exception as e:
                        self.logger.error(f"[잔고조회] {ex}: get_balance() 오류: {e}")
                        results[ex] = f"get_balance 오류: {e}"
                else:
                    self.logger.error(f"[잔고조회] {ex}: get_balance 메서드 없음")
                    results[ex] = 'get_balance 없음'
            except Exception as e:
                self.logger.error(f"[잔고조회] {ex}: 예외 발생: {e}")
                results[ex] = f"예외: {e}"
        self.logger.info(f"[잔고조회] 전체 결과: {results}")
        return results

    # ------------------------------------------------------------------
    # 내부 유틸리티
    # ------------------------------------------------------------------
    def _normalize_exchange(self, exchange_name: Optional[str]) -> str:
        return str(exchange_name or '').strip().lower()

    def _compute_enabled_exchanges(self) -> List[str]:
        # 통합 코인 루프 대상은 '암호화폐 거래소'만 허용한다.
        # 주식 브로커(kiwoom/shinhan/miraeAsset/koreaInvestment)가 유입되면
        # 코인 선택/저장 로그가 주식 컨텍스트로 잘못 기록될 수 있다.
        allowed_crypto_exchanges = {'bybit', 'okx', 'bitget', 'upbit', 'bithumb'}
        enabled_set = set()
        try:
            raw = self.settings.get('enabled_exchanges', []) if isinstance(self.settings, dict) else []
            for item in raw or []:
                normalized = self._normalize_exchange(item)
                if normalized in allowed_crypto_exchanges:
                    enabled_set.add(normalized)
        except Exception:
            enabled_set = set()

        if not enabled_set:
            fallback = self._normalize_exchange(self.settings.get('selected_exchange', 'bybit'))
            if fallback in allowed_crypto_exchanges:
                enabled_set.add(fallback)

        enabled_list = list(enabled_set)
        if not enabled_list:
            enabled_list.append('bybit')  # 바이낸스 대신 bybit 기본값
        return enabled_list

    def _is_exchange_enabled(self, exchange_name: str) -> bool:
        normalized = self._normalize_exchange(exchange_name)
        return normalized in self.enabled_exchanges

    def _compute_trade_enabled_exchanges(self) -> List[str]:
        allowed = {'binance', 'bybit', 'okx', 'bitget', 'upbit', 'bithumb'}
        settings = self.settings if isinstance(self.settings, dict) else {}
        if not bool(settings.get('_trade_scope_user_confirmed_v3904', False)):
            return []
        configured = settings.get('trade_enabled_exchanges', [])
        normalized = [
            self._normalize_exchange(item)
            for item in (configured or [])
            if self._normalize_exchange(item) in allowed
        ]
        if normalized:
            return list(dict.fromkeys(normalized))
        # Missing key means a pre-scope legacy profile. An explicitly saved
        # empty list means "no live orders".
        if 'trade_enabled_exchanges' in settings:
            return []
        selected = self._normalize_exchange(settings.get('selected_exchange', 'binance'))
        return [selected] if selected in allowed else ['binance']

    def _compute_learning_enabled_exchanges(self) -> List[str]:
        allowed = {'binance', 'bybit', 'okx', 'bitget', 'upbit', 'bithumb'}
        configured = self.settings.get('learning_enabled_exchanges', []) if isinstance(self.settings, dict) else []
        source = configured or self.settings.get('enabled_exchanges', [])
        normalized = [
            self._normalize_exchange(item)
            for item in (source or [])
            if self._normalize_exchange(item) in allowed
        ]
        return list(dict.fromkeys(normalized))

    def _is_trade_enabled(self, exchange_name: str) -> bool:
        scope = getattr(self, 'trade_enabled_exchanges', None)
        if scope is None:
            if 'trade_enabled_exchanges' not in (self.settings or {}):
                return True
            scope = self._compute_trade_enabled_exchanges()
            self.trade_enabled_exchanges = scope
        return self._normalize_exchange(exchange_name) in scope

    def _execution_mode(self, exchange_name: str) -> ExecutionMode:
        return resolve_crypto_execution_mode(
            getattr(self, 'settings', {}) if isinstance(getattr(self, 'settings', {}), dict) else {},
            exchange_name,
            live_enabled=self._is_trade_enabled(exchange_name),
        )

    def _position_store(self, exchange_name: str) -> Dict[str, Position]:
        if self._execution_mode(exchange_name) == ExecutionMode.PAPER:
            if not hasattr(self, 'paper_positions'):
                self.paper_positions = {}
            return self.paper_positions.setdefault(exchange_name, {})
        return self.active_positions.setdefault(exchange_name, {})

    def _managed_open_trade_map(self, exchange_name: str) -> Dict[str, Dict[str, Any]]:
        getter = getattr(getattr(self, 'recorder', None), 'get_open_managed_trades', None)
        rows = getter(exchange_name) if callable(getter) else []
        return dict(managed_trade_map(rows or []))

    def _remember_trade_decision(
        self,
        exchange_name: str,
        symbol: str,
        status: str,
        reason: str,
        **extra: Any,
    ) -> None:
        venue = str(exchange_name or '').strip().lower()
        snapshot = {
            'exchange': venue,
            'symbol': str(symbol or ''),
            'status': str(status or 'unknown'),
            'reason': str(reason or ''),
            'recorded_at': datetime.now(timezone.utc).isoformat(),
            **extra,
        }
        if not isinstance(getattr(self, 'last_trade_decisions', None), dict):
            self.last_trade_decisions = {}
        self.last_trade_decisions.setdefault(venue, {})[str(symbol or '')] = snapshot
        saver = getattr(getattr(self, 'recorder', None), 'save_ai_decision', None)
        if callable(saver):
            try:
                saver(str(symbol or ''), f'trade_runtime::{venue}', snapshot)
            except Exception:
                pass

    def _effective_leverage_policy(
        self,
        exchange_name: str,
        requested: Any,
        *,
        cold_start: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        level = 'NORMAL'
        analyzer = getattr(self, 'analyzer', None)
        if analyzer is not None:
            try:
                market_data = analyzer._analyze_current_market_conditions()
                level = str((market_data or {}).get('level', 'NORMAL')).upper()
            except Exception:
                level = 'NORMAL'
        if level not in {'HIGH', 'NORMAL', 'LOW'}:
            level = 'NORMAL'
        return resolve_effective_leverage(
            configured_leverage=requested,
            exchange=exchange_name,
            market_level=level,
            exchange_max_leverage=exchange_leverage_cap(self.settings or {}, exchange_name),
            cold_start_max_leverage=(cold_start or {}).get('max_leverage'),
        )

    def _trade_stats_store(self, exchange_name: str) -> Dict[str, Any]:
        stores = self.paper_trade_stats if self._execution_mode(exchange_name) == ExecutionMode.PAPER else self.trade_stats
        return stores.setdefault(exchange_name, {
            'total_trades': 0,
            'profitable_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
        })

    def _is_learning_enabled(self, exchange_name: str) -> bool:
        scope = getattr(self, 'learning_enabled_exchanges', None)
        if scope is None:
            scope = self._compute_learning_enabled_exchanges()
            self.learning_enabled_exchanges = scope
        return self._normalize_exchange(exchange_name) in scope

    def _get_advanced_layers_settings(self, exchange_name: str) -> Dict[str, Any]:
        try:
            root = self.settings.get('advanced_trading_layers', {}) if isinstance(self.settings, dict) else {}
            exchange_overrides = (root.get('exchange_overrides', {}) or {}).get(exchange_name, {})
            merged = dict(root or {})
            merged.update(exchange_overrides or {})
            return merged
        except Exception:
            return {}

    def _get_local_trade_samples_unified(
        self,
        exchange_name: str,
        *,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """수익성 판단용 표본을 네트워크 없이 로컬 DB에서 읽는다.

        진입-청산이 연결된 ``trade_log``를 우선하고, 아직 완료 거래가 없으면
        거래소 확정 체결 원장을 보조 표본으로 사용한다. 전체 체결 목록 API가
        분석 10초 주기와 결합되지 않게 하는 것이 핵심이다.
        """
        recorder = getattr(self, 'recorder', None)
        completed_getter = getattr(recorder, 'get_recent_trades', None)
        if callable(completed_getter):
            try:
                rows = completed_getter(
                    coin='', exchange=str(exchange_name or '').lower(), days=30
                ) or []
                completed = [dict(row) for row in rows if isinstance(row, dict)]
                if completed:
                    return completed[:max(1, int(limit))]
            except (TypeError, ValueError):
                pass
            except Exception as exc:
                self.logger.warning(
                    f"{exchange_name} 로컬 완료 거래 조회 실패: {exc}"
                )

        execution_getter = getattr(recorder, 'get_recent_exchange_executions', None)
        if callable(execution_getter):
            try:
                rows = execution_getter(
                    str(exchange_name or '').lower(), limit=max(1, int(limit))
                ) or []
                return [dict(row) for row in rows if isinstance(row, dict)]
            except Exception as exc:
                self.logger.warning(
                    f"{exchange_name} 로컬 체결 원장 조회 실패: {exc}"
                )
        return []

    def _get_recent_trade_samples_unified(self, exchange_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        # 동기화는 자체 저빈도/모드/미확정 주문 정책을 따르며 분석 루프가
        # 강제로 REST 전체 조회를 일으키지 않는다.
        result = self.sync_exchange_execution_ledger(
            exchange_name,
            limit=limit,
            force=False,
        )
        local_rows = self._get_local_trade_samples_unified(
            exchange_name,
            limit=limit,
        )
        if local_rows:
            return local_rows
        # 구형/테스트 Recorder처럼 로컬 조회 계약이 없을 때만 이번 동기화
        # 응답을 호환 표본으로 사용한다.
        return list(result.get('trades') or [])

    def sync_exchange_execution_ledger(
        self,
        exchange_name: str,
        *,
        limit: int = 200,
        force: bool = False,
        full_backfill: bool = False,
        reason: str = 'runtime',
    ) -> Dict[str, Any]:
        """UI와 무관하게 거래소 체결/주문접수를 로컬 원장과 대조한다.

        전체 체결 이력은 시작/수동 복구 또는 기본 5분 저빈도 증분 조회만 허용한다.
        미확정 NoahAI 주문은 별도 짧은 주기로 주문 ID만 확인한다. LEARNING/PAPER는
        미확정 실주문이 없는 한 개인 체결 API를 호출하지 않는다.
        """
        venue = str(exchange_name or '').strip().lower()
        result: Dict[str, Any] = {
            'exchange': venue,
            'trades': [],
            'received': 0,
            'inserted': 0,
            'recovered': 0,
            'pending': 0,
            'failed': 0,
            'skipped_by_throttle': False,
            'skipped_by_mode': False,
            'history_requested': False,
            'history_incremental': False,
            'stream_received': 0,
            'sync_reason': str(reason or 'runtime'),
        }
        if not venue:
            return result
        now = time.monotonic()

        settings = self.settings if isinstance(getattr(self, 'settings', None), dict) else {}
        try:
            history_interval = max(
                60,
                int(settings.get('execution_history_sync_interval_seconds', 300) or 300),
            )
        except (TypeError, ValueError):
            history_interval = 300
        try:
            receipt_interval = max(
                2,
                int(settings.get('pending_order_poll_interval_seconds', 10) or 10),
            )
        except (TypeError, ValueError):
            receipt_interval = 10

        history_state = getattr(self, '_runtime_execution_sync_state', None)
        if not isinstance(history_state, dict):
            history_state = {}
            self._runtime_execution_sync_state = history_state
        receipt_state = getattr(self, '_runtime_receipt_sync_state', None)
        if not isinstance(receipt_state, dict):
            receipt_state = {}
            self._runtime_receipt_sync_state = receipt_state

        recorder = getattr(self, 'recorder', None)
        reference_getter = getattr(recorder, 'get_exchange_order_references', None)
        references: List[Dict[str, Any]] = []
        if callable(reference_getter):
            try:
                references = list(reference_getter(venue, limit=limit) or [])
            except Exception as exc:
                result['failed'] += 1
                self.logger.warning(f"{venue} 미확정 주문 조회 실패: {exc}")

        # 신규 주문은 계정 전체 체결목록 대신 저장된 주문 ID만 terminal 상태까지 확인한다.
        last_receipt = float(receipt_state.get(venue, 0.0) or 0.0)
        receipt_due = bool(references) and (force or now - last_receipt >= receipt_interval)
        if receipt_due:
            receipt_state[venue] = now
            reconciled = self.reconcile_exchange_order_receipts(venue, limit=limit)
            result['recovered'] = int(reconciled.get('confirmed', 0) or 0)
            result['pending'] = int(reconciled.get('pending', 0) or 0)
            result['failed'] += int(reconciled.get('failed', 0) or 0)
        else:
            result['pending'] = len(references)

        try:
            execution_mode = self._execution_mode(venue)
        except Exception:
            # 부분 객체를 사용하는 구형 호출/테스트만 LIVE 호환으로 처리한다.
            execution_mode = ExecutionMode.LIVE
        if execution_mode != ExecutionMode.LIVE:
            result['skipped_by_mode'] = True
            result['trades'] = self._get_local_trade_samples_unified(
                venue, limit=limit
            )
            return result

        # 어댑터가 인증 사용자 체결 스트림을 제공하면 먼저 비운다. 현재 공개
        # 시장가 WebSocket과 혼동하지 않으며, 명시적 drain 계약이 있을 때만 사용한다.
        client = self.get_exchange_client(venue)
        stream_reader = getattr(client, 'drain_execution_events', None)
        stream_healthy = False
        if callable(stream_reader):
            try:
                streamed = stream_reader(limit=max(1, int(limit))) or []
                streamed_rows = [dict(row) for row in streamed if isinstance(row, dict)]
                stream_health = getattr(client, 'execution_stream_healthy', None)
                stream_healthy = bool(stream_health()) if callable(stream_health) else False
                saver = getattr(recorder, 'save_exchange_execution_history', None)
                if streamed_rows and callable(saver):
                    saved = saver(
                        venue, streamed_rows, source='private_execution_stream'
                    ) or {}
                    result['inserted'] += int(saved.get('inserted', 0) or 0)
                    result['stream_received'] = len(streamed_rows)
            except Exception as exc:
                result['failed'] += 1
                self.logger.warning(f"{venue} 사용자 체결 스트림 처리 실패: {exc}")

        last_history = float(history_state.get(venue, 0.0) or 0.0)
        history_due = force or now - last_history >= history_interval
        if stream_healthy and not force and not full_backfill:
            history_due = False
        if not history_due:
            result['skipped_by_throttle'] = True
            result['trades'] = self._get_local_trade_samples_unified(
                venue, limit=limit
            )
            return result
        # 실패해도 분석 루프마다 재시도하지 않도록 시도 시점을 먼저 기록한다.
        history_state[venue] = now

        try:
            if client is not None and hasattr(client, 'get_trade_history'):
                cursor: Dict[str, Any] = {}
                cursor_getter = getattr(recorder, 'get_exchange_execution_cursor', None)
                if not full_backfill and callable(cursor_getter):
                    cursor = dict(cursor_getter(venue) or {})
                incremental = bool(cursor.get('since_ms') or cursor.get('trade_id'))
                try:
                    rows = client.get_trade_history(
                        limit=max(1, int(limit)),
                        since_ms=cursor.get('since_ms'),
                        from_id=cursor.get('trade_id'),
                    ) or []
                except TypeError:
                    # 아직 증분 인자를 구현하지 않은 외부/레거시 어댑터 호환.
                    rows = client.get_trade_history(limit=max(1, int(limit))) or []
                    incremental = False
                normalized = [dict(row) for row in rows if isinstance(row, dict)]
                result['trades'] = normalized
                result['received'] = len(normalized)
                result['history_requested'] = True
                result['history_incremental'] = incremental
                saver = getattr(recorder, 'save_exchange_execution_history', None)
                if normalized and callable(saver):
                    saved = saver(
                        venue,
                        normalized,
                        source=(
                            'runtime_exchange_incremental'
                            if incremental else 'runtime_exchange_backfill'
                        ),
                    ) or {}
                    result['inserted'] += int(saved.get('inserted', 0) or 0)
            if result['inserted'] or result['recovered']:
                self.logger.info(
                    f"{venue} 런타임 체결 원장 동기화: "
                    f"신규 {result['inserted']}건 · 주문복구 {result['recovered']}건"
                )
        except Exception as exc:
            result['failed'] += 1
            self.logger.warning(f"{venue} 런타임 체결 원장 동기화 실패: {exc}")
        local_rows = self._get_local_trade_samples_unified(venue, limit=limit)
        if local_rows:
            result['trades'] = local_rows
        return result

    def _build_strategy_runtime_state_unified(self, exchange_name: str, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        runtime_state: Dict[str, Any] = {}
        for trade in trades or []:
            symbol = str(trade.get('symbol') or '').strip().upper()
            if not symbol:
                continue
            ts_raw = trade.get('timestamp') or trade.get('filled_at') or trade.get('time') or trade.get('order_time')
            parsed = None
            try:
                if isinstance(ts_raw, (int, float)):
                    parsed = datetime.fromtimestamp(float(ts_raw) / 1000.0 if float(ts_raw) > 1e12 else float(ts_raw))
                elif isinstance(ts_raw, str) and ts_raw:
                    parsed = datetime.fromisoformat(ts_raw.replace('Z', '+00:00')).replace(tzinfo=None)
            except Exception:
                parsed = None
            if parsed is None:
                continue
            key = f'last_trade_at::{symbol}'
            if key not in runtime_state or parsed > runtime_state[key]:
                runtime_state[key] = parsed
        return runtime_state

    def _build_portfolio_allocation_unified(self, exchange_name: str, selected_coins: List[Dict[str, Any]], analysis_results: Dict[str, Dict[str, Any]], layer_settings: Dict[str, Any]) -> Dict[str, Any]:
        policy = dict(layer_settings.get('portfolio_orchestration', {}) or {})
        if not bool(policy.get('enabled', False)):
            return {'allocations': {}, 'portfolio_risk': 0.0, 'risk_scale': 1.0}

        total_capital = 0.0
        try:
            balance_result = self.exchange_manager.get_exchange_balance(exchange_name, force_refresh=False) if hasattr(self.exchange_manager, 'get_exchange_balance') else {}
            if isinstance(balance_result, dict) and balance_result.get('status') == 'success':
                balance = balance_result.get('balance', {})
                if isinstance(balance, dict):
                    if 'USDT' in balance and isinstance(balance.get('USDT'), dict):
                        total_capital = float(balance.get('USDT', {}).get('free', 0) or 0)
                    else:
                        total_capital = float(balance.get('total', balance.get('cash', 0)) or 0)
        except Exception:
            total_capital = 0.0

        # UnifiedTrader는 암호화폐 거래소만 대상으로 동작하므로 asset_class를 crypto로 고정한다.
        asset_class = 'crypto' if exchange_name in ['bybit', 'okx', 'bitget', 'upbit', 'bithumb'] else 'stock'
        candidates = []
        for coin in selected_coins or []:
            symbol = str((coin or {}).get('symbol') or '').strip().upper()
            analysis = analysis_results.get(symbol, {}) if isinstance(analysis_results, dict) else {}
            if not symbol or not analysis:
                continue
            candidates.append({
                'symbol': symbol,
                'asset_class': asset_class,
                'signal_strength': max(0.0, min(1.0, float(analysis.get('confidence', 0.0) or 0.0))),
                'volatility': max(0.005, abs(float(analysis.get('market_volatility', 0.5) or 0.5)) / 100.0),
                'avg_correlation': float(((policy.get('correlation_overrides', {}) or {}).get(symbol, 0.25)) or 0.25),
            })
        return PortfolioOrchestrator().allocate(candidates=candidates, total_capital=total_capital, policy=policy)

    def _initialize_exchanges(self, exchanges: Optional[List[str]] = None):
        """거래소별 시스템 초기화 (CCXT 거래소만)

        기본은 지연 초기화이며, 필요한 거래소만 명시적으로 준비한다.
        """
        target_exchanges = exchanges if exchanges is not None else self.enabled_exchanges
        for exchange in target_exchanges:
            # 🔥 바이낸스는 절대 처리하지 않음 (Trader에서 처리)
            if exchange == 'binance':
                self.logger.debug(f"바이낸스는 unified_trader에서 처리하지 않습니다: {exchange}")
                continue

            if exchange in self._initialized_exchanges:
                continue

            # 거래소별 통계 초기화 (DB에서 로드)
            self.trade_stats[exchange] = {
                'total_trades': 0,
                'profitable_trades': 0,
                'losing_trades': 0,
                'total_pnl': 0.0
            }
            self.paper_trade_stats.setdefault(exchange, {
                'total_trades': 0,
                'profitable_trades': 0,
                'losing_trades': 0,
                'total_pnl': 0.0,
            })

            # DB에서 이전 통계 로드
            if self._execution_mode(exchange) != ExecutionMode.PAPER:
                self._load_trade_stats_from_db(exchange)

            # 실제·가상 포지션 저장소를 분리한다. PAPER에서는 실계좌
            # 포지션을 가져오지 않아 가상 청산/보호주문과 섞이지 않게 한다.
            self.active_positions[exchange] = {}
            self.paper_positions.setdefault(exchange, {})
            if self._execution_mode(exchange) != ExecutionMode.PAPER:
                self._restore_positions_from_exchange(exchange)
            else:
                self.logger.info(f"🧪 {exchange} PAPER 초기화 - 실제 포지션 복구 생략")

            # 거래소별 모니터링 플래그 초기화
            self.monitoring_flags[exchange] = False
            self.monitoring_threads.setdefault(exchange, None)

            # 거래소별 거래 진입 여부 초기화
            self.trade_entered[exchange] = {}

            # 거래소별 AI 최적화 캐시 초기화
            self.ai_optimization_cache[exchange] = {}

            # 거래소별 패턴 분석 캐시 초기화
            self.pattern_analysis_cache[exchange] = {}

            # 거래소별 가격 데이터 포인트 초기화
            self.price_data_points[exchange] = {}

            # 거래소별 고급 주문 관리자 초기화 (CCXT 거래소만 지원)
            self.advanced_order_managers[exchange] = None

            self.logger.info(f"✅ {exchange} 거래소 시스템 초기화 완료")
            self._initialized_exchanges.add(exchange)

    def _ensure_exchange_initialized(self, exchange_name: str) -> bool:
        ex = self._normalize_exchange(exchange_name)
        if not ex or ex == 'binance':
            return False
        if ex not in self.enabled_exchanges:
            self.logger.warning(f"{ex}는 활성 거래소 목록에 없어 초기화를 건너뜁니다")
            return False
        if ex not in self._initialized_exchanges:
            self._initialize_exchanges([ex])
        return ex in self._initialized_exchanges

    def get_exchange_client(self, exchange_name: str):
        """거래소별 클라이언트 가져오기 (CCXT 거래소만 지원)"""
        if not self._is_exchange_enabled(exchange_name):
            return None

        # 바이낸스는 지원하지 않음 (trader.py에서 처리)
        if exchange_name.lower() == 'binance':
            self.logger.warning(f"바이낸스는 unified_trader에서 지원하지 않습니다. trader.py를 사용하세요.")
            return None

        trading_type = 'futures' if exchange_name in ['bybit', 'okx', 'bitget'] else 'spot'
        return self.unified_manager.get_exchange(exchange_name, trading_type)

    def select_trading_coins_unified(self, exchange_name: str) -> List[Dict[str, Any]]:
        """거래소별 코인 선택 (기존 evaluator와 연동)"""
        try:
            allowed_crypto_exchanges = {'bybit', 'okx', 'bitget', 'upbit', 'bithumb'}
            if self._normalize_exchange(exchange_name) not in allowed_crypto_exchanges:
                self.logger.info(f"{exchange_name}는 코인 선택 대상이 아님 - unified 코인 선택 건너뜀")
                return []

            if not self._is_exchange_enabled(exchange_name):
                self.logger.debug(f"{exchange_name} 코인 선택 건너뜀 (비활성 거래소)")
                return []

            self.logger.info(f"🔄 {exchange_name} 코인 선택 시작")
            self.logger.info(f"코인 선택 시작 (ex={exchange_name})")

            # 기존 evaluator 사용 (바이낸스와 동일한 로직)
            if hasattr(self, 'evaluator') and self.evaluator:
                # 기존 evaluator의 코인 선택 로직 사용
                ex_client_for_eval = None
                try:
                    ex_client_for_eval = self.get_exchange_client(exchange_name)
                except Exception:
                    ex_client_for_eval = None

                # 비바이낸스에서 거래소 클라이언트가 없으면 바이낸스 폴백을 금지
                if exchange_name != 'binance' and not ex_client_for_eval:
                    self.logger.warning(
                        f"⚠️ {exchange_name} 클라이언트 없음 - 지원 심볼을 확인할 수 없어 코인 선택 중단"
                    )
                    self.selected_coins[exchange_name] = []
                    if hasattr(self, 'main_app') and self.main_app:
                        if not hasattr(self.main_app, 'selected_coins_by_exchange'):
                            self.main_app.selected_coins_by_exchange = {}
                        self.main_app.selected_coins_by_exchange[exchange_name] = []
                    return []

                selected_coins = self.evaluator.select_trading_coins(
                    num_alt=15,
                    num_major=5,
                    regime=str(
                        (getattr(self, 'last_market_regime_by_exchange', {}) or {}).get(
                            exchange_name,
                            'normal',
                        )
                    ),
                    exchange=exchange_name,
                    exchange_client=ex_client_for_eval
                )
                selection_cfg = dict(
                    (self.settings or {}).get('crypto_selection', {}) or {}
                )
                manual_by_exchange = dict(
                    selection_cfg.get('manual_symbols_by_exchange', {}) or {}
                )
                general_selection = SelectionPolicy(
                    target=exchange_name,
                    asset_class='crypto',
                    limit=20,
                ).resolve(
                    automatic_candidates=list(selected_coins or []),
                    pinned_symbols=list(
                        manual_by_exchange.get(
                            str(exchange_name or '').strip().lower(),
                            [],
                        )
                        or []
                    ),
                )
                raw_market_universe = list(
                    (
                        getattr(
                            self.evaluator,
                            "last_market_universe_candidates_by_exchange",
                            {},
                        )
                        or {}
                    ).get(str(exchange_name or "").strip().lower(), [])
                    or []
                )
                advanced_selection = select_advanced_strategy_universe(
                    strategy_pool=list(
                        getattr(self, "active_custom_strategy_pool", []) or []
                    ),
                    market_candidates=raw_market_universe or selected_coins,
                    pinned_symbols=list(
                        manual_by_exchange.get(
                            str(exchange_name or "").strip().lower(),
                            [],
                        )
                        or []
                    ),
                    asset_class="crypto",
                    target=exchange_name,
                    default_limit=20,
                )
                selected_coins = combine_selection_paths(
                    general_selection,
                    advanced_selection,
                )
                selected_coins = self._prefilter_supported_coins(
                    exchange_name,
                    selected_coins,
                )
                # 거래소별 코인 목록은 항상 분리 보관
                self.selected_coins[exchange_name] = list(selected_coins or [])

                # main_app에도 거래소별 맵으로 동기화 (레거시 selected_coins 오염 방지)
                if hasattr(self, 'main_app') and self.main_app:
                    if not hasattr(self.main_app, 'selected_coins_by_exchange'):
                        self.main_app.selected_coins_by_exchange = {}
                    self.main_app.selected_coins_by_exchange[exchange_name] = list(selected_coins or [])
                    # 현재 선택된 거래소와 일치할 때만 main_app.selected_coins 업데이트 (바이낸스 강제 조건 제거)
                    selected_ex = str(getattr(self.main_app, 'current_exchange', '') or '').lower()
                    if selected_ex == str(exchange_name).lower():
                        self.main_app.selected_coins = list(selected_coins or [])
                # 사용자 안내: 코인정보 탭에서 새로고침 시 상세 확인 가능
                self.logger.info(f"✅ {exchange_name} 코인 선택 완료: {len(selected_coins)}개 - 코인정보에서 새로고침 시 확인 가능 (ex={exchange_name})")
                return selected_coins
            else:
                # 기본 코인 목록 사용
                default_coins = self._get_default_coins(exchange_name)
                selection_cfg = dict(
                    (self.settings or {}).get('crypto_selection', {}) or {}
                )
                manual_by_exchange = dict(
                    selection_cfg.get('manual_symbols_by_exchange', {}) or {}
                )
                general_selection = SelectionPolicy(
                    target=exchange_name,
                    asset_class='crypto',
                    limit=20,
                ).resolve(
                    automatic_candidates=list(default_coins or []),
                    pinned_symbols=list(
                        manual_by_exchange.get(
                            str(exchange_name or '').strip().lower(),
                            [],
                        )
                        or []
                    ),
                )
                advanced_selection = select_advanced_strategy_universe(
                    strategy_pool=list(
                        getattr(self, "active_custom_strategy_pool", []) or []
                    ),
                    market_candidates=default_coins,
                    pinned_symbols=list(
                        manual_by_exchange.get(
                            str(exchange_name or "").strip().lower(),
                            [],
                        )
                        or []
                    ),
                    asset_class="crypto",
                    target=exchange_name,
                    default_limit=20,
                )
                default_coins = combine_selection_paths(
                    general_selection,
                    advanced_selection,
                )
                default_coins = self._prefilter_supported_coins(
                    exchange_name,
                    default_coins,
                )
                self.selected_coins[exchange_name] = list(default_coins or [])

                # main_app에도 거래소별 맵으로 동기화
                if hasattr(self, 'main_app') and self.main_app:
                    if not hasattr(self.main_app, 'selected_coins_by_exchange'):
                        self.main_app.selected_coins_by_exchange = {}
                    self.main_app.selected_coins_by_exchange[exchange_name] = list(default_coins or [])
                    # 현재 선택된 거래소와 일치할 때만 main_app.selected_coins 업데이트 (바이낸스 강제 조건 제거)
                    selected_ex = str(getattr(self.main_app, 'current_exchange', '') or '').lower()
                    if selected_ex == str(exchange_name).lower():
                        self.main_app.selected_coins = list(default_coins or [])
                # 사용자 안내: 코인정보 탭에서 새로고침 시 상세 확인 가능
                self.logger.info(f"✅ {exchange_name} 기본 코인 선택 완료: {len(default_coins)}개 - 코인정보에서 새로고침 시 확인 가능 (ex={exchange_name})")
                return default_coins

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} 코인 선택 실패: {e}")
            return []

    def _get_default_coins(self, exchange_name: str) -> List[Dict[str, Any]]:
        """거래소별 기본 코인 목록 (CCXT 거래소만)"""
        default_coins = {
            'bybit': [
                {'symbol': 'BTCUSDT', 'is_major': True},
                {'symbol': 'ETHUSDT', 'is_major': True},
                {'symbol': 'ADAUSDT', 'is_major': False}
            ],
            'okx': [
                {'symbol': 'BTC-USDT', 'is_major': True},
                {'symbol': 'ETH-USDT', 'is_major': True},
                {'symbol': 'ADA-USDT', 'is_major': False}
            ],
            'bitget': [
                {'symbol': 'BTCUSDT', 'is_major': True},
                {'symbol': 'ETHUSDT', 'is_major': True},
                {'symbol': 'ADAUSDT', 'is_major': False}
            ],
            'upbit': [
                {'symbol': 'KRW-BTC', 'is_major': True},
                {'symbol': 'KRW-ETH', 'is_major': True},
                {'symbol': 'KRW-ADA', 'is_major': False}
            ],
            'bithumb': [
                {'symbol': 'BTC/KRW', 'is_major': True},
                {'symbol': 'ETH/KRW', 'is_major': True},
                {'symbol': 'ADA/KRW', 'is_major': False}
            ]
        }
        return default_coins.get(exchange_name, [])

    def analyze_coins_unified(self, exchange_name: str, coins: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """거래소별 코인 분석 (기존 analyzer와 연동)"""
        try:
            # 사용자 안내: 코인정보 탭 새로고침으로 분석 대상 확인 가능
            self.logger.info(f"📊 {exchange_name} 코인 분석 시작: {len(coins)}개 - 코인정보에서 새로고침 시 확인 가능")
            self.logger.info(f"코인 분석 시작: {len(coins)}개 - 코인정보에서 새로고침 시 확인 가능 (ex={exchange_name})")

            # 거래소-심볼 호환성 사전 필터 적용
            coins = self._prefilter_supported_coins(exchange_name, coins)
            self.logger.info(f"분석 대상 확정: {len(coins)}개 (ex={exchange_name})")

            analysis_results = {}

            total = len(coins)
            for idx, coin in enumerate(coins):
                # 🔥 중지 플래그 체크: 거래 중지 시 즉시 루프 탈출
                if not self.trading_cycles.get(exchange_name, False):
                    self.logger.info(f"⏹️ {exchange_name} 분석 중지됨 ({idx}/{total} 완료)")
                    try:
                        self.logger.info(f"분석 중지됨 ({idx}/{total} 완료) (ex={exchange_name})")
                    except Exception:
                        pass
                    break

                symbol = coin.get('symbol', '')
                if not symbol:
                    continue
                # 코인별 진행 상황 로그 (실시간 가시성 향상)
                try:
                    self.logger.info(f"[{idx+1}/{total}] {symbol} 분석 시작 (ex={exchange_name})")
                except Exception:
                    pass

                # 기존 analyzer 사용
                if self.analyzer:
                    try:
                        inference_started = time.perf_counter()
                        analysis_config = self.settings
                        if str(coin.get("_selection_pipeline") or "") == "advanced":
                            analysis_config = dict(self.settings or {})
                            analysis_config["_skip_ai_enhancement"] = True
                        signal_data = self.analyzer.generate_trading_signal(
                            symbol,
                            config=analysis_config,
                            exchange_name=exchange_name,
                        )
                        inference_ms = (time.perf_counter() - inference_started) * 1000.0
                        emit_kpi_event(
                            event_type='ai_inference_completed',
                            category='learning',
                            asset_class='crypto',
                            status='success',
                            source='noahai_client_unified_trader',
                            metric_value=float(inference_ms),
                            metadata={
                                'exchange': exchange_name,
                                'symbol': symbol,
                                'signal': str(signal_data.get('signal', 'HOLD')) if isinstance(signal_data, dict) else 'HOLD',
                                'ai_call_mode': str(signal_data.get('ai_call_mode', 'unknown')) if isinstance(signal_data, dict) else 'unknown',
                                'ai_model': str(signal_data.get('ai_model', '')) if isinstance(signal_data, dict) else '',
                                'strategy_variant': str(signal_data.get('strategy_variant', 'unknown')) if isinstance(signal_data, dict) else 'unknown',
                                'input_tokens': int((signal_data.get('ai_usage', {}) or {}).get('input_tokens', 0) or 0) if isinstance(signal_data, dict) else 0,
                                'output_tokens': int((signal_data.get('ai_usage', {}) or {}).get('output_tokens', 0) or 0) if isinstance(signal_data, dict) else 0,
                            },
                        )
                    except Exception as e:
                        emit_kpi_event(
                            event_type='ai_inference_completed',
                            category='learning',
                            asset_class='crypto',
                            status='failed',
                            source='noahai_client_unified_trader',
                            metadata={
                                'exchange': exchange_name,
                                'symbol': symbol,
                                'reason': str(e),
                            },
                        )
                        raise
                    if not isinstance(signal_data, dict):
                        self.logger.warning(
                            f"⚠️ {exchange_name} {symbol} 분석 응답 형식 오류: "
                            f"{type(signal_data).__name__} → HOLD로 격리"
                        )
                        signal_data = {
                            "signal": "HOLD",
                            "confidence": 0.0,
                            "reason": "분석기 응답 형식 오류",
                        }
                    signal_data["_selection_pipeline"] = str(
                        coin.get("_selection_pipeline") or "general"
                    )
                    signal_data["_eligible_strategy_modes"] = list(
                        coin.get("_eligible_strategy_modes") or []
                    )
                    signal_data["_eligible_strategy_ids"] = list(
                        coin.get("_eligible_strategy_ids") or []
                    )
                    analysis_results[symbol] = signal_data
                    # 코인별 완료 로그 (핵심 지표 요약은 선택적으로 표시)
                    try:
                        sig = str(signal_data.get('signal', '')) if isinstance(signal_data, dict) else ''
                        conf = signal_data.get('confidence') if isinstance(signal_data, dict) else None
                        conf_txt = f", confidence={conf}" if conf is not None else ''
                        self.logger.info(f"[{idx+1}/{total}] {symbol} 분석 완료: signal={sig}{conf_txt} (ex={exchange_name})")
                        # 신호 발생 시 핵심 지표를 추가로 요약 표기
                        if isinstance(signal_data, dict) and str(signal_data.get('signal', '')).upper() in ('LONG', 'SHORT'):
                            mv = signal_data.get('market_volatility')
                            ts = signal_data.get('trend_strength')
                            ep = signal_data.get('entry_price')
                            tp = signal_data.get('tp_percent')
                            sl = signal_data.get('sl_percent')
                            lev = signal_data.get('leverage')
                            reason = signal_data.get('reason', '')
                            def _fmt(v, prec=4):
                                try:
                                    return f"{float(v):.{prec}f}"
                                except Exception:
                                    return str(v)
                            details = (
                                f"conf={_fmt(conf,2) if conf is not None else 'N/A'}, "
                                f"trend={_fmt(ts,2) if ts is not None else 'N/A'}, "
                                f"vol={_fmt(mv,4) if mv is not None else 'N/A'}, "
                                f"entry={_fmt(ep,6) if ep is not None else 'N/A'}, "
                                f"tp={_fmt(tp,4) if tp is not None else 'N/A'}, "
                                f"sl={_fmt(sl,4) if sl is not None else 'N/A'}, "
                                f"lev={_fmt(lev,1) if lev is not None else 'N/A'}"
                            )
                            reason_short = (reason[:120] + '…') if isinstance(reason, str) and len(reason) > 120 else (reason or '')
                            self.logger.info(f"{symbol} 신호 상세: {details}{(' | ' + reason_short) if reason_short else ''} (ex={exchange_name})")
                    except Exception:
                        pass

                else:
                    # 기본 분석 결과
                    analysis_results[symbol] = {
                        'signal': 'HOLD',
                        'confidence': 0.5,
                        'reason': '기본 분석'
                    }
                    try:
                        self.logger.info(f"[{idx+1}/{total}] {symbol} 기본 분석 완료 (ex={exchange_name})")
                    except Exception:
                        pass

            self.logger.info(f"✅ {exchange_name} 코인 분석 완료: {len(analysis_results)}개")
            self.logger.info(f"코인 분석 완료: {len(analysis_results)}개 (ex={exchange_name})")
            return analysis_results

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} 코인 분석 실패: {e}")
            return {}

    def execute_trading_cycle_unified(self, exchange_name: str):
        """거래소별 거래 사이클 실행 (바이낸스와 동일한 로직)"""
        try:
            self.logger.info(f"🔄 {exchange_name} 거래 사이클 시작")
            execution_mode = self._execution_mode(exchange_name)
            learning_scope = getattr(self, 'learning_enabled_exchanges', None)
            if learning_scope is None:
                learning_scope = self._compute_learning_enabled_exchanges()
                self.learning_enabled_exchanges = learning_scope
            scope_keys_present = any(
                key in (self.settings or {})
                for key in ('trade_enabled_exchanges', 'learning_enabled_exchanges', 'enabled_exchanges')
            )
            if (
                scope_keys_present
                and self._normalize_exchange(exchange_name) not in learning_scope
                and not self._is_trade_enabled(exchange_name)
            ):
                self.logger.info(f"⏭️ {exchange_name} 거래·학습 대상 아님 - 사이클 생략")
                return

            # 🤖 AI 자동 학습: 거래 성과에 따라 신호 기준 조절
            self._auto_adjust_threshold_from_performance(exchange_name)
            self._apply_connected_strategy_runtime_unified(exchange_name)

            # 0. 코인 재선택 로직 (시장 상황 변화 체크) - 최적화
            self._check_and_reselect_coins_unified_optimized(exchange_name)

            # 1. 거래 모드 확인 (페이퍼/데모/실제)
            try:
                paper = execution_mode == ExecutionMode.PAPER
                demo = bool(self.settings.get('demo_mode', False)) if isinstance(self.settings, dict) else False

                if demo:
                    try:
                        from path_utils import get_current_user_account
                        from utils.admin_utils import is_admin_account

                        current_user = get_current_user_account() or self.settings.get('user_id') or self.settings.get('username')
                        if not is_admin_account(current_user):
                            self.logger.warning("⛔ 데모 모드는 관리자 계정에서만 사용할 수 있습니다. demo_mode를 비활성화합니다.")
                            demo = False
                        else:
                            # 데모 모드는 실거래 호출이 없어야 하므로 내부적으로 paper 모드를 강제한다.
                            paper = True
                    except Exception as admin_check_err:
                        self.logger.warning(f"⚠️ 데모 모드 권한 확인 실패로 demo_mode를 비활성화합니다: {admin_check_err}")
                        demo = False

                # 데모 모드 우선순위 (데모 > 페이퍼 > 실제)
                if demo:
                    mode_text = 'DEMO'
                    # 데모 모드 초기화
                    if not hasattr(self, 'demo_trader'):
                        from trading.demo_trader import DemoTrader
                        self.demo_trader = DemoTrader(self.settings, self.logger)
                        self.logger.info("🎭 데모 모드 활성화 - 관리자 전용 고성능 시뮬레이션")
                elif paper:
                    mode_text = 'PAPER'
                else:
                    mode_text = 'REAL'

                self.logger.info(f"거래 모드: {mode_text} (ex={exchange_name})")
            except Exception:
                paper = execution_mode == ExecutionMode.PAPER
                demo = False
                mode_text = 'REAL'

            # 1. 거래소별 선택 코인 사용 (거래소 간 코인 오염 방지)
            selected_store = getattr(self, 'selected_coins', {}) or {}
            if isinstance(selected_store, dict):
                selected_coins = list(selected_store.get(exchange_name, []) or [])
            else:
                selected_coins = []
            # main_app에서도 거래소별 맵만 허용한다. 과거 단일 selected_coins
            # 폴백은 화면 전환 타이밍에 Binance 후보를 다른 거래소로 오염시켰다.
            if not selected_coins:
                selected_by_exchange = getattr(
                    getattr(self, 'main_app', None),
                    'selected_coins_by_exchange',
                    {},
                ) or {}
                if isinstance(selected_by_exchange, dict):
                    selected_coins = list(selected_by_exchange.get(exchange_name, []) or [])
            if not selected_coins:
                self.log_event('system', f"{exchange_name} 선택된 코인 없음 - 코인 선택 필요", exchange=exchange_name, level='WARNING')
                return

            # Evaluator의 극한 폴백은 문자열 심볼을 반환할 수 있다. 이후
            # 포트폴리오·실행 루프는 dict 계약만 사용하도록 여기서 통일한다.
            selected_coins = self._prefilter_supported_coins(
                exchange_name,
                selected_coins,
            )
            selected_coins = [
                dict(item)
                if isinstance(item, dict)
                else {"symbol": str(item or "").strip()}
                for item in selected_coins
                if (
                    str(item.get("symbol") or "").strip()
                    if isinstance(item, dict)
                    else str(item or "").strip()
                )
            ]
            if not selected_coins:
                self.logger.warning(f"{exchange_name} 지원되는 분석 심볼 없음 (ex={exchange_name})")
                return

            self.log_event('system', f"📈 {exchange_name} 선택된 코인: {len(selected_coins)}개", exchange=exchange_name)

            # 2. 코인 분석
            analysis_results = self.analyze_coins_unified(exchange_name, selected_coins)
            if not analysis_results:
                self.logger.warning(f"{exchange_name} 분석 결과 없음 (ex={exchange_name})")
                return

            self.logger.info(f"📊 {exchange_name} 분석 완료: {len(analysis_results)}개 (ex={exchange_name})")

            # LEARNING도 커스텀 후보까지 전체 판단하고 주문만 차단한다.
            learning_only = execution_mode == ExecutionMode.LEARNING
            if execution_mode == ExecutionMode.PAPER:
                self.logger.info(
                    f"🧪 {exchange_name} PAPER 주문 판단 시작 - 실제 주문 API 0건"
                )

            layer_settings = self._get_advanced_layers_settings(exchange_name)
            recent_trades = self._get_recent_trade_samples_unified(exchange_name, limit=200)
            profitability_report = ProfitabilityValidator().evaluate_strategy(
                recent_trades=recent_trades,
                policy=dict(layer_settings.get('profitability_validation', {}) or {}),
            )
            profitability_blocked = bool(
                (layer_settings.get('profitability_validation', {}) or {}).get('enabled', False)
            ) and not bool(profitability_report.get('enabled', True))
            if profitability_blocked:
                self.logger.warning(
                    f"⚠️ {exchange_name} 기본/confirm 후보 수익성 정책 차단: "
                    f"{profitability_report.get('reasons', [])} · independent 전략은 버전별 검증 사용"
                )
            if profitability_report.get('stage') in {'limited_live_learning', 'recovery_learning'}:
                stage_label = (
                    '성과회복 제한 운용'
                    if profitability_report.get('stage') == 'recovery_learning'
                    else '신규/데이터부족 제한 운용'
                )
                self.logger.info(
                    f"🌱 {exchange_name} {stage_label}: "
                    f"거래 {profitability_report.get('total_trades', 0)}/{profitability_report.get('next_review_at_trades')} · "
                    f"위험배수 {profitability_report.get('risk_multiplier', 0.1):.2f} · "
                    f"최대포지션 {profitability_report.get('max_positions', 1)} · "
                    f"최대레버리지 {profitability_report.get('max_leverage', 1)}x"
                )

            self.portfolio_allocation_cache[exchange_name] = self._build_portfolio_allocation_unified(
                exchange_name,
                selected_coins,
                analysis_results,
                layer_settings,
            )
            strategy_runtime_state = self._build_strategy_runtime_state_unified(exchange_name, recent_trades)
            strategy_engine = StrategyEngine()
            cycle_metrics = {'attempted': 0, 'failed': 0, 'latencies': [], 'slippages': []}

            # 3. 거래 실행
            trades_executed = 0
            for coin in selected_coins:
                if not self.monitoring_flags.get(exchange_name, False):
                    self.logger.info(f"⏹️ {exchange_name} 중단 신호 감지: 사이클 중단")
                    break
                symbol = coin.get('symbol', '')
                analysis = analysis_results.get(symbol, {})
                # 🔥 상세 분석 과정 로깅 (거래소 정보 포함)
                self.logger.info(f"[{symbol}] 분석 과정 상세: (ex={exchange_name})")
                self.logger.info(f"   • 시그널: {analysis.get('signal', 'HOLD')} (ex={exchange_name})")
                self.logger.info(f"   • 신뢰도: {analysis.get('confidence', 0):.2f} (ex={exchange_name})")

                # 트렌드 정보
                trend = analysis.get('trend', 'UNKNOWN')
                if trend:
                    trend_str = str(trend).split('.')[-1] if hasattr(trend, 'value') else str(trend)
                    self.logger.info(f"   • 트렌드: {trend_str} (ex={exchange_name})")

                # 변동성 정보
                volatility = analysis.get('market_volatility', 0)
                self.logger.info(f"   • 변동성: {volatility:.2f}% (ex={exchange_name})")

                # 지지/저항 레벨
                support_level = analysis.get('support_level', 0)
                resistance_level = analysis.get('resistance_level', 0)
                self.logger.info(f"   • 지지 레벨: {support_level:.4f} (ex={exchange_name})")
                self.logger.info(f"   • 저항 레벨: {resistance_level:.4f} (ex={exchange_name})")

                # 기술적 지표들
                rsi = analysis.get('rsi', 0)
                macd = analysis.get('macd', 0)
                bb_position = analysis.get('bb_position', 0)
                ma20 = analysis.get('ma20', 0)
                ma50 = analysis.get('ma50', 0)

                self.logger.info(f"   • RSI: {rsi:.2f} (ex={exchange_name})")
                self.logger.info(f"   • MACD: {macd:.4f} (ex={exchange_name})")
                self.logger.info(f"   • 볼린저밴드 위치: {bb_position:.2f} (ex={exchange_name})")
                self.logger.info(f"   • 이동평균 20: {ma20:.4f} (ex={exchange_name})")
                self.logger.info(f"   • 이동평균 50: {ma50:.4f} (ex={exchange_name})")

                # 추론 정보
                reason = analysis.get('reason', '')
                if reason:
                    self.logger.info(f"   • 추론: {reason} (ex={exchange_name})")

                self.logger.info(f"{symbol} 분석 완료 - 시그널: {analysis.get('signal', 'HOLD')} (ex={exchange_name})")

                from .custom_strategy_validator import enrich_advanced_indicator_context
                strategy_pool = getattr(self, 'active_custom_strategy_pool', []) or []
                analysis = enrich_advanced_indicator_context(
                    analysis,
                    strategy_pool,
                    lambda timeframe, limit: self.exchange_manager.get_klines(
                        symbol,
                        interval=timeframe,
                        limit=limit,
                        exchange_name=exchange_name,
                    ),
                )
                runtime_strategy_context = dict(
                    (
                        getattr(
                            self,
                            '_custom_strategy_runtime_context_by_exchange',
                            {},
                        )
                        or {}
                    ).get(exchange_name, {})
                    or {}
                )
                analysis['_strategy_performance'] = dict(
                    runtime_strategy_context.get('performance', {}) or {}
                )
                candidate = evaluate_trade_candidate(
                    symbol=symbol,
                    context=analysis,
                    strategy_pool=strategy_pool,
                    asset_class="crypto",
                    target=exchange_name,
                    market_regime=str(
                        (getattr(self, 'last_market_regime_by_exchange', {}) or {}).get(
                            exchange_name, 'range'
                        )
                    ),
                )
                analysis = apply_trade_candidate(analysis, candidate)
                learning_scope = getattr(self, 'learning_enabled_exchanges', None)
                if learning_scope is None:
                    learning_scope = self._compute_learning_enabled_exchanges()
                    self.learning_enabled_exchanges = learning_scope
                if exchange_name in learning_scope and not learning_only:
                    self._generate_ai_learning_data(exchange_name, symbol, analysis)
                if not candidate.allowed:
                    if learning_only and exchange_name in learning_scope:
                        learning_payload = dict(analysis)
                        learning_payload['_learning_decision'] = 'candidate_blocked'
                        learning_payload['_learning_block_reason'] = str(candidate.reason)
                        self._generate_ai_learning_data(exchange_name, symbol, learning_payload)
                    self.logger.info(
                        f"⏸️ {exchange_name} {symbol} AI 커스텀 HOLD - 현재 범위·국면·진입조건 미충족: "
                        f"{candidate.reason}"
                    )
                    self._remember_trade_decision(
                        exchange_name, symbol, 'hold',
                        f'AI 커스텀 후보 차단: {candidate.reason}',
                        signal=str(analysis.get('signal', 'HOLD')),
                    )
                    continue
                if candidate.strategy_name:
                    self.logger.info(
                        f"🧠 {exchange_name} {symbol} AI 커스텀 선택: "
                        f"{candidate.strategy_name} (버전={candidate.strategy_version_id or '-'}, "
                        f"방식={candidate.strategy_role}, 운용={candidate.operation_mode}, "
                        f"국면={candidate.market_regime}, 국면기준={candidate.regime_scope}, "
                        f"후보출처={candidate.signal_source}, "
                        f"위험예산={candidate.engine_settings.get('risk_per_trade_percent', '-')}, "
                        f"TP={candidate.engine_settings.get('tp_percent', '-')}, "
                        f"SL={candidate.engine_settings.get('sl_percent', '-')})"
                    )

                if profitability_blocked and candidate.requires_noah_strategy_policy:
                    if learning_only and exchange_name in learning_scope:
                        learning_payload = dict(analysis)
                        learning_payload['_learning_decision'] = 'profitability_blocked'
                        learning_payload['_learning_block_reason'] = str(
                            profitability_report.get('reasons', [])
                        )
                        self._generate_ai_learning_data(exchange_name, symbol, learning_payload)
                    self.logger.warning(
                        f"⛔ {exchange_name} {symbol} 기본/confirm 후보 수익성 검증 차단: "
                        f"{profitability_report.get('reasons', [])}"
                    )
                    self._remember_trade_decision(
                        exchange_name, symbol, 'blocked',
                        f"수익성 검증 차단: {profitability_report.get('reasons', [])}",
                        signal=str(analysis.get('signal', 'HOLD')),
                    )
                    continue

                if (
                    profitability_report.get('stage') in {'limited_live_learning', 'recovery_learning'}
                    and candidate.requires_noah_strategy_policy
                ):
                    analysis['_cold_start_profile'] = dict(profitability_report)

                if analysis.get('signal') in ['LONG', 'SHORT'] and candidate.requires_noah_strategy_policy:
                    strategy_allowed, strategy_meta = strategy_engine.should_trade(
                        symbol=symbol,
                        analysis_result={
                            'score': float(analysis.get('confidence', 0.0) or 0.0) * 100.0,
                            'momentum': float(analysis.get('price_change', analysis.get('market_volatility', 0.0)) or 0.0),
                        },
                        runtime_state=strategy_runtime_state,
                        policy=dict(layer_settings.get('strategy_engine', {}) or {}),
                    )
                    if not strategy_allowed:
                        if learning_only and exchange_name in learning_scope:
                            learning_payload = dict(analysis)
                            learning_payload['_learning_decision'] = 'strategy_guardrail_blocked'
                            learning_payload['_learning_block_reason'] = str(
                                strategy_meta.get('reasons', [])
                            )
                            self._generate_ai_learning_data(exchange_name, symbol, learning_payload)
                        custom_name = analysis.get('_selected_custom_strategy', '기본 AI')
                        self.logger.warning(
                            f"⛔ {exchange_name} {symbol} {custom_name} HOLD - 후행 전략 가드레일 차단: "
                            f"{strategy_meta.get('reasons', [])}"
                        )
                        self._remember_trade_decision(
                            exchange_name, symbol, 'blocked',
                            f"전략 가드레일 차단: {strategy_meta.get('reasons', [])}",
                            signal=str(analysis.get('signal', 'HOLD')),
                        )
                        continue

                if analysis.get('signal') in ['LONG', 'SHORT']:
                    self.logger.info(f"[{symbol}] 거래 실행 시작 - 시그널: {analysis.get('signal')} (ex={exchange_name})")

                    # 거래 실행
                    if learning_only:
                        analysis['_learning_only'] = True
                    trade_result = self._execute_signal_trade(exchange_name, symbol, analysis)
                    status = trade_result.get('status')
                    self._remember_trade_decision(
                        exchange_name,
                        symbol,
                        str(status or 'unknown'),
                        str(trade_result.get('reason') or trade_result.get('error') or '주문 처리'),
                        signal=str(analysis.get('signal', 'HOLD')),
                        trade_plan=dict(trade_result.get('trade_plan') or {}),
                    )
                    if learning_only:
                        if exchange_name in learning_scope:
                            learning_payload = dict(analysis)
                            learning_payload['_learning_decision'] = str(status or 'unknown')
                            learning_payload['_learning_block_reason'] = str(
                                trade_result.get('reason') or trade_result.get('error') or ''
                            )
                            learning_payload['_learning_trade_plan'] = dict(
                                trade_result.get('trade_plan') or {}
                            )
                            self._generate_ai_learning_data(exchange_name, symbol, learning_payload)
                        self.logger.info(
                            f"🧠 {exchange_name} {symbol} LEARNING 전체 판단 완료 - "
                            f"후보={candidate.final_signal}, 출처={candidate.signal_source}, "
                            f"전략={candidate.strategy_name or '기본 AI'}, 결과={status} · 실제 주문 0건"
                        )
                        continue
                    cycle_metrics['attempted'] += 1
                    latency_ms = float(trade_result.get('latency_ms', 0.0) or 0.0)
                    slippage_bps = float(trade_result.get('slippage_bps', 0.0) or 0.0)
                    if latency_ms > 0:
                        cycle_metrics['latencies'].append(latency_ms)
                    if slippage_bps != 0.0:
                        cycle_metrics['slippages'].append(slippage_bps)
                    if status == 'success':
                        trades_executed += 1
                        strategy_runtime_state[f'last_trade_at::{symbol.upper()}'] = datetime.now()
                        self.logger.info(f"✅ {exchange_name} {symbol} 거래 실행 성공")
                        self.logger.info(f"{symbol} 거래 실행 성공 (ex={exchange_name})")
                    elif status == 'skipped':
                        reason = trade_result.get('reason', '사유 미상')
                        # 실패가 아니라 정책적 미실행이므로 '정보' 수준으로 명확히 표기
                        self.logger.info(f"⏭️ {exchange_name} {symbol} 거래 미실행(SKIP): {reason}")
                        self.logger.info(f"{symbol} 거래 미실행(SKIP): {reason} (ex={exchange_name})")
                    else:
                        cycle_metrics['failed'] += 1
                        err = trade_result.get('error', 'Unknown error')
                        self.logger.warning(f"❌ {exchange_name} {symbol} 거래 실행 실패: {err}")
                        self.logger.warning(f"{symbol} 거래 실행 실패: {err} (ex={exchange_name})")
                else:
                    if learning_only and exchange_name in learning_scope:
                        learning_payload = dict(analysis)
                        learning_payload['_learning_decision'] = 'hold'
                        learning_payload['_learning_block_reason'] = str(
                            analysis.get('reason') or f"final_signal={analysis.get('signal', 'HOLD')}"
                        )
                        self._generate_ai_learning_data(exchange_name, symbol, learning_payload)
                    # HOLD 신호인 경우에도 상세 로그 출력
                    self.logger.info(f"[{symbol}] 거래 시그널 없음 - {analysis.get('signal', 'HOLD')} (거래 실행 생략) (ex={exchange_name})")

                    # HOLD 사유를 간단히 도출해 사용자에게 전달(분석 요약)
                    hold_reason = ''
                    try:
                        pre = self._perform_pre_entry_analysis_unified(exchange_name, symbol, analysis)
                        if isinstance(pre, dict):
                            hold_reason = pre.get('reason', '')
                    except Exception:
                        hold_reason = ''
                    if hold_reason:
                        self.logger.info(f"⏸️ {exchange_name} {symbol} 거래 신호 없음(HOLD): {hold_reason}")
                        self.logger.info(f"{symbol} 신호 없음(HOLD): {hold_reason} (ex={exchange_name})")
                        self._remember_trade_decision(
                            exchange_name, symbol, 'hold', hold_reason,
                            signal=str(analysis.get('signal', 'HOLD')),
                        )
                    else:
                        self.logger.info(f"⏸️ {exchange_name} {symbol} 거래 신호 없음: {analysis.get('signal', 'HOLD')}")
                        self.logger.info(f"{symbol} 신호 없음: {analysis.get('signal', 'HOLD')} (ex={exchange_name})")
                        self._remember_trade_decision(
                            exchange_name,
                            symbol,
                            'hold',
                            str(analysis.get('reason') or f"최종 신호 {analysis.get('signal', 'HOLD')}"),
                            signal=str(analysis.get('signal', 'HOLD')),
                        )

            # 4. 포지션 모니터링
            self._monitor_exchange_positions(exchange_name)

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
            self.cycle_execution_metrics[exchange_name] = {
                'attempted_orders': attempts,
                'failed_orders': failed,
                'avg_latency_ms': round(avg_latency, 2),
                'avg_slippage_bps': round(avg_slippage, 2),
                'quality_score': quality_score,
                'anomalies': anomalies,
                'rollback_action': ops_engine.build_rollback_action(anomalies, dict(layer_settings.get('ops_automation', {}) or {})),
                'daily_briefing': ops_engine.build_daily_briefing(
                    {
                        'orders_executed': trades_executed,
                        'execution_metrics': {
                            'quality_score': quality_score,
                            'reject_rate': reject_rate,
                            'avg_slippage_bps': avg_slippage,
                        },
                    },
                    anomalies,
                ),
                'profitability_validation': profitability_report,
                'learning_only': learning_only,
            }

            if learning_only:
                self.logger.info(
                    f"🧠 {exchange_name} LEARNING 판단 사이클 완료: 실제 주문 0개 "
                    "(기본 AI·AI 커스텀·안전 경계 판단 기록)"
                )
            else:
                self.logger.info(f"✅ {exchange_name} 거래 사이클 완료: {trades_executed}개 거래 실행")
                self.logger.info(f"거래 사이클 완료: {trades_executed}개 거래 실행 (ex={exchange_name})")

        except Exception as e:
            self.logger.error(f"{exchange_name} 거래 사이클 실패: {e}")

    def _execute_signal_trade(self, exchange_name: str, symbol: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """거래소별 신호 거래 실행 (AI 기반 고급 거래 실행)"""
        opportunity_auth = None
        crypto_command_id = ""
        try:
            signal = analysis.get('signal', 'HOLD')
            confidence = analysis.get('confidence', 0.0)
            learning_only = bool(analysis.get('_learning_only', False))
            independent_custom = analysis.get('_custom_signal_mode') == 'independent'
            custom_engine_settings = dict(analysis.get('_custom_engine_settings') or {})

            # 거래 모드 확인
            try:
                execution_mode = self._execution_mode(exchange_name)
                paper = execution_mode == ExecutionMode.PAPER
                demo = bool(self.settings.get('demo_mode', False)) if isinstance(self.settings, dict) else False

                if demo:
                    try:
                        from path_utils import get_current_user_account
                        from utils.admin_utils import is_admin_account

                        current_user = get_current_user_account() or self.settings.get('user_id') or self.settings.get('username')
                        if not is_admin_account(current_user):
                            self.logger.warning("⛔ 관리자 계정이 아니므로 demo_mode를 무시합니다.")
                            demo = False
                        else:
                            paper = True
                    except Exception as admin_check_err:
                        self.logger.warning(f"⚠️ 데모 모드 권한 확인 실패로 demo_mode를 비활성화합니다: {admin_check_err}")
                        demo = False
            except Exception:
                execution_mode = self._execution_mode(exchange_name)
                paper = execution_mode == ExecutionMode.PAPER
                demo = False

            halt = (getattr(self, "_entry_halts", {}) or {}).get(str(exchange_name).lower())
            if halt and not paper and not learning_only:
                return {
                    "status": "skipped",
                    "reason": (
                        "주문 상태/청산 오류가 아직 조정되지 않아 신규 진입을 중단했습니다: "
                        f"{halt.get('category', 'unknown')} - {halt.get('reason', '')}"
                    ),
                    "entry_halt": dict(halt),
                }

            # 현물의 SHORT 신호는 신규 공매도 주문이 아니다. NoahAI가 실제로
            # 진입해 소유권 원장이 있는 LONG만 청산하고, 기존 수동 보유자산은
            # 신호가 와도 절대 매도하지 않는다.
            if str(exchange_name or '').lower() in {'upbit', 'bithumb'} and str(signal).upper() == 'SHORT':
                position_store = self._position_store(exchange_name)
                target_key = normalize_position_symbol(symbol)
                managed_item = next(
                    (
                        (stored_symbol, candidate)
                        for stored_symbol, candidate in position_store.items()
                        if normalize_position_symbol(stored_symbol) == target_key
                        and is_noah_managed_position(candidate)
                    ),
                    None,
                )
                if managed_item is None:
                    return {
                        'status': 'skipped',
                        'reason': (
                            '현물 SHORT는 신규 공매도가 아닙니다. '
                            'NoahAI가 진입한 LONG 포지션이 없어 수동 보유자산을 보호했습니다'
                        ),
                    }
                if learning_only:
                    return {
                        'status': 'learning_planned',
                        'reason': 'LEARNING 모드: 현물 LONG 청산 판단만 기록하고 주문은 제출하지 않음',
                    }
                stored_symbol, managed_position = managed_item
                try:
                    close_price = float(
                        self.exchange_manager.get_current_price(stored_symbol, exchange_name)
                        if hasattr(self, 'exchange_manager') else 0.0
                    )
                except Exception:
                    close_price = float(getattr(managed_position, 'current_price', 0.0) or 0.0)
                closed = self._close_position_unified(
                    exchange_name, stored_symbol, managed_position, close_price
                )
                return {
                    'status': 'success' if closed else 'error',
                    'reason': (
                        '현물 SHORT 신호를 NoahAI 관리 LONG 청산으로 실행'
                        if closed else '현물 관리 LONG 청산 실패'
                    ),
                }

            # 데모 모드에서 신호 향상
            if demo and hasattr(self, 'demo_trader'):
                enhanced_signal, enhanced_confidence = self.demo_trader.enhance_signal(signal, confidence)
                signal = enhanced_signal
                confidence = enhanced_confidence
                self.logger.debug(f"🎭 [DEMO] 신호 향상: {analysis.get('signal', 'HOLD')} → {signal}, 신뢰도: {confidence:.2f}")

            # 리스크 관리: 코인 스킵 체크
            if not paper and self.risk_manager and self.risk_manager.should_skip_coin(symbol):
                return {'status': 'skipped', 'reason': f'리스크 관리로 스킵: {symbol}'}

            # 리스크 관리: 일일 손실 한도 체크
            if not paper and self.risk_manager and self.risk_manager.check_daily_loss_limit():
                return {'status': 'skipped', 'reason': '일일 손실 한도 초과'}

            if independent_custom:
                # 고급 AI 커스텀은 사용자 전략 원형이 주 전략이다. NoahAI의
                # 진입 재심사·동적 임계값·동적 TP/SL로 전략을 다시 쓰지 않는다.
                requested_tp = float(custom_engine_settings.get('tp_percent', 0.0) or 0.0)
                requested_sl = float(custom_engine_settings.get('sl_percent', 0.0) or 0.0)
                if requested_tp <= 0.0 or requested_sl <= 0.0:
                    return {
                        'status': 'skipped',
                        'reason': (
                            '고급 커스텀 전략 청산계획 누락: '
                            f'tp={requested_tp:.6f}, sl={requested_sl:.6f}'
                        ),
                    }
                analysis['tp_percent'] = requested_tp
                analysis['sl_percent'] = requested_sl
                pre_entry_analysis = {
                    'proceed': True,
                    'reason': 'independent_custom_strategy_integrity',
                    'strategy_integrity_preserved': True,
                }
                self._log_trade_event(
                    'analysis',
                    (
                        f"{symbol} 고급 커스텀 전략 청산값 원형 유지: "
                        f"tp={requested_tp:.6f}({requested_tp*100:.3f}%), "
                        f"sl={requested_sl:.6f}({requested_sl*100:.3f}%)"
                    ),
                    exchange=exchange_name,
                )
            else:
                # 기본·일반 경로에서만 NoahAI 진입 재심사와 동적 계획을 적용한다.
                pre_entry_analysis = self._perform_pre_entry_analysis_unified(exchange_name, symbol, analysis)
                if not pre_entry_analysis['proceed']:
                    return {'status': 'skipped', 'reason': f'AI 진입 전 분석 실패: {pre_entry_analysis["reason"]}'}

                dynamic_tp_sl = self._calculate_dynamic_tp_sl_unified(exchange_name, symbol, analysis)
                if dynamic_tp_sl.get('rr_guardrail_enabled', False) and not dynamic_tp_sl.get('rr_guardrail_passed', True):
                    rr_after = float(dynamic_tp_sl.get('rr_after', 0.0) or 0.0)
                    rr_min = float(dynamic_tp_sl.get('rr_min', 2.0) or 2.0)
                    return {
                        'status': 'skipped',
                        'reason': f'RR 가드레일 미충족: {rr_after:.2f} < {rr_min:.2f}'
                    }

                analysis['tp_percent'] = dynamic_tp_sl['tp']
                analysis['sl_percent'] = dynamic_tp_sl['sl']

                if self.settings.get('verbose_trade_logging', False):
                    self._log_trade_event('analysis', f"{symbol} 동적 TP/SL 계산: tp={dynamic_tp_sl['tp']:.6f}({dynamic_tp_sl['tp']*100:.3f}%), sl={dynamic_tp_sl['sl']:.6f}({dynamic_tp_sl['sl']*100:.3f}%)", exchange=exchange_name)

                pattern_decision = self._analyze_pattern_similarity_unified(exchange_name, symbol, analysis)
                if pattern_decision.get('action') == 'SKIP':
                    return {'status': 'skipped', 'reason': f'패턴 유사성 분석: SKIP - {pattern_decision.get("reason", "")}'}
                if pattern_decision.get('action') == 'ADJUST':
                    analysis = self._apply_pattern_adjustments(analysis, pattern_decision)

                dynamic_threshold = self._calculate_dynamic_confidence_threshold_unified(exchange_name, symbol, analysis)
                if confidence < dynamic_threshold:
                    return {'status': 'skipped', 'reason': f'동적 신뢰도 부족: {confidence:.2f} < {dynamic_threshold:.2f}'}

            # 리스크 분석 로그 (verbose)
            try:
                if isinstance(self.settings, dict) and self.settings.get('verbose_trade_logging', False):
                    qty = float(analysis.get('qty', 0) or 0)
                    entry_price = float(analysis.get('price', 0) or 0)
                    leverage = int(self.settings.get('default_leverage', 1))
                    position_value = qty * entry_price
                    # 통합 경로에서는 잔고 조회가 거래소별로 다르므로 추정치로 기록
                    position_ratio = 0.0
                    try:
                        bal_dict = self.exchange_manager.get_exchange_balance(exchange_name, force_refresh=False) if hasattr(self, 'exchange_manager') else {}
                        # Dict에서 잔고 추출: 'balance' 키에서 USDT 값 가져오기
                        if isinstance(bal_dict, dict) and bal_dict.get('status') == 'success':
                            balance_data = bal_dict.get('balance', {})
                            # USDT 잔고 추출 (바이낸스는 'USDT', CCXT는 'USDT' 키)
                            usdt_balance = 0.0
                            if isinstance(balance_data, dict):
                                usdt_balance = float(balance_data.get('USDT', {}).get('free', 0) or 0)
                            if usdt_balance > 0:
                                position_ratio = (position_value / usdt_balance) * 100
                    except Exception:
                        pass
                    liquidation_distance = (1 / leverage) * 100 if leverage > 0 else 0
                    self._log_trade_event('analysis', f"{symbol} Risk analysis: position_ratio={position_ratio:.2f}%, leverage={leverage}x, liquidation_distance={liquidation_distance:.1f}%", exchange=exchange_name)
            except Exception:
                pass

            # 포지션 수 체크
            active_positions = self._position_store(exchange_name)
            if symbol in active_positions:
                return {
                    'status': 'skipped',
                    'reason': f'동일 종목 포지션이 이미 관리 중입니다: {symbol}',
                }
            # max_positions은 AI/동적 파라미터로만 결정 (수동 설정 완전 제거)
            max_positions = self._get_ai_max_positions(exchange_name)
            cold_start = dict(analysis.get('_cold_start_profile', {}) or {})
            if cold_start:
                max_positions = min(max_positions, int(cold_start.get('max_positions', 1) or 1))

            external_count = len(
                (getattr(self, 'external_position_symbols', {}) or {}).get(exchange_name, set())
            )
            effective_count = len(active_positions) + external_count
            if effective_count >= max_positions:
                return {
                    'status': 'skipped',
                    'reason': (
                        f'최대 포지션 수 초과: 관리 {len(active_positions)} + '
                        f'수동/외부 {external_count} = {effective_count} >= {max_positions}'
                    ),
                }

            # AI 강화 파라미터 적용
            optimized_params = self._get_ai_enhanced_parameters_unified(exchange_name, symbol, analysis, pre_entry_analysis)
            optimized_params = apply_engine_settings_to_trade_config(
                optimized_params, analysis.get('_custom_engine_settings', {}) or {}
            )
            optimized_params['_selected_custom_strategy'] = analysis.get('_selected_custom_strategy')
            optimized_params['_selected_custom_strategy_id'] = analysis.get('_selected_custom_strategy_id')
            optimized_params['_selected_custom_strategy_key'] = analysis.get('_selected_custom_strategy_key')
            optimized_params['_selected_custom_strategy_version_id'] = analysis.get('_selected_custom_strategy_version_id')
            optimized_params['_custom_signal_mode'] = analysis.get('_custom_signal_mode')
            optimized_params['_custom_operation_mode'] = analysis.get('_custom_operation_mode')
            optimized_params['_exit_plan'] = dict(analysis.get('_exit_plan') or {})
            optimized_params['_custom_strategy_rules'] = dict(analysis.get('_custom_strategy_rules') or {})
            exit_plan = dict(optimized_params.get('_exit_plan') or {})
            optimized_params['_exit_policy'] = build_exit_policy(
                settings=self.settings,
                exit_plan=exit_plan,
                effective_tp_fraction=optimized_params.get('tp_percent', 0.0),
                effective_sl_fraction=optimized_params.get('sl_percent', 0.0),
                effective_reason=(
                    'AI 커스텀 전략 원형'
                    if exit_plan.get('strategy_owned')
                    else '종목·변동성 기반 동적 청산'
                ),
                entry_price=analysis.get('current_price', analysis.get('price', 0.0)),
                side=signal,
                asset_class='crypto',
                target=exchange_name,
                symbol=symbol,
            )
            self.logger.info(
                f"{exchange_name} {symbol} "
                f"{format_exit_policy(optimized_params['_exit_policy'])}"
            )

            # 거래 실행
            exchange_client = self.get_exchange_client(exchange_name)
            if not exchange_client and not paper and not learning_only:
                return {'status': 'error', 'error': '거래소 클라이언트 없음'}

            # 포지션 크기 계산 및 최소 노셔널 보정
            position_size = self._calculate_position_size_unified(exchange_name, symbol, analysis, optimized_params)
            if cold_start:
                position_size *= float(cold_start.get('risk_multiplier', 0.10) or 0.10)
            try:
                current_price_hint = self.exchange_manager.get_current_price(symbol, exchange_name) if hasattr(self, 'exchange_manager') else 0.0
            except Exception:
                current_price_hint = 0.0

            # LIVE KRW 현물은 실제 계좌 잔고와 앱 원장을 주문 전에 조정한다.
            # PAPER/LEARNING은 개인 잔고 API를 호출하지 않는다.
            if (
                not paper
                and not learning_only
                and str(exchange_name or '').lower() in {'upbit', 'bithumb'}
            ):
                if signal.upper() != 'LONG':
                    return {
                        'status': 'skipped',
                        'reason': '현물 신규 진입은 보유하지 않은 자산 매도를 허용하지 않습니다',
                    }
                from trading.spot_position_policy import (
                    assess_spot_holding,
                    spot_base_asset,
                    summarize_spot_portfolio,
                )
                try:
                    actual_balance = exchange_client.get_balance() if exchange_client else {}
                except Exception:
                    actual_balance = {}
                if not isinstance(actual_balance, dict) or not actual_balance:
                    return {
                        'status': 'skipped',
                        'reason': '현물 실제 잔고 확인 실패 - 신규 주문을 안전 차단했습니다',
                    }
                holding = assess_spot_holding(actual_balance, symbol, current_price_hint)
                if holding.is_material:
                    return {
                        'status': 'skipped',
                        'reason': (
                            '앱 원장에 없는 기존 보유자산이 최소 주문금액 이상입니다: '
                            f'{holding.asset} {holding.notional:,.0f} KRW'
                        ),
                    }
                prices_by_asset = {holding.asset: float(current_price_hint or 0.0)}
                try:
                    raw_exchange = getattr(exchange_client, 'exchange', None)
                    tickers = (
                        raw_exchange.fetch_tickers()
                        if raw_exchange is not None and hasattr(raw_exchange, 'fetch_tickers')
                        else {}
                    ) or {}
                    for market_symbol, ticker in tickers.items():
                        market_text = str(market_symbol or '').upper()
                        if 'KRW' not in market_text:
                            continue
                        asset = spot_base_asset(market_text)
                        if isinstance(ticker, dict):
                            price = float(ticker.get('last') or ticker.get('close') or 0.0)
                            if price > 0:
                                prices_by_asset[asset] = price
                except Exception as ticker_exc:
                    self.logger.warning(
                        f"{exchange_name} 현물 전체 보유자산 가격 분류 일부 생략: {ticker_exc}"
                    )
                managed_assets = {
                    spot_base_asset(position_symbol)
                    for position_symbol in active_positions.keys()
                }
                portfolio = summarize_spot_portfolio(
                    actual_balance,
                    prices_by_asset,
                    managed_assets=managed_assets,
                )
                effective_position_count = len(active_positions) + len(portfolio.material_assets)
                if effective_position_count >= max_positions:
                    return {
                        'status': 'skipped',
                        'reason': (
                            '앱 포지션과 기존 중요 현물 보유를 합산한 최대 포지션 수 초과: '
                            f'{effective_position_count} >= {max_positions}'
                        ),
                    }
                if portfolio.unknown_price_assets:
                    self.logger.warning(
                        f"{exchange_name} 가격 미확인 현물 보유자산: "
                        f"{sorted(portfolio.unknown_price_assets)}"
                    )
                optimized_params['_spot_baseline_quantity'] = holding.quantity
                optimized_params['_spot_holding_classification'] = holding.classification
            allocation_result = self.portfolio_allocation_cache.get(exchange_name, {}) if isinstance(self.portfolio_allocation_cache, dict) else {}
            if allocation_result:
                try:
                    allocated_size = PortfolioOrchestrator().quantity_from_allocation(
                        symbol=symbol,
                        price=float(current_price_hint or 0.0),
                        fallback_qty=position_size,
                        allocation_result=allocation_result,
                    )
                    position_size = (
                        min(position_size, allocated_size)
                        if independent_custom and position_size > 0 and allocated_size > 0
                        else allocated_size
                    )
                except Exception:
                    pass
            try:
                adjusted_size, adjust_note = self._ensure_min_notional(exchange_name, symbol, position_size)
                if adjust_note:
                    self.logger.info(f"🔧 {exchange_name} {symbol} 최소 노셔널 보정: {adjust_note}")
                position_size = adjusted_size
            except Exception as exc:
                self.logger.error(
                    f"❌ {exchange_name} {symbol} 최소 주문 규격 검증 실패: {exc}"
                )
                return {
                    'status': 'skipped',
                    'reason': f'최소 주문 규격 검증 실패: {exc}',
                }

            # 레버리지 기본값 설정 (try 블록 밖에서 선언)
            desired_leverage_raw = optimized_params.get(
                'leverage',
                self.settings.get('default_leverage', 10),
            )
            leverage_policy = self._effective_leverage_policy(
                exchange_name,
                desired_leverage_raw,
                cold_start=cold_start,
            )
            leverage = int(leverage_policy['effective'])
            optimized_params['leverage'] = leverage
            optimized_params['_leverage_policy'] = leverage_policy
            if not isinstance(getattr(self, 'last_effective_trade_params', None), dict):
                self.last_effective_trade_params = {}
            self.last_effective_trade_params.setdefault(exchange_name, {})[symbol] = {
                'configured_leverage': int(leverage_policy['configured']),
                'effective_leverage': leverage,
                'leverage_reason': str(leverage_policy['reason']),
                'tp_percent': float(optimized_params.get('tp_percent', 0.0) or 0.0),
                'sl_percent': float(optimized_params.get('sl_percent', 0.0) or 0.0),
                'updated_at': datetime.now(timezone.utc).isoformat(),
            }

            authorized_targets = (
                list(getattr(self, "trade_enabled_exchanges", []) or [])
                if execution_mode == ExecutionMode.LIVE
                else list(getattr(self, "enabled_exchanges", []) or [])
            )
            opportunity_policy = policy_from_settings(
                self.settings,
                authorized_targets=authorized_targets,
            )
            minimum_validated_size = float(position_size or 0.0)
            opportunity_auth = get_opportunity_coordinator().authorize(
                policy=opportunity_policy,
                asset_class="crypto",
                target=exchange_name,
                symbol=symbol,
                direction=signal,
                quantity=position_size,
                price=float(current_price_hint or analysis.get("current_price", 0.0) or 0.0),
                stop_fraction=float(optimized_params.get("sl_percent", 0.0) or 0.0),
                strategy_version=str(
                    analysis.get("_selected_custom_strategy_version_id")
                    or "noah_base"
                ),
                account_scope=str(
                    self.settings.get("account_id")
                    or self.settings.get("user_id")
                    or f"{exchange_name}:{id(self)}"
                ),
                reserve=not learning_only,
            )
            optimized_params["_opportunity"] = opportunity_auth.to_dict()
            if not opportunity_auth.allowed:
                return {
                    "status": "skipped",
                    "reason": f"다중 거래소 기회 정책 차단: {opportunity_auth.reason}",
                    "opportunity": opportunity_auth.to_dict(),
                }
            position_size = float(opportunity_auth.authorized_quantity or 0.0)
            if position_size < minimum_validated_size * (1.0 - 1e-9):
                post_auth_size, post_auth_note = self._ensure_min_notional(
                    exchange_name,
                    symbol,
                    position_size,
                )
                if post_auth_size > position_size * (1.0 + 1e-9):
                    get_opportunity_coordinator().release(opportunity_auth)
                    return {
                        "status": "skipped",
                        "reason": f"위험 분할 후 거래소 최소 주문 규격 미달: {post_auth_note}",
                        "opportunity": opportunity_auth.to_dict(),
                    }
            self.logger.info(
                f"🔗 {exchange_name} {symbol} 기회연결: "
                f"id={opportunity_auth.opportunity_id}, mode={opportunity_auth.execution_mode}, "
                f"target={exchange_name}, qty_factor={opportunity_auth.quantity_factor:.4f}, "
                f"aggregate_targets={opportunity_auth.aggregate_targets}, "
                f"aggregate_loss={opportunity_auth.aggregate_estimated_loss:.4f} "
                f"{opportunity_auth.quote_currency}"
            )

            # LEARNING은 여기까지 기본/커스텀 후보, 수익성·전략 게이트,
            # pre-entry, 동적/전략 청산값, 포트폴리오·수량·최소 노셔널,
            # 레버리지 한도를 모두 평가한다. 이후 set_leverage/set_margin_type와
            # 주문 제출은 외부 상태를 바꾸므로 정확히 이 경계에서 차단한다.
            if learning_only:
                return {
                    'status': 'learning_planned',
                    'reason': 'LEARNING 모드: 전체 판단 완료 후 주문 제출 차단',
                    'trade_plan': {
                        'exchange': exchange_name,
                        'symbol': symbol,
                        'signal': signal,
                        'confidence': float(confidence or 0.0),
                        'quantity': float(position_size or 0.0),
                        'reference_price': float(current_price_hint or 0.0),
                        'leverage': int(leverage),
                        'tp_percent': float(optimized_params.get('tp_percent', 0.0) or 0.0),
                        'sl_percent': float(optimized_params.get('sl_percent', 0.0) or 0.0),
                        'strategy': analysis.get('_selected_custom_strategy') or '기본 AI',
                        'strategy_version': analysis.get('_selected_custom_strategy_version_id'),
                        'candidate_source': analysis.get('_candidate_source', 'base_ai'),
                        'exit_plan': dict(analysis.get('_exit_plan') or {}),
                        'exit_policy': dict(optimized_params.get('_exit_policy') or {}),
                        'opportunity': opportunity_auth.to_dict(),
                    },
                }

            # 외부 주문보다 먼저 영속 명령을 선점한다. 프로세스가 주문 응답 전에
            # 종료되어도 같은 명령을 다시 제출하지 않고 조정 대상으로 남긴다.
            if not paper and not demo:
                crypto_command_id = str(opportunity_auth.idempotency_key or "")
                if not crypto_command_id or not self.recorder:
                    get_opportunity_coordinator().release(opportunity_auth)
                    return {
                        "status": "skipped",
                        "reason": "영속 주문 명령 원장을 사용할 수 없어 LIVE 주문을 차단했습니다",
                    }
                claimed = self.recorder.claim_crypto_order_command(
                    command_id=crypto_command_id,
                    exchange=exchange_name,
                    symbol=symbol,
                    side=signal,
                    intent_type="entry",
                    quantity=position_size,
                )
                if not bool(claimed.get("claimed")):
                    get_opportunity_coordinator().release(opportunity_auth)
                    return {
                        "status": "skipped",
                        "reason": (
                            "동일 주문 명령이 이미 원장에 존재하여 중복 제출을 차단했습니다 "
                            f"(status={claimed.get('status')})"
                        ),
                        "command_id": crypto_command_id,
                    }
                self.recorder.update_crypto_order_command(
                    crypto_command_id, status="submitting", increment_attempt=True,
                )
                optimized_params["_client_order_id"] = exchange_client_order_id(crypto_command_id)

            # 레버리지/마진 타입 설정 (선물 거래소에서만)
            try:
                # CCXT 어댑터 여부에 따라 심볼 정규화
                normalized_symbol = self._normalize_symbol_for_adapter(exchange_client, symbol) if exchange_client else symbol
                is_futures_exchange = exchange_name in ['bybit', 'okx', 'bitget']  # 바이낸스 제외
                # 레버리지 가드레일 적용
                desired_leverage = leverage
                # 마진 타입 가드레일 적용
                default_margin_type = str(self.settings.get('default_margin_type', 'ISOLATED')).upper()
                if default_margin_type not in ('ISOLATED', 'CROSS', 'CROSSED'):
                    default_margin_type = 'ISOLATED'

                if is_futures_exchange and not paper:
                    # set_leverage
                    try:
                        set_lev = getattr(exchange_client, 'set_leverage', None)
                        if callable(set_lev):
                            ok = False
                            try:
                                ok = bool(set_lev(normalized_symbol, int(desired_leverage)))
                            except Exception as ie:
                                raise ie
                            if ok:
                                self.logger.info(f"⚙️ {exchange_name} {normalized_symbol} 레버리지 설정: {int(desired_leverage)}x")
                            else:
                                self.logger.warning(f"{exchange_name} 레버리지 설정 실패 또는 미지원")
                    except Exception as e:
                        self.logger.warning(f"{exchange_name} 레버리지 설정 실패(계속): {e}")
                    # set_margin_type / set_margin_mode
                    try:
                        mt = default_margin_type
                        # 바이낸스 네이티브 API 명칭 호환
                        if hasattr(exchange_client, 'client'):
                            # python-binance 경로 가능성: CROSSED 사용
                            if mt == 'CROSS':
                                mt = 'CROSSED'
                        set_mt = getattr(exchange_client, 'set_margin_type', None)
                        if not callable(set_mt):
                            # CCXT의 경우 set_margin_mode 사용
                            set_mt = getattr(exchange_client, 'set_margin_mode', None)
                        if callable(set_mt):
                            ok_mt = False
                            try:
                                ok_mt = bool(set_mt(normalized_symbol, mt))
                            except Exception as ime:
                                raise ime
                            if ok_mt:
                                self.logger.info(f"⚙️ {exchange_name} {normalized_symbol} 마진 타입 설정: {mt}")
                            else:
                                self.logger.warning(f"{exchange_name} 마진 타입 설정 실패 또는 미지원: {mt}")
                    except Exception as e:
                        self.logger.warning(f"{exchange_name} 마진 타입 설정 실패(계속): {e}")
            except Exception as e:
                self.logger.warning(f"레버리지/마진 설정 단계 경고(계속): {e}")

            # 주문 실행 (어댑터 심볼 규칙 적용 + 사이드 매핑 + 경로 통일)
            order_symbol = self._normalize_symbol_for_adapter(exchange_client, symbol) if exchange_client else symbol
            side_for_ccxt = 'buy' if signal.upper() == 'LONG' else ('sell' if signal.upper() == 'SHORT' else signal.lower())
            side_for_order = 'BUY' if signal.upper() == 'LONG' else ('SELL' if signal.upper() == 'SHORT' else signal.upper())

            order_result: Dict[str, Any] = {}
            try:
                # 데모 모드: 고성능 시뮬레이션
                if demo and hasattr(self, 'demo_trader'):
                    # 실제 가격 조회 (실제 데이터 사용)
                    current_price = self.exchange_manager.get_current_price(symbol, exchange_name) if hasattr(self, 'exchange_manager') else 50000.0

                    # 데모 모드 거래 실행 (TP/SL 포함)
                    tp_percent = optimized_params.get('tp_percent', 0.018) if isinstance(optimized_params, dict) else 0.018
                    sl_percent = optimized_params.get('sl_percent', 0.020) if isinstance(optimized_params, dict) else 0.020

                    order_result = self.demo_trader.simulate_trade_execution(
                        exchange_name=exchange_name,
                        symbol=order_symbol,
                        side=side_for_ccxt,
                        quantity=position_size,
                        price=current_price,
                        leverage=leverage,
                        tp_percent=tp_percent,
                        sl_percent=sl_percent
                    )

                    # 데모 거래 로그 출력
                    self.demo_trader.log_demo_trade(order_result, exchange_name)

                # paper_trading 모드: 네트워크 호출 없이 성공 결과 시뮬레이션
                elif paper:
                    now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
                    order_result = {
                        'status': 'success',
                        'order_id': f"paper-{exchange_name}-{symbol}-{now_ts}",
                        'symbol': order_symbol,
                        'side': side_for_ccxt,
                        'quantity': position_size,
                        'price': self.exchange_manager.get_current_price(symbol, exchange_name) if hasattr(self, 'exchange_manager') else None,
                        'order_type': 'market',
                        'timestamp': now_ts,
                        'simulated': True
                    }
                else:
                    # 가능 시 UnifiedTradingManager 경유로 표준화된 결과 사용
                    trading_type = 'futures' if exchange_name in ['bybit', 'okx', 'bitget'] else 'spot'  # 바이낸스 제외
                    unified_ex = None
                    try:
                        unified_ex = self.unified_manager.get_exchange(exchange_name, trading_type) if hasattr(self, 'unified_manager') and self.unified_manager else None
                    except Exception:
                        unified_ex = None

                    if not paper and unified_ex:
                        # CCXT 표준 경로
                        advanced_cfg = self._get_advanced_layers_settings(exchange_name)
                        execution_policy = dict(advanced_cfg.get('execution_optimizer', {}) or {})
                        execution_policy.setdefault('signal_strength', float(confidence or 0.0))
                        execution_policy.setdefault('volatility', float(analysis.get('market_volatility', 0.5) or 0.5) / 100.0)
                        order_result = cast(Dict[str, Any], self.unified_manager.place_order_with_quality_control(
                            exchange_name=exchange_name,
                            trading_type=trading_type,
                            symbol=order_symbol,
                            side=side_for_ccxt,
                            quantity=position_size,
                            price=None,
                            order_type='market',
                            policy=execution_policy,
                            client_order_id=(
                                exchange_client_order_id(crypto_command_id)
                                if crypto_command_id else None
                            ),
                        ))
                    elif not paper:
                        # 직접 클라이언트 경로
                        if exchange_client and hasattr(exchange_client, 'exchange'):
                            # CCXT 어댑터
                            order_result = exchange_client.place_order(
                                symbol=order_symbol,
                                side=side_for_ccxt,
                                order_type='market',
                                quantity=position_size,
                                client_order_id=(
                                    exchange_client_order_id(crypto_command_id)
                                    if crypto_command_id else None
                                ),
                            )
                        elif exchange_client:
                            # CCXT 어댑터만 지원 (바이낸스 제외)
                            if hasattr(exchange_client, 'exchange'):
                                # CCXT 어댑터
                                order_result = exchange_client.place_order(
                                    symbol=order_symbol,
                                    side=side_for_ccxt,
                                    order_type='market',
                                    quantity=position_size,
                                    client_order_id=(
                                        exchange_client_order_id(crypto_command_id)
                                        if crypto_command_id else None
                                    ),
                                )
                            else:
                                raise RuntimeError('CCXT 어댑터가 아닙니다')
                        else:
                            raise RuntimeError('exchange client unavailable')
            except Exception as e:
                self.logger.error(f"주문 실행 오류: {e}")
                order_result = {'status': 'error', 'error': str(e)}

            if not paper and isinstance(order_result, dict):
                order_result = self._confirm_ccxt_order_result(
                    exchange_client,
                    order_result,
                    symbol=order_symbol,
                )
                # 주문 접수는 항상 복구 원장에 남기되, 실제 체결 확정 전에는
                # 내부 포지션/trade_log를 만들지 않는다.
                self._record_exchange_execution(
                    exchange_name,
                    symbol,
                    side_for_ccxt,
                    order_result,
                    source='noahai_entry_order',
                )

            execution_confirmed = bool(
                paper
                or (isinstance(order_result, dict) and order_result.get('_execution_confirmed'))
            )
            if self._is_order_success(order_result) and execution_confirmed:
                if crypto_command_id and self.recorder:
                    self.recorder.update_crypto_order_command(
                        crypto_command_id,
                        status="confirmed",
                        exchange_order_id=str(
                            order_result.get("order_id") or order_result.get("id") or ""
                        ),
                    )
                get_opportunity_coordinator().record_result(
                    opportunity_auth,
                    status="paper_filled" if paper else "submitted",
                    order_id=str(
                        order_result.get("order_id")
                        or order_result.get("id")
                        or ""
                    ),
                )
                executed_quantity, executed_price, executed_notional = self._resolve_execution_values(
                    order_result=order_result,
                    fallback_quantity=position_size,
                    exchange_name=exchange_name,
                    symbol=symbol,
                )
                if executed_quantity > 0:
                    position_size = executed_quantity
                    order_result["quantity"] = executed_quantity
                    order_result.setdefault("filled", executed_quantity)
                if executed_price > 0:
                    order_result["price"] = executed_price
                if executed_notional > 0:
                    order_result["cost"] = executed_notional

                # 포지션 기록 (TP/SL 포함)
                self._record_position_with_tp_sl(
                    exchange_name,
                    symbol,
                    signal,
                    position_size,
                    order_result,
                    optimized_params,
                    execution_mode='demo' if demo else ('paper' if paper else 'live'),
                )

                # 바이낸스 실거래 시 TP/SL 주문 발주(지원 시)
                try:
                    paper_mode = False
                    try:
                        paper_mode = bool(self.settings.get('paper_trading', False)) if isinstance(self.settings, dict) else False
                    except Exception:
                        paper_mode = False
                    # 바이낸스는 trader.py에서 처리 (문서 가이드라인 준수)
                    if False and exchange_name == 'binance' and not paper_mode and hasattr(self.exchange_manager, 'binance_client'):
                        bc = getattr(self.exchange_manager, 'binance_client', None)
                        if bc and hasattr(bc, 'place_tp_sl_orders'):
                            # entry_price 산출
                            eprice = order_result.get('price') or 0.0
                            try:
                                eprice = float(eprice)
                            except Exception:
                                # 현재가 보정
                                cp = self.exchange_manager.get_current_price(symbol, exchange_name)
                                eprice = float(cp or 0.0)
                            # TP/SL 퍼센트
                            tp_pct = float(optimized_params.get('tp_percent', self.settings.get('default_tp', 0.0018))) if isinstance(optimized_params, dict) else 0.0018
                            sl_pct = float(optimized_params.get('sl_percent', self.settings.get('default_sl', 0.0020))) if isinstance(optimized_params, dict) else 0.0020
                            if eprice and eprice > 0:
                                if signal.upper() == 'LONG':
                                    tp_price = eprice * (1 + tp_pct)
                                    sl_price = eprice * (1 - sl_pct)
                                    pos_side = 'LONG'
                                else:
                                    tp_price = eprice * (1 - tp_pct)
                                    sl_price = eprice * (1 + sl_pct)
                                    pos_side = 'SHORT'
                                try:
                                    # 🔥 closePosition=True 사용 시 quantity 파라미터 불필요 (Binance API 규칙)
                                    # place_tp_sl_orders()는 내부에서 closePosition=True를 사용하므로 quantity는 무시됨
                                    bc.place_tp_sl_orders(symbol=symbol, position_side=pos_side, take_profit=tp_price, stop_loss=sl_price, quantity=None)
                                    self.logger.info(f"🛡️ {exchange_name} {symbol} TP/SL 주문 발주(TP:{tp_price:.6f}, SL:{sl_price:.6f})")
                                except Exception as tp_e:
                                    self.logger.warning(f"{exchange_name} {symbol} TP/SL 주문 발주 실패(계속): {tp_e}")
                    elif exchange_name in ('bybit', 'okx', 'bitget') and not paper_mode:
                        # 캐시에서 미지원으로 판정된 거래소는 즉시 스킵
                        try:
                            if self._tp_sl_support_cache.get(exchange_name) is False:
                                self.logger.info(f"🛡️ {exchange_name} 보험 TP/SL 미지원(캐시) → 시도 생략")
                                raise Exception("tp_sl_unsupported_cached")
                        except Exception:
                            pass
                        # CCXT 계열 보험 TP/SL (거래소별 어댑터가 구현한 경우에만 시도)
                        try:
                            adapter = None
                            try:
                                adapter = self.unified_manager.get_exchange(exchange_name, 'futures') if hasattr(self, 'unified_manager') and self.unified_manager else None
                            except Exception:
                                adapter = None
                            if adapter and hasattr(adapter, 'place_insurance_tp_sl'):
                                # 설정값 로드: enable/trigger source/override
                                tp_sl_cfg = {}
                                try:
                                    tp_sl_cfg = self.settings.get('tp_sl_settings', {}) if isinstance(self.settings, dict) else {}
                                except Exception:
                                    tp_sl_cfg = {}
                                ex_over = {}
                                try:
                                    ex_over = (self.settings.get('exchange_tp_sl_overrides', {}) or {}).get(exchange_name, {}) if isinstance(self.settings, dict) else {}
                                except Exception:
                                    ex_over = {}
                                enabled = True
                                try:
                                    enabled = bool(ex_over.get('enabled', tp_sl_cfg.get('enabled', True)))
                                except Exception:
                                    enabled = True
                                if not enabled:
                                    self.logger.info(f"🛡️ {exchange_name} 보험 TP/SL 비활성화 설정으로 건너뜀")
                                    raise Exception("tp_sl_disabled_by_settings")
                                trigger_src = str(ex_over.get('trigger_price_source', tp_sl_cfg.get('trigger_price_source', 'mark')))
                                eprice = order_result.get('price') or 0.0
                                try:
                                    eprice = float(eprice)
                                except Exception:
                                    cp = self.exchange_manager.get_current_price(symbol, exchange_name)
                                    eprice = float(cp or 0.0)
                                tp_pct = float(optimized_params.get('tp_percent', self.settings.get('default_tp', 0.0018))) if isinstance(optimized_params, dict) else 0.0018
                                sl_pct = float(optimized_params.get('sl_percent', self.settings.get('default_sl', 0.0020))) if isinstance(optimized_params, dict) else 0.0020
                                if eprice and eprice > 0:
                                    if signal.upper() == 'LONG':
                                        tp_price = eprice * (1 + tp_pct)
                                        sl_price = eprice * (1 - sl_pct)
                                        pos_side = 'LONG'
                                    else:
                                        tp_price = eprice * (1 - tp_pct)
                                        sl_price = eprice * (1 + sl_pct)
                                        pos_side = 'SHORT'
                                    try:
                                        if exchange_name == 'okx':
                                            # OKX는 margin mode를 함께 전달
                                            margin_mode = 'cross'
                                            try:
                                                # default_margin_type(e.g., ISOLATED/CROSSED) → okx 문자열 매핑
                                                mt = str(self.settings.get('default_margin_type', 'ISOLATED')).upper() if isinstance(self.settings, dict) else 'ISOLATED'
                                                margin_mode = 'isolated' if mt.startswith('ISOL') else 'cross'
                                            except Exception:
                                                margin_mode = 'cross'
                                            margin_mode = str(ex_over.get('margin_mode', margin_mode))
                                            result = adapter.place_insurance_tp_sl(
                                                symbol=symbol,
                                                position_side=pos_side,
                                                take_profit=tp_price,
                                                stop_loss=sl_price,
                                                quantity=position_size,
                                                trigger_price_type=trigger_src,
                                                margin_mode=margin_mode,
                                            )
                                        else:
                                            result = adapter.place_insurance_tp_sl(
                                                symbol=symbol,
                                                position_side=pos_side,
                                                take_profit=tp_price,
                                                stop_loss=sl_price,
                                                quantity=position_size,
                                                trigger_price_type=trigger_src,
                                            )
                                        if isinstance(result, dict) and result.get('status') == 'success':
                                            optimized_params['_exit_policy'] = record_insurance_submission(
                                                optimized_params.get('_exit_policy'),
                                                submitted_tp_price=tp_price,
                                                submitted_sl_price=sl_price,
                                                status='submitted_to_exchange',
                                                order_ids={
                                                    'tp': result.get('tp_order_id'),
                                                    'sl': result.get('sl_order_id'),
                                                },
                                            )
                                            self.logger.info(f"🛡️ {exchange_name} {symbol} 보험 TP/SL 설정 완료(TP:{tp_price:.6f}, SL:{sl_price:.6f})")
                                            self.logger.info(
                                                f"{exchange_name} {symbol} "
                                                f"{format_exit_policy(optimized_params['_exit_policy'])}"
                                            )
                                            # 성공 시 지원 가능으로 캐시
                                            try:
                                                self._tp_sl_support_cache[exchange_name] = True
                                            except Exception:
                                                pass
                                        else:
                                            optimized_params['_exit_policy'] = record_insurance_submission(
                                                optimized_params.get('_exit_policy'),
                                                status='exchange_submission_failed',
                                            )
                                            self.logger.warning(f"{exchange_name} {symbol} 보험 TP/SL 설정 실패(계속): {result}")
                                            self.logger.warning(
                                                f"{exchange_name} {symbol} "
                                                f"{format_exit_policy(optimized_params['_exit_policy'])}"
                                            )
                                    except Exception as ccxt_e:
                                        optimized_params['_exit_policy'] = record_insurance_submission(
                                            optimized_params.get('_exit_policy'),
                                            status=f'exchange_submission_error:{type(ccxt_e).__name__}',
                                        )
                                        self.logger.warning(f"{exchange_name} {symbol} 보험 TP/SL 설정 오류(계속): {ccxt_e}")
                                        # 명백한 미지원 키워드가 포함된 경우만 미지원 캐시
                                        try:
                                            msg = str(ccxt_e).lower()
                                            if any(k in msg for k in ['not supported', 'unsupported', 'not available', 'notimplemented']):
                                                self._tp_sl_support_cache[exchange_name] = False
                                        except Exception:
                                            pass
                            else:
                                optimized_params['_exit_policy'] = record_insurance_submission(
                                    optimized_params.get('_exit_policy'),
                                    status='adapter_insurance_order_not_supported',
                                )
                                self.logger.info(
                                    f"{exchange_name} {symbol} "
                                    f"{format_exit_policy(optimized_params['_exit_policy'])}"
                                )
                        except Exception:
                            optimized_params['_exit_policy'] = record_insurance_submission(
                                optimized_params.get('_exit_policy'),
                                status='insurance_order_disabled_or_unavailable',
                            )
                            self.logger.info(
                                f"{exchange_name} {symbol} "
                                f"{format_exit_policy(optimized_params['_exit_policy'])}"
                            )
                    elif paper_mode:
                        optimized_params['_exit_policy'] = record_insurance_submission(
                            optimized_params.get('_exit_policy'),
                            status='paper_virtual_exit_no_exchange_submission',
                        )
                        self.logger.info(
                            f"{exchange_name} {symbol} "
                            f"{format_exit_policy(optimized_params['_exit_policy'])}"
                        )
                    elif exchange_name in ('upbit', 'bithumb'):
                        optimized_params['_exit_policy'] = record_insurance_submission(
                            optimized_params.get('_exit_policy'),
                            status='spot_monitor_exit_no_insurance_order',
                        )
                        self.logger.info(
                            f"{exchange_name} {symbol} "
                            f"{format_exit_policy(optimized_params['_exit_policy'])}"
                        )
                except Exception:
                    pass
                # 진입 시점 사이징 스냅샷 저장(성과 매핑용)
                try:
                    snapshot = {
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'exchange': exchange_name,
                        'symbol': symbol,
                        'quote_currency': (
                            'KRW'
                            if str(exchange_name or '').lower() in {'upbit', 'bithumb'}
                            or 'KRW' in str(symbol or '').upper()
                            else 'USDT'
                        ),
                        'signal': signal,
                        'entry_price': order_result.get('price', 0.0),
                        'position_size': position_size,
                        'leverage': optimized_params.get('leverage', None),
                        'sizing_detail': getattr(self, '_last_sizing_detail', None),
                        'confidence': analysis.get('confidence', None),
                        'tp_percent': analysis.get('tp_percent', None),
                        'sl_percent': analysis.get('sl_percent', None),
                        'exit_policy': dict(optimized_params.get('_exit_policy') or {}),
                    }
                    self.position_sizing_snapshots[(exchange_name, symbol)] = snapshot
                except Exception:
                    pass

                # 거래 진입 DB 로그 (Recorder) 기록 시도
                try:
                    if hasattr(self, 'recorder') and self.recorder:
                        pos = (self._position_store(exchange_name) or {}).get(symbol)
                        if pos is not None and not paper:
                            trade_params = {
                                'reason': analysis.get('reason', 'AI signal'),
                                'exchange': exchange_name,
                                'confidence': analysis.get('confidence', None),
                                'order_id': (
                                    order_result.get('order_id')
                                    or order_result.get('orderId')
                                    or order_result.get('id')
                                ),
                            }
                            try:
                                inserted_id = self.recorder.log_trade_entry(pos, trade_params)
                                if inserted_id is None:
                                    self.logger.error(
                                        f"{exchange_name} {symbol} 체결 성공 후 진입 통계 기록 실패"
                                    )
                            except Exception as rec_e:
                                self.logger.warning(f"Recorder 진입 로그 실패(계속): {rec_e}")
                except Exception:
                    pass
                if not paper:
                    emit_kpi_event(
                        event_type='trade_order_executed',
                        category='trade',
                        asset_class='crypto',
                        status='success',
                        source='noahai_client_unified_trader',
                        metric_value=float(executed_quantity or position_size),
                        metadata={
                            'exchange': exchange_name,
                            'symbol': symbol,
                            'quote_currency': (
                                'KRW'
                                if str(exchange_name or '').lower() in {'upbit', 'bithumb'}
                                or 'KRW' in str(symbol or '').upper()
                                else 'USDT'
                            ),
                            'signal': signal,
                            'mode': 'demo' if demo else 'live',
                            'order_id': order_result.get('order_id'),
                            'executed_price': executed_price,
                            'notional_estimate': executed_notional,
                        },
                    )
                return {
                    'status': 'success',
                    'order': order_result,
                    'params': optimized_params,
                    'latency_ms': float(order_result.get('latency_ms', 0.0) or 0.0),
                    'slippage_bps': float(order_result.get('slippage_bps', 0.0) or 0.0),
                }
            else:
                get_opportunity_coordinator().release(opportunity_auth)
                get_opportunity_coordinator().record_result(
                    opportunity_auth,
                    status="failed",
                    detail=str(order_result.get("error") or order_result),
                )
                # 실패 상세 원인 전파(원문 보존)
                reason = order_result.get('error')
                if not reason:
                    # 상태/원시결과로 힌트 구성
                    st = order_result.get('status')
                    raw = order_result.get('raw_result') or order_result
                    try:
                        import json as _json
                        raw_txt = _json.dumps(raw, ensure_ascii=False)[:500]
                    except Exception:
                        raw_txt = str(raw)
                    reason = f"status={st} raw={raw_txt}"
                self.logger.warning(f"주문 실패 상세: {exchange_name} {symbol} → {reason}")
                error_policy = classify_order_error(reason)
                if crypto_command_id and self.recorder:
                    self.recorder.update_crypto_order_command(
                        crypto_command_id,
                        status=("ambiguous" if error_policy.get("reconcile") else "failed"),
                        error_class=str(error_policy.get("category", "unknown")),
                        error_message=str(reason),
                    )
                if error_policy.get("halt_entries"):
                    self._entry_halts[str(exchange_name).lower()] = {
                        "category": error_policy.get("category"),
                        "reason": str(reason),
                        "command_id": crypto_command_id,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                emit_kpi_event(
                    event_type='trade_order_failed',
                    category='trade',
                    asset_class='crypto',
                    status='failed',
                    source='noahai_client_unified_trader',
                    metadata={
                        'exchange': exchange_name,
                        'symbol': symbol,
                        'signal': signal,
                        'reason': str(reason),
                        'mode': 'demo' if demo else ('paper' if paper else 'live'),
                    },
                )
                return {
                    'status': 'error',
                    'error': reason,
                    'raw': order_result,
                    'latency_ms': float(order_result.get('latency_ms', 0.0) or 0.0),
                    'slippage_bps': float(order_result.get('slippage_bps', 0.0) or 0.0),
                }

        except Exception as e:
            if opportunity_auth is not None:
                get_opportunity_coordinator().release(opportunity_auth)
                get_opportunity_coordinator().record_result(
                    opportunity_auth,
                    status="failed",
                    detail=str(e),
                )
            self.logger.error(f"❌ {exchange_name} {symbol} 거래 실행 실패: {e}")
            if crypto_command_id and self.recorder:
                error_policy = classify_order_error(e)
                self.recorder.update_crypto_order_command(
                    crypto_command_id,
                    status=("ambiguous" if error_policy.get("reconcile") else "failed"),
                    error_class=str(error_policy.get("category", "unknown")),
                    error_message=str(e),
                )
            emit_kpi_event(
                event_type='trade_order_failed',
                category='trade',
                asset_class='crypto',
                status='failed',
                source='noahai_client_unified_trader',
                metadata={
                    'exchange': exchange_name,
                    'symbol': symbol,
                    'signal': signal,
                    'reason': str(e),
                    'error_type': 'exception',
                },
            )
            return {'status': 'error', 'error': str(e)}


    def _clamp_leverage(self, exchange_name: str, leverage: Any) -> int:
        """설정 기반 레버리지 상하한 가드레일 적용"""
        try:
            lev = int(max(1, round(float(leverage))))
        except Exception:
            lev = 1
        try:
            # 우선순위: exchange_risk_overrides.{ex}.max_leverage > settings.max_leverage > 기본 20
            overrides = (self.settings.get('exchange_risk_overrides', {}) or {}).get(exchange_name, {}) if isinstance(self.settings, dict) else {}
            max_lev = overrides.get('max_leverage', None)
            if max_lev is None:
                max_lev = self.settings.get('max_leverage', None) if isinstance(self.settings, dict) else None
            if max_lev is None:
                # 보수적 기본 상한
                max_lev = 20
            max_lev = int(max(1, round(float(max_lev))))
            return max(1, min(lev, max_lev))
        except Exception:
            return max(1, min(lev, 20))

    def execute_signal_trade(self, exchange_name: str, symbol: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """거래소별 신호 거래 실행 (public wrapper)"""
        return self._execute_signal_trade(exchange_name, symbol, analysis)

    def _ensure_min_notional(self, exchange_name: str, symbol: str, position_size: float) -> Tuple[float, str]:
        """설정과 거래소 market 규격을 함께 충족하는 승인 전 수량을 계산한다."""
        try:
            # 현재가 조회 (ExchangeManager 경유)
            current_price = None
            if hasattr(self, 'exchange_manager') and self.exchange_manager:
                try:
                    current_price = self.exchange_manager.get_current_price(symbol, exchange_name)
                except Exception:
                    current_price = None
            if not current_price or current_price <= 0:
                return position_size, ''

            # 심볼별 오버라이드 > 전역 최소 거래 금액
            min_notional_overrides = {}
            try:
                min_notional_overrides = (self.settings.get('symbol_min_notional_overrides', {}) or {}) if isinstance(self.settings, dict) else {}
            except Exception:
                min_notional_overrides = {}
            min_trade_amount = 5.0
            try:
                min_trade_amount = float(self.settings.get('min_trade_amount', 5.0)) if isinstance(self.settings, dict) else 5.0
            except Exception:
                min_trade_amount = 5.0

            sym_key = symbol.replace('/', '').replace('-', '')
            min_notional = float(min_notional_overrides.get(sym_key, min_trade_amount))
            min_amount = 0.0
            ccxt_exchange = None
            normalized_symbol = symbol
            try:
                adapter = self.get_exchange_client(exchange_name)
                ccxt_exchange = getattr(adapter, 'exchange', None)
                if ccxt_exchange is not None:
                    normalized_symbol = self._normalize_symbol_for_adapter(adapter, symbol)
                    from trading.exchanges.order_constraints import resolve_ccxt_order_limits
                    resolved_limits = resolve_ccxt_order_limits(
                        ccxt_exchange,
                        normalized_symbol,
                    )
                    min_amount = resolved_limits['min_amount']
                    min_notional = max(
                        min_notional,
                        resolved_limits['min_cost'],
                    )
            except Exception:
                ccxt_exchange = None

            target_notional = min_notional * 1.01 if min_notional > 0 else 0.0
            notional = position_size * float(current_price)
            if notional >= target_notional and position_size >= min_amount:
                return position_size, ''
            # 상향 보정
            required_size = max(
                min_amount,
                target_notional / float(current_price) if target_notional > 0 else 0.0,
            )
            # 상한/하한 적용 재사용
            # 최소 단위는 내부 min_position_size 이상
            try:
                overrides = (self.settings.get('exchange_risk_overrides', {}) or {}).get(exchange_name, {}) if isinstance(self.settings, dict) else {}
                min_size = float(overrides.get('min_position_size', 0.0))
            except Exception:
                min_size = 0.0
            adjusted = max(required_size, min_size)
            if ccxt_exchange is not None:
                try:
                    from trading.exchanges.order_constraints import ccxt_amount_ceiling
                    adjusted = ccxt_amount_ceiling(
                        ccxt_exchange,
                        normalized_symbol,
                        adjusted,
                    )
                except Exception:
                    pass
            return adjusted, (
                f"{notional:.4f} < target {target_notional:.4f}, "
                f"min_qty {min_amount:.8f} → size {position_size:.8f} → {adjusted:.8f}"
            )
        except Exception:
            return position_size, ''

    def _is_order_success(self, order_result: Dict[str, Any]) -> bool:
        """주문 결과의 성공 여부를 다양한 반환 형식에서 안전하게 판별"""
        if not order_result or not isinstance(order_result, dict):
            return False
        status = str(order_result.get('status', '')).upper()
        if status == 'SUCCESS':
            return True
        if status in ('CLOSED', 'FILLED', 'PARTIALLY_FILLED', 'PENDING', 'NEW'):
            return True
        # UnifiedTradingManager 표준 포맷
        if order_result.get('order_id') and order_result.get('symbol'):
            return True
        # 원시 바이낸스 포맷
        if order_result.get('orderId'):
            return True
        # CCXT 원시 주문 포맷. 실패/취소 상태는 id가 있어도 성공으로 보지 않는다.
        if (
            order_result.get('id')
            and order_result.get('symbol')
            and status not in {'FAILED', 'ERROR', 'CANCELED', 'CANCELLED', 'REJECTED', 'EXPIRED'}
        ):
            return True
        # 바이낸스 네이티브 클라이언트 주문 성공 판별 (OrderRequest 기반)
        # 이 함수는 주문 성공 여부만 판별해야 하므로, 실제 주문 실행 코드는 _execute_signal_trade에서만 처리
        # 여기서는 order_result dict의 status, orderId 등만 안전하게 판별
        return False

    def _resolve_execution_values(
        self,
        *,
        order_result: Dict[str, Any],
        fallback_quantity: float,
        exchange_name: str,
        symbol: str,
    ) -> Tuple[float, float, float]:
        """거래소별 시장가 응답에서 실제 체결수량·가격·결제금액을 복원한다.

        Upbit/Bithumb CCXT 시장가 주문은 ``price``가 비어 있어도
        ``filled``/``average``/``cost``가 채워질 수 있다. 이 값을 우선하고,
        체결 응답에 가격만 없을 때에만 주문 시점 공개 시세를 보조값으로 쓴다.
        """
        result = order_result if isinstance(order_result, dict) else {}
        raw = result.get("raw_result") if isinstance(result.get("raw_result"), dict) else {}

        def _first_positive(*values: Any) -> float:
            for value in values:
                try:
                    number = float(value or 0.0)
                except (TypeError, ValueError):
                    continue
                if number > 0.0:
                    return number
            return 0.0

        quantity = _first_positive(
            result.get("filled"),
            result.get("executed_qty"),
            result.get("quantity"),
            result.get("amount"),
            raw.get("filled"),
            raw.get("executed_qty"),
            raw.get("amount"),
            fallback_quantity,
        )
        price = _first_positive(
            result.get("average"),
            result.get("avg_price"),
            result.get("executed_price"),
            result.get("price"),
            raw.get("average"),
            raw.get("avg_price"),
            raw.get("price"),
        )
        notional = _first_positive(
            result.get("cost"),
            result.get("cummulativeQuoteQty"),
            raw.get("cost"),
            raw.get("cummulativeQuoteQty"),
        )
        if price <= 0.0 and notional > 0.0 and quantity > 0.0:
            price = notional / quantity
        if price <= 0.0:
            try:
                price = _first_positive(
                    self.exchange_manager.get_current_price(symbol, exchange_name)
                    if hasattr(self, "exchange_manager")
                    else 0.0
                )
            except Exception:
                price = 0.0
        if notional <= 0.0 and price > 0.0 and quantity > 0.0:
            notional = price * quantity
        return quantity, price, notional

    def _record_position(self, exchange_name: str, symbol: str, signal: str, quantity: float, order_result: Dict[str, Any]):
        """포지션 기록"""
        try:
            entry_price = float(order_result.get('price', 0.0))
            lev = int(self.settings.get('default_leverage', 10)) if isinstance(self.settings, dict) else 10
            # 기본 TP/SL 가격 계산
            try:
                tp_pct = float(self.settings.get('default_tp', 0.0018))
                sl_pct = float(self.settings.get('default_sl', 0.0020))
            except Exception:
                tp_pct, sl_pct = 0.0018, 0.0020
            if signal.upper() == 'LONG':
                tp_price = entry_price * (1 + tp_pct)
                sl_price = entry_price * (1 - sl_pct)
            else:
                tp_price = entry_price * (1 - tp_pct)
                sl_price = entry_price * (1 + sl_pct)

            position = Position(
                symbol=symbol,
                side=PositionSide.LONG if signal == 'LONG' else PositionSide.SHORT,
                entry_price=entry_price,
                current_price=entry_price,
                quantity=quantity,
                leverage=lev,
                unrealized_pnl=0.0,
                unrealized_pnl_percent=0.0,
                entry_time=datetime.now(timezone.utc),
                tp_price=tp_price,
                sl_price=sl_price,
                entry_order_id=str(
                    order_result.get('order_id')
                    or order_result.get('orderId')
                    or order_result.get('id')
                    or ''
                ) or None,
                position_owner=NOAH_POSITION_OWNER,
            )

            self._position_store(exchange_name)[symbol] = position
            self.logger.info(f"📝 {exchange_name} {symbol} 포지션 기록 완료")

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {symbol} 포지션 기록 실패: {e}")

    def _monitor_exchange_positions(self, exchange_name: str):
        """거래소별 포지션 모니터링 (바이낸스와 동일한 로직)"""
        try:
            if self._execution_mode(exchange_name) == ExecutionMode.LIVE:
                self.sync_exchange_execution_ledger(exchange_name)
            active_positions = self._position_store(exchange_name)
            if not active_positions:
                return

            # TP/SL 누락 시 주기적으로 재발주
            try:
                self._verify_and_repair_tp_sl(exchange_name)
            except Exception as exc:
                self.logger.warning(
                    f"TP/SL 누락 검증 실패: {exchange_name}: {exc}"
                )

            self.logger.info(f"📊 {exchange_name} 포지션 모니터링: {len(active_positions)}개")

            for symbol, position in list(active_positions.items()):
                try:
                    # 현재 가격 조회
                    # 현재가는 ExchangeManager 경유(표준화)
                    current_price = None
                    if hasattr(self, 'exchange_manager') and self.exchange_manager:
                        try:
                            current_price = self.exchange_manager.get_current_price(symbol, exchange_name)
                        except Exception:
                            current_price = None
                    if not current_price:
                        continue

                    # 포지션 가격 업데이트
                    position.current_price = current_price

                    # PnL 계산 (바이낸스와 동일한 로직)
                    pnl_data = self._calculate_pnl_unified(position, current_price)

                    advanced_decision = self._advanced_order_plan_decision_unified(
                        position, pnl_data,
                    )
                    if advanced_decision.get('action') == 'partial_close':
                        self._execute_advanced_partial_close_unified(
                            exchange_name, symbol, position, current_price, advanced_decision,
                        )
                        continue
                    if advanced_decision.get('action') == 'close_all':
                        self.logger.info(
                            f"{exchange_name} {symbol} AI 커스텀 고급 청산: "
                            f"{advanced_decision.get('reason')}"
                        )
                        self._close_position_unified(exchange_name, symbol, position, current_price)
                        continue

                    # 청산 조건 확인 (바이낸스와 동일한 로직)
                    if self._should_close_position_unified(exchange_name, position, current_price, pnl_data):
                        self._close_position_unified(exchange_name, symbol, position, current_price)

                except Exception as e:
                    self.logger.error(f"❌ {exchange_name} {symbol} 포지션 모니터링 실패: {e}")

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} 포지션 모니터링 실패: {e}")

    @staticmethod
    def _advanced_order_plan_decision_unified(
        position: Position, pnl_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        rules = dict(getattr(position, 'custom_strategy_rules', {}) or {})
        plan = dict(rules.get('advanced_order_plan') or {})
        if not plan:
            return {'action': 'hold', 'reason': 'advanced_order_plan_not_set'}
        decision = evaluate_order_plan(
            plan,
            getattr(position, 'custom_order_plan_state', {}) or None,
            pnl_percent=float(pnl_data.get('net_pnl_percent', 0.0) or 0.0),
            current_quantity=float(getattr(position, 'quantity', 0.0) or 0.0),
        )
        # 고점·armed 상태는 주문과 무관한 관찰 상태라 즉시 보존한다. 부분청산 완료
        # 인덱스는 체결 확인 뒤 confirm_order_plan_action에서만 추가한다.
        position.custom_order_plan_state = dict(decision.get('next_state') or {})
        return decision

    def _execute_advanced_partial_close_unified(
        self,
        exchange_name: str,
        symbol: str,
        position: Position,
        current_price: float,
        decision: Dict[str, Any],
    ) -> bool:
        quantity = min(
            float(getattr(position, 'quantity', 0.0) or 0.0),
            float(decision.get('quantity', 0.0) or 0.0),
        )
        if quantity <= 0:
            return False
        paper = self._execution_mode(exchange_name) == ExecutionMode.PAPER
        order_result: Dict[str, Any]
        if paper:
            now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
            order_result = {
                'status': 'success', '_execution_confirmed': True,
                'order_id': f"paper-partial-{exchange_name}-{symbol}-{now_ts}",
                'symbol': symbol, 'quantity': quantity, 'price': current_price,
                'simulated': True,
            }
        else:
            client = self.get_exchange_client(exchange_name)
            if client is None:
                return False
            opposite = 'sell' if position.side == PositionSide.LONG else 'buy'
            try:
                if hasattr(client, 'exchange') and getattr(client, 'exchange', None) is not None:
                    normalized = client._normalize_symbol(symbol) if hasattr(client, '_normalize_symbol') else symbol
                    raw = client.exchange.create_order(
                        normalized, 'market', opposite, quantity, None, {'reduceOnly': True},
                    )
                    order_result = dict(raw or {})
                    order_result.setdefault('order_id', order_result.get('id'))
                elif hasattr(client, 'place_futures_order'):
                    order_result = client.place_futures_order(
                        symbol=symbol,
                        side=opposite.upper(),
                        order_type='MARKET',
                        quantity=quantity,
                        reduce_only=True,
                        close_position=None,
                    )
                else:
                    self.logger.warning(
                        f"{exchange_name} {symbol} 부분청산 미지원: reduce-only 주문 계약 없음"
                    )
                    return False
                order_result = self._confirm_ccxt_order_result(client, order_result, symbol=symbol)
                self._record_exchange_execution(
                    exchange_name, symbol, opposite, order_result,
                    source='noahai_custom_partial_exit',
                )
            except Exception as exc:
                self.logger.warning(f"{exchange_name} {symbol} 부분청산 제출 실패: {exc}")
                return False
        confirmed = bool(
            paper or (self._is_order_success(order_result) and order_result.get('_execution_confirmed'))
        )
        if not confirmed:
            self.logger.warning(
                f"{exchange_name} {symbol} 부분청산 체결 미확정, 다음 복구 주기에서 재확인"
            )
            return False
        remaining = max(0.0, float(position.quantity) - quantity)
        position.quantity = remaining
        position.custom_order_plan_state = confirm_order_plan_action(
            decision, remaining_quantity=remaining,
        )
        self.logger.info(
            f"{exchange_name} {symbol} AI 커스텀 부분청산 확인: {quantity:g}, "
            f"잔여 {remaining:g}, 사유={decision.get('reason')}"
        )
        if remaining <= 0:
            self._position_store(exchange_name).pop(symbol, None)
        return True

    def _verify_and_repair_tp_sl(self, exchange_name: str, interval_sec: int = 20) -> None:
        """진입 후 TP/SL 서버-사이드 주문 누락 시 재발주.
        - binance: binance_client.get_open_orders 사용, type으로 TP/SL 판별
        - bybit/okx/bitget: CCXT 어댑터 fetch_open_orders 사용, type/info 휴리스틱 판별
        """
        try:
            if self._execution_mode(exchange_name) == ExecutionMode.PAPER:
                return
            positions = self.active_positions.get(exchange_name, {}) or {}
            if not positions:
                return
            if not hasattr(self, '_last_tp_sl_verify'):
                self._last_tp_sl_verify = {}
            # 정적 분석기용 사전 바인딩 (경로별 변수 사용 안정화)
            bc = None  # type: ignore[assignment]
            adapter = None  # type: ignore[assignment]
            now = time.time()
            for symbol, pos in positions.items():
                key = (exchange_name, symbol)
                last = self._last_tp_sl_verify.get(key, 0)
                if now - last < interval_sec:
                    continue
                self._last_tp_sl_verify[key] = now
                open_orders: list[dict] = []
                # 바이낸스는 trader.py에서 처리 (문서 가이드라인 준수)
                if False and exchange_name == 'binance':
                    # bc = getattr(self.exchange_manager, 'binance_client', None) if hasattr(self, 'exchange_manager') else None
                    # if not bc or not hasattr(bc, 'get_open_orders'):
                    #     continue
                    # try:
                    #     open_orders = bc.get_open_orders(symbol) or []
                    # except Exception:
                    #     open_orders = []
                    # # 유형 판별
                    # types = {str(o.get('type', '')).upper() for o in open_orders if isinstance(o, dict)}
                    continue  # 바이낸스는 스킵
                elif exchange_name in ('bybit', 'okx', 'bitget'):
                    # CCXT 어댑터 경로
                    adapter = None
                    try:
                        adapter = self.unified_manager.get_exchange(exchange_name, 'futures') if hasattr(self, 'unified_manager') and self.unified_manager else None
                    except Exception:
                        adapter = None
                    if not adapter or not hasattr(adapter, 'get_open_orders'):
                        continue
                    try:
                        oo = adapter.get_open_orders(symbol)
                        # dict list로 정규화
                        open_orders = [dict(x) for x in (oo or [])]
                    except Exception:
                        open_orders = []
                    # 정밀 판별: 거래소별 필드 우선 → 휴리스틱 보조
                    def _ccxt_tp_sl_present(ex: str, orders: list[dict]) -> bool:
                        try:
                            ex = ex.lower()
                            for o in orders:
                                t = str(o.get('type', '')).lower()
                                info = o.get('info') or {}
                                s = str(info).lower()
                                if ex == 'bybit':
                                    # stopOrderType, takeProfit/stopLoss, triggerPrice 등
                                    if any(k in info for k in ('takeProfit','stopLoss','triggerPrice','tpSlMode','tpslMode','triggerBy')):
                                        return True
                                    if any(k in t for k in ('stop','conditional','take','profit')):
                                        return True
                                    if 'tp' in s or ('stop' in s and 'loss' in s):
                                        return True
                                elif ex == 'okx':
                                    # tpTriggerPx/slTriggerPx/tpOrdPx/slOrdPx, tdMode, reduceOnly
                                    if any(k in info for k in ('tpTriggerPx','slTriggerPx','tpOrdPx','slOrdPx','tdMode')):
                                        return True
                                    if 'reduceonly' in s:
                                        return True
                                    if any(k in t for k in ('conditional','stop','take','profit')):
                                        return True
                                elif ex == 'bitget':
                                    # takeProfitPrice/stopLossPrice/planType/triggerType/triggerPrice
                                    if any(k in info for k in ('takeProfitPrice','stopLossPrice','planType','triggerType','triggerPrice','presetTakeProfitPrice','presetStopLossPrice')):
                                        return True
                                    if any(k in t for k in ('plan','stop','take','profit')):
                                        return True
                                else:
                                    # 보조 휴리스틱
                                    if any(k in t for k in ('take','profit','stop','conditional')):
                                        return True
                                    if 'tp' in s or ('stop' in s and 'loss' in s):
                                        return True
                            return False
                        except Exception:
                            return False

                    if _ccxt_tp_sl_present(exchange_name, open_orders):
                        continue
                else:
                    # 기타 거래소는 현재 미지원
                    continue
                # 가격 계산
                entry = float(getattr(pos, 'entry_price', 0) or 0)
                if entry <= 0:
                    cp = 0.0
                    try:
                        cp = float(self.exchange_manager.get_current_price(symbol, exchange_name) or 0)
                    except Exception:
                        cp = 0.0
                    if cp <= 0:
                        continue
                    entry = cp
                tp_pct = float(self.settings.get('default_tp', 0.0018)) if isinstance(self.settings, dict) else 0.0018
                sl_pct = float(self.settings.get('default_sl', 0.0020)) if isinstance(self.settings, dict) else 0.0020
                try:
                    snap = self.position_sizing_snapshots.get((exchange_name, symbol))
                    if snap:
                        tp_pct = float(snap.get('tp_percent', tp_pct) or tp_pct)
                        sl_pct = float(snap.get('sl_percent', sl_pct) or sl_pct)
                except Exception:
                    pass
                if getattr(pos, 'side', None) == PositionSide.LONG:
                    tp_price = entry * (1 + tp_pct)
                    sl_price = entry * (1 - sl_pct)
                    pos_side = 'LONG'
                else:
                    tp_price = entry * (1 - tp_pct)
                    sl_price = entry * (1 + sl_pct)
                    pos_side = 'SHORT'
                try:
                    # 바이낸스는 trader.py에서 처리 (문서 가이드라인 준수)
                    if False and exchange_name == 'binance':
                        # if bc and hasattr(bc, 'place_tp_sl_orders'):
                        #     bc.place_tp_sl_orders(symbol=symbol, position_side=pos_side, take_profit=tp_price, stop_loss=sl_price, quantity=None)
                        continue
                    else:
                        if adapter and hasattr(adapter, 'place_insurance_tp_sl'):
                            if exchange_name == 'okx':
                                # 🔥 포지션 수량을 quantity로 전달
                                position_qty = abs(float(getattr(pos, 'quantity', 0) or 0))
                                result = adapter.place_insurance_tp_sl(symbol=symbol, position_side=pos_side, take_profit=tp_price, stop_loss=sl_price, quantity=position_qty, trigger_price_type='mark', margin_mode='cross')
                            else:
                                # 🔥 포지션 수량을 quantity로 전달
                                position_qty = abs(float(getattr(pos, 'quantity', 0) or 0))
                                result = adapter.place_insurance_tp_sl(symbol=symbol, position_side=pos_side, take_profit=tp_price, stop_loss=sl_price, quantity=position_qty, trigger_price_type='mark')
                            if isinstance(result, dict) and result.get('status') != 'success':
                                raise Exception(result.get('error', 'unknown'))
                    self.logger.info(f"🛡️ 재발주: {exchange_name} {symbol} TP/SL(TP:{tp_price:.6f}, SL:{sl_price:.6f})")
                except Exception as e:
                    self.logger.warning(f"TP/SL 재발주 실패: {exchange_name} {symbol}: {e}")
        except Exception as exc:
            self.logger.warning(
                f"TP/SL 검증·복구 전체 실패: {exchange_name}: {exc}"
            )

    def _extract_tp_sl_from_open_orders(self, exchange_name: str, open_orders: List[Dict[str, Any]]) -> Tuple[Optional[float], Optional[float]]:
        """거래소별 오픈오더에서 TP/SL 가격을 추출"""
        tp_price: Optional[float] = None
        sl_price: Optional[float] = None

        def _to_float(value: Any) -> Optional[float]:
            try:
                if value in (None, '', 0, '0'):
                    return None
                return float(value)
            except Exception:
                return None

        for order in open_orders or []:
            if not isinstance(order, dict):
                continue

            info = order.get('info') or {}
            order_type = str(order.get('type', '')).lower()
            info_text = str(info).lower()

            tp_candidate = (
                _to_float(info.get('tpTriggerPx')) or
                _to_float(info.get('takeProfitPrice')) or
                _to_float(info.get('takeProfit')) or
                _to_float(info.get('presetTakeProfitPrice')) or
                _to_float(info.get('triggerPrice') if 'take' in order_type or 'profit' in info_text else None) or
                _to_float(order.get('stopPrice') if 'take' in order_type else None)
            )
            sl_candidate = (
                _to_float(info.get('slTriggerPx')) or
                _to_float(info.get('stopLossPrice')) or
                _to_float(info.get('stopLoss')) or
                _to_float(info.get('presetStopLossPrice')) or
                _to_float(info.get('triggerPrice') if 'stop' in order_type or 'loss' in info_text else None) or
                _to_float(order.get('stopPrice') if 'stop' in order_type else None)
            )

            if tp_candidate and tp_price is None:
                tp_price = tp_candidate
            if sl_candidate and sl_price is None:
                sl_price = sl_candidate

            if tp_price is not None and sl_price is not None:
                break

        return tp_price, sl_price

    def _get_restored_tp_sl_prices(self, exchange_name: str, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        """재시작 복구 시 거래소 오픈오더에서 TP/SL 가격을 복원"""
        try:
            if exchange_name not in ('bybit', 'okx', 'bitget'):
                return None, None

            adapter = None
            try:
                adapter = self.unified_manager.get_exchange(exchange_name, 'futures') if hasattr(self, 'unified_manager') and self.unified_manager else None
            except Exception:
                adapter = None

            if not adapter or not hasattr(adapter, 'get_open_orders'):
                return None, None

            open_orders = adapter.get_open_orders(symbol) or []
            normalized_orders = [dict(order) for order in open_orders if isinstance(order, dict)]
            return self._extract_tp_sl_from_open_orders(exchange_name, normalized_orders)
        except Exception:
            return None, None

    def _calculate_pnl_unified(self, position: Position, current_price: float) -> Dict[str, Any]:
        """PnL 계산 (CCXT 거래소용)"""
        try:
            # 안전성 검사
            if not position.entry_price or position.entry_price <= 0:
                self.logger.warning(f"{position.symbol} 진입가가 유효하지 않음: {position.entry_price}")
                return {'current_pnl_percent': 0.0, 'net_pnl_percent': 0.0, 'unrealized_pnl': 0.0}

            if not current_price or current_price <= 0:
                self.logger.warning(f"{position.symbol} 현재가가 유효하지 않음: {current_price}")
                return {'current_pnl_percent': 0.0, 'net_pnl_percent': 0.0, 'unrealized_pnl': 0.0}

            if not position.quantity or position.quantity <= 0:
                self.logger.warning(f"{position.symbol} 수량이 유효하지 않음: {position.quantity}")
                return {'current_pnl_percent': 0.0, 'net_pnl_percent': 0.0, 'unrealized_pnl': 0.0}

            # 기본 PnL 계산
            if position.side == PositionSide.LONG:
                current_pnl_percent = ((current_price - position.entry_price) / position.entry_price) * 100
            else:  # SHORT
                current_pnl_percent = ((position.entry_price - current_price) / position.entry_price) * 100

            # recorder의 청산 로그 계산식과 동일하게 화폐단위로 추정 후 퍼센트 환산
            side_sign = 1 if position.side == PositionSide.LONG else -1
            gross_pnl_ccy = (current_price - position.entry_price) * position.quantity * side_sign
            notional = position.entry_price * position.quantity

            try:
                fee_rate = float((self.settings or {}).get('estimated_round_trip_fee_rate', 0.0004))
            except Exception:
                fee_rate = 0.0004
            try:
                slippage_rate = float((self.settings or {}).get('estimated_slippage_rate', 0.0002))
            except Exception:
                slippage_rate = 0.0002

            fee_rate = max(0.0, fee_rate)
            slippage_rate = max(0.0, slippage_rate)

            estimated_fees = notional * fee_rate
            estimated_slippage = notional * slippage_rate
            net_pnl_ccy = gross_pnl_ccy - estimated_fees - estimated_slippage
            net_pnl_percent = (net_pnl_ccy / notional) * 100 if notional > 0 else 0.0

            # 미실현 손익은 비용 차감 전 변동 손익(화폐단위)
            position_value = position.quantity * current_price
            entry_value = position.quantity * position.entry_price
            unrealized_pnl = gross_pnl_ccy

            return {
                'current_pnl_percent': current_pnl_percent,
                'net_pnl_percent': net_pnl_percent,
                'unrealized_pnl': unrealized_pnl,
                'position_value': position_value,
                'entry_value': entry_value,
                'gross_pnl_ccy': gross_pnl_ccy,
                'net_pnl_ccy': net_pnl_ccy,
                'estimated_fees': estimated_fees,
                'estimated_slippage': estimated_slippage
            }

        except Exception as e:
            self.logger.error(f"❌ {position.symbol} PnL 계산 실패: {e}")
            return {'current_pnl_percent': 0.0, 'net_pnl_percent': 0.0, 'unrealized_pnl': 0.0}

    def _custom_strategy_exit_triggered_unified(
        self,
        exchange_name: str,
        position: Position,
        current_price: float,
    ) -> bool:
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
            klines = self.exchange_manager.get_klines(
                position.symbol,
                interval="5m",
                limit=220,
                exchange_name=exchange_name,
            )
            context = build_indicator_context(klines or [], signal=position.side.value)
            context.update({
                "current_price": current_price,
                "price": current_price,
                "close": current_price,
                "signal": position.side.value,
            })
            context = enrich_advanced_indicator_context(
                context,
                rules,
                lambda timeframe, limit: self.exchange_manager.get_klines(
                    position.symbol,
                    interval=timeframe,
                    limit=limit,
                    exchange_name=exchange_name,
                ),
            )
            result = DeclarativeStrategyEngine.evaluate_exit(rules, context)
            if result.get("allowed", False):
                self.logger.info(
                    f"{exchange_name} {position.symbol} AI 커스텀 명시 청산 조건 충족: "
                    f"{position.custom_strategy_name or position.custom_strategy_id or '사용자 전략'}"
                )
                return True
        except Exception as exc:
            self.logger.warning(
                f"{exchange_name} {position.symbol} AI 커스텀 청산 조건 평가 실패(기존 TP/SL 유지): {exc}"
            )
        return False

    def _should_close_position_unified(self, exchange_name: str, position: Position, current_price: float, pnl_data: Dict[str, Any]) -> bool:
        """AI 모니터링 중심 포지션 청산 여부 판단 (Unified)"""
        try:
            if self._custom_strategy_exit_triggered_unified(exchange_name, position, current_price):
                return True

            current_pnl_percent = pnl_data.get('current_pnl_percent', 0.0)
            net_pnl_percent = pnl_data.get('net_pnl_percent', 0.0)
            advanced_plan = dict(
                (getattr(position, 'custom_strategy_rules', {}) or {}).get('advanced_order_plan') or {}
            )
            partial_plan_active = bool(advanced_plan.get('partial_take_profits'))

            # 🔥 1. AI 모니터링 중심 청산 판단 (주력)
            ai_exit_decision = self._get_enhanced_ai_exit_decision_unified(exchange_name, position, current_price, pnl_data)
            if ai_exit_decision.get('should_exit', False):
                reason = ai_exit_decision.get('reason', 'AI 분석 기반 청산')
                confidence = ai_exit_decision.get('confidence', 0.0)
                self.logger.info(f"{exchange_name} {position.symbol} AI 모니터링 청산: {reason} (신뢰도: {confidence:.2f})")
                try:
                    self._log_trade_event('exit', f"{exchange_name} {position.symbol} AI 모니터링 청산: {reason} (신뢰도: {confidence:.2f})", exchange=exchange_name)
                except Exception:
                    pass
                return True

            # 🔥 2. 동적 임계값 기반 실시간 모니터링 청산
            dynamic_thresholds = self._calculate_dynamic_thresholds_unified(exchange_name, position.symbol)

            # 수익 청산 (동적 임계값)
            if not partial_plan_active and net_pnl_percent >= dynamic_thresholds['profit_threshold']:
                self.logger.info(f"{exchange_name} {position.symbol} 동적 수익 청산: {net_pnl_percent:.4f}% >= {dynamic_thresholds['profit_threshold']:.4f}%")
                try:
                    self._log_trade_event('exit', f"{exchange_name} {position.symbol} 동적 수익 청산: {net_pnl_percent:.4f}% >= {dynamic_thresholds['profit_threshold']:.4f}%", exchange=exchange_name)
                except Exception:
                    pass
                return True

            # 손실 청산 (동적 임계값)
            if net_pnl_percent <= dynamic_thresholds['loss_threshold']:
                self.logger.info(f"{exchange_name} {position.symbol} 동적 손실 청산: {net_pnl_percent:.4f}% <= {dynamic_thresholds['loss_threshold']:.4f}%")
                try:
                    self._log_trade_event('exit', f"{exchange_name} {position.symbol} 동적 손실 청산: {net_pnl_percent:.4f}% <= {dynamic_thresholds['loss_threshold']:.4f}%", exchange=exchange_name)
                except Exception:
                    pass
                return True

            # 🔥 3. TP/SL 안전장치 (최후의 보호막)
            try:
                if position.tp_price is not None and position.sl_price is not None:
                    entry = float(position.entry_price)
                    if position.side == PositionSide.LONG:
                        tp_percent = ((float(position.tp_price) - entry) / entry) * 100
                        sl_percent = ((entry - float(position.sl_price)) / entry) * 100
                    else:
                        tp_percent = ((entry - float(position.tp_price)) / entry) * 100
                        sl_percent = ((float(position.sl_price) - entry) / entry) * 100
                    if not partial_plan_active and net_pnl_percent >= tp_percent:
                        self.logger.info(f"{exchange_name} {position.symbol} TP 안전장치 발동: {net_pnl_percent:.4f}% >= {tp_percent:.4f}%")
                        try:
                            self._log_trade_event('exit', f"{exchange_name} {position.symbol} TP 안전장치 발동: {net_pnl_percent:.4f}% >= {tp_percent:.4f}%", exchange=exchange_name)
                        except Exception:
                            pass
                        return True
                    if net_pnl_percent <= -sl_percent:
                        self.logger.info(f"{exchange_name} {position.symbol} SL 안전장치 발동: {net_pnl_percent:.4f}% <= -{sl_percent:.4f}%")
                        try:
                            self._log_trade_event('exit', f"{exchange_name} {position.symbol} SL 안전장치 발동: {net_pnl_percent:.4f}% <= -{sl_percent:.4f}%", exchange=exchange_name)
                        except Exception:
                            pass
                        return True
            except Exception as exc:
                self.logger.warning(
                    f"{exchange_name} {position.symbol} TP/SL 안전장치 계산 실패: {exc}"
                )

            return False

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {position.symbol} 청산 판단 실패: {e}")
            return False


    def _close_position_unified(self, exchange_name: str, symbol: str, position: Position, current_price: float) -> bool:
        """포지션 청산 (바이낸스와 동일한 로직)"""
        try:
            if not is_noah_managed_position(position):
                self.logger.warning(
                    f"{exchange_name} {symbol} 수동/외부 포지션 보호: NoahAI 진입 원장이 없어 청산 차단"
                )
                return False
            retry_key = str(
                getattr(position, 'position_id', None)
                or getattr(position, 'entry_order_id', None)
                or f"{exchange_name}:{normalize_position_symbol(symbol)}:{getattr(position, 'entry_time', '')}"
            )
            retry_state = (getattr(self, '_close_retry_state', {}) or {}).get(retry_key, {})
            now_epoch = datetime.now(timezone.utc).timestamp()
            if float(retry_state.get('next_retry_at', 0.0) or 0.0) > now_epoch:
                return False
            close_quantity = float(position.quantity or 0.0)
            # paper_trading 모드에서는 네트워크 호출 없이 즉시 성공 처리
            paper = self._execution_mode(exchange_name) == ExecutionMode.PAPER
            close_command_id = f"close:{retry_key}"
            reconciled_order_result: Optional[Dict[str, Any]] = None

            if not paper and self.recorder:
                claimed = self.recorder.claim_crypto_order_command(
                    command_id=close_command_id,
                    exchange=exchange_name,
                    symbol=symbol,
                    side=('SELL' if position.side == PositionSide.LONG else 'BUY'),
                    intent_type='close',
                    quantity=close_quantity,
                    position_key=retry_key,
                )
                existing_status = str(claimed.get('status') or '')
                # submitting/ambiguous는 거래소 조회 전 재제출하면 이중 청산이
                # 될 수 있으므로 자동 재제출을 금지한다.
                if not claimed.get('claimed') and existing_status in {'submitting', 'ambiguous', 'confirmed'}:
                    exchange_client_for_lookup = self.get_exchange_client(exchange_name)
                    reconciled_order_result = self._lookup_order_by_client_id(
                        exchange_name,
                        exchange_client_for_lookup,
                        symbol,
                        exchange_client_order_id(close_command_id),
                    )
                    if reconciled_order_result:
                        self.logger.info(
                            f"{exchange_name} {symbol} 청산 명령을 client-order ID로 조정했습니다"
                        )
                    else:
                        self._entry_halts[str(exchange_name).lower()] = {
                            'category': 'close_reconciliation_required',
                            'reason': f'청산 명령 상태 확인 필요: {existing_status}',
                            'command_id': close_command_id,
                            'created_at': datetime.now(timezone.utc).isoformat(),
                        }
                        return False
                self.recorder.update_crypto_order_command(
                    close_command_id, status='submitting', increment_attempt=True,
                )

            if paper:
                now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
                order_result = {
                    'status': 'success',
                    'order_id': f"paper-close-{exchange_name}-{symbol}-{now_ts}",
                    'symbol': symbol,
                    'side': 'sell' if position.side == PositionSide.LONG else 'buy',
                    'quantity': position.quantity,
                    'price': current_price,
                    'order_type': 'market',
                    'timestamp': now_ts,
                    'simulated': True
                }
            elif reconciled_order_result is not None:
                order_result = reconciled_order_result
                exchange_client = self.get_exchange_client(exchange_name)
            else:
                exchange_client = self.get_exchange_client(exchange_name)
                if not exchange_client:
                    return False
                if str(exchange_name or '').lower() in {'upbit', 'bithumb'}:
                    from trading.spot_position_policy import (
                        DEFAULT_KRW_MIN_NOTIONAL,
                        balance_quantity,
                        safe_managed_close_quantity,
                        spot_base_asset,
                    )
                    try:
                        actual_balance = exchange_client.get_balance()
                    except Exception:
                        actual_balance = {}
                    if not isinstance(actual_balance, dict) or not actual_balance:
                        self.logger.error(
                            f"{exchange_name} {symbol} 실제 잔고 확인 실패 - 청산 주문 차단"
                        )
                        return False
                    asset = spot_base_asset(symbol)
                    actual_quantity = balance_quantity(actual_balance, asset)
                    close_quantity = safe_managed_close_quantity(
                        managed_quantity=position.quantity,
                        actual_quantity=actual_quantity,
                        baseline_quantity=getattr(position, 'spot_baseline_quantity', 0.0),
                    )
                    if close_quantity <= 0:
                        self.logger.error(
                            f"{exchange_name} {symbol} 앱 관리수량과 실제 잔고 불일치 - 청산 주문 차단"
                        )
                        return False
                    if close_quantity * float(current_price or 0.0) < DEFAULT_KRW_MIN_NOTIONAL:
                        # 거래소 최소 주문금액보다 작은 잔여분은 주문 실패를 반복하지
                        # 않고 dust로 분리한다. 실제 잔고는 그대로 유지된다.
                        self._position_store(exchange_name).pop(symbol, None)
                        self.logger.warning(
                            f"{exchange_name} {symbol} 잔여 관리수량 {close_quantity:g} "
                            f"({close_quantity * float(current_price or 0.0):,.0f} KRW)을 dust로 분리"
                        )
                        return False
                # 반대 방향 주문 실행 (거래소별 안전 분기)
                opposite_side = 'SELL' if position.side == PositionSide.LONG else 'BUY'
                try:
                    if hasattr(exchange_client, 'exchange'):
                        # CCXT 어댑터 경로
                        close_kwargs: Dict[str, Any] = {
                            'symbol': symbol,
                            'side': opposite_side.lower(),
                            'order_type': 'market',
                            'quantity': close_quantity,
                        }
                        if exchange_name != 'bithumb':
                            close_kwargs['client_order_id'] = exchange_client_order_id(close_command_id)
                        if exchange_name in {'bybit', 'okx', 'bitget'}:
                            close_kwargs['reduce_only'] = True
                        order_result = exchange_client.place_order(
                            **close_kwargs,
                        )
                    else:
                        # 바이낸스 네이티브 경로: reduceOnly로 안전 청산
                        try:
                            try:
                                from api.binance_client import BinanceClient as _BinanceClient
                            except Exception:
                                _BinanceClient = None  # type: ignore[assignment]
                            if (_BinanceClient is not None) and isinstance(exchange_client, _BinanceClient) and hasattr(exchange_client, 'place_futures_order'):
                                order_result = exchange_client.place_futures_order(
                                    symbol=symbol,
                                    side=opposite_side,
                                    order_type='MARKET',
                                    quantity=close_quantity,
                                    reduce_only=True,
                                    close_position=None,
                                    client_order_id=exchange_client_order_id(close_command_id),
                                )
                                # 성공 표준화
                                st = str(order_result.get('status', '')).upper()
                                if st in ('NEW','PENDING','PARTIALLY_FILLED') and order_result.get('executed_qty'):
                                    order_result['status'] = 'success'
                                elif st == 'FILLED':
                                    order_result['status'] = 'success'
                            else:
                                order_result = {'status': 'error', 'error': 'Unsupported exchange client for futures close'}
                        except Exception as be:
                            order_result = {'status': 'error', 'error': str(be)}
                except Exception as e:
                    order_result = {'status': 'error', 'error': str(e)}

            if not paper and isinstance(order_result, dict):
                order_result = self._confirm_ccxt_order_result(
                    exchange_client,
                    order_result,
                    symbol=symbol,
                )
                self._record_exchange_execution(
                    exchange_name,
                    symbol,
                    'sell' if position.side == PositionSide.LONG else 'buy',
                    order_result,
                    source='noahai_exit_order',
                )

            execution_confirmed = bool(
                paper
                or (isinstance(order_result, dict) and order_result.get('_execution_confirmed'))
            )
            if self._is_order_success(order_result) and execution_confirmed:
                if not paper and self.recorder:
                    self.recorder.update_crypto_order_command(
                        close_command_id,
                        status='confirmed',
                        exchange_order_id=str(
                            order_result.get('order_id') or order_result.get('id') or ''
                        ),
                    )
                # 체결·통계·KPI는 실제로 청산 요청한 관리수량을 기준으로 한다.
                position.quantity = close_quantity
                # PnL 계산
                pnl_data = self._calculate_pnl_unified(position, current_price)
                pnl_percent = pnl_data.get('net_pnl_percent', 0.0)
                closed_at = utc_now()
                # 거래 청산 DB 로그 (Recorder) 기록 시도
                try:
                    if not paper and hasattr(self, 'recorder') and self.recorder:
                        # 트리거 사유는 상세 판별이 어려워 우선 일반 사유로 기록
                        reason = 'auto_exit'
                        try:
                            # 간단한 힌트 추가: 수익/손실 여부
                            reason = 'tp_or_profit' if pnl_percent > 0 else 'sl_or_loss'
                        except Exception:
                            pass
                        try:
                            # CCXT 경로일 경우 실제 체결 내역으로 가중 평균 가격/수수료/수량 계산 시도
                            actual = None
                            try:
                                exch_client = self.get_exchange_client(exchange_name)
                                if exch_client is not None and hasattr(exch_client, 'get_trade_history') and hasattr(exch_client, 'exchange'):
                                    # 최근 체결 n개 조회 후 entry_time 이후의 반대 방향 체결만 누적
                                    sym = symbol
                                    try:
                                        if hasattr(exch_client, '_normalize_symbol'):
                                            sym = exch_client._normalize_symbol(symbol)  # type: ignore
                                    except Exception:
                                        pass
                                    trades = exch_client.get_trade_history(symbol=sym, limit=100) or []
                                    total_qty = 0.0
                                    total_cost = 0.0
                                    total_fees = 0.0
                                    from datetime import datetime as _dt
                                    et = position.entry_time
                                    # entry_time이 timezone-aware일 수 있어 naive로 변환 비교
                                    try:
                                        if hasattr(et, 'tzinfo') and et.tzinfo is not None:
                                            et = et.replace(tzinfo=None)
                                    except Exception:
                                        pass
                                    for t in trades:
                                        try:
                                            ts_ms = float(t.get('timestamp') or t.get('time') or 0)
                                            if ts_ms > 1e12:
                                                ts = _dt.fromtimestamp(ts_ms/1000.0)
                                            else:
                                                ts = _dt.fromtimestamp(ts_ms)
                                            # entry 이후 체결만 고려
                                            if ts <= et:
                                                continue
                                            # 반대 방향 체결 판단(buy/sell 문자열 사용)
                                            side = str(t.get('side','')).lower()
                                            need_side = 'sell' if position.side == PositionSide.LONG else 'buy'
                                            if side and side != need_side:
                                                continue
                                            price = float(t.get('price') or t.get('avgPrice') or 0.0)
                                            amount = float(t.get('amount') or t.get('qty') or t.get('quantity') or 0.0)
                                            fee = 0.0
                                            try:
                                                fee_obj = t.get('fee')
                                                if isinstance(fee_obj, dict):
                                                    fee = float(fee_obj.get('cost') or 0.0)
                                                else:
                                                    fee = float(t.get('feeCost') or 0.0)
                                            except Exception:
                                                fee = 0.0
                                            if amount <= 0 or price <= 0:
                                                continue
                                            total_qty += amount
                                            total_cost += price * amount
                                            total_fees += fee
                                        except Exception:
                                            continue
                                    if total_qty > 0:
                                        avg_price = total_cost / total_qty
                                        actual = {
                                            'exit_price': avg_price,
                                            'fees': total_fees,
                                            'slippage': 0.0,
                                            'quantity': total_qty
                                        }
                            except Exception:
                                actual = None
                            exit_saved = self.recorder.log_trade_exit(
                                position,
                                reason,
                                float(current_price),
                                actual_trade_info=actual,
                                exchange=exchange_name,
                                exit_order_id=(
                                    order_result.get('order_id')
                                    or order_result.get('orderId')
                                    or order_result.get('id')
                                ),
                            )
                            if not exit_saved:
                                self.logger.error(
                                    f"{exchange_name} {symbol} 체결 성공 후 청산 통계 기록 실패"
                                )
                        except Exception as rec_e:
                            self.logger.warning(f"Recorder 청산 로그 실패(계속): {rec_e}")
                except Exception:
                    pass

                # 실행 모드별 저장소에서만 제거한다.
                self._position_store(exchange_name).pop(symbol, None)

                # 거래 통계 업데이트
                self._update_trade_stats_unified(exchange_name, pnl_percent)

                if not paper:
                    emit_kpi_event(
                        event_type='trade_order_executed',
                        category='trade',
                        asset_class='crypto',
                        status='success',
                        source='noahai_client_unified_trader_close',
                        metric_value=float(position.quantity),
                        metadata={
                            'exchange': exchange_name,
                            'symbol': symbol,
                            'quote_currency': (
                                'KRW'
                                if str(exchange_name or '').lower() in {'upbit', 'bithumb'}
                                or 'KRW' in str(symbol or '').upper()
                                else 'USDT'
                            ),
                            'side': 'CLOSE',
                            'close': True,
                            'reason': 'auto_close',
                            'executed_price': float(current_price or 0.0),
                            'notional_estimate': float(position.quantity) * float(current_price or 0.0),
                        },
                    )
                if getattr(position, 'entry_time_source', 'execution') == 'execution':
                    exit_order_id = None
                    if isinstance(order_result, dict):
                        exit_order_id = (
                            order_result.get('order_id')
                            or order_result.get('orderId')
                            or order_result.get('id')
                        )
                    emit_position_closed(
                        asset_class='crypto',
                        venue=exchange_name,
                        symbol=symbol,
                        side=position.side.value,
                        opened_at=position.entry_time,
                        closed_at=closed_at,
                        entry_price=position.entry_price,
                        exit_price=float(current_price or 0.0),
                        closed_quantity=position.quantity,
                        close_reason='auto_close',
                        position_id=position.position_id,
                        exit_order_id=exit_order_id,
                        execution_mode=getattr(position, 'execution_mode', 'live'),
                        source='noahai_client_unified_position',
                        gross_pnl=float(pnl_data.get('gross_pnl', pnl_data.get('pnl', 0.0)) or 0.0),
                        net_pnl=float(pnl_data.get('net_pnl', 0.0) or 0.0),
                        fees=float(pnl_data.get('total_fees', pnl_data.get('fees', 0.0)) or 0.0),
                        extra={'leverage': int(position.leverage or 1)},
                    )

                # RiskManager 이력 업데이트 (거래소 필터 정합성 보장)
                if not paper and hasattr(self, 'risk_manager') and self.risk_manager:
                    try:
                        entry_time = position.entry_time if hasattr(position, 'entry_time') else datetime.now(timezone.utc)
                        exit_time = datetime.now(timezone.utc)
                        holding_time_ms = int((exit_time - entry_time).total_seconds() * 1000) if isinstance(entry_time, datetime) else 0
                        trade_result = 'PROFIT' if pnl_percent > 0 else 'LOSS'
                        self.risk_manager.update_coin_trade_history(
                            symbol=symbol,
                            trade_result=trade_result,
                            profit_rate=pnl_percent,
                            entry_price=position.entry_price,
                            exit_price=float(current_price),
                            position_size=float(position.quantity) * float(position.entry_price),
                            holding_time=holding_time_ms,
                            exchange=exchange_name,
                        )
                    except Exception as rm_err:
                        self.logger.warning(f"{exchange_name} {symbol} RiskManager 이력 업데이트 실패(계속): {rm_err}")

                # AI 분석 (익절/손절)
                if not paper:
                    if pnl_percent > 0:
                        self._perform_profit_analysis_unified(exchange_name, symbol, position, pnl_data)
                    else:
                        self._perform_loss_analysis_unified(exchange_name, symbol, position, pnl_data)

                # 사이징 스냅샷과 결과 매핑 로그
                try:
                    snap = self.position_sizing_snapshots.pop((exchange_name, symbol), None)
                    if snap:
                        self.logger.info(
                            "📈 SizingOutcome Mapping → "
                            f"{exchange_name} {symbol} signal={snap.get('signal')} size={snap.get('position_size')} "
                            f"lev={snap.get('leverage')} entry={snap.get('entry_price')} pnl={pnl_percent:.4f}% | "
                            f"detail={snap.get('sizing_detail')}"
                        )
                        # 선택적으로 CSV에 영속화
                        try:
                            persist = False
                            if isinstance(self.settings, dict):
                                persist = bool(self.settings.get('position_sizing_persist', False))
                            if persist:
                                out_dir = None
                                try:
                                    from path_utils import get_app_data_dir
                                    out_dir = os.path.join(get_app_data_dir(), 'analytics')
                                except Exception:
                                    out_dir = os.path.join(os.path.expanduser('~'), 'Documents', 'NoahAI', 'analytics')
                                os.makedirs(out_dir, exist_ok=True)
                                out_path = os.path.join(out_dir, 'sizing_outcomes.csv')
                                header = [
                                    'timestamp','exchange','symbol','signal','entry_price','exit_price','pnl_percent',
                                    'position_size','leverage','confidence','tp_percent','sl_percent',
                                    'base_size','confidence_factor','market_factor','exchange_factor','position_size_factor','risk_factor','pre_clamp','min_size','max_size','final_size'
                                ]
                                row = [
                                    snap.get('timestamp'), exchange_name, symbol, snap.get('signal'),
                                    snap.get('entry_price'), current_price, f"{pnl_percent:.6f}",
                                    snap.get('position_size'), snap.get('leverage'), snap.get('confidence'),
                                    snap.get('tp_percent'), snap.get('sl_percent')
                                ]
                                detail = snap.get('sizing_detail') or {}
                                row.extend([
                                    detail.get('base_size'), detail.get('confidence_factor'), detail.get('market_factor'),
                                    detail.get('exchange_factor'), detail.get('position_size_factor'), detail.get('risk_factor'),
                                    detail.get('pre_clamp'), detail.get('min_size'), detail.get('max_size'), detail.get('final_size')
                                ])
                                write_header = not os.path.exists(out_path)
                                with open(out_path, 'a', newline='', encoding='utf-8') as f:
                                    w = csv.writer(f)
                                    if write_header:
                                        w.writerow(header)
                                    w.writerow(row)
                                self.logger.info(f"📝 Sizing outcome saved → {out_path}")
                        except Exception as e:
                            self.logger.warning(f"Sizing outcome persistence failed: {e}")
                except Exception:
                    pass

                # 최근 성과 추적 업데이트
                try:
                    outcome_ok = pnl_percent > 0
                    if not hasattr(self, '_recent_outcomes'):
                        self._recent_outcomes = {}
                    dq = self._recent_outcomes.get(exchange_name)
                    if dq is None:
                        from collections import deque as _dq
                        winwin = int(self.settings.get('risk_winrate_window', 10)) if isinstance(self.settings, dict) else 10
                        dq = _dq(maxlen=max(1, winwin))
                        self._recent_outcomes[exchange_name] = dq
                    dq.append(outcome_ok)
                except Exception:
                    pass

                # 잔여 TP/SL 등 미체결 주문 정리
                try:
                    # 바이낸스는 trader.py에서 처리 (문서 가이드라인 준수)
                    if paper:
                        pass
                    elif exchange_name == 'binance':
                        pass  # 바이낸스는 스킵
                    elif exchange_name in ('bybit','okx','bitget','upbit','bithumb'):
                        # CCXT 거래소: 어댑터의 get_open_orders/cancel_order 사용
                        adapter = None
                        try:
                            trading_type = 'futures' if exchange_name in ('bybit','okx','bitget') else 'spot'
                            adapter = self.unified_manager.get_exchange(exchange_name, trading_type) if hasattr(self, 'unified_manager') and self.unified_manager else None
                        except Exception:
                            adapter = None

                        if adapter and hasattr(adapter, 'get_open_orders') and hasattr(adapter, 'cancel_order'):
                            try:
                                # 어댑터의 메서드 사용 (중복 구현 제거)
                                open_orders = adapter.get_open_orders(symbol) or []
                                for order in open_orders:
                                    order_id = str(order.get('id') or order.get('orderId') or '')
                                    if order_id:
                                        try:
                                            adapter.cancel_order(order_id, symbol)
                                        except Exception:
                                            pass
                                self.logger.info(f"🧹 {exchange_name} {symbol} 잔여 오픈오더 정리 완료(어댑터)")
                            except Exception as e:
                                self.logger.warning(f"{exchange_name} {symbol} 잔여 오더 조회/정리 실패(계속): {e}")
                except Exception as _ce:
                    self.logger.warning(f"{exchange_name} {symbol} 잔여 오더 정리 실패(계속): {_ce}")

                self.logger.info(f"✅ {exchange_name} {symbol} 포지션 청산 완료 (PnL: {pnl_percent:.4f}%)")
                getattr(self, '_close_retry_state', {}).pop(retry_key, None)
                getattr(self, '_close_failure_fingerprints', {}).pop(retry_key, None)
                getattr(self, '_entry_halts', {}).pop(str(exchange_name).lower(), None)
                return True
            else:
                reason = str(order_result.get('error') or order_result.get('message') or '거래소가 오류 상세를 반환하지 않음')
                attempts = int(retry_state.get('attempts', 0) or 0) + 1
                error_policy = classify_order_error(reason)
                # 명백한 rate limit처럼 주문 미접수로 분류 가능한 경우만 제한적으로
                # 재시도한다. 전송 모호/포지션 불일치는 조회가 끝나기 전 재제출 금지.
                can_retry = bool(error_policy.get('retry')) and not bool(error_policy.get('reconcile')) and attempts < 3
                retry_delay = int(error_policy.get('delay', 0) or 0) if can_retry else 0
                if not isinstance(getattr(self, '_close_retry_state', None), dict):
                    self._close_retry_state = {}
                self._close_retry_state[retry_key] = {
                    'attempts': attempts,
                    'reason': reason,
                    'category': error_policy.get('category'),
                    'reconciliation_required': bool(error_policy.get('reconcile')),
                    'next_retry_at': (now_epoch + retry_delay) if can_retry else float('inf'),
                }
                if not paper and self.recorder:
                    self.recorder.update_crypto_order_command(
                        close_command_id,
                        status=('ambiguous' if error_policy.get('reconcile') else 'failed'),
                        error_class=str(error_policy.get('category', 'unknown')),
                        error_message=reason,
                    )
                self._entry_halts[str(exchange_name).lower()] = {
                    'category': error_policy.get('category'),
                    'reason': reason,
                    'command_id': close_command_id,
                    'created_at': datetime.now(timezone.utc).isoformat(),
                }
                fingerprint = f"{retry_key}:{reason}"
                if not isinstance(getattr(self, '_close_failure_fingerprints', None), dict):
                    self._close_failure_fingerprints = {}
                if self._close_failure_fingerprints.get(retry_key) != fingerprint:
                    emit_kpi_event(
                        event_type='trade_order_failed',
                        category='trade',
                        asset_class='crypto',
                        status='failed',
                        source='noahai_client_unified_trader_close',
                        metadata={
                            'exchange': exchange_name,
                            'symbol': symbol,
                            'side': 'CLOSE',
                            'close': True,
                            'reason': reason,
                            'position_owner': NOAH_POSITION_OWNER,
                            'position_key': retry_key,
                            'retry_after_seconds': retry_delay,
                            'error_class': error_policy.get('category'),
                            'reconciliation_required': bool(error_policy.get('reconcile')),
                        },
                    )
                    self._close_failure_fingerprints[retry_key] = fingerprint
                self.logger.error(
                    f"❌ {exchange_name} {symbol} 포지션 청산 실패: {reason} "
                    + (
                        f"(동일 실패 KPI 중복 억제, {retry_delay}초 후 제한 재시도)"
                        if can_retry
                        else "(신규 진입 중단, 거래소 상태 조정 후 재개 필요)"
                    )
                )
                return False

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {symbol} 포지션 청산 실패: {e}")
            return False

    def _update_trade_stats_unified(self, exchange_name: str, pnl_percent: float):
        """거래 통계 업데이트 (거래소별)"""
        try:
            stats = self._trade_stats_store(exchange_name)
            stats['total_trades'] += 1
            stats['total_pnl'] += pnl_percent

            if pnl_percent > 0:
                stats['profitable_trades'] += 1
            else:
                stats['losing_trades'] = stats.get('losing_trades', 0) + 1

            stats['win_rate'] = (stats['profitable_trades'] / stats['total_trades']) * 100

            # DB에도 최신 통계 저장 (dashboard와 일관성 유지)
            if self._execution_mode(exchange_name) == ExecutionMode.LIVE and hasattr(self, 'recorder') and self.recorder:
                stats_for_db = stats.copy()
                stats_for_db['winning_trades'] = stats_for_db.get('profitable_trades', 0)
                self.recorder.save_exchange_trade_stats(exchange_name, stats_for_db)

            self.logger.info(f"📊 {exchange_name} 거래 통계 업데이트: 총 {stats['total_trades']}회, 승률 {stats['win_rate']:.1f}%, 총 PnL {stats['total_pnl']:.2f}%")

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} 거래 통계 업데이트 실패: {e}")

    def _calc_pnl_percent(self, position: Position, exit_price: float) -> float:
        """간단한 PnL 퍼센트 계산 유틸(진입가 대비)"""
        try:
            if position.entry_price <= 0:
                return 0.0
            if position.side == PositionSide.LONG:
                raw = ((exit_price - position.entry_price) / position.entry_price) * 100
            else:
                raw = ((position.entry_price - exit_price) / position.entry_price) * 100
            # 수수료 보수적 차감
            fee_rt = 0.04  # 왕복 0.04% 가정
            return raw - fee_rt
        except Exception:
            return 0.0

    def _perform_profit_analysis_unified(self, exchange_name: str, symbol: str, position: Position, pnl_data: Dict[str, Any]):
        """익절 분석 (거래소별)"""
        try:
            if (
                not self.ai_manager
                or not getattr(
                    self.ai_manager,
                    'enabled_for_role',
                    lambda _role: self.ai_manager.enabled(),
                )('profit_analysis')
            ):
                return

            # 익절 분석 요청 데이터 구성
            profit_analysis_request = {
                'symbol': symbol,
                'exchange': exchange_name,
                'side': position.side.value,
                'entry_price': position.entry_price,
                'exit_price': pnl_data.get('position_value', 0) / position.quantity,
                'quantity': position.quantity,
                'pnl_percent': pnl_data.get('net_pnl_percent', 0.0),
                'holding_time_minutes': (datetime.now(timezone.utc) - position.entry_time).total_seconds() / 60,
                'leverage': getattr(position, 'leverage', 1),
                'reason': '익절'
            }

            # AI 익절 분석 요청
            ai_result = self.ai_manager.analyze_profit_trade(symbol, profit_analysis_request)

            if ai_result:
                self._save_ai_trade_analysis_unified(symbol, ai_result, 'PROFIT')
                self.logger.info(f"🎯 {exchange_name} {symbol} AI 익절 분석: {ai_result.get('success_cause', '익절 분석 완료')}")

                # 기존 시스템 스타일 로그
                specific_adjustments = ai_result.get('specific_adjustments', {})
                if specific_adjustments.get('profit_target_adjustment') == 'INCREASE':
                    self.logger.info(f"🎯 {exchange_name} {symbol} AI 권장: 수익 목표 증가")

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {symbol} 익절 분석 실패: {e}")

    def _perform_loss_analysis_unified(self, exchange_name: str, symbol: str, position: Position, pnl_data: Dict[str, Any]):
        """손절 분석 (거래소별)"""
        try:
            if (
                not self.ai_manager
                or not getattr(
                    self.ai_manager,
                    'enabled_for_role',
                    lambda _role: self.ai_manager.enabled(),
                )('loss_analysis')
            ):
                return

            # 손절 분석 요청 데이터 구성
            loss_analysis_request = {
                'symbol': symbol,
                'exchange': exchange_name,
                'side': position.side.value,
                'entry_price': position.entry_price,
                'exit_price': pnl_data.get('position_value', 0) / position.quantity,
                'quantity': position.quantity,
                'pnl_percent': pnl_data.get('net_pnl_percent', 0.0),
                'holding_time_minutes': (datetime.now(timezone.utc) - position.entry_time).total_seconds() / 60,
                'leverage': getattr(position, 'leverage', 1),
                'reason': '손절'
            }

            # AI 손절 분석 요청
            ai_result = self.ai_manager.analyze_loss_trade(symbol, loss_analysis_request)

            if ai_result:
                self._save_ai_trade_analysis_unified(symbol, ai_result, 'LOSS')
                self.logger.info(f"🛑 {exchange_name} {symbol} AI 손절 분석: {ai_result.get('loss_cause', '손절 분석 완료')}")

                # 기존 시스템 스타일 로그
                recommended_action = ai_result.get('recommended_action', '')
                if recommended_action == 'ADJUST_TP_SL':
                    specific_adjustments = ai_result.get('specific_adjustments', {})
                    if specific_adjustments.get('profit_target_adjustment') == 'DECREASE':
                        self.logger.info(f"🛑 {exchange_name} {symbol} AI 권장: 수익 목표 감소")

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {symbol} 손절 분석 실패: {e}")

    def _save_ai_trade_analysis_unified(self, symbol: str, analysis: Dict[str, Any], analysis_type: str) -> None:
        """다중거래소 청산 AI 분석 결과를 Recorder에 저장"""
        try:
            if hasattr(self, 'recorder') and self.recorder:
                self.recorder.save_ai_trade_analysis(None, symbol, analysis, analysis_type)
        except Exception as e:
            self.logger.warning(f"{symbol} AI 거래 분석 저장 실패: {e}")

    def _analyze_pattern_similarity_unified(self, exchange_name: str, symbol: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """패턴 유사성 분석 (바이낸스와 동일한 로직)"""
        try:
            if (
                not self.ai_manager
                or not getattr(
                    self.ai_manager,
                    'enabled_for_role',
                    lambda _role: self.ai_manager.enabled(),
                )('pattern_similarity')
            ):
                return {'action': 'PROCEED', 'reason': 'AI 비활성화'}

            # 최근 손실 패턴 조회
            recent_patterns = self._get_recent_loss_patterns_unified(exchange_name, symbol, limit=5)

            if not recent_patterns:
                return {'action': 'PROCEED', 'reason': '패턴 데이터 없음'}

            # 현재 신호 데이터 구성
            current_signal_data = {
                'signal_type': analysis.get('signal', 'UNKNOWN'),
                'confidence': analysis.get('confidence', 0.0),
                'reason': analysis.get('reason', ''),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

            # AI 패턴 유사성 분석
            decision = self.ai_manager.analyze_pattern_similarity(symbol, current_signal_data, recent_patterns)

            if decision:
                action = (decision.get('action') or 'PROCEED').upper()
                reason = decision.get('reason', '')

                self.logger.info(f"🔍 {exchange_name} {symbol} 패턴 분석: {action} - {reason}")

                return {
                    'action': action,
                    'reason': reason,
                    'decision': decision
                }
            else:
                return {'action': 'PROCEED', 'reason': 'AI 분석 실패'}

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {symbol} 패턴 유사성 분석 실패: {e}")
            return {'action': 'PROCEED', 'reason': f'분석 오류: {str(e)}'}

    def _get_recent_loss_patterns_unified(self, exchange_name: str, symbol: str, limit: int = 5) -> List[Dict[str, Any]]:
        """최근 손실 패턴 조회 (거래소별)"""
        try:
            # 기본 패턴 데이터 (실제 구현에서는 recorder에서 조회)
            # 여기서는 기본값 반환
            return [
                {
                    'symbol': symbol,
                    'exchange': exchange_name,
                    'side': 'LONG',
                    'entry_price': 50000.0,
                    'exit_price': 49500.0,
                    'pnl_percent': -1.0,
                    'holding_time_minutes': 15.0,
                    'timestamp': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                    'reason': '손절'
                },
                {
                    'symbol': symbol,
                    'exchange': exchange_name,
                    'side': 'SHORT',
                    'entry_price': 51000.0,
                    'exit_price': 51500.0,
                    'pnl_percent': -0.98,
                    'holding_time_minutes': 8.0,
                    'timestamp': (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                    'reason': '손절'
                }
            ]

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {symbol} 패턴 조회 실패: {e}")
            return []

    def _apply_pattern_adjustments(self, analysis: Dict[str, Any], pattern_decision: Dict[str, Any]) -> Dict[str, Any]:
        """패턴 분석 결과에 따른 조정 적용"""
        try:
            # 분석 결과 복사
            adjusted_analysis = analysis.copy()

            # 보수적 조정 적용
            if pattern_decision.get('action') == 'ADJUST':
                # 신뢰도 20% 감소
                if 'confidence' in adjusted_analysis:
                    adjusted_analysis['confidence'] *= 0.8

                # TP/SL 조정 (더 보수적으로)
                if 'tp_percent' in adjusted_analysis:
                    adjusted_analysis['tp_percent'] *= 0.9  # TP 10% 감소
                if 'sl_percent' in adjusted_analysis:
                    adjusted_analysis['sl_percent'] *= 0.8  # SL 20% 감소

                # 레버리지 조정
                if 'leverage' in adjusted_analysis:
                    adjusted_analysis['leverage'] = max(1, int(adjusted_analysis['leverage'] * 0.8))

                self.logger.info(f"🔧 패턴 분석 조정 적용: 신뢰도 {adjusted_analysis.get('confidence', 0):.2f}, TP {adjusted_analysis.get('tp_percent', 0):.3f}, SL {adjusted_analysis.get('sl_percent', 0):.3f}")

            return adjusted_analysis

        except Exception as e:
            self.logger.error(f"❌ 패턴 조정 적용 실패: {e}")
            return analysis

    def _update_trade_stats(self, exchange_name: str, position: Position, exit_price: float):
        """거래 통계 업데이트 및 DB 저장"""
        try:
            # PnL 계산 (간단한 퍼센트 기반)
            pnl_percent = self._calc_pnl_percent(position, exit_price)

            stats = self._trade_stats_store(exchange_name)
            stats['total_trades'] += 1
            stats['total_pnl'] += pnl_percent

            if pnl_percent > 0:
                stats['profitable_trades'] += 1
            else:
                stats['losing_trades'] += 1

            # DB에 통계 저장
            if self._execution_mode(exchange_name) == ExecutionMode.LIVE and hasattr(self, 'recorder') and self.recorder:
                # UnifiedTrader는 profitable_trades 사용, Recorder는 winning_trades 사용
                stats_for_db = stats.copy()
                stats_for_db['winning_trades'] = stats_for_db.get('profitable_trades', 0)
                self.recorder.save_exchange_trade_stats(exchange_name, stats_for_db)
                self.logger.info(f"✅ {exchange_name} 거래 통계 DB 저장 완료")

            self.logger.info(f"📊 {exchange_name} 거래 통계 업데이트: PnL {pnl_percent:.2f}%")

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} 거래 통계 업데이트 실패: {e}")

    def _load_trade_stats_from_db(self, exchange_name: str):
        """DB에서 거래 통계 로드"""
        try:
            if hasattr(self, 'recorder') and self.recorder:
                db_stats = self.recorder.load_exchange_trade_stats(exchange_name)
                if db_stats:
                    # DB의 winning_trades를 profitable_trades로 변환
                    if 'winning_trades' in db_stats:
                        db_stats['profitable_trades'] = db_stats['winning_trades']
                        del db_stats['winning_trades']

                    self.trade_stats[exchange_name].update(db_stats)
                    self.logger.info(f"✅ {exchange_name} 거래 통계 DB 로드 완료: {db_stats.get('total_trades', 0)}건")
                else:
                    self.logger.info(f"📊 {exchange_name} 거래 통계 DB에서 로드할 데이터 없음")
        except Exception as e:
            self.logger.error(f"❌ {exchange_name} 거래 통계 DB 로드 실패: {e}")

    def _restore_positions_from_exchange(self, exchange_name: str):
        """Persisted NoahAI entries만 실제 계좌와 대조해 복구한다.

        거래소의 계정 전체 포지션/잔고는 수동 거래를 포함하므로 소유권의
        증거가 아니다. 일치하지 않는 포지션은 외부 포지션으로 표시해 신규
        진입 한도에는 포함하지만 모니터링·청산 대상으로 가져오지 않는다.
        """
        try:
            if self._execution_mode(exchange_name) == ExecutionMode.PAPER:
                self.logger.info(f"🧪 {exchange_name} PAPER - 실제 포지션 복구 차단")
                return
            # Binance는 고유 Trader 경로에서 처리하므로 여기서 스킵
            if str(exchange_name).lower() == 'binance':
                self.logger.info("바이낸스 포지션 복구는 Trader 경로에서 처리됨 (Unified 경로 스킵)")
                return

            venue = str(exchange_name or '').lower()
            managed = self._managed_open_trade_map(venue)
            self.active_positions.setdefault(venue, {})
            self.external_position_symbols.setdefault(venue, set())
            self.external_position_symbols[venue].clear()
            adapter = self.get_exchange_client(venue)
            if not adapter:
                self.logger.warning(f"{venue} 포지션 복구 생략: 거래소 클라이언트 없음")
                return

            if venue in {'upbit', 'bithumb'}:
                from trading.spot_position_policy import balance_quantity, safe_managed_close_quantity, spot_base_asset
                try:
                    balances = adapter.get_balance() or {}
                except Exception as exc:
                    self.logger.warning(f"{venue} 현물 복구 잔고 조회 실패: {exc}")
                    return
                restored = 0
                for key, row in managed.items():
                    symbol = str(row.get('symbol') or '')
                    actual_qty = balance_quantity(balances, spot_base_asset(symbol))
                    managed_qty = safe_managed_close_quantity(
                        managed_quantity=float(row.get('quantity') or 0.0),
                        actual_quantity=actual_qty,
                        baseline_quantity=float(row.get('spot_baseline_quantity') or 0.0),
                    )
                    if managed_qty <= 0:
                        continue
                    try:
                        current_price = float(self.exchange_manager.get_current_price(symbol, venue) or 0.0)
                    except Exception:
                        current_price = float(row.get('entry_price') or 0.0)
                    position = Position(
                        symbol=symbol,
                        side=PositionSide.LONG,
                        entry_price=float(row.get('entry_price') or current_price),
                        current_price=current_price,
                        quantity=managed_qty,
                        leverage=1,
                        unrealized_pnl=0.0,
                        unrealized_pnl_percent=0.0,
                        entry_time=parse_entry_time(row.get('entry_time')),
                        tp_price=float(row.get('tp_price') or 0.0) or None,
                        sl_price=float(row.get('sl_price') or 0.0) or None,
                        position_id=str(row.get('id') or ''),
                        entry_order_id=str(row.get('order_id') or ''),
                        entry_order_ids=list(row.get('_entry_order_ids') or []),
                        entry_time_source='execution',
                        execution_mode=str(row.get('execution_mode') or 'live'),
                        position_owner=NOAH_POSITION_OWNER,
                        spot_baseline_quantity=float(row.get('spot_baseline_quantity') or 0.0),
                    )
                    self.active_positions[venue][symbol] = position
                    restored += 1
                self.logger.info(
                    f"✅ {venue} NoahAI 소유 현물 복구: {restored}개 "
                    f"(수동 잔고는 복구·청산 대상 제외)"
                )
                return

            actual_positions = adapter.get_positions() if hasattr(adapter, 'get_positions') else []
            actual_by_symbol = {
                normalize_position_symbol(pos.get('symbol')): pos
                for pos in (actual_positions or [])
                if isinstance(pos, dict) and float(pos.get('contracts') or pos.get('size') or 0.0) > 0
            }
            restored = 0
            for key, pos_data in actual_by_symbol.items():
                row = managed.get(key)
                if row is None:
                    self.external_position_symbols[venue].add(str(pos_data.get('symbol') or key))
                    continue
                symbol = str(pos_data.get('symbol') or row.get('symbol') or '')
                side_str = str(pos_data.get('side') or row.get('side') or '').lower()
                restored_tp, restored_sl = self._get_restored_tp_sl_prices(venue, symbol)
                position = Position(
                    symbol=symbol,
                    side=PositionSide.LONG if side_str in {'long', 'buy'} else PositionSide.SHORT,
                    entry_price=float(pos_data.get('entryPrice') or row.get('entry_price') or 0.0),
                    current_price=float(pos_data.get('markPrice') or pos_data.get('last') or 0.0),
                    quantity=float(pos_data.get('contracts') or pos_data.get('size') or row.get('quantity') or 0.0),
                    leverage=int(float(pos_data.get('leverage') or row.get('leverage') or 1)),
                    unrealized_pnl=float(pos_data.get('unrealizedPnl') or 0.0),
                    unrealized_pnl_percent=float(pos_data.get('percentage') or 0.0),
                    entry_time=parse_entry_time(row.get('entry_time')),
                    tp_price=float(row.get('tp_price') or restored_tp or 0.0) or None,
                    sl_price=float(row.get('sl_price') or restored_sl or 0.0) or None,
                    position_id=str(row.get('id') or ''),
                    entry_order_id=str(row.get('order_id') or ''),
                    entry_order_ids=list(row.get('_entry_order_ids') or []),
                    entry_time_source='execution',
                    execution_mode=str(row.get('execution_mode') or 'live'),
                    position_owner=NOAH_POSITION_OWNER,
                )
                self.active_positions[venue][symbol] = position
                restored += 1
            self.logger.info(
                f"✅ {venue} 소유권 대조 복구: NoahAI {restored}개, "
                f"수동/외부 {len(self.external_position_symbols[venue])}개(자동청산 제외)"
            )
        except Exception as e:
            self.logger.error(f"❌ {exchange_name} 포지션 복구 실패: {e}")

    def get_active_positions(self, exchange_name: Optional[str] = None) -> Dict[str, Dict[str, Position]]:
        """활성 포지션 조회"""
        if exchange_name:
            return {exchange_name: self._position_store(exchange_name)}
        result: Dict[str, Dict[str, Position]] = {}
        exchanges = set(self.active_positions) | set(getattr(self, 'paper_positions', {}))
        for name in exchanges:
            result[name] = self._position_store(name)
        return result

    def get_trade_stats(self, exchange_name: Optional[str] = None) -> Dict[str, Any]:
        """거래 통계 조회"""
        if exchange_name:
            return self._trade_stats_store(exchange_name)
        return {
            name: self._trade_stats_store(name)
            for name in (set(self.trade_stats) | set(self.paper_trade_stats))
        }

    def start_trading(self, exchange_name: str):
        """거래소별 실행 시작.

        학습 범위에만 포함된 거래소도 분석·학습 루프를 시작한다. 실제 주문은
        execute_trading_cycle_unified의 주문 단계에서 별도로 차단한다.
        """
        try:
            trade_enabled = self._is_trade_enabled(exchange_name)
            learning_enabled = self._is_learning_enabled(exchange_name)
            if not trade_enabled and not learning_enabled:
                self.logger.warning(
                    f"⚠️ {exchange_name} 실행 시작 취소 - 거래·학습 활성 범위에 없습니다."
                )
                return False
            if not self._ensure_exchange_initialized(exchange_name):
                self.logger.warning(f"⚠️ {exchange_name} 실행 시작 취소 - 거래소 초기화 실패")
                return False

            # 이미 실행 중이면 중복 스레드 생성 방지
            if self.monitoring_flags.get(exchange_name, False):
                thread = self.monitoring_threads.get(exchange_name)
                if thread is not None and thread.is_alive():
                    self.logger.info(f"ℹ️ {exchange_name} 이미 실행 중 - start 재요청 무시")
                    return True

            # 거래 시작 전 거래소별 코인 준비 보장
            selected = list(self.selected_coins.get(exchange_name, []) or [])
            if not selected:
                selected = self.select_trading_coins_unified(exchange_name)
            if not selected:
                self.logger.warning(f"⚠️ {exchange_name} 거래 시작 취소 - 선택된 코인 없음")
                return False

            self.monitoring_flags[exchange_name] = True
            self.trading_cycles[exchange_name] = True

            # 모니터링 스레드 시작
            monitoring_thread = threading.Thread(
                target=self._monitoring_loop,
                args=(exchange_name,),
                daemon=True
            )
            monitoring_thread.start()
            self.monitoring_threads[exchange_name] = monitoring_thread

            execution_mode = self._execution_mode(exchange_name)
            mode_label = {
                ExecutionMode.LIVE: "실거래",
                ExecutionMode.PAPER: "페이퍼",
                ExecutionMode.LEARNING: "학습 전용",
            }[execution_mode]
            self.logger.info(f"🚀 {exchange_name} {mode_label} 실행 시작")
            self.logger.info(f"{mode_label} 실행 시작 (ex={exchange_name})")
            return True

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} 거래 시작 실패: {e}")
            return False

    def stop_trading(self, exchange_name: str, close_all: bool = False):
        """거래소별 거래 중지

        close_all=True: 보유 포지션을 시장가로 즉시 청산 (close_all 정책)
        close_all=False (기본): 신규 진입만 차단, 기존 포지션은 TP/SL에 맡김
        """
        try:
            self.monitoring_flags[exchange_name] = False
            self.trading_cycles[exchange_name] = False

            # close_all 정책: 보유 포지션 즉시 시장가 청산
            if close_all:
                if self._execution_mode(exchange_name) == ExecutionMode.PAPER:
                    self.paper_positions.setdefault(exchange_name, {}).clear()
                    self.logger.info(f"🧪 {exchange_name} PAPER 포지션 전체 정리 완료")
                    return
                try:
                    exchange = self.unified_manager.get_exchange(exchange_name)
                    if exchange:
                        positions = exchange.fetch_positions() or []
                        for pos in positions:
                            contracts = float(pos.get('contracts') or pos.get('contractSize') or 0)
                            symbol = pos.get('symbol', '')
                            side = pos.get('side', '')
                            if contracts <= 0 or not symbol:
                                continue
                            tracked_positions = self.active_positions.get(exchange_name, {})
                            tracked_position = tracked_positions.get(symbol)
                            if tracked_position is None:
                                normalized_symbol = (
                                    str(symbol).upper()
                                    .replace("/", "")
                                    .replace(":", "")
                                    .replace("-", "")
                                )
                                for tracked_symbol, candidate in tracked_positions.items():
                                    normalized_tracked = (
                                        str(tracked_symbol).upper()
                                        .replace("/", "")
                                        .replace(":", "")
                                        .replace("-", "")
                                    )
                                    if (
                                        normalized_tracked == normalized_symbol
                                        or normalized_tracked.startswith(normalized_symbol)
                                        or normalized_symbol.startswith(normalized_tracked)
                                    ):
                                        tracked_position = candidate
                                        symbol = tracked_symbol
                                        break
                            if tracked_position is not None:
                                if not is_noah_managed_position(tracked_position):
                                    self.logger.warning(
                                        f"수동/외부 포지션 보호: {exchange_name} {symbol} close_all 제외"
                                    )
                                    continue
                                current_price = float(
                                    pos.get("markPrice")
                                    or pos.get("last")
                                    or tracked_position.current_price
                                    or tracked_position.entry_price
                                    or 0.0
                                )
                                self._close_position_unified(
                                    exchange_name,
                                    symbol,
                                    tracked_position,
                                    current_price,
                                )
                                continue
                            self.logger.warning(
                                f"수동/외부 포지션 보호: {exchange_name} {symbol} "
                                f"계정 포지션은 close_all 자동청산에서 제외"
                            )
                except Exception as pe:
                    self.logger.warning(f"⚠️ close_all: {exchange_name} 포지션 조회 실패: {pe}")

            # 모니터링 스레드 종료 대기
            if exchange_name in self.monitoring_threads:
                thread = self.monitoring_threads[exchange_name]
                if thread.is_alive():
                    thread.join(timeout=5)
                del self.monitoring_threads[exchange_name]

            self.logger.info(f"⏹️ {exchange_name} 거래 중지")
            self.logger.info(f"거래 중지 (ex={exchange_name})")
            flush_kpi_events(timeout=5.0)

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} 거래 중지 실패: {e}")

    def _monitoring_loop(self, exchange_name: str):
        """거래소별 모니터링 루프"""
        try:
            while self.monitoring_flags.get(exchange_name, False):
                # 중단 신호를 바로 감지
                if not self.monitoring_flags.get(exchange_name, False):
                    break
                # 거래 사이클 실행
                self.execute_trading_cycle_unified(exchange_name)

                # 대기 (1초 단위로 중단 신호 감지)
                try:
                    wait_secs = int(self.monitoring_interval)
                except Exception:
                    wait_secs = 1
                for _ in range(max(1, wait_secs)):
                    if not self.monitoring_flags.get(exchange_name, False):
                        break
                    time.sleep(1)

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} 모니터링 루프 실패: {e}")

    def set_evaluator(self, evaluator):
        """evaluator 설정 (코인 선택용)"""
        self.evaluator = evaluator
        self.logger.info("✅ Evaluator 설정 완료")

    def set_selected_coins(self, exchange_name: str, selected_coins: List[Dict[str, Any]]):
        """명시한 거래소의 선택 코인만 설정한다."""
        try:
            target_exchange = self._normalize_exchange(exchange_name)
            if not target_exchange or target_exchange not in self.enabled_exchanges:
                self.logger.warning(
                    f"활성 대상이 아닌 거래소의 선택 코인 주입을 거부합니다: {target_exchange or 'missing'}"
                )
                return

            self.selected_coins[target_exchange] = list(selected_coins or [])

            if hasattr(self, 'main_app') and self.main_app:
                if not hasattr(self.main_app, 'selected_coins_by_exchange'):
                    self.main_app.selected_coins_by_exchange = {}
                self.main_app.selected_coins_by_exchange[target_exchange] = list(selected_coins or [])

            self.logger.info(f"✅ UnifiedTrader에 선택된 코인 설정 완료: {target_exchange} {len(selected_coins)}개")

        except Exception as e:
            self.logger.error(f"❌ 선택된 코인 설정 실패: {e}")

    def update_selected_coins(self, exchange_name: str, selected_coins: List[Dict[str, Any]]):
        """특정 거래소의 선택된 코인 업데이트"""
        try:
            self.selected_coins[exchange_name] = selected_coins.copy()
            self.logger.info(f"✅ {exchange_name} 선택된 코인 업데이트 완료: {len(selected_coins)}개")

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} 선택된 코인 업데이트 실패: {e}")

    def _auto_adjust_threshold_from_performance(self, exchange_name: str):
        """🤖 AI 기반 신호 기준 자동 조절 (OpenAI API 활용) - 거래소별"""
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
                return  # 조용히 스킵

            # 3. 거래 데이터 수집 (거래소별)
            all_trades = []
            for coin_trades in self.risk_manager.coin_trade_history.values():
                # 해당 거래소의 거래만 필터링
                exchange_trades = [t for t in coin_trades if t.get('exchange') == exchange_name]
                all_trades.extend(exchange_trades)

            # RiskManager 메모리에 exchange 태그가 비어있을 수 있으므로 DB 이력으로 보강한다.
            if len(all_trades) < 10 and hasattr(self, 'recorder') and self.recorder:
                try:
                    db_trades = self.recorder.get_recent_trades(coin='', exchange=exchange_name, days=30) or []
                    existing_timestamps = {t.get('timestamp') for t in all_trades if t.get('timestamp')}
                    for row in db_trades:
                        if not isinstance(row, dict):
                            continue
                        ts = row.get('exit_time') or row.get('timestamp')
                        if ts and ts in existing_timestamps:
                            continue
                        pnl_percent = float(row.get('pnl_percent', row.get('pnl', 0.0)) or 0.0)
                        all_trades.append({
                            'result': 'PROFIT' if pnl_percent > 0 else 'LOSS',
                            'profit': pnl_percent,
                            'profit_rate': pnl_percent,
                            'timestamp': ts,
                            'exchange': exchange_name,
                        })
                        if ts:
                            existing_timestamps.add(ts)
                except Exception as db_err:
                    self.logger.warning(f"[{exchange_name}] DB 거래 이력 보강 실패: {db_err}")

            total_count = len(all_trades)

            # 4. 최소 거래 수 체크 (10거래 미만은 학습 부족)
            if total_count < 10:
                return

            # 5. 조절 빈도 제어 (거래소별 카운터, 5거래마다 한 번씩만)
            if not hasattr(self, '_last_adjust_count_by_exchange'):
                self._last_adjust_count_by_exchange = {}

            last_count = self._last_adjust_count_by_exchange.get(exchange_name, 0)
            if total_count - last_count < 5:
                return

            # 6. 거래 성과 분석
            context = self._collect_trading_context_for_ai(all_trades, exchange_name)

            # 같은 거래 표본에서 응답 오류가 나도 매 사이클 재호출하지 않는다.
            self._last_adjust_count_by_exchange[exchange_name] = total_count

            # 7. AI에게 최적값 질문
            ai_result = self._ask_ai_for_optimal_threshold(context, exchange_name)

            if not ai_result:
                return  # 조용히 스킵

            # 8. AI 추천값 적용
            self._apply_ai_threshold_recommendation(ai_result, context, exchange_name)

        except Exception as e:
            self.logger.error(f"[{exchange_name}] AI 자동 조절 오류: {e}")

    def _collect_trading_context_for_ai(self, all_trades: list, exchange_name: str) -> dict:
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

            # 시장 변동성 (첫 코인 기준)
            try:
                first_symbol = recent[0].get('coin', 'BTCUSDT') + 'USDT' if recent else 'BTCUSDT'
                volatility = 0.01  # 기본값
            except:
                volatility = 0.01

            return {
                'exchange': exchange_name,
                'total_trades': len(all_trades),
                'recent_trades': len(recent),
                'win_count': len(wins),
                'loss_count': len(losses),
                'win_rate': (len(wins) / len(recent) * 100) if recent else 0,
                'avg_profit_percent': avg_profit,
                'avg_loss_percent': avg_loss,
                'profit_loss_ratio': (avg_profit / avg_loss) if avg_loss > 0 else 0,
                'current_threshold': self.analyzer.get_user_signal_threshold(exchange_name),
                'market_volatility': volatility,
                'consecutive_losses': getattr(self.risk_manager, 'consecutive_losses', 0)
            }
        except Exception as e:
            self.logger.error(f"[{exchange_name}] 거래 상황 수집 오류: {e}")
            return {}

    def _ask_ai_for_optimal_threshold(self, context: dict, exchange_name: str) -> Optional[dict]:
        """AI에게 최적 threshold 질문"""
        try:
            system_prompt = "You are an expert cryptocurrency trading system optimizer. Analyze trading performance and recommend optimal signal threshold."

            user_prompt = f"""
Analyze the current trading performance and recommend optimal user_signal_threshold value.

Exchange: {context['exchange']}

Current Trading Data:
- Total Trades: {context['total_trades']}
- Recent 30 Trades: {context['recent_trades']}
- Win Rate: {context['win_rate']:.1f}%
- Wins/Losses: {context['win_count']}/{context['loss_count']}
- Average Profit: {context['avg_profit_percent']:.2f}%
- Average Loss: {context['avg_loss_percent']:.2f}%
- Profit/Loss Ratio: {context['profit_loss_ratio']:.2f}
- Current Threshold: {context['current_threshold']}
- Market Volatility: {context['market_volatility']:.2%}
- Consecutive Losses: {context['consecutive_losses']}

Signal Threshold Explanation:
- Lower value (30-50): More trades, higher sensitivity, aggressive
- Medium value (50-65): Balanced approach
- Higher value (65-80): Fewer trades, conservative, quality focus

Constraints:
- Must be integer between 30 and 80
- Consider win rate, profit/loss ratio, and market volatility
- If consecutive losses > 3, recommend conservative value

Response in JSON format:
{{
  "optimal_threshold": integer (30-80),
  "reasoning": "detailed explanation in Korean",
  "expected_outcome": "expected trading improvement in Korean",
  "risk_level": "LOW/MEDIUM/HIGH",
  "adjustment_type": "AGGRESSIVE/MODERATE/CONSERVATIVE/MAINTAIN"
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
                    max_tokens=500,
                )
            else:
                result = self.ai_manager.client.chat_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.3,
                    max_tokens=500
                )

            return result

        except Exception as e:
            self.logger.error(f"[{exchange_name}] AI 질문 오류: {e}")
            return None

    def _apply_ai_threshold_recommendation(self, ai_result: dict, context: dict, exchange_name: str):
        """AI 추천값을 시스템에 적용"""
        try:
            new_threshold = ai_result.get('optimal_threshold')
            current_threshold = context['current_threshold']

            # 유효성 검사
            if not new_threshold or not isinstance(new_threshold, (int, float)):
                self.logger.error(f"[{exchange_name}] ⚠️ AI 응답 오류: 잘못된 threshold 값 - {new_threshold}")
                return

            new_threshold = int(new_threshold)

            # 범위 체크 (30-80)
            if new_threshold < 30 or new_threshold > 80:
                self.logger.warning(f"[{exchange_name}] ⚠️ AI 추천값 범위 초과: {new_threshold} → 범위 내로 조정")
                new_threshold = max(30, min(80, new_threshold))

            # 변경이 없으면 스킵
            if new_threshold == current_threshold:
                self.logger.info(f"[{exchange_name}] ✅ AI 분석 완료: 현재 설정({current_threshold}) 유지 권장")
                return

            # 1. 메모리에 즉시 적용 - 다른 거래소의 학습 기준을 변경하지 않는다.
            self.analyzer.set_user_signal_threshold(new_threshold, exchange_name=exchange_name)

            # 2. 거래소별 settings에 영구 저장
            analyzer_settings = self.settings.setdefault('analyzer_settings', {})
            exchange_thresholds = analyzer_settings.setdefault('exchange_signal_thresholds', {})
            exchange_thresholds[str(exchange_name).lower()] = new_threshold
            from config.settings import save_settings
            save_settings(self.settings)

            # 3. 상세 로그 출력
            self.logger.info(f"""
╔══════════════════════════════════════════════════════════════╗
║     🤖 AI 기반 신호 기준 자동 조절 완료 [{exchange_name}]    ║
╠══════════════════════════════════════════════════════════════╣
║ 이전 값: {current_threshold} → 새 값: {new_threshold}
║ 조절 유형: {ai_result.get('adjustment_type', 'N/A')}
║ 위험도: {ai_result.get('risk_level', 'N/A')}
║
║ [거래 성과]
║ - 총 거래: {context['total_trades']}회
║ - 승률: {context['win_rate']:.1f}%
║ - 손익비: {context['profit_loss_ratio']:.2f}
║ - 연속 손실: {context['consecutive_losses']}회
║
║ [AI 분석]
║ {ai_result.get('reasoning', 'N/A')}
║
║ [예상 효과]
║ {ai_result.get('expected_outcome', 'N/A')}
╚══════════════════════════════════════════════════════════════╝
            """)

        except Exception as e:
            self.logger.error(f"[{exchange_name}] AI 추천값 적용 오류: {e}")

    def _generate_ai_learning_data(self, exchange_name: str, symbol: str, signal_data: Dict[str, Any]):
        """AI 학습 데이터 생성 (ai_manager 유무와 무관하게 기록).
        - 기존에는 ai_manager가 없으면 반환했으나, 신호/분석 히스토리는 항상 남겨야 하므로 제거.
        """
        try:
            perf = self._collect_symbol_performance_snapshot_unified(exchange_name=exchange_name, symbol=symbol)

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
                elm = self._learning_managers.get(exchange_name)
                if elm is None:
                    elm = ExchangeLearningManager(exchange_name)
                    self._learning_managers[exchange_name] = elm
                elm.add_learning_data(learning_data)
            except Exception:
                # 조용히 패스(학습 저장 실패가 거래 흐름을 막지 않도록)
                pass

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {symbol} AI 학습 데이터 생성 실패: {e}")

    def _perform_pre_entry_analysis_unified(self, exchange_name: str, symbol: str, signal_data: Dict) -> Dict:
        """AI 기반 진입 전 분석 (거래소별)"""
        try:
            # 분석 시작 로그
            self._log_trade_event('analysis', f"{symbol} 분석 시작", exchange=exchange_name, verbose_only=True)

            # 1. 최근 거래 이력 분석
            pattern_analysis = self._analyze_recent_trading_patterns_unified(exchange_name, symbol)

            # 2. 현재 시장 조건 평가
            market_conditions = self._evaluate_current_market_conditions_unified(exchange_name, symbol)

            # WebSocket 데이터 체크 (verbose)
            try:
                if isinstance(self.settings, dict) and self.settings.get('verbose_trade_logging', False):
                    has_depth = hasattr(self, 'depth_data')
                    has_ticker = hasattr(self, 'ticker_data')
                    self._log_trade_event('analysis', f"{symbol} WebSocket data check: depth={'✓' if has_depth else '✗'}, ticker={'✓' if has_ticker else '✗'}", exchange=exchange_name)
            except Exception:
                pass

            # 3. AI 기반 종합 판단
            ai_validation = self._ai_validate_entry_conditions_unified(
                exchange_name, symbol, signal_data, pattern_analysis, market_conditions
            )

            # 4. 🔥 동적 임계값 기반 최종 결정
            dynamic_thresholds = self._get_dynamic_entry_thresholds_unified(exchange_name, symbol, market_conditions)
            try:
                base_snapshot = dynamic_thresholds.get('_base', {}) if isinstance(dynamic_thresholds, dict) else {}
                source = dynamic_thresholds.get('_source', 'unknown') if isinstance(dynamic_thresholds, dict) else 'unknown'
                self._log_trade_event(
                    'analysis',
                    (
                        f"[{symbol}] 학습 반영 임계값(before->after): "
                        f"min_ai_confidence {base_snapshot.get('min_ai_confidence', 'N/A')} -> {dynamic_thresholds.get('min_ai_confidence', 'N/A')}, "
                        f"max_loss_rate {base_snapshot.get('max_loss_rate', 'N/A')} -> {dynamic_thresholds.get('max_loss_rate', 'N/A')}, "
                        f"min_trades_history {base_snapshot.get('min_trades_history', 'N/A')} -> {dynamic_thresholds.get('min_trades_history', 'N/A')} "
                        f"(source={source})"
                    ),
                    exchange=exchange_name,
                )
            except Exception:
                pass

            proceed = (
                pattern_analysis['loss_rate'] < dynamic_thresholds['max_loss_rate'] and
                pattern_analysis['recent_trades'] >= dynamic_thresholds['min_trades_history'] and
                market_conditions['volatility_suitable'] and
                ai_validation['confidence'] >= dynamic_thresholds['min_ai_confidence']
            )

            reason = ai_validation.get('reasoning', '진입 조건 분석 완료')
            if not proceed:
                # 거래 이력이 실제 요구 조건보다 부족할 때만 cold-start 차단으로 안내한다.
                if pattern_analysis['recent_trades'] < dynamic_thresholds['min_trades_history']:
                    reason = f"거래 이력 부족 ({pattern_analysis['recent_trades']}회)"
                elif pattern_analysis['loss_rate'] >= 50.0:
                    reason = f"높은 손실률 ({pattern_analysis['loss_rate']:.1f}%)"
                elif not market_conditions['volatility_suitable']:
                    reason = "변동성 부적절"
                else:
                    reason = f"AI 신뢰도 부족 ({ai_validation['confidence']:.1f})"

            self.logger.info(f"[{exchange_name}] [{symbol}] 진입 전 분석 결과:")
            self.logger.info(f"  - 최근 손실률: {pattern_analysis['loss_rate']:.1f}%")
            self.logger.info(f"  - 거래 이력: {pattern_analysis['recent_trades']}회")
            self.logger.info(f"  - 변동성 적합: {market_conditions['volatility_suitable']}")
            self.logger.info(f"  - AI 신뢰도: {ai_validation['confidence']:.1f}")
            self.logger.info(f"  - 결정: {'진입 허용' if proceed else '진입 금지'} ({reason})")
            # 실시간 로그 스트림에 요약 전달 (trade 카테고리)
            try:
                from log_system.log_stream import get_log_stream
                stream = get_log_stream()
                stream.add_event(exchange_name, 'INFO', 'trade', (
                    f"[진입 전 분석] {symbol}: 손실률 {pattern_analysis['loss_rate']:.1f}%, 거래 {pattern_analysis['recent_trades']}회, "
                    f"변동성 {market_conditions['volatility_suitable']}, AI {ai_validation['confidence']:.1f}, "
                    f"결정: {'허용' if proceed else '금지'} ({reason})"
                ))
            except Exception:
                pass

            return {
                'proceed': proceed,
                'reason': reason,
                'pattern_analysis': pattern_analysis,
                'market_conditions': market_conditions,
                'ai_validation': ai_validation
            }

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {symbol} 진입 전 분석 실패: {e}")
            try:
                log_exception('trade', f"진입 전 분석 실패: {symbol}", exchange=exchange_name, exc=e)
            except Exception:
                pass
            return {'proceed': False, 'reason': f'분석 오류: {str(e)}'}

    def _analyze_recent_trading_patterns_unified(self, exchange_name: str, symbol: str) -> Dict:
        """최근 거래 패턴 분석 (거래소별) - 실제 데이터베이스에서 로드"""
        try:
            # 실제 데이터베이스에서 최근 거래 이력 조회
            if hasattr(self, 'recorder') and self.recorder:
                # 최근 30일간 해당 코인의 거래 이력 조회
                recent_trades = []
                try:
                    method = getattr(self.recorder, 'get_recent_trades', None)
                    if callable(method):
                        rt = method(symbol=symbol, exchange=exchange_name, days=30)
                        recent_trades = rt if isinstance(rt, list) else []
                    else:
                        rt = self.recorder.get_trade_history(symbol=symbol, days=30)
                        recent_trades = rt if isinstance(rt, list) else []
                except Exception:
                    recent_trades = []

                if isinstance(recent_trades, list) and len(recent_trades) > 0:
                    # 🔥 확장된 분석: 최근 50회 거래 분석
                    recent_trades = recent_trades[-50:]  # 최근 50회로 제한

                    # recent_trades가 dict/list/tuple/None 등 섞여도 안전하게 PnL을 수집
                    from typing import List

                    def _to_float(val) -> float:
                        try:
                            if val is None:
                                return 0.0
                            return float(val)
                        except Exception:
                            return 0.0

                    pnl_values: List[float] = []
                    for t in recent_trades:
                        if isinstance(t, dict):
                            # dict: 우선 'pnl', 없으면 'pnl_percent' 사용
                            v = t.get('pnl')
                            if v is None:
                                v = t.get('pnl_percent')
                            pnl_values.append(_to_float(v))
                        elif isinstance(t, (list, tuple)):
                            # tuple/list: trade_log 테이블 인덱스 기준
                            # id(0), symbol(1), entry_price(2), exit_price(3), quantity(4),
                            # leverage(5), pnl(6), pnl_percent(7), entry_time(8), exit_time(9), ...
                            v = None
                            if len(t) > 6 and t[6] is not None:
                                v = t[6]
                            elif len(t) > 7:
                                v = t[7]
                            pnl_values.append(_to_float(v))
                        else:
                            pnl_values.append(0.0)

                    # 통계 계산
                    total_trades = len(pnl_values)
                    profitable_trades = sum(1 for v in pnl_values if v > 0)
                    loss_trades = sum(1 for v in pnl_values if v < 0)

                    # 라플라스 스무딩으로 극단값(0%/100%) 완화
                    if total_trades > 0:
                        win_rate = ((profitable_trades + 1) / (total_trades + 2)) * 100.0
                        loss_rate = ((loss_trades + 1) / (total_trades + 2)) * 100.0
                    else:
                        win_rate = 0.0
                        loss_rate = 0.0

                    profits = [v for v in pnl_values if v > 0]
                    losses = [v for v in pnl_values if v < 0]

                    avg_profit = (sum(profits) / len(profits)) if profits else 0.0
                    avg_loss = (sum(losses) / len(losses)) if losses else 0.0

                    # 🔥 시장 상황별 분석 추가
                    market_analysis = self._analyze_market_conditions_patterns_unified(recent_trades)

                    # 🔥 시간대별 분석 추가
                    time_analysis = self._analyze_time_patterns_unified(recent_trades)

                    # 🔥 최근 성과 추세 분석
                    trend_analysis = self._analyze_performance_trend_unified(recent_trades)

                    return {
                        'loss_rate': loss_rate,
                        'recent_trades': total_trades,
                        'win_rate': win_rate,
                        'avg_profit': avg_profit,
                        'avg_loss': avg_loss,
                        'data_insufficient': bool(total_trades < 20),  # 최소 20회 필요
                        'used_defaults': False,
                        'market_analysis': market_analysis,  # 시장 상황별 분석
                        'time_analysis': time_analysis,       # 시간대별 분석
                        'trend_analysis': trend_analysis      # 성과 추세 분석
                    }

            # 데이터가 없거나 recorder가 없으면 완화된 기본값 반환
            return {
                'loss_rate': 0.0,
                'recent_trades': 0,
                'win_rate': 0.0,
                'avg_profit': 0.0,
                'avg_loss': 0.0,
                'data_insufficient': True,
                'used_defaults': True
            }

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"❌ {exchange_name} {symbol} 패턴 분석 실패: {e}")
            return {'loss_rate': 100.0, 'recent_trades': 0, 'win_rate': 0.0, 'avg_profit': 0.0, 'avg_loss': 0.0}

    def _check_and_reselect_coins_unified_optimized(self, exchange_name: str):
        """최적화된 코인 재선택 로직 (CCXT 거래소용)"""
        try:
            # 1. 코인이 비어있으면 선택
            current_selected = list(self.selected_coins.get(exchange_name, []) or [])
            if not current_selected:
                self.logger.info(f"{exchange_name} 선택된 코인 없음 - 코인 선택 필요")
                return

            # 2. 시장 상황 변화 체크 (1시간마다) - 최적화
            import time
            current_time = time.time()

            last_analysis_time = self.last_market_analysis_time_by_exchange.get(exchange_name)
            if last_analysis_time is None:
                # 첫 실행 시 시간 기록 (거래 시작 시점)
                self.last_market_analysis_time_by_exchange[exchange_name] = current_time
                regime = self._evaluate_current_market_conditions_unified_fast(exchange_name, 'BTCUSDT')
                self.last_market_regime_by_exchange[exchange_name] = regime
                self.log_event('analysis', f"{exchange_name} 시장 분석 시작 - 기준 시간: {time.strftime('%H:%M:%S', time.localtime(current_time))}", exchange=exchange_name)
                self.log_event('analysis', f"{exchange_name} 시장 상황 분석 결과: {regime}", exchange=exchange_name)
                return

            # 1시간 경과 체크 (거래 시작 시점 기준)
            time_elapsed = current_time - float(last_analysis_time)
            if time_elapsed > 3600:  # 1시간
                self.log_event('analysis', f"{exchange_name} 1시간 경과 - 시장 재분석 시작 (경과: {time_elapsed/3600:.1f}시간)", exchange=exchange_name)

                current_regime = self._evaluate_current_market_conditions_unified_fast(exchange_name, 'BTCUSDT')
                last_regime = self.last_market_regime_by_exchange.get(exchange_name)

                if last_regime is not None and current_regime != last_regime:
                    self.logger.info(f"{exchange_name} 시장 상황 변경 감지: {last_regime} → {current_regime}")

                    # 3. 거래 진행 중인지 확인
                    active_positions = self.get_active_positions(exchange_name).get(exchange_name, {})
                    if active_positions:
                        self.logger.warning(f"{exchange_name} 거래 진행 중 - 코인 재선택 연기 (활성 포지션: {len(active_positions)}개)")
                        self.logger.info(f"{exchange_name} 모든 거래 완료 후 다음 사이클에서 재선택 예정")
                    else:
                        self.logger.info(f"{exchange_name} 거래 없음 - 코인 재선택 실행")
                        self._reselect_coins_unified(exchange_name)
                else:
                    self.logger.info(f"{exchange_name} 시장 상황 유지: {current_regime}")

                self.last_market_regime_by_exchange[exchange_name] = current_regime
                self.last_market_analysis_time_by_exchange[exchange_name] = current_time

        except Exception as e:
            self.logger.error(f"{exchange_name} 코인 재선택 체크 오류: {e}")

    def _check_and_reselect_coins_unified(self, exchange_name: str):
        """코인 재선택 로직 (CCXT 거래소용)"""
        try:
            # 1. 코인이 비어있으면 선택
            current_selected = list(self.selected_coins.get(exchange_name, []) or [])
            if not current_selected:
                self.logger.info(f"{exchange_name} 선택된 코인 없음 - 코인 선택 필요")
                return

            # 2. 시장 상황 변화 체크 (1시간마다)
            import time
            current_time = time.time()

            last_analysis_time = self.last_market_analysis_time_by_exchange.get(exchange_name)
            if last_analysis_time is None:
                # 첫 실행 시 시간 기록
                self.last_market_analysis_time_by_exchange[exchange_name] = current_time
                self.last_market_regime_by_exchange[exchange_name] = self._evaluate_current_market_conditions_unified(exchange_name, 'BTCUSDT')
                return

            # 1시간 경과 체크
            if current_time - float(last_analysis_time) > 3600:  # 1시간
                current_regime = self._evaluate_current_market_conditions_unified(exchange_name, 'BTCUSDT')
                last_regime = self.last_market_regime_by_exchange.get(exchange_name)

                if last_regime is not None and current_regime != last_regime:
                    self.logger.info(f"{exchange_name} 시장 상황 변경 감지: {last_regime} → {current_regime}")

                    # 3. 거래 진행 중인지 확인
                    active_positions = self.get_active_positions(exchange_name).get(exchange_name, {})
                    if active_positions:
                        self.logger.warning(f"{exchange_name} 거래 진행 중 - 코인 재선택 연기 (활성 포지션: {len(active_positions)}개)")
                        self.logger.info(f"{exchange_name} 모든 거래 완료 후 다음 사이클에서 재선택 예정")
                    else:
                        self.logger.info(f"{exchange_name} 거래 없음 - 코인 재선택 실행")
                        self._reselect_coins_unified(exchange_name)

                self.last_market_regime_by_exchange[exchange_name] = current_regime
                self.last_market_analysis_time_by_exchange[exchange_name] = current_time

        except Exception as e:
            self.logger.error(f"{exchange_name} 코인 재선택 체크 오류: {e}")

    def _reselect_coins_unified(self, exchange_name: str):
        """실제 코인 재선택 실행 (CCXT 거래소용)"""
        try:
            self.logger.info(f"🔄 {exchange_name} 코인 재선택 시작...")

            # 1. 현재 시장 상황 분석
            current_regime = self._evaluate_current_market_conditions_unified(exchange_name, 'BTCUSDT')
            self.logger.info(f"{exchange_name} 현재 시장 상황: {current_regime}")

            # 2. 기존 코인 백업
            old_coins = list(self.selected_coins.get(exchange_name, []) or [])
            self.logger.info(f"{exchange_name} 기존 코인: {len(old_coins)}개")

            # 3. 거래소별 재선택 (전역 selected_coins 오염 경로 제거)
            new_coins = list(self.select_trading_coins_unified(exchange_name) or [])

            # 4. 코인 변경 로그
            if new_coins != old_coins:
                self.logger.info(f"{exchange_name} 코인 변경 완료: {len(old_coins)}개 → {len(new_coins)}개")
                self.logger.info(f"{exchange_name} 새로운 코인: {[coin.get('symbol', '') for coin in new_coins]}")

                # 5. WebSocket 구독 업데이트 (CCXT는 WebSocket 없음)
                self.logger.info(f"{exchange_name} WebSocket 구독 업데이트 완료")
            else:
                self.logger.info(f"{exchange_name} 코인 변경 없음 - 동일한 코인 유지")

        except Exception as e:
            self.logger.error(f"{exchange_name} 코인 재선택 실행 오류: {e}")
            import traceback
            self.logger.error(f"{exchange_name} 코인 재선택 상세 오류: {traceback.format_exc()}")

    def _evaluate_current_market_conditions_unified_fast(self, exchange_name: str, symbol: str) -> str:
        """빠른 CCXT 시장 상황 분석 (최적화)"""
        try:
            # 최소한의 데이터만 요청 (20개 캔들)
            klines = []
            try:
                if hasattr(self, 'exchange_manager') and self.exchange_manager:
                    klines = self.exchange_manager.get_klines(symbol, interval='15m', limit=20, exchange_name=exchange_name)
            except Exception:
                pass

            if not klines or len(klines) < 10:
                return 'normal'

            prices = [kline_number(k, "close") for k in klines]
            volumes = [kline_number(k, "volume") for k in klines]

            # 간단한 RSI 계산 (10기간)
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

            if len(gains) >= 10:
                avg_gain = sum(gains[-10:]) / 10
                avg_loss = sum(losses[-10:]) / 10

                if avg_loss == 0:
                    rsi = 100
                else:
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))
            else:
                rsi = 50

            # 간단한 트렌드 분석 (10기간)
            recent_prices = prices[-10:]
            if len(recent_prices) >= 2:
                trend_slope = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
                if trend_slope > 0.03:  # 3% 이상 상승
                    trend = 'UPTREND'
                elif trend_slope < -0.03:  # 3% 이상 하락
                    trend = 'DOWNTREND'
                else:
                    trend = 'SIDEWAYS'
            else:
                trend = 'SIDEWAYS'

            # 간단한 거래량 분석
            if len(volumes) >= 5:
                avg_volume = sum(volumes[-5:]) / 5
                current_volume = volumes[-1]
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            else:
                volume_ratio = 1.0

            # 간단한 변동성 분석 (30분 가격 변화율)
            if len(prices) >= 2:
                price_change_30m = (prices[-1] - prices[-2]) / prices[-2] * 100
            else:
                price_change_30m = 0.0

            # 시장 상황 판단 (간소화)
            if rsi > 65 and trend == 'UPTREND' and volume_ratio > 1.2:
                regime = 'bull'  # 상승장
            elif rsi < 35 and trend == 'DOWNTREND' and volume_ratio > 1.2:
                regime = 'bear'  # 하락장
            elif abs(price_change_30m) > 2.0:  # 30분 내 2% 이상 변동
                regime = 'volatile'  # 변동성 높음
            else:
                regime = 'normal'  # 정상 시장

            # 시장 분석 결과 로그
            if hasattr(self, 'logger') and self.logger:
                self.log_event('analysis', f"🔍 {exchange_name} 빠른 시장 분석 결과:", exchange=exchange_name)
                self.log_event('analysis', f"  - RSI: {rsi:.2f}", exchange=exchange_name)
                self.log_event('analysis', f"  - 트렌드: {trend}", exchange=exchange_name)
                self.log_event('analysis', f"  - 거래량 비율: {volume_ratio:.2f}", exchange=exchange_name)
                self.log_event('analysis', f"  - 30분 가격변화: {price_change_30m:.2f}%", exchange=exchange_name)
                self.log_event('analysis', f"  - 판단: {regime}", exchange=exchange_name)

            return regime

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"{exchange_name} 빠른 시장 분석 오류: {e}")
            return 'normal'

    def _evaluate_current_market_conditions_unified(self, exchange_name: str, symbol: str) -> Dict:
        """현재 시장 조건 평가 (거래소별)"""
        try:
            # 1) 심볼별 OHLCV 데이터 확보 (가능하면 ExchangeManager 우선)
            klines = []
            try:
                if hasattr(self, 'exchange_manager') and self.exchange_manager and hasattr(self.exchange_manager, 'get_klines'):
                    klines = self.exchange_manager.get_klines(symbol, interval='15m', limit=60, exchange_name=exchange_name)  # type: ignore[arg-type]
            except Exception:
                klines = []
            if not klines and hasattr(self, 'analyzer') and self.analyzer and hasattr(self.analyzer, '_get_klines'):
                try:
                    klines = self.analyzer._get_klines(symbol, '15m', 60)  # type: ignore[attr-defined]
                except Exception:
                    klines = []

            def _to_float(v, default=0.0):
                try:
                    if v is None:
                        return float(default)
                    return float(v)
                except Exception:
                    return float(default)

            volatility_suitable = False
            volume_suitable = False
            trend_suitable = False
            trend_strength = 0.0
            avg_return = 0.0
            volume_ratio = 0.0
            short_sma = None
            long_sma = None

            if klines and len(klines) >= 25:
                # Binance/CCXT 포맷 가정: [openTime, open, high, low, close, volume, ...]
                closes = []
                highs = []
                lows = []
                volumes = []
                for k in klines:
                    try:
                        # 일부 거래소/어댑터는 값이 문자열일 수 있음 → 안전 변환
                        opens = _to_float(k[1]) if len(k) > 1 else None
                        highs.append(_to_float(k[2]) if len(k) > 2 else 0.0)
                        lows.append(_to_float(k[3]) if len(k) > 3 else 0.0)
                        closes.append(_to_float(k[4]) if len(k) > 4 else (opens or 0.0))
                        volumes.append(_to_float(k[5]) if len(k) > 5 else 0.0)
                    except Exception:
                        continue

                # 1-a) 변동성(평균 절대 수익률) 계산
                returns = []
                for i in range(1, len(closes)):
                    prev = closes[i-1]
                    cur = closes[i]
                    if prev > 0:
                        returns.append(abs(cur - prev) / prev)
                if returns:
                    avg_return = sum(returns[-30:]) / min(len(returns), 30)  # 최근 30개 기준

                # 심볼 분류: 메이저/알트
                majors = {'BTCUSDT', 'ETHUSDT', 'BNBUSDT'}
                is_major = symbol.upper() in majors

                # 설정 기반 변동성 임계치
                min_th = 0.0006
                max_th = 0.02
                try:
                    aset = (self.settings.get('analyzer_settings', {}) or {}).get('volatility_thresholds', {}) if isinstance(self.settings, dict) else {}
                    if is_major:
                        min_th = float(aset.get('major_min', 0.0002))
                        max_th = float(aset.get('major_max', 0.015))
                    else:
                        min_th = float(aset.get('altcoin_min', 0.0006))
                        max_th = float(aset.get('altcoin_max', 0.02))
                except Exception:
                    pass

                volatility_suitable = (avg_return >= min_th) and (avg_return <= max_th)

                # 1-b) 거래량 적합성: 최근 vs 평균 비율로 평가(절대 임계치 대신 동적)
                if len(volumes) >= 20:
                    recent_vol = sum(volumes[-3:]) / 3.0
                    avg_vol = sum(volumes[-20:]) / 20.0
                    if avg_vol > 0:
                        volume_ratio = recent_vol / avg_vol
                        # 최근 거래량이 평균의 0.8배 이상이면 적합으로 간주
                        volume_suitable = volume_ratio >= 0.8

                # 1-c) 트렌드 적합성: 단순 20/50 SMA 기울기 차이
                try:
                    if len(closes) >= 50:
                        short_window = 20
                        long_window = 50
                        short_sma = sum(closes[-short_window:]) / float(short_window)
                        long_sma = sum(closes[-long_window:]) / float(long_window)
                    elif len(closes) >= 30:  # 데이터가 적을 때 완화
                        short_window = 10
                        long_window = 30
                        short_sma = sum(closes[-short_window:]) / float(short_window)
                        long_sma = sum(closes[-long_window:]) / float(long_window)
                    if short_sma and long_sma and long_sma > 0:
                        trend_strength = abs(short_sma - long_sma) / long_sma
                        # 충분한 추세 구분이 되는지(완만한 횡보 제외)
                        trend_suitable = trend_strength >= 0.002  # 0.2%
                except Exception:
                    trend_suitable = False

            # 2) 전체 시장 스트레스 레벨 (Analyzer의 시장 분석 활용)
            market_level = 'NORMAL'
            try:
                if hasattr(self, 'analyzer') and self.analyzer and hasattr(self.analyzer, '_analyze_current_market_conditions'):
                    md = self.analyzer._analyze_current_market_conditions()  # type: ignore[attr-defined]
                    market_level = str(md.get('level', 'NORMAL'))
            except Exception:
                market_level = 'NORMAL'

            return {
                'volatility_suitable': bool(volatility_suitable),
                'volume_suitable': bool(volume_suitable),
                'trend_suitable': bool(trend_suitable),
                'market_stress': market_level,
                # 참고용 메트릭(상위 호출에서 요약 로그로 활용)
                'metrics': {
                    'avg_return': avg_return,
                    'volume_ratio': volume_ratio,
                    'trend_strength': trend_strength,
                    'short_sma': short_sma,
                    'long_sma': long_sma,
                }
            }
        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {symbol} 시장 조건 평가 실패: {e}")
            return {'volatility_suitable': False, 'volume_suitable': False, 'trend_suitable': False, 'market_stress': 'HIGH'}

    def _ai_validate_entry_conditions_unified(self, exchange_name: str, symbol: str, signal_data: Dict, pattern_analysis: Dict, market_conditions: Dict) -> Dict:
        """AI 기반 진입 조건 검증 (거래소별)"""
        try:
            # 🔥 AI 기반 동적 신뢰도 계산
            base_confidence = 0.6  # 기본 신뢰도 (보수적으로 설정)
            confidence = base_confidence
            reasoning_parts = []

            # 패턴 분석 기반 신뢰도 조정 (더 정교한 로직)
            loss_rate = pattern_analysis.get('loss_rate', 50)
            win_rate = pattern_analysis.get('win_rate', 50)
            recent_trades = pattern_analysis.get('recent_trades', 0)

            has_completed_history = recent_trades > 0 and not pattern_analysis.get('used_defaults')
            if has_completed_history:
                # 실제 청산 표본이 있을 때만 0%/100%를 성과로 해석한다.
                if win_rate > 70:
                    confidence += 0.2
                    reasoning_parts.append(f"높은 승률({win_rate:.1f}%)")
                elif win_rate < 30:
                    confidence -= 0.2
                    reasoning_parts.append(f"낮은 승률({win_rate:.1f}%)")

                if loss_rate > 60:
                    confidence -= 0.25
                    reasoning_parts.append(f"높은 손실률({loss_rate:.1f}%)")
                elif loss_rate < 20:
                    confidence += 0.15
                    reasoning_parts.append(f"낮은 손실률({loss_rate:.1f}%)")

                if recent_trades < 5:
                    confidence -= 0.1
                    reasoning_parts.append("청산 표본 부족")
                elif recent_trades > 20:
                    confidence += 0.1
                    reasoning_parts.append("충분한 거래 이력")
            else:
                reasoning_parts.append("완료 거래 없음·제한 학습 허용")

            # 신뢰도 범위 제한 (0.1 ~ 0.95)
            confidence = max(0.1, min(0.95, confidence))

            # 데이터 신뢰도 주석 추가(표본 부족/기본값 사용)
            data_notes = []
            if pattern_analysis.get('data_insufficient'):
                data_notes.append('성과 표본 없음(진입 차단 사유 아님)')
            if pattern_analysis.get('used_defaults'):
                data_notes.append('중립 기본값 사용')
            note_suffix = f" | 데이터: {', '.join(data_notes)}" if data_notes else ''
            reasoning = f"동적 AI 검증: {', '.join(reasoning_parts) if reasoning_parts else '기본 검증'}{note_suffix}"

            # 시장 조건 기반 조정
            if not market_conditions.get('volatility_suitable', True):
                confidence -= 0.3
                reasoning += " + 부적절한 변동성"

            # 신호 데이터 기반 조정
            signal_confidence = signal_data.get('confidence', 0.5)
            if signal_confidence > 0.8:
                confidence += 0.1
                reasoning += " + 강한 신호"
            elif signal_confidence < 0.5:
                confidence -= 0.1
                reasoning += " + 약한 신호"

            # 최종 신뢰도 범위 제한
            confidence = max(0.0, min(confidence, 1.0))

            return {
                'confidence': confidence,
                'reasoning': reasoning,
                'validation': 'APPROVED' if confidence >= 0.4 else 'REJECTED',
                'cold_start': not has_completed_history,
                'history_gate_blocked': False,
            }

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {symbol} AI 검증 오류: {e}")
            return {
                'confidence': 0.5,
                'reasoning': f'AI 검증 오류: {str(e)}',
                'validation': 'ERROR'
            }

    def _calculate_dynamic_confidence_threshold_unified(self, exchange_name: str, symbol: str, signal_data: Dict) -> float:
        """AI 기반 동적 신뢰도 임계값 계산 (거래소별)"""
        try:
            # 기본 임계값 (완화)
            base_threshold = 0.4  # 0.6 → 0.4 (완화)

            # 시장 상황별 조정
            if self.analyzer:
                try:
                    market_data = self.analyzer._analyze_current_market_conditions()
                    market_level = market_data.get('level', 'NORMAL')

                    if market_level == 'HIGH':
                        market_factor = 0.9  # 고변동성: 더 높은 신뢰도 요구
                    elif market_level == 'LOW':
                        market_factor = 0.7  # 저변동성: 낮은 신뢰도도 허용
                    else:
                        market_factor = 0.8

                    base_threshold *= market_factor
                except Exception:
                    pass

            # 연속 성공/실패 이력 고려
            if self.risk_manager:
                coin = symbol.replace('USDT', '')
                consecutive_wins = self.risk_manager.coin_consecutive_wins.get(coin, 0)
                consecutive_losses = self.risk_manager.coin_consecutive_losses.get(coin, 0)

                # 연속 성공 → 신뢰도 요구사항 완화
                if consecutive_wins >= 3:
                    base_threshold *= 0.8
                # 연속 실패 → 신뢰도 요구사항 강화
                elif consecutive_losses >= 3:
                    base_threshold *= 1.2

            # 최종 임계값 범위 제한
            return max(0.3, min(base_threshold, 0.9))

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {symbol} 동적 임계값 계산 실패: {e}")
            return 0.6  # 기본값 반환

    def _get_ai_enhanced_parameters_unified(self, exchange_name: str, symbol: str, analysis: Dict, pre_entry_analysis: Dict) -> Dict:
        """AI 강화 파라미터 적용 (거래소별)"""
        try:
            # 기본 파라미터
            params = {
                'tp_percent': analysis.get('tp_percent', 0.0018),
                'sl_percent': analysis.get('sl_percent', 0.0020),
                'leverage': analysis.get('leverage', 10),
                'position_size_factor': 1.0,
                'entry_confidence': analysis.get('confidence', 0.5)
            }

            # AI 분석 결과 적용
            ai_validation = pre_entry_analysis.get('ai_validation', {})
            if ai_validation.get('confidence', 0) > 0.8:
                # 높은 신뢰도 → 더 공격적 설정
                params['tp_percent'] *= 1.2
                params['leverage'] = min(params['leverage'] * 1.1, 20)
                params['position_size_factor'] = 1.2
            elif ai_validation.get('confidence', 0) < 0.5:
                # 낮은 신뢰도 → 더 보수적 설정
                params['tp_percent'] *= 0.8
                params['leverage'] = max(params['leverage'] * 0.9, 1)
                params['position_size_factor'] = 0.8

            # 패턴 분석 결과 적용
            pattern_analysis = pre_entry_analysis.get('pattern_analysis', {})
            if pattern_analysis.get('loss_rate', 0) > 40:
                # 높은 손실률 → 보수적 설정
                params['tp_percent'] *= 0.9
                params['sl_percent'] *= 0.8
                params['position_size_factor'] *= 0.7

            return params

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {symbol} AI 강화 파라미터 적용 실패: {e}")
            return {
                'tp_percent': 0.0018,
                'sl_percent': 0.0020,
                'leverage': 10,
                'position_size_factor': 1.0,
                'entry_confidence': 0.5
            }

    def _calculate_position_size_unified(self, exchange_name: str, symbol: str, analysis: Dict, optimized_params: Dict) -> float:
        """AI 기반 포지션 크기 계산 (거래소 타입별 분기)"""
        try:
            # 🔥 현물 거래소는 포지션 크기 개념이 다름 (실제 매수량)
            if exchange_name in ['upbit', 'bithumb']:
                return self._calculate_spot_position_size(exchange_name, symbol, analysis, optimized_params)

            # 🔥 선물 거래소별 최소 포지션 크기 설정 (CCXT 거래소만)
            exchange_min_sizes = {
                'okx': 1.0,      # OKX는 대부분 1개 이상
                'bybit': 0.1,    # Bybit는 보통 0.1개 이상
                'bitget': 0.1,   # Bitget도 0.1개 이상
            }

            # 기본 포지션 크기 (거래소별 최소값 고려)
            base_size = exchange_min_sizes.get(exchange_name, 0.1)

            # 1. AI 신뢰도에 따른 조정
            confidence = analysis.get('confidence', 0.5)
            confidence_factor = 0.3 + (confidence * 0.7)  # 0.3 ~ 1.0

            # 2. 시장 상황에 따른 조정
            market_factor = 1.0
            if self.analyzer:
                try:
                    market_data = self.analyzer._analyze_current_market_conditions()
                    market_level = market_data.get('level', 'NORMAL')

                    if market_level == 'HIGH':
                        market_factor = 0.8  # 고변동성: 더 작은 포지션
                    elif market_level == 'LOW':
                        market_factor = 1.2  # 저변동성: 더 큰 포지션
                except Exception:
                    pass

            # 3. 거래소별 조정
            exchange_factor = self._get_exchange_position_factor(exchange_name)

            # 4. 최적화된 파라미터 적용
            position_size_factor = optimized_params.get('position_size_factor', 1.0)

            # 5. 리스크 관리 기반 조정
            risk_factor = self._calculate_risk_factor_unified(exchange_name, symbol, analysis)

            # 6. 성과 기반 보정(최근 승률)
            performance_factor = 1.0
            try:
                window = max(1, int(self.settings.get('risk_winrate_window', 10)))
                down_th = float(self.settings.get('risk_downshift_threshold', 40))
                up_th = float(self.settings.get('risk_upshift_threshold', 60))
                f_down = float(self.settings.get('risk_shift_factor_down', 0.85))
                f_up = float(self.settings.get('risk_shift_factor_up', 1.10))
                outcomes = list(getattr(self, '_recent_outcomes', {}).get(exchange_name, []))
                wins = sum(1 for ok in outcomes if ok)
                total = len(outcomes)
                win_rate = (wins / total) * 100 if total else None
                if win_rate is not None:
                    if win_rate < down_th:
                        performance_factor *= f_down
                    elif win_rate > up_th:
                        performance_factor *= f_up
            except Exception:
                performance_factor = 1.0

            # 7. 최종 포지션 크기 계산
            pre_clamp = (base_size * confidence_factor * market_factor *
                         exchange_factor * position_size_factor * risk_factor * performance_factor)
            final_size = pre_clamp

            # 8. 최소/최대 제한
            min_size = 0.001
            max_size = self._get_max_position_size_unified(exchange_name, symbol)
            # 설정 오버라이드 최소값
            try:
                overrides = (self.settings.get('exchange_risk_overrides', {}) or {}).get(exchange_name, {})
                if 'min_position_size' in overrides:
                    min_size = float(overrides.get('min_position_size', min_size))
            except Exception:
                pass

            final_size = max(min_size, min(final_size, max_size))

            # 상세 디버그 로깅(설정으로 제어)
            debug_enabled = False
            try:
                if isinstance(self.settings, dict):
                    debug_enabled = bool(self.settings.get('position_sizing_debug', False))
            except Exception:
                debug_enabled = False

            self.logger.info(
                f"📊 {exchange_name} {symbol} 포지션 크기: {final_size:.6f} "
                f"(신뢰도: {confidence_factor:.2f}, 시장: {market_factor:.2f}, "
                f"거래소: {exchange_factor:.2f}, 리스크: {risk_factor:.2f})"
            )
            if debug_enabled:
                self.logger.info(
                    "🔎 PositionSizing Debug → "
                    f"base={base_size}, conf={confidence_factor:.4f}, market={market_factor:.4f}, "
                    f"exchange={exchange_factor:.4f}, opt_factor={position_size_factor:.4f}, risk={risk_factor:.4f}, perf={performance_factor:.4f}, "
                    f"pre_clamp={pre_clamp:.8f}, min={min_size}, max={max_size}, final={final_size:.8f}"
                )

            return final_size

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {symbol} 포지션 크기 계산 실패: {e}")
            return 0.001  # 기본값 반환

    def _get_exchange_position_factor(self, exchange_name: str) -> float:
        """거래소별 포지션 크기 팩터"""
        try:
            # 설정 기반 거래소별 보정 계수 (CCXT 거래소만)
            default_factors = {
                'bybit': 0.9,        # 약간 보수적
                'okx': 0.8,          # 더 보수적
                'bitget': 0.85,      # 보수적
                'upbit': 0.7,        # 현물 거래소: 더 보수적
                'bithumb': 0.7       # 현물 거래소: 더 보수적
            }
            settings_factors = {}
            try:
                if isinstance(self.settings, dict):
                    settings_factors = self.settings.get('exchange_position_factors', {}) or {}
            except Exception:
                settings_factors = {}
            factors = default_factors.copy()
            factors.update(settings_factors)
            return float(factors.get(exchange_name, 1.0))

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} 거래소 팩터 조회 실패: {e}")
            return 1.0

    def _calculate_risk_factor_unified(self, exchange_name: str, symbol: str, analysis: Dict) -> float:
        """리스크 기반 포지션 크기 팩터"""
        try:
            risk_factor = 1.0

            # 1. 연속 손실 이력 고려
            if self.risk_manager:
                coin = symbol.replace('USDT', '')
                consecutive_losses = self.risk_manager.coin_consecutive_losses.get(coin, 0)

                if consecutive_losses >= 3:
                    risk_factor *= 0.5  # 연속 손실 시 50% 감소
                elif consecutive_losses >= 2:
                    risk_factor *= 0.7  # 2회 연속 손실 시 30% 감소

            # 2. 일일 손실 한도 고려
            if self.risk_manager and hasattr(self.risk_manager, 'daily_pnl'):
                daily_pnl = getattr(self.risk_manager, 'daily_pnl', 0)
                if daily_pnl < -2.0:  # 일일 손실 2% 이상
                    risk_factor *= 0.6  # 40% 감소

            # 3. 시장 변동성 고려
            volatility = analysis.get('market_volatility', 'NORMAL')
            if volatility == 'HIGH':
                risk_factor *= 0.8  # 고변동성 시 20% 감소
            elif volatility == 'LOW':
                risk_factor *= 1.1  # 저변동성 시 10% 증가

            # 범위 제한
            clamped = max(0.1, min(risk_factor, 2.0))  # 0.1 ~ 2.0

            # 디버그 로깅(설정)
            debug_enabled = False
            try:
                if isinstance(self.settings, dict):
                    debug_enabled = bool(self.settings.get('position_sizing_debug', False))
            except Exception:
                debug_enabled = False
            if debug_enabled:
                self.logger.info(
                    "🔎 RiskFactor Debug → "
                    f"exchange={exchange_name}, symbol={symbol}, "
                    f"consecutive_losses={self.risk_manager.coin_consecutive_losses.get(symbol.replace('USDT',''), 0) if self.risk_manager else 'NA'}, "
                    f"daily_pnl={getattr(self.risk_manager, 'daily_pnl', 'NA') if self.risk_manager else 'NA'}, "
                    f"volatility={analysis.get('market_volatility', 'NA')}, raw={risk_factor:.4f}, clamped={clamped:.4f}"
                )

            return clamped

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {symbol} 리스크 팩터 계산 실패: {e}")
            return 1.0

    def _get_max_position_size_unified(self, exchange_name: str, symbol: str) -> float:
        """거래소별 최대 포지션 크기"""
        try:
            # 거래소별 최대 포지션 크기 제한 (CCXT 거래소만)
            max_sizes = {
                'bybit': 0.008,      # 0.008 BTC
                'okx': 0.006,        # 0.006 BTC
                'bitget': 0.007,     # 0.007 BTC
                'upbit': 0.005,      # 현물: 더 작은 크기
                'bithumb': 0.005     # 현물: 더 작은 크기
            }

            return max_sizes.get(exchange_name, 0.01)

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} 최대 포지션 크기 조회 실패: {e}")
            return 0.01

    def _record_position_with_tp_sl(
        self,
        exchange_name: str,
        symbol: str,
        signal: str,
        quantity: float,
        order_result: Dict[str, Any],
        optimized_params: Dict,
        execution_mode: str = 'live',
    ):
        """TP/SL 포함 포지션 기록 (거래소별)"""
        try:
            entry_price = float(order_result.get('price', 0.0))
            # 가격 누락 시 현재가로 선보정 (TP/SL 계산 전에 실행)
            if not entry_price or entry_price <= 0:
                try:
                    if hasattr(self, 'exchange_manager') and self.exchange_manager:
                        ep = self.exchange_manager.get_current_price(symbol, exchange_name)
                        if ep and ep > 0:
                            entry_price = float(ep)
                except Exception:
                    pass

            lev = int(optimized_params.get('leverage', self.settings.get('default_leverage', 10))) if isinstance(optimized_params, dict) else 10
            # tp/sl 퍼센트가 None/빈값이면 기본값 사용
            try:
                _tpv = optimized_params.get('tp_percent') if isinstance(optimized_params, dict) else None
                tp_pct = float(_tpv) if _tpv not in (None, '') else float(self.settings.get('default_tp', 0.0018))
            except Exception:
                tp_pct = float(self.settings.get('default_tp', 0.0018))
            try:
                _slv = optimized_params.get('sl_percent') if isinstance(optimized_params, dict) else None
                sl_pct = float(_slv) if _slv not in (None, '') else float(self.settings.get('default_sl', 0.0020))
            except Exception:
                sl_pct = float(self.settings.get('default_sl', 0.0020))

            side_enum = PositionSide.LONG if signal.upper() == 'LONG' else PositionSide.SHORT
            if entry_price and entry_price > 0:
                if side_enum == PositionSide.LONG:
                    tp_price = entry_price * (1 + tp_pct)
                    sl_price = entry_price * (1 - sl_pct)
                else:
                    tp_price = entry_price * (1 - tp_pct)
                    sl_price = entry_price * (1 + sl_pct)
            else:
                tp_price = 0.0
                sl_price = 0.0

            position = Position(
                symbol=symbol,
                side=side_enum,
                entry_price=entry_price,
                current_price=entry_price,
                quantity=quantity,
                leverage=lev,
                unrealized_pnl=0.0,
                unrealized_pnl_percent=0.0,
                entry_time=datetime.now(timezone.utc),
                tp_price=tp_price,
                sl_price=sl_price,
                execution_mode=execution_mode,
                position_owner=NOAH_POSITION_OWNER,
                custom_strategy_id=optimized_params.get('_selected_custom_strategy_id'),
                custom_strategy_name=optimized_params.get('_selected_custom_strategy'),
                custom_strategy_rules=dict(optimized_params.get('_custom_strategy_rules') or {}),
                spot_baseline_quantity=float(
                    optimized_params.get('_spot_baseline_quantity', 0.0) or 0.0
                ),
            )

            position.entry_order_id = (
                order_result.get('order_id')
                or order_result.get('orderId')
                or order_result.get('id')
            )

            self._position_store(exchange_name)[symbol] = position
            entry_order_id = (
                order_result.get('order_id')
                or order_result.get('orderId')
                or order_result.get('id')
            )
            _, position.position_id = emit_position_opened(
                asset_class='crypto',
                venue=exchange_name,
                symbol=symbol,
                side=position.side.value,
                opened_at=position.entry_time,
                entry_price=position.entry_price,
                quantity=position.quantity,
                position_id=position.position_id,
                entry_order_id=entry_order_id,
                execution_mode=execution_mode,
                source='noahai_client_unified_position',
                extra={'leverage': int(lev or 1)},
            )
            # 실제 체결 원장(exchange_execution_log)은 주문 단위 감사 기록이고,
            # trade_log는 진입→청산 성과 생명주기다. 기존 공통 거래소 경로는
            # 전자만 기록해 청산 시 UPDATE 대상이 없었고, 통계/AI 리포트에서
            # 거래가 영구 누락됐다. LIVE 진입은 두 원장을 함께 시작한다.
            if str(execution_mode or '').lower() == 'live':
                recorder = getattr(self, 'recorder', None)
                entry_logger = getattr(recorder, 'log_trade_entry', None)
                if callable(entry_logger):
                    trade_log_id = entry_logger(
                        position,
                        {
                            'exchange': exchange_name,
                            'order_id': entry_order_id,
                            'reason': 'AI live entry',
                            'execution_mode': execution_mode,
                            'spot_baseline_quantity': position.spot_baseline_quantity,
                        },
                    )
                    if trade_log_id is None:
                        self.logger.error(
                            f"{exchange_name} {symbol} 포지션 생성 후 거래 생명주기 원장 시작 실패"
                        )
            self.logger.info(
                f"✅ {exchange_name} {symbol} 포지션 기록 완료 (entry={entry_price:.6f}, TP={tp_price:.6f}, SL={sl_price:.6f}, lev={lev}x)"
            )
        except Exception as e:
            self.logger.error(f"❌ {exchange_name} {symbol} 포지션 기록 실패: {e}")

    def _record_exchange_execution(
        self,
        exchange_name: str,
        symbol: str,
        side: str,
        order_result: Dict[str, Any],
        *,
        source: str,
    ) -> None:
        """실주문 결과를 거래소 체결 원장에 즉시 기록한다."""
        recorder = getattr(self, 'recorder', None)
        saver = getattr(recorder, 'save_exchange_execution_history', None)
        receipt_saver = getattr(recorder, 'save_exchange_order_receipt', None)
        if not isinstance(order_result, dict):
            return
        try:
            raw = order_result.get('raw_result')
            payload = dict(raw) if isinstance(raw, dict) else {}
            payload.update({
                'id': payload.get('id') or order_result.get('order_id') or order_result.get('id'),
                'order': payload.get('order') or order_result.get('order_id') or order_result.get('id'),
                'symbol': payload.get('symbol') or order_result.get('symbol') or symbol,
                'side': payload.get('side') or order_result.get('side') or side,
                'price': (
                    payload.get('average') or payload.get('price')
                    or order_result.get('price')
                ),
                'amount': (
                    payload.get('filled') or payload.get('amount')
                    or order_result.get('filled') or order_result.get('quantity')
                ),
                'filled': (
                    payload.get('filled') or order_result.get('filled')
                    or order_result.get('quantity')
                ),
                'cost': payload.get('cost') or order_result.get('cost'),
                'timestamp': payload.get('timestamp') or order_result.get('timestamp'),
                'status': payload.get('status') or order_result.get('status'),
            })
            payload['_execution_confirmed'] = bool(
                payload.get('_execution_confirmed')
                or order_result.get('_execution_confirmed')
            )
            if callable(receipt_saver):
                receipt_saver(exchange_name, payload, source=source)
            if payload['_execution_confirmed'] and callable(saver):
                saver(exchange_name, [payload], source=source)
            elif not payload['_execution_confirmed']:
                self.logger.warning(
                    f"{exchange_name} {symbol} 주문 접수됨 · 실제 체결 확인 대기"
                )
        except Exception as exc:
            self.logger.warning(
                f"{exchange_name} {symbol} 실제 체결 원장 기록 실패(거래 계속): {exc}"
            )

    def _confirm_ccxt_order_result(
        self,
        exchange_client: Any,
        order_result: Dict[str, Any],
        *,
        symbol: str,
    ) -> Dict[str, Any]:
        """모든 CCXT 거래소 주문을 개별 주문 조회로 확정한 뒤 공통 형식으로 반환한다."""
        if not isinstance(order_result, dict) or exchange_client is None:
            return order_result
        ccxt_exchange = getattr(exchange_client, 'exchange', None)
        if ccxt_exchange is None:
            return order_result
        try:
            from trading.exchanges.execution_history import confirm_ccxt_order_execution

            raw = order_result.get('raw_result')
            seed = dict(raw) if isinstance(raw, dict) else dict(order_result)
            seed.setdefault(
                'id',
                order_result.get('order_id') or order_result.get('orderId') or order_result.get('id'),
            )
            seed.setdefault('order', seed.get('id'))
            seed.setdefault('symbol', order_result.get('symbol') or symbol)
            seed.setdefault('side', order_result.get('side'))
            seed.setdefault('filled', order_result.get('filled'))
            seed.setdefault('amount', order_result.get('amount') or order_result.get('quantity'))
            seed.setdefault('price', order_result.get('price'))
            seed.setdefault('cost', order_result.get('cost'))
            seed.setdefault('status', order_result.get('status'))
            formatter = getattr(exchange_client, '_display_symbol', None)
            confirmed = confirm_ccxt_order_execution(
                ccxt_exchange,
                seed,
                symbol=symbol,
                symbol_formatter=formatter if callable(formatter) else None,
            )
            merged = dict(order_result)
            merged.update({
                'order_id': confirmed.get('order') or confirmed.get('id'),
                'id': confirmed.get('id') or confirmed.get('order'),
                'symbol': confirmed.get('symbol') or symbol,
                'side': confirmed.get('side') or order_result.get('side'),
                'price': confirmed.get('average') or confirmed.get('price'),
                'average': confirmed.get('average') or confirmed.get('price'),
                'filled': confirmed.get('filled'),
                'quantity': confirmed.get('filled') or confirmed.get('amount'),
                'amount': confirmed.get('amount') or confirmed.get('filled'),
                'cost': confirmed.get('cost'),
                'fee': confirmed.get('fee'),
                'timestamp': confirmed.get('timestamp'),
                'datetime': confirmed.get('datetime'),
                '_execution_confirmed': bool(confirmed.get('_execution_confirmed')),
                '_execution_confirmation_source': confirmed.get('_execution_confirmation_source'),
                'raw_result': confirmed,
            })
            # 주문 성공 판정에는 원래 접수 상태를 보존하고, 원장의 raw_result에는
            # 거래소가 확인한 실제 상태를 남긴다.
            if not merged.get('status'):
                merged['status'] = confirmed.get('status')
            return merged
        except Exception as exc:
            self.logger.warning(f"{symbol} 개별 주문 체결 확인 실패: {exc}")
            fallback = dict(order_result)
            fallback['_execution_confirmed'] = False
            return fallback

    def reconcile_exchange_order_receipts(self, exchange_name: str, limit: int = 500) -> Dict[str, int]:
        """전체 체결목록 API가 없어도 로컬 주문 ID로 누락된 확정 체결을 복구한다."""
        result = {'checked': 0, 'confirmed': 0, 'pending': 0, 'failed': 0}
        recorder = getattr(self, 'recorder', None)
        getter = getattr(recorder, 'get_exchange_order_references', None)
        receipt_saver = getattr(recorder, 'save_exchange_order_receipt', None)
        execution_saver = getattr(recorder, 'save_exchange_execution_history', None)
        client = self.get_exchange_client(exchange_name)
        ccxt_exchange = getattr(client, 'exchange', None) if client is not None else None
        if not callable(getter) or ccxt_exchange is None:
            return result
        for reference in getter(exchange_name, limit=limit) or []:
            result['checked'] += 1
            try:
                confirmed = self._confirm_ccxt_order_result(
                    client,
                    {
                        'id': reference.get('order_id'),
                        'order_id': reference.get('order_id'),
                        'symbol': reference.get('symbol'),
                        'side': reference.get('side'),
                        'status': reference.get('status'),
                    },
                    symbol=str(reference.get('symbol') or ''),
                )
                raw = confirmed.get('raw_result')
                payload = dict(raw) if isinstance(raw, dict) else dict(confirmed)
                if callable(receipt_saver):
                    receipt_saver(exchange_name, payload, source='order_id_reconcile')
                if bool(payload.get('_execution_confirmed')):
                    if callable(execution_saver):
                        execution_saver(exchange_name, [payload], source='order_id_reconcile')
                    result['confirmed'] += 1
                else:
                    from .order_state_machine import reduce_order_state
                    state = reduce_order_state(reference.get('status'), payload)
                    if state['terminal']:
                        result['failed'] += 1
                    else:
                        result['pending'] += 1
            except Exception as exc:
                result['failed'] += 1
                self.logger.warning(
                    f"{exchange_name} 주문별 체결 복구 실패({reference.get('order_id')}): {exc}"
                )
        return result

    def get_exchange_statistics(self, exchange_name: str) -> Dict[str, Any]:
        """거래소별 통계 조회"""
        try:
            stats_store = self._trade_stats_store(exchange_name)
            if not stats_store:
                return {
                    'total_trades': 0,
                    'profitable_trades': 0,
                    'total_pnl': 0.0,
                    'win_rate': 0.0,
                    'avg_profit': 0.0,
                    'avg_loss': 0.0,
                    'max_profit': 0.0,
                    'max_loss': 0.0,
                    'active_positions': 0
                }

            stats = stats_store.copy()
            stats['active_positions'] = len(self._position_store(exchange_name))

            # 평균 수익/손실 계산
            if stats['total_trades'] > 0:
                profitable_count = stats['profitable_trades']
                loss_count = stats['total_trades'] - profitable_count

                if profitable_count > 0:
                    stats['avg_profit'] = stats['total_pnl'] / profitable_count
                if loss_count > 0:
                    stats['avg_loss'] = (stats['total_pnl'] - (profitable_count * stats['avg_profit'])) / loss_count

            return stats

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} 통계 조회 실패: {e}")
            return {}

    def get_all_statistics(self) -> Dict[str, Any]:
        """전체 통계 조회"""
        try:
            all_stats = {}
            total_trades = 0
            total_profitable = 0
            total_pnl = 0.0

            exchange_names = set(self.trade_stats) | set(self.paper_trade_stats)
            for exchange_name in exchange_names:
                exchange_stats = self.get_exchange_statistics(exchange_name)
                all_stats[exchange_name] = exchange_stats

                total_trades += exchange_stats['total_trades']
                total_profitable += exchange_stats['profitable_trades']
                total_pnl += exchange_stats['total_pnl']

            # 전체 통계
            all_stats['total'] = {
                'total_trades': total_trades,
                'profitable_trades': total_profitable,
                'total_pnl': total_pnl,
                'win_rate': (total_profitable / total_trades * 100) if total_trades > 0 else 0.0,
                'active_positions': sum(
                    len(self._position_store(name))
                    for name in exchange_names
                )
            }

            return all_stats

        except Exception as e:
            self.logger.error(f"❌ 전체 통계 조회 실패: {e}")
            return {}

    def generate_performance_report(self, exchange_name: Optional[str] = None) -> Dict[str, Any]:
        """성과 리포트 생성"""
        try:
            if exchange_name:
                stats = self.get_exchange_statistics(exchange_name)
                report = {
                    'exchange': exchange_name,
                    'period': 'all_time',
                    'generated_at': datetime.now(timezone.utc).isoformat(),
                    'statistics': stats,
                    'recommendations': self._generate_recommendations(exchange_name, stats)
                }
            else:
                all_stats = self.get_all_statistics()
                report = {
                    'period': 'all_time',
                    'generated_at': datetime.now(timezone.utc).isoformat(),
                    'statistics': all_stats,
                    'recommendations': self._generate_overall_recommendations(all_stats)
                }

            return report

        except Exception as e:
            self.logger.error(f"❌ 성과 리포트 생성 실패: {e}")
            return {}

    def _generate_recommendations(self, exchange_name: str, stats: Dict[str, Any]) -> List[str]:
        """거래소별 권장사항 생성"""
        try:
            recommendations = []

            # 승률 기반 권장사항
            win_rate = stats.get('win_rate', 0)
            if win_rate < 40:
                recommendations.append(f"⚠️ {exchange_name} 승률이 낮습니다 ({win_rate:.1f}%). 거래 전략을 재검토하세요.")
            elif win_rate > 70:
                recommendations.append(f"✅ {exchange_name} 승률이 우수합니다 ({win_rate:.1f}%). 현재 전략을 유지하세요.")

            # 총 PnL 기반 권장사항
            total_pnl = stats.get('total_pnl', 0)
            if total_pnl < -5:
                recommendations.append(f"🚨 {exchange_name} 총 손실이 큽니다 ({total_pnl:.2f}%). 거래를 일시 중단하세요.")
            elif total_pnl > 10:
                recommendations.append(f"🎉 {exchange_name} 수익이 우수합니다 ({total_pnl:.2f}%). 포지션 크기를 점진적으로 늘려보세요.")

            # 활성 포지션 기반 권장사항
            active_positions = stats.get('active_positions', 0)
            max_positions = self._get_ai_max_positions(exchange_name)  # 🔥 설정값 사용
            if active_positions > max_positions:
                recommendations.append(f"⚠️ {exchange_name} 활성 포지션이 많습니다 ({active_positions}개, 최대: {max_positions}개). 리스크를 관리하세요.")

            return recommendations

        except Exception as e:
            self.logger.error(f"❌ {exchange_name} 권장사항 생성 실패: {e}")
            return []

    def _generate_overall_recommendations(self, all_stats: Dict[str, Any]) -> List[str]:
        """전체 권장사항 생성"""
        try:
            recommendations = []
            total_stats = all_stats.get('total', {})

            # 전체 성과 기반 권장사항
            total_pnl = total_stats.get('total_pnl', 0)
            total_trades = total_stats.get('total_trades', 0)
            win_rate = total_stats.get('win_rate', 0)

            if total_trades > 0:
                if win_rate < 45:
                    recommendations.append("⚠️ 전체 승률이 낮습니다. AI 분석 파라미터를 조정하세요.")
                elif win_rate > 65:
                    recommendations.append("✅ 전체 승률이 우수합니다. 현재 설정을 유지하세요.")

                if total_pnl < -10:
                    recommendations.append("🚨 전체 손실이 큽니다. 거래를 일시 중단하고 전략을 재검토하세요.")
                elif total_pnl > 20:
                    recommendations.append("🎉 전체 수익이 우수합니다. 포지션 크기를 점진적으로 늘려보세요.")

            # 거래소별 성과 비교
            exchange_performance = []
            for exchange_name, stats in all_stats.items():
                if exchange_name != 'total' and stats['total_trades'] > 0:
                    exchange_performance.append((exchange_name, stats['win_rate'], stats['total_pnl']))

            if exchange_performance:
                # 승률 기준 정렬
                exchange_performance.sort(key=lambda x: x[1], reverse=True)
                best_exchange = exchange_performance[0]
                worst_exchange = exchange_performance[-1]

                if best_exchange[1] - worst_exchange[1] > 20:
                    recommendations.append(f"📊 {best_exchange[0]}의 성과가 우수합니다. 다른 거래소의 설정을 참고하세요.")

            return recommendations

        except Exception as e:
            self.logger.error(f"❌ 전체 권장사항 생성 실패: {e}")
            return []

    def update_settings(self, new_settings: Dict[str, Any]):
        """설정 업데이트"""
        sanitized = dict(new_settings or {})
        from config.settings import normalize_trade_rate
        for key, kind in (("default_tp", "tp"), ("default_sl", "sl")):
            if key not in sanitized:
                continue
            fallback, _ = normalize_trade_rate(
                self.settings.get(key, 0.0018 if kind == "tp" else 0.0020),
                kind=kind,
            )
            sanitized[key], changed = normalize_trade_rate(
                sanitized[key],
                kind=kind,
                fallback=fallback,
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
                    self.logger.info(
                        f"{key} 레거시 퍼센트 단위 자동 변환: "
                        f"{new_settings[key]} → {sanitized[key]}"
                    )
                else:
                    self.logger.warning(
                        f"⚠️ {key} 비정상 입력 안전값 복구: "
                        f"{new_settings[key]} → {sanitized[key]}"
                    )
        previous_modes = {
            ex: self._execution_mode(ex)
            for ex in getattr(self, 'enabled_exchanges', [])
        }
        self.settings.update(sanitized)
        # API 키/토큰 등 설정값 자체를 로그에 출력하지 않는다. 설정 저장 직후
        # 이 메서드를 호출하므로 키 이름만으로도 민감할 수 있는 항목은 제외한다.
        sensitive_tokens = ('key', 'secret', 'token', 'password', 'passphrase', 'credential')
        safe_keys = sorted(
            str(key)
            for key in sanitized.keys()
            if not any(token in str(key).lower() for token in sensitive_tokens)
        )
        self.logger.info(f"UnifiedTrader 설정 동기화 완료: 항목 {len(sanitized)}개, 일반 설정 키={safe_keys[:20]}")

        # 활성 거래소 목록 재계산
        self.enabled_exchanges = self._compute_enabled_exchanges()
        self.trade_enabled_exchanges = self._compute_trade_enabled_exchanges()
        self.learning_enabled_exchanges = self._compute_learning_enabled_exchanges()

        # 비활성 거래소 데이터 정리
        containers = [
            self.trade_stats,
            self.paper_trade_stats,
            self.active_positions,
            self.paper_positions,
            self.monitoring_flags,
            self.monitoring_threads,
            self.trade_entered,
            self.ai_optimization_cache,
            self.pattern_analysis_cache,
            self.price_data_points,
            self.advanced_order_managers,
            self.selected_coins,
            self.position_sizing_snapshots,
        ]
        for container in containers:
            for key in list(container.keys()):
                if key not in self.enabled_exchanges:
                    container.pop(key, None)

        # 활성 거래소는 지연 초기화로 전환: 기존 초기화 마크만 정리
        self._initialized_exchanges = {
            ex for ex in self._initialized_exchanges if ex in self.enabled_exchanges
        }
        for exchange_name in self.enabled_exchanges:
            if previous_modes.get(exchange_name) != self._execution_mode(exchange_name):
                self.monitoring_flags[exchange_name] = False
                self.trading_cycles[exchange_name] = False
                self._initialized_exchanges.discard(exchange_name)
                self.logger.info(
                    f"🔄 {exchange_name} 실행 모드 변경 - 안전한 재초기화를 위해 실행을 중지했습니다."
                )
        self._recent_outcomes = {ex: deque(maxlen=self._winrate_window) for ex in self.enabled_exchanges}

    # 🔥 사용되지 않는 함수 제거됨 (2025-10-20):
    # - execute_trade_unified() (라인 3443-3483): main.py에서만 호출되지만 main.py가 사용되지 않음
    #
    # 현재 실제 사용되는 CCXT 거래 실행 경로:
    # TradingWorker → start_trading → _monitoring_loop → execute_trading_cycle_unified → _execute_signal_trade
    #
    # 삭제 이유:
    # 1. main.py의 _execute_unified_trade 함수가 이미 삭제됨
    # 2. 동일한 기능을 execute_trading_cycle_unified가 수행함
    # 3. 코드 중복 제거 및 혼란 방지

    def _analyze_market_conditions_patterns_unified(self, trades: List[Dict]) -> Dict:
        """시장 상황별 거래 패턴 분석 (Unified)"""
        try:
            if len(trades) < 5:
                return {'bull_market': {}, 'bear_market': {}, 'sideways_market': {}}

            # 시장 상황 분류 (간단한 휴리스틱)
            bull_trades = []
            bear_trades = []
            sideways_trades = []

            for trade in trades:
                # 거래 시점의 시장 상황 추정 (가격 변화율 기반)
                price_change = trade.get('price_change_percent', 0)

                if price_change > 2.0:  # 2% 이상 상승
                    bull_trades.append(trade)
                elif price_change < -2.0:  # 2% 이상 하락
                    bear_trades.append(trade)
                else:  # 횡보
                    sideways_trades.append(trade)

            # 각 시장 상황별 승률 계산
            def calculate_win_rate(trade_list):
                if not trade_list:
                    return {'win_rate': 50.0, 'count': 0, 'avg_profit': 0.0}

                wins = sum(1 for t in trade_list if t.get('pnl', 0) > 0)
                total = len(trade_list)
                win_rate = (wins / total) * 100.0
                avg_profit = sum(t.get('pnl', 0) for t in trade_list if t.get('pnl', 0) > 0) / max(wins, 1)

                return {
                    'win_rate': win_rate,
                    'count': total,
                    'avg_profit': avg_profit
                }

            return {
                'bull_market': calculate_win_rate(bull_trades),
                'bear_market': calculate_win_rate(bear_trades),
                'sideways_market': calculate_win_rate(sideways_trades)
            }

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"시장 상황별 패턴 분석 오류: {e}")
            return {'bull_market': {}, 'bear_market': {}, 'sideways_market': {}}

    def _analyze_time_patterns_unified(self, trades: List[Dict]) -> Dict:
        """시간대별 거래 패턴 분석 (Unified)"""
        try:
            if len(trades) < 5:
                return {'morning': {}, 'afternoon': {}, 'evening': {}, 'night': {}}

            # 시간대별 분류
            morning_trades = []    # 06:00-12:00
            afternoon_trades = []  # 12:00-18:00
            evening_trades = []    # 18:00-24:00
            night_trades = []      # 00:00-06:00

            for trade in trades:
                # 거래 시간 추출 (가능한 경우)
                trade_time = trade.get('timestamp', datetime.now())
                if isinstance(trade_time, str):
                    try:
                        trade_time = datetime.fromisoformat(trade_time)
                    except:
                        trade_time = datetime.now()

                hour = trade_time.hour

                if 6 <= hour < 12:
                    morning_trades.append(trade)
                elif 12 <= hour < 18:
                    afternoon_trades.append(trade)
                elif 18 <= hour < 24:
                    evening_trades.append(trade)
                else:
                    night_trades.append(trade)

            # 각 시간대별 승률 계산
            def calculate_time_win_rate(trade_list):
                if not trade_list:
                    return {'win_rate': 50.0, 'count': 0, 'avg_profit': 0.0}

                wins = sum(1 for t in trade_list if t.get('pnl', 0) > 0)
                total = len(trade_list)
                win_rate = (wins / total) * 100.0
                avg_profit = sum(t.get('pnl', 0) for t in trade_list if t.get('pnl', 0) > 0) / max(wins, 1)

                return {
                    'win_rate': win_rate,
                    'count': total,
                    'avg_profit': avg_profit
                }

            return {
                'morning': calculate_time_win_rate(morning_trades),
                'afternoon': calculate_time_win_rate(afternoon_trades),
                'evening': calculate_time_win_rate(evening_trades),
                'night': calculate_time_win_rate(night_trades)
            }

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"시간대별 패턴 분석 오류: {e}")
            return {'morning': {}, 'afternoon': {}, 'evening': {}, 'night': {}}

    def _analyze_performance_trend_unified(self, trades: List[Dict]) -> Dict:
        """최근 성과 추세 분석 (Unified)"""
        try:
            if len(trades) < 10:
                return {'trend': 'STABLE', 'recent_performance': 50.0, 'improvement': False}

            # 최근 10회와 그 이전 10회 비교
            recent_10 = trades[-10:]
            previous_10 = trades[-20:-10] if len(trades) >= 20 else trades[:-10]

            # 각 그룹의 승률 계산
            def calculate_group_win_rate(group):
                if not group:
                    return 50.0
                wins = sum(1 for t in group if t.get('pnl', 0) > 0)
                return (wins / len(group)) * 100.0

            recent_win_rate = calculate_group_win_rate(recent_10)
            previous_win_rate = calculate_group_win_rate(previous_10)

            # 추세 판단
            improvement = recent_win_rate > previous_win_rate
            trend_diff = recent_win_rate - previous_win_rate

            if trend_diff > 10:
                trend = 'IMPROVING'
            elif trend_diff < -10:
                trend = 'DECLINING'
            else:
                trend = 'STABLE'

            return {
                'trend': trend,
                'recent_performance': recent_win_rate,
                'previous_performance': previous_win_rate,
                'improvement': improvement,
                'trend_strength': abs(trend_diff)
            }

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"성과 추세 분석 오류: {e}")
            return {'trend': 'STABLE', 'recent_performance': 50.0, 'improvement': False}

    def _get_dynamic_entry_thresholds_unified(self, exchange_name: str, symbol: str, market_conditions: Dict) -> Dict:
        """시장 상황 기반 동적 진입 임계값 계산 (Unified) - AI 학습 기반"""
        try:
            base_thresholds = {
                'max_loss_rate': 50.0,
                'min_trades_history': 0,
                'min_ai_confidence': 0.4,
            }

            # AI 학습 데이터 기반 임계값 계산
            learned_thresholds = self._get_ai_learned_thresholds_unified(exchange_name, symbol)
            if learned_thresholds:
                learned_thresholds['_source'] = 'learning_store'
                learned_thresholds['_base'] = dict(base_thresholds)
                return learned_thresholds

            # 시장 변동성 기반 조정 (AI가 학습할 기준점)
            volatility = market_conditions.get('volatility', 0.01)

            if volatility > 0.02:  # 높은 변동성 (AI 학습 기준점)
                return {
                    'max_loss_rate': base_thresholds['max_loss_rate'] * 0.8,  # AI가 학습할 조정 계수
                    # 완료 이력이 없는 신규 심볼을 완료 이력 조건으로 영구 차단하지 않는다.
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
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"❌ {exchange_name} {symbol} 동적 임계값 계산 오류: {e}")
            # 오류 시 기본값 반환
            return {
                'max_loss_rate': 50.0,
                'min_trades_history': 0,
                'min_ai_confidence': 0.4,
                '_source': 'fallback',
                '_base': {'max_loss_rate': 50.0, 'min_trades_history': 0, 'min_ai_confidence': 0.4},
            }

    def _get_ai_learned_thresholds_unified(self, exchange_name: str, symbol: str) -> Optional[Dict]:
        """AI 학습 데이터 기반 임계값 계산(저장된 learning_data 단일 소스)."""
        try:
            entries = self._get_recent_learning_entries_unified(exchange_name=exchange_name, symbol=symbol, limit=80)
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
                if recent_trade_count > 0:
                    try:
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
                # 학습 신호가 쌓여도 청산 이력이 전혀 없으면 그 이력을 새 진입의
                # 필수조건으로 만들지 않는다. 시장·신호·AI 신뢰도 가드는 그대로 유지한다.
                avg_win_rate = 0.0
                max_loss = 60.0
                min_trades = 0

            self.logger.info(
                f"[{exchange_name}] [{symbol}] 학습저장소 임계값 반영: n={len(entries)}, "
                f"closed_samples={max(observed_trade_counts or [0])}, "
                f"avg_win={avg_win_rate*100:.1f}%, avg_conf={avg_conf:.2f}"
            )
            return {
                'max_loss_rate': max_loss,
                'min_trades_history': min_trades,
                'min_ai_confidence': min_ai_conf,
            }
        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"❌ {exchange_name} {symbol} AI 학습 임계값 계산 오류: {e}")
            return None

    def _collect_symbol_performance_snapshot_unified(self, exchange_name: str, symbol: str) -> Dict[str, Any]:
        """학습데이터 저장 시점의 최근 성과 스냅샷을 수집한다."""
        try:
            rows = []
            if self.recorder and hasattr(self.recorder, 'get_recent_trades'):
                rows = self.recorder.get_recent_trades(symbol=symbol, exchange=exchange_name, days=30) or []
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

    def _get_recent_learning_entries_unified(self, exchange_name: str, symbol: str, limit: int = 80) -> List[Dict[str, Any]]:
        """저장된 learning_data에서 심볼 기준 최근 항목을 읽는다."""
        try:
            from .exchange_learning_manager import ExchangeLearningManager
            elm = self._learning_managers.get(exchange_name)
            if elm is None:
                elm = ExchangeLearningManager(exchange_name)
                self._learning_managers[exchange_name] = elm
            history = list(getattr(elm, 'learning_history', []) or [])
            target = str(symbol or '').upper()
            filtered = [
                h for h in history
                if isinstance(h, dict) and str(h.get('symbol', '')).upper() == target
            ]
            return filtered[-max(1, int(limit)):]
        except Exception:
            return []

    def _calculate_dynamic_tp_sl_unified(self, exchange_name: str, symbol: str, analysis: Dict) -> Dict:
        """시장 상황 기반 동적 TP/SL 계산 (Unified)"""
        try:
            # 기본 TP/SL 값
            base_tp = analysis.get('tp_percent', 0.0018)  # 기본값 0.18%
            base_sl = analysis.get('sl_percent', 0.002)   # 기본값 0.20%

            # 시장 변동성 계산
            volatility = analysis.get('market_volatility', 0.01)

            # 변동성 기반 조정
            if volatility > 0.02:  # 높은 변동성 (2% 이상)
                # 변동성이 높을 때: 더 넓은 범위
                tp_multiplier = 1.5  # TP 확대
                sl_multiplier = 1.3  # SL 확대
            elif volatility > 0.01:  # 중간 변동성 (1-2%)
                # 중간 변동성: 약간 확대
                tp_multiplier = 1.2
                sl_multiplier = 1.1
            else:  # 낮은 변동성 (1% 미만)
                # 변동성이 낮을 때: 더 좁은 범위
                tp_multiplier = 0.8  # TP 축소
                sl_multiplier = 0.9  # SL 축소

            # 최근 거래 패턴 기반 추가 조정
            pattern_adjustment = self._get_pattern_based_tp_sl_adjustment_unified(exchange_name, symbol)
            tp_multiplier *= pattern_adjustment['tp_multiplier']
            sl_multiplier *= pattern_adjustment['sl_multiplier']

            # 최종 TP/SL 계산
            final_tp = base_tp * tp_multiplier
            final_sl = base_sl * sl_multiplier

            # 안전 범위 제한
            final_tp = max(0.0005, min(final_tp, 0.01))  # 0.05% ~ 1.0%
            final_sl = max(0.0005, min(final_sl, 0.01))  # 0.05% ~ 1.0%

            rr_guard = self._enforce_rr_floor(
                final_tp,
                final_sl,
                min_tp=0.0005,
                max_tp=0.01,
                min_sl=0.0005,
                max_sl=0.01,
                exchange_name=exchange_name,
                symbol=symbol,
                market_volatility=volatility,
                context=f"{exchange_name}:{symbol}:dynamic_tp_sl",
            )
            final_tp = float(rr_guard['tp'])
            final_sl = float(rr_guard['sl'])

            if rr_guard.get('enabled') and rr_guard.get('applied') and hasattr(self, 'logger') and self.logger:
                self.logger.info(
                    f"{exchange_name} {symbol} RR 가드레일 적용: {rr_guard['rr_before']:.3f} -> {rr_guard['rr_after']:.3f} "
                    f"(min={rr_guard['min_rr_ratio']:.2f}, strict={rr_guard['strict']})"
                )

            return {
                'tp': final_tp,
                'sl': final_sl,
                'volatility': volatility,
                'tp_multiplier': tp_multiplier,
                'sl_multiplier': sl_multiplier,
                'rr_before': rr_guard['rr_before'],
                'rr_after': rr_guard['rr_after'],
                'rr_guardrail_enabled': rr_guard['enabled'],
                'rr_guardrail_passed': rr_guard['passed'] or (not rr_guard['strict']),
                'rr_guardrail_applied': rr_guard['applied'],
                'rr_min': rr_guard['min_rr_ratio'],
                'rr_configured': rr_guard.get('configured_min_rr_ratio', rr_guard['min_rr_ratio']),
                'rr_adaptive_enabled': rr_guard.get('adaptive_enabled', False),
                'rr_adaptive_reason': rr_guard.get('adaptive_reason', 'n/a'),
            }

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"동적 TP/SL 계산 오류: {e}")
            # 오류 시 기본값 반환
            return {
                'tp': analysis.get('tp_percent', 0.0018),
                'sl': analysis.get('sl_percent', 0.002),
                'volatility': 0.01,
                'tp_multiplier': 1.0,
                'sl_multiplier': 1.0
            }

    def _get_pattern_based_tp_sl_adjustment_unified(self, exchange_name: str, symbol: str) -> Dict:
        """최근 거래 패턴 기반 TP/SL 조정 (Unified)"""
        try:
            # 최근 20회 거래 분석
            coin = symbol.replace('USDT', '')
            recent_trades = []

            if hasattr(self, 'recorder') and self.recorder:
                try:
                    method = getattr(self.recorder, 'get_recent_trades', None)
                    if callable(method):
                        rt = method(coin=coin, exchange=exchange_name, days=30)
                        recent_trades = rt if isinstance(rt, list) else []
                    else:
                        symbol_full = f"{coin}USDT"
                        rt = self.recorder.get_trade_history(symbol=symbol_full, days=30)
                        recent_trades = rt if isinstance(rt, list) else []
                except Exception:
                    recent_trades = []

            if len(recent_trades) < 5:
                return {'tp_multiplier': 1.0, 'sl_multiplier': 1.0}

            # 승률 계산
            wins = sum(1 for t in recent_trades if t.get('pnl', 0) > 0)
            win_rate = wins / len(recent_trades)

            # 평균 수익률과 손실률 계산
            profits = [t.get('pnl', 0) for t in recent_trades if t.get('pnl', 0) > 0]
            losses = [abs(t.get('pnl', 0)) for t in recent_trades if t.get('pnl', 0) < 0]

            avg_profit = sum(profits) / len(profits) if profits else 0.0
            avg_loss = sum(losses) / len(losses) if losses else 0.0

            # 패턴 기반 조정
            if win_rate > 0.7:  # 높은 승률
                # 수익 목표는 약간 상향, 손실 한계는 약간 하향
                tp_multiplier = 1.1
                sl_multiplier = 0.9
            elif win_rate < 0.3:  # 낮은 승률
                # 수익 목표는 하향, 손실 한계는 상향
                tp_multiplier = 0.8
                sl_multiplier = 1.2
            else:  # 중간 승률
                tp_multiplier = 1.0
                sl_multiplier = 1.0

            # 평균 수익률/손실률 기반 추가 조정
            if avg_profit > 0.5:  # 평균 수익률이 높으면
                tp_multiplier *= 1.1  # TP 약간 상향
            elif avg_profit < 0.2:  # 평균 수익률이 낮으면
                tp_multiplier *= 0.9  # TP 약간 하향

            if avg_loss > 0.3:  # 평균 손실률이 높으면
                sl_multiplier *= 1.1  # SL 약간 상향
            elif avg_loss < 0.1:  # 평균 손실률이 낮으면
                sl_multiplier *= 0.9  # SL 약간 하향

            return {
                'tp_multiplier': tp_multiplier,
                'sl_multiplier': sl_multiplier,
                'win_rate': win_rate,
                'avg_profit': avg_profit,
                'avg_loss': avg_loss
            }

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"패턴 기반 TP/SL 조정 오류: {e}")
            return {'tp_multiplier': 1.0, 'sl_multiplier': 1.0}

    def _get_enhanced_ai_exit_decision_unified(self, exchange_name: str, position: Position, current_price: float, pnl_data: Dict) -> Dict:
        """향상된 AI 청산 결정 (Unified)"""
        try:
            if not self.ai_manager or not self.ai_manager.enabled():
                return {'should_exit': False, 'reason': 'AI 비활성화', 'confidence': 0.0}

            # 현재 시장 상황 분석
            market_data = self._get_current_market_context_unified(exchange_name, position.symbol)

            # 포지션 상태 분석
            position_analysis = self._analyze_position_status_unified(position, pnl_data)

            # AI 청산 결정 요청
            exit_decision = getattr(self.ai_manager, 'get_exit_decision', lambda **kwargs: {'should_exit': False, 'reason': 'AI 분석 비활성화'})(
                symbol=position.symbol,
                position_data={
                    'side': position.side.value,
                    'entry_price': position.entry_price,
                    'current_price': current_price,
                    'quantity': position.quantity,
                    'leverage': position.leverage,
                    'unrealized_pnl_percent': pnl_data.get('current_pnl_percent', 0.0),
                    'holding_time_minutes': (datetime.now() - position.entry_time).total_seconds() / 60
                },
                market_context=market_data,
                position_analysis=position_analysis
            )

            return exit_decision

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"AI 청산 결정 오류: {e}")
            return {'should_exit': False, 'reason': f'AI 오류: {e}', 'confidence': 0.0}

    def _calculate_dynamic_thresholds_unified(self, exchange_name: str, symbol: str) -> Dict:
        """시장 변동성 기반 동적 임계값 계산 (Unified)"""
        try:
            # 시장 변동성 계산
            volatility = self._calculate_market_volatility_unified(exchange_name, symbol)

            # 설정 정본은 비율(0.0018=0.18%), 아래 계산은 퍼센트 포인트다.
            configured_tp = float((self.settings or {}).get('default_tp', 0.0018) or 0.0018)
            configured_sl = float((self.settings or {}).get('default_sl', 0.0020) or 0.0020)
            base_tp = configured_tp * 100.0
            base_sl = configured_sl * 100.0

            # 변동성 기반 조정
            if volatility > 0.02:  # 높은 변동성 (2% 이상)
                tp_multiplier = 1.5  # 더 넓은 수익 목표
                sl_multiplier = 1.2  # 더 넓은 손실 한계
            elif volatility > 0.01:  # 중간 변동성 (1-2%)
                tp_multiplier = 1.2
                sl_multiplier = 1.1
            else:  # 낮은 변동성 (1% 미만)
                tp_multiplier = 0.8  # 더 좁은 수익 목표
                sl_multiplier = 0.9  # 더 좁은 손실 한계

            # 최근 거래 패턴 기반 추가 조정
            pattern_adjustment = self._get_pattern_based_adjustment_unified(exchange_name, symbol)
            tp_multiplier *= pattern_adjustment['tp_multiplier']
            sl_multiplier *= pattern_adjustment['sl_multiplier']

            # 최종 임계값 계산
            profit_threshold = base_tp * tp_multiplier
            loss_threshold = -base_sl * sl_multiplier

            # 안전 범위 제한
            profit_threshold = max(0.05, min(profit_threshold, 1.0))  # 0.05% ~ 1.0%
            loss_threshold = max(-2.0, min(loss_threshold, -0.05))    # -2.0% ~ -0.05%

            rr_guard = self._enforce_rr_floor(
                profit_threshold,
                abs(loss_threshold),
                min_tp=0.05,
                max_tp=1.0,
                min_sl=0.05,
                max_sl=2.0,
                exchange_name=exchange_name,
                symbol=symbol,
                market_volatility=volatility,
                context=f"{exchange_name}:{symbol}:dynamic_exit_threshold",
            )
            profit_threshold = float(rr_guard['tp'])
            loss_threshold = -float(rr_guard['sl'])

            return {
                'profit_threshold': profit_threshold,
                'loss_threshold': loss_threshold,
                'volatility': volatility,
                'tp_multiplier': tp_multiplier,
                'sl_multiplier': sl_multiplier,
                'rr_before': rr_guard['rr_before'],
                'rr_after': rr_guard['rr_after'],
                'rr_guardrail_applied': rr_guard['applied'],
                'rr_min': rr_guard['min_rr_ratio'],
                'rr_configured': rr_guard.get('configured_min_rr_ratio', rr_guard['min_rr_ratio']),
                'rr_adaptive_enabled': rr_guard.get('adaptive_enabled', False),
                'rr_adaptive_reason': rr_guard.get('adaptive_reason', 'n/a'),
            }

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"동적 임계값 계산 오류: {e}")
            # 오류 시 기본값 반환
            return {
                'profit_threshold': 0.18,
                'loss_threshold': -0.20,
                'volatility': 0.01,
                'tp_multiplier': 1.0,
                'sl_multiplier': 1.0
            }

    def _calculate_market_volatility_unified(self, exchange_name: str, symbol: str) -> float:
        """시장 변동성 계산 (Unified)"""
        try:
            # 최근 24시간 가격 데이터로 변동성 계산
            klines = []
            try:
                if hasattr(self, 'exchange_manager') and self.exchange_manager:
                    klines = self.exchange_manager.get_klines(symbol, interval='1h', limit=24, exchange_name=exchange_name)
            except Exception:
                pass

            if not klines or len(klines) < 24:
                return 0.01  # 기본값

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
            return 0.01  # 기본값

    def _get_pattern_based_adjustment_unified(self, exchange_name: str, symbol: str) -> Dict:
        """최근 거래 패턴 기반 임계값 조정 (Unified)"""
        try:
            # 최근 20회 거래 분석
            coin = symbol.replace('USDT', '')
            recent_trades = []

            if hasattr(self, 'recorder') and self.recorder:
                try:
                    method = getattr(self.recorder, 'get_recent_trades', None)
                    if callable(method):
                        rt = method(coin=coin, exchange=exchange_name, days=30)
                        recent_trades = rt if isinstance(rt, list) else []
                    else:
                        symbol_full = f"{coin}USDT"
                        rt = self.recorder.get_trade_history(symbol=symbol_full, days=30)
                        recent_trades = rt if isinstance(rt, list) else []
                except Exception:
                    recent_trades = []

            if len(recent_trades) < 5:
                return {'tp_multiplier': 1.0, 'sl_multiplier': 1.0}

            # 승률 계산
            wins = sum(1 for t in recent_trades if t.get('pnl', 0) > 0)
            win_rate = wins / len(recent_trades)

            # 평균 수익률 계산
            avg_profit = sum(t.get('pnl', 0) for t in recent_trades if t.get('pnl', 0) > 0)
            avg_profit = avg_profit / max(wins, 1)

            # 패턴 기반 조정
            if win_rate > 0.7:  # 높은 승률
                tp_multiplier = 1.1  # 수익 목표 약간 상향
                sl_multiplier = 0.9  # 손실 한계 약간 하향
            elif win_rate < 0.3:  # 낮은 승률
                tp_multiplier = 0.8  # 수익 목표 하향
                sl_multiplier = 1.2  # 손실 한계 상향
            else:  # 중간 승률
                tp_multiplier = 1.0
                sl_multiplier = 1.0

            return {
                'tp_multiplier': tp_multiplier,
                'sl_multiplier': sl_multiplier,
                'win_rate': win_rate,
                'avg_profit': avg_profit
            }

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"패턴 기반 조정 오류: {e}")
            return {'tp_multiplier': 1.0, 'sl_multiplier': 1.0}

    def _get_current_market_context_unified(self, exchange_name: str, symbol: str) -> Dict:
        """현재 시장 상황 분석 (Unified)"""
        try:
            # 기술적 지표 계산
            klines = []
            try:
                if hasattr(self, 'exchange_manager') and self.exchange_manager:
                    klines = self.exchange_manager.get_klines(symbol, interval='15m', limit=100, exchange_name=exchange_name)
            except Exception:
                pass

            if not klines or len(klines) < 50:
                return {'rsi': 50, 'trend': 'SIDEWAYS', 'volume': 'NORMAL'}

            # RSI 계산 (간단한 구현)
            from typing import cast, Dict, Any
            prices = [float(cast(Dict[str, Any], k)['close']) for k in klines]
            volumes = [float(cast(Dict[str, Any], k)['volume']) for k in klines]

            # 간단한 RSI 계산
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

            # 트렌드 분석 (간단한 구현)
            recent_prices = prices[-20:]
            if len(recent_prices) >= 2:
                trend_slope = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
                if trend_slope > 0.02:
                    trend = 'UPTREND'
                elif trend_slope < -0.02:
                    trend = 'DOWNTREND'
                else:
                    trend = 'SIDEWAYS'
            else:
                trend = 'SIDEWAYS'

            # 거래량 분석
            avg_volume = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else volumes[-1] if volumes else 1
            current_volume = volumes[-1] if volumes else 1
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

            volume_status = 'HIGH' if volume_ratio > 1.5 else 'LOW' if volume_ratio < 0.5 else 'NORMAL'

            return {
                'rsi': float(rsi),
                'trend': trend,
                'volume': volume_status,
                'volume_ratio': float(volume_ratio),
                'price_change_1h': float((prices[-1] - prices[-4]) / prices[-4] * 100) if len(prices) >= 4 else 0.0
            }

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"시장 상황 분석 오류: {e}")
            return {'rsi': 50, 'trend': 'SIDEWAYS', 'volume': 'NORMAL'}

    def _analyze_position_status_unified(self, position: Position, pnl_data: Dict) -> Dict:
        """포지션 상태 분석 (Unified)"""
        try:
            # 보유 시간
            holding_time_minutes = (datetime.now() - position.entry_time).total_seconds() / 60

            # 수익률 분석
            pnl_percent = pnl_data.get('current_pnl_percent', 0.0)

            # 포지션 상태 분류
            if pnl_percent > 0.5:
                status = 'STRONG_PROFIT'
            elif pnl_percent > 0.1:
                status = 'PROFIT'
            elif pnl_percent > -0.1:
                status = 'NEUTRAL'
            elif pnl_percent > -0.5:
                status = 'LOSS'
            else:
                status = 'STRONG_LOSS'

            return {
                'status': status,
                'pnl_percent': pnl_percent,
                'holding_time_minutes': holding_time_minutes,
                'leverage': position.leverage,
                'side': position.side.value
            }

        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"포지션 상태 분석 오류: {e}")
            return {'status': 'UNKNOWN', 'pnl_percent': 0.0, 'holding_time_minutes': 0}

    def _calculate_spot_position_size(self, exchange_name: str, symbol: str, analysis: Dict, optimized_params: Dict) -> float:
        """현물 거래소용 포지션 크기 계산 (실제 매수량)"""
        try:
            # 🔥 현물 거래소는 잔고 기반으로 매수량 계산
            exchange_client = self.get_exchange_client(exchange_name)
            if not exchange_client:
                return 0.0

            # 잔고 조회 (원화/코인 잔고)
            balance = exchange_client.get_balance()
            if exchange_name == 'upbit':
                available_krw = balance.get('KRW', 0.0)
            elif exchange_name == 'bithumb':
                available_krw = balance.get('KRW', 0.0)
            else:
                available_krw = 0.0

            signal = str(analysis.get('signal', 'HOLD') or 'HOLD').upper()

            # 현물 SHORT는 공매도 진입이 아니라 보유 코인 매도로 처리
            if signal == 'SHORT':
                base_asset = ''
                symbol_txt = str(symbol or '').upper()
                if '-' in symbol_txt:
                    parts = symbol_txt.split('-')
                    if len(parts) == 2:
                        base_asset = parts[1] if parts[0] in ('KRW', 'USDT', 'USD') else parts[0]
                elif '/' in symbol_txt:
                    parts = symbol_txt.split('/')
                    if len(parts) == 2:
                        base_asset = parts[0]
                else:
                    for quote in ('KRW', 'USDT', 'USDC', 'BTC', 'ETH'):
                        if symbol_txt.endswith(quote) and len(symbol_txt) > len(quote):
                            base_asset = symbol_txt[:-len(quote)]
                            break

                available_coin = float(balance.get(base_asset, 0.0) or 0.0) if base_asset else 0.0
                if available_coin <= 0.0:
                    self.logger.info(f"{exchange_name} 현물 SHORT 스킵: {base_asset or symbol} 보유 수량 없음")
                    return 0.0

                confidence = float(analysis.get('confidence', 0.5) or 0.5)
                sell_ratio = 0.25 + (confidence * 0.75)  # 25%~100% 분할 매도
                sell_quantity = max(0.0, available_coin * min(1.0, sell_ratio))
                self.logger.info(
                    f"{exchange_name} 현물 매도 계산: 자산={base_asset}, 보유={available_coin:.8f}, 비율={sell_ratio:.1%}, 수량={sell_quantity:.8f}"
                )
                return sell_quantity

            if available_krw <= 0:
                self.logger.warning(f"{exchange_name} 원화 잔고 부족: {available_krw}")
                return 0.0

            # 🔥 현물 거래는 전체 잔고의 일정 비율로 매수
            # AI 신뢰도에 따른 비율 조정
            confidence = analysis.get('confidence', 0.5)

            # 신뢰도에 따른 비율 조정 (0.05 ~ 0.2)
            confidence_ratio = 0.05 + (confidence * 0.15)

            # 매수 금액 계산
            buy_amount_krw = available_krw * confidence_ratio

            # 현재가 조회
            get_price_method = getattr(exchange_client, 'get_current_price', None)
            if not get_price_method:
                self.logger.warning(f"{exchange_name} get_current_price 메서드 없음 - 기본값 반환")
                return 0.0
            current_price = get_price_method(symbol)
            if current_price <= 0:
                return 0.0

            # 매수 수량 계산
            buy_quantity = buy_amount_krw / current_price

            self.logger.info(f"{exchange_name} 현물 매수 계산: 잔고={available_krw:.0f}원, 비율={confidence_ratio:.1%}, 금액={buy_amount_krw:.0f}원, 수량={buy_quantity:.6f}")

            return buy_quantity

        except Exception as e:
            self.logger.error(f"현물 포지션 크기 계산 중 오류: {e}")
            return 0.0
