#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""앱 배포 버전 단일 소스.

주의:
- 배포 승인 없이 값을 올리지 않는다.
- 문서 동기화만으로는 RELEASE_VERSION을 변경하지 않는다.
"""

RELEASE_VERSION = "3.9.1.43"
PUBLIC_RELEASE_VERSION = "3.9.1.42"
RELEASE_DATE = "2026-09-20"
RELEASE_HIGHLIGHT = "거래 기록 점검·복구 유지관리 및 전략 스튜디오 난이도 동선 개선"
RELEASE_PATCH = "Record Recovery Maintenance and Strategy UX Patch"
RELEASE_BUILD_LABEL = f"v{RELEASE_VERSION} {RELEASE_PATCH}"
# 릴리스 자산·manifest에는 위 내부 식별자를 유지하되 일반 사용자가 보는
# 창 제목과 인앱 메뉴얼에는 렌더러 구현명(Web UI)을 노출하지 않는다.
RELEASE_DISPLAY_LABEL = f"v{RELEASE_VERSION}"
# 기존 매뉴얼 추출기와 롤백 도구가 가져오는 호환 이름이다. 더 이상 UI
# 구현명을 뜻하지 않으며 사용자에게 보여 줄 제품 버전만 제공한다.
RELEASE_DISPLAY_PATCH = RELEASE_DISPLAY_LABEL
RELEASE_NOTICE_ID = "v3.9.1.43-record-recovery-maintenance-patch"

DASHBOARD_TITLE = f"Noah AI Client - 대시보드 Beta {RELEASE_DISPLAY_LABEL}"
USER_MANUAL_TITLE = f"NoahAI 사용메뉴얼 {RELEASE_DISPLAY_LABEL}"
