#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CCXT 잔고 응답을 거래소에 관계없는 자산별 total 값으로 정규화한다."""

from typing import Any, Dict
import math


_META_KEYS = {
    "FREE",
    "USED",
    "TOTAL",
    "INFO",
    "TIMESTAMP",
    "DATETIME",
    "DEBT",
}


def normalize_ccxt_available_funds(raw_balance: Any, *, quote_asset: str) -> Dict[str, Any]:
    """Read a verified free amount without altering legacy total-balance display."""
    quote = str(quote_asset or '').strip().upper()
    unknown = {'status': 'error', 'quote_currency': quote, 'reason': 'available_balance_unverified'}
    if not isinstance(raw_balance, dict) or not quote:
        return unknown
    if str(raw_balance.get('status') or '').lower() in {'error', 'failed', 'unavailable'}:
        return unknown
    values = []
    currency = raw_balance.get(quote)
    free = raw_balance.get('free')
    for container, key in ((currency, 'free'), (free, quote)):
        if isinstance(container, dict) and key in container:
            raw = container[key]
            try:
                number = float(raw) if raw is not None and not isinstance(raw, bool) else float('nan')
            except (TypeError, ValueError):
                return unknown
            if not math.isfinite(number) or number < 0:
                return unknown
            values.append(number)
    if not values or any(v != values[0] for v in values):
        return unknown
    return {'status': 'ok', 'quote_currency': quote, 'available_balance': values[0],
            'basis': 'ccxt_provider_free_balance'}


def normalize_ccxt_total_balances(
    raw_balance: Any,
    *,
    quote_asset: str,
) -> Dict[str, float]:
    """기준통화와 실제 보유 중인 모든 자산을 반환한다.

    CCXT의 ``total`` 맵을 우선하고, 없으면 자산별 ``total`` 값을 읽는다.
    기준통화는 0이어도 표시하며 다른 자산의 0 잔고는 화면에서 제외한다.
    """
    quote = str(quote_asset or "").strip().upper()
    if not isinstance(raw_balance, dict):
        return {quote: 0.0} if quote else {}

    candidates: Dict[str, Any] = {}
    total_map = raw_balance.get("total")
    if isinstance(total_map, dict):
        candidates.update(total_map)

    for raw_key, raw_value in raw_balance.items():
        asset = str(raw_key or "").strip().upper()
        if not asset or asset in _META_KEYS:
            continue
        if isinstance(raw_value, dict):
            value = raw_value.get(
                "total",
                raw_value.get(
                    "wallet_balance",
                    raw_value.get("walletBalance", raw_value.get("balance")),
                ),
            )
        else:
            value = raw_value
        if value is not None and asset not in candidates:
            candidates[asset] = value

    normalized: Dict[str, float] = {}
    if quote:
        try:
            normalized[quote] = float(candidates.get(quote, 0) or 0)
        except (TypeError, ValueError):
            normalized[quote] = 0.0

    for asset, raw_value in candidates.items():
        key = str(asset or "").strip().upper()
        if not key or key == quote or key in _META_KEYS:
            continue
        try:
            numeric = float(raw_value or 0)
        except (TypeError, ValueError):
            continue
        if numeric > 0:
            normalized[key] = numeric
    return normalized
