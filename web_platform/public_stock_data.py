"""Public Korean stock quotes used by the legacy market-trend surface."""

from __future__ import annotations

import time
from typing import Any, Iterable

import requests


class PublicKoreanStockData:
    """Read-only Naver Finance adapter; never substitutes account or order data."""

    STOCK_URL = "https://m.stock.naver.com/api/stock/{symbol}/basic"
    INDEX_URL = "https://m.stock.naver.com/api/index/{symbol}/basic"

    def __init__(self, session: requests.Session | None = None, *, timeout: float = 6.0, ttl_seconds: float = 60.0):
        self.session = session or requests.Session()
        self.timeout = max(1.0, float(timeout))
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    @staticmethod
    def _number(value: Any) -> float:
        text = str(value or "0").replace(",", "").replace("%", "").replace("+", "").strip()
        try:
            return float(text)
        except (TypeError, ValueError):
            return 0.0

    def _get(self, kind: str, symbol: str) -> dict[str, Any]:
        key = f"{kind}:{symbol}"
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < self.ttl_seconds:
            return dict(cached[1])
        template = self.INDEX_URL if kind == "index" else self.STOCK_URL
        url = template.format(symbol=symbol)
        try:
            response = self.session.get(url, timeout=self.timeout, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("invalid_public_stock_payload")
            raw_volume = payload.get("accumulatedTradingVolume") or payload.get("quant")
            row = {
                "symbol": symbol,
                "name": str(payload.get("stockName") or payload.get("indexName") or symbol),
                "price": self._number(payload.get("closePrice")),
                "change": self._number(payload.get("fluctuationsRatio")),
                "volume": self._number(raw_volume) if raw_volume not in (None, "") else None,
                "traded_at": str(payload.get("localTradedAt") or payload.get("localTradeAt") or ""),
                "market_status": str(payload.get("marketStatus") or ""),
                "status": "ok",
                "source": "naver_finance_public",
                "source_url": url,
                "freshness": "public_endpoint_exchange_dependent",
            }
        except Exception as exc:
            row = {
                "symbol": symbol,
                "name": symbol,
                "price": None,
                "change": None,
                "volume": None,
                "status": "unavailable",
                "source": "naver_finance_public",
                "error": f"{type(exc).__name__}:{exc}",
            }
        self._cache[key] = (time.monotonic(), dict(row))
        return row

    def snapshot(self, symbols: Iterable[str]) -> dict[str, Any]:
        normalized = []
        for raw in symbols:
            symbol = "".join(character for character in str(raw or "") if character.isdigit())
            if 5 <= len(symbol) <= 8 and symbol not in normalized:
                normalized.append(symbol)
        if not normalized:
            normalized = ["005930", "000660", "035420", "035720", "005380", "373220"]
        if len(normalized) > 20:
            raise ValueError("public_stock_symbol_count_invalid")
        quotes = [self._get("stock", symbol) for symbol in normalized]
        # The legacy numeric codes (0001/1001) now return StockConflict (409).
        # Naver's current public endpoint accepts the stable index symbols.
        indices = [self._get("index", symbol) for symbol in ("KOSPI", "KOSDAQ")]
        return {
            "schema_version": "1.0.0",
            "quotes": quotes,
            "indices": indices,
            "source": "naver_finance_public",
            "account_data": False,
            "order_capability": False,
            "status": "ok" if any(row["status"] == "ok" for row in quotes + indices) else "unavailable",
        }
