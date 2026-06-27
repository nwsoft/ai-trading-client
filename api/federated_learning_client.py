#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""연합학습 서버 통신 클라이언트(기본 비활성화)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


class FederatedLearningClient:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: int = 5,
        enabled: bool = False,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.timeout = int(timeout)
        self.enabled = bool(enabled)

    def submit_batch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "reason": "disabled"}
        if not self.base_url:
            return {"ok": False, "reason": "missing_base_url"}

        url = f"{self.base_url}/api/federated-learning/batch"
        return self._post_json(url, payload)

    def fetch_global_model_info(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "reason": "disabled"}
        if not self.base_url:
            return {"ok": False, "reason": "missing_base_url"}

        url = f"{self.base_url}/api/federated-learning/model/latest"
        req = urllib.request.Request(url=url, method="GET", headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
            data = json.loads(body) if body else {}
            return {"ok": True, "status": 200, "data": data}
        except urllib.error.HTTPError as e:
            return {"ok": False, "status": e.code, "reason": str(e)}
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    def _post_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            data=encoded,
            method="POST",
            headers=self._headers(),
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = getattr(resp, "status", 200)
                body = resp.read().decode("utf-8")
            data = json.loads(body) if body else {}
            return {"ok": True, "status": status, "data": data}
        except urllib.error.HTTPError as e:
            return {"ok": False, "status": e.code, "reason": str(e)}
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
