"""UI-neutral application services for the remaining Web UI workspaces.

These adapters reuse the existing domain engines, but shape their output for a
strict local gateway.  They never import a desktop UI module and never turn a
read request into a trading command.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from config.settings import load_settings
from trading.financial_intelligence.service import FinancialIntelligenceService
from trading.life_finance import FinanceSimulator, LifeFinanceManager
from trading.life_finance_products import FinanceProductAdvisor
from trading.tax_calculation_service import (
    calc_financial_investment_tax,
    calc_year_end_tax_settlement,
    check_financial_income_comprehensive_tax,
    compare_tax_saving_accounts,
    generate_tax_optimization_summary,
)

from .asset_insight_data import load_closed_trade_records
from .query_services import AccountQueryService


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _public_catalog_status(status: Mapping[str, Any]) -> dict[str, Any]:
    """Do not expose local catalog paths through the renderer."""
    return {
        str(name): {
            "source_kind": str((row or {}).get("source_kind") or "unknown"),
            "exists": bool((row or {}).get("exists")),
            "updated_at": str((row or {}).get("mtime_str") or "N/A"),
        }
        for name, row in status.items()
        if isinstance(row, Mapping)
    }


class AdvancedFeatureServices:
    """Account-scoped facade for finance intelligence, portfolio and finance."""

    MARKET_PRESETS: dict[str, list[dict[str, Any]]] = {
        "blockchain": [
            {"symbol": "BTCUSDT", "asset_type": "crypto", "watched": True},
            {"symbol": "ETHUSDT", "asset_type": "crypto", "watched": True},
            {"symbol": "SOLUSDT", "asset_type": "crypto", "watched": True},
        ],
        "stock": [
            {"symbol": "SPY", "asset_type": "etf", "watched": True},
            {"symbol": "QQQ", "asset_type": "etf", "watched": True},
            {"symbol": "^KS11", "asset_type": "index", "watched": True},
        ],
        "ai_analyst": [
            {"symbol": "BTCUSDT", "asset_type": "crypto", "watched": True},
            {"symbol": "SPY", "asset_type": "etf", "watched": True},
            {"symbol": "^KS11", "asset_type": "index", "watched": True},
        ],
    }

    def __init__(self, *, data_dir: Path, queries: AccountQueryService):
        self.data_dir = Path(data_dir)
        self.queries = queries
        intelligence_dir = self.data_dir / "financial_intelligence"
        intelligence_dir.mkdir(parents=True, exist_ok=True)
        settings = dict(load_settings(persist_migrations=False) or {})
        self.settings = settings
        self.intelligence = FinancialIntelligenceService(
            intelligence_dir / "web_ui.sqlite3",
            settings=dict(settings.get("financial_intelligence") or {}),
        )
        self.product_advisor = FinanceProductAdvisor(auto_refresh_interval=0)

    def refresh_settings(self, settings: Mapping[str, Any]) -> None:
        """Keep Web finance readers on the same canonical settings revision."""
        updated = deepcopy(dict(settings or {}))
        self.settings.clear()
        self.settings.update(updated)
        self.intelligence.refresh_settings(updated.get("financial_intelligence") or {})

    def financial_intelligence_snapshot(self, *, service: str) -> dict[str, Any]:
        normalized = str(service or "").strip().lower()
        if normalized not in self.MARKET_PRESETS:
            raise ValueError("unsupported_financial_intelligence_service")
        workspace = self.queries.workspace(
            "ai_analyst" if normalized == "ai_analyst" else normalized,
            f"{normalized}.intelligence",
        )
        decisions = list(workspace.get("ai_decisions") or [])
        analyses = list(workspace.get("ai_analysis") or [])
        risk = list(workspace.get("risk") or [])
        return {
            "schema_version": "1.0.0",
            "service": normalized,
            "dashboard": self.intelligence.dashboard_snapshot(),
            "evidence": {
                "ai_decisions": decisions[:25],
                "ai_analysis": analyses[:25],
                "risk": risk[:25],
                "execution": list(workspace.get("execution") or [])[:25],
            },
            "summary": {
                "decision_count": len(decisions),
                "analysis_count": len(analyses),
                "risk_count": len(risk),
                "data_status": "available" if decisions or analyses or risk else "insufficient_data",
            },
            "market_presets": self.MARKET_PRESETS[normalized],
            "direct_trade_signal": False,
            "captured_at": _now(),
        }

    def refresh_financial_market(
        self,
        *,
        service: str,
        universe: Iterable[Mapping[str, Any]] = (),
        use_network: bool = False,
    ) -> dict[str, Any]:
        normalized = str(service or "").strip().lower()
        if normalized not in self.MARKET_PRESETS:
            raise ValueError("unsupported_financial_intelligence_service")
        rows = [dict(item) for item in universe] or [dict(item) for item in self.MARKET_PRESETS[normalized]]
        if len(rows) > 20:
            raise ValueError("financial_intelligence_universe_too_large")
        chart_points: list[dict[str, Any]] = next((
            [dict(point) for point in list(item.get("points") or []) if isinstance(point, Mapping)]
            for item in rows if item.get("points")
        ), [])
        if use_network:
            # Preserve the legacy widget contract: hydrate each requested
            # market with the shared provider and retain the first available
            # series for the visible price chart.  Calling global_market with
            # use_network=True alone produced summaries but discarded the
            # chart series in the Web shell.
            hydrated: list[dict[str, Any]] = []
            for item in rows:
                symbol = str(item.get("symbol") or "").strip()
                asset_type = str(item.get("asset_type") or "stock").strip().lower()
                fetched = self._history(symbol, asset_type)
                points = [dict(point) for point in list(fetched.get("points") or []) if isinstance(point, Mapping)]
                hydrated.append({**item, "points": points})
                if not chart_points and points:
                    chart_points = points
            result = self.intelligence.global_market(hydrated, use_network=False)
        else:
            result = self.intelligence.global_market(rows, use_network=False)
        result["_chart_points"] = chart_points
        return {
            "schema_version": "1.0.0",
            "service": normalized,
            "market": result,
            "direct_trade_signal": False,
            "captured_at": _now(),
        }

    @staticmethod
    def _allowed_actions(service: str) -> set[str]:
        return {
            "blockchain": {"market", "events", "screener", "technical", "backtest"},
            "stock": {"market", "fundamental", "valuation", "screener", "technical", "backtest", "institutional"},
            "ai_analyst": {"market", "events", "narrative", "macro"},
        }.get(service, set())

    def _history(self, symbol: str, asset_type: str) -> dict[str, Any]:
        if asset_type == "crypto":
            return self.intelligence.provider.fetch_binance_history(symbol, interval="1d", limit=200)
        return self.intelligence.provider.fetch_yahoo_history(
            symbol, range_name="6mo", interval="1d", asset_type=asset_type,
        )

    def run_financial_intelligence_action(
        self,
        *,
        service: str,
        action: str,
        payload: Mapping[str, Any],
        account_snapshot: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the same read-only actions exposed by the legacy intelligence widget."""
        normalized = str(service or "").strip().lower()
        action = str(action or "").strip().lower()
        if action not in self._allowed_actions(normalized):
            raise ValueError("unsupported_financial_intelligence_action")
        values = dict(payload or {})
        financial = dict(self.settings.get("financial_intelligence") or {})

        if action == "market":
            universe = values.get("universe") or self.MARKET_PRESETS[normalized]
            result = self.refresh_financial_market(
                service=normalized,
                universe=universe if isinstance(universe, list) else (),
                use_network=bool(values.get("use_network", True)),
            )
        elif action == "events":
            events = [dict(row) for row in financial.get("event_feed_items", []) if isinstance(row, Mapping)]
            rss_urls = [str(url).strip() for url in financial.get("news_rss_urls", []) if str(url).strip()]
            if not events and not rss_urls:
                result = {"status": "configuration_required", "message": "현재 운영 일정·뉴스 공급자가 연결되지 않았습니다. 중앙 공급자 연결 후 자동 제공됩니다."}
            else:
                positions = self._position_rows(account_snapshot)
                result = self.intelligence.event_risk(events, positions)
                news_rows: list[dict[str, Any]] = []
                for url in rss_urls[:10]:
                    news_rows.extend(self.intelligence.news.fetch_rss(url).get("items") or [])
                if news_rows:
                    held = [str(row.get("symbol") or "") for row in positions]
                    result["news"] = self.intelligence.news_and_narratives(news_rows, held)
        elif action == "narrative":
            rss_urls = [str(url).strip() for url in financial.get("news_rss_urls", []) if str(url).strip()]
            if not rss_urls:
                result = {"status": "configuration_required", "message": "운영 뉴스 공급자가 연결되지 않았습니다. 연결되면 이 화면이 자동으로 채워집니다."}
            else:
                rows: list[dict[str, Any]] = []
                for url in rss_urls[:10]:
                    rows.extend(self.intelligence.news.fetch_rss(url).get("items") or [])
                held = [str(row.get("symbol") or "") for row in self._position_rows(account_snapshot)]
                result = self.intelligence.news_and_narratives(rows, held)
        elif action == "macro":
            indicators = financial.get("macro_indicators")
            result = ({"macro": self.intelligence.macro.classify(indicators)} if isinstance(indicators, Mapping) and indicators else {
                "status": "configuration_required", "message": "공식 거시지표 공급자가 아직 연결되지 않았습니다. 임의 수치로 결과를 만들지 않습니다.",
            })
        elif action == "fundamental":
            provider = str(values.get("provider") or "dart").lower()
            code = str(values.get("code") or "").strip()
            if not code:
                raise ValueError("financial_intelligence_company_code_required")
            result = self.intelligence.fetch_stock_research(
                provider,
                cik=code,
                sec_user_agent=str(financial.get("sec_user_agent") or ""),
                corp_code=code,
                business_year=str(values.get("year") or datetime.now().year),
                dart_api_key=str(financial.get("dart_api_key") or ""),
            )
        elif action == "valuation":
            result = self.intelligence.valuation.scenario_dcf(
                float(values.get("base_fcf") or 0),
                float(values.get("shares") or 0),
                float(values.get("net_debt") or 0),
            )
        elif action in {"screener", "technical", "backtest"}:
            default_symbol = "BTC" if normalized == "blockchain" else "AAPL"
            asset_type = "crypto" if normalized == "blockchain" else "stock"
            symbols = [token.strip() for token in str(values.get("symbols") or values.get("symbol") or default_symbol).split(",") if token.strip()]
            if not symbols or len(symbols) > 20:
                raise ValueError("financial_intelligence_symbol_count_invalid")
            if action == "screener":
                hydrated = []
                errors = []
                for symbol in symbols:
                    fetched = self._history(symbol, asset_type)
                    if fetched.get("status") != "ok":
                        errors.append({"symbol": symbol, "error": fetched.get("error")})
                    hydrated.append({"symbol": symbol, "asset_type": asset_type, "points": fetched.get("points") or []})
                market = self.intelligence.global_market(hydrated, use_network=False)
                screened = self.intelligence.screener.screen(
                    market.get("summaries") or [],
                    [{"field": "price", "op": "gte", "value": float(values.get("min_price") or 0)}],
                )
                result = {"status": market.get("status"), "조건 통과 종목": screened, "수집 오류": errors}
            else:
                symbol = symbols[0]
                fetched = self._history(symbol, asset_type)
                points = list(fetched.get("points") or [])
                if action == "technical":
                    closes = [row.get("close", row.get("price")) for row in points]
                    volumes = [row.get("volume", 0) for row in points]
                    result = {"종목": symbol.upper(), **self.intelligence.technical.analyze(closes, volumes), "chart_points": points}
                else:
                    fast_n = int(values.get("fast") or 5)
                    slow_n = int(values.get("slow") or 20)
                    if fast_n <= 0 or slow_n <= fast_n:
                        raise ValueError("financial_intelligence_average_window_invalid")
                    bars = [{"open": row.get("open"), "close": row.get("close", row.get("price"))} for row in points]
                    def signal(rows: list[dict[str, Any]], index: int) -> str:
                        if index < slow_n:
                            return "HOLD"
                        closes = [float(row["close"]) for row in rows[:index + 1] if row.get("close") is not None]
                        if len(closes) < slow_n:
                            return "HOLD"
                        return "LONG" if sum(closes[-fast_n:]) / fast_n > sum(closes[-slow_n:]) / slow_n else "CLOSE"
                    result = self.intelligence.backtest.run(
                        bars, signal, fee_rate=0.001, slippage_bps=5,
                        spread_bps=2, execution_delay_bars=1,
                    ).to_dict()
                    result["chart_points"] = points
        elif action == "institutional":
            current = financial.get("institutional_current")
            previous = financial.get("institutional_previous")
            result = self.intelligence.institutional.changes(current, previous) if isinstance(current, list) and isinstance(previous, list) else {
                "status": "configuration_required", "message": "기관 보유 데이터 공급자가 아직 연결되지 않았습니다.",
            }
        else:
            analysis = self.portfolio_analysis(account_snapshot=account_snapshot)
            result = self.intelligence.portfolio_report(analysis.get("positions") or [], analysis.get("recent_closed_trades") or [])

        return {
            "schema_version": "1.0.0",
            "service": normalized,
            "action": action,
            "result": result,
            "direct_trade_signal": False,
            "order_submitted": False,
            "captured_at": _now(),
        }

    @staticmethod
    def _position_rows(account_snapshot: Mapping[str, Any] | None) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        sources = dict((account_snapshot or {}).get("sources") or {})
        for source, raw_account in sources.items():
            account = raw_account if isinstance(raw_account, Mapping) else {}
            if account.get("status") not in {None, "success"}:
                continue
            balance = account.get("balance") or {}
            if isinstance(balance, Mapping):
                balance = balance.get("balance", balance)
            cash = None
            cash_currency = "KRW" if str(source) in {"kis", "kiwoom", "shinhan", "mirae", "upbit", "bithumb", "coinone"} else "USDT"
            if isinstance(balance, Mapping):
                cash = balance.get("cash", balance.get(cash_currency))
                if isinstance(cash, Mapping):
                    cash = cash.get("total", cash.get("balance", cash.get("wallet_balance")))
                if cash is not None:
                    output.append({"source": str(source), "symbol": cash_currency, "side": "CASH",
                                   "quantity": _number(cash), "market_value": _number(cash),
                                   "currency": cash_currency, "unrealized_pnl": 0.0})
            positions = account.get("positions") or []
            if isinstance(positions, Mapping):
                positions = [dict(value, symbol=key) if isinstance(value, Mapping) else {"symbol": key, "value": value} for key, value in positions.items()]
            for raw in positions if isinstance(positions, list) else []:
                if not isinstance(raw, Mapping):
                    continue
                quantity = _number(raw.get("quantity", raw.get("size", raw.get("positionAmt"))))
                price = _number(raw.get("mark_price", raw.get("markPrice", raw.get("current_price", raw.get("price")))))
                market_value = abs(_number(raw.get("market_value")) or quantity * price)
                output.append({
                    "source": str(source),
                    "symbol": str(raw.get("symbol") or raw.get("asset") or "unknown"),
                    "side": str(raw.get("side") or ("LONG" if quantity > 0 else "SHORT" if quantity < 0 else "FLAT")),
                    "quantity": quantity,
                    "market_value": market_value,
                    "allocation_value": 0.0 if cash is not None and str(source) in {"binance", "bybit", "okx", "bitget"} else market_value,
                    "valuation_status": "priced" if market_value > 0 else "price_unavailable",
                    "currency": str(raw.get("currency") or ("KRW" if str(source) in {"upbit", "bithumb", "coinone", "kiwoom", "shinhan", "mirae", "kis"} else "USDT")),
                    "unrealized_pnl": _number(raw.get("unrealized_pnl", raw.get("unrealizedPnl"))),
                })
        return output

    @staticmethod
    def _performance_by_currency(trades: list[dict[str, Any]]) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for trade in trades:
            grouped[str(trade.get("currency") or "UNKNOWN")].append(trade)
        result: dict[str, Any] = {}
        for currency, rows in grouped.items():
            pnl = [_number(row.get("pnl")) for row in reversed(rows)]
            cumulative = 0.0
            peak = 0.0
            max_drawdown_amount = 0.0
            curve = []
            for value in pnl:
                cumulative += value
                peak = max(peak, cumulative)
                max_drawdown_amount = max(max_drawdown_amount, peak - cumulative)
                curve.append(round(cumulative, 8))
            wins = sum(1 for value in pnl if value > 0)
            gross_profit = sum(value for value in pnl if value > 0)
            gross_loss = abs(sum(value for value in pnl if value < 0))
            result[currency] = {
                "trades": len(rows),
                "wins": wins,
                "win_rate": wins / len(rows) if rows else 0.0,
                "net_pnl": sum(pnl),
                "gross_profit": gross_profit,
                "gross_loss": gross_loss,
                "profit_factor": gross_profit / gross_loss if gross_loss else None,
                "max_drawdown_amount": max_drawdown_amount,
                "cumulative_pnl": curve[-120:],
            }
        return result

    def portfolio_analysis(self, *, account_snapshot: Mapping[str, Any] | None, paper_records=None) -> dict[str, Any]:
        from web_platform.asset_insight_data import load_live_history_evidence
        history = load_live_history_evidence(self.queries.db_path)
        loaded = load_closed_trade_records(self.queries.db_path, limit=5000, confirmed_only=True)
        trades = list(paper_records) if paper_records is not None else list(loaded.get("records") or [])
        positions = self._position_rows(account_snapshot)
        values: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for position in positions:
            values[str(position["currency"])][str(position["symbol"])] += _number(position.get("allocation_value", position["market_value"]))
        allocation: dict[str, Any] = {}
        for currency, symbol_values in values.items():
            total = sum(symbol_values.values())
            if total <= 0:
                continue
            weights = {symbol: value / total if total else 0.0 for symbol, value in symbol_values.items()}
            max_weight = max(weights.values(), default=0.0)
            hhi = sum(weight * weight for weight in weights.values())
            allocation[currency] = {
                "total_value": total,
                "weights": weights,
                "max_weight": max_weight,
                "hhi": hhi,
                "concentration": "high" if max_weight >= 0.6 or hhi >= 0.5 else "medium" if max_weight >= 0.4 or hhi >= 0.3 else "balanced",
                "guidance": "단일 종목 비중을 검토하세요." if max_weight >= 0.6 else "현재 통화군 내 비중을 유지 관찰하세요.",
            }
        return {
            "schema_version": "1.0.0",
            "positions": positions,
            "unvalued_position_count": sum(1 for row in positions if row.get("valuation_status") == "price_unavailable" and row.get("quantity")),
            "allocation_basis": "현금·예수금 및 가격 확인된 현물 평가 · 선물 명목노출은 잔고에 더하지 않음 · 미평가 보유분 제외",
            "allocation_by_currency": allocation,
            "live_history_evidence": history,
            "performance_by_currency": self._performance_by_currency(trades),
            "performance_basis": "PAPER 유효 가상 청산 · 최근 최대 5,000건 · 실제 계좌 잔고와 별도" if paper_records is not None else "LIVE 체결 대조 완료 순손익 · 최근 최대 5,000건 · PAPER 제외",
            "execution_mode": "paper" if paper_records is not None else "live",
            "account_status": {source: {"status": row.get("status"), "captured_at": row.get("captured_at")} for source, row in dict((account_snapshot or {}).get("sources") or {}).items() if isinstance(row, Mapping)},
            "recent_closed_trades": trades[:100],
            "risk_records": self.queries.table_rows("risk_log", limit=100),
            "data_status": "available" if positions or trades else "insufficient_data",
            "fresh_account_data": bool(account_snapshot),
            "currency_separation": True,
            "recommendations_only": True,
            "correlation": {"status": "insufficient_data", "reason": "aligned_price_series_required"},
            "captured_at": _now(),
        }

    @staticmethod
    def life_finance_analysis(manager: LifeFinanceManager) -> dict[str, Any]:
        today = date.today()
        report = manager.get_monthly_report(today.year, today.month)
        monthly_income = _number(report.total_income)
        monthly_expenses = _number(report.total_expense)
        return {
            "schema_version": "1.0.0",
            "monthly_savings": manager.get_monthly_stats(12),
            "spending_trend": manager.get_spending_trend(12),
            "category_stats": manager.get_category_stats(),
            "alerts": [alert.to_dict() for alert in manager.get_finance_alerts()],
            "projection": FinanceSimulator.project_savings(monthly_income, monthly_expenses, months=12),
            "projection_basis": {
                "monthly_income": monthly_income,
                "monthly_expenses": monthly_expenses,
                "inflation_rate": 0.02,
            },
            "captured_at": _now(),
        }

    def product_catalog(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "catalog": _public_catalog_status(self.product_advisor.get_catalog_status()),
            "counts": {
                "loan": len(self.product_advisor.loan_products),
                "insurance": len(self.product_advisor.insurance_products),
                "savings": len(self.product_advisor.savings_products),
            },
            "disclaimer": "상품 비교는 정보 제공용이며 가입·신청 또는 수익 보장이 아닙니다. 공시 원문과 실제 약관을 확인하세요.",
            "captured_at": _now(),
        }

    def compare_product(
        self, *, product_type: str, amount: float, term_months: int,
        category: str | None, credit_score: str = "보통 (650~750)",
    ) -> dict[str, Any]:
        normalized = str(product_type or "").strip().lower()
        if normalized == "loan":
            result = self.product_advisor.compare_loans(amount, term_months, category)
            result = self.product_advisor.apply_credit_adjustment_to_loans(result, credit_score)
        elif normalized == "insurance":
            result = self.product_advisor.compare_insurances(amount, category)
        elif normalized == "savings":
            result = self.product_advisor.compare_savings(amount, term_months)
            result = self.product_advisor.apply_credit_adjustment_to_savings(result, credit_score)
        else:
            raise ValueError("unsupported_finance_product_type")
        result.pop("catalog_source", None)
        return {
            "schema_version": "1.0.0",
            "product_type": normalized,
            "credit_profile": credit_score,
            "result": result,
            "application_submitted": False,
            "captured_at": _now(),
        }

    @staticmethod
    def calculate_tax(*, calculation: str, values: Mapping[str, Any]) -> dict[str, Any]:
        allowed = {
            "year_end": calc_year_end_tax_settlement,
            "financial_income": check_financial_income_comprehensive_tax,
            "investment": calc_financial_investment_tax,
            "saving_accounts": compare_tax_saving_accounts,
            "optimization": generate_tax_optimization_summary,
        }
        function = allowed.get(str(calculation or "").strip().lower())
        if function is None:
            raise ValueError("unsupported_tax_calculation")
        result = function(**dict(values))
        return {
            "schema_version": "1.0.0",
            "calculation": calculation,
            "result": result,
            "official_filing": False,
            "law_basis": "calculator_reference_dataset",
            "captured_at": _now(),
        }
