"""New v49 closed-bar fields. Never reinterpret Analyzer display values.

The window excludes the current close for support/resistance. Volatility is
non-annualized population log-return deviation in percent, not 24h change.
DI uses the same rolling sums as the legacy ADX approximation (not Wilder RMA).
"""
import math

CONTRACT = 'closed-bar-fields.v1'
FIELDS = frozenset({'support_level', 'resistance_level', 'volatility',
                    'historical_volatility', 'di_plus', 'di_minus'})


def values(history):
    result = dict.fromkeys(FIELDS)
    window = history[-21:]
    if len(window) < 21:
        return result
    try:
        for row in window:
            for key in ('close', 'high', 'low'):
                value = row[key]
                if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) <= 0:
                    return result
            if not float(row['low']) <= float(row['close']) <= float(row['high']):
                return result
        closes = [float(row['close']) for row in window]
        result['support_level'] = min(closes[:-1])
        result['resistance_level'] = max(closes[:-1])
        returns = [math.log(b / a) for a, b in zip(closes, closes[1:])]
        mean = sum(returns) / len(returns)
        vol = math.sqrt(sum((value - mean)**2 for value in returns) / len(returns)) * 100
        result['volatility'] = result['historical_volatility'] = vol
        tr = plus = minus = 0.0
        for previous, current in zip(window[-15:-1], window[-14:]):
            high, low = float(current['high']), float(current['low'])
            up, down = high - float(previous['high']), float(previous['low']) - low
            tr += max(high-low, abs(high-float(previous['close'])), abs(low-float(previous['close'])))
            plus += up if up > down and up > 0 else 0.0
            minus += down if down > up and down > 0 else 0.0
        result['di_plus'] = 100*plus/tr if tr else 0.0
        result['di_minus'] = 100*minus/tr if tr else 0.0
    except (KeyError, TypeError, ValueError, OverflowError):
        return dict.fromkeys(FIELDS)
    return result


def read(context, field):
    if field in FIELDS and context.get('_condition_fields_contract') != CONTRACT:
        return None
    return context.get(field)


def requested(value):
    if isinstance(value, dict):
        return any((key in {'field', 'value_field'} and isinstance(item, str) and item in FIELDS)
                   or requested(item) for key, item in value.items())
    return isinstance(value, list) and any(requested(item) for item in value)
