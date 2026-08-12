#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""암호화폐 주문 명령의 멱등 키와 실패 처리 정책."""

from __future__ import annotations

import hashlib
from typing import Any, Dict


def exchange_client_order_id(command_id: str, max_length: int = 32) -> str:
    """거래소 공통 허용문자/길이에 맞춘 추적 가능한 클라이언트 주문 ID."""
    digest = hashlib.sha256(str(command_id or "").encode("utf-8")).hexdigest()[:24]
    return f"noah-{digest}"[:max(8, int(max_length))]


def client_order_params(exchange: str, command_id: str) -> Dict[str, Any]:
    value = exchange_client_order_id(command_id)
    normalized = str(exchange or "").strip().lower()
    if normalized == "binance":
        return {"newClientOrderId": value}
    if normalized == "bybit":
        return {"orderLinkId": value}
    if normalized == "okx":
        return {"clOrdId": value}
    if normalized == "bitget":
        return {"clientOid": value}
    if normalized == "upbit":
        return {"identifier": value}
    # 현재 Bithumb CCXT 어댑터는 client_order_id가 추가된 /v2/orders가
    # 아니라 구형 주문 endpoint를 사용한다. 미지원 파라미터를 보내지 않는다.
    if normalized == "bithumb":
        return {}
    return {"clientOrderId": value}


def classify_order_error(error: Any) -> Dict[str, Any]:
    """문자열 오류를 재시도/조회/진입중단 정책으로 변환한다.

    알 수 없는 주문 결과는 성공/실패 어느 쪽으로도 단정하지 않고 조회가
    끝날 때까지 ambiguous로 둔다.
    """
    message = str(error or "unknown order error")
    lower = message.lower()
    if any(token in lower for token in ("api key", "signature", "unauthorized", "forbidden", "permission", "invalid key", "ip whitelist")):
        return {"category": "auth_permission", "retry": False, "reconcile": False, "halt_entries": True, "delay": 0}
    if any(token in lower for token in ("insufficient", "not enough", "잔고", "balance")):
        return {"category": "insufficient_funds", "retry": False, "reconcile": True, "halt_entries": True, "delay": 0}
    if any(token in lower for token in ("minimum", "min notional", "precision", "step size", "lot size", "too small", "dust", "최소 주문")):
        return {"category": "order_constraint", "retry": False, "reconcile": False, "halt_entries": True, "delay": 0}
    if any(token in lower for token in ("position", "reduceonly", "reduce only", "size is zero", "no position")):
        return {"category": "position_mismatch", "retry": False, "reconcile": True, "halt_entries": True, "delay": 0}
    if any(token in lower for token in ("429", "rate limit", "too many request")):
        return {"category": "rate_limit", "retry": True, "reconcile": False, "halt_entries": True, "delay": 30}
    if any(token in lower for token in ("timeout", "timed out", "network", "connection", "request_failed", "temporarily unavailable")):
        return {"category": "ambiguous_transport", "retry": True, "reconcile": True, "halt_entries": True, "delay": 10}
    if any(token in lower for token in ("500", "502", "503", "504", "server error", "exchange unavailable")):
        return {"category": "transient_exchange", "retry": True, "reconcile": True, "halt_entries": True, "delay": 15}
    return {"category": "unknown", "retry": False, "reconcile": True, "halt_entries": True, "delay": 0}
