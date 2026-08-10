"""Runtime construction policy for venue-specific clients."""

from __future__ import annotations

from typing import Any, Mapping


def requires_binance_runtime(settings: Mapping[str, Any] | None) -> bool:
    """Return whether this profile explicitly needs the Binance runtime.

    Once any exchange scope is present, Binance must be named in that scope.
    Legacy profiles without scope keys retain their selected-exchange behavior.
    """
    cfg = dict(settings or {})
    scope_keys = (
        "enabled_exchanges",
        "trade_enabled_exchanges",
        "learning_enabled_exchanges",
    )
    explicit_scope = any(key in cfg for key in scope_keys)
    scoped = {
        str(item or "").strip().lower()
        for key in scope_keys
        for item in (cfg.get(key, []) or [])
        if str(item or "").strip()
    }
    if explicit_scope:
        return "binance" in scoped
    return str(cfg.get("selected_exchange") or "binance").strip().lower() == "binance"
