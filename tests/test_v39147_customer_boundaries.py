"""Offline replay: no orders, credentials or writes to customer originals."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from threading import Event, RLock
from types import SimpleNamespace
from unittest.mock import Mock
import json
import sqlite3
import pytest

from trading.binance_history_recovery import reconstruct_uniform_close_lot, BinanceHistoryRecovery
from trading.pnl_evidence import performance_evidence
from test_v39143_history_discovery import setup, BASE


def mixed(tmp_path):
    r, tid, c, job = setup(tmp_path)
    opening, close = c.data['fills']
    other = {**opening, 'id':999, 'orderId':'99', 'price':'101', 'time':BASE+500}
    close.update(qty='4', realizedPnl='-22', commission='.2')
    c.data['fills'].insert(0, other)
    c.data['orders'][1]['executedQty']='4'
    c.data['orders'].append({**c.data['orders'][0], 'orderId':'99','time':BASE+500})
    c.data['income'][0]['income']='-22'
    return r, tid, c, job


def test_uniform_shared_close_recovers_only_owned_lot_and_is_idempotent(tmp_path):
    r, tid, c, job = mixed(tmp_path)
    result = job.start('binance', background=False)
    assert result['recovered'] == 1, result
    row = r.execute_query('SELECT quantity,gross_pnl,net_pnl,exit_order_id,pnl_source FROM trade_log')[0]
    assert row == (2, -10, pytest.approx(-10.3), None, 'exchange_uniform_close_lot')
    assert r.execute_query('SELECT COUNT(*) FROM trade_log')[0][0] == 1
    assert r.execute_query('SELECT quantity FROM recovery_exit_lot_allocations')[0][0] == '2'
    assert r.execute_query('SELECT COUNT(*) FROM recovery_cycle_claims')[0][0] == 1
    from web_platform.query_services import AccountQueryService
    statistics=AccountQueryService(r.db_path).trading_statistics(asset_class='crypto',source='binance',period='all')
    assert statistics['groups'][0]['rows'][0]['gross_pnl']==-10
    assert statistics['groups'][0]['rows'][0]['total_pnl']==pytest.approx(-10.3)
    r.link_unresolved_trade_closes_with_executions('binance')
    assert r.execute_query('SELECT reconciliation_status FROM trade_log')[0][0] == 'exact_fill_price_no_provider_pnl'
    job.now = lambda:(BASE+86400000)/1000+31
    assert job.start('binance', background=False)['remaining'] == 0
    assert r.execute_query('SELECT quantity,gross_pnl,net_pnl,exit_order_id,pnl_source FROM trade_log')[0] == row


def test_two_owned_lots_share_close_without_double_counting(tmp_path):
    r, tid, c, job = mixed(tmp_path)
    with sqlite3.connect(r.db_path) as db:
        db.row_factory=sqlite3.Row
        row=dict(db.execute('SELECT * FROM trade_log WHERE id=?',(tid,)).fetchone()); row.pop('id')
        row.update(order_id='99',entry_price=101)
        db.execute('INSERT INTO trade_log ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
    result=job.start('binance',background=False)
    assert result['recovered']==2, result
    assert r.execute_query('SELECT SUM(gross_pnl), SUM(net_pnl) FROM trade_log')[0] == (-22,pytest.approx(-22.6))
    assert sum(Decimal(r[0]) for r in r.execute_query('SELECT quantity FROM recovery_exit_lot_allocations'))==4


@pytest.mark.parametrize('change', ['gross','quantity','mixed_prices','missing_order','reentry','currency'])
def test_shared_close_does_not_guess_allocation(tmp_path, change):
    r, tid, c, job = mixed(tmp_path)
    if change == 'gross': c.data['fills'][-1]['realizedPnl']='100'
    if change == 'quantity': c.data['fills'][1]['qty']='1'
    if change == 'missing_order': c.data['orders'].pop()
    if change == 'currency': c.data['fills'][0]['commissionAsset']='BNB'
    if change == 'reentry': c.data['fills'][0]['time']=BASE+2500
    if change == 'mixed_prices':
        close=c.data['fills'][-1]; close['qty']='2'
        c.data['fills'].append({**close,'id':5555,'price':'94'})
    result=job.start('binance', background=False)
    assert result['recovered']==0
    assert r.execute_query('SELECT net_pnl FROM trade_log')[0][0] is None


def test_customer_cached_cycle_proof_without_api_or_original_writes():
    candidates=list(Path('data/260924_Teayu').rglob('trading.db'))
    if not candidates: pytest.skip('private read-only customer fixture absent')
    with sqlite3.connect(candidates[0].resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        trade=dict(db.execute('SELECT * FROM trade_log WHERE id=57909').fetchone())
        session=db.execute("SELECT * FROM recovery_history_sessions WHERE symbol='AVAXUSDT' AND verified=1 ORDER BY start LIMIT 1").fetchone()
        data={}
        for kind in ('fills','orders'):
            unique={}
            for page in db.execute("SELECT rows FROM recovery_history_pages WHERE scope=? AND symbol=? AND kind=? AND state='complete' AND start>=? AND end<=?",(session['scope'],trade['symbol'],kind,session['start'],session['end'])):
                for row in json.loads(page[0]): unique[str(row['id' if kind=='fills' else 'orderId'])]=row
            data[kind]=list(unique.values())
    proof, reason=reconstruct_uniform_close_lot(trade,data['fills'],data['orders'],json.loads(session['anchor']),session['start'],session['end'])
    assert reason=='', reason
    assert proof['quantity']==Decimal('6') and proof['total_quantity']==Decimal('12')
    assert proof['lot_gross']==Decimal('1.709')


def test_monitor_is_async_unique_and_retains_ownership_until_exit():
    from trading.trader import Trader
    trader=Trader.__new__(Trader)
    trader._monitoring_lock=RLock(); trader.monitoring_flags={}; trader.monitoring_threads={}
    trader._pending_monitoring={}; trader.active_positions={}
    entered, release = Event(), Event()
    def blocking(symbol, position, *, stop_event):
        entered.set(); release.wait(2)
    trader.start_realtime_monitoring=blocking
    position=object()
    assert trader._start_monitoring('BTCUSDT',position)
    assert entered.wait(1)
    worker=trader.monitoring_threads['BTCUSDT']
    assert not trader._start_monitoring('BTCUSDT',position)
    trader.monitoring_flags['BTCUSDT'].set()
    assert not trader._start_monitoring('BTCUSDT',position)
    release.set(); worker.join(2)
    assert not trader.monitoring_threads and not trader.monitoring_flags


def test_monitor_replacement_hands_off_only_after_old_worker_finishes():
    from trading.trader import Trader
    trader=Trader.__new__(Trader)
    trader._monitoring_lock=RLock(); trader.monitoring_flags={}; trader.monitoring_threads={}; trader._pending_monitoring={}
    first, second=object(),object()
    trader.active_positions={'BTCUSDT':first}
    old_entered, old_release, new_entered, new_release=Event(),Event(),Event(),Event()
    def run(symbol, position, *, stop_event):
        if position is first: old_entered.set(); old_release.wait(2)
        else: new_entered.set(); new_release.wait(2)
    trader.start_realtime_monitoring=run
    trader._start_monitoring('BTCUSDT',first); assert old_entered.wait(1)
    old_worker=trader.monitoring_threads['BTCUSDT']
    trader.active_positions['BTCUSDT']=second
    assert not trader._start_monitoring('BTCUSDT',second)
    assert not new_entered.is_set()
    old_release.set(); assert new_entered.wait(1)
    new_worker=trader.monitoring_threads['BTCUSDT']
    assert new_worker is not old_worker
    new_release.set(); old_worker.join(2); new_worker.join(2)
    assert not trader.monitoring_threads


def test_busy_recovery_stays_retryable_and_pending(tmp_path):
    from test_v39143_record_recovery import make
    r, tid, fill, client, job=make(tmp_path)
    client.get_recovery_order_fills=Mock(side_effect=sqlite3.OperationalError('database is locked: private data'))
    state=job.start('binance',background=False)
    assert state['retryable'] and state['error']=='storage_busy_retryable'
    assert state['remaining']==1


def test_fill_storage_reconciles_only_affected_orders(tmp_path, monkeypatch):
    from test_v39143_record_recovery import make
    r,tid,fill,client,job=make(tmp_path,count=80)
    calls=[]
    original=r.reconcile_trade_log_with_executions
    def spy(venue, *, trade_ids=None):
        calls.append(trade_ids)
        return original(venue,trade_ids=trade_ids)
    monkeypatch.setattr(r,'reconcile_trade_log_with_executions',spy)
    r.save_exchange_execution_history('binance',[fill])
    assert calls==[[tid]]


def test_reconcile_releases_write_admission_between_small_batches(tmp_path, monkeypatch):
    from test_v39143_record_recovery import make
    from contextlib import contextmanager
    r,tid,fill,client,job=make(tmp_path,count=80)
    original=r._write_connection; batches=[]
    @contextmanager
    def tracked(*args, **kwargs):
        if kwargs.get('operation')=='reconcile_trade_log_with_executions': batches.append(1)
        with original(*args, **kwargs) as db: yield db
    monkeypatch.setattr(r,'_write_connection',tracked)
    r.reconcile_trade_log_with_executions('binance')
    assert len(batches)==4


def test_structured_source_decimal_condition_compiles_without_inline_entry_keyword():
    from trading.strategy_source_ingestor import StrategySourceIngestor
    result=StrategySourceIngestor().analyze('ENTRY:\n- rsi <= 30.5\nEXIT:\n- rsi >= 55.5\nRISK:\n손절 1%, 익절 2%, 자산 5%. 횡보장 15분봉.',kind='text')
    assert result['rules']['executable_entry']['all']==[{'field':'rsi','operator':'lte','value':30.5}]
    assert result['rules']['executable_exit']['all']==[{'field':'rsi','operator':'gte','value':55.5}]
    assert result['ready_for_execution'], result['blocking_details']


def test_structured_source_retains_unsupported_clauses_with_specific_questions():
    from trading.strategy_source_ingestor import StrategySourceIngestor
    result=StrategySourceIngestor().analyze('# 진입 금지 주석\nENTRY:\n- rsi <= 30.5\n- 강한 유동성 스윕 후 재진입\nEXIT:\n- rsi >= 55\nRISK:\n손절 1%, 익절 2%, 자산 5%. 횡보장 15분봉.',kind='text')
    assert not result['ready_for_execution']
    assert result['rules']['source_condition_gaps'][0]['line']==4
    assert any('강한 유동성 스윕' in q['title'] for q in result['clarification_questions'])
    assert '# 진입 금지' not in result['rules']['entry']
