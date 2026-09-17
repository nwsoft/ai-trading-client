"""Read-only, bounded LIVE close history for one account database and venue.

This is a lifecycle ledger, not a list of all exchange fills. Missing evidence
must never become confirmed PnL. PAPER and unscoped records stay separate.
"""
import math
import sqlite3
from contextlib import closing
from pathlib import Path

from trading.exchanges.venue_capabilities import SUPPORTED_VENUES, STOCK_VENUES, normalize_venue
from .asset_insight_data import CONFIRMED_TRADE_STATUSES


def load_source_live_history(db_path, *, source, limit=50):
    venue = normalize_venue(source)
    limit = max(1, min(int(limit), 100))
    result = dict(source=venue, status="unavailable", error="", records=[], limit=limit,
                  scope="stored_closed_trades", has_more=False)
    if venue not in SUPPORTED_VENUES:
        return {**result, "error": "source_required"}
    if not db_path or not Path(db_path).is_file():
        return {**result, "error": "database_missing"}
    try:
        with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            columns = {str(row[1]) for row in db.execute("PRAGMA table_info(trade_log)")}
            if not {"symbol", "exchange", "exit_time"}.issubset(columns):
                return {**result, "error": "history_schema_missing"}
            # SQL filtering happens BEFORE LIMIT, including historical broker aliases.
            db.create_function("history_venue", 1, normalize_venue, deterministic=True)
            fields = [name for name in (
                "id", "symbol", "exchange", "asset_type", "entry_time", "exit_time", "side",
                "entry_price", "exit_price", "quantity", "net_pnl", "reconciliation_status",
                "settlement_currency", "execution_mode", "position_owner", "reason",
                "strategy_key", "version_id", "strategy_version_id",
            ) if name in columns]
            mode_clause = (
                "AND LOWER(TRIM(COALESCE(NULLIF(execution_mode, ''), 'live'))) "
                "IN ('live', 'live_api', 'optimized', 'manual')"
                if "execution_mode" in columns else ""
            )
            order = "julianday(exit_time) DESC, exit_time DESC" + (", id DESC" if "id" in columns else "")
            rows = db.execute(
                f"SELECT {', '.join(fields)} FROM trade_log WHERE history_venue(exchange) = ? "
                "AND exit_time IS NOT NULL AND TRIM(exit_time) != '' "
                f"{mode_clause} ORDER BY {order} LIMIT ?", (venue, limit + 1),
            ).fetchall()
        result["has_more"] = len(rows) > limit

        def finite(value):
            try:
                number = float(value)
                return number if math.isfinite(number) else None
            except (ValueError, TypeError, OverflowError):
                return None

        for raw in rows[:limit]:
            row = dict(raw)
            symbol = str(row.get("symbol") or "")
            currency = str(row.get("settlement_currency") or "").strip().upper()
            if not currency:
                currency = ("KRW" if symbol.isdigit() and len(symbol) == 6 else "UNKNOWN") if venue in STOCK_VENUES else (
                    "KRW" if venue in {"upbit", "bithumb", "coinone"} else
                    "USDT" if "USDT" in symbol.upper() else "UNKNOWN")
            mode = str(row.get("execution_mode") or "").strip().lower()
            owner = str(row.get("position_owner") or "").strip().lower()
            status = str(row.get("reconciliation_status") or "")
            net = finite(row.get("net_pnl"))
            imported = str(row.get("reason") or "").lower() == "binance_import"
            confirmed = (mode in {"live", "live_api", "optimized", "manual"}
                         and status in CONFIRMED_TRADE_STATUSES and net is not None and currency != "UNKNOWN"
                         and not imported and owner not in {"manual", "external"})
            result["records"].append({
                "id": str(row.get("id") or ""), "source": venue, "symbol": symbol,
                "asset_class": "stock" if venue in STOCK_VENUES else "crypto",
                "asset_type": str(row.get("asset_type") or ""), "currency": currency,
                "entry_time": str(row.get("entry_time") or ""), "exit_time": str(row["exit_time"]),
                "side": str(row.get("side") or ""), "entry_price": finite(row.get("entry_price")),
                "exit_price": finite(row.get("exit_price")), "quantity": finite(row.get("quantity")),
                "net_pnl": net if confirmed else None,
                "evidence": "imported" if imported else "external" if owner in {"manual", "external"} else
                            "confirmed" if confirmed else "unreconciled",
                "strategy_key": str(row.get("strategy_key") or ""),
                "version_id": str(row.get("version_id") or row.get("strategy_version_id") or ""),
            })
        return {**result, "status": "available"}
    except (sqlite3.Error, OSError, ValueError):
        return {**result, "records": [], "error": "history_read_failed"}
