# Web UI 격리 화면 회귀

## v3.9.2.2 보험 화면 회귀

`insurance.html`은 실제 InsuranceWorkspace/API를 사용한다. `scripts/qa_insurance_gateway.py`는 실제 인증 gateway와 보험 저장소를 연결하되 임시 폴더·합성 계정만 사용한다. 종료하면 임시 자료를 정리한다. 고객 계정·보험·거래 엔진·외부 AI를 연결하지 않는다. 이 페이지는 production 진입점에 포함되지 않는다.

1. 프로젝트 루트에서 `.venv/bin/python scripts/qa_insurance_gateway.py` (127.0.0.1:4199).
2. 별도 터미널에서 `cd webui` 후 `npm run dev -- --host 127.0.0.1 --port 5173`.
3. Chrome과 Playwright가 준비된 환경에서 `PLAYWRIGHT_MODULE_PATH=/absolute/path/to/playwright node scripts/test_insurance_ui.cjs`.
4. 시험 종료 후 두 개발 서버를 종료한다. 다른 보험 저장소/고객 gateway를 이 fixture에 연결하지 않는다.

1490/1080/640px에서 암호화 저장소 생성·잠금, 계약 입력/정정, 원문 PNG 등록·초안, 월 보험료 환산, 두 계약 비교, 원문 삭제 후 재확인, 보고서 검토·다운로드, 암호화 백업을 확인한다. 페이지 오류·외부 요청·가로 넘침도 검사한다. 640px은 새 패널 시험이며 전체 앱의 최소폭 1080px이나 Windows DPI 인수를 대체하지 않는다. 화면은 `/tmp/noah-v3922-insurance-*.png`에 저장한다. `?locale=en`으로 영어 상태 선택값 유지도 확인할 수 있다.

이 Mac에서는 공유 node_modules의 Windows용 Rollup 문제를 피해 기존 격리된 Mac 의존성 환경의 Vite 6.4.3으로 빌드했다. 원본 node_modules를 지우지 않았다. 재현 환경에는 해당 OS용 잠금 파일 의존성과 `electron/ui-build-contract.cjs`의 buildPlugin이 필요하다. 실제 산출물 지문은 TEST_STATUS에 기록한다.

## 이전 전략 스튜디오 화면 회귀

### 3.9.2.2 금융상품 초보자 가이드

Vite를 127.0.0.1:5173에서 실행한 뒤 `PLAYWRIGHT_MODULE_PATH=/absolute/path/to/playwright node scripts/test_product_guide_ui.cjs`. 실제 `LifeFinanceAdvanced`→`GuidedProductComparison`을 렌더링하고 gateway는 합성 fixture다. 대출/예금/적금 계산은 실제 순수 함수다. 1490/1080/640px에서 탭·키보드·빈 입력·예시·결과 무효화·월 부담 그래프·적립 방식·AI 초안과 명시 전송·입력 유지·보험 지연 진입을 검사한다. 실제 금융사/API/AI는 호출하지 않는다. 화면은 `/tmp/noah-product-*.png`, 산술 회귀는 `node --test tests/finance-comparison.test.cjs`로 재현한다. 640px은 패널 범위이며 전체 앱의 모바일 지원을 뜻하지 않는다.

`strategy-feedback.html`은 실제 StrategyStudio/SourceWorkspace 컴포넌트에 합성 응답만 연결하는 개발용 fixture다. API 키·사용자 원장·주문·외부 AI를 사용하지 않으며 production 진입점에 포함되지 않는다.

1. Node 22 환경에서 `npm run dev -- --host 127.0.0.1 --port 5193`를 실행한다.
2. 별도 QA 환경에 Playwright와 Chrome을 준비한다. `PLAYWRIGHT_MODULE`에는 설치된 Playwright의 `index.mjs` 절대 경로를 지정할 수 있다.
3. 프로젝트 루트에서 `node webui/qa/check-feedback.mjs`를 실행한다. 다른 포트는 `QA_BASE_URL`로 지정한다.

검사: 코인·주식의 날짜·상태·v1 비교(1280/1440/1920), 예제→보완 포커스→저장→승인→과거재생→PAPER(1280), 거래소/증권사 카드·실행 풀 안내·로그(800/1280/1440/1920 × 연결/미연결), 계정 거래 권한 차단 카드와 HTTP 409의 승인 행동 안내 변환. 배율 1.25로 실행하며 오류 및 카드 겹침·넘침을 검사한다.

이는 UI 회귀다. 응답은 합성이므로 실행 엔진·실계정·Windows COM·DPI 검증을 대체하지 않는다. 스크린샷은 `/tmp/noahai-v39130-*-repair.png`에 저장한다.

v47 오류 안내: `check-gateway-errors.mjs`는 실제 프런트 오류 변환기를 11기관 문자열/구조화 응답 및 미분류 409로 검사한다. 응답 본문의 비밀값을 출력하지 않는지와 반복 클릭 안내 제거를 확인한다. `check-strategy-repair.mjs`는 기존 원문 보완 시 포커스 이동·원문 보존·공통 안내도 검사한다. 실제 사용자 409 원인을 재현하는 시험과는 다르다.


2026-10-04: 상품 가이드 첫 화면은 `FinanceDiscovery`로 교체되었습니다. 기존 `test_product_guide_ui.cjs`의 두 견적 기본 노출 가정은 과거 UI 검증입니다. 현재 초보자 흐름은 `scripts/test_v3923_discovery_ui.cjs`, 직접 견적/대화/탭 유지 회귀는 `scripts/test_v3923_advanced_ui.cjs`로 검증합니다.


2026-10-10: `check-simple-studio.mjs`는 Vite 5193에서 코인·주식 1440/1080의 작업 선택, 초안 보존, 학습·따라하기, 공유 내보내기와 가로 넘침을 검사합니다. 필요하면 `PLAYWRIGHT_MODULE`에 Playwright 모듈 경로를 지정합니다. 합성 자료이며 실제 거래를 실행하지 않습니다.


v3.9.2.10: `check-simple-studio.mjs`는 초보/상세 모드 각각 코인·주식 1440/1080에서 작업 선택·초안 보존·학습·공유 전용 행동을 검사합니다. `QA_BASE_URL`로 Vite 주소, `QA_PYTHON`으로 실제 로컬 컴파일러 Python을 지정할 수 있습니다. `check-strategy-levels.mjs`와 `check-strategy-repair.mjs`는 Windows 경로와 UTF-8 입출력을 지원합니다. 계정 응답은 합성이며 실제 주문은 실행하지 않습니다.
