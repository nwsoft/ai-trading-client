#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""앱 배포 버전 단일 소스.

주의:
- 배포 승인 없이 값을 올리지 않는다.
- 문서 동기화만으로는 RELEASE_VERSION을 변경하지 않는다.
"""

RELEASE_VERSION = "3.9.0.8"
RELEASE_DATE = "2026-08-11"
RELEASE_HIGHLIGHT = "AI 커스텀 P1~P3 · Windows UI 메뉴·AI 호출·주문 명령 안전화"
RELEASE_PATCH = "AI Custom Update Fix 4"
RELEASE_BUILD_LABEL = f"v{RELEASE_VERSION} {RELEASE_PATCH}"
RELEASE_NOTICE_ID = "v3.9.0.8-ai-custom-fix4-windows-menu-ai-budget-crypto-oms-source-candidate"

DASHBOARD_TITLE = f"Noah AI Client - 대시보드 Beta {RELEASE_VERSION} {RELEASE_PATCH}"
USER_MANUAL_TITLE = f"NoahAI 사용메뉴얼 {RELEASE_BUILD_LABEL}"
