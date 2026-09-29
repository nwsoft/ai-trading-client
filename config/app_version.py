#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""앱 배포 버전 단일 소스.

주의:
- 배포 승인 없이 값을 올리지 않는다.
- 문서 동기화만으로는 RELEASE_VERSION을 변경하지 않는다.
"""

RELEASE_VERSION = "3.9.1.49"
PUBLIC_RELEASE_VERSION = "3.9.1.48"
RELEASE_DATE = "2026-09-29"
RELEASE_HIGHLIGHT = "PAPER 평가 용량·완료 봉 지표·읽기 전용 운용 요약"
RELEASE_PATCH = "Strategy Capacity and Operations Evidence Patch"
RELEASE_BUILD_LABEL = f"v{RELEASE_VERSION} {RELEASE_PATCH}"
# 릴리스 자산·manifest에는 위 내부 식별자를 유지하되 일반 사용자가 보는
# 창 제목과 인앱 메뉴얼에는 렌더러 구현명(Web UI)을 노출하지 않는다.
RELEASE_DISPLAY_LABEL = f"v{RELEASE_VERSION}"
# 기존 매뉴얼 추출기와 롤백 도구가 가져오는 호환 이름이다. 더 이상 UI
# 구현명을 뜻하지 않으며 사용자에게 보여 줄 제품 버전만 제공한다.
RELEASE_DISPLAY_PATCH = RELEASE_DISPLAY_LABEL
RELEASE_NOTICE_ID = "v3.9.1.49-strategy-capacity-operations-evidence-patch"

DASHBOARD_TITLE = f"Noah AI Client - 대시보드 Beta {RELEASE_DISPLAY_LABEL}"
USER_MANUAL_TITLE = f"NoahAI 사용메뉴얼 {RELEASE_DISPLAY_LABEL}"
