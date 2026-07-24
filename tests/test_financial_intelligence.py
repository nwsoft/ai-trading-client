from __future__ import annotations

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest

from trading.financial_intelligence.backtest import BacktestEngine
from trading.financial_intelligence.event_calendar import EventCalendarEngine
from trading.financial_intelligence.fundamentals import FundamentalAnalyzer
from trading.financial_intelligence.institutional import InstitutionalHoldingsAnalyzer
from trading.financial_intelligence.macro import IndustryAnalyzer, MacroRegimeEngine
from trading.financial_intelligence.market_data import MarketIntelligenceEngine
from trading.financial_intelligence.narrative_engine import NarrativeEngine
from trading.financial_intelligence.news_pipeline import NewsPipeline
from trading.financial_intelligence.performance import PortfolioPerformanceEngine
from trading.financial_intelligence.providers import CalendarFileProvider, RegulatoryDataProvider
from trading.financial_intelligence.screener import QuantScreener
from trading.financial_intelligence.service import FinancialIntelligenceService
from trading.financial_intelligence.store import FinancialIntelligenceStore
from trading.financial_intelligence.technical import TechnicalIndicatorEngine
from trading.financial_intelligence.valuation import ValuationEngine


def market_points(values):
    return [
        {
            "symbol": "AAPL",
            "asset_type": "stock",
            "price": value,
            "close": value,
            "timestamp": f"2026-01-{index + 1:02d}T00:00:00+00:00",
            "provenance": {"source": "test", "as_of": "2026-01-01T00:00:00+00:00"},
        }
        for index, value in enumerate(values)
    ]


def test_market_returns_and_heatmap():
    engine = MarketIntelligenceEngine()
    summary = engine.summarize_symbol("AAPL", "stock", market_points([100, 105, 110]))
    assert summary["status"] == "ok"
    assert summary["returns"]["1D"] == pytest.approx((110 / 105 - 1) * 100)
    summary["sector"] = "기술"
    heatmap = engine.build_heatmap([summary])
    assert heatmap["cells"][0]["symbol"] == "AAPL"


def test_store_can_persist_from_ui_worker_thread():
    store = FinancialIntelligenceStore(":memory:")

    def write_from_worker():
        return store.upsert_records("market", market_points([100]))

    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(write_from_worker).result(timeout=2) == 1
    assert store.list_records("market")[0]["symbol"] == "AAPL"
    store.close()


def test_event_matching_never_auto_applies():
    engine = EventCalendarEngine()
    starts = datetime.now(timezone.utc) + timedelta(hours=1)
    event = engine.normalize(
        {
            "title": "FOMC",
            "event_type": "fomc",
            "starts_at": starts.isoformat(),
            "importance": 4,
            "asset_types": ["stock", "crypto"],
        }
    )
    matched = engine.match_exposures([event], [{"symbol": "AAPL", "asset_type": "stock"}])
    assert matched[0]["risk_action"]["level"] == "제한 검토"
    assert matched[0]["risk_action"]["auto_apply"] is False


def test_news_dedupe_entity_and_priority():
    pipeline = NewsPipeline()
    rows = [
        pipeline.normalize(
            {
                "title": "Apple announces AI update",
                "summary": "Apple reported a new release",
                "source": "wire",
                "url": "https://example.com/1",
                "published_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        pipeline.normalize(
            {
                "title": "Apple announces new AI update",
                "summary": "Repeated report",
                "source": "copy",
                "url": "https://example.com/2",
                "published_at": "2026-01-01T00:01:00+00:00",
            }
        ),
    ]
    unique = pipeline.score_novelty(pipeline.deduplicate(rows, threshold=0.70))
    assert len(unique) == 1
    assert "AAPL" in unique[0].entities
    prioritized = pipeline.prioritize(unique, ["AAPL"])
    assert prioritized[0]["held_match"] is True


def test_narrative_links_evidence_and_does_not_signal_trade():
    engine = NarrativeEngine()
    narratives = engine.build(
        [
            {
                "news_id": "n1",
                "entities": ["AAPL"],
                "topics": ["기술"],
                "impact_score": 0.8,
                "novelty_score": 0.9,
                "source_score": 0.9,
                "fact_claim": "fact",
            }
        ],
        {"AAPL": 2.0},
        {"AAPL": 1.0},
    )
    assert narratives[0]["evidence_ids"] == ["n1"]
    assert narratives[0]["confirmation"] == "가격·수급 동행"
    assert "trade_signal" not in narratives[0]


def test_fundamentals_metrics_and_risk():
    analyzer = FundamentalAnalyzer()
    result = analyzer.analyze(
        [
            {
                "period": "2024",
                "currency": "KRW",
                "revenue": 100,
                "operating_income": 10,
                "net_income": 8,
                "assets": 200,
                "equity": 100,
                "debt": 50,
                "cash": 20,
                "operating_cash_flow": 12,
                "capital_expenditure": 4,
            },
            {
                "period": "2025",
                "currency": "KRW",
                "revenue": 120,
                "operating_income": 18,
                "net_income": 12,
                "assets": 220,
                "equity": 110,
                "debt": 55,
                "cash": 25,
                "operating_cash_flow": 20,
                "capital_expenditure": 5,
            },
        ]
    )
    assert result["metrics"]["revenue_growth_percent"] == pytest.approx(20)
    assert result["metrics"]["operating_margin_percent"] == pytest.approx(15)
    assert result["metrics"]["free_cash_flow"] == 15


def test_valuation_models_and_assumptions():
    engine = ValuationEngine()
    relative = engine.relative_valuation(
        price=10,
        shares=100,
        earnings=100,
        revenue=500,
        book_value=400,
        ebitda=120,
    )
    assert relative["multiples"]["PER"] == 10
    dcf = engine.dcf(100, 100, growth_rates=[0.05] * 5, wacc=0.1, terminal_growth=0.02)
    assert dcf["value_per_share"] > 0
    reverse = engine.reverse_dcf_growth(dcf["value_per_share"], 100, 100, wacc=0.1, terminal_growth=0.02)
    assert reverse["implied_fcf_growth"] == pytest.approx(0.05, abs=1e-4)
    assert engine.ddm(1, 0.1, 0.02)["value_per_share"] > 0
    assert "value_per_share" in engine.rim(10, 0.15, 0.1)


def test_screener_components_and_account_eligibility():
    screener = QuantScreener()
    result = screener.screen(
        [
            {"symbol": "A", "price": 10, "momentum": 80, "liquidity": 90},
            {"symbol": "B", "price": 1, "momentum": 20, "liquidity": 10},
        ],
        [{"field": "price", "op": "gte", "value": 5}],
        {"momentum": 0.6, "liquidity": 0.4},
    )
    assert [row["symbol"] for row in result] == ["A"]
    eligibility = screener.account_eligibility(
        {"price": 10, "min_quantity": 2, "estimated_slippage_bps": 10},
        available_cash=100,
        risk_budget=50,
    )
    assert eligibility["eligible"] is True


def test_technical_indicators_and_multitimeframe_conflict():
    engine = TechnicalIndicatorEngine()
    up = list(range(1, 80))
    down = list(range(100, 20, -1))
    result = engine.analyze(up, [100] * len(up))
    assert result["ma20"] is not None
    assert result["rsi14"] == 100
    multi = engine.multi_timeframe({"1h": up, "1d": down})
    assert multi["conflict"] is True


def test_performance_metrics_and_grouping():
    engine = PortfolioPerformanceEngine()
    trades = [
        {"pnl": 10, "fee": 1, "asset_type": "stock", "strategy": "a"},
        {"pnl": -5, "fee": 1, "asset_type": "stock", "strategy": "a"},
        {"pnl": 8, "fee": 1, "asset_type": "crypto", "strategy": "b"},
    ]
    metrics = engine.trade_metrics(trades)
    assert metrics["trades"] == 3
    assert metrics["profit_factor"] > 1
    grouped = engine.grouped_metrics(trades, ["asset_type"])
    assert set(grouped["asset_type"]) == {"stock", "crypto"}


def test_backtest_signal_execution_delay_costs_and_walkforward():
    bars = [{"open": price, "close": price} for price in range(100, 140)]
    engine = BacktestEngine()

    def signal(_rows, index):
        return "LONG" if index == 0 else "CLOSE" if index == 20 else "HOLD"

    result = engine.run(bars, signal, fee_rate=0.001, slippage_bps=5, execution_delay_bars=1)
    assert result.status == "ok"
    assert result.trades
    assert result.trades[0]["entry_index"] == 1
    assert result.assumptions["fee_rate"] == 0.001
    assert result.metrics["net_pnl"] == pytest.approx(
        sum(trade["pnl"] - trade["fee"] for trade in result.trades)
    )

    def factory(_train):
        return signal

    walk = engine.walk_forward(bars * 4, factory, train_size=40, test_size=20)
    assert walk["out_of_sample"] is True
    assert walk["windows"]


def test_macro_industry_and_institutional():
    macro = MacroRegimeEngine().classify(
        {"growth_z": 0.5, "inflation_z": -0.3, "liquidity_z": 0.4, "credit_stress_z": 0.0}
    )
    assert macro["cycle"] == "확장"
    assert macro["rule_version"]
    industry = IndustryAnalyzer().analyze(
        [{"symbol": "A", "revenue_growth": 0.2, "operating_margin": 0.1, "valuation_multiple": 15}]
    )
    assert industry["leaders"][0]["symbol"] == "A"
    analyzer = InstitutionalHoldingsAnalyzer()
    changes = analyzer.changes(
        [{"symbol": "A", "weight": 0.2}],
        [{"symbol": "A", "weight": 0.1}, {"symbol": "B", "weight": 0.1}],
    )
    assert {row["action"] for row in changes["changes"]} == {"비중 확대", "청산 추정"}
    assert changes["is_realtime_signal"] is False


def test_store_and_service_end_to_end(tmp_path):
    db_path = tmp_path / "fi.db"
    store = FinancialIntelligenceStore(db_path)
    store.set_feature_status("x", "current", "test")
    assert store.feature_statuses()["x"]["status"] == "current"
    store.upsert_records("news", [{"news_id": "n1", "published_at": "2026-01-01", "source": "test"}])
    assert store.list_records("news")[0]["news_id"] == "n1"
    store.close()

    service = FinancialIntelligenceService(db_path)
    market = service.global_market(
        [{"symbol": "AAPL", "asset_type": "stock", "points": market_points([100, 102, 104])}]
    )
    assert market["summaries"][0]["price"] == 104
    news = service.news_and_narratives(
        [
            {
                "title": "Apple announced earnings",
                "summary": "Apple revenue reported",
                "source": "wire",
                "url": "https://example.com/a",
                "published_at": "2026-01-01T00:00:00+00:00",
            }
        ],
        ["AAPL"],
    )
    assert news["direct_trade_signal"] is False
    assert service.dashboard_snapshot()["feature_status"]


def test_regulatory_provider_normalization_and_ics():
    provider = RegulatoryDataProvider()
    sec = provider.normalize_sec_companyfacts(
        {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {"form": "10-K", "fy": 2025, "fp": "FY", "filed": "2026-02-01", "val": 100}
                            ]
                        }
                    },
                    "NetIncomeLoss": {
                        "units": {
                            "USD": [
                                {"form": "10-K", "fy": 2025, "fp": "FY", "filed": "2026-02-01", "val": 10}
                            ]
                        }
                    },
                }
            }
        }
    )
    assert sec[0]["revenue"] == 100
    assert sec[0]["net_income"] == 10
    dart = provider.normalize_dart(
        [
            {"account_nm": "매출액", "thstrm_amount": "1,000"},
            {"account_nm": "영업이익", "thstrm_amount": "100"},
        ],
        "2025",
    )
    assert dart[0]["revenue"] == 1000
    assert dart[0]["operating_income"] == 100
    ics = CalendarFileProvider.parse_ics(
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:x1\nDTSTART:20260730T180000Z\n"
        "SUMMARY:FOMC\nDESCRIPTION:rate decision\nEND:VEVENT\nEND:VCALENDAR"
    )
    assert ics[0]["title"] == "FOMC"
    assert ics[0]["starts_at"].startswith("2026-07-30")


def test_sec_provider_requires_identified_user_agent():
    result = RegulatoryDataProvider().fetch_sec_companyfacts("320193", "NoahAI")
    assert result["status"] == "configuration_required"
