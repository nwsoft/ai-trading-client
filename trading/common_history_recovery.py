"""Bounded, resumable CCXT derivatives close discovery (read endpoints only).

No nearest-order matching. Complete suffix coverage, stable position anchors,
terminal order totals, position lanes and an isolated owned cycle are required.
Legacy CCXT quantity is contracts; linear contractSize is applied explicitly.
Inverse quantity bases and unavailable history use statement review instead.
"""
import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal

from trading.binance_history_recovery import HistoryPending
from trading.recovery_statement import decimal, symbol_key, prove_isolated_cycle, apply_cycle
from trading.write_coordination import connection


class CommonHistoryRecovery:
    def __init__(self,recorder,client,venue,queried):
        self.recorder,self.client,self.venue,self.queried=recorder,client,venue,queried
        self.exchange=getattr(client,'exchange',None)
        self.job_id=''

    def db(self):
        return connection(self.recorder.db_path,operation='common_history_checkpoint',priority=20,timeout=5)

    def query(self,method,*args):
        self.queried(); return method(*args)

    def anchor(self,symbol):
        rows=self.query(self.exchange.fetch_positions,[symbol])
        if not isinstance(rows,list): raise RuntimeError('provider_history_query_failed')
        result=[]
        for row in rows:
            if not isinstance(row,dict): raise RuntimeError('provider_history_query_failed')
            if symbol_key(row.get('symbol'))!=symbol_key(symbol): continue
            size=decimal(row.get('contracts'))
            if size<0: raise ValueError('position_anchor_unavailable')
            if size==0: continue
            side=str(row.get('side','')).upper()
            if side not in {'LONG','SHORT'} or type(row.get('hedged')) is not bool:
                raise ValueError('position_anchor_unavailable')
            lane=side if row['hedged'] else 'BOTH'
            result.append((lane,str(size if side=='LONG' else -size),row.get('timestamp')))
        if len({r[0] for r in result})!=len(result): raise ValueError('position_anchor_unavailable')
        return sorted(result)

    def lane(self,order):
        info=order.get('info') or {}
        if self.venue=='okx':
            return {'net':'BOTH','long':'LONG','short':'SHORT'}.get(info.get('posSide'))
        if self.venue=='bybit':
            return {'0':'BOTH','1':'LONG','2':'SHORT'}.get(str(info.get('positionIdx')))
        if info.get('posMode')=='one_way_mode': return 'BOTH'
        if info.get('posMode')=='hedge_mode':
            return {'long':'LONG','short':'SHORT'}.get(info.get('posSide'))
        return None

    def recover(self,trade):
        ex=self.exchange
        if self.venue not in {'okx','bybit','bitget'} or ex is None:
            return 'provider_historical_evidence_unsupported'
        if not all(callable(getattr(ex,m,None)) for m in ('fetch_my_trades','fetch_order','fetch_positions')):
            return 'provider_historical_evidence_unsupported'
        credential=str(getattr(ex,'apiKey','') or '')
        if not credential: return 'recovery_credential_required'
        scope=hashlib.sha256((self.venue+':'+credential).encode()).hexdigest()
        symbol=self.client._normalize_symbol(trade['symbol'])
        market=(getattr(ex,'markets',{}) or {}).get(symbol,{})
        if market.get('linear') is not True or market.get('contractSize') is None:
            return 'contract_unit_verification_required'
        try: contract_size=decimal(market['contractSize'])
        except ValueError: return 'contract_unit_verification_required'
        if contract_size<=0: return 'contract_unit_verification_required'
        epoch=self.recorder._ledger_time_epoch(trade['entry_time'])
        if epoch is None: return 'execution_time_missing'
        now=int(time.time()*1000); start=int(epoch//86400)*86400000-86400000
        if start<now-89*86400000: return 'history_retention_exceeded'
        sid=hashlib.sha256(f'{scope}:{symbol}:{start}:{self.job_id}'.encode()).hexdigest()
        with self.db() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS common_history_sessions(id TEXT PRIMARY KEY, end INTEGER, anchor TEXT);
              CREATE TABLE IF NOT EXISTS common_history_pages(id TEXT,start INTEGER,end INTEGER,rows_json TEXT,
                PRIMARY KEY(id,start,end));
              CREATE TABLE IF NOT EXISTS common_history_orders(id TEXT,oid TEXT,order_json TEXT,PRIMARY KEY(id,oid));
            ''')
            session=db.execute('SELECT end,anchor FROM common_history_sessions WHERE id=?',(sid,)).fetchone()
        if not session:
            try: anchor=self.anchor(symbol)
            except ValueError: return 'position_anchor_unavailable'
            end=int(time.time()*1000)
            with self.db() as db:
                db.execute('INSERT INTO common_history_sessions VALUES(?,?,?)',(sid,end,json.dumps(anchor)))
                for left in range(start,end+1,86400000):
                    db.execute('INSERT INTO common_history_pages VALUES(?,?,?,NULL)',(sid,left,min(left+86400000-1,end)))
            raise HistoryPending()
        end,anchor_json=session
        with self.db() as db:
            page=db.execute('SELECT start,end FROM common_history_pages WHERE id=? AND rows_json IS NULL ORDER BY start LIMIT 1',(sid,)).fetchone()
        if page:
            left,right=page
            rows=self.query(ex.fetch_my_trades,symbol,left,100,{'until':right,'paginate':False})
            if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):
                raise RuntimeError('provider_history_query_failed')
            if any(r.get('timestamp') is None or not left<=int(r['timestamp'])<=right for r in rows):
                return 'history_identity_mismatch'
            with self.db() as db:
                if len(rows)>=100:
                    if left==right: return 'history_page_incomplete'
                    middle=(left+right)//2
                    db.execute('DELETE FROM common_history_pages WHERE id=? AND start=? AND end=?',(sid,left,right))
                    for a,b in ((left,middle),(middle+1,right)):
                        db.execute('INSERT INTO common_history_pages VALUES(?,?,?,NULL)',(sid,a,b))
                else:
                    encoded=json.dumps(rows)
                    used=db.execute('SELECT COALESCE(SUM(length(rows_json)),0) FROM common_history_pages').fetchone()[0]
                    if used+len(encoded.encode())>128*1024*1024:
                        return 'history_storage_limit'
                    db.execute('UPDATE common_history_pages SET rows_json=? WHERE id=? AND start=? AND end=?',
                               (encoded,sid,left,right))
            raise HistoryPending()
        with self.db() as db:
            pages=db.execute('SELECT start,end,rows_json FROM common_history_pages WHERE id=? ORDER BY start',(sid,)).fetchall()
            cached=dict(db.execute('SELECT oid,order_json FROM common_history_orders WHERE id=?',(sid,)).fetchall())
        through=start-1; fills={}
        for left,right,raw in pages:
            if left!=through+1 or raw is None: return 'history_page_incomplete'
            through=right
            for row in json.loads(raw):
                identity=str(row.get('id') or '')
                if not identity or not row.get('order') or symbol_key(row.get('symbol'))!=symbol_key(symbol):
                    return 'history_identity_mismatch'
                if identity in fills and fills[identity]!=row: return 'history_identity_mismatch'
                fills[identity]=row
        if through!=end: return 'history_page_incomplete'
        if len(fills)>20000: return 'history_page_incomplete'
        for oid in sorted({str(r['order']) for r in fills.values()}):
            if oid not in cached:
                order=self.query(ex.fetch_order,oid,symbol)
                if not isinstance(order,dict) or str(order.get('id'))!=oid:
                    return 'order_history_incomplete'
                with self.db() as db:
                    db.execute('INSERT INTO common_history_orders VALUES(?,?,?)',(sid,oid,json.dumps(order)))
                raise HistoryPending()
        normalized=[]
        for oid,raw in cached.items():
            order=json.loads(raw); lane=self.lane(order)
            group=[r for r in fills.values() if str(r['order'])==oid]
            if not lane: return 'position_anchor_unavailable'
            if order.get('status') not in {'closed','canceled','cancelled','expired'} or symbol_key(order.get('symbol'))!=symbol_key(symbol):
                return 'order_history_incomplete'
            try:
                if decimal(order.get('filled'))!=sum((decimal(r.get('amount')) for r in group),Decimal(0)):
                    return 'partial_or_quantity_mismatch'
                for r in group:
                    fee=r.get('fee') or {}
                    qty=decimal(r.get('amount')); price=decimal(r.get('price')); cost=decimal(fee.get('cost'))
                    if qty<=0 or price<=0 or r.get('side') not in {'buy','sell'} or r['side']!=order.get('side'):
                        return 'history_identity_mismatch'
                    from trading.pnl_evidence import provider_fill_gross_pnl
                    gross=provider_fill_gross_pnl(self.venue,r)
                    normalized.append({'execution_id':str(r['id']),'order_id':oid,'symbol':str(trade['symbol']),
                        'side':r['side'],'quantity':str(qty),'price':str(price),'fee':str(cost),
                        'fee_currency':str(fee.get('currency') or '').upper(),'position_side':lane,
                        'timestamp':datetime.fromtimestamp(int(r['timestamp'])/1000,timezone.utc).isoformat(),
                        'realized_pnl':None if gross is None else str(gross)})
            except (ValueError,TypeError,OverflowError): return 'provider_pnl_or_cost_evidence_incomplete'
        try: current=self.anchor(symbol)
        except ValueError: return 'position_anchor_unavailable'
        if json.dumps(current)!=anchor_json: return 'position_anchor_changed'
        # Same-size/flat round trips after the anchor also invalidate coverage.
        tail_end=int(time.time()*1000)
        tail=self.query(ex.fetch_my_trades,symbol,end+1,100,{'until':tail_end,'paginate':False}) if tail_end>end else []
        if not isinstance(tail,list): raise RuntimeError('provider_history_query_failed')
        if tail: return 'position_anchor_changed'
        if hashlib.sha256((self.venue+':'+str(getattr(ex,'apiKey','') or '')).encode()).hexdigest()!=scope:
            return 'credential_scope_changed'
        own=[r for r in normalized if r['order_id']==str(trade['order_id'])]
        if not own: return 'entry_order_not_in_history'
        quantity=next((decimal(r[1]) for r in current if r[0]==own[0]['position_side']),Decimal(0))
        proof,reason=prove_isolated_cycle(trade,normalized,closing_quantity=quantity,contract_size=contract_size)
        if reason:
            if quantity==0 and reason in {'position_cycle_ambiguous','partial_or_quantity_mismatch','execution_order_ambiguous'}:
                from trading.recovery_allocation import recover_shared_cycle
                return recover_shared_cycle(self.recorder,self.venue,trade,normalized,
                    {'kind':'api','session':sid,'start':start,'end':end},contract_size=contract_size)
            return reason
        return apply_cycle(self.recorder,self.venue,trade,proof,{'kind':'api','session':sid,
            'start':start,'end':end,'basis':'complete_isolated_linear_cycle','contract_size':str(contract_size),'funding_included':False})
