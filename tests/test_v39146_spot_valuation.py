"""Exercise real balance -> catalogue -> ticker -> risk -> persisted basis path.

Only external I/O is supplied; never replace the equity evaluator with a bool.
"""
import logging
import sqlite3
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from trading.exchange_manager import ExchangeManager
from trading.risk_manager import RiskManager
from trading.spot_valuation import SpotValuation


VENUES = ('upbit', 'bithumb', 'coinone')


def market(base='BTC', quote='KRW', active=True):
    return dict(symbol=f'{base}/{quote}', base=base, quote=quote, active=active, spot=True)


def setup(tmp_path, monkeypatch, venue):
    from trading import notifications
    notify = Mock(return_value=True)
    monkeypatch.setattr(notifications, 'publish_notification', notify)
    markets = {'BTC/KRW': market()}
    prices = {'BTC/KRW': 100_000_000}
    exchange = SimpleNamespace(load_markets=Mock(side_effect=lambda **k: deepcopy(markets)),
                               fetch_ticker=Mock(side_effect=lambda s: {'last': prices[s]}))
    adapter = SimpleNamespace(is_connected=True, exchange=exchange)
    balances = {'KRW': 1_000_000, 'BTC': .01, 'APENFT': 100, 'EMC': 1}
    manager = ExchangeManager.__new__(ExchangeManager)
    manager.settings = {'enabled_exchanges': [venue]}
    manager._get_or_create_exchange_client = Mock(return_value=adapter)
    manager.get_exchange_balance = Mock(side_effect=lambda *a, **k: {'status': 'success', 'balance': dict(balances)})
    ledger = SimpleNamespace(db_path=str(tmp_path/'risk.db'),
                             get_open_managed_trades=Mock(return_value=[]),
                             get_daily_actual_trades=Mock(return_value=[]))
    risk = RiskManager(object(), ledger, {f'{venue}_api_key': 'test-only'}, manager)
    return risk, markets, prices, balances, exchange, ledger, notify


@pytest.mark.parametrize('venue', VENUES)
def test_residuals_do_not_block_or_become_zero_valued_assets(tmp_path, monkeypatch, venue):
    risk, _, _, balances, exchange, ledger, notify = setup(tmp_path, monkeypatch, venue)
    original = dict(balances)
    result = risk.evaluate_daily_loss_limit(venue, execution_mode='live')
    assert not result.blocked and result.status == 'ok'
    assert result.current_equity == 2_000_000
    assert result.valuation_scope == 'priced_assets_only'
    assert {v['asset'] for v in result.unvalued_assets} == {'APENFT', 'EMC'}
    assert all(v['value'] is None for v in result.unvalued_assets)
    assert balances == original
    ledger.get_open_managed_trades.assert_called_with(venue, strict=True)
    assert not notify.called  # Not a fake failed-account alert.
    assert all(c.args[0] == 'BTC/KRW' for c in exchange.fetch_ticker.call_args_list)


@pytest.mark.parametrize('venue', VENUES)
@pytest.mark.parametrize('failure', ['ticker', 'markets', 'empty_markets', 'bad_market', 'ownership', 'managed', 'suspended', 'nan_balance'])
def test_uncertainty_still_blocks(tmp_path, monkeypatch, venue, failure):
    risk, markets, prices, balances, exchange, ledger, notify = setup(tmp_path, monkeypatch, venue)
    if failure == 'ticker': exchange.fetch_ticker.side_effect = TimeoutError()
    if failure == 'markets': exchange.load_markets.side_effect = TimeoutError()
    if failure == 'empty_markets': markets.clear()
    if failure == 'bad_market': markets['BROKEN'] = {}
    if failure == 'ownership': ledger.get_open_managed_trades.side_effect = sqlite3.OperationalError()
    if failure == 'managed': ledger.get_open_managed_trades.return_value = [{'symbol':'APENFT/KRW', 'execution_mode':'live', 'quantity':100, 'entry_price':1}]
    if failure == 'suspended': markets['BTC/KRW']['active'] = False
    if failure == 'nan_balance': balances['EMC'] = float('nan')
    result = risk.evaluate_daily_loss_limit(venue, execution_mode='live')
    assert result.blocked and result.status == 'risk_data_unavailable'
    assert notify.call_args.args[0] == 'risk_data_unavailable'
    assert not (tmp_path/'risk.db').exists()  # No new denominator from an invalid account.


@pytest.mark.parametrize('venue', VENUES)
def test_non_krw_market_uses_same_venue_conversion_including_managed_pnl(tmp_path, monkeypatch, venue):
    risk, markets, prices, balances, _, ledger, _ = setup(tmp_path, monkeypatch, venue)
    markets['EMC/BTC'] = market('EMC', 'BTC')
    prices['EMC/BTC'] = .000001
    ledger.get_open_managed_trades.return_value = [{'symbol':'EMC/KRW', 'execution_mode':'live', 'quantity':1, 'entry_price':80}]
    result = risk.evaluate_daily_loss_limit(venue, execution_mode='live')
    assert not result.blocked
    assert result.current_equity == pytest.approx(2_000_100)
    assert result.unrealized_pnl == pytest.approx(20)
    assert [v['asset'] for v in result.unvalued_assets] == ['APENFT']


@pytest.mark.parametrize('venue', VENUES)
def test_real_losses_and_daily_basis_survive_residuals_restart_and_changed_prices(tmp_path, monkeypatch, venue):
    risk, _, prices, _, _, ledger, _ = setup(tmp_path, monkeypatch, venue)
    first = risk.evaluate_daily_loss_limit(venue, execution_mode='live')
    ledger.get_daily_actual_trades.return_value = [{'net_pnl':-1_000_000, 'performance_evidence_ready': True}]
    prices['BTC/KRW'] = 200_000_000
    restarted = RiskManager(object(), ledger, risk.settings, risk.exchange_manager)
    result = restarted.evaluate_daily_loss_limit(venue, execution_mode='live')
    assert result.initial_equity == first.initial_equity == 2_000_000
    assert result.loss_rate == 50 and result.blocked
    with sqlite3.connect(ledger.db_path) as conn:
        assert conn.execute('SELECT count(*) FROM daily_risk_basis').fetchone()[0] == 1


@pytest.mark.parametrize('venue', VENUES)
def test_paper_learning_do_not_read_live_account(tmp_path, monkeypatch, venue):
    risk, *rest = setup(tmp_path, monkeypatch, venue)
    for mode in ('paper', 'learning'):
        assert risk.evaluate_daily_loss_limit(venue, execution_mode=mode).status == 'not_applicable'
    risk.exchange_manager.get_exchange_balance.assert_not_called()


def test_catalogue_refresh_failure_never_reuses_success_as_absence(monkeypatch):
    now = [0]
    monkeypatch.setattr('trading.spot_valuation.time.monotonic', lambda: now[0])
    exchange = SimpleNamespace(load_markets=Mock(return_value={'BTC/KRW':market()}), fetch_ticker=Mock())
    store = SpotValuation()
    assert store.values('upbit', exchange, ['OLD'])['OLD']['status'] == 'no_supported_market'
    store.values('upbit', exchange, ['OLD'])
    assert exchange.load_markets.call_count == 1
    now[0] = 301
    exchange.load_markets.side_effect = TimeoutError()
    assert store.values('upbit', exchange, ['OLD'])['OLD']['status'] == 'market_query_failed'
    store.values('upbit', exchange, ['OLD'])
    assert exchange.load_markets.call_count == 2  # Failure backoff too.


@pytest.mark.parametrize('ticker', [{'last': 0}, {'last': float('nan')}, {'last': float('inf')}, {'last': 1, 'timestamp': 1}, None])
def test_bad_ticker_is_not_an_unsupported_asset(ticker):
    exchange = SimpleNamespace(load_markets=lambda **k:{'BTC/KRW':market()}, fetch_ticker=lambda s:ticker)
    result = SpotValuation().values('upbit', exchange, ['BTC'])['BTC']
    assert result['status'] == 'price_query_failed' and result['price'] is None


@pytest.mark.parametrize('mode,blocked', [('paper', False), ('learning', False), ('live_api', True), ('unknown', True)])
def test_unpriced_managed_ownership_is_not_hidden_by_mode(tmp_path, monkeypatch, mode, blocked):
    risk, _, _, _, _, ledger, _ = setup(tmp_path, monkeypatch, 'upbit')
    ledger.get_open_managed_trades.return_value = [{'symbol':'APENFT/KRW', 'execution_mode':mode, 'quantity':100, 'entry_price':1}]
    assert risk.evaluate_daily_loss_limit('upbit', execution_mode='live').blocked is blocked


def test_non_krw_managed_entry_price_is_not_reinterpreted_as_krw(tmp_path, monkeypatch):
    risk, markets, prices, _, _, ledger, _ = setup(tmp_path, monkeypatch, 'upbit')
    markets['EMC/BTC'] = market('EMC', 'BTC')
    prices['EMC/BTC'] = .000001
    ledger.get_open_managed_trades.return_value = [{'symbol':'EMC/BTC', 'execution_mode':'live', 'quantity':1, 'entry_price':.0000008}]
    result = risk.evaluate_daily_loss_limit('upbit', execution_mode='live')
    assert result.blocked and '기준통화' in result.reason


def test_existing_full_account_basis_is_not_reset_to_subset(tmp_path, monkeypatch):
    from datetime import datetime
    from trading.daily_risk_basis import load_or_create, credential_scope
    risk, _, _, _, _, ledger, _ = setup(tmp_path, monkeypatch, 'upbit')
    scope = credential_scope(risk.settings, risk.binance_client, 'upbit')
    load_or_create(ledger.db_path, datetime.now().date().isoformat(), 'upbit', 'KRW', scope, 3_000_000)
    assert risk.evaluate_daily_loss_limit('upbit', execution_mode='live').initial_equity == 3_000_000


def test_cash_only_account_never_needs_price_or_catalogue(tmp_path, monkeypatch):
    risk, _, _, balances, exchange, _, _ = setup(tmp_path, monkeypatch, 'upbit')
    balances.clear()
    balances['KRW'] = 1000
    assert not risk.evaluate_daily_loss_limit('upbit', execution_mode='live').blocked
    exchange.load_markets.assert_not_called()
    exchange.fetch_ticker.assert_not_called()


@pytest.mark.parametrize('venue', VENUES)
def test_unknown_active_flag_can_be_valued_but_is_not_missing_market(tmp_path, monkeypatch, venue):
    risk, markets, _, _, _, _, _ = setup(tmp_path, monkeypatch, venue)
    markets['BTC/KRW']['active'] = None
    result = risk.evaluate_daily_loss_limit(venue, execution_mode='live')
    assert not result.blocked and result.current_equity == 2_000_000
    assert 'BTC' not in [v['asset'] for v in result.unvalued_assets]


def test_installed_coinone_ccxt_market_shape_is_valued():
    import ccxt
    client = ccxt.coinone()
    client.v2PublicGetTickerNewQuoteCurrency = Mock(return_value={
        'result':'success', 'error_code':'0', 'tickers':[
            {'quote_currency':'krw', 'target_currency':'btc', 'last':'100000000'}]})
    rows = client.fetch_markets()
    assert rows[0]['active'] is None
    exchange = SimpleNamespace(load_markets=lambda **k:{m['symbol']:m for m in rows},
                               fetch_ticker=lambda s:{'last':100000000})
    values = SpotValuation().values('coinone', exchange, ['BTC', 'APENFT'])
    assert values['BTC']['status'] == 'priced'
    assert values['APENFT']['status'] == 'no_supported_market'


@pytest.mark.parametrize('venue', VENUES)
def test_candidate_prefilter_rejects_inactive_and_wrong_quote(tmp_path, monkeypatch, venue):
    from trading.unified_trader import UnifiedTrader
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.logger = logging.getLogger('fixture')
    adapter = SimpleNamespace(exchange=SimpleNamespace(markets={
        'BTC/KRW':market(), 'OLD/KRW':market('OLD', active=False), 'EMC/BTC':market('EMC', 'BTC')}))
    trader.unified_manager = SimpleNamespace(get_exchange=lambda *a:adapter)
    rows = [{'symbol':s} for s in ('BTC/KRW', 'OLD/KRW', 'EMC/BTC', 'APENFT/KRW')]
    assert [r['symbol'] for r in trader._prefilter_supported_coins(venue, rows)] == ['BTC/KRW']
