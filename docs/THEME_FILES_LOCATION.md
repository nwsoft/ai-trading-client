> [폐기] 본 문서는 2025-10-29 기준으로 삭제되었습니다.

프로젝트는 테마 시스템을 더 이상 사용하지 않습니다. 단일 고정 스킨(하드코딩) 전환 계획은 `UI_FIXED_SKIN_PLAN.md`를 참고하세요. 과거 팔레트 정보는 `HISTORICAL_THEME_BASELINE.md`에 보존되어 있습니다.
        "primary": "#1f2937",      # 여기서 색상 변경
        "secondary": "#374151",
        ...
    }
}
```

### 2. 대시보드 레이아웃 변경
**파일**: `ui/dashboard_modern.py`
- 색상: `self.colors["primary"]` 사용
- 레이아웃: CustomTkinter API 사용

### 3. 위젯 디자인 변경
**파일**: `ui/widgets/*.py`
- 색상: `self._color("primary")` 사용 (대시보드에서 전달받음)
- 레이아웃: CustomTkinter API 사용

### 4. 전역 설정
**파일**: `main.py`, `ui/login_modern.py`, `ui/dashboard_modern.py`
```python
ctk.set_appearance_mode("dark")  # 다크/라이트 모드
```

## 🚫 문제 해결

### 테마가 안 나오는 경우
1. **ThemeManager 초기화 확인**
   - `ui/dashboard_modern.py` line 180: `self.theme_manager = ThemeManager()`
   - `ui/login_modern.py` line 38: `self.theme_manager = ThemeManager()`

2. **colors 전달 확인**
   - 대시보드 → 위젯: `colors=self.colors` 전달 확인
   - `grep "colors=self.colors" ui/dashboard_modern.py`

3. **테마 파일 확인**
   - `theme_system/color_palettes.py`: 색상 정의 확인
   - `theme_config.json`: 설정 확인

## 📊 현재 상태

### ✅ 정상 동작
- `ui/dashboard_modern.py`: ThemeManager 사용, colors 전달
- `ui/login_modern.py`: ThemeManager 사용, colors 사용
- `ui/widgets/ai_assistant_widget_modern.py`: colors 파라미터, 하드코딩 제거
- `ui/widgets/realtime_log_widget.py`: colors 파라미터, 하드코딩 제거

### 🎯 사용 중인 테마
- 이름: `modern_dark` (모던 다크)
- 파일: `theme_system/color_palettes.py` line 16-37
- 설정: `data/nwsoft/config/theme_config.json`

