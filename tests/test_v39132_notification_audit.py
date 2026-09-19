"""No real credentials or networks. Audit regressions across all 11 venues."""
import threading
from datetime import datetime
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from trading import notifications as n
from trading.exchanges.venue_capabilities import SUPPORTED_VENUES, CRYPTO_VENUES, normalize_venue
from trading.market_selection_runtime import RegimeStabilizer
from trading.stock_analysis_service import StockAnalysisService, detect_market_regime
from trading.stock_runtime_controller import StockRuntimeController
from web_platform.application_services import EDITABLE_BY_PATH, ApplicationServices


def settings():
    return {'notification_integrations': {'enabled': True, 'cooldown_seconds': 0, 'retry_count': 0,
        'channels': {'discord': {'enabled': True, 'webhook_url': 'old-target'},
                     'telegram': {'enabled': True, 'bot_token': 'old-token', 'chat_id': 'old-chat'}},
        'events': {event: True for event in n.SUPPORTED_EVENTS}}}


def dispatcher():
    d = n.NotificationDispatcher()
    d._settings = settings()
    return d


@pytest.mark.parametrize('venue', sorted(SUPPORTED_VENUES))
def test_all_venues_have_editable_opt_out_and_unknown_does_not_notify(venue, monkeypatch):
    path = f'notification_integrations.exchanges.{venue}'
    assert path in EDITABLE_BY_PATH
    cfg = settings()
    assert ApplicationServices._notification_venue_value(cfg, path)
    cfg['notification_integrations']['exchanges'] = {venue: False}
    assert not n.notification_status(cfg)['exchanges'][venue]
    d = dispatcher(); d._settings = cfg
    assert not d.publish(n.NotificationMessage('market_regime_change', 'test', 'test', source=venue))
    send = Mock(); monkeypatch.setattr(n, 'publish_notification', send)
    for old, new in [('bull', 'unknown'), ('unknown', 'bull'), ('normal', 'normal')]:
        assert not n.publish_market_regime_change(venue, old, new)
    send.assert_not_called()


@pytest.mark.parametrize('alias', ['miraeAsset', 'MIRAE', 'koreaInvestment', 'KIS'])
def test_broker_alias_opt_out(alias):
    cfg = {'exchanges': {alias: False}}
    assert not n._source_enabled(cfg, normalize_venue(alias))


def test_zero_cooldown_and_zero_retries_are_respected(monkeypatch):
    d = dispatcher(); item = n.NotificationMessage('report', 'x', 'x')
    monkeypatch.setattr(n.time, 'monotonic', lambda: 1)
    assert d.publish(item) and d.publish(item)
    failure = Mock(side_effect=n.NotificationDeliveryError('notification_network_error'))
    monkeypatch.setattr(n, '_deliver_discord', failure)
    monkeypatch.setattr(n, '_deliver_telegram', Mock())
    monkeypatch.setattr(n.time, 'sleep', Mock())
    d._deliver(item)
    assert failure.call_count == 1
    n.time.sleep.assert_not_called()


def test_first_notification_not_suppressed_on_fresh_boot(monkeypatch):
    d = dispatcher(); d._settings['notification_integrations']['cooldown_seconds'] = 300
    monkeypatch.setattr(n.time, 'monotonic', lambda: 1)
    item = n.NotificationMessage('report', 'x', 'x')
    assert d.publish(item)
    assert not d.publish(item)


def test_account_change_at_delivery_boundary_drops_old_message(monkeypatch):
    d = dispatcher(); d.publish(n.NotificationMessage('report', 'old account', 'private'))
    d._queue.put_nowait(None)
    original = d._deliver
    def switch(item, *, generation):
        with patch('threading.Thread.start'):
            d.configure(settings(), scope='new-account')
        original(item, generation=generation)
    monkeypatch.setattr(d, '_deliver', switch)
    send = Mock(); monkeypatch.setattr(n, '_deliver_discord', send); monkeypatch.setattr(n, '_deliver_telegram', send)
    d._run()
    send.assert_not_called()


def test_account_change_during_inflight_channel_never_uses_new_destinations(monkeypatch):
    d = dispatcher(); captured = []
    def first(config, item, timeout):
        captured.append(config)
        other = settings(); other['notification_integrations']['channels']['telegram']['bot_token'] = 'new-token'
        with patch('threading.Thread.start'):
            d.configure(other, scope='new-account')
    monkeypatch.setattr(n, '_deliver_discord', first)
    second = Mock(); monkeypatch.setattr(n, '_deliver_telegram', second)
    d._deliver(n.NotificationMessage('report', 'old', 'private'))
    assert captured == [{'enabled': True, 'webhook_url': 'old-target'}]
    second.assert_not_called()


@pytest.mark.parametrize('venue', sorted(CRYPTO_VENUES))
def test_missing_crypto_candles_never_mean_normal(venue, monkeypatch):
    from trading.trader import Trader
    from trading.unified_trader import UnifiedTrader
    monkeypatch.setattr('trading.runtime_observability.emit_runtime_status', Mock())
    obj = object.__new__(Trader if venue == 'binance' else UnifiedTrader)
    obj.logger = Mock(); obj.settings = {}; obj.log_event = Mock()
    obj.binance_client = SimpleNamespace(get_klines=lambda *a, **kw: [])
    obj.exchange_manager = obj.binance_client
    result = obj._analyze_market_regime_binance_fast() if venue == 'binance' else obj._evaluate_current_market_conditions_unified_fast(venue, 'BTCUSDT')
    assert result == 'unknown'
    assert obj._market_data_unavailable[venue]


def test_unknown_does_not_replace_confirmed_regime_or_count_as_confirmation():
    s = RegimeStabilizer()
    assert s.observe('kis', 'bull', now=0) == ('bull', False)
    s.observe('kis', 'bear', now=1000)
    assert s.observe('kis', 'unknown', now=1100) == ('bull', False)
    assert s.observe('kis', 'bear', now=1200) == ('bull', False)
    assert s.observe('kis', 'bear', now=1300) == ('bear', True)


@pytest.mark.parametrize('broker', ['kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment'])
def test_stock_failure_preserves_valid_regime_and_recovery_does_not_fake_transition(broker, monkeypatch):
    clock = [1000]
    monkeypatch.setattr('trading.stock_analysis_service.pytime.time', lambda: clock[0])
    monkeypatch.setattr('trading.runtime_observability.emit_runtime_status', Mock())
    s = object.__new__(StockAnalysisService)
    s.adapter = SimpleNamespace(get_index_price=lambda *a: {}, get_realtime_price=lambda *a: {})
    s.broker_name = broker; s._regime_cache = 'bull'; s._regime_cache_time = 0
    s._REGIME_CACHE_TTL = 300
    s.log_event = Mock(); s._emit_analysis_log = Mock(); s._persist_xai_decision = Mock()
    assert detect_market_regime(s.adapter) == 'unknown'
    assert s.get_market_regime() == 'unknown'
    assert s._regime_cache == 'bull'
    clock[0] += 61
    s.adapter.get_index_price = lambda *a: {'change_rate': 2}
    send = Mock(); monkeypatch.setattr(n, 'publish_market_regime_change', send)
    assert s.get_market_regime() == 'bull'
    send.assert_not_called()


@pytest.mark.parametrize('broker', ['kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment'])
def test_no_candidates_still_calls_position_management_service(broker, monkeypatch):
    adapter = SimpleNamespace(is_connected=True, api_type='mock')
    service = SimpleNamespace(adapter=adapter, run_auto_trade_cycle=Mock(return_value={'orders_executed': 0}))
    controller = StockRuntimeController(settings_provider=lambda: {'paper_trading': True},
        adapter_factory=lambda *a: adapter, service_factory=lambda *a, **kw: service)
    monkeypatch.setattr(controller, '_live_permission', lambda *a: (False, 'paper'))
    monkeypatch.setattr('trading.stock_runtime_controller.select_stock_universe', lambda *a, **kw: [])
    result, _ = controller._run_once(broker)
    assert result['reason'] == 'empty_stock_universe'
    assert service.run_auto_trade_cycle.call_args.kwargs['symbols'] == []


@pytest.mark.parametrize('broker', ['kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment'])
def test_stock_worker_errors_reach_external_event_without_exception_secrets(broker, monkeypatch):
    c = StockRuntimeController(settings_provider=lambda: {})
    stop = threading.Event()
    def cycle(_):
        stop.set(); raise RuntimeError('secret token MUST NOT appear')
    c._run_once = cycle
    monkeypatch.setattr('trading.runtime_observability.emit_runtime_status', Mock())
    send = Mock(); monkeypatch.setattr(n, 'publish_notification', send)
    c._worker(broker, stop)
    assert send.call_args.args[0] == 'runtime_failure'
    assert 'secret token' not in str(send.call_args)


@pytest.mark.parametrize('broker', ['kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment'])
@pytest.mark.parametrize('mode', ['live', 'paper', 'learning'])
def test_stock_risk_events_are_mode_scoped(broker, mode, monkeypatch):
    send = Mock(return_value=True); monkeypatch.setattr(n, 'publish_notification', send)
    cases = [({'allowed': False, 'reasons': ['risk_data_unavailable']}, 'risk_data_unavailable'),
             ({'allowed': False, 'reasons': ['daily_loss_limit']}, 'guardrail_stop'),
             ({'allowed': True, 'metrics': {'loss_rate': 6}}, 'loss_warning')]
    for decision, event in cases:
        send.reset_mock()
        n.publish_stock_risk_decision(broker, mode, decision)
        if mode == 'live':
            assert send.call_args.args[0] == event
            assert send.call_args.kwargs['source'] == normalize_venue(broker)
        else:
            send.assert_not_called()


def test_missing_loss_rate_is_not_fabricated(monkeypatch):
    send = Mock(); monkeypatch.setattr(n, 'publish_notification', send)
    assert not n.publish_stock_risk_decision('kis', 'live', {'allowed': True, 'metrics': {}})
    send.assert_not_called()


def test_mirae_candles_do_not_route_to_catalog():
    from trading.exchanges.adapters.mirae_asset_stock_adapter import MiraeAssetStockAdapter
    a = object.__new__(MiraeAssetStockAdapter)
    a.partner_profile = {'endpoints': {'stock_list': '/catalog', 'candles': '/candles'}}
    assert a._resolve_path('/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice') == '/candles'


@pytest.mark.parametrize('venue', sorted(CRYPTO_VENUES))
def test_crypto_cycle_errors_emit_scoped_runtime_event(venue, monkeypatch):
    from trading.trader import Trader
    from trading.unified_trader import UnifiedTrader
    obj = object.__new__(Trader if venue == 'binance' else UnifiedTrader)
    obj.logger = Mock()
    obj._execution_mode = Mock(side_effect=RuntimeError('private-api-detail'))
    send = Mock(); monkeypatch.setattr(n, 'publish_notification', send)
    if venue == 'binance':
        obj.execute_trading_cycle()
    else:
        obj.execute_trading_cycle_unified(venue)
    assert send.call_args.args[0] == 'runtime_failure'
    assert send.call_args.kwargs['source'] == venue
    assert 'private-api-detail' not in str(send.call_args)


def test_discord_long_emoji_message_is_bounded_and_mentions_disabled(monkeypatch):
    send = Mock(return_value={'id': 'mock-message'})
    monkeypatch.setattr(n, '_request_json', send)
    n._deliver_discord({'webhook_url': 'https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyzABCDE'},
        n.NotificationMessage('report', '긴 리포트', '😀' * 3200), 5)
    payload = send.call_args.args[1]
    assert len(payload['content'].encode('utf-16-le')) <= 4000
    assert '요약 표시' in payload['content']
    assert payload['allowed_mentions'] == {'parse': []}


def test_telegram_failed_discovery_is_not_an_empty_success(monkeypatch):
    cfg = settings(); cfg['notification_integrations']['channels']['telegram']['bot_token'] = '123456789:abcdefghijklmnopqrstuvwxyzABCDE'
    monkeypatch.setattr(n, '_request_json', Mock(side_effect=[{'ok': True}, {'ok': False, 'error_code': 429}]))
    with pytest.raises(n.NotificationDeliveryError):
        n.discover_telegram_chats(cfg)


@pytest.mark.parametrize('broker', ['kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment'])
def test_unverified_broker_pnl_is_not_zero_and_paper_uses_own_ledger(broker):
    s = object.__new__(StockAnalysisService); s.broker_name = broker
    s.adapter = SimpleNamespace(get_trading_stats=Mock(return_value={'realized_pnl': 0, 'pnl_verified': False}))
    s._get_recent_trade_samples = Mock(return_value=[])
    s._get_recent_paper_trade_samples = Mock(return_value=[{'net_pnl': -200, 'timestamp': datetime.now().isoformat()}])
    policy = {'risk_guard_enabled': True, 'daily_max_loss': 100}
    live = s._evaluate_auto_trade_risk_guard(symbol='005930', auto_risk_policy=policy, execution_mode='live')
    assert live['allowed'] is False and live['reasons'] == ['risk_data_unavailable']
    s.adapter.get_trading_stats.reset_mock()
    paper = s._evaluate_auto_trade_risk_guard(symbol='005930', auto_risk_policy=policy, execution_mode='paper')
    s.adapter.get_trading_stats.assert_not_called()
    assert paper['metrics']['realized_pnl'] == -200
    assert paper['allowed'] is False


@pytest.mark.parametrize('pnl', [None, float('nan'), float('inf'), 'invalid'])
def test_invalid_live_pnl_is_unavailable(pnl):
    s = object.__new__(StockAnalysisService)
    s.adapter = SimpleNamespace(get_trading_stats=lambda: {'realized_pnl': pnl})
    s._get_recent_trade_samples = Mock(return_value=[])
    result = s._evaluate_auto_trade_risk_guard(symbol='005930', execution_mode='live', auto_risk_policy={'risk_guard_enabled': True})
    assert result['reasons'] == ['risk_data_unavailable']
