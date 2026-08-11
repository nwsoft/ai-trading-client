from pathlib import Path

from ui.widget_lifecycle import (
    WidgetOwnershipRegistry,
    delete_ctk_tab,
    get_windows_gui_resources,
)


class _Widget:
    def __init__(self, children=None):
        self.children = list(children or [])
        self.events = []
        self.exists = True

    def winfo_children(self):
        return list(self.children)

    def cleanup_after_jobs(self):
        self.events.append("cleanup_after_jobs")

    def cleanup(self):
        self.events.append("cleanup")

    def winfo_exists(self):
        return self.exists

    def destroy(self):
        self.events.append("destroy")
        self.exists = False


class _Tabview:
    def __init__(self, name, frame):
        self._tab_dict = {name: frame}
        self.deleted = []

    def delete(self, name):
        self.deleted.append(name)
        self._tab_dict.pop(name)


def test_dynamic_tab_delete_cleans_children_and_destroys_frame():
    child = _Widget()
    frame = _Widget([child])
    tabview = _Tabview("BITGET", frame)

    assert delete_ctk_tab(tabview, "BITGET") is True
    assert tabview.deleted == ["BITGET"]
    assert child.events == ["cleanup_after_jobs", "cleanup"]
    assert frame.events == ["cleanup_after_jobs", "cleanup", "destroy"]
    assert frame.exists is False


def test_dynamic_tab_delete_is_idempotent_for_missing_tab():
    frame = _Widget()
    tabview = _Tabview("OKX", frame)
    assert delete_ctk_tab(tabview, "OKX") is True
    assert delete_ctk_tab(tabview, "OKX") is False
    assert frame.events.count("destroy") == 1


def test_dashboard_dynamic_tab_paths_use_destructive_helper():
    source = (Path(__file__).parents[1] / "ui" / "dashboard_modern.py").read_text(
        encoding="utf-8"
    )
    # 대시보드 삭제는 단 하나의 소유권 경계만 통과한다. 저수준 helper를
    # 여러 곳에서 직접 호출하면 캐시 무효화가 다시 누락될 수 있다.
    assert source.count("delete_ctk_tab(") == 1
    assert source.count("self._delete_dashboard_tab(") >= 3
    assert "tv.delete(tab_name)" not in source
    assert "self.tab_widget.delete(label)" not in source


def test_widget_ownership_registry_clears_attribute_and_mapping_by_identity():
    registry = WidgetOwnershipRegistry()
    owner = type("Owner", (), {})()
    mapping = {}
    first = _Widget()
    second = _Widget()

    registry.register_attribute("AI 어시스턴트", owner, "assistant", first)
    registry.register_mapping("금융 인텔리전스", mapping, "blockchain", first)
    registry.register_attribute("AI 어시스턴트", owner, "assistant", second)

    assert owner.assistant is second
    assert mapping["blockchain"] is first
    assert registry.invalidate("AI 어시스턴트") == 1
    assert owner.assistant is None
    assert mapping["blockchain"] is first
    assert registry.invalidate("금융 인텔리전스") == 1
    assert "blockchain" not in mapping


def test_widget_ownership_registry_stays_bounded_during_rebuild_stress():
    registry = WidgetOwnershipRegistry()
    owner = type("Owner", (), {})()

    for _ in range(200):
        registry.register_attribute("시장 트렌드", owner, "trend", _Widget())
        assert registry.binding_count() == 1
        registry.invalidate("시장 트렌드")
        assert owner.trend is None
        assert registry.binding_count() == 0


def test_gui_resource_probe_is_safe_off_windows():
    result = get_windows_gui_resources()
    assert result is None or set(result) == {"gdi", "user"}
