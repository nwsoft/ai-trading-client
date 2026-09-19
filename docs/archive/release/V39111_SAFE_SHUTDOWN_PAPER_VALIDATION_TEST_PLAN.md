# v3.9.1.11 안전 종료·PAPER 검증 정합 테스트 계획

기준일: 2026-08-26  
상태: 소스 후보, Windows 재빌드 전

## 소스 자동 검증

- [x] 거래소 중지 요청이 worker join보다 먼저 전체 런타임에 전달된다.
- [x] Binance·통합 거래소가 하나의 종료 제한시간을 공유하며 5초 조기 실패를 만들지 않는다.
- [x] 거래 사이의 3초 대기가 중지 이벤트로 즉시 해제된다.
- [x] 저장 전략 TP/SL은 `percent_points`/`fraction` 단위를 명시하고 저장→실행 경계에서 한 번만 변환된다.
- [x] 단위가 없는 구형 사용자 전략은 값 크기로 추정하지 않고 실행 풀에서 제외해 새 버전 검토를 요구한다.
- [x] PAPER와 LIVE가 같은 TP/SL 단일 권위 검증을 사용하며 `tp/tp_percent`, `sl/sl_percent` 충돌·출처 누락·범위 위반을 주문 전에 차단한다.
- [x] 전진검증은 첫 청산 전에도 관찰 일수를 표시한다.
- [x] 전진검증 재시작은 이전 결과를 보존하고 관찰 시작 이전 청산을 제외한다.
- [x] LIVE 화면의 PAPER 원장은 과거 검증 이력으로 명시된다.
- [x] Binance와 통합 5개 거래소가 동일한 SmartExitPolicy 결정 함수를 사용하고 동일 입력에서 같은 fraction TP/SL을 반환한다.
- [x] 전체 KPI와 종목별 최적화 표본을 구분하며, 종목 표본 부족 시 같은 거래소 청산 표본만 축소 가중치로 사용한다.
- [x] AI 커스텀 고정 TP/SL은 통계·변동성 규칙이 덮어쓰지 않으며 RR 미달은 값 변경 대신 진입 차단으로 처리한다.
- [x] 통합 PAPER 청산은 `net_pnl_ccy`·`estimated_fees`·슬리피지·가격·수량·방향·기준통화를 기록하고 구버전 미확정 행은 승률에서 제외한다.

## Windows 설치본 외부 게이트

- [ ] `WIN-BUILD`: Windows x64 설치기·blockmap·내장 엔진을 새 소스에서 빌드한다.
- [ ] `WIN-UPGRADE`: v3.9.1.10 설치본에서 v3.9.1.11 자동업데이트 후 설정·자격증명·DB·PAPER 원장을 보존한다.
- [ ] `KIWOOM-E2E`: 키움 별도 QAx/COM 프로세스의 연결·종료·재시작을 확인한다.
- [ ] `KIS-E2E`: 한국투자증권 조회·종료가 암호화폐 worker 종료를 방해하지 않는지 확인한다.
- [ ] `BITHUMB-E2E`: Bithumb 현물 PAPER LONG 진입·청산과 미체결 조회를 확인한다.
- [ ] `RECONCILE-E2E`: 거래소 체결·NoahAI 관리 원장·PAPER 원장이 모드별로 섞이지 않는지 확인한다.
- [ ] `SPOT-FUTURES-PAPER`: Upbit·Bithumb 현물과 Binance·Bybit·OKX·Bitget 선물 PAPER 방향·포지션·TP/SL을 확인한다.
- [ ] `REPORT-E2E`: PAPER 검증 수와 AI 리포트 수치가 정확한 전략·기간·통화 원장과 일치하는지 확인한다.
- [ ] `SOAK`: 6개 거래소를 24~72시간 실행한 뒤 종료 버튼 한 번으로 60초 안에 엔진·Electron이 종료되고 잔류 프로세스가 0개다.
- [ ] 종료 중 각 worker가 새 분석 주기를 시작하지 않고 현재 저장/정리만 완료한다.
- [ ] Binance PAPER 진입 후 UI 활성 포지션, 엔진 원장, 재시작 복구가 같은 종목·수량·진입가를 표시한다.
- [ ] 단위 없는 구형 전략이 주문되지 않고 재검토 안내를 남기며, 단위를 명시해 새 버전으로 저장한 뒤 실제 진입가 대비 정확한 TP/SL을 생성한다.
- [ ] 기본 동적 전략과 승인된 AI 커스텀 전략 각각에서 최종 로그·PAPER 포지션·LIVE dry-run의 TP/SL 값이 동일하다.
- [ ] Binance·Upbit·Bithumb·Bybit·Bitget·OKX의 PAPER 개별 거래내역·승률·순손익·수수료가 원장과 일치하고 KRW/USDT가 합산되지 않는다.
- [ ] AI 커스텀 전략별 PAPER 시작일·정확한 청산 수·7일 진행률이 다른 전략 기록과 섞이지 않는다.
- [ ] Upbit PAPER에서 LONG 조건은 가상 진입·청산 이력을 만들고 SHORT 조건은 신규 공매도 대신 보유 LONG 청산만 수행한다.
- [ ] LIVE 화면에서는 PAPER 기록이 현재 실거래나 활성 포지션으로 오해되지 않는다.
- [ ] 설치기·blockmap·latest.yml·내장 엔진의 버전, 크기, SHA-256을 manifest와 대조한다.

모든 외부 게이트가 완료되기 전에는 `publish_ready=false`를 유지하며 공개 v3.9.1.10 자산을 덮어쓰지 않습니다.
