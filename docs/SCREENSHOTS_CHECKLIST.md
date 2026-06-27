# 스크린샷 체크리스트 (v3.8.x)

본 문서는 사용자 문서/테스트 현황에 삽입될 스크린샷 항목과 파일명을 정의합니다. 캡처 후 `docs/images/`에 저장하고, 문서에서 상대 경로로 참조하세요.

## 필수 캡처 목록

1) ModernDashboard 메인(다크 테마)
   - 파일: `images/modern_dashboard_main_dark.png`
   - 포커스: 상단 CTkTabview, 기본 "📊 실시간 거래 로그" 탭 표시

2) 설정(일반) — classic_view ON
   - 파일: `images/settings_general_classic_view_on.png`
   - 포커스: 클래식 보기 토글 상태, 설명 툴팁 영역 포함

3) Classic View 시작 직후 — AI 학습/리포트 탭 자동 생성
   - 파일: `images/classic_view_ai_tabs_auto_created.png`
   - 포커스: "📚 AI 학습" 탭 선택 상태, "📊 AI 리포트" 탭 함께 보이기

4) 블록체인 서비스 — 거래소 필터/Trend Summary
   - 파일: `images/blockchain_exchange_filter_trend_summary.png`
   - 포커스: 거래소 필터(예: Binance/OKX/Bitget) UI, Trend Summary 카드/라벨

5) 멀티 거래소 활성 — 탭 라이프사이클
   - 파일: `images/multi_exchange_tabs_lifecycle.png`
   - 포커스: 활성 거래소만 탭 생성, 비활성 시 제거된 상태를 보여주는 화면

6) 커뮤니티 탭(플레이스홀더)
   - 파일: `images/community_tab_placeholder.png`
   - 포커스: QnA/Chat 섹션, "업데이트 준비중" 안내

7) AI 어시스턴트 빠른 이동(퀵 점프)
   - 파일: `images/ai_assistant_quick_jump.png`
   - 포커스: 설정 버튼/퀵 점프 UI, AI 학습/리포트로 이동 동작 힌트

8) macOS 앱 번들(배포 산출물) 아이콘/정보
   - 파일: `images/macos_app_bundle_overview.png`
   - 포커스: AITrading.app 정보 패널, 아이콘, codesign/notarize 완료 상태(가능 시)

## 선택 캡처
- 라이트 테마 변환 샷: `images/modern_dashboard_main_light.png`
- 페이퍼 모드 알림/표시 샷: `images/paper_mode_indicator.png`

## 문서 삽입 위치 가이드
- TEST_STATUS.md: 실행 PASS 결과 상단에 1), 3), 5) 삽입
- README.md: Quick Start 하단에 1), 2), 6) 삽입
- CHANGELOG.md: v3.8.2 항목에 2), 4) 썸네일 수준으로 링크
- EXCHANGE_SETUP.md: 멀티거래소 섹션에 4), 5) 삽입

캡처가 완료되면, 각 문서 해당 섹션에 다음 형식으로 추가하세요.

![ModernDashboard 메인](images/modern_dashboard_main_dark.png)

주의: 저장소 용량을 고려하여 PNG를 70~80% 품질로 최적화하고, 가로 폭 1200px 기준으로 리사이즈를 권장합니다.