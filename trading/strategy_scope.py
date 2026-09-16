"""Shared asset/venue scope contract for selection, observation and display."""
from __future__ import annotations


def canonical_venue(value: str) -> str:
    value = str(value or "").strip().lower().replace("_", "")
    return {"koreainvestment": "kis", "miraeasset": "mirae"}.get(value, value)


def scope_matches(scope: str, *, asset_class: str, target: str) -> bool:
    scope = str(scope or "asset:crypto").strip().lower()
    asset = str(asset_class or "").strip().lower()
    family = "stock" if asset == "etf" else asset
    if scope == "asset:all" or scope == f"asset:{family}" or scope == f"asset:{asset}":
        return True
    kind, _, names = scope.partition(":")
    if kind not in {"broker", "exchange"}:
        return False
    if family != ("stock" if kind == "broker" else "crypto"):
        return False
    if names in {"connected", "unified"}:
        return True
    return canonical_venue(target) in {canonical_venue(name) for name in names.split(",") if name.strip()}


def scoped_pool(strategies, *, asset_class: str, target: str, limit: int = 10):
    eligible = [item for item in strategies if isinstance(item, dict) and scope_matches(
        item.get("target_scope") or (item.get("rules") or {}).get("target_scope"),
        asset_class=asset_class, target=target,
    )]
    return sorted(eligible, key=lambda item: int(item.get("priority", 5) or 5), reverse=True)[:limit]
