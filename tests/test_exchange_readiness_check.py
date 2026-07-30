#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import logging
from pathlib import Path
from types import SimpleNamespace
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


def test_balance_connect_failure_preserves_authentication_root_cause():
    from trading.exchange_manager import ExchangeManager

    class InvalidKeyClient:
        is_connected = False
        last_error = "API key is invalid"
        last_auth_guidance = "API 키 상태와 권한을 확인하세요."

        @staticmethod
        def connect():
            return False

    manager = object.__new__(ExchangeManager)
    manager.logger = logging.getLogger("test.exchange_manager")
    manager.invalid_api_keys = set()
    manager._get_or_create_exchange_client = lambda _exchange: InvalidKeyClient()

    result = manager._get_ccxt_balance("bybit", force_refresh=True)

    assert result["status"] == "invalid_api_keys"
    assert "bybit" in manager.invalid_api_keys


def test_balance_empty_adapter_result_does_not_become_false_success():
    from trading.exchange_manager import ExchangeManager

    class InvalidIpClient:
        is_connected = True
        last_error = ""
        last_auth_guidance = ""

        def get_balance(self):
            self.last_error = "Invalid IP address"
            self.last_auth_guidance = "API 키의 IP 접근 정책을 확인하세요."
            return {}

        def get_account_info(self):
            return {}

    manager = object.__new__(ExchangeManager)
    manager.logger = logging.getLogger("test.exchange_manager")
    manager.invalid_api_keys = set()
    manager.balance_cache = {}
    manager.last_balance_update = {}
    manager._get_or_create_exchange_client = lambda _exchange: InvalidIpClient()

    result = manager._get_ccxt_balance("bitget", force_refresh=True)

    assert result["status"] == "invalid_api_keys"
    assert "bitget" in manager.invalid_api_keys
    assert "bitget_balance" not in manager.balance_cache


def test_balance_empty_adapter_result_is_not_cached_as_success():
    from trading.exchange_manager import ExchangeManager

    class EmptyClient:
        is_connected = True
        last_error = ""
        last_auth_guidance = ""

        @staticmethod
        def get_balance():
            return {}

        @staticmethod
        def get_account_info():
            return {}

    manager = object.__new__(ExchangeManager)
    manager.logger = logging.getLogger("test.exchange_manager")
    manager.invalid_api_keys = set()
    manager.balance_cache = {}
    manager.last_balance_update = {}
    manager._get_or_create_exchange_client = lambda _exchange: EmptyClient()

    result = manager._get_ccxt_balance("okx", force_refresh=True)

    assert result["status"] == "empty_response"
    assert "okx_balance" not in manager.balance_cache


def test_binance_adapter_delegates_account_runtime_features():
    from trading.exchanges.adapters.binance_futures_adapter import BinanceFuturesAdapter

    class FakeBinanceClient:
        @staticmethod
        def get_positions():
            return [
                SimpleNamespace(
                    symbol="BTCUSDT",
                    side="LONG",
                    size=0.1,
                    entry_price=1.0,
                    mark_price=2.0,
                    unrealized_pnl=0.1,
                    liquidation_price=0.5,
                    leverage=7,
                    margin_type="isolated",
                )
            ]

        @staticmethod
        def get_open_orders(symbol):
            return [{"id": "open-1", "symbol": symbol}]

        @staticmethod
        def get_trade_history(symbol, limit):
            return [{"id": "trade-1", "symbol": symbol, "limit": limit}]

        @staticmethod
        def get_recent_trades(symbol, limit):
            return [{"id": "recent-1", "symbol": symbol, "limit": limit}]

        @staticmethod
        def set_leverage(symbol, leverage):
            return symbol == "BTCUSDT" and leverage == 7

        @staticmethod
        def set_margin_type(symbol, margin_type):
            return symbol == "BTCUSDT" and margin_type == "CROSSED"

        @staticmethod
        def futures_funding_rate(symbol, limit=1):
            return [{"symbol": symbol, "fundingRate": "0.0001"}]

    adapter = BinanceFuturesAdapter("key", "secret")
    adapter.client = FakeBinanceClient()
    adapter.is_connected = True

    assert adapter.get_positions()[0]["symbol"] == "BTCUSDT"
    assert adapter.get_open_orders("BTCUSDT")[0]["id"] == "open-1"
    assert adapter.get_trade_history("BTCUSDT", 3)[0]["limit"] == 3
    assert adapter.get_trade_history(None, 2)[0]["id"] == "recent-1"
    assert adapter.set_leverage("BTCUSDT", 7) is True
    assert adapter.get_leverage("BTCUSDT") == 7
    assert adapter.set_margin_type("BTCUSDT", "cross") is True
    assert adapter.get_funding_rate("BTCUSDT") == 0.0001


def test_readiness_resolves_explicit_account_without_hardcoded_user():
    from scripts import exchange_readiness_check as readiness

    path = readiness.resolve_settings_path(account="260729_Teayu_02")

    assert path == (
        ROOT / "data" / "260729_Teayu_02" / "config" / "settings.json"
    ).resolve()
