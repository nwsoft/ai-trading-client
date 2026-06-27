#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX 선물 어댑터 (CCXT 기반)
"""

import logging
from typing import Dict, List, Optional, Any
from decimal import Decimal, ROUND_DOWN
from ..interfaces.futures_exchange import FuturesExchange

class OkxFuturesAdapter(FuturesExchange):
    """OKX 선물 어댑터"""
    
    def __init__(self, api_key: str, secret_key: str, passphrase: str, **kwargs):
        super().__init__("okx")
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.exchange = None
        self.logger = logging.getLogger(__name__)
        
        # 🔥 로그 시스템 통일을 위한 헬퍼 메서드
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO': log_event(category, msg, exchange='okx', level=level)
        self._pos_mode_cached: Optional[str] = None  # 'net' | 'hedge' | None
    
    def connect(self) -> bool:
        # API 키가 없으면 연결 시도하지 않음
        if not self.api_key or not self.secret_key or not self.passphrase:
            self.log_event('system', "OKX API 키가 설정되지 않음 - 연결 건너뜀")
            return False
            
        try:
            import importlib
            ccxt = importlib.import_module('ccxt')
            config = {
                'apiKey': str(self.api_key) if self.api_key is not None else '',
                'secret': str(self.secret_key) if self.secret_key is not None else '',
                'password': str(self.passphrase) if self.passphrase is not None else '',
                'options': {
                    'defaultType': 'swap',
                },
                'enableRateLimit': True,
            }
            self.exchange = ccxt.okx(config)  # type: ignore
            self.exchange.load_markets()
            self.is_connected = True
            self.log_event('system', "OKX 선물 연결 성공")
            
            # 🔍 계좌 모드 사전 검증 (선물 거래 가능 여부 확인)
            try:
                account_config = self.exchange.fetch_account_configuration()  # type: ignore
                account_mode = account_config.get('accountMode', 'unknown')
                
                # Simple mode인 경우 경고 (API 거래 불가)
                if account_mode and str(account_mode).lower() in ['simple', '1', 'cash']:
                    self.log_event('system', f"⚠️ OKX 계좌 모드가 '{account_mode}'로 설정되어 있습니다. 선물 거래를 위해서는 OKX 웹사이트에서 계좌 모드를 'Single-currency margin' 또는 'Multi-currency margin'으로 변경해주세요. 현재 모드에서는 API 거래가 제한될 수 있습니다.", level='WARNING')
                elif account_mode:
                    self.log_event('system', f"OKX 계좌 모드: {account_mode}")
                # 포지션 모드 캐시 시도
                try:
                    pmode = str(account_config.get('posMode') or '').lower()
                    if pmode in ('net_mode', 'net', '1'):
                        self._pos_mode_cached = 'net'
                    elif pmode in ('long_short_mode', 'longshort', 'hedge', '2'):
                        self._pos_mode_cached = 'hedge'
                except Exception:
                    pass
            except Exception as check_err:
                # 계좌 설정 조회 실패는 치명적이지 않으므로 경고만 출력
                error_msg = str(check_err).lower()
                if '51010' in error_msg or 'account mode' in error_msg:
                    self.logger.warning(
                        f"⚠️ OKX 계좌 모드 확인 실패: 계좌가 선물 거래에 적합하지 않을 수 있습니다. "
                        f"OKX 웹사이트에서 거래 설정 → 계좌 모드를 확인하고 "
                        f"'Single-currency margin' 또는 'Multi-currency margin'으로 설정해주세요. "
                        f"상세: {check_err}"
                    )
                else:
                    self.logger.debug(f"OKX 계좌 모드 확인 생략: {check_err}")
            
            return True
        except Exception as e:
            error_msg = str(e).lower()
            # 계좌 모드 관련 에러 감지
            if '51010' in error_msg or 'account mode' in error_msg:
                self.logger.error(
                    f"OKX 연결 실패: 계좌 모드가 올바르지 않습니다. "
                    f"OKX 웹사이트에서 거래 설정 → 계좌 모드를 "
                    f"'Single-currency margin' 또는 'Multi-currency margin'으로 변경해주세요. "
                    f"상세: {e}"
                )
            else:
                self.logger.error(f"OKX 선물 연결 실패: {e}")
            return False

    def _detect_position_mode(self) -> str:
        """OKX 포지션 모드 감지: 'net' 또는 'hedge' 반환 (실패 시 'net').
        - 우선 캐시 사용, 없으면 fetch_positions의 info.posSide/pos 값으로 유추
        """
        if self._pos_mode_cached in ('net', 'hedge'):
            return self._pos_mode_cached  # type: ignore
        try:
            if not self.exchange:
                return 'net'
            positions = self.exchange.fetch_positions()  # type: ignore
            pos_sides = set()
            for p in positions or []:
                try:
                    info = p.get('info', {}) if isinstance(p, dict) else {}
                    ps = str(info.get('posSide') or '').lower()
                    if ps in ('long', 'short'):
                        pos_sides.add(ps)
                except Exception:
                    continue
            # 롱/숏 둘 다 관측되면 hedge로 간주
            if 'long' in pos_sides or 'short' in pos_sides:
                # 일부 계정은 포지션 없으면 빈값이므로, 하나만 있어도 헤지 모드로 간주
                self._pos_mode_cached = 'hedge'
                return 'hedge'
            self._pos_mode_cached = 'net'
            return 'net'
        except Exception:
            self._pos_mode_cached = 'net'
            return 'net'

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
            self.logger.error(f"잔고 조회 실패: {e}")
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
            self.logger.error(f"계정 정보 조회 실패: {e}")
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
            self.logger.error(f"포지션 조회 실패: {e}")
            return []
    
    def place_order(self, symbol: str, side: str, quantity: float, 
                   price: Optional[float] = None, order_type: str = "MARKET") -> Dict[str, Any]:
        if not self.is_connected:
            return {'status': 'error', 'error': '연결되지 않음'}
        try:
            # 심볼 정규화 및 선물 마켓 존재 여부 확인 (예: OKX는 XMR/USDT 선물 미지원)
            normalized = self._normalize_symbol(symbol)
            try:
                markets = getattr(self.exchange, 'markets', None) or {}
                if not markets:
                    self.exchange.load_markets()  # type: ignore
                    markets = getattr(self.exchange, 'markets', {})
            except Exception:
                markets = {}
            if not normalized or normalized not in markets:
                msg = f"미지원 선물 심볼: {symbol} (OKX에 {symbol} USDT 선물 없음)"
                self.logger.warning(msg)
                return {'status': 'error', 'error': msg}

            # 🔥 최소 주문 수량 검증 (강제 조정 비활성화)
            # 🔥 단일 권위 원칙: Optimizer에서 수량 결정 완료
            ENABLE_FORCE_ADJUSTMENT = False
            
            if ENABLE_FORCE_ADJUSTMENT:
                # 기존 강제 조정 로직 (비활성화됨)
                try:
                    market_info = self.exchange.market(normalized)  # type: ignore
                    min_amount = market_info.get('limits', {}).get('amount', {}).get('min', 0)
                    
                    # 🔥 최소 수량이 설정되어 있고 현재 수량이 미달하는 경우
                    if min_amount and quantity < min_amount:
                        self.logger.warning(f"{symbol} 최소 주문 수량 미달: {quantity} < {min_amount}")
                        
                        # 🔥 최소 수량으로 강제 조정
                        quantity = min_amount
                        self.logger.info(f"{symbol} 최소 주문 수량으로 조정: {quantity}")
                        
                        # 🔥 추가 검증: 최소 노셔널도 확인
                        try:
                            current_price = self.get_current_price(symbol)
                            if current_price > 0:
                                notional_value = quantity * current_price
                                min_notional = 5.0  # 기본 최소 노셔널
                                
                                if notional_value < min_notional:
                                    # 최소 노셔널을 충족하는 수량으로 재조정
                                    required_quantity = min_notional / current_price
                                    # 최소 수량보다 크면 최소 수량으로, 작으면 required_quantity로
                                    quantity = max(min_amount, required_quantity)
                                    self.logger.info(f"{symbol} 최소 노셔널 충족을 위한 수량 조정: {quantity} (노셔널: {quantity * current_price:.2f} USDT)")
                        except Exception as price_e:
                            self.logger.warning(f"가격 조회 실패, 최소 수량만 적용: {price_e}")
                except Exception:
                    pass
            else:
                # 🔥 검증만 수행: 최소 수량 미달 시 거래 건너뛰기
                try:
                    market_info = self.exchange.market(normalized)  # type: ignore
                    min_amount = market_info.get('limits', {}).get('amount', {}).get('min', 0)
                    
                    if min_amount and quantity < min_amount:
                        self.logger.warning(f"{symbol} 최소 주문 수량 미달 검증: {quantity} < {min_amount}")
                        self.logger.info(f"{symbol} 💡 해결방법: Optimizer에서 수량을 {min_amount} 이상으로 설정 필요")
                        return {'status': 'error', 'error': f'Minimum quantity not met: {quantity} < {min_amount}'}
                    
                    # 최소 노셔널 검증
                    try:
                        current_price = self.get_current_price(symbol)
                        if current_price > 0:
                            notional_value = quantity * current_price
                            min_notional = 5.0  # 기본 최소 노셔널
                            
                            if notional_value < min_notional:
                                self.logger.warning(f"{symbol} 최소 노셔널 미달 검증: {notional_value:.2f} < {min_notional} USDT")
                                self.logger.info(f"{symbol} 💡 해결방법: Optimizer에서 수량을 {min_notional/current_price:.6f} 이상으로 설정 필요")
                                return {'status': 'error', 'error': f'Minimum notional not met: {notional_value:.2f} < {min_notional} USDT'}
                    except Exception as price_e:
                        self.logger.warning(f"가격 조회 실패, 노셔널 검증 건너뛰기: {price_e}")
                        
                except Exception as e:
                    self.logger.warning(f"최소 수량 검증 실패, 계속 진행: {e}")
            
            # 수량 정밀도 조정 (프로토콜 포맷팅만)
            quantity = self._round_amount(symbol, quantity)

            type_literal = 'limit' if str(order_type).upper() == 'LIMIT' else 'market'
            side_literal = 'buy' if str(side).lower() == 'buy' else 'sell'

            # ✅ OKX 전용 파라미터 구성: tdMode + (hedge 모드일 때만 positionSide)
            params: Dict[str, Any] = {}
            try:
                # tdMode: settings에서 기본 마진 타입을 읽거나 기본 cross
                default_margin = 'cross'
                try:
                    # settings를 통한 주입을 고려: self.settings가 없을 수 있어 보호
                    default_margin = str(getattr(self, 'settings', {}).get('default_margin_type', 'CROSS')).lower()
                except Exception:
                    pass
                params['marginMode'] = 'cross' if default_margin.startswith('cross') else 'isolated'

                pos_mode = self._detect_position_mode()
                if pos_mode == 'hedge':
                    # hedge 모드에서는 파생상품 주문에 posSide 필수
                    params['positionSide'] = 'long' if side_literal == 'buy' else 'short'
            except Exception:
                pass

            order = self.exchange.create_order(  # type: ignore
                symbol=normalized, type=type_literal, side=side_literal,
                amount=quantity, price=price, params=params
            )
            return {
                'status': 'success',
                'order_id': order.get('id'),
                'symbol': order.get('symbol'),
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
            error_msg = str(e)
            # 🔥 OKX 특화 오류 메시지 처리
            if "account mode" in error_msg.lower() or "51010" in error_msg:
                self.logger.error(f"OKX 계좌 모드 오류: {error_msg}")
                return {'status': 'error', 'error': 'OKX 계좌 모드를 Single-currency margin 또는 Multi-currency margin으로 변경해주세요'}
            elif "minimum amount" in error_msg.lower() or "precision" in error_msg.lower():
                self.logger.error(f"OKX 최소 주문 수량 오류: {error_msg}")
                return {'status': 'error', 'error': f'{symbol} 최소 주문 수량을 확인해주세요'}
            else:
                self.logger.error(f"주문 실행 실패: {e}")
                return {'status': 'error', 'error': str(e)}
    
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        if not self.is_connected or not self.exchange:
            return False
        try:
            self.exchange.cancel_order(order_id, symbol)  # type: ignore
            return True
        except Exception as e:
            self.logger.error(f"주문 취소 실패: {e}")
            return False
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.is_connected or not self.exchange:
            return []
        try:
            orders = self.exchange.fetch_open_orders(self._normalize_symbol(symbol))  # type: ignore
            def decode_dict(d):
                return {k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in dict(d).items()}
            normalized_orders = []
            for o in orders:
                item = decode_dict(o)
                item['symbol'] = self._display_symbol(item.get('symbol'))
                normalized_orders.append(item)
            return normalized_orders
        except Exception as e:
            self.logger.error(f"오픈 주문 조회 실패: {e}")
            return []
    
    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.is_connected or not self.exchange:
            return []
        try:
            trades = self.exchange.fetch_my_trades(self._normalize_symbol(symbol), limit=limit)  # type: ignore
            def decode_dict(d):
                return {k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in dict(d).items()}
            normalized_trades = []
            for t in trades:
                item = decode_dict(t)
                item['symbol'] = self._display_symbol(item.get('symbol'))
                normalized_trades.append(item)
            return normalized_trades
        except Exception as e:
            if 'not supported' in str(e).lower() or 'unsupported' in str(e).lower():
                self.logger.info("OKX 거래 내역 조회: fetch_my_trades 미지원")
            else:
                self.logger.error(f"거래 내역 조회 실패: {e}")
            return []
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        if not self.is_connected or not self.exchange:
            return False
        try:
            norm = self._normalize_symbol(symbol)
            params: Dict[str, Any] = {}
            try:
                if self._detect_position_mode() == 'hedge':
                    # OKX는 헤지 모드에서 posSide를 요구하는 경우가 많음 → 양쪽 설정을 시도
                    # 우선 long에 대해 설정, 실패 시 short도 시도
                    ok = False
                    try:
                        params_long = {'positionSide': 'long'}
                        self.exchange.set_leverage(leverage, norm, params=params_long)  # type: ignore
                        ok = True
                    except Exception:
                        pass
                    try:
                        params_short = {'positionSide': 'short'}
                        self.exchange.set_leverage(leverage, norm, params=params_short)  # type: ignore
                        ok = True or ok
                    except Exception:
                        pass
                    return ok
            except Exception:
                pass
            self.exchange.set_leverage(leverage, norm)  # type: ignore
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
        """마진 타입 설정 (OKX 전용: 레버리지 파라미터 필수)
        
        OKX는 마진 모드 변경 시 레버리지 정보를 필수로 요구합니다.
        현재 레버리지를 조회하여 함께 전달합니다.
        """
        if not self.is_connected or not self.exchange:
            return False
        try:
            normalized = self._normalize_symbol(symbol)
            margin_mode = self._normalize_margin_mode(margin_type)
            
            # OKX는 set_margin_mode 호출 시 레버리지 파라미터 필수
            # 현재 레버리지 조회 시도
            current_leverage = self.get_leverage(symbol)
            if current_leverage < 1:
                # 레버리지 조회 실패 시 기본값 사용 (10배)
                current_leverage = 10
                self.logger.warning(f"{symbol} 현재 레버리지 조회 실패, 기본값 {current_leverage} 사용")
            
            # OKX API는 params에 lever 전달 필요
            params: Dict[str, Any] = {'lever': int(current_leverage)}
            try:
                if self._detect_position_mode() == 'hedge':
                    # 헤지 모드에서는 posSide 지정 필요할 수 있어 양쪽 적용 시도
                    ok = False
                    try:
                        params_long = dict(params)
                        params_long['posSide'] = 'long'
                        self.exchange.set_margin_mode(margin_mode, normalized, params=params_long)  # type: ignore
                        ok = True
                    except Exception:
                        pass
                    try:
                        params_short = dict(params)
                        params_short['posSide'] = 'short'
                        self.exchange.set_margin_mode(margin_mode, normalized, params=params_short)  # type: ignore
                        ok = True or ok
                    except Exception:
                        pass
                    if ok:
                        self.logger.info(f"OKX 마진 타입(헤지) 설정 완료: {symbol} -> {margin_mode}, leverage={current_leverage}")
                        return True
            except Exception:
                pass
            self.exchange.set_margin_mode(margin_mode, normalized, params=params)  # type: ignore
            self.logger.info(f"OKX 마진 타입 설정 완료: {symbol} -> {margin_mode}, leverage={current_leverage}")
            return True
        except Exception as e:
            error_msg = str(e).lower()
            # OKX 계정 모드 문제 감지 (51010 에러)
            if '51010' in error_msg or 'account mode' in error_msg:
                self.logger.error(
                    f"마진 타입 설정 실패: OKX 계좌 모드가 선물 거래에 적합하지 않습니다. "
                    f"OKX 웹사이트에서 계좌 설정을 'Single-currency margin' 또는 'Multi-currency margin' 모드로 변경해주세요. "
                    f"상세 오류: {e}"
                )
            else:
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
        margin_mode: str = 'cross',
        **kwargs: Any
    ) -> Dict[str, Any]:
        """포지션 진입 직후 서버-사이드 TP/SL(보험) 설정 (OKX).
        - OKX는 create_order()에 takeProfit/stopLoss를 첨부하거나 tp/slTriggerPx를 직접 지정해 포지션에 TP/SL 트리거를 붙일 수 있습니다.
        - 여기서는 ccxt 표준 파라미터(takeProfit/stopLoss) + 트리거타입(mark) + reduceOnly/positionSide/marginMode를 사용합니다.
        """
        if not self.is_connected or not self.exchange:
            return {'status': 'error', 'error': '연결되지 않음'}
        try:
            norm_symbol = self._normalize_symbol(symbol)
            # 수량: 미지정 시 포지션 contracts에서 추론
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
            pos_side = 'long' if str(position_side).upper() == 'LONG' else 'short'

            # ✅ OKX 파라미터: tdMode 명시, hedge 모드일 때만 positionSide 포함
            params: Dict[str, Any] = {
                'reduceOnly': True,
                'marginMode': str(margin_mode),  # 호환 목적
                'tdMode': 'cross' if str(margin_mode).lower().startswith('cross') else 'isolated',
                # 트리거타입 지정(마크가격 기준)
                'tpTriggerPxType': str(trigger_price_type),
                'slTriggerPxType': str(trigger_price_type),
                # 조건부 트리거(시장 청산)
                'tpTriggerPx': tp_price,
                'tpOrdPx': '-1',
                'slTriggerPx': sl_price,
                'slOrdPx': '-1',
            }

            try:
                if self._detect_position_mode() == 'hedge':
                    params['positionSide'] = pos_side  # hedge에서만 지정
            except Exception:
                pass

            order = self.exchange.create_order(  # type: ignore
                symbol=norm_symbol,
                type='conditional',
                side=close_side,
                amount=amt,
                price=None,
                params=params,
            )

            return {
                'status': 'success',
                'tp_sl': order,
                'tp_price': tp_price,
                'sl_price': sl_price,
            }
        except Exception as e:
            self.logger.error(f"OKX 보험 TP/SL 설정 실패: {e}")
            return {'status': 'error', 'error': str(e)}
