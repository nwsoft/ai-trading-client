"""거래소·증권사 공통 주문 상태와 재시작 복구 판단."""

from __future__ import annotations

from typing import Any, Dict, Mapping


ALIASES = {
    "new": "accepted", "open": "accepted", "pending": "accepted",
    "partially_filled": "partially_filled", "partial": "partially_filled",
    "closed": "filled", "filled": "filled", "done": "filled",
    "canceled": "canceled", "cancelled": "canceled",
    "rejected": "rejected", "expired": "expired",
    "failed": "failed", "error": "failed",
}
TERMINAL_STATES = {"filled", "canceled", "rejected", "expired", "failed"}
TRANSITIONS = {
    "submitted": {"accepted", "partially_filled", *TERMINAL_STATES},
    "accepted": {"partially_filled", *TERMINAL_STATES},
    "partially_filled": {"partially_filled", *TERMINAL_STATES},
}


def normalize_order_state(value: Any, *, filled: Any = 0.0, amount: Any = 0.0) -> str:
    raw = str(value or "submitted").strip().lower().replace(" ", "_")
    state = ALIASES.get(raw, raw if raw in TRANSITIONS or raw in TERMINAL_STATES else "submitted")
    try:
        filled_value = float(filled or 0.0)
        amount_value = float(amount or 0.0)
    except (TypeError, ValueError):
        filled_value = amount_value = 0.0
    if state not in TERMINAL_STATES and filled_value > 0:
        state = "filled" if amount_value > 0 and filled_value >= amount_value else "partially_filled"
    return state


def reduce_order_state(previous: Any, receipt: Mapping[str, Any] | None) -> Dict[str, Any]:
    before = normalize_order_state(previous)
    payload = dict(receipt or {})
    after = normalize_order_state(
        payload.get("status"), filled=payload.get("filled"), amount=payload.get("amount")
    )
    allowed = before == after or before == "submitted" or after in TRANSITIONS.get(before, set())
    if before in TERMINAL_STATES and after != before:
        allowed = False
    return {
        "previous": before,
        "current": after if allowed else before,
        "terminal": (after if allowed else before) in TERMINAL_STATES,
        "transition_allowed": allowed,
        "recovery_required": (after if allowed else before) not in TERMINAL_STATES,
        "filled": float(payload.get("filled", 0.0) or 0.0),
        "amount": float(payload.get("amount", 0.0) or 0.0),
    }
