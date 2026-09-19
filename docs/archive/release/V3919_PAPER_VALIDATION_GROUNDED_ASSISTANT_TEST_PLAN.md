# v3.9.1.9 PAPER 전진검증·근거형 AI 어시스턴트 검증 계획

## 소스·로컬 자동검증

- [x] `PAPER-STATE` — 사용자 승인 버전은 과거 검증 구간이 없어도 LIVE active와 분리된 PAPER 전용 풀에 등록된다. v3.9.1.23부터 중지는 `paper_paused` 일시정지이며 같은 시도 재개 시 기존 근거와 활성 검증시간을 보존한다.
- [x] `PAPER-PROGRESS` — 3체결/7일 미만은 실패가 아니라 진행 중이며 조건 충족 시 `paper_validated`로 전환된다.
- [x] `PAPER-HISTORY` — 기본 전략과 AI 커스텀 가상 청산을 모두 기록하되 전략 검증 합산은 정확한 전략 키·버전 결과만 사용한다.
- [x] `ASSISTANT-GUIDE` — 포지션 일반 안내는 반복 AI 커스텀 문구가 아니라 관리 포지션·TP/SL·전략·최근 신호를 설명한다.
- [x] `ASSISTANT-DEEP` — 심층분석 Provider context에 구조화된 실행 근거가 포함되고 없는 값은 추정하지 않는다.
- [x] `KIWOOM-ROUTING` — Web 증권 컨트롤러는 환경변수 누락 시에도 Windows 키움 COM 프로세스 프록시를 선택한다.
- [x] `KIS-ETF-CONTRACT` — KIS ETF 목록/현재가는 비공식 404 경로를 호출하지 않는다.
- [x] `FOCUSED-REGRESSION` — v3.9.1.8 관련 회귀 포함 `148 passed`.
- [x] `FULL-SOURCE-REGRESSION` — 전체 Python 회귀 `1,751 passed, 8 skipped`, 문서·버전·활성 소스·Web parity 계약 감사를 통과했다.
- [x] `WEB-BUILD` — TypeScript 검사와 Vite production build 49 modules 통과. 로컬 Node 20은 권장 Node 22보다 낮으므로 Windows release build 근거로 사용하지 않는다.

## Windows·외부 환경 필수 게이트

- [ ] `FULL-REGRESSION` — Node 22/Python release 환경에서 전체 Python 회귀와 문서·버전 감사를 통과한다.
- [ ] `WIN-BUILD` — `NoahAI-3.9.1.9-Setup.exe`, `NoahAIEngine.exe`, blockmap, 새 `latest.yml(3.9.109)`을 같은 소스로 빌드하고 SHA-256을 확정한다.
- [ ] `WIN-UPGRADE` — 공개 v3.9.1.8에서 v3.9.1.9로 자동 업데이트·안전 종료·재시작·롤백을 확인한다.
- [ ] `KIWOOM-E2E` — Windows 메인 프로세스/자식 프로세스에서 OpenAPI+ 로그인·조회·시작·정지·재시작을 확인하고 AnyIO worker COM 오류가 없음을 확인한다.
- [ ] `KIS-E2E` — KIS 실전/모의 계정에서 토큰·잔고·국내주식·설정 ETF 현재가를 조회하고 `inquire-etf-daily` 404 로그가 없음을 확인한다.
- [ ] `BITHUMB-E2E` — Bithumb 현물 보유·미체결·체결 조회가 종목 필수 계약을 지키고 신규 SHORT를 만들지 않는지 확인한다.
- [ ] `RECONCILE-E2E` — 거래소 확인 체결, NoahAI 관리 포지션 청산과 PAPER 이력이 서로 다른 원장으로 정확히 연결·표시되는지 확인한다.
- [ ] `SPOT-FUTURES-PAPER` — Upbit·Bithumb 현물과 Binance·Bybit·OKX·Bitget 선물의 PAPER 방향·수량·청산 계약을 확인한다.
- [ ] `REPORT-E2E` — AI 리포트가 KRW·USDT를 환율 없이 합산하지 않고 PAPER 결과를 LIVE 실현손익으로 표시하지 않는지 확인한다.
- [ ] `PAPER-FORWARD` — PAPER ON에서 AI 커스텀 버전을 시작해 최소 7일·3건 가상 청산, 앱 재시작 후 누적 유지, 통과 후 명시 적용까지 확인한다.
- [ ] `PAPER-DASHBOARD` — 6개 거래소/증권사별 PAPER 배지·가상 포지션·최근 거래내역이 LIVE 체결 통계와 섞이지 않음을 확인한다.
- [ ] `ASSISTANT-PROVIDER` — 일반 안내는 Provider 호출 0회, 심층분석은 명시 호출 1회이며 실제 포지션의 방향·추세·TP/SL·유지 근거가 런타임/로그와 일치한다.
- [ ] `LONG-RUN` — 다중 거래소 PAPER 24~72시간에서 설정·AI 커스텀·어시스턴트·로그 응답과 안전 종료를 확인한다.
- [ ] `SOAK` — 같은 Windows 설치본으로 24~72시간 연속 운용 후 메모리·폴링·로그·KPI·종료 상태를 다시 대조한다.

모든 외부 게이트가 끝나기 전 manifest는 `pending_windows_rebuild`, `publish_ready=false`를 유지한다.
