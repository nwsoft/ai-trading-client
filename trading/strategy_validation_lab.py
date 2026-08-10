"""비용·워크포워드·민감도·과최적화·PAPER 전진검증 정본."""

from __future__ import annotations

import random
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Sequence


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _net_returns(trades: Sequence[Mapping[str, Any]], *, cost_multiplier: float = 1.0) -> List[float]:
    return [
        _number(row.get("pnl", row.get("realized_pnl")))
        - cost_multiplier * (_number(row.get("fee")) + _number(row.get("slippage")))
        for row in trades
    ]


def _timestamp(row: Mapping[str, Any]) -> datetime | None:
    raw = next((row.get(key) for key in (
        "exit_time", "closed_at", "timestamp", "time", "date", "entry_time"
    ) if row.get(key) not in (None, "")), None)
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.astimezone(timezone.utc) if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        value = float(raw)
        if value > 10_000_000_000:
            value /= 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None


def _trade_return_fraction(row: Mapping[str, Any], initial_capital: float) -> float:
    if row.get("return_percent") is not None:
        return _number(row.get("return_percent")) / 100.0
    if row.get("net_pnl_percent") is not None:
        return _number(row.get("net_pnl_percent")) / 100.0
    return (
        _number(row.get("pnl", row.get("realized_pnl")))
        - _number(row.get("fee")) - _number(row.get("slippage"))
    ) / max(initial_capital, 1e-9)


def _performance_summary(
    rows: Sequence[Mapping[str, Any]], initial_capital: float
) -> Dict[str, Any]:
    equity = peak = float(initial_capital)
    max_drawdown = 0.0
    max_drawdown_percent = 0.0
    outcomes: List[float] = []
    period_rows: Dict[str, Dict[str, List[float]]] = {"monthly": {}, "yearly": {}}
    for row in rows:
        trade_return = _trade_return_fraction(row, initial_capital)
        before = equity
        pnl = before * trade_return
        equity = max(0.0, before + pnl)
        outcomes.append(pnl)
        peak = max(peak, equity)
        drawdown = peak - equity
        drawdown_percent = drawdown / max(peak, 1e-9) * 100.0
        max_drawdown = max(max_drawdown, drawdown)
        max_drawdown_percent = max(max_drawdown_percent, drawdown_percent)
        timestamp = _timestamp(row)
        if timestamp:
            for bucket, key in (("monthly", timestamp.strftime("%Y-%m")), ("yearly", timestamp.strftime("%Y"))):
                period_rows[bucket].setdefault(key, []).append(trade_return)

    def period_table(bucket: str) -> List[Dict[str, Any]]:
        table = []
        for period, values in sorted(period_rows[bucket].items()):
            factor = 1.0
            for value in values:
                factor *= max(0.0, 1.0 + value)
            period_return = factor - 1.0
            table.append({
                "period": period,
                "return_percent": round(period_return * 100.0, 6),
                "net_pnl": round(initial_capital * period_return, 6),
                "trades": len(values),
            })
        return table

    wins = [value for value in outcomes if value > 0]
    losses = [value for value in outcomes if value < 0]
    profit_factor = sum(wins) / abs(sum(losses)) if losses else ("inf" if wins else 0.0)
    return {
        "initial_capital": round(initial_capital, 6),
        "final_equity": round(equity, 6),
        "total_net_pnl": round(equity - initial_capital, 6),
        "total_return_percent": round((equity / max(initial_capital, 1e-9) - 1.0) * 100.0, 6),
        "max_drawdown": round(max_drawdown, 6),
        "max_drawdown_percent": round(max_drawdown_percent, 6),
        "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / max(len(outcomes), 1), 6),
        "profit_factor": profit_factor if isinstance(profit_factor, str) else round(profit_factor, 6),
        "monthly_returns": period_table("monthly"),
        "yearly_returns": period_table("yearly"),
    }


def run_validation_lab(
    trades: Sequence[Mapping[str, Any]],
    *,
    parameter_variants: Sequence[Mapping[str, Any]] | None = None,
    paper_trades: Sequence[Mapping[str, Any]] | None = None,
    seed: int = 3906,
    initial_capital: float = 10_000.0,
    minimum_trades: int = 3,
    maximum_mdd_percent: float = 90.0,
) -> Dict[str, Any]:
    rows = [dict(row) for row in trades]
    initial_capital = max(1.0, _number(initial_capital))
    returns = _net_returns(rows)
    performance = _performance_summary(rows, initial_capital)
    split = max(1, int(len(returns) * 0.6)) if returns else 0
    train = returns[:split]
    out_of_sample = returns[split:]
    window = max(1, len(returns) // 4) if returns else 1
    walkforward_windows = []
    for start in range(split, len(returns), window):
        test = returns[start:start + window]
        if test:
            walkforward_windows.append({
                "start": start,
                "trades": len(test),
                "net_pnl": round(sum(test), 6),
                "passed": statistics.mean(test) > 0,
            })
    wf_rate = (
        sum(1 for item in walkforward_windows if item["passed"]) / len(walkforward_windows)
        if walkforward_windows else 0.0
    )
    cost_sensitivity = {
        label: round(sum(_net_returns(rows, cost_multiplier=multiple)), 6)
        for label, multiple in (("base", 1.0), ("cost_1_5x", 1.5), ("cost_2x", 2.0))
    }
    variants = [dict(item) for item in (parameter_variants or [])]
    variant_scores = [_number(item.get("net_pnl")) for item in variants]
    sensitivity_spread = (
        max(variant_scores) - min(variant_scores) if len(variant_scores) >= 2 else 0.0
    )
    rng = random.Random(seed)
    monte_carlo = []
    for _ in range(100 if returns else 0):
        sample = list(returns)
        rng.shuffle(sample)
        running = peak = 0.0
        max_drawdown = 0.0
        for value in sample:
            running += value
            peak = max(peak, running)
            max_drawdown = max(max_drawdown, peak - running)
        monte_carlo.append(max_drawdown)
    paper_returns = _net_returns([dict(item) for item in (paper_trades or [])])
    paper_passed = len(paper_returns) >= 3 and sum(paper_returns) > 0
    train_mean = statistics.mean(train) if train else 0.0
    test_mean = statistics.mean(out_of_sample) if out_of_sample else 0.0
    overfit_flags = []
    if train_mean > 0 and test_mean <= 0:
        overfit_flags.append("out_of_sample_degradation")
    if sensitivity_spread > max(1.0, abs(sum(returns)) * 2.0):
        overfit_flags.append("parameter_sensitivity_high")
    if cost_sensitivity["base"] > 0 >= cost_sensitivity["cost_2x"]:
        overfit_flags.append("cost_fragile")
    minimum_gate_reasons = []
    if len(rows) < max(1, int(minimum_trades)):
        minimum_gate_reasons.append("sample_too_small")
    if performance["total_net_pnl"] <= 0:
        minimum_gate_reasons.append("non_positive_total_pnl")
    if performance["max_drawdown_percent"] > float(maximum_mdd_percent):
        minimum_gate_reasons.append("max_drawdown_excessive")
    return {
        "schema_version": 2,
        "purpose": "minimum_quality_filter_not_future_prediction",
        "sample": {"total": len(returns), "train": len(train), "out_of_sample": len(out_of_sample)},
        "performance": performance,
        "train_net_pnl": round(sum(train), 6),
        "out_of_sample_net_pnl": round(sum(out_of_sample), 6),
        "walkforward": {"windows": walkforward_windows, "pass_rate": round(wf_rate, 4)},
        "cost_sensitivity": cost_sensitivity,
        "parameter_sensitivity": {"variants": len(variants), "score_spread": round(sensitivity_spread, 6)},
        "monte_carlo": {
            "runs": len(monte_carlo),
            "median_max_drawdown": round(statistics.median(monte_carlo), 6) if monte_carlo else 0.0,
            "worst_max_drawdown": round(max(monte_carlo), 6) if monte_carlo else 0.0,
        },
        "paper_forward": {"trades": len(paper_returns), "net_pnl": round(sum(paper_returns), 6), "passed": paper_passed},
        "overfit_risk": {"flagged": bool(overfit_flags), "reasons": overfit_flags},
        "minimum_quality_gate": {
            "passed": not minimum_gate_reasons,
            "reasons": minimum_gate_reasons,
            "criteria": {
                "minimum_trades": max(1, int(minimum_trades)),
                "total_net_pnl_must_be_positive": True,
                "maximum_mdd_percent": float(maximum_mdd_percent),
            },
        },
        "promotion_ready": bool(
            len(out_of_sample) >= 3 and wf_rate >= 0.5 and not overfit_flags
            and not minimum_gate_reasons and paper_passed
        ),
        "paper_required": True,
        "backtest_can_auto_promote": False,
        "auto_promoted": False,
    }
