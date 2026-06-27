#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from trading.federated_learning_manager import FederatedLearningDataManager


def test_batch_lifecycle(tmp_path):
    mgr = FederatedLearningDataManager(base_dir=str(tmp_path / "fl"))
    payload = [{"transition_id": "t_1"}, {"transition_id": "t_2"}]

    batch = mgr.create_batch(payload)
    pending = mgr.list_pending_batches()
    assert len(pending) == 1
    assert pending[0].batch_id == batch.batch_id

    loaded = mgr.load_batch_payload(batch)
    assert len(loaded) == 2

    sent_path = mgr.mark_sent(batch)
    assert sent_path.endswith(".json")
    assert mgr.list_pending_batches() == []
