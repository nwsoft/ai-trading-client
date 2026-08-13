"""Load and validate the single Web UI feature inventory."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


INVENTORY_PATH = Path(__file__).resolve().parents[1] / "config" / "web_ui_feature_inventory.json"


@lru_cache(maxsize=1)
def load_feature_inventory() -> dict[str, Any]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    required = {"schema_version", "release_version", "transition_mode", "services", "platform_features"}
    missing = required.difference(payload)
    if missing:
        raise ValueError(f"web UI feature inventory missing keys: {sorted(missing)}")
    if payload["transition_mode"] != "read_only_parallel":
        raise ValueError("Stage 0 inventory must remain read_only_parallel")

    feature_ids: set[str] = set()
    for service in payload.get("services", []):
        if not service.get("id") or not service.get("label"):
            raise ValueError("every service requires id and label")
        for feature in service.get("features", []):
            feature_id = str(feature.get("id") or "")
            if not feature_id or feature_id in feature_ids:
                raise ValueError(f"invalid or duplicate feature id: {feature_id!r}")
            feature_ids.add(feature_id)

    return payload
