"""Common, auditable position-sizing contract.

The policy decides quote-currency exposure.  Venue adapters only translate the
approved exposure into spot units, futures contracts, or whole stock shares.
``legacy_venue`` is kept only as an explicit migration state.  New installs
use ``account_risk``; an old account that had no sizing policy is stamped as
legacy before template merging so an update cannot silently increase a live
order.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping


FIXED_NOTIONAL = "fixed_notional"
ACCOUNT_RISK = "account_risk"
LEGACY_VENUE = "legacy_venue"
MANUAL_NOTIONAL = "manual_notional"
SUPPORTED_MODES = {FIXED_NOTIONAL, MANUAL_NOTIONAL, ACCOUNT_RISK, LEGACY_VENUE}


def derive_market_risk_multiplier(
    *, market_regime: Any = "", volatility_fraction: Any = 0.0,
) -> float:
    """Return a reduction-only market overlay shared by every asset adapter."""
    regime = str(market_regime or "").strip().lower()
    volatility = abs(_float(volatility_fraction, 0.0))
    if regime in {"extreme", "crash", "panic"} or volatility >= 0.05:
        return 0.50
    if regime in {"volatile", "high_volatility"} or volatility >= 0.03:
        return 0.70
    if regime in {"bear", "risk_off"} or volatility >= 0.02:
        return 0.85
    return 1.0


def effective_position_limit(
    account_limit: Any,
    *,
    strategy_risk_model: Mapping[str, Any] | None = None,
    performance_limit: Any = None,
) -> Dict[str, Any]:
    """Resolve one position-count ceiling without allowing a strategy to raise it."""
    account = max(1, min(int(_float(account_limit, 1.0)), 10))
    strategy = dict(strategy_risk_model or {})
    requested_raw = strategy.get("max_concurrent_positions")
    requested = (
        max(1, min(int(_float(requested_raw, account)), 10))
        if requested_raw is not None else account
    )
    performance = (
        max(1, min(int(_float(performance_limit, account)), 10))
        if performance_limit is not None else account
    )
    effective = min(account, requested, performance)
    return {
        "account_max_positions": account,
        "strategy_requested_max_positions": requested_raw,
        "performance_max_positions": performance_limit,
        "effective_max_positions": effective,
        "limited_by": [
            reason for reason, value in (
                ("account_position_cap", account),
                ("strategy_position_cap", requested),
                ("performance_position_cap", performance),
            ) if value == effective
        ],
    }


def _float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except (TypeError, ValueError):
        return default


def normalize_position_sizing_policy(
    settings: Mapping[str, Any] | None,
    *,
    quote_currency: str,
) -> Dict[str, Any]:
    root = dict(settings or {})
    raw = dict(root.get("position_sizing_policy") or {})
    mode = str(raw.get("mode") or LEGACY_VENUE).strip().lower()
    if mode not in SUPPORTED_MODES:
        mode = LEGACY_VENUE
    if mode == FIXED_NOTIONAL:
        mode = MANUAL_NOTIONAL
    quote = str(quote_currency or "USDT").strip().upper()
    paper_equity_key = "paper_equity_krw" if quote == "KRW" else "paper_equity_usdt"
    return {
        "mode": mode,
        "risk_per_trade_percent": max(
            0.01, min(_float(raw.get("risk_per_trade_percent"), 0.50), 2.0)
        ),
        "max_margin_usage_percent": max(
            0.1, min(_float(raw.get("max_margin_usage_percent"), 10.0), 50.0)
        ),
        "max_notional_percent": max(
            0.1, min(_float(raw.get("max_notional_percent"), 50.0), 100.0)
        ),
        "paper_equity": max(
            0.0,
            _float(
                raw.get(paper_equity_key),
                1_000_000.0 if quote == "KRW" else 1_000.0,
            ),
        ),
        "quote_currency": quote,
    }


def calculate_position_sizing(
    *,
    policy: Mapping[str, Any] | None,
    asset_class: str,
    quote_currency: str,
    account_equity: float,
    account_equity_source: str,
    price: float,
    stop_fraction: float,
    requested_leverage: int,
    leverage_cap: int,
    fixed_notional: float,
    risk_multiplier: float = 1.0,
    market_risk_multiplier: float = 1.0,
    contract_size: float = 1.0,
    strategy_risk_model: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Calculate one auditable sizing plan without accessing an account/API."""
    normalized = normalize_position_sizing_policy(
        {"position_sizing_policy": dict(policy or {})},
        quote_currency=quote_currency,
    )
    mode = normalized["mode"]
    asset = str(asset_class or "crypto_futures").strip().lower()
    quote = normalized["quote_currency"]
    equity = max(0.0, _float(account_equity, 0.0))
    px = max(0.0, _float(price, 0.0))
    stop = max(0.0, _float(stop_fraction, 0.0))
    fixed = max(0.0, _float(fixed_notional, 0.0))
    performance_multiplier = max(0.01, min(_float(risk_multiplier, 1.0), 1.0))
    market_multiplier = max(0.01, min(_float(market_risk_multiplier, 1.0), 1.0))
    multiplier = performance_multiplier * market_multiplier
    strategy = dict(strategy_risk_model or {})
    contract = max(1e-12, _float(contract_size, 1.0))
    is_leveraged = asset in {"crypto_futures", "futures", "derivative"}
    configured_leverage = max(1, int(_float(requested_leverage, 1.0)))
    account_leverage_cap = max(1, int(_float(leverage_cap, configured_leverage)))
    strategy_leverage_cap = max(
        1,
        int(_float(strategy.get("max_leverage"), account_leverage_cap)),
    )
    hard_leverage_cap = min(account_leverage_cap, strategy_leverage_cap)
    available_leverage = min(configured_leverage, hard_leverage_cap) if is_leveraged else 1

    result: Dict[str, Any] = {
        "allowed": False,
        "reason": "",
        "mode": mode,
        "asset_class": asset,
        "quote_currency": quote,
        "account_equity": equity,
        "account_equity_source": str(account_equity_source or "unavailable"),
        "stop_fraction": stop,
        "risk_multiplier": multiplier,
        "performance_risk_multiplier": performance_multiplier,
        "market_risk_multiplier": market_multiplier,
        "configured_leverage": configured_leverage,
        "account_leverage_cap": account_leverage_cap,
        "strategy_requested_leverage_cap": strategy.get("max_leverage"),
        "leverage_cap": hard_leverage_cap,
        "effective_leverage": available_leverage,
        "contract_size": contract,
    }
    if px <= 0:
        result["reason"] = "reference_price_unavailable"
        return result

    if mode == LEGACY_VENUE:
        result["reason"] = "legacy_venue_adapter_required"
        return result

    if mode in {FIXED_NOTIONAL, MANUAL_NOTIONAL}:
        if fixed <= 0:
            result["reason"] = "fixed_notional_missing"
            return result
        target_notional = fixed * multiplier
        # The legacy configured amount remains the upper authorization.  A
        # venue minimum may raise a reduced cold-start order only inside it.
        authorized_cap = fixed
        risk_amount = target_notional * stop if stop > 0 else 0.0
        margin = target_notional / available_leverage
        result.update({
            "allowed": True,
            "reason": "manual_notional_preserved",
            "target_risk_amount": risk_amount,
            "risk_per_trade_percent": (
                risk_amount / equity * 100.0 if equity > 0 else None
            ),
            "target_notional_before_caps": target_notional,
            "target_notional": target_notional,
            "authorized_notional_cap": authorized_cap,
            "estimated_margin": margin,
            "margin_usage_percent": margin / equity * 100.0 if equity > 0 else None,
            "target_quantity": target_notional / (px * contract),
        })
        return result

    if equity <= 0:
        result["reason"] = "account_equity_unavailable"
        return result
    if stop <= 0:
        result["reason"] = "stop_distance_unavailable"
        return result

    account_risk_percent = normalized["risk_per_trade_percent"]
    account_margin_percent = normalized["max_margin_usage_percent"]
    account_notional_percent = normalized["max_notional_percent"]

    def _strategy_cap(key: str, account_value: float) -> float:
        if strategy.get(key) is None:
            return account_value
        requested = _float(strategy.get(key), account_value)
        return min(account_value, max(0.0, requested))

    risk_percent = _strategy_cap("risk_per_trade_percent", account_risk_percent)
    margin_percent = _strategy_cap("max_margin_usage_percent", account_margin_percent)
    notional_percent = _strategy_cap("max_notional_percent", account_notional_percent)
    if risk_percent <= 0 or margin_percent <= 0 or notional_percent <= 0:
        result["reason"] = "strategy_risk_budget_zero"
        return result
    target_risk_amount = equity * (risk_percent / 100.0) * multiplier
    risk_notional = target_risk_amount / stop
    notional_cap = equity * (notional_percent / 100.0)
    margin_cap = equity * (margin_percent / 100.0)
    uncapped_target = risk_notional
    target_before_leverage = min(risk_notional, notional_cap)
    required_leverage = max(1, int(math.ceil(target_before_leverage / margin_cap))) if margin_cap > 0 else 1
    effective_leverage = min(available_leverage, required_leverage)
    leverage_notional_cap = margin_cap * effective_leverage
    target_notional = min(target_before_leverage, leverage_notional_cap)
    actual_risk_amount = target_notional * stop
    estimated_margin = target_notional / effective_leverage
    limiting_reasons = []
    if notional_cap + 1e-12 < risk_notional:
        limiting_reasons.append("max_notional_percent")
    if leverage_notional_cap + 1e-12 < target_before_leverage:
        limiting_reasons.append("max_margin_and_leverage")
    if performance_multiplier < 1.0:
        limiting_reasons.append("performance_risk_multiplier")
    if market_multiplier < 1.0:
        limiting_reasons.append("market_risk_multiplier")

    result.update({
        "allowed": target_notional > 0,
        "reason": "account_risk_budget" if target_notional > 0 else "risk_budget_zero",
        "target_risk_amount": target_risk_amount,
        "actual_risk_amount_at_stop": actual_risk_amount,
        "risk_per_trade_percent": risk_percent,
        "account_risk_per_trade_percent": account_risk_percent,
        "strategy_requested_risk_per_trade_percent": strategy.get("risk_per_trade_percent"),
        "effective_risk_per_trade_percent": risk_percent * multiplier,
        "account_max_margin_usage_percent": account_margin_percent,
        "strategy_requested_max_margin_usage_percent": strategy.get("max_margin_usage_percent"),
        "effective_max_margin_usage_percent": margin_percent,
        "account_max_notional_percent": account_notional_percent,
        "strategy_requested_max_notional_percent": strategy.get("max_notional_percent"),
        "effective_max_notional_percent": notional_percent,
        "target_notional_before_caps": uncapped_target,
        "target_notional": target_notional,
        "authorized_notional_cap": min(notional_cap, leverage_notional_cap),
        "max_notional_amount": notional_cap,
        "max_margin_amount": margin_cap,
        "estimated_margin": estimated_margin,
        "margin_usage_percent": estimated_margin / equity * 100.0,
        "effective_leverage": effective_leverage,
        "required_leverage": required_leverage,
        "target_quantity": target_notional / (px * contract),
        "limiting_reasons": limiting_reasons,
    })
    if strategy.get("risk_per_trade_percent") is not None and risk_percent < _float(strategy.get("risk_per_trade_percent"), risk_percent):
        result["limiting_reasons"].append("account_risk_cap")
    if strategy.get("max_margin_usage_percent") is not None and margin_percent < _float(strategy.get("max_margin_usage_percent"), margin_percent):
        result["limiting_reasons"].append("account_margin_cap")
    if strategy.get("max_notional_percent") is not None and notional_percent < _float(strategy.get("max_notional_percent"), notional_percent):
        result["limiting_reasons"].append("account_notional_cap")
    if strategy.get("max_leverage") is not None and account_leverage_cap < strategy_leverage_cap:
        result["limiting_reasons"].append("account_leverage_cap")
    return result
