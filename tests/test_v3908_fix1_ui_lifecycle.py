from __future__ import annotations

import inspect
from pathlib import Path

from ui.service_tab_policy import get_service_tab_order
from ui.widget_lifecycle import cleanup_widget_tree, reorder_ctk_tabs


class _NativeMenu:
    def __init__(self) -> None:
        self.destroy_count = 0

    def destroy(self) -> None:
        self.destroy_count += 1


class _Widget:
    def __init__(self, menu=None, children=None) -> None:
        self._dropdown_menu = menu
        self._children = children or []

    def winfo_children(self):
        return list(self._children)


class _Segmented:
    def __init__(self) -> None:
        self.values = []

    def configure(self, **kwargs) -> None:
        self.values = list(kwargs["values"])


class _Tabview:
    def __init__(self) -> None:
        self._tab_dict = {name: object() for name in ["BINANCE", "실시간 거래 로그", "코인 정보"]}
        self._name_list = ["BINANCE", "실시간 거래 로그", "코인 정보"]
        self._segmented_button = _Segmented()
        self.selected = "BINANCE"

    def get(self):
        return self.selected

    def set(self, name):
        self.selected = name


def test_cleanup_releases_customtkinter_native_dropdown_menu_once() -> None:
    menu = _NativeMenu()
    widget = _Widget(menu=menu)

    cleanup_widget_tree(widget)
    cleanup_widget_tree(widget)

    assert menu.destroy_count == 1
    assert widget._dropdown_menu is None


def test_canonical_tab_order_keeps_existing_frames_and_selection() -> None:
    tabview = _Tabview()
    original_frames = dict(tabview._tab_dict)

    changed = reorder_ctk_tabs(
        tabview,
        get_service_tab_order("blockchain", ["BINANCE"]),
    )

    assert changed is True
    assert tabview._name_list == ["실시간 거래 로그", "코인 정보", "BINANCE"]
    assert tabview._segmented_button.values == tabview._name_list
    assert tabview._tab_dict == original_frames
    assert tabview.selected == "BINANCE"


def test_stock_and_blockchain_sources_never_precede_information_tab() -> None:
    blockchain = get_service_tab_order("blockchain", ["UPBIT", "BINANCE"])
    stock = get_service_tab_order("stock", ["KIWOOM", "SHINHAN"])

    assert blockchain.index("코인 정보") < blockchain.index("UPBIT")
    assert blockchain.index("코인 정보") < blockchain.index("BINANCE")
    assert stock.index("종목 정보") < stock.index("KIWOOM")
    assert "코인 정보" not in stock
    assert "종목 정보" not in blockchain


def test_settings_close_confirmation_does_not_allocate_another_ctk_toplevel() -> None:
    from ui.settings_modern import ModernSettingsWindow

    source = inspect.getsource(ModernSettingsWindow._ask_save_on_close)
    assert "ctk.CTkToplevel(" not in source
    assert "askyesnocancel" in source
    assert hasattr(ModernSettingsWindow, "show")
    assert hasattr(ModernSettingsWindow, "dispose")


def test_service_switch_has_one_source_teardown_and_current_service_refresh() -> None:
    source = (Path(__file__).resolve().parents[1] / "ui" / "dashboard_modern.py").read_text(
        encoding="utf-8"
    )
    switch_source = source[source.index("    def switch_service("):source.index("    def _get_ops_kpi_specs_for_service(")]
    refresh_source = source[source.index("    def update_exchange_info("):source.index("    # --- 대시보드 외부 호출 메서드")]
    position_source = source[source.index("    def _render_position_cards("):source.index("    def _display_unified_balances(")]

    assert "clear_service_sub_tabs(previous_service)" in switch_source
    assert "_destroy_all_service_tabs_except_protected" not in switch_source
    assert "target_service = 'stock' if current_service == 'stock' else 'blockchain'" in refresh_source
    assert "show_stock_content()" in refresh_source
    assert "identity = ctk.CTkFrame" not in position_source
    assert "card.grid_propagate(False)" in position_source


def test_same_service_click_reuses_existing_tree_and_tab_style_preserves_selection() -> None:
    source = (Path(__file__).resolve().parents[1] / "ui" / "dashboard_modern.py").read_text(
        encoding="utf-8"
    )
    switch_source = source[source.index("    def switch_service("):source.index("    def _get_ops_kpi_specs_for_service(")]
    style_source = source[source.index("    def _apply_tabview_style("):source.index("    def _clear_tab_children(")]

    assert "if previous_service == target_service:" in switch_source
    assert "service-switch-reused" in switch_source
    assert "getter = getattr(tv, \"get\", None)" in style_source
    assert "current = tv._name_list[0]  # 첫 탭을 최소 선택" not in style_source


def test_service_source_tabs_are_reused_and_partial_render_is_rejected() -> None:
    source = (Path(__file__).resolve().parents[1] / "ui" / "dashboard_modern.py").read_text(
        encoding="utf-8"
    )
    create_source = source[source.index("    def create_service_sub_tabs("):source.index("    def _get_service_split_layout(")]

    assert "all(widget_is_alive(frame) for frame in existing.values())" in create_source
    assert "self._ensure_active_source_tab(service_name, selected)" in create_source
    assert "previous_frame" in create_source
    assert "self._clear_tab_children(previous_frame)" in create_source
    assert "service_tab_partial_render:" in create_source
    assert "부분 화면으로 거래하지 말고" in create_source


def test_exit_authorizes_update_before_shutdown() -> None:
    source = (Path(__file__).resolve().parents[1] / "ui" / "dashboard_modern.py").read_text(
        encoding="utf-8"
    )
    close_source = source[source.index("    def on_closing("):source.index("    def _safe_destroy_widgets(")]

    assert close_source.index("prepare_update_preflight_on_exit") < close_source.index("shutdown_for_exit")
