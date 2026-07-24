# 대시보드 우측 패널 코드 위치 (이력 보관)

## 📍 코드 위치

**파일**: `ui/dashboard_modern.py`

### 거래 현황 섹션
- **Line 3064-3096**: "거래 현황" 제목 + 카드 프레임 + 텍스트박스
- **카드 프레임**: Line 3070-3077
  - `fg_color=self.colors["surface"]`
  - `border_color=self.colors["border"]`
  - `corner_radius=10`
- **텍스트박스**: Line 3079-3088
  - `fg_color="transparent"`
  - `text_color=self.colors["text_primary"]`

### Quick Actions 섹션
- **Line 3097-3138**: "Quick Actions" 제목 + 카드 프레임 + 버튼들
- **카드 프레임**: Line 3106-3113
  - `fg_color=self.colors["surface"]`
  - `border_color=self.colors["border"]`
  - `corner_radius=10`
- **버튼**: Line 3116-3138
  - `fg_color=self.colors["secondary"]`
  - `hover_color=self.colors["hover"]`

### 통합 잔고 요약 섹션
- **Line 3140-3171**: "통합 잔고 요약" 제목 + 카드 프레임 + 텍스트박스
- **카드 프레임**: Line 3149-3156
  - `fg_color=self.colors["surface"]`
  - `border_color=self.colors["border"]`
  - `corner_radius=10`
- **텍스트박스**: Line 3158-3166
  - `fg_color="transparent"`
  - `text_color=self.colors["text_primary"]`

## 🎯 수정 방법

### 색상 수정
- **파일**: `theme_system/color_palettes.py` line 20-36
- 카드 배경: `"surface": "#1f2937"`
- 테두리: `"border": "#374151"`
- 텍스트: `"text_primary": "#f9fafb"`

### 디자인 수정
- **파일**: `ui/dashboard_modern.py`
- Line 3071-3076: 거래 현황 카드 스타일
- Line 3106-3113: Quick Actions 카드 스타일
- Line 3149-3156: 통합 잔고 카드 스타일

## ✅ 현재 상태
- 모든 색상은 `self.colors` 사용
- 하드코딩 없음
- 카드 디자인 적용됨

