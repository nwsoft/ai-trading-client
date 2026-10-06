import json
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from trading.paper_capital import paper_available_funds, paper_funds_for


def outcome(**changes):
    return dict(event_id='one', exchange='binance', execution_mode='paper',
                quote_currency='USDT', calculation_status='valid', net_pnl=-50., **changes)


def position(**changes):
    row = dict(execution_mode='paper', entry_price=100., quantity=2., leverage=2)
    row.update(changes)
    return row


def test_available_cash_deducts_open_margin_and_realized_loss_not_mark_gains(tmp_path):
    ledger = tmp_path/'ledger.jsonl'
    ledger.write_text(json.dumps(outcome())+'\n')
    result = paper_available_funds(1000, {'BTC':position(unrealized_pnl=90000)}, venue='binance', quote='USDT', ledger_file=ledger)
    assert result['available_capital'] == 848
    assert result['open_margin'] == 102
    assert result['capital_basis'] == 'paper_reconciled_funds'
    # After a persisted open position disappears, its margin becomes available.
    assert paper_available_funds(1000, {}, venue='binance', quote='USDT', ledger_file=ledger)['available_capital'] == 950


def test_other_venues_and_duplicate_close_events_cannot_change_wallet(tmp_path):
    ledger = tmp_path/'ledger.jsonl'
    one = outcome()
    other = {**one, 'exchange':'upbit', 'quote_currency':'KRW', 'net_pnl':999999}
    ledger.write_text('\n'.join(json.dumps(r) for r in [one, one, other]))
    assert paper_available_funds(1000, {}, venue='binance', quote='USDT', ledger_file=ledger)['available_capital'] == 950


@pytest.mark.parametrize('change', [{'net_pnl':None}, {'net_pnl':float('nan')}, {'quote_currency':''},
                                  {'calculation_status':'legacy_unverified'}, {'event_id':''}])
def test_uncertain_ledger_blocks_new_cash_without_zero_pnl_assumption(tmp_path, change):
    ledger = tmp_path/'ledger.jsonl'
    ledger.write_text(json.dumps({**outcome(), **change}))
    result = paper_available_funds(1000, {}, venue='binance', quote='USDT', ledger_file=ledger)
    assert result['available_capital'] == 0 and result['realized_net_pnl'] is None
    assert result['capital_basis'] == 'paper_funds_unverified'


def test_corrupt_private_ledger_does_not_expose_contents(tmp_path):
    ledger = tmp_path/'ledger.jsonl'; ledger.write_text('private-not-json-account-info')
    result = paper_available_funds(1000, {}, venue='binance', quote='USDT', ledger_file=ledger)
    assert result['available_capital'] == 0
    assert 'private' not in json.dumps(result)


@pytest.mark.parametrize('change', [{'quantity':float('inf')}, {'entry_price':0}, {'execution_mode':'live'}, {'leverage':0}])
def test_unknown_open_margin_is_never_free_cash(tmp_path, change):
    result = paper_available_funds(1000, {'BTC':position(**change)}, venue='binance', quote='USDT', ledger_file=tmp_path/'absent')
    assert result['available_capital'] == 0 and result['open_margin'] is None


def test_spot_and_stock_hold_full_notional_even_with_legacy_leverage(tmp_path):
    for venue in ['upbit', 'kiwoom', 'koreaInvestment', 'miraeAsset', 'shinhan']:
        result = paper_available_funds(1000, {'QA':position(leverage=100)}, venue=venue, quote='KRW', ledger_file=tmp_path/'absent')
        assert result['available_capital'] == 796


def test_contract_size_is_applied_to_simulated_margin(tmp_path):
    row = position(entry_evidence={'position_sizing':{'contract_size':.01}})
    result = paper_available_funds(1000, {'QA':row}, venue='okx', quote='USDT', ledger_file=tmp_path/'absent')
    assert result['available_capital'] == pytest.approx(998.98)


def test_insolvent_paper_wallet_and_pending_reservations_cannot_borrow_initial_cash(tmp_path):
    from trading.opportunity_coordinator import OpportunityCoordinator
    result = paper_available_funds(100, {'BTC':position()}, venue='binance', quote='USDT', ledger_file=tmp_path/'absent')
    assert result['available_capital'] == 0
    c = OpportunityCoordinator(tmp_path/'runtime.db')
    kwargs = dict(policy={}, asset_class='crypto', target='binance', direction='LONG', quantity=1,
                  price=50, stop_fraction=.01, account_scope='qa:paper', signal_time=1800,
                  capital_guard_enabled=True, available_capital=100)
    first = c.authorize(symbol='BTCUSDT', **kwargs)
    assert first.allowed
    c.mark_submitting(first)
    resumed = OpportunityCoordinator(tmp_path/'runtime.db')
    second = resumed.authorize(symbol='ETHUSDT', **kwargs)
    assert not second.allowed and second.reason == 'available_capital_reserved_by_other_orders'


def test_account_change_without_private_recorder_refuses_other_accounts_ledger():
    owner = SimpleNamespace(_opportunity_account='first')
    with patch('path_utils.get_current_user_account', return_value='second'), patch('trading.paper_strategy_ledger.ledger_path', side_effect=AssertionError('must not read')):
        assert paper_funds_for(owner, 1000, {}, venue='binance', quote='USDT')['reason'] == 'paper_account_scope_changed'


def test_recorder_ownership_survives_global_account_change(tmp_path):
    owner = SimpleNamespace(recorder=SimpleNamespace(db_path=str(tmp_path/'account.db')), _opportunity_account='first')
    with patch('trading.paper_strategy_ledger.ledger_path', side_effect=AssertionError('global account path')):
        assert paper_funds_for(owner, 1000, {}, venue='binance', quote='USDT')['available_capital'] == 1000


def test_conflicting_duplicate_is_not_silently_deduplicated(tmp_path):
    ledger = tmp_path/'ledger.jsonl'
    ledger.write_text(json.dumps(outcome())+'\n'+json.dumps({**outcome(), 'net_pnl':9999}))
    assert paper_available_funds(1000, {}, venue='binance', quote='USDT', ledger_file=ledger)['reason'] == 'paper_ledger_event_conflict'


def test_kiwoom_orderable_cash_does_not_fall_back_to_deposit():
    from trading.exchanges.adapters.kiwoom_stock_adapter import KiwoomStockAdapter
    adapter = KiwoomStockAdapter.__new__(KiwoomStockAdapter)
    adapter.account_no = adapter.user_id = ''
    adapter.api_type = adapter.api_version = 'qa'
    cash = adapter._parse_balance_summary({'예수금':'1000000'})
    assert cash['cash'] == 1000000 and cash['orderable_cash'] is None
    zero = adapter._parse_balance_summary({'예수금':'1000000', '주문가능현금':'0'})
    assert zero['orderable_cash'] == 0
