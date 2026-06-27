# GALA/JASMY TP 미작동 근본 원인 분석 (2026-01-25)

> **목적**: 수정이 아닌 원인 분석. "이전에 완벽하게 수정되었다"고 한 근거, 그리고 실제로 해결되지 않은 이유를 로그·스크린샷·코드 기반으로 규명.

---

## 1. 요약

| 항목 | 내용 |
|------|------|
| **증상** | GALA, JASMY 등 저가 알트에서 TP 주문이 반복적으로 실패하고, SL만 설정되거나 TP=-- 로 표시됨 |
| **로그 오류** | `APIError(code=-2021): Order would immediately trigger.` (TP 주문에서 다수, SL에서도 일부) |
| **입력 값** | `place_tp_sl_orders()` 호출 시 **TP=0.01, SL=0.01**로 **동일 값**이 반복 전달됨 |
| **근본 원인** | (1) **trader 쪽 TP/SL 가격 계산**에서 `price_precision=2`로 포맷하여 0.006xx 대가 **0.01로 찌그러짐** (2) **binance_client 쪽**에서는 **TP 방향 검증(SHORT일 때 TP < 현재가)** 이 없어, 잘못된 0.01이 그대로 API로 전달됨 (3) **get_symbol_info_direct**와 **trader** 간 **키 이름 불일치**(`price_precision` vs `pricePrecision`)로 `price_prec`가 항상 2로 고정됨 |

---

## 2. 로그·스크린샷 정리

### 2.1. 260120 로그 – GALAUSDT SHORT

**place_tp_sl_orders 호출**

```
[GALAUSDT] 🔍 place_tp_sl_orders() 호출됨 - TP=0.01, SL=0.01, position_side=SHORT
[GALAUSDT] 🔧 tickSize 적용: TP 0.01 → 0.01, SL 0.01 → 0.01 (tickSize=1e-05)
```

**포지션 정보 (진입 직후)**

- `entryPrice`: **0.0067**
- `markPrice`: **0.00670500**

**TP 실패, SL만 성공**

```
[GALAUSDT] ⚠️ SL만 설정됨: SL=0.010000, TP 실패
[GALAUSDT]   - TP 오류: APIError(code=-2021): Order would immediately trigger.
```

**재시도 3회 모두 동일**: `TP=0.01, SL=0.01` 재전달 → TP만 -2021, SL만 설정.

**정리**

- `place_tp_sl_orders`에는 **TP=0.01, SL=0.01**이 들어옴.
- 진입가·현재가 ~0.0067인데 TP/SL이 모두 0.01로 **같고**, **현재가보다 위**에 있음.

### 2.2. 바이낸스 스크린샷과의 대응

- **데스크톱**: GALAUSDT SHORT – TP=`--`, SL=0.01000  
  → TP는 아예 설정되지 않았고, SL만 0.01로 존재.
- **모바일**: GALAUSDT – TP=0.01000, SL=0.00670, Entry=0.00672  
  - 이 설정은 **다른 진입·다른 시점**이거나, SL/TP 라벨이 뒤바뀌어 보이는 경우일 수 있음.
  - 공통: TP=0.01이 **진입가 0.0067x 대비 크게 위**에 있다는 점.

### 2.3. JASMY

- **260120 로그**: JASMYUSDT 검색 결과 없음 (해당일 선택 코인에 없었을 가능성).
- **이전(260118) 분석**:  
  - JASMYUSDT LONG: `TP=0.01, SL=0.01`, 진입가 ~0.008154 → **SL**에서 -2021.  
  - GALAUSDT SHORT: `TP=0.01, SL=0.01` → **TP**에서 -2021.

→ GALA/JASMY 공통: **TP/SL이 0.01로 동일하게** 들어가고, **저가(0.006~0.008)**와 겹쳐 `-2021`이 TP 또는 SL 쪽에서 발생.

---

## 3. 코드 흐름과 “0.01”이 나오는 지점

### 3.1. TP/SL 가격을 만드는 쪽: `trading/trader.py` – `execute_single_trade`

**대략 흐름**

1. `backup_tp`, `backup_sl` (비율) 계산  
   - 예: `backup_tp ≈ 0.02`, `backup_sl ≈ 0.02` (설정·변동성에 따라 달라짐).
2. **절대 가격**  
   - SHORT:  
     - `tp_price = actual_entry_price * (1 - backup_tp)` → 예: 0.0067×0.98 ≈ **0.00657**  
     - `sl_price = actual_entry_price * (1 + backup_sl)` → 예: 0.0067×1.02 ≈ **0.00683**
3. `get_symbol_info_direct(symbol)` → `info`
4. **여기서 정밀도/틱 사용**  
   - `price_prec = info.get('price_precision', 2)`  
   - `tick_size = float(info.get('tick_size', 10 ** (-int(price_prec))))`
5. `snap()` 후  
   - `tp_price = float(format(tp_price, f'.{price_prec}f'))`  
   - `sl_price = float(format(sl_price, f'.{price_prec}f'))`
6. **예외 시**  
   - `tp_price = round(tp_price, 2)`, `sl_price = round(sl_price, 2)`

**실제로 쓰이는 `info` 키**

- `get_symbol_info_direct()` 반환:  
  - `pricePrecision`, `tickSize` (camelCase)  
  - `price_precision`, `tick_size` (snake_case) 는 **없음**.

그래서:

- `info.get('price_precision', 2)` → 키 없음 → **항상 2**.
- `info.get('tick_size', ...)` → 키 없음 → `10**(-2)=0.01` 등으로 폴백.

**`price_prec=2`일 때**

- `format(0.00657, '.2f')` → `'0.01'`
- `format(0.00683, '.2f')` → `'0.01'`

→ **tp_price, sl_price 둘 다 0.01**이 됨.  
예외 블록의 `round(., 2)`도 동일 효과.

**정리: 0.01이 나오는 직접적 원인**

- `get_symbol_info_direct`는 `pricePrecision`, `tickSize`를 주는데,
- `trader`는 `price_precision`, `tick_size`를 찾고, 없으면 **기본 2·0.01** 사용.
- 그 결과 `format(., '.2f')` / `round(., 2)`에 의해 **0.006xx 대 → 0.01**로 묶임.
- GALA, JASMY처럼 **0.001~0.01 구간**인 코인이 특히 0.01로 몰림.

---

## 4. `-2021`이 TP에서 나는 이유 (SHORT 기준)

### 4.1. Binance TAKE_PROFIT_MARKET (SHORT)

- SHORT 청산 = 매수.  
- **가격이 stopPrice 이하로 내려갔을 때** 매수 발동.
- 즉, **stopPrice < 현재가** 여야 “앞으로 가격이 내려가면” 트리거.

### 4.2. 우리가 보낸 값

- `TP=0.01`, 현재가 ≒ **0.0067**.
- 0.01 > 0.0067 ⇒ **TP(stopPrice)가 현재가보다 위**.
- 조건: “가격이 0.01 **이하**로 내려갈 때”  
  - 현재 0.0067이 이미 0.01 이하 ⇒ **이미 조건 충족** → “Order would immediately trigger” → **-2021**.

반대로:

- **SL=0.01 (STOP_MARKET, SHORT)**  
  - “가격이 0.01 **이상**으로 올라갈 때” 매수 청산.  
  - 0.0067 < 0.01 ⇒ 아직 조건 불충족 → **즉시 트리거 아님** → 주문 수락.
- 그래서 **TP만 -2021, SL만 성공**하는 패턴이 반복됨.

---

## 5. `binance_client.place_tp_sl_orders`의 한계 (이전 수정이 “완전”하지 못한 이유)

### 5.1. 이전에 넣은 수정 (요지)

- **TP**: 현재가와의 **거리**만 검사 (예: `tp_distance_pct < min_distance`일 때 조정).
- **SL**:  
  - **방향** (LONG: SL < 현재가, SHORT: SL > 현재가)  
  - **거리** (너무 가까우면 조정)  
  → `CODE_CHANGE_LOG` 기준으로 SL 검증이 추가됨.

### 5.2. 이번에 드러난 공백

1. **TP에 대한 “방향” 검증이 없음**  
   - SHORT: TP는 **현재가보다 낮아야** 함.  
   - `tp_price=0.01`, `current=0.0067`이면 0.01 > 0.0067인데,  
     `tp_distance_pct`는 크므로 “거리 부족” 분기로 안 들어가고, **조정 없이 0.01이 그대로** API로 감.
2. **입력 자체가 이미 잘못됨**  
   - `place_tp_sl_orders`에는 **tp=0.01, sl=0.01**이 들어옴.  
   - 이 값은 **trader**에서 `price_precision=2`·`format(., '.2f')` 때문에 만들어진 것이고,  
     `binance_client`는 “들어온 숫자를 tickSize 등으로만 다듬는” 역할만 함.  
   - **TP/SL이 서로 같고, SHORT인데 TP가 현재가보다 위**인 **구성**을 **걸러주는** 로직은 없었음.

그래서:

- SL 검증 추가로 **SL 쪽 -2021**은 많이 막았을 수 있지만,
- **TP 방향 오류**(SHORT인데 TP > 현재가)와  
- **트레이더 쪽에서 0.01로 찌그러뜨리는 문제**는 그대로여서,  
  GALA SHORT처럼 **TP -2021**이 반복됨.

---

## 6. “TP/SL 주문이 실제로 생성되지 않음” 경고

- **위치**: `trading/trader.py` 등, `place_tp_sl_orders` 이후 검증 로직.
- **의미**: “일반 주문 0개, Algo Order 0개”처럼 보일 때 이 경고 출력.
- **GALA와의 관계**  
  - GALA는 **TP가 -2021로 실패**하고, **SL만 Algo로 생성**됨.  
  - “TP/SL 주문이 실제로 생성되지 않음”은 **TP+SL이 둘 다 정상일 때의 검증**이 실패해 나오는 메시지이고,  
  - GALA처럼 **TP는 애초에 실패**한 경우와는 **다른 레이어**의 문제.  
- DOTUSDT 등: TP/SL **둘 다 성공**한 뒤, Algo Order **조회/매칭 방식**이나 **타이밍** 차이로 “실제로 생성되지 않음”이 나올 수 있음. (이번 분석의 핵심 대상은 GALA/JASMY TP -2021이므로, 여기서는 부수 이슈로만 언급.)

---

## 7. 이전 “수정 완료” 인식이 잘못된 이유

1. **대상이 SL 위주였다**  
   - SL 쪽 -2021·즉시 트리거 방지를 위한 **검증·조정**이 추가됨.  
   - TP는 **거리**만 다루고, **방향(위/아래)** 은 다루지 않음.

2. **호출 전 단계(트레이더)를 다루지 않음**  
   - `place_tp_sl_orders` **입력**이 이미 `TP=0.01, SL=0.01`인 상태.  
   - `get_symbol_info_direct`와의 **키 불일치**(`price_precision` vs `pricePrecision`)로  
     `price_prec=2` 고정 → `format(., '.2f')` → 0.01로 찌그러지는 **근본 원인**은 **trader**에 있음.  
   - 이 경로를 고치지 않으면, `binance_client`만 다듬어도 **잘못된 0.01**이 계속 들어옴.

3. **TP에 대한 “방향” 검증 부재**  
   - SHORT: TP < 현재가 여야 하는데,  
     `tp_price > current`인 경우(0.01 > 0.0067)를 **걸러서 조정**하는 로직이 없음.  
   - “거리만 충분하면 통과”라서, 0.01이 그대로 API로 전달되어 -2021.

4. **검증·테스트 범위**  
   - 주로 **SL**·중가격대 위주로 검증했을 가능성.  
   - **진입가 0.006~0.01 구간 + SHORT + TP** 조합( GALA, JASMY)에서  
     `price_prec=2` 포맷 → 0.01 동일화 → TP -2021 시나리오가 누적 재현된 것으로 보임.

---

## 8. JASMY가 260120에 없는 이유

- 260120 로그에서 `JASMY`, `JASMYUSDT` 검색 결과 없음.  
- 해당일 **선택 코인**에 JASMY가 없었을 가능성이 큼.  
- 260118 분석 문서·이전 대화 기준으로 JASMY도 **TP/SL=0.01**·저가·LONG에서 **SL -2021** 등  
  **동일 메커니즘**(포맷·정밀도·방향 검증 누락)이 적용됐을 것으로 추정.

---

## 9. 수정이 아닌 “원인 정리” 결론

| 구분 | 내용 |
|------|------|
| **1) TP/SL이 0.01로 동일해지는 이유** | `trader.execute_single_trade`에서 `get_symbol_info_direct` 결과를 `price_precision`, `tick_size`로 참조하는데, 실제 키는 `pricePrecision`, `tickSize`. 폴백으로 `price_prec=2` 고정 → `format(., '.2f')` / `round(., 2)`에 의해 0.006xx 대가 0.01로 round됨. |
| **2) GALA SHORT에서 TP만 -2021, SL만 성공하는 이유** | TP=0.01이 SHORT 기준 “가격이 0.01 이하로 내려갈 때” 트리거인데, 현재가 0.0067이 이미 0.01 이하라 **즉시 트리거**로 간주되어 -2021. SL=0.01은 “가격이 0.01 이상일 때”라 아직 미충족 → 수락. |
| **3) 이전 수정이 “완전”하지 않았던 이유** | SL 위주 검증·조정 추가. TP는 거리만 보고 **방향(TP < 현재가 for SHORT)** 검증 없음. 또한 **trader 쪽 `price_precision`/`tick_size` 키 불일치**와 `format(., '.2f')`로 인한 0.01 왜곡을 다루지 않음. |
| **4) JASMY** | 260120에는 선택되지 않았을 가능성. 260118 등 이전: LONG + TP/SL=0.01에서 SL -2021 등, GALA와 **같은 포맷·정밀도·방향 문제**로 해석 가능. |

---

## 10. (참고) 추후 수정 시 다룰 포인트

- **trader**  
  - `get_symbol_info_direct` 결과 사용 시  
    - `pricePrecision` → `price_prec`,  
    - `tickSize` → `tick_size`  
    같이 **실제 반환 키**에 맞게 매핑.  
  - `price_prec`가 2로만 쓰이지 않도록, **저가 코인**은 `pricePrecision`이 4–5 이상이면 그대로 사용.  
  - `format(., f'.{price_prec}f')` / `round(., 2)`가 0.00x 대를 0.01로 묶지 않도록, **진입가 대비 최소 소수 자리** 또는 **tickSize** 기반 포맷 고려.
- **binance_client.place_tp_sl_orders**  
  - SHORT: `tp_price > current_price`이면 “즉시 트리거”로 간주하고,  
    `tp_price`를 `current * (1 - min_distance)` 쪽으로 **재계산/조정**해 API에 넘기는 **TP 방향 검증** 추가.

이 문서는 **원인 분석**만 하며, 실제 코드 수정은 별도 작업으로 진행하는 것이 좋습니다.
