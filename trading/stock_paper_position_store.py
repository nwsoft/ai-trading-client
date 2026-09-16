"""Crash-safe, account-scoped persistence for stock/ETF PAPER positions.

The stock PAPER engine keeps plain dictionaries rather than LIVE broker
position objects.  Persist only simulated LONG positions and reject malformed
or non-PAPER rows when restoring after an application/update restart.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from trading.paper_position_store import position_store_path


_LOCKS: dict[str, threading.RLock] = {}


def _lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    if key not in _LOCKS:
        _LOCKS[key] = threading.RLock()
    return _LOCKS[key]


def stock_position_store_path(settings: Mapping[str, Any] | None = None) -> Path:
    return position_store_path(dict(settings or {}), "stock")


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def save_stock_paper_positions(
    settings: Mapping[str, Any] | None,
    stores: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> None:
    path = stock_position_store_path(settings)
    payload = {
        "schema_version": 1,
        "execution_mode": "paper",
        "asset_scope": "domestic_stock_etf",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "brokers": {
            str(broker).lower(): {
                str(symbol).upper(): _json_safe(dict(position))
                for symbol, position in dict(positions or {}).items()
            }
            for broker, positions in dict(stores or {}).items()
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


def load_stock_paper_positions(
    settings: Mapping[str, Any] | None,
) -> dict[str, dict[str, dict[str, Any]]]:
    path = stock_position_store_path(settings)
    if not path.exists():
        return {}
    with _lock(path):
        payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        int(payload.get("schema_version") or 0) != 1
        or payload.get("execution_mode") != "paper"
        or payload.get("asset_scope") != "domestic_stock_etf"
    ):
        raise ValueError("unsupported_stock_paper_position_store")
    restored: dict[str, dict[str, dict[str, Any]]] = {}
    for broker, positions in dict(payload.get("brokers") or {}).items():
        broker_positions: dict[str, dict[str, Any]] = {}
        for symbol, raw in dict(positions or {}).items():
            row = dict(raw or {})
            normalized_symbol = str(row.get("symbol") or symbol or "").strip().upper()
            try:
                quantity = float(row.get("quantity") or 0.0)
                entry_price = float(row.get("entry_price") or 0.0)
            except (TypeError, ValueError):
                continue
            if (
                not normalized_symbol
                or quantity <= 0.0
                or entry_price <= 0.0
                or str(row.get("execution_mode") or "").lower() != "paper"
                or str(row.get("side") or "").upper() != "LONG"
                or str(row.get("quote_currency") or "").upper() != "KRW"
            ):
                continue
            row["symbol"] = normalized_symbol
            row["code"] = normalized_symbol
            row["quantity"] = quantity
            row["entry_price"] = entry_price
            broker_positions[normalized_symbol] = row
        restored[str(broker).lower()] = broker_positions
    return restored
