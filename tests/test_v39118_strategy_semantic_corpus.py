import json
from pathlib import Path

import pytest

from trading.strategy_source_ingestor import StrategySourceIngestor
from web_platform.application_services import ApplicationServices


CORPUS_PATH = Path(__file__).parent / "fixtures" / "strategy_semantic_corpus_v39118.json"
ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_strategy_source_semantics_are_preserved_or_fail_closed(case):
    result = StrategySourceIngestor().analyze(case["source"], case["kind"])
    rules = result["rules"]
    engine = result["engine_settings"]

    assert result["ready_for_execution"] is case["ready"]
    if "signal_mode" in case:
        assert rules["signal_mode"] == case["signal_mode"]
    if "entry_signal" in case:
        assert rules["entry_signal"] == case["entry_signal"]
    if "branches" in case:
        assert set(rules["independent_entries"]) == set(case["branches"])
    if "entry_condition" in case:
        assert case["entry_condition"] in rules["executable_entry"]["all"]
    if "tp_percent" in case:
        assert engine["tp_percent"] == pytest.approx(case["tp_percent"])
    if "sl_percent" in case:
        assert engine["sl_percent"] == pytest.approx(case["sl_percent"])
    for reason in case.get("missing_contains", []):
        assert reason in result["missing_conditions"]
    for field in case.get("engine_absent", []):
        assert field not in engine


def test_semantic_corpus_has_supported_and_blocked_examples():
    assert len(CASES) >= 6
    assert any(case["ready"] for case in CASES)
    assert any(not case["ready"] for case in CASES)
    assert {case["kind"] for case in CASES} == {"text", "pine"}


def test_strategy_studio_exposes_validation_and_venue_evidence():
    component = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")
    contracts = (ROOT / "webui" / "src" / "types.ts").read_text(encoding="utf-8")

    for phrase in (
        "실행 전 기관·상품 호환성",
        "venueProfilesForService",
        "거래소별 PAPER 전진검증",
        "검증 근거 보기",
        "과거 결과는 미래 수익 보장이나 자동 적용 근거가 아닙니다.",
    ):
        assert phrase in component
    assert "paper_evidence_by_venue" in contracts
    assert "venue_compatibility" in contracts


def test_dual_direction_strategy_is_partial_on_krw_spot_and_compatible_on_futures():
    rows = ApplicationServices._strategy_venue_compatibility(
        scope="unified",
        rules={
            "target_scope": "asset:crypto",
            "signal_mode": "independent",
            "independent_entries": {"LONG": {"all": []}, "SHORT": {"all": []}},
        },
    )
    by_venue = {row["venue"]: row for row in rows}

    assert by_venue["upbit"]["status"] == "partial"
    assert by_venue["bithumb"]["supported_directions"] == ["LONG"]
    assert by_venue["binance"]["status"] == "compatible"
    assert by_venue["okx"]["status"] == "compatible"


def test_short_only_strategy_is_blocked_on_spot_without_rewriting_direction():
    crypto = ApplicationServices._strategy_venue_compatibility(
        scope="unified",
        rules={"target_scope": "asset:crypto", "entry_signal": "SHORT"},
    )
    stock = ApplicationServices._strategy_venue_compatibility(
        scope="unified",
        rules={"target_scope": "asset:stock", "entry_signal": "SHORT"},
    )

    assert {row["status"] for row in crypto if row["market_type"] == "krw_spot"} == {"blocked"}
    assert {row["status"] for row in stock} == {"blocked"}
    assert all(row["requested_directions"] == ["SHORT"] for row in crypto + stock)
