#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
주식/ETF 테스트용 Mock 어댑터
실제 API 없이도 전체 흐름을 검증할 수 있게 샘플 데이터 반환

용도:
  1. 단위 테스트 / 통합 테스트
  2. 데모 모드 (API 키 없이 UI 확인)
  3. API 연동 전 개발 중 대리(Stub)

사용법:
  settings.json > stock_broker_configs.kiwoom.api_type = "mock"
  또는 exchange_factory.py에서 mock=True 파라미터 사용
"""

import logging
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from ..interfaces.stock_exchange import StockExchange


# ─── 샘플 데이터 (실제 종목 기반, 가격은 임의) ───────────────────────────────

_SAMPLE_STOCKS = [
    {"code": "005930", "name": "삼성전자",    "market": "KOSPI", "sector": "반도체"},
    {"code": "000660", "name": "SK하이닉스",  "market": "KOSPI", "sector": "반도체"},
    {"code": "051910", "name": "LG화학",      "market": "KOSPI", "sector": "화학"},
    {"code": "035420", "name": "NAVER",       "market": "KOSPI", "sector": "IT"},
    {"code": "035720", "name": "카카오",      "market": "KOSPI", "sector": "IT"},
    {"code": "207940", "name": "삼성바이오",  "market": "KOSPI", "sector": "바이오"},
    {"code": "006400", "name": "삼성SDI",     "market": "KOSPI", "sector": "2차전지"},
    {"code": "373220", "name": "LG에너지솔루션", "market": "KOSPI", "sector": "2차전지"},
    {"code": "003490", "name": "대한항공",    "market": "KOSPI", "sector": "항공"},
    {"code": "033780", "name": "KT&G",        "market": "KOSPI", "sector": "담배"},
    {"code": "263750", "name": "펄어비스",    "market": "KOSDAQ", "sector": "게임"},
    {"code": "293490", "name": "카카오게임즈","market": "KOSDAQ", "sector": "게임"},
]

_SAMPLE_ETFS = [
    {"code": "069500", "name": "KODEX 200",          "market": "ETF", "base_index": "KOSPI200"},
    {"code": "102110", "name": "TIGER 200",           "market": "ETF", "base_index": "KOSPI200"},
    {"code": "122630", "name": "KODEX 레버리지",      "market": "ETF", "base_index": "KOSPI200 2x"},
    {"code": "114800", "name": "KODEX 인버스",        "market": "ETF", "base_index": "KOSPI200 -1x"},
    {"code": "261120", "name": "KODEX 국고채3년",     "market": "ETF", "base_index": "국고채3년"},
    {"code": "292000", "name": "KODEX 골드선물H",     "market": "ETF", "base_index": "Gold Futures"},
    {"code": "143010", "name": "TIGER 200IT레버리지", "market": "ETF", "base_index": "KOSPI200 IT"},
    {"code": "111020", "name": "TIGER 국채10년",      "market": "ETF", "base_index": "국채10년"},
]

_BASE_PRICES = {
    "005930": 72000, "000660": 175000, "051910": 320000,
    "035420": 185000, "035720": 45000, "207940": 850000,
    "006400": 390000, "373220": 480000, "003490": 23000,
    "033780": 90000, "263750": 32000, "293490": 12000,
    "069500": 35000, "102110": 15000, "122630": 20000,
    "114800": 5000,  "261120": 9800,  "292000": 11000,
    "143010": 8200,  "111020": 10500,
}


def _mock_price(code: str, noise: float = 0.02) -> float:
    """기준가에 ±noise 범위의 랜덤 가격 반환"""
    base = _BASE_PRICES.get(code, 10000)
    return round(base * (1 + random.uniform(-noise, noise)))


def _mock_change_rate() -> float:
    """임의 등락률"""
    return round(random.uniform(-3.0, 3.0), 2)


class StockMockAdapter(StockExchange):
    """
    주식/ETF Mock 어댑터
    실제 API 없이도 전체 흐름 검증 가능
    
    Args:
        broker_name: 'kiwoom' | 'shinhan' | 'miraeAsset' | 'koreaInvestment'
        user_id: (무시됨, 형식 호환용)
        password: (무시됨, 형식 호환용)
        latency_ms: 인위적 지연 (ms, 기본 50)
    """
    
    def __init__(
        self,
        broker_name: str = "mock",
        user_id: str = "",
        password: str = "",
        cert_password: str = "",
        account_no: str = "",
        latency_ms: int = 50,
        **kwargs
    ):
        super().__init__(broker_name)
        self.broker_name = broker_name
        self.user_id = user_id
        self.account_no = account_no or "1234567890"
        self.latency_ms = latency_ms
        self.api_type = kwargs.get('api_type', 'mock')
        self.api_version = kwargs.get('api_version', 'sim_v1')
        self.logger = logging.getLogger(__name__)
        
        # 가상 잔고/포지션 상태
        self._cash = 5_000_000.0      # 초기 현금 500만원
        self._holdings: Dict[str, Dict[str, Any]] = {
            "005930": {"quantity": 10, "avg_price": 70000, "name": "삼성전자"},
            "069500": {"quantity": 5,  "avg_price": 34500, "name": "KODEX 200"},
        }
        self._order_counter = 1000
        self._orders: Dict[str, Dict[str, Any]] = {}
        
        # ETF 코드 범위
        self.etf_code_ranges = [
            (69500,  69599),    # KODEX, KINDEX 등
            (102000, 102999),
            (105000, 115999),   # KODEX 인버스/레버리지 등 (114800 포함)
            (117000, 117999),
            (122000, 122999),
            (143000, 143999),
            (261000, 261999),
            (292000, 292999),
            (295000, 295999),
        ]
    
    def _delay(self):
        """API 지연 시뮬레이션"""
        if self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000)
    
    # ─── 연결 ───────────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Mock 연결 (항상 성공)"""
        self._delay()
        self.is_connected = True
        self.logger.info(f"[MOCK] {self.broker_name} 연결 성공")
        return True
    
    def disconnect(self) -> None:
        """Mock 연결 해제"""
        self.is_connected = False
        self.logger.info(f"[MOCK] {self.broker_name} 연결 해제")
    
    # ─── 종목 조회 ───────────────────────────────────────────────────────────────

    def get_stock_list(self, market: str = "KOSPI") -> List[Dict[str, Any]]:
        """주식 목록 조회"""
        self._delay()
        result = []
        for s in _SAMPLE_STOCKS:
            if market == "ALL" or s["market"] == market:
                price = _mock_price(s["code"])
                result.append({
                    **s,
                    "current_price": price,
                    "change_rate": _mock_change_rate(),
                    "volume": random.randint(100_000, 10_000_000),
                    "market_cap": price * random.randint(1_000_000, 100_000_000),
                    "timestamp": datetime.now().isoformat(),
                })
        return result
    
    def get_etf_list(self) -> List[Dict[str, Any]]:
        """ETF 목록 조회"""
        self._delay()
        result = []
        for e in _SAMPLE_ETFS:
            price = _mock_price(e["code"])
            result.append({
                **e,
                "current_price": price,
                "change_rate": _mock_change_rate(),
                "volume": random.randint(10_000, 1_000_000),
                "nav": price * random.uniform(0.999, 1.001),   # 순자산가치
                "tracking_error": round(random.uniform(0.001, 0.05), 4),
                "expense_ratio": round(random.uniform(0.001, 0.003), 4),
                "trade_value": float(random.randint(1_000_000, 50_000_000_000)),
                "timestamp": datetime.now().isoformat(),
            })
        return result

    def get_etf_realtime_metrics(self, symbol: str) -> Dict[str, Any]:
        """ETF 실시간 지표 조회 (Mock)."""
        self._delay()
        etf = next((e for e in _SAMPLE_ETFS if e["code"] == symbol), None)
        if not etf:
            return {"status": "error", "error": "not_found"}
        price = _mock_price(symbol)
        nav = price * random.uniform(0.997, 1.003)
        return {
            "code": symbol,
            "current_price": price,
            "change_rate": _mock_change_rate(),
            "volume": random.randint(10_000, 1_000_000),
            "trade_value": float(random.randint(1_000_000, 50_000_000_000)),
            "nav": nav,
            "tracking_error": round(random.uniform(0.001, 0.05), 4),
            "expense_ratio": round(random.uniform(0.001, 0.003), 4),
            "base_index": etf.get("base_index", ""),
            "timestamp": datetime.now().isoformat(),
            "status": "ok",
        }
    
    def is_etf(self, symbol: str) -> bool:
        """ETF 여부 확인"""
        try:
            code_int = int(symbol)
            for start, end in self.etf_code_ranges:
                if start <= code_int <= end:
                    return True
            return False
        except (ValueError, TypeError):
            return False
    
    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """종목 상세 정보"""
        self._delay()
        # 주식/ETF 모두에서 검색
        all_items = _SAMPLE_STOCKS + _SAMPLE_ETFS
        item = next((x for x in all_items if x["code"] == symbol), None)
        if not item:
            return {"status": "not_found", "code": symbol}
        
        price = _mock_price(symbol)
        return {
            **item,
            "current_price": price,
            "open_price":   round(price * random.uniform(0.98, 1.02)),
            "high_price":   round(price * random.uniform(1.0,  1.03)),
            "low_price":    round(price * random.uniform(0.97, 1.0)),
            "prev_close":   round(price * random.uniform(0.98, 1.02)),
            "change_rate":  _mock_change_rate(),
            "volume":       random.randint(100_000, 5_000_000),
            "is_etf":       self.is_etf(symbol),
            "timestamp":    datetime.now().isoformat(),
        }
    
    def get_realtime_price(self, symbol: str) -> Dict[str, Any]:
        """실시간 시세"""
        self._delay()
        price = _mock_price(symbol, noise=0.005)
        return {
            "code":         symbol,
            "current_price": price,
            "change_rate":  _mock_change_rate(),
            "volume":       random.randint(1000, 50000),
            "timestamp":    datetime.now().isoformat(),
            "status":       "ok",
        }
    
    # ─── 계좌/잔고/포지션 ─────────────────────────────────────────────────────────

    def get_account_info(self) -> Dict[str, Any]:
        """계정 정보 조회"""
        self._delay()
        total_eval = sum(
            h["quantity"] * _mock_price(code)
            for code, h in self._holdings.items()
        )
        total_assets = self._cash + total_eval
        return {
            "account_no":     self.account_no,
            "user_id":        self.user_id or "mock_user",
            "api_type": self.api_type,
            "api_version": self.api_version,
            "broker":         self.broker_name,
            "cash":           round(self._cash),
            "stock_eval":     round(total_eval),
            "total_assets":   round(total_assets),
            "profit_loss":    round(total_assets - 5_000_000),
            "profit_rate":    round((total_assets - 5_000_000) / 5_000_000 * 100, 2),
            "timestamp":      datetime.now().isoformat(),
            "status":         "ok",
        }
    
    def get_balance(self) -> Dict[str, Any]:
        """잔고 조회"""
        return self.get_account_info()
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """보유 종목 조회"""
        self._delay()
        result = []
        for code, h in self._holdings.items():
            current = _mock_price(code)
            avg = h["avg_price"]
            qty = h["quantity"]
            pnl = (current - avg) * qty
            result.append({
                "code":        code,
                "name":        h["name"],
                "quantity":    qty,
                "avg_price":   avg,
                "current_price": current,
                "eval_amount": current * qty,
                "pnl":         round(pnl),
                "pnl_rate":    round((current - avg) / avg * 100, 2),
                "is_etf":      self.is_etf(code),
                "timestamp":   datetime.now().isoformat(),
            })
        return result
    
    # ─── 주문 ────────────────────────────────────────────────────────────────────

    def place_order(
        self, symbol: str, side: str, quantity: float, price: float
    ) -> Dict[str, Any]:
        """주문 실행"""
        self._delay()
        if not self.is_connected:
            return {"status": "error", "error": "not_connected"}
        
        order_id = f"MOCK-{self._order_counter}"
        self._order_counter += 1
        
        # 실제 잔고/포지션 반영
        if side.upper() in ("BUY", "매수"):
            cost = price * quantity
            if cost > self._cash:
                return {"status": "error", "error": "insufficient_cash"}
            self._cash -= cost
            existing = self._holdings.get(symbol)
            if existing:
                total_qty = existing["quantity"] + quantity
                avg = (existing["avg_price"] * existing["quantity"] + price * quantity) / total_qty
                self._holdings[symbol] = {"quantity": int(total_qty), "avg_price": avg, "name": existing.get("name", symbol)}
            else:
                all_items = _SAMPLE_STOCKS + _SAMPLE_ETFS
                name = next((x["name"] for x in all_items if x["code"] == symbol), symbol)
                self._holdings[symbol] = {"quantity": int(quantity), "avg_price": price, "name": name}
        
        elif side.upper() in ("SELL", "매도"):
            existing = self._holdings.get(symbol)
            if not existing or existing["quantity"] < quantity:
                return {"status": "error", "error": "insufficient_position"}
            self._cash += price * quantity
            remaining = existing["quantity"] - int(quantity)
            if remaining <= 0:
                del self._holdings[symbol]
            else:
                self._holdings[symbol]["quantity"] = remaining
        
        order = {
            "order_id":  order_id,
            "symbol":    symbol,
            "side":      side,
            "quantity":  quantity,
            "price":     price,
            "status":    "filled",
            "filled_at": datetime.now().isoformat(),
            "broker":    self.broker_name,
            "api_type":  "mock",
            "api_version": "mock",
            "execution_mode": "mock",
            "success":   True,
        }
        self._orders[order_id] = order
        self.logger.info(f"[MOCK] 주문 체결: {order_id} {side} {symbol} {quantity}@{price}")
        return order
    
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        """주문 취소"""
        self._delay()
        if order_id in self._orders:
            self._orders[order_id]["status"] = "cancelled"
            return True
        return False
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """미체결 주문 조회"""
        self._delay()
        orders = [o for o in self._orders.values() if o["status"] == "open"]
        if symbol:
            orders = [o for o in orders if o["symbol"] == symbol]
        return orders
    
    def get_trade_history(
        self, symbol: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """거래 내역 조회"""
        self._delay()
        history = list(self._orders.values())
        if symbol:
            history = [h for h in history if h["symbol"] == symbol]
        return history[:limit]
    
    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        """24시간 티커"""
        return self.get_realtime_price(symbol)
    
    # ─── 통계 ────────────────────────────────────────────────────────────────────

    def get_trading_stats(self) -> Dict[str, Any]:
        """거래 통계"""
        trades = list(self._orders.values())
        buy_count  = sum(1 for t in trades if t["side"].upper() in ("BUY",  "매수"))
        sell_count = sum(1 for t in trades if t["side"].upper() in ("SELL", "매도"))
        return {
            "total_trades": len(trades),
            "buy_count":    buy_count,
            "sell_count":   sell_count,
            "broker":       self.broker_name,
            "timestamp":    datetime.now().isoformat(),
        }
    
    def get_today_trades(self) -> List[Dict[str, Any]]:
        """오늘 거래 내역"""
        today = datetime.now().date()
        result = []
        for t in self._orders.values():
            try:
                trade_date = datetime.fromisoformat(t["filled_at"]).date()
                if trade_date == today:
                    result.append(t)
            except Exception:
                pass
        return result
