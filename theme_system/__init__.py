#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NoahAI 테마 시스템
CustomTkinter 기반 현대적 UI 테마 시스템
"""

from .theme_manager import ThemeManager
from .color_palettes import ColorPalettes
from .windows_font_system import WindowsFontSystem
from .ui_components import (
    ThemedButton, ThemedLabel, ThemedEntry, ThemedFrame,
    ThemedCheckbox, ThemedTabview, ThemedScrollableFrame,
    ThemedProgressBar, ThemedSwitch, ThemedComboBox, ThemedTextbox,
    create_themed_button, create_themed_label, create_themed_entry,
    create_themed_frame, create_themed_checkbox, create_themed_tabview,
    create_themed_scrollable_frame
)

__version__ = "1.0.0"
__author__ = "NoahAI Team"

# 기본 테마 시스템 인스턴스
_default_theme_manager = None

def get_default_theme_manager():
    """기본 테마 관리자 인스턴스 반환"""
    global _default_theme_manager
    if _default_theme_manager is None:
        _default_theme_manager = ThemeManager()
    return _default_theme_manager

def create_theme_manager():
    """새로운 테마 관리자 인스턴스 생성"""
    return ThemeManager()

# 편의 함수들
def get_current_theme():
    """현재 테마 이름 반환"""
    return get_default_theme_manager().get_current_theme()

def get_current_colors():
    """현재 테마 색상 반환"""
    return get_default_theme_manager().get_current_colors()

def get_current_fonts():
    """현재 테마 폰트 반환"""
    return get_default_theme_manager().get_current_fonts()

def apply_theme(theme_name):
    """테마 적용"""
    return get_default_theme_manager().apply_theme(theme_name)

def get_available_themes():
    """사용 가능한 테마 목록 반환"""
    return get_default_theme_manager().get_available_themes()

# 내보내기
__all__ = [
    # 클래스
    "ThemeManager",
    "ColorPalettes", 
    "WindowsFontSystem",
    "ThemedButton",
    "ThemedLabel",
    "ThemedEntry",
    "ThemedFrame",
    "ThemedCheckbox",
    "ThemedTabview",
    "ThemedScrollableFrame",
    "ThemedProgressBar",
    "ThemedSwitch",
    "ThemedComboBox",
    "ThemedTextbox",
    
    # 헬퍼 함수
    "create_themed_button",
    "create_themed_label", 
    "create_themed_entry",
    "create_themed_frame",
    "create_themed_checkbox",
    "create_themed_tabview",
    "create_themed_scrollable_frame",
    
    # 편의 함수
    "get_default_theme_manager",
    "create_theme_manager",
    "get_current_theme",
    "get_current_colors",
    "get_current_fonts",
    "apply_theme",
    "get_available_themes"
]
