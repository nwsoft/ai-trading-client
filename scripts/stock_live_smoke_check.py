#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""증권 실연동 smoke 점검 스크립트.

목적:
- 실주문 없이 브로커별 연결/잔고/포지션/미체결 조회 가능 여부를 점검
- stock_d1_preflight 기준으로 BLOCKED 브로커는 자동 skip
- 운영자가 실계정 준비 상태를 빠르게 확인하도록 돕는다.
"""

import sys
import argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stock_d1_preflight import _build_rows, _load_settings
from trading.exchanges.exchange_factory import ExchangeFactory


CHECK_STEPS = (
    ("connect", lambda adapter: adapter.connect()),
    ("balance", lambda adapter: adapter.get_balance()),
    ("positions", lambda adapter: adapter.get_positions()),
    ("open_orders", lambda adapter: adapter.get_open_orders()),
)


def _resolve_broker_settings(settings: Dict[str, Any], broker: str) -> Dict[str, Any]:
    stock_configs = settings.get("stock_broker_configs", {})
    if broker in stock_configs and isinstance(stock_configs[broker], dict):
        return stock_configs[broker]

    lower_map = {str(k).lower(): v for k, v in stock_configs.items() if isinstance(v, dict)}
    return lower_map.get(str(broker).lower(), {})


def _should_skip(row: Dict[str, Any]) -> Tuple[bool, str]:
    if not row.get("valid_combo"):
        return True, "invalid api_type/api_version"
    if row.get("execution_mode") != "live_api":
        return True, "not live_api path"
    if not row.get("credentials_ready"):
        missing = ",".join(row.get("missing_credentials") or [])
        return True, f"missing credentials: {missing}"
    if row.get("os_blocked"):
        return True, "os blocked"
    return False, ""


def _check_adapter(adapter: Any) -> List[str]:
    notes: List[str] = []
    for name, action in CHECK_STEPS:
        try:
            result = action(adapter)
            if name == "connect":
                if result is not True:
                    notes.append(f"{name}=fail:{result}")
                    break
                notes.append(f"{name}=ok")
                continue

            if name == "balance":
                status = result.get("status") if isinstance(result, dict) else None
                notes.append(f"{name}={status or type(result).__name__}")
                if status not in ("ok", "success"):
                    break
                continue

            if isinstance(result, list):
                notes.append(f"{name}=ok:{len(result)}")
            else:
                notes.append(f"{name}={type(result).__name__}")
        except Exception as exc:
            notes.append(f"{name}=error:{exc}")
            break
    return notes


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="증권 실연동 smoke 점검")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="실행 대상이 없거나 실패가 있으면 종료코드 1 반환",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    settings, settings_path = _load_settings()
    rows = _build_rows(settings)

    print("증권 live smoke 점검 시작")
    print(f"- settings: {settings_path}")

    if not rows:
        print("- 결과: FAIL | 활성 브로커 없음")
        return 1

    failures = []
    executed = 0
    for row in rows:
        broker = row["broker"]
        skip, reason = _should_skip(row)
        if skip:
            print(f"- {broker:<12} SKIP | {reason}")
            continue

        executed += 1
        try:
            adapter = ExchangeFactory.create_stock_exchange(broker, settings)
            notes = _check_adapter(adapter)
            is_ok = all("error:" not in note and "fail:" not in note for note in notes)
            print(f"- {broker:<12} {'OK' if is_ok else 'FAIL'} | {' | '.join(notes)}")
            if not is_ok:
                failures.append((broker, notes))
        except Exception as exc:
            print(f"- {broker:<12} FAIL | factory_error:{exc}")
            failures.append((broker, [f"factory_error:{exc}"]))

    print("\n[요약]")
    if executed == 0:
        print("- 실행된 live smoke 대상 없음")
        return 1 if args.strict else 0
    if failures:
        print(f"- 결과: FAIL ({len(failures)} broker)")
        return 1

    print(f"- 결과: PASS ({executed} broker)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
