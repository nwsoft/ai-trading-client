from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_settings_diagnosis_starts_collapsed_and_reserves_footer_before_tabs():
    source = _read("ui/settings_modern.py")

    assert "self._ai_diagnosis_collapsed = True" in source
    assert "text='상세 보기' if self._ai_diagnosis_collapsed else '접기'" in source
    assert 'height=500' in source
    assert 'button_frame.pack(side="bottom", fill="x"' in source
    assert source.index("self.create_button_area(main_frame)") < source.index(
        "self.tabview = ctk.CTkTabview("
    )


def test_settings_footer_buttons_use_compact_dimensions():
    source = _read("ui/settings_modern.py")
    footer = source[
        source.index("    def create_button_area(") : source.index("    def center_window(")
    ]

    assert footer.count("height=38") == 3
    assert "width=142" in footer
    assert "width=90" in footer
    assert "width=132" in footer
    assert 'size=13, weight="bold"' in footer
    assert footer.count('padx=(0, 6)') == 3


def test_settings_modal_lock_is_deferred_until_construction_finishes():
    source = _read("ui/settings_modern.py")
    init_source = source[
        source.index("    def __init__(") : source.index("    def _activate_modal(")
    ]

    assert "self.root.after_idle(self._activate_modal)" in init_source
    assert "self.root.grab_set()" not in init_source
    assert "self.root.destroy()" in init_source
    assert "raise" in init_source


def test_icon_cache_keeps_pil_source_instead_of_tk_bound_ctkimage():
    source = _read("ui/visual_system.py")

    assert "_ICON_CACHE[key] = image" in source
    assert "_ICON_CACHE[key] = icon" not in source
    assert "cached_image = _ICON_CACHE.get(key)" in source
    assert "return ctk.CTkImage(light_image=cached_image" in source


def test_diagnosis_toggle_restores_body_without_tk_runtime():
    from ui.settings_modern import ModernSettingsWindow

    class FakeFrame:
        def __init__(self):
            self.visible = False

        def pack(self, **_kwargs):
            self.visible = True

        def pack_forget(self):
            self.visible = False

    class FakeButton:
        def __init__(self):
            self.text = ""

        def configure(self, **kwargs):
            self.text = kwargs.get("text", self.text)

    window = object.__new__(ModernSettingsWindow)
    window._ai_diagnosis_collapsed = True
    window._ai_diagnosis_body_frame = FakeFrame()
    window._ai_diagnosis_toggle_btn = FakeButton()

    window._toggle_ai_diagnosis_panel()
    assert window._ai_diagnosis_collapsed is False
    assert window._ai_diagnosis_body_frame.visible is True
    assert window._ai_diagnosis_toggle_btn.text == "접기"

    window._toggle_ai_diagnosis_panel()
    assert window._ai_diagnosis_collapsed is True
    assert window._ai_diagnosis_body_frame.visible is False
    assert window._ai_diagnosis_toggle_btn.text == "상세 보기"
