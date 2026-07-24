# Alpha Arena 프롬프트 분석 및 업데이트 기록 (이력 보관)

**작성일**: 2025-01-XX  
**최종 업데이트**: 2025-01-XX  
**상태**: 분석 완료, 코드 업데이트 완료 ✅

> **[2026-05-07 열람 주의]** 이 문서는 2025-01 시점의 분석 이력 노트입니다.
> 본문의 ❌ / "미구현" 표시는 당시 분석 당시의 미완 항목이며,
> 이후 코드 업데이트로 대부분 반영되었습니다.
> 현재 구현 상태의 기준 문서는 `docs/DEVELOPMENT_STATUS_COMPREHENSIVE_20260427.md` 입니다.

---

## 📋 목차

1. [Reddit 역공학 결과 분석](#1-reddit-역공학-결과-분석)
2. [실제 Alpha Arena 프롬프트 샘플 분석](#2-실제-alpha-arena-프롬프트-샘플-분석)
3. [현재 코드와의 비교](#3-현재-코드와의-비교)
4. [필요한 수정 사항](#4-필요한-수정-사항)
5. [결론](#5-결론)

---

## 1. Reddit 역공학 결과 분석

### 1.1 프롬프트 구조 (역공학 결과)

Reddit 사용자가 Alpha Arena 벤치마크의 실제 프롬프트를 역공학한 결과:

#### Time Frame (Header)
- 현재 시간, 경과 분, 호출 횟수 (`invoke_count`)
- "ALL OF THE PRICE OR SIGNAL DATA BELOW IS ORDERED: OLDEST → NEWEST"
- "Timeframes note: Unless stated otherwise, intraday series are provided at 3-minute intervals."

#### Market State
각 코인별로 다음 데이터 제공:
- **Current indicators**: `current_price`, `current_ema20`, `current_macd`, `current_rsi (7 period)`
- **Open Interest**: Latest, Average
- **Funding Rate**
- **Intraday series (3-minute intervals)**:
  - `Mid prices`: [array]
  - `EMA indicators (20-period)`: [array] ⚠️ **현재 코드 미구현**
  - `MACD indicators`: [array] ⚠️ **현재 코드 미구현**
  - `RSI indicators (7-Period)`: [array] ⚠️ **현재 코드 미구현**
  - `RSI indicators (14-Period)`: [array] ⚠️ **현재 코드 미구현**
- **Longer-term context (4-hour timeframe)**:
  - `20-Period EMA vs 50-Period EMA`
  - `3-Period ATR vs 14-Period ATR`
  - `Current Volume vs Average Volume` ⚠️ **현재 코드 생략**
  - `MACD indicators`: [array] ⚠️ **현재 코드 미구현**
  - `RSI indicators (14-Period)`: [array] ⚠️ **현재 코드 미구현**

#### Current Position
각 포지션별로 다음 필드 제공:
- `symbol`, `quantity`, `entry_price`, `current_price`, `liquidation_price`
- `unrealized_pnl`, `leverage`
- `exit_plan`: `profit_target`, `stop_loss`, `invalidation_condition`
- `confidence`, `risk_usd`
- `sl_oid`, `tp_oid`, `wait_for_fill`, `entry_oid`, `notional_usd`

#### Chain of Thought (분석 단계)
Reddit 역공학 결과에 따르면 LLM이 다음 단계로 분석:
1. **Position Review Phase**: 모든 기존 포지션과 exit plan 확인
2. **Individual Position Analysis**: 각 포지션별 기술적 분석 (RSI, EMA, MACD)
3. **Position Decision Logic**: 무효화 조건 확인, HOLD 기본값
4. **New Entry Evaluation**: 사용 가능한 현금, 피라미딩 금지, 재진입 금지
5. **Output Format Rules**: JSON 형식, 필수 필드 명시
6. **Data Compilation Process**: 기존 값 추출, JSON 포맷팅

---

## 2. 실제 Alpha Arena 프롬프트 샘플 분석

### 2.1 제공된 실제 프롬프트 샘플

사용자가 제공한 실제 Alpha Arena 프롬프트 샘플 (2025-10-23 20:14:54 기준):

#### Header 섹션
```
It has been 1863 minutes since you started trading.
The current time is 2025-10-23 20:14:54.607019 and you've been invoked 1158 times.
Below, we are providing you with a variety of state data, price data, and predictive signals so you can discover alpha.

ALL OF THE PRICE OR SIGNAL DATA BELOW IS ORDERED: OLDEST → NEWEST

Timeframes note: Unless stated otherwise in a section title, intraday series are provided at 3‑minute intervals. If a coin uses a different interval, it is explicitly stated in that coin's section.
```

**차이점**:
- ✅ 현재 코드와 일치
- ✅ "Below, we are providing you with a variety of state data, price data, and predictive signals so you can discover alpha." 문구 포함 (현재 코드에는 없음)

#### Market State 섹션 (BTC 예시)

```
ALL BTC DATA

current_price = 109919.5, current_ema20 = 110276.623, current_macd = -154.217, current_rsi (7 period) = 16.273

In addition, here is the latest BTC open interest and funding rate for perps (the instrument you are trading):

Open Interest: Latest: 24983.73  Average: 24974.91

Funding Rate: 1.25e-05

Intraday series (by minute, oldest → latest):

Mid prices: [110405.0, 110508.5, 110504.0, 110332.5, 110321.0, 110201.5, 109981.5, 110029.0, 110045.0, 109919.5]

EMA indicators (20‑period): [110473.627, 110477.281, 110478.207, 110463.044, 110448.278, 110421.68, 110385.235, 110350.546, 110321.636, 110276.623]

MACD indicators: [-81.016, -69.067, -60.912, -67.231, -72.293, -86.523, -107.056, -123.36, -132.653, -154.217]

RSI indicators (7‑Period): [50.23, 57.765, 54.243, 36.699, 35.814, 26.422, 20.544, 19.831, 24.259, 16.273]

RSI indicators (14‑Period): [42.212, 46.079, 44.89, 37.825, 37.41, 32.548, 28.781, 28.292, 30.136, 24.888]

Longer‑term context (4‑hour timeframe):

20‑Period EMA: 109055.99 vs. 50‑Period EMA: 109743.55

3‑Period ATR: 541.25 vs. 14‑Period ATR: 1214.557

Current Volume: 80.16 vs. Average Volume: 5080.498

MACD indicators: [-128.289, -190.044, -218.073, -280.466, -357.024, -341.94, -249.964, -184.945, -80.045, 24.991]

RSI indicators (14‑Period): [43.393, 46.27, 47.199, 45.212, 43.784, 47.863, 51.9, 51.344, 54.116, 55.277]
```

**주요 특징**:
1. ✅ **코인별 "ALL {COIN} DATA" 형식**: 현재 코드는 `# {symbol}` 형식 사용
2. ✅ **RSI (7 period) 사용**: 현재 코드는 RSI14만 사용, RSI7 미사용
3. ⚠️ **EMA20 배열**: 각 캔들별 EMA20 값 배열 제공 (현재 코드 TODO)
4. ⚠️ **MACD 배열**: 각 캔들별 MACD 값 배열 제공 (현재 코드 TODO)
5. ⚠️ **RSI7 배열**: 각 캔들별 RSI7 값 배열 제공 (현재 코드 TODO)
6. ⚠️ **RSI14 배열**: 각 캔들별 RSI14 값 배열 제공 (현재 코드 TODO)
7. ⚠️ **4H MACD 배열**: 4시간봉 MACD 값 배열 제공 (현재 코드 단일 값만)
8. ⚠️ **4H RSI14 배열**: 4시간봉 RSI14 값 배열 제공 (현재 코드 단일 값만)
9. ⚠️ **Current Volume vs Average Volume**: 현재 코드 생략

#### Account & Positions 섹션

```
HERE IS YOUR ACCOUNT INFORMATION & PERFORMANCE

Current Total Return (percent): 40.95%

Available Cash: 97.8

Current Account Value: 14095.04

Current live positions & performance:

{'symbol': 'BTC', 'quantity': 1.96, 'entry_price': 107993.0, 'current_price': 109919.5, 'liquidation_price': 103972.2, 'unrealized_pnl': 3775.94, 'leverage': 20, 'exit_plan': {'invalidation_condition': '4-hour close below 105000', 'profit_target': 112253.96, 'stop_loss': 105877.7}, 'confidence': 0.88, 'risk_usd': 403.75, 'sl_oid': 208968581802, 'tp_oid': 208968572628, 'wait_for_fill': False, 'entry_oid': 208968549342, 'notional_usd': 215442.22}

Sharpe Ratio: 0.152
```

**주요 특징**:
1. ✅ **Current Total Return (percent)**: 현재 코드에는 없음 (Account Value만 표시)
2. ✅ **Available Cash**: 현재 코드와 일치
3. ✅ **Current Account Value**: 현재 코드와 일치
4. ✅ **Sharpe Ratio**: 현재 코드와 일치 (단, 값이 0.0으로 고정)
5. ✅ **포지션 정보**: 현재 코드와 대체로 일치 (단, `symbol`이 'BTC' 형식, 현재 코드는 'BTCUSDT')

#### Rules & Output Format 섹션

```
Evaluate a decision to maximize risk-adjusted returns. Generate output in JSON format only USING THIS FORMAT:

"invalidation_condition":
"quantity":
"stop_loss":
"signal":
"profit_target":
"coin":
"leverage":
"risk_usd":
"confidence":
"justification":
```

**주요 특징**:
1. ✅ **Rules**: "Evaluate a decision to maximize risk-adjusted returns." (현재 코드와 일치)
2. ✅ **Output Format**: JSON 형식 명시 (현재 코드와 일치)
3. ⚠️ **"justification" 필드**: 실제 프롬프트에 포함되어 있으나 현재 코드 스키마에는 없음
4. ⚠️ **필드 순서**: 실제 프롬프트의 필드 순서와 현재 코드 스키마 순서가 다름

---

## 3. 현재 코드와의 비교

### 3.1 Header 섹션

| 항목 | 실제 프롬프트 | 현재 코드 | 상태 |
|------|--------------|----------|------|
| 경과 분 | ✅ | ✅ | 일치 |
| 현재 시간 | ✅ | ✅ | 일치 |
| 호출 횟수 | ✅ | ✅ | 일치 |
| "discover alpha" 문구 | ✅ | ❌ | 누락 |
| 데이터 순서 안내 | ✅ | ✅ | 일치 |
| Timeframes note | ✅ | ✅ | 일치 |

### 3.2 Market State 섹션

| 항목 | 실제 프롬프트 | 현재 코드 | 상태 |
|------|--------------|----------|------|
| 코인별 헤더 형식 | "ALL {COIN} DATA" | "# {symbol}" | 형식 다름 |
| current_rsi (7 period) | ✅ | ❌ (RSI14만) | RSI7 누락 |
| Open Interest (Latest/Average) | ✅ | ✅ (Average는 TODO) | 부분 일치 |
| Funding Rate | ✅ | ✅ | 일치 |
| Mid prices 배열 | ✅ | ✅ | 일치 |
| EMA20 배열 | ✅ | ❌ (TODO) | 미구현 |
| MACD 배열 | ✅ | ❌ (TODO) | 미구현 |
| RSI7 배열 | ✅ | ❌ (TODO) | 미구현 |
| RSI14 배열 | ✅ | ❌ (TODO) | 미구현 |
| 4H EMA20 vs EMA50 | ✅ | ✅ | 일치 |
| 4H ATR3 vs ATR14 | ✅ | ✅ | 일치 |
| 4H Current Volume vs Avg | ✅ | ❌ (생략) | 누락 |
| 4H MACD 배열 | ✅ | ❌ (단일 값만) | 배열 미구현 |
| 4H RSI14 배열 | ✅ | ❌ (단일 값만) | 배열 미구현 |

### 3.3 Account & Positions 섹션

| 항목 | 실제 프롬프트 | 현재 코드 | 상태 |
|------|--------------|----------|------|
| Current Total Return (percent) | ✅ | ❌ | 누락 |
| Available Cash | ✅ | ✅ | 일치 |
| Current Account Value | ✅ | ✅ | 일치 |
| Sharpe Ratio | ✅ | ✅ (0.0 고정) | 값 계산 필요 |
| 포지션 정보 | ✅ | ✅ | 일치 |
| symbol 형식 | 'BTC' | 'BTCUSDT' | 형식 다름 |

### 3.4 Rules & Output Format 섹션

| 항목 | 실제 프롬프트 | 현재 코드 | 상태 |
|------|--------------|----------|------|
| Rules 문구 | ✅ | ✅ | 일치 |
| JSON 형식 명시 | ✅ | ✅ | 일치 |
| 필드 순서 | 특정 순서 | 다른 순서 | 순서 다름 |
| "justification" 필드 | ✅ | ❌ | 누락 |

---

## 4. 필요한 수정 사항

### 4.1 우선순위 높음 (필수)

1. **EMA20, MACD, RSI7, RSI14 배열 계산 및 추가**
   - 각 3분봉 캔들별로 EMA20, MACD, RSI7, RSI14 계산
   - 배열 형식으로 프롬프트에 포함
   - 파일: `trading/alpha_arena/prompt_builder.py`의 `_calculate_indicators()` 메서드

2. **RSI7 추가**
   - 현재 RSI14만 계산, RSI7 추가 필요
   - `current_rsi (7 period)` 표시
   - 파일: `trading/alpha_arena/prompt_builder.py`

3. **4H MACD, RSI14 배열 추가**
   - 4시간봉 MACD, RSI14 배열 계산 및 제공
   - 현재는 단일 값만 제공
   - 파일: `trading/alpha_arena/prompt_builder.py`

4. **Current Volume vs Average Volume 추가**
   - 4H 컨텍스트에 Volume 데이터 추가
   - 파일: `trading/alpha_arena/prompt_builder.py`

### 4.2 우선순위 중간 (권장)

5. **Header에 "discover alpha" 문구 추가**
   - "Below, we are providing you with a variety of state data, price data, and predictive signals so you can discover alpha."
   - 파일: `trading/alpha_arena/prompt_builder.py`의 `_format_prompt()`

6. **코인별 헤더 형식 변경**
   - `# {symbol}` → `ALL {COIN} DATA` (예: `ALL BTC DATA`)
   - 파일: `trading/alpha_arena/prompt_builder.py`

7. **Current Total Return (percent) 추가**
   - Account & Positions 섹션에 수익률 퍼센트 추가
   - 파일: `trading/alpha_arena/prompt_builder.py`, `trading/alpha_arena/metrics.py`

8. **Sharpe Ratio 계산 구현**
   - 현재 0.0 고정, 실제 계산 필요
   - 파일: `trading/alpha_arena/metrics.py`

### 4.3 우선순위 낮음 (선택)

9. **"justification" 필드 추가**
   - Output Format에 "justification" 필드 추가 (선택적)
   - 파일: `trading/alpha_arena/prompt_builder.py`, `trading/alpha_arena/response_parser.py`

10. **필드 순서 조정**
    - 실제 프롬프트의 필드 순서에 맞춰 조정 (선택적)
    - 파일: `trading/alpha_arena/prompt_builder.py`

11. **symbol 형식 통일**
    - 포지션 정보에서 'BTC' vs 'BTCUSDT' 형식 통일 (선택적)
    - 파일: `trading/alpha_arena/prompt_builder.py`

---

## 5. 결론

### 5.1 현재 상태

현재 코드는 Alpha Arena 벤치마크의 기본 구조는 갖추고 있으나, **실제 프롬프트와 비교했을 때 중요한 데이터 배열들이 누락**되어 있습니다:

- ❌ **EMA20, MACD, RSI7, RSI14 배열 미구현** (각 캔들별 계산 필요)
- ❌ **RSI7 미사용** (RSI14만 사용)
- ❌ **4H MACD, RSI14 배열 미구현** (단일 값만 제공)
- ❌ **Volume 데이터 생략**

### 5.2 Reddit 역공학 결과 vs 실제 프롬프트 샘플

Reddit 역공학 결과와 실제 프롬프트 샘플이 **놀랍도록 일치**합니다:

- ✅ 프롬프트 구조 (Header, Market State, Account & Positions, Rules, Output Format)
- ✅ 시계열 데이터 형식 (3분봉 배열, 4H 컨텍스트)
- ✅ 지표 종류 (EMA20, MACD, RSI7, RSI14)
- ✅ 배열 데이터 제공 방식

**결론**: Reddit 역공학 결과가 매우 정확하며, 실제 Alpha Arena 벤치마크의 프롬프트 구조를 잘 반영하고 있습니다.

### 5.3 다음 단계

1. **즉시 수정 필요** (우선순위 높음):
   - EMA20, MACD, RSI7, RSI14 배열 계산 구현
   - RSI7 추가
   - 4H MACD, RSI14 배열 추가
   - Volume 데이터 추가

2. **문서 업데이트**:
   - `docs/ALPHA_ARENA_MODE.md`에 실제 프롬프트 샘플 반영
   - 배열 데이터 형식 명시

3. **테스트**:
   - 수정 후 실제 프롬프트 형식과 비교 검증
   - LLM 응답 품질 확인

---

## 6. 수정 완료 보고 (2025-01-XX)

### 6.1 수정 완료된 항목

#### ✅ 1. EMA20, MACD, RSI7, RSI14 배열 계산 구현

**수정 파일**: `trading/alpha_arena/prompt_builder.py`

**추가된 메서드**:
- `_calculate_rsi_array(prices, period)`: 각 캔들별 RSI 값 배열 계산
- `_calculate_ema_array(prices, period)`: 각 캔들별 EMA 값 배열 계산
- `_calculate_macd_array(prices)`: 각 캔들별 MACD 값 배열 계산 (EMA12 - EMA26)

**작동 방식**:
- 3분봉 캔들 데이터를 순차적으로 처리하여 각 시점의 지표 값을 계산
- RSI 배열: 각 캔들 시점에서 해당 시점까지의 데이터로 RSI 계산
- EMA 배열: 첫 EMA는 SMA로 시작, 이후 EMA 공식 적용
- MACD 배열: EMA12 배열과 EMA26 배열을 계산한 후 차이값으로 MACD 배열 생성

**MarketSnapshot 데이터 클래스 업데이트**:
- `ema_20_array: Optional[List[float]]` 추가
- `macd_array: Optional[List[float]]` 추가
- `rsi_7_array: Optional[List[float]]` 추가
- `rsi_14_array: Optional[List[float]]` 추가

#### ✅ 2. RSI7 추가

**수정 내용**:
- `_calculate_indicators()` 메서드에서 RSI7 계산 추가
- `MarketSnapshot`에 `rsi_7: Optional[float]` 필드 추가
- 프롬프트에 `current_rsi (7 period)` 표시 추가

**작동 방식**:
- 3분봉 데이터가 7개 이상일 때 RSI7 계산
- 현재값과 배열 모두 제공

#### ✅ 3. 4H MACD, RSI14 배열 추가

**수정 내용**:
- 4시간봉 데이터에 대해 MACD 배열, RSI14 배열 계산 추가
- `MarketSnapshot`에 `macd_4h_array`, `rsi_14_4h_array` 필드 추가

**작동 방식**:
- 4시간봉 캔들 데이터를 사용하여 배열 계산
- 3분봉과 동일한 방식으로 각 캔들별 지표 값 계산

#### ✅ 4. Volume 데이터 추가

**수정 내용**:
- 4시간봉 데이터에서 Volume 추출
- `current_volume`: 최신 4H 캔들의 볼륨
- `average_volume`: 모든 4H 캔들의 평균 볼륨
- 프롬프트에 "Current Volume vs Average Volume" 형식으로 표시

**작동 방식**:
- 4시간봉 캔들 데이터에서 `volume` 필드 추출
- 최신 캔들의 볼륨을 `current_volume`으로 설정
- 모든 캔들의 볼륨 평균을 `average_volume`으로 계산

#### ✅ 5. 프롬프트 포맷팅 수정

**수정 내용**:
- Header에 "discover alpha" 문구 추가
- 코인별 헤더 형식 변경: `# {symbol}` → `ALL {COIN} DATA`
- RSI7 표시: `current_rsi (7 period)` 형식
- 배열 데이터를 프롬프트에 포함:
  - `EMA indicators (20‑period): [array]`
  - `MACD indicators: [array]`
  - `RSI indicators (7‑Period): [array]`
  - `RSI indicators (14‑Period): [array]`
- 4H 컨텍스트에 배열 데이터 포함:
  - `MACD indicators: [array]`
  - `RSI indicators (14‑Period): [array]`
- Volume 데이터 표시: `Current Volume: {v} vs. Average Volume: {v}`

**작동 방식**:
- 각 코인별로 최근 10개 캔들의 배열 데이터만 사용 (실제 프롬프트 샘플 기준)
- 배열 값은 소수점 자릿수 반올림 (EMA/MACD: 3자리, RSI: 2-3자리)
- 코인 심볼에서 USDT 제거 (예: BTCUSDT → BTC)

### 6.2 현재 프롬프트 구조

#### Header 섹션
```
It has been {minutes_running} minutes since you started trading.
The current time is {now} and you've been invoked {tick_count} times.
Below, we are providing you with a variety of state data, price data, and predictive signals so you can discover alpha.

ALL OF THE PRICE OR SIGNAL DATA BELOW IS ORDERED: OLDEST → NEWEST

Timeframes note: Unless stated otherwise in a section title, intraday series are provided at 3‑minute intervals. If a coin uses a different interval, it is explicitly stated in that coin's section.
```

#### Market State 섹션 (각 코인별)
```
ALL {COIN} DATA

current_price = {v}, current_ema20 = {v}, current_macd = {v}, current_rsi (7 period) = {v}

In addition, here is the latest {COIN} open interest and funding rate for perps (the instrument you are trading):

Open Interest: Latest: {v}  Average: {v}

Funding Rate: {v}

Intraday series (3‑minute intervals, oldest → latest):

{COIN} mid prices: [{...}]

EMA indicators (20‑period): [{...}]

MACD indicators: [{...}]

RSI indicators (7‑Period): [{...}]

RSI indicators (14‑Period): [{...}]

Longer‑term context (4‑hour timeframe):

20‑Period EMA: {v} vs. 50‑Period EMA: {v}

3‑Period ATR: {v} vs. 14‑Period ATR: {v}

Current Volume: {v} vs. Average Volume: {v}

MACD indicators: [{...}]

RSI indicators (14‑Period): [{...}]
```

### 6.3 작동 흐름

1. **시장 데이터 수집** (`collect_market_data`)
   - Binance API에서 3분봉, 4시간봉 데이터 조회
   - 24h 티커 데이터에서 가격, Funding Rate, Open Interest 조회

2. **지표 계산** (`_calculate_indicators`)
   - 3분봉 데이터로 현재값 지표 계산 (RSI7, RSI14, EMA20, MACD)
   - 3분봉 데이터로 배열 지표 계산 (EMA20, MACD, RSI7, RSI14 배열)
   - 4시간봉 데이터로 현재값 지표 계산 (EMA20/EMA50, ATR3/ATR14, MACD, RSI14)
   - 4시간봉 데이터로 배열 지표 계산 (MACD, RSI14 배열)
   - 4시간봉 데이터에서 Volume 추출 및 평균 계산

3. **프롬프트 생성** (`build_prompt` → `_format_prompt`)
   - Header 섹션 생성
   - Market State 섹션 생성 (각 코인별 상세 데이터)
   - Account & Positions 섹션 생성
   - Rules 섹션 생성
   - Output Format 섹션 생성

4. **LLM 호출**
   - 생성된 프롬프트를 LLM에 전달
   - LLM이 MODEL_CHAT과 TRADING_DECISIONS 응답 생성

### 6.4 주요 개선 사항

1. **실제 Alpha Arena 벤치마크와 일치하는 프롬프트 형식**
   - Reddit 역공학 결과와 실제 프롬프트 샘플을 기반으로 정확히 구현
   - 배열 데이터 제공으로 LLM이 시계열 패턴 분석 가능

2. **더 풍부한 시장 데이터 제공**
   - RSI7 추가로 단기 모멘텀 분석 가능
   - 각 캔들별 지표 배열로 추세 변화 추적 가능
   - Volume 데이터로 거래량 분석 가능

3. **4H 컨텍스트 강화**
   - 4H MACD, RSI14 배열로 장기 추세 분석 가능
   - Volume 비교로 거래량 변화 추적 가능

### 6.5 남은 작업 (선택적)

1. **Open Interest 평균 계산 개선**
   - 현재는 현재값과 동일하게 설정
   - 향후 여러 틱의 평균 계산 가능

2. **"justification" 필드 추가** (선택적)
   - Output Format에 "justification" 필드 추가 가능

3. **필드 순서 조정** (선택적)
   - 실제 프롬프트의 필드 순서에 맞춰 조정 가능

---

## 참고 자료

- Reddit 역공학 결과: 사용자 제공
- 실제 Alpha Arena 프롬프트 샘플: 사용자 제공 (2025-10-23 20:14:54 기준)
- 현재 코드: `trading/alpha_arena/prompt_builder.py`
- 문서: `docs/ALPHA_ARENA_MODE.md`
