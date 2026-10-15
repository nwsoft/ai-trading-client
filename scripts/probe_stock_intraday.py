"""Operator-run read-only Windows broker probe. No settings writes/order methods.

Credentials are entered with getpass (not arguments/files). Output contains
only counts and finite status codes; do not share provider/customer raw logs.
"""
import argparse
from datetime import datetime, timezone
from getpass import getpass
import json
from pathlib import Path
import platform
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def inspect(adapter, symbol, timeframes):
    results=[]
    for tf in timeframes:
        try:
            rows=adapter.get_intraday_candles(symbol,tf,205)
            now=datetime.now(timezone.utc).timestamp()
            valid=all(isinstance(r.get('timestamp'),(int,float)) and r['timestamp']<r['close_timestamp']<=now for r in rows)
            ordered=all(a['timestamp']<b['timestamp'] for a,b in zip(rows,rows[1:]))
            results.append({'timeframe':tf,'bars':len(rows),'status':'READY' if len(rows)>=205 and valid and ordered else 'WARMING_OR_INSUFFICIENT' if valid and ordered else 'FAIL_INVALID_BARS'})
        except Exception as exc:
            results.append({'timeframe':tf,'bars':None,'status':'FAIL_READ','error_type':type(exc).__name__})
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--broker',choices=['kiwoom','kis'],required=True)
    p.add_argument('--symbol',default='005930')
    p.add_argument('--sandbox',action='store_true',help='KIS demo server; current-day minutes only')
    p.add_argument('--rounds',type=int,default=3)
    p.add_argument('--output',type=Path,default=Path('reports/stock-intraday-probe.json'))
    a=p.parse_args()
    if not 1<=a.rounds<=30 or not (a.symbol.isdigit() and len(a.symbol)==6):p.error('rounds 1..30; six-digit public symbol required')
    if platform.system()!='Windows' and a.broker=='kiwoom':p.error('Kiwoom requires Windows and packaged x86 host')
    if a.broker=='kiwoom':
        from trading.exchanges.adapters.kiwoom_process_proxy import KiwoomProcessProxy
        adapter=KiwoomProcessProxy(getpass('Kiwoom user ID (hidden): '),'','',getpass('Account (hidden; blank = login default): '))
    else:
        from trading.exchanges.adapters.korea_investment_stock_adapter import KoreaInvestmentStockAdapter
        adapter=KoreaInvestmentStockAdapter('','','',getpass('KIS account (hidden): '),
            app_key=getpass('KIS app key (hidden): '),app_secret=getpass('KIS app secret (hidden): '),sandbox=a.sandbox)
        adapter.log_event=lambda *args,**kwargs:None
    report={'broker':a.broker,'sandbox':a.sandbox,'orders_attempted':0,'rounds':[]}
    try:
        if not adapter.connect():raise RuntimeError('probe_connection_failed')
        for i in range(a.rounds):
            results=inspect(adapter,a.symbol,['3m','5m','15m','30m','1h'])
            report['rounds'].append(results)
            print(json.dumps({'round':i+1,'results':results}))
            if all(r['status']=='READY' for r in results):break
            if i+1<a.rounds:time.sleep(10)
        if a.broker=='kiwoom':
            # Account read detects opw00018 failures separately from charts;
            # print no holdings, amounts, identifiers or raw response.
            positions=adapter.get_positions_result()
            report['account_read_status']='PASS' if positions.get('status')=='success' else 'FAIL'
        last=report['rounds'][-1]
        report['status']='PASS' if all(r['status']=='READY' for r in last) and report.get('account_read_status','PASS')=='PASS' else 'NOT_ACCEPTED'
    except Exception as exc:
        report.update(status='FAIL',error_type=type(exc).__name__)
    finally:
        adapter.disconnect()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(report['status'])
    return 0 if report['status']=='PASS' else 2


if __name__=='__main__':raise SystemExit(main())
