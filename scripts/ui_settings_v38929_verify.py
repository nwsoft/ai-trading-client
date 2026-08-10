#!/usr/bin/env python3
"""실계정 값을 읽지 않고 v3.9.0.0 설정 저장 UX를 렌더링한다."""

from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import customtkinter as ctk

from ui.settings_modern import ModernSettingsWindow


def main():
    ctk.set_appearance_mode("dark")
    window = ModernSettingsWindow(current_settings={})
    verify_tab = str(os.environ.get("NOAHAI_SETTINGS_VERIFY_TAB", "") or "").strip()
    if verify_tab:
        window.tabview.set(verify_tab)
    verify_scroll = str(os.environ.get("NOAHAI_SETTINGS_VERIFY_SCROLL", "") or "").lower()
    if verify_scroll:
        try:
            scroll_fraction = 1.0 if verify_scroll == "bottom" else max(0.0, min(1.0, float(verify_scroll)))
        except ValueError:
            scroll_fraction = 0.0

        def _scroll_visible_frames_to_bottom():
            stack = [window.root]
            while stack:
                widget = stack.pop()
                stack.extend(widget.winfo_children())
                canvas = getattr(widget, "_parent_canvas", None)
                if canvas is not None and widget.winfo_viewable():
                    try:
                        canvas.yview_moveto(scroll_fraction)
                    except Exception:
                        pass
        window.root.after(350, _scroll_visible_frames_to_bottom)
    window.root.attributes("-topmost", True)
    window.root.after(1200, lambda: window.root.attributes("-topmost", False))
    window.root.mainloop()


if __name__ == "__main__":
    main()
