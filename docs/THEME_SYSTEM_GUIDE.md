# [폐기] 테마 시스템 가이드라인

## 📋 개요

이 문서는 2025-10-29 기준으로 폐기되었습니다. 프로젝트는 테마 시스템을 더 이상 사용하지 않으며, 단일 고정 스킨(하드코딩) 방식으로 전환되었습니다. 최신 가이드는 `UI_FIXED_SKIN_PLAN.md`를 확인하세요. 과거 팔레트 값은 `HISTORICAL_THEME_BASELINE.md`에 보존되어 있습니다.

2026-08-01 최종 정리에서 `theme_system` 소스 6개도 프로젝트 외부 격리로 이동했습니다. 현행 코드는 `utils.fixed_colors`와 `ui.visual_system`만 사용하며 아래 import 예시는 실행하면 안 되는 과거 기록입니다.

## (폐기)

```python
from theme_system import ThemeManager

class ModernDashboard:
    def __init__(self):
        # 테마 관리자 초기화
        self.theme_manager = ThemeManager()
        self.colors = self.theme_manager.get_current_colors()
        self.fonts = self.theme_manager.get_current_fonts()
```

**준수 사항**:
- ✅ ThemeManager 인스턴스 생성
- ✅ `self.colors` 딕셔너리 사용
- ✅ `self.fonts` 딕셔너리 사용

### 2. 위젯 (하위 컴포넌트)

```python
class MyWidget(CTkFrame):
    def __init__(self, parent, colors=None):
        super().__init__(parent)
        
        # 대시보드에서 전달받은 colors만 사용
        self.colors = dict(colors) if colors and isinstance(colors, dict) else {}
        
        # 하드코딩 색상 절대 금지 ❌
```

**준수 사항**:
- ✅ `colors` 파라미터로 받기
- ✅ 하드코딩 색상 제거
- ✅ ThemeManager 직접 생성 금지
- ✅ 대시보드에서 전달받은 colors만 사용

### 3. 대시보드에서 위젯 호출

```python
# ✅ 올바른 방법
widget = MyWidget(parent, colors=self.colors)

# ❌ 잘못된 방법
widget = MyWidget(parent)  # colors 전달 안함
widget = MyWidget(parent, colors={...})  # 새 colors 딕셔너리 전달
```

## 🚫 금지 사항

### 1. 하드코딩 색상 사용 금지

```python
# ❌ 잘못된 방법
self.label = CTkLabel(self, fg_color="#3b82f6")
self.colors = {"primary": "#3b82f6"}  # fallback 색상 하드코딩

# ✅ 올바른 방법
self.label = CTkLabel(self, fg_color=self._color("primary"))
```

### 2. 위젯에서 ThemeManager 생성 금지

```python
# ❌ 잘못된 방법
self.theme_manager = ThemeManager()
self.colors = self.theme_manager.get_current_colors()

# ✅ 올바른 방법
# colors를 파라미터로 받기
```

### 3. 대시보드에서 colors 전달 누락 금지

```python
# ❌ 잘못된 방법
widget = MyWidget(parent)

# ✅ 올바른 방법
widget = MyWidget(parent, colors=self.colors)
```

## 📊 데이터 흐름

```
ThemeManager
    ↓
대시보드/로그인창
    ↓ (colors 전달)
위젯 (하드코딩 없음)
```

## 🔧 수정 시 체크리스트

### 대시보드 수정 시
- [ ] ThemeManager 초기화 확인
- [ ] self.colors, self.fonts 설정 확인
- [ ] 위젯 호출 시 colors 전달 확인

### 위젯 수정 시
- [ ] colors 파라미터 정의 확인
- [ ] 하드코딩 색상 제거 확인
- [ ] ThemeManager 직접 생성 제거 확인
- [ ] fallback 딕셔너리 제거 확인

## 📝 현재 상태

### ✅ 올바르게 구현된 파일
- `ui/dashboard_modern.py`: ThemeManager 사용, colors 전달
- `ui/login_modern.py`: ThemeManager 사용, colors 전달
- `ui/widgets/realtime_log_widget.py`: colors 파라미터 사용, 하드코딩 제거
- `ui/widgets/ai_assistant_widget_modern.py`: colors 파라미터 사용, 하드코딩 제거

### � 2025-10-28 업데이트
- `ui/dashboard_modern.py` Quick Actions 버튼과 글로벌 제어 버튼이 테마 색상 기반 CTkImage 아이콘을 동적으로 생성하도록 변경함 (`_get_icon`, `_refresh_quick_action_buttons`).
- 시작/정지, 설정 버튼은 `_refresh_start_button_appearance`, `_refresh_settings_button_appearance`를 통해 테마 팔레트 변화와 거래 상태에 따라 색상·아이콘이 자동 갱신됨.
- 차트 분석/사용자 매뉴얼 퀵 액션은 이제 ThemeManager에서 받은 colors만 사용하며, 새로 생성한 모달 핸들러 `_open_chart_screenshot_analyzer`, `_open_manual_modal`로 안정적으로 동작함.

### �🎯 현재 흐름
1. 대시보드: `ThemeManager()` → `self.colors` → 위젯에 전달
2. 위젯: `colors` 파라미터로 받아서 `self.colors = dict(colors)` 사용
3. 충돌 방지: 하드코딩 없음, 대시보드 기준만 사용

## 🚨 문제 발생 시 확인 사항

1. **위젯이 하드코딩 색상 사용?**
   - ❌ → 제거 필요

2. **대시보드가 colors 전달 안함?**
   - ❌ → `colors=self.colors` 추가 필요

3. **위젯이 ThemeManager 직접 생성?**
   - ❌ → 제거 필요

4. **ThemeManager import 누락?**
   - ❌ → `from theme_system import ThemeManager` 추가 필요

