#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""문서/버전 정합성 자동 점검 스크립트.

목적:
- 배포 버전 단일 소스(config/app_version.py)와 UI/문서 표기가 일치하는지 점검
- 임의 버전 상향(문서만 버전 증가) 같은 운영 리스크를 자동 차단
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.app_version import RELEASE_VERSION

TARGETS: Dict[str, Path] = {
    "app_version": ROOT / "config" / "app_version.py",
    "dashboard": ROOT / "ui" / "dashboard_modern.py",
    "manual_widget": ROOT / "ui" / "widgets" / "user_manual_widget.py",
    "user_guide": DOCS / "USER_GUIDE.md",
    "changelog": DOCS / "CHANGELOG.md",
    "policy": DOCS / "DOCUMENTATION_POLICY.md",
}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def check_exists(files: Dict[str, Path]) -> List[str]:
    errors: List[str] = []
    for key, path in files.items():
        if not path.exists():
            errors.append(f"[MISSING] {key}: {path}")
    return errors


def check_release_version_markers(text_map: Dict[str, str]) -> List[str]:
    errors: List[str] = []
    dashboard = text_map.get("dashboard", "")
    manual_widget = text_map.get("manual_widget", "")
    user_guide = text_map.get("user_guide", "")
    policy = text_map.get("policy", "")

    if "self.title(DASHBOARD_TITLE)" not in dashboard:
        errors.append("[DASHBOARD] 대시보드 제목이 DASHBOARD_TITLE 상수를 사용하지 않습니다.")

    if "self.window.title(USER_MANUAL_TITLE)" not in manual_widget:
        errors.append("[MANUAL] 인앱 메뉴얼 제목이 USER_MANUAL_TITLE 상수를 사용하지 않습니다.")

    expected_release_line = f"현재 배포 기준 버전: **v{RELEASE_VERSION}**"
    if expected_release_line not in user_guide:
        errors.append(f"[USER_GUIDE] '{expected_release_line}' 문구가 없습니다.")

    if "배포 버전 변경 없음" not in user_guide:
        errors.append("[USER_GUIDE] 문서 동기화 항목의 '배포 버전 변경 없음' 표기가 없습니다.")

    if "문서 동기화/표현 정정/운영 기준 보강만으로는 버전을 올리지 않는다." not in policy:
        errors.append("[POLICY] 문서 버전 상향 금지 규칙이 없습니다.")

    return errors


def check_for_higher_version_mentions(text_map: Dict[str, str]) -> List[str]:
    errors: List[str] = []
    # RELEASE_VERSION보다 큰 3.8.9.x 버전 표기가 핵심 문서에 있으면 실패
    try:
        release_patch = int(RELEASE_VERSION.split(".")[-1])
    except Exception:
        release_patch = 0
    version_regex = re.compile(r"v?3\.8\.9\.(\d+)")

    for key in ("user_guide", "changelog", "policy"):
        text = text_map.get(key, "")
        for m in version_regex.finditer(text):
            detected_patch = int(m.group(1))
            if detected_patch > release_patch:
                errors.append(f"[VERSION_HIGH] {key}: 배포 버전(v{RELEASE_VERSION})보다 높은 표기 감지 -> {m.group(0)}")
    return errors


def main() -> int:
    missing = check_exists(TARGETS)
    if missing:
        print("문서 정합성 점검: FAIL")
        for e in missing:
            print("-", e)
        return 1

    text_map = {k: read_text(v) for k, v in TARGETS.items()}

    errors: List[str] = []
    errors.extend(check_release_version_markers(text_map))
    errors.extend(check_for_higher_version_mentions(text_map))

    print("문서/버전 정합성 점검 결과")
    print(f"- 기준 배포 버전: v{RELEASE_VERSION}")

    if errors:
        print("\n결과: FAIL")
        for e in errors:
            print("-", e)
        return 1

    print("\n결과: PASS")
    print("- 핵심 표기 일치: dashboard/manual/user_guide/policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
