# -*- coding: utf-8 -*-
"""
단일 고정 스킨용 색상 상수와 헬퍼
- 테마/팔레트 시스템을 대체하는 프로젝트 단일 색상 소스
"""
from typing import Dict

FIXED_COLORS: Dict[str, str] = {
    # 베이스
    'background': '#050a13',
    'surface': '#1f2632',
    'surface_alt': '#202c42',
    'panel': '#252d38',
    'panel_alt': '#27354d',
    'border': '#374151',
    # 텍스트
    'text_primary': '#f9fafb',
    'text_secondary': '#9ca3af',
    # 버튼
    'button_primary': '#1f6feb',
    'button_primary_hover': '#1a5fd1',
    'button_secondary': '#3a5a7f',
    'button_secondary_hover': '#4a6a8f',
    # 상태/강조
    'success': '#22c55e',
    'danger': '#ef4444',
    'warning': '#f59e0b',
    'accent': '#8b5cf6',
    'info': '#3b82f6',
}

# 버튼/탭 등에서 재사용할 규격값
BUTTON_CORNER_RADIUS = 10
BUTTON_HEIGHT_SMALL = 32
BUTTON_HEIGHT_MEDIUM = 36

__all__ = [
    'FIXED_COLORS',
    'BUTTON_CORNER_RADIUS',
    'BUTTON_HEIGHT_SMALL',
    'BUTTON_HEIGHT_MEDIUM',
]
