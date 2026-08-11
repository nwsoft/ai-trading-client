"""NoahAI-managed position ownership and reconciliation helpers.

Exchange balances/positions describe the whole user account.  They are never
proof that NoahAI created a position.  Only a locally persisted NoahAI entry
order may authorize automatic monitoring or closing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


NOAH_POSITION_OWNER = "noahai"


def normalize_position_symbol(symbol: Any) -> str:
    value = str(symbol or "").strip().upper()
    # CCXT derivatives may append settlement currency (BTC/USDT:USDT).
    value = value.split(":", 1)[0]
    # Domestic REST APIs sometimes use quote-first KRW-BTC while CCXT and the
    # local ledger use BTC/KRW. Canonicalize both to BTCKRW.
    for separator in ("-", "_"):
        parts = value.split(separator)
        if len(parts) == 2 and parts[0] in {"KRW", "USDT", "USDC"}:
            value = f"{parts[1]}/{parts[0]}"
            break
    return value.replace("/", "").replace("-", "").replace("_", "")


def is_noah_managed_position(position: Any) -> bool:
    """Return True only when a position carries NoahAI entry provenance."""
    owner = str(getattr(position, "position_owner", "") or "").strip().lower()
    if owner == NOAH_POSITION_OWNER:
        return True
    entry_order_id = str(getattr(position, "entry_order_id", "") or "").strip()
    entry_source = str(getattr(position, "entry_time_source", "") or "").strip().lower()
    return bool(entry_order_id and entry_source == "execution")


def parse_entry_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def managed_trade_map(rows: list[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Aggregate persisted NoahAI scale-ins by normalized symbol.

    A former restart bug could create more than one open entry row for the same
    spot symbol.  All rows are Noah-owned, so recovery must manage their summed
    quantity instead of silently keeping only the newest row.
    """
    result: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        key = normalize_position_symbol(row.get("symbol"))
        if not key:
            continue
        order_id = str(row.get("order_id") or "").strip()
        quantity = max(0.0, float(row.get("quantity") or 0.0))
        entry_price = max(0.0, float(row.get("entry_price") or 0.0))
        if key not in result:
            item = dict(row)
            item["_entry_order_ids"] = [order_id] if order_id else []
            result[key] = item
            continue
        item = result[key]
        prior_quantity = max(0.0, float(item.get("quantity") or 0.0))
        total_quantity = prior_quantity + quantity
        if total_quantity > 0:
            item["entry_price"] = (
                (float(item.get("entry_price") or 0.0) * prior_quantity)
                + (entry_price * quantity)
            ) / total_quantity
        item["quantity"] = total_quantity
        if order_id and order_id not in item["_entry_order_ids"]:
            item["_entry_order_ids"].append(order_id)
        item["entry_time"] = min(
            parse_entry_time(item.get("entry_time")),
            parse_entry_time(row.get("entry_time")),
        ).isoformat()
        item["spot_baseline_quantity"] = min(
            float(item.get("spot_baseline_quantity") or 0.0),
            float(row.get("spot_baseline_quantity") or 0.0),
        )
    return result
