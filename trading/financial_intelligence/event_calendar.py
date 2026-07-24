from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from .models import FinancialEvent, Provenance, parse_datetime


class EventCalendarEngine:
    IMPORTANCE_LABELS = {1: "정보", 2: "주의", 3: "중요", 4: "매우 중요"}

    def normalize(self, raw: Dict[str, Any], source: str = "user") -> FinancialEvent:
        title = str(raw.get("title") or raw.get("name") or "이름 없는 이벤트").strip()
        starts_at = parse_datetime(raw.get("starts_at") or raw.get("date") or raw.get("timestamp")).isoformat()
        event_type = str(raw.get("event_type") or raw.get("type") or "other").strip().lower()
        fingerprint = f"{source}|{event_type}|{starts_at}|{title}"
        event_id = str(raw.get("event_id") or hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:20])
        importance = max(1, min(int(raw.get("importance", 1) or 1), 4))
        return FinancialEvent(
            event_id=event_id,
            title=title,
            event_type=event_type,
            starts_at=starts_at,
            importance=importance,
            country=str(raw.get("country") or ""),
            symbols=[str(value).upper() for value in (raw.get("symbols") or [])],
            asset_types=[str(value).lower() for value in (raw.get("asset_types") or [])],
            previous=self._float_or_none(raw.get("previous")),
            expected=self._float_or_none(raw.get("expected")),
            actual=self._float_or_none(raw.get("actual")),
            description=str(raw.get("description") or ""),
            provenance=Provenance(
                source=source,
                source_url_or_id=str(raw.get("source_url_or_id") or raw.get("url") or ""),
                as_of=str(raw.get("as_of") or datetime.now(timezone.utc).isoformat()),
                freshness=str(raw.get("freshness") or "scheduled"),
                is_delayed=bool(raw.get("is_delayed", False)),
                quality_flags=list(raw.get("quality_flags") or []),
            ),
        )

    @staticmethod
    def _float_or_none(value: Any) -> Optional[float]:
        try:
            return None if value in (None, "") else float(value)
        except Exception:
            return None

    def list_window(
        self,
        events: Iterable[FinancialEvent | Dict[str, Any]],
        start: datetime,
        end: datetime,
    ) -> List[Dict[str, Any]]:
        start_utc = parse_datetime(start)
        end_utc = parse_datetime(end)
        selected: List[Dict[str, Any]] = []
        for value in events:
            event = value if isinstance(value, FinancialEvent) else self.normalize(value, str(value.get("source") or "user"))
            event_time = parse_datetime(event.starts_at)
            if start_utc <= event_time <= end_utc:
                selected.append(event.to_dict())
        selected.sort(key=lambda item: (item["starts_at"], -int(item["importance"])))
        return selected

    def match_exposures(
        self,
        events: Iterable[FinancialEvent | Dict[str, Any]],
        positions: Iterable[Dict[str, Any]],
        now: Optional[datetime] = None,
        horizon_hours: int = 72,
    ) -> List[Dict[str, Any]]:
        now_utc = parse_datetime(now or datetime.now(timezone.utc))
        end = now_utc + timedelta(hours=max(1, int(horizon_hours)))
        upcoming = self.list_window(events, now_utc, end)
        position_rows = list(positions)
        matched: List[Dict[str, Any]] = []
        macro_types = {"fomc", "cpi", "ppi", "gdp", "employment", "rate_decision", "macro"}
        for event in upcoming:
            event_symbols = {str(symbol).upper() for symbol in event.get("symbols") or []}
            event_assets = {str(asset).lower() for asset in event.get("asset_types") or []}
            related: List[str] = []
            for position in position_rows:
                symbol = str(position.get("symbol") or position.get("code") or "").upper()
                asset_type = str(position.get("asset_type") or "").lower()
                if (
                    symbol in event_symbols
                    or asset_type in event_assets
                    or str(event.get("event_type")) in macro_types
                ):
                    if symbol:
                        related.append(symbol)
            if related or int(event.get("importance", 1)) >= 3:
                matched.append(
                    {
                        **event,
                        "related_positions": sorted(set(related)),
                        "risk_action": self.risk_action(event),
                    }
                )
        return matched

    def risk_action(self, event: FinancialEvent | Dict[str, Any], minutes_to_event: Optional[float] = None) -> Dict[str, Any]:
        payload = event.to_dict() if isinstance(event, FinancialEvent) else event
        importance = int(payload.get("importance", 1) or 1)
        if minutes_to_event is None:
            minutes_to_event = (parse_datetime(payload.get("starts_at")) - datetime.now(timezone.utc)).total_seconds() / 60.0
        if importance >= 4 and -30 <= minutes_to_event <= 120:
            level = "제한 검토"
            multiplier = 0.5
        elif importance >= 3 and -60 <= minutes_to_event <= 360:
            level = "주의"
            multiplier = 0.75
        else:
            level = "정보"
            multiplier = 1.0
        return {
            "level": level,
            "risk_multiplier_suggestion": multiplier,
            "auto_apply": False,
            "reason": f"{self.IMPORTANCE_LABELS.get(importance, '정보')} 이벤트 전후 변동성 가능성",
        }

    def reaction_record(
        self,
        event: FinancialEvent | Dict[str, Any],
        before_price: float,
        after_price: float,
        before_volume: float = 0.0,
        after_volume: float = 0.0,
        slippage_bps: Optional[float] = None,
    ) -> Dict[str, Any]:
        payload = event.to_dict() if isinstance(event, FinancialEvent) else event
        price_return = ((float(after_price) / float(before_price)) - 1.0) * 100.0 if before_price else None
        volume_change = ((float(after_volume) / float(before_volume)) - 1.0) * 100.0 if before_volume else None
        return {
            "event_id": payload.get("event_id"),
            "price_return_percent": price_return,
            "volume_change_percent": volume_change,
            "slippage_bps": slippage_bps,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
