import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from trading.write_coordination import admission, connection, snapshot
from test_v39146_customer_write_recovery import recorder, decision, entry


def test_entry_retry_survives_restart_and_commit_before_ack(recorder):
    import json
    from trading import recorder_write_queue as queue
    from trading.recorder import TradeLog
    lock = sqlite3.connect(recorder.db_path)
    lock.execute('BEGIN IMMEDIATE')
    try:
        assert entry(recorder, 'deferred-entry') is None
        assert queue.status(recorder.db_path)['pending'] == 1
        assert queue.unresolved_closes(recorder.db_path, 'binance') == 1
    finally:
        lock.rollback(); lock.close()
    with queue._connect(recorder) as conn:
        token, raw = conn.execute('SELECT token,payload FROM pending').fetchone()
    record = TradeLog(**json.loads(raw)['trade_log'])
    assert recorder.insert_trade_log(record, _write_token=token)
    assert queue.drain(recorder) == 1
    with sqlite3.connect(recorder.db_path) as conn:
        assert conn.execute("SELECT count(*) FROM trade_log WHERE order_id='deferred-entry'").fetchone()[0] == 1
    assert queue.unresolved_closes(recorder.db_path, 'binance') == 0


@pytest.mark.parametrize('broker', ['kiwoom','shinhan','mirae','kis'])
@pytest.mark.parametrize('case', ['empty','failure','malformed','disconnected','missing_quantity'])
def test_broker_positions_distinguish_failure_from_empty(broker, case):
    from trading.exchanges.adapters.kiwoom_stock_adapter import KiwoomStockAdapter
    from trading.exchanges.adapters.shinhan_stock_adapter import ShinhanStockAdapter
    from trading.exchanges.adapters.mirae_asset_stock_adapter import MiraeAssetStockAdapter
    from trading.exchanges.adapters.korea_investment_stock_adapter import KoreaInvestmentStockAdapter
    cls = {'kiwoom':KiwoomStockAdapter, 'shinhan':ShinhanStockAdapter,
           'mirae':MiraeAssetStockAdapter, 'kis':KoreaInvestmentStockAdapter}[broker]
    adapter = object.__new__(cls)
    adapter.is_connected = case != 'disconnected'
    adapter.account_no = 'test-only'
    adapter.account_password = ''
    payload = {'multi':[]} if broker == 'kiwoom' else {'holdings':[]}
    if case == 'missing_quantity':
        payload = {'multi':[{'code':'005930'}]} if broker == 'kiwoom' else {'holdings':[{'code':'005930'}]}
    getter = Mock(return_value={} if case == 'malformed' else payload)
    if case == 'failure': getter.side_effect = TimeoutError('fixture')
    adapter._get = getter
    adapter._call_block_request = getter
    result = adapter.get_positions_result()
    assert result['status'] == ('success' if case == 'empty' else 'error')
    assert result['positions'] == ([] if case == 'empty' else None)


def test_stock_exit_failure_is_not_no_positions():
    from trading.stock_analysis_service import StockAnalysisService
    adapter = SimpleNamespace(get_positions_result=lambda: {'status':'error','positions':None})
    service = StockAnalysisService(adapter=adapter, broker_name='kis')
    result, orders = service._run_auto_exit_cycle(asset_mode='all', allow_live_order=True,
        execution_mode='live', remaining_order_budget=1, exit_policy={'enable_exit_policy':True})
    assert orders == 0
    assert result[0]['reason'] == 'exit_positions_unavailable'


def test_waiting_trade_writer_precedes_maintenance(tmp_path):
    path = tmp_path/'ledger.db'
    order = []
    def enter(name, priority):
        with admission(path, name, priority=priority):
            order.append(name)
    with ThreadPoolExecutor(max_workers=2) as pool:
        with admission(path, 'held'):
            low = pool.submit(enter, 'maintenance', 20)
            high = pool.submit(enter, 'trade', 0)
            deadline = time.monotonic()+2
            while snapshot(path)['waiting_writers'] != 2 and time.monotonic()<deadline:
                time.sleep(.002)
            assert snapshot(path)['waiting_writers'] == 2
        high.result(timeout=3); low.result(timeout=3)
    assert order == ['trade','maintenance']
    assert snapshot(path)['active_operation'] is None


def test_slow_maintenance_rolls_back_and_releases_writer(tmp_path):
    path = tmp_path/'ledger.db'
    with connection(path, operation='setup') as conn:
        conn.execute('CREATE TABLE evidence(id INTEGER)')
    with pytest.raises(sqlite3.OperationalError, match='interrupted'):
        with connection(path, operation='maintenance', priority=20, budget_seconds=.01) as conn:
            conn.execute('INSERT INTO evidence VALUES(1)')
            conn.execute('WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<100000000) SELECT sum(x) FROM n').fetchone()
    with connection(path, operation='close') as conn:
        assert conn.execute('SELECT count(*) FROM evidence').fetchone()[0] == 0
        conn.execute('INSERT INTO evidence VALUES(2)')


def test_metadata_budget_cursor_never_skips_unprocessed_rows(recorder, monkeypatch):
    from trading import decision_storage
    for index in range(8):
        recorder.save_ai_decision(**{**decision(), 'symbol':f'T{index}USDT'})
    original = decision_storage.metadata
    def slow(*a, **kw):
        time.sleep(.003)
        return original(*a, **kw)
    monkeypatch.setattr(decision_storage, 'metadata', slow)
    with sqlite3.connect(recorder.db_path) as conn:
        processed = decision_storage.backfill_batch(conn, limit=8, budget_seconds=.001)
        assert 1 <= processed < 8
        first = conn.execute("SELECT cursor FROM storage_migrations WHERE name='decision_metadata_v1'").fetchone()[0]
        ids = [row[0] for row in conn.execute('SELECT id FROM ai_decisions ORDER BY id')]
        assert first == ids[processed - 1]
    with sqlite3.connect(recorder.db_path) as conn:
        assert decision_storage.backfill_batch(conn, limit=8) == 8 - processed


@pytest.mark.parametrize('venue',['binance','okx','bybit','bitget','upbit','bithumb','coinone','kiwoom','shinhan','mirae','kis'])
def test_confirmed_receipt_never_regresses_to_new(recorder, venue):
    for state in ('NEW','PARTIALLY_FILLED','FILLED','NEW','CANCELED'):
        assert recorder.save_exchange_order_receipt(venue, {'id':'fixture','symbol':'BTCUSDT','status':state},source='fixture')
    with sqlite3.connect(recorder.db_path) as conn:
        assert conn.execute('SELECT status FROM exchange_order_receipt WHERE exchange=?',(venue,)).fetchone()[0] == 'FILLED'
        import json
        assert json.loads(conn.execute('SELECT raw_json FROM exchange_order_receipt WHERE exchange=?',(venue,)).fetchone()[0])['status'] == 'FILLED'


@pytest.mark.parametrize('method',['save_exchange_order_receipt','save_exchange_execution_history'])
def test_deferred_order_evidence_exactly_once(recorder, method):
    from trading import recorder_write_queue as queue
    payload = dict(exchange='okx', source='fixture')
    if method == 'save_exchange_order_receipt':
        payload['order'] = {'id':'receipt','symbol':'BTCUSDT','status':'NEW'}
        table = 'exchange_order_receipt'
    else:
        payload.update(trades=[{'id':'fill','order':'receipt','symbol':'BTCUSDT','side':'sell',
            'price':102,'amount':1,'timestamp':1790164800000,'fee':{'cost':.1,'currency':'USDT'}}], reconcile=False)
        table = 'exchange_execution_log'
    token = queue.enqueue(recorder, method, payload)
    getattr(recorder, method)(**payload, _write_token=token)
    assert queue.drain(recorder) == 1
    with sqlite3.connect(recorder.db_path) as conn:
        assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 1


@pytest.mark.parametrize('venue',['bybit','okx','bitget'])
@pytest.mark.parametrize('case',['matched','empty','failure','quantity','side','nan'])
def test_futures_account_evidence_before_pnl(venue, case):
    from trading.risk_manager import RiskManager
    from trading.exchanges.position_snapshot import ccxt_snapshot
    row = {'symbol':'BTC/USDT:USDT','side':'long','contracts':2,'unrealizedPnl':-3}
    provider = SimpleNamespace(is_connected=True, exchange=SimpleNamespace(fetch_positions=Mock(return_value=[row])))
    provider.get_positions_result = lambda: ccxt_snapshot(provider)
    if case=='empty': provider.exchange.fetch_positions.return_value=[]
    if case=='failure': provider.exchange.fetch_positions.side_effect=TimeoutError()
    if case=='quantity': row['contracts']=1
    if case=='side': row['side']='short'
    if case=='nan': row['unrealizedPnl']=float('nan')
    ledger=SimpleNamespace(get_open_managed_trades=lambda *a,**kw:[{'symbol':'BTCUSDT','side':'BUY','quantity':2,'execution_mode':'live'}])
    manager=SimpleNamespace(get_exchange_client=lambda source:provider)
    result=RiskManager(None,ledger,exchange_manager=manager)._managed_unrealized_pnl(venue)
    assert result[0] is (case=='matched')
    if case=='matched': assert result[1]==-3
