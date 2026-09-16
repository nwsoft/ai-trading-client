"""Deterministic valuation contract for Korean stock/ETF PAPER positions.

The PAPER engine cannot know an account's promotional brokerage commission or
the final execution slippage.  Values produced here are therefore estimates,
never broker-confirmed costs.  Rates are stored on each opened position so a
later settings change cannot silently rewrite the entry contract.
"""

from __future__ import annotations

from typing import Any, Mapping


DEFAULT_STOCK_PAPER_COSTS = {
    # Brokerage commission varies by broker/account.  This is a conservative
    # simulation default and is explicitly labelled as an estimate.
    "buy_commission_rate": 0.00015,
    "sell_commission_rate": 0.00015,
    # 2026 listed-stock sell-side total used by the simulation profile.
    # ETF units do not use the stock securities-transaction-tax rate.
    "stock_sell_tax_rate": 0.002,
    "etf_sell_tax_rate": 0.0,
    "buy_slippage_rate": 0.0003,
    "sell_slippage_rate": 0.0003,
}


def _rate(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    # A PAPER cost rate above 5% almost certainly represents a percent/fraction
    # unit mistake.  Fail back to the documented default rather than accepting
    # it or silently clamping a user value to a different meaning.
    if parsed < 0.0 or parsed > 0.05:
        return float(default)
    return parsed


def normalize_stock_paper_cost_policy(
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = dict(policy or {})
    configured = root.get("paper_costs")
    if isinstance(configured, Mapping):
        values = dict(configured)
        source = "settings.paper_costs"
    else:
        # The calculator may receive an already-normalized policy.  Accept the
        # same named fields so legacy-position valuation keeps the configured
        # profile instead of falling back to defaults on the second pass.
        values = {
            key: root[key]
            for key in DEFAULT_STOCK_PAPER_COSTS
            if key in root
        }
        source = str(root.get("cost_source") or "normalized_paper_costs")

    issues: list[str] = []
    normalized: dict[str, Any] = {}
    for key, default in DEFAULT_STOCK_PAPER_COSTS.items():
        raw = values.get(key, default)
        try:
            parsed = float(raw)
        except (TypeError, ValueError):
            parsed = float(default)
            if key in values:
                issues.append(f"{key}:not_numeric")
        if parsed < 0.0 or parsed > 0.05:
            parsed = float(default)
            issues.append(f"{key}:outside_fraction_range")
        normalized[key] = parsed
    normalized.update({
        "quote_currency": "KRW",
        "cost_schema_version": 1,
        "cost_calculation_status": (
            "estimated_stock_paper_contract_with_fallback"
            if issues
            else "estimated_stock_paper_contract"
        ),
        "cost_source": (
            "invalid_settings_fallback"
            if issues
            else source if values else "default_stock_paper_contract"
        ),
        "cost_policy_issues": issues,
    })
    return normalized


def calculate_stock_paper_valuation(
    position: Mapping[str, Any],
    current_price: float,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return gross/net PnL and an auditable estimated cost breakdown.

    Only LONG positions are supported by the domestic securities PAPER path.
    Entry costs already stored on the position are preserved.  A position
    opened by an older version is valued with the current documented PAPER
    profile and labelled ``estimated_legacy_stock_position``.
    """

    entry_price = float(position.get("entry_price") or 0.0)
    quantity = float(position.get("quantity") or 0.0)
    mark_price = float(current_price or 0.0)
    if entry_price <= 0.0 or quantity <= 0.0 or mark_price <= 0.0:
        return {
            "calculation_status": "invalid",
            "cost_calculation_status": "unavailable",
            "gross_pnl": 0.0,
            "net_pnl": 0.0,
            "net_pnl_percent": 0.0,
            "estimated_fees": 0.0,
            "estimated_taxes": 0.0,
            "estimated_slippage": 0.0,
            "total_cost": 0.0,
        }

    configured = normalize_stock_paper_cost_policy(policy)
    asset_class = str(position.get("asset_class") or "stock").strip().lower()
    is_etf = asset_class == "etf"

    def stored_rate(name: str) -> float:
        return _rate(position.get(name), float(configured[name]))

    buy_commission_rate = stored_rate("buy_commission_rate")
    sell_commission_rate = stored_rate("sell_commission_rate")
    buy_slippage_rate = stored_rate("buy_slippage_rate")
    sell_slippage_rate = stored_rate("sell_slippage_rate")
    sell_tax_rate = stored_rate("etf_sell_tax_rate" if is_etf else "stock_sell_tax_rate")

    entry_notional = entry_price * quantity
    exit_notional = mark_price * quantity
    legacy_entry_cost = "entry_fees" not in position or "entry_slippage" not in position
    entry_fees = (
        float(position.get("entry_fees") or 0.0)
        if "entry_fees" in position
        else entry_notional * buy_commission_rate
    )
    entry_slippage = (
        float(position.get("entry_slippage") or 0.0)
        if "entry_slippage" in position
        else entry_notional * buy_slippage_rate
    )
    exit_fees = exit_notional * sell_commission_rate
    exit_taxes = exit_notional * sell_tax_rate
    exit_slippage = exit_notional * sell_slippage_rate
    estimated_fees = entry_fees + exit_fees
    estimated_slippage = entry_slippage + exit_slippage
    total_cost = estimated_fees + estimated_slippage + exit_taxes
    gross_pnl = (mark_price - entry_price) * quantity
    net_pnl = gross_pnl - total_cost

    return {
        "calculation_status": "valid",
        "cost_calculation_status": (
            "estimated_legacy_stock_position"
            if legacy_entry_cost
            else "estimated_stock_paper_contract"
        ),
        "cost_source": str(
            position.get("cost_source") or configured["cost_source"]
        ),
        "cost_policy_issues": list(
            position.get("cost_policy_issues") or configured.get("cost_policy_issues") or []
        ),
        "cost_schema_version": 1,
        "asset_class": "etf" if is_etf else "stock",
        "quote_currency": "KRW",
        "entry_notional": entry_notional,
        "exit_notional": exit_notional,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "net_pnl_percent": net_pnl / entry_notional * 100.0,
        "estimated_fees": estimated_fees,
        "estimated_taxes": exit_taxes,
        "estimated_slippage": estimated_slippage,
        "total_cost": total_cost,
        "entry_fees": entry_fees,
        "entry_slippage": entry_slippage,
        "exit_fees": exit_fees,
        "exit_taxes": exit_taxes,
        "exit_slippage": exit_slippage,
        "buy_commission_rate": buy_commission_rate,
        "sell_commission_rate": sell_commission_rate,
        "stock_sell_tax_rate": stored_rate("stock_sell_tax_rate"),
        "etf_sell_tax_rate": stored_rate("etf_sell_tax_rate"),
        "buy_slippage_rate": buy_slippage_rate,
        "sell_slippage_rate": sell_slippage_rate,
    }
