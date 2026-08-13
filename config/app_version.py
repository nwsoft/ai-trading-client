#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""앱 배포 버전 단일 소스.

주의:
- 배포 승인 없이 값을 올리지 않는다.
- 문서 동기화만으로는 RELEASE_VERSION을 변경하지 않는다.
"""

RELEASE_VERSION = "3.9.0.10"
RELEASE_DATE = "2026-08-13"
RELEASE_HIGHLIGHT = "AI 커스텀 관리 · 설정 오류 차단 · 최신 탭 렌더·위젯 소유권 안정화"
RELEASE_PATCH = "AI Custom Management & Runtime Integrity Update"
RELEASE_BUILD_LABEL = f"v{RELEASE_VERSION} {RELEASE_PATCH}"
RELEASE_NOTICE_ID = "v3.9.0.10-ai-custom-management-settings-tab-runtime-integrity-source-candidate"

DASHBOARD_TITLE = f"Noah AI Client - 대시보드 Beta {RELEASE_VERSION} {RELEASE_PATCH}"
USER_MANUAL_TITLE = f"NoahAI 사용메뉴얼 {RELEASE_BUILD_LABEL}"
