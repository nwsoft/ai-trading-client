#!/usr/bin/env python3
"""macOS와 Windows에서 동일하게 보이는 NoahAI 공용 시각 자산."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import customtkinter as ctk

try:
    from PIL import Image, ImageDraw
except Exception:
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore


_ICON_CACHE: Dict[Tuple[str, int, int, str], ctk.CTkImage] = {}


def _line_width(size: Tuple[int, int]) -> int:
    return max(2, round(min(size) * 0.10))


def get_ui_icon(
    name: str,
    size: Tuple[int, int] = (18, 18),
    color: str = "#ffffff",
) -> Optional[ctk.CTkImage]:
    """PIL로 그린 단색 아이콘을 CTkImage로 반환한다.

    운영체제의 컬러 이모지 폰트를 사용하지 않으므로 macOS/Windows에서
    모양·색상·크기가 동일하다.
    """
    key = (str(name), int(size[0]), int(size[1]), str(color))
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    if Image is None or ImageDraw is None:
        return None

    w, h = size
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    stroke = _line_width(size)
    pad = max(2, round(min(size) * 0.15))
    left, top, right, bottom = pad, pad, w - pad, h - pad
    mid_x, mid_y = w / 2, h / 2
    radius = max(2, round(min(size) * 0.12))

    if name == "blockchain":
        box = max(4, round(min(size) * 0.28))
        points = [(left, mid_y - box / 2), (right - box, top), (right - box, bottom - box)]
        centers = []
        for x, y in points:
            draw.rounded_rectangle([x, y, x + box, y + box], radius=1, outline=color, width=stroke)
            centers.append((x + box / 2, y + box / 2))
        draw.line([centers[0], centers[1]], fill=color, width=stroke)
        draw.line([centers[0], centers[2]], fill=color, width=stroke)
        draw.line([centers[1], centers[2]], fill=color, width=stroke)
    elif name in {"stock", "chart"}:
        draw.line([(left, top), (left, bottom), (right, bottom)], fill=color, width=stroke)
        draw.line(
            [(left + 2, bottom - 3), (mid_x - 2, mid_y), (mid_x + 2, mid_y + 2), (right, top + 2)],
            fill=color,
            width=stroke,
            joint="curve",
        )
    elif name in {"portfolio", "assets"}:
        draw.ellipse([left, top, right, bottom], outline=color, width=stroke)
        draw.line([(mid_x, top), (mid_x, mid_y), (right, mid_y)], fill=color, width=stroke)
    elif name in {"wallet", "finance"}:
        draw.rounded_rectangle([left, top + 2, right, bottom], radius=radius, outline=color, width=stroke)
        draw.line([(left + 2, top + 2), (right - 3, top + 2)], fill=color, width=stroke)
        draw.ellipse(
            [right - stroke * 2.5, mid_y - stroke, right - stroke * 0.7, mid_y + stroke],
            fill=color,
        )
    elif name in {"analyst", "spark"}:
        draw.line([(left, bottom - 2), (mid_x - 2, mid_y + 1), (right - 2, top + 3)], fill=color, width=stroke)
        draw.line([(right - 2, top), (right - 2, top + stroke * 3)], fill=color, width=stroke)
        draw.line([(right - stroke * 1.5, top + stroke), (right + stroke * 0.5, top + stroke)], fill=color, width=stroke)
    elif name in {"manual", "book"}:
        draw.rounded_rectangle([left, top, mid_x - 1, bottom], radius=radius, outline=color, width=stroke)
        draw.rounded_rectangle([mid_x + 1, top, right, bottom], radius=radius, outline=color, width=stroke)
        draw.line([(mid_x, top + 1), (mid_x, bottom)], fill=color, width=stroke)
    elif name in {"settings", "sliders"}:
        ys = [top + 2, mid_y, bottom - 2]
        knobs = [mid_x + 3, mid_x - 4, mid_x + 1]
        for y, knob in zip(ys, knobs):
            draw.line([(left, y), (right, y)], fill=color, width=stroke)
            draw.ellipse([knob - stroke, y - stroke, knob + stroke, y + stroke], fill=color)
    elif name == "power":
        draw.arc([left, top + 1, right, bottom + 1], start=315, end=225, fill=color, width=stroke)
        draw.line([(mid_x, top), (mid_x, mid_y + 1)], fill=color, width=stroke)
    elif name == "update":
        draw.arc([left, top, right, bottom], start=35, end=325, fill=color, width=stroke)
        draw.polygon(
            [(right - 1, top + 1), (right - stroke * 3, top + 1), (right - 1, top + stroke * 3)],
            fill=color,
        )
    elif name == "history":
        draw.ellipse([left, top, right, bottom], outline=color, width=stroke)
        draw.line([(mid_x, mid_y), (mid_x, top + 3)], fill=color, width=stroke)
        draw.line([(mid_x, mid_y), (right - 3, mid_y + 2)], fill=color, width=stroke)
    elif name == "save":
        draw.rounded_rectangle([left, top, right, bottom], radius=radius, outline=color, width=stroke)
        draw.rectangle([left + 3, top, right - 3, mid_y], outline=color, width=stroke)
        draw.rectangle([left + 3, mid_y + 2, right - 3, bottom], outline=color, width=stroke)
    elif name == "close":
        draw.line([(left + 1, top + 1), (right - 1, bottom - 1)], fill=color, width=stroke)
        draw.line([(right - 1, top + 1), (left + 1, bottom - 1)], fill=color, width=stroke)
    else:
        draw.rounded_rectangle([left, top, right, bottom], radius=radius, outline=color, width=stroke)

    icon = ctk.CTkImage(light_image=image, dark_image=image, size=size)
    _ICON_CACHE[key] = icon
    return icon


def style_tabview(
    tabview: ctk.CTkTabview,
    *,
    accent: str = "#2563eb",
    bar_color: str = "#111c2f",
    inactive: str = "#263a57",
    text_color: str = "#dbe7f5",
    font_size: int = 11,
    height: int = 34,
) -> None:
    """탭 바를 공통 고대비 스타일로 맞춘다."""
    try:
        tabview.configure(
            fg_color="#0b1120",
            border_width=1,
            border_color="#334155",
            segmented_button_fg_color=bar_color,
            segmented_button_selected_color=accent,
            segmented_button_unselected_color=inactive,
            segmented_button_selected_hover_color="#1d4ed8",
            segmented_button_unselected_hover_color="#334e72",
            segmented_button_text_color=text_color,
            segmented_button_corner_radius=9,
        )
        try:
            tabview.configure(segmented_button_selected_text_color="#ffffff")
        except Exception:
            pass
    except Exception:
        pass
    try:
        segmented = getattr(tabview, "_segmented_button", None)
        if segmented is not None:
            segmented.configure(
                fg_color=bar_color,
                selected_color=accent,
                unselected_color=inactive,
                selected_hover_color="#1d4ed8",
                unselected_hover_color="#334e72",
                text_color=text_color,
                font=ctk.CTkFont(family="Segoe UI", size=font_size, weight="bold"),
                height=height,
                corner_radius=9,
            )
            try:
                segmented.configure(selected_text_color="#ffffff")
            except Exception:
                pass
            try:
                segmented.configure(border_width=1, border_color="#48627f")
            except Exception:
                # 일부 구형 CustomTkinter는 segmented-button 테두리를
                # 지원하지 않는다. 공통 색상·글꼴·높이는 그대로 유지한다.
                pass
    except Exception:
        pass
