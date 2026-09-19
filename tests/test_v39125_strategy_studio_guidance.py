from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from config.ai_custom_knowledge import build_ai_custom_knowledge


ROOT = Path(__file__).resolve().parents[1]


def test_blank_provider_answer_is_rejected_and_never_cached(tmp_path):
    from web_platform.interactive_ai import InteractiveAIService

    class BlankAdapter:
        model = "blank-model"

        @staticmethod
        def is_ready():
            return True

        @staticmethod
        def chat_text(*_args, **_kwargs):
            return SimpleNamespace(
                ok=True,
                content="   ",
                error=None,
                usage={},
                provider="blank-provider",
                model="blank-model",
            )

    router = SimpleNamespace(
        spec=SimpleNamespace(provider="blank-provider"),
        adapter=BlankAdapter(),
    )
    service = InteractiveAIService(data_dir=tmp_path, router_factory=lambda *_args, **_kwargs: router)

    with pytest.raises(RuntimeError, match="빈 응답"):
        service.ask(
            settings={"ai_cost_control": {"interactive_cache_sec": 900}},
            workload="assistant",
            question="전략 차단 이유를 알려줘",
            context="{}",
            system_prompt="정본만 설명",
            max_tokens=500,
        )

    assert not service.cache_path.exists()


def test_strategy_validation_question_returns_actionable_ai_custom_guidance():
    answer = build_ai_custom_knowledge(
        "전략 스튜디오 최종 재검증에서 다음 항목이 차단됐어: "
        "pine_dynamic_input_requires_user_confirmation, "
        "pine_custom_function_not_supported, "
        "missing_required_rule:stop_loss, missing_required_rule:take_profit, "
        "missing_required_rule:position_size",
        {},
    )

    assert "Pine 입력값을 확정해야 합니다" in answer
    assert "Pine 사용자 함수의 실행 의미를 확인할 수 없습니다" in answer
    assert "손절 조건 항목이 없습니다" in answer
    assert "수익 실현 항목이 없습니다" in answer
    assert "거래 위험예산 항목이 없습니다" in answer
    assert "수정 순서" in answer
    assert "AI에게 묻기는 설명만 제공" in answer


def test_deep_assistant_provider_failure_returns_local_product_answer(tmp_path, monkeypatch):
    import web_platform.application_services as module

    settings = json.loads((ROOT / "config" / "settings_template.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(module, "load_settings", lambda **kwargs: deepcopy(settings))
    services = module.ApplicationServices(account="tester")
    services.interactive_ai.ask = lambda **_kwargs: (_ for _ in ()).throw(
        RuntimeError("AI 제공사가 빈 응답을 반환했습니다.")
    )

    result = services.ask_assistant(
        question="최종 재검증의 missing_required_rule:stop_loss를 어떻게 고쳐?",
        service="ai_custom",
        explanation_level="beginner",
        mode="deep_analysis",
    )

    assert result["answer"].strip()
    assert "손절 조건 항목이 없습니다" in result["answer"]
    assert result["provider_called"] is False
    assert result["provider_failed"] is True
    assert result["source"] == "versioned_local_product_knowledge_fallback"


def test_strategy_studio_state_is_kept_alive_while_using_its_assistant():
    app = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    assistant = (ROOT / "webui" / "src" / "components" / "AssistantWorkspace.tsx").read_text(encoding="utf-8")
    studio = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")

    assert "visitedStrategyStudios" in app
    assert 'className="strategy-studio-keepalive" hidden={!visible}' in app
    assert 'setAssistantService("ai_custom")' in app
    assert "전략 스튜디오로 돌아가기 · 입력 유지" in app
    assert 'ai_custom: {' in assistant
    assert "AI 응답이 비어 있어 답변을 표시하지 못했습니다" in assistant
    assert "무엇을 고쳐야 하나요?" in studio
    assert "원문 다시 분석 준비" in studio
    assert "기본 NoahAI 사용 확인 완료" in studio
    assert "NoahAI 보조 전략 초안 만들기" not in studio


def test_missing_risk_uses_user_confirmed_insert_instead_of_ai_guessing():
    studio = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")

    assert "function insertConfirmedSupplement" in studio
    assert "현재 선택값을 보완 근거로 추가" in studio
    assert "AI가 추측한 값이 아니라 현재 화면에서 사용자가 선택한 값" in studio
    assert "거래당 계좌 손실 ${riskPerTrade}%" in studio
    assert "증거금 사용\"}은 최대 ${maxMargin}%" in studio
    assert "AI가 알아서 판단해서 전략 조건을 추가" not in studio


def test_guided_start_keeps_levels_and_safety_steps_unchanged():
    studio = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")
    guided = studio[studio.index("function openGuidedTour"):studio.index("useEffect(refresh")]

    assert "setFeatureViewLevel" not in guided
    assert "setPaperModeEnabled" not in guided
    assert "setParallelPaperEnabled" not in guided
    assert "PAPER는 실주문 권한 없이" in studio
    assert "검증 통과가 자동 LIVE 적용으로 이어지지 않습니다" in studio


def test_guided_start_does_not_force_noah_base_overlay_through_historical_replay():
    studio = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")
    services = (ROOT / "web_platform" / "application_services.py").read_text(encoding="utf-8")

    assert "function historicalReplayApplicable" in studio
    assert "guidedHistoricalReplayApplicable" in studio
    assert "과거재생 비대상 확인" in studio
    assert "진입 규칙을 임의로 만들어 과거 성과를 표시하지 않고" in studio
    assert 'directPaperValidation' in studio
    assert "이 전략은 NoahAI 기본 진입을 사용하므로 독립 과거재생 대상이 아닙니다." in services


def test_candidate_web_version_fallback_matches_current_release():
    app = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    settings = (ROOT / "webui" / "src" / "components" / "SettingsCenter.tsx").read_text(encoding="utf-8")
    updates = (ROOT / "webui" / "src" / "components" / "UpdateCenter.tsx").read_text(encoding="utf-8")

    from config.app_version import RELEASE_VERSION
    assert f'platform?.release_version || "{RELEASE_VERSION}"' in app
    assert f'platform?.release_label ?? "v{RELEASE_VERSION}"' in app
    assert 'platform?.release_version || "3.9.1.25"' not in app
    assert f"v{RELEASE_VERSION}" in settings
    assert f'currentVersion = "v{RELEASE_VERSION}"' in updates


def test_local_assistant_explains_historical_replay_not_applicable_without_faking_pass():
    answer = build_ai_custom_knowledge(
        "다시 눌러 자동검증 확정을 눌러도 실행 가능한 진입 조건이 없어 PAPER 단계로 안 넘어가요",
        {},
    )

    assert "검증 실패가 아닙니다" in answer
    assert "NoahAI 기본 진입 + 사용자 위험·청산" in answer
    assert "PAPER 단계로 이동" in answer
    assert "자동 LIVE 적용은 여전히 없습니다" in answer
