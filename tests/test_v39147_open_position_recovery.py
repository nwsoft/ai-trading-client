"""Missing-close feedback: real local pipeline, synthetic read-only providers."""
import sqlite3
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_v39143_history_discovery import setup, fixtures, BASE
from test_v39143_record_recovery import make
from trading.risk_manager import RiskManager
from web_platform.application_services import ApplicationServices
from web_platform.headless_runtime import HeadlessTradingRuntime


def linked_open(tmp_path, venue='okx'):
    from datetime import datetime, timedelta, timezone
    r,tid,fill,c,job=make(tmp_path,venue)
    with sqlite3.connect(r.db_path) as db:
        db.execute('''UPDATE trade_log SET exit_time=NULL,exit_price=NULL,pnl=NULL,net_pnl=NULL,
            entry_time=? WHERE id=?''', ((datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),tid))
    r.save_exchange_execution_history(venue,[fill],reconcile=False)
    c.get_recovery_order_fills=lambda *args:[fill]
    if venue in {'kis','kiwoom','shinhan','mirae'}:
        c.get_recovery_order_fills=lambda symbol,order,epoch:[{
            **fill,'order':order,'id':'fill-entry' if order=='entry-1' else fill['id'],
            'side':'buy' if order=='entry-1' else 'sell',
            'price':100 if order=='entry-1' else 95,
        }]
    return r,tid,fill,c,job


@pytest.mark.parametrize('venue',['okx','bybit','bitget','upbit','bithumb','coinone','kis','kiwoom','shinhan','mirae'])
def test_linked_saved_close_restores_timestamp_then_revalidates_costs(tmp_path,venue):
    r,tid,fill,c,job=linked_open(tmp_path,venue)
    result=job.start(venue,background=False)
    assert result['recovered']==1 and result['remaining']==0, result
    row=r.execute_query('SELECT exit_time,net_pnl FROM trade_log WHERE id=?',(tid,))[0]
    saved=r.execute_query('SELECT executed_at FROM exchange_execution_log WHERE order_id=?',('exit-1',))[0][0]
    assert row[0]==saved  # preserve recorded precision; do not invent lost milliseconds
    assert row[1]==pytest.approx(-10.4 if venue in {'kis','kiwoom','shinhan','mirae'} else -10.2)
    assert not result['auto_started'] and not result['resume_authorized']


@pytest.mark.parametrize('fault,reason',[
    ('partial','partial_or_quantity_mismatch'),
    ('side','order_identity_mismatch'),
    ('symbol','order_identity_mismatch'),
    ('time','execution_time_outside_position'),
    ('unconfirmed','exchange_fill_not_found'),
])
def test_linked_close_rejects_incomplete_or_conflicting_saved_evidence(tmp_path,fault,reason):
    r,tid,fill,c,job=linked_open(tmp_path)
    changes={
        'partial':"quantity=1", 'side':"side='buy'", 'symbol':"symbol='OTHER'",
        'time':"executed_at='2000-01-01 00:00:00'",
        'unconfirmed':"confirmation_status='legacy_unverified'",
    }
    with sqlite3.connect(r.db_path) as db:
        db.execute('UPDATE exchange_execution_log SET '+changes[fault])
    before=r.execute_query('SELECT * FROM trade_log')
    assert job.start('okx',background=False)['reasons']=={reason:1}
    assert r.execute_query('SELECT * FROM trade_log')==before


def test_linked_close_cost_failure_is_not_zero_or_verified(tmp_path):
    r,tid,fill,c,job=linked_open(tmp_path)
    c.get_recovery_order_fills=lambda *args:[{**fill,'fee':{'cost':None}}]
    result=job.start('okx',background=False)
    assert result['remaining']==1 and result['recovered']==0
    row=r.execute_query('SELECT exit_time,net_pnl,pnl FROM trade_log')[0]
    assert row[0] is not None and row[1:]==(None,None)
    c.get_recovery_order_fills=lambda *args:[fill]
    job.now=lambda:__import__('time').time()+31
    assert job.start('okx',background=False)['recovered']==1


def test_linked_close_cannot_consume_another_trades_order(tmp_path):
    r,tid,fill,c,job=linked_open(tmp_path)
    with sqlite3.connect(r.db_path) as db:
        db.row_factory=sqlite3.Row
        row=dict(db.execute('SELECT * FROM trade_log WHERE id=?',(tid,)).fetchone())
        row.pop('id');row['order_id']='other-entry'
        db.execute(f"INSERT INTO trade_log ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",list(row.values()))
    before=r.execute_query('SELECT * FROM trade_log')
    result=job.start('okx',background=False)
    assert result['reasons']=={'order_attribution_conflict':2}
    assert before==r.execute_query('SELECT * FROM trade_log')


def test_linked_close_restart_after_clock_commit_rechecks_costs_once(tmp_path):
    from trading.record_recovery import RecordRecovery
    from trading.record_recovery_adapters import RecoveryResolver
    r,tid,fill,c,job=linked_open(tmp_path)
    def interrupted(*args): raise RuntimeError('simulated_process_exit_after_clock_commit')
    c.get_recovery_order_fills=interrupted
    assert job.start('okx',background=False)['state']=='failed'
    assert r.execute_query('SELECT net_pnl FROM trade_log')[0][0] is None
    c.get_recovery_order_fills=lambda *args:[fill]
    resumed=RecordRecovery(r,RecoveryResolver(r,c,'okx'),delay=0,now=lambda:__import__('time').time()+31)
    assert resumed.start('okx',background=False)['recovered']==1
    before=r.execute_query('SELECT * FROM trade_log')
    resumed.now=lambda:__import__('time').time()+62
    assert resumed.start('okx',background=False)['total']==0
    assert before==r.execute_query('SELECT * FROM trade_log')


def test_linked_close_legacy_fee_default_cannot_certify_costs(tmp_path):
    r,tid,fill,c,job=linked_open(tmp_path)
    with sqlite3.connect(r.db_path) as db:
        db.execute('UPDATE exchange_execution_log SET fee=0')
    c.get_recovery_order_fills=lambda *args:[{**fill,'fee':None}]
    result=job.start('okx',background=False)
    assert result['remaining']==1 and result['recovered']==0
    assert r.execute_query('SELECT net_pnl,pnl FROM trade_log')[0]==(None,None)


def reopen(recorder, tid):
    with sqlite3.connect(recorder.db_path) as db:
        db.execute('UPDATE trade_log SET exit_time=NULL,exit_price=NULL,exit_order_id=NULL,pnl=NULL,net_pnl=NULL WHERE id=?', (tid,))


@pytest.mark.parametrize('partial', [False, True])
def test_confirmed_flat_missing_close_is_recovered_without_zero_or_now(tmp_path, partial):
    r, tid, client, job = setup(tmp_path, partial=partial)
    reopen(r, tid)
    client.get_positions_result = lambda: {'status':'success','positions':[]}
    risk = RiskManager(client, r)
    assert risk._managed_unrealized_pnl('binance') == (False, 0.0, '현재 포지션 없음 · 과거 관리 원장 청산 대조 필요')
    risk.daily_initial_balance=1000
    risk._get_live_equity_snapshot=lambda _: {'valid':True,'equity':1000}
    decision=risk.evaluate_daily_loss_limit('binance',execution_mode='live')
    assert decision.reason_code=='managed_position_reconciliation_required'
    runtime=SimpleNamespace(risk_manager=SimpleNamespace(evaluate_daily_loss_limit=lambda **kw:decision))
    with pytest.raises(RuntimeError,match='risk_data_unavailable:managed_position_reconciliation_required'):
        HeadlessTradingRuntime.start_trading_loop(runtime)
    result = job.start('binance', background=False)
    assert result['total'] == result['recovered'] == 1 and result['remaining'] == 0
    assert not result['auto_started'] and not result['resume_authorized']
    row = r.execute_query('SELECT exit_time,net_pnl FROM trade_log WHERE id=?', (tid,))[0]
    assert r._ledger_time_epoch(row[0]) == (BASE + (3000 if partial else 2000))/1000
    assert row[1] == pytest.approx(-10.3)
    assert risk._managed_unrealized_pnl('binance') == (True, 0.0, '')
    before = r.execute_query('SELECT * FROM trade_log')
    job.now = lambda: (BASE+86400000)/1000+31
    assert job.start('binance', background=False)['total'] == 0
    assert r.execute_query('SELECT * FROM trade_log') == before


@pytest.mark.parametrize('venue',['binance','okx','bybit','bitget'])
def test_actual_owned_open_position_is_verified_without_closing(tmp_path, venue):
    r,tid,fill,client,job = make(tmp_path,venue)
    reopen(r,tid)
    client.get_positions_result=lambda:{'status':'success','positions':[{'symbol':'BTCUSDT','side':'LONG','size':2,'unrealized_pnl':-1}]}
    before=r.execute_query('SELECT * FROM trade_log')
    result=job.start(venue,background=False)
    assert result['verified_open']==1 and result['remaining']==result['recovered']==0
    assert result['state']=='checked' and not result['unresolved_items']
    assert before==r.execute_query('SELECT * FROM trade_log')


def test_native_position_objects_and_many_rows_share_bounded_snapshot(tmp_path):
    r,tid,fill,c,job=make(tmp_path,count=40)
    with sqlite3.connect(r.db_path) as db:
        db.execute('UPDATE trade_log SET exit_time=NULL,exit_price=NULL,exit_order_id=NULL,pnl=NULL,net_pnl=NULL')
    c.get_positions_result=Mock(return_value={'status':'success','positions':[SimpleNamespace(symbol='BTCUSDT',side='LONG',size=80,unrealized_pnl=0)]})
    result=job.start('binance',background=False)
    assert result['verified_open']==40 and result['remaining']==0
    assert c.get_positions_result.call_count==1


def test_paper_and_unowned_open_rows_are_not_repaired(tmp_path):
    r,tid,c,job=setup(tmp_path)
    reopen(r,tid)
    with sqlite3.connect(r.db_path) as db:
        db.execute("UPDATE trade_log SET execution_mode='paper' WHERE id=?",(tid,))
    assert job.start('binance',background=False)['total']==0
    job.now=lambda:(BASE+86400000)/1000+31
    with sqlite3.connect(r.db_path) as db:
        db.execute("UPDATE trade_log SET execution_mode='live',position_owner='manual',reason='external' WHERE id=?",(tid,))
    assert job.start('binance',background=False)['total']==0
    assert not c.calls


@pytest.mark.parametrize('status',['error','timeout'])
def test_failed_snapshot_never_means_flat_and_never_closes(tmp_path,status):
    r,tid,c,job=setup(tmp_path)
    reopen(r,tid)
    c.get_positions_result=lambda:{'status':status,'positions':[]}
    before=r.execute_query('SELECT * FROM trade_log')
    result=job.start('binance',background=False)
    assert result['remaining']==1 and result['reasons']=={'provider_query_failed':1}
    assert before==r.execute_query('SELECT * FROM trade_log')
    assert not c.calls


def test_no_close_evidence_stays_unresolved_then_later_history_can_recover(tmp_path):
    r,tid,c,job=setup(tmp_path)
    reopen(r,tid)
    c.get_positions_result=lambda:{'status':'success','positions':[]}
    c.data={'fills':[],'orders':[],'algos':[],'income':[]}
    result=job.start('binance',background=False)
    assert result['remaining']==1 and result['state']=='needs_evidence'
    assert r.execute_query('SELECT exit_time,net_pnl FROM trade_log')[0]==(None,None)
    c.data=fixtures()
    job.now=lambda:(BASE+86400000)/1000+31
    assert job.start('binance',background=False)['recovered']==1


@pytest.mark.parametrize('venue',['okx','bybit','bitget','upbit','bithumb','coinone','kis','kiwoom','shinhan','mirae'])
def test_other_venues_do_not_silently_omit_missing_close(tmp_path,venue):
    r,tid,fill,c,job=make(tmp_path,venue)
    reopen(r,tid)
    result=job.start(venue,background=False)
    assert result['total']==result['remaining']==1
    assert result['state']=='needs_evidence'
    reason='provider_historical_evidence_unsupported' if venue in {'okx','bybit','bitget'} else 'recovery_credential_required'
    assert result['reasons']=={reason:1}  # fixture intentionally has no history API


def test_old_paused_job_expands_scope_without_losing_checkpoint(tmp_path):
    r,tid,c,job=setup(tmp_path)
    job.request_budget=1
    result=job.start('binance',background=False)
    with job._connect() as db:
        db.execute('UPDATE jobs SET scope_version=0')
        db.execute('DELETE FROM items')
    reopen(r,tid)
    job.request_budget=10000
    after=job.start('binance',background=False)
    assert result['job_id']==after['job_id'] and after['recovered']==1


def test_restart_after_close_commit_does_not_double_count_or_lose_progress(tmp_path):
    from trading.record_recovery import RecordRecovery
    from trading.record_recovery_adapters import RecoveryResolver
    r,tid,c,job=setup(tmp_path,partial=True)
    reopen(r,tid)
    original=job.resolver
    class InterruptedResolver:
        def __getattr__(self,name): return getattr(original,name)
        def __call__(self,venue,trade):
            result=original(venue,trade)
            if result=='': raise RuntimeError('simulated_restart_after_commit')
            return result
    job.resolver=InterruptedResolver()
    assert job.start('binance',background=False)['state']=='failed'
    baseline=r.execute_query('SELECT * FROM trade_log')
    restarted=RecordRecovery(r,RecoveryResolver(r,c,'binance'),now=lambda:(BASE+86400000)/1000+31,request_budget=10000,delay=0)
    result=restarted.start('binance',background=False)
    assert result['recovered']==1 and result['remaining']==0
    assert baseline==r.execute_query('SELECT * FROM trade_log')
    assert r.execute_query('SELECT SUM(net_pnl) FROM trade_log')[0][0]==pytest.approx(-10.3)


@pytest.mark.parametrize('failure',[None,'recovery_already_running','recovery_engine_not_ready'])
def test_start_refusal_requests_bounded_recovery_but_never_restarts(monkeypatch,failure):
    import web_platform.application_services as module
    import trading.notifications as notifications
    monkeypatch.setattr(module,'load_settings',lambda **kw:{'paper_trading':True})
    send=Mock();monkeypatch.setattr(notifications,'publish_notification',send)
    reason='risk_data_unavailable:managed_position_reconciliation_required'
    bridge=SimpleNamespace(execute=Mock(side_effect=RuntimeError(reason)),record_recovery=Mock(side_effect=RuntimeError(failure) if failure else None))
    service=SimpleNamespace(_accepting_runtime_commands=True,_lock=RLock(),_command_results={},refresh_membership_status=lambda **kw:{'active':True},runtime_bridge=bridge)
    with pytest.raises(RuntimeError,match=reason) as caught:
        ApplicationServices.execute_runtime_command(service,command_id='qa47-start-0000001',command='trading.start',payload={'source':'binance'})
    assert bridge.execute.call_count==1 and not send.called
    bridge.record_recovery.assert_called_once_with('binance',start=True)
    assert str(caught.value).endswith('recovery_unavailable') == (failure=='recovery_engine_not_ready')
