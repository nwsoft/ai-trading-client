#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
바이낸스 선물 어댑터 (python-binance 기반으로 변경 필요, CCXT 사용 금지)
"""

import logging
from typing import Dict, List, Optional, Any
from ..interfaces.futures_exchange import FuturesExchange
from api.binance_client import BinanceClient, BinanceConfig

class BinanceFuturesAdapter(FuturesExchange):
    """바이낸스 선물 어댑터 (python-binance 기반)"""
    supports_order_request = False

    def __init__(self, api_key: str, secret_key: str, **kwargs):
        super(BinanceFuturesAdapter, self).__init__("binance")
        self.api_key = api_key
        self.secret_key = secret_key
        self.testnet = kwargs.get('testnet', False)
        self.logger = logging.getLogger(__name__)
        
        # 🔥 로그 시스템 통일을 위한 헬퍼 메서드
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO': log_event(category, msg, exchange='binance', level=level)
        self.is_connected = False
        self.client: Optional[BinanceClient] = None
    
    def connect(self) -> bool:
        try:
            cfg = BinanceConfig(api_key=self.api_key or "", secret_key=self.secret_key or "", testnet=self.testnet)
            self.client = BinanceClient(cfg)
            # 가벼운 호출로 유효성 확인 (공개 엔드포인트도 가능하지만, 키 검증 위해 계정정보 시도)
            try:
                _ = self.client.get_account_info()
            except Exception:
                # 계정 호출 실패해도 클라이언트는 유지 (잔고 조회 시 최종 판별)
                pass
            self.is_connected = True
            self.log_event('system', "바이낸스 선물 연결 성공 (python-binance)")
            return True
        except Exception as e:
            self.log_event('system', f"바이낸스 연결 실패: {e}", level='ERROR')
            self.is_connected = False
            return False
    
    def get_balance(self) -> Dict[str, float]:
        if not self.is_connected or not self.client:
            return {}
        try:
            balances = self.client.get_balance()  # 자산별 dict 반환
            # 간단화: 자산별 wallet_balance를 직접 수치로 노출 (프리뷰 호환)
            flat: Dict[str, float] = {}
            if isinstance(balances, dict):
                for asset, info in balances.items():
                    try:
                        if isinstance(info, dict):
                            wb = float(info.get('wallet_balance', info.get('walletBalance', 0)) or 0)
                            if wb > 0:
                                flat[asset] = wb
                    except Exception:
                        pass
            return flat
        except Exception as e:
            self.log_event('system', f"바이낸스 잔고 조회 실패: {e}", level='ERROR')
            return {}

    def get_account_info(self) -> Dict[str, Any]:
        """계정 정보 조회 (ExchangeManager 공통 경로 호환)"""
        if not self.is_connected or not self.client:
            return {}
        try:
            info = self.client.get_account_info()
            return info if isinstance(info, dict) else {}
        except Exception as e:
            self.log_event('system', f"바이낸스 계정 정보 조회 실패: {e}", level='ERROR')
            return {}
    
    def get_positions(self) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        # CCXT 제거, 실제 포지션 조회는 python-binance 기반으로 변경 필요
        return []
    
    def place_order(self, order_request) -> Dict[str, Any]:
        """OrderRequest 기반 주문 실행 위임"""
        try:
            if not self.is_connected or not self.client:
                return {'status': 'error', 'error': '연결되지 않음'}
            return self.client.place_order(order_request)
        except Exception as e:
            self.log_event('system', f"주문 실행 실패: {e}", level='ERROR')
            return {'status': 'error', 'error': str(e)}
    
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        try:
            if not self.is_connected or not self.client or not symbol:
                return False
            return self.client.cancel_order(symbol, int(order_id))
        except Exception as e:
            self.logger.error(f"주문 취소 실패: {e}")
            return False
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        # CCXT 코드 삭제, python-binance 기반으로 구현 필요
        return []
    
    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        # CCXT 코드 삭제, python-binance 기반으로 구현 필요
        return []
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        if not self.is_connected:
            return False
        # CCXT 코드 삭제, python-binance 기반으로 구현 필요
        return False
    
    def get_leverage(self, symbol: str) -> int:
        if not self.is_connected:
            return 1
        # CCXT 코드 삭제, python-binance 기반으로 구현 필요
        return 1
    
    def set_margin_type(self, symbol: str, margin_type: str) -> bool:
        # CCXT 코드 삭제, python-binance 기반으로 구현 필요
        return False
    
    def get_funding_rate(self, symbol: str) -> float:
        # CCXT 코드 삭제, python-binance 기반으로 구현 필요
        return 0.0
    
    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        try:
            if not self.is_connected or not self.client:
                return {}
            t = self.client.get_24h_ticker(symbol)
            return t if isinstance(t, dict) else {}
        except Exception as e:
            self.logger.error(f"24시간 티커 조회 실패: {e}")
            return {}
    
    def validate_credentials(self) -> bool:
        """API 키 유효성 검증 (다른 거래소 어댑터와 일관성 유지)
        
        ExchangeManager.validate_exchange_connection()에서 호출될 수 있음.
        다른 거래소 어댑터들의 validate_credentials()와 동일한 인터페이스를 제공하여
        모듈화된 거래소 관리 시스템과 일관성을 유지합니다.
        
        Returns:
            bool: 연결이 성공하고 API 키가 유효하면 True, 그렇지 않으면 False
        """
        try:
            # connect() 메서드를 통해 검증 (BinanceClient의 get_account_info 호출)
            return self.connect()
        except Exception as e:
            self.logger.error(f"API 키 검증 실패: {e}")
            return False