import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

from trading.decision_storage import ensure_schema, save, backfill_batch
from trading.learning_storage import LearningStore


def decisions(path):
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE IF NOT EXISTS ai_decisions(id INTEGER PRIMARY KEY,symbol TEXT,decision_type TEXT,decision_json TEXT,user_feedback TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
    ensure_schema(conn); conn.commit()
    return conn


def test_historical_metadata_conflicts_and_missing_mode(tmp_path):
    with closing(decisions(tmp_path/'test.db')) as conn:
        payloads = [('trade_runtime::okx', {'exchange':'okx'}),
                    ('trade_runtime::okx', {'exchange':'binance','execution_mode':'live'}),
                    ('stock_auto_trade_symbol', {'broker':'kiwoom','execution_mode':'paper','strategy_version_id':'v1'}),
                    ('legacy', 'broken')]
        for kind,data in payloads:
            conn.execute('INSERT INTO ai_decisions(symbol,decision_type,decision_json) VALUES(?,?,?)', ('BTC',kind,json.dumps(data)))
        conn.commit()
        with conn: assert backfill_batch(conn,2)==2
        with conn: assert backfill_batch(conn,2)==2
        assert backfill_batch(conn,2)==0
        assert conn.execute('SELECT exchange,execution_mode FROM ai_decisions ORDER BY id').fetchall()==[
            ('okx','unknown'),('unknown','live'),('kiwoom','paper'),('unknown','unknown')]


def test_hold_buckets_preserve_changes_modes_and_critical_events(tmp_path):
    with closing(decisions(tmp_path/'test.db')) as conn, conn:
        data={'exchange':'okx','execution_mode':'paper','status':'hold','signal':'HOLD','reason':'neutral',
              'event_time':'2026-09-21T00:00:00+00:00','rsi':50}
        for second in range(30):
            save(conn,'BTC','trade_runtime::okx',{**data,'event_time':f'2026-09-21T00:00:{second:02d}+00:00'})
        assert conn.execute('SELECT count(*),sum(repeat_count) FROM ai_decisions').fetchone()==(1,30)
        for update in ({'rsi':51},{'execution_mode':'live'},{'strategy_version_id':'v2'}, {'event_time':'2026-09-21T00:01:00+00:00'}):
            save(conn,'BTC','trade_runtime::okx',{**data,**update})
        for _ in range(4): save(conn,'BTC','trade_runtime::okx',{**data,'reason':'risk blocked'})
        assert conn.execute('SELECT count(*),sum(repeat_count) FROM ai_decisions').fetchone()==(9,38)


def entry(venue, ident):
    return {'_learning_event_id':f'{venue}-{ident}', 'exchange':venue,'symbol':'BTC','signal':'HOLD',
            'timestamp':f'2026-09-21T00:{ident//60%60:02d}:{ident%60:02d}+00:00',
            'strategy':{'rules':['a','b'],'version':'v1'}, 'metrics':{'rsi':ident%10}, 'execution_mode':'paper'}


def test_learning_roundtrip_archive_idempotency_and_corruption(tmp_path):
    store=LearningStore(tmp_path)
    rows=[entry('okx',i) for i in range(120)]
    for row in rows: store.append('okx',row)
    assert store.recent('okx')==rows
    with closing(store.connect()) as conn:
        assert conn.execute('SELECT count(*) FROM evidence').fetchone()[0]==11
    assert store.archive(keep=20)==100
    with closing(store.connect()) as conn: names=[r[0] for r in conn.execute('SELECT name FROM segments')]
    restored=store.recent('okx')+store.read_segment(names[0])
    assert sorted(restored,key=lambda r:r['_learning_event_id'])==sorted(rows,key=lambda r:r['_learning_event_id'])
    for row in rows: store.append('okx',row)
    assert store.count('okx')==20
    with pytest.raises(ValueError,match='identity_conflict'): store.append('okx',{**rows[0],'signal':'LONG'})
    with closing(store.connect()) as conn, conn: conn.execute("UPDATE evidence SET body='{}'")
    with pytest.raises(ValueError,match='evidence'): store.read_segment(names[0])


def test_stream_import_preserves_original_and_resumes(tmp_path):
    store=LearningStore(tmp_path)
    legacy=tmp_path/'ai_learning_data_okx.json'
    rows=[{**entry('okx',i),'large':'x'*1000} for i in range(250)]
    legacy.write_text(json.dumps(rows),encoding='utf-8')
    before=hashlib.sha256(legacy.read_bytes()).hexdigest()
    assert store.import_legacy(legacy,'okx')==250
    assert store.import_legacy(legacy,'okx')==0
    assert store.recent('okx')==rows
    assert hashlib.sha256(legacy.read_bytes()).hexdigest()==before
    bad=tmp_path/'bad.json'; bad.write_text(json.dumps(rows)[:-10])
    with pytest.raises(ValueError): store.import_legacy(bad,'okx')
    bad.write_text(json.dumps(rows))
    store.import_legacy(bad,'okx')
    assert store.count('okx')==250


def test_seven_venues_concurrent_writes_and_archival(tmp_path):
    venues=['binance','upbit','bithumb','bybit','okx','bitget','coinone']
    store=LearningStore(tmp_path)
    def write(venue):
        for i in range(100): store.append(venue,entry(venue,i))
    with ThreadPoolExecutor(max_workers=8) as pool:
        tasks=[pool.submit(write,v) for v in venues]
        tasks.append(pool.submit(store.archive,20))
        for task in tasks: task.result()
    while store.archive(keep=20): pass
    restored=[]
    with closing(store.connect()) as conn: names=[r[0] for r in conn.execute('SELECT name FROM segments')]
    for name in names: restored+=store.read_segment(name)
    restored+=LearningStore(tmp_path).recent(limit=10000)
    assert len(restored)==700
    assert len({r['_learning_event_id'] for r in restored})==700


def test_manager_account_scope_and_no_json_rewrite(tmp_path,monkeypatch):
    import path_utils
    from trading.exchange_learning_manager import get_exchange_learning_manager
    monkeypatch.setattr(path_utils,'get_app_data_dir',lambda:str(tmp_path/'a'))
    with ThreadPoolExecutor(max_workers=7) as pool: managers=list(pool.map(get_exchange_learning_manager,['okx']*7))
    assert len({id(m) for m in managers})==1
    manager=managers[0]
    monkeypatch.setattr('trading.exchange_learning_manager.emit_kpi_event',lambda **kw:None)
    for i in range(105): assert manager.add_learning_data(entry('okx',i))
    manager._save_learning_data()
    assert not Path(manager.db_path).exists()
    assert len(manager.learning_history)==105
    monkeypatch.setattr(path_utils,'get_app_data_dir',lambda:str(tmp_path/'b'))
    assert get_exchange_learning_manager('okx') is not manager


def test_debug_lease_and_budget(tmp_path,monkeypatch):
    from log_system import storage_policy as policy
    monkeypatch.setattr(policy.time,'time',lambda:1000)
    policy.debug_lease(tmp_path,24)
    debug={'level':SimpleNamespace(no=10)}
    assert policy.diagnostic_filter(tmp_path,debug)
    monkeypatch.setattr(policy.time,'time',lambda:1000+86401)
    assert not policy.diagnostic_filter(tmp_path,debug)
    assert policy.diagnostic_filter(tmp_path,{'level':SimpleNamespace(no=20)})
    (tmp_path/'logs').mkdir(); (tmp_path/'logs'/'trading.log').write_text('x'*100)
    policy.write_policy(tmp_path,{'log_budget_bytes':50})
    assert not policy.diagnostic_filter(tmp_path,{'level':SimpleNamespace(no=20)})
    assert policy.diagnostic_filter(tmp_path,{'level':SimpleNamespace(no=20),'extra':{'_audit_required':True,'_audit_persisted':False}})
    assert not policy.diagnostic_filter(tmp_path,{'level':SimpleNamespace(no=40,name='ERROR'),'message':'failure'})
    with closing(sqlite3.connect(tmp_path/'event_audit.sqlite3')) as conn:
        assert conn.execute('SELECT count(*) FROM events').fetchone()[0]==1


def test_gateway_storage_auth_and_intent(tmp_path):
    from fastapi.testclient import TestClient
    from web_platform.gateway import create_gateway_app
    app=create_gateway_app(token='x'*40,application_services=SimpleNamespace(data_dir=tmp_path,runtime_snapshot=lambda:{}))
    with TestClient(app) as client:
        path='/api/v1/maintenance/storage'; auth={'Authorization':'Bearer '+'x'*40}
        assert client.get(path).status_code==401
        assert client.post(path,headers=auth,json={'action':'debug','hours':24}).status_code==428
        auth['X-NoahAI-Intent']='confirmed'
        assert client.post(path,headers=auth,json={'action':'debug','hours':24}).status_code==200
        assert client.post(path,headers=auth,json={'action':'debug','hours':500}).status_code==400
        assert client.get(path,headers=auth).json()['trade_records_deleted'] is False


def test_real_runtime_contract_hold_and_order_preservation(tmp_path):
    from trading.event_contract import runtime_decision
    with closing(decisions(tmp_path/'test.db')) as conn, conn:
        for venue in ('binance','okx','kiwoom','kis','mirae','shinhan'):
            value=runtime_decision(venue,'BTC','hold','neutral','paper',actual_order=False)
            for _ in range(5): save(conn,'BTC','trade_runtime::'+venue,value)
            for _ in range(2): save(conn,'BTC','trade_runtime::'+venue,{**value,'order_id':'confirmed-order'})
        assert conn.execute('SELECT count(*),sum(repeat_count) FROM ai_decisions').fetchone()==(18,42)
        assert conn.execute('SELECT DISTINCT actual_order FROM ai_decisions').fetchall()==[(0,)]


def test_nested_stock_mode_conflict_and_invalid_legacy_fields():
    from trading.event_contract import metadata
    result=metadata('stock_auto_trade_symbol',{'broker':'kiwoom','validation':{'execution_mode':'paper','trade_candidate':{'strategy_version_id':'v2'}}},historical=True)
    assert (result['exchange'],result['execution_mode'],result['strategy_version_id'])==('kiwoom','paper','v2')
    assert metadata('stock',{'execution_mode':'live','validation':{'execution_mode':'paper'}})['execution_mode']=='unknown'
    result=metadata(None,{'strategy_version_id':{},'reason_code':['invalid'],'session_id':{}})
    assert result['reason_code']=='unknown' and result['strategy_version_id'] is None


def test_common_contract_normalizes_all_current_venues_and_stock_etf():
    from trading.event_contract import contract_issues, metadata, runtime_decision
    crypto = ('binance','upbit','bithumb','coinone','bybit','okx','bitget')
    brokers = ('kiwoom','shinhan','mirae','kis')
    for venue in crypto:
        value = runtime_decision(venue,'BTC','hold','neutral','mock',actual_order=False)
        assert value['execution_mode'] == 'paper'
        assert value['asset_class'] == 'crypto'
        assert value['instrument_type'] in {'spot','futures'}
        assert contract_issues(value) == []
    for broker in brokers:
        value = runtime_decision(broker,'005930','hold','neutral','live_api',actual_order=False)
        assert value['execution_mode'] == 'live'
        assert value['asset_class'] == 'securities'
        assert value['instrument_type'] == 'stock'
        assert contract_issues(value) == []
    etf = metadata('stock_auto_trade_symbol', {
        'broker':'kiwoom','execution_mode':'live_api','is_etf':True,
        'status':'blocked','reason_code':'etf_nav_gap','actual_order':False,
    })
    assert (etf['execution_mode'],etf['asset_class'],etf['instrument_type']) == ('live','securities','etf')


def test_stock_xai_envelope_records_mode_reason_order_and_instrument():
    from unittest.mock import MagicMock
    from trading.stock_analysis_service import StockAnalysisService
    adapter = MagicMock(api_type='real')
    recorder = MagicMock()
    service = StockAnalysisService(adapter, broker_name='kiwoom', recorder=recorder)
    service._persist_xai_decision('069500','stock_auto_trade_symbol', {
        'execution_mode':'live_api','is_etf':True,'action':'BUY','reason_code':'entry_allowed',
        'actual_order':True,'result':{'order_id':'stock-order-1'},'reasoning':'추세와 ETF 괴리율 통과',
    })
    saved = recorder.save_ai_decision.call_args.args[2]
    assert saved['execution_mode'] == 'live'
    assert saved['asset_class'] == 'securities' and saved['instrument_type'] == 'etf'
    assert saved['status'] == 'buy' and saved['reason_code'] == 'entry_allowed'
    assert saved['actual_order'] is True and saved['order_id'] == 'stock-order-1'
    assert saved['xai_contract']['why'] == '추세와 ETF 괴리율 통과'


def test_stock_learning_snapshot_includes_analysis_trade_and_exit_xai(tmp_path):
    from web_platform.query_services import AccountQueryService
    db = tmp_path/'trading.db'
    with closing(decisions(db)) as conn, conn:
        for kind, payload in (
            ('stock_analyze_symbol', {'broker':'kiwoom','execution_mode':'learning','is_etf':False,'signal':'HOLD','reasoning':'관찰'}),
            ('stock_auto_trade_symbol', {'broker':'kiwoom','execution_mode':'paper','is_etf':True,'action':'BUY','reason_code':'entry_allowed','actual_order':False}),
            ('stock_auto_exit_symbol', {'broker':'kiwoom','execution_mode':'live_api','is_etf':True,'action':'SELL','reason_code':'take_profit','actual_order':True,'order_id':'exit-1'}),
        ):
            save(conn,'069500',kind,payload,exchange='kiwoom')
    result = AccountQueryService(str(db)).learning_snapshot(source='kiwoom',limit=10)
    assert {row['decision_type'] for row in result['records']} == {
        'stock_analyze_symbol','stock_auto_trade_symbol','stock_auto_exit_symbol'
    }
    live = next(row for row in result['records'] if row['decision_type']=='stock_auto_exit_symbol')
    assert (live['execution_mode'],live['instrument_type'],live['reason_code'],live['actual_order']) == (
        'live','etf','take_profit',1
    )


def test_archive_failure_does_not_remove_hot_records(tmp_path,monkeypatch):
    import trading.learning_storage as module
    store=LearningStore(tmp_path)
    rows=[entry('okx',i) for i in range(25)]
    for row in rows: store.append('okx',row)
    replace=module.os.replace
    def disk_failure(*args): raise OSError('simulated disk full')
    monkeypatch.setattr(module.os,'replace',disk_failure)
    with pytest.raises(OSError): store.archive(keep=5)
    assert store.recent('okx')==rows
    with closing(store.connect()) as conn:
        assert conn.execute('SELECT count(*) FROM segments').fetchone()[0]==0
    monkeypatch.setattr(module.os,'replace',replace)
    assert LearningStore(tmp_path).archive(keep=5)==20


def test_orphan_segment_retry_and_transaction_rollback(tmp_path,monkeypatch):
    store=LearningStore(tmp_path)
    rows=[entry('binance',i) for i in range(25)]
    for row in rows: store.append('binance',row)
    with closing(store.connect()) as conn:
        conn.execute("CREATE TRIGGER reject_segment BEFORE INSERT ON segments BEGIN SELECT RAISE(ABORT,'crash before commit'); END")
    with pytest.raises(sqlite3.IntegrityError): store.archive(keep=5)
    assert store.count('binance')==25
    assert len(list((tmp_path/'learning_segments').glob('*.gz')))==1
    with closing(store.connect()) as conn: conn.execute('DROP TRIGGER reject_segment')
    assert LearningStore(tmp_path).archive(keep=5)==20
    assert len(list((tmp_path/'learning_segments').glob('*.gz')))==1
    with closing(store.connect()) as conn: name=conn.execute('SELECT name FROM segments').fetchone()[0]
    assert len(store.read_segment(name))+store.count('binance')==25


def test_backfill_two_writers_resume_without_losing_cursor(tmp_path):
    path=tmp_path/'test.db'
    with closing(decisions(path)) as conn,conn:
        conn.executemany('INSERT INTO ai_decisions(symbol,decision_type,decision_json) VALUES(?,?,?)',
                         [('BTC','trade_runtime::okx','{}')]*250)
    def migrate():
        with closing(sqlite3.connect(path,timeout=10)) as conn:
            while True:
                with conn: count=backfill_batch(conn,17)
                if not count: break
    with ThreadPoolExecutor(max_workers=2) as pool:
        for result in [pool.submit(migrate),pool.submit(migrate)]: result.result()
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute('SELECT count(*) FROM ai_decisions WHERE exchange IS NULL').fetchone()[0]==0
        assert conn.execute('SELECT cursor FROM storage_migrations').fetchone()[0]==250


def test_seven_recorders_upgrade_same_legacy_schema_once(tmp_path):
    path=tmp_path/'legacy.db'
    with closing(sqlite3.connect(path)) as conn:
        conn.execute('CREATE TABLE ai_decisions(id INTEGER PRIMARY KEY,symbol TEXT,decision_type TEXT,decision_json TEXT,user_feedback TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
    barrier=threading.Barrier(7)
    def upgrade(_):
        with closing(sqlite3.connect(path,timeout=10)) as conn:
            barrier.wait()
            with conn: ensure_schema(conn)
    with ThreadPoolExecutor(max_workers=7) as pool: list(pool.map(upgrade,range(7)))
    with closing(sqlite3.connect(path)) as conn:
        assert len([row for row in conn.execute('PRAGMA table_info(ai_decisions)') if row[1]=='exchange'])==1


def test_maintenance_retains_financial_tables_and_legacy(tmp_path):
    from trading.storage_maintenance import StorageMaintenance
    with closing(decisions(tmp_path/'trading.db')) as conn,conn:
        conn.execute('CREATE TABLE trades(id INTEGER PRIMARY KEY,pnl TEXT)')
        conn.execute("INSERT INTO trades VALUES(1,'0.25')")
        conn.execute("INSERT INTO ai_decisions(symbol,decision_type,decision_json) VALUES('BTC','legacy','{}')")
    legacy=tmp_path/'ai_learning_data_okx.json'; legacy.write_text(json.dumps([entry('okx',1)]))
    digest=hashlib.sha256(legacy.read_bytes()).hexdigest()
    service=StorageMaintenance(tmp_path); service.run(); service.run()
    assert service.status()['state']=='complete'
    with closing(sqlite3.connect(tmp_path/'trading.db')) as conn:
        assert conn.execute('SELECT * FROM trades').fetchall()==[(1,'0.25')]
    assert hashlib.sha256(legacy.read_bytes()).hexdigest()==digest
    assert LearningStore(tmp_path).count('okx')==1


@pytest.mark.parametrize('body',['[{},,{}]','[{},]','[{}{}]','[null]','[{}]garbage'])
def test_corrupt_legacy_input_is_reported_not_silently_accepted(tmp_path,body):
    path=tmp_path/'legacy.json'; path.write_text(body)
    with pytest.raises(ValueError): LearningStore(tmp_path).import_legacy(path,'okx')
    assert path.read_text()==body


def test_process_crash_preserves_committed_events_and_rolls_back_pending(tmp_path):
    import subprocess,sys
    script='''
import os,sys
from trading.learning_storage import LearningStore
store=LearningStore(sys.argv[1])
store.append('okx',{'_learning_event_id':'committed','timestamp':'2026-09-21T00:00:00Z','symbol':'BTC','rules':{'a':1}})
conn=store.connect()
store.append('okx',{'_learning_event_id':'uncommitted','timestamp':'2026-09-21T00:00:01Z'},conn=conn)
os._exit(7)
'''
    result=subprocess.run([sys.executable,'-c',script,str(tmp_path)],cwd=Path(__file__).resolve().parents[1],timeout=20)
    assert result.returncode==7
    store=LearningStore(tmp_path)
    assert [row['_learning_event_id'] for row in store.recent('okx')]==['committed']
    with closing(store.connect()) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('SELECT count(*) FROM identities').fetchone()[0]==1


def test_critical_audit_preserves_repeated_order_evidence(tmp_path):
    from log_system.event_audit import persist
    for _ in range(3):
        result=persist('order','order submitted','INFO','okx','live',
                       {'symbol':'BTC','order_id':'order-1','ledger_id':'ledger-1','strategy_version_id':'v1','actual_order':True,'reason_code':'entry_allowed'},root=tmp_path)
        assert result['_audit_persisted']
    with closing(sqlite3.connect(tmp_path/'event_audit.sqlite3')) as conn:
        rows=conn.execute('SELECT body FROM events').fetchall()
    assert len(rows)==3
    payload=json.loads(rows[0][0])
    assert payload['execution_mode']=='live' and payload['actual_order']==1
    assert all(key in payload for key in ('app_version','session_id','event_time','event_kind','symbol','exchange','strategy_version_id','reason_code','order_id','ledger_id'))


def test_corrupt_store_status_remains_visible(tmp_path):
    from trading.storage_maintenance import StorageMaintenance
    (tmp_path/'learning.sqlite3').write_bytes(b'corrupt')
    assert StorageMaintenance(tmp_path).status()['learning_archive_error']=='DatabaseError'


def test_report_counts_collapsed_hold_events_without_changing_financials(tmp_path):
    from scripts.generate_noah_user_kpi_report import build_payload
    from trading.event_contract import runtime_decision
    path=tmp_path/'trading.db'
    with closing(decisions(path)) as conn,conn:
        conn.execute('CREATE TABLE trade_log(pnl REAL,pnl_percent REAL,fees REAL,slippage REAL,exchange TEXT,reason TEXT,exit_time TEXT)')
        conn.execute("INSERT INTO trade_log VALUES(.25,5,.01,0,'okx','take_profit','2026-09-21 00:00:00')")
        conn.execute('CREATE TABLE performance_stats(max_drawdown REAL)')
        value=runtime_decision('okx','BTC','hold','neutral','paper')
        for _ in range(30): save(conn,'BTC','trade_runtime::okx',value)
    report=build_payload(path)['summary']
    assert report['counts']['ai_decisions']==30
    assert report['counts']['closed_trades']==1
    assert report['performance']['total_pnl']==.25
    assert report['top_decision_types'][0]['count']==30
