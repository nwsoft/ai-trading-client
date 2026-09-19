# v3.9.1.24 Strategy Studio 가독성·Strategy Hub 접근 검증 원장

소스 후보: `3.9.1.24` / updater `3.9.124`  
작성일: 2026-09-09  
직전 공개판: `3.9.1.23`  
배포 상태: Windows 재빌드 전 (`pending_windows_rebuild`, `publish_ready=false`)

## 버전 불변성

- v3.9.1.23은 LIVE/PAPER 통계 정본, 비파괴 표시 기준, PAPER 일시정지·재개를 제공한 직전 공개판이다.
- v3.9.1.23의 공개 installer SHA-256은 `10183438bbb4b3316d340a916bc76c145b8214f739c43c24a7778731cd333f82`다.
- 아래 후속 변경은 v3.9.1.23 자산을 덮어쓰거나 같은 버전으로 재배포하지 않고 v3.9.1.24에서만 전달한다.
- 제품 버전 `3.9.1.24`, updater SemVer `3.9.124`, 설치 파일 `NoahAI-3.9.1.24-Setup.exe`, blockmap, `latest.yml`, 앱 화면과 Windows ProductVersion이 모두 일치해야 한다.

## v3.9.1.24 변경 범위

- 일반 기능 탭과 거래소·증권사 탭을 반응형 별도 그룹으로 유지한다.
- 낮은 화면에서도 `전략 스튜디오 실행 풀 없음` 상태와 기본 NoahAI PAPER 계속 운용 안내가 가려지지 않는다.
- Level 3·4 고급 JSON 확인 체크는 이름·책임·비우회 범위를 함께 표시한다.
- 최종 규칙 재검증 실패는 부족 조건·차단 이유·수정 방법·입력 예시와 AI 질문 연결을 제공한다.
- `전략 둘러보기`는 공개 허브, `내 전략 라이선스`는 브라우저 회원 세션이 필요한 화면으로 구분한다.
- daltrading 미로그인은 로그인 후 원래 라이선스 화면으로 복귀하고, API 클라이언트에는 UTF-8 JSON `401`을 유지한다.
- daltrading 제출은 1단계에서 서버가 패키지의 자산·현물/선물·기관·시장국면·검증 대상을 추출하고 2단계에서 같은 사용자가 범위와 권리를 확인한다. 수동 태그 누락·불일치는 차단하고 2단계 오류는 24시간 분석 초안과 작성값을 보존한다.
- 같은 strategy key의 다른 버전이 PAPER 검증 중일 때 실행 권한을 묵시적으로 교체하지 않고, 기존 버전 일시정지를 먼저 요구한다.
- 버전 카드에 저장된 시장국면·역할·청산·TP/SL·위험·적용 범위를 재확인하는 읽기 전용 실행 계약을 표시한다.
- 해당 strategy key/version의 PAPER 세부 체결만 계정 로컬 JSON으로 내보낸다. 공유 `.noahstrategy`와 허브 자동 전송에서 분리하고, 미기록 구형 필드는 0으로 표시하지 않는다.
- daltrading E0는 순위·0.0점이 아닌 신규 등록·검증 대기로 표시하고, 제작자 설명과 허브 검증 근거를 분리한다.

## 누적 계약

- v3.9.1.23의 LIVE/PAPER/LEARNING 원장 분리, 기간 통계, KRW/USDT 분리, 비파괴 표시 기준과 PAPER attempt 보존을 변경하지 않는다.
- Binance·Upbit·Bithumb·Bybit·Bitget·OKX와 키움·신한·미래에셋·한국투자의 실행·통계·주문 계약은 이번 UI/접근 패치로 달라지지 않는다.
- 공개 허브 로그인이나 제출 실패가 로컬 전략, PAPER 근거, LIVE 설정 또는 거래 원장을 수정하지 않는다.

## 소스 회귀

- [x] `VERSION-SOURCE` — Python 정본, Electron package/buildVersion, Windows version resource, Web fallback과 inventory가 `3.9.1.24` / `3.9.124`로 일치
- [x] `PREVIOUS-IMMUTABLE` — `deploy/version.txt`, 공개 manifest와 v3.9.1.23 설치 자산은 직전 공개판으로 보존
- [x] `STUDIO-RESPONSIVE` — 기관 탭 분리와 실행 풀 상태 가독성 source contract
- [x] `STUDIO-XAI` — 고급 JSON 확인과 재검증 세부 사유 source contract
- [x] `HUB-AUTH` — 공개 둘러보기/회원 라이선스 구분, 로그인 복귀와 API 401 계약
- [x] `HUB-DRAFT` — 서버 추출 범위, 2단계 사용자 확인, 수동 불일치 차단, 24시간 분석 초안 보존 계약
- [x] `PAPER-SIBLING-GRANT` — v1 검증 중 v2 시작 차단, v1 attempt·근거·열린 구간 보존, 명시 일시정지 후 v2 시작
- [x] `PAPER-EVIDENCE-EXPORT` — key/version·scope 격리, 보유시간·비용·진입 국면·신호 출처·수량 제한·TP/SL·Smart Exit·사유 필드, 개인/주문 식별자 제외
- [x] `VERSION-CONTRACT-VIEW` — 저장 버전 파라미터 읽기 전용 표시
- [x] `HUB-E0-CLARITY` — E0와 E2~E5 검증 랭킹 분리, 순위·0.0점 제거, 제작자 설명·서버 근거·기관별 결과 구분
- [x] `PYTHON-REGRESSION` — NoahAI 전체 `2,136 passed, 8 skipped`, 변경 집중 `66 passed`, daltrading 전체 `93 passed`
- [x] `WEB-BUILD` — TypeScript/Vite production build `50 modules`, `js-yaml` 4.3.2 보안 고정, npm 전체/production audit 취약점 0건. 로컬 Node 20.11.0은 빌드만 확인했으며 Windows 릴리스는 요구 버전 22.12 이상에서 재검증
- [x] `DOC-CONSISTENCY` — 버전·매뉴얼·AI 지식·릴리스 원장 정합 검사 (`PASS`)

현재 소스 fingerprint 참고값: `59c67cc3a82a4e67222d2be30cfb19672f4d290c0f317520a94c9957fadb9c74`. Windows 빌드 직전에 같은 스크립트로 다시 확정한다.

## Windows·운영 외부 게이트

- [ ] `WIN-BUILD` — 현재 source fingerprint로 엔진, `NoahAI-3.9.1.24-Setup.exe`, blockmap, `latest.yml` 생성
- [ ] `WIN-IDENTITY` — 파일 속성, 창 제목, 설정, 업데이트 화면이 모두 v3.9.1.24 표시
- [ ] `WIN-UPGRADE` — 공개 v3.9.1.23에서 v3.9.1.24 업데이트·안전 종료·재시작·설정/원장 보존
- [ ] `DISPLAY-E2E` — Windows 배율 100/125/150%, 1366×768·1920×1080에서 탭과 실행 풀 안내 확인
- [ ] `STUDIO-E2E` — 고급 JSON과 최종 재검증 오류를 실제 전략으로 재현해 설명·AI 질문·저장 차단 확인
- [ ] `HUB-BROWSER-E2E` — 미로그인→로그인→라이선스 복귀, 공개 둘러보기, 제출 실패 초안 보존 확인
- [ ] `VENUE-SMOKE` — 6개 거래소와 4개 증권사에서 기존 v3.9.1.23 실행·통계·PAPER 계약 비회귀 확인
- [ ] `KIWOOM-E2E` — Windows OpenAPI+ 조회·종료·LIVE/PAPER 통계의 v3.9.1.23 계약 비회귀 확인
- [ ] `KIS-E2E` — 토큰 재사용·호출 제한·LIVE/PAPER 통계의 v3.9.1.23 계약 비회귀 확인
- [ ] `BITHUMB-E2E` — KRW 현물 주문 단위·청산·비용·기간 통계 비회귀 확인
- [ ] `RECONCILE-E2E` — 기관 원장·거래 통계·운영 KPI·AI 리포트의 동일 범위 체크섬 확인
- [ ] `SPOT-FUTURES-PAPER` — 국내 KRW 현물과 해외 USDT 선물의 방향·수량·PAPER 분리 확인
- [ ] `REPORT-E2E` — 일간·주간·월간 상세와 통화별 합계 비회귀 확인
- [ ] `SOAK` — 6개 거래소·4개 증권사 24~72시간 조회·집계·재시작 지속성 확인

소스 회귀가 통과해도 Windows 설치본과 운영 브라우저 검증 전에는 v3.9.1.24를 공개 배포 완료로 표시하지 않는다.
