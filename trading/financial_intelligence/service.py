from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from .backtest import BacktestEngine
from .event_calendar import EventCalendarEngine
from .fundamentals import FundamentalAnalyzer
from .institutional import InstitutionalHoldingsAnalyzer
from .macro import IndustryAnalyzer, MacroRegimeEngine
from .market_data import MarketIntelligenceEngine, PublicMarketDataProvider
from .narrative_engine import NarrativeEngine
from .news_pipeline import NewsPipeline
from .performance import PortfolioPerformanceEngine
from .providers import RegulatoryDataProvider
from .screener import QuantScreener
from .store import FinancialIntelligenceStore
from .technical import TechnicalIndicatorEngine
from .valuation import ValuationEngine


class FinancialIntelligenceService:
    """UI와 AI애널리스트가 공유하는 금융 인텔리전스 파사드."""

    FEATURES = {
        "global_market": "current",
        "sector_heatmap": "current",
        "event_calendar": "current",
        "news": "current",
        "narratives": "current",
        "fundamentals": "current",
        "valuation": "current",
        "screener": "current",
        "technical": "current",
        "portfolio_performance": "current",
        "backtest": "current",
        "industry_macro": "current",
        "institutional": "current",
    }

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        settings: Optional[Mapping[str, Any]] = None,
    ):
        self.settings = dict(settings or {})
        self.store = FinancialIntelligenceStore(db_path)
        self.provider = PublicMarketDataProvider(timeout=float(self.settings.get("timeout", 8.0) or 8.0))
        self.market = MarketIntelligenceEngine()
        self.events = EventCalendarEngine()
        self.news = NewsPipeline(
            entity_aliases=self.settings.get("entity_aliases"),
            source_scores=self.settings.get("source_scores"),
        )
        self.narratives = NarrativeEngine()
        self.fundamentals = FundamentalAnalyzer()
        self.valuation = ValuationEngine()
        self.screener = QuantScreener()
        self.technical = TechnicalIndicatorEngine()
        self.performance = PortfolioPerformanceEngine()
        self.regulatory = RegulatoryDataProvider(timeout=float(self.settings.get("timeout", 12.0) or 12.0))
        self.backtest = BacktestEngine()
        self.macro = MacroRegimeEngine()
        self.industry = IndustryAnalyzer()
        self.institutional = InstitutionalHoldingsAnalyzer()
        for feature_id, status in self.FEATURES.items():
            self.store.set_feature_status(feature_id, status, "financial_intelligence package")

    @staticmethod
    def _run_id(kind: str, inputs: Any) -> str:
        encoded = json.dumps(inputs, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:18]
        return f"{kind}-{digest}"

    def global_market(self, universe: Iterable[Mapping[str, Any]], use_network: bool = False) -> Dict[str, Any]:
        universe_rows = [dict(item) for item in universe]
        summaries = []
        errors = []
        for item in universe_rows:
            symbol = str(item.get("symbol") or "")
            asset_type = str(item.get("asset_type") or "stock")
            points = list(item.get("points") or [])
            if use_network and not points:
                fetched = (
                    self.provider.fetch_binance_history(symbol)
                    if asset_type == "crypto"
                    else self.provider.fetch_yahoo_history(symbol, asset_type=asset_type)
                )
                points = list(fetched.get("points") or [])
                if fetched.get("status") != "ok":
                    errors.append({"symbol": symbol, "error": fetched.get("error")})
            summary = self.market.summarize_symbol(symbol, asset_type, points)
            summary.update(
                {
                    "market_cap": item.get("market_cap"),
                    "held": bool(item.get("held")),
                    "watched": bool(item.get("watched")),
                }
            )
            summaries.append(summary)
            if points:
                self.store.upsert_records("market", points)
        result = {
            "status": "ok" if summaries else "no_data",
            "summaries": summaries,
            "heatmap": self.market.build_heatmap(summaries),
            "errors": errors,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save("global_market", {"universe": universe_rows, "use_network": use_network}, result)
        return result

    def event_risk(
        self,
        raw_events: Iterable[Mapping[str, Any]],
        positions: Iterable[Mapping[str, Any]],
        horizon_hours: int = 72,
    ) -> Dict[str, Any]:
        normalized = [self.events.normalize(dict(row), str(row.get("source") or "user")) for row in raw_events]
        self.store.upsert_records("event", [event.to_dict() for event in normalized])
        matched = self.events.match_exposures(normalized, positions, horizon_hours=horizon_hours)
        result = {"events": [event.to_dict() for event in normalized], "matched": matched, "auto_apply": False}
        self._save("event_risk", {"horizon_hours": horizon_hours}, result)
        return result

    def news_and_narratives(
        self,
        raw_news: Iterable[Mapping[str, Any]],
        held_symbols: Iterable[str] = (),
        price_reactions: Optional[Mapping[str, float]] = None,
        flow_signals: Optional[Mapping[str, float]] = None,
    ) -> Dict[str, Any]:
        normalized = [self.news.normalize(dict(row), str(row.get("source") or "unknown")) for row in raw_news]
        unique = self.news.score_novelty(self.news.deduplicate(normalized))
        prioritized = self.news.prioritize(unique, held_symbols)
        narratives = self.narratives.build(prioritized, price_reactions, flow_signals)
        self.store.upsert_records("news", prioritized)
        self.store.upsert_records(
            "narrative",
            [{**row, "record_id": row["narrative_id"], "as_of": row["generated_at"], "source": "noahai"} for row in narratives],
        )
        result = {"news": prioritized, "narratives": narratives, "direct_trade_signal": False}
        self._save("news_narrative", {"held_symbols": list(held_symbols)}, result)
        return result

    def stock_research(
        self,
        periods: Iterable[Mapping[str, Any]],
        valuation_inputs: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        fundamental_result = self.fundamentals.analyze(periods)
        valuation_result: Dict[str, Any] = {}
        if valuation_inputs:
            mode = str(valuation_inputs.get("mode") or "relative")
            values = {key: value for key, value in valuation_inputs.items() if key != "mode"}
            if mode == "dcf":
                valuation_result = self.valuation.scenario_dcf(**values)
            elif mode == "reverse_dcf":
                valuation_result = self.valuation.reverse_dcf_growth(**values)
            elif mode == "ddm":
                valuation_result = self.valuation.ddm(**values)
            elif mode == "rim":
                valuation_result = self.valuation.rim(**values)
            else:
                valuation_result = self.valuation.relative_valuation(**values)
        result = {"fundamentals": fundamental_result, "valuation": valuation_result}
        self._save("stock_research", {"valuation_mode": (valuation_inputs or {}).get("mode")}, result)
        return result

    def fetch_stock_research(
        self,
        provider: str,
        *,
        cik: str = "",
        sec_user_agent: str = "",
        corp_code: str = "",
        business_year: str = "",
        dart_api_key: str = "",
    ) -> Dict[str, Any]:
        if str(provider).lower() == "sec":
            fetched = self.regulatory.fetch_sec_companyfacts(cik, sec_user_agent)
        elif str(provider).lower() == "dart":
            fetched = self.regulatory.fetch_dart_financials(corp_code, business_year, dart_api_key)
        else:
            return {"status": "configuration_required", "error": "provider must be sec or dart"}
        if fetched.get("status") != "ok":
            return fetched
        return {
            **fetched,
            "analysis": self.fundamentals.analyze(fetched.get("periods") or []),
        }

    def portfolio_report(
        self,
        positions: Iterable[Mapping[str, Any]],
        trades: Iterable[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        position_rows = list(positions)
        trade_rows = list(trades)
        result = {
            "exposure": self.performance.exposure_summary(position_rows),
            "performance": self.performance.trade_metrics(trade_rows),
            "grouped": self.performance.grouped_metrics(
                trade_rows,
                ["asset_type", "strategy", "broker", "market_regime", "decision_type", "hour"],
            ),
        }
        self._save("portfolio", {"position_count": len(position_rows), "trade_count": len(trade_rows)}, result)
        return result

    def dashboard_snapshot(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        events = self.store.list_records("event", 100)
        upcoming = [
            row for row in events
            if now <= self._safe_datetime(row.get("starts_at")) <= now + timedelta(days=7)
        ]
        return {
            "feature_status": self.store.feature_statuses(),
            "market": self.store.list_records("market", 20),
            "upcoming_events": upcoming[:10],
            "news": self.store.list_records("news", 10),
            "narratives": self.store.list_records("narrative", 10),
        }

    @staticmethod
    def _safe_datetime(value: Any) -> datetime:
        try:
            text = str(value or "").replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    def _save(self, kind: str, inputs: Dict[str, Any], result: Dict[str, Any]) -> None:
        self.store.save_analysis(self._run_id(kind, inputs), kind, inputs, result)
