"""Upbit/Bithumb read-only native closed-order discovery.

Uses native documented history APIs, independent of older CCXT history support.
Order aggregates use actual execution prices/quantities and final paid_fee;
order limit prices, estimated costs and empty-on-error are never evidence.
"""
import hashlib
import time
import uuid
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode

from ccxt import Exchange
import requests

from trading.recovery_statement import decimal


def native_reader(adapter,session=None):
    venue=str(adapter.exchange_name).lower()
    if venue not in {'upbit','bithumb'}:raise RuntimeError('provider_historical_evidence_unsupported')
    key=getattr(adapter,'api_key',''); secret=getattr(adapter,'secret_key','')
    if not key or not secret:raise RuntimeError('recovery_credential_required')
    transport=session or requests.Session(); calls=0
    deadline=time.monotonic()+120
    def get(path,params):
        nonlocal calls
        calls+=1
        if calls>250 or time.monotonic()>deadline:raise RuntimeError('history_page_incomplete')
        query='&'.join(f'{k}={v}' for k,v in params.items())
        payload={'access_key':key,'nonce':str(uuid.uuid4())}
        if query:payload.update(query_hash=hashlib.sha512(query.encode()).hexdigest(),query_hash_alg='SHA512')
        if venue=='bithumb':payload['timestamp']=int(time.time()*1000)
        token=Exchange.jwt(payload,secret.encode(),algorithm='sha256')
        # Leave capacity for the trading engine even during maintenance.
        if calls>1:time.sleep(0.15)
        response=transport.get(f'https://api.{venue}.com'+path+'?'+urlencode(params),
            headers={'Authorization':'Bearer '+token},timeout=15,allow_redirects=False)
        if response.status_code in {401,403}:raise RuntimeError('history_api_permission_required')
        if response.status_code==429:raise RuntimeError('provider_history_rate_limited')
        if response.status_code!=200:raise RuntimeError('provider_history_query_failed')
        return response.json()
    return get


def holding_quantity(adapter,symbol,session=None):
    rows=native_reader(adapter,session)('/v1/accounts',{})
    if not isinstance(rows,list):raise RuntimeError('position_anchor_unavailable')
    balances={}
    for row in rows:
        currency=row.get('currency')
        if not currency or currency in balances:raise RuntimeError('position_anchor_unavailable')
        qty=decimal(row.get('balance'))+decimal(row.get('locked'))
        if qty<0:raise RuntimeError('position_anchor_unavailable')
        balances[currency.upper()]=qty
    # Native accounts returns the complete list; absence here means no holding.
    return balances.get(adapter._normalize_symbol(symbol).split('/')[0],Decimal(0))


def day_fills(adapter,symbol,epoch,session=None):
    venue=str(adapter.exchange_name).lower()
    get=native_reader(adapter,session)
    symbol=adapter._normalize_symbol(symbol)
    base,quote=symbol.split('/')
    market=quote+'-'+base
    start=int(epoch*1000); end=min(int(time.time()*1000),start+86400000-1)
    orders={}
    if venue=='bithumb':
        cursor=''; seen=set()
        for _ in range(20):
            params={'market':market,'start_time':str(start),'end_time':str(end),'limit':100,'order_by':'asc'}
            if cursor:params['next_key']=cursor
            data=get('/v2/orders/history',params)
            if not isinstance(data,dict) or not isinstance(data.get('data'),list) or type(data.get('has_next')) is not bool:
                raise RuntimeError('provider_history_query_failed')
            for row in data['data']:
                oid=str(row.get('order_id') or '')
                if not oid or oid in orders:raise RuntimeError('history_identity_mismatch')
                orders[oid]=row
            if not data['has_next']:break
            cursor=str(data.get('next_key') or '')
            if not cursor or cursor in seen or not data['data']:raise RuntimeError('history_page_incomplete')
            seen.add(cursor)
        else:raise RuntimeError('history_page_incomplete')
    else:
        for state in ('done','cancel'):
            windows=[(start,end)]
            while windows:
                left,right=windows.pop()
                page=get('/v1/orders/closed',{'market':market,'state':state,'start_time':str(left),'end_time':str(right),'limit':100,'order_by':'asc'})
                if not isinstance(page,list):raise RuntimeError('provider_history_query_failed')
                if len(page)>=100:
                    if left==right:raise RuntimeError('history_page_incomplete')
                    middle=(left+right)//2; windows.extend(((middle+1,right),(left,middle))); continue
                for row in page:
                    oid=str(row.get('uuid') or '')
                    if not oid or oid in orders:raise RuntimeError('history_identity_mismatch')
                    created=datetime.fromisoformat(str(row['created_at']).replace('Z','+00:00')).timestamp()*1000
                    if not left<=created<=right:raise RuntimeError('history_time_invalid')
                    orders[oid]=row
    result=[]
    for oid,summary in orders.items():
        if decimal(summary.get('executed_volume'))==0:continue
        row=get('/v1/order',{'uuid':oid})
        if str(row.get('uuid') or row.get('order_id'))!=oid or row.get('state') not in {'done','cancel'} or row.get('market')!=market:
            raise RuntimeError('history_identity_mismatch')
        trades=row.get('trades')
        if not isinstance(trades,list) or not trades:raise RuntimeError('exchange_fill_not_found')
        quantity=sum((decimal(r['volume']) for r in trades),Decimal(0))
        if quantity<=0 or quantity!=decimal(row.get('executed_volume')):raise RuntimeError('partial_or_quantity_mismatch')
        if len({r.get('uuid') for r in trades})!=len(trades) or any(not r.get('uuid') for r in trades):
            raise RuntimeError('history_fill_identity_missing')
        if row.get('side') not in {'bid','ask'} or any(r.get('side')!=row['side'] or r.get('market')!=market for r in trades):
            raise RuntimeError('history_identity_mismatch')
        price=sum((decimal(r['volume'])*decimal(r['price']) for r in trades),Decimal(0))/quantity
        stamps=[datetime.fromisoformat(r['created_at'].replace('Z','+00:00')).timestamp() for r in trades]
        result.append({'id':'order-aggregate:'+oid,'order':oid,'symbol':symbol,'side':'buy' if row['side']=='bid' else 'sell',
            'amount':str(quantity),'price':str(price),'timestamp':max(stamps)*1000,
            'fee':{'cost':str(decimal(row.get('paid_fee'))),'currency':quote},'_execution_confirmed':True,
            'info':row})
    return result
