#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""거래소별 OHLCV 응답 형식 차이를 한 곳에서 정규화한다."""

from __future__ import annotations

from typing import Any
import math


class CandleRows(list):
    """List-compatible query result retaining a sanitized failure cause."""
    def __init__(self, rows=(), *, reason="", error_type="", status_code=None):
        super().__init__(rows)
        self.reason = reason
        self.error_type = error_type
        self.status_code = status_code


def failed_candles(reason: str, error=None) -> CandleRows:
    status = getattr(error, 'status_code', None)
    if status is None:
        status = getattr(getattr(error, 'response', None), 'status_code', None)
    return CandleRows(reason=reason, error_type=type(error).__name__ if error else '',
                      status_code=status if isinstance(status, int) else None)


def optional_market_number(*values):
    """Missing/invalid is None; an explicitly reported zero stays zero."""
    for value in values:
        if value is None or value == '' or isinstance(value, bool):
            continue
        try:
            number = float(str(value).strip().replace(',', '').rstrip('%'))
            if math.isfinite(number):
                return number
        except (ValueError, TypeError):
            continue
    return None


def chronological_candles(rows):
    """Canonical ascending OHLCV; never synthesize gaps or pick conflicting bars."""
    by_time = {}
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise ValueError('invalid_candle_shape')
        values = [float(value) for value in row[:6]]
        if not all(math.isfinite(v) for v in values) or min(values[:5]) <= 0 or values[5] < 0:
            raise ValueError('invalid_candle_values')
        if values[0] in by_time and by_time[values[0]] != values:
            raise ValueError('conflicting_candle_timestamp')
        by_time[values[0]] = values
    return [by_time[key] for key in sorted(by_time)]


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
