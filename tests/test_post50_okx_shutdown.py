"""Post-50 customer paths: real adapter boundaries, no credentials/network/orders."""
from types import SimpleNamespace
from unittest.mock import Mock
import threading
import pytest

from trading.evaluator import Evaluator
from trading.exchanges.adapters.okx_futures_adapter import OkxFuturesAdapter
from trading.exchanges.adapters.kiwoom_process_proxy import KiwoomProcessProxy
from trading.stock_runtime_controller import StockRuntimeController


def okx_fixture():
    symbol = 'BTC/USDT:USDT'
    market = dict(symbol=symbol, base='BTC', quote='USDT', settle='USDT', active=True,
                  swap=True, contract=True, type='swap')
    ticker = dict(symbol=symbol, last=25000., open=24500., high=26000., low=24000.,
                  quoteVolume=None, baseVolume=2500000., percentage=None,
                  info=dict(instType='SWAP', volCcy24h='1000', vol24h='2500000', open24h='24500'))
    raw = SimpleNamespace(markets={symbol: market}, id='okx')
    raw.load_markets = lambda reload=False: raw.markets
    raw.fetch_tickers = Mock(side_effect=OSError('batch temporarily unavailable'))
    raw.fetch_ticker = Mock(return_value=ticker)
    adapter = OkxFuturesAdapter('', '', '')
    adapter.exchange = raw; adapter.is_connected = True
    analyzer = SimpleNamespace(settings={}, binance_client=None)
    evaluator = Evaluator(analyzer=analyzer, recorder=None, settings={
        'futures_selection': {'okx': {'min_quote_volume': 15000000, 'volatility_max': 25}}})
    evaluator._set_selection_context('okx', adapter)
    return evaluator, adapter, ticker


def test_okx_batch_failure_single_ticker_fallback_keeps_turnover_evidence():
    evaluator, adapter, _ = okx_fixture()
    rows = evaluator._analyze_candidate_coins_ccxt_futures(adapter)
    assert len(rows) == 1
    assert rows[0]['quoteVolume'] == 25000000
    assert rows[0]['priceChangePercent'] == pytest.approx(2.0408163265)


def test_batch_signature_retry_failure_still_reaches_single_ticker_fallback():
    evaluator, adapter, _ = okx_fixture()
    adapter.exchange.fetch_tickers.side_effect = [TypeError('symbol argument unsupported'), OSError('batch temporarily unavailable')]
    rows = evaluator._analyze_candidate_coins_ccxt_futures(adapter)
    assert len(rows) == 1
    assert rows[0]['quoteVolume'] == 25000000
    assert adapter.exchange.fetch_tickers.call_count == 2


def test_missing_ticker_never_becomes_a_zero_price_candidate():
    evaluator, adapter, _ = okx_fixture()
    evaluator.settings['futures_selection']['okx']['min_quote_volume'] = 0
    adapter.exchange.fetch_ticker.return_value = {}
    assert evaluator._analyze_candidate_coins_ccxt_futures(adapter) == []
    assert evaluator.candidate_failure_by_exchange['okx'] == 'trading_candidate_tickers_unavailable'


def test_liquidity_filter_stays_enforced_and_has_distinct_reason():
    evaluator, adapter, _ = okx_fixture()
    evaluator.settings['futures_selection']['okx']['min_quote_volume'] = 100000000
    assert evaluator._analyze_candidate_coins_ccxt_futures(adapter) == []
    assert evaluator.candidate_failure_by_exchange['okx'] == 'trading_candidate_filters_excluded'


def test_inactive_instruments_are_not_reintroduced_by_ticker_recovery():
    evaluator, adapter, _ = okx_fixture()
    adapter.exchange.markets['BTC/USDT:USDT']['active'] = False
    assert evaluator._analyze_candidate_coins_ccxt_futures(adapter) == []
    assert evaluator.candidate_failure_by_exchange['okx'] == 'trading_candidate_markets_unavailable'
    adapter.exchange.fetch_ticker.assert_not_called()


def test_candidate_failure_reaches_customer_venue_audit_without_raw_ticker(monkeypatch):
    from log_system import log_adapter
    record = Mock()
    monkeypatch.setattr(log_adapter, 'log_event', record)
    evaluator, adapter, _ = okx_fixture()
    evaluator.settings['futures_selection']['okx']['min_quote_volume'] = 100000000
    assert evaluator._analyze_candidate_coins_ccxt_futures(adapter) == []
    payload = record.call_args.kwargs
    assert payload['exchange'] == 'okx'
    assert payload['details'] == dict(reason_code='trading_candidate_filters_excluded',
        failure_stage='candidate_selection', market_count=1, candidate_count=1, valid_ticker_count=1, passed_count=0)
    assert 'BTC' not in record.call_args.args[1]


@pytest.mark.parametrize('method', ['get', 'post'])
def test_kis_transport_error_does_not_log_account_query_or_credentials(method):
    from trading.exchanges.adapters.korea_investment_stock_adapter import KoreaInvestmentStockAdapter
    from requests.exceptions import SSLError
    adapter = KoreaInvestmentStockAdapter('fixture', 'fixture', account_no='1234567801')
    http = Mock()
    getattr(http, method).side_effect = SSLError('https://fixture?CANO=12345678&appsecret=private-fixture')
    adapter._get_http = lambda: http
    adapter._tr_id = lambda *args, **kwargs: 'fixture'
    adapter._ensure_token = lambda: True
    adapter._request_headers = lambda *args, **kwargs: {}
    adapter._access_token = 'private-token'
    adapter.log_event = Mock()
    assert getattr(adapter, '_' + method)('/fixture') == {}
    message = adapter.log_event.call_args.args[1]
    assert 'SSLError' in message
    assert all(value not in message for value in ['12345678', 'private-fixture', 'private-token', 'CANO'])


def test_stock_stop_signals_read_cancellation_before_waiting_for_worker():
    controller = StockRuntimeController(settings_provider=lambda: {})
    released = threading.Event()
    adapter = SimpleNamespace(request_stop=released.set, disconnect=lambda: True)
    controller._adapters['kiwoom'] = adapter
    controller._events['kiwoom'] = threading.Event()
    worker = threading.Thread(target=lambda: released.wait(2))
    controller._threads['kiwoom'] = worker
    worker.start()
    try:
        controller.request_stop('kiwoom')
        assert released.is_set(), 'cancellation must precede join'
        assert controller.wait_for_stops(['kiwoom'], timeout=.5)['alive'] == []
    finally:
        released.set(); worker.join(2)


def test_proxy_stop_interrupts_read_without_restarting_host():
    proxy = KiwoomProcessProxy('fixture', '', '')
    entered = threading.Event(); stopped = threading.Event()
    proxy._ensure_process = Mock()
    proxy._shutdown_process = Mock(return_value=True)
    def poll(timeout):
        entered.set(); stopped.wait(min(timeout, .2)); return False
    proxy._connection = Mock(poll=poll)
    failures = []
    def run():
        try: proxy._call('get_stock_list', timeout=120)
        except Exception as exc: failures.append(str(exc))
    worker = threading.Thread(target=run, daemon=True); worker.start()
    try:
        assert entered.wait(1)
        proxy.request_stop(); stopped.set(); worker.join(1)
        assert not worker.is_alive()
        assert failures and 'kiwoom_runtime_stopping' in failures[0]
        with pytest.raises(RuntimeError, match='kiwoom_runtime_stopping'):
            proxy._call('get_balance')
        assert proxy._ensure_process.call_count == 1
    finally:
        stopped.set()


def test_proxy_stop_does_not_discard_a_sent_order_reply():
    proxy = KiwoomProcessProxy('fixture', '', '')
    proxy._ensure_process = Mock()
    proxy._shutdown_process = Mock(return_value=True)
    def poll(timeout):
        proxy.request_stop()
        return True
    proxy._connection = Mock(poll=poll)
    proxy._connection.recv.return_value = (1, True, {'order_id': 'fixture'})
    assert proxy._call('place_order') == {'order_id': 'fixture'}
    assert not proxy._order_outcome_unknown
    proxy._shutdown_process.assert_not_called()
    with pytest.raises(RuntimeError, match='kiwoom_runtime_stopping'):
        proxy._call('place_order')
    assert proxy._connection.send.call_count == 1


def test_stopped_stock_cycle_cannot_create_or_reconnect_an_adapter():
    factory = Mock()
    controller = StockRuntimeController(settings_provider=lambda: {}, adapter_factory=factory)
    event = controller._events['kiwoom'] = threading.Event(); event.set()
    with pytest.raises(RuntimeError, match='stock_runtime_stopping'):
        controller._run_once('kiwoom')
    factory.assert_not_called()


@pytest.mark.parametrize('suffix', ['catalogue_unavailable', 'markets_unavailable', 'tickers_unavailable', 'filters_excluded'])
def test_start_preserves_candidate_failure_subreason(suffix):
    from trading.unified_trader import UnifiedTrader
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.logger = Mock(); trader.settings = {}
    trader.monitoring_flags = {}; trader.monitoring_threads = {}; trader.trading_cycles = {}
    trader.selected_coins = {}; trader.last_market_regime_by_exchange = {}
    trader._is_trade_enabled = lambda _: True; trader._is_learning_enabled = lambda _: False
    trader._ensure_exchange_initialized = lambda _: True
    trader._evaluate_current_market_conditions_unified_fast = lambda *args: 'normal'
    trader._regime_stabilizer = SimpleNamespace(observe=lambda *args, **kwargs: ('normal', {}))
    trader.select_trading_coins_unified = lambda _: []
    reason = 'trading_candidate_' + suffix
    trader.evaluator = SimpleNamespace(candidate_failure_by_exchange={'okx': reason})
    with pytest.raises(RuntimeError, match=reason + ':okx:candidate_selection'):
        trader.start_trading_checked('okx')
