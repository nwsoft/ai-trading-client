# 대시보드 버튼 분석 (이력 보관)

## 클릭 가능한 버튼 목록

### 1. 상단 헤더 버튼들

#### 1.1 "모두 시작" 버튼 (Line 945-958)
```python
self.start_stop_btn = ctk.CTkButton(
    button_frame,
    text="▶️ 모두 시작",
    command=self._on_start_stop_clicked,
    height=50,
    fg_color=self.colors["success"],
    text_color=self.colors["text_primary"],
    hover_color=self.colors["success"],
    corner_radius=25
)
```
**상태**: ✅ 테마 색상 사용 중

#### 1.2 "설정" 버튼 (Line 961-974)
```python
self.settings_btn = ctk.CTkButton(
    button_frame,
    text="⚙️ 설정",
    command=self.show_settings_dialog,
    height=50,
    fg_color=self.colors["secondary"],
    text_color=self.colors["text_primary"],
    hover_color=self.colors["hover"],
    corner_radius=25
)
```
**상태**: ✅ 테마 색상 사용 중

### 2. 서비스 탭 버튼들 (Line 978-1074)

#### 2.1 "블록체인" 버튼 (Line 997-1010)
```python
self.blockchain_btn = ctk.CTkButton(
    parent,
    text="🔗 블록체인",
    command=lambda: self.switch_service("blockchain"),
    height=35,
    fg_color=active_color,  # self.colors["info"] 또는 inactive
    text_color=text_color,  # self.colors["text_primary"]
    hover_color=hover_color,  # self.colors["hover"]
    corner_radius=8
)
```
**상태**: ✅ 테마 색상 사용 중 (`self.colors` 사용)

#### 2.2 "주식/증권" 버튼 (Line 1013-1026)
```python
self.stock_btn = ctk.CTkButton(
    parent,
    text="📈 주식/증권",
    command=lambda: self._on_stock_click(),
    height=35,
    fg_color=active_color,
    text_color=text_color,
    hover_color=hover_color,
    corner_radius=8
)
```
**상태**: ✅ 테마 색상 사용 중

#### 2.3 "부동산" 버튼 (Line 1029-1042)
```python
self.real_estate_btn = ctk.CTkButton(
    parent,
    text="🏠 부동산",
    command=lambda: self._on_real_estate_click(),
    height=35,
    fg_color=active_color,
    text_color=text_color,
    hover_color=hover_color,
    corner_radius=8
)
```
**상태**: ✅ 테마 색상 사용 중

#### 2.4 "기타투자" 버튼 (Line 1045-1058)
```python
self.other_investment_btn = ctk.CTkButton(
    parent,
    text="💼 기타투자",
    command=lambda: self._on_other_investment_click(),
    height=35,
    fg_color=active_color,
    text_color=text_color,
    hover_color=hover_color,
    corner_radius=8
)
```
**상태**: ✅ 테마 색상 사용 중

#### 2.5 "AI애널리스트" 버튼 (Line 1061-1074)
```python
self.ai_analyst_btn = ctk.CTkButton(
    parent,
    text="🤖 AI애널리스트",
    command=lambda: self._on_ai_analyst_click(),
    height=35,
    fg_color=active_color,
    text_color=text_color,
    hover_color=hover_color,
    corner_radius=8
)
```
**상태**: ✅ 테마 색상 사용 중

### 3. 우측 패널 Quick Actions 버튼들 (Line 3101-3123)

#### 3.1 "차트 이미지 분석" 버튼 (Line 3101-3112)
```python
ctk.CTkButton(
    quickbar2,
    text="📊 차트 이미지 분석",
    width=160,
    fg_color=self.colors["secondary"],
    text_color="white",  # ⚠️ 하드코딩!
    hover_color=self.colors["hover"],
    corner_radius=8,
    command=self._open_chart_screenshot_analyzer
)
```
**상태**: ⚠️ `text_color="white"` 하드코딩

#### 3.2 "사용자 매뉴얼" 버튼 (Line 3114-3123)
```python
ctk.CTkButton(
    quickbar2,
    text="📚 사용자 매뉴얼",
    width=130,
    fg_color=self.colors["secondary"],
    text_color="white",  # ⚠️ 하드코딩!
    hover_color=self.colors["hover"],
    corner_radius=8,
    command=self._open_manual_modal
)
```
**상태**: ⚠️ `text_color="white"` 하드코딩

### 4. 기타 버튼들

#### 4.1 "확인" 버튼 (모달) (Line 1316-1325)
- 테마 색상 사용

#### 4.2 "출시 알림 받기" 버튼 (Line 1328-1337)
- 하드코딩 색상 사용

#### 4.3 "신청하기" 버튼 (Line 1383-1391)
- 하드코딩 색상 사용

#### 4.4 "취소" 버튼 (Line 1394-1403)
- 하드코딩 색상 사용

#### 4.5 "거래소 시작" 버튼 (Line 1856-1866)
```python
toggle_btn = ctk.CTkButton(
    btn_frame,
    text=f"▶️ {exchange.upper()} 시작",
    fg_color="#10b981",  # ⚠️ 하드코딩!
    ...
)
```
**상태**: ⚠️ `fg_color="#10b981"` 하드코딩

## 발견된 하드코딩 문제

### 🔴 수정 필요
1. **Quick Actions 버튼들** (Line 3101-3123)
   - `text_color="white"` → `text_color=self.colors["text_primary"]`

2. **거래소 시작 버튼** (Line 1856-1866)
   - `fg_color="#10b981"` → `fg_color=self.colors["success"]`

### ✅ 올바르게 설정된 버튼
- 모든 헤더 버튼 (모두 시작, 설정)
- 모든 서비스 탭 버튼 (블록체인, 주식, 부동산, 기타투자, AI애널리스트)

