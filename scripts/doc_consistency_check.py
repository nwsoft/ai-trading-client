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
    "release_notes": ROOT / "RELEASE_NOTES.md",
    "deploy_release_notes": ROOT / "deploy" / "release_notes.md",
    "architecture": DOCS / "ARCHITECTURE.md",
    "update_plan": DOCS / "UPDATE_PLAN.md",
    "execution_guide": ROOT / "USER_GUIDE_AI_EXECUTION.md",
    "test_status": DOCS / "TEST_STATUS.md",
    "readme": ROOT / "README.md",
    "docs_readme": DOCS / "README.md",
    "settings_reference": DOCS / "SETTINGS_REFERENCE_v3.9.0.8.md",
    "ai_custom_architecture": DOCS / "AI_CUSTOM_STRATEGY_ARCHITECTURE.md",
    "assistant_guide": DOCS / "AI_ASSISTANT_GUIDE.md",
    "trading_flow": DOCS / "TRADING_FLOW.md",
    "deploy_checklist": DOCS / "DEPLOY_CHECKLIST.md",
    "master_documentation": DOCS / "MASTER_DOCUMENTATION.md",
    "build_guide": DOCS / "BUILD_GUIDE.md",
    "architecture_audit": DOCS / "ARCHITECTURE_AUDIT_2026-08-01.md",
    "source_quarantine": DOCS / "SOURCE_QUARANTINE_MANIFEST_20260801.md",
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

    app_version = text_map.get("app_version", "")
    if 'RELEASE_HIGHLIGHT = "AI 커스텀 P1~P3 · Windows UI 메뉴·AI 호출·주문 명령 안전화"' not in app_version:
        errors.append("[APP_VERSION] 대시보드 사용자용 최신 업데이트 요약이 현행 변경과 다릅니다.")

    expected_release_line = f"현재 설치 기준 버전: **v{RELEASE_VERSION}**"
    if expected_release_line not in user_guide:
        errors.append(f"[USER_GUIDE] '{expected_release_line}' 문구가 없습니다.")

    if "배포 버전 변경 없음" not in user_guide:
        errors.append("[USER_GUIDE] 문서 동기화 항목의 '배포 버전 변경 없음' 표기가 없습니다.")

    if "문서 동기화/표현 정정/운영 기준 보강만으로는 버전을 올리지 않는다." not in policy:
        errors.append("[POLICY] 문서 버전 상향 금지 규칙이 없습니다.")

    changelog = text_map.get("changelog", "")
    latest_heading = extract_latest_changelog_heading(changelog)
    expected_changelog_tag = f"v{RELEASE_VERSION}"
    if latest_heading is None:
        errors.append("[CHANGELOG] 최신 섹션 제목(## ...)을 찾을 수 없습니다.")
    elif expected_changelog_tag not in latest_heading:
        errors.append(
            f"[CHANGELOG] 최신 섹션 제목에 '{expected_changelog_tag}'가 없습니다. (현재: {latest_heading})"
        )

    return errors


def check_for_higher_version_mentions(text_map: Dict[str, str]) -> List[str]:
    errors: List[str] = []
    # RELEASE_VERSION보다 큰 vX.Y.Z.W 형태 표기가 핵심 문서에 있으면 실패
    release_tuple = parse_version_tuple(RELEASE_VERSION)
    if release_tuple is None:
        return [f"[VERSION_PARSE] RELEASE_VERSION 형식 오류: {RELEASE_VERSION}"]

    version_regex = re.compile(r"v?(\d+)\.(\d+)\.(\d+)\.(\d+)")

    for key in ("user_guide", "changelog", "policy"):
        text = text_map.get(key, "")
        for m in version_regex.finditer(text):
            detected = (
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)),
            )
            if detected > release_tuple:
                errors.append(f"[VERSION_HIGH] {key}: 배포 버전(v{RELEASE_VERSION})보다 높은 표기 감지 -> {m.group(0)}")
    return errors


def check_release_surface_alignment(text_map: Dict[str, str]) -> List[str]:
    """동일 버전의 핵심 변경이 사용자 노출·기술·검증 문서에 함께 있는지 확인한다."""
    if RELEASE_VERSION == "3.9.0.8":
        required = {
            "manual_widget": ("v3.9.0.8 Fix 4 최신 업데이트", "Noah Strategy IR", "초보자·일반·고급·실험실", "PAPER"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.0.8**", "AI Custom Update", "pending_windows_rebuild"),
            "release_notes": ("v3.9.0.8 AI Custom Update Fix 4", "Noah Strategy IR", ".noahstrategy", "pending_windows_rebuild"),
            "deploy_release_notes": ("v3.9.0.8 AI Custom Update Fix 4", "Expression Graph", "pending_windows_rebuild"),
            "update_plan": ("v3.9.0.8 AI Custom Update Fix 2", "AI 어시스턴트", "pending_windows_rebuild"),
            "test_status": ("v3.9.0.8 AI Custom Update Fix 4", "Windows", "PAPER"),
            "readme": ("v3.9.0.8 AI Custom Update Fix 4", "Noah Strategy IR", "pending_windows_rebuild"),
            "docs_readme": ("v3.9.0.8 AI Custom Update Fix 2", "Expression Graph", "pending_windows_rebuild"),
            "deploy_checklist": ("v3.9.0.8 AI Custom Update Fix 2", "pending_windows_rebuild"),
            "master_documentation": ("v3.9.0.8 AI Custom Update Fix 2", "어시스턴트 지식", "Windows 재빌드 전"),
            "build_guide": ("v3.9.0.8 AI Custom Update Fix 2", "v3.9.0.8 AI Custom Update 자산", "pending_windows_rebuild"),
            "ai_custom_architecture": ("v3.9.0.8 AI Custom Update Fix 2", "Noah Strategy IR", "pending_windows_rebuild"),
            "assistant_guide": ("v3.9.0.8 AI Custom Update Fix 2", "백테스트/PAPER", ".noahstrategy"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors

    if RELEASE_VERSION == "3.9.0.7":
        required = {
            "manual_widget": ("v3.9.0.7 최신 업데이트", "Fix Patch 3", "VC 런타임", "LEARNING/PAPER/LIVE"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.0.7**", "Fix Patch 3", "사용자별 verified"),
            "release_notes": ("v3.9.0.7 Fix Patch 3", "VC 런타임", "동적 탭", "Bitget", "dust", "pending_windows_rebuild"),
            "deploy_release_notes": ("v3.9.0.7 Fix Patch 3", "VC 런타임", "pending_windows_rebuild"),
            "architecture": ("v3.9.0.7", "사용자별 암호화 UID", "전역 활성 ∩ 사용자별 verified"),
            "update_plan": ("v3.9.0.7 Fix Patch 3", "VC 런타임", "pending_windows_rebuild"),
            "test_status": ("v3.9.0.7 Fix Patch 3", "pending_windows_rebuild"),
            "readme": ("v3.9.0.7 Fix Patch 3", "사용자별 verified", "pending_windows_rebuild"),
            "docs_readme": ("v3.9.0.7 Fix Patch 3", "pending_windows_rebuild"),
            "deploy_checklist": ("v3.9.0.7 Fix Patch 3", "pending_windows_rebuild"),
            "master_documentation": ("v3.9.0.7", "사용자별 verified UID", "pending_windows_rebuild"),
            "build_guide": ("v3.9.0.7 Fix Patch 3", "VC143", "pending_windows_rebuild"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors

    if RELEASE_VERSION == "3.9.0.6":
        required = {
            "manual_widget": ("v3.9.0.6 최신 업데이트", "통화별 리포트", "200건"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.0.6**", "Source Candidate 2", "200건"),
            "release_notes": ("v3.9.0.6 Source Candidate 2", "inconclusive_currency_boundary", "pending_windows_rebuild"),
            "deploy_release_notes": ("v3.9.0.6 Source Candidate 2", "KRW/USDT", "pending_windows_rebuild"),
            "update_plan": ("v3.9.0.6 Source Candidate 2", "data/260802_Teayu", "Windows 재빌드 필요"),
            "test_status": ("v3.9.0.6 Source Candidate 2", "data/260802_Teayu", "pending_windows_rebuild"),
            "readme": ("v3.9.0.6 Source Candidate 2", "INCIDENT_260802_TEAYU_V3906.md", "pending_windows_rebuild"),
            "docs_readme": ("v3.9.0.6 Source Candidate 2", "pending_windows_rebuild"),
            "deploy_checklist": ("v3.9.0.6 Source Candidate 2", "pending_windows_rebuild"),
            "master_documentation": ("v3.9.0.6", "INCIDENT_260802_TEAYU_V3906.md"),
            "build_guide": ("v3.9.0.6 Source Candidate 2", "pending_windows_rebuild"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors

    if RELEASE_VERSION == "3.9.0.5":
        required = {
            "manual_widget": (
                "v3.9.0.5 최신 업데이트",
                "Fix Patch 5",
                "보유자산",
                "Fix Patch 3",
                "전역 LIVE·해당 증권사 LIVE",
                "실잔고 미사용",
            ),
            "user_guide": (
                "현재 설치 기준 버전: **v3.9.0.5**",
                "v3.9.0.5 Fix Patch 식별",
                "Fix Patch 5",
                "거래소 계좌 화면 보는 법",
                "SOURCE_QUARANTINE_MANIFEST_20260801.md",
                "실잔고 미사용",
            ),
            "release_notes": (
                "v3.9.0.5 Fix Patch 5",
                "1,298 passed",
                "pending_windows_rebuild",
                "SOURCE_QUARANTINE",
            ),
            "deploy_release_notes": (
                "v3.9.0.5 Fix Patch 5",
                "1,298 passed",
                "pending_windows_rebuild",
            ),
            "changelog": (
                "v3.9.0.5 Fix Patch 5",
                "1,298 passed",
                "SOURCE_QUARANTINE_MANIFEST_20260801.md",
            ),
            "update_plan": (
                "Fix Patch 5 최종 개발·정합 마감",
                "active_source_audit.py",
                "pending_windows_rebuild",
            ),
            "test_status": (
                "v3.9.0.5 소스·출시 준비 검증",
                "1,298 passed, 6 skipped",
                "active_source_audit.py",
                "pending_windows_rebuild",
            ),
            "readme": (
                "현재 배포 버전: v3.9.0.5 · 공개 Fix Patch 1 / 현재 작업 소스 Fix Patch 5",
                "1,298 passed",
                "pending_windows_rebuild",
            ),
            "docs_readme": (
                "현재 공개 v3.9.0.5 Fix Patch 1 / 재빌드 대상 소스 Fix Patch 5",
                "SOURCE_QUARANTINE_MANIFEST_20260801.md",
            ),
            "deploy_checklist": (
                "v3.9.0.5",
                "active_source_audit.py",
                "pending_windows_rebuild",
            ),
            "settings_reference": (
                "설정 철학",
                "LEARNING·PAPER·LIVE",
                "더미 설정 정리",
                "거래소·증권사 공통성과 차이",
            ),
            "architecture": (
                "Fix Patch 5",
                "account_state_controller",
                "source_quarantine_manifest.json",
            ),
            "architecture_audit": (
                "Fix Patch 5",
                "1,298 passed",
                "16개 아티팩트",
            ),
            "source_quarantine": (
                "16",
                "SHA-256",
                "theme_system",
            ),
            "master_documentation": (
                "Fix Patch 5",
                "SOURCE_QUARANTINE_MANIFEST_20260801.md",
            ),
            "build_guide": (
                "Fix Patch 5",
                "active_source_audit.py",
                "theme_system",
            ),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors

    if RELEASE_VERSION == "3.9.0.3":
        required = {
            "manual_widget": (
                "v3.9.0.3 업데이트 배포 대상",
                "v3.9.0.2는 이전 고객 배포본",
                "OpenAI·DeepSeek·Anthropic Claude·Google Gemini",
                "사용자 재개 전 신규 주문 잠금",
                "1,128 passed",
            ),
            "user_guide": (
                "현재 업데이트 배포 대상 버전: **v3.9.0.3**",
                "v3.9.0.2 GitHub EXE는 이전 고객 배포본",
                "실제 주문 실행 거래소",
                "1,128 passed",
            ),
            "release_notes": (
                "v3.9.0.3 Windows 업데이트 배포 대상",
                "Anthropic Claude·Google Gemini",
                "pending_windows_rebuild",
                "1,128 passed",
            ),
            "deploy_release_notes": (
                "v3.9.0.3 Windows 업데이트 배포 대상",
                "v3.9.0.2는 이전 Windows 배포본",
                "pending_windows_rebuild",
            ),
            "changelog": (
                "v3.9.0.3 Windows 업데이트 배포 대상",
                "Provider Router",
                "사용자 거래 재개 전 신규 주문 잠금",
            ),
            "update_plan": (
                "v3.9.0.3 업데이트에 멀티 AI API 확장 포함",
                "AlphaArena 멀티 엔진 비교와 실거래 연결만 다음 업데이트",
                "사용자 재개 전 주문 잠금",
            ),
            "execution_guide": (
                "v3.9.0.3 Windows 업데이트 배포 대상",
                "v3.9.0.2는 이전 배포본",
                "실제 주문 실행 거래소",
            ),
            "test_status": (
                "v3.9.0.3 업데이트 배포 대상 검증",
                "v3.9.0.2는 이전 고객 배포본",
                "1128 passed",
                "pending_windows_rebuild",
            ),
            "readme": (
                "현재 배포 버전: v3.9.0.2",
                "v3.9.0.3 업데이트 배포 대상 소스",
                "pending_windows_rebuild",
            ),
            "docs_readme": (
                "현재 배포 v3.9.0.2 / 업데이트 대상 v3.9.0.3",
                "AI_ENGINE_EXPANSION_PLAN_v3.9.0.3.md",
                "pending_windows_rebuild",
            ),
            "deploy_checklist": (
                "v3.9.0.3 안정성·멀티 AI API·AI 커스텀 통합",
                "v3.9.0.2 이전 배포본",
                "authenticode_required=false",
            ),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors

    if RELEASE_VERSION != "3.9.0.2":
        return []
    required = {
        "manual_widget": (
            "직전·현재 캔들 기반 실제 교차",
            "비중첩 단일 포지션",
            "사용자별 감사로그",
            "실제 운용",
            "1,079 passed",
        ),
        "user_guide": (
            "### 2026-07-27 v3.9.0.2",
            "직전·현재 캔들",
            "사용자별 영속 감사로그",
            "실제 체결금액",
            "1,079 passed",
        ),
        "release_notes": (
            "AI 커스텀 실행정합",
            "crossover/crossunder",
            "실제 체결금액",
            "1,079 passed",
            "pending_windows_rebuild",
        ),
        "deploy_release_notes": (
            "2026-07-27 - v3.9.0.2",
            "실제 체결금액",
            "1,079 passed",
            "pending_windows_rebuild",
        ),
        "changelog": (
            "AI 커스텀 실행정합",
            "crosses_above",
            "클라이언트 거래 통계·리포트 운용 지표",
            "1,079 passed",
            "prekey",
        ),
        "architecture": (
            "custom_strategy_validator",
            "PROTECTED_ACTION_REGISTRY",
            "직전·현재 캔들 기반 교차",
        ),
        "update_plan": (
            "P0 진행",
            "crossover/crossunder",
            "보호 작업 레지스트리",
        ),
        "execution_guide": (
            "사용자별 감사로그",
            "실행하지 않았습니다",
            "거래 통계·AI 리포트",
            "1,079 passed",
        ),
        "test_status": (
            "1079 passed",
            "81 passed",
            "prekey",
        ),
        "readme": (
            "통합 배포 준비 버전: v3.9.0.2",
            "실제 체결금액",
            "1,079 passed",
            "보호 작업",
        ),
        "docs_readme": (
            "AI 커스텀·레퍼럴·거래 통계 고도화",
            "실제 체결금액",
            "1,079 passed",
            "pending_windows_rebuild",
        ),
        "ai_custom_architecture": (
            "crosses_above",
            "unsupported_executable_conditions",
            "양방향 슬리피지",
        ),
        "assistant_guide": (
            "사용자별 앱 데이터",
            "보호 작업 레지스트리",
            "실행하지 않았습니다",
        ),
        "trading_flow": (
            "비중첩 포지션",
            "국면 판단 시각",
            "오래된 입력 차단",
        ),
        "deploy_checklist": (
            "unsupported_executable_conditions",
            "settings_change_history.json",
            "현재/후보 국면",
            "USDT·KRW 체결금액",
        ),
        "master_documentation": (
            "v3.9.0.2 릴리스 묶음",
            "RELEASE_NOTES.md",
            "docs/TEST_STATUS.md",
        ),
    }
    errors: List[str] = []
    for surface, markers in required.items():
        text = text_map.get(surface, "")
        for marker in markers:
            if marker not in text:
                errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
    return errors


def parse_version_tuple(version: str) -> tuple[int, int, int, int] | None:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", version.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))


def extract_latest_changelog_heading(changelog_text: str) -> str | None:
    for line in changelog_text.splitlines():
        if line.startswith("## "):
            return line.strip()
    return None


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
    errors.extend(check_release_surface_alignment(text_map))

    print("문서/버전 정합성 점검 결과")
    print(f"- 기준 배포 버전: v{RELEASE_VERSION}")

    if errors:
        print("\n결과: FAIL")
        for e in errors:
            print("-", e)
        return 1

    print("\n결과: PASS")
    print("- 핵심 표기 일치: dashboard/manual/user_guide/policy")
    print(f"- v{RELEASE_VERSION} 변경 표면 일치: README/manual/release/guide/architecture/flow/plan/deploy/test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
