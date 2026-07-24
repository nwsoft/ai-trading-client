# 코인 재선택 로직 안전성 분석 (2026-01-18, 이력 보관)

## 📋 분석 목적

코인 재선택 로직 수정 후, 실제 거래 중에 발생할 수 있는 문제점을 사전에 확인하고 안전성을 검증합니다.

## ✅ 확인 사항

### 1. 중복 호출 문제

**호출 경로:**
1. `trading_worker.py` → `select_trading_coins()` (초기 선택, 라인 109)
2. `_check_and_reselect_coins_optimized()` → `select_trading_coins()` (코인 비어있을 때, 라인 1076)
3. `_reselect_coins()` → `select_trading_coins()` (재선택, 라인 1168)

**결과: ✅ 문제 없음**
- 경로 2는 코인이 비어있을 때만 호출하고 `return`하므로, 경로 3과 겹치지 않음
- 경로 1은 초기 선택 시에만 호출 (조건: `not selected_coins`)
- 각 경로가 서로 다른 조건에서 실행되어 중복 호출 문제 없음

### 2. 거래 중 코인 변경 시 안전성

**시나리오:** 거래 중 `select_trading_coins()`가 호출되어 `selected_coins`가 변경됨
- 예: AVXUSDT를 보유 중인데, 재선택 후 `selected_coins`에서 AVXUSDT가 제거됨

**분석:**
```python
# execute_trading_cycle() 라인 1541-1568
# 1. 활성 포지션 심볼 추출
open_symbols = set(active_positions.keys())  # 예: {'AVXUSDT', 'LINKUSDT'}

# 2. selected_coins 필터링 (보유 중인 심볼 제외)
filtered = [c for c in selected_coins if coin_symbol(c) not in open_symbols]

# 3. 필터링된 코인만 거래 대상으로 사용
selected_coins = filtered
```

**결과: ✅ 문제 없음**
- `active_positions`와 `selected_coins`는 **독립적으로 관리**됨
- 거래 중인 코인이 `selected_coins`에서 제거되어도 **포지션에는 영향 없음**
- `execute_trading_cycle()`에서 **필터링**하여 보유 중인 코인은 제외하고, 새로운 코인만 거래 대상으로 사용
- 재선택으로 인해 거래 중인 코인이 `selected_coins`에서 사라져도, 해당 코인은 `open_symbols`에 포함되어 필터링되어 **안전함**

### 3. 코인 선택 기준 일관성

**초기 선택:**
- `main.py.select_trading_coins()` 호출 (라인 2669)
- 시장 상황 분석 → 코인 수 결정 → Evaluator로 코인 선택

**재선택:**
- `_reselect_coins()` → `main_app.select_trading_coins()` 호출 (라인 1168)
- **동일한 메서드 사용**

**결과: ✅ 기준 동일**
- 초기 선택과 재선택 모두 **동일한 `select_trading_coins()` 메서드 사용**
- 시장 상황에 따른 코인 수 결정 로직 동일
- Evaluator를 통한 코인 선택 로직 동일

### 4. 모듈화 고려

**코인 저장 위치:**
- `main_app.selected_coins`: 단일 소스 (모든 컴포넌트가 참조)
- `trader.selected_coins`: 사용 안 함 (라인 206에서 빈 리스트로 초기화)

**결과: ✅ 모듈화 고려됨**
- `_check_and_reselect_coins_optimized()`는 `main_app.selected_coins`만 참조 (라인 1071)
- `_reselect_coins()`도 `main_app.selected_coins`만 사용 (라인 1161, 1169)
- `execute_trading_cycle()`도 `main_app.selected_coins`만 사용 (라인 1547)
- **단일 소스 원칙 준수**

### 5. 거래 중 재선택 타이밍 안전성

**재선택 조건:**
1. **시장 상황 변경 + 포지션 < 50%**: 재선택 실행
2. **시장 상황 변경 + 포지션 >= 50%**: 재선택 연기
3. **시장 상황 유지 + 3시간 경과 + 포지션 < 70%**: 재선택 실행
4. **시장 상황 유지 + 3시간 경과 + 포지션 >= 70%**: 재선택 연기

**결과: ✅ 안전함**
- 포지션이 많을 때는 재선택을 **연기**하여 거래 중단 방지
- 포지션이 적을 때만 재선택하여 **새로운 기회 포착**
- 재선택 후에도 `execute_trading_cycle()`에서 필터링하여 **보유 중인 코인 보호**

## 🔍 실제 동작 흐름

### 시나리오 1: 거래 중 시장 상황 변경

```
1. 현재 상태:
   - active_positions: {'AVXUSDT', 'LINKUSDT'}
   - selected_coins: ['AVXUSDT', 'LINKUSDT', 'BNBUSDT', 'ETHUSDT', ...]

2. 1시간 경과 + 시장 상황 변경 감지
   → 포지션 2개 < 50% (max_positions=3 기준 1.5개)
   → 재선택 실행

3. select_trading_coins() 호출
   → 새로운 selected_coins: ['YFIUSDT', 'DOTUSDT', 'CHZUSDT', ...]
   → AVXUSDT, LINKUSDT가 제거됨

4. 다음 execute_trading_cycle() 실행
   → open_symbols = {'AVXUSDT', 'LINKUSDT'}
   → filtered = [c for c in selected_coins if coin_symbol(c) not in open_symbols]
   → filtered: ['YFIUSDT', 'DOTUSDT', 'CHZUSDT', ...]
   → AVXUSDT, LINKUSDT는 필터링되어 제외됨 ✅

5. 결과:
   - AVXUSDT, LINKUSDT 포지션은 그대로 유지됨
   - 새로운 코인(YFIUSDT, DOTUSDT 등)만 거래 대상
```

### 시나리오 2: 거래 중 시장 상황 유지 (3시간 경과)

```
1. 현재 상태:
   - active_positions: {'AVXUSDT'} (1개 < 70%, max_positions=3 기준 2.1개)
   - selected_coins: ['AVXUSDT', 'LINKUSDT', ...]

2. 3시간 경과 + 시장 상황 유지
   → 포지션 1개 < 70%
   → 재선택 실행 (코인 다양성 확보)

3. select_trading_coins() 호출
   → 새로운 selected_coins 선택

4. 다음 execute_trading_cycle() 실행
   → 필터링하여 보유 중인 코인 제외
   → 새로운 코인만 거래 대상 ✅
```

## ⚠️ 주의사항

1. **포지션 보호**: `execute_trading_cycle()`의 필터링 로직이 거래 중인 코인을 보호함
2. **재선택 타이밍**: 포지션이 많을 때는 재선택을 연기하여 거래 중단 방지
3. **단일 소스**: `main_app.selected_coins`만 사용하여 일관성 유지

## ✅ 결론

**모든 시나리오에서 안전함**

1. ✅ 중복 호출 문제 없음
2. ✅ 거래 중 코인 변경 시 안전함 (필터링으로 보호)
3. ✅ 코인 선택 기준 일관성 유지
4. ✅ 모듈화 고려됨 (단일 소스 원칙)
5. ✅ 재선택 타이밍 안전함 (포지션 수 고려)

**수정 내용이 안전하고 정상적으로 작동함을 확인했습니다.**
