from copy import deepcopy
import json

import pytest

from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.declarative_strategy_engine import DeclarativeStrategyEngine
from trading.noah_strategy_ir import IR_FORMAT, IR_VERSION, NoahStrategyIR
from strategy_customizer import StrategyCustomizer


def _complete_rules():
    return {
        "entry": "RSI(14)가 30 미만이고 EMA20이 EMA50을 상향 돌파",
        "exit": "RSI(14)가 65 이상이면 전체 청산",
        "stop_loss": 1.0,
        "take_profit": 2.0,
        "position_size": 0.05,
        "market_conditions": ["range", "trend"],
        "target_scope": "exchange:binance",
        "market_regimes": ["range", "trend"],
        "regime_scope": "market",
        "signal_mode": "independent",
        "entry_signal": "LONG",
        "executable_entry": {
            "all": [
                {
                    "field": {"indicator": "rsi", "period": 14, "timeframe": "5m", "source": "close"},
                    "operator": "lt",
                    "value": 30,
                },
                {
                    "field": {"indicator": "ema", "period": 20, "timeframe": "5m", "source": "close"},
                    "operator": "crosses_above",
                    "value_field": {"indicator": "ema", "period": 50, "timeframe": "5m", "source": "close"},
                },
            ]
        },
        "executable_exit": {"all": [{"field": "rsi", "operator": "gte", "value": 65}]},
        "advanced_order_plan": {
            "partial_take_profits": [
                {"target_percent": 1.0, "close_fraction": 0.5},
                {"target_percent": 2.0, "close_fraction": 0.5},
            ],
            "trailing_stop": {"activation_percent": 1.0, "distance_percent": 0.5},
            "break_even": {"trigger_percent": 0.8, "offset_percent": 0.05},
            "reentry": {"cooldown_bars": 5, "max_reentries": 1},
            "pyramiding": {"max_entries": 2, "add_fraction": 0.25},
        },
    }


def test_ir_compiles_supported_rules_with_evidence_and_capabilities():
    ir = NoahStrategyIR.compile(
        _complete_rules(), source_kind="pine", source_reference="private://strategy.pine"
    )

    assert ir["format"] == IR_FORMAT
    assert ir["ir_version"] == IR_VERSION
    assert ir["support"]["status"] == "supported"
    assert ir["support"]["node_count"] == 8
    assert ir["support"]["evidence_node_count"] == 8
    assert all(node.get("evidence", {}).get("excerpts") for node in ir["nodes"])
    assert ir["capability_profile"]["status"] == "supported"
    assert "previous_value" in ir["capability_profile"]["required"]["states"]


def test_ir_round_trip_is_lossless_and_progressive_views_share_one_contract():
    rules = _complete_rules()
    ir = NoahStrategyIR.compile(rules)

    assert NoahStrategyIR.to_rules(ir) == rules
    assert NoahStrategyIR.round_trip(ir)["equivalent"] is True
    level_1 = NoahStrategyIR.project(ir, 1)
    level_2 = NoahStrategyIR.project(ir, 2)
    level_3 = NoahStrategyIR.project(ir, 3)
    assert level_1["strategy_contract"] == level_2["strategy_contract"] == level_3["strategy_contract"]
    assert level_1["format"] == level_2["format"] == level_3["format"] == IR_FORMAT
    assert "summary" in level_1 and "canonical_rules" not in level_1
    assert "editable_parameters" in level_2 and "nodes" not in level_2
    assert level_3["canonical_rules"] == rules


def test_ir_distinguishes_clarification_from_unsupported_capability():
    needs_input = NoahStrategyIR.compile(
        _complete_rules(), missing_conditions=["stop_loss"]
    )
    assert needs_input["support"]["status"] == "needs_clarification"

    rules = _complete_rules()
    rules["executable_entry"]["all"][0]["field"]["indicator"] = "supertrend"
    unsupported = NoahStrategyIR.compile(rules)
    assert unsupported["support"]["status"] == "unsupported"
    assert any("unsupported_indicator:supertrend" in reason for reason in unsupported["support"]["unsupported_reasons"])


def test_ir_tampering_is_fail_closed():
    ir = NoahStrategyIR.compile(_complete_rules())
    tampered = deepcopy(ir)
    tampered["canonical_rules"]["stop_loss"] = 99

    validation = NoahStrategyIR.validate(tampered)
    assert validation["valid"] is False
    assert "canonical_rules_hash_mismatch" in validation["errors"]
    assert "integrity_hash_mismatch" in validation["errors"]
    with pytest.raises(ValueError, match="무결성"):
        NoahStrategyIR.to_rules(tampered)


def test_pipeline_persists_ir_and_blocks_tampered_or_unsupported_versions():
    pipeline = CustomStrategyPipeline(min_paper_trades=1)
    submitted = pipeline.submit(name="IR vertical slice", rules=_complete_rules())
    assert submitted["status"] == "analyzed"
    assert submitted["ir_validation"]["valid"] is True
    assert submitted["ir_hash"] == submitted["strategy_ir"]["integrity_sha256"]
    assert submitted["correlation_id"].startswith("strategy_event_")

    key, version_id = submitted["strategy_key"], submitted["version_id"]
    pipeline.strategies[key][0]["strategy_ir"]["canonical_rules"]["take_profit"] = 100
    with pytest.raises(ValueError, match="무결성"):
        pipeline.approve(key, version_id, approved_by="tester")

    unsupported_rules = _complete_rules()
    unsupported_rules["executable_entry"]["all"][0]["operator"] = "predicts_up"
    blocked = pipeline.submit(name="unsupported", rules=unsupported_rules)
    with pytest.raises(ValueError, match="지원하지 않는 전략 노드"):
        pipeline.approve(blocked["strategy_key"], blocked["version_id"], approved_by="tester")


def test_pipeline_upgrades_legacy_version_and_runtime_uses_exact_ir_rules():
    pipeline = CustomStrategyPipeline(min_paper_trades=1)
    submitted = pipeline.submit(name="legacy", rules=_complete_rules())
    stored = pipeline.strategies[submitted["strategy_key"]][0]
    for field in ("strategy_ir", "ir_validation", "ir_hash"):
        stored.pop(field, None)

    approved = pipeline.approve(
        submitted["strategy_key"], submitted["version_id"], approved_by="tester"
    )
    assert approved["strategy_ir"]["ir_version"] == IR_VERSION
    rules = NoahStrategyIR.to_rules(approved["strategy_ir"])
    previous = {
        "custom_rsi_14_5m_close": 32,
        "custom_ema_20_5m_close": 99,
        "custom_ema_50_5m_close": 100,
    }
    current = {
        "custom_rsi_14_5m_close": 28,
        "custom_ema_20_5m_close": 101,
        "custom_ema_50_5m_close": 100,
        "_previous": previous,
    }
    decision = DeclarativeStrategyEngine.evaluate_entry(rules, current)
    assert decision == {
        "allowed": True,
        "bypassed": False,
        "all": [
            (True, "custom_rsi_14_5m_close=28 lt 30"),
            (
                True,
                "custom_ema_20_5m_close crosses_above custom_ema_50_5m_close (prev=99/100, now=101/100)",
            ),
        ],
        "any": [],
        "reason": "custom_entry_passed",
    }


def test_active_runtime_pool_excludes_an_ir_tampered_after_activation(tmp_path):
    customizer = StrategyCustomizer(
        None, None, None, None,
        storage_path=str(tmp_path / "private.json"),
        min_paper_trades=1,
    )
    strategy_id = customizer.create_custom_strategy({
        "name": "runtime integrity",
        "rules": _complete_rules(),
        "base_params": {"leverage": 1, "tp_percent": 2.0, "sl_percent": 1.0},
        "target_scope": "exchange:binance",
        "signal_mode": "independent",
        "entry_signal": "LONG",
    })
    strategy = customizer.user_strategies[strategy_id]
    key, version_id = strategy["pipeline_strategy_key"], strategy["pipeline_version_id"]
    customizer.approve_custom_strategy(key, version_id, approved_by="tester")
    customizer.record_paper_validation(key, version_id, trades=1)
    customizer.activate_custom_strategy(key, version_id, live_confirmation=True)
    assert len(customizer.get_active_strategy_pool()) == 1

    customizer.user_strategies[strategy_id]["strategy_ir"]["canonical_rules"]["stop_loss"] = 77
    assert customizer.get_active_strategy_pool() == []


def test_legacy_active_storage_is_compiled_to_ir_during_hydration(tmp_path):
    storage = tmp_path / "legacy-private.json"
    pipeline = CustomStrategyPipeline(storage_path=str(storage), min_paper_trades=1)
    submitted = pipeline.submit(name="legacy active", rules=_complete_rules())
    key, version_id = submitted["strategy_key"], submitted["version_id"]
    pipeline.approve(key, version_id, approved_by="tester")
    pipeline.record_paper_validation(key, version_id, trades=1)
    pipeline.activate(key, version_id, live_confirmation=True)

    payload = json.loads(storage.read_text(encoding="utf-8"))
    payload["schema_version"] = 1
    for version in payload["strategies"][key]:
        for field in ("strategy_ir", "ir_validation", "ir_hash"):
            version.pop(field, None)
    storage.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    restored = StrategyCustomizer(None, None, None, None, storage_path=str(storage))
    pool = restored.get_active_strategy_pool()
    assert len(pool) == 1
    assert pool[0]["ir_version"] == IR_VERSION
