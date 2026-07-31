#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
업비트 현물 어댑터 (CCXT 기반)
"""

import logging
from typing import Dict, List, Optional, Any
from ..interfaces.spot_exchange import SpotExchange
from ..balance_normalizer import normalize_ccxt_total_balances
from ..execution_history import build_execution_capabilities, fetch_ccxt_execution_history

class UpbitSpotAdapter(SpotExchange):
    """업비트 현물 어댑터"""
    
    def __init__(self, api_key: str, secret_key: str, **kwargs):
        super().__init__("upbit")
        self.api_key = api_key
        self.secret_key = secret_key
        self.exchange = None
        self.logger = logging.getLogger(__name__)
        self.last_error: str = ""
        self.last_auth_guidance: str = ""
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO': log_event(category, msg, exchange='upbit', level=level)
        self._trade_history_notice_emitted = False
        self._last_execution_capabilities: Dict[str, Any] = {}

    def _display_symbol(self, symbol: Optional[str]) -> str:
        return self._normalize_upbit_symbol(str(symbol or "BTC/KRW"))

    def get_execution_capabilities(self) -> Dict[str, Any]:
        detected = build_execution_capabilities(self.exchange)
        if self._last_execution_capabilities:
            detected.update(self._last_execution_capabilities)
        return detected

    def _extract_total_balance(self, balance: Dict[str, Any], currency: str) -> float:
        """ccxt fetch_balance 결과에서 통화 잔고를 안전하게 추출"""
        try:
            total_map = balance.get('total', {}) if isinstance(balance, dict) else {}
            if isinstance(total_map, dict) and currency in total_map:
                return float(total_map.get(currency) or 0.0)
            cur = balance.get(currency, {}) if isinstance(balance, dict) else {}
            if isinstance(cur, dict):
                return float(cur.get('total') or 0.0)
            if isinstance(cur, (int, float)):
                return float(cur)
        except Exception:
            pass
        return 0.0

    def _normalize_upbit_symbol(self, symbol: str) -> str:
        """업비트 심볼 정규화 (BTCUSDT/KRW-BTC/BTC/KRW -> BTC/KRW)"""
        if not symbol:
            return 'BTC/KRW'

        s = str(symbol).strip().upper()
        if '/' in s:
            base, quote = s.split('/', 1)
            if base == 'KRW':
                return f'{quote}/KRW'
            if quote in {'KRW', 'USDT'}:
                return f'{base}/KRW'
        if s.startswith('KRW-'):
            return f"{s.split('-', 1)[1]}/KRW"
        if s.endswith('USDT'):
            return f"{s[:-4]}/KRW"
        if s.endswith('KRW') and len(s) > 3:
            return f"{s[:-3]}/KRW"
        return f'{s}/KRW'
    
    def connect(self) -> bool:
        try:
            import importlib
            ccxt = importlib.import_module('ccxt')
            # API 키가 있으면 인증 모드, 없으면 공개 모드
            if self.api_key and self.secret_key:
                config = {
                    'apiKey': str(self.api_key) if self.api_key is not None else '',
                    'secret': str(self.secret_key) if self.secret_key is not None else '',
                    'enableRateLimit': True,
                }
                self.exchange = ccxt.upbit(config)  # type: ignore
                self.log_event('system', "업비트 연결 성공 (인증 모드)")
            else:
                config = {
                    'enableRateLimit': True,
                }
                self.exchange = ccxt.upbit(config)  # type: ignore
                self.log_event('system', "업비트 연결 성공 (공개 모드)")
            
            self.exchange.load_markets()
            self.is_connected = True
            self.last_error = ""
            self.last_auth_guidance = ""
            return True
        except Exception as e:
            self.last_error = str(e)
            self.log_event('system', f"업비트 연결 실패: {e}", level='ERROR')
            return False
    
    def get_balance(self) -> Dict[str, float]:
        if not self.is_connected or not self.exchange:
            return {}
        
        # API 키가 없으면 잔고 조회 불가
        if not self.api_key or not self.secret_key:
            return {'KRW': 0.0}
        
        try:
            balance = self.exchange.fetch_balance()
            return normalize_ccxt_total_balances(balance, quote_asset='KRW')
        except Exception as e:
            self.last_error = str(e)
            self.log_event('system', f"잔고 조회 실패: {e}", level='ERROR')
            return {}
    
    def get_account_info(self) -> Dict[str, Any]:
        """계정 정보 조회 (get_balance 래퍼)"""
        if not self.is_connected:
            return {}
        try:
            balance = self.get_balance()
            if not balance:
                return {}
            return {
                'available_balance': balance.get('KRW', 0),
                'total_balance': balance.get('KRW', 0),
                'balances': balance
            }
        except Exception as e:
            self.log_event('system', f"계정 정보 조회 실패: {e}", level='ERROR')
            return {}

    def get_current_price(self, symbol: str) -> float:
        if not self.is_connected:
            return 0.0
        try:
            sym = self._normalize_upbit_symbol(symbol)
            
            # 🔥 안전한 티커 조회
            ticker = self.exchange.fetch_ticker(sym)  # type: ignore
            if not ticker:
                self.log_event('system', f"업비트 티커 데이터 없음: {sym}", level='WARNING')
                return 0.0
                
            # 🔥 안전한 가격 추출
            price = ticker.get('last') or ticker.get('close') or ticker.get('price')
            if price is None:
                self.log_event('system', f"업비트 가격 데이터 없음: {sym}", level='WARNING')
                return 0.0
                
            return float(price)
        except Exception as e:
            self.log_event('system', f"현재가 조회 실패 ({symbol}): {e}", level='ERROR')
            return 0.0

    def get_exchange_info(self) -> Dict[str, Any]:
        if not self.is_connected:
            return {}
        try:
            markets = self.exchange.load_markets()  # type: ignore
            return {
                'symbols': [
                    {
                        'symbol': sym,
                        'baseAsset': info.get('base'),
                        'quoteAsset': info.get('quote'),
                        'status': 'TRADING' if info.get('active') else 'BREAK'
                    }
                    for sym, info in markets.items()
                    if sym.endswith('/KRW')
                ]
            }
        except Exception as e:
            self.logger.error(f"거래소 정보 조회 실패: {e}")
            return {}

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        if not self.is_connected:
            return {}
        try:
            order = self.exchange.fetch_order(order_id)  # type: ignore
            return dict(order)
        except Exception as e:
            self.logger.error(f"주문 상태 조회 실패: {e}")
            return {}

    def validate_credentials(self) -> bool:
        try:
            if not self.connect():
                return False

            # API 키가 설정된 경우 실제 인증 호출로 키 유효성 검증
            if self.api_key and self.secret_key and self.exchange:
                try:
                    self.exchange.fetch_balance()  # type: ignore
                except Exception as e:
                    self.last_error = str(e)
                    if 'ip' in self.last_error.lower():
                        self.last_auth_guidance = "업비트 API 키의 허용 IP 설정을 확인하세요."
                    self.log_event('system', f"업비트 API 키 검증 실패: {e}", level='ERROR')
                    return False

            return True
        except Exception as e:
            self.logger.error(f"API 키 검증 실패: {e}")
            return False
    
    def place_order(self, symbol: str, side: str, quantity: float, 
                   price: Optional[float] = None, order_type: str = "MARKET") -> Dict[str, Any]:
        if not self.is_connected:
            return {}
        try:
            symbol = self._normalize_upbit_symbol(symbol)

            from trading.exchanges.order_constraints import prepare_ccxt_order_quantity
            constraint = prepare_ccxt_order_quantity(
                self.exchange, symbol, quantity, reference_price=price,
            )
            if not constraint.get('allowed'):
                msg = str(constraint.get('reason') or 'order constraints not met')
                self.log_event('system', f"{symbol} 주문 규격 차단: {msg}", level='WARNING')
                return {'status': 'error', 'error': msg}
            quantity = float(constraint['quantity'])
            
            type_literal = 'limit' if order_type.upper() == 'LIMIT' else 'market'
            side_literal = 'buy' if side.lower() == 'buy' else 'sell'
            order = self.exchange.create_order(  # type: ignore
                symbol=symbol, type=type_literal, side=side_literal,
                amount=quantity, price=price
            )
            return order
        except Exception as e:
            self.logger.error(f"주문 실행 실패: {e}")
            return {}
    
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        if not self.is_connected:
            return False
        try:
            self.exchange.cancel_order(order_id, symbol)  # type: ignore
            return True
        except Exception as e:
            self.logger.error(f"주문 취소 실패: {e}")
            return False
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            orders = self.exchange.fetch_open_orders(symbol)  # type: ignore
            return [dict(o) for o in orders]
        except Exception as e:
            self.logger.error(f"오픈 주문 조회 실패: {e}")
            return []
    
    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            normalized = self._normalize_upbit_symbol(symbol) if symbol else None
            rows, capabilities = fetch_ccxt_execution_history(
                self.exchange,
                symbol=normalized,
                limit=limit,
                symbol_formatter=self._display_symbol,
            )
            self._last_execution_capabilities = capabilities
            if not rows and not capabilities.get("history_available") and not self._trade_history_notice_emitted:
                self._trade_history_notice_emitted = True
                self.log_event(
                    'system',
                    "업비트 과거 체결 API 미지원: NoahAI가 제출한 새 주문은 실제 체결 원장에 기록되지만 수동·과거 주문 자동 가져오기는 지원되지 않습니다.",
                    level='WARNING',
                )
            return rows
        except Exception as e:
            self.logger.error(f"거래 내역 조회 실패: {e}")
            return []
    
    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        """24시간 티커 데이터 조회"""
        if not self.is_connected:
            return {}
        try:
            sym = self._normalize_upbit_symbol(symbol)
            ticker = self.exchange.fetch_ticker(sym)  # type: ignore
            return {
                'last': ticker.get('last', 0),
                'high': ticker.get('high', 0),
                'low': ticker.get('low', 0),
                'open': ticker.get('open', 0),
                'change': ticker.get('change', 0),
                'percentage': ticker.get('percentage', 0),
                'baseVolume': ticker.get('baseVolume', 0),
                'quoteVolume': ticker.get('quoteVolume', 0)
            }
        except Exception as e:
            self.logger.error(f"24시간 티커 조회 실패: {e}")
            return {}
