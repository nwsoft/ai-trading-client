from copy import deepcopy
import json
from pathlib import Path

from scripts.audit_settings_ai_assistant_contract import audit
from config.settings import migrate_webui_enum_contracts
from web_platform.contracts import AssistantQueryContract


def test_settings_and_ai_assistant_full_source_contract():
    errors, summary = audit()
    assert errors == []
    assert summary["legacy_visible_fields"] >= 50
    assert summary["sections"] == 9
    assert summary["leaf_ownership"]["unowned"] == 0


def test_early_webui_enum_values_migrate_to_runtime_contract():
    settings = {
        "assistant_response_mode": "beginner",
        "ai_custom_features": {"profile": "laboratory", "overrides": {}},
    }
    migrated, changed = migrate_webui_enum_contracts(settings)
    assert changed is True
    assert migrated["assistant_response_mode"] == "saver"
    assert migrated["ai_custom_features"]["profile"] == "lab"


def test_web_ai_models_are_provider_scoped_dropdowns_with_fixed_transcription_provider(tmp_path, monkeypatch):
    import web_platform.application_services as module

    stored = json.loads((Path(module.__file__).parents[1] / "config" / "settings_template.json").read_text(encoding="utf-8"))
    stored["ai_provider_profiles"]["analyst"] = {"provider": "deepseek", "model": "deepseek-v4-flash"}
    stored["ai_provider_profiles"]["assistant"] = {"provider": "openai", "model": "legacy-account-model"}
    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(module, "load_settings", lambda **kwargs: deepcopy(stored))

    snapshot = module.ApplicationServices(account="tester").settings_snapshot()
    fields = {field["path"]: field for field in snapshot["fields"]}
    model_paths = {
        "ai_provider_profiles.analyst.model",
        "ai_provider_profiles.assistant.model",
        "ai_model_roles.frequent_cheap.model",
        "ai_model_roles.standard.model",
        "ai_model_roles.premium.model",
        "ai_custom_transcription.model",
    }
    assert {fields[path]["kind"] for path in model_paths} == {"model_select"}
    assert fields["ai_provider_profiles.analyst.model"]["options"] == [
        "deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-vision-exp",
    ]
    assert fields["ai_provider_profiles.assistant.model"]["options"][0] == "legacy-account-model"
    assert fields["ai_custom_transcription.model"]["options"] == [
        "gpt-4o-mini-transcribe", "gpt-4o-transcribe", "gpt-4o-transcribe-diarize",
    ]
    assert snapshot["model_catalogs"]["deepseek"]["transcribe"] == []
    assert snapshot["model_catalogs"]["openai"]["transcribe"] == fields["ai_custom_transcription.model"]["options"]


def test_assistant_contract_accepts_only_bounded_recent_conversation():
    request = AssistantQueryContract(
        question="앞 질문을 이어서 설명해줘",
        service="settings",
        recent_messages=[{"role": "user", "content": "AI 비용 설정은?"}],
    )
    assert request.recent_messages[0].role == "user"


def test_assistant_contract_accepts_only_the_nine_settings_sections():
    sections = {
        "general", "exchange_selection", "exchange_api", "ai_engine", "notifications",
        "advanced", "alpha", "system", "update",
    }
    for section in sections:
        request = AssistantQueryContract(
            question="현재 탭을 설명해줘",
            service="settings",
            settings_section=section,
        )
        assert request.settings_section == section


def test_every_settings_section_has_a_scoped_secret_free_local_answer(tmp_path, monkeypatch):
    import web_platform.application_services as module

    stored = json.loads((Path(module.__file__).parents[1] / "config" / "settings_template.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(module, "load_settings", lambda **kwargs: deepcopy(stored))
    services = module.ApplicationServices(account="tester")

    for section in (
        "general", "exchange_selection", "exchange_api", "ai_engine", "notifications",
        "advanced", "alpha", "system", "update",
    ):
        result = services.ask_assistant(
            question="이 탭에서 확인할 항목과 주의사항을 설명해줘",
            service="settings",
            explanation_level="beginner",
            settings_section=section,
        )
        assert result["provider_called"] is False
        assert result["settings_section"] == section
        assert "현재 설정 탭:" in result["answer"]
        assert "api_secret" not in result["answer"].lower()


def test_settings_section_reaches_deep_analysis_context(tmp_path, monkeypatch):
    import web_platform.application_services as module

    stored = json.loads((Path(module.__file__).parents[1] / "config" / "settings_template.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(module, "load_settings", lambda **kwargs: deepcopy(stored))
    services = module.ApplicationServices(account="tester")
    captured = {}

    def fake_ask(**kwargs):
        captured.update(kwargs)
        return {"answer": "설정 답변", "provider_called": True, "provider": "openai", "model": "test"}

    services.interactive_ai.ask = fake_ask
    result = services.ask_assistant(
        question="비용 보호를 자세히 설명해줘",
        service="settings",
        explanation_level="standard",
        mode="deep_analysis",
        settings_section="ai_engine",
    )
    assert json.loads(captured["context"])["settings_section"] == "ai_engine"
    assert result["settings_section"] == "ai_engine"


def test_settings_ui_keeps_section_context_and_invalidates_cross_tab_answers():
    root = Path(__file__).parents[1]
    settings_ui = (root / "webui/src/components/SettingsCenter.tsx").read_text(encoding="utf-8")
    app_ui = (root / "webui/src/App.tsx").read_text(encoding="utf-8")
    assistant_ui = (root / "webui/src/components/AssistantWorkspace.tsx").read_text(encoding="utf-8")

    assert "guideRequestRef.current += 1" in settings_ui
    assert "setGuideAnswer(\"\")" in settings_ui
    assert "onAskAssistant(question, settingsSection)" not in app_ui
    assert 'openAssistant(question, "settings", settingsSection)' in app_ui
    assert "settingsSection={context.service === \"settings\" ? context.section : \"\"}" in app_ui
    assert "recentMessages, settingsSection" in assistant_ui
    assert "설정 문맥 고정" in assistant_ui


def _write_paths(payload, changes):
    result = deepcopy(payload)
    for path, value in changes.items():
        current = result
        parts = path.split(".")
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = deepcopy(value)
    return result


def test_web_ai_role_update_keeps_legacy_compatibility_keys_in_one_save(tmp_path, monkeypatch):
    import web_platform.application_services as module

    stored = json.loads((Path(module.__file__).parents[1] / "config" / "settings_template.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(module, "load_settings", lambda **kwargs: deepcopy(stored))

    def patch(changes):
        stored.clear()
        stored.update(_write_paths(stored_snapshot[0], changes))
        stored_snapshot[0] = deepcopy(stored)
        return True

    stored_snapshot = [deepcopy(stored)]
    monkeypatch.setattr(module, "patch_settings_paths", patch)
    services = module.ApplicationServices(account="tester")
    snapshot = services.settings_snapshot()
    services.update_settings(
        expected_revision=snapshot["revision"],
        changes={
            "ai_provider_profiles.analyst.provider": "deepseek",
            "ai_provider_profiles.analyst.model": "deepseek-chat",
            "ai_provider_profiles.assistant.model": "deepseek-reasoner",
        },
    )
    assert stored["ai_provider"] == "deepseek"
    assert stored["openai_model"] == "deepseek-chat"
    assert stored["assistant_ai_model"] == "deepseek-reasoner"
    assert stored["ai_models"]["analyst"] == "deepseek-chat"
    assert stored["ai_models"]["assistant"] == "deepseek-reasoner"


def test_deep_assistant_uses_saved_budget_and_recent_conversation(tmp_path, monkeypatch):
    import web_platform.application_services as module

    settings = json.loads((Path(module.__file__).parents[1] / "config" / "settings_template.json").read_text(encoding="utf-8"))
    settings["assistant_response_mode"] = "saver"
    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(module, "load_settings", lambda **kwargs: deepcopy(settings))
    services = module.ApplicationServices(account="tester")
    captured = {}

    def fake_ask(**kwargs):
        captured.update(kwargs)
        return {"answer": "연속 답변", "provider_called": True, "provider": "openai", "model": "test"}

    services.interactive_ai.ask = fake_ask
    result = services.ask_assistant(
        question="그 설정을 더 설명해줘",
        service="settings",
        explanation_level="advanced",
        mode="deep_analysis",
        recent_messages=[{"role": "user", "content": "AI 비용 상한은?"}],
    )
    context = json.loads(captured["context"])
    assert captured["max_tokens"] == 500
    assert context["recent_conversation"] == [{"role": "user", "content": "AI 비용 상한은?"}]
    assert result["response_mode"] == "saver"
    assert result["recent_turns_used"] == 1
