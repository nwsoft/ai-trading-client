#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""문서/버전 정합성 자동 점검 스크립트.

목적:
- 배포 버전 단일 소스(config/app_version.py)와 UI/문서 표기가 일치하는지 점검
- 임의 버전 상향(문서만 버전 증가) 같은 운영 리스크를 자동 차단
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.app_version import RELEASE_HIGHLIGHT, RELEASE_VERSION

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
    "marketplace_plan": DOCS / "STRATEGY_MARKETPLACE_POINTS_AND_LICENSE_PLAN.md",
    "release_manifest": ROOT / "deploy" / "release-manifest.json",
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
    if f'RELEASE_HIGHLIGHT = "{RELEASE_HIGHLIGHT}"' not in app_version:
        errors.append("[APP_VERSION] 대시보드 사용자용 최신 업데이트 요약이 현행 변경과 다릅니다.")

    expected_release_lines = (
        f"현재 설치 기준 버전: **v{RELEASE_VERSION}**",
        f"현재 공개 버전: **v{RELEASE_VERSION}**",
        f"현재 소스 후보 버전: **v{RELEASE_VERSION}**",
    )
    if not any(line in user_guide for line in expected_release_lines):
        errors.append(
            f"[USER_GUIDE] 현재 설치/공개/소스 후보 v{RELEASE_VERSION} 문구가 없습니다."
        )

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


def check_current_release_and_marketplace(text_map: Dict[str, str]) -> List[str]:
    """Keep current public identity and monetization policy out of historical drift."""
    errors: List[str] = []
    try:
        manifest = json.loads(text_map.get("release_manifest", ""))
    except (TypeError, ValueError):
        return ["[RELEASE_MANIFEST] JSON을 읽을 수 없습니다."]

    manifest_version = str(manifest.get("version") or "")
    manifest_tuple = parse_version_tuple(manifest_version)
    source_tuple = parse_version_tuple(RELEASE_VERSION)
    if manifest_tuple is None:
        errors.append("[RELEASE_MANIFEST] 공개 version 형식이 올바르지 않습니다.")
    elif source_tuple is not None and manifest_tuple > source_tuple:
        errors.append("[RELEASE_MANIFEST] 공개 version이 현재 소스 후보보다 높습니다.")

    if manifest.get("publish_ready") is True:
        required_public = {
            "readme": f"현재 공개 기반: v{manifest_version}",
            "docs_readme": f"v{manifest_version}",
            "release_notes": f"공개 v{manifest_version}",
            "user_guide": f"현재 공개 버전: **v{manifest_version}**",
            "test_status": f"v{manifest_version}",
        }
        for surface, marker in required_public.items():
            if marker not in text_map.get(surface, "")[:6000]:
                errors.append(f"[PUBLIC_RELEASE] {surface}: '{marker}' 누락")

        user_guide_head = text_map.get("user_guide", "")[:6000]
        if len(re.findall(r"^현재 공개 버전:", user_guide_head, flags=re.MULTILINE)) != 1:
            errors.append("[PUBLIC_RELEASE] USER_GUIDE 상단의 '현재 공개 버전'은 정확히 한 줄이어야 합니다.")

    marketplace = text_map.get("marketplace_plan", "")
    for marker in (
        "무료 상품 스냅샷",
        "플랫폼 기본 수수료",
        "유상 Noah Point",
        "Evidence의 약자",
        "1P = 1원 구매가치",
        "10,000,000P 이상",
        "daltrading 관리자 운영 콘솔",
        "모바일 앱스토어는 현재 범위가 아님",
        "하루 첫 유효 PAPER 60분",
        "T+30",
        "코인 결제",
        "출시 금지 조건",
    ):
        if marker not in marketplace:
            errors.append(f"[MARKETPLACE_POLICY] '{marker}' 누락")
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
    if RELEASE_VERSION == "3.9.1.42":
        required = {
            "manual_widget": ("v3.9.1.42 최신 업데이트", "원격 권한 저장", "비밀번호 재확인"),
            "user_guide": ("현재 소스 후보 버전: **v3.9.1.42**", "3.9.142", "REMOTE_MANAGEMENT_GUIDE_V39142.md"),
            "release_notes": ("v3.9.1.42", "공개 v3.9.1.41"),
            "deploy_release_notes": ("NoahAI v3.9.1.42", "3.9.142"),
            "build_guide": ("3.9.142", "V39142_REMOTE_CONTROL_PLAN.md"),
            "test_status": ("v3.9.1.42", "Windows", "미완료"),
            "readme": ("현재 소스 후보: v3.9.1.42", "현재 공개 기반: v3.9.1.41"),
        }
        return [f"[RELEASE_SURFACE] {surface}: '{marker}' 누락"
                for surface, markers in required.items() for marker in markers
                if marker not in text_map.get(surface, "")]
    if RELEASE_VERSION == "3.9.1.41":
        required = {
            "manual_widget": ("v3.9.1.41 최신 업데이트", "관찰 후보 XAI 비교", "공개 stable/latest는 v3.9.1.40"),
            "user_guide": ("현재 소스 후보 버전: **v3.9.1.41**", "3.9.141", "V39141_MARKET_TREND_XAI_TEST_PLAN.md"),
            "release_notes": ("v3.9.1.41 Market Trend Visuals", "공개 stable/latest는 **v3.9.1.40**"),
            "changelog": ("V39141_MARKET_TREND_XAI_TEST_PLAN.md", "관찰 후보"),
            "build_guide": ("3.9.141", "V39141_MARKET_TREND_XAI_TEST_PLAN.md"),
            "test_status": ("v3.9.1.41", "Windows", "미완료"),
            "deploy_checklist": ("v3.9.1.41", "3.9.141", "v3.9.1.40"),
            "readme": ("현재 소스 후보: v3.9.1.41", "현재 공개 기반: v3.9.1.40"),
        }
        return [f"[RELEASE_SURFACE] {surface}: '{marker}' 누락"
                for surface, markers in required.items() for marker in markers
                if marker not in text_map.get(surface, "")]
    if RELEASE_VERSION == "3.9.1.40":
        required = {
            "manual_widget": ("v3.9.1.40 최신 업데이트", "PAPER 판단 실험", "선택 모델 1회 실제 호출 점검"),
            "user_guide": ("현재 소스 후보 버전: **v3.9.1.40**", "3.9.140"),
            "release_notes": ("v3.9.1.40", "공개 stable/latest는 **v3.9.1.39**"),
            "changelog": ("V39140_STUDIO_ALPHA_SETTINGS_TEST_PLAN.md",),
            "build_guide": ("3.9.140", "V39140_STUDIO_ALPHA_SETTINGS_TEST_PLAN.md"),
            "test_status": ("v3.9.1.40", "Windows", "미완료"),
            "readme": ("현재 소스 후보: v3.9.1.40", "현재 공개 기반: v3.9.1.39"),
        }
        return [f"[RELEASE_SURFACE] {surface}: '{marker}' 누락"
                for surface, markers in required.items() for marker in markers
                if marker not in text_map.get(surface, "")]
    if RELEASE_VERSION == "3.9.1.39":
        required = {
            "manual_widget": ("v3.9.1.39 최신 업데이트", "거래소 체결 동기화", "대조 전"),
            "user_guide": ("현재 소스 후보 버전: **v3.9.1.39**", "3.9.139", "외부 TP/SL"),
            "release_notes": ("v3.9.1.39 External Close Ledger Reconciliation", "공개 stable/latest는 **v3.9.1.38**"),
            "changelog": ("V39139_EXTERNAL_CLOSE_RECONCILIATION_TEST_PLAN.md", "exit_order_id"),
            "build_guide": ("3.9.139", "V39139_EXTERNAL_CLOSE_RECONCILIATION_TEST_PLAN.md"),
            "test_status": ("v3.9.1.39", "Windows", "미완료"),
            "deploy_checklist": ("v3.9.1.39", "3.9.139", "현재 공개 버전: **v3.9.1.38**"),
            "readme": ("현재 소스 후보: v3.9.1.39", "현재 공개 기반: v3.9.1.38"),
            "architecture": ("v3.9.1.39", "exact-order"),
        }
        return [f"[RELEASE_SURFACE] {surface}: '{marker}' 누락"
                for surface, markers in required.items() for marker in markers
                if marker not in text_map.get(surface, "")]
    if RELEASE_VERSION == "3.9.1.38":
        required = {
            "manual_widget": ("v3.9.1.38 최신 업데이트", "v3.9.1.37 이전 업데이트", "기본 접힘"),
            "user_guide": ("현재 소스 후보 버전: **v3.9.1.38**", "3.9.138", "기관별 거래내역"),
            "release_notes": ("v3.9.1.38 Strategy Replay", "공개 stable/latest는 **v3.9.1.37**"),
            "deploy_release_notes": ("NoahAI v3.9.1.38", "3.9.138"),
            "changelog": ("V39138_STRATEGY_REPLAY_LIVE_HISTORY_TEST_PLAN.md", "SOURCE_TRADE_HISTORY_20260917.md"),
            "build_guide": ("3.9.138", "V39138_STRATEGY_REPLAY_LIVE_HISTORY_TEST_PLAN.md"),
            "test_status": ("v3.9.1.38", "Windows", "미완료"),
            "deploy_checklist": ("v3.9.1.38", "3.9.138", "현재 공개 버전: **v3.9.1.37**"),
            "readme": ("현재 소스 후보: v3.9.1.38", "현재 공개 기반: v3.9.1.37"),
            "architecture": ("v3.9.1.38", "기관별 LIVE 이력"),
        }
        return [f"[RELEASE_SURFACE] {surface}: '{marker}' 누락"
                for surface, markers in required.items() for marker in markers
                if marker not in text_map.get(surface, "")]
    if RELEASE_VERSION == "3.9.1.37":
        required = {
            "manual_widget": ("v3.9.1.37 최신 업데이트", "v3.9.1.36 이전 업데이트", "v3.9.1.35 이전 업데이트"),
            "user_guide": ("현재 소스 후보 버전: **v3.9.1.37**", "3.9.137"),
            "release_notes": ("v3.9.1.37", "공개 v3.9.1.36"),
            "changelog": ("V39137_KIWOOM_BOUNDED_QUERIES_TEST_PLAN.md",),
            "build_guide": ("3.9.137", "V39137_KIWOOM_BOUNDED_QUERIES_TEST_PLAN.md"),
            "test_status": ("v3.9.1.37", "Windows", "미완료"),
        }
        return [f"[RELEASE_SURFACE] {surface}: '{marker}' 누락"
                for surface, markers in required.items() for marker in markers
                if marker not in text_map.get(surface, "")]
    if RELEASE_VERSION == "3.9.1.34":
        required = {
            "manual_widget": ("v3.9.1.34 최신 업데이트", "32비트 호스트"),
            "user_guide": ("현재 소스 후보 버전: **v3.9.1.34**", "현재 공개 버전: **v3.9.1.33**"),
            "release_notes": ("v3.9.1.34 Kiwoom x86", "3.9.134", "공개 v3.9.1.33"),
            "deploy_release_notes": ("NoahAI v3.9.1.34 Kiwoom x86", "3.9.134", "prerelease"),
            "changelog": ("v3.9.1.34", "source fingerprint", "V39134_KIWOOM_X86_RELEASE_INTEGRITY_TEST_PLAN.md"),
            "readme": ("현재 소스 후보: v3.9.1.34", "현재 공개 기반: v3.9.1.33"),
            "architecture": ("v3.9.1.34", "전용 x86 호스트"),
            "test_status": ("v3.9.1.34", "키움 OCX", "미완료"),
            "deploy_checklist": ("v3.9.1.34", "3.9.134", "공개 안정판: **v3.9.1.33**"),
            "build_guide": ("3.9.134", "NoahAIKiwoomHost.exe", "requirements_kiwoom_x86.txt", "prerelease"),
        }
        return [f"[RELEASE_SURFACE] {surface}: '{marker}' 누락"
                for surface, markers in required.items() for marker in markers
                if marker not in text_map.get(surface, "")]
    if RELEASE_VERSION == "3.9.1.33":
        required = {
            "manual_widget": ("v3.9.1.33 최신 업데이트", "증권 AI 학습", "32비트 호스트"),
            "user_guide": ("현재 소스 후보 버전: **v3.9.1.33**", "현재 공개 버전: **v3.9.1.32**"),
            "release_notes": ("v3.9.1.33 Evidence", "3.9.133", "미배포 후보"),
            "changelog": ("v3.9.1.33", "미배포 후보", "V39132_USER_FEEDBACK_AUDIT.md"),
            "readme": ("현재 소스 후보: v3.9.1.33", "현재 공개 기반: v3.9.1.32"),
            "architecture": ("v3.9.1.33", "증권사별 학습 DB"),
            "test_status": ("v3.9.1.33", "Windows", "미완료"),
            "deploy_checklist": ("v3.9.1.33", "3.9.133", "공개 v3.9.1.32"),
            "build_guide": ("3.9.133", "v3.9.1.33", "NoahAIKiwoomHost.exe"),
        }
        return [f"[RELEASE_SURFACE] {surface}: '{marker}' 누락"
                for surface, markers in required.items() for marker in markers
                if marker not in text_map.get(surface, "")]
    if RELEASE_VERSION == "3.9.1.32":
        required = {
            "manual_widget": ("v3.9.1.32 최신 업데이트", "다음 예약", "후보 점수"),
            "user_guide": ("현재 소스 후보 버전: **v3.9.1.32**", "현재 공개 버전: **v3.9.1.31**"),
            "release_notes": ("v3.9.1.32 Runtime Recovery", "공개 v3.9.1.31"),
            "changelog": ("v3.9.1.32", "fetch_tickers(symbols)", "정본 재추출"),
            "readme": ("현재 소스 후보: v3.9.1.32", "현재 공개 기반: v3.9.1.31"),
            "architecture": ("update-scheduler.cjs", "kis_market_master.py", "runtime_observability.py"),
            "test_status": ("v3.9.1.32", "V39132_RUNTIME_RECOVERY_TEST_PLAN.md"),
            "deploy_checklist": ("v3.9.1.32", "V39132_RUNTIME_RECOVERY_TEST_PLAN.md"),
            "build_guide": ("3.9.132", "v3.9.1.32"),
        }
        return [f"[RELEASE_SURFACE] {surface}: '{marker}' 누락"
                for surface, markers in required.items() for marker in markers
                if marker not in text_map.get(surface, "")]
    if RELEASE_VERSION == "3.9.1.31":
        required = {
            "manual_widget": ("v3.9.1.31 최신 업데이트", "11개 메뉴얼", "AlphaArena는 이 후보에서 PAPER"),
            "user_guide": ("v3.9.1.31 메뉴얼", "현재 소스 후보 버전: **v3.9.1.31**", "현재 공개 버전: **v3.9.1.30**"),
            "release_notes": ("v3.9.1.31 Readable Manual Experience Patch", "PAPER 판단·결과 기록"),
            "changelog": ("v3.9.1.31 대시보드 메뉴얼 전 탭", "정본 재추출"),
            "readme": ("현재 소스 후보: v3.9.1.31", "현재 공개 기반: v3.9.1.30"),
            "docs_readme": ("v3.9.1.31 소스 후보", "공개 v3.9.1.30"),
            "architecture": ("현재 소스 후보 v3.9.1.31", "사용자 메뉴얼 정본 계약"),
            "update_plan": ("v3.9.1.31 사용자 메뉴얼 정본", "Windows 100/125/150/175% DPI"),
            "test_status": ("v3.9.1.31 사용자 메뉴얼 정본", "68 passed"),
            "deploy_checklist": ("v3.9.1.31 패치 필수 게이트", "11개 고유 탭"),
            "master_documentation": ("v3.9.1.31 소스 후보", "11개 정본의 생성"),
            "build_guide": ("v3.9.1.31 Readable Manual Experience 소스 후보", "3.9.131"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors
    if RELEASE_VERSION == "3.9.1.15":
        required = {
            "manual_widget": ("v3.9.1.15 최신 업데이트", "[v3.9.1.15 Web UI]", "상태형 포지션"),
            "user_guide": ("현재 소스 후보 버전: **v3.9.1.15**", "3.9.115", "신규 주문을 보류"),
            "release_notes": ("v3.9.1.15 Web UI Order Contract, Strategy Studio Level 4 & Binance Cycle Integrity Patch", "3.9.115", "5.10 USDT", "계정의 쓰기 가능한"),
            "deploy_release_notes": ("NoahAI v3.9.1.15 Web UI Order Contract, Strategy Studio Level 4 & Binance Cycle Integrity Patch", "3.9.115", "Level 4"),
            "changelog": ("v3.9.1.15 주문규격 정합·Strategy Studio Level 4·Binance 사이클 복구", "3.9.115"),
            "readme": ("v3.9.1.15 Web UI Order Contract, Strategy Studio Level 4 & Binance Cycle Integrity Patch · Windows 재빌드 전",),
            "build_guide": ("v3.9.1.15 Web UI Order Contract, Strategy Studio Level 4 & Binance Cycle Integrity Patch", "V39115_ORDER_CONTRACT_LEVEL4_STRATEGY_HUB.md", "3.9.115"),
            "deploy_checklist": ("v3.9.1.15 Web UI Order Contract, Strategy Studio Level 4 & Binance Cycle Integrity Patch", "V39115_ORDER_CONTRACT_LEVEL4_STRATEGY_HUB.md"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors
    if RELEASE_VERSION == "3.9.1.14":
        required = {
            "manual_widget": ("v3.9.1.14 최신 업데이트", "[v3.9.1.14 Web UI]", "이전 정상 점수 후보"),
            "user_guide": ("현재 소스 후보 버전: **v3.9.1.14**", "3.9.114", "기본 60초"),
            "release_notes": ("v3.9.1.14 Web UI Selection Recovery & Broker Lifecycle Patch", "3.9.114", "기존 정상 후보"),
            "deploy_release_notes": ("NoahAI v3.9.1.14 Web UI Selection Recovery & Broker Lifecycle Patch", "3.9.114", "V39114_SELECTION_RECOVERY_BROKER_LIFECYCLE_TEST_PLAN.md"),
            "changelog": ("v3.9.1.14 후보 선정 복구·증권 조회 연결", "3.9.114"),
            "readme": ("v3.9.1.14 Web UI Selection Recovery & Broker Lifecycle Patch · Windows 재빌드 전",),
            "build_guide": ("v3.9.1.14 Web UI Selection Recovery & Broker Lifecycle Patch", "V39114_SELECTION_RECOVERY_BROKER_LIFECYCLE_TEST_PLAN.md", "3.9.114"),
            "deploy_checklist": ("v3.9.1.14 Web UI Selection Recovery & Broker Lifecycle Patch", "V39114_SELECTION_RECOVERY_BROKER_LIFECYCLE_TEST_PLAN.md"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors
    if RELEASE_VERSION == "3.9.1.13":
        required = {
            "manual_widget": ("v3.9.1.13 최신 업데이트", "[v3.9.1.13 Web UI]", "숨은 PAPER"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.1.13**", "3.9.113", "112%"),
            "release_notes": ("v3.9.1.13 Web UI OKX Shutdown, Accessibility & Validation Clarity Patch", "3.9.113", "worker"),
            "deploy_release_notes": ("NoahAI v3.9.1.13 Web UI OKX Shutdown, Accessibility & Validation Clarity Patch", "3.9.113", "V39113_OKX_UI_ACCESSIBILITY_TEST_PLAN.md"),
            "changelog": ("v3.9.1.13 OKX 안전 종료·가독성·PAPER", "3.9.113"),
            "readme": ("v3.9.1.13 Web UI OKX Shutdown, Accessibility & Validation Clarity Patch · Windows 재빌드 전",),
            "build_guide": ("v3.9.1.13 Web UI OKX Shutdown, Accessibility & Validation Clarity Patch", "V39113_OKX_UI_ACCESSIBILITY_TEST_PLAN.md", "3.9.113"),
            "deploy_checklist": ("v3.9.1.13 Web UI OKX Shutdown, Accessibility & Validation Clarity Patch", "V39113_OKX_UI_ACCESSIBILITY_TEST_PLAN.md"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors
    if RELEASE_VERSION == "3.9.1.12":
        required = {
            "manual_widget": ("v3.9.1.12 최신 업데이트", "[v3.9.1.12 Web UI]", "회원 전략 제출", "검증 여권"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.1.12**", "3.9.112", "허브에 제출"),
            "release_notes": ("v3.9.1.12 Web UI Strategy Hub, Manual & Trust Patch", "3.9.112", "자동 업로드"),
            "deploy_release_notes": ("NoahAI v3.9.1.12 Web UI Strategy Hub, Manual & Trust Patch", "3.9.112", "V39112_STRATEGY_HUB_MANUAL_TRUST_TEST_PLAN.md"),
            "changelog": ("v3.9.1.12 전략 허브·메뉴얼·검증 신뢰", "3.9.112"),
            "readme": ("v3.9.1.12 Web UI Strategy Hub, Manual & Trust Patch · Windows 재빌드 전",),
            "build_guide": ("v3.9.1.12 Web UI Strategy Hub, Manual & Trust Patch", "V<버전숫자>_*_TEST_PLAN.md", "3.9.112"),
            "deploy_checklist": ("v3.9.1.12 Web UI Strategy Hub, Manual & Trust Patch", "V39112_STRATEGY_HUB_MANUAL_TRUST_TEST_PLAN.md"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors
    if RELEASE_VERSION == "3.9.1.11":
        required = {
            "manual_widget": ("v3.9.1.11 최신 업데이트", "[v3.9.1.11 Web UI]", "PAPER TP/SL"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.1.11**", "3.9.111", "관찰 일수"),
            "release_notes": ("v3.9.1.11 Web UI Safe Shutdown & PAPER Validation Integrity Patch", "3.9.111", "45초"),
            "deploy_release_notes": ("NoahAI v3.9.1.11 Web UI Safe Shutdown & PAPER Validation Integrity Patch", "3.9.111", "V39111_SAFE_SHUTDOWN_PAPER_VALIDATION_TEST_PLAN.md"),
            "changelog": ("v3.9.1.11 안전 종료·PAPER 검증 정합", "3.9.111"),
            "readme": ("v3.9.1.11 Web UI Safe Shutdown & PAPER Validation Integrity Patch · Windows 재빌드 전",),
            "build_guide": ("v3.9.1.11 Web UI Safe Shutdown & PAPER Validation Integrity Patch", "V<버전숫자>_*_TEST_PLAN.md", "3.9.111"),
            "deploy_checklist": ("v3.9.1.11 Web UI Safe Shutdown & PAPER Validation Integrity Patch", "V39111_SAFE_SHUTDOWN_PAPER_VALIDATION_TEST_PLAN.md"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors
    if RELEASE_VERSION == "3.9.1.10":
        required = {
            "manual_widget": ("v3.9.1.10 최신 업데이트", "[v3.9.1.10 Web UI]", "가상 거래 통계"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.1.10**", "3.9.110", "가상 포지션"),
            "release_notes": ("v3.9.1.10 Web UI PAPER Position, Statistics & Notifications Patch", "3.9.110", "Discord", "tail-read"),
            "deploy_release_notes": ("NoahAI v3.9.1.10 Web UI PAPER Position, Statistics & Notifications Patch", "3.9.110", "V39110_PAPER_POSITION_POLICY_STATISTICS_TEST_PLAN.md"),
            "changelog": ("v3.9.1.10 PAPER 포지션·가상 통계·외부 알림", "3.9.110"),
            "readme": ("v3.9.1.10 Web UI PAPER Position, Statistics & Notifications Patch · Windows 재빌드 전",),
            "build_guide": ("v3.9.1.10 Web UI PAPER Position, Statistics & Notifications Patch", "V<버전숫자>_*_TEST_PLAN.md", "3.9.110"),
            "deploy_checklist": ("v3.9.1.10 Web UI PAPER Position, Statistics & Notifications Patch", "V39110_PAPER_POSITION_POLICY_STATISTICS_TEST_PLAN.md"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors
    if RELEASE_VERSION == "3.9.1.9":
        required = {
            "manual_widget": ("v3.9.1.9 최신 업데이트", "[v3.9.1.9 Web UI]", "PAPER 전진검증"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.1.9**", "3.9.109", "PAPER 전진검증"),
            "release_notes": ("v3.9.1.9 Web UI PAPER Validation & Grounded Assistant Patch", "3.9.109", "AI 어시스턴트"),
            "deploy_release_notes": ("NoahAI v3.9.1.9 Web UI PAPER Validation & Grounded Assistant Patch", "3.9.109", "V3919_PAPER_VALIDATION_GROUNDED_ASSISTANT_TEST_PLAN.md"),
            "changelog": ("v3.9.1.9 PAPER 전진검증", "3.9.109"),
            "readme": ("v3.9.1.9 Web UI PAPER Validation & Grounded Assistant Patch · Windows 재빌드 전",),
            "build_guide": ("v3.9.1.9 Web UI PAPER Validation & Grounded Assistant Patch", "V<버전숫자>_*_TEST_PLAN.md", "3.9.109"),
            "deploy_checklist": ("v3.9.1.9 Web UI PAPER Validation & Grounded Assistant Patch", "V3919_PAPER_VALIDATION_GROUNDED_ASSISTANT_TEST_PLAN.md"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors

    if RELEASE_VERSION == "3.9.1.8":
        required = {
            "manual_widget": ("v3.9.1.8 최신 업데이트", "[v3.9.1.8 Web UI]", "거래소 확인 체결"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.1.8**", "3.9.108", "KRW와 USDT"),
            "release_notes": ("v3.9.1.8 Web UI Execution Reconciliation & Broker Reliability Patch", "3.9.108", "Bithumb"),
            "deploy_release_notes": ("NoahAI v3.9.1.8 Web UI Execution Reconciliation & Broker Reliability Patch", "3.9.108", "V3918_EXECUTION_RECONCILIATION_PATCH_TEST_PLAN.md"),
            "changelog": ("v3.9.1.8 체결 원장 정합", "3.9.108"),
            "readme": ("v3.9.1.8 Web UI Execution Reconciliation & Broker Reliability Patch · Windows 재빌드 전",),
            "build_guide": ("v3.9.1.8 Web UI Execution Reconciliation & Broker Reliability Patch", "V<버전숫자>_*_TEST_PLAN.md", "3.9.108"),
            "deploy_checklist": ("v3.9.1.8 Web UI Execution Reconciliation & Broker Reliability Patch", "V3918_EXECUTION_RECONCILIATION_PATCH_TEST_PLAN.md"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors

    if RELEASE_VERSION == "3.9.1.7":
        required = {
            "manual_widget": ("v3.9.1.7 최신 업데이트", "[v3.9.1.7 Web UI]", "single-flight"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.1.7**", "6개 거래소 장시간", "3.9.107"),
            "release_notes": ("v3.9.1.7 Web UI Long-Run Performance & Request Isolation Patch", "3.9.107", "single-flight"),
            "deploy_release_notes": ("NoahAI v3.9.1.7 Web UI Long-Run Performance & Request Isolation Patch", "3.9.107", "V3917_LONG_RUN_PERFORMANCE_PATCH_TEST_PLAN.md"),
            "changelog": ("v3.9.1.7 장시간 성능·요청 격리 패치", "3.9.107"),
            "readme": ("v3.9.1.7 Web UI Long-Run Performance & Request Isolation Patch · Windows 재빌드 전",),
            "build_guide": ("v3.9.1.7 Web UI Long-Run Performance & Request Isolation Patch", "V<버전숫자>_*_TEST_PLAN.md", "3.9.107"),
            "deploy_checklist": ("v3.9.1.7 Web UI Long-Run Performance & Request Isolation Patch", "V3917_LONG_RUN_PERFORMANCE_PATCH_TEST_PLAN.md"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors

    if RELEASE_VERSION == "3.9.1.6":
        plan_marker = "V<버전숫자>_*_TEST_PLAN.md"
        required = {
            "manual_widget": ("v3.9.1.6 최신 업데이트", "[v3.9.1.6 Web UI]", "최근 50개"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.1.6**", "Learning Data, Exchange Logs & Runtime Reliability Patch", "3.9.106"),
            "release_notes": ("v3.9.1.6 Web UI Learning Data, Exchange Logs & Runtime Reliability Patch", "3.9.106", "최근 50개"),
            "deploy_release_notes": ("NoahAI v3.9.1.6 Web UI Learning Data, Exchange Logs & Runtime Reliability Patch", "3.9.106", "V3916_LEARNING_LOG_RUNTIME_PATCH_TEST_PLAN.md"),
            "changelog": ("v3.9.1.6 학습 데이터·거래소 로그·런타임 안정화 패치", "3.9.106"),
            "readme": ("v3.9.1.6 Web UI Learning Data, Exchange Logs & Runtime Reliability Patch · Windows 재빌드 전",),
            "build_guide": ("v3.9.1.6 Web UI Learning Data, Exchange Logs & Runtime Reliability Patch", plan_marker, "3.9.106"),
            "deploy_checklist": ("v3.9.1.6 Web UI Learning Data, Exchange Logs & Runtime Reliability Patch", "V3916_LEARNING_LOG_RUNTIME_PATCH_TEST_PLAN.md"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors

    if RELEASE_VERSION == "3.9.1.5":
        required = {
            "manual_widget": ("v3.9.1.5 최신 업데이트", "[v3.9.1.5 Web UI]", "settings.write_failed"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.1.5**", "Windows Exchange API Encoding & Credential Verification Patch", "3.9.105"),
            "release_notes": ("v3.9.1.5 Windows Exchange API Encoding & Credential Verification Patch", "3.9.105", "settings.write_failed"),
            "deploy_release_notes": ("NoahAI v3.9.1.5 Windows Exchange API Encoding & Credential Verification Patch", "3.9.105", "V3915_EXCHANGE_API_ENCODING_PATCH_TEST_PLAN.md"),
            "changelog": ("v3.9.1.5 Windows 거래소 API 인코딩", "3.9.105"),
            "readme": ("v3.9.1.5 Windows Exchange API Encoding & Credential Verification Patch · Windows 재빌드 전",),
            "build_guide": ("v3.9.1.5 Windows Exchange API Encoding & Credential Verification Patch", "V3915_EXCHANGE_API_ENCODING_PATCH_TEST_PLAN.md", "3.9.105"),
            "deploy_checklist": ("v3.9.1.5 Windows Exchange API Encoding & Credential Verification Patch", "V3915_EXCHANGE_API_ENCODING_PATCH_TEST_PLAN.md"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors

    if RELEASE_VERSION == "3.9.1.3":
        required = {
            "manual_widget": ("v3.9.1.3 최신 업데이트", "[v3.9.1.3 Web UI]", "설정 저장 후 재검증"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.1.3**", "Settings Persistence Verification Patch", "검증 영수증"),
            "release_notes": ("v3.9.1.3 Settings Persistence Verification Patch", "3.9.103", "NoahAIEngine.exe"),
            "deploy_release_notes": ("NoahAI v3.9.1.3 Settings Persistence Verification Patch", "3.9.103", "pending_windows_rebuild"),
            "changelog": ("v3.9.1.3 설정 저장", "3.9.103"),
            "readme": ("v3.9.1.3 Settings Persistence Verification Patch · Windows 재빌드 전",),
            "build_guide": ("v3.9.1.3 Settings Persistence Verification Patch", "V3913_SETTINGS_VERIFICATION_PATCH_TEST_PLAN.md", "3.9.103"),
            "deploy_checklist": ("v3.9.1.3 Settings Persistence Verification Patch", "V3913_SETTINGS_VERIFICATION_PATCH_TEST_PLAN.md"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors

    if RELEASE_VERSION == "3.9.1.1":
        required = {
            "manual_widget": ("v3.9.1.1 최신 업데이트", "[v3.9.1.1 Web UI]"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.1.1**",),
            "release_notes": ("v3.9.1.1 Settings Persistence Patch", "3.9.101", "v3.9.1.0→v3.9.1.1"),
            "deploy_release_notes": ("NoahAI v3.9.1.1 Settings Persistence Patch", "3.9.101", "Documents/NoahAI"),
            "changelog": ("v3.9.1.1 설정 저장 패치", "3.9.101"),
            "readme": ("v3.9.1.1 Settings Persistence Patch · Windows 검증 전",),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors

    if RELEASE_VERSION == "3.9.1.0":
        required = {
            # 내부 후보 식별자는 manifest/배포 문서에만 유지한다. 최종 사용자용
            # 인앱 매뉴얼에는 제품 버전과 사용자 영향만 표시한다.
            "manual_widget": ("v3.9.1.0 최신 업데이트", "[v3.9.1.0 Web UI]", "Windows bundle"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.1.0**", "Web UI Internal Integration Candidate", "pending_windows_rebuild"),
            "release_notes": ("v3.9.1.0 Web UI Internal Integration Candidate", "실패 폐쇄", "pending_windows_rebuild"),
            "deploy_release_notes": ("v3.9.1.0 Web UI Internal Integration Candidate", "read_first", "pending_windows_rebuild"),
            "architecture": ("현재 소스 v3.9.1.0", "web_platform/gateway.py", "Application Services"),
            "update_plan": ("v3.9.1.0 Web UI Major Transition", "PENDING", "pending_windows_rebuild"),
            "test_status": ("v3.9.1.0 Web UI 1:1 전환 현재 검증", "전체 Python 회귀", "전체 1:1 완료 및 배포 가능 판정은 아니다"),
            "readme": ("v3.9.1.0 Web UI 1:1 전환 진행 중 · 배포 불가", "모든 필수 행이 `[x] VERIFIED`", "pending_windows_rebuild"),
            "docs_readme": ("v3.9.1.0 Web UI 1:1 전환 진행 중 · 배포 불가", "35개", "pending_windows_rebuild"),
            "deploy_checklist": ("v3.9.1.0 Web UI Internal Integration Candidate", "Gateway", "build_web_ui_windows.ps1", "publish_ready=false", "pending_windows_rebuild"),
            "master_documentation": ("v3.9.1.0 Web UI 1:1 전환 진행 중", "WEB_UI_1_TO_1_PARITY_EXECUTION_PLAN", "배포 불가"),
            "build_guide": ("v3.9.1.0 Web UI Internal Integration Candidate", "Node `>=22.12.0`", "publish_web_ui_windows_release.ps1", "built_windows_unverified", "publish_ready=false"),
            "ai_custom_architecture": ("v3.9.1.0 Web UI Internal Integration Candidate", "버전 diff/rollback", "pending_windows_rebuild"),
            "assistant_guide": ("v3.9.1.0 Web UI Internal Integration Candidate", "백테스트/PAPER", ".noahstrategy"),
            "trading_flow": ("v3.9.1.0 Web UI Internal Integration Candidate", "실패 폐쇄", "PAPER/Windows E2E"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors

    if RELEASE_VERSION == "3.9.0.10":
        required = {
            "manual_widget": ("v3.9.0.10 최신 업데이트", "수정본 만들기", "전략 삭제", "PAPER"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.0.10**", "Runtime Integrity Update", "pending_windows_rebuild"),
            "release_notes": ("v3.9.0.10 AI Custom Management & Runtime Integrity Update", "수정본", "pending_windows_rebuild"),
            "deploy_release_notes": ("v3.9.0.10 AI Custom Management & Runtime Integrity Update", "최신 요청 하나", "pending_windows_rebuild"),
            "update_plan": ("v3.9.0.10 AI Custom Management & Runtime Integrity Update", "AI 어시스턴트", "pending_windows_rebuild"),
            "test_status": ("v3.9.0.10 AI Custom Management & Runtime Integrity Update", "Windows", "프라이빗 전략 관리"),
            "readme": ("v3.9.0.10 AI Custom Management & Runtime Integrity Update", "수정본", "pending_windows_rebuild"),
            "docs_readme": ("v3.9.0.10 AI 커스텀 관리", "위젯 소유권", "pending_windows_rebuild"),
            "deploy_checklist": ("v3.9.0.10 AI Custom Management & Runtime Integrity Update", "급속 전환 200회", "pending_windows_rebuild"),
            "master_documentation": ("v3.9.0.10 AI Custom Management & Runtime Integrity Update", "어시스턴트 지식", "Windows 재빌드 전"),
            "build_guide": ("v3.9.0.10 AI Custom Management & Runtime Integrity Update", "v3.9.0.9", "pending_windows_rebuild"),
            "ai_custom_architecture": ("v3.9.0.10 AI Custom Management & Runtime Integrity Update", "승인본", "pending_windows_rebuild"),
            "assistant_guide": ("v3.9.0.10 AI Custom Management & Runtime Integrity Update", "백테스트/PAPER", ".noahstrategy"),
        }
        errors: List[str] = []
        for surface, markers in required.items():
            text = text_map.get(surface, "")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[RELEASE_SURFACE] {surface}: '{marker}' 누락")
        return errors

    if RELEASE_VERSION == "3.9.0.9":
        required = {
            "manual_widget": ("v3.9.0.9 최신 업데이트", "Noah Strategy IR", "초보자·일반·고급·실험실", "PAPER"),
            "user_guide": ("현재 설치 기준 버전: **v3.9.0.9**", "AI Custom Stability Update", "pending_windows_rebuild"),
            "release_notes": ("v3.9.0.9 AI Custom Stability Update", "Noah Strategy IR", ".noahstrategy", "pending_windows_rebuild"),
            "deploy_release_notes": ("v3.9.0.9 AI Custom Stability Update", "단일 프로세스", "pending_windows_rebuild"),
            "update_plan": ("v3.9.0.9 AI Custom Stability Update", "AI 어시스턴트", "pending_windows_rebuild"),
            "test_status": ("v3.9.0.9 AI Custom Stability Update", "Windows", "PAPER"),
            "readme": ("v3.9.0.9 AI Custom Stability Update", "Noah Strategy IR", "pending_windows_rebuild"),
            "docs_readme": ("v3.9.0.9 AI Custom Stability Update", "Expression Graph", "pending_windows_rebuild"),
            "deploy_checklist": ("v3.9.0.9 AI Custom Stability Update", "pending_windows_rebuild"),
            "master_documentation": ("v3.9.0.9 AI Custom Stability Update", "어시스턴트 지식", "Windows 재빌드 전"),
            "build_guide": ("v3.9.0.9 AI Custom Stability Update", "v3.9.0.8 Fix 4", "pending_windows_rebuild"),
            "ai_custom_architecture": ("v3.9.0.9 AI Custom Stability Update", "Noah Strategy IR", "pending_windows_rebuild"),
            "assistant_guide": ("v3.9.0.9 AI Custom Stability Update", "백테스트/PAPER", ".noahstrategy"),
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
    errors.extend(check_current_release_and_marketplace(text_map))

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
