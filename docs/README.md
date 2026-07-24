# NoahAI Client 공식 문서

> 기준: 2026-07-24 · v3.9.0.1  
> 이 파일은 문서 진입점입니다. 현재 상태는 아래 정본 문서로 판단하고, `docs/archive/`와 `data/**/reports/`는 제품 설명 정본으로 사용하지 않습니다.

## 먼저 읽을 문서

| 목적 | 정본 |
|---|---|
| 전체 문서 지도 | `MASTER_DOCUMENTATION.md` |
| 버전별 변경 | `CHANGELOG.md` |
| 사용자 사용법 | `USER_GUIDE.md` |
| 앱 안의 쉬운 설명 | `ui/widgets/user_manual_widget.py` |
| 개발 계획·완료/미완료 | `UPDATE_PLAN.md` |
| 기술 구조·책임 경계 | `ARCHITECTURE.md` |
| 거래 실행 흐름 | `TRADING_FLOW.md` |
| 개발 규칙 | `DEV_GUIDE.md` |
| 빌드 | `BUILD_GUIDE.md` |
| 배포 전후 점검 | `DEPLOY_CHECKLIST.md` |
| 최신 테스트 근거 | `TEST_STATUS.md` |
| 기술 백서 | `NOAHAI_TECHNICAL_WHITEPAPER.md` |
| 사업 설명 | `BUSINESS_PROPOSAL_2026.md` |

## v3.9.0.1 금융 인텔리전스

- 사용자 동선: `USER_GUIDE.md`와 앱의 `사용자 매뉴얼 → 금융 인텔리전스`
- 기능·메뉴·데이터 상태: `FINANCIAL_INTELLIGENCE_EXPANSION_PLAN_20260723.md`
- 검증 범위: `FINANCIAL_INTELLIGENCE_TEST_CHECKLIST_20260723.md`
- 릴리스 준비: `BUILD_GUIDE.md`, `DEPLOY_CHECKLIST.md`, `TEST_STATUS.md`

## 기능별 상세 정본

| 영역 | 정본 | 보충 |
|---|---|---|
| AlphaArena | `ALPHA_ARENA_DEVELOPMENT.md` | 과거 설계·검토본은 `archive/alpha_arena/` |
| 코인 선정 | `COIN_SELECTION_GUIDE.md` | 실행 흐름은 `TRADING_FLOW.md` |
| 대시보드 잔고·포지션 | `DASHBOARD_POSITION_SYSTEM.md` | 과거 UI 초안은 `archive/dashboard/` |
| 증권·ETF | `STOCK_ETF_IMPLEMENTATION_STATUS_20260423.md` | 테스트는 `STOCK_ETF_TEST_CHECKLIST_20260118.md` |
| AI 커스텀 | `AI_CUSTOM_STRATEGY_ARCHITECTURE_v3.9.0.0.md` | 실제 운용 기록은 `V3900_IMPLEMENTATION_RECORD_20260722.md` |
| 금융 인텔리전스 | `FINANCIAL_INTELLIGENCE_EXPANSION_PLAN_20260723.md` | 검증 체크리스트와 함께 사용 |

## 실행과 빌드

개발 환경에서 실행:

```bash
python3 main.py
```

안전 빌드:

```bash
python build_safe.py --platform windows
python build_safe.py --platform macos
python build_safe.py --platform linux
```

Windows 공식 배포물은 Windows 빌드 환경에서 생성합니다. v3.9.0.1 EXE가 새로 생성되기 전에는 `deploy/release-manifest.json`의 `pending_windows_rebuild` 상태를 유지하며, 과거 EXE의 이름만 바꿔 배포하지 않습니다.

## 문서 관리 규칙

- 같은 주제의 새 Markdown을 만들지 말고 위 정본에 통합합니다.
- 완료 보고, 일회성 분석, 과거 검증, 동기화 충돌본은 `docs/archive/`에 보관합니다.
- 이전 릴리스 체크리스트는 `archive/release/`, 문제 분석·완료 보고는 `archive/history/`에서만 조회합니다.
- `data/**/reports/*.md`는 런타임이 만든 분석 산출물이며 공식 제품 문서 수에 포함하지 않습니다.
- 사용자 체감 변경은 `CHANGELOG.md`, `UPDATE_PLAN.md`, `USER_GUIDE.md`, 인앱 매뉴얼을 함께 맞춥니다.
- 구현 여부는 코드와 테스트를 먼저 보고, 사업 문서나 과거 계획 문서만으로 판단하지 않습니다.

세부 정책은 `DOCUMENTATION_POLICY.md`를 따릅니다.
