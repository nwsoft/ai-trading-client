#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API 신호 교환 관리 모듈
거래소별 API 신호 수신 및 학습 데이터 생성
"""

import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
# PyQt5 의존성 제거 - CustomTkinter 호환
# from PyQt5.QtCore import QTimer, QObject, pyqtSignal
import threading
import time
from .exchange_manager import ExchangeManager
from .symbol_validator import symbol_validator


class APISignalManager:
    """API 신호 교환 관리 클래스 (PyQt5 의존성 제거)"""
    
    # 시그널 정의 (PyQt5 의존성 제거)
    # signal_received = pyqtSignal(dict)  # 신호 수신 시그널
    # learning_data_updated = pyqtSignal(dict)  # 학습 데이터 업데이트 시그널
    # exchange_data_updated = pyqtSignal(str, dict)  # 거래소별 데이터 업데이트 시그널
    
    def __init__(self, exchange_manager: ExchangeManager, settings: Dict[str, Any]):
        # super().__init__()  # PyQt5 QObject 상속 제거
        self.exchange_manager = exchange_manager
        self.settings = settings
        self.logger = logging.getLogger(__name__)
        
        # 콜백 함수들 (PyQt5 시그널 대신)
        self.on_signal_received_callback = None
        self.on_learning_data_updated_callback = None
        
        # 신호 수집 설정
        self.signal_interval = 60  # 1분 간격
        self.max_signals_per_exchange = 100  # 거래소별 최대 신호 수
        self.learning_data = {}
        
        # 타이머 설정 (PyQt5 QTimer 대신 threading 사용)
        self.signal_timer = None
        self.timer_thread = None
        self.running = False
        
        # 신호 저장소
        self.signal_storage = {
            'binance': [],
            'upbit': [],
            'bithumb': []
        }
        
        # 학습 데이터 저장소
        self.learning_storage = {
            'market_data': [],
            'price_movements': [],
            'volume_patterns': [],
            'correlation_data': []
        }
        
        self.logger.info("API 신호 관리자 초기화 완료")

    # ------------------------------------------------------------------
    # 내부 유틸리티
    # ------------------------------------------------------------------
    def _normalize_exchange(self, exchange_name: Optional[str]) -> str:
        return str(exchange_name or '').strip().lower()

    def _get_enabled_exchanges(self) -> set:
        enabled_set = set()
        try:
            raw = self.settings.get('enabled_exchanges', []) if isinstance(self.settings, dict) else []
            for item in raw or []:
                normalized = self._normalize_exchange(item)
                if normalized:
                    enabled_set.add(normalized)
        except Exception:
            enabled_set = set()

        if not enabled_set:
            fallback = self._normalize_exchange(self.settings.get('selected_exchange', 'binance'))
            if fallback:
                enabled_set.add(fallback)
        return enabled_set

    def _is_exchange_enabled(self, exchange_name: str) -> bool:
        return self._normalize_exchange(exchange_name) in self._get_enabled_exchanges()
    
    def start_signal_collection(self):
        """신호 수집 시작 (threading 방식)"""
        try:
            if not self.running:
                self.running = True
                self.timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
                self.timer_thread.start()
                self.logger.info(f"API 신호 수집 시작 (간격: {self.signal_interval}초)")
                
                # 초기 신호 수집
                self._collect_signals()
            
        except Exception as e:
            self.logger.error(f"신호 수집 시작 오류: {e}")
    
    def stop_signal_collection(self):
        """신호 수집 중지 (threading 방식)"""
        try:
            self.running = False
            if self.timer_thread:
                self.timer_thread.join(timeout=1)
            self.logger.info("API 신호 수집 중지")
        except Exception as e:
            self.logger.error(f"신호 수집 중지 오류: {e}")
    
    def _timer_loop(self):
        """타이머 루프 (threading 방식)"""
        while self.running:
            try:
                self._collect_signals()
                time.sleep(self.signal_interval)
            except Exception as e:
                self.logger.error(f"❌ 타이머 루프 오류: {e}")
                time.sleep(1)
    
    def _has_valid_api_keys(self, exchange_name: str) -> bool:
        """API 키 유효성 검사"""
        try:
            normalized = self._normalize_exchange(exchange_name)
            if normalized == 'binance':
                api_key = self.settings.get('binance_api_key', '')
                secret_key = self.settings.get('binance_secret_key', '')
                return bool(api_key and secret_key)
            elif normalized == 'upbit':
                api_key = self.settings.get('upbit_api_key', '')
                secret_key = self.settings.get('upbit_secret_key', '')
                return bool(api_key and secret_key)
            elif normalized == 'bithumb':
                api_key = self.settings.get('bithumb_api_key', '')
                secret_key = self.settings.get('bithumb_secret_key', '')
                return bool(api_key and secret_key)
            return False
        except Exception as e:
            self.logger.error(f"API 키 검증 오류: {e}")
            return False
    
    def _collect_signals(self):
        """신호 수집 실행"""
        try:
            self.logger.debug("API 신호 수집 실행")
            
            enabled = self._get_enabled_exchanges()
            # 각 거래소별로 신호 수집
            for exchange_name in ['binance', 'upbit', 'bithumb']:
                normalized = self._normalize_exchange(exchange_name)
                if enabled and normalized not in enabled:
                    continue
                if self._has_valid_api_keys(normalized):
                    self._collect_exchange_signals(normalized)

            # 학습 데이터 생성
            self._generate_learning_data()
            
        except Exception as e:
            self.logger.error(f"신호 수집 오류: {e}")
    
    def _collect_exchange_signals(self, exchange_name: str):
        """특정 거래소 신호 수집"""
        try:
            if not self._is_exchange_enabled(exchange_name):
                return

            client = self.exchange_manager.get_exchange_client(exchange_name)
            if not client:
                return

            is_connected = getattr(client, 'is_connected', False)
            if not is_connected and hasattr(client, 'connect'):
                is_connected = client.connect()

            if not is_connected:
                return

            # 기본 시장 데이터 수집
            market_data = self._get_market_data(client, exchange_name)
            
            # 가격 데이터 수집
            price_data = self._get_price_data(client, exchange_name)
            
            # 거래량 데이터 수집
            volume_data = self._get_volume_data(client, exchange_name)
            
            # 신호 조합
            signal = {
                'exchange': exchange_name,
                'timestamp': datetime.now().isoformat(),
                'market_data': market_data,
                'price_data': price_data,
                'volume_data': volume_data,
                'signal_id': f"{exchange_name}_{int(time.time())}"
            }
            
            # 신호 저장
            self._store_signal(exchange_name, signal)
            
            # 시그널 발생 (PyQt5 의존성 제거 - 콜백 사용)
            self.logger.info(f"신호 수신: {exchange_name} - {signal.get('symbol', 'Unknown')}")
            if self.on_signal_received_callback:
                self.on_signal_received_callback(signal)
            # self.signal_received.emit(signal)  # PyQt5 의존성 제거
            # self.exchange_data_updated.emit(exchange_name, signal)  # PyQt5 의존성 제거
            
            self.logger.debug(f"{exchange_name} 신호 수집 완료")
            
        except Exception as e:
            self.logger.error(f"{exchange_name} 신호 수집 오류: {e}")
    
    def _get_market_data(self, client, exchange_name: str) -> Dict[str, Any]:
        """시장 데이터 수집"""
        try:
            # 주요 코인 목록 (거래소별로 다를 수 있음)
            symbols = self._get_exchange_symbols(exchange_name)
            market_data = {}
            
            for symbol in symbols[:5]:  # 상위 5개만
                try:
                    price = client.get_current_price(symbol)
                    if price > 0:
                        market_data[symbol] = {
                            'price': price,
                            'timestamp': datetime.now().isoformat()
                        }
                except Exception as e:
                    self.logger.debug(f"{symbol} 가격 조회 실패: {e}")
                    continue
            
            return market_data
            
        except Exception as e:
            self.logger.error(f"시장 데이터 수집 오류: {e}")
            return {}
    
    def _get_price_data(self, client, exchange_name: str) -> Dict[str, Any]:
        """가격 데이터 수집"""
        try:
            # 잔고 정보에서 가격 데이터 추출
            balance_info = self.exchange_manager.get_exchange_balance(exchange_name)
            
            price_data = {
                'exchange': exchange_name,
                'timestamp': datetime.now().isoformat(),
                'balance_info': balance_info.get('balance', {}),
                'account_info': balance_info.get('account_info', {})
            }
            
            return price_data
            
        except Exception as e:
            self.logger.error(f"가격 데이터 수집 오류: {e}")
            return {}
    
    def _get_volume_data(self, client, exchange_name: str) -> Dict[str, Any]:
        """거래량 데이터 수집"""
        try:
            # 안전 심볼 사용
            safe_symbol = symbol_validator.get_safe_symbol(exchange_name)
            trade_history = client.get_trade_history(symbol=safe_symbol, limit=10)
            
            volume_data = {
                'exchange': exchange_name,
                'timestamp': datetime.now().isoformat(),
                'recent_trades': len(trade_history),
                'trade_volume': sum(trade.get('amount', 0) for trade in trade_history)
            }
            
            return volume_data
            
        except Exception as e:
            self.logger.error(f"거래량 데이터 수집 오류: {e}")
            return {}
    
    def _get_exchange_symbols(self, exchange_name: str) -> List[str]:
        """거래소별 심볼 목록 반환"""
        if exchange_name == 'binance':
            return ['BTCUSDT', 'ETHUSDT', 'ADAUSDT', 'DOTUSDT', 'LINKUSDT']
        elif exchange_name == 'upbit':
            return ['KRW-BTC', 'KRW-ETH', 'KRW-ADA', 'KRW-DOT', 'KRW-LINK']
        elif exchange_name == 'bithumb':
            return ['BTC/KRW', 'ETH/KRW', 'ADA/KRW', 'DOT/KRW', 'LINK/KRW']
        else:
            return []
    
    def _store_signal(self, exchange_name: str, signal: Dict[str, Any]):
        """신호 저장"""
        try:
            # 신호 저장소에 추가
            self.signal_storage[exchange_name].append(signal)
            
            # 최대 개수 제한
            if len(self.signal_storage[exchange_name]) > self.max_signals_per_exchange:
                self.signal_storage[exchange_name] = self.signal_storage[exchange_name][-self.max_signals_per_exchange:]
            
            self.logger.debug(f"{exchange_name} 신호 저장 완료 (총 {len(self.signal_storage[exchange_name])}개)")
            
        except Exception as e:
            self.logger.error(f"신호 저장 오류: {e}")
    
    def _generate_learning_data(self):
        """학습 데이터 생성"""
        try:
            # 모든 거래소 신호 분석
            all_signals = []
            for exchange_signals in self.signal_storage.values():
                all_signals.extend(exchange_signals[-10:])  # 최근 10개씩
            
            if len(all_signals) < 2:
                return
            
            # 가격 상관관계 분석
            correlation_data = self._analyze_price_correlation(all_signals)
            
            # 시장 패턴 분석
            market_patterns = self._analyze_market_patterns(all_signals)
            
            # 학습 데이터 조합
            learning_data = {
                'timestamp': datetime.now().isoformat(),
                'correlation_data': correlation_data,
                'market_patterns': market_patterns,
                'signal_count': len(all_signals),
                'exchanges': list(self.signal_storage.keys())
            }
            
            # 학습 데이터 저장
            self.learning_storage['market_data'].append(learning_data)
            
            # 최대 개수 제한
            if len(self.learning_storage['market_data']) > 1000:
                self.learning_storage['market_data'] = self.learning_storage['market_data'][-1000:]
            
            # 시그널 발생 (PyQt5 의존성 제거 - 콜백 사용)
            self.logger.info(f"학습 데이터 업데이트: {len(all_signals)}개 신호")
            if self.on_learning_data_updated_callback:
                self.on_learning_data_updated_callback(learning_data)
            # self.learning_data_updated.emit(learning_data)  # PyQt5 의존성 제거
            
            self.logger.info(f"학습 데이터 생성 완료 (신호 수: {len(all_signals)})")
            
        except Exception as e:
            self.logger.error(f"학습 데이터 생성 오류: {e}")
    
    def _analyze_price_correlation(self, signals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """가격 상관관계 분석"""
        try:
            # 간단한 상관관계 분석 (실제로는 더 복잡한 분석 필요)
            price_changes = {}
            
            for signal in signals:
                exchange = signal.get('exchange')
                market_data = signal.get('market_data', {})
                
                for symbol, data in market_data.items():
                    if symbol not in price_changes:
                        price_changes[symbol] = []
                    price_changes[symbol].append(data.get('price', 0))
            
            # 상관관계 계산 (간단한 버전)
            correlation_data = {}
            symbols = list(price_changes.keys())
            
            for i, symbol1 in enumerate(symbols):
                for symbol2 in symbols[i+1:]:
                    if len(price_changes[symbol1]) > 1 and len(price_changes[symbol2]) > 1:
                        # 간단한 상관관계 계산
                        correlation = self._calculate_correlation(
                            price_changes[symbol1], 
                            price_changes[symbol2]
                        )
                        correlation_data[f"{symbol1}-{symbol2}"] = correlation
            
            return correlation_data
            
        except Exception as e:
            self.logger.error(f"가격 상관관계 분석 오류: {e}")
            return {}
    
    def _analyze_market_patterns(self, signals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """시장 패턴 분석"""
        try:
            # 간단한 패턴 분석
            patterns = {
                'total_signals': len(signals),
                'exchanges_active': len(set(s.get('exchange') for s in signals)),
                'time_range': {
                    'start': signals[0].get('timestamp') if signals else None,
                    'end': signals[-1].get('timestamp') if signals else None
                }
            }
            
            return patterns
            
        except Exception as e:
            self.logger.error(f"시장 패턴 분석 오류: {e}")
            return {}
    
    def _calculate_correlation(self, x: List[float], y: List[float]) -> float:
        """간단한 상관관계 계산"""
        try:
            if len(x) != len(y) or len(x) < 2:
                return 0.0
            
            # 피어슨 상관계수 계산 (간단한 버전)
            n = len(x)
            sum_x = sum(x)
            sum_y = sum(y)
            sum_xy = sum(x[i] * y[i] for i in range(n))
            sum_x2 = sum(xi * xi for xi in x)
            sum_y2 = sum(yi * yi for yi in y)
            
            numerator = n * sum_xy - sum_x * sum_y
            denominator = ((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y)) ** 0.5
            
            if denominator == 0:
                return 0.0
            
            return numerator / denominator
            
        except Exception as e:
            self.logger.error(f"상관관계 계산 오류: {e}")
            return 0.0
    
    def get_signal_statistics(self) -> Dict[str, Any]:
        """신호 통계 반환"""
        try:
            stats = {}
            for exchange_name, signals in self.signal_storage.items():
                stats[exchange_name] = {
                    'signal_count': len(signals),
                    'last_signal': signals[-1].get('timestamp') if signals else None,
                    'has_api_keys': self._has_valid_api_keys(exchange_name)
                }
            
            stats['total_signals'] = sum(len(signals) for signals in self.signal_storage.values())
            stats['learning_data_count'] = len(self.learning_storage['market_data'])
            
            return stats
            
        except Exception as e:
            self.logger.error(f"신호 통계 조회 오류: {e}")
            return {}
    
    def get_learning_data(self, limit: int = 100) -> List[Dict[str, Any]]:
        """학습 데이터 반환"""
        try:
            return self.learning_storage['market_data'][-limit:]
        except Exception as e:
            self.logger.error(f"학습 데이터 조회 오류: {e}")
            return []
    
    def clear_old_data(self, days: int = 7):
        """오래된 데이터 정리"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # 신호 데이터 정리
            for exchange_name in self.signal_storage:
                self.signal_storage[exchange_name] = [
                    signal for signal in self.signal_storage[exchange_name]
                    if datetime.fromisoformat(signal.get('timestamp', '')) > cutoff_date
                ]
            
            # 학습 데이터 정리
            self.learning_storage['market_data'] = [
                data for data in self.learning_storage['market_data']
                if datetime.fromisoformat(data.get('timestamp', '')) > cutoff_date
            ]
            
            self.logger.info(f"{days}일 이전 데이터 정리 완료")
            
        except Exception as e:
            self.logger.error(f"데이터 정리 오류: {e}")
