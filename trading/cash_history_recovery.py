"""Resumable spot/stock history discovery; read-only provider calls outside DB locks."""
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from trading.binance_history_recovery import HistoryPending
from trading.exchanges.venue_capabilities import STOCK_VENUES
from trading.recovery_statement import decimal, symbol_key, prove_isolated_cycle, apply_cycle
from trading.write_coordination import connection


class CashHistoryRecovery:
    def __init__(self,recorder,client,venue,queried):
        self.recorder,self.client,self.venue,self.queried=recorder,client,venue,queried
        self.job_id=''

    def scope(self):
        ex=getattr(self.client,'exchange',None)
        identity=str(getattr(self.client,'account_no','') or getattr(self.client,'api_key','') or getattr(ex,'apiKey',''))
        if not identity: raise RuntimeError('recovery_credential_required')
        return hashlib.sha256((self.venue+':'+identity).encode()).hexdigest()

    def flat(self,symbol):
        self.queried()
        if self.venue in STOCK_VENUES:
            snapshot=self.client.get_positions_result()
            if not isinstance(snapshot,dict) or snapshot.get('status')!='success' or not isinstance(snapshot.get('positions'),list):
                raise RuntimeError('provider_history_query_failed')
            for row in snapshot['positions']:
                if symbol_key(row.get('symbol') or row.get('code'))==symbol_key(symbol) and decimal(row.get('quantity'))!=0:
                    return False
            return True
        exchange=getattr(self.client,'exchange',None)
        native=getattr(self.client,'get_recovery_holding_quantity',None)
        if callable(native):return decimal(native(symbol))==0
        if not exchange or not callable(getattr(exchange,'fetch_balance',None)):
            raise RuntimeError('position_anchor_unavailable')
        balance=exchange.fetch_balance()
        total=balance.get('total') if isinstance(balance,dict) else None
        base=self.client._normalize_symbol(symbol).split('/')[0]
        # A missing currency is not a certified zero from an arbitrary normalizer.
        if not isinstance(total,dict) or base not in total: raise RuntimeError('position_anchor_unavailable')
        return decimal(total[base])==0

    def day(self,symbol,day):
        epoch=datetime.fromisoformat(day).replace(tzinfo=ZoneInfo('Asia/Seoul')).timestamp()
        self.queried()
        if self.venue in STOCK_VENUES:
            rows=self.client.get_recovery_order_fills(symbol,None,epoch)
        else:
            fetch=getattr(self.client,'get_recovery_day_fills',None)
            if not callable(fetch): raise RuntimeError('provider_historical_evidence_unsupported')
            rows=fetch(symbol,epoch)
        if not isinstance(rows,list): raise RuntimeError('provider_history_query_failed')
        normalized=[]; seen=set()
        for row in rows:
            if row.get('_execution_confirmed') is not True: raise RuntimeError('history_identity_mismatch')
            oid=str(row.get('order') or ''); fid=str(row.get('id') or '')
            if not oid or not fid or fid in seen or symbol_key(row.get('symbol'))!=symbol_key(symbol):
                raise RuntimeError('history_identity_mismatch')
            seen.add(fid)
            stamp=self.recorder._ledger_time_epoch(row.get('timestamp'))
            if stamp is not None and stamp>1e11: stamp/=1000
            if stamp is None or not epoch<=stamp<epoch+86400: raise RuntimeError('history_time_invalid')
            qty=decimal(row.get('amount')); price=decimal(row.get('price'))
            fee=row.get('fee') or {}; cost=decimal(fee.get('cost'))
            if qty<=0 or price<=0 or row.get('side') not in {'buy','sell'}:raise RuntimeError('history_identity_mismatch')
            # Broker order_fills already combines explicit fee + sell tax.
            normalized.append({'execution_id':fid,'order_id':oid,'symbol':symbol,'side':row['side'],
                'quantity':str(qty),'price':str(price),'fee':str(cost),'fee_currency':str(fee.get('currency') or '').upper(),
                'tax':'0','position_side':'BOTH','timestamp':datetime.fromtimestamp(stamp,timezone.utc).isoformat()})
        return sorted(normalized,key=lambda r:(r['timestamp'],r['execution_id']))

    def recover(self,trade):
        if self.client is None:return 'provider_connection_required'
        epoch=self.recorder._ledger_time_epoch(trade['entry_time'])
        if epoch is None:return 'execution_time_missing'
        scope=self.scope()
        start=datetime.fromtimestamp(epoch,ZoneInfo('Asia/Seoul')).date()
        today=datetime.now(ZoneInfo('Asia/Seoul')).date()
        if not 0<=(today-start).days<=3650:return 'history_retention_exceeded'
        if not self.flat(trade['symbol']):return 'position_anchor_not_flat'
        sid=hashlib.sha256(f'{scope}:{trade["symbol"]}:{start}:{today}:{self.job_id}'.encode()).hexdigest()
        def db():return connection(self.recorder.db_path,operation='cash_history_checkpoint',priority=20,timeout=5)
        with db() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS cash_history_days(id TEXT,day TEXT,rows_json TEXT,PRIMARY KEY(id,day))')
            for i in range((today-start).days+1):
                conn.execute('INSERT OR IGNORE INTO cash_history_days VALUES(?,?,NULL)',(sid,str(start+timedelta(days=i))))
            pending=conn.execute('SELECT day FROM cash_history_days WHERE id=? AND rows_json IS NULL ORDER BY day LIMIT 1',(sid,)).fetchone()
        if pending:
            rows=self.day(trade['symbol'],pending[0])
            encoded=json.dumps(rows,sort_keys=True)
            with db() as conn:
                used=conn.execute('SELECT COALESCE(SUM(length(rows_json)),0) FROM cash_history_days').fetchone()[0]
                if used+len(encoded.encode())>128*1024*1024:return 'history_storage_limit'
                conn.execute('UPDATE cash_history_days SET rows_json=? WHERE id=? AND day=?',(encoded,sid,pending[0]))
            raise HistoryPending()
        with db() as conn:
            pages=conn.execute('SELECT day,rows_json FROM cash_history_days WHERE id=? ORDER BY day',(sid,)).fetchall()
        # A same-size/flat round-trip during recovery must invalidate the snapshot.
        if json.dumps(self.day(trade['symbol'],str(today)),sort_keys=True)!=pages[-1][1]:return 'position_anchor_changed'
        if not self.flat(trade['symbol']) or self.scope()!=scope:return 'position_anchor_changed'
        rows=[row for _,raw in pages for row in json.loads(raw)]
        if len(rows)>20000:return 'history_page_incomplete'
        evidence={'kind':'api','session':sid,'basis':'complete_cash_order_history','start':str(start),'end':str(today)}
        proof,reason=prove_isolated_cycle(trade,rows,opening_quantity=Decimal(0))
        if not reason:return apply_cycle(self.recorder,self.venue,trade,proof,evidence)
        if reason in {'position_cycle_ambiguous','partial_or_quantity_mismatch','execution_order_ambiguous'}:
            from trading.recovery_allocation import recover_shared_cycle
            return recover_shared_cycle(self.recorder,self.venue,trade,rows,evidence)
        return reason
