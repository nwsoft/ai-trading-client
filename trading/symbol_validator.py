#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
심볼 검증 유틸리티
거래소별 심볼 포맷 검증 및 안전 심볼 매핑
"""

import logging
from typing import Dict, List, Optional, Any

class SymbolValidator:
    """심볼 검증 클래스"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 거래소별 안전 심볼 매핑
        self.safe_symbols = {
            'binance': 'BTCUSDT',
            'bybit': 'BTCUSDT', 
            'okx': 'BTC-USDT',
            'bitget': 'BTCUSDT',
            'upbit': 'KRW-BTC',
            'bithumb': 'BTC/KRW'
        }
        
        # 거래소별 심볼 포맷 패턴
        self.symbol_patterns = {
            'binance': r'^[A-Z0-9]+USDT$',
            'bybit': r'^[A-Z0-9]+USDT$',
            'okx': r'^[A-Z0-9]+-[A-Z0-9]+$',
            'bitget': r'^[A-Z0-9]+USDT$',
            'upbit': r'^KRW-[A-Z0-9]+$',
            'bithumb': r'^[A-Z0-9]+/[A-Z0-9]+$'
        }
    
    def is_valid_symbol(self, exchange: str, symbol: str) -> bool:
        """심볼 유효성 검증"""
        try:
            if not symbol or not exchange:
                return False
                
            # 기본 패턴 검증
            import re
            pattern = self.symbol_patterns.get(exchange)
            if pattern and not re.match(pattern, symbol):
                return False
                
            # 거래소별 특수 검증
            if exchange == 'upbit' and not symbol.startswith('KRW-'):
                return False
            elif exchange == 'bithumb' and '/' not in symbol:
                return False
            elif exchange == 'okx' and '-' not in symbol:
                return False
            elif exchange in ['binance', 'bybit', 'bitget'] and not symbol.endswith('USDT'):
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"심볼 검증 오류: {e}")
            return False
    
    def get_safe_symbol(self, exchange: str) -> str:
        """거래소별 안전 심볼 반환"""
        return self.safe_symbols.get(exchange, 'BTCUSDT')
    
    def normalize_symbol(self, exchange: str, symbol: str) -> str:
        """심볼을 거래소 포맷으로 정규화"""
        try:
            if not symbol or not exchange:
                return self.get_safe_symbol(exchange)
            
            # 이미 올바른 포맷인 경우
            if self.is_valid_symbol(exchange, symbol):
                return symbol
            
            # 거래소별 정규화
            if exchange == 'upbit':
                if not symbol.startswith('KRW-'):
                    return f'KRW-{symbol}'
            elif exchange == 'bithumb':
                if '/' not in symbol:
                    return f'{symbol}/KRW'
            elif exchange == 'okx':
                if '-' not in symbol and symbol.endswith('USDT'):
                    return symbol.replace('USDT', '-USDT')
            elif exchange in ['binance', 'bybit', 'bitget']:
                if not symbol.endswith('USDT'):
                    return f'{symbol}USDT'
            
            return symbol
            
        except Exception as e:
            self.logger.error(f"심볼 정규화 오류: {e}")
            return self.get_safe_symbol(exchange)
    
    def validate_and_normalize(self, exchange: str, symbol: str) -> Optional[str]:
        """심볼 검증 후 정규화된 심볼 반환 (실패 시 None)"""
        try:
            normalized = self.normalize_symbol(exchange, symbol)
            if self.is_valid_symbol(exchange, normalized):
                return normalized
            else:
                self.logger.warning(f"심볼 검증 실패: {exchange} - {symbol}")
                return None
        except Exception as e:
            self.logger.error(f"심볼 검증/정규화 오류: {e}")
            return None

# 전역 인스턴스
symbol_validator = SymbolValidator()

