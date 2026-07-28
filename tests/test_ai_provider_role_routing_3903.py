import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from trading.ai.model_registry import (
    model_status_text,
    selectable_models,
    validate_model_route,
)
from trading.ai.provider_router import AIProviderRouter, normalize_model_route
from trading.strategy_source_ingestor import StrategySourceIngestor


def _multi_provider_settings():
    return {
        "ai_provider": "openai",
        "openai_model": "gpt-5.6-luna",
        "assistant_ai_model": "claude-sonnet-5",
        "ai_credentials": {
            "openai": {"api_key": "openai-key", "base_url": ""},
            "deepseek": {"api_key": "deepseek-key", "base_url": "https://api.deepseek.com"},
            "anthropic": {"api_key": "claude-key", "base_url": "https://api.anthropic.com"},
        },
        "ai_provider_profiles": {
            "analyst": {"provider": "openai", "model": "gpt-5.6-luna"},
            "assistant": {"provider": "anthropic", "model": "claude-sonnet-5"},
            "transcription": {"provider": "openai", "model": "gpt-4o-mini-transcribe"},
        },
        "ai_model_roles": {
            "frequent_cheap": {"provider": "deepseek", "model": "deepseek-v4-flash"},
            "standard": {"provider": "openai", "model": "gpt-5.6-terra"},
            "premium": {"provider": "anthropic", "model": "claude-opus-5"},
        },
        "ai_custom_transcription": {
            "enabled": True,
            "provider": "openai",
            "model": "gpt-4o-mini-transcribe",
        },
    }


def test_role_routes_store_provider_and_model_independently():
    settings = _multi_provider_settings()
    cheap = AIProviderRouter.from_settings(settings, workload="frequent_cheap")
    premium = AIProviderRouter.from_settings(settings, workload="premium")
    assert cheap.spec.provider == "deepseek"
    assert cheap.adapter.model == "deepseek-v4-flash"
    assert premium.spec.provider == "anthropic"
    assert premium.adapter.model == "claude-opus-5"


def test_transcription_profile_is_independent_from_analyst_provider():
    settings = _multi_provider_settings()
    settings["ai_provider_profiles"]["analyst"] = {
        "provider": "anthropic",
        "model": "claude-sonnet-5",
    }
    transcription = AIProviderRouter.from_settings(settings, workload="transcription")
    assert transcription.spec.provider == "openai"
    assert transcription.adapter.model == "gpt-4o-mini-transcribe"
    assert transcription.adapter.client.api_key == "openai-key"


def test_strategy_ingestor_keeps_analysis_and_transcription_clients_separate():
    analysis = SimpleNamespace(is_ready=lambda: True)
    transcription = SimpleNamespace(is_ready=lambda: True, transcribe_audio=lambda *_a, **_k: "전사")
    ingestor = StrategySourceIngestor(
        analysis,
        transcription_client=transcription,
    )
    assert ingestor.ai_client is analysis
    assert ingestor.transcription_client is transcription


def test_model_registry_distinguishes_lifecycle_and_capability():
    assert "deepseek-chat" not in selectable_models("deepseek")
    retired = validate_model_route(
        "deepseek",
        "deepseek-chat",
        capability="chat_json",
    )
    assert retired["ok"] is False
    assert retired["replacement"] == "deepseek-v4-flash"
    assert "종료" in model_status_text("deepseek", "deepseek-chat")
    assert "gpt-4o-transcribe-diarize" in selectable_models(
        "openai",
        capability="transcribe",
    )


def test_legacy_model_string_normalizes_without_changing_provider():
    assert normalize_model_route(
        "gpt-4o-mini",
        fallback_provider="openai",
        fallback_model="gpt-5.6-luna",
    ) == {"provider": "openai", "model": "gpt-4o-mini"}


def test_load_settings_migrates_legacy_roles_to_provider_model(tmp_path):
    from config import settings as settings_module

    config_path = tmp_path / "settings.json"
    backup_dir = tmp_path / "backups"
    config_path.write_text(
        json.dumps({
            "ai_provider": "openai",
            "openai_model": "gpt-4o-mini",
            "assistant_ai_model": "gpt-4o",
            "ai_model_roles": {
                "frequent_cheap": "gpt-4o-mini",
                "standard": "gpt-4o",
                "premium": "gpt-4o",
            },
        }),
        encoding="utf-8",
    )
    with patch.object(
        settings_module,
        "_get_settings_paths",
        return_value=(str(config_path), str(backup_dir)),
    ), patch("path_utils.get_config_dir", return_value=str(tmp_path)):
        migrated = settings_module.load_settings()
    assert migrated["ai_model_roles"]["frequent_cheap"] == {
        "provider": "openai",
        "model": "gpt-4o-mini",
    }
    assert migrated["ai_provider_profiles"]["transcription"] == {
        "provider": "openai",
        "model": "gpt-4o-mini-transcribe",
    }


def test_load_settings_preserves_legacy_deepseek_provider(tmp_path):
    from config import settings as settings_module

    config_path = tmp_path / "settings.json"
    backup_dir = tmp_path / "backups"
    config_path.write_text(
        json.dumps({
            "openai_base_url": "https://api.deepseek.com",
            "openai_model": "deepseek-chat",
            "assistant_ai_model": "deepseek-reasoner",
            "ai_model_roles": {
                "frequent_cheap": "deepseek-chat",
                "standard": "deepseek-chat",
                "premium": "deepseek-reasoner",
            },
        }),
        encoding="utf-8",
    )
    with patch.object(
        settings_module,
        "_get_settings_paths",
        return_value=(str(config_path), str(backup_dir)),
    ), patch("path_utils.get_config_dir", return_value=str(tmp_path)):
        migrated = settings_module.load_settings()
    assert migrated["ai_provider"] == "deepseek"
    assert migrated["ai_provider_profiles"]["analyst"] == {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
    }
    assert migrated["ai_model_roles"]["premium"] == {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
    }
