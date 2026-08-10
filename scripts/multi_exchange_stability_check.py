#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""다중 거래소 안정성 원샷 점검 스크립트.

목적:
- 실계정 없이 코인 오염/시작 상태 오표시/학습 저장 경합 관련 회귀를 빠르게 점검한다.
- 배포 전 반복 가능한 단일 명령을 제공한다.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
_VENV_WIN = ROOT / ".venv" / "Scripts" / "python.exe"
_VENV_UNIX = ROOT / ".venv" / "bin" / "python"
PYTHON = str(_VENV_WIN if _VENV_WIN.exists() else (_VENV_UNIX if _VENV_UNIX.exists() else sys.executable))

REPORT_DIR = ROOT / "data" / "reports"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="다중 거래소 안정성 원샷 점검")
    parser.add_argument("--skip-compile", action="store_true", help="py_compile 단계 생략")
    parser.add_argument("--skip-pytest", action="store_true", help="pytest 회귀 단계 생략")
    parser.add_argument("--no-write-report", action="store_true", help="JSON 리포트 파일 저장 생략")
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


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _check_source_invariants() -> List[str]:
    """재발 방지용 소스 불변 조건을 점검한다."""
    issues: List[str] = []

    ut_path = ROOT / "trading" / "unified_trader.py"
    db_path = ROOT / "ui" / "dashboard_modern.py"
    ev_path = ROOT / "trading" / "evaluator.py"
    main_path = ROOT / "main.py"
    ai_settings_path = ROOT / "ui" / "settings_modern.py"

    ut = _read_text(ut_path)
    db = _read_text(db_path)
    ev = _read_text(ev_path)
    main_source = _read_text(main_path)
    ai_settings = _read_text(ai_settings_path)

    if "selected_coins = list(selected_store.get(exchange_name, []) or [])" not in ut:
        issues.append("unified_trader: 거래소별 selected_coins 우선 사용 코드 누락")

    if "new_coins = list(self.select_trading_coins_unified(exchange_name) or [])" not in ut:
        issues.append("unified_trader: 거래소별 재선택 호출 코드 누락")

    if "elm = self._learning_managers.get(exchange_name)" not in ut:
        issues.append("unified_trader: 거래소별 학습 매니저 캐시 사용 코드 누락")

    if "legacy_selected = getattr(getattr(self, 'main_app', None), 'selected_coins'" in ut:
        issues.append("unified_trader: 전역 main_app.selected_coins 폴백 경로 잔존")
    if "elif isinstance(selected_store, list):" in ut:
        issues.append("unified_trader: 전역 list형 selected_coins 호환 경로 잔존")
    if "def set_selected_coins(self, selected_coins" in ut:
        issues.append("unified_trader: 거래소 인자 없는 선택 코인 주입 API 잔존")

    if "started = bool(self.main_app.on_start_exchange(e))" not in db:
        issues.append("dashboard_modern: 개별 토글 시작 bool 판정 코드 누락")

    # 전역 오케스트레이션은 정책상 제거됨.
    has_legacy_orchestration = "_run_global_orchestration_job" in db or "_execute_exchange_actions_parallel" in db
    has_policy_marker = "전역 전체 시작/정지 기능은 제거되었습니다." in db
    if has_legacy_orchestration:
        issues.append("dashboard_modern: 제거 대상 전역 오케스트레이션 코드 잔존")
    if not has_policy_marker:
        issues.append("dashboard_modern: 전역 제어 제거 정책 안내 문구 누락")

    if "self.log_event('analysis', f\"{exchange_name} 시장 분석 시작" not in ut:
        issues.append("unified_trader: 시장 분석 시작 로그 경로 점검 필요")
    if "exchange=exchange_name" not in ut:
        issues.append("unified_trader: 거래소별 로그 태깅(exchange=exchange_name) 누락")

    if "major_bases = {'BTC', 'ETH', 'BNB', 'SOL', 'ADA', 'XRP', 'DOT', 'LINK', 'AVAX', 'MATIC'}" not in ev:
        issues.append("evaluator: 포맷 독립 메이저 코인 분류 코드 누락")

    if "is_crypto_derivative_candidate(" not in ev:
        issues.append("evaluator: 토큰화 비암호화 상품 metadata 필터 누락")

    if "create_ai_manager_from_settings(" not in main_source:
        issues.append("main: 선택 Provider 기준 AIManager 초기화 경계 누락")

    if 'provider == "kimi" and scope != "assistant"' in ai_settings:
        issues.append("settings_modern: Kimi 작업별 라우팅 구버전 차단 잔존")

    return issues


def _write_report(report: Dict[str, object]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    latest_path = REPORT_DIR / "multi_exchange_stability_latest.json"
    archive_path = REPORT_DIR / f"multi_exchange_stability_{ts}.json"

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    latest_path.write_text(payload, encoding="utf-8")
    archive_path.write_text(payload, encoding="utf-8")


def main() -> int:
    args = _parse_args()

    failures: List[str] = []
    notes: List[str] = []
    steps: List[Dict[str, object]] = []

    if not args.skip_compile:
        rc, out = _run_step(
            "COMPILE",
            [
                PYTHON,
                "-m",
                "py_compile",
                "trading/unified_trader.py",
                "ui/dashboard_modern.py",
                "trading/evaluator.py",
                "trading/market_asset_classifier.py",
                "trading/ai/ai_manager.py",
                "trading/ai/provider_router.py",
                "main.py",
            ],
        )
        steps.append({"name": "COMPILE", "returncode": rc, "ok": rc == 0})
        if rc != 0:
            failures.append("COMPILE")
            notes.append(out)

    if not args.skip_pytest:
        rc, out = _run_step(
            "PYTEST_E2E",
            [
                PYTHON,
                "-m",
                "pytest",
                "tests/test_dashboard_full_button_e2e.py",
                "tests/test_e2e_ai_execute_flow.py",
                "-q",
                "--tb=no",
            ],
        )
        steps.append({"name": "PYTEST_E2E", "returncode": rc, "ok": rc == 0})
        if rc != 0:
            failures.append("PYTEST_E2E")
            notes.append(out)

    invariant_issues = _check_source_invariants()
    print("\n[SOURCE_INVARIANTS]")
    if invariant_issues:
        for item in invariant_issues:
            print(f"- FAIL: {item}")
        failures.append("SOURCE_INVARIANTS")
    else:
        print("PASS | 핵심 불변조건 충족")
    steps.append({"name": "SOURCE_INVARIANTS", "ok": not invariant_issues, "issues": invariant_issues})

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": PYTHON,
        "steps": steps,
        "status": "FAIL" if failures else "PASS",
        "failures": failures,
        "notes": notes,
    }

    if not args.no_write_report:
        _write_report(report)

    print("\n[FINAL]")
    if failures:
        print(f"FAIL | {', '.join(failures)}")
        return 1

    print("PASS | multi-exchange stability check completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
