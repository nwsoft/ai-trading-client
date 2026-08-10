#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
바이비트 선물 어댑터 (CCXT 기반)
"""

import logging
from typing import Dict, List, Optional, Any
from urllib import request as urllib_request
from ..interfaces.futures_exchange import FuturesExchange
from ..balance_normalizer import normalize_ccxt_total_balances
from ..execution_history import fetch_ccxt_execution_history
from decimal import Decimal, ROUND_DOWN

class BybitFuturesAdapter(FuturesExchange):
    """바이비트 선물 어댑터"""
    
    def __init__(self, api_key: str, secret_key: str, **kwargs):
        super().__init__("bybit")
        self.api_key = api_key
        self.secret_key = secret_key
        self.exchange = None
        self.logger = logging.getLogger(__name__)
        self.last_error: str = ""
        self.last_auth_guidance: str = ""
        self._auth_tip_emitted = set()
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO': log_event(category, msg, exchange='bybit', level=level)

    @staticmethod
    def _get_public_ip(timeout_sec: float = 1.8) -> Optional[str]:
        try:
            with urllib_request.urlopen('https://api.ipify.org', timeout=timeout_sec) as resp:
                ip = resp.read().decode('utf-8').strip()
                return ip or None
        except Exception:
            return None

    def _classify_auth_error(self, message: str) -> str:
        msg = str(message or '').lower()
        if 'unmatched ip' in msg or 'bound ip' in msg:
            return 'invalid_ip'
        if 'invalid api key' in msg or 'api key is invalid' in msg or 'retcode":10003' in msg:
            return 'invalid_api_key'
        if '401' in msg or 'unauthorized' in msg:
            return 'unauthorized'
        return ''

    def _build_auth_guidance(self, error_type: str) -> str:
        if error_type == 'invalid_ip':
            ip = self._get_public_ip()
            if ip:
                return (
                    f"Bybit IP 화이트리스트 불일치(Unmatched IP). 현재 공인 IP: {ip}. "
                    f"Bybit API 키의 bound IP 주소에 해당 IP를 등록하세요."
                )
            return "Bybit IP 화이트리스트 불일치(Unmatched IP). API 키 bound IP 설정을 확인하세요."
        if error_type == 'invalid_api_key':
            return "Bybit API 키가 유효하지 않습니다. 키 상태(활성/권한/만료)를 확인하세요."
        if error_type == 'unauthorized':
            return "Bybit 인증 실패(401). API Key/Secret 및 선물 거래 권한을 확인하세요."
        return ""

    def _handle_auth_error(self, raw_error: Any, where: str) -> None:
        msg = str(raw_error or '')
        error_type = self._classify_auth_error(msg)
        if not error_type:
            return
        guidance = self._build_auth_guidance(error_type)
        self.last_auth_guidance = guidance
        dedup_key = f"{where}:{error_type}"
        if guidance and dedup_key not in self._auth_tip_emitted:
            self.log_event('system', f"[Bybit 진단가이드] {guidance}", level='WARNING')
            self._auth_tip_emitted.add(dedup_key)
    
    def connect(self) -> bool:
        # API 키가 없으면 연결 시도하지 않음
        if not self.api_key or not self.secret_key:
            self.log_event('system', "바이비트 API 키가 설정되지 않음 - 연결 건너뜀")
            return False
            
        try:
            import importlib
            ccxt = importlib.import_module('ccxt')
            config = {
                'apiKey': str(self.api_key) if self.api_key is not None else '',
                'secret': str(self.secret_key) if self.secret_key is not None else '',
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',  # 선물 스왑 기본
                },
            }
            self.exchange = ccxt.bybit(config)  # type: ignore
            self.exchange.load_markets()
            self.is_connected = True
            self.last_error = ""
            self.last_auth_guidance = ""
            self.log_event('system', "바이비트 선물 연결 성공")
            return True
        except Exception as e:
            self.last_error = str(e)
            self._handle_auth_error(e, where='connect')
            self.log_event('system', f"바이비트 선물 연결 실패: {e}", level='ERROR')
            return False

    def _normalize_symbol(self, symbol: str) -> str:
        """CCXT 선물 심볼 정규화: BTCUSDT -> BTC/USDT:USDT"""
        s = str(symbol or '').upper().replace('-', '').replace('_', '')
        if '/' in symbol:
            # BTC/USDT or BTC/USDT:USDT 형태 처리
            return symbol if ':' in symbol else f"{symbol}:USDT"
        # 기본 USDT 가정
        if s.endswith('USDT'):
            base = s[:-4]
            if base:
                return f"{base}/USDT:USDT"
        return symbol

    def _display_symbol(self, symbol: Optional[str]) -> str:
        """로그/학습 데이터용 심볼 정규화: BTC/USDT:USDT -> BTCUSDT"""
        if not symbol:
            return ''
        s = str(symbol).upper().strip().replace('-', '').replace('_', '')
        if ':' in s:
            s = s.split(':', 1)[0]
        if '/' in s:
            base, quote = s.split('/', 1)
            return f"{base}{quote.replace(':', '')}"
        return s

    def _normalize_margin_mode(self, margin_type: str) -> str:
        mode = str(margin_type or '').strip().upper()
        if mode.startswith('ISOL'):
            return 'isolated'
        if mode in {'CROSS', 'CROSSED', 'CROSS_MARGIN', 'CROSS-MARGIN'}:
            return 'cross'
        return 'isolated'
    
    def get_balance(self) -> Dict[str, float]:
        if not self.is_connected or not self.exchange:
            return {}
        try:
            balance = self.exchange.fetch_balance()
            return normalize_ccxt_total_balances(balance, quote_asset='USDT')
        except Exception as e:
            self.last_error = str(e)
            self._handle_auth_error(e, where='get_balance')
            self.log_event('system', f"잔고 조회 실패: {e}", level='ERROR')
            return {}
    
    def get_account_info(self) -> Dict[str, Any]:
        if not self.is_connected or not self.exchange:
            return {}
        try:
            balance = self.exchange.fetch_balance()
            usdt = balance.get('USDT', {}) if isinstance(balance, dict) else {}
            return {
                'available_balance': usdt.get('free', 0),
                'total_balance': usdt.get('total', 0),
                'balances': balance
            }
        except Exception as e:
            self.last_error = str(e)
            self._handle_auth_error(e, where='get_account_info')
            self.log_event('system', f"계정 정보 조회 실패: {e}", level='ERROR')
            return {}
    
    def get_positions(self) -> List[Dict[str, Any]]:
        if not self.is_connected or not self.exchange:
            return []
        try:
            positions = self.exchange.fetch_positions()
            position_list = []
            for pos in positions:
                contracts = float(pos.get('contracts') or 0)
                if contracts > 0:
                    info = pos.get('info') or {}
                    side = str(pos.get('side') or info.get('side') or '').lower()
                    margin_type = (
                        pos.get('marginType')
                        or pos.get('margin_type')
                        or info.get('tradeMode')
                        or info.get('marginMode')
                        or 'unknown'
                    )
                    position_list.append({
                        'symbol': self._display_symbol(pos.get('symbol')),
                        'side': 'LONG' if side == 'long' else 'SHORT',
                        'size': contracts,
                        'entry_price': pos.get('entryPrice'),
                        'mark_price': pos.get('markPrice'),
                        'unrealized_pnl': pos.get('unrealizedPnl'),
                        'liquidation_price': pos.get('liquidationPrice'),
                        'leverage': pos.get('leverage'),
                        'margin_type': margin_type
                    })
            return position_list
        except Exception as e:
            self.log_event('system', f"포지션 조회 실패: {e}", level='ERROR')
            return []
    
    def place_order(self, symbol: str, side: str, quantity: float, 
                   price: Optional[float] = None, order_type: str = "MARKET") -> Dict[str, Any]:
        if not self.is_connected:
            return {'status': 'error', 'error': '연결되지 않음'}
        try:
            # 심볼 정규화 및 선물 마켓 존재 여부 확인
            norm_symbol = self._normalize_symbol(symbol)
            try:
                markets = getattr(self.exchange, 'markets', None) or {}
                if not markets:
                    self.exchange.load_markets()  # type: ignore
                    markets = getattr(self.exchange, 'markets', {})
            except Exception:
                markets = {}
            if not norm_symbol or norm_symbol not in markets:
                msg = f"미지원 선물 심볼: {symbol} (Bybit에 {symbol} USDT 선물 없음)"
                self.log_event('system', msg, level='WARNING')
                return {'status': 'error', 'error': msg}

            from trading.exchanges.order_constraints import prepare_ccxt_order_quantity
            constraint = prepare_ccxt_order_quantity(
                self.exchange, norm_symbol, quantity, reference_price=price,
            )
            if not constraint.get('allowed'):
                msg = str(constraint.get('reason') or 'order constraints not met')
                self.log_event('system', f"{symbol} 주문 규격 차단: {msg}", level='WARNING')
                return {'status': 'error', 'error': msg}
            quantity = float(constraint['quantity'])

            type_literal = 'limit' if str(order_type).upper() == 'LIMIT' else 'market'
            side_literal = 'buy' if str(side).lower() == 'buy' else 'sell'
            order = self.exchange.create_order(  # type: ignore
                symbol=norm_symbol, type=type_literal, side=side_literal,  # type: ignore
                amount=quantity, price=price
            )
            return {
                'status': 'success',
                'order_id': order.get('id'),
                'symbol': self._display_symbol(order.get('symbol')),
                'side': order.get('side'),
                'amount': order.get('amount'),
                'price': order.get('price'),
                'filled': order.get('filled'),
                'remaining': order.get('remaining'),
                'cost': order.get('cost'),
                'fee': order.get('fee'),
                'timestamp': order.get('timestamp')
            }
        except Exception as e:
            self.log_event('system', f"주문 실행 실패: {e}", level='ERROR')
            return {'status': 'error', 'error': str(e)}
    
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
            sym = self._normalize_symbol(symbol) if symbol else None
            orders = self.exchange.fetch_open_orders(sym)  # type: ignore
            normalized_orders = []
            for o in orders:
                item = dict(o)
                item['symbol'] = self._display_symbol(item.get('symbol'))
                normalized_orders.append(item)
            return normalized_orders
        except Exception as e:
            self.logger.error(f"오픈 주문 조회 실패: {e}")
            return []
    
    def get_trade_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
        since_ms: Optional[int] = None,
        from_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            sym = self._normalize_symbol(symbol) if symbol else None
            rows, capabilities = fetch_ccxt_execution_history(
                self.exchange,
                symbol=sym,
                limit=limit,
                since_ms=since_ms,
                symbol_formatter=self._display_symbol,
            )
            self._last_execution_capabilities = capabilities
            if capabilities.get("history_source") in {"fetch_closed_orders", "fetch_orders"}:
                self.logger.info("Bybit 거래 내역 조회: 주문 내역 폴백 사용")
            return rows
        except Exception as e:
            self.logger.error(f"거래 내역 조회 실패: {e}")
            return []
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        if not self.is_connected or not self.exchange:
            return False
        try:
            self.exchange.set_leverage(leverage, self._normalize_symbol(symbol))
            return True
        except Exception as e:
            self.logger.error(f"레버리지 설정 실패: {e}")
            return False
    
    def get_leverage(self, symbol: str) -> int:
        if not self.is_connected or not self.exchange:
            return 1
        try:
            positions = self.exchange.fetch_positions()
            for pos in positions:
                if pos['symbol'] == self._normalize_symbol(symbol):
                    return pos.get('leverage', 1)
            return 1
        except Exception as e:
            self.logger.error(f"레버리지 조회 실패: {e}")
            return 1
    
    def set_margin_type(self, symbol: str, margin_type: str) -> bool:
        """마진 타입 설정 (Bybit - 방어적 레버리지 전달)
        
        Bybit는 일부 경우 레버리지 파라미터를 요구할 수 있으므로
        방어적으로 현재 레버리지를 조회하여 함께 전달합니다.
        """
        if not self.is_connected or not self.exchange:
            return False
        try:
            normalized = self._normalize_symbol(symbol)
            margin_mode = self._normalize_margin_mode(margin_type)
            
            # 방어적 코딩: 현재 레버리지 조회 시도
            try:
                current_leverage = self.get_leverage(symbol)
                if current_leverage >= 1:
                    # 레버리지 정보가 있으면 params로 전달
                    params = {'leverage': current_leverage}
                    self.exchange.set_margin_mode(margin_mode, normalized, params=params)
                else:
                    # 레버리지 정보 없으면 기본 호출
                    self.exchange.set_margin_mode(margin_mode, normalized)
            except Exception:
                # 레버리지 조회 실패 시 기본 호출로 폴백
                self.exchange.set_margin_mode(margin_mode, normalized)
            
            self.logger.info(f"Bybit 마진 타입 설정 완료: {symbol} -> {margin_mode}")
            return True
        except Exception as e:
            self.logger.error(f"마진 타입 설정 실패: {e}")
            return False
    
    def get_funding_rate(self, symbol: str) -> float:
        if not self.is_connected or not self.exchange:
            return 0.0
        try:
            if hasattr(self.exchange, "fetch_funding_rate"):
                funding_rate = self.exchange.fetch_funding_rate(self._normalize_symbol(symbol))
                return funding_rate.get('fundingRate', 0.0)
            else:
                self.logger.error("fetch_funding_rate 메서드가 지원되지 않음")
                return 0.0
        except Exception as e:
            self.logger.error(f"펀딩 수수료 조회 실패: {e}")
            return 0.0
    
    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        """24시간 티커 데이터 조회"""
        if not self.is_connected:
            return {}
        try:
            ticker = self.exchange.fetch_ticker(self._normalize_symbol(symbol))  # type: ignore
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
        if not self.is_connected or not self.exchange:
            return 0.0
        try:
            t = self.exchange.fetch_ticker(self._normalize_symbol(symbol))
            return float(t.get('last') or t.get('close') or 0.0)
        except Exception as e:
            self.logger.error(f"현재가 조회 실패: {e}")
            return 0.0

    def validate_credentials(self) -> bool:
        try:
            return self.connect()
        except Exception as e:
            self.logger.error(f"API 키 검증 실패: {e}")
            return False

    # ---- 보험 TP/SL (서버 사이드) ---------------------------------------
    def _round_price(self, symbol: str, price: float) -> float:
        try:
            if not self.exchange:
                return float(price)
            self.exchange.load_markets()  # type: ignore
            m = self.exchange.market(self._normalize_symbol(symbol))  # type: ignore
            prec = (m.get('precision') or {}).get('price', None)
            if prec is None:
                return float(price)
            q = Decimal(10) ** -Decimal(int(prec))
            return float(Decimal(price).quantize(q, rounding=ROUND_DOWN))
        except Exception:
            return float(price)

    def place_insurance_tp_sl(
        self,
        symbol: str,
        position_side: str,  # 'LONG' or 'SHORT'
        take_profit: float,
        stop_loss: float,
        quantity: Optional[float] = None,
        trigger_price_type: str = 'mark',
        **kwargs: Any
    ) -> Dict[str, Any]:
        """포지션 진입 직후 서버-사이드 TP/SL(보험) 설정.
        - Bybit ccxt는 create_order()에 takeProfit/stopLoss 트리거를 첨부하면
          내부적으로 v5 Position Trading Stop 엔드포인트로 라우팅합니다.
        - 가능한 한 포지션 수량을 사용하고, 없으면 현재 포지션 contracts를 조회해 사용합니다.
        - 실패 시 예외를 삼키지 않고 호출자에게 반환합니다(호출자 단에서 경고 처리).
        """
        if not self.is_connected or not self.exchange:
            return {'status': 'error', 'error': '연결되지 않음'}
        try:
            norm_symbol = self._normalize_symbol(symbol)
            # 수량 보정: 미지정이면 포지션에서 추론
            amt = quantity
            if amt is None:
                try:
                    positions = self.exchange.fetch_positions()  # type: ignore
                    for p in positions:
                        if p.get('symbol') == norm_symbol and float(p.get('contracts') or 0) > 0:
                            amt = float(p.get('contracts'))
                            break
                except Exception:
                    amt = None
            if amt is None:
                # 최후 폴백: 아주 작은 값(거래소에서 무시/반려될 수 있음)
                amt = 0.001

            # 가격 정밀도 라운딩
            tp_price = self._round_price(symbol, float(take_profit))
            sl_price = self._round_price(symbol, float(stop_loss))

            close_side = 'sell' if str(position_side).upper() == 'LONG' else 'buy'

            params: Dict[str, Any] = {
                # 트리거 기준: 마크 가격(지원됨)
                'triggerPriceType': str(trigger_price_type).lower(),
                # 첨부형 TP/SL 트리거
                'takeProfit': {'triggerPrice': tp_price},
                'stopLoss': {'triggerPrice': sl_price},
            }

            # create_order는 내부적으로 position trading stop으로 라우팅됨
            order = self.exchange.create_order(  # type: ignore
                symbol=norm_symbol,
                type='market',
                side=close_side,
                amount=amt,
                price=None,
                params=params,
            )
            # ccxt는 order 파싱을 수행하므로 표준 구조를 최대한 따름
            return {
                'status': 'success',
                'tp_sl': order,
                'tp_price': tp_price,
                'sl_price': sl_price,
            }
        except Exception as e:
            self.logger.error(f"Bybit 보험 TP/SL 설정 실패: {e}")
            return {'status': 'error', 'error': str(e)}
