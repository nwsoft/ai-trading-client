"""Read-only historical order evidence, retaining absent costs as unknown."""
from datetime import datetime
from zoneinfo import ZoneInfo
import math
import json


def _pages(fetch, rows_key, cursor_fields=()):
    """Never return a truncated page set as complete evidence."""
    output, cursor, seen = [], {}, set()
    for _ in range(20):
        data = fetch(cursor)
        if isinstance(data,dict) and data.get('rt_cd') not in (None,'0',0):
            raise RuntimeError('provider_history_query_failed')
        rows = data.get(rows_key) if isinstance(data,dict) else None
        if not isinstance(rows,list): raise RuntimeError('provider_history_query_failed')
        signature = json.dumps(rows,sort_keys=True,default=str)
        if rows and signature in seen: raise RuntimeError('history_page_incomplete')
        seen.add(signature); output.extend(rows)
        if len(output)>20000: raise RuntimeError('history_page_incomplete')
        cursor = {target:str(data.get(source) or '').strip() for source,target in cursor_fields}
        continuation = data.get('_tr_cont')
        more = continuation in {'M','F'} if continuation is not None else any(cursor.values())
        if not more: return output
        if not rows or not any(cursor.values()): raise RuntimeError('history_page_incomplete')
    raise RuntimeError('history_page_incomplete')


def _partner_pages(adapter,config,params,default_rows):
    """Partner endpoints/cursors belong to the signed provider profile, not KIS guesses."""
    cursor_fields=config.get('cursor_fields') or []
    if not isinstance(cursor_fields,list) or any(not isinstance(pair,(list,tuple)) or len(pair)!=2 or
            any(not isinstance(key,str) or not key or len(key)>100 for key in pair) for pair in cursor_fields):
        raise RuntimeError('broker_historical_contract_required')
    def fetch(cursor):
        data=adapter._get(config['path'],params={**params,**cursor})
        if not isinstance(data,dict):raise RuntimeError('provider_history_query_failed')
        if not cursor_fields and (data.get('next') or data.get('next_key')):
            raise RuntimeError('broker_historical_contract_required')
        return data
    return _pages(fetch,config.get('rows_key',default_rows),cursor_fields)


def order_fills(adapter, symbol, order_id, epoch):
    if not adapter.is_connected or not adapter.account_no:
        raise RuntimeError('provider_connection_required')
    day = datetime.fromtimestamp(epoch,ZoneInfo('Asia/Seoul')).strftime('%Y%m%d')
    broker = str(getattr(adapter,'exchange_name','')).lower()
    if 'kiwoom' in broker:
        raw = adapter._call_block_request('opw00007', 계좌번호=adapter.account_no,
            비밀번호=adapter.account_password, 비밀번호입력매체구분='00', 주문일자=day,
            조회구분='1', 주식채권구분='1', 매도수구분='0', 시작주문번호='',
            종목코드=adapter._normalize_symbol(symbol), output='계좌별주문체결내역상세', next=0)
        if raw is None: raise RuntimeError('provider_history_query_failed')
        items = raw.get('multi') if isinstance(raw,dict) else adapter._extract_records(raw)
        if not isinstance(items,list): raise RuntimeError('provider_history_query_failed')
        items = list(items)
        seen = {json.dumps(items,sort_keys=True,default=str)}
        for _ in range(19):
            if not getattr(getattr(adapter,'kiwoom',None),'tr_remained',False): break
            raw = adapter._call_block_request('opw00007', 계좌번호=adapter.account_no,
                비밀번호=adapter.account_password, 비밀번호입력매체구분='00', 주문일자=day,
                조회구분='1', 주식채권구분='1', 매도수구분='0', 시작주문번호='',
                종목코드=adapter._normalize_symbol(symbol), output='계좌별주문체결내역상세', next=2)
            page = raw.get('multi') if isinstance(raw,dict) else adapter._extract_records(raw)
            signature = json.dumps(page,sort_keys=True,default=str)
            if not isinstance(page,list) or not page or signature in seen: raise RuntimeError('history_page_incomplete')
            seen.add(signature); items.extend(page)
        if getattr(getattr(adapter,'kiwoom',None),'tr_remained',False): raise RuntimeError('history_page_incomplete')
        parse = adapter._parse_trade_record
    elif 'shinhan' in broker:
        # Contract endpoints are resolved by the existing partner profile.
        profile = getattr(adapter,'partner_profile',{})
        config = profile.get('recovery_history') or {}
        if not config.get('date_parameter'):
            raise RuntimeError('broker_historical_contract_required')
        items = _partner_pages(adapter,config,{'accNo':adapter.account_no,config['date_parameter']:day},'trades')
        parse = adapter._parse_order
    else:
        if 'korea' not in broker and broker != 'kis':
            config = (getattr(adapter,'partner_profile',{}) or {}).get('recovery_history') or {}
            if not config.get('date_parameter'): raise RuntimeError('broker_historical_contract_required')
            items = _partner_pages(adapter,config,{config['date_parameter']:day,'CANO':adapter.account_no[:8]},'output1')
            data = {}
        else:
            params = {
                'CANO':adapter.account_no[:8],'ACNT_PRDT_CD':adapter.account_no[8:] or '01',
                'INQR_STRT_DT':day,'INQR_END_DT':day,'SLL_BUY_DVSN_CD':'00','INQR_DVSN':'00',
                'PDNO':adapter._normalize_symbol(symbol),'CCLD_DVSN':'01','ORD_GNO_BRNO':'',
                'ODNO':str(order_id or ''),'INQR_DVSN_3':'00','INQR_DVSN_1':'','CTX_AREA_FK100':'','CTX_AREA_NK100':''}
            items = _pages(lambda cursor:adapter._get('/uapi/domestic-stock/v1/trading/inquire-daily-ccld',
                params={**params,**cursor}), 'output1',
                (('ctx_area_fk100','CTX_AREA_FK100'),('ctx_area_nk100','CTX_AREA_NK100')))
            data = {}
        if str(data.get('ctx_area_nk100') or '').strip() or data.get('next') or data.get('next_key'):
            raise RuntimeError('history_page_incomplete')
        parse = adapter._parse_order
    if not isinstance(items,list): raise RuntimeError('provider_history_query_failed')
    output = []
    for raw in items:
        row = parse(raw)
        identity = str(row.get('order_id') or row.get('id') or '')
        if order_id is not None and identity != str(order_id): continue
        if not identity: raise RuntimeError('history_fill_identity_missing')
        if adapter._normalize_symbol(row.get('symbol','')) != adapter._normalize_symbol(symbol):
            raise RuntimeError('provider_order_symbol_mismatch')
        quantity = row.get('filled_quantity',row.get('quantity'))
        # Never let a normalizer's order-limit-price fallback certify a fill.
        price = next((raw[k] for k in ('avg_prvs','avg_ccld_unpr','체결단가','체결가','filled_price','execPrc') if raw.get(k) not in (None,'')),None)
        if not price and raw.get('tot_ccld_amt') is not None and quantity:
            price = float(raw['tot_ccld_amt']) / float(quantity)
        if not quantity or not price: continue
        fee = next((raw[k] for k in ('fee','commission','tot_fee','수수료') if raw.get(k) not in (None,'')),None)
        tax = next((raw[k] for k in ('tax','제세금','제세금합','tax_amount') if raw.get(k) not in (None,'')),None)
        side = str(row.get('side','')).lower()
        # Buys incur no securities sell tax; sells require explicit tax evidence.
        cost = float(fee) + (float(tax) if tax is not None else 0) if fee is not None and (side=='buy' or tax is not None) else None
        stamp = str(row.get('timestamp') or row.get('time') or '')
        clock = str(raw.get('ord_tmd') or raw.get('체결시간') or '').strip()
        if len(stamp)==8 and stamp.isdigit() and len(clock)==6:
            stamp = datetime.strptime(stamp+clock,'%Y%m%d%H%M%S').replace(tzinfo=ZoneInfo('Asia/Seoul')).isoformat()
        elif len(stamp)==6 and stamp.isdigit():
            stamp = datetime.strptime(day+stamp,'%Y%m%d%H%M%S').replace(tzinfo=ZoneInfo('Asia/Seoul')).isoformat()
        execution_id = raw.get('execution_id') or raw.get('체결번호') or raw.get('execNo')
        output.append({'id':f'{day}:{identity}:{execution_id or "aggregate"}', 'order':identity,'symbol':symbol,'side':side,
            'amount':quantity,'price':price,'timestamp':stamp,
            'fee':{'cost':cost,'currency':'KRW'},'_execution_confirmed':True,'info':raw})
    return output


def recover_exact_orders(recorder, client, venue, trade, queried):
    from trading.record_recovery import validate_fills
    if not trade.get('order_id') or not trade.get('exit_order_id'):
        return 'broker_close_order_identity_required'
    if not trade.get('exit_time'): return 'execution_time_missing'
    fetch = getattr(client,'get_recovery_order_fills',None)
    if not callable(fetch): return 'broker_historical_evidence_unsupported'
    incoming = {**trade,'exit_order_id':trade['order_id'],'side':'SHORT','exit_time':trade['entry_time']}
    evidence=[]
    for item in (incoming,trade):
        epoch=recorder._ledger_time_epoch(item['exit_time'])
        if epoch is None: return 'execution_time_missing'
        queried()
        try: rows=fetch(item['symbol'],str(item['exit_order_id']),epoch)
        except RuntimeError as exc:
            if str(exc) in {'broker_historical_contract_required','history_page_incomplete'}: return str(exc)
            raise
        rows,reason=validate_fills(item,rows)
        if reason:return reason
        if any(str(row['fee'].get('currency','')).upper()!='KRW' for row in rows):return 'entry_fee_conversion_required'
        evidence.append(rows)
    buy,sell=evidence
    qty=float(trade['quantity'])
    entry=sum(float(r['amount'])*float(r['price']) for r in buy)/qty
    if abs(entry-float(trade['entry_price'])) > max(1e-8,entry*1e-8):
        return 'entry_price_evidence_mismatch'
    exit_price=sum(float(r['amount'])*float(r['price']) for r in sell)/qty
    costs=[sum(float(r['fee']['cost']) for r in rows) for rows in evidence]
    gross=(exit_price-entry)*qty
    net=gross-sum(costs)
    if not all(math.isfinite(n) for n in (entry,exit_price,net,*costs)) or min(costs)<0:return 'fee_or_fill_data_incomplete'
    with recorder._write_connection(operation='broker_exact_order_recovery') as db:
        owners=db.execute('SELECT count(*) FROM trade_log WHERE lower(exchange)=? AND order_id=? AND symbol=?',
                          (venue,trade['order_id'],trade['symbol'])).fetchone()[0]
        if owners!=1:return 'entry_order_allocation_required'
        result=db.execute('''UPDATE trade_log SET entry_price=?,exit_price=?,gross_pnl=?,net_pnl=?,pnl=?,
            pnl_percent=?,entry_fee=?,exit_fee=?,fees=?,entry_fee_asset='KRW',exit_fee_asset='KRW',
            settlement_currency='KRW',pnl_source='broker_exact_order_costs',reconciliation_status='broker_order_linked'
            WHERE id=? AND order_id=? AND exit_order_id=? AND quantity=? AND entry_price=? AND exit_time=?''',
            (entry,exit_price,gross,net,net,net/(entry*qty)*100,*costs,sum(costs),trade['id'],trade['order_id'],
             trade['exit_order_id'],qty,trade['entry_price'],trade['exit_time']))
        if not result.rowcount:return 'record_identity_changed'
    recorder.save_exchange_execution_history(venue,buy+sell,source='broker_exact_order_recovery',reconcile=False)
    return ''
