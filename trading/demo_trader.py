#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
데모 모드 거래 시뮬레이터
관리자 전용 고성능 시뮬레이션 모드
"""

import random
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
import logging


class DemoTrader:
    """데모 모드 거래 시뮬레이터"""
    
    def __init__(self, settings: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.settings = settings
        self.logger = logger or logging.getLogger(__name__)
        
        # 데모 모드 전용 설정
        self.demo_config = {
            'base_win_rate': 0.85,  # 기본 승률 85%
            'profit_multiplier': 1.8,  # 수익 배율
            'loss_reduction': 0.3,  # 손실 감소율
            'signal_boost': 1.5,  # 신호 강화 배율
            'min_profit_percent': 0.8,  # 최소 수익률 0.8%
            'max_profit_percent': 2.5,  # 최대 수익률 2.5%
            'min_loss_percent': -0.6,  # 최소 손실률 -0.6%
            'max_loss_percent': -0.2,  # 최대 손실률 -0.2%
            'trade_frequency_boost': 1.3,  # 거래 빈도 증가
        }
        
        # 가상 잔고 (각 거래소별)
        self.virtual_balances = {
            'binance': {'USDT': 10000.0},
            'upbit': {'KRW': 15000000.0},
            'bybit': {'USDT': 10000.0},
            'okx': {'USDT': 10000.0},
            'bitget': {'USDT': 10000.0},
            'bithumb': {'KRW': 15000000.0}
        }
        
        # 거래 기록 (성과 분석용)
        self.trade_history = []
        self.performance_stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'total_profit': 0.0,
            'win_rate': 0.0,
            'avg_profit': 0.0,
            'max_profit': 0.0,
            'max_loss': 0.0
        }
        
        # 시장 상황 시뮬레이션
        self.market_conditions = {
            'trend': 'bullish',  # bullish, bearish, sideways
            'volatility': 'medium',  # low, medium, high
            'momentum': 'strong'  # weak, moderate, strong
        }
        
        self.logger.info("🎭 데모 모드 거래 시뮬레이터 초기화 완료")
    
    def enhance_signal(self, original_signal: str, confidence: float) -> Tuple[str, float]:
        """
        신호를 데모 모드용으로 향상
        
        Args:
            original_signal: 원본 신호 (LONG, SHORT, HOLD)
            confidence: 원본 신뢰도
        
        Returns:
            Tuple[str, float]: 향상된 신호와 신뢰도
        """
        enhanced_confidence = min(0.95, confidence * self.demo_config['signal_boost'])
        
        # 데모 모드에서는 더 적극적인 신호 생성
        if original_signal == 'HOLD':
            # HOLD를 LONG 또는 SHORT로 변경 (시장 상황에 따라)
            if self.market_conditions['trend'] == 'bullish':
                enhanced_signal = 'LONG'
                enhanced_confidence = min(0.90, enhanced_confidence + 0.1)
            elif self.market_conditions['trend'] == 'bearish':
                enhanced_signal = 'SHORT'
                enhanced_confidence = min(0.90, enhanced_confidence + 0.1)
            else:
                # 시드마켓에서는 랜덤하게 결정
                enhanced_signal = random.choice(['LONG', 'SHORT'])
                enhanced_confidence = min(0.85, enhanced_confidence + 0.05)
        else:
            enhanced_signal = original_signal
            enhanced_confidence = min(0.95, enhanced_confidence + 0.05)
        
        return enhanced_signal, enhanced_confidence
    
    def simulate_trade_execution(self, 
                               exchange_name: str,
                               symbol: str, 
                               side: str, 
                               quantity: float,
                               price: float,
                               leverage: int = 1,
                               tp_percent: Optional[float] = None,
                               sl_percent: Optional[float] = None) -> Dict[str, Any]:
        """
        거래 실행 시뮬레이션 (TP/SL 기반)
        
        Args:
            exchange_name: 거래소명
            symbol: 심볼
            side: 매수/매도 (buy/sell)
            quantity: 수량
            price: 진입가격
            leverage: 레버리지
            tp_percent: TP 비율 (예: 0.018 = 1.8%)
            sl_percent: SL 비율 (예: 0.020 = 2.0%)
        
        Returns:
            Dict[str, Any]: 거래 결과
        """
        # TP/SL 기본값 설정
        if tp_percent is None:
            tp_percent = 0.018  # 1.8% 기본 TP
        if sl_percent is None:
            sl_percent = 0.020  # 2.0% 기본 SL
            
        # 데모 모드에서는 TP/SL을 더 유리하게 조정
        tp_percent *= self.demo_config['profit_multiplier']  # 1.8배 적용
        sl_percent *= self.demo_config['loss_reduction']  # 0.3배 적용
        
        # 거래 성공률 계산 (TP/SL 기반)
        win_probability = self.demo_config['base_win_rate']
        
        # 시장 상황에 따른 성공률 조정
        if self.market_conditions['trend'] == 'bullish':
            if side.lower() == 'buy':
                win_probability += 0.1
            else:
                win_probability -= 0.05
        elif self.market_conditions['trend'] == 'bearish':
            if side.lower() == 'sell':
                win_probability += 0.1
            else:
                win_probability -= 0.05
        
        # 거래 성공 여부 결정 (TP/SL 기반)
        is_winning_trade = random.random() < win_probability
        
        # TP/SL 기반 수익/손실 계산
        if is_winning_trade:
            # TP 달성 (수익)
            profit_percent = tp_percent * 100
        else:
            # SL 달성 (손실)
            profit_percent = -sl_percent * 100
        
        # 레버리지 적용
        if leverage > 1:
            profit_percent *= leverage
        
        # 거래 금액 계산
        trade_amount = quantity * price
        profit_amount = trade_amount * (profit_percent / 100)
        
        # 가상 잔고 업데이트
        self._update_virtual_balance(exchange_name, side, trade_amount, profit_amount)
        
        # 거래 기록 저장
        trade_record = {
            'timestamp': datetime.now(timezone.utc),
            'exchange': exchange_name,
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'price': price,
            'leverage': leverage,
            'tp_percent': tp_percent,
            'sl_percent': sl_percent,
            'profit_percent': profit_percent,
            'profit_amount': profit_amount,
            'is_winning': is_winning_trade,
            'trade_amount': trade_amount,
            'close_reason': 'TP' if is_winning_trade else 'SL'
        }
        
        self.trade_history.append(trade_record)
        self._update_performance_stats(trade_record)
        
        # 거래 결과 반환
        return {
            'status': 'success',
            'order_id': f"demo-{exchange_name}-{symbol}-{int(time.time() * 1000)}",
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'price': price,
            'leverage': leverage,
            'tp_percent': tp_percent,
            'sl_percent': sl_percent,
            'profit_percent': profit_percent,
            'profit_amount': profit_amount,
            'is_winning': is_winning_trade,
            'close_reason': 'TP' if is_winning_trade else 'SL',
            'virtual_balance': self.virtual_balances[exchange_name].copy(),
            'performance_stats': self.performance_stats.copy(),
            'demo_mode': True,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def _update_virtual_balance(self, exchange_name: str, side: str, trade_amount: float, profit_amount: float):
        """가상 잔고 업데이트"""
        if exchange_name not in self.virtual_balances:
            return
        
        balance = self.virtual_balances[exchange_name]
        
        # 기본 통화 (USDT 또는 KRW)
        base_currency = 'USDT' if exchange_name in ['binance', 'bybit', 'okx', 'bitget'] else 'KRW'
        
        if side.lower() == 'buy':
            # 매수: 기본 통화 차감, 수익 추가
            balance[base_currency] -= trade_amount
            balance[base_currency] += profit_amount
        else:
            # 매도: 기본 통화 증가, 수익 추가
            balance[base_currency] += trade_amount
            balance[base_currency] += profit_amount
    
    def _update_performance_stats(self, trade_record: Dict[str, Any]):
        """성과 통계 업데이트"""
        self.performance_stats['total_trades'] += 1
        
        if trade_record['is_winning']:
            self.performance_stats['winning_trades'] += 1
        
        self.performance_stats['total_profit'] += trade_record['profit_amount']
        self.performance_stats['win_rate'] = (
            self.performance_stats['winning_trades'] / self.performance_stats['total_trades']
        )
        self.performance_stats['avg_profit'] = (
            self.performance_stats['total_profit'] / self.performance_stats['total_trades']
        )
        
        # 최대 수익/손실 업데이트
        if trade_record['profit_amount'] > self.performance_stats['max_profit']:
            self.performance_stats['max_profit'] = trade_record['profit_amount']
        
        if trade_record['profit_amount'] < self.performance_stats['max_loss']:
            self.performance_stats['max_loss'] = trade_record['profit_amount']
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """성과 요약 반환"""
        if not self.trade_history:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'total_profit': 0.0,
                'total_profit_percent': 0.0,
                'avg_profit_per_trade': 0.0,
                'hourly_return_rate': 0.0,
                'demo_mode': True
            }
        
        # 시간당 수익률 계산 (1시간당 약 10% 목표)
        total_profit_percent = (self.performance_stats['total_profit'] / 10000.0) * 100
        hours_trading = max(1, len(self.trade_history) / 6)  # 6거래당 1시간 가정
        hourly_return_rate = total_profit_percent / hours_trading
        
        return {
            'total_trades': self.performance_stats['total_trades'],
            'winning_trades': self.performance_stats['winning_trades'],
            'win_rate': round(self.performance_stats['win_rate'] * 100, 2),
            'total_profit': round(self.performance_stats['total_profit'], 2),
            'total_profit_percent': round(total_profit_percent, 2),
            'avg_profit_per_trade': round(self.performance_stats['avg_profit'], 2),
            'hourly_return_rate': round(hourly_return_rate, 2),
            'max_profit': round(self.performance_stats['max_profit'], 2),
            'max_loss': round(self.performance_stats['max_loss'], 2),
            'virtual_balances': self.virtual_balances,
            'demo_mode': True,
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
    
    def update_market_conditions(self, market_data: Dict[str, Any]):
        """시장 상황 업데이트 (더 나은 거래 결과를 위해)"""
        # 시장 데이터를 기반으로 데모 모드에 유리한 조건 설정
        if market_data.get('trend', '') == 'bullish':
            self.market_conditions['trend'] = 'bullish'
            self.market_conditions['momentum'] = 'strong'
        elif market_data.get('trend', '') == 'bearish':
            self.market_conditions['trend'] = 'bearish'
            self.market_conditions['momentum'] = 'strong'
        else:
            self.market_conditions['trend'] = 'bullish'  # 기본적으로 강세로 설정
            self.market_conditions['momentum'] = 'strong'
        
        # 변동성은 중간 수준으로 설정 (안정적인 수익을 위해)
        self.market_conditions['volatility'] = 'medium'
    
    def log_demo_trade(self, trade_result: Dict[str, Any], exchange_name: str):
        """데모 거래 로그 출력"""
        status_emoji = "🟢" if trade_result['is_winning'] else "🔴"
        profit_sign = "+" if trade_result['profit_amount'] >= 0 else ""
        quote_asset = 'KRW' if exchange_name in {'upbit', 'bithumb'} else 'USDT'
        quote_balance = float(
            (self.virtual_balances.get(exchange_name) or {}).get(quote_asset, 0.0)
        )
        
        self.logger.info(
            f"{status_emoji} [DEMO] {exchange_name} {trade_result['symbol']} "
            f"{trade_result['side'].upper()} - "
            f"수익: {profit_sign}{trade_result['profit_percent']:.2f}% "
            f"({profit_sign}{trade_result['profit_amount']:.2f}) - "
            f"잔고: {quote_balance:.2f} {quote_asset}"
        )
        
        # 성과 요약 로그
        if self.performance_stats['total_trades'] > 0 and self.performance_stats['total_trades'] % 10 == 0:
            summary = self.get_performance_summary()
            self.logger.info(
                f"📊 [DEMO] 성과 요약 - "
                f"총 거래: {summary['total_trades']}회, "
                f"승률: {summary['win_rate']}%, "
                f"총 수익: {summary['total_profit_percent']}%, "
                f"시간당 수익률: {summary['hourly_return_rate']}%"
            )
