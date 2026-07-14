#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
거래소별 학습 데이터 관리자
- 바이낸스: ai_learning_data_binance.json
- 업비트: ai_learning_data_upbit.json
- 빗썸: ai_learning_data_bithumb.json
"""

import os
import json
import logging
import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional
from dataclasses import dataclass, asdict
import sys
from api.kpi_client import emit_kpi_event


_FILE_LOCKS: Dict[str, threading.Lock] = {}


def _get_file_lock(path: str) -> threading.Lock:
    """파일 경로별 락을 반환합니다."""
    key = os.path.abspath(path)
    lock = _FILE_LOCKS.get(key)
    if lock is None:
        lock = threading.Lock()
        _FILE_LOCKS[key] = lock
    return lock


@dataclass
class ExchangeLearningData:
    """거래소별 학습 데이터"""
    timestamp: datetime
    exchange: str  # "binance", "upbit", "bithumb"
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
    # 현물 거래 특화 필드
    spot_trading_metrics: Dict  # TP/SL 성공률, 수수료 등
    api_usage_stats: Dict  # API 호출 횟수, 제한 상태 등


class ExchangeLearningManager:
    """거래소별 학습 데이터 관리자"""

    def __init__(self, exchange: str = "binance"):
        """
        거래소별 학습 매니저 초기화

        Args:
            exchange: "binance", "upbit", "bithumb"
        """
        self.exchange = exchange.lower()
        self.logger = logging.getLogger(f"{__name__}.{self.exchange}")

        # 거래소별 파일 경로 설정
        self.db_path = self._get_exchange_learning_path()

        # 학습 데이터 로드
        self.learning_history = self._load_learning_data()

        # API 제한 설정 (거래소별)
        self.api_limits = self._get_api_limits()

        # API 요청 빈도 추적(최근 1분 롤링 윈도우)
        self._api_request_times: Deque[datetime] = deque(maxlen=4000)
        self._api_rate_lock = threading.Lock()

        self.logger.info(f"{self.exchange.upper()} 학습 매니저 초기화 완료")

    def _get_exchange_learning_path(self) -> str:
        """거래소별 학습 데이터 파일 경로 반환"""
        try:
            # path_utils 사용 (개발/배포 환경 모두 지원)
            from path_utils import get_app_data_dir
            data_dir = get_app_data_dir()

            # 개발 환경에서 계정 하위 폴더 자동 보정
            # (예: noahai_client/data/nwsoft/ 을 선호)
            try:
                base_name = os.path.basename(os.path.normpath(data_dir))
                if base_name == 'data':
                    # 1) 환경변수 우선
                    preferred = os.getenv('NOAHAI_ACCOUNT', '').strip()
                    candidate_dir = None
                    if preferred:
                        pd = os.path.join(data_dir, preferred)
                        if os.path.isdir(pd):
                            candidate_dir = pd
                    # 2) 일반적으로 많이 쓰는 계정명 우선(nwsoft)
                    if candidate_dir is None:
                        subs = [d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))]
                        if 'nwsoft' in subs:
                            candidate_dir = os.path.join(data_dir, 'nwsoft')
                        elif len(subs) == 1:
                            candidate_dir = os.path.join(data_dir, subs[0])
                    if candidate_dir:
                        data_dir = candidate_dir
            except Exception:
                pass

            # 거래소별 파일명 (계정별 폴더 사용)
            return os.path.join(data_dir, f'ai_learning_data_{self.exchange}.json')

        except Exception as e:
            self.logger.error(f"학습 데이터 경로 설정 오류: {e}")
            # 폴백: path_utils 사용
            from path_utils import get_exchange_ai_learning_data_path
            return get_exchange_ai_learning_data_path(self.exchange)

    def _get_api_limits(self) -> Dict:
        """거래소별 API 제한 설정"""
        limits = {
            "binance": {
                "requests_per_minute": 1200,
                "analysis_delay": 0.1,  # 100ms
                "max_coins_per_analysis": 100,
                "websocket_supported": True
            },
            "upbit": {
                "requests_per_minute": 600,
                "analysis_delay": 0.2,  # 200ms (더 보수적)
                "max_coins_per_analysis": 50,  # 현물이므로 적게
                "websocket_supported": True
            },
            "bithumb": {
                "requests_per_minute": 300,
                "analysis_delay": 0.3,  # 300ms (가장 보수적)
                "max_coins_per_analysis": 30,  # 현물이므로 더 적게
                "websocket_supported": False
            }
        }
        return limits.get(self.exchange, limits["binance"])

    def _load_learning_data(self) -> List[Dict]:
        """학습 데이터 로드"""
        try:
            if os.path.exists(self.db_path):
                data = self._read_json_list_safe(self.db_path)
                # JSON에서 datetime 객체로 변환
                for item in data:
                    try:
                        ts = datetime.fromisoformat(item['timestamp'])
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        item['timestamp'] = ts
                    except Exception:
                        pass
                return data
            else:
                # 파일이 없으면 초기 파일 생성
                self.logger.info(f"{self.exchange.upper()} 학습 데이터 파일이 없습니다. 초기 파일을 생성합니다: {self.db_path}")
                initial_data = []
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
                self._atomic_write_json(self.db_path, initial_data)
                self.logger.info(f"{self.exchange.upper()} 초기 학습 데이터 파일 생성 완료")
                return []
        except Exception as e:
            self.logger.error(f"{self.exchange.upper()} 학습 데이터 로드 오류: {e}")
            return []

    def _save_learning_data(self):
        """학습 데이터 저장 (일간 아카이브 자동 로테이션 포함)"""
        try:
            # 1단계: 아카이브 로테이션 (상한 초과 데이터를 아카이브로 이동)
            self._rotate_to_archive()
            
            # 2단계: 운영 파일은 최신 N개만 유지 (UI/판단 성능 보호)
            max_entries = self._get_retention_limit()
            if len(self.learning_history) > max_entries:
                self.learning_history = self.learning_history[-max_entries:]

            # 3단계: datetime 객체를 문자열로 변환
            data_to_save = []
            for item in self.learning_history:
                item_copy = item.copy()
                # timestamp는 datetime 또는 이미 문자열일 수 있음
                try:
                    ts = item.get('timestamp')
                    if ts is None:
                        ts_str = datetime.now(timezone.utc).isoformat()
                    elif isinstance(ts, str):
                        ts_str = ts
                    else:
                        # datetime 또는 유사 객체인 경우
                        ts_str = ts.isoformat()
                    item_copy['timestamp'] = ts_str
                except Exception:
                    # 최후 폴백: 문자열 변환
                    item_copy['timestamp'] = str(item.get('timestamp', datetime.now(timezone.utc).isoformat()))
                data_to_save.append(item_copy)

            # 4단계: 저장 경로 확인 로그
            self.logger.info(f"💾 {self.exchange.upper()} 학습 데이터 저장 경로: {self.db_path}")
            self.logger.info(f"💾 저장할 데이터 개수: {len(data_to_save)}개")
            self.logger.info(f"💾 보관 상한: {max_entries}개")

            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._atomic_write_json(self.db_path, data_to_save)

            self.logger.info(f"✅ {self.exchange.upper()} 학습 데이터 저장 완료")
        except Exception as e:
            self.logger.error(f"{self.exchange.upper()} 학습 데이터 저장 오류: {e}")

    def _get_retention_limit(self) -> int:
        """거래소 특성에 맞춘 학습 데이터 보관 상한(기본 10,000 이하)."""
        # 선물(고빈도) 거래소는 10,000, 현물 거래소는 6,000으로 제한
        # 기본값도 8,000으로 유지해 단일 파일 과성장을 방지
        limits = {
            'binance': 10000,
            'bybit': 10000,
            'okx': 10000,
            'bitget': 10000,
            'upbit': 6000,
            'bithumb': 6000,
        }
        return int(limits.get(self.exchange, 8000))

    def _get_archive_path(self) -> str:
        """날짜별 아카이브 파일 경로 반환 (YYYYMMDD 패턴)"""
        base_dir = os.path.dirname(self.db_path)
        today = datetime.now().strftime('%Y%m%d')
        archive_filename = f'ai_learning_data_{self.exchange}_archive_{today}.json'
        return os.path.join(base_dir, archive_filename)

    def _rotate_to_archive(self):
        """상한 초과 데이터를 일간 아카이브로 이동합니다."""
        max_entries = self._get_retention_limit()
        if len(self.learning_history) > max_entries:
            excess_count = len(self.learning_history) - max_entries
            # 제거될 데이터 (오래된 항목들)
            archived_data = self.learning_history[:excess_count]
            
            archive_path = self._get_archive_path()
            try:
                # 기존 아카이브 데이터 로드
                existing_archive = []
                if os.path.exists(archive_path):
                    existing_archive = self._read_json_list_safe(archive_path)
                
                # 제거될 데이터를 아카이브에 추가
                for item in archived_data:
                    item_copy = item.copy()
                    ts = item.get('timestamp')
                    if ts and not isinstance(ts, str):
                        # datetime 객체를 ISO 형식으로 변환
                        item_copy['timestamp'] = ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
                    existing_archive.append(item_copy)
                
                # 아카이브 파일에 저장
                os.makedirs(os.path.dirname(archive_path), exist_ok=True)
                self._atomic_write_json(archive_path, existing_archive)
                self.logger.info(f"📦 {self.exchange.upper()} 일간 아카이브: {excess_count}개 항목을 {archive_path}로 이동")
            except Exception as e:
                self.logger.warning(f"⚠️ {self.exchange.upper()} 아카이브 로테이션 실패: {e}")
                # 아카이브 실패는 무시 (운영 파일은 정상 저장됨)

    def record_criteria_adjustment(self, market_analysis: Dict, original_coins: List,
                                 adjusted_coins: List, adjustment_factor: float,
                                 adjustment_reason: str, spot_metrics: Optional[Dict] = None):
        """코인 선택 기준 조정 기록 (거래소별)"""
        try:
            # 현물 거래 특화 메트릭
            if spot_metrics is None:
                spot_metrics = self._get_default_spot_metrics()

            # API 사용량 통계
            api_stats = self._get_api_usage_stats()

            learning_data = ExchangeLearningData(
                timestamp=datetime.now(timezone.utc),
                exchange=self.exchange,
                learning_type="criteria_adjustment",
                market_condition=market_analysis.get('level', 'UNKNOWN'),
                market_score=market_analysis.get('score', 0.0),
                original_criteria={
                    'selected_count': len(original_coins),
                    'criteria_strictness': 'HIGH' if len(original_coins) < 3 else 'NORMAL',
                    'exchange_type': 'futures' if self.exchange == 'binance' else 'spot'
                },
                adjusted_criteria={
                    'adjustment_factor': adjustment_factor,
                    'new_strictness': 'LOW' if adjustment_factor < 0.8 else 'NORMAL',
                    'selection_strategy': self._get_selection_strategy(),
                    'api_limits_applied': self.api_limits
                },
                adjustment_factor=adjustment_factor,
                adjustment_reason=adjustment_reason,
                selected_coins_count=len(adjusted_coins),
                selected_coins=[coin['symbol'] if isinstance(coin, dict) else coin for coin in adjusted_coins],
                performance_metrics={
                    'improvement_ratio': len(adjusted_coins) / max(len(original_coins), 1),
                    'market_adaptation_score': self._calculate_adaptation_score(market_analysis, len(adjusted_coins)),
                    'selection_efficiency': len(adjusted_coins) / self.api_limits['max_coins_per_analysis']
                },
                learning_notes=self._generate_learning_notes(market_analysis, original_coins, adjusted_coins, adjustment_factor),
                spot_trading_metrics=spot_metrics,
                api_usage_stats=api_stats
            )

            self.learning_history.append(asdict(learning_data))
            self._save_learning_data()

            # 글로벌 집계 파일에도 동시 기록
            try:
                self._append_to_global_aggregator(asdict(learning_data))
            except Exception as agg_e:
                self.logger.debug(f"글로벌 학습 집계 기록 스킵/오류: {agg_e}")

            self.logger.info(f"🤖 {self.exchange.upper()} AI 학습 데이터 기록 완료:")
            self.logger.info(f"  - 시장 상황: {learning_data.market_condition} (점수: {learning_data.market_score:.2f})")
            self.logger.info(f"  - 조정 계수: {adjustment_factor:.2f}")
            self.logger.info(f"  - 선택 전략: {self._get_selection_strategy()}")
            self.logger.info(f"  - 선택 효율성: {learning_data.performance_metrics['selection_efficiency']:.2f}")
            self.logger.info(f"  - API 제한: {self.api_limits['requests_per_minute']} req/min, {self.api_limits['analysis_delay']}s 딜레이")

        except Exception as e:
            self.logger.error(f"{self.exchange.upper()} 학습 데이터 기록 오류: {e}")

    def _get_default_spot_metrics(self) -> Dict:
        """현물 거래 기본 메트릭"""
        return {
            'tp_sl_success_rate': 0.0,
            'fee_efficiency': 0.0,
            'holding_period_avg': 0.0,
            'profit_margin_avg': 0.0,
            'risk_reward_ratio': 0.0
        }

    def _get_api_usage_stats(self) -> Dict:
        """API 사용량 통계"""
        now = datetime.now(timezone.utc)
        with self._api_rate_lock:
            cutoff = now - timedelta(minutes=1)
            while self._api_request_times and self._api_request_times[0] < cutoff:
                self._api_request_times.popleft()
            req_minute = len(self._api_request_times)
        return {
            'requests_this_hour': 0,
            'requests_this_minute': req_minute,
            'rate_limit_remaining': max(0, int(self.api_limits['requests_per_minute']) - req_minute),
            'last_request_time': now.isoformat()
        }

    def _get_selection_strategy(self) -> str:
        """거래소별 선택 전략"""
        strategies = {
            "binance": "futures_high_frequency",  # 선물 고빈도
            "upbit": "spot_balanced",  # 현물 균형
            "bithumb": "spot_conservative"  # 현물 보수적
        }
        return strategies.get(self.exchange, "default")

    def _calculate_adaptation_score(self, market_analysis: Dict, selected_count: int) -> float:
        """시장 적응 점수 계산 (거래소별)"""
        try:
            market_score = market_analysis.get('score', 50.0)
            market_level = market_analysis.get('level', 'NORMAL')

            # 거래소별 적응 점수 기준
            if self.exchange == "binance":
                # 바이낸스: 선물 거래 기준
                if market_level == "LOW" and selected_count >= 5:
                    return 0.9
                elif market_level == "NORMAL" and selected_count >= 10:
                    return 0.8
                elif market_level == "HIGH" and selected_count >= 15:
                    return 0.7
            else:
                # 업비트/빗썸: 현물 거래 기준 (더 보수적)
                if market_level == "LOW" and selected_count >= 3:
                    return 0.9
                elif market_level == "NORMAL" and selected_count >= 5:
                    return 0.8
                elif market_level == "HIGH" and selected_count >= 8:
                    return 0.7

            return 0.5  # 기본 점수
        except Exception as e:
            self.logger.error(f"적응 점수 계산 오류: {e}")
            return 0.5

    def _generate_learning_notes(self, market_analysis: Dict, original_coins: List,
                               adjusted_coins: List, adjustment_factor: float) -> str:
        """학습 노트 생성 (거래소별)"""
        try:
            market_level = market_analysis.get('level', 'UNKNOWN')
            market_score = market_analysis.get('score', 0.0)

            notes = []
            notes.append(f"거래소: {self.exchange.upper()}")
            notes.append(f"거래 유형: {'선물' if self.exchange == 'binance' else '현물'}")
            notes.append(f"시장 상황: {market_level} (점수: {market_score:.2f})")
            notes.append(f"원래 선택: {len(original_coins)}개")
            notes.append(f"조정 후 선택: {len(adjusted_coins)}개")
            notes.append(f"조정 계수: {adjustment_factor:.2f}")
            notes.append(f"API 제한: {self.api_limits['requests_per_minute']} req/min")

            if self.exchange == "binance":
                notes.append("전략: 선물 고빈도 거래")
            else:
                notes.append("전략: 현물 보수적 거래")
                notes.append(f"최대 분석 코인: {self.api_limits['max_coins_per_analysis']}개")

            return " | ".join(notes)

        except Exception as e:
            self.logger.error(f"학습 노트 생성 오류: {e}")
            return "학습 노트 생성 실패"

    def add_learning_data(self, learning_data: Dict):
        """분석 결과를 AI 학습 데이터로 추가"""
        from log_system.log_adapter import log_event
        try:
            # 거래소 정보 추가
            learning_data['exchange'] = self.exchange
            learning_data['api_limits'] = self.api_limits

            # 기존 학습 데이터에 추가
            self.learning_history.append(learning_data)

            # 즉시 저장 (UI/파일 조회 일관성 확보)
            self._save_learning_data()
            msg = f"🤖 {self.exchange.upper()} AI 학습 데이터 저장 (총 {len(self.learning_history)}개)"
            self.logger.info(msg)
            log_event('ai_learning', msg, exchange=self.exchange, level='INFO')

            # 글로벌 집계 파일에도 동시 기록(레거시/대시보드 호환)
            try:
                self._append_to_global_aggregator(learning_data)
            except Exception as agg_e:
                self.logger.debug(f"글로벌 학습 집계 기록 스킵/오류: {agg_e}")
                log_event('ai_learning', f"글로벌 학습 집계 기록 오류: {agg_e}", exchange=self.exchange, level='WARNING')

            # 로그 출력
            symbol = learning_data.get('symbol', 'N/A')
            signal = learning_data.get('signal', 'N/A')
            confidence = learning_data.get('confidence', 0)
            msg2 = f"📊 {self.exchange.upper()} 학습 데이터 추가: {symbol} - {signal} (신뢰도: {confidence:.2f})"
            self.logger.info(msg2)
            log_event('ai_learning', msg2, exchange=self.exchange, level='INFO')

            emit_kpi_event(
                event_type='learning_data_recorded',
                category='learning',
                asset_class='crypto',
                status='success',
                source='noahai_client_learning',
                metric_value=float(confidence) if confidence is not None else None,
                metadata={
                    'exchange': self.exchange,
                    'symbol': symbol,
                    'signal': signal,
                    'history_size': len(self.learning_history),
                },
            )

            return True  # 성공적으로 추가됨
        except Exception as e:
            self.logger.error(f"{self.exchange.upper()} AI 학습 데이터 추가 오류: {e}")
            log_event('ai_learning', f"{self.exchange.upper()} AI 학습 데이터 추가 오류: {e}", exchange=self.exchange, level='ERROR')
            emit_kpi_event(
                event_type='learning_data_recorded',
                category='learning',
                asset_class='crypto',
                status='failed',
                source='noahai_client_learning',
                metadata={
                    'exchange': self.exchange,
                    'reason': str(e),
                },
            )
            return False  # 추가 실패

    def get_recent_learning_data(self, hours: int = 24) -> List[Dict]:
        """최근 학습 데이터 조회"""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            recent_data = [
                data for data in self.learning_history
                if self._ensure_aware_timestamp(data.get('timestamp')) >= cutoff_time
            ]
            return recent_data
        except Exception as e:
            self.logger.error(f"{self.exchange.upper()} 최근 학습 데이터 조회 오류: {e}")
            return []

    def get_exchange_specific_insights(self) -> Dict:
        """거래소별 특화 인사이트"""
        from log_system.log_adapter import log_event
        try:
            if not self.learning_history:
                return {}

            insights = {
                'exchange': self.exchange,
                'total_learning_entries': len(self.learning_history),
                'api_limits': self.api_limits,
                'recent_performance': {},
                'market_adaptation_patterns': {},
                'spot_trading_metrics': {} if self.exchange != 'binance' else None
            }

            # 최근 성능 분석
            recent_data = self.get_recent_learning_data(hours=24)
            if recent_data:
                insights['recent_performance'] = {
                    'entries_last_24h': len(recent_data),
                    'avg_market_score': sum(d.get('market_score', 0) for d in recent_data) / len(recent_data),
                    'avg_selection_count': sum(d.get('selected_coins_count', 0) for d in recent_data) / len(recent_data)
                }

                msg_path = f"💾 {self.exchange.upper()} 학습 데이터 저장 경로: {self.db_path}"
                msg_count = f"💾 저장할 데이터 개수: {len(self.learning_history)}개"
                self.logger.info(msg_path)
                self.logger.info(msg_count)
                log_event('ai_learning', msg_path, exchange=self.exchange, level='INFO')
                log_event('ai_learning', msg_count, exchange=self.exchange, level='INFO')

                spot_metrics = [d.get('spot_trading_metrics', {}) for d in recent_data if d.get('spot_trading_metrics')]
                if spot_metrics and self.exchange != 'binance':
                    insights['spot_trading_metrics'] = {
                        'avg_tp_sl_success_rate': sum(m.get('tp_sl_success_rate', 0) for m in spot_metrics) / len(spot_metrics),
                        'avg_fee_efficiency': sum(m.get('fee_efficiency', 0) for m in spot_metrics) / len(spot_metrics)
                    }

                msg_done = f"✅ {self.exchange.upper()} 학습 데이터 저장 완료"
                self.logger.info(msg_done)
                log_event('ai_learning', msg_done, exchange=self.exchange, level='INFO')

            return insights
        except Exception as e:
            err_msg = f"{self.exchange.upper()} 특화 인사이트 생성 오류: {e}"
            self.logger.error(err_msg)
            log_event('ai_learning', err_msg, exchange=self.exchange, level='ERROR')
            return {}

    def should_apply_api_delay(self) -> bool:
        """API 딜레이 적용 여부 확인"""
        now = datetime.now(timezone.utc)
        with self._api_rate_lock:
            self._api_request_times.append(now)
            cutoff = now - timedelta(minutes=1)
            while self._api_request_times and self._api_request_times[0] < cutoff:
                self._api_request_times.popleft()

            requests_per_minute = len(self._api_request_times)
            max_requests = max(1, int(self.api_limits.get('requests_per_minute', 60)))

        # 80% 이상 사용 시 딜레이 적용
        return requests_per_minute >= (max_requests * 0.8)

    def get_analysis_delay(self) -> float:
        """분석 딜레이 시간 반환 (초)"""
        return self.api_limits['analysis_delay']

    def get_max_coins_for_analysis(self) -> int:
        """분석 가능한 최대 코인 수 반환"""
        return self.api_limits['max_coins_per_analysis']

    # ---- 내부: 글로벌 집계 파일 관리 ----
    def _append_to_global_aggregator(self, learning_data: Dict) -> None:
        """글로벌 단일 파일(ai_learning_data.json)에 엔트리 추가(호환성용).
        - timestamp를 ISO 문자열로 강제 저장
        - 과도한 파일 성장을 방지하기 위해 최대 5000개로 제한(앞쪽 삭제)
        """
        try:
            # 글로벌 파일은 거래소별 파일과 동일한 디렉토리에 생성하여 경로 불일치 방지
            base_dir = os.path.dirname(self.db_path)
            agg_path = os.path.join(base_dir, 'ai_learning_data.json')
            # 안전 변환: timestamp를 문자열(ISO)로 정규화
            entry = dict(learning_data)
            ts = entry.get('timestamp')
            try:
                if ts is None:
                    ts_str = datetime.now(timezone.utc).isoformat()
                elif isinstance(ts, str):
                    ts_str = ts
                else:
                    # datetime 또는 유사 객체이면 isoformat 시도, 실패 시 str 폴백
                    try:
                        ts_str = ts.isoformat()  # type: ignore[attr-defined]
                    except Exception:
                        ts_str = str(ts)
                entry['timestamp'] = ts_str
            except Exception:
                # 최후 폴백
                entry['timestamp'] = str(ts or datetime.now(timezone.utc).isoformat())
            data: List[Dict] = []
            if os.path.exists(agg_path):
                loaded = self._read_json_list_safe(agg_path)
                if isinstance(loaded, list):
                    data = loaded
            data.append(entry)
            # 용량 관리: 최근 5000개만 유지
            if len(data) > 5000:
                data = data[-5000:]
            self._atomic_write_json(agg_path, data)
        except Exception:
            # 집계 실패는 무시(주 파일에는 이미 저장됨)
            pass

    def _atomic_write_json(self, path: str, payload: List[Dict]) -> None:
        """JSON 파일을 임시 파일에 쓴 뒤 원자적으로 교체합니다."""
        lock = _get_file_lock(path)
        with lock:
            tmp_path = f"{path}.tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)

    def _read_json_list_safe(self, path: str) -> List[Dict]:
        """JSON 리스트 파일을 안전하게 읽고, 깨진 경우 복구합니다."""
        lock = _get_file_lock(path)
        with lock:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                return loaded if isinstance(loaded, list) else []
            except json.JSONDecodeError as e:
                self.logger.warning(f"{self.exchange.upper()} 학습 데이터 JSON 손상 감지: {e}")
                try:
                    backup_path = f"{path}.corrupt.{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
                    os.replace(path, backup_path)
                    self.logger.warning(f"손상 파일 백업 완료: {backup_path}")
                except Exception:
                    pass
                return []

    @staticmethod
    def _ensure_aware_timestamp(value: Any) -> datetime:
        """timestamp 값을 timezone-aware UTC datetime으로 정규화한다."""
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
                return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
            except Exception:
                return datetime.now(timezone.utc)
        return datetime.now(timezone.utc)


def get_exchange_learning_manager(exchange: str) -> ExchangeLearningManager:
    """거래소별 학습 매니저 팩토리 함수"""
    return ExchangeLearningManager(exchange)
