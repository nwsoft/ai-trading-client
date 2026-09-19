from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock
import threading

import pytest

from trading.market_data_utils import failed_candles, optional_market_number
from trading.unified_trader import UnifiedTrader
from trading.trader import Trader
from trading.stock_analysis_service import detect_market_regime
from trading.exchanges.adapters.mirae_asset_stock_adapter import MiraeAssetStockAdapter
from trading.exchanges.adapters.korea_investment_stock_adapter import KoreaInvestmentStockAdapter
from trading.exchanges.adapters.shinhan_stock_adapter import ShinhanStockAdapter
from trading.exchanges.adapters.kiwoom_stock_adapter import KiwoomStockAdapter
from trading.exchanges.adapters.coinone_spot_adapter import CoinoneSpotAdapter
from trading.exchange_manager import ExchangeManager


def trader_for(venue, getter):
    trader = object.__new__(Trader if venue == 'binance' else UnifiedTrader)
    trader.settings = {'market_regime_check_interval_seconds': 3600}
    trader.logger = Mock(); trader.log_event = Mock()
    trader.exchange_manager = SimpleNamespace(get_klines=getter)
    trader.binance_client = trader.exchange_manager
    return trader


def candles():
    return [[i * 900_000, 100, 104, 99, 100, 10] for i in range(20)]


@pytest.mark.parametrize('venue', ['upbit', 'bithumb', 'coinone', 'bybit', 'bitget', 'okx'])
def test_failure_recovery_does_not_wait_for_one_hour_normal_cache(venue, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('trading.unified_trader.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('trading.runtime_observability.emit_runtime_status', Mock())
    get = Mock(side_effect=[failed_candles('candle_query_failed', TimeoutError('private-url')), candles()])
    trader = trader_for(venue, get)
    assert trader._evaluate_current_market_conditions_unified_fast(venue, 'BTCUSDT') == 'unknown'
    assert trader._market_observation_detail[venue]['error_type'] == 'TimeoutError'
    assert 'private-url' not in str(trader._market_observation_detail)
    clock[0] += 29
    assert trader._evaluate_current_market_conditions_unified_fast(venue, 'BTCUSDT') == 'unknown'
    assert get.call_count == 1
    clock[0] += 2
    assert trader._evaluate_current_market_conditions_unified_fast(venue, 'BTCUSDT') == 'normal'
    assert not trader._market_data_unavailable[venue]
    assert get.call_count == 2


def test_concurrent_refresh_joins_request_instead_of_false_missing(monkeypatch):
    monkeypatch.setattr('trading.runtime_observability.emit_runtime_status', Mock())
    entered, release = threading.Event(), threading.Event()
    def get(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return candles()
    get = Mock(side_effect=get)
    trader = trader_for('okx', get)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(trader._evaluate_current_market_conditions_unified_fast, 'okx', 'BTCUSDT')
        assert entered.wait(3)
        second = pool.submit(trader._evaluate_current_market_conditions_unified_fast, 'okx', 'BTCUSDT')
        release.set()
        assert first.result(3) == second.result(3) == 'normal'
    assert get.call_count == 1
    assert not trader._market_data_unavailable['okx']


@pytest.mark.parametrize('venue', ['binance', 'upbit', 'bithumb', 'coinone', 'bybit', 'bitget', 'okx'])
def test_thirty_minute_change_uses_two_fifteen_minute_steps(venue, monkeypatch):
    monkeypatch.setattr('trading.runtime_observability.emit_runtime_status', Mock())
    rows = candles()
    rows[-2][4] = 101.5
    rows[-1][4] = 103
    trader = trader_for(venue, lambda *a, **kw: rows)
    result = (trader._analyze_market_regime_binance_fast() if venue == 'binance'
              else trader._evaluate_current_market_conditions_unified_fast(venue, 'BTCUSDT'))
    assert result == 'volatile'


@pytest.mark.parametrize('adapter_class', [MiraeAssetStockAdapter, KoreaInvestmentStockAdapter, ShinhanStockAdapter, KiwoomStockAdapter])
def test_broker_missing_change_is_not_zero_or_range(adapter_class):
    adapter = object.__new__(adapter_class)
    adapter.is_connected = True
    adapter.log_event = Mock()
    adapter._normalize_symbol = lambda x: x
    # Data source supplies a price but omits the change-rate field.
    adapter._get = Mock(return_value={'current_price': 70000})
    adapter._call_block_request = Mock(return_value={'현재가': '70000'})
    if isinstance(adapter, KiwoomStockAdapter):
        adapter._basic_info_cache = {}  # fixture bypasses __init__
    adapter._extract_first_record = lambda x: x
    result = adapter.get_realtime_price('005930')
    assert result['change_rate'] is None
    assert detect_market_regime(adapter) == 'unknown'
    # Explicit 0% is valid, including when an alternative key has a different value.
    adapter._get = Mock(return_value={'current_price': 70000, 'prdy_ctrt': 0, 'change_rate': 8})
    adapter._call_block_request = Mock(return_value={'현재가': '70000', '등락율': '0'})
    if isinstance(adapter, KiwoomStockAdapter):
        adapter._basic_info_cache.clear()  # start a new market-data fixture
    assert adapter.get_realtime_price('005930')['change_rate'] == 0
    assert detect_market_regime(adapter) == 'range'


def test_invalid_index_response_does_not_hide_valid_proxy_quote():
    adapter = SimpleNamespace(get_index_price=lambda *a: {'status': 'error'},
                              get_realtime_price=lambda *a: {'status': 'ok', 'change_rate': 2})
    assert detect_market_regime(adapter) == 'bull'


def test_optional_market_number_preserves_missing_and_explicit_zero():
    assert optional_market_number(None, '', 'NaN') is None
    assert optional_market_number(0, 3) == 0
    assert optional_market_number('-1.5%') == -1.5


@pytest.mark.parametrize('venue', ['upbit', 'bithumb', 'bybit', 'bitget', 'okx'])
def test_candle_manager_retains_failure_without_repeating_catalog_query(venue):
    ccxt = SimpleNamespace(markets={}, load_markets=Mock(side_effect=TimeoutError('private-api-url')),
                           fetch_ohlcv=Mock())
    manager = object.__new__(ExchangeManager)
    manager.settings = {}; manager.logger = Mock()
    manager._is_exchange_enabled = lambda *a: True
    manager._get_or_create_exchange_client = lambda *a: SimpleNamespace(exchange=ccxt)
    rows = manager.get_klines('BTCUSDT', '15m', 20, venue)
    assert rows == [] and rows.reason == 'market_catalog_query_failed'
    assert rows.error_type == 'TimeoutError'
    ccxt.fetch_ohlcv.assert_not_called()


def test_coinone_native_candles_match_chronological_runtime_contract(monkeypatch):
    adapter = object.__new__(CoinoneSpotAdapter)
    adapter.exchange = None
    payload = {'result': 'success', 'error_code': '0', 'chart': [
        {'timestamp': ts, 'open': price, 'high': price+1, 'low': price-1, 'close': price, 'target_volume': 2}
        for ts, price in [(2_700_000, 103), (1_800_000, 102), (900_000, 101)]
    ]}
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    monkeypatch.setattr('requests.get', Mock(return_value=response))
    rows = adapter.get_klines('BTC/KRW', '15m', 2)
    assert [r[0] for r in rows] == [1_800_000, 2_700_000]
    assert [r[4] for r in rows] == [102, 103]
    payload['result'] = 'error'; payload['error_code'] = '123'
    rows = adapter.get_klines('BTC/KRW', '15m', 2)
    assert not rows and rows.reason == 'coinone_chart_api_rejected'


def test_coinone_failure_does_not_fall_through_to_unsupported_ccxt():
    ccxt = SimpleNamespace(fetch_ohlcv=Mock())
    client = SimpleNamespace(get_klines=Mock(return_value=failed_candles('coinone_chart_query_failed')),
                             exchange=ccxt)
    manager = object.__new__(ExchangeManager)
    manager.settings = {}; manager.logger = Mock()
    manager._is_exchange_enabled = lambda *a: True
    manager._get_or_create_exchange_client = lambda *a: client
    rows = manager.get_klines('BTCUSDT', '15m', 20, 'coinone')
    assert not rows and rows.reason == 'coinone_chart_query_failed'
    ccxt.fetch_ohlcv.assert_not_called()
