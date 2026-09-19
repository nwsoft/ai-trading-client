import json
import os
import stat
from types import SimpleNamespace
from unittest.mock import patch

from trading.ai.credentials import (
    hydrate_ai_credentials,
    prepare_ai_credentials_for_storage,
)
from trading.ai.openai_client import OpenAIClient
from trading.ai.provider_router import (
    AIProviderRouter,
    PROVIDER_SPECS,
    provider_capability_schema,
)


def test_provider_capability_schema_has_required_v3903_providers():
    schema = provider_capability_schema()
    assert set(schema) == {"openai", "deepseek", "kimi", "anthropic", "gemini"}
    assert schema["deepseek"]["capabilities"]["chat_json"] is True
    assert schema["kimi"]["status"] == "stable"
    assert schema["deepseek"]["capabilities"]["transcribe"] is False
    assert schema["anthropic"]["capabilities"]["structured_output"] is False
    assert schema["gemini"]["capabilities"]["vision"] is True


def test_default_settings_include_router_models_and_saver_policy():
    from config.settings import get_default_settings

    settings = get_default_settings()
    assert settings["ai_provider"] == "openai"
    assert set(settings["ai_provider_profiles"]) == {"analyst", "assistant", "transcription"}
    assert settings["ai_provider_profiles"]["transcription"]["provider"] == "openai"
    assert settings["ai_model_roles"]["premium"] == {
        "provider": "openai",
        "model": "gpt-5.6-sol",
    }
    assert set(settings["ai_models"]) == {"analyst", "assistant", "roles"}
    assert settings["assistant_response_mode"] == "standard"
    assert settings["assistant_token_budget"]["saver"]["max_output_tokens"] == 500
    assert settings["assistant_context_policy"]["saver"]["include_recent_turns"] == 4


def test_deepseek_router_uses_current_models_and_official_endpoint():
    router = AIProviderRouter(
        "deepseek",
        api_key="test-key",
        model="deepseek-v4-flash",
    )
    assert router.spec.base_url == "https://api.deepseek.com"
    assert "deepseek-v4-flash" in router.spec.fallback_models
    assert "deepseek-chat" not in PROVIDER_SPECS["deepseek"].fallback_models


def test_claude_uses_native_anthropic_messages_client():
    from trading.ai.anthropic_client import AnthropicClient

    router = AIProviderRouter("anthropic", api_key="sk-ant-test", model="claude-sonnet-4-6")
    assert isinstance(router.adapter.client, AnthropicClient)
    assert router.spec.base_url == "https://api.anthropic.com"


def test_gemini_uses_official_openai_compatibility_endpoint():
    router = AIProviderRouter("gemini", api_key="test", model="gemini-3.6-flash")
    assert router.spec.base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert "gemini-3.6-flash" in router.spec.fallback_models


def test_openai_compatible_client_distinguishes_packaging_failure_from_missing_key():
    with patch("trading.ai.openai_client.OpenAI", None):
        client = OpenAIClient(api_key="present-but-not-printed", provider="openai")
    error = client.get_initialization_error()
    assert client.is_ready() is False
    assert error["code"] == "provider_sdk_unavailable"
    assert "present-but-not-printed" not in json.dumps(error)


def test_router_from_settings_keeps_legacy_openai_compatible():
    router = AIProviderRouter.from_settings(
        {
            "openai_api_key": "legacy-key",
            "openai_model": "gpt-4o-mini",
            "assistant_ai_model": "gpt-4o",
        },
        workload="assistant",
    )
    assert router.spec.provider == "openai"
    assert router.adapter.client.api_key == "legacy-key"
    assert router.adapter.model == "gpt-4o"


def test_legacy_selected_provider_key_survives_empty_structured_template_entries():
    settings = {
        "ai_provider": "deepseek",
        "openai_api_key": "legacy-selected-provider-key",
        "openai_base_url": "https://api.deepseek.com",
        "openai_model": "deepseek-v4-flash",
        "ai_credentials": {
            "openai": {"api_key": "", "base_url": ""},
            "deepseek": {"api_key": "", "base_url": "https://api.deepseek.com"},
            "kimi": {"api_key": "", "base_url": "https://api.moonshot.ai/v1"},
            "anthropic": {"api_key": "", "base_url": "https://api.anthropic.com"},
            "gemini": {"api_key": "", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/"},
        },
        "ai_provider_profiles": {
            "analyst": {"provider": "deepseek", "model": "deepseek-v4-flash"},
        },
    }
    hydrated = hydrate_ai_credentials(settings)
    assert hydrated["ai_credentials"]["deepseek"]["api_key"] == "legacy-selected-provider-key"
    assert hydrated["ai_credentials"]["openai"]["api_key"] == ""
    router = AIProviderRouter.from_settings(settings, workload="analyst")
    assert router.spec.provider == "deepseek"
    assert router.adapter.client.api_key == "legacy-selected-provider-key"


def test_legacy_alias_is_not_borrowed_when_a_structured_provider_owns_it():
    settings = {
        "ai_provider": "deepseek",
        "openai_api_key": "openai-owned-key",
        "ai_credentials": {
            "openai": {"api_key": "openai-owned-key"},
            "deepseek": {"api_key": ""},
        },
        "ai_provider_profiles": {
            "analyst": {"provider": "deepseek", "model": "deepseek-v4-flash"},
        },
    }
    router = AIProviderRouter.from_settings(settings, workload="analyst")
    assert router.adapter.client.api_key == ""


def test_kimi_profile_routes_independently_by_workload():
    settings = {
        "ai_provider": "openai",
        "openai_api_key": "openai-key",
        "openai_model": "gpt-4o-mini",
        "assistant_ai_model": "kimi-k3",
        "ai_credentials": {
            "openai": {"api_key": "openai-key", "base_url": ""},
            "kimi": {"api_key": "kimi-key", "base_url": "https://api.moonshot.ai/v1"},
        },
        "ai_provider_profiles": {
            "analyst": {"provider": "openai", "model": "gpt-4o-mini"},
            "assistant": {"provider": "kimi", "model": "kimi-k3"},
        },
    }
    analyst = AIProviderRouter.from_settings(settings, workload="analyst")
    assistant = AIProviderRouter.from_settings(settings, workload="assistant")
    assert analyst.spec.provider == "openai"
    assert assistant.spec.provider == "kimi"
    assert assistant.adapter.client.api_key == "kimi-key"


def test_kimi_can_route_analyst_json_workload():
    settings = {
        "ai_provider": "kimi",
        "openai_model": "kimi-k2.6",
        "ai_credentials": {"kimi": {"api_key": "kimi-key"}},
        "ai_provider_profiles": {
            "analyst": {"provider": "kimi", "model": "kimi-k2.6"},
        },
    }
    analyst = AIProviderRouter.from_settings(settings, workload="analyst")
    validation = analyst.validate_model(capability="chat_json")
    assert analyst.spec.provider == "kimi"
    assert analyst.adapter.client.api_key == "kimi-key"
    assert validation["ok"] is True


def test_model_listing_accepts_provider_prefixes():
    client = OpenAIClient(api_key="")
    client._client = SimpleNamespace(
        models=SimpleNamespace(
            list=lambda: SimpleNamespace(
                data=[
                    SimpleNamespace(id="deepseek-v4-flash"),
                    SimpleNamespace(id="deepseek-v4-pro"),
                    SimpleNamespace(id="gpt-4o-mini"),
                ]
            )
        )
    )
    assert client.list_chat_models(("deepseek-",)) == [
        "deepseek-v4-pro",
        "deepseek-v4-flash",
    ]


def test_local_credential_round_trip_keeps_provider_key_without_os_dependency():
    settings = {
        "ai_provider": "deepseek",
        "openai_api_key": "secret-value",
        "ai_credentials": {
            "deepseek": {
                "api_key": "secret-value",
                "base_url": "https://api.deepseek.com",
            }
        },
    }
    stored, warnings = prepare_ai_credentials_for_storage(settings, strict=True)
    assert warnings == []
    assert stored["openai_api_key"] == "secret-value"
    assert stored["ai_credentials"]["deepseek"]["api_key"] == "secret-value"
    assert "credential_ref" not in stored["ai_credentials"]["deepseek"]

    hydrated = hydrate_ai_credentials(stored)
    assert hydrated["ai_credentials"]["deepseek"]["api_key"] == "secret-value"
    assert hydrated["openai_api_key"] == "secret-value"


def test_existing_alphaarena_key_stays_local_without_enabling_multi_engine():
    settings = {
        "alpha_arena": {
            "engine": "deepseek-v4-flash",
            "deepseek_api_key": "arena-secret",
            "credential_refs": {"deepseek": "keyring://NoahAI/old.deepseek"},
        },
        "alphaarena_deepseek_api_key": "arena-secret",
    }
    stored, warnings = prepare_ai_credentials_for_storage(settings, strict=True)
    assert warnings == []
    assert stored["alpha_arena"]["engine"] == "deepseek-v4-flash"
    assert stored["alpha_arena"]["deepseek_api_key"] == "arena-secret"
    assert stored["alphaarena_deepseek_api_key"] == "arena-secret"
    assert "credential_refs" not in stored["alpha_arena"]

    hydrated = hydrate_ai_credentials(stored)
    assert hydrated["alpha_arena"]["deepseek_api_key"] == "arena-secret"


def test_usage_normalizes_kimi_cached_tokens_and_finish_reason():
    client = OpenAIClient(api_key="", provider="kimi")
    completion = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            cached_tokens=4,
            prompt_tokens_details=None,
        ),
        choices=[SimpleNamespace(finish_reason="stop")],
    )
    client._record_usage(completion, "kimi-k3")
    assert client.get_last_usage() == {
        "provider": "kimi",
        "model": "kimi-k3",
        "requested_model": "kimi-k3",
        "input_tokens": 10,
        "cached_input_tokens": 4,
        "output_tokens": 5,
        "total_tokens": 15,
    }
    assert client.get_last_response_meta()["finish_reason"] == "stop"


def test_usage_preserves_requested_and_provider_response_model():
    client = OpenAIClient(api_key="", provider="openai")
    completion = SimpleNamespace(
        id="chatcmpl-diagnostic",
        model="gpt-6-astra-2026-09-01",
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=1, total_tokens=4),
        choices=[SimpleNamespace(finish_reason="stop")],
    )

    client._record_usage(completion, "gpt-6-astra")

    assert client.get_last_usage()["requested_model"] == "gpt-6-astra"
    assert client.get_last_usage()["model"] == "gpt-6-astra-2026-09-01"
    assert client.get_last_response_meta()["response_id"] == "chatcmpl-diagnostic"


def test_gpt6_chat_uses_reasoning_compatible_completion_parameters():
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                id="chatcmpl-astra",
                model="gpt-6-astra",
                choices=[SimpleNamespace(message=SimpleNamespace(content="OK"), finish_reason="stop")],
                usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1, total_tokens=3),
            )

    client = OpenAIClient(api_key="test", model="gpt-6-astra", provider="openai")
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))

    assert client.chat(
        "system",
        "user",
        max_tokens=64,
        temperature=0.2,
        top_p=0.8,
        logprobs=True,
        top_logprobs=2,
        reasoning_effort="low",
    ) == "OK"
    assert captured["max_completion_tokens"] == 64
    assert captured["reasoning_effort"] == "low"
    assert "max_tokens" not in captured
    assert "temperature" not in captured
    assert "top_p" not in captured
    assert "logprobs" not in captured
    assert "top_logprobs" not in captured


def test_router_probe_calls_selected_model_and_reports_provider_model(monkeypatch):
    router = AIProviderRouter("openai", api_key="test", model="gpt-6-astra")
    observed = {}

    def fake_chat(system, prompt, **kwargs):
        observed.update({"system": system, "prompt": prompt, **kwargs})
        return SimpleNamespace(
            ok=True,
            requested_model="gpt-6-astra",
            model="gpt-6-astra-2026-09-01",
            usage={"model": "gpt-6-astra-2026-09-01", "total_tokens": 4},
            finish_reason="stop",
            error=None,
        )

    monkeypatch.setattr(router.adapter, "chat_text", fake_chat)
    monkeypatch.setattr(router.adapter.client, "get_last_response_meta", lambda: {"response_id": "chatcmpl-probe"})

    result = router.probe_model(capability="chat_text")

    assert result["ok"] is True
    assert result["requested_model"] == "gpt-6-astra"
    assert result["actual_model"] == "gpt-6-astra-2026-09-01"
    assert result["response_id"] == "chatcmpl-probe"
    assert observed["model"] == "gpt-6-astra"
    assert observed["reasoning_effort"] == "low"
    assert "계좌" not in observed["prompt"]


def test_invalid_json_is_normalized_as_contract_error():
    completion = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="not-json"),
                finish_reason="stop",
            )
        ],
    )
    client = OpenAIClient(api_key="", provider="deepseek")
    client._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **_kwargs: completion)
        )
    )
    assert client.chat_json("system", "user", model="deepseek-v4-flash") is None
    assert client.get_last_error()["code"] == "invalid_json"


def test_kimi_k3_uses_current_completion_limit_without_temperature():
    captured = {}
    completion = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2, cached_tokens=0),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok"),
                finish_reason="stop",
            )
        ],
    )

    def create(**kwargs):
        captured.update(kwargs)
        return completion

    client = OpenAIClient(api_key="", provider="kimi", model="kimi-k3")
    client._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    assert client.chat("system", "user", max_tokens=500, temperature=0.2) == "ok"
    assert captured["max_completion_tokens"] == 500
    assert "max_tokens" not in captured
    assert "temperature" not in captured


def test_save_settings_keeps_local_ai_key_and_private_file_mode(tmp_path):
    from config.settings import save_settings

    config_path = tmp_path / "settings.json"
    backup_dir = tmp_path / "backups"
    config_path.write_text(
        json.dumps({"openai_api_key": "old-plaintext-secret"}),
        encoding="utf-8",
    )
    settings = {
        "ai_provider": "openai",
        "openai_api_key": "secret-value",
        "ai_credentials": {
            "openai": {"api_key": "secret-value", "base_url": ""},
        },
    }
    with patch(
        "config.settings._get_settings_paths",
        return_value=(str(config_path), str(backup_dir)),
    ):
        assert save_settings(settings) is True

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["openai_api_key"] == "secret-value"
    assert persisted["ai_credentials"]["openai"]["api_key"] == "secret-value"
    assert "credential_ref" not in persisted["ai_credentials"]["openai"]
    if os.name != "nt":
        assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    backups = list(backup_dir.glob("settings_*.json"))
    assert len(backups) == 1
    assert "old-plaintext-secret" in backups[0].read_text(encoding="utf-8")


def test_reset_preserves_local_api_key_and_unresolved_reference():
    from config.settings import _preserve_sensitive_values

    current = {
        "ai_credentials": {
            "openai": {
                "api_key": "local-secret",
                "credential_ref": "keyring://NoahAI/account.openai",
                "base_url": "",
            }
        }
    }
    defaults = {
        "ai_credentials": {
            "openai": {
                "credential_ref": "",
                "base_url": "",
            }
        }
    }
    merged = _preserve_sensitive_values(current, defaults)
    assert merged["ai_credentials"]["openai"]["api_key"] == "local-secret"
    assert merged["ai_credentials"]["openai"]["credential_ref"] == "keyring://NoahAI/account.openai"
