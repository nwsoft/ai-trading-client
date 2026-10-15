"""Bounded, incremental KIS one-minute history shared by all strategy timeframes.

Official real endpoint returns <=120 rows; demo endpoint <=30, current day only.
Read-only RAM cache; restart warms again. Never invent missing/zero-volume bars.
"""
from datetime import datetime, timedelta
import time
from trading.stock_candles import KST, candle, completed


def read_intraday(adapter, symbol, required):
    required = max(1,min(int(required)+60,37000))
    now = datetime.now(KST)
    cache = adapter._intraday_cache
    if symbol not in cache:
        if len(cache) >= 8:
            cache.pop(next(iter(cache)))
        cache[symbol] = {'rows':{},'cursor':None,'fetched':-float('inf'),'exhausted':False,'day':now.date()}
    entry = cache[symbol]
    if adapter.sandbox and entry['day'] != now.date():
        entry.update(rows={},cursor=None,fetched=-float('inf'),exhausted=False,day=now.date())
    if time.monotonic()-entry['fetched'] < 10:
        return completed(entry['rows'].values())
    deadline = time.monotonic() + 10
    cursor = now.replace(second=0,microsecond=0)
    if not adapter.sandbox and (cursor.hour < 9 or cursor.weekday() >= 5):
        cursor = (cursor-timedelta(days=1)).replace(hour=15,minute=30)
        while cursor.weekday() >= 5:
            cursor -= timedelta(days=1)
    elif cursor.hour*60+cursor.minute > 930:
        cursor = cursor.replace(hour=15,minute=30)
    # Refresh newest bars, then continue warming from the oldest retained cursor.
    for page in range(4):
        if page:
            if len(entry['rows']) >= required or entry['exhausted'] or time.monotonic() >= deadline:
                break
            cursor = entry['cursor']
            if cursor is None:
                break
            time.sleep(0.6 if adapter.sandbox else 0.12)
        path = '/uapi/domestic-stock/v1/quotations/' + ('inquire-time-itemchartprice' if adapter.sandbox else 'inquire-time-dailychartprice')
        params = {'FID_COND_MRKT_DIV_CODE':'J','FID_INPUT_ISCD':symbol,
                  'FID_INPUT_HOUR_1':cursor.strftime('%H%M%S'),'FID_PW_DATA_INCU_YN':'Y'}
        if adapter.sandbox:
            params['FID_ETC_CLS_CODE']=''
        else:
            params.update(FID_INPUT_DATE_1=cursor.strftime('%Y%m%d'),FID_FAKE_TICK_INCU_YN='N')
        data = adapter._get(path,params=params)
        items = data.get('output2') if isinstance(data,dict) and adapter._kis_success(data) else None
        if not isinstance(items,list):
            raise ValueError('kis_intraday_page_unavailable')
        parsed = []
        for item in items:
            # Provider supplies each minute's volume, not cumulative daily volume.
            row = candle(str(item['stck_bsop_date'])+str(item['stck_cntg_hour']), {
                'open':item['stck_oprc'],'high':item['stck_hgpr'],'low':item['stck_lwpr'],
                'close':item['stck_prpr'],'volume':item['cntg_vol']})
            if row is not None:
                if row['timestamp'] > cursor.timestamp():
                    raise ValueError('kis_intraday_cursor_ignored')
                if adapter.sandbox and datetime.fromtimestamp(row['timestamp'],KST).date() != now.date():
                    raise ValueError('kis_demo_intraday_wrong_date')
                parsed.append(row)
        if not parsed:
            # No progress (including auction/after-hours data); retry newest on
            # the next cycle, do not loop at a non-advancing cursor.
            break
        earliest = datetime.fromtimestamp(min(r['timestamp'] for r in parsed),KST)
        next_cursor = earliest-timedelta(minutes=1)
        if next_cursor >= cursor:
            raise ValueError('kis_intraday_not_advancing')
        for row in completed(parsed,now=now.timestamp()):
            entry['rows'][row['timestamp']]=row
        if entry['cursor'] is None or next_cursor < entry['cursor']:
            entry['cursor'] = next_cursor
        if adapter.sandbox and next_cursor.hour < 9:
            entry['exhausted']=True
        if len(entry['rows']) > 37000:
            entry['rows'] = {ts:entry['rows'][ts] for ts in sorted(entry['rows'])[-37000:]}
    entry['fetched'] = time.monotonic()
    return completed(entry['rows'].values(),now=now.timestamp())
