#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CCXT 체결 이력 조회와 기능 상태를 위한 공통 계약."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple


UNSUPPORTED_TOKENS = (
    "not supported",
    "unsupported",
    "fetchmytrades",
    "fetch_my_trades",
)


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


def fetch_ccxt_execution_history(
    exchange: Any,
    *,
    symbol: Optional[str],
    limit: int,
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
