#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""주문 이벤트와 분리된 포지션 생명주기 KPI 유틸리티."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from api.kpi_client import emit_kpi_event


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: Any) -> Optional[datetime]:
    """datetime/ISO 문자열을 시간대가 포함된 UTC datetime으로 정규화한다.

    기존 클라이언트의 naive datetime은 실행 OS의 로컬 시간으로 생성되었으므로
    시스템 로컬 시간대로 해석한 뒤 UTC로 변환한다.
    """
    parsed: Optional[datetime]
    if isinstance(value, datetime):
        parsed = value
    elif value not in (None, ""):
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    else:
        return None

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.astimezone()
    return parsed.astimezone(timezone.utc)


def elapsed_seconds(opened_at: Any, ended_at: Any) -> Optional[float]:
    opened_utc = as_utc(opened_at)
    ended_utc = as_utc(ended_at)
    if opened_utc is None or ended_utc is None:
        return None
    seconds = (ended_utc - opened_utc).total_seconds()
    if seconds < 0:
        return None
    return seconds


def make_position_id(
    *,
    venue: str,
    symbol: str,
    opened_at: Any,
    entry_order_id: Optional[Any] = None,
) -> Optional[str]:
    opened_utc = as_utc(opened_at)
    if opened_utc is None:
        return None
    identity = "|".join(
        (
            str(venue or "unknown").strip().lower(),
            str(symbol or "").strip().upper(),
            opened_utc.isoformat(),
            str(entry_order_id or ""),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def emit_position_opened(
    *,
    asset_class: str,
    venue: str,
    symbol: str,
    side: str,
    opened_at: Any,
    entry_price: float,
    quantity: float,
    position_id: Optional[str] = None,
    entry_order_id: Optional[Any] = None,
    execution_mode: str = "live",
    source: str = "noahai_client_position",
    extra: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Optional[str]]:
    opened_utc = as_utc(opened_at)
    resolved_id = position_id or make_position_id(
        venue=venue,
        symbol=symbol,
        opened_at=opened_utc,
        entry_order_id=entry_order_id,
    )
    if (
        opened_utc is None
        or not resolved_id
        or float(entry_price or 0.0) <= 0
        or float(quantity or 0.0) <= 0
    ):
        return False, resolved_id

    metadata: Dict[str, Any] = {
        "event_id": f"{resolved_id}:opened",
        "position_id": resolved_id,
        "venue": str(venue or "unknown"),
        "exchange": str(venue or "unknown") if asset_class == "crypto" else None,
        "broker": str(venue or "unknown") if asset_class in {"stock", "etf"} else None,
        "symbol": str(symbol or "").upper(),
        "side": str(side or "").upper(),
        "opened_at": opened_utc.isoformat(),
        "entry_price": float(entry_price),
        "quantity": float(quantity),
        "entry_order_id": str(entry_order_id) if entry_order_id not in (None, "") else None,
        "execution_mode": str(execution_mode or "live"),
    }
    metadata.update(extra or {})
    metadata = {key: value for key, value in metadata.items() if value is not None}
    emitted = emit_kpi_event(
        event_type="trade_position_opened",
        category="trade",
        asset_class=asset_class,
        status="success",
        source=source,
        metric_value=float(quantity),
        metadata=metadata,
    )
    return emitted, resolved_id


def emit_position_closed(
    *,
    asset_class: str,
    venue: str,
    symbol: str,
    side: str,
    opened_at: Any,
    closed_at: Any,
    entry_price: float,
    exit_price: float,
    closed_quantity: float,
    close_reason: str,
    position_id: Optional[str] = None,
    entry_order_id: Optional[Any] = None,
    exit_order_id: Optional[Any] = None,
    execution_mode: str = "live",
    source: str = "noahai_client_position",
    gross_pnl: Optional[float] = None,
    net_pnl: Optional[float] = None,
    fees: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> bool:
    opened_utc = as_utc(opened_at)
    closed_utc = as_utc(closed_at)
    hold_seconds = elapsed_seconds(opened_utc, closed_utc)
    resolved_id = position_id or make_position_id(
        venue=venue,
        symbol=symbol,
        opened_at=opened_utc,
        entry_order_id=entry_order_id,
    )
    if (
        opened_utc is None
        or closed_utc is None
        or hold_seconds is None
        or not resolved_id
        or float(entry_price or 0.0) <= 0
        or float(exit_price or 0.0) <= 0
        or float(closed_quantity or 0.0) <= 0
    ):
        return False

    close_identity = str(exit_order_id or close_reason or "closed")
    metadata: Dict[str, Any] = {
        "event_id": f"{resolved_id}:closed:{close_identity}",
        "position_id": resolved_id,
        "venue": str(venue or "unknown"),
        "exchange": str(venue or "unknown") if asset_class == "crypto" else None,
        "broker": str(venue or "unknown") if asset_class in {"stock", "etf"} else None,
        "symbol": str(symbol or "").upper(),
        "side": str(side or "").upper(),
        "opened_at": opened_utc.isoformat(),
        "closed_at": closed_utc.isoformat(),
        "hold_seconds": round(hold_seconds, 3),
        "entry_price": float(entry_price),
        "exit_price": float(exit_price),
        "closed_quantity": float(closed_quantity),
        "close_reason": str(close_reason or "unknown"),
        "entry_order_id": str(entry_order_id) if entry_order_id not in (None, "") else None,
        "exit_order_id": str(exit_order_id) if exit_order_id not in (None, "") else None,
        "execution_mode": str(execution_mode or "live"),
        "gross_pnl": float(gross_pnl) if gross_pnl is not None else None,
        "net_pnl": float(net_pnl) if net_pnl is not None else None,
        "fees": max(0.0, float(fees)) if fees is not None else None,
    }
    metadata.update(extra or {})
    metadata = {key: value for key, value in metadata.items() if value is not None}
    return emit_kpi_event(
        event_type="trade_position_closed",
        category="trade",
        asset_class=asset_class,
        status="success",
        source=source,
        metric_value=float(closed_quantity),
        metadata=metadata,
    )


def emit_position_reduced(
    *,
    asset_class: str,
    venue: str,
    symbol: str,
    side: str,
    opened_at: Any,
    event_at: Any,
    closed_quantity: float,
    remaining_quantity: float,
    position_id: str,
    exit_order_id: Optional[Any] = None,
    execution_mode: str = "live",
    source: str = "noahai_client_position",
    extra: Optional[Dict[str, Any]] = None,
) -> bool:
    opened_utc = as_utc(opened_at)
    event_utc = as_utc(event_at)
    hold_seconds = elapsed_seconds(opened_utc, event_utc)
    if (
        opened_utc is None
        or event_utc is None
        or hold_seconds is None
        or not position_id
        or float(closed_quantity or 0.0) <= 0
        or float(remaining_quantity or 0.0) < 0
    ):
        return False

    reduce_identity = str(exit_order_id or f"{event_utc.isoformat()}:{closed_quantity}")
    metadata: Dict[str, Any] = {
        "event_id": f"{position_id}:reduced:{reduce_identity}",
        "position_id": position_id,
        "venue": str(venue or "unknown"),
        "exchange": str(venue or "unknown") if asset_class == "crypto" else None,
        "broker": str(venue or "unknown") if asset_class in {"stock", "etf"} else None,
        "symbol": str(symbol or "").upper(),
        "side": str(side or "").upper(),
        "opened_at": opened_utc.isoformat(),
        "event_at": event_utc.isoformat(),
        "hold_seconds": round(hold_seconds, 3),
        "closed_quantity": float(closed_quantity),
        "remaining_quantity": float(remaining_quantity),
        "exit_order_id": str(exit_order_id) if exit_order_id not in (None, "") else None,
        "execution_mode": str(execution_mode or "live"),
    }
    metadata.update(extra or {})
    metadata = {key: value for key, value in metadata.items() if value is not None}
    return emit_kpi_event(
        event_type="trade_position_reduced",
        category="trade",
        asset_class=asset_class,
        status="success",
        source=source,
        metric_value=float(closed_quantity),
        metadata=metadata,
    )
