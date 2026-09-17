"""Local, read-only chart evidence from the exact normalized replay inputs."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def build_replay_visualization(rows: list[dict[str, Any]], trades: list[dict[str, Any]],
                               equity: list[float], drawdown: list[float]) -> dict[str, Any]:
    base = {"schema_version": 1, "basis": "closed_trade_compounded_return",
            "time_basis": "candle_open_utc", "simulation_only": True}

    def unavailable(reason: str) -> dict[str, Any]:
        return {**base, "status": "unavailable", "reason": reason}

    # Never invent timestamps, silently truncate a run, or change the replay itself.
    if not rows or len(rows) > 5000:
        return unavailable("candle_count_out_of_bounds")
    candles = []
    previous = -1
    for row in rows:
        timestamp = row.get("timestamp")
        if not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp) or timestamp <= 0:
            return unavailable("candle_time_not_recorded")
        time = int(timestamp)
        if time <= previous:
            return unavailable("candle_time_not_strictly_increasing")
        prices = [row.get(key) for key in ("open", "high", "low", "close")]
        if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in prices):
            return unavailable("invalid_ohlc")
        op, high, low, close = prices
        if not low <= min(op, close) <= max(op, close) <= high:
            return unavailable("invalid_ohlc")
        candles.append({"time": time, "open": op, "high": high, "low": low, "close": close})
        previous = time
    if len(trades) != len(equity) or len(trades) != len(drawdown):
        return unavailable("trade_curve_mismatch")
    points = [{"time": candles[0]["time"], "value": 0.0, "drawdown": 0.0}]
    last_exit = -1
    for trade, value, dd in zip(trades, equity, drawdown):
        entry, exit_ = trade.get("entry_index"), trade.get("exit_index")
        if (not isinstance(entry, int) or not isinstance(exit_, int)
                or not last_exit < entry < exit_ < len(candles)
                or trade.get("side") not in {"LONG", "SHORT"}
                or not math.isfinite(value) or not math.isfinite(dd)):
            return unavailable("trade_candle_mismatch")
        points.append({"time": candles[exit_]["time"], "value": value, "drawdown": dd})
        last_exit = exit_
    if points[-1]["time"] != candles[-1]["time"]:
        points.append({**points[-1], "time": candles[-1]["time"]})
    digest = hashlib.sha256(json.dumps(candles, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()
    return {**base, "status": "available", "candles": candles, "equity": points,
            "candles_sha256": digest}
