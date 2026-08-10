"""AI 커스텀 고급 주문 계획의 결정 상태머신.

주문 제출은 거래소 어댑터가 담당한다. 이 모듈은 같은 가격을 여러 번 받아도
동일 부분청산을 중복 요청하지 않고, 트레일링·손익분기·재진입 조건을 명시한다.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping


def initial_order_plan_state(original_quantity: float) -> Dict[str, Any]:
    quantity = max(0.0, float(original_quantity or 0.0))
    return {
        "schema_version": 1,
        "original_quantity": quantity,
        "remaining_quantity": quantity,
        "completed_partial_indices": [],
        "peak_pnl_percent": 0.0,
        "trailing_armed": False,
        "break_even_armed": False,
        "reentry_count": 0,
        "bars_since_exit": None,
    }


def evaluate_order_plan(
    plan: Mapping[str, Any] | None,
    state: Mapping[str, Any] | None,
    *,
    pnl_percent: float,
    current_quantity: float,
) -> Dict[str, Any]:
    """현재 PnL에서 다음 단일 동작을 계산한다. 반환 상태는 주문 성공 전 확정하지 않는다."""
    spec = dict(plan or {})
    runtime = deepcopy(dict(state or initial_order_plan_state(current_quantity)))
    current_qty = max(0.0, float(current_quantity or 0.0))
    original_qty = max(current_qty, float(runtime.get("original_quantity", current_qty) or current_qty))
    pnl = float(pnl_percent or 0.0)
    peak = max(float(runtime.get("peak_pnl_percent", pnl) or pnl), pnl)
    runtime["peak_pnl_percent"] = peak
    runtime["remaining_quantity"] = current_qty

    trailing = dict(spec.get("trailing_stop") or {})
    if trailing and bool(trailing.get("enabled", True)):
        activation = float(trailing.get("activation_percent", 0.0) or 0.0)
        distance = float(trailing.get("distance_percent", 0.0) or 0.0)
        runtime["trailing_armed"] = bool(runtime.get("trailing_armed")) or peak >= activation
        if runtime["trailing_armed"] and pnl <= peak - distance:
            return {
                "action": "close_all", "reason": "advanced_trailing_stop",
                "quantity": current_qty, "next_state": runtime,
            }

    break_even = dict(spec.get("break_even") or {})
    if break_even and bool(break_even.get("enabled", True)):
        trigger = float(break_even.get("trigger_percent", 0.0) or 0.0)
        offset = float(break_even.get("offset_percent", 0.0) or 0.0)
        runtime["break_even_armed"] = bool(runtime.get("break_even_armed")) or peak >= trigger
        if runtime["break_even_armed"] and pnl <= offset:
            return {
                "action": "close_all", "reason": "advanced_break_even",
                "quantity": current_qty, "next_state": runtime,
            }

    completed = {int(index) for index in runtime.get("completed_partial_indices", [])}
    for index, step in enumerate(list(spec.get("partial_take_profits") or [])):
        if index in completed:
            continue
        target = float(step.get("target_percent", 0.0) or 0.0)
        if pnl < target:
            continue
        requested = original_qty * float(step.get("close_fraction", 0.0) or 0.0)
        quantity = min(current_qty, max(0.0, requested))
        if quantity <= 0:
            continue
        if quantity >= current_qty - 1e-12:
            return {
                "action": "close_all",
                "reason": f"advanced_final_take_profit_{index + 1}",
                "quantity": current_qty,
                "partial_index": index,
                "next_state": runtime,
            }
        return {
            "action": "partial_close",
            "reason": f"advanced_partial_take_profit_{index + 1}",
            "quantity": quantity,
            "partial_index": index,
            "next_state": runtime,
        }
    return {"action": "hold", "reason": "advanced_order_plan_hold", "quantity": 0.0, "next_state": runtime}


def confirm_order_plan_action(
    decision: Mapping[str, Any], *, remaining_quantity: float,
) -> Dict[str, Any]:
    """체결 확인 뒤에만 부분청산 완료 표시를 확정한다."""
    runtime = deepcopy(dict(decision.get("next_state") or {}))
    runtime["remaining_quantity"] = max(0.0, float(remaining_quantity or 0.0))
    if decision.get("action") == "partial_close":
        completed = {int(index) for index in runtime.get("completed_partial_indices", [])}
        completed.add(int(decision.get("partial_index", -1)))
        runtime["completed_partial_indices"] = sorted(index for index in completed if index >= 0)
    runtime["last_confirmed_action"] = str(decision.get("action") or "hold")
    runtime["last_confirmed_reason"] = str(decision.get("reason") or "")
    return runtime


def evaluate_reentry(
    plan: Mapping[str, Any] | None,
    state: Mapping[str, Any] | None,
    *,
    bars_since_exit: int,
) -> Dict[str, Any]:
    """재진입 가능 여부만 반환하며 주문이나 활성 전략을 자동 변경하지 않는다."""
    reentry = dict((plan or {}).get("reentry") or {})
    runtime = deepcopy(dict(state or {}))
    if not reentry or not bool(reentry.get("enabled", True)):
        return {"allowed": False, "reason": "reentry_disabled", "next_state": runtime}
    cooldown = int(reentry.get("cooldown_bars", 0) or 0)
    maximum = int(reentry.get("max_reentries", 0) or 0)
    used = int(runtime.get("reentry_count", 0) or 0)
    allowed = int(bars_since_exit) >= cooldown and used < maximum
    return {
        "allowed": allowed,
        "reason": "reentry_eligible_user_signal_required" if allowed else "reentry_guard_blocked",
        "requires_new_entry_signal": True,
        "auto_ordered": False,
        "next_state": runtime,
    }
