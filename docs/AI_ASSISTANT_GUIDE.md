# NoahAI AI 어시스턴트 가이드 (대시보드)

이 문서는 **공개 저장소 기준**으로 `ui/widgets/ai_assistant_widget.py`의 실제 동작과 맞추었습니다. 설치 후 바로 확인할 수 있도록 **전제 조건 → UI 위치 → 대화로 되는 일/안 되는 일 → 설정 자동 반영 규칙 → 트러블슈팅 → 음성(STT/TTS) 로드맵** 순으로 읽으면 됩니다.

상위 원칙·책임 경계는 `docs/ARCHITECTURE.md`, 문서 간 우선순위는 `docs/DOCUMENTATION_POLICY.md`를 참고하세요.

---

## 1. 이 앱에서 AI 어시스턴트가 하는 일

NoahAI 클라이언트는 사용자가 연결한 거래소 API와 설정 범위 안에서 **판단·설명·일부 설정 변경**을 돕습니다. **체결·잔고 확정**은 거래소 쪽 책임이며, 어시스턴트는 브로커가 아닙니다.

AI 어시스턴트 탭은 대략 다음을 수행합니다.

- **일반 질문**: 대시보드에서 수집한 **거래·계정 컨텍스트 문자열**과 함께 LLM에 질의하여 분석·조언 텍스트를 표시합니다.
- **설정 변경으로 분류되는 질문**: 모델이 특정 **JSON 형식**으로 답하면, 검증 후 `settings.json`에 저장하고 대시보드 설정을 갱신합니다.
- **차트 이미지 분석**: `ChartScreenshotWidget` 모듈이 로드되는 빌드에서만 **「📊 차트 이미지 분석」** 버튼이 동작합니다. 임포트 실패 시 경고만 표시됩니다.

**대화만으로 할 수 없는 것(현재 코드 기준)**

- 거래 **시작/중지**, 주문 직접 하기, 다른 탭으로 전환, API 키 입력 등 **전체 앱 조작**은 채팅으로 연결되어 있지 않습니다.
- **「설정관리」** 모달의 일부 기능(예: 이력 되돌리기·기본 전략 복구)은 UI에 있어도 **실제 복원 로직이 TODO**인 부분이 있을 수 있습니다. 설정 자동 저장 경로는 아래 JSON 규칙이 확실합니다.

---

## 2. 시작하기 전에 (필수)

### 2.1 설치·실행

1. `docs/INSTALLATION.md` — Python 버전, `pip install -r requirements.txt`(또는 Windows용 파일), `python3 main.py` 실행.
2. 문제 발생 시 `docs/TROUBLESHOOTING.md`.

### 2.2 AI API 설정

설정(`settings.json` 또는 앱 내 설정 UI)에 다음이 필요합니다.

| 키 | 설명 |
|----|------|
| `openai_api_key` | OpenAI 호환 API 키. 비어 있으면 `ai_assistant_widget`에서 AI 기능이 비활성화됩니다. |
| `assistant_ai_model` | 어시스턴트 전용 모델명(미설정 시 위젯에서 정규화 후 기본값 사용). |
| `openai_model` / `openai_base_url` | 트레이딩용 AI와 공통 `AIManager` 구성에 사용. **다른 벤더(DeepSeek, OpenRouter, 로컬 OpenAI 호환 서버)** 는 `docs/AI_API_ARCHITECTURE.md` 참고. |

앱 실행 후 대시보드에서 **「💬 AI 어시스턴트」**(또는 제품 버전에 따른 동일 탭)을 엽니다. 상단에 **「현재 어시스턴트 모델: …」** 캡션이 보이면 위젯이 로드된 것입니다.

---

## 3. 어시스턴트가 참고하는 «현재 상황» 컨텍스트

`parent_dashboard`와 거래소 매니저가 연결되어 있으면, 매 질의마다 `_get_current_trading_context()`가 대략 다음 정보를 **한 덩어리 텍스트**로 만듭니다(일부는 거래소/API 상태에 따라 «조회 실패» 등으로 끊길 수 있음).

- 선택 거래소, 연결 상태(참고용 — **설정 파일 저장과는 독립**이라는 규칙이 설정 변경 프롬프트에 명시됨)
- 잔고·USDT 환산 등
- `default_leverage`, `default_tp`, `default_sl`, `min_trade_amount`, RSI·변동성·`ai_trading_preferences`·`ai_exit_settings` 등 **현재 설정 스냅샷**
- 거래 통계 요약, 활성 포지션 요약, 시장 데이터 일부, 선택 코인·분석 요약, AI 학습 패턴 수, CPU/메모리 등

따라서 **같은 질문이라도 시점·연결 상태에 따라 답이 달라지는 것이 정상**입니다. 컨텍스트가 비어 있거나 오류 문자열만 있으면 LLM 품질이 떨어질 수 있으므로, 먼저 거래소 연결·API 키·대시보드 탭에서 선택한 거래소를 확인하세요.

---

## 4. 대화 흐름 두 가지

### 4.1 일반 질문

설정 변경으로 분류되지 않으면, 시스템 프롬프트는 **시장·거래 조언** 위주입니다. 응답은 채팅창에 그대로 표시됩니다. 응답 안에 «권장 설정» 등이 포함되면, 키워드 기반으로 **권장 설정 딕셔너리**가 채워질 수 있으며(휴리스틱), **「설정관리」**에서 적용 여부를 이어갈 수 있습니다.

### 4.2 설정 변경으로 분류되는 질문

메시지에 아래 **키워드 중 하나라도** 포함되면(대소문자 무시) 설정 변경 모드로 들어갑니다.

`레버리지`, `leverage`, `tp`, `sl`, `손절`, `익절`, `설정`, `변경`, `바꿔`, `조정`, `수정`, `설정해`, `내려`, `높여`, `줄여`, `낮춰`, `증가`, `감소`, `보수`, `적극`, `conservative`, `aggressive`, `moderate`, `리스크`, `risk`, `거래 성향`

주의: **「설정」**처럼 넓은 단어가 포함되면 일상 질문도 설정 모드로 분류될 수 있습니다. 모호하면 **구체적으로** «레버리지를 3으로», «TP를 낮춰줘»처럼 쓰는 것이 안전합니다.

이 모드에서는 모델에게 **반드시 JSON**으로 답하라고 요청합니다. 앱이 파싱하는 형식은 다음과 같습니다.

- 우선 마크다운 코드 펜스로 감싼 JSON 블록(펜스 첫 줄이 json 언어 태그인 형태)을 파싱합니다.
- 실패 시 `"action"`·`"settings"`가 포함된 `{...}` 패턴을 정규식으로 찾습니다.

**성공 시** `action`이 `"settings_change"`이고 `settings`에 허용된 키가 있어야 자동 적용됩니다.

**자동 적용 시 실제로 갱신되는 키 예시** (`_apply_settings_automatically` 기준)

- 최상위: `default_leverage`, `default_tp`, `default_sl` 등 일반 설정 키.
- `risk_tolerance`, `balance_utilization_limit`는 **`ai_trading_preferences` 내부**로 넣어 저장합니다.

모델이 JSON을 어기면 텍스트만 표시되고, 키워드 기반 **fallback 권장 설정**으로 넘어갈 수 있습니다.

---

## 5. 설정 변경 JSON 예시 (복사해 참고용)

아래는 모델 응답 예시입니다. 실제 숫자는 현재 전략에 맞게 조정해야 합니다.

```json
{
  "action": "settings_change",
  "message": "보수적으로 조정했습니다.",
  "settings": {
    "default_leverage": 3,
    "default_tp": 0.015,
    "default_sl": 0.012
  },
  "reason": "변동성 완화"
}
```

리스크 성향만 바꿀 때 예시:

```json
{
  "action": "settings_change",
  "message": "거래 성향을 보수적으로 변경합니다.",
  "settings": {
    "risk_tolerance": "CONSERVATIVE",
    "balance_utilization_limit": 0.15
  },
  "reason": "사용자 요청"
}
```

적용 후에는 `save_settings`가 성공해야 하며, 대시보드에 `on_settings_changed`가 있으면 호출됩니다. **가드레일**(레버리지 상한, 최소 노셔널 등)은 트레이딩 경로에서 별도로 적용되므로, 대화에서 나온 수치와 최종 주문이 다를 수 있습니다. 개요는 기존 가이드 문단과 동일합니다.

- 레버리지 clamp, 마진 타입, 최소 노셔널 등: `README.md` 및 `docs/ARCHITECTURE.md`의 가드레일 설명 참고.

---

## 6. UI에서 바로 쓸 수 있는 것

- **자주 하는 질문** 버튼(우측 열): 미리 정의된 문장을 입력창에 넣고 전송합니다.
- **전송**: 채팅 질의.
- **설정관리**: 모달에서 이력 확인·권장 설정 적용 등(기능은 버전별로 상이할 수 있음).
- **📊 차트 이미지 분석**: 스크린샷 기반 질문용 별도 창. 모듈 미로드 시 경고.

---

## 7. 트러블슈팅

| 증상 | 확인 |
|------|------|
| «AI 기능이 비활성화» / API 키 안내 | `openai_api_key` 설정 후 앱 재시작. `AIManager.enabled()`가 거짓이면 동일. |
| «AI 매니저가 활성화되지 않았습니다» | 키·네트워크·`openai_base_url` 호환 여부. `docs/AI_API_ARCHITECTURE.md`. |
| 설정 변경 말했는데 텍스트만 옴 | 모델 응답이 **유효 JSON 블록**인지 확인. `action`/`settings` 철자. |
| «대시보드에 연결되지 않아 설정을 적용할 수 없습니다» | 위젯의 `parent_dashboard`가 주입되지 않은 상태. 대시보드에서 탭을 연 경로인지 확인(개발 시 위젯 단독 테스트면 발생). |
| 컨텍스트가 비어 있거나 엉뚱함 | 선택 거래소, API 키, `ExchangeManager` 연결, 대시보드에 `settings`가 있는지 확인. |
| 차트 분석 버튼이 안 됨 | `chart_screenshot_widget` 임포트 실패 로그. 의존성/경로 확인. |

---

## 8. 음성 STT / TTS (현재 구현 + 운영 주의)

현재 저장소 기준으로 AI 어시스턴트 음성 기능은 다음 범위까지 구현되어 있습니다.

- STT 입력: `ui/widgets/ai_assistant_widget.py`의 `🎤 음성입력` 버튼으로 마이크 음성을 텍스트로 변환하여 입력창에 주입
- TTS 출력: `assistant_voice.auto_tts=true`일 때 AI 답변을 OS 기본 엔진으로 읽기
- 음성 모듈: `ui/widgets/ai_voice_module.py`
  - macOS TTS: `say`
  - Windows TTS: PowerShell SpeechSynthesizer
  - STT: `SpeechRecognition` 사용 (`transcribe_microphone`)

의존성/배포 주의

- STT는 선택 의존성입니다. 미설치 시 `not_available`로 폴백됩니다.
- 배포 환경에서는 아래 패키지 포함 여부를 반드시 확인하세요.
  - `SpeechRecognition>=3.10.0`
  - `pyaudio>=0.2.14`
- macOS는 PortAudio 선설치가 필요할 수 있습니다.

제약 사항

- 현재 구현은 **음성 입력 보조 + 음성 읽기** 중심입니다.
- 사용자가 음성만으로 앱의 모든 기능을 직접 제어하는 전면 음성 UI(권한·화이트리스트 기반 명령 실행)는 별도 단계입니다.

권장 운영 흐름

1. 설정에서 `assistant_voice.enabled=true` 후 마이크 권한 확인
2. `🎤 음성입력`으로 질문 입력 → AI 분석/설정 제안 확인
3. 설정 변경은 AI 제안(JSON)을 검토 후 사용자 확인 기반으로 적용

---

## 9. 더 읽을 문서

- `docs/INSTALLATION.md` — 설치·실행  
- `docs/USER_GUIDE.md` — 전체 기능·대시보드 사용 설명  
- `docs/AI_API_ARCHITECTURE.md` — OpenAI 호환 API·베이스 URL  
- `docs/ARCHITECTURE.md` — 모듈·책임 경계  
- `docs/TRADING_FLOW.md` — 거래·AI 신호 흐름  
- `docs/CHANGELOG.md` — 버전별 변경(어시스턴트 관련 수정 포함)

---

**요약**: AI 어시스턴트는 **컨텍스트가 붙은 채팅 조언**과, 조건이 맞을 때 **JSON 기반 설정 자동 저장**에 강점이 있습니다. **모든 기능을 대화만으로 조작**하는 단계는 아니며, 그 부분은 로드맵과 별도 설계가 필요합니다.
