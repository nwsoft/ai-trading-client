# v3.9.1.39 PnL 신뢰성 재감사

2026-09-18 · 소스 후보 3.9.1.39 / updater 3.9.139 · **배포 보류**

## 판정과 증거 경계

기간·초기화·수동 거래·총손익/순손익·수수료·세금·펀딩비·원가 산정의 차이는 정상적인 비교 차이를 만들 수 있습니다. 그러나 같은 거래/기간/비용 기준에서 발생한 누락 또는 부호 반전은 그 설명만으로 정당화할 수 없습니다.

사용자 스크린샷은 첫 행 미대조와 다음 행만의 부분 합계를 보여 줍니다. `exit_order_id` 없는 외부 청산 경로를 소스로 확인했지만 **사용자 DB 및 거래소 원본 체결이 없어 해당 계좌의 원인을 최종 확정한 것은 아닙니다.** 이전 문서의 사용자 원인 확정 및 자동 복구 완료 표현을 정정합니다.

## 재현한 추가 결함과 보강

새 감사 테스트 최초 실행: **19 failed**. 실제 주문/API 호출 없는 임시 SQLite fixture입니다.

| 경로 | 재현한 문제 | 현재 소스 조치 |
|---|---|---|
| 공통 대조기 / 7 거래소·4 증권사 | 같은 주문 ID의 LIVE 체결이 PAPER 종료 행을 덮을 수 있음 | LIVE 계열 모드만 대조 |
| ID 누락 외부 청산 | 시간/수량 유일 후보도 수동 거래일 수 있음 | 후보를 `candidate_requires_order_evidence`로만 표시, ID/PnL 자동 덮어쓰기 철회 |
| 정확한 주문 ID 대조 | 청산 방향 검사 없음, 같은 주문의 중복 귀속 가능 | 반대 방향 및 귀속 충돌 검사 |
| 비용 | 일부 fill의 빈 비용 통화를 다른 fill 통화로 추정 | 미확인/혼합 통화 순손익 확정 차단; 수수료 환급 부호 보존 |
| 시각 | epoch는 로컬, UTC ISO는 시차 없이 잘라 저장 | timezone-aware ISO를 로컬로 변환 후 저장 |
| 재동기화 | 동일 체결 ID의 늦게 온 PnL을 INSERT OR IGNORE가 무시 | 같은 기관·종목·주문·체결 ID를 보강하며 이미 있는 PnL/비용을 빈 재응답으로 지우지 않음 |
| 증권 조회 합계 | KIS/키움/신한/미래 체결금액을 USDT로 분류 | KRW로 수정 |
| Provider PnL | CCXT native `fillPnl`/`profit` 누락, 임의 `pnl` 해석 | Binance realizedPnl / OKX fillPnl / Bitget profit 및 명시 정규화 필드만 처리, NaN 배제 |
| 성과 입력 | 미대조 추정 PnL에도 `pnl_is_net=True` | Recorder에 성과 근거 상태 전달 |
| 수익성 검증 / Smart Exit | 미확정 손실을 제외한 양수 부분 표본으로 판단 가능 | 미확정 입력이 있으면 수익성 검증 보류, Smart Exit 통계 조정 중지 |
| Unified / 증권 성과 | 개별 체결을 왕복 종료 손익 표본으로 사용 | Unified raw fill fallback은 미검증; 증권 LIVE는 로컬 종료 원장 사용, MOCK/PAPER 별도 유지 |
| Unified 부분청산 | provider 근거 없이 확정 partial 상태 부여 | 실제 근거에 맞는 상태 사용 |

이는 **공통 소스 결함의 재현**이며 11기관에서 실제 사고가 있었다거나 11기관 API를 검증했다는 의미가 아닙니다.

## 표시 기준

- `NoahAI 연결 청산 순손익`: NoahAI 종료 원장의 대조 완료분. 미확정이 있으면 부분 합계 경고.
- `거래소 수집 체결 실현손익 · 비용 차감 전`: 저장된 provider fill PnL. 수동 거래가 포함될 수 있고 계좌 전체 수집 완료를 보증하지 않음.
- `연결 청산 총손익`: 기존 오해 소지가 있는 거래소/기관 실현 PnL 표 제목을 변경.
- 펀딩비/계좌 전체 누적 PnL은 미검증. 이를 0 또는 이미 1:1 일치한 값으로 표시하지 않음.
- 표시 기준 초기화는 조회 시작점만 변경하며 원장·학습·위험 기록을 삭제하지 않음.
- 같은 기간이어도 체결 시각 합계와 청산 시각의 왕복 거래 합계는 다름. 진입 비용이 기간 밖일 수 있으므로 두 수치를 단순 차감해 오류로 단정하지 않음.

## 기관별 확인 범위 / 남은 작업

| 기관 | 현재 확인 | 아직 필요한 증거 |
|---|---|---|
| Binance | exact-order gross/net, 외부 청산 ID 누락, 공통 대조 회귀 | 보호 algo 주문→실제 체결 주문 연결, 페이지 누락 없는 history, funding/commission 원장 |
| Bybit | CCXT execution history 경로 | execution/list는 종료 순손익 원장이 아님. closed-pnl 별도 귀속 및 비용 중복차감 방지 |
| OKX | native fillPnl 파싱 회귀 | 계약수/contractSize, fee/rebate 및 bill/funding 계정 대조 |
| Bitget | native profit 파싱 회귀 | 계약수, feeDetail/보유비용, 계정 모드별 대조 |
| Upbit/Bithumb/Coinone | 공통 PAPER 격리·exact-order/기존 현물 회귀 | 매수 lot/평균원가·수동 보유분·수수료의 계좌별 대조; Coinone LIVE 준비도는 별개 |
| KIS/키움/신한/미래 | 공통 대조 격리, KRW 집계, 기존 stock lot/fee/tax 회귀 | 주식/ETF 및 계정별 매수원가·매도 체결·수수료·세금·정정/취소 대조 |

## 배포 차단 게이트

- [ ] 외부 TP/SL의 실제 주문 소유권을 증명해 자동 복구. 시간/수량 추측을 다시 확정 근거로 사용하지 않음.
- [ ] 사용자 DB + 같은 기간 거래소 체결/주문/비용 원장으로 AVAUSDT 첫 +0.25와 다음 거래 1:1 확인. API 키/비밀번호는 수집하지 않음.
- [ ] 모든 AI/학습 입력 소비자 감사. 이번 조치는 ProfitabilityValidator/Smart Exit 및 공통 Reader에 한정되며, TP/SL 소멸 시 임시 누적 통계와 직접 learning/journal 이벤트의 추정 PnL 경로는 아직 남음.
- [ ] 포지션 관리·보호주문은 지속하되 대조 미완료 성과로 신규 진입 위험을 늘리지 않는 전체 정책 검증. 기존 독립 커스텀의 수익성 정책 우회도 별도 데이터 무결성 게이트가 필요.
- [ ] 진입 비용 미수집/제로 구분, 비용 통화 환산, 계약수/기초자산 단위 및 여러 진입 lot의 청산 주문 배분 검증.
- [ ] `exchange_confirmed`와 `broker_order_linked`/계산형 근거 등급을 모든 UI/내보내기에서 분리. 과거 잘못 확정된 행은 백업과 근거 없이 일괄 변경하지 않음.
- [ ] API 페이지 끝/조회기간 누락·오류·재시작·중복 동기화와 부분체결 전체 대조.
- [ ] Windows 새 빌드, UI 실화면, 실계정 읽기 전용 대조, v38→v39 업데이트. 새 실거래 주문은 별도 허가 없이 실행하지 않음.

## 검증 기록

- 추가 감사 29건 + 기존 v39 5건 + v28 24건: **58 passed**.
- 증권 모의 실행 회귀 포함 집중: **132 passed**.
- 첫 전체 회귀: **2,602 passed / 3 failed / 8 skipped / 3 subtests**. 3건은 MOCK 성과 입력을 LIVE 원장으로 변경한 영향으로, MOCK 분기 복원 후 집중 재실행 통과.
- Node 22.23.1 Web production: **61 modules**, build PASS. 기존 500kB chunk 경고 유지.
- 최종 전체 재실행: **2,606 passed / 8 skipped / 3 subtests**, Starlette 기존 경고 1건.
- 격리 코인/주식 UI fixture: 1600×1200/1280×900, 브라우저 오류 및 API 쓰기 0건. 비교 설명 추가 시 기존 고정 grid가 카드와 표를 겹치게 하는 문제를 발견해 세로 스크롤 레이아웃으로 수정하고 경계 겹침을 자동 검사했습니다.
- [화면 검증 자료](../reports/pnl-audit-20260918/README.md). Windows/실계정/전체 기간 수집 완료 증거가 아닙니다.
- 과거 이미 잘못 저장된 UTC naive 시각이나 중복 원장을 일괄 재작성하지 않았습니다. 원본 증거/백업에 기반한 별도 이관이 필요합니다.

## 공식 API 근거

- [Bybit Trade History](https://bybit-exchange.github.io/docs/v5/order/execution): 개별 체결·비용·커서이며 종료 손익 원장은 별도.
- [Bybit Closed PnL](https://bybit-exchange.github.io/docs/v5/position/close-pnl): 청산 손익 전용 조회.
- [OKX API](https://www.okx.com/docs-v5/en/): fillPnl 및 fee/feeCcy 계약.
- [Bitget Order Fills](https://www.bitget.com/api-doc/classic/contract/trade/Get-Order-Fills): profit 및 feeDetail 계약.
