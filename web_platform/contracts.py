"""Versioned, UI-neutral contracts for the parallel Web UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CONTRACT_SCHEMA_VERSION = "1.0.0"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthContract(StrictContract):
    status: Literal["ok"] = "ok"
    service: Literal["noahai-local-gateway"] = "noahai-local-gateway"
    release_version: str
    schema_version: str = CONTRACT_SCHEMA_VERSION
    mode: Literal["internal_migration_candidate"] = "internal_migration_candidate"
    timestamp: datetime = Field(default_factory=utc_now)


class PlatformContract(StrictContract):
    product: Literal["NoahAI Client"] = "NoahAI Client"
    release_version: str
    release_label: str
    schema_version: str = CONTRACT_SCHEMA_VERSION
    ui_platform: Literal["web_electron"] = "web_electron"
    legacy_ui: Literal["not_packaged"] = "not_packaged"
    gateway_mode: Literal["account_scoped"] = "account_scoped"
    commands_enabled: bool = True


class RuntimeSnapshotContract(StrictContract):
    snapshot_version: int = 1
    status: Literal["detached", "ready", "partial", "stale", "error"] = "detached"
    service: str | None = None
    selected_source: str | None = None
    selected_sources: dict[str, str] = Field(default_factory=dict)
    enabled_sources: list[str] = Field(default_factory=list)
    running_sources: list[str] = Field(default_factory=list)
    enabled_sources_by_service: dict[str, list[str]] = Field(default_factory=dict)
    running_sources_by_service: dict[str, list[str]] = Field(default_factory=dict)
    credential_status: dict[str, bool] = Field(default_factory=dict)
    configured_sources_by_service: dict[str, list[str]] = Field(default_factory=dict)
    execution_modes: dict[str, Literal["learning", "paper", "live"]] = Field(default_factory=dict)
    paper_trading: bool | None = None
    live_trading: bool | None = None
    captured_at: datetime = Field(default_factory=utc_now)
    reason: str = "headless_runtime_not_attached"


class CandleContract(StrictContract):
    source: str
    market_type: Literal["spot", "futures", "stock"]
    symbol: str
    interval: str
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    closed: bool
    sequence: int


class CandleSnapshotContract(StrictContract):
    schema_version: str = CONTRACT_SCHEMA_VERSION
    source: str
    symbol: str
    interval: str
    candles: list[CandleContract]
    markers: list[dict[str, Any]] = Field(default_factory=list)
    captured_at: datetime = Field(default_factory=utc_now)


class EventEnvelope(StrictContract):
    schema_version: str = CONTRACT_SCHEMA_VERSION
    event_id: str
    sequence: int = Field(ge=0)
    event_type: str
    occurred_at: datetime = Field(default_factory=utc_now)
    source: str
    account_scope: str = "none"
    payload: dict[str, Any] = Field(default_factory=dict)


class SettingsUpdateContract(StrictContract):
    expected_revision: str = Field(min_length=64, max_length=64)
    changes: dict[str, Any] = Field(min_length=1, max_length=500)


class CredentialUpdateContract(StrictContract):
    expected_revision: str = Field(min_length=64, max_length=64)
    provider: str = Field(min_length=2, max_length=32)
    values: dict[str, str] = Field(min_length=1, max_length=8)


class NotificationChannelContract(StrictContract):
    channel: Literal["discord", "telegram"]


class NotificationReportContract(StrictContract):
    title: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=3200)
    source: str = Field(default="", max_length=32)


class NotificationUpdateContract(StrictContract):
    version: str = Field(min_length=1, max_length=64)
    current_version: str = Field(default="", max_length=64)


class AIProviderDiagnosticContract(StrictContract):
    provider: Literal["openai", "deepseek", "kimi", "anthropic", "gemini"]
    model: str = Field(default="", max_length=160)
    capability: Literal["chat_text", "chat_json", "vision", "transcribe"] = "chat_text"


class ChartImageAnalysisContract(StrictContract):
    file_name: str = Field(min_length=1, max_length=255)
    image_data_url: str = Field(min_length=32, max_length=12_000_000)
    service: Literal["blockchain", "stock", "portfolio", "ai_analyst"] = "blockchain"


class SettingsRestoreContract(StrictContract):
    expected_revision: str = Field(min_length=64, max_length=64)
    backup_name: str = Field(pattern=r"^settings_[0-9]{8}_[0-9]{6}_[0-9]{6}\.json$", min_length=36, max_length=64)


class StrategyDeleteContract(StrictContract):
    scope: Literal["binance", "unified"]
    strategy_key: str = Field(min_length=1, max_length=160)
    version_id: str | None = Field(default=None, max_length=200)


class StrategySubmitContract(StrictContract):
    scope: Literal["binance", "unified"]
    name: str = Field(min_length=1, max_length=160)
    rules: dict[str, Any]
    source_kind: Literal["text", "pine", "document", "image", "video", "url", "manual"] = "manual"
    source_reference: str = Field(default="", max_length=2048)
    strategy_key: str | None = Field(default=None, max_length=160)


class StrategyActionContract(StrictContract):
    scope: Literal["binance", "unified"]
    strategy_key: str = Field(min_length=1, max_length=160)
    version_id: str = Field(min_length=1, max_length=200)
    action: Literal["approve", "start_paper", "stop_paper", "restart_paper", "activate", "deactivate", "rollback"]
    live_confirmation: bool = False
    operation_mode: Literal["standard", "limited_live"] = "standard"


class StrategyPaperValidationContract(StrictContract):
    scope: Literal["binance", "unified"]
    strategy_key: str = Field(min_length=1, max_length=160)
    version_id: str = Field(min_length=1, max_length=200)
    trades: int = Field(ge=0, le=1_000_000)
    guardrail_violations: int = Field(default=0, ge=0, le=1_000_000)
    metrics: dict[str, Any] = Field(default_factory=dict)


class StrategyHistoricalValidationContract(StrictContract):
    scope: Literal["binance", "unified"]
    strategy_key: str = Field(min_length=1, max_length=160)
    version_id: str = Field(min_length=1, max_length=200)
    asset_class: Literal["crypto", "stock"] = "crypto"
    source: str = Field(default="", max_length=40)
    market_type: Literal["spot", "futures"] | None = None
    symbol: str = Field(default="BTCUSDT", min_length=3, max_length=24)
    limit: int = Field(default=500, ge=100, le=1000)


class StrategySourceAnalyzeContract(StrictContract):
    source_kind: Literal["auto", "text", "pine", "pdf", "image", "video", "youtube", "tradingview", "url"] = "auto"
    value: str = Field(min_length=1, max_length=40_000_000)
    encoding: Literal["text", "base64"] = "text"
    file_name: str = Field(default="", max_length=255)
    supplemental_text: str = Field(default="", max_length=20_000)
    authoring_mode: Literal["source_faithful", "guided_clarification", "noah_delegate"] = "source_faithful"


class StrategyDraftValidationContract(StrictContract):
    rules: dict[str, Any]
    compiler_issues: list[str] = Field(default_factory=list, max_length=100)


class StrategyMentorContract(StrictContract):
    profile: dict[str, Any] = Field(default_factory=dict)


class StrategyPackageImportContract(StrictContract):
    scope: Literal["binance", "unified"]
    file_name: str = Field(default="imported.noahstrategy", max_length=255)
    package: dict[str, Any]


class LifeTransactionCreateContract(StrictContract):
    date: str
    amount: float = Field(gt=0, le=1_000_000_000_000)
    type: Literal["수입", "지출"]
    description: str = Field(min_length=1, max_length=500)
    method: str = Field(default="기타", max_length=100)
    category: str | None = Field(default=None, max_length=100)


class LifeGoalCreateContract(StrictContract):
    name: str = Field(min_length=1, max_length=160)
    target_amount: float = Field(gt=0, le=1_000_000_000_000)
    deadline: str | None = None
    category: str = Field(default="기타", max_length=100)
    priority: Literal["높음", "중간", "낮음"] = "중간"
    description: str = Field(default="", max_length=500)


class LifeGoalSavingsContract(StrictContract):
    amount: float = Field(gt=0, le=1_000_000_000_000)


class SessionLoginContract(StrictContract):
    username: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=1, max_length=512)


class AssistantTurnContract(StrictContract):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AssistantQueryContract(StrictContract):
    question: str = Field(min_length=2, max_length=4000)
    service: Literal["blockchain", "stock", "portfolio", "personal_finance", "ai_analyst", "settings", "ai_custom"] = "ai_custom"
    explanation_level: Literal["beginner", "standard", "advanced"] = "standard"
    mode: Literal["guide", "deep_analysis"] = "guide"
    recent_messages: list[AssistantTurnContract] = Field(default_factory=list, max_length=12)
    settings_section: Literal[
        "general", "exchange_selection", "exchange_api", "ai_engine", "notifications",
        "advanced", "alpha", "system", "update",
    ] | None = None
    data_scope: Literal["private", "public_general"] = "private"


class RuntimeCommandContract(StrictContract):
    command_id: str = Field(min_length=16, max_length=80)
    command: Literal["trading.start", "trading.stop", "coins.select", "coins.analyze", "stocks.analyze", "trades.import"]
    source: str = Field(min_length=2, max_length=32)
    close_all: bool = False
    symbol: str = Field(default="", max_length=32)
    live_confirmation: bool = False


class StockSearchProfileActionContract(StrictContract):
    action: Literal["recent_add", "favorite_toggle", "watchlist_add"]
    symbol: str = Field(pattern=r"^[0-9]{5,8}$")


class AccountSnapshotRequestContract(StrictContract):
    sources: list[Literal[
        "binance", "upbit", "bithumb", "coinone", "bybit", "okx", "bitget",
        "kiwoom", "shinhan", "mirae", "kis",
    ]] = Field(min_length=1, max_length=11)
    force_refresh: bool = False


class StatisticsViewBaselineContract(StrictContract):
    service: Literal["blockchain", "stock"]
    source: str = Field(default="", max_length=40)
    action: Literal["set", "clear"]


class FinancialMarketUniverseItem(StrictContract):
    symbol: str = Field(min_length=1, max_length=32)
    asset_type: Literal["crypto", "stock", "etf", "index"]
    held: bool = False
    watched: bool = True
    market_cap: float | None = Field(default=None, ge=0)
    points: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)


class FinancialMarketRefreshContract(StrictContract):
    service: Literal["blockchain", "stock", "ai_analyst"]
    universe: list[FinancialMarketUniverseItem] = Field(default_factory=list, max_length=20)
    use_network: bool = False


class FinancialIntelligenceActionContract(StrictContract):
    service: Literal["blockchain", "stock", "ai_analyst"]
    action: Literal[
        "market", "events", "narrative", "macro", "fundamental", "valuation",
        "screener", "technical", "backtest", "institutional", "performance",
    ]
    payload: dict[str, Any] = Field(default_factory=dict, max_length=30)


class FinanceProductCompareContract(StrictContract):
    product_type: Literal["loan", "insurance", "savings"]
    amount: float = Field(gt=0, le=10_000_000_000)
    term_months: int = Field(default=12, ge=1, le=600)
    category: str | None = Field(default=None, max_length=80)
    credit_score: Literal["좋음 (750~900)", "보통 (650~750)", "낮음 (~650)"] = "보통 (650~750)"


class TaxCalculationContract(StrictContract):
    calculation: Literal["year_end", "financial_income", "investment", "saving_accounts", "optimization"]
    annual_salary: float = Field(default=0, ge=0, le=10_000_000_000)
    credit_card: float = Field(default=0, ge=0, le=10_000_000_000)
    debit_cash: float = Field(default=0, ge=0, le=10_000_000_000)
    medical_expense: float = Field(default=0, ge=0, le=10_000_000_000)
    education_expense: float = Field(default=0, ge=0, le=10_000_000_000)
    donation: float = Field(default=0, ge=0, le=10_000_000_000)
    pension_savings: float = Field(default=0, ge=0, le=10_000_000_000)
    irp_contribution: float = Field(default=0, ge=0, le=10_000_000_000)
    personal_deduction_count: int = Field(default=1, ge=0, le=50)
    interest_income: float = Field(default=0, ge=0, le=10_000_000_000)
    dividend_income: float = Field(default=0, ge=0, le=10_000_000_000)
    domestic_stock_profit: float = Field(default=0, ge=0, le=100_000_000_000)
    overseas_stock_profit: float = Field(default=0, ge=0, le=100_000_000_000)
    etf_profit: float = Field(default=0, ge=0, le=100_000_000_000)
    other_profit: float = Field(default=0, ge=0, le=100_000_000_000)
    annual_investment: float = Field(default=0, ge=0, le=10_000_000_000)
    investment_years: int = Field(default=5, ge=1, le=100)
    expected_return_rate: float = Field(default=0.05, ge=0, le=1)
    isa_type: Literal["general", "preferential"] = "general"


class AlphaArenaCommandContract(StrictContract):
    command_id: str = Field(min_length=16, max_length=80)
    action: Literal["start", "stop"]
    live_confirmation: bool = False
