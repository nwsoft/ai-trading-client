#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
비트겟 선물 어댑터 (CCXT 기반)
"""

import logging
from typing import Dict, List, Optional, Any
from decimal import Decimal, ROUND_DOWN
from ..interfaces.futures_exchange import FuturesExchange

class BitgetFuturesAdapter(FuturesExchange):
    """비트겟 선물 어댑터"""
    
    def __init__(self, api_key: str, secret_key: str, password: str = "", **kwargs):
        super().__init__("bitget")
        self.api_key = api_key
        self.secret_key = secret_key
        self.password = password
        self.exchange = None
        self.logger = logging.getLogger(__name__)
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO': log_event(category, msg, exchange='bitget', level=level)
    
    def connect(self) -> bool:
        try:
            import importlib
            ccxt = importlib.import_module('ccxt')
            config = {
                'apiKey': str(self.api_key) if self.api_key is not None else '',
                'secret': str(self.secret_key) if self.secret_key is not None else '',
                'password': str(self.password) if self.password is not None else '',
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',  # 선물 스왑 기본
                },
            }
            # 모든 값이 str이어야 하는 경우를 위해 dict 내에서 str 변환을 명확히 적용
            for k in ['apiKey', 'secret', 'password']:
                config[k] = str(config[k])
            self.exchange = ccxt.bitget(config)  # type: ignore
            self.exchange.load_markets()
            self.is_connected = True
            self.log_event('system', "비트겟 선물 연결 성공")
            return True
        except Exception as e:
            self.log_event('system', f"비트겟 선물 연결 실패: {e}", level='ERROR')
            return False

    def _normalize_symbol(self, symbol: Optional[str]) -> Optional[str]:
        if not symbol:
            return None
        s = str(symbol).upper().replace('-', '').replace('_', '')
        if '/' in symbol:
            return symbol if ':' in symbol else f"{symbol}:USDT"
        if s.endswith('USDT'):
            base = s[:-4]
            if base:
                return f"{base}/USDT:USDT"
        return symbol

    def _display_symbol(self, symbol: Optional[str]) -> str:
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
            return {
                'USDT': balance.get('USDT', {}).get('total', 0),
                'BTC': balance.get('BTC', {}).get('total', 0),
                'ETH': balance.get('ETH', {}).get('total', 0),
            }
        except Exception as e:
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
        if not self.is_connected or not self.exchange:
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
                msg = f"미지원 선물 심볼: {symbol} (Bitget에 {symbol} USDT 선물 없음)"
                self.log_event('system', msg, level='WARNING')
                return {'status': 'error', 'error': msg}

            # CCXT는 type: 'limit' 또는 'market', side: 'buy' 또는 'sell'만 허용
            type_literal = 'limit' if str(order_type).upper() == 'LIMIT' else 'market'
            side_literal = 'buy' if str(side).lower() == 'buy' else 'sell'
            order = self.exchange.create_order(
                symbol=norm_symbol,
                type=type_literal,
                side=side_literal,
                amount=quantity,
                price=price
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
        if not self.is_connected or not self.exchange:
            return False
        try:
            self.exchange.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            self.log_event('system', f"주문 취소 실패: {e}", level='ERROR')
            return False
    
    def get_open_orders(self, symbol: Optional[str] = None) -> Any:
        if not self.is_connected or not self.exchange:
            return []
        try:
            sym = self._normalize_symbol(symbol)
            orders = self.exchange.fetch_open_orders(sym)
            normalized_orders = []
            for o in orders:
                item = dict(o)
                item['symbol'] = self._display_symbol(item.get('symbol'))
                normalized_orders.append(item)
            return normalized_orders
        except Exception as e:
            self.logger.error(f"오픈 주문 조회 실패: {e}")
            return []
    
    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> Any:
        if not self.is_connected or not self.exchange:
            return []
        try:
            trades = self.exchange.fetch_my_trades(self._normalize_symbol(symbol), limit=limit)
            normalized_trades = []
            for t in trades:
                item = dict(t)
                item['symbol'] = self._display_symbol(item.get('symbol'))
                normalized_trades.append(item)
            return normalized_trades
        except Exception as e:
            if 'not supported' in str(e).lower() or 'unsupported' in str(e).lower():
                self.logger.info("Bitget 거래 내역 조회: fetch_my_trades 미지원")
            else:
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
        """마진 타입 설정 (Bitget - 방어적 레버리지 전달)
        
        Bitget는 일부 경우 레버리지 파라미터를 요구할 수 있으므로
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
            
            self.logger.info(f"Bitget 마진 타입 설정 완료: {symbol} -> {margin_mode}")
            return True
        except Exception as e:
            self.logger.error(f"마진 타입 설정 실패: {e}")
            return False
    
    def get_funding_rate(self, symbol: str) -> float:
        if not self.is_connected or not self.exchange:
            return 0.0
        try:
            funding_rate = self.exchange.fetch_funding_rate(self._normalize_symbol(symbol))
            return funding_rate.get('fundingRate', 0.0)
        except Exception as e:
            self.logger.error(f"펀딩 수수료 조회 실패: {e}")
            return 0.0
    
    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        """24시간 티커 데이터 조회"""
        if not self.is_connected or not self.exchange:
            return {}
        try:
            ticker = self.exchange.fetch_ticker(self._normalize_symbol(symbol))
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

    def _round_amount(self, symbol: str, amount: float) -> float:
        try:
            if not self.exchange:
                return float(amount)
            self.exchange.load_markets()  # type: ignore
            m = self.exchange.market(self._normalize_symbol(symbol))  # type: ignore
            prec = (m.get('precision') or {}).get('amount', None)
            if prec is None:
                return float(amount)
            q = Decimal(10) ** -Decimal(int(prec))
            return float(Decimal(amount).quantize(q, rounding=ROUND_DOWN))
        except Exception:
            return float(amount)

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
        """포지션 진입 직후 서버-사이드 TP/SL(보험) 설정 (Bitget).
        - Bitget ccxt는 create_order()에 takeProfitPrice/stopLossPrice를 각각 전달하면 TPSL 플랜 주문을 생성합니다.
        - 한 번 호출로 TP/SL을 동시 등록하기 어려워 TP, SL을 각각 분리 호출합니다.
        - reduceOnly=True로 포지션 청산 전용으로 생성하며, posSide는 side에 따라 ccxt가 설정합니다.
        """
        if not self.is_connected or not self.exchange:
            return {'status': 'error', 'error': '연결되지 않음'}
        try:
            norm_symbol = self._normalize_symbol(symbol)

            # 수량: 미지정 시 포지션에서 추론
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
                amt = 0.001
            amt = self._round_amount(symbol, float(amt))

            # 가격 정밀도 라운딩
            tp_price = self._round_price(symbol, float(take_profit))
            sl_price = self._round_price(symbol, float(stop_loss))

            close_side = 'sell' if str(position_side).upper() == 'LONG' else 'buy'

            # 공통 파라미터
            common: Dict[str, Any] = {
                'reduceOnly': True,
            }

            # TP 플랜 주문
            tp_result = None
            try:
                tp_params = dict(common)
                tp_params['takeProfitPrice'] = tp_price
                tp_params['tpTriggerBy'] = str(trigger_price_type)
                tp_result = self.exchange.create_order(  # type: ignore
                    symbol=norm_symbol,
                    type='market',
                    side=close_side,
                    amount=amt,
                    price=None,
                    params=tp_params,
                )
            except Exception as e:
                self.logger.warning(f"Bitget TP 플랜 주문 실패(계속): {e}")
                tp_result = {'error': str(e)}

            # SL 플랜 주문
            sl_result = None
            try:
                sl_params = dict(common)
                sl_params['stopLossPrice'] = sl_price
                sl_params['slTriggerBy'] = str(trigger_price_type)
                sl_result = self.exchange.create_order(  # type: ignore
                    symbol=norm_symbol,
                    type='market',
                    side=close_side,
                    amount=amt,
                    price=None,
                    params=sl_params,
                )
            except Exception as e:
                self.logger.warning(f"Bitget SL 플랜 주문 실패(계속): {e}")
                sl_result = {'error': str(e)}

            ok_tp = isinstance(tp_result, dict) and ('id' in tp_result or 'orderId' in tp_result or not tp_result.get('error'))
            ok_sl = isinstance(sl_result, dict) and ('id' in sl_result or 'orderId' in sl_result or not sl_result.get('error'))

            status = 'success' if ok_tp or ok_sl else 'error'
            return {
                'status': status,
                'tp_order': tp_result,
                'sl_order': sl_result,
                'tp_price': tp_price,
                'sl_price': sl_price,
            }
        except Exception as e:
            self.logger.error(f"Bitget 보험 TP/SL 설정 실패: {e}")
            return {'status': 'error', 'error': str(e)}
