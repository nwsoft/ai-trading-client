"""Recorded indicator projection. Never reconstruct measurements from prose/signals.

Used at the learning write boundary and when reading historical evidence. This
does not calculate signals, change selection weights, or make network requests.
"""
from collections.abc import Mapping
from math import isfinite


NUMERIC_FIELDS = (
    'rsi', 'macd', 'macd_signal', 'macd_histogram', 'bb_position',
    'ma20', 'ma50', 'ma200', 'sma20', 'sma50', 'sma200',
    'ema20', 'ema50', 'ema200', 'adx', 'atr', 'atr_percent', 'bb_width',
    'volume', 'volume_sma20', 'volume_ratio',
)


def indicator_snapshot(payload: Mapping) -> dict:
    """Prefer explicit scalar fields; support legacy nested indicator envelopes."""
    sources = [payload]
    for key in ('indicators', 'technical_indicators'):
        value = payload.get(key)
        if isinstance(value, Mapping):
            sources.append(value)

    def recorded(key, *aliases):
        for source in sources:
            for name in (key, *aliases):
                if source.get(name) is not None:
                    return source[name]
        return None

    result = {}
    for key in NUMERIC_FIELDS:
        raw = recorded(key, key.upper())
        try:
            value = None if raw is None or isinstance(raw, bool) else float(raw)
        except (TypeError, ValueError, OverflowError):
            value = None
        if value is not None and (not isfinite(value) or (key == 'rsi' and not 0 <= value <= 100)):
            value = None
        result[key] = value
    trend = recorded('trend', 'market_trend')
    trend = getattr(trend, 'value', trend)
    result['trend'] = trend if isinstance(trend, str) and trend.strip() and trend.lower() not in {'unknown', 'n/a', 'none'} else None
    missing = [key for key in ('rsi', 'macd', 'trend') if result[key] is None]
    result['indicator_status'] = 'not_recorded' if len(missing) == 3 else 'partial' if missing else 'available'
    result['missing_indicator_fields'] = missing
    return result
