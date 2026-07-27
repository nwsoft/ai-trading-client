# AI API 아키텍처 및 오픈소스 전환 가이드

> 기준: 2026-07-26 · v3.9.0.2  
> 이 문서는 AI 호출 계층의 기술 정본입니다. 금융 인텔리전스 UI·데이터 상태는 `FINANCIAL_INTELLIGENCE_EXPANSION_PLAN_20260723.md`, 사용자 사용법은 `USER_GUIDE.md`와 인앱 매뉴얼을 따릅니다.

## 📋 목적
NoahAI의 AI API 구조를 이해하고, 향후 오픈소스 LLM으로 전환할 수 있도록 설계된 아키텍처를 문서화합니다.

---

## 🏗️ 현재 AI API 구조

### 계층 구조
```
AIManager (trading/ai/ai_manager.py)
  ├─ OpenAIClient (trading/ai/openai_client.py)
  │   ├─ OpenAI SDK 래퍼
  │   ├─ base_url 지원 (오픈소스 LLM 전환)
  │   └─ model 설정 가능
  └─ 주요 기능:
      ├─ 시장 분석 (analyze_market_conditions)
      ├─ 청산 분석 (analyze_exit_conditions)
      ├─ 패턴 유사성 검증 (verify_pattern_similarity)
      └─ 대화형 AI (chat_completion)
```

### 현재 호출 경로의 비용 특성 (2026-07-24 점검)

현재 코드는 AI가 활성화되면 최종 LONG/SHORT가 확정된 뒤에만 호출하는 구조가 아니다.

1. `TradingWorker`가 `auto_trade_interval`에 따라 거래 사이클을 반복한다. 사용자 점검 설정값은 10초였다.
2. `Trader.execute_trading_cycle()`과 `UnifiedTrader.analyze_coins_unified()`가 분석 대상 심볼을 순회한다.
3. `Analyzer.generate_trading_signal()`은 기술 신호를 최종 필터링하기 전에 `AIManager.analyze_market_conditions()`를 호출한다.
4. AI 응답을 받은 뒤 LONG/SHORT/HOLD를 결정하고 학습 레코드를 저장한다.
5. LONG/SHORT 후보는 패턴·진입 전 검증 등 추가 AI 호출이 발생할 수 있다.

기존에는 거래가 0건이어도 AI 활성 상태에서 심볼 분석이 반복되면 비용이 발생했다. v3.9.0.1 후속 패치부터 `OpportunityAwareInferencePolicy`가 로컬 신호를 먼저 계산하고 동일 상태는 캐시한다. 새 캔들·가격·RSI·MACD·국면 변화 또는 탐색 주기에는 즉시 재분석한다. 일·월·거래소별 예산 소진 시에도 로컬 신호와 주문 경로는 중단하지 않는다. 다심볼 단일 요청은 신호 품질 A/B 전이므로 남아 있다.

현재 호출 경로:

```
로컬 기술 신호
  ├─ LONG/SHORT 후보 또는 시장 이벤트 → LLM 신규 호출
  ├─ 동일 시장상태 → 15분 캐시 재사용
  └─ 안정 HOLD 또는 예산 소진 → 로컬 결과로 계속 운용
```

`trade_enabled_exchanges`가 실제 주문 범위, `learning_enabled_exchanges`가 학습 범위다. 두 값이 비어 있으면 선택 거래소만 주문하고 활성 거래소 전체를 학습한다.

### 2026-07-24 사용자 데이터 교차 점검

- 비용 CSV: 2026-05 $62.05, 2026-06-01~07-01 $51.73, 2026-07-21~23 $9.08
- 2026-07-21~23 모델 요청: 27,879회, 일평균 9,293회
- 최근 3일 속도 단순 환산: 30일 약 $90.82
- 선택 거래소는 Binance였지만 활성 거래소에는 Binance·Upbit·Bithumb·Bybit·OKX·Bitget 6개가 모두 포함
- 6개 거래소 로그가 2026-07-21~23 구간에 생성됨
- 전체 점검 기간 모델 비용 중 출력 토큰 67.5%, 캐시 입력 약 0.001%

OpenAI 비용 CSV는 프로젝트 단위이고 거래소 메타데이터를 포함하지 않으므로 거래소별 정확한 비용 배분은 할 수 없다. 다만 활성 거래소·로그·학습 파일을 함께 보면 최근 구간을 “Binance 한 곳 비용”으로 해석하면 안 된다.

### 핵심 클래스

#### 1. OpenAIClient (`trading/ai/openai_client.py`)
```python
class OpenAIClient:
    def __init__(self, api_key: str, model: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key
        self.model = model or "gpt-3.5-turbo"
        self.base_url = base_url  # 🔥 오픈소스 전환 핵심
        # base_url이 있으면 다른 LLM API 사용 가능
```

**오픈소스 전환 지원**:
- `base_url` 파라미터로 다른 API 엔드포인트 사용 가능
- OpenAI 호환 API를 지원하는 모든 서비스 사용 가능
- 예: DeepSeek, OpenRouter, Local LLM 서버 등

#### 2. AIManager (`trading/ai/ai_manager.py`)
```python
class AIManager:
    def __init__(self, api_key: str, model: Optional[str] = None, base_url: Optional[str] = None):
        self.client = OpenAIClient(api_key=api_key, model=model, base_url=base_url)
    
    def enabled(self) -> bool:
        """AI 기능 활성화 여부"""
        return bool(self.api_key) and self.client.is_ready()
    
    def analyze_market_conditions(self, symbol: str, market_data: List, indicators: Dict) -> Dict:
        """시장 분석 (암호화폐/ETF/주식 공통 사용)"""
        # AI 호출 로직
        pass
    
    def analyze_exit_conditions(self, ...) -> Dict:
        """청산 분석"""
        pass
    
    def verify_pattern_similarity(self, ...) -> Dict:
        """패턴 유사성 검증"""
        pass
```

---

## 🔄 오픈소스 LLM 전환 방법

### 현재 구조의 장점
현재 `OpenAIClient`는 이미 `base_url`을 지원하므로, **코드 변경 없이** 다른 LLM API로 전환 가능합니다.

### 전환 시나리오

#### 시나리오 1: DeepSeek API 사용
```python
# settings.json
{
  "openai_api_key": "sk-...",
  "openai_model": "deepseek-chat",
  "openai_base_url": "https://api.deepseek.com"
}

# main.py (라인 1600)
self.ai_manager = AIManager(
    openai_api_key, 
    openai_model, 
    base_url=settings.get('openai_base_url')  # DeepSeek API 사용
)
```

#### 시나리오 2: OpenRouter 사용 (다양한 모델 선택)
```python
# settings.json
{
  "openai_api_key": "sk-or-...",
  "openai_model": "qwen/qwen-2.5-72b-instruct",
  "openai_base_url": "https://openrouter.ai/api/v1"
}
```

#### 시나리오 3: 로컬 LLM 서버 사용
```python
# settings.json
{
  "openai_api_key": "not-needed",
  "openai_model": "local-model",
  "openai_base_url": "http://localhost:1234/v1"  # Local LLM 서버
}
```

### 전환 절차
1. **설정 파일 수정**: `openai_base_url` 추가
2. **모델명 변경**: `openai_model`을 해당 서비스의 모델명으로 변경
3. **API 키 설정**: 해당 서비스의 API 키 입력 (로컬 서버는 불필요)
4. **코드 변경 없음**: 기존 코드 그대로 사용 가능

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

## 🚀 오픈소스 전환 로드맵

### Phase 1: 현재 (OpenAI API)
- ✅ OpenAI GPT-3.5/GPT-4 사용
- ✅ `base_url` 지원으로 전환 준비 완료

### Phase 2: 하이브리드 (2026 Q2)
- [ ] OpenRouter 통합 (다양한 모델 선택)
- [ ] DeepSeek API 지원
- [ ] 사용자가 모델 선택 가능

### Phase 3: 오픈소스 전환 (2026 Q3-Q4)
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
- **모델 호환성**: OpenAI 호환 API만 사용
- **에러 처리**: API 변경 시에도 안정적으로 동작

### 3. 코드 일관성
- **가드 체크**: 항상 `if self.ai_manager and self.ai_manager.enabled()` 사용
- **에러 폴백**: AI 실패 시 기본 분석으로 폴백
- **로깅**: AI 호출 및 결과 로깅

---

## 📚 참고 코드

### AIManager 초기화 (main.py)
```python
# 라인 1598-1614
if openai_api_key:
    openai_model = settings.get('openai_model', 'gpt-3.5-turbo')
    openai_base_url = settings.get('openai_base_url')  # 오픈소스 전환용
    self.ai_manager = AIManager(openai_api_key, openai_model, base_url=openai_base_url)
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
- [ ] 설정 파일에 `openai_base_url` 필드 추가
- [ ] 코드에서 하드코딩된 API 엔드포인트 제거
- [ ] 다양한 모델 지원 테스트
- [ ] 로컬 LLM 서버 연동 테스트
- [ ] 로컬 모델의 지연·정확도·운영비 비교
- [ ] OpenAI 프로젝트/키/사용자/거래소별 비용 귀속 메타데이터
- [x] 요청 예산·시장 이벤트·중복 제거·거래 기회 보존 회귀 테스트
- [ ] 다심볼 배치 분석 품질·비용 A/B
