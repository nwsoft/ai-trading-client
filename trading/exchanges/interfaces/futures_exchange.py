#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
선물 거래소 인터페이스
"""

from abc import abstractmethod
from typing import Dict, Any, Optional
from .exchange_interface import ExchangeInterface, TradingType

class FuturesExchange(ExchangeInterface):
    """선물 거래소 인터페이스"""
    
    def __init__(self, exchange_name: str):
        super().__init__(exchange_name, TradingType.FUTURES)
    
    @abstractmethod
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """레버리지 설정"""
        pass
    
    @abstractmethod
    def get_leverage(self, symbol: str) -> int:
        """레버리지 조회"""
        pass
    
    @abstractmethod
    def set_margin_type(self, symbol: str, margin_type: str) -> bool:
        """마진 타입 설정 (ISOLATED/CROSS)"""
        pass
    
    @abstractmethod
    def get_funding_rate(self, symbol: str) -> float:
        """펀딩 수수료 조회"""
        pass

    # 선택 기능: 서버-사이드 보험 TP/SL 설정 (어댑터별로 선택 구현)
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
        """기본 구현: 미지원. 각 어댑터에서 필요 시 오버라이드.
        UnifiedTrader는 실패를 경고 후 계속 진행합니다.
        """
        return {"status": "error", "error": "not_supported"}
