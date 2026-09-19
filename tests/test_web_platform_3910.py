from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from web_platform.application_services import (
    ALL_EDITABLE_SETTINGS,
    ApplicationServices,
    DetachedRuntimeBridge,
    _read_tail_lines,
    _read_path,
    _validate_setting,
    sanitize_settings,
)
from web_platform.contracts import CandleContract, CandleSnapshotContract, PlatformContract
from web_platform.feature_inventory import load_feature_inventory
from web_platform.gateway import create_gateway_app
from web_platform.market_data import BinancePublicMarketData, MultiSourcePublicMarketData, PublicMarketDataError
from web_platform.query_services import AccountQueryService
from web_platform.runtime_bridge import HeadlessRuntimeBridge, LazyLegacyRuntimeBridge
from web_platform.headless_runtime import HeadlessTradingRuntime
from web_platform.credential_contract import credential_value_present
from web_platform.interactive_ai import InteractiveAIService
from web_platform.public_stock_data import PublicKoreanStockData
from trading.stock_runtime_controller import StockRuntimeController
from config.app_version import RELEASE_VERSION


TOKEN = "test-gateway-token-that-is-at-least-32-characters"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
ROOT = Path(__file__).resolve().parents[1]


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


class FakePublicStockResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakePublicStockSession:
    def get(self, url, **_kwargs):
        if "/index/" in url:
            return FakePublicStockResponse({"indexName": "KOSPI", "closePrice": "3,250.10", "fluctuationsRatio": "+0.42%"})
        return FakePublicStockResponse({"stockName": "삼성전자", "closePrice": "84,700", "fluctuationsRatio": "+1.25%", "accumulatedTradingVolume": "12,345,678"})


def test_public_stock_overview_matches_legacy_read_only_naver_contract():
    provider = PublicKoreanStockData(session=FakePublicStockSession(), ttl_seconds=60)
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge(), public_stock_data=provider)
    client = TestClient(create_gateway_app(token=TOKEN, application_services=services))

    response = client.get("/api/v1/market/stock-overview?symbols=005930", headers=AUTH)

    assert response.status_code == 200
    payload = response.json()
    assert payload["quotes"][0]["name"] == "삼성전자"
    assert payload["quotes"][0]["price"] == 84700
    assert payload["quotes"][0]["change"] == pytest.approx(1.25)
    assert len(payload["indices"]) == 2
    assert [row["symbol"] for row in payload["indices"]] == ["KOSPI", "KOSDAQ"]
    assert payload["account_data"] is False
    assert payload["order_capability"] is False


def test_strategy_mentor_and_final_draft_validation_are_real_gateway_contracts(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())
    client = TestClient(create_gateway_app(token=TOKEN, application_services=services))
    confirmed = {**AUTH, "X-NoahAI-Intent": "confirmed"}

    mentor = client.post(
        "/api/v1/strategies/mentor",
        headers=confirmed,
        json={"profile": {
            "experience_level": "beginner", "asset_class": "crypto", "capital_band": "small",
            "review_frequency": "daily", "trade_frequency": "medium", "leverage_allowed": False,
            "paper_ready": True, "max_loss_percent": 0.5,
        }},
    )
    assert mentor.status_code == 200
    assert len(mentor.json()["candidates"]) in {2, 3}
    assert mentor.json()["auto_saved"] is False

    invalid = client.post(
        "/api/v1/strategies/draft-validation",
        headers=confirmed,
        json={"rules": {
            "entry": "RSI LONG", "exit": "TP/SL", "stop_loss": "1%",
            "take_profit": "2%", "position_size": "75%", "market_conditions": ["range"],
            "signal_mode": "confirm", "entry_signal": "LONG",
            "executable_entry": {"all": [{"field": "rsi", "operator": "lte", "value": 30}]},
            "engine_settings": {"_unit": "percent_points", "tp_percent": 2, "sl_percent": 1, "position_size": 0.75},
            "exit_policy": {"mode": "strategy_owned"},
        }},
    )
    assert invalid.status_code == 200
    assert invalid.json()["ready"] is False
    assert "engine_settings_contract_invalid" in invalid.json()["reasons"]


def test_feature_inventory_is_versioned_unique_and_gated():
    load_feature_inventory.cache_clear()
    inventory = load_feature_inventory()

    assert inventory["release_version"] == RELEASE_VERSION
    assert inventory["transition_mode"] == "internal_full_migration"
    assert inventory["commands_enabled"] is True
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
    feature_ids.extend(feature["id"] for feature in inventory["platform_features"])
    assert len(feature_ids) == len(set(feature_ids))


def test_contracts_reject_unknown_fields_and_commands_are_gated():
    contract = PlatformContract(release_version="3.9.1.0", release_label="v3.9.1.0 test")
    assert contract.commands_enabled is True
    assert contract.gateway_mode == "account_scoped"

    with pytest.raises(ValidationError):
        PlatformContract(
            release_version="3.9.1.0",
            release_label="v3.9.1.0 test",
            unsafe_command=True,
        )


def test_runtime_snapshot_exposes_separate_crypto_and_stock_scopes(monkeypatch):
    bridge = HeadlessRuntimeBridge(account="tester")
    monkeypatch.setattr(
        bridge,
        "_settings",
        lambda: {
            "selected_exchange": "binance",
            "enabled_exchanges": ["binance", "upbit"],
            "enabled_stock_brokers": ["kiwoom", "shinhan"],
            "binance_api_key": "key",
            "binance_secret_key": "secret",
            "stock_broker_configs": {
                "kiwoom": {"id": "tester", "password": "secret", "account_no": "123"},
                "shinhan": {},
            },
            "paper_trading": True,
        },
    )

    snapshot = bridge.snapshot()

    assert snapshot["selected_sources"] == {"blockchain": "binance", "stock": "kiwoom"}
    assert snapshot["enabled_sources_by_service"]["blockchain"] == ["binance", "upbit"]
    assert snapshot["enabled_sources_by_service"]["stock"] == ["kiwoom", "shinhan"]
    assert snapshot["credential_status"]["binance"] is True
    assert snapshot["credential_status"]["upbit"] is False
    assert snapshot["configured_sources_by_service"]["stock"] == ["kiwoom"]


def test_canonical_settings_template_is_saveable_through_web_contract():
    settings = json.loads((ROOT / "config" / "settings_template.json").read_text(encoding="utf-8"))

    for field in ALL_EDITABLE_SETTINGS:
        _validate_setting(field, _read_path(settings, field.path))

    operation_mode = next(field for field in ALL_EDITABLE_SETTINGS if field.path == "operation_mode")
    assert settings["operation_mode"] in operation_mode.options


def test_unconfirmed_legacy_live_profile_can_repair_unrelated_settings(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    stored = json.loads((ROOT / "config" / "settings_template.json").read_text(encoding="utf-8"))
    stored["paper_trading"] = False
    stored["_trade_scope_user_confirmed_v3905"] = False
    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: deepcopy(stored))

    def fake_save(next_settings):
        stored.clear()
        stored.update(deepcopy(next_settings))
        return True

    monkeypatch.setattr(service_module, "save_settings", fake_save)
    monkeypatch.setattr(service_module, "patch_settings_paths", lambda changes: fake_save(_with_setting_paths(stored, changes)))
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())
    snapshot = services.settings_snapshot()

    repaired = services.update_settings(
        expected_revision=snapshot["revision"],
        changes={"log_level": "INFO"},
    )
    assert stored["log_level"] == "INFO"

    with pytest.raises(ValueError, match="PAPER 모드를 해제"):
        services.update_settings(
            expected_revision=repaired["revision"],
            changes={"paper_trading": False},
        )


@pytest.mark.parametrize(
    "config",
    [
        {"account_no": "123"},
        {"id": "tester"},
        {"id": "tester", "password": "********"},
        {"id": "********", "password": "secret"},
    ],
)
def test_incomplete_kiwoom_credentials_never_query_the_runtime(monkeypatch, config):
    runtime_builds = []
    bridge = HeadlessRuntimeBridge(
        account="tester",
        factory=lambda account: runtime_builds.append(account),
    )
    monkeypatch.setattr(
        bridge,
        "_settings",
        lambda: {
            "selected_stock_broker": "kiwoom",
            "enabled_stock_brokers": ["kiwoom"],
            "stock_broker_configs": {"kiwoom": config},
        },
    )

    assert bridge.snapshot()["credential_status"]["kiwoom"] is False
    result = bridge.account_snapshot(sources=["kiwoom"], force_refresh=True)

    assert runtime_builds == []
    assert result["fresh"] is False
    assert result["sources"]["kiwoom"]["status"] == "credential_required"
    assert "설정한 뒤 연결을 확인하세요" in result["sources"]["kiwoom"]["message"]


@pytest.mark.parametrize("value", [None, "", "   ", "***", "••••", "<redacted>", "redacted", "미설정", "not_configured"])
def test_credential_placeholders_never_count_as_configured(value):
    assert credential_value_present(value) is False


def test_runtime_snapshot_fails_closed_for_masked_credentials(monkeypatch):
    bridge = HeadlessRuntimeBridge(account="tester")
    monkeypatch.setattr(
        bridge,
        "_settings",
        lambda: {
            "selected_exchange": "binance",
            "enabled_exchanges": ["binance", "okx"],
            "binance_api_key": "********",
            "binance_secret_key": "********",
            "okx_api_key": "<redacted>",
            "okx_secret_key": "secret",
            "okx_passphrase": "pass",
        },
    )
    snapshot = bridge.snapshot()
    assert snapshot["credential_status"]["binance"] is False
    assert snapshot["credential_status"]["okx"] is False
    assert snapshot["configured_sources_by_service"]["blockchain"] == []


def test_runtime_bridge_coin_selection_reuses_engine_selector(monkeypatch):
    class App:
        def running_crypto_exchanges(self):
            return []

        def select_trading_coins(self):
            return [{"symbol": "BTCUSDT"}, {"coin": "ETHUSDT"}]

    bridge = HeadlessRuntimeBridge(account="tester", factory=lambda account: App())
    monkeypatch.setattr(
        bridge,
        "_settings",
        lambda: {"binance_api_key": "key", "binance_secret_key": "secret"},
    )

    result = bridge.execute("coins.select", {"source": "binance"})

    assert result["selected_count"] == 2
    assert result["execution_eligible_count"] == 2
    assert result["selection_status"] == "scored"
    assert result["selected_symbols"] == ["BTCUSDT", "ETHUSDT"]


@pytest.mark.parametrize(
    ("rows", "expected_status", "expected_eligible"),
    [
        (
            [{"symbol": "BTCUSDT", "selection_status": "scored_partial"}],
            "scored_partial",
            1,
        ),
        (
            [
                {
                    "symbol": "BTCUSDT",
                    "selection_status": "fallback_unscored",
                    "execution_eligible": False,
                }
            ],
            "data_unavailable",
            0,
        ),
        (
            [
                {
                    "symbol": "BTCUSDT",
                    "selection_status": "stale_unscored",
                    "execution_eligible": False,
                }
            ],
            "stale_data",
            0,
        ),
    ],
)
def test_runtime_bridge_coin_selection_exposes_partial_and_data_unavailable_states(
    monkeypatch,
    rows,
    expected_status,
    expected_eligible,
):
    class App:
        def running_crypto_exchanges(self):
            return []

        def select_trading_coins(self):
            return rows

    bridge = HeadlessRuntimeBridge(account="tester", factory=lambda account: App())
    monkeypatch.setattr(
        bridge,
        "_settings",
        lambda: {"binance_api_key": "key", "binance_secret_key": "secret"},
    )

    result = bridge.execute("coins.select", {"source": "binance"})

    assert result["selection_status"] == expected_status
    assert result["execution_eligible_count"] == expected_eligible


def test_runtime_bridge_coin_analysis_reuses_engine_analyzer_without_order(monkeypatch):
    class Analyzer:
        def analyze_symbol(self, symbol):
            assert symbol == "BTCUSDT"
            return {
                "symbol": symbol,
                "signal": "LONG",
                "confidence": 0.82,
                "current_price": 123.45,
                "reasoning": "live engine result",
            }

    class App:
        analyzer = Analyzer()

    bridge = HeadlessRuntimeBridge(account="tester", factory=lambda account: App())
    monkeypatch.setattr(
        bridge,
        "_settings",
        lambda: {"binance_api_key": "key", "binance_secret_key": "secret"},
    )

    result = bridge.execute("coins.analyze", {"source": "binance", "symbol": "btc"})

    assert result["symbol"] == "BTCUSDT"
    assert result["analysis"]["signal"] == "LONG"
    assert result["analysis"]["confidence"] == pytest.approx(0.82)
    assert result["read_only"] is True
    assert result["order_submitted"] is False


def test_runtime_bridge_trade_import_reuses_execution_history_store(monkeypatch):
    class Client:
        def get_recent_trades(self, symbol=None, limit=0):
            assert symbol is None
            assert limit == 200
            return [{"id": "trade-1", "symbol": "BTCUSDT"}]

    class Manager:
        def get_exchange_client(self, source):
            assert source == "binance"
            return Client()

    class Recorder:
        def save_exchange_execution_history(self, exchange, rows, **kwargs):
            assert exchange == "binance"
            assert rows == [{"id": "trade-1", "symbol": "BTCUSDT"}]
            assert kwargs["source"] == "web_dashboard_exchange_sync"
            return {"received": 1, "inserted": 1, "skipped": 0}

    class App:
        exchange_manager = Manager()
        recorder = Recorder()

        def running_crypto_exchanges(self):
            return []

    bridge = HeadlessRuntimeBridge(account="tester", factory=lambda account: App())
    monkeypatch.setattr(
        bridge,
        "_settings",
        lambda: {"binance_api_key": "key", "binance_secret_key": "secret"},
    )

    result = bridge.execute("trades.import", {"source": "binance"})

    assert result["received"] == 1
    assert result["inserted"] == 1
    assert result["skipped"] == 0


def test_log_snapshot_never_leaks_crypto_records_into_stock_service(tmp_path, monkeypatch):
    today = datetime.now().astimezone().date().isoformat()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "trading.log").write_text(
        f"{today} INFO crypto (ex=binance)\n"
        f"{today} INFO stock (ex=kiwoom)\n"
        f"{today} INFO 증권 계좌 확인 (ex=global)\n"
        f"{today} INFO Binance USDT scan (ex=global)\n"
        f"{today} INFO unscoped startup\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("web_platform.application_services.get_log_dir", lambda: str(log_dir))
    monkeypatch.setattr("web_platform.application_services.get_log_file_path", lambda: str(log_dir / "trading.log"))
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())

    stock = services.log_snapshot(service="stock", source="all", lines=50)
    blockchain = services.log_snapshot(service="blockchain", source="all", lines=50)

    assert [row["message"] for row in stock["lines"]] == [
        f"{today} INFO stock (ex=kiwoom)",
        f"{today} INFO 증권 계좌 확인 (ex=global)",
    ]
    assert all("ex=kiwoom" not in row["message"] for row in blockchain["lines"])
    assert all("증권 계좌" not in row["message"] for row in blockchain["lines"])
    assert any("ex=binance" in row["message"] for row in blockchain["lines"])
    assert any("Binance USDT" in row["message"] for row in blockchain["lines"])


def test_log_snapshot_uses_only_the_current_legacy_log_file_for_each_surface(tmp_path, monkeypatch):
    today = datetime.now().astimezone().date().isoformat()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "trading.log").write_text(
        f"{today} 15:14:19 | INFO | global current (ex=binance)\n",
        encoding="utf-8",
    )
    (log_dir / "trading.log.1").write_text(
        "2025-12-27 14:40:28 | INFO | rotated stale (ex=binance)\n",
        encoding="utf-8",
    )
    (log_dir / "trading_binance.log").write_text(
        f"{today} 15:14:20 | INFO | binance current (ex=binance)\n"
        f"{today} 15:14:20 | INFO | binance current (ex=binance)\n",
        encoding="utf-8",
    )
    (log_dir / "trading_upbit.log").write_text(
        f"{today} 15:14:21 | INFO | upbit current (ex=upbit)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("web_platform.application_services.get_log_dir", lambda: str(log_dir))
    monkeypatch.setattr("web_platform.application_services.get_log_file_path", lambda: str(log_dir / "trading.log"))
    monkeypatch.setattr("web_platform.application_services.get_exchange_log_file_path", lambda source: str(log_dir / f"trading_{source}.log"))
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())

    global_messages = [row["message"] for row in services.log_snapshot(service="blockchain", source="all", lines=50)["lines"]]
    binance_messages = [row["message"] for row in services.log_snapshot(service="blockchain", source="binance", lines=50)["lines"]]
    missing_messages = [row["message"] for row in services.log_snapshot(service="blockchain", source="bithumb", lines=50)["lines"]]

    assert global_messages == [f"{today} 15:14:19 | INFO | global current (ex=binance)"]
    assert binance_messages == [f"{today} 15:14:20 | INFO | binance current (ex=binance)"]
    assert missing_messages == []


def test_realtime_log_reader_seeks_only_recent_physical_lines_and_emits_filter_metadata(tmp_path, monkeypatch):
    today = datetime.now().astimezone().date().isoformat()
    log_path = tmp_path / "trading_binance.log"
    rows = [f"{today} 12:00:{index % 60:02d} | INFO | old {index} (ex=binance)" for index in range(3000)]
    rows.extend([
        f"{today} 13:00:00 | DEBUG | RSI 분석 시작 (ex=binance)",
        f"{today} 13:00:01 | ERROR | 주문 실패 (ex=binance)",
    ])
    log_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    assert _read_tail_lines(log_path, 2) == rows[-2:]
    monkeypatch.setattr(
        "web_platform.application_services.get_exchange_log_file_path",
        lambda source: str(log_path),
    )
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())
    snapshot = services.log_snapshot(service="blockchain", source="binance", lines=10)

    analysis = next(row for row in snapshot["lines"] if "RSI 분석" in row["message"])
    order = next(row for row in snapshot["lines"] if "주문 실패" in row["message"])
    assert (analysis["level"], analysis["exchange"], analysis["category"]) == ("DEBUG", "binance", "analysis")
    assert (order["level"], order["exchange"], order["category"]) == ("ERROR", "binance", "trade")


def test_realtime_log_snapshot_hides_retained_rows_from_previous_days(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    today = datetime.now().astimezone().date().isoformat()
    (log_dir / "trading.log").write_text(
        "2025-12-27 14:40:28 | INFO | retained audit row (ex=binance)\n"
        f"{today} 15:14:19 | INFO | current row (ex=binance)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("web_platform.application_services.get_log_file_path", lambda: str(log_dir / "trading.log"))
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())

    messages = [row["message"] for row in services.log_snapshot(service="blockchain", source="all", lines=50)["lines"]]

    assert messages == [f"{today} 15:14:19 | INFO | current row (ex=binance)"]


def test_realtime_log_snapshot_uses_latest_session_boundary(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    today = datetime.now().astimezone().date().isoformat()
    (log_dir / "trading.log").write_text(
        f"{today} 09:00:00 | INFO | earlier launch row\n"
        f"{today} 12:00:00 | INFO | 로그 초기화 완료 — level=INFO, file=trading.log\n"
        f"{today} 12:00:01 | INFO | 로그인 성공, 백엔드 승인 완료\n"
        f"{today} 12:00:02 | INFO | current launch row\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("web_platform.application_services.get_log_file_path", lambda: str(log_dir / "trading.log"))
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())

    messages = [row["message"] for row in services.log_snapshot(service="blockchain", source="all", lines=50)["lines"]]

    assert all("earlier launch row" not in message for message in messages)
    assert messages == [
        f"{today} 12:00:00 | INFO | 로그 초기화 완료 — level=INFO, file=trading.log",
        f"{today} 12:00:01 | INFO | 로그인 성공, 백엔드 승인 완료",
        f"{today} 12:00:02 | INFO | current launch row",
    ]


def test_log_snapshot_filters_before_applying_visible_line_limit(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    today = datetime.now().astimezone().date().isoformat()
    rows = [f"{today} 15:00:00 | INFO | matching crypto row (ex=binance)"]
    rows.extend(
        f"{today} 15:00:{index:02d} | INFO | stock burst {index} (ex=kiwoom)"
        for index in range(20)
    )
    (log_dir / "trading.log").write_text("\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setattr("web_platform.application_services.get_log_file_path", lambda: str(log_dir / "trading.log"))
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())

    messages = [
        row["message"]
        for row in services.log_snapshot(service="blockchain", source="all", lines=10)["lines"]
    ]

    assert messages == [f"{today} 15:00:00 | INFO | matching crypto row (ex=binance)"]


def test_mixed_account_refresh_is_not_fresh_when_one_requested_source_needs_credentials():
    class Manager:
        def get_exchange_balance(self, source, force_refresh=False):
            return {"status": "success", "balance": {"USDT": 123}}

        def get_exchange_client(self, source):
            return None

    class App:
        exchange_manager = Manager()

        def running_crypto_exchanges(self):
            return []

    bridge = HeadlessRuntimeBridge(account="tester", factory=lambda account: App())
    bridge._settings = lambda: {
        "binance_api_key": "key",
        "binance_secret_key": "secret",
        "enabled_exchanges": ["binance", "upbit"],
    }

    snapshot = bridge.account_snapshot(sources=["binance", "upbit"], force_refresh=True)

    assert snapshot["sources"]["binance"]["status"] == "success"
    assert snapshot["sources"]["upbit"]["status"] == "credential_required"
    assert snapshot["fresh"] is False


@pytest.mark.parametrize(
    ("service", "source"),
    [
        *[("blockchain", source) for source in ("binance", "upbit", "bithumb", "bybit", "okx", "bitget")],
        *[("stock", source) for source in ("kiwoom", "shinhan", "mirae", "kis")],
    ],
)
def test_every_missing_source_credential_blocks_runtime_and_account_calls(monkeypatch, service, source):
    runtime_builds = []
    bridge = HeadlessRuntimeBridge(account="tester", factory=lambda account: runtime_builds.append(account))
    monkeypatch.setattr(
        bridge,
        "_settings",
        lambda: {
            "enabled_exchanges": ["binance", "upbit", "bithumb", "bybit", "okx", "bitget"],
            "enabled_stock_brokers": ["kiwoom", "shinhan", "mirae", "kis"],
            "stock_broker_configs": {},
        },
    )

    snapshot = bridge.snapshot()
    result = bridge.account_snapshot(sources=[source], force_refresh=True)

    assert snapshot["credential_status"][source] is False
    assert runtime_builds == []
    assert result["fresh"] is False
    assert result["sources"][source]["status"] == "credential_required"
    assert "API 키를 설정한 뒤 연결을 확인하세요" in result["sources"][source]["message"]


@pytest.mark.parametrize(
    ("service", "source", "file_source", "other"),
    [
        ("blockchain", "binance", "binance", "upbit"),
        ("blockchain", "upbit", "upbit", "binance"),
        ("blockchain", "bithumb", "bithumb", "bybit"),
        ("blockchain", "bybit", "bybit", "bithumb"),
        ("blockchain", "okx", "okx", "bitget"),
        ("blockchain", "bitget", "bitget", "okx"),
        ("stock", "kiwoom", "kiwoom", "shinhan"),
        ("stock", "shinhan", "shinhan", "kiwoom"),
        ("stock", "mirae", "miraeAsset", "kis"),
        ("stock", "kis", "koreaInvestment", "miraeasset"),
    ],
)
def test_every_source_log_reads_only_its_current_authoritative_file(
    tmp_path, monkeypatch, service, source, file_source, other,
):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    today = datetime.now().astimezone().date().isoformat()
    own_path = log_dir / f"trading_{file_source}.log"
    own_path.write_text(
        f"{today} 16:00:00 | INFO | own row (ex={source})\n"
        f"{today} 16:00:01 | INFO | foreign row (ex={other})\n"
        f"{today} 16:00:00 | INFO | own row (ex={source})\n",
        encoding="utf-8",
    )
    (log_dir / f"trading_{source}.log.1").write_text(
        f"2025-12-27 14:40:28 | INFO | rotated row (ex={source})\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "web_platform.application_services.get_exchange_log_file_path",
        lambda requested: str(log_dir / f"trading_{requested}.log"),
    )
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())

    messages = [row["message"] for row in services.log_snapshot(service=service, source=source, lines=50)["lines"]]

    assert messages == [f"{today} 16:00:00 | INFO | own row (ex={source})"]
    assert all(f"ex={other}" not in message for message in messages)
    assert all("2025-12-27" not in message for message in messages)


@pytest.mark.parametrize(
    ("service", "source"),
    [("blockchain", "kiwoom"), ("blockchain", "kis"), ("stock", "binance"), ("stock", "upbit")],
)
def test_log_and_workspace_reject_cross_service_source_requests(tmp_path, service, source):
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())
    with pytest.raises(ValueError, match="현재 서비스에 속하지 않는 로그 범위"):
        services.log_snapshot(service=service, source=source)

    queries = AccountQueryService(str(tmp_path / "missing.db"))
    with pytest.raises(ValueError, match="workspace_source_service_mismatch"):
        queries.workspace(service, f"{service}.source_workspaces", source=source)


def test_workspace_gateway_rejects_feature_owned_by_another_service():
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())
    client = TestClient(create_gateway_app(token=TOKEN, application_services=services))

    response = client.get(
        "/api/v1/workspaces/stock/blockchain.coin_info",
        headers=AUTH,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "workspace_feature_service_mismatch"


def test_ai_analyst_workspace_uses_all_assets_without_a_binance_default(tmp_path):
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE trade_log (symbol TEXT, exchange TEXT, asset_type TEXT, pnl REAL, entry_time TEXT, exit_time TEXT)"
        )
        connection.executemany(
            "INSERT INTO trade_log VALUES (?, ?, ?, ?, '2026-08-15 10:00:00', '2026-08-15 10:05:00')",
            [
                ("BTCUSDT", "binance", "crypto", 10),
                ("005930", "kiwoom", "stock", 2000),
            ],
        )

    workspace = AccountQueryService(str(db_path)).workspace(
        "ai_analyst", "ai_analyst.workspace",
    )

    assert workspace["trading"]["closed_count"] == 2
    assert {row["asset_class"] for row in workspace["trading"]["recent_trades"]} == {"crypto", "stock"}
    assert workspace["source"] == ""
    assert workspace["data_scope"] == {
        "mode": "account_all_assets", "unscoped_records_included": True,
    }


def test_personal_finance_workspace_uses_life_finance_store_not_trading_store(tmp_path, monkeypatch):
    monkeypatch.setattr("web_platform.application_services.get_app_data_dir", lambda: str(tmp_path))
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())

    workspace = services.workspace_snapshot(
        service="personal_finance", feature="personal_finance.service",
    )

    assert workspace["service"] == "personal_finance"
    assert workspace["source"] == "life_finance_manager"
    assert "life_finance" in workspace
    assert "trading" not in workspace
    assert "selected_coins" not in workspace


def test_in_app_manual_reads_the_packaged_legacy_section_contract(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    sections = [
        {"id": f"section-{index}", "label": f"탭 {index}", "content": "정본 기능 설명입니다. " * 20, "legacy_method": f"method_{index}"}
        for index in range(11)
    ]
    payload = {
        "schema_version": "1.0.0",
        "release_version": "3.9.1.0",
        "source": "ui/widgets/user_manual_widget.py",
        "source_sha256": "abc123",
        "sections": sections,
    }
    (docs_dir / "USER_MANUAL_SECTIONS.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("web_platform.application_services.get_app_base_dir", lambda: str(tmp_path))

    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())
    snapshot = services.manual_snapshot()

    assert snapshot["source"] == "docs/USER_MANUAL_SECTIONS.json"
    assert snapshot["source_reference"] == "ui/widgets/user_manual_widget.py"
    assert snapshot["source_sha256"] == "abc123"
    assert snapshot["sections"] == sections
    assert "# 탭 0" in snapshot["content"]

    client = TestClient(create_gateway_app(token=TOKEN, application_services=services))
    response = client.get("/api/v1/manual", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["sections"] == sections
    assert response.json()["content"] == snapshot["content"]


def test_stock_info_does_not_relabel_legacy_selected_coins(tmp_path):
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE selected_coins (id INTEGER PRIMARY KEY, symbol TEXT, overall_score REAL, created_at TEXT)"
        )
        connection.execute(
            "INSERT INTO selected_coins(symbol, overall_score, created_at) VALUES ('BTCUSDT', 99, '2026-08-15')"
        )
    queries = AccountQueryService(str(db_path))

    crypto = queries.workspace("blockchain", "blockchain.coin_info")
    stock = queries.workspace("stock", "stock.info")

    assert crypto["selected_coins"][0]["symbol"] == "BTCUSDT"
    assert stock["selected_coins"] == []
    assert stock["data_status"] == "stock_candidate_store_unavailable"


def test_selected_coin_workspace_returns_only_latest_exchange_session(tmp_path):
    from trading.recorder import Recorder

    db_path = tmp_path / "trading.db"
    log_path = tmp_path / "logs"
    recorder = Recorder(db_path=str(db_path), log_path=str(log_path), exchange="binance")
    recorder.save_coin_selection(
        [{"symbol": "BTCUSDT", "is_major": True, "overall_score": 71.5}],
        num_alt=0,
        num_major=1,
        market_regime="normal",
        exchange="binance",
    )
    recorder.save_coin_selection(
        [{"symbol": "ETHUSDT", "is_major": True, "overall_score": 82.0}],
        num_alt=0,
        num_major=1,
        market_regime="bull",
        exchange="binance",
    )
    recorder.save_coin_selection(
        [{"symbol": "BTC/USDT:USDT", "is_major": True, "overall_score": 65.0}],
        num_alt=0,
        num_major=1,
        market_regime="normal",
        exchange="okx",
    )

    queries = AccountQueryService(str(db_path))
    binance = queries.workspace("blockchain", "blockchain.coin_info", source="binance")
    okx = queries.workspace("blockchain", "blockchain.coin_info", source="okx")

    assert [row["symbol"] for row in binance["selected_coins"]] == ["ETHUSDT"]
    assert binance["selected_coins"][0]["exchange"] == "binance"
    assert [row["symbol"] for row in okx["selected_coins"]] == ["BTC/USDT:USDT"]


def test_legacy_unscoped_selected_coins_are_not_attributed_to_binance(tmp_path):
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE selected_coins (id INTEGER PRIMARY KEY, session_id INTEGER, symbol TEXT, "
            "exchange TEXT NOT NULL DEFAULT 'legacy_unscoped', overall_score REAL)"
        )
        connection.execute(
            "INSERT INTO selected_coins(session_id, symbol, overall_score) VALUES (1, 'BTCUSDT', 99)"
        )

    workspace = AccountQueryService(str(db_path)).workspace(
        "blockchain", "blockchain.coin_info", source="binance"
    )

    assert workspace["selected_coins"] == []


def test_trading_overview_counts_only_distinct_noahai_owned_open_positions(tmp_path):
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE trade_log (id INTEGER PRIMARY KEY, symbol TEXT, side TEXT, exchange TEXT, "
            "asset_type TEXT, order_id TEXT, position_owner TEXT, reason TEXT, exit_time TEXT)"
        )
        connection.executemany(
            "INSERT INTO trade_log(symbol, side, exchange, asset_type, order_id, position_owner, reason, exit_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("BTCUSDT", "LONG", "binance", "crypto", "entry-1", "noahai", "AI signal", None),
                ("BTCUSDT", "LONG", "binance", "crypto", "entry-2", "noahai", "AI scale-in", None),
                ("ETHUSDT", "SHORT", "binance", "crypto", "entry-3", "noahai", "AI signal", None),
                ("XRPUSDT", "LONG", "binance", "crypto", "manual-1", "manual", "manual trade", None),
                ("KRW-BTC", "LONG", "upbit", "crypto", "entry-4", "noahai", "AI signal", None),
                ("SOLUSDT", "LONG", "binance", "crypto", "entry-5", "noahai", "AI signal", "2026-08-17"),
            ],
        )

    overview = AccountQueryService(str(db_path)).trading_overview(asset_class="crypto", source="binance")

    assert overview["open_position_count"] == 2


def test_learning_snapshot_summarizes_full_exchange_file_and_maps_legacy_metrics(tmp_path, monkeypatch):
    learning_path = tmp_path / "ai_learning_data_binance.json"
    records = [
        {
            "timestamp": f"2026-06-30T09:{index % 60:02d}:00+00:00",
            "exchange": "binance",
            "symbol": f"COIN{index}USDT",
            "signal": "LONG" if index % 3 == 0 else "SHORT" if index % 3 == 1 else "HOLD",
            "confidence": 0.5,
            "market_volatility": index / 1000,
            "trend_strength": index / 10000,
        }
        for index in range(1849)
    ]
    learning_path.write_text(json.dumps(records), encoding="utf-8")
    monkeypatch.setattr(
        "web_platform.query_services.get_exchange_ai_learning_data_path",
        lambda source: str(learning_path),
    )

    snapshot = AccountQueryService(str(tmp_path / "missing.db")).learning_snapshot(source="binance")

    assert snapshot["summary"]["total_count"] == 1849
    assert len(snapshot["records"]) == 50
    # Volatility and trend strength are not RSI or MACD. Keep original values
    # without relabeling missing indicators as unrelated measurements.
    assert snapshot["records"][-1]["rsi"] is None
    assert snapshot["records"][-1]["macd"] is None
    assert snapshot["records"][-1]["market_volatility"] == pytest.approx(1.848)
    assert snapshot["records"][-1]["trend"] is None
    assert snapshot["records"][-1]["trend_strength"] == pytest.approx(0.1848)
    assert sum(snapshot["summary"]["signal_counts"].values()) == 1849


def test_large_learning_snapshot_reads_recent_pages_and_exposes_more_boundary(tmp_path, monkeypatch):
    learning_path = tmp_path / "ai_learning_data_binance.json"
    records = [
        {
            "timestamp": f"2026-08-23T00:{index % 60:02d}:00+00:00",
            "exchange": "binance",
            "symbol": f"COIN{index}USDT",
            "signal": "LONG",
            "confidence": 0.5,
        }
        for index in range(125)
    ]
    learning_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(AccountQueryService, "LARGE_LEARNING_FILE_BYTES", 1)
    monkeypatch.setattr(
        "web_platform.query_services.get_exchange_ai_learning_data_path",
        lambda source: str(learning_path),
    )
    queries = AccountQueryService(str(tmp_path / "missing.db"))

    latest = queries.learning_snapshot(source="binance", offset=0, limit=50)
    older = queries.learning_snapshot(source="binance", offset=50, limit=50)
    oldest = queries.learning_snapshot(source="binance", offset=100, limit=50)

    assert [row["symbol"] for row in latest["records"]] == [f"COIN{index}USDT" for index in range(75, 125)]
    assert [row["symbol"] for row in older["records"]] == [f"COIN{index}USDT" for index in range(25, 75)]
    assert [row["symbol"] for row in oldest["records"]] == [f"COIN{index}USDT" for index in range(25)]
    assert latest["pagination"] == {
        "offset": 0,
        "limit": 50,
        "returned": 50,
        "has_more": True,
        "total_count": 125,
    }
    assert oldest["pagination"]["has_more"] is False
    assert latest["summary"]["complete"] is False


def test_source_workspace_statistics_and_trades_are_strictly_venue_scoped(tmp_path):
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE trade_log (symbol TEXT, exchange TEXT, asset_type TEXT, pnl REAL, net_pnl REAL, entry_time TEXT, exit_time TEXT, reconciliation_status TEXT)"
        )
        connection.executemany(
            "INSERT INTO trade_log VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("BTCUSDT", "binance", "crypto", 10, 10, "2026-08-15 10:00:00", "2026-08-15 10:05:00", "exchange_confirmed"),
                ("KRW-BTC", "upbit", "crypto", 20, 20, "2026-08-15 11:00:00", "2026-08-15 11:05:00", "exchange_confirmed"),
                ("ETHUSDT", "", "crypto", 999, 999, "2026-08-15 12:00:00", "2026-08-15 12:05:00", "exchange_confirmed"),
            ],
        )
        connection.execute("CREATE TABLE exchange_trade_stats (exchange TEXT, fee REAL, created_at TEXT)")
        connection.executemany(
            "INSERT INTO exchange_trade_stats VALUES (?, ?, ?)",
            [("binance", 1.5, "2026-08-15"), ("upbit", 7.5, "2026-08-15"), ("", 99, "2026-08-15")],
        )
    queries = AccountQueryService(str(db_path))

    binance = queries.workspace("blockchain", "blockchain.source_workspaces", source="binance")
    upbit = queries.workspace("blockchain", "blockchain.source_workspaces", source="upbit")

    assert binance["trading"]["closed_count"] == 1
    assert binance["trading"]["pnl_by_currency"] == {"USDT": 10.0}
    assert [row["fee"] for row in binance["statistics"]] == [1.5]
    assert upbit["trading"]["closed_count"] == 1
    assert upbit["trading"]["pnl_by_currency"] == {"KRW": 20.0}
    assert upbit["data_scope"] == {"mode": "source_strict", "source": "upbit", "unscoped_records_included": False}


@pytest.mark.parametrize("source", ["binance", "upbit", "bithumb", "bybit", "okx", "bitget"])
def test_every_crypto_workspace_excludes_other_and_unscoped_rows(tmp_path, source):
    db_path = tmp_path / "trading.db"
    all_sources = ["binance", "upbit", "bithumb", "bybit", "okx", "bitget"]
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE trade_log (symbol TEXT, exchange TEXT, asset_type TEXT, pnl REAL, entry_time TEXT, exit_time TEXT)"
        )
        connection.executemany(
            "INSERT INTO trade_log VALUES (?, ?, 'crypto', ?, '2026-08-15 10:00:00', '2026-08-15 10:05:00')",
            [(f"{venue.upper()}USDT", venue, index + 1) for index, venue in enumerate(all_sources)]
            + [("UNSCOPEDUSDT", "", 999)],
        )
        connection.execute("CREATE TABLE exchange_trade_stats (exchange TEXT, fee REAL, created_at TEXT)")
        connection.executemany(
            "INSERT INTO exchange_trade_stats VALUES (?, ?, '2026-08-15')",
            [(venue, index + 0.5) for index, venue in enumerate(all_sources)] + [("", 999)],
        )
    workspace = AccountQueryService(str(db_path)).workspace(
        "blockchain", "blockchain.source_workspaces", source=source,
    )

    assert workspace["trading"]["closed_count"] == 1
    assert workspace["trading"]["recent_trades"][0]["exchange"] == source
    assert [row["exchange"] for row in workspace["statistics"]] == [source]
    assert workspace["trading_statistics"]["filter_source"] == source
    assert workspace["data_scope"] == {
        "mode": "source_strict", "source": source, "unscoped_records_included": False,
    }


@pytest.mark.parametrize("source", ["kiwoom", "shinhan", "mirae", "kis"])
def test_every_stock_workspace_excludes_crypto_other_brokers_and_unscoped_rows(tmp_path, source):
    db_path = tmp_path / "trading.db"
    all_sources = ["kiwoom", "shinhan", "mirae", "kis"]
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE trade_log (symbol TEXT, exchange TEXT, asset_type TEXT, pnl REAL, entry_time TEXT, exit_time TEXT)"
        )
        connection.executemany(
            "INSERT INTO trade_log VALUES (?, ?, 'stock', ?, '2026-08-15 10:00:00', '2026-08-15 10:05:00')",
            [(f"00{index + 1:04d}", venue, (index + 1) * 1000) for index, venue in enumerate(all_sources)]
            + [("999999", "", 999999)],
        )
        connection.execute(
            "CREATE TABLE stock_trade_stats (broker TEXT, asset_type TEXT, total_trades INTEGER, winning_trades INTEGER, losing_trades INTEGER, buy_count INTEGER, sell_count INTEGER, realized_pnl REAL, win_rate REAL, avg_pnl REAL, max_drawdown REAL, stat_date TEXT)"
        )
        connection.executemany(
            "INSERT INTO stock_trade_stats VALUES (?, 'stock', 1, 1, 0, 1, 0, ?, 100, ?, 0, '2026-08-15')",
            [(venue, (index + 1) * 1000, (index + 1) * 1000) for index, venue in enumerate(all_sources)]
            + [("", 999999, 999999)],
        )
        connection.execute("CREATE TABLE exchange_trade_stats (exchange TEXT, fee REAL, created_at TEXT)")
        connection.execute("INSERT INTO exchange_trade_stats VALUES ('binance', 999, '2026-08-15')")
    workspace = AccountQueryService(str(db_path)).workspace(
        "stock", "stock.source_workspaces", source=source,
    )

    assert workspace["trading"]["closed_count"] == 1
    assert workspace["trading"]["recent_trades"][0]["exchange"] == source
    assert [row["broker"] for row in workspace["statistics"]] == [source]
    assert "trading_statistics" not in workspace
    assert workspace["stock_trading_statistics"]["filter_source"] == source
    assert workspace["data_scope"] == {
        "mode": "source_strict", "source": source, "unscoped_records_included": False,
    }


def test_trading_overview_win_rate_counts_each_closed_trade_once(tmp_path):
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE trade_log (symbol TEXT, exchange TEXT, asset_type TEXT, pnl REAL, net_pnl REAL, entry_time TEXT, exit_time TEXT, reconciliation_status TEXT)"
        )
        connection.executemany(
            "INSERT INTO trade_log VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("BTCUSDT", "binance", "crypto", 10, 10, "2026-08-15 10:00:00", "2026-08-15 10:05:00", "exchange_confirmed"),
                ("ETHUSDT", "binance", "crypto", -2, -2, "2026-08-15 11:00:00", "2026-08-15 11:05:00", "exchange_confirmed"),
            ],
        )

    overview = AccountQueryService(str(db_path)).trading_overview(asset_class="crypto", source="binance")

    assert overview["closed_count"] == 2
    assert overview["win_rate"] == 50.0


def test_general_trade_statistics_starts_account_wide_and_filters_without_cross_service_leak(tmp_path):
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """CREATE TABLE trade_log (
                symbol TEXT, exchange TEXT, asset_type TEXT, side TEXT,
                pnl REAL, net_pnl REAL, pnl_percent REAL, fees REAL, entry_price REAL,
                quantity REAL, entry_time TEXT, exit_time TEXT, reconciliation_status TEXT
            )"""
        )
        connection.executemany(
            "INSERT INTO trade_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("BTCUSDT", "binance", "crypto", "LONG", 10, 10, 1.0, 0.1, 100, 2, "2026-08-15 10:00:00", "2026-08-15 10:10:00", "exchange_confirmed"),
                ("KRW-BTC", "upbit", "crypto", "BUY", -3, -3, -0.3, 300, 1000, 1, "2026-08-15 11:00:00", "2026-08-15 11:05:00", "exchange_confirmed"),
                ("ETHUSDT", "", "crypto", "SHORT", 2, 2, 0.2, 0.02, 50, 1, "2026-08-15 12:00:00", "2026-08-15 12:03:00", "exchange_confirmed"),
                ("005930", "kiwoom", "stock", "BUY", 5000, 5000, 2.0, 25, 70000, 1, "2026-08-15 13:00:00", "2026-08-15 14:00:00", "broker_order_linked"),
            ],
        )
    queries = AccountQueryService(str(db_path))

    crypto_all = queries.trading_statistics(asset_class="crypto")
    crypto_upbit = queries.trading_statistics(asset_class="crypto", source="upbit")
    crypto_binance = queries.trading_statistics(asset_class="crypto", source="binance")
    stock_all = queries.trading_statistics(asset_class="stock")

    assert crypto_all["closed_count"] == 2
    assert {group["label"] for group in crypto_all["groups"]} == {"BINANCE", "LEGACY", "UPBIT"}
    assert crypto_all["pnl_by_currency"] == {"USDT": 10.0, "KRW": -3.0}
    assert crypto_all["legacy_unattributed_count"] == 1
    assert crypto_upbit["closed_count"] == 1
    assert [group["label"] for group in crypto_upbit["groups"]] == ["UPBIT"]
    assert crypto_upbit["pnl_by_currency"] == {"KRW": -3.0}
    assert crypto_binance["closed_count"] == 1
    assert {group["label"] for group in crypto_binance["groups"]} == {"BINANCE"}
    assert stock_all["closed_count"] == 1
    assert [group["label"] for group in stock_all["groups"]] == ["KIWOOM"]
    assert stock_all["pnl_by_currency"] == {"KRW": 5000.0}


def test_stock_statistics_use_stock_tables_and_never_reuse_crypto_totals(tmp_path):
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """CREATE TABLE stock_trade_stats (
                id INTEGER PRIMARY KEY, broker TEXT, asset_type TEXT, stat_date TEXT,
                total_trades INTEGER, winning_trades INTEGER, losing_trades INTEGER,
                buy_count INTEGER, sell_count INTEGER, realized_pnl REAL,
                win_rate REAL, avg_pnl REAL, max_drawdown REAL, last_updated TEXT, created_at TEXT
            )"""
        )
        connection.executemany(
            "INSERT INTO stock_trade_stats VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("kiwoom", "stock", "2026-08-15", 3, 2, 1, 2, 1, 15000, 66.7, 1.2, -2.5, "2026-08-15", "2026-08-15"),
                ("shinhan", "etf", "2026-08-15", 2, 1, 1, 1, 1, -5000, 50, -0.3, -4, "2026-08-15", "2026-08-15"),
            ],
        )
        connection.execute(
            "CREATE TABLE exchange_trade_stats (exchange TEXT, total_trades INTEGER, realized_pnl REAL, created_at TEXT)"
        )
        connection.execute("INSERT INTO exchange_trade_stats VALUES ('binance', 999, 123456, '2026-08-15')")
    queries = AccountQueryService(str(db_path))

    all_rows = queries.workspace("stock", "stock.statistics")["stock_trading_statistics"]
    kiwoom = queries.workspace("stock", "stock.statistics", source="kiwoom")["stock_trading_statistics"]

    assert all_rows["cross_service_data_included"] is False
    assert {row["broker"] for row in all_rows["brokers"]} == {"kiwoom", "shinhan"}
    assert [row["broker"] for row in kiwoom["brokers"]] == ["kiwoom"]
    assert kiwoom["brokers"][0]["total_trades"] == 3
    assert kiwoom["brokers"][0]["realized_pnl"] == 15000
    assert "trading_statistics" not in queries.workspace("stock", "stock.statistics")


def test_stock_statistics_use_latest_snapshot_without_all_asset_double_count(tmp_path):
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """CREATE TABLE stock_trade_stats (
                id INTEGER PRIMARY KEY, broker TEXT, asset_type TEXT, stat_date TEXT,
                total_trades INTEGER, winning_trades INTEGER, losing_trades INTEGER,
                buy_count INTEGER, sell_count INTEGER, realized_pnl REAL,
                win_rate REAL, avg_pnl REAL, max_drawdown REAL, last_updated TEXT, created_at TEXT
            )"""
        )
        connection.executemany(
            "INSERT INTO stock_trade_stats VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("kiwoom", "all", "2026-08-14", 90, 60, 30, 50, 40, 9000, 66.7, 1.0, -3.0, "2026-08-14", "2026-08-14"),
                ("kiwoom", "stock", "2026-08-14", 70, 50, 20, 40, 30, 7000, 71.4, 1.1, -2.0, "2026-08-14", "2026-08-14"),
                ("kiwoom", "all", "2026-08-15", 10, 7, 3, 6, 4, 1000, 70.0, 1.2, -1.5, "2026-08-15", "2026-08-15"),
                ("kiwoom", "stock", "2026-08-15", 8, 6, 2, 5, 3, 800, 75.0, 1.3, -1.0, "2026-08-15", "2026-08-15"),
                ("kiwoom", "etf", "2026-08-15", 2, 1, 1, 1, 1, 200, 50.0, 0.8, -1.5, "2026-08-15", "2026-08-15"),
            ],
        )

    broker = AccountQueryService(str(db_path)).stock_trading_statistics(source="kiwoom")["brokers"][0]

    assert broker["total_trades"] == 10
    assert broker["realized_pnl"] == 1000
    assert broker["win_rate"] == 70.0
    assert [row["asset_type"] for row in broker["details"]] == ["ALL", "ETF", "STOCK"]
    assert [row["total_trades"] for row in broker["details"]] == [10, 2, 8]


def test_exchange_execution_summary_counts_all_confirmed_rows_but_bounds_history(tmp_path):
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """CREATE TABLE exchange_execution_log (
                id INTEGER PRIMARY KEY, exchange TEXT, symbol TEXT, side TEXT, price REAL,
                quantity REAL, cost REAL, fee REAL, executed_at TEXT, created_at TEXT,
                confirmation_status TEXT
            )"""
        )
        connection.executemany(
            "INSERT INTO exchange_execution_log VALUES (NULL, ?, 'BTCUSDT', 'BUY', 1, 1, ?, 0, ?, ?, ?)",
            [("binance", 2, f"2026-08-15 10:{index % 60:02d}:00", f"2026-08-15 10:{index % 60:02d}:00", "confirmed") for index in range(125)]
            + [("upbit", 999, "2026-08-15 10:00:00", "2026-08-15 10:00:00", "confirmed")]
            + [("binance", 777, "2026-08-15 10:00:00", "2026-08-15 10:00:00", "failed")],
        )
    summary = AccountQueryService(str(db_path)).trading_statistics(asset_class="crypto", source="binance")

    assert summary["execution_count"] == 125
    assert summary["notional_by_currency"] == {"USDT": 250.0}
    assert len(summary["execution_rows"]) == 50


def test_ai_analyst_scenario_matches_legacy_policy_and_three_scope_contract(tmp_path, monkeypatch):
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE trade_log (symbol TEXT, exchange TEXT, asset_type TEXT, pnl REAL, entry_time TEXT, exit_time TEXT)"
        )
        connection.executemany(
            "INSERT INTO trade_log VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("BTCUSDT", "binance", "crypto", 10, "2026-08-15 10:00:00", "2026-08-15 10:05:00"),
                ("ETHUSDT", "binance", "crypto", -4, "2026-08-15 11:00:00", "2026-08-15 11:05:00"),
                ("005930", "kiwoom", "stock", 1000, "2026-08-15 12:00:00", "2026-08-15 12:05:00"),
            ],
        )
    monkeypatch.setattr(
        "web_platform.query_services.load_settings",
        lambda **kwargs: {"stock_auto_trading": {"buy_threshold": 0.4, "sell_threshold": 0.6, "interval_seconds": 1800, "max_positions": 3, "risk_guard_enabled": True}},
    )
    legacy = AccountQueryService(str(db_path)).workspace("ai_analyst", "ai_analyst.scenario")["scenario"]
    assert legacy["scopes"]["all"]["sample_count"] == 0
    with sqlite3.connect(db_path) as connection:
        connection.execute("ALTER TABLE trade_log ADD COLUMN reconciliation_status TEXT")
        connection.execute("ALTER TABLE trade_log ADD COLUMN net_pnl REAL")
        connection.execute("UPDATE trade_log SET reconciliation_status='exchange_confirmed', net_pnl=pnl")
    result = AccountQueryService(str(db_path)).workspace("ai_analyst", "ai_analyst.scenario")["scenario"]
    assert result["read_only"] is True
    assert result["policy_source"] == "stock_auto_trading"
    assert result["policy"]["max_positions"] == 3
    assert result["scopes"]["all"]["sample_count"] == 3
    assert result["scopes"]["crypto"]["sample_count"] == 2
    assert result["scopes"]["stock"]["sample_count"] == 1
    assert result["scopes"]["all"]["currency_mixed"] is True
    assert result["scopes"]["all"]["currencies"] == ["KRW", "USDT"]
    assert result["scopes"]["all"]["scenarios"] == []
    assert [row["name"] for row in result["scopes"]["crypto"]["scenarios"]] == ["보수적", "현재 정책", "공격적"]
    assert result["scopes"]["crypto"]["scenarios"][0]["position_ratio"] == 0.7
    assert result["scopes"]["crypto"]["scenarios"][0]["currency"] == "USDT"
    assert result["policy"]["threshold_scale"] == 1.0
    assert [row["description"].split(" | ")[0] for row in result["scopes"]["crypto"]["scenarios"]] == [
        "기록된 순손익 × 0.7 · 주문/진입 조건 재시뮬레이션 아님", "기록된 순손익 × 1.0 · 주문/진입 조건 재시뮬레이션 아님", "기록된 순손익 × 1.3 · 주문/진입 조건 재시뮬레이션 아님",
    ]

    monkeypatch.setattr(
        "web_platform.query_services.load_settings",
        lambda **kwargs: {"stock_auto_trading": {"buy_threshold": 70, "sell_threshold": 30, "interval_seconds": 1800, "max_positions": 3, "risk_guard_enabled": True}},
    )
    score_result = AccountQueryService(str(db_path)).workspace("ai_analyst", "ai_analyst.scenario")["scenario"]
    assert score_result["policy"]["threshold_scale"] == 100.0
    assert [row["description"].split(" | ")[0] for row in score_result["scopes"]["crypto"]["scenarios"]] == [
        "기록된 순손익 × 0.7 · 주문/진입 조건 재시뮬레이션 아님", "기록된 순손익 × 1.0 · 주문/진입 조건 재시뮬레이션 아님", "기록된 순손익 × 1.3 · 주문/진입 조건 재시뮬레이션 아님",
    ]


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
    assert health.json()["mode"] == "internal_migration_candidate"

    assert client.get("/api/v1/platform").status_code == 401
    assert client.get("/api/v1/platform", headers=AUTH).status_code == 200
    runtime = client.get("/api/v1/runtime/snapshot", headers=AUTH)
    assert runtime.status_code == 200
    assert runtime.json()["running_sources"] == ["binance"]

    features = client.get("/api/v1/features", headers=AUTH)
    assert features.status_code == 200
    assert features.json()["commands_enabled"] is True

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
        assert event["payload"]["commands_enabled"] is True
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


class VenueResponse(FakeResponse):
    def __init__(self, payload): self.payload = payload
    def json(self): return self.payload


class VenueSession(FakeSession):
    def __init__(self, payloads): super().__init__(); self.payloads = list(payloads)
    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        return VenueResponse(self.payloads.pop(0))


@pytest.mark.parametrize("source,market_type,symbol,interval,payload,expected_open", [
    ("bybit", "futures", "BTCUSDT", "1m", {"retCode": 0, "result": {"list": [["1000", "10", "12", "9", "11", "7"]]}}, 10),
    ("okx", "spot", "BTCUSDT", "1m", {"code": "0", "data": [["1000", "10", "12", "9", "11", "7"]]}, 10),
    ("bitget", "futures", "BTCUSDT", "1m", {"code": "00000", "data": [["1000", "10", "12", "9", "11", "7"]]}, 10),
    ("upbit", "spot", "BTCKRW", "1m", [{"candle_date_time_utc": "2026-08-14T00:00:00", "opening_price": 10, "high_price": 12, "low_price": 9, "trade_price": 11, "candle_acc_trade_volume": 7}], 10),
    ("bithumb", "spot", "BTCKRW", "1m", {"status": "0000", "data": [[1000, "10", "11", "12", "9", "7"]]}, 10),
])
def test_multi_source_market_data_normalizes_supported_venues(source, market_type, symbol, interval, payload, expected_open):
    provider = MultiSourcePublicMarketData(session=VenueSession([payload]), ttl_seconds=0)
    snapshot = provider.get_candles(source, market_type, symbol, interval, 20)
    assert snapshot.source == source
    assert snapshot.candles[0].open == expected_open
    assert snapshot.candles[0].market_type == market_type


def test_web_desktop_shell_is_version_aligned_and_fail_closed():
    package = json.loads((ROOT / "webui" / "package.json").read_text(encoding="utf-8"))
    electron_main = (ROOT / "webui" / "electron" / "main.cjs").read_text(encoding="utf-8")
    vite_config = (ROOT / "webui" / "vite.config.ts").read_text(encoding="utf-8")
    major, minor, patch, revision = (int(part) for part in RELEASE_VERSION.split("."))
    updater_version = f"{major}.{minor}.{patch * 100 + revision}"

    assert package["version"] == updater_version
    assert package["main"] == "electron/main.cjs"
    assert package["engines"]["node"] == ">=22.12.0"
    assert package["devDependencies"]["electron"] == "43.4.0"
    assert "nodeIntegration: false" in electron_main
    assert "contextIsolation: true" in electron_main
    assert "sandbox: true" in electron_main
    assert 'setWindowOpenHandler' in electron_main
    assert 'will-navigate' in electron_main
    assert 'protocol.registerSchemesAsPrivileged' in electron_main
    assert 'startGateway' in electron_main
    assert 'findFreePort' in electron_main
    assert 'app.requestSingleInstanceLock()' in electron_main
    assert 'autoUpdater.autoDownload = false' in electron_main
    assert 'autoUpdater.autoInstallOnAppQuit = false' in electron_main
    assert 'autoUpdater.allowPrerelease = false' in electron_main
    assert 'autoUpdater.allowDowngrade = false' in electron_main
    assert 'autoUpdater.autoDownload = preferences.autoDownload' in electron_main
    assert 'autoUpdater.autoInstallOnAppQuit = preferences.autoInstallOnAppQuit' in electron_main
    assert 'shouldInstallUpdateOnQuit({' in electron_main
    assert 'autoUpdater.quitAndInstall(true, false)' in electron_main
    app_source = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert 'autoInstallOnAppQuit: values["ui_settings.auto_update_auto_apply_on_exit"] === true' in app_source
    update_center = (ROOT / "webui" / "src" / "components" / "UpdateCenter.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "webui" / "src" / "styles.css").read_text(encoding="utf-8")
    assert 'className="update-check-button"' in update_center
    assert ".update-version-actions .update-check-button" in styles
    assert 'NOAHAI_GATEWAY_TOKEN' in electron_main
    assert '"/api"' in vite_config
    launcher = (ROOT / "web_platform" / "launcher.py").read_text(encoding="utf-8")
    assert '"--gateway-only"' in launcher
    assert "use_colors=False" in launcher

    package_build = package["build"]
    assert package_build["directories"]["output"] == "release"
    assert package_build["buildVersion"] == RELEASE_VERSION
    assert package_build["win"]["artifactName"] == f"NoahAI-{RELEASE_VERSION}-Setup.${{ext}}"
    assert package_build["win"]["executableName"] == "NoahAI"
    assert package_build["publish"] == [{"provider": "github", "owner": "nwsoft", "repo": "ai-trading-client"}]
    assert package_build["extraResources"][0]["to"] == "engine"
    assert (ROOT / "scripts" / "build_web_ui_windows.ps1").exists()
    assert (ROOT / "noahai_web_engine.spec").exists()
    build_script = (ROOT / "scripts" / "build_web_ui_windows.ps1").read_text(encoding="utf-8")
    assert 'Filter "NoahAI-$version-Setup.exe.blockmap"' in build_script
    assert 'build_status = "built_windows_unverified"' in build_script
    assert 'publish_ready = $false' in build_script
    assert "source_fingerprint = $sourceFingerprint" in build_script
    assert 'legacy_single_exe_updater = "retired_after_v3.9.0.10"' in build_script
    publish_script = (ROOT / "scripts" / "publish_web_ui_windows_release.ps1").read_text(encoding="utf-8")
    assert "Get-ReleaseSourceFingerprint" in publish_script
    assert "Windows candidate is stale" in publish_script
    update_ui = (ROOT / "webui" / "src" / "components" / "UpdateCenter.tsx").read_text(encoding="utf-8")
    assert "설치·재시작" in update_ui
    assert "/api/v1/runtime/shutdown" in electron_main
    assert "requestSafeGatewayShutdown" in electron_main
    assert "quitAndInstall" in electron_main


def test_windows_data_root_prefers_canonical_legacy_directory(monkeypatch, tmp_path):
    import path_utils

    documents = tmp_path / "Documents"
    canonical = documents / "NoahAI"
    backup = documents / "NoahAI_old"
    backup.mkdir(parents=True)
    canonical.mkdir()
    monkeypatch.setattr(path_utils.os.path, "expanduser", lambda _value: str(tmp_path))

    assert Path(path_utils.find_noahai_dir()) == canonical


def test_web_engine_runtime_and_spec_are_legacy_ui_free():
    runtime_source = (ROOT / "web_platform" / "runtime_bridge.py").read_text(encoding="utf-8")
    headless_source = (ROOT / "web_platform" / "headless_runtime.py").read_text(encoding="utf-8")
    spec_source = (ROOT / "noahai_web_engine.spec").read_text(encoding="utf-8")
    build_source = (ROOT / "scripts" / "build_web_ui_windows.ps1").read_text(encoding="utf-8")

    assert "from main import" not in runtime_source + headless_source
    assert "from ui" not in runtime_source + headless_source
    assert "customtkinter" not in runtime_source + headless_source
    assert "aiautotrade.spec" not in spec_source
    assert '"main", "ui", "customtkinter", "tkinter"' in spec_source
    assert '("config/web_ui_feature_inventory.json", "config")' in spec_source
    assert "verify_web_engine_bundle.py" in build_source
    assert "Built sidecar desktop bootstrap API smoke" in build_source
    assert "Tcl/Tk preflight" not in build_source

    smoke_source = (ROOT / "scripts" / "smoke_web_engine.py").read_text(encoding="utf-8")
    for route in (
        "/api/v1/platform",
        "/api/v1/session",
        "/api/v1/features",
        "/api/v1/runtime/snapshot",
    ):
        assert route in smoke_source


def test_settings_sanitizer_never_serializes_nested_secrets():
    value = sanitize_settings({
        "binance_api_key": "do-not-expose",
        "nested": {"password": "hidden", "safe": 3},
        "enabled_exchanges": ["binance"],
    })
    encoded = json.dumps(value)
    assert "do-not-expose" not in encoded
    assert "hidden" not in encoded
    assert value["binance_api_key"] == {"configured": True, "write_only": True}
    assert value["nested"]["safe"] == 3


def test_detached_runtime_bridge_fails_closed():
    bridge = DetachedRuntimeBridge()
    assert bridge.snapshot()["status"] == "detached"
    with pytest.raises(RuntimeError, match="연결되지 않아"):
        bridge.execute("trading.start", {"source": "binance"})


def test_lazy_runtime_bridge_constructs_only_after_confirmed_command():
    calls = []
    class FakeApp:
        def __init__(self):
            self.started = False
        def _running_crypto_exchanges(self):
            return ["binance"] if self.started else []
        def _start_binance_trading(self):
            self.started = True
            return True
    bridge = LazyLegacyRuntimeBridge(account="tester", factory=lambda account: calls.append(account) or FakeApp())
    bridge._settings = lambda: {"binance_api_key": "key", "binance_secret_key": "secret"}
    assert bridge.snapshot()["reason"] == "engine_lazy_until_confirmed_start"
    assert calls == []
    result = bridge.execute("trading.start", {"source": "binance"})
    assert calls == ["tester"]
    assert result["running_sources"] == ["binance"]


def test_live_runtime_start_requires_explicit_live_confirmation():
    class FakeApp:
        def __init__(self):
            self.started = False

        def running_crypto_exchanges(self):
            return ["binance"] if self.started else []

        def start_source(self, _source):
            self.started = True
            return True

    bridge = LazyLegacyRuntimeBridge(account="tester", factory=lambda _account: FakeApp())
    bridge._settings = lambda: {
        "paper_trading": False,
        "enabled_exchanges": ["binance"],
        "binance_api_key": "key",
        "binance_secret_key": "secret",
    }

    with pytest.raises(RuntimeError, match="live_start_confirmation_required"):
        bridge.execute("trading.start", {"source": "binance"})
    result = bridge.execute("trading.start", {"source": "binance", "live_confirmation": True})
    assert result["running_sources"] == ["binance"]


def test_runtime_shutdown_endpoint_blocks_new_commands_and_requires_safe_result(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    class Bridge:
        def __init__(self): self.shutdown_calls = 0
        def snapshot(self): return {"status": "ready", "enabled_sources": ["binance"], "running_sources": []}
        def execute(self, command, payload): return {"ok": True}
        def account_snapshot(self, **kwargs): return {}
        def stock_candles(self, **kwargs): return []
        def shutdown(self):
            self.shutdown_calls += 1
            return {"safe_to_exit": True, "running_sources": [], "errors": []}

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    bridge = Bridge()
    services = ApplicationServices(account="tester", runtime_bridge=bridge)
    client = TestClient(create_gateway_app(token=TOKEN, application_services=services))
    confirmed = {**AUTH, "X-NoahAI-Intent": "confirmed"}

    assert client.post("/api/v1/runtime/shutdown", headers=AUTH, json={}).status_code == 428
    response = client.post("/api/v1/runtime/shutdown", headers=confirmed, json={})
    assert response.status_code == 200
    assert response.json()["safe_to_exit"] is True
    assert bridge.shutdown_calls == 1
    command = client.post("/api/v1/runtime/commands", headers=confirmed, json={
        "command_id": "abcdefghijklmnop",
        "command": "trading.start",
        "source": "binance",
        "close_all": False,
    })
    assert command.status_code == 409
    assert command.json()["detail"] == "runtime_shutdown_in_progress"


def test_runtime_account_snapshot_uses_shared_adapter_and_redacts_secrets():
    class Client:
        def get_positions(self):
            return [{"symbol": "BTCUSDT", "quantity": 0.1, "api_key": "never-return"}]
        def get_open_orders(self):
            return [{"id": "order-1", "password": "never-return"}]
    class Manager:
        def __init__(self): self.client = Client()
        def get_exchange_balance(self, source, force_refresh=False):
            return {"status": "success", "balance": {"USDT": Decimal("123.4567")}, "secret": "never-return"}
        def get_exchange_client(self, source): return self.client
    class App:
        exchange_manager = Manager()
        def _running_crypto_exchanges(self): return []
    bridge = LazyLegacyRuntimeBridge(account="tester", factory=lambda account: App())
    bridge._settings = lambda: {"binance_api_key": "key", "binance_secret_key": "secret"}
    snapshot = bridge.account_snapshot(sources=["binance"], force_refresh=True)
    encoded = json.dumps(snapshot)
    assert snapshot["sources"]["binance"]["positions"][0]["symbol"] == "BTCUSDT"
    assert snapshot["sources"]["binance"]["open_orders"][0]["id"] == "order-1"
    assert snapshot["sources"]["binance"]["balance"]["balance"]["USDT"] == pytest.approx(123.4567)
    assert "never-return" not in encoded


def test_spot_account_snapshot_uses_balance_holdings_instead_of_futures_positions():
    class Client:
        def get_open_orders(self):
            return []

    class Manager:
        def get_exchange_balance(self, source, force_refresh=False):
            return {"status": "success", "balance": {"KRW": 50_000, "BTC": 0.012, "ETH": 0}}

        def get_exchange_client(self, source):
            return Client()

    class App:
        exchange_manager = Manager()

        def _running_crypto_exchanges(self):
            return []

    bridge = LazyLegacyRuntimeBridge(account="tester", factory=lambda account: App())
    bridge._settings = lambda: {"upbit_api_key": "key", "upbit_secret_key": "secret"}

    account = bridge.account_snapshot(sources=["upbit"], force_refresh=True)["sources"]["upbit"]

    assert account["positions_status"] == "success"
    assert len(account["positions"]) == 1
    holding = account["positions"][0]
    assert holding["symbol"] == "BTC"
    assert holding["side"] == "HOLD"
    assert holding["quantity"] == pytest.approx(0.012)
    assert holding["ownership"] == "external"
    assert holding["managed_quantity"] == 0.0
    assert holding["auto_trade_managed"] is False
    assert holding["display_group"] == "market_unknown"
    assert account["managed_positions"] == []
    assert account["spot_holding_summary"] == {
        "account_total": 1,
        "noahai_managed": 0,
        "external_tradable": 0,
        "reference_only": 1,
    }


def test_missing_credentials_do_not_construct_runtime_or_query_balance():
    calls = []
    bridge = LazyLegacyRuntimeBridge(account="tester", factory=lambda account: calls.append(account))
    bridge._settings = lambda: {"enabled_exchanges": ["binance"]}

    snapshot = bridge.account_snapshot(sources=["binance"], force_refresh=True)

    assert calls == []
    assert snapshot["fresh"] is False
    assert snapshot["sources"]["binance"]["status"] == "credential_required"
    assert "API 키를 설정" in snapshot["sources"]["binance"]["message"]
    with pytest.raises(RuntimeError, match="credential_required:binance"):
        bridge.execute("trading.start", {"source": "binance"})
    assert calls == []


def test_stock_account_snapshot_is_read_only_and_component_scoped():
    settings = {"enabled_stock_brokers": ["kis"]}
    class Adapter:
        is_connected = True
        def get_balance(self): return {"KRW": 1000}
        def get_positions(self): return [{"symbol": "005930", "quantity": 1}]
        def get_open_orders(self): raise RuntimeError("orders_not_supported")
    controller = StockRuntimeController(
        settings_provider=lambda: deepcopy(settings),
        adapter_factory=lambda broker, cfg: Adapter(),
    )
    snapshot = controller.account_snapshot("kis")
    assert snapshot["balance"] == {"KRW": 1000}
    assert snapshot["positions"][0]["symbol"] == "005930"
    assert snapshot["open_orders_status"] == "error"
    assert snapshot["status"] == "success"


def test_stock_runtime_candles_use_enabled_broker_and_normalized_symbol():
    settings = {"enabled_stock_brokers": ["kis"]}
    class Adapter:
        is_connected = False
        def connect(self): self.is_connected = True; return True
        def get_daily_candles(self, symbol, limit=100):
            assert symbol == "005930"
            assert limit == 20
            return [{"date": "20260813", "open": 70000, "high": 72000, "low": 69000, "close": 71000, "volume": 1234}]
    controller = StockRuntimeController(
        settings_provider=lambda: deepcopy(settings),
        adapter_factory=lambda broker, cfg: Adapter(),
    )
    rows = controller.market_candles("kis", "005930", limit=20)
    assert rows[0]["close"] == 71000
    with pytest.raises(RuntimeError, match="stock_source_not_enabled"):
        controller.market_candles("kiwoom", "005930")
    with pytest.raises(ValueError, match="invalid_stock_symbol"):
        controller.market_candles("kis", "005930.KS")


def test_stock_runtime_analysis_reuses_legacy_analysis_service_without_orders():
    settings = {"enabled_stock_brokers": ["kis"]}
    calls = []

    class Adapter:
        is_connected = False
        def connect(self):
            self.is_connected = True
            return True

    class Service:
        def __init__(self, adapter, **kwargs):
            calls.append((adapter, kwargs))

        def analyze_symbol(self, symbol):
            calls.append(symbol)
            return {
                "status": "ok",
                "symbol": symbol,
                "current_price": 71000,
                "change_rate": 1.2,
                "ai_score": 74,
                "reasoning": "legacy service result",
            }

    controller = StockRuntimeController(
        settings_provider=lambda: deepcopy(settings),
        adapter_factory=lambda broker, cfg: Adapter(),
        service_factory=Service,
    )

    result = controller.analyze_symbol("kis", "005930")

    assert result["ai_score"] == 74
    assert calls[0][1]["broker_name"] == "kis"
    assert calls[1] == "005930"
    assert controller.running_sources() == []


def test_stock_runtime_suggestions_reuse_broker_stock_and_etf_lists_without_orders():
    settings = {"enabled_stock_brokers": ["kis"]}

    class Adapter:
        is_connected = False

        def connect(self):
            self.is_connected = True
            return True

        def get_stock_list(self, market):
            assert market == "ALL"
            return [
                {"code": "005930", "name": "삼성전자"},
                {"code": "000660", "name": "SK하이닉스"},
            ]

        def get_etf_list(self):
            return [{"code": "069500", "name": "KODEX 200", "is_etf": True}]

        def is_etf(self, code):
            return code == "069500"

    controller = StockRuntimeController(
        settings_provider=lambda: deepcopy(settings),
        adapter_factory=lambda broker, cfg: Adapter(),
    )

    assert controller.symbol_suggestions("kis", query="삼성", asset_mode="stock")[0]["code"] == "005930"
    etfs = controller.symbol_suggestions("kis", query="069", asset_mode="etf")
    assert etfs == [{
        "code": "069500", "name": "KODEX 200", "is_etf": True,
        "broker": "kis", "kind": "etf",
    }]
    assert controller.running_sources() == []


def test_gateway_stock_candles_are_broker_scoped_and_daily_only(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    class Bridge:
        def snapshot(self): return {"status": "ready", "enabled_sources": ["kis"], "running_sources": []}
        def execute(self, command, payload): raise AssertionError("must not execute orders")
        def account_snapshot(self, **kwargs): return {}
        def stock_candles(self, *, source, symbol, limit=300):
            assert (source, symbol, limit) == ("kis", "005930", 30)
            return [{"date": "20260813", "open": 70000, "high": 72000, "low": 69000, "close": 71000, "volume": 1234}]

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    services = ApplicationServices(account="tester", runtime_bridge=Bridge())
    client = TestClient(create_gateway_app(token=TOKEN, market_data=FakeMarketData(), application_services=services))
    response = client.get(
        "/api/v1/market/candles?source=kis&market_type=stock&symbol=005930&interval=1d&limit=30",
        headers=AUTH,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "kis"
    assert payload["candles"][0]["market_type"] == "stock"
    assert payload["candles"][0]["close"] == 71000
    invalid = client.get(
        "/api/v1/market/candles?source=kis&market_type=stock&symbol=005930&interval=1h&limit=30",
        headers=AUTH,
    )
    assert invalid.status_code == 400


def test_stock_runtime_controller_is_ui_neutral_paper_first_and_blocks_account_wide_close():
    settings = {
        "paper_trading": True,
        "enabled_stock_brokers": ["kis"],
        "stock_broker_configs": {"koreaInvestment": {"api_type": "mock", "api_version": "mock"}},
        "stock_auto_trading": {"symbols": ["005930"], "interval_sec": 5},
    }
    class Adapter:
        api_type = "mock"
        api_version = "mock"
        broker_name = "koreaInvestment"
        is_connected = True
        def get_stock_list(self, market): return []
        def get_etf_list(self): return []
    calls = []
    class Service:
        def __init__(self, adapter, **kwargs): pass
        def run_auto_trade_cycle(self, **kwargs):
            calls.append(kwargs)
            return {"orders_executed": 0, "execution_mode": kwargs["execution_mode_override"]}
    controller = StockRuntimeController(
        settings_provider=lambda: deepcopy(settings),
        adapter_factory=lambda broker, cfg: Adapter(),
        service_factory=Service,
    )
    result, _ = controller._run_once("koreaInvestment")
    assert result["execution_mode"] == "paper"
    assert calls[0]["allow_live_order"] is True
    assert calls[0]["symbols"] == ["005930"]
    with pytest.raises(RuntimeError, match="position_ownership_required"):
        controller.stop("kis", close_all=True)


class FakeApplicationServices:
    def session_snapshot(self):
        return {"authenticated": True, "account": "tester", "user": {"id": "tester"}}

    def authenticate(self, **kwargs):
        return {"authenticated": True, "account": kwargs["username"], "user": {"id": kwargs["username"]}}

    def ask_assistant(self, **kwargs):
        return {"answer": "safe guide", "provider_called": False, **kwargs}

    def runtime_snapshot(self):
        return {"status": "detached", "reason": "test", "enabled_sources": [], "running_sources": []}

    def settings_snapshot(self):
        return {"revision": "a" * 64, "fields": [], "credential_status": {}}

    def settings_diagnostics(self):
        return {"schema_version": "1.0.0", "ai": {"configured": False}, "credential_status": {}}

    def check_ai_provider(self, **kwargs):
        return {"ok": True, "network_checked": True, "models": ["test-model"], **kwargs}

    def analyze_chart_image(self, **kwargs):
        return {"analysis": {"stance": "NEUTRAL"}, "order_submitted": False, **kwargs}

    def update_settings(self, **kwargs):
        return {"revision": "b" * 64, "fields": [], "credential_status": {}, "received": kwargs}

    def settings_backups(self, **kwargs):
        return {"schema_version": "1.0.0", "backups": [{"name": "settings_20260815_120000_000001.json", "created_at": "2026-08-15T03:00:00+00:00", "size": 10}]}

    def restore_settings_backup(self, **kwargs):
        return {"revision": "c" * 64, "fields": [], "credential_status": {}, "received": kwargs}

    def strategy_catalog(self):
        return {"strategies": []}

    def delete_strategy(self, **kwargs):
        return {"deleted": "strategy", **kwargs}

    def life_finance_snapshot(self):
        return {"summary": {}, "transactions": [], "goals": []}

    def log_snapshot(self, **kwargs):
        return {"lines": [], **kwargs}

    def execute_runtime_command(self, **kwargs):
        raise RuntimeError("trading_engine_not_attached")


def test_mutations_require_explicit_intent_and_detached_commands_are_blocked():
    app = create_gateway_app(
        token=TOKEN,
        market_data=FakeMarketData(),
        application_services=FakeApplicationServices(),
    )
    client = TestClient(app)
    body = {"expected_revision": "a" * 64, "changes": {"paper_trading": True}}
    assert client.post("/api/v1/settings", headers=AUTH, json=body).status_code == 428
    saved = client.post(
        "/api/v1/settings",
        headers={**AUTH, "X-NoahAI-Intent": "confirmed"},
        json=body,
    )
    assert saved.status_code == 200
    backups = client.get("/api/v1/settings/backups", headers=AUTH)
    assert backups.status_code == 200
    restore_body = {"expected_revision": "a" * 64, "backup_name": "settings_20260815_120000_000001.json"}
    assert client.post("/api/v1/settings/restore", headers=AUTH, json=restore_body).status_code == 428
    restored = client.post(
        "/api/v1/settings/restore",
        headers={**AUTH, "X-NoahAI-Intent": "confirmed"},
        json=restore_body,
    )
    assert restored.status_code == 200
    traversal = client.post(
        "/api/v1/settings/restore",
        headers={**AUTH, "X-NoahAI-Intent": "confirmed"},
        json={"expected_revision": "a" * 64, "backup_name": "../settings_20260815_120000_000001.json"},
    )
    assert traversal.status_code == 422
    command = client.post(
        "/api/v1/runtime/commands",
        headers={**AUTH, "X-NoahAI-Intent": "confirmed"},
        json={
            "command_id": "0123456789abcdef",
            "command": "trading.start",
            "source": "binance",
            "close_all": False,
        },
    )
    assert command.status_code == 409

    assistant = client.post(
        "/api/v1/assistant/ask",
        headers={**AUTH, "X-NoahAI-Intent": "confirmed"},
        json={"question": "PAPER가 무엇인가요?", "service": "ai_custom", "explanation_level": "beginner"},
    )
    assert assistant.status_code == 200
    assert assistant.json()["provider_called"] is False

    diagnostics = client.get("/api/v1/settings/diagnostics", headers=AUTH)
    assert diagnostics.status_code == 200
    provider_body = {"provider": "openai", "model": "test-model", "capability": "chat_text"}
    assert client.post("/api/v1/settings/ai-provider-check", headers=AUTH, json=provider_body).status_code == 428
    provider_check = client.post(
        "/api/v1/settings/ai-provider-check",
        headers={**AUTH, "X-NoahAI-Intent": "confirmed"},
        json=provider_body,
    )
    assert provider_check.status_code == 200
    assert provider_check.json()["network_checked"] is True


def test_application_services_use_revision_allowlist_audit_and_redacted_logs(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    stored = {
        "paper_trading": True,
        "demo_mode": False,
        "operation_mode": "balanced",
        "default_leverage": 3,
        "default_tp": 0.018,
        "default_sl": 0.012,
        "max_positions": 3,
        "min_trade_amount": 10,
        "auto_trade_interval": 30,
        "dynamic_thresholds_enabled": True,
        "dynamic_thresholds_mode": "auto",
        "ai_learning_min_samples": 10,
        "ai_provider": "deepseek",
        "assistant_response_mode": "standard",
        "ai_custom_runtime": {"enabled": False, "allow_limited_live": False},
        "alpha_arena": {"enabled": False},
        "log_level": "INFO",
        "detailed_logs_enabled": False,
        "binance_api_key": "private-key",
        "binance_secret_key": "private-secret",
        "_trade_scope_user_confirmed_v3905": False,
    }

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "get_log_dir", lambda: str(tmp_path / "logs"))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: deepcopy(stored))

    def fake_save(next_settings):
        stored.clear()
        stored.update(deepcopy(next_settings))
        return True

    monkeypatch.setattr(service_module, "save_settings", fake_save)
    monkeypatch.setattr(service_module, "patch_settings_paths", lambda changes: fake_save(_with_setting_paths(stored, changes)))
    services = ApplicationServices(account="tester")
    snapshot = services.settings_snapshot()
    encoded = json.dumps(snapshot)
    assert "private-key" not in encoded
    assert snapshot["credential_status"]["binance"] is True
    assert snapshot["credential_field_status"]["binance"] == {
        "api_key": True,
        "secret_key": True,
    }
    diagnostics = services.settings_diagnostics()
    assert diagnostics["ai"]["provider"] == "deepseek"
    assert diagnostics["ai"]["network_checked"] is False
    assert diagnostics["trading"]["live_ready"] is False
    assert "private-key" not in json.dumps(diagnostics)
    assert {field["section"] for field in snapshot["fields"]} <= {
        "general", "exchange_selection", "exchange_api", "ai_engine",
        "notifications", "advanced", "alpha", "system", "update",
    }
    assert {field["presentation"] for field in snapshot["fields"]} <= {"primary", "advanced"}
    fields_by_path = {field["path"]: field for field in snapshot["fields"]}
    assert fields_by_path["paper_trading"]["section"] == "general"
    assert fields_by_path["paper_trading"]["presentation"] == "primary"
    assert fields_by_path["default_leverage"]["section"] == "advanced"
    assert fields_by_path["default_leverage"]["presentation"] == "advanced"
    assert fields_by_path["default_margin_type"]["presentation"] == "advanced"
    assert "ai_learning_min_samples" not in fields_by_path
    assert fields_by_path["dynamic_thresholds_enabled"]["presentation"] == "advanced"
    assert fields_by_path["backup_tp_sl_settings"]["presentation"] == "advanced"
    assert fields_by_path["alpha_arena.enabled"]["presentation"] == "primary"
    assert fields_by_path["alpha_arena.engine"]["presentation"] == "primary"
    assert fields_by_path["alpha_arena.initial_capital_benchmark"]["presentation"] == "primary"
    assert fields_by_path["alpha_arena.tick_interval_sec"]["presentation"] == "advanced"
    coverage = snapshot["coverage"]
    assert coverage["editable_top_level"] + len(coverage["excluded"]) == coverage["template_top_level"]
    assert coverage["editable_top_level"] > 80
    assert "binance_api_key" in coverage["excluded"]
    assert "ai_learning_min_samples" in coverage["excluded"]

    updated = services.update_settings(
        expected_revision=snapshot["revision"],
        changes={"default_leverage": 5, "paper_trading": True},
    )
    assert stored["default_leverage"] == 5
    assert updated["revision"] != snapshot["revision"]
    with pytest.raises(RuntimeError, match="revision_conflict"):
        services.update_settings(expected_revision=snapshot["revision"], changes={"default_leverage": 4})
    with pytest.raises(ValueError, match="변경할 수 없는"):
        services.update_settings(expected_revision=updated["revision"], changes={"binance_api_key": "stolen"})

    json_updated = services.update_settings(
        expected_revision=updated["revision"],
        changes={"ai_cost_control.max_daily_interactive_calls": 50},
    )
    assert stored["ai_cost_control"]["max_daily_interactive_calls"] == 50
    with pytest.raises(ValueError, match="변경할 수 없는|자격증명"):
        services.update_settings(
            expected_revision=json_updated["revision"],
            changes={"ai_cost_control": {"api_key": "must-not-pass"}},
        )

    credential_snapshot = services.update_credentials(
        expected_revision=json_updated["revision"],
        provider="okx",
        values={"api_key": "okx-private", "secret_key": "okx-secret", "passphrase": "okx-pass"},
    )
    assert stored["okx_api_key"] == "okx-private"
    assert credential_snapshot["credential_status"]["okx"] is True
    assert credential_snapshot["credential_field_status"]["okx"] == {
        "api_key": True,
        "secret_key": True,
        "passphrase": True,
    }
    assert "okx-private" not in json.dumps(credential_snapshot)

    stored["stock_broker_configs"] = {
        "kiwoom": {"enabled": False, "api_type": "openapi_plus", "api_version": "pykiwoom", "allow_live_order": False, "asset_types": ["stock", "etf"], "account_no": "", "password": "", "cert_password": "", "id": ""},
    }
    stock_revision = services.settings_snapshot()["revision"]
    stock_settings = services.update_settings(
        expected_revision=stock_revision,
        changes={"stock_broker_configs.kiwoom.enabled": True},
    )
    assert stored["stock_broker_configs"]["kiwoom"]["enabled"] is True
    stock_credentials = services.update_credentials(
        expected_revision=stock_settings["revision"], provider="stock:kiwoom",
        values={"account_no": "12345678", "password": "stock-secret", "user_id": "tester"},
    )
    assert stored["stock_broker_configs"]["kiwoom"]["id"] == "tester"
    assert stock_credentials["credential_status"]["stock:kiwoom"] is True
    assert "stock-secret" not in json.dumps(stock_credentials)

    alpha_settings = services.update_settings(
        expected_revision=stock_credentials["revision"],
        changes={
            "alpha_arena.initial_capital_benchmark": "1000",
            "alpha_arena.tick_interval_sec": 60,
        },
    )
    assert stored["alpha_arena"]["initial_capital_benchmark"] == 1000
    assert isinstance(stored["alpha_arena"]["initial_capital_benchmark"], int)
    alpha_credentials = services.update_credentials(
        expected_revision=alpha_settings["revision"],
        provider="alpha:deepseek",
        values={"api_key": "alpha-private"},
    )
    assert stored["alpha_arena"]["deepseek_api_key"] == "alpha-private"
    assert alpha_credentials["credential_status"]["alpha:deepseek"] is True
    assert "alpha-private" not in json.dumps(alpha_credentials)

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "trading.log").write_text("INFO api_key=abc123 token:xyz789 normal=yes\n", encoding="utf-8")
    log_payload = services.log_snapshot()
    assert "abc123" not in json.dumps(log_payload)
    assert "xyz789" not in json.dumps(log_payload)
    audit_text = (tmp_path / "audit" / "web_ui_commands.jsonl").read_text(encoding="utf-8")
    assert "okx-private" not in audit_text


def test_ai_provider_check_is_explicit_read_only_and_returns_no_credentials(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    stored = {
        "ai_provider": "openai",
        "openai_model": "gpt-test",
        "ai_credentials": {"openai": {"api_key": "never-return-this"}},
    }
    observed = {}

    class FakeRouter:
        @classmethod
        def from_settings(cls, settings, *, workload):
            observed["settings"] = deepcopy(settings)
            observed["workload"] = workload
            return cls()

        def health_check(self):
            return {"ok": True, "provider": "openai", "network_checked": True, "models": ["gpt-test", "gpt-next"]}

        def validate_model(self, *, capability, verify_account):
            observed["validation"] = (capability, verify_account)
            return {"ok": True, "provider": "openai", "model": "gpt-test", "errors": [], "warnings": []}

        def probe_model(self, *, capability):
            observed["probe"] = capability
            return {
                "attempted": True,
                "ok": True,
                "requested_model": "gpt-test",
                "actual_model": "gpt-test-2026-09-01",
                "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
                "finish_reason": "stop",
                "response_id": "chatcmpl-test",
                "error": None,
            }

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: deepcopy(stored))
    monkeypatch.setattr(service_module, "AIProviderRouter", FakeRouter)

    result = ApplicationServices(account="tester").check_ai_provider(
        provider="openai", model="gpt-test", capability="chat_text",
    )
    assert result["ok"] is True
    assert result["models"] == ["gpt-test", "gpt-next"]
    assert result["network_checked"] is True
    assert result["model_callable"] is True
    assert result["requested_model"] == "gpt-test"
    assert result["actual_model"] == "gpt-test-2026-09-01"
    assert result["probe_usage"]["total_tokens"] == 3
    assert observed["validation"] == ("chat_text", False)
    assert observed["probe"] == "chat_text"
    assert "never-return-this" not in json.dumps(result)

    stored["ai_provider_profiles"] = {
        "analyst": {"provider": "openai", "model": "gpt-test"},
    }
    ApplicationServices(account="tester").check_ai_provider(
        provider="gemini", model="", capability="chat_text",
    )
    assert observed["settings"]["ai_provider_profiles"]["analyst"] == {
        "provider": "gemini",
        "model": "",
    }


def test_ai_provider_check_reports_pre_network_missing_key_and_provider_specific_status(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    stored = {
        "ai_provider": "deepseek",
        "openai_api_key": "openai-owned-key",
        "ai_credentials": {
            "openai": {"api_key": "openai-owned-key"},
            "deepseek": {"api_key": ""},
            "kimi": {"api_key": ""},
            "anthropic": {"api_key": ""},
            "gemini": {"api_key": ""},
        },
        "ai_provider_profiles": {
            "analyst": {"provider": "deepseek", "model": "deepseek-v4-flash"},
        },
    }
    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: deepcopy(stored))
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())

    snapshot = services.settings_snapshot()
    assert snapshot["credential_status"]["ai:openai"] is True
    assert snapshot["credential_status"]["ai:deepseek"] is False
    assert snapshot["credential_status"]["ai"] is False

    result = services.check_ai_provider(provider="deepseek", model="", capability="chat_text")
    assert result["ok"] is False
    assert result["provider_configured"] is False
    assert result["network_checked"] is False
    assert "저장된 API 키가 없습니다" in " ".join(result["errors"])
    assert "openai-owned-key" not in json.dumps(result)


def test_settings_primary_controls_preserve_legacy_scope_and_stock_safety_contract(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    stored = {
        "paper_trading": True,
        "enabled_exchanges": ["binance"],
        "learning_enabled_exchanges": ["binance"],
        "trade_enabled_exchanges": [],
        "selected_exchange": "binance",
        "multi_venue_execution": {"mode": "parallel"},
        "enabled_stock_brokers": [],
        "stock_asset_mode": "all",
        "stock_order_guardrails": {
            "enabled": True,
            "enforce_market_hours": True,
            "allow_market_order": False,
            "max_quantity": 10,
            "max_order_value": 1_000_000,
            "daily_order_limit": 20,
        },
        "stock_auto_trading": {"enabled": False, "auto_start": False},
        "enable_stock_live_order": False,
        "asset_stop_position_policy": "keep_with_tp_sl",
        "stock_broker_configs": {
            "kiwoom": {"enabled": False, "allow_live_order": False, "legacy_extension": {"keep": True}},
            "shinhan": {"enabled": False, "allow_live_order": False},
            "miraeAsset": {"enabled": False, "allow_live_order": False},
            "koreaInvestment": {"enabled": False, "allow_live_order": False},
        },
        "_trade_scope_user_confirmed_v3905": False,
        "future_extension": {"unknown_key": "must-survive-web-save", "nested": {"value": 7}},
    }

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: deepcopy(stored))

    def fake_save(next_settings):
        stored.clear()
        stored.update(deepcopy(next_settings))
        return True

    monkeypatch.setattr(service_module, "save_settings", fake_save)
    monkeypatch.setattr(service_module, "patch_settings_paths", lambda changes: fake_save(_with_setting_paths(stored, changes)))
    services = ApplicationServices(account="tester")
    snapshot = services.settings_snapshot()
    fields = {field["path"]: field for field in snapshot["fields"]}

    for path in (
        "enabled_exchanges",
        "trade_enabled_exchanges",
        "enabled_stock_brokers",
        "stock_asset_mode",
        "stock_order_guardrails.enabled",
        "stock_auto_trading.auto_start",
        "enable_stock_live_order",
        "asset_stop_position_policy",
    ):
        assert fields[path]["section"] == "exchange_selection"
        assert fields[path]["presentation"] == "primary"
    assert fields["enabled_exchanges"]["kind"] == "multiselect"
    assert fields["trade_enabled_exchanges"]["kind"] == "multiselect"
    assert fields["enabled_stock_brokers"]["kind"] == "multiselect"
    assert fields["multi_venue_execution.mode"]["kind"] == "select"
    assert fields["stock_broker_configs.kiwoom.allow_live_order"]["section"] == "exchange_api"
    assert fields["stock_broker_configs.kiwoom.allow_live_order"]["presentation"] == "primary"

    updated = services.update_settings(
        expected_revision=snapshot["revision"],
        changes={"enabled_exchanges": ["binance", "okx"]},
    )
    assert stored["learning_enabled_exchanges"] == ["binance", "okx"]
    assert stored["future_extension"] == {"unknown_key": "must-survive-web-save", "nested": {"value": 7}}
    assert stored["stock_broker_configs"]["kiwoom"]["legacy_extension"] == {"keep": True}
    updated = services.update_settings(
        expected_revision=updated["revision"],
        changes={"trade_enabled_exchanges": ["okx", "okx"]},
    )
    assert stored["trade_enabled_exchanges"] == ["okx"]
    assert stored["_trade_scope_user_confirmed_v3905"] is True

    with pytest.raises(ValueError, match="관찰·분석 거래소"):
        services.update_settings(
            expected_revision=updated["revision"],
            changes={"trade_enabled_exchanges": ["upbit"]},
        )

    updated = services.update_settings(
        expected_revision=updated["revision"],
        changes={"enabled_stock_brokers": ["kiwoom", "koreaInvestment"]},
    )
    assert stored["stock_broker_configs"]["kiwoom"]["enabled"] is True
    assert stored["stock_broker_configs"]["shinhan"]["enabled"] is False
    assert stored["stock_broker_configs"]["koreaInvestment"]["enabled"] is True
    updated = services.update_settings(
        expected_revision=updated["revision"],
        changes={"stock_auto_trading.auto_start": True},
    )
    assert stored["stock_auto_trading"] == {"enabled": True, "auto_start": True}


def test_session_login_persists_token_write_only_and_assistant_uses_local_knowledge(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    class LoginResponse:
        status_code = 200
        def json(self):
            return {
                "access_token": "server-secret-token",
                "id": "tester",
                "email": "tester@example.com",
                "user_grade": "pro_coin",
                "membership_policy": {"policy_version": "test"},
            }

    observed = {}
    def fake_post(url, *, json, timeout):
        observed.update({"url": url, "body": deepcopy(json), "timeout": timeout})
        return LoginResponse()

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {"paper_trading": True})
    monkeypatch.setattr(service_module.requests, "post", fake_post)
    services = ApplicationServices()
    result = services.authenticate(username="tester", password="login-password")
    assert result["authenticated"] is True
    assert "login-password" not in json.dumps(result)
    token_text = (tmp_path / "token.json").read_text(encoding="utf-8")
    assert "server-secret-token" in token_text
    assert "login-password" not in token_text
    audit_text = (tmp_path / "audit" / "web_ui_commands.jsonl").read_text(encoding="utf-8")
    assert "server-secret-token" not in audit_text
    assert "login-password" not in audit_text
    assert observed["url"].startswith("https://daltrading.net/")

    answer = services.ask_assistant(
        question="백테스트와 PAPER 차이는?", service="ai_custom", explanation_level="beginner",
    )
    assert answer["provider_called"] is False
    assert "미래 수익" in answer["answer"]


def test_interactive_ai_is_explicit_budgeted_and_cached(tmp_path):
    calls = []
    class Response:
        ok = True
        content = "근거 기반 심층분석"
        provider = "deepseek"
        model = "deepseek-chat"
        usage = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
        error = None
    class Adapter:
        model = "deepseek-chat"
        def is_ready(self): return True
        def chat_text(self, system, prompt, max_tokens): calls.append((system, prompt, max_tokens)); return Response()
    class Router:
        spec = type("Spec", (), {"provider": "deepseek"})()
        adapter = Adapter()
    service = InteractiveAIService(data_dir=tmp_path, router_factory=lambda settings, workload: Router())
    settings = {"ai_cost_control": {"max_daily_interactive_calls": 1, "max_monthly_interactive_calls": 2, "interactive_cache_sec": 900}}
    first = service.ask(settings=settings, workload="assistant", question="현재 위험?", context="검증된 데이터", system_prompt="근거만", max_tokens=500)
    second = service.ask(settings=settings, workload="assistant", question="현재 위험?", context="검증된 데이터", system_prompt="근거만", max_tokens=500)
    assert first["provider_called"] is True and first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert len(calls) == 1
    assert service.status(settings)["daily_used"] == 1
    with pytest.raises(RuntimeError, match="budget_exceeded"):
        service.ask(settings=settings, workload="assistant", question="다른 질문", context="검증된 데이터", system_prompt="근거만", max_tokens=500)


def _complete_web_strategy_rules():
    return {
        "decision_timeframe": "15m",
        "entry": "RSI 30 이하 LONG",
        "exit": "RSI 55 이상 청산",
        "stop_loss": "1%",
        "take_profit": "2%",
        "position_size": "5%",
        "market_conditions": "횡보장",
        "target_scope": "exchange:binance",
        "signal_mode": "independent",
        "entry_signal": "LONG",
        "executable_entry": {"all": [{"field": "rsi", "operator": "lte", "value": 30}]},
        "executable_exit": {"all": [{"field": "rsi", "operator": "gte", "value": 55}]},
    }


def test_web_strategy_full_state_machine_and_active_delete_guard(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    class StrategyRefreshBridge(DetachedRuntimeBridge):
        def __init__(self):
            self.refresh_calls = 0

        def refresh_strategies(self):
            self.refresh_calls += 1
            return {"ok": True, "runtime_attached": True, "active_count": 1}

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    bridge = StrategyRefreshBridge()
    services = ApplicationServices(account="tester", runtime_bridge=bridge)
    created = services.submit_strategy(
        scope="binance", name="Web RSI", rules=_complete_web_strategy_rules(),
        source_kind="manual", source_reference="web-ui://test",
    )
    key, version_id = created["strategy_key"], created["version_id"]
    assert created["status"] == "analyzed"
    approved = services.strategy_action(
        scope="binance", strategy_key=key, version_id=version_id, action="approve",
    )
    assert approved["status"] == "approved"
    paper = services.record_strategy_paper_validation(
        scope="binance", strategy_key=key, version_id=version_id,
        trades=3, guardrail_violations=0, metrics={"net_pnl": 1.2},
    )
    assert paper["status"] == "paper_validated"
    active = services.strategy_action(
        scope="binance", strategy_key=key, version_id=version_id,
        action="activate", live_confirmation=True,
    )
    assert active["status"] == "active"
    assert active["runtime_refresh"]["ok"] is True
    with pytest.raises(ValueError, match="적용 중"):
        services.delete_strategy(scope="binance", strategy_key=key)
    deactivated = services.strategy_action(
        scope="binance", strategy_key=key, version_id=version_id, action="deactivate",
    )
    assert deactivated["status"] == "paper_validated"
    assert services.delete_strategy(scope="binance", strategy_key=key)["deleted"] == "strategy"
    assert bridge.refresh_calls == 4


def test_strategy_text_source_and_noahstrategy_round_trip(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    settings = {"ai_custom_features": {"profile": "standard", "overrides": {}}}
    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: deepcopy(settings))
    services = ApplicationServices(account="tester")
    analyzed = services.analyze_strategy_source(
        source_kind="text",
        value="RSI 30 이하에서 LONG 진입, RSI 55 이상 청산, 손절 1%, 익절 2%, 포지션 5%, 횡보장 Binance",
    )
    assert analyzed["rules"]["executable_entry"]
    created = services.submit_strategy(
        scope="binance", name="Source RSI", rules=analyzed["rules"],
        source_kind="text", source_reference="pasted.txt",
    )
    exported = services.export_strategy_package(
        scope="binance", strategy_key=created["strategy_key"], version_id=created["version_id"],
    )
    imported = services.import_strategy_package(
        scope="unified", file_name="roundtrip.noahstrategy", package=exported["package"],
    )
    assert imported["status"] in {"analyzed", "needs_clarification"}
    assert imported["source_reference"] == "roundtrip.noahstrategy"


def test_web_historical_validation_uses_market_data_and_cannot_replace_paper(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    class HistoricalProvider:
        def get_candles(self, source, market_type, symbol, interval, limit):
            assert source == "binance"
            assert market_type == "futures"
            candles = []
            for index in range(120):
                close = 100 + ((index % 20) - 10) * 2
                candles.append(CandleContract(
                    source="binance", market_type="futures", symbol=symbol, interval=interval,
                    open_time=index * 60_000, close_time=index * 60_000 + 59_999,
                    open=close - 1, high=close + 2, low=close - 2, close=close,
                    volume=1000, closed=True, sequence=index,
                ))
            return CandleSnapshotContract(source="binance", symbol=symbol, interval=interval, candles=candles)

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {})
    services = ApplicationServices(account="tester", historical_market_data=HistoricalProvider())
    created = services.submit_strategy(
        scope="binance", name="Historical RSI", rules=_complete_web_strategy_rules(),
        source_kind="manual", source_reference="web-ui://test",
    )
    key, version_id = created["strategy_key"], created["version_id"]
    services.strategy_action(scope="binance", strategy_key=key, version_id=version_id, action="approve")
    validated = services.run_strategy_historical_validation(
        scope="binance", strategy_key=key, version_id=version_id, symbol="BTCUSDT", limit=120,
    )
    execution = validated["execution_validation"]
    assert execution["mode"] == "historical_replay"
    assert execution["metrics"]["future_performance_guaranteed"] is False
    with pytest.raises(ValueError, match="실행 검증|PAPER"):
        services.strategy_action(
            scope="binance", strategy_key=key, version_id=version_id,
            action="activate", live_confirmation=True,
        )


def test_noah_base_overlay_skips_impossible_replay_and_can_start_forward_paper(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    class HistoricalProvider:
        @staticmethod
        def get_candles(*_args, **_kwargs):
            raise AssertionError("Noah-base overlay must not request standalone replay candles")

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {})
    services = ApplicationServices(account="tester", historical_market_data=HistoricalProvider())
    rules = deepcopy(_complete_web_strategy_rules())
    rules.update({
        "signal_mode": "confirm",
        "entry_signal": "",
        "executable_entry": {"all": [], "any": []},
        "independent_entries": {},
        "source_grounding": {
            "status": "user_declared_override",
            "confirmed_by_user": True,
        },
    })
    created = services.submit_strategy(
        scope="binance", name="Noah base risk exit", rules=rules,
        source_kind="manual", source_reference="web-ui://noah-base-overlay",
    )
    key, version_id = created["strategy_key"], created["version_id"]
    approved = services.strategy_action(
        scope="binance", strategy_key=key, version_id=version_id, action="approve",
    )

    readiness = approved["paper_execution_readiness"]
    assert readiness["ready"] is True
    assert readiness["validation_subject"] == "noah_base_with_custom_risk_exit"
    assert readiness["historical_validation_applicable"] is False
    with pytest.raises(ValueError, match="독립 과거재생 대상이 아닙니다"):
        services.run_strategy_historical_validation(
            scope="binance", strategy_key=key, version_id=version_id,
            source="binance", market_type="futures", symbol="BTCUSDT", limit=120,
        )

    observing = services.strategy_action(
        scope="binance", strategy_key=key, version_id=version_id, action="start_paper",
    )
    assert observing["status"] == "paper_observing"
    assert observing["paper_observation_started_at"]


@pytest.mark.parametrize(
    ("venue", "market_type", "symbol", "interval", "currency"),
    [
        ("binance", "futures", "BTCUSDT", "15m", "USDT"),
        ("upbit", "spot", "BTCKRW", "15m", "KRW"),
        ("bithumb", "spot", "BTCKRW", "30m", "KRW"),
        ("coinone", "spot", "BTCKRW", "15m", "KRW"),
        ("bybit", "futures", "BTCUSDT", "15m", "USDT"),
        ("bitget", "futures", "BTCUSDT", "15m", "USDT"),
        ("okx", "futures", "BTCUSDT", "15m", "USDT"),
    ],
)
def test_strategy_historical_validation_uses_exact_venue_market_contract(
    tmp_path, monkeypatch, venue, market_type, symbol, interval, currency,
):
    import web_platform.application_services as service_module

    calls = []

    class HistoricalProvider:
        def get_candles(self, actual_venue, actual_market_type, actual_symbol, actual_interval, limit):
            calls.append((actual_venue, actual_market_type, actual_symbol, actual_interval, limit))
            candles = [
                CandleContract(
                    source=actual_venue, market_type=actual_market_type, symbol=actual_symbol,
                    interval=actual_interval, open_time=1788000000000 + index * 60_000,
                    close_time=1788000000000 + index * 60_000 + 59_999, open=100, high=104,
                    low=98, close=100 + (index % 4), volume=1000,
                    closed=True, sequence=index,
                )
                for index in range(120)
            ]
            return CandleSnapshotContract(
                source=actual_venue, symbol=actual_symbol,
                interval=actual_interval, candles=candles,
            )

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {})
    services = ApplicationServices(account="tester", historical_market_data=HistoricalProvider())
    scope = "binance" if venue == "binance" else "unified"
    created = services.submit_strategy(
        scope=scope, name=f"{venue} validation", rules={
            **_complete_web_strategy_rules(),
            "decision_timeframe": interval,
            "target_scope": f"exchange:{venue}" if venue == "binance" else "asset:crypto",
        }, source_kind="manual", source_reference=f"web-ui://{venue}",
    )
    services.strategy_action(
        scope=scope, strategy_key=created["strategy_key"],
        version_id=created["version_id"], action="approve",
    )
    result = services.run_strategy_historical_validation(
        scope=scope, strategy_key=created["strategy_key"], version_id=created["version_id"],
        source=venue, market_type=market_type, symbol=symbol, limit=120,
    )

    assert calls == [(venue, market_type, symbol, interval, 120)]
    metrics = result["execution_validation"]["metrics"]
    assert metrics["validation_source"] == venue
    assert metrics["validation_market_type"] == market_type
    assert metrics["validation_interval"] == interval
    assert metrics["quote_currency"] == currency
    chart = metrics["replay_visualization"]
    assert chart["status"] == "available"
    assert len(chart["candles"]) == 120
    assert chart["binding"]["version_id"] == created["version_id"]
    assert chart["binding"]["strategy_key"] == created["strategy_key"]
    assert not result.get("active")
    assert result["status"] in {"execution_validated", "execution_rejected"}
    assert result.get("paper_validation") is None
    assert chart["equity"][-1]["value"] == metrics["net_pnl_percent"]
    from trading.strategy_package import build_strategy_package
    package = build_strategy_package(result, passport={"execution_validation": result["execution_validation"]})
    assert "replay_visualization" not in package["passport"]["execution_validation"]["metrics"]
    assert "replay_visualization" in result["execution_validation"]["metrics"]
    assert package["import_contract"]["paper_required"] is True
    assert package["import_contract"]["active"] is False


@pytest.mark.parametrize("broker", ["kiwoom", "shinhan", "mirae", "kis"])
@pytest.mark.parametrize("symbol,asset_class", [("005930", "stock"), ("069500", "etf")])
@pytest.mark.parametrize("target_kind", ["connected", "specific"])
def test_web_stock_and_etf_historical_validation_use_each_selected_broker(
    tmp_path, monkeypatch, broker, symbol, asset_class, target_kind,
):
    import web_platform.application_services as service_module

    class StockHistoryBridge(DetachedRuntimeBridge):
        def __init__(self):
            self.calls = []

        def stock_candles(self, *, source, symbol, limit=300):
            self.calls.append((source, symbol, limit))
            rows = []
            for index in range(120):
                close = 70_000 + ((index % 20) - 10) * 500
                rows.append({
                    "date": f"2026{1 + index // 28:02d}{1 + index % 28:02d}",
                    "open": close - 100, "high": close + 500, "low": close - 500,
                    "close": close, "volume": 100_000,
                })
            return rows

    bridge = StockHistoryBridge()
    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {
        "enabled_stock_brokers": [broker], "selected_stock_broker": broker,
    })
    services = ApplicationServices(account="tester", runtime_bridge=bridge)
    rules = {**_complete_web_strategy_rules(), "target_scope": f"broker:{broker if target_kind == 'specific' else 'connected'}", "decision_timeframe": "1d"}
    created = services.submit_strategy(
        scope="unified", name="Stock RSI", rules=rules,
        source_kind="manual", source_reference="web-ui://stock-test",
    )
    services.strategy_action(
        scope="unified", strategy_key=created["strategy_key"],
        version_id=created["version_id"], action="approve",
    )
    validated = services.run_strategy_historical_validation(
        scope="unified", strategy_key=created["strategy_key"],
        version_id=created["version_id"], asset_class=asset_class, symbol=symbol, limit=120,
    )

    assert bridge.calls == [(broker, symbol, 120)]
    metrics = validated["execution_validation"]["metrics"]
    assert metrics["asset_class"] == asset_class
    assert metrics["validation_source"] == broker
    assert metrics["broker"] == broker
    assert metrics["exchange"] is None
    assert metrics["quote_currency"] == "KRW"
    assert metrics["validation_interval"] == "1d"
    assert metrics["cost_contract"] == "estimated_stock_paper_contract"
    chart = metrics["replay_visualization"]
    assert chart["status"] == "available"
    assert len(chart["candles"]) == 120
    assert chart["binding"]["version_id"] == created["version_id"]
    assert chart["equity"][-1]["value"] == metrics["net_pnl_percent"]
    assert not validated.get("active")
    assert validated["status"] in {"execution_validated", "execution_rejected"}
    assert validated.get("paper_validation") is None
    assert metrics["estimated_sell_tax_rate"] == pytest.approx(
        0.002 if asset_class == "stock" else 0.0
    )
    assert metrics["round_trip_cost_percent"] == pytest.approx(
        0.29 if asset_class == "stock" else 0.09
    )
    if target_kind == "specific":
        with pytest.raises(ValueError, match="전용 증권사"):
            services.run_strategy_historical_validation(
                scope="unified", strategy_key=created["strategy_key"],
                version_id=created["version_id"], asset_class=asset_class, symbol=symbol,
                source="kis" if broker != "kis" else "kiwoom",
            )


def test_stock_historical_validation_rejects_crypto_scope_and_new_short(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    class NoStockHistoryExpected(DetachedRuntimeBridge):
        def stock_candles(self, **kwargs):
            raise AssertionError("범위·방향 검사가 시세 조회보다 먼저 실행되어야 합니다.")

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {
        "enabled_stock_brokers": ["kiwoom"], "selected_stock_broker": "kiwoom",
    })
    services = ApplicationServices(account="tester", runtime_bridge=NoStockHistoryExpected())

    crypto = services.submit_strategy(
        scope="unified", name="Crypto only", rules={
            **_complete_web_strategy_rules(), "target_scope": "asset:crypto",
        }, source_kind="manual", source_reference="web-ui://scope-mismatch",
    )
    services.strategy_action(
        scope="unified", strategy_key=crypto["strategy_key"],
        version_id=crypto["version_id"], action="approve",
    )
    with pytest.raises(ValueError, match="암호화폐 전략을 주식·ETF 시세"):
        services.run_strategy_historical_validation(
            scope="unified", strategy_key=crypto["strategy_key"],
            version_id=crypto["version_id"], asset_class="stock", source="kiwoom",
        )

    short_rules = {
        **_complete_web_strategy_rules(),
        "target_scope": "asset:stock",
        "entry_signal": "SHORT",
    }
    stock_short = services.submit_strategy(
        scope="unified", name="Unsupported stock short", rules=short_rules,
        source_kind="manual", source_reference="web-ui://stock-short",
    )
    services.strategy_action(
        scope="unified", strategy_key=stock_short["strategy_key"],
        version_id=stock_short["version_id"], action="approve",
    )
    with pytest.raises(ValueError, match="신규 SHORT 진입을 지원하지 않습니다"):
        services.run_strategy_historical_validation(
            scope="unified", strategy_key=stock_short["strategy_key"],
            version_id=stock_short["version_id"], asset_class="stock", source="kiwoom",
        )


def test_crypto_historical_validation_rejects_stock_strategy_scope(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {})
    services = ApplicationServices(account="tester")
    stock = services.submit_strategy(
        scope="unified", name="Stock only", rules={
            **_complete_web_strategy_rules(), "target_scope": "asset:stock",
        }, source_kind="manual", source_reference="web-ui://stock-only",
    )
    services.strategy_action(
        scope="unified", strategy_key=stock["strategy_key"],
        version_id=stock["version_id"], action="approve",
    )
    with pytest.raises(ValueError, match="주식·ETF 전략을 암호화폐 시세"):
        services.run_strategy_historical_validation(
            scope="unified", strategy_key=stock["strategy_key"],
            version_id=stock["version_id"], asset_class="crypto", source="binance",
        )


def test_strategy_paper_ledger_auto_sync_requires_forward_observation(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {})
    services = ApplicationServices(account="tester")
    created = services.submit_strategy(
        scope="binance", name="Forward RSI", rules=_complete_web_strategy_rules(),
        source_kind="manual", source_reference="web-ui://paper-ledger",
    )
    services.strategy_action(
        scope="binance", strategy_key=created["strategy_key"], version_id=created["version_id"], action="approve",
    )
    rows = []
    now = service_module.datetime.now(service_module.timezone.utc)
    for index in range(3):
        rows.append({
            "event_id": f"paper-{index}", "scope": "binance", "exchange": "binance", "symbol": "BTCUSDT",
            "strategy_key": created["strategy_key"], "version_id": created["version_id"],
            "opened_at": (now - service_module.timedelta(days=8, minutes=index)).isoformat(),
            "closed_at": (now - service_module.timedelta(days=index)).isoformat(),
            "net_pnl": 1.0 if index != 1 else -0.25, "fees": 0.01,
            "guardrail_violations": 0, "execution_mode": "paper",
        })
    (tmp_path / "strategy_paper_outcomes.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8",
    )
    refresh_calls = []
    monkeypatch.setattr(services, "_refresh_runtime_after_strategy_change", lambda: refresh_calls.append(True) or {"ok": True})
    sync = services.sync_strategy_paper_results()
    assert sync["synced_versions"] == 1
    assert refresh_calls == [True]
    version = services.strategy_catalog()["strategies"][0]["versions"][0]
    assert version["paper_validation"]["passed"] is True
    assert version["paper_validation"]["metrics"]["manual_input_allowed"] is False
    assert version["paper_validation"]["metrics"]["seven_day"]["trades"] == 3


def test_strategy_paper_sync_never_adds_krw_and_usdt(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {})
    services = ApplicationServices(account="tester")
    created = services.submit_strategy(
        scope="unified", name="Mixed venue", rules={
            **_complete_web_strategy_rules(), "target_scope": "asset:crypto",
        }, source_kind="manual", source_reference="web-ui://mixed-currency",
    )
    services.strategy_action(
        scope="unified", strategy_key=created["strategy_key"],
        version_id=created["version_id"], action="approve",
    )
    now = service_module.datetime.now(service_module.timezone.utc)
    common = {
        "scope": "unified", "strategy_key": created["strategy_key"],
        "version_id": created["version_id"], "opened_at": now.isoformat(),
        "closed_at": now.isoformat(), "fees": 0.1, "guardrail_violations": 0,
        "execution_mode": "paper", "calculation_status": "valid",
    }
    rows = [
        {**common, "event_id": "krw", "exchange": "upbit", "symbol": "BTC/KRW", "net_pnl": 1000.0, "quote_currency": "KRW"},
        {**common, "event_id": "usdt", "exchange": "bybit", "symbol": "BTC/USDT:USDT", "net_pnl": 2.0, "quote_currency": "USDT"},
    ]
    (tmp_path / "strategy_paper_outcomes.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8",
    )

    assert services.sync_strategy_paper_results()["synced_versions"] == 1
    version = services.strategy_catalog()["strategies"][0]["versions"][0]
    metrics = version["paper_validation"]["metrics"]
    assert metrics["net_pnl"] is None
    assert metrics["currencies_comparable"] is False
    assert metrics["pnl_by_currency"] == {"KRW": 1000.0, "USDT": 2.0}
    evidence = {
        (row["exchange"], row["quote_currency"]): row
        for row in version["paper_evidence_by_venue"]
    }
    assert evidence[("upbit", "KRW")]["net_pnl"] == 1000.0
    assert evidence[("upbit", "KRW")]["win_rate"] == 100.0
    assert evidence[("bybit", "USDT")]["net_pnl"] == 2.0
    assert evidence[("bybit", "USDT")]["valid_trades"] == 1


def test_strategy_catalog_separates_unverified_paper_evidence_by_venue(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {})
    services = ApplicationServices(account="tester")
    created = services.submit_strategy(
        scope="unified", name="Evidence status", rules={
            **_complete_web_strategy_rules(), "target_scope": "asset:crypto",
        }, source_kind="manual", source_reference="web-ui://paper-evidence",
    )
    now = service_module.datetime.now(service_module.timezone.utc)
    common = {
        "scope": "unified", "exchange": "okx", "symbol": "BTC/USDT:USDT",
        "strategy_key": created["strategy_key"], "version_id": created["version_id"],
        "opened_at": now.isoformat(), "closed_at": now.isoformat(),
        "execution_mode": "paper", "quote_currency": "USDT",
    }
    rows = [
        {**common, "event_id": "valid", "net_pnl": -1.5, "fees": 0.2, "calculation_status": "valid"},
        {**common, "event_id": "legacy", "net_pnl": 0.0, "fees": 0.0, "calculation_status": "legacy_unverified"},
    ]
    (tmp_path / "strategy_paper_outcomes.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8",
    )

    version = services.strategy_catalog()["strategies"][0]["versions"][0]
    evidence = version["paper_evidence_by_venue"][0]
    assert evidence["exchange"] == "okx"
    assert evidence["recorded_trades"] == 2
    assert evidence["valid_trades"] == 1
    assert evidence["unverified_trades"] == 1
    assert evidence["losses"] == 1
    assert evidence["win_rate"] == 0.0
    assert evidence["net_pnl"] == -1.5
    assert version["paper_progress"]["trades"] == 1


def test_strategy_catalog_advances_paper_days_before_first_close(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {})
    services = ApplicationServices(account="tester")
    created = services.submit_strategy(
        scope="binance", name="Elapsed Paper", rules=_complete_web_strategy_rules(),
        source_kind="manual", source_reference="web-ui://paper-progress",
    )
    services.strategy_action(
        scope="binance", strategy_key=created["strategy_key"],
        version_id=created["version_id"], action="approve",
    )
    services.strategy_action(
        scope="binance", strategy_key=created["strategy_key"],
        version_id=created["version_id"], action="start_paper",
    )
    pipeline = services._strategy_pipeline("binance_private.json")
    version = pipeline._find(created["strategy_key"], created["version_id"])
    version["paper_observation_started_at"] = (
        service_module.datetime.now(service_module.timezone.utc)
        - service_module.timedelta(days=2)
    ).isoformat()
    pipeline._save()

    catalog_version = services.strategy_catalog()["strategies"][0]["versions"][0]

    assert catalog_version["paper_progress"]["trades"] == 0
    assert catalog_version["paper_progress"]["observation_days"] >= 2.0
    assert catalog_version["paper_progress"]["observing"] is True


def test_new_paper_observation_excludes_old_strategy_closes(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {})
    services = ApplicationServices(account="tester")
    created = services.submit_strategy(
        scope="binance", name="Fresh Paper", rules=_complete_web_strategy_rules(),
        source_kind="manual", source_reference="web-ui://fresh-paper",
    )
    services.strategy_action(
        scope="binance", strategy_key=created["strategy_key"],
        version_id=created["version_id"], action="approve",
    )
    services.strategy_action(
        scope="binance", strategy_key=created["strategy_key"],
        version_id=created["version_id"], action="start_paper",
    )
    now = service_module.datetime.now(service_module.timezone.utc)
    pipeline = services._strategy_pipeline("binance_private.json")
    version = pipeline._find(created["strategy_key"], created["version_id"])
    version["paper_observation_started_at"] = (now - service_module.timedelta(days=1)).isoformat()
    pipeline._save()
    rows = [
        {
            "event_id": "old", "scope": "binance", "exchange": "binance", "symbol": "OLDUSDT",
            "strategy_key": created["strategy_key"], "version_id": created["version_id"],
            "opened_at": (now - service_module.timedelta(days=3)).isoformat(),
            "closed_at": (now - service_module.timedelta(days=2)).isoformat(),
                "net_pnl": 10.0, "fees": 0.0, "execution_mode": "paper",
                "cost_calculation_status": "recorded_contract",
        },
        {
            "event_id": "new", "scope": "binance", "exchange": "binance", "symbol": "NEWUSDT",
            "strategy_key": created["strategy_key"], "version_id": created["version_id"],
            "opened_at": (now - service_module.timedelta(hours=2)).isoformat(),
                "closed_at": now.isoformat(), "net_pnl": 1.0, "fees": 0.0,
                "execution_mode": "paper", "cost_calculation_status": "recorded_contract",
        },
    ]
    (tmp_path / "strategy_paper_outcomes.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8",
    )

    catalog_version = services.strategy_catalog()["strategies"][0]["versions"][0]

    assert catalog_version["paper_progress"]["trades"] == 1
    assert catalog_version["paper_validation"]["trades"] == 1


def test_web_life_finance_mutations_use_existing_manager(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {})
    services = ApplicationServices(account="tester")
    transaction = services.add_life_transaction(
        transaction_date="2026-08-14", amount=12000, transaction_type="지출",
        description="점심", method="카드",
    )
    goal = services.add_life_goal(name="비상금", target_amount=1000000, priority="높음")
    snapshot = services.life_finance_snapshot()
    assert {item["id"] for item in snapshot["transactions"]} == {transaction["id"]}
    assert {item["id"] for item in snapshot["goals"]} == {goal["id"]}
    assert services.delete_life_transaction(transaction["id"])["deleted"] is True
    assert services.delete_life_goal(goal["id"])["deleted"] is True


def test_account_query_service_reads_allowlisted_tables_and_trade_metrics(tmp_path):
    import sqlite3

    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE trade_log (id INTEGER, symbol TEXT, pnl REAL, net_pnl REAL, entry_time TEXT, exit_time TEXT, exchange TEXT, entry_price REAL, quantity REAL, reconciliation_status TEXT)")
        connection.execute("INSERT INTO trade_log VALUES (1, 'BTCUSDT', 3.5, 3.5, '2026-08-14', '2026-08-14', 'binance', 100, 1, 'exchange_confirmed')")
        connection.execute("CREATE TABLE ai_decisions (id INTEGER, symbol TEXT, decision_json TEXT, created_at TEXT)")
        connection.execute("INSERT INTO ai_decisions VALUES (1, 'BTCUSDT', '{\"signal\":\"HOLD\"}', '2026-08-14')")
    queries = AccountQueryService(str(db_path))
    overview = queries.trading_overview(asset_class="crypto")
    assert overview["closed_count"] == 1
    assert overview["pnl_by_currency"]["USDT"] == 3.5
    assert queries.table_rows("ai_decisions")[0]["decision_json"]["signal"] == "HOLD"
    with pytest.raises(ValueError, match="unsupported_query_table"):
        queries.table_rows("sqlite_master")


def test_stock_search_profile_preserves_legacy_recent_favorite_and_watchlist_settings(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    stored = {
        "stock_search_profile": {"recent_codes": ["000660"], "favorites": ["005930"]},
        "stock_auto_trading": {"symbols": ["069500"]},
    }

    class SettingsAwareBridge(DetachedRuntimeBridge):
        refreshed: dict | None = None

        def refresh_settings(self, settings):
            self.refreshed = deepcopy(settings)

    bridge = SettingsAwareBridge()
    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: deepcopy(stored))

    def fake_save(next_settings):
        stored.clear()
        stored.update(deepcopy(next_settings))
        return True

    monkeypatch.setattr(service_module, "save_settings", fake_save)
    monkeypatch.setattr(service_module, "patch_settings_paths", lambda changes: fake_save(_with_setting_paths(stored, changes)))
    services = ApplicationServices(account="tester", runtime_bridge=bridge)
    assert services.stock_search_profile() == {
        "schema_version": "1.0.0",
        "recent_codes": ["000660"],
        "favorites": ["005930"],
        "watchlist": ["069500"],
    }

    recent = services.update_stock_search_profile(action="recent_add", symbol="035420")
    assert recent["recent_codes"][:2] == ["035420", "000660"]
    favorite = services.update_stock_search_profile(action="favorite_toggle", symbol="035420")
    assert favorite["favorites"] == ["035420", "005930"]
    watched = services.update_stock_search_profile(action="watchlist_add", symbol="035420")
    assert watched["watchlist"] == ["069500", "035420"]
    assert stored["stock_auto_trading"]["symbols"] == ["069500", "035420"]
    assert stored["stock_auto_trading"]["watchlist"] == ["069500", "035420"]
    assert bridge.refreshed == stored

    unchanged = services.update_stock_search_profile(action="watchlist_add", symbol="035420")
    assert unchanged["changed"] is False
    with pytest.raises(ValueError, match="5~8"):
        services.update_stock_search_profile(action="recent_add", symbol="ABC")


def test_settings_save_and_credentials_refresh_attached_runtime(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    stored = {
        "paper_trading": True,
        "enabled_exchanges": ["binance"],
        "learning_enabled_exchanges": ["binance"],
        "trade_enabled_exchanges": [],
        "enabled_stock_brokers": [],
        "stock_broker_configs": {
            "kiwoom": {
                "enabled": False, "api_type": "openapi_plus", "api_version": "pykiwoom",
                "allow_live_order": False, "asset_types": ["stock", "etf"],
                "account_no": "", "password": "", "cert_password": "", "id": "",
            },
        },
    }

    class SettingsAwareBridge(DetachedRuntimeBridge):
        refreshed = []

        def refresh_settings(self, settings):
            self.refreshed.append(deepcopy(settings))

    bridge = SettingsAwareBridge()
    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: deepcopy(stored))

    def fake_save(next_settings):
        stored.clear()
        stored.update(deepcopy(next_settings))
        return True

    monkeypatch.setattr(service_module, "save_settings", fake_save)
    monkeypatch.setattr(service_module, "patch_settings_paths", lambda changes: fake_save(_with_setting_paths(stored, changes)))
    services = ApplicationServices(account="tester", runtime_bridge=bridge)
    snapshot = services.settings_snapshot()
    selected = services.update_settings(
        expected_revision=snapshot["revision"],
        changes={"enabled_stock_brokers": ["kiwoom"]},
    )
    assert bridge.refreshed[-1]["enabled_stock_brokers"] == ["kiwoom"]
    assert bridge.refreshed[-1]["stock_broker_configs"]["kiwoom"]["enabled"] is True

    services.update_credentials(
        expected_revision=selected["revision"],
        provider="stock:kiwoom",
        values={"account_no": "12345678", "password": "secret", "user_id": "tester"},
    )
    assert bridge.refreshed[-1]["stock_broker_configs"]["kiwoom"]["account_no"] == "12345678"


def test_ai_report_execution_quality_uses_cycle_metrics_without_starting_runtime():
    builds = []
    bridge = HeadlessRuntimeBridge(account="tester", factory=lambda account: builds.append(account))

    inactive = bridge.execution_quality_snapshot(service="blockchain", source="binance")
    assert inactive["status"] == "engine_inactive"
    assert inactive["rows"] == []
    assert builds == []

    class Engine:
        cycle_execution_metrics = {
            "binance": {
                "quality_score": 96.5,
                "attempted_orders": 4,
                "failed_orders": 0,
                "avg_latency_ms": 82.1,
                "avg_slippage_bps": 1.4,
                "anomalies": [],
            }
        }

    class App:
        trader = Engine()
        unified_trader = None

    bridge._app = App()
    active = bridge.execution_quality_snapshot(service="blockchain", source="binance")
    assert active["status"] == "available"
    assert active["rows"][0]["metric_scope"] == "latest_runtime_cycle"
    assert active["rows"][0]["quality_score"] == pytest.approx(96.5)
    assert builds == []


def test_stock_stop_remains_available_when_membership_blocks_new_commands(monkeypatch):
    stopped = []

    class Controller:
        def stop(self, source, close_all=False):
            stopped.append((source, close_all))
            return True

        @staticmethod
        def running_sources():
            return []

    class App:
        stock_runtime_controller = Controller()

        @staticmethod
        def assert_command_allowed(_source):
            raise RuntimeError("membership_exchange_not_allowed:kiwoom")

    bridge = HeadlessRuntimeBridge(account="tester")
    bridge._app = App()
    monkeypatch.setattr(bridge, "_settings", lambda: {})

    result = bridge.execute("trading.stop", {"source": "kiwoom", "close_all": False})
    assert result["command"] == "trading.stop"
    assert stopped == [("kiwoom", False)]


def test_stock_membership_policy_is_fail_closed_for_non_stock_grades():
    runtime = HeadlessTradingRuntime.__new__(HeadlessTradingRuntime)
    runtime.current_membership_policy = {}

    runtime.current_user_grade = "pro_coin"
    assert runtime._membership_allows("kiwoom") is False
    runtime.current_user_grade = "referral"
    assert runtime._membership_allows("kis") is False
    runtime.current_user_grade = "pro_stock"
    assert runtime._membership_allows("mirae") is True
    runtime.current_user_grade = "premium"
    assert runtime._membership_allows("shinhan") is True


def test_referral_runtime_reports_bybit_approval_state_and_allows_complete_approval():
    runtime = HeadlessTradingRuntime.__new__(HeadlessTradingRuntime)
    runtime._accepting_commands = True
    runtime.current_user_grade = "referral"
    runtime.current_membership_policy = {
        "allowed_exchanges": ["binance", "bybit"],
        "referral_programs": [
            {
                "exchange": "bybit",
                "enabled": True,
                "attribution_status": "pending",
                "can_configure_api": False,
            }
        ],
    }

    with pytest.raises(
        RuntimeError,
        match=r"^membership_exchange_approval_pending:bybit$",
    ):
        runtime.assert_command_allowed("bybit")

    runtime.current_membership_policy["referral_programs"][0].update(
        attribution_status="verified", can_configure_api=True
    )
    runtime.assert_command_allowed("bybit")


def test_settings_ai_help_is_noahai_specific_and_secret_safe(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    settings = {
        "selected_exchange": "binance",
        "binance_api_key": "configured-key",
        "binance_secret_key": "configured-secret",
        "advanced_trading": {"profitability_gate_enabled": True},
    }
    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: deepcopy(settings))
    services = ApplicationServices(account="tester")

    api_help = services.ask_assistant(
        question="바이낸스 API 발급과 연결을 초보자에게 설명해줘",
        service="settings",
        explanation_level="beginner",
    )["answer"]
    assert "출금 권한은 켜지 않습니다" in api_help
    assert "비밀키를 AI 대화에 붙여 넣지 마세요" in api_help
    assert "configured-key" not in api_help
    assert "configured-secret" not in api_help

    advanced_help = services.ask_assistant(
        question="고급 매매 계층과 가드레일은 어떻게 써?",
        service="settings",
        explanation_level="beginner",
    )["answer"]
    assert "NoahAI 고급 매매 계층" in advanced_help
    assert "PAPER" in advanced_help
def _with_setting_paths(settings, changes):
    updated = deepcopy(settings)
    for path, value in changes.items():
        target = updated
        parts = str(path).split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = deepcopy(value)
    return updated
