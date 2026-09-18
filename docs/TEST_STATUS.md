## 2026-09-18 · v3.9.1.39 PnL 재감사 — 배포 보류

현재 소스 후보 **v3.9.1.39** · updater **3.9.139** · 공개 stable/latest **v3.9.1.38**. **PnL 재감사로 배포 보류**입니다.

- 시간/수량 유일 후보의 자동 주문 연결은 소유권 오인 위험으로 철회했습니다. 주문 ID 없는 과거 외부 청산 자동 복구는 아직 미완료입니다.
- PAPER/LIVE 격리, 청산 방향·중복 귀속, 미확인 비용 통화, 수수료 환급, UTC 입력 및 증권 KRW 집계를 보강했습니다.
- NoahAI 연결 청산 순손익과 거래소 수집 체결 총손익을 구분하고 미확정 거래가 있으면 부분 합계로 표시합니다.
- 미대조 성과가 수익성 검증의 정상/콜드스타트 판정과 Smart Exit 통계 조정에 사용되지 않도록 보강했습니다. 직접 학습·저널 경로까지 완료된 것은 아닙니다.
- 추가 집중 회귀 **58 passed**, 전체 **2,606 passed / 8 skipped / 3 subtests**, Node 22.23.1 Web **61 modules** build PASS. 격리 코인/주식 UI fixture에서 API 쓰기·브라우저 오류 0건과 카드 겹침 해소를 확인했습니다. 이전 2,577건 및 prekey 결과는 재감사 전 코드의 기록입니다.
- 실제 외부 청산 주문 소유권 연결, 사용자 원본 대조, 전체 AI 소비자 감사, Windows/업데이트/실계정 게이트가 남았습니다.

상세 원인·검증·미완료 게이트: [PnL 신뢰성 재감사](V39139_PNL_TRUST_AUDIT.md).

## v3.9.1.38 전략 과거재생·기관별 거래내역 (공개 기록)

기준일 2026-09-17. 제품 **3.9.1.38** / updater **3.9.138**. 현재 공개 stable/latest는 **v3.9.1.37**이며 v38 Windows 새 설치본은 아직 생성·게시하지 않았습니다.

- v3.9.1.38 버전 승격 후 전체 Python **2,572 passed / 8 skipped / 3 subtests passed**, 기존 Starlette 폐기예정 경고 1건.
- 기관별 거래내역 집중 **70 passed**, Node **22.23.1** Web production **61 modules**, 11기관 격리 브라우저와 과거재생 브라우저 검사 오류 **0건**, 매뉴얼 11개 섹션과 문서 정합 PASS.
- prekey 릴리스 게이트 PASS: 증권 집중 **176 passed / 6 skipped**, 4개 증권사 모드·무키 경로, 7개 거래소 준비도 보고, 사용자 노출 문서 동기화, 다중 거래소 불변조건 PASS. 자격정보 없는 오프라인 검사이므로 실계정 연결 증거는 아닙니다.
- 코인 과거재생과 네 증권사 × 주식/ETF 500봉 서비스 경로, 수익률/가격 정밀도, 타점·거래표 연결을 검사했습니다. 500봉 자료는 가상 시세이며 실제 시장 성과가 아닙니다.
- LIVE/PAPER 기본 탭과 접힘, 기관·계정 격리, 미확정/외부/가져오기/통화 불명/조회 실패를 검사했습니다. 거래소·증권사 전체 체결 API 또는 실계정 E2E 증거는 아닙니다.
- Windows x64/x86 빌드, PE 버전·SHA, v37→v38 자동업데이트, 키움 OCX, 기관 실계정, 24시간 이상 PAPER는 **미완료**입니다.

[v3.9.1.38 검증 원장](V39138_STRATEGY_REPLAY_LIVE_HISTORY_TEST_PLAN.md) · [과거재생](STRATEGY_REPLAY_VISUALIZATION_20260917.md) · [거래내역](SOURCE_TRADE_HISTORY_20260917.md)

## v3.9.1.37 키움 조회 대기·실패 상태 수정 (당시 기록)

2026-09-17 업데이트 채널 수정 후 최종: **2,494 passed / 8 skipped / 3 subtests passed**. 실제 electron-updater Provider 회귀 **4 passed**, 관련 집중 **51 passed**, 공개 서버 stable/latest→v36/latest.yml HTTP 200·설치기 주소 선택 확인. Web 52 modules·문서·매뉴얼·Electron/PowerShell 구문 PASS. Windows 설치/업데이트는 미완료. [업데이트 원인 분석](V39137_UPDATER_CHANNEL_INCIDENT.md).

최종 소스 검증: 전체 Python **2,491 passed / 8 skipped / 3 subtests passed**, 집중 회귀 **135 passed / 3 subtests passed**, Node **22.23.1** Web build **52 modules**, 개발 릴리스 게이트·문서 정합·11개 매뉴얼 추출 PASS. Windows 설치기/OCX/사용자 실제 계정 재현은 **미완료**입니다.

당시 소스 후보 버전: **v3.9.1.37** · updater 3.9.137. 당시 공개 기반: v3.9.1.36 stable/latest. 현재 v3.9.1.37은 공개됐으며 이 문단의 미완료 표기는 당시 기록입니다.

- 로그인 후 종목 조회 중단 로그를 반영해 TR 즉시 오류·응답 제한·요청 간격·늦은 응답을 처리합니다.
- 조회 실패를 정상 분석으로 넘기지 않고 최초 원인을 보존합니다. 계좌 목록·잔고·보유종목·미체결·ETF/거래내역 조회 계약을 수정합니다.
- 공개 v3.9.1.36 자산은 보존합니다. 실제 통신 단절·주문 불명확 상태의 안전 차단은 유지합니다.
- [검증 계획](V39137_KIWOOM_BOUNDED_QUERIES_TEST_PLAN.md) · [사용자 로그 분석](V39137_KIWOOM_USER_LOG_ANALYSIS.md).

## 이전 버전 기록 (이하 후보·공개·검증 상태는 당시 기록)

## v3.9.1.36 키움 세션·증권 PAPER·전략검증 정합 (2026-09-16 소스 후보)

현재 소스 후보 버전: **v3.9.1.36** · updater **3.9.136**. 현재 공개 기반: v3.9.1.35 stable/latest. 소스 수정·자동 테스트와 Windows 설치·실계정 검증을 분리합니다.

- 키움 자동 재로그인/호스트 재시작 고리 차단 소스 회귀: PASS.
- 네 증권사 × 주식/ETF PAPER 비용·청산·재시작 복구 회귀: PASS.
- 네 증권사 × 주식/ETF 일봉 전략검증·기관 범위·비용 계약 회귀: PASS.
- 전체 Python **2,466 passed / 8 skipped / 3 subtests passed**, Web production **52 modules**, 문서/11개 매뉴얼 정합, 개발 릴리스 게이트, 격리 브라우저 fixture: PASS. npm production 취약점 0건.
- 로컬 Web 빌드는 Node 20.11에서 성공했지만 요구 버전 Node 22.12보다 낮아 경고가 있었습니다. Windows 정식 빌드는 워크플로의 Node 22.12에서 다시 검증해야 합니다.
- Windows x64 엔진/x86 키움 호스트/설치기 및 실제 네 증권사 시세·PAPER E2E: 미완료.
- 검증 정본: [v3.9.1.36 검증 계획](V39136_KIWOOM_SESSION_STOCK_PAPER_VALIDATION_TEST_PLAN.md).


v3.9.1.35 공개 당시 기록: 원장 전체 건수/기간, 대조 전·가져오기·외부 기록을 조회 전용으로 분리 표시했습니다. Teayu 공유 스냅샷 57,666 종료 기록(확정 0, 참고 57,666)을 확인했습니다. 추가 수정 전 macOS arm64 DMG/ZIP 및 내장 엔진·로그인 화면·압축 무결성 확인 완료. 추가 수정 포함 재빌드 및 패키지 로그인·내장 UI·DMG/ZIP 검사도 완료했습니다. 당시 fingerprint는 b64fe0ec19ec8f1a43402be8012527bf1d50ab4c2857c2e47aebc693d149be6b이며 v3.9.1.35 검증 계획의 MAC-BUILD 행을 기준으로 합니다. 기존 draft r1은 추가 수정 미포함 보존본이며 SUPERSEDED입니다. 별도 GitHub draft `v3.9.1.35-macos-candidate-r2`에 4개 파일 업로드·원격 SHA-256 대조 완료. Developer ID 서명·공증 및 실계정/업데이트 검증은 미완료였습니다.

최종 자동 검증: Python **2,458 passed / 8 skipped / 3 subtests passed** (2026-09-16 macOS arm64), Web production **52 modules**, 업데이트 타이머 **4 tests**, 빌드/릴리즈 회귀 **21 tests**, 브라우저 fixture 편집·저장·대화·모드 검증 PASS. PowerShell **10개 구문 PASS**, 활성 소스 **457개 PASS**, 설치 의존성 검사 PASS, npm production 취약점 **0건**. 실제 Windows 설치·연결·장시간 운용은 미완료입니다. [원인·수정·검증 경계](../reports/v39135-release-verification.md).

## 이전 버전 기록 (아래 현재·공개 표기는 당시 기록이며 현행 판단에 사용하지 않음)

## v3.9.1.34 키움 x86·릴리즈 무결성 검증 후보 (2026-09-16)

제품 3.9.1.34 / updater 3.9.134. 전체 Python **2,424 passed, 8 skipped**, Web production build **51 modules**, npm audit 0건, x64 엔진 bootstrap smoke, x86 키움 호스트 PE·시작/종료, 설치기와 GitHub 원격 SHA 검증을 통과했습니다. 3.9.1.34는 GitHub prerelease로 게시했고 공개 안정판 v3.9.1.33은 보존했습니다. 상세 증거는 [v3.9.1.34 검증 계획](V39134_KIWOOM_X86_RELEASE_INTEGRITY_TEST_PLAN.md)을 따릅니다. 키움 OCX·실계정, v3.9.1.33 업데이트·롤백, 24~72시간 운용은 실제 환경 전까지 미완료입니다.

## v3.9.1.33 성과·증권 학습 정합 소스 후보 (2026-09-15)

시세 원인 추가 수정 후: **전체 Python 2,419 통과·8 건너뜀**. Coinone 실제 공개 차트를 거래 어댑터로 재조회해 시간 오름차순을 확인했습니다. 문서·11개 매뉴얼 정본 정합 PASS. [추가 원인 및 검증 경계](V39133_MARKET_DATA_ROOT_CAUSES.md). 아래 2,392개는 추가 수정 전 결과입니다.

제품 3.9.1.33 / updater 3.9.133. 공개 v3.9.1.32 자산은 변경하지 않습니다. 수정 후 전체 Python 2,392 통과·8 건너뜀, 웹 빌드 및 주요 React 브라우저 fixture 검증 통과. 버전 전환 후 정합 검사는 아래 보고서를 기준으로 재확인합니다. Windows 키움 호스트·계좌 E2E·새 설치본 업데이트는 미완료입니다.

[v3.9.1.33 수정·검증 범위](V39132_USER_FEEDBACK_AUDIT.md)

## 이전 v3.9.1.32 런타임 복구·주기 업데이트 소스 후보 기록 (2026-09-15)

### 알림·증권 추가 감사 후 최종 소스 회귀

- 전체 Python **2,400 passed, 8 skipped** (35.55초), 기존 Starlette/httpx 폐기 예정 경고 1건. 새 감사 테스트 70개와 국면 미확인 중 실제 청산 경로 회귀를 포함한다.
- Node22.23.1 Web production build **51 modules PASS**. 기존 500KB chunk 크기 경고는 잔존한다. updater 타이머 **4 tests PASS**.
- 문서/버전 정합, 메뉴얼11개 재추출, Web 표면 **11기관·9설정·11메뉴얼 PASS**, 설정 정본 검사 PASS.
- 검증 항목: 계정 전환 발송 경합/채널 중간 전환, 0초·0회, 첫 알림, 11기관 설정·별칭, 7거래소 시세 누락, 4증권사 실패·복구/빈 후보/오류 이벤트, LIVE와 PAPER 위험 분리, 미확정·NaN 손익 차단, 미래에셋 candles 라우팅, Discord 긴 메시지·Telegram 조회 실패.
- 주의: 미확정 증권 PnL은 신규 진입 보류 대상이다. 실제 일일 손익 계약 없는 어댑터의 거래 건수 요약은 위험 근거로 승격하지 않는다. Windows 실계정·실제 채널 수신·장시간 운용은 여전히 외부 게이트이며 이 기록은 배포 완료가 아니다.

### 1차 후보 점검 이력

- 공개 v3.9.1.31 매니페스트/Windows 자산은 보존한다. 현재 제품 소스 v3.9.1.32 / updater 3.9.132.
- 전체 Python `2,329 passed, 8 skipped` (35.49초). 이번 피드백 재현 테스트29개를 포함하며 기존 제휴 ETF 목록·NAV·추적오차·KIS 지정 ETF 계약도 회귀 통과했다.
- Node 타이머4개 통과. Node22.14.0 + lockfile 재설치 기준 Web production build `51 modules` 통과. React19.2.8/Rollup4.62.4 설치값과 lockfile 일치. npm 의존성 감사0건. 큰 JS 청크 및 Starlette/httpx deprecation 경고는 남는다.
- 문서/버전 정합 PASS, 메뉴얼11개 정본 재추출·무손실 검사 PASS, Web 표면 계약 PASS(5서비스·35기능·11기관·9설정·11메뉴얼). 이는 Windows 실제 화면·설치 완료 증거가 아니다.
- 공개 Coinone CCXT 4.5.50 시장363개·ticker363개 및 상위5개 후보, 공식 KOSPI/KOSDAQ 마스터 파싱을 사용자 키 없이 확인했다. 주문·PAPER 장시간 성공을 뜻하지 않는다.
- [검증·외부 게이트](V39132_RUNTIME_RECOVERY_TEST_PLAN.md): Windows 새 빌드/업데이트 주기/기관 실계정/24~72시간은 미완료다.

## v3.9.1.31 사용자 메뉴얼 정본·검색 소스 후보 (당시 기록 · 2026-09-14)

- 제품 3.9.1.31 / updater 3.9.131. 현재 공개 Windows 자산과 `deploy/release-manifest.json`은 v3.9.1.30이다.
- 11개 메뉴얼 정본을 다시 생성해 JSON과 완전 일치함을 확인했고 고유 탭 11개, 전체 본문 184,233자, U+FFFD/깨진 로그인 문구 0건을 확인했다.
- 현행 기관 등록부의 7개 코인 거래소·4개 증권사, Coinone LIVE 차단, Strategy Studio의 동적 기관 필터·과거 시세 재생 용어, AlphaArena PAPER 전용/LIVE 실패 폐쇄를 현재 사용법과 대조했다.
- 메뉴얼·Web UI·고급 기능 집중 회귀 `68 passed`, 전체 Python 회귀 `2,300 passed, 8 skipped`, 전체 Web 표면 계약 감사 `PASS`(5개 서비스·35기능·11기관·9설정·11메뉴얼), 문서/버전 정합 검사 `PASS`, 로컬 Node 20.11.0 production build `51 modules`와 production 의존성 취약점 `0건`을 확인했다. 릴리스 요구 Node 22.12+ Windows 빌드는 외부 게이트다.
- 로컬 정적 preview는 Gateway token이 없는 개발 셸에서 메뉴얼 API를 불러오지 못하므로 실제 전체 렌더 증거로 사용하지 않았다. Windows 설치기·업데이트/재시작·DPI·검색 이동은 새 산출물의 외부 게이트다.
- 외부 게이트와 배포 판정은 [v3.9.1.31 검증·배포 계약](V39131_READABLE_MANUAL_RELEASE_TEST_PLAN.md)에 기록한다.

## v3.9.1.30 통계·시간봉·증권 연결 공개 기준 (2026-09-14)

- 제품 3.9.1.30 / updater 3.9.130 Windows 자산이 공개됐으며 `deploy/release-manifest.json`의 설치기·blockmap·`latest.yml` 해시가 공개 기준이다. 실계정 증권사·장시간 PAPER는 게시와 별도의 운영 게이트다.
- 추가 회귀는 `tests/test_v39130_contracts.py`. 7개 코인/4개 증권사 기관 분리·기간 전 제한·캐시 무효화·선언 시간봉·상위봉 미래 데이터 차단·Coinone·키움 timeout을 검사한다.
- 실제 React 컴포넌트 QA fixture: `webui/qa/strategy-feedback.html`. 브라우저에서 암호화폐/주식 1280·1440·1920, 배율 125%, 날짜·상태·v1 비교·보완 포커스 및 예제→보완→승인→과거재생→PAPER 완료 동선을 확인했다. 브라우저 서비스 호출은 합성 fixture이며 실계정 증거가 아니다.
- 최종 전체 회귀 `2,296 passed, 8 skipped` (36초), Node 22 production build `51 modules`, Web 표면 계약 감사 PASS(11기관)를 확인했다. Starlette/httpx deprecation 및 큰 JS 청크 경고는 남는다.
- SourceWorkspace는 연결/미연결 × 코인/주식 × 800/1280/1440/1920의 16개 조합을 추가 확인했다. 계정 거래 권한 차단 2개 조합에서는 승인 안내와 409 사용자 문구 변환을 확인했다. StrategyStudio 6개와 합쳐 브라우저 24개 조합이 통과했다.
- 7개 코인 공개 15m 시세 조회·시간순 정렬을 확인했으며 빗썸 공식 15m/4h는 각각 완료 199봉을 확인했다. 인증·주문·장시간 운용 증거가 아니다. [v3.9.1.30 검증 계획](V39130_STRATEGY_VENUE_CONSISTENCY_TEST_PLAN.md)의 미완료 환경 게이트를 소스 테스트로 대체하지 않는다.

## v3.9.1.29 전략 공용계층·운용용량·Coinone 소스 후보 (2026-09-12)

- 현재 소스 제품 버전은 v3.9.1.29, updater SemVer는 3.9.129입니다.
- 전략 제작·PAPER 검증은 회원등급과 분리하고, 실제 계정 관리형 다중포지션만 무료 최대 3개/코인 유료 최대 5개로 분리했습니다. 집중운용은 1개이며 위험계층은 언제든 더 작게 제한합니다.
- Coinone은 PAPER·공개시세 준비 상태이며 LIVE는 실계좌 주문·부분체결·비용·복구 E2E 전까지 실패 폐쇄합니다. 자동 회귀 통과를 LIVE 준비 완료로 승격하지 않습니다.
- NoahAI 전체 Python 회귀 `2,251 passed, 8 skipped`, AI Provider·Web 설정 집중 회귀 `180 passed`, 추가 국내 현물·PAPER·Web 집중 회귀 `172 passed`, Node Web production build `51 modules`와 Web 표면 정합 감사를 통과했습니다. 8개 skip은 별도 OS·외부기관 환경 항목입니다.
- AI 진단 회귀는 모델 목록과 실제 호출의 분리, 요청 모델과 Provider 응답 모델 기록, GPT-6 reasoning 파라미터, 토큰·비용 원장과 저장 전 초안 표시를 포함합니다. 실제 사용자 Project의 권한·청구·Usage 대조는 Windows 설치본에서 별도 외부 게이트입니다.
- 공개 v3.9.1.28 installer·blockmap·`latest.yml`과 manifest는 변경하지 않습니다. v3.9.1.29 Windows 산출물과 외부기관 게이트는 미완료입니다.

## v3.9.1.28 체결 정합성·통계 화면·처음 사용 빠른 시작 공개판 (2026-09-12)

- 현재 소스 제품 버전은 v3.9.1.28, updater SemVer는 3.9.128입니다. 창 제목은 Electron 런타임 `43.4.0`이 아니라 제품 버전을 사용하고, 사용자 제목에서 구현 방식인 `Web UI`를 제거했습니다.
- 정확한 청산 주문 ID와 체결수량으로 원장을 대조하고 거래소 실현손익과 비용 반영 순손익을 분리합니다. 대조할 수 없는 과거 자료는 임의 보정하지 않고 `대조 미확정`으로 유지합니다. 코인 6개 거래소와 주식·ETF 4개 증권사는 각 기관의 체결 계약에 맞춰 같은 통계 의미를 사용합니다.
- 통계 표의 스크롤 소유자와 메시지 영역을 분리해 체결 동기화 뒤에도 헤더가 유지됩니다. 다른 주요 탭의 조건부 메시지도 같은 레이아웃 회귀를 적용했습니다.
- 설정의 `처음 사용 · 빠른 시작`은 자산군과 기관 하나를 선택해 기존 설정의 안전한 PAPER 시작값만 대기 상태로 구성합니다. 새 모드·새 위험 정책을 만들지 않으며 `전체 설정 저장`, 자격증명 확인, 서비스 시작은 각각 사용자 확인을 요구합니다. 9개 고급 설정 탭과 Strategy Studio Level 1~4는 그대로 유지됩니다.
- NoahAI 전체 Python 회귀 `2,235 passed, 8 skipped`, v3.9.1.28 관련 집중 회귀 `103 passed`, Node Web production build `51 modules`를 통과했습니다. daltrading 전략 허브·초보자·설정 가이드 포함 전체 회귀는 `100 passed`이며 신규 기관의 LIVE 온보딩 실패 폐쇄도 포함합니다.
- v3.9.1.28 installer·blockmap·`latest.yml`과 manifest가 게시됐습니다. 실제 거래소·증권사 계정 대조, Windows DPI/해상도와 초보 사용자 동선은 공개 사실과 별도인 환경별 검증 범위입니다.

## v3.9.1.27 Strategy Assistant 연속성·AI 비용·모델 라우팅 공개판 (2026-09-11)

- 현재 제품 버전은 v3.9.1.27, updater SemVer는 3.9.127입니다. `deploy/release-manifest.json`은 `windows_verified_release_candidate`, `publish_ready=true`이며 v3.9.1.27 installer·blockmap·`latest.yml` 공개 URL의 HTTP 200을 확인했습니다. v3.9.1.26은 직전 공개·롤백 기준 자산으로 보존합니다.
- 단일 확인창, 전략 버전 생성 시각, 외부 AI 429의 로컬 규칙 컴파일 fallback, 설명 수준별 프롬프트·캐시, AI 답변의 검토 후 재분석 전달을 전용 회귀로 고정했습니다.
- 사용자 요청형 성공 호출만 실제 토큰·기준일 단가로 예상 비용을 계산하고, 토큰·단가가 없으면 0원이 아닌 `비용 미산출`로 분리합니다. 자동매매 백그라운드 AI와 Provider 전체 청구액은 이 카드의 범위가 아닙니다.
- 역할별 Provider·모델 구성을 한 화면에서 확인하고, DeepSeek 공식 `deepseek-v4-flash` 자동 최신 별칭·`deepseek-v4-pro`·별도 비전 실험 모델을 구분합니다. 일반 Flash의 이미지 입력은 호출 전에 차단합니다.
- 암호화폐와 주식·ETF의 공통 분석 경로를 합성 입력으로 검증했습니다. 실제 Provider 429, Windows DPI, 패키지 업데이트/재시작, 거래소·증권사 실환경은 공개 후에도 별도 외부 게이트입니다.
- 최신 기록은 OpenAI Project 직접 회귀 `8 passed`, 관련 AI·설정·차트 집중 회귀 `56 passed`, 전체 Python 회귀 `2,208 passed, 8 skipped`, Node 22 Web production build `50 modules`, production 의존성 취약점 `0건`, 문서·사용자 노출 동기화와 Web UI 전체 표면 계약 `PASS`입니다. 경고 1건은 기존 Starlette/httpx 호환성 폐기 예정 경고입니다.
- 실제 사용자 키·계정·네트워크를 사용하지 않는 `release_gate --profile prekey`도 PASS입니다. Windows 설치본은 공개됐지만 Provider 계정 권한·실청구, 업데이트/재시작, 거래소·증권사 실연동과 장시간 운용은 아래 외부 게이트로 남깁니다.

## v3.9.1.26 Strategy Studio 위험 입력·질문형 사용자 확인 당시 소스 회귀 (2026-09-10 · 이력)

- 당시 소스 제품 버전은 v3.9.1.26, updater SemVer는 3.9.126이었습니다. 공개 v3.9.1.25 installer와 manifest를 직전 자산으로 보존했고, 이 섹션의 `pending_windows_rebuild`·`publish_ready=false`는 v3.9.1.26 빌드 전 판정 이력입니다. 현행 판정은 문서 최상단 v3.9.1.27 섹션을 따릅니다.
- 거래당 계좌 손실·1회 위험·risk per trade와 증거금/종목당 투자 비중의 명시적 퍼센트 구조화, 단위 없는 숫자 실패 폐쇄, 분석 위험값의 UI 동기화, 사용자 확인 보완의 허용 필드를 회귀로 고정했습니다.
- `원문 그대로 구조화 / 질문으로 함께 완성 / 기본 NoahAI에 맡기기`를 구분하고, AI 예시 비실행·사용자 답변 별도 해시·원본 파일 불변·기존 원문 충돌 차단을 고정했습니다. 기본 NoahAI/confirm과 사용자 독립 전략의 책임·성과 근거도 계속 분리합니다.
- v3.9.1.26 전용 회귀 15건, 전체 Python 회귀 `2,179 passed, 8 skipped`, Web production build `50 modules`, 문서/버전 정합과 Web UI 전체 표면 계약 `PASS`를 확인했습니다. 위험률 변경 무결성, 원문-보완 충돌 차단과 `webui/src/` 사용자 문서 동기화 게이트도 포함합니다. Windows 암호화폐/주식 실제 화면과 v3.9.1.25→v3.9.1.26 업데이트는 새 산출물에서 확인해야 합니다.

## v3.9.1.25 Strategy Studio 안내·AI 문맥 복구 소스 회귀 (2026-09-09)

- 현재 소스 제품 버전은 v3.9.1.25, updater SemVer는 3.9.125입니다. 공개 v3.9.1.24 installer와 manifest는 직전 공개 자산으로 보존하며 v3.9.1.25 Windows 빌드·업데이트 전에는 `pending_windows_rebuild`, `publish_ready=false`입니다.
- `AI에게 묻기`의 AI 커스텀 문맥 라우팅, 빈 Provider 응답 실패 처리·비캐시, Provider 실패 로컬 정본 대체, Strategy Studio keep-alive, 5분 안내의 기본 NoahAI/전략 제작 분리와 차단 상세를 집중 회귀로 고정했습니다.
- v3.9.1.25 단독 회귀 `8 passed`, Web 플랫폼·과거재생·전략 의미·PAPER·AI 어시스턴트 집중 회귀 `199 passed`, 전체 Python 회귀 `2,148 passed, 8 skipped`, Web production build `50 modules`, 문서/버전 및 전체 Web 표면 계약 `PASS`를 확인했습니다. 양방향 `independent_entries` 재생, 방향 충돌 HOLD, NoahAI 기본 진입 confirm 전략의 과거재생 비대상·PAPER 직접 연결 계약을 포함합니다.
- Windows 입력/파일 보존·실제 Provider·DPI E2E는 설치본 생성 뒤 확인합니다.

## v3.9.1.24 Strategy Studio·Strategy Hub UX 소스 회귀 (2026-09-09)

- daltrading 회원 전용 라이선스 브라우저 화면은 로그인 후 원래 주소로 복귀하고, API는 UTF-8 JSON 401을 유지하도록 계약을 분리했습니다. 제출은 1단계 서버 패키지 분석과 2단계 추출 범위·권리 확인으로 분리하며 수동 태그 누락·불일치를 차단합니다. E0 신규 공개본은 E2~E5 검증 랭킹과 분리합니다. 달트레이딩 운영 배포와 NoahAI 클라이언트의 운영 브라우저 왕복은 v3.9.1.24 E2E에서 확인해야 합니다.
- v3.9.1.24 installer와 manifest가 이후 공개됐으며 v3.9.1.25의 직전 공개 자산으로 보존합니다.
- Strategy Studio 반응형 기관 탭, 실행 풀 안내, 고급 JSON 확인, 최종 재검증 세부 설명을 v3.9.1.24 회귀 범위로 분리했습니다.
- sibling 버전 PAPER 실행 권한 보호, 버전별 저장 파라미터 표시와 계정 로컬 PAPER 상세 근거 내보내기를 추가했습니다. 개인 세부 거래는 `.noahstrategy`와 허브 자동 전송에 포함하지 않습니다.
- Strategy Hub E0 카드는 E2~E5 검증 랭킹과 분리하고 순위·0.0점 대신 성과 점수 없음·검증 시작 전으로 표시하며 제작자 자기설명과 서버 검증 근거를 분리합니다.
- NoahAI 전체 Python 회귀 `2,136 passed, 8 skipped`, 변경 집중 회귀 `66 passed`, daltrading 전체 회귀 `93 passed`를 확인했습니다.
- Web production build는 `50 modules`로 통과했습니다. `js-yaml` 4.3.2 보안 고정 뒤 npm 전체/production audit는 취약점 `0건`입니다. 로컬 Node 20.11.0은 빌드에는 성공했지만 프로젝트 릴리스 요구 `22.12+`보다 낮으므로 Windows 빌드는 요구 버전에서 수행해야 합니다.
- 문서/버전 정합, Web UI 전체 표면 계약과 활성 Python 소스 감사도 `PASS`입니다.
- source fingerprint 참고값은 `59c67cc3a82a4e67222d2be30cfb19672f4d290c0f317520a94c9957fadb9c74`이며 Windows 빌드 직전 현재 소스에서 다시 산출합니다.

## v3.9.1.23 LIVE 통계 정본·기간·비파괴 기준 공개 회귀 (2026-09-08)

- 기관 등록부에서 Python 런타임·통계 집합을 파생하고, Web UI inventory/공통 `venueSources.ts` 목록과 서비스별 통계 allowlist가 어긋나면 실패하는 회귀를 추가했습니다. 미등록·교차 서비스 기관은 실패 폐쇄합니다.
- LIVE 청산 원장 우선, PAPER/LEARNING 제외, 구형 `optimized/manual` LIVE 마이그레이션, KRW/USDT 분리, 오늘·7일·30일·전체·사용자 지정 경계와 비파괴 기준시각 설정/해제를 회귀로 고정했습니다.
- 전체 Python 회귀 `2,129 passed, 8 skipped`, v3.9.1.23 기관 등록부·통계·PAPER 생명주기 집중 회귀 `38 passed`, Web TypeScript/Vite production build `50 modules`를 통과했습니다.
- Windows 설치기·업데이트·현재 계좌 대조, 6개 거래소·4개 증권사 실환경 테스트는 아래 검증 원장에 따라 계속 확인해야 합니다.
- 개발 release gate는 증권 계약 회귀 `175 passed, 6 skipped`, 8개 지원 모드 매트릭스와 4개 증권사 mock hardening을 통과했습니다. dev/prekey는 이제 실제 사용자 폴더를 자동 탐색하거나 브로커 네트워크를 호출하지 않는 offline readiness만 실행합니다. 실연동은 승인된 QA 계정을 명시한 release 게이트로 분리했습니다.
- 소스 fingerprint 참고값: `974bfc37b4d35f8b055bbe5a05f744779a69d003c3e1377eb64d8d2879c45eff` (Windows 빌드에서 최종 재산출).
- Windows 자산은 공개됐습니다. 자세한 범위와 남은 운영 관찰은 [v3.9.1.23 검증 원장](archive/release/V39123_CANONICAL_LIVE_STATISTICS_TEST_PLAN.md)을 따릅니다.

## v3.9.1.22 공통 투자금·성과회복·병행 PAPER 소스 회귀 (2026-09-06)

- 기존 사용자 fixed Notional 보존과 선택형 account-risk 계산, SL 거리·평가금·성과 위험배수·마진/노출 상한을 순수 계약으로 검증했습니다.
- Binance와 Unified 5개 거래소, 키움·신한·미래에셋·한국투자 공통 경로 연결 및 CCXT contractSize 최소주문 산식을 검증했습니다.
- PAPER/LEARNING에서 실계좌 잔고를 읽지 않고 LIVE 활성 전략과 PAPER 관찰 전략을 별도 풀·가상 포지션으로 유지하는 집중 회귀를 추가했습니다.
- 성과회복 KPI는 거래별 순수익률을 사용하며 KRW/USDT 현금 손익 합계와 분리하고 구간 안정률을 실제 OOS 워크포워드로 오인하지 않도록 명칭·방법을 기록합니다.
- v3.9.1.22 전체 Python 회귀 `2,097 passed, 8 skipped`, 투자금·전략·기관 집중 회귀 `176 passed`, 증권 개발 게이트 `169 passed, 6 skipped`, Web TypeScript/Vite production build `49 modules`를 통과했습니다.
- daltrading 전략 허브 전체 회귀 `85 passed`, NoahAI Labs production build `225 pages`, lint 오류 `0건`, info/ip 통합 사이트 production build `45 pages`를 확인했습니다. 공개 URL 검증은 실제 배포 뒤 별도 수행합니다.
- 통합 거래소의 percent-point 변동성을 fraction으로 명시 변환하고 Binance의 결측 변동성을 임의 2%로 추정하지 않는 시장 위험배수 회귀를 추가했습니다. 기존 계정 `legacy_venue` 상태도 Web 설정에서 빈 값이 아니라 전환 사유와 저장 전 초안으로 표시합니다.
- Strategy Studio Level 4는 전략 요청값·계좌 정책·시장/성과 적용 전 허용값을 비교하며, 암호화폐 6개 거래소와 국내 증권 4개 경로는 주문 직전 예상손실·Notional·증거금·레버리지·수량과 제한 사유를 XAI에 기록합니다.
- 활성 소스·설정 정본·AI 설정 소유권·문서/버전·Web UI source contract·dev release gate가 PASS입니다. 로컬 Node `20.11.0`은 프로젝트 요구 `22.12+`보다 낮지만 번들은 성공했으며, Rollup macOS ARM 선택 의존성을 복구한 `npm audit` 결과는 취약점 0건입니다.
- 소스 fingerprint: `7b6e0e9ad64f59689d9830d1adc6c62c61f569597fa8d328bcb9ab4474311df4`.
- 개발 게이트의 한국투자 읽기 연결은 성공했지만 주문 드릴은 `EGW00133` 1분 토큰 제한으로 실패했고, 키움은 macOS라 건너뛰었습니다. Windows v3.9.1.22 설치기·자동 업데이트·승인 최소 LIVE 주문·6개 거래소/4개 증권사 24~72시간 병행 PAPER는 **PENDING**입니다.

## v3.9.1.21 PAPER 손익·비용·거래소 귀속 소스 회귀 (2026-09-04)

- 사용자 피드백·주식/ETF 정합 집중 회귀 `205 passed, 6 skipped`, 전체 Python 회귀 `2,052 passed, 8 skipped`를 통과했습니다.
- 공개 v3.9.1.20의 중지 권한·열린 포지션 복구·멱등 청산·다중 전략 순환·UPBIT cache·학습 journal·Algo TP/SL 회귀를 유지했습니다.
- Teayu v3.9.1.19 원장의 Binance 184행 중 근거가 충분한 177행만 기본 비용 계약 추정 대상으로 판정하고 근거 부족 7행은 `비용 미확정·과거 손익 미확정`으로 승패·순손익 확정 통계에서 제외했습니다.
- Upbit·Bithumb·Bybit·Bitget·OKX 각각의 활성 PAPER 포지션이 청산 전에 비용 차감 후 미실현 PnL을 갱신하고, Recorder가 거래소별 최신 표본과 실제 로그 소유 거래소를 사용하는지 검증했습니다.
- Teayu `trading_binance.log`에서 타 거래소 소유 결정 3,245행이 과거에 `(ex=binance)`로 잘못 기록된 것을 확인했습니다. 신규 기록은 실제 실행 거래소로 라우팅하고 구형 행은 Binance 화면에서 실패 폐쇄합니다.
- 성과회복 제한은 6개 거래소별 최근 완료 거래를 독립 조회하고 순손익 비용을 이중 차감하지 않으며, 위험배수·포지션·레버리지 제한에 전달되는 공통 실행 경로를 확인했습니다.
- 키움·신한·미래에셋·한국투자 공통 경로에서 주식/ETF 활성 PAPER 포지션의 현재가 기준 KRW 순손익, 수수료·예상 세금·슬리피지, 부분청산 비용 배분, 보유량 초과 매도 차단을 검증했습니다.
- 증권 PAPER 성과 표본은 해당 증권사의 유효한 PAPER 원장만 사용하고 LIVE 체결을 호출하지 않으며, XAI 로그는 명시한 실행 증권사에 귀속되는지 검증했습니다.
- 다중 PAPER 관찰 전략 공유 슬롯 round-robin, UPBIT ticker cache, append-only 학습 journal 복구, Binance Algo TP/SL 감사를 검증했습니다.
- v3.9.1.19 UNIFIED Binance 귀속·`.noahstrategy` 이중 해시·검증 대상 분리 누적 회귀를 통과했습니다.
- Web UI는 Node `22.23.1`에서 TypeScript/Vite production build 49 modules, npm audit 취약점 0건을 통과했습니다. chunk 크기 권고 경고는 있으나 빌드 실패는 아닙니다.
- 문서/버전 정합 검사, Web UI parity source contract, dev release gate를 통과했습니다. dev gate의 실주문은 비활성이고 키움은 macOS에서 OS 차단됩니다.
- 소스 fingerprint: `1553a72723c3a5fe9503fe056065399e7887f1008356d407a3b5eeed9c11c1f0` (Windows 빌드가 생성하는 release manifest와 대조).
- 공개판은 v3.9.1.20입니다. v3.9.1.21 Windows 엔진·설치기·blockmap·`latest.yml`, 자동 업데이트와 6개 거래소·4개 증권사 24~72시간 PAPER E2E는 **PENDING**입니다.

## v3.9.1.18 OKX 후보 복구·전략 검증 근거 소스 회귀 (2026-09-03)

- 첨부 피드백의 약 1분 간격 `코인 선택 데이터 저장 완료`를 Teayu 원장과 대조해 OKX 정상 재선정이 아니라 `candidate_evaluation_unavailable / fallback_unscored` 10개가 반복 저장된 사실을 확인했습니다.
- OKX CCXT ticker가 `quoteVolume=None`인 실제 파생 입력에서 원문 `volCcy24h`(기초자산 수량)×현재가로 USDT 거래대금을 복원하고, `vol24h`/CCXT `baseVolume` 계약 수를 수량으로 오인하지 않는지 검증했습니다. Bybit·Bitget의 명시적 quote 거래대금과 국내 현물의 base 수량×현재가 계약도 함께 회귀 고정했습니다.
- 동일 실패 스냅샷은 기본 15분에 한 번만 저장하고, 미산출 복구는 즉시 1회 뒤 60초→120초→240초·최대 15분으로 늘어나는 거래소별 backoff를 검증했습니다.
- 거래소별 거래대금 단위 회귀를 보강한 집중 회귀 `44 passed`를 유지하고, v3.9.1.18 전략/PAPER 추가 회귀와 전체 Python 회귀 `1,992 passed, 8 skipped`를 통과했습니다.
- Web UI TypeScript/Vite production build(49 modules), Web UI parity, 활성 소스, 문서/버전 정합, Web engine spec, dev release gate를 통과했습니다. 로컬 Node `20.11.0`은 릴리스 요구 `22.12+`보다 낮으므로 Windows 패키징은 요구 버전에서 다시 수행해야 합니다.
- 공개 v3.9.1.17 manifest fingerprint `0d9c8a...`와 현재 v3.9.1.18 소스 fingerprint `f977adea6f98...`는 다릅니다. 공개 자산에 이 수정이 포함됐다고 판단하거나 같은 버전으로 덮어쓰면 안 됩니다.
- 다음 불변 버전 Windows 빌드·OKX 실제 ticker 콜드/웜 선정·장시간 PAPER·업데이트 E2E는 **PENDING**입니다.
- Strategy Studio API가 PAPER를 거래소·기준통화별로 분리하고 과거 미확정 행을 승패에서 제외하는 회귀를 추가했습니다.
- Web UI에 Validation Lab 상세·거래소별 PAPER 근거·현물/선물 호환성 안내를 추가했으며, 대표 자연어/Pine 의미 코퍼스는 지원 사례와 실패 폐쇄 사례를 함께 포함합니다.

## v3.9.1.17 전략 의미 보존·PAPER 격리·AI 리포트 정산 회귀 (2026-09-01)

- Teayu 원장을 읽기 전용으로 조사해 마지막 NoahAI 청산 직후 PAPER 관찰 전략이 등록됐고, 그 뒤 `no_strategy_matched_current_scope_regime_and_entry` 전역 차단이 25,201건 누적된 순서를 확인했습니다. 분석·학습은 계속됐으므로 worker 정지나 시장 무신호가 아닌 PAPER 권한 혼입 오류입니다.
- PAPER 후보만 평가하고 일치하지 않을 때 기본 NoahAI 신호로 위임하고, 사용자가 최종 적용한 전략은 조건 미충족 시 HOLD하는 계약을 분리했습니다.
- Binance·Upbit·Bithumb·Bybit·Bitget·OKX 6개 거래소 PAPER 불일치 위임, 적용 전략 실패 폐쇄, 독립 전략 방향·진입조건·TP/SL 단위 준비도를 집중 회귀로 고정했습니다.
- Teayu의 PAPER 관찰 6개를 재평가한 결과 실행 준비 완료는 0개였습니다. 독립 전략 5개는 방향과 선언형 진입조건이, confirm 전략 1개는 TP/SL 실행 단위가 부족했으며 사용자 파일은 변경하지 않았습니다.
- 전략 문서 저장, 실행 준비, 사용자 승인, PAPER 전진검증을 서로 다른 게이트로 분리했습니다. 독립 전략은 LONG/SHORT별 선언형 진입 규칙과 전략 소유 TP/SL이 필요하며, `confirm` 전략만 명시적으로 NoahAI 스마트 청산을 상속할 수 있습니다. 단위 누락·비정상 수치·위험 범위 초과는 승인 전에 거부합니다.
- AI 리포트 요약과 상세를 같은 `trade_log` 청산 원장과 동일한 기간 하한·현재시각 상한에 연결했습니다. 100건 페이지 이동, 전체 기간 체크섬, 거래소·종목·방향·실현손익·손익률·수수료·진입가·청산가 표시와 미래 시각 행 제외를 회귀로 확인했습니다.
- confirm 방향 보존, 자연어 양방향 분리, Pine RSI 별칭·지원 가능한 AND 복합조건 해석, 미해석 별칭 실패 폐쇄, TP/SL 명시 단위와 공통 주문 범위, 무음 보정 금지, 저장 직전 서버 재검증을 회귀로 고정했습니다.
- Web AI 멘토를 일반 어시스턴트 호출이 아닌 8문항 구조화 후보 생성에 연결했습니다. 관리 프리셋은 선언형 LONG/SHORT·TP/SL·위험예산을 가진 실행 초안이며 공통 준비 계약 통과 여부를 표시합니다. 불러오기는 저장·승인·과거검증·PAPER·LIVE를 자동 실행하지 않습니다.
- 외부 LLM이 원문과 다른 실행 조건·방향·TP/SL·비중을 제안해도 로컬 결정형 컴파일 결과만 주문 정본으로 사용하고 거절 경로를 XAI에 남깁니다. 분석 뒤 실행값이 바뀌면 source-grounding 해시 불일치로 저장을 차단합니다.
- `request.security`·동적 `input.*`·사용자 함수·컬렉션·rolling state·position price 기반 동적 청산 Pine은 단순 규칙으로 축소하지 않고 구체적인 미지원 사유로 차단합니다.
- 과거검증은 Upbit·Bithumb KRW 현물과 Binance·Bybit·OKX·Bitget USDT 선물의 실제 venue·시장유형·시간봉·기준통화를 기록합니다. PAPER 및 리포트의 KRW와 USDT는 환율 근거 없이 합산하지 않습니다.
- LIVE 일일 손실 판정을 거래소·실행모드·기준통화별로 격리했습니다. 6개 거래소 LEARNING/PAPER는 실계좌 잔고 조회와 손실 알림을 생성하지 않고, LIVE 빈/무효 응답은 100% 손실이 아닌 `risk_data_unavailable`로 분리합니다.
- 거래소×모드 알림 격리, 실제 LIVE 손실, 빈 잔고, 출금 오인 방지, 거래소별 ON/OFF, LIVE 메시지 표시 집중 회귀 `41 passed`를 통과했습니다.
- v3.9.1.17 전체 Python 회귀 `1,974 passed, 8 skipped`, 내장/Web 매뉴얼 스냅샷 정합, Web UI TypeScript/Vite production build를 통과했습니다.
- Web UI TypeScript/Vite production build는 49 modules로 통과했습니다. 로컬 Node `20.11.0`은 프로젝트 요구 `22.12+`보다 낮아 Windows 릴리스 빌드는 요구 버전으로 다시 수행해야 합니다.
- daltrading은 전략 제작 멘토를 앱 내부 기능으로, 웹 허브를 회원 제출·검토·탐색·다운로드 기능으로 분리한 안내를 `c12cac8`로 운영 배포했고 공개 가이드 경로를 확인했습니다.
- NoahAI Labs는 v3.9.1.16을 현재 공개 Windows판으로 유지하면서 v3.9.1.17을 소스 후보로 분리한 Strategy Studio·LLM 정본을 `c21cfb1`로 Cloudflare Pages에 배포했고 공개 제품·source 경로를 확인했습니다.
- 공개 v3.9.1.16 `latest.yml`과 Windows 자산은 변경하지 않았습니다. v3.9.1.17 Windows 설치기·업데이트·실계정·6개 거래소 PAPER 24~72시간 E2E는 **PENDING**입니다.
- 배포 상태: `pending_windows_rebuild`, `publish_ready=false`.

## v3.9.1.16 거래소 실행 계약·KRW 현물 주문 정합 회귀 (2026-08-29)

- Upbit·Bithumb KRW 현물과 Binance·Bybit·OKX·Bitget USDT 선물을 상품·방향·기준통화·주문단위로 분리했습니다. 국내 현물 `SHORT`는 신규 공매도가 아니라 NoahAI 관리 LONG의 청산 신호이며, 관리 원장이 없으면 실행하지 않습니다.
- Upbit 시장가 매수는 승인된 KRW 총액, 시장가 매도는 base 코인 수량을 제출합니다. Bithumb은 기존 base 수량 계약을 유지해 거래소별 주문 규격이 서로 전파되지 않도록 했습니다.
- 포지션 원장 단계에 국내 현물 SHORT 실패 폐쇄 방어를 추가하고, Upbit BUY/SELL·Bithumb 분리·국내 현물 방향·Bybit/Bitget/OKX 선물 청산 파라미터·PAPER 원장 경계를 결정적 회귀로 고정했습니다.
- 10초 거래 루프마다 반복되던 거래소별 15분봉 시장국면 요청과 성과 DB 조회를 기본 5분 TTL single-flight 캐시로 합쳤습니다. Upbit·Bithumb 대표 국면 심볼은 `BTC/KRW`입니다.
- v3.9.1.16 집중 회귀 `29 passed`, 전체 Python 회귀 `1,911 passed, 8 skipped`, Python compile, Web UI 소스 parity 감사, release gate dev 프로필을 통과했습니다.
- Web UI TypeScript/Vite production build는 49 modules로 통과했습니다. 로컬 Node `20.11.0`은 프로젝트 요구 `22.12+`보다 낮아 엔진 경고가 있었으므로 Windows 릴리스 빌드는 요구 Node 버전으로 다시 수행해야 합니다.
- Windows 설치기·blockmap·`latest.yml`, v3.9.1.15→v3.9.1.16 업데이트, Upbit/Bithumb 승인된 최소 LIVE, 해외 선물 one-way/hedge, 6개 거래소 PAPER 24~72시간 E2E는 **PENDING**입니다.
- 배포 상태: `pending_windows_rebuild`, `publish_ready=false`.

## v3.9.1.15 주문규격·Level 4 집중 회귀 (2026-08-28)

- NoahAI Strategy Studio의 정식 명칭, Level 1~4 설명, `.noahstrategy` 호환, 무료 Verified Strategy Hub 범위를 클라이언트·내장 메뉴얼·제품 문서에 맞췄습니다.
- daltrading의 회원 제출→운영자 승인→인증 다운로드→제작자 공개 중지 요청→즉시 신규 다운로드 차단→운영자 확정/반려 흐름을 추가했습니다. 운영 서버 DB 스키마 적용·서비스 재시작과 공개 Hub/가이드/제출 안내 경로를 확인했으며, 실제 회원·운영자 계정 왕복 E2E는 별도 게이트입니다.
- daltrading 무료 다운로드를 `FREE` 취득 거래와 계정별 영구·비독점 실행 라이선스로 원자 기록하고, 반복 다운로드 멱등성, 내 라이선스 화면·API, 공개 중지 뒤 기존 취득자 재다운로드/미취득자 차단, 기존 다운로드 감사의 1회 마이그레이션을 추가했습니다. daltrading 전체 회귀는 `81 passed`입니다.
- NoahAI Labs Strategy Studio 4개 언어 제품 페이지는 production build 225 pages, ip.noahai.net 기술·IR 설명은 production build 45 pages를 통과했습니다. `noahailabs.com`의 제품 페이지·LLM 정본·사이트맵과 `ip.noahai.net` 공개 문구를 배포 후 운영 URL에서 확인했습니다.
- `min_trade_amount=20`, 초기 위험배수 `0.10`, Binance 최소 주문 `5`인 결정적 케이스에서 수량 `0.51`, 주문금액 `5.10`이 거래소 규격을 통과함을 확인했습니다.
- 사용자 목표금액·Opportunity 승인 수량 상한·거래소 최소 주문규격을 분리하고, 승인 상한이 거래소 최소보다 작으면 수량을 상향하지 않고 차단하는 회귀를 추가했습니다.
- `SPLIT`의 `authorized_quantity`에 이미 반영된 비율을 후단에서 다시 곱하지 않는 회귀를 추가했습니다.
- 구형 `risk_budget`의 `risk_model` 정규화, Level 4 IR 투영, 하드 가드레일 해제 필드 저장 거부를 검증했습니다.
- 주문·IR·AI 커스텀 집중 회귀는 `PYTHONPATH=. pytest -q tests/test_v39115_order_contract_and_level4.py tests/test_noah_strategy_ir_v1.py tests/test_ai_custom_p1_p3_features.py` 기준 `26 passed`입니다.
- 전체 Python 회귀 `1,898 passed, 8 skipped`, Web UI TypeScript/Vite production build 49 modules와 문서 정합 검사를 통과했습니다. Windows 패키지·PAPER/LIVE E2E는 별도 게이트입니다.
- 배포 상태: `pending_windows_rebuild`, `publish_ready=false`.

## v3.9.1.15 Binance 후보 선정 복구·사이클 정합성 회귀 (2026-08-28)

- Teayu 로그의 10개 `fallback_unscored` 반복은 거래 부적합 판단이 아니라 실행 가능한 후보 0개의 복구 실패임을 확인했습니다.
- Binance 상품·티커·백업 캐시를 현재 계정의 쓰기 가능한 폴더로 격리하고, 미산출 결과의 single-flight 캐시를 즉시 무효화하며 폴백→폴백 재선정을 완료로 기록하지 않도록 수정했습니다.
- 미산출 후보만 있는 동안 반복 시장국면·상세 분석을 생략하고, 기본 60초 쿨다운의 단일 백그라운드 재선정만 수행하도록 검증했습니다.
- 설정/API 런타임 교체 시 Evaluator의 Binance 클라이언트도 Trader와 같은 새 객체로 갱신함을 회귀로 고정했습니다.
- Teayu 계정 범위의 공개 읽기 전용 Binance 스모크에서 약 4.2초에 10개 모두 숫자 점수·실행 가능 후보로 선정했습니다. 비밀키와 주문은 사용하지 않았습니다.
- 시작 버튼 1회당 즉시 Binance 사이클 1회와 다음 실행 전 설정 간격 대기를 결정적 worker 회귀로 고정했습니다.
- 상태형 포지션 API 우선, 조회 실패 시 플래그·포지션·모니터 보존, 성공한 빈 스냅샷에서만 오래된 상태 정리를 검증했습니다.
- 같은 LIVE 사이클의 포지션 스냅샷을 좀비 정리와 메모리 동기화가 공유하며, 조회 불확정 사이클은 신규 주문을 보류하도록 수정했습니다.
- 후보 선정·사이클·문서 집중 회귀 `52 passed`, 전체 Python 회귀 `1,893 passed, 8 skipped`를 통과했습니다.
- Web UI TypeScript/Vite production build 49 modules, npm audit 취약점 0, 활성 소스·설정·AI 어시스턴트·Web parity·문서 정합 감사를 통과했습니다.
- 로컬 Web build는 성공했지만 Node `20.11.0`에서 프로젝트 권장 `22.12+` engine 경고가 있었으므로 Windows 릴리스 빌드는 요구 Node 버전으로 수행해야 합니다.
- Windows `NoahAIEngine.exe`, `NoahAI-3.9.1.15-Setup.exe`, blockmap, 새 `latest.yml`, 1.14→1.15 업데이트, Binance 정상/무포지션/장애 복구와 12시간 다중 거래소 E2E는 **PENDING**입니다.
- 배포 상태: `pending_windows_rebuild`, `publish_ready=false`.

## v3.9.1.14 후보 선정 복구·증권 조회 종료 회귀 (2026-08-27)

- 후보 전체 미산출 판정, 거래소별 60초 재시도 쿨다운, 기존 정상 후보 보존, 신한·미래/KIS REST 세션 해제 회귀를 추가했습니다.
- Binance·Upbit·Bithumb·Bybit·Bitget·OKX 30개 후보가 네트워크 없는 스냅샷 점수로 모두 산출되는 매개변수 회귀를 통과했습니다.
- 키움·신한·미래에셋·KIS 조회용 어댑터가 거래 worker 없이도 종료 대상에 포함되는 회귀와 Binance·Bybit 시간 오차 재측정, KIS 토큰 single-flight·60초 쿨다운, LEARNING 명시 시작 계약을 함께 검증했습니다.
- 집중 회귀 `50 passed`, 전체 Python 회귀 `1,883 passed, 8 skipped`, Web UI TypeScript/Vite production build 49 modules, npm audit 취약점 0, 활성 소스 감사와 문서·버전 정합 검사를 통과했습니다.
- 현재 소스 fingerprint는 `9290246ea58d1d79abe8d19a3f90dc55db52c70d9d19399a3d6c2ba65a2f16bd`입니다. Windows 빌드가 생성하는 manifest fingerprint와 일치해야 게시할 수 있습니다.
- Windows `NoahAIEngine.exe`, `NoahAI-3.9.1.14-Setup.exe`, blockmap, `latest.yml`, 1.13→1.14 업데이트, 6개 거래소/4개 증권사 실환경 종료, Binance·Bybit 시간 복구, KIS 실제 토큰 제한, LEARNING 실행 E2E는 **PENDING**입니다.
- 배포 상태: `pending_windows_rebuild`, `publish_ready=false`.

## v3.9.1.13 OKX 안전 종료·가독성·PAPER 안내 회귀 (2026-08-27)

- CCXT 5개 거래소의 12초 요청 경계, 분석 호출 후 중지 소비, API 배지 카드 포함, PAPER 이력 접기/펼치기, 3개 화면 프리셋, 업데이트 외부 알림, LIVE/PAPER 검증 안내 회귀를 추가했습니다.
- 후속 수정 집중 회귀 `41 passed`, 전체 Python 회귀 `1,866 passed, 8 skipped`, Web UI TypeScript/Vite production build 49 modules, Python compile·문서 정합성·Web source parity 감사를 통과했습니다.
- 일괄 ticker 1회, 상세 후보 30개 제한, 8개 제한 병렬, 캔들 60초 재사용, 거래소 single-flight, 120초 stale 차단, 국면 확인·유지시간, 주식 5거래일 국면과 서비스·유니버스 재사용 회귀를 추가했습니다.
- 거래소 미기록 `selected_coins`가 source-strict 조회에서 사라지던 문제, 폴백 10개를 0점으로 오표시하던 문제와 거래소별 최신 세션 혼입 방지 회귀를 추가했습니다.
- 정상 후보 부족은 유효 후보만 `scored_partial`로 유지하고, 점수 없는 심볼에 임의 30·50점을 생성하지 않습니다. 평가 후보가 0개인 `fallback_unscored`는 Binance·통합 Trader 모두 PAPER/LIVE 신규 진입을 차단하고 기존 포지션 보호는 계속합니다.
- Binance 후보는 거래 가능한 USDT 무기한 선물 전체 티커를 거래대금으로 정렬합니다. 결정적 101번째 고거래대금 심볼 회귀와 공통 메이저 분류 회귀를 통과했습니다.
- 2026-08-27 읽기 전용 Binance 공개 API 스모크에서 거래 가능한 USDT 무기한 선물 524개와 24시간 티커 524개를 일치시켰고, 거래대금 상위 5개 모두 1시간봉 50개를 확보했습니다. 주문 제출은 0건입니다.
- v3.9.1.13 Windows 자산은 게시됐습니다. 다만 이번 Binance·OKX 후보 점수와 조회 전용 증권 어댑터 종료 수정은 해당 설치기 이후 소스이므로 v3.9.1.13에 포함됐다고 판정하지 않습니다.
- 기존 v3.9.1.13을 덮어쓰지 않는 후속 버전 Windows Setup·업데이트, 6개 거래소 콜드/웜 선정 p95, 키움 조회 전용 COM 종료, 4개 증권사 조회 후 종료 E2E는 **PENDING**입니다.

## v3.9.1.12 전략 허브·메뉴얼·검증 신뢰 회귀 (2026-08-27)

- AI 커스텀의 무료 전략 허브·회원 제출·전략별 제출 링크와 패키지 내보내기 경계를 소스 계약으로 확인했습니다.
- 제출은 자동 업로드가 아니며 회원 로그인 뒤 파일·공개 설명·시장·위험·권리를 직접 확인하고 비공개 검토로 접수하는 흐름을 문서와 UI에 일치시켰습니다.
- 공개 랭킹은 자기신고 성과가 아니라 서버 검증 여권을 사용하고, 다운로드 전략은 비활성 검토 버전으로 가져와 승인·자동검증·PAPER를 다시 거치는 계약을 검증했습니다.
- 인앱 메뉴얼, Web 메뉴얼 JSON, 사용자 가이드, AI 어시스턴트 지식과 릴리스 문서의 v3.9.1.12 표기를 정합화했습니다.
- 전체 Python 회귀 `1,825 passed, 8 skipped`, React/TypeScript production build 49 modules, 문서 정합 검사를 통과했습니다.
- 사용자 배포판은 v3.9.1.11입니다. Windows Setup·v3.9.1.11→v3.9.1.12 업데이트·전략 내보내기/회원 제출/관리자 승인/다운로드/가져오기·누적 6개 거래소/증권 외부 E2E는 **PENDING**입니다.
- 배포 상태: `pending_windows_rebuild`, `publish_ready=false`.

## v3.9.1.11 안전 종료·PAPER 검증 정합 회귀 (2026-08-26)

- 종료 요청을 비차단 방식으로 전체 거래소에 먼저 전달하고 하나의 45초 예산으로 Binance·통합 worker·모니터 정리를 기다리는 계약을 추가했습니다.
- 거래 사이 3초 대기를 중지 이벤트로 해제하며, 실제 종료 중인 worker를 5초 만에 실패로 확정하지 않는 회귀를 검증했습니다.
- PAPER 구형 TP/SL 백분율 단위 변환과 PAPER/LIVE 유효 범위 차단을 검증했습니다.
- AI 커스텀 PAPER 관찰 일수, 정확한 전략 키·버전의 관찰 시작 이후 청산 합산, 재시작 시 이전 검증 보존을 검증했습니다.
- Binance·통합 5개 거래소 공통 SmartExitPolicy, 종목 표본 부족 시 거래소 보조 표본 축소 적용, AI 커스텀 선언값 불변·RR 미달 진입 차단을 검증했습니다.
- 통합 PAPER 손익 필드·KRW/USDT 분리·구버전 미확정 행 제외와 WebUI 표시 계약을 검증했습니다.
- 전체 Python 회귀 `1,824 passed, 8 skipped`, React/TypeScript production build 49 modules를 통과했습니다. Windows 외부 계정·설치본 검증은 아래와 같이 별도입니다.
- Windows Setup·v3.9.1.10→v3.9.1.11 업데이트·6개 거래소 실제 종료·PAPER 재시작 복구·Upbit PAPER LONG E2E는 **PENDING**입니다.
- 배포 상태: `pending_windows_rebuild`, `publish_ready=false`.

## v3.9.1.10 PAPER 포지션·가상 통계·외부 알림 회귀 (2026-08-25)

- 집중 운용이 stale `max_positions=3`과 거래소 override보다 우선해 1개로 제한되고, 다중/고급 2개 설정이 6개 거래소에 일관되게 저장되는지 검증했습니다.
- Binance PAPER와 통합 거래소 LIVE/PAPER가 같은 제한 함수를 사용하며, 계좌 스냅샷이 실계정 포지션과 런타임 가상 포지션을 분리하는지 확인했습니다.
- PAPER/LEARNING 상한에서 과거 LIVE 수동·외부 포지션을 제외하고, 거래소별 실행 모드와 메모리 전용 가상 포지션이 기존 workspace 폴링으로 전달되는지 확인했습니다.
- 실제 로컬 Web 렌더 중 런타임의 `execution_modes`를 엄격한 Gateway 계약이 추가 필드로 거부해 `/api/v1/runtime/snapshot`이 500이 되는 문제를 재현했습니다. DTO에 거래소별 LEARNING/PAPER/LIVE 계약을 추가하고 Gateway TestClient 회귀로 Web 전달을 고정했습니다.
- PAPER 원장 tail-read, 최근 PAPER 통계 집계, `가상 포지션`·`가상 거래 통계`·스크롤 UI와 적용 중 전략의 PAPER 자동 실행 안내를 검증했습니다.
- 100MiB 초과 합성 PAPER 원장에서 최근 500건 조회를 20회 반복해도 회당 최대 128KiB만 읽고 정확한 최근 범위를 반환하는 결정적 I/O 상한 회귀를 통과했습니다. 이는 24~72시간 실제 6개 거래소 soak를 대체하지 않습니다.
- 일반 안내의 High vol·AI 커스텀·시장·성과 빠른 질문이 서로 다른 정본 근거와 답변으로 분기되고 외부 Provider를 호출하지 않는지 검증했습니다.
- 암호화폐·증권 PAPER 포지션 질문이 stale LIVE 저장소 대신 현재 가상 포지션과 최근 사이클 메트릭을 사용하는지 검증했습니다.
- 질문에 명시한 거래소·증권사 우선 선택과 포지션 없는 추세 질문의 시장 신호 분류를 검증했습니다.
- Windows 빌드·게시가 같은 릴리스 지문 계산기를 사용하고 `trading/trader.py`, 통합 Trader, 공통 포지션 정책, AI 커스텀, Gateway, WebUI와 패키지 매뉴얼 변경을 모두 감지하는 회귀를 추가했습니다. 거래 엔진 파일 한 줄 변경으로 지문이 실제 달라지는 변이 검사도 통과했습니다.
- 장시간 검증 모니터를 Windows/Electron·one-file engine 프로세스 트리 합산, 런타임/workspace/설정/AI 커스텀 P95, 거래소별 실행·PAPER 모드·가상 포지션 상태 확인으로 확장했습니다. 기존 포지션은 강제 청산하지 않는 계약과 새 계정의 엄격한 상한 검사를 별도 옵션으로 분리했습니다.
- 실제 로컬 Gateway와 추가 프로세스 루트 단기 스모크는 런타임 6.08ms, Binance workspace 6.54ms, 설정 6.35ms, AI 커스텀 1.59ms, 합산 RSS 88.20MB로 PASS했고 결과 JSON에 Gateway 토큰이 포함되지 않았습니다. 이는 Windows 6개 거래소 24~72시간 실행 증거를 대체하지 않습니다.
- 압축 부하에서 6개 거래소 workspace 반복 조회가 `trading.db`/WAL/SHM 파일 디스크립터를 누적하는 실제 문제를 발견했습니다. Python `sqlite3.Connection`의 `with`가 연결을 닫지 않는 경로를 Web query와 거래 이력 helper에서 모두 명시적 `closing()`으로 변경했습니다.
- 수정 전 200주기 파일 디스크립터 증가는 `181`, 1차 수정 뒤 `63`, 최종 수정 뒤 `0`이었습니다. 최종 720주기·5,328 HTTP 요청은 실패 0, RSS 증가 5.51MB, 스레드·디스크립터 증가 0, 런타임 P95 1.71ms, workspace 최대 6.20ms, 설정 6.41ms, AI 커스텀 1.77ms였습니다. 압축 반복은 실제 Windows 24~72시간 경과 검증을 대체하지 않습니다.
- 외부 알림은 Discord/Telegram 연결 저장·상태·테스트·대화방 자동 찾기, 공식 HTTPS 대상 제한, write-only 비밀값, 제한 큐·timeout·재시도·cooldown·계정 전환 격리와 가드레일/손실/시장국면/런타임/수동 리포트 이벤트 연결을 자동 회귀로 확인했습니다.
- 로컬 실제 Web 설정 모달에서 `알림·리포트` 9번째 탭과 Discord/Telegram 단계형 연결 UI를 확인했고, 1440px에서는 2열, 900px에서는 1열로 배치되며 내부 가로 넘침이 없음을 확인했습니다. 실제 외부 계정 발송은 수행하지 않았습니다.
- 2026-08-25 재검증에서 전체 Python 회귀 `1,804 passed, 8 skipped`, React/TypeScript production build 49 modules, 문서·Web parity·설정/어시스턴트 계약 감사를 통과했습니다.
- 활성 V1 PAPER 귀속 회귀를 추가해 가상 진입 포지션의 전략 이름·키·버전 `v1` 보존과 TP/SL 가상 청산 원장의 동일 버전 기록을 확인했습니다. 전역 PAPER 실행 풀은 적용 중 V1과 `paper_validation` 후보를 함께 전달하지만 상태를 구분합니다.
- 로컬 실제 Web fixture에서 Binance PAPER의 가상 포지션 6개와 PAPER 이력 6건이 카드 내부에서 스크롤되고, `가상 거래 통계`만 자동 표시되며 실거래 통계가 숨겨지는 것을 확인했습니다. 활성 `추세 따라가기 V1`은 `앱 PAPER에서는 가상 실행`·`적용 해제`를 표시하고 중복 `PAPER 전진검증 시작`은 표시하지 않았습니다. 이 6개 fixture는 스크롤 렌더 검증용 합성값이며 실제 포지션 상한 증거는 아닙니다.
- 별도 Binance PAPER 거래소 화면 렌더에서 `AI 커스텀 적용: 추세 따라가기 V1`, `적용 중 버전은 PAPER에서 자동 실행 · 재적용 불필요`, `PAPER · 3개 활성 / 다중 상한 3`, `가상 거래 통계`, `종료 이력 2건 · 활성 수와 무관`을 한 화면 계약으로 확인했습니다. 후보 V2는 적용 버전과 섞지 않고 `전진검증 후보 1개 별도`로 표시했습니다. 이는 UI·Gateway 전달 증거이며 실제 거래소 주문·상한 집행 E2E는 아닙니다.
- 별도 초과 fixture에서 `PAPER · 6개 활성 / 상한 3 · 신규 진입 차단`, `종료 이력 6건 · 활성 수와 무관`과 두 카드의 실제 내부 스크롤을 확인했습니다. 새 계좌·네트워크 폴링은 추가하지 않았고 기존 workspace 응답의 설정 상한만 함께 표시합니다.
- 제품 버전 `3.9.1.10`, updater SemVer `3.9.110`; Windows Setup·v3.9.1.9→v3.9.1.10 업데이트·6개 거래소 장시간 PAPER 실화면·실제 Discord/Telegram 발송과 비밀값 비노출 검증은 **PENDING**입니다.
- 배포 상태: `pending_windows_rebuild`, `publish_ready=false`.

## v3.9.1.9 PAPER 전진검증·근거형 AI 어시스턴트 회귀 (2026-08-24)

- 사용자 승인 뒤 과거 구간 유무와 무관한 PAPER 전용 풀 시작/중지 → 진행 중 조건 미달 비실패 → 버전 귀속 가상 청산 자동 집계 계약을 회귀 검증합니다.
- 전략 키가 없는 기본 PAPER 청산도 사용자 이력에 보존하되 AI 커스텀 버전 성과에는 잘못 합산하지 않습니다.
- 일반 안내의 포지션 질문과 심층분석 컨텍스트가 런타임 관리 포지션·TP/SL·전략 버전·최근 신호를 사용하는지 검증합니다.
- 전체 Python 회귀 `1,751 passed, 8 skipped`, React/TypeScript production build 49 modules, npm audit 취약점 0, 문서·버전·활성 소스·Web parity 계약 감사를 통과했습니다.
- 제품 버전 `3.9.1.9`, updater SemVer `3.9.109`; Windows Setup·업데이트·키움/KIS 실계정·7일 PAPER·실제 Provider 검증은 **PENDING**입니다.
- 배포 상태: `pending_windows_rebuild`, `publish_ready=false`.

## v3.9.1.8 체결 원장 정합·증권 API 안정화 회귀 (2026-08-24)

- 집중 소스 회귀: 현물/선물 기능 계약, Bithumb DB/설정 종목 재주입과 20종목 고정 절단 제거, KIS ETF 공식 현재가 경로와 설정 감시목록, 키움 Web 프로세스 프록시의 소유 자식 정리를 검증했습니다. 제한/증분 체결 조회는 계정 전체 이력으로 표시하지 않고 저장 범위로 표시합니다.
- 종료 회귀는 실행 플래그가 이미 꺼졌어도 실제 스레드가 살아 있으면 다음 종료 시도에서 다시 발견하며, CCXT·증권 worker를 선신호/공통 제한시간으로 정리하고 잔존 worker·키움 자식 프로세스가 있으면 안전 종료 성공으로 처리하지 않음을 검증했습니다.
- React/TypeScript production build 49 modules를 확인했습니다.
- 전체 Python 회귀 `1,744 passed, 8 skipped`, 문서/버전 정합성 PASS를 확인했습니다. Windows Setup/업데이트·6개 거래소 안전 종료, 실제 키움 OpenAPI+ COM, KIS·Bithumb·Upbit 외부 계정, 다중 거래소 PAPER는 최종 게이트 결과를 별도 기록합니다.
- 배포 상태: `pending_windows_rebuild`, `publish_ready=false`.

## v3.9.1.7 장시간 성능·요청 격리 회귀 (2026-08-23)

- 소스 상태: 전체 Python 회귀 `1,722 passed, 8 skipped`, 문서/버전 정합성 PASS
- 확인 결과: 완료 후 다음 폴링, 계좌/멤버십 single-flight, 설정·AI 커스텀 잠금 비차단, 200건 초과 KPI 전체 집계, 3,002행 로그 tail을 자동 회귀로 확인
- Teayu 지원 DB 실측: 메인 운영 workspace P95 `63.0ms`, Binance 상세 통계 P95 `129.9ms` (각 목표 150ms/300ms 이하)
- 외부 게이트: Windows 설치본, v3.9.1.6→v3.9.1.7 업데이트, 6개 거래소 24시간 PAPER soak는 미완료
- 배포 상태: `pending_windows_rebuild`, `publish_ready=false`

## v3.9.1.6 학습 데이터·거래소 로그·런타임 안정화 회귀 (2026-08-23)

- AI 학습은 최근 50개부터 표시하고 더보기마다 50개를 추가합니다. 100MB 이상 운영 파일도 최근 레코드 tail과 별도 전체 계수 캐시를 사용해 초기 화면에서 전체 JSON을 매번 역직렬화하지 않습니다.
- Web sidecar 로그인 후 계정별 `trading.log`와 `trading_<source>.log` sink를 원본과 동일하게 재구성하고, 거래소 탭은 현재 계정 세션의 메모리 스트림과 영속 파일을 병합해 1초마다 갱신합니다. 이전 계정의 메모리 로그는 세션 경계 이전 이벤트로 차단합니다.
- 잔고 조회와 거래 시작의 UI 잠금을 분리하고, 서버의 전역 런타임 명령 잠금을 짧은 멱등성·감사 구간으로 축소해 서로 다른 거래소 시작이 병렬 진행됩니다. 개별 시작/정지 외에 설정·자격증명 준비 대상을 동시에 시작하거나 실행 중 대상을 모두 정지하는 명시 확인 UI를 추가했습니다.
- 최상위 런타임 상태를 2초마다 재조회하며, 플래그만 남고 실제 스레드가 종료된 거래소는 실행 중으로 집계하지 않습니다. 메인 KPI의 자동 거래 상태와 실시간 운영 알림은 같은 실제 워커 목록을 사용합니다.
- 메인 최근 100줄·거래소별 최근 200줄 tail, 구조화된 거래소·레벨·카테고리 필터, 상세 로그 설정의 Trader·통합 Trader·Analyzer·connector 반영을 자동 회귀로 확인합니다.
- 전체 Python 회귀 `1,716 passed, 8 skipped`, React production build 48 modules, npm audit 취약점 0, 활성 Python 389개, 문서/버전·Web engine spec 감사 **PASS**. 경고 1건은 FastAPI TestClient의 향후 `httpx2` 전환 안내이며 제품 실패가 아닙니다.
- 현재 결과는 소스 후보입니다. 새 Windows Setup/업데이트, 사용자 제공 설치 환경의 6개 거래소 동시 PAPER 시작·정지·로그·KPI, 실제 외부 계정과 장시간 운전은 **PENDING**입니다.
- manifest는 `3.9.1.6`, `pending_windows_rebuild`, `publish_ready=false`이며 설치기·engine·latest.yml·blockmap SHA는 비어 있습니다.

## v3.9.1.5 거래소 API cp949·자격증명 검증 회귀 (2026-08-22)

- 제보된 `'cp949' codec can't encode character '\U0001f527'`는 거래소 응답이 아니라 headless runtime 구성 중 설정 마이그레이션 상태 출력에서 발생하며, 외부 API 호출 전 로컬 예외임을 확인했다.
- Windows sidecar UTF-8 환경·launcher 스트림 재설정·설정 진단 출력 비차단·`local_runtime_encoding_error` 분류를 추가했다.
- UTF-8 BOM·UTF-16·CP949 설정의 값/자격증명 보존과 UTF-8 정규화, 손상 설정 덮어쓰기 차단, 잘못된 백업 복구 거부, 한글 사용자 경로 저장을 자동 회귀로 확인했다.
- 저장소의 `data` 아래 설정·백업 38개를 비밀값 출력 없이 검사했으며 모두 BOM 없는 UTF-8 객체 JSON이고 해독 불가 파일은 0개였다. Teayu 설정과 백업 3개도 이 정상 UTF-8 집합에 포함된다.
- Binance·Upbit·Bithumb·Bybit·OKX·Bitget 자격증명 저장 → fresh disk reread → runtime refresh → account snapshot 라우팅과 `status=success` 단독 성공 판정 집중 회귀 **PASS**.
- 집중 회귀 `209 passed`, 전체 Python 회귀 `1,702 passed, 8 skipped`, React production build 47 modules, npm audit 취약점 0, 활성 Python 388개, 문서/버전·Web engine spec 감사 **PASS**. 경고 1건은 FastAPI TestClient의 향후 `httpx2` 전환 안내이며 제품 실패가 아니다.
- Windows 새 Setup, v3.9.1.4→v3.9.1.5 자동업데이트, cp949 실환경 재현, 실제 6개 거래소 외부 계정 조회는 **PENDING**이다.
- manifest는 `3.9.1.5`, `pending_windows_rebuild`, `publish_ready=false`이며 설치기·engine·latest.yml·blockmap SHA는 비어 있다.

## v3.9.1.4 Windows 설정 잠금·업데이터 표시 회귀 (2026-08-22)

- 공개 v3.9.1.3 설치본에서도 설정 저장 실패가 재현됐다는 사용자 제보를 반영해 v3.9.1.3의 해결 완료 판정을 철회하고 새 updater SemVer `3.9.104` 후보로 분리했다.
- 계정별 프로세스 간 설정 잠금의 실제 다중 프로세스 대기, Windows 공유 위반 분류, 원자 교체 실패의 기존 정본 보존, 저장 실패 `code/stage/winerror` 영수증을 자동 회귀로 검증했다. Windows `os.replace()`에만 필요한 삭제 공유가 차단된 경우 원본의 제자리 쓰기 형태로 폴백하고 완전한 임시 JSON과 기록 바이트를 재검증하는 회귀도 통과했다.
- Electron 단일 인스턴스 비소유 프로세스의 sidecar startup 차단과 `latest.yml 3.9.104 + stale releaseName 3.9.0.10 → 표시 3.9.1.4` 순수 함수 회귀를 추가했다.
- Teayu 원본은 수정하지 않고 임시 복제본으로 ApplicationServices 저장 → 2.2초 대기 → 재조회했으며 검증 영수증, 값 유지, 런타임 갱신이 모두 **PASS**였다.
- 설정 정본 감사: 117개 최상위/646개 leaf, 직접 편집 132, 전문가 JSON 261, 전용 관리 171, 보호 82, 미분류 0, Web 활성 runtime 전체 writer 0, 명시 복구 호출 1 **PASS**.
- 전체 Python 회귀 `1,686 passed, 8 skipped`, React production build 47 modules, npm audit 취약점 0, 활성 Python 387개, 문서/버전·Web engine spec 감사 **PASS**.
- 인앱 Browser 연결이 없어 설정 하단 실제 렌더는 검증하지 못했다. Windows 100%·125%·150% DPI, 새 Setup, v3.9.1.3→v3.9.1.4 자동업데이트, 실제 사용자 저장→재시작은 **PENDING**이다.
- manifest는 `3.9.1.4`, `pending_windows_rebuild`, `publish_ready=false`, 설치기·engine·latest.yml·blockmap SHA는 비어 있다.

## v3.9.1.3 설정 저장 재검증 회귀 (2026-08-21)

- 2026-08-22 설정·AI 어시스턴트 전수 감사: 정본 117개 최상위/646개 leaf, 직접 편집 132, 전문가 JSON 261, 전용 관리 171, 보호 82, 미분류 0, Web 활성 runtime 전체 writer 0, 명시 복구 호출 1 **PASS**.
- 원본 사용자 설정 55개와 8개 탭, 잘못된 Web enum 마이그레이션, 탭별·전체 기본값 staging, AI 최근 문맥·저장 비용 프리셋, AI 커스텀 Level 3 프로필 게이트 집중 회귀 `196 passed` **PASS**.
- 전체 Python 회귀 `1,677 passed, 8 skipped`, React production build 47 modules, npm audit 0, 활성 소스 386개, 문서/버전·설정 정본·전체 서비스·sidecar 레거시 UI 0개 감사 **PASS**.
- Teayu 원본 설정은 읽기 전용 계약 감사에서 스키마 `3.9.0.5`, LEARNING, 모순 0건이며 원본 파일을 수정하지 않았다.
- 공개 v3.9.1.2 실사용 화면에서 `저장 중…` 직후 원복과 API 연결확인 실패가 재현됐다는 제보를 반영했다.
- 설정 경로 병합 후 fresh read 값 검증과 Web 검증 영수증을 추가하고, Evaluator의 settings.json 직접 쓰기·내부 `.backup` 자동 복구를 제거했다.
- 입력 중인 API 자격증명을 저장·검증한 뒤 연결 점검하고 Provider 전환 시 이전 모델을 교차 적용하지 않으며, Windows 잔류 sidecar를 시작 전에 정리한다.
- 기존 공통 AI 키와 빈 Provider별 템플릿의 호환 판별, Provider 간 키 비차용, Provider별 등록 상태, 키/SDK 준비 실패의 네트워크 미실행 표시와 Windows sidecar의 AI SDK 필수 모듈 감사를 추가했다.
- AI/설정 집중 회귀 `179 passed`, 전체 Python 회귀 `1,672 passed, 8 skipped`, React production build 47 modules, 활성 소스 384개·문서/버전·설정 계약·Web sidecar AI 모듈 감사·npm audit 0 vulnerabilities **PASS**.
- Windows v3.9.1.3 Setup 생성, v3.9.1.2→v3.9.1.3 업데이트, 실제 사용자 계정의 저장→닫기→재시작 값 유지와 API 연결확인은 아직 **PENDING**이다.
- manifest는 `3.9.1.3`, `pending_windows_rebuild`, `publish_ready=false`다.

## v3.9.1.2 Teayu 설정 저장·런타임 정본 회귀 (2026-08-21)

- 지원 폴더 `data/260821_Teayu`는 원본을 수정하지 않고 점검했다. `config/settings.json`과 3개 백업의 연속 기록에서 설정 변경 뒤 일부 값이 다시 이전 값으로 기록된 정황을 확인했다. 첨부 화면은 제목 표시 기준 v3.9.1.0이며 상태 503을 표시한다.
- 디스크 저장 완료 뒤 런타임 갱신 예외를 저장 실패 503으로 바꾸지 않는 계약, Headless runtime의 장기 설정 보유 객체 동기화, 백그라운드 임계값의 경로 단위 병합 저장과 사용자 설정 구조 메모리 복사 회귀를 추가했다. 자격증명 값은 출력하지 않았다.
- Web AI 어시스턴트의 차트분석 버튼이 자산정보 화면으로만 이동하던 누락을 수정하고 이미지 업로드·OCR·명시적 비전 호출·비용/예산·근거/위험/참고 플랜·주문 0건·임시 파일 삭제 계약을 추가했다.
- 전체 Python 회귀 `1,665 passed, 8 skipped`, React production build 47 modules, 활성 소스 감사 384개와 설정 계약 감사 **PASS**.
- 소스 수정은 완료했지만 Windows v3.9.1.2 Setup·blockmap·`latest.yml`은 아직 생성·검증되지 않았다. manifest는 `pending_windows_rebuild`, `publish_ready=false`이며 실제 설치본의 저장→닫기→재시작→값 유지 확인 전 배포 완료가 아니다.

## v3.9.1.0 Windows 최종 로컬 후보 재빌드 (2026-08-20)

- 옵션 없는 공식 전체 빌드 `scripts/build_web_ui_windows.ps1` **PASS**. Web 집중 회귀 `120 passed`, 전체 Python 회귀 `1,652 passed, 8 skipped`, 활성 소스 381개, 문서/버전, engine TOC와 packaged desktop bootstrap API smoke를 통과했다.
- React production build 47 modules, CSS `117.33 kB`(gzip `22.01 kB`), JS `482.90 kB`(gzip `142.03 kB`), npm audit 취약점 0 **PASS**.
- 설치기: `deploy/web-release/NoahAI-3.9.1.0-Setup.exe`, 412,711,100 bytes, SHA-256 `0354c712e7d5be7bf7ef87e0d9901cb9a8f301267d82cb24a31190d6096abc5e`.
- engine: `deploy/web-engine/NoahAIEngine.exe`, 314,794,502 bytes, SHA-256 `facd11ab897bcf9f73e3519a39fc6dee20158497f22f91536ba65b0a2f744f7e`.
- 기존 설치본은 `config/web_ui_feature_inventory.json` 누락으로 `/api/v1/features`가 500을 반환했다. 수정본은 격리 설치 exit 0, 내장 engine SHA 일치, `/api/v1/health`, `/platform`, `/session`, `/features`, `/runtime/snapshot`과 `noahai://app` CORS 응답 **PASS**.
- 설치기 Authenticode는 `NotSigned`다. 자동업데이트·이전 Electron bundle 롤백·유효 자격증명 10개 기관 E2E·다중 모니터·24~72시간 PAPER는 실행 원장에서 완료되지 않았다.
- 사용자 설치본 확인 후 `v3.9.1.0` 정식 GitHub Release를 공개했다. Setup, `latest.yml`, blockmap, manifest 4개 자산의 원격 크기와 SHA-256 digest 일치를 재검증했다.

## v3.9.1.0 Windows 최종 소스 재빌드 후보 (2026-08-19)

- 공식 전체 빌드 `scripts/build_web_ui_windows.ps1` **PASS**. 집중 회귀 `101 passed`, 전체 Python 회귀 `1,620 passed, 8 skipped`, 활성 소스 379개·문서/버전·완성 engine TOC 감사와 packaged health smoke를 통과했다.
- React production build 46 modules, CSS `64.35 kB`(gzip `13.11 kB`), JS `380.97 kB`(gzip `113.37 kB), npm audit 취약점 0 **PASS**.
- 설치기: `deploy/web-release/NoahAI-3.9.1.0-Setup.exe`, 412,632,744 bytes, SHA-256 `af1f35e123901166f66d37a24dfb64953b5eec4efcbfe479d66f6ad568a82446`.
- engine: `deploy/web-engine/NoahAIEngine.exe`, 314,745,599 bytes, SHA-256 `59269707a1e01f7609800e0b1ef11f0216a56d019b653912542c214293838c44`.
- 격리 설치 exit 0, 설치본 `NoahAI.exe` 3.9.1.0과 내장 engine SHA 일치, `noahai://app/index.html` 로그인 페이지와 Electron/engine 프로세스 정상 응답, silent 제거 exit 0 및 설치 디렉터리 제거 **PASS**.
- Authenticode는 설치기와 engine 모두 `NotSigned`다. 인앱 Browser runtime이 제공되지 않아 자동 클릭·화면 캡처는 수행하지 못했고, 자동업데이트·이전 Electron bundle 롤백·실계정·다중 모니터·24~72시간 PAPER는 **PENDING**이다.
- manifest 상태는 `built_windows_unverified`, `publish_ready=false`다. 실행 원장의 OPEN 항목과 외부 게이트가 남아 있으므로 이 후보 생성은 공개 배포 승인이 아니다.

## v3.9.1.0 Web UI 1:1 전환 현재 검증 (2026-08-16)

- 정본: [Web UI 1:1 전환 실행 원장](WEB_UI_1_TO_1_PARITY_EXECUTION_PLAN_v3.9.1.0.md). 소스·테스트·빌드 성공과 화면/동작/Windows 완료를 분리한다.
- 데이터·자격증명·서비스 문맥·라우팅·설정·매뉴얼 집중 회귀: `147 passed, 1 warning` **PASS**.
- 전체 Python 회귀: `1,620 passed, 8 skipped, 0 failed`, 경고 1건 **PASS**. 경고는 FastAPI TestClient의 `httpx2` 전환 deprecation이며 제품 실패가 아니다.
- React production build: `46 modules`, CSS `64.35 kB`(gzip `13.11 kB`), JS `380.97 kB`(gzip `113.37 kB`) **PASS**.
- npm audit: 취약점 `0` **PASS**.
- Web 고급 기능·문서 동기화를 포함한 확대 집중 회귀: `92 passed, 1 warning` **PASS**.
- 5개 서비스 전체 소스 계약 감사: 서비스 5개, 상위 기능 35개, 거래소·증권사 10개, 생활금융 내부 7개, 설정 8개, 매뉴얼 11개, AI애널리스트 카드 6개 **PASS**. 이 감사는 시각 1:1이나 Windows E2E를 의미하지 않는다.
- 활성 소스 감사: Python `379`개 파일, 구문 실패·금지 활성 소스·증권사 계약 오류 `0` **PASS**.
- Web engine spec 감사: `main`, `ui.*`, `tkinter`, `customtkinter` 포함 `0` **PASS**. 완성 Windows EXE TOC 검증은 별도다.
- 문서/버전 정합성: 현재의 `1:1 전환 진행 중 · 배포 불가` 판정 기준 **PASS**.
- 현재 검증된 핵심 계약: 서비스·source별 로그/통계 실패 폐쇄, 미설정·마스킹·부분 자격증명의 런타임/잔고 조회 0회, 35개 기능 ID의 정본 라우팅, 서비스와 다른 기능 ID 요청 거부, 자산 통합·생활금융·AI애널리스트의 AI 질문 문맥 분리, 생활금융의 전용 저장소 사용, AI애널리스트의 암호화폐·주식 전체 자산 집계, 서버 소유 설정 영역, 레거시 매뉴얼 11개 탭 원문 계약.
- 미검증: 로그인부터 모든 서비스·하위 탭·거래소/증권사·설정·매뉴얼의 동일 조건 나란히 렌더, 기존 사용자 데이터 업그레이드, Windows Setup/자동업데이트/롤백, 실제 계정 및 24~72시간 PAPER. 따라서 **전체 1:1 완료 및 배포 가능 판정은 아니다.**

## v3.9.1.0 Web UI 기존 화면 동등성 재검증 (과거 기록 · 2026-08-15)

- 공유된 CTk/WebUI 좌우 화면을 정본으로 재감사해 실시간 로그의 임의 XAI 중복 탭 제거, 주식 AI 4개 독립 탭 복원, 시장 트렌드 5개 영역 복원, 최신 로그 시간 정렬을 소스에 반영했다. 저장된 로컬 로그인 정보로 실제 Electron 대시보드까지 열어 기본 로그·BINANCE·주식/증권 화면을 확인했지만 전체 탭/설정/매뉴얼의 나란히 대조는 남아 있다. **SOURCE + AUTHENTICATED MAC SUBSET PASS / FULL LEGACY COMPARE OPEN**
- 현재 Windows Setup 후보는 위 소스보다 오래되고 source fingerprint가 없어 게시 스크립트가 차단한다. manifest는 `pending_windows_rebuild`, `publish_ready=false`다. **STALE CANDIDATE BLOCKED / WINDOWS REBUILD PENDING**
- 오후 기능 재감사에서 블록체인/증권 전역 선택 source, 공통 로그와 `selected_coins` 재사용을 분리했다. 증권 화면은 증권 source·로그만 사용하고 증권 후보 저장소가 없으면 암호화폐 후보를 재표시하지 않는다. **SOURCE + FOCUSED PASS / REAL BROKER E2E PENDING**
- AI 어시스턴트 FAQ를 블록체인/증권/애널리스트별로 분리하고, 초보자·일반·고급은 설명 밀도만 바꾸며 `일반 안내`는 외부 호출 0, `외부 AI 심층분석`은 명시 호출·예산 표시로 구분했다. **SOURCE + FOCUSED PASS / PROVIDER FLOW PENDING**
- 앱 내부 매뉴얼의 축약 사본을 제거하고 레거시 `show_manual()`이 실제 여는 11개 탭과 본문 전체를 빌드 시 JSON으로 추출해 Gateway·Web client·PyInstaller data 계약으로 연결했다. **EXACT SOURCE CONTRACT / RENDER·FLOW COMPARE OPEN**
- 메뉴얼 정본·Web 플랫폼·고급 기능·동등성 집중 회귀 `61 passed`, React production build `43 modules`, CSS `50.90 kB`(gzip `10.68 kB`), JS `329.07 kB`(gzip `98.09 kB`) **PASS**. 저장소 전체 `1,536 passed, 8 skipped`, npm audit 취약점 `0`, 활성 소스 375개와 Web engine 레거시 UI 모듈 0 감사는 직전 전체 기준선이며 이번 메뉴얼 계약 변경 뒤 전체 회귀/감사는 별도 재실행 대상이다.
- macOS Electron 개발 실행은 `ELECTRON_RUN_AS_NODE` 환경을 제거한 실제 Electron 런타임에서 450×708 로그인 창과 저장된 로컬 로그인 정보로 1500×980 대시보드를 열었다. LIVE 명령은 실행하지 않았다. 기본 실시간 로그는 2026-08-15 최신 행까지, BINANCE 전용 로그도 최신 행까지 자동 이동하며, 주식/증권은 AI 4개 독립 탭과 증권 전용 로그를 사용하는 것을 확인했다. 실제 계좌 잔고·주문·Provider 호출 E2E는 **PENDING**이다.

- 2026-08-15 정오 사용자 캡처 재감사에서 Electron 기본 아이콘, 로그인 여백, 로그 전체 문서 확장, 코인 정보/BINANCE 동시 선택, 공용 차트·원시 DB 화면 대체, AI 어시스턴트·AI 커스텀 흐름 차이를 확인했다. 이전 화면 완료 주장을 철회하고 `legacy_visual_parity`/`legacy_flow_parity` 미완료로 고정했다.
- 제품 아이콘을 Electron 창·macOS Dock·Windows/macOS 패키지 계약에 연결하고, 로그인 카드 위치를 실제 레거시 450×708 창과 나란히 맞췄다. 로그인 도움말은 별도 창·3탭·조정된 글자 크기로 macOS에서 다시 열어 확인했다. **LOGIN MAC RENDER + LEGACY COMPARE PASS / PACKAGED ICON PENDING**
- 로그인 정보 저장은 Electron OS 암호화 저장소와 권한 제한 파일을 사용하며 renderer/localStorage에 비밀번호를 남기지 않는다. 저장소 실패는 성공한 계정 로그인을 실패로 되돌리지 않는다. **SOURCE + FOCUSED PASS / PACKAGED KEYCHAIN E2E PENDING**
- 실시간 로그는 고정 앱 viewport와 내부 스크롤을 사용한다. 잘못 추가된 XAI 중복 보기는 제거하고 기능 탭과 거래소/증권사 source 탭 활성 상태를 분리했으며 코인·종목 정보 및 거래소·증권사 전용 워크스페이스를 복원했다. 기본 로그와 거래소 전용 로그 모두 최신 행으로 자동 이동하는 실제 로그인 렌더를 확인했다. **SOURCE + AUTHENTICATED MAC SUBSET PASS / FULL LEGACY COMPARE OPEN**
- AI 어시스턴트는 대화·FAQ·복사/TXT·입력·음성·설정·차트분석 구조, AI 커스텀은 철학·처음 사용법·멘토·설정·안전 흐름을 복원했다. 실제 음성 입력, 멘토 인터뷰, 심층분석, 설정 영향·매뉴얼 본문까지는 기존 흐름 전수 대조가 남아 있다. **SOURCE PARTIAL / FLOW PENDING**
- 최신 React production build `49 modules`, CSS `45.89 kB`(gzip `9.82 kB`), JS `501.02 kB`(gzip `154.95 kB`) **PASS**. 500 kB 청크 경고는 남아 있으며 기능 오류는 아니지만 배포 전 code splitting 검토 대상이다. npm audit 취약점 `0` **PASS**.
- 이전의 “기존 기능 Web 소스 이전 완료”는 API/컴포넌트 연결 판정이었으며 화면·동작 동등성 완료 판정이 아니었다. `legacy_visual_parity`와 `legacy_flow_parity`가 없었던 완료 표현을 철회한다.
- 로그인 450×708, 실제 로고, 로그인 전 별도 도움말 3탭을 macOS Electron에서 직접 열어 기존 화면과 대조했다. 로그인 뒤 기본 로그·BINANCE source·주식/증권 내비게이션을 실제 렌더로 재검증했다. **LOGIN + AUTHENTICATED MAC SUBSET PASS / FULL TAB PARITY OPEN / WINDOWS PENDING**
- 설정은 세로형 외형과 8개 기능 영역, 영역별 AI 질문, write-only 거래소·증권·AI 연결, 변경분 저장 소스가 있다. 매뉴얼은 레거시 실제 11개 탭의 상세 본문을 자동 추출해 동일 콘텐츠를 사용하지만 렌더·검색·딥링크 흐름 대조는 남아 있다. **CONTENT CONTRACT PASS / LEGACY RENDER·FLOW OPEN**
- 거래소 상단 표기는 암호화폐 6개만 집계하고 증권 4개를 분리했다. 비활성 AlphaArena와 내부 통합 source 메뉴는 사용자 탭에서 숨겼다. **SOURCE PASS / FINAL RENDER RECHECK**
- 하단 AI 실행 기록은 고정 문구가 아니라 계정 감사 원장의 최근 assistant/strategy/AlphaArena 이벤트를 사용한다. 종료 버튼은 Electron safe-shutdown IPC에 연결했다. **SOURCE + FOCUSED TEST PASS / WINDOWS E2E PENDING**
- 이전 React production build `48 modules`, CSS `36.26 kB`, JS `485.57 kB`와 Web UI 동등성/platform 집중 회귀 `41 passed`는 과거 기준선이며, 현재 재작업 빌드 수치는 위 최신 항목을 따른다.
- 현재 선택한 Web UI 플랫폼/고급 기능/동등성 집중 회귀 `61 passed` **PASS**. 경고 1건은 FastAPI TestClient의 `httpx2` 전환 deprecation이며 제품 실패가 아니다. 저장소 전체 회귀 `1,536 passed, 8 skipped, 0 failed`는 직전 전체 기준선이다.
- 활성 소스 감사 `433`개 Python 파일, 구문 실패·금지 활성 소스 0 **PASS**. Web engine spec의 레거시 desktop UI 모듈 0 **PASS**. npm audit 취약점 0 **PASS**. 문서/버전 정합성 **PASS**.
- 세부 증거: `docs/WEB_UI_LEGACY_PARITY_MATRIX_v3.9.1.0.md`. 전체 기능 탭과 Windows E2E 전에는 **배포 불가**다.

## v3.9.1.0 Web UI Internal Integration Candidate 검증 (2026-08-14)

- 2026-08-15 패키지 재검증: 최초 후보의 engine 상대 import 실패를 수정하고 빌드 단계 packaged health smoke를 추가했다. 교체 후보는 격리 설치·덮어쓰기 업그레이드·설치 파일 계약·engine SHA·Electron page load·Gateway health·사용자 데이터 보존을 통과했다. silent uninstaller는 exit 0 뒤 파일이 남아 **FAIL**, 자동업데이트·이전 Electron bundle 롤백·실계정·다중 모니터·24~72시간 PAPER는 **PENDING**이다.
- 2026-08-14 당시 소스 연결 판정: **UI-neutral 런타임·패키징 구조와 기존 기능 Web 컴포넌트 연결, Windows/실계정 외부 E2E 진행 전**이었다. 이 기록은 화면·동작 동등성 완료를 뜻하지 않으며 현재 판정은 문서 맨 위 재검증 항목을 따른다. `config/web_ui_feature_inventory.json` 40개 중 `source_complete` 34, `source_complete_external_e2e` 4, `integrated_in_ai_custom` 1, `server_later` 1이며 `read_first`는 0개였다.
- 런타임 경계: `runtime_bridge.py`는 `main.NoahAIClient`를 더 이상 사용하지 않고 `HeadlessTradingRuntime`을 지연 생성하며, shutdown은 신규 명령 차단→crypto/stock worker 정지→signal/optimizer 정지→Recorder/log flush→완료 응답 순서로 실패 폐쇄한다. **FOCUSED SOURCE PASS / EXTERNAL E2E PENDING**
- Web sidecar: 독립 `noahai_web_engine.spec`과 `verify_web_engine_bundle.py`가 `main`, `ui.*`, `tkinter`, `customtkinter`, 레거시 updater를 금지한다. 실제 Windows `Analysis-00.toc`에서 레거시 UI 모듈 0개를 확인했다. **SPEC PASS / WINDOWS TOC PASS**
- 설치 계약: `NoahAI-3.9.1.0-Setup.exe` → 사용자 실행 `NoahAI.exe` → 내부 `resources/engine/NoahAIEngine.exe`. 설치기 SHA-256 `a0ecd5bee659cc7bf84bab849493046f8bd870fba09a803cf9c8518d17c0c4bb`, engine SHA-256 `933905e7fddbae4897091cb4e14c5b080fd70554f4f52ac3ba2f7d2d2ff1673c`; Authenticode는 미서명이다. **BUILT / LOCAL INSTALL-RUN-UPGRADE PASS / EXTERNAL GATES PENDING**
- 계정 정본 Application Services: 템플릿 설정·증권사 안전 필드, revision/diff, write-only 거래소·증권·AI 자격증명, 실시간 계좌 snapshot, AI 커스텀, 생활금융·마스킹 로그 **SOURCE PASS**
- Gateway: Bearer+Origin+명시 intent, stale revision `409`, 엔진 미연결 명령·증권 차트 fail-closed, 엄격 DTO **FOCUSED PASS**
- AI 커스텀: 다중 원본 추출, 제한 IR/XAI, 상태머신·삭제·diff/rollback, `.noahstrategy`, 자동 과거재생, 암호화폐·주식 PAPER 전략 버전 귀속 **FOCUSED PASS**
- AI 가이드/분석: 로컬 무과금 제품 가이드와 명시 외부 Provider 분석을 분리하고 일/월 예산·캐시·토큰/비용 상태 확인 **FOCUSED PASS**
- 고급 12개 Web 기능: 금융 인텔리전스, AlphaArena, 자산 인사이트·배분·리스크·성과, 생활금융 분석·상품·세금, AI 요약/허브를 전용 Application Service·엄격 DTO·Gateway·React 화면으로 이전 **SOURCE PASS / EXTERNAL DATA E2E PENDING**
- AlphaArena: PAPER 판단은 위험 게이트를 적용하되 거래소 주문 호출 0, `order_submitted=false`; LIVE는 `alpha_arena_live_blocked_pending_external_gate`로 실패 폐쇄 **FOCUSED PASS / PACKAGED PAPER PENDING**
- 차트: 6개 암호화폐 venue parser와 4개 증권사 일봉 계약, 진입·청산·XAI marker, 오류 재시도 **FOCUSED PASS**
- Electron/업데이터: 임의 loopback port, 실행별 token, `--gateway-only` sidecar, 단일 인스턴스, 명시 다운로드, 안전 종료 handshake 성공 후에만 설치·재시작, NSIS 빌드 체인 **SOURCE PASS / PACKAGED E2E PENDING**
- 고급 기능·동기화 충돌 집중 회귀: `8 passed`; 전체 Web/빌드 회귀는 전체 Python 회귀에 포함, TestClient deprecation 경고 1건 **PASS**
- 최신 Web production build: 48 modules, JS 458.95 kB(gzip 141.96 kB), CSS 20.49 kB(gzip 5.29 kB), npm audit `0 vulnerabilities` **PASS**
- Web 배포 계약: NSIS installer·`latest.yml`·blockmap·embedded engine sidecar를 하나의 GitHub release로 다루고, Windows 빌드 스크립트가 각 SHA-256과 `built_windows_unverified`/`publish_ready=false` manifest를 생성 **SOURCE PASS**
- 최신 브라우저 확인: 1920×1080 viewport 요청 세션에서 매뉴얼·설정 노출, 전용 금융 인텔리전스 렌더, 실제 DOM `scrollWidth == clientWidth`, 콘솔 error 0 **PASS**. 브라우저 호스트 유효 viewport는 1731×1214로 보고됐다.
- 동기화 충돌 재현: Synology Drive가 `FinancialIntelligenceWorkspace.tsx`를 `*_Conflict.tsx`로 변경해 Vite import 실패·빈 화면을 만든 사실을 실브라우저에서 확인했다. 정본 파일 복원 뒤 Python뿐 아니라 TS/TSX/JS/JSX/JSON 충돌 파일도 활성 소스 감사에서 차단 **PASS**
- 최신 전체 Python 회귀: `1,517 passed, 8 skipped, 0 failed`, 경고 2건 **PASS**. Binance TP/SL 실계정 2건은 `INTEGRATION_TEST=1` 명시 실행으로 격리했다.
- 활성 소스 감사: 활성 Python 374개, 구문 실패·금지 Python/Web 활성 소스·정의 전용 대시보드 메서드 0, broker 계약 **PASS**
- 문서/버전 정합성 **PASS**
- 당시 소스 판정: 구조 분리와 AI 커스텀·12개 고급 읽기 기능의 API/컴포넌트 연결 및 Windows bundle 생성은 확인했다. 이는 UI/UX·사용 흐름 동등성 완료가 아니며, 현재 재작업과 외부 게이트가 남아 `built_windows_unverified`, `publish_ready=false`다.

### Stage 0 기준선 기록

- 기능 inventory·엄격 DTO·read-only API·인증/Origin·시장 데이터 정규화·Electron 보안 설정 집중 회귀: `8 passed` **PASS**
- 전체 Python 회귀: `1,483 passed, 6 skipped, 0 failed` **PASS**
- React/TypeScript production build: Vite 6.4.3, 37 modules, JS 370.78 kB, gzip 118.14 kB **PASS**
- Electron 셸: 43.4.0 설치 확인, context isolation·sandbox·navigation 차단 구성 **SOURCE PASS**
- npm 보안 감사: production/전체 `0 vulnerabilities` **PASS**
- 브라우저 실렌더: Binance BTCUSDT 캔들·거래량, 5개 서비스, 블록체인 11개/주식 7개 기능, 15분→1시간 전환, 오류 배너 0, 콘솔 오류 0 **PASS**
- 당시 레거시 엔진 영향: 기존 설정·전략·주문 코드는 변경하지 않았고 Gateway command endpoint는 0개 **PASS BY SCOPE (HISTORICAL)**
- 아직 미검증: 실제 runtime snapshot adapter, Windows bundle/설치/자동업데이트/롤백, 다중 모니터, 장시간 PAPER/LIVE **PENDING**
- 배포 상태: `pending_windows_rebuild`; 직전 v3.9.0.10 EXE SHA `6aaa66787666...`는 이전 자산으로 보존
- 비차단 경고: FastAPI 0.141.1/Starlette 1.6.0 TestClient의 `httpx` 호환 deprecation 1건. 제품 런타임 실패는 아니며 테스트 의존성 전환 때 제거한다.

## 2026-08-13 UI 플랫폼 전환 설계·기준선 (배포 버전 변경 없음)

- 현행 구조 분석: CustomTkinter 대형 화면 클래스, 동적 탭/콜백/Toplevel 소유권, UI의 거래·설정 직접 결합을 전환 대상 경계로 식별 **DOCUMENTED**
- 의존성 분석: Windows 키움은 PyQt5/QAxWidget을 사용하고 현재 빌드는 PySide6/PyQt6를 제외함 **CONFIRMED**
- 목표 구조: Web UI + desktop shell + localhost gateway + Python application services + 별도 Kiwoom worker **DECIDED FOR PLAN**
- 기능 보존 준비: 앱 셸·5개 서비스·6개 거래소·4개 증권·AI 커스텀·차트·설정·OMS·파일/업데이트 기능군 parity 원장 정의 **DOCUMENTED**
- 차트/랭킹 준비: Lightweight Charts 후보, market event 계약, 전략/XAI marker, 목적별 검증 랭킹·privacy/license 경계 **DOCUMENTED**
- 소스 기준선 백업: 633개 파일, SHA-256 `b4bdf11d6c633c1c4942bb1fb422241436fd3c923dfac2230e3e8146bb48ab96` **VERIFIED**
- 기존 자동 회귀 기준: v3.9.0.10 `1,475 passed, 6 skipped, 0 failed`; 이번 작업은 문서·백업만 수행하여 런타임 결과를 새로 주장하지 않음
- 미검증: Electron/Tauri POC, Gateway 계약, 화면 parity, Windows 설치형 EXE, bundle 자동업데이터·롤백, 다중 모니터, PAPER/LIVE E2E **NOT IMPLEMENTED**
- 판정: UI 전환 계획과 복구 기준선은 준비됐지만 제품 UI 전환은 아직 시작되지 않음

## v3.9.0.10 AI Custom Management & Runtime Integrity Update 소스 검증 (2026-08-13)

- 설정 회귀: `dashboard_modern.py`의 `copy.deepcopy()` 의존성 import와 설정창 생성 경로 회귀 검사 **PASS**
- 소스 탭 생명주기: 서비스별 예약 렌더 최신 1개 병합, 선택/세대 재확인, 새 트리 완성 뒤 이전 트리 정리, 대시보드 Toplevel 소유권 검사 **PASS**
- AI 커스텀 생명주기: 7개 저장 전략 조건, 시작 시 헤더-only 지연 생성, 최초 선택 1회 생성, `CTkScrollableFrame._parent_frame` 소유권 판정, 반복 선택 동일 인스턴스 재사용, 중복 idle·재진입 차단 **PASS**
- 프라이빗 전략 관리: 저장 버전 복원→새 버전 저장, 적용 중 삭제 차단, 비활성 전체 버전 삭제, 민감 규칙 없는 삭제 tombstone **PASS**
- AI 커스텀 실제 macOS 렌더: 위젯 생성, 6개 상위 카드, root Toplevel 소유권 **PASS**
- 전체 자동 회귀: `1,475 passed, 6 skipped, 0 failed` (`.venv/bin/python -m pytest -q`, 2026-08-13) **PASS**
- Windows 외부 게이트: v3.9.0.10 EXE 신규 빌드, 설정 50회, 6개 거래소 왕복 100회, 급속 탭 전환 200회, USER/GDI/TK_MENU, 분리 native 창 0, PAPER 2시간
- 배포 상태: `pending_windows_rebuild`; 직전 v3.9.0.9 EXE SHA-256 `857ee230a60f...`는 이전 자산

## v3.9.0.9 AI Custom Stability Update 소스 검증 (2026-08-12)

- 배포 신원: 현재 `deploy/release-manifest.json`은 v3.9.0.9 `pending_windows_rebuild`를 가리킵니다. 공개 v3.9.0.8 Fix 4 SHA-256 `91070a67eb0a...`는 이전 자산으로 별도 보존했으며 새 Windows EXE·manifest SHA가 필요합니다.
- Windows 메뉴 상한: CTkComboBox/OptionMenu 500개 생성 후 유휴 `TK_MENU=0`, 전체 설정창 생성·숨김·재열기 후 `TK_MENU=0` **PASS**. 선택 중에도 프로세스 전체 최대 1개 native 메뉴만 허용합니다.
- 탭/상태 정본: 금융 인텔리전스가 6개 거래소보다 앞에 위치, `거래소: 6곳 · 기준 BINANCE`, `자동매매: 정지 (0/6 실행)` 순수 계약 회귀 **PASS**.
- 사용자 AI 비용 사실확인: `data/260809_Teayu/ai_market_call_budget.json`에서 2026-07-24~08-09 매일 정확히 1,200회 소진, DeepSeek 화면 74,492 요청·57,134,137토큰과 증가 방향 일치 **CONFIRMED**
- 인과 경계: Provider 화면만으로 3.9.0.7만의 단독 원인은 확정하지 않음. 로컬 시장 원장 20,400회와 Provider 전체 74,492회의 차이는 시장분석 밖 호출·다른 경로/클라이언트 포함 가능 **OPEN TELEMETRY**
- AI 호출 회귀: level-trigger 후보/RSI 제거, 단순 새 캔들 로컬 처리, 30분 상태 캐시, 5분 미세변화 간격, 기존 고비용 설정 hard ceiling, 모든 자동 역할 영속 예산 **PASS**
- OMS 회귀: 암호화폐 명령 원자 선점·재시작 중복 차단, 거래소별 client-order ID 전달, 오류 분류, 모호한 청산 재주문 금지와 신규진입 중단 **PASS**
- 사용자 원장 복제 시뮬레이션: 기존 8월 10,800회는 `legacy_snapshot` 보존, Fix 4 카운터 240회에서 정지, 6개 거래소별 최대 40회 **PASS**
- 설정/탭/프로세스 집중 회귀: UI-only diff 무재시작, 메뉴 가드 선설치, 선택 source 단일 트리, 원자적 중복 실행 차단, Binance 구독 직렬화 **PASS**
- macOS 실렌더: 설정 읽기 `0.003초`, 전체 설정 UI 생성 `0.696초`, BINANCE→UPBIT→BITHUMB→BINANCE에서 완전한 source 트리 항상 1개 **PASS**
- 전체 자동 회귀 `1,468 passed, 6 skipped, 0 failed` (`.venv/bin/python -m pytest -q`, 2026-08-12)
- Windows 외부 게이트: 새 v3.9.0.9 EXE, 설정/6개 거래소 왕복 100회, 중복 실행 차단, USER/GDI/TK_MENU 상한, Binance PAPER 2시간, client-order ID·주문/포지션 조정 E2E
- 현재 소스 배포 상태: `pending_windows_rebuild`; 이전 공개 v3.9.0.8 Fix 4 Windows 자산과 구분

## v3.9.0.8 AI Custom Update Fix 3 실행 소유권 검증 (2026-08-11)

- 포지션 소유권: NoahAI 진입 주문 원장이 있는 포지션만 재시작 복구·모니터 청산·close_all·우아한 종료 대상으로 인정 **PASS**
- 수동/외부 포지션: 자동청산 제외, 활성 위험 한도에는 합산 **PASS**
- 현물 방향: Upbit·Bithumb SHORT 신규 주문 0, NoahAI 관리 LONG만 청산 신호로 변환, 수동 잔고 보호 **PASS**
- 중복 진입 복구: 같은 심볼의 NoahAI 진입 수량·가중 진입가·주문 ID 집계, 분할 원장 일괄 종료 손익 중복 방지 **PASS**
- 주문 오류: Upbit·Bithumb 빈 오류 응답 제거, 원문 오류 보존, 동일 청산 실패 KPI 중복 억제와 30~900초 재시도 간격 **PASS**
- 초기 검증: Binance 포함 6개 거래소 완료 거래 0건 선행조건 제거, 제한 학습 1포지션·1배, `진입 차단 사유 아님` XAI **PASS**
- 레버리지: 설정 상한과 실제 적용값 분리, 현물 1배, 선물 고변동 1/보통 2/저변동 3배 공통 정책과 초기검증 상한 **PASS**
- AI 어시스턴트: 화면 선택 거래소보다 질문에 명시한 거래소 우선, 최근 실행 판단·실제 레버리지·축소 이유 표시 **PASS**
- 집중 회귀: `111 passed`; 전체 자동 회귀: `1,450 passed, 6 skipped, 0 failed`
- 현재 배포 상태: `pending_windows_rebuild` — Windows 새 EXE 및 거래소별 소액 LIVE·재시작 복구는 외부 검증 필요

## v3.9.0.8 AI Custom Update Fix 2 소스 검증 (2026-08-11)

- 업데이트 상태 머신 집중 회귀: 종료 전 승인 1회, 종료 후 재조회 금지, 승인 없는 적용 차단, 실패 staged EXE 재시도, 같은 버전 설치 SHA 불일치 차단, PowerShell 상태 기록 순서·복사 후 SHA 검증 **PASS**
- UI 재사용 집중 회귀: 동일 서비스 재클릭 no-op, 동일 source 구성 재사용, 현재 선택 탭 보존, 부분 렌더 fail-closed, 종료 전 승인 순서 **PASS**
- 업데이트·UI 근본 원인 집중 회귀: `35 passed`; 버전·매뉴얼·AI 지식 포함 집중 회귀: `86 passed`
- 전체 자동 회귀: `1,441 passed, 6 skipped, 0 failed`
- Python 구문 검사, 문서/버전 정합성, 빌드 포함 검사, 활성 소스 감사 **PASS**(활성 Python 342개, 구문 실패·금지 활성 소스·정의 전용 대시보드 메서드 0개)
- Windows 외부 게이트: Fix 2 새 EXE 빌드·SHA 확정, 최초 수동 교체, 설정 100회, 블록체인↔주식 100회, USER/GDI 상한, 다운로드→종료→교체→재시작→설치 SHA 일치, 실패 후 재시도
- 현재 배포 상태: `pending_windows_rebuild`

## v3.9.0.8 AI Custom Update Fix 1 공통 원인 재검증 (2026-08-11)

- 동적 화면 소유권 registry: 속성/매핑 identity 해제, 재구성 200회 뒤 바인딩 0, 대시보드 저수준 삭제 단일 경계 **PASS**
- AI·시장 트렌드·금융 인텔리전스·AlphaArena·코인/종목·거래 통계·AI 애널리스트 장기 참조를 같은 탭 소유권에 등록 **PASS**
- 통합자산 현재 잔고 단일 저장소, 동시 갱신, KRW/USDT 무단 합산 차단, 구형/신형 거래 DB 공통 어댑터 **PASS**
- 시나리오 점검·보안 경고의 `asset_type`·`entry_amount` 직접 SQL 0건 **PASS**
- AI 요청 ID 단일 원장의 `running → completed/failed`, 파괴된 Tcl 입력 거부, 생존 위젯 재확인 **PASS**
- 공통 원인 집중 회귀: `48 passed`
- 전체 자동 회귀: `1,432 passed, 6 skipped, 0 failed`
- 문서/버전 정합성 `PASS`, 빌드 포함 검사 `PASS`, 활성 소스 감사 `PASS`(활성 Python 342개, 구문 실패·정의 전용 메서드 0개)
- 실제 사용자 DB 읽기 점검: `data/nwsoft/trading.db` 종료 거래 104건, `data/Teayu/trading.db` 종료 거래 47,699건을 레거시 호환 경로로 읽고 스키마 오류 0건
- Windows 외부 게이트: 새 EXE에서 자산 잔고 수신·통화별 표기, AI 애널리스트 심층분석 응답, 하단 실행 기록 생성까지 실제 계정/화면으로 확인
- 현재 배포 상태: `pending_windows_rebuild`

## v3.9.0.8 AI Custom Update Fix 1 검증 (2026-08-10)

- Fix 1 집중 회귀: 설정창 단일 인스턴스·native 메뉴 회수·정본 탭 순서·현재 서비스 설정 갱신·포지션 경량 렌더 계약
- 기존 UI 생명주기·서비스 정책·설정창 복구·메뉴 회귀와 함께 재검증
- 전체 자동 회귀: `1,421 passed, 6 skipped, 0 failed`
- native 메뉴 반복 생성 스모크: 12개 ComboBox 생성/정리 100회에서 메뉴 명령 `3 → 최대 15 → 3`, 잔류 명령 0개
- 실제 설정창 재사용 스모크: 설정창 생성 전 메뉴 3개, 생성 후 35개, 숨김/재표시 25회 내내 35개 고정, 단일 창 유지, `dispose()` 후 3개 복귀
- 실제 CTkTabview 정본 순서 스모크: 프레임 identity와 현재 선택을 유지한 채 `실시간 로그 → 코인 정보 → 거래 통계 → BINANCE` 순서 복구
- 문서/버전 정합성 `PASS`, 빌드 포함 검사 `PASS`, 활성 소스 감사 `PASS`(활성 Python 339개, 구문 실패·정의 전용 메서드 0개)
- Windows 외부 게이트: 새 EXE에서 설정 열기/닫기 100회, 블록체인↔주식 100회, 10회 단위 USER/GDI 기록, 빈 창·탭 혼합·순서 이동·빈 포지션 카드 0건
- 현재 배포 상태: `pending_windows_rebuild`

## v3.9.0.8 AI Custom Update 검증 (2026-08-10)

- 기존 P1~P3 신규 기능 집중 회귀: `35 passed`
- 버전·대시보드 매뉴얼·AI 어시스턴트 지식까지 포함한 집중 회귀: `94 passed`
- 확인 계약: 초보자/일반/고급/실험실 프로필과 개별 게이트, 종속 기능 fail-closed, 중첩 Expression Graph, 제한형 사용자 지표 AST와 임의 코드 차단, IR 노드/의존성, 총 PnL·MDD·월별/연별 표, 백테스트 단독 자동 승격 차단, `.noahstrategy` 변조/민감정보 차단과 비활성 가져오기, webhook 서명/시간/중복 차단, 품질/재생 diff/감사 계약
- Python 구문 검사: 변경 Python/UI 모듈 `PASS`; 설정 템플릿 JSON 파싱 `PASS`
- 전체 회귀: `1,411 passed, 6 skipped`
- 문서·버전 정합성: `PASS`
- 빌드 포함 검사: `PASS`
- 활성 소스 감사: `PASS` — 활성 Python 337개, 구문 실패 0, 금지 활성 소스 0, 격리 아티팩트 16개 정상
- 외부 미검증: Windows 설치본 화면/설정 저장, 실제 TradingView 재생·webhook, 장시간 PAPER/LIVE, 회원/팀 서버 공유, 인증 B2B API, 결제·정산·법무

## AI 커스텀 Noah Strategy IR v1 검증 (2026-08-09)

- IR·파이프라인·런타임·한국어 RSI 변환 집중 회귀: `34 passed`
- 확인 계약: canonical rules 무손실 왕복, Level 1·2·3 동일 계약, 모든 실행 노드 근거, capability 판정, `supported / needs_clarification / unsupported`, 규칙·IR 변조 차단, 레거시 저장 버전 승격, 선언형 RSI 진입 평가, 활성 풀 재검증
- 실제 CustomTkinter 생성 스모크: Level 1 기본 표시, Level 3 안전 DSL 표시, Level 2 복귀, 대표 한국어 RSI 원본의 `supported`·근거 `2/2`·전체 IR 렌더 `PASS`
- 문서·버전 정합: `PASS`
- 전체 회귀: `1,397 passed, 6 skipped, 2 failed`. 실패 2건은 이번 변경 경로가 아니라 `deploy/release-manifest.json`의 실제 `build_status=built`와 과거 `pending_windows_rebuild`를 고정 기대하는 릴리스 메타데이터 테스트 불일치
- 위 알려진 릴리스 기대값 2건을 제외한 전체 회귀: `1,397 passed, 6 skipped, 2 deselected`
- 미검증: Windows 설치본 실제 화면, Pine·PDF·영상 코퍼스 의미 동등성, 실제 계정 장시간 PAPER/LIVE, 실체결·재시작 복구. 사용자 절차는 `AI_CUSTOM_FEATURE_TEST_AND_FEEDBACK_GUIDE_20260809.md` 참조

## v3.9.0.7 Fix Patch 3 검증 (2026-08-08)

- 소스 집중 회귀: VC 단일 세트 검증·최신 공식 세트 선택·혼합/구형 차단·PyQt 보존·ONNX/PaddleOCR 지연 로드·검증 실패 exit code `7 passed`
- UI 탭 실제 파괴·콜백 정리·Windows 리소스 probe, 거래소 컨텍스트·Binance 런타임 범위, KRW 현물 dust·관리수량 정책 집중 회귀: `PASS`
- 클라이언트 전체 회귀: `1,377 passed, 6 skipped`
- 문서·버전 정합, 빌드 포함 검사, 활성 소스·격리 감사: `PASS`
- PyQt5는 키움 QAxWidget 지원을 위해 유지하며 `pyi_rth_pyqt5` 제거를 해결책으로 사용하지 않음
- macOS에서는 Windows PE/VC 파일의 정책과 소스 테스트까지만 가능하며 새 EXE는 `pending_windows_rebuild`
- Windows 빌드 후 완성 EXE의 하위 VC DLL 0개·공식 원본 SHA-256·Kiwoom·OCR·제보 PC Binance PAPER, 서비스/거래소 100회 전환 USER/GDI 상한, Bitget-only 무-Binance 호출, Bithumb/Upbit 소액 체결을 별도 확인해야 함
- 공개 Fix Patch 2 EXE는 `previous_published_asset`으로 보존하고 Fix Patch 3 자산과 혼용하지 않음

## v3.9.0.7 Fix Patch 2 검증 (2026-08-08)

- 개인정보 allowlist·Windows PID·활성 로그 비삭제·원문 응답 로그 금지 집중 회귀: `22 passed`
- 설정창 레이아웃·모달 복구·창별 아이콘 캐시·하단 버튼 축소 집중 회귀: `5 passed`
- 클라이언트 전체 회귀: `1,354 passed, 6 skipped`
- 문서·버전 정합, 빌드 포함 검사, 활성 소스·격리 감사: `PASS`
- Windows EXE·SHA-256·설치 후 로그인 로그·회전·재시작 E2E는 `pending_windows_rebuild`
- 공개 당시 Fix Patch 1 EXE를 비교 자산으로 보존했으며, 현재는 Fix Patch 2가 Fix Patch 3의 `previous_published_asset`임

## v3.9.0.7 Fix Patch 1 검증 (2026-08-07)

- daltrading 전체 회귀: `52 passed, 3 subtests passed`
- 클라이언트 전체 회귀: `1,344 passed, 6 skipped`
- 문서·버전·릴리스 자산·AI 키 없는 시작·일시 상태 장애·명시적 세션 종료 집중 회귀: `16 passed`
- 운영 daltrading: SHA `dc827ec`, 서비스 active, 로그인 쿠키 전략 허브와 관리자 암호화 Affiliate 키 설정 배포
- 운영 Affiliate 자동조회 준비: Binance·Bybit·OKX·Bitget 모두 실제 자격증명 미입력으로 `manual_fallback`; 관리자 설정 저장·마스킹·삭제·기존 pending 재검증 경로는 자동 회귀 통과
- Windows EXE는 `pending_windows_rebuild`; 사용자가 Windows에서 재빌드·SHA·설치 검증하기 전 소스 수정 배포 완료로 보지 않음

## v3.9.0.7 Source Candidate 2 검증 (2026-08-06)

- daltrading 전체 회귀: `45 passed, 3 subtests passed`
- 클라이언트 레퍼럴 로컬 UID·Secret 비전송·정책 집중 회귀: `11 passed`
- Python 구문 검사: `referral_account_proof.py`, `membership_policy.py`, `ui/settings_modern.py`, `config/app_version.py` 통과
- 운영 daltrading: SHA `e534f92`, 웹 서비스 active, 재검증 timer active/job success, 홈·레퍼럴 가입 HTTP 200, 무인증 자동검증 401
- 운영 Affiliate 환경파일: 권한 600, 실제 Bybit·Bitget·OKX 조회 전용 값 미입력으로 모두 `manual_fallback`
- 전체 클라이언트 회귀는 임시 테스트 환경의 `numpy/loguru/websocket` 미설치로 수집하지 못했으며 기존 Source Candidate 1 전체 회귀를 이번 변경 완료 근거로 재사용하지 않는다.
- Windows EXE·실제 Affiliate UID 자동 승인·LEARNING/PAPER는 `pending_windows_rebuild` 및 외부 계정 검증 전이다.

## v3.9.0.7 Source Candidate 1 검증 (2026-08-05)

### 레퍼럴 UID 귀속·공식 클라이언트 권한 집중 검증

- daltrading 전체 자동 회귀: **41 passed, 3 subtests passed, 0 failed**
- NoahAI 레퍼럴 정책·설정·실행 안전 집중 회귀: **32 passed, 0 failed**
- 확인 계약: UID 암호화 저장·마스킹 응답, 미승인 allowed_exchanges 제외, verified만 허용, 유료 등급 면제, 설정 API/거래소 선택 제어, 시작 게이트 소스
- NoahAI 전체 자동 회귀: **1,336 passed, 6 skipped, 0 failed** (`.venv/bin/python -m pytest -q`, 2026-08-05)
- 문서 정합: **PASS** (`.venv/bin/python scripts/doc_consistency_check.py`)
- 빌드 포함 검사: **PASS** (`.venv/bin/python verify_build_includes.py`)
- 활성 소스·격리 감사: **PASS**, 활성 Python 310개·구문 실패 0·격리 아티팩트 16개 정상 (`.venv/bin/python scripts/active_source_audit.py`)
- daltrading 운영 배포·실제 Affiliate Portal UID 대사·브라우저 E2E·Windows EXE: **`pending_windows_rebuild`**, 외부 검증 전

## v3.9.0.6 Source Candidate 2 검증 (2026-08-04)

### 체결 조회 API 예산·증분 동기화 집중 검증

- AI 커스텀 1~5단계 소스 후보 집중 회귀: **15 passed** — 고급 주문 계획 fail-closed·부분청산 체결 상태, AI 멘토·버전 diff, 검증 연구소·PAPER 기록, 전략 충돌 HOLD·강등 제안, 공통 주문 상태·인증 체결 큐
- 분석 10초 주기 반복 호출 방지, LIVE 저빈도 증분 커서, LEARNING 개인 체결 API 미호출, 미확정 주문 ID 전용 재조회, 수동 전체 백필 분리, 로컬 realized PnL·커서 보존: **5 passed**
- CCXT `since` 전달과 기존 체결 기능 계약, 공통 원장·갱신·통화 정합 확대 집중 회귀: **45 passed**
- 전체 자동 회귀: **1,332 passed, 6 skipped, 0 failed** (`.venv/bin/python -m pytest -q`, 2026-08-04)
- 문서 정합·빌드 포함·활성 소스/격리 감사: **PASS**
- Windows EXE·거래소/증권 SDK별 인증 사용자 체결 스트림 바인딩·실계정 부분청산/복구·장시간 실행: `pending_windows_rebuild`, 외부 검증 전

### 사용자 `data/260802_Teayu` 기반 집중 검증

- SQLite `quick_check`: `ok`
- Source Candidate 1 당시 전체 자동 회귀: **1,308 passed, 6 skipped**
- 거래소 원본 심볼·무이력 학습 임계값·KRW/USDT 분리·챔피언–챌린저·동시 실행 종료 진단 집중 회귀 포함 PASS
- 문서/버전 정합 검사, 빌드 포함 검사, 활성 소스·격리 감사: PASS
- 사용자 DB에는 기존 `reason=binance_import` 행 4,800건이 보존되어 있으며 최근 7일 200건이 원시 fill 성과로 중복 편입돼 있었습니다. 제외 후 challenger는 494건, `USDT -2.4001`, `KRW +112.0228`로 분리되고 금액 우열은 `inconclusive_currency_boundary`입니다.
- Windows EXE: `pending_windows_rebuild`; 실제 API 주문·재시작·장시간 실행은 미검증
- 기존 v3.9.0.5 검증 이력은 아래에 보존합니다.

## v3.9.0.5 소스·출시 준비 검증 (2026-08-01)

### 2026-08-01 Fix Patch 5 · 갱신 생존성·체결 원장 연결 검증

- 전체 자동 회귀: **1,298 passed, 6 skipped, 0 failed** (`.venv/bin/python -m pytest -q`, 2026-08-02)
- Fix Patch 5 집중 회귀: **6 passed** — Map 이벤트 없는 숨김→표시 자동 복구, CCXT LIVE 진입·청산 성과 원장 연결과 멱등성, Binance 네이티브 공통 체결 원장, AI 리포트 실제 체결 조회, 사용자 구형 DB의 미청산 행·거래소 식별자 보존형 시작 마이그레이션, DB 준비 실패 시 거래 초기화 차단
- 인앱 실거래 필수 안내 집중 회귀: **5 passed** — Fix Patch 설치 식별, 최초 1회 안내 확인 저장, 대시보드·설정 상시 진입점, 매뉴얼 독립 탭, 6개 거래소·4개 증권사·회원등급·LIVE 조건 정본
- PAPER 대시보드·실행모드·계좌 상태 집중 회귀: **23 passed** — LIVE 저장소 혼입 차단, Binance/통합 PAPER 저장소, 가상 PnL 요약
- 주문 안전·학습 파이프라인 집중 회귀: **26 passed**
- 계좌 상태 컨트롤러·대시보드 집중 회귀: **47 passed**
- 활성 소스 감사: **PASS** (`.venv/bin/python scripts/active_source_audit.py`) — Python 구문, 금지/충돌 소스, `ModernDashboard` 정의 전용 메서드 0개, 외부 격리 16개 SHA-256, 증권 4개 계약, 필수 문서
- 빌드 포함 검증: **PASS** (`.venv/bin/python verify_build_includes.py`)
- 문서·버전 정합: **PASS** (`.venv/bin/python scripts/doc_consistency_check.py`)
- 소스 검증 경계: Windows EXE, 실제 거래소/증권사 계정, 키움 OCX, 실제 주문·취소·체결, 재시작 후 복구, 24~72시간 갱신 지속성은 증명하지 않음
- 배포 manifest: **`pending_windows_rebuild`**. 공개 Fix Patch 1 EXE와 Fix Patch 5 소스를 구분
- 직전 사용자 재현 Fix Patch 4 EXE는 `previous_tested_asset`으로 보존하며, Fix Patch 5 배포 자산의 size·SHA는 Windows 재빌드 전까지 비워 둠

### 2026-08-01 Fix Patch 3 · 증권사 공식 계약·LIVE AND 권한

- 증권 공식 계약 집중 회귀: **7 passed** — 설정 자동 이전, 잘못된 XingAPI/KIS 혼선 제거, LIVE AND 권한, KIS 공식 헤더/TR ID/실전·모의 주문, 신한 HMAC 봉투
- 증권 경계·팩토리·어댑터 확대 회귀: **131 passed, 6 skipped**
- 4개 증권사 Mock 연결·잔고·계좌·포지션 진단: **28 OK, 0 FAIL** (`scripts/verify_stock_broker_connection.py --all_brokers --no_save`; 실계정 증거 아님)
- 전체 자동 회귀: **1,277 passed, 6 skipped, 0 failed** (`.venv/bin/python -m pytest -q`, 2026-08-01)
- Python 구문·설정 템플릿 JSON 검사: **PASS**
- 미검증: Windows 빌드/키움 OCX, 실제 증권 계약 계정의 연결·잔고·포지션·소액 주문·취소·체결내역, 배포 후 재시작·장시간 안정성

### 2026-08-01 Fix Patch 2 · 확정 체결·통계 복구·Binance 포지션

- 구조 감사 집중 회귀: **79 passed** — 공통 어댑터 단일 정본과 Bithumb 정상 0건 뒤 재조회 포함
- 관련 거래소·증권·대시보드 확대 회귀: **144 passed, 6 skipped**
- 미사용·손상 위젯 격리 후 전체 활성 소스 compileall: **PASS**
- 증권 API 성숙도 계약: **15개 등록 조합 확인**, 미구현 2개 생성 차단, 나머지 실계정 미검증 경로 실주문 실패 폐쇄
- 빌드 구조 검증: **PASS** — spec 단일 생성기, Python 소스 datas 이중 번들·폐기 테마 제거, Windows hidden import 판정 수정
- 전체 자동 회귀: **1,269 passed, 6 skipped, 0 failed, 0 warnings** (`.venv/bin/python -m pytest -q`, 2026-08-01)
- 집중 회귀: **26 passed** — 주문 ID별 체결 복구, 미확정 주문 체결 오인 차단, 거래소·주문 ID 청산 연결, Binance 포지션 시간 재동기화·정본 클라이언트 포함
- Python 구문 검사: **PASS**
- 문서·버전 정합성: **PASS**
- `prekey` 게이트 기능 검사는 통과했으나 현재 폴더에 `.git`이 없어 `SYNC_GUARD` 단계는 **FAIL**
- manifest: `pending_windows_rebuild`; 새 EXE 크기·SHA 비움, 직전 공개 Fix Patch 1 자산은 `previous_published_asset`에 보존
- 미검증: Windows EXE, 실계정 6개 거래소 주문 계약, Bithumb 최소 매수·매도·복구, Binance 포지션 장시간 갱신, 24~72시간 안정성

### 2026-07-31 Update Patch 1 · 거래소 공통 원장·화면 조회·자동업데이트

- 전체 자동 회귀: **1,254 passed, 6 skipped, 0 failed** (`.venv/bin/python -m pytest -q`, 2026-07-31)
- 최소 주문 규격·포지션 갱신 후속: Binance 제출 직전 필터, 5개 CCXT market limit·정밀도, KRW 5,000원 폴백, 위험 분할 후 재검증, 거래소·증권 비동기 포지션 갱신 포함
- Update Patch 1 집중 회귀: **78 passed** — 5개 CCXT 새 주문·체결/완료주문 폴백 기능 계약과 실행 중 원장 정합화, raw `closed` 성공/취소 실패, Bithumb 원장·통계 분리, 최신 PAPER/LIVE 동기화, 전역 읽기 조회·상한 UI 큐, 15초 최초/설정 주기, 동일 버전 SHA, GitHub 외 URL 차단 포함
- 수정 파일 Python 구문 검사: **PASS**
- 공개 v3.9.0.5 Fix Patch 1 EXE는 `362,674,458`바이트, SHA-256 `1508310500f27ce91dc0148b49371da58daa51d5b2a783eca921c851ece74f67`
- 현재 Update Patch 1 manifest: `pending_windows_rebuild`, 새 EXE 크기·SHA는 의도적으로 비어 있고 공개 Fix Patch 1 자산은 `previous_published_asset`으로 분리
- Windows 새 EXE의 Bybit LIVE 최소단위 주문, Bithumb 매수·매도·통계 동기화, 서비스 왕복 잔고, Fix Patch 1 자동업데이트는 사용자 빌드 후 외부 검증 게이트

### 2026-07-29 설정 정본·실행 모드·사용자 안내

- 당시 전체 자동 회귀: **1,233 passed, 6 skipped, 0 failed**
- Fix Patch 1: 동적 전체 보유자산·단일 잔고 호출·설정 탭별 AI 질문·FAQ 독립 스크롤·KRW 알트/주식/ETF 학습 분류·데모 기준통화 회귀 포함
- SelectionPolicy·StrategyUniversePolicy·regime_scope·동일기회·ExitPolicy 집중 회귀: **51 passed**
- AI 시장분석·포지션 크기·손실패턴 캐시, 실패 쿨다운, 역할별 Provider 경계, 거래소 지원 심볼 fail-closed, KOSPI·KOSDAQ·ETF 유니버스 집중 회귀: **PASS**
- 멀티 거래소 E2E **72 passed**, 증권 집중 회귀 **157 passed, 6 skipped**, `prekey` 릴리스 게이트 **PASS**
- Teayu_02 읽기 전용 실연결: Upbit·Bithumb·Bybit·OKX·Bitget 인증/IP 차단, Binance 계정 정보 빈 응답으로 암호화폐 6개 모두 운영 준비 미완료
- 빈 잔고 거짓 성공·인증 원인 오분류·진단 설정 변경·비밀값 로그·전략 파일 권한·준비도 프로세스 정리·Binance 폴백 미구현을 회귀 수정
- 통합 판정 정본: `INTEGRATED_AUDIT_v3.9.0.5_20260731.md`
- Teayu_02 장애 집중 회귀: 필수 keyring 제거, v3.9.0.3 참조 호환 저장, 전 거래소 잔고 정본·숨은 탭 재개·12초 제한·terminal 상태, AI 설정창 수명주기, 배열/dict OHLCV, 문자열 심볼 HOLD 격리, datetime 저장, TP/SL 포지션 확인 **12 passed**
- TP/SL 무결성 집중 회귀: 구버전 퍼센트 단위 최초 1회 저장, AI 화면 fraction 기본값, 비정상 값 안전 복구 포함 **8 passed**
- Teayu_02 원본 로그 증거: 지연 잔고 갱신 `NameError` 90건, 비정상 종료 감지 4건, 파괴 위젯 `TclError` 1건, 과거 UI 성능 로그 1,393,277줄. 원본은 수정하지 않음
- requirements와 두 PyInstaller 스펙에 keyring·Windows 보안 저장소 의존성이 없음을 자동 검증. Windows 최종 사용자는 별도 패키지 설치 없음
- `runtime_faulthandler.log`에는 native fatal stack이 없어 비정상 종료의 단일 원인을 단정하지 않으며 서명 Windows 설치본 장시간 검증을 외부 게이트로 유지
- 설정 v3.9.0.5 정본·레거시 보관·AlphaArena 이전·범위 부분집합 집중 회귀: **4 passed**
- 설정 템플릿 감사: 정본 `3.9.0.5`, LEARNING 기본값, 레거시·모순 0건 **PASS**
- Teayu 2026-07-29 설정 증거 감사: 실행 미사용 과거 설정 20개, AlphaArena 중복 10개, 확인 표식 없는 실주문 6개 확인. 원본 증거 파일은 수정하지 않음
- 동일 설정의 v3.9.0.5 메모리 마이그레이션: 정본 3.9.0.5, 과거 값 25개 호환 보관, LEARNING 잠금, 모순 0건 **PASS**
- 문서·버전 정합성 검사와 Python 문법·JSON 구문: **PASS**
- 당시 v3.9.0.5 manifest는 `pending_windows_rebuild`였으며 이후 Fix Patch 1이 공개되었습니다. 현재 Update Patch 1는 다시 Windows 재빌드 대기 상태입니다.

### 2026-07-28 작업별 멀티 Provider·독립 전사·모델 수명주기

- 전체 자동 회귀: **1,135 passed, 6 skipped, 0 failed, 4 warnings**
- 작업별 `ai_model_roles.<tier> = {provider, model}` 저장·라우팅과 기존 모델 문자열 자동 이전 확인
- 분석 Provider와 OpenAI transcription Provider 분리 확인
- 권장·계정 확인·미리보기·비권장·종료 상태와 종료/capability 불일치 차단 확인
- Claude Sonnet 5·Opus 5·Fable 5, Gemini 3.5 Flash-Lite·3.6 Flash, Kimi K3·K2.6 공식 기준 목록 반영
- 실제 자격증명 검증 도구: 설정의 `실제 API 기능 검증`, `scripts/ai_provider_preflight.py`
- 외부 게이트: Windows 서명 후보 빌드에서 약 10명의 사용자 겸 테스터가 각자 보유한 Provider 키로 텍스트·JSON·usage·error·선택적 전사를 검증
- Kimi 공식 Open Platform의 OpenAI 호환·JSON Mode·비전 계약에 맞춰 정식 Provider로 등록. 실제 계정 권한은 앱의 `실제 API 기능 검증`에서 별도 확인

- Teayu 안정성·주문 범위·AI 커스텀 고급모드·탭 callback 수명주기·업데이트 P0·Claude/Gemini·문서 정합 반영 전체 자동 회귀: **1128 passed, 6 skipped, 0 failed, 3 warnings**
- 업데이트 캐시 타겟 복구·시간대 정규화·성능 로그 회전·명시적 주문 범위 집중 회귀: **10 passed**
- AI 커스텀 사용자 기간·다중 시간봉·AND/OR·안전 차단 포함 관련 통합 회귀: **35 passed**
- 실제 주문은 만들지 않았으며 Windows 새 EXE의 거래소별 최소 주문·24~72시간 실행은 외부 게이트
- Provider Router·capability·공통 텍스트/JSON/사용량/오류 계약 집중 회귀: **13 passed**
- AI 엔진 계약·v3.9.0.3 credential reference 호환·로컬 설정 저장 집중 회귀: **16 passed**
- 탭 callback 수명주기·업데이트 P0·Claude/Gemini·가격 카탈로그 집중 회귀: **32 passed, 0 failed**
- AI 엔진 문서 정합 회귀: **5 passed, 0 failed**
- 전체 자동 회귀: **1128 passed, 6 skipped, 0 failed, 3 warnings**
- Python 문법·`settings_template.json` 구문: **PASS**
- v3.9.0.3 Keychain/keyring 자동 이전은 v3.9.0.5 정책에서 철회
- 현재 계정 설정 마이그레이션: 기존 OpenAI 모델·로컬 키 보존, 새 provider profile/model schema 생성, AlphaArena `deepseek-v4-flash` 이전, `settings.json` 권한 `0600` **PASS**
- OpenAI·DeepSeek·Anthropic·Gemini 실연결 검증 경로: **준비 완료**. 현재 계정과 환경 변수에 제공사 API 키가 없어 인증·동적 모델 목록 확인은 건너뜀
- AlphaArena 멀티 엔진 비교·실거래 연결은 이번 후보에서 제외하고 다음 업데이트로 이관
- v3.9.0.2는 이전 고객 배포본이며, 오늘 변경은 실제 제공사 키·서명 Windows 빌드·설치·자동복원 검증 후 v3.9.0.5로 배포
- Windows 글꼴·비정상 종료 진단·학습/주문 거래소 분리·AI 커스텀 1+4 프리셋 집중 회귀: **10 passed**
- 위 피드백 회귀와 기존 AI Provider Router·거래소 범위 회귀 통합: **25 passed**
- 프리셋 무키 분석: 지원하지 않는 선언형 조건은 없으며, ATR·스윙 손절 등 확정 불가 값은 누락 조건으로 남겨 승인 준비 상태를 차단 **PASS**
- 사용자 노출 동기화와 문서/버전 정합성: **PASS**
- Windows 10/11 배율별 글꼴 실화면, Authenticode 서명 EXE의 이전 버전 업데이트·health check 실패 자동복원, 비정상 종료 장시간 재현, 각 실제 거래소 최소 주문은 외부 게이트로 유지
- README·문서 색인·업데이트 내역·사용자 가이드·인앱 매뉴얼·AI API 사용자/아키텍처·확장 계획·기술 백서 정합성: **PASS**

---

## 문서 동기화 메모 (2026-07-27 KPI 수집·대시보드 정합)

- 2026-07-27 기간별 실행 분포·KRW 체결금액 보강 포함 최신 실행: `1079 passed, 6 skipped, 3 warnings`.
- 포지션 KPI 재시도·종료 flush·안전 종료 경로·결제통화 회귀: `9 passed`.
- 클라이언트 통화별 체결금액·유효 평균 보유시간·거래 통계·리포트 연결 집중 회귀: `93 passed`.
- 공통 팔레트·AI 리포트·주식 거래 통계·생활금융 월간 요약·어시스턴트 모델명 비노출 UI 정합 회귀: `12 passed`; 대시보드 집중 회귀: `39 passed`.
- 클라이언트 레퍼럴 정책·AI 도움말·UI 집중 회귀: `10 passed`.
- daltrading 기간별 동시 거래소 분포·거래량·보유시간·회원정책 KPI 회귀: `20 passed`.
- daltrading EC2 운영 배포: 약 1.8GB DB 백업·WAL·무결성 `ok`, KPI 런타임 커밋 `1b058b5`, 배포 기록 포함 서버 HEAD `f5bc66d`, 서비스·공개 경로 HTTP 200 **PASS**.
- 운영 30일 원본 집계: USDT `103047.56`, KRW `0`, 진입 `82`, 종료 `0`, 수집률 `관찰 중`; 집계 응답 `14.35초`. 실행 스냅샷은 1·7·30·90일 모두 `1개 3명`, `6개 1명`이고, KRW 실제 체결 `0건`·Upbit/Bithumb 활동 `1,022,044건`으로 확인했다.
- Python 문법, 사용자 매뉴얼 JSON, daltrading Jinja 전체 템플릿 파싱: **PASS**.
- 앞선 UI 정합 집중 회귀 `127 passed`, 문서·사용자 노출 동기화, macOS 실화면 검증 결과는 유지한다.
- macOS 1500×980 실화면: 블록체인 거래 통계 약 7행 표시와 표 단일 스크롤, 금융 인텔리전스 초보자 안내·AI 질문 버튼, 생활금융 공통 고정 스킨 렌더링 **PASS**.
- 소스/문서 버전 단일 소스(`config/app_version.py`) 기준 제품 버전은 `v3.9.0.5`이며 Fix Patch 포함 여부는 배포 manifest의 빌드 시각·크기·SHA로 구분한다.
- 현재 공개 자산은 v3.9.0.5 Fix Patch 1이다. 오늘 변경을 담은 Update Patch 1 manifest는 `pending_windows_rebuild`이며 새 EXE 검증이 필요하다.
- 전체 자동 테스트 최신 실행: `1079 passed, 6 skipped, 3 warnings` (2026-07-27, macOS/Python 3.13, 기간별 실행 분포·KRW 체결금액 포함)
- 경고 3건은 기존 `scripts/test_coin_selection*.py`의 list 반환이며 실패는 아니다.
- AI 커스텀·어시스턴트 집중 회귀: `81 passed, 0 failed`.
- Python 문법 검사: 어시스턴트·AI 커스텀·인앱 매뉴얼·설정·선언형 엔진·신규 테스트 파일 PASS.
- 문서 정합성 검사: `scripts/doc_consistency_check.py` PASS.
- v3.9.0.5 업데이트 표면 정합성: README·설정 정본 안내·문서 진입점·인앱 업데이트·사용자 가이드·릴리스 노트·Windows 배포용 `deploy/release_notes.md`·변경이력·공통/AI 커스텀 아키텍처·AI 어시스턴트·거래 흐름·계획·배포 체크리스트·테스트 상태 필수 항목 **PASS**.
- 신규 대상 테스트: EMA200 워밍업, 비용 반영 검증, 미지원 조건 차단, 코인 명시 청산, AI 커스텀 명시/제외 시장국면 추천, NoahAI 정체성·대화 문맥·모호한 요청 재질문·강제 최종확인, 설정 타입 레지스트리·중첩값 롤백을 포함한다.
- QA 절차 정본: `AI_CUSTOM_ASSISTANT_TEST_RUNBOOK_v3.9.0.2.md`. 실제 비밀번호·API 키는 문서에 저장하지 않는다.

---

## 이전 배포 범위 테스트 결과 (2026-07-27 v3.9.0.2)

- 전체 회귀: **1079 passed, 6 skipped, 0 failed, 3 warnings**
- KPI 수집 집중 회귀: **9 passed, 0 failed**
- daltrading 정책·KPI 회귀: **20 passed, 0 failed**
- AI 커스텀·어시스턴트 안전성 집중 회귀: **81 passed, 0 failed**
- AI 커스텀 실행 정합성: EMA/SMA 20·50·200, ADX·ATR·거래량, 미지원 조건 fail-closed, 비중첩 비용 검증, 코인 명시 청산 **PASS**
- Pine 교차·국면 안정화: 직전/현재 캔들 교차 판정, 국면 시각·신뢰도·오래된 입력 차단·히스테리시스 **PASS**
- AI 어시스턴트 설정·작업 안전성: 등록된 설정만 변경, 사용자 최종확인, 저장 후 재조회, 사용자별 영속 감사로그·재시작 후 되돌리기, 주문/거래상태/API/출금 보호 작업 미실행 **PASS**
- 포지션 KPI·테스트 격리 집중 회귀: **8 passed, 0 failed**
- TP/SL 무결성·코인/종목 정보 탭 집중 회귀: **7 passed, 0 failed**
- AI 커스텀 위험기반 전략 집중 회귀: **56 passed, 0 failed**
- AI 비용·성과 집중 회귀: **108 passed, 0 failed**
- 금융 인텔리전스·생활금융·메뉴 정책 집중 회귀: **181 passed**
- 문서/버전 정합성: **PASS**
- Python 문법 검사: 금융 인텔리전스·대시보드·인앱 매뉴얼 수정 파일 **PASS**
- 공개 데이터 스모크: Binance BTCUSDT, Yahoo Finance AAPL·KOSPI·KRW 환율·금 선물 **PASS**
- 로컬 UI 스모크(macOS): 금융 인텔리전스가 BINANCE보다 앞에 표시되고, 시장 프리셋·종목 입력·차트·조회 버튼 본문까지 실제 렌더됨 **PASS**
- 금융 인텔리전스 탭 재선택/지연 초기화: 동일 서비스 위젯 재사용으로 CustomTkinter Canvas 예약 콜백 충돌과 빈 탭 회귀 방지 **PASS**
- 사용자 화면 표기 점검: 운영체제 이모지를 제거하고 앱 렌더링 공용 아이콘·서비스별 선택 색상·탭 대비로 macOS/Windows 표기 기준 통일 **PASS**
- 대시보드 공간 회귀: 하단 상태·업데이트·AI 실행 기록을 동일 행으로 배치하고 본문 세로 공간 복구, 공용 아이콘·탭 스타일 집중 회귀 `29 passed` **PASS**
- macOS 실화면: 1500×980 대시보드에서 한 줄 하단 패널과 공용 아이콘 렌더링 확인 **PASS**
- 인앱 매뉴얼·도움 동선 정적/회귀 검증: 당시 v3.9.0.2 제목, AI 커스텀 초보자/결과 질문 버튼, 시장국면 추천 설명 **PASS**
- 정본 버전 감사: 당시 v3.9.0.2 배포 범위의 README·마스터 인덱스·변경이력·계획·사용자 가이드·아키텍처·거래 흐름·개발/API·빌드/배포·테스트·백서·사업·AlphaArena·코인·대시보드 **PASS**
- 문서 구조 감사: `docs` 최상위 179개 → 103개, 이력 79개는 `docs/archive/`로 이동, 런타임 보고서 1,168개는 공식 문서에서 분리 **PASS**
- 빌드 사전 게이트(`release_gate.py --profile prekey`): 증권 회귀 `150 passed, 6 skipped`, 모드 매트릭스·무키 점검·문서 정합·사용자 노출 동기화·다중 거래소 불변조건·준비도 체인 **PASS**. 이번 AI 커스텀·어시스턴트 변경 29개 파일을 `SYNC_GUARD_CHANGED_FILES`로 명시했다.
- 실연동 준비도: 선택 거래소 Binance는 인증·잔고 조회 준비 완료. Upbit·Bithumb·Bybit·OKX·Bitget은 현재 키/권한/네트워크/추가 자격증명 점검이 필요하며 배포 후 해당 거래소 실운용 전 재검증한다.
- 현재 남은 외부 게이트: v3.9.0.5 Windows 빌드·설치·전수 실클릭, YouTube/TradingView 실제 URL 입력 E2E, SEC/DART 운영 자격증명, 각 실제 거래소 장시간 또는 최소단위 검증

---

## 최신 점검 결과 (2026-07-05 거래소 진단/정합)

### 2026-07-05 반영
- 운영 진단(5m x 50 캔들, 상위 10심볼)
   - 결과: Bitget 10/10, Upbit 10/10, Bithumb 10/10, Bybit 0/10(Unmatched IP), OKX 0/10(연결 실패)
   - 해석: 다중 거래소 미체결 이슈를 전략 로직 단일 원인으로 보지 않고, 인증/권한/IP 화이트리스트 계층으로 분리 진단 가능
- 정적 오류 점검(`get_errors`) 핵심 수정 파일
   - 대상: `trading/unified_trader.py`, `trading/recorder.py`, `trading/exchanges/adapters/bitget_futures_adapter.py`, `trading/exchanges/adapters/bybit_futures_adapter.py`, `trading/exchanges/adapters/okx_futures_adapter.py`, `ui/settings_modern.py`
   - 결과: **No errors found**
   - 해석: 2026-07-05 거래소 진단 UX 및 Unified 게이트 정합 패치 기준 신규 오류 없음

---

## 최신 테스트 결과 (2026-06-05 v3.8.9.21)

**후속 안정화 검증: PASS**

### 2026-06-05 반영
- `python3 scripts/multi_exchange_stability_check.py`
   - 결과: **PASS**
   - 해석: 전역 전체시작 제거 정책과 거래소별 상태/코인 분리 불변조건 통과
- 정적 오류 점검(`get_errors`) 핵심 파일
   - 대상: `trading/unified_trader.py`, `trading/evaluator.py`, `ui/dashboard_modern.py`, `ui/login_modern.py`
   - 결과: **No errors found**
   - 해석: v3.8.9.21 후속 핫픽스 반영 파일에 신규 오류 없음

---

## 최신 테스트 결과 (2026-05-29 v3.8.9.20)

**패치 검증: 2건 완료**

### 2026-05-29 반영
- `python -m py_compile trading/unified_trader.py`
   - 결과: **성공 (문법 오류 없음)**
   - 해석: 실시간 청산 net PnL 산식 정합화 패치의 기본 문법 안정성 확인
- 정적 오류 점검(`get_errors`) 핵심 수정 파일
   - 대상: `trading/unified_trader.py`, `ui/widgets/user_manual_widget.py`
   - 결과: **No errors found**
   - 해석: 코드/인앱 공지 반영 파일에 신규 오류 없음

---

## 최신 테스트 결과 (2026-05-21 v3.8.9.20)

**추가 검증: 3 passed**

### 2026-05-21 반영
- `pytest -q tests/test_fl_rl_data_adapter.py tests/test_federated_learning_manager.py tests/test_federated_learning_preparation.py`
   - 결과: **3 passed**
   - 해석: FL/RL 사전 준비 구조(전이 변환/배치 관리/오케스트레이터) 기본 동작 정상
- 정적 오류 점검(`get_errors`) 신규/수정 파일
   - 결과: **No errors found**
   - 해석: 버전 상향/문서 동기화 포함 변경 파일 문제 없음

---

## 최신 테스트 결과 (2026-05-07 검증 동기화)

**추가 검증: 102 passed** (경고 0건)

### 2026-05-07 반영
- `python -m pytest tests/test_dashboard_full_button_e2e.py tests/test_menu_regression.py tests/test_service_tab_policy_snapshot.py tests/test_settings_backup.py -q --tb=short`
   - 결과: **102 passed**
   - 해석: 대시보드 전수 버튼/탭 E2E(44) 신규 추가 후 기존 핵심 회귀와 충돌 없이 통과
- `python3 scripts/verify_stock_broker_connection.py --all_brokers --no_save`
   - 결과: **kiwoom/shinhan/miraeAsset 18/18 OK**
   - 해석: 브로커 연결 검증 스크립트 정상 동작(조합검증/어댑터생성/연결/잔고/계좌/포지션)

---

## 이전 기준선 (2026-05-04 안정화)

**전체: 813 passed, 6 skipped** (경고 0건)

### 2026-05-04 품질 고도화 반영
- `python -m pytest tests/ -q`
   - 결과: **813 passed, 6 skipped, 0 warnings**
   - 해석: 음성 배포 안정화 + 경고 제거 패치 반영 후 전체 회귀 통과
- 경고 제거 항목
   - `api/backend_api.py`: `websockets.client.connect` deprecated import 제거
   - `tests/test_tp_sl_validation.py`: `PytestReturnNotNoneWarning` 제거 (pytest 테스트/스크립트 함수 분리)
   - `trading/recorder.py`: sqlite datetime 바인딩을 ISO 문자열로 정규화

---

## 이전 기준선 (2026-05-03 9차)

**전체: 814 passed, 6 skipped** (신규 85개 추가)

| 테스트 파일 | 결과 | 내용 |
|------------|------|------|
| test_tax_calculation_service.py | **53 passed** (신규) | 세무계산, 연말정산, 금투세, ISA/IRP 비교 |
| test_fraud_detection_service.py | **32 passed** (신규) | 보이스피싱, 이상거래, 약탈적대출 탐지 |
| test_stock_symbol_search.py | 43 passed | 종목 검색/자동완성/즐겨찾기/최근검색 |
| test_asset_correlation_service.py | 44 passed | 자산 상관관계 분석, 리밸런싱 제안 |
| test_life_finance_goal_service.py | 45 passed | 목표 관리, 시뮬레이션, 예산 배분 |
| test_mock_live_boundary.py | 32 passed | Mock/Live 경계, allow_live_order |
| test_asset_mode_etf_stock_branch.py | 44 passed | ETF/주식 분기 로직 |
| test_community_qna_chat.py | 36 passed | 커뮤니티 QnA/Chat |
| test_alpha_arena_readiness.py | 26 passed | AlphaArena 준비도 |
| test_menu_regression.py | 42 passed | 메뉴 회귀 |

> flaky 1건: `test_ai_assistant_context.py::test_restore_default_strategy_applies_loaded_settings`
> — 단독 실행 시 통과, 전체 실행 시 전역 상태 충돌. 이번 변경과 무관.

---

# 테스트 현황 요약 — 2026-05-03 (최신)

본 문서는 현재까지 확인된 실행/기능 테스트 결과를 요약합니다.
문서 설명보다 실제 코드 동작 범위를 우선 표기합니다.

## 중요 정리 (주식/ETF / 해외선물 관련)
- 주식/ETF UI 경로와 어댑터 라우팅은 동작합니다.
- 주식/ETF 실증권사 연동 상태: 키움(pykiwoom 골격), **신한(REST 완성 + 401 자동갱신 + health_check)**, **미래에셋(REST 완성 + 401 자동갱신 + health_check)**
- 주식/ETF 통합 테스트 `tests/test_stock_integration.py`의 PASS는 대부분 Mock 어댑터 기준입니다.
- 해외선물(증권사) 전용 어댑터/실주문 경로는 현재 코드에 구현되어 있지 않습니다.
- 현재 실운영 선물 경로는 암호화폐 futures(예: binance/bybit/okx/bitget)입니다.

## 환경
- OS: macOS
- 실행 방식: 소스 직접 실행 (python3 main.py)
- Python: 3.13

## 추가 확인 결과 (2026-05-03 9차 당시)
- `python -m pytest tests/ -q`
   - 결과: **595 passed, 6 skipped**
   - 해석: 전체 테스트 스위트 통과 (ETF 실시간 지표 연동 +11, AlphaArena readiness +26, 메뉴 회귀 +42, 커뮤니티 QnA/Chat +36 신규 추가)

### 신규 추가 테스트 그룹 (2026-05-03 6차)
- `tests/test_etf_adapter_indicators.py`: **67 passed** (+11, 신한/미래에셋 trade_value/expense_ratio 필드매핑, get_etf_realtime_metrics 통합)
- `tests/test_alpha_arena_readiness.py`: **26 passed** (신규 생성, start/stop/주문게이트/예외복구/readiness 체크리스트)
- `tests/test_menu_regression.py`: **42 passed** (신규 생성, 서비스명 정규화/탭 보호/구조 불변성/새로고침 경로/컨텍스트 동기화)
- `tests/test_community_qna_chat.py`: **36 passed** (신규 생성, QnA 목록/상세/등록, 답변 등록, 채팅 조회/전송, 공지사항 7개 API)

## 추가 타겟 검증 (2026-05-03 최신) — 수익성 검증/워크포워드 자동화
- `python -m pytest tests/test_profitability_validation.py tests/test_stock_analysis_service.py -q`
   - 결과: **74 passed**
   - 해석: ProfitabilityValidator 단위 25건 + StockAnalysisService 통합 2건 추가로 `profitability_blocked`/`insufficient_trades bypass` 동작 검증

## 추가 타겟 검증 (2026-05-03 최신) — UI/AlphaArena/문서 정합성
- `python -m pytest tests/test_service_tab_policy_snapshot.py -q`
   - 결과: **4 passed**
   - 해석: 블록체인/증권 서비스 보호 탭 정책(snapshot) 정상
- `python -m pytest tests/test_alpha_arena_guardrails.py -q`
   - 결과: **6 passed**
   - 해석: AlphaArena 틱 주기/TP·SL/리스크캡/쿨다운/동시포지션 가드레일 정상
- `python scripts/stock_supported_mode_matrix_check.py`
   - 결과: **PASS** (11개 조합 확인, 키움 Windows 필요 2건 경고)
- `python scripts/doc_consistency_check.py`
   - 결과: **PASS** (dashboard/manual/user_guide/policy 핵심 표기 일치)

## 추가 타겟 검증 (2026-05-03) — 어댑터 로버스트니스
- `python -m pytest tests/test_stock_adapter_robustness.py -v`
   - 결과: **23 passed**
   - 해석: 신한/미래에셋 토큰 자동갱신(401 재시도), health_check, api_type/api_version 실행경로 방어검증


## 추가 타겟 검증 (2026-05-02) — ETF 지표 어댑터 연동
- `python -m pytest tests/test_etf_adapter_indicators.py -v`
   - 결과: **56 passed**
   - 해석: StockMockAdapter/ShinhanStockAdapter/MiraeAssetStockAdapter get_etf_list 필드매핑 검증 (`isuSrtCd→code`, `trcErrRt→tracking_error`, `bchidxNm→base_index` / `stck_shrt_cd→code`, `trc_errt→tracking_error`, `bchm_nm→base_index`), is_etf() 코드 범위 판별, ETFMetrics risk_level(ok/warn/alert)/nav_gap/summary/to_dict, score_etf() 점수 계산, StockAnalysisService.get_etf_analysis() Mock 통합 전체 통과

## 추가 타겟 검증 (2026-05-02) — Phase F 생활금융 회귀
- `python -m pytest tests/test_life_finance_phase_f.py -v`
   - 결과: **27 passed**
   - 해석: LifeFinanceQualityTracker.build_quality_report() 리스크 판정, FinanceProductAdvisor 외부 JSON 카탈로그 로드/갱신/사용자 태그 매칭 전체 통과

## 최신 확인 결과 (2026-04-24)
- `python -m pytest tests/ -q`
   - 결과: **125 passed, 6 skipped** (당시 기준)
   - 해석: 전체 테스트 스위트 통과
- `python -m pytest tests/test_kiwoom_backend_adapter.py -q`
   - 결과: 6 passed
   - 해석: 키움 어댑터 fake backend — 연결/잔고/보유종목/시세/미체결/주문 파싱 골격 검증
- `python -m pytest tests/test_shinhan_backend_adapter.py -q`
   - 결과: 8 passed
   - 해석: 신한 SOL Trading API REST 어댑터 — connect/balance/positions/open_orders/place_order/is_etf/account_info 검증
- `python -m pytest tests/test_mirae_asset_backend_adapter.py -q`
   - 결과: 10 passed
   - 해석: 미래에셋 Open Trading API REST 어댑터 — connect/balance/positions/open_orders/trade_history/place_order/cancel_order/is_etf/account_info 검증
- `python -m pytest tests/test_stock_analysis_service.py -q`
   - 결과: 27 passed
   - 해석: StockAnalysisService (ETFMetrics, score_stock, summarize_portfolio, AI context, symbol analysis, 분석 로그 이벤트) 전체 커버
- `python -m pytest tests/test_stock_integration.py -q`
   - 결과: 46 passed, 6 skipped
   - 해석: Live 테스트는 `LIVE_STOCK_TEST=true`에서만 동작하며, 키움 Live는 Windows + pykiwoom 조건 미충족 시 명시적으로 skip 처리

## 추가 검증 결과 (2026-04-24)
- 상위 메뉴 `🤖 AI애널리스트` 클릭 시 `switch_service("ai_analyst")` 경로 동작 확인
- 서비스 전환 시 정보 탭 보호 정책 서비스별 적용 확인
   - `blockchain` 모드: `🪙 코인 정보` 유지
   - `stock` 모드: `🪙 종목 정보` 유지
- AI 애널리스트 화면이 준비중 플레이스홀더가 아니라 카드형 분석 UI로 렌더링되는 코드 경로 확인
- 시장 트렌드/AI 학습 위젯의 `set_service_context()` 존재 및 대시보드 전환 시 동기 호출 경로 확인
- STT 배포 의존성 정합성 확인
   - `requirements.txt`: `SpeechRecognition`, `pyaudio` 포함
   - `aiautotrade.spec` hiddenimports: `speech_recognition`, `pyaudio` 포함

## 런타임 장애/제약 점검 (2026-04-24 추가)
- `python3 main.py` 실행 시 발생하던 메뉴얼 위젯 들여쓰기 오류 수정 완료
   - 원인: `ui/widgets/user_manual_widget.py`의 `create_multi_exchange_tab` 블록 들여쓰기 불일치
   - 조치: 클래스 메서드 들여쓰기 정렬 후 import 스모크 및 main.py 재실행 확인
- 실행 상태: import 단계 크래시 해소, 로그인 창 진입까지 확인
- 시장 트렌드 상단 칩 정합성 개선
   - `ui/widgets/market_trend_widget.py`: 데이터 미수집 상태를 `0.0000`처럼 표시하지 않고 `수집 대기`로 표시
   - 주식 컨텍스트에서 코인 전용 심리(펀딩비/공포탐욕) 강제 표시를 피하고 일반화 칩으로 전환
- 아직 남은 제한 경로(코드 기준)
   - AlphaArena `qwen3-max`는 DashScope 전용 클라이언트 경로가 미구현(주석/미지원 표기 존재)
    - 자산 통합/생활금융은 더 이상 준비중 화면만 있는 상태는 아님
       - 자산 통합: 통합 자산 현황/비중/리스크 요약/추천 액션 표시
       - 생활금융: 수입/고정비/변동비 입력과 저축 가능액 계산 제공
    - 다만 두 영역 모두 DB 저장, 자동 분류, 심화 추천까지 완료된 상태는 아님
   - 커뮤니티 QnA/Chat은 플레이스홀더 성격(실시간 연동 미완료)

## 추가 타겟 검증 (2026-04-27)
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_analysis_service.py tests/test_stock_integration.py -q`
   - 결과: **74 passed, 6 skipped**
   - 해석: 종목 검색/분석과 증권 통합 경로의 핵심 회귀는 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_analysis_service.py tests/test_alpha_arena_guardrails.py -q`
   - 결과: **38 passed**
   - 해석: 주식/ETF 표시 모드 필터, 증권 AI 컨텍스트 분기, AlphaArena 틱 주기/TP·SL/리스크 캡/쿨다운/동시 포지션 가드레일 회귀 통과
- 코드 기준 정정 사항
   - 자산 통합/생활금융: "안내만 존재" 문구는 최신 빌드와 불일치
   - AlphaArena: 설정 화면에는 Qwen 관련 항목이 남아 있지만, 대시보드 실행 위젯은 DeepSeek 우선 경로 기준
   - 주식/ETF: 사용자용 `통합/주식만/ETF만` 표시 모드는 추가되었지만, 증권 자동주문 경로는 아직 암호화폐처럼 완성되지 않음

## 추가 타겟 검증 (2026-04-27 Phase 1-2)
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_order_guardrails.py tests/test_stock_integration.py tests/test_stock_analysis_service.py -q`
   - 결과: **86 passed, 6 skipped**
   - 해석: 증권 가드레일(시장시간/모드불일치/한도초과/최소주문단위/정상) + 종목분석 + 통합 경로 전체 회귀 통과

## 추가 타겟 검증 (2026-04-28 D0)
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_integration.py -q`
   - 결과: **47 passed, 6 skipped**
   - 해석: 주문 결과에 `execution_mode`, `api_type`, `success` 메타데이터 추가 후 증권 통합 계약 유지
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_analysis_service.py tests/test_stock_integration.py -q`
   - 결과: **79 passed, 6 skipped**
   - 해석: 주식/ETF 분석 결과에 `analysis_type`, `score_model`, `reasoning`을 추가한 후 분석 분기와 주문 경로 회귀가 함께 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_integration.py tests/test_stock_analysis_service.py tests/test_stock_order_guardrails.py -q`
   - 결과: **91 passed, 6 skipped**
   - 해석: 대시보드 증권 주문 호출을 `qty` 우선 재시도에서 `quantity` 계약 우선 호출로 정규화한 후 핵심 증권 회귀 전체 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_integration.py -q`
   - 결과: **48 passed, 6 skipped**
   - 해석: 실주문 feature flag 기본값(`enable_stock_live_order`, `allow_live_order`) 추가 후 증권 통합 계약 테스트 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_analysis_service.py -q`
   - 결과: **35 passed**
   - 해석: 증권 자동매매 1차 로직(`evaluate_trade_signal`, `run_auto_trade_cycle`) 단위 검증 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_analysis_service.py tests/test_stock_integration.py -q`
   - 결과: **84 passed, 6 skipped**
   - 해석: 자동매매 1차 루프 + 설정 기본값 + 실주문 차단 분기까지 증권 핵심 회귀 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_analysis_service.py tests/test_stock_integration.py -q`
   - 결과: **84 passed, 6 skipped**
   - 해석: 자동매매 경로에서 심볼 단위 XAI 저장 및 성공 주문 즉시 `trade_log` 기록 보강 후에도 회귀 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_integration.py tests/test_stock_analysis_service.py -q`
   - 결과: **85 passed, 6 skipped**
   - 해석: 종목 검색 고도화 1차(최근검색/즐겨찾기/원클릭 재검색)와 템플릿 기본값(`stock_search_profile`) 추가 후 회귀 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_integration.py tests/test_stock_analysis_service.py -q`
   - 결과: **85 passed, 6 skipped**
   - 해석: 종목 검색 고도화 2차(자동완성/부분일치 추천/원클릭 제안 검색) 반영 후에도 증권 핵심 회귀 유지
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_integration.py tests/test_stock_analysis_service.py -q`
   - 결과: **85 passed, 6 skipped**
   - 해석: 자산 통합 확장(상관계수/리밸런싱 제안) 반영 후에도 증권 핵심 회귀 유지
- 코드 기준 정정 사항
   - 증권 주문 결과는 이제 UI 상태 라벨에서 `모의주문 경로` 또는 `실주문 경로(api_type)`를 함께 표시한다.
   - `StockAnalysisService.analyze_symbol()`은 주식과 ETF에 대해 서로 다른 판단 근거 문자열을 생성한다.
   - `ui/dashboard_modern.py`의 증권 주문 호출은 이제 stock adapter 계약(`quantity`)을 우선 사용하고, 예전 호출 방식은 안전망으로만 유지한다.
   - `ui/dashboard_modern.py`는 mock이 아닌 주문 경로에서 feature flag가 꺼져 있으면 주문을 사전에 차단한다.
   - `StockAnalysisService.run_auto_trade_cycle()`가 주식/ETF 분석 신호를 기반으로 주문 실행(또는 live 차단)까지 1회 사이클로 처리한다.
   - `ui/dashboard_modern.py`는 `stock_auto_trading` 설정이 활성화되면 주식 서비스에서 주기적으로 자동매매 사이클을 실행한다.
   - 자동매매 각 심볼의 의사결정은 `stock_auto_trade_symbol` XAI로 저장되며, 사이클 요약은 `stock_auto_trade_cycle`로 저장된다.
   - 자동매매 성공 주문은 대시보드 수동주문과 동일하게 `trade_log`에 즉시 기록된다.
   - 종목 검색은 `stock_search_profile`에 최근검색/즐겨찾기를 저장하며, 검색 탭에서 즉시 재검색 버튼으로 재실행 가능하다.
   - 종목 검색은 자동완성 제안을 통해 코드/종목명 부분일치 검색을 지원한다.
   - 자산 통합 탭은 crypto/stock 일별 손익 기반 상관계수와 집중도 지표를 계산해 동적 리밸런싱 액션을 제시한다.
- Phase 1-2 정합 반영
   - 증권 탭은 분석/설명 중심 흐름으로 정리
   - 증권 가드레일은 시스템 경로에서 계속 적용(`trading/stock_order_guardrails.py`)
   - 브로커별 최소주문단위 검증(최소수량/수량단위) 유지
   - `config/settings_template.json` 의 `stock_order_guardrails` 기본값 유지

## 증권 개발 마스터 실행 순서 (1 → 2 → 3)

이 섹션은 지금부터 실제 개발을 마무리할 때까지의 기준 문서다.
목표는 "국내 주식/ETF를 실제로 문제 없이 연결하고, AI/설정/어시스턴트까지 일관되게 작동시킨 뒤, 해외를 별도 확장"하는 것이다.

### 1단계. 국내 주식/ETF 완성 (최우선)

#### 목표
- 키움을 기준 브로커로 먼저 완성한다.
- 국내 주식/ETF의 연결, 잔고, 보유종목, 시세, 주문, 미체결, 로그, 통계가 실제 계정 기준으로 동작해야 한다.
- Mock 없이도 사용자가 설정 저장 후 대시보드에서 실제 상태를 확인할 수 있어야 한다.

#### 현재 상태
- UI/설정/어댑터 라우팅은 이미 존재한다.
- 키움 어댑터는 pure placeholder에서 한 단계 올라가 backend 기반 연결/파싱 구조를 갖췄다.
- 다만 실계좌 Live 검증과 실제 pykiwoom/키움 REST 운영 검증은 아직 남아 있다.
- 따라서 지금은 "증권 구조와 키움 연동 골격은 있으나 실거래 완성은 아님"으로 판단한다.

#### 구현 대상 모듈
- 설정/UI: `ui/settings_modern.py`
- 대시보드/증권 탭: `ui/dashboard_modern.py`
- 팩토리/라우팅: `trading/exchanges/exchange_factory.py`
- 인터페이스: `trading/exchanges/interfaces/stock_exchange.py`
- 증권 어댑터: `trading/exchanges/adapters/kiwoom_stock_adapter.py`
- 후속 어댑터: `trading/exchanges/adapters/shinhan_stock_adapter.py`, `trading/exchanges/adapters/mirae_asset_stock_adapter.py`

#### 필수 데이터 (국내 주식/ETF)
- 사용자 인증 정보: ID, 비밀번호, 인증서/추가 비밀번호, 계좌번호
- 계좌 정보: 예수금, 주문가능금액, 총자산, 평가손익
- 보유 종목: 종목코드, 종목명, 수량, 평균단가, 현재가, 평가손익, 수익률
- 시세 데이터: 현재가, 전일대비, 등락률, 거래량, 거래대금
- ETF 추가 데이터: NAV, 괴리율, 추적오차, 기초지수/섹터
- 주문 데이터: 매수/매도, 주문가, 주문수량, 체결수량, 미체결수량, 주문상태, 주문시간
- 일봉/분봉 데이터: AI 분석과 시장 분석 위젯에서 사용할 OHLCV

#### 사용자 계정 연결 방식
- 사용자는 설정창에서 증권사별 `api_type`, `api_version`, 계정정보를 입력한다.
- 저장 시 `stock_broker_configs` 아래에 증권사별 설정이 저장된다.
- 대시보드는 `_get_stock_adapter()`를 통해 선택 증권사 어댑터를 가져오고 연결한다.
- 연결 성공 시 증권 탭 잔고/보유종목/통계/로그가 실제 계정 기준으로 새로고침되어야 한다.

#### API 활용 방식
- 1차 기준은 키움 공식 REST/OpenAPI에서 가능한 범위를 우선 사용한다.
- 연결 API: 로그인/세션/토큰 발급 또는 OpenAPI 로그인
- 조회 API: 계좌조회, 잔고조회, 보유종목조회, 종목정보조회, 시세조회, 미체결조회
- 주문 API: 현금 매수/매도, 정정/취소
- ETF는 별도 상품군이 아니라 주식 주문 경로와 동일하되, 분석/표시에서 ETF 메타데이터를 추가 사용한다.

#### 키움 인증 방식 결정안 (2026-04-24)
- 기본 운영안: `api_type=openapi`, `api_version=pykiwoom`
- 적용 환경: Windows 실계좌 운용 환경
- macOS 개발 환경: 키움 Live 직접 연결은 제외하고 mock 또는 REST 기반 증권사(신한/미래에셋)로 검증
- 전환 조건: 키움 REST가 계좌/주문/미체결/체결까지 안정적으로 동일 커버되는 것이 확인되면 `api_type=rest` 분기 추가 검토

#### 완료 조건
- [x] 키움 `connect()` backend 연동 골격 구현
- [x] 키움 `get_balance()` 응답 표준화 골격 구현
- [x] 키움 `get_positions()` 응답 표준화 골격 구현
- [x] 키움 `get_realtime_price()` 응답 표준화 골격 구현
- [x] 키움 `place_order()` 호출 골격 구현
- [x] 키움 `get_open_orders()` 응답 표준화 골격 구현
- [x] 대시보드 주식 정보/통계 플레이스홀더 제거
- [x] 신한 `shinhan_stock_adapter.py` REST SOL Trading API 전면 구현
- [x] 미래에셋 `mirae_asset_stock_adapter.py` REST Open Trading API 전면 구현
- [x] `tests/test_shinhan_backend_adapter.py` fake backend 8개 테스트 추가
- [x] `tests/test_mirae_asset_backend_adapter.py` fake backend 10개 테스트 추가
- [ ] Live 테스트가 skip이 아니라 실제 통과로 전환

#### 개발 체크리스트
- [x] 키움 API 인증 방식 1차 확정 (현재 운영안: OpenAPI+ / pykiwoom)
- [x] 운영 OS 제약 확인 (키움 OpenAPI+ 직접 연결은 Windows 전용, macOS는 mock/타 증권사 REST 중심)
- [ ] `kiwoom_stock_adapter.py`의 남은 TODO 제거
- [x] 응답 필드를 내부 표준 포맷으로 매핑하는 기반 추가
- [ ] 주문 실패/세션 만료/장외시간 예외 처리
- [ ] 실계좌 전 미니 검증용 모의/테스트 모드 분리
- [x] fake backend 기반 어댑터 테스트 추가
- [ ] `tests/test_stock_integration.py`의 LIVE 구간을 실제 검증 가능 상태로 보강

### 2단계. AI/시장분석/어시스턴트/환경설정 일체화

#### 목표
- 주식/ETF가 단순 조회/주문만 되는 것이 아니라, NoahAI 엔진과 AI 어시스턴트가 실제로 증권 데이터를 활용해야 한다.
- 사용자는 설정, 분석, AI 설명, 로그, 거래 상태를 하나의 흐름으로 이해할 수 있어야 한다.

#### 현재 상태
- AI 어시스턴트는 stock 모드에서 증권사/보유 ETF 문맥을 읽는다.
- ETF 보유 시 추적오차/NAV 괴리/거래대금 문맥이 들어간다.
- 주식 종목 정보 탭과 주식 거래 통계 탭은 연결된 증권사 데이터 표시로 1차 전환되었다.
- 다만 아직 AI 분석 점수화/시장분석 서비스 모듈 분리는 미완이다.

#### AI가 실제로 해야 할 일
- 시장 분석: 국내 시장 장중/장마감 상태, 지수, 섹터, 거래대금, 변동성 확인
- 종목 분석: 가격, 거래량, 추세, 최근 변동성, 리스크 요인 요약
- ETF 분석: NAV 괴리, 추적오차, 거래대금, 섹터/지수 성격 요약
- 사용자 설명: 왜 이 종목/ETF가 위험한지 또는 유리한지 설명
- 설정 연동: 공격형/보수형 등 투자 성향에 따라 설정 제안
- 로그 연동: 분석 결과와 실제 주문/미체결/체결 결과를 분리 기록

#### 필요한 데이터 파이프라인
- 시세/호가/분봉/일봉 데이터 수집 모듈
- ETF 메타데이터 수집 모듈
- 장 상태/휴장일/시장시간 모듈
- 종목/ETF 공통 분석 모델 + ETF 전용 분석 보강 모듈
- AI 어시스턴트 컨텍스트 생성기
- 기록/환류 저장소 (판단 근거, 결과, 사후평가)

#### 위젯 및 모듈 분리 원칙
- 어댑터: 브로커 API 통신만 담당
- 분석 모듈: 시장/종목/ETF 분석만 담당
- 대시보드 위젯: 표시와 사용자 액션만 담당
- AI 어시스턴트: 설명/권장/설정 변경 지원만 담당
- 기록 모듈: 판단/결과/오류/이벤트 로그 저장만 담당

#### 완료 조건
- [x] `ui/dashboard_modern.py`의 주식 정보 탭 플레이스홀더 제거
- [x] `ui/dashboard_modern.py`의 주식 통계 탭 플레이스홀더 제거
- [x] 주식/ETF 분석용 서비스 모듈 분리 (`trading/stock_analysis_service.py` 완성, 27개 테스트)
- [x] AI 어시스턴트가 실제 종목/ETF 분석 결과를 콘텍스트로 사용 (`StockAnalysisService.build_ai_context()` 연동)
- [ ] 설정 변경이 증권 모드에서도 유효하게 반영
- [x] 판단 근거/리스크/결과가 로그에 남음 (`StockAnalysisService`가 portfolio/etf/trade/analyze 이벤트를 `stock_analysis` 카테고리로 기록)

#### 개발 체크리스트
- [ ] `show_stock_content()`와 관련 탭 갱신 흐름 재점검
- [ ] stock 전용 분석 서비스(`services` 또는 `trading` 하위) 설계
- [ ] 종목/ETF 점수화 기준 정의
- [ ] 주식용 위험관리 규칙 정의 (장마감, 변동성, 주문가능금액, 종목당 비중)
- [ ] AI 어시스턴트 프롬프트를 주식/ETF 기준으로 고도화
- [ ] 설정 UI와 어시스턴트 JSON 변경 경로 점검

### 3단계. 해외 확장 (국내 완성 후)

#### 원칙
- 해외는 국내 주식/ETF가 완성된 뒤 진행한다.
- 해외선물과 해외주식은 같은 문제가 아니므로 분리한다.
- "지원 가능성"과 "현재 코드 구현"을 반드시 구분한다.

#### 키움 해외선물 현재 확인 상태
- 저장소 내부 문서에는 "키움 해외선물 어댑터를 별도로 둘 수 있다"는 계획이 있다.
- 현재 코드에는 키움 해외선물 전용 어댑터/주문/조회 구현이 없다.
- 공개 확인 기준으로 `https://openapi.kiwoom.com/` 첫 화면에서 확인되는 범위는 국내주식 주문, 시세, 계좌 현황 중심이며, 이번 점검에서는 해외선물 API 지원을 공식적으로 확인하지 못했다.
- 따라서 현 시점 문서 기준 상태는 `확인 필요`로 둔다.

#### 해외 확장 분기
- A안: 국내 증권사 경유 해외선물/해외주식 API가 실제 가능하면 별도 어댑터 추가
- B안: 한국인이 이용 가능한 해외 브로커/해외 증권사 API가 안정적이면 별도 브로커 어댑터 추가
- C안: 암호화폐 futures 엔진 구조를 재사용하되, 자산/심볼/거래시간/증거금 규칙만 분리

#### 해외 단계 착수 조건
- [ ] 국내 주식/ETF 실거래 경로 완료
- [ ] 주식/ETF 분석/AI/로그 일체화 완료
- [ ] 키움 해외선물 공식 API 문서 또는 실제 지원 근거 확보
- [ ] 해외 브로커 후보군별 한국 사용자 이용 가능성, 법적/운영상 제한 점검

#### 해외 단계 개발 체크리스트
- [ ] 키움 해외선물 공식 지원 여부 재확인
- [ ] 별도 `FuturesExchange` 기반 증권사 해외선물 어댑터 필요 여부 결정
- [ ] 심볼 규칙, 거래시간, 만기, 롤오버, 증거금, 통화 처리 정의
- [ ] 해외주식과 해외선물의 UI/분석/주문 규칙 분리

## 오늘 기준 결론
- 지금 바로 완성해야 하는 것은 국내 주식/ETF다.
- 키움을 먼저 완성하는 전략은 타당하다.
- 다만 "키움이 해외선물을 지원한다"는 이유만으로 현재 앱이 바로 그 경로를 쓸 수 있는 상태는 아니다.
- 해외는 국내 주식/ETF 완성 후, 공식 지원 근거와 API 스펙을 확보한 뒤 별도 단계로 진행한다.

## 실행/런타임
- 직접 실행 (python3 main.py): PASS — Exit Code 0 (개발용 로그인 우회 NOAHAI_SKIP_LOGIN로 신속 검증 완료)
   - 진단 로그: 경로/토큰/설정 출력 OK, trading.log 초기화 OK
   - 참고: docs/TROUBLESHOOTING.md (권한/경로/Tk 포함 여부/네트워크 등)
   - 로그 소음 최소화: API 키 미입력 거래소는 비활성 처리되어 불필요한 인증/심볼 오류 로그가 생성되지 않음
   - 업데이트: BinanceClient에 API 키 가드를 전면 적용했고, WS unsubscribe가 서버에도 반영되도록 개선하여 무키 환경 소음을 더 줄임
   - 추가: WebSocket 경로의 "Invalid symbol" 로그는 최초 1회만 경고로 출력, 이후 동일 심볼은 디버그로 억제됨 (중복 소음 방지)

## UI — ModernDashboard (CustomTkinter)
- 상단 콘텐츠 CTkTabview 초기화/배치: PASS (정적 점검)
- 기본 탭 “📊 실시간 거래 로그” 생성 보장: PASS (정적 점검)
- 서비스 전환 시 하위 탭(블록체인/주식/부동산/기타/AI 애널리스트) 정리 및 재구성: PASS (정적 점검)
- 블록체인 서비스 내 거래소 하위 탭 라이프사이클(활성화된 거래소만 생성, 비활성화 시 제거): PASS (정적 점검)
- 커뮤니티 탭(👥 커뮤니티) + 내부 QnA/Chat 플레이스홀더: PASS (정적 점검)
- ‘클래식 보기’(classic_view) 토글: PASS — true일 때 시작 시 📚 AI 학습/📊 AI 리포트 탭 자동 생성·선택 확인(정적/런타임 점검 병행)

주의: 위 항목들은 코드 수준/정적 점검(린트/구조 확인) 기준 PASS입니다. 직접 실행이 복구되는 즉시 화면 렌더링과 전환 동작을 런타임에서 재확인합니다.

## 타입/정적 점검
- main.py 주요 경로 타입 오류 해소: PASS (이전 사이클)
- dashboard_modern.py 수정 후 타입/린트 오류: 없음 (PASS)

## 멀티 거래소/거래 파이프라인
- 거래소별 섹션(제어/잔고/포지션/통계/로그) 생성 경로 일관성: 준비됨 (정적 점검 OK)
- 단일 비바이낸스 모드(예: Bybit만 활성) UI 동일성: 미수행 (다음 단계)
- 다중 거래소 동시 활성(예: Binance+OKX+Bitget) UI 동일성: 미수행 (다음 단계)

## 주식/ETF 실제 코드 상태 (중요)
- 대시보드 주식 서비스 탭 생성/연결: 구현됨
- 대시보드 주식 정보/거래 통계 탭: 플레이스홀더 제거, 연결 데이터 1차 표시 구현
- 증권사 설정 `api_type`/`api_version` 선택 및 동적 제한: 구현됨
- 팩토리에서 `api_type-api_version` 유효 조합 보정 후 어댑터 전달: 구현됨
- 키움 어댑터: backend 주입 기반 connect/get_balance/get_positions/get_realtime_price/place_order/get_open_orders 골격 구현
- **신한 어댑터**: REST SOL Trading API 전면 구현 완료 — OAuth 토큰/계좌조회/잔고/보유종목/주문/취소/미체결/거래내역 (8개 테스트 통과)
- **미래에셋 어댑터**: REST Open Trading API (UAPI) 전면 구현 완료 — OAuth2 토큰/잔고/보유종목/주문/취소/미체결/거래내역, ETF 코드 범위 105000~115999 (10개 테스트 통과)
- `trading/stock_analysis_service.py`: ETFMetrics, score_stock, summarize_portfolio, StockAnalysisService, build_ai_context(), 분석 로그 이벤트 — 27개 테스트 통과
- Mock 어댑터(`stock_mock_adapter.py`): 계좌/잔고/포지션/주문/ETF 지표(nav, tracking_error) 시뮬레이션 구현

## AI 연동 상태 (주식/ETF)
- AI 어시스턴트는 주식 서비스 컨텍스트를 읽고 증권사 보유/ETF 여부를 요약함
- ETF 보유 시 추적오차/NAV 괴리/거래대금 지표를 조건부로 문맥에 주입함
- `StockAnalysisService` 분석 로그 이벤트 추가: portfolio/etf/trade/analyze/ai_context 결과를 `stock_analysis` 카테고리로 기록
- 주의: 이 기능은 "설명/분석 보조" 경로이며, 실증권사 주문 자동화 완성과는 별개임

## AI 어시스턴트 음성 모듈 (베타 운영)
- 신규 모듈: `ui/widgets/ai_voice_module.py`
   - OS 기본 TTS 래퍼(초기): macOS `say`, Windows `powershell` 지원
   - STT 2차: `speech_recognition`이 설치된 환경에서 마이크 음성 인식 지원 (`transcribe_microphone`)
   - 미설치/비활성 환경에서는 `not_available` + 사유 코드(`voice_disabled`, `speech_recognition_not_installed`, `pyaudio_not_installed`) 반환
   - 기본값은 비활성(기존 UX 영향 없음)
- 위젯 연동: `ui/widgets/ai_assistant_widget.py`
   - 설정 키 `assistant_voice`(enabled/auto_tts/rate) 기반 초기화
   - `auto_tts=true`일 때 AI 메시지 출력 후 TTS 호출
   - `🎤 음성입력` 버튼 추가: STT 결과를 입력창에 주입
- 테스트: `tests/test_ai_voice_module.py`, `tests/test_assistant_voice_settings.py`, `tests/test_stock_analysis_service.py` 로그 검증 케이스

### 음성 배포 의존성 정합 (2026-05-04)
- `requirements.txt`: `SpeechRecognition` 유지, `PyAudio`는 Windows 전용 마커 적용
- `requirements_windows.txt`: `SpeechRecognition`, `pyaudio`, `pipwin` 포함
- `build_safe.py`: 음성 의존성 보정 설치 경로 추가
   - Windows: `pip install pyaudio` 실패 시 `pipwin install pyaudio` 재시도
   - 비-Windows: PyAudio 미설치 허용(마이크 STT만 비활성), TTS/텍스트 기능 정상 유지

## 테스터 배포 전 동시 검증 (AI 어시스턴트 포함)
아래 3개는 라이브 테스터 배포 전 필수 수행:
1) 핵심 회귀
   - `python -m pytest tests/test_stock_integration.py tests/test_stock_analysis_service.py -q`
2) AI 어시스턴트 + 음성 모듈
   - `python -m pytest tests/test_ai_voice_module.py tests/test_assistant_voice_settings.py -q`
3) 라이브 검증(테스터 환경)
   - Windows 키움 실계좌: `LIVE_STOCK_TEST=true python -m pytest tests/test_stock_integration.py -v -k "live and kiwoom"`
   - macOS/일반 테스터: 신한/미래에셋 중심 검증 + 키움 live skip 확인

### 스모크 테스트 결과 (직접 실행 스크립트)
- test_unified_system.py: PASS
   - 지원 거래소: {'futures': ['binance', 'bybit', 'okx', 'bitget'], 'spot': ['upbit', 'bithumb']}
   - 연결된 거래소: [] (API 키 미입력 시 의도된 동작)
   - 레버리지 clamp: 요청 200 → 적용 20
   - 최소 노셔널 보정: 0.000050 → 0.001000
   - 주문 성공 판정 샘플: [True, True, True, False]
- test_paper_flow.py: PASS
- test_multi_exchange_runtime.py: PASS
   - 케이스: ['bybit'], ['binance','okx'], ['binance','okx','bitget'] 모두 예외 없이 초기화/잔고/현재가 조회 OK
   - 페이퍼 주문 성공: status=success, simulated=True, symbol=BTCUSDT, qty=0.001, price≈27k
   - 활성 포지션: 빈 딕셔너리(예상 동작)

## 스크린샷(자리표시자)

아래 이미지는 캡처 완료 후 추가됩니다. 파일은 `docs/images/`에 저장됩니다. 상세 목록은 `SCREENSHOTS_CHECKLIST.md`를 참고하세요.

- ModernDashboard 메인: `images/modern_dashboard_main_dark.png` (현재 미보관)
- Classic View ON 설정: `images/settings_general_classic_view_on.png` (현재 미보관)
- Classic View 시작 후 AI 탭 자동 생성: `images/classic_view_ai_tabs_auto_created.png` (현재 미보관)
- 거래소 필터/Trend Summary: `images/blockchain_exchange_filter_trend_summary.png` (현재 미보관)
- 멀티 거래소 탭 라이프사이클: `images/multi_exchange_tabs_lifecycle.png` (현재 미보관)
- 커뮤니티 탭(플레이스홀더): `images/community_tab_placeholder.png` (현재 미보관)

## AI 어시스턴트/설정 흐름
- 어시스턴트가 설정 변경 → 대시보드/매니저에 반영: 코드 경로 준비됨, 런타임 검증 미수행 (다음 단계)

## 알려진 이슈/제약
- 일부 기능은 플레이스홀더(커뮤니티 QnA/Chat): “업데이트 준비중”, FastAPI/WebSocket 연동 주석 템플릿 포함

## 다음 단계 (즉시 수행)
1) 단일 거래소 모드 런타임 검증
   - settings.enabled_exchanges: ["bybit"] 같은 구성으로 실행 → Binance 탭이 생기지 않는지, 동일 섹션과 파이프라인으로 동작하는지 확인
2) 멀티 거래소 모드 런타임 검증
   - ["binance", "okx", "bitget"] 등 조합에서 각 거래소 탭이 동일 섹션으로 생성/갱신되는지 확인
3) 커뮤니티 탭 UI 동작 확인
   - 렌더링/탭 전환 시 예외 없음 확인, FastAPI/WebSocket 연동 시나리오 준비
4) AI 어시스턴트 설정 변경 흐름 검증
   - 어시스턴트에서 설정 변경 → refresh_after_settings_change → 잔고/상태/탭 갱신 경로 확인
5) 스모크 테스트 실행
   - test_unified_system.py, test_paper_flow.py를 paper 모드로 수행하여 거래 가드/파이프라인을 빠르게 검증

업데이트: 추후 테스트가 완료되는 즉시 본 문서에 “PASS/FAIL 및 로그 링크”를 추가하겠습니다.
## 2026-07-29 - v3.9.0.3 실행 모드·페이퍼 안전성·고급 계층 정합화

- 전체 자동 회귀: `1,147 passed, 6 skipped, 3 warnings`
- 신규 안전 회귀: LEARNING/PAPER/LIVE 우선순위, Binance 저수준 실주문 차단, Binance·Unified 페이퍼 포지션 격리, 증권 페이퍼 내부 체결, 고급 프리셋 상세값 deep merge, 항상 최상단 기본 OFF, 증권 고급 계층 연결
- Python 구문 검증: `main.py`, 설정/대시보드, Binance/Unified/증권 실행 경로 통과
- 경고 3건은 기존 `scripts/test_coin_selection*.py` 테스트가 `None` 대신 리스트를 반환하는 `PytestReturnNotNoneWarning`
- Windows EXE 빌드는 사용자 수행 범위로 남겼고 `deploy/release-manifest.json`은 `pending_windows_rebuild` 상태로 표시
## v3.9.1.9 PAPER 전진검증·근거형 AI 어시스턴트 회귀 (2026-08-24)

- 집중 회귀: PAPER 전용 전략 풀 등록/중지, 진행 상태 유지, 7일·최소 3체결 통과, 기본 전략 가상 청산 기록, 명시적 Web 런타임 키움 프로세스 프록시, 일반/심층 AI 포지션 근거 전달을 검증했습니다.
- 기존 v3.9.1.8 관련 집중 회귀와 합쳐 `148 passed`; React/TypeScript production build 49 modules를 확인했습니다.
- 전체 Python 회귀, Node 22 Windows production build, 새 Setup/업데이트, 키움/KIS 실계정, 7일 PAPER 및 실제 AI Provider 응답은 아래 테스트 계획의 외부 게이트입니다.
- 배포 상태: `pending_windows_rebuild`, `publish_ready=false`.
## v3.9.1.19 전략 검증 여권·패키지 무결성 소스 회귀 (2026-09-03)

- 실제 사용자 `01_STRUCTURE.noahstrategy`에서 브라우저가 소수형을 정수형으로 바꾼 두 위험 필드를 확인했고, IR·전체 패키지 해시를 모두 재검증하는 제한 복구를 통과했습니다.
- Binance 실행 범위로 저장된 구형 PAPER 행이 고유 UNIFIED key/version으로 귀속되고 Binance 거래소 근거에 나타나는 회귀를 추가했습니다.
- 컴파일러가 만든 실행 노드 없는 원문은 차단되고, 사용자가 명시적으로 재선언한 NoahAI 기본 진입 오버레이만 별도 검증 대상으로 허용되는 회귀를 추가했습니다.
- 집중 회귀 현황과 전체 빌드 결과는 [v3.9.1.19 검증 원장](archive/release/V39119_STRATEGY_PASSPORT_INTEGRITY_TEST_PLAN.md)에 최종 기록합니다.
- 집중 회귀 `35 passed`, 전체 Python 회귀 `1,995 passed, 8 skipped`, Web UI TypeScript/Vite production build를 통과했습니다.
- `세계 최초의 전략 검증 여권 생태계`라는 한정된 범주 비전을 daltrading 허브·가이드, NoahAI Labs 제품·LLM 안내, 클라이언트 대시보드 메뉴얼·AI 어시스턴트 지식에 동기화했습니다. 기존 백테스트의 발명이나 수익 보장을 뜻하지 않으며 현재 공개판·소스 후보·향후 마켓 기능을 구분합니다.
- daltrading 전략 허브 전체 회귀 `83 passed, 3 subtests passed`, NoahAI Labs production build `225 pages`, 클라이언트 관련 집중 회귀 `46 passed`와 Web UI TypeScript/Vite production build를 통과했습니다.
- daltrading `2628b73`은 EC2 운영 서버에 배포해 서비스 재시작·DB 마이그레이션·공개 전략 경로와 인증 경계를 확인했습니다. GitHub Actions 자동 배포는 저장소의 `EC2_HOST`, `EC2_USER`, `EC2_SSH_PRIVATE_KEY` 미설정 때문에 별도로 실패 중입니다.
- NoahAI Labs `39e45d1`은 Cloudflare Pages 운영 배포와 `noahailabs.com`의 전략 스튜디오·`llms.txt` 실제 응답을 확인했습니다.
- NoahAI 정보/IP 사이트 `e176de7`은 production build `45 pages`를 통과하고 EC2/PM2에 배포했으며 `info.noahai.net`·`ip.noahai.net`·기술 위키·`llms.txt`의 실제 응답을 확인했습니다.
- Windows v3.9.1.19 설치기·blockmap·`latest.yml`은 게시됐습니다. 6개 거래소 장시간 PAPER/실환경 E2E는 소급 완료로 표시하지 않고 후속 운영 관찰로 유지합니다.
