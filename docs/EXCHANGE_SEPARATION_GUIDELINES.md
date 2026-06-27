# 거래소 분리 가이드라인 (Exchange Separation Guidelines)

## 🚨 중요: 거래소별 시스템 분리 원칙

이 문서는 NoahAI 시스템에서 바이낸스와 CCXT 거래소들 간의 명확한 분리를 보장하기 위한 가이드라인입니다.

## 📋 기본 원칙

### 1. 절대 금지 사항
- ❌ **바이낸스는 절대 `unified_trader.py`를 사용하지 않음**
- ❌ **CCXT 거래소들은 절대 `trader.py`를 사용하지 않음**
- ❌ **바이낸스에서 `unified_trader.py` 호출 금지**
- ❌ **CCXT 거래소에서 `trader.py` 호출 금지**
- ❌ **거래소별 시스템 간 중첩이나 중복 금지**

### 2. 올바른 분리 구조
- ✅ **바이낸스**: `trader.py` + `api/binance_client.py` (python-binance)
- ✅ **CCXT 거래소**: `unified_trader.py` + `trading/exchanges/adapters/` (CCXT)

## 🏗️ 시스템 구조

### 바이낸스 전용 시스템
```
📁 바이낸스 거래 시스템:
├── trading/trader.py                    ← 메인 거래 실행기 (바이낸스 전용)
├── api/binance_client.py               ← 고성능 클라이언트 (현물 거래용)
└── trading/exchanges/adapters/binance_futures_adapter.py ← 선물 거래용 어댑터
```

### CCXT 거래소 통합 시스템
```
📁 CCXT 거래 시스템:
├── trading/unified_trader.py           ← 메인 거래 실행기 (CCXT 거래소 전용)
├── trading/unified_trading_manager.py ← CCXT 거래소 관리자
├── trading/exchange_manager.py        ← 전체 거래소 통합 관리자
└── trading/exchanges/adapters/        ← 각 거래소별 어댑터
    ├── bybit_futures_adapter.py
    ├── okx_futures_adapter.py
    ├── bitget_futures_adapter.py
    ├── upbit_spot_adapter.py
    └── bithumb_spot_adapter.py
```

## 🔄 거래 실행 흐름

### 바이낸스 거래 흐름
```
대시보드 시작 버튼 클릭
    ↓
main.py.on_start_exchange('binance')
    ↓
main.py._start_binance_trading()
    ↓
main.py.start_trading_loop()
    ↓
main.py.trading_loop()  ← 메인 거래 루프
    ↓
AI 분석 및 거래 실행
    ↓
trader.execute_trades()
    ↓
api/binance_client.py
    ↓
바이낸스 API 직접 호출
```

### CCXT 거래소 거래 흐름
```
대시보드 시작 버튼 클릭
    ↓
main.py.on_start_exchange(exchange)
    ↓
main.py._start_unified_trading(exchange)
    ↓
unified_trader.start_trading(exchange)
    ↓
unified_trader._monitoring_loop(exchange)
    ↓
AI 분석 및 거래 실행
    ↓
unified_trader._execute_signal_trade()
    ↓
CCXT 어댑터
    ↓
각 거래소 API 호출
```

## 📝 코드 작성 가이드라인

### main.py에서 거래소별 라우팅
```python
def on_start_exchange(self, exchange: str) -> bool:
    """거래소별 시작 (바이낸스는 trader.py, 다른 거래소는 unified_trader.py)"""
    ex = exchange.lower().strip()
    
    if ex == 'binance':
        return self._start_binance_trading()  # trader.py 시스템
    else:
        return self._start_unified_trading(ex)  # unified_trader.py 시스템

def _start_binance_trading(self) -> bool:
    """바이낸스 거래 시작 (trader.py 사용)"""
    # start_trading_loop() 호출
    return self.start_trading_loop()

def _start_unified_trading(self, exchange: str) -> bool:
    """통합 거래소 거래 시작 (unified_trader.py 사용)"""
    # unified_trader.start_trading(exchange) 호출
    return self.unified_trader.start_trading(exchange)
```

### unified_trader.py에서 바이낸스 제외
```python
def get_exchange_client(self, exchange_name: str):
    """거래소별 클라이언트 가져오기 (CCXT 거래소만 지원)"""
    if exchange_name.lower() == 'binance':
        self.logger.warning(f"바이낸스는 unified_trader에서 지원하지 않습니다. trader.py를 사용하세요.")
        return None
    
    # CCXT 거래소만 처리
    trading_type = 'futures' if exchange_name in ['bybit', 'okx', 'bitget'] else 'spot'
    return self.unified_manager.get_exchange(exchange_name, trading_type)
```

## 🚨 주의사항

### 1. 새로운 거래소 추가 시
- **바이낸스**: `trader.py` 시스템에 추가 (python-binance 사용)
- **다른 거래소**: `unified_trader.py` 시스템에 추가 (CCXT 사용)

### 2. 기존 코드 수정 시
- 바이낸스 관련 코드는 `trader.py`에서만 수정
- CCXT 거래소 관련 코드는 `unified_trader.py`에서만 수정
- 두 시스템 간의 직접적인 호출 금지

### 3. 디버깅 시
- 바이낸스 문제: `trader.py`와 `api/binance_client.py` 확인
- CCXT 거래소 문제: `unified_trader.py`와 해당 어댑터 확인

## 📊 거래소별 지원 현황

| 거래소 | 시스템 | API 라이브러리 | 거래 유형 | 상태 |
|--------|--------|----------------|-----------|------|
| 바이낸스 | `trader.py` | python-binance | 선물 | ✅ 완료 |
| 업비트 | `unified_trader.py` | CCXT | 현물 | ✅ 완료 |
| 빗썸 | `unified_trader.py` | CCXT | 현물 | ✅ 완료 |
| OKX | `unified_trader.py` | CCXT | 선물 | ✅ 완료 |
| 바이비트 | `unified_trader.py` | CCXT | 선물 | ✅ 완료 |
| 비트겟 | `unified_trader.py` | CCXT | 선물 | ✅ 완료 |

## 🔧 문제 해결

### "거래소 클라이언트 없음" 오류
1. **바이낸스**: `trader.py`가 올바르게 초기화되었는지 확인
2. **CCXT 거래소**: `unified_trader.py`가 올바르게 초기화되었는지 확인
3. **API 키**: 해당 거래소의 API 키가 올바르게 설정되었는지 확인

### 거래가 시작되지 않는 경우
1. **바이낸스**: `main.py.start_trading_loop()` 호출 확인
2. **CCXT 거래소**: `unified_trader.start_trading(exchange)` 호출 확인
3. **라우팅**: `main.py`에서 올바른 경로로 라우팅되는지 확인

## 📚 관련 문서
- [ARCHITECTURE.md](./ARCHITECTURE.md) - 전체 시스템 아키텍처
- [TRADING_FLOW.md](./TRADING_FLOW.md) - 거래 실행 흐름
- [MASTER_DOCUMENTATION.md](./MASTER_DOCUMENTATION.md) - 마스터 문서

---

**마지막 업데이트**: 2025-01-15  
**작성자**: NoahAI Development Team  
**목적**: 거래소별 시스템 분리 원칙 보장
