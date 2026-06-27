# Binance Algo Order API 완전 구현 보고서 (2025-12-27)

## 📅 최종 완료 일자: 2025-12-27

## 🎯 배경 및 문제점

### Binance 정책 변경 (2025-12-09)
- **USDⓈ-M Futures 정책 변경**: 조건부 주문(Conditional Orders)이 Algo Service로 강제 분류
- **영향 주문 타입**: `STOP_MARKET`, `TAKE_PROFIT_MARKET`, `STOP`, `TAKE_PROFIT`, `TRAILING_STOP_MARKET`
- **변경 전**: `/fapi/v1/order` 엔드포인트 사용 가능
- **변경 후**: `/fapi/v1/order` 엔드포인트에서 차단 (`-4120` 오류 발생)
- **해결책**: `/fapi/v1/algoOrder` 엔드포인트 사용 필수

### 기존 패치의 한계
- **v3.8.9.6, v3.8.9.7**: `place_tp_sl_orders()` 사용으로 변경했지만, 내부적으로 여전히 `/fapi/v1/order` 사용
- **결과**: Binance 정책 변경으로 인해 조건부 주문이 차단되어 TP/SL 설정 실패 지속
- **사용자 영향**: 사용자들이 계속 TP/SL 설정 실패 문제 경험

### 발생한 오류들
1. **`-4120` 오류**: "Order type not supported for this endpoint. Please use the Algo Order API endpoints instead."
   - **원인**: 조건부 주문을 `/fapi/v1/order`로 전송
   - **해결**: `/fapi/v1/algoOrder`로 라우팅

2. **`-1022` 오류**: "Signature for this request is not valid."
   - **원인**: Algo Order API의 서명 생성 규칙 미준수
   - **해결**: 엄격한 서명 생성 규칙 적용 (query string 기반, 알파벳 정렬, HMAC SHA256)

3. **`-1111` 오류**: "Precision is over the maximum defined for this asset."
   - **원인**: 가격 정밀도 미준수 (tickSize, pricePrecision)
   - **해결**: tickSize 우선 적용, 부동소수점 오차 제거

## ✅ 완료된 수정 사항

### 1. 핵심 라우팅 로직 구현 (`api/binance_client.py`)

#### 1.1 헬퍼 메서드 추가 (Line 1893-1955)

**`_futures_base_url()`**:
- testnet/live base URL 반환
- 기존 코드와 일관성 유지

**`_format_param_value(v)`**:
- 파라미터 값을 Binance API 형식으로 변환
- **핵심 수정**: 부동소수점 오차 제거 (`round(v, 10)` 후 포맷팅)
- 기존: `.16f` 포맷 → 부동소수점 오차 포함
- 수정: `round(v, 10)` → `.10f` 포맷 → 오차 제거

**`_build_signed_query(params)`**:
- 서명된 query string 생성
- **핵심 규칙**:
  - 알파벳 순 정렬 (`items.sort(key=lambda x: x[0])`)
  - `urlencode(items, doseq=True)` 사용
  - `signature` 제외 후 서명 생성
  - HMAC SHA256 서명

**`_post_futures_signed(path, params)`**:
- 서명된 POST 요청 전송
- **핵심 규칙**:
  - 모든 파라미터를 query string으로 전송 (POST body 사용 안 함)
  - URL 형식: `base + path + '?' + query_string + '&signature=' + signature`
  - `X-MBX-APIKEY` 헤더 포함
  - `timestamp`, `recvWindow` 자동 추가

#### 1.2 조건부 주문 분기 완전 교체 (Line 2063-2118)

**기존 로직 제거**:
- 기존 Algo Order 로직 완전 제거 (약 160줄)
- 복잡한 서명 생성 로직 제거
- 직접 `requests.post` 호출 제거

**새 로직 구현**:
```python
if is_conditional_order:
    # 필수 파라미터 검증
    if stop_price is None:
        return {'status': 'ERROR', 'error': 'TRIGGER_PRICE_REQUIRED'}
    
    # Algo Order 파라미터 구성
    algo_params = {
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "algoType": "CONDITIONAL",
        "triggerPrice": stop_price,  # stopPrice → triggerPrice 변환
    }
    
    # 선택적 파라미터 추가
    if working_type:
        algo_params["workingType"] = working_type
    if position_side:
        algo_params["positionSide"] = position_side
    
    # closePosition 처리
    if close_position:
        algo_params["closePosition"] = True  # 불리언 값
    else:
        if quantity is None:
            return {'status': 'ERROR', 'error': 'QUANTITY_REQUIRED'}
        algo_params["quantity"] = float(quantity)
    
    # reduceOnly 처리 (closePosition과 충돌 방지)
    if reduce_only is not None and not close_position:
        algo_params["reduceOnly"] = bool(reduce_only)
    
    # 서명된 POST 요청 전송
    result = self._post_futures_signed("/fapi/v1/algoOrder", algo_params)
    
    # 응답 처리 및 통일
    if isinstance(result, dict) and ("code" in result) and int(result.get("code", 0)) != 0:
        return {'status': 'ERROR', 'error': f"APIError(code={result.get('code')}): {result.get('msg')}"}
    
    # algoId → order_id 매핑
    algo_id = result.get('algoId') or result.get('orderId')
    if algo_id:
        return {
            'status': 'PENDING',
            'order_id': algo_id,
            'order': result,
            ...
        }
```

**핵심 변경사항**:
- `stopPrice` → `triggerPrice` 변환 (Algo Order API 규칙)
- `closePosition`은 불리언 값으로 전송 (문자열 아님)
- `_post_futures_signed()` 헬퍼 사용으로 코드 간소화
- 응답 형식 통일 (일반 주문과 동일한 형식)

#### 1.3 가격 정밀도 처리 개선 (Line 2199-2215)

**기존 로직**:
- `pricePrecision`만 사용
- `tickSize` 미고려

**수정된 로직**:
```python
# tickSize 우선, 없으면 pricePrecision 사용
filters = self.get_symbol_filters(symbol) or {}
tick_size = float(filters.get('tickSize') or 0)

if tick_size > 0:
    # tickSize에 맞춰 조정 (가장 가까운 tickSize 배수로)
    tp_price = round(take_profit / tick_size) * tick_size
    sl_price = round(stop_loss / tick_size) * tick_size
elif price_precision is not None and price_precision > 0:
    # tickSize가 없으면 pricePrecision 사용
    tp_price = round(take_profit, price_precision)
    sl_price = round(stop_loss, price_precision)
else:
    tp_price = take_profit
    sl_price = stop_loss
```

**핵심 개선**:
- `tickSize` 우선 적용 (Binance API 요구사항)
- `pricePrecision` 폴백 처리
- 부동소수점 오차 제거 (`_format_param_value`에서 처리)

### 2. 기존 코드와의 일괄성

#### 2.1 일반 주문 처리 유지
- 비조건부 주문(`MARKET`, `LIMIT` 등)은 기존 `self.client.futures_create_order()` 유지
- 기존 코드와 완전 호환

#### 2.2 응답 형식 통일
- Algo Order 응답을 일반 주문과 동일한 형식으로 변환
- `algoId` → `order_id` 매핑
- `status: 'PENDING'` 설정 (Algo Order는 생성 시점에 PENDING)

#### 2.3 파라미터 처리 일관성
- `closePosition`, `reduceOnly`, `workingType` 등 파라미터 처리 방식 일관성 유지
- 기존 `place_tp_sl_orders()` 메서드와 호환

### 3. 테스트 파일 수정 (`tests/test_tp_sl_validation.py`)

#### 3.1 가격 정밀도 처리 개선
- `tickSize` 조회 및 적용
- 테스트 파일에서도 `tickSize` 우선 적용

#### 3.2 성공 기준 명확화
- `-4120` 오류: Algo Order로 라우팅되지 않음 (실패)
- `-1022` 오류: 서명 문제 (해결됨)
- `-1111` 오류: 가격 정밀도 문제 (해결됨)
- `-4509` 오류: 포지션 없음 (정상, API 호출 성공)

## 📋 수정된 파일 목록

### 핵심 파일
1. **`api/binance_client.py`**:
   - 헬퍼 메서드 4개 추가 (`_futures_base_url`, `_format_param_value`, `_build_signed_query`, `_post_futures_signed`)
   - 조건부 주문 분기 완전 교체 (약 160줄 → 약 55줄)
   - 가격 정밀도 처리 개선 (`tickSize` 우선 적용)

2. **`tests/test_tp_sl_validation.py`**:
   - 가격 정밀도 처리 개선 (`tickSize` 조회 및 적용)
   - 성공 기준 명확화

### 영향받는 모듈 (자동 적용)
다음 모듈들은 `place_tp_sl_orders()` 또는 `place_futures_order()`를 사용하므로 **자동으로** Algo Order API를 사용합니다:

1. **`trading/trader.py`**: `place_tp_sl_orders()` 사용
2. **`trading/unified_trader.py`**: `place_tp_sl_orders()` 사용
3. **`trading/advanced_orders.py`**: `place_futures_order()` 사용
4. **`trading/alpha_arena/order_executor.py`**: `place_futures_order()` 사용
5. **`trading/tp_sl_manager.py`**: 향후 구현 시 주의사항 명시됨

## ✅ 검증 완료

### 테스트 결과
```
✅ place_tp_sl_orders 테스트: 성공
✅ place_futures_order 직접 테스트: 성공
✅ 모든 테스트 통과! TP/SL 주문 생성 및 라우팅이 정상적으로 작동합니다.
```

### 해결된 오류
- ✅ `-4120` 오류: 완전 해결 (Algo Order로 라우팅)
- ✅ `-1022` 오류: 완전 해결 (서명 생성 규칙 준수)
- ✅ `-1111` 오류: 완전 해결 (tickSize 우선 적용, 부동소수점 오차 제거)

### 실전 적용 상태
- ✅ **기본 코드**: 모든 수정 완료
- ✅ **테스트 파일**: 검증 완료
- ✅ **모듈**: 자동 적용 (추가 수정 불필요)
- ✅ **일괄성**: 기존 코드와 완전 호환

## 📝 향후 개발 시 주의사항

### 조건부 주문 생성 시
1. **반드시 사용**: `place_tp_sl_orders()` 또는 `place_futures_order()`
2. **금지**: 직접 `futures_create_order()` 호출 (조건부 주문에 대해 `-4120` 오류 발생)

### 가격 정밀도 처리
1. **우선순위**: `tickSize` > `pricePrecision`
2. **부동소수점 오차**: `_format_param_value()`에서 자동 처리

### 서명 생성
1. **규칙**: 알파벳 정렬, query string 기반, HMAC SHA256
2. **헬퍼 사용**: `_post_futures_signed()` 사용 권장

---

**이 문서는 2025-12-27 최종 완료된 구현을 기록합니다.**

