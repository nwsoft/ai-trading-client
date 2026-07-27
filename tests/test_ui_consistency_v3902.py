from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_trading_statistics_uses_only_the_table_scroll_area():
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    section = source.split("def _ensure_trading_stats_tab", 1)[1].split("def _ensure_trend_tab", 1)[0]

    assert "main_container = ctk.CTkFrame(" in section
    assert "self.trading_stats_scroll = ctk.CTkScrollableFrame(" in section
    assert "main_container = ctk.CTkScrollableFrame(" not in section


def test_financial_intelligence_explains_coin_info_and_discovery_without_api():
    source = (ROOT / "ui" / "widgets" / "ai_assistant_widget.py").read_text(encoding="utf-8")
    section = source.split("def _build_financial_intelligence_support", 1)[1].split(
        "def _build_identity_support", 1
    )[0]

    assert "내 계좌" in section
    assert "시장 검색" in section
    assert "자동 주문되지는 않습니다" in section
    assert "financial_intelligence_support = self._build_financial_intelligence_support(message)" in source


def test_assistant_explains_referral_policy_and_admin_settings_without_api():
    source = (ROOT / "ui" / "widgets" / "ai_assistant_widget.py").read_text(encoding="utf-8")
    section = source.split("def _build_membership_support", 1)[1].split(
        "def _build_identity_support", 1
    )[0]

    assert "daltrading 관리자 포털" in section
    assert "Binance·Bybit·OKX·Bitget" in section
    assert "Upbit·Bithumb" in section
    assert "membership_support = self._build_membership_support(message)" in source


def test_financial_intelligence_has_in_context_ai_help_and_beginner_steps():
    source = (ROOT / "ui" / "widgets" / "financial_intelligence_widget.py").read_text(encoding="utf-8")

    assert "AI에게 사용법 묻기" in source
    assert "처음 사용:" in source
    assert "코인 정보는 내 계좌" in source


def test_tab_hover_color_stays_in_the_service_accent_family():
    source = (ROOT / "ui" / "visual_system.py").read_text(encoding="utf-8")

    assert "selected_hover = _shade_hex(accent, 1.10)" in source
    assert "inactive_hover = _shade_hex(inactive, 1.10)" in source
    assert 'selected_hover_color=selected_hover' in source


def test_life_finance_progress_bars_use_supported_set_api():
    source = (ROOT / "ui" / "widgets" / "life_finance_widget.py").read_text(encoding="utf-8")

    assert "CTkProgressBar(progress_frame, value=" not in source
    assert "CTkProgressBar(card, value=" not in source
    assert "CTkProgressBar(row, value=" not in source
    assert "progress.set(" in source


def test_function_tabs_share_the_ai_custom_visual_palette():
    palette = (ROOT / "utils" / "fixed_colors.py").read_text(encoding="utf-8")
    dashboard = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")

    for token in (
        "'content_bg': '#0b1120'",
        "'card': '#111827'",
        "'card_alt': '#172033'",
        "'border_soft': '#273449'",
        "'border_strong': '#334155'",
    ):
        assert token in palette

    assert dashboard.count("colors=dict(_FIXED_COLORS)") >= 4
    assert "MarketTrendWidget(tab, dashboard_ref=self, colors=dict(_FIXED_COLORS))" in dashboard


def test_market_trend_learning_and_assistant_normalize_widget_colors():
    trend = (ROOT / "ui" / "widgets" / "market_trend_widget.py").read_text(encoding="utf-8")
    learning = (ROOT / "ui" / "widgets" / "ai_learning_widget.py").read_text(encoding="utf-8")
    assistant = (ROOT / "ui" / "widgets" / "ai_assistant_widget.py").read_text(encoding="utf-8")

    for source in (trend, learning, assistant):
        assert "build_widget_palette" in source
        assert 'palette["content_bg"]' in source

    assert 'self._color("card", "#111827")' in trend
    assert 'self._color("border_soft", "#273449")' in learning
    assert 'self._color("border_strong", "#334155")' in assistant


def test_crypto_and_stock_market_trend_use_the_same_visual_contract():
    dashboard = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    crypto = dashboard.split("def _ensure_trend_tab", 1)[1].split(
        "def _ensure_blockchain_settings_tab", 1
    )[0]
    stock = dashboard.split("def _ensure_stock_trend_tab", 1)[1].split(
        "def _ensure_stock_settings_tab", 1
    )[0]

    constructor = "MarketTrendWidget(tab, dashboard_ref=self, colors=dict(_FIXED_COLORS))"
    assert constructor in crypto
    assert constructor in stock


def test_ai_report_primary_and_safe_widgets_use_the_common_palette():
    dashboard = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    report = (ROOT / "ui" / "widgets" / "ai_report_widget.py").read_text(encoding="utf-8")
    safe = (ROOT / "ui" / "widgets" / "ai_report_widget_safe.py").read_text(encoding="utf-8")

    report_tab = dashboard.split("def _ensure_ai_report_tab", 1)[1].split(
        "def _ensure_ai_assistant_tab", 1
    )[0]
    assert "report_palette = build_widget_palette(dict(_FIXED_COLORS))" in report_tab
    assert "AIReportWidget(container, colors=report_palette)" in report_tab
    assert "AIReportWidgetSafe(container, colors=report_palette)" in report_tab

    for source in (report, safe):
        assert "build_widget_palette" in source
        assert "style_tabview(" in source
        assert 'self._color("content_bg", "#0b1120")' in source
        assert 'self._color("surface", "#111827")' in source
        assert 'self._color("border_strong", "#334155")' in source


def test_stock_trade_stats_and_life_monthly_summary_use_common_cards():
    dashboard = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    life = (ROOT / "ui" / "widgets" / "life_finance_widget.py").read_text(encoding="utf-8")

    stock = dashboard.split("def _ensure_stock_trading_stats_tab", 1)[1].split(
        "def _ensure_stock_trend_tab", 1
    )[0]
    assert 'fg_color=self._color("content_bg", "#0b1120")' in stock
    assert 'fg_color=self._color("surface", "#111827")' in stock
    assert 'border_color=self._color("border", "#273449")' in stock

    monthly = life.split("# 1. 월간 요약 카드", 1)[1].split("# 2. 비교", 1)[0]
    assert 'fg_color="#111827"' in monthly
    assert 'fg_color="#172033"' in monthly
    assert 'border_color="#334155"' in monthly
    assert 'text_color="#9ca3af"' in monthly


def test_assistant_does_not_render_the_internal_model_caption():
    source = (ROOT / "ui" / "widgets" / "ai_assistant_widget.py").read_text(encoding="utf-8")
    info_bar = source.split("def create_info_bar", 1)[1].split("def copy_all_chat", 1)[0]

    assert "현재 어시스턴트 모델:" not in info_bar
    assert "self.model_caption = None" in info_bar
    assert "전체 복사" in info_bar
    assert "TXT 저장" in info_bar
