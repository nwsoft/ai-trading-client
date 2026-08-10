#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
거래소 기본 클래스
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import logging


class BaseExchange(ABC):
    """거래소 기본 클래스"""
    
    def __init__(self, api_key: str, secret_key: str, **kwargs):
        self.api_key = api_key
        self.secret_key = secret_key
        self.logger = logging.getLogger(__name__)
        self.is_connected = False
        
    @abstractmethod
    def connect(self) -> bool:
        """거래소 연결"""
        pass
        
    @abstractmethod
    def get_account_info(self) -> Dict[str, Any]:
        """계정 정보 조회"""
        pass
        
    @abstractmethod
    def get_balance(self) -> Dict[str, float]:
        """잔고 조회"""
        pass
        
    @abstractmethod
    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        """24시간 티커 데이터 조회"""
        pass
        
    @abstractmethod
    def get_exchange_info(self) -> Dict[str, Any]:
        """거래소 정보 조회"""
        pass
        
    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        """현재 가격 조회"""
        pass
        
    @abstractmethod
    def place_order(self, symbol: str, side: str, quantity: float, 
                   price: Optional[float] = None, order_type: str = "MARKET") -> Dict[str, Any]:
        """주문 실행"""
        pass
        
    @abstractmethod
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """주문 상태 조회"""
        pass
        
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """주문 취소"""
        pass
        
    @abstractmethod
    def get_trade_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
        since_ms: Optional[int] = None,
        from_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """거래 내역 조회"""
        pass
        
    def validate_credentials(self) -> bool:
        """API 키 유효성 검증"""
        try:
            return self.connect()
        except Exception as e:
            self.logger.error(f"API 키 검증 실패: {e}")
            return False
            
    def get_exchange_name(self) -> str:
        """거래소 이름 반환"""
        return self.__class__.__name__.replace('Client', '').lower()
