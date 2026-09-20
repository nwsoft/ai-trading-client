"""Regression for the committed-write/False-return found in customer logs."""
import sqlite3

import pytest
import trading.recorder as recorder_module
from test_v39139_pnl_audit import setup_trade, VENUES


@pytest.mark.parametrize('venue', VENUES)
@pytest.mark.parametrize('legacy_schema', [False, True])
def test_stats_save_returns_committed_id_without_false_failure(tmp_path, monkeypatch, venue, legacy_schema):
    recorder, _, _ = setup_trade(tmp_path, venue)
    messages = []
    monkeypatch.setattr(recorder_module, 'log_event', lambda *a, **kw: messages.append((a, kw)))
    before = recorder.execute_query('SELECT * FROM trade_log')
    if legacy_schema:
        with sqlite3.connect(recorder.db_path) as db:
            db.execute('DROP TABLE exchange_trade_stats')
            db.execute('''CREATE TABLE exchange_trade_stats (
                id INTEGER PRIMARY KEY, exchange TEXT UNIQUE, total_trades INTEGER,
                winning_trades INTEGER, losing_trades INTEGER, total_pnl REAL,
                max_drawdown REAL, last_updated TEXT)''')
    for pnl in (0.25, -0.30):
        result = recorder.save_exchange_trade_stats(venue, {
            'total_trades': 1, 'winning_trades': int(pnl > 0),
            'losing_trades': int(pnl < 0), 'total_pnl': pnl, 'total_fees': 0.01,
        })
        assert isinstance(result, int) and not isinstance(result, bool) and result > 0
        assert recorder.execute_query('SELECT total_trades,total_pnl FROM exchange_trade_stats WHERE exchange=?',
                                      (venue,)) == [(1, pnl)]
    assert not any(kw.get('level') == 'ERROR' for _, kw in messages)
    assert recorder.execute_query('SELECT * FROM trade_log') == before
