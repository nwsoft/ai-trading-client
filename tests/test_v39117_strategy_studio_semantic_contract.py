import pytest
from copy import deepcopy

from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.custom_strategy_mentor import recommend_strategy_candidates
from trading.custom_strategy_runtime import ExitRateContractError, normalize_engine_settings
from trading.declarative_strategy_engine import DeclarativeStrategyEngine
from trading.strategy_source_ingestor import StrategySourceIngestor
from web_platform.application_services import ApplicationServices


def analyze(text: str, kind: str = "text"):
    return StrategySourceIngestor().analyze(text, kind)


def test_confirm_long_source_never_confirms_noah_short():
    result = analyze(
        "RSI 30 이하에서 LONG 진입. RSI 55 이상에서 청산. "
        "손절 1%, 익절 2%, 자산 5%. 횡보장에서 사용."
    )
    assert result["ready_for_execution"] is True
    rules = result["rules"]
    assert rules["entry_signal"] == "LONG"

    common = {
        "name": "LONG 확인",
        "target_scope": "asset:crypto",
        "market_regimes": ["range"],
        "signal_mode": "confirm",
        "entry_signal": rules["entry_signal"],
        "rules": rules,
        "engine_settings": rules["engine_settings"],
    }
    allowed = DeclarativeStrategyEngine.evaluate_strategy_pool(
        [common], {"signal": "LONG", "rsi": 25},
        asset_class="crypto", target="binance", market_regime="range",
    )
    blocked = DeclarativeStrategyEngine.evaluate_strategy_pool(
        [common], {"signal": "SHORT", "rsi": 25},
        asset_class="crypto", target="binance", market_regime="range",
    )
    assert allowed["allowed"] is True
    assert blocked["allowed"] is False


def test_dual_direction_natural_language_compiles_two_independent_branches():
    result = analyze(
        "RSI 30 이하이면 LONG 진입, RSI 70 이상이면 SHORT 진입. "
        "RSI 50에서 청산. 손절 1%, 익절 2%, 자산 5%. 횡보장."
    )
    rules = result["rules"]
    assert rules["signal_mode"] == "independent"
    assert set(rules["independent_entries"]) == {"LONG", "SHORT"}
    assert rules["independent_entries"]["LONG"]["all"][0]["operator"] == "lte"
    assert rules["independent_entries"]["SHORT"]["all"][0]["operator"] == "gte"


def test_pine_rsi_alias_is_resolved_and_unknown_alias_fails_closed():
    supported = analyze(
        """//@version=5
r = ta.rsi(close, 14)
longCondition = r < 30
if longCondition
    strategy.entry('L', strategy.long)
// RSI 55 이상 청산. 손절 1%, 익절 2%, 자산 5%. 횡보장.
strategy.close('L')
""",
        "pine",
    )
    assert supported["ready_for_execution"] is True
    assert {"field": "rsi", "operator": "lt", "value": 30.0} in supported["rules"]["executable_entry"]["all"]

    unsupported = analyze(
        """//@version=5
longCondition = secretSignal
if longCondition
    strategy.entry('L', strategy.long)
// RSI 55 이상 청산. 손절 1%, 익절 2%, 자산 5%. 횡보장.
strategy.close('L')
""",
        "pine",
    )
    assert unsupported["ready_for_execution"] is False
    assert "pine_entry_condition_unresolved:longCondition" in unsupported["missing_conditions"]


def test_unitless_exit_values_are_not_guessed_or_silently_clamped():
    result = analyze(
        "RSI 30 이하 LONG 진입. RSI 55 이상 청산. "
        "손절 30, 익절 100, 자산 80%. 횡보장."
    )
    assert result["ready_for_execution"] is False
    assert "stop_loss_unit_missing" in result["missing_conditions"]
    assert "take_profit_unit_missing" in result["missing_conditions"]
    assert {item["code"] for item in result["blocking_details"]} >= {
        "stop_loss_unit_missing", "take_profit_unit_missing",
    }
    assert all(item["action"] and item["example"] for item in result["blocking_details"])
    assert "sl_percent" not in result["engine_settings"]
    assert "tp_percent" not in result["engine_settings"]
    assert result["engine_settings"]["position_size"] == pytest.approx(0.8)


def test_pipeline_and_order_boundary_share_same_exit_rate_limits():
    pipeline = CustomStrategyPipeline()
    version = {
        "rules": {
            "entry": "RSI 30 이하 LONG",
            "exit": "고정 TP/SL",
            "stop_loss": "5%",
            "take_profit": "10%",
            "position_size": "5%",
            "market_conditions": ["횡보장"],
            "signal_mode": "independent",
            "entry_signal": "LONG",
            "executable_entry": {"all": [{"field": "rsi", "operator": "lte", "value": 30}]},
            "exit_policy": {"mode": "strategy_owned"},
            "engine_settings": {
                "_unit": "percent_points", "tp_percent": 10.0, "sl_percent": 5.0,
            },
        },
        "missing_conditions": [],
    }
    readiness = pipeline.paper_execution_readiness(version)
    assert readiness["ready"] is False
    assert "exit_rate_contract_missing_or_invalid" in readiness["reasons"]
    with pytest.raises(ExitRateContractError):
        normalize_engine_settings(version["rules"]["engine_settings"])


@pytest.mark.parametrize(
    ("field", "value"),
    [("position_size", 0.75), ("leverage", 11), ("signal_threshold", 70)],
)
def test_user_values_are_rejected_instead_of_silently_clamped(field, value):
    with pytest.raises(ExitRateContractError):
        normalize_engine_settings({"_unit": "percent_points", field: value})


class _HallucinatingAI:
    @staticmethod
    def is_ready():
        return True

    @staticmethod
    def chat_json(*_args, **_kwargs):
        return {
            "name": "AI가 제안한 이름",
            "summary": "설명은 참고할 수 있지만 주문 규칙은 컴파일러가 결정합니다.",
            "rules": {
                "entry": "RSI 10 이하 LONG",
                "exit": "RSI 90 이상",
                "stop_loss": "3%", "take_profit": "5%", "position_size": "50%",
                "market_conditions": ["상승장"],
                "signal_mode": "independent", "entry_signal": "LONG",
                "executable_entry": {"all": [{"field": "rsi", "operator": "lte", "value": 10}]},
                "executable_exit": {"all": [{"field": "rsi", "operator": "gte", "value": 90}]},
            },
            "engine_settings": {
                "_unit": "percent_points", "tp_percent": 5,
                "sl_percent": 3, "position_size": 0.5,
            },
            "missing_conditions": [], "risks": [], "scenarios": [],
        }


def test_external_ai_cannot_replace_source_compiled_order_rules():
    result = StrategySourceIngestor(_HallucinatingAI()).analyze(
        "RSI 30 이하에서 LONG 진입. RSI 55 이상에서 청산. "
        "손절 1%, 익절 2%, 자산 5%. 횡보장에서 사용.",
        "text",
    )
    assert result["ready_for_execution"] is True
    assert result["rules"]["executable_entry"]["all"][0]["value"] == 30
    assert result["engine_settings"]["tp_percent"] == 2
    assert result["engine_settings"]["sl_percent"] == 1
    assert result["ai_execution_suggestion_rejected"] is True
    assert "engine_settings.tp_percent" in result["rules"]["source_grounding"]["rejected_ai_paths"]


def test_execution_edit_after_source_analysis_requires_regrounding():
    result = analyze(
        "RSI 30 이하에서 LONG 진입. RSI 55 이상에서 청산. "
        "손절 1%, 익절 2%, 자산 5%. 횡보장에서 사용."
    )
    rules = deepcopy(result["rules"])
    clean = object.__new__(ApplicationServices).validate_strategy_draft(rules=rules)
    assert clean["ready"] is True

    rules["engine_settings"]["tp_percent"] = 4
    stale = object.__new__(ApplicationServices).validate_strategy_draft(rules=rules)
    assert stale["ready"] is False
    assert "source_grounding_stale_after_execution_edit" in stale["compiler_issues"]
    assert stale["blocking_details"] == [{
        "code": "source_grounding_stale_after_execution_edit",
        "title": "분석 후 실행 규칙이 변경됐습니다",
        "explanation": "현재 JSON이 분석한 원문과 달라 원문 근거 해시가 일치하지 않습니다.",
        "action": "변경 내용을 원문에 반영해 다시 분석하거나, 직접 편집한 내용이 맞다면 사용자 선언 확인란을 선택하세요.",
        "example": "원문 수정 → AI 분석 및 전략 초안 만들기 → 최종 재검증",
    }]

    rules["source_grounding"] = {
        **rules["source_grounding"],
        "status": "user_declared_override",
        "confirmed_by_user": True,
        "base_compiler_contract_sha256": rules["source_grounding"]["compiler_contract_sha256"],
    }
    declared = object.__new__(ApplicationServices).validate_strategy_draft(rules=rules)
    assert declared["ready"] is True
    assert declared["rules"]["source_grounding"]["status"] == "user_declared_override"
    assert declared["rules"]["source_grounding"]["compiler_contract_sha256"] != rules["source_grounding"]["compiler_contract_sha256"]


def test_draft_validation_explains_each_missing_condition_for_beginners():
    rules = {
        "entry": "RSI 30 이하 LONG",
        "exit": "고정 TP/SL",
        "stop_loss": "숫자만 기재",
        "take_profit": "숫자만 기재",
        "position_size": "5%",
        "market_conditions": ["횡보장"],
        "signal_mode": "independent",
        "entry_signal": "LONG",
        "executable_entry": {"all": [{"field": "rsi", "operator": "lte", "value": 30}]},
        "exit_policy": {"mode": "strategy_owned"},
        "engine_settings": {"_unit": "percent_points"},
        "compiler_issues": ["stop_loss_unit_missing", "take_profit_unit_missing"],
    }
    result = object.__new__(ApplicationServices).validate_strategy_draft(rules=rules)

    assert result["ready"] is False
    assert {item["code"] for item in result["blocking_details"]} == {
        "stop_loss_unit_missing", "take_profit_unit_missing",
    }
    assert all(item["title"] and item["action"] and item["example"] for item in result["blocking_details"])


def test_source_analysis_translates_plain_required_field_codes_without_duplicates():
    result = analyze("이동평균선 전략으로 거래한다.")
    details = result["blocking_details"]

    assert {item["code"] for item in details} == {
        "entry", "exit", "stop_loss", "take_profit", "position_size", "market_conditions",
    }
    assert {item["title"] for item in details} >= {
        "진입 조건 항목이 없습니다", "손절 조건 항목이 없습니다", "거래 위험예산 항목이 없습니다",
    }


@pytest.mark.parametrize(
    "risk_text, expected_risk, expected_margin",
    [
        ("거래당 계좌 손실 0.5%, 증거금 사용은 최대 10%", 0.5, 10.0),
        ("거래 한 번에서 계좌의 최대 0.75%까지 손실, 증거금 최대 20%", 0.75, 20.0),
        ("1회 위험 1%, 종목당 투자 비중은 최대 15%", 1.0, 15.0),
        ("risk per trade 0.25%, position size 5%", 0.25, 5.0),
    ],
)
def test_user_facing_risk_budget_examples_compile_deterministically(
    risk_text, expected_risk, expected_margin,
):
    result = analyze(
        "RSI 30 이하에서 LONG 진입. RSI 55 이상에서 청산. "
        f"손절 1%, 익절 2%. {risk_text}. 상승장에서 사용."
    )

    assert "position_size" not in result["missing_conditions"]
    assert result["rules"]["position_size"] == f"{expected_margin}%"
    assert result["rules"]["engine_settings"]["position_size"] == pytest.approx(expected_margin / 100.0)
    assert result["rules"]["risk_model"]["risk_per_trade_percent"] == pytest.approx(expected_risk)
    assert result["rules"]["risk_model"]["max_margin_usage_percent"] == pytest.approx(expected_margin)


def test_unitless_risk_budget_is_not_silently_treated_as_percent():
    result = analyze(
        "RSI 30 이하에서 LONG 진입. RSI 55 이상에서 청산. "
        "손절 1%, 익절 2%. 거래당 계좌 손실 0.5, 증거금 최대 10. 상승장에서 사용."
    )

    assert "position_size" in result["missing_conditions"]
    assert result["rules"].get("risk_model") is None


def test_managed_mentor_candidates_are_complete_but_never_auto_applied():
    profile = {
        "asset_class": "crypto", "capital_band": "small",
        "max_loss_percent": 0.5, "review_frequency": "daily",
        "trade_frequency": "medium", "leverage_allowed": False,
        "experience_level": "beginner", "paper_ready": True,
    }
    candidates = recommend_strategy_candidates(profile)
    assert candidates
    for candidate in candidates:
        assert candidate["executable_template"] is True
        assert candidate["auto_applied"] is False
        assert candidate["draft_analysis"]["ready_for_execution"] is True
        assert candidate["draft_analysis"]["execution_readiness"]["historical_validation_applicable"] is True
        validated = object.__new__(ApplicationServices).validate_strategy_draft(
            rules=deepcopy(candidate["draft_rules"])
        )
        assert validated["ready"] is True


def test_managed_stock_candidates_are_long_only_unleveraged_and_replayable():
    profile = {
        "asset_class": "stock", "capital_band": "small",
        "max_loss_percent": 0.5, "review_frequency": "daily",
        "trade_frequency": "medium", "leverage_allowed": True,
        "experience_level": "beginner", "paper_ready": True,
    }
    candidates = recommend_strategy_candidates(profile)
    assert candidates
    for candidate in candidates:
        rules = candidate["draft_rules"]
        readiness = candidate["draft_analysis"]["execution_readiness"]
        assert rules["entry_signal"] == "LONG"
        assert "independent_entries" not in rules
        assert rules["executable_entry"]
        assert rules["engine_settings"]["leverage"] == 1
        assert rules["risk_model"]["max_leverage"] == 1
        assert readiness["entry_directions"] == ["LONG"]
        assert readiness["historical_validation_applicable"] is True
        assert candidate["auto_applied"] is False


def test_complex_pine_features_are_explicitly_blocked_instead_of_degraded():
    result = analyze(
        """//@version=5
period = input.int(14)
htf = request.security(syminfo.tickerid, '60', close)
longCondition = ta.rsi(close, period) < 30
if longCondition
    strategy.entry('L', strategy.long)
strategy.exit('X', 'L', stop=strategy.position_avg_price * 0.99)
// 손절 1%, 익절 2%, 자산 5%. 횡보장.
""",
        "pine",
    )
    assert result["ready_for_execution"] is False
    assert "pine_dynamic_input_requires_user_confirmation" in result["missing_conditions"]
    assert "pine_multitimeframe_request_not_supported" in result["missing_conditions"]
    assert "pine_position_price_exit_not_supported" in result["missing_conditions"]
