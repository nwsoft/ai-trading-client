# UI 디자인 변경 기록 (Design Changelog)

이 문서는 UI/디자인 관련 변경 사항을 상세히 추적하기 위한 전용 변경 기록입니다. 코드/문서 추가·수정·삭제와 함께 변경 이유, 영향도, 회귀 체크, 롤백 가이드를 함께 남깁니다.

## 2025-10-30 — UI 베이스라인 통합

- 변경 유형: Remove (삭제), Add (추가), Modify (수정)
- 배경/문제: 대시보드에서만 corner_radius가 각지게 보이고 텍스트 안티앨리어싱이 거칠게 보임
- 근본 원인: CustomTkinter 내부 draw 경로 monkey patch로 인해 CTk의 라운드/AA 렌더링 파이프라인이 훼손됨

### 코드 변경
- Remove: `ui/dashboard_modern.py` → `_patch_customtkinter_methods` 함수 및 호출부
- Remove: `ui/widgets/market_trend_widget.py` → `_patch_customtkinter_methods` 함수 및 호출부
- Modify: `ui/widgets/market_trend_widget.py` → 일부 `fg_color="transparent"`를 `#0b1120`로 치환(고정 스킨 정책)
- Modify: `ui/settings_modern.py` → 메인 컨테이너 및 하단 버튼 프레임의 `fg_color="transparent"`를 `#0b1120`로 치환(1차 안전 범위)

### 문서 변경
- Add: `docs/UI_DESIGN_GUIDE.md` (Root Cause/베이스라인/컴포넌트 스펙/Do&Don't/폴리싱 체크리스트/작업 로그)
- Remove: 레거시/중복 문서 일괄 삭제
  - archive/history/THEME_APPLICATION_COMPLETE.md, THEME_FILES_LOCATION.md, THEME_REMOVAL_DETAILED_CHANGELOG_20251030.md, THEME_SYSTEM.md, THEME_SYSTEM_GUIDE.md
  - archive/dashboard/DASHBOARD_BUTTONS_ANALYSIS.md, archive/dashboard/DASHBOARD_DESIGN_IMPROVEMENTS_20251030.md, archive/dashboard/DASHBOARD_DESIGN_MODIFICATION.md, DASHBOARD_POSITION_SYSTEM.md, archive/dashboard/DASHBOARD_REDESIGN_PLAN.md, archive/dashboard/DASHBOARD_RIGHT_PANEL_LOCATION.md
  - HISTORICAL_THEME_BASELINE.md, UI_FIXED_SKIN_PLAN.md, UI_FIXED_SKIN_TODO.md, archive/history/UI_FIXED_SKIN_WORK_SUMMARY_20251029.md, archive/history/UI_FIXED_SKIN_WORK_SUMMARY_20251030.md
  - archive/history/WIDGETS_HARDCODED_COLORS_ANALYSIS.md, WIDGET_COLORS_FIX_PLAN.md, archive/history/WIDGET_USAGE_ANALYSIS.md

### 영향도 / 리스크
- 라운드/텍스트 렌더링 품질 즉시 개선
- 투명색 제거로 일부 배경 톤 차이 가능(점진 치환)
- monkey patch 제거로 버전 호환성/유지보수 리스크 크게 감소

### 회귀 체크리스트
- 독립 예제 `test_button_minimal.py`의 둥근 버튼 확인
- 대시보드 상단 버튼/서비스 탭/카드형 패널 라운드와 텍스트 가독성 확인
- 남아있는 `transparent` 사용처 점검(설정 화면 등)
  - settings_modern: 상위/서브 프레임 추가 점검 및 점진 치환 예정

### 검증(Validation)
- App run: `python main.py` → PASS (Windows, 2025-10-30 기준)
- Minimal CTk test: `test_button_minimal.py` → PASS (둥근 버튼 정상 표시)
- Verification: `ui/settings_modern.py` 내 `fg_color="transparent"` 잔여 사용처 없음 (2025-10-30 검색 기준)
- Final check: 전체 앱 실행 후 대시보드/설정/위젯 모두 둥근 렌더링 및 텍스트 AA 정상 작동 확인

### 롤백 가이드
- monkey patch 복원은 비권장(문제 재발 위험 높음). 실험 필요 시 별도 브랜치로 제한하고 스크린샷 전후 비교 필수.

---

### 2025-10-30 — 서비스 메뉴/액션 버튼 크기 통일
- 변경 유형: Modify
- 배경/문제: 상단 서비스 메뉴(블록체인~AI애널리스트)와 우측 액션 버튼(모두 시작, 설정)의 높이/폰트가 좌측 개별 거래소 토글 버튼 대비 과도하게 커서 시각적 균형이 맞지 않음
- 목표: 좌측 '사용자 거래소' 토글(높이 36)을 기준으로 서비스 메뉴와 액션 버튼의 크기를 축소/통일

#### 코드 변경
- Modify: `ui/dashboard_modern.py`
  - `create_status_bar()` 내 우측 액션 버튼 크기 조정
    - `self.start_stop_btn`: `height=48 → 36`, `font size=15 → 13`
    - `self.settings_btn`: `height=48 → 36`, `font size=15 → 13`
  - `create_service_tabs()` 내 서비스 메뉴 버튼 크기 조정
    - 서비스 버튼 공통 `height=42 → 36`
    - 서비스 버튼 폰트 fallback `size=14 → 13`

#### 영향도 / 리스크
- 상단바 높이감이 줄어들어 정보 밀도가 개선되고 좌우 요소 간 균형이 향상
- 텍스트 크기 축소로 일부 사용자 환경에서 시인성이 약간 낮아질 수 있음(필요 시 14로 복귀 가능)

#### 회귀 체크리스트
- 앱 실행 후 상단 서비스 메뉴 라인이 좌측 거래소 토글과 높이가 일치하는지 확인(36px)
- '모두 시작' / '설정' 버튼의 시각적 높이와 폰트가 서비스 메뉴와 조화를 이루는지 확인
- 버튼 라운드 및 호버 컬러는 이전과 동일하게 유지되는지 확인

#### 롤백 가이드
- `ui/dashboard_modern.py`에서 해당 속성 값을 이전 값(높이 42/48, 폰트 14/15)으로 되돌리면 즉시 복구됨

### 2025-10-30 — 상단 타이틀을 하단 상태 줄로 이동, 서비스 메뉴 공간 확보
- 변경 유형: Modify
- 배경/문제: 상단바 좌측에 표시하던 앱 타이틀("🚀 NoahAI-재테크 어시스턴트")가 서비스 메뉴 버튼들과 수평 공간을 경쟁하여 마지막 항목(예: "🤖 AI애널리스트")이 가려지는 경우 발생
- 목표: 상단 서비스 메뉴에 충분한 수평 공간을 제공하여 모든 메뉴 버튼이 노출되도록 하고, 앱 타이틀은 하단 상태 줄 프리픽스로 일관되게 노출

#### 코드 변경
- Modify: `ui/dashboard_modern.py`
  - `create_status_bar()`에서 좌측 타이틀 프레임/라벨 블록 제거
  - `get_status_info()`에서 반환 문자열 앞에 타이틀 프리픽스 추가: `"🚀 NoahAI-재테크 어시스턴트 | ..."`

#### 영향도 / 리스크
- 상단바 수평 공간 증가로 서비스 메뉴 마지막 버튼(특히 "🤖 AI애널리스트") 가시성 향상
- 하단 상태 줄 텍스트가 길어짐. 매우 좁은 해상도에서 상태 줄 텍스트가 잘릴 수 있음(기능 영향 없음)

#### 회귀 체크리스트
- 앱 실행 후 상단 서비스 메뉴 전 항목 노출 여부 확인(창 폭 1280px 이상 기준)
- 하단 상태 줄에 다음 형식으로 노출되는지 확인: `🚀 NoahAI-재테크 어시스턴트 | MODE: ... | EXCHANGE: ... | HH:MM:SS`
- 버튼 라운드/호버/클릭 동작은 종전과 동일한지 확인

#### 롤백 가이드
- `ui/dashboard_modern.py`에서 `create_status_bar()`의 타이틀 라벨 블록을 복원하고, `get_status_info()`의 타이틀 프리픽스 추가를 제거하면 즉시 이전 레이아웃으로 복귀 가능

### 2025-10-30 — 좌측 사용자 영역 5px 오프셋 및 Quick Actions 좌우 대칭 정렬
- 변경 유형: Modify
- 배경/문제: 상단 바 좌측 가장자리에 붙어 보이는 사용자 영역을 살짝 띄워 미세 정렬을 개선하고, 우측 Quick Actions(차트 분석, 사용자 매뉴얼) 버튼들의 좌우 여백이 불균형해 보이는 문제
- 목표: 사용자 시선 정렬 개선과 우측 버튼군의 시각적 균형 확보

#### 코드 변경
- Modify: `ui/dashboard_modern.py`
  - `create_status_bar()` 내 `user_frame.pack(side="left", padx=(5, 8))`로 좌측 오프셋 +5px 적용
  - Quick Actions 섹션을 `pack` → `grid`로 전환하여 양쪽에 동일 가중치 스페이서 컬럼(0,3)을 두고 버튼을 1,2열에 배치하여 좌우 대칭 확보

#### 영향도 / 리스크
- 좌측 여백 증가로 전체 상단 바의 시선 정렬감 향상
- Quick Actions 버튼군이 창 폭 변화에도 균형을 유지

#### 회귀 체크리스트
- 창 폭 1280px 기준 좌측 사용자/거래소 영역이 가장자리에서 적절히 떨어져 보이는지 확인
- Quick Actions 두 버튼의 좌우 여백과 상자 내부 여백이 대칭인지 확인

#### 롤백 가이드
- `user_frame.pack`의 padx를 `(0, 8)`로 복원하고, Quick Actions 내부 버튼 배치를 `pack(side="left")`로 되돌리면 이전 레이아웃으로 복귀

### 2025-10-30 — 메인 탭바(실시간 거래 로그~시장 트렌드) 대비 강화
- 변경 유형: Modify
- 배경/문제: 탭 바 배경과 본문 배경의 톤이 유사해 탭 버튼이 레이아웃과 구분되지 않음
- 목표: 고정 스킨 팔레트 내에서 탭 바를 툴바 톤으로 설정하고, 선택/비선택 탭 버튼의 배경/텍스트 대비를 강화

#### 코드 변경
- Modify: `ui/dashboard_modern.py`
  - `create_main_content()` 내 CTkTabview 설정값 조정
    - `segmented_button_fg_color` → toolbar 계열(#111827)
    - `segmented_button_unselected_color` → 짙은 표면색(#1f2937)
    - `segmented_button_selected_color` → 주색(#2563eb), hover는 약간 어둡게
    - 텍스트: 비선택은 `text_secondary`(#cbd5e1), 선택은 `text_primary`(#ffffff)
    - `segmented_button_corner_radius=12`

#### 영향도 / 리스크
- 탭 버튼이 본문과 명확히 분리되어 인지성 향상
- 컬러 대비 증가로 저해상도/저명암비 디스플레이에서도 가독성 개선

#### 회귀 체크리스트
- 선택 탭은 파란 주색 배경/흰색 텍스트로 분명히 보이는지 확인
- 비선택 탭은 어두운 회색 배경/밝은 회색 텍스트로 차분하게 보이는지 확인
- 탭 바 전체 배경이 본문 카드와 구분되어 띠 형태로 보이는지 확인

#### 롤백 가이드
- 동일 위치의 CTkTabview 색상 설정을 이전 값으로 되돌리면 복구 가능

### 2025-10-30 — 탭바 스타일 재적용기 보강 + Hover 밝기 + 텍스트 명도 상향
- 변경 유형: Modify
- 목표: 사용자 환경에 따라 탭 색상이 적용되지 않는 문제를 방지하고 탭 상호작용성을 강화

#### 코드 변경
- Modify: `ui/dashboard_modern.py`
  - `_apply_tabview_style(tv)` 헬퍼 추가: Tabview 생성 직후·탭 추가 직후 2회 적용으로 재정의/순서 문제 방지
  - 팔레트 미세 조정: 비선택 버튼 배경 = 탭 바 배경(일체감), 선택 배경 = 주색(#2563eb), 텍스트 명도 소폭 상향
  - Hover 효과: 선택/비선택 각각 약 +6~10% 밝아지는 효과로 모달 버튼과 상호작용감 일치

#### 회귀 체크리스트
- 탭 생성/추가 순서가 달라도 스타일이 유지되는지 확인(앱 재시작/탭 동적 추가 시)
- 포인터 오버 시 비선택 탭이 살짝 밝아지고, 선택 탭은 과도하게 밝지 않은지 확인

#### 롤백 가이드
- `_apply_tabview_style` 호출 제거 및 색상 값 원복

### 2025-10-30 — 실시간 로그 영역 최적화: 헤더 제거 + 드롭다운 하단 이동
- 변경 유형: Modify
- 목표: 가용 세로 공간 극대화 및 필터의 논리적 그룹화(레벨/거래소/카테고리)

#### 코드 변경
- Modify: `ui/dashboard_modern.py`
  - "📡 실시간 거래 로그" 헤더 라벨 제거, 상단 패딩 축소로 가시 라인 수 증가
- Modify: `ui/widgets/realtime_log_widget.py`
  - 거래소/카테고리 콤보박스를 상단 필터 행에서 하단 제어 행(로그 레벨 옆)으로 이동
  - `log_level_combo` 폭 100→120으로 통일, 콤보 폭도 120으로 정렬
  - 스트림 모드에서만 콤보를 생성하고, None-가드로 안전 접근(정적 분석 경고 제거)

#### 회귀 체크리스트
- 상단 필터 행에는 체크박스만 남는지 확인
- 하단 제어 행에서 "로그 레벨 / 거래소 / 카테고리"가 가로로 정렬되고 동작하는지 확인

#### 롤백 가이드
- 위젯 생성 위치를 원래 상단 필터 행으로 되돌리면 즉시 복귀

### 2025-10-30 — 로그인 도움말 버튼 위치 변경
- 변경 유형: Modify
- 목표: 도움말 접근성은 유지하면서도 폼 내 컨텍스트와 가까이 배치

#### 코드 변경
- Modify: `ui/login_modern.py`
  - 도움말 버튼을 하단 푸터에서 "로그인 정보 저장" 체크박스 오른쪽으로 이동(가로 행 구성)
  - 푸터는 여백만 유지하도록 단순화

#### 회귀 체크리스트
- 체크박스 오른쪽에 "? 도움말" 버튼이 동일 행에 표시되는지 확인
- 버튼 크기/폰트가 로그인 모달 전체 톤과 조화로운지 확인

#### 롤백 가이드
- `create_footer_section()`에 기존 도움말 버튼 블록을 복원하고, 폼 행에서 제거

## 템플릿 (새 변경을 기록할 때 복사하여 사용)

```
### YYYY-MM-DD — 변경 요약 제목
- 변경 유형: Add | Modify | Remove
- 배경/문제: (한 줄 요약)
- 원인 또는 목표: (근본 원인/목표)

#### 코드 변경
- Add/Modify/Remove: <파일 경로> — (요약)

#### 문서 변경
- Add/Modify/Remove: <문서 경로> — (요약)

#### 영향도 / 리스크
- (장점/잠재 리스크)

#### 회귀 체크리스트
- (체크 항목 2~4개)

#### 롤백 가이드
- (가능한 경우만, 요약)
```
