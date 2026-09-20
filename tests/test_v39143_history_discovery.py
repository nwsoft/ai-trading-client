"""Native-API contract replay. Fixtures are not actual customer API responses."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import sqlite3

import pytest

from api.binance_client import BinanceClient
from trading.binance_history_recovery import reconstruct_cycle, BinanceHistoryRecovery, HistoryPending
from trading.record_recovery import RecordRecovery
from trading.record_recovery_adapters import RecoveryResolver
from trading.profitability_validation import ProfitabilityValidator
from trading.pnl_evidence import performance_evidence
from test_v39139_pnl_audit import setup_trade


BASE = 1789689600000  # deterministic UTC-day boundary


def fixtures(count=1, partial=False):
    fills, orders, income = [], [], []
    for i in range(count):
        entry_id, close_id = str(100+i*3), str(101+i*3)
        when = BASE+1000+i*10000
        pair = [dict(id=1000+i*3,orderId=entry_id,symbol='BTCUSDT',side='BUY',
                     qty='2',price='100',commission='0.2',commissionAsset='USDT',realizedPnl='0',
                     positionSide='BOTH',time=when),
                dict(id=1001+i*3,orderId=close_id,symbol='BTCUSDT',side='SELL',
                     qty='2',price='95',commission='0.1',commissionAsset='USDT',realizedPnl='-10',
                     positionSide='BOTH',time=when+1000)]
        if partial:
            pair[1].update(qty='1',commission='0.05',realizedPnl='-5')
            pair.append({**pair[1], 'id':1002+i*3,'orderId':str(102+i*3),'time':when+2000})
        fills.extend(pair)
        for row in pair:
            orders.append(dict(orderId=row['orderId'],symbol='BTCUSDT',side=row['side'],
                               positionSide='BOTH',status='FILLED',executedQty=row['qty'],time=row['time']))
            if row['side']=='SELL':
                income.append(dict(tranId=row['id'],tradeId=str(row['id']),symbol='BTCUSDT',
                                   incomeType='REALIZED_PNL',asset='USDT',income=row['realizedPnl'],time=row['time']))
    return {'fills':fills,'orders':orders,'algos':[],'income':income}


class NativeReplay:
    def __init__(self, data):
        self.data = data
        self.config = SimpleNamespace(api_key='fixture-only-no-real-key')
        self.calls = []
        self.anchor = [dict(symbol='BTCUSDT',positionSide='BOTH',positionAmt='0',updateTime=BASE)]
    def get_synced_timestamp(self): return BASE+86400000-1
    def get_recovery_position_anchor(self, symbol):
        self.calls.append(('anchor',symbol))
        return deepcopy(self.anchor)
    def get_recovery_history_page(self,kind,symbol,start,end):
        self.calls.append((kind,symbol,start,end))
        return deepcopy([r for r in self.data[kind] if start <= int(r.get('time',BASE+1000)) <= end][-1000:])


def setup(tmp_path, count=1, partial=False):
    recorder, tid, _ = setup_trade(tmp_path,exit_id=None)
    with sqlite3.connect(recorder.db_path) as db:
        db.row_factory=sqlite3.Row
        row=dict(db.execute('SELECT * FROM trade_log WHERE id=?',(tid,)).fetchone());row.pop('id')
        for i in range(count):
            row.update(order_id=str(100+i*3),entry_time=datetime.fromtimestamp((BASE+1000+i*10000)/1000,timezone.utc).isoformat(),
                       exit_time=datetime.fromtimestamp((BASE+3000+i*10000)/1000,timezone.utc).isoformat(),entry_fee=None)
            if i==0:
                db.execute('UPDATE trade_log SET '+','.join(k+'=?' for k in row)+' WHERE id=?',(*row.values(),tid))
            else:
                db.execute('INSERT INTO trade_log ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
    client=NativeReplay(fixtures(count,partial))
    resolver=RecoveryResolver(recorder,client,'binance')
    job=RecordRecovery(recorder,resolver,now=lambda:(BASE+86400000)/1000,request_budget=10000,delay=0)
    return recorder,tid,client,job


@pytest.mark.parametrize('count',[1,40,301])
def test_missing_exit_and_protection_history_recovers_without_local_order_id(tmp_path,count):
    r,tid,c,job=setup(tmp_path,count)
    status=job.start('binance',background=False)
    assert status['state']=='checked'
    assert status['recovered']==count
    assert r.execute_query('SELECT COUNT(*),SUM(net_pnl) FROM trade_log')[0]==(count,pytest.approx(-10.3*count))
    assert {call[0] for call in c.calls}=={'anchor','fills','orders','algos','income'}
    rows=[]
    with sqlite3.connect(r.db_path) as db:
        db.row_factory=sqlite3.Row
        rows=[{**dict(row),**performance_evidence(dict(row))} for row in db.execute('SELECT * FROM trade_log')]
    # No reconciliation block remains; losses still fail profitability policy.
    assert 'pnl_reconciliation_required' not in ProfitabilityValidator().evaluate_strategy(rows).get('reasons',[])
    assert status['auto_started'] is False and status['resume_authorized'] is False


def test_multiple_partial_close_orders_have_exact_claims_not_fake_order_id(tmp_path):
    r,tid,c,job=setup(tmp_path,partial=True)
    assert job.start('binance',background=False)['recovered']==1
    assert r.execute_query('SELECT exit_order_id,net_pnl FROM trade_log')[0]==(None,pytest.approx(-10.3))
    assert r.execute_query('SELECT COUNT(*) FROM recovery_cycle_claims')[0][0]==3
    baseline=r.execute_query('SELECT * FROM trade_log')
    job.now=lambda:(BASE+86400000)/1000+31
    assert job.start('binance',background=False)['total']==0
    assert baseline==r.execute_query('SELECT * FROM trade_log')


@pytest.mark.parametrize('case',['mixed_entry','existing_position','missing_income','wrong_income','unknown_fee',
                                 'partial_history','bad_order','hedge_mismatch','duplicate_fill','unknown_position_side'])
def test_ambiguous_or_incomplete_provider_proof_never_certifies(tmp_path,case):
    r,tid,c,job=setup(tmp_path)
    if case=='mixed_entry':
        c.data['fills'][0]['qty']='1'
        c.data['fills'].append({**c.data['fills'][0],'id':9999,'orderId':'999','time':BASE+1500})
    if case=='existing_position': c.anchor[0]['positionAmt']='1'
    if case=='missing_income': c.data['income']=[]
    if case=='wrong_income': c.data['income'][0]['income']='10'
    if case=='unknown_fee': c.data['fills'][1]['commissionAsset']='BNB'
    if case=='partial_history': c.data['fills'].pop()
    if case=='bad_order': c.data['orders'][1]['status']='NEW'
    if case=='hedge_mismatch': c.data['fills'][1]['positionSide']='SHORT'
    if case=='duplicate_fill': c.data['fills'][1]['id']=c.data['fills'][0]['id']
    if case=='unknown_position_side': c.data['fills'][1].pop('positionSide')
    result=job.start('binance',background=False)
    assert result['recovered']==0
    assert r.execute_query('SELECT exit_order_id,net_pnl FROM trade_log')[0]==(None,None)


def test_manual_cycles_before_and_after_do_not_prevent_owned_cycle_recovery(tmp_path):
    r,tid,c,job=setup(tmp_path)
    extra=fixtures(3)
    c.data=extra
    assert job.start('binance',background=False)['recovered']==1
    assert r.execute_query('SELECT COUNT(*) FROM trade_log')[0][0]==1


def test_budget_restart_uses_persisted_pages(tmp_path):
    r,tid,c,job=setup(tmp_path)
    job.request_budget=2
    status=job.start('binance',background=False)
    assert status['state']=='paused' and status['processed']==0
    for _ in range(10):
        job=RecordRecovery(r,RecoveryResolver(r,c,'binance'),now=lambda:(BASE+86400000)/1000,request_budget=2,delay=0)
        status=job.start('binance',background=False)
        if status['state']!='paused': break
    assert status['recovered']==1
    assert sum(call[0]=='fills' for call in c.calls)==1


def test_timeout_retries_pending_page_and_does_not_call_it_empty_history(tmp_path):
    r,tid,c,job=setup(tmp_path)
    original=c.get_recovery_history_page
    c.get_recovery_history_page=lambda *_: (_ for _ in ()).throw(TimeoutError('private-provider-message'))
    result=job.start('binance',background=False)
    assert result['state']=='failed' and result['processed']==0 and result['error']=='TimeoutError'
    c.get_recovery_history_page=original
    job.now=lambda:(BASE+86400000)/1000+31
    assert job.start('binance',background=False)['recovered']==1


def test_saturated_time_window_splits_and_proves_full_coverage(tmp_path):
    r,tid,c,job=setup(tmp_path,600)
    status=job.start('binance',background=False)
    assert status['recovered']==600
    assert sum(call[0]=='fills' for call in c.calls)>1


def test_snapshot_changes_during_collection_never_writes_pnl(tmp_path):
    r,tid,c,job=setup(tmp_path)
    original=c.get_recovery_history_page
    def fetch(*args):
        c.anchor[0]['updateTime']=BASE+100
        return original(*args)
    c.get_recovery_history_page=fetch
    assert job.start('binance',background=False)['reasons']=={'position_anchor_changed':1}
    assert r.execute_query('SELECT net_pnl FROM trade_log')[0][0] is None


def test_native_endpoints_are_signed_read_only_time_bounded_and_errors_propagate():
    client=object.__new__(BinanceClient)
    client._has_api_keys=lambda: True
    seen=[]
    client._get_futures_signed=lambda path,params: seen.append((path,params)) or []
    for kind in ('fills','orders','algos','income'):
        assert client.get_recovery_history_page(kind,'BTCUSDT',BASE,BASE+1000)==[]
    assert all('orderId' not in params and params['limit']==1000 for _,params in seen)
    client._get_futures_signed=lambda *_: {'code':-1003,'msg':'private'}
    with pytest.raises(RuntimeError,match='provider_history_query_failed'):
        client.get_recovery_history_page('fills','BTCUSDT',BASE,BASE+1000)
    with pytest.raises(ValueError): client.get_recovery_history_page('fills','BTCUSDT',BASE,BASE+7*86400000)
    with pytest.raises(RuntimeError): client.get_recovery_position_anchor('BTCUSDT')


@pytest.mark.parametrize('count',[1,2])
def test_first_positive_close_not_lost_when_next_close_arrives(tmp_path,count):
    r,tid,c,job=setup(tmp_path,count)
    for i,row in enumerate(c.data['fills']):
        row['commission']='0.002' if row['side']=='BUY' else '0.003'
        if row['side']=='SELL':
            row['realizedPnl']='0.25' if i==1 else '0.02'
            row['price']='100.125' if i==1 else '100.01'
    for i,row in enumerate(c.data['income']):
        row['income']='0.25' if i==0 else '0.02'
    assert job.start('binance',background=False)['recovered']==count
    assert r.execute_query('SELECT SUM(gross_pnl),SUM(net_pnl) FROM trade_log')[0]==(
        pytest.approx(0.25 if count==1 else 0.27),pytest.approx(0.245 if count==1 else 0.26))
    assert r.execute_query('SELECT COUNT(*) FROM exchange_execution_log')[0][0]==count*2
    from web_platform.query_services import AccountQueryService
    stats=AccountQueryService(r.db_path).trading_statistics(asset_class='crypto',source='binance',period='all')
    assert stats['reconciled_closed_count']==count
    assert stats['gross_pnl_by_currency']['USDT']==pytest.approx(0.25 if count==1 else 0.27)
    assert stats['pnl_by_currency']['USDT']==pytest.approx(0.245 if count==1 else 0.26)


def test_delayed_income_is_refetched_on_new_check_not_cached_forever(tmp_path):
    r,tid,c,job=setup(tmp_path)
    income=c.data['income']; c.data['income']=[]
    assert job.start('binance',background=False)['reasons']=={'income_reconciliation_required':1}
    c.data['income']=income
    job.now=lambda:(BASE+86400000)/1000+31
    assert job.start('binance',background=False)['recovered']==1
    assert sum(call[0]=='income' for call in c.calls)==2


def test_crash_after_atomic_repair_before_checkpoint_recovers_idempotently(tmp_path):
    r,tid,c,job=setup(tmp_path)
    original=BinanceHistoryRecovery.apply
    def crash(self,*args):
        result=original(self,*args)
        if not result: raise RuntimeError('injected crash')
        return result
    from unittest.mock import patch
    with patch.object(BinanceHistoryRecovery,'apply',crash):
        assert job.start('binance',background=False)['state']=='failed'
    baseline=r.execute_query('SELECT * FROM trade_log')
    job.now=lambda:(BASE+86400000)/1000+31
    assert job.start('binance',background=False)['recovered']==1
    assert baseline==r.execute_query('SELECT * FROM trade_log')
    assert r.execute_query('SELECT COUNT(*) FROM exchange_execution_log')[0][0]==2


def test_key_change_cannot_reuse_old_account_history(tmp_path):
    r,tid,c,job=setup(tmp_path)
    job.request_budget=2
    assert job.start('binance',background=False)['state']=='paused'
    c.config.api_key='different-fixture-account'
    assert job.start('binance',background=False)['reasons']=={'credential_scope_changed':1}
    assert r.execute_query('SELECT net_pnl FROM trade_log')[0][0] is None


def test_execution_storage_failure_does_not_certify_trade(tmp_path,monkeypatch):
    r,tid,c,job=setup(tmp_path)
    monkeypatch.setattr(r,'save_exchange_execution_history',lambda *a,**kw: {})
    assert job.start('binance',background=False)['reasons']=={'execution_storage_incomplete':1}
    assert r.execute_query('SELECT net_pnl FROM trade_log')[0][0] is None


@pytest.mark.parametrize('position_side,direction',[('BOTH','SHORT'),('LONG','LONG'),('SHORT','SHORT')])
def test_short_and_hedge_position_sides(tmp_path,position_side,direction):
    r,tid,c,job=setup(tmp_path)
    with sqlite3.connect(r.db_path) as db:
        db.execute('UPDATE trade_log SET side=?',(direction,))
    for row in c.data['fills']:
        row['positionSide']=position_side
        if direction=='SHORT':
            row['side']='SELL' if row['side']=='BUY' else 'BUY'
            if row['side']=='BUY': row['price']='105'
    for row,fill in zip(c.data['orders'],c.data['fills']):
        row['positionSide']=position_side; row['side']=fill['side']
    c.anchor[0]['positionSide']=position_side
    assert job.start('binance',background=False)['recovered']==1
    assert r.execute_query('SELECT net_pnl FROM trade_log')[0][0]==pytest.approx(-10.3)


def test_multiple_entry_fills_and_multiple_close_fills_same_order(tmp_path):
    r,tid,c,job=setup(tmp_path)
    original=deepcopy(c.data['fills'])
    c.data['fills']=[]; c.data['income']=[]
    for i,row in enumerate(original):
        for j in range(2):
            fill={**row,'id':5000+i*2+j,'qty':'1','commission':str(Decimal(row['commission'])/2),
                  'realizedPnl':str(Decimal(row['realizedPnl'])/2),'time':row['time']+j}
            c.data['fills'].append(fill)
            if fill['side']=='SELL':
                c.data['income'].append(dict(tranId=fill['id'],tradeId=str(fill['id']),symbol='BTCUSDT',
                    incomeType='REALIZED_PNL',asset='USDT',income=fill['realizedPnl'],time=fill['time']))
    assert job.start('binance',background=False)['recovered']==1
    assert r.execute_query('SELECT COUNT(*) FROM exchange_execution_log')[0][0]==4
    assert r.execute_query('SELECT net_pnl FROM trade_log')[0][0]==pytest.approx(-10.3)


def test_existing_fill_claim_cannot_be_reassigned(tmp_path):
    r,tid,c,job=setup(tmp_path)
    resolver=job.resolver
    history=BinanceHistoryRecovery(r,c,resolver._queried)
    with history.db() as db:
        db.execute('INSERT INTO recovery_cycle_claims VALUES(?,?,?,?,?)',
                   (history.scope,'BTCUSDT','1001',99999,'preexisting'))
    assert job.start('binance',background=False)['reasons']=={'order_attribution_conflict':1}
    assert r.execute_query('SELECT net_pnl FROM trade_log')[0][0] is None


def test_incomplete_entire_millisecond_is_not_claimed_complete(tmp_path):
    r,tid,c,job=setup(tmp_path)
    original=c.get_recovery_history_page
    def saturated(kind,symbol,start,end):
        if kind=='fills' and start <= BASE+1000 <= end:
            return [{**c.data['fills'][0],'id':9999+i} for i in range(1000)]
        return original(kind,symbol,start,end)
    c.get_recovery_history_page=saturated
    assert job.start('binance',background=False)['reasons']=={'history_page_incomplete':1}
    assert r.execute_query('SELECT net_pnl FROM trade_log')[0][0] is None


def test_exchange_manager_wrapper_uses_connected_native_client(tmp_path):
    r,tid,c,job=setup(tmp_path)
    from trading.exchanges.adapters.binance_futures_adapter import BinanceFuturesAdapter
    wrapper=object.__new__(BinanceFuturesAdapter)
    wrapper.client=c
    wrapper.connect=lambda: pytest.fail('must reuse existing native connection')
    job.resolver=RecoveryResolver(r,wrapper,'binance')
    assert job.start('binance',background=False)['recovered']==1


@pytest.mark.parametrize('value',['NaN','Infinity','1e999','1e-999'])
def test_invalid_provider_amount_never_writes_nonfinite_values(tmp_path,value):
    r,tid,c,job=setup(tmp_path)
    c.data['fills'][0]['qty']=value
    status=job.start('binance',background=False)
    assert status['recovered']==0
    assert r.execute_query('SELECT net_pnl FROM trade_log')[0][0] is None


def test_repaired_utc_and_legacy_offset_rows_use_chronological_policy_order(tmp_path):
    from datetime import timedelta
    r,tid,c,job=setup(tmp_path,2)
    now=datetime.now(timezone.utc)
    newer=(now-timedelta(minutes=5)).isoformat()
    older=(now-timedelta(minutes=10)).astimezone(timezone(timedelta(hours=9))).isoformat()
    with sqlite3.connect(r.db_path) as db:
        db.execute('UPDATE trade_log SET exit_time=? WHERE id=?',(newer,tid))
        db.execute('UPDATE trade_log SET exit_time=? WHERE id!=?',(older,tid))
    rows=r.get_recent_trades(exchange='binance',days=45)
    assert [row['exit_time'] for row in rows]==[older,newer]
