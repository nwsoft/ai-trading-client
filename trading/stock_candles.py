"""KRX intraday candle contract. No synthetic bars or daily substitutions."""
from datetime import datetime, timedelta, timezone
import math

KST = timezone(timedelta(hours=9))
STOCK_INTRADAY_MINUTES = {'1m': 1, '3m': 3, '5m': 5, '10m': 10, '15m': 15, '30m': 30, '1h': 60}


def intraday_minutes(timeframe):
    try:
        return STOCK_INTRADAY_MINUTES[timeframe]
    except KeyError:
        raise ValueError('stock_strategy_timeframe_unsupported:' + str(timeframe)) from None


def candle(timestamp, values, minutes=1):
    """Normalize a provider's KST bar start; reject corrupt prices/volume."""
    start = datetime.strptime(str(timestamp).strip(), '%Y%m%d%H%M%S').replace(tzinfo=KST)
    end = start.replace(hour=15, minute=30, second=0)
    if start.weekday() >= 5 or not start.replace(hour=9, minute=0, second=0) <= start < end:
        return None  # KRX regular session only (no NXT/pre/after-hours mixing).
    numbers = {k: abs(float(str(values[k]).replace(',', '').strip())) for k in ('open','high','low','close')}
    numbers['volume'] = float(str(values['volume']).replace(',', '').strip())
    if numbers['volume'] < 0 or not all(math.isfinite(v) for v in numbers.values()) or min(numbers[k] for k in ('open','high','low','close')) <= 0:
        raise ValueError('invalid_stock_intraday_numbers')
    if numbers['low'] > min(numbers['open'],numbers['close']) or numbers['high'] < max(numbers['open'],numbers['close']) or numbers['low'] > numbers['high']:
        raise ValueError('invalid_stock_intraday_ohlc')
    return {**numbers, 'timestamp':start.timestamp(),
            'close_timestamp':min(start + timedelta(minutes=minutes), end).timestamp()}


def completed(rows, *, now=None):
    now = datetime.now(KST).timestamp() if now is None else now
    unique = {}
    for row in rows:
        if row is not None and row['close_timestamp'] <= now:
            ts = row['timestamp']
            if ts in unique and unique[ts] != row:
                raise ValueError('conflicting_stock_intraday_row')
            unique[ts] = row
    return [unique[k] for k in sorted(unique)]


def aggregate_minutes(rows, timeframe, *, now=None):
    """Session-anchored buckets; missing minutes never become invented candles."""
    minutes = intraday_minutes(timeframe)
    groups = {}
    for row in completed(rows, now=now):
        dt = datetime.fromtimestamp(row['timestamp'], KST)
        session = dt.replace(hour=9, minute=0, second=0, microsecond=0)
        start = session + timedelta(minutes=((dt.hour*60+dt.minute-540)//minutes)*minutes)
        groups.setdefault(start, []).append(row)
    output = []
    for start, bars in sorted(groups.items()):
        end = min(start + timedelta(minutes=minutes), start.replace(hour=15,minute=30))
        expected = int((end-start).total_seconds()/60)
        bars = sorted(bars,key=lambda b:b['timestamp'])
        if len(bars) != expected or any(b['timestamp'] != start.timestamp()+i*60 for i,b in enumerate(bars)):
            continue
        output.append({'timestamp':start.timestamp(),'close_timestamp':end.timestamp(),
                       'open':bars[0]['open'],'close':bars[-1]['close'],
                       'high':max(b['high'] for b in bars),'low':min(b['low'] for b in bars),
                       'volume':sum(b['volume'] for b in bars)})
    return completed(output,now=now)
