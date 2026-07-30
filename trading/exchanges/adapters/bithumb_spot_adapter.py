#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
빗썸 현물 어댑터 (CCXT 기반)
"""

import logging
from typing import Dict, List, Optional, Any
from ..interfaces.spot_exchange import SpotExchange

class BithumbSpotAdapter(SpotExchange):
    """빗썸 현물 어댑터"""
    
    def __init__(self, api_key: str, secret_key: str, **kwargs):
        super().__init__("bithumb")
        self.api_key = api_key
        self.secret_key = secret_key
        self.exchange = None
        self.logger = logging.getLogger(__name__)
        self.last_error: str = ""
        self.last_auth_guidance: str = ""
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO': log_event(category, msg, exchange='bithumb', level=level)
        # 거래내역 조회 경로 캐시: my_trades | orders_fallback | unsupported
        self._trade_history_mode: Optional[str] = None
        self._trade_history_notice_emitted = set()

    def _log_trade_history_notice_once(self, key: str, msg: str, level: str = 'INFO') -> None:
        if key in self._trade_history_notice_emitted:
            return
        self._trade_history_notice_emitted.add(key)
        self.log_event('system', msg, level=level)

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

    def _normalize_bithumb_symbol(self, symbol: str) -> str:
        """빗썸 심볼 정규화 (BTCUSDT/KRW-BTC/KRW/BTC -> BTC/KRW)"""
        if not symbol:
            return 'BTC/KRW'

        s = str(symbol).strip().upper()
        if s.startswith('KRW-'):
            return f"{s.split('-', 1)[1]}/KRW"
        if '/' in s:
            left, right = s.split('/', 1)
            if left == 'KRW':
                return f"{right}/KRW"
            if right in {'KRW', 'USDT'}:
                return f"{left}/KRW"
            return f"{left}/KRW"
        if s.endswith('USDT'):
            return f"{s[:-4]}/KRW"
        if s.endswith('KRW') and len(s) > 3:
            return f"{s[:-3]}/KRW"
        return f'{s}/KRW'

    def _display_symbol(self, symbol: Optional[str]) -> str:
        if not symbol:
            return 'BTC/KRW'
        raw = str(symbol).upper().strip()
        if raw.startswith('KRW-'):
            return f"{raw.split('-', 1)[1]}/KRW"
        if raw.startswith('KRW/'):
            return f"{raw.split('/', 1)[1]}/KRW"
        s = raw.replace('-', '').replace('_', '')
        if ':' in s:
            s = s.split(':', 1)[0]
        if '/' in s:
            left, right = s.split('/', 1)
            if right in {'KRW', 'USDT'}:
                return f'{left}/KRW'
            return f'{left}/{right}'
        if s.endswith('USDT'):
            return f'{s[:-4]}/KRW'
        if s.endswith('KRW') and len(s) > 3:
            return f'{s[:-3]}/KRW'
        return f'{s}/KRW'

    def _orders_to_trade_history(self, orders: List[Dict[str, Any]], symbol_hint: Optional[str] = None) -> List[Dict[str, Any]]:
        trades: List[Dict[str, Any]] = []
        for order in orders or []:
            item = dict(order)
            status = str(item.get('status') or '').lower()
            filled = float(item.get('filled') or 0.0)
            if status not in ('closed', 'filled') and filled <= 0:
                continue
            amount = float(item.get('amount') or filled or 0.0)
            price = float(item.get('average') or item.get('price') or 0.0)
            cost = float(item.get('cost') or (price * amount if price and amount else 0.0))
            trades.append({
                'id': item.get('id'),
                'order': item.get('id'),
                'symbol': self._display_symbol(item.get('symbol') or symbol_hint),
                'side': str(item.get('side') or '').lower(),
                'type': item.get('type'),
                'status': item.get('status'),
                'price': price,
                'average': item.get('average') or price,
                'amount': amount,
                'filled': filled or amount,
                'remaining': item.get('remaining'),
                'cost': cost,
                'timestamp': item.get('timestamp'),
                'datetime': item.get('datetime'),
                'fee': item.get('fee'),
            })
        return trades
    
    def connect(self) -> bool:
        try:
            import importlib
            ccxt = importlib.import_module('ccxt')
            if self.api_key and self.secret_key:
                config = {
                    'apiKey': str(self.api_key) if self.api_key is not None else '',
                    'secret': str(self.secret_key) if self.secret_key is not None else '',
                    'enableRateLimit': True,
                }
                mode = "인증 모드"
            else:
                config = {
                    'enableRateLimit': True,
                }
                mode = "공개 모드"
            self.exchange = ccxt.bithumb(config)  # type: ignore
            self.exchange.load_markets()
            self.is_connected = True
            self.last_error = ""
            self.last_auth_guidance = ""
            self.log_event('system', f"빗썸 연결 성공 ({mode})")
            return True
        except Exception as e:
            self.last_error = str(e)
            self.log_event('system', f"빗썸 연결 실패: {e}", level='ERROR')
            return False
    
    def get_balance(self) -> Dict[str, float]:
        if not self.is_connected or not self.exchange:
            return {}

        if not self.api_key or not self.secret_key:
            return {
                'KRW': 0.0,
                'BTC': 0.0,
                'ETH': 0.0,
            }

        try:
            balance = self.exchange.fetch_balance()
            return {
                'KRW': self._extract_total_balance(balance, 'KRW'),
                'BTC': self._extract_total_balance(balance, 'BTC'),
                'ETH': self._extract_total_balance(balance, 'ETH'),
            }
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
    
    def place_order(self, symbol: str, side: str, quantity: float, 
                   price: Optional[float] = None, order_type: str = "MARKET") -> Dict[str, Any]:
        if not self.is_connected:
            return {}
        try:
            symbol = self._normalize_bithumb_symbol(symbol)
            
            type_literal = 'limit' if order_type.upper() == 'LIMIT' else 'market'
            side_literal = 'buy' if side.lower() == 'buy' else 'sell'
            order = self.exchange.create_order(  # type: ignore
                symbol=symbol, type=type_literal, side=side_literal,
                amount=quantity, price=price
            )
            return order
        except Exception as e:
            self.log_event('system', f"주문 실행 실패: {e}", level='ERROR')
            return {}
    
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        if not self.is_connected:
            return False
        try:
            self.exchange.cancel_order(order_id, symbol)  # type: ignore
            return True
        except Exception as e:
            self.log_event('system', f"주문 취소 실패: {e}", level='ERROR')
            return False
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            orders = self.exchange.fetch_open_orders(symbol)  # type: ignore
            normalized_orders = []
            for o in orders:
                item = dict(o)
                item['symbol'] = self._display_symbol(item.get('symbol'))
                normalized_orders.append(item)
            return normalized_orders
        except Exception as e:
            self.log_event('system', f"오픈 주문 조회 실패: {e}", level='ERROR')
            return []
    
    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            normalized = self._normalize_bithumb_symbol(symbol) if symbol else None
            mode = self._trade_history_mode
            if mode is None:
                has_fetch_my_trades = True
                try:
                    has_fetch_my_trades = bool(getattr(self.exchange, 'has', {}).get('fetchMyTrades', True))
                except Exception:
                    has_fetch_my_trades = True
                mode = 'my_trades' if has_fetch_my_trades else 'orders_fallback'
                self._trade_history_mode = mode

            if mode == 'my_trades':
                try:
                    trades = self.exchange.fetch_my_trades(normalized, limit=limit)  # type: ignore
                    return [dict(t) for t in trades]
                except Exception as fetch_err:
                    fetch_err_text = str(fetch_err).lower()
                    unsupported_tokens = ('not supported', 'unsupported', 'fetchmytrades', 'fetch_my_trades')
                    if not any(token in fetch_err_text for token in unsupported_tokens):
                        raise
                    # 한 번 미지원이 확정되면 이후에는 fetch_my_trades를 시도하지 않음
                    mode = 'orders_fallback'
                    self._trade_history_mode = mode
                    self._log_trade_history_notice_once(
                        'fetch_my_trades_unsupported',
                        '빗썸 거래 내역 조회: fetch_my_trades 미지원, 주문 내역 기반 폴백으로 전환'
                    )

            if mode == 'orders_fallback':
                for method_name in ('fetch_closed_orders', 'fetch_orders'):
                    fetcher = getattr(self.exchange, method_name, None)
                    if not callable(fetcher):
                        continue
                    try:
                        try:
                            orders = fetcher(normalized, limit=limit)  # type: ignore[misc]
                        except TypeError:
                            orders = fetcher(normalized)  # type: ignore[misc]
                    except Exception:
                        continue

                    trades = self._orders_to_trade_history(list(orders or []), symbol_hint=normalized)
                    if trades:
                        self._log_trade_history_notice_once(
                            'orders_fallback_in_use',
                            '빗썸 거래 내역 조회: 주문 내역 기반 폴백 사용 중'
                        )
                        return trades[:limit]

                # 폴백 경로에서도 결과를 얻지 못하면 unsupported로 고정해 과도한 재시도 차단
                self._trade_history_mode = 'unsupported'
                self._log_trade_history_notice_once(
                    'trade_history_effectively_unsupported',
                    '빗썸 거래 내역 조회: 현재 환경에서 거래 내역 API 경로를 사용할 수 없음'
                )
                return []

            if mode == 'unsupported':
                return []

            for method_name in ('fetch_closed_orders', 'fetch_orders'):
                fetcher = getattr(self.exchange, method_name, None)
                if not callable(fetcher):
                    continue
                try:
                    try:
                        orders = fetcher(normalized, limit=limit)  # type: ignore[misc]
                    except TypeError:
                        orders = fetcher(normalized)  # type: ignore[misc]
                except Exception:
                    continue

                trades = self._orders_to_trade_history(list(orders or []), symbol_hint=normalized)
                if trades:
                    self._log_trade_history_notice_once(
                        'orders_fallback_in_use',
                        '빗썸 거래 내역 조회: 주문 내역 기반 폴백 사용 중'
                    )
                    return trades[:limit]

            self._trade_history_mode = 'unsupported'
            self._log_trade_history_notice_once(
                'trade_history_effectively_unsupported',
                '빗썸 거래 내역 조회: 현재 환경에서 거래 내역 API 경로를 사용할 수 없음'
            )
            return []
        except Exception as e:
            err_text = str(e).lower()
            if ('not supported' in err_text or 'unsupported' in err_text
                    or 'fetchmytrades' in err_text or 'fetch_my_trades' in err_text):
                self._trade_history_mode = 'unsupported'
                self._log_trade_history_notice_once(
                    'fetch_my_trades_unsupported',
                    '빗썸 거래 내역 조회: fetch_my_trades 미지원'
                )
            else:
                self.log_event('system', f"거래 내역 조회 실패: {e}", level='ERROR')
            return []
    
    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        """24시간 티커 데이터 조회"""
        if not self.is_connected:
            return {}
        try:
            sym = self._normalize_bithumb_symbol(symbol)
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

    def get_current_price(self, symbol: str) -> float:
        if not self.is_connected:
            return 0.0
        try:
            # 🔥 빗썸 심볼 정규화 개선
            sym = self._normalize_bithumb_symbol(symbol)
            
            # 🔥 안전한 티커 조회
            ticker = self.exchange.fetch_ticker(sym)  # type: ignore
            if not ticker:
                self.logger.warning(f"빗썸 티커 데이터 없음: {sym}")
                return 0.0
                
            # 🔥 안전한 가격 추출
            price = ticker.get('last') or ticker.get('close') or ticker.get('price')
            if price is None:
                self.logger.warning(f"빗썸 가격 데이터 없음: {sym}")
                return 0.0
                
            return float(price)
        except Exception as e:
            self.logger.error(f"현재가 조회 실패 ({symbol}): {e}")
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

            # 실제 인증 호출로 API 키 유효성 검증
            if self.api_key and self.secret_key and self.exchange:
                try:
                    self.exchange.fetch_balance()  # type: ignore
                except Exception as e:
                    self.last_error = str(e)
                    if 'ip' in self.last_error.lower():
                        self.last_auth_guidance = "빗썸 API 키의 허용 IP 설정을 확인하세요."
                    self.log_event('system', f"빗썸 API 키 검증 실패: {e}", level='ERROR')
                    return False

            return True
        except Exception as e:
            self.logger.error(f"API 키 검증 실패: {e}")
            return False
