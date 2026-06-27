#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
통합 거래 매니저
"""

import logging
from typing import Dict, List, Optional, Any
from .exchanges.exchange_factory import ExchangeFactory
from .exchanges.interfaces.exchange_interface import ExchangeInterface
from .execution_optimizer import ExecutionOptimizer

class UnifiedTradingManager:
    """통합 거래 매니저"""
    
    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings
        self.logger = logging.getLogger(__name__)
        self.exchanges = {}
        self._initialize_exchanges()

    def _get_enabled_exchange_set(self) -> set:
        enabled_set = set()
        try:
            raw_enabled = self.settings.get('enabled_exchanges', []) if isinstance(self.settings, dict) else []
            for item in raw_enabled or []:
                name = str(item).strip().lower()
                if name:
                    enabled_set.add(name)
        except Exception:
            enabled_set = set()

        if not enabled_set:
            fallback = str(self.settings.get('selected_exchange', 'binance')).strip().lower()
            if fallback:
                enabled_set.add(fallback)
        return enabled_set

    def _initialize_exchanges(self):
        """거래소 초기화"""
        # 설정에서 활성화된 거래소만 초기화 (API 키 유효성 + enabled_exchanges 동시 만족)
        enabled = self._get_enabled_exchange_set()
        # 선물 거래소들
        futures_exchanges = ['binance', 'bybit', 'okx', 'bitget']
        for exchange_name in futures_exchanges:
            if (not enabled or exchange_name in enabled) and self._has_valid_api_keys(exchange_name):
                try:
                    exchange = ExchangeFactory.create_futures_exchange(exchange_name, self.settings)
                    if exchange and exchange.connect():
                        self.exchanges[f"{exchange_name}_futures"] = exchange
                        self.logger.info(f"{exchange_name} 선물 거래소 초기화 완료")
                except Exception as e:
                    self.logger.error(f"{exchange_name} 선물 거래소 초기화 실패: {e}")
        
        # 현물 거래소들
        spot_exchanges = ['upbit', 'bithumb']
        for exchange_name in spot_exchanges:
            if (not enabled or exchange_name in enabled) and self._has_valid_api_keys(exchange_name):
                try:
                    exchange = ExchangeFactory.create_spot_exchange(exchange_name, self.settings)
                    if exchange and exchange.connect():
                        self.exchanges[f"{exchange_name}_spot"] = exchange
                        self.logger.info(f"{exchange_name} 현물 거래소 초기화 완료")
                except Exception as e:
                    self.logger.error(f"{exchange_name} 현물 거래소 초기화 실패: {e}")
    
    def _has_valid_api_keys(self, exchange_name: str) -> bool:
        """API 키 유효성 확인 (거래소별 요구사항 반영)"""
        name = str(exchange_name or '').strip().lower()
        api_key = self.settings.get(f'{name}_api_key', '')
        secret_key = self.settings.get(f'{name}_secret_key', '')
        if not (api_key and secret_key):
            return False
        # 추가 요구 사항
        if name == 'okx':
            return bool(self.settings.get('okx_passphrase'))
        if name == 'bitget':
            return bool(self.settings.get('bitget_password'))
        return True
    
    def get_exchange(self, exchange_name: str, trading_type: str) -> Optional[ExchangeInterface]:
        """거래소 가져오기"""
        key = f"{exchange_name}_{trading_type}"
        return self.exchanges.get(key)
    
    def get_all_balances(self) -> Dict[str, Dict[str, float]]:
        """활성화된 거래소의 잔고만 조회 (비활성 거래소 에러 방지)"""
        balances = {}
        enabled_exchanges = self._get_enabled_exchange_set()
        
        for key, exchange in self.exchanges.items():
            # 키에서 거래소명 추출 (예: binance_futures -> binance)
            exchange_base = key.split('_')[0]
            
            # 활성화된 거래소만 조회
            if exchange_base not in enabled_exchanges:
                continue
                
            try:
                balance = exchange.get_balance()
                balances[key] = balance
            except Exception as e:
                self.logger.error(f"{key} 잔고 조회 실패: {e}")
                balances[key] = {}
        return balances
    
    def get_all_positions(self) -> Dict[str, List[Dict[str, Any]]]:
        """활성화된 선물 거래소의 포지션만 조회 (비활성 거래소 에러 방지)"""
        positions = {}
        enabled_exchanges = self._get_enabled_exchange_set()
        
        for key, exchange in self.exchanges.items():
            if key.endswith('_futures'):
                # 키에서 거래소명 추출 (예: binance_futures -> binance)
                exchange_base = key.split('_')[0]
                
                # 활성화된 거래소만 조회
                if exchange_base not in enabled_exchanges:
                    continue
                    
                try:
                    pos = exchange.get_positions()
                    positions[key] = pos
                except Exception as e:
                    self.logger.error(f"{key} 포지션 조회 실패: {e}")
                    positions[key] = []
        return positions
    
    def place_order_unified(self, exchange_name: str, trading_type: str, symbol: str,
        side: str, quantity: float, price: Optional[float] = None,
        order_type: str = "MARKET") -> Dict[str, Any]:
        """통합 주문 실행 (거래소별 안전 분기, 모든 거래소 정상 동작 보장)"""
        exchange = self.get_exchange(exchange_name, trading_type)
        if not exchange:
            return {'error': f'{exchange_name} {trading_type} 거래소를 찾을 수 없습니다', 'status': 'failed'}

        try:
            # 바이낸스만 OrderRequest 방식, 나머지는 파라미터 방식
            if exchange_name.lower() == 'binance' and hasattr(exchange, 'place_order'):
                # Binance 네이티브: 대문자 규약으로 정규화 (CCXT와 다름)
                from api.binance_client import OrderRequest
                side_up = str(side).upper() if isinstance(side, str) else side
                ot_up = str(order_type).upper() if isinstance(order_type, str) else order_type
                order_req = OrderRequest(
                    symbol=symbol,
                    side=side_up,              # BUY/SELL
                    order_type=ot_up,          # MARKET/LIMIT/...
                    quantity=quantity,
                    price=price
                )
                result = exchange.place_order(order_req)
            elif hasattr(exchange, 'place_order'):
                result = exchange.place_order(symbol, side, quantity, price, order_type)
            else:
                return {'error': '지원하지 않는 거래소 타입 또는 place_order 미구현', 'status': 'failed'}

            # 결과 통일
            if result and ('id' in result or 'order_id' in result):
                # 안전 매핑: 바이낸스 네이티브 결과(avg_price/executed_qty) 포함 처리
                mapped_price = result.get('price', None)
                if mapped_price in (None, ''):
                    mapped_price = result.get('avg_price', None)
                mapped_qty = result.get('amount', None)
                if mapped_qty in (None, ''):
                    mapped_qty = result.get('quantity', None)
                if mapped_qty in (None, ''):
                    mapped_qty = result.get('executed_qty', quantity)
                mapped_type = result.get('type', None) or order_type
                return {
                    'status': 'success',
                    'order_id': result.get('id', result.get('order_id')),
                    'symbol': result.get('symbol', symbol),
                    'side': result.get('side', side),
                    'quantity': mapped_qty,
                    'price': mapped_price,
                    'order_type': mapped_type,
                    'timestamp': result.get('timestamp'),
                    'raw_result': result
                }
            else:
                # 원인 전달: 하위에서 error를 제공했다면 그대로 전달
                if isinstance(result, dict) and result.get('error'):
                    return {'error': result.get('error'), 'status': 'failed'}
                return {'error': '주문 실행 결과가 올바르지 않음', 'status': 'failed'}

        except Exception as e:
            self.logger.error(f"통합 주문 실행 실패: {e}")
            return {'error': str(e), 'status': 'failed'}

    def place_order_with_quality_control(
        self,
        exchange_name: str,
        trading_type: str,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: str = "MARKET",
        policy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """재시도/타임아웃/슬리피지 상한을 적용한 공통 주문 실행."""
        effective = dict(policy or {})
        if not bool(effective.get('enabled', False)):
            result = self.place_order_unified(exchange_name, trading_type, symbol, side, quantity, price, order_type)
            result.setdefault('latency_ms', 0.0)
            result.setdefault('slippage_bps', 0.0)
            result.setdefault('errors', [])
            return result

        optimizer = ExecutionOptimizer()
        chosen_order_type = optimizer.choose_order_type(
            preferred=order_type,
            signal_strength=float(effective.get('signal_strength', 0.5) or 0.5),
            volatility=float(effective.get('volatility', 0.02) or 0.02),
            spread_bps=float(effective.get('spread_bps', 10.0) or 10.0),
        )

        success, result, errors, latency_ms, slippage_bps = optimizer.execute_with_quality_control(
            place_order_fn=lambda dyn_order_type, dyn_price: self._place_order_quality_once(
                exchange_name=exchange_name,
                trading_type=trading_type,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=dyn_price,
                order_type=dyn_order_type,
            ),
            order_type=chosen_order_type,
            request_price=price,
            fallback_market=bool(effective.get('fallback_market', True)),
            max_retries=max(0, int(effective.get('max_retries', 1) or 1)),
            timeout_ms=max(300, int(effective.get('timeout_ms', 3000) or 3000)),
            max_slippage_bps=max(0.1, float(effective.get('max_slippage_bps', 35.0) or 35.0)),
        )
        payload = dict(result or {})
        payload['status'] = 'success' if success else str(payload.get('status') or 'failed')
        payload['latency_ms'] = latency_ms
        payload['slippage_bps'] = slippage_bps
        payload['errors'] = errors
        payload['order_type'] = payload.get('order_type') or chosen_order_type
        return payload

    def _place_order_quality_once(
        self,
        exchange_name: str,
        trading_type: str,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float],
        order_type: str,
    ) -> tuple[bool, Dict[str, Any], List[str]]:
        result = self.place_order_unified(exchange_name, trading_type, symbol, side, quantity, price, order_type)
        status = str((result or {}).get('status') or '').strip().lower()
        success = status == 'success'
        errors = [] if success else [str((result or {}).get('error') or 'order_failed')]
        return success, (result if isinstance(result, dict) else {}), errors
    
    def get_exchange_balance(self, exchange_name: str, trading_type: str) -> Dict[str, Any]:
        """특정 거래소 잔고 조회"""
        exchange = self.get_exchange(exchange_name, trading_type)
        if not exchange:
            return {'error': f'{exchange_name} {trading_type} 거래소를 찾을 수 없습니다'}
        
        try:
            balance = exchange.get_balance()
            return {
                'exchange': f"{exchange_name}_{trading_type}",
                'balance': balance,
                'status': 'success'
            }
        except Exception as e:
            self.logger.error(f"{exchange_name} {trading_type} 잔고 조회 실패: {e}")
            return {'error': str(e), 'status': 'error'}
    
    def get_supported_exchanges(self) -> Dict[str, List[str]]:
        """지원하는 거래소 목록 반환"""
        return ExchangeFactory.get_supported_exchanges()
    
    def get_connected_exchanges(self) -> List[str]:
        """연결된 거래소 목록 반환"""
        return list(self.exchanges.keys())

    # ---- 런타임 재초기화/재연결 지원 ----
    def reload_settings(self, new_settings: Dict[str, Any]) -> None:
        """설정 변경 시 설정 갱신 및 재초기화"""
        try:
            self.settings = new_settings
            self.logger.info("UnifiedTradingManager 설정 갱신")
            self._reinitialize()
        except Exception as e:
            self.logger.error(f"UnifiedTradingManager 설정 재로드 실패: {e}")

    def _reinitialize(self) -> None:
        """모든 연결을 재구성 (간단히 재생성)"""
        try:
            self.exchanges.clear()
            self._initialize_exchanges()
            self.logger.info("UnifiedTradingManager 재초기화 완료")
        except Exception as e:
            self.logger.error(f"UnifiedTradingManager 재초기화 실패: {e}")

    def refresh_exchange(self, exchange_name: str) -> bool:
        """특정 거래소만 재연결(가능 시)"""
        try:
            # enabled_exchanges에 없는 거래소는 재연결하지 않음
            enabled = self._get_enabled_exchange_set()
            if enabled and exchange_name not in enabled:
                self.logger.info(f"{exchange_name}는 비활성화되어 있어 재연결을 건너뜁니다")
                # 기존 연결 제거만 수행
                self.exchanges.pop(f"{exchange_name}_futures", None)
                self.exchanges.pop(f"{exchange_name}_spot", None)
                return False
            updated = False
            for t in ("futures", "spot"):
                key = f"{exchange_name}_{t}"
                if key in self.exchanges:
                    # 기존 것을 제거하고 재생성
                    self.exchanges.pop(key, None)
                if (t == 'futures' and exchange_name in ['binance', 'bybit', 'okx', 'bitget']) \
                or (t == 'spot' and exchange_name in ['upbit', 'bithumb']):
                    if self._has_valid_api_keys(exchange_name):
                        try:
                            if t == 'futures':
                                ex = ExchangeFactory.create_futures_exchange(exchange_name, self.settings)
                            else:
                                ex = ExchangeFactory.create_spot_exchange(exchange_name, self.settings)
                            if ex and ex.connect():
                                self.exchanges[key] = ex
                                updated = True
                                self.logger.info(f"{key} 재연결 완료")
                        except Exception as e:
                            self.logger.error(f"{key} 재연결 실패: {e}")
            return updated
        except Exception as e:
            self.logger.error(f"거래소 재연결 오류: {e}")
            return False
