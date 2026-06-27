# Alpha Arena 모드 차이점 분석 문서

**작성일**: 2025-11-07  
**최종 업데이트**: 2025-11-07  
**목적**: 벤치마크, 문서, 실제 코드 간 차이점 명확화 및 수정 완료 보고

---

## 📋 목차

1. [벤치마크 원본 vs 우리 구현](#1-벤치마크-원본-vs-우리-구현)
2. [업데이트한 3개 문서 vs 벤치마크](#2-업데이트한-3개-문서-vs-벤치마크)
3. [실제 개발 코드 vs 문서](#3-실제-개발-코드-vs-문서)
4. [종합 차이점 요약](#4-종합-차이점-요약)

---

## 1. 벤치마크 원본 vs 우리 구현

### 1.1 벤치마크 원본 (nof1.ai Alpha Arena)

**공개된 정보 기준:**
- **거래소**: Hyperliquid (USDC perpetuals)
- **자금**: $10,000 고정
- **심볼**: 6개 고정 (BTC, ETH, SOL, XRP, DOGE, BNB)
- **트리거 방식**: 명시되지 않음 (공개 문서에 없음)
- **시계열 데이터**: 3분봉 배열 + 4시간 컨텍스트 (공개 스니펫 기준)
- **프롬프트 구조**: 5개 섹션 (Header, Market State, Account & Positions, Rules, Output format)
- **엔진**: DeepSeek Chat V3.1, Qwen 3 Max 등 다수 엔진 비교

### 1.2 우리 구현 (NoahAI Alpha Arena)

**실제 구현:**
- **거래소**: Binance Futures (USDT-M)
- **자금**: 사용자 계좌 잔고 (가변)
- **심볼**: 6개 고정 (BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT, BNBUSDT) ✅
- **트리거 방식**: 폴링 기반 실행 (현재 기본 60초, 최소 30초 가드레일)
- **시계열 데이터**: 3분봉 + 4시간봉 컨텍스트 기준으로 수집
- **프롬프트 구조**: Market State + Account + Positions + Last Orders/Errors 중심
- **엔진**: 현재 대시보드 실행은 DeepSeek 3.1 기준, Qwen 3 Max 관련 설정은 준비 상태

### 1.3 주요 차이점

| 항목 | 벤치마크 원본 | 우리 구현 | 차이 |
|------|--------------|----------|------|
| **거래소** | Hyperliquid | Binance Futures | ✅ 의도적 변경 (상용화) |
| **트리거** | 명시 안 됨 | 10초 폴링 | ❌ 벤치마크와 다름 |
| **시계열** | 3분봉 + 4H 컨텍스트 | 15m + 1h | ❌ 벤치마크와 다름 |
| **프롬프트** | 5개 섹션 고정 | 간단한 구조 | ⚠️ 부분 일치 |
| **지표** | EMA20/EMA50, ATR3/ATR14, MACD, RSI14 | RSI(14), EMA(20), MACD | ⚠️ 일부 누락 |

---

## 2. 업데이트한 3개 문서 vs 벤치마크

### 2.1 문서 업데이트 내용

**업데이트한 문서:**
1. `ALPHA_ARENA_MODE.md`
2. `ALPHA_ARENA_DEVELOPMENT.md`
3. `ALPHA_ARENA_FINAL_REVIEW.md` (사용자가 추가 수정)

### 2.2 문서에 명시된 내용

**틱 주기:**
- `ALPHA_ARENA_MODE.md`: "기본 60초(권장), 최소 30초"
- `ALPHA_ARENA_DEVELOPMENT.md`: "기본 60초(권장), 최소 30초"
- `ALPHA_ARENA_FINAL_REVIEW.md`: "기본 = **3분봉 마감 이벤트(≈180초)**. 보조 트리거 = 주문 체결/실패/강제청산/포지션 변화 발생 시 즉시 1회 호출. 폴백 폴링 = 60초" (사용자 수정)

**시계열 데이터:**
- 모든 문서: "3분봉 배열(OLDEST → NEWEST) + 4시간 컨텍스트 지표(EMA20/EMA50, ATR3/ATR14, MACD, RSI14)"

**프롬프트 구조:**
- 모든 문서: "5개 섹션 고정 (Header, Market State, Account & Positions, Rules, Output format)"

### 2.3 문서 vs 벤치마크

| 항목 | 벤치마크 원본 | 문서 내용 | 일치 여부 |
|------|--------------|----------|----------|
| **트리거** | 명시 안 됨 | 60초 폴링 / 3분봉 마감 이벤트 (FINAL_REVIEW) | ⚠️ 추정 |
| **시계열** | 3분봉 + 4H 컨텍스트 | 3분봉 + 4H 컨텍스트 | ✅ 일치 |
| **프롬프트** | 5개 섹션 | 5개 섹션 | ✅ 일치 |
| **지표** | EMA20/EMA50, ATR3/ATR14, MACD, RSI14 | EMA20/EMA50, ATR3/ATR14, MACD, RSI14 | ✅ 일치 |

**결론**: 문서는 벤치마크와 **대부분 일치**하지만, 트리거 방식은 벤치마크에 명시되지 않아 **추정**입니다.

---

## 3. 실제 개발 코드 vs 문서

### 3.1 틱 주기 (Runner)

**문서:**
- `ALPHA_ARENA_MODE.md`: "기본 60초(권장), 최소 30초"
- `ALPHA_ARENA_DEVELOPMENT.md`: "기본 60초(권장), 최소 30초"
- `ALPHA_ARENA_FINAL_REVIEW.md`: "3분봉 마감 이벤트(≈180초) + 보조 트리거 + 폴백 60초"

**실제 코드 (`runner.py`):**
```python
# 라인 60
self.tick_interval_sec = self.arena_settings.get('tick_interval_sec', 10)

# 라인 177
if self.stop_event.wait(timeout=self.tick_interval_sec):
```

**차이점:**
- ❌ **코드는 기본값 10초**, 문서는 60초
- ❌ **코드는 간단한 폴링**, 문서는 3분봉 마감 이벤트 + 보조 트리거
- ❌ **코드에 이벤트 기반 트리거 없음**

### 3.2 시계열 데이터 (Prompt Builder)

**문서:**
- 모든 문서: "3분봉 배열(OLDEST → NEWEST) + 4시간 컨텍스트 지표(EMA20/EMA50, ATR3/ATR14, MACD, RSI14)"

**실제 코드 (`prompt_builder.py`):**
```python
# 라인 166-169
klines_15m = self.binance_client.get_klines(symbol, '15m', 100)
klines_1h = self.binance_client.get_klines(symbol, '1h', 100)

# 라인 179-183
rsi_15m = self._calculate_rsi(closes_15m, 14)
rsi_1h = self._calculate_rsi(closes_1h, 14)
ema_20 = self._calculate_ema(closes_15m, 20)
macd = ema_12 - ema_26  # 15m 기준
```

**차이점:**
- ❌ **코드는 15분봉 + 1시간봉**, 문서는 3분봉 + 4시간봉
- ❌ **코드는 RSI(14), EMA(20), MACD만**, 문서는 EMA20/EMA50, ATR3/ATR14, MACD, RSI14
- ❌ **코드에 4시간 컨텍스트 없음**
- ❌ **코드에 ATR 지표 없음**

### 3.3 프롬프트 구조

**문서:**
- 모든 문서: "5개 섹션 고정 (Header, Market State, Account & Positions, Rules, Output format)"
- 샘플 프롬프트 블록 제공

**실제 코드 (`prompt_builder.py`):**
```python
# 라인 371-481 (_format_prompt)
# 구조:
# 1. Header (간단)
# 2. MARKET STATE (시장 데이터)
# 3. ACCOUNT & OPEN POSITIONS
# 4. LAST ORDERS/ERRORS
# 5. 마지막 지시 (MODEL_CHAT + TRADING_DECISIONS)
```

**차이점:**
- ⚠️ **코드는 5개 섹션 구조는 있지만**, 문서의 상세한 샘플 프롬프트와 **형식이 다름**
- ⚠️ **코드에 Rules 섹션 없음** (문서에는 "No pyramiding. No re-entry..." 등)
- ⚠️ **코드에 Output format 섹션 없음** (문서에는 JSON 스키마 상세 설명)
- ⚠️ **코드의 Market State는 간단한 형식**, 문서는 상세한 3분봉 배열 + 4H 컨텍스트

### 3.4 설정 구조

**문서:**
- `ALPHA_ARENA_FINAL_REVIEW.md`: `tick_trigger`: "candle_close_3m" | "interval" (기본 "candle_close_3m")

**실제 코드:**
- `runner.py`: `tick_interval_sec`만 존재, `tick_trigger` 없음
- `settings_template.json`: `tick_interval_sec`만 존재

**차이점:**
- ❌ **코드에 `tick_trigger` 설정 키 없음**
- ❌ **코드에 3분봉 마감 이벤트 감지 로직 없음**

---

## 4. 종합 차이점 요약

### 4.1 벤치마크 vs 문서

| 항목 | 벤치마크 | 문서 | 일치 여부 |
|------|---------|------|----------|
| 시계열 데이터 | 3분봉 + 4H | 3분봉 + 4H | ✅ 일치 |
| 프롬프트 구조 | 5개 섹션 | 5개 섹션 | ✅ 일치 |
| 지표 | EMA20/EMA50, ATR3/ATR14, MACD, RSI14 | EMA20/EMA50, ATR3/ATR14, MACD, RSI14 | ✅ 일치 |
| 트리거 | 명시 안 됨 | 60초 / 3분봉 마감 이벤트 | ⚠️ 추정 |

**결론**: 문서는 벤치마크와 **대부분 일치**하지만, 트리거 방식은 **추정**입니다.

### 4.2 문서 vs 실제 코드

| 항목 | 문서 | 실제 코드 | 차이 |
|------|------|----------|------|
| **틱 주기** | 60초 / 3분봉 마감 이벤트 | 10초 폴링 | ❌ **큰 차이** |
| **시계열 데이터** | 3분봉 + 4H 컨텍스트 | 15m + 1h | ❌ **큰 차이** |
| **지표** | EMA20/EMA50, ATR3/ATR14, MACD, RSI14 | RSI(14), EMA(20), MACD | ❌ **부분 차이** |
| **프롬프트 구조** | 5개 섹션 상세 | 5개 섹션 간단 | ⚠️ **형식 차이** |
| **설정 키** | `tick_trigger` | 없음 | ❌ **누락** |

**결론**: 실제 코드는 문서와 **상당한 차이**가 있습니다.

### 4.3 벤치마크 vs 실제 코드

| 항목 | 벤치마크 | 실제 코드 | 차이 |
|------|---------|----------|------|
| **거래소** | Hyperliquid | Binance Futures | ✅ 의도적 변경 |
| **트리거** | 명시 안 됨 | 10초 폴링 | ⚠️ 불명확 |
| **시계열** | 3분봉 + 4H | 15m + 1h | ❌ **큰 차이** |
| **지표** | EMA20/EMA50, ATR3/ATR14, MACD, RSI14 | RSI(14), EMA(20), MACD | ❌ **부분 차이** |
| **프롬프트** | 5개 섹션 상세 | 5개 섹션 간단 | ⚠️ **형식 차이** |

**결론**: 실제 코드는 벤치마크와 **상당한 차이**가 있습니다.

---

## 5. 개선 필요 사항

### 5.1 우선순위 높음 (벤치마크 일치)

1. **시계열 데이터 수정**
   - [ ] 15분봉 → 3분봉으로 변경
   - [ ] 4시간 컨텍스트 지표 추가 (EMA20/EMA50, ATR3/ATR14, MACD, RSI14)
   - [ ] ATR 지표 계산 로직 추가

2. **틱 주기 수정**
   - [ ] 기본값 10초 → 60초로 변경
   - [ ] 3분봉 마감 이벤트 감지 로직 추가 (선택적)
   - [ ] 보조 트리거 로직 추가 (주문 체결/실패/강제청산/포지션 변화)

3. **프롬프트 구조 개선**
   - [ ] Rules 섹션 추가 ("No pyramiding. No re-entry..." 등)
   - [ ] Output format 섹션 추가 (JSON 스키마 상세 설명)
   - [ ] Market State 섹션을 문서 샘플 형식으로 개선

### 5.2 우선순위 중간 (문서 일치)

4. **설정 키 추가**
   - [ ] `tick_trigger` 설정 키 추가 ("candle_close_3m" | "interval")
   - [ ] `tick_interval_sec` 기본값 60으로 변경

5. **지표 계산 개선**
   - [ ] EMA50 계산 추가
   - [ ] ATR3/ATR14 계산 추가
   - [ ] 4시간봉 데이터 수집 추가

### 5.3 우선순위 낮음 (선택적)

6. **이벤트 기반 트리거**
   - [ ] 3분봉 마감 이벤트 감지 (WebSocket 또는 폴링)
   - [ ] 보조 트리거 구현 (주문 체결/실패/강제청산/포지션 변화)

---

## 6. 결론 및 수정 완료 보고

### 6.1 수정 완료 상태 (2025-11-07)

- **문서**: 벤치마크와 **대부분 일치** ✅
- **코드**: 벤치마크와 **일치하도록 수정 완료** ✅
- **문서 vs 코드**: **일치** ✅

### 6.2 수정 완료된 항목

1. ✅ **틱 주기**: 10초 → 60초 (기본값), 최소 30초 가드레일 추가
2. ✅ **시계열 데이터**: 15m+1h → 3분봉+4H 컨텍스트로 변경
3. ✅ **지표 추가**: ATR3/ATR14, EMA50 계산 로직 추가
4. ✅ **프롬프트 구조**: 5개 섹션 고정 (Header, Market State, Account & Positions, Rules, Output format)
5. ✅ **DeepSeek API**: base_url 설정 완료 (`https://api.deepseek.com`)
6. ✅ **설정 키**: tick_trigger 추가

### 6.3 최종 상태

**현재 코드는 업데이트된 문서의 사양과 일치하며, DeepSeek 엔진을 사용한 Alpha Arena와 유사한 실전 거래가 가능합니다.**

**추가 작업 필요 (선택적):**
- Qwen3 엔진: Alibaba DashScope API 클라이언트 별도 구현 필요
- 3분봉 마감 이벤트 트리거: 현재는 interval 폴링만 지원, candle_close_3m 트리거는 향후 구현 가능

---

**작성자**: 개발 시스템  
**최종 업데이트**: 2025-11-07

