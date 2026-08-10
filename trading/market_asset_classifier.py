#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""암호화폐 자동선정에서 비암호화 토큰화 파생상품을 제외하는 공용 정책."""

from __future__ import annotations

from typing import Any, Dict, Iterable


# 거래소 metadata가 불완전하거나 잘못 표기된 실제 사례를 위한 마지막 방어선.
KNOWN_TOKENIZED_NON_CRYPTO_BASES = frozenset({
    "AAOI", "AAPL", "AMZN", "BABA", "BILL", "CL", "COIN", "CRCL", "EPIC",
    "EWY", "GOOG", "GOOGL", "IBM", "INTC", "LAB", "META", "MSFT", "MSTR",
    "MU", "MUU", "NVDA", "SAMSUNG", "SKHYNIX", "SNDK", "SKHY", "SPCX",
    "TSLA", "TSEM",
})

_NON_CRYPTO_MARKET_TERMS = (
    "stock",
    "equity",
    "share",
    "commodity",
    "forex",
    "foreign exchange",
    "tokenized stock",
    "tokenised stock",
)


def _metadata_texts(market: Dict[str, Any]) -> Iterable[str]:
    """명시적인 상품 분류 필드만 읽어 코인 이름의 우연한 오탐을 피한다."""
    keys = (
        "type", "subType", "category", "assetType", "productType",
        "underlyingType", "instrumentType", "symbolType", "marketType",
    )
    for key in keys:
        value = market.get(key)
        if value not in (None, ""):
            yield str(value).strip().lower()
    info = market.get("info")
    if isinstance(info, dict):
        for key in keys:
            value = info.get(key)
            if value not in (None, ""):
                yield str(value).strip().lower()


def is_crypto_derivative_candidate(
    market: Dict[str, Any],
    *,
    configured_exclusions: Iterable[str] = (),
) -> bool:
    """CCXT market이 암호화폐 USDT 파생상품 후보인지 보수적으로 판정한다."""
    if not isinstance(market, dict) or not market.get("active", False):
        return False
    if not (market.get("swap") or market.get("future") or market.get("contract")):
        return False
    if str(market.get("quote") or "").upper() != "USDT":
        return False

    base = str(market.get("base") or "").upper().strip()
    excluded = {str(value or "").upper().strip() for value in configured_exclusions}
    if not base or base in KNOWN_TOKENIZED_NON_CRYPTO_BASES or base in excluded:
        return False

    for text in _metadata_texts(market):
        normalized = text.replace("_", " ").replace("-", " ")
        if normalized in {"index", "indices", "fx"}:
            return False
        if any(term in normalized for term in _NON_CRYPTO_MARKET_TERMS):
            return False
    return True
