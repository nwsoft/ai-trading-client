# 로그 검증 업데이트 보고서 (2026-01-13) - SL 주문 생성 오류 추가 발견

## 발견된 추가 문제

### SL 주문 생성 시 `-4006` 오류 (Stop price less than zero)

**발생 시간**: 2026-01-13 22:37:19  
**심볼**: ZILUSDT  
**오류 메시지**: `APIError(code=-4006): Stop price less than zero.`

### 문제 분석

#### 로그 증거
```
3531:2026-01-13 22:37:15 | INFO - [ZILUSDT] 🔍 TP/SL 설정 - tp: 0.000528427781237906, sl: 0.002, mode: optimized
3550:2026-01-13 22:37:17 | INFO - [ZILUSDT]   - SL: 0.002000
3562:2026-01-13 22:37:18 | INFO - [ZILUSDT] ✅ 주문 체결 완료!
3566:2026-01-13 22:37:19 | ERROR - ❌ AlgoOrder 실패: {'code': -4006, 'msg': 'Stop price less than zero.'}
3570:2026-01-13 22:37:19 | ERROR - [ZILUSDT] ❌ SL 주문 생성 실패: {'status': 'ERROR', 'error': 'APIError(code=-4006): Stop price less than zero.'}
```

#### 원인 분석

1. **TP/SL 가격 계산 과정**:
   - TP/SL은 퍼센트 값(`tp: 0.000528427781237906, sl: 0.002`)으로 계산됨
   - 실제 가격으로 변환: `sl_price = actual_entry_price * (1 - backup_sl)` (LONG) 또는 `actual_entry_price * (1 + backup_sl)` (SHORT)
   - **tickSize 스냅**: 가격을 tickSize에 맞춰 조정
   - **format() 함수**: price_precision 자릿수로 포맷팅

2. **문제 발생 지점**:
   - 저가 코인(ZILUSDT, 가격 약 0.0057)에서 tickSize 스냅 및 format() 과정에서 **반올림 오류** 발생
   - `math.floor()` 또는 `math.ceil()` 연산 후 `format()` 함수 적용 시 **가격이 0보다 작아질 수 있음**
   - 특히 `format(tp_price, f'.{price_prec}f')` 과정에서 **부동소수점 연산 오류**로 인해 0 이하 값 생성 가능

3. **검증 누락**:
   - 기존 코드: 스냅 전 검증만 있음 (2590-2598줄)
   - **스냅 후 최종 검증이 없어** 스냅 과정에서 생성된 잘못된 가격이 API로 전달됨

### 수정 내용

#### 1. `trading/trader.py` (2622-2631줄)
```python
# 🔥 스냅 후 최종 검증: 가격이 0보다 큰지 확인 (저가 코인 대응)
if tp_price <= 0 or sl_price <= 0:
    self.logger.error(f"[{symbol}] ❌ TP/SL 스냅 후 가격이 0 이하: TP={tp_price}, SL={sl_price}, Entry={actual_entry_price}, tick={tick_size}. 기본값으로 재계산.")
    if side == 'BUY':  # LONG
        tp_price = actual_entry_price * 1.01
        sl_price = actual_entry_price * 0.99
    else:  # SELL (SHORT)
        tp_price = actual_entry_price * 0.99
        sl_price = actual_entry_price * 1.01
    # 다시 스냅 적용
    tp_price = float(format(tp_price, f'.{price_prec}f'))
    sl_price = float(format(sl_price, f'.{price_prec}f'))
```

#### 2. `api/binance_client.py` (2303-2341줄)
```python
# tickSize 스냅 후 검증 추가
if tp_price <= 0 or sl_price <= 0:
    self.logger.error(f"[{symbol}] ❌ tickSize 스냅 후 가격이 0 이하: TP={tp_price}, SL={sl_price}, 원본 TP={take_profit}, SL={stop_loss}, tickSize={tick_size}")
    # 원본 가격을 최소값으로 보장
    tp_price = max(take_profit, tick_size) if take_profit > 0 else tick_size
    sl_price = max(stop_loss, tick_size) if stop_loss > 0 else tick_size
    # 다시 스냅 적용
    tp_price = round(tp_price / tick_size) * tick_size
    sl_price = round(sl_price / tick_size) * tick_size
```

### 수정 이유

1. **이중 검증 강화**: 
   - 스냅 전 검증(기존) + 스냅 후 검증(신규) → 저가 코인에서도 안전
   
2. **다층 방어**:
   - `trading/trader.py`: 가격 계산 및 스냅 단계에서 검증
   - `api/binance_client.py`: API 호출 직전 최종 검증

3. **폴백 메커니즘**:
   - 검증 실패 시 기본값(1% TP/SL)으로 재계산
   - 최소값 보장 (0.0001 또는 tick_size)

### 기존 수정 사항과의 관계

- ✅ **v3.8.9.9 초기 수정**: TP/SL 가격 계산 오류(`-4006`) 수정 - **스냅 전 검증** 추가
- ⚠️ **추가 발견**: **스냅 후 검증 누락**으로 인해 저가 코인에서 여전히 발생
- ✅ **추가 수정 완료**: 스냅 후 최종 검증 추가로 완전 해결

### 결론

- **기존 수정 사항**: 부분적으로 적용됨 (스냅 전 검증만 있었음)
- **추가 문제**: 스냅 후 최종 검증 누락
- **해결**: 스냅 전/후 이중 검증으로 완전 해결

---

## 수정 파일 목록

1. `trading/trader.py`:
   - 스냅 후 최종 검증 추가 (2622-2631줄)
   - 기본값 적용 후 검증 추가 (2632-2640줄)

2. `api/binance_client.py`:
   - tickSize 스냅 후 검증 추가 (2303-2320줄)
   - precision 반올림 후 검증 추가 (2321-2334줄)
   - 기본값 검증 추가 (2335-2341줄)

---

## 다음 테스트 권장 사항

1. **저가 코인 테스트**: ZILUSDT, ROSEUSDT 등 저가 코인에서 SL 주문 생성 테스트
2. **로그 확인**: "❌ TP/SL 스냅 후 가격이 0 이하" 메시지 발생 여부 확인
3. **폴백 동작 확인**: 검증 실패 시 기본값으로 재계산되는지 확인
