#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""사용자 노출 변경 시 문서/인앱 동기화 강제 점검.

검증 목적:
- 기능(UI/동작) 변경이 있을 때 사용자 안내 문서와 인앱 매뉴얼이 함께 갱신되었는지 확인
- 릴리즈 직전(prekey/release) 게이트에서 누락을 자동 차단
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import List, Sequence, Set

ROOT = Path(__file__).resolve().parents[1]

# 사용자 체감에 영향이 큰 코드 경로
USER_VISIBLE_PREFIXES = (
    "ui/",
    "trading/",
    "api/",
    "main.py",
    "config/",
)

# 문서/비검증 경로
NON_USER_VISIBLE_PREFIXES = (
    "docs/",
    "tests/",
    "scripts/",
    ".github/",
)

# 사용자 노출 변경 시 함께 바뀌어야 하는 필수 동기화 대상
REQUIRED_SYNC_FILES = (
    "docs/CHANGELOG.md",
    "docs/USER_GUIDE.md",
    "USER_GUIDE_AI_EXECUTION.md",
    "ui/widgets/user_manual_widget.py",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NoahAI 사용자 노출 동기화 게이트")
    parser.add_argument(
        "--base-ref",
        default="HEAD~1",
        help="비교 기준 git ref (기본: HEAD~1)",
    )
    parser.add_argument(
        "--changed-files",
        default="",
        help="git 대신 직접 전달할 변경 파일 목록(쉼표 구분)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="변경 파일 수집 불가 시 실패 처리",
    )
    return parser.parse_args()


def _run_git(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip()


def _parse_changed_files_arg(value: str) -> Set[str]:
    if not value.strip():
        return set()
    return {_normalize(part) for part in value.split(",") if part.strip()}


def _collect_changed_files_from_git(base_ref: str) -> tuple[Set[str], str]:
    probe = _run_git(["rev-parse", "--is-inside-work-tree"])
    if probe.returncode != 0 or "true" not in (probe.stdout or "").lower():
        return set(), "git 작업공간을 찾을 수 없습니다"

    changed: Set[str] = set()

    # 최근 기준 ref와의 차이(가능한 경우)
    base_diff = _run_git(["diff", "--name-only", "--diff-filter=ACMRTUXB", f"{base_ref}...HEAD"])
    if base_diff.returncode == 0:
        changed.update(_normalize(line) for line in (base_diff.stdout or "").splitlines() if line.strip())

    # 작업중 변경 + stage 변경 + untracked
    for args in (
        ["diff", "--name-only", "--diff-filter=ACMRTUXB"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMRTUXB"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        result = _run_git(args)
        if result.returncode == 0:
            changed.update(_normalize(line) for line in (result.stdout or "").splitlines() if line.strip())

    return changed, ""


def _is_user_visible_change(path: str) -> bool:
    if any(path.startswith(prefix) for prefix in NON_USER_VISIBLE_PREFIXES):
        return False
    return any(path.startswith(prefix) for prefix in USER_VISIBLE_PREFIXES)


def main() -> int:
    args = _parse_args()

    changed_files = _parse_changed_files_arg(args.changed_files)
    source = "--changed-files"
    if not changed_files:
        env_changed = _parse_changed_files_arg(os.environ.get("SYNC_GUARD_CHANGED_FILES", ""))
        if env_changed:
            changed_files = env_changed
            source = "SYNC_GUARD_CHANGED_FILES"

    if not changed_files:
        changed_files, error = _collect_changed_files_from_git(args.base_ref)
        source = f"git({args.base_ref})"
        if error:
            print("SYNC_GUARD: WARN")
            print(f"- 변경 파일 수집 실패: {error}")
            print("- 해결: git 작업공간에서 실행하거나 --changed-files/환경변수(SYNC_GUARD_CHANGED_FILES) 사용")
            return 1 if args.strict else 0

    print("SYNC_GUARD: INFO")
    print(f"- 변경 파일 수집 경로: {source}")
    print(f"- 변경 파일 수: {len(changed_files)}")

    if not changed_files:
        print("SYNC_GUARD: PASS")
        print("- 감지된 변경 없음")
        return 0

    user_visible_changes = sorted(path for path in changed_files if _is_user_visible_change(path))
    if not user_visible_changes:
        print("SYNC_GUARD: PASS")
        print("- 사용자 노출 변경 없음 (문서/테스트/스크립트 범위 변경)")
        return 0

    missing = [path for path in REQUIRED_SYNC_FILES if path not in changed_files]

    print("- 사용자 노출 변경 파일:")
    for path in user_visible_changes:
        print(f"  - {path}")

    if missing:
        print("SYNC_GUARD: FAIL")
        print("- 사용자 노출 변경이 감지되었지만 필수 동기화 파일이 누락되었습니다:")
        for path in missing:
            print(f"  - {path}")
        print("- 해결: 기능 변경과 동시에 문서+인앱 메뉴얼 4종을 같은 배치에서 수정하세요")
        return 1

    print("SYNC_GUARD: PASS")
    print("- 사용자 노출 변경 + 문서/인앱 동기화 파일 반영 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
