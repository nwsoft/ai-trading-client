## 2026-10-18 제품 이용 통계 후속 소스

공개 v3.9.2.17(426400d)의 PAPER 원장·백그라운드 대조·AI 모델 호환 변경을 보존한 채 선택 동의, 가명 계정, 실제 행동 이벤트, 영속 outbox·재시도·철회를 병합했습니다. 중앙 서버는 운영 반영 및 HTTPS 합성 수신·집계 검증을 마쳤습니다. 이 추가 기능은 이미 공개된 v3.9.2.17 설치본에는 포함되지 않았으며 릴리스 자산·태그는 변경하지 않았습니다. 실사용 성과는 미측정입니다.

운영의 기존 auth/KPI DB 경로는 유지하고 새 통계만 `DALTRADING_PRODUCT_METRICS_DB`로 분리합니다. 테스트·내부·미분류는 real 집계에서 제외하며 검증용 두 계정은 검증 후 비활성화했습니다.

# 제품 이용 통계 후속 구현 · 2026-10-18 KST

## 현재 결과
동의 화면, 실제 사용자 행동 연결, 계정별 영속 outbox, 재전송, 서버 receipt 중복 방지, 원래 행동 시각 집계, 테스트/내부/미분류 제외를 구현했다. 독립 체크아웃에서 빌드와 관련 검증을 마친 **소스 배포 후보**다. 운영 서버 배포·Windows 설치기 생성·실제 외부 사용자의 수신 검증을 완료했다는 뜻은 아니다.

원래 사용자·거래 DB, 설치본, 동기화 sources/는 수정하지 않았다. 신규 수집 데이터는 기존 거래 저장소와 분리된 outbox 및 별도 metrics DB에만 쓴다. 지표에 실사용으로 분류할 실제 계정이 제공되지 않았으므로 운영 사용자 수와 성과는 미측정이다.

## 구현 위치와 동작
- 설정 → 일반의 ‘제품 이용 통계 · 선택 동의’. 기본 OFF/체크 해제, 명시 확인 후 활성화, 철회 시 미전송/거부 이벤트 삭제. 일반 설정 저장이나 원격 연결 동의와 독립 저장한다. 마지막 수신 확인·미전송·거부·저장 실패 상태를 보여준다.
- 앱 열기와 활성 Strategy Studio 진입은 실제 렌더러 경계에서 전송한다. keepalive 화면의 백그라운드 poll은 이용으로 세지 않는다. 동일 화면의 React effect 재실행은 중복 억제한다.
- 서버 facade에서 성공한 전략 저장, 초안 검증 실행, 승인, 적용, PAPER 시작/재시작/일시정지, 명시 LIVE 시작에 연결했다. 실패한 승인이나 LIVE 확인 차단은 성공 활동으로 기록하지 않는다. XAI는 사용자가 ‘검증 근거·실행 조건 자세히 보기’를 열 때 기록한다.
- `paper_pause`는 검증 완료가 아니다. 현재 제품은 관찰 목표일 도달이 자동 종료를 뜻하지 않으므로 이를 `paper_complete`로 만들지 않았다. 사용 행동과 PAPER/LIVE의 검증 통과·실체결·수익은 별개이며 후자는 계속 미측정이다. 별도 복기 기능의 완료율도 이번 행동으로 추정하지 않는다.
- `<계정 data_dir>/product_metrics/<계정 해시>.sqlite3`: 거래 DB와 별도. 동의 전에는 생성하지 않는다. 사건 UUID·action/mode·발생시각·동의 버전만 보관하며 token/API키/계정 원문/전략 원문/손익은 보관하지 않는다. FULL sync로 commit 후 응답한다.
- 백그라운드 워커가 전달하고, HTTP 200 + accepted=true + 동일 UUID receipt를 받은 후에만 outbox에서 삭제한다. 통신 단절/401/403/서버 장애는 보존·재시도, 400/409 등 영구 거부는 보존하고 거부 건수를 노출한다. 앱 재실행·재로그인 시 이어서 전송한다. 자격증명은 기존 token 파일에서 현재 소유 계정을 확인해 전송 직전에 읽으며 outbox에 복사하지 않는다.
- 네트워크 잠금과 로컬 기록 잠금을 분리했다. 느린 서버가 전략 저장/거래 명령의 완료를 기다리게 하지 않는다. 철회는 이미 진행 중인 제한 시간 요청의 처리를 기다린 다음 동의 변경과 미전송 삭제를 확정한다.
- 정상 종료·gateway 종료에는 워커를 닫되 저장된 outbox를 비우지 않는다. 강제 종료 후 다음 실행에서도 committed 이벤트가 남는다. 계정 전환은 이전 워커를 닫고 계정별 파일/토큰 소유권을 분리한다.
- 중앙 endpoint는 기존 JWT의 활성/철회 검사를 재사용한다. 별도 metrics DB가 미설정이거나 auth DB의 별칭이면 수집을 거부한다. 가명화 키와 cohort 설정은 서버에서만 관리한다.
- 서버는 받은 시각과 별도로 원래 `occurred_at`을 저장하고 KST 집계에 사용한다. 90일 초과 또는 미래 5분 초과 시각은 거부한다. 클라이언트 시각이므로 기기 시계 오차는 품질 한계다.
- 기존 KPI의 짧은 receipt 정리에서 `product:` receipt를 제외했다. 오프라인 후 재시도가 3일을 넘겨도 중복 방지가 유지된다. 새 source는 기존 사용자 수 집계에서 제외된다.

## 검증 증거
- 클라이언트 관련 회귀: **146 passed** (`client-followup-tests.txt`). 신규 durable/서비스 연결, 실제 strategy pipeline, gateway 인증·Origin·의도 확인, 저장 실패, 원격/설정/기록 복구 회귀 포함.
- 서버 관련 회귀: **72 passed** (`server-followup-tests.txt`). 새 수신/집계, 기존 거래·계정·배치·300 합성 계정 회귀 포함. 총 Python **218 passed**. TestClient 의존성 사용 중단 예고는 있으나 실패 없음.
- 실제 loopback TCP/HTTP + 진짜 JWT 검증 + 별도 SQLite + 제품 outbox를 연결했다. 4개 **합성** 계정(real/test/internal/unknown)의 수신 4행, 수신 응답 유실 후 재시도 1회, 최종 real 활성 계정 1, 기존 사용자 집계 추가 0을 확인했다.
- 같은 시험에서 어제 발생한 오프라인 행동은 어제 구간에 1, 재접속한 오늘 구간에 0으로 집계됐다. 실제 워커의 장애→재연결 전송과 비활성 계정 수신 거부도 확인했다.
- 기존 사용자 행과 거래 표본의 내용 보존, read-only 보고서의 원본 해시 보존을 검사했다. 이 표본 보존 시험은 운영 DB 대조를 대신하지 않는다.
- 동의 패널 브라우저 시험: 기본 OFF, 체크 전 버튼 비활성, 명시 동의, 철회, 미전송 표시, 1440/390px 패널 가로 넘침 없음, page error 없음. `consent-ui-test.txt`, `consent-*.png`. 390px은 패널 fixture 검사이며 전체 데스크톱 앱의 모바일 인수를 뜻하지 않는다.
- TypeScript 검사 및 Vite production build 성공 (`ui-build.txt`). 기존 큰 번들 경고는 남아 있다. `client/webui/dist/`는 빌드 결과다.

## 보관·삭제
새 product source에만 적용되는 90일 일일 정리와 검증된 고객지원 삭제 도구를 추가했다. `product_kpi_maintenance.py`는 기본 dry-run이며 `--run`에서만 삭제한다. 과거 legacy KPI·사용자·거래 테이블은 대상이 아니다. 원시 활동·연결 receipt를 함께 정리한다. 계정별 삭제는 본인 확인 후 서버 가명키를 `--actor`로 지정한다. 백업의 잔여 데이터는 조직 백업 만료 정책에 맞춰 별도 관리한다.

`deploy/daltrading-product-kpi-maintenance.service/.timer`는 매일 실행하는 설치용 파일이다. 아직 운영 설치/실행하지 않았다. 서버 원시 이벤트는 90일 기준으로 매일 정리하며, 미전송 PC 이벤트는 수신 확인/동의 철회까지 보존한다. 서버가 너무 오래된 이벤트를 거부하면 PC는 누락 가능성을 거부 건수로 표시한다.

## 배포 순서와 보존 경계
1. `verification.json`의 기준 커밋·패치 SHA를 대조한다. client 기준은 공개 v3.9.2.16 소스, server 기준은 감사 당시 GitHub HEAD다. 기존 v3.9.2.17 로컬 유지보수 후보는 덮어쓰지 않았다. 최신 운영 브랜치에 적용할 때 `git apply --check` 또는 리뷰 브랜치 병합으로 선행 변경과 충돌을 확인한다.
2. 운영의 auth/metrics 실제 경로와 WAL을 포함한 일관 백업·복원 지점을 확인한다. DB 전체 덮어쓰기, 원래 data/·token·전략·거래 원장 복사는 하지 않는다. 소스 파일과 검증된 UI 빌드만 교체한다. 현재 코드의 additive view/receipt는 기존 KPI 저장 구조를 재사용한다.
3. `server/deploy/product-metrics.env.example`의 키를 기존 보호된 서비스 환경에 병합한다. 별도 metrics DB, 전용 random key, 가명계정→분류 JSON을 설정한다. 실제 키는 Git/로그에 남기지 않는다. 관측 기간 중 키를 변경하면 고유 계정 연결이 끊어지므로 별도 전환 절차가 필요하다.
4. 기본 분류는 unknown이다. 운영자가 확인한 외부 계정만 real로 등록한다. 내부·테스트·미분류는 집계에서 제외한다. 계정 이름 패턴으로 real을 추정하지 않는다. 분류의 효력일/근거를 기록하고, 이미 수신된 unknown을 무근거로 소급 real로 바꾸지 않는다.
5. 서버를 먼저 배포하고 endpoint/catalog·전용 DB·JWT·기존 관리자 집계 회귀를 확인한다. 그 후 동의 화면이 포함된 클라이언트를 배포한다. 새 공개 설치기에는 별도의 정식 버전/renderer 식별자를 부여해야 한다. **기존 v3.9.2.16 이름으로 재발행하지 않는다.** 이번에는 Windows 빌드/설치기/업데이터 자산을 생성하지 않았다.
6. 90일 정리 dry-run의 대상이 product source뿐인지 확인한 뒤 timer를 설치한다. 별도 metrics DB 경로가 서비스와 타이머에서 동일해야 한다. 타이머는 기존 KPI 정리 주기를 바꾸지 않는다.
7. 소수 allowlist의 실제 설치본에서 동의 OFF/ON, 행동, 오프라인, 강제 종료, 재실행, 수신 receipt, 철회, 다른 계정 로그인을 확인한다. 운영자 real/test/unknown 분류와 수신/거부/대기 건수를 맞춘다. 이 단계와 외부 HTTPS/TLS 경로, Windows 설치 인수는 아직 미확인이다.
8. 불일치와 잔여 outbox가 없음을 확인한 기간만 `--verified-coverage-start`로 보고한다. 첫 이벤트 수신 시각을 완전 수집 시작점으로 쓰지 않는다. 관측이 끝나지 않은 D7/D30이나 거래 검증 결과를 0으로 채우지 않는다.

롤백은 신규 endpoint 차단/키 비활성화와 timer 중지부터 한다. 이미 수신된 제품 행이 legacy 사용자 집계에 섞이지 않도록 filtered view와 보고서 호환 변경은 유지한다. 클라이언트 outbox는 삭제하지 않으며 사용자가 동의를 철회할 때만 미전송분을 지운다. 운영에서 생긴 이후 변경을 잃는 과거 auth DB 전체 복원은 하지 않는다.

## 보증 범위
로컬 HTTP 시험의 real 라벨은 운영 분류 로직을 검증하기 위한 합성 fixture다. 실제 사용자 수나 제품 성과가 아니다. 디스크 고장/저장 실패, 서버의 영구 거부, 사용자 철회, 행동 처리와 계측 commit 사이의 비정상 종료까지 ‘누락 0’이라고 보증하지 않는다. 저장 실패는 화면에 드러내고, committed 이벤트의 종료/재시도 누락과 중복을 방지한다. 기존 legacy 수집 경로의 원문 user/session ID·임의 metadata는 이번 새 opt-in 범위와 별개로 남아 있다.

## 로컬 재현
서버 전용 가상환경에 `server/requirements-product-kpi-test.txt`를 설치한다. server/에서 `python -m pytest tests/test_product_metrics.py tests/test_product_metrics_http_e2e.py tests/test_position_kpi.py tests/test_v39141_remote_metrics.py tests/test_referral_membership.py -q`를 실행한다. HTTP 통합 시험은 이 번들의 sibling client/를 읽으며 loopback에만 바인딩한다.

client/의 기존 의존성 환경에서 product_metrics_transport/services와 이번 검증 목록을 실행하고, webui/에서는 Node >=22.12와 잠금파일 의존성으로 `npm run build`를 실행한다. UI 패널은 `npm run dev -- --port 5196 --strictPort` 후 `PLAYWRIGHT_MODULE=/설치된/playwright/index.mjs node qa/check-product-metrics.mjs`로 재현한다. 전체 인수 결과는 번들 내 로그와 verification.json을 함께 확인한다.
