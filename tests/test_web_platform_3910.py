from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from web_platform.contracts import CandleContract, CandleSnapshotContract, PlatformContract
from web_platform.feature_inventory import load_feature_inventory
from web_platform.gateway import create_gateway_app
from web_platform.market_data import BinancePublicMarketData, PublicMarketDataError


TOKEN = "test-gateway-token-that-is-at-least-32-characters"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeMarketData:
    def get_spot_candles(self, symbol: str, interval: str, limit: int):
        return CandleSnapshotContract(
            source="binance",
            symbol=symbol.upper(),
            interval=interval,
            candles=[
                CandleContract(
                    source="binance",
                    market_type="spot",
                    symbol=symbol.upper(),
                    interval=interval,
                    open_time=1,
                    close_time=2,
                    open=1,
                    high=3,
                    low=0.5,
                    close=2,
                    volume=10,
                    closed=True,
                    sequence=0,
                )
            ],
        )


def test_feature_inventory_is_versioned_unique_and_read_only():
    load_feature_inventory.cache_clear()
    inventory = load_feature_inventory()

    assert inventory["release_version"] == "3.9.1.0"
    assert inventory["transition_mode"] == "read_only_parallel"
    assert inventory["commands_enabled"] is False
    assert {service["id"] for service in inventory["services"]} == {
        "blockchain",
        "stock",
        "portfolio",
        "personal_finance",
        "ai_analyst",
    }

    feature_ids = [
        feature["id"]
        for service in inventory["services"]
        for feature in service["features"]
    ]
    assert len(feature_ids) == len(set(feature_ids))


def test_contracts_reject_unknown_fields_and_commands_remain_disabled():
    contract = PlatformContract(release_version="3.9.1.0", release_label="v3.9.1.0 test")
    assert contract.commands_enabled is False
    assert contract.gateway_mode == "read_only"

    with pytest.raises(ValidationError):
        PlatformContract(
            release_version="3.9.1.0",
            release_label="v3.9.1.0 test",
            unsafe_command=True,
        )


def test_gateway_requires_strong_token():
    with pytest.raises(ValueError, match="at least 32"):
        create_gateway_app(token="too-short")


def test_gateway_read_only_auth_origin_and_runtime_contract():
    app = create_gateway_app(
        token=TOKEN,
        runtime_provider=lambda: {
            "status": "ready",
            "service": "blockchain",
            "selected_source": "binance",
            "enabled_sources": ["binance", "upbit"],
            "running_sources": ["binance"],
            "paper_trading": True,
            "live_trading": False,
            "reason": "legacy_runtime_snapshot",
        },
        market_data=FakeMarketData(),
    )
    client = TestClient(app)

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["mode"] == "read_only_parallel"

    assert client.get("/api/v1/platform").status_code == 401
    assert client.get("/api/v1/platform", headers=AUTH).status_code == 200
    runtime = client.get("/api/v1/runtime/snapshot", headers=AUTH)
    assert runtime.status_code == 200
    assert runtime.json()["running_sources"] == ["binance"]

    features = client.get("/api/v1/features", headers=AUTH)
    assert features.status_code == 200
    assert features.json()["commands_enabled"] is False

    assert client.post("/api/v1/platform", headers=AUTH).status_code == 405
    forbidden = client.get(
        "/api/v1/platform",
        headers={**AUTH, "Origin": "https://attacker.example"},
    )
    assert forbidden.status_code == 403

    candles = client.get(
        "/api/v1/market/candles?source=binance&symbol=btcusdt&interval=1m&limit=30",
        headers=AUTH,
    )
    assert candles.status_code == 200
    assert candles.json()["symbol"] == "BTCUSDT"
    assert candles.json()["candles"][0]["closed"] is True
    assert client.get(
        "/api/v1/market/candles?source=unknown",
        headers=AUTH,
    ).status_code == 400


def test_gateway_websocket_authenticates_in_first_message_not_url():
    app = create_gateway_app(token=TOKEN, market_data=FakeMarketData())
    client = TestClient(app)

    with client.websocket_connect("/api/v1/events", headers={"Origin": "http://127.0.0.1:5173"}) as ws:
        ws.send_json({"token": TOKEN})
        event = ws.receive_json()
        assert event["event_type"] == "gateway.ready"
        assert event["payload"]["commands_enabled"] is False
        assert "token" not in json.dumps(event)


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return [[1000, "10", "12", "9", "11", "7.5", 2000, "0", 0, "0", "0", "0"]]


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        return FakeResponse()


def test_binance_market_data_validates_normalizes_and_caches():
    session = FakeSession()
    provider = BinancePublicMarketData(session=session, ttl_seconds=60)

    first = provider.get_spot_candles("btcusdt", "1m", 20)
    second = provider.get_spot_candles("BTCUSDT", "1m", 20)

    assert first == second
    assert len(session.calls) == 1
    assert first.candles[0].open == 10
    assert first.candles[0].close == 11
    assert first.candles[0].sequence == 0

    with pytest.raises(ValueError, match="symbol"):
        provider.get_spot_candles("BTC/USDT", "1m", 20)
    with pytest.raises(ValueError, match="interval"):
        provider.get_spot_candles("BTCUSDT", "7m", 20)


class InvalidResponse(FakeResponse):
    def json(self):
        return {"unexpected": True}


class InvalidSession(FakeSession):
    def get(self, url, *, params, timeout):
        return InvalidResponse()


def test_binance_market_data_rejects_invalid_payload():
    provider = BinancePublicMarketData(session=InvalidSession())
    with pytest.raises(PublicMarketDataError, match="invalid_payload"):
        provider.get_spot_candles("BTCUSDT", "1m", 20)
