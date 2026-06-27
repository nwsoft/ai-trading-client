#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""로컬 모델 파일 버전/무결성 관리."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from path_utils import get_cache_dir


class LocalModelManager:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        root = base_dir or os.path.join(get_cache_dir(), "fl_models")
        self.base_dir = root
        self.models_dir = os.path.join(self.base_dir, "artifacts")
        self.meta_dir = os.path.join(self.base_dir, "metadata")
        os.makedirs(self.models_dir, exist_ok=True)
        os.makedirs(self.meta_dir, exist_ok=True)

    def save_model(self, model_name: str, version: str, content: bytes, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        filename = f"{model_name}_{version}.bin"
        model_path = os.path.join(self.models_dir, filename)
        with open(model_path, "wb") as fp:
            fp.write(content)

        checksum = hashlib.sha256(content).hexdigest()
        meta = {
            "model_name": model_name,
            "version": version,
            "file_name": filename,
            "checksum": checksum,
            "size": len(content),
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "extra": extra or {},
        }
        meta_path = self._meta_path(model_name, version)
        with open(meta_path, "w", encoding="utf-8") as fp:
            json.dump(meta, fp, ensure_ascii=False, indent=2)
        return meta

    def verify_model(self, model_name: str, version: str) -> bool:
        meta = self.get_model_meta(model_name, version)
        if not meta:
            return False
        model_path = os.path.join(self.models_dir, str(meta.get("file_name") or ""))
        if not os.path.exists(model_path):
            return False
        with open(model_path, "rb") as fp:
            actual = hashlib.sha256(fp.read()).hexdigest()
        return actual == meta.get("checksum")

    def get_model_meta(self, model_name: str, version: str) -> Optional[Dict[str, Any]]:
        path = self._meta_path(model_name, version)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)

    def activate_model(self, model_name: str, version: str) -> None:
        pointer = os.path.join(self.base_dir, f"active_{model_name}.json")
        payload = {
            "model_name": model_name,
            "version": version,
            "activated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(pointer, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)

    def get_active_model(self, model_name: str) -> Optional[Dict[str, Any]]:
        pointer = os.path.join(self.base_dir, f"active_{model_name}.json")
        if not os.path.exists(pointer):
            return None
        with open(pointer, "r", encoding="utf-8") as fp:
            return json.load(fp)

    def _meta_path(self, model_name: str, version: str) -> str:
        return os.path.join(self.meta_dir, f"{model_name}_{version}.json")
