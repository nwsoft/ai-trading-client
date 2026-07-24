#!/usr/bin/env python3
"""실계정 값을 읽지 않고 v3.9.0.0 설정 저장 UX를 렌더링한다."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import customtkinter as ctk

from ui.settings_modern import ModernSettingsWindow


def main():
    ctk.set_appearance_mode("dark")
    window = ModernSettingsWindow(current_settings={})
    window.root.attributes("-topmost", True)
    window.root.after(1200, lambda: window.root.attributes("-topmost", False))
    window.root.mainloop()


if __name__ == "__main__":
    main()
