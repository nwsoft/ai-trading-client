#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
고급 리스크 관리 시스템
연속 익절/손절 추적, 일일 손실 한도, 동적 코인 교체
"""

import json
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import os


@dataclass
class TradeResult:
    """거래 결과 데이터"""
    symbol: str
    result: str  # 'PROFIT', 'LOSS', 'FORCE_CLOSE'
    profit_rate: float
    timestamp: datetime
    entry_price: float
    exit_price: float
    position_size: float
    holding_time: int  # milliseconds


@dataclass
class CoinPerformance:
    """코인별 성과 추적"""
    symbol: str
    consecutive_wins: int
    consecutive_losses: int
    total_trades: int
    total_profit: float
    win_rate: float
    avg_profit_rate: float
    last_trade_time: datetime
    should_replace: bool
    replacement_reason: str


class RiskManager:
    """고급 리스크 관리 시스템"""
    
    def __init__(self, binance_client, database_manager):
        self.binance_client = binance_client
        self.database_manager = database_manager
        self.logger = logging.getLogger(__name__)
        
        # 연속 거래 추적
        self.coin_consecutive_wins = {}
        self.coin_consecutive_losses = {}
        self.coin_trade_history = {}
        
        # 일일 손실 관리
        self.daily_initial_balance = 0.0
        self.daily_pnl = 0.0
        self.last_daily_reset = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 거래 설정
        self.max_daily_loss_percent = float(os.getenv('MAX_DAILY_LOSS_PERCENT', '30'))
        self.max_consecutive_losses = 3
        self.max_consecutive_wins = 12  # 과열 방지
        
        # 코인 교체 설정
        self.last_trade_time = datetime.now()
        self.last_dynamic_check = datetime.now()
        self.coin_replacement_interval = timedelta(hours=1)
        
        self.logger.info("RiskManager 초기화 완료")
    
    def update_coin_trade_history(self, symbol: str, trade_result: str, profit_rate: float,
                                entry_price: float, exit_price: float, position_size: float,
                                holding_time: int, exchange: Optional[str] = None) -> bool:
        """코인별 거래 이력 업데이트 및 즉시 교체 결정"""
        try:
            coin = symbol.replace('USDT', '')
            
            # 초기화
            if coin not in self.coin_trade_history:
                self.coin_trade_history[coin] = []
                self.coin_consecutive_wins[coin] = 0
                self.coin_consecutive_losses[coin] = 0
            
            # 거래 이력 추가
            trade_info = TradeResult(
                symbol=symbol,
                result=trade_result,
                profit_rate=profit_rate,
                timestamp=datetime.now(),
                entry_price=entry_price,
                exit_price=exit_price,
                position_size=position_size,
                holding_time=holding_time
            )
            trade_payload = asdict(trade_info)
            if exchange:
                trade_payload['exchange'] = str(exchange).strip().lower()
            self.coin_trade_history[coin].append(trade_payload)
            
            # 연속 횟수 업데이트
            if trade_result == 'PROFIT':
                self.coin_consecutive_wins[coin] += 1
                self.coin_consecutive_losses[coin] = 0
                self.logger.info(f"[{symbol}] 익절 성공 - 연속 익절: {self.coin_consecutive_wins[coin]}회")
            else:  # LOSS, FORCE_CLOSE
                self.coin_consecutive_losses[coin] += 1
                self.coin_consecutive_wins[coin] = 0
                self.logger.warning(f"[{symbol}] 손절 발생 - 연속 손실: {self.coin_consecutive_losses[coin]}회")
            
            # 거래 시간 업데이트
            self.last_trade_time = datetime.now()
            
            # 거래 후 즉시 성과 체크 및 교체 결정
            should_replace = self._check_coin_performance_after_trade(coin, trade_result, profit_rate)
            
            return should_replace
            
        except Exception as e:
            self.logger.error(f"거래 이력 업데이트 오류: {e}")
            return False
    
    def _check_coin_performance_after_trade(self, coin: str, trade_result: str, profit_rate: float) -> bool:
        """거래 완료 후 코인 성과 체크 및 즉시 교체 결정"""
        try:
            consecutive_losses = self.coin_consecutive_losses.get(coin, 0)
            consecutive_wins = self.coin_consecutive_wins.get(coin, 0)
            
            # 1. 급격한 손실 체크 (단일 거래 손실률 2% 이상)
            if trade_result in ['LOSS', 'FORCE_CLOSE'] and abs(profit_rate) > 2.0:
                # coin 전체를 로그로 출력하지 않음
                coin_symbol = coin.get('symbol', 'UNKNOWN') if isinstance(coin, dict) else str(coin)
                self.logger.warning(f"{coin_symbol}: 급격한 손실 발생 ({profit_rate:.2f}%), 즉시 교체 권장")
                return True
            
            # 2. 연속 손실 체크 (3회 이상)
            if consecutive_losses >= self.max_consecutive_losses:
                # coin 전체를 로그로 출력하지 않음
                coin_symbol = coin.get('symbol', 'UNKNOWN') if isinstance(coin, dict) else str(coin)
                self.logger.warning(f"{coin_symbol}: 연속 손실 {consecutive_losses}회, 즉시 교체 필요")
                return True
            
            # 3. 연속 익절 체크 (스캘핑 최적화: 과열 방지)
            if consecutive_wins >= self.max_consecutive_wins:
                # coin 전체를 로그로 출력하지 않음
                coin_symbol = coin.get('symbol', 'UNKNOWN') if isinstance(coin, dict) else str(coin)
                self.logger.info(f"{coin_symbol}: 연속 익절 {consecutive_wins}회, 안정화를 위해 교체 권장")
                return True
            
            # 4. 누적 손실률 체크 (최근 10거래 기준)
            recent_performance = self._get_recent_performance(coin)
            if recent_performance and recent_performance['total_loss_rate'] > 5.0:  # 5% 이상 누적 손실
                # coin 전체를 로그로 출력하지 않음
                coin_symbol = coin.get('symbol', 'UNKNOWN') if isinstance(coin, dict) else str(coin)
                self.logger.warning(f"{coin_symbol}: 누적 손실률 {recent_performance['total_loss_rate']:.2f}%, 교체 권장")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"코인 성과 체크 오류: {e}")
            return False
    
    def _get_recent_performance(self, coin: str) -> Optional[Dict]:
        """최근 거래 성과 분석 (최근 10거래)"""
        try:
            if coin not in self.coin_trade_history or len(self.coin_trade_history[coin]) < 3:
                return None
            
            # 최근 10거래 분석
            recent_trades = self.coin_trade_history[coin][-10:]
            
            total_pnl = 0
            total_amount = 0
            profit_count = 0
            
            for trade in recent_trades:
                profit_rate = trade['profit_rate']
                position_size = trade['position_size']
                entry_price = trade['entry_price']
                
                trade_amount = position_size * entry_price
                trade_pnl = trade_amount * (profit_rate / 100)
                
                total_pnl += trade_pnl
                total_amount += trade_amount
                
                if profit_rate > 0:
                    profit_count += 1
            
            if total_amount > 0:
                total_loss_rate = (abs(total_pnl) / total_amount) * 100 if total_pnl < 0 else 0
                win_rate = (profit_count / len(recent_trades)) * 100
                
                return {
                    'total_pnl': total_pnl,
                    'total_amount': total_amount,
                    'total_loss_rate': total_loss_rate,
                    'win_rate': win_rate,
                    'trade_count': len(recent_trades)
                }
            
            return None
            
        except Exception as e:
            # coin 전체를 로그로 출력하지 않음
            coin_symbol = coin.get('symbol', 'UNKNOWN') if isinstance(coin, dict) else str(coin)
            self.logger.error(f"최근 성과 분석 오류 for {coin_symbol}: {e}")
            return None
    
    def should_skip_coin(self, symbol: str) -> bool:
        """코인 거래 스킵 여부 결정"""
        try:
            coin = symbol.replace('USDT', '')
            
            # 메이저 코인 리스트
            MAJOR_COINS = ["BTC", "ETH", "BNB", "SOL", "XRP"]
            is_major_coin = coin in MAJOR_COINS
            
            consecutive_wins = self.coin_consecutive_wins.get(coin, 0)
            consecutive_losses = self.coin_consecutive_losses.get(coin, 0)
            
            self.logger.info(f"[{symbol}] 거래 검토 - 연속익절: {consecutive_wins}, 연속손실: {consecutive_losses}, 메이저: {is_major_coin}")
            
            # 1. 익절 후 재진입 전략 적용
            if self._should_apply_reentry_strategy(coin, consecutive_wins, consecutive_losses):
                self.logger.info(f"[{symbol}] 재진입 전략 적용 - 익절 후 재진입 허용")
                return False
            
            # 2. 시장 상황 기반 스킵 해제 체크
            if self._should_reset_skip_due_to_market_conditions(coin, consecutive_wins, consecutive_losses):
                self.logger.info(f"[{symbol}] 시장 상황 양호 - 스킵 해제")
                return False
            
            # 3. 연속 손실 기반 스킵 결정
            if is_major_coin:
                should_skip = consecutive_losses >= 3  # 메이저 코인: 3회 연속 손실
            else:
                should_skip = consecutive_losses >= 3  # 알트코인: 3회 연속 손실
            
            if should_skip:
                self.logger.warning(f"[{symbol}] 연속 손실로 스킵: {consecutive_losses}회")
            
            return should_skip
            
        except Exception as e:
            self.logger.error(f"코인 스킵 결정 오류: {e}")
            return False
    
    def _should_apply_reentry_strategy(self, coin: str, consecutive_wins: int, consecutive_losses: int) -> bool:
        """익절 후 재진입 전략 적용 여부 결정"""
        try:
            # 1. 기본 조건: 연속 익절 1회 이상
            if consecutive_wins < 1:
                return False
            
            # 2. 연속 손실이 있으면 재진입 금지
            if consecutive_losses > 0:
                return False
            
            # 3. 최근 거래 이력 확인
            if coin not in self.coin_trade_history or len(self.coin_trade_history[coin]) < 1:
                return False
            
            # 4. 최근 거래가 익절인지 확인
            recent_trade = self.coin_trade_history[coin][-1]
            if recent_trade['result'] != 'PROFIT':
                return False
            
            # 5. 수익률 기준 (0.05% 이상)
            if recent_trade['profit_rate'] < 0.05:
                return False
            
            # 6. 과열 방지: 연속 익절 12회 이상이면 재진입 제한
            if consecutive_wins >= 12:
                # coin 전체를 로그로 출력하지 않음
                coin_symbol = coin.get('symbol', 'UNKNOWN') if isinstance(coin, dict) else str(coin)
                self.logger.info(f"[{coin_symbol}] 과도한 연속 익절 ({consecutive_wins}회), 재진입 제한")
                return False
            
            return True
            
        except Exception as e:
            # coin 전체를 로그로 출력하지 않음
            coin_symbol = coin.get('symbol', 'UNKNOWN') if isinstance(coin, dict) else str(coin)
            self.logger.error(f"재진입 전략 체크 오류 for {coin_symbol}: {e}")
            return False
    
    def _should_reset_skip_due_to_market_conditions(self, coin: str, consecutive_wins: int, consecutive_losses: int) -> bool:
        """시장 상황이 좋을 때 스킵 상태 해제"""
        try:
            # 연속 손실이 1회 이상인 경우 스킵 해제 금지
            if consecutive_losses >= 1:
                return False
            
            # 연속 익절이 2회 이상인 경우 허용
            if consecutive_wins >= 2:
                return True
            
            return False
            
        except Exception as e:
            # coin 전체를 로그로 출력하지 않음
            coin_symbol = coin.get('symbol', 'UNKNOWN') if isinstance(coin, dict) else str(coin)
            self.logger.error(f"시장 상황 체크 오류 for {coin_symbol}: {e}")
            return False

    def check_daily_loss_limit(self) -> bool:
        """일일 손실 한도 체크"""
        try:
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # 일일 초기화
            if today > self.last_daily_reset:
                self.daily_initial_balance = self._calculate_cumulative_balance()
                self.daily_pnl = 0
                self.last_daily_reset = today
                self.logger.info(f"일일 초기화: 시작 잔고 {self.daily_initial_balance:.2f} USDT")
            
            # 현재 잔고 및 손익 계산
            current_balance = self._calculate_cumulative_balance()
            today_trades = self._get_today_trades()
            
            realized_pnl = sum(trade.get('realized_pnl', 0) for trade in today_trades)
            unrealized_pnl = self._get_unrealized_pnl()
            
            total_pnl = realized_pnl + unrealized_pnl
            balance_change = current_balance - self.daily_initial_balance
            
            # 손실률 계산
            if self.daily_initial_balance > 0:
                loss_rate = abs(balance_change / self.daily_initial_balance) * 100 if balance_change < 0 else 0
            else:
                loss_rate = 0
            
            # 한도 초과 체크
            stop_trading = balance_change < 0 and loss_rate > self.max_daily_loss_percent
            
            # 상세 로그
            self.logger.info(f"""
            [일일 손실 체크]
            시작 잔고: {self.daily_initial_balance:.4f} USDT
            현재 잔고: {current_balance:.4f} USDT
            잔고 변화: {balance_change:.4f} USDT
            실현 손익: {realized_pnl:.4f} USDT
            미실현 손익: {unrealized_pnl:.4f} USDT
            총 손익: {total_pnl:.4f} USDT
            손실률: {loss_rate:.2f}%
            한도: {self.max_daily_loss_percent:.2f}%
            거래 중단: {'예' if stop_trading else '아니오'}
            오늘 거래 수: {len(today_trades)}
            """)
            
            # 한도 초과 시 경고
            if stop_trading:
                self.logger.error(f"""
                일일 손실 한도 초과!
                현재 손실률: {loss_rate:.2f}%
                한도: {self.max_daily_loss_percent:.2f}%
                초과 금액: {abs(balance_change):.4f} USDT
                거래 중단!
                """)
            
            return stop_trading
            
        except Exception as e:
            self.logger.error(f"일일 손실 체크 오류: {e}")
            return True  # 오류 시 안전하게 거래 중단
    
    def _calculate_cumulative_balance(self) -> float:
        """누적 잔고 계산"""
        try:
            # 데모 모드 확인
            if os.getenv('DEMO_MODE', 'False').lower() == 'true':
                initial_demo_balance = float(os.getenv('DEMO_INITIAL_BALANCE', '1000'))
                
                # 데이터베이스에서 모든 거래 손익 조회
                trades = self.database_manager.get_all_trades()
                total_pnl = sum(trade.get('realized_pnl', 0) for trade in trades)
                
                return initial_demo_balance + total_pnl
            else:
                # 실제 계좌 잔고 조회
                try:
                    account_balance = self.binance_client.get_balance()
                    if account_balance and isinstance(account_balance, dict):
                        # 새로운 바이낸스 API 응답 구조 처리
                        if 'wallet_balance' in account_balance:
                            # 선물 계좌 응답 구조
                            return float(account_balance['wallet_balance'])
                        elif 'USDT' in account_balance:
                            # 기존 현물 계좌 응답 구조
                            usdt_balance = account_balance['USDT']
                            if isinstance(usdt_balance, dict) and 'balance' in usdt_balance:
                                return float(usdt_balance['balance'])
                            elif isinstance(usdt_balance, dict) and 'wallet_balance' in usdt_balance:
                                # 새로운 바이낸스 API 응답 구조 (wallet_balance 사용)
                                return float(usdt_balance['wallet_balance'])
                            else:
                                self.logger.warning(f"USDT 잔고 구조 이상: {usdt_balance}")
                                return 0.0
                        else:
                            self.logger.warning(f"지원되지 않는 잔고 구조: {account_balance}")
                            return 0.0
                    else:
                        self.logger.warning(f"계좌 잔고 조회 실패: {account_balance}")
                        return 0.0
                except Exception as e:
                    self.logger.error(f"잔고 조회 중 오류: {e}")
                    return 0.0
                
        except Exception as e:
            self.logger.error(f"누적 잔고 계산 오류: {e}")
            return 0.0
    
    def _get_today_trades(self) -> List[Dict]:
        """오늘 거래 조회"""
        try:
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            return self.database_manager.get_daily_actual_trades(today)
        except Exception as e:
            self.logger.error(f"오늘 거래 조회 오류: {e}")
            return []
    
    def _get_unrealized_pnl(self) -> float:
        """미실현 손익 계산"""
        try:
            positions = self.binance_client.get_positions()
            unrealized_pnl = 0
            
            if positions:
                for position in positions:
                    # dict(CCXT 스타일) 또는 dataclass(Position) 모두 지원
                    try:
                        if isinstance(position, dict):
                            position_amt = float(position.get('positionAmt', 0) or 0)
                            if position_amt != 0:
                                unrealized_profit = float(position.get('unRealizedProfit', 0) or 0)
                                unrealized_pnl += unrealized_profit
                        else:
                            # dataclass(Position) 경로
                            if hasattr(position, 'unrealized_pnl'):
                                unrealized_pnl += float(getattr(position, 'unrealized_pnl') or 0)
                            else:
                                # 최후 폴백: 기본 계산
                                side = getattr(position, 'side', None)
                                size = float(getattr(position, 'size', 0) or getattr(position, 'quantity', 0) or 0)
                                entry = float(getattr(position, 'entry_price', 0) or 0)
                                mark = float(getattr(position, 'mark_price', 0) or 0)
                                if size and entry and mark:
                                    sign = 1 if (str(getattr(side, 'value', side)).upper() == 'LONG') else -1
                                    unrealized_pnl += (mark - entry) * size * sign
                    except Exception:
                        continue
            
            return unrealized_pnl
            
        except Exception as e:
            self.logger.error(f"미실현 손익 계산 오류: {e}")
            return 0.0

    def get_coin_performance_summary(self) -> Dict[str, CoinPerformance]:
        """코인별 성과 요약"""
        try:
            performance_summary = {}
            
            for coin, history in self.coin_trade_history.items():
                if not history:
                    continue
                
                consecutive_wins = self.coin_consecutive_wins.get(coin, 0)
                consecutive_losses = self.coin_consecutive_losses.get(coin, 0)
                
                # 통계 계산
                total_trades = len(history)
                profit_trades = [t for t in history if t['result'] == 'PROFIT']
                total_profit = sum(t['profit_rate'] for t in history)
                win_rate = (len(profit_trades) / total_trades) * 100 if total_trades > 0 else 0
                avg_profit_rate = total_profit / total_trades if total_trades > 0 else 0
                
                # 교체 필요성 판단
                should_replace = self._check_coin_performance_after_trade(coin, history[-1]['result'], history[-1]['profit_rate'])
                replacement_reason = self._get_replacement_reason(coin, consecutive_wins, consecutive_losses)
                
                performance = CoinPerformance(
                    symbol=f"{coin}USDT",
                    consecutive_wins=consecutive_wins,
                    consecutive_losses=consecutive_losses,
                    total_trades=total_trades,
                    total_profit=total_profit,
                    win_rate=win_rate,
                    avg_profit_rate=avg_profit_rate,
                    last_trade_time=datetime.fromisoformat(history[-1]['timestamp']) if history[-1]['timestamp'] else datetime.now(),
                    should_replace=should_replace,
                    replacement_reason=replacement_reason
                )
                
                performance_summary[coin] = performance
            
            return performance_summary
            
        except Exception as e:
            self.logger.error(f"코인 성과 요약 오류: {e}")
            return {}
    
    def _get_replacement_reason(self, coin: str, consecutive_wins: int, consecutive_losses: int) -> str:
        """교체 사유 생성"""
        reasons = []
        
        if consecutive_losses >= 3:
            reasons.append(f"연속 손실 {consecutive_losses}회")
        
        if consecutive_wins >= 12:
            reasons.append(f"연속 익절 과열 {consecutive_wins}회")
        
        recent_performance = self._get_recent_performance(coin)
        if recent_performance and recent_performance['total_loss_rate'] > 5.0:
            reasons.append(f"누적 손실률 {recent_performance['total_loss_rate']:.2f}%")
        
        return ", ".join(reasons) if reasons else "양호"
