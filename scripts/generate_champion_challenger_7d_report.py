#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate 7-day champion-challenger report from local trading DB.

Champion: previous 7 days
Challenger: latest 7 days
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from utils.trade_operating_metrics import calculate_currency_financial_metrics
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from utils.trade_operating_metrics import calculate_currency_financial_metrics


def _resolve_default_db_path() -> Path:
    try:
        from path_utils import get_db_file_path

        return Path(get_db_file_path())
    except Exception:
        return Path("data/trading.db")


def _resolve_default_reports_dir() -> Path:
    try:
        from path_utils import get_reports_dir

        return Path(get_reports_dir())
    except Exception:
        return Path("data/reports")


@dataclass
class WindowMetrics:
    label: str
    start: str
    end: str
    trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: Optional[float]
    avg_pnl: Optional[float]
    avg_pnl_percent: float
    max_win: Optional[float]
    max_loss: Optional[float]
    fees_total: Optional[float]
    net_pnl_after_fees: Optional[float]
    net_expectancy: Optional[float]
    pnl_by_currency: dict[str, float]
    fees_by_currency: dict[str, float]
    currencies: list[str]
    mixed_currency: bool


@dataclass
class Comparison:
    win_rate_delta: float
    total_pnl_delta: Optional[float]
    net_pnl_delta: Optional[float]
    avg_pnl_delta: Optional[float]
    avg_pnl_percent_delta: float
    trades_delta: int
    verdict: str
    summary: str


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _fetch_window_metrics(conn: sqlite3.Connection, window: str) -> WindowMetrics:
    # window = 'challenger' -> latest 7 days, 'champion' -> previous 7 days
    if window == "challenger":
        where = (
            "exit_time IS NOT NULL "
            "AND LOWER(COALESCE(reason, '')) != 'binance_import' "
            "AND datetime(exit_time) >= datetime('now', '-7 day')"
        )
        label = "challenger_latest_7d"
        start_sql = "datetime('now', '-7 day')"
        end_sql = "datetime('now')"
    else:
        where = (
            "exit_time IS NOT NULL "
            "AND LOWER(COALESCE(reason, '')) != 'binance_import' "
            "AND datetime(exit_time) >= datetime('now', '-14 day') "
            "AND datetime(exit_time) < datetime('now', '-7 day')"
        )
        label = "champion_previous_7d"
        start_sql = "datetime('now', '-14 day')"
        end_sql = "datetime('now', '-7 day')"

    cursor = conn.cursor()
    row = cursor.execute(
        f"""
        SELECT
          COUNT(*) AS trades,
          SUM(CASE WHEN COALESCE(pnl, 0) > 0 THEN 1 ELSE 0 END) AS wins,
          SUM(CASE WHEN COALESCE(pnl, 0) <= 0 THEN 1 ELSE 0 END) AS losses,
          ROUND(SUM(COALESCE(pnl, 0)), 4) AS total_pnl,
          ROUND(AVG(COALESCE(pnl, 0)), 4) AS avg_pnl,
          ROUND(AVG(COALESCE(pnl_percent, 0)), 4) AS avg_pnl_percent,
          ROUND(MAX(COALESCE(pnl, 0)), 4) AS max_win,
          ROUND(MIN(COALESCE(pnl, 0)), 4) AS max_loss,
          ROUND(SUM(COALESCE(fees, 0)), 4) AS fees_total
        FROM trade_log
        WHERE {where}
        """
    ).fetchone()

    period_row = cursor.execute(
        f"SELECT {start_sql} AS start_dt, {end_sql} AS end_dt"
    ).fetchone()

    trades = _as_int(row[0] if row else 0)
    wins = _as_int(row[1] if row else 0)
    losses = _as_int(row[2] if row else 0)
    win_rate = round((wins / trades) * 100.0, 2) if trades > 0 else 0.0

    trade_rows = cursor.execute(
        f"""
        SELECT symbol, COALESCE(exchange, ''), COALESCE(pnl, 0),
               COALESCE(fees, 0), COALESCE(fee_asset, '')
        FROM trade_log
        WHERE {where}
        """
    ).fetchall()
    financials = calculate_currency_financial_metrics(
        {
            "symbol": item[0],
            "exchange": item[1],
            "pnl": item[2],
            "fees": item[3],
            "fee_asset": item[4],
        }
        for item in trade_rows
    )
    pnl_by_currency = {
        currency: round(float(bucket["pnl"]), 4)
        for currency, bucket in financials["by_currency"].items()
    }
    fees_by_currency = {
        currency: round(float(value), 4)
        for currency, value in financials["fees_by_currency"].items()
    }
    currencies = list(financials["currencies"])
    monetary_comparable = len(currencies) <= 1 and set(fees_by_currency).issubset(set(currencies))
    if not trade_rows:
        total_pnl: Optional[float] = 0.0
        avg_pnl: Optional[float] = 0.0
        fees_total: Optional[float] = 0.0
        net_pnl: Optional[float] = 0.0
        expectancy: Optional[float] = 0.0
        max_win: Optional[float] = 0.0
        max_loss: Optional[float] = 0.0
    elif monetary_comparable:
        currency = currencies[0]
        total_pnl = pnl_by_currency[currency]
        avg_pnl = round(total_pnl / trades, 4) if trades else 0.0
        fees_total = fees_by_currency.get(currency, 0.0)
        net_pnl = round(total_pnl - fees_total, 4)
        expectancy = round(net_pnl / trades, 6) if trades else 0.0
        pnl_values = [_as_float(item[2]) for item in trade_rows]
        max_win = round(max(pnl_values), 4)
        max_loss = round(min(pnl_values), 4)
    else:
        total_pnl = avg_pnl = fees_total = net_pnl = expectancy = None
        max_win = max_loss = None

    return WindowMetrics(
        label=label,
        start=str(period_row[0]) if period_row else "",
        end=str(period_row[1]) if period_row else "",
        trades=trades,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        total_pnl=total_pnl,
        avg_pnl=avg_pnl,
        avg_pnl_percent=_as_float(row[5] if row else 0.0),
        max_win=max_win,
        max_loss=max_loss,
        fees_total=fees_total,
        net_pnl_after_fees=net_pnl,
        net_expectancy=expectancy,
        pnl_by_currency=pnl_by_currency,
        fees_by_currency=fees_by_currency,
        currencies=currencies,
        mixed_currency=bool(financials["mixed_currency"]),
    )


def _compare(champion: WindowMetrics, challenger: WindowMetrics) -> Comparison:
    win_rate_delta = round(challenger.win_rate - champion.win_rate, 2)
    same_currency = (
        not champion.mixed_currency
        and not challenger.mixed_currency
        and champion.currencies == challenger.currencies
        and champion.total_pnl is not None
        and challenger.total_pnl is not None
    )
    total_pnl_delta = round(challenger.total_pnl - champion.total_pnl, 4) if same_currency else None
    net_pnl_delta = (
        round(challenger.net_pnl_after_fees - champion.net_pnl_after_fees, 4)
        if same_currency and champion.net_pnl_after_fees is not None and challenger.net_pnl_after_fees is not None
        else None
    )
    avg_pnl_delta = (
        round(challenger.avg_pnl - champion.avg_pnl, 4)
        if same_currency and champion.avg_pnl is not None and challenger.avg_pnl is not None
        else None
    )
    avg_pnl_percent_delta = round(challenger.avg_pnl_percent - champion.avg_pnl_percent, 4)
    trades_delta = challenger.trades - champion.trades

    score = 0
    if net_pnl_delta is not None and net_pnl_delta > 0:
        score += 2
    elif net_pnl_delta is not None and net_pnl_delta < 0:
        score -= 2

    if win_rate_delta > 0:
        score += 1
    elif win_rate_delta < 0:
        score -= 1

    if avg_pnl_delta is not None and avg_pnl_delta > 0:
        score += 1
    elif avg_pnl_delta is not None and avg_pnl_delta < 0:
        score -= 1

    if not same_currency:
        verdict = "inconclusive_currency_boundary"
        summary = "결제통화 구성이 달라 환산 없는 금액 우열 판정을 보류합니다."
    elif score >= 2:
        verdict = "challenger_wins"
        summary = "최근 7일 챌린저 성과가 기준선 대비 우위입니다."
    elif score <= -2:
        verdict = "champion_wins"
        summary = "기준선 챔피언 성과가 더 안정적입니다."
    else:
        verdict = "inconclusive"
        summary = "우열이 명확하지 않습니다. 추가 관찰이 필요합니다."

    return Comparison(
        win_rate_delta=win_rate_delta,
        total_pnl_delta=total_pnl_delta,
        net_pnl_delta=net_pnl_delta,
        avg_pnl_delta=avg_pnl_delta,
        avg_pnl_percent_delta=avg_pnl_percent_delta,
        trades_delta=trades_delta,
        verdict=verdict,
        summary=summary,
    )


def _to_dict(metrics: WindowMetrics) -> dict[str, Any]:
    return {
        "label": metrics.label,
        "period": {
            "start": metrics.start,
            "end": metrics.end,
        },
        "trades": metrics.trades,
        "wins": metrics.wins,
        "losses": metrics.losses,
        "win_rate": metrics.win_rate,
        "total_pnl": metrics.total_pnl,
        "avg_pnl": metrics.avg_pnl,
        "avg_pnl_percent": metrics.avg_pnl_percent,
        "max_win": metrics.max_win,
        "max_loss": metrics.max_loss,
        "fees_total": metrics.fees_total,
        "net_pnl_after_fees": metrics.net_pnl_after_fees,
        "net_expectancy": metrics.net_expectancy,
        "pnl_by_currency": metrics.pnl_by_currency,
        "fees_by_currency": metrics.fees_by_currency,
        "currencies": metrics.currencies,
        "mixed_currency": metrics.mixed_currency,
    }


def _fetch_variant_breakdown(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    columns = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(trade_log)").fetchall()
    }
    if "strategy_variant" not in columns or "model_version" not in columns:
        return []
    rows = conn.execute(
        """
        SELECT
          COALESCE(NULLIF(strategy_variant, ''), 'legacy') AS variant,
          COALESCE(NULLIF(model_version, ''), 'unknown') AS model,
          COUNT(*) AS trades,
          SUM(CASE WHEN COALESCE(pnl, 0) > 0 THEN 1 ELSE 0 END) AS wins,
          SUM(COALESCE(pnl, 0)) AS gross_pnl,
          SUM(COALESCE(fees, 0)) AS fees,
          SUM(CASE WHEN fee_source = 'exchange_fill' THEN 1 ELSE 0 END) AS fee_verified
        FROM trade_log
        WHERE exit_time IS NOT NULL
          AND LOWER(COALESCE(reason, '')) != 'binance_import'
          AND datetime(exit_time) >= datetime('now', '-14 day')
        GROUP BY variant, model
        ORDER BY (SUM(COALESCE(pnl, 0)) - SUM(COALESCE(fees, 0))) DESC
        """
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        trades = _as_int(row[2])
        wins = _as_int(row[3])
        gross = _as_float(row[4])
        fees = _as_float(row[5])
        result.append(
            {
                "strategy_variant": str(row[0]),
                "model_version": str(row[1]),
                "trades": trades,
                "win_rate": round((wins / trades) * 100.0, 2) if trades else 0.0,
                "gross_pnl": round(gross, 4),
                "fees": round(fees, 4),
                "net_pnl_after_fees": round(gross - fees, 4),
                "net_expectancy": round((gross - fees) / trades, 6) if trades else 0.0,
                "fee_verification_rate": round((_as_int(row[6]) / trades) * 100.0, 2)
                if trades
                else 0.0,
            }
        )
    return result


def _money(value: Optional[float], digits: int = 4) -> str:
    return "통화별 분리" if value is None else f"{value:.{digits}f}"


def _money_delta(value: Optional[float], digits: int = 4) -> str:
    return "비교 보류" if value is None else f"{value:+.{digits}f}"


def _currency_lines(metrics: WindowMetrics) -> str:
    currencies = sorted(set(metrics.pnl_by_currency) | set(metrics.fees_by_currency))
    if not currencies:
        return "- 데이터 없음"
    return "\n".join(
        f"- {currency}: PnL {metrics.pnl_by_currency.get(currency, 0.0):+.4f}, "
        f"Fee {metrics.fees_by_currency.get(currency, 0.0):.4f}"
        for currency in currencies
    )


def _render_markdown(champion: WindowMetrics, challenger: WindowMetrics, comparison: Comparison) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"""# 7일 챔피언-챌린저 리포트

- 생성시각: {now}
- 챔피언(기준선): 직전 7일
- 챌린저(비교군): 최근 7일

## 비교 결과

- 판정: {comparison.verdict}
- 요약: {comparison.summary}

| 지표 | 챔피언 | 챌린저 | 변화(챌린저-챔피언) |
| --- | ---: | ---: | ---: |
| 거래 수 | {champion.trades} | {challenger.trades} | {comparison.trades_delta:+d} |
| 승률(%) | {champion.win_rate:.2f} | {challenger.win_rate:.2f} | {comparison.win_rate_delta:+.2f} |
| 총손익(동일통화일 때만) | {_money(champion.total_pnl)} | {_money(challenger.total_pnl)} | {_money_delta(comparison.total_pnl_delta)} |
| 수수료 차감 후 손익(동일통화일 때만) | {_money(champion.net_pnl_after_fees)} | {_money(challenger.net_pnl_after_fees)} | {_money_delta(comparison.net_pnl_delta)} |
| 거래당 순기대값(동일통화일 때만) | {_money(champion.net_expectancy, 6)} | {_money(challenger.net_expectancy, 6)} | {_money_delta((challenger.net_expectancy - champion.net_expectancy) if champion.net_expectancy is not None and challenger.net_expectancy is not None else None, 6)} |
| 평균손익(동일통화일 때만) | {_money(champion.avg_pnl)} | {_money(challenger.avg_pnl)} | {_money_delta(comparison.avg_pnl_delta)} |
| 평균손익률(%) | {champion.avg_pnl_percent:.4f} | {challenger.avg_pnl_percent:.4f} | {comparison.avg_pnl_percent_delta:+.4f} |

## 통화별 손익·수수료

### 챔피언
{_currency_lines(champion)}

### 챌린저
{_currency_lines(challenger)}

KRW·USDT 등 서로 다른 통화는 환율 기준 없이 합산하거나 금액 우열을 판정하지 않습니다.

## 기간 정보

- 챔피언: {champion.start} ~ {champion.end}
- 챌린저: {challenger.start} ~ {challenger.end}
"""


def generate_report(db_path: Path, out_dir: Path) -> tuple[Path, Path]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB file not found: {db_path}")

    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    champion = _fetch_window_metrics(conn, "champion")
    challenger = _fetch_window_metrics(conn, "challenger")
    variant_breakdown = _fetch_variant_breakdown(conn)
    conn.close()

    comparison = _compare(champion, challenger)

    payload: dict[str, Any] = {
        "report_type": "champion_challenger_7d",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": {
            "db_path": str(db_path),
            "table": "trade_log",
        },
        "champion": _to_dict(champion),
        "challenger": _to_dict(challenger),
        "comparison": {
            "win_rate_delta": comparison.win_rate_delta,
            "total_pnl_delta": comparison.total_pnl_delta,
            "net_pnl_delta": comparison.net_pnl_delta,
            "avg_pnl_delta": comparison.avg_pnl_delta,
            "avg_pnl_percent_delta": comparison.avg_pnl_percent_delta,
            "trades_delta": comparison.trades_delta,
            "verdict": comparison.verdict,
            "summary": comparison.summary,
        },
        "variant_breakdown_latest_14d": variant_breakdown,
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_latest = out_dir / "champion_challenger_7d_latest.json"
    json_dated = out_dir / f"champion_challenger_7d_{stamp}.json"
    md_latest = out_dir / "champion_challenger_7d_latest.md"
    md_dated = out_dir / f"champion_challenger_7d_{stamp}.md"

    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    md_text = _render_markdown(champion, challenger, comparison)

    json_latest.write_text(json_text, encoding="utf-8")
    json_dated.write_text(json_text, encoding="utf-8")
    md_latest.write_text(md_text, encoding="utf-8")
    md_dated.write_text(md_text, encoding="utf-8")

    return json_latest, md_latest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate 7-day champion-challenger report from trade_log")
    parser.add_argument("--db", default=str(_resolve_default_db_path()), help="Path to trading sqlite DB")
    parser.add_argument("--output", default=str(_resolve_default_reports_dir()), help="Output directory")
    args = parser.parse_args()

    db_path = Path(args.db)
    out_dir = Path(args.output)

    json_file, md_file = generate_report(db_path=db_path, out_dir=out_dir)
    print(f"✅ champion-challenger report generated")
    print(f"- JSON: {json_file}")
    print(f"- MARKDOWN: {md_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
