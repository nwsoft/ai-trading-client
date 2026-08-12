"""Bound Windows native-menu usage for CustomTkinter dropdown widgets.

CustomTkinter 5.2.x creates one persistent ``tk.Menu`` for every CTkComboBox
and CTkOptionMenu.  The dashboard owns many dynamic tab trees and the settings
window alone contains dozens of selectors.  A missed teardown in any old tree
can therefore accumulate native HMENU/USER objects until Tk raises::

    No more menus can be allocated.

On Windows we replace only CustomTkinter's private dropdown factory with a
lazy adapter.  The visible CTk widgets are unchanged; a real ``tk.Menu`` exists
only while one dropdown is open and is destroyed as soon as it closes.  This
makes menu usage bounded independently of tab rebuild frequency.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from typing import Any, Callable, Dict, Iterable, Optional


class LazyWindowsDropdownMenu:
    """Small DropdownMenu-compatible adapter with no persistent native menu."""

    _active_owner: Optional["LazyWindowsDropdownMenu"] = None

    def __init__(
        self,
        *args: Any,
        master: Any = None,
        min_character_width: int = 18,
        fg_color: Any = None,
        hover_color: Any = None,
        text_color: Any = None,
        font: Any = None,
        command: Optional[Callable[[str], Any]] = None,
        values: Optional[Iterable[str]] = None,
        **kwargs: Any,
    ) -> None:
        if master is None and args:
            master = args[0]
        self.master = master
        self._min_character_width = int(min_character_width or 18)
        self._fg_color = fg_color
        self._hover_color = hover_color
        self._text_color = text_color
        self._font = font
        self._command = command
        self._values = list(values or [])
        self._native_menu: Optional[tk.Menu] = None
        self._destroyed = False

    @staticmethod
    def _appearance_value(value: Any) -> Any:
        if isinstance(value, (tuple, list)) and value:
            try:
                import customtkinter as ctk

                return value[1] if str(ctk.get_appearance_mode()).lower() == "dark" and len(value) > 1 else value[0]
            except Exception:
                return value[-1]
        return value

    def _destroy_native(self, expected: Optional[tk.Menu] = None) -> None:
        menu = self._native_menu
        if menu is None or (expected is not None and menu is not expected):
            return
        self._native_menu = None
        if type(self)._active_owner is self:
            type(self)._active_owner = None
        try:
            menu.unpost()
        except Exception:
            pass
        try:
            menu.destroy()
        except Exception:
            pass

    def _destroy_after_idle(self, menu: tk.Menu) -> None:
        try:
            owner = self.master
            if owner is not None and hasattr(owner, "after_idle"):
                owner.after_idle(lambda current=menu: self._destroy_native(current))
                return
        except Exception:
            pass
        self._destroy_native(menu)

    def _select(self, value: str, menu: tk.Menu) -> None:
        # Tk may still be executing the menu command, so release it on idle.
        self._destroy_after_idle(menu)
        callback = self._command
        if callback is not None:
            callback(value)

    def _menu_options(self) -> Dict[str, Any]:
        options: Dict[str, Any] = {"tearoff": False, "relief": "flat", "borderwidth": 4}
        fg = self._appearance_value(self._fg_color)
        hover = self._appearance_value(self._hover_color)
        text = self._appearance_value(self._text_color)
        if fg not in (None, "transparent"):
            options["bg"] = fg
        if hover not in (None, "transparent"):
            options["activebackground"] = hover
        if text not in (None, "transparent"):
            options["fg"] = text
            options["activeforeground"] = text
        if self._font is not None:
            options["font"] = self._font
        if sys.platform.startswith("win"):
            options["cursor"] = "hand2"
            options["activeborderwidth"] = 4
        return options

    def open(self, x: int | float, y: int | float) -> None:
        if self._destroyed:
            return
        active_owner = type(self)._active_owner
        if active_owner is not None and active_owner is not self:
            active_owner._destroy_native()
        self._destroy_native()
        options = self._menu_options()
        try:
            menu = tk.Menu(self.master, **options)
        except (tk.TclError, TypeError):
            # A theme/font option must never prevent access to the selector.
            menu = tk.Menu(self.master, tearoff=False)
        self._native_menu = menu
        type(self)._active_owner = self
        for value in self._values:
            label = str(value).ljust(self._min_character_width)
            menu.add_command(
                label=label,
                command=lambda selected=str(value), current=menu: self._select(selected, current),
            )
        try:
            menu.bind(
                "<Unmap>",
                lambda _event, current=menu: self._destroy_after_idle(current),
                add="+",
            )
        except Exception:
            pass
        try:
            menu.post(int(x), int(y) + 3)
        except Exception:
            self._destroy_native(menu)
            raise

    def configure(self, **kwargs: Any) -> None:
        mapping = {
            "fg_color": "_fg_color",
            "hover_color": "_hover_color",
            "text_color": "_text_color",
            "font": "_font",
            "command": "_command",
            "values": "_values",
            "min_character_width": "_min_character_width",
        }
        for key, value in kwargs.items():
            attribute = mapping.get(key)
            if attribute is None:
                continue
            if key == "values":
                value = list(value or [])
            setattr(self, attribute, value)

    config = configure

    def cget(self, attribute_name: str) -> Any:
        mapping = {
            "fg_color": self._fg_color,
            "hover_color": self._hover_color,
            "text_color": self._text_color,
            "font": self._font,
            "command": self._command,
            "values": list(self._values),
            "min_character_width": self._min_character_width,
        }
        return mapping.get(attribute_name)

    def destroy(self) -> None:
        self._destroyed = True
        self._destroy_native()


_INSTALLED = False


def install_windows_menu_guard(*, force: bool = False) -> bool:
    """Install the lazy factory before CTk dropdown instances are created."""
    global _INSTALLED
    if _INSTALLED:
        return True
    if os.name != "nt" and not force:
        return False
    try:
        import customtkinter.windows.widgets.ctk_combobox as combo_module
        import customtkinter.windows.widgets.ctk_optionmenu as option_module

        combo_module.DropdownMenu = LazyWindowsDropdownMenu
        option_module.DropdownMenu = LazyWindowsDropdownMenu
        _INSTALLED = True
        return True
    except Exception:
        return False


def windows_menu_guard_installed() -> bool:
    return bool(_INSTALLED)
