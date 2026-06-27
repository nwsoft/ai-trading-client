#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""증권 런타임 흐름 데모 (연결 -> 분석 -> 자동매매 사이클 -> 기록 확인).

의도:
- 브로커 API 키 없이도(mock) 실제 동작 흐름을 재현
- 로그/DB 기록 지점을 한 번에 확인
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading.exchanges.adapters.stock_mock_adapter import StockMockAdapter
from trading.stock_analysis_service import StockAnalysisService


def _safe_count(db_path: Path, table: str) -> int:
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        row = cur.fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0
    finally:
        conn.close()


def _tail_file(path: Path, limit: int = 10) -> list[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return lines[-limit:]
    except Exception:
        return []


def main() -> int:
    print("[1] mock 어댑터 생성/연결")
    adapter = StockMockAdapter(broker_name="shinhan", latency_ms=0)
    connected = adapter.connect()
    print(f"- connected: {connected}")
    if not connected:
        print("- FAIL: mock connect failed")
        return 1

    print("\n[2] 분석 서비스 생성")
    service = StockAnalysisService(adapter=adapter, broker_name="shinhan")

    print("\n[3] 단일 종목 분석")
    analysis = service.analyze_symbol("005930")
    print(json.dumps({
        "symbol": analysis.get("symbol"),
        "score": analysis.get("score"),
        "analysis_type": analysis.get("analysis_type"),
        "reasoning": analysis.get("reasoning"),
        "status": analysis.get("status"),
    }, ensure_ascii=False, indent=2))

    print("\n[4] 자동매매 1회 사이클 (mock, 주문 허용 플래그 false여도 mock은 실행)")
    cycle = service.run_auto_trade_cycle(
        symbols=["005930", "069500"],
        quantity=1,
        order_type="MARKET",
        buy_threshold=60,
        sell_threshold=30,
        asset_mode="all",
        max_orders=1,
        allow_live_order=False,
    )
    print(json.dumps({
        "status": cycle.get("status"),
        "broker": cycle.get("broker"),
        "execution_mode": cycle.get("execution_mode"),
        "orders_executed": cycle.get("orders_executed"),
        "decisions": cycle.get("decisions", [])[:2],
    }, ensure_ascii=False, indent=2))

    print("\n[5] 기록 확인 (Recorder DB + 로컬 로그)")
    recorder = service._get_recorder()  # noqa: SLF001 - 운영 점검 스크립트 목적
    db_path = Path(getattr(recorder, "db_path", "")) if recorder is not None else Path()
    print(f"- recorder_db: {db_path if db_path else '(none)'}")

    trade_count = _safe_count(db_path, "trade_log") if db_path else 0
    analysis_count = _safe_count(db_path, "analysis_log") if db_path else 0
    decision_count = _safe_count(db_path, "ai_decisions") if db_path else 0

    print(f"- trade_log rows: {trade_count}")
    print(f"- analysis_log rows: {analysis_count}")
    print(f"- ai_decisions rows: {decision_count}")

    raw_log_file = str(getattr(adapter, "log_file", "") or "").strip()
    log_file = Path(raw_log_file) if raw_log_file else Path()
    if not raw_log_file or raw_log_file == ".":
        try:
            from path_utils import get_log_file_path
            log_file = Path(get_log_file_path())
        except Exception:
            log_file = Path()

    print(f"- log_file: {log_file if log_file else '(unknown)'}")
    for line in _tail_file(log_file, limit=8):
        print(f"  {line}")

    print("\n[완료] 런타임 흐름 데모 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
