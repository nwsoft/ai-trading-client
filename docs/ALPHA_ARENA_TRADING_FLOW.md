# Alpha Arena 모드 거래 흐름 상세 분석

**작성일**: 2025-11-07  
**목적**: Alpha Arena 모드의 실제 거래 실행 흐름을 코드 기반으로 상세 분석

---

## 📋 목차

1. [전체 거래 흐름 개요](#1-전체-거래-흐름-개요)
2. [단계별 상세 분석](#2-단계별-상세-분석)
3. [Alpha Arena와의 동일성 확인](#3-alpha-arena와의-동일성-확인)
4. [실제 거래 실행 확인](#4-실제-거래-실행-확인)

---

## 1. 전체 거래 흐름 개요

```
[60초 주기 루프]
    ↓
[1. 프롬프트 생성]
    ├─ 시장 데이터 수집 (6개 코인)
    │   ├─ 3분봉 배열 (OLDEST → NEWEST, 최근 200개)
    │   ├─ 4H 컨텍스트 지표 (EMA20/EMA50, ATR3/ATR14, MACD, RSI14)
    │   └─ 현재가, Funding Rate, Open Interest 등
    ├─ 계좌 정보 수집 (잔고, 미실현 PnL)
    ├─ 포지션 정보 수집 (현재 보유 포지션)
    └─ 프롬프트 포맷팅 (5개 섹션: Header, Market State, Account & Positions, Rules, Output format)
    ↓
[2. LLM 호출]
    ├─ DeepSeek API 호출 (base_url: https://api.deepseek.com)
    ├─ 모델: deepseek-chat
    └─ 응답 수신 (MODEL_CHAT + TRADING_DECISIONS)
    ↓
[3. 응답 파싱]
    ├─ MODEL_CHAT 추출 (사람이 읽는 설명)
    ├─ TRADING_DECISIONS JSON 파싱
    └─ 검증 (신호, TP/SL 필수, 수량, 레버리지 등)
    ↓
[4. 주문 실행]
    ├─ 각 심볼별 거래 결정 실행
    │   ├─ 게이트 검증 (TP/SL 필수, 쿨다운, 리스크 캡 등)
    │   ├─ 진입 주문 (ENTER_LONG/ENTER_SHORT)
    │   │   ├─ 레버리지 설정 (10-20x 범위)
    │   │   ├─ 수량 계산 및 정밀도 반올림
    │   │   ├─ 시장가 주문 실행
    │   │   └─ TP/SL 주문 생성 (TAKE_PROFIT_MARKET, STOP_MARKET)
    │   └─ 청산 주문 (CLOSE)
    └─ 주문 결과 피드백 (다음 프롬프트에 반영)
    ↓
[5. 피드백 루프]
    └─ 주문 성공/실패 사유를 다음 프롬프트에 포함
```

---

## 2. 단계별 상세 분석

### 2.1 프롬프트 생성 (`prompt_builder.py`)

**파일**: `trading/alpha_arena/prompt_builder.py`

**주요 메서드**:
- `build_prompt()`: 전체 프롬프트 생성
- `collect_market_data()`: 시장 데이터 수집
- `_calculate_indicators()`: 지표 계산 (3분봉 + 4H)
- `_format_prompt()`: 프롬프트 포맷팅

**수집 데이터**:
1. **3분봉 데이터** (최근 200개, OLDEST → NEWEST):
   - 캔들 배열: `[{time, open, high, low, close, volume}, ...]`
   - 지표: RSI14, EMA20, EMA50, MACD

2. **4H 컨텍스트 지표**:
   - EMA20 vs EMA50
   - ATR3 vs ATR14
   - MACD(4H)
   - RSI14(4H)

3. **계좌 정보**:
   - Wallet Balance, Available Balance
   - Unrealized PnL, Total Balance

4. **포지션 정보**:
   - 각 심볼별 포지션 (LONG/SHORT)
   - Entry Price, Current Price, PnL, Leverage

5. **피드백 정보**:
   - 최근 주문 결과 (성공/실패)
   - 최근 에러 메시지

**프롬프트 구조** (5개 섹션 고정):
1. **Header**: 세션 정보, 경과 시간, 현재 시간
2. **Market State**: 6개 코인별 시장 데이터 (3분봉 배열 + 4H 컨텍스트)
3. **Account & Positions**: 계좌 정보 및 현재 포지션
4. **Rules**: 거래 규칙 (Pyramiding 금지, 재진입 금지, TP/SL 필수 등)
5. **Output Format**: MODEL_CHAT + TRADING_DECISIONS JSON 형식

---

### 2.2 LLM 호출 (`runner.py`)

**파일**: `trading/alpha_arena/runner.py`

**주요 메서드**:
- `_call_llm()`: LLM API 호출

**호출 과정**:
1. **엔진 선택**: 설정에서 `engine` 값 확인
   - `deepseek-3.1` → `deepseek-chat` 모델명 매핑
   - `qwen3-max` → `qwen-plus` 모델명 매핑 (현재 미지원)

2. **API 호출**:
   - DeepSeek: `base_url='https://api.deepseek.com'` 설정
   - OpenAI 호환 API 사용
   - 시스템 프롬프트 + 사용자 프롬프트 전송

3. **응답 수신**:
   - MODEL_CHAT (사람이 읽는 설명)
   - TRADING_DECISIONS (실행 가능한 JSON)

**코드 위치**:
```python
# runner.py:292-298
response = self.ai_manager.client.chat(
    system_prompt=system_prompt,
    user_prompt=prompt,
    model=use_model,  # 'deepseek-chat'
    temperature=0.3,
    max_tokens=4000
)
```

---

### 2.3 응답 파싱 (`response_parser.py`)

**파일**: `trading/alpha_arena/response_parser.py`

**주요 메서드**:
- `parse_response()`: 전체 응답 파싱
- `_extract_model_chat()`: MODEL_CHAT 추출
- `_extract_trading_decisions()`: TRADING_DECISIONS JSON 파싱

**파싱 과정**:
1. **MODEL_CHAT 추출**:
   - "MODEL_CHAT" 또는 "Model Chat" 패턴 찾기
   - TRADING_DECISIONS 이전의 모든 텍스트 추출

2. **TRADING_DECISIONS 파싱**:
   - JSON 블록 찾기 (```json``` 또는 `{...}`)
   - 각 심볼별 검증:
     - 신호 검증: `HOLD`, `CLOSE`, `ENTER_LONG`, `ENTER_SHORT`만 허용
     - TP/SL 필수 검증: `ENTER_*` 신호는 `profit_target`, `stop_loss` 필수
     - 수량 검증: `quantity` 또는 `notional_usd` 중 하나 필수
     - 레버리지 검증: 1-125 범위 (실제 실행 시 10-20으로 클램핑)

**검증 실패 시**:
- TP/SL 누락: `error: 'TP/SL 누락'` 플래그 설정, 주문 실행 안 함
- 기타 오류: `parse_errors` 리스트에 추가

---

### 2.4 주문 실행 (`order_executor.py`)

**파일**: `trading/alpha_arena/order_executor.py`

**주요 메서드**:
- `execute_trading_decision()`: 거래 결정 실행
- `_check_trade_gates()`: 게이트 검증
- `_execute_enter_order()`: 진입 주문 실행
- `_execute_close_order()`: 청산 주문 실행
- `_create_tp_order()`: TP 주문 생성
- `_create_sl_order()`: SL 주문 생성

**실행 과정**:

#### 2.4.1 게이트 검증 (`_check_trade_gates`)

**검증 항목**:
1. **신호 검증**: `ENTER_LONG` 또는 `ENTER_SHORT`만 허용
2. **TP/SL 필수**: `profit_target`, `stop_loss` 필수 (없으면 실행 안 함)
3. **레버리지 범위**: 10-20x 범위 (벗어나면 클램핑, 경고만)
4. **리스크 캡**: 틱당 최대 리스크 제한 (기본 1500 USDT)
5. **쿨다운**: 동일 코인 재진입 최소 30초 간격
6. **최대 동시 포지션**: 6개 코인 (심볼당 1개)

**검증 실패 시**:
- `{'allowed': False, 'reason': '...'}` 반환
- 주문 실행 안 함, 스킵 사유를 피드백에 포함

#### 2.4.2 진입 주문 실행 (`_execute_enter_order`)

**실행 순서**:
1. **게이트 검증**: `_check_trade_gates()` 호출
2. **레버리지 설정**: `_ensure_leverage_and_margin()` 호출
   - 심볼별 레버리지 캐시 확인
   - 설정되지 않았으면 Binance API로 설정
3. **수량 계산**:
   - `quantity` 또는 `notional_usd` 중 하나 사용
   - `notional_usd`가 있으면 현재가로 나누어 수량 계산
4. **정밀도 반올림**:
   - `_round_quantity()`: `stepSize` 기준 반올림
   - `_round_price()`: `tickSize` 기준 반올림
5. **minNotional 검증**: 최소 명목가 검증
6. **시장가 주문 실행**:
   ```python
   order_result = self.binance_client.place_futures_order(
       symbol=symbol,
       side=side,  # 'BUY' or 'SELL'
       order_type='MARKET',
       quantity=quantity
   )
   ```
7. **TP/SL 주문 생성**:
   - `_create_tp_order()`: `TAKE_PROFIT_MARKET` 주문
   - `_create_sl_order()`: `STOP_MARKET` 주문
   - `workingType=MARK_PRICE` 사용

#### 2.4.3 청산 주문 실행 (`_execute_close_order`)

**실행 순서**:
1. **포지션 확인**: 현재 포지션 수량 확인
2. **시장가 청산**:
   ```python
   order_result = self.binance_client.place_futures_order(
       symbol=symbol,
       side=side,  # 포지션 반대 방향
       order_type='MARKET',
       close_position=True  # 전량 청산
   )
   ```

#### 2.4.4 TP/SL 주문 생성

**TP 주문** (`_create_tp_order`):
- 주문 타입: `TAKE_PROFIT_MARKET`
- `workingType`: `MARK_PRICE`
- `stopPrice`: `profit_target` 값

**SL 주문** (`_create_sl_order`):
- 주문 타입: `STOP_MARKET`
- `workingType`: `MARK_PRICE`
- `stopPrice`: `stop_loss` 값

---

### 2.5 피드백 루프 (`runner.py`)

**파일**: `trading/alpha_arena/runner.py`

**피드백 과정**:
1. **주문 결과 수집**:
   - 성공/실패 여부
   - 주문 ID
   - 스킵 사유 (게이트 검증 실패 시)

2. **에러 수집**:
   - 주문 실행 오류
   - 파싱 오류

3. **프롬프트 빌더에 추가**:
   - `prompt_builder.add_order_result()`: 주문 결과 추가
   - `prompt_builder.add_error()`: 에러 추가

4. **다음 프롬프트에 반영**:
   - `_format_prompt()`에서 "Recent Orders/Errors" 섹션에 포함
   - LLM이 실패 사유를 읽고 재조정

---

## 3. Alpha Arena와의 동일성 확인

### 3.1 프롬프트 구조

**Alpha Arena 벤치마크**:
- 5개 섹션 고정 (Header, Market State, Account & Positions, Rules, Output format)
- 3분봉 배열 (OLDEST → NEWEST)
- 4H 컨텍스트 지표 (EMA20/EMA50, ATR3/ATR14, MACD, RSI14)

**우리 구현**:
- ✅ 5개 섹션 고정 구조 동일
- ✅ 3분봉 배열 (OLDEST → NEWEST) 동일
- ✅ 4H 컨텍스트 지표 동일

### 3.2 거래 실행 방식

**Alpha Arena 벤치마크**:
- LLM이 `TRADING_DECISIONS` JSON 제공
- 클라이언트가 JSON만 파싱하여 주문 실행
- TP/SL 필수, 없으면 실행 안 함

**우리 구현**:
- ✅ `TRADING_DECISIONS` JSON 파싱 동일
- ✅ TP/SL 필수 검증 동일
- ✅ TP/SL 없으면 실행 안 함 동일

### 3.3 주문 매핑

**Alpha Arena 벤치마크**:
- `ENTER_LONG` → `FUTURES MARKET BUY`
- `ENTER_SHORT` → `FUTURES MARKET SELL`
- TP → `TAKE_PROFIT_MARKET` (workingType=MARK_PRICE)
- SL → `STOP_MARKET` (workingType=MARK_PRICE)

**우리 구현**:
- ✅ `ENTER_LONG` → `MARKET BUY` 동일
- ✅ `ENTER_SHORT` → `MARKET SELL` 동일
- ✅ TP → `TAKE_PROFIT_MARKET` 동일
- ✅ SL → `STOP_MARKET` 동일
- ✅ `workingType=MARK_PRICE` 사용 (Binance API 기본값)

### 3.4 가드레일

**Alpha Arena 벤치마크**:
- 레버리지 범위: 10-20x
- 쿨다운: 30초
- Pyramiding 금지
- 보유 코인 재진입 금지

**우리 구현**:
- ✅ 레버리지 범위: 10-20x 동일
- ✅ 쿨다운: 30초 동일
- ✅ Pyramiding 금지 (Rules 섹션에 명시)
- ✅ 보유 코인 재진입 금지 (Rules 섹션에 명시)

---

## 4. 실제 거래 실행 확인

### 4.1 거래 실행 가능 여부

**✅ 실제 거래 가능**:
- `order_executor.py`의 `execute_trading_decision()` 메서드가 실제 Binance Futures API를 호출합니다.
- `binance_client.place_futures_order()` 메서드를 통해 실제 주문이 실행됩니다.

**실행 흐름**:
1. LLM이 `TRADING_DECISIONS` JSON 제공
2. `response_parser.py`가 JSON 파싱 및 검증
3. `order_executor.py`가 게이트 검증 및 주문 실행
4. Binance API로 실제 주문 전송
5. 주문 결과를 피드백 루프에 반영

### 4.2 Alpha Arena와의 차이점

**거래소 차이**:
- Alpha Arena: Hyperliquid (USDC perpetuals)
- 우리 구현: Binance Futures (USDT-M)

**의도적 차이**:
- 거래소는 상용화 목적으로 Binance로 변경
- 프롬프트 구조, 지표, 주문 매핑은 벤치마크와 동일

**결론**:
- ✅ **프롬프트 구조 동일**: 5개 섹션, 3분봉+4H 컨텍스트
- ✅ **지표 동일**: EMA20/EMA50, ATR3/ATR14, MACD, RSI14
- ✅ **주문 매핑 동일**: ENTER_LONG/ENTER_SHORT → MARKET, TP/SL → TAKE_PROFIT_MARKET/STOP_MARKET
- ✅ **가드레일 동일**: 레버리지 범위, 쿨다운, Pyramiding 금지 등
- ⚠️ **거래소 차이**: Hyperliquid → Binance Futures (의도적 변경)

**따라서, Alpha Arena 벤치마크와 "유사한" 거래가 가능하며, 프롬프트 구조와 주문 실행 방식은 동일합니다.**

---

## 5. 결론

**Alpha Arena 모드는 실제로 거래가 가능하며, 벤치마크와 동일한 프롬프트 구조와 주문 실행 방식을 사용합니다.**

**주요 확인 사항**:
1. ✅ 프롬프트 생성: 3분봉+4H 컨텍스트, 5개 섹션 구조
2. ✅ LLM 호출: DeepSeek API 정상 작동
3. ✅ 응답 파싱: MODEL_CHAT + TRADING_DECISIONS 분리 파싱
4. ✅ 주문 실행: 실제 Binance Futures API 호출
5. ✅ 피드백 루프: 주문 결과를 다음 프롬프트에 반영

**차이점**:
- 거래소: Hyperliquid → Binance Futures (의도적 변경)
- 트리거: 벤치마크는 명시 안 됨, 우리는 60초 폴링 (기본값)

**결론**: Alpha Arena 벤치마크와 "유사한" 거래가 가능하며, 프롬프트 구조와 주문 실행 방식은 동일합니다.

---

**작성자**: 개발 시스템  
**최종 업데이트**: 2025-11-07

