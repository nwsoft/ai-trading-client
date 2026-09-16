"""Read-only multi-exchange public candle providers for the Web chart."""

from __future__ import annotations

import re
import threading
import time
from typing import Any

import requests
from trading.exchanges.venue_capabilities import CRYPTO_VENUES, USDT_FUTURES_VENUES

from .contracts import CandleContract, CandleSnapshotContract


BINANCE_SPOT_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_FUTURES_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
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
        self._sentiment_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def get_futures_sentiment(self, symbol: str = "BTCUSDT") -> dict[str, Any]:
        """Return the same public funding/long-short inputs used by the legacy trend widget."""
        normalized_symbol = str(symbol or "").upper().strip()
        if not SYMBOL_PATTERN.fullmatch(normalized_symbol):
            raise ValueError("unsupported symbol format")
        now = time.monotonic()
        with self._lock:
            cached = self._sentiment_cache.get(normalized_symbol)
            if cached and now - cached[0] <= max(30.0, self._ttl_seconds):
                return dict(cached[1])
        try:
            funding_response = self._session.get(
                "https://fapi.binance.com/fapi/v1/fundingRate",
                params={"symbol": normalized_symbol, "limit": 1},
                timeout=(3.0, 8.0),
            )
            funding_response.raise_for_status()
            funding_rows = funding_response.json()
            ratio_response = self._session.get(
                "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
                params={"symbol": normalized_symbol, "period": "5m", "limit": 1},
                timeout=(3.0, 8.0),
            )
            ratio_response.raise_for_status()
            ratio_rows = ratio_response.json()
            if not isinstance(funding_rows, list) or not funding_rows or not isinstance(ratio_rows, list) or not ratio_rows:
                raise PublicMarketDataError("binance_public_sentiment_invalid_payload")
            result = {
                "source": "binance",
                "symbol": normalized_symbol,
                "funding_rate": float(funding_rows[0].get("fundingRate", 0.0)),
                "long_short_ratio": float(ratio_rows[0].get("longShortRatio", 1.0)),
                "captured_at": int(time.time() * 1000),
            }
        except (requests.RequestException, TypeError, ValueError, KeyError, IndexError) as exc:
            raise PublicMarketDataError("binance_public_sentiment_unavailable") from exc
        with self._lock:
            self._sentiment_cache[normalized_symbol] = (now, result)
        return dict(result)

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


class MultiSourcePublicMarketData(BinancePublicMarketData):
    SOURCES = set(CRYPTO_VENUES)

    def get_candles(self, source: str, market_type: str, symbol: str, interval: str, limit: int = 300) -> CandleSnapshotContract:
        venue = str(source or "").lower().strip()
        kind = str(market_type or "spot").lower().strip()
        if venue not in self.SOURCES:
            raise ValueError("unsupported market source")
        if venue == "binance" and kind == "spot":
            return self.get_spot_candles(symbol, interval, limit)
        normalized_symbol = str(symbol or "").upper().strip().replace("/", "").replace("_", "").replace("-", "")
        if not SYMBOL_PATTERN.fullmatch(normalized_symbol):
            raise ValueError("unsupported symbol format")
        bounded = max(10, min(int(limit), 1000 if venue in USDT_FUTURES_VENUES else 200))
        cache_key = (f"{venue}:{kind}:{normalized_symbol}", str(interval), bounded)
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and now - cached[0] <= self._ttl_seconds:
                return cached[1]
        try:
            # Build only exact, complete groups when an API lacks the requested
            # interval. Never rename a 30m series to 15m.
            aggregation = {"2h": ("1h", 2)} if venue == "bithumb" else {}
            base_interval, factor = aggregation.get(str(interval), (str(interval), 1))
            rows = self._request_rows(venue, kind, normalized_symbol, base_interval, bounded * factor + (factor if factor > 1 else 0))
            candles = self._normalize_rows(venue, kind, normalized_symbol, base_interval, rows)
            if factor > 1:
                buckets: dict[int, dict[int, CandleContract]] = {}
                width = interval_milliseconds(str(interval))
                step = interval_milliseconds(base_interval)
                for candle in candles:
                    bucket = candle.open_time // width * width
                    buckets.setdefault(bucket, {})[candle.open_time] = candle
                aggregated = []
                for start, group in sorted(buckets.items()):
                    if set(group) != {start + i * step for i in range(factor)}:
                        continue
                    parts = [group[start + i * step] for i in range(factor)]
                    aggregated.append(CandleContract(
                        source=venue, market_type=kind, symbol=normalized_symbol, interval=str(interval),
                        open_time=start, close_time=start + width - 1,
                        open=parts[0].open, high=max(p.high for p in parts), low=min(p.low for p in parts),
                        close=parts[-1].close, volume=sum(p.volume for p in parts),
                        closed=all(p.closed for p in parts), sequence=len(aggregated),
                    ))
                candles = aggregated[-bounded:]
        except ValueError:
            raise
        except (requests.RequestException, TypeError, KeyError, IndexError) as exc:
            raise PublicMarketDataError(f"{venue}_public_candles_unavailable") from exc
        snapshot = CandleSnapshotContract(source=venue, symbol=normalized_symbol, interval=str(interval), candles=candles)
        with self._lock:
            self._cache[cache_key] = (now, snapshot)
        return snapshot

    def _request_rows(self, venue: str, market_type: str, symbol: str, interval: str, limit: int) -> list[Any]:
        if venue == "binance":
            if interval not in BINANCE_INTERVALS:
                raise ValueError("unsupported candle interval")
            url = BINANCE_FUTURES_KLINES_URL if market_type == "futures" else BINANCE_SPOT_KLINES_URL
            response = self._session.get(url, params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=(3.0, 8.0))
            response.raise_for_status(); payload = response.json()
            if not isinstance(payload, list): raise PublicMarketDataError("binance_public_candles_invalid_payload")
            return payload
        if venue == "bybit":
            mapping = {"1m":"1","3m":"3","5m":"5","15m":"15","30m":"30","1h":"60","2h":"120","4h":"240","6h":"360","12h":"720","1d":"D","1w":"W","1M":"M"}
            if interval not in mapping: raise ValueError("unsupported candle interval")
            response = self._session.get("https://api.bybit.com/v5/market/kline", params={"category":"linear" if market_type == "futures" else "spot","symbol":symbol,"interval":mapping[interval],"limit":limit}, timeout=(3.0,8.0))
            response.raise_for_status(); payload = response.json()
            if int(payload.get("retCode", -1)) != 0: raise PublicMarketDataError("bybit_public_candles_error")
            return list((payload.get("result") or {}).get("list") or [])
        if venue == "okx":
            mapping = {"1m":"1m","3m":"3m","5m":"5m","15m":"15m","30m":"30m","1h":"1H","2h":"2H","4h":"4H","6h":"6H","12h":"12H","1d":"1D","3d":"3D","1w":"1W","1M":"1M"}
            if interval not in mapping: raise ValueError("unsupported candle interval")
            base = symbol[:-4] if symbol.endswith("USDT") else symbol
            inst_id = f"{base}-USDT-SWAP" if market_type == "futures" else f"{base}-USDT"
            response = self._session.get("https://www.okx.com/api/v5/market/candles", params={"instId":inst_id,"bar":mapping[interval],"limit":min(limit,300)}, timeout=(3.0,8.0))
            response.raise_for_status(); payload = response.json()
            if str(payload.get("code")) != "0": raise PublicMarketDataError("okx_public_candles_error")
            return list(payload.get("data") or [])
        if venue == "bitget":
            if interval not in BINANCE_INTERVALS - {"8h"}: raise ValueError("unsupported candle interval")
            response = self._session.get("https://api.bitget.com/api/v2/mix/market/candles", params={"symbol":symbol,"productType":"USDT-FUTURES","granularity":interval,"limit":min(limit,1000)}, timeout=(3.0,8.0))
            response.raise_for_status(); payload = response.json()
            if str(payload.get("code")) != "00000": raise PublicMarketDataError("bitget_public_candles_error")
            return list(payload.get("data") or [])
        quote = "KRW"
        base = symbol[:-3] if symbol.endswith(quote) else symbol[3:] if symbol.startswith(quote) else symbol.replace("USDT", "")
        if venue == "upbit":
            minute_map = {"1m":1,"3m":3,"5m":5,"15m":15,"30m":30,"1h":60,"4h":240}
            if interval in minute_map:
                url = f"https://api.upbit.com/v1/candles/minutes/{minute_map[interval]}"
            elif interval == "1d": url = "https://api.upbit.com/v1/candles/days"
            elif interval == "1w": url = "https://api.upbit.com/v1/candles/weeks"
            else: raise ValueError("unsupported candle interval")
            response = self._session.get(url, params={"market":f"KRW-{base}","count":limit}, timeout=(3.0,8.0)); response.raise_for_status(); payload=response.json()
            if not isinstance(payload,list): raise PublicMarketDataError("upbit_public_candles_invalid_payload")
            return payload
        if venue == "bithumb":
            # v1.2 candlestick is capped at 200 rows. Use native v2.1
            # minute candles for 15m/4h instead of shrinking the sample by
            # resampling that legacy response.
            if interval in {"15m", "4h"}:
                minutes = 15 if interval == "15m" else 240
                response = self._session.get(
                    f"https://api.bithumb.com/v1/candles/minutes/{minutes}",
                    params={"market": f"KRW-{base}", "count": min(limit, 200)}, timeout=(3.0,8.0),
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    raise PublicMarketDataError("bithumb_public_candles_invalid_payload")
                return [[int(datetime_from_iso(row["candle_date_time_utc"]).timestamp()*1000),
                         row["opening_price"], row["trade_price"], row["high_price"],
                         row["low_price"], row["candle_acc_trade_volume"]] for row in payload]
            mapping = {"1m":"1m","3m":"3m","5m":"5m","10m":"10m","30m":"30m","1h":"1h","6h":"6h","12h":"12h","1d":"24h"}
            if interval not in mapping: raise ValueError("unsupported candle interval")
            response = self._session.get(f"https://api.bithumb.com/public/candlestick/{base}_KRW/{mapping[interval]}", params={}, timeout=(3.0,8.0)); response.raise_for_status(); payload=response.json()
            if str(payload.get("status")) != "0000": raise PublicMarketDataError("bithumb_public_candles_error")
            return list(payload.get("data") or [])[-limit:]
        if venue == "coinone":
            supported = {"1m", "3m", "5m", "10m", "15m", "30m", "1h", "2h", "4h", "6h", "1d", "1w"}
            if market_type != "spot" or interval not in supported:
                raise ValueError("Coinone 현물에서 지원하지 않는 시간봉입니다.")
            response = self._session.get(
                f"https://api.coinone.co.kr/public/v2/chart/KRW/{base}",
                params={"interval": interval, "size": min(limit, 500)}, timeout=(3.0, 8.0),
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("result") != "success" or str(payload.get("error_code", "0")) != "0":
                raise PublicMarketDataError("coinone_public_candles_error")
            return [[row["timestamp"], row["open"], row["high"], row["low"], row["close"], row["target_volume"]]
                    for row in payload.get("chart", [])]
        raise ValueError("unsupported market source")

    @staticmethod
    def _normalize_rows(venue: str, market_type: str, symbol: str, interval: str, rows: list[Any]) -> list[CandleContract]:
        now_ms = int(time.time() * 1000)
        output: list[CandleContract] = []
        # Providers return different orders, including ascending Bitget and
        # descending Coinone responses. Sort by timestamp, never by venue guess.
        ordered = sorted(rows, key=lambda row: (
            datetime_from_iso(str(row.get("candle_date_time_utc"))).timestamp() * 1000
            if venue == "upbit" else int(row[0])
        ))
        for sequence, row in enumerate(ordered):
            if venue == "upbit":
                open_time = int(datetime_from_iso(str(row.get("candle_date_time_utc"))).timestamp() * 1000)
                values = (row["opening_price"], row["high_price"], row["low_price"], row["trade_price"], row["candle_acc_trade_volume"])
                close_time = open_time + interval_milliseconds(interval) - 1
            elif venue == "bithumb":
                open_time = int(row[0]); values = (row[1], row[3], row[4], row[2], row[5]); close_time = open_time + interval_milliseconds(interval) - 1
            else:
                open_time = int(row[0]); values = (row[1], row[2], row[3], row[4], row[5]); close_time = open_time + interval_milliseconds(interval) - 1
                if venue == "binance" and len(row) > 6: close_time = int(row[6])
            output.append(CandleContract(source=venue, market_type="futures" if market_type == "futures" else "spot", symbol=symbol, interval=interval, open_time=open_time, close_time=close_time, open=float(values[0]), high=float(values[1]), low=float(values[2]), close=float(values[3]), volume=float(values[4]), closed=close_time < now_ms, sequence=sequence))
        return output


def datetime_from_iso(value: str):
    from datetime import datetime, timezone
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def interval_milliseconds(interval: str) -> int:
    unit = interval[-1]
    amount = int(interval[:-1])
    return amount * {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000, "M": 2_592_000_000}.get(unit, 60_000)
