#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
코인 후보군 선별 (점수 기반) 및 선정 이유 기록
"""

import numpy as np
import pandas as pd
import logging
import sys
import json
import time
import os
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import time
import os
import json
import shutil
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
from .symbol_validator import symbol_validator


class EvaluationCriteria(Enum):
    """평가 기준"""
    TECHNICAL_SCORE = "TECHNICAL_SCORE"
    VOLATILITY_SCORE = "VOLATILITY_SCORE"
    VOLUME_SCORE = "VOLUME_SCORE"
    TREND_SCORE = "TREND_SCORE"
    RISK_SCORE = "RISK_SCORE"
    OVERALL_SCORE = "OVERALL_SCORE"


@dataclass
class CoinCandidate:
    """코인 후보"""
    symbol: str
    overall_score: float
    technical_score: float
    volatility_score: float
    volume_score: float
    trend_score: float
    risk_score: float
    signal: str
    confidence: float
    reasoning: str
    recommendation: str
    timestamp: datetime


class Evaluator:
    """코인 평가 및 선정"""

    def __init__(self, analyzer, recorder, settings=None):
        """평가기 초기화"""
        self.analyzer = analyzer
        self.recorder = recorder
        # 동적 주입 클라이언트는 Any로 취급해 정적 분석 경고를 줄임
        self.binance_client: Any = getattr(analyzer, 'binance_client', None)

        # 로그 스팸 방지를 위한 경고 메시지 캐시
        self._warning_cache = set()

        # 설정값 로드 (환경변수 기본값을 settings.json과 일치시킴)
        self.FINAL_COIN_LIMIT = int(os.getenv('FINAL_COIN_LIMIT', '20'))  # 5 → 20 (settings.json max_total_coins와 일치)
        self.MIN_TOTAL_COINS = int(os.getenv('MIN_TOTAL_COINS', '10'))    # 5 → 10 (settings.json min_total_coins와 일치)
        self.MAX_TOTAL_COINS = int(os.getenv('MAX_TOTAL_COINS', '20'))    # 7 → 20 (settings.json max_total_coins와 일치)

        # 기본 코인 선택 개수 설정 (환경변수 기본값을 settings.json과 일치시킴)
        self.DEFAULT_NUM_ALT = int(os.getenv('DEFAULT_NUM_ALT', '15'))    # 3 → 15 (settings.json num_alt_coins와 일치)
        self.DEFAULT_NUM_MAJOR = int(os.getenv('DEFAULT_NUM_MAJOR', '5')) # 2 → 5 (settings.json num_major_coins와 일치)

        # 로거 설정 (먼저 설정)
        self.logger = logging.getLogger(__name__)

        # 🔥 로그 시스템 통일을 위한 헬퍼 메서드
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO', exchange=None: log_event(category, msg, exchange=exchange or 'global', level=level)

        # 설정 파일에서 값 읽기 (우선순위: 직접 전달된 settings > analyzer.settings > 환경변수)
        # 🔥 설정 우선순위: 1) 직접 전달된 settings > 2) analyzer.settings > 3) 환경변수 > 4) 코드 기본값
        if settings:
            self.settings = settings
            self.logger.info("직접 전달된 settings 객체 사용")
        elif hasattr(analyzer, 'settings') and analyzer.settings:
            self.settings = analyzer.settings
            self.logger.info("analyzer.settings 사용")
        else:
            self.settings = {}
            self.logger.warning("settings 객체를 찾을 수 없어 기본값 사용")

        # settings에서 값 읽기
        if self.settings:
            try:
                self.MIN_TOTAL_COINS = self.settings.get('min_total_coins', self.MIN_TOTAL_COINS)
                self.MAX_TOTAL_COINS = self.settings.get('max_total_coins', self.MAX_TOTAL_COINS)
                self.DEFAULT_NUM_ALT = self.settings.get('num_alt_coins', self.DEFAULT_NUM_ALT)
                self.DEFAULT_NUM_MAJOR = self.settings.get('num_major_coins', self.DEFAULT_NUM_MAJOR)
                self.logger.info(f"설정 파일에서 코인 선택 설정 로드: 알트{self.DEFAULT_NUM_ALT}개, 메이저{self.DEFAULT_NUM_MAJOR}개, 최소{self.MIN_TOTAL_COINS}개, 최대{self.MAX_TOTAL_COINS}개")
            except Exception as e:
                self.logger.warning(f"설정 파일 로드 실패, 기본값 사용: {e}")

        # 폴백 메이저 코인들
        self.FALLBACK_MAJOR_COINS = ['BTC', 'ETH', 'BNB', 'SOL', 'XRP']  # ALPACAUSDT 완전 제거

        # 코인 선택 캐시 및 상태
        self.selected_coins = []
        self.last_coin_update = None
        self.coin_selection_cache = {}
        self.cache_duration = timedelta(hours=1)
        self.last_cache_cleanup = datetime.now()

        # AI 학습 매니저 초기화 (거래소별)
        from .exchange_learning_manager import get_exchange_learning_manager
        # 학습 매니저는 런타임 팩토리 반환형이 유동적이므로 Any로 주석
        self.ai_learning_manager: Any = get_exchange_learning_manager("binance")  # 기본값

        # 캐시 정리
        self._cleanup_cache()

        # 🔥 누락된 성능 통계 초기화 추가
        self.coin_selection_performance = {
            'cache_hits': 0,
            'cache_misses': 0,
            'total_selections': 0,
            'avg_selection_time': 0.0
        }

        self.logger.info("Evaluator 초기화 완료")
        # 🔇 Invalid symbol 중복 경고 억제(최초 1회만 warning, 이후 debug)
        self._invalid_symbol_warned = set()

    def switch_exchange_learning(self, exchange: str):
        """거래소별 학습 매니저 전환"""
        try:
            from .exchange_learning_manager import get_exchange_learning_manager
            self.ai_learning_manager = get_exchange_learning_manager(exchange)
            self.logger.info(f"학습 매니저를 {exchange.upper()}로 전환 완료")
        except Exception as e:
            self.logger.error(f"거래소 학습 매니저 전환 오류: {e}")

    def _cleanup_cache(self):
        """캐시 정리"""
        current_time = datetime.now()
        expired_keys = []

        for key, (data, cache_time) in self.coin_selection_cache.items():
            if current_time - cache_time > self.cache_duration:
                expired_keys.append(key)

        for key in expired_keys:
            del self.coin_selection_cache[key]

        if expired_keys:
            self.logger.debug(f"캐시 정리 완료: {len(expired_keys)}개 항목 제거")

    def _load_backup_symbols(self, backup_file):
        """백업 심볼 목록 로드"""
        try:
            if os.path.exists(backup_file):
                with open(backup_file, 'r', encoding='utf-8') as f:
                    backup_data = json.load(f)
                    self.logger.info(f"백업 심볼 목록 로드: {len(backup_data.get('symbols', []))}개")
                    return backup_data
            else:
                # 최종 백업: 하드코딩된 주요 심볼들
                self.logger.warning("백업 파일 없음 - 하드코딩된 심볼 사용")
                return {
                    'symbols': [
                        {'symbol': symbol, 'contract_type': 'PERPETUAL', 'status': 'TRADING'}
                        for symbol in [
                            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ADAUSDT', 'XRPUSDT', 'DOTUSDT', 'LINKUSDT', 'AVAXUSDT', 'MATICUSDT',
                            'ALGOUSDT', 'XMRUSDT', 'SUSHIUSDT', 'KAVAUSDT', 'DASHUSDT', 'ATOMUSDT', 'TRBUSDT', 'VETUSDT', 'THETAUSDT', 'BATUSDT',
                            'COMPUSDT', 'FLMUSDT', 'NEOUSDT', 'BANDUSDT', 'ZECUSDT', 'IOTAUSDT', 'FILUSDT', 'AAVEUSDT', 'UNIUSDT', 'CAKEUSDT'
                        ]
                    ]
                }
        except Exception as e:
            self.logger.error(f"백업 심볼 로드 실패: {e}")
            return {'symbols': []}

    def _save_backup_symbols(self, backup_file, valid_symbols):
        """백업 심볼 목록 저장"""
        try:
            backup_data = {
                'symbols': [
                    {'symbol': symbol, 'contract_type': 'PERPETUAL', 'status': 'TRADING'}
                    for symbol in valid_symbols[:50]  # 상위 50개만 저장
                ],
                'timestamp': time.time(),
                'count': len(valid_symbols)
            }
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"백업 심볼 목록 저장: {len(valid_symbols)}개")
        except Exception as e:
            self.logger.warning(f"백업 심볼 저장 실패: {e}")

    def select_trading_coins(self, num_alt=15, num_major=5, regime: Optional[str] = None, exchange: Optional[str] = None, exchange_client=None):
        """🔥 통합된 트레이딩 코인 선정 시스템"""
        self.logger.info(f"🔍 코인 선정 시작 - 알트: {num_alt}개, 메이저: {num_major}개")
        _t_total_start = time.perf_counter()
        _t_stage = {}

        # 거래소별 학습 매니저 전환
        if exchange:
            self.switch_exchange_learning(exchange)
            self.logger.info(f"거래소 전환: {exchange.upper()}")

        try:
            # 🔥 1. 거래소별 코인 분석
            _t_analysis_start = time.perf_counter()
            valid_coins = self._analyze_candidate_coins_by_exchange(
                exchange=exchange,
                exchange_client=exchange_client,
                adjustment_factor=1.0,
            )
            _t_stage['analysis'] = time.perf_counter() - _t_analysis_start
            self.logger.info(f"✅ 기본 분석 완료: {len(valid_coins)}개 유효한 코인")

            # 🔥 항상 _select_final_coins 호출 (코인 수 부족해도)
            self.logger.info(f"🎯 _select_final_coins 호출 시작")
            _t_select_start = time.perf_counter()
            selected_coins = self._select_final_coins(valid_coins, num_alt, num_major, regime)
            _t_stage['select_final'] = time.perf_counter() - _t_select_start
            self.logger.info(f"✅ _select_final_coins 완료: {len(selected_coins)}개 코인 선정")

            # 🔥 점수 데이터가 포함된 코인 정보 반환
            scored_coins = []
            for coin in selected_coins:
                if isinstance(coin, dict) and 'overall_score' in coin:
                    scored_coins.append(coin)
                else:
                    # 점수 데이터가 없는 경우 기본값 설정
                    coin_info = {
                        'symbol': coin if isinstance(coin, str) else str(coin),
                        'overall_score': 50.0,
                        'technical_score': 50.0,
                        'volatility_score': 50.0,
                        'volume_score': 50.0,
                        'trend_score': 50.0,
                        'risk_score': 50.0
                    }
                    scored_coins.append(coin_info)

            # 🔥 선택된 코인 수 검증
            if len(scored_coins) >= (num_alt + num_major):
                self.logger.info(f"🎯 목표 달성: {len(scored_coins)}개 >= {num_alt + num_major}개")

                # 🔥 코인 선택 데이터를 데이터베이스에 저장
                _t_db_start = time.perf_counter()
                self.logger.info("🔍 DEBUG: save_coin_selection 호출 직전")
                try:
                    if hasattr(self, 'recorder') and self.recorder:
                        self.logger.info("🔍 DEBUG: recorder 존재 확인됨")
                        session_id = self.recorder.save_coin_selection(
                            selected_coins=scored_coins,
                            num_alt=num_alt,
                            num_major=num_major,
                            market_regime=regime or 'neutral',
                            selection_reason='initial_selection',
                            adjustment_factor=1.0
                        )
                        if session_id > 0:
                            self.logger.info(f"✅ 코인 선택 데이터 저장 완료: 세션 ID {session_id}")
                        else:
                            self.logger.warning("⚠️ 코인 선택 데이터 저장 실패")
                    else:
                        self.logger.warning("⚠️ Recorder가 초기화되지 않음 - 데이터 저장 건너뜀")
                except Exception as e:
                    self.logger.error(f"❌ 코인 선택 데이터 저장 중 오류: {e}")
                finally:
                    _t_stage['db_save'] = time.perf_counter() - _t_db_start

                # 🔥 AI 평가 단계 추가
                _t_ai_start = time.perf_counter()
                self.logger.info("🤖 AI 평가 단계 시작...")
                try:
                    # 선택된 코인 심볼 리스트 생성
                    selected_symbols = [coin['symbol'] for coin in scored_coins]

                    # AI 평가 실행
                    ai_evaluated_coins = self._evaluate_coins_with_ai(valid_coins, selected_symbols)

                    if ai_evaluated_coins:
                        self.logger.info(f"✅ AI 평가 완료: {len(ai_evaluated_coins)}개 코인 평가됨")
                        # AI 평가 결과를 DB에 저장
                        self._save_coin_evaluation_to_db(ai_evaluated_coins)
                    else:
                        self.logger.warning("⚠️ AI 평가 결과 없음")

                except Exception as e:
                    self.logger.error(f"❌ AI 평가 중 오류: {e}")
                finally:
                    _t_stage['ai_eval'] = time.perf_counter() - _t_ai_start

                self.logger.info("🔍 DEBUG: evaluator에서 return 직전")
                total_elapsed = time.perf_counter() - _t_total_start
                self.logger.info(f"⏱️ 코인 선정 전체 소요시간(기본선정 성공): {total_elapsed:.2f}s | 단계별: {_t_stage}")
                try:
                    self.coin_selection_performance['total_selections'] += 1
                    ts = self.coin_selection_performance['total_selections']
                    prev_avg = self.coin_selection_performance['avg_selection_time']
                    self.coin_selection_performance['avg_selection_time'] = ((prev_avg * (ts-1)) + total_elapsed) / ts
                except Exception:
                    pass
                return selected_coins
            else:
                self.logger.warning(f"⚠️ 목표 미달성: {len(selected_coins)}개 < {num_alt + num_major}개 필요")

            # 🔥 2. 코인이 부족하면 기준 완화 (통합된 로직 사용)
            self.logger.warning(f"코인 부족 ({len(selected_coins)}개), 기준 완화 시작")
            _t_stage['before_fallback'] = time.perf_counter() - _t_total_start

            # 설정에서 adjustment_factors 가져오기
            try:
                strategy_config = getattr(self, 'settings', {}).get('trading_strategies', {}).get('scalping', {})
                adjustment_factors = strategy_config.get('adjustment_factors', {}).get('fallback_levels', [0.7, 0.5, 0.3, 0.1])
            except:
                adjustment_factors = [0.7, 0.5, 0.3, 0.1]  # 기본값

            self.logger.info(f"📊 사용할 조정계수: {adjustment_factors}")

            for factor in adjustment_factors:
                self.logger.info(f"기준 {((1-factor)*100):.0f}% 완화 시도 (조정계수: {factor})...")
                _t_fb_iter_start = time.perf_counter()
                # 🔥 통합된 메서드 사용 (adjustment_factor로 기준 조절)
                adjusted_coins = self._analyze_candidate_coins_by_exchange(
                    exchange=exchange,
                    exchange_client=exchange_client,
                    adjustment_factor=factor,
                )
                self.logger.info(f"⏱️ 기준 완화 분석 소요시간: {factor:.2f} → {len(adjusted_coins) if adjusted_coins else 0}개, {(time.perf_counter()-_t_fb_iter_start):.2f}s")

                if len(adjusted_coins) >= (num_alt + num_major):
                    _t_fb_select_start = time.perf_counter()
                    selected_coins = self._select_final_coins(adjusted_coins, num_alt, num_major, regime)
                    self.logger.info(f"⏱️ 기준 완화 최종선정 소요시간: {(time.perf_counter()-_t_fb_select_start):.2f}s")
                    self.logger.info(f"기준 완화로 {len(selected_coins)}개 코인 선정 (조정계수: {factor})")
                    total_elapsed = time.perf_counter() - _t_total_start
                    self.logger.info(f"⏱️ 코인 선정 전체 소요시간(폴백 완료): {total_elapsed:.2f}s | 단계별: {_t_stage}")
                    try:
                        self.coin_selection_performance['total_selections'] += 1
                        ts = self.coin_selection_performance['total_selections']
                        prev_avg = self.coin_selection_performance['avg_selection_time']
                        self.coin_selection_performance['avg_selection_time'] = ((prev_avg * (ts-1)) + total_elapsed) / ts
                    except Exception:
                        pass
                    return selected_coins

            # 🔥 3. 모든 시도 실패 시 메이저 코인으로 폴백 (극한 상황에서만)
            self.logger.warning("🚨 모든 기준 완화 시도 실패 → 메이저 코인으로 폴백")
            total_elapsed = time.perf_counter() - _t_total_start
            self.logger.info(f"⏱️ 코인 선정 전체 소요시간(폴백 실패): {total_elapsed:.2f}s | 단계별: {_t_stage}")
            try:
                self.coin_selection_performance['total_selections'] += 1
                ts = self.coin_selection_performance['total_selections']
                prev_avg = self.coin_selection_performance['avg_selection_time']
                self.coin_selection_performance['avg_selection_time'] = ((prev_avg * (ts-1)) + total_elapsed) / ts
            except Exception:
                pass
            fallback_coins = self._fallback_to_major_coins(num_alt + num_major, exchange=exchange)
            self.logger.info(f"🔄 폴백 결과: {len(fallback_coins)}개 메이저 코인 반환")
            return fallback_coins

        except Exception as e:
            self.logger.error(f"코인 선정 오류: {e}")
            # 오류 시 기본 메이저 코인 반환
            return self._fallback_to_major_coins(num_alt + num_major, exchange=exchange)

    def _analyze_candidate_coins_by_exchange(
        self,
        exchange: Optional[str],
        exchange_client=None,
        adjustment_factor: float = 1.0,
    ):
        """거래소 컨텍스트를 유지한 후보 코인 분석 디스패처.

        주의: 기준 완화(fallback) 단계에서도 반드시 동일한 거래소 경로를 사용해야
        업비트/빗썸에서 바이낸스 USDT 심볼이 혼입되지 않는다.
        """
        ex = str(exchange or '').strip().lower()
        if ex in ('upbit', 'bithumb'):
            self.logger.info(f"🔍 현물 거래소 코인 분석 시작: {ex.upper()}")
            if exchange_client:
                return self._analyze_candidate_coins_spot(exchange_client, adjustment_factor=adjustment_factor)
            self.logger.warning(f"{ex.upper()} 클라이언트 없음 - 현물 기본 코인 분석 폴백 사용")
            return []
        if ex in ('bybit', 'okx', 'bitget'):
            self.logger.info(f"🔍 CCXT 선물 거래소 코인 분석 시작: {ex.upper()}")
            if exchange_client and hasattr(exchange_client, 'exchange'):
                return self._analyze_candidate_coins_ccxt_futures(exchange_client, adjustment_factor=adjustment_factor)
            self.logger.warning(f"{ex.upper()} 어댑터 없음 - 선물 기본 코인 분석 폴백 사용")
            return []

        # 기본 경로: 바이낸스 선물
        self.logger.info("🔍 바이낸스 선물 거래소 코인 분석 시작")
        return self._analyze_candidate_coins(adjustment_factor=adjustment_factor)

    def _analyze_market_activity(self):
        """시장 활동 분석 (원래 autotrade.py 기반)"""
        try:
            self.logger.info("🔍 시장 활동 분석 시작...")

            # 바이낸스에서 모든 USDT 페어 가져오기
            tickers = self.binance_client.get_futures_ticker()
            usdt_pairs = [t for t in tickers if t['symbol'].endswith('USDT')]

            # 메이저 코인과 알트코인 분리
            major_coins = ['BTC', 'ETH', 'BNB']
            major_tickers = [t for t in usdt_pairs if t['symbol'].replace('USDT', '') in major_coins]
            alt_tickers = [t for t in usdt_pairs if t['symbol'].replace('USDT', '') not in major_coins]

            # 메이저 코인 활동도 계산
            major_volatility = []
            for ticker in major_tickers:
                try:
                    change_1h = abs(float(ticker.get('priceChangePercent', 0)))
                    major_volatility.append(change_1h)
                except:
                    continue

            avg_major_vol = sum(major_volatility) / len(major_volatility) if major_volatility else 0
            major_activity = min(100, avg_major_vol * 10)  # 변동성을 활동도로 변환

            # 알트코인 활동도 계산
            alt_volatility = []
            for ticker in alt_tickers[:50]:  # 상위 50개만 분석
                try:
                    change_1h = abs(float(ticker.get('priceChangePercent', 0)))
                    alt_volatility.append(change_1h)
                except:
                    continue

            avg_alt_vol = sum(alt_volatility) / len(alt_volatility) if alt_volatility else 0
            alt_activity = min(100, avg_alt_vol * 6)  # 알트코인은 더 민감하게

            # 전체 활동도 계산
            total_activity = (major_activity * 0.3) + (alt_activity * 0.7)

            # 활동 레벨 결정
            if total_activity > 80:
                activity_level = "HIGH"
            elif total_activity > 50:
                activity_level = "NORMAL"
            else:
                activity_level = "LOW"

            # 평균 변동성과 거래량 스파이크 계산 (원래 로그와 동일)
            all_volatility = []
            all_volume_spikes = []

            for ticker in usdt_pairs[:100]:  # 상위 100개만 분석
                try:
                    change_1h = abs(float(ticker.get('priceChangePercent', 0)))
                    all_volatility.append(change_1h)

                    # 거래량 스파이크는 간단히 계산
                    volume = float(ticker.get('volume', 0))
                    if volume > 0:
                        all_volume_spikes.append(volume)
                except:
                    continue

            avg_volatility = sum(all_volatility) / len(all_volatility) if all_volatility else 0
            avg_volume_spike = sum(all_volume_spikes) / len(all_volume_spikes) if all_volume_spikes else 1.0

            self.logger.info(f"""
            시장 활동 분석:
            - 메이저 코인 활동도: {major_activity:.2f} (평균 변동성: {avg_major_vol:.2f}%)
            - 알트코인 활동도: {alt_activity:.2f} (평균 변동성: {avg_alt_vol:.2f}%)
            - 전체 활동도: {total_activity:.2f}
            - 활동 레벨: {activity_level}
            - 선택된 후보: 100개 코인

            현재 시장 분석:
            - 시장 활동: {activity_level} (점수: {total_activity:.2f})
            - 평균 변동성: {avg_volatility:.2f}%
            - 평균 거래량 스파이크: {avg_volume_spike:.2f}x
            - 선택된 후보: 100개 코인
            """)

            return {
                'level': activity_level,
                'score': total_activity,
                'major_activity': major_activity,
                'alt_activity': alt_activity,
                'avg_major_vol': avg_major_vol,
                'avg_alt_vol': avg_alt_vol
            }

        except Exception as e:
            self.logger.error(f"시장 활동 분석 오류: {e}")
            return {'level': 'NORMAL', 'score': 50.0}

    def _analyze_candidate_coins(self, adjustment_factor=1.0):
        """🔥 통합된 코인 선택 로직 - autotrade.py 방식으로 수정"""
        try:
            self.logger.info(f"📊 _analyze_candidate_coins() 시작 (조정계수: {adjustment_factor:.2f})")
            _t_total_start = time.perf_counter()
            _dur = { 'exchange_info': 0.0, 'symbol_filter': 0.0, 'ticker_load': 0.0, 'verify_1m': 0.0, 'klines_1h': 0.0, 'merge': 0.0 }

            # 🔥 최적화: 거래소 정보 캐싱으로 4분 지연 해결
            self.logger.info("바이낸스 거래소 정보에서 유효한 거래 심볼만 가져오는 중...")

            # 🔥 하이브리드 접근법: 캐싱 + 백업 심볼 목록
            cache_file = "data/nwsoft/cache/exchange_info.json"
            backup_symbols_file = "data/nwsoft/cache/backup_symbols.json"
            import os
            import json


            # 캐시 디렉토리 생성
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)

            # 🔥 1단계: 캐시 확인 (1시간 이내)
            _t_exinfo_start = time.perf_counter()
            if os.path.exists(cache_file):
                cache_age = time.time() - os.path.getmtime(cache_file)
                if cache_age < 3600:  # 1시간
                    self.logger.info("캐시된 거래소 정보 사용 (빠른 로딩)")
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        exchange_info = json.load(f)
                else:
                    self.logger.info("캐시 만료 - 새로 가져오는 중...")
                    try:
                        exchange_info = self.binance_client.get_exchange_info()
                        with open(cache_file, 'w', encoding='utf-8') as f:
                            json.dump(exchange_info, f, ensure_ascii=False, indent=2)
                        self.logger.info("거래소 정보 캐시 저장 완료")
                    except Exception as e:
                        self.logger.warning(f"API 호출 실패, 백업 심볼 사용: {e}")
                        exchange_info = self._load_backup_symbols(backup_symbols_file)
            else:
                self.logger.info("캐시 없음 - API 호출 중...")
                try:
                    exchange_info = self.binance_client.get_exchange_info()
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(exchange_info, f, ensure_ascii=False, indent=2)
                    self.logger.info("거래소 정보 캐시 저장 완료")
                except Exception as e:
                    self.logger.warning(f"API 호출 실패, 백업 심볼 사용: {e}")
                    exchange_info = self._load_backup_symbols(backup_symbols_file)
            _dur['exchange_info'] = time.perf_counter() - _t_exinfo_start

            if not exchange_info or 'symbols' not in exchange_info:
                self.logger.error("거래소 정보를 가져올 수 없음")
                return []

            # 🔥 1단계: 유효한 거래 심볼만 필터링 (원래 로직 복원)
            _t_symbol_start = time.perf_counter()
            valid_symbols = []
            for symbol_info in exchange_info['symbols']:
                symbol = symbol_info['symbol']

                # 기본 필터링: USDT 페어만
                if not symbol.endswith('USDT'):
                    continue

                # 추가 필터링: _is_valid_symbol 적용
                if not self._is_valid_symbol(symbol):
                    continue

                valid_symbols.append(symbol)
            _dur['symbol_filter'] = time.perf_counter() - _t_symbol_start
            self.logger.info(f"🔍 유효한 거래 심볼 필터링 완료: {len(valid_symbols)}개")

            # 🔥 백업 심볼 목록 저장 (API 실패 시 대비)
            self._save_backup_symbols(backup_symbols_file, valid_symbols)

            # PERPETUAL 계약만 필터링된 상태 확인
            perpetual_count = sum(1 for s in exchange_info['symbols'] if s.get('contract_type') == 'PERPETUAL')
            self.logger.info(f"PERPETUAL 계약 심볼: {perpetual_count}개")

            if not valid_symbols:
                self.logger.warning("유효한 거래 심볼이 없음")
                return []

            # 🔥 2단계: 24h 티커 데이터 조회 (캐시 + 일괄 조회)
            self.logger.info("24h 티커 데이터를 조회하는 중...")

            _t_ticker_start = time.perf_counter()
            try:
                # 🔥 캐시된 티커 데이터 확인 (5분 이내)
                ticker_cache_file = "data/nwsoft/cache/ticker_data.json"
                valid_tickers = []

                if os.path.exists(ticker_cache_file):
                    cache_age = time.time() - os.path.getmtime(ticker_cache_file)
                    if cache_age < 300:  # 5분
                        self.logger.info("캐시된 티커 데이터 사용 (빠른 로딩)")
                        with open(ticker_cache_file, 'r', encoding='utf-8') as f:
                            cached_tickers = json.load(f)

                        # 유효한 심볼들만 필터링
                        valid_symbols_set = set(valid_symbols[:100])
                        for ticker in cached_tickers:
                            if ticker and 'symbol' in ticker:
                                symbol = ticker['symbol']
                                if symbol in valid_symbols_set:
                                    valid_tickers.append(ticker)

                        self.logger.info(f"✅ 캐시된 티커 데이터 사용: {len(valid_tickers)}개")
                    else:
                        self.logger.info("캐시 만료 - 새로 조회 중...")
                        valid_tickers = self._fetch_ticker_data(valid_symbols)
                else:
                    self.logger.info("캐시 없음 - 새로 조회 중...")
                    valid_tickers = self._fetch_ticker_data(valid_symbols)

                # 캐시 저장
                if valid_tickers:
                    os.makedirs(os.path.dirname(ticker_cache_file), exist_ok=True)
                    with open(ticker_cache_file, 'w', encoding='utf-8') as f:
                        json.dump(valid_tickers, f, ensure_ascii=False, indent=2)
                    self.logger.info("티커 데이터 캐시 저장 완료")

            except Exception as e:
                self.logger.error(f"❌ 24h 티커 조회 실패: {e}")
                return []
            finally:
                _dur['ticker_load'] = time.perf_counter() - _t_ticker_start

            if not valid_tickers:
                self.logger.warning("유효한 24h 티커 데이터가 없음")
                return []

            # 🔥 3단계: 거래량 기준으로 정렬 및 선택
            target_count = int(100 * adjustment_factor)
            volume_sorted = sorted(valid_tickers, key=lambda x: float(x.get('quoteVolume', 0)), reverse=True)
            selected_tickers = volume_sorted[:target_count]

            self.logger.info(f"상위 {target_count}개 거래량 코인 선택 완료")

            # 3.5단계 제거됨 - 중복 제거
            # K라인 데이터 수집은 4단계에서만 수행

            # 🔥 4단계: 선택된 코인들에 대한 상세 데이터 수집 (Invalid symbol 오류 처리)
            self.logger.info(f"{target_count}개 심볼에 대한 K라인 데이터 수집 중...")
            symbols = [ticker['symbol'] for ticker in selected_tickers]

            # 🔥 4.1단계: K라인 데이터 수집 전 추가 검증
            self.logger.info("K라인 데이터 수집 전 추가 검증 시작...")
            _t_verify_start = time.perf_counter()
            verified_symbols = []

            for symbol in symbols:
                try:
                    # 심볼 검증 먼저 수행
                    if not symbol_validator.is_valid_symbol('binance', symbol):
                        self.logger.warning(f"🚨 {symbol}: 심볼 포맷 검증 실패 - 제외")
                        continue

                    # 간단한 K라인 데이터 1개만 테스트
                    test_klines = self.binance_client.get_klines(symbol, '1m', 1)
                    if test_klines and len(test_klines) > 0:
                        verified_symbols.append(symbol)
                        self.logger.debug(f"✅ {symbol}: K라인 데이터 수집 가능 확인")
                    else:
                        self.logger.warning(f"⚠️ {symbol}: K라인 데이터 없음 - 제외")
                except Exception as e:
                    if "Invalid symbol" in str(e):
                        if symbol not in self._invalid_symbol_warned:
                            self._invalid_symbol_warned.add(symbol)
                            self.logger.warning(f"🚨 {symbol}: Invalid symbol 확인됨 - 제외")
                        else:
                            self.logger.debug(f"🚫 {symbol}: Invalid symbol(중복) - 로그 억제, 제외")
                    else:
                        self.logger.warning(f"❌ {symbol}: 테스트 실패 - 제외: {e}")

            self.logger.info(f"✅ K라인 데이터 검증 완료: {len(verified_symbols)}개")
            _dur['verify_1m'] = time.perf_counter() - _t_verify_start

            if not verified_symbols:
                self.logger.warning("검증된 심볼이 없음")
                return []

            # 🔥 5단계: 검증된 심볼들에 대한 K라인 데이터 수집 및 분석
            self.logger.info(f"{len(verified_symbols)}개 검증된 심볼에 대한 K라인 데이터 수집 중...")

            # 병렬로 K라인 데이터 수집
            def collect_kline_data(symbol):
                try:
                    # 1시간 K라인 데이터 100개 수집
                    klines = self.binance_client.get_klines(symbol, '1h', 100)
                    if klines and len(klines) >= 50:  # 최소 50개 데이터 필요
                        return {
                            'symbol': symbol,
                            'klines': klines,
                            'base_symbol': symbol.replace('USDT', ''),
                            'volume': 0,
                            'quoteVolume': 0,
                            'count': 0,
                            'priceChange': 0,
                            'priceChangePercent': 0
                        }
                    return None
                except Exception as e:
                    self.logger.debug(f"❌ {symbol}: K라인 데이터 수집 실패: {e}")
                    return None

            # 병렬 처리로 K라인 데이터 수집
            _t_klines_start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=10) as executor:
                kline_results = list(executor.map(collect_kline_data, verified_symbols))
            _dur['klines_1h'] = time.perf_counter() - _t_klines_start

            # None 결과 제거
            valid_coins = [k for k in kline_results if k is not None]
            self.logger.info(f"✅ K라인 데이터 수집 완료: {len(valid_coins)}개")

            # 🔥 6단계: 24h 티커 데이터와 K라인 데이터 병합
            self.logger.info("24h 티커 데이터와 K라인 데이터 병합 중...")
            _t_merge_start = time.perf_counter()

            # 티커 데이터를 심볼별로 딕셔너리화
            ticker_dict = {t['symbol']: t for t in valid_tickers}

            # K라인 데이터에 티커 정보 병합
            for coin in valid_coins:
                symbol = coin['symbol']
                if symbol in ticker_dict:
                    ticker = ticker_dict[symbol]
                    coin.update({
                        'volume': float(ticker.get('volume', 0)),
                        'quoteVolume': float(ticker.get('quoteVolume', 0)),
                        'count': int(ticker.get('count', 0)),
                        'priceChange': float(ticker.get('priceChange', 0)),
                        'priceChangePercent': float(ticker.get('priceChangePercent', 0))
                    })
            _dur['merge'] = time.perf_counter() - _t_merge_start

            # 🔥 7단계: 메이저 코인과 알트코인 분리 확인
            major_coins = [coin for coin in valid_coins if coin.get('is_major', False)]
            alt_coins = [coin for coin in valid_coins if not coin.get('is_major', False)]

            self.logger.info(f"🎯 최종 결과: 메이저 코인 {len(major_coins)}개, 알트코인 {len(alt_coins)}개")

            total_elapsed = time.perf_counter() - _t_total_start
            self.logger.info(f"⏱️ 후보 코인 분석 소요시간: {total_elapsed:.2f}s | 단계별(ms): "
                             f"exchange_info={_dur['exchange_info']*1000:.0f}, "
                             f"symbol_filter={_dur['symbol_filter']*1000:.0f}, "
                             f"ticker_load={_dur['ticker_load']*1000:.0f}, "
                             f"verify_1m={_dur['verify_1m']*1000:.0f}, "
                             f"klines_1h={_dur['klines_1h']*1000:.0f}, "
                             f"merge={_dur['merge']*1000:.0f}")
            return valid_coins

        except Exception as e:
            self.logger.error(f"❌ _analyze_candidate_coins 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []

    def _fetch_ticker_data(self, valid_symbols):
        """24h 티커 데이터 조회 (일괄 조회)"""
        try:
            # 🔥 최적화: 개별 조회 대신 일괄 조회 사용
            all_tickers = self.binance_client.get_all_24h_tickers()
            self.logger.info(f"✅ 전체 24h 티커 데이터 수집 완료: {len(all_tickers)}개")

            # 유효한 심볼들만 필터링
            valid_tickers = []
            valid_symbols_set = set(valid_symbols[:100])  # 상위 100개로 확장

            for ticker in all_tickers:
                if ticker and 'symbol' in ticker:
                    symbol = ticker['symbol']
                    if symbol in valid_symbols_set:
                        valid_tickers.append(ticker)

            self.logger.info(f"✅ 필터링된 24h 티커 데이터: {len(valid_tickers)}개")
            return valid_tickers

        except Exception as e:
            self.logger.error(f"❌ 티커 데이터 조회 실패: {e}")
            return []

    def _analyze_candidate_coins_spot(self, exchange_client, adjustment_factor=1.0):
        """현물 거래소용 코인 분석 (업비트/빗썸)"""
        try:
            self.logger.info(f"📊 현물 거래소 코인 분석 시작 (조정계수: {adjustment_factor:.2f})")
            _t_total_start = time.perf_counter()

            # API 제한 확인
            if self.ai_learning_manager.should_apply_api_delay():
                delay = self.ai_learning_manager.get_analysis_delay()
                self.logger.info(f"API 제한으로 인한 딜레이 적용: {delay}초")
                time.sleep(delay)

            # 최대 분석 코인 수 제한
            max_coins = self.ai_learning_manager.get_max_coins_for_analysis()
            self.logger.info(f"최대 분석 코인 수: {max_coins}개")

            # 거래소별 코인 목록 가져오기 (어댑터 구현 차이 호환)
            markets = None
            if hasattr(exchange_client, 'get_markets'):
                try:
                    markets = exchange_client.get_markets()
                except Exception:
                    markets = None

            # 일부 어댑터는 get_exchange_info만 제공하므로 여기서 표준 형태로 변환
            if not markets and hasattr(exchange_client, 'get_exchange_info'):
                try:
                    ex_info = exchange_client.get_exchange_info() or {}
                    symbols = ex_info.get('symbols', []) if isinstance(ex_info, dict) else []
                    normalized = {}
                    for item in symbols:
                        if not isinstance(item, dict):
                            continue
                        sym = str(item.get('symbol') or '').strip()
                        if not sym:
                            continue
                        quote = str(item.get('quoteAsset') or '').upper().strip()
                        base = str(item.get('baseAsset') or '').upper().strip()
                        active = str(item.get('status') or 'TRADING').upper() == 'TRADING'
                        normalized[sym] = {
                            'symbol': sym,
                            'quote': quote,
                            'base': base,
                            'active': active,
                        }
                    markets = normalized
                except Exception:
                    markets = None

            if markets:
                if not markets:
                    self.logger.warning("거래소에서 마켓 정보를 가져올 수 없음")
                    return []

                # KRW 페어만 필터링 (현물 거래소) + 전량 티커 조회 후 거래량 기준 정렬
                krw_pairs = []
                for symbol, market in markets.items():
                    if market.get('quote') == 'KRW' and market.get('active', False):
                        krw_pairs.append({
                            'symbol': symbol,
                            'base': market.get('base'),
                            'quote': market.get('quote'),
                            'active': market.get('active', False)
                        })

                self.logger.info(f"KRW 페어 발견: {len(krw_pairs)}개")

                # 모든 후보에 대해 티커 조회 → 거래량(quoteVolume) 수집
                volume_scored = []
                for pair in krw_pairs:
                    try:
                        symbol = pair['symbol']
                        if hasattr(exchange_client, 'fetch_ticker'):
                            ticker = exchange_client.fetch_ticker(symbol)
                        elif hasattr(exchange_client, 'exchange') and getattr(exchange_client, 'exchange', None) is not None:
                            ticker = exchange_client.exchange.fetch_ticker(symbol)
                        else:
                            ticker = None
                        qv = float((ticker or {}).get('quoteVolume', 0) or 0)
                        volume_scored.append((qv, pair, ticker))
                        if self.ai_learning_manager.should_apply_api_delay():
                            time.sleep(self.ai_learning_manager.get_analysis_delay())
                    except Exception as e:
                        self.logger.debug(f"❌ {pair.get('symbol')}: 데이터 수집 실패: {e}")
                        continue

                # 거래량 기준 정렬 후 상위 target_count만 최종 선정
                target_count = int(max_coins * adjustment_factor)
                volume_scored.sort(key=lambda x: x[0], reverse=True)
                top = volume_scored[:target_count]

                valid_coins = []
                for qv, pair, ticker in top:
                    if not ticker:
                        continue
                    try:
                        symbol = pair['symbol']
                        coin_data = {
                            'symbol': symbol,
                            'base_symbol': pair['base'],
                            'is_major': pair['base'] in ['BTC', 'ETH', 'XRP', 'ADA', 'DOT'],
                            'volume': float(ticker.get('quoteVolume', 0) or 0),
                            'quoteVolume': float(ticker.get('quoteVolume', 0) or 0),
                            'priceChangePercent': float(ticker.get('percentage', 0) or 0),
                            'lastPrice': float(ticker.get('last', 0) or 0),
                            'high': float(ticker.get('high', 0) or 0),
                            'low': float(ticker.get('low', 0) or 0)
                        }
                        valid_coins.append(coin_data)
                    except Exception:
                        continue

                self.logger.info(f"✅ 현물 거래소 코인 분석 완료(정렬 적용): {len(valid_coins)}개 → 상위 {target_count}개 반환")
                self.logger.info(f"⏱️ 현물 분석 소요시간: {(time.perf_counter()-_t_total_start):.2f}s")
                return valid_coins
            else:
                self.logger.warning("현물 거래소 마켓 정보를 가져올 수 없음")
                return []

        except Exception as e:
            self.logger.error(f"❌ 현물 거래소 코인 분석 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []

    def _analyze_candidate_coins_ccxt_futures(self, exchange_client, adjustment_factor: float = 1.0):
        """CCXT 선물 거래소(바이비트/OKX/비트겟) 코인 분석
        - exchange.markets 기반 USDT 선물 마켓만 추출
        - 24h 티커의 quoteVolume 기준 정렬 후 상위 target_count 반환
        """
        try:
            self.logger.info(f"📊 CCXT 선물 코인 분석 시작 (조정계수: {adjustment_factor:.2f})")
            _t_total_start = time.perf_counter()

            # API 제한 확인(있으면 적용)
            try:
                if hasattr(self, 'ai_learning_manager') and self.ai_learning_manager and self.ai_learning_manager.should_apply_api_delay():
                    delay = self.ai_learning_manager.get_analysis_delay()
                    self.logger.info(f"API 제한으로 인한 딜레이 적용: {delay}초")
                    import time as _t
                    _t.sleep(delay)
            except Exception:
                pass

            try:
                max_coins = self.ai_learning_manager.get_max_coins_for_analysis() if self.ai_learning_manager else 100
            except Exception:
                max_coins = 100

            # 설정 기반 파라미터 로드(거래소별 오버라이드)
            ex_name = None
            try:
                ex_name = str(getattr(exchange_client, 'exchange_name', '')).lower()
                if not ex_name and hasattr(exchange_client, 'exchange') and hasattr(exchange_client.exchange, 'id'):
                    ex_name = str(exchange_client.exchange.id).lower()
            except Exception:
                ex_name = None
            fs_cfg = {}
            try:
                if hasattr(self, 'settings') and isinstance(self.settings, dict):
                    fs_cfg = (self.settings.get('futures_selection', {}) or {}).get(ex_name or '', {})
            except Exception:
                fs_cfg = {}
            fs_max = int(fs_cfg.get('max_candidates', max_coins)) if isinstance(fs_cfg, dict) else max_coins
            min_qv = float(fs_cfg.get('min_quote_volume', 0)) if isinstance(fs_cfg, dict) else 0.0
            vol_max = float(fs_cfg.get('volatility_max', 1e9)) if isinstance(fs_cfg, dict) else 1e9
            sort_w = (fs_cfg.get('sort_weights', {}) or {}) if isinstance(fs_cfg, dict) else {}
            w_vol = float(sort_w.get('volume', 1.0))
            w_vlt = float(sort_w.get('volatility', 0.0))

            ex = getattr(exchange_client, 'exchange', None)
            if not ex or not hasattr(ex, 'markets'):
                self.logger.warning("CCXT 어댑터 markets 정보 없음")
                return []
            markets = getattr(ex, 'markets', {}) or {}
            if not markets:
                try:
                    ex.load_markets()
                    markets = getattr(ex, 'markets', {}) or {}
                except Exception:
                    pass
            if not markets:
                self.logger.warning("마켓 정보를 가져올 수 없음")
                return []

            # USDT 선물/스왑만
            candidates = []
            for sym, m in markets.items():
                try:
                    if not m.get('active', False):
                        continue
                    if not (m.get('swap') or m.get('future') or m.get('contract')):
                        continue
                    if str(m.get('quote') or '').upper() != 'USDT':
                        continue
                    candidates.append((sym, m))
                except Exception:
                    continue

            if not candidates:
                self.logger.warning("USDT 선물 후보 없음")
                return []

            # 24h 티커 수집 → 컷오프 적용 → 가중 정렬
            scored = []
            for sym, m in candidates:
                try:
                    t = exchange_client.get_24h_ticker(sym) if hasattr(exchange_client, 'get_24h_ticker') else None
                    qv = float((t or {}).get('quoteVolume', 0) or 0)
                    pct = float((t or {}).get('percentage', 0) or 0)
                    # 컷오프 적용
                    if min_qv and qv < min_qv:
                        continue
                    if abs(pct) > vol_max:
                        continue
                    scored.append((qv, abs(pct), sym, m, t))
                except Exception:
                    continue

            if not scored:
                self.logger.warning("티커 수집/필터 후 후보 없음")
                return []

            target_count = int(max(1, int(min(fs_max, max_coins) * adjustment_factor)))
            max_qv = max((x[0] for x in scored), default=1.0)
            max_pct = max((x[1] for x in scored), default=1.0)
            def _score(row):
                qv_norm = (row[0] / max_qv) if max_qv > 0 else 0.0
                vol_norm = (row[1] / max_pct) if max_pct > 0 else 0.0
                return (w_vol * qv_norm) + (w_vlt * vol_norm)
            scored.sort(key=_score, reverse=True)
            top = scored[:target_count]

            valid_coins = []
            for qv, apct, sym, m, t in top:
                try:
                    base = m.get('base')
                    pct = float((t or {}).get('percentage', 0) or 0)
                    last = float((t or {}).get('last', 0) or 0)
                    high = float((t or {}).get('high', 0) or 0)
                    low = float((t or {}).get('low', 0) or 0)
                    valid_coins.append({
                        'symbol': sym,
                        'base_symbol': base,
                        'is_major': base in ['BTC', 'ETH', 'BNB', 'XRP', 'ADA', 'SOL'],
                        'quoteVolume': qv,
                        'priceChangePercent': pct,
                        'lastPrice': last,
                        'high': high,
                        'low': low,
                    })
                except Exception:
                    continue

            self.logger.info(f"✅ CCXT 선물 코인 분석 완료: {len(valid_coins)}개 → 상위 {target_count}개 반환")
            self.logger.info(f"⏱️ CCXT 선물 분석 소요시간: {(time.perf_counter()-_t_total_start):.2f}s")
            return valid_coins
        except Exception as e:
            self.logger.error(f"❌ CCXT 선물 코인 분석 오류: {e}")
            return []

    def _is_valid_symbol(self, symbol: str) -> bool:
        """🔥 설정 기반 심볼 유효성 검증 (symbol_filters 적용)"""
        try:
            if not symbol or not isinstance(symbol, str):
                return False

            # 1단계: USDT로 끝나는지 확인
            if not symbol.endswith('USDT'):
                return False

            # 2단계: USDC 관련 제외
            if 'USDC' in symbol:
                return False

            # 3단계: settings.json의 symbol_filters 적용
            try:
                if hasattr(self, 'settings') and self.settings:
                    symbol_filters = self.settings.get('symbol_filters', {})

                    # 제외된 심볼 목록 확인
                    excluded_symbols = symbol_filters.get('excluded_symbols', [])
                    if symbol in excluded_symbols:
                        return False

                    # 제외된 패턴 확인
                    excluded_patterns = symbol_filters.get('excluded_patterns', [])
                    for pattern in excluded_patterns:
                        if pattern in symbol:
                            return False

                else:
                    self.logger.warning(f"⚠️ {symbol}: settings 객체를 찾을 수 없어 기본 필터링만 적용")

            except Exception as e:
                self.logger.warning(f"심볼 필터 적용 중 오류: {e}, 기본 필터링만 사용")

            return True

        except Exception as e:
            self.logger.error(f"🚨 {symbol}: 심볼 유효성 검증 중 오류: {e}")
            return False

    def _calculate_trading_scores(self, valid_coins, strategy='scalping', adjustment_factor=1.0):
        """🔥 전략별 점수 계산 (모든 코인을 알트코인으로 처리)"""
        scored_coins = []

        # 모든 코인을 알트코인으로 처리 (메이저 코인 분리는 _select_final_coins에서 처리)
        self.logger.info(f"📊 점수 계산 시작: 총 {len(valid_coins)}개 코인")

        # 🔥 모든 코인: 스캘핑 전략 평가
        for coin in valid_coins:
            try:
                # 알트코인용 가중치 (스캘핑 중심)
                alt_weights = {
                    'volatility_weight': 0.35,        # 높은 변동성 선호
                    'volume_stability_weight': 0.25,   # 거래량 안정성
                    'trend_weight': 0.25,              # 트렌드
                    'frequency_weight': 0.15           # 거래 빈도
                }

                # 스캘핑 점수 계산
                scores = self._calculate_altcoin_scores(coin, alt_weights)

                # 🔥 K-line 데이터 제외하고 필요한 정보만 추출하여 새로운 딕셔너리 생성
                clean_coin_data = {
                    'symbol': coin.get('symbol', 'N/A'),
                    'is_major': coin.get('is_major', False),
                    'base_symbol': coin.get('base_symbol', 'N/A'),
                    'overall_score': scores['overall_score'],
                    'technical_score': scores['technical_score'],
                    'volatility_score': scores['volatility_score'],
                    'volume_score': scores['volume_score'],
                    'trend_score': scores['trend_score'],
                    'risk_score': scores['risk_score'],
                    'volume': coin.get('volume', 0),
                    'quoteVolume': coin.get('quoteVolume', 0),
                    'count': coin.get('count', 0),
                    'priceChange': coin.get('priceChange', 0),
                    'priceChangePercent': coin.get('priceChangePercent', 0)
                }

                # 🔥 메이저 코인도 알트코인과 동일하게 모든 점수 필드 포함
                # 이제 메이저 코인도 대시보드에서 모든 점수가 정상적으로 표시됨

                scored_coins.append(clean_coin_data)
                self.logger.debug(f"✅ {coin['symbol']}: 점수 {scores['overall_score']:.2f}")

            except Exception as e:
                self.logger.warning(f"⚠️ {coin['symbol']}: 점수 계산 실패: {e}")
                # 🔥 기본 점수로 깨끗한 딕셔너리 생성
                clean_coin_data = {
                    'symbol': coin.get('symbol', 'N/A'),
                    'is_major': coin.get('is_major', False),
                    'base_symbol': coin.get('base_symbol', 'N/A'),
                    'overall_score': 30.0,  # 기본 점수
                    'technical_score': 30.0,
                    'volatility_score': 30.0,
                    'volume_score': 30.0,
                    'trend_score': 30.0,
                    'risk_score': 30.0,
                    'volume': coin.get('volume', 0),
                    'quoteVolume': coin.get('quoteVolume', 0),
                    'count': coin.get('count', 0),
                    'priceChange': coin.get('priceChange', 0),
                    'priceChangePercent': coin.get('priceChangePercent', 0)
                }
                scored_coins.append(clean_coin_data)

        self.logger.info(f"🎯 점수 계산 완료: 총 {len(scored_coins)}개")

        return scored_coins

    def _get_funding_rate(self, symbol: str) -> Optional[float]:
        """Binance Futures 펀딩비 조회. 반환: 현재 펀딩비율 (예: 0.0001 = 0.01%)"""
        try:
            # binance_client 존재 시 우선 사용
            if hasattr(self, 'binance_client') and self.binance_client:
                bc = self.binance_client
                if hasattr(bc, 'get_funding_rate'):
                    data = bc.get_funding_rate(symbol)
                    if data:
                        return float(data.get('lastFundingRate') or data.get('fundingRate') or 0)
            # 직접 API 호출 (CCXT 등 없을 때)
            import urllib.request, json
            url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
            with urllib.request.urlopen(url, timeout=3) as resp:
                data = json.loads(resp.read())
                return float(data.get('lastFundingRate') or 0)
        except Exception as e:
            self.logger.debug(f"펀딩비 조회 실패 ({symbol}): {e}")
            return None

    def _get_open_interest(self, symbol: str) -> Optional[dict]:
        """Binance Futures 미결제약정 조회. 반환: {'open_interest': float, 'oi_change_pct': float}"""
        try:
            import urllib.request, json
            url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
            with urllib.request.urlopen(url, timeout=3) as resp:
                data = json.loads(resp.read())
                oi = float(data.get('openInterest') or 0)
            # 5분전 OI와 비교 (sumOpenInterest from statistics endpoint)
            try:
                hist_url = f"https://fapi.binance.com/futures/data/openInterestHist?symbol={symbol}&period=5m&limit=2"
                with urllib.request.urlopen(hist_url, timeout=3) as resp2:
                    hist = json.loads(resp2.read())
                    if len(hist) >= 2:
                        oi_prev = float(hist[-2].get('sumOpenInterest') or 0)
                        oi_curr = float(hist[-1].get('sumOpenInterest') or oi)
                        change_pct = (oi_curr - oi_prev) / max(oi_prev, 1) * 100
                    else:
                        change_pct = 0.0
            except Exception:
                change_pct = 0.0
            return {'open_interest': oi, 'oi_change_pct': change_pct}
        except Exception as e:
            self.logger.debug(f"OI 조회 실패 ({symbol}): {e}")
            return None

    def _validate_frequency_thresholds(self, thresholds):
        """✅ 설정 파일 스키마 검증"""
        if not isinstance(thresholds, (list, tuple)):
            return False, f"타입 오류: {type(thresholds)} (리스트/튜플 필요)"
        if len(thresholds) < 5:
            return False, f"길이 부족: {len(thresholds)}개 (5개 필요)"
        if not all(isinstance(x, (int, float)) for x in thresholds):
            return False, f"요소 타입 오류: 숫자가 아닌 요소 포함"
        if thresholds != sorted(thresholds):
            return False, f"정렬 오류: 오름차순이 아님"
        return True, "검증 통과"

    def _normalize_freq_thresholds(self, v, symbol='UNKNOWN'):
        """✅ 안전 가드: 어떤 형식이 와도 [t0,t1,t2,t3,t4]로 정규화"""
        try:
            # 1) 단일 숫자면 20/40/60/80% 구간으로 분할
            if isinstance(v, (int, float)):
                top = int(v)
                result = [max(1, int(top * r)) for r in (0.2, 0.4, 0.6, 0.8, 1.0)]
                self.logger.debug(f"[{symbol}] 단일 숫자 정규화: {v} → {result}")
                return result

            # 2) 리스트/튜플이면 정수화+정렬 후 길이 보정
            if isinstance(v, (list, tuple)):
                arr = sorted(int(x) for x in v if x is not None)
                # 길이 5로 패딩 (기하증가 형태)
                while len(arr) < 5:
                    if not arr:
                        arr = [100, 500, 1000, 2000, 5000]
                        break
                    last = arr[-1]
                    step = last - (arr[-2] if len(arr) > 1 else max(1, last // 2))
                    arr.append(last + max(1, step))
                # 5개 초과면 앞에서부터 5개만 사용(오름차순 전제)
                result = arr[:5]
                if len(v) != 5:
                    self.logger.warning(f"[{symbol}] frequency_thresholds 보정: {v} → {result}")
                return result

        except Exception as e:
            self.logger.warning(f"[{symbol}] 잘못된 frequency_thresholds 입력 → 디폴트 사용: {e}")

        # 3) 완전 비정상 입력 → 디폴트
        return [100, 500, 1000, 2000, 5000]

    def _calculate_altcoin_scores(self, coin, weights_param):
        """알트코인 점수 계산 (설정 파일 기반 동적 계산)"""
        try:
            # 🔥 디버깅: 메서드 시작
            self.logger.info(f"🔍 {coin.get('symbol', 'UNKNOWN')} 점수 계산 시작")

            # ✅ 스코프 문제 해결: 변수를 try/except 블록 밖에서 정의
            symbol = coin.get('symbol', 'UNKNOWN')

            # 기본값들 (안전한 기본값)
            volatility_thresholds = [1.0, 3.0, 5.0, 7.0, 10.0]
            frequency_thresholds = [100, 500, 1000, 2000, 5000]
            volume_thresholds = {
                'optimal_min': 1e6,      # 1백만
                'optimal_max': 1e8,      # 1억
                'acceptable_min': 5e5,   # 50만
                'acceptable_max': 1e9    # 10억
            }
            weights = {
                'volatility_weight': 0.35,
                'volume_stability_weight': 0.25,
                'trend_weight': 0.25,
                'frequency_weight': 0.15
            }
            base_scores = {
                'volatility_initial': 50,
                'volume_initial': 50,
                'trend_base': 60,
                'frequency_base': 70,
                'technical_base': 60,
                'risk_base': 70
            }

            # 🔥 설정 파일에서 임계값 가져오기 (디폴트는 현재 하드코딩된 값)
            try:
                strategy_config = getattr(self, 'settings', {}).get('trading_strategies', {}).get('scalping', {})
                criteria = strategy_config.get('criteria', {})

                # 🔥 디버깅: criteria 내용 확인 (첫 번째 코인에서만)
                if not hasattr(self, '_criteria_debugged'):
                    self.logger.info(f"[{symbol}] 🔍 DEBUG: criteria 타입={type(criteria)}, 키 목록={list(criteria.keys()) if isinstance(criteria, dict) else 'N/A'}")
                    if isinstance(criteria, dict) and 'frequency_thresholds' in criteria:
                        freq_val = criteria.get('frequency_thresholds')
                        self.logger.info(f"[{symbol}] 🔍 DEBUG: frequency_thresholds 타입={type(freq_val)}, 값={freq_val}")
                    self._criteria_debugged = True

                # 변동성 임계값 (디폴트: 현재 하드코딩된 값)
                volatility_thresholds = criteria.get('volatility_thresholds', [1.0, 3.0, 5.0, 7.0, 10.0])

                # 거래량 임계값 (디폴트: 현재 하드코딩된 값)
                volume_thresholds = criteria.get('volume_thresholds', {
                    'optimal_min': 1e6,      # 1백만
                    'optimal_max': 1e8,      # 1억
                    'acceptable_min': 5e5,   # 50만
                    'acceptable_max': 1e9    # 10억
                })

                # ✅ 거래 빈도 임계값 안전 가드 적용 (메이저/알트코인 분리)
                # 🔥 frequency_thresholds는 코인의 24시간 거래 횟수(count)를 평가하는 임계값입니다
                # 정수 값이어야 합니다 (예: [1000, 5000, 10000, 50000, 100000])
                # settings.json에서는 딕셔너리 형식: {"major": [...], "altcoin": [...]}
                raw_freq_config = criteria.get('frequency_thresholds')
                
                # 🔥 근본 원인 파악 및 수정
                if raw_freq_config is None:
                    # criteria에 frequency_thresholds 키가 없는 경우
                    raw_freq_config = {
                        'major': [5000, 20000, 50000, 200000, 500000],
                        'altcoin': [1000, 5000, 10000, 50000, 100000]
                    }
                    if not hasattr(self, '_freq_config_missing'):
                        self.logger.error(f"[{symbol}] ❌ frequency_thresholds가 criteria에 없음 - 딕셔너리 기본값 사용")
                        self.logger.error(f"[{symbol}] ❌ criteria 키 목록: {list(criteria.keys()) if isinstance(criteria, dict) else 'N/A'}")
                        self.logger.error(f"[{symbol}] ❌ strategy_config 키 목록: {list(strategy_config.keys()) if isinstance(strategy_config, dict) else 'N/A'}")
                        self._freq_config_missing = True
                elif isinstance(raw_freq_config, list):
                    # 🔥 리스트 형식이 들어온 경우 (잘못된 형식 또는 하위 호환성)
                    if len(raw_freq_config) == 4 and all(0 < x < 1 for x in raw_freq_config):
                        # 🔥 잘못된 값 (소수점 리스트) - 완전히 잘못된 값
                        # ⚠️ 한 번만 경고 출력 (반복 로그 방지)
                        warning_key = "frequency_thresholds_invalid_format"
                        if warning_key not in self._warning_cache:
                            self.logger.warning(f"⚠️ frequency_thresholds 잘못된 형식 감지: {raw_freq_config} (딕셔너리 형식 필요, 기본값으로 교체)")
                            self.logger.warning(f"⚠️ criteria 전체 내용: {criteria}")
                            self.logger.warning(f"⚠️ 올바른 형식: {{'major': [5000, 20000, 50000, 200000, 500000], 'altcoin': [1000, 5000, 10000, 50000, 100000]}}")
                            self._warning_cache.add(warning_key)
                        # 올바른 딕셔너리 기본값으로 교체
                        raw_freq_config = {
                            'major': [5000, 20000, 50000, 200000, 500000],
                            'altcoin': [1000, 5000, 10000, 50000, 100000]
                        }
                    elif len(raw_freq_config) == 5 and all(isinstance(x, (int, float)) and x >= 1 for x in raw_freq_config):
                        # 🔥 기존 리스트 형식 (하위 호환성) - 정수 리스트
                        raw_freq_config = {
                            'major': raw_freq_config,
                            'altcoin': raw_freq_config
                        }
                        if not hasattr(self, '_freq_config_list_warned'):
                            self.logger.warning(f"[{symbol}] ⚠️ frequency_thresholds가 리스트 형식 - 딕셔너리로 변환")
                            self._freq_config_list_warned = True
                    else:
                        # 🔥 알 수 없는 리스트 형식
                        self.logger.error(f"[{symbol}] ❌ frequency_thresholds 알 수 없는 리스트 형식: {raw_freq_config}")
                        raw_freq_config = {
                            'major': [5000, 20000, 50000, 200000, 500000],
                            'altcoin': [1000, 5000, 10000, 50000, 100000]
                        }
                elif not isinstance(raw_freq_config, dict):
                    # 🔥 딕셔너리도 리스트도 아닌 경우
                    self.logger.error(f"[{symbol}] ❌ frequency_thresholds 잘못된 타입: {type(raw_freq_config)}, 값: {raw_freq_config}")
                    raw_freq_config = {
                        'major': [5000, 20000, 50000, 200000, 500000],
                        'altcoin': [1000, 5000, 10000, 50000, 100000]
                    }

                # 메이저/알트코인 구분하여 적절한 임계값 선택
                if isinstance(raw_freq_config, dict):
                    # 새로운 형식: {"major": [...], "altcoin": [...]}
                    is_major = coin.get('is_major', False)
                    raw_freq = raw_freq_config.get('major' if is_major else 'altcoin', None)
                    # 🔥 키를 찾지 못한 경우 기본값 사용
                    if raw_freq is None:
                        raw_freq = [1000, 5000, 10000, 50000, 100000]
                        warning_key_missing = f"frequency_thresholds_missing_key_{is_major}"
                        if warning_key_missing not in self._warning_cache:
                            self.logger.warning(f"[{symbol}] frequency_thresholds 딕셔너리에서 키를 찾지 못함 (major={is_major}), 기본값 사용")
                            self._warning_cache.add(warning_key_missing)
                else:
                    # 기존 형식: [1000, 5000, 10000, 50000, 100000]
                    raw_freq = raw_freq_config

                # ✅ 스키마 검증 먼저 수행
                is_valid, validation_msg = self._validate_frequency_thresholds(raw_freq)
                if not is_valid:
                    warning_key = f"frequency_thresholds_validation_{validation_msg}"
                    if warning_key not in self._warning_cache:
                        self.logger.warning(f"[{symbol}] frequency_thresholds 검증 실패: {validation_msg}")
                        self._warning_cache.add(warning_key)

                frequency_thresholds = self._normalize_freq_thresholds(raw_freq, symbol)

                # 가중치와 기본 점수 가져오기 (없으면 디폴트 사용)
                weights = strategy_config.get('weights', weights)
                base_scores = strategy_config.get('base_scores', base_scores)

                self.logger.info(f"🔍 {symbol} 설정 로드 성공")

            except Exception as e:
                self.logger.warning(f"⚠️ {symbol} 설정 파일 로드 실패, 디폴트 값 사용: {e}")
                # 디폴트 값은 이미 위에서 정의됨 (스코프 문제 해결)

            # 🔥 디버깅: 코인 데이터 확인
            self.logger.info(f"🔍 {coin.get('symbol', 'UNKNOWN')} 코인 데이터:")
            self.logger.info(f"  - priceChangePercent: {coin.get('priceChangePercent', 'N/A')}")
            self.logger.info(f"  - volume: {coin.get('volume', 'N/A')}")
            self.logger.info(f"  - count: {coin.get('count', 'N/A')}")

            # 1. 변동성 점수 (높을수록 좋음 - 스캘핑)
            volatility_score = base_scores.get('volatility_initial', 50)
            if 'priceChangePercent' in coin:
                change = abs(float(coin.get('priceChangePercent', 0)))

                # 🔥 설정 파일의 임계값 사용
                if change > volatility_thresholds[4]:  # 최고 임계값
                    volatility_score = 100
                elif change > volatility_thresholds[3]:  # 높은 임계값
                    volatility_score = 90
                elif change > volatility_thresholds[2]:  # 중간 임계값
                    volatility_score = 80
                elif change > volatility_thresholds[1]:  # 낮은 임계값
                    volatility_score = 70
                elif change > volatility_thresholds[0]:  # 최저 임계값
                    volatility_score = 60
                else:
                    volatility_score = 40

                self.logger.info(f"🔍 {coin.get('symbol', 'UNKNOWN')} 변동성 점수: {change:.2f}% → {volatility_score} (임계값: {volatility_thresholds})")

            # 2. 거래량 안정성 점수 (적당할수록 좋음)
            volume_stability_score = base_scores.get('volume_initial', 50)
            if 'quoteVolume' in coin:
                volume = float(coin.get('quoteVolume', 0))

                # 🔥 설정 파일의 임계값 사용
                if volume_thresholds['optimal_min'] <= volume <= volume_thresholds['optimal_max']:
                    volume_stability_score = 100  # 최적 범위
                elif volume_thresholds['acceptable_min'] <= volume < volume_thresholds['optimal_min']:
                    volume_stability_score = 80   # 허용 범위 (낮음)
                elif volume_thresholds['optimal_max'] <= volume <= volume_thresholds['acceptable_max']:
                    volume_stability_score = 70   # 허용 범위 (높음)
                else:
                    volume_stability_score = 50   # 기본값

                self.logger.info(f"🔍 {coin.get('symbol', 'UNKNOWN')} 거래량 점수: {volume:,.0f} → {volume_stability_score} (최적: {volume_thresholds['optimal_min']:,.0f}-{volume_thresholds['optimal_max']:,.0f})")

            # 3. 트렌드 점수 (실제 가격 변화 방향 기반)
            trend_score = base_scores.get('trend_base', 60)
            if 'priceChange' in coin and 'priceChangePercent' in coin:
                price_change = float(coin.get('priceChange', 0))
                price_change_percent = float(coin.get('priceChangePercent', 0))

                # 상승 트렌드 (양수 변화)
                if price_change > 0:
                    if price_change_percent > 5.0:  # 강한 상승
                        trend_score = 100
                    elif price_change_percent > 2.0:  # 중간 상승
                        trend_score = 85
                    elif price_change_percent > 0.5:  # 약한 상승
                        trend_score = 70
                    else:  # 미미한 상승
                        trend_score = 60
                # 하락 트렌드 (음수 변화)
                elif price_change < 0:
                    if price_change_percent < -5.0:  # 강한 하락
                        trend_score = 20
                    elif price_change_percent < -2.0:  # 중간 하락
                        trend_score = 35
                    elif price_change_percent < -0.5:  # 약한 하락
                        trend_score = 50
                    else:  # 미미한 하락
                        trend_score = 55
                else:  # 변화 없음
                    trend_score = 50

                self.logger.debug(f"트렌드 점수: {price_change_percent:.2f}% → {trend_score}")

            # 4. 거래 빈도 점수 (실제 거래 횟수 기반) - ✅ 루프 비교 방식으로 개선
            frequency_score = base_scores.get('frequency_base', 70)
            if 'count' in coin:
                count = int(coin.get('count', 0))

                # ✅ 경계 포함 비교 방식 (>= 사용으로 정확한 임계값 처리)
                bands = [
                    (4, 100),  # >= t4 (매우 높은 빈도)
                    (3,  90),  # >= t3 (높은 빈도)
                    (2,  80),  # >= t2 (중간 빈도)
                    (1,  70),  # >= t1 (낮은 빈도)
                    (0,  60),  # >= t0 (매우 낮은 빈도)
                ]
                frequency_score = 40  # 기본값 (거의 거래 없음)

                for idx, score in bands:
                    if count >= frequency_thresholds[idx]:
                        frequency_score = score
                        break

                self.logger.debug(f"거래 빈도 점수: {count}회 → {frequency_score} (임계값: {frequency_thresholds})")

            # 5. 기술적 점수 (실제 기술적 지표 기반)
            technical_score = base_scores.get('technical_base', 60)
            try:
                # 기술적 지표 계산 시도
                symbol = coin.get('symbol', '')
                if symbol:
                    technical_indicators = self.calculate_technical_indicators(symbol)
                    if technical_indicators:
                        # RSI 기반 점수 계산
                        rsi_15m = technical_indicators.get('rsi_15m', 50)
                        rsi_1h = technical_indicators.get('rsi_1h', 50)

                        # RSI 종합 점수 (15분과 1시간 평균)
                        avg_rsi = (rsi_15m + rsi_1h) / 2

                        if 30 <= avg_rsi <= 70:  # 정상 범위
                            technical_score = 80
                        elif 20 <= avg_rsi < 30 or 70 < avg_rsi <= 80:  # 과매도/과매수 경계
                            technical_score = 70
                        elif avg_rsi < 20 or avg_rsi > 80:  # 극단적 과매도/과매수
                            technical_score = 50
                        else:  # 기타
                            technical_score = 60

                        self.logger.debug(f"기술적 점수: RSI {avg_rsi:.1f} → {technical_score}")
            except Exception as e:
                self.logger.debug(f"기술적 지표 계산 실패, 기본값 사용: {e}")

            # 6. 리스크 점수 (변동성과 거래량 종합)
            risk_score = base_scores.get('risk_base', 70)
            try:
                # 변동성과 거래량을 종합하여 리스크 평가
                volatility_risk = 100 - volatility_score  # 변동성이 높으면 리스크 높음
                volume_risk = 100 - volume_stability_score  # 거래량이 불안정하면 리스크 높음

                # 리스크 점수 계산 (낮을수록 좋음)
                risk_score = max(20, min(100, (volatility_risk + volume_risk) / 2))

                self.logger.debug(f"리스크 점수: 변동성 {volatility_risk:.1f} + 거래량 {volume_risk:.1f} → {risk_score:.1f}")
            except Exception as e:
                self.logger.debug(f"리스크 점수 계산 실패, 기본값 사용: {e}")

            # 7. 펀딩비 점수 (Binance Futures 전용, 5%)
            funding_score = 50.0
            try:
                funding_rate = self._get_funding_rate(symbol)
                if funding_rate is not None:
                    rate_pct = funding_rate * 100  # 예: 0.0001 → 0.01%
                    if 0.0 <= rate_pct <= 0.01:
                        funding_score = 80.0   # 적정 범위 (매수/매도 균형)
                    elif rate_pct > 0.05:
                        funding_score = 30.0   # 롱 포지션 과도 → 조정 위험
                    elif rate_pct < -0.01:
                        funding_score = 35.0   # 숏 포지션 많음 → 반등 가능성
                    else:
                        funding_score = 60.0
                    self.logger.debug(f"펀딩비 점수: {rate_pct:.4f}% → {funding_score}")
            except Exception as e:
                self.logger.debug(f"펀딩비 점수 계산 실패: {e}")

            # 8. 미결제약정(OI) 점수 (Binance Futures 전용, 5%)
            oi_score = 50.0
            try:
                oi_data = self._get_open_interest(symbol)
                if oi_data:
                    oi_change_pct = oi_data.get('oi_change_pct', 0.0)
                    oi_value = oi_data.get('open_interest', 0.0)
                    # OI 급증 → 추세 강화 신호
                    if oi_change_pct > 5.0:
                        oi_score = 80.0
                    elif oi_change_pct > 2.0:
                        oi_score = 70.0
                    elif oi_change_pct < -5.0:
                        oi_score = 30.0  # OI 급감 → 청산 신호
                    else:
                        oi_score = 55.0
                    self.logger.debug(f"OI 점수: {oi_change_pct:.2f}% → {oi_score}")
            except Exception as e:
                self.logger.debug(f"OI 점수 계산 실패: {e}")

            # 🔥 설정 파일의 가중치 사용 (펀딩비+OI 반영으로 기존 가중치 조정)
            overall_score = (
                volatility_score * weights.get('volatility_weight', 0.30) +
                volume_stability_score * weights.get('volume_stability_weight', 0.22) +
                trend_score * weights.get('trend_weight', 0.22) +
                frequency_score * weights.get('frequency_weight', 0.13) +
                funding_score * 0.08 +
                oi_score * 0.05
            )

            self.logger.info(f"🔍 {coin.get('symbol', 'UNKNOWN')} 종합 점수 계산:")
            self.logger.info(f"  - 변동성: {volatility_score} × {weights.get('volatility_weight', 0.30)} = {volatility_score * weights.get('volatility_weight', 0.30):.2f}")
            self.logger.info(f"  - 거래량: {volume_stability_score} × {weights.get('volume_stability_weight', 0.22)} = {volume_stability_score * weights.get('volume_stability_weight', 0.22):.2f}")
            self.logger.info(f"  - 트렌드: {trend_score} × {weights.get('trend_weight', 0.22)} = {trend_score * weights.get('trend_weight', 0.22):.2f}")
            self.logger.info(f"  - 빈도: {frequency_score} × {weights.get('frequency_weight', 0.13)} = {frequency_score * weights.get('frequency_weight', 0.13):.2f}")
            self.logger.info(f"  - 펀딩비: {funding_score:.1f} × 0.08 = {funding_score * 0.08:.2f}")
            self.logger.info(f"  - OI: {oi_score:.1f} × 0.05 = {oi_score * 0.05:.2f}")
            self.logger.info(f"  - 최종 점수: {overall_score:.2f}")

            return {
                'overall_score': overall_score,
                'technical_score': technical_score,
                'volatility_score': volatility_score,
                'volume_score': volume_stability_score,
                'trend_score': trend_score,
                'risk_score': risk_score
            }

        except Exception as e:
            symbol = coin.get('symbol', 'UNKNOWN')
            self.logger.error(f"❌ {symbol} 알트코인 점수 계산 오류: {e}")
            import traceback
            self.logger.error(f"❌ {symbol} 상세 오류: {traceback.format_exc()}")
            return {
                'overall_score': 30.0,
                'technical_score': 30.0,
                'volatility_score': 30.0,
                'volume_score': 30.0,
                'trend_score': 30.0,
                'risk_score': 30.0
            }

    def _select_final_coins(self, selected_symbols, num_alt, num_major, market_regime: Optional[str] = None):
        """최종 코인 선택 (시장 상황에 따라 동적 조절, 메이저 코인 2개 이상 보장)"""
        try:
            self.logger.info(f"🎯 최종 코인 선택 시작 - 알트코인 {num_alt}개, 메이저 {num_major}개")

            # 🔥 먼저 점수 계산 수행 (메이저/알트코인 분리 및 점수 계산)
            self.logger.info("📊 점수 계산 시작...")
            scored_coins = self._calculate_trading_scores(selected_symbols, 'scalping', 1.0)
            self.logger.info(f"✅ 점수 계산 완료: {len(scored_coins)}개 코인")

            # 거래소별 심볼 포맷(USDT/KRW/BASE-QUOTE/BASE/QUOTE)과 무관하게 메이저 분류
            major_bases = {'BTC', 'ETH', 'BNB', 'SOL', 'ADA', 'XRP', 'DOT', 'LINK', 'AVAX', 'MATIC'}
            alt_coins = []
            major_coins = []

            for coin_data in scored_coins:
                symbol = str(coin_data.get('symbol', '') or '').upper().strip()
                base_symbol = str(coin_data.get('base_symbol', '') or '').upper().strip()
                base = base_symbol
                if not base:
                    if '-' in symbol:
                        parts = symbol.split('-')
                        if len(parts) == 2:
                            base = parts[1] if parts[0] in {'KRW', 'USDT', 'USD'} else parts[0]
                    elif '/' in symbol:
                        parts = symbol.split('/')
                        if len(parts) == 2:
                            base = parts[0] if parts[1] in {'KRW', 'USDT', 'USD'} else parts[0]
                    else:
                        for quote in ('USDT', 'USDC', 'KRW', 'BTC', 'ETH'):
                            if symbol.endswith(quote) and len(symbol) > len(quote):
                                base = symbol[:-len(quote)]
                                break

                if base in major_bases:
                    coin_data['is_major'] = True  # 메이저 코인 표시
                    major_coins.append(coin_data)
                else:
                    coin_data['is_major'] = False  # 알트코인 표시
                    alt_coins.append(coin_data)

            self.logger.info(f"분류 결과 - 알트코인: {len(alt_coins)}개, 메이저: {len(major_coins)}개")

            # 🔥 시장 상황에 따른 동적 코인 수 조절 (설정 파일 기반, 범위 제한)
            try:
                # 설정에서 최소/최대 코인 수 가져오기
                min_total_coins = getattr(self, 'settings', {}).get('min_total_coins', 15)
                max_total_coins = getattr(self, 'settings', {}).get('max_total_coins', 20)
            except:
                # 설정 파일 로드 실패 시 기본값 사용
                min_total_coins = 15
                max_total_coins = 20

            # 🔥 설정값 범위 내에서만 동적 조절
            base_total = num_alt + num_major  # 기본 설정값

            if market_regime == 'bear':
                target_total = max(min_total_coins, base_total - 2)  # 최소값 보장
                self.logger.info(f"📉 시장 상황 나쁨 → {target_total}개 코인 선택 (기본: {base_total}개, 범위: {min_total_coins}-{max_total_coins})")
            elif market_regime == 'normal':
                target_total = base_total  # 기본값 유지
                self.logger.info(f"📊 시장 상황 보통 → {target_total}개 코인 선택 (기본: {base_total}개, 범위: {min_total_coins}-{max_total_coins})")
            elif market_regime == 'bull':
                target_total = min(max_total_coins, base_total + 2)  # 최대값 제한
                self.logger.info(f"📈 시장 상황 좋음 → {target_total}개 코인 선택 (기본: {base_total}개, 범위: {min_total_coins}-{max_total_coins})")
            elif market_regime == 'volatile':
                target_total = base_total  # 변동성 높음은 기본값 유지
                self.logger.info(f"⚡ 시장 상황 변동성 높음 → {target_total}개 코인 선택 (기본: {base_total}개, 범위: {min_total_coins}-{max_total_coins})")
            else:
                target_total = base_total  # 기본값
                self.logger.info(f"🔍 시장 상황 미정 → {target_total}개 코인 선택 (기본: {base_total}개, 범위: {min_total_coins}-{max_total_coins})")

            # 🔥 설정값 범위 엄격 준수
            target_total = max(min_total_coins, min(target_total, max_total_coins))
            self.logger.info(f"🎯 최종 목표: {target_total}개 (범위 제한 적용)")

            # 🔥 시장 상황에 따른 메이저/알트 비율 동적 조정 (설정 파일 기반)
            try:
                # 설정 파일에서 시장 상황별 비율 가져오기
                coin_ratios = getattr(self, 'settings', {}).get('coin_selection_ratios', {})
                regime_ratios = coin_ratios.get(market_regime, {'altcoin_ratio': 0.7, 'major_ratio': 0.3})
                target_major_ratio = regime_ratios['major_ratio']
                target_alt_ratio = regime_ratios['altcoin_ratio']
                self.logger.info(f"📊 설정 파일 기반 비율: 메이저 {target_major_ratio*100:.0f}% + 알트코인 {target_alt_ratio*100:.0f}%")
            except Exception as e:
                self.logger.warning(f"⚠️ 설정 파일 로드 실패, 기본 비율 사용: {e}")
                # 기본 비율 (설정 파일 없을 때)
                if market_regime == 'bear':
                    target_major_ratio = 0.6
                    target_alt_ratio = 0.4
                    self.logger.info(f"📉 하락장 → 메이저 {target_major_ratio*100:.0f}% + 알트코인 {target_alt_ratio*100:.0f}% (보수적)")
                elif market_regime == 'bull':
                    target_major_ratio = 0.2
                    target_alt_ratio = 0.8
                    self.logger.info(f"📈 상승장 → 메이저 {target_major_ratio*100:.0f}% + 알트코인 {target_alt_ratio*100:.0f}% (공격적)")
                elif market_regime == 'volatile':
                    target_major_ratio = 0.4
                    target_alt_ratio = 0.6
                    self.logger.info(f"⚡ 변동성 높음 → 메이저 {target_major_ratio*100:.0f}% + 알트코인 {target_alt_ratio*100:.0f}% (균형)")
                else:  # normal
                    target_major_ratio = 0.3
                    target_alt_ratio = 0.7
                    self.logger.info(f"📊 정상장 → 메이저 {target_major_ratio*100:.0f}% + 알트코인 {target_alt_ratio*100:.0f}% (기본)")

            # 목표 메이저/알트 코인 수 계산
            target_major_count = int(target_total * target_major_ratio)
            target_alt_count = target_total - target_major_count

            self.logger.info(f"🎯 목표 비율: 메이저 {target_major_count}개, 알트코인 {target_alt_count}개")

            # 🔥 목표 비율에 맞춰 조정
            current_major = len(major_coins)
            current_alt = len(alt_coins)

            if current_major != target_major_count or current_alt != target_alt_count:
                self.logger.info(f"비율 조정: 메이저 {current_major}→{target_major_count}개, 알트코인 {current_alt}→{target_alt_count}개")

                # 메이저 코인 조정
                if current_major > target_major_count:
                    # 메이저 코인 제거 (점수 낮은 순)
                    major_coins = sorted(major_coins, key=lambda x: x.get('overall_score', 0), reverse=True)[:target_major_count]
                    self.logger.info(f"메이저 코인 제거: {current_major}개 → {len(major_coins)}개")
                elif current_major < target_major_count:
                    # 메이저 코인 부족 - 점수가 높은 알트코인을 메이저로 승격
                    shortage = target_major_count - current_major
                    alt_coins_sorted = sorted(alt_coins, key=lambda x: x.get('overall_score', 0), reverse=True)

                    for i in range(min(shortage, len(alt_coins_sorted))):
                        promoted_coin = alt_coins_sorted[i]
                        promoted_coin['is_major'] = True
                        major_coins.append(promoted_coin)
                        alt_coins.remove(promoted_coin)

                    self.logger.info(f"알트코인 메이저 승격: {shortage}개")

                # 알트코인 조정
                if len(alt_coins) > target_alt_count:
                    # 알트코인 제거 (점수 낮은 순)
                    alt_coins = sorted(alt_coins, key=lambda x: x.get('overall_score', 0), reverse=True)[:target_alt_count]
                    self.logger.info(f"알트코인 제거: {current_alt}개 → {len(alt_coins)}개")

            # 🔥 최종 선택: 점수 순으로 정렬하여 상위 코인 선택
            self.logger.info("🎯 최종 코인 선택 (점수 순 정렬)")

            # 🔥 시장 상황에 따른 비율 조정이 완료되었으므로 추가 로직 불필요
            # 메뉴얼에 따라 시장 상황별로 적절한 비율로 조정됨

            # 최종 선택된 코인들
            selected_major = major_coins
            selected_alt = alt_coins
            self.logger.info(f"✅ 최종 선택: 메이저 {len(selected_major)}개, 알트코인 {len(selected_alt)}개")

            # 최종 결과 병합
            final_selection = selected_major + selected_alt

            # 🔥 교과서적인 로그 형식으로 각 코인별 상세 정보 출력 (K-line 데이터 제외)
            self.logger.info(f"🎯 최종 선택 완료: 총 {len(final_selection)}개 (메이저: {len(selected_major)}개, 알트: {len(selected_alt)}개)")

            for coin in final_selection:
                symbol = coin['symbol']
                overall_score = coin.get('overall_score', 0)
                technical_score = coin.get('technical_score', 0)
                volatility_score = coin.get('volatility_score', 0)
                volume_score = coin.get('volume_score', 0)
                trend_score = coin.get('trend_score', 0)
                risk_score = coin.get('risk_score', 0)
                volume = coin.get('volume', 0)
                price_change = coin.get('priceChangePercent', 0)
                is_major = coin.get('is_major', False)

                # 🔥 매우 간단한 로그 형식 (핵심 정보만)
                self.log_event('system', f"{symbol} ({'메이저' if is_major else '알트'}) | 점수: {overall_score:.2f}", exchange='binance')

            # 🔥 점수가 포함된 딕셔너리 리스트 반환 (대시보드에서 점수 표시용)
            # 🔥 K-line 데이터는 포함하되 로그에는 출력하지 않음

            # 🔥 디버깅: 반환 직전 확인
            self.logger.debug(f"_select_final_coins returning {len(final_selection)} coins")

            return final_selection

        except Exception as e:
            self.logger.error(f"❌ _select_final_coins 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []

    def _fallback_to_major_coins(self, limit, exchange: Optional[str] = None):
        """메이저 코인으로 폴백 (거래소 포맷 반영)."""
        fallback_coins = ['BTC', 'ETH', 'BNB', 'SOL', 'ADA', 'XRP', 'DOT', 'LINK', 'AVAX', 'MATIC']
        ex = str(exchange or '').strip().lower()
        if ex == 'upbit':
            return [f"KRW-{coin}" for coin in fallback_coins[:limit]]
        if ex == 'bithumb':
            return [f"{coin}/KRW" for coin in fallback_coins[:limit]]
        return [f"{coin}USDT" for coin in fallback_coins[:limit]]

    def _initialize_websocket_connection(self):
        """🔥 WebSocket 연결 초기화 (사용하지 않음 - API 기반 분석으로 대체)"""
        # WebSocket 초기화 제거 - 코인 분석은 API로 수행
        # 실제 포지션 진입 시에만 WebSocket 구독 사용
        self.logger.info("WebSocket 초기화 건너뜀 - API 기반 분석 사용")
        return

    # 🔥 _manage_trading_websocket_subscriptions 함수 제거됨
    # 웹소켓 구독은 main.py에서 관리하므로 이 메서드는 불필요함

    def calculate_technical_indicators_from_klines(self, klines_15m, klines_1h):
        """기술적 지표 계산 (일괄 조회된 K라인 데이터 사용)"""
        try:
            if not klines_15m or not klines_1h:
                return None

            # 15분 데이터 처리
            closes_15m = [float(k[4]) for k in klines_15m]
            volumes_15m = [float(k[5]) for k in klines_15m]

            # 1시간 데이터 처리
            closes_1h = [float(k[4]) for k in klines_1h]
            volumes_1h = [float(k[5]) for k in klines_1h]

            # 변화율 계산
            change_15m = ((closes_15m[-1] - closes_15m[-2]) / closes_15m[-2]) * 100
            change_1h = ((closes_1h[-1] - closes_1h[-2]) / closes_1h[-2]) * 100

            # 거래량 스파이크 계산
            avg_volume_15m = sum(volumes_15m[:-1]) / len(volumes_15m[:-1])
            current_volume_15m = volumes_15m[-1]
            volume_spike = current_volume_15m / avg_volume_15m if avg_volume_15m > 0 else 1.0

            # RSI 계산
            rsi_15m = self._calculate_rsi(closes_15m, 14)
            rsi_1h = self._calculate_rsi(closes_1h, 14)

            # 트렌드 강도 계산
            trend_strength = self._calculate_trend_strength(closes_15m)

            # 거래 빈도 계산 (간단한 추정)
            trade_frequency = len(klines_15m) / 100  # 100개 캔들 기준

            # 호가창 깊이 계산 (간단한 추정)
            orderbook_depth = sum(volumes_15m[-5:]) / 5  # 최근 5개 캔들 평균

            return {
                'change_15m': change_15m,
                'change_1h': change_1h,
                'volume_spike': volume_spike,
                'rsi_15m': rsi_15m,
                'rsi_1h': rsi_1h,
                'trend_strength': trend_strength,
                'trade_frequency': trade_frequency,
                'orderbook_depth': orderbook_depth
            }

        except Exception as e:
            self.logger.error(f"기술적 지표 계산 오류: {e}")
            return None

    def calculate_technical_indicators(self, symbol):
        """기술적 지표 계산 (실제 구현)"""
        try:
            # 바이낸스에서 K라인 데이터 가져오기
            klines_15m = self.binance_client.get_klines(symbol, "15m", 100)
            klines_1h = self.binance_client.get_klines(symbol, "1h", 100)

            if not klines_15m or not klines_1h:
                return None

            # 15분 데이터 처리
            closes_15m = [float(k[4]) for k in klines_15m]
            volumes_15m = [float(k[5]) for k in klines_15m]

            # 1시간 데이터 처리
            closes_1h = [float(k[4]) for k in klines_1h]
            volumes_1h = [float(k[5]) for k in klines_1h]

            # 변화율 계산
            change_15m = ((closes_15m[-1] - closes_15m[-2]) / closes_15m[-2]) * 100
            change_1h = ((closes_1h[-1] - closes_1h[-2]) / closes_1h[-2]) * 100

            # 거래량 스파이크 계산
            avg_volume_15m = sum(volumes_15m[:-1]) / len(volumes_15m[:-1])
            current_volume_15m = volumes_15m[-1]
            volume_spike = current_volume_15m / avg_volume_15m if avg_volume_15m > 0 else 1.0

            # RSI 계산
            rsi_15m = self._calculate_rsi(closes_15m, 14)
            rsi_1h = self._calculate_rsi(closes_1h, 14)

            # 트렌드 강도 계산
            trend_strength = self._calculate_trend_strength(closes_15m)

            # 거래 빈도 (간단한 추정)
            trade_frequency = len(klines_15m) / 100  # 100개 캔들 기준

            # 호가창 깊이 (간단한 추정)
            orderbook_depth = avg_volume_15m * 10  # 거래량의 10배로 추정

            return {
                'change_15m': change_15m,
                'change_1h': change_1h,
                'volume_spike': volume_spike,
                'rsi_15m': rsi_15m,
                'rsi_1h': rsi_1h,
                'trend_strength': trend_strength,
                'trade_frequency': trade_frequency,
                'orderbook_depth': orderbook_depth
            }

        except Exception as e:
            self.logger.error(f"{symbol} 기술적 지표 계산 오류: {e}")
            return None

    def _calculate_rsi(self, prices, period=14):
        """RSI 계산"""
        try:
            if len(prices) < period + 1:
                return 50.0

            deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
            gains = [d if d > 0 else 0 for d in deltas]
            losses = [-d if d < 0 else 0 for d in deltas]

            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period

            if avg_loss == 0:
                return 100.0

            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            return rsi

        except Exception:
            return 50.0

    def _calculate_trend_strength(self, prices):
        """트렌드 강도 계산"""
        try:
            if len(prices) < 20:
                return 0.0

            # 20일 이동평균
            sma_20 = sum(prices[-20:]) / 20
            current_price = prices[-1]

            # 현재가와 이동평균의 차이를 백분율로 계산
            trend_strength = abs((current_price - sma_20) / sma_20) * 100
            return trend_strength

        except Exception:
            return 0.0

    # 🔥 중복된 evaluate_candidates, evaluate_single_coin, calculate_overall_score 함수 제거됨
    # 이 함수들은 실제로 사용되지 않으며, 코인 선택 로직은 select_trading_coins에서 처리됨

    # 🔥 중복된 세부 점수 계산 함수들 제거됨
    # calculate_technical_score, calculate_volatility_score, calculate_volume_score,
    # calculate_trend_score, calculate_risk_score, generate_selection_reasoning, generate_recommendation
    # 이 함수들은 실제로 사용되지 않으며, 코인 선택 로직은 select_trading_coins에서 처리됨

    # 🔥 save_evaluation_results 함수 제거됨 - 실제로 사용되지 않음

    def get_performance_stats(self) -> Dict:
        """성능 통계 조회"""
        return {
            'cache_hits': self.coin_selection_performance['cache_hits'],
            'cache_misses': self.coin_selection_performance['cache_misses'],
            'total_selections': self.coin_selection_performance['total_selections'],
            'avg_selection_time': self.coin_selection_performance['avg_selection_time'],
            'cache_hit_rate': (
                self.coin_selection_performance['cache_hits'] /
                max(1, self.coin_selection_performance['total_selections'])
            ) * 100
        }

    def _evaluate_coins_with_ai(self, valid_coins, selected_coins):
        """AI 평가 단계 - 상세 스코어 계산 및 DB 저장"""
        try:
            self.logger.info("🤖 AI 평가 단계 시작...")

            # 데이터 일관성 검증 추가
            initial_data = {}
            for coin_data in valid_coins:
                # 🔥 얕은 가드 사용 - 중복 부착 방지만
                symbol = coin_data['symbol']
                symbol_with_usdt = self._append_usdt_if_missing(symbol)
                initial_data[symbol_with_usdt] = coin_data

            self._verify_data_consistency(selected_coins, initial_data)

            # 🔥 일괄 K라인 데이터 조회 (API 최적화 + 캐시)
            selected_symbols_with_usdt = []
            for coin in valid_coins:
                if coin['symbol'] in selected_coins:
                    symbol = coin['symbol']
                    symbol_with_usdt = self._append_usdt_if_missing(symbol)
                    selected_symbols_with_usdt.append(symbol_with_usdt)

            self.logger.info(f"🚀 일괄 K라인 데이터 조회 시작: {len(selected_symbols_with_usdt)}개 코인")

            # 🔥 캐시된 K라인 데이터 확인 (10분 이내)
            klines_cache_file_15m = "data/nwsoft/cache/klines_15m.json"
            klines_cache_file_1h = "data/nwsoft/cache/klines_1h.json"

            all_klines_15m = {}
            all_klines_1h = {}

            # 15분 데이터 캐시 확인
            if os.path.exists(klines_cache_file_15m):
                cache_age = time.time() - os.path.getmtime(klines_cache_file_15m)
                if cache_age < 600:  # 10분
                    self.logger.info("캐시된 15분 K라인 데이터 사용")
                    with open(klines_cache_file_15m, 'r', encoding='utf-8') as f:
                        all_klines_15m = json.load(f)
                else:
                    self.logger.info("15분 K라인 캐시 만료 - 새로 조회")
                    all_klines_15m = self.binance_client.get_multiple_klines(selected_symbols_with_usdt, "15m", 100)
            else:
                self.logger.info("15분 K라인 캐시 없음 - 새로 조회")
                all_klines_15m = self.binance_client.get_multiple_klines(selected_symbols_with_usdt, "15m", 100)

            # 1시간 데이터 캐시 확인
            if os.path.exists(klines_cache_file_1h):
                cache_age = time.time() - os.path.getmtime(klines_cache_file_1h)
                if cache_age < 600:  # 10분
                    self.logger.info("캐시된 1시간 K라인 데이터 사용")
                    with open(klines_cache_file_1h, 'r', encoding='utf-8') as f:
                        all_klines_1h = json.load(f)
                else:
                    self.logger.info("1시간 K라인 캐시 만료 - 새로 조회")
                    all_klines_1h = self.binance_client.get_multiple_klines(selected_symbols_with_usdt, "1h", 100)
            else:
                self.logger.info("1시간 K라인 캐시 없음 - 새로 조회")
                all_klines_1h = self.binance_client.get_multiple_klines(selected_symbols_with_usdt, "1h", 100)

            # 🔥 캐시 저장
            if all_klines_15m:
                os.makedirs(os.path.dirname(klines_cache_file_15m), exist_ok=True)
                with open(klines_cache_file_15m, 'w', encoding='utf-8') as f:
                    json.dump(all_klines_15m, f, ensure_ascii=False, indent=2)
                self.logger.info("15분 K라인 데이터 캐시 저장 완료")

            if all_klines_1h:
                os.makedirs(os.path.dirname(klines_cache_file_1h), exist_ok=True)
                with open(klines_cache_file_1h, 'w', encoding='utf-8') as f:
                    json.dump(all_klines_1h, f, ensure_ascii=False, indent=2)
                self.logger.info("1시간 K라인 데이터 캐시 저장 완료")

            self.logger.info(f"✅ 일괄 K라인 조회 완료: 15분({len(all_klines_15m)}개), 1시간({len(all_klines_1h)}개)")

            coin_scores = []
            for coin_data in valid_coins:
                if coin_data['symbol'] not in selected_coins:
                    continue

                # 🔥 일괄 조회된 데이터 사용
                symbol_with_usdt = self._append_usdt_if_missing(coin_data['symbol'])

                # 일괄 조회된 K라인 데이터 확인
                if symbol_with_usdt not in all_klines_15m or symbol_with_usdt not in all_klines_1h:
                    self.logger.warning(f"⚠️ {coin_data['symbol']}: 일괄 조회 데이터 없음")
                    continue

                # 기술적 지표 계산 (일괄 조회된 데이터 사용)
                technical_indicators = self.calculate_technical_indicators_from_klines(
                    all_klines_15m[symbol_with_usdt],
                    all_klines_1h[symbol_with_usdt]
                )

                if not technical_indicators:
                    self.logger.warning(f"⚠️ {coin_data['symbol']}: 기술적 지표 계산 실패")
                    continue

                # 1. 변동성 점수 (스캘핑 최적화) - 실제 계산값 사용
                volatility_15m = abs(technical_indicators.get('change_15m', 0))
                volatility_1h = abs(technical_indicators.get('change_1h', 0))
                avg_volatility = (volatility_15m + volatility_1h) / 2

                if avg_volatility < 0.5:
                    volatility_score = 30  # 스캘핑에 부적합
                elif 0.5 <= avg_volatility <= 2.0:  # 스캘핑에 최적
                    volatility_score = 100
                elif 2.0 < avg_volatility <= 5.0:  # 스캘핑 가능
                    volatility_score = 80
                else:
                    volatility_score = max(20, 100 - (avg_volatility - 5.0) * 15)

                # 2. 거래량 점수 - 실제 계산값 사용
                volume_score = min(100, technical_indicators.get('volume_spike', 1.0) * 8)

                # 3. RSI 점수 (15분 + 1시간 평균) - 실제 계산값 사용
                rsi_15m = technical_indicators.get('rsi_15m', 50)
                rsi_1h = technical_indicators.get('rsi_1h', 50)
                avg_rsi = (rsi_15m + rsi_1h) / 2

                if 40 <= avg_rsi <= 60:
                    rsi_score = 70  # 중립 구간
                elif (25 <= avg_rsi < 40) or (60 < avg_rsi <= 75):
                    rsi_score = 85  # 약한 과매도/과매수
                elif avg_rsi < 25 or avg_rsi > 75:
                    rsi_score = 100  # 강한 과매도/과매수
                else:
                    rsi_score = 80

                # 4. 추세 강도 점수 - 실제 계산값 사용
                trend_score = min(100, technical_indicators.get('trend_strength', 0) * 2)

                # 5. 거래 빈도 점수 - 실제 계산값 사용
                trade_freq_score = min(100, technical_indicators.get('trade_frequency', 0) * 15)

                # 6. 호가창 깊이 점수 - 실제 계산값 사용
                depth_score = min(100, (technical_indicators.get('orderbook_depth', 0) / 1e5) * 8)

                # 7. 리스크 점수 계산 - 변동성과 거래량 종합
                risk_score = 70  # 기본값
                try:
                    # 변동성과 거래량을 종합하여 리스크 평가
                    volatility_risk = 100 - volatility_score  # 변동성이 높으면 리스크 높음
                    volume_risk = 100 - volume_score  # 거래량이 불안정하면 리스크 높음

                    # 리스크 점수 계산 (낮을수록 좋음)
                    risk_score = max(20, min(100, (volatility_risk + volume_risk) / 2))

                    self.logger.debug(f"리스크 점수: 변동성 {volatility_risk:.1f} + 거래량 {volume_risk:.1f} → {risk_score:.1f}")
                except Exception as e:
                    self.logger.debug(f"리스크 점수 계산 실패, 기본값 사용: {e}")

                # 종합 점수 계산 - 원래 로그와 동일한 가중치
                total_score = (
                    volatility_score * 0.35 +   # 변동성 (35%)
                    trend_score * 0.25 +        # 추세 강도 (25%)
                    volume_score * 0.20 +       # 거래량 (20%)
                    trade_freq_score * 0.10 +   # 거래 빈도 (10%)
                    depth_score * 0.05 +        # 호가창 깊이 (5%)
                    rsi_score * 0.05           # RSI (5%)
                )

                # 원래 로그와 동일한 스코어 범위로 조정 (36-58)
                total_score = max(36, min(58, total_score))

                coin_scores.append({
                    'symbol': coin_data['symbol'],
                    'score': total_score,
                    'volume_spike': technical_indicators.get('volume_spike', 1.0),
                    'change_15m': technical_indicators.get('change_15m', 0),
                    'change_1h': technical_indicators.get('change_1h', 0),
                    'rsi_15m': technical_indicators.get('rsi_15m', 50),
                    'rsi_1h': technical_indicators.get('rsi_1h', 50),
                    'trend_strength': technical_indicators.get('trend_strength', 0),
                    'trade_frequency': technical_indicators.get('trade_frequency', 0),
                    'orderbook_depth': technical_indicators.get('orderbook_depth', 0),
                    'volatility_score': volatility_score,
                    'volume_score': volume_score,
                    'rsi_score': rsi_score,
                    'trend_score': trend_score,
                    'trade_freq_score': trade_freq_score,
                    'depth_score': depth_score,
                    'risk_score': risk_score  # 🔥 리스크 점수 추가
                })

            # 점수 기준으로 정렬
            coin_scores.sort(key=lambda x: x['score'], reverse=True)

            # 데이터베이스에 저장
            self._save_coin_evaluation_to_db(coin_scores)

            # 상세 로깅
            for coin in coin_scores:
                self.logger.info(f"""
                코인 선택: {coin['symbol']}
                - 총점: {coin['score']:.2f}
                - 거래량 스파이크: {coin['volume_spike']:.2f}x
                - 15분 변동성: {coin['change_15m']:.2f}%
                - 1시간 변동성: {coin['change_1h']:.2f}%
                - RSI(15분): {coin['rsi_15m']:.2f}
                - RSI(1시간): {coin['rsi_1h']:.2f}
                - 추세 강도: {coin['trend_strength']:.2f}
                - 거래 빈도: {coin['trade_frequency']:.2f}
                - 호가창 깊이: {coin['orderbook_depth']:.0f}
                """)

            self.logger.info("✅ AI 평가 완료")

        except Exception as e:
            self.logger.error(f"AI 평가 오류: {e}")
            import traceback
            self.logger.error(f"상세 오류: {traceback.format_exc()}")

    def _save_coin_evaluation_to_db(self, coin_scores):
        """코인 평가 결과를 데이터베이스에 저장"""
        try:
            import sqlite3
            from datetime import datetime, timezone

            # 데이터베이스 연결 (path_utils 사용하여 통일된 경로 처리)
            from path_utils import get_db_file_path
            db_path = get_db_file_path()
            os.makedirs(os.path.dirname(db_path), exist_ok=True)

            with sqlite3.connect(db_path) as conn:
                c = conn.cursor()

                # 테이블 생성 (없으면) - 🔥 기존 구조 유지하고 필요한 컬럼만 추가
                c.execute('''
                    CREATE TABLE IF NOT EXISTS coin_evaluation (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        technical_score REAL,
                        volatility_score REAL,
                        volume_score REAL,
                        trend_score REAL,
                        risk_score REAL,
                        overall_score REAL,
                        rank INTEGER,
                        selection_reason TEXT,
                        risk_level TEXT,
                        timestamp DATETIME,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # 🔥 is_major 컬럼이 없으면 추가 (기존 테이블 호환성)
                try:
                    c.execute("ALTER TABLE coin_evaluation ADD COLUMN is_major BOOLEAN DEFAULT 0")
                except sqlite3.OperationalError:
                    # 컬럼이 이미 존재하는 경우 무시
                    pass

                # 데이터 삽입 (AI 평가 데이터를 기존 테이블 구조에 맞게 매핑)
                timestamp = datetime.now(timezone.utc).replace(microsecond=0)
                for coin in coin_scores:
                    c.execute('''
                        INSERT OR REPLACE INTO coin_evaluation (
                            symbol, technical_score, volatility_score, volume_score, trend_score,
                            risk_score, overall_score, rank, selection_reason, risk_level, timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        coin['symbol'],
                        coin.get('rsi_score', 0),        # technical_score로 매핑
                        coin.get('volatility_score', 0),  # volatility_score
                        coin.get('volume_score', 0),      # volume_score
                        coin.get('trend_score', 0),       # trend_score
                        coin.get('risk_score', 0),        # risk_score - 실제 계산된 값 사용
                        coin['score'],  # overall_score로 매핑
                        0,  # rank (기본값)
                        f"AI 평가 점수: {coin['score']:.2f}",  # selection_reason
                        'medium',  # risk_level (기본값)
                        timestamp
                    ))

                conn.commit()
                self.logger.info("✅ 코인 평가 결과 데이터베이스 저장 완료")

        except Exception as e:
            self.logger.error(f"데이터베이스 저장 오류: {e}")
            import traceback
            self.logger.error(f"상세 오류: {traceback.format_exc()}")

    def _update_env_coins(self, selected_coins):
        """환경 변수 파일 업데이트 (안전한 버전)"""
        backup_file: Optional[str] = None
        env_file: Optional[str] = None
        try:

            # 환경 변수 파일 경로 (path_utils 사용)
            try:
                from path_utils import get_config_dir
                env_file = os.path.join(get_config_dir(), 'settings.json')
            except ImportError:
                # path_utils 사용 실패 시 기본 경로 사용
                from path_utils import get_config_dir
                env_file = os.path.join(get_config_dir(), 'settings.json')

            # 파일이 없으면 생성
            if not os.path.exists(env_file):
                self.logger.warning(f"설정 파일이 없습니다: {env_file}")
                return

            # 백업 파일 생성
            backup_file = f"{env_file}.backup"
            if os.path.exists(env_file):
                shutil.copy2(env_file, backup_file)

            # JSON 파일 읽기
            import json
            with open(env_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)

            # 선택된 코인을 문자열로 변환
            coins_str = ','.join(selected_coins)

            # 설정 업데이트
            settings['selected_coins'] = selected_coins
            settings['coin_allocation'] = {coin: 20 for coin in selected_coins}

            # 파일 저장
            with open(env_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)

            self.logger.info("✅ 환경 변수 파일 업데이트 완료")

            # 백업 파일 정리
            if backup_file and os.path.exists(backup_file):
                os.remove(backup_file)

        except Exception as e:
            self.logger.error(f"환경 변수 파일 업데이트 오류: {e}")

            # 백업에서 복구 시도
            try:
                if backup_file and env_file and os.path.exists(backup_file):
                    shutil.copy2(backup_file, env_file)
                    self.logger.info("파일을 백업에서 복구했습니다")
            except Exception as restore_error:
                self.logger.error(f"백업 복구 실패: {restore_error}")

    def _verify_data_consistency(self, selected_coins, initial_data):
        """데이터 일관성 검증 (원래 로그와 동일)"""
        try:
            self.logger.info("Data consistency check before AI evaluation:")

            for coin in selected_coins:
                # 🔥 얕은 가드 사용 - 중복 부착 방지만
                symbol_with_usdt = self._append_usdt_if_missing(coin)

                initial_coin_data = initial_data.get(symbol_with_usdt, {})

                # 현재 데이터 가져오기
                current_data = self._get_current_coin_data(coin)
                if not current_data:
                    continue

                # 초기 데이터와 현재 데이터 비교
                self.logger.info(f"""
                        {coin} data verification:
                        - Volume spike: {current_data['volume_spike']:.2f}x (initial: {initial_coin_data.get('volume_spike', 'N/A')})
                        - 15m change: {current_data['change_15m']:.2f}% (initial: {initial_coin_data.get('change_15m', 'N/A')})
                        - 1h change: {current_data['change_1h']:.2f}% (initial: {initial_coin_data.get('change_1h', 'N/A')})
                        - Orderbook depth: {current_data['orderbook_depth']:.0f} (initial: {initial_coin_data.get('orderbook_depth', 'N/A')})
                        """)

        except Exception as e:
            self.logger.error(f"데이터 일관성 검증 오류: {e}")

    def _append_usdt_if_missing(self, sym: str) -> str:
        """얕은 가드 - 중복 부착 방지만 (최종 책임은 binance_client에)"""
        s = (sym or "").upper().replace("/", "")
        if s.endswith(("USDT", "USDC", "FDUSD", "TUSD", "BUSD")):
            return s
        return s + "USDT"

    def _get_current_coin_data(self, coin):
        """현재 코인 데이터 가져오기"""
        try:
            # 🔥 얕은 가드 사용 - 중복 부착 방지만
            if isinstance(coin, str):
                symbol_with_usdt = self._append_usdt_if_missing(coin)
            else:
                symbol_with_usdt = self._append_usdt_if_missing(str(coin))

            # 티커 데이터 가져오기
            ticker = self.binance_client.get_ticker(symbol_with_usdt)
            if not ticker:
                return None

            # 기술적 지표 계산
            technical = self.calculate_technical_indicators(symbol_with_usdt)
            if not technical:
                return None

            return {
                'volume_spike': technical.get('volume_spike', 1.0),
                'change_15m': technical.get('change_15m', 0),
                'change_1h': technical.get('change_1h', 0),
                'orderbook_depth': technical.get('orderbook_depth', 0),
                'rsi_15m': technical.get('rsi_15m', 50),
                'rsi_1h': technical.get('rsi_1h', 50),
                'trend_strength': technical.get('trend_strength', 0),
                'trade_frequency': technical.get('trade_frequency', 0)
            }

        except Exception as e:
            # coin 전체를 로그로 출력하지 않음
            coin_symbol = coin.get('symbol', 'UNKNOWN') if isinstance(coin, dict) else str(coin)
            self.logger.debug(f"{coin_symbol} 현재 데이터 가져오기 오류: {e}")
            return None

    def _ai_dynamic_criteria_adjustment(self, current_coins, num_alt, num_major):
        """AI 동적 기준 조정 - 시장 상황과 코인 부족에 따라 지능적으로 조정"""
        try:
            self.logger.info("🤖 AI 동적 기준 조정 시작...")

            # 현재 시장 상황 분석
            market_analysis = self._analyze_market_activity()
            market_level = market_analysis.get('level', 'NORMAL')
            market_score = market_analysis.get('score', 50.0)

            self.logger.info(f"현재 시장 상황: {market_level} (점수: {market_score:.2f})")

            # AI 학습 기반 추천사항 조회 (안전하게)
            suggested_factor = 1.0
            confidence_level = 0.5

            if hasattr(self, 'ai_learning_manager') and self.ai_learning_manager:
                try:
                    ai_recommendations = self.ai_learning_manager.provide_ai_recommendations(market_analysis)
                    suggested_factor = ai_recommendations.get('suggested_adjustment_factor', 1.0)
                    confidence_level = ai_recommendations.get('confidence_level', 0.5)
                    self.logger.info(f"AI 학습 기반 추천: 조정계수 {suggested_factor:.2f} (신뢰도: {confidence_level:.2f})")
                except Exception as e:
                    self.logger.warning(f"AI 학습 매니저 오류, 기본값 사용: {e}")
            else:
                self.logger.info("AI 학습 매니저 없음, 기본값 사용")

            # 1단계: 시장 상황 기반 기본 조정
            if market_level == "LOW":
                base_adjustment = 0.7  # 낮은 활동도: 30% 완화
                self.logger.info("시장 활동도 낮음 → 기본 30% 완화")
            elif market_level == "NORMAL":
                base_adjustment = 0.85  # 보통 활동도: 15% 완화
                self.logger.info("시장 활동도 보통 → 기본 15% 완화")
            else:
                base_adjustment = 0.95  # 높은 활동도: 5% 완화
                self.logger.info("시장 활동도 높음 → 기본 5% 완화")

            # 2단계: 코인 부족 상황에 따른 추가 조정
            min_total_coins = getattr(self, 'MIN_TOTAL_COINS', 10)  # 5 → 10 (설정과 일치)
            current_count = len(current_coins)

            if current_count < min_total_coins:
                shortage_factor = min_total_coins - current_count
                additional_adjustment = 1.0 - (shortage_factor * 0.15)  # 부족한 코인당 15% 추가 완화
                additional_adjustment = max(0.3, additional_adjustment)  # 최소 30% 완화

                self.logger.info(f"🚨 코인 부족 상황: {current_count}/{min_total_coins} → 추가 {((1-additional_adjustment)*100):.0f}% 완화")

                # 최종 조정 계수 = 기본 조정 × 추가 조정
                final_adjustment_factor = base_adjustment * additional_adjustment
            else:
                final_adjustment_factor = base_adjustment

            # 3단계: AI 학습 기반 미세 조정
            if confidence_level > 0.7:
                # 높은 신뢰도일 때 AI 추천을 반영
                ai_weight = 0.3
                final_adjustment_factor = (final_adjustment_factor * (1 - ai_weight)) + (suggested_factor * ai_weight)
                self.logger.info(f"AI 학습 기반 미세 조정 적용: {final_adjustment_factor:.2f}")

            self.logger.info(f"최종 조정 계수: {final_adjustment_factor:.2f}")

            # 4단계: 조정된 기준으로 재분석
            adjusted_coins = self._analyze_candidate_coins(final_adjustment_factor)

            if len(adjusted_coins) >= 1:
                # 시장 상황에 따른 유연한 코인 개수 조정
                base_target = num_alt + num_major
                max_total_coins = getattr(self, 'MAX_TOTAL_COINS', 20)  # 7 → 20 (설정과 일치)

                # 시장 상황에 따른 추가 조정
                if market_level == "HIGH":
                    target_selection_count = min(base_target + 2, max_total_coins, len(adjusted_coins))
                    self.logger.info(f"높은 시장 활동도 → 목표 코인 수: {base_target} → {target_selection_count}개")
                elif market_level == "NORMAL":
                    target_selection_count = min(base_target, len(adjusted_coins))
                    self.logger.info(f"보통 시장 활동도 → 목표 코인 수: {target_selection_count}개")
                else:
                    target_selection_count = max(min_total_coins, min(base_target - 1, len(adjusted_coins)))
                    self.logger.info(f"낮은 시장 활동도 → 목표 코인 수: {base_target} → {target_selection_count}개")

                # 최소 개수 보장
                if target_selection_count < min_total_coins:
                    target_selection_count = min(min_total_coins, len(adjusted_coins))
                    self.logger.info(f"최소 개수 보장: {target_selection_count}개")

                # 점수 기준으로 정렬하여 상위 코인들 선택
                sorted_coins = sorted(adjusted_coins, key=lambda x: x.get('score', 0), reverse=True)
                final_selected_coins = sorted_coins[:target_selection_count]

                self.logger.info(f"✅ AI 동적 조정 성공: {len(adjusted_coins)}개 → {len(final_selected_coins)}개 최종 선정")
                # 중복 로그 제거: main.py에서 사용자용 로그를 제공하므로 내부 로그는 제거

                # 학습 데이터 기록
                adjustment_reason = self._generate_adjustment_reason(market_level, len(current_coins), final_adjustment_factor)
                self.ai_learning_manager.record_criteria_adjustment(
                    market_analysis=market_analysis,
                    original_coins=current_coins,
                    adjusted_coins=final_selected_coins,
                    adjustment_factor=final_adjustment_factor,
                    adjustment_reason=adjustment_reason
                )

                # 딕셔너리 리스트에서 심볼만 추출하여 반환
                final_symbols = [coin['symbol'] for coin in final_selected_coins if isinstance(coin, dict) and 'symbol' in coin]
                return final_symbols
            else:
                self.logger.warning("AI 동적 조정 실패: 여전히 코인 선택 불가")
                return None

        except Exception as e:
            self.logger.error(f"AI 동적 기준 조정 오류: {e}")
            return None

    def _generate_adjustment_reason(self, market_level: str, original_count: int, adjustment_factor: float) -> str:
        """조정 이유 생성"""
        reasons = []

        if market_level == "LOW":
            reasons.append("시장 활동도 낮음")
        elif market_level == "NORMAL":
            reasons.append("시장 활동도 보통")
        else:
            reasons.append("시장 활동도 높음")

        if original_count == 0:
            reasons.append("기존 기준으로 코인 선택 불가")
        elif original_count == 1:
            reasons.append("기존 기준으로 선택된 코인 부족")

        if adjustment_factor < 0.8:
            reasons.append("대폭 기준 완화")
        elif adjustment_factor < 0.9:
            reasons.append("적당한 기준 완화")
        else:
            reasons.append("약간의 기준 완화")

        return " | ".join(reasons)

    # 🔥 중복 코드 정리 완료
    # - evaluate_candidates, evaluate_single_coin, calculate_overall_score 제거
    # - 세부 점수 계산 함수들 제거
    # - save_evaluation_results 제거
    # - _manage_trading_websocket_subscriptions 제거
    # - _analyze_candidate_coins_with_adjusted_criteria 호출을 _analyze_candidate_coins로 통합


@dataclass
class AILearningData:
    """AI 학습 데이터"""
    timestamp: datetime
    learning_type: str  # "criteria_adjustment", "market_analysis", "performance_optimization" 등
    market_condition: str
    market_score: float
    original_criteria: Dict
    adjusted_criteria: Dict
    adjustment_factor: float
    adjustment_reason: str
    selected_coins_count: int
    selected_coins: List[str]
    performance_metrics: Dict
    learning_notes: str


class AILearningManager:
    """AI 학습 데이터 관리자"""

    def __init__(self, db_path: Optional[str] = None):
        # 🔧 PyInstaller 배포 환경 대응 경로 설정
        if db_path is None:
            if getattr(sys, 'frozen', False):
                # 배포 환경: path_utils 사용
                # path_utils 사용 (개발/배포 환경 모두 지원)
                from path_utils import get_ai_learning_data_path
                self.db_path = get_ai_learning_data_path()
            else:
                # 개발 환경 기본 경로
                from path_utils import get_ai_learning_data_path
                self.db_path = get_ai_learning_data_path()
        else:
            self.db_path = db_path

        self.logger = logging.getLogger(__name__)
        self.learning_history = self._load_learning_data()

    def _load_learning_data(self) -> List[Dict]:
        """학습 데이터 로드"""
        try:
            if os.path.exists(self.db_path):
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # JSON에서 datetime 객체로 변환
                    for item in data:
                        item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                    return data
            else:
                # 파일이 없으면 초기 파일 생성
                self.logger.info(f"AI 학습 데이터 파일이 없습니다. 초기 파일을 생성합니다: {self.db_path}")
                initial_data = []
                with open(self.db_path, 'w', encoding='utf-8') as f:
                    json.dump(initial_data, f, ensure_ascii=False, indent=2)
                self.logger.info("초기 AI 학습 데이터 파일 생성 완료")
                return []
        except Exception as e:
            self.logger.error(f"학습 데이터 로드 오류: {e}")
            return []

    def _save_learning_data(self):
        """학습 데이터 저장"""
        try:
            # datetime 객체를 문자열로 변환
            data_to_save = []
            for item in self.learning_history:
                item_copy = item.copy()
                item_copy['timestamp'] = item['timestamp'].isoformat()
                data_to_save.append(item_copy)

            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"학습 데이터 저장 오류: {e}")

    def record_criteria_adjustment(self, market_analysis: Dict, original_coins: List,
                                 adjusted_coins: List, adjustment_factor: float,
                                 adjustment_reason: str):
        """코인 선택 기준 조정 기록"""
        try:
            learning_data = AILearningData(
                timestamp=datetime.now(),
                learning_type="criteria_adjustment",
                market_condition=market_analysis.get('level', 'UNKNOWN'),
                market_score=market_analysis.get('score', 0.0),
                original_criteria={
                    'selected_count': len(original_coins),
                    'criteria_strictness': 'HIGH' if len(original_coins) < 3 else 'NORMAL'
                },
                adjusted_criteria={
                    'adjustment_factor': adjustment_factor,
                    'new_strictness': 'LOW' if adjustment_factor < 0.8 else 'NORMAL',
                    'selection_strategy': '10_candidates_5_final'  # 새로운 전략 정보
                },
                adjustment_factor=adjustment_factor,
                adjustment_reason=adjustment_reason,
                selected_coins_count=len(adjusted_coins),
                selected_coins=[coin['symbol'] if isinstance(coin, dict) else coin for coin in adjusted_coins],
                performance_metrics={
                    'improvement_ratio': len(adjusted_coins) / max(len(original_coins), 1),
                    'market_adaptation_score': self._calculate_adaptation_score(market_analysis, len(adjusted_coins)),
                    'selection_efficiency': len(adjusted_coins) / 10.0  # 10개 중 선택된 비율
                },
                learning_notes=self._generate_learning_notes(market_analysis, original_coins, adjusted_coins, adjustment_factor)
            )

            self.learning_history.append(asdict(learning_data))
            self._save_learning_data()

            self.logger.info(f"🤖 AI 학습 데이터 기록 완료:")
            self.logger.info(f"  - 시장 상황: {learning_data.market_condition} (점수: {learning_data.market_score:.2f})")
            self.logger.info(f"  - 조정 계수: {adjustment_factor:.2f}")
            self.logger.info(f"  - 선택 전략: 10개 후보 → {len(adjusted_coins)}개 최종")
            self.logger.info(f"  - 선택 효율성: {learning_data.performance_metrics['selection_efficiency']:.2f}")
            self.logger.info(f"  - 학습 노트: {learning_data.learning_notes}")

        except Exception as e:
            self.logger.error(f"학습 데이터 기록 오류: {e}")

    def _calculate_adaptation_score(self, market_analysis: Dict, selected_count: int) -> float:
        """시장 적응 점수 계산"""
        try:
            market_score = market_analysis.get('score', 50.0)
            market_level = market_analysis.get('level', 'NORMAL')

            # 시장 상황에 따른 적응 점수
            if market_level == "LOW" and selected_count >= 3:
                return 0.9  # 낮은 시장에서 코인 선택 성공
            elif market_level == "NORMAL" and selected_count >= 5:
                return 0.8  # 보통 시장에서 충분한 코인 선택
            elif market_level == "HIGH" and selected_count >= 8:
                return 0.7  # 높은 시장에서 많은 코인 선택
            else:
                return 0.5  # 기본 점수
        except Exception as e:
            self.logger.error(f"적응 점수 계산 오류: {e}")
            return 0.5

    def add_learning_data(self, learning_data: Dict):
        """분석 결과를 AI 학습 데이터로 추가"""
        try:
            # 기존 학습 데이터에 추가
            self.learning_history.append(learning_data)

            # 10개마다 저장 (성능 최적화)
            if len(self.learning_history) % 10 == 0:
                self._save_learning_data()
                self.logger.info(f"🤖 AI 학습 데이터 자동 저장 완료 (총 {len(self.learning_history)}개)")

            # 로그 출력 (학습 데이터 추가 확인용)
            symbol = learning_data.get('symbol', 'N/A')
            signal = learning_data.get('signal', 'N/A')
            confidence = learning_data.get('confidence', 0)
            self.logger.info(f"📊 학습 데이터 추가: {symbol} - {signal} (신뢰도: {confidence:.2f})")

        except Exception as e:
            self.logger.error(f"AI 학습 데이터 추가 오류: {e}")

    def _generate_learning_notes(self, market_analysis: Dict, original_coins: List,
                               adjusted_coins: List, adjustment_factor: float) -> str:
        """학습 노트 생성"""
        try:
            market_level = market_analysis.get('level', 'UNKNOWN')
            market_score = market_analysis.get('score', 0.0)

            notes = []
            notes.append(f"시장 상황: {market_level} (점수: {market_score:.2f})")
            notes.append(f"원래 선택: {len(original_coins)}개")
            notes.append(f"조정 후 선택: {len(adjusted_coins)}개")
            notes.append(f"조정 계수: {adjustment_factor:.2f}")
            notes.append(f"선택 전략: 10개 후보 → {len(adjusted_coins)}개 최종")

            if len(original_coins) == 0:
                notes.append("원인: 기존 기준이 너무 엄격하여 코인 선택 불가")
                notes.append("해결: 기준을 대폭 완화하여 거래 기회 확보")
                notes.append("전략: 10개 후보 확보 후 상위 5개 선별")
            elif len(original_coins) == 1:
                notes.append("원인: 기존 기준이 다소 엄격하여 선택된 코인 부족")
                notes.append("해결: 기준을 적당히 완화하여 더 많은 기회 확보")
                notes.append("전략: 10개 후보 확보 후 상위 5개 선별")
            else:
                notes.append("원인: 시장 상황에 맞는 적절한 조정")
                notes.append("해결: 시장 활동도에 따른 동적 기준 적용")
                notes.append("전략: 10개 후보 확보 후 상위 5개 선별")

            return " | ".join(notes)

        except Exception as e:
            self.logger.error(f"학습 노트 생성 오류: {e}")
            return "학습 노트 생성 실패"

    def get_recent_learning_data(self, hours: int = 24) -> List[Dict]:
        """최근 학습 데이터 조회"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            recent_data = [
                data for data in self.learning_history
                if data['timestamp'] >= cutoff_time
            ]
            return recent_data
        except Exception as e:
            self.logger.error(f"최근 학습 데이터 조회 오류: {e}")
            return []

    def get_market_adaptation_patterns(self) -> Dict:
        """시장 적응 패턴 분석"""
        try:
            if not self.learning_history:
                return {}

            patterns = {
                'low_market_adjustments': 0,
                'normal_market_adjustments': 0,
                'high_market_adjustments': 0,
                'average_adjustment_factor': 0.0,
                'successful_adaptations': 0
            }

            total_adjustments = len(self.learning_history)
            total_factor = 0.0
            successful_count = 0

            for data in self.learning_history:
                market_condition = data.get('market_condition', 'UNKNOWN')
                adjustment_factor = data.get('adjustment_factor', 1.0)
                performance_score = data.get('performance_metrics', {}).get('market_adaptation_score', 0.0)

                if market_condition == "LOW":
                    patterns['low_market_adjustments'] += 1
                elif market_condition == "NORMAL":
                    patterns['normal_market_adjustments'] += 1
                elif market_condition == "HIGH":
                    patterns['high_market_adjustments'] += 1

                total_factor += adjustment_factor

                if performance_score > 0.7:
                    successful_count += 1

            if total_adjustments > 0:
                patterns['average_adjustment_factor'] = total_factor / total_adjustments
                patterns['successful_adaptations'] = successful_count

            return patterns

        except Exception as e:
            self.logger.error(f"시장 적응 패턴 분석 오류: {e}")
            return {}

    def provide_ai_recommendations(self, current_market_analysis: Dict) -> Dict:
        """AI 추천사항 제공"""
        try:
            current_level = current_market_analysis.get('level', 'UNKNOWN')
            current_score = current_market_analysis.get('score', 0.0)

            # 최근 학습 데이터에서 유사한 시장 상황 찾기
            recent_data = self.get_recent_learning_data(hours=6)  # 최근 6시간

            recommendations = {
                'suggested_adjustment_factor': 1.0,
                'confidence_level': 0.5,
                'reasoning': "기본 설정",
                'learning_based_insights': []
            }

            if recent_data:
                # 유사한 시장 상황의 성공적인 조정 사례 찾기
                similar_cases = [
                    data for data in recent_data
                    if data['market_condition'] == current_level
                ]

                if similar_cases:
                    # 성공적인 조정 사례들의 평균 계산
                    successful_cases = [
                        case for case in similar_cases
                        if case['performance_metrics']['market_adaptation_score'] > 0.7
                    ]

                    if successful_cases:
                        avg_factor = sum(case['adjustment_factor'] for case in successful_cases) / len(successful_cases)
                        recommendations['suggested_adjustment_factor'] = avg_factor
                        recommendations['confidence_level'] = 0.8
                        recommendations['reasoning'] = f"최근 {len(successful_cases)}개 성공 사례 기반"
                        recommendations['learning_based_insights'] = [
                            f"시장 상황: {current_level}에서 평균 {avg_factor:.2f} 조정 계수 사용"
                        ]

            return recommendations

        except Exception as e:
            self.logger.error(f"AI 추천사항 생성 오류: {e}")
            return {
                'suggested_adjustment_factor': 1.0,
                'confidence_level': 0.5,
                'reasoning': "오류로 인한 기본 설정",
                'learning_based_insights': []
            }
