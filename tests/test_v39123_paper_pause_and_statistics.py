from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.paper_strategy_ledger import paper_position_execution_evidence
from trading.strategy_package import verify_strategy_package
from web_platform.application_services import ApplicationServices


def _rules() -> dict:
    return {
        "entry": "RSI < 30", "exit": "RSI > 55", "stop_loss": "1%",
        "take_profit": "2%", "position_size": "5%", "market_conditions": ["all"],
        "signal_mode": "confirm", "entry_signal": "LONG",
        "executable_entry": {"all": [{"field": "signal", "operator": "eq", "value": "LONG"}]},
        "exit_policy": {"mode": "strategy_owned"},
        "engine_settings": {"_unit": "percent_points", "tp_percent": 2, "sl_percent": 1},
    }


def _approved_pipeline(tmp_path):
    pipeline = CustomStrategyPipeline(storage_path=str(tmp_path / "strategies.json"))
    created = pipeline.submit(name="pause resume", rules=_rules())
    pipeline.approve(created["strategy_key"], created["version_id"], approved_by="tester")
    return pipeline, created["strategy_key"], created["version_id"]


def test_paper_pause_and_resume_preserve_current_evidence_and_active_time(tmp_path):
    pipeline, key, version_id = _approved_pipeline(tmp_path)
    pipeline.start_paper_observation(key, version_id)
    progress = pipeline.record_paper_validation(
        key, version_id, trades=70,
        metrics={"require_forward_days": True, "observation_days": 3.25},
    )
    assert progress["paper_validation"]["completion_status"] == "in_progress"
    paused = pipeline.stop_paper_observation(key, version_id)
    assert paused["status"] == "paper_paused"
    assert paused["paper_validation"]["trades"] == 70
    assert len(paused["paper_observation_windows"]) == 1
    assert paused["paper_observation_windows"][0]["stopped_at"]

    resumed = pipeline.start_paper_observation(key, version_id)
    assert resumed["status"] == "paper_observing"
    assert resumed["paper_validation"]["trades"] == 70
    assert len(resumed["paper_observation_windows"]) == 2
    assert resumed["paper_observation_windows"][0]["stopped_at"]
    assert resumed["paper_observation_windows"][1]["stopped_at"] is None


def test_new_paper_attempt_archives_previous_attempt_instead_of_deleting_it(tmp_path):
    pipeline, key, version_id = _approved_pipeline(tmp_path)
    first = pipeline.start_paper_observation(key, version_id)
    first_attempt = first["paper_observation_attempt_id"]
    pipeline.record_paper_validation(
        key, version_id, trades=5,
        metrics={"require_forward_days": True, "observation_days": 2.0},
    )
    pipeline.stop_paper_observation(key, version_id)
    restarted = pipeline.restart_paper_observation(key, version_id)
    assert restarted["status"] == "paper_observing"
    assert restarted["paper_observation_attempt_id"] != first_attempt
    assert restarted["paper_validation"] is None
    assert restarted["paper_validation_attempt_history"][0]["paper_validation"]["trades"] == 5
    assert restarted["paper_validation_history"][0]["trades"] == 5


def test_starting_sibling_version_requires_explicit_pause_and_preserves_attempt(tmp_path):
    pipeline, key, v1_id = _approved_pipeline(tmp_path)
    v1 = pipeline.start_paper_observation(key, v1_id)
    pipeline.record_paper_validation(
        key, v1_id, trades=4,
        metrics={"require_forward_days": True, "observation_days": 2.0},
    )
    v2 = pipeline.submit(name="pause resume v2", rules=_rules(), strategy_key=key)
    pipeline.approve(key, v2["version_id"], approved_by="tester")

    with pytest.raises(ValueError, match="PAPER 일시정지"):
        pipeline.start_paper_observation(key, v2["version_id"])

    preserved = pipeline.get_version(key, v1_id)
    assert preserved["status"] == "paper_observing"
    assert preserved["paper_observation_attempt_id"] == v1["paper_observation_attempt_id"]
    assert preserved["paper_validation"]["trades"] == 4
    assert preserved["paper_observation_windows"][-1]["stopped_at"] is None
    assert pipeline.paper_versions == {key: v1_id}

    pipeline.stop_paper_observation(key, v1_id)
    started_v2 = pipeline.start_paper_observation(key, v2["version_id"])
    assert started_v2["status"] == "paper_observing"
    assert pipeline.get_version(key, v1_id)["paper_validation"]["trades"] == 4


def test_legacy_stopped_attempt_migrates_to_resumable_pause(tmp_path):
    pipeline, key, version_id = _approved_pipeline(tmp_path)
    pipeline.start_paper_observation(key, version_id)
    pipeline.record_paper_validation(
        key, version_id, trades=70,
        metrics={"require_forward_days": True, "observation_days": 3.25},
    )
    pipeline.stop_paper_observation(key, version_id)
    path = tmp_path / "strategies.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = payload["strategies"][key][0]
    version["status"] = "execution_validated"
    version.pop("paper_observation_windows", None)
    payload["paper_versions"] = {}
    path.write_text(json.dumps(payload), encoding="utf-8")

    restored = CustomStrategyPipeline(storage_path=str(path)).get_version(key, version_id)
    assert restored["status"] == "paper_paused"
    assert restored["paper_validation"]["trades"] == 70
    assert len(restored["paper_observation_windows"]) == 1


def test_strategy_execution_evidence_export_is_version_scoped_and_private(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: {})
    services = ApplicationServices(account="tester")
    version = services.submit_strategy(
        scope="binance", name="Evidence", rules=_rules(),
        source_kind="manual", source_reference="web-ui://evidence",
    )
    now = datetime.now(timezone.utc)
    rows = [{
        "event_id": "paper-evidence-1", "scope": "binance",
        "execution_scope": "binance", "strategy_scope": "binance",
        "exchange": "binance", "symbol": "BTCUSDT",
        "strategy_key": version["strategy_key"], "version_id": version["version_id"],
        "opened_at": (now - timedelta(minutes=15)).isoformat(),
        "closed_at": now.isoformat(), "entry_price": 100.0, "exit_price": 101.0,
        "quantity": 2.0, "side": "LONG", "leverage": 3,
        "gross_pnl": 2.0, "fees": 0.2, "estimated_slippage": 0.1,
        "estimated_taxes": 0.0, "net_pnl": 1.7, "net_pnl_percent": 0.85,
        "entry_reason": "custom entry matched", "exit_reason": "time profit",
        "entry_market_regime": "bull", "entry_regime_scope": "market",
        "entry_signal_source": "custom_strategy",
        "sizing_policy_reason": "account_risk_budget",
        "sizing_target_notional": 220.0, "sizing_final_notional": 200.0,
        "sizing_limiting_reasons": ["account_notional_cap"],
        "tp_price": 102.0, "sl_price": 99.0,
        "effective_tp_fraction": 0.02, "effective_sl_fraction": 0.01,
        "smart_exit_source": "time_profit", "smart_exit_reason": "15m",
        "quote_currency": "USDT", "execution_mode": "paper",
        "calculation_status": "valid", "cost_calculation_status": "recorded_contract",
    }, {
        "event_id": "other-version", "scope": "binance",
        "strategy_scope": "binance", "exchange": "binance", "symbol": "ETHUSDT",
        "strategy_key": version["strategy_key"], "version_id": "different",
        "opened_at": now.isoformat(), "closed_at": now.isoformat(),
        "net_pnl": 99.0, "execution_mode": "paper", "calculation_status": "valid",
    }]
    ledger = tmp_path / "strategy_paper_outcomes.jsonl"
    ledger.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    exported = services.export_strategy_execution_evidence(
        scope="binance", strategy_key=version["strategy_key"], version_id=version["version_id"],
    )
    payload = json.loads(exported["evidence_json"])
    assert payload["evidence_scope"]["trade_count"] == 1
    trade = payload["trades"][0]
    assert trade["holding_seconds"] == 900.0
    assert trade["leverage"] == 3
    assert trade["entry_notional"] == 200.0
    assert trade["entry_market_regime"] == "bull"
    assert trade["sizing_final_notional"] == 200.0
    assert trade["sizing_limiting_reasons"] == ["account_notional_cap"]
    assert trade["smart_exit_source"] == "time_profit"
    assert payload["privacy_boundary"]["share_package_contains_trade_rows"] is False
    encoded = exported["evidence_json"]
    assert "api_credentials" in encoded
    assert "exchange_order_id\"" in encoded
    assert "position_id" not in encoded


def test_paper_position_evidence_keeps_only_bounded_decision_context():
    evidence = paper_position_execution_evidence({
        "leverage": 4,
        "tp_price": 105.0,
        "sl_price": 98.0,
        "custom_strategy_rules": {"entry_signal": "LONG"},
        "entry_evidence": {
            "signal_source": "custom_strategy",
            "trade_candidate": {
                "reason": "entry matched", "market_regime": "bull",
                "regime_scope": "both", "private_prompt": "must not escape",
            },
            "position_sizing": {
                "reason": "account_risk_budget", "target_notional": 250.0,
                "final_notional": 200.0,
                "limiting_reasons": ["account_notional_cap"],
                "account_balance": 123456.0,
            },
        },
        "exit_policy": {
            "effective": {"tp_fraction": 0.05, "sl_fraction": 0.02, "source": "custom"},
            "last_exit_decision": {"source": "smart_exit", "reason": "trend_reversal"},
        },
    })
    assert evidence["entry_market_regime"] == "bull"
    assert evidence["entry_regime_scope"] == "both"
    assert evidence["sizing_final_notional"] == 200.0
    assert evidence["sizing_limiting_reasons"] == ["account_notional_cap"]
    assert evidence["smart_exit_reason"] == "trend_reversal"
    assert "private_prompt" not in evidence
    assert "account_balance" not in evidence


def test_paper_statistics_are_scoped_by_mode_venue_asset_and_currency(tmp_path):
    now = datetime.now(timezone.utc)
    rows = []
    crypto = ["binance", "upbit", "bithumb", "bybit", "bitget", "okx"]
    brokers = ["kiwoom", "shinhan", "mirae", "kis"]
    for index, venue in enumerate(crypto + brokers):
        is_krw = venue in {"upbit", "bithumb", *brokers}
        rows.append({
            "event_id": f"paper-{venue}", "scope": "unified", "exchange": venue,
            "symbol": "005930" if venue in brokers else ("BTC/KRW" if is_krw else "BTC/USDT:USDT"),
            "strategy_key": "", "version_id": "", "opened_at": (now - timedelta(minutes=20)).isoformat(),
            # The close timestamp must remain in the current local "today"
            # window even when this test runs just after midnight.
            "closed_at": now.isoformat(), "net_pnl": float(index + 1),
            "fees": 0.1, "entry_price": 100.0, "quantity": 2.0,
            "net_pnl_percent": 0.5, "quote_currency": "KRW" if is_krw else "USDT",
            "execution_mode": "paper", "calculation_status": "valid",
        })
    (tmp_path / "strategy_paper_outcomes.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8",
    )
    services = object.__new__(ApplicationServices)
    services.data_dir = tmp_path

    crypto_all = services._paper_statistics_snapshot(asset_class="crypto", period="today")
    assert crypto_all["execution_mode"] == "paper"
    assert crypto_all["closed_count"] == 6
    assert {group["source"] for group in crypto_all["groups"]} == set(crypto)
    assert set(crypto_all["pnl_by_currency"]) == {"KRW", "USDT"}
    assert crypto_all["execution_count"] == 0

    okx = services._paper_statistics_snapshot(asset_class="crypto", source="okx", period="today")
    assert okx["closed_count"] == 1
    assert [group["source"] for group in okx["groups"]] == ["okx"]

    stock_all = services._paper_statistics_snapshot(asset_class="stock", period="today")
    assert stock_all["closed_count"] == 4
    assert {group["source"] for group in stock_all["groups"]} == set(brokers)
    assert stock_all["pnl_by_currency"] == {"KRW": 34.0}


def test_web_surfaces_expose_paper_mode_without_mixing_live_import_or_baseline():
    operations = open("webui/src/components/Operations.tsx", encoding="utf-8").read()
    statistics = open("webui/src/components/TradingStatisticsWorkspace.tsx", encoding="utf-8").read()
    assert "dashboardStatisticsMode" in operations
    assert 'statisticsMode === "paper" ? t("가상 포지션")' in operations
    assert '>PAPER</button>' in statistics
    assert 'statisticsMode === "live" && <button' in statistics
    assert 'statisticsMode === "live" && <button type="button" onClick={importTrades}' in statistics


def test_workspace_paper_mode_uses_virtual_positions_and_close_ledger(tmp_path, monkeypatch):
    import web_platform.application_services as module

    class Bridge:
        @staticmethod
        def paper_position_snapshot(*, service, source):
            assert service == "blockchain"
            return {
                "source": source,
                "status": "success" if source == "binance" else "not_paper",
                "positions": [{"symbol": "BTCUSDT"}] if source == "binance" else [],
            }

    now = datetime.now(timezone.utc)
    row = {
        "event_id": "paper-binance-integration", "scope": "binance", "exchange": "binance",
        "symbol": "BTCUSDT", "opened_at": (now - timedelta(minutes=15)).isoformat(),
        "closed_at": now.isoformat(), "net_pnl": 1.25, "fees": 0.05,
        "entry_price": 100.0, "quantity": 2.0, "net_pnl_percent": 0.625,
        "quote_currency": "USDT", "execution_mode": "paper", "calculation_status": "valid",
    }
    (tmp_path / "strategy_paper_outcomes.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda _account: None)
    monkeypatch.setattr(module, "load_settings", lambda **_kwargs: {})
    services = module.ApplicationServices(account="tester", runtime_bridge=Bridge())
    services.queries.workspace = lambda service, feature, **kwargs: {
        "schema_version": "1.0.0", "service": service, "feature": feature,
        "source": kwargs.get("source", ""), "freshness": "test",
        "trading": {"open_position_count": 0, "closed_count": 0, "pnl_by_currency": {}},
    }

    snapshot = services.workspace_snapshot(
        service="blockchain", feature="blockchain.logs", statistics_mode="paper",
    )

    assert snapshot["statistics_view"]["execution_mode"] == "paper"
    assert snapshot["trading"]["execution_mode"] == "paper"
    assert snapshot["trading"]["open_position_count"] == 1
    assert snapshot["trading"]["closed_count"] == 1
    assert snapshot["trading"]["pnl_by_currency"] == {"USDT": 1.25}
    assert snapshot["paper_positions"] == [{"symbol": "BTCUSDT", "exchange": "binance"}]


def test_exported_package_keeps_archived_paper_attempt_and_remains_valid(tmp_path, monkeypatch):
    import web_platform.application_services as module

    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda _account: None)
    monkeypatch.setattr(module, "load_settings", lambda **_kwargs: {"paper_trading": True})
    monkeypatch.setattr(
        module, "resolve_ai_custom_features",
        lambda _settings: {"features": {"strategy_package": True}},
    )
    services = module.ApplicationServices(account="tester")
    created = services.submit_strategy(
        scope="binance", name="passport history", rules=_rules(),
        source_kind="manual", source_reference="test",
    )
    key, version_id = created["strategy_key"], created["version_id"]
    services.strategy_action(scope="binance", strategy_key=key, version_id=version_id, action="approve")
    services.strategy_action(scope="binance", strategy_key=key, version_id=version_id, action="start_paper")
    pipeline = services._strategy_pipeline("binance_private.json")
    pipeline.record_paper_validation(
        key, version_id, trades=70,
        metrics={"require_forward_days": True, "observation_days": 3.25},
    )
    services.strategy_action(scope="binance", strategy_key=key, version_id=version_id, action="stop_paper")
    services.strategy_action(scope="binance", strategy_key=key, version_id=version_id, action="restart_paper")

    exported = services.export_strategy_package(
        scope="binance", strategy_key=key, version_id=version_id,
    )["package"]

    assert exported["passport"]["paper_validation_attempt_history"][0]["paper_validation"]["trades"] == 70
    assert exported["passport"]["paper_validation_history"][0]["completion_status"] == "in_progress"
    assert verify_strategy_package(exported)["valid"] is True
