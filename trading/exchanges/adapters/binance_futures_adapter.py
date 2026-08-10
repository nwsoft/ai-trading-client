#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""바이낸스 선물 어댑터 (python-binance 기반)."""

import logging
from typing import Dict, List, Optional, Any
from ..interfaces.futures_exchange import FuturesExchange
from api.binance_client import BinanceClient, BinanceConfig

class BinanceFuturesAdapter(FuturesExchange):
    """바이낸스 선물 어댑터 (python-binance 기반)"""
    supports_order_request = True

    def __init__(self, api_key: str, secret_key: str, **kwargs):
        super(BinanceFuturesAdapter, self).__init__("binance")
        self.api_key = api_key
        self.secret_key = secret_key
        self.testnet = kwargs.get('testnet', False)
        self.logger = logging.getLogger(__name__)
        self.last_error: str = ""
        self.last_auth_guidance: str = ""
        
        # 🔥 로그 시스템 통일을 위한 헬퍼 메서드
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO': log_event(category, msg, exchange='binance', level=level)
        self.is_connected = False
        self.client: Optional[BinanceClient] = None
    
    def connect(self) -> bool:
        if not self.api_key or not self.secret_key:
            self.last_error = "missing_credentials"
            self.last_auth_guidance = "바이낸스 API 키와 시크릿을 모두 입력하세요."
            return False
        try:
            if self.client is None:
                cfg = BinanceConfig(api_key=self.api_key or "", secret_key=self.secret_key or "", testnet=self.testnet)
                self.client = BinanceClient(cfg)
            self.is_connected = True
            self.last_error = ""
            self.last_auth_guidance = ""
            self.log_event('system', "바이낸스 선물 연결 성공 (python-binance)")
            return True
        except Exception as e:
            self.last_error = str(e)
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
            self.last_error = str(e)
            self.log_event('system', f"바이낸스 잔고 조회 실패: {e}", level='ERROR')
            return {}

    def get_account_info(self) -> Dict[str, Any]:
        """계정 정보 조회 (ExchangeManager 공통 경로 호환)"""
        if not self.is_connected or not self.client:
            return {}
        try:
            info = self.client.get_account_info()
            if isinstance(info, dict) and info:
                return info
            self.last_error = "account_info_empty"
            return {}
        except Exception as e:
            self.last_error = str(e)
            self.log_event('system', f"바이낸스 계정 정보 조회 실패: {e}", level='ERROR')
            return {}
    
    def get_positions(self) -> List[Dict[str, Any]]:
        if not self.is_connected or not self.client:
            return []
        try:
            return [
                dict(vars(position)) if hasattr(position, '__dict__') else dict(position)
                for position in self.client.get_positions()
            ]
        except Exception as e:
            self.last_error = str(e)
            self.log_event('system', f"바이낸스 포지션 조회 실패: {e}", level='ERROR')
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
        if not self.is_connected or not self.client:
            return []
        try:
            return self.client.get_open_orders(symbol or '')
        except Exception as e:
            self.last_error = str(e)
            self.log_event('system', f"바이낸스 미체결 주문 조회 실패: {e}", level='ERROR')
            return []
    
    def get_trade_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
        since_ms: Optional[int] = None,
        from_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not self.is_connected or not self.client:
            return []
        try:
            if symbol:
                if since_ms is None and from_id is None:
                    return self.client.get_trade_history(symbol, limit)
                try:
                    return self.client.get_trade_history(
                        symbol, limit, since_ms=since_ms, from_id=from_id
                    )
                except TypeError:
                    return self.client.get_trade_history(symbol, limit)
            if since_ms is None and from_id is None:
                return self.client.get_recent_trades('', limit)
            try:
                return self.client.get_recent_trades(
                    '', limit, since_ms=since_ms, from_id=from_id
                )
            except TypeError:
                return self.client.get_recent_trades('', limit)
        except Exception as e:
            self.last_error = str(e)
            self.log_event('system', f"바이낸스 거래내역 조회 실패: {e}", level='ERROR')
            return []
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        if not self.is_connected or not self.client:
            return False
        return self.client.set_leverage(symbol, leverage)
    
    def get_leverage(self, symbol: str) -> int:
        if not self.is_connected or not self.client:
            return 1
        normalized = str(symbol or '').upper().replace('/', '').split(':', 1)[0]
        for position in self.client.get_positions():
            if str(getattr(position, 'symbol', '')).upper() == normalized:
                return int(getattr(position, 'leverage', 1) or 1)
        return 1
    
    def set_margin_type(self, symbol: str, margin_type: str) -> bool:
        if not self.is_connected or not self.client:
            return False
        normalized = 'CROSSED' if str(margin_type).upper().startswith('CROSS') else 'ISOLATED'
        return self.client.set_margin_type(symbol, normalized)
    
    def get_funding_rate(self, symbol: str) -> float:
        if not self.is_connected or not self.client:
            return 0.0
        try:
            rows = self.client.futures_funding_rate(symbol, limit=1)
            if not rows:
                return 0.0
            return float(rows[-1].get('fundingRate') or 0.0)
        except Exception as e:
            self.last_error = str(e)
            self.logger.error(f"펀딩비 조회 실패: {e}")
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
            if not self.connect() or not self.client:
                return False
            valid = bool(self.client.validate_credentials())
            if not valid:
                self.last_error = "credential_validation_failed"
            return valid
        except Exception as e:
            self.logger.error(f"API 키 검증 실패: {e}")
            return False
