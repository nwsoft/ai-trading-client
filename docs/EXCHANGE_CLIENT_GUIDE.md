# 거래소 클라이언트 파일 경로 가이드

## 🚨 중요: 올바른 파일 경로 사용

이 문서는 각 거래소에서 사용해야 하는 올바른 클라이언트 파일의 경로를 명시합니다. **잘못된 파일을 수정하면 변경사항이 반영되지 않습니다.**

## 📁 거래소별 올바른 파일 경로

### **🔥 바이낸스 (Binance)**
- **✅ 사용**: `api/binance_client.py` - **BinanceClient 클래스**
- **❌ 사용 안함**: `trading/exchanges/binance_client.py` (삭제됨)
- **✅ 어댑터**: `trading/exchanges/adapters/binance_futures_adapter.py` - **BinanceFuturesAdapter 클래스**

**바이낸스 수정 시 사용할 파일:**
```python
# 메인 거래용 (현물)
from api.binance_client import BinanceClient, BinanceConfig

# 선물 거래용 (어댑터)
from trading.exchanges.adapters.binance_futures_adapter import BinanceFuturesAdapter
```

### **🔥 바이비트 (Bybit)**
- **✅ 사용**: `trading/exchanges/adapters/bybit_futures_adapter.py` - **BybitFuturesAdapter 클래스**

**바이비트 수정 시 사용할 파일:**
```python
from trading.exchanges.adapters.bybit_futures_adapter import BybitFuturesAdapter
```

### **🔥 OKX**
- **✅ 사용**: `trading/exchanges/adapters/okx_futures_adapter.py` - **OkxFuturesAdapter 클래스**

**OKX 수정 시 사용할 파일:**
```python
from trading.exchanges.adapters.okx_futures_adapter import OkxFuturesAdapter
```

### **🔥 비트겟 (Bitget)**
- **✅ 사용**: `trading/exchanges/adapters/bitget_futures_adapter.py` - **BitgetFuturesAdapter 클래스**

**비트겟 수정 시 사용할 파일:**
```python
from trading.exchanges.adapters.bitget_futures_adapter import BitgetFuturesAdapter
```

### **🔥 빗썸 (Bithumb)**
- **✅ 사용**: `trading/exchanges/adapters/bithumb_spot_adapter.py` - **BithumbSpotAdapter 클래스**
- **❌ 사용 안함**: `trading/exchanges/bithumb_client.py` (삭제됨)

**빗썸 수정 시 사용할 파일:**
```python
from trading.exchanges.adapters.bithumb_spot_adapter import BithumbSpotAdapter
```

### **🔥 업비트 (Upbit)**
- **✅ 사용**: `trading/exchanges/adapters/upbit_spot_adapter.py` - **UpbitSpotAdapter 클래스**
- **❌ 사용 안함**: `trading/exchanges/upbit_client.py` (삭제됨)

**업비트 수정 시 사용할 파일:**
```python
from trading.exchanges.adapters.upbit_spot_adapter import UpbitSpotAdapter
```

## 🏗️ 거래소 클라이언트 구조

### **현재 활성 파일 구조**
```
trading/exchanges/
├── base_exchange.py                    # 기본 거래소 클래스
├── exchange_factory.py                 # 거래소 팩토리
├── exchange_manager.py                 # 거래소 관리자
├── interfaces/                         # 인터페이스
│   ├── exchange_interface.py
│   ├── futures_exchange.py
│   └── spot_exchange.py
└── adapters/                          # 실제 사용되는 어댑터들
    ├── binance_futures_adapter.py     # 바이낸스 선물
    ├── bybit_futures_adapter.py       # 바이비트 선물
    ├── okx_futures_adapter.py         # OKX 선물
    ├── bitget_futures_adapter.py      # 비트겟 선물
    ├── bithumb_spot_adapter.py        # 빗썸 현물
    └── upbit_spot_adapter.py          # 업비트 현물

api/
└── binance_client.py                   # 바이낸스 고성능 클라이언트 (현물)
```

### **삭제된 파일들 (더 이상 존재하지 않음)**
```
❌ trading/exchanges/binance_client.py   (삭제됨)
❌ trading/exchanges/bithumb_client.py   (삭제됨)
❌ trading/exchanges/upbit_client.py     (삭제됨)
```

## 🎯 거래소별 사용 패턴

### **바이낸스 거래 흐름**
```
main.py → api/binance_client.py → trading/trader.py
```

### **CCXT 거래소 거래 흐름**
```
main.py → trading/exchanges/exchange_factory.py → adapters/*.py → trading/unified_trader.py
```

## ⚠️ 주의사항

### **수정 시 반드시 확인할 것**
1. **올바른 파일 경로 사용**: 위의 가이드에 명시된 파일만 수정
2. **클래스명 확인**: 각 파일의 올바른 클래스명 사용
3. **import 경로 확인**: 수정한 파일이 올바른 경로에서 import되는지 확인

### **잘못된 파일 수정의 결과**
- ❌ 변경사항이 반영되지 않음
- ❌ 시스템이 올바르게 작동하지 않음
- ❌ 디버깅이 어려워짐

### **올바른 수정 방법**
1. 이 가이드에서 올바른 파일 경로 확인
2. 해당 파일의 클래스명 확인
3. 수정 후 import 경로가 올바른지 확인
4. 테스트를 통한 동작 확인

## 🔧 개발자 체크리스트

거래소 관련 수정 시 다음을 확인하세요:

- [ ] 올바른 파일 경로를 사용했는가?
- [ ] 올바른 클래스명을 사용했는가?
- [ ] import 경로가 올바른가?
- [ ] 삭제된 파일을 참조하지 않는가?
- [ ] 수정 후 테스트를 진행했는가?

---

**이 가이드를 따라하면 올바른 파일을 수정하여 변경사항이 정확히 반영됩니다.**
