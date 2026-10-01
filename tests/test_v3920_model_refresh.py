"""2026-10-01 catalog and wire contracts. No credentials, paid API or orders."""
from types import SimpleNamespace as NS

import pytest

from trading.ai.anthropic_client import AnthropicClient
from trading.ai.model_registry import selectable_models, validate_model_route
from trading.ai.openai_client import OpenAIClient
from trading.ai.provider_catalog import model_catalog_details
from trading.ai.provider_router import AIProviderRouter
from web_platform.interactive_ai import InteractiveAIService


def fake_completion(client, captured, content='{"ok":true}'):
    def create(**kwargs):
        captured.update(kwargs)
        return NS(
            model=kwargs["model"], id="mock-only", usage=NS(prompt_tokens=20, completion_tokens=5, total_tokens=25),
            choices=[NS(message=NS(content=content), finish_reason="stop")],
        )
    client._client = NS(chat=NS(completions=NS(create=create)))


@pytest.mark.parametrize("provider,model,vision", [
    ("openai", "gpt-6-luna", True), ("openai", "gpt-6-sol", True),
    ("openai", "gpt-6.1-sol", True), ("deepseek", "deepseek-flash", True),
    ("kimi", "kimi-k2.7-code", True), ("kimi", "kimi-k2.7-code-highspeed", True),
    ("anthropic", "claude-sonnet-5-5", False), ("anthropic", "claude-opus-5-5", False),
    ("gemini", "gemini-3.8-flash", True),
])
def test_new_catalog_keeps_capability_and_account_checks_separate(provider, model, vision):
    for capability in ("chat_text", "chat_json"):
        assert model in selectable_models(provider, capability=capability)
        assert validate_model_route(provider, model, capability=capability)["ok"]
        assert not validate_model_route(provider, model, capability=capability, account_models=[])["ok"]
    assert (model in selectable_models(provider, capability="vision")) is vision
    assert model not in selectable_models(provider, capability="transcribe")


@pytest.mark.parametrize("model,effort", [("gpt-6-luna", "none"), ("gpt-6-sol", "none"), ("gpt-6.1-sol", "low"), ("gpt-6-astra", "low")])
@pytest.mark.parametrize("capability", ["chat_text", "chat_json"])
def test_real_probe_path_accepts_json_reasoning_keyword(model, effort, capability):
    router = AIProviderRouter("openai", api_key="mock", model=model)
    captured = {}
    fake_completion(router.adapter.client, captured)
    result = router.probe_model(capability=capability)
    assert result["ok"] and result["actual_model"] == model
    assert captured["reasoning_effort"] == effort
    assert captured["max_completion_tokens"] == 64
    assert "max_tokens" not in captured
    assert captured["store"] is False


@pytest.mark.parametrize("provider,model,limit_key", [
    ("openai", "gpt-6-luna", "max_completion_tokens"),
    ("openai", "gpt-6.1-sol", "max_completion_tokens"),
    ("kimi", "kimi-k2.7-code", "max_tokens"),
    ("deepseek", "deepseek-flash", "max_tokens"),
    ("gemini", "gemini-3.8-flash", "max_tokens"),
])
@pytest.mark.parametrize("workload", ["text", "json", "vision"])
def test_model_request_contracts(provider, model, limit_key, workload, tmp_path):
    client = OpenAIClient(api_key="mock", model=model, provider=provider)
    captured = {}
    fake_completion(client, captured)
    if workload == "vision":
        image = tmp_path / "mock.png"
        image.write_bytes(b"mock image bytes; no provider request")
        assert client.vision_json("Return JSON", "inspect", [str(image)], max_tokens=500) == {"ok": True}
    elif workload == "json":
        assert client.chat_json("Return JSON", "inspect", max_tokens=500) == {"ok": True}
    else:
        assert client.chat("system", "hello", max_tokens=500, temperature=0.2, top_p=0.2)
    assert captured[limit_key] == 500
    assert ("max_tokens" if limit_key == "max_completion_tokens" else "max_completion_tokens") not in captured
    if provider in {"openai", "kimi", "gemini"}:
        assert "temperature" not in captured
    if provider == "kimi":
        assert "top_p" not in captured


def test_luna_explicit_none_keeps_sampling_and_token_cap():
    client = OpenAIClient(api_key="", provider="openai")
    options = client._sanitize_completion_options("gpt-6-luna", {
        "max_tokens": 50, "max_completion_tokens": 80, "reasoning_effort": "none", "temperature": 0.2,
    })
    assert options == {"max_completion_tokens": 80, "reasoning_effort": "none", "temperature": 0.2}


@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1", "claude-opus-4-7", "claude-opus-5-5-20260922"])
def test_claude_current_models_omit_sampling_and_record_actual_model(monkeypatch, model):
    client = AnthropicClient(api_key="mock", model=model)
    captured = {}
    def request(method, path, payload):
        captured.update(payload)
        return {"model": "provider-actual-id", "content": [{"type": "text", "text": '{"ok":true}'}], "usage": {"input_tokens": 3, "output_tokens": 2}}
    monkeypatch.setattr(client, "_request_json", request)
    assert client.chat_json("system", "hello") == {"ok": True}
    assert "temperature" not in captured
    assert client.get_last_usage()["requested_model"] == model
    assert client.get_last_usage()["model"] == "provider-actual-id"


def test_prices_preserve_unknowns_and_current_standard_rates():
    estimate = InteractiveAIService._estimate_cost
    assert estimate("openai", "gpt-6-luna", {"input_tokens": 1000, "output_tokens": 1000}) == 0.0006
    assert estimate("openai", "gpt-6-luna-2026-09-01", {"input_tokens": 1000, "output_tokens": 1000}) == 0.0006
    assert estimate("openai", "gpt-6-luna", {"input_tokens": 300_000, "output_tokens": 1000}) == 0.06075
    assert estimate("openai", "gpt-6-luna", {}) is None
    assert estimate("openai", "gpt-6-luna-custom", {"input_tokens": 1000}) is None
    assert estimate("kimi", "kimi-k2.7-code-highspeed", {"input_tokens": 1000}) is None
    rows = {r["model"]: r for r in model_catalog_details("deepseek")}
    assert rows["deepseek-v4-flash"]["replacement"] == "deepseek-flash"
    assert "임시 호환" in rows["deepseek-v4-flash"]["note"]
    assert rows["deepseek-flash"]["input_per_mtok_usd"] == .3


def test_unknown_account_model_is_not_silently_certified():
    result = validate_model_route("openai", "gpt-future", capability="chat_json", account_models=["gpt-future"])
    assert result["ok"] and result["status"] == "unknown" and result["warnings"]


def test_existing_default_and_explicit_routes_are_not_migrated():
    from config.settings import get_default_settings
    settings = get_default_settings()
    assert settings["openai_model"] == "gpt-5.6-luna"
    assert settings["ai_model_roles"]["frequent_cheap"]["model"] == "gpt-5.6-luna"
    for provider, model in (("openai", "gpt-5.6-luna"), ("deepseek", "deepseek-v4-flash"), ("anthropic", "claude-sonnet-5")):
        assert AIProviderRouter(provider, api_key="", model=model).adapter.model == model
