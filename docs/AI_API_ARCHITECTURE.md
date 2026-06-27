# AI API 아키텍처 및 오픈소스 전환 가이드

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
- [ ] 비용 0원 운영

---

## ⚠️ 개발 시 주의사항

### 1. AI 호출 최적화
- **호출 빈도**: 실제 거래 신호 발생 시에만 (일일 10-50회)
- **조건부 호출**: AI 매니저 활성화 시에만
- **캐싱**: 동일한 분석 결과 재사용

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
