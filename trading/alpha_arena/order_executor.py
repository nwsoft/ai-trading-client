#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alpha Arena 주문 실행기

Binance 선물 API를 직접 호출하여 주문을 실행합니다.
기존 trader.py, unified_trader.py를 사용하지 않는 독립 모듈입니다.
"""

import logging
import math
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

try:
    from api.binance_client import BinanceClient, OrderRequest
except ImportError:
    BinanceClient = None  # type: ignore
    OrderRequest = None  # type: ignore


class OrderExecutor:
    """Alpha Arena 주문 실행기"""
    
    # Alpha Arena 고정 심볼 (USDT 추가)
    ARENA_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'BNBUSDT']
    
    def __init__(self, binance_client: Optional[BinanceClient] = None, settings: Optional[Dict[str, Any]] = None, recorder: Optional[Any] = None):
        """
        Args:
            binance_client: Binance API 클라이언트
            settings: 설정 딕셔너리 (alpha_arena 섹션)
            recorder: Recorder 인스턴스 (데이터베이스 저장용)
        """
        self.binance_client = binance_client
        self.settings = settings or {}
        self.arena_settings = self.settings.get('alpha_arena', {})
        self.recorder = recorder  # 🔥 Recorder 인스턴스 추가
        
        self.logger = logging.getLogger(__name__)
        
        # ExchangeInfo 캐시 (60분 갱신)
        self._exchange_info_cache: Dict[str, Any] = {}
        self._exchange_info_cache_time: Optional[datetime] = None
        self._cache_ttl_minutes = 60
        
        # 심볼별 필터 캐시
        self._symbol_filters_cache: Dict[str, Dict[str, Any]] = {}
        
        # 레버리지 설정 캐시 (심볼별로 한 번만 설정)
        self._leverage_set_cache: Dict[str, Tuple[int, datetime]] = {}  # symbol -> (leverage, set_time)
        
        # 쿨다운 추적 (심볼별 마지막 진입 시간)
        self._cooldown_tracker: Dict[str, float] = {}  # symbol -> timestamp
        self._cooldown_sec = self.arena_settings.get('cooldown_sec_per_symbol', 30)
        
        # 리스크 캡 추적 (틱별)
        self._current_tick_risk_usd = 0.0
        self._max_risk_per_tick = self.arena_settings.get('max_risk_per_tick', 1500.0)
        self._tick_start_time = time.time()
        
        # 동시 포지션 추적
        self._max_concurrent_positions = self.arena_settings.get('max_concurrent_positions', 6)
        
        # 세션 ID (멱등성 보장용)
        self.session_id: Optional[str] = None
    
    def set_session_id(self, session_id: str):
        """세션 ID 설정 (멱등성 보장용)"""
        self.session_id = session_id
    
    def _get_exchange_info(self, force_refresh: bool = False) -> Dict[str, Any]:
        """ExchangeInfo 조회 (캐싱)"""
        try:
            now = datetime.now()
            
            # 캐시 확인
            if not force_refresh and self._exchange_info_cache_time:
                elapsed = (now - self._exchange_info_cache_time).total_seconds() / 60
                if elapsed < self._cache_ttl_minutes:
                    return self._exchange_info_cache
            
            if not self.binance_client or not self.binance_client.client:
                self.logger.warning("Binance 클라이언트가 없어 ExchangeInfo를 조회할 수 없습니다.")
                return {}
            
            # ExchangeInfo 조회
            exchange_info = self.binance_client.client.futures_exchange_info()
            
            # 캐시 업데이트
            self._exchange_info_cache = exchange_info
            self._exchange_info_cache_time = now
            
            self.logger.info(f"ExchangeInfo 캐시 갱신 완료 ({len(exchange_info.get('symbols', []))} 심볼)")
            
            return exchange_info
            
        except Exception as e:
            self.logger.error(f"ExchangeInfo 조회 오류: {e}")
            return self._exchange_info_cache  # 캐시된 값 반환
    
    def _get_symbol_filters(self, symbol: str) -> Dict[str, Any]:
        """심볼 필터 정보 조회 (캐싱)"""
        try:
            # 캐시 확인
            if symbol in self._symbol_filters_cache:
                return self._symbol_filters_cache[symbol]
            
            # BinanceClient의 get_symbol_filters 사용
            if self.binance_client:
                filters = self.binance_client.get_symbol_filters(symbol)
                if filters:
                    self._symbol_filters_cache[symbol] = filters
                    return filters
            
            # 폴백: ExchangeInfo에서 직접 추출
            exchange_info = self._get_exchange_info()
            for sym_info in exchange_info.get('symbols', []):
                if sym_info['symbol'] == symbol:
                    filters = {}
                    for filter_info in sym_info.get('filters', []):
                        filter_type = filter_info.get('filterType')
                        if filter_type == 'LOT_SIZE':
                            filters['minQty'] = float(filter_info.get('minQty', 0))
                            filters['maxQty'] = float(filter_info.get('maxQty', 0))
                            filters['stepSize'] = float(filter_info.get('stepSize', 0))
                        elif filter_type == 'MIN_NOTIONAL':
                            filters['minNotional'] = float(filter_info.get('notional', filter_info.get('minNotional', 0)))
                        elif filter_type == 'PRICE_FILTER':
                            filters['tickSize'] = float(filter_info.get('tickSize', 0))
                            filters['minPrice'] = float(filter_info.get('minPrice', 0))
                            filters['maxPrice'] = float(filter_info.get('maxPrice', 0))
                    
                    filters['quantityPrecision'] = sym_info.get('quantityPrecision', 0)
                    filters['pricePrecision'] = sym_info.get('pricePrecision', 0)
                    
                    self._symbol_filters_cache[symbol] = filters
                    return filters
            
            self.logger.warning(f"심볼 필터 정보를 찾을 수 없습니다: {symbol}")
            return {}
            
        except Exception as e:
            self.logger.error(f"심볼 필터 조회 오류 ({symbol}): {e}")
            return {}
    
    def _round_price(self, symbol: str, price: float) -> float:
        """가격 정밀도 반올림"""
        try:
            filters = self._get_symbol_filters(symbol)
            tick_size = filters.get('tickSize', 0)
            price_precision = filters.get('pricePrecision', 8)
            
            if tick_size > 0:
                # tickSize 기준 반올림
                price = round(price / tick_size) * tick_size
            
            # pricePrecision 자릿수 제한
            price = float(format(price, f'.{price_precision}f'))
            
            return price
            
        except Exception as e:
            self.logger.warning(f"가격 반올림 오류 ({symbol}): {e}")
            return price
    
    def _round_quantity(self, symbol: str, quantity: float) -> float:
        """수량 정밀도 반올림"""
        try:
            filters = self._get_symbol_filters(symbol)
            step_size = filters.get('stepSize', 0)
            min_qty = filters.get('minQty', 0.001)
            quantity_precision = filters.get('quantityPrecision', 8)
            
            if step_size > 0:
                # stepSize 기준 반올림 (ceil 전략)
                quantity = math.ceil(quantity / step_size) * step_size
            
            # minQty 보장
            quantity = max(quantity, min_qty)
            
            # quantityPrecision 자릿수 제한
            quantity = float(format(quantity, f'.{quantity_precision}f'))
            
            return quantity
            
        except Exception as e:
            self.logger.warning(f"수량 반올림 오류 ({symbol}): {e}")
            return quantity
    
    def _check_min_notional(self, symbol: str, quantity: float, price: float) -> Tuple[bool, Optional[str]]:
        """최소 명목금액 검증"""
        try:
            filters = self._get_symbol_filters(symbol)
            min_notional = filters.get('minNotional', 0)
            
            if min_notional <= 0:
                return True, None
            
            notional = quantity * price
            if notional < min_notional:
                return False, f"minNotional 미만: {notional:.2f} < {min_notional:.2f}"
            
            return True, None
            
        except Exception as e:
            self.logger.warning(f"minNotional 검증 오류 ({symbol}): {e}")
            return True, None  # 오류 시 통과
    
    def _count_active_positions(self) -> int:
        """활성 포지션 수 계산 (Alpha Arena 심볼만)"""
        try:
            if not self.binance_client:
                return 0
            
            count = 0
            for symbol in self.ARENA_SYMBOLS:
                try:
                    position_info = self.binance_client.get_position_info(symbol)
                    if position_info:
                        position_amt = float(position_info.get('positionAmt', 0))
                        if abs(position_amt) > 1e-8:  # 포지션 있음
                            count += 1
                except Exception:
                    continue
            
            return count
            
        except Exception as e:
            self.logger.warning(f"활성 포지션 수 계산 오류: {e}")
            return 0  # 오류 시 0 반환
    
    def _ensure_leverage_and_margin(self, symbol: str, leverage: int) -> bool:
        """레버리지 및 마진 모드 설정 (1회만)"""
        try:
            # 레버리지 클램핑 (10~20)
            leverage_min = self.arena_settings.get('leverage_min', 10)
            leverage_max = self.arena_settings.get('leverage_max', 20)
            leverage = max(leverage_min, min(leverage, leverage_max))
            
            # 캐시 확인 (이미 설정된 경우 스킵)
            if symbol in self._leverage_set_cache:
                cached_leverage, set_time = self._leverage_set_cache[symbol]
                # 1시간 이내면 재설정 스킵
                if (datetime.now() - set_time).total_seconds() < 3600:
                    if cached_leverage == leverage:
                        return True
                    else:
                        self.logger.info(f"[{symbol}] 레버리지 변경 필요: {cached_leverage} → {leverage}")
            
            if not self.binance_client or not self.binance_client.client:
                self.logger.warning(f"Binance 클라이언트가 없어 레버리지 설정을 할 수 없습니다: {symbol}")
                return False
            
            # 마진 모드 설정 (isolated)
            try:
                self.binance_client.client.futures_change_margin_type(
                    symbol=symbol,
                    marginType='ISOLATED'
                )
                self.logger.info(f"[{symbol}] 마진 모드 ISOLATED 설정 완료")
            except Exception as e:
                # 이미 설정된 경우 무시
                if "No need to change margin type" not in str(e):
                    self.logger.warning(f"[{symbol}] 마진 모드 설정 오류 (무시): {e}")
            
            # 레버리지 설정
            try:
                self.binance_client.client.futures_change_leverage(
                    symbol=symbol,
                    leverage=leverage
                )
                self.logger.info(f"[{symbol}] 레버리지 {leverage}x 설정 완료")
                
                # 캐시 업데이트
                self._leverage_set_cache[symbol] = (leverage, datetime.now())
                return True
                
            except Exception as e:
                self.logger.error(f"[{symbol}] 레버리지 설정 오류: {e}")
                return False
                
        except Exception as e:
            self.logger.error(f"레버리지/마진 설정 오류 ({symbol}): {e}")
            return False
    
    def _generate_order_id(self, symbol: str) -> str:
        """멱등성 보장 주문 ID 생성"""
        if not self.session_id:
            self.session_id = f"arena_{int(time.time())}"
        
        unique_id = str(uuid.uuid4()).replace('-', '')[:12]
        return f"arena:{self.session_id}:{symbol}:{unique_id}"
    
    def _reset_tick_tracking(self):
        """틱 추적 리셋 (새 틱 시작)"""
        self._current_tick_risk_usd = 0.0
        self._tick_start_time = time.time()
    
    def execute_trading_decision(self, symbol: str, decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        거래 결정 실행
        
        Args:
            symbol: 심볼 (예: 'BTCUSDT')
            decision: TRADING_DECISIONS의 심볼별 결정 딕셔너리
        
        Returns:
            {
                'status': 'SUCCESS' | 'SKIPPED' | 'ERROR',
                'order_id': str (optional),
                'error': str (optional),
                'skip_reason': str (optional)
            }
        """
        try:
            signal = decision.get('signal', '').upper()
            
            # 신호 검증
            valid_signals = ['HOLD', 'CLOSE', 'ENTER_LONG', 'ENTER_SHORT']
            if signal not in valid_signals:
                return {
                    'status': 'SKIPPED',
                    'skip_reason': f"유효하지 않은 신호: {signal}"
                }
            
            # HOLD는 주문 없음
            if signal == 'HOLD':
                return {
                    'status': 'SKIPPED',
                    'skip_reason': 'HOLD 신호 (주문 없음)'
                }
            
            # CLOSE는 청산 주문
            if signal == 'CLOSE':
                return self._execute_close_order(symbol, decision)
            
            # ENTER_*는 진입 주문
            if signal in ['ENTER_LONG', 'ENTER_SHORT']:
                return self._execute_enter_order(symbol, decision)
            
            return {
                'status': 'ERROR',
                'error': f"처리되지 않은 신호: {signal}"
            }
            
        except Exception as e:
            self.logger.error(f"거래 결정 실행 오류 ({symbol}): {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {
                'status': 'ERROR',
                'error': str(e)
            }
    
    def _execute_close_order(self, symbol: str, decision: Dict[str, Any]) -> Dict[str, Any]:
        """청산 주문 실행"""
        try:
            if not self.binance_client:
                return {'status': 'ERROR', 'error': 'Binance 클라이언트 없음'}
            
            # 현재 포지션 확인
            position_info = self.binance_client.get_position_info(symbol)
            if not position_info:
                return {
                    'status': 'SKIPPED',
                    'skip_reason': '포지션 없음'
                }
            
            position_amt = float(position_info.get('positionAmt', 0))
            if abs(position_amt) < 1e-8:
                return {
                    'status': 'SKIPPED',
                    'skip_reason': '포지션 수량 없음'
                }
            
            # 시장가 청산 (closePosition=True)
            side = 'SELL' if position_amt > 0 else 'BUY'
            
            # 진입 정보 저장 (DB 업데이트용)
            entry_price = float(position_info.get('entryPrice', 0))
            entry_quantity = abs(position_amt)
            leverage = int(position_info.get('leverage', 1))
            unrealized_pnl = float(position_info.get('unRealizedProfit', 0))
            
            order_result = self.binance_client.place_futures_order(
                symbol=symbol,
                side=side,
                order_type='MARKET',
                close_position=True
            )
            
            if order_result.get('status') in ['FILLED', 'PENDING']:
                # 🔥 데이터베이스에 청산 정보 업데이트
                try:
                    if self.recorder:
                        from trading.recorder import TradeLog
                        # 실제 청산 가격 (order_result에서 가져오기)
                        exit_price = float(order_result.get('price', 0))
                        if exit_price <= 0:
                            # 현재가로 대체
                            exit_price = self.binance_client.get_current_price(symbol)
                        
                        # PnL 계산
                        if entry_price > 0:
                            if side == 'SELL':  # LONG 포지션 청산
                                pnl = (exit_price - entry_price) * entry_quantity
                            else:  # SHORT 포지션 청산
                                pnl = (entry_price - exit_price) * entry_quantity
                            
                            pnl_percent = (pnl / (entry_price * entry_quantity)) * 100 if entry_price * entry_quantity > 0 else 0
                        else:
                            pnl = unrealized_pnl
                            pnl_percent = 0.0
                        
                        # 기존 거래 로그 찾기 (진입 시 저장된 것)
                        # 심볼과 진입 시간으로 찾기 (최근 것)
                        # 🔥 recorder의 db_path 사용 (사용자별 경로 보장)
                        if not self.recorder or not hasattr(self.recorder, 'db_path'):
                            self.logger.warning(f"[{symbol}] Recorder 또는 db_path가 없어 청산 정보 업데이트 불가")
                        else:
                            db_path = self.recorder.db_path
                            
                            if os.path.exists(db_path):
                                import sqlite3
                                with sqlite3.connect(db_path) as conn:
                                    cursor = conn.cursor()
                                    # 가장 최근의 미청산 거래 찾기
                                    cursor.execute("""
                                        SELECT id FROM trade_log
                                        WHERE symbol = ? AND exit_time IS NULL
                                        ORDER BY entry_time DESC
                                        LIMIT 1
                                    """, (symbol,))
                                    row = cursor.fetchone()
                                    
                                    if row:
                                        trade_id = row[0]
                                        # 업데이트
                                        cursor.execute("""
                                            UPDATE trade_log
                                            SET exit_price = ?,
                                                exit_time = ?,
                                                pnl = ?,
                                                pnl_percent = ?
                                            WHERE id = ?
                                        """, (exit_price, datetime.now(), pnl, pnl_percent, trade_id))
                                        conn.commit()
                                        self.logger.info(f"[{symbol}] 청산 정보 데이터베이스 업데이트 완료 (ID: {trade_id})")
                                    else:
                                        # 기존 거래 로그가 없으면 새로 생성
                                        trade_log = TradeLog(
                                            id=None,
                                            symbol=symbol,
                                            entry_price=entry_price,
                                            exit_price=exit_price,
                                            quantity=entry_quantity,
                                            leverage=leverage,
                                            pnl=pnl,
                                            pnl_percent=pnl_percent,
                                            entry_time=datetime.now() - timedelta(seconds=60),  # 대략적인 진입 시간
                                            exit_time=datetime.now(),
                                            reason="Alpha Arena CLOSE",
                                            side=side,
                                            tp_price=None,
                                            sl_price=None,
                                            fees=0.0,
                                            slippage=0.0,
                                            exchange='binance'
                                        )
                                        self.recorder.insert_trade_log(trade_log)
                                        self.logger.info(f"[{symbol}] 청산 거래 로그 데이터베이스 저장 완료")
                except Exception as db_err:
                    self.logger.warning(f"[{symbol}] 청산 정보 데이터베이스 업데이트 실패: {db_err}")
                    # DB 업데이트 실패해도 청산은 성공으로 처리
                
                return {
                    'status': 'SUCCESS',
                    'order_id': str(order_result.get('order_id', '')),
                    'order_result': order_result
                }
            else:
                return {
                    'status': 'ERROR',
                    'error': order_result.get('error', '청산 주문 실패')
                }
                
        except Exception as e:
            self.logger.error(f"청산 주문 실행 오류 ({symbol}): {e}")
            return {
                'status': 'ERROR',
                'error': str(e)
            }
    
    def _execute_enter_order(self, symbol: str, decision: Dict[str, Any]) -> Dict[str, Any]:
        """진입 주문 실행 (게이트 검증 포함)"""
        try:
            # 게이트 검증
            gate_result = self._check_trade_gates(symbol, decision)
            if not gate_result['allowed']:
                return {
                    'status': 'SKIPPED',
                    'skip_reason': gate_result['reason']
                }
            
            if not self.binance_client:
                return {'status': 'ERROR', 'error': 'Binance 클라이언트 없음'}
            
            # 레버리지 설정
            leverage = decision.get('leverage', 10)
            if not self._ensure_leverage_and_margin(symbol, leverage):
                return {
                    'status': 'ERROR',
                    'error': '레버리지/마진 설정 실패'
                }
            
            # 수량/가격 계산
            quantity = decision.get('quantity')
            notional_usd = decision.get('notional_usd')
            current_price = self.binance_client.get_current_price(symbol)
            
            if not quantity and notional_usd:
                # notional_usd를 수량으로 변환
                if current_price > 0:
                    quantity = notional_usd / current_price
                else:
                    return {
                        'status': 'ERROR',
                        'error': '현재가 조회 실패'
                    }
            
            if not quantity or quantity <= 0:
                return {
                    'status': 'ERROR',
                    'error': '수량 정보 없음'
                }
            
            # 정밀도 반올림
            quantity = self._round_quantity(symbol, quantity)
            
            # minNotional 검증
            is_valid, error_msg = self._check_min_notional(symbol, quantity, current_price)
            if not is_valid:
                return {
                    'status': 'SKIPPED',
                    'skip_reason': error_msg or 'minNotional 미만'
                }
            
            # 진입 주문 실행
            signal = decision.get('signal', '').upper()
            side = 'BUY' if signal == 'ENTER_LONG' else 'SELL'
            
            order_result = self.binance_client.place_futures_order(
                symbol=symbol,
                side=side,
                order_type='MARKET',
                quantity=quantity
            )
            
            if order_result.get('status') not in ['FILLED', 'PENDING']:
                return {
                    'status': 'ERROR',
                    'error': order_result.get('error', '진입 주문 실패')
                }
            
            order_id = str(order_result.get('order_id', ''))
            
            # TP/SL 주문 생성
            profit_target = decision.get('profit_target')
            stop_loss = decision.get('stop_loss')
            
            tp_result = None
            sl_result = None
            
            if profit_target:
                tp_result = self._create_tp_order(symbol, profit_target, side)
            
            if stop_loss:
                sl_result = self._create_sl_order(symbol, stop_loss, side)
            
            # 쿨다운 추적 업데이트
            self._cooldown_tracker[symbol] = time.time()
            
            # 리스크 추적 업데이트
            risk_usd = decision.get('risk_usd', 0)
            if risk_usd > 0:
                self._current_tick_risk_usd += risk_usd
            
            # 🔥 데이터베이스에 거래 로그 저장
            try:
                if self.recorder:
                    from trading.recorder import TradeLog
                    # 실제 체결 가격 (order_result에서 가져오기)
                    filled_price = float(order_result.get('price', current_price))
                    if filled_price <= 0:
                        filled_price = current_price
                    
                    trade_log = TradeLog(
                        id=None,
                        symbol=symbol,
                        entry_price=filled_price,
                        exit_price=None,  # 진입 시에는 미청산 상태
                        quantity=quantity,
                        leverage=leverage,
                        pnl=None,  # 청산 시에만 설정
                        pnl_percent=None,
                        entry_time=datetime.now(),
                        exit_time=None,  # 청산 시에만 설정
                        reason=f"Alpha Arena {signal}",
                        side=side,
                        tp_price=profit_target,
                        sl_price=stop_loss,
                        fees=0.0,  # 진입 시에는 수수료 0 (청산 시 계산)
                        slippage=0.0,
                        exchange='binance'
                    )
                    self.recorder.insert_trade_log(trade_log)
                    self.logger.info(f"[{symbol}] 거래 로그 데이터베이스 저장 완료")
            except Exception as db_err:
                self.logger.warning(f"[{symbol}] 거래 로그 데이터베이스 저장 실패: {db_err}")
                # DB 저장 실패해도 주문은 성공으로 처리
            
            return {
                'status': 'SUCCESS',
                'order_id': order_id,
                'order_result': order_result,
                'tp_order': tp_result,
                'sl_order': sl_result
            }
            
        except Exception as e:
            self.logger.error(f"진입 주문 실행 오류 ({symbol}): {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {
                'status': 'ERROR',
                'error': str(e)
            }
    
    def _check_trade_gates(self, symbol: str, decision: Dict[str, Any]) -> Dict[str, Any]:
        """주문 게이트 검증"""
        try:
            # 1. 신호 검증
            signal = decision.get('signal', '').upper()
            if signal not in ['ENTER_LONG', 'ENTER_SHORT']:
                return {'allowed': False, 'reason': f'진입 신호 아님: {signal}'}
            
            # 2. TP/SL 필수 검증
            profit_target = decision.get('profit_target')
            stop_loss = decision.get('stop_loss')
            
            if profit_target is None:
                return {'allowed': False, 'reason': 'profit_target 누락'}
            if stop_loss is None:
                return {'allowed': False, 'reason': 'stop_loss 누락'}
            
            # 3. 정밀도 검증 (나중에 실행 단계에서 처리)
            
            # 4. 레버리지 범위 검증 (클램핑으로 처리)
            leverage = decision.get('leverage', 10)
            leverage_min = self.arena_settings.get('leverage_min', 10)
            leverage_max = self.arena_settings.get('leverage_max', 20)
            
            if leverage < leverage_min or leverage > leverage_max:
                # 클램핑으로 처리 (경고만)
                self.logger.warning(f"[{symbol}] 레버리지 범위 벗어남: {leverage} (클램핑 예정)")
            
            # 5. 리스크 캡 검증
            risk_usd = decision.get('risk_usd', 0)
            if risk_usd > 0:
                if self._current_tick_risk_usd + risk_usd > self._max_risk_per_tick:
                    return {
                        'allowed': False,
                        'reason': f'리스크 캡 초과: {self._current_tick_risk_usd + risk_usd:.2f} > {self._max_risk_per_tick:.2f}'
                    }
            
            # 6. 쿨다운 검증
            if symbol in self._cooldown_tracker:
                last_enter_time = self._cooldown_tracker[symbol]
                elapsed = time.time() - last_enter_time
                if elapsed < self._cooldown_sec:
                    return {
                        'allowed': False,
                        'reason': f'쿨다운 미경과: {elapsed:.1f}s < {self._cooldown_sec}s'
                    }
            
            # 7. 최대 동시 포지션 검증 (현재 포지션 수 확인)
            current_positions = self._count_active_positions()
            if current_positions >= self._max_concurrent_positions:
                return {
                    'allowed': False,
                    'reason': f'최대 동시 포지션 초과: {current_positions} >= {self._max_concurrent_positions}'
                }
            
            return {'allowed': True, 'reason': None}
            
        except Exception as e:
            self.logger.error(f"게이트 검증 오류 ({symbol}): {e}")
            return {'allowed': False, 'reason': f'검증 오류: {str(e)}'}
    
    def _create_tp_order(self, symbol: str, profit_target: float, entry_side: str) -> Optional[Dict[str, Any]]:
        """
        TP 주문 생성
        
        주의:
            - 2025-12-09 이후 Binance 정책 변경: TAKE_PROFIT_MARKET은 Algo Order API 사용 필수
            - place_futures_order()는 내부에서 자동으로 /fapi/v1/algoOrder로 라우팅함
        """
        try:
            if not self.binance_client:
                return None
            
            # 가격 정밀도 반올림
            stop_price = self._round_price(symbol, profit_target)
            
            # TP는 반대 방향으로 청산
            close_side = 'SELL' if entry_side == 'BUY' else 'BUY'
            
            # workingType 파라미터 (바이낸스 API 필수)
            working_type = self.arena_settings.get('workingType', 'MARK_PRICE')
            
            # 🔥 place_futures_order()는 조건부 주문을 자동으로 Algo Order API로 라우팅함
            order_result = self.binance_client.place_futures_order(
                symbol=symbol,
                side=close_side,
                order_type='TAKE_PROFIT_MARKET',
                stop_price=stop_price,
                close_position=True,
                working_type=working_type  # ✅ 바이낸스 API 필수 파라미터
            )
            
            if order_result.get('status') in ['FILLED', 'NEW', 'PENDING']:
                return order_result
            else:
                self.logger.warning(f"[{symbol}] TP 주문 생성 실패: {order_result.get('error')}")
                return None
                
        except Exception as e:
            self.logger.error(f"TP 주문 생성 오류 ({symbol}): {e}")
            return None
    
    def _create_sl_order(self, symbol: str, stop_loss: float, entry_side: str) -> Optional[Dict[str, Any]]:
        """
        SL 주문 생성
        
        주의:
            - 2025-12-09 이후 Binance 정책 변경: STOP_MARKET은 Algo Order API 사용 필수
            - place_futures_order()는 내부에서 자동으로 /fapi/v1/algoOrder로 라우팅함
        """
        try:
            if not self.binance_client:
                return None
            
            # 가격 정밀도 반올림
            stop_price = self._round_price(symbol, stop_loss)
            
            # SL은 반대 방향으로 청산
            close_side = 'SELL' if entry_side == 'BUY' else 'BUY'
            
            # workingType 파라미터 (바이낸스 API 필수)
            working_type = self.arena_settings.get('workingType', 'MARK_PRICE')
            
            # 🔥 place_futures_order()는 조건부 주문을 자동으로 Algo Order API로 라우팅함
            order_result = self.binance_client.place_futures_order(
                symbol=symbol,
                side=close_side,
                order_type='STOP_MARKET',
                stop_price=stop_price,
                close_position=True,
                working_type=working_type  # ✅ 바이낸스 API 필수 파라미터
            )
            
            if order_result.get('status') in ['FILLED', 'NEW', 'PENDING']:
                return order_result
            else:
                self.logger.warning(f"[{symbol}] SL 주문 생성 실패: {order_result.get('error')}")
                return None
                
        except Exception as e:
            self.logger.error(f"SL 주문 생성 오류 ({symbol}): {e}")
            return None

