"""확정 체결 원장의 읽기 전용 화면/리포트 변환."""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List, Optional


def load_execution_data(
    db_path: str,
    *,
    days: int = 1,
    exchange: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not db_path or not os.path.exists(db_path):
        return []
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='exchange_execution_log'"
            )
            if cursor.fetchone() is None:
                return []
            sql = """
                SELECT exchange, symbol, side, price, quantity, cost, fee,
                       fee_currency, executed_at
                FROM exchange_execution_log
                WHERE confirmation_status = 'confirmed'
                  AND date(COALESCE(executed_at, created_at)) >=
                      date('now', 'localtime', '-{} days')
            """.format(max(0, int(days)))
            params: List[Any] = []
            if exchange and str(exchange).strip().lower() not in {'전체', 'all'}:
                sql += " AND LOWER(exchange) = LOWER(?)"
                params.append(str(exchange).strip())
            sql += " ORDER BY COALESCE(executed_at, created_at) DESC, id DESC"
            cursor.execute(sql, tuple(params))
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception:
        return []


def format_execution_detail(
    executions: List[Dict[str, Any]],
    *,
    limit: int = 30,
) -> str:
    if not executions:
        return "실제 체결 내역\n\n확정된 실제 체결이 없습니다."
    lines = ["실제 체결 내역 (PnL 계산과 분리)", ""]
    for index, fill in enumerate(executions[:max(1, int(limit))], 1):
        venue = str(fill.get('exchange') or '').upper()
        symbol = str(fill.get('symbol') or '')
        side = str(fill.get('side') or '').upper()
        when = str(fill.get('executed_at') or '-')[:16]
        price = float(fill.get('price') or 0.0)
        quantity = float(fill.get('quantity') or 0.0)
        cost = float(fill.get('cost') or 0.0)
        currency = 'KRW' if venue in {'UPBIT', 'BITHUMB'} else 'USDT'
        lines.append(
            f"{index:2d}. {when} | {venue} | {symbol} | {side} | "
            f"{quantity:.8f} @ {price:,.8f} | {cost:,.2f} {currency}"
        )
    if len(executions) > limit:
        lines.append(f"\n... 및 {len(executions) - limit}건 더")
    return "\n".join(lines)
