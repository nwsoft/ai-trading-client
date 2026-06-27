# 거래 차단 원인 분석 및 해결 방안

## 🔍 문제 상황

- **증상**: 시그널은 발생하지만 한 시간 동안 거래가 실행되지 않음
- **설정값**: `user_signal_threshold = 68`로 변경했음에도 거래가 차단됨

---

## 🚨 발견된 문제점

### 1. **데이터 부족 시 강제 최소 임계값 (0.75)**

**위치**: `trading/trader.py` Line 3024

```python
else:
    # 데이터 부족: 더 보수적인 임계값 적용 (신뢰도 요구사항 강화)
    conservative_threshold = max(dynamic_confidence_threshold, 0.75)  # 최소 0.75 이상
    proceed = (
        market_conditions['volatility_suitable'] and
        ai_validation['confidence'] >= conservative_threshold
    )
```

**문제점:**
- `user_signal_threshold`가 68이면 `dynamic_confidence_threshold`는 0.68 (68/100)이 됩니다.
- 하지만 거래 이력이 20회 미만이면 `data_insufficient = True`가 되고, 이 경우 **최소 0.75 (75%)를 강제**합니다.
- AI 검증의 기본 신뢰도는 0.7 (70%)인데, 0.75를 요구하므로 **0.7 < 0.75로 거래가 차단**됩니다.

**영향:**
- 거래 이력이 적은 코인은 거의 거래가 불가능합니다.
- 새로 시작하는 코인은 첫 거래가 매우 어렵습니다.

---

### 2. **거래 이력 부족 판단 기준**

**위치**: `trading/trader.py` Line 3134

```python
'data_insufficient': bool(total < 20),  # 최소 20회 필요
```

**문제점:**
- 거래 이력이 20회 미만이면 `data_insufficient = True`가 됩니다.
- 이 경우 위의 0.75 강제 임계값이 적용됩니다.

---

### 3. **AI 검증 기본 신뢰도**

**위치**: `trading/trader.py` Line 3207

```python
confidence = 0.7  # 기본 신뢰도
```

**문제점:**
- 기본 신뢰도가 0.7 (70%)입니다.
- 데이터 부족 시 0.75를 요구하므로 기본 신뢰도로는 통과할 수 없습니다.

---

## 🔧 해결 방안

### 방안 1: 데이터 부족 시 임계값을 user_signal_threshold 기반으로 조정

**수정 위치**: `trading/trader.py` Line 3022-3028

**현재 코드:**
```python
else:
    # 데이터 부족: 더 보수적인 임계값 적용 (신뢰도 요구사항 강화)
    conservative_threshold = max(dynamic_confidence_threshold, 0.75)  # 최소 0.75 이상
    proceed = (
        market_conditions['volatility_suitable'] and
        ai_validation['confidence'] >= conservative_threshold
    )
```

**수정안:**
```python
else:
    # 데이터 부족: user_signal_threshold 기반 임계값 사용 (0.75 강제 제거)
    # dynamic_confidence_threshold는 이미 user_signal_threshold를 반영함 (68 → 0.68)
    conservative_threshold = dynamic_confidence_threshold  # 0.75 강제 제거
    proceed = (
        market_conditions['volatility_suitable'] and
        ai_validation['confidence'] >= conservative_threshold
    )
```

**효과:**
- `user_signal_threshold = 68`이면 `dynamic_confidence_threshold = 0.68`이 됩니다.
- 데이터 부족 시에도 0.68을 요구하므로 기본 신뢰도 0.7로 통과 가능합니다.

---

### 방안 2: 데이터 부족 시 임계값을 약간만 높이기 (권장)

**수정안:**
```python
else:
    # 데이터 부족: user_signal_threshold 기반 + 소폭 보정 (0.75 강제 제거)
    # dynamic_confidence_threshold는 이미 user_signal_threshold를 반영함
    # 데이터 부족 시 약간만 높임 (최대 +0.05)
    conservative_threshold = min(dynamic_confidence_threshold + 0.05, 0.70)  # 최대 0.70
    proceed = (
        market_conditions['volatility_suitable'] and
        ai_validation['confidence'] >= conservative_threshold
    )
```

**효과:**
- `user_signal_threshold = 68`이면 `dynamic_confidence_threshold = 0.68` → `conservative_threshold = 0.73`
- 기본 신뢰도 0.7로는 통과할 수 없지만, 약간의 조정으로 통과 가능합니다.
- 최대 0.70으로 제한하여 과도한 보수성을 방지합니다.

---

### 방안 3: AI 검증 기본 신뢰도 조정

**수정 위치**: `trading/trader.py` Line 3207

**현재 코드:**
```python
confidence = 0.7  # 기본 신뢰도
```

**수정안:**
```python
confidence = 0.75  # 기본 신뢰도 (데이터 부족 시 임계값 0.75에 맞춤)
```

**효과:**
- 기본 신뢰도를 0.75로 높여 데이터 부족 시에도 통과 가능합니다.
- 하지만 이 방법은 모든 경우에 신뢰도를 높이므로 덜 선호됩니다.

---

## 📊 권장 해결책

**방안 2를 권장합니다.**

**이유:**
1. `user_signal_threshold` 설정을 존중하면서도 데이터 부족 시 약간의 보정을 적용합니다.
2. 최대 0.70으로 제한하여 과도한 보수성을 방지합니다.
3. 기존 로직의 의도(데이터 부족 시 보수적 접근)를 유지하면서도 거래 가능성을 높입니다.

**수정 코드:**
```python
else:
    # 데이터 부족: user_signal_threshold 기반 + 소폭 보정
    # dynamic_confidence_threshold는 이미 user_signal_threshold를 반영함 (68 → 0.68)
    # 데이터 부족 시 약간만 높임 (최대 +0.05, 최대값 0.70)
    conservative_threshold = min(dynamic_confidence_threshold + 0.05, 0.70)
    proceed = (
        market_conditions['volatility_suitable'] and
        ai_validation['confidence'] >= conservative_threshold
    )
```

**예상 결과:**
- `user_signal_threshold = 68` → `dynamic_confidence_threshold = 0.68` → `conservative_threshold = 0.73`
- 기본 신뢰도 0.7로는 통과할 수 없지만, 약간의 조정(신호 강도 등)으로 통과 가능합니다.
- 또는 기본 신뢰도를 0.73 이상으로 조정하면 통과 가능합니다.

---

## 🔍 추가 확인 사항

### 거래 이력 부족 판단 기준 완화 검토

**현재**: `total < 20` (20회 미만)

**검토 사항:**
- 20회는 다소 높은 기준일 수 있습니다.
- 10회 또는 5회로 낮추는 것도 고려할 수 있습니다.
- 하지만 이는 기존 로직의 의도와 다를 수 있으므로 신중히 결정해야 합니다.

---

## 📝 수정 요약

1. **`trading/trader.py` Line 3024**: `0.75` 강제 제거, `user_signal_threshold` 기반으로 조정
2. **선택적**: `trading/trader.py` Line 3207: 기본 신뢰도 조정 (0.7 → 0.75 또는 동적 계산)

---

## 📅 작성일

2025-01-27

