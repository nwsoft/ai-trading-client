#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
현물 거래소 인터페이스
"""

from typing import List, Dict, Any
from .exchange_interface import ExchangeInterface, TradingType

class SpotExchange(ExchangeInterface):
    """현물 거래소 인터페이스"""
    
    def __init__(self, exchange_name: str):
        super().__init__(exchange_name, TradingType.SPOT)
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """현물은 포지션이 없으므로 빈 리스트 반환"""
        return []
