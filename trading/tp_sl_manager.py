"""
TP/SL Manager 모듈
===================

역할:
- TP/SL 생성, 검증, 재설정, 워치독 로직을 단일 모듈에서 관리
- Trader / UnifiedTrader / AlphaArena 등은 이 모듈을 통해서만 TP/SL을 다루도록 유도

주의:
- 현재는 v3.8.9.5 이전 코드와의 호환을 위해 최소한의 뼈대만 정의한다.
- 기존 동작을 바꾸지 않기 위해, 실제 로직 이관은 단계적으로 진행한다.

참고 문서:
- docs/TP_SL_GUIDELINES.md
- docs/TRADING_FLOW.md (TP/SL 운영 규약)
- docs/TP_SL_FINAL_SOLUTION.md
- docs/TP_SL_ANALYSIS_REPORT.md
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from trading.trader import Trader

import time


class TpSlManager:
    """
    TP/SL 관리 전담 클래스 (Binance 중심, 이후 UnifiedTrader/CCXT로 확장 예정)

    설계 원칙:
    - TP/SL 관련 책임(생성/검증/재설정/워치독)을 한 곳에서 관리한다.
    - Binance API 호출은 가급적 Trader가 들고 있는 BinanceClient 래퍼를 통해 수행한다.
    - TP_SL_GUIDELINES.md의 규칙을 단일 기준으로 따른다.
    """

    def __init__(self, trader: "Trader") -> None:
        """
        Trader 인스턴스를 주입받는다.

        주입 이유:
        - trader.binance_client, trader.settings, trader.logger 등을 재사용하기 위함
        - 초기 단계에서는 기존 헬퍼(_tp_sl_order_params 등)와 공존해야 함
        """
        self.trader: "Trader" = trader
        self.binance_client = getattr(trader, "binance_client", None)
        self.settings = getattr(trader, "settings", {})
        self.logger = getattr(trader, "logger", None)

    # NOTE:
    # 아래 메서드들은 현재는 시그니처만 정의해두고,
    # 실제 로직은 향후 단계에서 trader.py에서 점진적으로 이관한다.

    # --- 생성 / 검증 -----------------------------------------------------

    def _protective_order_snapshot(self, symbol: str) -> Dict[str, Any]:
        """Read normal and Binance Algo protective orders as one contract."""
        normal = list(
            self.binance_client.client.futures_get_open_orders(symbol=symbol) or []
        )
        algo_getter = getattr(self.binance_client, "get_open_algo_orders", None)
        if not callable(algo_getter):
            raise RuntimeError('protection_algo_query_unavailable')
        algo = list(algo_getter(symbol=symbol, strict=True) or [])
        tp_orders = []
        sl_orders = []
        for order in normal + algo:
            order_type = str(order.get("orderType") or order.get("type") or "").upper()
            if order_type in ("TAKE_PROFIT", "TAKE_PROFIT_MARKET"):
                tp_orders.append(order)
            elif order_type in ("STOP", "STOP_MARKET"):
                sl_orders.append(order)
        protective_ids = {
            str(order.get("orderId") or order.get("algoId") or "")
            for order in tp_orders + sl_orders
        }
        other_orders = [
            order for order in normal
            if str(order.get("orderId") or "") not in protective_ids
        ]
        return {"tp": tp_orders, "sl": sl_orders, "other": other_orders}

    @staticmethod
    def _protective_order_is_open(order: Dict[str, Any]) -> bool:
        status = str(order.get("algoStatus") or order.get("status") or "PENDING").upper()
        working_type = str(order.get("workingType") or "MARK_PRICE").upper()
        return status in {"NEW", "PENDING", "WORKING"} and working_type == "MARK_PRICE"

    def create_tp_sl(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        tp_pct: float,
        sl_pct: float,
        price_prec: int,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        TP/SL 서버 주문을 생성한다.

        반환:
            (tp_order, sl_order)
        
        주의:
            - 2025-12-09 이후 Binance 정책 변경: 조건부 주문은 Algo Order API 사용 필수
            - 이 메서드를 구현할 때는 반드시 binance_client.place_tp_sl_orders() 또는
              place_futures_order()를 사용해야 함 (직접 futures_create_order 사용 금지)
            - place_futures_order()는 내부에서 조건부 주문을 자동으로 /fapi/v1/algoOrder로 라우팅함
        """
        # 1단계: 기존 동작을 깨지 않기 위해, 초기 버전은 trader.execute_single_trade 내부 로직을
        #       그대로 유지하고, 이 메서드는 차후 이관 시에만 사용한다.
        # 현재 단계에서는 아직 사용하지 않으므로 안전하게 빈 결과를 반환한다.
        # 
        # 🔥 향후 구현 시 주의사항:
        # - 반드시 self.binance_client.place_tp_sl_orders() 또는 place_futures_order() 사용
        # - 직접 futures_create_order() 호출 금지 (조건부 주문은 -4120 오류 발생)
        return None, None

    def validate_tp_sl(
        self, symbol: str, side: str, tp_price: float, sl_price: float, price_prec: int,
    ) -> bool:
        """Read-only validation. Never cancel unrelated orders to pass a check."""
        from trading.protection_snapshot import assess_protection
        try:
            snapshot = self._protective_order_snapshot(symbol)
            state = assess_protection(
                snapshot["tp"] + snapshot["sl"], symbol=symbol, position_side=side,
            )
            return state["status"] == "verified"
        except Exception as exc:
            if self.logger:
                self.logger.warning(f"[{symbol}] 보호주문 검증 실패 · 주문 보존 ({type(exc).__name__})")
            return False

    # --- 비파괴적인 상태 점검용 (비교/감시 전용) -----------------------------

    def audit_tp_sl_state(
        self,
        symbol: str,
    ) -> bool:
        """
        TP/SL 상태를 *변경 없이* 점검하는 경량 헬퍼.

        - 오픈오더를 한 번 조회하고, TP/SL/기타 주문 개수와 상태만 확인한다.
        - 재설정/취소 등은 절대 수행하지 않는다.
        - 비교/모니터링용이므로, 검증 실패 시에도 거래 동작에는 영향을 주지 않는다.
        """
        if not self.binance_client:
            return False

        try:
            snapshot = self._protective_order_snapshot(symbol)
            tp_orders = snapshot["tp"]
            sl_orders = snapshot["sl"]
            other_orders = snapshot["other"]

            tp_ok = len(tp_orders) == 1 and self._protective_order_is_open(tp_orders[0])
            sl_ok = len(sl_orders) == 1 and self._protective_order_is_open(sl_orders[0])

            if self.logger:
                self.logger.info(
                    f"[{symbol}] [TP_SL_AUDIT] "
                    f"tp_count={len(tp_orders)}, sl_count={len(sl_orders)}, "
                    f"other_count={len(other_orders)}, tp_ok={tp_ok}, sl_ok={sl_ok}"
                )

            return tp_ok and sl_ok and len(other_orders) == 0

        except Exception as e:
            if self.logger:
                self.logger.warning(f"[{symbol}] [TP_SL_AUDIT] 상태 점검 중 예외: {e}")
            return False

    # --- 재설정 / 워치독 --------------------------------------------------

    def reset_tp_sl(
        self,
        symbol: str,
        position: Any,
    ) -> bool:
        """
        비정상 상태(TP/SL 누락/중복 등) 시 TP/SL을 재설정한다.

        - 기존 `_retry_tp_sl_setup()` 로직을 점진적으로 이관하는 용도
        """
        return self.trader._tp_sl_watchdog(symbol, position, 0)

    def watchdog_check_and_repair(
        self,
        symbol: str,
        position: Any,
        check_idx: int,
    ) -> bool:
        """
        워치독 관점에서 TP/SL 상태를 점검하고, 필요 시 복구를 시도한다.

        - 기존 `_tp_sl_watchdog()` 로직을 점진적으로 이관하는 용도
        """
        return self.trader._tp_sl_watchdog(symbol, position, check_idx)
