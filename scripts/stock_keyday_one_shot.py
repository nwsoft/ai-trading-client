#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""키 입력 당일 원샷 실브로커 검증 실행기.

목적:
- 키 발급 전에는 prekey 게이트로 코드/정책을 모두 닫고,
- 키 입력 당일에는 이 스크립트로 실브로커 검증을 한 번에 끝낸다.
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


ROOT = Path(__file__).resolve().parents[1]
PYTHON = str((ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable)

DEFAULT_BROKERS = ["kiwoom", "shinhan", "miraeAsset", "koreaInvestment"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="키 입력 당일 원샷 실브로커 검증")
    parser.add_argument(
        "--brokers",
        default=",".join(DEFAULT_BROKERS),
        help="검증 대상 브로커 콤마 구분 (예: kiwoom,shinhan,miraeAsset,koreaInvestment)",
    )
    parser.add_argument(
        "--allow-kiwoom-nonwindows",
        action="store_true",
        help="비-Windows 환경에서도 키움을 강제로 포함",
    )
    return parser.parse_args()


def _run_step(title: str, command: List[str]) -> Tuple[int, str]:
    result = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True)
    output = (result.stdout or "").strip()
    if result.stderr:
        err = result.stderr.strip()
        output = f"{output}\n{err}" if output else err

    print(f"\n[{title}]")
    print(output if output else "(no output)")
    return result.returncode, output


def _normalize_brokers(raw: str) -> List[str]:
    ordered: List[str] = []
    for token in str(raw or "").split(","):
        item = token.strip()
        if item and item not in ordered:
            ordered.append(item)
    return ordered or list(DEFAULT_BROKERS)


def main() -> int:
    args = _parse_args()
    brokers = _normalize_brokers(args.brokers)

    if platform.system() != "Windows" and not args.allow_kiwoom_nonwindows:
        brokers = [b for b in brokers if b.lower() != "kiwoom"]
        if not brokers:
            brokers = ["shinhan", "miraeAsset", "koreaInvestment"]

    failures: List[str] = []

    # 1) 인증/준비도 리포트
    code, _ = _run_step("EXCHANGE_READINESS_REPORT", [PYTHON, "scripts/exchange_readiness_check.py"])
    if code != 0:
        failures.append("EXCHANGE_READINESS_REPORT")

    # 2) D1 preflight
    code, _ = _run_step("PRECHECK", [PYTHON, "scripts/stock_d1_preflight.py"])
    if code != 0:
        failures.append("PRECHECK")

    # 3) 브로커별 strict readiness
    for broker in brokers:
        code, _ = _run_step(
            f"READINESS:{broker}",
            [PYTHON, "scripts/stock_live_readiness_run.py", "--broker", broker, "--strict"],
        )
        if code != 0:
            failures.append(f"READINESS:{broker}")

    print("\n[FINAL]")
    if failures:
        print(f"FAIL | {', '.join(failures)}")
        return 1

    print("PASS | key-day one-shot validation completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
