#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""거래소별 OHLCV 응답 형식 차이를 한 곳에서 정규화한다."""

from __future__ import annotations

from typing import Any


_KLINE_INDEX = {
    "timestamp": 0,
    "open": 1,
    "high": 2,
    "low": 3,
    "close": 4,
    "volume": 5,
}


def kline_number(row: Any, field: str, default: float = 0.0) -> float:
    """Binance/CCXT 배열과 dict OHLCV를 동일하게 숫자로 읽는다."""
    value: Any = default
    key = str(field or "").strip().lower()
    try:
        if isinstance(row, dict):
            aliases = {
                "timestamp": ("timestamp", "time", "open_time", "openTime"),
                "open": ("open", "o"),
                "high": ("high", "h"),
                "low": ("low", "l"),
                "close": ("close", "c", "last"),
                "volume": ("volume", "v", "baseVolume"),
            }
            for candidate in aliases.get(key, (key,)):
                if row.get(candidate) is not None:
                    value = row.get(candidate)
                    break
        elif isinstance(row, (list, tuple)):
            index = _KLINE_INDEX.get(key)
            if index is not None and len(row) > index:
                value = row[index]
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return float(default)
