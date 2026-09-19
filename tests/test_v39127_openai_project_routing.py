from types import SimpleNamespace
from copy import deepcopy
import json
from pathlib import Path

from trading.ai.openai_client import OpenAIClient
from trading.ai.provider_router import AIProviderRouter
from web_platform.application_services import ApplicationServices
from web_platform.interactive_ai import InteractiveAIService


def _settings(*, enabled=True, shared_key="shared-key"):
    return {
        "ai_provider": "deepseek",
        "ai_credentials": {
            "deepseek": {"api_key": "private-key", "base_url": "https://api.deepseek.com"},
            "openai": {"api_key": "protected-openai-key", "base_url": ""},
            "openai_shared": {"api_key": shared_key, "base_url": ""},
        },
        "ai_provider_profiles": {
            "assistant": {"provider": "deepseek", "model": "deepseek-v4-flash"},
        },
        "ai_data_routing": {
            "public_general_sharing_enabled": enabled,
            "public_openai_model": "gpt-5.6-luna",
        },
    }


def test_private_is_default_and_never_borrows_shared_openai_key():
    router = AIProviderRouter.from_settings(_settings(), workload="assistant")

    assert router.spec.provider == "deepseek"
    assert router.adapter.client.api_key == "private-key"
    assert router.privacy_route == "protected_default"


def test_explicit_public_general_uses_separate_openai_project_key():
    router = AIProviderRouter.from_settings(
        _settings(), workload="assistant", privacy_class="public_general",
    )

    assert router.spec.provider == "openai"
    assert router.adapter.client.api_key == "shared-key"
    assert router.adapter.model == "gpt-5.6-luna"
    assert router.privacy_route == "openai_shared_public_general"


def test_disabled_or_missing_shared_route_falls_back_to_protected_not_reverse():
    disabled = AIProviderRouter.from_settings(
        _settings(enabled=False), workload="assistant", privacy_class="public_general",
    )
    missing = AIProviderRouter.from_settings(
        _settings(shared_key=""), workload="assistant", privacy_class="public_general",
    )
    private_without_private_key = AIProviderRouter.from_settings(
        {
            **_settings(),
            "ai_credentials": {
                "deepseek": {"api_key": ""},
                "openai_shared": {"api_key": "shared-key"},
            },
        },
        workload="assistant",
    )

    assert disabled.adapter.client.api_key == "private-key"
    assert missing.adapter.client.api_key == "private-key"
    assert disabled.privacy_route == missing.privacy_route == "protected_default_fallback"
    assert private_without_private_key.adapter.client.api_key == ""
    assert private_without_private_key.privacy_route == "protected_default"


def test_openai_chat_requests_disable_provider_side_response_storage():
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )

    client = OpenAIClient(api_key="test", model="gpt-5.6-luna", provider="openai")
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))

    assert client.chat("system", "public help", max_tokens=20) == "ok"
    assert captured["store"] is False


def test_shared_credential_status_is_presence_only():
    status = ApplicationServices._credential_status(_settings())
    fields = ApplicationServices._credential_field_status(_settings())

    assert status["ai:openai_shared"] is True
    assert fields["openai_shared"] == {"api_key": True, "base_url": False}
    assert "shared-key" not in str(status)
    assert "shared-key" not in str(fields)


def test_public_route_is_part_of_cache_and_usage_audit(tmp_path):
    calls = []

    class Response:
        ok = True
        content = "public answer"
        provider = "openai"
        model = "gpt-5.6-luna"
        usage = {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}
        error = None

    class Adapter:
        model = "gpt-5.6-luna"

        def is_ready(self):
            return True

        def chat_text(self, system, prompt, max_tokens):
            calls.append((system, prompt, max_tokens))
            return Response()

    class Router:
        spec = SimpleNamespace(provider="openai")
        adapter = Adapter()
        privacy_route = "openai_shared_public_general"
        privacy_reason = "explicit public"

    def factory(settings, *, workload, privacy_class="private"):
        assert privacy_class == "public_general"
        return Router()

    service = InteractiveAIService(data_dir=tmp_path, router_factory=factory)
    settings = {"ai_cost_control": {"max_daily_interactive_calls": 30, "max_monthly_interactive_calls": 500}}
    result = service.ask(
        settings=settings,
        workload="assistant",
        question="공개 기능 질문",
        context="개인정보 없음",
        system_prompt="공개 안내",
        max_tokens=100,
        privacy_class="public_general",
    )

    assert result["privacy_route"] == "openai_shared_public_general"
    assert service.status(settings)["usage_by_privacy_route"]["openai_shared_public_general"]["calls"] == 1
    assert len(calls) == 1


def test_ui_and_backend_keep_public_lane_context_free():
    ui = open("webui/src/components/AssistantWorkspace.tsx", encoding="utf-8").read()
    service = open("web_platform/application_services.py", encoding="utf-8").read()

    assert 'dataScope === "public_general" ? []' in ui
    assert "질문 1건만 전송 · 최근 대화와 앱 상태 제외" in ui
    assert "if public_general_request:" in service
    assert 'context["public_product_boundary"]' in service
    assert "and not public_general_request" in service


def test_public_general_application_request_drops_private_context(tmp_path, monkeypatch):
    import web_platform.application_services as module

    stored = json.loads((Path(module.__file__).parents[1] / "config" / "settings_template.json").read_text(encoding="utf-8"))
    stored["ai_data_routing"]["public_general_sharing_enabled"] = True
    stored["ai_credentials"]["openai_shared"]["api_key"] = "shared-key"
    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(module, "load_settings", lambda **kwargs: deepcopy(stored))
    services = module.ApplicationServices(account="tester")
    services.workspace_snapshot = lambda **kwargs: {"secret_account": "must-not-leave"}
    services.strategy_catalog = lambda: {"secret_strategy": "must-not-leave"}
    captured = {}
    services.interactive_ai.ask = lambda **kwargs: captured.update(kwargs) or {
        "answer": "공개 답변",
        "provider_called": True,
        "provider": "openai",
        "model": "gpt-5.6-luna",
        "privacy_route": "openai_shared_public_general",
    }

    result = services.ask_assistant(
        question="공개된 NoahAI 기능을 설명해줘",
        service="blockchain",
        explanation_level="standard",
        mode="deep_analysis",
        recent_messages=[{"role": "user", "content": "비공개 이전 대화"}],
        data_scope="public_general",
    )
    context = json.loads(captured["context"])

    assert captured["privacy_class"] == "public_general"
    assert context["assistant_policy"]["recent_turns"] == 0
    assert "recent_conversation" not in context
    assert "runtime" not in context
    assert "account_workspace" not in context
    assert "strategies" not in context
    assert "settings" not in context
    assert "must-not-leave" not in captured["context"]
    assert result["data_scope"] == "public_general"
