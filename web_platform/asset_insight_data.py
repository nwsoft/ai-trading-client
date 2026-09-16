"""UI-neutral trade-history normalization used by the Web platform.

This module deliberately lives outside ``ui``.  The Web engine sidecar must be
able to load account data without importing Tk/CustomTkinter or a legacy
dashboard package.
"""

from __future__ import annotations

import os
import math
import sqlite3
from pathlib import Path
from contextlib import closing
from typing import Any

from trading.exchanges.venue_capabilities import CRYPTO_VENUES, STOCK_VENUES


CRYPTO_EXCHANGES = set(CRYPTO_VENUES)
STOCK_EXCHANGES = set(STOCK_VENUES) | {
    "kiwoom", "shinhan", "miraasset", "miraeasset", "mirae_asset",
    "koreainvestment", "korea_investment", "korea-investment", "kis",
}

CONFIRMED_TRADE_STATUSES = {
    "exchange_confirmed", "exchange_confirmed_partial", "broker_order_linked",
    "exact_fill_price_no_provider_pnl",
}


def load_live_history_evidence(db_path, *, asset_class=None, currency="", limit=100):
    """Read-only inventory, NOT a repair or a substitute for confirmed performance.

    Count the entire stored history before limiting detail rows. Keep imports and
    external trades in separate buckets: they may overlap strategy records.
    Never infer a net result from legacy ``pnl`` or turn a missing value into zero.
    """
    result = {"status": "unavailable", "error": "", "total_count": 0,
              "confirmed_count": 0, "reference_count": 0, "groups": [],
              "recent_records": [], "available_currencies": [],
              "first_exit_time": "", "last_exit_time": "", "detail_limit": limit}
    if not db_path or not os.path.isfile(db_path):
        result["error"] = "database_missing"
        return result
    try:
        with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            columns = _table_columns(connection, "trade_log")
            if not {"symbol", "exit_time", "pnl"}.issubset(columns):
                result["error"] = "trade_log_schema_missing"
                return result
            fields = [name for name in (
                "symbol", "exchange", "asset_type", "execution_mode", "position_owner",
                "reason", "pnl", "net_pnl", "reconciliation_status", "settlement_currency",
                "exit_time",
            ) if name in columns]
            groups = {}
            currencies = set()
            for raw in connection.execute(
                f"SELECT {', '.join(fields)} FROM trade_log "
                "WHERE exit_time IS NOT NULL AND TRIM(exit_time) != '' ORDER BY exit_time DESC"
            ):
                row = dict(raw)
                mode = str(row.get("execution_mode") or "live").strip().lower() or "live"
                if mode not in {"live", "live_api", "optimized", "manual"}:
                    continue
                family = _classify_trade(row["symbol"], row.get("exchange"), row.get("asset_type"))
                if asset_class and family != asset_class:
                    continue
                unit = str(row.get("settlement_currency") or "").strip().upper()
                if not unit:
                    # Old overseas stock records do not prove KRW settlement.
                    unit = ("UNKNOWN" if family == "other" or
                            (family == "stock" and not (str(row["symbol"]).isdigit() and len(str(row["symbol"])) == 6))
                            else _trade_currency(row["symbol"], row.get("exchange"), family))
                currencies.add(unit)
                if currency and unit != currency.upper():
                    continue
                status = str(row.get("reconciliation_status") or "legacy_unverified")
                owner = str(row.get("position_owner") or "legacy_unknown").lower()
                def finite(value):
                    try:
                        number = float(value)
                        return number if math.isfinite(number) else None
                    except (TypeError, ValueError, OverflowError):
                        return None
                saved = finite(row.get("pnl"))
                net = finite(row.get("net_pnl"))
                if str(row.get("reason") or "").lower() == "binance_import":
                    category = "imported"
                elif owner in {"manual", "external"}:
                    category = "external"
                elif status in CONFIRMED_TRADE_STATUSES and net is not None:
                    category = "confirmed"
                else:
                    category = "unreconciled"
                result["total_count"] += 1
                result["confirmed_count" if category == "confirmed" else "reference_count"] += 1
                timestamp = str(row["exit_time"])
                result["first_exit_time"] = timestamp
                if not result["last_exit_time"]:
                    result["last_exit_time"] = timestamp
                key = (category, unit)
                group = groups.setdefault(key, {"category": category, "currency": unit,
                    "count": 0, "stored_pnl_count": 0, "missing_pnl_count": 0, "stored_pnl_sum": None})
                group["count"] += 1
                if saved is None:
                    group["missing_pnl_count"] += 1
                else:
                    group["stored_pnl_count"] += 1
                    group["stored_pnl_sum"] = (group["stored_pnl_sum"] or 0.0) + saved
                if category != "confirmed" and len(result["recent_records"]) < max(0, limit):
                    result["recent_records"].append({"symbol": row["symbol"],
                        "exchange": row.get("exchange") or "unknown", "asset_class": family,
                        "currency": unit, "stored_pnl": saved, "category": category,
                        "reconciliation_status": status, "exit_time": timestamp})
            result.update(status="available", groups=list(groups.values()), available_currencies=sorted(currencies))
    except sqlite3.Error:
        # Do not leak local paths/account metadata through a database exception.
        result["error"] = "history_read_failed"
    return result


def _normalize_venue(value: Any) -> str:
    venue = str(value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    return {
        "miraeasset": "mirae",
        "koreainvestment": "kis",
    }.get(venue, venue)


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1]).lower()
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        if len(row) > 1
    }


def _classify_trade(symbol: Any, exchange: Any, asset_type: Any) -> str:
    explicit = str(asset_type or "").strip().lower()
    if explicit in {"crypto", "stock"}:
        return explicit
    venue = str(exchange or "").strip().lower().replace(" ", "")
    if venue in STOCK_EXCHANGES:
        return "stock"
    if venue in CRYPTO_EXCHANGES:
        return "crypto"
    symbol_key = str(symbol or "").strip().upper().replace("/", "").replace("-", "")
    if symbol_key.endswith(("USDT", "USDC", "BTC", "KRW")):
        return "crypto"
    if symbol_key.isdigit() and len(symbol_key) == 6:
        return "stock"
    return "other"


def _trade_currency(symbol: Any, exchange: Any, asset_class: str) -> str:
    if asset_class == "stock":
        return "KRW"
    venue = str(exchange or "").strip().lower()
    symbol_key = str(symbol or "").strip().upper()
    return "KRW" if venue in {"upbit", "bithumb", "coinone"} or symbol_key.startswith("KRW-") else "USDT"


def load_paper_trade_records(data_dir, *, asset_class=None, limit=5000):
    """Use valid virtual closes only; never reinterpret them as LIVE fills."""
    from pathlib import Path
    from trading.paper_strategy_ledger import read_paper_strategy_outcomes
    from trading.paper_strategy_ledger import normalize_paper_outcome_costs, paper_outcome_calculation_status
    rows = read_paper_strategy_outcomes(path=Path(data_dir) / "strategy_paper_outcomes.jsonl", limit=100_000)
    output = []
    for raw in rows:
        row = normalize_paper_outcome_costs(raw)
        venue = _normalize_venue(row.get("exchange"))
        if venue not in STOCK_EXCHANGES | CRYPTO_EXCHANGES:
            continue
        if not row.get("closed_at"):
            continue
        family = "stock" if venue in STOCK_EXCHANGES else "crypto"
        if asset_class and asset_class != family:
            continue
        if paper_outcome_calculation_status(row) != "valid":
            continue
        output.append({**row, "asset_class": family, "exchange": venue,
                       "currency": row.get("quote_currency") or _trade_currency(row.get("symbol"), venue, family),
                       "pnl": _number(row.get("net_pnl")), "exit_time": row.get("closed_at"),
                       "entry_time": row.get("opened_at"), "execution_mode": "paper"})
    output.sort(key=lambda row: str(row.get("exit_time") or ""), reverse=True)
    return {"records": output[:limit], "schema_compatible": True, "error": "", "execution_mode": "paper"}


def load_closed_trade_records(
    db_path: str,
    *,
    asset_class: str | None = None,
    source: str | None = None,
    limit: int | None = None,
    confirmed_only: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {"records": [], "schema_compatible": False, "error": ""}
    if not db_path or not os.path.exists(db_path):
        result["error"] = "database_missing"
        return result
    try:
        with closing(sqlite3.connect(db_path)) as connection:
            columns = _table_columns(connection, "trade_log")
            if not {"symbol", "pnl", "entry_time", "exit_time"}.issubset(columns):
                result["error"] = "trade_log_schema_missing"
                return result
            asset_expression = "asset_type" if "asset_type" in columns else "NULL"
            exchange_expression = "exchange" if "exchange" in columns else "NULL"
            side_expression = "side" if "side" in columns else "NULL"
            pnl_percent_expression = "pnl_percent" if "pnl_percent" in columns else "0"
            fees_expression = "fees" if "fees" in columns else "0"
            entry_price_expression = "entry_price" if "entry_price" in columns else "0"
            exit_price_expression = "exit_price" if "exit_price" in columns else "0"
            quantity_expression = "quantity" if "quantity" in columns else "0"
            if "entry_amount" in columns:
                notional_expression = "COALESCE(entry_amount, 0)"
            elif {"entry_price", "quantity"}.issubset(columns):
                notional_expression = "ABS(COALESCE(entry_price, 0) * COALESCE(quantity, 0))"
            elif "amount" in columns:
                notional_expression = "ABS(COALESCE(amount, 0))"
            else:
                notional_expression = "0"
            requested = str(asset_class or "").strip().lower()
            requested_source = _normalize_venue(source)
            where_parts = ["exit_time IS NOT NULL"]
            params: list[Any] = []
            pnl_expression = "COALESCE(pnl, 0)"
            if confirmed_only:
                if "reconciliation_status" not in columns or "net_pnl" not in columns:
                    return {"records": [], "schema_compatible": True, "error": "reconciliation_evidence_missing"}
                where_parts.append("reconciliation_status IN ('exchange_confirmed', 'exchange_confirmed_partial', 'broker_order_linked', 'exact_fill_price_no_provider_pnl')")
                where_parts.append("net_pnl IS NOT NULL")
                pnl_expression = "net_pnl"
                if "position_owner" in columns:
                    where_parts.append("LOWER(COALESCE(position_owner, 'legacy_unknown')) NOT IN ('manual', 'external')")
            if "execution_mode" in columns:
                # v3.9.1.22 and older Binance LIVE rows may carry the strategy
                # style in this column. Preserve those two legacy aliases, but
                # never mix PAPER/LEARNING records into LIVE insight cards.
                where_parts.append(
                    "LOWER(TRIM(COALESCE(NULLIF(execution_mode, ''), 'live'))) "
                    "IN ('live', 'live_api', 'optimized', 'manual')"
                )
            if "reason" in columns:
                where_parts.append("LOWER(COALESCE(reason, '')) != 'binance_import'")
            if requested_source and "exchange" in columns:
                where_parts.append(
                    "LOWER(REPLACE(REPLACE(REPLACE(COALESCE(exchange, ''), '_', ''), '-', ''), ' ', '')) = ?"
                )
                params.append(requested_source)
            if requested and "asset_type" in columns:
                where_parts.append("LOWER(COALESCE(asset_type, '')) = ?")
                params.append(requested)
            # A bounded recent panel must remain bounded inside SQLite.  When an
            # old schema has no asset_type/source column, over-read a limited
            # window and preserve the existing Python classifier below.
            sql_limit = ""
            if limit is not None:
                overread = max(1, int(limit)) if requested_source or "asset_type" in columns else max(1, int(limit)) * 20
                sql_limit = " LIMIT ?"
                params.append(min(overread, 20_000))
            order_sql = " ORDER BY exit_time DESC" if limit is not None else ""
            rows = connection.execute(
                f"""
                SELECT symbol, {exchange_expression}, {asset_expression}, {pnl_expression},
                       {notional_expression}, COALESCE(exit_time, entry_time),
                       DATE(COALESCE(exit_time, entry_time)), {side_expression},
                       COALESCE({pnl_percent_expression}, 0), COALESCE({fees_expression}, 0),
                       COALESCE({entry_price_expression}, 0), COALESCE({exit_price_expression}, 0),
                       COALESCE({quantity_expression}, 0),
                       entry_time, exit_time
                FROM trade_log
                WHERE {' AND '.join(where_parts)}{order_sql}{sql_limit}
                """,
                tuple(params),
            ).fetchall()

        normalized: list[dict[str, Any]] = []
        for (
            symbol, exchange, explicit_class, pnl, notional, timestamp, day,
            side, pnl_percent, fees, entry_price, exit_price, quantity, entry_time, exit_time,
        ) in rows:
            normalized_class = _classify_trade(symbol, exchange, explicit_class)
            if requested and normalized_class != requested:
                continue
            # A source workspace must never relabel unscoped or another venue's
            # records as its own performance. Missing venue metadata therefore
            # fails closed instead of falling back to an asset-class aggregate.
            if requested_source and _normalize_venue(exchange) != requested_source:
                continue
            normalized.append({
                "symbol": str(symbol or ""),
                "exchange": str(exchange or ""),
                "asset_class": normalized_class,
                "currency": _trade_currency(symbol, exchange, normalized_class),
                "pnl": _number(pnl),
                "pnl_percent": _number(pnl_percent),
                "fees": _number(fees),
                "notional": _number(notional),
                "entry_price": _number(entry_price),
                "exit_price": _number(exit_price),
                "quantity": _number(quantity),
                "side": str(side or ""),
                "entry_time": str(entry_time or ""),
                "exit_time": str(exit_time or ""),
                "timestamp": str(timestamp or ""),
                "day": str(day or ""),
            })
            if limit is not None and len(normalized) >= max(0, int(limit)):
                break
        result.update(records=normalized, schema_compatible=True)
    except Exception as exc:
        result["error"] = str(exc)
    return result


def load_trade_history_metrics(db_path: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "closed_count": 0,
        "pnl_by_currency": {},
        "pnl_by_asset_currency": {"crypto": {}, "stock": {}, "other": {}},
        "daily_pnl": {},
        "schema_compatible": False,
        "error": "",
    }
    loaded = load_closed_trade_records(db_path, confirmed_only=True)
    result["schema_compatible"] = bool(loaded.get("schema_compatible"))
    result["error"] = str(loaded.get("error") or "")
    for record in loaded.get("records", []):
        asset_class = str(record.get("asset_class") or "other")
        currency = str(record.get("currency") or "")
        pnl = _number(record.get("pnl"))
        day = str(record.get("day") or "")
        result["closed_count"] += 1
        result["pnl_by_currency"][currency] = result["pnl_by_currency"].get(currency, 0.0) + pnl
        asset_bucket = result["pnl_by_asset_currency"].setdefault(asset_class, {})
        asset_bucket[currency] = asset_bucket.get(currency, 0.0) + pnl
        if day and asset_class in {"crypto", "stock"}:
            day_bucket = result["daily_pnl"].setdefault(day, {})
            day_bucket[asset_class] = day_bucket.get(asset_class, 0.0) + pnl
    return result
