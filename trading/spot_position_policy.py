"""Fail-closed reconciliation rules for KRW spot holdings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Set


SPOT_EXCHANGES = frozenset({"upbit", "bithumb"})
DEFAULT_KRW_MIN_NOTIONAL = 5_000.0


def spot_base_asset(symbol: str) -> str:
    value = str(symbol or "").upper().strip()
    if "/" in value:
        left, right = value.split("/", 1)
        return right.split(":", 1)[0] if left == "KRW" else left
    if "-" in value:
        left, right = value.split("-", 1)
        return right if left == "KRW" else left
    if value.endswith("KRW"):
        return value[:-3]
    if value.startswith("KRW"):
        return value[3:]
    return value


def balance_quantity(balance: Mapping[str, Any], asset: str) -> float:
    value = balance.get(str(asset or "").upper(), 0) if isinstance(balance, Mapping) else 0
    if isinstance(value, Mapping):
        value = value.get("total", value.get("free", value.get("balance", 0)))
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


@dataclass(frozen=True)
class SpotHoldingAssessment:
    asset: str
    quantity: float
    price: float
    notional: float
    minimum_notional: float
    classification: str

    @property
    def is_material(self) -> bool:
        return self.classification == "material"


@dataclass(frozen=True)
class SpotPortfolioSummary:
    material_assets: frozenset[str]
    dust_assets: frozenset[str]
    unknown_price_assets: frozenset[str]


def assess_spot_holding(
    balance: Mapping[str, Any],
    symbol: str,
    price: float,
    *,
    minimum_notional: float = DEFAULT_KRW_MIN_NOTIONAL,
) -> SpotHoldingAssessment:
    asset = spot_base_asset(symbol)
    quantity = balance_quantity(balance, asset)
    safe_price = max(0.0, float(price or 0))
    notional = quantity * safe_price
    if quantity <= 0:
        classification = "empty"
    elif notional >= float(minimum_notional):
        classification = "material"
    else:
        classification = "dust"
    return SpotHoldingAssessment(
        asset=asset,
        quantity=quantity,
        price=safe_price,
        notional=notional,
        minimum_notional=float(minimum_notional),
        classification=classification,
    )


def safe_managed_close_quantity(
    *,
    managed_quantity: float,
    actual_quantity: float,
    baseline_quantity: float,
) -> float:
    """Never sell pre-existing holdings or more than the managed position."""
    managed = max(0.0, float(managed_quantity or 0))
    actual = max(0.0, float(actual_quantity or 0))
    baseline = max(0.0, float(baseline_quantity or 0))
    return min(managed, max(0.0, actual - baseline))


def summarize_spot_portfolio(
    balance: Mapping[str, Any],
    prices_by_asset: Mapping[str, Any],
    *,
    managed_assets: Set[str] | frozenset[str] = frozenset(),
    quote_asset: str = "KRW",
    minimum_notional: float = DEFAULT_KRW_MIN_NOTIONAL,
) -> SpotPortfolioSummary:
    """Classify unmanaged positive balances for total-position risk limits."""
    material: set[str] = set()
    dust: set[str] = set()
    unknown: set[str] = set()
    managed = {str(asset).upper() for asset in managed_assets}
    quote = str(quote_asset or "KRW").upper()
    for raw_asset in balance.keys() if isinstance(balance, Mapping) else ():
        asset = str(raw_asset or "").upper().strip()
        if not asset or asset == quote or asset in managed:
            continue
        quantity = balance_quantity(balance, asset)
        if quantity <= 0:
            continue
        try:
            price = float(prices_by_asset.get(asset, 0) or 0)
        except (TypeError, ValueError):
            price = 0.0
        if price <= 0:
            unknown.add(asset)
        elif quantity * price >= float(minimum_notional):
            material.add(asset)
        else:
            dust.add(asset)
    return SpotPortfolioSummary(
        material_assets=frozenset(material),
        dust_assets=frozenset(dust),
        unknown_price_assets=frozenset(unknown),
    )
