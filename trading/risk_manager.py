#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
고급 리스크 관리 시스템
연속 익절/손절 추적, 일일 손실 한도, 동적 코인 교체
"""

import json
import sqlite3
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
import time
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


@dataclass(frozen=True)
class DailyLossDecision:
    """거래소별 LIVE 일일 손실 판정 결과.

    ``blocked``는 실제 한도 초과뿐 아니라 계좌/가격 데이터를 확인하지 못해
    신규 LIVE 진입을 안전 보류한 경우에도 True다. ``status``로 두 경우를
    반드시 구분해 화면과 외부 알림이 가짜 손실률을 만들지 않게 한다.
    """

    blocked: bool
    status: str
    source: str
    execution_mode: str
    currency: str = ""
    initial_equity: float = 0.0
    current_equity: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    loss_amount: float = 0.0
    loss_rate: float = 0.0
    reason: str = ""
    checked_at: float = field(default_factory=time.time)


class RiskManager:
    """고급 리스크 관리 시스템"""
    
    def __init__(self, binance_client, database_manager, settings=None, exchange_manager=None):
        self.binance_client = binance_client
        self.database_manager = database_manager
        self.settings = settings if isinstance(settings, dict) else {}
        self.exchange_manager = exchange_manager
        self.logger = logging.getLogger(__name__)
        
        # 연속 거래 추적
        self.coin_consecutive_wins = {}
        self.coin_consecutive_losses = {}
        self.coin_trade_history = {}
        
        # 일일 손실 관리
        self.daily_initial_balance = 0.0
        self.daily_pnl = 0.0
        self.last_daily_reset = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self._daily_initial_equity: Dict[str, float] = {}
        self._last_daily_loss_decision: Dict[str, DailyLossDecision] = {}
        
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

    @staticmethod
    def _risk_number(value: Any) -> float:
        if isinstance(value, dict):
            for key in (
                'margin_balance', 'marginBalance', 'wallet_balance', 'walletBalance',
                'total_balance', 'total', 'balance', 'free', 'available_balance',
            ):
                if key in value:
                    try:
                        return float(value.get(key) or 0.0)
                    except (TypeError, ValueError):
                        continue
            return 0.0
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _risk_currency(source: str) -> str:
        return 'KRW' if source in {'upbit', 'bithumb', 'coinone'} else 'USDT'

    def _resolved_execution_mode(self, source: str, execution_mode: Optional[str]) -> str:
        explicit = str(execution_mode or '').strip().lower()
        if explicit in {'learning', 'paper', 'live'}:
            return explicit
        try:
            from trading.execution_mode import resolve_crypto_execution_mode

            return resolve_crypto_execution_mode(self.settings, source).value
        except Exception:
            # 모드를 확인하지 못한 상태에서 계좌 손실을 계산하지 않는다.
            return 'unknown'

    def _get_live_equity_snapshot(self, source: str) -> Dict[str, Any]:
        """거래소별 검증된 LIVE 계좌 자산 스냅샷을 반환한다.

        실패/빈 응답과 실제 0원을 구분하지 못하는 응답은 ``valid=False``다.
        특히 국내 현물은 KRW 현금만 보지 않고 보유자산을 현재 KRW 가격으로
        평가해 매수 자체가 손실로 오인되지 않게 한다.
        """
        venue = str(source or 'binance').strip().lower()
        currency = self._risk_currency(venue)
        manager = getattr(self, 'exchange_manager', None)
        if manager is None:
            if venue != 'binance':
                return {'valid': False, 'reason': '기관별 계좌 공급자 없음: Binance 잔고를 대신 사용하지 않습니다.'}
            equity = self._calculate_cumulative_balance()
            return {
                'valid': equity > 0,
                'source': venue,
                'currency': currency,
                'equity': float(equity or 0.0),
                'status': 'legacy_success' if equity > 0 else 'equity_unavailable',
                'reason': '' if equity > 0 else '유효한 계좌 자산을 확인하지 못했습니다.',
            }

        try:
            payload = manager.get_exchange_balance(venue, force_refresh=False)
        except Exception as exc:
            return {
                'valid': False, 'source': venue, 'currency': currency, 'equity': 0.0,
                'status': 'balance_query_failed', 'reason': str(exc),
            }
        if not isinstance(payload, dict) or str(payload.get('status') or '').lower() != 'success':
            return {
                'valid': False,
                'source': venue,
                'currency': currency,
                'equity': 0.0,
                'status': str((payload or {}).get('status') or 'invalid_response'),
                'reason': str(
                    (payload or {}).get('message')
                    or (payload or {}).get('error')
                    or '거래소가 유효한 잔고 스냅샷을 반환하지 않았습니다.'
                ),
            }

        balance = payload.get('balance') if isinstance(payload.get('balance'), dict) else {}
        account_info = payload.get('account_info') if isinstance(payload.get('account_info'), dict) else {}
        equity = 0.0
        if venue in {'upbit', 'bithumb', 'coinone'}:
            missing_prices: List[str] = []
            for asset, raw_amount in balance.items():
                amount = self._risk_number(raw_amount)
                if amount <= 0:
                    continue
                asset_name = str(asset or '').strip().upper()
                if asset_name == currency:
                    equity += amount
                    continue
                try:
                    price = float(manager.get_current_price(f'{asset_name}/{currency}', venue) or 0.0)
                except Exception:
                    price = 0.0
                if price <= 0:
                    missing_prices.append(asset_name)
                    continue
                equity += amount * price
            if missing_prices:
                return {
                    'valid': False, 'source': venue, 'currency': currency, 'equity': equity,
                    'status': 'spot_valuation_incomplete',
                    'reason': f"현물 보유자산 가격 확인 실패: {', '.join(sorted(set(missing_prices))[:8])}",
                }
        else:
            # Binance 원본 계정 응답은 totalMarginBalance가 현재 계정 equity에
            # 가장 가깝다. 통합 어댑터의 flat balance는 USDT total을 사용한다.
            for key in ('totalMarginBalance', 'total_margin_balance', 'margin_balance'):
                equity = self._risk_number(account_info.get(key))
                if equity > 0:
                    break
            if equity <= 0:
                equity = self._risk_number(balance.get(currency))
            if equity <= 0:
                equity = self._risk_number(account_info.get('total_balance'))

        if equity <= 0:
            return {
                'valid': False, 'source': venue, 'currency': currency, 'equity': float(equity),
                'status': 'equity_non_positive',
                'reason': '계좌 자산이 0 이하이거나 응답 구조를 확인할 수 없습니다.',
            }
        return {
            'valid': True,
            'source': venue,
            'currency': currency,
            'equity': float(equity),
            'status': 'success',
            'reason': '',
            'timestamp': str(payload.get('timestamp') or ''),
        }

    def _today_live_trades(self, source: str) -> List[Dict[str, Any]]:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        getter = getattr(self.database_manager, 'get_daily_actual_trades', None)
        if not callable(getter):
            raise RuntimeError('daily ledger reader unavailable')
        return list(getter(today, exchange=source, execution_mode='live', strict=True) or [])

    def _managed_unrealized_pnl(self, source: str) -> Tuple[bool, float, str]:
        getter = getattr(self.database_manager, 'get_open_managed_trades', None)
        if not callable(getter):
            # 구형 Binance 경로의 호환 계산. 통합 거래소에 Binance 포지션을
            # 재사용하지 않도록 source가 Binance일 때만 허용한다.
            if source == 'binance' and self.exchange_manager is None:
                return True, float(self._get_unrealized_pnl() or 0.0), ''
            return True, 0.0, ''
        try:
            rows = list(getter(source, strict=True) or [])
        except Exception as exc:
            return False, 0.0, f'NoahAI 관리 포지션 원장 조회 실패: {exc}'
        live_rows = [
            row for row in rows
            if isinstance(row, dict)
            and str(row.get('execution_mode') or 'live').strip().lower() in {'live', 'live_api', 'optimized', 'manual'}
        ]
        if source == 'binance':
            # Local open rows are historical intent, not proof that a position
            # still exists. A confirmed flat account must not value zombie lots.
            getter = getattr(self.binance_client, 'get_positions_result', None)
            if not callable(getter):
                return False, 0.0, 'Binance 현재 포지션 확인 API 없음'
            try:
                snapshot = getter()
                if not isinstance(snapshot, dict) or snapshot.get('status') != 'success' or not isinstance(snapshot.get('positions'), list):
                    return False, 0.0, 'Binance 현재 포지션 조회 실패'
                actual = snapshot['positions']
                if not actual:
                    return True, 0.0, ''
                total = 0.0
                for pos in actual:
                    def field(key):
                        return pos.get(key) if isinstance(pos, dict) else getattr(pos, key, None)
                    symbol, side = str(field('symbol')), str(field('side')).upper()
                    owned = [r for r in live_rows if r.get('symbol') == symbol and
                             ('SHORT' if str(r.get('side')).upper() in ('SELL','SHORT') else 'LONG') == side]
                    if not owned:
                        continue  # account/manual position outside NoahAI scope
                    size = float(field('size'))
                    qty = sum(float(r.get('quantity') or 0) for r in owned)
                    if not math.isfinite(size) or size <= 0 or not math.isclose(qty, size, rel_tol=1e-6, abs_tol=1e-8):
                        return False, 0.0, f'{symbol} 현재 포지션과 관리 원장 수량 대조 필요'
                    pnl = float(field('unrealized_pnl'))
                    if not math.isfinite(pnl):
                        return False, 0.0, f'{symbol} 거래소 미실현 손익 확인 필요'
                    total += pnl
                return True, total, ''
            except Exception:
                return False, 0.0, 'Binance 현재 포지션 손익 응답 검증 실패'
        if not live_rows:
            return True, 0.0, ''
        manager = getattr(self, 'exchange_manager', None)
        if manager is None:
            return False, 0.0, '거래소별 현재가 공급자를 사용할 수 없습니다.'
        total = 0.0
        for row in live_rows:
            symbol = str(row.get('symbol') or '').strip()
            entry = self._risk_number(row.get('entry_price'))
            quantity = self._risk_number(row.get('quantity'))
            if not symbol or entry <= 0 or quantity <= 0:
                return False, 0.0, f'관리 포지션 원장 필수값 누락: {symbol or "unknown"}'
            try:
                current = float(manager.get_current_price(symbol, source) or 0.0)
            except Exception:
                current = 0.0
            if not math.isfinite(current) or current <= 0:
                return False, 0.0, f'관리 포지션 현재가 확인 실패: {symbol}'
            side = str(row.get('side') or 'LONG').strip().upper()
            sign = -1.0 if side in {'SHORT', 'SELL'} else 1.0
            total += (current - entry) * quantity * sign
        return True, float(total), ''

    def evaluate_daily_loss_limit(
        self,
        source: str = 'binance',
        *,
        execution_mode: Optional[str] = None,
    ) -> DailyLossDecision:
        """거래소별 LIVE 손실 가드레일을 평가한다."""
        venue = str(source or 'binance').strip().lower()
        mode = self._resolved_execution_mode(venue, execution_mode)
        currency = self._risk_currency(venue)
        if mode != 'live':
            decision = DailyLossDecision(
                blocked=False,
                status='not_applicable',
                source=venue,
                execution_mode=mode,
                currency=currency,
                reason='LEARNING/PAPER에서는 실제 계좌 일일 손실 가드레일을 평가하지 않습니다.',
            )
            self._last_daily_loss_decision[venue] = decision
            return decision

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        snapshot = self._get_live_equity_snapshot(venue)
        if (not bool(snapshot.get('valid')) or
                not math.isfinite(float(snapshot.get('equity') or 0)) or float(snapshot.get('equity') or 0) <= 0):
            reason = str(snapshot.get('reason') or snapshot.get('status') or 'risk_data_unavailable')
            decision = DailyLossDecision(
                blocked=True,
                status='risk_data_unavailable',
                source=venue,
                execution_mode=mode,
                currency=currency,
                reason=reason,
            )
            self._last_daily_loss_decision[venue] = decision
            self.logger.warning(
                f"{venue.upper()} LIVE 위험 데이터 확인 실패 - 손실률을 계산하지 않고 신규 진입 보류: {reason}"
            )
            try:
                from trading.notifications import publish_notification

                publish_notification(
                    'risk_data_unavailable',
                    'LIVE 위험 데이터 확인 실패',
                    f'잔고·포지션 데이터를 확인하지 못해 손실률을 계산하지 않았습니다. 신규 진입만 보류하고 기존 포지션 보호 상태를 유지합니다. 원인: {reason}',
                    source=venue,
                    execution_mode='live',
                    severity='warning',
                    dedupe_key=f'risk-data-unavailable:live:{venue}:{today.date().isoformat()}',
                )
            except Exception:
                pass
            return decision

        current_equity = float(snapshot.get('equity') or 0.0)
        try:
            trades = self._today_live_trades(venue)
            unresolved = sum(not isinstance(row, dict) or row.get('performance_evidence_ready') is not True
                             for row in trades)
            if unresolved:
                raise ValueError(f'당일 LIVE 청산 {len(trades)}건 중 {unresolved}건 손익 대조 필요')
            nets = [float(row['net_pnl']) for row in trades]
            if not all(math.isfinite(value) for value in nets):
                raise ValueError('확정 순손익 값이 유효하지 않습니다')
            realized_pnl = sum(nets)
        except Exception as exc:
            reason = str(exc)
            decision = DailyLossDecision(
                blocked=True, status='risk_data_unavailable', source=venue,
                execution_mode=mode, currency=currency, current_equity=current_equity,
                reason=reason,
            )
            self._last_daily_loss_decision[venue] = decision
            self.logger.warning(f'{venue.upper()} LIVE 손익 대조 필요: {reason}')
            try:
                from trading.notifications import publish_notification
                publish_notification(
                    'risk_data_unavailable', 'LIVE 손익 대조 필요',
                    f'확정 순손익을 확인하지 못해 손실 금액·비율을 알리지 않습니다. 원인: {reason}. '
                    '신규 진입을 보류합니다. 거래 통계의 체결 동기화와 미대조 사유를 확인하세요.',
                    source=venue, execution_mode='live', severity='warning',
                    dedupe_key=f'risk-pnl-unavailable:live:{venue}:{today.date().isoformat()}',
                )
            except Exception:
                pass
            return decision
        unrealized_valid, unrealized_pnl, unrealized_reason = self._managed_unrealized_pnl(venue)
        if not unrealized_valid:
            decision = DailyLossDecision(
                blocked=True,
                status='risk_data_unavailable',
                source=venue,
                execution_mode=mode,
                currency=currency,
                current_equity=current_equity,
                realized_pnl=realized_pnl,
                reason=unrealized_reason,
            )
            self._last_daily_loss_decision[venue] = decision
            try:
                from trading.notifications import publish_notification

                publish_notification(
                    'risk_data_unavailable',
                    'LIVE 포지션 손익 확인 실패',
                    f'미실현 손익을 확인하지 못해 손실률을 계산하지 않았습니다. 신규 진입만 보류합니다. 원인: {unrealized_reason}',
                    source=venue,
                    execution_mode='live',
                    severity='warning',
                    dedupe_key=f'risk-position-unavailable:live:{venue}:{today.date().isoformat()}',
                )
            except Exception:
                pass
            return decision

        total_pnl = float(realized_pnl + unrealized_pnl)
        self.daily_pnl = total_pnl
        from trading.daily_risk_basis import credential_scope, load_or_create
        scope = credential_scope(self.settings, self.binance_client, venue)
        baseline_key = f'{today.date().isoformat()}:{venue}:{currency}:{scope}'
        initial_equity = self._daily_initial_equity.get(baseline_key, 0.0)
        if initial_equity <= 0:
            if self.daily_initial_balance > 0 and not self._daily_initial_equity:
                # 기존 호출자/테스트가 명시한 시작 잔고를 한 번만 승계한다.
                initial_equity = float(self.daily_initial_balance)
            else:
                # 실행 세션의 추정 기준값. 입출금/외부 거래를 모르면 실제 일 시작
                # 자산은 복원할 수 없다. 거래소 일별 계좌 PnL과 혼동하지 않는다.
                initial_equity = max(0.0, current_equity - total_pnl)
            if initial_equity <= 0:
                initial_equity = current_equity
            if scope:
                try:
                    initial_equity = load_or_create(
                        getattr(self.database_manager, 'db_path', None), today.date().isoformat(),
                        venue, currency, scope, initial_equity)
                except Exception:
                    decision = DailyLossDecision(blocked=True, status='risk_data_unavailable', source=venue,
                        execution_mode=mode, currency=currency, reason='일일 위험 기준 자산 저장/복원 실패')
                    self._last_daily_loss_decision[venue] = decision
                    return decision
            elif self.daily_initial_balance <= 0:
                decision = DailyLossDecision(blocked=True, status='risk_data_unavailable', source=venue,
                    execution_mode=mode, currency=currency, reason='일일 위험 기준 계정 식별 필요')
                self._last_daily_loss_decision[venue] = decision
                return decision
            self._daily_initial_equity[baseline_key] = initial_equity
        self.daily_initial_balance = initial_equity
        self.last_daily_reset = today

        loss_amount = max(0.0, -total_pnl)
        loss_rate = (loss_amount / initial_equity * 100.0) if initial_equity > 0 else 0.0
        stop_trading = loss_amount > 0 and loss_rate > self.max_daily_loss_percent
        status = 'loss_limit_exceeded' if stop_trading else 'ok'
        decision = DailyLossDecision(
            blocked=stop_trading,
            status=status,
            source=venue,
            execution_mode=mode,
            currency=currency,
            initial_equity=initial_equity,
            current_equity=current_equity,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            loss_amount=loss_amount,
            loss_rate=loss_rate,
            reason='일일 손실 한도 초과' if stop_trading else '',
        )
        self._last_daily_loss_decision[venue] = decision
        self.logger.info(
            f"[LIVE 일일 손실 체크] 거래소={venue} 기준자산={initial_equity:.4f} {currency}, "
            f"현재자산={current_equity:.4f} {currency}, 실현={realized_pnl:.4f}, "
            f"미실현={unrealized_pnl:.4f}, 손실률={loss_rate:.2f}%, "
            f"한도={self.max_daily_loss_percent:.2f}%, 중단={'예' if stop_trading else '아니오'}"
        )

        notification_config = self.settings.get('notification_integrations')
        notification_config = notification_config if isinstance(notification_config, dict) else {}
        warning_percent = float(notification_config.get('loss_warning_percent', 5.0) or 5.0)
        if stop_trading:
            try:
                from trading.notifications import publish_notification

                publish_notification(
                    'guardrail_stop',
                    'LIVE 일일 손실 가드레일 거래 중단',
                    f'NoahAI 당일 청산 순손익 {realized_pnl:.4f} + 관리 포지션 미실현 {unrealized_pnl:.4f} = {total_pnl:.4f} {currency}, '
                    f'손실률 {loss_rate:.2f}%가 중단 한도 {self.max_daily_loss_percent:.2f}%를 초과했습니다. '
                    f'당일 고정 위험 기준 자산 {initial_equity:.4f}, 현재 자산 {current_equity:.4f} {currency}. '
                    '최초 확인 시점의 조정 기준이며 거래소 계좌 일별 PnL과 범위가 다릅니다.',
                    source=venue,
                    execution_mode='live',
                    severity='critical',
                    dedupe_key=f'daily-loss-stop:live:{venue}:{today.date().isoformat()}',
                )
            except Exception:
                pass
        elif loss_amount > 0 and loss_rate >= max(0.1, warning_percent):
            try:
                from trading.notifications import publish_notification

                publish_notification(
                    'loss_warning',
                    'LIVE 일일 손실 경고',
                    f'NoahAI 당일 청산 순손익 {realized_pnl:.4f} + 관리 포지션 미실현 {unrealized_pnl:.4f} '
                    f'= {total_pnl:.4f} {currency}, 손실률 {loss_rate:.2f}%입니다. '
                    f'당일 고정 위험 기준 자산 {initial_equity:.4f} {currency}, 중단 한도 {self.max_daily_loss_percent:.2f}%. '
                    '최초 확인 시점의 조정 기준이며 거래소 계좌 일별 PnL과 범위가 다릅니다.',
                    source=venue,
                    execution_mode='live',
                    severity='warning',
                    dedupe_key=f'daily-loss-warning:live:{venue}:{today.date().isoformat()}',
                )
            except Exception:
                pass
        return decision

    def check_daily_loss_limit(
        self,
        source: str = 'binance',
        *,
        execution_mode: Optional[str] = None,
    ) -> bool:
        """기존 bool 계약을 유지하는 일일 손실 가드레일 래퍼."""
        try:
            return self.evaluate_daily_loss_limit(
                source=source,
                execution_mode=execution_mode,
            ).blocked
        except Exception as exc:
            self.logger.error(f"일일 손실 체크 오류: {exc}")
            return True
    
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
