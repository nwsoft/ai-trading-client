# 설정값 리셋 문제 분석

## 🚨 문제 상황

사용자가 설정값을 수정해도 프로그램 재시작 시 다시 원래대로 돌아가는 문제가 발생하고 있습니다.

---

## 🔍 원인 분석

### 1. `load_settings()` 함수가 매번 템플릿과 병합

**위치**: `config/settings.py` Line 178-240

```python
def load_settings() -> Dict[str, Any]:
    # ...
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        # 🔄 템플릿에서 새로운 설정 업데이트
        settings = update_settings_from_template(settings)  # ⚠️ 매번 호출됨
        
        # 업데이트된 설정 저장
        save_settings(settings)  # ⚠️ 템플릿 병합 결과를 저장
```

**문제점:**
- `load_settings()`가 호출될 때마다 `update_settings_from_template()` 호출
- 템플릿과 병합한 결과를 다시 저장
- 사용자가 수정한 값이 템플릿 값으로 덮어씌워질 수 있음

---

### 2. `deep_merge_settings()` 함수의 중첩 딕셔너리 처리 문제

**위치**: `config/settings.py` Line 76-156

```python
def deep_merge_settings(existing: Dict[str, Any], template: Dict[str, Any]) -> Dict[str, Any]:
    result = existing.copy()
    
    for key, template_value in template.items():
        if isinstance(template_value, dict) and isinstance(result[key], dict):
            # 모든 딕셔너리는 사용자 설정 보존 (새로운 키만 추가)
            merged_dict = result[key].copy()
            for nested_key, nested_value in template_value.items():
                if nested_key not in merged_dict:
                    merged_dict[nested_key] = nested_value
                    print(f"  ➕ {key}.{nested_key} 추가: {nested_value}")
                # 기존 키는 전부 보존 (템플릿으로 덮어쓰지 않음)
            result[key] = merged_dict
```

**문제점:**
- 중첩된 딕셔너리의 경우 **1단계만 처리**하고 재귀적으로 처리하지 않음
- `analyzer_settings.user_signal_threshold`는 보존되지만
- `ai_trading_preferences.risk_levels.conservative.balance_utilization` 같은 **2단계 이상 중첩**은 제대로 보존되지 않을 수 있음

---

### 3. 보호되지 않는 설정 항목

**보호되는 항목** (Line 114-120):
- API 키들
- `selected_exchange`, `enabled_exchanges`
- `default_margin_type`, `paper_trading`, `demo_mode`

**보호되지 않는 항목:**
- `analyzer_settings.user_signal_threshold` (중첩 딕셔너리 내부)
- `ai_trading_preferences.risk_tolerance` (중첩 딕셔너리 내부)
- `ai_trading_preferences.balance_utilization_limit` (중첩 딕셔너리 내부)
- `exchange_risk_overrides.binance.max_position_size` (중첩 딕셔너리 내부)

---

## 🔧 해결 방안

### 방안 1: 중첩 딕셔너리 재귀 처리 추가 (권장)

**문제점:**
- 현재는 1단계 중첩만 처리
- 2단계 이상 중첩은 보존되지 않음

**해결책:**
```python
def deep_merge_settings(existing: Dict[str, Any], template: Dict[str, Any]) -> Dict[str, Any]:
    """깊은 병합으로 설정을 안전하게 업데이트 (사용자 설정 보존)"""
    result = existing.copy()
    
    for key, template_value in template.items():
        if key not in result:
            # 새로운 키는 추가
            result[key] = template_value
        elif isinstance(template_value, dict) and isinstance(result[key], dict):
            # 🔥 재귀적으로 병합 (2단계 이상 중첩도 처리)
            result[key] = deep_merge_settings(result[key], template_value)
        # ... 나머지 로직
```

---

### 방안 2: 중요한 설정 항목 보호 리스트 추가

**해결책:**
```python
# 보호할 설정 항목 리스트 확장
PROTECTED_SETTINGS = [
    'analyzer_settings.user_signal_threshold',
    'ai_trading_preferences.risk_tolerance',
    'ai_trading_preferences.balance_utilization_limit',
    'ai_trading_preferences.risk_levels.conservative.balance_utilization',
    'exchange_risk_overrides.binance.max_position_size',
    # ... 기타 중요한 설정
]

def is_protected_setting(key_path: str) -> bool:
    """설정 항목이 보호되는지 확인"""
    return key_path in PROTECTED_SETTINGS
```

---

### 방안 3: 템플릿 병합 빈도 제한

**문제점:**
- 매번 `load_settings()` 호출 시 템플릿 병합
- 불필요한 병합으로 인한 성능 저하 및 설정 덮어쓰기

**해결책:**
```python
# 템플릿 버전 체크
def load_settings() -> Dict[str, Any]:
    settings = json.load(f)
    
    # 템플릿 버전 확인
    template_version = get_template_version()
    settings_version = settings.get('_template_version', None)
    
    # 템플릿이 업데이트된 경우에만 병합
    if template_version != settings_version:
        settings = update_settings_from_template(settings)
        settings['_template_version'] = template_version
        save_settings(settings)
    
    return settings
```

---

## 📊 권장 해결책

### 단계별 적용

1. **방안 1: 중첩 딕셔너리 재귀 처리** (즉시 적용)
   - 2단계 이상 중첩도 보존
   - 가장 근본적인 해결책

2. **방안 2: 중요한 설정 항목 보호** (즉시 적용)
   - 명시적으로 보호할 항목 지정
   - 안전성 향상

3. **방안 3: 템플릿 병합 빈도 제한** (선택적)
   - 성능 개선
   - 불필요한 병합 방지

---

## 🎯 예상 결과

### 적용 전
- 사용자가 `analyzer_settings.user_signal_threshold = 68`로 수정
- 프로그램 재시작 시 템플릿 병합
- 템플릿 값(85)으로 덮어씌워짐 ❌

### 적용 후
- 사용자가 `analyzer_settings.user_signal_threshold = 68`로 수정
- 프로그램 재시작 시 템플릿 병합
- 사용자 값(68) 보존 ✅

---

## 📝 결론

**근본 원인:**
1. `load_settings()`가 매번 템플릿과 병합
2. 중첩 딕셔너리 재귀 처리 부족
3. 중요한 설정 항목 보호 리스트 부족

**해결책:**
1. 중첩 딕셔너리 재귀 처리 추가
2. 중요한 설정 항목 보호 리스트 추가
3. 템플릿 병합 빈도 제한 (선택적)

---

## 📅 작성일

2025-01-27

