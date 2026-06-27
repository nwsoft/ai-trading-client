#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""증권 실연동 준비도 전체 실행기.

순서:
1. preflight
2. smoke
3. order drill (기본 dry-run)

기본 모드는 각 단계 결과를 보고하고,
엄격 모드에서는 skip/실패를 종료코드 1로 처리한다.
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stock_d1_preflight import _get_enabled_brokers, _load_settings
from trading.exchanges.exchange_factory import ExchangeFactory


PYTHON = ROOT / ".venv" / "bin" / "python"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="증권 실연동 준비도 전체 실행")
    parser.add_argument("--broker", default="kiwoom", help="order drill 대상 브로커")
    parser.add_argument("--all-brokers", action="store_true", help="enabled_stock_brokers 전체를 순회 실행")
    parser.add_argument("--all-supported-brokers", action="store_true", help="설정과 무관하게 지원 브로커(키움/신한/미래에셋/한국투자) 전체 순회")
    parser.add_argument("--skip-mock-check", action="store_true", help="mock 공통경로 점검(stock_nonkey_hardening_check)을 건너뜀")
    parser.add_argument("--strict", action="store_true", help="각 단계 skip/실패를 종료코드 1로 처리")
    return parser.parse_args()


def _resolve_target_brokers(args: argparse.Namespace) -> List[str]:
    if bool(getattr(args, "all_supported_brokers", False)):
        supported = ExchangeFactory.get_supported_exchanges().get("stock", [])
        ordered: List[str] = []
        for broker in supported:
            value = str(broker or "").strip()
            if value and value not in ordered:
                ordered.append(value)
        return ordered or ["kiwoom", "shinhan", "miraeAsset", "koreaInvestment"]

    if not bool(getattr(args, "all_brokers", False)):
        return [str(getattr(args, "broker", "kiwoom") or "kiwoom").strip()]

    settings, _ = _load_settings()
    brokers = _get_enabled_brokers(settings)
    ordered: List[str] = []
    for broker in brokers:
        value = str(broker or "").strip()
        if value and value not in ordered:
            ordered.append(value)
    return ordered or ["kiwoom", "shinhan", "miraeAsset", "koreaInvestment"]


def _run_step(title: str, command: List[str]) -> Tuple[int, str]:
    result = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "").strip()
    if result.stderr:
        stderr_text = result.stderr.strip()
        output = f"{output}\n{stderr_text}" if output else stderr_text

    print(f"\n[{title}]")
    print(output if output else "(no output)")
    return result.returncode, output


def main() -> int:
    args = _parse_args()

    python_cmd = str(PYTHON if PYTHON.exists() else sys.executable)
    target_brokers = _resolve_target_brokers(args)

    steps = [
        (
            "MODE_MATRIX",
            [python_cmd, "scripts/stock_supported_mode_matrix_check.py"],
            True,
        ),
        (
            "PRECHECK",
            [python_cmd, "scripts/stock_d1_preflight.py"],
            True,
        ),
    ]

    if not bool(getattr(args, "skip_mock_check", False)):
        steps.append(
            (
                "MOCK_HARDENING",
                [python_cmd, "scripts/stock_nonkey_hardening_check.py"],
                True,
            )
        )

    steps.extend([
        (
            "SMOKE",
            [python_cmd, "scripts/stock_live_smoke_check.py"] + (["--strict"] if args.strict else []),
            False,
        ),
    ])

    for broker in target_brokers:
        steps.append(
            (
                f"ORDER_DRILL:{broker}",
                [python_cmd, "scripts/stock_live_order_drill.py", "--broker", broker]
                + (["--strict"] if args.strict else []),
                False,
            )
        )

    failures = []
    for title, command, always_strict in steps:
        exit_code, _ = _run_step(title, command)
        if exit_code != 0 and (args.strict or always_strict):
            if (
                title == "PRECHECK"
                and bool(getattr(args, "all_supported_brokers", False))
                and not bool(getattr(args, "strict", False))
            ):
                print("- NOTE: all-supported-brokers 모드에서는 PRECHECK BLOCKED를 경고로 처리하고 다음 단계를 계속합니다.")
                continue
            failures.append(title)

    print("\n[FINAL]")
    if failures:
        print(f"FAIL | blocking steps: {', '.join(failures)}")
        return 1

    print("PASS | readiness chain completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())