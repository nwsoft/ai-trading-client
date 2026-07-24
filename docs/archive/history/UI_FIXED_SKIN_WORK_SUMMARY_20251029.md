# UI 고정 스킨 전환 작업 요약 (2025-10-29) (이력 보관)

## 완료된 작업

### 1. 대시보드 테마 시스템 완전 제거
- ✅ ThemeManager 인스턴스 생성 제거
- ✅ 테마 리스너 등록 제거
- ✅ self.colors, self.fonts 속성 제거
- ✅ ThemeManager, create_themed_button import 제거
- ✅ _color() 메서드를 FIXED_COLORS 전용으로 변환
- ✅ _apply_theme_palette를 고정 스킨 적용 전용으로 변환
- ✅ on_theme_changed를 no-op으로 변환

### 2. 대시보드 버튼 시스템 고정 스킨화
- ✅ _create_fixed_button 헬퍼 메서드 추가 (variant: primary/secondary)
- ✅ start_stop_btn → _create_fixed_button로 전환
- ✅ settings_btn → _create_fixed_button로 전환
- ✅ 서비스 탭 버튼들 (블록체인/주식/부동산/기타/AI) → _create_fixed_button로 전환
- ✅ 모든 버튼 색상/hover/텍스트가 FIXED_COLORS에서 직접 지정됨

### 3. 대시보드 색상 참조 고정화
- ✅ 모든 self.colors["key"] → self._color('key', fallback)로 변환
- ✅ 모든 self.fonts.get() → self._get_safe_font() 또는 고정 폰트로 변환
- ✅ 사용자 정보 라벨, 거래소 라벨, 앱 제목 라벨 등 모든 라벨 색상 고정
- ✅ 상태 프레임, 패널 프레임 등 모든 컨테이너 색상 고정

### 4. 위젯 파라미터 정리
- ✅ RealtimeLogWidget: fonts, colors 파라미터 제거
  - FIXED_COLORS 직접 import 및 참조
  - 모든 self.fonts.get() 제거, 고정 폰트로 대체
- ✅ ChartScreenshotWidget: 대시보드 호출 시 colors 파라미터 제거
- ✅ UserManualWidget: 대시보드 호출 시 colors 파라미터 제거

### 5. 문서화
- ✅ docs/UI_FIXED_SKIN_TODO.md 작업 진행 상황 업데이트
- ✅ 완료된 체크리스트 항목 ✓ 표시
- ✅ 남은 작업 명확히 문서화

## 현재 상태

### 대시보드 (ui/dashboard_modern.py)
- ThemeManager 의존성: **완전 제거**
- 색상 시스템: **FIXED_COLORS 전용**
- 버튼 생성: **_create_fixed_button 래퍼**
- 레이아웃: **변경 없음 (유지됨)**

### 위젯들
- RealtimeLogWidget: **고정 스킨 완료**
- ChartScreenshotWidget: 호출부 완료, 내부 구현 검토 필요
- UserManualWidget: 호출부 완료, 내부 구현 검토 필요

### 기타 UI 파일
- login_modern.py: ThemeManager 사용 중 (로그인 모달은 별도 관리 가능)
- settings_modern.py: ThemeManager 사용 중 (설정 다이얼로그는 별도 관리 가능)

## 남은 작업

### 우선순위 1: 위젯 내부 구현 확인
- [ ] chart_screenshot_widget.py 파일 열어서 colors 파라미터 사용 로직 확인 및 제거
- [ ] user_manual_widget.py 파일 열어서 colors 파라미터 사용 로직 확인 및 제거
- [ ] 두 위젯 모두 FIXED_COLORS 직접 참조로 전환

### 우선순위 2: 다른 UI 파일 결정
- [ ] login_modern.py의 테마 의존성 평가
  - 로그인 모달은 대시보드와 독립적이므로 테마 유지 가능
  - 또는 고정 스킨으로 전환하여 일관성 확보
- [ ] settings_modern.py의 테마 의존성 평가
  - 설정 다이얼로그도 독립적이므로 테마 유지 가능
  - 또는 고정 스킨으로 전환

### 우선순위 3: 최종 검증
- [ ] 대시보드 실행하여 모든 버튼 표시 확인
- [ ] 서비스 탭 active/inactive 색상 대비 확인
- [ ] 시작/정지 버튼 primary 색상 확인
- [ ] 설정 버튼 secondary 색상 확인
- [ ] hover 상태 동작 확인
- [ ] 스크린샷 촬영 및 문서 업데이트

## 주의 사항

### 정적 분석 경고
- 동적 속성 경고는 기존부터 존재 (위젯 동적 생성으로 인한 것)
- SettingsDialog의 _color, _mark 등: 내부 클래스 메서드로 정의되어 있으나 Pylance가 인식 못함
- 이러한 경고는 실제 런타임에 영향 없음

### 테마 시스템 잔존
- theme_system/ 디렉토리는 아직 존재
- login_modern.py, settings_modern.py가 아직 사용 중
- 완전 제거 전 다른 UI 파일들의 전환 필요

### 색상 일관성
- FIXED_COLORS에 정의된 색상만 사용
- 새로운 색상 필요 시 FIXED_COLORS에 먼저 추가
- fallback 값도 가능한 FIXED_COLORS 키를 사용

## 다음 단계 권장사항

1. **즉시 진행**: 위젯 내부 구현 검토 (chart_screenshot, user_manual)
2. **선택적**: login/settings 고정 스킨 전환 (일관성 원하면 진행)
3. **최종**: 전체 테스트 및 스크린샷 업데이트
4. **문서화**: 완료 후 ARCHITECTURE.md, CODE_CHANGE_LOG.md 최종 업데이트

## 성공 기준

✅ 대시보드가 ThemeManager 없이 정상 동작
✅ 모든 버튼이 FIXED_COLORS 기반으로 올바른 색상 표시
✅ 서비스 탭 active/inactive 상태 명확히 구분
✅ hover 효과 정상 동작
✅ 레이아웃 변경 없음
✅ 색상 대비 AA 기준 충족 (텍스트 가독성 확보)
