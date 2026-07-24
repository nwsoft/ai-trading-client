# NoahAI 마스터 문서

> 최신 동기화: 2026-07-24 · v3.9.0.1  
> 이 파일은 공식 문서의 지도입니다. 기능의 사실 판단은 코드 → 테스트 → 아래 정본 순서로 확인합니다.

## 공식 정본

| 구분 | 파일 | 책임 |
|---|---|---|
| 문서 진입점 | `docs/README.md` | 처음 읽을 문서와 빠른 실행 |
| 변경 이력 | `docs/CHANGELOG.md` | 버전별 사용자·개발 변경 |
| 개발 계획 | `docs/UPDATE_PLAN.md` | 완료·부분 완료·미완료 분리 |
| 사용자 가이드 | `docs/USER_GUIDE.md` | 설치 후 실제 사용 순서 |
| 인앱 매뉴얼 | `ui/widgets/user_manual_widget.py` | 앱 안의 쉬운 기능 설명 |
| 기술 구조 | `docs/ARCHITECTURE.md` | 모듈 구조와 책임 경계 |
| 거래 흐름 | `docs/TRADING_FLOW.md` | 코인·증권 주문 파이프라인 |
| 개발 규칙 | `docs/DEV_GUIDE.md` | 회귀 방지와 개발 체크리스트 |
| AI API | `docs/AI_API_ARCHITECTURE.md` | 모델 호출과 공급자 경계 |
| 빌드 | `docs/BUILD_GUIDE.md` | 의존성·명령·산출물 검증 |
| 배포 | `docs/DEPLOY_CHECKLIST.md` | 배포 전후 운영 게이트 |
| 테스트 | `docs/TEST_STATUS.md` | 최신 자동·GUI 검증 근거 |
| 기술 백서 | `docs/NOAHAI_TECHNICAL_WHITEPAPER.md` | 기술 철학·구조 공식 설명 |
| 사업 설명 | `docs/BUSINESS_PROPOSAL_2026.md` | 구현과 로드맵을 구분한 사업 문서 |
| 문서 정책 | `docs/DOCUMENTATION_POLICY.md` | 중복 방지·정합성 규칙 |

## v3.9.0.1 릴리스 묶음

- 버전 단일 소스: `config/app_version.py`
- 사용자 사용법: `docs/USER_GUIDE.md`, 앱 `사용자 매뉴얼 → 금융 인텔리전스`
- 기능·메뉴·데이터 상태: `docs/FINANCIAL_INTELLIGENCE_EXPANSION_PLAN_20260723.md`
- 검증 체크리스트: `docs/FINANCIAL_INTELLIGENCE_TEST_CHECKLIST_20260723.md`
- AI 커스텀 구현 기록: `docs/V3900_IMPLEMENTATION_RECORD_20260722.md`
- 빌드·배포 상태: `docs/BUILD_GUIDE.md`, `docs/DEPLOY_CHECKLIST.md`, `deploy/release-manifest.json`

Windows EXE를 새로 만들기 전 릴리스 매니페스트의 `pending_windows_rebuild`는 정상적인 차단 상태입니다. 과거 EXE의 파일명만 바꾸어 v3.9.0.1로 배포하지 않습니다.

## 기능별 상세 문서

기능별 문서는 공통 정본에 넣기 어려운 계산·검증 세부사항이 있을 때만 유지합니다.

| 기능 | 현행 상세 문서 | 공통 정본 |
|---|---|---|
| 금융 인텔리전스 | `FINANCIAL_INTELLIGENCE_EXPANSION_PLAN_20260723.md` | `UPDATE_PLAN.md`, `USER_GUIDE.md` |
| AlphaArena | `ALPHA_ARENA_DEVELOPMENT.md` | `ARCHITECTURE.md`, 인앱 매뉴얼 |
| 코인 선정 | `COIN_SELECTION_GUIDE.md` | `TRADING_FLOW.md` |
| 대시보드 잔고·포지션 | `DASHBOARD_POSITION_SYSTEM.md` | `USER_GUIDE.md`, `DEV_GUIDE.md` |
| AI 커스텀 | `AI_CUSTOM_STRATEGY_ARCHITECTURE_v3.9.0.0.md` | `ARCHITECTURE.md` |
| 증권·ETF | `STOCK_ETF_IMPLEMENTATION_STATUS_20260423.md` | `UPDATE_PLAN.md`, `TEST_STATUS.md` |
| 생활금융 | `LIFE_FINANCE_GUIDE.md` | `UPDATE_PLAN.md`, `BUSINESS_PROPOSAL_2026.md` |
| 자동 업데이트 | `CLIENT_AUTO_UPDATE_ARCHITECTURE_20260626.md` | `BUILD_GUIDE.md`, `DEPLOY_CHECKLIST.md` |

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
