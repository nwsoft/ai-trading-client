#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""NoahAI 클라이언트의 서버 KPI 이벤트 전송 유틸리티."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


ALLOWED_ASSET_CLASSES = (
    "platform",
    "crypto",
    "stock",
    "etf",
    "life_finance",
    "risk",
)

ALLOWED_CATEGORIES = (
    "auth",
    "trade",
    "report",
    "learning",
    "risk",
    "platform",
)

ALLOWED_STATUSES = (
    "success",
    "failed",
    "blocked",
    "skipped",
    "info",
)


def _normalize_dimensions(category: str, asset_class: str, status: str) -> Tuple[str, str, str]:
    category_norm = str(category or "").strip().lower()
    asset_norm = str(asset_class or "").strip().lower()
    status_norm = str(status or "").strip().lower()

    category_alias = {
        "trading": "trade",
        "reports": "report",
        "ai_learning": "learning",
        "platform_health": "platform",
        "authentication": "auth",
    }
    status_alias = {
        "ok": "success",
        "done": "success",
        "error": "failed",
        "failure": "failed",
        "rejected": "blocked",
        "denied": "blocked",
        "skip": "skipped",
        "hold": "skipped",
        "warning": "info",
    }
    asset_alias = {
        "stocks": "stock",
        "equity": "stock",
        "life": "life_finance",
        "lifefinance": "life_finance",
    }

    category_norm = category_alias.get(category_norm, category_norm)
    status_norm = status_alias.get(status_norm, status_norm)
    asset_norm = asset_alias.get(asset_norm, asset_norm)

    if category_norm not in ALLOWED_CATEGORIES:
        category_norm = "platform"
    if asset_norm not in ALLOWED_ASSET_CLASSES:
        asset_norm = "platform"
    if status_norm not in ALLOWED_STATUSES:
        status_norm = "info"

    return category_norm, asset_norm, status_norm


class ServerKPIClient:
    """fastapi설치 서버의 KPI 수집 엔드포인트 호출 클라이언트."""

    def __init__(self, base_url: str = "https://daltrading.net", timeout: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def emit_event(
        self,
        *,
        event_type: str,
        category: str,
        asset_class: str = "platform",
        status: str = "success",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        source: str = "noahai_client",
        metric_value: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        normalized_category, normalized_asset, normalized_status = _normalize_dimensions(
            category=category,
            asset_class=asset_class,
            status=status,
        )

        payload: Dict[str, Any] = {
            "event_type": event_type,
            "category": normalized_category,
            "asset_class": normalized_asset,
            "status": normalized_status,
            "user_id": user_id,
            "session_id": session_id,
            "source": source,
            "metric_value": metric_value,
            "metadata": {
                "schema_version": "kpi-v1",
                **(metadata or {}),
            },
        }
        try:
            response = requests.post(
                f"{self.base_url}/auth/kpi/event",
                json=payload,
                timeout=self.timeout,
            )
            return response.status_code == 200
        except Exception as exc:
            logger.debug("KPI 이벤트 전송 실패: %s", exc)
            return False


def _load_user_context() -> Dict[str, Optional[str]]:
    """token.json에서 user_id/session_id를 읽어 전송 컨텍스트를 만든다."""
    try:
        from path_utils import get_token_file_path

        token_path = get_token_file_path()
        with open(token_path, "r", encoding="utf-8") as token_file:
            token_data = json.load(token_file)

        user_info = token_data.get("user_info", {}) if isinstance(token_data, dict) else {}
        return {
            "user_id": user_info.get("id") or token_data.get("user_id"),
            "session_id": user_info.get("session_id") or token_data.get("session_id"),
        }
    except Exception:
        return {"user_id": None, "session_id": None}


def emit_kpi_event(
    *,
    event_type: str,
    category: str,
    asset_class: str = "platform",
    status: str = "success",
    source: str = "noahai_client",
    metric_value: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
    include_user_context: bool = True,
) -> bool:
    """예외를 밖으로 던지지 않는 안전한 KPI 이벤트 전송 함수."""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    if include_user_context:
        context = _load_user_context()
        user_id = context.get("user_id")
        session_id = context.get("session_id")

    client = ServerKPIClient()
    return client.emit_event(
        event_type=event_type,
        category=category,
        asset_class=asset_class,
        status=status,
        user_id=user_id,
        session_id=session_id,
        source=source,
        metric_value=metric_value,
        metadata=metadata,
    )
