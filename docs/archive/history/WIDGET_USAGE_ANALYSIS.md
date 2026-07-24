# Widget 사용 현황 및 하드코딩 색상 분석 (이력 보관)

## 📋 분석 결과

### 1. MarketTrendWidget (하드코딩 9개 색상)
**사용 위치**: `ui/dashboard_modern.py` line 3844
**호출 방식**: `MarketTrendWidget(tab, dashboard_ref=self)`
**colors 전달**: ❌ 전달 안함
**하드코딩 색상**: 
- line 43-51: `"#1f538d"`, `"#2b7a0b"`, `"#6b7280"`
- line 520-557: `"#059669"`, `"#dc2626"`, `"#2563eb"`, `"#f59e0b"`
**원인**: 동적 채널/방향 색상 - 성공(#059669), 위험(#dc2626), 중립(#6b7280)
**필요성**: ⚠️ 부분 필요 (동적 색상은 하드코딩, 기본 텍스트는 테마)

### 2. ChartScreenshotWidget (하드코딩 6개 색상)
**사용 위치**: `ui/dashboard_modern.py` line 3198
**호출 방식**: `ChartScreenshotWidget(win, ai_client=ai_client)`
**colors 전달**: ❌ 전달 안함
**하드코딩 색상**:
- line 70, 207, 215, 224: `"#9aa0a6"` (회색 텍스트)
- line 223: `"#2ecc71"` (초록 텍스트 - LONG 표시)
- line 381: `"#f1c40f"` (노란 경고)
- line 383: `"#e74c3c"` (빨간 에러)
**원인**: 상태 색상 (정상/경고/에러 구분)
**필요성**: ⚠️ 부분 필요 (상태 색상만 하드코딩, 기본 텍스트는 테마)

### 3. AIReportWidgetReal (하드코딩 5개 색상)
**사용 위치**: `ui/dashboard_modern.py` line 3511
**호출 방식**: `AIReportWidgetReal(container)`
**colors 전달**: ❌ 전달 안함
**하드코딩 색상**:
- line 84, 149-150: `"#e74c3c"` (버튼 색상)
- line 149: `"#c0392b"` (호버 색상)
- line 385-386: `"#9b59b6"`, `"#8e44ad"` (버튼 색상)
**원인**: 버튼, 위험/성공 구분 색상
**필요성**: ⚠️ 부분 필요 (기능 색상만 하드코딩, 기본 배경은 테마)

### 4. ai_learning_widget_fixed.py (하드코딩 3개 색상)
**사용 여부**: ⚠️ 확인 필요
**하드코딩 색상**: `"#e74c3c"`, `"#95a5a6"`, `"#27ae60"`
**원인**: 에러/정상 상태 구분
**필요성**: ⚠️ 부분 필요 (상태 색상만 하드코딩)

### 5. user_manual_widget.py (하드코딩 1개 색상)
**사용 여부**: ⚠️ 확인 필요
**하드코딩 색상**: `"#2c3e50"`
**원인**: 텍스트 색상
**필요성**: ❌ 테마로 대체 가능

## 🎯 결론

### 하드코딩이 필요한 경우
**동적 상태 색상** (성공/위험/중립 등):
- `"#059669"` (성공 - 녹색)
- `"#dc2626"` (위험 - 빨간색)
- `"#6b7280"` (중립 - 회색)

### 하드코딩 제거 가능
**정적 기본 색상**:
- 텍스트 색상: `"#9aa0a6"` → `self._color("text_secondary")`
- 배경 색상: CustomTkinter 기본 사용
- 버튼 색상: `"#e74c3c"` → `self._color("danger")`

## ✅ 권장 수정 방법

### 1. colors 파라미터 추가 (필수)
```python
def __init__(self, parent, dashboard_ref=None, colors=None):
    self.colors = dict(colors) if colors and isinstance(colors, dict) else {}
```

### 2. 기본 텍스트는 테마 사용
```python
# ❌
text_color="#9aa0a6"

# ✅
text_color=self._color("text_secondary")
```

### 3. 동적 상태 색상은 하드코딩 유지
```python
# ✅ 상태 색상은 하드코딩 OK
direction_color = "#059669"  # 성공
direction_color = "#dc2626"  # 위험
```

### 4. 대시보드에서 colors 전달
```python
# ❌ 현재
trend_widget = MarketTrendWidget(tab, dashboard_ref=self)

# ✅ 수정 필요
trend_widget = MarketTrendWidget(tab, dashboard_ref=self, colors=self.colors)
```

## 📊 수정 우선순위

### 높음 (colors 전달 누락)
1. **MarketTrendWidget** (line 3844) - colors 추가 필요
2. **ChartScreenshotWidget** (line 3198) - colors 추가 필요
3. **AIReportWidgetReal** (line 3511) - colors 추가 필요

### 중간 (하드코딩 부분 제거)
4. 기본 텍스트 색상 하드코딩 제거
5. 배경/테두리 색상 하드코딩 제거

### 낮음 (유지)
6. 동적 상태 색상 하드코딩 유지 (성공/위험 등)

