#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
고급 주문 기능: OCO, 트레일링 스탑, 조건부 주문
"""

import time
import logging
import asyncio
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

class OrderType(Enum):
    """주문 타입"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    OCO = "OCO"
    TRAILING_STOP = "TRAILING_STOP"

class OrderStatus(Enum):
    """주문 상태"""
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"

@dataclass
class TrailingStopConfig:
    """트레일링 스탑 설정"""
    callback_rate: float  # 트레일링 비율 (0.01 = 1%)
    activation_price: Optional[float] = None  # 활성화 가격
    max_trail_distance: Optional[float] = None  # 최대 트레일링 거리
    min_trail_distance: Optional[float] = None  # 최소 트레일링 거리

@dataclass
class OCOConfig:
    """OCO 주문 설정"""
    take_profit_price: float  # 이익실현 가격
    stop_loss_price: float   # 손절 가격
    tp_limit_price: Optional[float] = None  # TP 리미트 가격
    sl_limit_price: Optional[float] = None  # SL 리미트 가격

@dataclass
class AdvancedOrder:
    """고급 주문"""
    id: str
    symbol: str
    side: str  # BUY, SELL
    order_type: OrderType
    quantity: float
    status: OrderStatus
    created_at: datetime
    
    # 기본 가격 정보
    entry_price: Optional[float] = None
    current_price: Optional[float] = None
    
    # OCO 설정
    oco_config: Optional[OCOConfig] = None
    
    # 트레일링 스탑 설정
    trailing_config: Optional[TrailingStopConfig] = None
    
    # 트레일링 상태
    best_price: Optional[float] = None  # 최고/최저 가격
    trail_stop_price: Optional[float] = None  # 현재 트레일링 손절가
    
    # 바이낸스 주문 ID들
    binance_order_ids: List[str] = field(default_factory=list)
    
    # 실행 상태
    is_monitoring: bool = False
    last_update: Optional[datetime] = None

class AdvancedOrderManager:
    """고급 주문 관리자"""
    
    def __init__(self, binance_client, websocket_manager):
        self.binance_client = binance_client
        self.websocket_manager = websocket_manager
        self.logger = logging.getLogger(__name__)
        
        # 활성 주문들
        self.active_orders: Dict[str, AdvancedOrder] = {}
        
        # 모니터링 스레드
        self.monitoring_active = False
        self.monitoring_thread = None
        
        # 가격 데이터 캐시
        self.price_cache: Dict[str, float] = {}
        self.last_price_update: Dict[str, datetime] = {}
        
        self.logger.info("AdvancedOrderManager 초기화 완료")
    
    def create_oco_order(self, symbol: str, side: str, quantity: float, 
                        oco_config: OCOConfig, position_side: str = "BOTH") -> str:
        """OCO 주문 생성"""
        try:
            order_id = f"oco_{symbol}_{int(time.time())}"
            
            # OCO 주문 객체 생성
            oco_order = AdvancedOrder(
                id=order_id,
                symbol=symbol,
                side=side,
                order_type=OrderType.OCO,
                quantity=quantity,
                status=OrderStatus.PENDING,
                created_at=datetime.now(),
                oco_config=oco_config
            )
            
            # 바이낸스에 OCO 주문 전송
            try:
                # 🔥 2025-12-09 이후 Binance 정책 변경: 조건부 주문은 Algo Order API 사용 필수
                # TAKE_PROFIT_MARKET, STOP_MARKET은 place_futures_order()를 통해 자동으로 /fapi/v1/algoOrder로 라우팅됨
                # 🔥 Binance API 공식 규칙 준수: closePosition=True 사용 (quantity 제거)
                # 바이낸스 선물에서는 OCO를 별도 TP/SL 주문으로 구현
                tp_order_result = self.binance_client.place_futures_order(
                    symbol=symbol,
                    side=side,
                    order_type='TAKE_PROFIT_MARKET',
                    stop_price=oco_config.take_profit_price,
                    close_position=True,  # 🔥 closePosition=True 사용 (quantity 불필요)
                    working_type='MARK_PRICE'
                )
                
                sl_order_result = self.binance_client.place_futures_order(
                    symbol=symbol,
                    side=side,
                    order_type='STOP_MARKET',
                    stop_price=oco_config.stop_loss_price,
                    close_position=True,  # 🔥 closePosition=True 사용 (quantity 불필요)
                    working_type='MARK_PRICE'
                )
                
                # 결과에서 orderId 추출
                tp_order_id = tp_order_result.get('order_id') if tp_order_result.get('status') != 'ERROR' else None
                sl_order_id = sl_order_result.get('order_id') if sl_order_result.get('status') != 'ERROR' else None
                
                if not tp_order_id or not sl_order_id:
                    error_msg = f"TP/SL 주문 생성 실패: TP={tp_order_result.get('error', 'Unknown')}, SL={sl_order_result.get('error', 'Unknown')}"
                    self.logger.error(error_msg)
                    raise Exception(error_msg)
                
                # 바이낸스 주문 ID 저장
                oco_order.binance_order_ids = [
                    str(tp_order_id),
                    str(sl_order_id)
                ]
                oco_order.status = OrderStatus.ACTIVE
                
                # 활성 주문에 추가
                self.active_orders[order_id] = oco_order
                
                # 모니터링 시작
                self._start_order_monitoring(order_id)
                
                self.logger.info(f"OCO 주문 생성 성공: {order_id}")
                return order_id
                
            except Exception as e:
                self.logger.error(f"바이낸스 OCO 주문 실패: {e}")
                oco_order.status = OrderStatus.FAILED
                raise
                
        except Exception as e:
            self.logger.error(f"OCO 주문 생성 오류: {e}")
            raise
    
    def create_trailing_stop_order(self, symbol: str, side: str, quantity: float,
                                 trailing_config: TrailingStopConfig,
                                 entry_price: float) -> str:
        """트레일링 스탑 주문 생성"""
        try:
            order_id = f"trail_{symbol}_{int(time.time())}"
            
            # 초기 트레일링 스탑 가격 계산
            if side == "SELL":  # 롱 포지션 청산
                initial_stop_price = entry_price * (1 - trailing_config.callback_rate)
                best_price = entry_price
            else:  # 숏 포지션 청산
                initial_stop_price = entry_price * (1 + trailing_config.callback_rate)
                best_price = entry_price
            
            # 트레일링 스탑 주문 객체 생성
            trailing_order = AdvancedOrder(
                id=order_id,
                symbol=symbol,
                side=side,
                order_type=OrderType.TRAILING_STOP,
                quantity=quantity,
                status=OrderStatus.ACTIVE,
                created_at=datetime.now(),
                entry_price=entry_price,
                trailing_config=trailing_config,
                best_price=best_price,
                trail_stop_price=initial_stop_price,
                is_monitoring=True
            )
            
            # 활성 주문에 추가
            self.active_orders[order_id] = trailing_order
            
            # 실시간 모니터링 시작
            self._start_trailing_monitoring(order_id)
            
            self.logger.info(f"트레일링 스탑 주문 생성: {order_id}, 초기 손절가: {initial_stop_price:.2f}")
            return order_id
            
        except Exception as e:
            self.logger.error(f"트레일링 스탑 주문 생성 오류: {e}")
            raise
    
    def _start_order_monitoring(self, order_id: str):
        """주문 모니터링 시작"""
        def monitor_order():
            try:
                order = self.active_orders.get(order_id)
                if not order:
                    return
                
                while order.status == OrderStatus.ACTIVE:
                    # 주문 상태 확인
                    self._check_order_status(order_id)
                    time.sleep(5)  # 5초마다 확인
                    
            except Exception as e:
                self.logger.error(f"주문 모니터링 오류 ({order_id}): {e}")
        
        thread = threading.Thread(target=monitor_order, daemon=True)
        thread.start()
    
    def _start_trailing_monitoring(self, order_id: str):
        """트레일링 스탑 실시간 모니터링"""
        def monitor_trailing():
            try:
                order = self.active_orders.get(order_id)
                if not order or not order.trailing_config:
                    return
                
                self.logger.info(f"트레일링 모니터링 시작: {order_id}")
                
                while order.status == OrderStatus.ACTIVE:
                    # 현재 가격 가져오기
                    current_price = self._get_current_price(order.symbol)
                    if not current_price:
                        time.sleep(1)
                        continue
                    
                    order.current_price = current_price
                    order.last_update = datetime.now()
                    
                    # 트레일링 로직 실행
                    self._update_trailing_stop(order_id, current_price)
                    
                    time.sleep(1)  # 1초마다 업데이트
                    
            except Exception as e:
                self.logger.error(f"트레일링 모니터링 오류 ({order_id}): {e}")
                if order_id in self.active_orders:
                    self.active_orders[order_id].status = OrderStatus.FAILED
        
        thread = threading.Thread(target=monitor_trailing, daemon=True)
        thread.start()
    
    def _update_trailing_stop(self, order_id: str, current_price: float):
        """트레일링 스탑 업데이트"""
        try:
            order = self.active_orders.get(order_id)
            if not order or not order.trailing_config:
                return

            config = order.trailing_config

            # best_price와 trail_stop_price가 None일 수 있으므로 비교 전에 체크
            if order.side == "SELL":  # 롱 포지션 청산
                # 가격이 상승하면 best_price 업데이트
                if order.best_price is not None and current_price > order.best_price:
                    order.best_price = current_price

                    # 새로운 트레일링 스탑 가격 계산
                    new_stop_price = current_price * (1 - config.callback_rate)

                    # 손절가는 올라가기만 함
                    if order.trail_stop_price is not None and new_stop_price > order.trail_stop_price:
                        old_stop_price = order.trail_stop_price
                        order.trail_stop_price = new_stop_price

                        self.logger.info(f"트레일링 업데이트 ({order_id}): "
                                       f"가격 {current_price:.2f}, "
                                       f"손절가 {old_stop_price:.2f} → {new_stop_price:.2f}")

                # 손절 조건 확인
                if order.trail_stop_price is not None and current_price <= order.trail_stop_price:
                    self._execute_trailing_stop(order_id, "손절 조건 도달")

            else:  # 숏 포지션 청산
                # 가격이 하락하면 best_price 업데이트
                if order.best_price is not None and current_price < order.best_price:
                    order.best_price = current_price

                    # 새로운 트레일링 스탑 가격 계산
                    new_stop_price = current_price * (1 + config.callback_rate)

                    # 손절가는 내려가기만 함
                    if order.trail_stop_price is not None and new_stop_price < order.trail_stop_price:
                        old_stop_price = order.trail_stop_price
                        order.trail_stop_price = new_stop_price

                        self.logger.info(f"트레일링 업데이트 ({order_id}): "
                                       f"가격 {current_price:.2f}, "
                                       f"손절가 {old_stop_price:.2f} → {new_stop_price:.2f}")

                # 손절 조건 확인
                if order.trail_stop_price is not None and current_price >= order.trail_stop_price:
                    self._execute_trailing_stop(order_id, "손절 조건 도달")

        except Exception as e:
            self.logger.error(f"트레일링 스탑 업데이트 오류 ({order_id}): {e}")
    
    def _execute_trailing_stop(self, order_id: str, reason: str):
        """트레일링 스탑 실행"""
        try:
            order = self.active_orders.get(order_id)
            if not order:
                return
            
            self.logger.warning(f"트레일링 스탑 실행: {order_id}, 사유: {reason}")
            
            # 시장가 매도 주문 실행
            result = self.binance_client.futures_create_order(
                symbol=order.symbol,
                side=order.side,
                type='MARKET',
                quantity=order.quantity,
                reduceOnly=True
            )
            
            # 주문 상태 업데이트
            order.status = OrderStatus.FILLED
            order.binance_order_ids.append(str(result['orderId']))
            
            # 실행 정보 로깅
            executed_price = float(result.get('avgPrice', order.current_price))
            if order.entry_price is not None:
                profit_pct = ((executed_price - order.entry_price) / order.entry_price) * 100
                self.logger.info(f"트레일링 스탑 체결: {order.symbol}, "
                               f"진입가: {order.entry_price:.2f}, "
                               f"체결가: {executed_price:.2f}, "
                               f"수익률: {profit_pct:+.2f}%")
            else:
                self.logger.info(f"트레일링 스탑 체결: {order.symbol}, "
                               f"진입가: None, "
                               f"체결가: {executed_price:.2f}, "
                               f"수익률: 계산 불가 (entry_price 없음)")

            return result
            
        except Exception as e:
            self.logger.error(f"트레일링 스탑 실행 오류 ({order_id}): {e}")
            if order_id in self.active_orders:
                self.active_orders[order_id].status = OrderStatus.FAILED
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """현재 가격 조회 (캐시 활용)"""
        try:
            # 캐시 확인 (5초 이내 데이터는 재사용)
            now = datetime.now()
            if (symbol in self.price_cache and 
                symbol in self.last_price_update and
                (now - self.last_price_update[symbol]).seconds < 5):
                return self.price_cache[symbol]
            
            # WebSocket에서 최신 가격 가져오기
            if self.binance_client and hasattr(self.binance_client, 'get_latest_ticker'):
                try:
                    ticker_data = self.binance_client.get_latest_ticker(symbol)
                    if ticker_data and 'c' in ticker_data:
                        price = float(ticker_data['c'])
                        self.price_cache[symbol] = price
                        self.last_price_update[symbol] = now
                        return price
                except Exception as e:
                    self.logger.warning(f"WebSocket 가격 조회 실패 ({symbol}): {e}")
            
            # 대체: REST API 호출
            ticker = self.binance_client.get_symbol_ticker(symbol=symbol)
            if ticker:
                price = float(ticker['price'])
                self.price_cache[symbol] = price
                self.last_price_update[symbol] = now
                return price
            
            return None
            
        except Exception as e:
            self.logger.error(f"현재 가격 조회 오류 ({symbol}): {e}")
            return None
    
    def _check_order_status(self, order_id: str):
        """주문 상태 확인 (OCO용)"""
        try:
            order = self.active_orders.get(order_id)
            if not order or not order.binance_order_ids:
                return
            
            # 각 바이낸스 주문 상태 확인
            for binance_order_id in order.binance_order_ids:
                order_status = self.binance_client.futures_get_order(
                    symbol=order.symbol,
                    orderId=binance_order_id
                )
                
                if order_status['status'] == 'FILLED':
                    # 체결된 주문이 있으면 나머지 취소
                    self._cancel_remaining_orders(order_id, binance_order_id)
                    order.status = OrderStatus.FILLED
                    
                    self.logger.info(f"OCO 주문 체결: {order_id}, "
                                   f"체결 주문: {binance_order_id}")
                    break
                    
        except Exception as e:
            self.logger.error(f"주문 상태 확인 오류 ({order_id}): {e}")
    
    def _cancel_remaining_orders(self, order_id: str, filled_order_id: str):
        """OCO에서 체결되지 않은 주문들 취소"""
        try:
            order = self.active_orders.get(order_id)
            if not order:
                return
            
            for binance_order_id in order.binance_order_ids:
                if binance_order_id != filled_order_id:
                    try:
                        self.binance_client.futures_cancel_order(
                            symbol=order.symbol,
                            orderId=binance_order_id
                        )
                        self.logger.info(f"OCO 나머지 주문 취소: {binance_order_id}")
                    except Exception as e:
                        self.logger.warning(f"주문 취소 실패 ({binance_order_id}): {e}")
                        
        except Exception as e:
            self.logger.error(f"나머지 주문 취소 오류: {e}")
    
    def cancel_order(self, order_id: str, reason: str = "사용자 요청") -> bool:
        """주문 취소"""
        try:
            order = self.active_orders.get(order_id)
            if not order:
                self.logger.warning(f"취소할 주문을 찾을 수 없음: {order_id}")
                return False
            
            # 바이낸스 주문들 취소
            cancelled_count = 0
            for binance_order_id in order.binance_order_ids:
                try:
                    self.binance_client.futures_cancel_order(
                        symbol=order.symbol,
                        orderId=binance_order_id
                    )
                    cancelled_count += 1
                except Exception as e:
                    self.logger.warning(f"주문 취소 실패 ({binance_order_id}): {e}")
            
            # 주문 상태 업데이트
            order.status = OrderStatus.CANCELLED
            order.is_monitoring = False
            
            self.logger.info(f"주문 취소 완료: {order_id}, "
                           f"취소된 주문 수: {cancelled_count}, 사유: {reason}")
            return True
            
        except Exception as e:
            self.logger.error(f"주문 취소 오류 ({order_id}): {e}")
            return False
    
    def get_active_orders(self) -> List[Dict[str, Any]]:
        """활성 주문 목록 조회"""
        try:
            active_list = []
            for order_id, order in self.active_orders.items():
                if order.status in [OrderStatus.ACTIVE, OrderStatus.PENDING]:
                    order_info = {
                        "order_id": order_id,
                        "symbol": order.symbol,
                        "type": order.order_type.value,
                        "side": order.side,
                        "quantity": order.quantity,
                        "status": order.status.value,
                        "created_at": order.created_at.isoformat(),
                        "current_price": order.current_price,
                        "entry_price": order.entry_price
                    }
                    
                    # 트레일링 스탑 정보 추가
                    if order.order_type == OrderType.TRAILING_STOP:
                        order_info.update({
                            "trail_stop_price": order.trail_stop_price,
                            "best_price": order.best_price,
                            "callback_rate": order.trailing_config.callback_rate if order.trailing_config else None
                        })
                    
                    # OCO 정보 추가
                    elif order.order_type == OrderType.OCO:
                        if order.oco_config:
                            order_info.update({
                                "take_profit_price": order.oco_config.take_profit_price,
                                "stop_loss_price": order.oco_config.stop_loss_price
                            })
                    
                    active_list.append(order_info)
            
            return active_list
            
        except Exception as e:
            self.logger.error(f"활성 주문 조회 오류: {e}")
            return []
    
    def get_order_performance_stats(self) -> Dict[str, Any]:
        """주문 성과 통계"""
        try:
            all_orders = list(self.active_orders.values())
            filled_orders = [o for o in all_orders if o.status == OrderStatus.FILLED]
            
            if not filled_orders:
                return {"total_orders": 0, "message": "체결된 주문이 없습니다"}
            
            stats = {
                "total_orders": len(all_orders),
                "filled_orders": len(filled_orders),
                "active_orders": len([o for o in all_orders if o.status == OrderStatus.ACTIVE]),
                "trailing_stop_orders": len([o for o in filled_orders if o.order_type == OrderType.TRAILING_STOP]),
                "oco_orders": len([o for o in filled_orders if o.order_type == OrderType.OCO]),
                "success_rate": len(filled_orders) / len(all_orders) * 100 if all_orders else 0
            }
            
            # 트레일링 스탑 성과 분석
            trailing_orders = [o for o in filled_orders if o.order_type == OrderType.TRAILING_STOP]
            if trailing_orders:
                profits = []
                for order in trailing_orders:
                    if order.entry_price and order.current_price:
                        if order.side == "SELL":  # 롱 청산
                            profit_pct = ((order.current_price - order.entry_price) / order.entry_price) * 100
                        else:  # 숏 청산
                            profit_pct = ((order.entry_price - order.current_price) / order.entry_price) * 100
                        profits.append(profit_pct)
                
                if profits:
                    stats["trailing_avg_profit"] = sum(profits) / len(profits)
                    stats["trailing_best_profit"] = max(profits)
                    stats["trailing_worst_profit"] = min(profits)
            
            return stats
            
        except Exception as e:
            self.logger.error(f"성과 통계 계산 오류: {e}")
            return {"error": str(e)}
    
    def cleanup_old_orders(self, days: int = 7):
        """오래된 주문 정리"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            orders_to_remove = []
            
            for order_id, order in self.active_orders.items():
                if (order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.FAILED] and
                    order.created_at < cutoff_date):
                    orders_to_remove.append(order_id)
            
            for order_id in orders_to_remove:
                del self.active_orders[order_id]
            
            if orders_to_remove:
                self.logger.info(f"오래된 주문 {len(orders_to_remove)}개 정리 완료")
                
        except Exception as e:
            self.logger.error(f"주문 정리 오류: {e}")
    
    def shutdown(self):
        """관리자 종료"""
        try:
            self.monitoring_active = False
            
            # 모든 활성 주문 취소
            active_order_ids = [
                order_id for order_id, order in self.active_orders.items()
                if order.status == OrderStatus.ACTIVE
            ]
            
            for order_id in active_order_ids:
                self.cancel_order(order_id, "시스템 종료")
            
            self.logger.info("AdvancedOrderManager 종료 완료")
            
        except Exception as e:
            self.logger.error(f"관리자 종료 오류: {e}")
