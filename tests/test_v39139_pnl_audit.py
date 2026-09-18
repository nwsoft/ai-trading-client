from datetime import datetime, timezone
import sqlite3

import pytest

from trading.recorder import Recorder, TradeLog
from web_platform.query_services import AccountQueryService
from trading.pnl_evidence import provider_fill_gross_pnl
from trading.profitability_validation import ProfitabilityValidator
from trading.smart_exit_policy import _trade_returns

VENUES = ('binance', 'bybit', 'okx', 'bitget', 'upbit', 'bithumb', 'coinone',
          'kis', 'kiwoom', 'shinhan', 'mirae')


def setup_trade(tmp_path, venue='binance', mode='live', exit_id='exit-1'):
    recorder = Recorder(db_path=str(tmp_path / 'trading.db'), log_path=str(tmp_path / 'logs'), exchange=venue)
    stock = venue in {'kis', 'kiwoom', 'shinhan', 'mirae'}
    symbol = '005930' if stock else 'BTCUSDT'
    currency = 'KRW' if stock or venue in {'upbit', 'bithumb', 'coinone'} else 'USDT'
    trade_id = recorder.insert_trade_log(TradeLog(
        id=None, symbol=symbol, entry_price=100, exit_price=110, quantity=2,
        leverage=1, pnl=20, pnl_percent=10, entry_time=datetime.now(), exit_time=datetime.now(),
        reason='AI close', side='LONG', tp_price=None, sl_price=None, fees=0, slippage=0,
        exchange=venue, order_id='entry-1', exit_order_id=exit_id, position_owner='noahai',
        execution_mode=mode, settlement_currency=currency, entry_fee=0,
        pnl_source='estimated_close_price', reconciliation_status='pending_exchange_reconciliation',
    ))
    fill = {'id': 'fill-1', 'order': 'exit-1', 'symbol': symbol, 'side': 'sell',
            'price': 95, 'amount': 2, 'realized_pnl': -10,
            'fee': {'cost': 0.2, 'currency': currency}, 'status': 'closed',
            'timestamp': int(datetime.now().timestamp() * 1000)}
    return recorder, trade_id, fill


@pytest.mark.parametrize('venue', VENUES)
def test_live_fill_never_rewrites_paper_trade(tmp_path, venue):
    recorder, trade_id, fill = setup_trade(tmp_path, venue, mode='paper')
    recorder.save_exchange_execution_history(venue, [fill])
    assert recorder.execute_query('SELECT pnl FROM trade_log WHERE id=?', (trade_id,))[0][0] == 20


def test_missing_order_unique_time_quantity_is_not_ownership_proof(tmp_path):
    recorder, trade_id, fill = setup_trade(tmp_path, exit_id=None)
    # A manual order may match all heuristic fields; do not certify ownership.
    recorder.save_exchange_execution_history('binance', [fill])
    row = recorder.execute_query('SELECT exit_order_id, pnl, reconciliation_status FROM trade_log WHERE id=?', (trade_id,))[0]
    assert not row[0]
    assert row[1] == 20
    assert not row[2].startswith('exchange_confirmed')


def test_exact_order_wrong_side_cannot_certify_close(tmp_path):
    recorder, trade_id, fill = setup_trade(tmp_path)
    fill['side'] = 'buy'
    recorder.save_exchange_execution_history('binance', [fill])
    assert recorder.execute_query('SELECT reconciliation_status FROM trade_log WHERE id=?', (trade_id,))[0][0] != 'exchange_confirmed'


def test_unknown_fee_currency_not_inferred_from_other_fill(tmp_path):
    recorder, trade_id, fill = setup_trade(tmp_path)
    fill['amount'] = 1
    other = {**fill, 'id': 'fill-2', 'fee': {'cost': 1, 'currency': ''}}
    recorder.save_exchange_execution_history('binance', [fill, other])
    row = recorder.execute_query('SELECT net_pnl, reconciliation_status FROM trade_log WHERE id=?', (trade_id,))[0]
    assert row[0] is None
    assert row[1] == 'exchange_confirmed_fee_conversion_required'


def test_timestamp_epoch_and_iso_represent_same_execution():
    instant = datetime(2026, 9, 18, 0, 3, 13, tzinfo=timezone.utc)
    assert Recorder._execution_time_text(instant.timestamp() * 1000) == Recorder._execution_time_text(instant.isoformat())


@pytest.mark.parametrize('venue', ('kis', 'kiwoom', 'shinhan', 'mirae'))
def test_stock_execution_notional_is_krw(tmp_path, venue):
    recorder, _, fill = setup_trade(tmp_path, venue)
    recorder.save_exchange_execution_history(venue, [fill])
    result = AccountQueryService(recorder.db_path)._exchange_execution_summary(source=venue, asset_class='stock')
    assert result['notional_by_currency'] == {'KRW': 190}


@pytest.mark.parametrize('venue,key', [('binance', 'realizedPnl'), ('okx', 'fillPnl'), ('bitget', 'profit')])
def test_native_provider_gross_fields(venue, key):
    assert provider_fill_gross_pnl(venue, {'info': {key: '-0.25'}}) == -0.25
    assert provider_fill_gross_pnl(venue, {'info': {key: '0'}}) == 0
    assert provider_fill_gross_pnl(venue, {'info': {key: 'nan'}}) is None


def test_generic_profit_or_bybit_closed_pnl_is_not_fill_gross():
    assert provider_fill_gross_pnl('bybit', {'pnl': 1, 'profit': 1, 'info': {'closedPnl': 1}}) is None


def test_persisted_estimate_blocks_profitability_success_and_cold_start(tmp_path):
    recorder, _, _ = setup_trade(tmp_path)
    for rows in (recorder.get_recent_trades(exchange='binance'), recorder.get_trade_history()):
        assert rows[0]['performance_evidence_ready'] is False
        assert rows[0]['pnl_is_net'] is False
        report = ProfitabilityValidator().evaluate_strategy(rows, {'enabled': True})
        assert report['enabled'] is False
        assert report['bypassed'] is False
        assert report['reason'] == 'pnl_reconciliation_required'
        assert _trade_returns(rows) == []


def test_actual_loss_replaces_estimated_profit_for_performance(tmp_path):
    recorder, _, fill = setup_trade(tmp_path)
    recorder.save_exchange_execution_history('binance', [fill])
    rows = recorder.get_recent_trades(exchange='binance')
    assert rows[0]['performance_evidence_ready'] is True
    assert rows[0]['net_pnl'] == pytest.approx(-10.2)
    assert _trade_returns(rows) == pytest.approx([-0.051])


def test_exchange_reference_is_not_noah_owned_or_full_account_total(tmp_path):
    recorder, _, fill = setup_trade(tmp_path)
    manual = {**fill, 'id': 'manual-fill', 'order': 'manual-exit', 'realized_pnl': 15}
    recorder.save_exchange_execution_history('binance', [fill, manual])
    stats = AccountQueryService(recorder.db_path).trading_statistics(asset_class='crypto', source='binance')
    assert stats['pnl_by_currency']['USDT'] == pytest.approx(-10.2)
    reference = stats['exchange_pnl_reference']
    assert reference['gross_pnl_by_currency']['USDT'] == 5
    assert reference['account_total_verified'] is False
    assert reference['fees_included'] is False
    assert reference['funding_included'] is False


def test_fee_rebate_is_not_discarded(tmp_path):
    recorder, trade_id, fill = setup_trade(tmp_path)
    fill['fee']['cost'] = -0.1
    recorder.save_exchange_execution_history('binance', [fill])
    assert recorder.execute_query('SELECT net_pnl FROM trade_log WHERE id=?', (trade_id,))[0][0] == pytest.approx(-9.9)


def test_shared_exit_order_cannot_double_count_pnl(tmp_path):
    recorder, trade_id, fill = setup_trade(tmp_path)
    with sqlite3.connect(recorder.db_path) as conn:
        columns = [row[1] for row in conn.execute('PRAGMA table_info(trade_log)') if row[1] != 'id']
        names = ','.join(columns)
        conn.execute(f'INSERT INTO trade_log ({names}) SELECT {names} FROM trade_log WHERE id=?', (trade_id,))
    recorder.save_exchange_execution_history('binance', [fill])
    assert recorder.execute_query('SELECT reconciliation_status FROM trade_log') == [('order_attribution_conflict',)] * 2


def test_late_pnl_enriches_same_fill_without_duplicates_or_downgrade(tmp_path):
    recorder, trade_id, fill = setup_trade(tmp_path)
    incomplete = {k: v for k, v in fill.items() if k not in ('realized_pnl', 'fee')}
    recorder.save_exchange_execution_history('binance', [incomplete])
    assert recorder.execute_query('SELECT realized_pnl_present FROM exchange_execution_log')[0][0] == 0
    recorder.save_exchange_execution_history('binance', [fill])
    assert recorder.execute_query('SELECT net_pnl FROM trade_log WHERE id=?', (trade_id,))[0][0] == pytest.approx(-10.2)
    incomplete['timestamp'] += 1000  # Same fill ID, corrected/reformatted timestamp.
    incomplete['fee'] = {'cost': None, 'currency': None}
    recorder.save_exchange_execution_history('binance', [incomplete])
    assert recorder.execute_query('SELECT COUNT(*), realized_pnl_present, realized_pnl, fee FROM exchange_execution_log')[0] == (1, 1, -10, 0.2)
    assert recorder.execute_query('SELECT net_pnl FROM trade_log WHERE id=?', (trade_id,))[0][0] == pytest.approx(-10.2)
