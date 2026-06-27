# 🚨 TP/SL 주문 시스템 가이드라인 (2025-12-27 최종 업데이트)

## ⚠️ **중요: 이 가이드라인을 위반하면 TP/SL이 완전히 작동하지 않습니다**

## 🔥 **Binance 정책 변경 (2025-12-09) - 필수 확인**

**조건부 주문은 이제 Algo Order API를 사용해야 합니다:**
- **영향 주문 타입**: `STOP_MARKET`, `TAKE_PROFIT_MARKET`, `STOP`, `TAKE_PROFIT`, `TRAILING_STOP_MARKET`
- **엔드포인트**: `/fapi/v1/algoOrder` (자동 라우팅됨)
- **구현 위치**: `api/binance_client.py`의 `place_futures_order()` 메서드
- **사용 방법**: `place_tp_sl_orders()` 또는 `place_futures_order()` 사용 (자동으로 Algo Order로 라우팅)

**자세한 내용**: `docs/BINANCE_ALGO_ORDER_IMPLEMENTATION_2025-12-27.md` 참조

### 📋 **바이낸스 API 규칙 (절대 위반 금지)**

#### **1. TP/SL 주문 생성 규칙**

**✅ 올바른 방식 (현재 구현 - 2025-12-27)**
```python
# BinanceClient.place_tp_sl_orders() 사용 (권장)
tp_order_result, sl_order_result = self.binance_client.place_tp_sl_orders(
    symbol=symbol,
    position_side='LONG',  # 또는 'SHORT'
    take_profit=tp_price,
    stop_loss=sl_price,
    quantity=None,  # closePosition=True이므로 수량 불필요
    price_precision=price_precision
)

# 또는 place_futures_order() 직접 사용 (조건부 주문은 자동으로 Algo Order로 라우팅됨)
result = self.binance_client.place_futures_order(
    symbol=symbol,
    side='SELL',  # LONG 포지션 종료용
    order_type='TAKE_PROFIT_MARKET',
    stop_price=tp_price,
    close_position=True,
    working_type='MARK_PRICE'
)
```

**핵심 규칙**:
1. **Algo Order API 자동 라우팅**: 조건부 주문 타입은 자동으로 `/fapi/v1/algoOrder`로 라우팅됨
2. **closePosition=True 사용**: 전량 청산, 수량 문제 방지
3. **quantity 파라미터 제거**: closePosition=True일 때 quantity 전송 금지
4. **reduceOnly와 closePosition 동시 사용 금지**: API 오류 `-1106` 발생
5. **가격 정밀도**: `tickSize` 우선 적용, 없으면 `pricePrecision` 사용
6. **파라미터 변환**: `stopPrice` → `triggerPrice` (Algo Order API 규칙)

#### **2. TP/SL 주문 검증 규칙**
```python
# ✅ 올바른 방식 (현재 구현)
# 필수 옵션 검증 (reduceOnly 조건 제거 - closePosition 사용 시 불필요)
tp_valid = (
    tp_order.get('workingType') == 'MARK_PRICE' and
    tp_order.get('status') == 'NEW'
)
sl_valid = (
    sl_order.get('workingType') == 'MARK_PRICE' and
    sl_order.get('status') == 'NEW'
)
```

### 🚫 **절대 하지 말아야 할 것들**

#### **1. TP/SL 생성에서 금지사항**
```python
# ❌ 절대 하지 말 것 - API 오류 -1106 발생
base = dict(reduceOnly=True, closePosition=True)  # 둘 다 사용 금지!

# ❌ 절대 하지 말 것 - 수량과 closePosition 동시 사용 금지
base = dict(closePosition=True, quantity=1.0)  # 양립 불가!

# ❌ 절대 하지 말 것 - reduceOnly만 사용 (closePosition이 더 안전)
base = dict(reduceOnly=True, workingType=working_type)  # 권장하지 않음
```

#### **2. TP/SL 검증에서 금지사항**
```python
# ❌ 절대 하지 말 것 - 무한 루프 원인
tp_valid = (
    tp_order.get('reduceOnly') == True and  # ← 이 조건이 문제!
    tp_order.get('workingType') == 'MARK_PRICE' and
    tp_order.get('status') == 'NEW'
)
```

#### **3. 수량 계산에서 금지사항**
```python
# ❌ 절대 하지 말 것 - 수량 계산 중복 (일관성 저하)
# should_execute_trade에서 이미 calculate_precise_quantity로 정확한 수량 계산 완료
# execute_single_trade에서 또 다시 계산하면 안됨!

# ❌ 잘못된 예시
def execute_single_trade(self, trade_params):
    quantity = trade_params['qty']  # 이미 정확한 수량
    # ... 중간 로직 ...
    if final_amount < min_notional:
        # ❌ 또 다시 수량 계산 - 중복!
        need_qty = math.ceil((min_notional / ref_price) / step_size) * step_size
        quantity = float(format(need_qty, f".{quantity_precision}f"))

# ✅ 올바른 예시
def execute_single_trade(self, trade_params):
    quantity = trade_params['qty']  # 이미 정확한 수량
    # ... 중간 로직 ...
    if final_amount < min_notional:
        # ✅ 최종 검증만 수행 (재계산 금지)
        self.logger.error(f"수량 계산 오류: {final_amount:.2f} USDT < {min_notional} USDT")
        return False
```

### 🔄 **올바른 사용 패턴**

#### **1. TP/SL 주문 (closePosition 방식)**
- **사용**: `closePosition=True`
- **제거**: `reduceOnly`, `quantity`
- **포지션 모드**: `positionSide` (헤지 모드일 때만)

#### **2. 일반 청산 주문 (reduceOnly 방식)**
- **사용**: `reduceOnly=True`, `quantity=position.quantity`
- **제거**: `closePosition`
- **용도**: 수동 청산, 강제 청산

#### **3. 수량 계산 단일화 패턴**
```python
# ✅ 올바른 수량 계산 흐름
def should_execute_trade(self, trade_params):
    # 1단계: 기본 수량 설정
    qty = trade_params.get('qty', 0.01)
    price = self.binance_client.get_current_price(symbol)
    
    # 2단계: 정확한 수량 계산 (단일 진실의 원천)
    if hasattr(self.binance_client, 'calculate_precise_quantity'):
        target_value = qty * price
        precise_qty = self.binance_client.calculate_precise_quantity(symbol, target_value)
        if precise_qty and precise_qty > 0:
            qty = precise_qty
            trade_params['qty'] = precise_qty
    
    return True

def execute_single_trade(self, trade_params):
    # 3단계: 이미 계산된 수량 사용 (재계산 금지)
    quantity = trade_params['qty']  # should_execute_trade에서 계산된 정확한 수량
    
    # 4단계: 최종 검증만 수행
    final_amount = quantity * ref_price
    if final_amount < min_notional:
        self.logger.error(f"수량 계산 오류: {final_amount:.2f} USDT < {min_notional} USDT")
        return False
    
    # 5단계: 주문 실행
    order_result = self.binance_client.place_futures_order(...)
```

### 📍 **수정된 파일 위치**

#### **1. TP/SL 주문 생성 로직**
- **파일**: `api/binance_client.py`
- **메서드**: `place_tp_sl_orders` (라인 2026-2041)
- **상태**: ✅ 수정 완료 (reduceOnly 제거, closePosition=True 사용)

#### **2. WebSocket 보장 로직**
- **파일**: `api/binance_client.py`
- **메서드**: `ensure_ws_for` (라인 1358-1368)
- **상태**: ✅ 추가 완료

#### **3. 수량 계산 단일화**
- **파일**: `trading/trader.py`
- **메서드**: `should_execute_trade` (라인 1606-1621)
- **상태**: ✅ 수정 완료 (calculate_precise_quantity 사용)

#### **4. 모니터링 루프 안정화**
- **파일**: `trading/trader.py`
- **메서드**: `start_realtime_monitoring` (라인 3346-3361)
- **상태**: ✅ 수정 완료 (WS 실패 시 REST 폴백 강화)

#### **5. 청산 로직 (정상 유지)**
- **파일**: `trading/trader.py`
- **메서드**: `close_position` (라인 3691, 3699)
- **상태**: ✅ 정상 (reduceOnly 사용 - 올바름)

#### **6. 수량 계산 중복 제거**
- **파일**: `trading/trader.py`
- **메서드**: `execute_single_trade` (라인 1873-1884)
- **상태**: ✅ 수정 완료 (중복 계산 제거, 최종 검증만 수행)

### 🧪 **테스트 시나리오**

#### **정상 동작 확인사항**
1. TP/SL 주문 생성 시 `APIError(code=-1106)` 발생하지 않음
2. 워치독이 무한 루프에 빠지지 않음
3. TP/SL 주문이 정상적으로 생성됨
4. 검증 단계에서 통과함

#### **로그 확인사항**
```
✅ TP/SL 완벽 설정 완료 - 검증 통과 (TP:xxx, SL:xxx)
```
이 로그가 나타나면 정상 작동

### 🚨 **경고사항**

1. **절대 `reduceOnly=True`와 `closePosition=True`를 동시에 사용하지 마세요**
2. **절대 검증 로직에서 `reduceOnly==True` 조건을 추가하지 마세요**
3. **절대 수량 계산을 여러 곳에서 중복으로 수행하지 마세요**
4. **TP/SL 수정 시 반드시 이 가이드라인을 참조하세요**
5. **수정 후 반드시 테스트하여 `-1106` 오류가 발생하지 않는지 확인하세요**
6. **수량 계산은 `should_execute_trade`에서 한 번만 수행하고, 이후 경로에서는 재계산 금지**

### 📚 **참고 자료**

- **바이낸스 API 문서**: USDT-M 선물 주문 파라미터
- **오류 코드 -1106**: "Parameter 'reduceonly' sent when not required"
- **수정 이력**: `docs/CODE_CHANGE_LOG.md` - 2025-10-24 TP/SL 주문 오류 수정 및 수량 계산 중복 제거

### 🔄 **최근 업데이트**

#### **2025-12-27: Binance Algo Order API 완전 구현**
- **조건부 주문 자동 라우팅**: `place_futures_order()`에서 조건부 주문 타입 감지 후 `/fapi/v1/algoOrder`로 자동 라우팅
- **서명 생성 규칙 준수**: query string 기반, 알파벳 정렬, HMAC SHA256
- **가격 정밀도 개선**: `tickSize` 우선 적용, 부동소수점 오차 제거
- **오류 해결**: `-4120`, `-1022`, `-1111` 오류 완전 해결
- **자세한 내용**: `docs/BINANCE_ALGO_ORDER_IMPLEMENTATION_2025-12-27.md` 참조

#### **2025-01-26: 검증 로직 개선**
- **주문 타입 필터링 통일**: 모든 검증 로직에서 `('TAKE_PROFIT', 'TAKE_PROFIT_MARKET')` 및 `('STOP', 'STOP_MARKET')` 모두 확인
- **검증 대기 시간 개선**: 고정 3초 → 재시도 로직 (2초, 3초, 4초)으로 변경
- **재설정 후 재검증**: 재설정 성공 후 즉시 재검증 추가

#### **원자성 보장 강화**
- **TP/SL 롤백 개선**: TP/SL 중 하나라도 실패 시 둘 다 롤백
- **재설정 원자성**: `_retry_tp_sl_setup()`에서 주문 생성 실패 시 생성된 주문 자동 롤백

#### **Watchdog 시스템 개선**
- **재설정 후 즉시 재검증**: 재설정 후 최대 2회 재검증 (1초, 1.5초 간격)
- **주문 상태 검증 추가**: 개수 확인뿐만 아니라 주문 상태도 검증

---
**이 가이드라인을 위반하면 TP/SL 시스템이 완전히 작동하지 않습니다. 반드시 준수하세요!**
