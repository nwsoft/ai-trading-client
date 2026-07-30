# NoahAI Client 공식 문서

> 기준: 2026-07-30 · 현재 배포 v3.9.0.2 / 업데이트 대상 v3.9.0.4  
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
| v3.9.0.4 거래·AI·설정 통합 감사 | `INTEGRATED_AUDIT_v3.9.0.4_20260729.md` |
| v3.9.0.4 설정 정본·실행 모드 | `SETTINGS_REFERENCE_v3.9.0.4.md` |
| AI 엔진/API 사용자 사용법 | `AI_API_USER_GUIDE.md` |
| AI Provider 기술 정본 | `AI_API_ARCHITECTURE.md` |
| v3.9.0.3 AI 엔진 확장 범위 | `AI_ENGINE_EXPANSION_PLAN_v3.9.0.3.md` |
| AI 커스텀·어시스턴트 수동 QA | `AI_CUSTOM_ASSISTANT_TEST_RUNBOOK_v3.9.0.2.md` |
| 기술 백서 | `NOAHAI_TECHNICAL_WHITEPAPER.md` |
| 사업 설명 | `BUSINESS_PROPOSAL_2026.md` |

## v3.9.0.4 업데이트 배포 대상 소스

- 설정 정본·LEARNING/PAPER/LIVE·분석 범위와 실주문 권한·레거시 정리: `SETTINGS_REFERENCE_v3.9.0.4.md`
- AI 제공사: OpenAI·DeepSeek·Anthropic Claude·Google Gemini 정식 선택, Kimi K3 어시스턴트 시험 지원
- 사용자 설정: API 키 보안 저장, 작업별 `{provider, model}`, 기존 문자열 자동 이전, 동적 모델 목록, 기준일 가격·공식 링크
- 모델 안전: 권장·계정 확인·미리보기·비권장·종료 구분, 종료/capability 불일치 저장 차단
- AI 커스텀 전사: 분석 Provider와 독립된 OpenAI transcription 프로필, 다중 화자 모델 선택
- 실연결 검증: 설정의 `실제 API 기능 검증`과 Windows 후보 빌드의 테스터별 Provider 키 E2E
- 주문 범위: 화면·분석·학습과 실제 주문 거래소 분리, 명시적 빈 주문 목록은 주문 0개
- 안정성: 숨은 탭 callback/API 조회 중지, 완료 작업 정리, UI 로그 회전
- 업데이트 P0: 포지션·주문 사전점검, TP·SL 또는 청산 체결 확인, SHA·코드서명, 영속 저널, health check·자동 복원·거래 재개 잠금
- 비용 제어: 시장분석 15분 상태 캐시·영속 호출예산, 포지션 크기 15분 캐시, 손실패턴 5분 캐시, 실패 120초 쿨다운
- 자산 후보: 거래소 지원 마켓 fail-closed, KOSPI·KOSDAQ·ETF 거래대금 우선·자산 모드별 균형 후보
- 검증: 전체 `1,200 passed, 6 skipped`; Windows 서명본·실제 API 키·거래소 실연결·장시간 실행 결과는 소스 회귀와 별도로 확인
- Teayu_02 운영 준비 상태: 암호화폐 6개 거래소와 AI Provider는 인증·IP·키 재입력 게이트 미통과
- Teayu_02 keyring·Binance 로딩·비정상 종료 조사: `INCIDENT_260729_TEAYU_02.md`
- 사용자 안내: `AI_API_USER_GUIDE.md`, `USER_GUIDE.md`, 앱 `사용자 매뉴얼 → 업데이트`
- 기술 정본: `AI_API_ARCHITECTURE.md`, `AI_ENGINE_EXPANSION_PLAN_v3.9.0.3.md`

## v3.9.0.2 AI 커스텀·레퍼럴·거래 통계 고도화

- 회원 운영: `레퍼럴` 무료회원, 서버 관리형 해외 제휴 거래소 정책, 동시 실행 거래소 KPI
- 처음 사용: 앱 `AI 커스텀 → 처음 사용법 AI에게 묻기`
- 결과 설명: 앱 `AI 커스텀 → 이 결과 AI에게 묻기`
- 실행 범위: SMA/EMA 20·50·200, ADX, ATR, 실제 Pine 교차, 비용 반영 검증, 코인 명시 청산
- 어시스턴트 안전: 허용 설정 최종확인, 저장 재검증, 사용자별 감사로그, 보호 작업 미실행
- 화면·사용법: 공통 기능 탭 스킨, 금융 인텔리전스 초보자 절차·AI 질문, 거래 통계 단일 스크롤
- 운용 지표: 거래 통계·AI 리포트의 통화별 실제 체결금액과 검증 가능한 평균 보유시간
- 최신 검증: 전체 `1,079 passed, 6 skipped`, daltrading `20 passed`, 문서 정합성 PASS
- 배포 경계: Windows 신규 EXE·실화면, 실제 YouTube URL, 실계좌 장시간 검증은 남음
- 구조·국면 추천·안전 경계: `AI_CUSTOM_STRATEGY_ARCHITECTURE.md`
- 대화형 전략·초보자 프리셋 후보: `AI_CUSTOM_CONVERSATIONAL_PRESETS_PLAN_v3.9.0.3.md`
- 사용자 사용법: `USER_GUIDE.md`, `AI_ASSISTANT_GUIDE.md`
- 테스트 순서·QA 계정 규칙: `AI_CUSTOM_ASSISTANT_TEST_RUNBOOK_v3.9.0.2.md`
- 완료·후속 범위: `UPDATE_PLAN.md`

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
| AI 커스텀 | `AI_CUSTOM_STRATEGY_ARCHITECTURE.md` | 실제 운용 기록은 `V3900_IMPLEMENTATION_RECORD_20260722.md` |
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

Windows 공식 배포물은 Windows 빌드 환경에서 생성합니다. v3.9.0.2는 이전 배포본이며 현재 v3.9.0.4 manifest는 `pending_windows_rebuild`입니다. 새 EXE의 크기·SHA·서명·설치·로그인·자동업데이트 E2E를 검증한 뒤 배포합니다.

## 문서 관리 규칙

- 같은 주제의 새 Markdown을 만들지 말고 위 정본에 통합합니다.
- 완료 보고, 일회성 분석, 과거 검증, 동기화 충돌본은 `docs/archive/`에 보관합니다.
- 이전 릴리스 체크리스트는 `archive/release/`, 문제 분석·완료 보고는 `archive/history/`에서만 조회합니다.
- `data/**/reports/*.md`는 런타임이 만든 분석 산출물이며 공식 제품 문서 수에 포함하지 않습니다.
- 사용자 체감 변경은 `CHANGELOG.md`, `UPDATE_PLAN.md`, `USER_GUIDE.md`, 인앱 매뉴얼을 함께 맞춥니다.
- 구현 여부는 코드와 테스트를 먼저 보고, 사업 문서나 과거 계획 문서만으로 판단하지 않습니다.

세부 정책은 `DOCUMENTATION_POLICY.md`를 따릅니다.
