"""Load and validate the single Web UI feature inventory."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from config.app_version import RELEASE_VERSION
from config.product_ui_contract import (
    AI_ANALYST_CARDS,
    LIFE_FINANCE_INNER_TABS,
    LIFE_FINANCE_QUICK_ACTIONS,
    MANUAL_SECTION_LABELS,
    PORTFOLIO_INSIGHT_SECTIONS,
    SERVICE_FEATURE_LABELS,
    SERVICE_ORDER,
    SERVICE_SOURCES,
    SETTINGS_SECTION_LABELS,
)


INVENTORY_PATH = Path(__file__).resolve().parents[1] / "config" / "web_ui_feature_inventory.json"


@lru_cache(maxsize=1)
def load_feature_inventory() -> dict[str, Any]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    required = {"schema_version", "release_version", "transition_mode", "services", "platform_features"}
    missing = required.difference(payload)
    if missing:
        raise ValueError(f"web UI feature inventory missing keys: {sorted(missing)}")
    if payload["transition_mode"] != "internal_full_migration":
        raise ValueError("Web UI inventory must describe the internal full migration candidate")
    if payload["release_version"] != RELEASE_VERSION:
        raise ValueError("web UI feature inventory release version is not aligned")
    if payload.get("commands_enabled") is not True:
        raise ValueError("The internal migration candidate must expose gated application commands")

    services = payload.get("services", [])
    observed_services = tuple((str(service.get("id") or ""), str(service.get("label") or "")) for service in services)
    if observed_services != SERVICE_ORDER:
        raise ValueError(f"web UI service order differs from product contract: {observed_services!r}")

    feature_ids: set[str] = set()
    for service in services:
        if not service.get("id") or not service.get("label"):
            raise ValueError("every service requires id and label")
        service_id = str(service["id"])
        sources = tuple(str(source) for source in service.get("sources", []))
        if sources != SERVICE_SOURCES[service_id]:
            raise ValueError(f"{service_id} source order differs from product contract")
        labels = tuple(str(feature.get("label") or "") for feature in service.get("features", []))
        if labels != SERVICE_FEATURE_LABELS[service_id]:
            raise ValueError(f"{service_id} feature order differs from product contract")
        for feature in service.get("features", []):
            feature_id = str(feature.get("id") or "")
            if not feature_id or feature_id in feature_ids:
                raise ValueError(f"invalid or duplicate feature id: {feature_id!r}")
            feature_ids.add(feature_id)

    for feature in payload.get("platform_features", []):
        feature_id = str(feature.get("id") or "")
        if not feature_id or feature_id in feature_ids:
            raise ValueError(f"invalid or duplicate feature id: {feature_id!r}")
        feature_ids.add(feature_id)

    payload["ui_contract"] = {
        "settings_sections": list(SETTINGS_SECTION_LABELS),
        "manual_sections": list(MANUAL_SECTION_LABELS),
        "life_finance_inner_tabs": list(LIFE_FINANCE_INNER_TABS),
        "life_finance_quick_actions": list(LIFE_FINANCE_QUICK_ACTIONS),
        "portfolio_insight_sections": list(PORTFOLIO_INSIGHT_SECTIONS),
        "ai_analyst_cards": list(AI_ANALYST_CARDS),
    }
    return payload


def feature_ids_by_service() -> dict[str, frozenset[str]]:
    """Return the exact workspace feature IDs owned by each product service.

    The Web gateway must not accept an arbitrary feature string merely because
    it is syntactically valid.  Doing so makes it possible for a stock screen to
    ask for a blockchain workspace (or the reverse) and was one of the causes of
    cross-service data appearing under the wrong tab during the migration.
    """

    inventory = load_feature_inventory()
    return {
        str(service["id"]): frozenset(
            str(feature["id"])
            for feature in service.get("features", [])
        )
        for service in inventory["services"]
    }


def validate_workspace_feature(service: str, feature: str) -> None:
    """Fail closed unless ``feature`` is owned by ``service`` in the contract."""

    owned = feature_ids_by_service().get(str(service or ""))
    if owned is None or str(feature or "") not in owned:
        raise ValueError("workspace_feature_service_mismatch")
