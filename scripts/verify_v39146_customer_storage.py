"""Offline full-size DB COPY stress. Never open the source for writing.

Usage: .venv/bin/python scripts/verify_v39146_customer_storage.py path/to/trading.db
Creates and removes only its own temporary directory. No customer credentials
or private record content is printed; all new writes are synthetic fixtures.
"""
import json
import shutil
import socket
import sqlite3
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run(source):
    source=Path(source).resolve(strict=True)
    wal=Path(str(source)+'-wal')
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError('Use a consistent offline backup; source WAL is not empty')
    before=(source.stat().st_size,source.stat().st_mtime_ns)
    def denied(*a,**kw): raise RuntimeError('Network disabled')
    socket.socket.connect=denied
    socket.create_connection=denied
    from trading.recorder import Recorder
    from trading import recorder_write_queue as queue
    from trading.decision_storage import backfill_batch
    from trading.write_coordination import connection,snapshot
    from trading.exchanges.venue_capabilities import SUPPORTED_VENUES
    import trading.recorder as module
    Recorder.setup_logger=lambda _:None
    Recorder._get_exchange_logger=lambda _:Mock()
    module.log_event=Mock()
    queue.schedule=lambda _:None
    with tempfile.TemporaryDirectory(prefix='noah-v46-ledger-') as temporary:
        target=Path(temporary)/'trading.db'
        shutil.copy2(source,target)
        started=time.monotonic()
        recorder=Recorder(db_path=str(target),log_path=str(Path(temporary)/'logs'))
        with closing(sqlite3.connect(target)) as conn:
            baseline=conn.execute('SELECT count(*) FROM ai_decisions').fetchone()[0]
        prefix='__V46_STRESS__'
        def decisions(venue):
            for n in range(100):
                recorder.save_ai_decision(prefix, f'analyze_symbol::{venue}',
                    {'exchange':venue,'execution_mode':'paper','signal':'HOLD','reason_code':'fixture',
                     'event_time':'2026-09-24T00:00:00+00:00'},exchange=venue)
        def maintenance():
            checked=0; paused=0
            for _ in range(100):
                try:
                    with connection(target,operation='stress_backfill',priority=20,timeout=.1,budget_seconds=.25) as conn:
                        checked+=backfill_batch(conn,limit=100,budget_seconds=.05)
                except sqlite3.OperationalError as exc:
                    if not any(x in str(exc).lower() for x in ('locked','busy','interrupted')):raise
                    paused+=1
                time.sleep(.005)
            return {'checked':checked,'yielded':paused}
        def closes():
            for n in range(20):
                order=f'{prefix}{n}'
                pos=SimpleNamespace(symbol=prefix,entry_price=100,quantity=1,leverage=1,
                    side=SimpleNamespace(value='LONG'),entry_time=datetime.now(timezone.utc),tp_price=110,sl_price=90)
                assert recorder.log_trade_entry(pos,{'exchange':'binance','order_id':order,'execution_mode':'live'})
                assert recorder.update_trade_log(prefix,102,datetime.now(timezone.utc),2,2,'fixture',
                    exchange='binance',entry_order_id=order,exit_order_id=order+'-exit')
        def fills():
            for n in range(20):
                result=recorder.save_exchange_execution_history('okx',[{'id':f'{prefix}{n}',
                    'order':f'{prefix}{n}','symbol':prefix,'side':'sell','price':102,'amount':1,
                    'timestamp':1790208000000+n,'fee':{'cost':.1,'currency':'USDT'}}],reconcile=False)
                assert result['inserted']==1
        with ThreadPoolExecutor(max_workers=14) as workers:
            work=[workers.submit(decisions,venue) for venue in sorted(SUPPORTED_VENUES)]
            work.extend([workers.submit(closes),workers.submit(fills)])
            background=workers.submit(maintenance)
            for result in work: result.result()
            progress=background.result()
        while queue.status(target)['pending']:
            assert queue.drain(recorder,limit=100)>0
        assert queue.status(target)['needs_review']==0
        with closing(sqlite3.connect(target)) as conn:
            actual=conn.execute('SELECT sum(repeat_count) FROM ai_decisions WHERE symbol=?',(prefix,)).fetchone()[0]
            assert actual==len(SUPPORTED_VENUES)*100
            assert conn.execute('SELECT count(*) FROM trade_log WHERE symbol=? AND exit_time IS NOT NULL',(prefix,)).fetchone()[0]==20
            assert conn.execute('SELECT count(*) FROM exchange_execution_log WHERE symbol=?',(prefix,)).fetchone()[0]==20
            assert conn.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        assert before==(source.stat().st_size,source.stat().st_mtime_ns)
        return {'source_unchanged':True,'source_bytes':before[0],'baseline_decisions':baseline,
            'synthetic_decisions':actual,'closed_records':20,'fills':20,'maintenance':progress,
            'writer':snapshot(target),'seconds':round(time.monotonic()-started,2),
            'network':'disabled','live_orders':0,'scope':'offline full-size copy; not Windows or real providers'}


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit(__doc__)
    print(json.dumps(run(sys.argv[1]),ensure_ascii=False,indent=2))
