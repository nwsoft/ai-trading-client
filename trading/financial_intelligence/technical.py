from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional


class TechnicalIndicatorEngine:
    @staticmethod
    def _valid(values: Iterable[Any]) -> List[float]:
        output: List[float] = []
        for value in values:
            try:
                number = float(value)
                if math.isfinite(number):
                    output.append(number)
            except Exception:
                continue
        return output

    @staticmethod
    def sma(values: List[float], period: int) -> Optional[float]:
        if len(values) < period or period <= 0:
            return None
        return sum(values[-period:]) / period

    @staticmethod
    def ema_series(values: List[float], period: int) -> List[float]:
        if not values or period <= 0:
            return []
        alpha = 2.0 / (period + 1.0)
        output = [values[0]]
        for value in values[1:]:
            output.append(alpha * value + (1.0 - alpha) * output[-1])
        return output

    def rsi(self, values: List[float], period: int = 14) -> Optional[float]:
        if len(values) <= period:
            return None
        changes = [values[i] - values[i - 1] for i in range(1, len(values))]
        recent = changes[-period:]
        gains = sum(max(change, 0.0) for change in recent) / period
        losses = sum(max(-change, 0.0) for change in recent) / period
        if losses <= 1e-12:
            return 100.0
        rs = gains / losses
        return 100.0 - (100.0 / (1.0 + rs))

    def macd(self, values: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, Optional[float]]:
        if len(values) < slow:
            return {"macd": None, "signal": None, "histogram": None}
        fast_values = self.ema_series(values, fast)
        slow_values = self.ema_series(values, slow)
        macd_series = [a - b for a, b in zip(fast_values, slow_values)]
        signal_series = self.ema_series(macd_series, signal)
        return {
            "macd": macd_series[-1],
            "signal": signal_series[-1],
            "histogram": macd_series[-1] - signal_series[-1],
        }

    def bollinger(self, values: List[float], period: int = 20, deviations: float = 2.0) -> Dict[str, Optional[float]]:
        if len(values) < period:
            return {"middle": None, "upper": None, "lower": None, "position": None}
        sample = values[-period:]
        middle = sum(sample) / period
        variance = sum((value - middle) ** 2 for value in sample) / period
        std = math.sqrt(variance)
        upper = middle + deviations * std
        lower = middle - deviations * std
        position = (values[-1] - lower) / (upper - lower) if upper != lower else 0.5
        return {"middle": middle, "upper": upper, "lower": lower, "position": position}

    def analyze(self, closes: Iterable[Any], volumes: Iterable[Any] = ()) -> Dict[str, Any]:
        values = self._valid(closes)
        volume_values = self._valid(volumes)
        macd = self.macd(values)
        bollinger = self.bollinger(values)
        rsi = self.rsi(values)
        ma20 = self.sma(values, 20)
        ma50 = self.sma(values, 50)
        trend = "데이터 부족"
        if ma20 is not None and ma50 is not None:
            trend = "상승" if values[-1] > ma20 > ma50 else "하락" if values[-1] < ma20 < ma50 else "혼조"
        volume_ratio = None
        if len(volume_values) >= 20:
            average = sum(volume_values[-20:]) / 20.0
            volume_ratio = volume_values[-1] / average if average else None
        signals = {
            "rsi": "과매수" if rsi is not None and rsi >= 70 else "과매도" if rsi is not None and rsi <= 30 else "중립",
            "macd": "상승" if macd["histogram"] is not None and macd["histogram"] > 0 else "하락",
            "trend": trend,
        }
        unique = {value for value in signals.values() if value not in {"중립", "데이터 부족"}}
        return {
            "count": len(values),
            "price": values[-1] if values else None,
            "rsi14": rsi,
            "macd": macd,
            "bollinger": bollinger,
            "ma20": ma20,
            "ma50": ma50,
            "volume_ratio20": volume_ratio,
            "signals": signals,
            "conflict": len(unique) > 1,
            "quality_flags": [] if len(values) >= 50 else ["insufficient_long_window"],
        }

    def multi_timeframe(self, series_by_timeframe: Dict[str, Iterable[Any]]) -> Dict[str, Any]:
        analyses = {timeframe: self.analyze(values) for timeframe, values in series_by_timeframe.items()}
        trends = {str(result.get("signals", {}).get("trend")) for result in analyses.values()}
        meaningful = trends - {"데이터 부족", "혼조"}
        return {
            "timeframes": analyses,
            "conflict": len(meaningful) > 1,
            "summary": "시간대별 신호 충돌" if len(meaningful) > 1 else "시간대별 방향 정합",
        }
