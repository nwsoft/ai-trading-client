"""Read-only historical range provider contracts; no private APIs."""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import pytest
from web_platform.market_data import MultiSourcePublicMarketData, PublicMarketDataError, datetime_from_iso

VENUES = ['binance','bybit','okx','bitget','upbit','bithumb','coinone']
START = 1700000100000
STEP = 900000

class Pages:
    def __init__(self, venue):
        self.venue = venue
        self.calls = []
    def get(self, url, *, params, timeout):
        self.calls.append((url, params))
        cursor = params.get('endTime', params.get('end', params.get('timestamp')))
        if 'after' in params: cursor = params['after'] - 1
        if 'to' in params: cursor = int(datetime_from_iso(params['to']).timestamp()*1000) - 1
        if self.venue == 'bithumb':
            cursor = int(datetime.fromisoformat(params['to']).replace(tzinfo=timezone(timedelta(hours=9))).timestamp()*1000)-1
        if self.venue == 'bitget': cursor -= 1
        assert cursor is not None
        indices = [i for i in range(600) if START + i*STEP <= cursor][-200:]
        raw = [[START+i*STEP,100,102,99,101,20,START+(i+1)*STEP-1] for i in reversed(indices)]
        if self.venue in {'upbit','bithumb'}:
            payload = [{'candle_date_time_utc':datetime.fromtimestamp(r[0]/1000,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'), 'opening_price':r[1], 'high_price':r[2], 'low_price':r[3], 'trade_price':r[4], 'candle_acc_trade_volume':r[5]} for r in raw]
        elif self.venue == 'coinone':
            payload = {'result':'success','error_code':'0','chart':[dict(zip(['timestamp','open','high','low','close','target_volume'],r[:6])) for r in raw]}
        elif self.venue == 'bybit': payload = {'retCode':0,'result':{'list':raw}}
        elif self.venue == 'okx': payload = {'code':'0','data':raw}
        elif self.venue == 'bitget': payload = {'code':'00000','data':raw}
        else: payload = raw
        return SimpleNamespace(raise_for_status=lambda:None, json=lambda:payload)


@pytest.mark.parametrize('venue',VENUES)
def test_backward_pages_exact_range_no_latest_fallback(venue):
    session = Pages(venue)
    result = MultiSourcePublicMarketData(session=session).get_candles_range(venue, 'spot' if venue in {'upbit','bithumb','coinone'} else 'futures', 'BTCKRW' if venue in {'upbit','bithumb','coinone'} else 'BTCUSDT', '15m', START+10*STEP, START+510*STEP)
    assert len(session.calls) == 3
    assert len(result.candles) == 500
    assert result.candles[0].open_time == START+10*STEP
    assert result.candles[-1].close_time == START+510*STEP-1
    assert all(c.source == venue and c.closed and c.high == 102 and c.close == 101 for c in result.candles)
    assert [c.sequence for c in result.candles] == list(range(500))
    if venue in {'okx','bitget'}: assert all('history-candles' in url for url, _ in session.calls)


@pytest.mark.parametrize('start,end,interval', [(START,START,'15m'),(START+STEP,START,'15m'),(START,START+5001*STEP,'15m'),(START,START+STEP,'1M')])
def test_invalid_range_never_queries(start,end,interval):
    session = Pages('binance')
    with pytest.raises(ValueError):
        MultiSourcePublicMarketData(session=session).get_candles_range('binance','futures','BTCUSDT',interval,start,end)
    assert not session.calls


def test_empty_range_not_fabricated():
    session=Pages('binance')
    result=MultiSourcePublicMarketData(session=session).get_candles_range('binance','futures','BTCUSDT','15m',START-10*STEP,START)
    assert result.candles == []


def test_invalid_price_rejected():
    provider=MultiSourcePublicMarketData()
    provider._request_rows=lambda *a,**k:[[START,100,float('nan'),99,101,1,START+STEP-1]]
    with pytest.raises((PublicMarketDataError,ValueError)):
        provider.get_candles_range('binance','futures','BTCUSDT','15m',START,START+STEP)


def test_entry_range_does_not_trade_warmup():
    from trading.custom_strategy_validator import run_historical_replay
    from test_v39147_strategy_repair import compiled
    rules=compiled()
    rules['executable_entry']={'all':[{'field':'rsi','operator':'gte','value':0}]}
    rows=[[START+i*STEP,100,102,99,101,20,START+(i+1)*STEP-1] for i in range(250)]
    result=run_historical_replay(rules,rows,horizon=20,entry_start_ms=START+150*STEP)
    assert result['trades']
    assert all(datetime_from_iso(t['entry_time']).timestamp()*1000 >= START+150*STEP for t in result['trades'])
    assert all(datetime_from_iso(t['exit_time']).timestamp()*1000 < START+250*STEP for t in result['trades'])
