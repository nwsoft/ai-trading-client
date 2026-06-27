# UI 고정 스킨(하드코딩) 전환 계획

본 계획은 테마/다크모드/팔레트 기반 시스템을 완전히 제거하고, 단일 디자인(고정 스킨)으로 일관되게 유지하기 위한 작업 가이드입니다.

작성일: 2025-10-29
우선순위: 대시보드 및 대시보드에서 호출하는 주요 위젯

## 목표
- 테마 의존성 제거: ThemeManager, palette, DEFAULT_COLORS 등 사용 금지
- 레이아웃 유지: 현재 UI/UX 배치, 탭 구조, 위젯 위치는 유지
- 시각 톤 재정의: 색상/버튼 형태/대비를 고정 값으로 통일
- 문서 일원화: 작업 진행과 결정 사항을 본 문서에만 업데이트

## 고정 색상 스펙(1차)
- background: #050a13
- surface: #1f2632
- panel: #252d38
- border: #374151
- text_primary: #f9fafb
- text_secondary: #9ca3af
- button_primary: #1f6feb
- button_primary_hover: #1a5fd1
- button_secondary: #3a5a7f
- button_secondary_hover: #4a6a8f
- success: #22c55e, danger: #ef4444, warning: #f59e0b, accent: #8b5cf6

버튼 스타일:
- corner_radius: 10~12(px) 고정
- 높이: 32~36(px), 텍스트 bold 12~13pt, 아이콘 좌측 배치
- service tab: active=button_primary, inactive=button_secondary

(필요 시 스크린샷 참고: Quick Actions/상단 버튼 파란색 톤 유지)

## 범위와 파일
1) 대시보드: ui/dashboard_modern.py
2) 핵심 위젯:
   - ui/widgets/realtime_log_widget.py
   - ui/widgets/market_trend_widget.py
   - ui/widgets/ai_report_widget*.py
   - ui/widgets/ai_learning_widget*.py
   - ui/widgets/chart_screenshot_widget.py

## 변경 원칙
- 색상 접근은 중앙 상수(FIXED_COLORS 또는 fixed_colors.py)만 사용
- 생성 직후/상태 변경 시 중복 스타일 재적용 금지 → 한 곳에서만 스타일 지정
- ThemedButton/ThemeManager 호출 제거 → CTkButton + 고정 스타일 래퍼 사용
- 폴백 HEX 남기지 않기: 모든 색은 고정 상수 참조

## 단계별 작업
1) 문서 정리
   - THEME_* 문서 삭제
   - 다른 문서의 테마 언급 제거 또는 폐기 안내
   - HISTORICAL_THEME_BASELINE.md에 과거 팔레트 보존
2) 고정 색상 소스 도입
   - utils/fixed_colors.py 생성(FIXED_COLORS dict)
   - ui 코드에서 이 모듈만 참조하도록 변경
3) 대시보드 전환
   - ThemeManager/색상 토큰/팔레트 참조 삭제
   - 버튼/탭/배경/텍스트 색을 FIXED_COLORS로 하드코딩
   - 다중 스타일 경로 정리(apply_theme 등 제거 또는 빈 구현)
4) 위젯 전환
   - 위젯들의 DEFAULT_COLORS 제거
   - 색상 접근을 FIXED_COLORS로 대체
5) 검증
   - 가독성/대비 체크(텍스트 대비, hover 효과)
   - 버튼/탭 활성/비활성 상태 시각 확인
6) 후속 정리
   - theme_system/ 디렉터리 제거(마이그레이션 완료 후)

## 작업 체크리스트
- [ ] THEME_* 문서 삭제 및 폐기 안내 반영
- [ ] fixed_colors.py 도입 및 참조 교체
- [ ] dashboard_modern.py 하드코딩 전환 완료
- [ ] 위젯 5종 하드코딩 전환 완료
- [ ] 최종 회귀 테스트 및 스냅샷 갱신

본 문서는 작업 진행 중 수시 업데이트합니다.
