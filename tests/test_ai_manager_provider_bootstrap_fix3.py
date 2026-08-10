from trading.ai.ai_manager import (
    ai_workload_route_status,
    create_ai_manager_from_settings,
)


def test_non_openai_provider_bootstraps_without_legacy_openai_key():
    settings = {
        "ai_provider": "deepseek",
        "openai_model": "deepseek-v4-flash",
        "ai_credentials": {
            "deepseek": {"api_key": "deepseek-key", "base_url": "https://api.deepseek.com"},
        },
        "ai_provider_profiles": {
            "analyst": {"provider": "deepseek", "model": "deepseek-v4-flash"},
        },
    }
    assert not settings.get("openai_api_key")
    status = ai_workload_route_status(settings)
    manager = create_ai_manager_from_settings(settings)
    assert status["ready"] is True
    assert status["provider"] == "deepseek"
    assert manager is not None
    assert manager.provider == "deepseek"


def test_selected_workload_without_its_own_key_stays_disabled():
    settings = {
        "ai_provider": "kimi",
        "openai_api_key": "unrelated-openai-key",
        "ai_credentials": {"openai": {"api_key": "unrelated-openai-key"}},
        "ai_provider_profiles": {
            "analyst": {"provider": "kimi", "model": "kimi-k3"},
        },
    }
    assert ai_workload_route_status(settings)["ready"] is False
    assert create_ai_manager_from_settings(settings) is None
