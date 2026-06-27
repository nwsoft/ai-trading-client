#!/usr/bin/env python3
"""Generate public-safe NoahAI user KPI snapshot from local trading DB."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Freshness:
    latest_trade: str | None
    latest_decision: str | None
    trade_hours: float | None
    decision_hours: float | None


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(value[:26], fmt)
        except ValueError:
            continue
    return None


def to_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def fetch_one(cur: sqlite3.Cursor, query: str) -> tuple[Any, ...]:
    row = cur.execute(query).fetchone()
    if row is None:
        return tuple()
    return tuple(row)


def table_columns(cur: sqlite3.Cursor, table: str) -> set[str]:
    rows = cur.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def detect_account_column(cur: sqlite3.Cursor, table: str) -> str | None:
    candidates = ("user_id", "account", "account_id", "account_name", "username", "user")
    cols = table_columns(cur, table)
    for c in candidates:
        if c in cols:
            return c
    return None


def build_freshness(
    cur: sqlite3.Cursor,
    trade_where: str,
    trade_params: tuple[Any, ...],
    decision_where: str,
    decision_params: tuple[Any, ...],
) -> Freshness:
    latest_trade = tuple(
        cur.execute(f"SELECT MAX(exit_time) FROM trade_log {trade_where}", trade_params).fetchone()
    )
    latest_decision = tuple(
        cur.execute(f"SELECT MAX(created_at) FROM ai_decisions {decision_where}", decision_params).fetchone()
    )
    now = datetime.now()
    latest_trade_s = latest_trade[0] if latest_trade else None
    latest_decision_s = latest_decision[0] if latest_decision else None
    trade_dt = parse_dt(latest_trade_s)
    decision_dt = parse_dt(latest_decision_s)
    trade_hours = round((now - trade_dt).total_seconds() / 3600.0, 2) if trade_dt else None
    decision_hours = round((now - decision_dt).total_seconds() / 3600.0, 2) if decision_dt else None
    return Freshness(
        latest_trade=latest_trade_s,
        latest_decision=latest_decision_s,
        trade_hours=trade_hours,
        decision_hours=decision_hours,
    )


def health_status(score: int) -> str:
    if score >= 70:
        return "GREEN"
    if score >= 40:
        return "YELLOW"
    if score > 0:
        return "RED"
    return "NODATA"


def build_health_score(closed_trades: int, win_rate: float, freshness: Freshness, decisions: int) -> int:
    if closed_trades == 0:
        return 0
    score = 40
    if win_rate >= 50.0:
        score += 20
    if freshness.trade_hours is not None and freshness.trade_hours <= 72.0:
        score += 20
    if decisions >= 100:
        score += 20
    return max(0, min(100, score))


def build_payload(
    db_path: Path,
    account: str | None = None,
    trade_account_column: str | None = None,
    decision_account_column: str | None = None,
) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    detected_trade_col = detect_account_column(cur, "trade_log")
    detected_decision_col = detect_account_column(cur, "ai_decisions")
    trade_col = trade_account_column or detected_trade_col
    decision_col = decision_account_column or detected_decision_col

    if account and not trade_col:
        raise ValueError("account filter requested, but trade_log has no detectable account column")
    if account and not decision_col:
        raise ValueError("account filter requested, but ai_decisions has no detectable account column")

    trade_where = "WHERE exit_time IS NOT NULL"
    trade_params: tuple[Any, ...] = tuple()
    if account and trade_col:
        trade_where += f" AND {trade_col} = ?"
        trade_params = (account,)

    decision_where = ""
    decision_params: tuple[Any, ...] = tuple()
    if account and decision_col:
        decision_where = f"WHERE {decision_col} = ?"
        decision_params = (account,)

    closed_stats = tuple(
        cur.execute(
            f"""
        SELECT
          COUNT(*) AS closed_trades,
          SUM(CASE WHEN COALESCE(pnl, 0) > 0 THEN 1 ELSE 0 END) AS wins,
          SUM(CASE WHEN COALESCE(pnl, 0) <= 0 THEN 1 ELSE 0 END) AS losses,
          ROUND(SUM(COALESCE(pnl, 0)), 4) AS total_pnl,
          ROUND(AVG(COALESCE(pnl, 0)), 4) AS avg_pnl,
          ROUND(AVG(COALESCE(pnl_percent, 0)), 4) AS avg_pnl_percent,
          ROUND(SUM(COALESCE(fees, 0)), 4) AS fees_total,
          ROUND(AVG(COALESCE(slippage, 0)), 6) AS slippage_avg
        FROM trade_log
        {trade_where}
            """,
            trade_params,
        ).fetchone()
    )

    closed_trades = int(closed_stats[0] or 0)
    wins = int(closed_stats[1] or 0)
    losses = int(closed_stats[2] or 0)
    total_pnl = to_float(closed_stats[3])
    avg_pnl = to_float(closed_stats[4])
    avg_pnl_percent = to_float(closed_stats[5])
    fees_total = to_float(closed_stats[6])
    slippage_avg = to_float(closed_stats[7])
    win_rate = round((wins / closed_trades) * 100.0, 2) if closed_trades > 0 else 0.0

    max_dd_row = fetch_one(
        cur,
        "SELECT ROUND(MAX(COALESCE(max_drawdown, 0)), 4) FROM performance_stats",
    )
    max_drawdown = to_float(max_dd_row[0] if max_dd_row else 0.0)

    decision_count_row = tuple(
        cur.execute(f"SELECT COUNT(*) FROM ai_decisions {decision_where}", decision_params).fetchone()
    )
    total_decisions = int(decision_count_row[0] or 0)

    exchange_rows = cur.execute(
        f"""
        SELECT
          COALESCE(exchange, 'unknown') AS exchange,
          COUNT(*) AS trades,
          ROUND(SUM(COALESCE(pnl, 0)), 4) AS total_pnl,
          ROUND(AVG(CASE WHEN COALESCE(pnl, 0) > 0 THEN 100.0 ELSE 0.0 END), 2) AS win_rate_pct
        FROM trade_log
        {trade_where}
        GROUP BY COALESCE(exchange, 'unknown')
        ORDER BY trades DESC
        LIMIT 6
        """,
        trade_params,
    ).fetchall()

    reason_rows = cur.execute(
        f"""
        SELECT COALESCE(reason, 'unknown') AS reason, COUNT(*) AS cnt
        FROM trade_log
        {trade_where}
        GROUP BY COALESCE(reason, 'unknown')
        ORDER BY cnt DESC
        LIMIT 8
        """,
        trade_params,
    ).fetchall()

    decision_rows = cur.execute(
        f"""
        SELECT COALESCE(decision_type, 'unknown') AS decision_type, COUNT(*) AS cnt
        FROM ai_decisions
        {decision_where}
        GROUP BY COALESCE(decision_type, 'unknown')
        ORDER BY cnt DESC
        LIMIT 8
        """,
        decision_params,
    ).fetchall()

    freshness = build_freshness(
        cur=cur,
        trade_where=trade_where,
        trade_params=trade_params,
        decision_where=decision_where,
        decision_params=decision_params,
    )
    score = build_health_score(closed_trades, win_rate, freshness, total_decisions)

    conn.close()

    reason_total = sum(int(r[1]) for r in reason_rows) or 1
    decision_total = sum(int(r[1]) for r in decision_rows) or 1

    payload = {
        "report_type": "noahai_user_kpi_public",
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "source_scope": {
            "account_filter": account or "ALL",
            "trade_account_column": trade_col,
            "decision_account_column": decision_col,
        },
        "summary": {
            "latest_dates": {
                "last_trade": freshness.latest_trade,
                "last_ai_decision": freshness.latest_decision,
            },
            "freshness_hours": {
                "trade": freshness.trade_hours,
                "ai_decision": freshness.decision_hours,
            },
            "status": {
                "health": health_status(score),
                "data_health_score": score,
            },
            "counts": {
                "closed_trades": closed_trades,
                "wins": wins,
                "losses": losses,
                "ai_decisions": total_decisions,
            },
            "performance": {
                "win_rate_pct": win_rate,
                "total_pnl": total_pnl,
                "avg_pnl": avg_pnl,
                "avg_pnl_percent": avg_pnl_percent,
            },
            "risk_and_cost": {
                "max_drawdown": max_drawdown,
                "fees_total": fees_total,
                "slippage_avg": slippage_avg,
            },
            "exchange_performance": [
                {
                    "exchange": r[0],
                    "trades": int(r[1]),
                    "total_pnl": to_float(r[2]),
                    "win_rate_pct": to_float(r[3]),
                }
                for r in exchange_rows
            ],
            "top_exit_reasons": [
                {
                    "reason": r[0],
                    "count": int(r[1]),
                    "share_pct": round((int(r[1]) / reason_total) * 100.0, 2),
                }
                for r in reason_rows
            ],
            "top_decision_types": [
                {
                    "decision_type": r[0],
                    "count": int(r[1]),
                    "share_pct": round((int(r[1]) / decision_total) * 100.0, 2),
                }
                for r in decision_rows
            ],
        },
        "disclaimer": "Public-safe summary only. Raw prompts, account identifiers, and user-level sensitive traces are excluded.",
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate NoahAI user KPI public JSON")
    parser.add_argument("--db", default="data/trading.db", help="Path to trading sqlite DB")
    parser.add_argument("--output", default="data/reports", help="Output directory")
    parser.add_argument("--account", default="", help="Optional account/user filter (e.g. A or nwsoft)")
    parser.add_argument("--trade-account-column", default="", help="Optional explicit account column for trade_log")
    parser.add_argument("--decision-account-column", default="", help="Optional explicit account column for ai_decisions")
    parser.add_argument(
        "--copy-to",
        default="",
        help="Optional destination file path for latest JSON copy",
    )
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    out_dir = Path(args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = build_payload(
        db_path=db_path,
        account=args.account or None,
        trade_account_column=args.trade_account_column or None,
        decision_account_column=args.decision_account_column or None,
    )
    latest_file = out_dir / "noahai_user_kpi_public_latest.json"
    dated_file = out_dir / f"noahai_user_kpi_public_{datetime.utcnow().strftime('%Y%m%d')}.json"

    latest_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.copy_to:
        dst = Path(args.copy_to).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(latest_file, dst)

    print(f"generated: {latest_file}")
    print(f"generated: {dated_file}")
    if args.copy_to:
        print(f"copied: {Path(args.copy_to).resolve()}")


if __name__ == "__main__":
    main()
