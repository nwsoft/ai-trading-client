#!/usr/bin/env python3
"""Read-only, aggregate-only incident audit of an offline customer ledger.

Requires a closed database copy (no WAL). Does not import Recorder, migrate,
query an exchange, print credentials/receipts, or change customer records.
"""
import argparse
import collections
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3


def audit(path, as_of):
    path = Path(path).resolve()
    if Path(str(path)+'-wal').exists():
        raise ValueError('Use an offline SQLite backup with WAL checkpointed')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1', uri=True) as conn:
        conn.row_factory=sqlite3.Row
        integrity=conn.execute('PRAGMA quick_check').fetchone()[0]
        rows=conn.execute('''SELECT execution_mode,reconciliation_status,exit_order_id,reason,exit_time
            FROM trade_log WHERE exchange='binance' AND exit_time>?
            AND LOWER(COALESCE(reason,''))!='binance_import' ORDER BY exit_time DESC LIMIT 300''',
            ((as_of-timedelta(days=45)).isoformat(),)).fetchall()
        missing=[r for r in rows if r['reconciliation_status']!='exchange_confirmed']
        opened=conn.execute('''SELECT count(*),count(DISTINCT symbol),min(entry_time),max(entry_time)
            FROM trade_log WHERE exchange='binance' AND exit_time IS NULL
            AND order_id IS NOT NULL AND (position_owner='noahai' OR reason LIKE 'AI %')''').fetchone()
        result={'sha256':before,'quick_check':integrity,'as_of':as_of.isoformat(),
                'recent_count':len(rows),'unresolved_count':len(missing),
                'unresolved_modes':dict(collections.Counter(r['execution_mode'] for r in missing)),
                'missing_exit_id_count':sum(not r['exit_order_id'] for r in missing),
                'unresolved_statuses':dict(collections.Counter(r['reconciliation_status'] for r in missing)),
                'tp_sl_reason_count':sum(r['reason']=='TP/SL 청산' for r in missing),
                'open_managed_rows':opened[0],'open_symbols':opened[1],
                'open_entry_range':list(opened[2:]),
                'execution_count':conn.execute('SELECT count(*) FROM exchange_execution_log').fetchone()[0],
                'latest_execution':conn.execute('SELECT max(executed_at) FROM exchange_execution_log').fetchone()[0]}
    after=hashlib.sha256(path.read_bytes()).hexdigest()
    if after!=before:
        raise RuntimeError('source changed during audit')
    result['original_unchanged']=True
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database')
    parser.add_argument('--as-of',required=True)
    args=parser.parse_args()
    print(json.dumps(audit(args.database,datetime.fromisoformat(args.as_of)),ensure_ascii=False,indent=2))
