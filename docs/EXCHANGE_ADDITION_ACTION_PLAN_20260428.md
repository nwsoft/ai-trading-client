# 🚀 액션 플랜: 거래소 추가 + 사용자 편의성 개선 (즉시 실행 가능)

**문서 목적**: 새로운 거래소 추가 방법 및 사용자 편의성 개선 구체적 절차

---

## 1️⃣ 새 거래소 추가 방법 (예: Kraken)

### **Step 1: Kraken 어댑터 구현 (1시간)**

```bash
# 파일 생성: trading/exchanges/adapters/kraken_futures_adapter.py
```

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kraken 선물 거래소 어댑터
"""

from typing import Dict, Optional, Any, List
import logging
import ccxt

from ..interfaces.futures_exchange import FuturesExchange


class KrakenFuturesAdapter(FuturesExchange):
    """Kraken 선물 거래 어댑터 (CCXT 기반)"""
    
    def __init__(self, api_key: str, secret_key: str, **kwargs):
        super().__init__(api_key, secret_key)
        self.logger = logging.getLogger(__name__)
        
        try:
            self.client = ccxt.kraken({
                'apiKey': api_key,
                'secret': secret_key,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # 선물 모드
                }
            })
            self.is_connected = False
        except Exception as e:
            self.logger.error(f"Kraken 클라이언트 초기화 실패: {e}")
            self.client = None
    
    def connect(self) -> bool:
        """연결 테스트 및 인증"""
        try:
            if not self.client:
                return False
            
            # API 키 유효성 검증
            balance = self.client.fetch_balance()
            self.is_connected = True
            self.logger.info("Kraken 연결 성공")
            return True
            
        except Exception as e:
            self.logger.error(f"Kraken 연결 실패: {e}")
            self.is_connected = False
            return False
    
    def get_account_info(self) -> Dict[str, Any]:
        """계정 정보 조회"""
        try:
            if not self.client:
                return {'status': 'error', 'message': 'Client not initialized'}
            
            info = self.client.fetch_account()
            return {
                'exchange': 'kraken',
                'account_id': info.get('id'),
                'account_type': 'futures',
                'status': 'active',
            }
        except Exception as e:
            self.logger.error(f"계정 정보 조회 실패: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def get_balance(self) -> Dict[str, float]:
        """잔고 조회"""
        try:
            if not self.client:
                return {}
            
            balance = self.client.fetch_balance()
            
            # CCXT 표준 포맷: {'USDT': {'free': 100, 'used': 50, 'total': 150}}
            result = {}
            for currency, info in balance.items():
                if currency not in ['free', 'used', 'total']:
                    result[currency] = info.get('total', 0)
            
            return result
            
        except Exception as e:
            self.logger.error(f"잔고 조회 실패: {e}")
            return {}
    
    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        """24시간 틱커 데이터"""
        try:
            if not self.client:
                return {}
            
            ticker = self.client.fetch_ticker(symbol)
            return {
                'symbol': symbol,
                'last': ticker.get('last'),
                'bid': ticker.get('bid'),
                'ask': ticker.get('ask'),
                'high': ticker.get('high'),
                'low': ticker.get('low'),
                'volume': ticker.get('quoteVolume'),
                'timestamp': ticker.get('timestamp'),
            }
        except Exception as e:
            self.logger.error(f"틱커 조회 실패 ({symbol}): {e}")
            return {}
    
    def get_exchange_info(self) -> Dict[str, Any]:
        """거래소 정보"""
        return {
            'name': 'Kraken',
            'type': 'futures',
            'website': 'https://www.kraken.com',
            'countries': ['USA'],
            'has': {
                'fetchBalance': True,
                'fetchTicker': True,
                'createOrder': True,
                'fetchOrder': True,
                'cancelOrder': True,
            }
        }
    
    def get_current_price(self, symbol: str) -> float:
        """현재 가격"""
        try:
            if not self.client:
                return 0
            
            ticker = self.client.fetch_ticker(symbol)
            return ticker.get('last', 0)
        except Exception as e:
            self.logger.error(f"가격 조회 실패 ({symbol}): {e}")
            return 0
    
    def place_order(self, symbol: str, side: str, quantity: float,
                   price: Optional[float] = None, order_type: str = "MARKET") -> Dict[str, Any]:
        """주문 실행"""
        try:
            if not self.client:
                return {'status': 'error', 'message': 'Client not initialized'}
            
            order = self.client.create_order(
                symbol=symbol,
                type=order_type.lower(),  # 'market' or 'limit'
                side=side.lower(),  # 'buy' or 'sell'
                amount=quantity,
                price=price if order_type.upper() == 'LIMIT' else None,
            )
            
            return {
                'order_id': order.get('id'),
                'symbol': symbol,
                'side': side,
                'quantity': quantity,
                'price': price,
                'status': order.get('status'),
                'timestamp': order.get('timestamp'),
            }
        except Exception as e:
            self.logger.error(f"주문 실행 실패: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """주문 상태 조회"""
        try:
            if not self.client:
                return {'status': 'error'}
            
            order = self.client.fetch_order(order_id)
            return {
                'order_id': order_id,
                'status': order.get('status'),  # 'open', 'closed', 'canceled'
                'filled': order.get('filled'),
                'remaining': order.get('remaining'),
                'average': order.get('average'),
            }
        except Exception as e:
            self.logger.error(f"주문 상태 조회 실패: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def cancel_order(self, order_id: str) -> bool:
        """주문 취소"""
        try:
            if not self.client:
                return False
            
            self.client.cancel_order(order_id)
            self.logger.info(f"주문 취소 완료: {order_id}")
            return True
        except Exception as e:
            self.logger.error(f"주문 취소 실패: {e}")
            return False
    
    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """거래 내역 조회"""
        try:
            if not self.client:
                return []
            
            trades = self.client.fetch_trades(symbol, limit=limit) if symbol else []
            return [
                {
                    'id': t.get('id'),
                    'symbol': t.get('symbol'),
                    'side': t.get('side'),
                    'price': t.get('price'),
                    'amount': t.get('amount'),
                    'timestamp': t.get('timestamp'),
                }
                for t in trades
            ]
        except Exception as e:
            self.logger.error(f"거래 내역 조회 실패: {e}")
            return []
```

### **Step 2: ExchangeFactory에 등록 (5분)**

```python
# trading/exchanges/exchange_factory.py

from .adapters.kraken_futures_adapter import KrakenFuturesAdapter

class ExchangeFactory:
    _futures_adapters = {
        'binance': BinanceFuturesAdapter,
        'bybit': BybitFuturesAdapter,
        'okx': OkxFuturesAdapter,
        'bitget': BitgetFuturesAdapter,
        'kraken': KrakenFuturesAdapter,  # ✅ 추가
    }
    
    @classmethod
    def create_futures_exchange(cls, exchange_name: str, settings: Dict[str, Any]):
        if exchange_name not in cls._futures_adapters:
            raise ValueError(f"지원하지 않는 거래소: {exchange_name}")
        
        adapter_class = cls._futures_adapters[exchange_name]
        api_key = settings.get(f'{exchange_name}_api_key', '')
        secret_key = settings.get(f'{exchange_name}_secret_key', '')
        
        # Kraken도 기본적으로 API 키/시크릿만 필요
        return adapter_class(api_key, secret_key)
```

### **Step 3: 설정 파일에 추가 (2분)**

```json
{
  "enabled_exchanges": ["binance", "bybit", "kraken"],
  "selected_exchange": "binance",
  
  "kraken_api_key": "your_kraken_api_key",
  "kraken_secret_key": "your_kraken_secret_key"
}
```

### **Step 4: UI에 Kraken 추가 (5분)**

```python
# ui/widgets/dashboard_modern.py

SUPPORTED_EXCHANGES = [
    'binance',
    'bybit',
    'okx',
    'bitget',
    'upbit',
    'bithumb',
    'kraken',  # ✅ 추가
]

def _setup_exchange_menu(self):
    """거래소 선택 메뉴"""
    exchange_menu = ctk.CTkOptionMenu(
        self.header_frame,
        values=SUPPORTED_EXCHANGES,
        command=self._on_exchange_selected
    )
    exchange_menu.pack(side="left", padx=10)
```

### **Step 5: 테스트 (30분)**

```bash
# 단위 테스트 작성
# tests/test_kraken_adapter.py

import pytest
from trading.exchanges.adapters.kraken_futures_adapter import KrakenFuturesAdapter

def test_kraken_connect():
    """Kraken 연결 테스트"""
    adapter = KrakenFuturesAdapter('test_key', 'test_secret')
    assert adapter.client is not None

def test_kraken_get_balance():
    """Kraken 잔고 조회"""
    adapter = KrakenFuturesAdapter('test_key', 'test_secret')
    balance = adapter.get_balance()
    assert isinstance(balance, dict)

# 실행
# pytest tests/test_kraken_adapter.py -v
```

---

## 2️⃣ 사용자 편의성 개선: 거래소 빠른 전환 UI

### **Problem: 현재 상태**

```
❌ 설정 파일 수정 필요
❌ 앱 재시작 필요
❌ 거래소 전환 시간: 2~3분
❌ 여러 거래소 동시 모니터링 불가
```

### **Solution: 거래소 탭 추가 (UI)**

```python
# ui/widgets/dashboard_modern.py

import customtkinter as ctk
from tkinter import ttk

class DashboardModern(ctk.CTkFrame):
    def _setup_exchange_tabs(self):
        """거래소별 탭 UI"""
        
        # 🎯 메인 탭 구조
        self.exchange_tabs = ctk.CTkTabview(self.main_frame)
        self.exchange_tabs.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 활성화된 거래소 탭 추가
        enabled = self.settings.get('enabled_exchanges', ['binance'])
        
        for exchange in enabled:
            tab = self.exchange_tabs.add(exchange.upper())
            self._setup_exchange_tab_content(tab, exchange)
    
    def _setup_exchange_tab_content(self, tab_frame: ctk.CTkFrame, exchange: str):
        """거래소별 탭 내용"""
        
        # 거래소 정보
        info_frame = ctk.CTkFrame(tab_frame, fg_color="gray25")
        info_frame.pack(fill="x", padx=10, pady=10)
        
        # 잔고 표시
        ctk.CTkLabel(info_frame, text=f"{exchange.upper()} Balance:").pack(side="left", padx=10)
        balance_label = ctk.CTkLabel(info_frame, text="Loading...", text_color="green")
        balance_label.pack(side="left", padx=10)
        
        # 실시간 업데이트
        self._refresh_exchange_balance(exchange, balance_label)
        
        # 포지션 표시
        position_frame = ctk.CTkFrame(tab_frame)
        position_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self._setup_position_table(position_frame, exchange)
        
        # 거래 신호
        signal_frame = ctk.CTkFrame(tab_frame)
        signal_frame.pack(fill="x", padx=10, pady=10)
        
        self._setup_signal_display(signal_frame, exchange)
    
    def _refresh_exchange_balance(self, exchange: str, label: ctk.CTkLabel):
        """거래소 잔고 새로고침"""
        try:
            balance = self.exchange_manager.get_exchange_balance(exchange)
            total = sum(v for v in balance.values() if isinstance(v, (int, float)))
            label.configure(text=f"${total:,.2f}")
        except Exception as e:
            label.configure(text=f"Error: {str(e)[:20]}")
        
        # 10초마다 새로고침
        self.after(10000, lambda: self._refresh_exchange_balance(exchange, label))
```

### **개선 효과**

```
✅ 거래소 탭: Binance | Upbit | Kraken
✅ 실시간 전환: 클릭 1회, 0.5초
✅ 동시 모니터링: 탭 전환으로 모든 거래소 추적
✅ 개별 신호: 거래소별 독립적 AI 신호
```

---

## 3️⃣ 다중 거래소 통합 자산 뷰

### **기능: 모든 거래소 한눈에 보기**

```python
# ui/widgets/portfolio_widget.py

class UnifiedPortfolioWidget(ctk.CTkFrame):
    """모든 거래소의 통합 자산 뷰"""
    
    def __init__(self, parent, exchange_manager, **kwargs):
        super().__init__(parent, **kwargs)
        self.exchange_manager = exchange_manager
        self._setup_ui()
    
    def _setup_ui(self):
        """통합 자산 UI"""
        
        # 제목
        ctk.CTkLabel(self, text="Unified Portfolio", font=("Arial", 18, "bold")).pack()
        
        # 통합 자산 요약
        summary_frame = ctk.CTkFrame(self)
        summary_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(summary_frame, text="Total Balance:").pack(side="left")
        self.total_label = ctk.CTkLabel(summary_frame, text="$0.00", text_color="green")
        self.total_label.pack(side="left", padx=10)
        
        # 거래소별 분리
        exchanges_frame = ctk.CTkFrame(self)
        exchanges_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        enabled = self.exchange_manager.settings.get('enabled_exchanges', [])
        
        for exchange in enabled:
            self._add_exchange_summary(exchanges_frame, exchange)
    
    def _add_exchange_summary(self, parent: ctk.CTkFrame, exchange: str):
        """거래소별 요약"""
        
        frame = ctk.CTkFrame(parent, fg_color="gray25")
        frame.pack(fill="x", pady=5)
        
        # 거래소 이름
        ctk.CTkLabel(frame, text=exchange.upper(), font=("Arial", 12, "bold")).pack(side="left", padx=10)
        
        # 잔고
        balance_label = ctk.CTkLabel(frame, text="$0.00")
        balance_label.pack(side="left", padx=20)
        
        # 포지션 수
        position_label = ctk.CTkLabel(frame, text="Positions: 0")
        position_label.pack(side="left", padx=20)
        
        # 실시간 업데이트
        self._update_exchange_summary(exchange, balance_label, position_label)
    
    def _update_exchange_summary(self, exchange: str, balance_label, position_label):
        """거래소 요약 업데이트"""
        
        balance = self.exchange_manager.get_exchange_balance(exchange)
        total = sum(v for v in balance.values() if isinstance(v, (int, float)))
        balance_label.configure(text=f"${total:,.2f}")
        
        positions = self.exchange_manager.get_open_positions(exchange)
        position_label.configure(text=f"Positions: {len(positions)}")
        
        # 30초마다 업데이트
        self.after(30000, lambda: self._update_exchange_summary(exchange, balance_label, position_label))
```

---

## 4️⃣ 실제 구현 순서 (추천)

### **Week 1 (Phase 1 완료 후)**
- [x] 신용도 기반 생활금융 개인화 (✅ 완료)

### **Week 2 (즉시 시작)**
- [ ] **Day 1-2**: 거래소 탭 UI 구현
  - 파일: `ui/widgets/exchange_tabs_widget.py`
  - 추가: Dashboard에 통합
  - 시간: 4~6시간
  
- [ ] **Day 3**: 통합 자산 뷰
  - 파일: `ui/widgets/unified_portfolio_widget.py`
  - 추가: 별도 탭으로 표시
  - 시간: 2~3시간

- [ ] **Day 4**: 테스트 + 문서화
  - 단위 테스트: `tests/test_multi_exchange_ui.py`
  - 사용 가이드 작성
  - 시간: 2~3시간

### **Week 3 (선택)**
- [ ] **분산 거래 실행**
  - 신호를 여러 거래소에 동시 실행
  - 예: "LONG BTC/USDT on all exchanges"
  
- [ ] **자동 리밸런싱**
  - 거래소 간 자산 비중 유지
  - 예: "Binance 40%, Upbit 30%, Kraken 30%"

---

## 5️⃣ 클라우드 전환 준비 (향후 4~8주)

### **아키텍처 변경 최소화**

```python
# 현재 (로컬)
exchange_manager = ExchangeManager(settings, binance_client)
trader = UnifiedTrader(exchange_manager)
signal = trader.analyze_coins(['BTC', 'ETH'])

# 미래 (클라우드)
# 변경 사항: 거의 없음!
api_client = APIClient(server_url='https://api.noahai.com')
signal = api_client.get_signals(['BTC', 'ETH'])  # 원격 서버에서 AI 신호 받음
```

**핵심**: API를 ExchangeManager 처럼 추상화하면 코드 변경 최소화

```python
# api/cloud_signal_provider.py (향후 추가)

class CloudSignalProvider:
    """클라우드 기반 신호 제공 (집단학습)"""
    
    def __init__(self, server_url: str, user_token: str):
        self.server_url = server_url
        self.user_token = user_token
    
    def get_signal(self, symbol: str, exchange: str) -> Dict:
        """
        서버에서 신호 받음
        - 모든 사용자의 데이터로 학습한 AI 모델 사용
        - 정확도: 55% → 70% (집단학습 효과)
        """
        return requests.get(
            f"{self.server_url}/signals/{exchange}/{symbol}",
            headers={'Authorization': f'Bearer {self.user_token}'}
        ).json()
    
    def submit_trade(self, trade_data: Dict):
        """
        거래 데이터 제출
        - 서버가 수집 → 월간 AI 재학습
        """
        return requests.post(
            f"{self.server_url}/trades",
            json=trade_data,
            headers={'Authorization': f'Bearer {self.user_token}'}
        ).json()
```

---

## 📋 체크리스트

### **즉시 (이번 주)**
- [ ] Kraken 어댑터 구현 (1시간)
- [ ] 거래소 탭 UI (4시간)
- [ ] 테스트 (2시간)

### **단기 (이번 달)**
- [ ] 통합 자산 뷰 (3시간)
- [ ] 문서화 (2시간)
- [ ] 베타 테스트 (1주)

### **중기 (1~3개월)**
- [ ] REST API 구축 (2~4주)
- [ ] 클라우드 배포 (2주)
- [ ] 집단학습 엔진 (4~8주)

---

## 🎯 최종 비전

```
현재 (2026-04-28)          미래 (2026-07-31)
───────────────────────────────────────────
로컬 단일 거래소    →    클라우드 다중 거래소
신호: 55% 정확도    →    신호: 70% 정확도
수동 거래           →    자동 분산 거래
개인 학습           →    집단학습 (1000명)
월 2M 수익률        →    월 4.5M 수익률 (126% 증가)
```

