#!/usr/bin/env python3
"""Deterministic, auditable TP/SL and runtime-exit policy shared by crypto engines.

The policy is intentionally not an LLM macro.  It combines verified closed
trades and current market/risk inputs.  AI Custom values are immutable strategy
declarations; a guardrail may reject an unsafe entry but never rewrites them.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _fraction(value: Any, default: float) -> float:
    result = abs(_float(value, default))
    return result / 100.0 if result > 1.0 else result


def _trade_returns(trades: Iterable[Mapping[str, Any]] | None) -> list[float]:
    output: list[float] = []
    for row in trades or []:
        raw = row.get("pnl_percent")
        if raw is None:
            continue
        value = _float(raw)
        # recorder stores pnl_percent as percentage points (0.63 == 0.63%).
        output.append(value / 100.0)
    return output


def resolve_smart_exit_policy(
    *,
    baseline_tp: Any,
    baseline_sl: Any,
    closed_trades: Iterable[Mapping[str, Any]] | None = None,
    fallback_closed_trades: Iterable[Mapping[str, Any]] | None = None,
    volatility: Any = 0.0,
    atr_fraction: Any = 0.0,
    market_regime: str = "NORMAL",
    fee_rate: Any = 0.0004,
    slippage_rate: Any = 0.0002,
    minimum_rr: Any = 1.0,
    minimum_samples: int = 10,
    strategy_owned: bool = False,
    strategy_source: str = "",
) -> dict[str, Any]:
    """Resolve one fraction-unit entry policy and its complete XAI trace."""
    tp0 = min(0.05, max(0.0005, _fraction(baseline_tp, 0.0018)))
    sl0 = min(0.03, max(0.0005, _fraction(baseline_sl, 0.0020)))
    rr_min = min(5.0, max(0.25, _float(minimum_rr, 1.0)))
    costs = max(0.0, _float(fee_rate)) + max(0.0, _float(slippage_rate))
    samples = _trade_returns(closed_trades)
    fallback_samples = _trade_returns(fallback_closed_trades)
    min_samples = max(1, int(minimum_samples))
    use_fallback = len(samples) < min_samples and len(fallback_samples) >= min_samples * 2
    statistical_samples = samples if not use_fallback else fallback_samples
    wins = [value for value in statistical_samples if value > 0]
    losses = [abs(value) for value in statistical_samples if value < 0]
    trace: dict[str, Any] = {
        "schema_version": 1,
        "unit": "fraction",
        "baseline": {"tp": tp0, "sl": sl0},
        "sample_scope": {
            "closed_count": len(samples),
            "minimum_required": min_samples,
            "sufficient": len(samples) >= min_samples,
            "fallback_closed_count": len(fallback_samples),
            "statistical_source": "exchange_pool" if use_fallback else "exchange_symbol",
        },
        "costs": {"fee_rate": max(0.0, _float(fee_rate)), "slippage_rate": max(0.0, _float(slippage_rate))},
        "market": {"volatility": _fraction(volatility, 0.0), "atr_fraction": _fraction(atr_fraction, 0.0), "regime": str(market_regime or "NORMAL").upper()},
        "strategy_owned": bool(strategy_owned),
        "strategy_source": str(strategy_source or ""),
    }

    if strategy_owned:
        rr = tp0 / sl0 if sl0 else 0.0
        trace.update({
            "statistical": {"applied": False, "reason": "ai_custom_immutable"},
            "volatility_adjustment": {"applied": False, "reason": "ai_custom_immutable"},
            "rr_guardrail": {"before": rr, "after": rr, "minimum": rr_min, "applied": False},
            "entry_allowed": rr >= rr_min,
            "rejection_reason": "" if rr >= rr_min else "ai_custom_rr_below_minimum",
            "final": {"tp": tp0, "sl": sl0, "source": "ai_custom_declared"},
        })
        return trace

    tp = tp0
    sl = sl0
    statistical_applied = (
        (len(samples) >= min_samples or use_fallback) and bool(wins)
    )
    if statistical_applied:
        learned_tp = min(0.05, max(0.0005, (sum(wins) / len(wins)) * 1.05))
        tp = (tp0 * 0.70 + learned_tp * 0.30) if use_fallback else learned_tp
        if losses:
            learned_sl = max(0.0005, (sum(losses) / len(losses)) * 1.05)
            sl = min(sl0, (sl0 * 0.70 + learned_sl * 0.30) if use_fallback else learned_sl)
    trace["statistical"] = {
        "applied": statistical_applied,
        "average_win": (sum(wins) / len(wins)) if wins else None,
        "average_loss": (sum(losses) / len(losses)) if losses else None,
        "tp": tp,
        "sl": sl,
        "source": "exchange_pool_shrunk" if use_fallback else "exchange_symbol",
    }

    vol = _fraction(volatility, 0.0)
    atr = _fraction(atr_fraction, 0.0)
    regime = str(market_regime or "NORMAL").upper()
    volatility_floor = max(vol, atr)
    regime_tp = {"HIGH": 1.20, "LOW": 0.90}.get(regime, 1.0)
    regime_sl = {"HIGH": 1.10, "LOW": 0.85}.get(regime, 1.0)
    before_volatility = (tp, sl)
    if volatility_floor > 0:
        tp = max(tp * regime_tp, volatility_floor * 0.75)
        # SL can be wider than the statistical candidate for observed noise,
        # but is capped by the original configured risk and absolute limit.
        sl = min(sl0, max(sl * regime_sl, volatility_floor * 0.50))
    else:
        tp *= regime_tp
        sl = min(sl0, sl * regime_sl)
    tp = min(0.05, max(0.0005, tp, costs * 1.25))
    sl = min(0.03, max(0.0005, sl))
    trace["volatility_adjustment"] = {
        "applied": before_volatility != (tp, sl),
        "before": {"tp": before_volatility[0], "sl": before_volatility[1]},
        "after": {"tp": tp, "sl": sl},
        "cost_floor": costs * 1.25,
    }

    rr_before = tp / sl if sl else 0.0
    rr_applied = rr_before < rr_min
    if rr_applied:
        # Tighten risk first.  Never widen SL to make an RR number look valid.
        sl = max(0.0005, min(sl, tp / rr_min))
        if tp / sl < rr_min:
            tp = min(0.05, max(tp, sl * rr_min))
    rr_after = tp / sl if sl else 0.0
    trace.update({
        "rr_guardrail": {"before": rr_before, "after": rr_after, "minimum": rr_min, "applied": rr_applied},
        "entry_allowed": rr_after >= rr_min,
        "rejection_reason": "" if rr_after >= rr_min else "rr_guardrail_unresolved",
        "final": {"tp": tp, "sl": sl, "source": "smart_exit_policy"},
    })
    return trace


def evaluate_runtime_smart_exit(
    *, position: Any, net_pnl_percent: Any, policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Conservative runtime exit; strategy-owned positions are never overridden."""
    snapshot = dict(policy or {})
    if bool(snapshot.get("strategy_owned")):
        return {"should_exit": False, "reason": "ai_custom_exit_contract", "source": "smart_exit_policy"}
    final = dict(snapshot.get("final") or snapshot.get("effective") or {})
    sl_fraction = _fraction(final.get("sl", final.get("sl_fraction", 0.0020)), 0.0020)
    pnl = _float(net_pnl_percent)
    try:
        entry_time = getattr(position, "entry_time", None)
        from datetime import datetime
        held_minutes = max(0.0, (datetime.now(entry_time.tzinfo) - entry_time).total_seconds() / 60.0)
    except Exception:
        held_minutes = 0.0
    # Time exit only realizes a positive result after costs. Risk reduction may
    # close before the insurance SL but can never increase the allowed loss.
    if held_minutes >= 25.0 and pnl > 0.08:
        return {"should_exit": True, "reason": f"보유시간 {held_minutes:.1f}분 및 순수익 {pnl:.3f}%", "source": "time_profit"}
    if pnl <= -(sl_fraction * 100.0 * 0.90):
        return {"should_exit": True, "reason": f"보험 SL 접근 {pnl:.3f}%", "source": "risk_reduction"}
    return {"should_exit": False, "reason": "유지", "source": "smart_exit_policy"}


def record_runtime_exit_decision(position: Any, decision: Mapping[str, Any]) -> None:
    snapshot = dict(getattr(position, "exit_policy", {}) or {})
    snapshot["last_exit_decision"] = dict(decision or {})
    position.exit_policy = snapshot
