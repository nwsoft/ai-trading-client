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

import logging
import hashlib
import time as pytime
from datetime import datetime, time as dtime, timedelta
from typing import Any, Dict, List, Optional
from log_system.log_adapter import log_event
from api.kpi_client import emit_kpi_event
from trading.stock_risk_governance import evaluate_stock_risk_governance
from trading.execution_optimizer import ExecutionOptimizer
from trading.ops_automation import OpsAutomationEngine
from trading.portfolio_orchestrator import PortfolioOrchestrator
from trading.profitability_validation import ProfitabilityValidator
from trading.strategy_engine import StrategyEngine

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
        'range'   : 횡보장 (나머지)
    """
    try:
        index_symbols = []
        if hasattr(adapter, 'get_index_price'):
            for idx in ('KOSPI', '코스피', '001'):
                try:
                    idx_data = adapter.get_index_price(idx) or {}
                    if idx_data:
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
                        cr = float(p.get('change_rate') or 0)
                        changes.append(cr)
                except Exception:
                    continue
            if not changes:
                return 'range'
            avg_change = sum(changes) / len(changes)
            if avg_change >= 1.5:
                return 'bull'
            if avg_change <= -1.5:
                return 'bear'
            if abs(avg_change) >= 1.0:
                return 'volatile'
            return 'range'

        # 지수 직접 사용
        idx = index_symbols[0]
        change_rate = float(idx.get('change_rate') or idx.get('change_pct') or 0)
        if change_rate >= 1.5:
            return 'bull'
        if change_rate <= -1.5:
            return 'bear'
        if abs(change_rate) >= 1.0:
            return 'volatile'
        return 'range'
    except Exception:
        return 'range'


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

    def __init__(self, adapter: Any, broker_name: str = '', recorder: Optional[Any] = None):
        """
        Args:
            adapter  : StockExchange 인터페이스를 구현한 어댑터 인스턴스
            broker_name : 표시용 이름 (없으면 adapter.broker_name에서 자동 추출)
        """
        self.adapter = adapter
        self.broker_name = broker_name or getattr(adapter, 'broker_name', '') or getattr(adapter, 'exchange_name', 'unknown')
        self.recorder = recorder
        self.log_event = lambda category, msg, level='INFO': log_event(
            category, msg, exchange=self.broker_name, level=level
        )
        # 레짐 캐시: 5분 유효 (코인 trader.py 방식과 동일)
        self._regime_cache: Optional[str] = None
        self._regime_cache_time: float = 0.0
        self._REGIME_CACHE_TTL: float = 300.0

    def _get_recorder(self) -> Optional[Any]:
        """Recorder 인스턴스를 지연 로드한다."""
        if self.recorder is not None:
            try:
                self.recorder.exchange = self.broker_name
            except Exception:
                pass
            return self.recorder

        # 어댑터에 이미 recorder가 연결된 경우 우선 사용
        try:
            adapter_recorder = getattr(self.adapter, 'recorder', None)
            if adapter_recorder is not None:
                try:
                    adapter_recorder.exchange = self.broker_name
                except Exception:
                    pass
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
        if self._regime_cache and (now - self._regime_cache_time) < self._REGIME_CACHE_TTL:
            return self._regime_cache

        regime = detect_market_regime(self.adapter)
        self._regime_cache = regime
        self._regime_cache_time = now

        self.log_event('stock_regime', f"시장 레짐 감지: {regime}")
        self._emit_analysis_log('market_regime', {'regime': regime, 'broker': self.broker_name})
        self._persist_xai_decision(
            symbol='MARKET',
            decision_type='stock_market_regime',
            payload={
                'regime': regime,
                'broker': self.broker_name,
                'reasoning': (
                    f"KOSPI 기반 레짐 분류: {regime} → "
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
        """어댑터 거래내역을 Recorder.trade_log로 동기화한다."""
        recorder = self._get_recorder()
        if recorder is None or not trades:
            return 0

        inserted = 0
        try:
            from trading.recorder import TradeLog
        except Exception:
            return 0

        for trade in trades:
            try:
                symbol = str(trade.get('symbol') or trade.get('code') or '').strip()
                if not symbol:
                    continue

                qty = self._to_float(trade.get('quantity', trade.get('filled_quantity', trade.get('qty', 0.0))))
                price = self._to_float(trade.get('filled_price', trade.get('price', trade.get('current_price', 0.0))))
                if qty <= 0 or price <= 0:
                    continue

                side = self._normalize_side(trade.get('side'))
                trade_time = self._parse_trade_time(
                    trade.get('timestamp') or trade.get('filled_at') or trade.get('time') or trade.get('order_time')
                ) or datetime.now()

                if self._trade_exists(recorder, symbol, side, trade_time, qty, price):
                    continue

                pnl = self._to_float(trade.get('pnl', trade.get('realized_pnl', 0.0)))
                notional = price * qty
                pnl_percent = self._to_float(trade.get('pnl_percent', (pnl / notional * 100.0) if notional > 0 else 0.0))
                fees = self._to_float(trade.get('fee', trade.get('fees', trade.get('commission', 0.0))))

                row = TradeLog(
                    id=None,
                    symbol=symbol,
                    entry_price=price,
                    exit_price=price,
                    quantity=qty,
                    leverage=1,
                    pnl=pnl,
                    pnl_percent=pnl_percent,
                    entry_time=trade_time,
                    exit_time=trade_time,
                    reason='stock_trade_sync',
                    side=side,
                    tp_price=None,
                    sl_price=None,
                    fees=fees,
                    slippage=0.0,
                    exchange=self.broker_name,
                )
                inserted_id = recorder.insert_trade_log(row)
                if inserted_id:
                    inserted += 1
            except Exception:
                continue

        if inserted > 0:
            self._emit_analysis_log('trade_sync', {'broker': self.broker_name, 'inserted': inserted})
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
        """XAI 성격의 의사결정 스냅샷을 ai_decisions에 저장한다."""
        recorder = self._get_recorder()
        if recorder is None:
            return

        try:
            recorder.save_ai_decision(symbol, decision_type, payload)
        except Exception:
            pass

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

            positions = []
            if hasattr(self.adapter, 'get_positions'):
                positions = self.adapter.get_positions() or []

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
            return {'broker': self.broker_name, 'error': str(exc)}

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

            price = {}
            if hasattr(self.adapter, 'get_realtime_price'):
                price = self.adapter.get_realtime_price(symbol) or {}

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

                # 가격 히스토리 (어댑터 지원 시 사용)
                price_history: Optional[List[float]] = None
                if hasattr(self.adapter, 'get_price_history'):
                    try:
                        hist = self.adapter.get_price_history(symbol, count=25) or []
                        if hist:
                            price_history = [float(h.get('close') or h) for h in hist if h]
                    except Exception:
                        price_history = None

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
    ) -> None:
        """자동매매 성공 주문을 trade_log에 즉시 기록한다."""
        recorder = self._get_recorder()
        if recorder is None:
            return

        try:
            from trading.recorder import TradeLog
        except Exception:
            return

        try:
            side_upper = str(side or '').upper()
            trade_side = 'LONG' if side_upper == 'BUY' else 'SHORT'
            log_row = TradeLog(
                id=None,
                symbol=symbol,
                entry_price=price,
                exit_price=price,
                quantity=quantity,
                leverage=1,
                pnl=0.0,
                pnl_percent=None,
                entry_time=datetime.now(),
                exit_time=datetime.now(),
                reason=f'stock_auto_{side_upper.lower()}_score_{score:.1f}_mom_{momentum:+.2f}',
                side=trade_side,
                tp_price=None,
                sl_price=None,
                fees=0.0,
                slippage=0.0,
                exchange=self.broker_name,
            )
            recorder.insert_trade_log(log_row)
        except Exception:
            return

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
            trade.get('pnl', trade.get('realized_pnl', trade.get('profit', 0.0))),
            default=0.0,
        )

    def _evaluate_auto_trade_risk_guard(
        self,
        *,
        symbol: str,
        auto_risk_policy: Optional[Dict[str, Any]] = None,
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
        try:
            if hasattr(self.adapter, 'get_trading_stats'):
                stats = self.adapter.get_trading_stats() or {}
        except Exception:
            stats = {}

        realized_pnl = self._to_float(stats.get('realized_pnl', 0.0), default=0.0)
        if daily_max_loss > 0 and realized_pnl <= -daily_max_loss:
            reasons.append(f'daily_loss_limit:{realized_pnl:.0f} <= -{daily_max_loss:.0f}')

        recent_trades = self._get_recent_trade_samples(limit=max(20, max_consecutive_losses * 4))
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
            },
        }

    def _sync_runtime_state_snapshot(self) -> Dict[str, int]:
        """재시작/순환 시작 시점의 포지션/미체결 스냅샷을 기록한다."""
        positions: List[Dict[str, Any]] = []
        open_orders: List[Dict[str, Any]] = []
        try:
            if hasattr(self.adapter, 'get_positions'):
                positions = self.adapter.get_positions() or []
        except Exception:
            positions = []
        try:
            if hasattr(self.adapter, 'get_open_orders'):
                open_orders = self.adapter.get_open_orders() or []
        except Exception:
            open_orders = []

        snapshot = {
            'positions': len(positions),
            'open_orders': len(open_orders),
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
        try:
            if hasattr(self.adapter, 'get_positions'):
                positions = self.adapter.get_positions() or []
        except Exception:
            positions = []
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

            exit_decision = evaluate_stock_position_exit(
                position=position,
                analysis_result=analysis,
                policy=policy,
                market_regime=market_regime,
            )
            if not bool(exit_decision.get('should_exit')):
                continue

            if execution_mode != 'mock' and not bool(allow_live_order):
                decisions.append({
                    'symbol': symbol,
                    'action': 'SELL',
                    'reason': 'exit_live_order_blocked',
                    'exit_reason': exit_decision.get('reason', ''),
                    'decision_type': 'exit',
                })
                continue

            current_price = self._to_float(analysis.get('current_price'), default=0.0)
            success, order_result, call_errors = self._place_stock_order(
                symbol=symbol,
                side='SELL',
                quantity=quantity,
                price=None,
                order_type='MARKET',
            )
            if success:
                executed_orders += 1

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
                    'side': 'SELL',
                    'reason': exit_decision.get('reason', ''),
                    'execution_mode': execution_mode,
                    'executed_price': current_price,
                    'notional_estimate': float(quantity) * float(current_price or 0.0),
                },
            )

            if success:
                self._insert_auto_trade_log(
                    symbol=symbol,
                    side='SELL',
                    quantity=quantity,
                    price=current_price,
                    score=self._to_float(analysis.get('score')),
                    momentum=self._to_float(analysis.get('momentum')),
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
        execution_mode = 'mock' if adapter_api_type == 'mock' else 'live_api'
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
        try:
            if hasattr(self.adapter, 'get_positions'):
                cached_positions = self.adapter.get_positions() or []
        except Exception:
            cached_positions = []
        cached_recent_trades = self._get_recent_trade_samples(limit=400)

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

        orchestrator = PortfolioOrchestrator()
        allocation_result: Dict[str, Any] = {'allocations': {}, 'portfolio_risk': 0.0, 'risk_scale': 1.0}
        if bool(portfolio_policy.get('enabled', False)):
            total_capital = 0.0
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
        )
        decisions.extend(exit_decisions)
        executed_orders += exit_orders

        for symbol in normalized_symbols:
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
                })
                continue

            if profitability_blocked:
                decisions.append({
                    'symbol': symbol,
                    'action': 'SKIP',
                    'reason': 'profitability_blocked',
                    'profitability_report': profitability_report,
                    'analysis_type': analysis.get('analysis_type'),
                    'score_model': analysis.get('score_model'),
                    'analysis_reasoning': analysis.get('reasoning', ''),
                })
                continue

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
                    'strategy_consensus': strategy_meta.get('consensus'),
                    'analysis_type': analysis.get('analysis_type'),
                    'score_model': analysis.get('score_model'),
                    'analysis_reasoning': analysis.get('reasoning', ''),
                })
                continue

            is_etf = bool(analysis.get('is_etf', False))
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
            if signal == 'HOLD':
                decisions.append({
                    'symbol': symbol,
                    'action': 'HOLD',
                    'reason': 'threshold_not_met',
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
                            'reason': 'threshold_not_met',
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

            # 승인된 AI 커스텀 전략 풀에서 현재 증권사·시장국면에 맞는 규칙을 선택한다.
            if custom_strategy_pool:
                from trading.declarative_strategy_engine import DeclarativeStrategyEngine
                custom_context = dict(analysis)
                custom_context.update({
                    'signal': 'LONG' if signal == 'BUY' else 'SHORT',
                    'confidence': max(0.0, min(1.0, self._to_float(analysis.get('score')) / 100.0)),
                    'current_price': self._to_float(analysis.get('current_price')),
                })
                custom_entry = DeclarativeStrategyEngine.evaluate_strategy_pool(
                    custom_strategy_pool,
                    custom_context,
                    asset_class='stock',
                    target=self.broker_name,
                    market_regime=market_regime,
                )
                if not custom_entry.get('allowed', False):
                    decisions.append({
                        'symbol': symbol,
                        'action': 'SKIP',
                        'reason': 'custom_strategy_not_matched',
                        'custom_strategy': custom_entry,
                    })
                    continue
                if custom_entry.get('selected_strategy_name'):
                    engine_settings = dict(custom_entry.get('engine_settings') or {})
                    if 'signal_threshold' in engine_settings:
                        custom_threshold = float(engine_settings['signal_threshold'])
                        if custom_threshold <= 1.0:
                            custom_threshold *= 100.0
                        if signal == 'BUY' and self._to_float(analysis.get('score')) < custom_threshold:
                            decisions.append({
                                'symbol': symbol, 'action': 'SKIP',
                                'reason': 'custom_signal_threshold_not_met',
                                'strategy': custom_entry.get('selected_strategy_name'),
                            })
                            continue
                    analysis['_selected_custom_strategy'] = custom_entry.get('selected_strategy_name')

            auto_risk_check = self._evaluate_auto_trade_risk_guard(
                symbol=symbol,
                auto_risk_policy=auto_risk_policy,
            )
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

            if execution_mode != 'mock' and not bool(allow_live_order):
                decisions.append({
                    'symbol': symbol,
                    'action': signal,
                    'reason': 'live_order_blocked',
                    'execution_mode': execution_mode,
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
                            'reason': 'live_order_blocked',
                            'execution_mode': execution_mode,
                            'effective_buy_threshold': effective_buy_threshold,
                            'effective_sell_threshold': effective_sell_threshold,
                        },
                    },
                )
                continue

            current_price = self._to_float(analysis.get('current_price'), default=0.0)
            effective_qty = requested_qty
            if bool(portfolio_policy.get('enabled', False)):
                effective_qty = orchestrator.quantity_from_allocation(
                    symbol=symbol,
                    price=current_price,
                    fallback_qty=requested_qty,
                    allocation_result=allocation_result,
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

            idempotency_key = self._build_stock_order_idempotency_key(
                symbol=symbol,
                side=signal,
                quantity=effective_qty,
                order_type=selected_order_type,
                price=request_price,
            )
            recorder = self._get_recorder()
            if recorder is not None:
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

            execution_attempts += 1
            if bool(execution_policy.get('enabled', False)):
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
                executed_orders += 1
                strategy_runtime_state[f'last_trade_at::{symbol.upper()}'] = datetime.now()
                self._insert_auto_trade_log(
                    symbol=symbol,
                    side=signal,
                    quantity=effective_qty,
                    price=current_price,
                    score=self._to_float(analysis.get('score')),
                    momentum=self._to_float(analysis.get('momentum')),
                )
                if recorder is not None:
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

            if recorder is not None:
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
                    'side': signal,
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
