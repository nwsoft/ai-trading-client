"""Shared widget teardown and Windows GUI-resource diagnostics.

CustomTkinter's ``CTkTabview.delete`` removes a tab from its internal maps but
does not destroy the tab frame.  Dynamic service/exchange tabs therefore need
an explicit teardown boundary so their ``after`` jobs, Tcl menus and child
widgets do not survive navigation.
"""

from __future__ import annotations

import ctypes
import os
from typing import Any, Dict, Optional


_CLEANUP_HOOKS = ("cleanup_after_jobs", "_cancel_after_jobs", "cleanup")


def cleanup_widget_tree(root: Any, *, include_root: bool = True) -> None:
    """Run known cleanup hooks once per widget, children first."""
    cleaned: set[int] = set()

    def _cleanup(widget: Any) -> None:
        try:
            children = list(widget.winfo_children())
        except Exception:
            children = []
        for child in children:
            _cleanup(child)

        widget_id = id(widget)
        if widget_id in cleaned:
            return
        cleaned.add(widget_id)
        for hook_name in _CLEANUP_HOOKS:
            hook = getattr(widget, hook_name, None)
            if callable(hook):
                try:
                    hook()
                except Exception:
                    pass

    if include_root:
        _cleanup(root)
        return
    try:
        children = list(root.winfo_children())
    except Exception:
        children = []
    for child in children:
        _cleanup(child)


def delete_ctk_tab(tabview: Any, name: str) -> bool:
    """Delete and *actually destroy* one CTkTabview tab.

    Returns ``True`` when the tab existed.  The frame is captured before
    ``delete`` because CustomTkinter removes the only public-ish reference.
    """
    tabs = getattr(tabview, "_tab_dict", {}) or {}
    frame = tabs.get(name)
    if frame is None:
        return False

    cleanup_widget_tree(frame)
    deleted = False
    try:
        tabview.delete(name)
        deleted = True
    finally:
        # Even if the segmented-button deletion raises, keeping an orphan Tcl
        # tree is worse.  Destroy is idempotently guarded for test doubles and
        # already-destroyed Tk widgets.
        try:
            exists = getattr(frame, "winfo_exists", None)
            if not callable(exists) or bool(exists()):
                frame.destroy()
        except Exception:
            pass
    return deleted


def get_windows_gui_resources() -> Optional[Dict[str, int]]:
    """Return current-process USER/GDI counts on Windows, else ``None``."""
    if os.name != "nt":
        return None
    try:
        process = ctypes.windll.kernel32.GetCurrentProcess()
        get_resources = ctypes.windll.user32.GetGuiResources
        return {
            "gdi": int(get_resources(process, 0)),
            "user": int(get_resources(process, 1)),
        }
    except Exception:
        return None


def log_windows_gui_resources(logger: Any, event: str) -> Optional[Dict[str, int]]:
    """Log bounded diagnostic evidence without affecting non-Windows runs."""
    resources = get_windows_gui_resources()
    if resources is not None:
        try:
            logger.info(
                "Windows GUI resources (%s): USER=%s, GDI=%s",
                event,
                resources["user"],
                resources["gdi"],
            )
        except Exception:
            pass
    return resources
