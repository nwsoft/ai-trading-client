# NoahAI Client Docs (재테크 금융 AI 플랫폼)

문서는 `noahai_client/docs/`에서 일괄 관리합니다. 백업 하위 `docs/`는 과거 스냅샷이며 최신이 아닙니다.

### 문서끼리 맞추기 (정합성)

- **`DOCUMENTATION_POLICY.md`**: 코드 → CHANGELOG → 아키텍처 → 인앱 메뉴얼 → USER_GUIDE → 화이트페이퍼 → 사업기획서 순의 **신뢰도 계층**, 버전 올릴 때 **동기화 체크리스트**.
- **인앱 사용자 메뉴얼**: `ui/widgets/user_manual_widget.py` — 최종 사용자 톤·책임 고지; 기술 세부는 `ARCHITECTURE.md`·`TRADING_FLOW.md`와 충돌 없게 유지.

## 🚀 NoahAI: 재테크 금융 AI 플랫폼으로의 진화

NoahAI는 **암호화폐 자동거래**를 시작으로, **종합 재테크 금융 AI 플랫폼**으로 확장하고 있습니다.

### 📌 증권/ETF 최신 구현 상태 빠른 확인
- 개발 상태 정본: `STOCK_ETF_CURRENT_STATUS_20260118.md` (상단 "최신 기준" 섹션)
- 설계 결정/로드맵: `STOCK_ETF_ARCHITECTURE_DECISION_20260423.md`
- 테스트 기준: `STOCK_ETF_TEST_CHECKLIST_20260118.md` + `tests/test_stock_integration.py`
- 변경 이력 기준점: `CHANGELOG.md` 최상단 2026-04-23 항목

### 개발 의의 (Why NoahAI Was Created)

NoahAI는 단순한 기술적 혁신을 넘어, **실제 사용자들이 겪는 근본적인 문제들을 해결하기 위해** 만들어졌습니다:

- **정보 격차 해소**: 전문가 수준의 시장 분석을 누구나 접근 가능하게
- **스트레스 해소**: 24시간 모니터링 부담을 AI에게 위임
- **시니어·접근성**: 대화형 UX·향후 음성(STT/TTS) 등은 로드맵·단계 공개 축(공개 저장소 기준 전면 음성 통합은 필수 아님 — 인앱 메뉴얼·`DOCUMENTATION_POLICY.md` 정합 절 참고)
- **사고 방지**: 자동 리스크 관리로 인간의 실수 방지
- **인간의 한계 초월**: AI가 할 수 있는 것을 인간 대신 수행 (24/7 모니터링, 수백 개 지표 동시 분석, 감정 없는 판단)

### 현재 핵심 상태
- UI: CustomTkinter-only (PyQt/PySide/Qt 제거)
- 탭: 서비스/거래소 하위 탭 라이프사이클 정리(활성만 생성/비활성 제거), 기본 로그 탭 보장
- 패키징: PyInstaller 스펙에서 Qt/Jupyter/대형 과학 패키지 제외
- 실시간: Binance WebSocket 매니저 API 통일 (subscribe_symbol/unsubscribe_symbol, get_latest_*)
- 실행: macOS에서 소스 직접 실행 지원, 실패 시 상세 진단 출력
 - 커뮤니티: ‘👥 커뮤니티’ 탭(QnA/Chat) 플레이스홀더 제공 — FastAPI/WebSocket 연동 주석 포함

바로가기
- AI_ASSISTANT_GUIDE.md — 대시보드 AI 어시스턴트(컨텍스트·설정 JSON·STT/TTS 로드맵)
- INSTALLATION.md — 설치/실행(직접 실행 포함)
- DEPLOY_CHECKLIST.md — 배포/패키징/사후 점검
- STORAGE_PATHS.md — 저장 경로 규칙
- UPDATE_PLAN.md — 개선 계획과 진행 현황
- CHANGELOG.md — 최근 변경 내역
- TROUBLESHOOTING.md — 문제 해결(직접 실행 실패, 권한, 네트워크 등)
 - TEST_STATUS.md — 최신 테스트 현황 요약(PASS/FAIL 및 다음 단계)
 - SCREENSHOTS_CHECKLIST.md — 문서에 포함할 스크린샷 목록과 파일명 규칙

알려진 이슈(요약)
- 일부 정적 경고(Pylance) 잔존: 동적 속성 주입 패턴으로 인한 것 → 순차 정리 중
- 소스 직접 실행이 특정 환경에서 종료(Exit Code 1): 진단 정보 출력 추가 완료 → 로그 기반 원인 제거 진행 중 (TROUBLESHOOTING 참고)

문의/피드백: 이슈로 남겨주세요.

## Quick Start

- 개발용 빠른 실행(로그인 우회): 환경변수 `NOAHAI_SKIP_LOGIN=true` 설정 후 실행
- 직접 실행: `python3 main.py`
- 최초 실행 시 `Documents/NoahAI/<username>` 하위에 logs/config/analytics 폴더가 자동 생성됩니다.

## Classic View(클래식 보기)

- 설정 화면의 ‘일반’ 탭에서 ‘클래식 보기’를 ON하면 앱 시작 시 자동으로
	- "📚 AI 학습"과 "📊 AI 리포트" 탭을 생성하고,
	- 기본으로 "📚 AI 학습" 탭을 선택합니다.
- 대시보드 진입 후 바로 AI 관련 화면을 확인하려는 경우 권장됩니다.

## Smoke Tests(빠른 검증)

- 네트워크 호출 없이 핵심 가드/파이프라인을 검증합니다.
	- 통합 시스템 드라이런: `python3 -u noahai_client/test_unified_system.py`
	- 페이퍼 모드 E2E: `python3 -u noahai_client/test_paper_flow.py`

## Build(크로스플랫폼)

- 안전 빌드 스크립트: `python build_safe.py --platform windows|macos|linux`
	- Windows: dist/AITrading.exe → deploy/AITrading.exe
	- macOS: dist/AITrading.app → deploy/AITrading.app (환경에 따라 단일 바이너리 deploy/AITrading 복사)
	- Linux: dist/AITrading → deploy/AITrading
- PyQt/Qt/Jupyter/대형 과학 패키지는 스펙에서 제외되며, data 폴더는 런타임에 생성됩니다.

## Screenshots

스크린샷은 `docs/images/`에 저장되며, 준비가 되는 대로 아래 항목을 업데이트합니다. 상세 목록은 `SCREENSHOTS_CHECKLIST.md` 참고.

- ModernDashboard 메인
	- ![placeholder](images/modern_dashboard_main_dark.png)
- Classic View ON 설정
	- ![placeholder](images/settings_general_classic_view_on.png)
- 커뮤니티 탭(플레이스홀더)
	- ![placeholder](images/community_tab_placeholder.png)

# NoahAI Client Docs  
## AI 자산 의사결정 인프라 (운영·검증 중)

이 문서는 `noahai_client/docs/`에서 관리되는 **NoahAI Client의 공식 기술·운영 문서**입니다.  
본 문서는 과거 자동거래 중심 설명을 대체하며, 현재 NoahAI Labs 웹사이트 및 기술 백서와 **동일한 정의와 관점**을 사용합니다.

**운영·제품 주체**: 노아에이아이랩스(Noah AI Labs) — NoahAI 제품·브랜드의 소유 및 개발·운영·서비스 기준 법인입니다.  
**기술 기원(고지)**: **AI 디지털케어로그**는 DAL(드림에이아이랩)에서 개발·검증된 기술·개념이며, Noah AI Labs가 금융 의사결정 인프라로 구현·고도화합니다.

---

## 🧠 NoahAI란 무엇인가

NoahAI는 특정 금융상품을 대신 거래하는 봇이나  
수익을 예측·보장하는 자동매매 시스템이 아닙니다.

**NoahAI는 금융 판단이 무너지지 않도록  
판단·기록·비교·경고의 환경을 유지하는  
AI 자산 의사결정 인프라입니다.**

이 인프라는  
- 판단을 대신하지 않고  
- 실행을 강제하지 않으며  
- 모든 판단 과정을 기록·설명·복기 가능하게 유지합니다.

NoahAI는 2024년 11월부터  
**실계좌·실시간 환경에서 24시간 운영·검증되고 있습니다.**

---

## 왜 NoahAI가 필요한가 (Why NoahAI Was Created)

금융 판단은 더 이상 개인이 안정적으로 감당할 수 있는 문제가 아닙니다.

- 시장은 24시간 움직이고
- 정보는 실시간으로 쏟아지며
- 판단의 근거는 기록되지 않고
- 실패는 반복되지만, 이유는 남지 않습니다

문제는 “누가 더 잘 맞히는가”가 아니라  
**판단이 무너지지 않는 환경을 어떻게 유지할 것인가**입니다.

NoahAI는 이 질문에서 출발했습니다.

---

## 판단 환경 인프라로서의 NoahAI

NoahAI가 하는 일은 다음 네 가지로 요약됩니다.

1. **기록한다**  
   - 모든 판단 시점, 근거, 결과를 로그로 남김
2. **연결한다**  
   - 시장 데이터, 계정 상태, 자산 구조, 리스크 조건을 함께 해석
3. **비교한다**  
   - 과거 패턴·연속 손실·판단 변화 흐름을 재현 가능하게 비교
4. **경고한다**  
   - 판단이 흔들리기 시작한 지점을 구조적으로 드러냄

실행은 언제나  
사용자 설정 또는 외부 시스템(API·거래소·증권사 등)의 선택에 따라 이루어집니다.

---

## 암호화폐는 ‘출발점’일 뿐이다

암호화폐는 NoahAI가 선택한 **첫 검증 도메인**입니다.

- 24시간 실시간 시장
- 높은 변동성
- 잦은 판단 오류
- 연속 손실이 쉽게 발생하는 환경

이 조건은  
AI 자산 의사결정 인프라를 검증하기에 가장 가혹하고 적합한 환경이었습니다.

NoahAI는 암호화폐 실환경에서  
판단·기록·비교·리스크 관리 파이프라인을 검증한 뒤,

동일한 구조를
ETF, 주식, 해외자산, 산업 연계 영역으로 확장하고 있습니다.

---

## 현재 운영 상태 (요약)

- **운영 시작**: 2024년 11월
- **운영 형태**: 실계좌·실시간·24/7
- **핵심 구조**
  - 판단 → 기록 → 비교 → 경고 → 환류
- **안전 장치**
  - 가드레일
  - 중단 조건
  - 보수적 리스크 정책
- **검증 체계**
  - 멀티 모델 비교(Alpha Arena)
  - 리플레이·감사 로그
  - 익명화 패턴 학습

---

## 기술적 원칙

- NoahAI는 금융상품 판매자가 아닙니다.
- NoahAI는 투자 수익을 약속하지 않습니다.
- NoahAI는 판단을 대신하지 않습니다.

NoahAI는  
**AI 시대에 금융 판단이 실제 삶과 산업에서 작동하도록  
판단 환경을 설계·운영하는 인프라**입니다.

---

## 문서 구성

이 문서들은 모두 동일한 정의를 공유합니다.

- INSTALLATION.md — 설치 및 실행
- DEPLOY_CHECKLIST.md — 배포·운영 점검
- UPDATE_PLAN.md — 개선 계획과 진행 현황
- CHANGELOG.md — 변경 내역
- TROUBLESHOOTING.md — 문제 해결
- TEST_STATUS.md — 테스트 현황
- SCREENSHOTS_CHECKLIST.md — 문서 스크린샷 규칙

---

## 문의

기술·운영 관련 문의는 이슈로 남겨주세요.  
NoahAI는 **설명 가능한 AI 의사결정 인프라**를 지향합니다.