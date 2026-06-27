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
        self,
        symbol: str,
        side: str,
        tp_price: float,
        sl_price: float,
        price_prec: int,
    ) -> bool:
        """
        현재 오픈오더 상태를 기반으로 TP/SL이 정상적으로 설정되었는지 검증하고,
        필요 시 비정상 주문 정리 + TP/SL 재설정을 시도한다.

        - 기존 trader.execute_single_trade 내 TP/SL 검증/재설정/기타 주문 정리 로직을 그대로 이관.
        - Trader._retry_tp_sl_setup()을 호출해 재설정을 수행한다.
        """
        if not self.binance_client:
            return False

        verification_passed = False
        tp_sl_verified = False

        try:
            # 재시도 로직: 최대 3회, 각 시도마다 대기 시간 증가
            for verify_attempt in range(3):
                wait_time = 2.0 + (verify_attempt * 1.0)  # 2초, 3초, 4초
                time.sleep(wait_time)

                open_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)

                # 주문 타입 필터링 통일: watchdog와 동일하게 처리
                tp_orders = [
                    o for o in open_orders
                    if o.get("type") in ("TAKE_PROFIT", "TAKE_PROFIT_MARKET")
                ]
                sl_orders = [
                    o for o in open_orders
                    if o.get("type") in ("STOP", "STOP_MARKET")
                ]
                other_orders = [
                    o for o in open_orders
                    if o.get("type") not in ("TAKE_PROFIT", "TAKE_PROFIT_MARKET", "STOP", "STOP_MARKET")
                ]

                # 엄격한 검증: 정확히 1:1 + 모든 옵션 확인
                if len(tp_orders) == 1 and len(sl_orders) == 1:
                    tp_order = tp_orders[0]
                    sl_order = sl_orders[0]

                    tp_valid = (
                        tp_order.get("workingType") == "MARK_PRICE"
                        and tp_order.get("status") == "NEW"
                    )
                    sl_valid = (
                        sl_order.get("workingType") == "MARK_PRICE"
                        and sl_order.get("status") == "NEW"
                    )

                    if tp_valid and sl_valid:
                        if self.logger:
                            self.logger.info(
                                f"[{symbol}] ✅ TP/SL 완벽 설정 완료 - 검증 통과 "
                                f"(TP:{tp_price:.5f}, SL:{sl_price:.5f}) [시도 {verify_attempt+1}/3]"
                            )
                        tp_sl_verified = True
                        verification_passed = True
                        break
                    else:
                        if self.logger:
                            self.logger.warning(
                                f"[{symbol}] ⚠️ TP/SL 옵션 검증 실패 (시도 {verify_attempt+1}/3): "
                                f"TP_valid={tp_valid}, SL_valid={sl_valid}"
                            )
                else:
                    if self.logger:
                        self.logger.warning(
                            f"[{symbol}] ⚠️ TP/SL 수량 검증 실패 (시도 {verify_attempt+1}/3): "
                            f"TP {len(tp_orders)}개, SL {len(sl_orders)}개 (정확히 1:1 필요)"
                        )

            # 모든 재시도 실패 시 재설정 시도
            if not verification_passed and hasattr(self.trader, "_retry_tp_sl_setup"):
                if self.logger:
                    self.logger.warning(
                        f"[{symbol}] ⚠️ TP/SL 검증 실패 (3회 시도 후) - 재설정 시도"
                    )
                retry_success = self.trader._retry_tp_sl_setup(
                    symbol, side, tp_price, sl_price, price_prec
                )
                if retry_success:
                    # 재설정 후 재검증 (1회)
                    time.sleep(2.0)
                    open_orders_retry = self.binance_client.client.futures_get_open_orders(
                        symbol=symbol
                    )
                    tp_orders_retry = [
                        o for o in open_orders_retry
                        if o.get("type") in ("TAKE_PROFIT", "TAKE_PROFIT_MARKET")
                    ]
                    sl_orders_retry = [
                        o for o in open_orders_retry
                        if o.get("type") in ("STOP", "STOP_MARKET")
                    ]
                    if len(tp_orders_retry) == 1 and len(sl_orders_retry) == 1:
                        tp_sl_verified = True
                        verification_passed = True
                        if self.logger:
                            self.logger.info(f"[{symbol}] ✅ TP/SL 재설정 후 검증 통과")
                    else:
                        if self.logger:
                            self.logger.warning(
                                f"[{symbol}] ⚠️ TP/SL 재설정 후 검증 실패: "
                                f"TP {len(tp_orders_retry)}개, SL {len(sl_orders_retry)}개"
                            )

            # 기타 주문이 있으면 정리 시도 (원래 trader 코드 그대로)
            if not verification_passed:
                open_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)
                tp_orders = [
                    o for o in open_orders
                    if o.get("type") in ("TAKE_PROFIT", "TAKE_PROFIT_MARKET")
                ]
                sl_orders = [
                    o for o in open_orders
                    if o.get("type") in ("STOP", "STOP_MARKET")
                ]
                other_orders = [
                    o for o in open_orders
                    if o.get("type") not in ("TAKE_PROFIT", "TAKE_PROFIT_MARKET", "STOP", "STOP_MARKET")
                ]

                if len(other_orders) > 0:
                    if self.logger:
                        self.logger.warning(
                            f"[{symbol}] ⚠️ 기타 주문 발견:\n"
                            f"- TP 주문: {len(tp_orders)}개 {[o.get('stopPrice', 'N/A') for o in tp_orders]}\n"
                            f"- SL 주문: {len(sl_orders)}개 {[o.get('stopPrice', 'N/A') for o in sl_orders]}\n"
                            f"- 기타 주문: {len(other_orders)}개"
                        )
                    try:
                        if len(other_orders) > 0:
                            if self.logger:
                                self.logger.info(
                                    f"[{symbol}] 🔄 비정상 주문 정리 후 TP/SL 재설정 시도"
                                )
                            # 기타 주문만 선별 취소
                            try:
                                open_orders2 = self.binance_client.client.futures_get_open_orders(
                                    symbol=symbol
                                )
                                others2 = [
                                    o for o in open_orders2
                                    if o.get("type") not in (
                                        "TAKE_PROFIT",
                                        "TAKE_PROFIT_MARKET",
                                        "STOP",
                                        "STOP_MARKET",
                                    )
                                ]
                                if others2:
                                    if hasattr(self.binance_client, "cancel_orders"):
                                        self.binance_client.cancel_orders(
                                            symbol, [o["orderId"] for o in others2]
                                        )
                                    else:
                                        for o in others2:
                                            self.binance_client.client.futures_cancel_order(
                                                symbol=symbol,
                                                orderId=o["orderId"],
                                            )
                                    if self.logger:
                                        self.logger.info(
                                            f"[{symbol}] 기타 주문 {len(others2)}개 정리 완료"
                                        )
                            except Exception as cleanup_e:
                                if self.logger:
                                    self.logger.warning(
                                        f"[{symbol}] 기타 주문 정리 중 오류: {cleanup_e}"
                                    )

                            # 정리 후 TP/SL 재설정 재시도
                            if hasattr(self.trader, "_retry_tp_sl_setup"):
                                retry_success2 = self.trader._retry_tp_sl_setup(
                                    symbol, side, tp_price, sl_price, price_prec
                                )
                                if retry_success2:
                                    if self.logger:
                                        self.logger.info(
                                            f"[{symbol}] ✅ 비정상 주문 정리 후 TP/SL 재설정 성공"
                                        )
                                    verification_passed = True
                                else:
                                    if self.logger:
                                        self.logger.warning(
                                            f"[{symbol}] ⚠️ 비정상 주문 정리 후 TP/SL 재설정 실패"
                                        )
                    except Exception as e_cleanup:
                        if self.logger:
                            self.logger.warning(
                                f"[{symbol}] ⚠️ 비정상 주문 정리 중 예외 발생: {e_cleanup}"
                            )

            return verification_passed or tp_sl_verified

        except Exception as e:
            if self.logger:
                self.logger.error(f"[{symbol}] TP/SL 검증 중 예외 발생: {e}")
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
            open_orders = self.binance_client.client.futures_get_open_orders(symbol=symbol)
            tp_orders = [
                o for o in open_orders
                if o.get("type") in ("TAKE_PROFIT", "TAKE_PROFIT_MARKET")
            ]
            sl_orders = [
                o for o in open_orders
                if o.get("type") in ("STOP", "STOP_MARKET")
            ]
            other_orders = [
                o for o in open_orders
                if o.get("type") not in ("TAKE_PROFIT", "TAKE_PROFIT_MARKET", "STOP", "STOP_MARKET")
            ]

            tp_ok = len(tp_orders) == 1 and tp_orders[0].get("status") == "NEW"
            sl_ok = len(sl_orders) == 1 and sl_orders[0].get("status") == "NEW"

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
        return True

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
        return True


