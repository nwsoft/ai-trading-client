#!/usr/bin/env python3
"""승인된 AI 커스텀 규칙을 실제 과거 캔들에 재생하는 보조 검증기."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .custom_strategy_runtime import normalize_engine_settings
from .declarative_strategy_engine import DeclarativeStrategyEngine


def _float(value: Any) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except Exception:
        return 0.0


def _ema_series(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    output = [values[0]]
    for value in values[1:]:
        output.append((value * alpha) + (output[-1] * (1.0 - alpha)))
    return output


def _ema(values: List[float], period: int) -> Optional[float]:
    return _ema_series(values, period)[-1] if values else None


def _sma(values: List[float], period: int) -> Optional[float]:
    if period <= 0 or len(values) < period:
        return None
    return sum(values[-period:]) / period


def _rsi(values: List[float], period: int = 14) -> Optional[float]:
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    sample = changes[-period:]
    gains = sum(max(item, 0.0) for item in sample) / period
    losses = sum(max(-item, 0.0) for item in sample) / period
    if losses <= 1e-12:
        return 100.0 if gains > 0 else 50.0
    return 100.0 - (100.0 / (1.0 + gains / losses))


def _true_ranges(rows: List[Dict[str, Any]]) -> List[float]:
    output: List[float] = []
    for index, row in enumerate(rows):
        previous = rows[index - 1]["close"] if index else row["close"]
        output.append(max(
            row["high"] - row["low"],
            abs(row["high"] - previous),
            abs(row["low"] - previous),
        ))
    return output


def _atr(rows: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
    ranges = _true_ranges(rows)
    return _sma(ranges, period)


def _adx(rows: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
    """Wilder 방향성 개념을 단순 이동평균으로 재현한 결정적 ADX 근사."""
    if len(rows) <= period * 2:
        return None
    true_ranges = _true_ranges(rows)
    plus_dm: List[float] = [0.0]
    minus_dm: List[float] = [0.0]
    for index in range(1, len(rows)):
        up = rows[index]["high"] - rows[index - 1]["high"]
        down = rows[index - 1]["low"] - rows[index]["low"]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    dx_values: List[float] = []
    start = max(period, len(rows) - period)
    for end in range(start, len(rows) + 1):
        tr = sum(true_ranges[end - period:end])
        if tr <= 1e-12:
            dx_values.append(0.0)
            continue
        plus_di = 100.0 * sum(plus_dm[end - period:end]) / tr
        minus_di = 100.0 * sum(minus_dm[end - period:end]) / tr
        denominator = plus_di + minus_di
        dx_values.append(100.0 * abs(plus_di - minus_di) / denominator if denominator else 0.0)
    return sum(dx_values[-period:]) / min(len(dx_values), period) if dx_values else None


def _timestamp_value(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.timestamp()
    try:
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000.0
        return number if number > 0 else None
    except Exception:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except Exception:
            return None


def _iso_timestamp(timestamp: Optional[float]) -> Optional[str]:
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except Exception:
        return None


def _candle_rows(klines: Iterable[Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in klines or []:
        timestamp: Optional[float] = None
        if isinstance(item, dict):
            row = {key: _float(item.get(key)) for key in ("open", "high", "low", "close", "volume")}
            timestamp = _timestamp_value(
                item.get("timestamp", item.get("time", item.get("open_time", item.get("date"))))
            )
        elif isinstance(item, (list, tuple)) and len(item) >= 6:
            row = {
                "open": _float(item[1]), "high": _float(item[2]), "low": _float(item[3]),
                "close": _float(item[4]), "volume": _float(item[5]),
            }
            timestamp = _timestamp_value(item[0])
        elif isinstance(item, (int, float)):
            close = _float(item)
            row = {"open": close, "high": close, "low": close, "close": close, "volume": 0.0}
        else:
            continue
        if row["close"] > 0:
            row["timestamp"] = timestamp
            rows.append(row)
    return rows


def _required_history(rules: Dict[str, Any]) -> int:
    fields = set()
    periods = [30]
    for section in ("executable_entry", "executable_exit"):
        spec = dict((rules or {}).get(section, {}) or {})
        for group in ("all", "any"):
            for condition in spec.get(group) or []:
                if not isinstance(condition, dict):
                    continue
                for reference in (condition.get("field"), condition.get("value_field")):
                    if isinstance(reference, dict):
                        try:
                            periods.append(int(reference.get("period") or 0))
                        except Exception:
                            pass
                    else:
                        fields.add(str(reference or ""))
    if fields & {"ma200", "sma200", "ema200"}:
        periods.append(200)
    if fields & {"ma50", "sma50", "ema50"}:
        periods.append(50)
    return max(periods)


def _indicator_value(rows: List[Dict[str, Any]], reference: Dict[str, Any]) -> Optional[float]:
    name = str(reference.get("indicator") or reference.get("name") or "").lower()
    period = int(reference.get("period") or 0)
    source = str(
        reference.get("source") or ("volume" if name == "volume_sma" else "close")
    ).lower()
    values = [_float(row.get(source)) for row in rows]
    if name == "ema":
        return _ema(values, period) if len(values) >= period else None
    if name == "sma" or name == "volume_sma":
        return _sma(values, period)
    if name == "rsi":
        return _rsi(values, period)
    if name == "atr":
        return _atr(rows, period)
    return None


def collect_advanced_indicator_references(rules_or_pool: Any) -> List[Dict[str, Any]]:
    """Collect and de-duplicate safe parameterized indicator references."""
    rules_list: List[Dict[str, Any]] = []
    if isinstance(rules_or_pool, list):
        for item in rules_or_pool:
            if isinstance(item, dict):
                rules_list.append(dict(item.get("rules") or item))
    elif isinstance(rules_or_pool, dict):
        rules_list.append(rules_or_pool)

    output: Dict[str, Dict[str, Any]] = {}
    for rules in rules_list:
        for section in ("executable_entry", "executable_exit"):
            spec = dict(rules.get(section, {}) or {})
            for group in ("all", "any"):
                for condition in spec.get(group) or []:
                    if not isinstance(condition, dict):
                        continue
                    for reference in (condition.get("field"), condition.get("value_field")):
                        if not isinstance(reference, dict):
                            continue
                        valid, _reason = DeclarativeStrategyEngine.validate_indicator_reference(reference)
                        if valid:
                            output[DeclarativeStrategyEngine.indicator_field_key(reference)] = dict(reference)
    return list(output.values())


def enrich_advanced_indicator_context(
    context: Dict[str, Any],
    rules_or_pool: Any,
    candle_fetcher,
) -> Dict[str, Any]:
    """Fetch each requested timeframe once and add evaluated/previous values."""
    enriched = dict(context or {})
    previous = dict(enriched.get("_previous") or {})
    references = collect_advanced_indicator_references(rules_or_pool)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for reference in references:
        grouped.setdefault(str(reference.get("timeframe") or "5m").lower(), []).append(reference)

    compared: List[Dict[str, Any]] = []
    for timeframe, items in grouped.items():
        limit = min(600, max(int(item.get("period") or 0) for item in items) + 5)
        try:
            rows = _candle_rows(candle_fetcher(timeframe, limit) or [])
        except Exception:
            rows = []
        for reference in items:
            key = DeclarativeStrategyEngine.indicator_field_key(reference)
            runtime_value = _indicator_value(rows, reference) if rows else None
            previous_value = _indicator_value(rows[:-1], reference) if len(rows) > 1 else None
            enriched[key] = runtime_value
            previous[key] = previous_value
            compared.append({
                "field": key,
                "requested": dict(reference),
                "runtime_value": runtime_value,
                "status": "calculated" if runtime_value is not None else "insufficient_data",
            })
    if previous:
        enriched["_previous"] = previous
    enriched["_advanced_indicator_values"] = compared
    return enriched


def _enrich_replay_context(
    context: Dict[str, Any],
    rules: Dict[str, Any],
    rows: List[Dict[str, Any]],
    *,
    timeframe_rows: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    cutoff_timestamp: Optional[float] = None,
) -> Dict[str, Any]:
    def _fetch(timeframe: str, limit: int):
        source_rows = rows
        if timeframe_rows is not None:
            source_rows = timeframe_rows.get(timeframe, [])
        if cutoff_timestamp is not None:
            source_rows = [
                row for row in source_rows
                if row.get("timestamp") is not None
                and float(row["timestamp"]) <= cutoff_timestamp
            ]
        return source_rows[-limit:]

    return enrich_advanced_indicator_context(
        context,
        rules,
        _fetch,
    )


def _context(
    rows: List[Dict[str, Any]],
    index: int,
    signal: str,
    *,
    include_previous: bool = True,
) -> Dict[str, Any]:
    history = rows[:index + 1]
    closes = [item["close"] for item in history]
    volumes = [item["volume"] for item in history]
    current_row = history[-1]
    current = current_row["close"]
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200) if len(closes) >= 200 else None
    mean20 = sma20 or current
    sample20 = closes[-20:]
    variance = sum((value - mean20) ** 2 for value in sample20) / max(len(sample20), 1)
    std20 = math.sqrt(max(variance, 0.0))
    macd_values = [
        fast - slow
        for fast, slow in zip(_ema_series(closes, 12), _ema_series(closes, 26))
    ]
    macd = macd_values[-1] if len(closes) >= 26 else None
    macd_signal = _ema(macd_values, 9) if len(closes) >= 26 else None
    atr = _atr(history)
    volume_sma20 = _sma(volumes, 20)
    timestamp = current_row.get("timestamp")
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc) if timestamp else None
    context = {
        "signal": signal,
        "confidence": min(
            1.0,
            0.5 + abs((sma20 or current) - (sma50 or current)) / max(current, 1e-9) * 20.0,
        ),
        "open": current_row["open"],
        "high": current_row["high"],
        "low": current_row["low"],
        "close": current,
        "current_price": current,
        "price": current,
        "rsi": _rsi(closes),
        "macd": macd,
        "macd_signal": macd_signal,
        "macd_histogram": (
            macd - macd_signal if macd is not None and macd_signal is not None else None
        ),
        "bb_position": (
            (current - (mean20 - 2 * std20)) / max(4 * std20, 1e-9)
        ),
        "bb_width": 4 * std20 / max(mean20, 1e-9),
        "ma20": sma20,
        "ma50": sma50,
        "ma200": sma200,
        "sma20": sma20,
        "sma50": sma50,
        "sma200": sma200,
        "ema20": ema20,
        "ema50": ema50,
        "ema200": ema200,
        "adx": _adx(history),
        "atr": atr,
        "atr_percent": atr / max(current, 1e-9) * 100.0 if atr is not None else None,
        "trend_strength": abs((ema20 or current) - (ema50 or current)) / max(current, 1e-9),
        "market_volatility": std20 / max(mean20, 1e-9),
        "volume": current_row["volume"],
        "volume_sma20": volume_sma20,
        "volume_ratio": (
            current_row["volume"] / max(volume_sma20, 1e-9) if volume_sma20 is not None else None
        ),
        "hour": dt.hour if dt else None,
        "weekday": dt.weekday() if dt else None,
    }
    if include_previous and index > 0:
        context["_previous"] = _context(
            rows, index - 1, signal, include_previous=False
        )
    return context


def _regime(context: Dict[str, Any]) -> str:
    price = _float(context.get("current_price"))
    ma50 = context.get("ma50")
    ma200 = context.get("ma200")
    volatility = _float(context.get("market_volatility"))
    if volatility >= 0.025:
        return "volatile"
    if ma50 is not None and ma200 is not None:
        if price > float(ma50) > float(ma200):
            return "bull"
        if price < float(ma50) < float(ma200):
            return "bear"
    return "range"


def _profit_factor(outcomes: List[float]) -> float:
    gross_profit = sum(item for item in outcomes if item > 0)
    gross_loss = abs(sum(item for item in outcomes if item < 0))
    if gross_loss <= 1e-12:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def build_indicator_context(klines: Iterable[Any], *, signal: str = "HOLD") -> Dict[str, Any]:
    """실시간 분석 경로가 과거검증과 같은 커스텀 지표 정의를 재사용한다."""
    rows = _candle_rows(klines)
    if not rows:
        return {}
    return _context(rows, len(rows) - 1, str(signal or "HOLD").upper())


def run_historical_replay(
    rules: Dict[str, Any],
    klines: Iterable[Any],
    *,
    timeframe_klines: Optional[Dict[str, Iterable[Any]]] = None,
    fee_rate: float = 0.001,
    slippage_bps: float = 2.0,
    spread_bps: float = 1.0,
    horizon: int = 12,
) -> Dict[str, Any]:
    """단일 포지션 방식의 조건 재생. 실전 수익 보장이 아닌 실행 가능성 보조 검증이다."""
    rows = _candle_rows(klines)
    replay_timeframes: Dict[str, List[Dict[str, Any]]] = {
        str(timeframe).lower(): _candle_rows(values)
        for timeframe, values in (timeframe_klines or {}).items()
    }
    if "15m" not in replay_timeframes:
        replay_timeframes["15m"] = rows
    requested_timeframes = {
        str(item.get("timeframe") or "5m").lower()
        for item in collect_advanced_indicator_references(rules)
    }
    missing_timeframes = sorted(requested_timeframes - set(replay_timeframes))
    if missing_timeframes:
        raise ValueError(
            "다중 시간봉 과거 데이터가 필요합니다: " + ", ".join(missing_timeframes)
        )
    spec = dict((rules or {}).get("executable_entry", {}) or {})
    validation = DeclarativeStrategyEngine.validate_rule_spec(rules)
    if not validation["valid"]:
        raise ValueError("미지원 선언형 조건: " + ", ".join(validation["errors"]))
    if len(rows) < 80:
        raise ValueError("과거 재생에는 최소 80개 캔들이 필요합니다.")
    if not (spec.get("all") or spec.get("any")):
        raise ValueError("실행 가능한 진입 조건이 없어 과거 재생할 수 없습니다.")
    warmup = _required_history(rules)
    if len(rows) <= warmup + max(1, horizon):
        raise ValueError(f"이 전략 지표에는 최소 {warmup + max(1, horizon) + 1}개 캔들이 필요합니다.")

    settings = normalize_engine_settings((rules or {}).get("engine_settings", {}))
    tp = float(settings.get("tp_percent", 0.02) or 0.02)
    sl = float(settings.get("sl_percent", 0.01) or 0.01)
    signal_mode = str((rules or {}).get("signal_mode", "confirm") or "confirm").lower()
    configured_signal = str((rules or {}).get("entry_signal", "") or "").upper()
    fee_per_side = max(0.0, float(fee_rate))
    slippage_per_side = max(0.0, float(slippage_bps)) / 10_000.0
    spread_round_trip = max(0.0, float(spread_bps)) / 10_000.0
    round_trip_cost = 2 * fee_per_side + 2 * slippage_per_side + spread_round_trip
    outcomes: List[float] = []
    gross_outcomes: List[float] = []
    trades: List[Dict[str, Any]] = []
    evaluated = 0
    next_available = warmup
    last_entry_index = len(rows) - max(1, horizon) - 1

    for index in range(warmup - 1, last_entry_index + 1):
        if index < next_available:
            continue
        base_context = _context(rows, index, "HOLD")
        ma20 = base_context.get("ma20") or rows[index]["close"]
        ma50 = base_context.get("ma50") or rows[index]["close"]
        proxy_signal = "LONG" if ma20 >= ma50 else "SHORT"
        entry_signal = configured_signal if signal_mode == "independent" else proxy_signal
        current_context = _enrich_replay_context(
            _context(rows, index, entry_signal),
            rules,
            rows[:index + 1],
            timeframe_rows=replay_timeframes,
            cutoff_timestamp=rows[index].get("timestamp"),
        )
        evaluated += 1
        if not DeclarativeStrategyEngine.evaluate_entry(rules, current_context).get("allowed", False):
            continue

        entry_price = rows[index]["close"]
        exit_index = min(index + max(1, horizon), len(rows) - 1)
        exit_price = rows[exit_index]["close"]
        exit_reason = "horizon"
        for future_index in range(index + 1, exit_index + 1):
            candle = rows[future_index]
            if entry_signal == "LONG":
                if candle["low"] <= entry_price * (1.0 - sl):
                    exit_price = entry_price * (1.0 - sl)
                    exit_reason = "stop_loss"
                    exit_index = future_index
                    break
                if candle["high"] >= entry_price * (1.0 + tp):
                    exit_price = entry_price * (1.0 + tp)
                    exit_reason = "take_profit"
                    exit_index = future_index
                    break
            else:
                if candle["high"] >= entry_price * (1.0 + sl):
                    exit_price = entry_price * (1.0 + sl)
                    exit_reason = "stop_loss"
                    exit_index = future_index
                    break
                if candle["low"] <= entry_price * (1.0 - tp):
                    exit_price = entry_price * (1.0 - tp)
                    exit_reason = "take_profit"
                    exit_index = future_index
                    break
            explicit_exit = DeclarativeStrategyEngine.evaluate_exit(
                rules,
                _enrich_replay_context(
                    _context(rows, future_index, entry_signal),
                    rules,
                    rows[:future_index + 1],
                    timeframe_rows=replay_timeframes,
                    cutoff_timestamp=rows[future_index].get("timestamp"),
                ),
            )
            if not explicit_exit.get("bypassed", False) and explicit_exit.get("allowed", False):
                exit_price = candle["close"]
                exit_reason = "declarative_exit"
                exit_index = future_index
                break

        gross = (exit_price / entry_price - 1.0) * (1.0 if entry_signal == "LONG" else -1.0)
        net = gross - round_trip_cost
        gross_outcomes.append(gross)
        outcomes.append(net)
        regime = _regime(current_context)
        trades.append({
            "entry_index": index,
            "exit_index": exit_index,
            "entry_time": _iso_timestamp(rows[index].get("timestamp")),
            "exit_time": _iso_timestamp(rows[exit_index].get("timestamp")),
            "side": entry_signal,
            "regime": regime,
            "entry_price": round(entry_price, 10),
            "exit_price": round(exit_price, 10),
            "exit_reason": exit_reason,
            "gross_pnl_percent": round(gross * 100.0, 6),
            "cost_percent": round(round_trip_cost * 100.0, 6),
            "net_pnl_percent": round(net * 100.0, 6),
        })
        next_available = exit_index + 1

    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    equity_curve: List[float] = []
    drawdown_curve: List[float] = []
    for outcome in outcomes:
        equity *= max(1e-9, 1.0 + outcome)
        peak = max(peak, equity)
        drawdown = (peak - equity) / max(peak, 1e-9)
        max_drawdown = max(max_drawdown, drawdown)
        equity_curve.append(round((equity - 1.0) * 100.0, 6))
        drawdown_curve.append(round(drawdown * 100.0, 6))
    wins = sum(1 for item in outcomes if item > 0)
    regime_results: Dict[str, Dict[str, Any]] = {}
    for regime in ("bull", "bear", "range", "volatile"):
        selected = [trade for trade in trades if trade["regime"] == regime]
        if selected:
            regime_results[regime] = {
                "decisions": len(selected),
                "win_rate": round(
                    sum(1 for trade in selected if trade["net_pnl_percent"] > 0) / len(selected), 6
                ),
                "net_pnl_percent": round(sum(trade["net_pnl_percent"] for trade in selected), 6),
            }
    profit_factor = _profit_factor(outcomes)
    return {
        "evidence_source": "exchange_candles",
        "candles": len(rows),
        "warmup_candles": warmup,
        "evaluated_windows": evaluated,
        "decisions": len(outcomes),
        "wins": wins,
        "losses": len(outcomes) - wins,
        "win_rate": round(wins / max(len(outcomes), 1), 6),
        "gross_pnl_percent": round(sum(gross_outcomes) * 100.0, 6),
        "net_pnl_percent": round((equity - 1.0) * 100.0, 6),
        "total_cost_percent": round(round_trip_cost * len(outcomes) * 100.0, 6),
        "max_drawdown_percent": round(max_drawdown * 100.0, 6),
        "profit_factor": "inf" if math.isinf(profit_factor) else round(profit_factor, 6),
        "expectancy_percent": round(
            sum(outcomes) / max(len(outcomes), 1) * 100.0, 6
        ),
        "fee_rate_percent_per_side": round(fee_per_side * 100.0, 6),
        "fee_rate_percent": round(fee_per_side * 100.0, 6),
        "slippage_bps_per_side": round(float(slippage_bps), 6),
        "spread_bps_round_trip": round(float(spread_bps), 6),
        "round_trip_cost_percent": round(round_trip_cost * 100.0, 6),
        "tp_percent": round(tp * 100.0, 6),
        "sl_percent": round(sl * 100.0, 6),
        "signal_mode": signal_mode,
        "equity_curve_percent": equity_curve,
        "drawdown_curve_percent": drawdown_curve,
        "regime_results": regime_results,
        "trades": trades,
        "assumptions": {
            "position_model": "single_non_overlapping",
            "same_bar_tp_sl_order": "stop_loss_first",
            "fee": "per_side",
            "slippage": "per_side",
            "spread": "round_trip",
            "funding": "not_modeled",
        },
        "note": "과거 재생은 보조 검증이며 실제 체결·펀딩비·시장충격·유동성 성과를 보장하지 않습니다.",
    }
