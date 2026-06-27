#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""증권 브로커별 장애 복구 자동화 스크립트.

실행 예시:
  python scripts/stock_broker_recovery.py --broker kiwoom
  python scripts/stock_broker_recovery.py --broker kiwoom --auto-mode
  python scripts/stock_broker_recovery.py --all
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading.exchanges.exchange_factory import ExchangeFactory

PYTHON = ROOT / ".venv" / "bin" / "python"

# 각 브로커 복구 점검 스텝 정의
RECOVERY_STEPS: Dict[str, List[Dict]] = {
    "preflight": {
        "name": "Preflight 점검",
        "script": "scripts/stock_d1_preflight.py",
        "required": True,
    },
    "mode_matrix": {
        "name": "지원 모드 매트릭스 점검",
        "script": "scripts/stock_supported_mode_matrix_check.py",
        "required": True,
    },
    "readiness": {
        "name": "Readiness 전체 체인",
        "script": None,  # 인라인 실행
        "required": False,
    },
}


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _run_script(script: str, extra_args: Optional[List[str]] = None) -> int:
    cmd = [str(PYTHON), str(ROOT / script)] + (extra_args or [])
    result = subprocess.run(cmd, cwd=str(ROOT))
    return result.returncode


def _run_readiness(broker: str, strict: bool = False) -> int:
    args: List[str] = [
        str(ROOT / "scripts" / "stock_live_readiness_run.py"),
        "--broker", broker,
        "--skip-mock-check",
    ]
    if strict:
        args.append("--strict")
    result = subprocess.run([str(PYTHON)] + args, cwd=str(ROOT))
    return result.returncode


def recover_broker(broker: str, auto_mode: bool = False, strict: bool = False) -> bool:
    """단일 브로커 복구 절차 실행. True = 복구 검증 통과."""
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"[{_now_str()}] 브로커 복구 시작: {broker}")
    print(sep)

    passed = []
    failed = []

    # 1. Preflight
    print(f"\n[1/3] Preflight 점검 ({broker})")
    rc = _run_script("scripts/stock_d1_preflight.py", ["--broker", broker])
    if rc == 0:
        passed.append("preflight")
        print("  ✔ PASS")
    else:
        failed.append("preflight")
        print("  ✖ FAIL (설정/인증 점검 필요)")
        if strict:
            _print_recovery_summary(broker, passed, failed)
            return False

    # 2. 지원 모드 매트릭스
    print(f"\n[2/3] 지원 모드 매트릭스 점검 ({broker})")
    rc = _run_script("scripts/stock_supported_mode_matrix_check.py", ["--broker", broker])
    if rc == 0:
        passed.append("mode_matrix")
        print("  ✔ PASS")
    else:
        failed.append("mode_matrix")
        print("  ✖ FAIL (api_type/api_version 조합 문제)")
        if strict:
            _print_recovery_summary(broker, passed, failed)
            return False

    # 3. Readiness 체인
    print(f"\n[3/3] Readiness 전체 체인 ({broker})")
    rc = _run_readiness(broker, strict=False)
    if rc == 0:
        passed.append("readiness")
        print("  ✔ PASS")
    else:
        failed.append("readiness")
        print("  ✖ FAIL (실연동 준비 미완)")

    _print_recovery_summary(broker, passed, failed)

    if failed and strict:
        return False
    if "preflight" in failed:
        return False
    return True


def _print_recovery_summary(broker: str, passed: List[str], failed: List[str]) -> None:
    print(f"\n[{_now_str()}] 복구 점검 결과 ({broker})")
    for step in passed:
        print(f"  ✔ {step}")
    for step in failed:
        print(f"  ✖ {step}")

    if not failed:
        print(f"\n  → [{broker}] 복구 검증 통과. 자동매매 재가동 가능.")
    else:
        print(f"\n  → [{broker}] 복구 미완. 다음 조치 후 재시도:")
        if "preflight" in failed:
            print("     - 브로커 인증 정보(app_key/app_secret/id/password) 점검")
            print("     - stock_auto_trading 설정 값 유효성 확인")
        if "mode_matrix" in failed:
            print("     - api_type, api_version 설정 값 점검")
        if "readiness" in failed:
            print("     - stock_live_readiness_run.py --broker {broker} --strict 로 상세 확인")


def _get_all_brokers() -> List[str]:
    supported = ExchangeFactory.get_supported_exchanges().get("stock", [])
    result: List[str] = []
    for b in supported:
        v = str(b or "").strip()
        if v and v not in result:
            result.append(v)
    return result or ["kiwoom", "shinhan", "miraeAsset", "koreaInvestment"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="증권 브로커별 장애 복구 자동화 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python scripts/stock_broker_recovery.py --broker kiwoom
  python scripts/stock_broker_recovery.py --broker kiwoom --strict
  python scripts/stock_broker_recovery.py --all
""",
    )
    parser.add_argument("--broker", default="kiwoom", help="복구 대상 브로커 (기본: kiwoom)")
    parser.add_argument("--all", action="store_true", help="지원 브로커 전체 복구 점검")
    parser.add_argument("--auto-mode", action="store_true", help="예약어(이전 호환성용, 무시됨)")
    parser.add_argument("--strict", action="store_true", help="점검 실패 시 즉시 중단 + exit code 1")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    brokers: List[str] = _get_all_brokers() if bool(getattr(args, "all", False)) else [args.broker]

    overall_pass = True
    results: Dict[str, bool] = {}

    for broker in brokers:
        ok = recover_broker(broker, strict=bool(getattr(args, "strict", False)))
        results[broker] = ok
        if not ok:
            overall_pass = False

    print("\n" + "=" * 60)
    print(f"[{_now_str()}] 전체 복구 점검 결과")
    print("=" * 60)
    for broker, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  {broker:<20} {status}")

    if overall_pass:
        print("\n전체 브로커 복구 검증 통과.")
        sys.exit(0)
    else:
        print("\n일부 브로커 복구 미완. 상세 내용을 확인하세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
