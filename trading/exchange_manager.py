#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
거래소 관리 모듈
main.py 수정 최소화하면서 거래소별 기능 제공
"""

import logging
import re
from typing import Dict, Any, Optional, List, Any as _Any
from datetime import datetime, timedelta
from .exchanges.exchange_factory import ExchangeFactory
from .exchanges.interfaces.exchange_interface import ExchangeInterface
from .exchanges.base_exchange import BaseExchange
from .unified_trading_manager import UnifiedTradingManager


class ExchangeManager:
    """거래소 관리 클래스"""
    
    def __init__(self, settings: Dict[str, Any], binance_client=None, unified_manager: Optional[UnifiedTradingManager] = None):
        self.settings = settings
        self.logger = logging.getLogger(__name__)
        
        # 🔥 로그 시스템 통일을 위한 헬퍼 메서드
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO', exchange=None: log_event(category, msg, exchange=exchange or 'global', level=level)
        self.current_exchange = None
        self.exchange_clients = {}  # 거래소별 클라이언트 캐시
        # 잘못된(Invalid) API 키로 판정된 거래소 (세션 동안 추가 호출 억제)
        self.invalid_api_keys = set()  # {exchange_name}
        self.last_balance_update = {}
        self.balance_cache = {}
        self.cache_duration = 30  # 30초 캐시 (거래 후 빠른 갱신을 위해 단축)
        
        # 🔥 바이낸스 클라이언트 주입 (기존 python-binance 방식)
        self.binance_client = binance_client
        
        # 통합 거래 매니저 초기화 (CCXT 거래소들용) - 재사용 가능
        self.unified_manager = unified_manager if unified_manager else UnifiedTradingManager(settings)
        
        # 현재 선택된 거래소 초기화
        self._initialize_current_exchange()

    # ------------------------------------------------------------------
    # 내부 유틸리티
    # ------------------------------------------------------------------
    def _normalize_exchange_name(self, exchange_name: Optional[str]) -> str:
        return str(exchange_name or '').strip().lower()

    def _is_auth_error_message(self, message: str) -> bool:
        """인증/권한 관련 오류 문자열을 방어적으로 판별"""
        try:
            msg = str(message or '').lower()
            auth_tokens = [
                'invalid api',
                'invalid access',
                'invalid_access_key',
                'apikey',
                'api key',
                'access key',
                'signature',
                'permission',
                'auth',
                'not authorized',
            ]
            return any(token in msg for token in auth_tokens)
        except Exception:
            return False

    def _get_enabled_exchange_set(self) -> set:
        enabled_set = set()
        try:
            raw_enabled = self.settings.get('enabled_exchanges', []) if isinstance(self.settings, dict) else []
            for item in raw_enabled or []:
                normalized = self._normalize_exchange_name(item)
                if normalized:
                    enabled_set.add(normalized)
        except Exception:
            enabled_set = set()

        if not enabled_set:
            fallback = self._normalize_exchange_name(self.settings.get('selected_exchange', 'binance'))
            if fallback:
                enabled_set.add(fallback)
        return enabled_set

    def _is_exchange_enabled(self, exchange_name: Optional[str]) -> bool:
        normalized = self._normalize_exchange_name(exchange_name)
        return normalized in self._get_enabled_exchange_set()

    def update_settings(self, new_settings: Dict[str, Any], unified_manager: Optional[UnifiedTradingManager] = None):
        """설정 변경 반영 및 현재 클라이언트 재구성"""
        try:
            self.settings = new_settings
            if unified_manager:
                self.unified_manager = unified_manager
            # 캐시 초기화
            self.clear_cache()
            # 현재 거래소 클라이언트 재생성
            self._initialize_current_exchange()
            self.log_event('system', "ExchangeManager 설정 업데이트 및 재초기화 완료")
        except Exception as e:
            self.log_event('system', f"ExchangeManager 설정 업데이트 실패: {e}", level='ERROR')
    
    def get_binance_client(self):
        """바이낸스 클라이언트 반환"""
        return self.binance_client
        
    def get_exchange_client(self, exchange_name: str):
        """거래소별 클라이언트를 안전하게 반환"""
        return self._get_or_create_exchange_client(exchange_name)

    def _initialize_current_exchange(self):
        """현재 선택된 거래소 초기화"""
        try:
            selected_exchange = self.settings.get('selected_exchange', 'binance')
            self.log_event('system', f"선택된 거래소: {selected_exchange}")
            
            # 기존 바이낸스 클라이언트가 있다면 유지 (하위 호환성)
            if hasattr(self, 'binance_client') and self.binance_client:
                self.exchange_clients['binance'] = self.binance_client
                self.log_event('system', "기존 바이낸스 클라이언트 유지")
            
            # 현재 선택된 거래소 클라이언트 생성
            self.current_exchange = self._get_or_create_exchange_client(selected_exchange)
            
        except Exception as e:
            self.logger.error(f"거래소 초기화 실패: {e}")
            self.current_exchange = None
    
    def _get_or_create_exchange_client(self, exchange_name: str) -> Optional[_Any]:
        """거래소 클라이언트 가져오기 또는 생성"""
        try:
            normalized_name = self._normalize_exchange_name(exchange_name)

            if not normalized_name:
                return None

            if not self._is_exchange_enabled(normalized_name):
                self.logger.debug(f"{exchange_name} 클라이언트 생략 (enabled_exchanges 비활성)")
                return None

            # 이전에 잘못된 키로 판정되었으면 즉시 None (로그 소음 억제)
            if normalized_name in self.invalid_api_keys:
                self.logger.debug(f"{exchange_name} 클라이언트 생략 (이전에 Invalid API Key 판정됨)")
                return None

            # 캐시된 클라이언트가 있으면 반환
            if normalized_name in self.exchange_clients:
                return self.exchange_clients[normalized_name]

            # 바이낸스는 기존 주입된 클라이언트가 있으면 우선 사용 (하위 호환)
            if normalized_name == 'binance' and getattr(self, 'binance_client', None):
                self.exchange_clients['binance'] = self.binance_client  # 캐시에 고정
                return self.binance_client

            # API 키 없으면 기본적으로 생성 생략.
            # 단, 업비트/빗썸은 공개모드 시세/분석이 가능하므로 생성 허용.
            if not self._has_valid_api_keys(normalized_name):
                if normalized_name not in ('upbit', 'bithumb'):
                    self.logger.debug(f"{exchange_name} API 키가 없어 클라이언트를 생성하지 않습니다 (요청시 None 반환)")
                    return None
                self.logger.info(f"{exchange_name} 공개모드 클라이언트 생성 시도 (API 키 없음)")

            # 새 클라이언트 생성
            trading_type = 'futures' if normalized_name in ['binance', 'bybit', 'okx', 'bitget'] else 'spot'
            client = ExchangeFactory.create_exchange(normalized_name, trading_type, self.settings)
            if client:
                try:
                    # 일부 어댑터는 즉시 connect 필요
                    if hasattr(client, 'connect'):
                        connected = client.connect()
                        if not connected:
                            self.logger.warning(f"{exchange_name} 초기 연결 실패 (지연 재시도 예정)")
                    self.exchange_clients[normalized_name] = client
                    self.logger.info(f"{exchange_name} 클라이언트 생성 완료")
                    return client
                except Exception as ce:
                    msg = str(ce).lower()
                    if 'invalid' in msg and ('api' in msg or 'access key' in msg or 'apikey' in msg):
                        if normalized_name not in self.invalid_api_keys:
                            self.logger.warning(f"{exchange_name} API 키가 유효하지 않음 - 추가 호출 억제")
                        self.invalid_api_keys.add(normalized_name)
                        return None
                    self.logger.error(f"{exchange_name} 클라이언트 연결/생성 중 오류: {ce}")
                    return None
            else:
                self.logger.error(f"{exchange_name} 클라이언트 생성 실패")
                return None
                
        except Exception as e:
            self.logger.error(f"{exchange_name} 클라이언트 생성 오류: {e}")
            import traceback
            self.logger.error(f"상세 오류: {traceback.format_exc()}")
            return None
    
    def get_current_exchange_client(self) -> Optional[_Any]:
        """현재 선택된 거래소 클라이언트 반환"""
        return self.current_exchange
    
    def switch_exchange(self, exchange_name: str) -> bool:
        """거래소 전환"""
        try:
            self.logger.info(f"거래소 전환 시도: {exchange_name}")
            
            # 설정 업데이트
            self.settings['selected_exchange'] = exchange_name
            
            # 새로운 거래소 클라이언트 생성
            new_client = self._get_or_create_exchange_client(exchange_name)
            if new_client:
                self.current_exchange = new_client
                self.logger.info(f"거래소 전환 완료: {exchange_name}")
                return True
            else:
                self.logger.error(f"거래소 전환 실패: {exchange_name}")
                return False
                
        except Exception as e:
            self.logger.error(f"거래소 전환 오류: {e}")
            return False
    
    def get_exchange_balance(self, exchange_name: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
        """거래소 잔고 조회 (캐시 적용)"""
        normalized_name = None
        try:
            if exchange_name is None:
                exchange_name = self.settings.get('selected_exchange', 'binance')

            normalized_name = self._normalize_exchange_name(exchange_name)

            if not self._is_exchange_enabled(normalized_name):
                return {
                    'exchange': normalized_name,
                    'status': 'disabled',
                    'message': '해당 거래소는 현재 비활성화되어 잔고 조회를 수행하지 않습니다.'
                }

            # Invalid API 키로 이미 판정된 경우 즉시 상태 반환 (로그 소음 차단)
            if normalized_name in self.invalid_api_keys:
                return {
                    'exchange': normalized_name,
                    'status': 'invalid_api_keys',
                    'message': 'API 키가 유효하지 않아 잔고 조회 생략'
                }

            # 캐시 확인 (force_refresh가 True면 캐시 무시)
            cache_key = f"{normalized_name}_balance"
            now = datetime.now()

            if (not force_refresh and 
                cache_key in self.balance_cache and 
                cache_key in self.last_balance_update and
                (now - self.last_balance_update[cache_key]).seconds < self.cache_duration):
                self.logger.debug(f"{exchange_name} 잔고 캐시 사용")
                return self.balance_cache[cache_key]

            # 🔥 바이낸스는 기존 방식 사용 (CCXT 어댑터 사용 안함)
            if normalized_name == 'binance':
                return self._get_binance_balance(force_refresh)
            else:
                # 다른 거래소는 CCXT 사용
                ex_name: str = normalized_name if isinstance(normalized_name, str) else self._normalize_exchange_name(self.settings.get('selected_exchange', 'binance'))
                return self._get_ccxt_balance(ex_name, force_refresh)

        except Exception as e:
            msg = str(e).lower()
            # normalized_name이 바인딩되지 않았을 수 있으므로 안전하게 fallback
            safe_normalized = normalized_name if normalized_name is not None else self._normalize_exchange_name(exchange_name if exchange_name is not None else 'binance')
            if 'invalid' in msg and ('api' in msg or 'access key' in msg or 'apikey' in msg):
                if safe_normalized not in self.invalid_api_keys:
                    self.logger.warning(f"{exchange_name} 잔고 조회 - 잘못된 API 키 감지, 이후 호출 억제")
                self.invalid_api_keys.add(safe_normalized)
                return {
                    'exchange': safe_normalized,
                    'status': 'invalid_api_keys',
                    'message': 'API 키가 유효하지 않아 잔고 조회 중단'
                }
            self.logger.error(f"{exchange_name} 잔고 조회 오류: {e}")
            return {'error': str(e), 'exchange': safe_normalized, 'status': 'error'}
    
    def _get_binance_balance(self, force_refresh: bool = False) -> Dict[str, Any]:
        """바이낸스 잔고 조회 (기존 python-binance 방식)"""
        try:
            # 기존 바이낸스 클라이언트가 있는지 확인
            if hasattr(self, 'binance_client') and self.binance_client:
                # 기존 바이낸스 클라이언트 사용
                account_info = self.binance_client.get_account_info()
                balance = self.binance_client.get_balance()
                
                result = {
                    'exchange': 'binance',
                    'balance': balance,
                    'account_info': account_info,
                    'timestamp': datetime.now().isoformat(),
                    'status': 'success'
                }
                
                # 캐시 저장
                cache_key = "binance_balance"
                self.balance_cache[cache_key] = result
                self.last_balance_update[cache_key] = datetime.now()
                
                self.logger.info("바이낸스 잔고 조회 완료 (기존 방식)")
                return result
            else:
                # 바이낸스 클라이언트가 없으면 CCXT 방식으로 폴백
                return self._get_ccxt_balance('binance', force_refresh)
                
        except Exception as e:
            self.logger.error(f"바이낸스 잔고 조회 오류: {e}")
            return {'error': str(e), 'exchange': 'binance', 'status': 'error'}
    
    def _get_ccxt_balance(self, exchange_name: str, force_refresh: bool = False) -> Dict[str, Any]:
        """CCXT 거래소 잔고 조회"""
        try:
            # 클라이언트 가져오기
            client = self._get_or_create_exchange_client(exchange_name)
            if not client:
                return {
                    'exchange': exchange_name,
                    'status': 'client_unavailable',
                    'error': f'{exchange_name} 클라이언트를 찾을 수 없습니다'
                }
            
            # 연결 확인
            if not client.is_connected:
                if not client.connect():
                    return {
                        'exchange': exchange_name,
                        'status': 'connection_failed',
                        'error': f'{exchange_name} 연결 실패'
                    }
            
            # 잔고 조회
            balance = client.get_balance()
            account_info = client.get_account_info()
            
            result = {
                'exchange': exchange_name,
                'balance': balance,
                'account_info': account_info,
                'timestamp': datetime.now().isoformat(),
                'status': 'success'
            }
            
            # 캐시 저장
            cache_key = f"{exchange_name}_balance"
            self.balance_cache[cache_key] = result
            self.last_balance_update[cache_key] = datetime.now()
            
            self.logger.info(f"{exchange_name} 잔고 조회 완료 (CCXT 방식)")
            return result
            
        except Exception as e:
            self.logger.error(f"{exchange_name} CCXT 잔고 조회 오류: {e}")
            if self._is_auth_error_message(str(e)):
                self.invalid_api_keys.add(self._normalize_exchange_name(exchange_name))
                return {
                    'error': str(e),
                    'exchange': exchange_name,
                    'status': 'invalid_api_keys',
                    'message': '인증 오류로 잔고 조회 실패'
                }
            return {'error': str(e), 'exchange': exchange_name, 'status': 'error'}
    
    def get_all_exchange_balances(self) -> Dict[str, Dict[str, Any]]:
        """모든 거래소 잔고 조회"""
        results = {}
        supported_exchanges = ['binance', 'upbit', 'bithumb', 'bybit', 'okx', 'bitget']

        for exchange_name in supported_exchanges:
            normalized = self._normalize_exchange_name(exchange_name)

            if not self._is_exchange_enabled(normalized):
                results[normalized] = {
                    'exchange': normalized,
                    'status': 'disabled',
                    'message': 'enabled_exchanges에 포함되지 않음'
                }
                continue

            # API 키가 있는 거래소만 조회
            if self._has_valid_api_keys(normalized):
                results[normalized] = self.get_exchange_balance(normalized)
            else:
                results[normalized] = {
                    'exchange': normalized,
                    'status': 'no_api_keys',
                    'message': 'API 키가 설정되지 않음'
                }

        return results
    
    def _has_valid_api_keys(self, exchange_name: str) -> bool:
        """거래소 API 키 유효성 확인"""
        normalized = self._normalize_exchange_name(exchange_name)
        if normalized == 'binance':
            return bool(self.settings.get('binance_api_key') and self.settings.get('binance_secret_key'))
        elif normalized == 'upbit':
            return bool(self.settings.get('upbit_api_key') and self.settings.get('upbit_secret_key'))
        elif normalized == 'bithumb':
            return bool(self.settings.get('bithumb_api_key') and self.settings.get('bithumb_secret_key'))
        elif normalized == 'bybit':
            return bool(self.settings.get('bybit_api_key') and self.settings.get('bybit_secret_key'))
        elif normalized == 'okx':
            return bool(self.settings.get('okx_api_key') and self.settings.get('okx_secret_key') and self.settings.get('okx_passphrase'))
        elif normalized == 'bitget':
            # Bitget는 password(=passphrase)도 필수
            return bool(
                self.settings.get('bitget_api_key') and
                self.settings.get('bitget_secret_key') and
                self.settings.get('bitget_password')
            )
        return False
    
    def get_current_price(self, symbol: str, exchange_name: Optional[str] = None) -> float:
        """현재 가격 조회"""
        try:
            if exchange_name is None:
                exchange_name = self.settings.get('selected_exchange', 'binance')

            ex_name: str = self._normalize_exchange_name(exchange_name if isinstance(exchange_name, str) else self.settings.get('selected_exchange', 'binance'))

            if not self._is_exchange_enabled(ex_name):
                return 0.0

            client = self._get_or_create_exchange_client(ex_name)
            if not client:
                return 0.0

            # Binance는 기존 경로 유지
            if ex_name == 'binance' and hasattr(client, 'get_current_price'):
                return float(client.get_current_price(symbol))

            # CCXT 경로: 심볼 정규화 + 마켓 검증 후 fetch_ticker 사용
            try:
                if not getattr(client, 'is_connected', False) and hasattr(client, 'connect'):
                    if not client.connect():
                        return 0.0
            except Exception:
                pass

            # 심볼 정규화
            ccxt_symbol = None
            try:
                if hasattr(client, '_normalize_symbol'):
                    ccxt_symbol = client._normalize_symbol(symbol)  # type: ignore
            except Exception:
                ccxt_symbol = None
            if not ccxt_symbol:
                ccxt_symbol = self._to_ccxt_symbol(symbol)
            try:
                if ex_name in ("upbit", "bithumb") and isinstance(ccxt_symbol, str) and ccxt_symbol.upper().endswith('/USDT'):
                    base = ccxt_symbol.split('/')[0]
                    ccxt_symbol = f"{base}/KRW"
            except Exception:
                pass

            ccxt_exchange = getattr(client, 'exchange', None)
            if ccxt_exchange is not None and hasattr(ccxt_exchange, 'fetch_ticker'):
                try:
                    if hasattr(ccxt_exchange, 'markets') and not getattr(ccxt_exchange, 'markets'):
                        if hasattr(ccxt_exchange, 'load_markets'):
                            ccxt_exchange.load_markets()
                except Exception:
                    pass

                try:
                    markets = getattr(ccxt_exchange, 'markets', {}) or {}
                    if isinstance(markets, dict) and ccxt_symbol not in markets:
                        try:
                            self.logger.info(f"{ex_name} 미지원 심볼 스킵: {ccxt_symbol}")
                        except Exception:
                            pass
                        return 0.0
                except Exception:
                    pass

                try:
                    t = ccxt_exchange.fetch_ticker(ccxt_symbol)
                    last = t.get('last') or t.get('close') or 0.0
                    return float(last or 0.0)
                except Exception as e:
                    try:
                        self.logger.info(f"{ex_name} 가격 조회 fetch_ticker 실패({ccxt_symbol}): {e}")
                    except Exception:
                        pass
                    return 0.0

            # 폴백: 클라이언트 구현 존재 시 사용
            if hasattr(client, 'get_current_price'):
                try:
                    return float(client.get_current_price(ccxt_symbol or symbol))
                except Exception:
                    return 0.0
            return 0.0

        except Exception as e:
            self.logger.error(f"{exchange_name} 가격 조회 오류: {e}")
            return 0.0

    def get_24h_ticker(self, symbol: str, exchange_name: Optional[str] = None) -> Dict[str, Any]:
        """24시간 티커 데이터 조회"""
        try:
            if exchange_name is None:
                exchange_name = self.settings.get('selected_exchange', 'binance')

            ex_name: str = self._normalize_exchange_name(exchange_name if isinstance(exchange_name, str) else self.settings.get('selected_exchange', 'binance'))

            if not self._is_exchange_enabled(ex_name):
                return {}

            client = self._get_or_create_exchange_client(ex_name)
            if not client:
                return {}

            # Binance는 기존 경로 유지
            if ex_name == 'binance' and hasattr(client, 'get_24h_ticker'):
                return client.get_24h_ticker(symbol) or {}

            # CCXT 경로: 심볼 정규화 + 마켓 검증 후 fetch_ticker 사용
            try:
                if not getattr(client, 'is_connected', False) and hasattr(client, 'connect'):
                    if not client.connect():
                        return {}
            except Exception:
                pass

            ccxt_symbol = None
            try:
                if hasattr(client, '_normalize_symbol'):
                    ccxt_symbol = client._normalize_symbol(symbol)  # type: ignore
            except Exception:
                ccxt_symbol = None
            if not ccxt_symbol:
                ccxt_symbol = self._to_ccxt_symbol(symbol)
            try:
                if ex_name in ("upbit", "bithumb") and isinstance(ccxt_symbol, str) and ccxt_symbol.upper().endswith('/USDT'):
                    base = ccxt_symbol.split('/')[0]
                    ccxt_symbol = f"{base}/KRW"
            except Exception:
                pass

            ccxt_exchange = getattr(client, 'exchange', None)
            if ccxt_exchange is not None and hasattr(ccxt_exchange, 'fetch_ticker'):
                try:
                    if hasattr(ccxt_exchange, 'markets') and not getattr(ccxt_exchange, 'markets'):
                        if hasattr(ccxt_exchange, 'load_markets'):
                            ccxt_exchange.load_markets()
                except Exception:
                    pass

                try:
                    markets = getattr(ccxt_exchange, 'markets', {}) or {}
                    if isinstance(markets, dict) and ccxt_symbol not in markets:
                        try:
                            self.logger.info(f"{ex_name} 미지원 심볼 스킵: {ccxt_symbol}")
                        except Exception:
                            pass
                        return {}
                except Exception:
                    pass

                try:
                    t = ccxt_exchange.fetch_ticker(ccxt_symbol)
                    return {
                        'symbol': ccxt_symbol,
                        'priceChangePercent': t.get('percentage', 0),
                        'lastPrice': t.get('last', 0),
                        'volume': t.get('baseVolume', 0),
                        'quoteVolume': t.get('quoteVolume', 0)
                    }
                except Exception as e:
                    try:
                        self.logger.info(f"{ex_name} 24h 티커 fetch_ticker 실패({ccxt_symbol}): {e}")
                    except Exception:
                        pass
                    return {}

            # 폴백: 클라이언트 구현 존재 시 사용
            if hasattr(client, 'get_24h_ticker'):
                try:
                    return client.get_24h_ticker(ccxt_symbol or symbol) or {}
                except Exception:
                    return {}
            return {}

        except Exception as e:
            self.logger.error(f"{exchange_name} 24시간 티커 조회 오류: {e}")
            return {}

    # ---- OHLCV/Klines 통합 조회 (Analyzer 연동용) ----
    def get_klines(self, symbol: str, interval: str = '1m', limit: int = 100, exchange_name: Optional[str] = None) -> List[List]:
        """거래소별 캔들 데이터 조회. Binance 포맷(list[list])로 반환"""
        try:
            if exchange_name is None:
                exchange_name = self.settings.get('selected_exchange', 'binance')
            ex_name: str = self._normalize_exchange_name(exchange_name if isinstance(exchange_name, str) else self.settings.get('selected_exchange', 'binance'))

            if not self._is_exchange_enabled(ex_name):
                return []

            # 1) Binance: 기존 클라이언트 경로 사용
            if ex_name == 'binance' and self.binance_client and hasattr(self.binance_client, 'get_klines'):
                return self.binance_client.get_klines(symbol, interval, limit)

            # 2) CCXT 어댑터 경유: fetch_ohlcv 사용 (심볼 변환 필요)
            client = self._get_or_create_exchange_client(ex_name)
            if not client:
                return []

            # 심볼 정규화: 어댑터의 _normalize_symbol 우선 사용(있을 때)
            ccxt_symbol = None
            try:
                if hasattr(client, '_normalize_symbol'):
                    ccxt_symbol = client._normalize_symbol(symbol)  # type: ignore
            except Exception:
                ccxt_symbol = None
            if not ccxt_symbol:
                # 폴백: 간단 규칙 변환
                ccxt_symbol = self._to_ccxt_symbol(symbol)

            # 한국 거래소(업비트/빗썸) 전용 규칙: USDT 마켓 미지원 → KRW로 매핑 시도
            try:
                if ex_name in ("upbit", "bithumb") and isinstance(ccxt_symbol, str):
                    if ccxt_symbol.upper().endswith("/USDT"):
                        base = ccxt_symbol.split("/")[0]
                        # 우선 KRW 시도로 교체
                        ccxt_symbol = f"{base}/KRW"
            except Exception:
                pass

            ccxt_timeframe = interval  # 기본 동일 표기

            # 타입 안정성: 런타임 속성 접근은 getattr로 안전하게
            ccxt_exchange = getattr(client, 'exchange', None)
            if ccxt_exchange is not None and hasattr(ccxt_exchange, 'fetch_ohlcv'):
                # 마켓 지원 여부 사전 검증 (오류 로그 억제용)
                try:
                    if hasattr(ccxt_exchange, 'markets') and not getattr(ccxt_exchange, 'markets'):
                        # markets 미로딩 시 로드
                        if hasattr(ccxt_exchange, 'load_markets'):
                            ccxt_exchange.load_markets()
                except Exception:
                    pass

                try:
                    markets = getattr(ccxt_exchange, 'markets', {}) or {}
                    if isinstance(markets, dict) and ccxt_symbol not in markets:
                        # 지원하지 않는 심볼은 조용히 스킵 (정보 로그만)
                        try:
                            self.logger.info(f"{ex_name} 미지원 심볼 스킵: {ccxt_symbol}")
                        except Exception:
                            pass
                        return []
                except Exception:
                    # 마켓 검증 실패 시에도 안전하게 진행
                    pass

                ohlcv = ccxt_exchange.fetch_ohlcv(ccxt_symbol, timeframe=ccxt_timeframe, limit=limit)
                # ccxt 포맷은 이미 [ts, o,h,l,c,v]
                return ohlcv or []

            # 3) 마지막 폴백: 지원 없음
            self.logger.warning(f"{ex_name} 어댑터가 OHLCV를 지원하지 않습니다")
            return []
        except Exception as e:
            safe_name = exchange_name or 'unknown'
            self.logger.error(f"{safe_name} klines 조회 오류: {e}")
            return []

    def _to_ccxt_symbol(self, symbol: str) -> str:
        """간단한 심볼 변환: 'BTCUSDT' -> 'BTC/USDT' (기본 규칙)"""
        try:
            if '/' in symbol:
                return symbol
            sym = symbol.upper()
            for quote in ('USDT', 'USD', 'USDC', 'BTC', 'ETH'):
                if sym.endswith(quote):
                    base = sym[:-len(quote)]
                    if base:
                        return f"{base}/{quote}"
            # 기본 USDT 가정 (이미 USDT로 끝나지 않은 경우만)
            if not sym.endswith('USDT'):
                return f"{sym}/USDT"
            else:
                # 이미 USDT로 끝나는 경우 그대로 반환
                return sym
        except Exception:
            return symbol
    
    def validate_exchange_connection(self, exchange_name: str) -> bool:
        """거래소 연결 유효성 검증 (개선된 버전)
        
        BinanceClient의 경우 is_connected 속성도 확인하여
        실제 연결 상태를 더 정확히 판단합니다.
        """
        try:
            normalized_name = self._normalize_exchange_name(exchange_name)
            if not normalized_name:
                return False
            
            # disabled 거래소는 연결 검증 대상에서 제외
            if not self._is_exchange_enabled(normalized_name):
                return False

            # Binance 특별 처리: BinanceClient의 실제 연결 상태 확인
            if normalized_name == 'binance' and getattr(self, 'binance_client', None):
                binance_client = self.binance_client
                # 1. is_connected 속성 확인 (빠른 체크)
                if hasattr(binance_client, 'is_connected') and binance_client.is_connected:
                    # 2. validate_credentials() 호출로 실제 검증
                    try:
                        return binance_client.validate_credentials()
                    except Exception as e:
                        self.logger.warning(f"Binance 연결 검증 중 오류 (is_connected=True): {e}")
                        # is_connected가 True면 연결은 되어 있다고 간주
                        return True
                else:
                    # is_connected가 False면 validate_credentials()로 재시도
                    try:
                        return binance_client.validate_credentials()
                    except Exception:
                        return False
            
            # 다른 거래소: 기존 로직 유지
            client = self._get_or_create_exchange_client(exchange_name)
            if not client:
                return False

            # 1) 어댑터 자체 검증
            try:
                if not client.validate_credentials():
                    return False
            except Exception:
                return False

            # 2) API 키가 있는 경우에는 실제 인증 호출(잔고)까지 성공해야 True
            if self._has_valid_api_keys(normalized_name):
                balance_result = self.get_exchange_balance(normalized_name, force_refresh=True)
                if not isinstance(balance_result, dict):
                    return False
                status = balance_result.get('status', '')
                if status != 'success':
                    return False

            return True
            
        except Exception as e:
            self.logger.error(f"{exchange_name} 연결 검증 오류: {e}")
            return False
    
    # 중복된 switch_exchange 정의 제거 (상단 메서드 사용)
    
    def get_exchange_status(self) -> Dict[str, Any]:
        """거래소 상태 정보 반환"""
        selected_exchange = self.settings.get('selected_exchange', 'binance')
        
        current_client = None
        try:
            if self.current_exchange is not None:
                current_client = getattr(self.current_exchange, 'exchange_name', None)
                if not current_client and hasattr(self.current_exchange, '__class__'):
                    current_client = self.current_exchange.__class__.__name__
        except Exception:
            current_client = None

        return {
            'selected_exchange': selected_exchange,
            'current_client': current_client or selected_exchange,
            'available_exchanges': self._get_available_exchanges(),
            'last_update': datetime.now().isoformat()
        }
    
    def _get_available_exchanges(self) -> List[str]:
        """사용 가능한 거래소 목록 반환"""
        available = []
        for exchange_name in ['binance', 'upbit', 'bithumb', 'bybit', 'okx', 'bitget']:
            if self._has_valid_api_keys(exchange_name):
                available.append(exchange_name)
        return available
    
    
    def clear_cache(self):
        """캐시 초기화"""
        self.balance_cache.clear()
        self.last_balance_update.clear()
        self.logger.info("거래소 캐시 초기화 완료")
