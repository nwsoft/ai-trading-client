# 3.9.2.0 AI 모델 호환 목록 갱신

기준일: 2026-10-01. 공개 설치본은 3.9.1.50, 이번 변경은 3.9.2.0 소스 후보다. Windows 빌드·게시자는 사용자다.

## 목적과 범위

빈번한 호출에 GPT-6 Luna를 선택할 수 있도록 하고, 기존 다섯 Provider의 공식 모델 ID·호환 조건·가격 안내를 점검한다. 새 Provider나 임의 도구 실행 권한을 추가하지 않는다. 최신 모델이 투자 정확도·수익·계정 호출 성공을 보장하지는 않는다.

| Provider | 이번 목록 변경 | 앱에서 연결하는 기능 |
|---|---|---|
| OpenAI | GPT-6 Luna, GPT-6.1 Sol, GPT-6 Sol 추가 | 텍스트·JSON·이미지 입력; 음성 전사는 기존 별도 프로필 |
| DeepSeek | `deepseek-flash` 추가, 구 Flash/vision-exp는 임시 호환 ID로 안내 | 새 Flash는 텍스트·JSON·이미지; 구 텍스트 ID의 이미지 경로는 자동 확대하지 않음 |
| Anthropic | Sonnet 5.5, Opus 5.5 추가; Fable 5.1 유지 | 현재 앱 어댑터의 텍스트·JSON만; Provider 자체 비전과 구분 |
| Kimi | K2.7 Code 및 HighSpeed 추가, K3 기본 가격 보완 | 텍스트·JSON·이미지; 코딩 특화, 일반 분석 기본값 자동 변경 없음 |
| Gemini | 최신 3.8 Flash와 3.5 Flash-Lite 재확인·유지 | 기존 텍스트·JSON·이미지 경로 |

HighSpeed처럼 단가를 확정하지 않은 항목은 가격 미등록/비용 미산출이며 0달러가 아니다. 기존 모델·역할·API 키·예산·개인정보 경로·승인·PAPER/LIVE 정책을 유지한다. 계정에서 발견한 미등록 모델은 호환 확인 필요 경고를 표시한다.

## 구현 순서와 결함 보완

1. 공통 model_registry → 라우터·Web/기존 UI 목록, provider_catalog → 가격·기능 안내를 연결한다. UI 별도 이름은 표시용이다.
2. GPT-6 JSON 점검의 reasoning_effort 인자 누락을 수정한다. 고정 연결 점검에서 Luna/Sol은 none, Astra/6.1 Sol은 low를 사용한다. 일반 작업의 추론 기본값·출력 상한은 확대하지 않는다.
3. GPT-6 추론 모드의 sampling 옵션, completion token 파라미터, Kimi K2/K3 토큰 키를 구분한다. 최신 Claude와 날짜 suffix에도 비호환 temperature를 보내지 않는다. 요청/실제 응답 모델을 구분한다.
4. DeepSeek 최신 ID와 이전 이름 설명을 설정·로컬 AI 안내·매뉴얼에서 정정한다. 구 ID의 Provider 측 임시 라우팅과 NoahAI의 사용자 설정 변경은 다르다.
5. 가격은 표준 참고값이다. GPT-6의 272K 초과 입력 할증과 정확한 날짜 suffix 가격 매칭을 보완한다. 캐시 읽기는 일반 입력으로 추정하며 쓰기·지역·티어 등 실제 청구는 다를 수 있다. 기존 과거 비용 원장은 재작성하지 않는다.
6. 요청/진단·작업별 권한·비용·기존 기본값 보존 회귀, 전체 시험, renderer 빌드를 수행한다. 결과 정본은 TEST_STATUS다.

## 사용 방법

설정 → AI 엔진/API → 나만의 AI 구성 · 작업별 모델에서 빈번·저비용 역할에 OpenAI / gpt-6-luna를 선택하고 저장한다. 연결 점검은 화면에 표시된 점검 대상 모델을 확인한다. 애널리스트 선택 모델의 `선택 모델 1회 실제 호출 점검`은 유료 호출일 수 있다. 다른 역할의 점검 성공을 뜻하지 않는다.

도움말·요약·반복 구조화는 Luna 후보 용도다. 복잡한 전략 해석은 대표 사례로 품질을 비교하고 정밀 모델을 별도 배치한다. 비용 한도·캐시·속도 제한을 유지하며 Chat Completions 앱이 Responses 전용 도구까지 지원한다고 표시하지 않는다.

## 공식 확인 자료

- [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna): 표준 입력 $0.10/출력 $0.50, 각각 100만 토큰.
- [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol), [GPT-6 Sol](https://developers.openai.com/api/docs/models/gpt-6-sol), [마이그레이션](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra.md#migration-quickstart).
- [DeepSeek 가격/별칭](https://api-docs.deepseek.com/quick_start/pricing/), [이미지 입력](https://api-docs.deepseek.com/guides/vision/).
- [Claude 모델](https://platform.claude.com/docs/en/models/overview), [Opus 5.5 호환](https://platform.claude.com/docs/en/models/opus-5-5/migration-guide), [Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/overview).
- [Kimi 기본 가격](https://platform.kimi.ai/), [K2.7 Code API](https://platform.kimi.ai/docs/guide/kimi-k2-7-code-quickstart).
- [Gemini 최신 모델](https://ai.google.dev/gemini-api/docs/latest-model), [가격](https://ai.google.dev/gemini-api/docs/pricing): Flash 소개 가격은 2026-12-31까지.

목록은 날짜가 있는 스냅샷이며 구형 모델의 영구 제공/가격이나 계정 권한·실호출·지연·정확도를 보증하지 않는다. 이번 개발에서는 고객 키 유료 호출·실제 주문·Windows 게시를 수행하지 않는다.
