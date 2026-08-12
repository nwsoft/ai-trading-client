## v3.9.0.8 AI Custom Update Fix 4 소스 검증 (2026-08-11)

- 배포 신원: 현재 `deploy/release-manifest.json`은 `Fix 2`, SHA-256 `c1edaf84410f...`의 built EXE를 가리킵니다. Fix 2 제목 제보 화면은 Fix 3/4 설치 증거가 아니며 Fix 4 Windows 재빌드·게시가 필요합니다.
- Windows 메뉴 상한: CTkComboBox/OptionMenu 500개 생성 후 유휴 `TK_MENU=0`, 전체 설정창 생성·숨김·재열기 후 `TK_MENU=0` **PASS**. 선택 중에도 프로세스 전체 최대 1개 native 메뉴만 허용합니다.
- 탭/상태 정본: 금융 인텔리전스가 6개 거래소보다 앞에 위치, `거래소: 6곳 · 기준 BINANCE`, `자동매매: 정지 (0/6 실행)` 순수 계약 회귀 **PASS**.
- 사용자 AI 비용 사실확인: `data/260809_Teayu/ai_market_call_budget.json`에서 2026-07-24~08-09 매일 정확히 1,200회 소진, DeepSeek 화면 74,492 요청·57,134,137토큰과 증가 방향 일치 **CONFIRMED**
- 인과 경계: Provider 화면만으로 3.9.0.7만의 단독 원인은 확정하지 않음. 로컬 시장 원장 20,400회와 Provider 전체 74,492회의 차이는 시장분석 밖 호출·다른 경로/클라이언트 포함 가능 **OPEN TELEMETRY**
- AI 호출 회귀: level-trigger 후보/RSI 제거, 단순 새 캔들 로컬 처리, 30분 상태 캐시, 5분 미세변화 간격, 기존 고비용 설정 hard ceiling, 모든 자동 역할 영속 예산 **PASS**
- OMS 회귀: 암호화폐 명령 원자 선점·재시작 중복 차단, 거래소별 client-order ID 전달, 오류 분류, 모호한 청산 재주문 금지와 신규진입 중단 **PASS**
- 사용자 원장 복제 시뮬레이션: 기존 8월 10,800회는 `legacy_snapshot` 보존, Fix 4 카운터 240회에서 정지, 6개 거래소별 최대 40회 **PASS**
- Fix 4 집중·연관 회귀 `82 passed`; 전체 자동 회귀 `1,458 passed, 6 skipped, 0 failed`; 문서/버전 정합성·활성 소스 감사 **PASS**(활성 Python 349개, 구문 실패 0)
- Windows 외부 게이트: 새 Fix 4 EXE, 6개 거래소 client-order ID 수용, 타임아웃 직후 재시작, 주문/포지션 조정 후 재개, 장시간 PAPER/LIVE
- 현재 소스 배포 상태: `pending_windows_rebuild`; 공개 manifest의 직전 Fix 2 Windows 자산 `built`와 구분

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

- ModernDashboard 메인: ![placeholder](images/modern_dashboard_main_dark.png)
- Classic View ON 설정: ![placeholder](images/settings_general_classic_view_on.png)
- Classic View 시작 후 AI 탭 자동 생성: ![placeholder](images/classic_view_ai_tabs_auto_created.png)
- 거래소 필터/Trend Summary: ![placeholder](images/blockchain_exchange_filter_trend_summary.png)
- 멀티 거래소 탭 라이프사이클: ![placeholder](images/multi_exchange_tabs_lifecycle.png)
- 커뮤니티 탭(플레이스홀더): ![placeholder](images/community_tab_placeholder.png)

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
