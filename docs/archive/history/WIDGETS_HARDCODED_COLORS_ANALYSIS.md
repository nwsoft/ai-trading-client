# Widgets 폴더 하드코딩 색상 분석 (이력 보관)

## 🔍 분석 결과

### ✅ 하드코딩 없는 파일 (colors 파라미터 사용)
- `realtime_log_widget.py`: colors 파라미터 사용, 하드코딩 제거됨 ✅
- `ai_assistant_widget_modern.py`: colors 파라미터 사용, 하드코딩 제거됨 ✅

### ❌ 하드코딩 색상 사용 중인 파일

#### 1. market_trend_widget.py
**위치**: line 43-51, 520-557
```python
# 하드코딩된 색상
"#1f538d", "#2b7a0b", "#6b7280", "#14375e", "#059669", "#dc2626", 
"#2563eb", "#6b7280", "#f59e0b"
```
**문제**: 칩(채널) 색상이 하드코딩되어 테마와 충돌

#### 2. chart_screenshot_widget.py  
**위치**: line 70, 207, 215, 223, 362, 381, 383
```python
# 하드코딩된 색상
"#9aa0a6", "#2ecc71", "#f1c40f", "#e74c3c"
```
**문제**: 텍스트 색상이 하드코딩

#### 3. ai_report_widget_real.py
**위치**: line 84, 149-150, 181, 385-386
```python
# 하드코딩된 색상
"#7f8c8d", "#e74c3c", "#c0392b", "#9b59b6", "#8e44ad"
```
**문제**: 버튼, 텍스트 색상 하드코딩

#### 4. ai_learning_widget_fixed.py
**위치**: line 120, 142, 223, 458
```python
# 하드코딩된 색상
"#e74c3c", "#95a5a6", "#27ae60"
```
**문제**: 텍스트 색상 하드코딩

#### 5. user_manual_widget.py
**위치**: line 52
```python
# 하드코딩된 색상
"#2c3e50"
```
**문제**: 텍스트 색상 하드코딩

## 🚨 충돌 가능성

### 테마 시스템과 충돌
1. **대시보드**: `theme_system/color_palettes.py`에서 색상 정의
2. **위젯**: 하드코딩된 색상 사용
3. **결과**: 테마 변경해도 위젯 색상 안바뀜, 일관성 깨짐

### 예시 충돌
- 대시보드: `"text_primary": "#f9fafb"` (밝은 회색)
- 위젯: `text_color="#9aa0a6"` (하드코딩된 회색)
- 결과: 서로 다른 색상 표시

## ✅ 해결 방법

### 1. colors 파라미터 추가
```python
def __init__(self, parent, colors=None):
    self.colors = dict(colors) if colors and isinstance(colors, dict) else {}
```

### 2. 하드코딩 제거
```python
# ❌ 하드코딩
text_color="#9aa0a6"

# ✅ 테마 사용
text_color=self._color("text_secondary")
```

### 3. 대시보드에서 colors 전달
```python
# ui/dashboard_modern.py
widget = MyWidget(parent, colors=self.colors)
```

## 📋 수정 우선순위

### 높음 (테마 충돌 심각)
1. `market_trend_widget.py` - 칩 색상 하드코딩
2. `chart_screenshot_widget.py` - 텍스트 색상 하드코딩
3. `ai_report_widget_real.py` - 버튼 색상 하드코딩

### 중간 (사용 빈도 낮음)
4. `ai_learning_widget_fixed.py`
5. `user_manual_widget.py`

### 낮음 (구버전/미사용)
6. `ai_assistant_widget.py` (구버전)
7. `ai_learning_widget.py` (구버전)
8. `ai_report_widget.py` (구버전)

## 🎯 결론

**하드코딩 제거해야 할 파일**: 5개
**충돌 가능성**: 높음 (테마 변경 시 일관성 깨짐)
**권장 조치**: colors 파라미터 추가 및 하드코딩 제거

