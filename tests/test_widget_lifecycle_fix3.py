from pathlib import Path

from ui.widget_lifecycle import delete_ctk_tab, get_windows_gui_resources


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
    assert source.count("delete_ctk_tab(") >= 5
    assert "tv.delete(tab_name)" not in source
    assert "self.tab_widget.delete(label)" not in source


def test_gui_resource_probe_is_safe_off_windows():
    result = get_windows_gui_resources()
    assert result is None or set(result) == {"gdi", "user"}
