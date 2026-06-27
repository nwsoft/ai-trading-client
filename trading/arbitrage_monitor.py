#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""거래소 간 차익(Arbitrage) 기회 탐지 모듈."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class ExchangeQuote:
    """단일 거래소 시세 스냅샷."""

    exchange: str
    symbol: str
    bid: float
    ask: float
    timestamp: datetime


@dataclass
class ArbitrageOpportunity:
    """차익 기회 결과."""

    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    spread: float
    estimated_fee: float
    estimated_profit: float
    detected_at: datetime


class ArbitrageMonitor:
    """다중 거래소 시세를 기반으로 차익 기회를 탐지한다."""

    def __init__(self, fee_rates: Optional[Dict[str, float]] = None, min_profit: float = 0.0):
        # fee_rates 예시: {"binance": 0.0004, "bybit": 0.0006}
        self.fee_rates = fee_rates or {}
        self.min_profit = float(min_profit)

    def _fee_rate(self, exchange: str) -> float:
        return float(self.fee_rates.get(exchange.lower(), 0.001))

    def estimate_round_trip_fee(self, buy_exchange: str, sell_exchange: str, buy_price: float, sell_price: float) -> float:
        buy_fee = buy_price * self._fee_rate(buy_exchange)
        sell_fee = sell_price * self._fee_rate(sell_exchange)
        return buy_fee + sell_fee

    def find_best_opportunity(self, quotes: Iterable[ExchangeQuote], symbol: str) -> Optional[ArbitrageOpportunity]:
        candidates = [q for q in quotes if q.symbol == symbol and q.ask > 0 and q.bid > 0]
        if len(candidates) < 2:
            return None

        best: Optional[ArbitrageOpportunity] = None
        for buy_q in candidates:
            for sell_q in candidates:
                if buy_q.exchange == sell_q.exchange:
                    continue
                spread = sell_q.bid - buy_q.ask
                fee = self.estimate_round_trip_fee(
                    buy_exchange=buy_q.exchange,
                    sell_exchange=sell_q.exchange,
                    buy_price=buy_q.ask,
                    sell_price=sell_q.bid,
                )
                estimated_profit = spread - fee
                if estimated_profit < self.min_profit:
                    continue

                opp = ArbitrageOpportunity(
                    symbol=symbol,
                    buy_exchange=buy_q.exchange,
                    sell_exchange=sell_q.exchange,
                    buy_price=buy_q.ask,
                    sell_price=sell_q.bid,
                    spread=spread,
                    estimated_fee=fee,
                    estimated_profit=estimated_profit,
                    detected_at=datetime.now(),
                )
                if best is None or opp.estimated_profit > best.estimated_profit:
                    best = opp
        return best

    def find_opportunities(self, quotes: Iterable[ExchangeQuote]) -> List[ArbitrageOpportunity]:
        by_symbol: Dict[str, List[ExchangeQuote]] = {}
        for quote in quotes:
            by_symbol.setdefault(quote.symbol, []).append(quote)

        found: List[ArbitrageOpportunity] = []
        for symbol, symbol_quotes in by_symbol.items():
            best = self.find_best_opportunity(symbol_quotes, symbol)
            if best is not None:
                found.append(best)

        found.sort(key=lambda x: x.estimated_profit, reverse=True)
        return found


def quote_from_ticker(exchange: str, symbol: str, ticker: Dict[str, Any]) -> Optional[ExchangeQuote]:
    """공통 ticker dict에서 ExchangeQuote 생성 헬퍼."""
    bid = float(ticker.get("bid") or ticker.get("bid_price") or 0)
    ask = float(ticker.get("ask") or ticker.get("ask_price") or 0)
    if bid <= 0 or ask <= 0:
        return None
    return ExchangeQuote(
        exchange=exchange,
        symbol=symbol,
        bid=bid,
        ask=ask,
        timestamp=datetime.now(),
    )
