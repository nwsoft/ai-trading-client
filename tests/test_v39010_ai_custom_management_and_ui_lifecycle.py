from __future__ import annotations

from pathlib import Path

import pytest

from trading.custom_strategy_pipeline import CustomStrategyPipeline
from ui.widget_lifecycle import widget_is_owned_by


ROOT = Path(__file__).resolve().parents[1]


def _rules(seed: int = 0):
    return {
        "entry": f"RSI < {30 + seed}",
        "exit": "RSI > 60",
        "stop_loss": 1.0,
        "take_profit": 2.0,
        "position_size": 0.05,
        "market_conditions": ["range"],
        "target_scope": "exchange:binance",
        "market_regimes": ["range"],
        "regime_scope": "market",
        "priority": 5,
    }


def test_settings_deepcopy_dependency_is_imported_in_dashboard_module() -> None:
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    imports = source[: source.index("class ModernDashboard")]
    assert "import copy" in imports
    assert "current_settings=copy.deepcopy(self.settings)" in source


def test_source_tab_renderer_coalesces_stale_requests_and_checks_ownership() -> None:
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    schedule = source[
        source.index("    def _schedule_source_tab_render("):
        source.index("    def _assert_dashboard_widget_ownership(")
    ]
    ensure = source[
        source.index("    def _ensure_active_source_tab("):
        source.index("    def _build_source_tab_content(")
    ]
    assert "self._cancel_source_tab_render(service)" in schedule
    assert "generation != self._source_render_generation.get(service)" in schedule
    assert "selected != label" in schedule
    assert "expected_generation" in ensure
    assert ensure.index("self._build_source_tab_content(") < ensure.index(
        "self._clear_tab_children(previous_frame)"
    )
    assert "_assert_dashboard_widget_ownership" in ensure


def test_scrollable_ai_custom_screen_is_recognized_as_owned_after_seven_saved_strategies() -> None:
    class FakeTab:
        pass
    tab = FakeTab()
    widget = type("ScrollableWidget", (), {})()
    widget.master = object()
    widget._parent_frame = type("ScrollableHost", (), {"master": tab})()
    widget.winfo_exists = lambda: 1
    widget.saved_strategy_rows = [f"strategy-{index}" for index in range(7)]

    assert len(widget.saved_strategy_rows) == 7
    assert widget_is_owned_by(widget, tab) is True
    assert widget_is_owned_by(widget, FakeTab()) is False


def test_ai_custom_startup_and_tab_selection_do_not_rebuild_the_heavy_tree() -> None:
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    ensure = source[
        source.index("    def _ensure_custom_strategy_tab("):
        source.index("    def _ensure_life_finance_tab(")
    ]
    main_content = source[
        source.index("    def create_main_content("):
        source.index("    def _open_manual_modal(")
    ]
    assert "current_is_owned" in ensure
    assert "current_is_owned = widget_is_owned_by(current, tab)" in ensure
    assert "if current_is_owned:" in ensure
    assert ensure.index("if current_is_owned:") < ensure.index("self._clear_tab_children(tab)")
    assert "_custom_strategy_widget_building" in ensure
    assert "self._ensure_custom_strategy_tab(materialize=False)" in main_content
    assert "self._schedule_custom_strategy_tab_render()" in source


def test_inactive_private_strategy_can_be_deleted_with_audit_tombstone(tmp_path) -> None:
    storage = tmp_path / "strategies.json"
    pipeline = CustomStrategyPipeline(storage_path=str(storage))
    first = pipeline.submit(name="editable", rules=_rules())
    pipeline.submit(
        name="editable",
        rules=_rules(1),
        strategy_key=first["strategy_key"],
    )

    deleted = pipeline.delete_strategy(
        first["strategy_key"],
        deleted_by="dashboard_user",
    )

    assert deleted["deleted_versions"] == 2
    assert pipeline.list_versions(first["strategy_key"]) == []
    assert pipeline.deletion_history[-1]["scope"] == "strategy"
    assert "rules" not in pipeline.deletion_history[-1]


def test_active_private_strategy_must_be_deactivated_before_delete() -> None:
    pipeline = CustomStrategyPipeline(min_paper_trades=1)
    item = pipeline.submit(name="active", rules=_rules())
    key, version_id = item["strategy_key"], item["version_id"]
    pipeline.approve(key, version_id, approved_by="tester")
    pipeline.record_paper_validation(key, version_id, trades=1)
    pipeline.activate(key, version_id, live_confirmation=True)

    with pytest.raises(ValueError, match="적용 해제"):
        pipeline.delete_strategy(key, deleted_by="dashboard_user")


def test_private_strategy_ui_uses_new_version_edit_and_explicit_delete() -> None:
    source = (ROOT / "ui" / "widgets" / "custom_strategy_widget.py").read_text(encoding="utf-8")
    edit_source = source[
        source.index("    def _load_version_for_edit("):
        source.index("    def _delete_private_strategy(")
    ]
    delete_source = source[
        source.index("    def _delete_private_strategy("):
        source.index("    def _show_strategy_ir(")
    ]
    save_source = source[
        source.index("    def _save_version("):
        source.index("    def refresh_versions(")
    ]
    assert "수정본 준비 · 저장하면 새 버전" in edit_source
    assert "self.version_target_combo.set(label)" in edit_source
    assert '"strategy_key": selected_target[1] if selected_target else None' in save_source
    assert "delete_custom_strategy" in delete_source
    assert "적용 중인 전략" in delete_source
