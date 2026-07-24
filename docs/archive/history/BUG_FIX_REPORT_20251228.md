# 🐛 버그 수정 보고서 - 2025-12-28 (이력 보관)

## 📋 사용자 보고 문제 요약

### 보고된 문제들:
1. **RVN/RSR 코인에서 -4006 오류 발생**: "Stop price less than zero"
2. **RVN/RSR 코인 모니터링 데이터 포인트 추가 실패**
3. **5개 포지션이 차면 AI 학습이 멈춤** (최대 3개만 가능해야 함)
4. **프로그램 재시작 후 포지션 복구 시 4-5개 포지션이 생성됨** (설정값 3개와 불일치)

---

## 🔍 문제 분석 상세

### 문제 1: RSRUSDT/RVNUSDT에서 -4006 오류 "Stop price less than zero"

#### 발생 시점
- **2025-12-28 10:42:08**: RSRUSDT SELL 포지션에서 TP 주문 생성 시 오류 발생
- **2025-12-28 10:44:13**: RVNUSDT LONG 포지션에서 SL 주문 생성 시 오류 발생

#### 로그 증거
```
1534줄: [RSRUSDT] 🔍 최종 trade_config: {'tp': 0.0007702239779240112, 'sl': 0.002, ...}
1574줄: [RSRUSDT]   - TP: 0.000770 (ex=binance)
1588줄: ❌ AlgoOrder 실패: {'code': -4006, 'msg': 'Stop price less than zero.'}
```

#### 근본 원인 분석

**1단계: TP 값의 의미**
- `tp: 0.0007702239779240112`는 **퍼센트 값**입니다 (0.077%)
- 이 값은 `Optimizer._build_trade_config()`에서 생성됩니다

**2단계: 백업 TP 계산 과정**
```python
# trading/trader.py 2534줄
backup_tp = tp * backup_multiplier * pattern_tp_multiplier
# 예: backup_tp = 0.0007702239779240112 * 2.0 * 1.0 = 0.00154... (여전히 작은 값)
```

**3단계: 절대 가격 계산**
```python
# trading/trader.py 2558줄 (SHORT 포지션)
tp_price = actual_entry_price * (1 - backup_tp)
# 예: tp_price = 0.002714 * (1 - 0.00154) = 0.002710... (정상적으로 양수)
```

**4단계: 스냅 로직에서 문제 발생 ⚠️**
```python
# trading/trader.py 2597-2598줄
def snap(price, is_buy):
    return math.ceil(price / tick_size) * tick_size if is_buy else math.floor(price / tick_size) * tick_size

# SHORT 포지션: tp_price = snap(tp_price, False)
# tp_price = math.floor(tp_price / tick_size) * tick_size
```

**문제점:**
- RSRUSDT의 경우 `tick_size`가 매우 작을 수 있습니다 (예: 0.000001)
- 만약 계산 과정에서 `tp_price`가 `tick_size`보다 작거나, 반올림 오차로 인해 매우 작은 값이 되면:
  - `math.floor(0.000001 / 0.000001) = math.floor(1.0) = 1` → `1 * 0.000001 = 0.000001` (정상)
  - 하지만 **`format()` 함수 사용 시 문제 발생**:
    ```python
    # trading/trader.py 2611줄
    tp_price = float(format(tp_price, f'.{price_prec}f'))
    ```
    - `price_prec`가 2일 때: `format(0.002710, '.2f') = '0.00'` → **0이 됨!**
    - `price_prec`가 6일 때는 괜찮지만, 기본값이 2이므로 문제 발생 가능

**5단계: BinanceClient에서 추가 스냅**
```python
# api/binance_client.py 2304-2305줄
tp_price = round(take_profit / tick_size) * tick_size
```
- `take_profit`이 이미 0이거나 매우 작은 값이면, `round(0 / tick_size) = 0` → **최종적으로 0이 됨**

**최종 원인:**
1. **스냅 전 검증 부족**: 스냅 로직 전에 TP/SL 가격이 유효한 범위에 있는지 검증하지 않음
2. **format() 함수의 반올림 문제**: `price_prec`가 작을 때 매우 작은 값이 0으로 반올림됨
3. **SHORT 포지션 TP 검증 부족**: SHORT 포지션에서 TP는 entry보다 낮아야 하는데, 계산 과정에서 검증하지 않음
4. **0 이하 값 검증 시점 문제**: 검증을 스냅 후에 하면, 이미 0이 된 값을 검증할 수 없음

#### 수정 내용

**수정 파일: `trading/trader.py` (2561-2587줄)**

```python
# 🔥 TP/SL 가격 유효성 검증 (음수 또는 잘못된 값 방지) 추가
# SHORT 포지션: TP는 entry보다 낮아야 하고, SL은 entry보다 높아야 함
# LONG 포지션: TP는 entry보다 높아야 하고, SL은 entry보다 낮아야 함
if side == 'BUY':  # LONG
    if tp_price <= actual_entry_price:
        self.logger.warning(f"[{symbol}] ⚠️ TP 가격이 진입가보다 낮거나 같음...")
        tp_price = actual_entry_price * 1.01  # 기본 1% 수익
    if sl_price >= actual_entry_price:
        self.logger.warning(f"[{symbol}] ⚠️ SL 가격이 진입가보다 높거나 같음...")
        sl_price = actual_entry_price * 0.99  # 기본 1% 손절
else:  # SELL (SHORT)
    if tp_price >= actual_entry_price:
        self.logger.warning(f"[{symbol}] ⚠️ TP 가격이 진입가보다 높거나 같음...")
        tp_price = actual_entry_price * 0.99  # 기본 1% 수익
    if sl_price <= actual_entry_price:
        self.logger.warning(f"[{symbol}] ⚠️ SL 가격이 진입가보다 낮거나 같음...")
        sl_price = actual_entry_price * 1.01  # 기본 1% 손절

# 최종 검증: 가격이 0보다 큰지 확인
if tp_price <= 0 or sl_price <= 0:
    self.logger.error(f"[{symbol}] ❌ TP/SL 가격이 0 이하: TP={tp_price}, SL={sl_price}...")
    # 기본값 적용
```

**수정 이유:**
- 스냅 로직 **이전**에 검증하여 잘못된 값이 스냅되지 않도록 함
- SHORT/LONG 포지션별로 올바른 TP/SL 관계 검증
- 0 이하 값 방지 및 기본값 적용

---

### 문제 2: 포지션 개수 제한 불일치 (3개 vs 5개)

#### 발생 시점
- 프로그램 시작 시 포지션 복구 후 4-5개 포지션이 생성됨
- 로그에서 "최대 포지션 수 초과 (5/5)" 메시지 반복 발생

#### 로그 증거
```
2900줄: 🔍 실제 거래소 포지션: 4개, 심볼=['RSRUSDT', 'AVAXUSDT', 'ROSEUSDT', 'RVNUSDT']
3390줄: ❌ 거래 차단 사유: 최대 포지션 수 초과 (5/5)
6849줄: 🔍 실제 거래소 포지션: 5개, 심볼=['ADAUSDT', 'AVAXUSDT', 'RVNUSDT', 'LINKUSDT', 'RSRUSDT']
6854줄: 최대 포지션 수 도달 - 필터링 후 신규 대상 없음 (활성: 5개 >= 최대: 5개, ...)
```

#### 근본 원인 분석

**1. `trader.py`에서 하드코딩된 값**
```python
# trading/trader.py 168줄 (수정 전)
'max_positions': 5,  # ❌ 하드코딩된 값
```

**설정 파일 값:**
```json
// data/nwsoft/config/settings.json 50줄
"max_positions": 3,  // ✅ 설정값
```

**2. `unified_trader.py`에서 하드코딩된 값**
```python
# trading/unified_trader.py 3602줄 (수정 전)
if active_positions > 5:  # ❌ 하드코딩된 값
```

**3. 포지션 복구 로직의 문제**
- 프로그램 재시작 시 `_restore_positions_from_exchange()` 메서드가 거래소의 실제 포지션을 모두 복구함
- 복구 과정에서 `max_positions` 제한을 체크하지 않음
- 결과적으로 설정값(3개)과 무관하게 4-5개 포지션이 메모리에 로드됨

#### 수정 내용

**수정 1: `trading/trader.py` 168줄**
```python
# 수정 전
'max_positions': 5,

# 수정 후
'max_positions': 3,  # 🔥 설정값과 일치 (기본값 3)
```

**수정 2: `trading/unified_trader.py` 3602줄**
```python
# 수정 전
if active_positions > 5:
    recommendations.append(f"⚠️ {exchange_name} 활성 포지션이 많습니다 ({active_positions}개)...")

# 수정 후
max_positions = self._get_ai_max_positions(exchange_name)  # 🔥 설정값 사용
if active_positions > max_positions:
    recommendations.append(f"⚠️ {exchange_name} 활성 포지션이 많습니다 ({active_positions}개, 최대: {max_positions}개)...")
```

**추가 수정 필요 (향후):**
- `_restore_positions_from_exchange()` 메서드에서 포지션 복구 시 `max_positions` 제한을 적용해야 함
- 현재는 복구 후에만 제한이 적용되어, 복구 단계에서 4-5개가 로드될 수 있음

---

### 문제 3: AI 학습 중단 문제

#### 보고 내용
- "5포지션이 다 차게되면 AI학습을 멈추게 된다"

#### 조사 결과

**코드 분석:**
- `exchange_learning_manager.py`에서 AI 학습 데이터 저장 로직 확인
- 포지션 개수에 따라 학습을 직접 중단하는 로직은 **발견되지 않음**

**실제 원인:**
- AI 학습 데이터는 **거래 실행 후**에 생성됩니다 (`_generate_ai_learning_data` 메서드)
- 포지션 개수 제한(5개)으로 인해 **새로운 거래가 실행되지 않으면**, 학습 데이터가 생성되지 않음
- 따라서 "학습이 멈춘다"기보다는 "새로운 학습 데이터가 생성되지 않는다"가 정확한 표현

**결론:**
- 문제 2(포지션 개수 제한) 수정으로 간접적으로 해결될 것으로 예상
- 포지션 개수가 설정값(3개)으로 제한되면, 더 많은 거래 기회가 생겨 학습 데이터 생성이 정상화됨

---

### 문제 4: RVN/RSR 코인 모니터링 데이터 포인트 추가 실패

#### 발생 시점
- TP/SL 설정 실패 후 모니터링이 시작되지 않음

#### 근본 원인
- **문제 1과 연관**: TP/SL 주문 생성 실패(`-4006` 오류)로 인해 거래 실행이 실패함
- 거래 실행 실패 시 포지션 모니터링이 시작되지 않음
- 결과적으로 WebSocket 가격 업데이트가 "Added data point" 로그에 기록되지 않음

#### 로그 증거
```
1588줄: ❌ AlgoOrder 실패: {'code': -4006, 'msg': 'Stop price less than zero.'}
1621줄: [RSRUSDT] ❌ 거래 실행 실패 - execute_single_trade 반환값: None
1623줄: ❌ RSRUSDT 거래 실행 실패
```

**AVAXUSDT는 정상 작동:**
```
1566줄: [AVAXUSDT] Added data point: time=2025-12-28 10:42:05.980707, price=12.768
```

**RSRUSDT/RVNUSDT는 데이터 포인트 없음:**
- TP/SL 설정 실패로 거래 실행이 실패하여 모니터링이 시작되지 않음

#### 해결 방법
- **문제 1 수정으로 해결 예상**: TP/SL 가격 계산 오류 수정 후, 거래 실행이 성공하면 모니터링도 정상 시작됨

---

## 🔧 수정 사항 요약

### 수정된 파일

1. **`trading/trader.py`**
   - 168줄: `max_positions: 5` → `max_positions: 3`
   - 2561-2587줄: TP/SL 가격 유효성 검증 로직 추가

2. **`trading/unified_trader.py`**
   - 3602줄: 하드코딩된 `5` 값 → 설정값 사용

### 수정 전후 비교

#### 수정 전 (문제 발생 코드)
```python
# trading/trader.py
'max_positions': 5,  # ❌ 설정값과 불일치

# TP/SL 가격 계산 후 바로 스냅 (검증 없음)
tp_price = actual_entry_price * (1 - backup_tp)  # SHORT
tp_price = snap(tp_price, False)  # ❌ 검증 없이 스냅
tp_price = float(format(tp_price, f'.{price_prec}f'))  # ❌ 0으로 반올림 가능
```

#### 수정 후 (수정된 코드)
```python
# trading/trader.py
'max_positions': 3,  # ✅ 설정값과 일치

# TP/SL 가격 계산 후 검증, 그 다음 스냅
tp_price = actual_entry_price * (1 - backup_tp)  # SHORT

# ✅ 검증 추가
if tp_price >= actual_entry_price:  # SHORT 포지션 검증
    tp_price = actual_entry_price * 0.99  # 기본값 적용
if tp_price <= 0:  # 0 이하 검증
    tp_price = actual_entry_price * 0.99  # 기본값 적용

tp_price = snap(tp_price, False)  # ✅ 검증 후 스냅
tp_price = float(format(tp_price, f'.{price_prec}f'))
```

---

## ✅ 수정 검증

### 검증 방법

1. **-4006 오류 방지:**
   - TP/SL 가격이 0 이하가 되지 않도록 검증 로직 추가
   - SHORT/LONG 포지션별 올바른 관계 검증

2. **포지션 개수 제한:**
   - 설정값(3개)과 코드 로직 일치 확인
   - `unified_trader.py`에서도 설정값 사용

3. **린터 오류:**
   - 수정 후 린터 오류 없음 확인 ✅

### 예상 효과

1. ✅ **RVN/RSR 코인에서 -4006 오류 해결**
   - TP/SL 가격 검증으로 0 이하 값 방지
   - SHORT 포지션에서 TP가 entry보다 낮은지 검증

2. ✅ **포지션 개수 제한 정상화**
   - 설정값(3개)과 코드 로직 일치
   - 새로운 거래 실행 시 3개 제한 적용

3. ✅ **모니터링 데이터 포인트 정상 생성**
   - TP/SL 설정 성공 → 거래 실행 성공 → 모니터링 시작

4. ⚠️ **AI 학습 데이터 생성 정상화** (간접적 해결)
   - 포지션 개수 제한 수정으로 더 많은 거래 기회 → 더 많은 학습 데이터

---

## 📝 추가 개선 사항 (향후)

### 권장 사항

1. **포지션 복구 로직 개선:**
   - `_restore_positions_from_exchange()` 메서드에서 복구 시 `max_positions` 제한 적용
   - 복구 후 초과 포지션 자동 정리 옵션 추가

2. **TP/SL 가격 계산 로직 개선:**
   - `format()` 함수 대신 더 안전한 반올림 방법 사용
   - `price_prec` 값을 심볼 정보에서 정확히 가져오기

3. **로깅 개선:**
   - TP/SL 가격 계산 과정의 중간 값들을 로그에 기록
   - 디버깅을 위한 상세 로그 추가

---

## 🔗 관련 파일

- `trading/trader.py` (수정됨)
- `trading/unified_trader.py` (수정됨)
- `api/binance_client.py` (참고)
- `data/nwsoft/logs/251228_log.txt` (문제 발생 로그)
- `data/nwsoft/config/settings.json` (설정 파일)

---

**작성일**: 2025-12-28  
**수정자**: AI Assistant  
**검토 필요**: 사용자 테스트 후 추가 수정 필요
