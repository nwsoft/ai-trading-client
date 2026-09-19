# v3.9.1.27 Strategy Assistant 연속성·AI 비용·모델 라우팅 검증 원장

기준 일자: 2026-09-11  
현재 공개판: NoahAI Client v3.9.1.27 / updater 3.9.127  
직전 공개판·롤백 기준: v3.9.1.26  
배포 신원: `windows_verified_release_candidate`, `publish_ready=true`; installer·blockmap·`latest.yml` 공개 URL HTTP 200 확인  
검증 경계: 게시 완료와 아래 환경별 업데이트·Provider·기관·DPI·장시간 검증은 분리한다.

## 수정 계약

- 승인·자동검증·PAPER 재개·삭제는 임시 두 번 누르기 상태가 아니라 작업 목적과 영향을 보여 주는 확인/취소 창으로 처리한다.
- 전략 버전 생성 시각은 저장된 `created_at`만 표시하며 구버전의 누락값을 추정하지 않는다.
- 외부 AI 보조가 `interactive_ai_budget_exceeded`로 실패해도 텍스트·Pine 결정형 컴파일은 계속한다. 이미지·영상처럼 외부 해석이 필수이면 정확한 한도 안내를 표시한다.
- 기본 일 30회는 라이선스·거래 제한이 아니라 API 비용·반복 호출 보호용 사용자 설정이다. 일반 안내와 로컬 규칙 분석은 한도를 소비하지 않는다.
- 설정의 AI 비용 관리 카드에서 기본 일 30회·월 500회, 현재 사용량, 일 1~1,000회·월 1~30,000회 범위와 UTC 갱신 기준을 확인할 수 있어야 한다.
- 사용자 요청형 성공 호출의 실제 토큰과 공개 단가가 있을 때만 예상 비용을 계산하고, 토큰·단가가 없으면 0원이 아니라 비용 미산출로 분리한다. 자동매매 백그라운드 비용과 Provider 전체 청구액으로 표현하지 않는다.
- 빈번·표준·정밀·애널리스트·어시스턴트·전사 경로의 현재 Provider·모델을 요약하고 기존 역할별 저장 계약을 그대로 사용한다.
- DeepSeek는 공식 `deepseek-v4-flash` 자동 최신 별칭·`deepseek-v4-pro`·별도 `deepseek-v4-flash-vision-exp`만 정적 등록한다. 일반 Flash를 이미지 입력 모델로 사용하지 않는다.
- `interactive_ai_budget_exceeded` 로컬 차단과 Provider 자체 429를 서로 다른 원인으로 안내한다.
- 초보자·일반·고급은 실제 시스템 지시문과 캐시 문맥을 분리한다. Strategy Studio에서 연 어시스턴트는 초보자를 기본으로 한다.
- AI 답변은 원본을 덮지 않는 편집 가능한 미적용 초안으로 Strategy Studio에 전달한다. 사용자가 확정한 뒤에만 별도 보완 근거로 결합하고 전체 규칙을 재분석한다.
- 답변 전달이나 보완 확정은 전략 저장·승인·PAPER·LIVE를 자동 실행하지 않는다.
- 공통 제작 경로는 암호화폐와 주식·ETF에 함께 적용한다. 레버리지 선택지는 암호화폐 최대 5배, 주식·ETF 1배를 유지한다.
- 설정 9개 탭은 타입이 제한된 탭 ID를 Gateway와 AI 어시스턴트까지 전달하며 질문 문구로 현재 탭을 추측하지 않는다. 탭 변경 뒤 이전 응답이 새 탭에 표시되지 않는다.
- 모든 지원 AI 제공사는 정적 호환 모델 상태·기능·용도·장단점·기준일 공개 단가와 실제 계정 조회 결과를 구분한다. 정적 목록만으로 호출 가능을 확정하지 않는다.
- OpenAI 기본 보호 Project와 공개 일반 질문용 Project 자격증명을 분리한다. 공개 경로는 기본 OFF이고 사용자가 공개 질문 1건을 확인한 경우에만 사용하며 최근 대화·계좌·설정·전략·파일·차트 문맥을 제외한다.
- 공유용 키 누락·설정 OFF·알 수 없는 범위는 기본 보호 경로로 닫고 보호 요청이 공유용 키를 빌려 쓰지 않는다. 조직 공유 활성화·무료량은 앱이 확인하거나 보장하지 않는다.

## 자동 검증

- [x] 암호화폐 텍스트 규칙 + 외부 AI 429에서도 로컬 컴파일
- [x] 주식·ETF 텍스트 규칙 + 외부 AI 429에서도 로컬 컴파일
- [x] 429 로컬 AI 설명과 일/월 한도 표시
- [x] 설정 AI 비용 관리 카드와 현재 사용량·갱신 기준 표시
- [x] 실제 토큰·공개 단가 기반 비용 추정과 비용 미산출 분리
- [x] 역할별 AI 구성 요약과 DeepSeek 공식 모델 ID
- [x] 선택 모델별 차트 비전 capability 사전 차단
- [x] 로컬 비용 보호 429와 Provider 자체 429 안내 분리
- [x] 단일 확인창과 두 번 누르기 상태 제거
- [x] 답변 전달 → 검토 → 사용자 확정 → 재분석 계약
- [x] 설명 수준별 시스템 지시문·캐시 분리
- [x] 동적 Electron 버전 제목과 버전 생성 시각 표시
- [x] 레버리지 가드레일 불변
- [x] 설정 9개 탭의 구조화 문맥·교차 탭 응답 무효화
- [x] 전체 AI 어시스턴트까지 설정 탭 문맥 전달·표시
- [x] 제공사별 모델 상태·기능·용도·장단점·공개 단가·전사 경로 표시
- [x] OpenAI 기본 보호/공개 질문용 Project 키 분리·기본 OFF·명시적 질문 1건 경로
- [x] 공개 질문의 최근 대화·계좌·설정·전략·파일·차트 문맥 제거와 안전 fallback
- [x] OpenAI 데이터 공유 상태·무료량 비보장·공식 설정 링크

OpenAI Project 경로 직접 회귀 `8 passed`, 관련 AI·설정·차트 집중 회귀 `56 passed`, 전체 Python 회귀 `2,208 passed, 8 skipped`, Node 22 Web production build `50 modules`, production 의존성 취약점 `0건`, 문서·사용자 노출 동기화와 Web UI 전체 표면 계약 `PASS`를 확인했다. 경고 1건은 기존 Starlette/httpx 호환성 폐기 예정 경고다.

실제 사용자 데이터·자격정보·브로커 네트워크를 사용하지 않는 `release_gate --profile prekey`도 PASS했다. `.git` 메타데이터가 없는 작업 폴더이므로 동기화 검사는 이번 변경 파일 24개를 쉼표 구분으로 명시해 수행했다.

## Windows 공개 자산 확인

- [x] `WIN-BUILD` — Windows v3.9.1.27 설치기·blockmap·`latest.yml` 버전·SHA 일치
- [x] `PUBLISH` — GitHub v3.9.1.27 릴리스, 설치기와 `latest.yml` 공개 URL HTTP 200
- 설치기: `NoahAI-3.9.1.27-Setup.exe`, 413,228,288 bytes, SHA-256 `6593ef09cef437c6d8126262292ad6ab5d81c5e69f910772a985c28b3e379d3f`
- blockmap SHA-256: `71c104700897bb561f4ea4807ec2afb8692fe32b37eaa67f80040816080bd484`
- `latest.yml` SHA-256: `bc96e1239b675a5dc8142cb141c98f8b37ff8ba6e91cbdb23bb353e900ec31af`
- embedded `NoahAIEngine.exe` SHA-256: `7d5fc56f309cdf5e529a2d5c7ad980fe20b926c29643c2f717d5d48b1a9a3047`
- 게시 확인 시각: 2026-09-11, 로컬 manifest와 공개 GitHub 자산 기준

## 공개 후 외부 환경 게이트

- [ ] `WIN-UPGRADE` — v3.9.1.26 → v3.9.1.27 업데이트·안전 종료·재시작·사용자 설정/원장/초안 보존
- [ ] `ROLLBACK` — 업데이트 실패 시 직전 공개판 복구와 사용자 데이터 불변
- [ ] `PROVIDER-429` — 실제 AI Provider의 정상 응답·빈 응답·30/30 한도·일/월 경계
- [ ] `PROVIDER-MODELS` — 실제 DeepSeek 계정의 공식 모델 목록·Flash/Pro 텍스트 JSON·계정 제공 시 Vision 실험 모델 이미지 입력
- [ ] `PROVIDER-CATALOGS` — 실제 OpenAI·Kimi·Anthropic·Gemini 계정 목록과 정적 호환 목록·기능·공식 가격 대조
- [ ] `OPENAI-SHARING` — 승인된 비민감 QA 계정에서 두 Project 키의 실제 분리, 공개 질문 route 표시, Provider Usage와 무료량 대조; 비공개 전략·계좌 데이터 전송 금지
- [ ] `PROVIDER-COST` — 앱 사용자 요청형 예상액과 Provider 콘솔 청구 범위 대조, 토큰·단가 미제공 호출의 비용 미산출 확인
- [ ] `WINDOWS-DPI` — Windows DPI/해상도별 확인창·생성 시각·답변 검토 패널
- [ ] `SPOT-FUTURES-PAPER` — 암호화폐 현물·선물 Strategy Studio 실제 화면 왕복
- [ ] `KIWOOM-E2E` — 키움 주식·ETF Strategy Studio 실제 화면 왕복
- [ ] `KIS-E2E` — 한국투자 주식·ETF Strategy Studio 실제 화면 왕복
- [ ] `BITHUMB-E2E` — Bithumb 현물 Strategy Studio 실제 화면 왕복
- [ ] `RECONCILE-E2E` — 재시작 뒤 전략 초안·버전·PAPER 원장 정합
- [ ] `REPORT-E2E` — AI 안내·내장 매뉴얼·버전 표기와 실제 화면 정합
- [ ] `SOAK` — 암호화폐·주식/ETF 장시간 PAPER 중 UI 상태와 원장 보존

공개 자산 존재는 위 외부 환경 항목을 소급 완료시키지 않는다. 실제 사용자 데이터 폴더는 수정하지 않고 합성 fixture와 명시적 QA 계정만 사용한다.
