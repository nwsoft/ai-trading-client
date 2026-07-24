from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import requests

from .models import MarketPoint, Provenance
from .taxonomy import AssetTaxonomy


class PublicMarketDataProvider:
    """인증키 없이 사용할 수 있는 공개 시세 어댑터.

    Yahoo chart와 Binance public klines만 사용한다. 실패 시 가짜 가격을
    만들지 않고 빈 목록과 오류 상태를 반환한다.
    """

    YAHOO_CHART_URLS = (
        "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
    )
    BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"

    def __init__(self, session: Optional[requests.Session] = None, timeout: float = 8.0):
        self.session = session or requests.Session()
        self.timeout = max(1.0, float(timeout))
        self.session.headers["User-Agent"] = "Mozilla/5.0"

    def fetch_yahoo_history(
        self,
        symbol: str,
        range_name: str = "1mo",
        interval: str = "1d",
        asset_type: str = "stock",
    ) -> Dict[str, Any]:
        errors: List[str] = []
        for template in self.YAHOO_CHART_URLS:
            url = template.format(symbol=str(symbol).strip())
            try:
                response = self.session.get(
                    url,
                    params={"range": range_name, "interval": interval, "events": "div,splits"},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                chart = response.json().get("chart") or {}
            except Exception as exc:
                errors.append(f"{url}:{type(exc).__name__}:{exc}")
                continue
            error = chart.get("error")
            results = chart.get("result") or []
            if error or not results:
                errors.append(f"{url}:{error or 'empty_result'}")
                continue
            result = results[0]
            timestamps = result.get("timestamp") or []
            quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
            adjclose = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
            meta = result.get("meta") or {}
            currency = str(meta.get("currency") or "")
            exchange_tz = str(meta.get("exchangeTimezoneName") or "UTC")
            closes = quote.get("close") or []
            points: List[MarketPoint] = []
            for index, timestamp in enumerate(timestamps):
                close = self._at(closes, index)
                adjusted = self._at(adjclose, index)
                price = adjusted if adjusted is not None else close
                if price is None:
                    continue
                points.append(
                    MarketPoint(
                        symbol=str(symbol).upper(),
                        asset_type=asset_type,
                        price=float(price),
                        timestamp=datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat(),
                        open=self._at(quote.get("open") or [], index),
                        high=self._at(quote.get("high") or [], index),
                        low=self._at(quote.get("low") or [], index),
                        close=close,
                        volume=float(self._at(quote.get("volume") or [], index) or 0.0),
                        provenance=Provenance(
                            source="yahoo_chart",
                            source_url_or_id=url,
                            currency=currency,
                            timezone=exchange_tz,
                            freshness="delayed_or_exchange_dependent",
                            is_delayed=True,
                            quality_flags=["public_endpoint", "adjusted_close_used" if adjusted is not None else "raw_close_used"],
                        ),
                    )
                )
            return {
                "status": "ok",
                "symbol": str(symbol).upper(),
                "currency": currency,
                "timezone": exchange_tz,
                "points": [point.to_dict() for point in points],
            }
        return {"status": "error", "error": " | ".join(errors[-2:]) or "all_yahoo_endpoints_failed", "points": []}

    def fetch_binance_history(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 100,
    ) -> Dict[str, Any]:
        normalized = str(symbol or "").replace("/", "").upper()
        if not normalized.endswith("USDT"):
            normalized += "USDT"
        try:
            response = self.session.get(
                self.BINANCE_KLINES_URL,
                params={"symbol": normalized, "interval": interval, "limit": max(2, min(int(limit), 1000))},
                timeout=self.timeout,
            )
            response.raise_for_status()
            rows = response.json()
            points: List[MarketPoint] = []
            for row in rows if isinstance(rows, list) else []:
                points.append(
                    MarketPoint(
                        symbol=normalized,
                        asset_type="crypto",
                        price=float(row[4]),
                        timestamp=datetime.fromtimestamp(float(row[0]) / 1000.0, tz=timezone.utc).isoformat(),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                        provenance=Provenance(
                            source="binance_public",
                            source_url_or_id=self.BINANCE_KLINES_URL,
                            currency="USDT",
                            freshness="exchange_public_realtime",
                            is_delayed=False,
                            quality_flags=["public_endpoint"],
                        ),
                    )
                )
            return {"status": "ok", "symbol": normalized, "points": [point.to_dict() for point in points]}
        except Exception as exc:
            return {"status": "error", "error": f"{type(exc).__name__}:{exc}", "points": []}

    @staticmethod
    def _at(values: List[Any], index: int) -> Optional[float]:
        try:
            value = values[index]
            return None if value is None else float(value)
        except Exception:
            return None


class MarketIntelligenceEngine:
    PERIODS = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "YTD": None}

    def __init__(self, taxonomy: Optional[AssetTaxonomy] = None):
        self.taxonomy = taxonomy or AssetTaxonomy()

    @staticmethod
    def _prices(points: Iterable[Dict[str, Any]]) -> List[float]:
        values: List[float] = []
        for point in points:
            try:
                price = float(point.get("price", point.get("close")))
                if math.isfinite(price) and price > 0:
                    values.append(price)
            except Exception:
                continue
        return values

    def period_returns(self, points: Iterable[Dict[str, Any]]) -> Dict[str, Optional[float]]:
        point_list = list(points)
        prices = self._prices(point_list)
        if len(prices) < 2:
            return {period: None for period in self.PERIODS}
        result: Dict[str, Optional[float]] = {}
        for label, lookback in self.PERIODS.items():
            if label == "YTD":
                start_index = 0
                for idx, point in enumerate(point_list):
                    timestamp = str(point.get("timestamp") or "")
                    if timestamp.startswith(str(datetime.now(timezone.utc).year)):
                        start_index = idx
                        break
            else:
                start_index = max(0, len(prices) - 1 - int(lookback or 1))
            base = prices[start_index]
            result[label] = ((prices[-1] / base) - 1.0) * 100.0 if base else None
        return result

    def summarize_symbol(self, symbol: str, asset_type: str, points: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        rows = list(points)
        prices = self._prices(rows)
        returns = self.period_returns(rows)
        if not prices:
            return {
                "symbol": symbol,
                "asset_type": asset_type,
                "status": "no_data",
                "returns": returns,
                "quality_flags": ["no_valid_prices"],
            }
        daily_returns = [
            (prices[i] / prices[i - 1]) - 1.0
            for i in range(1, len(prices))
            if prices[i - 1] > 0
        ]
        mean = sum(daily_returns) / len(daily_returns) if daily_returns else 0.0
        variance = (
            sum((value - mean) ** 2 for value in daily_returns) / len(daily_returns)
            if daily_returns else 0.0
        )
        return {
            "symbol": symbol,
            "asset_type": asset_type,
            "status": "ok",
            "price": prices[-1],
            "returns": returns,
            "volatility_annualized": math.sqrt(variance) * math.sqrt(252) * 100.0,
            "sector": self.taxonomy.sector_for(symbol, asset_type),
            "as_of": str((rows[-1] or {}).get("timestamp") or ""),
            "provenance": (rows[-1] or {}).get("provenance") or {},
        }

    def build_heatmap(
        self,
        summaries: Iterable[Dict[str, Any]],
        period: str = "1D",
        metric: str = "return",
        weighting: str = "equal",
    ) -> Dict[str, Any]:
        grouped = self.taxonomy.group(summaries)
        cells: List[Dict[str, Any]] = []
        sector_rows: List[Dict[str, Any]] = []
        for sector, rows in sorted(grouped.items()):
            weighted_values: List[tuple[float, float]] = []
            for row in rows:
                if metric == "volatility":
                    value = row.get("volatility_annualized")
                else:
                    value = (row.get("returns") or {}).get(period)
                if value is None:
                    continue
                weight = float(row.get("market_cap", 1.0) or 1.0) if weighting == "market_cap" else 1.0
                weighted_values.append((float(value), max(0.0, weight)))
                cells.append(
                    {
                        "sector": sector,
                        "symbol": row.get("symbol"),
                        "value": float(value),
                        "weight": weight,
                        "held": bool(row.get("held")),
                        "watched": bool(row.get("watched")),
                    }
                )
            denominator = sum(weight for _, weight in weighted_values)
            sector_value = (
                sum(value * weight for value, weight in weighted_values) / denominator
                if denominator > 0 else None
            )
            sector_rows.append({"sector": sector, "value": sector_value, "count": len(weighted_values)})
        return {
            "period": period,
            "metric": metric,
            "weighting": weighting,
            "sectors": sector_rows,
            "cells": cells,
            "generated_at": time.time(),
        }
