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
    mode: Literal["read_only_parallel"] = "read_only_parallel"
    timestamp: datetime = Field(default_factory=utc_now)


class PlatformContract(StrictContract):
    product: Literal["NoahAI Client"] = "NoahAI Client"
    release_version: str
    release_label: str
    schema_version: str = CONTRACT_SCHEMA_VERSION
    ui_platform: Literal["web_parallel"] = "web_parallel"
    legacy_ui: Literal["customtkinter_active"] = "customtkinter_active"
    gateway_mode: Literal["read_only"] = "read_only"
    commands_enabled: bool = False


class RuntimeSnapshotContract(StrictContract):
    snapshot_version: int = 1
    status: Literal["detached", "ready", "partial", "stale", "error"] = "detached"
    service: str | None = None
    selected_source: str | None = None
    enabled_sources: list[str] = Field(default_factory=list)
    running_sources: list[str] = Field(default_factory=list)
    paper_trading: bool | None = None
    live_trading: bool | None = None
    captured_at: datetime = Field(default_factory=utc_now)
    reason: str = "legacy_runtime_not_attached"


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
