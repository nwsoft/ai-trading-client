#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
거래소 공통 인터페이스
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from enum import Enum

class TradingType(Enum):
    FUTURES = "futures"
    SPOT = "spot"
    STOCK = "stock"  # 주식/ETF 거래 타입

class ExchangeInterface(ABC):
    """거래소 공통 인터페이스"""
    
    def __init__(self, exchange_name: str, trading_type: TradingType):
        self.exchange_name = exchange_name
        self.trading_type = trading_type
        self.is_connected = False
        self.logger = None
        from trading.authenticated_execution_stream import AuthenticatedExecutionStream
        self._execution_stream = AuthenticatedExecutionStream(exchange_name)
    
    @abstractmethod
    def connect(self) -> bool:
        """거래소 연결"""
        pass
    
    @abstractmethod
    def get_balance(self) -> Dict[str, float]:
        """잔고 조회"""
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """포지션 조회 (선물만)"""
        pass
    
    @abstractmethod
    def place_order(self, *args, **kwargs) -> Dict[str, Any]:
        """
        - CCXT: place_order(symbol, side, quantity, price=None, order_type='MARKET')
        - Binance: place_order(order_request: OrderRequest)
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        """주문 취소"""
        pass

    @abstractmethod
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """오픈 주문 조회"""
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

    def get_execution_capabilities(self) -> Dict[str, Any]:
        """과거 체결 API 미지원과 실제 무거래를 구분하는 기능 계약."""
        try:
            from ..execution_history import build_execution_capabilities
            detected = build_execution_capabilities(getattr(self, "exchange", None))
            last = getattr(self, "_last_execution_capabilities", None)
            if isinstance(last, dict):
                detected.update(last)
            return detected
        except Exception:
            return {
                "live_order_receipt": True,
                "historical_trades": False,
                "closed_orders_fallback": False,
                "manual_trade_backfill": False,
                "history_available": False,
                "history_reason": "capability_detection_failed",
            }

    def ingest_authenticated_execution_event(self, event: Dict[str, Any]) -> bool:
        """거래소 SDK의 인증 주문/체결 콜백을 공통 원장 큐에 넣는다."""
        return bool(self._execution_stream.push(event))

    def mark_execution_stream_connected(self) -> None:
        self._execution_stream.mark_connected()

    def mark_execution_stream_disconnected(self, reason: str) -> None:
        self._execution_stream.mark_disconnected(reason)

    def drain_execution_events(self, limit: int = 200) -> List[Dict[str, Any]]:
        return self._execution_stream.drain_execution_events(limit=limit)

    def execution_stream_healthy(self) -> bool:
        return self._execution_stream.execution_stream_healthy()

    def get_execution_stream_capabilities(self) -> Dict[str, Any]:
        """공개 시세 WS와 인증 체결 스트림을 혼동하지 않는 명시 계약."""
        return {
            "authenticated_private_stream": True,
            "adapter_callback_bound": bool(self._execution_stream.status().get("connected")),
            "rest_incremental_recovery": True,
            "market_data_stream_is_not_execution_stream": True,
        }
    
    @abstractmethod
    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        """24시간 티커 데이터 조회"""
        pass

    # 선택 기능: 서버-사이드 보험 TP/SL 설정 (선물 전용 어댑터가 오버라이드)
    def place_insurance_tp_sl(
        self,
        symbol: str,
        position_side: str,
        take_profit: float,
        stop_loss: float,
        quantity: Optional[float] = None,
        trigger_price_type: str = 'mark',
        **kwargs: Any
    ) -> Dict[str, Any]:
        return {"status": "error", "error": "not_supported"}
