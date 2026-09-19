from config.ai_custom_knowledge import build_ai_custom_knowledge
from web_platform.application_services import ApplicationServices


def _settings(mode: str = "manual_notional") -> dict:
    return {
        "min_trade_amount": 20.0,
        "position_sizing_policy": {
            "mode": mode,
            "risk_per_trade_percent": 0.5,
            "max_margin_usage_percent": 10.0,
            "max_notional_percent": 50.0,
        },
        "advanced_trading_layers": {
            "profitability_validation": {
                "min_trades": 10,
                "recovery_review_interval_trades": 20,
                "recovery_risk_multiplier": 0.15,
            }
        },
    }


def test_manual_sizing_answer_says_performance_does_not_raise_configured_notional():
    answer = build_ai_custom_knowledge(
        "레버리지는 3배에서 5배로 올랐는데 거래금액은 왜 20 USDT 그대로야?",
        _settings(),
    )

    assert "수동 목표금액 모드" in answer
    assert "20" in answer
    assert "자동 증액하지 않습니다" in answer
    assert "필요한 증거금만 줄어듭니다" in answer
    assert "유효 청산 10건" in answer


def test_account_risk_answer_explains_equity_stop_and_caps():
    answer = build_ai_custom_knowledge(
        "성과회복 뒤 투자금은 언제 올라가나요?",
        _settings("account_risk"),
    )

    assert "NoahAI 자동 위험관리" in answer
    assert "계좌 평가금액" in answer
    assert "SL 거리" in answer
    assert "최대 증거금 10%" in answer
    assert "최대 Notional 50%" in answer
    assert "달력상의 며칠 뒤가 아니라" in answer


def test_settings_and_blockchain_assistant_route_sizing_questions_to_local_contract(monkeypatch):
    services = object.__new__(ApplicationServices)
    settings = _settings()

    settings_answer = services._settings_support_answer("성과회복 뒤 투자금은?", settings)
    assert "수동 목표금액 모드" in settings_answer

    source = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "web_platform" / "application_services.py"
    ).read_text(encoding="utf-8")
    assert '"notional", "노셔널", "복리", "성과회복", "레버리지"' in source
