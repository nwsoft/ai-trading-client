# Widget 하드코딩 색상 수정 계획

## 📋 수정 대상

### 1. MarketTrendWidget (line 3844)
**현재**: `MarketTrendWidget(tab, dashboard_ref=self)`
**수정**: `MarketTrendWidget(tab, dashboard_ref=self, colors=self.colors)`

### 2. ChartScreenshotWidget (line 3198)
**현재**: `ChartScreenshotWidget(win, ai_client=ai_client)`
**수정**: `ChartScreenshotWidget(win, ai_client=ai_client, colors=self.colors)`

### 3. AIReportWidgetReal (line 3511)
**현재**: `AIReportWidgetReal(container)`
**수정**: `AIReportWidgetReal(container, colors=self.colors)`

## ✅ 수정 방법

### 1. colors 파라미터 추가
```python
# 각 위젯의 __init__ 메서드에
def __init__(self, parent, ..., colors=None):
    self.colors = dict(colors) if colors and isinstance(colors, dict) else {}
```

### 2. 기본 색상 하드코딩 제거
```python
# ❌
text_color="#9aa0a6"

# ✅
text_color=self._color("text_secondary")
```

### 3. 동적 상태 색상은 유지
```python
# ✅ 상태 색상은 하드코딩 OK
direction_color = "#059669"  # 성공
direction_color = "#dc2626"  # 위험
```

## 🎯 최종 상태

- **대시보드**: ThemeManager로 colors 제공
- **위젯**: colors 파라미터로 받아서 기본 색상은 테마 사용
- **동적 색상**: 상태별 하드코딩 유지 (의도적)

결론: **colors 파라미터만 추가하면 충돌 해결**

