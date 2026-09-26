"""Read-only, account-scoped query models for Web UI feature workspaces."""

from __future__ import annotations

import json
import mmap
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from config.settings import load_settings
from .source_trade_history import load_source_live_history
from path_utils import get_ai_learning_data_path, get_db_file_path, get_exchange_ai_learning_data_path
from .asset_insight_data import (
    _classify_trade,
    _trade_currency,
    load_closed_trade_records,
    load_trade_history_metrics,
)
from trading.exchanges.venue_capabilities import (
    CRYPTO_VENUES,
    STOCK_VENUES,
    normalize_venue,
    venue_quote_currency,
)


CRYPTO_SOURCES = set(CRYPTO_VENUES)
STOCK_SOURCES = set(STOCK_VENUES)
LIVE_EXECUTION_MODES = {"live", "live_api", "optimized", "manual"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return value[:2000]
    return decoded if isinstance(decoded, (dict, list, str, int, float, bool)) or decoded is None else str(decoded)


def _normalize_source(value: Any) -> str:
    return normalize_venue(value)


def _minutes_between(start: Any, end: Any) -> float | None:
    try:
        started = datetime.fromisoformat(str(start or "").replace("Z", "+00:00"))
        ended = datetime.fromisoformat(str(end or "").replace("Z", "+00:00"))
        minutes = (ended - started).total_seconds() / 60.0
        return minutes if minutes > 0 else None
    except (TypeError, ValueError):
        return None


def _timestamp_epoch(value: Any) -> float | None:
    """Normalize legacy local-naive and ISO/UTC ledger timestamps.

    Older NoahAI ledgers stored Windows local time without an offset, while
    newer services may persist ISO-8601 UTC values.  SQLite string comparison
    cannot safely mix those forms.  Naive values therefore keep their original
    contract (system local time at that historical date), and offset-aware
    values are converted by their explicit offset.
    """
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric / 1000.0 if abs(numeric) > 10_000_000_000 else numeric
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed.timestamp()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _live_execution_clause(columns: set[str], *, prefix: str = "") -> str | None:
    """Return the LIVE ledger predicate, including two historical aliases.

    Binance releases before v3.9.1.23 wrote the strategy style (``optimized``
    or ``manual``) into ``execution_mode`` even though the order path was LIVE.
    They remain visible as legacy LIVE records, while PAPER and LEARNING are
    always excluded. New records are written as ``live``.
    """
    if "execution_mode" not in columns:
        return None
    column = f"{prefix}execution_mode"
    values = ",".join(f"'{value}'" for value in sorted(LIVE_EXECUTION_MODES))
    return f"LOWER(TRIM(COALESCE(NULLIF({column}, ''), 'live'))) IN ({values})"


def _confirmed_net_pnl_expression(columns: set[str], *, prefix: str = "") -> str:
    """Return money only when the close has an auditable execution contract."""
    if "reconciliation_status" not in columns:
        return "NULL"
    pnl_column = f"{prefix}net_pnl" if "net_pnl" in columns else f"{prefix}pnl"
    status_column = f"{prefix}reconciliation_status"
    statuses = (
        "'exchange_confirmed','exchange_confirmed_partial',"
        "'broker_order_linked','exact_fill_price_no_provider_pnl'"
    )
    return f"CASE WHEN {status_column} IN ({statuses}) THEN {pnl_column} ELSE NULL END"


def _statistics_time_range(
    period: str,
    *,
    custom_start: str = "",
    custom_end: str = "",
    baseline_at: str = "",
) -> tuple[str, float | None, float]:
    """Resolve the five display ranges in local time without deleting data."""
    now = datetime.now().astimezone()
    normalized = str(period or "today").strip().lower()
    if normalized not in {"today", "7d", "30d", "all", "custom"}:
        normalized = "today"
    start: datetime | None
    if normalized == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif normalized == "7d":
        start = now - timedelta(days=7)
    elif normalized == "30d":
        start = now - timedelta(days=30)
    elif normalized == "custom":
        try:
            start = datetime.fromisoformat(str(custom_start).strip()).astimezone()
        except (TypeError, ValueError):
            raise ValueError("statistics_custom_start_required")
    else:
        start = None

    end = now
    if normalized == "custom" and str(custom_end or "").strip():
        try:
            parsed_end = datetime.fromisoformat(str(custom_end).strip()).astimezone()
        except (TypeError, ValueError):
            raise ValueError("statistics_custom_end_invalid")
        # Date-only input includes the complete selected end day.
        if len(str(custom_end).strip()) == 10:
            parsed_end = parsed_end.replace(hour=23, minute=59, second=59, microsecond=999999)
        end = min(parsed_end, now)

    baseline_epoch = _timestamp_epoch(baseline_at)
    if baseline_epoch is not None and (start is None or baseline_epoch > start.timestamp()):
        start = datetime.fromtimestamp(baseline_epoch, tz=now.tzinfo)
    if start is not None and start > end:
        raise ValueError("statistics_range_invalid")
    return normalized, start.timestamp() if start is not None else None, end.timestamp()


@lru_cache(maxsize=128)
def _count_pretty_json_array_records(path_value: str, mtime_ns: int, file_size: int) -> int | None:
    """Count top-level indent=2 objects once per immutable file revision."""
    del mtime_ns, file_size  # cache-key only; path content is read below
    path = Path(path_value)
    try:
        with path.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            total = 0
            cursor = 0
            while True:
                found = mapped.find(b"\n  {", cursor)
                if found < 0:
                    break
                total += 1
                cursor = found + 4
            return total or None
    except (OSError, ValueError):
        return None


class AccountQueryService:
    """Build UI-neutral snapshots from the existing account database and files."""

    # Above 4 MB the screen must not decode the complete history merely to
    # render 50 recent rows. Current retained 6k/10k exchange files are already
    # 13-23 MB in real accounts, so they take the bounded-tail path as well.
    LARGE_LEARNING_FILE_BYTES = 4 * 1024 * 1024

    TABLE_LIMITS = {
        "trade_log": 250,
        "ai_decisions": 100,
        "ai_trade_analysis": 100,
        "analysis_log": 100,
        "selected_coins": 200,
        "exchange_trade_stats": 100,
        "stock_trade_stats": 100,
        "risk_log": 100,
        "performance_stats": 100,
        "exchange_execution_log": 100,
        "stock_execution_metrics": 100,
    }

    def __init__(self, db_path: str | None = None):
        self.db_path = str(db_path or get_db_file_path())

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path or not os.path.exists(self.db_path):
            raise FileNotFoundError("account_database_missing")
        connection = sqlite3.connect(f"file:{Path(self.db_path).resolve()}?mode=ro", uri=True, timeout=2)
        connection.row_factory = sqlite3.Row
        connection.create_function("noah_epoch", 1, _timestamp_epoch, deterministic=True)
        connection.execute("PRAGMA query_only=ON")
        return connection

    @staticmethod
    def _execution_capability_status(
        connection: sqlite3.Connection, requested_source: str, confirmed_count: int,
    ) -> dict[str, Any]:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='exchange_execution_capability'"
        ).fetchone()
        if not exists:
            return {
                "history_available": bool(confirmed_count),
                "history_status": "stored_only" if confirmed_count else "not_checked",
                "history_reason": "capability_ledger_missing",
            }
        params: tuple[Any, ...] = ()
        where = ""
        if requested_source:
            where = " WHERE LOWER(REPLACE(REPLACE(REPLACE(exchange, '_', ''), '-', ''), ' ', '')) = ?"
            params = (requested_source,)
        columns = {
            str(row[1]) for row in connection.execute(
                "PRAGMA table_info(exchange_execution_capability)"
            ).fetchall()
        }
        completeness_expr = "history_complete" if "history_complete" in columns else "1 AS history_complete"
        coverage_reason_expr = "coverage_reason" if "coverage_reason" in columns else "'legacy_capability' AS coverage_reason"
        rows = connection.execute(
            f"SELECT history_available, history_reason, {completeness_expr}, {coverage_reason_expr} "
            f"FROM exchange_execution_capability{where}", params
        ).fetchall()
        if not rows:
            return {
                "history_available": bool(confirmed_count),
                "history_status": "stored_only" if confirmed_count else "not_checked",
                "history_reason": "history_capability_not_checked",
            }
        available = sum(1 for row in rows if bool(row["history_available"]))
        unavailable = len(rows) - available
        if unavailable and available:
            return {"history_available": True, "history_status": "partial", "history_reason": "some_exchange_history_unsupported"}
        if unavailable:
            return {
                "history_available": False,
                "history_status": "stored_only" if confirmed_count else "unsupported",
                "history_reason": str(rows[0]["history_reason"] or "exchange_history_api_unsupported"),
            }
        incomplete = [row for row in rows if not bool(row["history_complete"])]
        if incomplete:
            return {
                "history_available": True,
                "history_status": "partial",
                "history_reason": str(incomplete[0]["coverage_reason"] or "bounded_or_incremental_history"),
            }
        return {"history_available": True, "history_status": "available", "history_reason": "available"}

    def table_rows(self, table: str, *, limit: int | None = None, source: str = "") -> list[dict[str, Any]]:
        if table not in self.TABLE_LIMITS:
            raise ValueError("unsupported_query_table")
        row_limit = max(1, min(int(limit or self.TABLE_LIMITS[table]), self.TABLE_LIMITS[table]))
        try:
            with closing(self._connect()) as connection:
                exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
                if not exists:
                    return []
                columns = [str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()]
                order_column = next((name for name in ("created_at", "last_updated", "exit_time", "entry_time", "id") if name in columns), None)
                order_sql = f" ORDER BY {order_column} DESC" if order_column else ""
                requested_source = _normalize_source(source)
                source_column = next((name for name in ("exchange", "source", "broker") if name in columns), None)
                if requested_source and source_column is None:
                    return []
                if requested_source:
                    # Query a wider bounded tail before normalizing aliases so
                    # one venue cannot crowd another venue out of the result.
                    rows = connection.execute(
                        f"SELECT * FROM {table}{order_sql} LIMIT ?", (min(row_limit * 20, 2000),)
                    ).fetchall()
                    rows = [row for row in rows if _normalize_source(row[source_column]) == requested_source][:row_limit]
                else:
                    rows = connection.execute(f"SELECT * FROM {table}{order_sql} LIMIT ?", (row_limit,)).fetchall()
            output = []
            for row in rows:
                safe = {}
                for key in row.keys():
                    value = row[key]
                    if str(key).lower() in {"decision_json", "analysis_json", "metadata", "details"}:
                        value = _safe_json(value)
                    safe[str(key)] = value
                output.append(safe)
            return output
        except (OSError, sqlite3.Error):
            return []

    def selected_coin_rows(self, *, source: str = "") -> list[dict[str, Any]]:
        """Return only the newest source-scoped selection session.

        Older schemas did not record an exchange and cannot be attributed safely.
        Those rows remain preserved but are not exposed as another venue's current
        candidates.
        """
        requested_source = _normalize_source(source)
        if not requested_source:
            return self.table_rows("selected_coins")
        try:
            with closing(self._connect()) as connection:
                exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='selected_coins'"
                ).fetchone()
                if not exists:
                    return []
                columns = {
                    str(row[1]) for row in connection.execute("PRAGMA table_info(selected_coins)").fetchall()
                }
                if not {"exchange", "session_id"}.issubset(columns):
                    return []
                scoped = connection.execute(
                    "SELECT MAX(session_id) FROM selected_coins "
                    "WHERE LOWER(REPLACE(REPLACE(REPLACE(COALESCE(exchange, ''), '_', ''), '-', ''), ' ', '')) = ?",
                    (requested_source,),
                ).fetchone()
                session_id = int((scoped or [0])[0] or 0)
                if session_id <= 0:
                    return []
                rows = connection.execute(
                    "SELECT * FROM selected_coins WHERE session_id = ? "
                    "AND LOWER(REPLACE(REPLACE(REPLACE(COALESCE(exchange, ''), '_', ''), '-', ''), ' ', '')) = ? "
                    "ORDER BY id ASC LIMIT ?",
                    (session_id, requested_source, self.TABLE_LIMITS["selected_coins"]),
                ).fetchall()
            return [{str(key): row[key] for key in row.keys()} for row in rows]
        except (OSError, sqlite3.Error, ValueError):
            return []

    def trading_overview(
        self,
        *,
        asset_class: str | None = None,
        source: str = "",
        period: str = "all",
        custom_start: str = "",
        custom_end: str = "",
        baseline_at: str = "",
    ) -> dict[str, Any]:
        # Cards render only a recent tail, while their count/win/PnL values are
        # complete aggregates.  The former implementation derived all four
        # values from a capped 200-row Python list, so "총 거래" stopped at 200
        # and repeatedly sorted much more of trade_log than the screen needed.
        loaded = load_closed_trade_records(self.db_path, asset_class=asset_class, source=source or None, limit=50)
        rows = list(loaded.get("records") or [])
        totals = self._closed_trade_totals(
            asset_class=asset_class,
            source=source,
            period=period,
            custom_start=custom_start,
            custom_end=custom_end,
            baseline_at=baseline_at,
        )
        closed_count = int(totals.get("closed_count") or 0)
        reconciled_closed_count = int(totals.get("reconciled_closed_count") or 0)
        wins = int(totals.get("winning_count") or 0)
        return {
            "open_position_count": self._managed_open_position_count(asset_class=asset_class, source=source),
            "closed_count": closed_count,
            "reconciled_closed_count": reconciled_closed_count,
            "unresolved_closed_count": int(totals.get("unresolved_closed_count") or 0),
            "win_rate": round((wins / reconciled_closed_count * 100), 2) if reconciled_closed_count else 0.0,
            "pnl_by_currency": dict(totals.get("pnl_by_currency") or {}),
            "recent_trades": rows[:50],
            "schema_compatible": bool(loaded.get("schema_compatible")) and bool(totals.get("schema_compatible")),
            "error": str(totals.get("error") or loaded.get("error") or ""),
            "range": dict(totals.get("range") or {}),
        }

    def report_period_metrics(
        self,
        *,
        asset_class: str,
        source: str = "",
        detail_period: str = "today",
        detail_offset: int = 0,
        detail_limit: int = 100,
        baseline_at: str = "",
    ) -> dict[str, Any]:
        """Return exact period aggregates without loading the trade history.

        Confirmed exchange fills and NoahAI-managed closed positions remain two
        separate measures.  Currency maps are deliberately not collapsed to a
        scalar because KRW spot and USDT futures are not additive without an
        explicit FX conversion policy.
        """
        now = datetime.now().astimezone()
        starts = {
            "today": now.replace(hour=0, minute=0, second=0, microsecond=0),
            "week": (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0),
            "month": now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
            "realtime": now - timedelta(hours=1),
        }
        requested_detail_period = str(detail_period or "today").strip().lower()
        if requested_detail_period not in starts:
            requested_detail_period = "today"
        requested_detail_offset = max(0, int(detail_offset or 0))
        requested_detail_limit = max(10, min(int(detail_limit or 100), 200))
        requested_source = _normalize_source(source)
        result: dict[str, Any] = {
            "asset_class": asset_class,
            "source": requested_source,
            "periods": {},
            "execution_history_available": False,
            "execution_history_status": "not_checked",
            "execution_history_reason": "execution_ledger_not_checked",
            "timezone": str(now.tzinfo or "local"),
            "generated_at": now.isoformat(),
            "detail_period": requested_detail_period,
        }
        try:
            with closing(self._connect()) as connection:
                trade_columns = {
                    str(row[1]) for row in connection.execute("PRAGMA table_info(trade_log)").fetchall()
                }
                if not {"symbol", "pnl", "exit_time"}.issubset(trade_columns):
                    raise sqlite3.OperationalError("trade_log_schema_missing")
                execution_exists = bool(connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='exchange_execution_log'"
                ).fetchone())
                if not execution_exists:
                    result["execution_history_available"] = False
                    result["execution_history_reason"] = "exchange_execution_ledger_missing"

                exchange_expr = "exchange" if "exchange" in trade_columns else "NULL"
                asset_expr = "asset_type" if "asset_type" in trade_columns else "NULL"
                fee_expr = next((name for name in ("fees", "fee", "commission") if name in trade_columns), "0")
                confirmed_net_expr = _confirmed_net_pnl_expression(trade_columns)
                order_columns = [name for name in ("order_id", "exit_order_id") if name in trade_columns]
                for key, started in starts.items():
                    start_epoch = started.timestamp()
                    baseline_epoch = _timestamp_epoch(baseline_at)
                    if baseline_epoch is not None:
                        start_epoch = max(start_epoch, baseline_epoch)
                    end_epoch = now.timestamp()
                    params: list[Any] = [start_epoch, end_epoch]
                    where = [
                        "exit_time IS NOT NULL",
                        "noah_epoch(exit_time) >= ?",
                        "noah_epoch(exit_time) <= ?",
                    ]
                    live_clause = _live_execution_clause(trade_columns)
                    if live_clause:
                        where.append(live_clause)
                    if "reason" in trade_columns:
                        where.append("LOWER(COALESCE(reason, '')) != 'binance_import'")
                        where.append("LOWER(COALESCE(reason, '')) != 'stock_trade_sync'")
                    if "position_owner" in trade_columns:
                        where.append("LOWER(COALESCE(position_owner, 'legacy_unknown')) NOT IN ('manual', 'external')")
                    if requested_source:
                        if "exchange" not in trade_columns:
                            aggregate_rows = []
                        else:
                            where.append("LOWER(REPLACE(REPLACE(REPLACE(COALESCE(exchange, ''), '_', ''), '-', ''), ' ', '')) = ?")
                            params.append(requested_source)
                            aggregate_rows = connection.execute(
                                f"""SELECT symbol, {exchange_expr} AS exchange_name, {asset_expr} AS asset_name,
                                           COUNT(*) AS closed_count,
                                           SUM(CASE WHEN {confirmed_net_expr} > 0 THEN 1 ELSE 0 END) AS winning_count,
                                           SUM(CASE WHEN {confirmed_net_expr} < 0 THEN 1 ELSE 0 END) AS losing_count,
                                           SUM(CASE WHEN {confirmed_net_expr} IS NOT NULL THEN 1 ELSE 0 END) AS reconciled_count,
                                           SUM(COALESCE({confirmed_net_expr}, 0)) AS pnl,
                                           SUM(COALESCE({fee_expr}, 0)) AS fees
                                    FROM trade_log WHERE {' AND '.join(where)}
                                    GROUP BY symbol, {exchange_expr}, {asset_expr}""",
                                tuple(params),
                            ).fetchall()
                    else:
                        aggregate_rows = connection.execute(
                            f"""SELECT symbol, {exchange_expr} AS exchange_name, {asset_expr} AS asset_name,
                                       COUNT(*) AS closed_count,
                                       SUM(CASE WHEN {confirmed_net_expr} > 0 THEN 1 ELSE 0 END) AS winning_count,
                                       SUM(CASE WHEN {confirmed_net_expr} < 0 THEN 1 ELSE 0 END) AS losing_count,
                                       SUM(CASE WHEN {confirmed_net_expr} IS NOT NULL THEN 1 ELSE 0 END) AS reconciled_count,
                                       SUM(COALESCE({confirmed_net_expr}, 0)) AS pnl,
                                       SUM(COALESCE({fee_expr}, 0)) AS fees
                                FROM trade_log WHERE {' AND '.join(where)}
                                GROUP BY symbol, {exchange_expr}, {asset_expr}""",
                            tuple(params),
                        ).fetchall()

                    closed = wins = losses = reconciled = 0
                    pnl_by_currency: dict[str, float] = {}
                    fees_by_currency: dict[str, float] = {}
                    for row in aggregate_rows:
                        classified = _classify_trade(row["symbol"], row["exchange_name"], row["asset_name"])
                        if classified != asset_class:
                            continue
                        currency = _trade_currency(row["symbol"], row["exchange_name"], classified)
                        closed += int(row["closed_count"] or 0)
                        wins += int(row["winning_count"] or 0)
                        losses += int(row["losing_count"] or 0)
                        reconciled += int(row["reconciled_count"] or 0)
                        pnl_by_currency[currency] = pnl_by_currency.get(currency, 0.0) + _number(row["pnl"])
                        fees_by_currency[currency] = fees_by_currency.get(currency, 0.0) + _number(row["fees"])

                    execution_count = 0
                    execution_notional: dict[str, float] = {}
                    if execution_exists:
                        execution_params: list[Any] = [start_epoch, end_epoch]
                        execution_where = [
                            "confirmation_status = 'confirmed'",
                            "noah_epoch(COALESCE(executed_at, created_at)) >= ?",
                            "noah_epoch(COALESCE(executed_at, created_at)) <= ?",
                        ]
                        if requested_source:
                            execution_where.append("LOWER(REPLACE(REPLACE(REPLACE(exchange, '_', ''), '-', ''), ' ', '')) = ?")
                            execution_params.append(requested_source)
                        else:
                            supported_venues = CRYPTO_VENUES if asset_class == "crypto" else STOCK_VENUES
                            supported_sql = ",".join(f"'{item}'" for item in sorted(supported_venues))
                            execution_where.append(
                                "LOWER(REPLACE(REPLACE(REPLACE(COALESCE(exchange, ''), '_', ''), '-', ''), ' ', '')) "
                                f"IN ({supported_sql})"
                            )
                        execution_rows = connection.execute(
                            f"SELECT exchange, COUNT(*) AS row_count, SUM(ABS(COALESCE(cost, 0))) AS notional "
                            f"FROM exchange_execution_log WHERE {' AND '.join(execution_where)} GROUP BY exchange",
                            tuple(execution_params),
                        ).fetchall()
                        for row in execution_rows:
                            currency = venue_quote_currency(row["exchange"], "USDT")
                            execution_count += int(row["row_count"] or 0)
                            execution_notional[currency] = execution_notional.get(currency, 0.0) + _number(row["notional"])

                    capability = (
                        self._execution_capability_status(connection, requested_source, execution_count)
                        if execution_exists
                        else {
                            "history_available": False,
                            "history_status": "unsupported",
                            "history_reason": result["execution_history_reason"],
                        }
                    )

                    linked = legacy_unknown = 0
                    if execution_exists and order_columns and "exchange" in trade_columns:
                        link_tests = [
                            f"NULLIF(TRIM(COALESCE(t.{column}, '')), '') = e.order_id" for column in order_columns
                        ]
                        link_params: list[Any] = [start_epoch, end_epoch]
                        link_where = [
                            "t.exit_time IS NOT NULL",
                            "noah_epoch(t.exit_time) >= ?",
                            "noah_epoch(t.exit_time) <= ?",
                        ]
                        link_live_clause = _live_execution_clause(trade_columns, prefix="t.")
                        if link_live_clause:
                            link_where.append(link_live_clause)
                        if "exchange" in trade_columns:
                            normalized_exchange = "LOWER(REPLACE(REPLACE(REPLACE(COALESCE(t.exchange, ''), '_', ''), '-', ''), ' ', ''))"
                            supported_venues = CRYPTO_VENUES if asset_class == "crypto" else STOCK_VENUES
                            supported_sql = ",".join(f"'{item}'" for item in sorted(supported_venues))
                            link_where.append(f"({normalized_exchange} IN ({supported_sql}) OR {normalized_exchange} = '')")
                        if "reason" in trade_columns:
                            link_where.append("LOWER(COALESCE(t.reason, '')) != 'binance_import'")
                        if requested_source and "exchange" in trade_columns:
                            link_where.append("LOWER(REPLACE(REPLACE(REPLACE(COALESCE(t.exchange, ''), '_', ''), '-', ''), ' ', '')) = ?")
                            link_params.append(requested_source)
                        link_row = connection.execute(
                            f"""SELECT
                                  SUM(CASE WHEN EXISTS (
                                      SELECT 1 FROM exchange_execution_log e
                                      WHERE e.confirmation_status = 'confirmed'
                                        AND ({' OR '.join(link_tests)})
                                        AND LOWER(REPLACE(REPLACE(REPLACE(COALESCE(e.exchange, ''), '_', ''), '-', ''), ' ', '')) =
                                            LOWER(REPLACE(REPLACE(REPLACE(COALESCE(t.exchange, ''), '_', ''), '-', ''), ' ', ''))
                                  ) THEN 1 ELSE 0 END) AS linked_count,
                                  SUM(CASE WHEN LOWER(COALESCE({('t.position_owner' if 'position_owner' in trade_columns else "'legacy_unknown'")}, 'legacy_unknown')) = 'legacy_unknown' THEN 1 ELSE 0 END) AS legacy_count
                                FROM trade_log t WHERE {' AND '.join(link_where)}""",
                            tuple(link_params),
                        ).fetchone()
                        linked = int(link_row["linked_count"] or 0) if link_row else 0
                        legacy_unknown = int(link_row["legacy_count"] or 0) if link_row else 0

                    detail_rows: list[dict[str, Any]] = []
                    detail_total = 0
                    detail_pnl: dict[str, float] = {}
                    detail_fees: dict[str, float] = {}
                    if key == requested_detail_period:
                        detail_where = [
                            "exit_time IS NOT NULL",
                            "noah_epoch(exit_time) >= ?",
                            "noah_epoch(exit_time) <= ?",
                        ]
                        detail_live_clause = _live_execution_clause(trade_columns)
                        if detail_live_clause:
                            detail_where.append(detail_live_clause)
                        detail_params: list[Any] = [start_epoch, end_epoch]
                        if "reason" in trade_columns:
                            detail_where.append("LOWER(COALESCE(reason, '')) != 'binance_import'")
                            detail_where.append("LOWER(COALESCE(reason, '')) != 'stock_trade_sync'")
                        if "position_owner" in trade_columns:
                            detail_where.append("LOWER(COALESCE(position_owner, 'legacy_unknown')) NOT IN ('manual', 'external')")
                        if requested_source:
                            if "exchange" not in trade_columns:
                                raw_detail_rows = []
                            else:
                                detail_where.append(
                                    "LOWER(REPLACE(REPLACE(REPLACE(COALESCE(exchange, ''), '_', ''), '-', ''), ' ', '')) = ?"
                                )
                                detail_params.append(requested_source)
                                raw_detail_rows = None
                        else:
                            raw_detail_rows = None
                        # Do not filter by raw asset_type here. Legacy rows may
                        # use an empty/older label and are classified from
                        # symbol+venue by the same helper as the aggregate.
                        if raw_detail_rows is None:
                            select_expr = {
                                "row_id": "id" if "id" in trade_columns else "rowid",
                                "exchange_name": "exchange" if "exchange" in trade_columns else "NULL",
                                "asset_name": "asset_type" if "asset_type" in trade_columns else "NULL",
                                "side_name": "side" if "side" in trade_columns else "NULL",
                                "pnl_percent_value": "pnl_percent" if "pnl_percent" in trade_columns else "0",
                                "entry_price_value": "entry_price" if "entry_price" in trade_columns else "0",
                                "exit_price_value": "exit_price" if "exit_price" in trade_columns else "0",
                                "quantity_value": "quantity" if "quantity" in trade_columns else "0",
                                "entry_time_value": "entry_time" if "entry_time" in trade_columns else "NULL",
                                "reason_value": "reason" if "reason" in trade_columns else "NULL",
                                "reconciliation_value": "reconciliation_status" if "reconciliation_status" in trade_columns else "'legacy_unverified'",
                            }
                            raw_detail_rows = connection.execute(
                                f"""SELECT {select_expr['row_id']} AS row_id, symbol,
                                           {select_expr['exchange_name']} AS exchange_name,
                                           {select_expr['asset_name']} AS asset_name,
                                           {select_expr['side_name']} AS side_name,
                                           {confirmed_net_expr} AS pnl_value,
                                           COALESCE({select_expr['pnl_percent_value']}, 0) AS pnl_percent_value,
                                           COALESCE({fee_expr}, 0) AS fee_value,
                                           COALESCE({select_expr['entry_price_value']}, 0) AS entry_price_value,
                                           COALESCE({select_expr['exit_price_value']}, 0) AS exit_price_value,
                                           COALESCE({select_expr['quantity_value']}, 0) AS quantity_value,
                                           {select_expr['entry_time_value']} AS entry_time_value,
                                           exit_time AS exit_time_value,
                                           {select_expr['reason_value']} AS reason_value
                                           ,{select_expr['reconciliation_value']} AS reconciliation_value
                                    FROM trade_log WHERE {' AND '.join(detail_where)}
                                    ORDER BY noah_epoch(exit_time) DESC, {select_expr['row_id']} DESC""",
                                tuple(detail_params),
                            ).fetchall()
                        normalized_detail: list[dict[str, Any]] = []
                        for row in raw_detail_rows:
                            classified = _classify_trade(row["symbol"], row["exchange_name"], row["asset_name"])
                            if classified != asset_class:
                                continue
                            currency = _trade_currency(row["symbol"], row["exchange_name"], classified)
                            reconciliation_value = str(row["reconciliation_value"] or "legacy_unverified")
                            pnl_value = _number(row["pnl_value"]) if row["pnl_value"] is not None else None
                            fee_value = _number(row["fee_value"])
                            if pnl_value is not None:
                                detail_pnl[currency] = detail_pnl.get(currency, 0.0) + pnl_value
                            detail_fees[currency] = detail_fees.get(currency, 0.0) + fee_value
                            detail_item = {
                                "id": row["row_id"],
                                "symbol": str(row["symbol"] or ""),
                                "exchange": str(row["exchange_name"] or ""),
                                "asset_class": classified,
                                "currency": currency,
                                "side": str(row["side_name"] or ""),
                                "pnl_percent": _number(row["pnl_percent_value"]),
                                "fees": fee_value,
                                "entry_price": _number(row["entry_price_value"]),
                                "exit_price": _number(row["exit_price_value"]),
                                "quantity": _number(row["quantity_value"]),
                                "entry_time": str(row["entry_time_value"] or ""),
                                "exit_time": str(row["exit_time_value"] or ""),
                                "timestamp": str(row["exit_time_value"] or ""),
                                "reason": str(row["reason_value"] or ""),
                                "reconciliation_status": reconciliation_value,
                            }
                            if pnl_value is not None:
                                detail_item["pnl"] = pnl_value
                            normalized_detail.append(detail_item)
                        detail_total = len(normalized_detail)
                        detail_rows = normalized_detail[
                            requested_detail_offset:requested_detail_offset + requested_detail_limit
                        ]

                    def _currency_maps_match(left: dict[str, float], right: dict[str, float]) -> bool:
                        currencies = set(left) | set(right)
                        return all(
                            abs(float(left.get(currency, 0.0)) - float(right.get(currency, 0.0))) <= 1e-8
                            for currency in currencies
                        )

                    period_payload = {
                        "started_at": datetime.fromtimestamp(start_epoch, tz=now.tzinfo).isoformat(),
                        "ended_at": now.isoformat(),
                        "closed_count": closed,
                        "reconciled_closed_count": reconciled,
                        "unresolved_closed_count": max(0, closed - reconciled),
                        "winning_count": wins,
                        "losing_count": losses,
                        "win_rate": round(wins / reconciled * 100.0, 2) if reconciled else 0.0,
                        "pnl_by_currency": pnl_by_currency,
                        "fees_by_currency": fees_by_currency,
                        "execution_count": execution_count,
                        "execution_notional_by_currency": execution_notional,
                        "linked_closed_count": min(linked, closed),
                        "unlinked_closed_count": max(0, closed - linked),
                        "legacy_unknown_count": min(legacy_unknown, closed),
                        "execution_history_available": capability["history_available"],
                        "execution_history_status": capability["history_status"],
                        "execution_history_reason": capability["history_reason"],
                        "baseline_at": str(baseline_at or "") or None,
                        "baseline_applied": baseline_epoch is not None,
                    }
                    if key == requested_detail_period:
                        period_payload.update({
                            "detail_rows": detail_rows,
                            "detail_total_count": detail_total,
                            "detail_offset": requested_detail_offset,
                            "detail_limit": requested_detail_limit,
                            "detail_has_more": requested_detail_offset + len(detail_rows) < detail_total,
                            "detail_checksum": {
                                "closed_count": detail_total,
                                "pnl_by_currency": detail_pnl,
                                "fees_by_currency": detail_fees,
                            },
                            "ledger_reconciled": bool(
                                detail_total == closed
                                and _currency_maps_match(detail_pnl, pnl_by_currency)
                                and _currency_maps_match(detail_fees, fees_by_currency)
                            ),
                        })
                    result["periods"][key] = period_payload
                    if key == "today":
                        result["execution_history_available"] = capability["history_available"]
                        result["execution_history_status"] = capability["history_status"]
                        result["execution_history_reason"] = capability["history_reason"]
        except (OSError, sqlite3.Error) as exc:
            result["error"] = str(exc)
        return result

    def _closed_trade_totals(
        self,
        *,
        asset_class: str | None,
        source: str = "",
        period: str = "all",
        custom_start: str = "",
        custom_end: str = "",
        baseline_at: str = "",
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "closed_count": 0, "winning_count": 0, "pnl_by_currency": {},
            "reconciled_closed_count": 0, "unresolved_closed_count": 0,
            "legacy_unattributed_count": 0,
            "schema_compatible": False, "error": "",
        }
        requested_source = _normalize_source(source)
        try:
            normalized_period, start_epoch, end_epoch = _statistics_time_range(
                period,
                custom_start=custom_start,
                custom_end=custom_end,
                baseline_at=baseline_at,
            )
            with closing(self._connect()) as connection:
                # ``exchange_trade_stats`` is a compatibility/performance
                # cache. Older unified venues stored percentages in its PnL
                # column, so it must never be a financial display authority.
                columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(trade_log)").fetchall()}
                if not {"symbol", "pnl", "exit_time"}.issubset(columns):
                    result["error"] = "trade_log_schema_missing"
                    return result
                exchange_expression = "exchange" if "exchange" in columns else "NULL"
                asset_expression = "asset_type" if "asset_type" in columns else "NULL"
                confirmed_net_expression = _confirmed_net_pnl_expression(columns)
                where = ["exit_time IS NOT NULL"]
                params: list[Any] = []
                live_clause = _live_execution_clause(columns)
                if live_clause:
                    where.append(live_clause)
                if start_epoch is not None:
                    where.append("noah_epoch(exit_time) >= ?")
                    params.append(start_epoch)
                where.append("noah_epoch(exit_time) <= ?")
                params.append(end_epoch)
                if "reason" in columns:
                    where.append("LOWER(COALESCE(reason, '')) != 'binance_import'")
                if requested_source:
                    if "exchange" not in columns:
                        return result
                    where.append(
                        "LOWER(REPLACE(REPLACE(REPLACE(COALESCE(exchange, ''), '_', ''), '-', ''), ' ', '')) = ?"
                    )
                    params.append(requested_source)
                rows = connection.execute(
                    f"""
                    SELECT symbol, {exchange_expression} AS exchange_name, {asset_expression} AS asset_name,
                           COUNT(*) AS closed_count,
                           SUM(CASE WHEN {confirmed_net_expression} > 0 THEN 1 ELSE 0 END) AS winning_count,
                           SUM(CASE WHEN {confirmed_net_expression} IS NOT NULL THEN 1 ELSE 0 END) AS reconciled_count,
                           SUM(COALESCE({confirmed_net_expression}, 0)) AS total_pnl
                    FROM trade_log
                    WHERE {' AND '.join(where)}
                    GROUP BY symbol, {exchange_expression}, {asset_expression}
                    """,
                    tuple(params),
                ).fetchall()
            requested_asset = str(asset_class or "").strip().lower()
            pnl_by_currency: dict[str, float] = {}
            for row in rows:
                if not _normalize_source(row["exchange_name"]):
                    # Preserve these rows in the ledger, but do not let an
                    # unknown historical venue inflate a verified LIVE KPI or
                    # get guessed as Binance.
                    result["legacy_unattributed_count"] += int(row["closed_count"] or 0)
                    continue
                classified = _classify_trade(row["symbol"], row["exchange_name"], row["asset_name"])
                if requested_asset and classified != requested_asset:
                    continue
                count = int(row["closed_count"] or 0)
                pnl = _number(row["total_pnl"])
                currency = _trade_currency(row["symbol"], row["exchange_name"], classified)
                result["closed_count"] += count
                result["winning_count"] += int(row["winning_count"] or 0)
                result["reconciled_closed_count"] += int(row["reconciled_count"] or 0)
                pnl_by_currency[currency] = pnl_by_currency.get(currency, 0.0) + pnl
            result.update(
                pnl_by_currency=pnl_by_currency,
                unresolved_closed_count=max(
                    0, int(result["closed_count"]) - int(result["reconciled_closed_count"])
                ),
                schema_compatible=True,
                range={
                    "period": normalized_period,
                    "started_at": datetime.fromtimestamp(start_epoch, tz=timezone.utc).isoformat() if start_epoch is not None else None,
                    "ended_at": datetime.fromtimestamp(end_epoch, tz=timezone.utc).isoformat(),
                    "baseline_applied": bool(str(baseline_at or "").strip()),
                },
            )
        except (OSError, sqlite3.Error, ValueError) as exc:
            result["error"] = str(exc)
        return result

    def _managed_open_position_count(self, *, asset_class: str | None = None, source: str = "") -> int:
        """Count persisted NoahAI-owned open positions without querying an exchange.

        Scale-in rows for the same venue/symbol/side are one position. Legacy or
        manual rows without an order id and an ownership signal are deliberately
        excluded so the dashboard cannot imply ownership of a user's position.
        """
        try:
            with closing(self._connect()) as connection:
                exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='trade_log'"
                ).fetchone()
                if not exists:
                    return 0
                columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(trade_log)").fetchall()}
                if not {"symbol", "exit_time", "order_id"}.issubset(columns):
                    return 0
                ownership: list[str] = []
                if "position_owner" in columns:
                    ownership.append("LOWER(COALESCE(position_owner, '')) = 'noahai'")
                if "reason" in columns:
                    ownership.append("LOWER(COALESCE(reason, '')) LIKE 'ai %'")
                if not ownership:
                    return 0
                conditions = [
                    "exit_time IS NULL",
                    "order_id IS NOT NULL",
                    "TRIM(order_id) <> ''",
                    f"({' OR '.join(ownership)})",
                ]
                live_clause = _live_execution_clause(columns)
                if live_clause:
                    conditions.append(live_clause)
                params: list[Any] = []
                if asset_class and "asset_type" in columns:
                    conditions.append("LOWER(COALESCE(asset_type, '')) = ?")
                    params.append(str(asset_class).lower())
                source_column = next((name for name in ("exchange", "source", "broker") if name in columns), None)
                requested_source = _normalize_source(source)
                if requested_source:
                    if source_column is None:
                        return 0
                    conditions.append(
                        f"LOWER(REPLACE(REPLACE(REPLACE(COALESCE({source_column}, ''), '_', ''), '-', ''), ' ', '')) = ?"
                    )
                    params.append(requested_source)
                side_expression = "UPPER(COALESCE(side, 'LONG'))" if "side" in columns else "'LONG'"
                venue_expression = f"LOWER(COALESCE({source_column}, ''))" if source_column else "''"
                rows = connection.execute(
                    f"SELECT symbol, {side_expression} AS side_key, {venue_expression} AS venue_key "
                    f"FROM trade_log WHERE {' AND '.join(conditions)}",
                    tuple(params),
                ).fetchall()
            return len({
                (str(row["venue_key"]), str(row["symbol"]).upper(), str(row["side_key"]).upper())
                for row in rows if str(row["symbol"] or "").strip()
            })
        except (OSError, sqlite3.Error):
            return 0

    def scenario_snapshot(self, *, paper_records=None, currency: str = "") -> dict[str, Any]:
        """Reproduce the legacy three-policy scenario view from account data.

        This is a descriptive historical sensitivity check.  It never sends an
        order and never labels an absent sample as a successful simulation.
        """
        settings = load_settings(persist_migrations=False)
        policy = dict(settings.get("stock_auto_trading") or {})
        buy_threshold = _number(policy.get("buy_threshold", 70.0))
        sell_threshold = _number(policy.get("sell_threshold", 30.0))
        interval_seconds = int(_number(policy.get("interval_seconds") or 1800))
        max_positions = max(1, int(_number(policy.get("max_positions") or 3)))
        risk_guard = bool(policy.get("risk_guard_enabled", True))

        # Older profiles used 0~1 fractions while the current stock engine and
        # settings template use a 0~100 score.  Keep the stored unit and apply a
        # 10-point/0.10 sensitivity accordingly.  A higher BUY threshold is the
        # conservative case because it requires a stronger score to enter.
        threshold_scale = 100.0 if max(abs(buy_threshold), abs(sell_threshold)) > 1.0 else 1.0
        threshold_step = 10.0 if threshold_scale == 100.0 else 0.10
        conservative_buy = min(threshold_scale, buy_threshold + threshold_step)
        aggressive_buy = max(0.0, buy_threshold - threshold_step)

        definitions = (
            ("conservative", "보수적", 0.7, "#3b82f6", conservative_buy, max(1, max_positions - 1), True),
            ("current", "현재 정책", 1.0, "#22c55e", buy_threshold, max_positions, risk_guard),
            ("aggressive", "공격적", 1.3, "#ef4444", aggressive_buy, max_positions + 1, False),
        )

        from web_platform.asset_insight_data import load_live_history_evidence
        scopes: dict[str, Any] = {}
        available_currencies: set[str] = set()
        for scope, asset_class in (("all", None), ("crypto", "crypto"), ("stock", "stock")):
            history = load_live_history_evidence(self.db_path, asset_class=asset_class, currency=currency)
            available_currencies.update(history["available_currencies"])
            loaded = load_closed_trade_records(self.db_path, asset_class=asset_class, limit=200, confirmed_only=True)
            rows = ([row for row in paper_records if asset_class is None or row.get("asset_class") == asset_class] if paper_records is not None else list(loaded.get("records") or []))
            available_currencies.update(str(row.get("currency") or "").upper() for row in rows if row.get("currency"))
            if currency:
                rows = [row for row in rows if str(row.get("currency") or "").upper() == currency.upper()]
            currencies = sorted({str(row.get("currency") or "").upper() for row in rows if str(row.get("currency") or "").strip()})
            currency_mixed = len(currencies) > 1
            scenarios = []
            for key, label, ratio, color, adjusted_buy, positions, guard in (() if currency_mixed else definitions):
                cumulative = 0.0
                peak = 0.0
                max_drawdown = 0.0
                pnl_values = [_number(row.get("pnl")) * ratio for row in reversed(rows)]
                for pnl in pnl_values:
                    cumulative += pnl
                    peak = max(peak, cumulative)
                    max_drawdown = max(max_drawdown, peak - cumulative)
                total_pnl = sum(pnl_values)
                wins = sum(1 for pnl in pnl_values if pnl > 0)
                scenarios.append({
                    "key": key,
                    "name": label,
                    "description": (
                        f"기록된 순손익 × {ratio:.1f} · 주문/진입 조건 재시뮬레이션 아님"
                    ),
                    "color": color,
                    "position_ratio": ratio,
                    "total": len(rows),
                    "wins": wins,
                    "win_rate": round((wins / len(rows) * 100.0), 2) if rows else 0.0,
                    "total_pnl": round(total_pnl, 8),
                    "avg_pnl": round(total_pnl / len(rows), 8) if rows else 0.0,
                    "max_drawdown": round(max_drawdown, 8),
                    "currency": currencies[0] if len(currencies) == 1 else "",
                })
            scopes[scope] = {
                "asset_class": asset_class or "all",
                "live_history_evidence": history,
                "sample_count": len(rows),
                "currencies": currencies,
                "currency_mixed": currency_mixed,
                "schema_compatible": bool(loaded.get("schema_compatible")),
                "error": str(loaded.get("error") or ""),
                "scenarios": scenarios,
            }
        return {
            "execution_mode": "paper" if paper_records is not None else "live",
            "policy_source": "stock_auto_trading",
            "available_currencies": sorted(available_currencies),
            "filter_currency": currency.upper(),
            "calculation_basis": "과거 순손익 배율 0.7/1.0/1.3 민감도 · 전략 재실행/백테스트 아님",
            "trade_source": "closed_trade_records",
            "read_only": True,
            "policy": {
                "buy_threshold": buy_threshold,
                "sell_threshold": sell_threshold,
                "interval_minutes": max(1, interval_seconds // 60),
                "max_positions": max_positions,
                "risk_guard_enabled": risk_guard,
                "threshold_scale": threshold_scale,
            },
            "scopes": scopes,
        }

    def trading_statistics(
        self,
        *,
        asset_class: str,
        source: str = "",
        period: str = "all",
        custom_start: str = "",
        custom_end: str = "",
        baseline_at: str = "",
    ) -> dict[str, Any]:
        """Return the legacy trade-statistics contract without cross-venue relabeling.

        The general statistics tab starts account-wide.  A source is applied only
        after the user explicitly chooses the legacy exchange/broker filter.
        Blank legacy crypto rows belong only to the historical Binance group;
        they are never copied into another exchange.
        """
        requested_source = _normalize_source(source)
        groups: dict[str, dict[str, Any]] = {}
        all_hold_total = 0.0
        all_hold_count = 0
        pnl_by_currency: dict[str, float] = {}
        gross_pnl_by_currency: dict[str, float] = {}
        fee_by_currency: dict[str, float] = {}
        notional_by_currency: dict[str, float] = {}
        wins = 0
        reconciled_closed_count = 0
        closed_count = 0
        query_error = ""
        schema_compatible = False
        normalized_period = "all"
        start_epoch: float | None = None
        end_epoch = datetime.now().timestamp()
        try:
            normalized_period, start_epoch, end_epoch = _statistics_time_range(
                period,
                custom_start=custom_start,
                custom_end=custom_end,
                baseline_at=baseline_at,
            )
            with closing(self._connect()) as connection:
                columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(trade_log)").fetchall()}
                if not {"symbol", "pnl", "entry_time", "exit_time"}.issubset(columns):
                    raise sqlite3.OperationalError("trade_log_schema_missing")
                exchange_expression = "exchange" if "exchange" in columns else "NULL"
                asset_expression = "asset_type" if "asset_type" in columns else "NULL"
                pnl_percent_expression = "pnl_percent" if "pnl_percent" in columns else "0"
                fees_expression = "fees" if "fees" in columns else "0"
                raw_net_pnl_expression = "COALESCE(net_pnl, pnl)" if "net_pnl" in columns else "pnl"
                gross_pnl_expression = "gross_pnl" if "gross_pnl" in columns else "NULL"
                reconciliation_expression = "reconciliation_status" if "reconciliation_status" in columns else "'legacy_unverified'"
                pnl_source_expression = "pnl_source" if "pnl_source" in columns else "'legacy_unverified'"
                confirmed_net_statuses = (
                    "'exchange_confirmed','exchange_confirmed_partial',"
                    "'broker_order_linked','exact_fill_price_no_provider_pnl'"
                )
                confirmed_net_expression = (
                    f"CASE WHEN {reconciliation_expression} IN ({confirmed_net_statuses}) "
                    f"THEN {raw_net_pnl_expression} ELSE NULL END"
                )
                provider_gross_expression = (
                    f"CASE WHEN {pnl_source_expression} IN ('exchange_realized_pnl','broker_lot_accounting','exchange_uniform_close_lot') "
                    f"THEN {gross_pnl_expression} ELSE NULL END"
                )
                if "entry_amount" in columns:
                    notional_expression = "ABS(COALESCE(entry_amount, 0))"
                elif {"entry_price", "quantity"}.issubset(columns):
                    notional_expression = "ABS(COALESCE(entry_price, 0) * COALESCE(quantity, 0))"
                elif "amount" in columns:
                    notional_expression = "ABS(COALESCE(amount, 0))"
                else:
                    notional_expression = "0"
                where = ["exit_time IS NOT NULL"]
                params: list[Any] = []
                live_clause = _live_execution_clause(columns)
                if live_clause:
                    where.append(live_clause)
                if start_epoch is not None:
                    where.append("noah_epoch(exit_time) >= ?")
                    params.append(start_epoch)
                where.append("noah_epoch(exit_time) <= ?")
                params.append(end_epoch)
                if "reason" in columns:
                    where.append("LOWER(COALESCE(reason, '')) != 'binance_import'")
                    where.append("LOWER(COALESCE(reason, '')) != 'stock_trade_sync'")
                if "position_owner" in columns:
                    where.append("LOWER(COALESCE(position_owner, 'legacy_unknown')) NOT IN ('manual', 'external')")
                aggregate_rows = connection.execute(
                    f"""
                    SELECT symbol, {exchange_expression} AS exchange_name, {asset_expression} AS asset_name,
                           COUNT(*) AS total_trades,
                           SUM(CASE WHEN {confirmed_net_expression} > 0 THEN 1 ELSE 0 END) AS winning_trades,
                           SUM(CASE WHEN {confirmed_net_expression} < 0 THEN 1 ELSE 0 END) AS losing_trades,
                           SUM(CASE WHEN {confirmed_net_expression} IS NOT NULL THEN COALESCE({pnl_percent_expression}, 0) ELSE 0 END) AS pnl_percent_sum,
                           SUM(COALESCE({confirmed_net_expression}, 0)) AS total_pnl,
                           SUM(CASE WHEN {provider_gross_expression} IS NOT NULL THEN {provider_gross_expression} ELSE 0 END) AS gross_pnl,
                           SUM(CASE WHEN {provider_gross_expression} IS NOT NULL THEN 1 ELSE 0 END) AS gross_pnl_count,
                           SUM(COALESCE({fees_expression}, 0)) AS total_fees,
                           SUM({notional_expression}) AS total_notional,
                           MAX({confirmed_net_expression}) AS max_profit,
                           MIN({confirmed_net_expression}) AS max_loss,
                           SUM(CASE WHEN {confirmed_net_expression} IS NOT NULL THEN 1 ELSE 0 END) AS reconciled_count,
                           SUM(CASE WHEN julianday(exit_time) > julianday(entry_time)
                                    THEN (julianday(exit_time) - julianday(entry_time)) * 1440.0 ELSE 0 END) AS hold_total,
                           SUM(CASE WHEN julianday(exit_time) > julianday(entry_time) THEN 1 ELSE 0 END) AS hold_count
                    FROM trade_log
                    WHERE {' AND '.join(where)}
                    GROUP BY symbol, {exchange_expression}, {asset_expression}
                    """,
                    tuple(params),
                ).fetchall()
            schema_compatible = True
            for row in aggregate_rows:
                classified = _classify_trade(row["symbol"], row["exchange_name"], row["asset_name"])
                if classified != asset_class:
                    continue
                raw_source = _normalize_source(row["exchange_name"])
                if requested_source and raw_source != requested_source:
                    continue
                source_key = raw_source or "unscoped"
                currency = _trade_currency(row["symbol"], row["exchange_name"], classified)
                total = int(row["total_trades"] or 0)
                row_wins = int(row["winning_trades"] or 0)
                row_reconciled = int(row["reconciled_count"] or 0)
                pnl = _number(row["total_pnl"])
                gross_pnl = _number(row["gross_pnl"])
                gross_pnl_count = int(row["gross_pnl_count"] or 0)
                fees = _number(row["total_fees"])
                notional = abs(_number(row["total_notional"]))
                hold_total = _number(row["hold_total"])
                hold_count = int(row["hold_count"] or 0)
                attributed = bool(raw_source)
                if attributed:
                    closed_count += total
                    wins += row_wins
                    reconciled_closed_count += row_reconciled
                    all_hold_total += hold_total
                    all_hold_count += hold_count
                    if row_reconciled:
                        pnl_by_currency[currency] = pnl_by_currency.get(currency, 0.0) + pnl
                    if gross_pnl_count:
                        gross_pnl_by_currency[currency] = gross_pnl_by_currency.get(currency, 0.0) + gross_pnl
                    fee_by_currency[currency] = fee_by_currency.get(currency, 0.0) + fees
                    notional_by_currency[currency] = notional_by_currency.get(currency, 0.0) + notional
                group = groups.setdefault(source_key, {
                    "source": source_key,
                    "label": "LEGACY" if source_key == "unscoped" else source_key.upper(),
                    "attribution_status": "legacy_source_unconfirmed" if source_key == "unscoped" else "venue_confirmed",
                    "currency": currency,
                    "closed_count": 0, "total_pnl": 0.0, "total_fees": 0.0,
                    "gross_pnl": 0.0, "gross_pnl_count": 0, "reconciled_count": 0,
                    "unresolved_count": 0,
                    "total_notional": 0.0, "hold_total": 0.0, "hold_count": 0, "rows": [],
                })
                group["closed_count"] += total
                group["total_pnl"] += pnl
                group["gross_pnl"] += gross_pnl
                group["gross_pnl_count"] += gross_pnl_count
                group["reconciled_count"] += row_reconciled
                group["unresolved_count"] += max(0, total - row_reconciled)
                group["total_fees"] += fees
                group["total_notional"] += notional
                group["hold_total"] += hold_total
                group["hold_count"] += hold_count
                group["rows"].append({
                    "symbol": str(row["symbol"] or "UNKNOWN").upper(),
                    "total_trades": total,
                    "winning_trades": row_wins,
                    "losing_trades": int(row["losing_trades"] or 0),
                    "win_rate": round(row_wins / row_reconciled * 100.0, 2) if row_reconciled else None,
                    "avg_profit_rate": round(
                        _number(row["pnl_percent_sum"]) / row_reconciled, 4
                    ) if row_reconciled else None,
                    "total_pnl": pnl if row_reconciled else None,
                    "gross_pnl": gross_pnl if gross_pnl_count else None,
                    "gross_pnl_count": gross_pnl_count,
                    "reconciled_count": row_reconciled,
                    "unresolved_count": max(0, total - row_reconciled),
                    "reconciliation_status": (
                        "confirmed" if row_reconciled == total
                        else "partial" if row_reconciled > 0
                        else "unresolved"
                    ),
                    "total_fees": fees,
                    "max_profit": _number(row["max_profit"]) if row["max_profit"] is not None else None,
                    "max_loss": _number(row["max_loss"]) if row["max_loss"] is not None else None,
                })
        except (OSError, sqlite3.Error, ValueError) as exc:
            query_error = str(exc)

        rendered_groups: list[dict[str, Any]] = []
        for group in groups.values():
            rows = list(group["rows"])
            rows.sort(key=lambda row: (-int(row["total_trades"]), str(row["symbol"])))
            hold_total = float(group.pop("hold_total"))
            hold_count = int(group.pop("hold_count"))
            group["avg_hold_minutes"] = hold_total / hold_count if hold_count else None
            group["valid_hold_count"] = hold_count
            group["avg_fee"] = group["total_fees"] / group["closed_count"] if group["closed_count"] else 0.0
            group["fee_pnl_percent"] = group["total_fees"] / abs(group["total_pnl"]) * 100.0 if group["total_pnl"] else 0.0
            group["rows"] = rows
            rendered_groups.append(group)
        rendered_groups.sort(key=lambda group: str(group["label"]))

        execution = self._exchange_execution_summary(
            source=source,
            asset_class=asset_class,
            start_epoch=start_epoch,
            end_epoch=end_epoch,
        )
        execution_count = int(execution.get("count") or 0)
        execution_notional = dict(execution.get("notional_by_currency") or {})
        execution_rows = list(execution.get("rows") or [])

        return {
            "asset_class": asset_class,
            "filter_source": requested_source,
            "closed_count": closed_count,
            "execution_count": execution_count,
            # Never relabel NoahAI position closures as exchange-confirmed
            # fills when the external history is empty or unsupported.
            "display_trade_count": execution_count,
            "execution_history_available": bool(execution.get("history_available", True)),
            "execution_history_status": str(execution.get("history_status") or "available"),
            "execution_history_reason": str(execution.get("history_reason") or "available"),
            "reconciled_closed_count": reconciled_closed_count,
            "unresolved_closed_count": max(0, closed_count - reconciled_closed_count),
            "win_rate": round(wins / reconciled_closed_count * 100.0, 2) if reconciled_closed_count else 0.0,
            "pnl_by_currency": pnl_by_currency,
            "gross_pnl_by_currency": gross_pnl_by_currency,
            "exchange_pnl_reference": execution.get("pnl_reference", {}),
            "fees_by_currency": fee_by_currency,
            "notional_by_currency": execution_notional or notional_by_currency,
            "avg_hold_minutes": all_hold_total / all_hold_count if all_hold_count else None,
            "valid_hold_count": all_hold_count,
            "groups": rendered_groups,
            "execution_rows": execution_rows,
            "schema_compatible": schema_compatible,
            "error": query_error,
            "range": {
                "period": normalized_period,
                "started_at": datetime.fromtimestamp(start_epoch, tz=timezone.utc).isoformat() if start_epoch is not None else None,
                "ended_at": datetime.fromtimestamp(end_epoch, tz=timezone.utc).isoformat(),
                "baseline_at": str(baseline_at or "") or None,
                "baseline_applied": bool(str(baseline_at or "").strip()),
            },
            "ledger_authority": "trade_log",
            "execution_authority": "exchange_execution_log",
            "legacy_execution_modes_mapped_to_live": ["optimized", "manual"],
            "legacy_unattributed_count": sum(
                int(group.get("closed_count") or 0)
                for group in rendered_groups
                if group.get("attribution_status") == "legacy_source_unconfirmed"
            ),
        }

    def _exchange_execution_summary(
        self,
        *,
        source: str = "",
        asset_class: str = "",
        limit: int = 50,
        start_epoch: float | None = None,
        end_epoch: float | None = None,
    ) -> dict[str, Any]:
        """Mirror the legacy confirmed-execution summary without a 100-row cap."""
        result: dict[str, Any] = {
            "count": 0, "notional_by_currency": {}, "rows": [],
            "history_available": True, "history_reason": "available",
            "history_status": "available",
        }
        requested_source = _normalize_source(source)
        try:
            with closing(self._connect()) as connection:
                exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='exchange_execution_log'"
                ).fetchone()
                if not exists:
                    result.update(history_available=False, history_status="unsupported", history_reason="exchange_execution_ledger_missing")
                    return result
                columns = {
                    str(row[1])
                    for row in connection.execute("PRAGMA table_info(exchange_execution_log)").fetchall()
                }
                conditions = ["confirmation_status = 'confirmed'"] if "confirmation_status" in columns else []
                params: list[Any] = []
                time_column = "COALESCE(executed_at, created_at)" if {"executed_at", "created_at"}.issubset(columns) else (
                    "executed_at" if "executed_at" in columns else "created_at" if "created_at" in columns else ""
                )
                if start_epoch is not None and time_column:
                    conditions.append(f"noah_epoch({time_column}) >= ?")
                    params.append(start_epoch)
                if end_epoch is not None and time_column:
                    conditions.append(f"noah_epoch({time_column}) <= ?")
                    params.append(end_epoch)
                if requested_source:
                    conditions.append("LOWER(REPLACE(REPLACE(REPLACE(exchange, '_', ''), '-', ''), ' ', '')) = ?")
                    params.append(requested_source)
                elif asset_class in {"crypto", "stock"}:
                    supported_venues = CRYPTO_VENUES if asset_class == "crypto" else STOCK_VENUES
                    supported_sql = ",".join(f"'{item}'" for item in sorted(supported_venues))
                    conditions.append(
                        "LOWER(REPLACE(REPLACE(REPLACE(COALESCE(exchange, ''), '_', ''), '-', ''), ' ', '')) "
                        f"IN ({supported_sql})"
                    )
                where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
                grouped = connection.execute(
                    f"SELECT exchange, COUNT(*) AS row_count, SUM(COALESCE(cost, 0)) AS total_cost "
                    f"FROM exchange_execution_log{where} GROUP BY exchange",
                    tuple(params),
                ).fetchall()
                notional: dict[str, float] = {}
                for row in grouped:
                    venue = _normalize_source(row["exchange"])
                    currency = "KRW" if venue in STOCK_VENUES | {"upbit", "bithumb", "coinone"} else "USDT"
                    result["count"] += int(row["row_count"] or 0)
                    notional[currency] = notional.get(currency, 0.0) + _number(row["total_cost"])
                result["notional_by_currency"] = notional

                # This is the saved fill window, NOT the venue account's total
                # PnL. Never infer complete API coverage or funding inclusion.
                if {"symbol", "realized_pnl", "realized_pnl_present"}.issubset(columns):
                    pnl_groups = connection.execute(
                        f"SELECT exchange, symbol, COUNT(*) AS n, "
                        "SUM(CASE WHEN realized_pnl_present=1 THEN 1 ELSE 0 END) AS present, "
                        "SUM(CASE WHEN realized_pnl_present=1 THEN realized_pnl ELSE 0 END) AS gross "
                        f"FROM exchange_execution_log{where} GROUP BY exchange, symbol",
                        tuple(params),
                    ).fetchall()
                    raw_gross: dict[str, float] = {}
                    known_count = 0
                    for item in pnl_groups:
                        known = int(item['present'] or 0)
                        known_count += known
                        if known:
                            family = _classify_trade(item['symbol'], item['exchange'], None)
                            unit = _trade_currency(item['symbol'], item['exchange'], family)
                            raw_gross[unit] = raw_gross.get(unit, 0.0) + _number(item['gross'])
                    result['pnl_reference'] = {
                        'basis': 'stored_provider_fill_gross',
                        'gross_pnl_by_currency': raw_gross,
                        'pnl_present_count': known_count,
                        'pnl_missing_count': int(result['count']) - known_count,
                        'account_total_verified': False,
                        'coverage': 'stored_window_only',
                        'funding_included': False,
                        'fees_included': False,
                    }

                order_column = time_column or "id"
                rows = connection.execute(
                    f"SELECT * FROM exchange_execution_log{where} ORDER BY {order_column} DESC, id DESC LIMIT ?",
                    tuple(params + [max(1, min(int(limit), 100))]),
                ).fetchall()
                result["rows"] = [{str(key): row[key] for key in row.keys()} for row in rows]
                capability = self._execution_capability_status(connection, requested_source, int(result["count"]))
                result.update(capability)
        except (OSError, sqlite3.Error):
            return result
        return result

    def stock_trading_statistics(self, *, source: str = "") -> dict[str, Any]:
        """Read the legacy stock DB statistics as an eight-column broker contract.

        This is deliberately separate from crypto PnL statistics.  Missing broker
        data stays empty and can never inherit Binance/USDT values.
        """
        requested_source = _normalize_source(source)
        rows = self.table_rows("stock_trade_stats", limit=100, source=source)
        metrics = self.table_rows("stock_execution_metrics", limit=100, source=source)
        by_broker: dict[str, dict[str, Any]] = {}
        today = datetime.now().date().isoformat()
        # ``stock_trade_stats`` stores daily snapshots.  The former Web UI
        # summed every historical row, which duplicated ALL/STOCK/ETF rows and
        # inflated the broker totals each time the screen was opened.  Keep the
        # newest row for each broker/asset type; ``table_rows`` is already
        # ordered newest-first.
        latest_rows: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            broker = _normalize_source(row.get("broker"))
            if not broker or (requested_source and broker != requested_source):
                continue
            asset_type = str(row.get("asset_type") or "all").lower()
            latest_rows.setdefault((broker, asset_type), row)

        rows_by_broker: dict[str, list[dict[str, Any]]] = {}
        for (broker, _asset_type), row in latest_rows.items():
            rows_by_broker.setdefault(broker, []).append(row)

        for broker, broker_rows in rows_by_broker.items():
            aggregate = by_broker.setdefault(broker, {
                "broker": broker,
                "total_trades": 0,
                "buy_count": 0,
                "sell_count": 0,
                "today_count": 0,
                "open_orders_count": 0,
                "realized_pnl": 0.0,
                "winning_trades": 0,
                "losing_trades": 0,
                "weighted_avg_pnl": 0.0,
                "max_drawdown": 0.0,
                "details": [],
            })
            primary_rows = [row for row in broker_rows if str(row.get("asset_type") or "all").lower() == "all"]
            if not primary_rows:
                primary_rows = broker_rows
            for row in primary_rows:
                total = int(row.get("total_trades") or 0)
                aggregate["total_trades"] += total
                aggregate["buy_count"] += int(row.get("buy_count") or 0)
                aggregate["sell_count"] += int(row.get("sell_count") or 0)
                aggregate["winning_trades"] += int(row.get("winning_trades") or 0)
                aggregate["losing_trades"] += int(row.get("losing_trades") or 0)
                aggregate["realized_pnl"] += _number(row.get("realized_pnl"))
                aggregate["weighted_avg_pnl"] += _number(row.get("avg_pnl")) * total
                aggregate["max_drawdown"] = min(aggregate["max_drawdown"], _number(row.get("max_drawdown")))
                if str(row.get("stat_date") or "")[:10] == today:
                    aggregate["today_count"] += total
            for row in broker_rows:
                aggregate["details"].append({
                    "asset_type": str(row.get("asset_type") or "all").upper(),
                    "total_trades": int(row.get("total_trades") or 0),
                    "buy_count": int(row.get("buy_count") or 0),
                    "sell_count": int(row.get("sell_count") or 0),
                    "realized_pnl": _number(row.get("realized_pnl")),
                    "win_rate": _number(row.get("win_rate")),
                    "avg_pnl": _number(row.get("avg_pnl")),
                    "max_drawdown": _number(row.get("max_drawdown")),
                })

        metric_groups: dict[str, list[dict[str, Any]]] = {}
        for row in metrics:
            broker = _normalize_source(row.get("broker"))
            if broker and (not requested_source or broker == requested_source):
                metric_groups.setdefault(broker, []).append(row)
        for broker, broker_metrics in metric_groups.items():
            aggregate = by_broker.setdefault(broker, {
                "broker": broker, "total_trades": 0, "buy_count": 0, "sell_count": 0,
                "today_count": 0, "open_orders_count": 0, "realized_pnl": 0.0,
                "winning_trades": 0, "losing_trades": 0, "weighted_avg_pnl": 0.0,
                "max_drawdown": 0.0, "details": [],
            })
            total = len(broker_metrics)
            success = sum(1 for row in broker_metrics if bool(row.get("success")))
            latency = [_number(row.get("latency_ms")) for row in broker_metrics if row.get("latency_ms") is not None]
            slippage = [_number(row.get("slippage_bps")) for row in broker_metrics if row.get("slippage_bps") is not None]
            aggregate["execution_quality"] = {
                "order_count": total,
                "success_rate": round(success / total * 100.0, 2) if total else 0.0,
                "avg_latency_ms": sum(latency) / len(latency) if latency else 0.0,
                "avg_slippage_bps": sum(slippage) / len(slippage) if slippage else 0.0,
            }

        rendered = []
        for aggregate in by_broker.values():
            total = int(aggregate["total_trades"])
            aggregate["win_rate"] = (
                round(aggregate["winning_trades"] / total * 100.0, 2) if total else 0.0
            )
            aggregate["avg_pnl"] = aggregate.pop("weighted_avg_pnl") / total if total else 0.0
            aggregate["details"].sort(key=lambda row: str(row["asset_type"]))
            rendered.append(aggregate)
        rendered.sort(key=lambda row: str(row["broker"]))
        return {
            "asset_class": "stock",
            "filter_source": requested_source,
            "brokers": rendered,
            "data_source": "stock_trade_stats",
            "period_days": 30,
            "cross_service_data_included": False,
        }

    def portfolio_snapshot(self) -> dict[str, Any]:
        settings = load_settings(persist_migrations=False)
        history = load_trade_history_metrics(self.db_path)
        saved = settings.get("asset_insight_snapshot") if isinstance(settings, dict) else {}
        return {
            "saved_snapshot": saved if isinstance(saved, dict) else {},
            "history": history,
            "fresh_balance_available": False,
            "freshness_reason": "runtime_balance_bridge_required",
        }

    @staticmethod
    def _recent_json_array_page(
        path: Path, *, offset: int, limit: int,
    ) -> tuple[list[Any], bool, int | None, list[Any] | None]:
        """Read a recent page without materialising a very large JSON array.

        Exchange learning files are atomically written with ``indent=2``.  For
        normal files a full decode keeps the exact legacy summary.  Historical
        accounts can have 100-200 MB pre-retention files, so those use a
        reverse tail read and only decode the requested top-level objects.
        """
        size = path.stat().st_size
        if size <= AccountQueryService.LARGE_LEARNING_FILE_BYTES:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                records = payload.get("data") or payload.get("records") or payload.get("patterns") or []
            else:
                records = payload
            safe = list(records or []) if isinstance(records, list) else []
            end = max(0, len(safe) - offset)
            start = max(0, end - limit)
            return safe[start:end], start > 0, len(safe), safe

        target = offset + limit + 1
        chunk_size = 1024 * 1024
        buffered = b""
        cursor = size
        positions: list[int] = []
        with path.open("rb") as handle:
            while cursor > 0:
                take = min(chunk_size, cursor)
                cursor -= take
                handle.seek(cursor)
                buffered = handle.read(take) + buffered
                positions = [match.start() + 2 for match in re.finditer(rb"(?m)^  \{", buffered)]
                if len(positions) >= target:
                    break

        if not positions:
            # Non-standard/compact legacy JSON is uncommon.  Preserve
            # compatibility rather than returning a false empty result.
            payload = json.loads(path.read_text(encoding="utf-8"))
            records = payload if isinstance(payload, list) else []
            end = max(0, len(records) - offset)
            start = max(0, end - limit)
            safe_records = list(records)
            return safe_records[start:end], start > 0, len(safe_records), safe_records

        chosen = positions[max(0, len(positions) - target)]
        snippet = buffered[chosen:]
        array_end = snippet.rfind(b"]")
        if array_end < 0:
            raise ValueError("learning_json_array_end_missing")
        decoded = json.loads(b"[" + snippet[:array_end].rstrip().rstrip(b",") + b"]")
        end = max(0, len(decoded) - offset)
        start = max(0, end - limit)

        # Decode only the recent page. The full total is a separate structural
        # count cached by path revision; no historical record dictionaries are
        # materialised merely to display the total.
        stat = path.stat()
        total_count = _count_pretty_json_array_records(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        has_more = (total_count > offset + limit) if total_count is not None else len(decoded) > offset + limit
        return list(decoded[start:end]), has_more, total_count, None

    def learning_snapshot(self, *, source: str = "", offset: int = 0, limit: int = 50) -> dict[str, Any]:
        normalized_source = _normalize_source(source)
        safe_offset = max(0, int(offset))
        safe_limit = max(10, min(int(limit), 200))
        if normalized_source in STOCK_SOURCES:
            return self._stock_learning_snapshot(normalized_source, safe_offset, safe_limit)
        source_path = (
            get_exchange_ai_learning_data_path(normalized_source)
            if normalized_source in CRYPTO_SOURCES
            else get_ai_learning_data_path()
        )
        path = Path(source_path)
        public_source = str(path)
        compact_path = path.parent / 'learning.sqlite3'
        if not path.exists() and not compact_path.exists():
            return {"records": [], "source": public_source, "status": "empty"}
        try:
            if compact_path.exists():
                from trading.learning_storage import LearningStore
                store = LearningStore(path.parent,initialize=False)
                known_total = store.count(normalized_source)
                if known_total or not path.exists():
                    page_records = store.recent(normalized_source, safe_limit, safe_offset)
                    has_more = safe_offset + len(page_records) < known_total
                    complete_records = None
                    public_source = str(compact_path)
                else:
                    page_records, has_more, known_total, complete_records = self._recent_json_array_page(
                        path, offset=safe_offset, limit=safe_limit,
                    )
            else:
                page_records, has_more, known_total, complete_records = self._recent_json_array_page(
                    path, offset=safe_offset, limit=safe_limit,
                )
        except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error):
            return {"records": [], "source": public_source, "status": "invalid"}
        safe_records = list(page_records)
        summary_records = list(complete_records) if complete_records is not None else safe_records
        if normalized_source:
            safe_records = [
                row for row in safe_records
                if isinstance(row, dict)
                and _normalize_source(row.get("exchange") or row.get("source") or row.get("broker")) == normalized_source
            ]
            summary_records = [
                row for row in summary_records
                if isinstance(row, dict)
                and _normalize_source(row.get("exchange") or row.get("source") or row.get("broker")) == normalized_source
            ]
            if complete_records is not None:
                end = max(0, len(summary_records) - safe_offset)
                start = max(0, end - safe_limit)
                safe_records = summary_records[start:end]
                has_more = start > 0
                known_total = len(summary_records)
        local_now = datetime.now().astimezone()
        today = local_now.date()
        week_start = today - timedelta(days=6)
        signal_counts = {"LONG": 0, "SHORT": 0, "HOLD": 0}
        confidence_values: list[float] = []
        today_count = 0
        weekly_count = 0

        def local_record_date(row: dict[str, Any]):
            raw = row.get("timestamp") or row.get("created_at") or row.get("time")
            try:
                parsed = datetime.fromisoformat(str(raw or "").replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone().date()
            except (TypeError, ValueError):
                return None

        def normalize_learning_records(records: list[Any], *, collect_summary: bool) -> list[dict[str, Any]]:
            from trading.indicator_evidence import indicator_snapshot
            normalized: list[dict[str, Any]] = []
            for raw in records:
                if not isinstance(raw, dict):
                    continue
                row = dict(raw)
                row.update(indicator_snapshot(row))
                normalized.append(row)
                if not collect_summary:
                    continue
                signal = str(row.get("signal") or row.get("decision") or "HOLD").upper()
                if signal in signal_counts:
                    signal_counts[signal] += 1
                try:
                    confidence_values.append(float(row.get("confidence", row.get("score", 0)) or 0))
                except (TypeError, ValueError):
                    pass
                record_date = local_record_date(row)
                nonlocal_today_week[0] += int(record_date == today)
                nonlocal_today_week[1] += int(record_date is not None and week_start <= record_date <= today)
            return normalized

        nonlocal_today_week = [0, 0]
        normalized_records = normalize_learning_records(safe_records, collect_summary=False)
        normalize_learning_records(summary_records, collect_summary=True)
        today_count, weekly_count = nonlocal_today_week
        displayed_total = len(summary_records) if complete_records is not None else known_total

        return {
            "records": normalized_records,
            "source": public_source,
            "status": "ok" if normalized_records else "empty",
            "summary": {
                "total_count": displayed_total if displayed_total is not None else safe_offset + len(normalized_records),
                "today_count": today_count,
                "weekly_count": weekly_count,
                "signal_counts": signal_counts,
                "average_confidence": (
                    sum(confidence_values) / len(confidence_values)
                    if confidence_values else 0.0
                ),
                "complete": complete_records is not None,
            },
            "pagination": {
                "offset": safe_offset,
                "limit": safe_limit,
                "returned": len(normalized_records),
                "has_more": bool(has_more),
                "total_count": known_total,
            },
            "data_scope": {
                "mode": "source_strict" if normalized_source else "account",
                "source": normalized_source,
                "unscoped_records_included": not bool(normalized_source),
            },
        }

    def _stock_learning_snapshot(self, source: str, offset: int, limit: int) -> dict[str, Any]:
        """Read broker-owned stock/ETF analysis and auto-decision evidence.

        Stock analysis is persisted in ai_decisions, not crypto learning JSON.
        Historical payloads without an explicit broker remain unattributed.
        """
        payload = {"records": [], "source": f"{self.db_path} · ai_decisions · {source}",
                   "status": "empty", "data_scope": {"mode": "source_strict", "source": source,
                   "unscoped_records_included": False}}
        try:
            with closing(self._connect()) as connection:
                connection.create_function("noah_source", 1, _normalize_source, deterministic=True)
                document = "CASE WHEN json_valid(decision_json) THEN decision_json ELSE '{}' END"
                owner = f"noah_source(COALESCE(json_extract({document}, '$.broker'), json_extract({document}, '$.exchange'), ''))"
                decision_types = "('stock_analyze_symbol','stock_auto_trade_symbol','stock_auto_exit_symbol')"
                where = f"decision_type IN {decision_types} AND {owner} = ?"
                params = (source,)
                columns = {row[1] for row in connection.execute('PRAGMA table_info(ai_decisions)')}
                if 'exchange' in columns:
                    # Preserve not-yet-migrated rows, without parsing every crypto
                    # decision. The type/venue index scopes the legacy fallback.
                    where = f"decision_type IN {decision_types} AND (exchange = ? OR (exchange IS NULL AND {owner} = ?))"
                    params = (source,source)
                def selected(column: str, fallback: str = 'NULL') -> str:
                    return column if column in columns else fallback
                total = connection.execute(f"SELECT COUNT(*) FROM ai_decisions WHERE {where}", params).fetchone()[0]
                event_total = connection.execute(
                    f"SELECT COALESCE(SUM({selected('repeat_count','1')}),0) FROM ai_decisions WHERE {where}", params,
                ).fetchone()[0]
                rows = connection.execute(
                    f"""SELECT id,symbol,created_at,decision_type,decision_json,
                        {selected('execution_mode')} AS execution_mode,
                        {selected('asset_class')} AS asset_class,
                        {selected('instrument_type')} AS instrument_type,
                        {selected('decision_status')} AS decision_status,
                        {selected('reason_code')} AS reason_code,
                        {selected('actual_order')} AS actual_order,
                        {selected('order_id')} AS order_id,
                        {selected('repeat_count','1')} AS repeat_count
                        FROM ai_decisions WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?""",
                    (*params, limit, offset),
                ).fetchall()
                summary_rows = connection.execute(
                    f"""SELECT created_at,json_extract({document}, '$.confidence') AS confidence,
                        COALESCE(json_extract({document}, '$.signal'),json_extract({document}, '$.action'),
                                 {selected('decision_status')}) AS signal,
                        {selected('repeat_count','1')} AS repeat_count
                        FROM ai_decisions WHERE {where} ORDER BY id DESC LIMIT 10000""",
                    params,
                )
                today = datetime.now().astimezone().date()
                counts = {"LONG": 0, "SHORT": 0, "HOLD": 0}
                today_count = weekly_count = confidence_count = 0
                confidence_total = 0.0
                for row in summary_rows:
                    # SQLite CURRENT_TIMESTAMP in ai_decisions is UTC even
                    # though its serialized value has no timezone suffix.
                    epoch = self._epoch_seconds(row["created_at"])
                    day = datetime.fromtimestamp(epoch).date() if epoch is not None else None
                    weight = max(1, int(row["repeat_count"] or 1))
                    today_count += weight * int(day == today)
                    weekly_count += weight * int(day is not None and today - timedelta(days=6) <= day <= today)
                    signal = str(row["signal"] or "").upper()
                    normalized_signal = 'LONG' if signal in {'BUY','LONG'} else 'SHORT' if signal in {'SELL','SHORT'} else 'HOLD' if signal in {'HOLD','SKIP','OBSERVED'} else ''
                    if normalized_signal:
                        counts[normalized_signal] += weight
                    if row["confidence"] is not None:
                        confidence_total += _number(row["confidence"]) * weight
                        confidence_count += weight
            records = []
            from trading.indicator_evidence import indicator_snapshot
            for row in reversed(rows):
                decision = _safe_json(row["decision_json"])
                decision = decision if isinstance(decision, dict) else {}
                signal = decision.get("signal") or decision.get("action") or row["decision_status"] or "기록 없음"
                xai = decision.get('xai_contract') if isinstance(decision.get('xai_contract'),dict) else {}
                records.append({"id": row["id"], "symbol": row["symbol"], "timestamp": row["created_at"],
                                "exchange": source, "signal": signal,
                                "confidence": decision.get("confidence"),
                                "reasoning": decision.get("reasoning") or xai.get('why') or decision.get('reason'),
                                "decision_type": row["decision_type"],
                                "execution_mode": row["execution_mode"] or decision.get('execution_mode') or 'unknown',
                                "asset_class": row["asset_class"] or decision.get('asset_class') or 'securities',
                                "instrument_type": row["instrument_type"] or decision.get('instrument_type') or ('etf' if decision.get('is_etf') is True else 'stock' if decision.get('is_etf') is False else 'unknown'),
                                "decision_status": row["decision_status"] or decision.get('decision_status'),
                                "reason_code": row["reason_code"] or decision.get('reason_code') or 'unknown',
                                "actual_order": row["actual_order"] if row["actual_order"] is not None else decision.get('actual_order'),
                                "order_id": row["order_id"] or decision.get('order_id'),
                                "repeat_count": max(1,int(row["repeat_count"] or 1)),
                                "market": decision.get("market"),
                                **indicator_snapshot(decision)})
            payload.update({"records": records, "status": "ok" if records else "empty",
                            "summary": {"total_count": int(event_total or 0), "stored_row_count": total, "today_count": today_count, "weekly_count": weekly_count,
                                        "signal_counts": counts, "average_confidence": confidence_total / confidence_count if confidence_count else None,
                                        "complete": total <= 10000, "sample_count": min(total,10000)},
                            "pagination": {"offset": offset, "limit": limit, "returned": len(records),
                                           "has_more": offset + len(records) < total, "total_count": total}})
        except (OSError, sqlite3.Error) as exc:
            payload.update({"status": "unavailable", "error": type(exc).__name__})
        return payload

    @staticmethod
    def _epoch_seconds(value: Any) -> int | None:
        try:
            if isinstance(value, (int, float)):
                raw = float(value)
                return int(raw / 1000 if raw > 10_000_000_000 else raw)
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
            return int(parsed.replace(tzinfo=timezone.utc).timestamp() if parsed.tzinfo is None else parsed.timestamp())
        except (TypeError, ValueError):
            return None

    def chart_markers(self, *, symbol: str, source: str) -> list[dict[str, Any]]:
        normalized_symbol = str(symbol or "").upper().replace("/", "").replace("-", "").replace("_", "")
        venue = str(source or "").lower()
        markers: list[dict[str, Any]] = []
        for row in self.table_rows("trade_log", limit=200, source=venue):
            row_symbol = str(row.get("symbol") or "").upper().replace("/", "").replace("-", "").replace("_", "")
            if row_symbol != normalized_symbol:
                continue
            side = str(row.get("side") or "").upper()
            entry = self._epoch_seconds(row.get("entry_time"))
            if entry:
                markers.append({"time": entry, "position": "belowBar" if side in {"LONG", "BUY"} else "aboveBar", "color": "#22c55e" if side in {"LONG", "BUY"} else "#f97316", "shape": "arrowUp" if side in {"LONG", "BUY"} else "arrowDown", "text": f"{side or 'ENTRY'} 진입", "kind": "entry"})
            closed = self._epoch_seconds(row.get("exit_time"))
            if closed:
                pnl = _number(row.get("pnl"))
                markers.append({"time": closed, "position": "aboveBar" if pnl >= 0 else "belowBar", "color": "#38bdf8" if pnl >= 0 else "#ef4444", "shape": "circle", "text": f"청산 PnL {pnl:.4g}", "kind": "exit"})
        for row in self.table_rows("ai_decisions", limit=100, source=venue):
            row_symbol = str(row.get("symbol") or "").upper().replace("/", "").replace("-", "").replace("_", "")
            if row_symbol != normalized_symbol:
                continue
            at = self._epoch_seconds(row.get("timestamp") or row.get("created_at"))
            if at:
                signal = str(row.get("signal") or row.get("decision") or "AI").upper()
                markers.append({"time": at, "position": "aboveBar", "color": "#a78bfa", "shape": "square", "text": f"XAI {signal}"[:80], "kind": "xai"})
        return sorted(markers, key=lambda item: int(item["time"]))[-300:]

    def workspace(
        self,
        service: str,
        feature: str,
        *,
        source: str = "",
        learning_offset: int = 0,
        learning_limit: int = 50,
        report_period: str = "today",
        report_offset: int = 0,
        report_limit: int = 100,
        statistics_period: str = "all",
        statistics_start: str = "",
        statistics_end: str = "",
        statistics_baseline_at: str = "",
    ) -> dict[str, Any]:
        service_key = str(service or "").strip().lower()
        feature_key = str(feature or "").strip().lower()
        source_scope = _normalize_source(source) if service_key in {"blockchain", "stock"} else ""
        if source_scope:
            service_sources = CRYPTO_SOURCES if service_key == "blockchain" else STOCK_SOURCES
            if source_scope not in service_sources:
                raise ValueError("workspace_source_service_mismatch")
        payload: dict[str, Any] = {
            "schema_version": "1.0.0", "service": service_key, "feature": feature_key,
            "source": source_scope, "captured_at": _now(),
            "freshness": "account_store",
        }
        if service_key == "portfolio":
            payload["portfolio"] = self.portfolio_snapshot()
            if "risk" in feature_key:
                payload["risk"] = self.table_rows("risk_log")
            if "performance" in feature_key:
                payload["statistics"] = self.table_rows("performance_stats")
            return payload
        if service_key == "ai_analyst":
            # 레거시 AI 애널리스트는 특정 거래소의 코인 화면이 아니라 계정의
            # 전체 종료 거래와 AI 판단/분석/위험 기록을 종합한다.  일반 crypto
            # 분기로 흘려 Binance 데이터만 보이게 하지 않는다.
            payload["trading"] = self.trading_overview(asset_class=None)
            payload["ai_decisions"] = self.table_rows("ai_decisions")
            payload["ai_analysis"] = self.table_rows("ai_trade_analysis")
            payload["analysis_log"] = self.table_rows("analysis_log")
            payload["risk"] = self.table_rows("risk_log")
            if "scenario" in feature_key:
                payload["scenario"] = self.scenario_snapshot()
            payload["data_scope"] = {
                "mode": "account_all_assets",
                "unscoped_records_included": True,
            }
            return payload
        # Every blockchain/stock screen is rendered in the currently selected
        # exchange/broker context.  Applying scope only to the dedicated source
        # tab allowed statistics, candidates and reports from other venues to
        # leak into otherwise source-specific screens.
        if service_key == "stock":
            payload["trading"] = self.trading_overview(
                asset_class="stock", source=source_scope, period=statistics_period,
                custom_start=statistics_start, custom_end=statistics_end,
                baseline_at=statistics_baseline_at,
            )
            if "statistics" in feature_key or "source_workspaces" in feature_key:
                payload["period_statistics"] = self.trading_statistics(
                    asset_class="stock", source=source_scope, period=statistics_period,
                    custom_start=statistics_start, custom_end=statistics_end,
                    baseline_at=statistics_baseline_at,
                )
                payload["stock_trading_statistics"] = self.stock_trading_statistics(source=source_scope)
            payload["statistics"] = self.table_rows("stock_trade_stats", source=source_scope)
            payload["execution"] = self.table_rows("stock_execution_metrics", source=source_scope)
        else:
            payload["trading"] = self.trading_overview(
                asset_class="crypto", source=source_scope, period=statistics_period,
                custom_start=statistics_start, custom_end=statistics_end,
                baseline_at=statistics_baseline_at,
            )
            if "statistics" in feature_key or "source_workspaces" in feature_key:
                payload["trading_statistics"] = self.trading_statistics(
                    asset_class="crypto", source=source_scope, period=statistics_period,
                    custom_start=statistics_start, custom_end=statistics_end,
                    baseline_at=statistics_baseline_at,
                )
            payload["statistics"] = self.table_rows("exchange_trade_stats", source=source_scope)
            payload["execution"] = self.table_rows("exchange_execution_log", source=source_scope)
        payload["statistics_view"] = {
            "period": statistics_period,
            "custom_start": statistics_start or None,
            "custom_end": statistics_end or None,
            "baseline_at": statistics_baseline_at or None,
            "records_deleted": False,
        }
        if "ai_reports" in feature_key:
            payload["report_periods"] = self.report_period_metrics(
                asset_class="stock" if service_key == "stock" else "crypto",
                source=source_scope,
                detail_period=report_period,
                detail_offset=report_offset,
                detail_limit=report_limit,
                baseline_at=statistics_baseline_at,
            )
        if source_scope:
            payload["data_scope"] = {
                "mode": "source_strict",
                "source": _normalize_source(source_scope),
                "unscoped_records_included": False,
            }
        if "source_workspaces" in feature_key and service_key in {"blockchain", "stock"}:
            payload["live_history"] = load_source_live_history(self.db_path, source=source_scope)
        if "learning" in feature_key:
            payload["learning"] = self.learning_snapshot(
                source=source_scope,
                offset=learning_offset,
                limit=learning_limit,
            )
        if "assistant" in feature_key or service_key == "ai_analyst":
            payload["ai_decisions"] = self.table_rows("ai_decisions", source=source_scope)
        if "report" in feature_key or service_key == "ai_analyst":
            payload["ai_analysis"] = self.table_rows("ai_trade_analysis", source=source_scope)
            payload["analysis_log"] = self.table_rows("analysis_log", source=source_scope)
        if "risk" in feature_key or "intelligence" in feature_key:
            payload["risk"] = self.table_rows("risk_log", source=source_scope)
        # selected_coins is an explicitly crypto table in the legacy schema.
        # Never relabel those rows as stock candidates when a stock-only table
        # does not exist; the stock UI must show an honest empty state instead.
        if service_key != "stock" and ("coin" in feature_key or "info" in feature_key or "trend" in feature_key or "alpha" in feature_key):
            payload["selected_coins"] = self.selected_coin_rows(source=source_scope)
        elif service_key == "stock" and ("info" in feature_key or "trend" in feature_key):
            payload["selected_coins"] = []
            payload["data_status"] = "stock_candidate_store_unavailable"
        return payload
