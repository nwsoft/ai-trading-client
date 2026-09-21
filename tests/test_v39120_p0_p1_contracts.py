from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.declarative_strategy_engine import DeclarativeStrategyEngine
from trading.exchange_learning_manager import ExchangeLearningManager
from trading.exchanges.adapters.upbit_spot_adapter import UpbitSpotAdapter
from trading.paper_position_store import load_positions, save_positions
from trading.paper_strategy_ledger import (
    normalize_paper_outcome_costs,
    read_paper_strategy_outcomes,
    record_paper_strategy_outcome,
)
from trading.execution_mode import ExecutionMode
from trading.profitability_validation import ProfitabilityValidator
from trading.tp_sl_manager import TpSlManager
from trading.trader import Position, PositionSide
from trading.trader import Trader
from trading.unified_trader import UnifiedTrader
from web_platform.application_services import ApplicationServices


def _rules():
    return {
        "entry": "RSI < 30", "exit": "RSI > 55", "stop_loss": "1%",
        "take_profit": "2%", "position_size": "5%", "market_conditions": ["all"],
        "signal_mode": "confirm", "entry_signal": "LONG",
        "executable_entry": {"all": [{"field": "signal", "operator": "eq", "value": "LONG"}]},
        "exit_policy": {"mode": "strategy_owned"},
        "engine_settings": {"_unit": "percent_points", "tp_percent": 2, "sl_percent": 1},
    }


def test_stopped_paper_validation_cannot_be_resurrected_by_late_sync(tmp_path):
    pipeline = CustomStrategyPipeline(storage_path=str(tmp_path / "strategies.json"))
    created = pipeline.submit(name="stop stays stopped", rules=_rules())
    key, version_id = created["strategy_key"], created["version_id"]
    pipeline.approve(key, version_id, approved_by="tester")
    pipeline.start_paper_observation(key, version_id)
    stopped = pipeline.stop_paper_observation(key, version_id)

    updated = pipeline.record_paper_validation(
        key, version_id, trades=2,
        metrics={"require_forward_days": True, "observation_days": 2.0},
    )
    assert updated["status"] == stopped["status"] == "paper_paused"
    assert key not in pipeline.paper_versions
    assert updated["paper_validation"]["trades"] == 2


def test_load_repairs_legacy_paper_status_without_execution_grant(tmp_path):
    path = tmp_path / "strategies.json"
    pipeline = CustomStrategyPipeline(storage_path=str(path))
    created = pipeline.submit(name="legacy split brain", rules=_rules())
    key, version_id = created["strategy_key"], created["version_id"]
    pipeline.approve(key, version_id, approved_by="tester")
    pipeline.start_paper_observation(key, version_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["paper_versions"] = {}
    path.write_text(json.dumps(payload), encoding="utf-8")

    repaired = CustomStrategyPipeline(storage_path=str(path))
    version = repaired.get_version(key, version_id)
    assert version["status"] == "paper_paused"
    assert version["paper_observation_stopped_at"]
    assert repaired.paper_versions == {}


def test_auto_sync_excludes_positions_opened_after_user_stopped_paper(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda _account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **_kwargs: {"paper_trading": True})
    services = ApplicationServices(account="tester")
    created = services.submit_strategy(
        scope="binance", name="bounded window", rules=_rules(),
        source_kind="manual", source_reference="test://bounded-window",
    )
    services.strategy_action(
        scope="binance", strategy_key=created["strategy_key"],
        version_id=created["version_id"], action="approve",
    )
    services.strategy_action(
        scope="binance", strategy_key=created["strategy_key"],
        version_id=created["version_id"], action="start_paper",
    )
    services.strategy_action(
        scope="binance", strategy_key=created["strategy_key"],
        version_id=created["version_id"], action="stop_paper",
    )
    version = services._strategy_pipeline("binance_private.json").get_version(
        created["strategy_key"], created["version_id"]
    )
    started = datetime.fromisoformat(version["paper_observation_started_at"])
    stopped = datetime.fromisoformat(version["paper_observation_stopped_at"])
    midpoint = started + (stopped - started) / 2
    rows = [
        {
            "event_id": "inside", "scope": "binance", "exchange": "binance", "symbol": "BTCUSDT",
            "strategy_key": created["strategy_key"], "version_id": created["version_id"],
            "opened_at": midpoint.isoformat(), "closed_at": stopped.isoformat(),
            "net_pnl": 1.0, "fees": 0.01, "execution_mode": "paper", "calculation_status": "valid",
        },
        {
            "event_id": "after-stop", "scope": "binance", "exchange": "binance", "symbol": "ETHUSDT",
            "strategy_key": created["strategy_key"], "version_id": created["version_id"],
            "opened_at": (stopped.timestamp() + 1), "closed_at": (stopped.timestamp() + 2),
            "net_pnl": 9.0, "fees": 0.01, "execution_mode": "paper", "calculation_status": "valid",
        },
    ]
    # Unix timestamps are not accepted by the ISO parser, so make the second
    # row unambiguously after the stop using ISO values.
    from datetime import timedelta
    rows[1]["opened_at"] = (stopped + timedelta(seconds=1)).isoformat()
    rows[1]["closed_at"] = (stopped + timedelta(seconds=2)).isoformat()
    assert services.sync_strategy_paper_results(outcomes=rows)["synced_versions"] == 1
    updated = services._strategy_pipeline("binance_private.json").get_version(
        created["strategy_key"], created["version_id"]
    )
    assert updated["status"] == "paper_paused"
    assert updated["paper_validation"]["trades"] == 1


def test_paper_open_position_round_trip_is_paper_only(tmp_path):
    path = tmp_path / "paper.json"
    position = Position(
        symbol="BTCUSDT", side=PositionSide.LONG, entry_price=100.0,
        current_price=101.0, quantity=0.5, leverage=2,
        unrealized_pnl=0.5, unrealized_pnl_percent=1.0,
        entry_time=datetime.now(timezone.utc), tp_price=102.0, sl_price=99.0,
        execution_mode="paper", custom_strategy_key="strategy-a",
        custom_strategy_version_id="v1",
    )
    save_positions(path, {"binance": {"BTCUSDT": position}})
    restored = load_positions(path, Position, PositionSide)
    assert restored["binance"]["BTCUSDT"].execution_mode == "paper"
    assert restored["binance"]["BTCUSDT"].custom_strategy_version_id == "v1"


def test_binance_switching_into_paper_restores_existing_snapshot(tmp_path):
    path = tmp_path / "paper.json"
    position = Position(
        symbol="ETHUSDT", side=PositionSide.LONG, entry_price=100.0,
        current_price=100.0, quantity=1.0, leverage=1,
        unrealized_pnl=0.0, unrealized_pnl_percent=0.0,
        entry_time=datetime.now(timezone.utc), execution_mode="paper",
    )
    save_positions(path, {"binance": {"ETHUSDT": position}})
    trader = object.__new__(Trader)
    trader.settings = {
        "paper_trading": False,
        "trade_enabled_exchanges": [],
        "paper_position_store_path_binance": str(path),
    }
    trader.paper_active_positions = {}
    trader.monitoring_flags = {}
    trader.log_event = lambda *_args, **_kwargs: None
    trader._paper_position_persistence_enabled = True
    trader.update_runtime_strategy_settings({"paper_trading": True})
    assert trader.paper_active_positions["ETHUSDT"].execution_mode == "paper"


def test_replayed_paper_close_is_idempotent_by_position_id(tmp_path, monkeypatch):
    import trading.paper_strategy_ledger as ledger_module

    monkeypatch.setattr(ledger_module, "get_app_data_dir", lambda: str(tmp_path))
    payload = {
        "scope": "binance", "exchange": "binance", "symbol": "BTCUSDT",
        "strategy_key": "strategy-a", "version_id": "v1",
        "position_id": "paper-position-1", "opened_at": "2026-09-03T00:00:00+00:00",
        "closed_at": "2026-09-03T00:10:00+00:00", "net_pnl": 1.0,
    }
    first = record_paper_strategy_outcome(**payload)
    second = record_paper_strategy_outcome(**payload)
    assert first["event_id"] == second["event_id"]
    assert len(read_paper_strategy_outcomes(path=tmp_path / "strategy_paper_outcomes.jsonl")) == 1


def test_upbit_ticker_cache_prevents_concurrent_style_request_burst():
    calls = []
    adapter = UpbitSpotAdapter("", "")
    adapter.is_connected = True
    adapter.exchange = SimpleNamespace(fetch_ticker=lambda symbol: calls.append(symbol) or {"last": 123.0})
    assert adapter.get_current_price("KRW-BTC") == 123.0
    assert adapter.get_current_price("BTC/KRW") == 123.0
    assert calls == ["BTC/KRW"]


def test_learning_events_use_incremental_store_without_large_checkpoint(tmp_path, monkeypatch):
    path = tmp_path / "ai_learning_data_upbit.json"
    monkeypatch.setattr(ExchangeLearningManager, "_get_exchange_learning_path", lambda self: str(path))
    manager = ExchangeLearningManager("upbit")
    manager.add_learning_data({"timestamp": datetime.now(timezone.utc), "symbol": "BTC/KRW", "signal": "HOLD", "confidence": 0.5})
    assert not path.exists()
    journal_rows = manager._store.recent('upbit')
    assert len(journal_rows) == 1
    assert journal_rows[0]["_learning_event_id"].startswith("learning_")
    reloaded = ExchangeLearningManager("upbit")
    assert len(reloaded.learning_history) == 1


def test_binance_tp_sl_audit_includes_algo_orders():
    client = SimpleNamespace(
        client=SimpleNamespace(futures_get_open_orders=lambda **_kwargs: []),
        get_open_algo_orders=lambda **_kwargs: [
            {"algoId": 1, "orderType": "TAKE_PROFIT_MARKET", "algoStatus": "NEW", "workingType": "MARK_PRICE"},
            {"algoId": 2, "orderType": "STOP_MARKET", "algoStatus": "NEW", "workingType": "MARK_PRICE"},
        ],
    )
    manager = TpSlManager(SimpleNamespace(binance_client=client, settings={}, logger=None))
    assert manager.audit_tp_sl_state("BTCUSDT") is True


def test_multiple_paper_strategies_receive_shared_slots_without_first_item_starvation():
    def strategy(name, version):
        return {
            "id": version, "strategy_key": name, "version_id": version, "name": name,
            "priority": 5, "operation_mode": "paper_validation", "signal_mode": "confirm",
            "entry_signal": "LONG", "target_scope": "asset:crypto", "market_regimes": ["all"],
            "rules": _rules(), "engine_settings": _rules()["engine_settings"],
        }
    pool = [strategy("one", "v1"), strategy("two", "v2")]
    common = {"signal": "LONG", "_paper_validation_rotation_index": 0}
    first = DeclarativeStrategyEngine.evaluate_strategy_pool(pool, common, asset_class="crypto", target="binance", market_regime="range")
    common["_paper_validation_rotation_index"] = 1
    second = DeclarativeStrategyEngine.evaluate_strategy_pool(pool, common, asset_class="crypto", target="binance", market_regime="range")
    assert [first["selected_version_id"], second["selected_version_id"]] == ["v1", "v2"]
    assert first["paper_validation_execution_model"] == "shared_round_robin"


@pytest.mark.parametrize(
    ("exchange", "symbol"),
    [
        ("upbit", "ADA/KRW"),
        ("bithumb", "ADA/KRW"),
        ("bybit", "ADA/USDT:USDT"),
        ("bitget", "ADA/USDT:USDT"),
        ("okx", "ADA/USDT:USDT"),
    ],
)
def test_unified_paper_monitor_updates_live_unrealized_pnl_before_close(exchange, symbol):
    position = Position(
        symbol=symbol, side=PositionSide.LONG, entry_price=1.0,
        current_price=1.0, quantity=100.0, leverage=1,
        unrealized_pnl=0.0, unrealized_pnl_percent=0.0,
        entry_time=datetime.now(timezone.utc), execution_mode="paper",
    )
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.settings = {}
    trader.logger = MagicMock()
    trader.exchange_manager = SimpleNamespace(
        get_current_price=lambda _symbol, _exchange: 1.02,
    )
    trader._execution_mode = lambda _exchange: ExecutionMode.PAPER
    trader._position_store = lambda _exchange: {position.symbol: position}
    trader._verify_and_repair_tp_sl = lambda _exchange: None
    trader._advanced_order_plan_decision_unified = lambda *_args: {"action": "hold"}
    trader._should_close_position_unified = lambda *_args: False

    trader._monitor_exchange_positions(exchange)

    assert position.current_price == pytest.approx(1.02)
    # 2.00 gross - 0.04 fee - 0.02 slippage = 1.94 net.
    assert position.unrealized_pnl == pytest.approx(1.94)
    assert position.unrealized_pnl_percent == pytest.approx(1.94)


def test_v39119_binance_zero_cost_row_is_reconstructed_but_explicitly_labeled():
    row = normalize_paper_outcome_costs({
        "scope": "binance", "exchange": "binance", "execution_mode": "paper",
        "calculation_status": "valid", "entry_price": 100.0, "exit_price": 101.0,
        "quantity": 1.0, "gross_pnl": 1.0, "net_pnl": 1.0,
        "fees": 0.0, "estimated_slippage": 0.0,
    })
    assert row["fees"] == pytest.approx(0.04)
    assert row["estimated_slippage"] == pytest.approx(0.03)
    assert row["net_pnl"] == pytest.approx(0.93)
    assert row["cost_calculation_status"] == "estimated_v39119_default_contract"


def test_strategy_evidence_cost_includes_fee_and_slippage_and_marks_estimate():
    row = normalize_paper_outcome_costs({
        "scope": "binance", "exchange": "binance", "execution_mode": "paper",
        "calculation_status": "valid", "entry_price": 100.0, "exit_price": 101.0,
        "quantity": 1.0, "gross_pnl": 1.0, "net_pnl": 1.0,
        "fees": 0.0, "estimated_slippage": 0.0,
    })
    evidence = ApplicationServices._strategy_paper_evidence_by_venue([row])[0]
    assert evidence["fees"] == pytest.approx(0.04)
    assert evidence["estimated_slippage"] == pytest.approx(0.03)
    assert evidence["total_cost"] == pytest.approx(0.07)
    assert evidence["estimated_cost_trades"] == 1


def test_strategy_evidence_does_not_disguise_unrecoverable_cost_as_exact_zero():
    row = normalize_paper_outcome_costs({
        "scope": "binance", "exchange": "binance", "execution_mode": "paper",
        "calculation_status": "valid", "net_pnl": 1.0, "fees": 0.0,
    })
    evidence = ApplicationServices._strategy_paper_evidence_by_venue([row])[0]
    assert row["cost_calculation_status"] == "unavailable"
    assert row["calculation_status"] == "legacy_unverified"
    assert evidence["unavailable_cost_trades"] == 1
    assert evidence["estimated_cost_trades"] == 0
    assert evidence["unverified_trades"] == 1
    assert evidence["valid_trades"] == 0


def test_profitability_uses_recent_exchange_samples_and_does_not_double_charge_net_pnl():
    trader = UnifiedTrader.__new__(UnifiedTrader)
    rows = [
        {"symbol": "OLD", "pnl": -99.0, "pnl_is_net": True, "entry_notional": 100.0},
        {"symbol": "NEW1", "pnl": 1.0, "pnl_is_net": True, "fees": 0.2, "entry_notional": 100.0},
        {"symbol": "NEW2", "pnl": 2.0, "pnl_is_net": True, "fees": 0.3, "entry_notional": 100.0},
    ]
    trader.recorder = SimpleNamespace(get_recent_trades=lambda **_kwargs: rows)
    selected = trader._get_local_trade_samples_unified("bitget", limit=2)
    assert [row["symbol"] for row in selected] == ["NEW1", "NEW2"]
    assert ProfitabilityValidator()._extract_trade_return(selected[0]) == pytest.approx(0.01)


@pytest.mark.parametrize("exchange", ["upbit", "bithumb", "bybit", "bitget", "okx"])
def test_unified_profitability_samples_are_requested_per_exchange(exchange):
    trader = UnifiedTrader.__new__(UnifiedTrader)
    recorder = MagicMock()
    recorder.get_recent_trades.return_value = [
        {"symbol": "RECENT", "pnl": 1.0, "pnl_is_net": True},
    ]
    trader.recorder = recorder

    rows = trader._get_local_trade_samples_unified(exchange, limit=200)

    assert rows[0]["symbol"] == "RECENT"
    recorder.get_recent_trades.assert_called_once_with(
        coin="", exchange=exchange, days=30,
    )


def test_unified_decision_recorder_receives_owning_exchange():
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.last_trade_decisions = {}
    trader.recorder = SimpleNamespace(save_ai_decision=MagicMock())

    trader._remember_trade_decision("upbit", "ARB/KRW", "hold", "test")

    trader.recorder.save_ai_decision.assert_called_once()
    args, kwargs = trader.recorder.save_ai_decision.call_args
    assert args[1] == "trade_runtime::upbit"
    assert args[2]["exchange"] == "upbit"
    assert kwargs["exchange"] == "upbit"


def test_binance_log_view_hides_legacy_decision_owned_by_another_exchange(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    today = datetime.now().astimezone().date().isoformat()
    log_path = tmp_path / "trading_binance.log"
    log_path.write_text(
        f"{today} 06:00:00 | INFO - [BTCUSDT] AI 결정 내역 저장 완료: trade_runtime::binance (ex=binance)\n"
        f"{today} 06:00:01 | INFO - [ARB/KRW] AI 결정 내역 저장 완료: trade_runtime::upbit (ex=binance)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        service_module, "get_exchange_log_file_path", lambda _source: str(log_path),
    )
    services = ApplicationServices(account="tester", runtime_bridge=service_module.DetachedRuntimeBridge())
    messages = [
        row["message"] for row in services.log_snapshot(
            service="blockchain", source="binance", lines=20,
        )["lines"]
    ]
    assert any("trade_runtime::binance" in row for row in messages)
    assert all("trade_runtime::upbit" not in row for row in messages)
