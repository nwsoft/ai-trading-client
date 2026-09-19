# v3.9.1.16 거래소 실행 계약·국내 현물 주문 검증 원장

상태: 소스 후보  
배포: `pending_windows_rebuild`, `publish_ready=false`  
대상: Upbit·Bithumb·Binance·Bybit·OKX·Bitget, LEARNING·PAPER·LIVE

## 수정 범위

- Upbit 시장가 매수를 base 수량 제출에서 KRW 총액 제출로 교정
- Upbit 시장가 매도와 Bithumb 현물 주문은 base 수량 계약 유지
- KRW 현물 `SHORT`를 신규 공매도가 아닌 NoahAI 관리 LONG의 EXIT로 고정
- 진입 원장 단계에 현물 SHORT가 도달하면 실패 폐쇄하는 2차 방어 추가
- 15분봉 시장국면을 거래소별 기본 5분 TTL single-flight로 공유
- 국내 현물·해외 선물·증권·PAPER/LIVE 계약을 `EXCHANGE_SEPARATION_GUIDELINES.md`에 정본화

## 소스 자동검증

- [x] Upbit/Bithumb은 KRW spot, SHORT/레버리지 불가
- [x] Binance/Bybit/OKX/Bitget은 USDT futures, LONG/SHORT 허용
- [x] Upbit 시장가 BUY가 KRW cost를 제출
- [x] Upbit 시장가 SELL이 base quantity를 제출
- [x] Bithumb에 Upbit cost 규격이 전파되지 않음
- [x] 관리 LONG 없는 국내 현물 SHORT는 신규 진입 불가
- [x] 포지션 기록 단계가 국내 현물 SHORT를 거부
- [x] 같은 거래소의 빠른 국면 연속 호출이 1회 네트워크 요청으로 합쳐짐
- [x] Upbit/Bithumb 대표 국면 심볼이 `BTC/KRW`
- [ ] 해외 선물 3개 CCXT 어댑터의 one-way/hedge 계정별 주문·청산 E2E
- [ ] Windows 전체 Python 회귀와 패키징 회귀

## PAPER 검증

- [ ] Upbit: LONG 가상 진입, SHORT 신규 진입 0, 관리 LONG 가상 청산과 KRW PnL
- [ ] Bithumb: LONG 가상 진입·청산과 KRW PnL
- [ ] Binance·Bybit·OKX·Bitget: LONG/SHORT 가상 진입·reduce-only 의미의 청산과 USDT PnL
- [ ] LEARNING에서 가상 포지션·승률·손익·외부 주문 모두 0
- [ ] 동일 전략·동일 입력에서 PAPER와 LIVE dry-run의 방향·수량·TP/SL 단위 일치

## 승인된 최소 LIVE 검증

- [ ] Upbit 최소 KRW 매수 → 주문조회 → 체결 → NoahAI 관리 수량 청산
- [ ] Bithumb 최소 KRW 매수 → 종목별 주문/체결조회 → 청산
- [ ] Binance LONG/SHORT → 보호주문 → 청산
- [ ] Bybit one-way/hedge 각각 `positionIdx`와 청산 방향 대조
- [ ] OKX net/long-short 각각 `tdMode`·`posSide` 대조
- [ ] Bitget one-way/hedge 각각 `tradeSide`·reduce-only 대조
- [ ] 수동·에어드롭·외부 보유자산 자동 매도 0건

## 장시간·업데이트 게이트

- [ ] `WIN-BUILD`: Windows 엔진, Web assets, 설치기, blockmap, `latest.yml`의 3.9.1.16 일치
- [ ] `WIN-UPGRADE`: v3.9.1.15→v3.9.1.16 설정·키·전략·PAPER 원장 보존과 롤백
- [ ] `KIWOOM-E2E`: 조회 전 연결·주문 미실행·안전 종료와 NoahAI 소유 COM 자식 0개
- [ ] `KIS-E2E`: 토큰 재사용·조회·승인된 모의/최소 주문과 종료
- [ ] `BITHUMB-E2E`: 최소 KRW 매수·종목별 주문/체결조회·관리 수량 청산
- [ ] `RECONCILE-E2E`: 주문 모호 상태를 재주문하지 않고 client order ID로 대조
- [ ] `SPOT-FUTURES-PAPER`: 국내 현물 LONG/청산과 해외 선물 LONG/SHORT·기준통화 분리
- [ ] `REPORT-E2E`: 거래소 체결, NoahAI 관리 청산, PAPER 성과와 KRW/USDT 리포트 합계 일치
- [ ] `SOAK`: 6개 거래소 동시 PAPER 24~72시간, 국면 요청·로그 폭증·잔류 worker 없음

위 미완료 항목을 통과하기 전에는 소스 수정이나 macOS 자동테스트 결과를 사용자 배포 완료라고 표시하지 않는다.
