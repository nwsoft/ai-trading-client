# UI 고정 스킨 전환 Todo

작성: 2025-10-29  
최종 업데이트: 2025-10-30

## ✅ 완료된 작업

### 대시보드 (2025-10-29 완료)
- [x] ui/dashboard_modern.py 에서 ThemeManager, Theme 관련 헬퍼 호출 제거
- [x] 버튼/탭/퀵액션 색상 경로를 고정 상수로 강제 (_color가 FIXED_COLORS만 반환)
- [x] apply_theme / _apply_theme_palette / 다중 스타일 재적용 경로 제거 또는 no-op 처리
- [x] ThemedButton → CTkButton 래퍼(고정 스킨)로 대체
- [x] ThemeManager 인스턴스 제거 및 self.colors/self.fonts 직접 참조 제거
- [x] create_themed_button import 제거
- [x] ChartScreenshotWidget, UserManualWidget 호출 시 colors 파라미터 제거

### 로그인 모달 (2025-10-30 완료)
- [x] ui/login_modern.py - ThemeManager 제거
- [x] FIXED_COLORS import 추가
- [x] _color() 헬퍼 메서드 추가
- [x] 50+ 색상 참조 변환 (self.colors[] → self._color())
- [x] 테마 설정 섹션 비활성화
- [x] apply_theme 메서드 비활성화
- [x] 컴파일 에러 0개 달성

### 위젯
- [x] realtime_log_widget.py: DEFAULT_COLORS 제거 → FIXED_COLORS 직접 참조로 전환

---

## 🔄 진행 중인 작업

### 설정 다이얼로그 (진행률: 10%)
- [x] ui/settings_modern.py - ThemeManager import 제거
- [x] FIXED_COLORS import 추가
- [x] _color() 헬퍼 메서드 추가
- [x] create_themed_tabview → ctk.CTkTabview 변환
- [x] 테마 선택 섹션 비활성화 시작
- [ ] **154+ 색상 참조 변환** (주요 작업)
- [ ] 테마 미리보기 섹션 완전 제거
- [ ] _on_theme_segment_change 비활성화
- [ ] update_current_window_colors 비활성화
- [ ] 전체 컴파일 에러 해결

**참고**: 설정 파일은 2380 lines로 매우 크며, 자동화 스크립트 또는 분할 작업 필요

---

## ⏸️ 대기 중인 작업

### 위젯 추가 전환
- [ ] chart_screenshot_widget.py: 내부 colors 파라미터 처리 로직 제거
- [ ] user_manual_widget.py: 내부 구현 확인 및 정리
- [ ] market_trend_widget.py: 색상 키를 고정 상수로 매핑 (사용 중이면 작업)
- [ ] ai_report_widget*.py: 색상 접근 치환 (사용 중이면 작업)
- [ ] ai_learning_widget*.py: 색상 접근 치환 (사용 중이면 작업)

### 최종 정리
- [ ] ui/ 전체 디렉토리에서 ThemeManager/create_themed_* 잔존 참조 최종 확인
- [ ] 전체 파일 컴파일 에러 확인
- [ ] 검증 체크리스트 실행

---

## 검증 체크리스트
- [ ] 로그인 모달 실행 테스트
- [ ] 대시보드 실행 테스트
- [ ] 스크린샷 기준 버튼 톤/모서리/배치 일치
- [ ] 서비스 탭 active/inactive 대비 충분
- [ ] 텍스트 대비(AA 기준) 최소 확보
- [ ] hover 상태 동작 일관
- [ ] 설정 창 기본 기능 작동 확인

---

## 작업 현황 요약

| 파일 | 상태 | 컴파일 에러 | 비고 |
|------|------|------------|------|
| dashboard_modern.py | ✅ 완료 | 0 | 대시보드 완전 변환 |
| login_modern.py | ✅ 완료 | 0 | 50+ 색상 참조 변환 |
| realtime_log_widget.py | ✅ 완료 | 0 | FIXED_COLORS 직접 사용 |
| settings_modern.py | 🔄 진행 중 (10%) | 154+ | **대규모 작업 필요** |
| chart_screenshot_widget.py | ⏸️ 대기 | ? | 내부 구현 확인 필요 |
| user_manual_widget.py | ⏸️ 대기 | ? | 내부 구현 확인 필요 |
| 기타 위젯들 | ⏸️ 대기 | ? | 조사 필요 |

---

## 참고 문서
- `utils/fixed_colors.py` - 고정 색상 정의
- `docs/UI_FIXED_SKIN_WORK_SUMMARY_20251029.md` - 대시보드 작업 요약
- `docs/UI_FIXED_SKIN_WORK_SUMMARY_20251030.md` - 로그인 작업 요약 (NEW)
- `ui/dashboard_modern.py` - 완성된 참조 구현
- `ui/login_modern.py` - 완성된 참조 구현

---

## 다음 우선순위

1. **HIGH**: settings_modern.py 색상 참조 대량 변환 (154+ 개)
2. **MEDIUM**: 위젯 파일들 내부 구현 확인 및 정리
3. **LOW**: 최종 검증 및 테스트

진행 중 변경/결정 사항은 본 문서를 계속 업데이트합니다.

