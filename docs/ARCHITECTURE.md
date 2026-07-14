# NoahAI 시스템 아키텍처 (v3.8.9.28+)

## 🚀 최신 버전 정보

**본 문서 마지막 대규모 갱신 기준**: v3.8.9.11 (2026-01-25)  
**운영 기준 최신 패치 동기화**: v3.8.9.28 (2026-07-10)  
**이전 기준**: v3.8.9.9 (2025-12-27), v3.8.8.3 (2025-10-20)

> **버전 정합성**: 배포 앱의 **인앱 메뉴얼 창 제목**과 `CHANGELOG.md`가 **더 최신 패치 버전**(예: v3.8.9.x)을 가리킬 수 있습니다. 모듈 구조·책임 경계는 본 문서를 따르되, **세부 변경 목록은 CHANGELOG**를 우선하세요. 문서 동기화 규칙은 `DOCUMENTATION_POLICY.md` 참고.
>
> 참고: 2025-10-29 기준 UI는 단일 고정 스킨으로 전환되어 테마 시스템은 사용하지 않습니다. 과거 기록은 `HISTORICAL_THEME_BASELINE.md`를 참고하세요.

## 2026-06-05 패치 기준선 (v3.8.9.21)

- 전역 전체시작 경로 제거 및 거래소별 개별 실행 UX로 정렬
- 다중 거래소 안정화: 거래소별 코인/상태 오염 방지, 시작 실패 상태 동기화 강화
- 로그 태깅 정합화: 거래소 루프/분석 로그에 거래소 식별값 명시
- 현물 어댑터 호환 경로 보강 및 안정성 점검 스크립트 정책 동기화

## 2026-07-10 패치 기준선 (v3.8.9.28 코인 우선 1단계 정합)

- 코인 우선 흡수 계층 고정
  - 1단계 범위를 코인 선택/진입/리스크/학습/로그 경로로 고정하고, 타 자산 확장은 동일 게이트 재사용 정책으로 분리
- 모듈 책임 경계 명시
  - `trading/evaluator.py`: 코인 선정 책임(목표 달성 시 즉시 반환)
  - `trading/trader.py`, `trading/unified_trader.py`: 거래소별 실행 책임(경로 혼재 금지)
  - `trading/risk_manager.py`, `trading/exchange_learning_manager.py`: 리스크/학습 임계값 및 자동조정 책임
  - `log_system/log_adapter.py`: 중복 억제/요약/비차단 기록 책임
- 가드레일/롤백/게이트 기준 고정
  - timezone 혼용 오류 0건
  - fallback 재진입 0건
  - 중복 로그 폭주 0건
  - 필수 회귀(`test_evaluator_selection_flow`, `test_exchange_learning_manager`, `test_auto_update_manager`) 통과

## 2026-06-17 패치 기준선 (v3.8.9.22)

- 사용자 안내 자동화 강화(지원요약/3분 점검본/즉시 조치 순서)
- SaaS 문서 기준선 정합화(증권 SaaS 4대 판단 기준 반영)
- 빌드/배포 문서와 증권 어댑터 hidden import 기준 동기화

## 2026-07-04 패치 기준선 (v3.8.9.27 시작/정지 응답성 근본 패치)

- 거래소 시작/정지 UI 비동기화
  - 거래소 토글 요청을 백그라운드 작업으로 분리해 UI 스레드 블로킹 제거
  - 처리 중 중복 토글 방지 및 상태 배지(`Starting...`/`Stopping...`) 즉시 반영
- Unified 계층 지연 초기화
  - UnifiedTradingManager를 lazy connect 모드로 전환해 로그인 직후 다중 거래소 동시 연결 제거
  - UnifiedTrader도 시작 대상 거래소만 초기화하도록 변경
- API 신호 수집 초기 동기 호출 제거
  - API 신호 관리 시작 시 동기 1회 수집을 제거해 초기 진입 체감 지연 완화

## 2026-07-01 패치 기준선 (v3.8.9.26 유지보수)

- Unified 포트폴리오 할당 자산분류 정합화
  - `upbit`/`bithumb` 자산군을 `crypto`로 고정하여 자산군 분류 일관성 강화
- 거래소별 학습 필터 정합화
  - RiskManager 이력에 `exchange` 태그 저장 경로 추가
  - Binance/Unified 청산 경로 모두 RiskManager 이력 저장 반영
  - Unified 자동조정에서 메모리 이력 부족 시 Recorder DB 이력 보강
- 로그 중복 포맷 재발 방지
  - `log_adapter`에서 선행 시간/레벨 프리픽스 제거 가드 추가

## 2026-05-29 패치 기준선 (v3.8.9.20)

- 실시간 청산 판단 `net_pnl_percent` 산식을 recorder 기준(화폐단위 순손익 환산)으로 정렬
- 릴리즈노트/거래흐름/사용자가이드/인앱 업데이트 공지 동기화
- 이번 패치는 판단-기록 정합화이며, RR/사이징/집중도 가드는 별도 최적화 과제로 분리

## 2026-05-07 패치 기준선 (v3.8.9.19)

- 대시보드 전수 버튼/탭 E2E 테스트 신규 추가: `tests/test_dashboard_full_button_e2e.py` 44 passed
- 핵심 묶음 회귀 재검증: 102 passed (`test_dashboard_full_button_e2e` + `test_menu_regression` + `test_service_tab_policy_snapshot` + `test_settings_backup`)
- 증권 브로커 연결 검증 도구 추가: `scripts/verify_stock_broker_connection.py` (`--all_brokers` 기준 kiwoom/shinhan/miraeAsset 18/18 OK)
- 설정 자동 백업/복구 흐름 고도화: 저장 전 백업(retention 3), 백업 목록 복구 UI 연동
- 최신 전체 회귀 기준: 864 passed, 6 skipped

## 2026-05-03 패치 기준선 (v3.8.9.18)

- 전략 초기화 경로 안정화: 기본값 복구/초기화 시 민감 설정(API 키·브로커 인증정보·backend_url) 보존
- 키움 연결 장애 진단 강화: QAxWidget 관련 사용자 안내에 원본 예외 포함
- 배포 준비 검증(당시 기준): 전체 회귀 336 passed, 6 skipped / prekey 게이트(TEST_STOCK 140 passed, 6 skipped)

## 2026-04-30 운영 기준선 (증권/거래 공통)

현재 운영 전환은 다음 3단계 게이트로 고정한다.

1. 키 입력 전 완료(`prekey`)

- `python scripts/release_gate.py --profile prekey`
- 목적: 키 없이 완료 가능한 코드/정책/문서/진단 항목을 먼저 닫는다.

1. 키 입력 당일 원샷(`key-day`)

- `python scripts/stock_keyday_one_shot.py`
- 목적: 설정/권한/환경이 준비된 상태에서 실브로커 readiness를 단일 명령으로 최종 판정한다.

1. 배포 직전 엄격 검증(`release`)

- `python scripts/release_gate.py --profile release`
- 목적: 배포 차단 조건을 모두 통과해야만 운영 배포를 허용한다.

위 기준은 "수익 보장"이 아니라 "안전한 실행 가능 경로"를 검증하는 구조다.
판단 품질 개선(백테스트/레짐/슬리피지 최적화 등)은 후속 고도화 트랙으로 분리해 관리한다.

## 📌 문서의 범위와 책임 정의

본 문서는 NoahAI Client(v3.8.x)의 구현 상세를 설명하기 이전에,
이 시스템이 무엇을 책임지고 무엇을 책임지지 않는지를 명확히 정의한다.

NoahAI는 금융상품을 판매하거나, 수익을 보장하거나,
**브로커·당사자 계약의 상대**가 아니다.

클라이언트는 사용자가 연결한 API 키와 설정 범위 안에서 **주문 요청을 전송**할 수 있으나,
**체결·잔고 확정·수수료·강제청산**은 항상 외부 거래소·증권사 규칙과 사용자 계약이 담당한다.

NoahAI의 역할은 다음으로 한정된다.

- 시장·계정·목표 정보를 종합하여 **판단 환경을 구조화**
- 판단 근거, 리스크, 대안 시나리오를 **기록·설명·비교**
- 모든 판단과 결과를 **검증·재현·환류 가능한 로그로 관리**
- 시간이 지날수록 더 신중해지도록 **의사결정 파이프라인을 고도화**

**주문 요청 전송**은 클라이언트가 외부 API를 호출해 수행할 수 있으나,
**체결·예탁·최종 계좌 상태**는 외부 거래소·증권사·금융기관 시스템이 확정한다.

이 문서는 특정 자산군이나 거래소 구현이 아니라,
자산군이 바뀌어도 유지되는 **AI 자산 의사결정 인프라의 구조**를 설명하는 문서다.

## 도메인 분류 체계 (2026-04-25)

아키텍처 설계와 UI/문서 명명은 아래 도메인 기준을 공통 적용한다.

- **Asset Decision Domain**: 암호화폐, 주식/증권, ETF 등 자산군 의사결정
- **Life Finance Domain**: 대출 비교, 보험 선택, 예적금/채권 비교, 개인 재무관리
- **Risk Protection Domain**: 금융사기 탐지, 이상거래 탐지, 고위험 선택 회피 보조
- **Accessibility Domain**: 고령층/디지털 약자 지원, 쉬운 용어·음성 기반 보조
- **Assistant Interface Layer**: 대화형 설명/비교/경고 인터페이스, 질의응답 허브

위 분류는 메뉴 이름보다 우선하는 상위 설계 기준이며,
`글로벌자산` 같은 포괄 명칭 대신 목적 기반 명칭(`자산 통합`, `글로벌 금융 인사이트`)을 우선한다.

이 정의는 이후 등장하는 모든 모듈, 거래소, 증권사, 자산군 설명에
우선 적용되는 최상위 원칙이다.
아래의 어떤 기술 구현도 이 책임 경계를 침범하지 않는다.

## 🚀 v3.8.9.11 주요 변경사항 (2026-01-25)

### TP/SL -2021 오류 근본 수정

- **문제**: GALA, JASMY 등 저가 알트코인에서 TP 주문 실패 (`-2021: Order would immediately trigger`)
- **근본 원인**:
  1. `trader.py`: 키 이름 불일치 (`price_precision` vs `pricePrecision`)로 `price_prec`가 항상 2로 고정
  2. `binance_client.py`: TP 방향 검증 누락 (SHORT 포지션에서 TP > 현재가인 경우 감지 못함)
- **수정 내용**:
  - 키 이름 호환성 처리 (`pricePrecision` 또는 `price_precision` 둘 다 지원)
  - 저가 코인 자동 감지 및 정밀도 강제 조정 (0.001~0.02 범위)
  - TP 방향 검증 추가 (LONG/SHORT 포지션별 올바른 방향 확인)
- **효과**: 모든 저가 알트코인에서 정확한 TP/SL 가격 계산 및 주문 성공

### AI 자산 의사결정 인프라 확장 (진행 중)

- ETF/주식 판단 인프라 확장: 자산 해석·비교·리스크 설명 UI 기본 구조 완료 (2026-01-18)
- StockExchange 인터페이스: 자산군별 판단 로직을 연결하기 위한 표준 판단 인터페이스
- 키움증권 어댑터: 증권사 API와의 집행 연동 계층
- 대시보드 확장: 암호화폐 / ETF / 주식 자산군에 동일한 판단·기록 UX 적용

판단·설명·기록·환류는 NoahAI가 담당하며,
주문·체결·자금 이동은 항상 외부 증권사·거래소 API가 수행한다.

## 🚀 v3.8.8.9 주요 아키텍처 변경사항 (2025-10-29)

## 🚀 v3.8.8.3 주요 아키텍처 변경사항 (2025-10-20)

### 바이낸스 자체 API 전환 완료

- **이전**: CCXT + `binance_extended_api.py` + `legacy_binance_adapter.py` 혼재
- **현재**: `api/binance_client.py` 단일 통합 클라이언트
- **장점**: 성능 향상, 안정성 증대, 유지보수성 개선

### 제거된 중복 파일들

- `trading/binance_extended_api.py` → `api/binance_client.py`로 통합
- `trading/legacy_binance_adapter.py` → CCXT 브리지 불필요

### 새로운 기능

- **동적 코인 재선택**: 1시간마다 시장 상황 분석 후 코인 재선택
- **최적화된 WebSocket**: 포지션 모니터링 전용, API 기반 분석으로 성능 향상
- **통합된 고급 API**: 미체결약정, 롱/숏 비율, 테이커 비율 등
- **WebSocket 아키텍처 개선**: 46초 지연 문제 해결, 즉시 시작 가능
- **AI 학습 데이터 시스템**: 모든 거래 신호 자동 수집 및 패턴 분석
- **실시간 로그 시스템**: 사용자 가시성을 위한 카테고리별 로그 분류

## 🏗️ 전체 시스템 구조

### 📁 프로젝트 구조

```text
noahai_client/
├── main.py                 # 메인 애플리케이션 진입점
├── ui/                     # 사용자 인터페이스
│   ├── dashboard_modern.py  # 메인 대시보드 (CustomTkinter-only, PyQt 제거)
│   ├── login_modern.py      # 로그인 화면 (CustomTkinter)
│   └── settings_modern.py   # 설정 화면 (CustomTkinter)
├── trading/               # 거래 로직
│   ├── trader.py          # 메인 거래 엔진 (Binance 전용 - 자체 API)
│   ├── unified_trader.py  # 통합 거래 엔진 (CCXT 거래소 전용)
│   ├── evaluator.py       # 코인 선택 엔진 (AI 기반 과학적 평가)
│   ├── exchange_manager.py # 거래소 관리자 (v3.3 신규)
│   ├── unified_trading_manager.py # 통합 거래 관리자 (CCXT 거래소용)
│   ├── api_signal_manager.py # API 신호 관리자 (v3.3 신규)
│   ├── ai/                # AI 모듈
│   │   ├── ai_manager.py  # AI 관리자
│   │   ├── auto_optimizer.py # 자동 최적화
│   │   └── openai_client.py # OpenAI 클라이언트
│   ├── exchanges/         # 거래소 모듈 (v3.3 확장)
│   │   ├── base_exchange.py # 기본 거래소 클래스
│   │   ├── exchange_factory.py # 거래소 팩토리
│   │   ├── exchange_manager.py # 거래소 관리자
│   │   ├── interfaces/    # 거래소 인터페이스
│   │   │   ├── exchange_interface.py
│   │   │   ├── futures_exchange.py
│   │   │   ├── spot_exchange.py
│   │   │   └── stock_exchange.py         # 증권 거래 인터페이스 (v3.8.9.11+)
│   │   └── adapters/      # 실제 사용되는 거래소 어댑터들
│   │       ├── binance_futures_adapter.py # 바이낸스 선물
│   │       ├── bybit_futures_adapter.py  # 바이비트 선물
│   │       ├── okx_futures_adapter.py    # OKX 선물
│   │       ├── bitget_futures_adapter.py # 비트겟 선물
│   │       ├── bithumb_spot_adapter.py   # 빗썸 현물
│   │       ├── upbit_spot_adapter.py     # 업비트 현물
│   │       └── kiwoom_stock_adapter.py   # 키움증권 주식/ETF (v3.8.9.11+)
│   └── recorder.py        # 거래 기록 관리
├── api/                   # API 연동
│   ├── backend_api.py     # 백엔드 서버 연동
│   └── binance_client.py  # 바이낸스 API 클라이언트 (WebSocket API 명칭 통일)
├── config/                # 설정 파일
│   ├── settings.json      # 메인 설정
│   ├── settings_template.json # 설정 템플릿
│   └── token.json         # 사용자 토큰
└── data/                  # 데이터 저장소
    ├── trading.db         # 거래 데이터베이스
    └── logs/              # 로그 파일
```

## 🔄 시스템 워크플로우

### 1. 애플리케이션 시작 (v3.8 개선)

```text
main.py → 로그인 → 거래소 선택 → API 키 설정 → 대시보드 초기화 → 판단·기록·검증 파이프라인 시작
```

### 2. 거래 실행 플로우 (거래소별 분리 - 혼재 금지)

```text
🔥 바이낸스 전용 경로:
main.py.trading_loop() → AI 분석 → trader.py.execute_trades() → api/binance_client.py → 바이낸스 API

🔥 CCXT 거래소 전용 경로:
main.py._start_unified_trading() → unified_trader.start_trading() → CCXT 어댑터 → 각 거래소 API

❌ 절대 금지: unified_trader.py에서 바이낸스 처리
❌ 절대 금지: trader.py에서 CCXT 거래소 처리
❌ 절대 금지: 바이낸스에서 unified_trader.py 호출
❌ 절대 금지: CCXT 거래소에서 trader.py 호출
```

### 3. 멀티 거래소 관리 (v3.3 → v3.8 고도화)

```text
거래소 선택 → ExchangeManager → 거래소별 클라이언트 생성 → 통합 관리
```

### 3. 사용자 상태 관리

```text
로그인 → 토큰 저장 → 서버 상태 체크 → 중복 실행 방지
```

## 🧩 핵심 모듈

### 🤖 AI 시스템

- **AIManager**: AI 신호 생성 및 분석
- **AutoOptimizer**: 실시간 파라미터 최적화
- **OpenAIClient**: OpenAI API 연동

### 💱 거래소 시스템 (중요: 혼재 금지 가이드라인)

- **Binance 전용**: `trader.py` + `api/binance_client.py` (python-binance)
  - **절대 금지**: `unified_trader.py`에서 바이낸스 처리
  - **특징**: 고성능 실시간 거래, WebSocket, 고급 주문 타입, Binance Algo Order API
  - **TP/SL**: Binance Algo Order API 사용 (v3.8.9.9+), 가격 정밀도 자동 조정 (v3.8.9.11+)
  - **시작/정지**: `main.py.start_trading_loop()` / `main.py.stop_trading_loop()`
- **CCXT 거래소**: `unified_trader.py` + `trading/exchanges/adapters/` (CCXT 라이브러리)
  - **대상**: Bybit, OKX, Bitget, Upbit, Bithumb
  - **특징**: 표준화된 API, 크로스 플랫폼 호환성
  - **시작/정지**: `unified_trader.start_trading(exchange)` / `unified_trader.stop_trading(exchange)`
- **증권/ETF 거래소** (v3.8.9.11+): `StockExchange` 인터페이스 + 증권사 어댑터
  - **책임 분리**: 판단·설명·기록·리스크 분석은 NoahAI 클라이언트가 담당. **주문 API 호출**은 사용자가 연결한 키로 클라이언트가 수행할 수 있으나, **계좌·체결·예탁·분쟁의 법적 1차 주체는 증권사·사용자**이다. (암호화폐 경로의 실행 연계와 같은 원칙.)
  - 연동·실행 가능 여부는 **빌드·설정·상용 공개 단계**에 따라 다르며, 인앱 「📈 증권/주식/ETF」·`CHANGELOG`가 체감 기준이다.
  - **대상**: 키움증권 (주식/ETF), 향후 확장 예정
  - **특징**: 증권사 API와의 집행 연동 계층, 주식/ETF 자산군에 대한 판단·기록 인터페이스
  - **구조**: `trading/exchanges/interfaces/stock_exchange.py` + `trading/exchanges/adapters/kiwoom_stock_adapter.py`
- **ExchangeManager**: 거래소 통합 관리 및 잔고 조회, 설정 반영/재연결
- **UnifiedTradingManager**: CCXT 거래소 통합 관리
- **APISignalManager**: 거래소별 API 신호 교환 및 학습 데이터 생성

#### 🚨 중요 가이드라인 (2025-01-15 업데이트)

1. **바이낸스는 절대 `unified_trader.py`를 사용하지 않음**
2. **CCXT 거래소들은 절대 `trader.py`를 사용하지 않음**
3. **`main.py`에서 거래소별로 올바른 경로로 라우팅**
4. **각 거래소별 어댑터는 해당 거래소만 담당**
5. **중첩이나 중복 없이 계층적 구조 유지**

### 🎛️ 대시보드 시스템 (중요)

- **ModernDashboard**: 메인 대시보드 (CustomTkinter)
- **서비스 구조**: 블록체인(암호화폐), 주식/증권(ETF 포함), 부동산 서비스 분리
- **포지션 표시 로직**: 거래소별 분기 처리
  - **바이낸스**: `main_app.trader.active_positions` 참조
  - **CCXT 거래소**: `unified_trader.active_positions[exchange]` 참조
  - **증권사**: `stock_exchange` 인터페이스를 통한 포지션 조회 (v3.8.9.11+)
- **통계 통합**: 바이낸스 + CCXT 거래소 데이터 합산
- **UI 패턴 일관성**: 모든 서비스에서 동일한 2단 레이아웃 구조 유지
  - 좌측: 제어/잔고/포지션/통계
  - 우측: 실시간 로그

### 🎨 UI 스타일 및 고정 스킨 (현재 기준)

- **CustomTkinter-only + 단일 고정 스킨**: 현재 런타임은 테마 전환형 구조가 아니라 고정된 시각 규칙을 사용함
- **고정 색상/폰트 규칙**: 주요 UI는 고정 색상 상수와 안전한 폰트 폴백을 기준으로 일관성을 유지함
- **과거 테마 시스템은 역사적 참고**: 예전 `ThemeManager` 기반 설계 흔적은 문서/백업 참고용이며, 현재 배포 기준의 핵심 구조는 아님
- **운영 원칙**: 새 위젯은 현재 고정 스킨 톤과 레이아웃 규칙을 따르되, 기능 회귀 없이 붙일 수 있어야 함

### 🔐 보안 시스템

- **UserStatusManager**: 사용자 상태 관리
- **BackendAPI**: 서버 연동 및 인증
- **TokenManager**: 토큰 관리 및 갱신

## 📊 데이터 흐름 (기술 도메인 맥락)

### 코인 선택 시스템 (evaluator.py, 도메인 예시)

```text
거래소 API → 심볼 수집 → 5가지 점수 계산 → 메이저/알트 비율 조정 → 최적 코인 선정
├── 1단계: 거래소별 심볼 수집 (바이낸스/업비트/바이비트 등)
├── 2단계: 다차원 점수 계산 (기술적/변동성/거래량/트렌드/리스크)
├── 3단계: 시장 상황별 비율 조정 (상승장/하락장/횡보장)
├── 4단계: 하이브리드 접근법 (캐싱 + 백업 + 하드코딩)
└── 5단계: 최종 코인 목록 반환
```

### 거래 데이터 (도메인 예시)

```text
시장 데이터 → AI 분석 → 거래 신호 → 거래 실행 → 결과 기록 → DB 저장
```

### 거래소별 데이터 수집 (v3.3 신규, 도메인 예시)

```text
거래소 API → ExchangeManager → 잔고/가격 조회 → 대시보드 표시
거래소 API → APISignalManager → 신호 수집 → 학습 데이터 생성
```

### 멀티 거래소 통합 관리 (도메인 예시)

```text
거래소 선택 → ExchangeFactory → 거래소별 클라이언트 생성 → 통합 인터페이스
```

## 🏛️ 기술 도메인 구조 (UI 메뉴 vs 기술 도메인)

NoahAI는 사용자가 보는 **UI 메뉴 구조**와 백엔드 **기술 도메인 구조**가 다릅니다.

### 사용자가 보는 메뉴 (UI 수준)

```text
📱 대시보드 탭
├── 🚀 암호화폐 (Blockchain/Futures)
├── 📈 주식/증권 (Stocks/Securities)
├── 🧭 자산 통합 (확정, v3.9부터)
├── 💰 생활금융 ✅ (핵심 기능 구현, v3.8.9.19)
├── 🎯 AlphaArena (LLM 기반 모드)
└── 📊 커뮤니티 (예정)
```

### 기술 도메인 구조 (시스템 수준)

#### 1. **의사결정 인터페이스 계층 (Decision Interface Layer)**

- **역할**: AI 판단 신호 생성 및 설명의 일관된 인터페이스 제공
- **구현**: `Decision`, `Recommendation` 기본 객체 정의
- **적용**: 모든 자산군(암호화폐, 주식, 부동산, 생활금융)에서 동일하게 사용

#### 2. **자산 의사결정 도메인 (Asset Decision Domain)**

- **암호화폐 (Blockchain)**
  - 기술 모듈: `trader.py`, `api/binance_client.py`, CCXT 거래소 어댑터
  - 판단 엔진: `evaluator.py` (코인 선택), `ai_manager.py` (신호 생성)
  - 기록/검증: `recorder.py`, 거래 이력 로그
  - 상태: ✅ 실제 운영 중 (6개 거래소)

- **주식/증권/ETF (Securities)**
  - 기술 모듈: `StockExchange` 인터페이스, `kiwoom_stock_adapter.py`
  - 판단 엔진: 자산 해석, 섹터 분석, 위험도 평가
  - 기록/검증: 주식 거래 로그, 포트폴리오 분석
  - 상태: 🚧 혼합 상태 (UI/기록/가드레일 구현 + Mock 검증 완료, 실API 실거래 검증 고도화 진행)

- **글로벌 금융자산 (Global Financial Assets)**
  - 기술 모듈: 부동산/국제 자산 관련 API 어댑터 (향후)
  - 판단 엔진: 자산 추적, 포트폴리오 분석
  - 상태: 📋 기획 단계 (메뉴명 "자산 통합" 확정)

#### 3. **생활금융 도메인 (Daily Life Finance Domain)** ✅ Phase F 완료 (2026-05-03)

- **대출 비교 (Loan Comparison)** ✅
  - 기술 모듈: `trading/life_finance_products.py`, `data/finance_products/loans.json` (20개)
  - 판단 엔진: 금리·수수료·약정 비교, loan_type 필터, 원리금균등 월납입액 계산
  - AI 연동: `LifeFinanceAssistant` → `COMPARE_LOAN` 인텐트
  - 상태: ✅ 구현 완료

- **보험 선택 (Insurance Selection)** ✅
  - 기술 모듈: `trading/life_finance_products.py`, `data/finance_products/insurances.json` (20개)
  - 판단 엔진: 보장 범위·보험료·기간 비교
  - 상태: ✅ 구현 완료

- **예금/적금/채권 (Deposits/Bonds)** ✅
  - 기술 모듈: `trading/life_finance_products.py`, `data/finance_products/savings.json` (20개, ISA형)
  - 판단 엔진: 이율·기간·비과세 여부 분석
  - 상태: ✅ 구현 완료

- **세무 계산 (Tax Calculation)** ✅ NEW (2026-05-03)
  - 기술 모듈: `trading/tax_calculation_service.py`
  - 판단 엔진: 연말정산·금융소득종합과세·금투세·ISA/IRP 절세 비교
  - AI 연동: TAX_SETTLEMENT / CHECK_FINANCIAL_INCOME_TAX / CALC_INVESTMENT_TAX / COMPARE_TAX_ACCOUNTS
  - 테스트: `tests/test_tax_calculation_service.py` 53 passed
  - 상태: ✅ 구현 완료

- **금융사기 탐지 (Fraud Detection)** ✅ NEW (2026-05-03)
  - 기술 모듈: `trading/fraud_detection_service.py`
  - 판단 엔진: 보이스피싱·스미싱 17개 패턴 / z-score 이상거래 / 약탈적 대출 탐지
  - AI 연동: ANALYZE_FRAUD_MESSAGE / DETECT_ABNORMAL_TX / CHECK_PREDATORY_LOAN
  - 테스트: `tests/test_fraud_detection_service.py` 32 passed
  - 상태: ✅ 구현 완료

#### 4. **위험보호 도메인 (Risk Protection Domain)**

- **거래 이상 감지 (Trade Anomaly Detection)**
  - 기술 모듈: 사용자 거래 패턴 분석기
  - 판단 엔진: 비정상 거래 자동 감지 및 경고
  - 상태: ✅ 기본 기능 운영 중

- **포지션 리스크 경고 (Position Risk Alert)**
  - 기술 모듈: 동적 손실한도 계산기, 레버리지 가드레일
  - 상태: ✅ 암호화폐/주식 상시 운영(기본 안전 디폴트 + 사용자 설정 기반 실주문)

#### 5. **접근성 도메인 (Accessibility Domain)**

- **고령층/디지털 약자 지원 (Elderly & Digital Disadvantaged)**
  - 기술 모듈: 음성 UI, 쉬운 용어 번역, 시각 보조
  - 판단 엔진: 초보자 수준의 설명 자동 생성
  - 상태: 🟡 베타 운영 (TTS 사용 가능, STT는 SpeechRecognition+PyAudio 환경에서 선택 사용)

- **다언어 지원 (Multi-language)**
  - 기술 모듈: 메뉴/상담 다국어 지원
  - 상태: 📋 로드맵

#### 6. **기록·검증·환류 도메인 (Audit & Replay Domain)**

- **판단 로그 (Decision Logging)**
  - 기술 모듈: `recorder.py`, 통합 로그 저장소
  - 구조: `판단 근거` + `신호 생성 시각` + `리스크 평가` + `실행 결과`
  - 상태: ✅ 운영 중

- **감시 가능성 (Auditability)**
  - 기술 모듈: 판단 재검증 엔진, 성과 분석기
  - 구조: 사후 검증으로 "AI 판단이 맞았는가" 추적
  - 상태: ✅ 운영 중

- **재현성 (Reproducibility)**
  - 기술 모듈: Replay 엔진 (동일 조건에서 판단 재시뮬레이션)
  - 상태: ✅ 계획 중

### 도메인 간 데이터 흐름

```text
사용자 요청 (UI 메뉴)
    ↓
어느 도메인인가? (의사결정 → 자산/생활금융/위험보호/접근성 분류)
    ↓
해당 기술 모듈 실행 (Adapter/Analyzer/Engine)
    ↓
판단·설명·리스크 평가
    ↓
기록·검증·환류 계층 (Audit & Replay)
    ↓
사용자에게 결과 표시 (UI)
```

### 주의: 메뉴명은 확정이 아닙니다

- "🧭 자산 통합" 메뉴명은 v3.9부터 확정 적용됩니다. 기술 도메인 구조는 메뉴명 변경과 무관하게 일관성을 유지합니다.
- 기술 도메인 구조는 메뉴명 변경과 무관하게 일관성을 유지합니다.

---

## 📊 데이터 흐름

### 코인 선택 시스템 (evaluator.py)

```text
거래소 API → 심볼 수집 → 5가지 점수 계산 → 메이저/알트 비율 조정 → 최적 코인 선정
├── 1단계: 거래소별 심볼 수집 (바이낸스/업비트/바이비트 등)
├── 2단계: 다차원 점수 계산 (기술적/변동성/거래량/트렌드/리스크)
├── 3단계: 시장 상황별 비율 조정 (상승장/하락장/횡보장)
├── 4단계: 하이브리드 접근법 (캐싱 + 백업 + 하드코딩)
└── 5단계: 최종 코인 목록 반환
```

### 거래 데이터

```text
시장 데이터 → AI 분석 → 거래 신호 → 거래 실행 → 결과 기록 → DB 저장
```

### 거래소별 데이터 수집 (v3.3 신규)

```text
거래소 API → ExchangeManager → 잔고/가격 조회 → 대시보드 표시
거래소 API → APISignalManager → 신호 수집 → 학습 데이터 생성
```

### 멀티 거래소 통합 관리

```text
거래소 선택 → ExchangeFactory → 거래소별 클라이언트 생성 → 통합 인터페이스
```

### 사용자 데이터

```text
로그인 → 토큰 생성 → 서버 저장 → 상태 체크 → 세션 관리
```

## 🔧 거래소별 최적화 전략 차이점 (2025-10-21 업데이트)

### 🎯 설계 의도와 아키텍처 분리

**이 시스템은 의도적으로 거래소별로 다른 최적화 전략을 사용합니다:**

#### **바이낸스 (독립 시스템)**

- **API**: python-binance (전용 API)
- **거래 유형**: 선물 거래
- **최적화 시스템**: `optimizer.py`의 완전한 AI 캐싱 시스템 활용
- **특징**:
  - 고급 주문 지원 (OCO, Trailing Stop)
  - 안정적이고 검증된 AI 최적화 시스템
  - `trader.py`에서 `optimizer.optimize_parameters()` 직접 호출
  - AI 캐싱: `_get_cached_ai_decision()`, `_cache_ai_decision()` 활용

#### **CCXT 거래소 (통합 시스템)**

- **API**: CCXT (통합 API)
- **거래 유형**:
  - **선물**: 바이비트, OKX, 비트겟
  - **현물**: 업비트, 빗썸
- **최적화 시스템**: 거래소별 특성에 맞는 자체 최적화 로직
- **특징**:
  - 거래소별 특성 반영 (현물/선물, SHORT 제한 등)
  - 유연한 최적화 전략
  - `unified_trader.py`에서 자체 파라미터 생성
  - AI 강화: `_get_ai_enhanced_parameters_unified()` 메서드

### 📊 왜 다른 최적화 전략을 사용하는가?

#### **1. 거래소별 특성 차이**

```text
바이낸스 (선물):
├── 레버리지 거래 가능
├── SHORT/LONG 모두 지원
├── 고급 주문 타입 지원
└── 안정적인 API

업비트/빗썸 (현물):
├── 레버리지 없음
├── SHORT 거래 제한
├── KRW 페어 거래
└── 현물 특성 반영 필요

바이비트/OKX/비트겟 (선물):
├── 다양한 레버리지
├── SHORT/LONG 지원
├── CCXT 통합 API
└── 거래소별 특성 차이
```

#### **2. API 차이점**

- **바이낸스**: python-binance (전용 라이브러리)
- **CCXT**: 통합 라이브러리 (다양한 거래소 지원)

#### **3. 최적화 요구사항 차이**

- **바이낸스**: 검증된 AI 최적화 시스템으로 안정성 우선
- **CCXT**: 거래소별 특성에 맞는 유연한 최적화 필요

### 🔄 현재 구현 상태

#### **바이낸스 (`trader.py`)**

```python
# optimizer.py의 AI 캐싱 시스템 활용
base_params = self.optimizer.optimize_parameters(symbol, signal_data)
# AI 캐싱: _get_cached_ai_decision(), _cache_ai_decision() 자동 활용
```text

#### **CCXT 거래소 (`unified_trader.py`)**

```python
# 자체 파라미터 생성 (거래소별 특성 반영)
optimized_params = self._get_ai_enhanced_parameters_unified(
    exchange_name, symbol, analysis, pre_entry_analysis
)
# 거래소별 특화 최적화 로직
```

### ✅ 설계의 장점

#### **1. 거래소별 특성 최적화**

- **바이낸스**: 안정적이고 검증된 AI 시스템
- **CCXT**: 거래소별 특성에 맞는 유연한 최적화

#### **2. 유지보수성**

- 각 거래소의 특성을 독립적으로 관리
- 거래소별 업데이트가 다른 거래소에 영향 없음

#### **3. 확장성**

- 새로운 거래소 추가 시 해당 거래소 특성에 맞는 최적화 구현 가능
- 기존 거래소에 영향 없이 확장 가능

### 🚨 개발자 주의사항

#### **절대 금지 사항**

1. **바이낸스에서 CCXT 최적화 방식 사용 금지**
2. **CCXT 거래소에서 바이낸스 최적화 방식 사용 금지**
3. **거래소별 특성을 무시한 통일된 최적화 방식 강제 적용 금지**

#### **올바른 접근 방법**

1. **각 거래소의 특성을 이해하고 그에 맞는 최적화 구현**
2. **기존 설계 의도를 존중하고 거래소별 분리 원칙 준수**
3. **새로운 거래소 추가 시 해당 거래소 특성에 맞는 최적화 전략 선택**

### 📈 향후 발전 방향

#### **1. 거래소별 AI 학습 데이터 분리**

- 각 거래소의 거래 패턴을 독립적으로 학습
- 거래소별 특성에 맞는 AI 모델 개발

#### **2. 거래소별 성능 최적화**

- 각 거래소의 API 특성에 맞는 성능 튜닝
- 거래소별 최적화 알고리즘 개선

#### **3. 통합 모니터링 시스템**

- 거래소별 성능 비교 및 분석
- 전체 시스템 성능 최적화

## 🔧 설정 관리

### 설정 파일 구조

- **settings.json**: 런타임 설정
- **settings_template.json**: 기본 설정 템플릿
- **token.json**: 사용자 인증 정보

### 설정 우선순위

1. 사용자 입력 (UI)
2. settings.json
3. settings_template.json
4. 기본값

## 🌐 네트워크 통신

### 백엔드 서버

- **URL**: <https://daltrading.net>
- **인증**: JWT 토큰 기반
- **주요 API**:
  - `/auth/api_login`: 로그인
  - `/auth/check_status`: 상태 체크
  - `/auth/kpi/event`: 클라이언트 KPI 이벤트 적재
  - `/api/signals`: 거래 신호 수신

### KPI 연동 현황 (클라이언트 → 서버)

- **연동 완료**
  - 로그인 성공/실패 이벤트 전송
  - AI 시장 리포트 생성/실패 이벤트 전송
- **아직 미연동**
  - 실시간 로그 본문 업로드
  - 학습 데이터 원문 업로드
  - 일/주/월 리포트 파일 원문 업로드
- **원칙**
  - 원문 로그/학습/리포트는 기본적으로 로컬 저장
  - 서버에는 집계/운영 KPI 이벤트만 전송

### 공개 KPI와 운영 KPI 해석 기준

- 공개 KPI: 외부 페이지/문서에 노출되는 코호트 기반 정적 공개 스냅샷
- 운영 KPI: 관리자 대시보드에서 확인하는 익명 이벤트 기반 최신 운영 집계
- 따라서 웹사이트 공개 KPI와 관리자 KPI는 숫자 구조가 달라도 이상이 아니다.

### v3.8.9.28 이후 누적되는 운영 메타 KPI

- 평균 보유시간(`hold_seconds`)
- 거래 처리/응답시간 계열
- `ai_inference_completed` 및 AI 응답시간 계열

위 항목은 28버전 배포 후부터 본격 누적되므로, 초기에는 0 또는 공란으로 보일 수 있다.

### 거래소 API (v3.3 확장)

- **바이낸스**: WebSocket + REST API (python-binance 라이브러리)
- **업비트**: REST API (ccxt 라이브러리)
- **빗썸**: REST API (ccxt 라이브러리)

## 🛡️ 보안 아키텍처

### 인증 시스템

```text
사용자 로그인 → JWT 토큰 발급 → 토큰 저장 → API 요청 시 토큰 사용
```

### 중복 실행 방지

```text
앱 시작 → 토큰 확인 → 서버 상태 체크 → 중복 감지 시 종료
```

### API 키 관리

```text
환경설정 → API 키 입력 → 암호화 저장 → 거래소 연동
```

## 📈 성능 최적화

### WebSocket 아키텍처 개선 (2025-10-20 완료)

- **문제**: 코인 선택 시 모든 코인 WebSocket 구독으로 인한 46초 지연
- **해결**: API 기반 분석으로 변경, WebSocket은 포지션 모니터링에만 사용
- **효과**: 시작 시간 46초 → 즉시 시작

### 비동기 처리

- WebSocket 연결을 통한 실시간 포지션 모니터링 (최적화됨)
- 멀티스레딩을 통한 UI와 거래 로직 분리
- 백그라운드에서 AI 분석 및 최적화 실행

### 메모리 관리

- 거래 데이터베이스 최적화
- 로그 파일 자동 정리
- 캐시 시스템을 통한 API 호출 최소화
- WebSocket 구독 최적화로 리소스 절약

## 🔄 확장성

### 새로운 거래소 추가 (v3.8 가이드)

1. `BaseExchange` 상속하여 새 클라이언트 구현
2. `ExchangeFactory`에 새 거래소 등록
3. `ExchangeManager`에 새 거래소 지원 추가
4. UI에 새 거래소 옵션 추가
5. `APISignalManager`에 신호 수집 로직 추가

### 새로운 AI 모델 추가

1. `AIManager`에 새 모델 인터페이스 구현
2. 설정에 모델 선택 옵션 추가
3. 성능 비교 및 자동 선택 로직 구현

### 📌 자산군 확장 공통 원칙

- 자산군이 달라져도 판단·기록·검증 파이프라인은 동일하다
- 암호화폐, ETF, 주식, 해외주식, 선물, 부동산은 모두 같은 판단 계층을 사용한다
- 실행은 항상 외부 금융기관·거래소 API가 담당한다
- NoahAI는 실행 주체가 아닌 AI 자산 의사결정 인프라로만 동작한다

## 🆕 v3.3 신규 모듈 상세

### Evaluator (코인 선택 엔진) - 핵심 모듈

- **역할**: AI가 거래할 최적의 코인들을 과학적으로 선별하는 핵심 엔진
- **주요 기능**:
  - **5가지 차원 점수 계산**: 기술적/변동성/거래량/트렌드/리스크 점수
  - **거래소별 특화 선택**: 바이낸스/업비트/바이비트 등 각 거래소 특성 반영
  - **시장 상황별 동적 조정**: 상승장/하락장/횡보장에 따른 메이저/알트 비율 자동 조정
  - **하이브리드 접근법**: 캐싱 + 백업 + 하드코딩으로 안정성과 성능 동시 확보
- **성능 최적화**:
  - **초기 로딩**: 4분 → 즉시 (99% 개선)
  - **API 의존성**: 100% → 30% (70% 감소)
  - **안정성**: 70% → 99% (29% 향상)
- **사용법**: `evaluator.select_trading_coins(num_alt, num_major, regime, exchange)`

### ExchangeManager (거래소 관리자)

- **역할**: 선택된 거래소의 클라이언트를 동적으로 생성 및 관리 (v3.8: 설정 변경 시 안전 재로딩)
- **주요 기능**:
  - 거래소별 클라이언트 캐싱
  - 잔고 조회 통합 인터페이스
  - 거래소 전환 시 자동 클라이언트 교체
- **사용법**: `exchange_manager.get_exchange_balance()`

### APISignalManager (API 신호 관리자)

- **역할**: 모든 거래소에서 시장 데이터를 수집하여 AI 학습에 활용
- **주요 기능**:
  - 1분 간격 자동 신호 수집
  - 거래소별 데이터 정규화
  - 학습 데이터 자동 생성
- **사용법**: 백그라운드에서 자동 실행

### ExchangeFactory (거래소 팩토리)

- **역할**: 거래소별 클라이언트 인스턴스를 생성하는 팩토리 패턴
- **주요 기능**:
  - 거래소별 클라이언트 생성
  - 설정 기반 클라이언트 초기화
  - 일관된 인터페이스 제공
- **사용법**: `ExchangeFactory.create_exchange(exchange_name, config)`

### BaseExchange (기본 거래소 클래스)

- **역할**: 모든 거래소 클라이언트의 공통 인터페이스 정의
- **주요 메서드**:
  - `connect()`: 거래소 연결
  - `get_balance()`: 잔고 조회
  - `get_current_price()`: 현재가 조회
  - `get_account_info()`: 계정 정보 조회

### 🔄 v3.8 아키텍처 업데이트 요약

- 설정 저장 시 런타임 재초기화 경로 도입: `UnifiedTradingManager.reload_settings()`, `ExchangeManager.update_settings()`로 재시작 없이 반영
- 대시보드가 메인 애플리케이션의 매니저 인스턴스를 재사용하여 상태 불일치 해소 (`ModernDashboard` → `main_app.unified_manager` 재사용)
- `UnifiedTradingManager`가 `refresh_exchange()`를 제공하여 특정 거래소만 선택 재연결 가능
- `ExchangeManager`가 Bybit/OKX/Bitget 키 검증 및 가용성 노출을 포함하도록 확장
- `Analyzer`가 가능한 경우 `ExchangeManager`를 통해 현재가를 조회(폴백: Binance) — 캔들 데이터도 `ExchangeManager.get_klines()`로 단계적 전환
- `UnifiedTrader`가 선물 거래소에서 레버리지/마진 타입을 주문 전 자동 설정하며, CCXT 어댑터에는 심볼 정규화(`BASE/QUOTE`)를 적용
  - 기본 마진 타입은 설정의 `default_margin_type`(기본 `ISOLATED`)을 사용
- 거래소별 시그널 임계값(`exchange_signal_thresholds`)을 설정에서 정의하고, Analyzer가 컨텍스트(거래소)에 따라 임계값을 적용
- 경로 체계 문서화: `docs/STORAGE_PATHS.md`에 개발/배포 환경의 저장 경로 및 계정별 폴더 구조 정리

#### WebSocket API 명칭 통일과 사용 원칙

- 구독: `subscribe_symbol(symbol)`, `unsubscribe_symbol(symbol)`
- 조회: `get_latest_ticker(symbol)`, `get_latest_orderbook(symbol)`
- 접근 가드:

  ```python
  client = getattr(self, 'binance_client', None)
  ws = getattr(client, 'websocket_manager', None) if client else None
  if not ws: return
  ```

#### 구독 유지 정책(retention policy)

- 기본 구독: 메이저 심볼(예: BTCUSDT, ETHUSDT)은 항상 유지
- 유지 조건: 열린 포지션 존재 또는 최근 거래 신호 발생 심볼
- 정리 조건: 상기 조건이 아닌 심볼은 배치 단위로 해제
- 구현: `main.manage_trading_websocket_subscriptions()`와 `_manage_subscription_retention_policy()`

## 📈 대시보드 애널리틱스 (v3.7.6)

- 요약 데이터: sizing_outcomes.csv 기반 전체/거래소별 승률·평균/중앙 PnL·평균 Size 표기
- 자동 새로고침: 설정 `analytics_refresh_interval_minutes`(기본 30분)
- 범위/기간 필터: All/Last 100/500/1000, All/Today/7d/30d

## 🚨 개발자 가이드라인 (중요: 혼재 방지)

### 거래소 처리 분리 원칙

```text
🔥 바이낸스 (Binance):
├── 거래 로직: trader.py 전용
├── API 클라이언트: api/binance_client.py (python-binance)
├── 포지션 관리: trader.py.active_positions
└── TP/SL: trader.py 내부 직접 구현

🔥 CCXT 거래소 (Bybit/OKX/Bitget/Upbit/Bithumb):
├── 거래 로직: unified_trader.py 전용
├── API 어댑터: trading/exchanges/adapters/
├── 포지션 관리: unified_trader.active_positions[exchange]
└── TP/SL: CCXT 어댑터의 place_insurance_tp_sl()
```

### 절대 금지 사항

1. **unified_trader.py에서 바이낸스 처리**: `exchange_name == 'binance'` 조건 금지
2. **trader.py에서 CCXT 거래소 처리**: CCXT 관련 import 금지
3. **중복 메서드 구현**: 같은 기능을 여러 파일에 구현 금지
4. **기능 분산**: 관련 기능을 여러 모듈에 분산 구현 금지
5. **어댑터 기능 무시**: 어댑터에 구현된 메서드를 무시하고 직접 구현 금지
6. **중복 로직**: 어댑터와 unified_trader에서 같은 로직 구현 금지
7. **이중 구조 금지**: trading/exchanges/와 trading/exchanges/adapters/에서 같은 거래소 중복 구현 금지
8. **통일된 경로**: CCXT 거래소는 adapters/ 경로만 사용, exchanges/ 경로 사용 금지

### 수정 시 체크리스트

- [ ] 바이낸스 관련 수정은 trader.py에서만 수행
- [ ] CCXT 거래소 관련 수정은 unified_trader.py에서만 수행
- [ ] 중복 메서드가 생성되지 않았는지 확인
- [ ] 어댑터에 구현된 기능을 먼저 확인하고 활용
- [ ] unified_trader.py에서 어댑터 메서드 우선 사용
- [ ] 직접 구현 전에 어댑터 기능 확인 필수
- [ ] CCXT 거래소는 adapters/ 경로만 사용 (exchanges/ 경로 사용 금지)
- [ ] 이중 구조 확인: 같은 거래소가 두 곳에 구현되지 않았는지 확인
- [ ] 문서 가이드라인 준수 여부 확인
- [ ] 거래소별 분리 원칙 위반 여부 확인
- 성과 색상 힌트: 승률/평균PnL 기준 green/yellow/red
- 국면 표시: 현재 국면(LOW/NORMAL/HIGH) 및 국면 모드(AUTO 또는 MANUAL) 표기
  - 상단 상태 바에도 REGIME/MODE 뱃지를 표시해 전체 상태를 즉시 파악
