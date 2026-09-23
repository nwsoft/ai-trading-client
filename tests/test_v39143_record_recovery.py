"""Offline recovery contract. No provider credentials, orders or user DB writes."""
from types import SimpleNamespace
from datetime import datetime
from pathlib import Path
import json
import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from test_v39139_pnl_audit import setup_trade, VENUES
from trading.record_recovery import RecordRecovery, validate_fills
from trading.record_recovery_adapters import RecoveryResolver
from trading.profitability_validation import ProfitabilityValidator
from web_platform.gateway import create_gateway_app
from api.binance_client import BinanceClient


def make(tmp_path, venue='binance', count=1, **kwargs):
    recorder, tid, fill = setup_trade(tmp_path, venue, **kwargs)
    if count > 1:
        with sqlite3.connect(recorder.db_path) as db:
            db.row_factory = sqlite3.Row
            row = dict(db.execute('SELECT * FROM trade_log WHERE id=?', (tid,)).fetchone())
            row.pop('id')
            for i in range(1, count):
                row['order_id'], row['exit_order_id'] = f'entry-{i+1}', f'exit-{i+1}'
                db.execute(f"INSERT INTO trade_log ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", list(row.values()))
    def fetch(symbol, order, closed):
        return [{**fill, 'order': order, 'id': f'fill-{order}'}]
    client = SimpleNamespace(get_recovery_order_fills=fetch)
    resolver = RecoveryResolver(recorder, client, venue)
    recovery = RecordRecovery(recorder, resolver, delay=0, request_budget=1000)
    return recorder, tid, fill, client, recovery


@pytest.mark.parametrize('count', [1, 40, 301])
def test_recovers_every_target_not_just_tail_and_preserves_backup(tmp_path, count):
    r, tid, fill, client, job = make(tmp_path, count=count)
    before = r.execute_query('SELECT count(*),sum(pnl) FROM trade_log')[0]
    result = job.start('binance', background=False)
    assert result['state'] == 'checked'
    assert (result['total'], result['recovered'], result['remaining']) == (count, count, 0)
    assert result['auto_started'] is False and result['resume_authorized'] is False
    assert r.execute_query('SELECT count(*),sum(net_pnl) FROM trade_log')[0] == (count, pytest.approx(-10.2*count))
    with sqlite3.connect(tmp_path/'backups/record_recovery/binance-before.sqlite3') as backup:
        assert backup.execute('SELECT count(*),sum(pnl) FROM trade_log').fetchone() == before
    assert RecordRecovery.read_status(r.db_path, 'binance')['recovered'] == count
    with pytest.raises(RuntimeError, match='cooldown'):
        job.start('binance', background=False)


@pytest.mark.parametrize('venue', VENUES)
def test_common_contract_isolates_paper_and_venue(tmp_path, venue):
    r, tid, fill, client, job = make(tmp_path, venue, mode='paper')
    assert job.start(venue, background=False)['total'] == 0
    assert r.execute_query('SELECT pnl FROM trade_log WHERE id=?', (tid,))[0][0] == 20


@pytest.mark.parametrize('venue', VENUES)
def test_complete_provider_evidence_common_ledger_contract(tmp_path, venue):
    r, tid, fill, client, job = make(tmp_path, venue)
    if venue in {'kis', 'kiwoom', 'shinhan', 'mirae'}:
        # A broker close requires independent entry evidence as well as the
        # sell. Reusing a sell fill as a buy is not complete provider evidence.
        client.get_recovery_order_fills = lambda symbol, order, epoch: [{
            **fill, 'order': order, 'id': f'fill-{order}',
            'side': 'buy' if order == 'entry-1' else 'sell',
            'price': 100 if order == 'entry-1' else fill['price'],
        }]
    assert job.start(venue, background=False)['recovered'] == 1
    # Synthetic contract proof is not a claim that every production adapter
    # exposes historical fills, provider gross PnL, fees or taxes.


def test_missing_id_cannot_adopt_same_time_manual_trade_or_unlock(tmp_path):
    r, tid, fill, client, job = make(tmp_path, exit_id=None)
    client.get_recovery_order_fills = lambda *args: pytest.fail('must not query arbitrary order')
    result = job.start('binance', background=False)
    assert result['state'] == 'needs_evidence'
    assert result['reasons'] == {'missing_exit_order_evidence': 1}
    assert r.execute_query('SELECT exit_order_id,pnl FROM trade_log WHERE id=?', (tid,))[0] == (None, 20)
    assert 'pnl_reconciliation_required' in ProfitabilityValidator().evaluate_strategy(
        recent_trades=[{'performance_evidence_ready': False}])['reasons']


def test_resume_budget_and_restart_does_not_repeat_processed_rows(tmp_path):
    r, tid, fill, client, job = make(tmp_path, count=40)
    job.request_budget = 7
    assert job.start('binance', background=False)['processed'] == 7
    restarted = RecordRecovery(r, RecoveryResolver(r, client, 'binance'), request_budget=100, delay=0)
    result = restarted.start('binance', background=False)
    assert result['state'] == 'checked' and result['recovered'] == 40
    assert r.execute_query('SELECT count(*) FROM exchange_execution_log')[0][0] == 40


def test_error_retries_same_record_without_reset_or_exposing_secret(tmp_path):
    r, tid, fill, client, job = make(tmp_path)
    original = client.get_recovery_order_fills
    def fail(*args): raise TimeoutError('secret-key-fixture')
    client.get_recovery_order_fills = fail
    result = job.start('binance', background=False)
    assert result['state'] == 'failed' and result['processed'] == 0
    assert 'secret-key' not in json.dumps(result)
    job.now = lambda: __import__('time').time()+31
    client.get_recovery_order_fills = original
    assert job.start('binance', background=False)['recovered'] == 1


@pytest.mark.parametrize('invalid', ['fee', 'partial', 'duplicate', 'symbol', 'side', 'time', 'nan', 'pending'])
def test_bad_fill_cannot_change_ledger(tmp_path, invalid):
    r, tid, fill, client, job = make(tmp_path)
    rows = [fill]
    if invalid == 'fee': fill.pop('fee')
    if invalid == 'partial': fill['amount'] = 1
    if invalid == 'duplicate': rows.append(dict(fill))
    if invalid == 'symbol': fill['symbol'] = 'OTHERUSDT'
    if invalid == 'side': fill['side'] = 'buy'
    if invalid == 'time': fill.pop('timestamp')
    if invalid == 'nan': fill['price'] = float('nan')
    if invalid == 'pending': fill['status'] = 'new'
    client.get_recovery_order_fills = lambda *args: rows
    assert job.start('binance', background=False)['recovered'] == 0
    assert r.execute_query('SELECT pnl FROM trade_log WHERE id=?', (tid,))[0][0] == 20


def test_single_flight_across_instances_and_separate_accounts(tmp_path):
    r, tid, fill, client, job = make(tmp_path)
    other = RecordRecovery(r, lambda *_: '', delay=0)
    job.lock.acquire()
    try:
        with pytest.raises(RuntimeError, match='already_running'):
            other.start('binance', background=False)
    finally: job.lock.release()
    second = tmp_path/'second'; second.mkdir()
    r2, _, _, _, job2 = make(second)
    assert job2.start('binance', background=False)['recovered'] == 1
    assert job.status('binance')['state'] == 'idle'


@pytest.mark.parametrize('venue', ['kis','kiwoom','shinhan','mirae'])
def test_today_only_broker_history_not_claimed_as_historical_recovery(tmp_path, venue):
    r, tid, fill, client, job = make(tmp_path, venue)
    job.resolver = RecoveryResolver(r, SimpleNamespace(get_trade_history=lambda **_: pytest.fail('today-only call')), venue)
    assert job.start(venue, background=False)['reasons'] == {'broker_historical_evidence_unsupported': 1}


def test_binance_recovery_uses_historical_window_and_propagates_error():
    queries = []
    client = object.__new__(BinanceClient)
    client._has_api_keys = lambda: True
    client.get_synced_timestamp = lambda: 1800000000000
    client.config = SimpleNamespace(recv_window=5000)
    client.client = SimpleNamespace(futures_account_trades=lambda **kw: queries.append(kw) or [])
    client.get_recovery_order_fills('BTCUSDT','123',1700000000)
    assert queries[0]['orderId'] == 123 and queries[0]['symbol'] == 'BTCUSDT'
    assert queries[0]['endTime']-queries[0]['startTime'] <= 7*86400*1000
    assert queries[0]['startTime'] == (1700000000-86400)*1000
    def fail(**kw): raise TimeoutError()
    client.client.futures_account_trades = fail
    with pytest.raises(TimeoutError): client.get_recovery_order_fills('BTCUSDT','123',1700000000)


def test_missing_entry_fee_recovered_from_unique_entry_order_not_total_fees(tmp_path):
    r, tid, fill, client, job = make(tmp_path)
    with sqlite3.connect(r.db_path) as db:
        db.execute('UPDATE trade_log SET entry_fee=NULL,fees=99 WHERE id=?', (tid,))
    def fetch(symbol, oid, closed):
        return [{**fill, 'order': oid, 'id': 'fill-'+oid,
                 'side': 'buy' if oid == 'entry-1' else 'sell'}]
    client.get_recovery_order_fills = fetch
    assert job.start('binance', background=False)['recovered'] == 1
    assert r.execute_query('SELECT entry_fee,net_pnl FROM trade_log WHERE id=?', (tid,))[0] == (0.2, pytest.approx(-10.4))


def test_recorder_never_uses_legacy_total_fee_as_entry_fee(tmp_path):
    r, tid, fill, client, job = make(tmp_path)
    with sqlite3.connect(r.db_path) as db:
        db.execute('UPDATE trade_log SET entry_fee=NULL,fees=99 WHERE id=?', (tid,))
    r.save_exchange_execution_history('binance', [fill])
    assert r.execute_query('SELECT gross_pnl,net_pnl,reconciliation_status FROM trade_log WHERE id=?', (tid,))[0] == (
        -10, None, 'entry_fee_evidence_missing')


def test_ambiguous_entry_fee_allocation_does_not_double_charge(tmp_path):
    r, tid, fill, client, job = make(tmp_path, count=2)
    with sqlite3.connect(r.db_path) as db:
        db.execute("UPDATE trade_log SET entry_fee=NULL,order_id='entry-1'")
    result = job.start('binance', background=False)
    assert result['reasons'] == {'entry_order_allocation_required': 2}
    assert result['recovered'] == 0


def test_gateway_requires_token_and_intent():
    calls = []
    service = SimpleNamespace(runtime_snapshot=lambda: {}, runtime_bridge=SimpleNamespace(
        record_recovery=lambda source, start=False: calls.append((source,start)) or {'state':'running'}))
    app = create_gateway_app(token='x'*40, application_services=service)
    with TestClient(app) as client:
        path = '/api/v1/maintenance/trade-records'
        assert client.post(path, json={'source':'binance'}).status_code == 401
        auth = {'Authorization':'Bearer '+'x'*40}
        assert client.post(path, headers=auth, json={'source':'binance'}).status_code == 428
        assert client.get(path+'?source=binance', headers=auth).status_code == 200
        auth['X-NoahAI-Intent'] = 'confirmed'
        assert client.post(path, headers=auth, json={'source':'binance'}).status_code == 200
        assert client.post(path, headers=auth, json={'source':'binance','start_live':True}).status_code == 400
        assert calls == [('binance',False),('binance',True)]


def test_crash_after_ledger_commit_before_checkpoint_is_idempotent(tmp_path):
    r, tid, fill, client, job = make(tmp_path)
    resolver = job.resolver
    def after_commit(venue, trade):
        resolver(venue, trade)
        raise RuntimeError('simulated interruption after commit')
    job.resolver = after_commit
    assert job.start('binance', background=False)['state'] == 'failed'
    job.now = lambda: __import__('time').time()+31
    job.resolver = lambda *_: pytest.fail('verified row must not be fetched again')
    assert job.start('binance', background=False)['recovered'] == 1
    assert r.execute_query('SELECT count(*) FROM exchange_execution_log')[0][0] == 1


def test_failed_backup_prevents_any_provider_request(tmp_path, monkeypatch):
    r, tid, fill, client, job = make(tmp_path)
    job.resolver = lambda *_: pytest.fail('backup must succeed before recovery')
    def fail(*args, **kwargs): raise OSError('backup unavailable')
    monkeypatch.setattr(Path, 'mkdir', fail)
    assert job.start('binance', background=False)['state'] == 'failed'
    assert r.execute_query('SELECT pnl FROM trade_log WHERE id=?', (tid,))[0][0] == 20


def test_replaced_trade_id_is_not_repaired_under_old_job_identity(tmp_path):
    r, tid, fill, client, job = make(tmp_path)
    prepare = job._prepare
    def replace(venue, job_id):
        prepare(venue, job_id)
        with sqlite3.connect(r.db_path) as db:
            db.execute("UPDATE trade_log SET symbol='OTHERUSDT' WHERE id=?", (tid,))
    job._prepare = replace
    job.resolver = lambda *_: pytest.fail('changed record must not be queried')
    assert job.start('binance', background=False)['reasons'] == {'record_identity_changed': 1}


def test_new_run_preserves_prior_audit_and_first_backup(tmp_path):
    r, tid, fill, client, job = make(tmp_path)
    first = job.start('binance', background=False)
    job.now = lambda: __import__('time').time()+31
    assert job.start('binance', background=False)['total'] == 0
    with job._connect() as db:
        assert db.execute('SELECT COUNT(*) FROM items WHERE job_id=?', (first['job_id'],)).fetchone()[0] == 1
    with sqlite3.connect(tmp_path/'backups/record_recovery/binance-before.sqlite3') as db:
        assert db.execute('SELECT pnl FROM trade_log WHERE id=?', (tid,)).fetchone()[0] == 20


def test_ordinary_underperformance_does_not_suggest_record_repair():
    from trading.record_recovery import recovery_hint
    assert '점검·복구' not in recovery_hint({'reasons':['min_win_rate']})
    assert '점검·복구' in recovery_hint({'reasons':['pnl_reconciliation_required']})


def test_bridge_never_bootstraps_ai_or_trade_workers_for_maintenance():
    from web_platform.runtime_bridge import HeadlessRuntimeBridge
    bridge = HeadlessRuntimeBridge(account='fixture', factory=lambda *_: pytest.fail('must not bootstrap runtime'))
    bridge._settings = lambda: {'binance_api_key':'fixture-key','binance_secret_key':'fixture-secret'}
    with pytest.raises(RuntimeError, match='engine_not_ready'):
        bridge.record_recovery('binance', start=True)
    assert bridge._app is None


def test_real_bridge_runs_async_local_task_without_any_trading_commands(tmp_path, monkeypatch):
    import time
    from web_platform.runtime_bridge import HeadlessRuntimeBridge
    r, tid, fill, client, job = make(tmp_path)
    bridge = HeadlessRuntimeBridge(account='fixture')
    bridge._settings = lambda: {'binance_api_key':'fixture-key','binance_secret_key':'fixture-secret'}
    bridge._app = SimpleNamespace(recorder=r, exchange_manager=SimpleNamespace(get_exchange_client=lambda _:client))
    monkeypatch.setattr('path_utils.get_db_file_path', lambda: str(r.db_path))
    assert bridge.record_recovery('binance')['state'] == 'idle'
    bridge.record_recovery('binance', start=True)
    deadline = time.monotonic()+3
    while time.monotonic() < deadline:
        result = bridge.record_recovery('binance')
        if result['state'] != 'running': break
        time.sleep(.02)
    assert result['state'] == 'checked' and result['recovered'] == 1
    # Restart status reads the durable journal without touching any provider.
    restarted = HeadlessRuntimeBridge(account='fixture', factory=lambda *_: pytest.fail('status initialized engine'))
    assert restarted.record_recovery('binance')['recovered'] == 1
    with pytest.raises(RuntimeError, match='account_change_requires_restart'):
        bridge.set_account('other')
