#!/usr/bin/env python3
"""Replay existing provider cache on a full COPY; no network or real keys.

Usage: .venv/bin/python scripts/verify_v39147_cached_customer_recovery.py
       data/260924_Teayu/trading.db --trade-id 57909
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trading.binance_history_recovery import BinanceHistoryRecovery, reconstruct_cycle, reconstruct_uniform_close_lot
from trading.pnl_evidence import performance_evidence
from trading.profitability_validation import ProfitabilityValidator
from trading.recorder import Recorder


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def connect(path):
    conn = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def other_rows(db, target):
    h = hashlib.sha256()
    for row in db.execute('SELECT * FROM trade_log WHERE id!=? ORDER BY id', (target,)):
        h.update(json.dumps(tuple(row), ensure_ascii=False).encode())
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--trade-id', type=int, required=True)
    args = parser.parse_args()
    source = args.database.resolve()
    if Path(str(source)+'-wal').exists() and Path(str(source)+'-wal').stat().st_size:
        raise SystemExit('Use a closed exported DB snapshot, not an active WAL database.')
    original_hash = digest(source)
    with connect(source) as db:
        trade = dict(db.execute('SELECT * FROM trade_log WHERE id=?', (args.trade_id,)).fetchone())
        baseline = other_rows(db, args.trade_id)
        since = int(Recorder._ledger_time_epoch(trade['entry_time'])//86400*86400000)-86400000
        sessions = db.execute('SELECT * FROM recovery_history_sessions WHERE symbol=? AND start=? AND verified=1', (trade['symbol'],since)).fetchall()
        assert len(sessions)==1, 'A unique verified cached session is required.'
        session = dict(sessions[0]); data = {}
        for kind, identity in (('fills','id'),('orders','orderId'),('income','tranId')):
            pages = db.execute('''SELECT p.* FROM recovery_history_session_pages m
                JOIN recovery_history_pages p ON p.scope=m.scope AND p.symbol=m.symbol
                AND p.kind=m.kind AND p.start=m.start AND p.end=m.end
                WHERE m.scope=? AND m.symbol=? AND m.session_start=? AND m.kind=? ORDER BY p.start''',
                (session['scope'],trade['symbol'],since,kind)).fetchall()
            through = since-1; unique = {}
            for page in pages:
                assert page['state']=='complete' and page['start']==through+1, 'Incomplete cached coverage'
                through=page['end']
                for row in json.loads(page['rows']):
                    key=str(row[identity])+(':'+row['incomeType'] if kind=='income' else '')
                    assert key not in unique or unique[key]==row, 'Conflicting cached identities'
                    unique[key]=row
            assert through==session['end'], 'Incomplete cached suffix'
            data[kind]=list(unique.values())
    proof, reason = reconstruct_cycle(trade,data['fills'],data['orders'],json.loads(session['anchor']),since,session['end'])
    if reason=='position_cycle_ambiguous':
        proof, reason=reconstruct_uniform_close_lot(trade,data['fills'],data['orders'],json.loads(session['anchor']),since,session['end'])
    assert not reason, reason
    folder=Path(tempfile.mkdtemp(prefix='noahai-v47-cached-proof-'))
    copied=folder/'trading.db'; shutil.copy2(source,copied)
    recorder=Recorder.__new__(Recorder); recorder.db_path=str(copied); recorder.exchange='binance'
    recovery=BinanceHistoryRecovery(recorder,SimpleNamespace(config=SimpleNamespace(api_key='offline-fixture-only')),lambda:None)
    recovery.scope=session['scope']  # Opaque cache scope, no credential extraction.
    assert recovery.apply(trade,proof,data['income'],since,session['end'])==''
    with connect(copied) as db:
        after=dict(db.execute('SELECT * FROM trade_log WHERE id=?',(args.trade_id,)).fetchone())
        assert performance_evidence(after)['performance_evidence_ready']
        assert baseline==other_rows(db,args.trade_id), 'An unrelated trade changed'
    assert recovery.apply(after,proof,data['income'],since,session['end'])==''
    with connect(copied) as db:
        assert after==dict(db.execute('SELECT * FROM trade_log WHERE id=?',(args.trade_id,)).fetchone())
        assert json.loads(db.execute('SELECT before_json FROM recovery_cycle_repairs WHERE scope=? AND trade_id=?',(session['scope'],args.trade_id)).fetchone()[0])==trade
        assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
    rows=recorder.get_recent_trades(exchange='binance',days=45)[-300:]
    reasons=ProfitabilityValidator().evaluate_strategy(rows).get('reasons',[])
    assert digest(source)==original_hash, 'Original database changed during replay'
    print(json.dumps({'copy':str(copied),'basis':proof.get('basis','isolated_position_cycle'),
        'quantity':after['quantity'],'gross':after['gross_pnl'],'net':after['net_pnl'],
        'recent_300_count':len(rows),'recent_300_unresolved':sum(not r.get('performance_evidence_ready',False) for r in rows),
        'reconciliation_policy_block':'pnl_reconciliation_required' in reasons,
        'other_trade_rows_unchanged':True,'original_unchanged':True,'real_api_called':False,
        'live_started':False},ensure_ascii=False))


if __name__=='__main__':
    main()
