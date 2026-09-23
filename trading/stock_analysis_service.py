#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
주식/ETF 분석 서비스 모듈
=====================================
역할:
  - 어댑터(데이터 수집)와 대시보드/AI(표시·판단) 사이 분석 계층
  - 종목·ETF 점수화, 리스크 평가, 시장 상태, AI 컨텍스트 생성을 담당
  - 특정 브로커 어댑터에 종속되지 않음 (StockExchange 인터페이스만 사용)

사용 예:
    from trading.stock_analysis_service import StockAnalysisService
    svc = StockAnalysisService(adapter)
    summary = svc.get_portfolio_summary()
    context = svc.build_ai_context()
"""

from __future__ import annotations
from trading.remote_entry_pause import entry_submission

import logging
import math
import hashlib
import threading
import time as pytime
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Any, Dict, List, Optional
from .market_data_utils import optional_market_number
from log_system.log_adapter import log_event
from api.kpi_client import emit_kpi_event
from api.position_kpi import (
    as_utc,
    emit_position_closed,
    emit_position_opened,
    emit_position_reduced,
    make_position_id,
    utc_now,
)
from trading.stock_risk_governance import evaluate_stock_risk_governance
from trading.execution_optimizer import ExecutionOptimizer
from trading.ops_automation import OpsAutomationEngine
from trading.portfolio_orchestrator import PortfolioOrchestrator
from trading.profitability_validation import ProfitabilityValidator
from trading.position_sizing_policy import (
    ACCOUNT_RISK,
    LEGACY_VENUE,
    calculate_position_sizing,
    derive_market_risk_multiplier,
    effective_position_limit,
    normalize_position_sizing_policy,
)
from trading.strategy_engine import StrategyEngine
from trading.execution_mode import ExecutionMode
from trading.trade_candidate import apply_trade_candidate, evaluate_trade_candidate
from trading.exit_policy import (
    build_exit_policy,
    format_exit_policy,
    record_insurance_submission,
)
from trading.opportunity_coordinator import (
    get_opportunity_coordinator,
    normalize_multi_venue_policy,
)
from trading.stock_exit_policy import resolve_stock_exit_thresholds
from trading.stock_paper_valuation import (
    calculate_stock_paper_valuation,
    normalize_stock_paper_cost_policy,
)
from trading.stock_paper_position_store import (
    load_stock_paper_positions,
    save_stock_paper_positions,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 시장 상태 유틸
# ---------------------------------------------------------------------------

def get_market_session() -> str:
    """현재 한국 시장 세션 반환.

    Returns:
        'pre'     : 장전 (08:00~09:00)
        'open'    : 장중 (09:00~15:30)
        'post'    : 장후 (15:30~18:00)
        'closed'  : 장외
    """
    now = datetime.now().time()
    if dtime(8, 0) <= now < dtime(9, 0):
        return 'pre'
    if dtime(9, 0) <= now <= dtime(15, 30):
        return 'open'
    if dtime(15, 30) < now <= dtime(18, 0):
        return 'post'
    return 'closed'


# ---------------------------------------------------------------------------
# ETF 메타데이터 분석
# ---------------------------------------------------------------------------

class ETFMetrics:
    """ETF 단일 종목 지표 컨테이너 및 평가 헬퍼."""

    # 임계값 (업계 일반 기준)
    NAV_GAP_WARN = 0.5       # NAV 괴리율 경고 (%)
    NAV_GAP_ALERT = 1.0      # NAV 괴리율 위험 (%)
    TRACKING_ERROR_WARN = 1.0   # 추적오차 경고 (%)
    TRACKING_ERROR_ALERT = 3.0  # 추적오차 위험 (%)
    LOW_TRADE_VALUE = 1_000_000  # 거래대금 낮음 기준 (원)

    def __init__(
        self,
        code: str,
        name: str,
        nav: float = 0.0,
        current_price: float = 0.0,
        tracking_error: Optional[float] = None,
        trade_value: float = 0.0,
        base_index: str = '',
        expense_ratio: Optional[float] = None,
    ):
        self.code = code
        self.name = name
        self.nav = nav
        self.current_price = current_price
        self.tracking_error = tracking_error  # None 허용
        self.trade_value = trade_value
        self.base_index = base_index
        self.expense_ratio = expense_ratio

    @property
    def nav_gap(self) -> Optional[float]:
        """NAV 괴리율 (%).  NAV=0이면 None."""
        if not self.nav or not self.current_price:
            return None
        return (self.current_price - self.nav) / self.nav * 100

    def risk_level(self) -> str:
        """'ok' | 'warn' | 'alert'"""
        if (
            (self.nav_gap is not None and abs(self.nav_gap) >= self.NAV_GAP_ALERT)
            or (self.tracking_error is not None and self.tracking_error >= self.TRACKING_ERROR_ALERT)
        ):
            return 'alert'
        if (
            (self.nav_gap is not None and abs(self.nav_gap) >= self.NAV_GAP_WARN)
            or (self.tracking_error is not None and self.tracking_error >= self.TRACKING_ERROR_WARN)
            or (self.trade_value > 0 and self.trade_value < self.LOW_TRADE_VALUE)
        ):
            return 'warn'
        return 'ok'

    def summary(self) -> str:
        """AI 컨텍스트용 한 줄 요약."""
        parts = [f"{self.name}({self.code})"]
        if self.nav_gap is not None:
            parts.append(f"NAV괴리 {self.nav_gap:+.2f}%")
        if self.tracking_error is not None:
            parts.append(f"추적오차 {self.tracking_error:.2f}%")
        if self.trade_value:
            tv = self.trade_value
            if tv >= 1_000_000_000:
                parts.append(f"거래대금 {tv/1_000_000_000:.1f}십억")
            elif tv >= 1_000_000:
                parts.append(f"거래대금 {tv/1_000_000:.0f}백만")
            else:
                parts.append(f"거래대금 {tv:,.0f}원")
        risk = self.risk_level()
        if risk != 'ok':
            parts.append(f"[{risk.upper()}]")
        return ' | '.join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'code': self.code,
            'name': self.name,
            'nav': self.nav,
            'current_price': self.current_price,
            'nav_gap': self.nav_gap,
            'tracking_error': self.tracking_error,
            'trade_value': self.trade_value,
            'base_index': self.base_index,
            'expense_ratio': self.expense_ratio,
            'risk_level': self.risk_level(),
        }


# ---------------------------------------------------------------------------
# 종목 점수화
# ---------------------------------------------------------------------------

def score_stock(
    current_price: float,
    prev_close: float,
    volume: float,
    avg_volume: float = 0.0,
    pnl_rate: float = 0.0,
    prices: Optional[List[float]] = None,
    foreign_net_buy: float = 0.0,
    institutional_net_buy: float = 0.0,
) -> Dict[str, Any]:
    """
    규칙 기반 종목 점수 (0~100).

    항목별 배점:
      - 기본 점수      : 20
      - 수익률 기여도  : ±30 (손익 방향 반영)
      - 가격 모멘텀    : ±20 (전일 대비 등락, 기존 ±30에서 조정)
      - 거래량 활성도  : +10 (평균 대비, 기존 +20에서 조정)
      - MA5/MA20 크로스: ±15 (골든크로스/데드크로스/정배열/역배열)
      - RSI(14)        : ±10 (과매도 반등/과매수 조정)
      - 외국인+기관수급: ±10 (순매수/순매도 규모)
    """
    score = 20.0

    # 수익률 기여
    pnl_score = min(max(pnl_rate / 10 * 30, -30), 30)
    score += pnl_score

    # 가격 모멘텀 (±20으로 조정)
    momentum_val = 0.0
    if prev_close and prev_close > 0:
        change_rate = (current_price - prev_close) / prev_close * 100
        momentum_val = change_rate
        momentum_score = min(max(change_rate / 3 * 20, -20), 20)
        score += momentum_score

    # 거래량 활성도 (+10으로 조정)
    if avg_volume and avg_volume > 0 and volume > 0:
        ratio = volume / avg_volume
        vol_score = min(10, ratio * 5)
        score += vol_score
    elif volume > 0:
        score += 3  # 기준 없어도 거래량 존재 시 소폭 가산

    # ── MA5/MA20 크로스 점수 (최대 ±15) ──
    ma_signal = 'none'
    if prices and len(prices) >= 20:
        ma5 = sum(prices[-5:]) / 5
        ma20 = sum(prices[-20:]) / 20
        if len(prices) >= 21:
            ma_prev5 = sum(prices[-6:-1]) / 5
            ma_prev20 = sum(prices[-21:-1]) / 20
            if ma_prev5 <= ma_prev20 and ma5 > ma20:
                score += 15
                ma_signal = 'golden_cross'
            elif ma_prev5 >= ma_prev20 and ma5 < ma20:
                score -= 15
                ma_signal = 'dead_cross'
            elif ma5 > ma20:
                score += 5
                ma_signal = 'bullish_alignment'
            else:
                score -= 5
                ma_signal = 'bearish_alignment'
        elif ma5 > ma20:
            score += 5
            ma_signal = 'bullish_alignment'
        else:
            score -= 5
            ma_signal = 'bearish_alignment'

    # ── RSI(14) 점수 (최대 ±10) ──
    rsi_val: Optional[float] = None
    if prices and len(prices) >= 15:
        gains: List[float] = []
        losses: List[float] = []
        for i in range(1, min(15, len(prices))):
            d = prices[-i] - prices[-i - 1]
            gains.append(max(d, 0.0))
            losses.append(max(-d, 0.0))
        ag = sum(gains) / len(gains) if gains else 0.0
        al = sum(losses) / len(losses) if losses else 0.0
        if al == 0:
            rsi_val = 100.0
        else:
            rsi_val = 100.0 - (100.0 / (1.0 + ag / al))
        if rsi_val <= 30:
            score += 10   # 과매도 반등 기회
        elif rsi_val >= 70:
            score -= 10   # 과매수 위험

    # ── 외국인+기관 수급 (최대 ±10) ──
    net_buy = foreign_net_buy + institutional_net_buy
    if net_buy > 1_000_000_000:      # 10억 이상 순매수
        score += 10
    elif net_buy > 100_000_000:      # 1억 이상
        score += 5
    elif net_buy < -1_000_000_000:   # 10억 이상 순매도
        score -= 10
    elif net_buy < -100_000_000:
        score -= 5

    return {
        'score': round(min(max(score, 0), 100), 1),
        'pnl_rate': pnl_rate,
        'momentum': round(momentum_val, 2),
        'ma_signal': ma_signal,
        'rsi': round(rsi_val, 1) if rsi_val is not None else None,
        'net_buy': net_buy,
    }


def score_etf(
    current_price: float,
    nav: float,
    tracking_error: Optional[float],
    trade_value: float,
    expense_ratio: Optional[float] = None,
) -> Dict[str, Any]:
    """
    ETF 전용 점수 (0~100).

    항목별 배점:
      - 기본 점수            : 50
      - NAV 괴리 페널티      : 최대 -25
      - 추적오차 페널티      : 최대 -20
      - 거래대금 유동성 보너스: 최대 +10
      - 운용보수 페널티       : 최대 -10
    """
    score = 50.0

    nav_gap = 0.0
    if nav and nav > 0 and current_price > 0:
        nav_gap = abs((current_price - nav) / nav * 100)
        score -= min(25.0, nav_gap * 12.5)

    if tracking_error is not None:
        score -= min(20.0, max(0.0, float(tracking_error)) * 8.0)

    if trade_value > 0:
        # 1천만원 이상이면 유동성 보너스 상한
        liquidity_boost = min(10.0, trade_value / 10_000_000 * 10.0)
        score += liquidity_boost

    if expense_ratio is not None:
        # 운용보수 1.0% 이상 구간은 강한 감점
        score -= min(10.0, max(0.0, float(expense_ratio)) * 1000.0)

    return {
        'score': round(min(max(score, 0), 100), 1),
        'nav_gap': round(nav_gap, 3),
        'tracking_error': None if tracking_error is None else float(tracking_error),
        'trade_value': float(trade_value or 0),
        'expense_ratio': None if expense_ratio is None else float(expense_ratio),
    }


# ---------------------------------------------------------------------------
# 시장 레짐 감지 (KOSPI/KOSDAQ 기반)
# ---------------------------------------------------------------------------

def detect_market_regime(adapter: Any) -> str:
    """KOSPI/KOSDAQ 지수 데이터로 현재 장세를 분류한다.

    Returns:
        'bull'    : 상승장 (KOSPI 5일 수익률 >= +1.5%)
        'bear'    : 하락장 (KOSPI 5일 수익률 <= -1.5%)
        'volatile': 고변동 (일간 등락폭 >= 2.0% 평균)
        'range'   : 횡보장 (나머지). 5일 지수 이력을 제공하지 않는
                    증권사는 당일 KOSPI 등락률을 명시적 fallback으로 사용한다.
    """
    try:
        # 설명과 구현을 일치시킨다. 지원 어댑터에서는 최근 6개 종가로
        # 5거래일 수익률과 일간 절대 변동 평균을 먼저 계산한다.
        history = []
        for method_name in ('get_index_history', 'get_index_price_history'):
            getter = getattr(adapter, method_name, None)
            if not callable(getter):
                continue
            try:
                history = getter('KOSPI', count=6) or []
            except TypeError:
                try:
                    history = getter('KOSPI', 6) or []
                except Exception:
                    history = []
            except Exception:
                history = []
            if history:
                break
        ordered_history = list(history or [])
        if ordered_history and all(isinstance(row, dict) for row in ordered_history):
            dated_rows = []
            for index, row in enumerate(ordered_history):
                date_key = str(
                    row.get('date')
                    or row.get('trading_date')
                    or row.get('business_date')
                    or row.get('timestamp')
                    or ''
                ).strip()
                dated_rows.append((date_key, index, row))
            if all(item[0] for item in dated_rows):
                ordered_history = [item[2] for item in sorted(dated_rows, key=lambda item: item[0])]
                # Repeated dates are not distinct trading sessions. Do not
                # label duplicate/conflicting rows as a five-session return.
                if len({item[0] for item in dated_rows}) != len(dated_rows):
                    ordered_history = []
            elif any(item[0] for item in dated_rows):
                ordered_history = []  # Partially dated history has no reliable order.

        closes = []
        for row in ordered_history[-6:]:
            value = row.get('close') if isinstance(row, dict) else row
            close = optional_market_number(value)
            if close is None or close <= 0:
                # Skipping a missing close would silently extend the window.
                closes = []
                break
            closes.append(close)
        if len(closes) >= 6:
            adapter._regime_data_reason = 'kospi_history'
            recent = closes[-6:]
            five_day_return = (recent[-1] - recent[0]) / recent[0] * 100.0
            daily_moves = [
                abs((recent[index] - recent[index - 1]) / recent[index - 1] * 100.0)
                for index in range(1, len(recent))
                if recent[index - 1] > 0
            ]
            average_daily_move = sum(daily_moves) / len(daily_moves) if daily_moves else 0.0
            if five_day_return >= 1.5:
                return 'bull'
            if five_day_return <= -1.5:
                return 'bear'
            if average_daily_move >= 2.0:
                return 'volatile'
            return 'range'

        index_symbols = []
        if hasattr(adapter, 'get_index_price'):
            for idx in ('KOSPI', '코스피', '001'):
                try:
                    idx_data = adapter.get_index_price(idx) or {}
                    if (idx_data and idx_data.get('status') not in {'error', 'unavailable'}
                            and optional_market_number(idx_data.get('change_rate'), idx_data.get('change_pct')) is not None):
                        index_symbols.append(idx_data)
                        break
                except Exception:
                    continue

        if not index_symbols:
            # 어댑터에서 지수를 못 가져오면 POSCO(005490)·삼성전자(005930) 대표 종목으로 추정
            proxy_symbols = ['005930', '005490']
            changes: list[float] = []
            for sym in proxy_symbols:
                try:
                    if hasattr(adapter, 'get_realtime_price'):
                        p = adapter.get_realtime_price(sym) or {}
                        if not p or p.get('status') in {'error', 'unavailable'} or p.get('change_rate') is None:
                            continue
                        cr = optional_market_number(p['change_rate'])
                        if cr is None:
                            continue
                        changes.append(cr)
                except Exception:
                    continue
            if not changes:
                adapter._regime_data_reason = 'index_and_proxy_quotes_unavailable'
                return 'unknown'
            adapter._regime_data_reason = 'proxy_stock_quotes'
            avg_change = sum(changes) / len(changes)
            if avg_change >= 1.5:
                return 'bull'
            if avg_change <= -1.5:
                return 'bear'
            if abs(avg_change) >= 1.0:
                return 'volatile'
            return 'range'

        # 지수 직접 사용
        adapter._regime_data_reason = 'kospi_quote'
        idx = index_symbols[0]
        raw_change = optional_market_number(idx.get('change_rate'), idx.get('change_pct'))
        if raw_change is None:
            return 'unknown'
        change_rate = float(raw_change)
        if not math.isfinite(change_rate):
            return 'unknown'
        if change_rate >= 1.5:
            return 'bull'
        if change_rate <= -1.5:
            return 'bear'
        if abs(change_rate) >= 1.0:
            return 'volatile'
        return 'range'
    except Exception as exc:
        adapter._regime_data_reason = 'index_observation_failed:' + type(exc).__name__
        return 'unknown'


def adjust_thresholds_by_regime(
    regime: str,
    base_buy: float = 70.0,
    base_sell: float = 30.0,
) -> tuple[float, float]:
    """레짐에 따라 매수/매도 임계값을 조정한다.

    bear  : 매수 조건 강화 (더 높은 점수 필요), 매도 조건 완화
    bull  : 매수 조건 완화, 매도 조건 강화
    volatile: 양방향 강화 (진입 억제)
    range : 기본값 유지
    """
    adjustments = {
        'bull':     (-5.0, +5.0),   # 매수 ↓ 완화, 매도 ↑ 강화
        'bear':     (+10.0, -5.0),  # 매수 ↑ 강화, 매도 ↓ 완화
        'volatile': (+8.0, +5.0),   # 양방향 진입 억제
        'range':    (0.0, 0.0),
    }
    delta_buy, delta_sell = adjustments.get(regime, (0.0, 0.0))
    return (
        max(50.0, min(95.0, base_buy + delta_buy)),
        max(10.0, min(50.0, base_sell + delta_sell)),
    )


# ---------------------------------------------------------------------------
# 포트폴리오 요약
# ---------------------------------------------------------------------------

def normalize_asset_mode(asset_mode: str = 'all') -> str:
    """주식 자산 모드 값을 정규화한다."""
    normalized = str(asset_mode or 'all').strip().lower()
    if normalized in {'stock', 'stocks'}:
        return 'stock'
    if normalized == 'etf':
        return 'etf'
    return 'all'


def asset_mode_matches(asset_mode: str, is_etf: bool) -> bool:
    """현재 자산 모드가 종목 유형과 일치하는지 반환한다."""
    normalized = normalize_asset_mode(asset_mode)
    if normalized == 'stock':
        return not is_etf
    if normalized == 'etf':
        return bool(is_etf)
    return True


def select_stock_universe(
    adapter: Any,
    configured_symbols: Optional[List[str]] = None,
    asset_mode: str = 'all',
    limit: int = 8,
    custom_strategy_pool: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """증권사 제공 목록에서 자동매매 분석 유니버스를 선정한다.

    사용자 지정 종목을 우선한다. 자동 선정은 KOSPI/KOSDAQ과 ETF를 모두
    조회하고 거래대금(없으면 거래량×가격, 최후에는 시가총액) 순으로 정렬한다.
    통합 모드는 주식과 ETF를 균형 배분한다. 이는 수익 예측 추천이 아니라 이후
    시장국면·신호·위험 검증에 넣을 유동성 후보를 고르는 단계다.
    """
    normalized_limit = max(1, int(limit or 8))
    configured = list(
        dict.fromkeys(
            str(symbol or '').strip().upper()
            for symbol in (configured_symbols or [])
            if str(symbol or '').strip()
        )
    )
    def _numeric(item: Dict[str, Any], *keys: str) -> float:
        for key in keys:
            try:
                value = float(item.get(key, 0) or 0)
                if value > 0:
                    return value
            except (TypeError, ValueError):
                continue
        return 0.0

    def _is_tradable(item: Dict[str, Any]) -> bool:
        status = str(item.get('status', '') or '').strip().lower()
        return status not in {
            'halted', 'suspended', 'inactive', 'delisted', 'stop', 'stopped',
            '거래정지', '상장폐지',
        }

    def _score(item: Dict[str, Any], index: int) -> tuple:
        direct_value = _numeric(
            item,
            'trade_value',
            'trading_value',
            'turnover',
            'acc_trade_value',
        )
        if direct_value <= 0:
            direct_value = (
                _numeric(item, 'volume', 'acc_volume')
                * _numeric(item, 'price', 'current_price', 'close')
            )
        if direct_value <= 0:
            direct_value = _numeric(item, 'market_cap')
        return direct_value, -index

    def _dedupe_and_rank(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        for item in items:
            if not isinstance(item, dict) or not _is_tradable(item):
                continue
            code = str(item.get('code') or item.get('symbol') or '').strip().upper()
            if not code:
                continue
            if code not in unique:
                order.append(code)
                unique[code] = dict(item)
        indexed = [(index, unique[code]) for index, code in enumerate(order)]
        return [
            item
            for _, item in sorted(
                indexed,
                key=lambda pair: _score(pair[1], pair[0]),
                reverse=True,
            )
        ]

    stock_items: List[Dict[str, Any]] = []
    universe_issues = []
    if hasattr(adapter, 'get_stock_list'):
        for market in ('KOSPI', 'KOSDAQ'):
            try:
                stock_items.extend(
                    dict(item or {})
                    for item in (adapter.get_stock_list(market) or [])
                    if isinstance(item, dict)
                )
            except Exception as exc:
                universe_issues.append(f"{market} 목록 수신 실패({type(exc).__name__})")
                continue

    etf_items: List[Dict[str, Any]] = []
    if hasattr(adapter, 'get_etf_list'):
        try:
            etf_items = [
                dict(item or {})
                for item in (adapter.get_etf_list() or [])
                if isinstance(item, dict)
            ]
        except Exception as exc:
            universe_issues.append(f"ETF 목록 수신 실패({type(exc).__name__})")
            etf_items = []

    # Worker/UI can distinguish an empty universe from an idle market.
    try:
        adapter.last_universe_issues = universe_issues
    except Exception:
        pass

    ranked_stocks = _dedupe_and_rank(stock_items)
    ranked_etfs = _dedupe_and_rank(etf_items)
    mode = normalize_asset_mode(asset_mode)

    if mode == 'stock':
        selected_items = ranked_stocks[:normalized_limit]
    elif mode == 'etf':
        selected_items = ranked_etfs[:normalized_limit]
    else:
        stock_quota = (normalized_limit + 1) // 2
        etf_quota = normalized_limit // 2
        selected_items = ranked_stocks[:stock_quota] + ranked_etfs[:etf_quota]
        selected_codes = {
            str(item.get('code') or item.get('symbol') or '').strip().upper()
            for item in selected_items
        }
        if len(selected_items) < normalized_limit:
            remaining = [
                item
                for item in ranked_stocks[stock_quota:] + ranked_etfs[etf_quota:]
                if str(item.get('code') or item.get('symbol') or '').strip().upper()
                not in selected_codes
            ]
            selected_items.extend(remaining[:normalized_limit - len(selected_items)])

    from .selection_policy import (
        SelectionPolicy,
        combine_selection_paths,
        select_advanced_strategy_universe,
    )

    automatic_candidates = [
        {
            **dict(item),
            'symbol': str(
                item.get('code') or item.get('symbol') or ''
            ).strip().upper(),
            'asset_type': 'etf' if bool(item.get('is_etf', False)) else 'stock',
        }
        for item in selected_items
        if str(item.get('code') or item.get('symbol') or '').strip()
    ]
    general_selection = SelectionPolicy(
        target=str(getattr(adapter, 'broker_name', '') or 'stock_broker'),
        asset_class='stock',
        limit=normalized_limit,
    ).resolve(
        automatic_candidates=automatic_candidates,
        pinned_symbols=configured,
    )
    all_ranked = (
        ranked_stocks
        if mode == 'stock'
        else ranked_etfs
        if mode == 'etf'
        else ranked_stocks + ranked_etfs
    )
    market_candidates = [
        {
            **dict(item),
            'symbol': str(item.get('code') or item.get('symbol') or '').strip().upper(),
            'asset_type': 'etf' if bool(item.get('is_etf', False)) else 'stock',
        }
        for item in all_ranked
        if str(item.get('code') or item.get('symbol') or '').strip()
    ]
    advanced_selection = select_advanced_strategy_universe(
        strategy_pool=custom_strategy_pool,
        market_candidates=market_candidates,
        pinned_symbols=configured,
        asset_class='stock',
        target=str(getattr(adapter, 'broker_name', '') or 'stock_broker'),
        default_limit=normalized_limit,
    )
    resolved = combine_selection_paths(general_selection, advanced_selection)
    return [str(item.get('symbol') or '').strip().upper() for item in resolved]


def filter_positions_by_asset_mode(positions: List[Dict[str, Any]], asset_mode: str = 'all') -> List[Dict[str, Any]]:
    """주식/ETF 자산 모드에 맞게 포지션을 필터링한다."""
    normalized = normalize_asset_mode(asset_mode)
    if normalized == 'all':
        return list(positions or [])
    return [
        position for position in (positions or [])
        if asset_mode_matches(normalized, bool(position.get('is_etf')))
    ]

def summarize_portfolio(positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    보유 종목 리스트로 포트폴리오 요약 생성.

    Args:
        positions: 어댑터의 get_positions() 반환값

    Returns:
        Dict 요약 (총평가금액, 손익, 종목수, ETF수, 리스크 분류)
    """
    if not positions:
        return {
            'total_eval': 0.0,
            'total_pnl': 0.0,
            'total_pnl_rate': 0.0,
            'count': 0,
            'etf_count': 0,
            'stock_count': 0,
            'risk_items': [],
        }

    total_eval = sum(float(p.get('eval_amount') or 0) for p in positions)
    total_pnl = sum(float(p.get('pnl') or 0) for p in positions)
    total_cost = total_eval - total_pnl
    total_pnl_rate = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

    etf_count = sum(1 for p in positions if p.get('is_etf'))
    stock_count = len(positions) - etf_count

    # 손익률 하위 항목 = 위험 종목 후보
    risk_items = [
        {'code': p.get('code', ''), 'name': p.get('name', ''), 'pnl_rate': float(p.get('pnl_rate') or 0)}
        for p in positions
        if float(p.get('pnl_rate') or 0) <= -5.0
    ]

    return {
        'total_eval': total_eval,
        'total_pnl': total_pnl,
        'total_pnl_rate': round(total_pnl_rate, 2),
        'count': len(positions),
        'etf_count': etf_count,
        'stock_count': stock_count,
        'risk_items': risk_items,
    }


# ---------------------------------------------------------------------------
# 메인 서비스 클래스
# ---------------------------------------------------------------------------

class StockAnalysisService:
    """
    주식/ETF 분석 서비스.

    대시보드와 AI 어시스턴트가 어댑터 직접 접근 없이 분석 결과를 가져올
    단일 진입점.
    """
    _paper_positions_by_broker: Dict[str, Dict[str, Dict[str, Any]]] = {}
    _custom_exit_plans_by_broker: Dict[str, Dict[str, Dict[str, Any]]] = {}
    _paper_positions_lock = threading.RLock()

    def __init__(
        self,
        adapter: Any,
        broker_name: str = '',
        recorder: Optional[Any] = None,
        paper_settings: Optional[Dict[str, Any]] = None,
    ):
        """
        Args:
            adapter  : StockExchange 인터페이스를 구현한 어댑터 인스턴스
            broker_name : 표시용 이름 (없으면 adapter.broker_name에서 자동 추출)
        """
        self.adapter = adapter
        self.broker_name = broker_name or getattr(adapter, 'broker_name', '') or getattr(adapter, 'exchange_name', 'unknown')
        self.recorder = recorder
        self._paper_settings = dict(paper_settings or {})
        self._paper_persistence_enabled = paper_settings is not None
        self._active_execution_mode = ExecutionMode.LEARNING.value
        self._instrument_type_cache: Dict[str, str] = {}
        try:
            setattr(self.adapter, '_noah_execution_mode', self._active_execution_mode)
        except Exception:
            pass
        self.log_event = lambda category, msg, level='INFO': log_event(
            category, msg, exchange=self.broker_name, level=level,
            execution_mode=self._active_execution_mode,
            details={'asset_class':'securities', 'instrument_type':'stock_or_etf'}
        )
        # 레짐 캐시: 5분 유효 (코인 trader.py 방식과 동일)
        self._regime_cache: Optional[str] = None
        self._regime_cache_time: float = 0.0
        self._REGIME_CACHE_TTL: float = 300.0
        if self._paper_persistence_enabled:
            self._restore_paper_positions()

    def _restore_paper_positions(self) -> None:
        """Restore only this broker's simulated positions for the active account."""
        try:
            restored = load_stock_paper_positions(self._paper_settings)
            broker_key = str(self.broker_name).lower()
            # The app-data directory is account-scoped.  Replace the in-memory
            # view on restore so a logout/login cannot carry another account's
            # PAPER position into the newly selected account.
            with self._paper_positions_lock:
                self._paper_positions_by_broker.clear()
                self._paper_positions_by_broker.update(
                    {key: dict(value) for key, value in restored.items()}
                )
                self._paper_positions_by_broker.setdefault(broker_key, {})
            self.log_event(
                'system',
                f"증권 PAPER 가상 포지션 {len(self._paper_positions_by_broker[broker_key])}개 복구",
            )
        except Exception as exc:
            self.log_event('system', f"증권 PAPER 포지션 복구 실패: {exc}", level='WARNING')

    def _persist_paper_positions(self) -> None:
        if not self._paper_persistence_enabled:
            return
        try:
            with self._paper_positions_lock:
                snapshot = {
                    broker: {
                        symbol: dict(position)
                        for symbol, position in dict(positions or {}).items()
                    }
                    for broker, positions in self._paper_positions_by_broker.items()
                }
            save_stock_paper_positions(self._paper_settings, snapshot)
        except Exception as exc:
            self.log_event('system', f"증권 PAPER 포지션 저장 실패: {exc}", level='ERROR')

    def _paper_positions(self) -> Dict[str, Dict[str, Any]]:
        return self._paper_positions_by_broker.setdefault(str(self.broker_name).lower(), {})

    def _custom_exit_plans(self) -> Dict[str, Dict[str, Any]]:
        """현재 프로세스의 증권 포지션별 승인 전략 청산계획."""
        return self._custom_exit_plans_by_broker.setdefault(
            str(self.broker_name).lower(),
            {},
        )

    def _restore_custom_exit_plan(self, symbol: str) -> Dict[str, Any]:
        """재시작 뒤 최근 XAI 진입 기록에서 활성 전략 청산계획을 복원한다."""
        cached = dict(self._custom_exit_plans().get(symbol, {}) or {})
        if cached:
            return cached
        recorder = self._get_recorder()
        getter = getattr(recorder, 'get_ai_decisions', None) if recorder is not None else None
        if not callable(getter):
            return {}
        try:
            rows = getter(symbol=symbol, limit=30) or []
        except Exception:
            return {}
        for row in rows:
            decision_type = str(row.get('decision_type') or '')
            payload = dict(row.get('decision_data') or {})
            validation = dict(payload.get('validation') or {})
            action = str(payload.get('action') or '').upper()
            if decision_type == 'stock_auto_exit_symbol' and bool(validation.get('success')):
                break
            if decision_type != 'stock_auto_trade_symbol' or action != 'BUY':
                continue
            if not bool(validation.get('success')):
                continue
            candidate = dict(validation.get('trade_candidate') or {})
            if not candidate.get('strategy_name'):
                break
            restored = {
                'strategy_id': candidate.get('strategy_id'),
                'strategy_key': candidate.get('strategy_key'),
                'strategy_version_id': candidate.get('strategy_version_id'),
                'strategy_name': candidate.get('strategy_name'),
                'strategy_role': candidate.get('strategy_role'),
                'operation_mode': candidate.get('operation_mode'),
                'engine_settings': dict(candidate.get('engine_settings') or {}),
                'rules': dict(candidate.get('selected_rules') or {}),
                'exit_plan': dict(candidate.get('exit_plan') or {}),
                'market_regime': candidate.get('market_regime'),
            }
            self._custom_exit_plans()[symbol] = restored
            return restored
        return {}

    @entry_submission('', stock=True)
    def _place_paper_stock_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_type: str,
        asset_class: str = "stock",
        cost_policy: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, Dict[str, Any], List[str]]:
        if price <= 0 or quantity <= 0:
            return False, {}, ['paper_price_or_quantity_invalid']
        now = datetime.now(timezone.utc)
        positions = self._paper_positions()
        side_upper = str(side).upper()
        normalized_asset_class = "etf" if str(asset_class).lower() == "etf" else "stock"
        costs = normalize_stock_paper_cost_policy(cost_policy)
        order_result: Dict[str, Any] = {}
        if side_upper == 'BUY':
            existing = positions.get(symbol)
            previous_qty = self._to_float((existing or {}).get('quantity'), default=0.0)
            previous_price = self._to_float((existing or {}).get('entry_price'), default=0.0)
            total_qty = previous_qty + quantity
            average_price = (
                ((previous_price * previous_qty) + (price * quantity)) / total_qty
                if total_qty > 0 else price
            )
            entry_notional = price * quantity
            previous_entry_fees = self._to_float((existing or {}).get('entry_fees'), default=0.0)
            previous_entry_slippage = self._to_float(
                (existing or {}).get('entry_slippage'), default=0.0
            )
            entry_fees = previous_entry_fees + entry_notional * float(costs['buy_commission_rate'])
            entry_slippage = (
                previous_entry_slippage
                + entry_notional * float(costs['buy_slippage_rate'])
            )
            positions[symbol] = {
                'symbol': symbol,
                'code': symbol,
                'side': 'LONG',
                'quantity': total_qty,
                'entry_price': average_price,
                'current_price': price,
                'asset_class': normalized_asset_class,
                'quote_currency': 'KRW',
                'entry_fees': entry_fees,
                'entry_slippage': entry_slippage,
                'buy_commission_rate': costs['buy_commission_rate'],
                'sell_commission_rate': costs['sell_commission_rate'],
                'stock_sell_tax_rate': costs['stock_sell_tax_rate'],
                'etf_sell_tax_rate': costs['etf_sell_tax_rate'],
                'buy_slippage_rate': costs['buy_slippage_rate'],
                'sell_slippage_rate': costs['sell_slippage_rate'],
                'cost_schema_version': costs['cost_schema_version'],
                'cost_calculation_status': costs['cost_calculation_status'],
                'cost_source': costs['cost_source'],
                'cost_policy_issues': list(costs.get('cost_policy_issues') or []),
                'opened_at': (existing or {}).get('opened_at') or now.isoformat(),
                'execution_mode': 'paper',
            }
            valuation = calculate_stock_paper_valuation(positions[symbol], price, costs)
            positions[symbol].update({
                'gross_pnl': valuation['gross_pnl'],
                'unrealized_pnl': valuation['net_pnl'],
                'unrealized_pnl_percent': valuation['net_pnl_percent'],
                'estimated_fees': valuation['estimated_fees'],
                'estimated_taxes': valuation['estimated_taxes'],
                'estimated_slippage': valuation['estimated_slippage'],
                'total_cost': valuation['total_cost'],
            })
            order_result = {
                'gross_pnl': 0.0,
                'net_pnl': -entry_notional * (
                    float(costs['buy_commission_rate']) + float(costs['buy_slippage_rate'])
                ),
                'fees': entry_notional * float(costs['buy_commission_rate']),
                'estimated_taxes': 0.0,
                'estimated_slippage': entry_notional * float(costs['buy_slippage_rate']),
                'total_cost': entry_notional * (
                    float(costs['buy_commission_rate']) + float(costs['buy_slippage_rate'])
                ),
                'cost_calculation_status': costs['cost_calculation_status'],
                'cost_source': costs['cost_source'],
                'cost_policy_issues': list(costs.get('cost_policy_issues') or []),
            }
        elif side_upper == 'SELL':
            existing = positions.get(symbol)
            if not existing:
                return False, {}, ['paper_position_not_found']
            normalized_asset_class = (
                'etf'
                if str(existing.get('asset_class') or normalized_asset_class).lower() == 'etf'
                else 'stock'
            )
            existing_qty = self._to_float(existing.get('quantity'))
            if quantity > existing_qty + 1e-9:
                return False, {}, ['paper_sell_quantity_exceeds_position']
            close_quantity = min(quantity, existing_qty)
            ratio = close_quantity / existing_qty if existing_qty > 0 else 0.0
            close_position = dict(existing)
            close_position['quantity'] = close_quantity
            close_position['entry_fees'] = self._to_float(
                existing.get('entry_fees'), default=0.0
            ) * ratio
            close_position['entry_slippage'] = self._to_float(
                existing.get('entry_slippage'), default=0.0
            ) * ratio
            valuation = calculate_stock_paper_valuation(close_position, price, costs)
            if valuation.get('calculation_status') != 'valid':
                return False, {}, ['paper_pnl_calculation_invalid']
            remaining = existing_qty - close_quantity
            if remaining > 1e-9:
                existing['quantity'] = remaining
                existing['current_price'] = price
                existing['entry_fees'] = max(
                    0.0,
                    self._to_float(existing.get('entry_fees'), default=0.0)
                    - float(valuation['entry_fees']),
                )
                existing['entry_slippage'] = max(
                    0.0,
                    self._to_float(existing.get('entry_slippage'), default=0.0)
                    - float(valuation['entry_slippage']),
                )
                remaining_valuation = calculate_stock_paper_valuation(existing, price, costs)
                existing.update({
                    'gross_pnl': remaining_valuation['gross_pnl'],
                    'unrealized_pnl': remaining_valuation['net_pnl'],
                    'unrealized_pnl_percent': remaining_valuation['net_pnl_percent'],
                    'estimated_fees': remaining_valuation['estimated_fees'],
                    'estimated_taxes': remaining_valuation['estimated_taxes'],
                    'estimated_slippage': remaining_valuation['estimated_slippage'],
                    'total_cost': remaining_valuation['total_cost'],
                })
            else:
                positions.pop(symbol, None)
            order_result = {
                'gross_pnl': valuation['gross_pnl'],
                'net_pnl': valuation['net_pnl'],
                'net_pnl_percent': valuation['net_pnl_percent'],
                'fees': valuation['estimated_fees'],
                'estimated_taxes': valuation['estimated_taxes'],
                'estimated_slippage': valuation['estimated_slippage'],
                'total_cost': valuation['total_cost'],
                'cost_calculation_status': valuation['cost_calculation_status'],
                'cost_source': valuation['cost_source'],
                'cost_policy_issues': list(valuation.get('cost_policy_issues') or []),
                'closed_quantity': close_quantity,
                'entry_price': self._to_float(close_position.get('entry_price')),
                'exit_price': price,
                'asset_class': valuation['asset_class'],
                'quote_currency': 'KRW',
                'fee_rate': float(valuation['buy_commission_rate']) + float(valuation['sell_commission_rate']),
                'tax_rate': (
                    float(valuation['etf_sell_tax_rate'])
                    if valuation['asset_class'] == 'etf'
                    else float(valuation['stock_sell_tax_rate'])
                ),
                'slippage_rate': float(valuation['buy_slippage_rate']) + float(valuation['sell_slippage_rate']),
            }
        else:
            return False, {}, ['paper_side_not_supported']

        return True, {
            'status': 'paper_filled',
            'success': True,
            'simulated': True,
            'order_id': f"paper-{self.broker_name}-{symbol}-{int(now.timestamp() * 1000)}",
            'symbol': symbol,
            'side': side_upper,
            'quantity': float(order_result.get('closed_quantity') or quantity),
            'price': price,
            'filled_price': price,
            'order_type': order_type,
            'asset_class': normalized_asset_class,
            'quote_currency': 'KRW',
            **order_result,
        }, []

    def _refresh_paper_position_valuation(
        self,
        symbol: str,
        current_price: float,
        cost_policy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        position = self._paper_positions().get(str(symbol or '').strip().upper())
        if not position:
            return {}
        valuation = calculate_stock_paper_valuation(position, current_price, cost_policy)
        if valuation.get('calculation_status') != 'valid':
            position['calculation_status'] = 'invalid'
            return valuation
        position.update({
            'current_price': float(current_price),
            'side': 'LONG',
            'quote_currency': 'KRW',
            'gross_pnl': valuation['gross_pnl'],
            'unrealized_pnl': valuation['net_pnl'],
            'unrealized_pnl_percent': valuation['net_pnl_percent'],
            'estimated_fees': valuation['estimated_fees'],
            'estimated_taxes': valuation['estimated_taxes'],
            'estimated_slippage': valuation['estimated_slippage'],
            'total_cost': valuation['total_cost'],
            'calculation_status': 'valid',
            'cost_calculation_status': valuation['cost_calculation_status'],
            'cost_source': valuation['cost_source'],
            'cost_policy_issues': list(valuation.get('cost_policy_issues') or []),
        })
        return valuation

    def _get_recent_paper_trade_samples(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Read only this broker's completed PAPER outcomes for PAPER policy."""
        try:
            from trading.paper_strategy_ledger import (
                is_valid_paper_outcome,
                read_paper_strategy_outcomes,
            )

            broker = str(self.broker_name or '').strip().lower()
            rows = [
                dict(row)
                for row in read_paper_strategy_outcomes()
                if str(row.get('exchange') or '').strip().lower() == broker
                and is_valid_paper_outcome(row)
            ]
            rows.sort(key=lambda row: str(row.get('closed_at') or ''))
            return [
                {
                    **row,
                    'pnl_is_net': True,
                    'timestamp': row.get('closed_at'),
                }
                for row in rows[-max(1, int(limit)):]
            ]
        except Exception as exc:
            self.log_event(
                'stock_auto_trade',
                f'PAPER 성과 표본 조회 실패: {exc}',
                level='WARNING',
            )
            return []

    def _record_stock_paper_outcome(
        self,
        *,
        position_before: Dict[str, Any],
        order_result: Dict[str, Any],
        strategy_key: str = '',
        version_id: str = '',
    ) -> Optional[Dict[str, Any]]:
        """Write one complete, KRW-denominated stock/ETF PAPER close."""
        try:
            from trading.paper_strategy_ledger import record_paper_strategy_outcome

            return record_paper_strategy_outcome(
                scope='unified',
                strategy_scope='unified',
                exchange=self.broker_name,
                symbol=str(position_before.get('symbol') or position_before.get('code') or ''),
                strategy_key=str(strategy_key or ''),
                version_id=str(version_id or ''),
                opened_at=position_before.get('opened_at'),
                closed_at=datetime.now(timezone.utc),
                gross_pnl=float(order_result.get('gross_pnl') or 0.0),
                net_pnl=float(order_result.get('net_pnl') or 0.0),
                net_pnl_percent=float(order_result.get('net_pnl_percent') or 0.0),
                fees=float(order_result.get('fees') or 0.0),
                estimated_taxes=float(order_result.get('estimated_taxes') or 0.0),
                estimated_slippage=float(order_result.get('estimated_slippage') or 0.0),
                entry_price=float(order_result.get('entry_price') or position_before.get('entry_price') or 0.0),
                exit_price=float(order_result.get('exit_price') or order_result.get('filled_price') or 0.0),
                quantity=float(order_result.get('closed_quantity') or order_result.get('quantity') or 0.0),
                side='LONG',
                quote_currency='KRW',
                fee_rate=float(order_result.get('fee_rate') or 0.0),
                tax_rate=float(order_result.get('tax_rate') or 0.0),
                slippage_rate=float(order_result.get('slippage_rate') or 0.0),
                calculation_status='valid',
                cost_calculation_status=str(
                    order_result.get('cost_calculation_status')
                    or 'estimated_stock_paper_contract'
                ),
                cost_policy_issues=list(order_result.get('cost_policy_issues') or []),
                guardrail_violations=0,
                position_id=str(order_result.get('order_id') or ''),
                leverage=1,
                entry_reason=str(position_before.get('entry_reason') or ''),
                entry_market_regime=str(position_before.get('entry_market_regime') or ''),
                entry_regime_scope=str(position_before.get('entry_regime_scope') or ''),
                entry_signal_source=str(position_before.get('entry_signal_source') or ''),
                sizing_policy_reason=str(
                    dict(position_before.get('position_sizing') or {}).get('reason') or ''
                ),
                sizing_target_notional=dict(
                    position_before.get('position_sizing') or {}
                ).get('target_notional'),
                sizing_final_notional=dict(
                    position_before.get('position_sizing') or {}
                ).get('final_notional'),
                sizing_limiting_reasons=list(dict(
                    position_before.get('position_sizing') or {}
                ).get('limiting_reasons') or []),
                exit_reason=str(order_result.get('exit_reason') or 'paper_sell'),
                tp_price=position_before.get('tp_price'),
                sl_price=position_before.get('sl_price'),
                effective_tp_fraction=position_before.get('effective_tp_fraction'),
                effective_sl_fraction=position_before.get('effective_sl_fraction'),
                exit_policy_source=str(position_before.get('exit_policy_source') or ''),
                exit_policy_reason=str(position_before.get('exit_policy_reason') or ''),
            )
        except Exception as exc:
            logger.debug("stock PAPER 전략 귀속 저장 실패 (%s): %s", self.broker_name, exc)
            return None

    def _get_recorder(self) -> Optional[Any]:
        """Recorder 인스턴스를 지연 로드한다."""
        if self.recorder is not None:
            return self.recorder

        # 어댑터에 이미 recorder가 연결된 경우 우선 사용
        try:
            adapter_recorder = getattr(self.adapter, 'recorder', None)
            if adapter_recorder is not None:
                self.recorder = adapter_recorder
                return self.recorder
        except Exception:
            pass

        # 로컬 Recorder 생성 (실패해도 서비스는 계속 동작)
        try:
            from trading.recorder import Recorder
            self.recorder = Recorder(exchange=self.broker_name)
        except Exception as exc:
            logger.warning("Recorder 초기화 실패 (%s): %s", self.broker_name, exc)
            self.recorder = None
        return self.recorder

    # ------------------------------------------------------------------
    # 시장 레짐 (캐싱)
    # ------------------------------------------------------------------

    def get_market_regime(self) -> str:
        """현재 시장 레짐을 반환한다 (5분 캐시).

        코인 trader._analyze_market_regime_binance_fast()와 동일한 역할.
        bear/bull/volatile/range 중 하나를 반환한다.
        """
        now = pytime.time()
        if now < getattr(self, '_regime_retry_after', 0):
            return 'unknown'
        if self._regime_cache and (now - self._regime_cache_time) < self._REGIME_CACHE_TTL:
            return self._regime_cache

        previous_regime = self._regime_cache
        regime = detect_market_regime(self.adapter)
        if regime == 'unknown':
            self._regime_retry_after = now + 60
            from trading.runtime_observability import emit_runtime_status
            emit_runtime_status(self, self.broker_name, 'market_data_missing',
                '시장국면 확인 불가 · 원인=' + str(getattr(self.adapter, '_regime_data_reason', 'no_usable_index_or_proxy_quote'))
                + ' · 신규 진입 보류. 기존 포지션 관리는 시도하지만 시세/주문 API 장애 시 청산을 보장하지 않습니다.', level='WARNING')
            return regime
        self._regime_retry_after = 0
        self._regime_cache = regime
        self._regime_cache_time = now

        if previous_regime and regime != previous_regime:
            try:
                from trading.notifications import publish_market_regime_change
                mode = str(getattr(self, '_active_execution_mode', 'learning') or 'learning')
                mode = {'live_api': 'live', 'mock': 'paper'}.get(mode, mode)
                publish_market_regime_change(self.broker_name, previous_regime, regime,
                                             execution_mode=mode)
            except Exception:
                pass

        basis = str(getattr(self.adapter, '_regime_data_reason', 'index_or_proxy'))
        self.log_event('stock_regime', f"시장 레짐 감지: {regime} · 근거={basis}")
        self._emit_analysis_log('market_regime', {'regime': regime, 'broker': self.broker_name, 'basis': basis})
        self._persist_xai_decision(
            symbol='MARKET',
            decision_type='stock_market_regime',
            payload={
                'regime': regime,
                'broker': self.broker_name,
                'reasoning': (
                    f"시장 근거 {basis} 기반 레짐 분류: {regime} → "
                    f"{'상승장 감지, 매수 조건 완화' if regime == 'bull' else ''}"
                    f"{'하락장 감지, 매수 조건 강화' if regime == 'bear' else ''}"
                    f"{'고변동 감지, 진입 억제' if regime == 'volatile' else ''}"
                    f"{'횡보장, 기본 임계값 유지' if regime == 'range' else ''}"
                ),
                'timestamp': datetime.now().isoformat(),
            },
        )
        return regime

    # ------------------------------------------------------------------
    # 거래 결과 학습 피드백
    # ------------------------------------------------------------------

    def _get_recent_trade_feedback(self, symbol: str, limit: int = 30) -> Dict[str, Any]:
        """최근 거래 결과를 DB에서 읽어 해당 종목의 성과를 집계한다.

        코인 ai_manager의 피드백 루프와 동일한 역할.
        결과를 score_stock/score_etf의 pnl_rate 인자로 연결한다.
        """
        recorder = self._get_recorder()
        if recorder is None:
            return {'pnl_rate': 0.0, 'win_rate': 0.0, 'trade_count': 0}

        try:
            rows = recorder.execute_query(
                """
                SELECT pnl, pnl_percent, side
                FROM trade_log
                WHERE UPPER(symbol) = ?
                  AND LOWER(COALESCE(exchange, '')) = ?
                  AND exit_time IS NOT NULL
                ORDER BY exit_time DESC
                LIMIT ?
                """,
                (symbol.upper(), self.broker_name.lower(), limit),
            )
            if not rows:
                return {'pnl_rate': 0.0, 'win_rate': 0.0, 'trade_count': 0}

            pnl_list = [float(r.get('pnl_percent') or r.get('pnl') or 0) for r in rows]
            wins = sum(1 for v in pnl_list if v > 0)
            avg_pnl = sum(pnl_list) / len(pnl_list) if pnl_list else 0.0
            win_rate = wins / len(pnl_list) if pnl_list else 0.0

            return {
                'pnl_rate': round(avg_pnl, 4),
                'win_rate': round(win_rate, 4),
                'trade_count': len(pnl_list),
            }
        except Exception as exc:
            logger.debug("거래 피드백 조회 실패 (%s %s): %s", self.broker_name, symbol, exc)
            return {'pnl_rate': 0.0, 'win_rate': 0.0, 'trade_count': 0}

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _normalize_side(side_raw: Any) -> str:
        raw = str(side_raw or '').upper()
        if 'BUY' in raw or '매수' in raw:
            return 'LONG'
        if 'SELL' in raw or '매도' in raw:
            return 'SHORT'
        return 'LONG'

    @staticmethod
    def _parse_trade_time(raw_ts: Any) -> Optional[datetime]:
        if raw_ts is None:
            return None
        text = str(raw_ts).strip()
        if not text:
            return None

        # ISO 우선
        try:
            return datetime.fromisoformat(text.replace('Z', '+00:00'))
        except Exception:
            pass

        digits = ''.join(ch for ch in text if ch.isdigit())
        if len(digits) == 14:
            try:
                return datetime.strptime(digits, '%Y%m%d%H%M%S')
            except Exception:
                pass
        if len(digits) == 8:
            try:
                return datetime.strptime(digits, '%Y%m%d')
            except Exception:
                pass
        if len(digits) == 6:
            try:
                now = datetime.now()
                hh = int(digits[0:2])
                mm = int(digits[2:4])
                ss = int(digits[4:6])
                return now.replace(hour=hh, minute=mm, second=ss, microsecond=0)
            except Exception:
                pass
        return None

    def _trade_exists(self, recorder: Any, symbol: str, side: str, entry_time: datetime, quantity: float, entry_price: float) -> bool:
        """중복 trade_log 저장을 방지한다."""
        try:
            query = """
                SELECT id
                FROM trade_log
                WHERE symbol = ?
                  AND side = ?
                  AND exchange = ?
                  AND entry_time = ?
                  AND ABS(quantity - ?) < 1e-9
                  AND ABS(entry_price - ?) < 1e-9
                LIMIT 1
            """
            params = (
                symbol,
                side,
                self.broker_name,
                entry_time,
                quantity,
                entry_price,
            )
            rows = recorder.execute_query(query, params)
            return bool(rows)
        except Exception:
            return False

    def _sync_trade_history_to_recorder(self, trades: List[Dict[str, Any]]) -> int:
        """Store broker fills as executions, never as fake closed positions.

        A fill is not a completed trade lifecycle.  PnL statistics are produced
        only by the NoahAI-owned BUY lot -> SELL allocation path below.
        """
        recorder = self._get_recorder()
        if recorder is None or not trades:
            return 0
        normalized: List[Dict[str, Any]] = []
        for trade in trades:
            if not isinstance(trade, dict):
                continue
            symbol = str(trade.get('symbol') or trade.get('code') or '').strip()
            qty = self._to_float(trade.get('quantity', trade.get('filled_quantity', trade.get('qty', 0.0))))
            price = self._to_float(trade.get('filled_price', trade.get('price', trade.get('current_price', 0.0))))
            if not symbol or qty <= 0 or price <= 0:
                continue
            row = dict(trade)
            # A broker fill is not a complete BUY-lot -> SELL-lot lifecycle.
            # Some adapters expose a fill-level `profit` field with a different
            # meaning, so never promote it to round-trip realized PnL here.
            for pnl_key in ('pnl', 'profit', 'realized_pnl', 'realizedPnl'):
                row.pop(pnl_key, None)
            normalized_side = self._normalize_side(trade.get('side'))
            row.update({
                'symbol': symbol,
                'side': 'buy' if normalized_side == 'LONG' else 'sell',
                'quantity': qty,
                'price': price,
                'timestamp': trade.get('timestamp') or trade.get('filled_at') or trade.get('time') or trade.get('order_time'),
                'order_id': trade.get('order_id') or trade.get('orderId') or trade.get('odno'),
                'trade_id': trade.get('trade_id') or trade.get('execution_id') or trade.get('id'),
                'commission': (
                    self._to_float(trade.get('fee', trade.get('fees', trade.get('commission', 0.0))))
                    + self._to_float(trade.get('tax', trade.get('transaction_tax', trade.get('securities_tax', 0.0))))
                ),
                'commission_asset': str(trade.get('fee_currency') or 'KRW').upper(),
                '_execution_confirmed': True,
                'status': 'filled',
            })
            normalized.append(row)
        result = recorder.save_exchange_execution_history(
            self.broker_name,
            normalized,
            source='broker_execution_api',
        )
        inserted = int((result or {}).get('inserted', 0) or 0)
        if inserted > 0:
            self._emit_analysis_log('trade_sync', {'broker': self.broker_name, 'inserted': inserted, 'ledger': 'exchange_execution_log'})
        return inserted

    def sync_recent_trades_to_recorder(self, limit: int = 500) -> int:
        """어댑터의 최근 체결을 즉시 Recorder에 동기화한다."""
        merged: List[Dict[str, Any]] = []
        try:
            if hasattr(self.adapter, 'get_today_trades'):
                merged.extend(self.adapter.get_today_trades() or [])
        except Exception:
            pass

        try:
            if hasattr(self.adapter, 'get_trade_history'):
                merged.extend(self.adapter.get_trade_history(limit=limit) or [])
        except Exception:
            pass

        if not merged:
            return 0

        # 중복 제거: symbol/side/time/qty/price 키로 축약
        dedup_map: Dict[str, Dict[str, Any]] = {}
        for t in merged:
            symbol = str(t.get('symbol') or t.get('code') or '').strip()
            side = str(t.get('side') or '').strip().upper()
            ts = str(t.get('timestamp') or t.get('filled_at') or t.get('time') or t.get('order_time') or '').strip()
            qty = str(t.get('quantity') or t.get('filled_quantity') or t.get('qty') or '').strip()
            price = str(t.get('filled_price') or t.get('price') or '').strip()
            if not symbol:
                continue
            key = f"{symbol}|{side}|{ts}|{qty}|{price}"
            dedup_map[key] = t

        return self._sync_trade_history_to_recorder(list(dedup_map.values()))

    def _classify_asset_type(self, symbol: str) -> str:
        try:
            if hasattr(self.adapter, 'is_etf') and self.adapter.is_etf(symbol):
                return 'etf'
        except Exception:
            pass
        return 'stock'

    def _aggregate_trade_stats(self, trades: List[Dict[str, Any]], asset_type: str = 'all') -> Dict[str, Any]:
        filtered = trades
        if asset_type in ('stock', 'etf'):
            filtered = [
                t for t in trades
                if self._classify_asset_type(str(t.get('symbol') or t.get('code') or '')) == asset_type
            ]

        total = len(filtered)
        buy_count = 0
        sell_count = 0
        winning = 0
        losing = 0
        total_pnl = 0.0
        pnl_values: List[float] = []

        for t in filtered:
            side = str(t.get('side') or '').upper()
            if 'BUY' in side or '매수' in side:
                buy_count += 1
            if 'SELL' in side or '매도' in side:
                sell_count += 1

            pnl = self._to_float(t.get('pnl', t.get('realized_pnl', 0.0)))
            total_pnl += pnl
            pnl_values.append(pnl)
            if pnl > 0:
                winning += 1
            elif pnl < 0:
                losing += 1

        avg_pnl = (sum(pnl_values) / len(pnl_values)) if pnl_values else 0.0
        max_drawdown = min(pnl_values) if pnl_values else 0.0
        win_rate = (winning / total * 100.0) if total > 0 else 0.0

        return {
            'total_trades': total,
            'buy_count': buy_count,
            'sell_count': sell_count,
            'winning_trades': winning,
            'losing_trades': losing,
            'realized_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'win_rate': win_rate,
            'max_drawdown': max_drawdown,
        }

    def _persist_stock_trade_stats(self, trades: List[Dict[str, Any]]) -> None:
        recorder = self._get_recorder()
        if recorder is None:
            return

        try:
            for asset_type in ('all', 'stock', 'etf'):
                stats = self._aggregate_trade_stats(trades, asset_type=asset_type)
                recorder.save_stock_trade_stats(
                    broker=self.broker_name,
                    asset_type=asset_type,
                    stats=stats,
                )
        except Exception as exc:
            logger.debug("stock_trade_stats 저장 실패 (%s): %s", self.broker_name, exc)

    def get_db_trade_summary(self, days: int = 30) -> Dict[str, Dict[str, Any]]:
        """Recorder의 브로커/자산유형 통계를 조회한다."""
        recorder = self._get_recorder()
        if recorder is None:
            return {}
        try:
            rows = recorder.load_stock_trade_stats(broker=self.broker_name, days=days)
            result: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                key = str(row.get('asset_type') or 'all').lower()
                result[key] = row
            return result
        except Exception:
            return {}

    def _persist_analysis_snapshot(self, result: Dict[str, Any]) -> None:
        """주식/ETF 분석 결과를 analysis_log에 저장한다."""
        recorder = self._get_recorder()
        if recorder is None:
            return

        try:
            from trading.recorder import AnalysisLog
            score = self._to_float(result.get('score'))
            momentum = self._to_float(result.get('momentum'))
            signal = 'HOLD'
            if score >= 70 and momentum >= 0:
                signal = 'LONG'
            elif score <= 30 and momentum < 0:
                signal = 'SHORT'

            analysis_log = AnalysisLog(
                id=None,
                symbol=str(result.get('symbol') or ''),
                signal=signal,
                confidence=max(0.0, min(1.0, score / 100.0)),
                rsi=self._to_float(result.get('rsi', 50.0)),
                macd=self._to_float(result.get('macd', 0.0)),
                sma_20=self._to_float(result.get('sma_20', result.get('current_price', 0.0))),
                sma_50=self._to_float(result.get('sma_50', result.get('current_price', 0.0))),
                bb_upper=self._to_float(result.get('bb_upper', 0.0)),
                bb_lower=self._to_float(result.get('bb_lower', 0.0)),
                volume_ratio=self._to_float(result.get('volume_ratio', 1.0)),
                volatility=abs(self._to_float(result.get('change_rate', 0.0))) / 100.0,
                trend='up' if momentum > 0 else ('down' if momentum < 0 else 'flat'),
                reasoning=(
                    f"stock_analysis score={score:.1f}, momentum={momentum:+.2f}, "
                    f"is_etf={bool(result.get('is_etf', False))}, broker={self.broker_name}"
                ),
                timestamp=datetime.now(),
            )
            recorder.insert_analysis_log(analysis_log)
        except Exception as exc:
            logger.debug("analysis_log 저장 실패 (%s): %s", self.broker_name, exc)

    def _persist_xai_decision(self, symbol: str, decision_type: str, payload: Dict[str, Any]) -> None:
        """Persist one broker-independent XAI envelope around stock/ETF evidence."""
        recorder = self._get_recorder()
        if recorder is None:
            return

        try:
            from trading.event_contract import execution_mode_key
            evidence = dict(payload or {})
            validation = dict(evidence.get('validation') or {}) if isinstance(evidence.get('validation'),dict) else {}
            result = dict(evidence.get('result') or {}) if isinstance(evidence.get('result'),dict) else {}
            raw_mode = evidence.get('execution_mode') or validation.get('execution_mode') or self._active_execution_mode
            mode = execution_mode_key(raw_mode)
            if mode == 'unknown' and not str(decision_type).startswith(('stock_auto_trade','stock_auto_exit')):
                mode = ExecutionMode.LEARNING.value
            symbol_key = str(symbol or '').strip().upper()
            explicit_asset = str(evidence.get('instrument_type') or evidence.get('asset_class') or '').lower()
            if explicit_asset in {'stock','etf'}:
                instrument_type = explicit_asset
            elif isinstance(evidence.get('is_etf'),bool):
                instrument_type = 'etf' if evidence['is_etf'] else 'stock'
            else:
                instrument_type = self._instrument_type_cache.get(symbol_key,'securities')
            action = str(evidence.get('decision_status') or evidence.get('action') or evidence.get('signal')
                         or validation.get('status') or 'observed').lower()
            reason_code = str(evidence.get('reason_code') or evidence.get('reason') or validation.get('reason')
                              or validation.get('status') or ('analysis_completed' if decision_type=='stock_analyze_symbol' else action))
            order_id = evidence.get('order_id') or result.get('order_id') or result.get('id')
            actual_order = evidence.get('actual_order')
            if not isinstance(actual_order,bool):
                if mode in {ExecutionMode.PAPER.value,ExecutionMode.LEARNING.value} or 'blocked' in reason_code:
                    actual_order = False
                elif mode == ExecutionMode.LIVE.value and order_id is not None:
                    actual_order = True
                else:
                    # A failed/timeout response is not proof that no order was
                    # submitted. Nor does a generic success prove acceptance.
                    actual_order = None
            evidence.update({
                'broker': evidence.get('broker') or self.broker_name,
                'execution_mode': mode,
                'asset_class': 'securities',
                'instrument_type': instrument_type,
                'event_kind': 'decision',
                'status': action,
                'decision_status': action,
                'reason_code': reason_code,
                'actual_order': actual_order,
                'order_id': str(order_id) if order_id is not None else None,
                'xai_contract': {
                    'schema_version': 1,
                    'decision': action,
                    'why': str(evidence.get('reasoning') or evidence.get('reason') or reason_code),
                    'constraints': validation,
                    'outcome': result,
                    'actual_order': actual_order,
                },
            })
            try:
                recorder.save_ai_decision(
                    symbol,
                    decision_type,
                    evidence,
                    exchange=self.broker_name,
                )
            except TypeError:
                # Compatibility for injected legacy/test recorders. Production
                # Recorder accepts the explicit owner above.
                recorder.save_ai_decision(symbol, decision_type, evidence)
        except Exception as exc:
            logger.warning('stock XAI persistence failed (%s): %s', self.broker_name, type(exc).__name__)

    def _emit_analysis_log(self, stage: str, payload: Dict[str, Any]) -> None:
        """분석 핵심 결과를 로그 스트림/UI에 남긴다."""
        try:
            keys = ', '.join(f"{k}={payload.get(k)}" for k in payload.keys())
            self.log_event('stock_analysis', f"{stage} | {keys}")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 포트폴리오 요약
    # ------------------------------------------------------------------

    def _confirmed_positions(self) -> List[Dict[str, Any]]:
        checked = getattr(self.adapter, 'get_positions_result', None)
        if callable(checked):
            result = checked()
            if not isinstance(result, dict) or result.get('status') != 'success' or not isinstance(result.get('positions'), list):
                raise RuntimeError('positions_unavailable')
            return result['positions']
        # Compatibility for in-memory PAPER/testing adapters.
        positions = self.adapter.get_positions()
        if not isinstance(positions, list):
            raise RuntimeError('positions_unavailable')
        return positions

    def get_portfolio_summary(self, asset_mode: str = 'all') -> Dict[str, Any]:
        """잔고 + 보유종목 통합 요약."""
        try:
            # 주문 직후 화면 갱신에서도 DB 반영이 되도록 선동기화 시도
            try:
                self.sync_recent_trades_to_recorder(limit=200)
            except Exception:
                pass

            balance = {}
            if hasattr(self.adapter, 'get_balance'):
                balance = self.adapter.get_balance() or {}

            positions = self._confirmed_positions()
            positions = filter_positions_by_asset_mode(positions, asset_mode)

            portfolio = summarize_portfolio(positions)
            portfolio['broker'] = self.broker_name
            portfolio['asset_mode'] = normalize_asset_mode(asset_mode)
            portfolio['cash'] = float(balance.get('cash') or 0)
            portfolio['total_assets'] = float(balance.get('total_assets') or 0)
            portfolio['account_no'] = balance.get('account_no', '')
            portfolio['balance_status'] = balance.get('status', 'unknown')
            self._emit_analysis_log('portfolio_summary', {
                'count': portfolio.get('count', 0),
                'etf_count': portfolio.get('etf_count', 0),
                'total_pnl_rate': portfolio.get('total_pnl_rate', 0),
                'risk_items': len(portfolio.get('risk_items') or []),
            })
            return portfolio
        except Exception as exc:
            logger.error("포트폴리오 요약 실패 (%s): %s", self.broker_name, exc)
            return {'broker': self.broker_name, 'error': str(exc), 'positions_status': 'error', 'positions': None}

    # ------------------------------------------------------------------
    # ETF 분석
    # ------------------------------------------------------------------

    def get_etf_analysis(self, asset_mode: str = 'all') -> List[ETFMetrics]:
        """보유 ETF 목록에서 ETFMetrics 리스트 반환."""
        metrics: List[ETFMetrics] = []
        try:
            if normalize_asset_mode(asset_mode) == 'stock':
                return metrics

            positions = []
            if hasattr(self.adapter, 'get_positions'):
                positions = self.adapter.get_positions() or []

            # ETF 보유 종목만 필터
            etf_positions = [p for p in filter_positions_by_asset_mode(positions, asset_mode) if p.get('is_etf')]

            # ETF 목록에서 메타데이터 보완
            etf_meta: Dict[str, Dict] = {}
            if hasattr(self.adapter, 'get_etf_list'):
                try:
                    for item in (self.adapter.get_etf_list() or []):
                        code = str(item.get('code', '')).strip()
                        if code:
                            etf_meta[code] = item
                except Exception:
                    pass

            for pos in etf_positions:
                code = str(pos.get('code', '')).strip()
                meta = etf_meta.get(code, {})
                current_price = float(pos.get('current_price') or 0)
                nav = float(meta.get('nav') or pos.get('nav') or 0)
                tracking_error = meta.get('tracking_error') or pos.get('tracking_error')
                if tracking_error is not None:
                    try:
                        tracking_error = float(tracking_error)
                    except Exception:
                        tracking_error = None
                trade_value = float(meta.get('trade_value') or pos.get('trade_value') or 0)
                expense_ratio = meta.get('expense_ratio')

                # 실시간 지표 보강: get_etf_realtime_metrics() 지원 어댑터이면
                # NAV·추적오차·거래대금을 실시간으로 갱신
                if hasattr(self.adapter, 'get_etf_realtime_metrics') and code:
                    try:
                        rt = self.adapter.get_etf_realtime_metrics(code)
                        if rt.get('status') == 'ok':
                            if rt.get('current_price'):
                                current_price = float(rt['current_price'])
                            if rt.get('nav'):
                                nav = float(rt['nav'])
                            if rt.get('tracking_error') is not None:
                                tracking_error = float(rt['tracking_error'])
                            if rt.get('trade_value'):
                                trade_value = float(rt['trade_value'])
                            if rt.get('expense_ratio') is not None:
                                expense_ratio = rt['expense_ratio']
                    except Exception:
                        pass  # 실시간 보강 실패 시 ETF 목록 데이터 유지

                metrics.append(ETFMetrics(
                    code=code,
                    name=str(pos.get('name', code)),
                    nav=nav,
                    current_price=current_price,
                    tracking_error=tracking_error,
                    trade_value=trade_value,
                    base_index=str(meta.get('base_index') or ''),
                    expense_ratio=expense_ratio,
                ))
            self._emit_analysis_log('etf_analysis', {
                'etf_positions': len(etf_positions),
                'alerts': len([m for m in metrics if m.risk_level() == 'alert']),
                'warns': len([m for m in metrics if m.risk_level() == 'warn']),
            })
        except Exception as exc:
            logger.error("ETF 분석 실패 (%s): %s", self.broker_name, exc)
        return metrics

    # ------------------------------------------------------------------
    # 거래 통계 요약
    # ------------------------------------------------------------------

    def get_trade_summary(self) -> Dict[str, Any]:
        """거래 통계 + 오늘 거래 + 미체결 통합 요약."""
        try:
            stats = {}
            if hasattr(self.adapter, 'get_trading_stats'):
                stats = self.adapter.get_trading_stats() or {}

            history: List[Dict] = []
            if hasattr(self.adapter, 'get_trade_history'):
                try:
                    history = self.adapter.get_trade_history(limit=500) or []
                except Exception:
                    history = []

            synced_count = self.sync_recent_trades_to_recorder(limit=500)

            today_trades: List[Dict] = []
            if hasattr(self.adapter, 'get_today_trades'):
                try:
                    today_trades = self.adapter.get_today_trades() or []
                except Exception:
                    pass

            open_orders: List[Dict] = []
            if hasattr(self.adapter, 'get_open_orders'):
                try:
                    open_orders = self.adapter.get_open_orders() or []
                except Exception:
                    pass

            summary = {
                'broker': self.broker_name,
                'total_trades': stats.get('total_trades', 0),
                'buy_count': stats.get('buy_count', 0),
                'sell_count': stats.get('sell_count', 0),
                'today_count': len(today_trades),
                'open_orders_count': len(open_orders),
                'realized_pnl': float(stats.get('realized_pnl', 0)),
                'today_trades': today_trades,
                'open_orders': open_orders,
                'synced_trades': synced_count,
                'status': stats.get('status', 'ok'),
            }

            # 브로커/자산유형 집계를 DB에 저장 (대시보드 DB 우선 표시용)
            self._persist_stock_trade_stats(history)

            self._emit_analysis_log('trade_summary', {
                'today_count': summary.get('today_count', 0),
                'open_orders_count': summary.get('open_orders_count', 0),
                'realized_pnl': summary.get('realized_pnl', 0),
                'synced_trades': summary.get('synced_trades', 0),
            })

            self._persist_xai_decision(
                symbol=f"{self.broker_name}_PORTFOLIO",
                decision_type='stock_trade_summary',
                payload={
                    'broker': self.broker_name,
                    'reasoning': (
                        f"today={summary.get('today_count', 0)}, open_orders={summary.get('open_orders_count', 0)}, "
                        f"realized_pnl={summary.get('realized_pnl', 0)}, synced={summary.get('synced_trades', 0)}"
                    ),
                    'confidence': 0.7,
                    'validation': {
                        'status': summary.get('status', 'ok'),
                        'source': 'adapter+recorder_sync',
                    },
                    'summary': summary,
                },
            )
            return summary
        except Exception as exc:
            logger.error("거래 요약 실패 (%s): %s", self.broker_name, exc)
            return {'broker': self.broker_name, 'error': str(exc)}

    # ------------------------------------------------------------------
    # AI 어시스턴트 컨텍스트 생성
    # ------------------------------------------------------------------

    def build_ai_context(self, asset_mode: str = 'all') -> str:
        """
        AI 어시스턴트에 주입할 증권 컨텍스트 문자열 생성.

        Returns:
            멀티라인 한국어 컨텍스트 문자열
        """
        lines: List[str] = []
        normalized_mode = normalize_asset_mode(asset_mode)
        mode_kr = {'all': '통합', 'stock': '주식만', 'etf': 'ETF만'}.get(normalized_mode, '통합')

        try:
            session = get_market_session()
            session_kr = {'pre': '장전', 'open': '장중', 'post': '장후', 'closed': '장외'}.get(session, session)
            lines.append(f"[증권 분석 컨텍스트 — {self.broker_name.upper()} / {datetime.now().strftime('%Y-%m-%d %H:%M')} / {session_kr}]")
            lines.append(f"현재 사용자 보기 모드: {mode_kr}")

            # 포트폴리오 요약
            portfolio = self.get_portfolio_summary(asset_mode=normalized_mode)
            if 'error' not in portfolio:
                lines.append(
                    f"보유종목: {portfolio['count']}개 (ETF {portfolio['etf_count']}개, 주식 {portfolio['stock_count']}개)"
                )
                lines.append(
                    f"총평가금액: {portfolio['total_eval']:,.0f}원 | "
                    f"손익: {portfolio['total_pnl']:+,.0f}원 ({portfolio['total_pnl_rate']:+.2f}%)"
                )
                lines.append(f"예수금: {portfolio['cash']:,.0f}원 | 총자산: {portfolio['total_assets']:,.0f}원")

                if portfolio['risk_items']:
                    risk_names = ', '.join(f"{r['name']}({r['pnl_rate']:+.1f}%)" for r in portfolio['risk_items'])
                    lines.append(f"⚠️ 손익 -5% 이하 위험 종목: {risk_names}")
            else:
                lines.append(f"포트폴리오 조회 실패: {portfolio['error']}")

            # ETF 분석
            etf_metrics = self.get_etf_analysis(asset_mode=normalized_mode)
            if etf_metrics:
                lines.append("\n[보유 ETF 분석]")
                for m in etf_metrics:
                    lines.append(f"  • {m.summary()}")
                alert_etfs = [m for m in etf_metrics if m.risk_level() == 'alert']
                warn_etfs = [m for m in etf_metrics if m.risk_level() == 'warn']
                if alert_etfs:
                    lines.append(f"  ⛔ ALERT ETF: {', '.join(m.code for m in alert_etfs)}")
                if warn_etfs:
                    lines.append(f"  ⚠️ WARN ETF: {', '.join(m.code for m in warn_etfs)}")

            # 주식/ETF 분리 점수 요약 (상위 3종목)
            try:
                positions = []
                if hasattr(self.adapter, 'get_positions'):
                    positions = self.adapter.get_positions() or []

                if positions:
                    positions = filter_positions_by_asset_mode(positions, normalized_mode)
                    # 평가금액 기준 상위 종목 3개만 분석해 비용을 제한
                    top_positions = sorted(
                        positions,
                        key=lambda p: float(p.get('eval_amount') or 0),
                        reverse=True,
                    )[:3]

                    scored_lines: List[str] = []
                    for pos in top_positions:
                        symbol = str(pos.get('code') or '').strip()
                        if not symbol:
                            continue
                        analysis = self.analyze_symbol(symbol)
                        if analysis.get('status') != 'ok':
                            continue

                        if analysis.get('is_etf'):
                            detail = analysis.get('etf_score_detail') or {}
                            nav_gap = detail.get('nav_gap')
                            te = detail.get('tracking_error')
                            scored_lines.append(
                                f"  • ETF {analysis.get('name', symbol)}: 점수 {analysis.get('score', 0):.1f} "
                                f"(NAV괴리 {nav_gap if nav_gap is not None else 'N/A'}%, 추적오차 {te if te is not None else 'N/A'})"
                            )
                        else:
                            scored_lines.append(
                                f"  • 주식 {analysis.get('name', symbol)}: 점수 {analysis.get('score', 0):.1f} "
                                f"(모멘텀 {analysis.get('momentum', 0):+.2f}%)"
                            )

                    if scored_lines:
                        lines.append("\n[주식/ETF 분리 점수]")
                        lines.extend(scored_lines)
            except Exception:
                pass

            # 거래 요약
            trade_summary = self.get_trade_summary()
            if 'error' not in trade_summary:
                lines.append(
                    f"\n[거래 현황] 오늘 {trade_summary['today_count']}건 | "
                    f"미체결 {trade_summary['open_orders_count']}건 | "
                    f"실현손익 {trade_summary['realized_pnl']:+,.0f}원"
                )

            # 시장 상태 알림
            if session == 'closed':
                lines.append("\n현재 장외 시간입니다. 시세/체결 데이터는 최근 장마감 기준입니다.")
            elif session == 'pre':
                lines.append("\n장전 시간입니다. 시간외 거래가 가능합니다.")

            self._emit_analysis_log('ai_context', {
                'session': session,
                'line_count': len(lines),
                'has_etf_section': bool(etf_metrics),
            })

            self._persist_xai_decision(
                symbol=f"{self.broker_name}_PORTFOLIO",
                decision_type='stock_ai_context',
                payload={
                    'broker': self.broker_name,
                    'reasoning': ' / '.join(lines[:6]),
                    'confidence': 0.65,
                    'validation': {
                        'line_count': len(lines),
                        'session': session,
                    },
                    'service': 'stock_analysis_service',
                },
            )

        except Exception as exc:
            logger.error("AI 컨텍스트 생성 실패: %s", exc)
            lines.append(f"[오류] AI 컨텍스트 생성 실패: {exc}")

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # 종목 상세 분석 (단일 종목)
    # ------------------------------------------------------------------

    def analyze_symbol(self, symbol: str) -> Dict[str, Any]:
        """
        단일 종목/ETF 분석.

        Args:
            symbol: 종목코드

        Returns:
            분석 결과 Dict (점수, 가격, 지표, ETF 메타 포함)
        """
        result: Dict[str, Any] = {'symbol': symbol, 'broker': self.broker_name}
        try:
            info = {}
            if hasattr(self.adapter, 'get_stock_info'):
                info = self.adapter.get_stock_info(symbol) or {}
                if info.get('status') == 'error':
                    raise RuntimeError('stock_info_unavailable:' + str(info.get('error') or 'unknown'))

            price = {}
            if hasattr(self.adapter, 'get_realtime_price'):
                price = self.adapter.get_realtime_price(symbol) or {}
                if price.get('status') == 'error':
                    raise RuntimeError('stock_quote_unavailable:' + str(price.get('error') or 'unknown'))

            current_price = float(price.get('current_price') or info.get('current_price') or 0)
            prev_close = float(info.get('prev_close') or 0)
            volume = float(price.get('volume') or info.get('volume') or 0)
            change_rate = float(price.get('change_rate') or info.get('change_rate') or 0)

            is_etf = bool(info.get('is_etf') or (hasattr(self.adapter, 'is_etf') and self.adapter.is_etf(symbol)))

            # ── 거래 결과 피드백: 해당 종목의 과거 성과를 점수에 반영 ──
            feedback = self._get_recent_trade_feedback(symbol)
            pnl_rate = feedback.get('pnl_rate', 0.0)
            feedback_trade_count = feedback.get('trade_count', 0)
            feedback_win_rate = feedback.get('win_rate', 0.0)

            # ── 현재 시장 레짐 ──
            market_regime = self.get_market_regime()

            # AI 커스텀과 자동검증이 같은 지표 정의를 사용하도록 최대 220개 이력을 확보한다.
            price_history: Optional[List[float]] = None
            if hasattr(self.adapter, 'get_price_history'):
                try:
                    hist = self.adapter.get_price_history(symbol, count=220) or []
                    if hist:
                        price_history = [float(h.get('close') or h) for h in hist if h]
                except Exception:
                    price_history = None

            scored: Dict[str, Any]
            if is_etf:
                tracking_error = info.get('tracking_error')
                if tracking_error is None:
                    tracking_error = price.get('tracking_error')
                expense_ratio = info.get('expense_ratio')
                trade_value = float(info.get('trade_value') or price.get('trade_value') or 0)
                nav = float(info.get('nav') or 0)
                scored = score_etf(
                    current_price=current_price,
                    nav=nav,
                    tracking_error=tracking_error,
                    trade_value=trade_value,
                    expense_ratio=expense_ratio,
                )
                reasoning = (
                    f"ETF 분석: NAV괴리 {scored.get('nav_gap', 0):.3f}%, "
                    f"추적오차 {scored.get('tracking_error') if scored.get('tracking_error') is not None else 'N/A'}%, "
                    f"거래대금 {scored.get('trade_value', 0):,.0f}원 기준 점수화 | "
                    f"시장레짐={market_regime} | "
                    f"과거성과: {feedback_trade_count}건 승률 {feedback_win_rate:.0%} 평균손익 {pnl_rate:+.2f}%"
                )
                analysis_type = 'etf'
                score_model = 'score_etf+regime+feedback'
            else:
                avg_volume = float(info.get('avg_volume') or 0)

                # 외국인/기관 순매수 (어댑터 지원 시 사용)
                foreign_net_buy = float(info.get('foreign_net_buy') or 0.0)
                institutional_net_buy = float(info.get('institutional_net_buy') or 0.0)

                scored = score_stock(
                    current_price,
                    prev_close,
                    volume,
                    avg_volume=avg_volume,
                    pnl_rate=pnl_rate,
                    prices=price_history,
                    foreign_net_buy=foreign_net_buy,
                    institutional_net_buy=institutional_net_buy,
                )
                ma_signal = scored.get('ma_signal', 'none')
                rsi_val = scored.get('rsi')
                net_buy = scored.get('net_buy', 0.0)
                rsi_text = f"RSI {rsi_val:.1f}" if rsi_val is not None else "RSI N/A"
                net_buy_text = f"수급 {net_buy/1e8:+.1f}억" if abs(net_buy) >= 1e6 else "수급 N/A"
                reasoning = (
                    f"주식 분석: 전일 대비 {scored.get('momentum', 0):+.2f}% 모멘텀, "
                    f"MA크로스={ma_signal}, {rsi_text}, {net_buy_text}, "
                    f"거래량 {volume:,.0f} 기준 점수화 | "
                    f"시장레짐={market_regime} | "
                    f"과거성과: {feedback_trade_count}건 승률 {feedback_win_rate:.0%} 평균손익 {pnl_rate:+.2f}%"
                )
                analysis_type = 'stock'
                score_model = 'score_stock+ma+rsi+flow+regime+feedback'

            result.update({
                'name': info.get('name', symbol),
                'market': info.get('market', ''),
                'current_price': current_price,
                'change_rate': change_rate,
                'volume': volume,
                'prev_close': prev_close,
                'score': scored['score'],
                'momentum': scored.get('momentum', 0.0),
                'is_etf': is_etf,
                'analysis_type': analysis_type,
                'score_model': score_model,
                'reasoning': reasoning,
                'status': 'ok',
                # ── AI 컨텍스트 확장 필드 ──
                'market_regime': market_regime,
                'feedback_pnl_rate': pnl_rate,
                'feedback_win_rate': feedback_win_rate,
                'feedback_trade_count': feedback_trade_count,
            })
            if price_history:
                from trading.custom_strategy_validator import build_indicator_context
                indicator_context = build_indicator_context(price_history)
                for key in (
                    'rsi', 'macd', 'macd_signal', 'macd_histogram',
                    'bb_position', 'bb_width',
                    'ma20', 'ma50', 'ma200', 'sma20', 'sma50', 'sma200',
                    'ema20', 'ema50', 'ema200', 'adx', 'atr', 'atr_percent',
                    'trend_strength', 'market_volatility',
                    'volume_sma20', 'volume_ratio',
                ):
                    if key in indicator_context:
                        result[key] = indicator_context[key]

            # ETF 추가 지표
            if result['is_etf']:
                etf_info = info  # 어댑터 get_stock_info에서 ETF 메타 포함 여부 활용
                metrics = ETFMetrics(
                    code=symbol,
                    name=result['name'],
                    nav=float(etf_info.get('nav') or 0),
                    current_price=current_price,
                    tracking_error=etf_info.get('tracking_error'),
                    trade_value=float(etf_info.get('trade_value') or 0),
                    base_index=str(etf_info.get('base_index') or ''),
                )
                result['etf'] = metrics.to_dict()
                result['etf_risk'] = metrics.risk_level()
                result['etf_score_detail'] = {
                    'nav_gap': scored.get('nav_gap'),
                    'tracking_error': scored.get('tracking_error'),
                    'trade_value': scored.get('trade_value'),
                    'expense_ratio': scored.get('expense_ratio'),
                }

            self._emit_analysis_log('analyze_symbol', {
                'symbol': symbol,
                'score': result.get('score', 0),
                'is_etf': result.get('is_etf', False),
                'status': result.get('status', 'unknown'),
            })

            self._persist_analysis_snapshot(result)
            self._persist_xai_decision(
                symbol=symbol,
                decision_type='stock_analyze_symbol',
                payload={
                    'broker': self.broker_name,
                    'symbol': symbol,
                    'market': result.get('market'),
                    'is_etf': bool(result.get('is_etf', False)),
                    'signal': ('LONG' if self._to_float(result.get('score')) >= 70 and self._to_float(result.get('momentum')) >= 0
                               else 'SHORT' if self._to_float(result.get('score')) <= 30 and self._to_float(result.get('momentum')) < 0 else 'HOLD'),
                    'rsi': result.get('rsi'),
                    'macd': result.get('macd'),
                    'trend': ('up' if self._to_float(result.get('momentum')) > 0 else 'down' if self._to_float(result.get('momentum')) < 0 else 'flat'),
                    'reasoning': (
                        f"score={result.get('score', 0)}, momentum={result.get('momentum', 0)}, "
                        f"is_etf={result.get('is_etf', False)}, market={result.get('market', '')}"
                    ),
                    'confidence': max(0.0, min(1.0, self._to_float(result.get('score')) / 100.0)),
                    'validation': {
                        'status': result.get('status', 'unknown'),
                        'has_etf_detail': bool(result.get('etf')),
                    },
                    'result': {
                        'score': result.get('score'),
                        'current_price': result.get('current_price'),
                        'change_rate': result.get('change_rate'),
                    },
                },
            )

        except Exception as exc:
            logger.error("종목 분석 실패 (%s / %s): %s", self.broker_name, symbol, exc)
            result['status'] = 'error'
            result['error'] = str(exc)

        return result

    def evaluate_trade_signal(
        self,
        analysis_result: Dict[str, Any],
        buy_threshold: float = 70.0,
        sell_threshold: float = 30.0,
    ) -> str:
        """분석 결과를 BUY/SELL/HOLD 신호로 변환한다.

        ETF와 주식은 서로 다른 신호 판단 기준을 사용한다.
        - 주식: score(모멘텀/수익률 기반) + momentum 방향 결합
        - ETF : NAV 괴리율 + 추적오차 기반 위험도 우선 평가 →
                위험(alert)이면 SELL, 안전(ok) + 점수 양호 시 BUY
        """
        is_etf = bool(analysis_result.get('is_etf', False))

        if is_etf:
            # ETF 전용 신호: NAV 괴리율 / 추적오차 위험 수준 우선
            etf_risk = str(analysis_result.get('etf_risk', 'ok')).lower()
            if etf_risk == 'alert':
                return 'SELL'
            score = self._to_float(analysis_result.get('score'))
            if etf_risk == 'ok' and score >= float(buy_threshold):
                return 'BUY'
            return 'HOLD'

        # 주식 신호: 기술분석 기반 score + momentum 방향
        score = self._to_float(analysis_result.get('score'))
        momentum = self._to_float(analysis_result.get('momentum'))

        if score >= float(buy_threshold) and momentum >= 0:
            return 'BUY'
        if score <= float(sell_threshold) and momentum < 0:
            return 'SELL'
        return 'HOLD'

    def _insert_auto_trade_log(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        score: float,
        momentum: float,
        *,
        asset_class: str = 'stock',
        execution_mode: str = 'live',
        order_result: Optional[Dict[str, Any]] = None,
        close_reason: str = '',
        strategy_key: Optional[str] = None,
        strategy_version_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """자동매매 체결을 포지션 생명주기로 저장하고 KPI를 전송한다."""
        recorder = self._get_recorder()
        if recorder is None:
            return None

        try:
            from trading.recorder import TradeLog
        except Exception:
            return None

        try:
            side_upper = str(side or '').upper()
            result = order_result if isinstance(order_result, dict) else {}
            order_id = (
                result.get('order_id')
                or result.get('orderId')
                or result.get('id')
                or result.get('odno')
            )
            filled_price = self._to_float(
                result.get('filled_price', result.get('price', price)),
                default=price,
            )
            execution_fee = max(0.0, self._to_float(
                result.get('fee', result.get('fees', result.get('commission', 0.0)))
            ))
            execution_tax = max(0.0, self._to_float(
                result.get('tax', result.get('transaction_tax', result.get('securities_tax', 0.0)))
            ))
            execution_cost = execution_fee + execution_tax
            event_at = utc_now()
            reason = (
                close_reason
                or f'stock_auto_{side_upper.lower()}_score_{score:.1f}_mom_{momentum:+.2f}'
            )

            if side_upper == 'BUY':
                log_row = TradeLog(
                    id=None,
                    symbol=symbol,
                    entry_price=filled_price,
                    exit_price=None,
                    quantity=quantity,
                    leverage=1,
                    pnl=None,
                    pnl_percent=None,
                    entry_time=event_at,
                    exit_time=None,
                    reason=reason,
                    side='LONG',
                    tp_price=None,
                    sl_price=None,
                    fees=execution_cost,
                    slippage=0.0,
                    exchange=self.broker_name,
                    order_id=str(order_id) if order_id not in (None, '') else None,
                    fee_asset='KRW',
                    fee_source='broker_execution' if execution_cost > 0 else 'broker_not_reported',
                    position_owner='noahai',
                    execution_mode=execution_mode,
                    entry_fee=execution_cost,
                    entry_fee_asset='KRW',
                    settlement_currency='KRW',
                    pnl_source='pending_broker_close',
                    reconciliation_status='open',
                    strategy_key=strategy_key,
                    strategy_version_id=strategy_version_id,
                )
                inserted_id = recorder.insert_trade_log(log_row)
                entry_identity = order_id or f'trade-log:{inserted_id}'
                position_id = make_position_id(
                    venue=self.broker_name,
                    symbol=symbol,
                    opened_at=event_at,
                    entry_order_id=entry_identity,
                )
                emitted, position_id = emit_position_opened(
                    asset_class=asset_class,
                    venue=self.broker_name,
                    symbol=symbol,
                    side='LONG',
                    opened_at=event_at,
                    entry_price=filled_price,
                    quantity=quantity,
                    position_id=position_id,
                    entry_order_id=entry_identity,
                    execution_mode=execution_mode,
                    source='noahai_client_stock_position',
                )
                return {
                    'event': 'opened',
                    'position_id': position_id,
                    'emitted': emitted,
                    'trade_log_id': inserted_id,
                }

            open_rows = recorder.execute_query(
                """
                SELECT id, entry_price, quantity, entry_time, order_id,
                       COALESCE(entry_fee, fees, 0), strategy_key, strategy_version_id
                FROM trade_log
                WHERE symbol = ?
                  AND exchange = ?
                  AND side = 'LONG'
                  AND exit_time IS NULL
                ORDER BY entry_time ASC, id ASC
                """,
                (symbol, self.broker_name),
            )
            if not open_rows:
                logger.warning(
                    "주식 포지션 종료 KPI 보류: %s %s의 검증 가능한 진입 로그가 없습니다.",
                    self.broker_name,
                    symbol,
                )
                return None

            quantity_to_close = float(quantity)
            lifecycle_events: List[Dict[str, Any]] = []
            for (
                trade_id,
                entry_price,
                open_quantity,
                opened_at_raw,
                entry_order_id,
                entry_fees,
                entry_strategy_key,
                entry_strategy_version_id,
            ) in open_rows:
                if quantity_to_close <= 1e-9:
                    break
                opened_at = as_utc(opened_at_raw)
                if opened_at is None or float(open_quantity or 0.0) <= 0:
                    continue

                close_quantity = min(quantity_to_close, float(open_quantity))
                remaining_quantity = max(0.0, float(open_quantity) - close_quantity)
                quantity_to_close -= close_quantity
                gross_pnl = (filled_price - float(entry_price)) * close_quantity
                fee_ratio = close_quantity / float(open_quantity)
                allocated_entry_fee = float(entry_fees or 0.0) * fee_ratio
                remaining_entry_fee = max(0.0, float(entry_fees or 0.0) - allocated_entry_fee)
                allocated_exit_fee = execution_cost * (close_quantity / float(quantity)) if float(quantity or 0.0) > 0 else 0.0
                net_pnl = gross_pnl - allocated_entry_fee - allocated_exit_fee
                notional = float(entry_price) * close_quantity
                pnl_percent = net_pnl / notional * 100.0 if notional > 0 else 0.0
                entry_identity = entry_order_id or f'trade-log:{trade_id}'
                position_id = make_position_id(
                    venue=self.broker_name,
                    symbol=symbol,
                    opened_at=opened_at,
                    entry_order_id=entry_identity,
                )
                if not position_id:
                    continue

                if remaining_quantity <= 1e-9:
                    recorder.execute_query(
                        """
                        UPDATE trade_log
                        SET exit_price = ?, exit_time = ?, pnl = ?, pnl_percent = ?,
                            reason = ?, exit_order_id = ?, gross_pnl = ?, net_pnl = ?,
                            entry_fee = ?, exit_fee = ?, fees = ?, fee_asset = 'KRW',
                            entry_fee_asset = 'KRW', exit_fee_asset = 'KRW',
                            fee_source = 'broker_execution', settlement_currency = 'KRW',
                            pnl_source = 'broker_lot_accounting',
                            reconciliation_status = 'broker_order_linked'
                        WHERE id = ?
                        """,
                        (
                            filled_price,
                            event_at.isoformat(),
                            net_pnl,
                            pnl_percent,
                            reason,
                            str(order_id) if order_id not in (None, '') else None,
                            gross_pnl,
                            net_pnl,
                            allocated_entry_fee,
                            allocated_exit_fee,
                            allocated_entry_fee + allocated_exit_fee,
                            trade_id,
                        ),
                    )
                    emitted = emit_position_closed(
                        asset_class=asset_class,
                        venue=self.broker_name,
                        symbol=symbol,
                        side='LONG',
                        opened_at=opened_at,
                        closed_at=event_at,
                        entry_price=float(entry_price),
                        exit_price=filled_price,
                        closed_quantity=close_quantity,
                        close_reason=reason,
                        position_id=position_id,
                        entry_order_id=entry_identity,
                        exit_order_id=order_id,
                        execution_mode=execution_mode,
                        source='noahai_client_stock_position',
                        gross_pnl=gross_pnl,
                        net_pnl=net_pnl,
                        fees=allocated_entry_fee + allocated_exit_fee,
                    )
                    lifecycle_events.append(
                        {'event': 'closed', 'position_id': position_id, 'emitted': emitted}
                    )
                    continue

                recorder.execute_query(
                    "UPDATE trade_log SET quantity = ?, fees = ?, entry_fee = ? WHERE id = ?",
                    (remaining_quantity, remaining_entry_fee, remaining_entry_fee, trade_id),
                )
                closed_lot = TradeLog(
                    id=None,
                    symbol=symbol,
                    entry_price=float(entry_price),
                    exit_price=filled_price,
                    quantity=close_quantity,
                    leverage=1,
                    pnl=net_pnl,
                    pnl_percent=pnl_percent,
                    entry_time=opened_at,
                    exit_time=event_at,
                    reason=reason,
                    side='LONG',
                    tp_price=None,
                    sl_price=None,
                    fees=allocated_entry_fee + allocated_exit_fee,
                    slippage=0.0,
                    exchange=self.broker_name,
                    order_id=str(entry_order_id) if entry_order_id not in (None, '') else None,
                    exit_order_id=str(order_id) if order_id not in (None, '') else None,
                    fee_asset='KRW',
                    fee_source='broker_execution',
                    position_owner='noahai',
                    execution_mode=execution_mode,
                    gross_pnl=gross_pnl,
                    net_pnl=net_pnl,
                    entry_fee=allocated_entry_fee,
                    exit_fee=allocated_exit_fee,
                    entry_fee_asset='KRW',
                    exit_fee_asset='KRW',
                    settlement_currency='KRW',
                    pnl_source='broker_lot_accounting',
                    reconciliation_status='broker_order_linked',
                    strategy_key=entry_strategy_key,
                    strategy_version_id=entry_strategy_version_id,
                )
                recorder.insert_trade_log(closed_lot)
                emitted = emit_position_reduced(
                    asset_class=asset_class,
                    venue=self.broker_name,
                    symbol=symbol,
                    side='LONG',
                    opened_at=opened_at,
                    event_at=event_at,
                    closed_quantity=close_quantity,
                    remaining_quantity=remaining_quantity,
                    position_id=position_id,
                    exit_order_id=order_id,
                    execution_mode=execution_mode,
                    source='noahai_client_stock_position',
                    extra={
                        'entry_price': float(entry_price),
                        'exit_price': filled_price,
                        'gross_pnl': gross_pnl,
                        'close_reason': reason,
                    },
                )
                lifecycle_events.append(
                    {'event': 'reduced', 'position_id': position_id, 'emitted': emitted}
                )

            if quantity_to_close > 1e-9:
                logger.warning(
                    "주식 포지션 종료 일부 미연결: %s %s 수량 %.8f",
                    self.broker_name,
                    symbol,
                    quantity_to_close,
                )
            return {
                'event': 'sell',
                'events': lifecycle_events,
                'unmatched_quantity': max(0.0, quantity_to_close),
            }
        except Exception as exc:
            logger.warning("주식 포지션 생명주기 기록 실패 (%s %s): %s", self.broker_name, symbol, exc)
            return None

    def _get_recent_trade_samples(self, limit: int = 50) -> List[Dict[str, Any]]:
        """최근 체결/거래 샘플을 수집한다."""
        merged: List[Dict[str, Any]] = []
        try:
            if hasattr(self.adapter, 'get_today_trades'):
                merged.extend(self.adapter.get_today_trades() or [])
        except Exception:
            pass

        try:
            if hasattr(self.adapter, 'get_trade_history'):
                merged.extend(self.adapter.get_trade_history(limit=limit) or [])
        except Exception:
            pass

        dedup: Dict[str, Dict[str, Any]] = {}
        for trade in merged:
            symbol = str(trade.get('symbol') or trade.get('code') or '').strip()
            side = str(trade.get('side') or '').strip().upper()
            ts = str(trade.get('timestamp') or trade.get('filled_at') or trade.get('time') or trade.get('order_time') or '').strip()
            qty = str(trade.get('quantity') or trade.get('filled_quantity') or trade.get('qty') or '').strip()
            price = str(trade.get('filled_price') or trade.get('price') or '').strip()
            key = f"{symbol}|{side}|{ts}|{qty}|{price}"
            dedup[key] = trade
        return list(dedup.values())[-limit:]

    def _extract_trade_pnl(self, trade: Dict[str, Any]) -> float:
        """거래 dict에서 손익 값을 안전하게 추출한다."""
        return self._to_float(
            trade.get('net_pnl', trade.get('pnl', trade.get('realized_pnl', trade.get('profit', 0.0)))),
            default=0.0,
        )

    def _evaluate_auto_trade_risk_guard(
        self,
        *,
        symbol: str,
        auto_risk_policy: Optional[Dict[str, Any]] = None,
        execution_mode: str = '',
    ) -> Dict[str, Any]:
        """증권 자동매매용 손실/쿨다운 가드레일 평가."""
        policy = dict(auto_risk_policy or {})
        if not bool(policy.get('risk_guard_enabled', False)):
            return {'allowed': True, 'reasons': []}

        reasons: List[str] = []
        max_consecutive_losses = max(1, int(policy.get('max_consecutive_losses', 3) or 3))
        daily_max_loss = max(0.0, float(policy.get('daily_max_loss', 0.0) or 0.0))
        cooldown_sec = max(0, int(policy.get('cooldown_sec_per_symbol', 0) or 0))

        stats: Dict[str, Any] = {}
        if execution_mode in {ExecutionMode.PAPER.value, ExecutionMode.LEARNING.value}:
            recent_trades = self._get_recent_paper_trade_samples(limit=100000)
            today = datetime.now().date()
            day_trades = [row for row in recent_trades if (self._parse_trade_time(row.get('timestamp')) or datetime.min).date() == today]
            stats = {'realized_pnl': sum(self._extract_trade_pnl(row) for row in day_trades)}
        else:
            try:
                if hasattr(self.adapter, 'get_trading_stats'):
                    stats = self.adapter.get_trading_stats() or {}
            except Exception:
                stats = {}
            recent_trades = self._get_recent_trade_samples(limit=max(20, max_consecutive_losses * 4))
            try:
                pnl_is_finite = math.isfinite(float(stats.get('realized_pnl')))
            except (TypeError, ValueError, OverflowError):
                pnl_is_finite = False
            if stats.get('pnl_verified') is False or not pnl_is_finite:
                return {'allowed': False, 'reasons': ['risk_data_unavailable'], 'metrics': {'pnl_verified': False}}

        realized_pnl = self._to_float(stats.get('realized_pnl', 0.0), default=0.0)
        if daily_max_loss > 0 and realized_pnl <= -daily_max_loss:
            reasons.append(f'daily_loss_limit:{realized_pnl:.0f} <= -{daily_max_loss:.0f}')

        consecutive_losses = 0
        for trade in reversed(recent_trades):
            pnl = self._extract_trade_pnl(trade)
            if pnl < 0:
                consecutive_losses += 1
                continue
            if pnl > 0:
                break
        if consecutive_losses >= max_consecutive_losses:
            reasons.append(f'consecutive_losses:{consecutive_losses} >= {max_consecutive_losses}')

        if cooldown_sec > 0:
            now = datetime.now()
            for trade in reversed(recent_trades):
                trade_symbol = str(trade.get('symbol') or trade.get('code') or '').strip().upper()
                if trade_symbol != str(symbol or '').strip().upper():
                    continue
                trade_time = self._parse_trade_time(
                    trade.get('timestamp') or trade.get('filled_at') or trade.get('time') or trade.get('order_time')
                )
                if trade_time is None:
                    break
                elapsed = (now - trade_time).total_seconds()
                if elapsed < cooldown_sec:
                    reasons.append(f'symbol_cooldown:{int(elapsed)} < {cooldown_sec}')
                break

        return {
            'allowed': len(reasons) == 0,
            'reasons': reasons,
            'metrics': {
                'realized_pnl': realized_pnl,
                'consecutive_losses': consecutive_losses,
                'loss_rate': stats.get('loss_rate'),
                'loss_basis': stats.get('loss_basis', '증권사 당일 실현손익'),
            },
        }

    def _notify_risk_decision(self, decision: Dict[str, Any], execution_mode: str) -> None:
        """Forward evidence, not fabricated PnL/rates; never affect an order."""
        try:
            from trading.notifications import publish_stock_risk_decision
            publish_stock_risk_decision(self.broker_name, execution_mode, decision,
                warning_percent=(getattr(self, 'notification_settings', {}) or {}).get('loss_warning_percent', 5))
        except Exception:
            logger.warning('증권 위험 알림 처리 실패 · 위험 판정은 유지합니다.')

    def _sync_runtime_state_snapshot(self) -> Dict[str, Any]:
        """재시작/순환 시작 시점의 포지션/미체결 스냅샷을 기록한다."""
        positions: List[Dict[str, Any]] = []
        open_orders: List[Dict[str, Any]] = []
        positions_ok = True
        orders_ok = True
        try:
            positions = self._confirmed_positions()
        except Exception:
            positions_ok = False
        try:
            if hasattr(self.adapter, 'get_open_orders'):
                open_orders = self.adapter.get_open_orders() or []
        except Exception:
            orders_ok = False

        snapshot = {
            'positions': len(positions) if positions_ok else None,
            'positions_status': 'success' if positions_ok else 'error',
            'open_orders': len(open_orders) if orders_ok else None,
            'open_orders_status': 'success' if orders_ok else 'error',
        }
        self._persist_xai_decision(
            symbol=f"{self.broker_name}_PORTFOLIO",
            decision_type='stock_runtime_sync',
            payload={
                'broker': self.broker_name,
                'reasoning': f"runtime_sync positions={snapshot['positions']} open_orders={snapshot['open_orders']}",
                'confidence': 0.7,
                'validation': snapshot,
            },
        )
        return snapshot

    def _build_stock_order_idempotency_key(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        price: Optional[float],
        bucket_seconds: int = 120,
    ) -> str:
        bucket = int(datetime.now().timestamp() // max(1, bucket_seconds))
        raw = (
            f"{str(self.broker_name).lower()}|{str(symbol).upper()}|{str(side).upper()}|"
            f"{quantity:.8f}|{str(order_type).upper()}|{(price if price is not None else 'MKT')}|{bucket}"
        )
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]

    @staticmethod
    def _calculate_execution_quality_score(
        *,
        success_rate: float,
        reject_rate: float,
        avg_latency_ms: float,
        avg_slippage_bps: float,
    ) -> float:
        latency_penalty = min(30.0, max(0.0, avg_latency_ms / 40.0))
        slippage_penalty = min(25.0, max(0.0, abs(avg_slippage_bps) / 0.8))
        score = (
            success_rate * 100.0
            - (reject_rate * 40.0)
            - latency_penalty
            - slippage_penalty
        )
        return max(0.0, min(100.0, round(score, 2)))

    def _get_today_order_count(self) -> int:
        """Recorder 기준 당일 주문(진입) 건수를 반환한다."""
        recorder = self._get_recorder()
        if recorder is None:
            return 0

        try:
            rows = recorder.execute_query(
                """
                SELECT COUNT(*)
                FROM trade_log
                WHERE DATE(entry_time) = DATE('now', 'localtime')
                  AND LOWER(COALESCE(exchange, '')) = ?
                """,
                (str(self.broker_name or '').lower(),),
            )
            if not rows:
                return 0
            row = rows[0]
            if isinstance(row, (list, tuple)):
                return int((row[0] if row else 0) or 0)
            if isinstance(row, dict):
                return int((row.get('COUNT(*)') or row.get('count') or 0) or 0)
            return int(row or 0)
        except Exception:
            return 0

    @entry_submission('', stock=True)
    def _place_stock_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float],
        order_type: str,
    ) -> tuple[bool, Dict[str, Any], List[str]]:
        """어댑터 호출 차이를 흡수해 주문을 실행한다."""
        order_result: Any = None
        call_errors: List[str] = []

        try:
            order_result = self.adapter.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                order_type=order_type,
            )
        except TypeError as exc:
            call_errors.append(str(exc))
            try:
                order_result = self.adapter.place_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                )
            except TypeError as exc2:
                call_errors.append(str(exc2))
                try:
                    order_result = self.adapter.place_order(
                        symbol,
                        side,
                        quantity,
                        float(price or 0.0),
                    )
                except Exception as exc3:
                    call_errors.append(str(exc3))
            except Exception as exc2:
                call_errors.append(str(exc2))
        except Exception as exc:
            call_errors.append(str(exc))

        success = False
        normalized_result = order_result if isinstance(order_result, dict) else {}
        if normalized_result:
            normalized_status = str(normalized_result.get('status') or '').strip().lower()
            success = normalized_status not in ('', 'error', 'failed', 'failure')
            if 'success' in normalized_result:
                success = bool(normalized_result.get('success')) and success

        return success, normalized_result, call_errors

    def _run_auto_exit_cycle(
        self,
        *,
        asset_mode: str,
        allow_live_order: bool,
        execution_mode: str,
        remaining_order_budget: int,
        exit_policy: Optional[Dict[str, Any]] = None,
        market_regime: Optional[str] = None,
        paper_cost_policy: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[Dict[str, Any]], int]:
        """보유 포지션에 대해 증권 전용 익절/손절 정책을 적용한다.

        market_regime: run_auto_trade_cycle()에서 감지한 시장 레짐을 그대로 전달.
        bear/volatile 시 SL 자동 축소, bull/trend 시 TP 자동 확대.
        """
        decisions: List[Dict[str, Any]] = []
        executed_orders = 0
        policy = dict(exit_policy or {})
        if not bool(policy.get('enable_exit_policy', False)):
            return decisions, executed_orders

        try:
            from trading.stock_exit_policy import evaluate_stock_position_exit
        except Exception as exc:
            return ([{
                'action': 'SKIP',
                'reason': f'exit_policy_import_error:{exc}',
            }], 0)

        positions: List[Dict[str, Any]] = []
        if execution_mode == ExecutionMode.PAPER.value:
            positions = [dict(value) for value in self._paper_positions().values()]
        else:
            try:
                positions = self._confirmed_positions()
            except Exception:
                return ([{'action': 'SKIP', 'reason': 'exit_positions_unavailable'}], 0)
        positions = filter_positions_by_asset_mode(positions, asset_mode)

        for position in positions:
            if executed_orders >= remaining_order_budget:
                break
            symbol = str(position.get('code') or position.get('symbol') or '').strip().upper()
            quantity = self._to_float(position.get('quantity'), default=0.0)
            if not symbol or quantity <= 0:
                continue

            analysis = self.analyze_symbol(symbol)
            if analysis.get('status') != 'ok':
                decisions.append({
                    'symbol': symbol,
                    'action': 'SKIP',
                    'reason': 'exit_analysis_error',
                })
                continue

            custom_exit_plan = self._restore_custom_exit_plan(symbol)
            custom_exit_result: Dict[str, Any] = {}
            effective_exit_policy = dict(policy)
            effective_exit_regime = market_regime
            if custom_exit_plan:
                settings = dict(custom_exit_plan.get('engine_settings') or {})
                tp_fraction = self._to_float(settings.get('tp_percent'), default=0.0)
                sl_fraction = self._to_float(settings.get('sl_percent'), default=0.0)
                if tp_fraction > 0:
                    effective_exit_policy['take_profit_percent'] = tp_fraction * 100.0
                    effective_exit_policy['etf_take_profit_percent'] = tp_fraction * 100.0
                if sl_fraction > 0:
                    effective_exit_policy['stop_loss_percent'] = sl_fraction * 100.0
                    effective_exit_policy['etf_stop_loss_percent'] = sl_fraction * 100.0
                # 사용자 전략의 TP/SL을 국면 배수로 다시 쓰거나 기본 SELL
                # 신호로 청산하지 않는다. 명시 청산 규칙과 원형 TP/SL만 사용한다.
                effective_exit_policy['use_signal_exit'] = False
                effective_exit_regime = 'range'
                try:
                    from trading.declarative_strategy_engine import DeclarativeStrategyEngine

                    custom_exit_result = DeclarativeStrategyEngine.evaluate_exit(
                        dict(custom_exit_plan.get('rules') or {}),
                        dict(analysis),
                    )
                except Exception as exc:
                    custom_exit_result = {
                        'allowed': False,
                        'reason': f'custom_exit_evaluation_error:{exc}',
                    }

            if custom_exit_result.get('allowed'):
                exit_decision = {
                    'should_exit': True,
                    'reason': (
                        f"custom_exit:{custom_exit_plan.get('strategy_name') or '-'}:"
                        f"{custom_exit_plan.get('strategy_version_id') or '-'}"
                    ),
                    'policy_snapshot': effective_exit_policy,
                    'custom_exit_result': custom_exit_result,
                }
            else:
                exit_decision = evaluate_stock_position_exit(
                    position=position,
                    analysis_result=analysis,
                    policy=effective_exit_policy,
                    market_regime=effective_exit_regime,
                )
                if custom_exit_plan:
                    exit_decision['custom_strategy'] = custom_exit_plan
                    exit_decision['custom_exit_result'] = custom_exit_result
            if not bool(exit_decision.get('should_exit')):
                continue

            if execution_mode == ExecutionMode.LEARNING.value or (
                execution_mode in {ExecutionMode.LIVE.value, 'live_api'} and not bool(allow_live_order)
            ):
                decisions.append({
                    'symbol': symbol,
                    'action': 'SELL',
                    'reason': 'exit_live_order_blocked',
                    'exit_reason': exit_decision.get('reason', ''),
                    'decision_type': 'exit',
                })
                continue

            current_price = self._to_float(analysis.get('current_price'), default=0.0)
            if execution_mode == ExecutionMode.PAPER.value:
                paper_position_before = dict(position)
                success, order_result, call_errors = self._place_paper_stock_order(
                    symbol=symbol,
                    side='SELL',
                    quantity=quantity,
                    price=current_price,
                    order_type='MARKET',
                    asset_class=str(position.get('asset_class') or ('etf' if bool(analysis.get('is_etf')) else 'stock')),
                    cost_policy=paper_cost_policy,
                )
            else:
                success, order_result, call_errors = self._place_stock_order(
                    symbol=symbol,
                    side='SELL',
                    quantity=quantity,
                    price=None,
                    order_type='MARKET',
                )
            if success:
                executed_orders += 1
                if execution_mode == ExecutionMode.PAPER.value:
                    strategy_key = str(
                        paper_position_before.get('custom_strategy_key')
                        or custom_exit_plan.get('strategy_key')
                        or ''
                    )
                    version_id = str(
                        paper_position_before.get('custom_strategy_version_id')
                        or custom_exit_plan.get('strategy_version_id')
                        or ''
                    )
                    self._record_stock_paper_outcome(
                        position_before=paper_position_before,
                        order_result=dict(order_result or {}),
                        strategy_key=strategy_key,
                        version_id=version_id,
                    )
                self._custom_exit_plans().pop(symbol, None)

            decisions.append({
                'symbol': symbol,
                'action': 'SELL',
                'reason': 'exit_policy_triggered',
                'exit_reason': exit_decision.get('reason', ''),
                'success': success,
                'decision_type': 'exit',
                'result': order_result,
                'errors': call_errors,
            })

            self._persist_xai_decision(
                symbol=symbol,
                decision_type='stock_auto_exit_symbol',
                payload={
                    'broker': self.broker_name,
                    'execution_mode': execution_mode,
                    'is_etf': bool(analysis.get('is_etf')),
                    'reason_code': exit_decision.get('reason') or 'auto_exit',
                    'result': order_result if isinstance(order_result, dict) else {},
                    'symbol': symbol,
                    'action': 'SELL',
                    'reasoning': exit_decision.get('reason', ''),
                    'confidence': max(0.0, min(1.0, self._to_float(analysis.get('score')) / 100.0)),
                    'validation': {
                        'success': success,
                        'decision_type': 'exit',
                        'policy': exit_decision.get('policy_snapshot', {}),
                        'errors': call_errors[:2],
                    },
                },
            )

            if execution_mode in {ExecutionMode.LIVE.value, 'live_api'}:
                emit_kpi_event(
                    event_type='trade_order_executed' if success else 'trade_order_failed',
                    category='trade',
                    asset_class='etf' if bool(analysis.get('is_etf')) else 'stock',
                    status='success' if success else 'failed',
                    source='noahai_client_stock_auto_exit',
                    metric_value=float(quantity),
                    metadata={
                        'broker': self.broker_name,
                        'symbol': symbol,
                        'quote_currency': 'KRW',
                        'side': 'SELL',
                        'close': True,
                        'reason': exit_decision.get('reason', ''),
                        'execution_mode': execution_mode,
                        'executed_price': current_price,
                        'notional_estimate': float(quantity) * float(current_price or 0.0),
                    },
                )

            if success and execution_mode in {ExecutionMode.LIVE.value, 'live_api'}:
                self._insert_auto_trade_log(
                    symbol=symbol,
                    side='SELL',
                    quantity=quantity,
                    price=current_price,
                    score=self._to_float(analysis.get('score')),
                    momentum=self._to_float(analysis.get('momentum')),
                    asset_class='etf' if bool(analysis.get('is_etf')) else 'stock',
                    execution_mode=execution_mode,
                    order_result=order_result if isinstance(order_result, dict) else {},
                    close_reason=str(exit_decision.get('reason') or 'exit_policy_triggered'),
                )

        return decisions, executed_orders

    def run_auto_trade_cycle(
        self,
        symbols: List[str],
        quantity: float = 1.0,
        order_type: str = 'MARKET',
        buy_threshold: float = 70.0,
        sell_threshold: float = 30.0,
        asset_mode: str = 'all',
        max_orders: int = 1,
        allow_live_order: bool = False,
        guardrails: Optional[Dict[str, Any]] = None,
        auto_risk_policy: Optional[Dict[str, Any]] = None,
        exit_policy: Optional[Dict[str, Any]] = None,
        custom_strategy_pool: Optional[List[Dict[str, Any]]] = None,
        execution_mode_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """주식/ETF 자동매매 1회 사이클을 실행한다 (신호→주문)."""
        normalized_symbols = [str(s or '').strip().upper() for s in symbols or [] if str(s or '').strip()]
        normalized_symbols = list(dict.fromkeys(normalized_symbols))

        requested_qty = self._to_float(quantity, default=0.0)
        if requested_qty <= 0:
            requested_qty = 1.0

        normalized_order_type = str(order_type or 'MARKET').strip().upper()
        normalized_max_orders = int(max_orders or 1)
        if normalized_max_orders <= 0:
            normalized_max_orders = 1

        adapter_api_type = str(getattr(self.adapter, 'api_type', '') or '').strip().lower()
        requested_mode = str(execution_mode_override or '').strip().lower()
        if requested_mode in {mode.value for mode in ExecutionMode}:
            execution_mode = requested_mode
        elif adapter_api_type == 'mock':
            execution_mode = 'mock'
        else:
            execution_mode = 'live_api'
        from trading.event_contract import execution_mode_key
        self._active_execution_mode = execution_mode_key(execution_mode)
        try:
            setattr(self.adapter, '_noah_execution_mode', self._active_execution_mode)
        except Exception:
            pass
        normalized_asset_mode = normalize_asset_mode(asset_mode)

        # ── api_type/api_version 조합 방어 검증 (실행 경로) ──────────────────
        # 설정 저장 경로뿐 아니라 실행 직전에도 어댑터 api 조합을 재검증한다.
        # ExchangeFactory.create_stock_adapter()가 이미 검증하지만,
        # 직접 어댑터를 주입받은 경우나 설정 재로드 없이 어댑터가 교체된 경우를 방어한다.
        # 단, '등록된 브로커'의 잘못된 조합만 차단한다. 미등록/Mock/테스트 브로커는 건너뜀.
        try:
            from trading.exchanges.exchange_factory import ExchangeFactory, SUPPORTED_API_VERSIONS
            # exchange_name 은 StockExchange.__init__ 에서 항상 설정됨
            # broker_name 폴백은 제외 (exchange_name이 정본 식별자)
            _raw_name = getattr(self.adapter, 'exchange_name', '')
            # Mock 객체가 반환되면 str()이 "<MagicMock ...>"이 됨 → 등록 목록에 없어 자동 스킵
            _broker_name = str(_raw_name or '').strip()
            _api_version = str(getattr(self.adapter, 'api_version', '') or '').strip()
            # SUPPORTED_API_VERSIONS에 등록된 브로커에만 검증 적용 (미등록 스킵)
            if _broker_name in SUPPORTED_API_VERSIONS and adapter_api_type and adapter_api_type != 'mock':
                _ok, _err = ExchangeFactory.validate_stock_broker_api_combo(
                    broker=_broker_name,
                    api_type=adapter_api_type,
                    api_version=_api_version,
                )
                if not _ok:
                    self.log_event('stock_auto_trade', f"[실행 차단] api_type/api_version 조합 오류: {_err}")
                    return {
                        'decisions': [],
                        'executed_orders': 0,
                        'execution_mode': 'blocked',
                        'blocked_reason': f'api_combo_invalid: {_err}',
                    }
        except Exception as _ve:
            self.log_event('stock_auto_trade', f"⚠️ api_type/api_version 실행 경로 검증 오류 (계속): {_ve}")

        # ── 시장 레짐 감지 + 임계값 자동 조정 ──
        # 코인 trader._analyze_market_regime_binance_fast()와 동일한 역할
        market_regime = self.get_market_regime()
        effective_buy_threshold, effective_sell_threshold = adjust_thresholds_by_regime(
            regime=market_regime,
            base_buy=float(buy_threshold),
            base_sell=float(sell_threshold),
        )
        if market_regime != 'range':
            self.log_event(
                'stock_auto_trade',
                f"레짐 조정: {market_regime} → 매수임계={effective_buy_threshold:.1f} "
                f"(기본:{buy_threshold:.1f}), 매도임계={effective_sell_threshold:.1f} (기본:{sell_threshold:.1f})",
            )

        decisions: List[Dict[str, Any]] = []
        executed_orders = 0
        runtime_snapshot = self._sync_runtime_state_snapshot()

        cached_positions: List[Dict[str, Any]] = []
        if execution_mode == ExecutionMode.PAPER.value:
            cached_positions = [dict(value) for value in self._paper_positions().values()]
        else:
            try:
                if hasattr(self.adapter, 'get_positions'):
                    cached_positions = self.adapter.get_positions() or []
            except Exception:
                cached_positions = []
        # PAPER 성과 판단은 PAPER 원장만, LIVE는 증권사 체결만 사용한다.
        # 두 범위를 섞으면 실제 계좌 거래가 가상 전략을 차단하거나 PAPER
        # 수익을 LIVE 성과로 오인할 수 있다.
        if execution_mode == ExecutionMode.PAPER.value:
            cached_recent_trades = self._get_recent_paper_trade_samples(limit=400)
        elif execution_mode == 'mock':
            cached_recent_trades = self._get_recent_trade_samples(limit=400)
        else:
            # Buy/sell executions alone are not completed net-PnL outcomes.
            recorder = getattr(self, 'recorder', None)
            getter = getattr(recorder, 'get_recent_trades', None)
            cached_recent_trades = (
                getter(coin='', exchange=self.broker_name, days=30) or []
                if callable(getter) else []
            )[-400:]
        strategy_performance_context = {
            'recent_win_rate': 0.5,
            'consecutive_losses': 0,
        }
        # Incomplete LIVE windows cannot become a winners-only tuning sample.
        live_performance_complete = execution_mode in (ExecutionMode.PAPER.value, 'mock') or all(
            isinstance(row, dict) and row.get('performance_evidence_ready') is True
            for row in cached_recent_trades
        )
        strategy_performance_context['performance_evidence_complete'] = live_performance_complete
        if cached_recent_trades and live_performance_complete:
            recent_sample = list(cached_recent_trades)[-30:]
            pnl_values: List[float] = []
            for trade in recent_sample:
                if not isinstance(trade, dict):
                    continue
                if trade.get('performance_evidence_ready') is False:
                    continue
                pnl_values.append(
                    self._to_float(
                        trade.get(
                            'pnl_percent',
                            trade.get(
                                'net_pnl_percent',
                                trade.get('realized_pnl', trade.get('net_pnl', trade.get('pnl', 0.0))),
                            ),
                        ),
                        default=0.0,
                    )
                )
            if pnl_values:
                strategy_performance_context['recent_win_rate'] = (
                    sum(1 for pnl in pnl_values if pnl > 0) / len(pnl_values)
                )
                consecutive_losses = 0
                for pnl in reversed(pnl_values):
                    if pnl < 0:
                        consecutive_losses += 1
                    else:
                        break
                strategy_performance_context['consecutive_losses'] = consecutive_losses

        profitability_policy = {}
        strategy_policy = {}
        portfolio_policy = {}
        execution_policy = {}
        ops_policy = {}
        if isinstance(auto_risk_policy, dict):
            profitability_policy = dict(auto_risk_policy.get('profitability_validation', {}) or {})
            strategy_policy = dict(auto_risk_policy.get('strategy_engine', {}) or {})
            portfolio_policy = dict(auto_risk_policy.get('portfolio_orchestration', {}) or {})
            execution_policy = dict(auto_risk_policy.get('execution_optimizer', {}) or {})
            ops_policy = dict(auto_risk_policy.get('ops_automation', {}) or {})
        position_sizing_policy = dict(
            (auto_risk_policy or {}).get('position_sizing_policy', {}) or {}
        )
        normalized_sizing_policy = normalize_position_sizing_policy(
            {'position_sizing_policy': position_sizing_policy},
            quote_currency='KRW',
        )

        # ── ProfitabilityValidator: 거래 수익성 KPI 기반 자동매매 ON/OFF ──
        # 충분한 거래 데이터가 쌓이면 KPI(승률/샤프/MDD)가 기준 미달 시 사이클 차단
        # enabled 기본값 True로 변경 (데이터 없으면 bypass 처리됨)
        effective_profitability_policy = dict(profitability_policy)
        if not effective_profitability_policy:
            effective_profitability_policy = {'enabled': True, 'min_trades': 20}

        profitability_validator = ProfitabilityValidator()
        profitability_report = profitability_validator.evaluate_strategy(
            recent_trades=cached_recent_trades,
            policy=effective_profitability_policy,
        )
        profitability_blocked = bool(
            effective_profitability_policy.get('enabled', True)
            and not bool(profitability_report.get('enabled', True))
            and not bool(profitability_report.get('bypassed', False))
        )

        # ── StrategyEngine: 레짐 필터 + 합의 점수 + 쿨다운 ──
        effective_strategy_policy = dict(strategy_policy)
        if not effective_strategy_policy:
            effective_strategy_policy = {
                'enabled': True,
                'allow_regimes': ['bull', 'range', 'trend'],
                'consensus_threshold': 0.55,
                'cooldown_sec': 300,
            }
        # 레짐 자동 반영: bear/volatile이면 더 보수적
        if market_regime == 'bear':
            effective_strategy_policy['allow_regimes'] = ['range']
            effective_strategy_policy['consensus_threshold'] = 0.70
        elif market_regime == 'volatile':
            effective_strategy_policy['consensus_threshold'] = 0.65

        strategy_engine = StrategyEngine()
        strategy_runtime_state: Dict[str, Any] = {}
        for trade in cached_recent_trades:
            trade_symbol = str(trade.get('symbol') or trade.get('code') or '').strip().upper()
            if not trade_symbol:
                continue
            trade_time = self._parse_trade_time(
                trade.get('timestamp') or trade.get('filled_at') or trade.get('time') or trade.get('order_time')
            )
            if trade_time is None:
                continue
            key = f"last_trade_at::{trade_symbol}"
            if key not in strategy_runtime_state or trade_time > strategy_runtime_state[key]:
                strategy_runtime_state[key] = trade_time

        pre_analyzed: Dict[str, Dict[str, Any]] = {}
        for symbol in normalized_symbols:
            analyzed = self.analyze_symbol(symbol)
            if analyzed.get('status') == 'ok':
                pre_analyzed[symbol] = analyzed

        if execution_mode == ExecutionMode.PAPER.value:
            # 보유 종목은 현재 후보군에서 빠졌더라도 청산 전 평가손익이
            # 멈추면 안 된다. 후보 분석 결과를 재사용하고, 없는 보유 종목만
            # 추가 조회해 4개 증권사 공통 PAPER Position을 갱신한다.
            for held_symbol in list(self._paper_positions()):
                analyzed = pre_analyzed.get(held_symbol)
                if analyzed is None:
                    analyzed = self.analyze_symbol(held_symbol)
                if analyzed.get('status') != 'ok':
                    continue
                mark_price = self._to_float(analyzed.get('current_price'), default=0.0)
                if mark_price > 0:
                    self._refresh_paper_position_valuation(
                        held_symbol,
                        mark_price,
                        auto_risk_policy,
                    )
            cached_positions = [dict(value) for value in self._paper_positions().values()]

        orchestrator = PortfolioOrchestrator()
        allocation_result: Dict[str, Any] = {'allocations': {}, 'portfolio_risk': 0.0, 'risk_scale': 1.0}
        if bool(portfolio_policy.get('enabled', False)):
            total_capital = 0.0
            if execution_mode in {ExecutionMode.PAPER.value, ExecutionMode.LEARNING.value, 'mock'}:
                # PAPER/LEARNING이 실계좌 잔고를 읽으면 검증 수량과 LIVE
                # 자금이 결합된다. 독립 가상 기준자금만 사용한다.
                total_capital = float(normalized_sizing_policy.get('paper_equity') or 0.0)
            else:
                try:
                    balance = self.adapter.get_balance() if hasattr(self.adapter, 'get_balance') else {}
                    if isinstance(balance, dict):
                        total_capital = self._to_float(balance.get('total_assets', balance.get('cash', 0.0)), default=0.0)
                except Exception:
                    total_capital = 0.0

            candidates: List[Dict[str, Any]] = []
            for symbol, analyzed in pre_analyzed.items():
                candidates.append({
                    'symbol': symbol,
                    'asset_class': 'etf' if bool(analyzed.get('is_etf')) else 'stock',
                    'signal_strength': max(0.0, min(1.0, self._to_float(analyzed.get('score'), default=0.0) / 100.0)),
                    'volatility': max(0.005, abs(self._to_float(analyzed.get('momentum'), default=0.0)) / 100.0),
                    'avg_correlation': self._to_float(
                        (portfolio_policy.get('correlation_overrides', {}) or {}).get(symbol, 0.25),
                        default=0.25,
                    ),
                })
            allocation_result = orchestrator.allocate(
                candidates=candidates,
                total_capital=total_capital,
                policy=portfolio_policy,
            )

        execution_attempts = 0
        execution_failures = 0
        latency_samples: List[float] = []
        slippage_samples: List[float] = []

        exit_decisions, exit_orders = self._run_auto_exit_cycle(
            asset_mode=normalized_asset_mode,
            allow_live_order=allow_live_order,
            execution_mode=execution_mode,
            remaining_order_budget=normalized_max_orders,
            exit_policy=exit_policy,
            market_regime=market_regime,
            paper_cost_policy=auto_risk_policy,
        )
        decisions.extend(exit_decisions)
        executed_orders += exit_orders

        for symbol in normalized_symbols:
            if market_regime == 'unknown':
                decisions.append({'symbol': symbol, 'action': 'SKIP', 'reason': 'market_data_unavailable'})
                continue
            if executed_orders >= normalized_max_orders:
                decisions.append({
                    'symbol': symbol,
                    'action': 'SKIP',
                    'reason': 'max_orders_reached',
                })
                continue

            analysis = pre_analyzed.get(symbol) or self.analyze_symbol(symbol)
            if analysis.get('status') != 'ok':
                decisions.append({
                    'symbol': symbol,
                    'action': 'SKIP',
                    'reason': 'analysis_error',
                    'analysis_status': analysis.get('status'),
                    'analysis_error': analysis.get('error', 'unknown'),
                })
                continue

            is_etf = bool(analysis.get('is_etf', False))
            self._instrument_type_cache[symbol] = 'etf' if is_etf else 'stock'
            if not asset_mode_matches(normalized_asset_mode, is_etf):
                decisions.append({
                    'symbol': symbol,
                    'action': 'SKIP',
                    'reason': 'asset_mode_filtered',
                    'asset_mode': normalized_asset_mode,
                    'is_etf': is_etf,
                })
                continue

            signal = self.evaluate_trade_signal(
                analysis_result=analysis,
                buy_threshold=effective_buy_threshold,
                sell_threshold=effective_sell_threshold,
            )
            custom_context = dict(analysis)
            custom_context.update({
                'signal': {'BUY': 'LONG', 'SELL': 'SHORT'}.get(signal, 'HOLD'),
                'confidence': max(0.0, min(1.0, self._to_float(analysis.get('score')) / 100.0)),
                'current_price': self._to_float(analysis.get('current_price')),
                '_strategy_performance': dict(strategy_performance_context),
            })
            observer = getattr(self, 'parallel_paper_observer', None)
            paper_strategy_pool = list(
                getattr(self, 'paper_validation_strategy_pool', []) or []
            )
            from trading.custom_strategy_validator import enrich_advanced_indicator_context
            def strategy_candles(timeframe, limit):
                if timeframe != '1d':
                    raise ValueError('stock_strategy_timeframe_unsupported:' + timeframe)
                getter = getattr(self.adapter, 'get_daily_candles', None)
                if not callable(getter):
                    return []
                from datetime import datetime, timezone, timedelta
                output = []
                for row in getter(symbol, limit) or []:
                    day = datetime.strptime(str(row.get('date') or '').replace('-', ''), '%Y%m%d').replace(tzinfo=timezone(timedelta(hours=9)))
                    output.append({**row, 'timestamp': day.timestamp(),
                                   'close_timestamp': day.replace(hour=15, minute=30).timestamp()})
                return output
            custom_context = enrich_advanced_indicator_context(
                custom_context, list(custom_strategy_pool or []) + paper_strategy_pool, strategy_candles,
            )
            if observer is not None:
                try:
                    observer.observe(
                        target=self.broker_name, symbol=symbol,
                        asset_class='etf' if bool(analysis.get('is_etf')) else 'stock',
                        primary_execution_mode=execution_mode,
                        context=custom_context,
                        strategy_pool=paper_strategy_pool,
                        market_regime=market_regime,
                    )
                except Exception as paper_exc:
                    self.log_event(
                        'stock_auto_trade',
                        f'병행 PAPER 관찰 실패(실주문 영향 없음): {paper_exc}',
                    )
            candidate = evaluate_trade_candidate(
                symbol=symbol,
                context=custom_context,
                strategy_pool=custom_strategy_pool,
                asset_class='stock',
                target=self.broker_name,
                market_regime=market_regime,
            )
            analysis = apply_trade_candidate(analysis, candidate)
            signal = {'LONG': 'BUY', 'SHORT': 'SELL'}.get(candidate.final_signal, 'HOLD')
            position_limit = effective_position_limit(
                (auto_risk_policy or {}).get('max_positions', 3),
                strategy_risk_model=dict(
                    (analysis.get('_custom_strategy_rules') or {}).get('risk_model') or {}
                ),
                performance_limit=(
                    profitability_report.get('max_positions')
                    if profitability_report.get('stage') in {'limited_live_learning', 'recovery_learning', 'validated_adaptive'}
                    else None
                ),
            )
            analysis['_position_limit'] = position_limit
            if signal == 'BUY' and len(cached_positions) >= int(position_limit['effective_max_positions']):
                decisions.append({
                    'symbol': symbol,
                    'action': 'SKIP',
                    'reason': 'effective_position_limit_reached',
                    'position_limit': position_limit,
                })
                continue
            stock_thresholds = resolve_stock_exit_thresholds(
                policy=exit_policy,
                is_etf=is_etf,
                market_regime=candidate.market_regime,
            )
            requested_tp = float(
                candidate.exit_plan.requested_tp_fraction or 0.0
            )
            requested_sl = float(
                candidate.exit_plan.requested_sl_fraction or 0.0
            )
            strategy_exit = bool(
                candidate.exit_plan.strategy_owned
                and requested_tp > 0.0
                and requested_sl > 0.0
            )
            stock_exit_snapshot = build_exit_policy(
                settings={
                    'default_tp': stock_thresholds['fallback_tp_fraction'],
                    'default_sl': stock_thresholds['fallback_sl_fraction'],
                },
                exit_plan=candidate.to_dict().get('exit_plan', {}),
                effective_tp_fraction=(
                    requested_tp
                    if strategy_exit
                    else stock_thresholds['effective_tp_fraction']
                ),
                effective_sl_fraction=(
                    requested_sl
                    if strategy_exit
                    else stock_thresholds['effective_sl_fraction']
                ),
                effective_reason=(
                    'AI 커스텀 전략 원형'
                    if strategy_exit
                    else str(stock_thresholds['reason'])
                ),
                entry_price=analysis.get('current_price', 0.0),
                side=signal,
                asset_class='etf' if is_etf else 'stock',
                target=self.broker_name,
                symbol=symbol,
            )
            analysis['_exit_policy'] = stock_exit_snapshot
            self.log_event(
                'stock_auto_trade',
                (
                    f"{symbol} 후보={candidate.final_signal} 출처={candidate.signal_source} "
                    f"역할={candidate.strategy_role} 전략={candidate.strategy_name or '기본 AI'} "
                    f"버전={candidate.strategy_version_id or '-'} 국면={candidate.market_regime} "
                    f"위험예산={candidate.engine_settings.get('risk_per_trade_percent', '-')} "
                    f"TP={candidate.engine_settings.get('tp_percent', '-')} "
                    f"SL={candidate.engine_settings.get('sl_percent', '-')}"
                ),
            )
            self.log_event(
                'stock_auto_trade',
                f"{symbol} {format_exit_policy(stock_exit_snapshot)}",
            )

            if not candidate.allowed:
                decisions.append({
                    'symbol': symbol,
                    'action': 'SKIP',
                    'reason': 'custom_strategy_not_matched',
                    'custom_strategy': candidate.to_dict(),
                })
                continue

            # 고급 커스텀은 사용자 전략 원형이 주 전략이다. NoahAI 전체
            # 수익성·합의 임계값은 기본/일반 후보에만 적용한다.
            if candidate.requires_noah_strategy_policy and profitability_blocked:
                decisions.append({
                    'symbol': symbol,
                    'action': 'SKIP',
                    'reason': 'profitability_blocked',
                    'profitability_report': profitability_report,
                    'trade_candidate': candidate.to_dict(),
                    'analysis_type': analysis.get('analysis_type'),
                    'score_model': analysis.get('score_model'),
                    'analysis_reasoning': analysis.get('reasoning', ''),
                })
                continue

            if candidate.requires_noah_strategy_policy:
                strategy_allowed, strategy_meta = strategy_engine.should_trade(
                    symbol=symbol,
                    analysis_result=analysis,
                    runtime_state=strategy_runtime_state,
                    policy=effective_strategy_policy,
                )
                if not strategy_allowed:
                    decisions.append({
                        'symbol': symbol,
                        'action': 'SKIP',
                        'reason': 'strategy_blocked',
                        'strategy_reasons': list(strategy_meta.get('reasons') or []),
                        'strategy_regime': strategy_meta.get('regime'),
                        'strategy_candidate_regime': strategy_meta.get('candidate_regime'),
                        'strategy_regime_confidence': strategy_meta.get('regime_confidence'),
                        'strategy_regime_observed_at': strategy_meta.get('regime_observed_at'),
                        'strategy_regime_transition_pending': strategy_meta.get(
                            'regime_transition_pending'
                        ),
                        'strategy_consensus': strategy_meta.get('consensus'),
                        'trade_candidate': candidate.to_dict(),
                        'analysis_type': analysis.get('analysis_type'),
                        'score_model': analysis.get('score_model'),
                        'analysis_reasoning': analysis.get('reasoning', ''),
                    })
                    continue
            if signal == 'HOLD':
                hold_reason = (
                    'custom_strategy_not_matched'
                    if candidate.custom_evaluated and candidate.signal_source == 'custom_blocked'
                    else 'threshold_not_met'
                )
                decisions.append({
                    'symbol': symbol,
                    'action': 'HOLD',
                    'reason': hold_reason,
                    'trade_candidate': candidate.to_dict(),
                    'score': analysis.get('score'),
                    'momentum': analysis.get('momentum'),
                    'analysis_type': analysis.get('analysis_type'),
                    'score_model': analysis.get('score_model'),
                    'analysis_reasoning': analysis.get('reasoning', ''),
                })
                self._persist_xai_decision(
                    symbol=symbol,
                    decision_type='stock_auto_trade_symbol',
                    payload={
                        'broker': self.broker_name,
                        'symbol': symbol,
                        'action': 'HOLD',
                        'reasoning': analysis.get('reasoning', ''),
                        'confidence': max(0.0, min(1.0, self._to_float(analysis.get('score')) / 100.0)),
                        'market_regime': market_regime,
                        'validation': {
                            'reason': hold_reason,
                            'trade_candidate': candidate.to_dict(),
                            'score': analysis.get('score'),
                            'momentum': analysis.get('momentum'),
                            'effective_buy_threshold': effective_buy_threshold,
                            'effective_sell_threshold': effective_sell_threshold,
                            'base_buy_threshold': buy_threshold,
                            'base_sell_threshold': sell_threshold,
                        },
                    },
                )
                continue

            auto_risk_check = self._evaluate_auto_trade_risk_guard(
                symbol=symbol,
                auto_risk_policy=auto_risk_policy,
                execution_mode=execution_mode,
            )
            self._notify_risk_decision(auto_risk_check, execution_mode)
            if not bool(auto_risk_check.get('allowed')):
                reasons = [str(x) for x in (auto_risk_check.get('reasons') or []) if str(x)]
                decisions.append({
                    'symbol': symbol,
                    'action': signal,
                    'reason': 'auto_risk_blocked',
                    'risk_reasons': reasons,
                    'analysis_type': analysis.get('analysis_type'),
                    'score_model': analysis.get('score_model'),
                    'analysis_reasoning': analysis.get('reasoning', ''),
                })
                self._persist_xai_decision(
                    symbol=symbol,
                    decision_type='stock_auto_trade_symbol',
                    payload={
                        'broker': self.broker_name,
                        'symbol': symbol,
                        'action': signal,
                        'reasoning': analysis.get('reasoning', ''),
                        'confidence': max(0.0, min(1.0, self._to_float(analysis.get('score')) / 100.0)),
                        'market_regime': market_regime,
                        'validation': {
                            'reason': 'auto_risk_blocked',
                            'risk_reasons': reasons[:3],
                            'risk_metrics': auto_risk_check.get('metrics', {}),
                            'effective_buy_threshold': effective_buy_threshold,
                            'effective_sell_threshold': effective_sell_threshold,
                        },
                    },
                )
                continue

            governance_check = {'allowed': True, 'reasons': [], 'metrics': {}}
            if isinstance(auto_risk_policy, dict) and bool(auto_risk_policy.get('risk_governance_enabled', False)):
                governance_check = evaluate_stock_risk_governance(
                    symbol=symbol,
                    signal=signal,
                    positions=cached_positions,
                    recent_trades=cached_recent_trades,
                    daily_realized_pnl=self._to_float(
                        (auto_risk_check.get('metrics') or {}).get('realized_pnl', 0.0),
                        default=0.0,
                    ),
                    policy=auto_risk_policy,
                    broker=self.broker_name,
                )
            if not bool(governance_check.get('allowed')):
                self._notify_risk_decision(governance_check, execution_mode)
                reasons = [str(x) for x in (governance_check.get('reasons') or []) if str(x)]
                decisions.append({
                    'symbol': symbol,
                    'action': signal,
                    'reason': 'governance_blocked',
                    'governance_reasons': reasons,
                    'governance_metrics': governance_check.get('metrics', {}),
                    'analysis_type': analysis.get('analysis_type'),
                    'score_model': analysis.get('score_model'),
                    'analysis_reasoning': analysis.get('reasoning', ''),
                })
                self._persist_xai_decision(
                    symbol=symbol,
                    decision_type='stock_auto_trade_symbol',
                    payload={
                        'broker': self.broker_name,
                        'symbol': symbol,
                        'action': signal,
                        'reasoning': analysis.get('reasoning', ''),
                        'confidence': max(0.0, min(1.0, self._to_float(analysis.get('score')) / 100.0)),
                        'market_regime': market_regime,
                        'validation': {
                            'reason': 'governance_blocked',
                            'governance_reasons': reasons[:3],
                            'governance_metrics': governance_check.get('metrics', {}),
                            'effective_buy_threshold': effective_buy_threshold,
                            'effective_sell_threshold': effective_sell_threshold,
                        },
                    },
                )
                continue

            if execution_mode in {ExecutionMode.LIVE.value, 'live_api'} and not bool(allow_live_order):
                order_block_reason = 'live_order_blocked'
                decisions.append({
                    'symbol': symbol,
                    'action': signal,
                    'reason': order_block_reason,
                    'execution_mode': execution_mode,
                    'trade_candidate': candidate.to_dict(),
                    'analysis_type': analysis.get('analysis_type'),
                    'score_model': analysis.get('score_model'),
                    'analysis_reasoning': analysis.get('reasoning', ''),
                })
                self._persist_xai_decision(
                    symbol=symbol,
                    decision_type='stock_auto_trade_symbol',
                    payload={
                        'broker': self.broker_name,
                        'symbol': symbol,
                        'action': signal,
                        'reasoning': analysis.get('reasoning', ''),
                        'confidence': max(0.0, min(1.0, self._to_float(analysis.get('score')) / 100.0)),
                        'market_regime': market_regime,
                        'validation': {
                            'reason': order_block_reason,
                            'execution_mode': execution_mode,
                            'trade_candidate': candidate.to_dict(),
                            'effective_buy_threshold': effective_buy_threshold,
                            'effective_sell_threshold': effective_sell_threshold,
                        },
                    },
                )
                continue

            current_price = self._to_float(analysis.get('current_price'), default=0.0)
            effective_qty = requested_qty
            sizing_plan: Dict[str, Any] = {}
            if normalized_sizing_policy.get('mode') != LEGACY_VENUE and signal == 'BUY':
                account_equity = 0.0
                equity_source = 'unavailable'
                if execution_mode in {ExecutionMode.PAPER.value, ExecutionMode.LEARNING.value, 'mock'}:
                    account_equity = float(normalized_sizing_policy.get('paper_equity') or 0.0)
                    equity_source = 'paper_virtual_equity'
                else:
                    try:
                        balance = self.adapter.get_balance() if hasattr(self.adapter, 'get_balance') else {}
                    except Exception:
                        balance = {}
                    if isinstance(balance, dict):
                        account_equity = self._to_float(
                            balance.get('total_assets', balance.get('cash', 0.0)),
                            default=0.0,
                        )
                    equity_source = 'live_broker_equity' if account_equity > 0 else 'unavailable'
                stop_fraction = float(
                    ((stock_exit_snapshot.get('effective') or {}).get('sl_fraction')) or 0.0
                )
                risk_multiplier = float(profitability_report.get('risk_multiplier', 1.0) or 1.0)
                sizing_plan = calculate_position_sizing(
                    policy=position_sizing_policy,
                    asset_class='etf' if is_etf else 'stock',
                    quote_currency='KRW',
                    account_equity=account_equity,
                    account_equity_source=equity_source,
                    price=current_price,
                    stop_fraction=stop_fraction,
                    requested_leverage=1,
                    leverage_cap=1,
                    fixed_notional=current_price * requested_qty,
                    risk_multiplier=risk_multiplier,
                    market_risk_multiplier=derive_market_risk_multiplier(
                        market_regime=market_regime,
                        volatility_fraction=abs(self._to_float(analysis.get('momentum'), 0.0)) / 100.0,
                    ),
                    contract_size=1.0,
                    strategy_risk_model=dict(
                        (analysis.get('_custom_strategy_rules') or {}).get('risk_model')
                        or {}
                    ),
                )
                analysis['_position_sizing'] = dict(sizing_plan)
                if not bool(sizing_plan.get('allowed')):
                    decisions.append({
                        'symbol': symbol,
                        'action': signal,
                        'reason': 'position_sizing_blocked',
                        'position_sizing': sizing_plan,
                    })
                    continue
                # 국내 주식·ETF 주문은 정수 주식만 허용한다. 소수점 올림은
                # 승인한 계좌 위험을 초과하므로 항상 내림한다.
                effective_qty = float(int(float(sizing_plan.get('target_quantity') or 0.0)))
                if effective_qty < 1.0:
                    decisions.append({
                        'symbol': symbol,
                        'action': signal,
                        'reason': 'account_risk_below_one_share',
                        'position_sizing': sizing_plan,
                    })
                    continue
            if bool(portfolio_policy.get('enabled', False)):
                allocated_qty = orchestrator.quantity_from_allocation(
                    symbol=symbol,
                    price=current_price,
                    fallback_qty=requested_qty,
                    allocation_result=allocation_result,
                )
                effective_qty = (
                    min(effective_qty, allocated_qty)
                    if sizing_plan and effective_qty > 0 and allocated_qty > 0
                    else allocated_qty
                )
                if effective_qty <= 0:
                    decisions.append({
                        'symbol': symbol,
                        'action': signal,
                        'reason': 'portfolio_allocation_blocked',
                        'analysis_type': analysis.get('analysis_type'),
                        'score_model': analysis.get('score_model'),
                        'analysis_reasoning': analysis.get('reasoning', ''),
                    })
                    continue

            custom_position = self._to_float(
                (analysis.get('_custom_engine_settings') or {}).get('position_size'), default=0.0
            )
            if custom_position > 0:
                # 주식 주문 수량을 키우지 않고 사용자 전략 비중을 상한으로만 적용한다.
                effective_qty *= min(1.0, custom_position / 0.10)

            execution_optimizer = ExecutionOptimizer()
            signal_strength = max(0.0, min(1.0, self._to_float(analysis.get('score'), default=0.0) / 100.0))
            spread_bps = self._to_float(execution_policy.get('spread_bps', 8.0), default=8.0)
            volatility = max(0.0, abs(self._to_float(analysis.get('momentum'), default=0.0)) / 100.0)
            selected_order_type = execution_optimizer.choose_order_type(
                preferred=normalized_order_type,
                signal_strength=signal_strength,
                volatility=volatility,
                spread_bps=spread_bps,
            ) if bool(execution_policy.get('enabled', False)) else normalized_order_type

            request_price: Optional[float] = None
            if selected_order_type == 'LIMIT':
                request_price = current_price if current_price > 0 else None

            # 자동매매 경로에서도 수동 주문과 동일한 가드레일을 강제 적용
            try:
                from trading.stock_order_guardrails import evaluate_stock_order_guardrails
                guardrail_check = evaluate_stock_order_guardrails(
                    symbol=symbol,
                    side=signal,
                    quantity=effective_qty,
                    price=(request_price if request_price is not None else (current_price if current_price > 0 else None)),
                    order_type=selected_order_type,
                    broker=self.broker_name,
                    asset_mode=normalized_asset_mode,
                    is_etf=is_etf,
                    daily_order_count=self._get_today_order_count(),
                    guardrails=guardrails,
                )
            except Exception as guardrail_exc:
                guardrail_check = {
                    'allowed': False,
                    'reasons': [f'guardrail_check_error:{guardrail_exc}'],
                }

            if not bool(guardrail_check.get('allowed')):
                self._notify_risk_decision(guardrail_check, execution_mode)
                reasons = [str(x) for x in (guardrail_check.get('reasons') or []) if str(x)]
                decisions.append({
                    'symbol': symbol,
                    'action': signal,
                    'reason': 'guardrail_blocked',
                    'guardrail_reasons': reasons,
                    'analysis_type': analysis.get('analysis_type'),
                    'score_model': analysis.get('score_model'),
                    'analysis_reasoning': analysis.get('reasoning', ''),
                })
                self._persist_xai_decision(
                    symbol=symbol,
                    decision_type='stock_auto_trade_symbol',
                    payload={
                        'broker': self.broker_name,
                        'symbol': symbol,
                        'action': signal,
                        'reasoning': analysis.get('reasoning', ''),
                        'confidence': max(0.0, min(1.0, self._to_float(analysis.get('score')) / 100.0)),
                        'market_regime': market_regime,
                        'validation': {
                            'reason': 'guardrail_blocked',
                            'guardrail_reasons': reasons[:3],
                            'effective_buy_threshold': effective_buy_threshold,
                            'effective_sell_threshold': effective_sell_threshold,
                        },
                    },
                )
                continue

            multi_venue_policy = normalize_multi_venue_policy(
                dict((auto_risk_policy or {}).get('multi_venue_execution', {}) or {})
            )
            opportunity_coordinator = get_opportunity_coordinator()
            opportunity_auth = opportunity_coordinator.authorize(
                policy=multi_venue_policy,
                asset_class='stock',
                target=self.broker_name,
                symbol=symbol,
                direction=signal,
                quantity=effective_qty,
                price=current_price,
                stop_fraction=float(
                    ((stock_exit_snapshot.get('effective') or {}).get('sl_fraction'))
                    or 0.0
                ),
                strategy_version=candidate.strategy_version_id,
                account_scope=self.broker_name,
                reserve=execution_mode != ExecutionMode.LEARNING.value,
            )
            opportunity_snapshot = opportunity_auth.to_dict()
            if not opportunity_auth.allowed:
                decisions.append({
                    'symbol': symbol,
                    'action': signal,
                    'reason': 'multi_venue_execution_blocked',
                    'opportunity': opportunity_snapshot,
                    'trade_candidate': candidate.to_dict(),
                    'analysis_type': analysis.get('analysis_type'),
                    'score_model': analysis.get('score_model'),
                    'analysis_reasoning': analysis.get('reasoning', ''),
                })
                continue
            effective_qty = opportunity_auth.authorized_quantity
            if opportunity_auth.quantity_factor != 1.0:
                try:
                    split_guardrail = evaluate_stock_order_guardrails(
                        symbol=symbol,
                        side=signal,
                        quantity=effective_qty,
                        price=(
                            request_price
                            if request_price is not None
                            else (current_price if current_price > 0 else None)
                        ),
                        order_type=selected_order_type,
                        broker=self.broker_name,
                        asset_mode=normalized_asset_mode,
                        is_etf=is_etf,
                        daily_order_count=self._get_today_order_count(),
                        guardrails=guardrails,
                    )
                except Exception as split_guardrail_exc:
                    split_guardrail = {
                        'allowed': False,
                        'reasons': [f'split_guardrail_check_error:{split_guardrail_exc}'],
                    }
                if not bool(split_guardrail.get('allowed')):
                    opportunity_coordinator.release(opportunity_auth)
                    decisions.append({
                        'symbol': symbol,
                        'action': signal,
                        'reason': 'multi_venue_split_guardrail_blocked',
                        'guardrail_reasons': list(split_guardrail.get('reasons') or []),
                        'opportunity': opportunity_snapshot,
                        'trade_candidate': candidate.to_dict(),
                    })
                    continue
            if sizing_plan:
                final_notional = float(effective_qty or 0.0) * float(current_price or 0.0)
                stop_fraction = float(
                    ((stock_exit_snapshot.get('effective') or {}).get('sl_fraction'))
                    or 0.0
                )
                sizing_plan.update({
                    'final_quantity': float(effective_qty or 0.0),
                    'final_notional': final_notional,
                    'final_estimated_margin': final_notional,
                    'final_expected_loss_at_stop': final_notional * stop_fraction,
                })
                analysis['_position_sizing'] = dict(sizing_plan)
                self.log_event(
                    'stock_auto_trade',
                    (
                        f"{symbol} 최종 주문 전 자금관리 XAI · 브로커={self.broker_name} "
                        f"예상손실={sizing_plan['final_expected_loss_at_stop']:.2f} KRW "
                        f"Notional={final_notional:.2f} KRW 증거금={final_notional:.2f} KRW "
                        f"레버리지=1x 수량={float(effective_qty or 0.0):.0f} "
                        f"제한={sizing_plan.get('limiting_reasons', [])}"
                    ),
                )
            self.log_event(
                'stock_auto_trade',
                (
                    f"{symbol} 동일기회={opportunity_auth.opportunity_id} "
                    f"실행정책={opportunity_auth.execution_mode} "
                    f"브로커={self.broker_name} 수량계수={opportunity_auth.quantity_factor:.4f} "
                    f"통합예상손실={opportunity_auth.aggregate_estimated_loss:.4f}"
                ),
            )

            idempotency_key = self._build_stock_order_idempotency_key(
                symbol=symbol,
                side=signal,
                quantity=effective_qty,
                order_type=selected_order_type,
                price=request_price,
            )
            recorder = self._get_recorder()
            if recorder is not None and execution_mode == ExecutionMode.LIVE.value:
                try:
                    is_dup = False
                    checker = getattr(recorder, 'is_duplicate_stock_order_key', None)
                    if callable(checker):
                        dup_result = checker(
                            broker=self.broker_name,
                            idempotency_key=idempotency_key,
                            within_seconds=120,
                        )
                        is_dup = (dup_result is True)
                except Exception:
                    is_dup = False
                if is_dup:
                    opportunity_coordinator.release(opportunity_auth)
                    decisions.append({
                        'symbol': symbol,
                        'action': signal,
                        'reason': 'duplicate_order_guard',
                        'idempotency_key': idempotency_key,
                        'analysis_type': analysis.get('analysis_type'),
                        'score_model': analysis.get('score_model'),
                        'analysis_reasoning': analysis.get('reasoning', ''),
                    })
                    continue

            if execution_mode == ExecutionMode.LEARNING.value:
                trade_plan = {
                    'broker': self.broker_name,
                    'symbol': symbol,
                    'signal': signal,
                    'quantity': effective_qty,
                    'reference_price': current_price,
                    'order_type': selected_order_type,
                    'request_price': request_price,
                    'strategy': candidate.strategy_name or '기본 AI',
                    'strategy_version': candidate.strategy_version_id,
                    'candidate_source': candidate.signal_source,
                    'exit_plan': candidate.to_dict().get('exit_plan', {}),
                    'order_validation_passed': True,
                    'opportunity': opportunity_snapshot,
                    'position_sizing': sizing_plan,
                }
                decisions.append({
                    'symbol': symbol,
                    'action': signal,
                    'reason': 'learning_order_blocked_after_full_pipeline',
                    'execution_mode': execution_mode,
                    'trade_candidate': candidate.to_dict(),
                    'trade_plan': trade_plan,
                    'analysis_type': analysis.get('analysis_type'),
                    'score_model': analysis.get('score_model'),
                    'analysis_reasoning': analysis.get('reasoning', ''),
                })
                self._persist_xai_decision(
                    symbol=symbol,
                    decision_type='stock_auto_trade_symbol',
                    payload={
                        'broker': self.broker_name,
                        'symbol': symbol,
                        'action': signal,
                        'reasoning': analysis.get('reasoning', ''),
                        'confidence': max(
                            0.0,
                            min(1.0, self._to_float(analysis.get('score')) / 100.0),
                        ),
                        'market_regime': market_regime,
                        'validation': {
                            'reason': 'learning_order_blocked_after_full_pipeline',
                            'execution_mode': execution_mode,
                            'trade_candidate': candidate.to_dict(),
                            'trade_plan': trade_plan,
                            'effective_buy_threshold': effective_buy_threshold,
                            'effective_sell_threshold': effective_sell_threshold,
                        },
                    },
                )
                continue

            execution_attempts += 1
            paper_position_before = dict(self._paper_positions().get(symbol, {})) if execution_mode == ExecutionMode.PAPER.value else {}
            if execution_mode == ExecutionMode.PAPER.value:
                started = pytime.perf_counter()
                success, order_result, call_errors = self._place_paper_stock_order(
                    symbol=symbol,
                    side=signal,
                    quantity=effective_qty,
                    price=current_price,
                    order_type=selected_order_type,
                    asset_class='etf' if is_etf else 'stock',
                    cost_policy=auto_risk_policy,
                )
                latency_ms = (pytime.perf_counter() - started) * 1000.0
                slippage_bps = 0.0
            elif bool(execution_policy.get('enabled', False)):
                success, order_result, call_errors, latency_ms, slippage_bps = execution_optimizer.execute_with_quality_control(
                    place_order_fn=lambda dyn_order_type, dyn_price: self._place_stock_order(
                        symbol=symbol,
                        side=signal,
                        quantity=effective_qty,
                        price=dyn_price,
                        order_type=dyn_order_type,
                    ),
                    order_type=selected_order_type,
                    request_price=request_price,
                    fallback_market=bool(execution_policy.get('fallback_market', True)),
                    max_retries=max(0, int(execution_policy.get('max_retries', 1) or 1)),
                    timeout_ms=max(300, int(execution_policy.get('timeout_ms', 3000) or 3000)),
                    max_slippage_bps=max(0.1, float(execution_policy.get('max_slippage_bps', 35.0) or 35.0)),
                )
            else:
                started = pytime.perf_counter()
                success, order_result, call_errors = self._place_stock_order(
                    symbol=symbol,
                    side=signal,
                    quantity=effective_qty,
                    price=request_price,
                    order_type=selected_order_type,
                )
                latency_ms = (pytime.perf_counter() - started) * 1000.0
                slippage_bps = 0.0

                filled_price = self._to_float(
                    (order_result or {}).get('filled_price', (order_result or {}).get('price', current_price)),
                    default=current_price,
                )
                if request_price is not None and request_price > 0 and filled_price > 0:
                    slippage_bps = ((filled_price - request_price) / request_price) * 10000.0
            latency_samples.append(latency_ms)
            if not success:
                execution_failures += 1
            if request_price is not None and request_price > 0:
                slippage_samples.append(slippage_bps)

            if success:
                opportunity_coordinator.record_result(
                    opportunity_auth,
                    status=(
                        'paper_filled'
                        if execution_mode == ExecutionMode.PAPER.value
                        else 'filled'
                    ),
                    order_id=str(
                        (order_result or {}).get('order_id')
                        or (order_result or {}).get('orderId')
                        or ''
                    ),
                )
                executed_orders += 1
                strategy_runtime_state[f'last_trade_at::{symbol.upper()}'] = datetime.now()
                stock_exit_snapshot = record_insurance_submission(
                    stock_exit_snapshot,
                    status=(
                        'paper_virtual_exit_no_broker_submission'
                        if execution_mode == ExecutionMode.PAPER.value
                        else 'portfolio_monitor_exit_no_broker_insurance_order'
                    ),
                )
                analysis['_exit_policy'] = stock_exit_snapshot
                self.log_event(
                    'stock_auto_trade',
                    f"{symbol} {format_exit_policy(stock_exit_snapshot)}",
                )
                if candidate.strategy_name and signal == 'BUY':
                    self._custom_exit_plans()[symbol] = {
                        'strategy_id': candidate.strategy_id,
                        'strategy_key': candidate.strategy_key,
                        'strategy_version_id': candidate.strategy_version_id,
                        'strategy_name': candidate.strategy_name,
                        'strategy_role': candidate.strategy_role,
                        'operation_mode': candidate.operation_mode,
                        'engine_settings': dict(candidate.engine_settings),
                        'rules': dict(candidate.selected_rules),
                        'exit_plan': candidate.to_dict().get('exit_plan', {}),
                        'market_regime': candidate.market_regime,
                        'exit_policy': dict(stock_exit_snapshot),
                    }
                if execution_mode == ExecutionMode.PAPER.value and signal == 'BUY':
                    paper_position = self._paper_positions().get(symbol)
                    if paper_position is not None:
                        paper_position['custom_strategy_key'] = candidate.strategy_key
                        paper_position['custom_strategy_version_id'] = candidate.strategy_version_id
                        paper_position['custom_strategy_name'] = candidate.strategy_name
                        paper_position['entry_reason'] = str(candidate.reason or '')
                        paper_position['entry_market_regime'] = str(candidate.market_regime or '')
                        paper_position['entry_regime_scope'] = str(candidate.regime_scope or '')
                        paper_position['entry_signal_source'] = str(candidate.signal_source or '')
                        paper_position['position_sizing'] = dict(
                            analysis.get('_position_sizing') or {}
                        )
                        paper_position['leverage'] = 1
                        paper_position['effective_tp_fraction'] = float(
                            candidate.exit_plan.requested_tp_fraction or 0.0
                        ) or None
                        paper_position['effective_sl_fraction'] = float(
                            candidate.exit_plan.requested_sl_fraction or 0.0
                        ) or None
                        paper_position['exit_policy_source'] = str(candidate.exit_plan.source or '')
                        paper_position['exit_policy_reason'] = (
                            'strategy_owned' if candidate.exit_plan.strategy_owned else 'noah_dynamic'
                        )
                elif execution_mode == ExecutionMode.PAPER.value and signal == 'SELL':
                    strategy_key = str(
                        paper_position_before.get('custom_strategy_key')
                        or candidate.strategy_key
                        or ''
                    )
                    version_id = str(
                        paper_position_before.get('custom_strategy_version_id')
                        or candidate.strategy_version_id
                        or ''
                    )
                    self._record_stock_paper_outcome(
                        position_before=paper_position_before,
                        order_result=dict(order_result or {}),
                        strategy_key=strategy_key,
                        version_id=version_id,
                    )
                if execution_mode == ExecutionMode.PAPER.value:
                    self._persist_paper_positions()
                if execution_mode in {ExecutionMode.LIVE.value, 'live_api'}:
                    self._insert_auto_trade_log(
                        symbol=symbol,
                        side=signal,
                        quantity=effective_qty,
                        price=current_price,
                        score=self._to_float(analysis.get('score')),
                        momentum=self._to_float(analysis.get('momentum')),
                        asset_class='etf' if bool(analysis.get('is_etf')) else 'stock',
                        execution_mode=execution_mode,
                        order_result=order_result if isinstance(order_result, dict) else {},
                        strategy_key=candidate.strategy_key,
                        strategy_version_id=candidate.strategy_version_id,
                    )
                if recorder is not None and execution_mode in {ExecutionMode.LIVE.value, 'live_api'}:
                    try:
                        saver = getattr(recorder, 'save_stock_order_idempotency', None)
                        if callable(saver):
                            saver(
                                broker=self.broker_name,
                                idempotency_key=idempotency_key,
                                symbol=symbol,
                                side=signal,
                                order_type=selected_order_type,
                                quantity=effective_qty,
                                price=request_price,
                            )
                    except Exception:
                        pass
            else:
                opportunity_coordinator.release(opportunity_auth)
                opportunity_coordinator.record_result(
                    opportunity_auth,
                    status='failed',
                    detail='; '.join(call_errors[:2]) if call_errors else '',
                )

            if recorder is not None and execution_mode in {ExecutionMode.LIVE.value, 'live_api'}:
                try:
                    metric_saver = getattr(recorder, 'save_stock_execution_metric', None)
                    if callable(metric_saver):
                        metric_saver({
                            'broker': self.broker_name,
                            'symbol': symbol,
                            'side': signal,
                            'order_type': selected_order_type,
                            'execution_mode': execution_mode,
                            'success': success,
                            'latency_ms': latency_ms,
                            'slippage_bps': slippage_bps,
                            'rejection_reason': '; '.join(call_errors[:2]) if call_errors else '',
                            'decision_type': 'entry',
                        })
                except Exception:
                    pass

            asset_class = 'etf' if bool(analysis.get('is_etf')) else 'stock'
            if execution_mode in {ExecutionMode.LIVE.value, 'live_api'}:
                emit_kpi_event(
                    event_type='trade_order_executed' if success else 'trade_order_failed',
                    category='trade',
                    asset_class=asset_class,
                    status='success' if success else 'failed',
                    source='noahai_client_stock_auto',
                    metric_value=float(effective_qty),
                    metadata={
                        'broker': self.broker_name,
                        'symbol': symbol,
                        'quote_currency': 'KRW',
                        'side': signal,
                        'close': bool(signal == 'SELL'),
                        'execution_mode': execution_mode,
                        'order_type': selected_order_type,
                        'score': self._to_float(analysis.get('score')),
                        'reason': '; '.join(call_errors[:2]) if call_errors else '',
                        'executed_price': self._to_float((order_result if isinstance(order_result, dict) else {}).get('price'), default=0.0),
                        'notional_estimate': float(effective_qty) * self._to_float((order_result if isinstance(order_result, dict) else {}).get('price'), default=0.0),
                    },
                )

            decisions.append({
                'symbol': symbol,
                'action': signal,
                'score': analysis.get('score'),
                'momentum': analysis.get('momentum'),
                'analysis_type': analysis.get('analysis_type'),
                'score_model': analysis.get('score_model'),
                'analysis_reasoning': analysis.get('reasoning', ''),
                'success': success,
                'execution_mode': execution_mode,
                'result': order_result if isinstance(order_result, dict) else {},
                'errors': call_errors,
                'latency_ms': round(latency_ms, 2),
                'idempotency_key': idempotency_key,
                'opportunity': opportunity_snapshot,
                'trade_candidate': candidate.to_dict(),
                'position_sizing': sizing_plan,
            })

            self._persist_xai_decision(
                symbol=symbol,
                decision_type='stock_auto_trade_symbol',
                payload={
                    'broker': self.broker_name,
                    'symbol': symbol,
                    'action': signal,
                    'reasoning': analysis.get('reasoning', ''),
                    'confidence': max(0.0, min(1.0, self._to_float(analysis.get('score')) / 100.0)),
                    'validation': {
                        'success': success,
                        'execution_mode': execution_mode,
                        'errors': call_errors[:2],
                        'opportunity': opportunity_snapshot,
                        'trade_candidate': candidate.to_dict(),
                        'position_sizing': sizing_plan,
                        'effective_buy_threshold': effective_buy_threshold,
                        'effective_sell_threshold': effective_sell_threshold,
                    },
                    'market_regime': market_regime,
                    'result': order_result if isinstance(order_result, dict) else {},
                },
            )

        avg_latency_ms = (sum(latency_samples) / len(latency_samples)) if latency_samples else 0.0
        avg_slippage_bps = (sum(slippage_samples) / len(slippage_samples)) if slippage_samples else 0.0
        success_rate = (executed_orders / execution_attempts) if execution_attempts > 0 else 0.0
        reject_rate = (execution_failures / execution_attempts) if execution_attempts > 0 else 0.0
        quality_score = self._calculate_execution_quality_score(
            success_rate=success_rate,
            reject_rate=reject_rate,
            avg_latency_ms=avg_latency_ms,
            avg_slippage_bps=avg_slippage_bps,
        )

        ops_engine = OpsAutomationEngine()
        ops_anomalies = ops_engine.detect_anomalies(
            execution_metrics={
                'reject_rate': reject_rate,
                'avg_slippage_bps': avg_slippage_bps,
                'quality_score': quality_score,
            },
            policy=ops_policy,
        )
        rollback_action = ops_engine.build_rollback_action(ops_anomalies, policy=ops_policy)

        summary = {
            'broker': self.broker_name,
            'execution_mode': execution_mode,
            'symbols': normalized_symbols,
            'orders_executed': executed_orders,
            'exit_orders_executed': exit_orders,
            'max_orders': normalized_max_orders,
            'decisions': decisions,
            'market_regime': market_regime,
            'effective_buy_threshold': effective_buy_threshold,
            'effective_sell_threshold': effective_sell_threshold,
            'runtime_snapshot': runtime_snapshot,
            'execution_metrics': {
                'attempted_orders': execution_attempts,
                'failed_orders': execution_failures,
                'success_rate': round(success_rate, 4),
                'reject_rate': round(reject_rate, 4),
                'avg_latency_ms': round(avg_latency_ms, 2),
                'avg_slippage_bps': round(avg_slippage_bps, 2),
                'quality_score': quality_score,
            },
            'profitability_validation': profitability_report,
            'portfolio_allocation': allocation_result,
            'ops_automation': {
                'anomalies': ops_anomalies,
                'rollback_action': rollback_action,
            },
            'status': 'ok',
        }

        summary['daily_briefing'] = ops_engine.build_daily_briefing(summary, ops_anomalies)

        self._emit_analysis_log('auto_trade_cycle', {
            'broker': self.broker_name,
            'symbols': len(normalized_symbols),
            'orders_executed': executed_orders,
            'execution_mode': execution_mode,
            'quality_score': quality_score,
            'market_regime': market_regime,
            'effective_buy_threshold': effective_buy_threshold,
            'effective_sell_threshold': effective_sell_threshold,
        })

        if execution_mode in {ExecutionMode.LIVE.value, 'live_api'}:
            emit_kpi_event(
                event_type='trade_execution_quality',
                category='trade',
                asset_class='stock',
                status='success',
                source='noahai_client_stock_auto',
                metric_value=float(quality_score),
                metadata={
                    'broker': self.broker_name,
                    'execution_mode': execution_mode,
                    'attempted_orders': execution_attempts,
                    'failed_orders': execution_failures,
                    'avg_latency_ms': round(avg_latency_ms, 2),
                    'avg_slippage_bps': round(avg_slippage_bps, 2),
                },
            )

        self._persist_xai_decision(
            symbol=f"{self.broker_name}_PORTFOLIO",
            decision_type='stock_auto_trade_cycle',
            payload={
                'broker': self.broker_name,
                'execution_mode': execution_mode,
                'reasoning': (
                    f"symbols={len(normalized_symbols)}, orders_executed={executed_orders}, "
                    f"execution_mode={execution_mode}, asset_mode={normalized_asset_mode}"
                ),
                'confidence': 0.7,
                'validation': {
                    'buy_threshold': buy_threshold,
                    'sell_threshold': sell_threshold,
                    'effective_buy_threshold': effective_buy_threshold,
                    'effective_sell_threshold': effective_sell_threshold,
                    'market_regime': market_regime,
                    'allow_live_order': bool(allow_live_order),
                },
                'summary': {
                    'orders_executed': executed_orders,
                    'decisions': decisions,
                },
            },
        )

        return summary
