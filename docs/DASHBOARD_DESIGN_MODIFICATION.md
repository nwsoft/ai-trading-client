# 대시보드 디자인 수정 가이드

## 🎯 핵심 원칙

**대시보드 파일 수정 금지** - 색상/모서리 관리는 테마 시스템이 처리

## 📝 수정 가능한 항목별 파일 위치

### 1. 색상 (배경, 텍스트, 버튼 등)
**파일**: 	heme_system/color_palettes.py line 16-36
`python
"modern_dark": {
    "colors": {
        "background": "#111827",   # 배경색
        "surface": "#1f2937",       # 카드 배경
        "border": "#374151",        # 테두리 색상
        "text_primary": "#f9fafb",   # 주 텍스트
        ...
    }
}
`

### 2. 모서리 라운드 (corner_radius)
**현재**: CustomTkinter 기본 사용
**수정 위치**: ui/dashboard_modern.py에서 위젯 생성 시
`python
CTkButton(self, corner_radius=10)  # 여기서 설정
`

### 3. 레이아웃 (위치, 크기, 배치)
**파일**: ui/dashboard_modern.py
- 위젯 생성, grid/pack 배치 코드 수정

## 🚫 수정 불가능한 부분

1. **대시보드에서 직접 색상 하드코딩**: 금지 ❌
   - 모든 색상은 self.colors["key"]로 사용
   - 하드코딩하면 테마 충돌 발생

2. **위젯에서 ThemeManager 생성**: 금지 ❌
   - 위젯은 colors 파라미터로만 받기

## 🔧 색상 변경 예시

### 배경색 변경
`python
# theme_system/color_palettes.py line 28
"background": "#111827",  # 기본
"background": "#0a0a0a",  # 더 어두운 배경
`

### 버튼 색상 변경
`python
# theme_system/color_palettes.py line 21
"primary": "#1f2937",    # 기본
"primary": "#3b82f6",   # 파란색
`

## ✅ 올바른 수정 방법

### 문제: 배경색이 너무 밝음
- ❌ ui/dashboard_modern.py 수정 안함
- ✅ 	heme_system/color_palettes.py 수정

### 문제: 버튼 모서리가 너무 둥글거나 각짐
- ✅ ui/dashboard_modern.py에서 corner_radius 값 변경

### 문제: 레이아웃이 어색함
- ✅ ui/dashboard_modern.py에서 grid/pack 위치 조정

## 📊 현재 동작 방식

`
theme_system/color_palettes.py
    ↓ (색상 정의)
theme_manager.py
    ↓ (ThemeManager 초기화)
ui/dashboard_modern.py
    ↓ (self.colors 딕셔너리)
ui/widgets/*.py
    ↓ (colors 파라미터)
실제 UI 표시
`

## 🎨 디자인 수정 체크리스트

- [ ] 색상 변경: 	heme_system/color_palettes.py
- [ ] 모서리: ui/dashboard_modern.py의 corner_radius
- [ ] 레이아웃: ui/dashboard_modern.py의 grid/pack
- [ ] 하드코딩 색상 제거 확인
- [ ] colors 파라미터 전달 확인

## 🚨 주의사항

1. **색상 하드코딩 절대 금지**: 테마 시스템 충돌
2. **대시보드가 색상 소스**: 위젯은 colors만 받기
3. **ThemeManager는 대시보드만**: 위젯에서는 생성 금지
