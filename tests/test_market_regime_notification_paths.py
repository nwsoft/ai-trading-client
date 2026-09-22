"""Offline positive-path audit: real detectors/callers, no orders or delivery.

This tests source wiring, not the customer's historical quotes or installed app.
"""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.settings_contract import TRADE_SCOPE_CONFIRMATION_KEY
from trading import notifications
from trading.execution_mode import resolve_stock_execution_mode
from trading.market_selection_runtime import RegimeStabilizer
from trading.stock_analysis_service import StockAnalysisService
from trading.trader import Trader
from trading.unified_trader import UnifiedTrader


@pytest.mark.parametrize('mode', ['paper', 'live', 'learning'])
@pytest.mark.parametrize('venue', ['binance', 'okx', 'bybit', 'bitget', 'upbit', 'bithumb', 'coinone'])
def test_crypto_healthy_observation_reaches_notification_in_each_mode(venue, mode, monkeypatch):
    clock = [1000.0]
    trend = [0]

    def candles(*args, **kwargs):
        return [[i, 100+i*trend[0], 100+i*trend[0], 100+i*trend[0],
                 100+i*trend[0], 100 if i < 19 else 500] for i in range(20)]

    trader = object.__new__(Trader if venue == 'binance' else UnifiedTrader)
    trader.logger = Mock()
    trader.log_event = Mock()
    trader.settings = {
        'paper_trading': mode == 'paper',
        TRADE_SCOPE_CONFIRMATION_KEY: mode == 'live',
        'trade_enabled_exchanges': [venue] if mode == 'live' else [],
        'exchange_execution_modes': {venue: mode},
        'market_regime_min_dwell_seconds': 0,
    }
    trader._regime_stabilizer = Mock(wraps=RegimeStabilizer())
    trader.get_active_positions = Mock(return_value=[] if venue == 'binance' else {venue: {}})
    if venue == 'binance':
        trader.main_app = SimpleNamespace(selected_coins=[{
            'symbol': 'BTCUSDT', 'overall_score': 80, 'execution_eligible': True}])
        trader.binance_client = SimpleNamespace(get_klines=candles)
        trader._get_ai_max_positions = Mock(return_value=3)
        trader._schedule_reselect_coins = Mock()
        check = trader._check_and_reselect_coins_optimized
        assert trader._execution_mode().value == mode
    else:
        trader.trade_enabled_exchanges = {venue} if mode == 'live' else set()
        trader.selected_coins = {venue: [{'symbol': 'BTCUSDT', 'overall_score': 80}]}
        trader.exchange_manager = SimpleNamespace(get_klines=candles)
        trader.last_market_analysis_time_by_exchange = {}
        trader.last_market_regime_by_exchange = {}
        trader._pending_regime_reselection_by_exchange = {}
        trader.last_coin_selection_time_by_exchange = {}
        trader._schedule_reselect_coins_unified = Mock()
        check = lambda: trader._check_and_reselect_coins_unified_optimized(venue)
        assert trader._execution_mode(venue).value == mode
    send = Mock(return_value=True)
    monkeypatch.setattr(notifications, 'publish_notification', send)
    monkeypatch.setattr('time.time', lambda: clock[0])
    monkeypatch.setattr('time.monotonic', lambda: clock[0])
    monkeypatch.setattr('trading.runtime_observability.emit_runtime_status', Mock())
    for step in range(3):
        clock[0] = 1000+step*301
        trend[0] = 0 if step == 0 else 1
        check()
    assert send.call_count == 1
    assert send.call_args.args[0] == 'market_regime_change'
    assert send.call_args.kwargs['source'] == venue
    assert send.call_args.kwargs['execution_mode'] == mode
    assert all(call.kwargs['min_dwell_seconds'] == 0 for call in trader._regime_stabilizer.observe.call_args_list)
    trader.logger.error.assert_not_called()


@pytest.mark.parametrize('mode', ['paper', 'live', 'learning'])
@pytest.mark.parametrize('broker', ['kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment'])
def test_broker_healthy_observation_reaches_notification_in_each_mode(broker, mode, monkeypatch):
    clock = [1000.0]
    change = [0]
    service = object.__new__(StockAnalysisService)
    service.adapter = SimpleNamespace(get_realtime_price=lambda symbol: {'change_rate': change[0]})
    service.broker_name = broker
    service.settings = {'paper_trading': mode == 'paper'}
    service._active_execution_mode = resolve_stock_execution_mode(
        service.settings, allow_live_order=mode == 'live', adapter_api_type='rest').value
    assert service._active_execution_mode == mode
    service._regime_cache = None
    service._regime_cache_time = 0
    service._REGIME_CACHE_TTL = 300
    service.log_event = Mock()
    service._emit_analysis_log = Mock()
    service._persist_xai_decision = Mock()
    send = Mock(return_value=True)
    monkeypatch.setattr(notifications, 'publish_notification', send)
    monkeypatch.setattr('trading.stock_analysis_service.pytime.time', lambda: clock[0])
    assert service.get_market_regime() == 'range'
    clock[0] = 1301
    change[0] = 2
    assert service.get_market_regime() == 'bull'
    assert send.call_count == 1
    assert send.call_args.args[0] == 'market_regime_change'
    assert send.call_args.kwargs['source'] == broker.lower()
    assert send.call_args.kwargs['execution_mode'] == mode


@pytest.mark.parametrize('mode', ['paper', 'live', 'learning'])
@pytest.mark.parametrize('venue', ['binance', 'okx', 'bybit', 'bitget', 'upbit', 'bithumb', 'coinone', 'kiwoom', 'shinhan', 'mirae', 'kis'])
def test_mode_filter_only_excludes_selected_regime_events(mode, venue):
    dispatcher = notifications.NotificationDispatcher()
    dispatcher._settings = {'notification_integrations': {
        'enabled': True, 'cooldown_seconds': 0,
        'channels': {'telegram': {'enabled': True, 'bot_token': 'fixture', 'chat_id': 'fixture'}},
        'events': {key: True for key in notifications.SUPPORTED_EVENTS},
        'market_regime_modes': {mode: False},
    }}
    # No worker/network. Verify all other event types remain independent.
    for event in sorted(notifications.SUPPORTED_EVENTS):
        assert dispatcher.publish(notifications.NotificationMessage(
            event, 'fixture', 'fixture', source=venue, execution_mode=mode
        )) == (event != 'market_regime_change')
    dispatcher._settings['notification_integrations']['market_regime_modes'][mode] = True
    assert dispatcher.publish(notifications.NotificationMessage(
        'market_regime_change', 'fixture', 'fixture', source=venue, execution_mode=mode))


def test_legacy_defaults_unknown_and_queued_mode_filter(monkeypatch):
    from web_platform.application_services import EDITABLE_BY_PATH
    for mode in ('paper', 'live', 'learning'):
        assert notifications._regime_mode_enabled({}, mode)
        assert f'notification_integrations.market_regime_modes.{mode}' in EDITABLE_BY_PATH
    assert not notifications._regime_mode_enabled({'market_regime_modes': {'live': False}}, 'live_api')
    assert not notifications._regime_mode_enabled({'market_regime_modes': {'paper': False}}, 'mock')
    assert not notifications._regime_mode_enabled({'market_regime_modes': {'paper': False}}, 'unknown')
    dispatcher = notifications.NotificationDispatcher()
    dispatcher._settings = {'notification_integrations': {
        'enabled': True, 'events': {'market_regime_change': True},
        'market_regime_modes': {'paper': False},
        'channels': {'telegram': {'enabled': True}},
    }}
    send = Mock()
    monkeypatch.setattr(notifications, '_deliver_telegram', send)
    dispatcher._deliver(notifications.NotificationMessage('market_regime_change', 'test', 'test', execution_mode='paper'))
    send.assert_not_called()


def test_mode_switch_does_not_share_regime_cooldown(monkeypatch):
    dispatcher = notifications.NotificationDispatcher()
    dispatcher._settings = {'notification_integrations': {
        'enabled': True, 'events': {'market_regime_change': True},
        'channels': {'telegram': {'enabled': True, 'bot_token': 'fixture', 'chat_id': 'fixture'}},
    }}
    monkeypatch.setattr(notifications, '_DISPATCHER', dispatcher)
    for mode in ('paper', 'live', 'learning'):
        assert notifications.publish_market_regime_change('binance', 'normal', 'bull', execution_mode=mode)
        assert not notifications.publish_market_regime_change('binance', 'normal', 'bull', execution_mode=mode)
    _, message = dispatcher._queue.get_nowait()
    assert '[PAPER]' in notifications._format_message(message)
