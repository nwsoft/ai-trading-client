# v3.9.1.10 PAPER Position, Statistics & Notifications 검증 계획

공개 v3.9.1.9 자산은 불변으로 보존합니다. 이 문서는 v3.9.1.10 소스, Windows 후보, 실제 화면·장시간 PAPER·외부 알림 증거를 분리하며 모든 외부 행이 끝나기 전에는 `publish_ready=false`를 유지합니다.

## 소스·자동 회귀

- [x] SOURCE — Web 설정의 `focus/multi`, `max_positions`, 6개 거래소 override 동기화
- [x] SOURCE — Binance 네이티브와 통합 거래소의 LIVE/PAPER 공통 제한 정책
- [x] SOURCE — PAPER/LEARNING 상한 계산에서 과거 LIVE 수동·외부 포지션을 제외하고 런타임 가상 포지션만 집계
- [x] SOURCE — 실계정 포지션과 런타임 PAPER 포지션의 응답 필드 분리
- [x] SOURCE — 거래소별 LEARNING/PAPER/LIVE 모드 분리와 기존 workspace 폴링 안의 메모리 전용 PAPER 포지션 조회
- [x] SOURCE — 엄격한 Gateway 런타임 계약이 거래소별 `execution_modes`를 거부하지 않고 Web UI까지 전달
- [x] SOURCE — PAPER 청산 수·승률·순손익·수수료와 실거래 통계 분리
- [x] SOURCE — 가상 포지션·PAPER 이력 내부 스크롤과 활성 전략 PAPER 안내
- [x] SOURCE — append-only PAPER 원장 최근 범위 tail-read
- [x] SOURCE — 100MiB 초과 PAPER 원장에서 최근 500건을 20회 연속 갱신해도 전체 파일이 아니라 회당 최대 128KiB, 총 최대 2.5MiB만 읽는 결정적 I/O 상한 회귀
- [x] SOURCE — AI 어시스턴트 일반 안내의 설정·시장·성과 빠른 질문이 서로 다른 정본 답변을 반환하고 외부 Provider를 호출하지 않음
- [x] SOURCE — AI 어시스턴트가 암호화폐·증권 PAPER 질문에서 stale LIVE 저장소가 아닌 현재 가상 포지션과 최근 사이클 메트릭을 사용
- [x] SOURCE — AI 어시스턴트가 질문에 명시한 거래소·증권사를 현재 탭보다 우선하고 포지션 없는 추세 질문을 시장 신호로 분류
- [x] SOURCE — Windows 빌드·게시가 하나의 교차 플랫폼 지문 계산기를 사용하고 Trader·통합 Trader·포지션 정책·AI 커스텀·Gateway·WebUI·패키지 매뉴얼 변경을 모두 감지
- [x] SOURCE — Windows/Electron·one-file engine 프로세스 트리와 Gateway 런타임/workspace/설정/AI 커스텀 P95, 6개 거래소 실행·PAPER 모드·가상 포지션 상태를 함께 기록하는 장시간 모니터 및 실패 폐쇄 판정
- [x] SOURCE — Web 조회 계층의 SQLite read-only 연결을 트랜잭션 종료가 아닌 명시적 `close()` 계약으로 통일해 반복 workspace·통계 조회의 `trading.db`/WAL/SHM 핸들 누적 차단
- [x] SOURCE — Binance PAPER 가상 진입이 선택된 AI 커스텀 이름·전략 키·버전 ID를 포지션에 보존하고, TP/SL 가상 청산이 같은 버전으로 PAPER 원장에 귀속
- [x] SOURCE — 전역 PAPER 런타임 풀이 적용 중 V1(`standard`)과 전진검증 후보(`paper_validation`)를 함께 엔진에 전달하되 상태를 분리
- [x] SOURCE — Discord/Telegram 설정·write-only 자격증명·상태·테스트·Telegram 대화방 자동 찾기 Gateway 계약
- [x] SOURCE — 공식 HTTPS 대상 제한, timeout/retry/cooldown, bounded queue, 계정 전환 세대 격리 및 거래 루프 비차단 계약
- [x] SOURCE — 가드레일 중단·손실 경고·시장국면·런타임 이벤트와 사용자 요청 AI 리포트 발송 연결
- [x] SOURCE — 전체 Python 회귀 `1804 passed, 8 skipped`
- [x] SOURCE — React/TypeScript production build 및 문서·Web parity·설정/어시스턴트 계약 감사

## 로컬 Web 실제 렌더

- [x] LOCAL-WEB — Binance PAPER 화면에서 `가상 포지션` 6개 fixture와 PAPER 이력 6건이 카드 내부 스크롤로 동작
- [x] LOCAL-WEB — PAPER 모드에서 `가상 거래 통계`가 자동 표시되고 실거래 통계는 동시에 노출되지 않음
- [x] LOCAL-WEB — 적용 중 `추세 따라가기 V1`에 `앱 PAPER에서는 가상 실행`·`적용 해제`가 표시되고 중복 `PAPER 전진검증 시작`은 미노출
- [x] LOCAL-WEB — Binance PAPER 거래소 제어 카드가 런타임 `active_custom_strategies`의 `추세 따라가기 V1`을 직접 읽어 `AI 커스텀 적용`과 `적용 중 버전은 PAPER에서 자동 실행 · 재적용 불필요`를 표시하며, PAPER 검증 후보는 `별도`로 구분
- [x] LOCAL-WEB — 같은 실제 렌더에서 `PAPER · 3개 활성 / 다중 상한 3`, `가상 포지션`, `가상 거래 통계`, `종료 이력 2건 · 활성 수와 무관`을 동시에 확인
- [x] LOCAL-WEB — 실제 `/api/v1/runtime/snapshot` 500 재현으로 발견한 `execution_modes` Gateway 계약 누락 수정 후 정상 렌더
- [x] LOCAL-WEB — 설정 모달에 `알림·리포트` 9번째 탭, Discord/Telegram 단계형 연결 UI와 1440px 2열·900px 1열 반응형 렌더 확인
- [x] LOCAL-WEB — `활성/상한`과 상한 초과 시 `신규 진입 차단`, PAPER 종료 이력의 `활성 수와 무관` 안내 렌더
- [x] LOCAL-PERF — 100MiB sparse 과거 구간과 최근 600건을 가진 원장에서 20회 연속 최근 500건 조회가 0.04초 안에 통과하고 모든 회차가 정확한 `event-100..599` 범위를 반환
- [x] LOCAL-SOAK-SMOKE — 실제 로컬 Gateway와 추가 프로세스 루트 HTTP 1회 샘플에서 런타임 6.08ms·Binance workspace 6.54ms·설정 6.35ms·AI 커스텀 1.59ms·합산 RSS 88.20MB로 PASS하고 결과에 Gateway 토큰이 없음을 확인
- [x] LOCAL-STRESS — 실제 로컬 Gateway 6개 거래소 720주기·5,328 HTTP 요청에서 실패 0, RSS 증가 5.51MB, 스레드·파일 디스크립터 증가 0, 런타임 P95 1.71ms, workspace 최대 P95 6.20ms, 설정 6.41ms, AI 커스텀 1.77ms 확인

위 fixture의 활성 6개 포지션은 스크롤 UI를 강제로 검증하기 위한 합성 데이터입니다. 집중 1·다중 기본 3 상한의 실제 실행 증거가 아니며, 해당 상한은 아래 Windows/PAPER E2E 행에서 별도로 검증합니다.

사용자 제공 v3.9.1.9 화면은 Binance 카드의 `PAPER · 1개 활성`과 아래 `3건 표시`, Bithumb의 긴 `가상 거래내역`을 보여 줍니다. 아래 여러 줄은 활성 포지션이 아니라 종료된 PAPER 청산 이력이므로 3개 상한 초과 증거가 아닙니다. 다만 구분이 약했던 UI는 위 LOCAL-WEB 표시로 보강했습니다.

## Windows 후보

- [ ] `WIN-BUILD` — Windows x64에서 `NoahAI-3.9.1.10-Setup.exe`, blockmap, `latest.yml(3.9.110)`, engine sidecar를 같은 source fingerprint로 새로 생성하고 SHA-256을 확정한다.
- [ ] `WIN-UPGRADE` — 깨끗한 설치와 공개 v3.9.1.9에서의 자동 업데이트·안전 종료·재시작·롤백·제거를 확인한다.
- [ ] `KIWOOM-E2E` — 키움 OpenAPI+ 별도 프로세스의 로그인·조회·시작·정지·재시작과 COM 스레드 경계를 확인한다.
- [ ] `KIS-E2E` — KIS 실전/모의 계정의 토큰·잔고·국내주식·ETF 현재가 경로를 확인한다.
- [ ] `BITHUMB-E2E` — Bithumb 현물의 보유·미체결·체결 조회와 종목 필수 계약을 확인한다.
- [ ] `RECONCILE-E2E` — 거래소 확인 체결·NoahAI 관리 포지션·PAPER 원장이 서로 섞이지 않는지 대조한다.
- [ ] `SPOT-FUTURES-PAPER` — Upbit·Bithumb 현물과 Binance·Bybit·OKX·Bitget 선물 PAPER의 방향·수량·청산·포지션 상한을 확인한다.
- [ ] `REPORT-E2E` — 가상 거래 통계와 AI 리포트가 PAPER/LIVE 및 KRW/USDT를 잘못 합산하지 않는지 확인한다.
- [ ] `ASSISTANT-PROVIDER` — 설치본에서 일반 안내 빠른 질문이 외부 호출 없이 서로 다른 정본 답변을 내고, 명시적 심층분석 1건은 실제 Provider에 구조화 포지션·신호 근거를 전달하는지 확인한다.
- [ ] `DISCORD-E2E` — Windows 설치본에서 실제 Discord Webhook 저장 → 테스트 수신 → 재시작 보존 → 가드레일/PAPER 이벤트 수신을 확인한다.
- [ ] `TELEGRAM-E2E` — 실제 Bot Token 저장 → `/start` → 개인/그룹 대화방 자동 찾기 → 테스트 수신 → 재시작 보존을 확인한다.
- [ ] `NOTIFICATION-ISOLATION` — 메신저 timeout·429·5xx·네트워크 단절 중에도 거래 루프·설정·AI 커스텀 P95가 상한을 넘지 않고 큐가 무제한 증가하지 않는지 확인한다.
- [ ] `NOTIFICATION-REDACTION` — 설정 API·로그·지원 번들·크래시 출력에 Discord URL, Bot Token, Chat ID 원문이 없고 계정 전환 전 대기 메시지가 새 계정으로 전송되지 않는지 확인한다.
- [ ] `SOAK` — 6개 거래소 PAPER를 24~72시간 실행해 메모리·원장 tail-read·화면 갱신·설정·AI 커스텀·안전 종료를 확인한다.
- [ ] OPEN — manifest source fingerprint와 네 자산 SHA-256 일치
- [ ] OPEN — 설정 집중/다중/고급 2개 저장 → 닫기 → 재열기 → 앱 재시작 유지
- [ ] OPEN — Windows 100%/125%/150% DPI에서 가상 포지션·통계·이력 카드 스크롤과 글자 잘림 없음
- [ ] OPEN — Windows 100%/125%/150% DPI에서 알림 탭 입력·단계 버튼·상태·오류 문구가 잘리거나 겹치지 않음

## 실제 PAPER·장시간 검증

- [ ] OPEN — Binance PAPER 집중 운용에서 stale 3 설정이 있어도 활성 1개 초과 신규 진입 차단
- [ ] OPEN — Bybit·OKX·Bitget 통합 PAPER에서 집중 1, 다중 기본 3, 고급 2 상한 확인
- [ ] OPEN — Upbit·Bithumb 현물 PAPER 가상 포지션과 실계정 보유자산을 혼합 표시하지 않음
- [ ] OPEN — 여러 거래소 합계는 거래소별 상한의 합일 수 있음을 화면·매뉴얼과 대조
- [ ] OPEN — 실제 설치본·실시간 시세에서 적용 중 AI 커스텀 V1이 전역 PAPER에서 별도 재적용 없이 선택·가상 청산 귀속 (소스 진입→청산 귀속 회귀는 PASS)
- [ ] OPEN — PAPER 전진검증 후보가 최종 적용 전략과 별도 상태로 집계
- [ ] OPEN — 100MB 이상 PAPER 원장에서 6개 거래소 24시간 실행 중 workspace 갱신 P95와 설정·AI 커스텀 응답 지연 확인
- [ ] OPEN — Windows 설치 후보 24~72시간 종료 시 engine/Electron 프로세스 트리 파일 핸들 증가가 상한 이내이고 `trading.db` 연결이 누적되지 않음
- [ ] OPEN — PAPER 통계가 실거래 체결·실계정 손익을 포함하지 않고 최근 원장 범위 안내와 일치
- [ ] OPEN — PAPER 시장국면·손실 경고·가드레일 중단 알림이 실제 거래 이벤트와 1:1로 대조되고 cooldown 동안 중복되지 않음
- [ ] OPEN — AI 리포트 `연동 채널로 보내기`가 선택 기간과 거래소를 유지하며 KRW와 USDT를 환율 없이 합산하지 않음

## 배포 판정

- Windows 후보 생성만으로 공개하지 않습니다.
- 위 OPEN 행을 동일 설치 후보에서 확인하고 source fingerprint가 유지될 때만 게시 검토합니다.
- 같은 `v3.9.1.9` 태그나 기존 자산을 교체하지 않습니다.
