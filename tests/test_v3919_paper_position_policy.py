import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_focus_mode_overrides_stale_global_and_exchange_caps():
    from trading.position_limit_policy import effective_crypto_position_limit

    settings = {
        "position_mode": "focus",
        "max_positions": 3,
        "exchange_risk_overrides": {"binance": {"max_positions": 3}},
    }
    assert effective_crypto_position_limit(settings, "binance") == 1


def test_position_mode_sync_matches_legacy_all_exchange_contract():
    from trading.position_limit_policy import CRYPTO_EXCHANGES, synchronize_position_limit_settings

    settings = {"exchange_risk_overrides": {"binance": {"max_drawdown": 0.1}}}
    assert synchronize_position_limit_settings(settings, mode="focus") == 1
    assert settings["position_mode"] == "focus"
    assert settings["max_positions"] == 1
    assert all(settings["exchange_risk_overrides"][name]["max_positions"] == 1 for name in CRYPTO_EXCHANGES)
    assert settings["exchange_risk_overrides"]["binance"]["max_drawdown"] == 0.1

    assert synchronize_position_limit_settings(settings, mode="multi") == 3
    assert all(settings["exchange_risk_overrides"][name]["max_positions"] == 3 for name in CRYPTO_EXCHANGES)


def test_explicit_advanced_cap_two_remains_two():
    from trading.position_limit_policy import effective_crypto_position_limit, synchronize_position_limit_settings

    settings = {}
    synchronize_position_limit_settings(settings, max_positions=2)
    assert settings["position_mode"] == "multi"
    assert settings["max_positions"] == 2
    assert effective_crypto_position_limit(settings, "okx") == 2


def test_expert_multi_position_cap_can_be_five_or_ten_but_focus_stays_one():
    from trading.position_limit_policy import effective_crypto_position_limit, synchronize_position_limit_settings

    settings = {"position_mode": "multi", "max_positions": 3}
    assert synchronize_position_limit_settings(settings, max_positions=5) == 5
    assert effective_crypto_position_limit(settings, "bybit") == 5
    assert synchronize_position_limit_settings(settings, max_positions=10) == 10
    assert effective_crypto_position_limit(settings, "okx") == 10
    settings["position_mode"] = "focus"
    assert effective_crypto_position_limit(settings, "okx") == 1


def test_paper_position_capacity_ignores_stale_live_external_positions():
    from trading.execution_mode import ExecutionMode
    from trading.position_limit_policy import effective_position_count

    managed = {"PAPERUSDT": object()}
    stale_live_external = {"MANUAL1USDT", "MANUAL2USDT", "MANUAL3USDT"}
    assert effective_position_count(managed, stale_live_external, ExecutionMode.PAPER) == 1
    assert effective_position_count(managed, stale_live_external, ExecutionMode.LEARNING) == 1
    assert effective_position_count(managed, stale_live_external, ExecutionMode.LIVE) == 4


def test_web_settings_save_synchronizes_focus_cap_and_overrides(tmp_path, monkeypatch):
    from copy import deepcopy

    import web_platform.application_services as module

    stored = json.loads((ROOT / "config" / "settings_template.json").read_text(encoding="utf-8"))
    stored["position_mode"] = "multi"
    stored["max_positions"] = 3
    stored["exchange_risk_overrides"] = {"binance": {"max_positions": 3}}

    def write_path(payload, path, value):
        cursor = payload
        segments = path.split(".")
        for segment in segments[:-1]:
            cursor = cursor.setdefault(segment, {})
        cursor[segments[-1]] = deepcopy(value)

    def patch_paths(changes):
        for path, value in changes.items():
            write_path(stored, path, value)
        return True

    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda _account: None)
    monkeypatch.setattr(module, "load_settings", lambda **_kwargs: deepcopy(stored))
    monkeypatch.setattr(module, "patch_settings_paths", patch_paths)
    services = module.ApplicationServices(account="tester", runtime_bridge=module.DetachedRuntimeBridge())
    services._refresh_runtime_after_settings_save = lambda _settings: {"ok": True, "restart_required": False}
    snapshot = services.settings_snapshot()

    services.update_settings(expected_revision=snapshot["revision"], changes={"position_mode": "focus"})
    assert stored["position_mode"] == "focus"
    assert stored["max_positions"] == 1
    assert all(
        stored["exchange_risk_overrides"][exchange]["max_positions"] == 1
        for exchange in ("binance", "upbit", "bithumb", "bybit", "okx", "bitget")
    )


def test_binance_paper_entry_respects_focus_mode_before_market_calls():
    from trading.execution_mode import ExecutionMode
    from trading.trader import Trader

    trader = object.__new__(Trader)
    trader.settings = {"position_mode": "focus", "max_positions": 3}
    trader.paper_active_positions = {"BTCUSDT": object()}
    trader._execution_mode = lambda: ExecutionMode.PAPER
    assert trader._execute_paper_trade("ETHUSDT", {"price": 1, "qty": 1}) is False


def test_ai_custom_paper_candidate_cannot_bypass_multi_position_cap():
    from trading.execution_mode import ExecutionMode
    from trading.trader import Trader

    trader = object.__new__(Trader)
    trader.settings = {"position_mode": "multi", "max_positions": 3}
    trader.paper_active_positions = {
        symbol: object() for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    }
    trader._execution_mode = lambda: ExecutionMode.PAPER

    result = trader._execute_paper_trade("XRPUSDT", {
        "price": 1, "qty": 1,
        "_selected_custom_strategy_key": "trend-follow",
        "_selected_custom_strategy_version_id": "v1",
    })

    assert result is False
    assert set(trader.paper_active_positions) == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}


def test_binance_paper_open_and_close_preserve_active_strategy_version(monkeypatch):
    """The V1 label must be execution attribution, not UI-only decoration."""
    import trading.paper_strategy_ledger as ledger
    import trading.trader as trader_module
    from trading.execution_mode import ExecutionMode
    from trading.trader import Trader

    recorded = []
    trader = object.__new__(Trader)
    trader.settings = {
        "position_mode": "multi",
        "max_positions": 3,
        "default_tp": 0.01,
        "default_sl": 0.02,
    }
    trader.paper_active_positions = {}
    trader.paper_trade_stats = {
        "total_trades": 0,
        "total_pnl": 0.0,
        "winning_trades": 0,
        "losing_trades": 0,
    }
    trader._execution_mode = lambda: ExecutionMode.PAPER
    trader.binance_client = SimpleNamespace(get_current_price=lambda _symbol: 102.0)
    trader.log_event = lambda *_args, **_kwargs: None

    monkeypatch.setattr(trader_module, "emit_position_opened", lambda **_kwargs: ("event-open", "paper-position-v1"))
    monkeypatch.setattr(trader_module, "emit_position_closed", lambda **_kwargs: "event-close")
    monkeypatch.setattr(ledger, "record_paper_strategy_outcome", lambda **kwargs: recorded.append(kwargs) or kwargs)

    from trading.custom_strategy_runtime import stamp_trade_exit_rates
    opened = trader._execute_paper_trade("BTCUSDT", stamp_trade_exit_rates({
        "price": 100.0,
        "qty": 1.0,
        "side": "BUY",
        "_selected_custom_strategy": "추세 따라가기 V1",
        "_selected_custom_strategy_id": "trend-v1",
        "_selected_custom_strategy_key": "trend-follow",
        "_selected_custom_strategy_version_id": "v1",
    }, tp_fraction=0.01, sl_fraction=0.02, source="test_optimizer"))

    assert opened["status"] == "PAPER_FILLED"
    position = trader.paper_active_positions["BTCUSDT"]
    assert position.custom_strategy_name == "추세 따라가기 V1"
    assert position.custom_strategy_key == "trend-follow"
    assert position.custom_strategy_version_id == "v1"

    trader._monitor_paper_positions()

    assert "BTCUSDT" not in trader.paper_active_positions
    assert recorded[0]["strategy_key"] == "trend-follow"
    assert recorded[0]["version_id"] == "v1"
    assert recorded[0]["position_id"] == "paper-position-v1"
    assert recorded[0]["gross_pnl"] == pytest.approx(2.0)
    assert recorded[0]["net_pnl_percent"] == pytest.approx(1.93)
    assert recorded[0]["fees"] == pytest.approx(0.04)
    assert recorded[0]["estimated_slippage"] == pytest.approx(0.03)
    assert recorded[0]["net_pnl"] == pytest.approx(1.93)
    assert recorded[0]["entry_price"] == pytest.approx(100.0)
    assert recorded[0]["exit_price"] == pytest.approx(102.0)
    assert recorded[0]["quantity"] == pytest.approx(1.0)
    assert recorded[0]["side"] == "LONG"
    assert recorded[0]["quote_currency"] == "USDT"
    assert recorded[0]["calculation_status"] == "valid"


def test_binance_paper_accepts_explicitly_normalized_custom_exit_rates(monkeypatch):
    """저장 단위 변환은 전략 경계에서 끝나며 PAPER는 fraction 계약만 받는다."""
    import trading.trader as trader_module
    from trading.custom_strategy_runtime import (
        apply_engine_settings_to_trade_config,
        normalize_engine_settings,
        stamp_trade_exit_rates,
    )
    from trading.execution_mode import ExecutionMode
    from trading.trader import Trader

    trader = object.__new__(Trader)
    trader.settings = {"position_mode": "multi", "max_positions": 3}
    trader.paper_active_positions = {}
    trader._execution_mode = lambda: ExecutionMode.PAPER
    trader.binance_client = SimpleNamespace(get_current_price=lambda _symbol: 100.0)
    trader.log_event = lambda *_args, **_kwargs: None
    monkeypatch.setattr(trader_module, "emit_position_opened", lambda **_kwargs: ("event", "position"))

    base = stamp_trade_exit_rates(
        {"price": 100.0, "qty": 1.0, "side": "LONG"},
        tp_fraction=0.0018,
        sl_fraction=0.0020,
        source="optimizer",
    )
    custom = normalize_engine_settings({
        "_unit": "percent_points", "tp_percent": 0.3, "sl_percent": 0.15,
    })
    params = apply_engine_settings_to_trade_config(base, custom)
    params.update({
        "_selected_custom_strategy_version_id": "strategy-v1",
    })
    result = trader._execute_paper_trade("INJUSDT", params)

    assert result["status"] == "PAPER_FILLED"
    position = trader.paper_active_positions["INJUSDT"]
    assert position.tp_price == pytest.approx(100.3)
    assert position.sl_price == pytest.approx(99.85)


def test_binance_paper_blocks_out_of_range_default_exit_values(monkeypatch):
    import trading.trader as trader_module
    from trading.execution_mode import ExecutionMode
    from trading.trader import Trader

    trader = object.__new__(Trader)
    trader.settings = {"position_mode": "multi", "max_positions": 3}
    trader.paper_active_positions = {}
    trader._execution_mode = lambda: ExecutionMode.PAPER
    trader.binance_client = SimpleNamespace(get_current_price=lambda _symbol: 100.0)
    trader.log_event = lambda *_args, **_kwargs: None
    monkeypatch.setattr(trader_module, "emit_position_opened", lambda **_kwargs: ("event", "position"))

    assert trader._execute_paper_trade(
        "INJUSDT", {"price": 100.0, "qty": 1.0, "tp": 0.3, "sl": 0.15},
    ) is False
    assert trader.paper_active_positions == {}


def test_binance_paper_blocks_conflicting_exit_aliases_even_with_fraction_marker(monkeypatch):
    import trading.trader as trader_module
    from trading.custom_strategy_runtime import stamp_trade_exit_rates
    from trading.execution_mode import ExecutionMode
    from trading.trader import Trader

    trader = object.__new__(Trader)
    trader.settings = {"position_mode": "multi", "max_positions": 3}
    trader.paper_active_positions = {}
    trader._execution_mode = lambda: ExecutionMode.PAPER
    trader.binance_client = SimpleNamespace(get_current_price=lambda _symbol: 100.0)
    trader.log_event = lambda *_args, **_kwargs: None
    monkeypatch.setattr(trader_module, "emit_position_opened", lambda **_kwargs: ("event", "position"))

    params = stamp_trade_exit_rates(
        {"price": 100.0, "qty": 1.0},
        tp_fraction=0.0018,
        sl_fraction=0.0020,
        source="optimizer",
    )
    params["tp_percent"] = 0.3

    assert trader._execute_paper_trade("INJUSDT", params) is False
    assert trader.paper_active_positions == {}


def test_global_paper_runtime_pool_contains_active_v1_and_separate_candidate():
    from web_platform.headless_runtime import HeadlessTradingRuntime

    active = {
        "id": "trend-v1",
        "name": "추세 따라가기 V1",
        "version_id": "v1",
        "operation_mode": "standard",
        "priority": 8,
    }
    candidate = {
        "id": "trend-v2",
        "name": "추세 따라가기 V2 후보",
        "version_id": "v2",
        "operation_mode": "paper_validation",
        "priority": 7,
    }
    customizer = SimpleNamespace(
        get_active_strategy_pool=lambda: [active],
        get_paper_strategy_pool=lambda: [active, candidate],
    )
    trader = SimpleNamespace()
    unified = SimpleNamespace()
    runtime = object.__new__(HeadlessTradingRuntime)
    runtime.settings = {"paper_trading": True, "ai_custom_runtime": {"enabled": True}}
    runtime.strategy_customizer = customizer
    runtime.strategy_customizer_unified = SimpleNamespace(
        get_active_strategy_pool=lambda: [],
        get_paper_strategy_pool=lambda: [],
    )
    runtime.trader = trader
    runtime.unified_trader = unified

    pool = runtime.sync_custom_strategy_runtime_pools()

    assert [(row["version_id"], row["operation_mode"]) for row in pool] == [
        ("v1", "standard"),
        ("v2", "paper_validation"),
    ]
    assert trader.active_custom_strategy_pool == pool
    assert unified.active_custom_strategy_pool == pool
    assert runtime.active_custom_strategy_pool == pool


def test_unified_live_and_paper_limit_share_policy():
    from trading.unified_trader import UnifiedTrader

    trader = object.__new__(UnifiedTrader)
    trader.settings = {
        "position_mode": "focus",
        "max_positions": 3,
        "exchange_risk_overrides": {"bybit": {"max_positions": 3}},
    }
    assert trader._get_ai_max_positions("bybit") == 1


def test_paper_ledger_tail_reader_returns_only_latest_window(tmp_path):
    from trading.paper_strategy_ledger import read_paper_strategy_outcomes

    path = tmp_path / "strategy_paper_outcomes.jsonl"
    rows = [
        {"execution_mode": "paper", "event_id": f"event-{index}", "net_pnl": index}
        for index in range(1200)
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    result = read_paper_strategy_outcomes(limit=5, path=path)
    assert [row["event_id"] for row in result] == [f"event-{index}" for index in range(1195, 1200)]


def test_100mb_paper_ledger_repeated_refresh_reads_only_bounded_tail(tmp_path, monkeypatch):
    from trading.paper_strategy_ledger import read_paper_strategy_outcomes

    path = tmp_path / "strategy_paper_outcomes.jsonl"
    with path.open("wb") as handle:
        # A sparse 100 MiB historical prefix makes file-size-dependent reads
        # observable without making the regression suite write 100 MiB.
        handle.seek(100 * 1024 * 1024)
        handle.write(b"\n")
        for index in range(600):
            row = {
                "execution_mode": "paper",
                "event_id": f"event-{index}",
                "exchange": "binance",
                "net_pnl": index,
            }
            handle.write(json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n")

    real_open = Path.open
    bytes_read = [0]

    class CountingReader:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.handle, name)

        def read(self, size=-1):
            data = self.handle.read(size)
            bytes_read[0] += len(data)
            return data

    def counting_open(self, mode="r", *args, **kwargs):
        handle = real_open(self, mode, *args, **kwargs)
        if self == path and mode == "rb":
            return CountingReader(handle)
        return handle

    monkeypatch.setattr(Path, "open", counting_open)
    for _ in range(20):
        result = read_paper_strategy_outcomes(limit=500, path=path)
        assert result[0]["event_id"] == "event-100"
        assert result[-1]["event_id"] == "event-599"

    # Each refresh may read two 64 KiB chunks around a line boundary, but it
    # must never scale with the 100 MiB historical prefix.
    assert bytes_read[0] <= 20 * 2 * 64 * 1024


def test_crypto_account_snapshot_exposes_runtime_paper_positions():
    from web_platform.runtime_bridge import HeadlessRuntimeBridge

    class Client:
        @staticmethod
        def get_positions():
            return [{"symbol": "LIVEUSDT"}]

        @staticmethod
        def get_open_orders():
            return []

    manager = SimpleNamespace(
        get_exchange_balance=lambda *_args, **_kwargs: {"status": "success", "balance": {"USDT": 100}},
        get_exchange_client=lambda _source: Client(),
    )
    paper_position = SimpleNamespace(
        symbol="PAPERUSDT", side="LONG", quantity=2, entry_price=10,
        current_price=11, unrealized_pnl=2, leverage=1, execution_mode="paper",
    )
    app = SimpleNamespace(
        settings={"paper_trading": True},
        exchange_manager=manager,
        trader=SimpleNamespace(paper_active_positions={"PAPERUSDT": paper_position}),
        unified_trader=SimpleNamespace(paper_positions={}),
    )
    result = HeadlessRuntimeBridge._crypto_account_snapshot(app, "binance", force_refresh=False)
    assert result["positions"][0]["symbol"] == "LIVEUSDT"
    assert result["paper_positions"][0]["symbol"] == "PAPERUSDT"
    assert result["paper_positions_status"] == "success"


def test_crypto_account_snapshot_respects_per_exchange_paper_mode():
    from web_platform.runtime_bridge import HeadlessRuntimeBridge

    manager = SimpleNamespace(
        get_exchange_balance=lambda *_args, **_kwargs: {"status": "success", "balance": {"USDT": 100}},
        get_exchange_client=lambda _source: SimpleNamespace(
            get_positions=lambda: [], get_open_orders=lambda: [],
        ),
    )
    app = SimpleNamespace(
        settings={
            "paper_trading": False,
            "exchange_execution_modes": {"bybit": "paper"},
        },
        exchange_manager=manager,
        trader=SimpleNamespace(paper_active_positions={}),
        unified_trader=SimpleNamespace(
            paper_positions={"bybit": {"ETHUSDT": {"symbol": "ETHUSDT", "execution_mode": "paper"}}},
        ),
    )
    result = HeadlessRuntimeBridge._crypto_account_snapshot(app, "bybit", force_refresh=False)
    assert result["paper_positions_status"] == "success"
    assert result["paper_positions"][0]["symbol"] == "ETHUSDT"


def test_runtime_workspace_reads_paper_positions_without_account_network(monkeypatch):
    from web_platform.runtime_bridge import HeadlessRuntimeBridge

    bridge = HeadlessRuntimeBridge(account="tester")
    monkeypatch.setattr(bridge, "_settings", lambda: {
        "paper_trading": True,
        "position_mode": "focus",
        "max_positions": 3,
    })
    bridge._app = SimpleNamespace(
        active_custom_strategy_pool=[{
            "name": "추세 따라가기 V1", "version_id": "v1", "operation_mode": "standard",
        }],
        trader=SimpleNamespace(
            paper_active_positions={"BTCUSDT": {"symbol": "BTCUSDT", "execution_mode": "paper"}},
        ),
        unified_trader=SimpleNamespace(
            paper_positions={"bybit": {"ETHUSDT": {"symbol": "ETHUSDT", "execution_mode": "paper"}}},
        ),
    )

    binance = bridge.paper_position_snapshot(service="blockchain", source="binance")
    bybit = bridge.paper_position_snapshot(service="blockchain", source="bybit")
    assert binance["status"] == "success" and binance["positions"][0]["symbol"] == "BTCUSDT"
    assert bybit["status"] == "success" and bybit["positions"][0]["symbol"] == "ETHUSDT"
    assert binance["position_policy"] == {
        "mode": "focus", "limit": 1, "scope": "per_exchange_adapter",
    }
    assert bybit["position_policy"]["limit"] == 1
    assert binance["active_custom_strategies"][0]["version_id"] == "v1"


def test_workspace_delivers_paper_limit_without_account_refresh(tmp_path, monkeypatch):
    import web_platform.application_services as module

    class Bridge:
        @staticmethod
        def paper_position_snapshot(*, service, source):
            assert service == "blockchain" and source == "binance"
            return {
                "source": source,
                "status": "success",
                "positions": [{"symbol": "BTCUSDT"}],
                "position_policy": {
                    "mode": "multi", "limit": 3, "scope": "per_exchange_adapter",
                },
                "active_custom_strategies": [{
                    "name": "추세 따라가기 V1", "version_id": "v1", "operation_mode": "standard",
                }],
            }

    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda _account: None)
    monkeypatch.setattr(module, "load_settings", lambda **_kwargs: {})
    monkeypatch.setattr(module, "read_paper_strategy_outcomes", lambda **_kwargs: [])
    services = module.ApplicationServices(account="tester", runtime_bridge=Bridge())
    services.queries.workspace = lambda service, feature, **kwargs: {
        "schema_version": "1.0.0", "service": service, "feature": feature,
        "source": kwargs.get("source", ""), "freshness": "test",
    }

    result = services.workspace_snapshot(
        service="blockchain", feature="blockchain.source_workspaces", source="binance",
    )

    assert result["paper_positions"] == [{"symbol": "BTCUSDT"}]
    assert result["paper_position_policy"] == {
        "mode": "multi", "limit": 3, "scope": "per_exchange_adapter",
    }
    assert result["active_custom_strategies"][0]["version_id"] == "v1"


def test_assistant_runtime_uses_paper_positions_instead_of_stale_live_store(monkeypatch):
    from web_platform.runtime_bridge import HeadlessRuntimeBridge

    bridge = HeadlessRuntimeBridge(account="tester")
    monkeypatch.setattr(bridge, "_settings", lambda: {
        "paper_trading": True,
        "enabled_exchanges": ["binance"],
    })
    bridge._app = SimpleNamespace(
        trader=SimpleNamespace(
            active_positions={"LIVEUSDT": {"symbol": "LIVEUSDT"}},
            paper_active_positions={"PAPERUSDT": {"symbol": "PAPERUSDT", "side": "LONG"}},
            cycle_execution_metrics={},
        ),
        unified_trader=None,
        stock_runtime_controller=None,
        active_custom_strategy_pool=[],
    )
    monkeypatch.setattr(bridge, "snapshot", lambda: {
        "selected_source": "binance",
        "selected_sources": {"blockchain": "binance"},
        "execution_modes": {"binance": "paper"},
        "running_sources": ["binance"],
        "paper_trading": True,
    })

    result = bridge.assistant_context_snapshot(service="blockchain", source="binance")

    assert result["execution_mode"] == "PAPER"
    assert [row["symbol"] for row in result["managed_positions"]] == ["PAPERUSDT"]


def test_assistant_runtime_uses_stock_paper_positions_and_cycle_metrics(monkeypatch):
    from web_platform.runtime_bridge import HeadlessRuntimeBridge

    class Controller:
        def paper_position_snapshot(self, source):
            return {
                "source": source,
                "status": "success",
                "positions": [{"symbol": "005930", "side": "BUY"}],
            }

        def snapshot(self):
            return {
                "last_results": {
                    "kiwoom": {
                        "symbols": ["005930", "000660"],
                        "decisions": [{"symbol": "005930", "success": True}],
                        "orders_executed": 1,
                        "execution_metrics": {"quality_score": 98.0},
                    },
                },
            }

    bridge = HeadlessRuntimeBridge(account="tester")
    monkeypatch.setattr(bridge, "_settings", lambda: {"paper_trading": True})
    bridge._app = SimpleNamespace(
        trader=None,
        unified_trader=None,
        stock_runtime_controller=Controller(),
        active_custom_strategy_pool=[],
    )
    monkeypatch.setattr(bridge, "snapshot", lambda: {
        "selected_source": "kiwoom",
        "selected_sources": {"stock": "kiwoom"},
        "execution_modes": {"kiwoom": "paper"},
        "running_sources": ["kiwoom"],
        "paper_trading": True,
    })

    result = bridge.assistant_context_snapshot(service="stock", source="kiwoom")

    assert result["managed_positions"][0]["symbol"] == "005930"
    assert result["cycle_execution_metrics"][0]["candidate_count"] == 2
    assert result["cycle_execution_metrics"][0]["order_count"] == 1


def test_runtime_snapshot_exposes_source_specific_execution_modes(monkeypatch):
    from web_platform.runtime_bridge import HeadlessRuntimeBridge

    bridge = HeadlessRuntimeBridge(account="tester")
    monkeypatch.setattr(bridge, "_settings", lambda: {
        "paper_trading": False,
        "enabled_exchanges": ["binance", "bybit"],
        "exchange_execution_modes": {"binance": "learning", "bybit": "paper"},
    })
    snapshot = bridge.snapshot()
    assert snapshot["execution_modes"]["binance"] == "learning"
    assert snapshot["execution_modes"]["bybit"] == "paper"


def test_gateway_runtime_contract_delivers_execution_modes_to_web_ui():
    from fastapi.testclient import TestClient

    from web_platform.gateway import create_gateway_app

    token = "paper-runtime-contract-token-0123456789"
    app = create_gateway_app(token=token, runtime_provider=lambda: {
        "status": "ready",
        "service": "blockchain",
        "selected_source": "binance",
        "selected_sources": {"blockchain": "binance"},
        "enabled_sources": ["binance", "bybit"],
        "running_sources": ["binance", "bybit"],
        "enabled_sources_by_service": {"blockchain": ["binance", "bybit"]},
        "running_sources_by_service": {"blockchain": ["binance", "bybit"]},
        "credential_status": {"binance": True, "bybit": True},
        "configured_sources_by_service": {"blockchain": ["binance", "bybit"]},
        "execution_modes": {"binance": "learning", "bybit": "paper"},
        "paper_trading": False,
        "live_trading": False,
        "reason": "test",
    })

    response = TestClient(app).get(
        "/api/v1/runtime/snapshot",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["execution_modes"] == {"binance": "learning", "bybit": "paper"}


def test_web_ui_switches_paper_positions_and_statistics_without_extra_poll():
    source = (ROOT / "webui" / "src" / "components" / "LegacyFeatureWorkspaces.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "webui" / "src" / "styles.css").read_text(encoding="utf-8")
    strategy = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")

    assert 'paperPositionView ? t("가상 포지션")' in source
    assert 'paperMode ? t("가상 거래 통계 · 전체") : "학습 실행 상태"' in source
    assert "workspace?.paper_positions" in source
    assert "paper_position_policy" in source
    assert "활성 수와 무관" in source
    assert "신규 진입 차단" in source
    assert "LEARNING은 분석·전략·가드레일 판단만 기록" in source
    assert "workspace?.paper_statistics" in source
    assert "적용 중 버전은 PAPER에서 자동 실행 · 재적용 불필요" in source
    assert "paper-position-scroll" in styles
    assert "legacy-paper-history" in styles and "overflow-y: auto" in styles
    assert "최종 적용됨 · 앱 PAPER에서는 가상 실행" in strategy
