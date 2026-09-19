from pathlib import Path

from config.ai_custom_knowledge import build_ai_custom_knowledge
from trading.ai.model_registry import model_record, selectable_models
from trading.ai.provider_router import PROVIDER_SPECS
from trading.ai.provider_router import AIProviderRouter
from web_platform.interactive_ai import InteractiveAIService


ROOT = Path(__file__).resolve().parents[1]


class _UsageClient:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self, usage):
        self.usage = dict(usage)
        self.calls = 0

    def is_ready(self):
        return True

    def chat_json(self, *_args, **_kwargs):
        self.calls += 1
        return {"ok": True}

    def get_last_usage(self):
        return dict(self.usage)


def test_deepseek_flash_uses_official_alias_and_exposes_vision_preview():
    models = selectable_models("deepseek", capability="chat_text")
    assert "deepseek-v4-flash" in models
    assert "deepseek-v4-pro" in models
    assert "deepseek-v4-flash-vision-exp" in models
    assert "deepseek-v4.1-flash" not in models
    assert model_record("deepseek", "deepseek-v4-flash")["status"] == "recommended"
    assert PROVIDER_SPECS["deepseek"].capabilities.vision is True


def test_budgeted_client_records_completed_tokens_model_role_and_peak_estimate(tmp_path):
    service = InteractiveAIService(data_dir=tmp_path, clock=lambda: 1_789_081_200.0)
    settings = {"ai_cost_control": {"max_daily_interactive_calls": 30, "max_monthly_interactive_calls": 500}}
    client = _UsageClient({"input_tokens": 1_000_000, "output_tokens": 1_000_000, "total_tokens": 2_000_000})

    result = service.budgeted_client(settings, client, role="strategy_source").chat_json("system", "prompt")
    status = service.status(settings)

    assert result == {"ok": True}
    assert client.calls == 1
    assert status["daily_used"] == 1
    assert status["completed_usage_calls"]["today"] == 1
    assert status["priced_calls"]["today"] == 1
    assert status["estimated_cost_usd"]["today"] == 1.76
    assert status["usage_by_role"]["strategy_source"]["calls"] == 1
    assert status["usage_by_model"]["deepseek:deepseek-v4-flash"]["total_tokens"] == 2_000_000


def test_missing_usage_is_unpriced_instead_of_false_zero(tmp_path):
    service = InteractiveAIService(data_dir=tmp_path, clock=lambda: 1_789_081_200.0)
    settings = {"ai_cost_control": {"max_daily_interactive_calls": 30, "max_monthly_interactive_calls": 500}}
    client = _UsageClient({})

    service.budgeted_client(settings, client, role="strategy_source").chat_json("system", "prompt")
    status = service.status(settings)

    assert status["completed_usage_calls"]["today"] == 1
    assert status["priced_calls"]["today"] == 0
    assert status["estimated_cost_usd"]["today"] == 0.0
    assert status["cost_unavailable_calls"]["today"] == 1
    assert status["usage_by_model"]["deepseek:deepseek-v4-flash"]["unpriced_calls"] == 1
    assert service._estimate_cost("deepseek", "deepseek-v4-flash", {"total_tokens": 1234}) is None


def test_settings_describes_cost_boundary_and_role_based_model_setup():
    settings = (ROOT / "webui/src/components/SettingsCenter.tsx").read_text(encoding="utf-8")

    assert "나만의 AI 구성 · 작업별 모델" in settings
    assert "자동매매 백그라운드 AI와 Provider 계정 전체 청구액은 포함하지 않습니다" in settings
    assert "YouTube 공개 자막이 없을 때만 음성 전사 사용" in settings
    assert "deepseek-v4.1-flash" in settings
    assert '"deepseek-v4.1-flash":' not in settings
    assert '"deepseek-v4-flash": "DeepSeek V4 Flash · 자동 최신"' in settings
    assert "SETTING_OPTION_LABELS[option] ?? option" in settings
    assert "선택 모델 1회 실제 호출 점검" in settings
    assert "요청 모델" in settings
    assert "실제 응답 모델" in settings
    assert "변경 대기 · 아직 미적용" in settings
    assert "실제 응답 모델별 사용량" in settings


def test_local_assistant_explains_deepseek_alias_routing_and_cost_scope():
    deepseek = build_ai_custom_knowledge("DeepSeek 4.1 Flash와 작업별 모델 설정을 알려줘", {})
    cost = build_ai_custom_knowledge("AI 비용 카드의 추정 비용 범위를 알려줘", {})

    assert "deepseek-v4-flash" in deepseek
    assert "deepseek-v4.1-flash" in deepseek
    assert "실제 연결 점검" in deepseek
    assert "공개 자막" in deepseek
    assert "사용자가 직접 실행한 호출" in cost
    assert "비용 미산출" in cost
    assert "자동매매 백그라운드" in cost


def test_deepseek_text_model_facade_does_not_send_images(monkeypatch):
    router = AIProviderRouter("deepseek", api_key="test-key", model="deepseek-v4-flash")
    calls = []
    monkeypatch.setattr(router.adapter.client, "vision_json", lambda *args, **kwargs: calls.append((args, kwargs)))

    assert router.client_facade().vision_json("system", "prompt", ["chart.png"]) is None
    assert calls == []
