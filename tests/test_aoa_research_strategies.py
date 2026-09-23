"""Research package contract tests; no exchange orders, accounts or source edits."""
import json
import subprocess

import pytest

from scripts.build_aoa_research_strategies import CATALOG, build, make_rules, make_version, indicator
from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.declarative_strategy_engine import DeclarativeStrategyEngine as Engine
from trading.noah_strategy_ir import NoahStrategyIR
from trading.strategy_package import build_strategy_package, import_strategy_package, verify_strategy_package


def context_for(key, direction):
    timeframe = CATALOG[key][1]
    is_long = direction == "LONG"
    key20, key50, key200 = [Engine.indicator_field_key(indicator("ema", p, timeframe)) for p in (20, 50, 200)]
    values = {key20: 101 if is_long else 99, key50: 100, key200: 98 if is_long else 102,
              "close": 102 if is_long else 98, "rsi": 60 if is_long else 40,
              "volume_ratio": 2.0}
    previous = {key20: 99 if is_long else 101, key50: 100, key200: values[key200],
                "close": 98 if is_long else 102}
    return {**values, "signal": direction, "_previous": previous,
            "_strategy_timeframe_contexts": {timeframe: {**values, "_previous": previous}}}


@pytest.mark.parametrize("key", CATALOG)
def test_build_import_roundtrip_has_no_inherited_performance_or_authority(key, tmp_path):
    build(tmp_path)
    imported = import_strategy_package(tmp_path / f"{key}.noahstrategy")
    expected = make_version(key)
    assert imported["rules"] == expected["rules"]
    assert imported["status"] == "review_only"
    assert not imported["active"] and imported["approval"] is None
    assert imported["passport"] == {}
    assert not imported["rules"]["research_notes"]["historical_performance_inherited"]
    pipeline = CustomStrategyPipeline(storage_path=str(tmp_path / "isolated.json"))
    submitted = pipeline.submit(name=imported["name"], rules=imported["rules"], source_kind="noahstrategy")
    assert submitted["status"] == "analyzed"
    assert submitted["execution_readiness"]["ready"]
    assert submitted["paper_validation"] is None and submitted["execution_validation"] is None
    with pytest.raises(ValueError):
        pipeline.activate(submitted["strategy_key"], submitted["version_id"], live_confirmation=False)
    restored = CustomStrategyPipeline(storage_path=str(tmp_path / "isolated.json"))
    assert restored.strategies[submitted["strategy_key"]][0]["rules"] == submitted["rules"]


@pytest.mark.parametrize("key", CATALOG)
@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_real_evaluator_direction_and_xai(key, direction):
    rules = make_rules(key)
    context = context_for(key, direction)
    for side, spec in rules["independent_entries"].items():
        result = Engine.evaluate_entry({**rules, "executable_entry": spec}, context)
        assert result["allowed"] == (side == direction), result
        assert result.get("reason")
    result = Engine.evaluate_strategy_pool([
        {"rules": rules, "target_scope": rules["target_scope"], "name": key,
         "version_id": key, "engine_settings": rules["engine_settings"]}
    ], context, asset_class="crypto", target="binance", market_regime="bull")
    assert result["allowed"] and result["entry_signal"] == direction, result
    assert result["engine_settings"]["leverage"] == 1
    assert result["engine_settings"]["position_size"] <= 0.05


@pytest.mark.parametrize("key", CATALOG)
@pytest.mark.parametrize("case", ["no_previous", "no_timeframe", "missing_volume", "low_volume", "missing_ema", "wrong_timeframe"])
def test_missing_conditions_never_become_an_entry(key, case):
    rules = make_rules(key)
    rules["executable_entry"] = rules["independent_entries"]["LONG"]
    ctx = context_for(key, "LONG")
    tf = CATALOG[key][1]
    if case == "no_previous":
        ctx.pop("_previous")
        ctx["_strategy_timeframe_contexts"][tf].pop("_previous")
    elif case == "no_timeframe":
        ctx.pop("_strategy_timeframe_contexts")
    elif case in {"missing_volume", "low_volume"}:
        ctx["volume_ratio"] = ctx["_strategy_timeframe_contexts"][tf]["volume_ratio"] = None if case == "missing_volume" else 0.9
    elif case == "missing_ema":
        field = Engine.indicator_field_key(indicator("ema", 200, tf))
        ctx[field] = ctx["_strategy_timeframe_contexts"][tf][field] = None
    else:
        rules["execution_timeframe"] = "1d"
    assert not Engine.evaluate_entry(rules, ctx)["allowed"]


@pytest.mark.parametrize("key", CATALOG)
@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_directional_exit_and_hash_tampering(key, direction):
    rules = make_rules(key)
    ctx = context_for(key, direction)
    assert not Engine.evaluate_exit(rules, ctx)["allowed"]
    ctx["close"] = ctx["_strategy_timeframe_contexts"][CATALOG[key][1]]["close"] = 99 if direction == "LONG" else 101
    assert Engine.evaluate_exit(rules, ctx)["allowed"]
    package = build_strategy_package(make_version(key))
    package["strategy"]["strategy_ir"]["canonical_rules"]["engine_settings"]["leverage"] = 5
    assert not verify_strategy_package(package)["valid"]


@pytest.mark.parametrize("key", CATALOG)
def test_no_unsupported_features_or_fake_source_claims(key):
    version = make_version(key)
    rules = version["rules"]
    assert NoahStrategyIR.validate(version["strategy_ir"])["valid"]
    assert Engine.validate_rule_spec(rules)["valid"]
    assert "advanced_order_plan" not in rules
    assert not rules["source_grounding"]["original_strategy_recovered"]
    assert rules["source_rule_trace"]["entry"]["status"] == "research_hypothesis"
    assert rules["target_scope"] == "exchange:binance"
    assert not Engine._scope_matches(rules["target_scope"], asset_class="stock", target="kis")
    assert not Engine._scope_matches(rules["target_scope"], asset_class="crypto", target="okx")


def test_build_preserves_existing_packages(tmp_path):
    build(tmp_path)
    original = (tmp_path / "01_pullback_5m.noahstrategy").read_bytes()
    with pytest.raises(FileExistsError):
        build(tmp_path)
    assert (tmp_path / "01_pullback_5m.noahstrategy").read_bytes() == original


def test_web_service_import_is_isolated_unapproved_and_preserves_rules(tmp_path, monkeypatch):
    import web_platform.application_services as services
    monkeypatch.setattr(services, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(services, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(services, "load_settings", lambda **kw: {"ai_custom_features": {"profile": "standard", "overrides": {}}})
    app = services.ApplicationServices(account="isolated_aoa_package_test")
    for key in CATALOG:
        version = make_version(key)
        package = build_strategy_package(version)
        # This is the actual renderer -> HTTP JSON transformation, not direct
        # Python-to-Python import which can conceal 1.0/1 integrity problems.
        browser = subprocess.run(["node", "-e", "let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>process.stdout.write(JSON.stringify(JSON.parse(s))))"],
                                 input=json.dumps(package, ensure_ascii=False), text=True,
                                 encoding='utf-8', capture_output=True, check=True)
        package = json.loads(browser.stdout)
        assert verify_strategy_package(package)["valid"]
        imported = app.import_strategy_package(scope="binance", file_name=key + ".noahstrategy", package=package)
        assert imported["rules"] == version["rules"]
        assert imported["approval"] is None
        assert not imported.get("active") and not imported.get("paper_observing")
        assert imported["execution_readiness"]["ready"]
