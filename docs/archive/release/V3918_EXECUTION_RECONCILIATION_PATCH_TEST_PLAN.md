# v3.9.1.8 체결 원장 정합·증권 API 안정화 검증 계획

소스 수정, Windows 패키지, 외부 API 읽기, PAPER 운용을 서로 다른 증거로 관리합니다. 아래 필수 행이 끝나기 전에는 `publish_ready=false`입니다.

- [x] `SOURCE-CAPABILITY` — Upbit·Bithumb은 KRW 현물/SHORT 불가, Binance·Bybit·OKX·Bitget은 USDT 선물/LONG·SHORT 가능 계약을 자동 검증한다.
- [x] `SOURCE-BITHUMB` — 종목 없는 Bithumb `fetchOpenOrders`를 호출하지 않고, DB 미확정 주문과 사용자 선택 종목을 재주입하며 20종목 고정 절단을 제거하고 조회 범위를 명시함을 자동 검증한다.
- [x] `SOURCE-KIS` — KIS ETF/ETN 현재가 경로와 TR ID `FHPST02400000`, 명시적으로 설정한 ETF 감시목록을 잘못된 목록 API 없이 사용함을 자동 검증한다.
- [x] `SOURCE-KIWOOM` — Windows Web runtime이 직접 QAx 어댑터 대신 별도 프로세스 프록시를 선택하고, 정상 종료 실패 시 프록시가 소유한 COM 자식 프로세스만 제한시간 뒤 정리함을 자동 검증한다.
- [x] `SOURCE-REPORT` — 100건 초과 기간 전체 집계, KRW/USDT 분리, 거래소 체결과 청산성과 연결 상태, 제한/증분 체결 이력을 전체 이력으로 오표시하지 않는 범위 상태를 자동 검증한다.
- [x] `SOURCE-SAFE-SHUTDOWN` — 실행 플래그가 이미 꺼진 실제 생존 worker도 재발견하고, 모든 CCXT/증권 worker를 먼저 신호한 뒤 공통 제한시간으로 기다리며 Electron이 실제 worker 오류를 전달함을 자동 검증한다.
- [x] `SOURCE-SPOT-OWNERSHIP` — 현물 계좌 잔고를 NoahAI 원장 수량·수동/외부·지원시장 외·거래불가로 분류하고, 소액을 숨기거나 원장 밖 수량을 자동관리하지 않음을 자동 검증한다.
- [x] `WEB-BUILD` — TypeScript 검사와 production build를 통과한다.
- [ ] `WIN-BUILD` — `NoahAI-3.9.1.8-Setup.exe`, `NoahAIEngine.exe`, blockmap, `latest.yml(3.9.108)`을 동일 소스로 빌드하고 SHA-256을 확정한다.
- [ ] `WIN-UPGRADE` — 공개 v3.9.1.7에서 업데이트·안전 종료·설치·재시작·사용자 데이터 보존을 확인한다.
- [ ] `WIN-SAFE-SHUTDOWN` — Binance 포함 6개 거래소 동시 실행 중 종료 버튼과 자동업데이트를 각각 실행해 오류창 없이 worker·DB·sidecar가 정리되고 강제 종료가 필요 없음을 확인한다.
- [ ] `KIWOOM-E2E` — Windows 키움 OpenAPI+ 로그인, 계좌/종목/미체결 읽기, worker 시작·정지·재시작 시 자식 프로세스 정리를 확인한다.
- [ ] `KIS-E2E` — 실제 KIS ETF/ETN 현재가 읽기에서 404와 빈 응답 오판이 없음을 확인한다.
- [ ] `BITHUMB-E2E` — 다종목 보유/미체결 계정에서 종목별 결과·호출 제한·오류 요약을 확인한다.
- [ ] `RECONCILE-E2E` — 각 거래소 실제 체결 API와 로컬 원장의 주문 ID·종목·방향·수량·시간을 대조하고 지원 불가를 0건으로 표시하지 않는지 확인한다.
- [ ] `SPOT-FUTURES-PAPER` — 현물 SELL이 보유량을 초과하거나 신규 SHORT를 만들지 않고, 선물 LONG/SHORT는 reduce-only/포지션 방향을 보존하는지 확인한다.
- [ ] `SPOT-OWNERSHIP-E2E` — 기존 수동 보유·에어드롭·거래지원 종료 자산이 계좌 잔고에는 보이되 NoahAI 관리 수량·포지션 슬롯·자동청산에 편입되지 않음을 Upbit와 Bithumb 실계정 읽기로 확인한다.
- [ ] `REPORT-E2E` — 오늘·주간·월간·최근 1시간의 체결/청산/손익/수수료가 DB 직접 질의와 일치하고 KRW·USDT가 분리되는지 확인한다.
- [ ] `SOAK` — 6개 거래소와 선택 증권사를 24시간 이상 PAPER 운용해 원장 중복·누락·Web 응답 정체가 없는지 확인한다.
