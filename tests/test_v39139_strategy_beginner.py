import json
from pathlib import Path

import pytest

from config.ai_custom_knowledge import build_ai_custom_knowledge
from config.strategy_explanation import MARKER, explain_strategy_snapshot
from trading.strategy_source_ingestor import StrategySourceIngestor

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("bad", ["", "{", "[]", '"text"', '{"rules": []}', '{"rules": null}'])
def test_invalid_snapshot_falls_back_without_crashing(bad):
    assert explain_strategy_snapshot(MARKER + bad) == ""


@pytest.mark.parametrize("market", ["코인", "주식·ETF"])
def test_real_local_analysis_rules_reach_read_only_explanation(market):
    analysis = StrategySourceIngestor().analyze(
        "RSI 30 이하 LONG 진입. RSI 55 이상 청산. 손절 1%, 익절 2%. 횡보장에서 사용.",
        "text", authoring_mode="guided_clarification",
    )
    snapshot = {"market": market, "name": "검토용", "rules": analysis["rules"],
                "coverage": analysis["source"]["coverage_summary"], "source_excerpts": [],
                "missing": [item["action"] for item in analysis["blocking_details"]]}
    answer = build_ai_custom_knowledge(MARKER + json.dumps(snapshot, ensure_ascii=False, default=str))
    assert "진입 — 거래를 시작하는 조건" in answer
    assert "RSI" in answer
    assert "영상 전체에 성과 설명이 없다는 뜻은 아닙니다" in answer
    assert "자동 실행되지 않습니다" in answer
    assert analysis["authoring_contract"]["auto_saved"] is False
    assert analysis["authoring_contract"]["auto_live_started"] is False


def test_overlong_or_non_string_explanation_fields_do_not_become_authority():
    assert explain_strategy_snapshot(MARKER + "x" * 4000) == ""
    answer = explain_strategy_snapshot(MARKER + json.dumps({"rules": {"entry": {"execute": "buy"}}, "source_excerpts": [123, {"win": 100}]}))
    assert "확인되지 않음" in answer
    assert "execute" not in answer
    assert "검증된 성과로 보지 않습니다" in answer


def test_beginner_panel_is_not_gated_to_advanced_and_manual_has_actual_flow():
    studio = (ROOT / "webui/src/components/StrategyStudio.tsx").read_text(encoding="utf-8")
    panel_pos = studio.index("<StrategyBeginnerExplanation")
    assert panel_pos < studio.index('{resultView !== "Level 1 이해·시험"')
    assistant = (ROOT / "webui/src/components/AssistantWorkspace.tsx").read_text(encoding="utf-8")
    assert 'strategyContext && !strategyContext.includes(MARKET_TREND_SNAPSHOT_MARKER) && dataScope === "public_general"' in assistant
    assert "client.askAssistant(requestPrompt" in assistant
    assert 'setMode("guide")' in assistant
    assert "분석 자료·대화 해제" in assistant
    manual = (ROOT / "ui/widgets/user_manual_widget.py").read_text(encoding="utf-8")
    for phrase in ["[과거재생 차트 따라 보기", "SHORT는 SELL 진입/BUY 청산", "심층분석", "PDF 책/문서", "성과 관련 원문 발췌", "일반 안내", "20건"]:
        assert phrase in manual
    assert "• 엔진 설정: 레버리지 1~10" not in manual
