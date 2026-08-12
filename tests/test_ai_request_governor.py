from trading.ai.request_governor import AIRequestGovernor


def test_role_and_total_budgets_are_persistent(tmp_path):
    state = str(tmp_path / "provider_budget.json")
    settings = {
        "ai_cost_control": {
            "max_daily_automatic_ai_calls": 3,
            "max_monthly_automatic_ai_calls": 10,
            "max_daily_ai_calls_by_role": {"pattern_similarity": 1},
        }
    }
    first = AIRequestGovernor(settings, state_path=state, clock=lambda: 1000.0)
    assert first.reserve("pattern_similarity")["allowed"] is True
    denied = first.reserve("pattern_similarity")
    assert denied == {
        "allowed": False,
        "reason": "role_daily_budget",
        "role": "pattern_similarity",
        "daily": 1,
        "role_daily": 1,
    }

    restarted = AIRequestGovernor(settings, state_path=state, clock=lambda: 1001.0)
    assert restarted.reserve("pattern_similarity")["reason"] == "role_daily_budget"


def test_provider_budget_can_be_disabled_without_persisting(tmp_path):
    governor = AIRequestGovernor(
        {"ai_cost_control": {"provider_budget_enabled": False}},
        state_path=str(tmp_path / "provider_budget.json"),
    )
    assert governor.reserve("signal_analysis") == {
        "allowed": True,
        "reason": "provider_budget_disabled",
    }
