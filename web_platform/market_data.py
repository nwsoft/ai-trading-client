"""Read-only public market data providers for the Web chart POC."""

from __future__ import annotations

import re
import threading
import time
from typing import Any

import requests

from .contracts import CandleContract, CandleSnapshotContract


BINANCE_SPOT_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
}
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{3,24}$")


class PublicMarketDataError(RuntimeError):
    """A sanitized public-market-data failure."""


class BinancePublicMarketData:
    def __init__(self, *, session: requests.Session | None = None, ttl_seconds: float = 2.0):
        self._session = session or requests.Session()
        self._ttl_seconds = max(0.0, float(ttl_seconds))
        self._cache: dict[tuple[str, str, int], tuple[float, CandleSnapshotContract]] = {}
        self._lock = threading.Lock()

    def get_spot_candles(self, symbol: str, interval: str, limit: int = 300) -> CandleSnapshotContract:
        normalized_symbol = str(symbol or "").upper().strip()
        normalized_interval = str(interval or "").strip()
        bounded_limit = max(10, min(int(limit), 1000))

        if not SYMBOL_PATTERN.fullmatch(normalized_symbol):
            raise ValueError("unsupported symbol format")
        if normalized_interval not in BINANCE_INTERVALS:
            raise ValueError("unsupported candle interval")

        cache_key = (normalized_symbol, normalized_interval, bounded_limit)
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and now - cached[0] <= self._ttl_seconds:
                return cached[1]

        try:
            response = self._session.get(
                BINANCE_SPOT_KLINES_URL,
                params={
                    "symbol": normalized_symbol,
                    "interval": normalized_interval,
                    "limit": bounded_limit,
                },
                timeout=(3.0, 8.0),
            )
            response.raise_for_status()
            raw_rows: Any = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise PublicMarketDataError("binance_public_candles_unavailable") from exc

        if not isinstance(raw_rows, list):
            raise PublicMarketDataError("binance_public_candles_invalid_payload")

        now_ms = int(time.time() * 1000)
        candles: list[CandleContract] = []
        for sequence, row in enumerate(raw_rows):
            if not isinstance(row, list) or len(row) < 7:
                raise PublicMarketDataError("binance_public_candles_invalid_row")
            try:
                open_time = int(row[0])
                close_time = int(row[6])
                candles.append(
                    CandleContract(
                        source="binance",
                        market_type="spot",
                        symbol=normalized_symbol,
                        interval=normalized_interval,
                        open_time=open_time,
                        close_time=close_time,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                        closed=close_time < now_ms,
                        sequence=sequence,
                    )
                )
            except (TypeError, ValueError, IndexError) as exc:
                raise PublicMarketDataError("binance_public_candles_invalid_row") from exc

        snapshot = CandleSnapshotContract(
            source="binance",
            symbol=normalized_symbol,
            interval=normalized_interval,
            candles=candles,
        )
        with self._lock:
            self._cache[cache_key] = (now, snapshot)
        return snapshot
