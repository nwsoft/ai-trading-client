# AlphaArena 모드 설계서

**상태**: 개발 완료 (가드레일 통합 테스트 통과 기준)  
**구현 여부**: 구현 완료  
**대상 버전**: v3.8.8.6+

**대상**: `noahai_client` 안에 기존 자동거래 파이프라인과 분리된 독립 모드

---
## 🚀 Quick Start (개발·테스트용 요약)

- **탭 켜기**: 대시보드 → 거래소 탭 옆 **AlphaArena** 탭 표시
- **엔진 선택**: DeepSeek 3.1(기본) / Qwen 3 Max(선택)
- **LLM 호출 주기**: 기본 60초(권장), 최소 30초(내부 가드레일)
- **시계열 데이터**: 3분봉 배열(OLDEST → NEWEST) + 4시간 컨텍스트 지표(EMA20/EMA50, ATR3/ATR14, MACD, RSI14)
- **주문 정책**:
  - LLM 응답의 `TRADING_DECISIONS`에 **ENTER_LONG/ENTER_SHORT**가 **명시된 코인만 진입** (명시 없으면 기본 HOLD)
  - **TP/SL가 둘 다 없는 진입은 실행 금지** (다음 턴 프롬프트에 누락 사유 첨부)
  - 청산(`CLOSE`)은 포지션이 있을 때만 실행
- **가드레일(필수)**:
  - 최대 동시 포지션: 기본 6종 (심볼당 최대 1개)
  - 최소 명목금액(심볼별 `minNotional`) 충족 시에만 주문
  - 레버리지 10–20x 범위로 클램핑 (응답이 범위를 벗어나면 경고 + 자동보정)
  - **쿨다운**: 동일 코인 재진입 최소 30초 간격
  - **리스크 캡**: `risk_usd` 합계가 `max_risk_per_tick` 초과 시 해당 틱 신규 진입 금지
- **피드백 루프**: 마지막 주문/응답/에러 전문을 **그대로** 다음 프롬프트에 첨부 → LLM이 직접 재지시

## 🎯 MVP 규칙 (최소 기능 모드)

Alpha Arena 모드는 다음 최소 구성으로 동작합니다:

1. **엔진 선택만 노출**: UI에서는 DeepSeek 3.1 또는 Qwen 3 Max 선택만 가능
2. **3분봉 배열 + 4H 컨텍스트 동적 프롬프트**: 시계열 데이터는 3분봉 배열과 4시간 컨텍스트 지표를 제공
3. **60초 주기 호출**: LLM 호출 주기는 기본 60초(권장), 최소 30초(내부 가드레일)
4. **동일 JSON 스키마**: Alpha Arena 벤치마크와 동일한 `TRADING_DECISIONS` JSON 형식
5. **Binance USDT-M 단일 거래소**: Binance Futures(USDT-M)만 사용
6. **게이트/맵핑 고정**: 주문 게이트 규칙과 Binance 주문 매핑 규칙은 벤치마크와 동일하게 고정

---

## ✅ Alpha Arena 모드 철학

본 모드는 nof1.ai의 Alpha Arena 벤치마크에서 **실제 수익을 낸 엔진들(DeepSeek Chat v3.1, Qwen 3 Max)**의 거래 구조와 프롬프트 형식을 그대로 이식하여,

동일한 거래 시퀀스(입력 → 판단 → 명령 → 체결)를 **NoahAI 내부 실거래 환경(Binance Futures)**에서 재현한다.

즉, Alpha Arena처럼 여러 AI를 비교하는 벤치마크는 아니며,

그 벤치마크에서 검증된 **"승리 알고리즘"**을 NoahAI가 상용화한 독립 거래 모드이다.

---

## ⚙️ 구현 핵심 (벤치마크 원리 + 상용화 결합형)

### 1. 공통 프롬프트 엔진
- Alpha Arena와 동일한 형식으로 프롬프트 구성 (5개 섹션 고정)
- 시계열 데이터: 3분봉 배열(OLDEST → NEWEST) + 4시간 컨텍스트 지표
- NoahAI의 실시간 데이터로 채움
- 데이터 소스: Binance Futures(USDT-M). OI/Funding/Price/Filters 모두 Binance API로부터 수집

### 2. 엔진 선택
- **DeepSeek 3.1** (기본)
- **Qwen 3 Max** (선택 / 멀티엔진 비교 가능)
- 나머지 엔진(GPT, Claude 등)은 제외

### 3. 거래 명령 구조
- Alpha Arena의 `TRADING_DECISIONS` JSON 형식을 **그대로** 유지
- **명시적 신호만 실행**: `ENTER_LONG`/`ENTER_SHORT`/`CLOSE`만 주문·청산. `HOLD` 또는 신호 미기재는 **무주문**(기본 유지)
- **TP/SL 의무화**:
  - 진입 시 `profit_target`(TP)·`stop_loss`(SL) **둘 다 필수**
  - 미제공 시 해당 심볼은 **스킵**하고, 다음 턴 프롬프트에 `TP/SL missing: {symbol}`를 첨부
- `invalidation_condition`는 설명·로그용으로만 저장(주문 생성에는 직접 사용하지 않음)
- 수량 필드:
  - `quantity`(계약 수량) 또는 `notional_usd`(명목금액) 중 하나 허용
  - `notional_usd`가 오면 현재가/필터 기준으로 **정확한 수량으로 변환**

### 4. 실행 환경
- Binance Futures API 사용 (실선물 계좌 또는 Testnet)
- NoahAI의 내부 모니터링 / 보험 로직은 끔 (LLM 판단 그대로 실행)

### 5. 성과 기록
- 각 엔진별 실현 수익률 / 샤프비율 기록
- 화면에 `MODEL_CHAT`을 그대로 보여줌 (Alpha Arena의 "Model Chat 탭" 느낌)
- **데이터베이스 저장**: 모든 거래(진입/청산)는 `trade_log` 테이블에 자동 저장됨
- **대시보드 통합**: 거래 현황 패널과 거래 통계 탭에서 Alpha Arena 거래도 함께 표시됨

---

## 📊 기대 결과

| 엔진 | 전략 특성 | Alpha Arena 기록 (참고) | NoahAI 적용 기대 |
|------|----------|------------------------|------------------|
| **DeepSeek Chat V3.1** | 짧은 보유시간, 변동성 추종, TP·SL 준수율 높음 | Season 1 상위권 (10~20%+) | Binance 기반에서도 고효율 가능 |
| **Qwen 3 Max** | 포지션 분할·확신도 조정이 안정적 | Season 1 상위권 | 장기·스윙형으로 응용 가능 |
| Others (GPT, Claude 등) | 명령 해석 불안정 / 리스크 관리 약함 | 손실 다수 | 제외 |

---

## 🧩 결론

- **Alpha Arena는 벤치마크 실험체계**
- **NoahAI AlphaArena 모드는 벤치마크의 승리전략을 상용화한 LLM 자율거래 모드**
- **거래소는 상관없음** — 단지 선물 거래 API를 지원하는 곳이면 충분
- **핵심은 "동일 프롬프트 구조 + 동일 명령 시퀀스 + 우수 엔진"**

---

## 핵심 원칙

1. **바이낸스 선물 하나만 쓴다.** (Hyperliquid/Bybit/OKX/CCXT 언급 금지)
2. **기존 `trader.py`, 포지션 모니터, TP/SL 보험, 워치독 안 쓴다.**
3. **LLM이 사람이 읽을 수 있는 `MODEL_CHAT`을 먼저 말하고,**
4. **그 아래에 실행 가능한 JSON(`TRADING_DECISIONS`)을 내려주면**
5. **클라이언트가 그 JSON만 바이낸스 주문으로 바꿔서 넣는다.**
6. **사용자가 모르면 AlphaArena 안내 모달 → 설정 탭 순서로 보게 한다.**

---

## 1. 목적

- **벤치마크가 아니라 검증된 승리전략을 상용화한 모드**
- **DeepSeek/Qwen 기반 동일 명령 실행 구조**
- **거래소는 바이낸스, 데이터 구조는 Alpha Arena 포맷 유지**
- nof1.ai의 Alpha Arena에서 실제 수익을 낸 엔진들의 거래 구조를 그대로 이식하여, 동일한 거래 시퀀스를 NoahAI 내부 실거래 환경에서 재현한다.
- "비교/실험 모드"가 아니라 **"검증된 LLM이 실제로 거래를 말로 하는 모드"**가 1차 목표다.
- 그래서 자동 보험 TP/SL, 감시 워치독 같은 NoahAI 고정 로직을 이 모드에서는 사용하지 않는다. 그건 LLM이 직접 다시 말해서 고치게 한다.

---

## 2. 범위 (Scope)

### 포함
- LLM 프롬프트 템플릿
- LLM 응답 포맷 (설명 + 실행 JSON) 정의
- Binance 선물 주문 파라미터로의 직접 변환 규칙
- AlphaArena 탭/UI/모달 안내 문구
- 설정 (`settings.json`)에 들어갈 키

### 제외
- 다중 거래소
- 기존 `trader.py` / `unified_trader` 경로로의 위임
- 자동 TP/SL 보험 / 워치독 / 재설정
- 리더보드·엔진간 성능 비교

---

## 3. 전체 구조

```
[대시보드 AlphaArena 탭]
        │
        ▼
[AlphaArena Runner]  ← 이게 새로 생기는 실행 루프
        │
        ├─ (1) 시장/계좌/포지션/직전주문 → LLM 프롬프트로 변환
        │
        ├─ (2) LLM 호출 (deepseek-3.1 1개부터)
        │
        ├─ (3) LLM 응답을 두 덩어리로 받음
        │        - MODEL_CHAT (사람이 읽는 설명)
        │        - TRADING_DECISIONS (기계가 실행)
        │
        ├─ (4) TRADING_DECISIONS만 파싱
        │
        └─ (5) Binance 선물 API로 직접 주문/청산
                (기존 trader.py 안 거침)
```

---

## 4. 실행 순서 (런타임 루프)

### 1. 수집
6개 코인 시세/지표 + 계좌 정보 + 현재 포지션 + 직전 주문 결과를 한 번에 모은다.

**고정 심볼**: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`, `DOGEUSDT`, `BNBUSDT`

### 2. 프롬프트 생성
Alpha Arena 벤치마크와 동일한 5개 섹션 구조로 프롬프트를 생성합니다:

1. **Header**: 현재 시간, 경과 분, 호출 횟수
2. **Market State**: 코인별 현재값 + 3분봉 배열 + 4H 컨텍스트
3. **Account & Positions**: 포지션 필드(quantity, entry_price, liquidation_price, unrealized_pnl, exit_plan{profit_target, stop_loss, invalidation_condition}, leverage, confidence, risk_usd, oid들)
4. **Rules**: 체크리스트("무효화 충족 전 보유, 피라미딩 금지, 보유 코인 재진입 금지, JSON-only 출력 등")
5. **Output format**: JSON compact, 산문 금지

### 3. LLM 호출
`deepseek-3.1` (v1은 이거만)

### 4. LLM 응답 파싱

- **첫 부분**: 설명형 모델 채팅 → 화면에 그대로 노출
- **두 번째 부분**: JSON → 이게 없으면 이번 턴은 실행 안 함

### 5. 주문/청산 실행

- JSON 안에 **신호가 있는 코인만** 실행 (명시 없는 코인은 기본 HOLD 처리)
- 진입 주문:
  - `MARKET` 진입 → **즉시** `TAKE_PROFIT_MARKET`/`STOP_MARKET` 예약 (reduceOnly=false)
  - 심볼별 정밀도(가격 틱, 수량 스텝, minNotional) **사전 검증 및 반올림**
- 청산 주문:
  - `CLOSE` 신호 수신 시 포지션 전량 시장가 청산(reduceOnly=true)
- 검증 실패 시:
  - 해당 심볼 실행 **건너뜀** + 실패 사유를 다음 프롬프트에 그대로 첨부

### 6. 피드백

- 방금 보낸 주문ID, 체결가, 미체결 사유를 다음 턴 프롬프트에 붙임
- LLM이 "그거 안 들어갔으니까 다시 보내"라고 직접 말하게 함

---

## 5. LLM 프롬프트 구조 (5개 섹션 고정)

### 섹션 1: Header
```
It has been {elapsed_minutes} minutes since you started trading.

The current time is {now_iso} and you've been invoked {invoke_count} times.

ALL OF THE PRICE OR SIGNAL DATA BELOW IS ORDERED: OLDEST → NEWEST

Timeframes note: Unless stated otherwise, intraday series are provided at 3-minute intervals.
```

### 섹션 2: Market State
```
CURRENT MARKET STATE FOR ALL COINS

# For each of [BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT, BNBUSDT]

{symbol}
current_price = {v}, current_ema20 = {v}, current_macd = {v}, current_rsi_7 = {v}

Open Interest: Latest: {v}  Average: {v}

Funding Rate: {v}

Intraday series (3-minute intervals, oldest → latest):
Mid prices: [{...}]
EMA20: [{...}]
MACD: [{...}]
RSI7/RSI14: [{...}]

Longer-term context (4-hour timeframe):
EMA20 vs EMA50: {v} vs {v}
ATR3 vs ATR14: {v} vs {v}
Current Volume vs Avg: {v} vs {v}
MACD(4H): [{...}]
RSI14(4H): [{...}]
```

### 섹션 3: Account & Positions
```
HERE IS YOUR ACCOUNT INFORMATION & PERFORMANCE

Available Cash: {v}
Account Value: {v}
Sharpe Ratio: {v}

Current live positions & performance:

# for each position
{'symbol': 'BTCUSDT', 'quantity': ..., 'entry_price': ..., 'current_price': ..., 
 'liquidation_price': ..., 'unrealized_pnl': ..., 'leverage': 10..20,
 'exit_plan': {'invalidation_condition': '...', 'profit_target': ..., 'stop_loss': ...},
 'confidence': ..., 'risk_usd': ..., 'sl_oid': ..., 'tp_oid': ..., 'wait_for_fill': ..., 'entry_oid': ..., 'notional_usd': ...}
```

### 섹션 4: Rules
```
Evaluate a decision to maximize risk-adjusted returns.

Rules: No pyramiding. No re-entry into coins you already hold. If invalidation not triggered → HOLD by default.
```

### 섹션 5: Output Format
```
JSON ONLY. NO prose.

For each of [BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT, BNBUSDT] output this schema:

{
 "coin": "...", 
 "signal": "HOLD|CLOSE|ENTER_LONG|ENTER_SHORT",
 "quantity": <number>, 
 "leverage": <10..20>, 
 "profit_target": <number>, 
 "stop_loss": <number>, 
 "invalidation_condition": "<string>", 
 "risk_usd": <number>,
 "confidence": <0..1>
}
```

---

## 6. LLM 응답 포맷

LLM이 이렇게 내려오도록 강제하는 게 목표입니다.

### MODEL_CHAT

```
I'm currently up 29.81% overall, managing profitable ETH, SOL, BTC, and DOGE positions...
(여러 줄 설명)
```

### TRADING_DECISIONS

```json
{
  "ETH": {
    "signal": "HOLD",
    "quantity": 4.57,
    "profit_target": 4068.075,
    "stop_loss": 3513.3375,
    "invalidation_condition": "If the price closes below 3650 on a 3-minute candle",
    "leverage": 10,
    "confidence": 0.7,
    "risk_usd": 844.825
  },
  "SOL": {
    "signal": "HOLD",
    "quantity": 79.18,
    "profit_target": 188.357,
    "stop_loss": 173.621,
    "invalidation_condition": "If the price closes below 170 on a 3-minute candle",
    "leverage": 10,
    "confidence": 0.8,
    "risk_usd": 290.99
  },
  "XRP": { ... },
  "BTC": { ... },
  "DOGE": { ... },
  "BNB": { ... }
}
```

### 중요 포인트

- **6개 코인은 모두 내려오게 한다.** (없으면 "누락"으로 다음 턴에 다시 요청)
- **signal 값은 이 4개만 허용**:
  - `HOLD` (기존 포지션 유지)
  - `CLOSE` (시장가 청산)
  - `ENTER_LONG`
  - `ENTER_SHORT`
- **TP/SL 둘 다 없으면 실행 안 함** → 다음 턴에 "TP/SL missing for XRP"를 붙여서 LLM에 다시 보냄
- **quantity는 USDT 기준 금액이 아니라 실제 계약 수량으로 받는 게 낫지만**, LLM이 헷갈릴 수 있으니 v1에서는 "수량 또는 notional" 둘 다 허용해도 됨 (Runner가 변환)

---

## 6.1 주문 게이트(Trade Eligibility) — 언제 **실제로** 주문하나

아래 조건을 **모두** 만족할 때만 진입 주문을 전송한다.

1) 신호: `ENTER_LONG` 또는 `ENTER_SHORT`
2) 보호장치: `profit_target`와 `stop_loss` **모두 존재**
3) 정밀도: 심볼의 가격 틱/수량 스텝/최소 명목금액 조건 충족
4) 레버리지: 10~20x 범위(벗어나면 자동보정 후 경고)
5) 리스크 캡: 이번 틱의 신규 진입 `risk_usd` 합 <= `max_risk_per_tick`
6) 쿨다운: 동일 심볼 최근 진입 이후 최소 30초 경과
7) 최대 동시 포지션: 심볼당 1개, 전체 6개 내

※ 하나라도 위배되면 **해당 심볼만 스킵**하고, 스킵 사유를 다음 프롬프트에 첨부한다.

---

## 6.2 검증 추가 규칙

### 신호별 TP/SL 필수 여부
- **`ENTER_LONG` / `ENTER_SHORT`**: `profit_target`와 `stop_loss` **둘 다 필수**
  - 하나라도 없으면 해당 심볼 실행 **스킵** + 다음 프롬프트에 "TP/SL missing: {symbol}" 첨부
- **`HOLD` / `CLOSE`**: TP/SL 없어도 허용
  - `HOLD`는 포지션 유지, `CLOSE`는 청산만 수행

### 레버리지 클램핑
- 실행 시 `leverage`는 **[10, 20] 범위로 자동 클램핑**
- 범위를 벗어나면:
  - 경고 로그 기록
  - 클램핑된 값으로 주문 실행
  - 다음 프롬프트에 "leverage clamped from {original} to {clamped}" 사유 첨부

## 7. Binance 주문 매핑 규칙 (벤치마크 규칙 고정)

### 신호별 매핑
- `HOLD` → 주문 전송 안 함
- `CLOSE` → 보유 수량 전량 시장가 청산 (reduceOnly=true)
- `ENTER_LONG` → `FUTURES MARKET BUY` 진입 → TP/SL 예약
- `ENTER_SHORT` → `FUTURES MARKET SELL` 진입 → TP/SL 예약

### TP/SL 생성
- **TP**: `TAKE_PROFIT_MARKET` + `stopPrice=profit_target` + `reduceOnly=true` + `workingType=MARK_PRICE`
- **SL**: `STOP_MARKET` + `stopPrice=stop_loss` + `reduceOnly=true` + `workingType=MARK_PRICE`

### 검증 규칙
- **ENTER_***: `profit_target`, `stop_loss`, `invalidation_condition` 필수
- **HOLD/CLOSE**: TP/SL 없어도 허용
- **레버리지**: [10, 20] 범위로 클램핑
- **Pyramiding 금지**: 보유 코인 재진입 금지
- **심볼별 쿨다운**: 30초 (동일 심볼 재진입 최소 간격)

### 정밀도/필터
- `exchangeInfo` 기반으로 가격/수량을 반올림(`tickSize`, `stepSize`)
- `minNotional` 미만이면 실행 금지(스킵 + 사유 첨부)

### 레버리지/마진 모드
- 심볼 진입 전 1회 `isolated` + `leverage in [10,20]` 설정

### 멱등성·시간
- `newClientOrderId` = `arena:{session_id}:{symbol}:{uuid}`
- `timestamp/recvWindow` 적용, 서버시간과 오차 ±500ms 유지

---

## 8. 설정 예시 (settings.json 일부)

```jsonc
{
  "alpha_arena": {
    "enabled": false,
    "exchange": "binance-futures",
    "engine": "deepseek-3.1",
    "available_engines": ["deepseek-3.1", "qwen3-max"],
    "deepseek_api_key": "",              // DeepSeek API 키 (설정 UI에서 입력)
    "qwen_api_key": "",                  // Qwen3 (Alibaba) API 키 (설정 UI에서 입력)
    "tick_interval_sec": 60,            // 내부 가드레일 (기본 60, 최소 30, UI 노출 X)
    "symbols": [
      "BTCUSDT",
      "ETHUSDT",
      "SOLUSDT",
      "XRPUSDT",
      "DOGEUSDT",
      "BNBUSDT"
    ],
    "leverage_min": 10,                   // 내부 가드레일 (사용자 조절 불필요)
    "leverage_max": 20,                   // 내부 가드레일 (사용자 조절 불필요)
    "max_risk_per_tick": 1500.0,          // 내부 가드레일 (사용자 조절 불필요)
    "cooldown_sec_per_symbol": 30,       // 내부 가드레일 (사용자 조절 불필요)
    "max_concurrent_positions": 6,        // 내부 가드레일 (사용자 조절 불필요)
    "require_trading_decisions": false,   // 설명만 한 턴도 허용
    "echo_last_orders_to_llm": true,      // 직전 주문/에러를 프롬프트에 항상 붙여줌
    "auto_insurance_tp_sl": false,        // ✅ 기존 보험 기능 끔
    "workingType": "MARK_PRICE",
    "logging": {
      "level": "INFO",
      "store_prompt_hash": true,
      "prompt_version": "alphaarena-v1"
    },
    "help": {
      "on_unknown": "대시보드 사용자메뉴얼에서 AlphaArena 가서 설명을 읽어주세요."
    }
  }
}
```

**설정 UI 구성**:
- **활성화 스위치**: Alpha Arena 모드 활성화/비활성화
- **AI 엔진 선택**: DeepSeek 3.1 또는 Qwen3 Max 선택 (UI 노출)
- **API 키 입력**: 
  - DeepSeek API Key (필수, 선택한 엔진이 DeepSeek인 경우)
  - Qwen3 (Alibaba) API Key (필수, 선택한 엔진이 Qwen3인 경우)
- **주의사항**: 카드 섹션으로 표시, "모르면 대시보드 사용자메뉴얼에서 AlphaArena 가서 설명을 읽어주세요"

**설정 노출 정책**: 엔진 선택(DeepSeek/Qwen)만 UI 노출. `tick_interval_sec`, `leverage` 범위, `cooldown`, 동시 포지션, `tick당 리스크`는 `settings.json` 내부 키로만 유지(가드레일), UI 비노출.

## 8.1 설정 키 상세 (필수/선택)

- `alpha_arena.max_concurrent_positions` (default: 6)
- `alpha_arena.cooldown_sec_per_symbol` (default: 30)
- `alpha_arena.max_risk_per_tick` (default: 1500)  // 이번 틱 신규 진입 risk_usd 합계 상한
- `alpha_arena.workingType` (default: "MARK_PRICE")
- `alpha_arena.min_tp_sl_distance_ratio` (optional)  // 현재가 대비 최소 TP/SL 거리

---

## 9. UI / 모달 문구 가이드

### 탭 이름
**AlphaArena**

### 첫 진입 시 모달

```
AlphaArena 모드는 일반 자동매매와 다릅니다.

1. LLM이 말로 거래를 지시하고
2. 그 지시만 그대로 바이낸스에 나가며
3. NoahAI의 기존 TP/SL 보험과 워치독은 동작하지 않습니다.

설정에서 엔진과 API 키만 입력해주세요.
```

### 모르면
"대시보드 사용자메뉴얼에서 AlphaArena 가서 설명을 읽어주세요"

- 모니터링 패널(AlphaArena 탭):
  - 상단: MODEL_CHAT 실시간 스트림 (분리 패널)
  - 중간: TRADING_DECISIONS 요약(신호/수량/TP/SL/사유) (분리 패널)
  - 좌측: 현재 포지션/미체결/실현·미실현 PnL
  - 우측: 최근 거래소 응답 전문(성공/실패 사유 포함)
  - 하단: 로그 표시 (MODEL_CHAT와 TRADING_DECISIONS 분리 표시)

---

## 10. 테스트 플로우 (개발자가 바로 쓸 수 있는 거)

1. 모의 데이터로 위에 주신 긴 상태 프롬프트를 그대로 LLM에 던진다.
2. LLM 응답에서 `TRADING_DECISIONS` 블록만 잘라서 파싱해본다.
3. 파싱 결과에서 TP/SL 없는 코인만 골라 "누락"으로 표시되는지 확인.
4. 그걸 다시 프롬프트에 붙여서 LLM이 정말로 보정해서 보내는지 본다.
5. 마지막으로 Binance testnet에 직접 주문을 던져서 "기존 trader.py 없이도" 체결이 되는지 확인한다.

---

## 11. 향후 확장 (메모만)

- **엔진 2개(deepseek + qwen)로 동시에 돌릴 때는**
  → `TRADING_DECISIONS`를 2개 받을지
  → 아니면 "둘 중 점수 높은 엔진 것만 실행"할지 정책이 필요하므로 v2로 미룸.
- **실거래 로그 → 화면 표시는 전부 MODEL_CHAT 우선 노출**
- **리더보드, 비교, 그래프는 이 모드 다 돌리고 나서 나중에**

---

## 12. 구현 예상 파일 구조

```
trading/
  alpha_arena/
    __init__.py
    runner.py          # 메인 실행 루프
    prompt_builder.py  # 프롬프트 생성
    response_parser.py # MODEL_CHAT + TRADING_DECISIONS 파싱
    order_executor.py  # Binance 직접 주문 (trader.py 안 거침)
    metrics.py         # 세션 메트릭 수집

ui/widgets/
  alpha_arena_widget.py  # AlphaArena 탭 UI

config/
  settings.py          # alpha_arena 설정 키 추가
```

---

## 13. 데이터 모델

### MarketSnapshot
```python
{
    "timestamp": "2024-01-01T00:00:00Z",
    "symbols": [
        {
            "symbol": "BTCUSDT",
            "price": 43250.5,
            "spread": 0.05,
            "24h_vol": 1250000000,
            "funding": 0.0001,
            "trend": "uptrend",
            "indicators": {
                "ema_20": 43000,
                "macd": 150,
                "rsi": 58,
                "oi": 5000000000
            }
        },
        # ... 5개 더
    ]
}
```

### ArenaDecision (TRADING_DECISIONS 파싱 결과)
```python
{
    "ETH": {
        "signal": "HOLD",  # HOLD | CLOSE | ENTER_LONG | ENTER_SHORT
        "quantity": 4.57,
        "profit_target": 4068.075,  # 가격 또는 None
        "stop_loss": 3513.3375,     # 가격 또는 None
        "invalidation_condition": "If price closes below 3650 on 3-min candle",
        "leverage": 10,
        "confidence": 0.7,
        "risk_usd": 844.825
    },
    # ... 5개 더 (모든 심볼 필수)
}
```

### ArenaSession
```python
{
    "session_id": "arena_20240101_120000",
    "start_time": "2024-01-01T12:00:00Z",
    "engine": "deepseek-3.1",
    "initial_balance": 10000.0,
    "current_balance": 12981.0,
    "open_positions": [...],
    "last_orders": [...],
    "errors": [...]
}
```

---

## 14. 로깅 설계

### 카테고리
- `arena.prompt` - 프롬프트 생성/전송
- `arena.response` - LLM 응답 수신
- `arena.model_chat` - MODEL_CHAT 내용 (분리 저장: `arena.model_chat.log`)
- `arena.decision` - TRADING_DECISIONS 파싱 (분리 저장: `arena.decisions.log`)
- `arena.order` - Binance 주문 실행
- `arena.error` - 실행 실패/파싱 실패

### 로그 저장 포맷
- **MODEL_CHAT**: `arena.model_chat.log` 파일에 분리 저장
- **TRADING_DECISIONS**: `arena.decisions.log` 파일에 분리 저장
- UI는 두 패널로 동시 표시 (MODEL_CHAT 패널 + TRADING_DECISIONS 패널)

### 예시
```
[arena.prompt] Generated prompt for tick #123 (length: 8521 chars)
[arena.response] Received response from deepseek-3.1 (length: 3241 chars)
[arena.model_chat] "I'm currently up 29.81% overall, managing profitable ETH, SOL..."
[arena.decision] Parsed 6 decisions: ETH=HOLD, SOL=HOLD, XRP=ENTER_LONG, ...
[arena.order] BTCUSDT ENTER_LONG qty=0.5 executed: orderId=12345678, price=43250.5
[arena.error] XRP TP/SL missing - skipping execution, will retry in next tick
```

---

## 15. 에러 처리

### 프롬프트 생성 실패
- 시장 데이터 조회 실패 → 루프 중단, 에러 로그

### LLM 호출 실패
- 네트워크 오류 → 재시도 (최대 3회)
- API 키 오류 → 설정 창으로 유도
- 응답 형식 오류 → "응답 형식이 올바르지 않습니다" 로그

### TRADING_DECISIONS 파싱 실패
- JSON 파싱 실패 → 다음 틱에서 다시 요청
- 필수 필드 누락 → 누락된 심볼/필드를 프롬프트에 붙여서 재요청
- TP/SL 누락 → 해당 심볼 실행 건너뛰고 다음 틱에 "TP/SL missing" 붙임

### Binance 주문 실패
- MIN_NOTIONAL → 실패 사유를 다음 프롬프트에 붙임
- INSUFFICIENT_BALANCE → 실패 사유를 다음 프롬프트에 붙임
- 기타 오류 → 실패 사유를 다음 프롬프트에 붙임
- **자동 재시도 안 함** (LLM이 다시 말하게 함)

## 15.1 “주문 안 나간” 정상 케이스(혼동 방지)

- LLM이 모든 코인에 `HOLD`만 지시
- `TP/SL` 누락으로 진입이 **의도적으로** 스킵됨
- `minNotional`/정밀도 위반으로 스킵
- `cooldown`/`risk cap`/`max_concurrent_positions` 초과로 스킵

→ 위 상황들은 **오류가 아니며**, 다음 프롬프트의 MODEL_CHAT/결정에서 자연스럽게 조정될 수 있도록 **그 사유를 그대로 첨부**한다.

---

## 16. 보안/프라이버시/면책

- AI의 분석/조언은 참고용, 최종 책임은 사용자에게 있음 (명시)
- API 키/비밀번호 등 민감정보는 엔진에 전달하지 않음
- 외부 엔진 호출 시 프롬프트/출력은 최소한만 저장 (옵트인)

---

## 17. 구현 우선순위

### Phase 1 (MVP)
1. ✅ 프롬프트 빌더 (고정 데이터로 시작)
2. ✅ LLM 호출 (deepseek-3.1)
3. ✅ 응답 파서 (MODEL_CHAT + TRADING_DECISIONS)
4. ✅ Binance 직접 주문 (기존 trader.py 안 거침)
5. ✅ 기본 UI (탭 + 모달)

### Phase 2
- 실제 시장 데이터 수집 연동
- 포지션/계좌 상태 실시간 반영
- 에러 피드백 루프

### Phase 3
- 메트릭/리포트
- 다중 엔진 지원

---

---

## 18. 환경/테스트넷/레이트리밋 가이드
### 18.1 환경 변수/키
- `BINANCE_API_KEY`, `BINANCE_API_SECRET`
- `OPENAI_API_KEY` 또는 `DEEPSEEK_API_KEY`/`QWEN_API_KEY`
- `ARENA_SESSION_ID`
- `TZ` : `Asia/Seoul` 권장

### 18.2 테스트넷 스위치
- 설정 키: `alpha_arena.exchange = "binance-futures-testnet" | "binance-futures"`
- TESTNET 배지/버튼 색상 분리

### 18.3 시간 동기화/레이트리밋
- 서버 시간 오차 ±500ms(5분마다 보정), `recvWindow=5000`
- 틱당 주문 상한: `alpha_arena.max_orders_per_tick`(기본 6)
- 429/418 수신 시 해당 틱 스킵 + 사유 피드백

---

## 19. 프롬프트/토큰 가이드
### 19.1 길이 관리
- 섹션별 최대 항목 수 제한, 숫자 자릿수(가격 2~4, 지표/퍼센트 2)
- 과거 틱 요약(“…omitted N points for brevity”)

### 19.2 일관 정책
- `workingType=MARK_PRICE`를 프롬프트에 명시
- 레버리지 10–20x/TP·SL 필수 규칙 재고지
- 실패/누락 사유 원문 그대로 포함(모델 재지시 유도)

---

## 20. TRADING_DECISIONS JSON 스키마(검증용)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "BTC": { "$ref": "#/$defs/decision" },
    "ETH": { "$ref": "#/$defs/decision" },
    "SOL": { "$ref": "#/$defs/decision" },
    "XRP": { "$ref": "#/$defs/decision" },
    "DOGE": { "$ref": "#/$defs/decision" },
    "BNB": { "$ref": "#/$defs/decision" }
  },
  "required": ["BTC","ETH","SOL","XRP","DOGE","BNB"],
  "$defs": {
    "decision": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "signal": { "enum": ["HOLD","CLOSE","ENTER_LONG","ENTER_SHORT"] },
        "quantity": { "type": "number" },
        "notional_usd": { "type": "number" },
        "profit_target": { "type": "number" },
        "stop_loss": { "type": "number" },
        "invalidation_condition": { "type": "string" },
        "leverage": { "type": "integer", "minimum": 1, "maximum": 125 },
        "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
        "risk_usd": { "type": "number", "minimum": 0 }
      },
      "required": ["signal"],
      "oneOf": [
        { "required": ["quantity"] },
        { "required": ["notional_usd"] }
      ]
    }
  }
}

---

## 21. 정밀도/필터 캐싱(ExchangeInfo)

### 캐시 대상
- `tickSize` (가격 틱 크기)
- `stepSize` (수량 스텝 크기)
- `minQty` (최소 수량)
- `minNotional` (최소 명목금액)
- `pricePrecision` (가격 소수점 자릿수)
- `quantityPrecision` (수량 소수점 자릿수)

### 반올림 규칙
- **가격**: `tickSize` 단위로 반올림
- **수량**: `stepSize` 단위로 반올림 + `minQty` 이상
- **명목금액**: `minNotional` 이상

### 캐시 갱신
- **60분마다 재조회** 후 변경 사항 감지
- 변경 시 알림 로그 기록
- 변경된 필터로 즉시 재검증

---

## 22. 멱등성/중복 방지

### 주문 ID 생성
- `newClientOrderId = "arena:{session_id}:{symbol}:{uuid4}"`
- 예: `arena:20240101_120000:BTCUSDT:a1b2c3d4-e5f6-7890-abcd-ef1234567890`

### 재시도 정책
- **재시도 없음** (중복 방지, 실패 사유만 피드백)
- 주문 실패 시:
  - 실패 사유를 다음 프롬프트에 그대로 첨부
  - LLM이 직접 재지시하도록 유도

### 동일 틱 중복 방지
- **동일 틱·동일 심볼 `ENTER_*` 2건 이상** → **1건만 허용**
- 첫 번째 신호만 실행, 나머지는 무시
- 로그에 "duplicate signal ignored" 기록

---

## 23. 품질체크리스트 (릴리스 전)

### 필수 검증 항목

#### 1. 테스트넷 검증
- [ ] 테스트넷 6심볼: `ENTER` → `TP/SL` → `CLOSE` 정상 작동
- [ ] 모든 신호 타입(`HOLD`, `CLOSE`, `ENTER_LONG`, `ENTER_SHORT`) 정상 처리

#### 2. 정밀도/필터 검증
- [ ] 정밀도/필터 위반 시 스킵 + 사유 피드백 정상 작동
- [ ] `minNotional` 미만 시 주문 차단 확인
- [ ] 가격/수량 반올림 정확성 확인

#### 3. 레버리지/마진 설정
- [ ] 심볼 진입 전 1회 `isolated` + `leverage in [10,20]` 설정 확인
- [ ] 설정 후 유지 확인 (매 틱마다 재설정하지 않음)

#### 4. 로깅/추적
- [ ] `prompt_version`/`hash` 저장/조회 정상 작동
- [ ] 모든 거래소 응답(성공/실패) 로그 기록 확인

#### 5. UI 표시
- [ ] `MODEL_CHAT` 실시간 표시 확인
- [ ] `TRADING_DECISIONS` 요약 표시 확인
- [ ] 거래소 응답 전문 표시 확인

#### 6. 시간동기화/레이트리밋
- [ ] 서버 시간 동기화(±500ms) 정상 작동
- [ ] 레이트리밋 처리(429/418) 정상 작동
- [ ] 틱당 주문 상한(`max_orders_per_tick`) 준수 확인

#### 7. 정상 케이스 UI 고지
- [ ] "주문 안 나감" 정상 케이스 UI 고지 확인
  - `HOLD` 신호만 있는 경우
  - `TP/SL` 누락으로 스킵된 경우
  - `minNotional`/정밀도 위반으로 스킵된 경우
  - `cooldown`/`risk cap`/`max_concurrent_positions` 초과로 스킵된 경우

---

본 문서는 기능 설계를 위한 기준점이며, 구현 단계에서 변경될 수 있습니다. 구현 전 추가 검토/보안 리뷰/법적 검토가 필요합니다.
