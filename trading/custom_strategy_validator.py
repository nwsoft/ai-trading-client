#!/usr/bin/env python3
"""승인된 AI 커스텀 규칙을 실제 과거 캔들에 재생하는 보조 검증기."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List

from .custom_strategy_runtime import normalize_engine_settings
from .declarative_strategy_engine import DeclarativeStrategyEngine


def _float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _ema(values: List[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    result = values[0]
    for value in values[1:]:
        result = (value * alpha) + (result * (1.0 - alpha))
    return result


def _rsi(values: List[float], period: int = 14) -> float:
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    sample = changes[-period:]
    gains = sum(max(item, 0.0) for item in sample) / max(len(sample), 1)
    losses = sum(max(-item, 0.0) for item in sample) / max(len(sample), 1)
    if losses <= 0:
        return 100.0 if gains > 0 else 50.0
    return 100.0 - (100.0 / (1.0 + gains / losses))


def _candle_rows(klines: Iterable[Any]) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []
    for item in klines or []:
        if isinstance(item, dict):
            row = {key: _float(item.get(key)) for key in ("open", "high", "low", "close", "volume")}
        elif isinstance(item, (list, tuple)) and len(item) >= 6:
            row = {
                "open": _float(item[1]), "high": _float(item[2]), "low": _float(item[3]),
                "close": _float(item[4]), "volume": _float(item[5]),
            }
        elif isinstance(item, (int, float)):
            close = _float(item)
            row = {"open": close, "high": close, "low": close, "close": close, "volume": 0.0}
        else:
            continue
        if row["close"] > 0:
            rows.append(row)
    return rows


def run_historical_replay(
    rules: Dict[str, Any],
    klines: Iterable[Any],
    *,
    fee_rate: float = 0.001,
    horizon: int = 12,
) -> Dict[str, Any]:
    """15분봉 기반 조건 재생. 백테스트 수익 보증이 아니라 실행 가능성 보조 검증이다."""
    rows = _candle_rows(klines)
    spec = dict((rules or {}).get("executable_entry", {}) or {})
    if len(rows) < 80:
        raise ValueError("과거 재생에는 최소 80개 캔들이 필요합니다.")
    if not (spec.get("all") or spec.get("any")):
        raise ValueError("실행 가능한 진입 조건이 없어 과거 재생할 수 없습니다.")

    settings = normalize_engine_settings((rules or {}).get("engine_settings", {}))
    tp = float(settings.get("tp_percent", 0.02) or 0.02)
    sl = float(settings.get("sl_percent", 0.01) or 0.01)
    signal_mode = str((rules or {}).get("signal_mode", "confirm") or "confirm").lower()
    configured_signal = str((rules or {}).get("entry_signal", "") or "").upper()
    outcomes: List[float] = []
    evaluated = 0

    for index in range(50, len(rows) - max(1, horizon)):
        history = rows[: index + 1]
        closes = [item["close"] for item in history]
        volumes = [item["volume"] for item in history]
        current = closes[-1]
        ma20 = sum(closes[-20:]) / 20.0
        ma50 = sum(closes[-50:]) / 50.0
        mean20 = ma20
        variance = sum((value - mean20) ** 2 for value in closes[-20:]) / 20.0
        std20 = math.sqrt(max(variance, 0.0))
        proxy_signal = "LONG" if ma20 >= ma50 else "SHORT"
        entry_signal = configured_signal if signal_mode == "independent" else proxy_signal
        context = {
            "signal": entry_signal,
            "confidence": min(1.0, 0.5 + abs(ma20 - ma50) / max(current, 1e-9) * 20.0),
            "rsi": _rsi(closes),
            "macd": _ema(closes[-60:], 12) - _ema(closes[-60:], 26),
            "bb_position": (current - (mean20 - 2 * std20)) / max(4 * std20, 1e-9),
            "ma20": ma20,
            "ma50": ma50,
            "current_price": current,
            "price": current,
            "trend_strength": abs(ma20 - ma50) / max(current, 1e-9),
            "market_volatility": std20 / max(mean20, 1e-9),
            "volume_ratio": volumes[-1] / max(sum(volumes[-20:]) / 20.0, 1e-9),
        }
        evaluated += 1
        if not DeclarativeStrategyEngine.evaluate_entry(rules, context).get("allowed", False):
            continue
        future = rows[index + 1: index + 1 + horizon]
        pnl = None
        for candle in future:
            if entry_signal == "LONG":
                if candle["low"] <= current * (1.0 - sl):
                    pnl = -sl
                    break
                if candle["high"] >= current * (1.0 + tp):
                    pnl = tp
                    break
            else:
                if candle["high"] >= current * (1.0 + sl):
                    pnl = -sl
                    break
                if candle["low"] <= current * (1.0 - tp):
                    pnl = tp
                    break
        if pnl is None:
            exit_price = future[-1]["close"]
            pnl = (exit_price / current - 1.0) * (1.0 if entry_signal == "LONG" else -1.0)
        outcomes.append(float(pnl) - max(0.0, float(fee_rate)))

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for outcome in outcomes:
        equity += outcome
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    wins = sum(1 for item in outcomes if item > 0)
    return {
        "evidence_source": "exchange_15m_candles",
        "candles": len(rows),
        "evaluated_windows": evaluated,
        "decisions": len(outcomes),
        "wins": wins,
        "losses": len(outcomes) - wins,
        "win_rate": round(wins / max(len(outcomes), 1), 6),
        "net_pnl_percent": round(sum(outcomes) * 100.0, 6),
        "max_drawdown_percent": round(max_drawdown * 100.0, 6),
        "fee_rate_percent": round(float(fee_rate) * 100.0, 6),
        "tp_percent": round(tp * 100.0, 6),
        "sl_percent": round(sl * 100.0, 6),
        "signal_mode": signal_mode,
        "note": "과거 재생은 보조 검증이며 실제 체결·슬리피지·유동성 성과를 보장하지 않습니다.",
    }
