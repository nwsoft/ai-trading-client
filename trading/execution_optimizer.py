#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""실행 품질 최적화 계층.

목표:
- 주문 라우팅/재시도/타임아웃/슬리피지 상한을 일관 정책으로 적용
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple


class ExecutionOptimizer:
    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    def choose_order_type(self, preferred: str, signal_strength: float, volatility: float, spread_bps: float) -> str:
        pref = str(preferred or "MARKET").upper()
        if pref == "LIMIT":
            return "LIMIT"
        if signal_strength >= 0.8 and volatility <= 0.015 and spread_bps <= 8.0:
            return "LIMIT"
        return "MARKET"

    def execute_with_quality_control(
        self,
        place_order_fn: Callable[[str, Optional[float]], Tuple[bool, Dict[str, Any], List[str]]],
        *,
        order_type: str,
        request_price: Optional[float],
        fallback_market: bool,
        max_retries: int,
        timeout_ms: int,
        max_slippage_bps: float,
    ) -> Tuple[bool, Dict[str, Any], List[str], float, float]:
        """품질 정책을 반영해 주문 실행한다.

        Returns:
            success, result, errors, latency_ms, slippage_bps
        """
        errors: List[str] = []
        retries = max(0, int(max_retries or 0))
        timeout_s = max(0.05, int(timeout_ms or 3000) / 1000.0)

        active_order_type = str(order_type or "MARKET").upper()
        active_price = request_price

        for attempt in range(retries + 1):
            started = time.perf_counter()
            success, result, call_errors = place_order_fn(active_order_type, active_price)
            latency_ms = (time.perf_counter() - started) * 1000.0
            errors.extend(call_errors or [])

            if latency_ms > timeout_s * 1000.0:
                errors.append(f"timeout:{latency_ms:.1f}ms")
                success = False

            filled_price = self._to_float(
                (result or {}).get("filled_price", (result or {}).get("price", active_price if active_price is not None else 0.0)),
                0.0,
            )
            slippage_bps = 0.0
            if active_price is not None and active_price > 0 and filled_price > 0:
                slippage_bps = ((filled_price - active_price) / active_price) * 10000.0
                if abs(slippage_bps) > max_slippage_bps:
                    errors.append(f"slippage_limit_exceeded:{slippage_bps:.2f}")
                    success = False

            if success:
                return True, (result if isinstance(result, dict) else {}), errors, latency_ms, slippage_bps

            if fallback_market and active_order_type == "LIMIT":
                active_order_type = "MARKET"
                active_price = None

            if attempt >= retries:
                return False, (result if isinstance(result, dict) else {}), errors, latency_ms, slippage_bps

        return False, {}, errors, 0.0, 0.0
