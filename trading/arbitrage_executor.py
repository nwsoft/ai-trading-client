#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""차익거래 실행 오케스트레이터(안전 가드 포함)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from .arbitrage_monitor import ArbitrageOpportunity


@dataclass
class ArbitrageExecutionResult:
    status: str
    message: str
    buy_order: Optional[Dict[str, Any]]
    sell_order: Optional[Dict[str, Any]]
    estimated_profit: float
    executed_at: datetime


class ArbitrageExecutor:
    """기회 검증 후 양방향 주문을 순차 실행한다.

    주의: 실제 환경에서는 거래소별 체결 확인/롤백/재시도 정책을 추가해야 한다.
    """

    def __init__(
        self,
        exchange_clients: Dict[str, Any],
        max_notional: float = 0.0,
        allow_pending_hedge: bool = False,
    ):
        self.exchange_clients = exchange_clients
        self.max_notional = float(max_notional)
        self.allow_pending_hedge = bool(allow_pending_hedge)

    @staticmethod
    def _normalize_order_status(order: Optional[Dict[str, Any]]) -> str:
        if not isinstance(order, dict):
            return ''
        status = str(order.get('order_status') or order.get('status') or '').strip()
        return status.upper()

    def _get_client(self, exchange: str) -> Any:
        return self.exchange_clients.get(exchange)

    def execute(self, opportunity: ArbitrageOpportunity, quantity: float) -> ArbitrageExecutionResult:
        qty = float(quantity)
        if qty <= 0:
            return ArbitrageExecutionResult(
                status="error",
                message="수량은 0보다 커야 합니다.",
                buy_order=None,
                sell_order=None,
                estimated_profit=0.0,
                executed_at=datetime.now(),
            )

        notional = qty * opportunity.buy_price
        if self.max_notional > 0 and notional > self.max_notional:
            return ArbitrageExecutionResult(
                status="blocked",
                message=f"최대 거래금액 초과: {notional:.2f} > {self.max_notional:.2f}",
                buy_order=None,
                sell_order=None,
                estimated_profit=0.0,
                executed_at=datetime.now(),
            )

        buy_client = self._get_client(opportunity.buy_exchange)
        sell_client = self._get_client(opportunity.sell_exchange)
        if not buy_client or not sell_client:
            return ArbitrageExecutionResult(
                status="error",
                message="거래소 클라이언트가 누락되었습니다.",
                buy_order=None,
                sell_order=None,
                estimated_profit=0.0,
                executed_at=datetime.now(),
            )

        try:
            # 1) 매수 주문
            buy_order = buy_client.place_order(
                symbol=opportunity.symbol,
                side="BUY",
                quantity=qty,
                order_type="MARKET",
            )
            buy_status = self._normalize_order_status(buy_order)
            if buy_status not in ("SUCCESS", "FILLED", "ACCEPTED", "PENDING", "NEW"):
                return ArbitrageExecutionResult(
                    status="buy_failed",
                    message=f"매수 주문 실패: {buy_order.get('error', 'unknown')}",
                    buy_order=buy_order,
                    sell_order=None,
                    estimated_profit=0.0,
                    executed_at=datetime.now(),
                )

            # 보수적 기본값: 매수 체결/접수 확실 상태가 아닐 때 매도 금지
            if not self.allow_pending_hedge and buy_status in ("PENDING", "NEW"):
                return ArbitrageExecutionResult(
                    status="buy_pending",
                    message="매수 주문이 아직 확정되지 않아 매도 주문을 보류했습니다.",
                    buy_order=buy_order,
                    sell_order=None,
                    estimated_profit=0.0,
                    executed_at=datetime.now(),
                )

            # 2) 매도 주문
            sell_order = sell_client.place_order(
                symbol=opportunity.symbol,
                side="SELL",
                quantity=qty,
                order_type="MARKET",
            )
            sell_status = self._normalize_order_status(sell_order)
            if sell_status not in ("SUCCESS", "FILLED", "ACCEPTED", "PENDING", "NEW"):
                return ArbitrageExecutionResult(
                    status="sell_failed",
                    message=f"매도 주문 실패: {sell_order.get('error', 'unknown')}",
                    buy_order=buy_order,
                    sell_order=sell_order,
                    estimated_profit=0.0,
                    executed_at=datetime.now(),
                )

            est_profit = opportunity.estimated_profit * qty
            return ArbitrageExecutionResult(
                status="success",
                message="차익거래 주문 접수 완료",
                buy_order=buy_order,
                sell_order=sell_order,
                estimated_profit=est_profit,
                executed_at=datetime.now(),
            )

        except Exception as exc:
            return ArbitrageExecutionResult(
                status="error",
                message=f"차익거래 실행 오류: {exc}",
                buy_order=None,
                sell_order=None,
                estimated_profit=0.0,
                executed_at=datetime.now(),
            )
