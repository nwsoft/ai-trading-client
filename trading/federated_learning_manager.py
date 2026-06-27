#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""연합학습 배치 파일을 로컬에서 안전하게 관리한다."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from path_utils import get_cache_dir


@dataclass
class FLBatch:
    batch_id: str
    created_at: str
    sample_count: int
    status: str
    file_path: str


class FederatedLearningDataManager:
    def __init__(self, base_dir: str | None = None) -> None:
        root = base_dir or os.path.join(get_cache_dir(), "federated_learning")
        self.base_dir = root
        self.pending_dir = os.path.join(self.base_dir, "pending")
        self.sent_dir = os.path.join(self.base_dir, "sent")
        os.makedirs(self.pending_dir, exist_ok=True)
        os.makedirs(self.sent_dir, exist_ok=True)

    def create_batch(self, payload: List[Dict[str, Any]]) -> FLBatch:
        now = datetime.now(timezone.utc)
        batch_id = now.strftime("flb_%Y%m%dT%H%M%S_%f")
        file_path = os.path.join(self.pending_dir, f"{batch_id}.json")

        raw = {
            "batch_id": batch_id,
            "created_at": now.isoformat(),
            "sample_count": len(payload),
            "status": "pending",
            "payload": payload,
        }
        with open(file_path, "w", encoding="utf-8") as fp:
            json.dump(raw, fp, ensure_ascii=False, indent=2)

        return FLBatch(
            batch_id=batch_id,
            created_at=raw["created_at"],
            sample_count=len(payload),
            status="pending",
            file_path=file_path,
        )

    def list_pending_batches(self) -> List[FLBatch]:
        items: List[FLBatch] = []
        for name in sorted(os.listdir(self.pending_dir)):
            if not name.endswith(".json"):
                continue
            file_path = os.path.join(self.pending_dir, name)
            try:
                with open(file_path, "r", encoding="utf-8") as fp:
                    raw = json.load(fp)
                items.append(
                    FLBatch(
                        batch_id=str(raw.get("batch_id") or name[:-5]),
                        created_at=str(raw.get("created_at") or ""),
                        sample_count=int(raw.get("sample_count") or 0),
                        status=str(raw.get("status") or "pending"),
                        file_path=file_path,
                    )
                )
            except Exception:
                continue
        return items

    def load_batch_payload(self, batch: FLBatch) -> List[Dict[str, Any]]:
        with open(batch.file_path, "r", encoding="utf-8") as fp:
            raw = json.load(fp)
        data = raw.get("payload")
        return data if isinstance(data, list) else []

    def mark_sent(self, batch: FLBatch) -> str:
        sent_path = os.path.join(self.sent_dir, os.path.basename(batch.file_path))
        with open(batch.file_path, "r", encoding="utf-8") as fp:
            raw = json.load(fp)
        raw["status"] = "sent"
        raw["sent_at"] = datetime.now(timezone.utc).isoformat()
        with open(sent_path, "w", encoding="utf-8") as fp:
            json.dump(raw, fp, ensure_ascii=False, indent=2)
        os.remove(batch.file_path)
        return sent_path

    @staticmethod
    def to_dict(batch: FLBatch) -> Dict[str, Any]:
        return asdict(batch)
