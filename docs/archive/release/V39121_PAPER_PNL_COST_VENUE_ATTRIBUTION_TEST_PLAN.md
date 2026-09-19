# v3.9.1.21 PAPER 손익·비용·거래소 귀속 검증 원장

기준일: 2026-09-04  
소스 후보: `3.9.1.21` / updater `3.9.121`  
현재 공개판: `3.9.1.20`

## 수정 범위

| 등급 | 문제 | 수정 계약 |
|---|---|---|
| P0 | v3.9.1.19 Binance 전략 검증 비용 0 | 근거가 있는 행만 당시 기본 계약으로 추정하고 건수 표시, 근거 부족 행은 손익·비용 미확정 |
| P0 | Upbit·Bithumb·Bybit·Bitget·OKX 활성 PAPER 미실현 PnL 0 | 현재가와 예상 비용을 Position·Web snapshot에 즉시 반영 |
| P0 | 타 거래소 판단 로그가 Binance 탭에 혼입 | Analyzer·Recorder 실행 거래소 태그 전달 + 구형 오태그 행 실패 폐쇄 |
| P1 | 성과회복 제한의 거래소별 적용·표본 불명확 | 6개 거래소별 최신 완료 거래, 순손익 비용 1회 차감, 다음 체결 후 재평가 |
| P0 | 4개 증권사 주식·ETF 활성 PAPER PnL·비용 누락 | 현재가 기준 KRW 순손익 및 수수료·세금·슬리피지 갱신 |
| P0 | 증권 PAPER 성과 판단에 LIVE 체결 혼입 가능 | PAPER는 해당 증권사 유효 PAPER 청산만, LIVE는 증권사 체결만 사용 |
| P1 | 주식/ETF·부분청산 비용 계약 불명확 | 자산유형별 매도세 분리, 진입비용 수량 비례 배분, 포지션 생성 시 비용 계약 고정 |
| P1 | 공유 Recorder의 증권사 로그 소유권 혼입 가능 | 각 XAI/거래 로그에 실행 증권사를 명시적으로 전달 |

## 확인된 사용자 데이터 근거

- Teayu PAPER 원장 Binance 184행 중 177행은 entry·quantity·gross/net이 남아 v3.9.1.19 기본 비용 계약 추정이 가능했습니다.
- 근거가 부족한 7행은 비용 0원이나 정확한 순손익으로 위장하지 않고 `비용 미확정·과거 손익 미확정`으로 제외합니다.
- Teayu `trading_binance.log`에는 타 거래소가 소유한 `trade_runtime::<venue>` 결정 3,245행이 `(ex=binance)`로 잘못 기록돼 있었습니다. 원본 파일은 변경하지 않고 새 기록 라우팅과 조회 필터를 함께 수정합니다.

## 소스 자동검증

- [x] Upbit·Bithumb·Bybit·Bitget·OKX 각각의 활성 PAPER 포지션이 청산 전에 비용 차감 후 미실현 PnL을 갱신한다.
- [x] v3.9.1.19 Binance 비용 0 행은 계산 근거가 있는 경우만 추정하며 append-only 원장을 변경하지 않는다.
- [x] 비용 근거가 없는 구형 행은 승패·순손익 확정 통계에서 제외하고 미확정 건수를 노출한다.
- [x] 전략 스튜디오 `비용`은 수수료와 예상 슬리피지 합계이며 추정 복구·미확정 건수를 구분한다.
- [x] 공유 Analyzer·Recorder가 실행 거래소를 로그 source로 사용한다.
- [x] 구형 타 거래소 소유 결정이 Binance 로그 화면에 노출되지 않는다.
- [x] 성과회복 제한은 거래소별 최신 완료 표본을 사용하며 이미 net인 PnL의 비용을 이중 차감하지 않는다.
- [x] 위험배수·최대 포지션·최대 레버리지 제한은 Binance와 통합 5개 거래소의 공통 실행 경로에 전달된다.
- [x] 키움·신한·미래에셋·한국투자 각각에서 주식과 ETF PAPER 활성 포지션이 청산 전 KRW 순손익을 갱신한다.
- [x] 주식 청산은 설정된 예상 매도세, ETF 청산은 ETF 세금 계약을 사용하며 수수료·세금·슬리피지를 합산 비용과 별도 필드로 기록한다.
- [x] 일부 청산은 진입 수수료·슬리피지를 수량 비율로 배분하고 보유 수량을 넘는 PAPER 매도를 차단한다.
- [x] 증권 PAPER 성과 표본은 해당 증권사의 유효한 PAPER 원장만 사용하고 실계좌 체결 조회를 호출하지 않는다.
- [x] 증권 XAI 로그는 공유 Recorder의 mutable 상태가 아니라 명시된 실행 증권사에 귀속된다.
- [x] 주식/ETF PAPER 비용 설정은 0~5% fraction만 허용하며 단위 오류는 문서화된 기본 추정 프로필로 실패 안전 처리한다.
- 사용자 피드백·주식/ETF 정합 집중 회귀: `205 passed, 6 skipped`
- 전체 Python 회귀: `2,052 passed, 8 skipped`
- Node `22.23.1` Web production build: 49 modules, offline npm audit 취약점 0건
- 문서/버전 정합, Web source contract, 활성 소스, dev release gate: PASS
- 소스 fingerprint: `1553a72723c3a5fe9503fe056065399e7887f1008356d407a3b5eeed9c11c1f0`

## Windows·실환경 필수 게이트

- [ ] `WIN-BUILD`: 현재 소스 fingerprint로 Windows 엔진과 `NoahAI-3.9.1.21-Setup.exe`를 새로 만든다.
- [ ] `ARTIFACTS`: 설치기·blockmap·`latest.yml`의 updater `3.9.121`, SHA-256, 소스 fingerprint를 대조한다.
- [ ] `WIN-UPGRADE`: v3.9.1.20→v3.9.1.21 자동 업데이트·안전 종료·재시작·롤백을 확인한다.
- [ ] `SPOT-FUTURES-PAPER`: 국내 KRW 현물과 해외 USDT 선물의 방향·통화·PnL 계약을 6개 거래소에서 대조한다.
- [ ] `BITHUMB-E2E`: Bithumb KRW 현물 PAPER의 진입·평가손익·청산·비용을 대조한다.
- [ ] `RECONCILE-E2E`: 런타임 포지션·PAPER 원장·전략 여권·화면 합계를 거래소/통화별로 대조한다.
- [ ] `REPORT-E2E`: PAPER 상세·전략 여권·일/주/월 리포트의 건수·손익·비용 체크섬을 대조한다.
- [ ] `ACTIVE-PNL-E2E`: 6개 거래소 PAPER에서 가격을 움직여 청산 전 화면 PnL과 런타임 계산값을 대조한다.
- [ ] `COST-E2E`: 신규 Binance PAPER의 gross·fee·slippage·net 및 전략 스튜디오 합계를 대조한다.
- [ ] `LOG-E2E`: 6개 거래소를 동시에 실행해 각 탭에 자기 거래소 로그만 나타나는지 확인한다.
- [ ] `RECOVERY-E2E`: 6개 거래소별 성과회복 상태·최근 표본·다음 체결 재평가·실제 위험 제한을 대조한다.
- [ ] `RESTART-E2E`: 열린 PAPER 포지션·전략 key/version·비용·미실현 PnL이 재시작 후 이어지는지 확인한다.
- [ ] `STOCK-PAPER-PNL`: 키움·신한·미래에셋·한국투자의 주식/ETF PAPER에서 가격 변동→평가손익→부분/전체 청산→KRW 원장을 대조한다.
- [ ] `STOCK-COST`: 증권사·계좌별 실제 수수료와 PAPER 추정 설정의 차이를 확인하고 주식/ETF 세금·슬리피지 표시를 대조한다.
- [ ] `STOCK-RECOVERY`: 네 증권사의 PAPER 성과회복이 서로의 원장과 LIVE 체결을 참조하지 않는지 대조한다.
- [ ] `KIWOOM-E2E`: 키움 조회 연결·거래 worker·PAPER 평가·안전 종료 누적 계약을 Windows에서 대조한다.
- [ ] `KIS-E2E`: KIS 토큰 재사용·호출 제한·PAPER 평가·안전 종료 누적 계약을 실제 계정에서 대조한다.
- [ ] `SHINHAN-MIRAE-E2E`: 제휴 계약이 준비된 신한·미래에셋 어댑터에서 조회·PAPER 평가·안전 종료를 대조한다.
- [ ] `SOAK`: 24~72시간 6개 거래소·4개 증권사 PAPER에서 PnL 정지, 로그 혼입, 중복 청산, 표본 교차가 0건인지 확인한다.

## 배포 판정

v3.9.1.20 GitHub 릴리스는 이미 공개된 불변 자산이며 이 수정이 포함됐다고 소급 표시하지 않습니다. 위 Windows·실환경 게이트를 통과한 새 v3.9.1.21 산출물만 게시할 수 있습니다. 소스 회귀와 Web build만 통과한 상태는 `pending_windows_rebuild`, `publish_ready=false`입니다.
