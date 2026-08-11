"""Shared widget teardown and Windows GUI-resource diagnostics.

CustomTkinter's ``CTkTabview.delete`` removes a tab from its internal maps but
does not destroy the tab frame.  Dynamic service/exchange tabs therefore need
an explicit teardown boundary so their ``after`` jobs, Tcl menus and child
widgets do not survive navigation.
"""

from __future__ import annotations

import ctypes
import os
import threading
from dataclasses import dataclass
from typing import Any, Dict, Iterable, MutableMapping, Optional


_CLEANUP_HOOKS = ("cleanup_after_jobs", "_cancel_after_jobs", "cleanup")


def widget_is_alive(widget: Any) -> bool:
    """Return whether a Tk/CTk object still owns a live Tcl command."""
    if widget is None:
        return False
    try:
        exists = getattr(widget, "winfo_exists", None)
        return bool(exists()) if callable(exists) else True
    except Exception:
        return False


@dataclass
class _OwnedWidgetBinding:
    owner_key: str
    owner: Any
    attribute: Optional[str]
    mapping: Optional[MutableMapping[Any, Any]]
    mapping_key: Any
    widget: Any

    def release(self) -> None:
        """Clear only the reference that still points at this exact widget."""
        if self.attribute:
            try:
                if getattr(self.owner, self.attribute, None) is self.widget:
                    setattr(self.owner, self.attribute, None)
            except Exception:
                pass
        if self.mapping is not None:
            try:
                if self.mapping.get(self.mapping_key) is self.widget:
                    self.mapping.pop(self.mapping_key, None)
            except Exception:
                pass


class WidgetOwnershipRegistry:
    """Single ownership contract for cached widgets in dynamic tab trees.

    Dashboard code may cache a child widget for cross-tab actions.  A tab can
    later be rebuilt in place or removed entirely, so those references must be
    invalidated at the same lifecycle boundary as the visual tree.  Identity
    checks prevent a late cleanup of an old tree from clearing its replacement.
    """

    def __init__(self) -> None:
        self._bindings: Dict[str, list[_OwnedWidgetBinding]] = {}
        self._lock = threading.RLock()

    def register_attribute(
        self,
        owner_key: str,
        owner: Any,
        attribute: str,
        widget: Any,
    ) -> Any:
        setattr(owner, attribute, widget)
        binding = _OwnedWidgetBinding(str(owner_key), owner, attribute, None, None, widget)
        with self._lock:
            self._replace_binding(binding)
        return widget

    def register_mapping(
        self,
        owner_key: str,
        mapping: MutableMapping[Any, Any],
        mapping_key: Any,
        widget: Any,
    ) -> Any:
        mapping[mapping_key] = widget
        binding = _OwnedWidgetBinding(str(owner_key), None, None, mapping, mapping_key, widget)
        with self._lock:
            self._replace_binding(binding)
        return widget

    def _replace_binding(self, binding: _OwnedWidgetBinding) -> None:
        entries = self._bindings.setdefault(binding.owner_key, [])
        retained: list[_OwnedWidgetBinding] = []
        for previous in entries:
            same_slot = (
                previous.owner is binding.owner
                and previous.attribute == binding.attribute
                and previous.mapping is binding.mapping
                and previous.mapping_key == binding.mapping_key
            )
            if not same_slot:
                retained.append(previous)
        retained.append(binding)
        self._bindings[binding.owner_key] = retained

    def invalidate(self, owner_key: str) -> int:
        with self._lock:
            entries = self._bindings.pop(str(owner_key), [])
        for binding in entries:
            binding.release()
        return len(entries)

    def resolve_attribute(self, owner: Any, attribute: str) -> Any:
        widget = getattr(owner, attribute, None)
        if widget_is_alive(widget):
            return widget
        try:
            if getattr(owner, attribute, None) is widget:
                setattr(owner, attribute, None)
        except Exception:
            pass
        return None

    def clear(self) -> int:
        with self._lock:
            keys = list(self._bindings)
        return sum(self.invalidate(key) for key in keys)

    def binding_count(self) -> int:
        with self._lock:
            return sum(len(entries) for entries in self._bindings.values())


def cleanup_widget_tree(root: Any, *, include_root: bool = True) -> None:
    """Run cleanup hooks and release native menus once, children first.

    ``CTkComboBox`` and ``CTkOptionMenu`` own a ``tk.Menu`` through the
    private ``_dropdown_menu`` attribute.  CustomTkinter 5.2.x does not
    explicitly destroy that object from the parent widget's ``destroy``
    method.  On Windows, repeated dynamic-tab rebuilds can therefore exhaust
    the per-process USER menu allocation even though the visible widget tree
    has disappeared.
    """
    cleaned: set[int] = set()
    released_native_resources: set[int] = set()

    def _release_native_resources(widget: Any) -> None:
        for attribute in ("_dropdown_menu", "_menu"):
            resource = getattr(widget, attribute, None)
            if resource is None or resource is widget:
                continue
            resource_id = id(resource)
            if resource_id in released_native_resources:
                continue
            released_native_resources.add(resource_id)
            destroy = getattr(resource, "destroy", None)
            if callable(destroy):
                try:
                    destroy()
                except Exception:
                    pass
            try:
                setattr(widget, attribute, None)
            except Exception:
                pass

    def _cleanup(widget: Any) -> None:
        try:
            children = list(widget.winfo_children())
        except Exception:
            children = []
        for child in children:
            _cleanup(child)

        _release_native_resources(widget)

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


def reorder_ctk_tabs(tabview: Any, ordered_names: Iterable[str]) -> bool:
    """Apply one canonical CTkTabview header order without rebuilding frames.

    CustomTkinter 5.2.x's public ``move`` changes the segmented button but can
    leave ``CTkTabview._name_list`` stale.  Updating both pieces together keeps
    the frame identities/content intact and avoids another teardown/allocation
    cycle.  Unknown names are ignored and remaining tabs keep their order.
    """
    tabs = getattr(tabview, "_tab_dict", {}) or {}
    current_names = list(getattr(tabview, "_name_list", []) or list(tabs.keys()))
    wanted = [name for name in ordered_names if name in tabs]
    wanted.extend(name for name in current_names if name in tabs and name not in wanted)
    if wanted == current_names:
        return False

    selected = None
    try:
        selected = tabview.get()
    except Exception:
        selected = getattr(tabview, "_current_name", None)

    tabview._name_list = wanted
    segmented = getattr(tabview, "_segmented_button", None)
    if segmented is not None and hasattr(segmented, "configure"):
        segmented.configure(values=wanted)
    if selected in tabs:
        try:
            tabview.set(selected)
        except Exception:
            pass
    elif wanted:
        try:
            tabview.set(wanted[0])
        except Exception:
            pass
    return True


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
