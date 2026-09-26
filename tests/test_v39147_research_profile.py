"""Presentation depth is not a strategy migration or execution entitlement."""
from copy import deepcopy
import json
import sqlite3

import pytest

from trading.ai_custom_features import normalize_ai_custom_feature_settings, resolve_ai_custom_features
from trading.noah_strategy_ir import NoahStrategyIR
from trading.strategy_research import replay_cost_sensitivity
from trading.custom_strategy_pipeline import CustomStrategyPipeline
from test_v39147_strategy_repair import compiled


@pytest.mark.parametrize("level,profile", enumerate(["beginner", "standard", "advanced", "lab", "research"], 1))
@pytest.mark.parametrize("venue", ["binance", "okx", "bybit", "bitget", "upbit", "bithumb", "coinone", "kis", "kiwoom", "shinhan", "mirae"])
def test_each_level_roundtrip_preserves_legacy_rules_and_paper(tmp_path, level, profile, venue):
    raw = {"profile": profile, "overrides": {"strategy_package": False}}
    assert normalize_ai_custom_feature_settings(json.loads(json.dumps(raw))) == raw
    features = resolve_ai_custom_features(raw)
    assert features["view_level"] == level
    assert not features["features"]["team_sharing"]
    rules = compiled()
    rules.pop("source_grounding", None)  # Pre-compiler declarative rules.
    rules.pop("source_evidence", None)
    rules["target_scope"] = f"broker:{venue}" if venue in {"kis", "kiwoom", "shinhan", "mirae"} else f"exchange:{venue}"
    store = tmp_path / "strategies.json"
    pipeline = CustomStrategyPipeline(storage_path=store)
    row = pipeline.submit(name="legacy executable", rules=rules)
    key, version = row["strategy_key"], row["version_id"]
    pipeline.approve(key, version, approved_by="fixture")
    before = store.read_bytes()
    reopened = CustomStrategyPipeline(storage_path=store)
    old = reopened.get_version(key, version)
    ir = deepcopy(old["strategy_ir"])
    projection = NoahStrategyIR.project(ir, level)
    assert ir == old["strategy_ir"]
    assert store.read_bytes() == before
    assert projection["integrity_sha256"] == old["ir_hash"]
    if level >= 4:
        assert "daily_loss_stop" in projection["expert_operation_policy"]["immutable_guardrails"]
    if level == 5:
        assert projection["research_policy"]["grants_execution_permission"] is False
    with pytest.raises(ValueError):
        reopened.activate(key, version, live_confirmation=True)
    paper = reopened.start_paper_observation(key, version)
    assert paper["rules"] == old["rules"]
    assert paper["status"] == "paper_observing"
    assert not reopened.active_versions


def test_research_is_independent_read_only_fixed_sample():
    metrics = {"trades": [{"gross_pnl_percent": 2., "cost_percent": 1.}, {"gross_pnl_percent": -1., "cost_percent": .5}]}
    original = deepcopy(metrics)
    result = replay_cost_sensitivity(metrics)
    assert metrics == original
    assert result["status"] == "completed" and not result["execution_permission"]
    assert result["scenarios"][0]["net_return_percent"] == pytest.approx(-.515)
    assert result["scenarios"][1]["net_return_percent"] == pytest.approx(-1.25875)
    assert result["scenarios"][2]["net_return_percent"] == pytest.approx(-2.)
    assert result["scenarios"][0]["max_drawdown_percent"] == pytest.approx(1.5)


@pytest.mark.parametrize("trades", [None, [], [{}], [True], [{"gross_pnl_percent": 1., "cost_percent": None}], [{"gross_pnl_percent": 1., "cost_percent": -1.}], [{"gross_pnl_percent": float("nan"), "cost_percent": 1.}], [{"gross_pnl_percent": 1., "cost_percent": True}]])
def test_missing_research_evidence_never_becomes_zero(trades):
    result = replay_cost_sensitivity({"trades": trades})
    assert result["status"] == "unavailable"
    assert result["scenarios"] == []
    assert not result["execution_permission"]


@pytest.mark.parametrize("venue", ["binance", "okx", "bybit", "bitget", "upbit", "bithumb", "coinone", "kis", "kiwoom", "shinhan", "mirae"])
def test_new_recovery_queue_includes_old_records_without_changing_paper(tmp_path, venue):
    from test_v39143_record_recovery import make
    recorder, tid, _, _, job = make(tmp_path, venue)
    with sqlite3.connect(recorder.db_path) as db:
        db.execute("UPDATE trade_log SET entry_time='2020-01-01 00:00:00',exit_time='2020-01-02 00:00:00',execution_mode='unknown' WHERE id=?", (tid,))
    state = job.start(venue, background=False)
    assert state["since"] == 0
    assert state["total"] == 1
    assert state["remaining"] == 1
    assert not state["resume_authorized"]


def test_resuming_old_job_preserves_its_range_and_checkpoint(tmp_path):
    from test_v39143_record_recovery import make
    _, _, _, _, job = make(tmp_path)
    original = job.start('binance', background=False)
    old_since = job.now() - 45 * 86400
    with job._connect() as db:
        db.execute("UPDATE jobs SET state='paused', since=? WHERE venue='binance'", (old_since,))
    resumed = job.start('binance', background=False)
    assert resumed['job_id'] == original['job_id']
    assert resumed['since'] == old_since
    assert resumed['recovered'] == original['recovered']


def test_all_history_queue_still_excludes_paper(tmp_path):
    from test_v39143_record_recovery import make
    recorder, tid, _, _, job = make(tmp_path, mode='paper')
    with sqlite3.connect(recorder.db_path) as db:
        before = db.execute('SELECT * FROM trade_log WHERE id=?', (tid,)).fetchone()
    assert job.start('binance', background=False)['total'] == 0
    with sqlite3.connect(recorder.db_path) as db:
        assert db.execute('SELECT * FROM trade_log WHERE id=?', (tid,)).fetchone() == before
