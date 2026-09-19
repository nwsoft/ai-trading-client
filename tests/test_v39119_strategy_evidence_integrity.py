from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.noah_strategy_ir import NoahStrategyIR
from trading.strategy_package import (
    build_strategy_package,
    serialize_strategy_package,
    verify_strategy_package,
)
from web_platform.application_services import ApplicationServices


def _rules() -> dict:
    return {
        "entry": "RSI 30 이하 LONG",
        "exit": "RSI 55 이상 청산",
        "stop_loss": "1%",
        "take_profit": "2%",
        "position_size": "5%",
        "market_conditions": ["NoahAI 판단"],
        "market_regimes": ["all"],
        "target_scope": "asset:crypto",
        "signal_mode": "independent",
        "entry_signal": "LONG",
        "exit_policy": {"mode": "strategy_owned"},
        "executable_entry": {
            "all": [{"field": "rsi", "operator": "lte", "value": 30}],
            "any": [],
        },
        "executable_exit": {
            "all": [{"field": "rsi", "operator": "gte", "value": 55}],
            "any": [],
        },
        "engine_settings": {
            "_unit": "percent_points", "tp_percent": 2, "sl_percent": 1,
        },
        "risk_model": {
            "risk_per_trade_percent": 2.0,
            "max_margin_usage_percent": 20.0,
            "max_leverage": 3,
        },
    }


def test_legacy_binance_execution_row_is_recovered_to_unique_unified_owner(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda _account: None)
    monkeypatch.setattr(
        service_module,
        "load_settings",
        lambda **_kwargs: {"ai_custom_features": {"strategy_package": True}},
    )
    services = ApplicationServices(account="tester")
    created = services.submit_strategy(
        scope="unified", name="six venue", rules=_rules(),
        source_kind="manual", source_reference="web-ui://scope-regression",
    )
    services.strategy_action(
        scope="unified", strategy_key=created["strategy_key"],
        version_id=created["version_id"], action="approve",
    )
    now = datetime.now(timezone.utc)
    rows = []
    for index in range(3):
        rows.append({
            "event_id": f"binance-native-{index}",
            # v3.9.1.18 wrote only the executing engine scope here.
            "scope": "binance", "exchange": "binance", "symbol": "BTCUSDT",
            "strategy_key": created["strategy_key"], "version_id": created["version_id"],
            "opened_at": (now - timedelta(days=8, minutes=index)).isoformat(),
            "closed_at": (now - timedelta(minutes=index)).isoformat(),
            "net_pnl": 1.0, "fees": 0.01, "quote_currency": "USDT",
            "calculation_status": "valid", "execution_mode": "paper",
        })
    (tmp_path / "strategy_paper_outcomes.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8",
    )

    assert services.sync_strategy_paper_results()["synced_versions"] == 1
    group = next(row for row in services.strategy_catalog()["strategies"] if row["scope"] == "unified")
    version = group["versions"][0]
    assert version["paper_progress"]["trades"] == 3
    assert version["paper_evidence_by_venue"][0]["exchange"] == "binance"
    assert version["paper_validation"]["metrics"]["validation_subject"] == "custom_entry_logic"
    exported = services.export_strategy_package(
        scope="unified",
        strategy_key=created["strategy_key"],
        version_id=created["version_id"],
    )["package"]
    assert exported["passport"]["evidence_status"] == "publisher_unsigned_local_package"
    assert exported["passport"]["paper_evidence_by_venue"][0]["exchange"] == "binance"
    assert "personal_trade_history" not in exported["passport"]


def test_python_serialized_package_preserves_hash_and_strictly_recovers_legacy_web_numbers():
    rules = _rules()
    ir = NoahStrategyIR.compile(
        rules, source_kind="text", source_reference="01_STRUCTURE.txt",
        missing_conditions=[],
    )
    package = build_strategy_package({
        "strategy_key": "strategy_test", "version_id": "strategy_test_v1",
        "version": 1, "name": "01_STRUCTURE", "source_kind": "text",
        "source_reference": "01_STRUCTURE.txt", "strategy_ir": ir,
    })
    exported = serialize_strategy_package(package)
    assert verify_strategy_package(json.loads(exported))["valid"] is True

    legacy = deepcopy(package)
    risk = legacy["strategy"]["strategy_ir"]["canonical_rules"]["risk_model"]
    risk["risk_per_trade_percent"] = 2
    risk["max_margin_usage_percent"] = 20
    recovered = verify_strategy_package(legacy)
    assert recovered["valid"] is True
    assert recovered["legacy_web_serialized"] is True
    normalized_risk = recovered["normalized_package"]["strategy"]["strategy_ir"]["canonical_rules"]["risk_model"]
    assert normalized_risk["risk_per_trade_percent"] == 2.0
    assert normalized_risk["max_margin_usage_percent"] == 20.0


def test_uncompiled_source_cannot_be_presented_as_source_logic_validation():
    base = {
        **_rules(), "signal_mode": "confirm", "entry_signal": "",
        "executable_entry": {"all": [], "any": []},
    }
    compiled = deepcopy(base)
    compiled["source_grounding"] = {"status": "compiler_authoritative"}
    blocked = CustomStrategyPipeline.paper_execution_readiness({"rules": compiled})
    assert blocked["ready"] is False
    assert "confirm_executable_entry_missing" in blocked["reasons"]

    declared = deepcopy(base)
    declared["source_grounding"] = {
        "status": "user_declared_override", "confirmed_by_user": True,
    }
    overlay = CustomStrategyPipeline.paper_execution_readiness({"rules": declared})
    assert overlay["ready"] is True
    assert overlay["validation_subject"] == "noah_base_with_custom_risk_exit"
    assert overlay["source_strategy_logic_executed"] is False
    assert overlay["historical_validation_applicable"] is False
    assert overlay["historical_validation_reason"] == "noah_base_entry_requires_forward_paper"


def test_strategy_passport_category_vision_keeps_product_boundaries_visible():
    root = Path(__file__).resolve().parents[1]
    manual = (root / "ui/widgets/user_manual_widget.py").read_text(encoding="utf-8")
    guide = (root / "docs/USER_GUIDE.md").read_text(encoding="utf-8")
    positioning = (root / "docs/STRATEGY_VALIDATION_MARKET_POSITIONING_39119.md").read_text(encoding="utf-8")

    for content in (manual, guide, positioning):
        assert "세계 최초의 전략 검증 여권 생태계" in content
        assert "백테스트 자체" in content
        assert "미래 수익" in content

    assert "현재 공개 v3.9.1.21·v3.9.1.22 소스 후보·무료 허브·향후 유료 생태계" in positioning
