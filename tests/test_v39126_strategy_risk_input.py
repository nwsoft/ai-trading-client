from pathlib import Path

import pytest

from trading.strategy_source_ingestor import StrategySourceIngestor


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("sentence", "risk", "margin"),
    [
        ("거래당 계좌 손실 0.5%, 증거금 사용은 최대 10%.", 0.5, 10.0),
        ("거래 한 번에서 계좌의 최대 0.75%까지 손실, 증거금 최대 12%.", 0.75, 12.0),
        ("1회 위험 1%, 종목당 투자 비중은 최대 15%.", 1.0, 15.0),
        ("risk per trade 0.25%, position size 8%.", 0.25, 8.0),
    ],
)
def test_explicit_user_risk_budget_becomes_execution_contract(sentence, risk, margin):
    result = StrategySourceIngestor().analyze(
        "RSI 30 이하 LONG 진입. RSI 55 이상 청산. "
        f"손절 1%, 익절 2%. 횡보장에서 사용. {sentence}",
        "text",
    )

    assert "missing_required_rule:position_size" not in result["missing_conditions"]
    assert result["rules"]["risk_model"]["risk_per_trade_percent"] == pytest.approx(risk)
    assert result["rules"]["risk_model"]["max_margin_usage_percent"] == pytest.approx(margin)
    assert result["rules"]["engine_settings"]["position_size"] == pytest.approx(margin / 100.0)


def test_unitless_risk_budget_is_not_guessed_as_percent():
    result = StrategySourceIngestor().analyze(
        "RSI 30 이하 LONG 진입. RSI 55 이상 청산. "
        "손절 1%, 익절 2%. 횡보장에서 사용. 거래당 계좌 손실 0.5, 증거금 최대 10.",
        "text",
    )

    assert "position_size" in result["missing_conditions"]
    assert "risk_model" not in result["rules"]


def test_strategy_studio_only_inserts_user_confirmed_operating_values():
    studio = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")

    assert '["position_size", "market_conditions"].includes(issueField(code))' in studio
    assert "현재 선택값을 보완 근거로 추가" in studio
    assert "AI가 추측한 값이 아니라 현재 화면에서 사용자가 선택한 값" in studio
    assert "entry" not in studio[studio.index("function canInsertConfirmedSupplement"):studio.index("async function createStrategy")]


def test_strategy_studio_syncs_parsed_risk_values_before_version_save():
    studio = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")

    assert "setRiskPerTrade(String(parsedRisk))" in studio
    assert "setMaxMargin(String(parsedMargin))" in studio
    assert "setLeverageCap(String(parsedLeverage))" in studio


def test_risk_budget_changes_the_compiler_execution_contract_hash():
    ingestor = StrategySourceIngestor()
    common = (
        "RSI 30 이하 LONG 진입. RSI 55 이상 청산. 손절 1%, 익절 2%. "
        "횡보장에서 사용. 증거금 사용은 최대 10%. "
    )
    conservative = ingestor.analyze(common + "거래당 계좌 손실 0.5%.", "text")
    active = ingestor.analyze(common + "거래당 계좌 손실 1.0%.", "text")

    assert conservative["rules"]["source_grounding"]["compiler_contract_sha256"]
    assert conservative["rules"]["source_grounding"]["compiler_contract_sha256"] != active["rules"]["source_grounding"]["compiler_contract_sha256"]
