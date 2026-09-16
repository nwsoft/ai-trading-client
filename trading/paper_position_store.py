"""Crash-safe persistence for simulated open positions.

Closed PAPER outcomes are an append-only ledger, but an open simulated
position also has to survive an application/update restart.  This module keeps
that transient state separate from LIVE positions and never calls an exchange.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


_LOCKS: Dict[str, threading.RLock] = {}


def _lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    if key not in _LOCKS:
        _LOCKS[key] = threading.RLock()
    return _LOCKS[key]


def position_store_path(settings: Dict[str, Any] | None, engine: str) -> Path:
    settings = settings if isinstance(settings, dict) else {}
    explicit = settings.get(f"paper_position_store_path_{engine}")
    if explicit:
        return Path(str(explicit)).expanduser()
    from path_utils import get_app_data_dir
    return Path(get_app_data_dir()) / f"paper_open_positions_{engine}.json"


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    enum_value = getattr(value, "value", None)
    return _json_safe(enum_value if enum_value is not None else str(value))


def serialize_position(position: Any) -> Dict[str, Any]:
    fields = (
        "symbol", "side", "entry_price", "current_price", "quantity", "leverage",
        "unrealized_pnl", "unrealized_pnl_percent", "entry_time", "tp_price", "sl_price",
        "position_id", "entry_order_id", "entry_order_ids", "entry_time_source",
        "execution_mode", "position_owner", "custom_strategy_id", "custom_strategy_name",
        "custom_strategy_rules", "custom_strategy_key", "custom_strategy_version_id",
        "custom_strategy_scope", "exit_policy", "entry_evidence", "custom_order_plan_state",
        "spot_baseline_quantity",
    )
    return {name: _json_safe(getattr(position, name, None)) for name in fields}


def _parse_datetime(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def deserialize_position(row: Dict[str, Any], position_cls: Any, side_cls: Any) -> Any:
    if str(row.get("execution_mode") or "").lower() != "paper":
        raise ValueError("non_paper_position_rejected")
    symbol = str(row.get("symbol") or "").strip()
    entry_price = float(row.get("entry_price") or 0.0)
    quantity = float(row.get("quantity") or 0.0)
    if not symbol or entry_price <= 0 or quantity <= 0:
        raise ValueError("invalid_paper_position_identity")
    side = side_cls(str(getattr(row.get("side"), "value", row.get("side")) or "").upper())
    return position_cls(
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        current_price=float(row.get("current_price") or entry_price),
        quantity=quantity,
        leverage=max(1, int(row.get("leverage") or 1)),
        unrealized_pnl=float(row.get("unrealized_pnl") or 0.0),
        unrealized_pnl_percent=float(row.get("unrealized_pnl_percent") or 0.0),
        entry_time=_parse_datetime(row.get("entry_time")),
        tp_price=None if row.get("tp_price") is None else float(row.get("tp_price")),
        sl_price=None if row.get("sl_price") is None else float(row.get("sl_price")),
        position_id=str(row.get("position_id") or "") or None,
        entry_order_id=str(row.get("entry_order_id") or "") or None,
        entry_order_ids=[str(item) for item in list(row.get("entry_order_ids") or []) if item],
        entry_time_source=str(row.get("entry_time_source") or "execution"),
        execution_mode="paper",
        position_owner=str(row.get("position_owner") or "legacy_unknown"),
        custom_strategy_id=str(row.get("custom_strategy_id") or "") or None,
        custom_strategy_name=str(row.get("custom_strategy_name") or "") or None,
        custom_strategy_rules=dict(row.get("custom_strategy_rules") or {}),
        custom_strategy_key=str(row.get("custom_strategy_key") or "") or None,
        custom_strategy_version_id=str(row.get("custom_strategy_version_id") or "") or None,
        custom_strategy_scope=str(row.get("custom_strategy_scope") or "") or None,
        exit_policy=dict(row.get("exit_policy") or {}),
        entry_evidence=dict(row.get("entry_evidence") or {}),
        custom_order_plan_state=dict(row.get("custom_order_plan_state") or {}),
        spot_baseline_quantity=float(row.get("spot_baseline_quantity") or 0.0),
    )


def save_positions(path: Path, stores: Dict[str, Dict[str, Any]]) -> None:
    payload = {
        "schema_version": 1,
        "execution_mode": "paper",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "venues": {
            str(venue).lower(): {
                str(symbol): serialize_position(position)
                for symbol, position in dict(positions or {}).items()
            }
            for venue, positions in dict(stores or {}).items()
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with _lock(path):
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        temp.replace(path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def load_positions(path: Path, position_cls: Any, side_cls: Any) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    with _lock(path):
        payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("schema_version") or 0) != 1 or payload.get("execution_mode") != "paper":
        raise ValueError("unsupported_paper_position_store")
    restored: Dict[str, Dict[str, Any]] = {}
    for venue, positions in dict(payload.get("venues") or {}).items():
        venue_positions: Dict[str, Any] = {}
        for symbol, row in dict(positions or {}).items():
            try:
                position = deserialize_position(dict(row or {}), position_cls, side_cls)
            except (TypeError, ValueError, KeyError):
                continue
            venue_positions[str(symbol)] = position
        restored[str(venue).lower()] = venue_positions
    return restored
