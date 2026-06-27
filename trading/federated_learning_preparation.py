#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""연합학습/사전 SaaS 준비 오케스트레이터.

기본 정책:
- 설정 기본값은 모두 OFF
- OFF일 때는 기존 트레이딩 경로에 영향을 주지 않고 준비 객체만 초기화
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from api.federated_learning_client import FederatedLearningClient
from path_utils import get_db_file_path
from trading.federated_learning_manager import FederatedLearningDataManager
from trading.fl_rl_data_adapter import RLDataAdapter
from trading.local_model_manager import LocalModelManager


class FederatedLearningPreparationService:
    def __init__(self, settings: Dict[str, Any], logger: Any = None, db_path: Optional[str] = None) -> None:
        self.settings = settings if isinstance(settings, dict) else {}
        self.logger = logger
        self.db_path = db_path or get_db_file_path()

        self.adapter: Optional[RLDataAdapter] = None
        self.batch_manager: Optional[FederatedLearningDataManager] = None
        self.client: Optional[FederatedLearningClient] = None
        self.model_manager: Optional[LocalModelManager] = None

    def bootstrap(self) -> Dict[str, Any]:
        fl_cfg = self._fl_cfg()
        enabled = bool(fl_cfg.get("enabled", False))

        self.adapter = RLDataAdapter(
            db_path=self.db_path,
            user_scope=str(self.settings.get("user_id") or "default"),
        )
        self.batch_manager = FederatedLearningDataManager()
        self.client = FederatedLearningClient(
            base_url=str(fl_cfg.get("server_base_url") or ""),
            api_key=str(fl_cfg.get("api_key") or ""),
            timeout=int(fl_cfg.get("timeout_sec") or 5),
            enabled=enabled and bool(fl_cfg.get("upload_enabled", False)),
        )
        self.model_manager = LocalModelManager()

        self._log("info", f"FL 준비 구조 초기화 완료 (enabled={enabled})")
        return {
            "ok": True,
            "enabled": enabled,
            "batch_enabled": bool(fl_cfg.get("batch_enabled", False)),
            "upload_enabled": bool(fl_cfg.get("upload_enabled", False)),
        }

    def prepare_batch_once(self, limit: int = 1000) -> Dict[str, Any]:
        fl_cfg = self._fl_cfg()
        if not bool(fl_cfg.get("enabled", False)):
            return {"ok": False, "reason": "fl_disabled"}
        if not bool(fl_cfg.get("batch_enabled", False)):
            return {"ok": False, "reason": "batch_disabled"}

        if not self.adapter or not self.batch_manager:
            self.bootstrap()
        if not self.adapter or not self.batch_manager:
            return {"ok": False, "reason": "bootstrap_failed"}

        rows = self.adapter.fetch_trade_rows(limit=limit)
        transitions = self.adapter.build_transitions(rows)
        if not transitions:
            return {"ok": False, "reason": "no_transitions"}

        salt = str(fl_cfg.get("anonymization_salt") or "noahai-default-salt")
        anon = self.adapter.anonymize(transitions, salt=salt)
        payload = self.adapter.to_json_records(anon)
        batch = self.batch_manager.create_batch(payload)

        return {
            "ok": True,
            "batch_id": batch.batch_id,
            "sample_count": batch.sample_count,
            "status": batch.status,
        }

    def sync_pending_once(self) -> Dict[str, Any]:
        fl_cfg = self._fl_cfg()
        if not bool(fl_cfg.get("enabled", False)):
            return {"ok": False, "reason": "fl_disabled"}
        if not bool(fl_cfg.get("upload_enabled", False)):
            return {"ok": False, "reason": "upload_disabled"}

        if not self.batch_manager or not self.client:
            self.bootstrap()
        if not self.batch_manager or not self.client:
            return {"ok": False, "reason": "bootstrap_failed"}

        pending = self.batch_manager.list_pending_batches()
        sent_count = 0
        failed_count = 0

        for batch in pending:
            payload = self.batch_manager.load_batch_payload(batch)
            resp = self.client.submit_batch({"batch_id": batch.batch_id, "samples": payload})
            if bool(resp.get("ok", False)):
                self.batch_manager.mark_sent(batch)
                sent_count += 1
            else:
                failed_count += 1

        return {
            "ok": True,
            "pending": len(pending),
            "sent": sent_count,
            "failed": failed_count,
        }

    def _fl_cfg(self) -> Dict[str, Any]:
        raw = self.settings.get("federated_learning", {})
        return raw if isinstance(raw, dict) else {}

    def _log(self, level: str, msg: str) -> None:
        if not self.logger:
            return
        fn = getattr(self.logger, level, None)
        if callable(fn):
            fn(msg)
