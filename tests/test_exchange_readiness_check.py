#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_classify_result_missing_credentials():
    from scripts import exchange_readiness_check as readiness

    result = readiness.classify_result({
        "exchange": "bitget",
        "key_ready": False,
        "validate": False,
        "balance_status": "unknown",
        "balance_message": "",
    })

    assert result["root_cause"] == "missing_credentials"


def test_classify_result_client_unavailable():
    from scripts import exchange_readiness_check as readiness

    result = readiness.classify_result({
        "exchange": "bitget",
        "key_ready": True,
        "validate": False,
        "balance_status": "client_unavailable",
        "balance_message": "bitget client missing",
    })

    assert result["root_cause"] == "client_unavailable"


def test_classify_result_permission_denied():
    from scripts import exchange_readiness_check as readiness

    result = readiness.classify_result({
        "exchange": "okx",
        "key_ready": True,
        "validate": False,
        "balance_status": "error",
        "balance_message": "permission denied for account access",
    })

    assert result["root_cause"] == "permission_denied"


def test_classify_result_ready():
    from scripts import exchange_readiness_check as readiness

    result = readiness.classify_result({
        "exchange": "binance",
        "key_ready": True,
        "validate": True,
        "balance_status": "success",
        "balance_message": "",
    })

    assert result["root_cause"] == "ready"


def test_check_one_adds_classification():
    from scripts import exchange_readiness_check as readiness

    class FakeManager:
        def __init__(self, settings):
            self.settings = settings

        def validate_exchange_connection(self, exchange):
            return False

        def get_exchange_balance(self, exchange, force_refresh=True):
            return {"status": "client_unavailable", "error": "ccxt missing"}

    with patch.object(readiness, "ExchangeManager", FakeManager):
        result = readiness.check_one(
            {"bitget_api_key": "a", "bitget_secret_key": "b", "bitget_password": "c"},
            "bitget",
        )

    assert result["root_cause"] == "client_unavailable"
    assert "클라이언트" in result["action"]