"""UI-neutral account display contracts shared by legacy and Web runtimes."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Set


def _numeric_balance(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("total", value.get("balance", value.get("wallet_balance", 0)))
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def normalize_spot_holdings(balance: Any, quote_asset: str = "KRW") -> Dict[str, Dict[str, Any]]:
    """Return positive spot holdings without quote and account summary fields."""
    if not isinstance(balance, dict):
        return {}

    excluded = {
        str(quote_asset or "KRW").upper(),
        "TOTAL", "TOTAL_BALANCE", "TOTAL_ASSETS", "AVAILABLE",
        "AVAILABLE_BALANCE", "FREE", "CASH", "EQUITY",
        "UNREALIZED_PNL", "UNREALIZEDPNL",
    }
    holdings: Dict[str, Dict[str, Any]] = {}
    for raw_asset, raw_value in balance.items():
        asset = str(raw_asset or "").strip().upper()
        quantity = _numeric_balance(raw_value)
        if not asset or asset in excluded or quantity <= 0:
            continue
        holdings[asset] = {
            "symbol": asset,
            "side": "HOLD",
            "quantity": quantity,
            "entry_price": 0.0,
            "unrealized_pnl": 0.0,
        }
    return holdings


def classify_spot_holdings(
    balance: Any,
    *,
    quote_asset: str = "KRW",
    managed_quantities: Optional[Mapping[str, float]] = None,
    exchange_tradable_assets: Optional[Set[str]] = None,
    noahai_eligible_assets: Optional[Set[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Classify every positive spot balance without claiming account ownership.

    Quantity or value thresholds are deliberately not used to hide airdrops.
    Ownership comes only from the persisted NoahAI entry ledger. Market
    metadata determines whether an external holding is in the supported KRW
    universe, exchange-tradable elsewhere, unavailable, or not yet known.
    """
    rows = normalize_spot_holdings(balance, quote_asset=quote_asset)
    managed = {
        str(asset or "").strip().upper(): max(0.0, float(quantity or 0.0))
        for asset, quantity in dict(managed_quantities or {}).items()
        if str(asset or "").strip()
    }
    tradable = (
        {str(asset).strip().upper() for asset in exchange_tradable_assets}
        if exchange_tradable_assets is not None else None
    )
    eligible = (
        {str(asset).strip().upper() for asset in noahai_eligible_assets}
        if noahai_eligible_assets is not None else None
    )
    for asset, row in rows.items():
        total = float(row.get("quantity") or 0.0)
        managed_quantity = min(total, managed.get(asset, 0.0))
        external_quantity = max(0.0, total - managed_quantity)
        if managed_quantity > 0 and external_quantity > 1e-12:
            ownership = "mixed"
        elif managed_quantity > 0:
            ownership = "noahai"
        else:
            ownership = "external"

        exchange_tradable = None if tradable is None else asset in tradable
        noahai_eligible = None if eligible is None else asset in eligible
        if ownership in {"noahai", "mixed"}:
            display_group = "noahai_managed"
        elif noahai_eligible is True:
            display_group = "external_tradable"
        elif exchange_tradable is True:
            display_group = "external_unsupported_market"
        elif exchange_tradable is False:
            display_group = "reference_unavailable"
        else:
            display_group = "market_unknown"

        row.update({
            "ownership": ownership,
            "managed_quantity": managed_quantity,
            "external_quantity": external_quantity,
            "auto_trade_managed": managed_quantity > 0,
            "exchange_tradable": exchange_tradable,
            "noahai_eligible": noahai_eligible,
            "display_group": display_group,
        })
    return rows
