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

    def get_recovery_day_fills(self, symbol, epoch):
        from trading.spot_history_discovery import day_fills
        return day_fills(self,symbol,epoch)

    def get_recovery_holding_quantity(self,symbol):
        from trading.spot_history_discovery import holding_quantity
        return holding_quantity(self,symbol)

    def get_recovery_order_fills(self, symbol: str, order_id: str, epoch: float):
        """Exact order detail, including cancelled orders with partial fills.

        A provider's order price or estimated fees are not execution evidence.
        Coinone overrides this with its native cursor-based history contract.
        """
        from decimal import Decimal
        from trading.recovery_statement import decimal, symbol_key
        exchange = getattr(self,'exchange',None)
        if exchange is None or not callable(getattr(exchange,'fetch_order',None)):
            raise RuntimeError('provider_historical_evidence_unsupported')
        normalize = getattr(self,'_normalize_symbol',lambda s:s)
        order = exchange.fetch_order(str(order_id),normalize(symbol))
        if not isinstance(order,dict) or str(order.get('id')) != str(order_id) or symbol_key(order.get('symbol')) != symbol_key(symbol):
            raise RuntimeError('history_identity_mismatch')
        if order.get('status') not in {'closed','canceled','cancelled','expired'}:
            raise RuntimeError('order_history_incomplete')
        rows = order.get('trades')
        if not isinstance(rows,list) or not rows: raise RuntimeError('exchange_fill_not_found')
        seen, result = set(), []
        for row in rows:
            identity = str(row.get('id') or '')
            if not identity or identity in seen: raise RuntimeError('history_fill_identity_missing')
            seen.add(identity)
            if str(row.get('order')) != str(order_id) or symbol_key(row.get('symbol')) != symbol_key(symbol) or row.get('side') != order.get('side'):
                raise RuntimeError('history_identity_mismatch')
            if decimal(row.get('amount'))<=0 or decimal(row.get('price'))<=0 or not row.get('timestamp'):
                raise RuntimeError('fee_or_fill_data_incomplete')
            result.append({**row,'_execution_confirmed':True})
        if sum((decimal(r['amount']) for r in result),Decimal(0)) != decimal(order.get('filled')):
            raise RuntimeError('partial_or_quantity_mismatch')
        return result
