# NoahAI 마스터 문서

> 최신 동기화: 2026-08-10 · 소스 대상 v3.9.0.8 AI Custom Update Fix 1, 대시보드 매뉴얼·어시스턴트 지식 반영·Windows 재빌드 전  
> 이 파일은 공식 문서의 지도입니다. 기능의 사실 판단은 코드 → 테스트 → 아래 정본 순서로 확인합니다.

## 공식 정본

| 구분 | 파일 | 책임 |
|---|---|---|
| 문서 진입점 | `docs/README.md` | 처음 읽을 문서와 빠른 실행 |
| 변경 이력 | `docs/CHANGELOG.md` | 버전별 사용자·개발 변경 |
| 개발 계획 | `docs/UPDATE_PLAN.md` | 완료·부분 완료·미완료 분리 |
| 사용자 가이드 | `docs/USER_GUIDE.md` | 설치 후 실제 사용 순서 |
| 레퍼럴·거래소 제휴 운영 | `daltrading/REFERRAL_MEMBERSHIP_OPERATIONS_20260727.md` | 제휴 신청·코드 연결·UID 귀속·회원등급 게이트 통합 정본(관련 저장소) |
| 인앱 매뉴얼 | `ui/widgets/user_manual_widget.py` | 앱 안의 쉬운 기능 설명 |
| 기술 구조 | `docs/ARCHITECTURE.md` | 모듈 구조와 책임 경계 |
| 거래 흐름 | `docs/TRADING_FLOW.md` | 코인·증권 주문 파이프라인 |
| 증권사 API 계약 | `docs/STOCK_BROKER_CONTRACTS_v3.9.0.5.md` | 공식 API 이름·설정 이전·PAPER/LEARNING/LIVE 권한 정본 |
| 활성 소스·격리 | `docs/SOURCE_QUARANTINE_MANIFEST_20260801.md` | 격리 사유·해시·빌드 제외·복원 기준 |
| 구조 종합 감사 | `docs/ARCHITECTURE_AUDIT_2026-08-01.md` | 거래소·증권·대시보드·빌드 최종 판정 |
| 개발 규칙 | `docs/DEV_GUIDE.md` | 회귀 방지와 개발 체크리스트 |
| AI API | `docs/AI_API_ARCHITECTURE.md` | 모델 호출과 공급자 경계 |
| 빌드 | `docs/BUILD_GUIDE.md` | 의존성·명령·산출물 검증 |
| 배포 | `docs/DEPLOY_CHECKLIST.md` | 배포 전후 운영 게이트 |
| 테스트 | `docs/TEST_STATUS.md` | 최신 자동·GUI 검증 근거 |
| AI 커스텀·어시스턴트 QA | `docs/AI_CUSTOM_ASSISTANT_TEST_RUNBOOK_v3.9.0.2.md` | 순서·계정·기대 결과 |
| AI 커스텀 핵심 고도화 | `docs/AI_CUSTOME_UPDATE_PLAN.md` | 시장 검증, Noah Strategy IR, Progressive Strategy UI, P0~P3와 KPI |
| AI 커스텀 제품 로드맵 | `docs/AI_CUSTOM_STRATEGY_OS_PRODUCT_ROADMAP.md` | 1~8단계와 현재 구현 경계 |
| 전략 여권·공유 | `docs/AI_CUSTOM_STRATEGY_SHARING_AND_PASSPORT.md` | `.noahstrategy`, 9개 목적별 탐색, 민감정보·유료 마켓 분리 |
| 대외 설명·비즈니스 정본 | `docs/NOAHAI_EXTERNAL_POSITIONING_AND_BUSINESS_PLAN_20260804.md` | NoahAI·AI 커스텀 공식 문구, 경쟁 비교, 고객별 설명, 무료→유료→B2B 사업 계층 |
| Teayu 테스터 진단 | `docs/TESTER_260728_STABILITY_EXCHANGE_REPORT.md` | 강제종료 후보·주문 범위·재검증 |
| Teayu_02 장애 조사 | `docs/INCIDENT_260729_TEAYU_02.md` | keyring·Binance 로딩·비정상 종료 증거와 v3.9.0.5 수정 |
| Teayu 거래소·통화 장애 조사 | `docs/INCIDENT_260802_TEAYU_V3906.md` | 6개 거래소 심볼 조회·무거래 순환 차단·KRW/USDT 리포트·200건·종료 진단 |

## v3.9.0.7 공개 설명 정본

- Fix Patch 3는 PyQt5·Kiwoom을 유지하면서 PyQt5·pandas 폴더의 중복 VC DLL을 제거하고 공식 VC143 x64 단일 세트를 EXE 루트에 넣습니다. ONNX는 실제 OCR 요청 때만 로드하고 빌드 전후 버전·중복·SHA-256을 검증합니다.
- Fix Patch 2의 로그 개인정보·파일 회전·PID 진단·설정창 복구 변경은 그대로 누적됩니다.
- 레퍼럴 거래소는 승인 전 API 입력·로컬 UID 검증까지만 허용하며 `관리자 전역 활성 ∩ 사용자별 verified UID 귀속`일 때만 선택·실행을 허용합니다.
- 유료 등급은 레퍼럴 UID 게이트 대상이 아닙니다. 비공식 재컴파일 클라이언트의 절대 차단은 현재 범위가 아닙니다.
- 신청·링크·UID 대사·운영·보안·QA의 단일 정본은 `daltrading/REFERRAL_MEMBERSHIP_OPERATIONS_20260727.md`입니다.
- daltrading 자동 교차검증·시간별 재검증과 관리자 암호화 Affiliate 키 설정은 배포됐습니다. 실제 Affiliate 전용 키 입력·연결 확인, 거래소 UID E2E와 Fix Patch 3 Windows EXE는 `pending_windows_rebuild`입니다.

## v3.9.0.6 공개 설명 정본

- 시작일: 2026-08-03
- 범위: 거래소 원본 심볼 성과 연결, 완료 거래 없는 종목의 순환 차단 제거, 통화별 리포트, 가져오기 건수 의미, 종료 진단
- 설정 DB 계약: 기존 `3.9.0.5` 설정 스키마 유지. 이번 제품 버전 변경으로 사용자 설정·거래 DB를 재작성하지 않음
- 배포 경계: 소스 후보이며 `pending_windows_rebuild`. Windows 설치·실계정·장시간 검증 전에는 배포 또는 거래소 완전 작동 완료가 아님

대외 설명은 `docs/NOAHAI_EXTERNAL_POSITIONING_AND_BUSINESS_PLAN_20260804.md`를 따른다. NoahAI는 `AI 금융 의사결정 인프라`, AI 커스텀은 `AI 전략 운영체제`, daltrading 전략 허브는 `검증 기반 무료 베타 탐색 계층`으로 구분한다. `TradingView 완전 상위호환`, `모든 Pine 지원`, `검증된 고수익 전략 마켓` 표현은 사용하지 않는다.
| 기술 백서 | `docs/NOAHAI_TECHNICAL_WHITEPAPER.md` | 기술 철학·구조 공식 설명 |
| 사업 설명 | `docs/BUSINESS_PROPOSAL_2026.md` | 구현과 로드맵을 구분한 사업 문서 |
| 문서 정책 | `docs/DOCUMENTATION_POLICY.md` | 중복 방지·정합성 규칙 |

## v3.9.0.5 공개 설명 정본

- 클라이언트 제품·실행 계약: `docs/UPDATE_PLAN.md`, `docs/AI_CUSTOM_STRATEGY_ARCHITECTURE.md`, `docs/TRADING_FLOW.md`
- 설치 사용자 안내: `docs/USER_GUIDE.md`, 앱 사용자 매뉴얼, 앱 AI 어시스턴트
- 공개 웹 기준: NoahAI Labs `/source/noahai-platform-v3904.md`와 네 언어 릴리스 노트
- 인증·다운로드 전 요약: daltrading 메인 홈의 실행 모드·AI 커스텀·다중 실행 안내
- 배포 경계: v3.9.0.5 Fix Patch 1은 공개 사용자 배포본입니다. Bybit 설정 동기화·Bithumb 체결 기록·서비스 복귀 잔고·자동업데이트 보강을 담은 Update Patch 1는 Windows 빌드·서명·설치·업데이트 복원·실연결 E2E 전까지 소스 후보입니다.

## v3.9.0.5 릴리스 묶음

- 버전 단일 소스: `config/app_version.py`
- 전체 변경 내역: `RELEASE_NOTES.md`, `docs/CHANGELOG.md`
- Windows 업데이트 패키지 사용자 요약: `deploy/release_notes.md`
- 사용자 사용법: `docs/USER_GUIDE.md`, 앱 `AI 커스텀 → 처음 사용법 AI에게 묻기`
- AI 실행 사용법: `USER_GUIDE_AI_EXECUTION.md`
- AI 커스텀 구조: `docs/AI_CUSTOM_STRATEGY_ARCHITECTURE.md`
- 어시스턴트 안전 변경: `docs/AI_ASSISTANT_GUIDE.md`
- AI 커스텀·어시스턴트 테스트: `docs/AI_CUSTOM_ASSISTANT_TEST_RUNBOOK_v3.9.0.2.md`
- AI 커스텀 IR·Progressive UI 사용자 시험/피드백: `docs/AI_CUSTOM_FEATURE_TEST_AND_FEEDBACK_GUIDE_20260809.md`
- 최신 검증 결과: `docs/TEST_STATUS.md`
- 기능·메뉴·데이터 상태: `docs/FINANCIAL_INTELLIGENCE_EXPANSION_PLAN_20260723.md`
- 검증 체크리스트: `docs/FINANCIAL_INTELLIGENCE_TEST_CHECKLIST_20260723.md`
- AI 커스텀 구현 기록: `docs/V3900_IMPLEMENTATION_RECORD_20260722.md`
- 빌드·배포 상태: `docs/BUILD_GUIDE.md`, `docs/DEPLOY_CHECKLIST.md`, `deploy/release-manifest.json`

v3.9.0.5 Fix Patch 1 Windows EXE는 현재 공개 자산입니다. 현재 Fix Patch 5 소스 manifest는 `pending_windows_rebuild`이며 새 Windows 빌드를 검증하기 전에는 Fix Patch 5 변경이 사용자에게 배포됐다고 보지 않습니다.

## 기능별 상세 문서

기능별 문서는 공통 정본에 넣기 어려운 계산·검증 세부사항이 있을 때만 유지합니다.

| 기능 | 현행 상세 문서 | 공통 정본 |
|---|---|---|
| 금융 인텔리전스 | `FINANCIAL_INTELLIGENCE_EXPANSION_PLAN_20260723.md` | `UPDATE_PLAN.md`, `USER_GUIDE.md` |
| AlphaArena | `ALPHA_ARENA_DEVELOPMENT.md` | `ARCHITECTURE.md`, 인앱 매뉴얼 |
| 코인 선정 | `COIN_SELECTION_GUIDE.md` | `TRADING_FLOW.md` |
| 대시보드 잔고·포지션 | `DASHBOARD_POSITION_SYSTEM.md` | `USER_GUIDE.md`, `DEV_GUIDE.md` |
| AI 커스텀 | `AI_CUSTOM_STRATEGY_ARCHITECTURE.md`, `AI_CUSTOME_UPDATE_PLAN.md` | `ARCHITECTURE.md` |
| 증권·ETF | `STOCK_BROKER_CONTRACTS_v3.9.0.5.md` | `UPDATE_PLAN.md`, `TEST_STATUS.md` |
| 생활금융 | `LIFE_FINANCE_GUIDE.md` | `UPDATE_PLAN.md`, `BUSINESS_PROPOSAL_2026.md` |
| 자동 업데이트 | `CLIENT_AUTO_UPDATE_ARCHITECTURE_20260626.md` | `BUILD_GUIDE.md`, `DEPLOY_CHECKLIST.md` |
| 레퍼럴·거래소 제휴 | `daltrading/REFERRAL_MEMBERSHIP_OPERATIONS_20260727.md` | `USER_GUIDE.md`, `ARCHITECTURE.md` |

## 보관 문서

`docs/archive/`는 삭제하지 않은 과거 증거입니다. 현행 기능 판단이나 새 개발의 출발점으로 사용하지 않습니다.

| 폴더 | 내용 |
|---|---|
| `archive/alpha_arena/` | 초기 설계, 프롬프트 분석, 거래 검증 보고 |
| `archive/build/` | 과거 빌드·경로 검증 보고 |
| `archive/dashboard/` | 버튼 분석, UI 초안, 구현 완료 기록 |
| `archive/coin/` | 2026-01 재선택 분석과 테스트 가이드 |
| `archive/conflicts/` | Synology 동기화 충돌본 |
| `archive/history/` | 과거 문제 분석, 수정·완료·검증 보고 |
| `archive/release/` | 이전 버전 업데이트 테스트 체크리스트 |

`data/**/reports/*.md`는 실행 중 생성되는 분석 결과이며 공식 문서가 아닙니다. 자동 생성 보고서는 보존 정책과 별도로 관리하고 `docs/`로 복사하지 않습니다.

## 변경 시 동기화

사용자가 체감하는 기능을 바꾸면 다음을 한 묶음으로 갱신합니다.

1. `CHANGELOG.md`: 무엇이 바뀌었는지
2. `UPDATE_PLAN.md`: 완료·부분 완료·미완료 상태
3. `USER_GUIDE.md`: 사용자가 무엇을 눌러야 하는지
4. `ui/widgets/user_manual_widget.py`: 앱 안의 쉬운 설명
5. `TEST_STATUS.md`: 검증 결과

빌드·배포가 관련되면 `BUILD_GUIDE.md`, `DEPLOY_CHECKLIST.md`, 버전 파일, 릴리스 매니페스트까지 함께 확인합니다.
