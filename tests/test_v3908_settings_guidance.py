from pathlib import Path

from config.ai_custom_knowledge import build_ai_custom_knowledge
from config.settings_knowledge import build_settings_knowledge
from trading.ai_custom_features import resolve_ai_custom_features


ROOT = Path(__file__).resolve().parents[1]


def test_webhook_is_lab_only_even_when_standard_override_requests_it():
    standard = resolve_ai_custom_features(
        {"ai_custom_features": {"profile": "standard", "overrides": {"signed_webhook": True}}}
    )
    lab = resolve_ai_custom_features(
        {"ai_custom_features": {"profile": "lab", "overrides": {"signed_webhook": True}}}
    )
    assert standard["features"]["signed_webhook"] is False
    assert lab["features"]["signed_webhook"] is True


def test_ai_custom_local_help_distinguishes_webhook_and_mentor_flows():
    webhook = build_ai_custom_knowledge("지정 거래소가 있는데 웹훅은 왜 필요해?")
    mentor = build_ai_custom_knowledge("AI 멘토와 처음 사용법 AI에게 묻기 차이는?")
    assert "webhook이 필요하지 않습니다" in webhook
    assert "거래소 주문 연결 방식이 아닙니다" in webhook
    assert "실험실 프로필 외에는 강제로 OFF" in webhook
    assert "8문항" in mentor
    assert "전략 후보 2~3개" in mentor
    assert "개인화 전략 후보를 만들지는 않습니다" in mentor


def test_settings_local_help_includes_current_advanced_and_alpha_state():
    settings = {
        "ai_custom_features": {"profile": "standard"},
        "advanced_trading_layers": {
            "profitability_validation": {"enabled": True},
            "portfolio_orchestration": {"enabled": True},
            "strategy_engine": {
                "enabled": True,
                "high_vol_action": "evaluate",
                "consensus_threshold": 0.7,
                "cooldown_sec": 120,
            },
            "execution_optimizer": {"enabled": True},
            "ops_automation": {"enabled": True},
        },
        "alpha_arena": {
            "enabled": False,
            "exchange": "binance-futures",
            "engine": "deepseek-v4-flash",
        },
    }
    advanced = build_settings_knowledge("고급 매매 계층 safe 프리셋이 뭐야?", settings)
    arena = build_settings_knowledge("AlphaArena가 뭐야?", settings)
    assert "safe와 PAPER 7~14일" in advanced
    assert "profitability_validation=ON" in advanced
    assert "evaluate / 0.7 / 120초" in advanced
    assert "숙련자용 Binance USDT 선물" in arena
    assert "AlphaArena: OFF / binance-futures / deepseek-v4-flash" in arena


def test_settings_and_ai_custom_ui_keep_explanations_visible_without_clipping_layout():
    settings_source = (ROOT / "ui" / "settings_modern.py").read_text(encoding="utf-8")
    custom_source = (ROOT / "ui" / "widgets" / "custom_strategy_widget.py").read_text(encoding="utf-8")
    advanced_start = settings_source.index("def create_advanced_layers_tab")
    alpha_start = settings_source.index("def create_alphaarena_tab")
    advanced = settings_source[advanced_start:alpha_start]
    alpha = settings_source[alpha_start: settings_source.index("def _verify_alphaarena_api_key", alpha_start)]

    assert "wraplength=980" not in advanced
    assert "policy_list" in advanced
    assert "safe (신규 권장)" in advanced
    assert "기본값 ‘평가 계속’" in advanced
    assert "Qwen3 (Alibaba) API Key:" not in alpha
    assert "현재 고정 가드레일과 기본값" in alpha
    assert "현재 실행 선택은 DeepSeek V4 Flash만 지원" in alpha
    assert 'window = ctk.CTkToplevel(self)' in custom_source
    assert "두 도움 기능의 차이" in custom_source
    assert "v3.9.0.8 기능 위치" in custom_source


def test_v3908_manual_and_tester_docs_cover_the_new_user_questions():
    manual = (ROOT / "ui" / "widgets" / "user_manual_widget.py").read_text(encoding="utf-8")
    reference = (ROOT / "docs" / "SETTINGS_REFERENCE_v3.9.0.8.md").read_text(encoding="utf-8")
    for marker in (
        "지정 거래소를 앱 안에서 분석·실행할 때 webhook은 필요하지 않습니다",
        "AI 멘토 인터뷰는 8문항",
        "safe(신규 권장)",
        "틱당 모델 제시 위험 합계 상한 1,500 USDT",
        '("설정 가이드", "시작·설정")',
        "v3.9.0.8 설정을 이해하는 가장 짧은 설명",
        "웹훅은 TradingView 같은 외부 도구의 신호",
        "고변동장 처리 — evaluate와 block의 차이",
        "현재 설치 버전과 설정을 기준으로 설명",
    ):
        assert marker in manual
    assert "v3.9.0.5 실제 작동 기준" not in manual
    for marker in (
        "webhook이 필요한 경우와 필요하지 않은 경우",
        "AI 멘토 인터뷰와 처음 사용법 AI에게 묻기",
        "고급 매매 계층",
        "AlphaArena",
        "배포와 검증 경계",
    ):
        assert marker in reference
