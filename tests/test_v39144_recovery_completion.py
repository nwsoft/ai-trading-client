"""Incident-shaped provider replay, never customer credentials or live orders."""
import json
import sqlite3
from types import SimpleNamespace

import pytest

from test_v39143_history_discovery import setup, BASE, fixtures
from trading.record_recovery import RecordRecovery
from trading.record_recovery_adapters import RecoveryResolver
from trading.pnl_evidence import performance_evidence
from trading.profitability_validation import ProfitabilityValidator
from web_platform.query_services import AccountQueryService


def exact_queries(client):
    def fetch(symbol,oid,closed):
        client.calls.append(('exact',symbol,oid))
        return [{**r,'order':str(r['orderId']),'quantity':r['qty'],
                 'commission_asset':r['commissionAsset'],'realized_pnl':r['realizedPnl']}
                for r in client.data['fills'] if str(r['orderId'])==oid]
    client.get_recovery_order_fills=fetch


@pytest.mark.parametrize('count',[1,10,40,301])
def test_existing_partial_close_id_recovers_full_cycle_once(tmp_path,count):
    r,tid,c,job=setup(tmp_path,count,partial=True)
    exact_queries(c)
    with sqlite3.connect(r.db_path) as db:
        db.execute('UPDATE trade_log SET exit_order_id=CAST(CAST(order_id AS INTEGER)+1 AS TEXT)')
    result=job.start('binance',background=False)
    assert result['recovered']==count and result['remaining']==0
    assert result['history_pages'].get('pending',0)==0
    stats=AccountQueryService(r.db_path).trading_statistics(source='binance',asset_class='crypto',period='all')
    assert stats['reconciled_closed_count']==count and stats['execution_count']==3*count
    assert stats['pnl_by_currency']['USDT']==pytest.approx(-10.3*count)
    with sqlite3.connect(r.db_path) as db:
        db.row_factory=sqlite3.Row
        rows=[{**dict(row),**performance_evidence(dict(row))} for row in db.execute('SELECT * FROM trade_log')]
    assert 'pnl_reconciliation_required' not in ProfitabilityValidator().evaluate_strategy(rows).get('reasons',[])
    before=r.execute_query('SELECT * FROM trade_log')
    job.now=lambda:(BASE+86400000)/1000+31
    assert job.start('binance',background=False)['total']==0
    assert job.status('binance')['history_pages']=={}
    assert r.execute_query('SELECT * FROM trade_log')==before


def test_provider_quantity_corrected_only_with_complete_owned_cycle(tmp_path):
    r,tid,c,job=setup(tmp_path,partial=True);exact_queries(c)
    with sqlite3.connect(r.db_path) as db:
        db.execute("UPDATE trade_log SET quantity=3,entry_price=101,exit_order_id='101'")
    assert job.start('binance',background=False)['recovered']==1
    assert r.execute_query('SELECT quantity,entry_price,net_pnl FROM trade_log')[0]==(2,100,pytest.approx(-10.3))
    before,after=r.execute_query('SELECT before_json,after_json FROM recovery_cycle_repairs')[0]
    assert json.loads(before)['quantity']==3 and json.loads(after)['quantity']==2
    with sqlite3.connect(job.journal) as db:
        db.execute("UPDATE items SET state='pending'")
        db.execute("UPDATE jobs SET state='paused'")
    restarted=RecordRecovery(r,RecoveryResolver(r,c,'binance'),now=job.now,delay=0)
    assert restarted.start('binance',background=False)['recovered']==1
    assert r.execute_query('SELECT count(*) FROM recovery_cycle_claims')[0][0]==3


def test_shared_entry_never_corrects_quantity_by_guess(tmp_path):
    r,tid,c,job=setup(tmp_path,2,partial=True);exact_queries(c)
    with sqlite3.connect(r.db_path) as db:
        db.execute("UPDATE trade_log SET order_id='100',quantity=3,exit_order_id='101'")
    assert job.start('binance',background=False)['recovered']==0
    assert r.execute_query('SELECT quantity,net_pnl FROM trade_log')==[(3,None),(3,None)]


def test_terminal_partial_cancel_with_all_actual_fills_is_recoverable(tmp_path):
    r,tid,c,job=setup(tmp_path,partial=True)
    c.data['orders'][1]['status']='CANCELED'
    assert job.start('binance',background=False)['recovered']==1


def test_status_does_not_count_812_unrelated_old_windows(tmp_path):
    r,tid,c,job=setup(tmp_path)
    job.request_budget=1
    status=job.start('binance',background=False)
    history=job.resolver.history
    with history.db() as db:
        db.executemany('INSERT INTO recovery_history_pages VALUES(?,?,?,?,?,?,NULL)',
                       [(history.scope,'OLDUSDT','fills',i,i,'pending') for i in range(812)])
    assert job.status('binance')['history_pages']==status['history_pages']
    job.request_budget=1000
    assert job.start('binance',background=False)['recovered']==1
    assert job.status('binance')['history_pages'].get('pending',0)==0


def test_delayed_income_refreshes_only_missing_kind_not_all_windows(tmp_path):
    r,tid,c,job=setup(tmp_path)
    income=c.data['income'];c.data['income']=[]
    assert job.start('binance',background=False)['remaining']==1
    before={kind:sum(call[0]==kind for call in c.calls) for kind in c.data}
    c.data['income']=income;job.now=lambda:(BASE+86400000)/1000+31
    assert job.start('binance',background=False)['recovered']==1
    for kind in ('fills','orders','algos'):
        assert sum(call[0]==kind for call in c.calls)==before[kind]
    assert sum(call[0]=='income' for call in c.calls)==before['income']+1


def drive_background(job):
    status=job.status('binance')
    assert job.lock.acquire(blocking=False)
    job._background('binance',status['job_id'])
    return job.status('binance')


def test_background_continues_without_browser_requests(tmp_path):
    r,tid,c,job=setup(tmp_path)
    job.request_budget=1
    assert job.start('binance',background=False)['state']=='paused'
    waits=[]
    job.cancelled=SimpleNamespace(is_set=lambda:False,wait=lambda delay:waits.append(delay) or False)
    assert drive_background(job)['recovered']==1
    assert waits and all(delay==2 for delay in waits)
    assert sum(call[0]=='fills' for call in c.calls)==1


def test_background_delayed_settlement_retries_then_recovers(tmp_path):
    r,tid,c,job=setup(tmp_path)
    income=c.data['income'];c.data['income']=[]
    job.start('binance',background=False)
    def wait(delay):
        assert delay==5
        c.data['income']=income
        return False
    job.cancelled=SimpleNamespace(is_set=lambda:False,wait=wait)
    status=drive_background(job)
    assert status['recovered']==1 and status['retry_count']==1


def test_background_no_infinite_retry_of_missing_settlement(tmp_path):
    r,tid,c,job=setup(tmp_path);c.data['income']=[]
    job.start('binance',background=False)
    waits=[]
    job.cancelled=SimpleNamespace(is_set=lambda:False,wait=lambda delay:waits.append(delay) or False)
    result=drive_background(job)
    assert result['state']=='needs_evidence' and result['recovered']==0
    assert waits==[5,15] and result['retry_count']==2
    assert r.execute_query('SELECT net_pnl FROM trade_log')[0][0] is None


def test_background_cancel_preserves_checkpoint_and_unlocks(tmp_path):
    r,tid,c,job=setup(tmp_path);job.request_budget=1
    job.start('binance',background=False)
    def stop(delay):
        job.cancelled.set();return True
    job.cancelled.wait=stop
    assert drive_background(job)['state']=='paused'
    restarted=RecordRecovery(r,RecoveryResolver(r,c,'binance'),now=job.now,delay=0,request_budget=1000)
    assert restarted.start('binance',background=False)['recovered']==1


@pytest.mark.parametrize('transient',[True,False])
def test_transient_failure_retries_but_bad_credentials_do_not(tmp_path,transient):
    r,tid,c,job=setup(tmp_path)
    original=c.get_recovery_history_page
    def fail(*args):
        if transient: raise TimeoutError('secret must not reach UI')
        raise ValueError('credentials invalid secret')
    c.get_recovery_history_page=fail
    job.start('binance',background=False)
    waits=[]
    def wait(delay):
        waits.append(delay);c.get_recovery_history_page=original;return False
    job.cancelled=SimpleNamespace(is_set=lambda:False,wait=wait)
    result=drive_background(job)
    assert 'secret' not in json.dumps(result)
    if transient: assert result['recovered']==1 and waits==[5]
    else: assert result['state']=='failed' and not waits


def test_interrupted_retry_is_resumable_after_process_exit(tmp_path):
    r,tid,c,job=setup(tmp_path);job.request_budget=1
    job.start('binance',background=False)
    with sqlite3.connect(job.journal) as db:
        db.execute("UPDATE jobs SET state='retry_wait',lease_until=0")
    assert job.status('binance')['state']=='interrupted'
    job.request_budget=1000
    assert job.start('binance',background=False)['recovered']==1


def test_v43_split_cache_migrates_without_redownloading_completed_fills(tmp_path):
    r,tid,c,job=setup(tmp_path)
    job.request_budget=1
    job.start('binance',background=False)
    history=job.resolver.history
    with history.db() as db:
        parent=db.execute("SELECT * FROM recovery_history_pages WHERE kind='fills'").fetchone()
        middle=(parent['start']+parent['end'])//2
        db.execute("UPDATE recovery_history_pages SET state='split',rows=NULL WHERE kind='fills'")
        for left,right in ((parent['start'],middle),(middle+1,parent['end'])):
            rows=[row for row in c.data['fills'] if left<=row['time']<=right]
            db.execute('INSERT INTO recovery_history_pages VALUES(?,?,?,?,?,?,?)',
                       (history.scope,'BTCUSDT','fills',left,right,'complete',json.dumps(rows)))
        db.execute('DELETE FROM recovery_history_session_pages')
        db.execute('DELETE FROM recovery_history_job_sessions')
    before=sum(call[0]=='fills' for call in c.calls)
    resumed=RecordRecovery(r,RecoveryResolver(r,c,'binance'),now=job.now,delay=0)
    assert resumed.start('binance',background=False)['recovered']==1
    assert sum(call[0]=='fills' for call in c.calls)==before
    assert resumed.status('binance')['history_pages']=={'complete':5}


def test_concurrent_entry_price_change_is_not_overwritten(tmp_path,monkeypatch):
    r,tid,c,job=setup(tmp_path)
    original=r.save_exchange_execution_history
    def concurrent_change(*args,**kwargs):
        value=original(*args,**kwargs)
        with sqlite3.connect(r.db_path) as db:
            db.execute('UPDATE trade_log SET entry_price=123 WHERE id=?',(tid,))
        return value
    monkeypatch.setattr(r,'save_exchange_execution_history',concurrent_change)
    result=job.start('binance',background=False)
    assert result['recovered']==0 and result['reasons']=={'record_identity_changed':1}
    assert r.execute_query('SELECT entry_price,net_pnl FROM trade_log')==[(123,None)]
