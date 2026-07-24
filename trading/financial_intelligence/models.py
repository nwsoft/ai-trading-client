from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
    else:
        text = str(value or "").strip()
        if not text:
            return datetime.now(timezone.utc)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class Provenance:
    source: str
    as_of: str = field(default_factory=utc_now_iso)
    source_url_or_id: str = ""
    currency: str = ""
    timezone: str = "UTC"
    freshness: str = "unknown"
    is_delayed: bool = False
    quality_flags: List[str] = field(default_factory=list)
    calculation_version: str = "fi-1"
    model_version: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MarketPoint:
    symbol: str
    asset_type: str
    price: float
    timestamp: str
    volume: float = 0.0
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    provenance: Provenance = field(default_factory=lambda: Provenance(source="unknown"))

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["provenance"] = self.provenance.to_dict()
        return payload


@dataclass
class FinancialEvent:
    event_id: str
    title: str
    event_type: str
    starts_at: str
    importance: int = 1
    country: str = ""
    symbols: List[str] = field(default_factory=list)
    asset_types: List[str] = field(default_factory=list)
    previous: Optional[float] = None
    expected: Optional[float] = None
    actual: Optional[float] = None
    description: str = ""
    provenance: Provenance = field(default_factory=lambda: Provenance(source="unknown"))

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["provenance"] = self.provenance.to_dict()
        return payload


@dataclass
class NewsItem:
    news_id: str
    title: str
    published_at: str
    source: str
    url: str = ""
    summary: str = ""
    entities: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    novelty_score: float = 0.0
    source_score: float = 0.5
    impact_score: float = 0.0
    fact_claim: str = "unknown"
    quality_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
