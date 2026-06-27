# 증권 및 ETF 추가 가이드

## 📋 현재 시스템 구조 분석

### 현재 지원 거래소
- **선물 거래소**: Binance, Bybit, OKX, Bitget (Futures)
- **현물 거래소**: Upbit, Bithumb (Spot)
- **거래 타입**: `Futures`와 `Spot`만 지원

### 시스템 아키텍처
```
trading/exchanges/
├── interfaces/
│   ├── exchange_interface.py      # 기본 인터페이스
│   ├── futures_exchange.py        # 선물 거래 인터페이스
│   └── spot_exchange.py           # 현물 거래 인터페이스
├── adapters/                      # 거래소별 어댑터 구현
└── exchange_factory.py            # 거래소 팩토리 (등록 필요)
```

---

## 🎯 키움증권 API 기준: 증권 및 ETF 추가 작업

### 1️⃣ ETF는 증권의 한 종류인가?

**답변: 예, 하지만 별도 처리 필요**

- **이론적으로**: ETF(Exchange Traded Fund)는 증권의 한 종류입니다
- **실제 구현**: 증권 시스템을 추가하면 ETF도 포함되지만, **별도 필터링/분류 로직 필요**

**이유**:
1. **심볼 형식 차이**
   - 주식: 6자리 숫자 코드 (예: 005930 = 삼성전자)
   - ETF: 6자리 숫자 코드이지만 특정 패턴 (예: 069500 = KODEX KOSPI)
   - ETF는 보통 특정 접두사나 범위를 가짐

2. **거래 방식 차이**
   - 주식: 일반 주문 방식
   - ETF: 동일하지만 리밸런싱, 선물대비 프리미엄/할인 등 추가 메트릭 필요

3. **분석 로직 차이**
   - 주식: 기업 재무제표, 실적 분석 등
   - ETF: 기초지수 추적 오차, 운용보수, 구성 종목 비중 등

### 2️⃣ 필요한 작업 항목

#### **A. 시스템 확장 작업 (필수)**

##### 1. TradingType 확장
**파일**: `trading/exchanges/interfaces/exchange_interface.py`

```python
class TradingType(Enum):
    FUTURES = "futures"
    SPOT = "spot"
    STOCK = "stock"  # 🔥 신규 추가
```

##### 2. StockExchange 인터페이스 생성
**파일**: `trading/exchanges/interfaces/stock_exchange.py` (신규 생성)

```python
from .exchange_interface import ExchangeInterface, TradingType

class StockExchange(ExchangeInterface):
    """증권 거래소 인터페이스"""
    
    def __init__(self, exchange_name: str):
        super().__init__(exchange_name, TradingType.STOCK)
    
    # 주식 특화 메서드
    @abstractmethod
    def get_stock_list(self, market: str = "KOSPI") -> List[Dict[str, Any]]:
        """주식 목록 조회"""
        pass
    
    @abstractmethod
    def get_etf_list(self) -> List[Dict[str, Any]]:
        """ETF 목록 조회"""
        pass
    
    @abstractmethod
    def is_etf(self, symbol: str) -> bool:
        """ETF 여부 확인"""
        pass
```

##### 3. 키움증권 Adapter 구현
**파일**: `trading/exchanges/adapters/kiwoom_stock_adapter.py` (신규 생성)

**필수 구현 사항**:
- 키움 OpenAPI+ Python 라이브러리 연동
- 로그인 처리 (OCX ActiveX 또는 Kiwoom Open API+)
- 주문 체결 (매수/매도)
- 잔고 조회
- 실시간 시세 조회
- ETF 필터링 로직

**핵심 코드 구조**:
```python
from ..interfaces.stock_exchange import StockExchange
import pykiwoom  # 또는 키움 API 라이브러리

class KiwoomStockAdapter(StockExchange):
    def __init__(self, user_id: str, password: str, cert_password: str):
        super().__init__("kiwoom")
        self.user_id = user_id
        self.password = password
        self.cert_password = cert_password
        self.kiwoom = None
    
    def connect(self) -> bool:
        # 키움 OpenAPI 로그인 처리
        pass
    
    def get_stock_list(self, market: str = "KOSPI") -> List[Dict[str, Any]]:
        # 주식 목록 조회
        pass
    
    def get_etf_list(self) -> List[Dict[str, Any]]:
        # ETF만 필터링하여 반환
        stocks = self.get_stock_list("ETF")
        return [s for s in stocks if self.is_etf(s['code'])]
    
    def is_etf(self, symbol: str) -> bool:
        # ETF 코드 패턴 확인 (예: 069xxx, 102xxx 등)
        # 또는 키움 API의 장구분 필드로 확인
        pass
```

##### 4. ExchangeFactory에 등록
**파일**: `trading/exchanges/exchange_factory.py`

```python
from .adapters.kiwoom_stock_adapter import KiwoomStockAdapter

class ExchangeFactory:
    _stock_adapters = {
        'kiwoom': KiwoomStockAdapter,  # 🔥 신규 추가
    }
    
    @classmethod
    def create_stock_exchange(cls, exchange_name: str, settings: Dict[str, Any]) -> Optional[StockExchange]:
        """증권 거래소 생성"""
        if exchange_name not in cls._stock_adapters:
            raise ValueError(f"지원하지 않는 증권 거래소: {exchange_name}")
        
        adapter_class = cls._stock_adapters[exchange_name]
        
        if exchange_name == 'kiwoom':
            user_id = settings.get('kiwoom_user_id', '')
            password = settings.get('kiwoom_password', '')
            cert_password = settings.get('kiwoom_cert_password', '')
            return adapter_class(user_id, password, cert_password)
        
        return None
    
    @classmethod
    def create_exchange(cls, exchange_name: str, trading_type: str, settings: Dict[str, Any]):
        # ... 기존 코드 ...
        elif trading_type == 'stock':  # 🔥 신규 추가
            return cls.create_stock_exchange(exchange_name, settings)
```

##### 5. UnifiedTradingManager 확장
**파일**: `trading/unified_trading_manager.py`

```python
def _initialize_exchanges(self):
    # ... 기존 코드 ...
    
    # 🔥 증권 거래소 추가
    stock_exchanges = ['kiwoom']
    for exchange_name in stock_exchanges:
        if (not enabled or exchange_name in enabled) and self._has_valid_api_keys(exchange_name):
            try:
                exchange = ExchangeFactory.create_stock_exchange(exchange_name, self.settings)
                if exchange and exchange.connect():
                    self.exchanges[f"{exchange_name}_stock"] = exchange
                    self.logger.info(f"{exchange_name} 증권 거래소 초기화 완료")
            except Exception as e:
                self.logger.error(f"{exchange_name} 증권 거래소 초기화 실패: {e}")
```

##### 6. 설정 파일 확장
**파일**: `config/settings_template.json`, `config/settings.py`

```json
{
  "kiwoom_user_id": "",
  "kiwoom_password": "",
  "kiwoom_cert_password": "",
  "enabled_exchanges": ["binance", "kiwoom"],
  "stock_settings": {
    "default_market": "KOSPI",
    "etf_code_patterns": ["069", "102", "122", "143"],
    "trading_hours": {
      "start": "09:00",
      "end": "15:30"
    }
  }
}
```

##### 7. UI 확장
**파일**: `ui/dashboard_modern.py`, `ui/settings_modern.py`

- 증권 거래소 탭 추가
- 키움증권 로그인 UI 추가
- 주식/ETF 선택 UI 추가
- 증권 거래 화면 구현

#### **B. ETF별도 처리 필요 작업**

##### 1. ETF 필터링 로직
```python
def is_etf(self, symbol: str) -> bool:
    """ETF 여부 확인"""
    # 방법 1: 코드 패턴 확인
    etf_prefixes = ['069', '102', '122', '143', '261']
    if any(symbol.startswith(prefix) for prefix in etf_prefixes):
        return True
    
    # 방법 2: 키움 API의 장구분 필드 확인
    # 키움 API에서 'ETF' 장구분 반환 시 True
    return False

def filter_etf(self, symbols: List[str]) -> List[str]:
    """ETF만 필터링"""
    return [s for s in symbols if self.is_etf(s)]

def filter_stocks(self, symbols: List[str]) -> List[str]:
    """주식만 필터링 (ETF 제외)"""
    return [s for s in symbols if not self.is_etf(s)]
```

##### 2. ETF 특화 분석 로직
- 기초지수 추적 오차 분석
- 구성 종목 비중 조회
- 운용보수 정보
- 선물대비 프리미엄/할인

##### 3. UI에서 ETF 별도 표시
- 주식 목록과 ETF 목록 분리 표시
- ETF 전용 대시보드 탭
- ETF 포트폴리오 리밸런싱 기능

---

## 🌍 해외 선물 기준: 해외 선물 추가 작업

### 1️⃣ 해외 선물은 기존 선물 시스템과 유사

**답변: 예, 기존 Futures 시스템 활용 가능**

- 해외 선물도 선물 거래이므로 기존 `FuturesExchange` 인터페이스 활용 가능
- 단, 키움증권 API를 통한 해외 선물 거래는 별도 어댑터 필요

### 2️⃣ 필요한 작업 항목

#### **A. 키움증권 해외 선물 Adapter**

##### 옵션 1: 키움증권 API 사용
**파일**: `trading/exchanges/adapters/kiwoom_futures_adapter.py` (신규 생성)

```python
from ..interfaces.futures_exchange import FuturesExchange

class KiwoomFuturesAdapter(FuturesExchange):
    """키움증권 해외 선물 어댑터"""
    
    def __init__(self, user_id: str, password: str, cert_password: str):
        super().__init__("kiwoom")
        self.user_id = user_id
        self.password = password
        self.cert_password = cert_password
    
    def connect(self) -> bool:
        # 키움 OpenAPI 로그인
        pass
    
    def get_symbols(self) -> List[str]:
        # 해외 선물 심볼 목록 조회
        # 예: ES (S&P 500), NQ (나스닥), YM (다우), CL (원유) 등
        pass
    
    def place_order(self, symbol: str, side: str, quantity: float, ...):
        # 해외 선물 주문
        pass
```

##### 옵션 2: 해외 선물 거래소 직접 연동 (CME, ICE 등)
- CME Group API 연동
- ICE API 연동
- Interactive Brokers API 연동

#### **B. ExchangeFactory에 등록**

```python
_futures_adapters = {
    'binance': BinanceFuturesAdapter,
    'bybit': BybitFuturesAdapter,
    'okx': OkxFuturesAdapter,
    'bitget': BitgetFuturesAdapter,
    'kiwoom': KiwoomFuturesAdapter,  # 🔥 신규 추가
}
```

#### **C. 해외 선물 심볼 정규화**

```python
def normalize_futures_symbol(self, symbol: str, market: str) -> str:
    """해외 선물 심볼 정규화"""
    # CME: ES (S&P 500), NQ (나스닥), YM (다우)
    # NYMEX: CL (원유), NG (천연가스)
    # ICE: B (브렌트유), C (옥수수)
    symbol_map = {
        'ES': 'ES',  # S&P 500 E-mini
        'NQ': 'NQ',  # 나스닥 100 E-mini
        'CL': 'CL',  # WTI 원유
    }
    return symbol_map.get(symbol, symbol)
```

---

## 📊 작업 우선순위 및 복잡도

### 키움증권 증권/ETF

| 작업 항목 | 복잡도 | 우선순위 | 예상 시간 |
|---------|--------|---------|----------|
| TradingType 확장 | 낮음 | 높음 | 1시간 |
| StockExchange 인터페이스 | 낮음 | 높음 | 2시간 |
| KiwoomStockAdapter 구현 | 높음 | 높음 | 1-2주 |
| ETF 필터링 로직 | 중간 | 중간 | 4시간 |
| ExchangeFactory 등록 | 낮음 | 높음 | 1시간 |
| UnifiedTradingManager 확장 | 중간 | 높음 | 2시간 |
| UI 구현 | 높음 | 중간 | 1-2주 |
| 테스트 및 검증 | 중간 | 높음 | 1주 |

### 키움증권 해외 선물

| 작업 항목 | 복잡도 | 우선순위 | 예상 시간 |
|---------|--------|---------|----------|
| KiwoomFuturesAdapter 구현 | 높음 | 중간 | 1-2주 |
| ExchangeFactory 등록 | 낮음 | 높음 | 1시간 |
| 심볼 정규화 | 중간 | 중간 | 4시간 |
| 테스트 및 검증 | 중간 | 높음 | 1주 |

---

## ⚠️ 주의사항

### 키움증권 API 특수사항

1. **ActiveX 기반 (Windows 전용)**
   - 키움 OpenAPI는 Windows ActiveX 기반
   - Linux/Mac에서는 사용 불가 (또는 Wine/VM 필요)
   - `pykiwoom` 라이브러리 사용 고려

2. **로그인 프로세스**
   - 공인인증서 또는 보안카드 필요
   - 로그인 후 세션 유지 필요
   - 자동 재로그인 로직 구현 필요

3. **API 호출 제한**
   - 초당 호출 제한 존재
   - 주문 체결 확인 지연 가능
   - 재시도 로직 필수

4. **ETF 특화 처리**
   - ETF는 증권의 한 종류이지만 별도 필터링 필요
   - ETF 전용 분석 로직 필요
   - 포트폴리오 리밸런싱 기능 고려

### 해외 선물 특수사항

1. **거래 시간**
   - 한국 시간 기준 거래 시간 다름
   - 거래소별 거래 시간 확인 필요

2. **마진 요구사항**
   - 상품별 초기증거금/유지증거금 다름
   - 레버리지 설정 확인 필요

3. **심볼 표기**
   - 거래소별 심볼 형식 다름
   - 정규화 로직 필요

---

## 🔄 작업 순서 제안

### Phase 1: 기본 구조 확장 (1주)
1. TradingType 확장
2. StockExchange 인터페이스 생성
3. ExchangeFactory 확장

### Phase 2: 키움증권 Adapter 구현 (2주)
1. KiwoomStockAdapter 기본 구현
2. 로그인/연결 처리
3. 기본 주문/조회 기능

### Phase 3: ETF 필터링 및 특화 (1주)
1. ETF 필터링 로직
2. ETF 목록 조회
3. ETF 특화 분석 (선택)

### Phase 4: UI 구현 (2주)
1. 증권 거래소 UI 추가
2. 주식/ETF 선택 화면
3. 증권 거래 대시보드

### Phase 5: 해외 선물 (선택, 2주)
1. KiwoomFuturesAdapter 구현
2. 해외 선물 심볼 정규화
3. UI 추가

### Phase 6: 테스트 및 검증 (1주)
1. 통합 테스트
2. 페이퍼 트레이딩 검증
3. 문서 업데이트

---

## 📝 결론

### ETF와 증권의 관계
- **ETF는 증권의 한 종류이지만**, 별도 필터링/분류 로직 필요
- 증권 시스템을 추가하면 ETF도 포함되지만, **별도 UI/분석 로직 구현 권장**

### 키움증권 추가 작업
- **증권/ETF**: 새로운 `STOCK` 타입 추가 + StockExchange 인터페이스 + KiwoomStockAdapter 구현
- **해외 선물**: 기존 `FUTURES` 타입 활용 + KiwoomFuturesAdapter 구현

### 해외 선물 추가 작업
- **키움증권 경유**: KiwoomFuturesAdapter 구현
- **거래소 직접 연동**: CME/ICE 등 거래소별 Adapter 구현

**예상 총 작업 기간**: 7-10주 (증권/ETF + 해외 선물 모두 포함)

---

## ⚠️ 중요: AI API 구조 활용 및 오픈소스 전환 고려

### AI API 활용 가이드
**참고 문서**: `docs/AI_API_ARCHITECTURE.md`

ETF/주식 개발 시 AI API를 올바르게 활용해야 합니다:

1. **AIManager 초기화**: 직접 초기화하지 않고 `main.py`에서 전달받음
2. **가드 체크 필수**: `if self.ai_manager and self.ai_manager.enabled()` 항상 사용
3. **에러 폴백**: AI 호출 실패 시 기본 분석으로 폴백
4. **오픈소스 전환 준비**: `base_url` 설정 지원으로 향후 전환 가능

### 대시보드 UI 일관성 유지
**현재 상태**: 블록체인 서비스와 동일한 패턴으로 이미 구현됨
- ✅ `create_service_sub_tabs('stock')` 구현 완료
- ✅ `create_broker_*` 메서드들 구현 완료 (placeholder)
- ✅ 좌/우 2단 레이아웃 구조 유지
- ✅ 동일한 색상/폰트/위젯 구조 사용

**참고**: `docs/STOCK_ETF_CURRENT_STATUS_20260118.md`에서 현재 구현 상태 확인

