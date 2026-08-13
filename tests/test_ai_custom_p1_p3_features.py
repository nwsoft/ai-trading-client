import json

import pytest

from trading.ai_custom_features import resolve_ai_custom_features
from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.declarative_strategy_engine import DeclarativeStrategyEngine
from trading.noah_strategy_ir import NoahStrategyIR
from trading.signed_strategy_webhook import SignedStrategyWebhookGate, sign_webhook_payload
from trading.strategy_package import (
    build_strategy_package,
    import_strategy_package,
    verify_strategy_package,
)
from trading.strategy_quality_report import build_strategy_quality_report, compare_replay_trades
from trading.strategy_validation_lab import run_validation_lab
from trading.user_indicator_language import UserIndicatorLanguage
from config.ai_custom_knowledge import build_ai_custom_knowledge


def _rules():
    return {
        "entry": "사용자 추세차가 양수이고 RSI 조건 충족",
        "exit": "RSI 70 이상",
        "stop_loss": "1%",
        "take_profit": "2%",
        "position_size": "5%",
        "market_conditions": "횡보장",
        "target_scope": "exchange:binance",
        "signal_mode": "independent",
        "entry_signal": "LONG",
        "user_indicators": {
            "trend_gap": "(ema(20, '15m') - ema(50, '15m')) / max(abs(ema(50, '15m')), 0.000001)",
        },
        "executable_entry": {
            "expression": {
                "type": "group", "operator": "and", "children": [
                    {"type": "condition", "field": {"user_indicator": "trend_gap"}, "operator": "gt", "value": 0},
                    {"type": "group", "operator": "or", "children": [
                        {"type": "condition", "field": "rsi", "operator": "lte", "value": 35},
                        {"type": "condition", "field": "volume_ratio", "operator": "gte", "value": 1.2},
                    ]},
                ],
            }
        },
        "executable_exit": {"all": [{"field": "rsi", "operator": "gte", "value": 70}]},
    }


def test_profiles_allow_individual_toggles_but_keep_dependencies_fail_closed():
    beginner = resolve_ai_custom_features({"ai_custom_features": {
        "profile": "beginner", "overrides": {"monthly_yearly_table": True},
    }})
    assert beginner["view_level"] == 1
    assert beginner["features"]["monthly_yearly_table"] is True
    disabled = resolve_ai_custom_features({"profile": "advanced", "overrides": {
        "replay_analytics": False, "team_sharing": True, "strategy_package": False,
    }})
    assert disabled["features"]["monthly_yearly_table"] is False
    assert disabled["features"]["team_sharing"] is False
    assert disabled["marketplace"] is False


def test_ai_assistant_knows_v3908_profile_and_backtest_boundaries():
    settings = {"ai_custom_features": {"profile": "advanced", "overrides": {}}}
    profile_answer = build_ai_custom_knowledge("AI 커스텀 고급 프로필과 지표 언어를 설명해줘", settings)
    assert "v3.9.0.10 AI Custom Management & Runtime Integrity Update" in profile_answer
    assert "현재 프로필: 고급 · 보기 Level 3" in profile_answer
    assert "제한형 사용자 지표 언어" in profile_answer
    assert "안전을 우회하지 않습니다" in profile_answer

    backtest_answer = build_ai_custom_knowledge("AI 커스텀 백테스트 PnL MDD와 PAPER 차이는?", settings)
    assert "최소 통과조건" in backtest_answer
    assert "미래 수익" in backtest_answer
    assert "PAPER 전진검증" in backtest_answer


def test_nested_expression_graph_and_user_indicator_are_safe_and_executable():
    rules = _rules()
    assert DeclarativeStrategyEngine.validate_rule_spec(rules)["valid"] is True
    decision = DeclarativeStrategyEngine.evaluate_entry(rules, {
        "custom_ema_20_15m_close": 110,
        "custom_ema_50_15m_close": 100,
        "rsi": 50,
        "volume_ratio": 1.3,
    })
    assert decision["allowed"] is True
    assert decision["expression"]["operator"] == "and"
    ir = NoahStrategyIR.compile(rules)
    assert ir["support"]["status"] == "supported"
    assert any(node["node_type"] == "boolean_group" for node in ir["nodes"])
    assert any(node["node_type"] == "user_indicator_formula" for node in ir["nodes"])


@pytest.mark.parametrize("expression", [
    "__import__('os').system('whoami')",
    "open('/tmp/noah')",
    "close.__class__",
    "2 ** 999",
])
def test_user_indicator_language_blocks_arbitrary_or_excessive_code(expression):
    with pytest.raises(ValueError):
        UserIndicatorLanguage.parse(expression)


def test_validation_lab_reports_total_pnl_mdd_and_month_year_tables():
    report = run_validation_lab([
        {"return_percent": 10, "exit_time": "2025-01-15T00:00:00Z"},
        {"return_percent": -5, "exit_time": "2025-02-15T00:00:00Z"},
        {"return_percent": 4, "exit_time": "2026-01-15T00:00:00Z"},
        {"return_percent": 3, "exit_time": "2026-01-20T00:00:00Z"},
    ], initial_capital=10_000, paper_trades=[])
    performance = report["performance"]
    assert report["schema_version"] == 2
    assert performance["total_net_pnl"] > 0
    assert performance["max_drawdown_percent"] == 5.0
    assert [row["period"] for row in performance["yearly_returns"]] == ["2025", "2026"]
    assert [row["period"] for row in performance["monthly_returns"]] == ["2025-01", "2025-02", "2026-01"]
    assert report["paper_required"] is True
    assert report["backtest_can_auto_promote"] is False
    assert report["promotion_ready"] is False


def test_historical_replay_alone_cannot_activate_standard_operation():
    pipeline = CustomStrategyPipeline(min_paper_trades=1)
    version = pipeline.submit(name="PAPER 필수", rules=_rules())
    key, version_id = version["strategy_key"], version["version_id"]
    pipeline.approve(key, version_id, approved_by="tester")
    pipeline.record_execution_validation(
        key, version_id, decisions=10, mode="historical_replay",
    )
    with pytest.raises(ValueError, match="PAPER 전진검증"):
        pipeline.activate(key, version_id, live_confirmation=True)
    pipeline.record_paper_validation(key, version_id, trades=1)
    assert pipeline.activate(key, version_id, live_confirmation=True)["status"] == "active"


def test_noahstrategy_roundtrip_is_review_only_and_tampering_is_blocked(tmp_path):
    rules = _rules()
    ir = NoahStrategyIR.compile(rules)
    version = {
        "strategy_key": "s1", "version_id": "s1-v1", "version": 1,
        "name": "공유 전략", "source_kind": "text", "source_reference": "/private/path/source.txt",
        "strategy_ir": ir,
    }
    package = build_strategy_package(version, passport={"risk_grade": "high"})
    assert verify_strategy_package(package)["valid"] is True
    path = tmp_path / "shared.noahstrategy"
    path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    imported = import_strategy_package(str(path))
    assert imported["status"] == "review_only"
    assert imported["active"] is False
    assert imported["approval"] is None
    assert imported["rules"] == rules
    assert imported["source_reference"] == "shared.noahstrategy"

    tampered = json.loads(json.dumps(package))
    tampered["strategy"]["name"] = "변조"
    assert verify_strategy_package(tampered)["valid"] is False


def test_signed_webhook_rejects_replay_and_never_orders():
    secret = "1234567890abcdef"
    payload = {"timestamp": 1000, "nonce": "n1", "delivery_id": "d1", "signal": "LONG"}
    gate = SignedStrategyWebhookGate(secret)
    signature = sign_webhook_payload(payload, secret)
    first = gate.verify(payload, signature, now=1000)
    second = gate.verify(payload, signature, now=1000)
    assert first == {
        "valid": True, "errors": [], "action": "strategy_signal_candidate",
        "auto_approved": False, "auto_ordered": False,
    }
    assert second["valid"] is False
    assert "duplicate_delivery" in second["errors"]


def test_quality_report_separates_evidence_and_replay_diff():
    difference = compare_replay_trades(
        [{"entry_time": "a", "entry_price": 100, "side": "LONG"}],
        [{"entry_time": "b", "entry_price": 101, "side": "LONG"}],
    )
    report = build_strategy_quality_report(
        validation_lab={"overfit_risk": {"flagged": False}},
        equivalence_report=difference,
    )
    assert difference["equivalent"] is False
    assert report["historical_only"] is True
    assert "paper_forward_not_passed" in report["warnings"]
    assert report["future_performance_guaranteed"] is False
