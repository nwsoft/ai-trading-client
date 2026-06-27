#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from trading.federated_learning_preparation import FederatedLearningPreparationService


def test_bootstrap_and_disabled_paths(tmp_path):
    settings = {
        "federated_learning": {
            "enabled": False,
            "batch_enabled": False,
            "upload_enabled": False,
            "server_base_url": "",
        }
    }
    svc = FederatedLearningPreparationService(settings=settings, db_path=str(tmp_path / "trading.db"))

    boot = svc.bootstrap()
    assert boot["ok"] is True
    assert boot["enabled"] is False

    batch = svc.prepare_batch_once(limit=10)
    assert batch["ok"] is False
    assert batch["reason"] == "fl_disabled"

    sync = svc.sync_pending_once()
    assert sync["ok"] is False
    assert sync["reason"] == "fl_disabled"
