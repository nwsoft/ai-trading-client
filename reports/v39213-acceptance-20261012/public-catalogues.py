"""Read-only network smoke. No keys, accounts, settings, orders or customer data."""
import sys,json,concurrent.futures,datetime
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
import ccxt,requests
from trading.exchanges.adapters.okx_futures_adapter import OkxFuturesAdapter
from trading.exchanges.adapters.bybit_futures_adapter import BybitFuturesAdapter
from trading.exchanges.adapters.bitget_futures_adapter import BitgetFuturesAdapter


def catalogue(venue, adapter):
    exchange=getattr(ccxt,venue)({'timeout':8000,'enableRateLimit':True})
    owner=adapter.__new__(adapter);owner.exchange=exchange
    try:
        markets=owner.load_instrument_catalogue()
        assert markets and all(m.get('symbol') for m in markets.values())
        return {'venue':venue,'status':'PASS','count':len(markets),'path':'actual_adapter.load_instrument_catalogue + CCXT '+ccxt.__version__,'private_calls':False}
    except Exception as exc:
        return {'venue':venue,'status':'UNAVAILABLE','error_type':type(exc).__name__,'path':'actual_adapter.load_instrument_catalogue','private_calls':False}


def endpoint(venue,url,key=None):
    try:
        r=requests.get(url,timeout=10);r.raise_for_status();data=r.json()
        rows=data[key] if key else data
        if isinstance(rows,dict):rows=[v for k,v in rows.items() if k!='date']
        assert isinstance(rows,list) and rows
        return {'venue':venue,'status':'PASS','count':len(rows),'path':'public GET only; not installed adapter acceptance'}
    except Exception as exc:
        return {'venue':venue,'status':'UNAVAILABLE','error_type':type(exc).__name__,'http_status':getattr(getattr(exc,'response',None),'status_code',None)}

with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
    futures=[pool.submit(catalogue,venue,adapter) for venue,adapter in [('okx',OkxFuturesAdapter),('bybit',BybitFuturesAdapter),('bitget',BitgetFuturesAdapter)]]
    futures += [pool.submit(endpoint,*args) for args in [('binance','https://fapi.binance.com/fapi/v1/exchangeInfo','symbols'),('upbit','https://api.upbit.com/v1/market/all'),('bithumb','https://api.bithumb.com/public/ticker/ALL_KRW','data'),('coinone','https://api.coinone.co.kr/public/v2/markets/KRW','markets')]]
    results=[f.result() for f in futures]
report={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'read_only':True,'credentials_used':False,'installed_windows_or_private_e2e':False,'results':results}
(root/'reports/v39213-acceptance-20261012/public-catalogues.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(results))
