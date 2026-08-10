#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CCXT 체결 이력 조회와 기능 상태를 위한 공통 계약."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple


UNSUPPORTED_TOKENS = (
    "not supported",
    "unsupported",
    "fetchmytrades",
    "fetch_my_trades",
)

FINAL_EXECUTION_STATUSES = {"closed", "filled"}
FAILED_EXECUTION_STATUSES = {
    "canceled", "cancelled", "rejected", "expired", "failed", "error",
}


def _has_capability(exchange: Any, name: str, default: bool = False) -> bool:
    try:
        value = (getattr(exchange, "has", {}) or {}).get(name, default)
        return bool(value)
    except Exception:
        return bool(default)


def build_execution_capabilities(
    exchange: Any,
    *,
    live_order_receipt: bool = True,
    manual_trade_backfill: bool = True,
) -> Dict[str, Any]:
    historical_trades = _has_capability(exchange, "fetchMyTrades")
    closed_orders_fallback = (
        _has_capability(exchange, "fetchClosedOrders")
        or _has_capability(exchange, "fetchOrders")
        or callable(getattr(exchange, "fetch_closed_orders", None))
        or callable(getattr(exchange, "fetch_orders", None))
    )
    available = historical_trades or closed_orders_fallback
    return {
        "live_order_receipt": bool(live_order_receipt),
        "historical_trades": bool(historical_trades),
        "closed_orders_fallback": bool(closed_orders_fallback),
        "manual_trade_backfill": bool(manual_trade_backfill and available),
        "history_available": bool(available),
        "history_reason": "available" if available else "exchange_history_api_unsupported",
    }


def normalize_execution(
    raw: Dict[str, Any],
    *,
    symbol_hint: Optional[str] = None,
    symbol_formatter: Optional[Callable[[Optional[str]], str]] = None,
) -> Dict[str, Any]:
    item = dict(raw or {})
    amount = float(item.get("amount") or item.get("filled") or item.get("quantity") or 0.0)
    filled = float(item.get("filled") or amount)
    price = float(item.get("average") or item.get("price") or 0.0)
    cost = float(item.get("cost") or (price * filled if price and filled else 0.0))
    symbol_raw = item.get("symbol") or symbol_hint
    symbol = symbol_formatter(symbol_raw) if callable(symbol_formatter) else str(symbol_raw or "")
    return {
        **item,
        "id": item.get("id") or item.get("trade_id"),
        "order": item.get("order") or item.get("order_id") or item.get("id"),
        "symbol": symbol,
        "side": str(item.get("side") or "").lower(),
        "price": price,
        "average": item.get("average") or price,
        "amount": amount,
        "filled": filled,
        "remaining": item.get("remaining"),
        "cost": cost,
        "timestamp": item.get("timestamp") or item.get("time"),
        "datetime": item.get("datetime"),
        "fee": item.get("fee"),
        "status": item.get("status"),
    }


def execution_is_confirmed(order: Dict[str, Any]) -> bool:
    """주문 접수가 아니라 실제 체결 수량이 확인된 응답만 체결로 판정한다."""
    try:
        status = str(order.get("status") or "").strip().lower()
        if status in FAILED_EXECUTION_STATUSES:
            return False
        filled = float(order.get("filled") or order.get("executed_qty") or 0.0)
        if filled <= 0:
            return False
        # 일부 거래소는 시장가 체결 뒤 status를 비워 반환한다. filled가 양수면
        # 확정 체결로 보되, NEW/PENDING/OPEN은 아직 미확정으로 유지한다.
        return status not in {"new", "pending", "open"}
    except Exception:
        return False


def confirm_ccxt_order_execution(
    exchange: Any,
    order: Dict[str, Any],
    *,
    symbol: Optional[str],
    symbol_formatter: Optional[Callable[[Optional[str]], str]] = None,
) -> Dict[str, Any]:
    """CCXT 주문 ID로 개별 주문을 재조회해 확정 체결 계약으로 정규화한다.

    Bithumb처럼 계정 전체 ``fetchMyTrades``/``fetchOrders``는 지원하지 않아도
    ``fetchOrder``를 지원하는 거래소가 있다. 새 NoahAI 주문은 주문 ID를 알고
    있으므로 이 경로로 실제 filled/average/cost/fee를 복구할 수 있다.
    """
    receipt = normalize_execution(
        dict(order or {}),
        symbol_hint=symbol,
        symbol_formatter=symbol_formatter,
    )
    order_id = str(
        receipt.get("order") or receipt.get("id")
        or order.get("order_id") or order.get("orderId") or ""
    ).strip()
    receipt["order"] = order_id or receipt.get("order")
    receipt["_execution_confirmation_source"] = "create_order"

    if not execution_is_confirmed(receipt) and order_id and exchange is not None:
        fetch_order = getattr(exchange, "fetch_order", None)
        if callable(fetch_order):
            fetched: Optional[Dict[str, Any]] = None
            try:
                fetched_raw = fetch_order(order_id, symbol)
                fetched = dict(fetched_raw) if isinstance(fetched_raw, dict) else None
            except TypeError:
                try:
                    fetched_raw = fetch_order(order_id)
                    fetched = dict(fetched_raw) if isinstance(fetched_raw, dict) else None
                except Exception as exc:
                    receipt["_execution_confirmation_error"] = str(exc)
            except Exception as exc:
                receipt["_execution_confirmation_error"] = str(exc)

            if fetched:
                # 주문 상세 응답을 우선하되 거래소가 생략한 필드는 접수 응답으로 보존한다.
                merged = dict(receipt)
                for key, value in fetched.items():
                    if value not in (None, "", [], {}):
                        merged[key] = value
                receipt = normalize_execution(
                    merged,
                    symbol_hint=symbol,
                    symbol_formatter=symbol_formatter,
                )
                receipt["order"] = receipt.get("order") or order_id
                receipt["_execution_confirmation_source"] = "fetch_order"

    confirmed = execution_is_confirmed(receipt)
    receipt["_execution_confirmed"] = confirmed
    if confirmed and not (
        receipt.get("timestamp") or receipt.get("datetime") or receipt.get("time")
    ):
        # 거래소가 체결시각을 생략하면 확인 시각을 명시적으로 보조값으로 남긴다.
        receipt["datetime"] = datetime.now(timezone.utc).isoformat()
        receipt["_execution_time_source"] = "local_confirmation_time"
    return receipt


def fetch_ccxt_execution_history(
    exchange: Any,
    *,
    symbol: Optional[str],
    limit: int,
    since_ms: Optional[int] = None,
    symbol_formatter: Optional[Callable[[Optional[str]], str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """체결 API 우선, 주문 API 폴백 순으로 조회하고 기능 상태도 함께 반환한다."""
    capabilities = build_execution_capabilities(exchange)
    if exchange is None:
        capabilities.update(history_available=False, history_reason="exchange_not_connected")
        return [], capabilities

    fetch_my_trades = getattr(exchange, "fetch_my_trades", None)
    if capabilities["historical_trades"] and callable(fetch_my_trades):
        try:
            if since_ms is not None:
                try:
                    trades = fetch_my_trades(symbol, since=since_ms, limit=limit)
                except TypeError:
                    try:
                        trades = fetch_my_trades(symbol, since_ms, limit)
                    except TypeError:
                        trades = fetch_my_trades(symbol, limit=limit)
            else:
                trades = fetch_my_trades(symbol, limit=limit)
            rows = [
                normalize_execution(
                    dict(item),
                    symbol_hint=symbol,
                    symbol_formatter=symbol_formatter,
                )
                for item in (trades or [])
                if isinstance(item, dict)
            ]
            capabilities["history_source"] = "fetch_my_trades"
            return rows[:limit], capabilities
        except Exception as exc:
            if not any(token in str(exc).lower() for token in UNSUPPORTED_TOKENS):
                capabilities.update(history_available=False, history_reason="history_query_failed")
                capabilities["history_error"] = str(exc)
                return [], capabilities
            capabilities["historical_trades"] = False

    for method_name in ("fetch_closed_orders", "fetch_orders"):
        fetcher = getattr(exchange, method_name, None)
        if not callable(fetcher):
            continue
        try:
            try:
                if since_ms is not None:
                    try:
                        orders = fetcher(symbol, since=since_ms, limit=limit)
                    except TypeError:
                        orders = fetcher(symbol, since_ms, limit)
                else:
                    orders = fetcher(symbol, limit=limit)
            except TypeError:
                orders = fetcher(symbol)
        except Exception:
            continue

        rows: List[Dict[str, Any]] = []
        for order in orders or []:
            if not isinstance(order, dict):
                continue
            status = str(order.get("status") or "").lower()
            filled = float(order.get("filled") or 0.0)
            if status not in {"closed", "filled"} and filled <= 0:
                continue
            rows.append(
                normalize_execution(
                    order,
                    symbol_hint=symbol,
                    symbol_formatter=symbol_formatter,
                )
            )
        capabilities.update(
            closed_orders_fallback=True,
            history_available=True,
            history_reason="available",
            history_source=method_name,
        )
        return rows[:limit], capabilities

    capabilities.update(
        history_available=False,
        history_reason="exchange_history_api_unsupported",
        history_source="none",
    )
    return [], capabilities
