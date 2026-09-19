from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from web_platform.application_services import ApplicationServices
from web_platform.advanced_services import AdvancedFeatureServices
from web_platform.headless_runtime import HeadlessTradingRuntime
from web_platform.runtime_bridge import HeadlessRuntimeBridge


class _Holder:
    def __init__(self, settings):
        self.settings = settings


def test_advanced_services_refreshes_financial_intelligence_settings_in_place():
    advanced = object.__new__(AdvancedFeatureServices)
    advanced.settings = {"financial_intelligence": {"timeout": 4, "event_feed_items": ["old"]}}

    class Intelligence:
        def __init__(self):
            self.calls = []

        def refresh_settings(self, settings):
            self.calls.append(deepcopy(settings))

    advanced.intelligence = Intelligence()
    original = advanced.settings

    advanced.refresh_settings({"financial_intelligence": {"timeout": 11, "news_rss_urls": ["https://example.test/rss"]}})

    assert advanced.settings is original
    assert advanced.settings["financial_intelligence"]["timeout"] == 11
    assert advanced.intelligence.calls == [
        {"timeout": 11, "news_rss_urls": ["https://example.test/rss"]},
    ]


def test_headless_runtime_refresh_updates_all_live_settings_holders_in_place():
    old = {"verbose_trade_logging": False, "enabled_exchanges": ["binance"], "runtime_only": "keep"}
    runtime = object.__new__(HeadlessTradingRuntime)
    runtime.settings = deepcopy(old)
    runtime.trader = _Holder({**old, "trader_default": 5})
    runtime.unified_trader = _Holder(deepcopy(old))
    runtime.unified_manager = _Holder(deepcopy(old))
    runtime.exchange_manager = _Holder(deepcopy(old))
    runtime.api_signal_manager = _Holder(deepcopy(old))
    runtime.optimizer = _Holder(deepcopy(old))
    runtime.evaluator = _Holder(deepcopy(old))
    runtime.auto_optimizer = _Holder(deepcopy(old))
    debug_refreshes = []
    runtime.binance_client = SimpleNamespace(_load_debug_settings=lambda: debug_refreshes.append("binance"))

    references = [holder.settings for holder in (
        runtime, runtime.trader, runtime.unified_trader, runtime.unified_manager,
        runtime.exchange_manager, runtime.api_signal_manager, runtime.optimizer,
        runtime.evaluator, runtime.auto_optimizer,
    )]
    runtime.refresh_settings({"verbose_trade_logging": True, "detailed_logs_enabled": True, "enabled_exchanges": ["upbit"]})

    assert all(reference["verbose_trade_logging"] is True for reference in references)
    assert all(reference["detailed_logs_enabled"] is True for reference in references)
    assert all(reference["enabled_exchanges"] == ["upbit"] for reference in references)
    assert all("runtime_only" not in reference for reference in references)
    assert runtime.trader.settings["trader_default"] == 5
    assert debug_refreshes == ["binance"]


def test_headless_runtime_refresh_rebuilds_saved_binance_credentials_without_restart(monkeypatch):
    import web_platform.headless_runtime as runtime_module

    created = []

    class FakeBinanceClient:
        def __init__(self, config):
            self.config = config
            self.stopped = False
            created.append(self)

        def stop_websocket_stream(self):
            self.stopped = True

    class FakeConfig:
        def __init__(self, api_key, secret_key, testnet):
            self.api_key = api_key
            self.secret_key = secret_key
            self.testnet = testnet

    class UnifiedManager(_Holder):
        def __init__(self, settings):
            super().__init__(settings)
            self.reloads = []

        def reload_settings(self, settings):
            self.reloads.append(deepcopy(settings))

    class ExchangeManager(_Holder):
        def __init__(self, settings, old_client):
            super().__init__(settings)
            self.binance_client = old_client
            self.current_exchange = old_client
            self.exchange_clients = {"binance": old_client}
            self.invalid_api_keys = {"binance"}
            self.cache_cleared = 0

        def clear_cache(self):
            self.cache_cleared += 1

    monkeypatch.setattr(runtime_module, "BinanceClient", FakeBinanceClient)
    monkeypatch.setattr(runtime_module, "BinanceConfig", FakeConfig)
    monkeypatch.setattr(runtime_module, "create_ai_manager_from_settings", lambda *_args, **_kwargs: None)

    old_client = FakeBinanceClient(FakeConfig("old-key", "old-secret", False))
    old_settings = {
        "selected_exchange": "binance",
        "enabled_exchanges": ["binance"],
        "binance_api_key": "old-key",
        "binance_secret_key": "old-secret",
    }
    runtime = object.__new__(HeadlessTradingRuntime)
    runtime.settings = deepcopy(old_settings)
    runtime.logger = SimpleNamespace(debug=lambda *_args, **_kwargs: None)
    runtime.binance_client = old_client
    runtime.unified_manager = UnifiedManager(deepcopy(old_settings))
    runtime.exchange_manager = ExchangeManager(deepcopy(old_settings), old_client)
    runtime.api_signal_manager = _Holder(deepcopy(old_settings))
    runtime.recorder = SimpleNamespace(binance_client=old_client)
    runtime.analyzer = SimpleNamespace(settings=deepcopy(old_settings), binance_client=old_client, ai_manager=None)
    runtime.optimizer = SimpleNamespace(settings=deepcopy(old_settings), binance_client=old_client, ai_manager=None)
    runtime.risk_manager = SimpleNamespace(binance_client=old_client)
    runtime.trader = SimpleNamespace(settings=deepcopy(old_settings), binance_client=old_client, ai_manager=None)
    runtime.unified_trader = SimpleNamespace(
        settings=deepcopy(old_settings), ai_manager=None,
        _compute_enabled_exchanges=lambda: ["binance"],
        _compute_trade_enabled_exchanges=lambda: ["binance"],
        _compute_learning_enabled_exchanges=lambda: ["binance"],
    )
    runtime.evaluator = SimpleNamespace(
        settings=deepcopy(old_settings),
        binance_client=old_client,
        invalidated=[],
        invalidate_selection_cache=lambda venue: runtime.evaluator.invalidated.append(venue),
    )
    runtime.auto_optimizer = SimpleNamespace(settings=deepcopy(old_settings), ai_manager=None)
    runtime.market_state_analyzer = SimpleNamespace(binance_client=old_client)

    runtime.refresh_settings({
        **old_settings,
        "binance_api_key": "new-key",
        "binance_secret_key": "new-secret",
    })

    new_client = runtime.binance_client
    assert new_client is not old_client
    assert new_client.config.api_key == "new-key"
    assert new_client.config.secret_key == "new-secret"
    assert old_client.stopped is True
    assert runtime.exchange_manager.binance_client is new_client
    assert runtime.exchange_manager.exchange_clients["binance"] is new_client
    assert "binance" not in runtime.exchange_manager.invalid_api_keys
    assert runtime.trader.binance_client is new_client
    assert runtime.analyzer.binance_client is new_client
    assert runtime.recorder.binance_client is new_client
    assert runtime.evaluator.binance_client is new_client
    assert runtime.evaluator.invalidated == ["binance"]


def test_exchange_manager_key_change_clears_stale_invalid_session_state():
    from trading.exchange_manager import ExchangeManager

    manager = object.__new__(ExchangeManager)
    manager.settings = {"enabled_exchanges": ["binance"], "binance_api_key": "old", "binance_secret_key": "old"}
    manager.unified_manager = None
    manager.invalid_api_keys = {"binance"}
    manager.exchange_clients = {"binance": object()}
    manager.balance_cache = {}
    manager.last_balance_update = {}
    manager.logger = SimpleNamespace(info=lambda *_args, **_kwargs: None, error=lambda *_args, **_kwargs: None)
    manager.log_event = lambda *_args, **_kwargs: None
    manager._initialize_current_exchange = lambda: None

    manager.update_settings({
        "enabled_exchanges": ["binance"],
        "binance_api_key": "new",
        "binance_secret_key": "new",
    })

    assert "binance" not in manager.invalid_api_keys
    assert "binance" not in manager.exchange_clients


def test_headless_runtime_refresh_discards_changed_stock_broker_adapter():
    runtime = object.__new__(HeadlessTradingRuntime)
    previous = {
        "enabled_stock_brokers": ["kis"],
        "stock_broker_configs": {"koreaInvestment": {"app_key": "old", "app_secret": "old"}},
    }
    runtime.settings = deepcopy(previous)
    runtime.stock_runtime_controller = SimpleNamespace(_adapters={"koreaInvestment": object()})

    runtime._refresh_connection_clients(previous, {
        "enabled_stock_brokers": ["kis"],
        "stock_broker_configs": {"koreaInvestment": {"app_key": "new", "app_secret": "new"}},
    })

    assert "koreaInvestment" not in runtime.stock_runtime_controller._adapters


def test_runtime_bridge_reloads_attached_ai_custom_pool_without_starting_detached_runtime():
    class Runtime:
        @staticmethod
        def refresh_strategy_runtime():
            return [{"version_id": "v1"}, {"version_id": "v2"}]

    bridge = HeadlessRuntimeBridge(account="tester", factory=lambda _account: Runtime())
    assert bridge.refresh_strategies() == {"ok": True, "runtime_attached": False, "active_count": 0}
    bridge._app = Runtime()
    assert bridge.refresh_strategies() == {"ok": True, "runtime_attached": True, "active_count": 2}


def test_headless_runtime_rejects_start_for_source_outside_all_configured_scopes():
    runtime = object.__new__(HeadlessTradingRuntime)
    runtime.settings = {
        "enabled_exchanges": ["upbit"],
        "learning_enabled_exchanges": ["upbit"],
        "trade_enabled_exchanges": [],
    }
    runtime.assert_command_allowed = lambda _source: None

    with pytest.raises(RuntimeError, match="runtime_source_not_enabled:binance"):
        runtime.start_source("binance")


def test_bridge_uses_runtime_refresh_contract_instead_of_replacing_settings_object():
    class Runtime:
        def __init__(self):
            self.settings = {"value": "old"}
            self.calls = 0

        def refresh_settings(self, settings):
            self.calls += 1
            self.settings.update(settings)

    runtime = Runtime()
    original = runtime.settings
    bridge = HeadlessRuntimeBridge(account="tester", factory=lambda account: runtime)
    bridge._app = runtime
    bridge.refresh_settings({"value": "new"})

    assert runtime.calls == 1
    assert runtime.settings is original
    assert runtime.settings["value"] == "new"


def test_completed_settings_write_is_not_reported_as_503_when_runtime_refresh_fails(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    stored = {"paper_trading": True, "verbose_trade_logging": False}

    class FailingRuntime:
        def refresh_settings(self, settings):
            raise RuntimeError("provider detail must not escape")

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: deepcopy(stored))

    def fake_save(next_settings):
        stored.clear()
        stored.update(deepcopy(next_settings))
        return True

    monkeypatch.setattr(service_module, "save_settings", fake_save)
    monkeypatch.setattr(
        service_module,
        "patch_settings_paths",
        lambda changes: fake_save({**deepcopy(stored), **deepcopy(changes)}),
    )
    services = ApplicationServices(account="tester", runtime_bridge=FailingRuntime())
    services._audit = lambda *args, **kwargs: None
    snapshot = services.settings_snapshot()

    result = services.update_settings(
        expected_revision=snapshot["revision"],
        changes={"verbose_trade_logging": True},
    )

    assert stored["verbose_trade_logging"] is True
    assert result["runtime_refresh"] == {
        "ok": False,
        "restart_required": True,
        "error_code": "runtime_refresh_failed",
    }
