#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSI, trend, volatility 등 계산
SHORT/LONG/HOLD 신호 평가 로직
"""

import numpy as np
import pandas as pd
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
import time
import os
import threading

from .ai.inference_policy import OpportunityAwareInferencePolicy


def format_percent(value: float, decimal_places: int = 2) -> str:
    """✅ 퍼센트 변환 함수 통일"""
    return f"{value * 100:.{decimal_places}f}%"


class SignalType(Enum):
    """신호 타입"""
    LONG = "LONG"
    SHORT = "SHORT"
    HOLD = "HOLD"


class TrendDirection(Enum):
    """트렌드 방향"""
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    SIDEWAYS = "SIDEWAYS"


@dataclass
class MarketData:
    """시장 데이터"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class TechnicalIndicators:
    """기술적 지표"""
    rsi: float
    macd: float
    macd_signal: float
    macd_histogram: float
    sma_20: float
    sma_50: float
    ema_12: float
    ema_26: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_width: float
    bb_position: float
    atr: float
    volume_sma: float
    volume_ratio: float
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    ema_200: Optional[float] = None
    sma_200: Optional[float] = None
    adx: Optional[float] = None


@dataclass
class AnalysisResult:
    """분석 결과"""
    symbol: str
    signal: SignalType
    confidence: float
    trend: TrendDirection
    volatility: float
    support_level: float
    resistance_level: float
    indicators: TechnicalIndicators
    reasoning: str
    timestamp: datetime
    current_price: float = 0.0


@dataclass
class TrendData:
    """트렌드 데이터"""
    strength: float
    direction: str
    momentum: float
    support_level: float
    resistance_level: float


@dataclass
class MarketState:
    """시장 상태"""
    symbol: str
    trend_data: TrendData
    volatility: float = 0.0


class Analyzer:
    """기술적 분석 및 거래 신호 생성"""

    # 메이저 코인 리스트
    MAJOR_COINS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'SOLUSDT', 'DOTUSDT', 'AVAXUSDT', 'MATICUSDT']

    def __init__(self, binance_client, exchange_manager=None):
        self.binance_client = binance_client
        self.exchange_manager = exchange_manager  # 선택적 다중거래소 인터페이스
        self.logger = logging.getLogger(__name__)

        # 설정 로드
        self.settings = self._load_settings()

        # AI 매니저 (외부에서 설정 가능)
        self.ai_manager = None

        # AI 학습 데이터 활용을 위한 참조
        self.ai_learning_manager = None

        # AI 리포트 매니저
        self.ai_report_manager = None

        # 시장 심리 분석기 초기화
        from .market_sentiment_analyzer import MarketSentimentAnalyzer
        self.sentiment_analyzer = MarketSentimentAnalyzer(binance_client, self.logger)

        # 데이터 캐시
        self.data_cache = {}
        self.cache_timeout = 300  # 5분 캐시 (성능 개선)
        self.ai_inference_policy = OpportunityAwareInferencePolicy(self.settings)

        # 거래소별 모니터링 스레드가 동시에 분석해도 컨텍스트가 섞이지 않게 한다.
        self._exchange_context_local = threading.local()
        self._exchange_context = None

        # 연속 손실/익절 추적
        self.consecutive_losses = {}
        self.consecutive_wins = {}

        # 마지막 거래 시간
        self.last_trade_time = None

        # 시장 국면 히스테리시스 상태 저장
        self._last_regime_per_symbol = {}

        # 사용자 설정 가능한 AI 신호 점수 기준
        # 설정 파일에서 analyzer 설정 읽기
        analyzer_settings = self.settings.get('analyzer_settings', {})
        self.user_signal_threshold = analyzer_settings.get('user_signal_threshold', 70)
        self.exchange_signal_thresholds = {
            str(key).lower(): int(value)
            for key, value in dict(analyzer_settings.get('exchange_signal_thresholds', {}) or {}).items()
            if isinstance(value, (int, float)) and 30 <= int(value) <= 90
        }

        self.logger.info("Analyzer 초기화 완료")

    # ---- 다중 거래소 지원을 위한 헬퍼 (점진적 적용) ----
    def set_exchange_manager(self, exchange_manager):
        self.exchange_manager = exchange_manager
        # 시장 심리 분석기는 binance_client 기반이므로 재초기화 불필요

    @property
    def _exchange_context(self) -> Optional[str]:
        local = getattr(self, '_exchange_context_local', None)
        return getattr(local, 'value', None) if local is not None else None

    @_exchange_context.setter
    def _exchange_context(self, value: Optional[str]) -> None:
        local = getattr(self, '_exchange_context_local', None)
        if local is None:
            local = threading.local()
            self._exchange_context_local = local
        local.value = str(value).lower().strip() if value else None

    def _get_current_price(self, symbol: str) -> Optional[float]:
        """현재가 조회(가능하면 ExchangeManager 사용, 폴백은 바이낸스)"""
        try:
            if self.exchange_manager:
                price = self.exchange_manager.get_current_price(
                    symbol,
                    exchange_name=self._exchange_context,
                )
                if price and price > 0:
                    return price
        except Exception as e:
            try:
                self.logger.debug(f"ExchangeManager 현재가 조회 실패: {e}")
            except Exception:
                pass
        if self._exchange_context and self._exchange_context != 'binance':
            return None
        try:
            return self.binance_client.get_current_price(symbol)
        except Exception as e:
            self.logger.error(f"현재가 조회 실패: {e}")
            return None

    def _get_klines(self, symbol: str, interval: str, limit: int) -> List[List]:
        """캔들 조회(가능하면 ExchangeManager 사용, 폴백은 바이낸스)"""
        try:
            if self.exchange_manager and hasattr(self.exchange_manager, 'get_klines'):
                data = self.exchange_manager.get_klines(
                    symbol,
                    interval,
                    limit,
                    exchange_name=self._exchange_context,
                )
                if data:
                    self.logger.debug(f"✅ ExchangeManager 캔들 조회 성공: {symbol} ({len(data)}개)")
                    return data
                else:
                    self.logger.warning(f"⚠️ ExchangeManager 캔들 조회 결과 없음: {symbol}")
        except Exception as e:
            try:
                self.logger.debug(f"ExchangeManager 캔들 조회 실패: {e}")
            except Exception:
                pass
        if self._exchange_context and self._exchange_context != 'binance':
            return []
        try:
            if self.binance_client and hasattr(self.binance_client, 'get_klines'):
                data = self.binance_client.get_klines(symbol, interval, limit)
                if data:
                    self.logger.debug(f"✅ BinanceClient 캔들 조회 성공: {symbol} ({len(data)}개)")
                    return data
                else:
                    self.logger.warning(f"⚠️ BinanceClient 캔들 조회 결과 없음: {symbol}")
        except Exception as e:
            self.logger.error(f"BinanceClient 캔들 조회 실패: {e}")
        self.logger.error(f"❌ 모든 캔들 조회 실패: {symbol}")
        return []

    def set_ai_learning_manager(self, ai_learning_manager):
        """AI 학습 매니저 설정"""
        self.ai_learning_manager = ai_learning_manager
        self.logger.info("AI 학습 매니저 설정 완료")

    def set_ai_report_manager(self, ai_report_manager):
        """AI 리포트 매니저 설정"""
        self.ai_report_manager = ai_report_manager
        self.logger.info("AI 리포트 매니저 설정 완료")

    def set_user_signal_threshold(self, threshold: int, exchange_name: Optional[str] = None):
        """사용자 신호 점수 기준 설정. 거래소가 있으면 해당 거래소에만 적용한다."""
        if 30 <= threshold <= 90:
            exchange = str(exchange_name or '').lower().strip()
            if exchange:
                self.exchange_signal_thresholds[exchange] = int(threshold)
                self.logger.info(f"AI 신호 점수 기준 변경: {exchange}={threshold}점")
            else:
                self.user_signal_threshold = threshold
                self.logger.info(f"AI 신호 점수 공통 기준 변경: {threshold}점")

            # AI 리포트 매니저 모드도 동기화
            if self.ai_report_manager and not exchange:
                if threshold >= 70:
                    mode = 'conservative'
                elif threshold >= 60:
                    mode = 'balanced'
                else:
                    mode = 'aggressive'
                self.ai_report_manager.set_trading_mode(mode)
        else:
            self.logger.error(f"잘못된 신호 점수 기준: {threshold} (30-90 범위)")

    def get_user_signal_threshold(self, exchange_name: Optional[str] = None) -> int:
        """현재 신호 점수 기준 반환. 거래소별 값이 없으면 공통 기준을 사용한다."""
        exchange = str(exchange_name or self._exchange_context or '').lower().strip()
        if exchange:
            return int(self.exchange_signal_thresholds.get(exchange, self.user_signal_threshold))
        return int(self.user_signal_threshold)

    def get_ai_learning_insights(self, symbol: str, market_state: MarketState) -> Dict:
        """AI 학습 데이터에서 인사이트 조회"""
        try:
            if not self.ai_learning_manager:
                return {}

            # 최근 학습 데이터에서 유사한 시장 상황의 성공 사례 찾기
            recent_data = self.ai_learning_manager.get_recent_learning_data(hours=12)

            insights = {
                'market_adaptation_patterns': {},
                'successful_strategies': [],
                'recommended_adjustments': {},
                'confidence_level': 0.5
            }

            if recent_data:
                # 시장 적응 패턴 분석
                patterns = self.ai_learning_manager.get_market_adaptation_patterns()
                insights['market_adaptation_patterns'] = patterns

                # 성공적인 전략 찾기
                successful_cases = [
                    data for data in recent_data
                    if data['performance_metrics']['market_adaptation_score'] > 0.7
                ]

                if successful_cases:
                    insights['successful_strategies'] = [
                        {
                            'market_condition': case['market_condition'],
                            'adjustment_factor': case['adjustment_factor'],
                            'selected_coins': case['selected_coins'],
                            'performance_score': case['performance_metrics']['market_adaptation_score']
                        }
                        for case in successful_cases[:5]  # 최근 5개 성공 사례
                    ]

                    # 추천 조정사항 생성
                    avg_factor = sum(case['adjustment_factor'] for case in successful_cases) / len(successful_cases)
                    insights['recommended_adjustments'] = {
                        'suggested_volatility_threshold': market_state.volatility * avg_factor,
                        'suggested_rsi_relaxation': 0.1 if avg_factor < 0.8 else 0.05,
                        'suggested_momentum_threshold': 0.001 * avg_factor
                    }

                    insights['confidence_level'] = min(0.9, len(successful_cases) * 0.1 + 0.5)

            return insights

        except Exception as e:
            self.logger.error(f"AI 학습 인사이트 조회 오류: {e}")
            return {}

    def apply_ai_learning_to_signal_generation(self, coin: str, market_data: List[MarketData],
                                             indicators: TechnicalIndicators, market_state: MarketState,
                                             config: Dict) -> Dict:
        """AI 학습 데이터를 활용한 시그널 생성 개선"""
        try:
            # 기본 시그널 생성
            basic_signal = self._generate_basic_signal(coin, market_data, indicators, market_state, config)

            # AI 학습 인사이트 조회
            ai_insights = self.get_ai_learning_insights(coin, market_state)

            if ai_insights and ai_insights.get('confidence_level', 0) > 0.6:
                # AI 학습 데이터를 활용한 시그널 개선
                improved_signal = self._improve_signal_with_ai_learning(basic_signal, ai_insights, market_state)

                # coin 전체를 로그로 출력하지 않음
                coin_symbol = coin.get('symbol', 'UNKNOWN') if isinstance(coin, dict) else str(coin)
                self.logger.info(f"{coin_symbol} AI 학습 기반 시그널 개선:")
                self.logger.info(f"  - 기본 신호: {basic_signal.get('signal', 'HOLD')}")
                self.logger.info(f"  - 개선된 신호: {improved_signal.get('signal', 'HOLD')}")
                self.logger.info(f"  - AI 신뢰도: {ai_insights.get('confidence_level', 0):.2f}")

                return improved_signal
            else:
                return basic_signal

        except Exception as e:
            self.logger.error(f"AI 학습 기반 시그널 생성 오류: {e}")
            return self._generate_basic_signal(coin, market_data, indicators, market_state, config)

    def _improve_signal_with_ai_learning(self, basic_signal: Dict, ai_insights: Dict, market_state: MarketState) -> Dict:
        """AI 학습 데이터를 활용한 시그널 개선"""
        try:
            improved_signal = basic_signal.copy()

            # 성공적인 전략에서 패턴 학습
            successful_strategies = ai_insights.get('successful_strategies', [])

            if successful_strategies:
                # 유사한 시장 상황의 성공 사례 분석
                current_volatility = market_state.volatility
                current_signal = basic_signal.get('signal', 'HOLD')

                # 성공 사례에서 유사한 변동성 패턴 찾기
                similar_cases = [
                    strategy for strategy in successful_strategies
                    if abs(strategy.get('adjustment_factor', 1.0) - 1.0) < 0.2  # 유사한 조정 계수
                ]

                if similar_cases:
                    # 성공 사례 기반 시그널 조정
                    avg_performance = sum(case['performance_score'] for case in similar_cases) / len(similar_cases)

                    if avg_performance > 0.8:
                        # 높은 성과의 사례가 있으면 시그널 신뢰도 향상
                        improved_signal['confidence'] = min(1.0, basic_signal.get('confidence', 0.5) * 1.2)
                        improved_signal['ai_learning_boost'] = True
                        improved_signal['learning_reason'] = f"성공 사례 기반 신뢰도 향상 (평균 성과: {avg_performance:.2f})"

                    # 추천 조정사항 적용
                    recommended_adjustments = ai_insights.get('recommended_adjustments', {})
                    if recommended_adjustments:
                        improved_signal['ai_recommended_adjustments'] = recommended_adjustments

            return improved_signal

        except Exception as e:
            self.logger.error(f"AI 학습 기반 시그널 개선 오류: {e}")
            return basic_signal

    def set_ai_manager(self, ai_manager):
        """AI 매니저 설정"""
        self.ai_manager = ai_manager
        self.logger.info("AI 매니저 설정 완료")

    def update_settings(self, new_settings: Dict):
        """설정 업데이트"""
        self.settings.update(new_settings)
        self.ai_inference_policy.update_settings(self.settings)
        self.logger.info(f"분석 설정 업데이트: {new_settings}")

    def generate_trading_signal(self, coin: str, config: Optional[Dict] = None, exchange_name: Optional[str] = None) -> Dict:
        """AI 기반 거래 신호 생성 (동적 TP/SL 포함)"""
        try:
            # 스트림 로그 유틸 (지연 임포트)
            try:
                from log_system.log_adapter import log_event as _log_event
            except Exception:
                _log_event = None
            # 거래소 컨텍스트 설정 (바이낸스 거래 시 'binance'로 고정)
            if exchange_name:
                self._exchange_context = exchange_name
            else:
                # 바이낸스 거래 시 기본값으로 'binance' 설정
                self._exchange_context = 'binance'
            # 기본 설정
            if config is None:
                config = self.settings

            # 시장 데이터 수집
            try:
                if _log_event:
                    _log_event('analysis', f"{coin} Market data retrieval started", exchange=self._exchange_context)
            except Exception:
                pass
            market_data = self.get_market_data(coin)
            if not market_data:
                return {"signal": "HOLD", "confidence": 0, "reason": "데이터 부족"}
            try:
                if _log_event:
                    _log_event('analysis', f"{coin} Market data retrieval completed: {len(market_data)} candles", exchange=self._exchange_context)
            except Exception:
                pass

            # 기술적 지표 계산
            indicators = self.calculate_indicators(market_data, coin)
            try:
                if _log_event and hasattr(indicators, 'rsi'):
                    _log_event('analysis', f"{coin} RSI: {float(indicators.rsi):.2f}", exchange=self._exchange_context)
            except Exception:
                pass

            # 시장 상태 분석
            market_state = self.get_market_state(coin)
            if not market_state:
                return {"signal": "HOLD", "confidence": 0, "reason": "시장 상태 분석 실패"}
            try:
                if _log_event:
                    _log_event('analysis', f"{coin} Market analysis started:", exchange=self._exchange_context)
                    _log_event('analysis', f"- Volatility: {float(market_state.volatility):.4f}", exchange=self._exchange_context)
                    if market_state.trend_data:
                        _log_event('analysis', f"- Trend strength: {float(market_state.trend_data.strength):.4f}", exchange=self._exchange_context)
                        _log_event('analysis', f"- Trend direction: {market_state.trend_data.direction}", exchange=self._exchange_context)
            except Exception:
                pass

            # 비용 제어는 거래를 중단하지 않는다. 먼저 로컬 신호를 계산한 뒤
            # 시장 이벤트가 있거나 거래 후보일 때만 LLM을 새로 호출한다.
            basic_signal = self._generate_basic_signal(coin, market_data, indicators, market_state, config)
            if bool((config or {}).get("_skip_ai_enhancement", False)):
                result = dict(basic_signal)
                result.update({
                    "ai_call_mode": "local_strategy_universe",
                    "ai_cost_control_reason": "advanced_independent_base_ai_shadow_disabled",
                    "strategy_variant": "custom_independent_local_context",
                    "ai_model": "",
                    "ai_optimized": False,
                })
                return result

            # AI 기반 분석 (AI 매니저가 있는 경우)
            if (
                self.ai_manager
                and getattr(
                    self.ai_manager,
                    'enabled_for_role',
                    lambda _role: self.ai_manager.enabled(),
                )('signal_analysis')
            ):
                exchange = str(self._exchange_context or "binance")
                decision = self.ai_inference_policy.decide(
                    exchange=exchange,
                    symbol=coin,
                    market_data=market_data,
                    indicators=indicators,
                    market_state=market_state,
                    basic_signal=basic_signal,
                )
                mode = str(decision.get("mode", "local"))
                if mode == "cache":
                    ai_analysis = dict(decision.get("analysis", {}) or {})
                elif mode == "call":
                    ai_analysis = self.ai_manager.analyze_market_conditions(coin, market_data, indicators)
                    self.ai_inference_policy.store(
                        exchange=exchange,
                        symbol=coin,
                        fingerprint=str(decision.get("fingerprint", "")),
                        analysis=ai_analysis,
                    )
                else:
                    result = dict(basic_signal)
                    result.update({
                        "ai_call_mode": "local",
                        "ai_cost_control_reason": str(decision.get("reason", "stable_non_candidate")),
                        "strategy_variant": "local_fallback",
                        "ai_model": "",
                        "ai_optimized": False,
                    })
                    return result

                result = self._generate_ai_enhanced_signal(
                    coin, market_data, indicators, market_state, ai_analysis, config
                )
                result.update({
                    "ai_call_mode": mode,
                    "ai_cost_control_reason": str(decision.get("reason", "")),
                    "strategy_variant": "ai_event_driven",
                    "ai_model": str(ai_analysis.get("_ai_model", "")),
                    "ai_usage": dict(ai_analysis.get("_ai_usage", {}) or {}),
                })
                return result
            else:
                # 기본 기술적 지표 기반
                result = dict(basic_signal)
                result.update({
                    "ai_call_mode": "disabled",
                    "strategy_variant": "local_only",
                    "ai_model": "",
                })
                try:
                    if _log_event:
                        _log_event('analysis', f"{coin} Market analysis completed: {result.get('signal','HOLD')}", exchange=self._exchange_context)
                except Exception:
                    pass
                return result

        except Exception as e:
            self.logger.error(f"거래 신호 생성 오류: {e}")
            return {"signal": "HOLD", "confidence": 0, "reason": f"오류: {str(e)}"}
        finally:
            self._exchange_context = None

    def _generate_ai_enhanced_signal(self, coin: str, market_data: List[MarketData],
                                   indicators: TechnicalIndicators, market_state: MarketState,
                                   ai_analysis: Dict, config: Dict) -> Dict:
        """AI 강화 거래 신호 생성 (시장 심리 분석 통합)"""
        try:
            # 1. 시장 심리 분석 추가
            sentiment_data = None
            if self.sentiment_analyzer and self._exchange_context:
                try:
                    sentiment_data = self.sentiment_analyzer.analyze_market_sentiment(coin, self._exchange_context)
                    self.logger.info(f"{coin} 시장 심리: {sentiment_data.sentiment_level.value} (점수: {sentiment_data.sentiment_score:.1f})")
                except Exception as e:
                    self.logger.warning(f"시장 심리 분석 실패 ({coin}): {e}")

            # 2. 이전 시스템의 정교한 시장 분석
            weighted_rsi_data = self.calculate_weighted_rsi(coin)
            detailed_trend_data = self.calculate_detailed_trend_analysis(coin)

            if not weighted_rsi_data or not detailed_trend_data:
                return self._generate_basic_signal(coin, market_data, indicators, market_state, config)

            # 3. 기본 신호 결정 (시장 심리 고려)
            signal = self._determine_signal_with_ai_and_sentiment(indicators, market_state, ai_analysis, sentiment_data)

            # 4. 이전 시스템의 정교한 시장 분석 결과
            weighted_rsi = weighted_rsi_data['weighted_rsi']
            weighted_trend = detailed_trend_data['weighted_trend']

            # 5. 시장 상태 분석 (시장 심리 포함)
            market_analysis = {
                'weighted_rsi': weighted_rsi,
                'weighted_trend': weighted_trend,
                'trend_strength': 'STRONG' if weighted_trend > 0.3 else 'WEAK',
                'primary_trend': 'SIDEWAYS',  # 실제로는 계산 필요
                'volume_score': sentiment_data.volume_analysis.volume_ratio * 10 if sentiment_data else 9,
                'volatility_score': 100,  # 실제로는 계산 필요
                'sentiment_score': sentiment_data.sentiment_score if sentiment_data else 0,
                'funding_rate': sentiment_data.funding_rate.current_rate if sentiment_data else 0
            }

            # 6. AI 최적화된 파라미터 계산 (시장 심리 고려)
            ai_params = self.calculate_ai_optimized_parameters_with_sentiment(coin, signal, indicators, market_state, sentiment_data)

            # 7. 최적화된 파라미터 적용
            entry_confidence = max(ai_analysis.get('entry_confidence', 0.5), ai_params['entry_confidence'])
            optimal_entry_price = ai_analysis.get('optimal_entry_price', market_data[-1].close)

            dynamic_tp_percent = ai_params['tp_percent']
            dynamic_sl_percent = ai_params['sl_percent']
            optimal_leverage = ai_params['leverage']

            # 8. AI 분석 결과 생성 (시장 심리 포함)
            ai_reason = ai_analysis.get('reason', 'AI 분석 기반')
            optimization_reason = ai_params['optimization_reason']
            sentiment_reason = f"시장심리:{sentiment_data.sentiment_level.value}" if sentiment_data else "시장심리:분석불가"
            analysis_reason = f"기술적 분석 완료 - {signal} 신호"
            combined_reason = f"{ai_reason} + {optimization_reason} + {sentiment_reason} + {analysis_reason}"

            # coin 전체를 로그로 출력하지 않음
            coin_symbol = coin.get('symbol', 'UNKNOWN') if isinstance(coin, dict) else str(coin)

            # ✅ 역추세 신호 라벨링 추가
            trend_direction = market_state.trend_data.direction if market_state.trend_data else "UNKNOWN"
            if trend_direction == "DOWNTREND" and signal == "LONG":
                reversal_label = " (역추세/반등형)"
            elif trend_direction == "UPTREND" and signal == "SHORT":
                reversal_label = " (역추세/조정형)"
            else:
                reversal_label = ""

            self.logger.info(f"📊 {coin_symbol} 분석 완료 - 시그널: {signal}{reversal_label} (ex=binance)")
            self.logger.info(f"{coin_symbol} AI+심리 강화 신호: {signal}, 신뢰도={entry_confidence:.2f}, "
                           f"TP={format_percent(dynamic_tp_percent, 3)}, SL={format_percent(dynamic_sl_percent, 3)}, "
                           f"레버리지={optimal_leverage}x")

            result = {
                "signal": signal,
                "confidence": entry_confidence,
                "entry_price": optimal_entry_price,
                "tp_percent": dynamic_tp_percent,
                "sl_percent": dynamic_sl_percent,
                "leverage": optimal_leverage,
                "reason": combined_reason,
                "market_volatility": market_state.volatility,
                "trend_strength": market_state.trend_data.strength if market_state.trend_data else 0,
                "weighted_rsi": weighted_rsi,
                "weighted_trend": weighted_trend,
                "ai_optimized": True,
                "optimization_reason": optimization_reason,
                "pattern_optimized": False,
                "ai_validation": "APPROVED",
                # 🔥 trader.py에서 기대하는 키들 추가 (안전한 접근)
                "rsi": indicators.rsi if indicators else 50.0,
                "macd": indicators.macd if indicators else 0.0,
                "macd_signal": indicators.macd_signal if indicators else 0.0,
                "macd_histogram": indicators.macd_histogram if indicators else 0.0,
                "bb_position": indicators.bb_position if indicators else 0.5,
                "ma20": indicators.sma_20 if indicators else 0.0,
                "ma50": indicators.sma_50 if indicators else 0.0,
                "ma200": indicators.sma_200 if indicators else None,
                "sma20": indicators.sma_20 if indicators else 0.0,
                "sma50": indicators.sma_50 if indicators else 0.0,
                "sma200": indicators.sma_200 if indicators else None,
                "ema20": indicators.ema_20 if indicators else None,
                "ema50": indicators.ema_50 if indicators else None,
                "ema200": indicators.ema_200 if indicators else None,
                "adx": indicators.adx if indicators else None,
                "atr": indicators.atr if indicators else None,
                "atr_percent": (
                    indicators.atr / max(market_data[-1].close, 1e-9) * 100.0
                    if indicators and market_data else None
                ),
                "bb_width": indicators.bb_width if indicators else None,
                "volume": market_data[-1].volume if market_data else None,
                "volume_sma20": indicators.volume_sma if indicators else None,
                "volume_ratio": indicators.volume_ratio if indicators else None,
                "current_price": market_data[-1].close if market_data else optimal_entry_price,
                "volatility": market_state.volatility,
                "trend": market_state.trend_data.direction if market_state.trend_data else "UNKNOWN",
                "support_level": market_state.trend_data.support_level if market_state.trend_data else 0,
                "resistance_level": market_state.trend_data.resistance_level if market_state.trend_data else 0
            }

            # 시장 심리 데이터 추가
            if sentiment_data:
                result.update({
                    "sentiment_score": sentiment_data.sentiment_score,
                    "sentiment_level": sentiment_data.sentiment_level.value,
                    "volume_ratio": sentiment_data.volume_analysis.volume_ratio,
                    "funding_rate": sentiment_data.funding_rate.current_rate,
                    "volume_spike": sentiment_data.volume_analysis.volume_spike
                })

            return result

        except Exception as e:
            self.logger.error(f"AI 강화 신호 생성 오류: {e}")
            return self._generate_basic_signal(coin, market_data, indicators, market_state, config)

    def _generate_basic_signal(self, coin: str, market_data: List[MarketData],
                             indicators: TechnicalIndicators, market_state: MarketState,
                             config: Dict) -> Dict:
        """기본 기술적 지표 기반 신호 생성 (AI 최적화 포함)"""
        try:
            # 기본 기술적 분석
            signal = self._determine_basic_signal(indicators, market_state)

            # AI 최적화된 파라미터 계산 (AI 매니저가 없는 경우에도 기본 최적화 적용)
            ai_params = self.calculate_ai_optimized_parameters(coin, signal, indicators, market_state)

            # 신호 결정 이유 생성
            rsi = indicators.rsi
            macd = indicators.macd
            macd_signal = indicators.macd_signal
            macd_histogram = indicators.macd_histogram
            bb_position = indicators.bb_position

            if signal == "LONG":
                if rsi < 30:
                    reason = f"RSI 과매도({rsi:.1f})"
                elif macd > macd_signal and macd_histogram > 0:
                    reason = f"MACD 상승신호(MACD:{macd:.4f}, Signal:{macd_signal:.4f})"
                elif bb_position < 0.2:
                    reason = f"볼린저밴드 하단근처({bb_position:.2f})"
                else:
                    reason = "기술적 지표 종합 분석"
            elif signal == "SHORT":
                if rsi > 70:
                    reason = f"RSI 과매수({rsi:.1f})"
                elif macd < macd_signal and macd_histogram < 0:
                    reason = f"MACD 하락신호(MACD:{macd:.4f}, Signal:{macd_signal:.4f})"
                elif bb_position > 0.8:
                    reason = f"볼린저밴드 상단근처({bb_position:.2f})"
                else:
                    reason = "기술적 지표 종합 분석"
            else:
                reason = f"중립 상태 (RSI:{rsi:.1f}, MACD:{macd:.4f}, BB:{bb_position:.2f})"

            # AI 최적화 파라미터 적용
            current_price = market_data[-1].close
            optimized_tp = ai_params['tp_percent']
            optimized_sl = ai_params['sl_percent']
            optimized_leverage = ai_params['leverage']
            position_size = ai_params['position_size']
            entry_confidence = ai_params['entry_confidence']

            # 최적화 이유 추가
            combined_reason = f"{reason} + {ai_params['optimization_reason']}"

            # coin 전체를 로그로 출력하지 않음
            coin_symbol = coin.get('symbol', 'UNKNOWN') if isinstance(coin, dict) else str(coin)
            self.logger.info(f"{coin_symbol} 기본 신호 생성 (기술적 분석): {signal}, 신뢰도={entry_confidence:.2f}, "
                           f"TP={optimized_tp:.3f}%, SL={optimized_sl:.3f}%, "
                           f"레버리지={optimized_leverage}x")

            return {
                "signal": signal,
                "confidence": entry_confidence,
                "entry_price": current_price,
                "tp_percent": optimized_tp,
                "sl_percent": optimized_sl,
                "leverage": optimized_leverage,
                # position_size는 optimizer.py에서 계산
                "reason": combined_reason,
                "market_volatility": market_state.volatility,
                "trend_strength": market_state.trend_data.strength if market_state.trend_data else 0,
                # 🔥 trader.py에서 기대하는 키들 추가 (안전한 접근)
                "rsi": rsi,
                "macd": macd,
                "macd_signal": macd_signal,
                "macd_histogram": macd_histogram,
                "bb_position": bb_position,
                "ma20": indicators.sma_20 if indicators else 0.0,
                "ma50": indicators.sma_50 if indicators else 0.0,
                "ma200": indicators.sma_200 if indicators else None,
                "sma20": indicators.sma_20 if indicators else 0.0,
                "sma50": indicators.sma_50 if indicators else 0.0,
                "sma200": indicators.sma_200 if indicators else None,
                "ema20": indicators.ema_20 if indicators else None,
                "ema50": indicators.ema_50 if indicators else None,
                "ema200": indicators.ema_200 if indicators else None,
                "adx": indicators.adx if indicators else None,
                "atr": indicators.atr if indicators else None,
                "atr_percent": (
                    indicators.atr / max(current_price, 1e-9) * 100.0 if indicators else None
                ),
                "bb_width": indicators.bb_width if indicators else None,
                "volume": market_data[-1].volume if market_data else None,
                "volume_sma20": indicators.volume_sma if indicators else None,
                "volume_ratio": indicators.volume_ratio if indicators else None,
                "current_price": current_price,
                "volatility": market_state.volatility,
                "trend": market_state.trend_data.direction if market_state.trend_data else "UNKNOWN",
                "support_level": market_state.trend_data.support_level if market_state.trend_data else 0,
                "resistance_level": market_state.trend_data.resistance_level if market_state.trend_data else 0,
                "ai_optimized": True,
                "optimization_reason": ai_params['optimization_reason']
            }

        except Exception as e:
            self.logger.error(f"기본 신호 생성 오류: {e}")
            return {"signal": "HOLD", "confidence": 0, "reason": f"오류: {str(e)}"}

    def _determine_signal_with_ai(self, indicators: TechnicalIndicators,
                                market_state: MarketState, ai_analysis: Dict) -> str:
        """AI 분석을 활용한 신호 결정"""
        try:
            # AI 분석 결과와 기술적 지표 결합
            ai_signal = ai_analysis.get('signal', 'HOLD')
            ai_confidence = ai_analysis.get(
                'entry_confidence',
                ai_analysis.get('confidence', 0.5),
            )
            # 학습 표본 수가 부족할 때 과도한 보수화(HOLD)로 치우치지 않도록 완화
            try:
                ai_samples = int(ai_analysis.get('samples_count', 0))
            except Exception:
                ai_samples = 0
            try:
                min_samples = int(self.settings.get('ai_learning_min_samples', 20)) if isinstance(self.settings, dict) else 20
            except Exception:
                min_samples = 20

            # 기술적 지표 신호
            tech_signal = self._determine_basic_signal(indicators, market_state)

            # AI 신뢰도가 높으면 AI 신호 우선
            if ai_confidence > 0.7:
                return ai_signal
            elif ai_confidence > 0.5:
                # AI와 기술적 지표 일치 시 신호 강화
                if ai_signal == tech_signal:
                    return ai_signal
                else:
                    # 학습 표본이 충분하지 않으면 보수적 관망 대신 기술 신호를 따름
                    if ai_samples < min_samples:
                        return tech_signal
                    return "HOLD"  # 불일치 + 표본 충분 시 관망
            else:
                return tech_signal  # AI 신뢰도 낮으면 기술적 지표 사용

        except Exception as e:
            self.logger.error(f"AI 신호 결정 오류: {e}")
            return "HOLD"

    def _determine_basic_signal(self, indicators: TechnicalIndicators,
                              market_state: MarketState) -> str:
        """기존 버전의 정교한 시그널 분석 로직 적용"""
        try:
            # 기본 지표 추출
            rsi = indicators.rsi
            macd = indicators.macd
            macd_signal = indicators.macd_signal
            macd_histogram = indicators.macd_histogram
            bb_position = indicators.bb_position

            # 트렌드 데이터 추출
            trend_strength = market_state.trend_data.strength if market_state.trend_data else 0
            trend_direction = market_state.trend_data.direction if market_state.trend_data else "SIDEWAYS"
            momentum = market_state.trend_data.momentum if market_state.trend_data else 0

            # 변동성 데이터
            volatility = market_state.volatility

            # 기존 버전의 정교한 분석 로직 적용
            log_reasons = []

            # 1. 동적 변동성 기준 체크 (기존 버전 로직)
            current_vol_15m = volatility
            dynamic_vol_threshold = self.calculate_dynamic_volatility_threshold(market_state.symbol, market_state.symbol in self.MAJOR_COINS)

            # current_vol_15m은 이미 퍼센트 단위이므로, dynamic_vol_threshold도 퍼센트로 변환
            # dynamic_vol_threshold는 소수점 형태 (예: 0.03)이므로 100을 곱해서 퍼센트로 변환
            dynamic_vol_threshold_percent = dynamic_vol_threshold * 100

            if current_vol_15m < dynamic_vol_threshold_percent:
                # AI 기반 유연한 신호 생성 체크
                should_signal = self._should_generate_signal_despite_low_volatility(
                    market_state.symbol, current_vol_15m, dynamic_vol_threshold_percent,
                    rsi, macd, macd_signal, bb_position, trend_strength, momentum
                )

                if should_signal:
                    self.logger.info(f"🤖 AI 판단: 낮은 변동성({current_vol_15m:.4%})이지만 거래 신호 생성 권장")
                else:
                    self.logger.info(f"실시간 변동성 {current_vol_15m:.4%} < 동적 기준 {dynamic_vol_threshold_percent:.4f}% → HOLD")
                    return "HOLD"

            # 2. 기존 포지션 체크 (동일한 방향 진입 방지)
            position_amt = self.get_position_amount(market_state.symbol)
            if position_amt > 0 and rsi > 70:
                log_reasons.append("Long position with overbought RSI → SHORT entry prohibited")
                self.logger.info(f"Entry condition not met → HOLD | Reason: {', '.join(log_reasons)}")
                return "HOLD"
            if position_amt < 0 and rsi < 30:
                log_reasons.append("Short position with oversold RSI → LONG entry prohibited")
                self.logger.info(f"Entry condition not met → HOLD | Reason: {', '.join(log_reasons)}")
                return "HOLD"

            # 3. 기존 버전의 RSI + 트렌드 기반 신호 생성
            # 거래소별 임계값 가져오기
            th = self._get_signal_thresholds()
            rsi_extreme_oversold = th.get('rsi_extreme_oversold', 30)
            rsi_oversold = th.get('rsi_oversold', 40)
            rsi_overbought = th.get('rsi_overbought', 60)
            rsi_extreme_overbought = th.get('rsi_extreme_overbought', 70)
            momentum_threshold = th.get('momentum_threshold', 0.0005)
            trend_momentum_threshold = th.get('trend_momentum_threshold', 0.02)

            # 3-0. 시장 국면 자동 보정(설정 허용 시)
            try:
                if isinstance(self.settings, dict) and self.settings.get('dynamic_thresholds_enabled', False):
                    regime = 'NORMAL'
                    # 간단한 국면 추정: 변동성이 동적 기준보다 낮으면 LOW, 높으면 HIGH
                    # current_vol_15m, dynamic_vol_threshold_percent는 위에서 계산됨
                    if 'current_vol_15m' in locals() and 'dynamic_vol_threshold_percent' in locals():
                        if current_vol_15m < dynamic_vol_threshold_percent:
                            regime = 'LOW'
                        else:
                            high_mult = 1.5
                            try:
                                high_mult = float(self.settings.get('dynamic_thresholds_high_multiplier', 1.5))
                            except Exception:
                                high_mult = 1.5
                            if current_vol_15m > (dynamic_vol_threshold_percent * high_mult):
                                regime = 'HIGH'
                    # 프로파일 적용
                    profile = self.settings.get('dynamic_thresholds_profile', {}) or {}
                    if regime == 'LOW':
                        p = profile.get('low', {}) or {}
                    elif regime == 'HIGH':
                        p = profile.get('high', {}) or {}
                    else:
                        p = {}
                    if p:
                        rsi_oversold = rsi_oversold + int(p.get('rsi_oversold_delta', 0))
                        rsi_overbought = rsi_overbought + int(p.get('rsi_overbought_delta', 0))
                        momentum_threshold = float(momentum_threshold) * float(p.get('momentum_threshold_scale', 1.0))
                        self.logger.info(f"🔧 Regime({regime}) 보정 적용: RSI({rsi_oversold}/{rsi_overbought}), MT={momentum_threshold:.6f}")
            except Exception as _e:
                try:
                    self.logger.debug(f"동적 임계값 보정 중 오류(무시): {_e}")
                except Exception:
                    pass

            # 3-1. 강한 과매도/과매수 구간 (즉시 진입)
            if rsi <= rsi_extreme_oversold:  # 극단적 과매도
                self.logger.info(f"LONG signal generated (RSI={rsi}, extreme oversold, threshold={rsi_extreme_oversold})")
                return "LONG"
            elif rsi >= rsi_extreme_overbought:  # 극단적 과매수
                self.logger.info(f"SHORT signal generated (RSI={rsi}, extreme overbought, threshold={rsi_extreme_overbought})")
                return "SHORT"

            # 3-2. 과매도/과매수 구간 (추세 확인 후 진입)
            elif rsi <= rsi_oversold:  # 과매도
                if momentum > -trend_momentum_threshold:  # 강한 하락 추세가 아닌 경우
                    self.logger.info(f"LONG signal generated (RSI={rsi}, oversold with trend check, threshold={rsi_oversold})")
                    return "LONG"
                else:
                    log_reasons.append(f"RSI {rsi} oversold but strong downtrend detected")
            elif rsi >= rsi_overbought:  # 과매수
                if momentum < trend_momentum_threshold:  # 강한 상승 추세가 아닌 경우
                    self.logger.info(f"SHORT signal generated (RSI={rsi}, overbought with trend check, threshold={rsi_overbought})")
                    return "SHORT"
                else:
                    log_reasons.append(f"RSI {rsi} overbought but strong uptrend detected")

            # 3-3. 중립 구간 (40-60) - 추세 기반 진입 (더 공격적)
            elif rsi_oversold < rsi < rsi_overbought:
                if momentum > momentum_threshold:  # 매우 약한 상승 모멘텀
                    self.logger.info(f"LONG signal generated (RSI={rsi}, neutral with very relaxed uptrend, threshold={momentum_threshold})")
                    return "LONG"
                elif momentum < -momentum_threshold:  # 매우 약한 하락 모멘텀
                    self.logger.info(f"SHORT signal generated (RSI={rsi}, neutral with very relaxed downtrend, threshold={momentum_threshold})")
                    return "SHORT"
                else:
                    log_reasons.append(f"RSI {rsi} in neutral zone - insufficient momentum")

            # 3-4. 추가 완화된 기준 (더 공격적)
            else:
                # RSI가 30-40 또는 60-70 구간에서도 더 완화된 기준 적용
                if rsi <= (rsi_oversold + 5) and momentum > -trend_momentum_threshold:  # 매우 완화된 과매도 기준
                    self.logger.info(f"LONG signal generated (RSI={rsi}, very relaxed oversold")
                    return "LONG"
                elif rsi >= (rsi_overbought - 5) and momentum < trend_momentum_threshold:  # 매우 완화된 과매수 기준
                    self.logger.info(f"SHORT signal generated (RSI={rsi}, very relaxed overbought")
                    return "SHORT"
                else:
                    log_reasons.append(f"RSI {rsi} outside all signal ranges")

            # 4. 모든 조건 미달 시
            self.logger.info(f"Entry condition not met → HOLD | Reason: {', '.join(log_reasons) or 'Condition threshold not met'}")
            return "HOLD"

        except Exception as e:
            self.logger.error(f"기본 신호 결정 오류: {e}")
            return "HOLD"

    def _get_signal_thresholds(self) -> Dict:
        """거래소별 임계값 딕셔너리 반환: exchange_signal_thresholds → 기본 signal_thresholds 순서"""
        try:
            base = (self.settings or {}).get('signal_thresholds', {}) if isinstance(self.settings, dict) else {}
            exch = None
            try:
                exch = self._exchange_context or (self.settings.get('selected_exchange') if isinstance(self.settings, dict) else None)
            except Exception:
                exch = None
            if exch:
                per = (self.settings or {}).get('exchange_signal_thresholds', {})
                overrides = per.get(exch, {}) if isinstance(per, dict) else {}
                # shallow merge: overrides on top of base
                merged = base.copy()
                merged.update(overrides)
                return merged
            return base
        except Exception as e:
            try:
                self.logger.debug(f"임계값 조회 오류(기본값 사용): {e}")
            except Exception:
                pass
            return (self.settings or {}).get('signal_thresholds', {})

    def calculate_rsi_for_symbol(self, symbol: str) -> Optional[float]:
        """심볼별 RSI 계산"""
        try:
            # 최근 가격 데이터 가져오기
            klines = self._get_klines(symbol, '1m', 100)
            if not klines or len(klines) < 14:
                return None

            # 종가 추출
            closes = [float(kline[4]) for kline in klines]
            prices = pd.Series(closes)

            # RSI 계산
            rsi = self.calculate_rsi(prices, self.settings['rsi_period'])
            return rsi

        except Exception as e:
            self.logger.error(f"{symbol} RSI 계산 오류: {e}")
            return None

    def analyze_trend_data(self, symbol: str) -> Optional[TrendData]:
        """트렌드 데이터 분석"""
        try:
            # 다양한 시간대의 가격 데이터 가져오기
            klines_1m = self._get_klines(symbol, '1m', 60)
            klines_5m = self._get_klines(symbol, '5m', 60)
            klines_15m = self._get_klines(symbol, '15m', 60)

            if not all([klines_1m, klines_5m, klines_15m]):
                return None

            # 종가 추출
            closes_1m = [float(k[4]) for k in klines_1m]
            closes_5m = [float(k[4]) for k in klines_5m]
            closes_15m = [float(k[4]) for k in klines_15m]

            # 트렌드 강도 계산
            trend_strength = self.calculate_trend_strength(closes_1m, closes_5m, closes_15m)

            # 트렌드 방향 결정
            direction = self.determine_trend_direction(closes_1m)

            # 모멘텀 계산
            momentum = self.calculate_momentum(closes_1m)

            # 지지/저항 레벨 계산
            support, resistance = self.calculate_support_resistance_levels(closes_1m)

            return TrendData(
                strength=trend_strength,
                direction=direction,
                momentum=momentum,
                support_level=support,
                resistance_level=resistance
            )

        except Exception as e:
            self.logger.error(f"{symbol} 트렌드 데이터 분석 오류: {e}")
            return None

    def get_market_state(self, symbol: str) -> Optional[MarketState]:
        """시장 상태 분석"""
        try:
            # 현재가 조회 (다중 거래소 지원 헬퍼)
            current_price = self._get_current_price(symbol)
            if current_price is None:
                return None

            # 변동성 계산
            self.logger.info(f"🔄 {symbol} 변동성 계산 시작 (get_market_state)")
            volatility = self.calculate_volatility_for_symbol(symbol)
            self.logger.info(f"✅ {symbol} 변동성 계산 완료: {volatility:.4f}%")

            # 트렌드 데이터
            trend_data = self.analyze_trend_data(symbol)
            if trend_data is None:
                return None

            # 분석 데이터
            analysis_data = {
                'risk_score': self.calculate_risk_score(symbol),
                'volume_ratio': self.calculate_volume_ratio(symbol),
                'price_momentum': self.calculate_price_momentum(symbol)
            }

            return MarketState(
                symbol=symbol,
                trend_data=trend_data,
                volatility=volatility
            )

        except Exception as e:
            self.logger.error(f"{symbol} 시장 상태 분석 오류: {e}")
            return None

    def get_position_amount(self, symbol: str) -> float:
        """포지션 수량 조회"""
        try:
            if hasattr(self.binance_client, 'get_positions'):
                positions = self.binance_client.get_positions()
                for position in positions:
                    if position.symbol == symbol:
                        return float(position.size) if position.side == "LONG" else -float(position.size)
            return 0.0
        except Exception as e:
            self.logger.error(f"{symbol} 포지션 조회 오류: {e}")
            return 0.0

    def get_recent_prices(self, symbol: str, interval: str = '15m', limit: int = 12) -> List[float]:
        """최근 가격 데이터 조회"""
        try:
            klines = self._get_klines(symbol, interval, limit)
            if not klines:
                return []

            # 종가 추출
            prices = [float(kline[4]) for kline in klines]
            return prices

        except Exception as e:
            self.logger.error(f"{symbol} 최근 가격 조회 오류: {e}")
            return []

    def calculate_dynamic_volatility_threshold(self, symbol: str, is_major: bool = False) -> float:
        """AI 기반 동적 변동성 임계값 계산"""
        try:
            # 시장 상황 분석
            market_analysis = self._analyze_current_market_conditions()
            market_level = market_analysis.get('level', 'NORMAL')
            market_score = market_analysis.get('score', 50.0)

            # 최근 가격 데이터 수집
            klines_15m = self._get_klines(symbol, '15m', 96)  # 24시간
            klines_1h = self._get_klines(symbol, '1h', 24)   # 24시간

            if not klines_15m or not klines_1h:
                # 시장 상황에 따른 기본값
                if market_level == 'LOW':
                    default_threshold = 0.001  # 0.1%
                elif market_level == 'NORMAL':
                    default_threshold = 0.003  # 0.3%
                else:
                    default_threshold = 0.005  # 0.5%

                self.logger.info(f"{symbol} 동적 기준 계산: 데이터 부족으로 {market_level} 기본값 {default_threshold:.3f} 사용")
                return default_threshold

            # 변동성 계산
            closes_15m = [float(k[4]) for k in klines_15m]
            closes_1h = [float(k[4]) for k in klines_1h]

            # 15분 변동성
            changes_15m = []
            for i in range(1, len(closes_15m)):
                change = abs(closes_15m[i] - closes_15m[i-1]) / closes_15m[i-1]
                changes_15m.append(change)

            # 1시간 변동성
            changes_1h = []
            for i in range(1, len(closes_1h)):
                change = abs(closes_1h[i] - closes_1h[i-1]) / closes_1h[i-1]
                changes_1h.append(change)

            # 평균 변동성
            avg_vol_15m = np.mean(changes_15m) if changes_15m else 0
            avg_vol_1h = np.mean(changes_1h) if changes_1h else 0

            # 기본 임계값 계산 (평균 변동성 기반)
            base_threshold = (avg_vol_15m + avg_vol_1h) / 2

            # 코인 타입에 따른 기본 조정 (설정 파일에서 읽기)
            analyzer_settings = self.settings.get('analyzer_settings', {})
            coin_multipliers = analyzer_settings.get('coin_multipliers', {'major': 0.4, 'altcoin': 0.6})

            if is_major:
                coin_multiplier = coin_multipliers.get('major', 0.4)
                coin_type = "메이저"
            else:
                coin_multiplier = coin_multipliers.get('altcoin', 0.6)
                coin_type = "알트"

            # 시장 상황에 따른 AI 조정 (설정 파일에서 읽기)
            market_multipliers = analyzer_settings.get('market_multipliers', {'low': 0.3, 'normal': 0.8, 'high': 1.0})

            if market_level == 'LOW':
                # 낮은 활동도 → 기준 대폭 완화
                if market_score < 20:
                    market_multiplier = market_multipliers.get('low', 0.3)  # 70% 완화
                else:
                    market_multiplier = market_multipliers.get('low', 0.5)  # 50% 완화
            elif market_level == 'NORMAL':
                market_multiplier = market_multipliers.get('normal', 0.8)  # 20% 완화
            else:  # HIGH
                market_multiplier = market_multipliers.get('high', 1.0)  # 기준 유지

            # AI 학습 데이터 기반 추가 조정
            ai_adjustment = self._get_ai_volatility_adjustment(symbol, market_analysis)

            # 최종 임계값 계산
            dynamic_threshold = base_threshold * coin_multiplier * market_multiplier * ai_adjustment

            # 실용적인 최소/최대 제한
            if is_major:
                min_threshold, max_threshold = 0.0005, 0.008  # 0.05% ~ 0.8%
            else:
                min_threshold, max_threshold = 0.001, 0.012   # 0.1% ~ 1.2%

            final_threshold = max(min_threshold, min(dynamic_threshold, max_threshold))

            # 상세한 AI 로그
            self.logger.info(f"{symbol} AI 동적 기준 계산 상세:")
            self.logger.info(f"  - 코인 타입: {coin_type}")
            self.logger.info(f"  - 시장 상황: {market_level} (점수: {market_score:.1f})")
            self.logger.info(f"  - 15m 평균 변동성: {avg_vol_15m:.6f}")
            self.logger.info(f"  - 1h 평균 변동성: {avg_vol_1h:.6f}")
            self.logger.info(f"  - 기본 임계값: {base_threshold:.6f}")
            self.logger.info(f"  - 코인 조정: x{coin_multiplier:.2f}")
            self.logger.info(f"  - 시장 조정: x{market_multiplier:.2f}")
            self.logger.info(f"  - AI 조정: x{ai_adjustment:.2f}")
            self.logger.info(f"  - 최종 임계값: {final_threshold:.6f} ({format_percent(final_threshold, 3)})")

            return final_threshold

        except Exception as e:
            self.logger.error(f"AI 동적 변동성 기준 계산 오류: {e}")
            # 오류 시 시장 상황에 따른 안전한 기본값
            if hasattr(self, '_last_market_level'):
                if self._last_market_level == 'LOW':
                    return 0.002
                elif self._last_market_level == 'NORMAL':
                    return 0.004
                else:
                    return 0.006
            return 0.003  # 중간값

    def calculate_trend_strength(self, closes_1m: List[float], closes_5m: List[float], closes_15m: List[float]) -> float:
        """트렌드 강도 계산"""
        try:
            # 각 시간대별 트렌드 계산
            trends = []

            for closes in [closes_1m, closes_5m, closes_15m]:
                if len(closes) >= 20:
                    # 이동평균 기울기로 트렌드 계산
                    ma_short = np.mean(closes[-10:])
                    ma_long = np.mean(closes[-20:])
                    trend = (ma_short - ma_long) / ma_long
                    trends.append(trend)

            # 가중 평균 (최근 데이터에 더 높은 가중치)
            if trends:
                weights = [0.5, 0.3, 0.2][:len(trends)]
                weighted_trend = np.average(trends, weights=weights)
                return float(abs(weighted_trend) * 100)  # 퍼센트로 변환

            return 0.0

        except Exception as e:
            self.logger.error(f"트렌드 강도 계산 오류: {e}")
            return 0.0

    def determine_trend_direction(self, closes: List[float]) -> str:
        """트렌드 방향 결정"""
        try:
            if len(closes) < 20:
                return "SIDEWAYS"

            # 최근 20개 데이터로 방향 결정
            recent = closes[-20:]
            ma_short = np.mean(recent[-10:])
            ma_long = np.mean(recent)

            if ma_short > ma_long * 1.001:
                return "UPTREND"
            elif ma_short < ma_long * 0.999:
                return "DOWNTREND"
            else:
                return "SIDEWAYS"

        except Exception as e:
            self.logger.error(f"트렌드 방향 결정 오류: {e}")
            return "SIDEWAYS"

    def calculate_momentum(self, closes: List[float]) -> float:
        """모멘텀 계산"""
        try:
            if len(closes) < 10:
                return 0.0

            # 최근 10개 데이터의 변화율
            recent = closes[-10:]
            momentum = (recent[-1] - recent[0]) / recent[0]
            return momentum

        except Exception as e:
            self.logger.error(f"모멘텀 계산 오류: {e}")
            return 0.0

    def calculate_support_resistance_levels(self, closes: List[float]) -> Tuple[float, float]:
        """지지/저항 레벨 계산"""
        try:
            if len(closes) < 20:
                return 0.0, 0.0

            # 최근 20개 데이터의 최고/최저
            recent = closes[-20:]
            support = min(recent)
            resistance = max(recent)

            return support, resistance

        except Exception as e:
            self.logger.error(f"지지/저항 레벨 계산 오류: {e}")
            return 0.0, 0.0

    def calculate_volatility_for_symbol(self, symbol: str) -> float:
        """심볼별 변동성 계산.

        다중 거래소 분석 중에는 현재 거래소의 24시간 티커를 사용한다.
        타 거래소 심볼을 BinanceClient로 넘기면 ``LA/KRW`` 또는
        ``BTC/USDT:USDT`` 같은 값이 잘못 정규화되어 Invalid symbol 오류가
        반복되므로, Binance 직접 폴백은 Binance 컨텍스트에서만 허용한다.
        """
        try:
            self.logger.debug(f"🔄 {symbol} 변동성 계산 시작")

            exchange_context = str(self._exchange_context or 'binance').lower().strip()

            # 현재 거래소의 24시간 티커 데이터 사용
            try:
                if self.exchange_manager and hasattr(self.exchange_manager, 'get_24h_ticker'):
                    ticker = self.exchange_manager.get_24h_ticker(
                        symbol,
                        exchange_name=exchange_context,
                    )
                    if ticker and 'priceChangePercent' in ticker:
                        volatility = float(ticker['priceChangePercent'])
                        self.logger.debug(
                            f"✅ {symbol} 변동성 계산 완료 "
                            f"({exchange_context} 24h 티커): {volatility:.2f}%"
                        )
                        return abs(volatility)
            except Exception as e:
                self.logger.debug(f"{exchange_context} 24h 티커 조회 실패: {e}")

            # ExchangeManager가 없는 구버전 Binance 경로만 직접 폴백한다.
            try:
                if (
                    exchange_context == 'binance'
                    and self.binance_client
                    and hasattr(self.binance_client, 'get_ticker')
                ):
                    ticker = self.binance_client.get_ticker(symbol)
                    if ticker and 'priceChangePercent' in ticker:
                        volatility = float(ticker['priceChangePercent'])
                        self.logger.debug(f"✅ {symbol} 변동성 계산 완료 (바이낸스 API): {volatility:.2f}%")
                        return abs(volatility)  # 절댓값으로 변동성 크기만 반환
            except Exception as e:
                self.logger.debug(f"바이낸스 API 티커 조회 실패: {e}")

            # 폴백: 간단한 캔들 기반 계산 (연간화 없음)
            klines = self._get_klines(symbol, '1h', 24)
            if not klines or len(klines) < 10:
                self.logger.warning(f"⚠️ {symbol} 변동성 계산 실패: 데이터 부족 ({len(klines) if klines else 0}개)")
                return 0.0

            closes = [float(k[4]) for k in klines]
            returns = []

            # 시간당 수익률 계산
            for i in range(1, len(closes)):
                ret = (closes[i] - closes[i-1]) / closes[i-1]
                returns.append(ret)

            # 표준편차로 변동성 계산 (연간화 없음)
            volatility = float(np.std(returns)) * 100  # 백분율로 변환
            self.logger.debug(f"✅ {symbol} 변동성 계산 완료 (폴백): {volatility:.2f}%")
            return volatility

        except Exception as e:
            self.logger.error(f"{symbol} 변동성 계산 오류: {e}")
            return 0.0

    def calculate_risk_score(self, symbol: str) -> float:
        """리스크 점수 계산 (evaluator.py와 통일된 방식)"""
        try:
            # 변동성과 거래량을 종합하여 리스크 평가 (evaluator.py와 동일한 방식)
            volatility = self.calculate_volatility_for_symbol(symbol)
            volume_ratio = self.calculate_volume_ratio(symbol)

            # 변동성 점수 계산 (스캘핑 최적화 기준)
            if volatility < 0.005:
                volatility_score = 30  # 스캘핑에 부적합
            elif 0.005 <= volatility <= 0.02:  # 스캘핑에 최적
                volatility_score = 100
            elif 0.02 < volatility <= 0.05:  # 스캘핑 가능
                volatility_score = 80
            else:
                volatility_score = max(20, 100 - (volatility - 0.05) * 1500)

            # 거래량 점수 계산
            volume_score = min(100, volume_ratio * 8)

            # 리스크 점수 계산 (변동성과 거래량 종합)
            volatility_risk = 100 - volatility_score  # 변동성이 높으면 리스크 높음
            volume_risk = 100 - volume_score  # 거래량이 불안정하면 리스크 높음

            # 리스크 점수 계산 (낮을수록 좋음)
            risk_score = max(20, min(100, (volatility_risk + volume_risk) / 2))

            return risk_score

        except Exception as e:
            self.logger.error(f"{symbol} 리스크 점수 계산 오류: {e}")
            return 70.0  # 기본값 (evaluator.py와 동일)

    def calculate_volume_ratio(self, symbol: str) -> float:
        """거래량 비율 계산"""
        try:
            klines = self._get_klines(symbol, '1m', 60)
            if not klines or len(klines) < 20:
                return 1.0

            volumes = [float(k[5]) for k in klines]
            recent_volume = np.mean(volumes[-10:])
            avg_volume = np.mean(volumes)

            if avg_volume > 0:
                return float(recent_volume / avg_volume)
            return 1.0

        except Exception as e:
            self.logger.error(f"{symbol} 거래량 비율 계산 오류: {e}")
            return 1.0

    def calculate_price_momentum(self, symbol: str) -> float:
        """가격 모멘텀 계산"""
        try:
            klines = self._get_klines(symbol, '1m', 20)
            if not klines or len(klines) < 10:
                return 0.0

            closes = [float(k[4]) for k in klines]
            momentum = (closes[-1] - closes[0]) / closes[0]
            return momentum

        except Exception as e:
            self.logger.error(f"{symbol} 가격 모멘텀 계산 오류: {e}")
            return 0.0

    def estimate_regime(self, symbol: str) -> str:
        """현재 시장 국면 추정: LOW / NORMAL / HIGH
        - 변동성(1m 표준편차)과 동적 변동성 임계값 비교
        - HIGH 판정 배율은 settings.dynamic_thresholds_high_multiplier 사용(기본 1.5)
        """
        try:
            # 수동 모드 우선
            try:
                if isinstance(self.settings, dict) and str(self.settings.get('dynamic_thresholds_mode', 'auto')).lower() == 'manual':
                    manual = str(self.settings.get('dynamic_thresholds_manual_regime', 'NORMAL')).upper()
                    if manual in ('LOW', 'NORMAL', 'HIGH'):
                        return manual
            except Exception:
                pass

            vol = self.calculate_volatility_for_symbol(symbol)  # fraction
            dyn_th = self.calculate_dynamic_volatility_threshold(symbol, symbol in self.MAJOR_COINS)  # fraction
            high_mult = 1.5
            try:
                if isinstance(self.settings, dict):
                    high_mult = float(self.settings.get('dynamic_thresholds_high_multiplier', 1.5))
            except Exception:
                high_mult = 1.5

            if vol < dyn_th:
                return 'LOW'
            elif vol > dyn_th * high_mult:
                return 'HIGH'
            return 'NORMAL'
        except Exception as e:
            try:
                self.logger.debug(f"regime 추정 실패: {e}")
            except Exception:
                pass
            return 'NORMAL'

    def calculate_ai_optimized_parameters(self, coin: str, signal: str, indicators: TechnicalIndicators,
                                        market_state: MarketState) -> Dict:
        """AI 최적화된 거래 파라미터 계산"""
        try:
            # 기본 파라미터 (settings.json에서 가져오기)
            base_tp = self.settings.get('default_tp', 0.0018)  # 0.18%
            base_sl = self.settings.get('default_sl', 0.002)   # 0.20%
            base_leverage = 1
            base_position_size = 0.10  # 10%

            # 시장 상황 분석
            volatility = market_state.volatility
            trend_strength = market_state.trend_data.strength if market_state.trend_data else 0
            rsi = indicators.rsi

            # AI 최적화 로직
            optimized_params = {
                'tp_percent': base_tp,
                'sl_percent': base_sl,
                'leverage': base_leverage,
                'position_size': base_position_size,
                'entry_confidence': 0.5,
                'optimization_reason': '기본 설정'
            }

            # 1. 변동성 기반 최적화
            if volatility > 0.05:  # 높은 변동성
                optimized_params['tp_percent'] = base_tp * 1.2  # 20% 증가
                optimized_params['sl_percent'] = base_sl * 1.1  # 10% 증가
                optimized_params['position_size'] = base_position_size * 0.8  # 20% 감소
                optimized_params['optimization_reason'] = '높은 변동성 - 보수적 설정'
            elif volatility < 0.02:  # 낮은 변동성
                optimized_params['tp_percent'] = base_tp * 0.8  # 20% 감소
                optimized_params['sl_percent'] = base_sl * 0.9  # 10% 감소
                optimized_params['position_size'] = base_position_size * 1.2  # 20% 증가
                optimized_params['optimization_reason'] = '낮은 변동성 - 공격적 설정'

            # 2. RSI 기반 최적화
            if signal == "LONG":
                if rsi < 25:  # 극단적 과매도
                    optimized_params['tp_percent'] *= 1.3  # 30% 증가
                    optimized_params['entry_confidence'] = 0.8
                    optimized_params['optimization_reason'] = '극단적 과매도 - 높은 수익 목표'
                elif rsi < 35:  # 과매도
                    optimized_params['tp_percent'] *= 1.1  # 10% 증가
                    optimized_params['entry_confidence'] = 0.7
                    optimized_params['optimization_reason'] = '과매도 - 수익 목표 증가'
            elif signal == "SHORT":
                if rsi > 75:  # 극단적 과매수
                    optimized_params['tp_percent'] *= 1.3  # 30% 증가
                    optimized_params['entry_confidence'] = 0.8
                    optimized_params['optimization_reason'] = '극단적 과매수 - 높은 수익 목표'
                elif rsi > 65:  # 과매수
                    optimized_params['tp_percent'] *= 1.1  # 10% 증가
                    optimized_params['entry_confidence'] = 0.7
                    optimized_params['optimization_reason'] = '과매수 - 수익 목표 증가'

            # 3. 트렌드 강도 기반 최적화
            if trend_strength > 0.5:  # 강한 트렌드
                optimized_params['leverage'] = min(2, base_leverage * 1.5)  # 레버리지 증가
                optimized_params['position_size'] *= 1.1  # 포지션 크기 증가
                optimized_params['optimization_reason'] += ' + 강한 트렌드'
            elif trend_strength < 0.2:  # 약한 트렌드
                optimized_params['leverage'] = 1  # 레버리지 유지
                optimized_params['position_size'] *= 0.9  # 포지션 크기 감소
                optimized_params['optimization_reason'] += ' + 약한 트렌드'

            # 4. 메이저 코인 vs 알트코인 최적화
            is_major = coin in self.MAJOR_COINS
            if is_major:
                optimized_params['tp_percent'] *= 0.9  # 메이저 코인은 더 보수적
                optimized_params['sl_percent'] *= 0.9
                optimized_params['optimization_reason'] += ' (메이저 코인)'
            else:
                optimized_params['tp_percent'] *= 1.1  # 알트코인은 더 공격적
                optimized_params['sl_percent'] *= 1.1
                optimized_params['optimization_reason'] += ' (알트코인)'

            # 5. 최종 검증 및 제한
            # 런타임 단위는 fraction이다. 0.001 = 0.1%.
            optimized_params['tp_percent'] = max(0.0005, min(optimized_params['tp_percent'], 0.05))
            optimized_params['sl_percent'] = max(0.0005, min(optimized_params['sl_percent'], 0.03))
            optimized_params['leverage'] = max(1, min(optimized_params['leverage'], 3))  # 1-3x
            optimized_params['position_size'] = max(0.05, min(optimized_params['position_size'], 0.20))  # 5-20%
            optimized_params['entry_confidence'] = max(0.3, min(optimized_params['entry_confidence'], 0.9))  # 30-90%

            # coin 전체를 로그로 출력하지 않음
            coin_symbol = coin.get('symbol', 'UNKNOWN') if isinstance(coin, dict) else str(coin)
            self.logger.info(f"{coin_symbol} AI 최적화 파라미터: TP={optimized_params['tp_percent'] * 100:.3f}%, "
                           f"SL={optimized_params['sl_percent'] * 100:.3f}%, "
                           f"레버리지={optimized_params['leverage']}x, "
                           f"포지션={optimized_params['position_size']:.1%}, "
                           f"신뢰도={optimized_params['entry_confidence']:.1f}")

            return optimized_params

        except Exception as e:
            self.logger.error(f"AI 최적화 파라미터 계산 오류: {e}")
            return {
                'tp_percent': 0.0018,
                'sl_percent': 0.0020,
                'leverage': 1,
                'position_size': 0.10,
                'entry_confidence': 0.5,
                'optimization_reason': '오류로 인한 기본 설정'
            }

    def update_trade_result(self, symbol: str, is_win: bool):
        """거래 결과 업데이트 (연속 손실/익절 추적)"""
        try:
            coin_name = symbol.replace('USDT', '')

            if is_win:
                self.consecutive_wins[coin_name] = self.consecutive_wins.get(coin_name, 0) + 1
                self.consecutive_losses[coin_name] = 0
            else:
                self.consecutive_losses[coin_name] = self.consecutive_losses.get(coin_name, 0) + 1
                self.consecutive_wins[coin_name] = 0

        except Exception as e:
            self.logger.error(f"거래 결과 업데이트 오류: {e}")

    def analyze_market(self, symbols: Optional[List[str]] = None) -> List[AnalysisResult]:
        """시장 분석 수행"""
        try:
            if symbols is None:
                # 기본 분석 대상 심볼들
                symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'SOLUSDT']

            results = []

            for symbol in symbols:
                try:
                    result = self.analyze_symbol(symbol)
                    if result:
                        results.append(result)

                except Exception as e:
                    self.logger.error(f"{symbol} 분석 중 오류: {e}")

            return results

        except Exception as e:
            self.logger.error(f"시장 분석 중 오류: {e}")
            return []

    def analyze_symbol(self, symbol: str) -> Optional[AnalysisResult]:
        """개별 심볼 분석"""
        try:
            self.logger.info(f"[{symbol}] 분석 시작")

            # 시장 데이터 가져오기
            market_data = self.get_market_data(symbol)
            if market_data is None or len(market_data) < 50:
                self.logger.warning(f"[{symbol}] 시장 데이터 부족: {len(market_data) if market_data else 0}개")
                return None

            # 기술적 지표 계산
            indicators = self.calculate_indicators(market_data, symbol)
            if indicators is None:
                self.logger.warning(f"[{symbol}] 기술적 지표 계산 실패")
                return None

            # 신호 생성 (기존 시스템 사용)
            # symbol은 이미 "BTCUSDT" 형태이므로 그대로 사용
            signal_result = self.generate_trading_signal(symbol)

            # 반환값이 딕셔너리인 경우 처리
            if isinstance(signal_result, dict):
                signal_str = signal_result.get('signal', 'HOLD')
                confidence = signal_result.get('confidence', 0.5)
                # 딕셔너리에서 reason도 추출
                reason = signal_result.get('reason', 'N/A')
            else:
                signal_str = str(signal_result) if signal_result else 'HOLD'
                confidence = 0.5
                reason = 'N/A'

            # SignalType으로 변환
            if signal_str == "LONG":
                signal = SignalType.LONG
            elif signal_str == "SHORT":
                signal = SignalType.SHORT
            else:
                signal = SignalType.HOLD

            # 트렌드 분석
            trend = self.analyze_trend(market_data, indicators)

            # 변동성 계산 (통일된 방식 사용)
            volatility = self.calculate_volatility_for_symbol(symbol)

            # 지지/저항 레벨 계산
            support, resistance = self.calculate_support_resistance(market_data)

            # 현재 가격 추가
            current_price = market_data[-1].close if market_data else 0.0

            result = AnalysisResult(
                symbol=symbol,
                signal=signal,
                confidence=confidence,
                trend=trend,
                volatility=volatility,
                support_level=support,
                resistance_level=resistance,
                indicators=indicators,
                reasoning=f"RSI 기반 신호: {signal_str} (이유: {reason})",
                timestamp=datetime.now(),
                current_price=current_price
            )

            # ✅ 역추세 신호 라벨링 추가
            trend_direction = str(trend).split('.')[-1] if hasattr(trend, 'value') else str(trend)
            if trend_direction == "DOWNTREND" and signal == "LONG":
                reversal_label = " (역추세/반등형)"
            elif trend_direction == "UPTREND" and signal == "SHORT":
                reversal_label = " (역추세/조정형)"
            else:
                reversal_label = ""

            self.logger.info(f"📊 {symbol} 분석 완료 - 시그널: {signal_str}{reversal_label} (ex=binance)")
            return result

        except Exception as e:
            self.logger.error(f"[{symbol}] 분석 중 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None

    def get_market_data(self, symbol: str) -> Optional[List[MarketData]]:
        """시장 데이터 가져오기"""
        try:
            # 캐시 확인
            # 같은 심볼 표기가 거래소별로 다른 데이터를 가리키므로
            # 캐시도 거래소 컨텍스트를 포함해 교차 오염을 막는다.
            exchange_context = str(self._exchange_context or 'binance').lower()
            cache_key = f"{exchange_context}:{symbol}_market_data"
            if cache_key in self.data_cache:
                cached_data, timestamp = self.data_cache[cache_key]
                if (datetime.now() - timestamp).seconds < self.cache_timeout:
                    return cached_data

            # 다중 거래소 경로: ExchangeManager가 있으면 우선 사용 (폴백: Binance)
            klines = []
            indicator_limit = max(220, int(self.settings.get("analysis_kline_limit", 220) or 220))
            if self.exchange_manager and hasattr(self.exchange_manager, 'get_klines'):
                klines = self.exchange_manager.get_klines(
                    symbol,
                    '5m',
                    indicator_limit,
                    exchange_name=exchange_context,
                )
            if not klines and self.binance_client and hasattr(self.binance_client, 'get_klines'):
                klines = self._get_klines(symbol, '5m', indicator_limit)

            if not klines:
                return None

            # 데이터 변환
            market_data = []
            for kline in klines:
                market_data.append(MarketData(
                    symbol=symbol,
                    timestamp=datetime.fromtimestamp(kline[0] / 1000),
                    open=float(kline[1]),
                    high=float(kline[2]),
                    low=float(kline[3]),
                    close=float(kline[4]),
                    volume=float(kline[5])
                ))

            # 캐시에 저장
            self.data_cache[cache_key] = (market_data, datetime.now())

            return market_data

        except Exception as e:
            self.logger.error(f"{symbol} 시장 데이터 가져오기 오류: {e}")
            return None

    def calculate_indicators(self, market_data: List[MarketData], symbol: str = "UNKNOWN") -> TechnicalIndicators:
        """기술적 지표 계산"""
        try:
            # DataFrame으로 변환
            df = pd.DataFrame([{
                'timestamp': data.timestamp,
                'open': data.open,
                'high': data.high,
                'low': data.low,
                'close': data.close,
                'volume': data.volume
            } for data in market_data])

            # 안전한 설정값 가져오기
            rsi_period = self.settings.get('rsi_period', 14)
            macd_fast = self.settings.get('macd_fast', 12)
            macd_slow = self.settings.get('macd_slow', 26)
            macd_signal = self.settings.get('macd_signal', 9)
            bb_period = self.settings.get('bb_period', 20)
            bb_std = self.settings.get('bb_std', 2)
            sma_short = self.settings.get('sma_short', 20)
            sma_long = self.settings.get('sma_long', 50)
            atr_period = self.settings.get('atr_period', 14)
            volume_period = self.settings.get('volume_period', 20)

            # RSI 계산
            rsi = self.calculate_rsi(df['close'], rsi_period)

            # 멀티타임프레임 RSI 계산 (verbose 로깅)
            if self.settings.get('verbose_trade_logging', False):
                from log_system.log_adapter import log_event

                # 다양한 기간의 RSI 계산 (이미 float 값 반환)
                rsi_5 = self.calculate_rsi(df['close'], 5)
                rsi_10 = self.calculate_rsi(df['close'], 10)
                rsi_21 = self.calculate_rsi(df['close'], 21)

                log_event(
                    level='INFO',
                    category='analysis',
                    message=f"{symbol} Multi-timeframe RSI: 5m={rsi_5:.2f}, 10m={rsi_10:.2f}, 14m={rsi:.2f}, 21m={rsi_21:.2f}",
                    exchange='binance'
                )

            # MACD 계산
            macd, macd_signal, macd_histogram = self.calculate_macd(
                df['close'], macd_fast, macd_slow, macd_signal
            )

            # 이동평균 계산
            sma_20 = df['close'].rolling(window=sma_short).mean().iloc[-1]
            sma_50 = df['close'].rolling(window=sma_long).mean().iloc[-1]
            ema_12 = df['close'].ewm(span=12).mean().iloc[-1]
            ema_26 = df['close'].ewm(span=26).mean().iloc[-1]
            ema_20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
            ema_50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
            ema_200 = (
                df['close'].ewm(span=200, adjust=False).mean().iloc[-1]
                if len(df) >= 200 else None
            )
            sma_200 = df['close'].rolling(window=200).mean().iloc[-1] if len(df) >= 200 else None

            # 볼린저 밴드 계산
            bb_upper, bb_middle, bb_lower, bb_width, bb_position = self.calculate_bollinger_bands(
                df['close'], bb_period, bb_std
            )

            # ATR 계산
            atr = self.calculate_atr(df, atr_period)
            adx = self.calculate_adx(df, atr_period)

            # 거래량 분석
            volume_sma = df['volume'].rolling(window=volume_period).mean().iloc[-1]
            volume_ratio = df['volume'].iloc[-1] / volume_sma if volume_sma > 0 else 1.0

            return TechnicalIndicators(
                rsi=rsi,
                macd=macd,
                macd_signal=macd_signal,
                macd_histogram=macd_histogram,
                sma_20=sma_20,
                sma_50=sma_50,
                ema_12=ema_12,
                ema_26=ema_26,
                bb_upper=bb_upper,
                bb_middle=bb_middle,
                bb_lower=bb_lower,
                bb_width=bb_width,
                bb_position=bb_position,
                atr=atr,
                volume_sma=volume_sma,
                volume_ratio=volume_ratio,
                ema_20=float(ema_20),
                ema_50=float(ema_50),
                ema_200=float(ema_200) if ema_200 is not None else None,
                sma_200=float(sma_200) if sma_200 is not None else None,
                adx=float(adx) if adx is not None else None,
            )

        except Exception as e:
            self.logger.error(f"지표 계산 중 오류: {e}")
            # None 대신 기본값 반환
            return self._create_default_indicators()

    def _create_default_indicators(self) -> TechnicalIndicators:
        """기본 기술적 지표 생성"""
        return TechnicalIndicators(
            rsi=50.0,
            macd=0.0,
            macd_signal=0.0,
            macd_histogram=0.0,
            sma_20=0.0,
            sma_50=0.0,
            ema_12=0.0,
            ema_26=0.0,
            bb_upper=0.0,
            bb_middle=0.0,
            bb_lower=0.0,
            bb_width=0.0,
            bb_position=0.5,
            atr=0.0,
            volume_sma=0.0,
            volume_ratio=1.0,
            ema_20=None,
            ema_50=None,
            ema_200=None,
            sma_200=None,
            adx=None,
        )

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """RSI 계산"""
        try:
            delta = prices.diff()
            # numpy 배열로 변환
            delta_arr = np.array(delta, dtype=float)

            # gain과 loss 계산
            gains = np.where(delta_arr > 0, delta_arr, 0)
            losses = np.where(delta_arr < 0, -delta_arr, 0)

            # 이동평균 계산
            avg_gain = np.mean(gains[-period:]) if len(gains) >= period else np.mean(gains)
            avg_loss = np.mean(losses[-period:]) if len(losses) >= period else np.mean(losses)
            if avg_loss == 0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            return float(rsi)
        except Exception as e:
            self.logger.error(f"RSI 계산 오류: {e}")
            return 50.0

    def calculate_macd(self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
        """MACD 계산"""
        try:
            ema_fast = prices.ewm(span=fast).mean()
            ema_slow = prices.ewm(span=slow).mean()
            macd_line = ema_fast - ema_slow
            macd_signal = macd_line.ewm(span=signal).mean()
            macd_histogram = macd_line - macd_signal

            return macd_line.iloc[-1], macd_signal.iloc[-1], macd_histogram.iloc[-1]
        except Exception as e:
            self.logger.error(f"MACD 계산 오류: {e}")
            return 0.0, 0.0, 0.0

    def calculate_bollinger_bands(self, prices: pd.Series, period: int = 20, std: int = 2) -> Tuple[float, float, float, float, float]:
        """볼린저 밴드 계산"""
        try:
            sma = prices.rolling(window=period).mean()
            std_dev = prices.rolling(window=period).std()

            bb_upper = sma + (std_dev * std)
            bb_middle = sma
            bb_lower = sma - (std_dev * std)

            bb_width = (bb_upper - bb_lower) / bb_middle
            bb_position = (prices.iloc[-1] - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1])

            return (
                bb_upper.iloc[-1], bb_middle.iloc[-1], bb_lower.iloc[-1],
                bb_width.iloc[-1], bb_position
            )
        except Exception as e:
            self.logger.error(f"볼린저 밴드 계산 오류: {e}")
            return 0.0, 0.0, 0.0, 0.0, 0.5

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """ATR (Average True Range) 계산"""
        try:
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())

            true_range = np.maximum(high_low, np.maximum(high_close, low_close))
            atr = np.mean(true_range[-period:]) if len(true_range) >= period else np.mean(true_range)

            return float(atr)
        except Exception as e:
            self.logger.error(f"ATR 계산 오류: {e}")
            return 0.0

    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """ADX를 계산하며 충분한 표본이 없으면 None으로 실패 폐쇄한다."""
        try:
            if len(df) < period * 2:
                return None
            up_move = df["high"].diff()
            down_move = -df["low"].diff()
            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
            high_low = df["high"] - df["low"]
            high_close = np.abs(df["high"] - df["close"].shift())
            low_close = np.abs(df["low"] - df["close"].shift())
            true_range = pd.Series(
                np.maximum(high_low, np.maximum(high_close, low_close)),
                index=df.index,
            )
            atr_series = true_range.rolling(window=period).mean()
            plus_di = 100.0 * pd.Series(plus_dm, index=df.index).rolling(window=period).sum() / atr_series
            minus_di = 100.0 * pd.Series(minus_dm, index=df.index).rolling(window=period).sum() / atr_series
            denominator = (plus_di + minus_di).replace(0, np.nan)
            dx = 100.0 * (plus_di - minus_di).abs() / denominator
            adx = dx.rolling(window=period).mean().iloc[-1]
            return float(adx) if pd.notna(adx) else None
        except Exception as e:
            self.logger.error(f"ADX 계산 오류: {e}")
            return None

    def analyze_trend(self, market_data: List[MarketData], indicators: TechnicalIndicators) -> TrendDirection:
        """트렌드 분석"""
        try:
            # 최근 가격 데이터
            recent_prices = [data.close for data in market_data[-20:]]

            # 선형 회귀로 트렌드 계산
            x = np.arange(len(recent_prices))
            slope, _ = np.polyfit(x, recent_prices, 1)

            # 이동평균 기울기
            ma_slope = indicators.sma_20 - indicators.sma_50

            # 트렌드 판단
            if slope > 0 and ma_slope > 0:
                return TrendDirection.UPTREND
            elif slope < 0 and ma_slope < 0:
                return TrendDirection.DOWNTREND
            else:
                return TrendDirection.SIDEWAYS

        except Exception as e:
            self.logger.error(f"트렌드 분석 중 오류: {e}")
            return TrendDirection.SIDEWAYS

    def calculate_support_resistance(self, market_data: List[MarketData]) -> Tuple[float, float]:
        """지지/저항 레벨 계산"""
        try:
            prices = [data.close for data in market_data]
            highs = [data.high for data in market_data]
            lows = [data.low for data in market_data]

            # 최근 20개 봉 기준
            recent_highs = highs[-20:]
            recent_lows = lows[-20:]

            resistance = max(recent_highs)
            support = min(recent_lows)

            return support, resistance

        except Exception as e:
            self.logger.error(f"지지/저항 레벨 계산 중 오류: {e}")
            return 0.0, 0.0

    def get_market_conditions(self, symbol: str) -> Dict:
        """시장 상황 확인"""
        try:
            analysis = self.analyze_symbol(symbol)
            if not analysis:
                return {'tradeable': False, 'reason': '분석 불가'}

            # 거래 가능 여부 판단
            tradeable = True
            reasons = []

            # 변동성 체크
            if analysis.volatility > 10:  # 10% 이상 변동성
                tradeable = False
                reasons.append("높은 변동성")

            # 신뢰도 체크
            if analysis.confidence < 0.6:
                tradeable = False
                reasons.append("낮은 신뢰도")

            # 트렌드 체크
            if analysis.trend == TrendDirection.SIDEWAYS:
                reasons.append("횡보장")

            return {
                'tradeable': tradeable,
                'reason': ", ".join(reasons) if reasons else "거래 가능",
                'analysis': analysis
            }

        except Exception as e:
            self.logger.error(f"시장 상황 확인 중 오류: {e}")
            return {'tradeable': False, 'reason': '오류 발생'}

    def calculate_weighted_rsi(self, symbol: str) -> Dict:
        """이전 시스템의 정교한 Weighted RSI 계산"""
        try:
            # 4시간대 RSI 데이터 수집
            rsi_15m = self.calculate_rsi_for_timeframe(symbol, '15m')
            rsi_1h = self.calculate_rsi_for_timeframe(symbol, '1h')
            rsi_4h = self.calculate_rsi_for_timeframe(symbol, '4h')
            rsi_1d = self.calculate_rsi_for_timeframe(symbol, '1d')

            if not all([rsi_15m, rsi_1h, rsi_4h, rsi_1d]):
                return {}

            # 이전 시스템의 가중치 적용
            # 15m: 40%, 1h: 35%, 4h: 20%, 1d: 5%
            weighted_rsi = (
                (rsi_15m or 0) * 0.40 +
                (rsi_1h or 0) * 0.35 +
                (rsi_4h or 0) * 0.20 +
                (rsi_1d or 0) * 0.05
            )

            self.logger.info(f"{symbol} Weighted RSI 계산: 15m={rsi_15m:.2f}, 1h={rsi_1h:.2f}, "
                           f"4h={rsi_4h:.2f}, 1d={rsi_1d:.2f}, Weighted={weighted_rsi:.2f}")

            return {
                'rsi_15m': rsi_15m,
                'rsi_1h': rsi_1h,
                'rsi_4h': rsi_4h,
                'rsi_1d': rsi_1d,
                'weighted_rsi': weighted_rsi
            }

        except Exception as e:
            self.logger.error(f"Weighted RSI 계산 오류: {e}")
            return {}

    def calculate_rsi_for_timeframe(self, symbol: str, timeframe: str) -> Optional[float]:
        """특정 시간대의 RSI 계산"""
        try:
            # 시간대별 캔들 수 결정
            candle_counts = {
                '15m': 96,   # 24시간
                '1h': 24,    # 24시간
                '4h': 30,    # 5일
                '1d': 14     # 2주
            }

            count = candle_counts.get(timeframe, 24)
            klines = self._get_klines(symbol, timeframe, count)

            if not klines or len(klines) < 14:
                return None

            # 종가 추출
            closes = [float(kline[4]) for kline in klines]
            prices = pd.Series(closes)

            # RSI 계산
            rsi = self.calculate_rsi(prices, 14)
            return rsi

        except Exception as e:
            self.logger.error(f"{symbol} {timeframe} RSI 계산 오류: {e}")
            return 50.0  # 중립값

    def calculate_detailed_trend_analysis(self, symbol: str) -> Dict:
        """이전 시스템의 정교한 트렌드 분석"""
        try:
            # 15분 및 1시간 데이터 수집
            klines_15m = self._get_klines(symbol, '15m', 96)
            klines_1h = self._get_klines(symbol, '1h', 24)

            if not klines_15m or not klines_1h:
                return {}  # 빈 딕셔너리 반환

            # 종가 추출
            closes_15m = [float(k[4]) for k in klines_15m]
            closes_1h = [float(k[4]) for k in klines_1h]

            # 15분 트렌드 분석
            slope_15m = self.calculate_slope_score(closes_15m)
            strength_15m = self.calculate_strength_score(closes_15m)
            trend_confirmed_15m = self.is_trend_confirmed(closes_15m)
            volume_confirmed_15m = self.is_volume_confirmed(symbol, '15m')
            trend_score_15m = (slope_15m + strength_15m) / 2

            # 상세 트렌드 분석 로그 (verbose)
            if self.settings.get('verbose_trade_logging', False):
                from log_system.log_adapter import log_event

                log_event(
                    level='INFO',
                    category='analysis',
                    message=f"{symbol} Detailed trend analysis (15m): slope={slope_15m:.3f}, strength={strength_15m:.3f}, confirmed={trend_confirmed_15m}, volume_confirmed={volume_confirmed_15m}",
                    exchange='binance'
                )

            # 1시간 트렌드 분석
            slope_1h = self.calculate_slope_score(closes_1h)
            strength_1h = self.calculate_strength_score(closes_1h)
            trend_confirmed_1h = self.is_trend_confirmed(closes_1h)
            volume_confirmed_1h = self.is_volume_confirmed(symbol, '1h')
            trend_score_1h = (slope_1h + strength_1h) / 2

            # 가중 평균 트렌드 점수
            weighted_trend = (trend_score_15m * 0.6 + trend_score_1h * 0.4)

            self.logger.info(f"{symbol} 15m detailed calculation:")
            self.logger.info(f"  - slope_score: {slope_15m}")
            self.logger.info(f"  - strength_score: {strength_15m}")
            self.logger.info(f"  - trend_confirmed: {trend_confirmed_15m}")
            self.logger.info(f"  - is_volume_confirmed: {volume_confirmed_15m}")
            self.logger.info(f"  - trend_score: {trend_score_15m}")
            self.logger.info(f"  - final trend_score: {trend_score_15m}")

            self.logger.info(f"{symbol} 1h detailed calculation:")
            self.logger.info(f"  - slope_score: {slope_1h}")
            self.logger.info(f"  - strength_score: {strength_1h}")
            self.logger.info(f"  - trend_confirmed: {trend_confirmed_1h}")
            self.logger.info(f"  - is_volume_confirmed: {volume_confirmed_1h}")
            self.logger.info(f"  - trend_score: {trend_score_1h}")
            self.logger.info(f"  - final trend_score: {trend_score_1h}")

            return {
                '15m': {
                    'slope_score': slope_15m,
                    'strength_score': strength_15m,
                    'trend_confirmed': trend_confirmed_15m,
                    'volume_confirmed': volume_confirmed_15m,
                    'trend_score': trend_score_15m
                },
                '1h': {
                    'slope_score': slope_1h,
                    'strength_score': strength_1h,
                    'trend_confirmed': trend_confirmed_1h,
                    'volume_confirmed': volume_confirmed_1h,
                    'trend_score': trend_score_1h
                },
                'weighted_trend': weighted_trend
            }

        except Exception as e:
            self.logger.error(f"상세 트렌드 분석 오류: {e}")
            return {}

    def calculate_slope_score(self, closes: List[float]) -> float:
        """가격 기울기 점수 계산"""
        try:
            if len(closes) < 2:
                return 0.0

            # 최근 10개 데이터의 기울기 계산
            recent_closes = closes[-10:]
            x = np.arange(len(recent_closes))
            y = np.array(recent_closes)

            slope, _ = np.polyfit(x, y, 1)

            # 정규화된 기울기 점수 (-1 ~ 1)
            max_price = max(recent_closes)
            normalized_slope = slope / max_price * 100

            return max(-1.0, min(1.0, normalized_slope))

        except Exception as e:
            self.logger.error(f"기울기 점수 계산 오류: {e}")
            return 0.0

    def calculate_strength_score(self, closes: List[float]) -> float:
        """트렌드 강도 점수 계산"""
        try:
            if len(closes) < 20:
                return 0.0

            # 최근 20개 데이터의 변동성 계산
            recent_closes = closes[-20:]
            returns = []

            for i in range(1, len(recent_closes)):
                ret = (recent_closes[i] - recent_closes[i-1]) / recent_closes[i-1]
                returns.append(ret)

            # 변동성 기반 강도 점수
            volatility = np.std(returns)
            strength = min(1.0, volatility * 100)  # 0~1 범위로 정규화

            return float(strength)

        except Exception as e:
            self.logger.error(f"강도 점수 계산 오류: {e}")
            return 0.0

    def is_trend_confirmed(self, closes: List[float]) -> bool:
        """트렌드 확인 여부"""
        try:
            if len(closes) < 10:
                return False

            # 최근 10개 데이터의 방향성 확인
            recent_closes = closes[-10:]
            up_count = sum(1 for i in range(1, len(recent_closes))
                          if recent_closes[i] > recent_closes[i-1])

            # 60% 이상 상승하면 상승 트렌드 확인
            return up_count >= 6

        except Exception as e:
            self.logger.error(f"트렌드 확인 오류: {e}")
            return False

    def is_volume_confirmed(self, symbol: str, timeframe: str) -> bool:
        """거래량 확인 여부"""
        try:
            # 간단한 거래량 확인 (실제로는 더 복잡한 로직 필요)
            klines = self._get_klines(symbol, timeframe, 20)
            if not klines:
                return False

            volumes = [float(k[5]) for k in klines]
            avg_volume = np.mean(volumes)
            current_volume = volumes[-1]

            # 현재 거래량이 평균보다 높으면 확인
            return bool(current_volume > avg_volume)

        except Exception as e:
            self.logger.error(f"거래량 확인 오류: {e}")
            return False

    # 🔥 perform_pattern_based_optimization 메서드 제거됨 (optimizer.py에서 처리)

    # 🔥 get_recent_trades, analyze_trading_patterns 메서드 제거됨 (optimizer.py에서 처리)

    # 🔥 calculate_default_position_size 메서드 제거됨 (optimizer.py에서 처리)

    # 🔥 perform_ai_validation 메서드 제거됨 (optimizer.py에서 처리)

    # 🔥 determine_final_settings, log_optimization_results 메서드들 제거됨 (optimizer.py에서 처리)

    def _load_settings(self):
        """설정 로드 - config.settings.load_settings() 사용"""
        try:
            from config.settings import load_settings
            settings = load_settings()
            self.logger.info(f"✅ Analyzer 설정 로드 완료 (user_signal_threshold: {settings.get('analyzer_settings', {}).get('user_signal_threshold', 'N/A')})")
            return settings
        except Exception as e:
            self.logger.warning(f"⚠️ 설정 파일 로드 실패, 기본값 사용: {e}")
            # 기본 설정 반환
            return {
                'default_tp': 0.0018,
                'default_sl': 0.0020,
                'default_leverage': 1,
                'rsi_period': 14,
                'macd_fast': 12,
                'macd_slow': 26,
                'macd_signal': 9,
                'bb_period': 20,
                'bb_std': 2,
                'sma_short': 20,
                'sma_long': 50,
                'atr_period': 14,
                'volume_period': 20
            }

    def _analyze_current_market_conditions(self) -> Dict:
        """현재 시장 상황 분석"""
        try:
            # 거래소별로 실제 지원 가능성이 높은 대표 심볼만 사용한다.
            # 국내 현물 거래소에 BNBUSDT를 반복 요청하면 지원 심볼이 없어
            # 매 분석마다 불필요한 캔들 조회 경고가 발생한다.
            exchange_context = str(self._exchange_context or 'binance').lower().strip()
            if exchange_context in {'upbit', 'bithumb'}:
                representative_symbols = ['BTC/KRW', 'ETH/KRW']
            elif exchange_context == 'binance':
                representative_symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
            else:
                representative_symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT']

            # 메이저 코인들의 변동성 분석
            major_volatility = []
            for symbol in representative_symbols:
                try:
                    klines = self._get_klines(symbol, '15m', 20)
                    if klines:
                        closes = [float(k[4]) for k in klines]
                        if len(closes) >= 2:
                            volatility = abs(closes[-1] - closes[-2]) / closes[-2]
                            major_volatility.append(volatility)
                except:
                    continue

            # 시장 활동도 계산
            avg_volatility = np.mean(major_volatility) if major_volatility else 0.01
            market_score = avg_volatility * 10000  # 점수화

            # 활동 레벨 결정
            if market_score < 30:
                level = 'LOW'
            elif market_score < 80:
                level = 'NORMAL'
            else:
                level = 'HIGH'

            # 마지막 시장 레벨 저장
            self._last_market_level = level

            return {
                'level': level,
                'score': market_score,
                'volatility': avg_volatility,
                'timestamp': datetime.now()
            }

        except Exception as e:
            self.logger.error(f"시장 상황 분석 오류: {e}")
            return {
                'level': 'NORMAL',
                'score': 50.0,
                'volatility': 0.01,
                'timestamp': datetime.now()
            }

    def _get_ai_volatility_adjustment(self, symbol: str, market_analysis: Dict) -> float:
        """AI 학습 데이터 기반 변동성 조정 계수"""
        try:
            # AI 학습 매니저가 있는 경우 활용
            if hasattr(self, 'ai_learning_manager') and self.ai_learning_manager:
                recommendations = self.ai_learning_manager.provide_ai_recommendations(market_analysis)
                return recommendations.get('volatility_adjustment', 1.0)

            # 기본 AI 조정 로직
            market_level = market_analysis.get('level', 'NORMAL')
            market_score = market_analysis.get('score', 50.0)

            # 연속 실패 횟수 확인
            consecutive_failures = self.consecutive_losses.get(symbol, 0)

            # 조정 계수 계산
            if consecutive_failures > 3:
                # 연속 실패가 많으면 더 보수적으로
                adjustment = 1.2
            elif consecutive_failures > 1:
                adjustment = 1.1
            elif market_level == 'LOW' and market_score < 20:
                # 극도로 낮은 활동도면 더 공격적으로
                adjustment = 0.7
            else:
                adjustment = 1.0

            return adjustment

        except Exception as e:
            self.logger.error(f"AI 변동성 조정 계산 오류: {e}")
            return 1.0

    def _should_generate_signal_despite_low_volatility(self, symbol: str, current_vol: float,
                                                     threshold_vol: float, rsi: float, macd: float,
                                                     macd_signal: float, bb_position: float,
                                                     trend_strength: float, momentum: float) -> bool:
        """AI 기반 낮은 변동성에도 신호 생성 여부 결정"""
        try:
            # 시장 상황 분석
            market_analysis = self._analyze_current_market_conditions()
            market_level = market_analysis.get('level', 'NORMAL')
            market_score = market_analysis.get('score', 50.0)

            signal_score = 0
            reasons = []

            # 1. 극단적 RSI 조건 (변동성 무시하고 진입)
            if rsi <= 20 or rsi >= 80:
                signal_score += 40
                reasons.append(f"극단적 RSI({rsi:.1f})")
            elif rsi <= 30 or rsi >= 70:
                signal_score += 25
                reasons.append(f"강한 RSI 신호({rsi:.1f})")

            # 2. MACD 강한 신호
            macd_diff = abs(macd - macd_signal)
            if macd_diff > 0.001:  # 강한 MACD 신호
                signal_score += 20
                reasons.append(f"강한 MACD 신호({macd_diff:.4f})")

            # 3. 볼린저 밴드 극단 위치
            if bb_position <= 0.1 or bb_position >= 0.9:
                signal_score += 25
                reasons.append(f"BB 극단 위치({bb_position:.2f})")

            # 4. 강한 트렌드 모멘텀
            if abs(momentum) > 0.5:
                signal_score += 15
                reasons.append(f"강한 모멘텀({momentum:.2f})")

            # 5. 시장 상황 고려
            if market_level == 'LOW' and current_vol >= threshold_vol * 0.7:
                # 낮은 시장에서는 70% 변동성만 있어도 기회
                signal_score += 20
                reasons.append("시장 침체기 거래 기회")
            elif market_level == 'NORMAL' and current_vol >= threshold_vol * 0.8:
                signal_score += 10
                reasons.append("보통 시장 거래 기회")

            # 6. 연속 HOLD 횟수 고려 (거래 기회 증대)
            consecutive_holds = getattr(self, '_consecutive_holds', {}).get(symbol, 0)
            if consecutive_holds > 5:
                signal_score += 15
                reasons.append(f"연속 HOLD {consecutive_holds}회")

            # 7. AI 학습 데이터 기반 추천
            if hasattr(self, 'ai_learning_manager') and self.ai_learning_manager:
                ai_recommendations = self.ai_learning_manager.provide_ai_recommendations(market_analysis)
                if ai_recommendations.get('force_signal_generation', False):
                    signal_score += 20
                    reasons.append("AI 학습 기반 권장")

            # 최종 판단 (사용자 설정 기준 이상이면 신호 생성)
            active_threshold = self.get_user_signal_threshold()
            should_signal = signal_score >= active_threshold

            if should_signal:
                self.logger.info(f"🤖 AI 신호 생성 승인: {signal_score}점 (기준: {active_threshold}점)")
                self.logger.info(f"   - 이유: {', '.join(reasons)}")
                self.logger.info(f"   - 변동성: {current_vol:.4%} (기준: {threshold_vol:.4f}%)")

                # 연속 HOLD 카운터 리셋
                if not hasattr(self, '_consecutive_holds'):
                    self._consecutive_holds = {}
                self._consecutive_holds[symbol] = 0
            else:
                self.logger.info(f"🤖 AI 신호 생성 거부: {signal_score}점 (필요: {active_threshold}점)")
                if reasons:
                    self.logger.info(f"   - 고려 요소: {', '.join(reasons)}")

                # 연속 HOLD 카운터 증가
                if not hasattr(self, '_consecutive_holds'):
                    self._consecutive_holds = {}
                self._consecutive_holds[symbol] = self._consecutive_holds.get(symbol, 0) + 1

            return should_signal

        except Exception as e:
            self.logger.error(f"AI 신호 생성 판단 오류: {e}")
            return False

    def _determine_signal_with_ai_and_sentiment(self, indicators: TechnicalIndicators,
                                              market_state: MarketState, ai_analysis: Dict,
                                              sentiment_data) -> str:
        """AI 분석과 시장 심리를 결합한 신호 결정"""
        try:
            # 기본 AI 신호
            base_signal = self._determine_signal_with_ai(indicators, market_state, ai_analysis)

            # 시장 심리가 없으면 기본 신호 반환
            if not sentiment_data:
                return base_signal

            # 시장 심리 기반 신호 조정
            sentiment_score = sentiment_data.sentiment_score
            sentiment_level = sentiment_data.sentiment_level
            volume_spike = sentiment_data.volume_analysis.volume_spike
            funding_rate = sentiment_data.funding_rate.current_rate

            # 극도의 공포 시 매수 기회 (역발상)
            if sentiment_level.name == 'EXTREME_FEAR' and base_signal != 'SHORT':
                self.logger.info(f"극도의 공포 상황에서 LONG 신호 강화 (심리점수: {sentiment_score})")
                return 'LONG'

            # 극도의 탐욕 시 매도 신호 (역발상)
            elif sentiment_level.name == 'EXTREME_GREED' and base_signal != 'LONG':
                self.logger.info(f"극도의 탐욕 상황에서 SHORT 신호 고려 (심리점수: {sentiment_score})")
                return 'SHORT'

            # 거래량 급증 + 기본 신호가 있는 경우 신호 강화
            elif volume_spike and base_signal != 'HOLD':
                self.logger.info(f"거래량 급증으로 {base_signal} 신호 유지")
                return base_signal

            # 높은 펀딩비 (과도한 롱) 시 SHORT 고려
            elif funding_rate > 0.001 and base_signal != 'LONG':  # 0.1% 이상
                self.logger.info(f"높은 펀딩비로 SHORT 신호 고려 (펀딩비: {funding_rate:.4f})")
                return 'SHORT'

            # 낮은 펀딩비 (과도한 숏) 시 LONG 고려
            elif funding_rate < -0.001 and base_signal != 'SHORT':  # -0.1% 이하
                self.logger.info(f"낮은 펀딩비로 LONG 신호 고려 (펀딩비: {funding_rate:.4f})")
                return 'LONG'

            return base_signal

        except Exception as e:
            self.logger.error(f"AI+심리 신호 결정 오류: {e}")
            return self._determine_signal_with_ai(indicators, market_state, ai_analysis)

    def calculate_ai_optimized_parameters_with_sentiment(self, coin: str, signal: str,
                                                       indicators: TechnicalIndicators,
                                                       market_state: MarketState,
                                                       sentiment_data) -> Dict:
        """시장 심리를 고려한 AI 최적화 파라미터 계산"""
        try:
            # 기본 AI 파라미터
            base_params = self.calculate_ai_optimized_parameters(coin, signal, indicators, market_state)

            # 시장 심리가 없으면 기본 파라미터 반환
            if not sentiment_data:
                return base_params

            # 시장 심리 기반 조정
            sentiment_score = sentiment_data.sentiment_score
            volume_ratio = sentiment_data.volume_analysis.volume_ratio
            funding_rate = sentiment_data.funding_rate.current_rate

            # 기본값 복사
            adjusted_params = base_params.copy()
            adjustments = []

            # 1. 변동성 조정 (거래량 기반)
            if volume_ratio > 3.0:  # 거래량 급증
                adjusted_params['tp_percent'] *= 1.2  # TP 20% 증가
                adjusted_params['sl_percent'] *= 0.9  # SL 10% 감소 (타이트하게)
                adjustments.append("거래량급증으로 TP확대/SL축소")
            elif volume_ratio < 0.5:  # 거래량 감소
                adjusted_params['tp_percent'] *= 0.8  # TP 20% 감소
                adjusted_params['sl_percent'] *= 1.1  # SL 10% 증가 (여유있게)
                adjustments.append("거래량감소로 TP축소/SL확대")

            # 2. 신뢰도 조정 (시장 심리 기반)
            if abs(sentiment_score) > 60:  # 극단적 심리
                adjusted_params['entry_confidence'] = min(0.95, adjusted_params['entry_confidence'] * 1.1)
                adjustments.append("극단적심리로 신뢰도상승")
            elif abs(sentiment_score) < 20:  # 중립적 심리
                adjusted_params['entry_confidence'] = max(0.3, adjusted_params['entry_confidence'] * 0.9)
                adjustments.append("중립심리로 신뢰도하락")

            # 3. 레버리지 조정 (펀딩비 기반)
            if abs(funding_rate) > 0.001:  # 높은 펀딩비
                adjusted_params['leverage'] = max(1, int(adjusted_params['leverage'] * 0.8))
                adjustments.append("높은펀딩비로 레버리지축소")
            elif abs(funding_rate) < 0.0002:  # 낮은 펀딩비
                adjusted_params['leverage'] = min(10, int(adjusted_params['leverage'] * 1.1))
                adjustments.append("낮은펀딩비로 레버리지확대")

            # 조정 사유 업데이트
            original_reason = adjusted_params.get('optimization_reason', '')
            sentiment_adjustments = f"심리조정({'/'.join(adjustments)})"
            adjusted_params['optimization_reason'] = f"{original_reason} + {sentiment_adjustments}"

            return adjusted_params

        except Exception as e:
            self.logger.error(f"심리 기반 파라미터 조정 오류: {e}")
            return self.calculate_ai_optimized_parameters(coin, signal, indicators, market_state)
