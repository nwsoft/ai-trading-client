import json
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


class _MemoryKeyring:
    def __init__(self):
        self.values = {}

    def set_password(self, service, username, value):
        self.values[(service, username)] = value

    def get_password(self, service, username):
        return self.values.get((service, username))


def test_provider_capability_schema_has_required_v3903_providers():
    schema = provider_capability_schema()
    assert set(schema) == {"openai", "deepseek", "kimi", "anthropic", "gemini"}
    assert schema["deepseek"]["capabilities"]["chat_json"] is True
    assert schema["kimi"]["status"] == "experimental"
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


def test_kimi_experimental_profile_routes_assistant_only():
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


def test_credential_reference_round_trip_and_disk_scrubbing():
    memory_keyring = _MemoryKeyring()
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
    with patch("trading.ai.credentials._keyring_module", return_value=memory_keyring):
        stored, warnings = prepare_ai_credentials_for_storage(settings, strict=True)
        assert warnings == []
        assert stored["openai_api_key"] == ""
        assert "api_key" not in stored["ai_credentials"]["deepseek"]
        assert stored["ai_credentials"]["deepseek"]["credential_ref"].startswith("keyring://NoahAI/")

        hydrated = hydrate_ai_credentials(stored)
        assert hydrated["ai_credentials"]["deepseek"]["api_key"] == "secret-value"
        assert hydrated["openai_api_key"] == "secret-value"


def test_existing_alphaarena_key_is_secured_without_enabling_multi_engine():
    memory_keyring = _MemoryKeyring()
    settings = {
        "alpha_arena": {
            "engine": "deepseek-v4-flash",
            "deepseek_api_key": "arena-secret",
        },
        "alphaarena_deepseek_api_key": "arena-secret",
    }
    with patch("trading.ai.credentials._keyring_module", return_value=memory_keyring):
        stored, warnings = prepare_ai_credentials_for_storage(settings, strict=True)
        assert warnings == []
        assert stored["alpha_arena"]["engine"] == "deepseek-v4-flash"
        assert stored["alpha_arena"]["deepseek_api_key"] == ""
        assert stored["alphaarena_deepseek_api_key"] == ""
        assert stored["alpha_arena"]["credential_refs"]["deepseek"].startswith("keyring://NoahAI/")

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
        "input_tokens": 10,
        "cached_input_tokens": 4,
        "output_tokens": 5,
        "total_tokens": 15,
    }
    assert client.get_last_response_meta()["finish_reason"] == "stop"


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


def test_save_settings_writes_only_credential_reference_and_private_mode(tmp_path):
    from config.settings import save_settings

    memory_keyring = _MemoryKeyring()
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
    with (
        patch("trading.ai.credentials._keyring_module", return_value=memory_keyring),
        patch("config.settings._get_settings_paths", return_value=(str(config_path), str(backup_dir))),
    ):
        assert save_settings(settings) is True

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["openai_api_key"] == ""
    assert "api_key" not in persisted["ai_credentials"]["openai"]
    assert persisted["ai_credentials"]["openai"]["credential_ref"].startswith("keyring://NoahAI/")
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    backups = list(backup_dir.glob("settings_*.json"))
    assert len(backups) == 1
    assert "old-plaintext-secret" not in backups[0].read_text(encoding="utf-8")


def test_reset_preserves_credential_reference():
    from config.settings import _preserve_sensitive_values

    current = {
        "ai_credentials": {
            "openai": {
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
    assert merged["ai_credentials"]["openai"]["credential_ref"] == "keyring://NoahAI/account.openai"
