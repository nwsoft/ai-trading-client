import json
from pathlib import Path

from web_platform.application_services import ApplicationServices


ROOT = Path(__file__).resolve().parents[1]


def _question(*, service: str = "blockchain") -> str:
    payload = {
        "schema": "market_trend_screen_v1",
        "service": service,
        "source": "binance" if service == "blockchain" else "kiwoom",
        "period": "최근 7일",
        "captured_at": "2026-09-19T00:00:00Z",
        "summary": {
            "direction": "상승",
            "average_change_pct": 2.1,
            "breadth": {"up": 2, "neutral": 0, "down": 1},
            "average_volume_change_pct": 4.3,
            "average_intraday_range_pct": 3.2,
            "funding_rate_pct": 0.01 if service == "blockchain" else None,
            "long_short_ratio": 1.1 if service == "blockchain" else None,
        },
        "assets": [
            {
                "symbol": "BTCUSDT" if service == "blockchain" else "005930",
                "name": "BTC/USDT" if service == "blockchain" else "삼성전자",
                "change_pct": 3.2,
                "volume_change_pct": 4.0,
                "average_intraday_range_pct": 2.3,
                "data_source": "binance" if service == "blockchain" else "kiwoom",
            }
        ],
        "missing": ["실제 공포탐욕지수" if service == "blockchain" else "외국인·기관 수급"],
    }
    return "관찰 후보를 XAI로 비교해줘\n[MARKET_TREND_SNAPSHOT]" + json.dumps(payload, ensure_ascii=False)


def test_market_trend_screen_evidence_produces_bounded_xai_answer():
    question = _question()
    evidence = ApplicationServices._market_trend_screen_evidence(question)

    assert evidence is not None
    answer = ApplicationServices._market_trend_screen_answer(question, evidence)
    assert "BINANCE · 최근 7일" in answer
    assert "시장 폭: 상승 2 · 중립 0 · 하락 1" in answer
    assert "지지 근거" in answer
    assert "반대·위험 근거" in answer
    assert "무효화 조건" in answer
    assert "개인화 매수 추천" in answer
    assert "실제 공포탐욕지수" in answer


def test_market_trend_screen_evidence_rejects_unknown_or_oversized_payload():
    assert ApplicationServices._market_trend_screen_evidence("시장 알려줘") is None
    assert ApplicationServices._market_trend_screen_evidence(
        "[MARKET_TREND_SNAPSHOT]" + json.dumps({"schema": "unknown", "assets": [], "summary": {}})
    ) is None
    oversized = "[MARKET_TREND_SNAPSHOT]" + "{" + ("x" * 12_001)
    assert ApplicationServices._market_trend_screen_evidence(oversized) is None


def test_market_trend_ui_uses_period_graphs_and_hidden_assistant_evidence():
    workspace = (ROOT / "webui" / "src" / "components" / "LegacyFeatureWorkspaces.tsx").read_text(encoding="utf-8")
    assistant = (ROOT / "webui" / "src" / "components" / "AssistantWorkspace.tsx").read_text(encoding="utf-8")
    app = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert 'type MarketTrendPeriod = "today" | "week" | "month"' in workspace
    assert "MarketBreadthDonut" in workspace
    assert "MarketSparkline" in workspace
    assert "공포·탐욕 지수가 아니라 선택 거래소 파생 데이터" in workspace
    assert "관찰 후보 XAI 비교" in workspace
    assert "[MARKET_TREND_SNAPSHOT]" in workspace
    assert "MARKET_TREND_SNAPSHOT_MARKER" in assistant
    assert "시장 트렌드 화면의 기간·기관·수집시각·표본 근거" in assistant
    assert "onAskAssistant={(question) => openAssistant(question, activeService)}" in app


def test_stock_long_period_history_is_sequential_and_today_uses_public_quote_only():
    workspace = (ROOT / "webui" / "src" / "components" / "LegacyFeatureWorkspaces.tsx").read_text(encoding="utf-8")

    assert 'period === "today" || !source' in workspace
    assert "symbols.reduce<Promise<Array<any>>>" in workspace
    assert 'client.candles(symbol, "1d", 45, source, "stock")' in workspace
    assert "Promise.all(symbols.map((symbol) => source ? client.candles" not in workspace
