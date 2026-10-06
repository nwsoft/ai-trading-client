from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from trading.exchanges.balance_normalizer import normalize_ccxt_available_funds
from trading.portfolio_orchestrator import live_crypto_available_funds
from trading.exchanges.adapters.upbit_spot_adapter import UpbitSpotAdapter
from trading.exchanges.adapters.bithumb_spot_adapter import BithumbSpotAdapter
from trading.exchanges.adapters.coinone_spot_adapter import CoinoneSpotAdapter
from trading.exchanges.adapters.bybit_futures_adapter import BybitFuturesAdapter
from trading.exchanges.adapters.okx_futures_adapter import OkxFuturesAdapter
from trading.exchanges.adapters.bitget_futures_adapter import BitgetFuturesAdapter


ADAPTERS = [('upbit', UpbitSpotAdapter, 'KRW'), ('bithumb', BithumbSpotAdapter, 'KRW'),
            ('coinone', CoinoneSpotAdapter, 'KRW'), ('bybit', BybitFuturesAdapter, 'USDT'),
            ('okx', OkxFuturesAdapter, 'USDT'), ('bitget', BitgetFuturesAdapter, 'USDT')]


@pytest.mark.parametrize('venue,cls,quote', ADAPTERS)
@pytest.mark.parametrize('free', [0, 120])
def test_real_adapter_contract_uses_provider_free_not_legacy_total(venue, cls, quote, free, tmp_path):
    from trading.unified_trader import UnifiedTrader
    from trading.execution_mode import ExecutionMode
    adapter = cls.__new__(cls)
    adapter.api_key = adapter.secret_key = 'fixture-not-real'
    adapter.is_connected = True
    adapter.exchange = SimpleNamespace(fetch_balance=Mock(return_value={
        quote: {'free': free, 'total': 999999, 'used': 200}, 'free': {quote: free}, 'total': {quote: 999999}}))
    adapter.get_balance = Mock(side_effect=AssertionError('total display is not available funds'))
    adapter.place_order = Mock(side_effect=AssertionError('read must not order'))
    engine = UnifiedTrader.__new__(UnifiedTrader)
    engine.settings = {}
    engine.recorder = SimpleNamespace(db_path=str(tmp_path / 'ledger.db'))
    engine._execution_mode = lambda source: ExecutionMode.LIVE
    engine.get_exchange_client = lambda source: adapter
    result = engine._build_portfolio_allocation_unified(venue, [{'symbol': 'QA'}],
        {'QA': {'confidence': .8}}, {'portfolio_orchestration': {'enabled': True}})
    assert result['available_capital'] == free
    assert result['capital_basis'] != 'available_balance_unverified'
    adapter.exchange.fetch_balance.assert_called_once_with()
    adapter.get_balance.assert_not_called()
    adapter.place_order.assert_not_called()


@pytest.mark.parametrize('snapshot', [
    {'total': {'USDT': 999999}}, {'USDT': {'total': 999999}},
    {'free': {'KRW': 50000}}, {'free': {'USDT': None}},
    {'USDT': {'free': float('nan')}}, {'USDT': {'free': -1}},
    {'USDT': {'free': True}}, {'USDT': {'free': 100}, 'free': {'USDT': 120}},
    {'status': 'error', 'free': {'USDT': 999999}},
])
def test_missing_invalid_wrong_currency_or_conflicting_free_is_unknown(snapshot):
    result = normalize_ccxt_available_funds(snapshot, quote_asset='USDT')
    assert result['status'] == 'error' and 'available_balance' not in result


def test_typed_provider_failure_cannot_restore_a_total_or_retry_another_balance_contract():
    adapter = SimpleNamespace(get_available_funds_result=Mock(side_effect=TimeoutError('private')),
        get_balance=Mock(return_value={'available_balance': 999999}))
    assert live_crypto_available_funds(adapter, 'USDT') == (0, 'available_balance_unverified')
    adapter.get_available_funds_result.assert_called_once_with(quote_currency='USDT')
    adapter.get_balance.assert_not_called()


def test_unconfigured_or_disconnected_adapter_does_not_read_private_balance():
    adapter = UpbitSpotAdapter.__new__(UpbitSpotAdapter)
    adapter.is_connected = True
    adapter.api_key = adapter.secret_key = ''
    adapter.exchange = SimpleNamespace(fetch_balance=Mock())
    assert adapter.get_available_funds_result('KRW')['status'] == 'unavailable'
    adapter.exchange.fetch_balance.assert_not_called()
