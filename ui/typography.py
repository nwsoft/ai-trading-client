#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""운영체제별 NoahAI 전역 글꼴 계약."""

from __future__ import annotations

import platform
from typing import Iterable, Optional


WINDOWS_KOREAN_FONT = "Malgun Gothic"
WINDOWS_FALLBACK_FONT = "Segoe UI"
MACOS_KOREAN_FONT = "Apple SD Gothic Neo"
LINUX_KOREAN_FONT = "Noto Sans CJK KR"


def platform_font_candidates(system_name: Optional[str] = None) -> tuple[str, ...]:
    system = str(system_name or platform.system()).strip().lower()
    if system == "windows":
        return (WINDOWS_KOREAN_FONT, WINDOWS_FALLBACK_FONT, "Arial")
    if system == "darwin":
        return (MACOS_KOREAN_FONT, "Helvetica Neue", "Arial")
    return (LINUX_KOREAN_FONT, "Noto Sans KR", "DejaVu Sans")


def resolve_platform_font(
    available_families: Optional[Iterable[str]] = None,
    *,
    system_name: Optional[str] = None,
) -> str:
    candidates = platform_font_candidates(system_name)
    if available_families is None:
        return candidates[0]
    normalized = {str(item).strip().lower(): str(item).strip() for item in available_families}
    for candidate in candidates:
        actual = normalized.get(candidate.lower())
        if actual:
            return actual
    return candidates[-1]


def configure_platform_typography(root=None) -> str:
    """CustomTkinter와 Tk named font를 같은 시스템 글꼴로 맞춘다."""
    import customtkinter as ctk

    families = None
    if root is not None:
        try:
            from tkinter import font as tkfont

            families = tkfont.families(root)
        except Exception:
            families = None
    family = resolve_platform_font(families)

    # CTkFont에서 family를 생략한 모든 대시보드 위젯에 적용된다.
    try:
        ctk.ThemeManager.theme.setdefault("CTkFont", {})["family"] = family
    except Exception:
        pass

    if root is not None:
        try:
            from tkinter import font as tkfont

            for name in (
                "TkDefaultFont",
                "TkTextFont",
                "TkMenuFont",
                "TkHeadingFont",
                "TkCaptionFont",
                "TkSmallCaptionFont",
                "TkIconFont",
                "TkTooltipFont",
            ):
                try:
                    tkfont.nametofont(name, root=root).configure(family=family)
                except Exception:
                    continue
            try:
                root.option_add("*Font", f"{{{family}}} 10")
            except Exception:
                pass
        except Exception:
            pass
    return family

