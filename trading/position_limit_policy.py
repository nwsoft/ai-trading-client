"""Shared crypto position-count policy for LIVE and PAPER execution paths.

The legacy settings screen stores ``focus``/``multi`` while a few older
runtime branches used the obsolete value ``single``.  Keeping normalization in
one small module prevents PAPER, Binance-native and unified adapters from
interpreting the same saved settings differently.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from trading.exchanges.venue_capabilities import CRYPTO_VENUE_ORDER


CRYPTO_EXCHANGES = CRYPTO_VENUE_ORDER
FOCUS_MODE_ALIASES = {"focus", "single", "concentrated"}
MULTI_MODE_ALIASES = {"multi", "multiple", "distributed"}


def normalize_position_mode(value: Any) -> str:
    """Return the canonical legacy-compatible position mode."""
    normalized = str(value or "").strip().lower()
    if normalized in FOCUS_MODE_ALIASES:
        return "focus"
    if normalized in MULTI_MODE_ALIASES:
        return "multi"
    return "multi"


def effective_crypto_position_limit(
    settings: Mapping[str, Any] | None,
    exchange_name: str = "",
    *,
    hard_max: int = 10,
) -> int:
    """Resolve one adapter's managed-position cap for both LIVE and PAPER.

    ``focus`` always means one position, even when an older profile still has
    stale ``max_positions=3`` or per-exchange overrides.  Multi mode respects
    the per-exchange override and then the account master value, bounded to the
    expert 1..10 product range.  A strategy and the performance layer may only
    reduce this account ceiling later; neither can raise it.
    """
    payload = settings if isinstance(settings, Mapping) else {}
    if normalize_position_mode(payload.get("position_mode")) == "focus":
        return 1

    raw: Any = payload.get("max_positions", 3)
    overrides = payload.get("exchange_risk_overrides")
    if isinstance(overrides, Mapping):
        exchange = str(exchange_name or "").strip().lower()
        exchange_settings = overrides.get(exchange)
        if isinstance(exchange_settings, Mapping):
            raw = exchange_settings.get("max_positions", raw)
    try:
        return max(1, min(max(1, int(hard_max)), int(raw or 3)))
    except (TypeError, ValueError):
        return min(10, max(1, int(hard_max)))


def effective_position_count(
    managed_positions: Collection[Any] | Mapping[Any, Any] | None,
    external_positions: Collection[Any] | Mapping[Any, Any] | None,
    execution_mode: Any,
) -> int:
    """Count external account positions only for LIVE order capacity.

    PAPER and LEARNING are isolated execution ledgers.  A manual position found
    during an earlier LIVE reconciliation must never consume a virtual slot or
    make a focus/multi PAPER run appear to ignore its configured cap.
    """
    managed_count = len(managed_positions or ())
    mode = str(getattr(execution_mode, "value", execution_mode) or "").strip().lower()
    if mode != "live":
        return managed_count
    return managed_count + len(external_positions or ())


def synchronize_position_limit_settings(
    settings: dict[str, Any],
    *,
    mode: Any | None = None,
    max_positions: Any | None = None,
) -> int:
    """Mutate a settings snapshot to the original UI's consistent contract."""
    canonical_mode = normalize_position_mode(
        settings.get("position_mode") if mode is None else mode
    )
    explicit_limit: int | None = None
    if mode is None and max_positions is not None:
        try:
            explicit_limit = max(1, min(10, int(max_positions)))
            canonical_mode = "focus" if explicit_limit == 1 else "multi"
        except (TypeError, ValueError):
            canonical_mode = "multi"
    if explicit_limit is not None:
        limit = explicit_limit
    elif canonical_mode == "focus":
        limit = 1
    elif mode is not None:
        # A direct focus -> multi UI switch restores the safe product default.
        # Expert 5/10 selection is a separate explicit max_positions change.
        limit = 3
    else:
        try:
            limit = max(2, min(10, int(settings.get("max_positions", 3) or 3)))
        except (TypeError, ValueError):
            limit = 3
    settings["position_mode"] = canonical_mode
    settings["max_positions"] = limit

    overrides = settings.get("exchange_risk_overrides")
    synchronized = dict(overrides) if isinstance(overrides, Mapping) else {}
    for exchange in CRYPTO_EXCHANGES:
        current = synchronized.get(exchange)
        row = dict(current) if isinstance(current, Mapping) else {}
        row["max_positions"] = limit
        synchronized[exchange] = row
    settings["exchange_risk_overrides"] = synchronized
    return limit
