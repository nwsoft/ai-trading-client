#!/usr/bin/env python3
"""Offline incident replay on disposable copies, NEVER on the supplied database.

No API credentials, network client, trading engine or fabricated exchange fills.
Empty WAL sidecars are fingerprinted and retained; nonempty WAL is rejected.
The saved-execution replay is limited evidence, not a live venue reconciliation.
"""
import argparse
import ast
import collections
from contextlib import closing
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trading.recorder import Recorder
from trading.pnl_evidence import performance_evidence
from trading.profitability_validation import ProfitabilityValidator
from trading.record_recovery import RecordRecovery
from trading.record_recovery_adapters import RecoveryResolver


def fingerprint(path):
    result = {}
    for suffix in ('', '-wal', '-shm'):
        file = Path(str(path) + suffix)
        if file.exists():
            with file.open('rb') as stream:
                result[suffix or 'db'] = {
                    'bytes': file.stat().st_size,
                    'sha256': hashlib.file_digest(stream, 'sha256').hexdigest(),
                }
    return result


def connect(path):
    # Only disposable copies reach this helper. Working copies can have a WAL;
    # immutable=1 would silently ignore committed pages still in that WAL and
    # give a false before/after or idempotence result.
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return closing(db)


def sample(path, as_of):
    with connect(path) as db:
        return [dict(row) for row in db.execute('''SELECT * FROM trade_log
            WHERE exchange='binance' AND exit_time>? AND exit_time<=?
            AND LOWER(COALESCE(reason,''))!='binance_import'
            AND LOWER(execution_mode) IN ('live','live_api','optimized','manual')
            ORDER BY exit_time DESC LIMIT 300''',
            ((as_of-timedelta(days=45)).isoformat(' '), as_of.isoformat(' ')))]


def policy(rows):
    return ProfitabilityValidator().evaluate_strategy(
        [{**row, **performance_evidence(row)} for row in rows])


def ledger_digest(path):
    with connect(path) as db:
        rows = [tuple(row) for row in db.execute('SELECT * FROM trade_log ORDER BY id')]
        return {'rows': len(rows), 'sha256': hashlib.sha256(
            json.dumps(rows, ensure_ascii=False).encode()).hexdigest()}


def compare_ledger(before_path, after_path, reported_ids):
    def read(path):
        with connect(path) as db:
            return {row['id']: dict(row) for row in db.execute('SELECT * FROM trade_log')}
    before, after = read(before_path), read(after_path)
    assert before.keys() == after.keys(), 'Recovery inserted or deleted historical trades'
    changed = {i: [key for key in row if row[key] != before[i][key]]
               for i, row in after.items() if row != before[i]}
    return {'changed_rows': len(changed),
            'changed_fields': dict(collections.Counter(key for keys in changed.values() for key in keys)),
            'reported_records_changed': sum(i in changed for i in reported_ids),
            'paper_or_open_records_changed': sum(
                before[i]['exit_time'] is None or str(before[i]['execution_mode']).lower() in {'paper','mock','learning','demo'}
                for i in changed),
            'entry_fees_restored': sum(before[i]['entry_fee'] is None and after[i]['entry_fee'] is not None for i in changed),
            'net_pnl_newly_available': sum(before[i]['net_pnl'] is None and after[i]['net_pnl'] is not None for i in changed)}


class SavedExecutionReplay:
    """Replay only persisted fields. Missing records stay missing (never invented)."""
    def __init__(self, path):
        self.rows = collections.defaultdict(list)
        self.calls = self.hits = 0
        with connect(path) as db:
            for row in db.execute("SELECT * FROM exchange_execution_log WHERE exchange='binance'"):
                row = dict(row)
                epoch = Recorder._ledger_time_epoch(row['executed_at'])
                fill = {'id': row['trade_id'], 'order': row['order_id'],
                        'symbol': row['symbol'], 'side': row['side'],
                        'price': row['price'], 'amount': row['quantity'],
                        'status': row['raw_status'],
                        'timestamp': epoch * 1000 if epoch else None}
                if row['fee'] is not None:
                    fill['fee'] = {'cost': row['fee'], 'currency': row['fee_currency']}
                if row['realized_pnl_present']:
                    fill['realized_pnl'] = row['realized_pnl']
                self.rows[(row['symbol'], str(row['order_id']))].append(fill)

    def get_recovery_order_fills(self, symbol, order_id, closed_epoch):
        self.calls += 1
        fills = self.rows.get((symbol, str(order_id)), [])
        self.hits += bool(fills)
        return [dict(row) for row in fills]


def scan_logs(folder, missing):
    entry_ids = {str(row['order_id']) for row in missing if row['order_id']}
    matched = set()
    algorithms = {}
    failures = set()
    files = sorted(folder.rglob('*.log'))
    for file in files:
        with file.open(errors='replace') as stream:
            for line in stream:
                if "name 'inserted_id' is not defined" in line:
                    failures.add(line.strip())  # duplicate general/venue log lines counted once
                if '주문 결과:' in line:
                    found = re.search(r"['\"]order_id['\"]\s*:\s*['\"]?(\d+)", line)
                    if found and found[1] in entry_ids:
                        matched.add(found[1])
                if '전체데이터:' in line and "'algoId':" in line:
                    text = line.split('전체데이터:', 1)[1].split(' (ex=', 1)[0].strip()
                    try:
                        row = ast.literal_eval(text)
                    except (ValueError, SyntaxError):
                        continue
                    algorithms[(str(row.get('algoId')), str(row.get('actualOrderId')))] = row
    return {'files_scanned': len(files), 'reported_entry_order_ids_seen': len(matched),
            'algo_response_versions': len(algorithms),
            'algo_responses_with_actual_order_id': sum(bool(r.get('actualOrderId')) for r in algorithms.values()),
            'stats_inserted_id_error_unique_lines': len(failures),
            'note': 'Order-entry sightings or NEW algo responses do not prove the executed closing order.'}


def run(path, as_of, logs=False):
    path = path.resolve()
    before = fingerprint(path)
    if before.get('-wal', {}).get('bytes', 0):
        raise ValueError('Nonempty WAL: supply a closed/checkpointed offline backup; source not modified')
    root = Path(tempfile.mkdtemp(prefix='noahai-customer-replay-'))
    frozen = root/'original.sqlite3'
    shutil.copy2(path, frozen)
    if fingerprint(path) != before:
        raise RuntimeError('Source changed while copying')
    original_rows = sample(frozen, as_of)
    missing = [row for row in original_rows if not performance_evidence(row)['performance_evidence_ready']]
    result = {'source': before, 'private_work_directory': str(root),
              'original_policy': policy(original_rows), 'runs': {}}
    with connect(frozen) as db:
        result['original_database'] = {
            'quick_check': db.execute('PRAGMA quick_check').fetchone()[0],
            'execution_count': db.execute('SELECT COUNT(*) FROM exchange_execution_log').fetchone()[0],
            'latest_execution': db.execute('SELECT MAX(executed_at) FROM exchange_execution_log').fetchone()[0],
            'reported_missing_exit_ids': sum(not r['exit_order_id'] for r in missing),
            'reported_missing_statuses': dict(collections.Counter(r['reconciliation_status'] for r in missing)),
            'has_protection_ownership_table': bool(db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='binance_close_evidence'").fetchone()),
        }
    # The first run checks the actual disconnected path; the second checks what
    # the uploaded execution ledger can really supply, not invented API success.
    for mode in ('no_provider', 'saved_execution_replay'):
        folder = root/mode
        folder.mkdir()
        copy = folder/'trading.db'
        shutil.copy2(frozen, copy)
        initial = ledger_digest(copy)
        recorder = Recorder(db_path=str(copy), log_path=str(folder/'logs'), exchange='binance')
        migrated = ledger_digest(copy)
        client = None if mode == 'no_provider' else SavedExecutionReplay(frozen)
        resolver = RecoveryResolver(recorder, client, 'binance')
        now = [as_of.timestamp()]
        recovery = RecordRecovery(recorder, resolver, now=lambda: now[0], delay=0, request_budget=60)
        started = time.monotonic()
        status = recovery.start('binance', background=False)
        passes = 1
        while status['state'] == 'paused' and passes < 100:
            # Recreate the service each pass: persisted queue restart contract.
            recovery = RecordRecovery(recorder, resolver, now=lambda: now[0], delay=0, request_budget=60)
            status = recovery.start('binance', background=False)
            passes += 1
        final_digest = ledger_digest(copy)
        diff = compare_ledger(frozen, copy, {row['id'] for row in missing})
        with connect(recovery.journal) as db:
            items = {row[0] for row in db.execute('SELECT trade_id FROM items WHERE job_id=?', (status['job_id'],))}
        entry = {'status': status, 'passes': passes, 'elapsed_seconds': round(time.monotonic()-started, 3),
                 'reported_targets_included': sum(row['id'] in items for row in missing),
                 'migration_changed_trade_log': initial != migrated,
                 'recovery_changed_trade_log': migrated != final_digest,
                 'policy_after': policy(sample(copy, as_of)),
                 'ledger_changes': diff,
                 'restart_status_identical': RecordRecovery.read_status(copy, 'binance') == status,
                 'provider_calls': client.calls if client else 0, 'saved_order_hits': client.hits if client else 0}
        assert entry['reported_targets_included'] == len(missing)
        assert status['auto_started'] is False and status['resume_authorized'] is False
        assert entry['restart_status_identical']
        assert diff['paper_or_open_records_changed'] == 0
        if mode == 'saved_execution_replay':
            with connect(copy) as db:
                executions_before = db.execute('SELECT COUNT(*) FROM exchange_execution_log').fetchone()[0]
            now[0] += 31  # Explicit second request, after the real cooldown.
            repeated = recovery.start('binance', background=False)
            repeat_passes = 1
            while repeated['state'] == 'paused' and repeat_passes < 100:
                repeated = recovery.start('binance', background=False)
                repeat_passes += 1
            with connect(copy) as db:
                executions_after = db.execute('SELECT COUNT(*) FROM exchange_execution_log').fetchone()[0]
            entry['repeat_run'] = {
                'state': repeated['state'], 'recovered': repeated['recovered'],
                'trade_log_unchanged': final_digest == ledger_digest(copy),
                'execution_count_unchanged': executions_before == executions_after,
            }
            assert entry['repeat_run']['trade_log_unchanged']
            assert entry['repeat_run']['execution_count_unchanged']
        result['runs'][mode] = entry
    # Reproduce the actual statistics-save path with the customer's existing
    # values on one more isolated copy; never feed a made-up profitable result.
    stats_folder = root/'statistics_save'
    stats_folder.mkdir()
    stats_copy = stats_folder/'trading.db'
    shutil.copy2(frozen, stats_copy)
    recorder = Recorder(db_path=str(stats_copy), log_path=str(stats_folder/'logs'), exchange='binance')
    with connect(stats_copy) as db:
        stats = dict(db.execute("SELECT * FROM exchange_trade_stats WHERE exchange='binance'").fetchone())
    baseline = ledger_digest(stats_copy)
    import trading.recorder as recorder_module
    messages, old_log = [], recorder_module.log_event
    try:
        recorder_module.log_event = lambda *a, **kw: messages.append(kw.get('level'))
        saved_id = recorder.save_exchange_trade_stats('binance', stats)
    finally:
        recorder_module.log_event = old_log
    result['statistics_save'] = {
        'returns_saved_row_id': type(saved_id) is int and saved_id > 0,
        'error_logged': 'ERROR' in messages,
        'trade_log_unchanged': baseline == ledger_digest(stats_copy),
    }
    assert result['statistics_save'] == {
        'returns_saved_row_id': True, 'error_logged': False, 'trade_log_unchanged': True}
    # Probe the new discovery route for EVERY real unresolved customer row.
    # Deliberately stop at the provider boundary: no fabricated snapshot, fills,
    # fees or profits and no actual user credential/network request.
    from types import SimpleNamespace
    class ProviderBoundary(Exception):
        pass
    requested = []
    def anchor_probe(symbol):
        requested.append(symbol)
        raise ProviderBoundary()
    probe_client = SimpleNamespace(config=SimpleNamespace(api_key='offline-routing-probe'),
        get_recovery_position_anchor=anchor_probe, get_recovery_history_page=lambda *_: None)
    resolver = RecoveryResolver(recorder, probe_client, 'binance')
    for row in missing:
        try:
            resolver('binance', row)
        except ProviderBoundary:
            pass
        else:
            raise AssertionError('Missing close did not reach native history discovery')
    result['native_discovery_probe'] = {
        'customer_rows_reaching_provider_boundary': len(requested),
        'symbols': len(set(requested)), 'real_provider_calls': 0,
        'trade_log_unchanged': baseline == ledger_digest(stats_copy),
        'note': 'Route verification only. No exchange responses were supplied; this is not recovery proof.'}
    assert len(requested) == len(missing) and result['native_discovery_probe']['trade_log_unchanged']
    if logs:
        result['logs'] = scan_logs(path.parent, missing)
    result['source_unchanged'] = fingerprint(path) == before
    assert result['source_unchanged']
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--as-of', required=True, help='Naive ISO time in the customer machine timezone')
    parser.add_argument('--scan-logs', action='store_true')
    args = parser.parse_args()
    # Keep output aggregate-only. Recorder application logging is not the report.
    from loguru import logger
    logger.remove()
    print(json.dumps(run(args.database, datetime.fromisoformat(args.as_of), args.scan_logs), ensure_ascii=False, indent=2))
