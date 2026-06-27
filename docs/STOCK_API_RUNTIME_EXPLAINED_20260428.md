# 증권 API 런타임 설명서 (2026-04-28)

## 1) "배포패키지면 OS 상관없다"가 왜 항상 맞지 않은가

배포패키지(Exe/App)는 Python 런타임을 묶어 배포할 뿐,
브로커가 제공한 외부 SDK/드라이버의 OS 제약까지 제거하지는 못한다.

즉,

- 앱 실행 가능 여부와
- 브로커 실연동 가능 여부는
서로 다른 문제다.

## 2) 브로커별 OS 특성

### 키움 (pykiwoom/OpenAPI+)

- 현재 코드 기준 Windows + pykiwoom 제약이 있다.
- macOS에서 앱은 실행돼도 키움 실주문 경로는 차단된다.

### 신한/미래에셋 (REST)

- REST 기반이라 macOS/Windows 모두에서 실연동 가능하다.
- 전제: app_key/app_secret/account_no 등 인증정보 준비

## 3) API 연결 후 실제 동작 순서

1. 어댑터 connect()
2. 시세/잔고/포지션 조회
3. StockAnalysisService.analyze_symbol() 분석
4. run_auto_trade_cycle() 신호 판단 및 주문 시도
5. 기록 저장
   - trade_log: 체결/주문 로그
   - analysis_log: 분석 스냅샷
   - ai_decisions: XAI 의사결정 기록
6. KPI 이벤트 전송(서버)
   - trade_order_executed / trade_order_failed

## 4) 로그와 학습(기록) 확인 위치

- 로컬 로그 파일: data/logs/trading.log (환경별 경로 차이 가능)
- 로컬 DB: data/trading.db
  - trade_log
  - analysis_log
  - ai_decisions
- 서버 KPI: fastapi설치/auth.db 의 kpi_events

## 5) 지금 바로 재현 가능한 명령

### A. 런타임 흐름 데모(키 없이 가능)

- `python scripts/stock_runtime_flow_demo.py`
- 출력: 분석 결과 + 자동매매 사이클 + DB row 카운트 + 로그 tail

### B. 실연동 준비도 점검

- `python scripts/stock_live_readiness_run.py --broker kiwoom`
- strict: `python scripts/stock_live_readiness_run.py --broker kiwoom --strict`

### C. 개별 점검

- `python scripts/stock_d1_preflight.py`
- `python scripts/stock_live_smoke_check.py`
- `python scripts/stock_live_order_drill.py --broker BROKER_NAME`

## 6) "모든 증권사가 제대로 작동"의 완료 기준

1. 키움(Windows) 실연동 통과
2. 신한(REST) 실연동 통과
3. 미래에셋(REST) 실연동 통과
4. preflight/smoke/order drill strict 통과
5. 실제 소량 주문/취소 후 trade_log + ai_decisions + KPI 확인

## 7) 현재 상태 요약

- 코드/테스트/검증 체인은 준비됨
- 현재 BLOCKED 원인은 인증정보 미입력 + 키움의 OS 제약
- 따라서 "개발 미완"이 아니라 "운영 준비 미완" 상태
