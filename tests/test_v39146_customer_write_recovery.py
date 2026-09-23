"""Real SQLite writes/replay; provider fixtures never submit orders."""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from trading import recorder_write_queue as queue
from trading.recorder import Recorder
from trading.declarative_strategy_engine import DeclarativeStrategyEngine as Engine


@pytest.fixture
def recorder(tmp_path, monkeypatch):
    monkeypatch.setattr(Recorder, 'setup_logger', lambda _: None)
    monkeypatch.setattr(Recorder, '_get_exchange_logger', lambda _: Mock())
    monkeypatch.setattr('trading.recorder.log_event', Mock())
    monkeypatch.setattr(queue, 'schedule', lambda _: None)
    return Recorder(db_path=str(tmp_path/'trading.db'), log_path=str(tmp_path/'logs'))


def decision(venue='binance'):
    return dict(symbol='BTCUSDT', decision_type=f'analyze_symbol::{venue}',
                decision_data={'exchange': venue, 'execution_mode': 'paper',
                               'signal': 'HOLD', 'reason_code': 'wait',
                               'event_time': '2026-09-23T12:00:00+00:00'}, exchange=venue)


def test_busy_decision_is_persisted_and_replayed_once(recorder):
    lock = sqlite3.connect(recorder.db_path)
    lock.execute('BEGIN IMMEDIATE')
    try:
        recorder.save_ai_decision(**decision())
        assert queue.status(recorder.db_path) == {'pending': 1, 'needs_review': 0}
    finally:
        lock.rollback()
        lock.close()
    # Simulate a restart and crash AFTER primary commit, BEFORE deleting outbox.
    with queue._connect(recorder) as conn:
        token = conn.execute('SELECT token FROM pending').fetchone()[0]
    restarted = Recorder(db_path=recorder.db_path, log_path=str(Path(recorder.db_path).parent/'logs'))
    restarted.save_ai_decision(**decision(), _write_token=token)
    assert queue.drain(restarted) == 1
    assert queue.drain(restarted) == 0
    with sqlite3.connect(recorder.db_path) as conn:
        assert conn.execute('SELECT count(*),sum(repeat_count) FROM ai_decisions').fetchone() == (1, 1)
        assert conn.execute('SELECT count(*) FROM record_write_receipts').fetchone()[0] == 1


def entry(recorder, order, venue='binance'):
    position = SimpleNamespace(symbol='BTCUSDT', entry_price=100, quantity=1,
        leverage=1, side=SimpleNamespace(value='LONG'), entry_time=datetime.now(timezone.utc),
        tp_price=110, sl_price=90)
    return recorder.log_trade_entry(position, {'exchange': venue, 'order_id': order, 'execution_mode': 'live'})


def close(order='original'):
    return dict(symbol='BTCUSDT', exit_price=102, exit_time=datetime.now(timezone.utc),
        pnl_percent=2, pnl_usdt=2, exit_reason='fixture', exchange='binance',
        entry_order_id=order, exit_order_id='close-original')


def test_busy_close_exact_identity_and_crash_receipt(recorder):
    old = entry(recorder, 'original')
    newer = entry(recorder, 'reentry')
    other = entry(recorder, 'original', 'okx')
    payload = close()
    lock = sqlite3.connect(recorder.db_path)
    lock.execute('BEGIN IMMEDIATE')
    try:
        assert recorder.update_trade_log(**payload) is False
        assert queue.unresolved_closes(recorder.db_path, 'binance') == 1
        assert queue.unresolved_closes(recorder.db_path, 'okx') == 0
    finally:
        lock.rollback()
        lock.close()
    with queue._connect(recorder) as conn:
        token = conn.execute('SELECT token FROM pending').fetchone()[0]
    assert recorder.update_trade_log(**payload, _write_token=token)
    assert queue.drain(recorder) == 1
    with sqlite3.connect(recorder.db_path) as conn:
        rows = dict(conn.execute('SELECT id,exit_time FROM trade_log'))
    assert rows[old] and rows[newer] is None and rows[other] is None
    assert queue.unresolved_closes(recorder.db_path, 'binance') == 0


def test_already_closed_conflict_is_retained_for_review(recorder):
    entry(recorder, 'original')
    queue.enqueue(recorder, 'update_trade_log', close())
    assert recorder.update_trade_log(**close())
    assert queue.drain(recorder) == 0
    assert queue.status(recorder.db_path) == {'pending': 0, 'needs_review': 1}
    assert queue.unresolved_closes(recorder.db_path, 'binance') == 1
    # Later exchange-confirmed recovery may supersede the estimate without
    # overwriting authoritative PnL or requiring a developer to delete a queue.
    with sqlite3.connect(recorder.db_path) as conn:
        conn.execute("UPDATE trade_log SET reconciliation_status='exchange_confirmed',net_pnl=1.8 WHERE order_id='original'")
    assert queue.drain(recorder) == 1
    assert queue.unresolved_closes(recorder.db_path, 'binance') == 0
    with sqlite3.connect(recorder.db_path) as conn:
        assert conn.execute('SELECT net_pnl FROM trade_log').fetchone()[0] == 1.8


def test_unidentified_close_never_replays_against_newer_position(recorder):
    payload = close()
    payload.pop('entry_order_id')
    with pytest.raises(ValueError, match='exact_entry_identity'):
        queue.enqueue(recorder, 'update_trade_log', payload)
    assert queue.status(recorder.db_path)['pending'] == 0


def test_distinct_databases_do_not_share_pending_writes(recorder, tmp_path):
    from log_system.storage_policy import disk_usage
    original_size = disk_usage(tmp_path)['db_bytes']
    queue.enqueue(recorder, 'save_ai_decision', decision())
    assert queue.status(str(tmp_path/'other.db'))['pending'] == 0
    assert disk_usage(tmp_path)['db_bytes'] > original_size


def test_seven_venue_concurrent_writes_keep_counts(recorder):
    venues = ['binance','okx','bybit','bitget','upbit','bithumb','coinone']
    def write(venue):
        for _ in range(30):
            recorder.save_ai_decision(**decision(venue))
    with ThreadPoolExecutor(max_workers=7) as workers:
        list(workers.map(write, venues))
    while queue.status(recorder.db_path)['pending']:
        assert queue.drain(recorder, limit=100) > 0
    with sqlite3.connect(recorder.db_path) as conn:
        counts = dict(conn.execute('SELECT exchange,sum(repeat_count) FROM ai_decisions GROUP BY exchange'))
    assert counts == dict.fromkeys(venues,30)


def test_verified_different_exit_does_not_resolve_deferred_close(recorder):
    entry(recorder, 'original')
    queue.enqueue(recorder, 'update_trade_log', close())
    payload = close()
    payload.update(exit_order_id='different-close', net_pnl=1.8, reconciliation_status='exchange_confirmed')
    assert recorder.update_trade_log(**payload)
    assert queue.drain(recorder) == 0
    assert queue.status(recorder.db_path)['needs_review'] == 1


@pytest.mark.parametrize('venue', ['upbit', 'bithumb', 'coinone'])
@pytest.mark.parametrize('held,qty,baseline,valid', [(0,.01,0,False), (.005,.01,0,False), (.01,.01,0,True), (.02,.01,.02,False), (.03,.01,.02,True)])
def test_stale_spot_lot_is_not_a_real_loss(tmp_path, monkeypatch, venue, held, qty, baseline, valid):
    from test_v39146_spot_valuation import setup
    risk, _, _, balances, _, ledger, notify = setup(tmp_path, monkeypatch, venue)
    balances['BTC'] = held
    ledger.get_open_managed_trades.return_value = [{'symbol':'BTC/KRW', 'execution_mode':'live',
        'quantity':qty, 'entry_price':200_000_000, 'spot_baseline_quantity':baseline}]
    result = risk.evaluate_daily_loss_limit(venue, execution_mode='live')
    if not valid:
        assert result.status == 'risk_data_unavailable' and result.blocked
        assert notify.call_args.args[0] == 'risk_data_unavailable'
    else:
        assert result.unrealized_pnl == -qty * 100_000_000


@pytest.mark.parametrize('status', ['compiler_authoritative', 'user_declared_override'])
def test_source_entry_cannot_be_silently_replaced_with_noah_base(status):
    rules = {'source_grounding': {'status':status}, 'source_evidence': {'text':'source entry'},
             'entry': 'source condition', 'executable_entry': {'all':[], 'any':[]}}
    assert Engine.evaluate_entry(rules, {}) == {'allowed':False, 'bypassed':False, 'reason':'source_entry_conditions_missing'}


def test_legacy_risk_only_overlay_still_uses_noah_base():
    assert Engine.evaluate_entry({'executable_entry':{}}, {})['allowed']


def test_internal_coinone_approval_is_not_editable():
    from web_platform.application_services import EDITABLE_BY_PATH
    assert 'coinone_live_e2e_verified' not in EDITABLE_BY_PATH


def test_pending_close_blocks_risk_without_erasing_loss(recorder):
    from trading.risk_manager import RiskManager
    queue.enqueue(recorder, 'update_trade_log', close())
    risk = RiskManager(object(), recorder)
    with pytest.raises(RuntimeError, match='청산 원장 저장'):
        risk._today_live_trades('binance')


def test_paper_pending_close_never_blocks_live(recorder):
    ident = entry(recorder, 'original')
    with sqlite3.connect(recorder.db_path) as conn:
        conn.execute("UPDATE trade_log SET execution_mode='paper' WHERE id=?", (ident,))
    queue.enqueue(recorder, 'update_trade_log', close())
    assert queue.status(recorder.db_path)['pending'] == 1
    assert queue.unresolved_closes(recorder.db_path, 'binance') == 0


def test_source_conditions_work_when_explicitly_defined():
    rules = {'source_grounding':{'status':'user_declared_override'},
             'source_evidence':{'text':'source'}, 'entry':'RSI below 30',
             'executable_entry':{'all':[{'field':'rsi','operator':'lt','value':30}]}}
    assert Engine.evaluate_entry(rules, {'rsi':20})['allowed']
    assert not Engine.evaluate_entry(rules, {'rsi':40})['allowed']


def test_customer_active_versions_and_missing_spot_holdings_readonly():
    from trading.risk_manager import RiskManager
    root = Path(__file__).resolve().parents[1]/'data/Teayu-001'
    if not (root/'trading.db').exists():
        pytest.skip('Private customer fixture is not distributed')
    strategy_path = root/'custom_strategies/unified_private.json'
    before = [(p.stat().st_size, p.stat().st_mtime_ns) for p in (root/'trading.db', strategy_path)]
    data = json.loads(strategy_path.read_text(encoding='utf-8'))
    tested = 0
    for key, version_id in data['active_versions'].items():
        version = next(v for v in data['strategies'][key] if v['version_id'] == version_id)
        result = Engine.evaluate_entry(version['rules'], {})
        assert not result['allowed'] and result['reason'] == 'source_entry_conditions_missing'
        tested += 1
    assert tested == 3
    # Real stored lots, supplied absence response, NOT the customer's actual API.
    with sqlite3.connect(f'file:{root / "trading.db"}?mode=ro&immutable=1', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute('SELECT * FROM trade_log WHERE id IN (56994,57499)')]
    assert len(rows) == 2 and all(r['exit_time'] is None for r in rows)
    ledger = SimpleNamespace(get_open_managed_trades=lambda *a, **kw: rows)
    risk = RiskManager(object(), ledger, exchange_manager=SimpleNamespace())
    result = risk._managed_unrealized_pnl('bithumb', account_snapshot={'valid':True, 'balance_quantities':{'KRW':441.5863}})
    assert not result[0] and '보유 수량과 관리 원장 불일치' in result[2]
    assert before == [(p.stat().st_size, p.stat().st_mtime_ns) for p in (root/'trading.db', strategy_path)]
