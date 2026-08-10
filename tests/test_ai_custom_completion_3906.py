from trading.custom_strategy_mentor import (
    build_mentor_questions,
    build_version_diff,
    recommend_strategy_candidates,
)
from trading.authenticated_execution_stream import AuthenticatedExecutionStream
from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.declarative_strategy_engine import DeclarativeStrategyEngine
from trading.order_state_machine import reduce_order_state
from trading.custom_strategy_order_plan import (
    confirm_order_plan_action,
    evaluate_order_plan,
    evaluate_reentry,
)
from trading.strategy_source_ingestor import StrategySourceIngestor
from trading.strategy_validation_lab import run_validation_lab
from trading.trader import Position, PositionSide
from trading.trader import Trader
from trading.unified_trader import UnifiedTrader
from trading.exchanges.adapters.bybit_futures_adapter import BybitFuturesAdapter
from datetime import datetime, timezone


def _rules():
    return {
        "entry": "RSI 30 이하 LONG",
        "exit": "RSI 55 이상 청산",
        "stop_loss": "1%",
        "take_profit": "2%",
        "position_size": "5%",
        "market_conditions": "횡보장",
        "executable_entry": {"all": [{"field": "rsi", "operator": "lte", "value": 30}]},
        "executable_exit": {"all": [{"field": "rsi", "operator": "gte", "value": 55}]},
    }


def test_advanced_order_plan_is_fail_closed_and_preserved():
    rules = _rules()
    rules["advanced_order_plan"] = {
        "partial_take_profits": [
            {"target_percent": 1.0, "close_fraction": 0.5},
            {"target_percent": 2.0, "close_fraction": 0.5},
        ],
        "trailing_stop": {"activation_percent": 1.0, "distance_percent": 0.5},
        "break_even": {"trigger_percent": 0.8, "offset_percent": 0.05},
        "reentry": {"cooldown_bars": 3, "max_reentries": 1},
        "pyramiding": {"max_entries": 2, "add_fraction": 0.25},
    }
    assert DeclarativeStrategyEngine.validate_rule_spec(rules)["valid"] is True

    rules["advanced_order_plan"]["partial_take_profits"][1]["close_fraction"] = 0.75
    result = DeclarativeStrategyEngine.validate_rule_spec(rules)
    assert result["valid"] is False
    assert "advanced_order_plan.partial_take_profits:total_fraction_exceeds_one" in result["errors"]


def test_advanced_order_plan_is_idempotent_until_fill_confirmation():
    plan = {
        "partial_take_profits": [
            {"target_percent": 1.0, "close_fraction": 0.5},
            {"target_percent": 2.0, "close_fraction": 0.5},
        ],
        "trailing_stop": {"activation_percent": 1.0, "distance_percent": 0.5},
    }
    first = evaluate_order_plan(plan, None, pnl_percent=1.1, current_quantity=10)
    assert first["action"] == "partial_close"
    assert first["quantity"] == 5
    repeated_before_fill = evaluate_order_plan(
        plan, first["next_state"], pnl_percent=1.2, current_quantity=10,
    )
    assert repeated_before_fill["partial_index"] == 0
    confirmed = confirm_order_plan_action(first, remaining_quantity=5)
    second = evaluate_order_plan(plan, confirmed, pnl_percent=2.1, current_quantity=5)
    assert second["action"] == "close_all"
    assert second["quantity"] == 5


def test_trailing_break_even_and_reentry_never_create_an_order():
    plan = {
        "trailing_stop": {"activation_percent": 1.0, "distance_percent": 0.5},
        "reentry": {"cooldown_bars": 3, "max_reentries": 1},
    }
    armed = evaluate_order_plan(plan, None, pnl_percent=1.2, current_quantity=2)
    stopped = evaluate_order_plan(plan, armed["next_state"], pnl_percent=0.6, current_quantity=2)
    assert stopped["action"] == "close_all"
    reentry = evaluate_reentry(plan, {"reentry_count": 0}, bars_since_exit=3)
    assert reentry["allowed"] is True
    assert reentry["requires_new_entry_signal"] is True
    assert reentry["auto_ordered"] is False


def test_unified_paper_partial_close_updates_position_only_after_confirmation():
    trader = object.__new__(UnifiedTrader)
    trader.settings = {"exchange_execution_modes": {"bybit": "paper"}}
    trader.active_positions = {"bybit": {}}
    trader.paper_active_positions = {"bybit": {}}
    trader.logger = type("Logger", (), {"info": lambda *args: None, "warning": lambda *args: None})()
    position = Position(
        symbol="BTCUSDT", side=PositionSide.LONG, entry_price=100.0,
        current_price=101.2, quantity=10.0, leverage=1,
        unrealized_pnl=0.0, unrealized_pnl_percent=1.2,
        entry_time=datetime.now(timezone.utc), execution_mode="paper",
        custom_strategy_rules={"advanced_order_plan": {
            "partial_take_profits": [{"target_percent": 1.0, "close_fraction": 0.5}],
        }},
    )
    trader.paper_active_positions["bybit"]["BTCUSDT"] = position
    decision = trader._advanced_order_plan_decision_unified(
        position, {"net_pnl_percent": 1.2},
    )
    assert trader._execute_advanced_partial_close_unified(
        "bybit", "BTCUSDT", position, 101.2, decision,
    ) is True
    assert position.quantity == 5.0
    assert position.custom_order_plan_state["completed_partial_indices"] == [0]


def test_binance_partial_close_only_updates_after_filled_receipt():
    class _Client:
        def __init__(self):
            self.client = self

        def place_futures_order(self, **_kwargs):
            return {"status": "NEW", "order_id": "o1", "executed_qty": 0}

        def futures_get_order(self, **_kwargs):
            return {"status": "FILLED", "executedQty": "2"}

    trader = object.__new__(Trader)
    trader.binance_client = _Client()
    trader.log_event = lambda *_args, **_kwargs: None
    trader._record_binance_execution = lambda *_args, **_kwargs: None
    position = Position(
        symbol="BTCUSDT", side=PositionSide.LONG, entry_price=100,
        current_price=101, quantity=4, leverage=1, unrealized_pnl=0,
        unrealized_pnl_percent=1, entry_time=datetime.now(timezone.utc),
    )
    decision = evaluate_order_plan(
        {"partial_take_profits": [{"target_percent": 1, "close_fraction": 0.5}]},
        None, pnl_percent=1, current_quantity=4,
    )
    assert trader._execute_advanced_partial_close_binance(position, decision) is True
    assert position.quantity == 2
    assert position.custom_order_plan_state["completed_partial_indices"] == [0]


def test_source_to_rule_trace_keeps_original_evidence():
    result = StrategySourceIngestor().analyze(
        "진입 RSI 30 이하. 청산 RSI 55 이상. 손절 1%. 익절 2%. "
        "포지션 크기 5%. 횡보장에서 사용한다.",
        "text",
    )
    trace = result["rules"]["source_rule_trace"]
    assert trace["entry"]["status"] == "matched"
    assert trace["entry"]["evidence"]
    assert trace["stop_loss"]["source_kind"] == "text"
    assert result["strategy_ir"]["format"] == "noah-strategy-ir"
    assert result["ir_level_1"]["level"] == 1
    assert result["ir_level_2"]["level"] == 2
    assert result["strategy_ir"]["support"]["evidence_node_count"] == len(
        result["strategy_ir"]["nodes"]
    )


def test_korean_natural_language_rsi_rules_compile_to_executable_ir():
    result = StrategySourceIngestor().analyze(
        "진입 RSI 30 이하 LONG. 청산 RSI 65 이상. 손절 1%. 익절 2%. "
        "포지션 크기 5%. 횡보장에서 사용한다.",
        "text",
    )

    assert result["missing_conditions"] == []
    assert result["rules"]["entry_signal"] == "LONG"
    assert result["rules"]["executable_entry"]["all"] == [
        {"field": "rsi", "operator": "lte", "value": 30.0}
    ]
    assert result["rules"]["executable_exit"]["all"] == [
        {"field": "rsi", "operator": "gte", "value": 65.0}
    ]
    assert result["strategy_ir"]["support"]["status"] == "supported"
    assert result["strategy_ir"]["support"]["node_count"] == 2


def test_mentor_requires_profile_and_returns_teaching_candidates():
    assert build_mentor_questions({"asset_class": "crypto"})
    profile = {
        "asset_class": "crypto",
        "capital_band": "small",
        "max_loss_percent": 0.5,
        "review_frequency": "daily",
        "trade_frequency": "medium",
        "leverage_allowed": False,
        "experience_level": "beginner",
        "paper_ready": True,
    }
    candidates = recommend_strategy_candidates(profile)
    assert 2 <= len(candidates) <= 3
    assert all(item["paper_required"] for item in candidates)
    assert all(item["auto_applied"] is False for item in candidates)
    assert all(item["when_not_to_trade"] for item in candidates)


def test_version_diff_and_validation_lab_never_auto_apply():
    diff = build_version_diff({"rsi": 30}, {"rsi": 35, "timeframe": "15m"})
    assert diff["change_count"] == 2
    assert diff["requires_user_review"] is True
    assert diff["auto_applied"] is False

    report = run_validation_lab(
        [{"pnl": 1.0, "fee": 0.01, "slippage": 0.01} for _ in range(20)],
        parameter_variants=[{"net_pnl": 17.0}, {"net_pnl": 18.0}],
        paper_trades=[{"pnl": 0.5} for _ in range(3)],
    )
    assert report["walkforward"]["pass_rate"] == 1.0
    assert report["paper_forward"]["passed"] is True
    assert report["promotion_ready"] is True
    assert report["auto_promoted"] is False


def test_pipeline_records_diff_validation_and_user_promotion(tmp_path):
    pipeline = CustomStrategyPipeline(storage_path=str(tmp_path / "strategies.json"))
    first = pipeline.submit(name="첫 버전", rules=_rules())
    pipeline.approve(first["strategy_key"], first["version_id"], approved_by="user")
    report = run_validation_lab(
        [{"pnl": 1.0} for _ in range(20)], paper_trades=[{"pnl": 1.0} for _ in range(3)]
    )
    saved = pipeline.record_validation_lab(first["strategy_key"], first["version_id"], report)
    assert saved["validation_lab"]["promotion_ready"] is True
    assert saved["promotion_history"][-1]["auto_promoted"] is False

    revised_rules = _rules()
    revised_rules["take_profit"] = "2.5%"
    revised = pipeline.submit(name="둘째 버전", rules=revised_rules, strategy_key=first["strategy_key"])
    assert revised["version_diff"]["requires_user_review"] is True


def test_paper_validation_updates_lab_but_never_auto_promotes(tmp_path):
    pipeline = CustomStrategyPipeline(
        storage_path=str(tmp_path / "strategies.json"), min_paper_trades=3,
    )
    submitted = pipeline.submit(name="PAPER 연결 전략", rules=_rules())
    approved = pipeline.approve(
        submitted["strategy_key"], submitted["version_id"], approved_by="user",
    )
    report = run_validation_lab([{"pnl": 1.0} for _ in range(8)])
    pipeline.record_validation_lab(approved["strategy_key"], approved["version_id"], report)
    stored = pipeline.record_paper_validation(
        approved["strategy_key"], approved["version_id"],
        trades=3, guardrail_violations=0, metrics={"net_pnl": 2.5},
    )
    assert stored["validation_lab"]["paper_forward"]["trades"] == 3
    assert stored["validation_lab"]["auto_promoted"] is False
    assert stored["promotion_history"][-1]["auto_promoted"] is False


def test_orchestrator_holds_conflicting_independent_strategies():
    pool = []
    for signal, version in (("LONG", "v-long"), ("SHORT", "v-short")):
        pool.append({
            "id": version,
            "version_id": version,
            "name": version,
            "priority": 5,
            "target_scope": "asset:crypto",
            "market_regimes": ["all"],
            "signal_mode": "independent",
            "entry_signal": signal,
            "rules": {"executable_entry": {}},
        })
    result = DeclarativeStrategyEngine.evaluate_strategy_pool(
        pool, {"signal": "HOLD"}, asset_class="crypto", target="binance"
    )
    assert result["allowed"] is False
    assert result["reason"] == "strategy_signal_conflict"
    assert result["transition_action"] == "hold"


def test_orchestrator_demotes_only_by_policy_and_proposes_new_version():
    pool = [{
        "id": "s1", "version_id": "v1", "name": "test", "priority": 5,
        "target_scope": "asset:crypto", "market_regimes": ["all"],
        "signal_mode": "independent", "entry_signal": "LONG",
        "rules": {"executable_entry": {}},
        "orchestration_policy": {"min_samples": 10, "max_consecutive_losses": 3},
    }]
    result = DeclarativeStrategyEngine.evaluate_strategy_pool(
        pool,
        {
            "signal": "HOLD",
            "_strategy_performance_by_id": {
                "v1": {"trades": 12, "consecutive_losses": 3, "recent_win_rate": 0.4}
            },
        },
        asset_class="crypto",
        target="binance",
    )
    assert result["demotions"][0]["action"] == "demote_to_paper"
    assert result["demotions"][0]["auto_changed"] is False
    assert result["improvement_proposals"][0]["requires_user_approval"] is True


def test_order_state_machine_recovers_pending_and_locks_terminal_state():
    partial = reduce_order_state("open", {"status": "open", "filled": 0.4, "amount": 1.0})
    assert partial["current"] == "partially_filled"
    assert partial["recovery_required"] is True
    filled = reduce_order_state("partially_filled", {"status": "closed", "filled": 1.0, "amount": 1.0})
    assert filled["current"] == "filled"
    assert filled["terminal"] is True
    invalid = reduce_order_state("filled", {"status": "open"})
    assert invalid["current"] == "filled"
    assert invalid["transition_allowed"] is False


def test_authenticated_execution_stream_deduplicates_and_exposes_health():
    stream = AuthenticatedExecutionStream("bybit", stale_after_seconds=90)
    stream.mark_connected()
    event = {"trade_id": "t1", "order_id": "o1", "symbol": "BTC/USDT", "filled": 1}
    assert stream.push(event) is True
    assert stream.push(event) is False
    assert stream.execution_stream_healthy() is True
    assert stream.drain_execution_events() == [{"exchange": "bybit", **event}]
    stream.mark_disconnected("network")
    assert stream.execution_stream_healthy() is False
    assert stream.status()["reconnect_attempts"] == 1


def test_exchange_adapter_keeps_private_execution_stream_separate_from_market_data():
    adapter = BybitFuturesAdapter("key", "secret")
    caps = adapter.get_execution_stream_capabilities()
    assert caps["authenticated_private_stream"] is True
    assert caps["adapter_callback_bound"] is False
    adapter.mark_execution_stream_connected()
    assert adapter.ingest_authenticated_execution_event({
        "trade_id": "t-private", "order_id": "o-private", "symbol": "BTC/USDT:USDT",
    }) is True
    assert adapter.execution_stream_healthy() is True
    assert adapter.drain_execution_events()[0]["trade_id"] == "t-private"
