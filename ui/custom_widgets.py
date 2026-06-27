#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CustomTkinter의 corner_radius 무시 문제를 해결하는 커스텀 위젯
CTk의 내부 테마 시스템을 우회하여 corner_radius를 강제 적용
"""

import customtkinter as ctk
from typing import Optional, Callable, Any


class RoundedButton(ctk.CTkButton):
    """corner_radius가 강제로 적용되는 버튼"""
    
    def __init__(self, master, corner_radius: int = 12, **kwargs):
        # corner_radius를 명시적으로 설정
        kwargs['corner_radius'] = corner_radius
        super().__init__(master, **kwargs)
        
        # 생성 후 다시 한번 corner_radius 강제 설정
        self.after(1, lambda: self._force_corner_radius(corner_radius))
    
    def _force_corner_radius(self, radius: int):
        """corner_radius를 강제로 적용"""
        try:
            self.configure(corner_radius=radius)
            # 내부 canvas가 있다면 직접 수정
            if hasattr(self, '_canvas') and self._canvas:
                self._canvas.itemconfig('inner_parts', outline='')
                self._draw()  # 강제 재렌더링
        except Exception as e:
            print(f"corner_radius 강제 적용 실패: {e}")


class RoundedFrame(ctk.CTkFrame):
    """corner_radius가 강제로 적용되는 프레임"""
    
    def __init__(self, master, corner_radius: int = 12, **kwargs):
        # corner_radius를 명시적으로 설정
        kwargs['corner_radius'] = corner_radius
        super().__init__(master, **kwargs)
        
        # 생성 후 다시 한번 corner_radius 강제 설정
        self.after(1, lambda: self._force_corner_radius(corner_radius))
    
    def _force_corner_radius(self, radius: int):
        """corner_radius를 강제로 적용"""
        try:
            self.configure(corner_radius=radius)
            if hasattr(self, '_canvas') and self._canvas:
                self._draw()  # 강제 재렌더링
        except Exception:
            pass


class RoundedEntry(ctk.CTkEntry):
    """corner_radius가 강제로 적용되는 입력 필드"""
    
    def __init__(self, master, corner_radius: int = 10, **kwargs):
        kwargs['corner_radius'] = corner_radius
        super().__init__(master, **kwargs)
        self.after(1, lambda: self._force_corner_radius(corner_radius))
    
    def _force_corner_radius(self, radius: int):
        try:
            self.configure(corner_radius=radius)
            if hasattr(self, '_canvas') and self._canvas:
                self._draw()
        except Exception:
            pass


# 편의 함수: 기존 CTk 위젯을 Rounded 버전으로 대체
def create_rounded_button(master, text: str = "", command: Optional[Callable] = None,
                         corner_radius: int = 12, **kwargs) -> RoundedButton:
    """둥근 버튼 생성 헬퍼"""
    return RoundedButton(
        master,
        text=text,
        command=command,
        corner_radius=corner_radius,
        **kwargs
    )


def create_rounded_frame(master, corner_radius: int = 12, **kwargs) -> RoundedFrame:
    """둥근 프레임 생성 헬퍼"""
    return RoundedFrame(
        master,
        corner_radius=corner_radius,
        **kwargs
    )
