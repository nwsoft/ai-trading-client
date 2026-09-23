"""Regression boundaries: fake transports only, production writers and readers."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import sqlite3

import pytest

from trading.execution_mode import ExecutionMode
from trading.exchanges.venue_capabilities import CRYPTO_VENUE_ORDER
from trading.protection_snapshot import assess_protection, ccxt_protection_orders
from trading.unified_trader import UnifiedTrader
from trading.unified_trading_manager import UnifiedTradingManager
from web_platform.runtime_bridge import HeadlessRuntimeBridge


def ccxt_contract_market():
    return {'id': 'BTCUSDT', 'symbol': 'BTC/USDT:USDT', 'base': 'BTC', 'quote': 'USDT',
            'baseId': 'BTC', 'quoteId': 'USDT', 'settle': 'USDT', 'settleId': 'USDT',
            'type': 'swap', 'spot': False, 'contract': True, 'swap': True, 'future': False,
            'option': False, 'linear': True, 'inverse': False, 'active': True,
            'contractSize': 1, 'precision': {'amount': 0.001, 'price': 0.01},
            'limits': {'amount': {'min': 0.001}, 'price': {}, 'cost': {}}, 'info': {}}


@pytest.mark.parametrize('side,index', [('LONG', 0), ('LONG', 1), ('SHORT', 0), ('SHORT', 2)])
def test_bybit_protection_actual_ccxt_routes_only_to_position_stop(side, index):
    import ccxt
    from trading.exchanges.adapters.bybit_futures_adapter import BybitFuturesAdapter
    exchange = ccxt.bybit()
    market = ccxt_contract_market()
    exchange.set_markets([market])
    exchange.is_unified_enabled = lambda: [True, True]
    exchange.fetch_positions = Mock(return_value=[{'symbol': market['symbol'], 'side': side.lower(),
                                                  'contracts': 1, 'info': {'positionIdx': index}}])
    exchange.privatePostV5PositionTradingStop = Mock(return_value={'retCode': 0, 'result': {}})
    exchange.privatePostV5OrderCreate = Mock(side_effect=AssertionError('ordinary order forbidden'))
    adapter = BybitFuturesAdapter('', '')
    adapter.exchange, adapter.is_connected = exchange, True
    result = adapter.place_insurance_tp_sl('BTC/USDT:USDT', side, 110, 90, quantity=1)
    assert result['status'] == 'success', result
    exchange.privatePostV5OrderCreate.assert_not_called()
    request = exchange.privatePostV5PositionTradingStop.call_args.args[0]
    assert request['positionIdx'] == index
    assert request['takeProfit'] == '110' and request['stopLoss'] == '90'
    assert request['tpSize'] == request['slSize'] == '1'
    assert request['tpslMode'] == 'Partial'
    assert request['tpTriggerBy'] == request['slTriggerBy'] == 'MarkPrice'
    assert 'side' not in request and 'orderType' not in request


def test_bybit_missing_position_does_not_guess_quantity_or_place_order():
    from trading.exchanges.adapters.bybit_futures_adapter import BybitFuturesAdapter
    adapter = BybitFuturesAdapter('', '')
    adapter.is_connected = True
    adapter.exchange = SimpleNamespace(fetch_positions=Mock(return_value=[]), create_order=Mock())
    adapter._normalize_symbol = lambda s: s
    result = adapter.place_insurance_tp_sl('BTCUSDT', 'LONG', 110, 90, quantity=1)
    assert result['status'] == 'error'
    adapter.exchange.create_order.assert_not_called()


def test_okx_protection_actual_ccxt_routes_to_oco():
    import ccxt
    from trading.exchanges.adapters.okx_futures_adapter import OkxFuturesAdapter
    exchange = ccxt.okx()
    market = ccxt_contract_market()
    market['id'] = 'BTC-USDT-SWAP'
    exchange.set_markets([market])
    exchange.privatePostTradeOrderAlgo = Mock(return_value={'code': '0', 'data': [{'algoId': 'pair', 'sCode': '0'}]})
    exchange.privatePostTradeOrder = Mock(side_effect=AssertionError('ordinary order forbidden'))
    exchange.privatePostTradeBatchOrders = Mock(side_effect=AssertionError('ordinary orders forbidden'))
    adapter = OkxFuturesAdapter('', '', '')
    adapter.exchange, adapter.is_connected = exchange, True
    adapter._detect_position_mode = lambda: 'hedge'
    result = adapter.place_insurance_tp_sl('BTC/USDT:USDT', 'LONG', 110, 90, quantity=1)
    assert result['status'] == 'success', result
    request = exchange.privatePostTradeOrderAlgo.call_args.args[0]
    assert request['ordType'] == 'oco'
    assert float(request['tpTriggerPx']) == 110 and float(request['slTriggerPx']) == 90
    assert request['posSide'] == 'long' and request['side'] == 'sell'


@pytest.mark.parametrize('responses,expected', [([{'id': 'tp'}, {'id': 'sl'}], 'success'),
                                             ([{}, {'id': 'sl'}], 'partial'), ([{}, {}], 'error')])
def test_bitget_needs_both_accepted_protection_legs(responses, expected):
    from trading.exchanges.adapters.bitget_futures_adapter import BitgetFuturesAdapter
    adapter = BitgetFuturesAdapter('', '', '')
    adapter.is_connected = True
    adapter.exchange = SimpleNamespace(create_order=Mock(side_effect=responses))
    adapter._normalize_symbol = lambda s: s
    adapter._round_price = lambda s, p: p
    adapter._round_amount = lambda s, a: a
    result = adapter.place_insurance_tp_sl('BTCUSDT', 'LONG', 110, 90, quantity=1)
    assert result['status'] == expected
    for call in adapter.exchange.create_order.call_args_list:
        assert call.kwargs['params']['triggerType'] == 'mark_price'


@pytest.mark.parametrize('scenario', ['verified', 'partial', 'query_failed', 'empty'])
def test_binance_watchdog_never_resubmits_after_partial_or_failed_read(scenario):
    from trading.trader import Trader
    from trading.position_ownership import NOAH_POSITION_OWNER
    trader = object.__new__(Trader)
    trader._execution_mode = lambda: ExecutionMode.LIVE
    trader.log_event = Mock()
    trader._place_owned_binance_protection = Mock()
    tp, sl = order('TAKE_PROFIT_MARKET', 110), order('STOP_MARKET', 90, '2')
    rows = {'verified': [tp, sl], 'partial': [sl], 'empty': [], 'query_failed': []}[scenario]
    algo = Mock(return_value=rows)
    if scenario == 'query_failed':
        algo.side_effect = RuntimeError('timeout')
    trader.binance_client = SimpleNamespace(client=SimpleNamespace(futures_get_open_orders=Mock(return_value=[])), get_open_algo_orders=algo)
    pos = SimpleNamespace(side=SimpleNamespace(value='LONG'), quantity=1, position_owner=NOAH_POSITION_OWNER,
                          tp_price=110, sl_price=90, entry_order_id='owned')
    assert trader._tp_sl_watchdog('BTCUSDT', pos, 0) == (scenario == 'verified')
    assert trader._place_owned_binance_protection.call_count == (1 if scenario == 'empty' else 0)
    # A second cycle must use the bounded verification interval.
    trader._tp_sl_watchdog('BTCUSDT', pos, 1)
    assert algo.call_count == 1


@pytest.mark.parametrize('venue', CRYPTO_VENUE_ORDER)
@pytest.mark.parametrize('mode', ['learning', 'paper', 'live'])
def test_start_boundary_uses_venue_mode(venue, mode):
    cfg = {'paper_trading': False, 'enabled_exchanges': [venue],
           'trade_enabled_exchanges': [venue] if mode == 'live' else [],
           '_trade_scope_user_confirmed_v3905': True,
           'exchange_execution_modes': {venue: mode},
           f'{venue}_api_key': 'fixture', f'{venue}_secret_key': 'fixture',
           f'{venue}_passphrase': 'fixture', f'{venue}_password': 'fixture'}
    app = SimpleNamespace(start_source=Mock(return_value=True), running_crypto_exchanges=lambda: [venue])
    bridge = HeadlessRuntimeBridge(account='fixture', factory=lambda _: app)
    bridge._settings = lambda: cfg
    if mode == 'live':
        with pytest.raises(RuntimeError, match='venue_live_onboarding_required|live_start_confirmation_required'):
            bridge.execute('trading.start', {'source': venue})
        app.start_source.assert_not_called()
    else:
        bridge.execute('trading.start', {'source': venue})
        app.start_source.assert_called_once_with(venue)


@pytest.mark.parametrize('venue', ['coinone', 'upbit', 'bithumb'])
def test_public_learning_client(venue, monkeypatch):
    factory = Mock(return_value=SimpleNamespace(connect=lambda: True))
    monkeypatch.setattr('trading.unified_trading_manager.ExchangeFactory.create_spot_exchange', factory)
    manager = UnifiedTradingManager({'paper_trading': False, 'enabled_exchanges': [venue], 'trade_enabled_exchanges': []})
    assert manager.get_exchange(venue, 'spot') is not None


@pytest.mark.parametrize('venue', CRYPTO_VENUE_ORDER)
def test_manual_analysis_reads_requested_venue_without_fallback(venue):
    from trading.analyzer import Analyzer
    analyzer = object.__new__(Analyzer)
    analyzer.logger = Mock()
    analyzer.settings = {}
    analyzer.data_cache = {}
    analyzer.cache_timeout = 60
    analyzer._exchange_context = None
    analyzer.binance_client = SimpleNamespace(get_klines=Mock(return_value=[]))
    analyzer.exchange_manager = SimpleNamespace(get_klines=Mock(return_value=[]))
    cfg = {f'{venue}_api_key': 'fixture', f'{venue}_secret_key': 'fixture', f'{venue}_passphrase': 'fixture', f'{venue}_password': 'fixture'}
    bridge = HeadlessRuntimeBridge(account='fixture', factory=lambda _: SimpleNamespace(analyzer=analyzer))
    bridge._settings = lambda: cfg
    with pytest.raises(RuntimeError, match='coin_analysis_unavailable'):
        bridge.execute('coins.analyze', {'source': venue, 'symbol': 'BTC'})
    assert analyzer.exchange_manager.get_klines.call_args.kwargs['exchange_name'] == venue
    assert analyzer._exchange_context is None
    if venue != 'binance':
        analyzer.binance_client.get_klines.assert_not_called()


def order(kind, price, identity='1', **extra):
    return {'symbol': 'BTCUSDT', 'side': 'SELL', 'algoStatus': 'NEW', 'orderType': kind,
            'triggerPrice': price, 'closePosition': True, 'algoId': identity, **extra}


def test_protection_requires_both_sides_and_positive_prices():
    tp = order('TAKE_PROFIT_MARKET', '110')
    sl = order('STOP_MARKET', '90', '2')
    assess = lambda rows: assess_protection(rows, symbol='BTCUSDT', position_side='LONG', quantity=1)
    assert assess([tp, sl])['status'] == 'verified'
    assert assess([sl])['status'] == 'partial_or_ambiguous'
    assert assess([order('LIMIT', None, tdMode='cross')])['status'] == 'missing'
    assert assess([dict(tp, side='BUY'), sl])['status'] != 'verified'
    assert assess([dict(tp, algoStatus='CANCELED'), sl])['status'] != 'verified'
    assert assess([dict(tp, triggerPrice='0'), sl])['status'] != 'verified'
    assert assess([tp, dict(sl, algoId='1')])['status'] != 'verified'
    assert assess_protection([tp, sl], symbol='BTCUSDT', position_side='LONG', expected_ids={'tp': 'other'})['status'] != 'verified'


def test_bitget_position_plans_keep_quantity_and_direction_evidence():
    rows = [{'info': {'symbol': 'BTCUSDT', 'holdSide': 'long', 'planType': kind,
                      'planStatus': 'live', 'triggerPrice': price, 'size': '1', 'orderId': kind}}
            for kind, price in [('pos_profit', '110'), ('pos_loss', '90')]]
    assert assess_protection(rows, symbol='BTCUSDT', position_side='LONG', quantity=1)['status'] == 'verified'
    assert assess_protection(rows, symbol='BTCUSDT', position_side='SHORT', quantity=1)['status'] != 'verified'
    assert assess_protection(rows, symbol='BTCUSDT', position_side='LONG', quantity=2)['status'] != 'verified'


def test_regime_diagnostic_does_not_defeat_candidate_log_throttle(monkeypatch):
    from trading.runtime_observability import emit_runtime_status, emit_regime_observation
    logger = Mock()
    monkeypatch.setattr('log_system.log_adapter.log_event', logger)
    owner = SimpleNamespace(settings={'paper_trading': False, 'trade_enabled_exchanges': []})
    for _ in range(5):
        emit_runtime_status(owner, 'coinone', 'candidates_ready', 'ready')
        emit_regime_observation(owner, 'coinone', 'normal', 'normal', False)
    assert logger.call_count == 2
    assert all(call.kwargs['execution_mode'] == 'learning' for call in logger.call_args_list)


@pytest.mark.parametrize('response', [None, {'code': -1}])
def test_binance_strict_algo_failure_is_not_empty_order_book(response):
    from api.binance_client import BinanceClient
    client = object.__new__(BinanceClient)
    client._has_api_keys = lambda: True
    client._get_futures_signed = Mock(return_value=response)
    client.log_event = Mock()
    with pytest.raises(RuntimeError):
        client.get_open_algo_orders('BTCUSDT', strict=True)


def test_bybit_empty_position_stop_fields_are_not_protective_orders():
    raw = SimpleNamespace(fetch_open_orders=Mock(return_value=[]), fetch_positions=Mock(return_value=[
        {'symbol': 'BTCUSDT', 'side': 'long', 'contracts': 1,
         'info': {'positionIdx': 0, 'takeProfit': '0', 'stopLoss': '0', 'tpslMode': 'Full'}}]))
    assert ccxt_protection_orders(SimpleNamespace(exchange=raw, _normalize_symbol=lambda s: s), 'bybit', 'BTCUSDT') == []


@pytest.mark.parametrize('venue', ['okx', 'bybit', 'bitget'])
def test_snapshot_queries_conditionals_and_fails_closed(venue):
    raw = SimpleNamespace(fetch_open_orders=Mock(return_value=[]), fetch_positions=Mock(return_value=[]))
    adapter = SimpleNamespace(exchange=raw, _normalize_symbol=lambda s: s)
    assert ccxt_protection_orders(adapter, venue, 'BTCUSDT') == []
    assert any(c.kwargs['params'].get('trigger') for c in raw.fetch_open_orders.call_args_list)
    raw.fetch_open_orders.side_effect = TimeoutError()
    with pytest.raises(TimeoutError):
        ccxt_protection_orders(adapter, venue, 'BTCUSDT')


@pytest.mark.parametrize('venue', ['okx', 'bybit', 'bitget'])
def test_query_failure_never_resubmits(venue):
    from trading.trader import PositionSide
    trader = object.__new__(UnifiedTrader)
    trader._execution_mode = lambda _: ExecutionMode.LIVE
    trader.logger = Mock()
    pos = SimpleNamespace(quantity=1, side=PositionSide.LONG, position_owner='noahai', tp_price=110, sl_price=90)
    trader.active_positions = {venue: {'BTCUSDT': pos}}
    adapter = SimpleNamespace(exchange=SimpleNamespace(fetch_open_orders=Mock(side_effect=TimeoutError())),
                              _normalize_symbol=lambda s: s, place_insurance_tp_sl=Mock())
    trader.unified_manager = SimpleNamespace(get_exchange=lambda *args: adapter)
    trader._verify_and_repair_tp_sl(venue)
    assert pos.protection_status == 'query_failed'
    adapter.place_insurance_tp_sl.assert_not_called()


@pytest.mark.parametrize('venue', [*CRYPTO_VENUE_ORDER, 'kiwoom', 'shinhan', 'mirae', 'kis'])
def test_production_recorder_roundtrip_strategy(venue, tmp_path, monkeypatch):
    from trading.recorder import Recorder
    from web_platform.source_trade_history import load_source_live_history
    monkeypatch.setattr(Recorder, 'setup_logger', lambda _: None)
    monkeypatch.setattr(Recorder, '_get_exchange_logger', lambda _: Mock())
    monkeypatch.setattr('trading.recorder.log_event', Mock())
    db = Recorder(db_path=str(tmp_path / 'ledger.db'), log_path=str(tmp_path / 'logs'))
    pos = SimpleNamespace(symbol='BTCUSDT', entry_price=100, quantity=1, leverage=1,
                          side=SimpleNamespace(value='LONG'), entry_time=datetime.now(timezone.utc), tp_price=110, sl_price=90,
                          custom_strategy_key='owned_strategy', custom_strategy_version_id='v1')
    row_id = db.log_trade_entry(pos, {'exchange': venue, 'order_id': 'entry-fixture', 'execution_mode': 'live'})
    assert row_id
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE trade_log SET exit_time=?, net_pnl=1, reconciliation_status='exchange_confirmed' WHERE id=?", (datetime.now(timezone.utc).isoformat(), row_id))
    row = load_source_live_history(db.db_path, source=venue)['records'][0]
    assert (row['strategy_key'], row['version_id']) == ('owned_strategy', 'v1')
    # Reopening and a repeated entry must not duplicate or erase evidence.
    assert db.log_trade_entry(pos, {'exchange': venue, 'order_id': 'entry-fixture'}) == row_id


@pytest.mark.parametrize('broker', ['kiwoom', 'shinhan', 'mirae', 'kis'])
@pytest.mark.parametrize('asset,symbol', [('stock', '005930'), ('etf', '069500')])
def test_stock_real_writer_partial_close_keeps_entry_strategy(broker, asset, symbol, tmp_path, monkeypatch):
    from trading.recorder import Recorder
    from trading.stock_analysis_service import StockAnalysisService
    monkeypatch.setattr(Recorder, 'setup_logger', lambda _: None)
    monkeypatch.setattr(Recorder, '_get_exchange_logger', lambda _: Mock())
    monkeypatch.setattr('trading.recorder.log_event', Mock())
    monkeypatch.setattr('trading.stock_analysis_service.emit_position_opened', lambda **kw: (True, 'fixture-position'))
    monkeypatch.setattr('trading.stock_analysis_service.emit_position_reduced', lambda **kw: True)
    monkeypatch.setattr('trading.stock_analysis_service.emit_position_closed', lambda **kw: True)
    recorder = Recorder(db_path=str(tmp_path / 'stock.db'), log_path=str(tmp_path / 'logs'))
    service = StockAnalysisService(SimpleNamespace(broker_name=broker), broker_name=broker, recorder=recorder)
    common = dict(symbol=symbol, price=100, score=80, momentum=1, asset_class=asset)
    assert service._insert_auto_trade_log(**common, side='BUY', quantity=3,
        strategy_key='original', strategy_version_id='v1', order_result={'order_id': 'buy'})
    assert service._insert_auto_trade_log(**common, side='SELL', quantity=1,
        strategy_key='other', strategy_version_id='v2', order_result={'order_id': 'sell'})
    with sqlite3.connect(recorder.db_path) as db:
        rows = db.execute('SELECT strategy_key, strategy_version_id FROM trade_log').fetchall()
    assert rows == [('original', 'v1'), ('original', 'v1')]


@pytest.mark.parametrize('venue', [*CRYPTO_VENUE_ORDER, 'kiwoom', 'shinhan', 'mirae', 'kis'])
@pytest.mark.parametrize('mode', ['paper', 'live', 'learning'])
def test_regime_event_reaches_enabled_telegram_transport(venue, mode, monkeypatch):
    from trading import notifications as n
    dispatcher = n.NotificationDispatcher()
    dispatcher._settings = {'notification_integrations': {'enabled': True, 'cooldown_seconds': 300,
        'channels': {'telegram': {'enabled': True, 'bot_token': 'fixture', 'chat_id': 'fixture'}},
        'events': {'market_regime_change': True}, 'exchanges': {venue: True},
        'market_regime_modes': {mode: True}}}
    monkeypatch.setattr(n, '_DISPATCHER', dispatcher)
    send = Mock()
    monkeypatch.setattr(n, '_deliver_telegram', send)
    assert not n.publish_market_regime_change(venue, 'range', 'range', execution_mode=mode)
    assert n.publish_market_regime_change(venue, 'range', 'bull', execution_mode=mode)
    generation, item = dispatcher._queue.get_nowait()
    dispatcher._deliver(item, generation=generation)
    send.assert_called_once()
    assert item.source == venue and item.execution_mode == mode
