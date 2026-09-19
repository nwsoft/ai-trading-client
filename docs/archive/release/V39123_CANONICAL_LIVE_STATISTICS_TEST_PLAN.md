# v3.9.1.23 LIVE/PAPER 통계 정본·PAPER 재개 검증 원장

소스 후보: `3.9.1.23` / updater `3.9.123`  
작성일: 2026-09-08  
배포 상태: 공개판 (installer SHA-256 `10183438bbb4b3316d340a916bc76c145b8214f739c43c24a7778731cd333f82`)

## 사용자 계약

- `data/Teayu`는 한 명의 실제 테스터가 제공한 지원 증거이며 전체 사용자 대표 데이터나 개발 fixture가 아니다. 진단은 읽기 전용으로만 수행하고 수정·초기화·마이그레이션·자동 준비도 점검 대상으로 사용하지 않는다.
- 운영 KPI와 거래 통계의 청산 수·승률·실현손익·비용 정본은 `trade_log`의 LIVE 청산 행이다.
- PAPER 운영 KPI와 거래 통계의 정본은 `strategy_paper_outcomes.jsonl`의 유효한 가상 청산 행이며 LIVE·거래소 확인 체결과 합산하지 않는다.
- 거래소 확인 체결은 `exchange_execution_log`로 별도 표시한다. 주문 체결 수와 포지션 청산 수는 같은 숫자라고 가정하지 않는다.
- `exchange_trade_stats`와 `stock_trade_stats`는 호환·운영 스냅샷이며 기간 손익 정본이 아니다.
- 실행모드는 `LIVE/PAPER/LEARNING` 경계로 집계한다. 과거 Binance의 `optimized/manual`은 실제 LIVE 주문 경로에서 잘못 저장된 별칭으로만 마이그레이션해 읽는다.
- KRW 현물·주식과 USDT 선물은 통화별로 표시하며 환율 정책 없이 합산하지 않는다.
- 거래소/증권사 출처가 없는 구형 행은 보존하되 현재 LIVE 대표 합계나 특정 기관 성과에 추정 귀속하지 않는다.

## 현재 및 미래 기관 계약

- 기관 의미의 코드 정본은 `trading/exchanges/venue_capabilities.py`, Web 화면 정본은 `config/web_ui_feature_inventory.json`이며 자동 회귀에서 정확히 일치해야 한다.
- 새 기관은 서비스·시장·통화·수량, 자격증명, 주문/보호/대조, LIVE/PAPER/LEARNING, 통계·KPI·리포트, 로그·알림, Strategy Studio 귀속, 안전 종료를 한 배포 단위로 구현한다.
- CCXT는 전송 계층일 뿐이며 contract size·포지션 모드·보호주문·시간·호출 제한의 native 적합성 검증을 대체하지 않는다.
- 실제 사용자 지원 폴더는 fixture나 readiness 계정으로 사용하지 않는다. 기관별 외부 점검은 명시한 QA 계정만 사용한다.

## 화면 계약

- 거래소·증권사 카드: 현재 계좌/가상 포지션과 오늘 요약만 표시한다.
- 실시간 거래 로그의 운영 KPI: 전체 실행 기관이 PAPER이면 현재 가상 포지션 + 오늘 PAPER 청산으로 자동 전환하고, LIVE/혼합이면 최신 계좌 조회 + 오늘 LIVE 청산을 표시한다.
- 거래 통계 탭: `LIVE / PAPER`와 `오늘 / 7일 / 30일 / 전체 / 사용자 지정`을 제공한다. PAPER에서는 실체결 가져오기와 LIVE 표시 기준을 숨긴다.
- 사용자 지정은 현지 시간의 시작일 00:00부터 종료일 23:59:59까지이며, 미래 시각은 포함하지 않는다.

## 비파괴 표시 기준

`통계 표시 기준 새로 시작`을 누른 시각을 `T`라고 하면:

- 통계는 `exit_time >= T`인 LIVE 청산부터 다시 계산한다.
- `T` 전에 진입한 열린 포지션도 `T` 이후 청산되면 포함한다.
- 체결 통계는 `executed_at >= T`부터 계산한다.
- 거래·체결·학습·PAPER·전략 여권·위험/성과회복 원장은 삭제하지 않는다.
- 열린 포지션, 주문, 가드레일, Profitability Gate에 영향을 주지 않는다.
- `전체 기록 복원`은 기준시각을 해제하고 보존된 원장을 다시 표시한다.
- 전체 범위의 기준이 활성화돼도 특정 거래소·증권사만 전체 기록을 복원할 수 있으며, 다른 기관의 기준은 유지한다.
- 기관을 선택하면 Binance·Upbit·Bithumb·Bybit·Bitget·OKX 또는 키움·신한·미래에셋·한국투자 중 그 기관의 LIVE 표시 기준만 바뀐다. `전체`을 선택하면 해당 자산군 전체 표시 기준이 바뀐다. 다른 자산군과 다른 계정에는 영향을 주지 않는다.
- PAPER는 검증 원장이므로 이 표시 기준 기능의 대상이 아니다. PAPER 시도 초기화는 Strategy Studio의 `새 검증 시작`에서만 수행하며 이전 attempt를 보관한다.

## 회귀 범위

- [x] 중앙 기관 등록부, Python 런타임·통계 집합, Web UI inventory/공통 `venueSources.ts` 목록 드리프트 차단
- [x] 미등록 기관과 암호화폐/증권 교차 서비스 source 실패 폐쇄
- [x] 캐시 값이 원장과 달라도 화면 집계는 `trade_log`를 사용
- [x] LIVE 및 레거시 LIVE 별칭만 포함하고 PAPER/LEARNING 제외
- [x] 오늘·7일·30일·전체·사용자 지정 시간 경계
- [x] 기준시각 설정/해제 시 원장 무변경
- [x] 전체 범위 기준 아래 특정 기관만 복원하는 범위 격리
- [x] 6개 거래소·4개 증권사의 기관별 표시 기준 키와 미래에셋/KIS 별칭 정규화
- [x] 개발·prekey 배포 게이트의 오프라인 격리와 실제 사용자 계정 자동탐색 금지
- [x] 주식/ETF와 암호화폐의 통화·기관 분리
- [x] 출처 없는 레거시 행 보존 및 대표 합계·Binance 추정 귀속 제외
- [x] 6개 코인 거래소와 4개 증권사 PAPER 청산의 기관·자산·KRW/USDT 분리
- [x] PAPER 일시정지 뒤 동일 attempt 재개 시 현재 근거와 활성 검증시간 보존
- [x] 새 PAPER 시도 시작 시 이전 validation/windows/attempt ID 보관 및 현재 진행률만 초기화
- [x] v3.9.1.22 이하 중지 저장본의 `paper_paused` 비파괴 마이그레이션
- [x] Web TypeScript와 production build (`50 modules`)
- [x] 전체 Python 회귀 (`2,129 passed, 8 skipped`)
- [x] v3.9.1.23 기관 등록부·통계·PAPER 생명주기 집중 회귀 (`38 passed`)
- [ ] Windows 설치·업데이트·재시작
- [ ] Binance·Upbit·Bithumb·Bybit·Bitget·OKX 실제 계정의 현재 포지션 대조
- [ ] 키움·신한·미래에셋·한국투자 실계정/모의계정 대조
- [ ] 한국시간/UTC 혼합 구형 계정 24시간 장시간 검증
- [ ] 전략 2개를 24시간 실행→일시정지→24시간 대기→재개해 대기시간 제외와 근거 연속성 확인

## Windows·기관별 외부 게이트

- [x] `WIN-BUILD` — Windows에서 공개 source fingerprint로 엔진, `NoahAI-3.9.1.23-Setup.exe`, blockmap, `latest.yml` 생성
- [ ] `WIN-UPGRADE` — 공개 v3.9.1.22에서 v3.9.1.23 업데이트·안전 종료·재시작·설정/원장 보존 확인
- [ ] `KIWOOM-E2E` — Windows OpenAPI+ 계좌 조회 전후 현재 포지션과 기간 통계 대조
- [ ] `KIS-E2E` — 토큰 재사용·호출 제한을 지키며 계좌/청산 통계 대조
- [ ] `BITHUMB-E2E` — KRW 현물 LIVE 청산·비용·오늘/기간 경계 대조
- [ ] `RECONCILE-E2E` — 거래소/증권사 원장·거래 통계·운영 KPI·AI 리포트의 같은 범위 체크섬 대조
- [ ] `SPOT-FUTURES-PAPER` — 기존 6개 거래소 PAPER/LIVE 분리와 Strategy Studio 검증 원장 무변경 확인
- [ ] `PAPER-PAUSE-RESUME` — 첨부 전략과 동등한 70건·3일 미완료 시도를 일시정지/재개해 미통과가 아닌 진행 상태, 근거·패키지 이력 보존 확인
- [ ] `PAPER-DASHBOARD` — Binance/통합 거래소/4개 증권사에서 소스 카드 활성 가상 포지션 수와 메인 PAPER KPI가 일치하고 거래 통계 전체 범위 청산 체크섬이 원장과 일치하는지 확인
- [ ] `REPORT-E2E` — 일간·주간·월간 상세 및 동일 범위의 통화별 합계 대조
- [ ] `SOAK` — 6개 거래소·4개 증권사 24~72시간 조회/집계/재시작 지속성 확인

실증권 readiness는 `python scripts/release_gate.py --profile release --readiness-account <명시적 QA계정>`처럼 승인된 QA 계정을 지정한 경우에만 실행한다. `dev`와 `prekey`는 사용자 설정·자격정보·네트워크를 열지 않는 offline readiness만 실행한다.

소스 테스트 통과는 Windows 설치본이나 외부 기관 E2E 완료를 뜻하지 않습니다. 사용자가 빌드한 새 설치기와 `latest.yml`의 버전·SHA-256·source fingerprint가 일치한 뒤에만 배포 상태를 승격합니다.
