"""Loopback-only gateway for the v3.9.1.13 Web UI."""

from __future__ import annotations

import asyncio
import hmac
import os
import re
import secrets
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config.app_version import RELEASE_BUILD_LABEL, RELEASE_VERSION

from .application_services import ApplicationServices
from .runtime_bridge import STOCK_SOURCES
from .contracts import (
    EventEnvelope,
    CredentialUpdateContract,
    NotificationChannelContract,
    NotificationReportContract,
    NotificationUpdateContract,
    AIProviderDiagnosticContract,
    ChartImageAnalysisContract,
    HealthContract,
    PlatformContract,
    RuntimeCommandContract,
    StockSearchProfileActionContract,
    LifeGoalCreateContract,
    LifeGoalSavingsContract,
    LifeTransactionCreateContract,
    RuntimeSnapshotContract,
    SettingsUpdateContract,
    SettingsRestoreContract,
    StrategyDeleteContract,
    StrategyActionContract,
    StrategyHistoricalValidationContract,
    StrategySubmitContract,
    SessionLoginContract,
    AssistantQueryContract,
    AccountSnapshotRequestContract,
    StatisticsViewBaselineContract,
    StrategySourceAnalyzeContract,
    StrategyDraftValidationContract,
    StrategyMentorContract,
    StrategyPackageImportContract,
    CandleSnapshotContract,
    FinancialMarketRefreshContract,
    FinancialIntelligenceActionContract,
    FinanceProductCompareContract,
    TaxCalculationContract,
    AlphaArenaCommandContract,
)
from .feature_inventory import load_feature_inventory
from .market_data import BinancePublicMarketData, MultiSourcePublicMarketData, PublicMarketDataError


ALLOWED_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "noahai://app",
)


def generate_gateway_token() -> str:
    return secrets.token_urlsafe(32)


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return value.strip()


def create_gateway_app(
    *,
    token: str | None = None,
    runtime_provider: Callable[[], RuntimeSnapshotContract | dict[str, Any]] | None = None,
    market_data: BinancePublicMarketData | None = None,
    application_services: ApplicationServices | None = None,
) -> FastAPI:
    expected_token = str(token or os.environ.get("NOAHAI_GATEWAY_TOKEN") or "").strip()
    if len(expected_token) < 32:
        raise ValueError("NOAHAI_GATEWAY_TOKEN must contain at least 32 characters")

    services = application_services or ApplicationServices()
    provider = runtime_provider or services.runtime_snapshot
    market_provider = market_data or MultiSourcePublicMarketData()

    app = FastAPI(
        title="NoahAI Local Gateway",
        version=RELEASE_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-NoahAI-Intent"],
    )

    @app.middleware("http")
    async def enforce_local_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and origin not in ALLOWED_ORIGINS:
            return _forbidden_response()
        return await call_next(request)

    def require_token(authorization: str | None = Header(default=None)) -> None:
        supplied = _extract_bearer(authorization)
        if not supplied or not hmac.compare_digest(supplied, expected_token):
            raise HTTPException(status_code=401, detail="gateway_authentication_required")

    def require_confirmed_intent(x_noahai_intent: str | None = Header(default=None)) -> None:
        if x_noahai_intent != "confirmed":
            raise HTTPException(status_code=428, detail="explicit_user_intent_required")

    @app.get("/api/v1/health", response_model=HealthContract)
    def health() -> HealthContract:
        return HealthContract(release_version=RELEASE_VERSION)

    @app.get('/api/v1/remote/status', dependencies=[Depends(require_token)])
    def remote_status():
        return services.remote_monitor().status()

    @app.post('/api/v1/remote/configure', dependencies=[Depends(require_token), Depends(require_confirmed_intent)])
    def remote_configure(payload: dict[str, Any]):
        try:
            return services.remote_monitor().configure(payload.get('enabled'), payload.get('name'), payload.get('allow_pause',False))
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.post('/api/v1/remote/resume-entries', dependencies=[Depends(require_token), Depends(require_confirmed_intent)])
    def resume_entries(payload: dict[str, Any]):
        from trading.remote_entry_pause import gate
        try:
            return gate(services.data_dir).set(str(payload.get('source','')),False)
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.get("/api/v1/platform", response_model=PlatformContract, dependencies=[Depends(require_token)])
    def platform() -> PlatformContract:
        return PlatformContract(
            release_version=RELEASE_VERSION,
            release_label=RELEASE_BUILD_LABEL,
        )

    @app.get("/api/v1/session", dependencies=[Depends(require_token)])
    def session_snapshot() -> dict[str, Any]:
        return services.session_snapshot()

    @app.post(
        "/api/v1/session/login",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def session_login(body: SessionLoginContract) -> dict[str, Any]:
        try:
            return services.authenticate(username=body.username, password=body.password)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post(
        "/api/v1/assistant/ask",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def assistant_ask(body: AssistantQueryContract) -> dict[str, Any]:
        try:
            return services.ask_assistant(
                question=body.question,
                service=body.service,
                explanation_level=body.explanation_level,
                mode=body.mode,
                recent_messages=[item.model_dump() for item in body.recent_messages],
                settings_section=body.settings_section,
                data_scope=body.data_scope,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            status = 429 if str(exc) == "interactive_ai_budget_exceeded" else 503
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @app.get("/api/v1/assistant/status", dependencies=[Depends(require_token)])
    def assistant_status() -> dict[str, Any]:
        return services.interactive_ai_status()

    @app.get("/api/v1/features", dependencies=[Depends(require_token)])
    def features() -> dict[str, Any]:
        return load_feature_inventory()

    @app.get("/api/v1/manual", dependencies=[Depends(require_token)])
    def manual() -> dict[str, Any]:
        try:
            return services.manual_snapshot()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/workspaces/{service}/{feature}", dependencies=[Depends(require_token)])
    def workspace_snapshot(
        service: str,
        feature: str,
        source: str = Query(default=""),
        learning_offset: int = Query(default=0, ge=0),
        learning_limit: int = Query(default=50, ge=10, le=200),
        report_period: str = Query(default="today", pattern="^(today|week|month|realtime)$"),
        report_offset: int = Query(default=0, ge=0),
        report_limit: int = Query(default=100, ge=10, le=200),
        statistics_period: str = Query(default="today", pattern="^(today|7d|30d|all|custom)$"),
        statistics_start: str = Query(default="", max_length=40),
        statistics_end: str = Query(default="", max_length=40),
        statistics_mode: str = Query(default="live", pattern="^(live|paper)$"),
        statistics_currency: str = Query(default="", pattern="^[A-Z]{0,10}$"),
    ) -> dict[str, Any]:
        allowed_services = {"blockchain", "stock", "portfolio", "personal_finance", "ai_analyst"}
        if service not in allowed_services or not re.fullmatch(r"[a-z0-9_.-]{2,80}", feature):
            raise HTTPException(status_code=400, detail="unsupported_workspace")
        try:
            return services.workspace_snapshot(
                service=service,
                feature=feature,
                source=source,
                learning_offset=learning_offset,
                learning_limit=learning_limit,
                report_period=report_period,
                report_offset=report_offset,
                report_limit=report_limit,
                statistics_period=statistics_period,
                statistics_start=statistics_start,
                statistics_end=statistics_end,
                statistics_mode=statistics_mode,
                statistics_currency=statistics_currency,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/api/v1/statistics/view-baseline",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def update_statistics_view_baseline(body: StatisticsViewBaselineContract) -> dict[str, Any]:
        try:
            return services.update_statistics_view_baseline(
                service=body.service,
                source=body.source,
                action=body.action,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/financial-intelligence/{service}", dependencies=[Depends(require_token)])
    def financial_intelligence_snapshot(service: str) -> dict[str, Any]:
        try:
            return services.financial_intelligence_snapshot(service=service)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/api/v1/financial-intelligence/market",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def refresh_financial_market(body: FinancialMarketRefreshContract) -> dict[str, Any]:
        try:
            return services.refresh_financial_market(
                service=body.service,
                universe=[item.model_dump() for item in body.universe],
                use_network=body.use_network,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post(
        "/api/v1/financial-intelligence/action",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def run_financial_intelligence_action(body: FinancialIntelligenceActionContract) -> dict[str, Any]:
        try:
            return services.run_financial_intelligence_action(
                service=body.service,
                action=body.action,
                payload=body.payload,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/portfolio/analysis", dependencies=[Depends(require_token)])
    def portfolio_analysis(statistics_mode: str = Query(default="live", pattern="^(live|paper)$")) -> dict[str, Any]:
        return services.portfolio_analysis(statistics_mode=statistics_mode)

    @app.post(
        "/api/v1/portfolio/snapshot",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def save_portfolio_snapshot() -> dict[str, Any]:
        try:
            return services.save_portfolio_snapshot()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/alpha-arena", dependencies=[Depends(require_token)])
    def alpha_arena_snapshot() -> dict[str, Any]:
        return services.alpha_arena_snapshot()

    @app.post(
        "/api/v1/alpha-arena/commands",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def alpha_arena_command(body: AlphaArenaCommandContract) -> dict[str, Any]:
        try:
            return services.control_alpha_arena(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/v1/runtime/snapshot", response_model=RuntimeSnapshotContract, dependencies=[Depends(require_token)])
    def runtime_snapshot() -> RuntimeSnapshotContract:
        snapshot = provider()
        if isinstance(snapshot, RuntimeSnapshotContract):
            return snapshot
        return RuntimeSnapshotContract.model_validate(snapshot)

    @app.post(
        "/api/v1/runtime/account-snapshot",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def account_snapshot(body: AccountSnapshotRequestContract) -> dict[str, Any]:
        try:
            return services.refresh_account_snapshot(
                sources=list(body.sources),
                force_refresh=body.force_refresh,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/v1/settings", dependencies=[Depends(require_token)])
    def settings_snapshot() -> dict[str, Any]:
        return services.settings_snapshot()

    @app.get("/api/v1/settings/backups", dependencies=[Depends(require_token)])
    def settings_backups() -> dict[str, Any]:
        return services.settings_backups(limit=3)

    @app.get("/api/v1/settings/diagnostics", dependencies=[Depends(require_token)])
    def settings_diagnostics() -> dict[str, Any]:
        return services.settings_diagnostics()

    @app.post(
        "/api/v1/settings/ai-provider-check",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def check_ai_provider(body: AIProviderDiagnosticContract) -> dict[str, Any]:
        try:
            return services.check_ai_provider(
                provider=body.provider,
                model=body.model,
                capability=body.capability,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post(
        "/api/v1/assistant/chart-analysis",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def analyze_chart_image(body: ChartImageAnalysisContract) -> dict[str, Any]:
        try:
            return services.analyze_chart_image(
                file_name=body.file_name,
                image_data_url=body.image_data_url,
                service=body.service,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            status = 429 if str(exc) == "interactive_ai_budget_exceeded" else 503
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @app.post(
        "/api/v1/settings/restore",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def restore_settings(body: SettingsRestoreContract) -> dict[str, Any]:
        try:
            return services.restore_settings_backup(
                expected_revision=body.expected_revision,
                backup_name=body.backup_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            status = 409 if str(exc) == "settings_revision_conflict" else 503
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @app.post(
        "/api/v1/settings",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def update_settings(body: SettingsUpdateContract) -> dict[str, Any]:
        try:
            return services.update_settings(
                expected_revision=body.expected_revision,
                changes=body.changes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            status = 409 if str(exc) == "settings_revision_conflict" else 503
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @app.post(
        "/api/v1/settings/credentials",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def update_credentials(body: CredentialUpdateContract) -> dict[str, Any]:
        try:
            return services.update_credentials(
                expected_revision=body.expected_revision,
                provider=body.provider,
                values=body.values,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            status = 409 if str(exc) == "settings_revision_conflict" else 503
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @app.get("/api/v1/notifications/status", dependencies=[Depends(require_token)])
    def notification_status() -> dict[str, Any]:
        return services.notification_status()

    @app.post(
        "/api/v1/notifications/test",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def test_notification(body: NotificationChannelContract) -> dict[str, Any]:
        try:
            return services.test_notification(channel=body.channel)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post(
        "/api/v1/notifications/telegram/discover",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def discover_telegram_chats() -> dict[str, Any]:
        try:
            return services.discover_telegram_chats()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post(
        "/api/v1/notifications/report",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def send_report_notification(body: NotificationReportContract) -> dict[str, Any]:
        try:
            return services.send_report_notification(
                title=body.title, message=body.message, source=body.source,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/v1/notifications/update-available",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def send_update_notification(body: NotificationUpdateContract) -> dict[str, Any]:
        try:
            return services.send_update_notification(
                version=body.version, current_version=body.current_version,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/stocks/search-profile", dependencies=[Depends(require_token)])
    def stock_search_profile() -> dict[str, Any]:
        return services.stock_search_profile()

    @app.get("/api/v1/stocks/suggestions", dependencies=[Depends(require_token)])
    def stock_search_suggestions(
        source: str = Query(default="kiwoom", min_length=2, max_length=32),
        query: str = Query(default="", max_length=80),
        asset_mode: str = Query(default="all", max_length=12),
    ) -> dict[str, Any]:
        try:
            return services.stock_search_suggestions(source=source, query=query, asset_mode=asset_mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/api/v1/stocks/search-profile",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def update_stock_search_profile(body: StockSearchProfileActionContract) -> dict[str, Any]:
        try:
            return services.update_stock_search_profile(action=body.action, symbol=body.symbol)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/strategies", dependencies=[Depends(require_token)])
    def strategy_catalog() -> dict[str, Any]:
        return services.strategy_catalog()

    @app.post(
        "/api/v1/strategies/source-analysis",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def strategy_source_analysis(body: StrategySourceAnalyzeContract) -> dict[str, Any]:
        try:
            return services.analyze_strategy_source(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            status = 429 if str(exc) == "interactive_ai_budget_exceeded" else 503
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @app.post(
        "/api/v1/strategies/draft-validation",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def strategy_draft_validation(body: StrategyDraftValidationContract) -> dict[str, Any]:
        try:
            return services.validate_strategy_draft(
                rules=body.rules, compiler_issues=body.compiler_issues,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/v1/strategies/mentor",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def strategy_mentor(body: StrategyMentorContract) -> dict[str, Any]:
        return services.strategy_mentor(profile=body.profile)

    @app.get("/api/v1/strategies/{scope}/{strategy_key}/{version_id}/package", dependencies=[Depends(require_token)])
    def strategy_package_export(scope: str, strategy_key: str, version_id: str) -> dict[str, Any]:
        try:
            return services.export_strategy_package(scope=scope, strategy_key=strategy_key, version_id=version_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get(
        "/api/v1/strategies/{scope}/{strategy_key}/{version_id}/execution-evidence",
        dependencies=[Depends(require_token)],
    )
    def strategy_execution_evidence_export(
        scope: str, strategy_key: str, version_id: str,
    ) -> dict[str, Any]:
        try:
            return services.export_strategy_execution_evidence(
                scope=scope,
                strategy_key=strategy_key,
                version_id=version_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/api/v1/strategies/package",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def strategy_package_import(body: StrategyPackageImportContract) -> dict[str, Any]:
        try:
            return services.import_strategy_package(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete(
        "/api/v1/strategies",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def delete_strategy(body: StrategyDeleteContract) -> dict[str, Any]:
        try:
            return services.delete_strategy(
                scope=body.scope,
                strategy_key=body.strategy_key,
                version_id=body.version_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/api/v1/strategies",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def submit_strategy(body: StrategySubmitContract) -> dict[str, Any]:
        try:
            return services.submit_strategy(
                scope=body.scope, name=body.name, rules=body.rules,
                source_kind=body.source_kind, source_reference=body.source_reference,
                strategy_key=body.strategy_key,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/api/v1/strategies/actions",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def strategy_action(body: StrategyActionContract) -> dict[str, Any]:
        try:
            return services.strategy_action(
                scope=body.scope, strategy_key=body.strategy_key,
                version_id=body.version_id, action=body.action,
                live_confirmation=body.live_confirmation,
                operation_mode=body.operation_mode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/v1/strategies/historical-validation",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def strategy_historical_validation(body: StrategyHistoricalValidationContract) -> dict[str, Any]:
        try:
            return services.run_strategy_historical_validation(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/life-finance", dependencies=[Depends(require_token)])
    def life_finance() -> dict[str, Any]:
        return services.life_finance_snapshot()

    @app.get("/api/v1/life-finance/analysis", dependencies=[Depends(require_token)])
    def life_finance_analysis() -> dict[str, Any]:
        return services.life_finance_analysis()

    @app.get("/api/v1/life-finance/products", dependencies=[Depends(require_token)])
    def finance_product_catalog() -> dict[str, Any]:
        return services.finance_product_catalog()

    @app.post(
        "/api/v1/life-finance/products/compare",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def compare_finance_product(body: FinanceProductCompareContract) -> dict[str, Any]:
        try:
            return services.compare_finance_product(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/api/v1/life-finance/tax",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def calculate_life_tax(body: TaxCalculationContract) -> dict[str, Any]:
        payload = body.model_dump()
        calculation = str(payload.pop("calculation"))
        fields = {
            "year_end": {
                "annual_salary", "credit_card", "debit_cash", "medical_expense",
                "education_expense", "donation", "pension_savings",
                "irp_contribution", "personal_deduction_count",
            },
            "financial_income": {"interest_income", "dividend_income", "annual_salary"},
            "investment": {"domestic_stock_profit", "overseas_stock_profit", "etf_profit", "other_profit"},
            "saving_accounts": {"annual_salary", "annual_investment", "investment_years", "expected_return_rate", "isa_type"},
            "optimization": {
                "annual_salary", "pension_savings", "irp_contribution", "credit_card",
                "debit_cash", "medical_expense", "education_expense", "donation",
                "interest_income", "dividend_income",
            },
        }[calculation]
        try:
            return services.calculate_life_tax(
                calculation=calculation,
                values={key: value for key, value in payload.items() if key in fields},
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/api/v1/life-finance/transactions",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def add_life_transaction(body: LifeTransactionCreateContract) -> dict[str, Any]:
        try:
            return services.add_life_transaction(
                transaction_date=body.date, amount=body.amount,
                transaction_type=body.type, description=body.description,
                method=body.method, category=body.category,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete(
        "/api/v1/life-finance/transactions/{transaction_id}",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def delete_life_transaction(transaction_id: str) -> dict[str, Any]:
        try:
            return services.delete_life_transaction(transaction_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/life-finance/goals",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def add_life_goal(body: LifeGoalCreateContract) -> dict[str, Any]:
        try:
            return services.add_life_goal(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/api/v1/life-finance/goals/{goal_id}/savings",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def add_life_goal_savings(goal_id: str, body: LifeGoalSavingsContract) -> dict[str, Any]:
        try:
            return services.add_life_goal_savings(goal_id, body.amount)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete(
        "/api/v1/life-finance/goals/{goal_id}",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def delete_life_goal(goal_id: str) -> dict[str, Any]:
        try:
            return services.delete_life_goal(goal_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/logs", dependencies=[Depends(require_token)])
    def logs(service: str = Query(default="blockchain"), source: str = Query(default="all"), lines: int = Query(default=300, ge=10, le=1000)) -> dict[str, Any]:
        try:
            return services.log_snapshot(service=service, source=source, lines=lines)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/audit/export", dependencies=[Depends(require_token)])
    def audit_export() -> dict[str, Any]:
        return services.audit_export()

    @app.post(
        "/api/v1/runtime/commands",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def runtime_command(body: RuntimeCommandContract) -> dict[str, Any]:
        try:
            return services.execute_runtime_command(
                command_id=body.command_id,
                command=body.command,
                payload={
                    "source": body.source, "close_all": body.close_all,
                    "symbol": body.symbol, "live_confirmation": body.live_confirmation,
                },
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/v1/runtime/shutdown",
        dependencies=[Depends(require_token), Depends(require_confirmed_intent)],
    )
    def runtime_shutdown() -> dict[str, Any]:
        try:
            result = services.prepare_shutdown()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not bool(result.get("safe_to_exit")):
            raise HTTPException(status_code=409, detail={
                "code": "runtime_shutdown_incomplete",
                "result": result,
            })
        return result

    @app.get("/api/v1/market/candles", dependencies=[Depends(require_token)])
    def market_candles(
        source: str = Query(default="binance"),
        market_type: str = Query(default="spot"),
        symbol: str = Query(default="BTCUSDT"),
        interval: str = Query(default="1m"),
        limit: int = Query(default=300, ge=10, le=1000),
    ):
        try:
            normalized_source = str(source or "").lower().strip()
            if normalized_source not in MultiSourcePublicMarketData.SOURCES | STOCK_SOURCES:
                raise ValueError("unsupported market source")
            if normalized_source in STOCK_SOURCES:
                if str(market_type or "").lower() != "stock" or str(interval or "").lower() != "1d":
                    raise ValueError("stock charts support market_type=stock and interval=1d only")
                return services.stock_candle_snapshot(
                    source=normalized_source,
                    symbol=symbol,
                    limit=limit,
                )
            getter = getattr(market_provider, "get_candles", None)
            snapshot = (
                getter(normalized_source, market_type, symbol, interval, limit)
                if callable(getter)
                else market_provider.get_spot_candles(symbol, interval, limit)
            )
            marker_getter = getattr(services, "chart_markers", None)
            markers = marker_getter(symbol=symbol, source=normalized_source) if callable(marker_getter) else []
            if isinstance(snapshot, CandleSnapshotContract):
                return snapshot.model_copy(update={"markers": markers})
            return snapshot
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PublicMarketDataError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/v1/market/stock-overview", dependencies=[Depends(require_token)])
    def stock_overview(symbols: str = Query(default="005930,000660,035420,035720,005380,373220")) -> dict[str, Any]:
        try:
            requested = [token.strip() for token in str(symbols or "").split(",") if token.strip()]
            return services.public_stock_snapshot(symbols=requested)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/market/sentiment", dependencies=[Depends(require_token)])
    def market_sentiment(symbol: str = Query(default="BTCUSDT")) -> dict[str, Any]:
        try:
            getter = getattr(market_provider, "get_futures_sentiment", None)
            if not callable(getter):
                raise PublicMarketDataError("binance_public_sentiment_unavailable")
            return getter(symbol)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PublicMarketDataError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.websocket("/api/v1/events")
    async def events(websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin")
        if origin and origin not in ALLOWED_ORIGINS:
            await websocket.close(code=4403, reason="origin_not_allowed")
            return
        await websocket.accept()
        try:
            auth_message = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
            supplied = str(auth_message.get("token") or "") if isinstance(auth_message, dict) else ""
            if not supplied or not hmac.compare_digest(supplied, expected_token):
                await websocket.close(code=4401, reason="authentication_required")
                return

            sequence = 0
            await websocket.send_json(
                EventEnvelope(
                    event_id=str(uuid.uuid4()),
                    sequence=sequence,
                    event_type="gateway.ready",
                    source="local_gateway",
                    payload={"commands_enabled": True, "release_version": RELEASE_VERSION},
                ).model_dump(mode="json")
            )
            while True:
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=15.0)
                except TimeoutError:
                    sequence += 1
                    await websocket.send_json(
                        EventEnvelope(
                            event_id=str(uuid.uuid4()),
                            sequence=sequence,
                            event_type="gateway.heartbeat",
                            source="local_gateway",
                        ).model_dump(mode="json")
                    )
        except (WebSocketDisconnect, asyncio.TimeoutError):
            return

    return app


def _forbidden_response():
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=403, content={"detail": "origin_not_allowed"})
