import pytest

from trading.custom_strategy_pipeline import CustomStrategyPipeline


def _rules(seed=1):
    return {
        "entry": f"RSI < {30 + seed}",
        "exit": "MACD dead cross",
        "stop_loss": 1.0,
        "take_profit": 2.0,
        "position_size": 0.05,
        "market_conditions": ["trend", "range"],
    }


def test_missing_conditions_are_not_inferred_or_approved():
    pipeline = CustomStrategyPipeline(min_paper_trades=2)
    draft = pipeline.submit(name="incomplete", rules={"entry": "RSI < 30"})

    assert draft["status"] == "needs_clarification"
    assert "stop_loss" in draft["missing_conditions"]
    with pytest.raises(ValueError):
        pipeline.approve(draft["strategy_key"], draft["version_id"], approved_by="user")


def test_approval_paper_validation_and_live_confirmation_are_mandatory():
    pipeline = CustomStrategyPipeline(min_paper_trades=2)
    item = pipeline.submit(name="safe", rules=_rules())

    with pytest.raises(ValueError):
        pipeline.activate(item["strategy_key"], item["version_id"], live_confirmation=True)

    pipeline.approve(item["strategy_key"], item["version_id"], approved_by="tester")
    rejected = pipeline.record_paper_validation(item["strategy_key"], item["version_id"], trades=1)
    assert rejected["status"] == "paper_rejected"
    validated = pipeline.record_paper_validation(item["strategy_key"], item["version_id"], trades=3)
    assert validated["status"] == "paper_validated"

    with pytest.raises(ValueError):
        pipeline.activate(item["strategy_key"], item["version_id"], live_confirmation=False)
    with pytest.raises(ValueError):
        pipeline.activate(
            item["strategy_key"], item["version_id"], live_confirmation=True,
            guardrail_check=lambda _version: {"allowed": False},
        )

    active = pipeline.activate(
        item["strategy_key"], item["version_id"], live_confirmation=True,
        guardrail_check=lambda _version: {"allowed": True},
    )
    assert active["status"] == "active"


def test_user_can_explicitly_choose_limited_live_after_failed_automatic_validation():
    pipeline = CustomStrategyPipeline(min_paper_trades=3)
    item = pipeline.submit(name="limited", rules=_rules())
    key, version_id = item["strategy_key"], item["version_id"]
    pipeline.approve(key, version_id, approved_by="tester")

    with pytest.raises(ValueError, match="자동 실행검증"):
        pipeline.activate(key, version_id, live_confirmation=True, operation_mode="limited_live")

    rejected = pipeline.record_execution_validation(
        key, version_id, decisions=1, guardrail_violations=1, mode="historical_replay",
    )
    assert rejected["status"] == "execution_rejected"
    active = pipeline.activate(
        key, version_id, live_confirmation=True, operation_mode="limited_live",
        guardrail_check=lambda version: {"allowed": version["operation_mode"] == "limited_live"},
    )
    assert active["status"] == "active"
    assert active["operation_mode"] == "limited_live"

    inactive = pipeline.deactivate(key, version_id, approved_by="tester")
    assert inactive["status"] == "execution_rejected"
    assert inactive["last_operation_mode"] == "limited_live"


def test_withdrawal_rules_are_rejected():
    pipeline = CustomStrategyPipeline()
    rules = _rules()
    rules["withdraw_api"] = True
    with pytest.raises(ValueError, match="출금"):
        pipeline.submit(name="forbidden", rules=rules)


def test_version_history_is_limited_to_ten_and_rollback_uses_validated_version():
    pipeline = CustomStrategyPipeline(max_versions=10, min_paper_trades=1)
    first = pipeline.submit(name="versioned", rules=_rules())
    key = first["strategy_key"]
    pipeline.approve(key, first["version_id"], approved_by="user")
    pipeline.record_paper_validation(key, first["version_id"], trades=1)
    pipeline.activate(key, first["version_id"], live_confirmation=True)

    for index in range(1, 13):
        pipeline.submit(name="versioned", rules=_rules(index), strategy_key=key)

    versions = pipeline.list_versions(key)
    assert len(versions) == 10
    assert any(item["version_id"] == first["version_id"] for item in versions)
    unvalidated = next(item for item in versions if item["version_id"] != first["version_id"])
    with pytest.raises(ValueError):
        pipeline.rollback(key, unvalidated["version_id"], approved_by="user")
    rolled_back = pipeline.rollback(key, first["version_id"], approved_by="user")
    assert rolled_back["status"] == "active"
