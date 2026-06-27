#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows 기본 폰트 시스템
CustomTkinter와 완벽 호환되는 Windows 기본 폰트 사용
"""

import customtkinter as ctk
import platform

class WindowsFontSystem:
    """Windows 기본 폰트 시스템"""
    
    def __init__(self):
        self.system = platform.system()
        self.fonts = self._get_windows_fonts()
        
    def _get_windows_fonts(self):
        """Windows 기본 폰트 설정"""
        if self.system == "Windows":
            return {
                "primary": "Segoe UI",           # Windows 10/11 기본 UI 폰트
                "secondary": "Arial",             # 크로스 플랫폼 호환
                "monospace": "Consolas",          # 코드용 모노스페이스
                "fallback": "Tahoma"              # 폴백 폰트
            }
        else:
            # 다른 OS용 폴백
            return {
                "primary": "Arial",
                "secondary": "Helvetica", 
                "monospace": "Courier New",
                "fallback": "Arial"
            }
    
    def get_font(self, font_type="primary", size=14, weight="normal"):
        """폰트 객체 생성"""
        font_family = self.fonts.get(font_type, self.fonts["primary"])
        
        try:
            return ctk.CTkFont(
                family=font_family,
                size=size,
                weight=weight
            )
        except Exception as e:
            print(f"폰트 생성 오류: {e}")
            # Tkinter 루트 윈도우가 없을 때는 None 반환
            return None
    
    def get_font_config(self):
        """완전한 폰트 설정 반환 (지연 로딩)"""
        # 폰트 설정을 딕셔너리로 반환 (실제 폰트 객체는 필요할 때 생성)
        return {
            # 제목 계층
            "title": ("primary", 28, "bold"),           # 메인 제목
            "heading": ("primary", 20, "bold"),         # 섹션 제목
            "subheading": ("primary", 16, "bold"),      # 서브 제목
            
            # 본문 계층
            "body_large": ("primary", 16, "normal"),    # 큰 본문
            "body": ("primary", 14, "normal"),          # 기본 본문
            "body_small": ("primary", 12, "normal"),    # 작은 본문
            
            # 특수 용도
            "caption": ("primary", 11, "normal"),       # 캡션
            "small": ("primary", 10, "normal"),         # 작은 텍스트
            "tiny": ("primary", 9, "normal"),           # 아주 작은 텍스트
            
            # 모노스페이스
            "code": ("monospace", 12, "normal"),        # 코드
            "code_small": ("monospace", 10, "normal"),  # 작은 코드
            
            # 버튼
            "button": ("primary", 14, "normal"),        # 일반 버튼
            "button_bold": ("primary", 14, "bold"),     # 굵은 버튼
            "button_large": ("primary", 16, "bold"),    # 큰 버튼
            
            # 입력 필드
            "input": ("primary", 14, "normal"),         # 입력 필드
            "input_large": ("primary", 16, "normal"),   # 큰 입력 필드
            
            # 테이블
            "table_header": ("primary", 12, "bold"),    # 테이블 헤더
            "table_cell": ("primary", 11, "normal"),    # 테이블 셀
        }
    
    def create_font(self, font_config_name: str):
        """폰트 설정 이름으로 실제 폰트 객체 생성"""
        font_config = self.get_font_config()
        if font_config_name in font_config:
            font_type, size, weight = font_config[font_config_name]
            return self.get_font(font_type, size, weight)
        return None
    
    def get_font_hierarchy(self):
        """폰트 계층 구조 반환"""
        return {
            "제목": {
                "title": "메인 제목 (28px, Bold)",
                "heading": "섹션 제목 (20px, Bold)", 
                "subheading": "서브 제목 (16px, Bold)"
            },
            "본문": {
                "body_large": "큰 본문 (16px, Normal)",
                "body": "기본 본문 (14px, Normal)",
                "body_small": "작은 본문 (12px, Normal)"
            },
            "특수": {
                "caption": "캡션 (11px, Normal)",
                "small": "작은 텍스트 (10px, Normal)",
                "tiny": "아주 작은 텍스트 (9px, Normal)"
            },
            "코드": {
                "code": "코드 (12px, Monospace)",
                "code_small": "작은 코드 (10px, Monospace)"
            },
            "인터페이스": {
                "button": "버튼 (14px, Normal)",
                "button_bold": "굵은 버튼 (14px, Bold)",
                "input": "입력 필드 (14px, Normal)"
            }
        }
    
    def apply_font_to_widget(self, widget, font_type="body"):
        """위젯에 폰트 적용"""
        try:
            font_config = self.get_font_config()
            if font_type in font_config:
                widget.configure(font=font_config[font_type])
                return True
        except Exception as e:
            print(f"위젯 폰트 적용 오류: {e}")
        return False
    
    def apply_font_to_all_children(self, parent_widget, font_type="body"):
        """모든 자식 위젯에 폰트 적용"""
        try:
            font_config = self.get_font_config()
            if font_type in font_config:
                font = font_config[font_type]
                
                # 현재 위젯에 적용
                if hasattr(parent_widget, 'configure'):
                    try:
                        parent_widget.configure(font=font)
                    except:
                        pass  # 폰트를 지원하지 않는 위젯 무시
                
                # 모든 자식 위젯에 재귀적으로 적용
                for child in parent_widget.winfo_children():
                    self.apply_font_to_all_children(child, font_type)
                    
        except Exception as e:
            print(f"자식 위젯 폰트 적용 오류: {e}")
    
    def get_available_fonts(self):
        """사용 가능한 폰트 목록 반환"""
        return list(self.fonts.values())
    
    def test_fonts(self):
        """폰트 테스트 창"""
        test_window = ctk.CTk()
        test_window.title("Windows 폰트 시스템 테스트")
        test_window.geometry("700x600")
        
        # 테스트 프레임
        test_frame = ctk.CTkScrollableFrame(test_window)
        test_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 폰트 설정 가져오기
        fonts = self.get_font_config()
        
        # 제목
        title_label = ctk.CTkLabel(
            test_frame,
            text="Windows 폰트 시스템 테스트",
            font=fonts["title"]
        )
        title_label.pack(pady=(0, 20))
        
        # 폰트 계층 구조 테스트
        hierarchy = self.get_font_hierarchy()
        
        for category, font_types in hierarchy.items():
            # 카테고리 제목
            category_label = ctk.CTkLabel(
                test_frame,
                text=f"📝 {category}",
                font=fonts["heading"]
            )
            category_label.pack(pady=(20, 10), anchor="w")
            
            # 각 폰트 타입 테스트
            for font_type, description in font_types.items():
                if font_type in fonts:
                    test_label = ctk.CTkLabel(
                        test_frame,
                        text=f"{description}: 안녕하세요! Hello World! 123456",
                        font=fonts[font_type]
                    )
                    test_label.pack(pady=2, anchor="w")
        
        # 사용 가능한 폰트 표시
        available_fonts_label = ctk.CTkLabel(
            test_frame,
            text=f"사용 가능한 폰트: {', '.join(self.get_available_fonts())}",
            font=fonts["caption"]
        )
        available_fonts_label.pack(pady=(30, 0), anchor="w")
        
        # 시스템 정보
        system_info_label = ctk.CTkLabel(
            test_frame,
            text=f"운영체제: {self.system}",
            font=fonts["small"]
        )
        system_info_label.pack(pady=(10, 0), anchor="w")
        
        test_window.mainloop()
    
    def get_font_recommendations(self):
        """폰트 사용 권장사항"""
        return {
            "금융 앱": {
                "제목": "title (28px, Bold)",
                "섹션": "heading (20px, Bold)",
                "본문": "body (14px, Normal)",
                "데이터": "code (12px, Monospace)",
                "버튼": "button_bold (14px, Bold)"
            },
            "일반 앱": {
                "제목": "title (28px, Bold)",
                "섹션": "subheading (16px, Bold)",
                "본문": "body (14px, Normal)",
                "설명": "body_small (12px, Normal)",
                "버튼": "button (14px, Normal)"
            },
            "코딩 앱": {
                "제목": "heading (20px, Bold)",
                "섹션": "subheading (16px, Bold)",
                "코드": "code (12px, Monospace)",
                "주석": "code_small (10px, Monospace)",
                "버튼": "button (14px, Normal)"
            }
        }

# 사용 예시
if __name__ == "__main__":
    font_system = WindowsFontSystem()
    font_system.test_fonts()
