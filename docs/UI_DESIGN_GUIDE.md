# UI 디자인 가이드 (고정 스킨, 둥근 UI 베이스라인)

최종 목표: 로그인 모달과 동일한 둥근 스타일을 대시보드 전역으로 통일하고, 재발 방지를 위한 규칙과 체크리스트를 제공한다.

## 2026-08-13 플랫폼 전환 적용 범위

- 이 문서의 기존 CustomTkinter 규칙은 레거시 UI가 운영되는 동안의 안정화 기준이다. 새 Web UI의 내부 구현 규칙으로 복사하지 않는다.
- 목표 UI는 브라우저와 데스크톱 셸이 같은 컴포넌트·디자인 토큰·정보구조를 사용한다. daltrading SaaS와 NoahAI Client가 브랜드는 같되 실행 권한은 서로 다른 제품 경계를 유지한다.
- 모든 화면은 `loading / ready / empty / stale / partial / error / permission-denied` 상태를 명시하고, 빈 화면이나 회색 native 창으로 실패를 숨기지 않는다.
- 탭은 위젯 파괴/재생성의 신호가 아니라 route 전환이다. 화면 로컬 상태와 서버/엔진 원본 상태를 구분하고, route 이동이 매매 worker·WebSocket·broker 연결을 재시작하지 않아야 한다.
- 상단의 기준 거래소, 활성 범위, 자동매매 실행 수, PAPER/LIVE 상태를 별도 필드로 표시한다. 한 문자열에 설정과 실제 실행 상태를 혼합하지 않는다.
- 초보자/일반/고급/실험실 프로필은 기능을 숨기는 장식이 아니라 정보 밀도·용어·위험 확인·편집 권한을 단계적으로 여는 제품 계약이다.
- 설정 저장은 즉시 UI 응답→변경 diff 확인→백그라운드 적용 결과의 순서로 표현한다. 관련 없는 증권/거래소 연결 점검을 자동 실행하지 않는다.
- 위험 명령은 대상·계정·거래소·모드·금액/수량·전략 버전·예상 영향과 차단 사유를 확인할 수 있어야 한다.

### 공통 Web UI 디자인 토큰 후보

| 영역 | 기준 |
|---|---|
| spacing | 4px 기반, 카드 내부 16~24px, 화면 gutter 24~32px |
| type | 본문 14~16px, 보조 12~14px, 수치 tabular-nums, 한국어 줄높이 1.45 이상 |
| state color | 정보/성공/주의/위험을 색상+아이콘+텍스트로 함께 전달 |
| focus | 모든 클릭 대상에 키보드 focus-visible, 44px 권장 hit target |
| table/chart | 통화·timezone·데이터 시각·표본 수·PAPER/LIVE 배지를 항상 함께 표시 |
| responsive | 1280px 기준 데스크톱, 작은 창에서는 우측 패널을 drawer로 전환하고 정보 삭제 금지 |

새 디자인 시스템의 시각 승인만으로 기능 parity를 판단하지 않는다. 동일 snapshot과 command 결과를 기존 UI와 비교하는 자동 계약 검증이 필수다.

### 금융 차트 UX 기준

- 차트에는 거래소/증권사, 심볼, 현물/선물/주식, 시간봉, timezone, 데이터 마지막 시각, stale/reconnect 상태를 함께 표시한다.
- 캔들·거래량·지표·전략 마커·포지션·주문을 겹쳐도 범례에서 계층별 ON/OFF가 가능해야 한다.
- LONG/SHORT 색상만으로 의미를 전달하지 않고 방향 텍스트·아이콘·주문 상태를 함께 사용한다.
- 진입/청산 마커 선택 시 전략 버전, XAI 근거, 주문/체결 ID, 가격·수량·수수료, PAPER/LIVE를 표시한다.
- 백테스트와 PAPER/LIVE 결과는 같은 차트 안에서도 배지·배경·기간 경계로 명확히 구분한다.
- 수익률 차트에는 MDD·표본 수·비용 포함 여부·기간을 함께 표시하고 미래 성과 기대 문구로 변환하지 않는다.
- 작은 창에서는 지표 pane을 접을 수 있지만 주문 위험·PAPER/LIVE·데이터 stale 상태는 숨기지 않는다.

## 1) 무엇이 문제였나 (Root Cause)
- 증상: 대시보드에서만 corner_radius가 무시되어 버튼/패널이 각지게 렌더링되고, 텍스트 안티앨리어싱도 거칠게 보임.
- 원인: 대시보드 및 일부 위젯에서 CustomTkinter 내부 draw 경로를 monkey patch(CTkLabel._draw, DrawEngine.draw_rounded_rect_with_border)하여 렌더 파이프라인이 깨짐.
- 검증: 최소 예제(독립 CTkButton)에서는 정상적으로 둥글게 표시 → 라이브러리 문제 아님. 패치 비활성화 후 즉시 둥근 렌더링 복구.
- 결론: CustomTkinter 내부 메서드 패치는 전면 금지. 모두 제거함.

## 2) 새로운 베이스라인
- 라이브러리: 레거시 UI 요구사항 `customtkinter>=5.2.0`. 실제 배포 버전과 Windows native menu 동작은 빌드 manifest에서 별도 확인한다.
- 스킨 전략: 고정 스킨(Fixed Skin)
  - 투명색("transparent") 미사용
  - 런타임 테마 전환 없음 (ThemeManager 사용 안 함)
- 전역 디자인 토큰(권장): FIXED_COLORS 사용
  - 배경, 버튼, 포커스, 경계선 색상은 코드 상수로 관리
- 코너 라디우스: 기본 10 (패널/버튼/입력 공통)
- 경계선: 기본 0. 필요한 경우 카드형 컨테이너에만 1~2 적용
- 폰트: Segoe UI, 11~14pt, 굵기는 CTA/제목 위주로 bold

## 3) 컴포넌트 스펙
- 버튼(CTkButton)
  - corner_radius=10, width=120~140, height=36~40
  - fg_color: 메인 액션(파란색 계열), hover_color: 약간 어둡게
  - border_width=0, text_color="#ffffff"
- 패널(CTkFrame/CTkScrollableFrame)
  - corner_radius=10~12, fg_color: 짙은 바탕, border_color: 중간 톤, border_width=0~2
  - 내부 패딩: padx=10~12, pady=8~10
- 입력(CTkEntry)
  - corner_radius=10, border_width=0~1, focus 시 살짝 강조
- 칩/태그(간단 버튼 또는 Frame)
  - 작은 높이(28~32), corner_radius=10, 여백을 충분히 두어 시각적 뭉침 방지

- 탭 바(CTkTabview)
  - segmented_button_corner_radius=12
  - 탭 바 배경과 비선택 탭 버튼 배경을 동일 톤으로 맞춰 일체감 유지
  - 선택 탭은 주색(#2563eb), 텍스트는 #ffffff, 비선택 텍스트는 밝은 회색 계열
  - Hover 시 약 +6~10% 밝기 상승으로 상호작용 피드백 제공(로그인 모달 버튼과 톤 일치)

## 4) 구현 체크리스트
- [ ] CustomTkinter 내부 메서드 패치 코드 전면 제거(완료)
- [ ] 위젯 생성 이후 스타일을 덮어쓰는 late configure 호출 점검
  - corner_radius, border_width, fg_color를 나중에 바꾸는 함수가 있는지 확인
  - 있다면 동일 규칙 유지: corner_radius 10 유지, border_width 기본 0, 투명색 금지
- [ ] 상단 바/서비스 탭/설정 버튼이 로그인 모달과 동일한 버튼 스펙인지 확인
- [ ] CTkScrollableFrame 등 컨테이너의 모서리/여백/색상을 카드형 규칙으로 통일

## 5) Do / Don’t
- Do
  - 최소 예제로 렌더링 이상 여부를 먼저 확인한다
  - 스타일 상수(FIXED_COLORS)와 공통 corner_radius를 일관되게 사용한다
  - configure로 덮어쓰는 경우도 최종 값이 규칙을 유지하는지 체크한다
- Don’t
  - CustomTkinter 내부 함수(특히 draw 경로)를 monkey patch 하지 않는다
  - "transparent" 색상을 사용하지 않는다
  - 위젯별 임의 corner_radius를 섞어 쓰지 않는다(일관성 붕괴)

## 6) 회귀 방지(Regression) 테스트
- 최소 버튼 예제 실행: `test_button_minimal.py` (둥근 버튼 2개가 선명히 보여야 함)
- 대시보드 실행 후 스크린샷 확인 포인트
  - 상단 주요 버튼(모두 시작/설정) 둥근 모서리 유지
  - 서비스 탭(거래소/카테고리) 버튼 둥근 모서리 유지
  - 카드형 패널(스크롤 프레임) 가장자리 라운드 유지 및 텍스트 가독성 양호

## 7) 마이그레이션 노트
- 제거됨
  - ui/dashboard_modern.py: `_patch_customtkinter_methods` 함수와 호출부
  - ui/widgets/market_trend_widget.py: `_patch_customtkinter_methods` 함수와 호출부
- 유지/정비
  - `safe_after`, `thread_safe_after` 등 UI 수명 주기 안전장치 함수는 유지
  - 스타일 상수(FIXED_COLORS) 참조 경로와 사용처는 그대로 유지

## 8) FAQ
- Q: 왜 로그인 모달은 둥글고 대시보드만 각졌나요?
  - A: 대시보드 경로에서만 CustomTkinter 내부 draw를 patch하여 라이브러리의 둥근/AA 렌더링이 깨졌기 때문입니다.
- Q: 투명색을 쓰면 안 되나요?
  - A: Tk/CTk에서 투명 처리의 부작용이 많아 고정 스킨 전략에서는 금지합니다. 색상 상수를 사용하세요.
- Q: corner_radius는 어디서 바꾸나요?
  - A: 기본값은 컴포넌트 생성 시 바로 지정합니다. 이후 configure로 덮어써야 한다면 규칙(10)을 유지하세요.

---
본 문서는 과거 테마/레이아웃 문서를 대체합니다. 새로운 변경이 필요할 경우 이 가이드를 단일 출처(Single Source of Truth)로 업데이트하세요.

## 9) 폴리싱 체크리스트 (진행형)
- [ ] market_trend_widget: 잔여 transparent 제거 여부 재검증 (컨테이너 배경색 적용 완료)
- [ ] settings_modern: 상위 컨테이너 transparent → 고정 배경색으로 점진 교체 계획 수립
- [ ] 대시보드 카드들의 corner_radius 값 범위(10~16) 최종 합의 및 통일 표기
- [ ] CTkLabel 배지 모서리 값(6) 유지/조정 검토 (일관성 관점)
- [ ] 서비스 탭 버튼 활성/비활성 색상 대비 확인 (명도 대비 4.5:1 이상 권장)

## 10) 작업 로그 (Audit Log)
- 2025-10-30: dashboard_modern.py, market_trend_widget.py의 CustomTkinter monkey patch 완전 제거
- 2025-10-30: docs/* 테마/레이아웃 관련 레거시 문서 일괄 삭제, UI_DESIGN_GUIDE.md 신설
- 2025-10-30: MarketTrendWidget 내부 transparent 사용 구간을 컨테이너 배경색(#0b1120)으로 치환
- 2025-10-30: Settings 창(main_frame, 하단 버튼 프레임)에서 transparent → #0b1120 1차 치환
- 2025-10-30: Settings 창 transparent 사용처 재검사 → 잔여 없음(현재 파일 기준)
- 2025-10-30: 전체 앱 실행 검증 완료 (python main.py → EXIT 0), 둥근 UI 및 텍스트 렌더링 정상 확인
 - 2025-10-30: 대시보드 상단 서비스 메뉴/액션 버튼 크기 통일 — service 버튼 높이 36, 폰트 13; '모두 시작/설정' 높이 36, 폰트 13으로 축소
 - 2025-10-30: 상단 타이틀("🚀 NoahAI-재테크 어시스턴트")을 하단 상태 줄 프리픽스로 이동 — 서비스 메뉴 공간 확보 및 "🤖 AI애널리스트" 가시성 개선
 - 2025-10-30: 상단 좌측 사용자 영역 좌측 오프셋 +5px 적용, Quick Actions 버튼군을 grid 배치로 변경해 좌우 대칭 정렬 확보
 - 2025-10-30: 메인 탭바(실시간 거래 로그~시장 트렌드) 대비 강화 — toolbar계열 배경(#111827), 비선택(#1f2937)/선택(#2563eb) 버튼, 텍스트 대비 상향
 - 2025-10-30: 탭바 스타일 재적용기 보강 및 Hover 밝기 효과 추가 — 비선택 배경=탭 바 배경으로 통일, 텍스트 명도 상향
 - 2025-10-30: 실시간 로그 레이아웃 최적화 — 헤더 라벨 제거로 가용 세로 공간 증가, 거래소/카테고리 콤보를 하단 "로그 레벨" 옆으로 이동
 - 2025-10-30: 로그인 모달 — 도움말 버튼을 "로그인 정보 저장" 체크박스 오른쪽으로 이동(푸터 단순화)

## 11) 어떻게 변경을 기록하나요? (Logging How-To)
- 모든 UI 관련 변경은 아래 두 곳에 기록합니다.
  1) 요약: `docs/CHANGELOG.md`의 해당 날짜 섹션에 한 줄 요약
  2) 상세: `docs/UI_DESIGN_CHANGELOG.md`에 코드/문서/영향/회귀/롤백까지 구체적으로 기록
- 새 변경을 추가할 때는 `UI_DESIGN_CHANGELOG.md`의 템플릿을 복사해 사용하세요.

## 12) 품질 게이트(빠른 확인)
- Build/Run: `python main.py` → PASS (2025-10-30 기준)
- Minimal UI test: `test_button_minimal.py` → PASS (CTkButton 라운드 정상)
- Lint/Type: 대시보드 일부 타입 경고(예: AILearningWidget.set_summary_callback) 잔존 — 기능 영향 없음, 후속 정리 항목으로 유지
