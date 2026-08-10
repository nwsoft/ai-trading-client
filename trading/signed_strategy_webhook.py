"""서명·시간·nonce·delivery ID를 검증하는 TradingView webhook 게이트."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Dict, Mapping, MutableMapping


def sign_webhook_payload(payload: Mapping[str, Any], secret: str) -> str:
    if not str(secret or ""):
        raise ValueError("webhook_secret_required")
    body = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


class SignedStrategyWebhookGate:
    """검증만 수행하며 주문을 만들거나 전략을 자동 승인하지 않는다."""

    def __init__(self, secret: str, *, max_clock_skew_seconds: int = 300):
        if len(str(secret or "")) < 16:
            raise ValueError("webhook_secret_must_be_at_least_16_chars")
        self.secret = str(secret)
        self.max_clock_skew_seconds = max(30, int(max_clock_skew_seconds))
        self._seen: MutableMapping[str, float] = {}

    def verify(self, payload: Mapping[str, Any], signature: str, *, now: float | None = None) -> Dict[str, Any]:
        current = float(now if now is not None else time.time())
        timestamp = float(payload.get("timestamp") or 0.0)
        nonce = str(payload.get("nonce") or "").strip()
        delivery_id = str(payload.get("delivery_id") or "").strip()
        errors = []
        if not nonce or not delivery_id:
            errors.append("nonce_and_delivery_id_required")
        if abs(current - timestamp) > self.max_clock_skew_seconds:
            errors.append("timestamp_outside_allowed_window")
        expected = sign_webhook_payload(payload, self.secret)
        if not hmac.compare_digest(expected, str(signature or "")):
            errors.append("signature_mismatch")
        replay_key = f"{delivery_id}:{nonce}"
        self._seen = {
            key: seen_at for key, seen_at in self._seen.items()
            if current - seen_at <= self.max_clock_skew_seconds
        }
        if replay_key in self._seen:
            errors.append("duplicate_delivery")
        if not errors:
            self._seen[replay_key] = current
        return {
            "valid": not errors,
            "errors": errors,
            "action": "strategy_signal_candidate" if not errors else "reject",
            "auto_approved": False,
            "auto_ordered": False,
        }

