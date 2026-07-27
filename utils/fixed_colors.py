# -*- coding: utf-8 -*-
"""
단일 고정 스킨용 색상 상수와 헬퍼
- 테마/팔레트 시스템을 대체하는 프로젝트 단일 색상 소스
"""
from typing import Dict

FIXED_COLORS: Dict[str, str] = {
    # 베이스
    'background': '#050a13',
    # 기능 탭 공통 캔버스/카드. AI 커스텀·거래 통계 화면과 동일한 계층을 사용한다.
    'content_bg': '#0b1120',
    'card': '#111827',
    'card_alt': '#172033',
    'input': '#0b1120',
    'surface': '#1f2632',
    'surface_alt': '#202c42',
    'panel': '#252d38',
    'panel_alt': '#27354d',
    'border': '#374151',
    'border_soft': '#273449',
    'border_strong': '#334155',
    # 텍스트
    'text_primary': '#f9fafb',
    'text_secondary': '#9ca3af',
    'text_muted': '#91a4bd',
    # 버튼
    'button_primary': '#1f6feb',
    'button_primary_hover': '#1a5fd1',
    'button_secondary': '#3a5a7f',
    'button_secondary_hover': '#4a6a8f',
    # 기능 탭 내부 액션/탭
    'primary': '#2563eb',
    'primary_hover': '#1d4ed8',
    'secondary': '#263a57',
    'secondary_hover': '#334e72',
    'hover': '#334155',
    'text_on_primary': '#ffffff',
    'tabbar_bg': '#111c2f',
    'tab_inactive': '#263a57',
    'tab_text': '#dbe7f5',
    # 상태/강조
    'success': '#22c55e',
    'danger': '#ef4444',
    'warning': '#f59e0b',
    'accent': '#8b5cf6',
    'info': '#3b82f6',
}


def build_widget_palette(overrides: Dict[str, str] | None = None) -> Dict[str, str]:
    """기능 탭 위젯에서 사용할 공통 시각 계층을 반환한다.

    기존 전역 스킨 값은 유지하면서 위젯의 ``background/surface/border`` 별칭만
    AI 커스텀·거래 통계와 같은 캔버스/카드 체계로 정규화한다.
    """
    palette = dict(FIXED_COLORS)
    if overrides:
        palette.update(overrides)
    palette.update({
        'background': palette['content_bg'],
        'surface': palette['card'],
        'surface_alt': palette['card_alt'],
        'border': palette['border_soft'],
    })
    return palette

# 버튼/탭 등에서 재사용할 규격값
BUTTON_CORNER_RADIUS = 10
BUTTON_HEIGHT_SMALL = 32
BUTTON_HEIGHT_MEDIUM = 36

__all__ = [
    'FIXED_COLORS',
    'build_widget_palette',
    'BUTTON_CORNER_RADIUS',
    'BUTTON_HEIGHT_SMALL',
    'BUTTON_HEIGHT_MEDIUM',
]
