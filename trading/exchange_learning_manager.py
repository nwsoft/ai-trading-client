#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
계정·거래소별 학습 데이터 관리자.
v44는 learning.sqlite3와 검증된 압축 세그먼트를 사용한다.
ai_learning_data_<exchange>.json은 읽기 전용 이관 원본이다.
"""

import os
import json
import logging
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional
from dataclasses import dataclass, asdict
from uuid import uuid4
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

    def __init__(self, exchange: str = "binance", *, data_dir: Optional[str] = None):
        """
        거래소별 학습 매니저 초기화

        Args:
            exchange: "binance", "upbit", "bithumb"
        """
        self.exchange = exchange.lower()
        self.logger = logging.getLogger(f"{__name__}.{self.exchange}")

        # 거래소별 파일 경로 설정
        self.db_path = os.path.join(data_dir,f'ai_learning_data_{self.exchange}.json') if data_dir else self._get_exchange_learning_path()
        self._journal_path = f"{self.db_path}.journal.jsonl"
        self._pending_checkpoint_entries = 0
        self._last_checkpoint_monotonic = time.monotonic()
        self._history_lock = threading.RLock()

        # 학습 데이터 로드
        from trading.learning_storage import LearningStore, RecentHistory
        self._store = LearningStore(os.path.dirname(self.db_path))
        self.migration_error = None
        for legacy_path in (self.db_path,self._journal_path):
            try:
                self._store.import_legacy(legacy_path,self.exchange)
            except (OSError,ValueError) as exc:
                self.migration_error = type(exc).__name__
                self.logger.error('%s legacy learning migration incomplete: %s',self.exchange,self.migration_error)
        self.learning_history = RecentHistory(self._store, self.exchange, self._get_retention_limit())
        if self._store.count(self.exchange)>10000:
            from trading.learning_storage import schedule_archive
            schedule_archive(self._store)

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

            # Only the authenticated account path is authoritative; never guess another account.

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
            },
            "coinone": {
                "requests_per_minute": 300,
                "analysis_delay": 0.3,
                "max_coins_per_analysis": 30,
                "websocket_supported": False
            }
        }
        return limits.get(self.exchange, limits["binance"])

    def _load_learning_data(self) -> List[Dict]:
        """Compatibility reader; the runtime uses an indexed lazy view."""
        return self._store.recent(self.exchange,self._get_retention_limit())

    def _save_learning_data(self):
        """Compatibility checkpoint: each event is already durably committed."""
        return None

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
        archive_filename = f'ai_learning_data_{self.exchange}_archive_{today}.jsonl'
        return os.path.join(base_dir, archive_filename)

    def _rotate_to_archive(self):
        """Schedule bounded compression; never truncate a legacy source."""
        from trading.learning_storage import schedule_archive
        schedule_archive(self._store)

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

            entry = asdict(learning_data)
            with self._history_lock:
                self.learning_history.append(entry)
                self._persist_increment(entry)

            # 글로벌 집계 파일에도 동시 기록
            try:
                self._append_to_global_aggregator(entry)
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
            learning_data = dict(learning_data or {})
            from trading.event_contract import metadata, input_issues
            if input_issues('analysis', learning_data, self.exchange):
                self._store.append(self.exchange, learning_data)
                log_event('ai_learning', '학습 기록 기관·모드 충돌: 원본 별도 보존, 학습 제외', exchange=self.exchange, level='WARNING')
                return False
            learning_data.setdefault('exchange', self.exchange)
            validation = learning_data.get('validation') or {}
            learning_data.setdefault('execution_mode', validation.get('execution_mode', 'learning') if isinstance(validation, dict) else 'learning')
            learning_data.update(metadata('analysis',learning_data,exchange=self.exchange))
            learning_data['api_limits'] = self.api_limits
            learning_data.setdefault('_learning_event_id', f"learning_{uuid4().hex}")

            # 기존 학습 데이터에 추가
            with self._history_lock:
                self.learning_history.append(learning_data)

                # Each event commits to the indexed store; no full JSON rewrite.
                self._persist_increment(learning_data)
                history_size = len(self.learning_history)
            msg = f"🤖 {self.exchange.upper()} AI 학습 데이터 저장 (총 {history_size}개)"
            log_event('ai_learning', msg, exchange=self.exchange, level='DEBUG')

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
            log_event('ai_learning', msg2, exchange=self.exchange, level='DEBUG')

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
                    'history_size': history_size,
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
                log_event('ai_learning', f"학습 인사이트 조회: {len(recent_data)}개", exchange=self.exchange, level='DEBUG')

                spot_metrics = [d.get('spot_trading_metrics', {}) for d in recent_data if d.get('spot_trading_metrics')]
                if spot_metrics and self.exchange != 'binance':
                    insights['spot_trading_metrics'] = {
                        'avg_tp_sl_success_rate': sum(m.get('tp_sl_success_rate', 0) for m in spot_metrics) / len(spot_metrics),
                        'avg_fee_efficiency': sum(m.get('fee_efficiency', 0) for m in spot_metrics) / len(spot_metrics)
                    }

                msg_done = f"✅ {self.exchange.upper()} 학습 데이터 저장 완료"
                log_event('ai_learning', msg_done, exchange=self.exchange, level='DEBUG')

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
        """The account-wide indexed view replaces duplicate global JSON writes."""
        return None

    def _persist_increment(self, entry: Dict[str, Any]) -> None:
        entry.setdefault("_learning_event_id", f"learning_{uuid4().hex}")
        from trading.event_contract import metadata
        kind = 'strategy_changed' if entry.get('learning_type')=='criteria_adjustment' else 'analysis'
        for key,value in metadata(kind,{**entry,'event_time':entry.get('timestamp')},exchange=self.exchange).items():
            entry.setdefault(key,value)
        self._store.append(self.exchange, self._storage_entry(entry))
        self._pending_checkpoint_entries += 1
        if self._pending_checkpoint_entries >= 1000:
            self._pending_checkpoint_entries = 0
            self._rotate_to_archive()

    def _read_learning_journal(self) -> List[Dict]:
        rows: List[Dict] = []
        if not os.path.exists(self._journal_path):
            return rows
        lock = _get_file_lock(self._journal_path)
        with lock:
            try:
                with open(self._journal_path, 'r', encoding='utf-8') as handle:
                    for line in handle:
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(row, dict):
                            rows.append(row)
            except OSError:
                return []
        return rows

    @staticmethod
    def _storage_entry(value: Dict[str, Any]) -> Dict[str, Any]:
        """Return a JSON-safe learning record without changing its meaning."""
        def convert(item: Any) -> Any:
            if isinstance(item, datetime):
                return item.isoformat()
            if isinstance(item, dict):
                return {str(key): convert(child) for key, child in item.items()}
            if isinstance(item, (list, tuple)):
                return [convert(child) for child in item]
            if isinstance(item, (str, int, float, bool)) or item is None:
                return item
            return str(item)
        return convert(dict(value))

    @staticmethod
    def _append_jsonl(path: str, entry: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        lock = _get_file_lock(path)
        with lock, open(path, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + '\n')
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _truncate_file(path: str) -> None:
        if not os.path.exists(path):
            return
        lock = _get_file_lock(path)
        with lock, open(path, 'w', encoding='utf-8'):
            pass

    def _checkpoint_global_aggregator(self) -> None:
        """No duplicate global snapshot is written in v44."""
        return None

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
        """Read-only compatibility import; malformed source files remain intact."""
        from trading.learning_storage import iter_legacy
        from pathlib import Path
        return list(iter_legacy(Path(path)))

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


_MANAGERS: Dict[tuple, ExchangeLearningManager] = {}
_MANAGERS_LOCK = threading.RLock()
_MANAGER_INIT_LOCKS = {}


def get_exchange_learning_manager(exchange: str) -> ExchangeLearningManager:
    """거래소별 학습 매니저 팩토리 함수"""
    from path_utils import get_app_data_dir
    key = (os.path.realpath(get_app_data_dir()), str(exchange).lower())
    with _MANAGERS_LOCK:
        lock = _MANAGER_INIT_LOCKS.setdefault(key,threading.RLock())
    with lock:
        if key not in _MANAGERS:
            _MANAGERS[key] = ExchangeLearningManager(exchange,data_dir=key[0])
        return _MANAGERS[key]
