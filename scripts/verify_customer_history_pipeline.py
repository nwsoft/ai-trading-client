#!/usr/bin/env python3
"""Integration test on full customer DB COPIES with explicitly SYNTHETIC API data.

This does NOT reconstruct the customer's actual missing profits. Real row IDs,
entry orders, sides, quantities, entry times and the surrounding DB are retained.
Only the missing provider input is simulated; close time/price/PnL/fees/flat
position are test assumptions. No credentials, network, engine or order calls.
Run verify_customer_record_recovery.py separately for stored-evidence-only proof.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_customer_record_recovery import (
    fingerprint, connect, sample, policy, ledger_digest, compare_ledger,
    Recorder, RecordRecovery, RecoveryResolver, performance_evidence,
)
from api.binance_client import BinanceClient
from web_platform.query_services import AccountQueryService


class SyntheticTransport:
    """Native BinanceClient read methods, with the transport replaced locally."""
    def __init__(self, rows, as_of):
        self.calls = Counter()
        self.omit_income = False
        self.fail_next_read = False
        self.expected = {}
        self.data = {'fills': [], 'orders': [], 'algos': [], 'income': []}
        for index, row in enumerate(sorted(rows, key=lambda r: r['id'])):
            quantity, price = Decimal(str(row['quantity'])), Decimal(str(row['entry_price']))
            side = 'BUY' if row['side'].upper() in {'BUY', 'LONG'} else 'SELL'
            # Deliberately artificial values, NOT the estimated DB PnL. Two
            # AVA rows exercise the reported +.25 followed by +.02 shape.
            gross = Decimal('.25') if row['id'] == 13296 else (
                Decimal('.02') if row['id'] == 13300 else Decimal('-.01'))
            start = int(Recorder._ledger_time_epoch(row['entry_time']) * 1000)
            end = start + 10000  # Test-only close, not claimed historical time.
            end_price = price + gross / quantity * (1 if side == 'BUY' else -1)
            assert end_price > 0
            pair = []
            for offset in (0, 1):
                fill = dict(id=9000000000000 + index * 2 + offset,
                    orderId=str(row['order_id']) if not offset else str(8000000000000 + index),
                    symbol=row['symbol'], side=side if not offset else ('SELL' if side == 'BUY' else 'BUY'),
                    qty=str(quantity), price=str(price if not offset else end_price),
                    commission='0.001' if not offset else '0.002', commissionAsset='USDT',
                    realizedPnl='0' if not offset else str(gross), positionSide='BOTH',
                    time=start if not offset else end)
                pair.append(fill)
                self.data['orders'].append(dict(orderId=fill['orderId'], symbol=fill['symbol'],
                    side=fill['side'], positionSide='BOTH', status='FILLED',
                    executedQty=fill['qty'], time=fill['time']))
            self.data['fills'].extend(pair)
            self.data['income'].append(dict(tranId=pair[-1]['id'], tradeId=str(pair[-1]['id']),
                symbol=row['symbol'], incomeType='REALIZED_PNL', asset='USDT',
                income=str(gross), time=end))
            self.expected[row['id']] = {'gross': float(gross), 'net': float(gross - Decimal('.003'))}
        self.client = object.__new__(BinanceClient)  # Never initialize a network SDK.
        self.client.config = SimpleNamespace(api_key='SYNTHETIC-OFFLINE-ONLY', recv_window=5000)
        self.client._has_api_keys = lambda: True
        self.client.get_synced_timestamp = lambda: int(as_of.timestamp() * 1000)
        self.client._get_futures_signed = self.signed
        self.client.client = SimpleNamespace(futures_account_trades=self.exact_order)

    def signed(self, path, params):
        self.calls[path] += 1
        if self.fail_next_read:
            self.fail_next_read = False
            raise TimeoutError('Injected offline transport timeout')
        if path == '/fapi/v2/positionRisk':
            return [dict(symbol=params['symbol'], positionSide='BOTH', positionAmt='0', updateTime=0)]
        kinds = {'/fapi/v1/userTrades': 'fills', '/fapi/v1/allOrders': 'orders',
                 '/fapi/v1/allAlgoOrders': 'algos', '/fapi/v1/income': 'income'}
        kind = kinds[path]  # Any unexpected (especially order-write) path fails.
        if kind == 'income' and self.omit_income:
            return []
        return deepcopy([r for r in self.data[kind] if r['symbol'] == params['symbol']
            and params['startTime'] <= r['time'] <= params['endTime']][-params['limit']:])

    def exact_order(self, **params):
        self.calls['SDK.userTrades'] += 1
        return deepcopy([r for r in self.data['fills'] if r['symbol'] == params['symbol']
            and str(r['orderId']) == str(params['orderId'])
            and params['startTime'] <= r['time'] <= params['endTime']])


def statistics(path):
    stats = AccountQueryService(str(path)).trading_statistics(asset_class='crypto', source='binance', period='all')
    return {key: stats[key] for key in ('reconciled_closed_count', 'gross_pnl_by_currency', 'pnl_by_currency')}


def drive(recorder, transport, now):
    passes = 0
    while True:
        # New worker/resolver each batch exercises the actual persisted restart.
        job = RecordRecovery(recorder, RecoveryResolver(recorder, transport.client, 'binance'),
                             now=lambda: now, request_budget=17, delay=0)
        status = job.start('binance', background=False)
        passes += 1
        if status['state'] != 'paused':
            assert status['state'] != 'failed', status
            return status, passes
        assert passes < 500, 'Recovery failed to make bounded progress'


def run(source, as_of):
    before = fingerprint(source)
    if before.get('-wal', {}).get('bytes', 0):
        raise ValueError('Nonempty source WAL; provide a closed/checkpointed copy')
    root = Path(tempfile.mkdtemp(prefix='noahai-customer-synthetic-'))
    frozen = root / 'original.sqlite3'
    shutil.copy2(source, frozen)
    assert fingerprint(source) == before
    missing = [r for r in sample(frozen, as_of) if not performance_evidence(r)['performance_evidence_ready']]
    assert len(missing) == 40, 'This incident test expects the supplied 40/300 DB snapshot'
    report = {'evidence_type': 'CUSTOMER_DB_WITH_SYNTHETIC_PROVIDER_INPUT_NOT_ACTUAL_RECOVERY',
              'source_sha256': before['db']['sha256'], 'private_work_directory': str(root),
              'source_missing_count': len(missing), 'scenarios': {}}
    for name, selected, delayed in (
        ('first_close', [r for r in missing if r['id'] == 13296], False),
        ('first_and_second', [r for r in missing if r['id'] in {13296, 13300}], False),
        ('all_40_with_restarts_and_delayed_income', missing, True),
    ):
        folder = root / name
        folder.mkdir()
        database = folder / 'trading.db'
        shutil.copy2(frozen, database)
        recorder = Recorder(db_path=str(database), log_path=str(folder / 'logs'), exchange='binance')
        baseline, stats_before = ledger_digest(database), statistics(database)
        transport = SyntheticTransport(selected, as_of)
        now = as_of.timestamp()
        started = time.monotonic()
        if delayed:
            transport.fail_next_read = True
            job = RecordRecovery(recorder, RecoveryResolver(recorder, transport.client, 'binance'),
                                 now=lambda: now, request_budget=17, delay=0)
            failed = job.start('binance', background=False)
            assert failed['state'] == 'failed' and failed['error'] == 'TimeoutError'
            assert failed['recovered'] == 0 and ledger_digest(database) == baseline
            now += 31
            transport.omit_income = True
            pending, _ = drive(recorder, transport, now)
            assert pending['recovered'] == 0
            assert pending['reasons'].get('income_reconciliation_required') == len(selected)
            assert ledger_digest(database) == baseline
            transport.omit_income = False
            now += 31
        status, passes = drive(recorder, transport, now)
        with connect(database) as db:
            actual = {r['id']: dict(r) for r in db.execute('SELECT * FROM trade_log') if r['id'] in transport.expected}
            for tid, expected in transport.expected.items():
                row = actual[tid]
                assert performance_evidence(row)['performance_evidence_ready'], (tid, row['reconciliation_status'])
                assert abs(row['gross_pnl'] - expected['gross']) < 1e-10
                assert abs(row['net_pnl'] - expected['net']) < 1e-10
            execution_count = db.execute('SELECT COUNT(*) FROM exchange_execution_log').fetchone()[0]
        stats_after = statistics(database)
        gross = sum(r['gross'] for r in transport.expected.values())
        net = sum(r['net'] for r in transport.expected.values())
        assert stats_after['reconciled_closed_count'] - stats_before['reconciled_closed_count'] == len(selected)
        assert abs(stats_after['gross_pnl_by_currency']['USDT'] - stats_before['gross_pnl_by_currency']['USDT'] - gross) < 1e-7
        assert abs(stats_after['pnl_by_currency']['USDT'] - stats_before['pnl_by_currency']['USDT'] - net) < 1e-7
        delta = compare_ledger(frozen, database, set(transport.expected))
        assert delta['changed_rows'] == len(selected) and delta['paper_or_open_records_changed'] == 0
        digest = ledger_digest(database)
        repeat, _ = drive(recorder, transport, now + 31)
        assert repeat['recovered'] == 0 and ledger_digest(database) == digest
        with connect(database) as db:
            assert db.execute('SELECT COUNT(*) FROM exchange_execution_log').fetchone()[0] == execution_count
            assert db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        # Evaluate the actual runtime getter (not SQL lexical time ordering).
        runtime_policy = policy(recorder.get_recent_trades(exchange='binance', days=3650)[-300:])
        assert runtime_policy.get('unresolved_trades', 0) == 40-len(selected), runtime_policy
        assert status['auto_started'] is False and status['resume_authorized'] is False
        report['scenarios'][name] = {
            'synthetic_recovered': status['recovered'], 'batch_restarts': passes-1,
            'delayed_income_blocks_then_retry_recovers': delayed,
            'timeout_preserves_ledger_then_resumes': delayed,
            'gross_delta': round(gross, 10), 'net_delta': round(net, 10),
            'runtime_recent_300_policy': runtime_policy,
            'full_maintenance_remaining': status['remaining'],
            'non_target_trade_rows_unchanged': True, 'statistics_delta_matches': True,
            'repeat_no_duplicate_fills_or_pnl': True, 'auto_started': False,
            'elapsed_seconds': round(time.monotonic()-started, 3),
            'local_transport_calls': dict(transport.calls),
        }
    report['source_and_sidecars_unchanged'] = fingerprint(source) == before
    assert report['source_and_sidecars_unchanged']
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--as-of', required=True)
    args = parser.parse_args()
    from loguru import logger
    logger.remove()
    # Fail closed if any implementation accidentally tries a real network call.
    with patch('socket.socket.connect', side_effect=AssertionError('Network forbidden in offline customer test')):
        print(json.dumps(run(args.database.resolve(), datetime.fromisoformat(args.as_of)), ensure_ascii=False, indent=2))
