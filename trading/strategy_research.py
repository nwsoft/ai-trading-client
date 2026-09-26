"""Read-only sensitivity of a fixed historical trade sample, not a new replay."""
from __future__ import annotations

import math
from typing import Any


def replay_cost_sensitivity(metrics: dict[str, Any]) -> dict[str, Any]:
    trades = metrics.get("trades")
    result = {"kind": "fixed_trade_cost_sensitivity", "status": "unavailable",
              "trades": 0, "scenarios": [], "execution_permission": False}
    if not isinstance(trades, list) or not trades:
        result["reason"] = "no_trade_evidence"
        return result
    if len(trades) > 100000:
        result["reason"] = "sample_limit_exceeded"
        return result
    values = []
    for trade in trades:
        if not isinstance(trade, dict):
            result["reason"] = "trade_cost_evidence_missing"
            return result
        pair = [trade.get("gross_pnl_percent"), trade.get("cost_percent")]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in pair) or pair[1] < 0:
            result["reason"] = "trade_cost_evidence_missing"
            return result
        values.append(pair)
    scenarios = []
    for multiplier in (1.0, 1.5, 2.0):
        equity = peak = 1.0
        drawdown = 0.0
        for gross, cost in values:
            equity *= max(1e-9, 1 + (gross - multiplier * cost) / 100)
            peak = max(peak, equity)
            drawdown = max(drawdown, (peak - equity) / peak * 100)
        if not math.isfinite(equity):
            result["reason"] = "non_finite_result"
            return result
        scenarios.append({"cost_multiplier": multiplier, "net_return_percent": round((equity - 1) * 100, 6),
                          "max_drawdown_percent": round(drawdown, 6)})
    result.update(status="completed", trades=len(values), scenarios=scenarios,
                  reason="same_entries_exits_no_liquidity_or_funding_resimulation")
    return result
