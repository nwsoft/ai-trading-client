"""Offline storage scale/recovery verification. Customer sources are read-only.

Usage: .venv/bin/python scripts/verify_v39144_storage.py --customer data/Teayu
Writes only to a new temporary directory and prints JSON measurements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from trading.decision_storage import ensure_schema, backfill_batch
from trading.learning_storage import LearningStore


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--customer',type=Path)
    args=parser.parse_args()
    work=Path(tempfile.mkdtemp(prefix='noahai-v39144-scale-'))
    result={'workspace':str(work),'network_calls':0,'customer_modified':False}
    db=work/'trading.db'
    if args.customer:
        original=args.customer.resolve()/'trading.db'
        before=hashlib.file_digest(original.open('rb'),'sha256').hexdigest()
        with closing(sqlite3.connect(original.as_uri()+'?mode=ro',uri=True)) as src, closing(sqlite3.connect(db)) as dst:
            src.backup(dst)
        result['customer_decisions']=sqlite3.connect(db).execute('SELECT count(*) FROM ai_decisions').fetchone()[0]
    with closing(sqlite3.connect(db)) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('CREATE TABLE IF NOT EXISTS ai_decisions(id INTEGER PRIMARY KEY,symbol TEXT,decision_type TEXT,decision_json TEXT,user_feedback TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        current=conn.execute('SELECT count(*) FROM ai_decisions').fetchone()[0]
        payload=json.dumps({'exchange':'okx','execution_mode':'paper','status':'hold','reason':'neutral'})
        with conn:
            conn.executemany("INSERT INTO ai_decisions(symbol,decision_type,decision_json) VALUES('BTC','trade_runtime::okx',?)", ((payload,) for _ in range(max(0,2500000-current))))
        before_report = None
        if args.customer:
            from scripts.generate_noah_user_kpi_report import build_payload
            before_report = build_payload(db)['summary']
        start=time.perf_counter()
        with conn: ensure_schema(conn)
        result['schema_seconds']=round(time.perf_counter()-start,3)
        start=time.perf_counter(); scanned=0
        while True:
            with conn: count=backfill_batch(conn,2000)
            scanned+=count
            if not count: break
        result['backfill_seconds']=round(time.perf_counter()-start,3)
        result['backfilled']=scanned
        result['unmigrated']=conn.execute('SELECT count(*) FROM ai_decisions WHERE exchange IS NULL').fetchone()[0]
        start=time.perf_counter()
        conn.execute("SELECT id,event_time FROM ai_decisions WHERE exchange='okx' AND execution_mode='paper' ORDER BY event_time DESC,id DESC LIMIT 50").fetchall()
        result['scoped_page_ms']=round((time.perf_counter()-start)*1000,3)
        result['query_plan']=[row[3] for row in conn.execute("EXPLAIN QUERY PLAN SELECT id,event_time FROM ai_decisions WHERE exchange='okx' AND execution_mode='paper' ORDER BY event_time DESC,id DESC LIMIT 50")]
        result['integrity']=conn.execute('PRAGMA quick_check').fetchone()[0]
        if before_report is not None:
            after_report = build_payload(db)['summary']
            for key in ('counts','performance','risk_and_cost','exchange_performance','top_exit_reasons','top_decision_types'):
                assert before_report[key] == after_report[key], key
            result['report_before_after'] = 'PASS'
    print(json.dumps({'phase':'decisions',**result},ensure_ascii=False),flush=True)
    store=LearningStore(work)
    venues=['binance','upbit','bithumb','bybit','okx','bitget','coinone']
    def writer(venue):
        # Bounded batches model independent processes committing simultaneously.
        with closing(store.connect()) as conn:
            for base in range(0,10000,100):
                with conn:
                    for i in range(base,base+100):
                        store.append(venue,{'_learning_event_id':f'{venue}:{i}','timestamp':f'2026-09-21T{i//3600:02d}:{i//60%60:02d}:{i%60:02d}+00:00',
                            'exchange':venue,'symbol':'BTC','execution_mode':'paper',
                            'strategy_rules':{'version':'v1','rules':['rsi < 30','tp 1%']},'metrics':{'rsi':i%100}},conn=conn)
    start=time.perf_counter()
    with ThreadPoolExecutor(max_workers=7) as pool: list(pool.map(writer,venues))
    result['seven_venue_write_seconds']=round(time.perf_counter()-start,3)
    assert store.count()==70000
    start=time.perf_counter()
    reopened=LearningStore(work)
    assert len(reopened.recent('okx',50))==50
    result['restart_and_page_ms']=round((time.perf_counter()-start)*1000,3)
    archived=0
    while True:
        count=store.archive(keep=1000)
        archived+=count
        if not count:break
    with closing(store.connect()) as conn:
        names=[row[0] for row in conn.execute('SELECT name FROM segments')]
        result['unique_evidence']=conn.execute('SELECT count(*) FROM evidence').fetchone()[0]
    restored=sum(len(store.read_segment(name)) for name in names)
    assert restored==archived==63000 and store.count()==7000
    result.update(learning_rows=70000,archived_rows=archived,archive_roundtrip='PASS')
    if args.customer:
        result['customer_sha256_unchanged']=hashlib.file_digest(original.open('rb'),'sha256').hexdigest()==before
        assert result['customer_sha256_unchanged']
        customer_store=LearningStore(work/'customer_learning')
        source=args.customer/'ai_learning_data_okx.json'
        start=time.perf_counter()
        if source.exists():
            with source.open('rb') as handle: learning_before=hashlib.file_digest(handle,'sha256').hexdigest()
            result['customer_learning_imported']=customer_store.import_legacy(source,'okx')
            result['customer_learning_import_seconds']=round(time.perf_counter()-start,3)
            assert customer_store.import_legacy(source,'okx')==0
            with source.open('rb') as handle: assert hashlib.file_digest(handle,'sha256').hexdigest()==learning_before
            result['customer_learning_sha256_unchanged'] = True
    print(json.dumps({'phase':'complete',**result},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__': main()
