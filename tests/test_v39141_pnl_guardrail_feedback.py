"""Offline regression of September 19 feedback; no user DB or exchange credentials."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import sqlite3

import pytest

from trading.recorder import Recorder
from trading.trader import Trader
from trading.risk_manager import RiskManager
from trading.profitability_validation import ProfitabilityValidator
from trading import notifications

VENUES = ('binance', 'bybit', 'okx', 'bitget', 'upbit', 'bithumb', 'coinone',
          'kis', 'kiwoom', 'shinhan', 'mirae')


@pytest.fixture
def ledger(tmp_path):
    return Recorder(db_path=str(tmp_path / 'fixture.db'), log_path=str(tmp_path / 'fixture.log'))


def add(ledger, venue, mode, closed, *, ready=True, net=-2, gross=10):
    with sqlite3.connect(ledger.db_path) as conn:
        conn.execute('''INSERT INTO trade_log
            (symbol,side,entry_price,exit_price,quantity,leverage,pnl,pnl_percent,reason,
             entry_time,exit_time,exchange,execution_mode,reconciliation_status,net_pnl)
            VALUES ('TEST','LONG',100,110,1,1,?,10,'AI close',?,?,?, ?,?,?)''',
            (gross, closed, closed, venue, mode,
             'exchange_confirmed' if ready else 'pending_exchange_reconciliation', net if ready else None))


@pytest.mark.parametrize('venue', VENUES)
def test_daily_window_and_live_aliases(ledger, venue):
    day = datetime(2026, 9, 19)
    noon = day.replace(hour=12)
    timestamps = [noon.isoformat(), str(noon), noon.astimezone(timezone.utc).isoformat()]
    for mode, stamp in zip(('live', 'live_api', 'manual'), timestamps):
        add(ledger, venue, mode, stamp)
    add(ledger, venue, 'optimized', noon.isoformat(), ready=False)
    add(ledger, venue, 'paper', noon.isoformat())
    add(ledger, venue, 'live', str(day - timedelta(seconds=1)))
    add(ledger, venue, 'live', str(day + timedelta(days=1)))
    add(ledger, 'other', 'live', noon.isoformat())
    rows = ledger.get_daily_actual_trades(day, exchange=venue, strict=True)
    assert len(rows) == 4
    assert sum(r['performance_evidence_ready'] for r in rows) == 3
    assert all(r['exchange'] == venue for r in rows)


def test_binance_paper_cannot_block_live_but_unresolved_live_does(ledger):
    now = datetime.now().isoformat()
    add(ledger, 'binance', 'paper', now, ready=False)
    add(ledger, 'binance', 'live', now)
    trader = SimpleNamespace(recorder=ledger)
    rows = Trader._get_recent_trade_samples_binance(trader)
    assert len(rows) == 1 and rows[0]['performance_evidence_ready']
    add(ledger, 'binance', 'live', now, ready=False)
    rows = Trader._get_recent_trade_samples_binance(trader)
    report = ProfitabilityValidator().evaluate_strategy(rows, {'enabled': True})
    assert report['reason'] == 'pnl_reconciliation_required'
    assert report['unresolved_trades'] == 1


def test_ledger_failure_is_not_cold_start(ledger, monkeypatch):
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError('fixture failure')
    monkeypatch.setattr(ledger, 'execute_query', fail)
    with pytest.raises(sqlite3.OperationalError):
        ledger.get_daily_actual_trades(datetime.now(), strict=True)
    rows = Trader._get_recent_trade_samples_binance(SimpleNamespace(recorder=ledger))
    assert rows[0]['performance_evidence_ready'] is False


@pytest.mark.parametrize('venue', VENUES)
@pytest.mark.parametrize('ready', (True, False))
def test_loss_alert_requires_verified_net_not_estimated_gross(ledger, monkeypatch, venue, ready):
    add(ledger, venue, 'live', datetime.now().isoformat(), ready=ready, net=-12, gross=10)
    manager = RiskManager(object(), ledger)
    manager.daily_initial_balance = 100
    manager.max_daily_loss_percent = 10
    monkeypatch.setattr(manager, '_get_live_equity_snapshot', lambda _: {'valid': True, 'equity': 88})
    monkeypatch.setattr(manager, '_managed_unrealized_pnl', lambda _, **kw: (True, 0, ''))
    events = []
    monkeypatch.setattr(notifications, 'publish_notification', lambda *a, **k: events.append(a) or True)
    decision = manager.evaluate_daily_loss_limit(venue, execution_mode='live')
    assert decision.blocked
    if ready:
        assert decision.realized_pnl == -12
        assert decision.loss_rate == 12
        assert events[0][0] == 'guardrail_stop'
        assert '기준 자산 100.0000' in events[0][2]
    else:
        assert decision.status == 'risk_data_unavailable'
        assert events[0][0] == 'risk_data_unavailable'
        assert '%' not in events[0][2]


def test_database_failure_is_not_zero_daily_loss(ledger, monkeypatch):
    manager = RiskManager(object(), ledger)
    monkeypatch.setattr(manager, '_get_live_equity_snapshot', lambda _: {'valid': True, 'equity': 100})
    monkeypatch.setattr(ledger, 'db_path', '/nonexistent/noah-fixture/ledger.db')
    monkeypatch.setattr(notifications, 'publish_notification', lambda *a, **k: True)
    assert manager.evaluate_daily_loss_limit(execution_mode='live').status == 'risk_data_unavailable'


@pytest.mark.parametrize('mode', ('live', 'live_api', 'optimized', 'manual'))
def test_managed_positions_require_valid_price_in_all_live_modes(monkeypatch, mode):
    ledger = SimpleNamespace(get_open_managed_trades=lambda *a, **k: [
        {'symbol': 'TEST', 'entry_price': 100, 'quantity': 1, 'side': 'LONG', 'execution_mode': mode}])
    position = {'symbol':'TEST','side':'LONG','size':1,'unrealized_pnl':-10}
    provider = SimpleNamespace(get_positions_result=lambda:{'status':'success','positions':[position]})
    exchange = SimpleNamespace(get_exchange_client=lambda *a:provider)
    manager = RiskManager(object(), ledger, exchange_manager=exchange)
    assert manager._managed_unrealized_pnl('bybit')[:2] == (True, -10)
    position['unrealized_pnl'] = float('nan')
    assert manager._managed_unrealized_pnl('bybit')[0] is False


def test_other_venue_cannot_use_legacy_binance_balance():
    manager = RiskManager(object(), object())
    assert manager._get_live_equity_snapshot('kiwoom')['valid'] is False
