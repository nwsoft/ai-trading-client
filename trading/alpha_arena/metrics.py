#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alpha Arena 메트릭 수집

세션 메트릭을 수집하고 기록합니다.
"""

import logging
import statistics
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field


@dataclass
class SessionMetrics:
    """세션 메트릭"""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    
    # 거래 통계
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # PnL
    total_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    
    # 승률
    win_rate: float = 0.0
    
    # 수익률
    total_return: float = 0.0
    initial_balance: float = 0.0
    current_balance: float = 0.0
    
    # 샤프 비율 (간단 버전)
    sharpe_ratio: float = 0.0
    
    # 추가 통계
    total_ticks: int = 0
    successful_orders: int = 0
    failed_orders: int = 0
    skipped_orders: int = 0
    
    # 심볼별 통계
    symbol_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class ArenaMetrics:
    """Alpha Arena 메트릭 수집기"""
    
    def __init__(self, session_id: str):
        """
        Args:
            session_id: 세션 ID
        """
        self.session_id = session_id
        self.logger = logging.getLogger(__name__)
        
        # 현재 세션 메트릭
        self.current_metrics = SessionMetrics(
            session_id=session_id,
            start_time=datetime.now()
        )
        
        # 거래 이력 (PnL 계산용)
        self.trade_history: List[Dict[str, Any]] = []
        
        # 틱별 PnL (샤프 비율 계산용)
        self.tick_pnl_history: List[float] = []
    
    def record_tick(self):
        """틱 실행 기록"""
        self.current_metrics.total_ticks += 1
    
    def record_order_result(self, result: Dict[str, Any]):
        """주문 결과 기록"""
        status = result.get('status', '')
        
        if status == 'SUCCESS':
            self.current_metrics.successful_orders += 1
        elif status == 'ERROR':
            self.current_metrics.failed_orders += 1
        elif status == 'SKIPPED':
            self.current_metrics.skipped_orders += 1
    
    def record_trade(self, symbol: str, side: str, entry_price: float, 
                    exit_price: Optional[float] = None, pnl: Optional[float] = None):
        """거래 기록"""
        trade = {
            'symbol': symbol,
            'side': side,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl': pnl,
            'timestamp': datetime.now()
        }
        
        self.trade_history.append(trade)
        self.current_metrics.total_trades += 1
        
        if pnl is not None:
            if pnl > 0:
                self.current_metrics.winning_trades += 1
            else:
                self.current_metrics.losing_trades += 1
            
            self.current_metrics.realized_pnl += pnl
            self.current_metrics.total_pnl += pnl
            
            # 틱별 PnL 기록
            self.tick_pnl_history.append(pnl)
        
        # 심볼별 통계 업데이트
        if symbol not in self.current_metrics.symbol_stats:
            self.current_metrics.symbol_stats[symbol] = {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'total_pnl': 0.0
            }
        
        stats = self.current_metrics.symbol_stats[symbol]
        stats['total_trades'] += 1
        if pnl is not None:
            if pnl > 0:
                stats['winning_trades'] += 1
            else:
                stats['losing_trades'] += 1
            stats['total_pnl'] += pnl
    
    def update_balance(self, balance: float):
        """잔고 업데이트"""
        if self.current_metrics.initial_balance == 0:
            self.current_metrics.initial_balance = balance
        
        self.current_metrics.current_balance = balance
        
        # 수익률 계산
        if self.current_metrics.initial_balance > 0:
            self.current_metrics.total_return = (
                (balance - self.current_metrics.initial_balance) / 
                self.current_metrics.initial_balance * 100
            )
    
    def update_unrealized_pnl(self, unrealized_pnl: float):
        """미실현 PnL 업데이트"""
        self.current_metrics.unrealized_pnl = unrealized_pnl
        self.current_metrics.total_pnl = (
            self.current_metrics.realized_pnl + unrealized_pnl
        )
    
    def calculate_win_rate(self) -> float:
        """승률 계산"""
        if self.current_metrics.total_trades == 0:
            return 0.0
        
        win_rate = (
            self.current_metrics.winning_trades / 
            self.current_metrics.total_trades * 100
        )
        self.current_metrics.win_rate = win_rate
        return win_rate
    
    def calculate_sharpe_ratio(self, risk_free_rate: float = 0.0) -> float:
        """샤프 비율 계산 (간단 버전)"""
        if len(self.tick_pnl_history) < 2:
            return 0.0
        
        try:
            # 평균 수익률
            mean_return = statistics.mean(self.tick_pnl_history)
            
            # 표준편차
            if len(self.tick_pnl_history) > 1:
                std_dev = statistics.stdev(self.tick_pnl_history)
            else:
                std_dev = 0.0
            
            # 샤프 비율 = (평균 수익률 - 무위험 수익률) / 표준편차
            if std_dev > 0:
                sharpe = (mean_return - risk_free_rate) / std_dev
            else:
                sharpe = 0.0
            
            self.current_metrics.sharpe_ratio = sharpe
            return sharpe
            
        except Exception as e:
            self.logger.warning(f"샤프 비율 계산 오류: {e}")
            return 0.0
    
    def finalize_session(self):
        """세션 종료 및 최종 계산"""
        self.current_metrics.end_time = datetime.now()
        
        # 최종 계산
        self.calculate_win_rate()
        self.calculate_sharpe_ratio()
    
    def get_metrics(self) -> Dict[str, Any]:
        """현재 메트릭 반환"""
        # 최신 계산 업데이트
        self.calculate_win_rate()
        
        # 딕셔너리로 변환
        metrics_dict = asdict(self.current_metrics)
        
        # datetime 직렬화
        if metrics_dict.get('start_time'):
            metrics_dict['start_time'] = self.current_metrics.start_time.isoformat()
        if metrics_dict.get('end_time'):
            metrics_dict['end_time'] = self.current_metrics.end_time.isoformat()
        
        return metrics_dict
    
    def log_metrics(self):
        """메트릭 로깅"""
        metrics = self.get_metrics()
        
        self.logger.info("=" * 60)
        self.logger.info(f"Alpha Arena 세션 메트릭: {self.session_id}")
        self.logger.info("=" * 60)
        self.logger.info(f"시작 시간: {metrics.get('start_time')}")
        self.logger.info(f"총 틱 수: {metrics.get('total_ticks')}")
        self.logger.info(f"총 거래 수: {metrics.get('total_trades')}")
        self.logger.info(f"승리 거래: {metrics.get('winning_trades')}")
        self.logger.info(f"손실 거래: {metrics.get('losing_trades')}")
        self.logger.info(f"승률: {metrics.get('win_rate'):.2f}%")
        self.logger.info(f"실현 PnL: ${metrics.get('realized_pnl'):.2f}")
        self.logger.info(f"미실현 PnL: ${metrics.get('unrealized_pnl'):.2f}")
        self.logger.info(f"총 PnL: ${metrics.get('total_pnl'):.2f}")
        self.logger.info(f"수익률: {metrics.get('total_return'):.2f}%")
        self.logger.info(f"샤프 비율: {metrics.get('sharpe_ratio'):.4f}")
        self.logger.info(f"성공 주문: {metrics.get('successful_orders')}")
        self.logger.info(f"실패 주문: {metrics.get('failed_orders')}")
        self.logger.info(f"스킵 주문: {metrics.get('skipped_orders')}")
        self.logger.info("=" * 60)

