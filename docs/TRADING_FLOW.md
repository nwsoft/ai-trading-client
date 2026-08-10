# 거래 흐름 기술 문서 (Technical Specification)

**작성일:** 2026년 4월 27일  
**최신 동기화:** 2026-07-29 · v3.9.0.4  
**목적:** 개발팀이 참고하는 기술 명세서 - 코드 경로, 데이터 흐름, 모듈 구조

> 코인 재선택·거래 실행·TP/SL 흐름의 현행 정본입니다. 2026-01 시점 재선택 분석과 테스트 설명은 `docs/archive/coin/`에 보관합니다. 금융 인텔리전스는 거래 실행을 대체하지 않으며, 분석 결과를 사용자에게 설명하는 별도 계층입니다.

## v3.9.0.4 실행 모드 단일 계약

- `LEARNING`: 선택 거래소의 시세 수집·분석·AI 학습만 수행하고 신규 주문은 제출하지 않습니다.
- `PAPER`: 실시간 시세·분석·전략·가드레일을 수행한 뒤 내부 가상 주문·가상 포지션·가상 통계만 갱신합니다. 실계좌 포지션 복구, 주문, TP/SL 보호주문, 실거래 DB/KPI 기록은 수행하지 않습니다.
- `LIVE`: `실제 주문 실행 거래소` 또는 증권 실주문 허용 범위에 포함된 경로만 실제 주문을 제출합니다.
- 전역 `paper_trading=true`는 개별 LIVE 설정보다 항상 우선합니다. 따라서 선택된 거래소에서 하단 실주문 범위를 선택하지 않아도 페이퍼 루프는 실행됩니다.
- 설정의 위쪽 거래소 선택은 데이터 수집·분석·학습 범위이고, 아래쪽 `실제 주문 실행 거래소`는 `LIVE` 주문 권한 범위입니다.

---

## v3.9.0.4 SelectionPolicy·StrategyUniversePolicy·ExitPolicy 계약

```text
대상별 지원 심볼·거래 가능·유동성·스프레드·데이터 품질
  ├─ 일반: 사용자 고정 + NoahAI 자동 후보 → 기본 AI → 커스텀 confirm
  └─ 고급: 사용자 고정 + StrategyUniversePolicy → 로컬 필터·지표 → 커스텀 independent
  → TradeCandidate
  → ExitPolicy
     ├─ 저장된 기본 폴백
     ├─ 현재 종목 적용값·근거
     └─ 실제 보험 주문 제출값·상태
  → 계좌·주문 안전
  → 동일 기회 그룹 → parallel / split / best
  → LEARNING / PAPER / LIVE
```

- AI 커스텀의 `exchange:*`, `broker:*`, `asset:*`는 적용 범위다. 일반 유니버스는 `SelectionPolicy`, 고급 유니버스는 `StrategyUniversePolicy`의 책임이다.
- 일반은 사용자 고정 종목 뒤에 NoahAI 자동 후보를 채운다. 고급은 포함/제외·거래대금·스프레드·변동성·최대 후보 수를 로컬에서 적용한다.
- 전략 국면 범위는 `market/symbol/both/none`이며 기본값은 `market`이다. 선택 범위 데이터가 없으면 암묵 폴백하지 않는다.
- 모든 거래소/증권사 범위도 각 대상의 지원 심볼·시세·계좌·주문 규격을 독립 유지한다.
- 다중 실제 주문 대상의 기본 `parallel`은 각 대상 실행이다. `split`과 `best`는 사용자 선택이며, 동일 대상·계좌·신호만 중복 차단한다.
- `ExitPolicy` 내부 단위는 fraction이다. 주식 설정의 퍼센트 포인트는 실행 경계에서 한 번만 변환한다.
- Binance는 실제 조회한 보험 주문 가격을, Unified 선물은 어댑터 제출값을 기록한다. 현물·증권처럼 서버 보험 주문이 없는 경로는 미제출 상태를 기록하고 클라이언트 모니터 청산을 사용한다.

---

## v3.9.0.2 AI 커스텀·어시스턴트 선행 흐름

```text
전략 소스
  → 근거·진입/청산 규칙·명시 국면·제외 국면 추출
  → 지원 DSL 검사(미지원 필드·연산자 승인 차단)
  → XAI와 추천 적용 범위 표시
  → 사용자 검토·승인·자동 과거재생
     (비중첩 포지션 + 양쪽 수수료·슬리피지·스프레드)
  → 현재 시장국면과 전략 범위 비교
  → 국면 판단 시각·신뢰도·현재/후보 상태 확인, 오래된 입력 차단·전환 히스테리시스
  → 기존 전략 엔진·수익성·리스크·주문 가드레일
  → 주문 후보 또는 HOLD/차단
  → 코인 진입 버전의 명시 청산 규칙을 포지션 모니터에 보존
```

- 상승장 영상이라고 해서 현재 시장을 상승장으로 간주하지 않는다. 영상의 적용 범위와 실시간 시장 판정은 분리한다.
- 소스에 국면 근거가 없으면 특정 국면을 추정하지 않고 사용자 확인을 요구한다.
- AI 어시스턴트의 설정 변경은 `현재값 조회 → 의도 확인/재질문 → 변경안 설명 → 사용자 확인 → 허용 설정 저장 → 재조회 검증` 순서다.
- 주문·시작·정지 요청은 v3.9.0.2 채팅 실행 대상이 아니며 기존 거래 화면과 가드레일을 사용한다.
- AI 커스텀 지표는 자동검증과 Analyzer가 같은 정의를 사용한다. 코인 명시 청산은 Binance/Unified 모니터에 연결되고 주식/ETF 명시 청산은 증권사별 후속 검증 범위다.

## 📊 전체 거래 흐름도 (기술 수준)

```
┌─────────────────────────────────────────────────────┐
│ UI Layer: dashboard_modern.py                        │
│ - switch_service() → 암호화폐/주식 서비스 선택       │
│ - on_start_exchange() → trading_loop 시작             │
└────────────┬────────────────────────────────────────┘
             │
    ┌────────┴────────┐
    ▼                 ▼
┌──────────────┐  ┌──────────────┐
│ 바이낸스 경로 │  │ CCXT 경로     │
│ (trader.py)  │  │ (unified_    │
│              │  │  trader.py)  │
└──────┬───────┘  └───────┬──────┘
       │                  │
       └────────┬─────────┘
                ▼
        ┌──────────────────┐
        │ 1. 코인/종목 선택 │ (selected_coins 리스트)
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │ 2. 신호 분석     │ (analyzer.generate_trading_signal)
        │ - 30개+ 기술지표 │
        │ - 로컬 신호 선판정│
        │ - 이벤트 시 AI   │
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │ 3. AI 검증       │ (pre_entry_analysis)
        │ - 리스크 체크    │
        │ - 패턴 유사성    │
        │ - 신뢰도 계산    │
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │ 4. 포지션 사이징 │ (calculate_position_size)
        │ - 신뢰도 팩터   │
        │ - 변동성 팩터   │
        │ - 레버리지 제약  │
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │ 5. 주문 실행     │ (place_futures_order)
        │ - 시장가 주문    │
        │ - 체결 대기      │
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │ 6. TP/SL 설정    │ (place_tp_sl_orders)
        │ - 동적 임계값 ×  │
        │   변동성 배수    │
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │ 7. 포지션 모니터 │ (_monitor_positions)
        │ - 30초마다 PnL   │
        │ - 실시간 청산    │
        │ - AI 판단 청산   │
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │ 8. 거래 종료     │ (log_trade_exit)
        │ - DB 기록        │
        │ - 학습 데이터    │
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │ 9. AI 학습       │ (ExchangeLearning
        │ - 신호 기록      │  Manager)
        │ - 신호 기준 조정 │
        └──────────────────┘
```

---

## 거래 흐름 상세 (암호화폐 vs 주식/ETF)

| 단계 | 암호화폐 (자동) | 주식/ETF (AUTO 가능 + 수동 병행) |
|------|-----------------|-----------|
| 1️⃣ 선택 | 거래소별 지원·유동성 자동 후보 + 사용자 고정 코인 우선 | 사용자 고정 종목 우선 + KOSPI/KOSDAQ/ETF 거래대금 후보 |
| 2️⃣ 신호 | 30개 지표 기반 | 종목/ETF 분석 + 점수화 |
| 3️⃣ 검증 | AI 패턴 유사성 + 리스크 | 가드레일(시간/수량/금액/모드/브로커) |
| 4️⃣ 사이징 | 자동 계산 | 정책 기반 자동 계산(필요 시 수동 보정) |
| 5️⃣ 주문 | 자동 실행 | AUTO 루프 주문 + 수동 주문 병행 |
| 6️⃣ TP/SL | 자동 설정 | 정책형 익절/손절 + 브로커 제약 반영 |
| 7️⃣ 모니터 | AI 실시간 청산 | AUTO 사이클/정책 모니터 + 수동 개입 가능 |
| 8️⃣ 로그 | DB 자동 기록 | DB 자동 기록 |
| 9️⃣ 학습 | AI 신호 기준 자동 조정 | 거래 이력 분석 |

---

## 코드 경로 요약 (파일/함수)

| 기능 | 파일 | 함수/클래스 |
|------|------|-----------|
| UI 진입 | `ui/dashboard_modern.py` | `DashboardModern.switch_service()` |
| 거래 시작 | `main.py` | `Main.on_start_exchange()` |
| 신호 생성 | `trading/analyzer.py` | `generate_trading_signal()` |
| AI 호출 정책 | `trading/ai/inference_policy.py` | `OpportunityAwareInferencePolicy` |
| 유니버스 정책 | `trading/selection_policy.py` | `SelectionPolicy` |
| 공통 청산 기록 | `trading/exit_policy.py` | `build_exit_policy()` |
| 암호화폐 거래 | `trading/unified_trader.py` | `UnifiedTrader.execute_signal_trade()` |
| 바이낸스 거래 | `trading/trader.py` | `Trader.execute_single_trade()` |
| 포지션 모니터 | 위 파일들 | `_monitor_exchange_positions()` |
| AI 학습 | `trading/exchange_learning_manager.py` | `ExchangeLearningManager.add_learning_data()` |
| DB 기록 | `trading/recorder.py` | `Recorder.log_trade_entry/exit()` |

---

## 데이터 저장 위치

| 데이터 | 위치 | 형식 |
|--------|------|------|
| 거래 기록 | `data/trading.db` → `trade_log` | SQLite: 주문번호·모델·전략·실체결 수수료 포함 |
| AI 학습 데이터 | `data/nwsoft/ai_learning_data_*.json` | JSON (거래소별) |
| 포지션 정보 | 메모리 + `data/*.json` | Python dict |
| 설정값 | `data/settings.json` | JSON |
| 로그 파일 | `data/logs/` | 텍스트 |

### v3.9.0.1 거래기회 보존형 비용 제어

- 선택 거래소는 실제 주문, 나머지 활성 거래소는 기본적으로 학습 전용이다.
- 로컬 LONG/SHORT 신호는 호출 예산이 소진돼도 주문 검증 경로를 계속 통과한다.
- 안정적인 동일 시장상태는 15분 캐시를 사용한다.
- 새 캔들·15bp 이상 가격 변화·RSI 구간·MACD 방향·시장 국면 변화는 캐시를 우회한다.
- 성과 미달은 1포지션·1배·위험배수 0.15 회복 학습으로 전환하고 Hard MDD만 차단한다.
- 챔피언/챌린저 판정은 총손익이 아니라 실체결 수수료 차감 순PnL과 거래당 순기대값을 우선한다.

### v3.9.0.4 AI 보조 호출 중복 제거

- 포지션 크기 AI는 같은 심볼·방향·상태를 15분 재사용하며, 방향·1% 가격·0.10 신뢰도 변화에서만 다시 계산한다.
- 높은 신뢰도나 SHORT라는 이유만으로 신선한 캐시를 우회하지 않는다.
- 진입 전 손실패턴 AI는 같은 신호·손실 표본을 5분 재사용한다.
- 두 경로 모두 호출 실패 후 120초 재시도 쿨다운을 사용한다.
- 성과 기반 임계값 최적화는 최소 10거래 뒤 새 5거래마다 한 번이며 같은 실패 표본을 매 사이클 재호출하지 않는다.
- 거래소 어댑터·지원 마켓을 확인할 수 없으면 기본 심볼로 분석을 계속하지 않고 해당 거래소 후보를 비운다.
- 증권 자동 후보는 KOSPI·KOSDAQ과 ETF를 함께 조회하며 통합 모드에서 주식/ETF를 균형 배분한다.

### v3.9.0.1 주문·포지션 KPI 흐름

```text
주문 체결
  ├─ trade_order_executed: 주문 성공률·거래량
  └─ trade_position_opened: position_id + UTC opened_at
         ├─ 부분 청산 → trade_position_reduced + 잔여 수량
         └─ 전량 청산 → trade_position_closed + UTC closed_at + 검증된 hold_seconds
```

- 코인은 거래 실행 시 만든 `Position.entry_time`을 UTC aware datetime으로 유지한다.
- 주식·ETF는 매수 체결을 `exit_time IS NULL`인 열린 로트로 저장하고 매도 수량을 오래된 진입부터 연결한다.
- 앱 재시작 후 실제 진입시각을 확인할 수 없는 거래소 복구 포지션에는 임의의 현재 시각이나 0초 보유시간을 전송하지 않는다.
- 클라이언트가 같은 종료 이벤트를 재전송해도 서버가 `event_id`로 한 번만 집계한다.
- Binance 안전 종료와 Unified `close_all`은 추적된 포지션이면 정상 청산 경로를 재사용해 주문·포지션 종료 KPI가 함께 남는다.
- 포지션 생명주기 이벤트는 일시적인 서버 오류 때 제한적으로 재시도하며, 종료 절차는 KPI 큐 처리를 확인한 뒤 끝난다.
- 주문 체결 이벤트의 결제통화는 `quote_currency`로 전송한다. Upbit·Bithumb·KRW 심볼은 KRW, 나머지 USDT 페어는 USDT 거래량으로 집계한다.

---

## TP/SL 운영 규약 (2025-12-27 업데이트)

### ⚠️ **중요 변경사항 (2025-12-09 Binance 정책 변경)**
- **조건부 주문은 Algo Order API 사용 필수**: `STOP_MARKET`, `TAKE_PROFIT_MARKET` 등
- **엔드포인트**: `/fapi/v1/algoOrder` (자동 라우팅됨)
- **자세한 내용**: `docs/BINANCE_ALGO_ORDER_IMPLEMENTATION_2025-12-27.md` 참조

### 1) TP/SL 생성은 헬퍼 경유
- **권장 방법**: `BinanceClient.place_tp_sl_orders()` 사용
- **또는**: `BinanceClient.place_futures_order()` 사용 (조건부 주문은 자동으로 Algo Order로 라우팅됨)
- 원웨이/헤지 자동 감지:
  - 헤지: `closePosition=True`, `positionSide`, `workingType`
  - 원웨이: `closePosition=True`, `workingType` (positionSide 제외)
- 모든 생성 지점은 위 메서드를 경유합니다.

### 2) 가격 계산 규칙
- 심볼의 `tick_size`로 스냅 후, `price_precision`으로 포맷합니다.
- LONG: TP 상향, SL 하향 / SHORT: TP 하향, SL 상향

### 3) 주문 정리 정책
- TP/SL 외 주문만 선별 취소(화이트리스트 유지). 전량 취소는 폴백.
- 필터: `type` not in (`TAKE_PROFIT`, `TAKE_PROFIT_MARKET`, `STOP`, `STOP_MARKET`)

### 4) 포지션 조회 리트라이
- 100~300ms 지연으로 최대 3회 시도하여 체결 직후 0 응답 레이스를 회피합니다.
- 함수: `_get_position_info_with_retry`

### 5) workingType 설정
- 설정 키: `tp_sl_working_type` (`MARK_PRICE` 기본, `CONTRACT_PRICE` 선택)
- 헬퍼 내부에서 일괄 적용됩니다.

---

## TP/SL 모듈화 상태 및 설정 시점 (2025-01-26 업데이트)

### 모듈화 상태
- **TpSlManager 생성됨**: `trading/tp_sl_manager.py` (준비 완료)
- **실제 사용은 아직**: 기존 코드 사용 중 (`BinanceClient.place_tp_sl_orders()` 직접 호출)
- **롤백 가능**: 기존 코드 유지

### TP/SL 설정 시점: **진입 후** (포지션 확인 성공 후)

**코드 위치**: `trading/trader.py` Line 2440-2571

**실행 순서:**
```
1. 주문 실행 (place_futures_order) ← Line 2306
2. 주문 상태 확인 (PENDING/NEW/FILLED) ← Line 2322-2353
3. 포지션 확인 (_get_position_info_with_retry) ← Line 2437
   └── positionAmt > 0 확인
4. TP/SL 설정 시작 ← Line 2449
   ├── 백업 TP/SL 계산 (settings.json 기반) ← Line 2452-2517
   ├── TP/SL 가격 스냅 (tickSize 기반) ← Line 2526-2557
   └── TP/SL 주문 생성 (place_tp_sl_orders) ← Line 2571
5. TP/SL 검증 (재시도 로직) ← Line 2622-2677
6. 포지션 저장 (active_positions) ← Line 2780
```

### TP/SL 역할
- **실시간 모니터링**: 동적 임계값 사용 (주력 청산)
- **백업 TP/SL**: 동적 임계값 × 2~3배 (보험 역할)
- **설정 값**: `settings.json`의 `backup_tp_sl_settings`에서 설정 가능

### 모듈화 계획
- **Phase 6 Step 2**: TpSlManager 생성 및 audit 로그 (✅ 완료)
- **Phase 6 Step 4**: 실제 로직 이관 (⏳ 진행 예정)

# Trading Flow: 시작 → 거래 → 학습 → DB 기록

본 문서는 다중 거래소 환경에서 per-exchange 기준으로 시작부터 학습/DB 기록까지의 전체 파이프라인을 요약합니다.

---

## 📋 전체 거래 플로우 상세 분석 (2025-01-26 업데이트)

### 🔍 코드 순서 검증 결과

**코드 순서 문제 없음**: 모든 단계가 명확하게 정의되어 있고, 각 단계별 검증 로직이 존재합니다.

### 📊 전체 플로우 요약

```
1. 코인 선택 (Evaluator)
   └── main_app.selected_coins (Line 1481)

2. 거래 사이클 시작 (execute_trading_cycle, Line 1373)
   ├── 좀비 플래그 정리
   ├── 시장 분석 및 코인 재선택
   ├── 일일 손실 한도 체크
   ├── AI 자동 학습
   └── 포지션 동기화 (실제 거래소 ↔ 메모리)

3. 포지션 수 체크 (Line 1465-1502)
   ├── 집중모드: 포지션 있으면 전체 스킵
   ├── 보유 심볼 제외 필터링
   └── 최대 포지션 수 체크 (max_positions)

4. 코인별 분석 (Line 1531-1707)
   ├── 시그널 생성 (analyzer.generate_trading_signal, Line 1572)
   ├── AI 학습 데이터 저장
   ├── AI 진입 전 분석 (_perform_pre_entry_analysis, Line 1644)
   ├── AI 강화 파라미터 최적화 (_get_ai_enhanced_parameters, Line 1680)
   └── execute_trades() 호출 (Line 1691)

5. 거래 실행 판단 (execute_trades, Line 1737)
   ├── trade_config 추출
   ├── TP/SL 필수 여부 검증
   ├── trade_params 구성 (Line 1812-1823)
   └── should_execute_trade() 검증 (Line 1830)

6. 거래 실행 조건 검증 (should_execute_trade, Line 1859)
   ├── 수량 검증
   ├── 현재가 조회
   ├── 필터 정규화
   ├── 수량 보정 (step_size, min_notional)
   ├── 포지션 중복 체크
   ├── 최대 포지션 수 체크
   ├── 잔고 확인
   └── AI 패턴 분석

7. 단일 거래 실행 (execute_single_trade, Line 2068)
   ├── TP/SL 검증
   ├── 거래 진입 플래그 체크
   ├── 거래 진입 플래그 설정
   ├── 오픈오더 정리
   ├── 잔고 검증
   ├── 레버리지 설정
   ├── 주문 실행 (place_futures_order, Line 2306)
   ├── 주문 상태 확인 및 체결 대기 (Line 2322-2353)
   ├── 주문 실패 처리 (실제 포지션 확인)
   └── 포지션 확인 및 TP/SL 설정 (Line 2440-2780)

8. 포지션 저장 및 모니터링 (Line 2780-2800)
   ├── Position 객체 생성
   ├── active_positions에 추가
   └── 모니터링 스레드 시작

9. 실시간 모니터링 및 청산 (should_close_position, Line 3219)
   ├── AI 모니터링 중심 청산 판단 (주력)
   ├── 동적 임계값 기반 실시간 모니터링 청산
   └── TP/SL 안전장치 (최후의 보호막)
```

---

## 📋 시그널 발생부터 거래 실행까지 전체 플로우 (2025-01-26 업데이트)

### 🔄 메인 거래 사이클
**진입점**: `trading/trader.py` → `execute_trading_cycle()` (Line 1373)

### 1단계: 거래 사이클 시작 (Line 1373-1394)
```
execute_trading_cycle()
├── 좀비 플래그 정리 (_cleanup_zombie_flags)
├── 시장 분석 및 코인 재선택 (_check_and_reselect_coins_optimized)
├── 일일 손실 한도 체크 (risk_manager.check_daily_loss_limit)
└── AI 자동 학습 (_auto_adjust_threshold_from_performance)
```

### 2단계: 포지션 동기화 (Line 1399-1463)
```
포지션 동기화
├── 실제 거래소에서 포지션 조회 (binance_client.get_positions)
├── 메모리에 있지만 실제 없는 포지션 제거
└── 실제 있지만 메모리에 없는 포지션 추가/복구
```

### 3단계: 거래 스킵 로직 (Line 1465-1502)
```
execute_trading_cycle()
├── 단일모드(집중모드)일 때: 활성 포지션 > 0 이면 전체 스킵
├── 보유 심볼 제외 필터링
└── 최대 포지션 수 도달 시 스킵
```

### 4단계: 코인별 시그널 분석 및 AI 검증 (Line 1531-1707)
```
execute_trading_cycle()
└── 각 selected_coins에 대해 반복
    ├── 분석 사이 딜레이 (3초)
    ├── 중지 신호 확인
    ├── 리스크 관리 코인 스킵 체크
    ├── 시그널 생성 (analyzer.generate_trading_signal) (Line 1572)
    │   └── AI 매니저 활성화 시 AI 분석 포함
    ├── AI 학습 데이터 저장 (_generate_ai_learning_data)
    ├── AI 진입 전 분석 (_perform_pre_entry_analysis) (Line 1644)
    │   └── 패턴 유사성 분석, 첫 거래 완화 등
    ├── AI 강화 파라미터 최적화 (_get_ai_enhanced_parameters) (Line 1680)
    └── execute_trades() 호출 (Line 1691)
```

### 5단계: 거래 실행 판단 (execute_trades 내부)
```
execute_trades(candidates, optimized_params) (Line 1737)
├── trade_config 추출 (optimized_params에서)
├── TP/SL 필수 여부 검증 (tp/sl 누락 시 스킵)
├── trade_params 구성 (Line 1812-1823)
│   ├── symbol, side, qty, price
│   ├── leverage, tp, sl
│   └── filters (step_size, min_qty, etc.)
└── should_execute_trade() 검증 (Line 1830)
```

### 6단계: 거래 실행 조건 검증 (should_execute_trade) (Line 1859-2067)
```
should_execute_trade(trade_params) (Line 1859)
├── 수량 검증
├── 현재가 조회 (price가 0일 때)
├── 필터 정규화 (camelCase → snake_case)
├── 수량 보정 (step_size, min_notional)
├── 포지션 중복 체크 (active_positions)
├── 최대 포지션 수 체크 (settings['max_positions'])
├── 잔고 확인 (available_balance)
└── AI 패턴 분석 (최근 손실 패턴 기반 조정/스킵)
```

### 7단계: 단일 거래 실행 (execute_single_trade) (Line 2068-2431)
```
execute_single_trade(trade_params) (Line 2068)
├── TP/SL 검증 (tp/sl 필수)
├── 거래 진입 플래그 체크 (trade_entered)
├── 거래 진입 플래그 설정 (trade_entered[symbol] = True)
├── 주문 실행 (binance_client.place_futures_order) (Line 2306)
│   ├── 시장가 주문 제출
│   └── 주문 결과 반환 (status: NEW/FILLED/PENDING)
├── 주문 상태 확인 및 체결 대기 (Line 2322-2353)
│   ├── PENDING/NEW 상태 체크
│   ├── 최대 10초 체결 대기
│   │   ├── 1초마다 주문 상태 확인 (futures_get_order)
│   │   ├── FILLED 확인 시 break
│   │   └── CANCELED/REJECTED 확인 시 break
│   └── 타임아웃 시 포지션 확인으로 진행
└── 주문 실패 처리 (Line 2357-2431)
    ├── MIN_NOTIONAL 에러 검증
    └── 실제 포지션 확인 (주문 실패 처리되었지만 포지션이 있을 수 있음)
        └── 포지션이 있으면 성공으로 처리 (order_status = 'FILLED')
```

### 8단계: 포지션 확인 및 TP/SL 설정 (execute_single_trade 내부) (Line 2434-2780)
```
execute_single_trade()
├── 주문 성공 처리 (order_status in ['NEW', 'FILLED', 'PENDING'])
├── 포지션 정보 조회 (_get_position_info_with_retry)
├── 실제 진입 가격 확인
├── 백업 TP/SL 계산 (settings.json 기반, 동적 변동성/패턴 조정)
├── TP/SL 가격 스냅 (tickSize, price_precision)
├── TP/SL 주문 생성 (binance_client.place_tp_sl_orders) (Line 2571)
│   ├── Algo Order API 대응
│   ├── closePosition=True, quantity=None
│   └── TP/SL 중 하나라도 실패 시 롤백 (원자성)
├── TP/SL 사후 검증 강화 (재시도 로직) (Line 2622-2677)
│   ├── 정확히 1:1 TP/SL 주문 확인
│   ├── workingType, status 등 상세 옵션 검증
│   └── 검증 실패 시 재설정 시도
└── TpSlManager audit (비파괴적 상태 점검) (Line 2770-2778)
```

### 9단계: 포지션 저장 및 모니터링 시작 (execute_single_trade 내부) (Line 2780-2800)
```
execute_single_trade()
├── Position 객체 생성 및 active_positions에 추가 (Line 2780-2799)
└── 모니터링 스레드 시작 (_start_monitoring)
```

---

## 🔍 코드 실행 순서 확인

### 시그널 발생 조건:
- ✅ 코인이 `selected_coins` 리스트에 포함
- ✅ 리스크 관리 (`risk_manager.should_skip_coin`)에서 스킵되지 않음
- ✅ 포지션 수 제한 내 (집중모드: 1개, 멀티모드: `max_positions`)
- ✅ `analyzer.generate_trading_signal()` 호출 (Line 1572)

### 거래 실행 조건:
- ✅ 시그널이 `LONG` 또는 `SHORT` (Line 1631)
- ✅ AI 진입 전 분석 통과 (`_perform_pre_entry_analysis`) (Line 1644)
- ✅ `should_execute_trade()` 검증 통과 (Line 1830)
  - 수량, 현재가, 필터, 포지션 중복, 최대 포지션 수, 잔고, AI 패턴 분석 등 모든 조건 통과

### 주문 실행 순서:
1. `binance_client.place_futures_order()` 호출 (Line 2306)
2. 주문 결과 확인 (status: `NEW`/`FILLED`/`PENDING`) (Line 2313)
3. `PENDING`/`NEW` 상태 → 체결 대기 (최대 10초) (Line 2322-2353)
4. 실제 포지션 확인 (Line 2437)
5. TP/SL 설정 (Line 2571)
6. 포지션 저장 (`active_positions`에 추가) (Line 2780)

### TP/SL 설정 순서:
1. 백업 TP/SL 계산 (settings.json 기반, 동적 변동성/패턴 조정) (Line 2452-2517)
2. TP/SL 가격 스냅 (tickSize, price_precision) (Line 2526-2558)
3. `binance_client.place_tp_sl_orders()` 호출 (Line 2571) ← 🔥 기존 코드
4. TP/SL 사후 검증 (재시도 로직) (Line 2622-2677)
5. 검증 실패 시 재설정 시도 (Line 2665)

---

## 💰 TP/SL 수치 및 청산 기준 상세 분석

### 1. 동적 임계값 (실시간 모니터링용 - 주력 청산)

**계산 위치**: `_calculate_dynamic_thresholds()` (Line 4434)

**기본값**:
- `profit_threshold`: 0.0018 (0.18%) - `settings.json`의 `default_tp`
- `loss_threshold`: 0.002 (0.20%) - `settings.json`의 `default_sl`

**동적 조정**:
- AI Optimizer가 시장 상황에 따라 조정
- 시장 변동성 기반 조정
- 최근 거래 패턴 기반 조정

**청산 조건** (Line 3241-3259):
- 수익 청산: `net_pnl_percent >= profit_threshold_percent`
- 손실 청산: `net_pnl_percent <= -loss_threshold_percent`

### 2. 백업 TP/SL (서버 주문용 - 보험 역할)

**계산 위치**: `execute_single_trade()` (Line 2452-2517)

**계산 공식**:
```
백업 TP/SL = 동적 임계값 × multiplier × pattern_multiplier
```

**Multiplier (settings.json)**:
- 높은 변동성 (>2%): 3.0배
- 중간 변동성 (1-2%): 2.5배
- 낮은 변동성 (<1%): 2.0배

**안전 범위 제한**:
- TP: 최소 1.0% ~ 최대 5.0%
- SL: 최소 0.8% ~ 최대 3.0%

**예시**:
- 동적 임계값 TP=0.18%, SL=0.20%
- 중간 변동성 (2.5배)
- 백업 TP = 0.18% × 2.5 = 0.45% (최소 1.0% 적용 → 1.0%)
- 백업 SL = 0.20% × 2.5 = 0.50% (최소 0.8% 적용 → 0.8%)

### 3. 청산 우선순위

**1순위: AI 모니터링 중심 청산** (Line 3223-3232)
- AI가 시장 상황을 분석하여 청산 결정
- 신뢰도 기반 판단

**2순위: 동적 임계값 기반 실시간 모니터링** (Line 3234-3259)
- 수익 청산: `net_pnl_percent >= profit_threshold_percent`
- 손실 청산: `net_pnl_percent <= -loss_threshold_percent`
- **이것이 주력 청산 메커니즘**

**3순위: TP/SL 안전장치** (Line 3261-3296)
- 서버 주문으로 설정된 백업 TP/SL
- 실시간 모니터링이 실패했을 때 최후의 보호막
- **실시간 모니터링보다 넓게 설정되어 있음**

### 4. 포지션 수 제한

**집중모드** (`position_mode == 'single'` 또는 `max_positions == 1`):
- 포지션이 1개 이상이면 전체 스킵 (Line 1471-1473)

**멀티모드** (`max_positions > 1`):
- 최대 포지션 수: `settings.json`의 `max_positions` (기본값: 3)
- 포지션 수 체크: Line 1497-1499, 1984-1986

**과도한 포지션 방지**:
- ✅ 집중모드: 최대 1개
- ✅ 멀티모드: 최대 `max_positions`개
- ✅ 포지션 중복 체크: Line 1979-1981
- ✅ 보유 심볼 제외 필터링: Line 1475-1490

### 5. 청산 기준 요약

**실시간 모니터링 청산** (주력):
- 수익: `net_pnl_percent >= 0.18%` (동적 조정 가능)
- 손실: `net_pnl_percent <= -0.20%` (동적 조정 가능)

**백업 TP/SL 청산** (보험):
- TP: 진입가 × (1 + 백업_TP) 도달 시
- SL: 진입가 × (1 - 백업_SL) 도달 시
- 백업 TP/SL은 동적 임계값보다 2~3배 넓게 설정

**AI 청산** (최우선):
- AI가 시장 상황을 분석하여 청산 결정
- 신뢰도 기반 판단

---

## 롤백 가능성

### 롤백 방법
- `trading/trader.py` Line 130-135 제거 (TpSlManager 초기화)
- `trading/trader.py` Line 2769-2778 제거 (audit 호출)
- 위 코드만 제거하면 완전히 이전 상태로 롤백 가능

### ⚠️ 주의사항
- **TpSlManager 제거해도 기존 동작에 영향 없음**
- **모든 TP/SL 로직은 기존 코드 사용 중**
- **모듈화는 아직 진행되지 않음** (준비 단계)

## 🚨 중요: 거래소별 분리 시스템 (2025-01-15 업데이트)

### 바이낸스 전용 시스템
- **시작**: `Main.on_start_exchange('binance')` → `_start_binance_trading()` → `start_trading_loop()`
- **거래 루프**: `main.py.trading_loop()` → AI 분석 → `trader.execute_trades()` → `api/binance_client.py`
- **정지**: `Main.on_stop_exchange('binance')` → `_stop_binance_trading()` → `stop_trading_loop()`

### CCXT 거래소 통합 시스템 (업비트, 빗썸, OKX, 바이비트, 비트겟)
- **시작**: `Main.on_start_exchange(exchange)` → `_start_unified_trading(exchange)` → `unified_trader.start_trading(exchange)`
- **거래 루프**: `unified_trader._monitoring_loop(exchange)` → AI 분석 → CCXT 어댑터 → 각 거래소 API
- **정지**: `Main.on_stop_exchange(exchange)` → `_stop_unified_trading(exchange)` → `unified_trader.stop_trading(exchange)`

## 1) 시작/정지 진입점 (UI → Main)
- UI: Modern Dashboard에서 거래소별 시작/정지 버튼 → `main.py`
- **바이낸스 시작**: `Main.on_start_exchange('binance')` → `_start_binance_trading()` → `start_trading_loop()`
- **CCXT 거래소 시작**: `Main.on_start_exchange(exchange)` → `_start_unified_trading(exchange)` → `unified_trader.start_trading(exchange)`
- **바이낸스 정지**: `Main.on_stop_exchange('binance')` → `_stop_binance_trading()` → `stop_trading_loop()`
- **CCXT 거래소 정지**: `Main.on_stop_exchange(exchange)` → `_stop_unified_trading(exchange)` → `unified_trader.stop_trading(exchange)`

## 2) 바이낸스 거래 루프
- **메인 루프**: `main.py.trading_loop()`
  - 주기(설정: `auto_trade_interval`)마다 선택된 코인들 분석 및 거래 실행
  - AI 분석: `analyzer.analyze_symbol(symbol)`
  - 거래 실행: `trader.execute_trades(candidates, optimized_params)`
  - 포지션 모니터링: `trader.monitor_positions()`

## 3) CCXT 거래소 모니터링 루프
- **메서드**: `UnifiedTrader._monitoring_loop(exchange)`
  - 주기(설정: `auto_trade_interval`)마다 `execute_trading_cycle_unified(exchange)` 실행

## 4) CCXT 거래소 거래 사이클
- 선택된 코인 사용: `selected_coins[exchange]`
- 분석: `analyze_coins_unified(exchange, coins)`
  - Analyzer에 위임: `analyzer.generate_trading_signal(symbol, exchange_name=exchange)`
  - 동시에 AI 학습 데이터 생성: `_generate_ai_learning_data(exchange, symbol, signal_data)`
- 거래 실행: `_execute_signal_trade(exchange, symbol, analysis)`
  - 사전 체크: 리스크 가드레일, AI 진입 전 분석, 패턴 유사성 분석, 동적 신뢰도 임계값
  - 포지션 사이징: `_calculate_position_size_unified()` + `_ensure_min_notional()`
  - 주문 경로: Paper 모드 시 시뮬레이션 결과, 실거래 시 UnifiedTradingManager/어댑터/네이티브 클라이언트 경유
  - 성공 시 포지션 기록: `_record_position_with_tp_sl()`
  - Recorder 진입 로그 기록: `recorder.log_trade_entry(position, trade_params)`
- 포지션 모니터링: `_monitor_exchange_positions(exchange)`
  - 실시간 PnL 계산, 동적 TP/SL/시간 기반/AI 가드레일로 청산 판단
  - 청산 시 Recorder 청산 로그 기록: `recorder.log_trade_exit(position, reason, exit_price)`

## 4) 학습/분석 데이터
- AI 학습(JSON): `_generate_ai_learning_data()` → `ExchangeLearningManager.add_learning_data()`
- 코인 평가/선정(DB): `Evaluator.select_trading_coins()` → `Recorder.save_coin_selection()` + `coin_evaluation` 저장
- 분석 로그(DB): `Main._save_analysis_to_database()` → `analysis_log` INSERT

## 5) 데이터 저장 위치
- DB 파일: `path_utils.get_db_file_path()` → `<사용자문서>/NoahAI*/<user>/trading.db`
  - 주요 테이블: `trade_log`, `analysis_log`, `ai_optimization`, `ai_trade_analysis`, `ai_decisions`, `coin_selection_sessions`, `selected_coins`, `coin_evaluation`, `performance_stats`
- 로그 파일: `path_utils.get_log_dir()`
- AI 학습 JSON:
  - 거래소별 파일: `<데이터 디렉토리>/ai_learning_data_{exchange}.json` (예: ai_learning_data_binance.json)
  - 글로벌 집계 파일: `<데이터 디렉토리>/ai_learning_data.json` (레거시/호환 목적, 최근 항목 위주)
  - 대시보드의 학습 탭은 거래소 선택 드롭다운을 제공하며, 선택된 거래소의 파일을 직접 로드합니다.

## 6) 안전성과 로그 정책
- API 키 미설정 시 REST 호출 가드 (노이즈 감소)
- 잘못된 심볼 경고 warn-once 캐시
- 최소 노셔널/레버리지/마진 타입 가드레일

## 7) 참고 소스
- `noahai_client/main.py` → on_start_exchange/on_stop_exchange, _save_analysis_to_database
- `trading/unified_trader.py` → 모든 거래/모니터링/사이징/AI 연동
- `trading/recorder.py` → SQLite 스키마 및 INSERT/UPDATE
- `trading/evaluator.py` → 코인 평가/선정 및 DB 기록

---
질문/개선 제안은 대시보드 커뮤니티 영역(플레이스홀더) 또는 이 문서에 코멘트로 남겨주세요.

## 📈 Chart Screenshot Analyzer 흐름 (로컬, 서버 없음)

목적: 사용자가 업로드한 거래소 캔들 차트 스크린샷을 기반으로 AI가 롱/숏/중립 스탠스, 시나리오, 진입/청산/목표를 즉시 제시.

구성
- UI: `ui/widgets/chart_screenshot_widget.py`
- 분석 모듈: `trading/ai/chart_screenshot_analyzer.py`
- 세션 재사용: `trading/ai/openai_client.py`를 AI 어시스턴트와 공유

플로우
1) 업로드 트리거
   - 위치 A: 대시보드 Quick Actions(거래 현황 아래) → “📊 차트 이미지 분석”
   - 위치 B: AI 어시스턴트 탭 채팅 입력 옆 → “📊 차트 이미지 분석”
2) 이미지 선택(로컬 파일 다이얼로그)
   - JPG/PNG 파일 선택
3) OCR 추출(선택 의존성)
   - PaddleOCR(use_angle_cls=True, lang='en')로 텍스트 추출
   - 미설치 시 경고만 표시하고 중단(앱은 정상 동작)
4) 특징 파싱
   - 심볼(BTC/USDT, BTCUSDT 등), 타임프레임(1D/4H/1H/15M/5M/1W), MA/EMA/SMA 값 정규식 파싱
5) LLM 분석 호출
   - OpenAIClient.chat_json() 호출, 결과를 JSON으로 강제
6) 결과 표시
   - 업로드 팝업에 결과 JSON 그대로 표시(향후 채팅 형태 렌더링으로 확장 가능)

스토리지 정책
- 서버 업로드 없음. 선택된 이미지는 로컬 캐시에만 복사되어 분석합니다.
- 경로: `Documents/NoahAI*/<user>/cache/chart_uploads/<timestamp>_<filename>`(배포) 또는 프로젝트 `data/<user>/cache/chart_uploads`(개발)

반환 스키마(예시)
```
{
  "stance": "LONG|SHORT|NEUTRAL",
  "confidence": 0.0,
  "scenarios": [
    { "title": "상승 지속", "prob": 0.55, "narrative": "..." },
    { "title": "조정 후 재상승", "prob": 0.30, "narrative": "..." }
  ],
  "plan": {
    "entry": 61234.5,
    "stop": 60321.0,
    "tp": [61800.0, 62500.0],
    "notes": "변동성 높은 구간, 포지션 축소 권장"
  },
  "features": { "symbol": "BTC/USDT", "timeframe": "1H", "moving_averages": {"MA20": 61000.0} },
  "raw_text": "..."
}
```

의존성(선택)
- `pip install paddleocr opencv-python-headless`
- 미설치 시 OCR 단계에서 경고만 반환합니다.

확장 아이디어
- 결과를 AI 채팅 버블 형태로 렌더링(요약 + 복사 버튼)
- 이미지 썸네일 미리보기 및 최근 업로드 이력
- 시나리오별 버튼(롱/숏 템플릿)로 전략 적용 연결
- 국내 거래소 표기/폰트 인식 강화, 시그널 라벨 OCR 보강
# Trading Flow Updates (2025-10-05)

## Binance vs CCXT Exchanges

- Binance: 네이티브 클라이언트 + OrderRequest 기반. 주문/청산은 `api.binance_client.BinanceClient.place_order(OrderRequest)` 경로로 수행합니다.
  - 정규화: `stepSize`(수량), `tickSize`(가격), `minNotional`(소폭 여유 0.5%)를 주문 직전에 보정하고, `quantityPrecision`으로 최종 포맷합니다.
  - 효과: Binance -1013(Filter failure: LOT_SIZE/PRICE_FILTER/MIN_NOTIONAL) 케이스를 현저히 줄입니다.
- Bybit/OKX/Bitget: CCXT 어댑터. `place_order(symbol, side, amount, price=None, order_type='market')` 시그니처를 사용합니다. OKX는 passphrase, Bitget은 password가 필수입니다.

### Fixes: 주문 타입/심볼 검증 강화 (2025-10-05)
- Binance 주문 타입 정규화: `api.binance_client.BinanceClient.place_order(OrderRequest)`가 `side`, `order_type` 입력을 대문자화하고 별칭을 표준 타입으로 매핑합니다. 예) `market`/`stop`/`take_profit` → `MARKET`/`STOP_MARKET`/`TAKE_PROFIT_MARKET`.
- OKX 선물 심볼 검증: `trading/exchanges/adapters/okx_futures_adapter.py`가 주문 전 마켓 존재 여부를 확인합니다. 거래소에 해당 선물 마켓이 없으면 즉시 `미지원 선물 심볼` 오류로 명확히 반환합니다(XMR/USDT 등).

## UnifiedTrader 청산 경로

- 거래소 타입에 따라 자동 분기합니다. CCXT는 키워드 인자, Binance는 OrderRequest로 호출해 시그니처 충돌을 방지합니다.

## 현물(KRW) 코인 선정

- 업비트/빗썸은 KRW 페어를 전부 수집 후 `quoteVolume` 기준 내림차순 정렬해 상위 N개를 선정합니다. 이전 릴리스의 단순 슬라이스(정렬 부재) 문제를 수정했습니다.
- 기본 알트 개수는 10으로 조정되었습니다(이전 15). 사용자 환경에서는 `settings.json`의 `num_alt_coins`로 즉시 변경 가능합니다.

## 전략/임계값 설정

- `config/settings_template.json`에 `strategy_config` 섹션이 추가되어 변동성/거래량 임계값과 점수 가중치를 조정할 수 있습니다.
- 동적 임계값(`dynamic_thresholds_*`)은 시장 국면에 따라 자동으로 시그널 기준을 보정합니다.
- 기본 시그널 기준을 보수화했습니다: RSI 과매도 28, 과매수 72(기존 30/70). 모멘텀 임계 역시 소폭 상향되어 노이즈 진입을 줄입니다. 필요 시 `settings.json`에서 사용자 환경에 맞게 미세 조정하세요.
- HIGH 국면 보수화: `rsi_oversold_delta -4`, `rsi_overbought_delta +4`, `momentum_threshold_scale 1.25`, 히스테리시스 `high_enter_mult 1.65`, `high_exit_mult 1.28`로 진입을 더 엄격하게 해 변동성 구간의 노이즈 진입을 줄입니다.

## TP/SL 및 진입 관련 설정 키(현행)
- 전역 키
  - `entry_order_type`: 'market' | 'limit' (기본 'market'). 현재 기본은 MARKET 진입이며, LIMIT는 실험적입니다.
  - `tp_sl_settings`
    - `enabled`: true/false, 보험 TP/SL 서버주문 발주 토글(기본 true)
    - `trigger_price_source`: 'mark' | 'last' | 'index' (거래소 지원 범위 내)
    - `tp_order_type`, `sl_order_type`: 'market' | 'limit' (기본 'market')
- 거래소별 오버라이드
  - `exchange_tp_sl_overrides.{exchange}`: `{ enabled?, trigger_price_source?, margin_mode? }`
    - 예) OKX: `{ "trigger_price_source": "mark", "margin_mode": "cross" }`
    - 예) Bybit/Bitget: `{ "trigger_price_source": "mark" }`

적용 우선순위: 거래소별 오버라이드 > 전역 `tp_sl_settings` > 기본값('mark', enabled=true)

## CCXT 선물 코인 선정 설정 키
- `futures_selection.{exchange}`
  - `max_candidates`: 선정 최대 후보 수(기본 100)
  - `min_quote_volume`: 최소 유동성 컷오프(USDT 기준, 예: 20_000_000)
  - `volatility_max`: 변동성 상한(24h `percentage` 절대값 기준, 예: 25.0)
  - `sort_weights`: `{ volume: 0.9, volatility: 0.1 }`와 같이 정렬 가중(볼륨/변동성)
  - 파일: noahai_client/config/settings_template.json

동작: Evaluator가 거래소 어댑터(`exchange_client`)를 받아 해당 값으로 후보군을 필터링/정렬합니다. 파일: noahai_client/trading/evaluator.py: `_analyze_candidate_coins_ccxt_futures()`

## 거래 통계(대시보드)
- “📈 거래 통계” 탭: DB `trade_log` 기반으로 최근 30일 요약을 표시(승·패/승률/평균·최대·최소 PnL%).
- 슬리피지 요약: 선택한 기간/거래소 필터에 따라 심볼별 평균/절대 평균 슬리피지 상위 항목을 표시.
- 기간/거래소 필터: 1d/7d/30d/90d/all, 전체/개별 거래소 선택 가능(선택 즉시 반영).
- 간단 시각화: 상단에 전체 승률(ProgressBar) 표시.
- 파일: noahai_client/ui/dashboard_modern.py: `_ensure_trading_stats_tab()`, `_update_trading_statistics()`

## 운영 모드와 AI 권장 튜닝(대시보드 UI)
- 운영 모드 드롭다운: `auto` | `guided` | `pro` (기본 `guided`)
  - `auto`: 앱 시작 시 최근 30일 DB를 근거로 선물 코인 선정 파라미터 자동 적용(데이터 없으면 건너뜀)
  - `guided`: “📈 거래 통계” 탭의 "AI 추천 튜닝 적용" 버튼 1회로 반영(저장 포함)
  - `pro`: 완전 수동(추천만 제공, 자동 적용 없음)
- 리스크 프리셋 드롭다운: `conservative` | `moderate` | `aggressive`
  - 클릭 시 `futures_selection.{exchange}`의 `min_quote_volume`/`volatility_max`/`sort_weights`를 일괄 적용(저장 포함)
- 권장치 산출 로직: `trading/tuning_manager.py`
  - 최근 30일 승률/평균 절대 슬리피지로 `min_quote_volume`, `volatility_max` 권장
  - 슬리피지↑ → min_quote_volume↑, volatility_max↓(보수화). 성과 양호 → 소폭 완화

## 실시간 청산 PnL 계산 기준 (2026-05-29 업데이트)
- 목적: "실시간 청산 판단"과 "청산 후 거래 기록"의 PnL 기준을 일치시켜 판단/리포트 불일치를 줄입니다.
- 적용 위치: `trading/unified_trader.py`의 `_calculate_pnl_unified()`
- 기준식(요약):
  - `gross_pnl_ccy = (current_price - entry_price) * quantity * side_sign`
  - `notional = entry_price * quantity`
  - `net_pnl_ccy = gross_pnl_ccy - (notional * fee_rate) - (notional * slippage_rate)`
  - `net_pnl_percent = (net_pnl_ccy / notional) * 100`
- 기본 추정치:
  - `fee_rate`: 0.0004 (왕복 0.04%)
  - `slippage_rate`: 0.0002 (0.02%)
  - 필요 시 `settings.json`에서 `estimated_round_trip_fee_rate`, `estimated_slippage_rate`로 오버라이드 가능
- 기록 계층 일치 기준: `trading/recorder.py`의 `gross_pnl_ccy/net_pnl_ccy` 계산 경로와 동일 철학 사용
- 유의사항:
  - 본 패치는 "판단 산식 정합화"이며, RR 구조(TP/SL 비율) 자체를 바꾸는 패치는 아닙니다.
  - 성과 개선은 RR/사이징/집중도 가드와 함께 병행해야 안정적입니다.

## 대시보드 잔고 표기 경로 요약
- UI `잔고` 탭은 우선 `UnifiedTradingManager.get_all_balances()`를 호출해 연결된 거래소별 잔고를 조회합니다. Binance는 네이티브 클라이언트를 통해 선물 전용 개인 엔드포인트(`futures_account`)로 조회합니다. 폴백에서는 `ExchangeManager.get_exchange_balance()`가 실행되며, 여기서도 Binance는 네이티브(private) 경로를 사용합니다.

## 재발 가능성 및 가드
- OKX: 거래소에 해당 선물 마켓이 실제로 없을 때는 여전히 “미지원 선물 심볼”로 반환됩니다(정상). 분석 단계에서 거래소-심볼 호환성 사전 필터를 추가하면 UX가 더 좋아집니다.
- Binance: `OrderRequest` 경로는 주문 타입 정규화로 보호됩니다. 만약 다른 경로에서 임의의 미지원 타입(또는 소문자)을 직접 전달하면 여전히 API 측에서 거절될 수 있습니다. 현재 코드에서는 구 경로(`place_futures_order`)도 ‘MARKET’ 대문자로 호출하므로 안전합니다.

## 주문 전략과 TP/SL(보험) 설계

- 정책(기본)
  - 진입: `MARKET`(시장가) 우선. 목적은 신호 시점에 즉시 체결(미체결/부분체결 최소화).
  - 보험 TP/SL: 진입 직후 거래소 서버 측에 `TAKE_PROFIT_MARKET`/`STOP_MARKET`를 "보험"으로 발주하여 갑작스런 장애/네트워크 단절에도 포지션이 방치되지 않도록 함.
  - 퍼센트 기준: 심볼/가격대가 모두 다른 환경에서 일관성을 위해 `tp_percent`/`sl_percent`(예: 0.0018=0.18%, 0.0020=0.20%)를 사용. 최적화/AI가 전달하면 우선 적용, 없으면 `settings.json`의 기본값 사용.

- 근거(코드)
  - 시장가 진입: `trading/unified_trader.py:506`, `trading/unified_trading_manager.py:128` 경로에서 기본 `order_type='market'`.
  - 결과 매핑 보강: 평균가/체결수량을 표준 필드로 보정해 포지션 기록 실패 방지(`trading/unified_trading_manager.py:156`).
  - 보험 TP/SL 발주: Binance 실거래 성공 시 `place_tp_sl_orders()` 호출(`trading/unified_trader.py:639` → `api/binance_client.py:1586`).
  - 포지션 기록/TP·SL 가격 계산: `trading/unified_trader.py:1960`.

- 장점
  - 즉시 체결 지향: 신호 발생 시 빠른 체결을 우선하되, 시장 상황에 따라 미체결/부분체결/지연은 발생 가능.
  - 서버-사이드 안전장치: 프로세스 중단/네트워크 단절에도 TP/SL이 거래소에서 동작.
  - 자산/거래소 간 일관성: 퍼센트 기반 TP/SL로 가격대가 달라도 동일 정책 적용.

- 단점/주의
  - 시장가 슬리피지: 급격한 변동/유동성 부족 시 체결가 불리 가능.
  - 잦은 스탑아웃: 변동성 대비 너무 작은 `sl_percent`면 노이즈에 잘릴 수 있음(시장 국면별 조정 권장).
  - LIMIT형 TP/SL 미사용: 급변동 시 LIMIT은 미체결 위험이 있어 기본은 MARKET형. 필요 시 옵션화 가능.

- 다른 거래소(CCXT) 적용 상태
  - Bybit/OKX/Bitget: 보험 TP/SL(서버‑사이드) 적용 완료. 진입 직후 포지션에 TP/SL 트리거를 부착합니다.
  - 각 거래소별 `create_order(..., params=...)`의 조건부 키가 상이하므로 어댑터 단에서 일괄 매핑합니다.

- 설정 키(현행)
  - `default_tp`, `default_sl`: 기본 TP/SL 퍼센트(소수, 예: 0.0018=0.18%).
  - (확장 제안) `entry_order_type`, `tp_order_type`, `sl_order_type`, `tp_sl_mode`: LIMIT/MARKET 선택 및 보험모드 토글.

## 보험 TP/SL 롤아웃 계획 (2025‑10‑05)
- Phase 1 — Bybit: 적용 완료
  - 구현: `noahai_client/trading/exchanges/adapters/bybit_futures_adapter.py:287`의 `place_insurance_tp_sl()`
    - ccxt bybit는 `create_order()`에 `takeProfit/stopLoss` 트리거를 첨부하면 내부적으로 Position Trading Stop API로 라우팅됨.
    - 파라미터: `takeProfit={'triggerPrice': tp}`, `stopLoss={'triggerPrice': sl}`, `triggerPriceType='mark'`(마크가격 기준)
    - UnifiedTrader 연동: 진입 성공 직후 호출하여 포지션에 TP/SL(보험)을 설정.
  - 호출부: `noahai_client/trading/unified_trader.py:700` 인접 분기에서 CCXT 계열(`bybit/okx/bitget`) 처리 추가.

- Phase 2 — OKX: 적용 완료
  - 구현: `noahai_client/trading/exchanges/adapters/okx_futures_adapter.py:...`의 `place_insurance_tp_sl()`
    - ccxt okx는 `create_order(type='conditional')`에 `tpTriggerPx/slTriggerPx`와 `tpOrdPx/slOrdPx='-1'`(시장청산)을 지정해 포지션에 TP/SL 트리거를 등록합니다.
    - 파라미터: `reduceOnly=True`, `positionSide=long|short`, `marginMode='cross'|'isolated'`, `tpTriggerPxType/slTriggerPxType='mark'`
    - UnifiedTrader 연동: 진입 성공 직후 호출.
  - 안전장치: 가격/수량 정밀도 라운딩, 실패 시 경고만 로그 후 런타임 모니터 청산 폴백.

- Phase 3 — Bitget: 적용 완료
  - 구현: `noahai_client/trading/exchanges/adapters/bitget_futures_adapter.py:...`의 `place_insurance_tp_sl()`
    - ccxt bitget는 `create_order()`에 `takeProfitPrice`/`stopLossPrice`를 각각 전달하여 TPSL 플랜 주문을 만듭니다. 두 주문(TP/SL)을 분리 호출하여 포지션에 등록합니다.
    - 파라미터: `reduceOnly=True`, 트리거 기준 `tpTriggerBy/slTriggerBy='mark'`(마크가격). `side`에 따라 ccxt가 `posSide`를 설정합니다.
    - UnifiedTrader 연동: 진입 성공 직후 TP→SL 순서로 호출.
  - 안전장치: 가격/수량 정밀도 라운딩, 실패 시 경고만 로그 후 런타임 모니터 청산 폴백.

## Bybit 구현 세부
- 어댑터: `noahai_client/trading/exchanges/adapters/bybit_futures_adapter.py:287`
  - 가격 정밀도 라운딩: 마켓 precision으로 내림(`_round_price()`)
  - 수량 추론: 미지정 시 `fetch_positions()`에서 해당 심볼 `contracts` 사용
  - 트리거 기준: `triggerPriceType='mark'`
  - 요청: `create_order(symbol, 'market', close_side, amount, params={takeProfit:{triggerPrice}, stopLoss:{triggerPrice}})`
- 트레이더 연동: `noahai_client/trading/unified_trader.py:700`
  - 진입 평균가→TP/SL 가격 산출(퍼센트 기반)
  - LONG: TP=entry*(1+tp%), SL=entry*(1-sl%), SHORT 반대
  - 어댑터가 결과를 반환하면 성공 로그, 실패는 경고로 계속 진행

## 운영 팁(업데이트)
- 변동성별 sl%/tp% 조정과 보험 TP/SL 병행 시, 장애/네트워크 단절에서도 포지션이 방치되지 않음
- CCXT 거래소도 서버‑사이드 보험을 기본 적용(가능한 범위) → 수익률 분포의 좌측 꼬리 리스크 감소
- 런타임 모니터(트레일/브레이크이븐)와 병행: 보험은 최후 안전장치, 더 유리한 가격 청산은 모니터가 담당

---
**교차 거래소: 코인 선정·분석·시그널·AI 동작(코드 기준 사실 정리)**
- 코인 선정(Evaluator)
  - 공통 진입점: trading/evaluator.py:150 의 `select_trading_coins(..., exchange=..., exchange_client=...)`
  - 업비트/빗썸(현물): CCXT 마켓을 기반으로 KRW 페어만 추출 → `quoteVolume` 내림차순 정렬 → 상위 N개 선택. 파일: noahai_client/trading/evaluator.py:535
  - Bybit/OKX/Bitget(선물): CCXT 마켓(`exchange.markets`)에서 USDT 선물(swap/future/contract)만 추출 → 각 심볼 24h 티커 조회 → `quoteVolume` 내림차순 정렬 후 상위 N개 선택. 파일: noahai_client/trading/evaluator.py: 추가된 `_analyze_candidate_coins_ccxt_futures`
  - Binance(선물): Binance 선물 데이터 기반 풀(USDT 페어, 24h 티커 정렬) 사용. 파일: noahai_client/trading/evaluator.py:359

- 분석·시그널(Analyzer)
  - 공통 진입점: UnifiedTrader가 거래소별로 `analyzer.generate_trading_signal(symbol, exchange_name=...)` 호출. 파일: noahai_client/trading/unified_trader.py:382
  - 캔들/시장데이터: 우선 `ExchangeManager.get_klines()`로 거래소별 OHLCV를 불러오고, 실패 시 Binance로 폴백. 파일: noahai_client/trading/analyzer.py:174, noahai_client/trading/exchange_manager.py:415
  - 임계값: `exchange_signal_thresholds.{exchange}` 오버라이드 → 기본 `signal_thresholds`와 병합. 파일: noahai_client/trading/analyzer.py:752
  - 시그널 로직: RSI 극단/과매도·과매수 + 모멘텀/트렌드, 동적 임계값(시장 국면 LOW/NORMAL/HIGH) 보정, 포지션 보호 로직 포함. 파일: noahai_client/trading/analyzer.py:1180 이후

- AI 동작
  - AI 사용 시: 기술 시그널 위에 시장심리/추세 가중·학습 인사이트를 반영해 신호 강화 및 TP/SL/레버리지/사이징을 동적으로 조정. 파일: noahai_client/trading/analyzer.py:348, 1386, 2210
  - 학습 데이터 저장: 거래소별 학습 파일 `ai_learning_data_{exchange}.json`에 기록. 파일: noahai_client/trading/unified_trader.py:1699, noahai_client/trading/exchange_learning_manager.py:72
  - 대시보드 표시: 학습 탭에서 거래소 드롭다운으로 해당 파일을 직접 로드해 표시. 활성 위젯: `ui/widgets/ai_learning_widget.py`

- 현재 차이점/주의(사실)
  - OHLCV 조회 시 어댑터 심볼 정규화 우선 사용으로 Bybit/OKX/Bitget의 `BTC/USDT:USDT` 같은 선물 심볼을 정확히 처리(폴백은 단순 변환). 파일: noahai_client/trading/exchange_manager.py: 변경된 `get_klines()`

- 개선 제안(권장 수정 항목)
  - CCXT 선물 코인 선정 전용 로직 추가: 거래소 어댑터의 `exchange.markets` + `fetch_ticker`를 사용해 각 거래소(바이비트/OKX/비트겟)의 선물 마켓 기준으로 후보군 구성.
  - OHLCV 심볼 정규화 보강: `get_klines()`에서 어댑터의 심볼 정규화(`_normalize_symbol`)를 우선 사용하거나, 거래소별로 `BTC/USDT:USDT` 등 UTA/swap 포맷을 매핑하도록 `_to_ccxt_symbol()` 확장.
  - 임계값 세트: `exchange_signal_thresholds`에 거래소별 기본값 제공(예: 스팟/선물 특성 반영)하여 기본 가시성 향상.
