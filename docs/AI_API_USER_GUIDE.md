# OpenAI/호환 API 사용자 안내 (초보자용)

## 이 문서는 누구를 위한 문서인가?
- 개발자가 아니라, 앱 사용자(Windows/macOS) 기준 안내입니다.
- 설정 화면에서 바로 따라 할 수 있도록 최소 단계만 정리했습니다.

## 먼저 알아두기
- ChatGPT 유료 구독(Plus/Team)과 OpenAI API 과금은 별개입니다.
- NoahAI 앱은 OpenAI API 키(또는 OpenAI 호환 API 키)가 필요합니다.
- API 키는 앱 안에서 발급되지 않고, 제공사 웹사이트에서 발급합니다.

## 1) OpenAI API 키 발급 순서
1. https://platform.openai.com 로그인
2. Billing(결제)에서 카드 등록
3. Usage limits(사용한도) 설정
   - 권장 시작값: Hard Limit 10~20 USD / Soft Limit 5 USD
   - 처음에는 낮게 시작하고, 사용량 확인 후 상향하세요.
4. API Keys > Create new secret key
5. Key Name(이름) 입력
   - 권장 예시: NoahAI-Desktop
   - 이유: 키를 여러 개 만들 때 용도 구분이 쉬워집니다.
6. 생성된 키를 즉시 복사
   - 보안상 생성 직후 전체 키를 다시 못 보는 경우가 많습니다.
7. NoahAI 앱 설정에 붙여넣기
   - 설정 > OpenAI API > OpenAI API Key

참고:
- 보통 선충전 없이 사용량 기반 과금으로 시작할 수 있습니다.
- 결제 정책/국가에 따라 소액 결제 인증이 필요할 수 있습니다.

## 2) OpenAI 호환 Base URL은 언제 쓰나?
- 기본(OpenAI 공식 API) 사용 시: 비워둡니다.
- 다른 제공사 사용 시에만 입력합니다.
  - 예: DeepSeek / OpenRouter / 로컬 Ollama

예시 Base URL:
- DeepSeek: https://api.deepseek.com
- OpenRouter: https://openrouter.ai/api/v1
- Ollama(local): http://localhost:11434/v1

## 3) 모델 선택 권장
- 초보자 기본: gpt-4o-mini
- 이유: 비용 대비 응답 품질 균형이 좋고 속도가 안정적입니다.

## 4) 비용 최적화 체크리스트
- Hard/Soft Limit를 먼저 설정했는지
- 기본 모델이 gpt-4o-mini인지
- 불필요한 반복 질문/자동 실행이 켜져 있지 않은지
- 1주 사용 후 사용량(Usage) 페이지를 보고 한도를 조정하는지

## 5) 자주 막히는 지점
- 키 이름 입력을 건너뛰어 헷갈리는 경우
  - 해결: 키 이름을 NoahAI-Desktop처럼 앱 이름으로 고정
- ChatGPT 구독만 하면 API가 자동으로 되는 것으로 오해
  - 해결: API는 별도 결제/사용한도 설정 필요
- Base URL을 OpenAI 사용인데도 입력해서 오류 발생
  - 해결: OpenAI 공식 사용이면 Base URL은 빈칸

## 6) 개발자 문서가 따로 있는 이유
- 현재 문서는 사용자용입니다.
- 개발자용 구현/코드 구조 문서는 별도로 분리되어 있습니다.
  - docs/AI_API_ARCHITECTURE.md
- 앱 설정 화면에서는 사용자용 문서를 우선 열도록 구성되어 있습니다.
