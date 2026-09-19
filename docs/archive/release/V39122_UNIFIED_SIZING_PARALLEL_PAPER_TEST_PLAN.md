# v3.9.1.22 공통 투자금·성과회복·병행 PAPER 검증 원장

소스 후보: `3.9.1.22` / updater `3.9.122`  
기준일: 2026-09-06  
현재 공개판: `3.9.1.21`  
상태: 소스 P0/P1 정합·회귀 게이트 완료 / Windows 새 산출물·실계정·장시간 E2E 미완료

## 수정 계약

| 우선순위 | 문제 | v3.9.1.22 계약 |
| --- | --- | --- |
| P0 | 같은 설정명이 기관별로 다른 수량 계산을 의미 | 신규 계정은 `account_risk`, 구형 무정책 계정은 `legacy_venue`, 수동 지정은 `manual_notional`로 분리. 마이그레이션은 LIVE 금액을 자동 확대하지 않음 |
| P0 | Strategy Studio 위험값이 최종 주문에서 축소 상한으로만 작동 | 계좌 마스터 위험과 전략 요청 위험의 `min()`에 시장·성과 배수를 적용하고 요청값·상한·최종값·제한 사유를 기록 |
| P0 | 동시 포지션 요청과 계좌 상한 불분명 | 최종 상한=`min(계좌, 전략 요청, 성과 제한)`. 전략 또는 다운로드 패키지는 계좌 상한을 높일 수 없음 |
| P0 | KRW/USDT 금액 PnL을 한 수익률 배열로 사용 | 거래별 순수익률을 우선 사용하고 금액만 있으면 진입 Notional로 나눔. 현금 손익 합계는 통화별 표시용으로 분리 |
| P0 | 최소주문 보정이 위험 계산 실패 수량을 되살릴 가능성 | 위험 계산 실패는 즉시 차단하고, 거래소 최소주문이 승인 Notional 상한을 넘으면 주문하지 않음 |
| P0 | Binance 계좌 위험 수량이 구형 optimizer 수량으로 다시 축소될 가능성 | 계좌 위험 수량을 다중 거래소 승인 전에 계산하고, 승인 뒤 최종 수량의 실제 필요 증거금을 다시 검사 |
| P0 | LIVE와 Strategy Studio PAPER 검증의 전역 모드 충돌 | 주문 API를 소유하지 않는 별도 관찰 엔진이 전략 버전·거래소·종목별 가상 포지션을 관리. 검증 결과가 LIVE 활성화로 자동 승격되지 않음 |
| P1 | 선물 계약 수와 기초자산 수량 혼동 | CCXT `contractSize`를 수량→Notional·최소주문 계산에 포함 |
| P1 | 주식 PAPER가 포트폴리오 계산 중 실계좌 잔고를 읽을 수 있음 | PAPER/LEARNING은 KRW 가상 기준자금만 사용하고 LIVE만 해당 증권사 평가금액을 사용 |

## 자산·기관별 동일 계약

- Binance·Bybit·Bitget·OKX USDT 선물: LONG/SHORT, 계약 크기, 레버리지·증거금 상한 적용.
- Upbit·Bithumb KRW 현물: LONG 신규 진입만 허용하고 1배 Notional로 계산.
- 키움·신한·미래에셋·한국투자 주식·ETF: 1배·KRW·정수 주식 내림. 승인 위험을 넘기는 소수점 올림 금지.
- PAPER/LEARNING/병행검증: 실계좌 잔고·주문 API를 사용하지 않고 독립 가상 기준자금 사용.
- LIVE: 잔고·현재가·SL 중 필수 근거가 없으면 계좌 위험 모드 주문을 실패 폐쇄.
- 병행 PAPER: 기본적으로 전략 버전당·거래소당 동시 가상 포지션 1개이며 사용자가 1~10 범위에서 늘릴 수 있다. 동일 가상 기준자금을 종목마다 무제한 중복 사용하지 않는다.

## 사용자 설정과 이전 버전 차이

- 신규 설치 기본은 `account_risk`(화면명 `NoahAI 자동 위험관리`)이다.
- v3.9.1.21 이하에서 공통 정책이 없던 기존 계정은 `legacy_venue`로 명시 마이그레이션한다. 자동 위험관리 또는 `manual_notional` 선택 전에는 거래소별 이전 계산을 보존한다.
- Web 설정은 이 마이그레이션 상태를 빈 선택값으로 숨기지 않고 이유와 전환 초안을 표시한다. 전환 버튼은 저장 전 초안만 바꾸며 자동 저장·자동 주문하지 않는다.
- `account_risk`: 계좌 상한과 Strategy Studio 전략 요청 중 더 작은 위험률·증거금·Notional·레버리지를 사용한다. 시장·성과 배수는 이를 더 줄일 수만 있다.
- 성과회복은 KPI 통과 즉시 1.0으로 점프하지 않고 통과 폭에 따라 0.50~1.00에서 점진 복구한다. 수익에 따른 무제한 복리 증액은 아니다.
- Level 1~3은 이해·검증·IR 제작 깊이이고 Level 4는 제한된 전문가 운용 요청이다. Level 5/가드레일 해제는 도입하지 않는다.
- 계좌 동시 포지션 기본은 3, 전문가 허용 범위는 1~10이다. 5~10은 전략 분산을 보장하지 않으며 상관 노출·총위험·증거금·보호주문/API 부하 검증이 필요하다.
- 레버리지는 목표 노출을 만드는 도구이며 투자금 증가 신호가 아니다. 최종 로그/XAI는 계좌 평가금, SL, 위험금액, Notional, 증거금, 수량, 적용 레버리지를 함께 남긴다.
- 설정·블록체인·주식/ETF AI 어시스턴트의 투자금 빠른 질문은 현재 저장 모드·고정 목표액·KPI 표본 기준을 읽어 설명하며 설정이나 주문을 변경하지 않는다.
- 기존 `walkforward_pass_rate`는 재학습 OOS 워크포워드가 아니라 완료 거래 창의 양수 기대값 안정률이다. v3.9.1.22부터 `window_stability_rate`와 방법명을 함께 노출한다.

## 소스 게이트

- [x] 공통 순수 함수 투자금 계약과 안전한 기본값
- [x] Binance 네이티브 최종 주문 수량 연결
- [x] Upbit·Bithumb·Bybit·Bitget·OKX 통합 주문 수량 연결
- [x] 키움·신한·미래에셋·한국투자 공통 주식/ETF 수량 연결
- [x] 전략 위험 요청과 계좌 마스터 위험의 최솟값을 Binance·통합 거래소·4개 증권사 최종 수량에 연결
- [x] 계좌·전략·성과 동시 포지션 상한의 최솟값 계약과 Level 4 UI 연결
- [x] Level 4 전략 요청·계좌 정책·정적 허용값 비교와 주문 직전 예상손실/Notional/증거금/레버리지/수량 XAI
- [x] AI 임계값 자동 보정을 영구 사용자 설정에서 24시간 런타임 오버레이로 분리
- [x] 신규 `account_risk` / 기존 `legacy_venue` / 수동 `manual_notional` 마이그레이션 분리
- [x] 신규 거래소는 CCXT 단독 신뢰가 아니라 기능 프로필·native escape hatch·기관별 적합성 시험을 요구
- [x] CCXT 계약 크기 및 거래소 최소주문/승인 상한 대조
- [x] 수익률 기준 성과회복 KPI와 현금 손익 표시 분리
- [x] LIVE 주문 권한 없는 전략별 병행 PAPER 엔진 및 append-only 청산 귀속
- [x] LIVE 활성 전략 풀과 PAPER 관찰 전략 풀 분리
- [x] 전략 스튜디오가 전체 PAPER·LIVE 병행검증 ON·LIVE 병행검증 OFF의 실제 설정과 집계 상태를 구분 표시
- [x] PAPER/LEARNING의 실계좌 잔고 비사용 회귀
- [x] 인앱 매뉴얼·AI 지식·제품/비즈니스 정본의 실제 시드 없는 PAPER·E0 공개·증거 단계 경계 동기화
- [x] daltrading 권리 자기선언+구조 검사 E0 공개, 근거 없는 점수 0, 증거 승격, 신고 사후 검토 소스 정합
- [x] 이번 정합 패치 이후 전체 Python 회귀 재실행: `2,097 passed, 8 skipped`
- [x] 투자금·전략·기관 집중 회귀: `176 passed`; 증권 dev gate: `169 passed, 6 skipped`
- [x] 이번 정합 패치 이후 Web TypeScript/Vite production build 재실행: 49 modules
- [x] 설정·AI 어시스턴트·문서/버전·Web UI source contract 및 npm audit(취약점 0건)
- [x] daltrading 전략 허브 전체 회귀: `85 passed`; NoahAI Labs production build: `225 pages`; lint 오류: `0건`; info/ip 통합 사이트 production build: `45 pages`
- [x] 새 소스 fingerprint 생성: `7b6e0e9ad64f59689d9830d1adc6c62c61f569597fa8d328bcb9ab4474311df4`
- [ ] Windows 산출물 manifest와 위 fingerprint 대조

## 신규 거래소·증권사 온보딩 계약

CCXT는 공개 시세, 심볼 메타데이터, 잔고와 표준 주문을 빠르게 연결하는 기본 어댑터로 우선 사용한다. 그러나 CCXT 지원 여부만으로 LIVE 준비 완료로 판단하지 않는다. 현물/선물, 주문 수량 단위, `contractSize`, one-way/hedge, reduce-only, 서버 보호주문, client order id, 부분체결·취소·재시작 대조, 수수료, 서버 시간, rate limit을 기능 프로필로 선언하고 실제 샌드박스/PAPER/최소 LIVE 적합성 시험을 통과해야 한다. CCXT가 표현하지 못하는 거래소 기능은 작은 native escape hatch로 격리하며 공통 위험 계산을 다시 구현하지 않는다.

## 배포 전 외부 게이트

- [ ] `WIN-BUILD` — Windows에서 현재 fingerprint로 `NoahAIEngine.exe`, `NoahAI-3.9.1.22-Setup.exe`, blockmap, `latest.yml` 생성
- [ ] `WIN-UPGRADE` — v3.9.1.21 → v3.9.1.22 업데이트·안전 종료·재시작·설정/전략/원장 보존
- [ ] `KIWOOM-E2E` — 키움 주식/ETF PAPER 정수 수량·평가·부분/전체 청산 대조
- [ ] `KIS-E2E` — 한국투자 및 신한·미래에셋 PAPER/LIVE 조회·주문 경계 대조
- [ ] `BITHUMB-E2E` — Bithumb KRW 현물 LONG·1배·최소주문·비용 대조
- [ ] `RECONCILE-E2E` — 거래소/증권사 원장·화면·리포트·성과회복 합계 대조
- [ ] `SPOT-FUTURES-PAPER` — 6개 거래소 각각 PAPER 진입·평가·청산·비용·Notional/XAI 대조
- [ ] `REPORT-E2E` — 일간·주간·월간 상세와 통화별 합계 체크섬 대조
- [ ] 승인된 최소 LIVE 주문으로 계좌 평가금·SL·수량·레버리지·실제 주문 Notional 대조
- [ ] `SOAK` — LIVE와 전략별 병행 PAPER 24~72시간 운용, 실주문 호출 격리와 재시작 복구 확인
- [ ] `HUB-E2E` — 실제 회원 제출→E0 공개→다운로드→재가져오기→증거 승격→독립 신고 격리·운영자 판정 대조
- [ ] `PUBLIC-SITES` — daltrading·NoahAI Labs 배포 뒤 `/llms.txt`, 전략 허브·가이드·제품·릴리스 경계 운영 URL 확인

## 배포 판정

소스 테스트와 Web 빌드 통과는 Windows 설치본이나 실제 기관 E2E 완료가 아니다. 위 외부 게이트를 완료한 뒤에만 `publish_ready=true`인 v3.9.1.22 manifest를 생성·게시한다. 현재 v3.9.1.21 공개 자산은 덮어쓰지 않는다.
