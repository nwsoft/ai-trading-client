import importlib.util
import json
import logging
from pathlib import Path

from trading.custom_strategy_presets import (
    get_beginner_preset,
    list_beginner_presets,
    preset_key_from_text,
    recommend_preset_for_regime,
)
from trading.strategy_source_ingestor import StrategySourceIngestor
from trading.unified_trader import UnifiedTrader
from ui.typography import (
    WINDOWS_KOREAN_FONT,
    platform_font_candidates,
    resolve_platform_font,
)
from utils import runtime_stability


ROOT = Path(__file__).resolve().parents[1]
_ASSISTANT_SPEC = importlib.util.spec_from_file_location(
    "test_v3903_ai_assistant_widget",
    ROOT / "ui" / "widgets" / "ai_assistant_widget.py",
)
assert _ASSISTANT_SPEC is not None and _ASSISTANT_SPEC.loader is not None
_ASSISTANT_MODULE = importlib.util.module_from_spec(_ASSISTANT_SPEC)
_ASSISTANT_SPEC.loader.exec_module(_ASSISTANT_MODULE)
AIAssistantWidget = _ASSISTANT_MODULE.AIAssistantWidget


def test_windows_typography_prefers_korean_system_font():
    assert platform_font_candidates("Windows")[0] == WINDOWS_KOREAN_FONT
    assert resolve_platform_font(
        ["Arial", "Segoe UI", "Malgun Gothic"],
        system_name="Windows",
    ) == "Malgun Gothic"
    assert resolve_platform_font(["Arial"], system_name="Windows") == "Arial"


def test_runtime_session_detects_unclean_exit_and_clean_shutdown(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_stability, "_runtime_dir", lambda: tmp_path)
    runtime_stability._SESSION_MARKER = None
    runtime_stability._CRASH_LOG = None
    runtime_stability._FATAL_EXCEPTION_SEEN = False

    first = runtime_stability.begin_runtime_session()
    marker = Path(first["marker"])
    assert first["previous_unclean"] is False
    assert marker.exists()

    second = runtime_stability.begin_runtime_session()
    assert second["previous_unclean"] is True
    assert runtime_stability.mark_clean_shutdown("test_shutdown") is True
    assert not marker.exists()
    events = [
        json.loads(line)
        for line in (tmp_path / "runtime_stability.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(item["event"] == "previous_unclean_shutdown_detected" for item in events)
    assert any(
        item["event"] == "clean_shutdown" and item["reason"] == "test_shutdown"
        for item in events
    )


def test_beginner_catalog_is_one_auto_plus_four_reviewable_templates():
    presets = list_beginner_presets()
    assert len(presets) == 5
    assert presets[0]["key"] == "auto_regime"
    assert presets[0]["executable_template"] is False
    assert sum(bool(item["executable_template"]) for item in presets) == 4
    assert all("보장하지" in item.get("source_text", "") for item in presets[1:])


def test_preset_aliases_and_hold_first_regime_recommendation():
    assert preset_key_from_text("이평선 매매를 알고 있어?") == "trend_follow"
    assert preset_key_from_text("눌림목 전략 초안을 넣어줘") == "trend_pullback"
    assert preset_key_from_text("박스권 RSI") == "range_rsi"
    assert preset_key_from_text("거래량 돌파") == "volume_breakout"
    assert recommend_preset_for_regime("range") == "range_rsi"
    assert recommend_preset_for_regime("volatile", volume_expansion=False) == "hold"
    assert recommend_preset_for_regime("trend", signal_conflict=True) == "hold"


def test_assistant_explains_moving_average_preset_without_claiming_execution():
    assistant = object.__new__(AIAssistantWidget)
    assistant.parent_dashboard = None
    assistant.logger = logging.getLogger("test-ai-custom-preset")
    response = assistant._build_ai_custom_preset_support("이평선 매매를 알고 있는지 설명해줘")
    assert response is not None
    assert "추세 따라가기" in response
    assert "HOLD" in response
    assert "보장" in response
    assert "자동검증" in response


def test_assistant_handoff_loads_draft_only_and_switches_tab():
    loaded = []
    selected_tabs = []

    class FakeCustomWidget:
        def load_beginner_preset(self, key):
            loaded.append(key)
            return True

    class FakeTabs:
        def set(self, name):
            selected_tabs.append(name)

    class FakeDashboard:
        custom_strategy_widget = FakeCustomWidget()
        tab_widget = FakeTabs()

        @staticmethod
        def _ensure_custom_strategy_tab():
            return None

    assistant = object.__new__(AIAssistantWidget)
    assistant.parent_dashboard = FakeDashboard()
    assistant.logger = logging.getLogger("test-ai-custom-preset-handoff")
    response = assistant._build_ai_custom_preset_support(
        "이평선 매매 초안을 AI 커스텀에 넣어줘"
    )
    assert loaded == ["trend_follow"]
    assert selected_tabs == ["AI 커스텀"]
    assert "아직 분석·저장·승인·실행하지 않았습니다" in response


def test_reviewable_presets_fail_closed_without_ai_structuring():
    ingestor = StrategySourceIngestor(None)
    for preset in list_beginner_presets():
        if not preset["executable_template"]:
            continue
        result = ingestor.analyze(preset["source_text"], "text")
        assert result["unsupported_conditions"] == []
        assert result["missing_conditions"]
        assert result["ready_for_review"] is False


def test_unified_start_rejects_learning_only_exchange_before_initialization():
    trader = object.__new__(UnifiedTrader)
    trader.logger = logging.getLogger("test-learning-only")
    trader._is_trade_enabled = lambda _exchange: False
    trader._ensure_exchange_initialized = lambda _exchange: (_ for _ in ()).throw(
        AssertionError("학습 전용 거래소에서 초기화가 호출되면 안 됩니다.")
    )
    assert trader.start_trading("bybit") is False


def test_feedback_surfaces_expose_trade_scope_and_preset_handoff():
    settings_source = (ROOT / "ui" / "settings_modern.py").read_text(encoding="utf-8")
    custom_source = (ROOT / "ui" / "widgets" / "custom_strategy_widget.py").read_text(encoding="utf-8")
    assistant_source = (ROOT / "ui" / "widgets" / "ai_assistant_widget.py").read_text(encoding="utf-8")
    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "실제 주문 실행 거래소" in settings_source
    assert "'trade_enabled_exchanges': trade_exchange_values" in settings_source
    assert "초보자 시작: AI 자동 대응 + 검토용 기본 전략 4개" in custom_source
    assert "고급모드 · 안전한 다중 시간대 규칙 편집" in custom_source
    assert "load_beginner_preset" in assistant_source
    assert "begin_runtime_session" in main_source


def test_preset_lookup_returns_copy():
    first = get_beginner_preset("trend_follow")
    second = get_beginner_preset("trend_follow")
    assert first and second
    first["name"] = "changed"
    assert second["name"] == "추세 따라가기"
