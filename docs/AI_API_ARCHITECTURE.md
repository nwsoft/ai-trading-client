# AI API 아키텍처 및 멀티 제공사 가이드

> 기준: 2026-07-29 · v3.9.0.4 업데이트 배포 대상. 멀티 Provider 구현은 v3.9.0.3 후보에서 시작해 v3.9.0.4에 포함  
> 이 문서는 AI 호출 계층의 기술 정본입니다. 금융 인텔리전스 UI·데이터 상태는 `FINANCIAL_INTELLIGENCE_EXPANSION_PLAN_20260723.md`, 사용자 사용법은 `USER_GUIDE.md`와 인앱 매뉴얼을 따릅니다.

## 📋 목적
NoahAI의 AI API 구조를 이해하고, 향후 오픈소스 LLM으로 전환할 수 있도록 설계된 아키텍처를 문서화합니다.

---

## 🏗️ 현재 AI API 구조

### 계층 구조
```
AIManager (trading/ai/ai_manager.py)
  ├─ AIProviderRouter (trading/ai/provider_router.py)
  │   ├─ OpenAICompatibleAdapter
  │   │   ├─ OpenAI
  │   │   ├─ DeepSeek V4 Flash/Pro
  │   │   ├─ Google Gemini
  │   │   └─ Kimi K3/K2.6 (어시스턴트용 NoahAI 시험 연동)
  │   ├─ AnthropicClient (네이티브 Messages API)
  │   ├─ ProviderCapabilities
  │   └─ ProviderResponse / NormalizedProviderError
  ├─ 로컬 credential 호환 계층 (trading/ai/credentials.py)
  │   └─ 거래소·증권사 키와 같은 사용자별 settings.json 정책
  ├─ OpenAIClient (하위 호환 SDK 래퍼)
  ├─ ModelRegistry (권장/미리보기/비권장/종료/capability)
  ├─ 작업별 route: ai_model_roles.<tier> = {provider, model}
  ├─ 독립 전사 route: ai_provider_profiles.transcription
  └─ 주요 기능:
      ├─ 시장 분석 (analyze_market_conditions)
      ├─ 청산 분석 (analyze_exit_conditions)
      ├─ 패턴 유사성 검증 (verify_pattern_similarity)
      └─ 대화형 AI (chat_completion)
```

AlphaArena 멀티 엔진·실거래 라우팅은 이번 v3.9.0.3 업데이트 범위가 아니다. 종료된
DeepSeek V3.1 모델만 V4 Flash로 이전하며 기존 주문 가드레일과 단일 실행
흐름을 유지한다.

Claude Code 앱/CLI 로그인이나 Claude 구독을 자격증명으로 재사용하지 않는다. NoahAI의
Claude 선택지는 Anthropic Console에서 발급한 별도 API 키와 API 과금을 사용한다.
Gemini도 Google AI Studio에서 발급한 Gemini API 키를 사용한다.

설정 화면의 가격 비교는 `2026-07-28`, USD/100만 토큰 기준 스냅샷이다. 캐시·장문·배치·
지역·서비스 티어에 따라 실제 청구가 달라지므로 각 제공사의 공식 가격 링크를 함께 표시한다.

### 현재 호출 경로의 비용 특성 (2026-07-24 점검)

현재 코드는 AI가 활성화되면 최종 LONG/SHORT가 확정된 뒤에만 호출하는 구조가 아니다.

1. `TradingWorker`가 `auto_trade_interval`에 따라 거래 사이클을 반복한다. 사용자 점검 설정값은 10초였다.
2. `Trader.execute_trading_cycle()`과 `UnifiedTrader.analyze_coins_unified()`가 분석 대상 심볼을 순회한다.
3. `Analyzer.generate_trading_signal()`은 기술 신호를 최종 필터링하기 전에 `AIManager.analyze_market_conditions()`를 호출한다.
4. AI 응답을 받은 뒤 LONG/SHORT/HOLD를 결정하고 학습 레코드를 저장한다.
5. LONG/SHORT 후보는 패턴·진입 전 검증 등 추가 AI 호출이 발생할 수 있다.

기존에는 거래가 0건이어도 AI 활성 상태에서 심볼 분석이 반복되면 비용이 발생했다. v3.9.0.1 후속 패치부터 `OpportunityAwareInferencePolicy`가 로컬 신호를 먼저 계산하고 동일 상태는 캐시한다. 새 캔들·가격·RSI·MACD·국면 변화 또는 탐색 주기에는 즉시 재분석한다. 일·월·거래소별 예산 소진 시에도 로컬 신호와 주문 경로는 중단하지 않는다. 다심볼 단일 요청은 신호 품질 A/B 전이므로 남아 있다.

v3.9.0.4 감사에서는 시장분석 정책 밖의 보조 호출도 별도로 제한했다. `Optimizer`의 포지션 크기 요청은 신선한 15분 캐시를 우선하고 방향·1% 가격·0.10 신뢰도 변화에서만 갱신한다. `AIManager`의 손실패턴 비교는 동일 신호·동일 손실 표본을 5분 재사용한다. 두 경로는 실패 후 120초 쿨다운을 사용한다. 성과 기반 파라미터 최적화는 최소 10거래 후 새 5거래마다 한 번만 역할별 Provider로 요청하며 동일 실패 표본을 거래 사이클마다 반복하지 않는다.

현재 호출 경로:

```
로컬 기술 신호
  ├─ LONG/SHORT 후보 또는 시장 이벤트 → LLM 신규 호출
  ├─ 동일 시장상태 → 15분 캐시 재사용
  └─ 안정 HOLD 또는 예산 소진 → 로컬 결과로 계속 운용
```

보조 호출 경계:

```
최종 진입 후보
  ├─ 포지션 크기 → 15분 상태 캐시 + 변화 이벤트 + 실패 120초 쿨다운
  └─ 최근 손실패턴 있음 → 동일 패턴 5분 캐시 + 실패 120초 쿨다운

완료 거래
  ├─ 손익 복기 → 포지션 종료 이벤트당 1회
  └─ 임계값 최적화 → 10거래 이후 새 5거래당 최대 1회

사용자 작업
  └─ 전략 원문·차트·어시스턴트 → 사용자가 요청한 때만 호출
```

`trade_enabled_exchanges`가 실제 주문 범위, `learning_enabled_exchanges`가 학습 범위다. 주문 키가 명시적으로 빈 목록이면 실제 주문은 0개다. 주문 키 자체가 없는 구버전 프로필만 선택 거래소 1곳으로 호환하며, 학습 범위가 비면 활성 거래소 전체를 사용한다.

### 2026-07-24 사용자 데이터 교차 점검

- 비용 CSV: 2026-05 $62.05, 2026-06-01~07-01 $51.73, 2026-07-21~23 $9.08
- 2026-07-21~23 모델 요청: 27,879회, 일평균 9,293회
- 최근 3일 속도 단순 환산: 30일 약 $90.82
- 선택 거래소는 Binance였지만 활성 거래소에는 Binance·Upbit·Bithumb·Bybit·OKX·Bitget 6개가 모두 포함
- 6개 거래소 로그가 2026-07-21~23 구간에 생성됨
- 전체 점검 기간 모델 비용 중 출력 토큰 67.5%, 캐시 입력 약 0.001%

OpenAI 비용 CSV는 프로젝트 단위이고 거래소 메타데이터를 포함하지 않으므로 거래소별 정확한 비용 배분은 할 수 없다. 다만 활성 거래소·로그·학습 파일을 함께 보면 최근 구간을 “Binance 한 곳 비용”으로 해석하면 안 된다.

### 핵심 클래스

#### 1. AIProviderRouter (`trading/ai/provider_router.py`)

- 설정 프로필에서 제공사·모델·로컬 API 키를 읽습니다.
- 애널리스트·어시스턴트뿐 아니라 frequent_cheap·standard·premium 작업 route를 각각 해석합니다.
- OpenAI·DeepSeek·Kimi·Gemini는 호환 어댑터로, Claude는 네이티브 Messages 클라이언트로 연결합니다.
- 모델 목록, 텍스트·JSON, usage·오류 정규화와 capability 검사를 공통 계약으로 제공합니다.
- 실거래 경로는 제공사 실패 때 다른 제공사로 임의 전환하지 않습니다.

#### 2. OpenAIClient / AnthropicClient

- `OpenAIClient`는 OpenAI와 공식 호환 엔드포인트의 텍스트·JSON 응답을 공통화합니다.
- `AnthropicClient`는 `x-api-key`와 Anthropic Messages 규약을 사용합니다.
- 비전·음성 등 capability가 없는 제공사에는 해당 호출을 보내지 않습니다.

#### 3. AIManager

- 시장 분석·청산 분석·패턴 검증·대화 기능은 Router의 공통 facade를 사용합니다.
- 역할별 route의 Provider가 다르면 해당 Provider credential과 client facade를 별도로 생성·재사용합니다.
- AI가 비활성화되거나 호출 예산을 소진하면 로컬 분석으로 계속 운용합니다.
- Provider Router는 모델 호출 계층이며 주문 권한·실제 주문 거래소·손실 가드레일을 변경하지 않습니다.

---

## 🔄 제공사 전환 방법

### 현재 구조의 장점
`AIProviderRouter`가 제공사별 Base URL, 모델 목록, capability와 응답 정규화를
관리한다. 사용자는 설정 화면에서 제공사를 선택하며 API 키를 JSON에 직접
작성하지 않는다.

### 전환 시나리오

#### 시나리오 1: DeepSeek API 사용
```python
{
  "ai_provider": "deepseek",
  "ai_credentials": {
    "deepseek": {
      "api_key": "<사용자별 로컬 설정>",
      "base_url": "https://api.deepseek.com"
    }
  },
  "ai_provider_profiles": {
    "analyst": {"provider": "deepseek", "model": "deepseek-v4-flash"},
    "assistant": {"provider": "deepseek", "model": "deepseek-v4-flash"},
    "transcription": {"provider": "openai", "model": "gpt-4o-mini-transcribe"}
  },
  "ai_model_roles": {
    "frequent_cheap": {"provider": "deepseek", "model": "deepseek-v4-flash"},
    "standard": {"provider": "openai", "model": "gpt-5.6-terra"},
    "premium": {"provider": "anthropic", "model": "claude-opus-5"}
  }
}

# 런타임
router = AIProviderRouter.from_settings(settings, workload="assistant")
client = router.client_facade()
```

#### 시나리오 2: Anthropic Claude 사용
```python
{
  "ai_provider": "anthropic",
  "ai_provider_profiles": {
    "analyst": {"provider": "anthropic", "model": "claude-sonnet-5"},
    "assistant": {"provider": "anthropic", "model": "claude-haiku-4-5"}
  }
}
```

#### 시나리오 3: Google Gemini 사용
```python
{
  "ai_provider": "gemini",
  "ai_provider_profiles": {
    "analyst": {"provider": "gemini", "model": "gemini-3.6-flash"},
    "assistant": {"provider": "gemini", "model": "gemini-3.5-flash-lite"}
  }
}
```

### 전환 절차
1. 앱 `설정 → AI 엔진/API`에서 제공사를 선택합니다.
2. 선택 제공사의 API 키를 사용자별 로컬 설정에 저장합니다.
3. 계정 모델 목록을 새로고침하고 역할별 모델을 선택합니다.
4. 저장 시 정적 capability·종료 상태를 검사하고, 키가 있으면 실제 계정 모델 목록도 확인합니다.
5. `실제 API 기능 검증`에서 텍스트·JSON·usage·정규화 오류와 선택적 음성 전사를 확인합니다.
6. 연결 실패 시 이전 설정을 유지하며 다른 제공사로 실거래를 자동 우회하지 않습니다.

### 음성 전사 분리

`StrategySourceIngestor`는 전략 구조화용 `ai_client`와 음성 전사용
`transcription_client`를 별도로 받습니다. 따라서 premium 분석 route가 Claude·DeepSeek·
Gemini여도 무자막 YouTube 전사는 `workload="transcription"`의 OpenAI credential과
전사 모델로 실행됩니다. 공개 자막 우선 정책은 유지합니다.

### 모델 수명주기

`trading/ai/model_registry.py`가 공식 기준 스냅샷과 capability를 관리합니다.

- `recommended`: 신규 기본 권장
- `available`: 사용 가능하지만 최신 기본은 아님
- `preview`: 미리보기이며 수명주기가 짧을 수 있음
- `deprecated`: 비권장 또는 종료 예정, 대체 모델 표시
- `retired`: 선택 목록 제외 및 저장 차단
- `experimental`: 공식 모델이지만 NoahAI 실제 키 검증 대기

API `list models` 결과는 수명주기와 별개로 `계정 확인됨` 상태를 부여합니다. 정적
목록에 있다는 사실만으로 계정 권한이나 실제 호출 성공을 주장하지 않습니다.

OpenRouter·로컬 LLM의 사용자 지정 Base URL은 고급 호환 실험 범위이며 이번 v3.9.0.3 정식 제공사 검증 범위가 아닙니다.

---

## 📝 ETF 개발 시 AI API 활용 가이드

### 1. AIManager 초기화
```python
# ETF Trader 초기화 시
class ETFTrader:
    def __init__(self, exchange_adapter, settings, ai_manager=None):
        self.exchange = exchange_adapter
        self.settings = settings
        # ⚠️ 중요: ai_manager는 main.py에서 초기화되어 전달받음
        # 직접 초기화하지 않음
        self.ai_manager = ai_manager
```

### 2. AI 분석 활용 패턴
```python
# ETF 신호 생성 시
def generate_etf_signal(self, symbol: str):
    # ... 기술적 분석 ...
    
    # AI 분석 (암호화폐와 동일한 패턴)
    if self.ai_manager and self.ai_manager.enabled():
        ai_analysis = self.ai_manager.analyze_market_conditions(
            symbol=symbol,
            market_data=[...],
            indicators={...}
        )
        # AI 분석 결과 반영
    else:
        # AI 비활성화 시 기본 분석만 사용
        pass
```

### 3. AI 가드 체크 필수
```python
# ⚠️ 항상 가드 체크 필요
if self.ai_manager and self.ai_manager.enabled():
    # AI 사용
    result = self.ai_manager.analyze_market_conditions(...)
else:
    # AI 비활성화 시 폴백
    result = self._basic_analysis(...)
```

### 4. 에러 처리
```python
try:
    if self.ai_manager and self.ai_manager.enabled():
        ai_result = self.ai_manager.analyze_market_conditions(...)
except Exception as e:
    self.logger.error(f"AI 분석 오류: {e}")
    # AI 오류 시 기본 분석으로 폴백
    ai_result = None
```

---

## 🚀 제공사·오픈소스 로드맵

### Phase 1: 기존 OpenAI 호환
- [x] 기존 OpenAI 설정과 Base URL 호환 유지

### Phase 2: v3.9.0.3 업데이트 배포 대상
- [x] OpenAI·DeepSeek·Claude·Gemini 정식 Router 등록
- [x] Kimi K3 어시스턴트 시험 등록
- [x] 동적 모델 목록, capability, 로컬 자격증명 호환, 응답·사용량·오류 정규화
- [ ] 실제 제공사 키 인증·모델 목록·과금 계정 E2E
- [ ] 서명된 Windows 설치본 연결·업데이트 E2E

### Phase 3: 후속 오픈소스 전환
- [ ] 로컬 LLM 서버 지원 (Ollama, LM Studio 등)
- [ ] 완전 오프라인 모드
- [ ] 외부 토큰 비용 제거와 로컬 장비·전력·운영비를 포함한 총비용 검증

---

## ⚠️ 개발 시 주의사항

### 1. AI 호출 최적화
- 현재 상태: 로컬 신호를 먼저 만들고 시장 이벤트·거래 후보·탐색 주기에만 LLM을 새로 호출한다.
- 모델 티어: `frequent_cheap`, `standard`, `premium` 역할 분리는 제공되지만 티어 변경만으로 호출 폭주를 막을 수 없다.
- 완료 게이트: 일·월·거래소별 시장분석 요청 수를 영속 저장하고 초과 시 로컬 분석으로 폴백한다.
- 완료 필터: 로컬 기술지표·시장상태 변경 검사와 LONG/SHORT 후보를 먼저 계산한다.
- 완료 캐시: 동일 시장상태는 15분 재사용하되 봉 마감·가격·RSI·MACD·국면 변화는 즉시 우회한다.
- P1 배치: 동일 주기의 여러 심볼을 한 요청으로 묶고 출력 스키마를 짧게 제한한다.
- P1 캐시: 고정 시스템 프롬프트를 앞부분에 유지하고 실제 cached input 비율을 운영 KPI로 기록한다.
- 완료 분리: 실제 주문과 학습 거래소 범위를 독립 제어한다.

### 2. 오픈소스 전환 고려
- **base_url 설정**: 항상 설정 파일에서 읽도록 구현
- **모델 호환성**: 공식 호환 API와 Anthropic 네이티브 Messages 계약을 제공사별로 분리
- **에러 처리**: API 변경 시에도 안정적으로 동작

### 3. 코드 일관성
- **가드 체크**: 항상 `if self.ai_manager and self.ai_manager.enabled()` 사용
- **에러 폴백**: AI 실패 시 기본 분석으로 폴백
- **로깅**: AI 호출 및 결과 로깅

---

## 📚 참고 코드

### AIManager의 Router 초기화 (`trading/ai/ai_manager.py`)
```python
if settings:
    self._provider_router = AIProviderRouter.from_settings(
        settings,
        workload="analyst",
        api_key_override=api_key,
    )
```

### AI 분석 활용 (trader.py)
```python
# 패턴 유사성 검증
if self.ai_manager and self.ai_manager.enabled():
    pattern_check = self.ai_manager.verify_pattern_similarity(...)
    if pattern_check['action'] == 'BLOCK':
        return
```

### AI 청산 분석 (unified_trader.py)
```python
# 청산 판단
if self.ai_manager and self.ai_manager.enabled():
    exit_analysis = self.ai_manager.analyze_exit_conditions(...)
    if exit_analysis.get('should_exit'):
        self._close_position(...)
```

---

## ✅ 체크리스트

### ETF 개발 시
- [ ] AIManager를 직접 초기화하지 않고 전달받음
- [ ] AI 가드 체크 필수 (`if self.ai_manager and self.ai_manager.enabled()`)
- [ ] AI 실패 시 기본 분석으로 폴백
- [ ] 자산 타입 명시 (`asset_type='etf'`)
- [ ] 오픈소스 전환 고려 (base_url 설정 지원)

### 오픈소스 전환 준비
- [x] 기존 `openai_base_url` 호환 유지
- [x] 정식 제공사 엔드포인트를 ProviderSpec으로 분리
- [x] 5개 제공사 모델 계약·가격 카탈로그 무자격증명 회귀
- [ ] 실제 제공사 키로 모델 목록·텍스트·JSON·사용량·오류 검증
- [ ] 로컬 LLM 서버 연동 테스트
- [ ] 로컬 모델의 지연·정확도·운영비 비교
- [ ] OpenAI 프로젝트/키/사용자/거래소별 비용 귀속 메타데이터
- [x] 요청 예산·시장 이벤트·중복 제거·거래 기회 보존 회귀 테스트
- [ ] 다심볼 배치 분석 품질·비용 A/B
