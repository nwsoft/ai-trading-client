"""v40 regressions: no network, credentials, orders or paid model calls."""
from collections import deque
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from trading.alpha_arena.configuration import alpha_arena_ai_settings
from trading.alpha_arena.runner import AlphaArenaRunner
from web_platform.headless_runtime import HeadlessTradingRuntime


def settings(**changes):
    return {"paper_trading": True, "alpha_arena": {
        "enabled": True, "deepseek_api_key": "dummy-arena-only",
        "engine": "deepseek-v4-flash", "tick_interval_sec": 60,
        "max_risk_per_tick": 100,
    }, **changes}


def runtime(config):
    app = object.__new__(HeadlessTradingRuntime)
    app.settings = deepcopy(config)
    app.alpha_arena_runner = None
    app._alpha_arena_events = deque(maxlen=200)
    app.binance_client = Mock()
    app.ai_manager = Mock(name="general_ai_must_not_be_used")
    app.recorder = None
    app.assert_command_allowed = Mock()
    app._configure_account_logging = Mock()
    app._refresh_connection_clients = Mock()
    return app


@pytest.mark.parametrize("paper", [False, True])
def test_runner_never_reaches_live_executor_even_after_mode_switch(paper):
    runner = AlphaArenaRunner(settings=settings())
    runner.running = True
    runner.settings["paper_trading"] = paper
    runner.order_executor.execute_trading_decision = Mock()
    runner.order_executor._check_trade_gates = Mock(return_value={"allowed": True})
    runner._execute_trading_decisions({"BTC": {"signal": "ENTER_LONG", "risk_usd": 10}})
    runner.order_executor.execute_trading_decision.assert_not_called()
    if not paper:
        assert not runner.running
        assert runner.stop_event.is_set()


def test_direct_live_start_fails_before_balance_or_ai_call():
    runner = AlphaArenaRunner(binance_client=Mock(), settings=settings(paper_trading=False))
    assert runner.start() is False
    runner.binance_client.get_balance.assert_not_called()


def test_stop_pending_thread_cannot_restart_or_clear_stop_signal():
    runner = AlphaArenaRunner(settings=settings())
    runner.run_thread = Mock()
    runner.run_thread.is_alive.return_value = True
    runner.stop_event.set()
    assert runner.start() is False
    assert runner.stop_event.is_set()


def test_late_ai_response_after_stop_is_not_published_or_executed():
    runner = AlphaArenaRunner(settings=settings())
    runner.running = True
    runner.prompt_builder.build_prompt = Mock(return_value="dummy prompt")
    def respond_after_stop(prompt):
        runner.stop()
        return "late response"
    runner._call_llm = respond_after_stop
    runner.response_parser.parse_response = Mock()
    runner._execute_trading_decisions = Mock()
    runner._execute_tick()
    runner.response_parser.parse_response.assert_not_called()
    runner._execute_trading_decisions.assert_not_called()


def test_paper_candidates_share_tick_risk_and_cooldown_without_fake_pnl():
    runner = AlphaArenaRunner(settings=settings())
    runner.running = True
    runner.order_executor._count_active_positions = Mock(return_value=0)
    runner.order_executor.execute_trading_decision = Mock()
    rows = []
    runner.on_order_result = lambda symbol, result: rows.append(result)
    decision = {"signal": "ENTER_LONG", "profit_target": 110, "stop_loss": 90, "risk_usd": 60}
    runner._execute_trading_decisions({"BTC": decision, "ETH": decision})
    assert [row["status"] for row in rows] == ["SIMULATED", "SKIPPED"]
    assert "리스크 캡" in rows[1]["skip_reason"]
    runner._execute_trading_decisions({"BTC": decision})
    assert "쿨다운" in rows[-1]["skip_reason"]
    assert all("pnl" not in row and row["order_submitted"] is False for row in rows)
    runner.order_executor.execute_trading_decision.assert_not_called()


@pytest.mark.parametrize("change", ["live", "disable", "risk", "key"])
def test_settings_changes_stop_cached_runner_and_require_new_session(change):
    original = settings()
    app = runtime(original)
    runner = AlphaArenaRunner(settings=deepcopy(original))
    runner.running = True
    app.alpha_arena_runner = runner
    updated = deepcopy(original)
    if change == "live": updated["paper_trading"] = False
    if change == "disable": updated["alpha_arena"]["enabled"] = False
    if change == "risk": updated["alpha_arena"]["max_risk_per_tick"] = 5
    if change == "key": updated["alpha_arena"]["deepseek_api_key"] = "dummy-new"
    app.refresh_settings(updated)
    assert not runner.running
    assert runner.stop_event.is_set()
    assert app.alpha_arena_runner is None
    assert app.settings == updated


def test_unchanged_settings_do_not_stop_runner():
    app = runtime(settings())
    app.alpha_arena_runner = Mock()
    app.refresh_settings(deepcopy(app.settings))
    app.alpha_arena_runner.stop.assert_not_called()


def test_inflight_request_preserved_until_terminated_and_cannot_restart():
    app = runtime(settings())
    runner = AlphaArenaRunner(settings=deepcopy(app.settings))
    runner.running = True
    runner.run_thread = Mock()
    runner.run_thread.is_alive.return_value = True
    app.alpha_arena_runner = runner
    updated = deepcopy(app.settings)
    updated["alpha_arena"]["max_risk_per_tick"] = 5
    app.refresh_settings(updated)
    assert app.alpha_arena_runner is runner
    assert not runner.running
    with pytest.raises(RuntimeError, match="이전 요청 종료 대기"):
        app.alpha_arena_control(action="start")


def test_dedicated_ai_route_never_uses_general_or_shared_key():
    original = settings(ai_provider="openai", ai_credentials={
        "openai": {"api_key": "dummy-general"}, "openai_shared": {"api_key": "dummy-shared"},
    })
    routed = alpha_arena_ai_settings(original)
    from trading.ai.provider_router import AIProviderRouter
    router = AIProviderRouter.from_settings(routed, workload="analyst")
    assert router.spec.provider == "deepseek"
    assert router.adapter.client.api_key == "dummy-arena-only"
    assert router.adapter.model == "deepseek-v4-flash"
    assert original["ai_provider"] == "openai"


def test_missing_arena_key_does_not_fall_back():
    original = settings(ai_credentials={"deepseek": {"api_key": "dummy-general"}})
    original["alpha_arena"]["deepseek_api_key"] = ""
    with pytest.raises(ValueError, match="전용 DeepSeek"):
        alpha_arena_ai_settings(original)


def test_start_constructs_dedicated_manager_and_fresh_runner():
    app = runtime(settings())
    dedicated = Mock()
    with patch("web_platform.headless_runtime.create_ai_manager_from_settings", return_value=dedicated) as factory, patch("trading.alpha_arena.runner.AlphaArenaRunner") as cls:
        runner = cls.return_value
        runner.running = False
        runner.start.return_value = True
        runner.get_status.return_value = {"running": True}
        result = app.alpha_arena_control(action="start")
        assert factory.call_args.args[0]["ai_credentials"]["deepseek"]["api_key"] == "dummy-arena-only"
        assert cls.call_args.kwargs["ai_manager"] is dedicated
        assert cls.call_args.kwargs["settings"] is not app.settings
        assert result["order_submission"] is False
        callback = runner.set_callbacks.call_args.kwargs["on_order_result"]
        callback("BTCUSDT", {"status": "SIMULATED"})
        assert app._alpha_arena_events[-1]["kind"] == "paper_result"


def test_stop_allowed_when_disabled_and_live():
    app = runtime(settings(paper_trading=False))
    app.settings["alpha_arena"]["enabled"] = False
    app.alpha_arena_runner = Mock()
    app.alpha_arena_runner.get_status.return_value = {"running": False}
    result = app.alpha_arena_control(action="stop")
    app.alpha_arena_runner.stop.assert_called_once()
    assert not result["available"]
    assert result["order_submission"] is False


@pytest.mark.parametrize("scope", ["alpha:deepseek", "openai_shared"])
def test_gateway_accepts_explicit_credential_scope_and_keeps_intent_gate(tmp_path, monkeypatch, scope):
    from fastapi.testclient import TestClient
    from web_platform.application_services import ApplicationServices
    from web_platform.gateway import create_gateway_app
    monkeypatch.setattr("web_platform.application_services.get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr("web_platform.application_services.set_current_user_account", lambda account: None)
    service = ApplicationServices(account="tester")
    service.check_ai_provider = Mock(return_value={"credential_scope": scope, "model_callable": True})
    token = "v40-isolated-token-at-least-32-characters"
    client = TestClient(create_gateway_app(token=token, application_services=service))
    auth = {"Authorization": f"Bearer {token}"}
    body = {"provider": scope, "model": "", "capability": "chat_text"}
    assert client.post("/api/v1/settings/ai-provider-check", headers=auth, json=body).status_code == 428
    response = client.post("/api/v1/settings/ai-provider-check", headers={**auth, "X-NoahAI-Intent": "confirmed"}, json=body)
    assert response.status_code == 200
    service.check_ai_provider.assert_called_once_with(**body)


def test_alpha_probe_uses_same_saved_key_and_model_as_execution(tmp_path, monkeypatch):
    from web_platform.application_services import ApplicationServices
    monkeypatch.setattr("web_platform.application_services.get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr("web_platform.application_services.set_current_user_account", lambda account: None)
    stored = settings()
    stored["alpha_arena"]["engine"] = "deepseek-v4-pro"
    monkeypatch.setattr("web_platform.application_services.load_settings", lambda **kwargs: deepcopy(stored))
    router = Mock()
    router.health_check.return_value = {"ok": False, "errors": ["mock offline"]}
    router.validate_model.return_value = {"model": "deepseek-v4-pro", "errors": []}
    with patch("web_platform.application_services.AIProviderRouter.from_settings", return_value=router) as factory:
        result = ApplicationServices(account="tester").check_ai_provider(provider="alpha:deepseek", model="untrusted-override")
    config = factory.call_args.args[0]
    assert config["ai_provider_profiles"]["analyst"]["model"] == "deepseek-v4-pro"
    assert config["ai_credentials"]["deepseek"]["api_key"] == "dummy-arena-only"
    assert result["diagnostic_scope"] == "alpha:deepseek"
    router.probe_model.assert_not_called()
