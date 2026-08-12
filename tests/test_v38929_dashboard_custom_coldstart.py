import json
import hashlib
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock

from trading.analyzer import Analyzer
from trading.profitability_validation import ProfitabilityValidator
from trading.strategy_source_ingestor import ExtractedStrategySource, StrategySourceIngestor
from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.declarative_strategy_engine import DeclarativeStrategyEngine


ROOT = Path(__file__).resolve().parents[1]


def test_exchange_overview_prioritizes_three_positions_and_slim_four_kpis():
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    assert "window_height = max(900, min(980, screen_height - 40))" in source
    assert "self.minsize(min(1280, window_width), min(900, window_height))" in source
    # 거래소/증권사가 하나의 지연 생성 공통 builder를 사용하므로 높이 계약도
    # 중복 구현하지 않고 한 곳에서 양쪽 source에 적용한다.
    assert source.count("stats.configure(height=88)") >= 1
    assert source.count("left_pane.grid_rowconfigure(3, minsize=88)") >= 1
    assert source.count("left_pane.grid_rowconfigure(2, weight=1, minsize=230)") >= 1
    assert source.count("positions.configure(height=240)") >= 1
    assert "CTkScrollableFrame" in source
    assert "body, height=58" in source
    assert "card.grid_propagate(False)" in source
    assert "미실현 PnL" in source
    assert "7초 자동 갱신" in source
    assert 'grid.grid_columnconfigure((0, 1, 2, 3)' in source
    assert '("total", "총 거래"' in source
    assert '("win_rate", "승률"' in source
    assert '("pnl", "순손익"' in source
    assert '("fees", "수수료"' in source
    assert '("today", "오늘 체결"' in source
    assert '("open_orders", "미체결"' in source


def test_exchange_balance_metrics_prioritize_quote_assets_and_limit_to_three():
    # 전체 suite의 다른 테스트가 customtkinter를 모의 모듈로 교체하므로
    # 실제 UI 모듈의 순서 독립성을 보장하기 위해 깨끗한 프로세스에서 검증한다.
    script = """
from ui.dashboard_modern import ModernDashboard
class Formatter:
    _format_balance_number = ModernDashboard._format_balance_number
formatter = Formatter()
metrics = ModernDashboard._balance_metric_items(
    formatter, 'binance', {'USDT': 1234.5, 'BTC': 0, 'ETH': 0, 'XRP': 50, 'SOL': 2}
)
assert metrics == [('USDT', '1,234.50'), ('XRP', '50'), ('SOL', '2')], metrics
krw_metrics = ModernDashboard._balance_metric_items(
    formatter, 'upbit', {'KRW': 2500000, 'BTC': 0, 'ETH': 0, 'XRP': 75}
)
assert krw_metrics[0] == ('KRW', '2,500,000'), krw_metrics
assert krw_metrics[1] == ('XRP', '75'), krw_metrics
assert len(krw_metrics) == 2, krw_metrics
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True, timeout=20,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_pine_source_is_converted_to_complete_reviewable_rules_without_api():
    pine = """
//@version=5
strategy("RSI EMA")
longCondition = ta.rsi(close, 14) < 30 and close > ta.ema(close, 200)
if longCondition
    strategy.entry("L", strategy.long)
strategy.exit("X", "L")
stop_loss 1%
take_profit 2%
position_size 5%
market conditions EMA RSI trend
"""
    result = StrategySourceIngestor().analyze(pine, "pine")
    assert result["source"]["kind"] == "pine"
    assert result["ready_for_review"] is True
    assert result["engine_settings"]["sl_percent"] == 1.0
    assert result["engine_settings"]["tp_percent"] == 2.0
    assert result["engine_settings"]["position_size"] == 0.05
    assert all(result["rules"].get(key) for key in StrategySourceIngestor.REQUIRED_RULES)
    assert result["rules"]["executable_entry"]["all"]
    assert {
        "field": "current_price", "operator": "gt_field", "value_field": "ema200",
    } in result["rules"]["executable_entry"]["all"]


def test_pine_crossover_preserves_previous_bar_semantics():
    pine = """
//@version=5
strategy("EMA cross")
longCondition = ta.crossover(close, ta.ema(close, 200))
if longCondition
    strategy.entry("L", strategy.long)
strategy.exit("X", "L")
stop_loss 1%
take_profit 2%
position_size 5%
상승장
"""
    result = StrategySourceIngestor().analyze(pine, "pine")
    assert {
        "field": "current_price",
        "operator": "crosses_above",
        "value_field": "ema200",
    } in result["rules"]["executable_entry"]["all"]


def test_declarative_entry_rules_gate_actual_signal_context():
    rules = {
        "executable_entry": {
            "all": [
                {"field": "signal", "operator": "eq", "value": "LONG"},
                {"field": "rsi", "operator": "lt", "value": 30},
            ],
            "any": [],
        }
    }
    assert DeclarativeStrategyEngine.evaluate_entry(rules, {"signal": "LONG", "rsi": 27})["allowed"] is True
    assert DeclarativeStrategyEngine.evaluate_entry(rules, {"signal": "LONG", "rsi": 45})["allowed"] is False


def test_incomplete_strategy_is_not_filled_with_invented_conditions():
    result = StrategySourceIngestor().analyze("RSI가 낮으면 매수를 생각한다", "text")
    assert result["ready_for_review"] is False
    assert "exit" in result["missing_conditions"]
    assert "stop_loss" in result["missing_conditions"]


def test_youtube_id_supports_watch_shorts_share_embed_and_live_urls():
    video_id = "exQKPige-og"
    urls = [
        f"https://www.youtube.com/watch?v={video_id}&t=12",
        f"https://www.youtube.com/shorts/{video_id}?feature=share",
        f"https://youtu.be/{video_id}?si=test",
        f"https://www.youtube.com/embed/{video_id}",
        f"https://www.youtube.com/live/{video_id}",
    ]
    assert [StrategySourceIngestor._youtube_id(url) for url in urls] == [video_id] * len(urls)


def test_youtube_without_caption_or_screen_evidence_never_becomes_review_ready():
    class EvidenceMissingIngestor(StrategySourceIngestor):
        def extract(self, value, kind="auto"):
            return ExtractedStrategySource(
                kind="youtube",
                reference="https://www.youtube.com/watch?v=exQKPige-og",
                title="승률을 주장하는 제목",
                text="제목: 승률 92% 전략\n제작자: 테스트",
                warnings=["자막과 화면 근거 없음"],
                evidence={"strategy_evidence_available": False},
            )

    result = EvidenceMissingIngestor().analyze("ignored", "youtube")
    assert result["ai_analyzed"] is False
    assert result["ready_for_review"] is False
    assert set(StrategySourceIngestor.REQUIRED_RULES).issubset(result["missing_conditions"])


def test_custom_strategy_worker_captures_error_before_tk_callback_runs():
    source = (ROOT / "ui" / "widgets" / "custom_strategy_widget.py").read_text(encoding="utf-8")
    assert "lambda error=error: self._show_error(error)" in source
    assert "lambda: self._show_error(str(exc))" not in source
    assert '"*.md *.pdf *.pine *.txt' in source


def test_packaged_build_collects_dynamic_ytdlp_extractors():
    hook = (ROOT / "hooks" / "hook-yt_dlp.py").read_text(encoding="utf-8")
    assert 'collect_submodules("yt_dlp")' in hook
    assert "hookspath=['hooks']" in (ROOT / "build_safe.py").read_text(encoding="utf-8")


def test_new_user_gets_limited_learning_profile_instead_of_permanent_block():
    report = ProfitabilityValidator().evaluate_strategy([], {"enabled": True, "min_trades": 10})
    assert report["enabled"] is True
    assert report["bypassed"] is True
    assert report["stage"] == "limited_live_learning"
    assert report["max_positions"] == 1
    assert report["max_leverage"] == 1
    assert report["risk_multiplier"] == 0.1
    assert report["next_review_at_trades"] == 10


def test_custom_strategy_accepts_real_observation_validation_after_approval(tmp_path):
    pipeline = CustomStrategyPipeline(str(tmp_path / "strategies.json"), min_paper_trades=3)
    version = pipeline.submit(
        name="observed",
        rules={key: "defined" for key in pipeline.REQUIRED_RULES},
    )
    pipeline.approve(version["strategy_key"], version["version_id"], approved_by="tester")
    checked = pipeline.record_execution_validation(
        version["strategy_key"], version["version_id"],
        decisions=3, guardrail_violations=0,
        metrics={"net_pnl": 1.2, "fees": 0.1}, mode="live_observation",
    )
    assert checked["status"] == "execution_validated"
    assert checked["execution_validation"]["mode"] == "live_observation"


def test_limited_learning_risk_increases_gradually_but_stays_capped():
    trades = [{"pnl": 1, "price": 1, "quantity": 1} for _ in range(9)]
    report = ProfitabilityValidator().evaluate_strategy(trades, {"enabled": True, "min_trades": 10})
    assert report["stage"] == "limited_live_learning"
    assert 0.1 < report["risk_multiplier"] <= 0.5


def test_analyzer_score_threshold_is_isolated_per_exchange():
    analyzer = Analyzer.__new__(Analyzer)
    analyzer.user_signal_threshold = 68
    analyzer.exchange_signal_thresholds = {}
    analyzer._exchange_context_local = __import__("threading").local()
    analyzer.ai_report_manager = None
    analyzer.logger = MagicMock()

    analyzer.set_user_signal_threshold(62, exchange_name="okx")
    analyzer.set_user_signal_threshold(74, exchange_name="bybit")

    assert analyzer.get_user_signal_threshold("okx") == 62
    assert analyzer.get_user_signal_threshold("bybit") == 74
    assert analyzer.get_user_signal_threshold("bitget") == 68


def test_settings_close_requires_explicit_choice_and_never_sys_exit():
    source = (ROOT / "ui" / "settings_modern.py").read_text(encoding="utf-8")
    block = source[source.index("    def on_closing(self):"):source.index("    def load_current_settings(self):")]
    assert "_ask_save_on_close" in block
    assert "self.save_settings()" in block
    assert "sys.exit" not in block


def test_settings_have_visible_section_save_bars_and_noahai_close_branding():
    source = (ROOT / "ui" / "settings_modern.py").read_text(encoding="utf-8")
    assert source.count("self._add_tab_save_bar(tab") >= 8
    dialog = source[source.index("    def _ask_save_on_close"):source.index("    @staticmethod\n    def _shade_color")]
    assert "ctk.CTkToplevel(" not in dialog
    assert "messagebox.askyesnocancel(" in dialog
    assert "저장 후 닫기" in dialog
    assert "저장하지 않고 닫기" in dialog
    assert "계속 편집" in dialog
    assert "ai_custom_runtime_enabled_var" in source
    assert "ai_custom_limited_live_var" in source
    assert "AI 커스텀 전략을 실제 자동매매 엔진에서 사용" in source
    assert "self.ai_custom_runtime_enabled_var = ctk.BooleanVar(value=False)" in source
    assert "self.ai_custom_limited_live_var = ctk.BooleanVar(value=False)" in source
    assert 'text="AI 애널리스트 모델:"' in source
    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "if 'ai_custom_runtime' in changed_keys:" in main_source
    assert "self.sync_custom_strategy_runtime_pools()" in main_source

    custom_source = (ROOT / "ui" / "widgets" / "custom_strategy_widget.py").read_text(encoding="utf-8")
    assert "검토 및 전략 버전 저장" in custom_source
    guidance_source = (ROOT / "ui" / "ai_custom_guidance.py").read_text(encoding="utf-8")
    assert "AI_CUSTOM_CONFIRM_ROLE_LABEL" in custom_source
    assert "AI_CUSTOM_INDEPENDENT_ROLE_LABEL" in custom_source
    assert 'AI_CUSTOM_CONFIRM_ROLE_LABEL = "기본 AI 후보 확인 (권장)"' in guidance_source
    assert 'AI_CUSTOM_INDEPENDENT_ROLE_LABEL = "사용자 전략 독립 신호 (숙련자)"' in guidance_source
    assert 'runtime_cfg.get("enabled", False)' in custom_source

    config_source = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    assert "_ai_custom_runtime_safe_default_v3900_applied" in config_source
    assert "runtime_cfg['enabled'] = False" in config_source
    assert "runtime_cfg['allow_limited_live'] = False" in config_source


def test_trading_stats_kpis_use_single_four_card_row():
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    block = source[source.index("    def _ensure_trading_stats_tab"):source.index("    def _ensure_trend_tab")]
    assert "card.grid(row=0, column=index" in block
    assert 'uniform="trade_stats_kpi"' in block
    assert '"누적 PnL", "누적 Fee"' in block
    assert "BINANCE (LEGACY)" in source


def test_custom_strategy_pool_selects_scope_regime_and_priority():
    strategies = [
        {
            "id": "range-low", "name": "횡보 저우선", "priority": 4,
            "target_scope": "asset:crypto", "market_regimes": ["range"],
            "rules": {"executable_entry": {"all": [{"field": "rsi", "operator": "lt", "value": 40}]}},
            "engine_settings": {"leverage": 1},
        },
        {
            "id": "range-high", "name": "횡보 고우선", "priority": 9,
            "target_scope": "exchange:okx", "market_regimes": ["range"],
            "rules": {"executable_entry": {"all": [{"field": "rsi", "operator": "lt", "value": 35}]}},
            "engine_settings": {"leverage": 2},
        },
    ]
    result = DeclarativeStrategyEngine.evaluate_strategy_pool(
        strategies, {"rsi": 30}, asset_class="crypto", target="okx", market_regime="SIDEWAYS"
    )
    assert result["allowed"] is True
    assert result["selected_strategy_id"] == "range-high"
    assert result["engine_settings"]["leverage"] == 2


def test_strategy_pool_bypasses_unrelated_asset_scope_without_blocking():
    result = DeclarativeStrategyEngine.evaluate_strategy_pool(
        [{
            "id": "stock-only", "target_scope": "asset:stock", "market_regimes": ["all"],
            "rules": {"executable_entry": {"all": [{"field": "signal", "operator": "eq", "value": "LONG"}]}},
        }],
        {"signal": "LONG"}, asset_class="crypto", target="binance", market_regime="bull",
    )
    assert result["allowed"] is True
    assert result["bypassed"] is True


def test_existing_strategy_key_creates_incrementing_versions_and_trims_to_ten(tmp_path):
    pipeline = CustomStrategyPipeline(str(tmp_path / "versions.json"))
    rules = {key: "defined" for key in pipeline.REQUIRED_RULES}
    first = pipeline.submit(name="versioned", rules=rules)
    for index in range(11):
        pipeline.submit(name=f"versioned-{index}", rules=rules, strategy_key=first["strategy_key"])
    versions = pipeline.list_versions(first["strategy_key"])
    assert len(versions) == 10
    assert versions[-1]["version"] == 12


def test_custom_strategy_manual_exposes_real_button_flow_and_scopes():
    manual = (ROOT / "ui" / "widgets" / "user_manual_widget.py").read_text(encoding="utf-8")
    assert 'tab_widget.add("AI 커스텀")' in manual
    assert "manual_width = max(900, min(1240, screen_width - 60))" in manual
    assert "style_tabview(" in manual
    for text in (
        "모든 블록체인", "모든 주식/ETF", "실행 검증 기록", "최종 적용", "최대 10개",
        "전략 설명 / Pine Script 직접 입력", "앞 100쪽", "앞 60,000자", "대표 장면 최대 9개",
        "설정 위치: 대시보드 상단", "정밀 진단·최적화(고성능 모델)",
        "TradingView·영상·문서·Pine 전략", "별도의 끝없는 승인 단계를 추가하지 않습니다",
    ):
        assert text in manual


def test_gpt56_catalog_and_dynamic_model_listing_are_exposed():
    settings_source = (ROOT / "ui" / "settings_modern.py").read_text(encoding="utf-8")
    client_source = (ROOT / "trading" / "ai" / "openai_client.py").read_text(encoding="utf-8")
    for model in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
        assert model in settings_source
    assert "def list_chat_models" in client_source
    assert "def vision_json" in client_source
    assert "max_completion_tokens" in client_source


def test_custom_strategy_source_limits_and_visible_ai_model_are_explicit():
    widget = (ROOT / "ui" / "widgets" / "custom_strategy_widget.py").read_text(encoding="utf-8")
    ingestor = (ROOT / "trading" / "strategy_source_ingestor.py").read_text(encoding="utf-8")
    assert "사용 AI:" in widget
    assert "AI 모델 설정 열기" in widget
    assert "PDF_MAX_PAGES = 100" in ingestor
    assert "AI_CONTENT_CHAR_LIMIT = 60000" in ingestor
    assert "VIDEO_SAMPLE_FRAMES = 9" in ingestor
    assert "_vision_strategy_text" in ingestor
    assert "audio_transcript_available" in ingestor


def test_windows_executable_metadata_is_aligned_to_3909():
    version_info = (ROOT / "config" / "windows_version_info.txt").read_text(encoding="utf-8")
    spec = (ROOT / "aiautotrade.spec").read_text(encoding="utf-8")
    safe_builder = (ROOT / "build_safe.py").read_text(encoding="utf-8")
    assert "filevers=(3, 9, 0, 9)" in version_info
    assert "ProductVersion', u'3.9.0.9'" in version_info
    assert "version='config/windows_version_info.txt'" in spec
    assert "version='config/windows_version_info.txt'" in safe_builder
    assert 'RELEASE_VERSION = "3.9.0.9"' in (ROOT / "config" / "app_version.py").read_text(encoding="utf-8")
    assert (ROOT / "deploy" / "version.txt").read_text(encoding="utf-8").strip() == "3.9.0.9"
    manifest = json.loads((ROOT / "deploy" / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "3.9.0.9"
    exe_asset = manifest["assets"]["exe"]
    # v3.9.0.9는 Windows 재빌드 대기이며 직전 공개 Fix 4는 별도 보존한다.
    assert manifest.get("build_status") == "pending_windows_rebuild"
    assert exe_asset["size"] == 0
    assert exe_asset["sha256"] == ""
    previous_asset = manifest["previous_published_asset"]
    exe_path = ROOT / previous_asset["path"]
    assert exe_path.exists()
    assert previous_asset["size"] == exe_path.stat().st_size
    digest = hashlib.sha256()
    with exe_path.open("rb") as exe_file:
        for chunk in iter(lambda: exe_file.read(1024 * 1024), b""):
            digest.update(chunk)
    assert previous_asset["sha256"] == digest.hexdigest()
    assert previous_asset["version"] == "3.9.0.8"
    assert previous_asset["release_label"] == "v3.9.0.8 AI Custom Update Fix 4"
    assert previous_asset["purpose"] == "previous_published_windows_build"
    assert "/v3.9.0.9/AITrading.exe" in manifest["assets"]["exe"]["download_url"]
    release_builder = (ROOT / "scripts" / "generate_release_assets.py").read_text(encoding="utf-8")
    assert "AITrading.exe가 최신 런타임 소스보다 오래된 빌드" in release_builder
    assert "_latest_runtime_source" in release_builder
    release_push = (ROOT / "scripts" / "release_tag_push.ps1").read_text(encoding="utf-8")
    assert "EXE ProductVersion mismatch" in release_push


def test_3901_update_notice_and_financial_intelligence_manual_are_visible():
    dashboard = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    manual = (ROOT / "ui" / "widgets" / "user_manual_widget.py").read_text(encoding="utf-8")
    assert "RELEASE_HIGHLIGHT" in dashboard
    assert "업데이트·사용법" in dashboard
    assert 'self._open_manual_modal("업데이트")' in dashboard
    assert 'tab_widget.add("금융 인텔리전스")' in manual


def test_3901_footer_is_one_row_and_keeps_content_height():
    dashboard = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    assert 'self.status_display.grid(row=0, column=0' in dashboard
    assert 'update_card.grid(row=0, column=1' in dashboard
    assert 'summary_card.grid(row=0, column=2' in dashboard
    assert 'update_card.pack(fill="x"' not in dashboard
    assert "inner.grid_columnconfigure(0, weight=3" in dashboard


def test_3901_cross_platform_icon_and_tab_visual_system_is_shared():
    dashboard = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    settings = (ROOT / "ui" / "settings_modern.py").read_text(encoding="utf-8")
    manual = (ROOT / "ui" / "widgets" / "user_manual_widget.py").read_text(encoding="utf-8")
    visual = (ROOT / "ui" / "visual_system.py").read_text(encoding="utf-8")
    assert "def get_ui_icon(" in visual
    assert "운영체제의 컬러 이모지 폰트를 사용하지 않으므로" in visual
    for icon_name in ("blockchain", "stock", "portfolio", "wallet", "analyst"):
        assert f'"{icon_name}"' in dashboard
    assert "style_tabview(" in dashboard
    assert "style_tabview(" in settings
    assert "style_tabview(" in manual


def test_3901_financial_intelligence_order_is_canonical_without_rebuild_dependency():
    dashboard = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    switch_body = dashboard[dashboard.index("    def switch_service"):dashboard.index("    def _get_ops_kpi_specs_for_service")]
    policy_body = dashboard[dashboard.index("    def _apply_service_tab_policy"):dashboard.index("    def _check_actual_exchange_status")]
    assert "self.create_service_sub_tabs(service_name)" in switch_body
    assert "get_service_tab_order" in policy_body
    assert "reorder_ctk_tabs" in policy_body


def test_3901_user_financial_intelligence_has_no_raw_json_input():
    widget = (ROOT / "ui" / "widgets" / "financial_intelligence_widget.py").read_text(encoding="utf-8")
    assert "_json_box" not in widget
    assert "json.loads" not in widget
    assert "CTkTextbox" in widget
    assert "chart_canvases" in widget


def test_3901_safe_build_bundles_life_finance_catalog_only():
    safe_builder = (ROOT / "build_safe.py").read_text(encoding="utf-8")
    spec = (ROOT / "aiautotrade.spec").read_text(encoding="utf-8")
    assert "('data/finance_products', 'data/finance_products')" in safe_builder
    assert "('data/finance_products', 'data/finance_products')" in spec
