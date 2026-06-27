#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""배포 게이트 자동화 스크립트.

기존 build_safe.py 배포 흐름을 바꾸지 않고,
빌드 전 검증 단계를 자동으로 강제한다.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NoahAI Release Gate")
    parser.add_argument(
        "--profile",
        choices=["dev", "prekey", "release"],
        default="dev",
        help="dev: 개발용, prekey: 키 입력 전 최종완료용, release: 배포 직전 엄격 검증",
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


def main() -> int:
    args = _parse_args()
    _venv_win = ROOT / ".venv" / "Scripts" / "python.exe"
    _venv_unix = ROOT / ".venv" / "bin" / "python"
    python_cmd = str(_venv_win if _venv_win.exists() else (_venv_unix if _venv_unix.exists() else sys.executable))

    strict = args.profile == "release"
    readiness_cmd = [python_cmd, "scripts/stock_live_readiness_run.py", "--all-supported-brokers"]
    if strict:
        readiness_cmd.append("--strict")

    steps = []
    # 공통 필수 회귀
    steps.append(
        (
            "TEST_STOCK",
            [
                python_cmd,
                "-m",
                "pytest",
                "tests/test_stock_live_readiness_scripts.py",
                "tests/test_stock_analysis_service.py",
                "tests/test_stock_integration.py",
                "tests/test_stock_risk_governance.py",
                "tests/test_stock_broker_recovery.py",
                "tests/test_exchange_readiness_check.py",
                "tests/test_release_gate.py",
                "tests/test_multi_exchange_stability_check.py",
                "-q",
                "--tb=no",
            ],
            True,
        )
    )
    steps.append(("MODE_MATRIX", [python_cmd, "scripts/stock_supported_mode_matrix_check.py"], True))

    # prekey/release에서는 키 없이 완료 가능한 진단 체인을 필수로 강제
    if args.profile in ("prekey", "release"):
        steps.append(("MOCK_HARDENING", [python_cmd, "scripts/stock_nonkey_hardening_check.py"], True))
        steps.append(("EXCHANGE_READINESS_REPORT", [python_cmd, "scripts/exchange_readiness_check.py"], True))
        steps.append(("DOC_CONSISTENCY", [python_cmd, "scripts/doc_consistency_check.py"], True))
        steps.append(("SYNC_GUARD", [python_cmd, "scripts/user_visible_sync_guard.py", "--strict"], True))
        steps.append(
            (
                "MULTI_EXCHANGE_STABILITY",
                [python_cmd, "scripts/multi_exchange_stability_check.py", "--skip-pytest"],
                True,
            )
        )

    # 실브로커 준비도는 release에서 필수, dev/prekey에서는 참고 단계
    steps.append(("READINESS", readiness_cmd, strict))

    failures: List[str] = []
    for title, command, required in steps:
        code, _ = _run_step(title, command)
        if code != 0 and required:
            failures.append(title)

    print("\n[RELEASE_GATE]")
    if failures:
        print(f"FAIL | {', '.join(failures)}")
        return 1

    print(f"PASS | profile={args.profile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
