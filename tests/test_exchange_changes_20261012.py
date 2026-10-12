"""Official October exchange changes and submission boundaries. No external orders."""
import logging
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace
import pytest
from api.binance_client import BinanceClient
from trading.opportunity_coordinator import OpportunityCoordinator
from trading.execution_optimizer import ExecutionOptimizer


def native_client():
    c = BinanceClient.__new__(BinanceClient)
    c.logger = logging.getLogger('exchange-test')
    c._has_api_keys = lambda: True
    c.get_synced_timestamp = lambda: 1
    c.get_symbol_filters = lambda _: {'stepSize': .001, 'minQty': .001}
    calls = []
    def submit(**params):
        calls.append(params)
        return {'status': 'NEW', 'orderId': 1}
    c.client = SimpleNamespace(futures_exchange_info=lambda: {'symbols': [
        {'symbol': 'BTCUSDT', 'quantityPrecision': 3}]}, futures_create_order=submit)
    return c, calls


@pytest.mark.parametrize('quantity,expected', [(.0019, '.001'), (.001, '.001')])
def test_reduce_only_quantity_never_exceeds_requested_residual(quantity, expected):
    c, calls = native_client()
    result = BinanceClient.place_futures_order.__wrapped__(c, 'BTCUSDT', 'SELL',
        quantity=quantity, reduce_only=True, client_order_id='residual-1')
    assert result['status'] == 'PENDING'
    assert Decimal(calls[0]['quantity']) == Decimal(expected)
    assert calls[0]['reduceOnly'] == 'true'


def test_sub_step_residual_is_not_inflated_into_minimum_order():
    c, calls = native_client()
    result = BinanceClient.place_futures_order.__wrapped__(c, 'BTCUSDT', 'SELL',
        quantity=.0005, reduce_only=True)
    assert result['status'] == 'REJECTED' and not calls
    assert result['reconciliation_required'] is False


def test_hedge_explicit_reduce_only_is_rejected_before_submission():
    c, calls = native_client()
    result = BinanceClient.place_futures_order.__wrapped__(c, 'BTCUSDT', 'SELL',
        quantity=.001, reduce_only=True, position_side='LONG')
    assert result['status'] == 'REJECTED' and not calls


def test_algo_submission_keeps_client_identity_on_lost_response():
    c, _ = native_client()
    calls = []
    def submit(path, params):
        calls.append((path, params))
        raise TimeoutError('do not expose account details')
    c._post_futures_signed = submit
    result = BinanceClient.place_futures_order.__wrapped__(c, 'BTCUSDT', 'SELL',
        order_type='STOP_MARKET', stop_price=100, close_position=True,
        client_order_id='stable-protection-1')
    assert calls[0][0] == '/fapi/v1/algoOrder'
    assert calls[0][1]['clientAlgoId'] == 'stable-protection-1'
    assert 'newClientOrderId' not in calls[0][1]
    assert result['status'] == 'UNKNOWN' and result['reconciliation_required']
    assert len(calls) == 1 and 'account details' not in str(result)


def authorize(c, version, **changes):
    args = dict(policy={'authorized_targets': ['okx']}, asset_class='crypto', target='okx',
        symbol='BTCUSDT', direction='LONG', quantity=1., price=100., stop_fraction=.01,
        strategy_version=version, account_scope='test:live', signal_time=1800.)
    args.update(changes)
    return c.authorize(**args)


def test_reserved_entries_from_distinct_strategies_cannot_race(tmp_path):
    path = tmp_path / 'coordinator.json'
    a, b = OpportunityCoordinator(storage_path=path), OpportunityCoordinator(storage_path=path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: authorize(*item), [(a, 'v1'), (b, 'v2')]))
    assert sum(r.allowed for r in results) == 1
    assert any(r.reason == 'previous_order_reconciliation_required' for r in results)
    winner = next(r for r in results if r.allowed)
    a.release(winner)
    assert authorize(b, 'v3').allowed


def test_reservation_scope_does_not_block_other_wallet_mode_or_instrument():
    c = OpportunityCoordinator()
    assert authorize(c, 'v1').allowed
    assert authorize(c, 'v2', account_scope='other:live').allowed
    assert authorize(c, 'v2', account_scope='test:paper').allowed
    assert authorize(c, 'v2', symbol='ETHUSDT').allowed
    # Confirmed terminal entry does not create a standing prohibition on hedging.
    first = OpportunityCoordinator()
    claim = authorize(first, 'v1')
    first.record_result(claim, status='filled', order_id='filled-1')
    first.release(claim)
    assert authorize(first, 'v2', direction='SHORT').allowed


@pytest.mark.parametrize('message', ['HTTP 429 too many requests', 'minimum notional not met',
    'unauthorized API key', 'APIError(code=-5047): The original order is not a reduce-only order'])
def test_rejected_request_does_not_burst_retry_or_switch_to_market(message):
    calls = []
    def place(kind, price):
        calls.append(kind)
        return False, {'status': 'REJECTED', 'error': message}, [message]
    result = ExecutionOptimizer().execute_with_quality_control(place, order_type='LIMIT',
        request_price=100., fallback_market=True, max_retries=5, timeout_ms=3000,
        max_slippage_bps=10.)
    assert not result[0] and calls == ['LIMIT']
    if '429' in message:
        assert result[1]['retry_after_seconds'] >= 30


@pytest.mark.parametrize('tags', [None, [], ['ST'], ['ST', 'FUTURE_UNKNOWN']])
@pytest.mark.parametrize('category', ['linear', 'inverse'])
def test_bybit_tags_tolerated_by_installed_ccxt_parser(tags, category):
    import ccxt
    from trading.exchanges.adapters.bybit_futures_adapter import BybitFuturesAdapter
    e = ccxt.bybit({'options': {'usePrivateInstrumentsInfo': False}})
    raw = dict(symbol='BTCUSDT' if category == 'linear' else 'BTCUSD', baseCoin='BTC',
        quoteCoin='USDT' if category == 'linear' else 'USD',
        settleCoin='USDT' if category == 'linear' else 'BTC',
        contractType='LinearPerpetual' if category == 'linear' else 'InversePerpetual',
        status='Trading', lotSizeFilter={'qtyStep': '.001', 'minOrderQty': '.001'},
        priceFilter={'tickSize': '.1'}, leverageFilter={})
    if tags is not None: raw['tags'] = tags
    e.publicGetV5MarketInstrumentsInfo = lambda p: {'result': {'list': [] if p.get('status') else [raw]}}
    # Product actually calls linear; inverse additionally verifies the SDK contract.
    rows = e.fetch_future_markets({'category': category})
    assert len(rows) == 1 and rows[0]['active']
    assert rows[0]['info'].get('tags') == tags
    assert rows[0]['precision']['price'] == .1
    assert rows[0]['limits']['amount']['min'] == .001
    if category == 'linear':
        a = BybitFuturesAdapter('', ''); a.exchange = e
        result = a.load_instrument_catalogue()
        assert result['BTC/USDT:USDT']['active']
        assert result['BTC/USDT:USDT']['info'].get('tags') == tags


@pytest.mark.parametrize('code,status', [(-1007, 'UNKNOWN'), (-1, 'UNKNOWN'),
    (-4164, 'REJECTED'), (-5047, 'REJECTED'), (-1003, 'UNKNOWN')])
def test_algo_error_dict_preserves_uncertainty_without_blind_retry(code, status):
    c, _ = native_client()
    calls = []
    def submit(path, params):
        calls.append(params)
        return {'code': code, 'msg': 'private response must not escape'}
    c._post_futures_signed = submit
    result = BinanceClient.place_futures_order.__wrapped__(c, 'BTCUSDT', 'SELL',
        order_type='STOP_MARKET', stop_price=100, close_position=True,
        client_order_id='stable-protection-2')
    assert result['status'] == status and len(calls) == 1
    assert result['reconciliation_required'] == (status == 'UNKNOWN')
    assert 'private response' not in str(result)


def test_entry_rounding_and_close_all_semantics_remain_separate():
    c, calls = native_client()
    BinanceClient.place_futures_order.__wrapped__(c, 'BTCUSDT', 'BUY', quantity=.0019)
    assert Decimal(calls[0]['quantity']) == Decimal('.002')
    algo = []
    c._post_futures_signed = lambda path, params: (algo.append(params) or {'algoId': 2})
    result = BinanceClient.place_futures_order.__wrapped__(c, 'BTCUSDT', 'SELL',
        order_type='STOP_MARKET', stop_price=100, close_position=True)
    assert result['status'] == 'PENDING'
    assert algo[0]['closePosition'] is True
    assert 'quantity' not in algo[0] and 'reduceOnly' not in algo[0]


def test_signed_post_debug_does_not_log_query_or_signature(caplog, monkeypatch):
    c, _ = native_client()
    c.config = SimpleNamespace(recv_window=5000, api_key='synthetic-test-key', timeout=1)
    c._should_log_debug = lambda: True
    c._build_signed_query = lambda _: ('clientAlgoId=synthetic-private-command', 'synthetic-signature')
    c._futures_base_url = lambda: 'https://example.invalid'
    monkeypatch.setattr('api.binance_client.requests.post',
        lambda *a, **k: SimpleNamespace(json=lambda: {'algoId': 2}))
    with caplog.at_level(logging.DEBUG):
        c._post_futures_signed('/fapi/v1/algoOrder', {})
    assert '/fapi/v1/algoOrder' in caplog.text
    assert all(value not in caplog.text for value in ['synthetic-test-key',
        'synthetic-private-command', 'synthetic-signature'])


@pytest.mark.parametrize('reconcile,retry_at,now,blocked', [
    (False, 1030., 1029., True), (False, 1030., 1030., False),
    (True, 1030., 2000., True), (None, 1030., 2000., True),
    (False, None, 2000., True), (False, float('nan'), 2000., True)])
def test_only_proven_rate_rejection_can_expire_entry_pause(reconcile, retry_at, now, blocked):
    from trading.unified_trader import UnifiedTrader
    t = UnifiedTrader.__new__(UnifiedTrader)
    t._entry_halts = {'bybit': {'category': 'rate_limit', 'retry_at': retry_at,
        'reconciliation_required': reconcile}, 'okx': {'category': 'ambiguous_transport'}}
    assert bool(t._active_entry_halt('bybit', now)) == blocked
    assert t._active_entry_halt('okx', now)['category'] == 'ambiguous_transport'


@pytest.mark.parametrize('message,receipt', [
    ('HTTP 429', {'status':'REJECTED', 'reconciliation_required':True}),
    ('connection timeout', {'status':'REJECTED'}),
    ('503 server error', {'status':'REJECTED'})])
def test_uncertain_receipt_never_becomes_retryable_rejection(message, receipt):
    calls=[]
    def place(*_):
        calls.append(1)
        return False, {**receipt, 'error':message}, [message]
    ok, result, *_ = ExecutionOptimizer().execute_with_quality_control(place,
        order_type='LIMIT', request_price=100., fallback_market=True,
        max_retries=3, timeout_ms=3000, max_slippage_bps=10.)
    assert not ok and len(calls)==1
    assert result['submission_state']=='unknown' and result['reconciliation_required']
