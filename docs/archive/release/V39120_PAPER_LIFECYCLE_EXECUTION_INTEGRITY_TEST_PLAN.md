# v3.9.1.20 PAPER 생명주기·실행 정합성 검증 원장

기준일: 2026-09-04  
공개 버전: `3.9.1.20` / updater `3.9.120`  
게시 시각: 2026-09-04 01:01 UTC

## 수정 범위

| 등급 | 문제 | 수정 계약 |
|---|---|---|
| P0 | 중지한 PAPER 전략이 결과 동기화로 재활성화 | `paper_versions` 실행 권한이 정본이며 결과 기록은 권한을 만들지 않음 |
| P0 | 열린 PAPER 포지션이 재시작 때 소실 | Binance·Unified 계정별 원자 snapshot 복구 |
| P0 | Binance PAPER 비용 0원 | gross에서 왕복 추정 수수료·슬리피지를 차감한 net 기록 |
| P1 | 여러 관찰 전략 중 첫 전략만 선택 | 동일 실행 슬롯의 deterministic round-robin |
| P1 | UPBIT 종목별 ticker burst/429 | 공유 캐시·최소 간격·429 backoff·제한된 stale fallback |
| P1 | 학습 이벤트마다 큰 JSON 전체 재작성 | append-only journal 즉시 기록 + bounded checkpoint |
| P1 | Binance Algo TP/SL을 누락으로 오감사 | 일반 주문과 Algo 주문의 통합 보호 주문 snapshot |

## 소스 자동검증

- [x] 중지 뒤 늦은 PAPER 결과가 검증 수치만 갱신하고 상태/실행 권한은 복구하지 않는다.
- [x] 구형 status/map split-brain을 한 번의 load로 비파괴 복구한다.
- [x] 관찰 시작 전·중지 후 새로 열린 포지션은 해당 관찰 구간 성과에 귀속하지 않는다.
- [x] PAPER 포지션 serialize/restore가 PAPER만 허용하고 전략 key/version·TP/SL을 보존한다.
- [x] 비-PAPER로 시작한 런타임도 설정에서 PAPER로 전환할 때 기존 열린 snapshot을 복구한다.
- [x] position ID가 있는 청산 재처리는 같은 event ID이며 조회에서 한 번만 집계한다.
- [x] Binance PAPER 통계·원장에 net PnL·fee·slippage가 반영된다.
- [x] 다중 PAPER 관찰 전략이 공유 슬롯에서 순환하며 LIVE 충돌 계약과 분리된다.
- [x] UPBIT 동일 심볼 반복 조회가 cache를 공유한다.
- [x] 학습 이벤트가 checkpoint 전 journal에 즉시 남고 재시작 때 복구된다.
- [x] Binance Algo TP/SL만 존재해도 보호 주문 감사에 통과한다.
- [x] v3.9.1.19 전략 귀속·패키지 해시·검증 대상 회귀를 유지한다.

## Windows·실환경 필수 게이트

- [x] `WIN-BUILD`: Windows Node 22.12+에서 Web build와 Python Windows sidecar를 새로 만들었다.
- [x] `ARTIFACTS`: `NoahAIEngine.exe`, `NoahAI-3.9.1.20-Setup.exe`, blockmap, `latest.yml`의 버전·SHA를 release manifest에 기록했다.
- [ ] `WIN-UPGRADE`: v3.9.1.19→v3.9.1.20 자동 업데이트·안전 종료·재시작·롤백을 확인한다.
- [ ] `SPOT-FUTURES-PAPER`: 6개 거래소 PAPER에서 열림→종료/강제종료→복구→청산을 최소 한 번씩 대조한다.
- [ ] `BITHUMB-E2E`: Bithumb KRW 현물 PAPER 방향·손익·비용·재시작 복구를 대조한다.
- [ ] `RECONCILE-E2E`: Binance PAPER fee/slippage, 전략 귀속, 멱등 청산과 6개 거래소 통화별 원장·화면 합계를 확인한다.
- [ ] `REPORT-E2E`: PAPER 거래 상세·전략 여권·일/주/월 리포트 체크섬을 대조한다.
- [ ] 실제 Binance 계정에서 일반/Algo TP·SL 감사를 읽기 전용으로 대조한다.
- [ ] UPBIT 콜드/웜 다중 종목 분석과 429 복구를 장시간 확인한다.
- [ ] `KIWOOM-E2E`: 키움 조회 연결·거래 worker·안전 종료가 누적 계약을 유지하는지 대조한다.
- [ ] `KIS-E2E`: KIS 토큰 재사용·호출 제한·안전 종료가 누적 계약을 유지하는지 대조한다.
- [ ] `SOAK`: 24~72시간 다중 거래소 PAPER에서 journal·snapshot 손상, 중복 청산, 전략 재활성화가 0건인지 확인한다.

## 배포 판정

v3.9.1.20은 Windows 산출물 생성 후 `AllowPendingExternalGates` 표시와 함께 게시됐습니다. 따라서 체크되지 않은 업데이트·실거래·24~72시간 E2E를 소급 완료로 표시하지 않습니다. 게시 뒤 확인된 활성 통합 PAPER PnL·과거 비용·로그 귀속·성과회복 문제는 v3.9.1.20 자산을 덮어쓰지 않고 [v3.9.1.21 검증 원장](V39121_PAPER_PNL_COST_VENUE_ATTRIBUTION_TEST_PLAN.md)에서 후속 처리합니다.
