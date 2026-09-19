from pathlib import Path

import pytest

from config.ai_custom_knowledge import build_ai_custom_knowledge
from trading.strategy_source_ingestor import StrategySourceIngestor
from web_platform.interactive_ai import InteractiveAIService


ROOT = Path(__file__).resolve().parents[1]


class _ExhaustedInteractiveAI:
    @staticmethod
    def is_ready():
        return True

    @staticmethod
    def chat_json(*_args, **_kwargs):
        raise RuntimeError("interactive_ai_budget_exceeded")


@pytest.mark.parametrize(
    "risk_sentence",
    [
        "거래당 계좌 손실 0.5%, 증거금 사용은 최대 10%.",
        "거래당 계좌 손실 0.5%, 종목당 투자 비중은 최대 10%.",
    ],
)
def test_external_ai_budget_never_blocks_crypto_or_stock_rule_compilation(risk_sentence):
    result = StrategySourceIngestor(_ExhaustedInteractiveAI()).analyze(
        "RSI 30 이하이면 LONG 진입. RSI 55 이상이면 청산. "
        f"손절 1%, 익절 2%. 횡보장에서 사용. {risk_sentence}",
        "text",
        authoring_mode="guided_clarification",
    )

    assert result["ready_for_execution"] is True
    assert result["ai_budget_fallback"] is True
    assert result["ai_analyzed"] is False
    assert result["missing_conditions"] == []
    assert any("앱 내부 규칙 분석으로 계속" in item for item in result["source"]["warnings"])


def test_local_assistant_explains_429_and_user_owned_limit():
    answer = build_ai_custom_knowledge(
        "상태 429와 심층분석 30개 제한은 왜 생기나요?",
        {"ai_cost_control": {"max_daily_interactive_calls": 30, "max_monthly_interactive_calls": 500}},
    )

    assert "거래 오류나 회원 등급 제한이 아니라" in answer
    assert "하루 30회" in answer
    assert "1~1000회" in answer
    assert "월 1~30000회" in answer
    assert "Provider가 직접 반환하는 429" in answer
    assert "로컬 컴파일러로 계속" in answer


def test_interactive_ai_status_exposes_exact_limit_reason_and_utc_reset(tmp_path):
    service = InteractiveAIService(data_dir=tmp_path, clock=lambda: 1789081200.0)
    settings = {"ai_cost_control": {"max_daily_interactive_calls": 1, "max_monthly_interactive_calls": 2}}

    first = service.reserve_operation(settings, role="assistant")
    status = service.status(settings)

    assert first["allowed"] is True
    assert status["daily_used"] == 1
    assert status["daily_exhausted"] is True
    assert status["monthly_exhausted"] is False
    assert status["period_timezone"] == "UTC"
    assert status["next_daily_reset_at"].endswith("+00:00")
    with pytest.raises(RuntimeError, match="interactive_ai_budget_exceeded"):
        service.reserve_operation(settings, role="assistant")


def test_settings_exposes_ai_budget_limits_usage_and_429_boundary():
    services = (ROOT / "web_platform/application_services.py").read_text(encoding="utf-8")
    settings = (ROOT / "webui/src/components/SettingsCenter.tsx").read_text(encoding="utf-8")

    assert "외부 AI 일일 호출 상한" in services
    assert "외부 AI 월간 호출 상한" in services
    assert "AI 비용 관리 · 외부 호출 한도" in settings
    assert "assistantStatus?.daily_used" in settings
    assert "assistantStatus?.monthly_used" in settings
    assert "interactive_ai_budget_exceeded" in settings
    assert "제공사 자체 429" in settings
    assert "응답 실패 여부와 관계없이" in settings


def test_strategy_studio_uses_single_confirmation_and_preserves_leverage_guardrail():
    studio = (ROOT / "webui/src/components/StrategyStudio.tsx").read_text(encoding="utf-8")

    assert "window.confirm" in studio
    assert "confirmKey" not in studio
    assert "같은 버튼을 한 번 더" not in studio
    assert "PAPER 검증을 재개할까요?" in studio
    assert "이 전략 버전\" : \"이 전략 전체" in studio
    leverage_control = studio[studio.index("레버리지 상한"):studio.index("전략 동시 포지션 요청")]
    assert '<option value={"5"}>5</option>' in leverage_control
    import re
    assert re.findall(r'<option[^>]*>(\d+)</option>', leverage_control) == ['1', '2', '3', '5']


def test_assistant_answer_handoff_requires_review_and_reanalysis_for_both_services():
    app = (ROOT / "webui/src/App.tsx").read_text(encoding="utf-8")
    assistant = (ROOT / "webui/src/components/AssistantWorkspace.tsx").read_text(encoding="utf-8")
    studio = (ROOT / "webui/src/components/StrategyStudio.tsx").read_text(encoding="utf-8")

    assert "strategyAssistantDraft" in app
    assert "onSendToStrategy" in assistant
    assert "이 답변을 전략 스튜디오 검토 영역으로 보내기" in assistant
    assert "AI 답변 검토 · 아직 전략에 적용되지 않음" in studio
    assert "사용자 보완 근거로 확정·재분석" in studio
    assert "await analyzeSource(nextSupplement)" in studio
    assert '(["blockchain", "stock"] as const).map' in app


def test_explanation_levels_are_prompt_and_cache_context_not_only_token_caps():
    services = (ROOT / "web_platform/application_services.py").read_text(encoding="utf-8")
    assistant = (ROOT / "webui/src/components/AssistantWorkspace.tsx").read_text(encoding="utf-8")

    assert '"explanation_level": explanation_level' in services
    assert "explanation_instruction" in services
    assert "초보자가 바로 따라 할 수 있는 쉬운 한국어" in services
    assert "실행 계약, 관련 필드, 증거 경계" in services
    assert 'service === "ai_custom" ? "beginner" : "standard"' in assistant


def test_window_title_comes_from_packaged_version_and_version_time_is_visible():
    electron = (ROOT / "webui/electron/main.cjs").read_text(encoding="utf-8")
    helper = (ROOT / "webui/electron/version.cjs").read_text(encoding="utf-8")
    studio = (ROOT / "webui/src/components/StrategyStudio.tsx").read_text(encoding="utf-8")

    assert "packageProductVersion" in electron
    assert "buildVersion" in helper
    assert "대시보드 Beta v${currentProductVersion()}" in electron
    assert "대시보드 Beta 3.9.1.24" not in electron
    assert "strategyVersionTime" in studio
    assert "strategy-version-created" in studio
