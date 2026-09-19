from pathlib import Path

import pytest
from pydantic import ValidationError

from trading.strategy_source_ingestor import StrategySourceIngestor
from web_platform.contracts import StrategySourceAnalyzeContract


ROOT = Path(__file__).resolve().parents[1]


def test_missing_rules_become_questions_not_ai_answers():
    result = StrategySourceIngestor().analyze(
        "RSI 30 이하 LONG 진입. 횡보장에서 사용.",
        "text",
        authoring_mode="guided_clarification",
    )

    questions = result["clarification_questions"]
    assert questions
    assert all(question["auto_executable"] is False for question in questions)
    assert {question["field"] for question in questions} >= {
        "exit", "stop_loss", "take_profit", "position_size",
    }
    assert result["authoring_contract"] == {
        "mode": "guided_clarification",
        "source_faithful": True,
        "user_confirmation_present": False,
        "ai_proposals_are_executable": False,
        "auto_saved": False,
        "auto_approved": False,
        "auto_paper_started": False,
        "auto_live_started": False,
    }


def test_user_confirmation_supplement_is_separate_evidence_and_can_complete_rules():
    original = (
        "RSI 30 이하이면 LONG 진입. RSI 55 이상이면 청산. "
        "손절 1%, 익절 2%. 횡보장에서 사용."
    )
    supplement = "거래당 계좌 손실 0.5%, 증거금 사용은 최대 10%."

    result = StrategySourceIngestor().analyze(
        original,
        "text",
        supplemental_text=supplement,
        authoring_mode="guided_clarification",
    )

    assert result["ready_for_execution"] is True
    assert result["missing_conditions"] == []
    assert result["rules"]["risk_model"]["risk_per_trade_percent"] == pytest.approx(0.5)
    assert result["rules"]["risk_model"]["max_margin_usage_percent"] == pytest.approx(10.0)
    evidence = result["source"]["evidence"]
    assert evidence["user_confirmation_present"] is True
    assert len(evidence["original_content_sha256"]) == 64
    assert len(evidence["user_confirmation_sha256"]) == 64
    grounding = result["rules"]["source_grounding"]
    assert grounding["authoring_mode"] == "guided_clarification"
    assert grounding["user_confirmation_present"] is True
    assert result["authoring_contract"]["ai_proposals_are_executable"] is False


def test_file_source_is_not_modified_when_user_confirmation_is_added(tmp_path):
    source_path = tmp_path / "owned-strategy.txt"
    original = (
        "RSI 30 이하이면 LONG 진입. RSI 55 이상이면 청산. "
        "손절 1%, 익절 2%. 횡보장에서 사용."
    )
    source_path.write_text(original, encoding="utf-8")

    result = StrategySourceIngestor().analyze(
        str(source_path),
        "text",
        supplemental_text="거래당 계좌 손실 0.5%, 증거금 사용은 최대 10%.",
        authoring_mode="guided_clarification",
    )

    assert source_path.read_text(encoding="utf-8") == original
    assert result["ready_for_execution"] is True
    assert result["source"]["reference"] == str(source_path)
    assert "원본 파일은 변경하지 않고" in result["source"]["warnings"][-1]


def test_user_confirmation_cannot_silently_replace_an_existing_source_rule():
    result = StrategySourceIngestor().analyze(
        (
            "RSI 30 이하이면 LONG 진입. RSI 55 이상이면 청산. "
            "손절 1%, 익절 2%. 횡보장에서 사용. "
            "거래당 계좌 손실 0.5%, 증거금 사용은 최대 10%."
        ),
        "text",
        supplemental_text="손절 2%로 변경.",
        authoring_mode="guided_clarification",
    )

    assert result["ready_for_execution"] is False
    assert "user_confirmation_conflicts_with_original:stop_loss" in result["missing_conditions"]
    assert any(
        item["title"] == "보완 답변이 기존 원문과 충돌합니다"
        for item in result["blocking_details"]
    )


def test_supplement_length_and_authoring_mode_are_bounded_at_gateway_contract():
    valid = StrategySourceAnalyzeContract(
        source_kind="text",
        value="RSI 30 이하 LONG",
        supplemental_text="사용자 확인 답변",
        authoring_mode="guided_clarification",
    )
    assert valid.authoring_mode == "guided_clarification"

    with pytest.raises(ValidationError):
        StrategySourceAnalyzeContract(
            source_kind="text",
            value="RSI 30 이하 LONG",
            supplemental_text="x" * 20_001,
        )

    with pytest.raises(ValidationError):
        StrategySourceAnalyzeContract(
            source_kind="text",
            value="RSI 30 이하 LONG",
            authoring_mode="unbounded_auto_complete",
        )


def test_strategy_studio_exposes_three_clear_paths_without_auto_execution():
    studio = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")

    assert "원문 그대로 구조화" in studio
    assert "질문으로 함께 완성" in studio
    assert "기본 NoahAI에 맡기기" in studio
    assert "답변 확정 후 다시 분석" in studio
    assert "빠진 조건을 질문으로 완성" in studio
    assert "AI 예시는 자동 적용되지 않습니다" in studio
    assert "ai_proposals_are_executable" not in studio
    assert "unbounded_auto_complete" not in studio
    mode_section = studio[studio.index("const AUTHORING_MODES"):studio.index("const GUIDED_METHOD_COPY")]
    assert "setFeatureViewLevel" not in mode_section


def test_release_sync_guard_treats_web_ui_as_user_visible():
    guard = (ROOT / "scripts" / "user_visible_sync_guard.py").read_text(encoding="utf-8")

    assert '"webui/src/"' in guard[guard.index("USER_VISIBLE_PREFIXES"):guard.index("NON_USER_VISIBLE_PREFIXES")]
