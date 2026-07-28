# NoahAI AI 엔진 확장 종합 계획
## v3.9.0.3 기존 AI 기능의 멀티 API 기반 확장

기준일: 2026-07-28
대상 버전: v3.9.0.3 Windows 업데이트
현재 상태: v3.9.0.3 업데이트 대상 구현 완료, 실제 제공사 키·코드서명 Windows 설치본 검증 후 배포

---

## 1. 문서 목적

이 문서는 이미 배포된 v3.9.0.2 이후, v3.9.0.3 Windows 업데이트에 다음 목표를 안전하게 포함하기 위한 기술/제품 실행 기준이다.

- 기존 사용자 입력 방식(API 키 입력 중심)을 유지한다.
- OpenAI 무중단 호환을 유지하면서 DeepSeek·Anthropic Claude·Google Gemini를 정식 선택지로 제공하고 Kimi K3를 어시스턴트 시험 지원한다.
- 사용자 입장에서 엔진 교체가 설정 손실 없이 작동하도록 한다.
- AI 질문답변, 문답 절약형(비용/토큰 절감) 동작을 엔진 중립적으로 재정의한다.
- AlphaArena 멀티 엔진·실거래 연결은 후속 업데이트로 분리한다.

---

## 2. 배경과 의사결정 이유

### 2-1. 왜 지금 확장하는가

- 제공사별 가격·속도·가용성이 다르므로 사용자가 비용과 품질 선택권을 가질 가치가 있다.
- 무료 크레딧이나 일시 할인은 보장하지 않으며, 비용 안내는 릴리스 시점의 공식 가격을 기준으로 한다.
- 현재 DeepSeek V3.1의 `deepseek-chat`/`deepseek-reasoner` 경로가 종료되어 동적 모델 대응이 즉시 필요하다.

### 2-2. 무엇을 유지하는가

- 사용자에게 익숙한 API 키 입력 방식은 그대로 유지한다.
- 기존 OpenAI 설정 키는 그대로 동작시켜 업그레이드 충격을 줄인다.

### 2-3. 2026-07-28 공식 문서 재확인

- DeepSeek 공식 변경이력은 `deepseek-chat`·`deepseek-reasoner`의 2026-07-24 종료와
  `deepseek-v4-flash`·`deepseek-v4-pro` 전환을 안내한다:
  https://api-docs.deepseek.com/updates/
- DeepSeek와 OpenAI는 각각 계정에서 허용된 모델을 확인하는 `GET /models` 계약을 제공한다:
  https://api-docs.deepseek.com/api/list-models
  https://platform.openai.com/docs/api-reference/models
- Kimi 국제 Open Platform은 OpenAI 호환 형식, `https://api.moonshot.ai/v1`,
  `kimi-k3` 모델을 공식 안내한다:
  https://platform.kimi.ai/docs/api/overview
  https://www.kimi.com/help/kimi-api/api-model-selection

따라서 종료 모델을 정적으로 계속 유지하는 것은 타당하지 않고, 동적 모델 목록과 공식 fallback을 함께 두는 선택이 맞다.

---

## 3. 현재 구조 이해 (코드 기준)

아래는 현재 코드에서 확인된 동작 기준선이다.

### 3-1. 일반 AI 설정

- 설정 저장 키:
  - openai_api_key
  - openai_base_url
  - openai_model
  - assistant_ai_model
  - ai_model_roles(frequent_cheap, standard, premium)
- 관련 파일:
  - ui/settings_modern.py
  - ui/dashboard_modern.py
  - trading/ai/openai_client.py

### 3-2. 현재 호환 구조의 강점

- OpenAIClient가 base_url을 지원하므로 OpenAI 호환 API 엔드포인트 전환이 이미 가능하다.
- 역할별 모델 티어(빈번 호출/표준/정밀)와 프리셋(절약형/균형형/정밀형)이 UI와 저장 로직에 존재한다.

### 3-3. 기준선에서 확인한 병목과 현재 조치

- OpenAI 중심 설정 용어는 `AI 엔진/API`와 provider profile로 확장했다.
- AlphaArena의 종료된 DeepSeek 3.1 별칭은 DeepSeek V4 Flash로 이전하되 멀티 엔진 실거래는 분리했다.
- 질문답변/문답 절약형 정책을 엔진 중립 예산으로 구현·문서화했다.

---

## 4. v3.9.0.3 업데이트 목표 범위

### 4-1. 지원 엔진

- OpenAI
- DeepSeek V4 Flash/Pro
- Anthropic Claude(Haiku/Sonnet/Opus, 네이티브 Messages API)
- Google Gemini(공식 OpenAI 호환 API)
- Kimi K3/K2.6(어시스턴트용 NoahAI 시험 연동)

### 4-2. 비목표(이번 버전에서 하지 않음)

- 자동 결제/구독 연동
- 엔진별 고급 파라미터를 초기 화면에 과다 노출
- 기존 OpenAI 키 이름/설정 키 강제 마이그레이션
- AlphaArena 멀티 엔진 비교·실거래 연결

### 4-3. 같은 후보 버전의 사용자 피드백 범위

AI API 확장과 함께 다음 항목을 같은 Windows 후보 빌드에서 검증한다.

- Windows 한글 기본 글꼴과 배율별 대시보드 표시
- 비정상 종료 세션 표식, 메인·스레드·Tk callback 예외, 지원 환경의 네이티브 치명 오류 진단
- 화면·분석·학습 거래소와 실제 주문 거래소의 명시적 분리
- AI 커스텀의 `AI 자동 대응 1개 + 검토용 초안 4개`
- AI 어시스턴트의 전략 설명과 AI 커스텀 입력창 전달

전략 초안 전달은 AI 분석·저장·승인·자동검증·최종 적용·주문을 자동 실행하지 않는다.
상세 계약은 `AI_CUSTOM_CONVERSATIONAL_PRESETS_PLAN_v3.9.0.3.md`를 따른다.

---

## 5. 설계 원칙

### 5-1. 호환성 우선

- 기존 openai_* 설정은 깨지지 않는다.
- 기존 사용자 업그레이드 후 즉시 기존 엔진(OpenAI)으로 동작해야 한다.

### 5-2. 사용자 전환 안전

- 엔진 전환은 저장 전 검증(키 존재, 모델 기본값, 연결 테스트)을 거친다.
- 실패 시 이전 엔진/모델 자동 롤백 옵션을 제공한다.

### 5-3. 엔진 중립 정책

- 질문답변 품질 정책, 절약 정책, 토큰 예산 정책을 특정 제공사 명칭에서 분리한다.

### 5-4. 관측 가능성

- 엔진별 호출 수, 실패율, 평균 응답시간, 토큰/비용 추정치를 동일 포맷으로 기록한다.

---

## 6. 목표 아키텍처 (Provider Adapter)

### 6-1. 핵심 아이디어

기존 OpenAIClient 직접 의존 경로를 아래 형태로 확장한다.

- AIProviderRouter
  - provider=openai|deepseek|kimi|anthropic|gemini
  - model
  - credential_ref
  - base_url(optional)
- OpenAICompatibleAdapter
  - OpenAI
  - DeepSeek
  - Kimi
  - Gemini 공식 호환 엔드포인트
- Native Adapter
  - Anthropic Messages API

### 6-2. 공통 인터페이스

- list_models()
- chat_text()
- chat_json()
- vision(optional)
- transcribe(optional)
- health_check()
- normalize_usage()
- capabilities()

### 6-3. 응답 정규화

엔진별 응답 포맷 차이를 공통 스키마로 맞춘다.

- content
- finish_reason
- usage.input_tokens
- usage.output_tokens
- usage.cached_input_tokens(optional)
- provider_error_code(optional)
- status_code(optional)
- retryable

---

## 7. 설정 스키마 전략 (하위 호환 포함)

### 7-1. 새 권장 스키마

- ai_provider: openai | deepseek | kimi | anthropic | gemini
- ai_credentials: provider별 `credential_ref`와 base_url
- ai_provider_profiles:
  - analyst
  - assistant
  - transcription(OpenAI 독립)
- ai_model_roles:
  - frequent_cheap: `{provider, model}`
  - standard: `{provider, model}`
  - premium: `{provider, model}`
- ai_models:
  - analyst
  - assistant
  - roles.frequent_cheap
  - roles.standard
  - roles.premium

### 7-2. 기존 키와의 공존

초기에는 아래 키를 그대로 유지하며 매핑 계층으로 흡수한다.

- openai_api_key -> 운영체제 보안 저장소의 ai_credentials.openai.credential_ref
- openai_base_url -> ai_credentials.openai.base_url
- openai_model -> ai_models.analyst
- assistant_ai_model -> ai_models.assistant
- 레거시 ai_model_roles의 모델 문자열 -> 같은 기존 Provider를 넣은 `{provider, model}`로 자동 변환

### 7-3. 저장/로드 규칙

- 저장 시: API 키는 macOS Keychain/Windows Credential Manager에 저장하고 JSON에는 `credential_ref`만 저장
- 로드 시: 새 스키마 우선, 없으면 레거시 키 fallback
- 레거시 `openai_api_key`는 보안 저장소 이전 성공 후 디스크에서 비우고 런타임 메모리에서만 복원
- settings.json과 자동 백업의 AI 평문 키를 credential reference로 교체하고, 가능한 운영체제에서 파일 권한을 사용자 전용(0600)으로 제한

---

## 8. 구현된 UI/UX (기존 입력 방식 유지)

### 8-1. OpenAI API 탭 명칭 정리

- 현재 OpenAI API 탭을 AI 엔진/API 탭으로 확장
- 사용자는 기존처럼 API 키 입력 방식으로 진행

### 8-2. 필수 UI 요소

- API 키를 편집할 엔진 드롭다운
- 선택 엔진 API 키 입력 필드(운영체제 보안 저장)
- 애널리스트/어시스턴트별 Provider+모델 선택
- 빈번/표준/정밀 작업별 Provider+모델 배치
- 절약형/균형형/정밀형 프리셋
- 계정 모델 새로고침과 실제 API 기능 검증 버튼
- 모델 상태(권장·계정 확인·미리보기·비권장·종료) 표시

### 8-3. 사용자 보호 문구

- ChatGPT 유료와 API 과금 분리 안내 유지
- Kimi K3는 시험 지원임을 표시
- 비전/음성 전사는 제공사 capability가 없으면 호출 전에 차단
- AI 커스텀 음성 전사는 분석 Provider와 분리한 OpenAI 전용 프로필로 실행
- `gpt-4o-mini-transcribe`, `gpt-4o-transcribe`, 다중 화자용 `gpt-4o-transcribe-diarize`를 구분

---

## 9. AI 질문답변/문답 절약형 재설계

### 9-1. 문제 정의

현재 프리셋은 모델 조합 중심이고, 질문답변 자체의 비용 절약 정책(컨텍스트 압축, 응답 길이, 반복 호출 억제)이 엔진 공통 스펙으로 명확하지 않다.

### 9-2. 운영 모드 3종(엔진 공통)

- QnA 표준형
  - 기본 설명 품질 우선
  - 중간 길이 응답
- 문답 절약형
  - 핵심 답 먼저, 근거 최소화, 토큰 상한 낮춤
  - 긴 이력 대신 요약 컨텍스트 사용
- 분석 정밀형
  - 근거/비교/리스크 설명 강화
  - 토큰 상한 상대적으로 높음

### 9-3. 절약형 정책 세부

- 요청 전 컨텍스트 압축:
  - 최근 대화 N개 + 요약 메모 1개만 전달
- 응답 정책:
  - 최대 토큰 상한 축소
  - 불필요한 서론/반복 문장 제거
- 중복 질의 캐시:
  - 동일 질문+동일 상태 해시 재사용
- 실패 폴백:
  - 엔진 오류 시 간단 모드 응답 또는 로컬 가이드 텍스트 제공

### 9-4. 정책 키 제안

- assistant_response_mode: standard | saver | premium
- assistant_token_budget:
  - max_input_chars
  - max_output_tokens
- assistant_context_policy:
  - include_recent_turns
  - include_summary
  - include_market_snapshot

---

## 10. AlphaArena 범위 분리

### 10-1. 현상

- 일부 컴포넌트가 deepseek 중심 기본값으로 고정되어 있음.

### 10-2. v3.9.0.3 포함 범위

- 종료된 `deepseek-3.1`/`deepseek-chat` 설정을 `deepseek-v4-flash`로 안전 이전
- AlphaArena의 기존 단일 DeepSeek 실행 흐름과 주문 가드레일 유지
- Qwen/기타 엔진을 새로 실거래 활성화하지 않음

### 10-3. 후속 업데이트

- 일반 AI Router와 AlphaArena 실행 프로필 통합
- 다중 엔진 비교·paper-trading·고정 시나리오 회귀 검증
- 사용자 명시적 재승인 후에만 엔진별 실거래 활성화
- 실거래 경로에서는 자동 provider fallback 금지

---

## 11. 마이그레이션/릴리스 상태

### Phase A. 구조 추가 (구현 완료)

- Provider Router/Adapter 도입
- 레거시 키 fallback 유지
- 기존 OpenAI 경로 무중단

### Phase B. UI 확장 (구현 완료)

- 엔진 선택 + 엔진별 키 입력
- 연결 테스트/모델 조회
- 절약형 정책 모드 노출

### Phase C. DeepSeek 폐기 모델 정리 (구현 완료)

- 일반 AI/AlphaArena의 종료 모델 별칭을 V4 Flash로 안전 이전
- 모델 목록 API 실패 시 공식 fallback 목록과 오류 상태를 구분

### Phase D. 작업별 멀티 Provider와 전사 분리 (구현 완료)

- 작업별 저장값을 모델 문자열에서 `{provider, model}`로 전환
- 기존 문자열 설정은 기존 Provider를 보존해 자동 마이그레이션
- AIManager가 빈번/표준/정밀 작업마다 해당 Provider Router를 사용
- AI 커스텀 분석은 premium 작업 프로필, 무자막 전사는 OpenAI transcription 프로필 사용
- Kimi는 실제 키 검증 전까지 어시스턴트 역할만 허용

### Phase E. 모델 수명주기와 저장 검증 (구현 완료)

- 공식 기준 모델 레지스트리와 권장·사용 가능·미리보기·비권장·종료 상태 추가
- 종료 모델은 정상 선택 목록에서 제외하고 저장 차단
- API 키가 있으면 저장 시 계정 모델 목록을 실제 조회
- 계정 조회가 실패하거나 키가 없으면 설정은 보존하되 테스터 검증 대기 경고를 영속 기록
- `실제 API 기능 검증`에서 텍스트·JSON·usage·정규화 오류·선택적 음성 전사를 점검

### Phase F. 검증/배포 (소스 회귀 완료·외부 게이트 대기)

- 문서 정합 회귀와 전체 무자격증명 회귀 `1,135 passed, 6 skipped, 0 failed`
- 사용자 문서·인앱 매뉴얼·업데이트 내역 정합화
- 실제 제공사 키, 서명된 Windows EXE, 이전 버전 자동업데이트·복원, 장시간 실사용은 대기

---

## 12. 테스트 기준 (Release Gate)

### 12-1. 기능 게이트

- OpenAI 기존 사용자 설정이 업데이트 후 그대로 동작
- OpenAI/DeepSeek 모델 목록·인증 연결 성공
- Anthropic Claude 네이티브 텍스트·JSON·사용량·오류 연결 성공
- Google Gemini 공식 호환 텍스트·JSON·사용량·오류 연결 성공
- Kimi K3/K2.6는 무자격증명 계약 회귀 통과, 실제 Kimi 키 E2E 후 시험 표시 유지/해제 결정
- 작업별 서로 다른 Provider가 실제 해당 키와 모델로 라우팅
- 분석 Provider가 Claude/DeepSeek/Gemini여도 전사는 OpenAI 프로필로 실행
- 전사 기본 2종과 다중 화자 모델의 capability·계정 권한 검증
- 질문답변 모드 3종 응답 정책 차이 확인

### 12-2. 안전 게이트

- 엔진 전환 실패 시 기존 설정 자동 복구
- API 키 누락/오입력 시 저장 차단 또는 경고
- 모델 조회 실패 시 수동 모델 입력 fallback
- API 키 평문이 새 settings.json/백업에 남지 않음

### 12-3. 관측 게이트

- provider/model/usage 로그 누락 0건
- 엔진별 오류 코드 분류 가능
- capability 미지원 기능은 호출 전에 차단 가능

---

## 13. 리스크와 대응

- 리스크: 엔진별 API 스펙 차이로 JSON 파싱 실패 증가
  - 대응: Adapter 계층에서 강제 정규화 + 공통 예외 코드
- 리스크: 사용자가 엔진 전환 후 품질 저하 체감
  - 대응: 균형형 기본 권장 + 즉시 롤백 버튼
- 리스크: 가격·한도·모델 ID 변경
  - 대응: 동적 모델 조회 + 공식 fallback 목록 + 릴리스 시점 문서 확인
- 리스크: API 키 보안 저장소 접근 실패
  - 대응: 새 키 저장 차단 + 기존 레거시 사용자의 무중단 실행 + 명시적 이전 경고

---

## 14. 운영 문서 갱신 체크리스트

이번 후보에서 아래 사용자·기술 표면을 함께 갱신했다.

- README.md / docs/README.md
- RELEASE_NOTES.md / docs/CHANGELOG.md / docs/UPDATE_PLAN.md
- docs/AI_API_ARCHITECTURE.md / docs/AI_API_USER_GUIDE.md
- docs/USER_GUIDE.md / USER_GUIDE_AI_EXECUTION.md
- ui/widgets/user_manual_widget.py
- docs/NOAHAI_TECHNICAL_WHITEPAPER.md

---

## 15. 완료 판정 기준

아래 조건을 모두 만족하면 v3.9.0.3 AI 엔진 확장 업데이트를 완료로 판정한다.

- 기존 OpenAI 사용자 무중단
- OpenAI/DeepSeek 정식 연결 계약 검증 완료
- Anthropic Claude·Google Gemini 정식 연결 계약 검증 완료
- Kimi K3/K2.6 어시스턴트 시험 계약 검증 완료
- 질문답변/문답 절약형 정책이 엔진 중립 스펙으로 구현
- AlphaArena 종료 모델 이전 완료, 멀티 엔진 실거래는 후속 계획으로 분리
- 사용자 문서/개발 문서/업데이트 플랜 정합성 일치
- Windows 10/11 새 설치본에서 한글 글꼴·비정상 종료 진단·거래소 주문 범위·AI 커스텀 입력 전달 실화면 확인

현재 소스 자동 회귀와 문서 정합성은 통과했지만 실제 OpenAI·DeepSeek·Anthropic·Gemini 자격증명 응답,
Kimi 시험 계정, Windows 재빌드·설치·자동복원·장시간 실행은 약 10명의 테스터가 배포 후보
Windows 빌드에서 확인하는 외부 게이트다. 이 항목을 통과하기 전에는 완료 배포로 표시하지 않는다.

---

## 부록 A. 권장 기본값

- 기본 엔진: OpenAI (기존 사용자 연속성 유지)
- 기본 모드: 질문답변 표준형
- 신규 사용자 추천 프리셋: 균형형
- 비용 민감 사용자 추천: 문답 절약형 + 절약형 프리셋

## 부록 B. 설정 예시 (과도기)

{
  "ai_provider": "openai",
  "ai_credentials": {
    "openai": {
      "credential_ref": "keyring://NoahAI/<account>.openai",
      "base_url": ""
    },
    "deepseek": {
      "credential_ref": "keyring://NoahAI/<account>.deepseek",
      "base_url": "https://api.deepseek.com"
    }
  },
  "ai_models": {
    "analyst": "gpt-5.6-luna",
    "assistant": "gpt-5.6-terra",
    "roles": {
      "frequent_cheap": {"provider": "deepseek", "model": "deepseek-v4-flash"},
      "standard": {"provider": "openai", "model": "gpt-5.6-terra"},
      "premium": {"provider": "anthropic", "model": "claude-opus-5"}
    }
  },
  "ai_custom_transcription": {
    "enabled": true,
    "provider": "openai",
    "model": "gpt-4o-mini-transcribe"
  },
  "assistant_response_mode": "saver"
}
