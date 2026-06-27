#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
증권 거래소 인터페이스
주식 및 ETF 거래를 위한 인터페이스 정의
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from .exchange_interface import ExchangeInterface, TradingType


class StockExchange(ExchangeInterface):
    """증권 거래소 인터페이스 (주식/ETF)"""
    
    def __init__(self, exchange_name: str):
        super().__init__(exchange_name, TradingType.STOCK)
        self.exchange_name = exchange_name
    
    # ===== 주식/ETF 특화 메서드 =====
    
    @abstractmethod
    def get_stock_list(self, market: str = "KOSPI") -> List[Dict[str, Any]]:
        """
        주식 목록 조회
        
        Args:
            market: 시장 구분 ("KOSPI", "KOSDAQ", "ALL")
        
        Returns:
            List[Dict]: 주식 정보 리스트
            [
                {
                    "code": "005930",  # 종목코드
                    "name": "삼성전자",  # 종목명
                    "market": "KOSPI",  # 시장 구분
                    "current_price": 75000.0,  # 현재가
                    "volume": 1000000,  # 거래량
                    ...
                }
            ]
        """
        pass
    
    @abstractmethod
    def get_etf_list(self) -> List[Dict[str, Any]]:
        """
        ETF 목록 조회
        
        Returns:
            List[Dict]: ETF 정보 리스트
            [
                {
                    "code": "069500",  # 종목코드
                    "name": "KODEX KOSPI",  # 종목명
                    "market": "ETF",  # 시장 구분
                    "current_price": 35000.0,  # 현재가
                    "base_index": "KOSPI",  # 기초지수
                    "tracking_error": 0.05,  # 추적오차
                    ...
                }
            ]
        """
        pass
    
    @abstractmethod
    def is_etf(self, symbol: str) -> bool:
        """
        ETF 여부 확인
        
        Args:
            symbol: 종목코드 (예: "069500")
        
        Returns:
            bool: ETF 여부
        """
        pass
    
    @abstractmethod
    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """
        주식/ETF 상세 정보 조회
        
        Args:
            symbol: 종목코드
        
        Returns:
            Dict: 종목 상세 정보
            {
                "code": "005930",
                "name": "삼성전자",
                "current_price": 75000.0,
                "change_rate": 1.5,  # 등락률 (%)
                "volume": 1000000,
                "market_cap": 5000000000000,  # 시가총액
                ...
            }
        """
        pass
    
    @abstractmethod
    def get_realtime_price(self, symbol: str) -> Dict[str, Any]:
        """
        실시간 시세 조회
        
        Args:
            symbol: 종목코드
        
        Returns:
            Dict: 실시간 시세 정보
            {
                "code": "005930",
                "current_price": 75000.0,
                "bid_price": 74900.0,  # 매수호가
                "ask_price": 75100.0,  # 매도호가
                "volume": 1000000,
                "timestamp": "2026-01-18 15:30:00"
            }
        """
        pass
    
    # ===== ExchangeInterface 구현 (주식/ETF용) =====
    
    def get_account_info(self) -> Dict[str, Any]:
        """계정 정보 조회 (주식 계좌 정보)"""
        return {"status": "error", "error": "not_implemented"}
    
    def get_balance(self) -> Dict[str, float]:
        """잔고 조회 (주식 계좌 잔고)"""
        return {"status": "error", "error": "not_implemented"}
    
    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        """24시간 티커 데이터 조회"""
        return {"status": "error", "error": "not_implemented"}
    
    def get_exchange_info(self) -> Dict[str, Any]:
        """거래소 정보 조회"""
        return {"status": "error", "error": "not_implemented"}
    
    def get_current_price(self, symbol: str) -> float:
        """현재 가격 조회"""
        try:
            price_info = self.get_realtime_price(symbol)
            return float(price_info.get("current_price", 0.0))
        except Exception:
            return 0.0
    
    def place_order(self, symbol: str, side: str, quantity: float, 
                   price: Optional[float] = None, order_type: str = "MARKET") -> Dict[str, Any]:
        """
        주문 실행 (주식/ETF 매수/매도)
        
        Args:
            symbol: 종목코드
            side: "BUY" 또는 "SELL"
            quantity: 수량
            price: 지정가 가격 (지정가 주문인 경우)
            order_type: "MARKET" (시장가) 또는 "LIMIT" (지정가)
        
        Returns:
            Dict: 주문 결과
            {
                "status": "success",
                "order_id": "12345",
                "symbol": "005930",
                "side": "BUY",
                "quantity": 10,
                "price": 75000.0,
                ...
            }
        """
        return {"status": "error", "error": "not_implemented"}
    
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """주문 상태 조회"""
        return {"status": "error", "error": "not_implemented"}
    
    def cancel_order(self, order_id: str) -> bool:
        """주문 취소"""
        return False
    
    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """거래 내역 조회"""
        return []
