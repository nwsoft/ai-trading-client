#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
색상 팔레트 정의
다양한 테마의 색상 팔레트를 정의하고 관리
"""

from typing import Any, Dict, List, Tuple
import colorsys

class ColorPalettes:
    """색상 팔레트 관리 클래스"""
    
    # 기본 색상 팔레트
    PALETTES = {
        "modern_dark": {
            "name": "모던 다크",
            "description": "기본 다크 테마 - 선명한 대비와 블루 포인트",
            "category": "기본",
            "colors": {
                "primary": "#1f4ed8",
                "secondary": "#1b2f4c",
                "success": "#10b981",
                "danger": "#f25f5c",
                "warning": "#fbbf24",
                "info": "#3b9af6",
                "background": "#050a13",
                "surface": "#1f2632",
                "surface_alt": "#262e3c",
                "surface_muted": "#2e3848",
                "surface_hover": "#374254",
                "panel": "#252d38",
                "panel_alt": "#2d3644",
                "text_primary": "#f4f7fb",
                "text_secondary": "#9aa6c2",
                "border": "#3a4454",
                "hover": "#314059",
                "active": "#2b6ffe",
                "disabled": "#6f829f",
                "accent": "#8b5cf6",
                "button_primary": "#1f6feb",
                "button_primary_hover": "#1a5fd1",
                "button_secondary": "#3a5a7f",
                "button_secondary_hover": "#4a6a8f",
                "chip": "#2b3644"
            }
        },
        "modern_light": {
            "name": "모던 라이트",
            "description": "기본 라이트 테마 - 밝고 깔끔한 디자인",
            "category": "기본",
            "colors": {
                "primary": "#f8fafc",
                "secondary": "#e2e8f0",
                "success": "#059669",
                "danger": "#dc2626",
                "warning": "#d97706",
                "info": "#2563eb",
                "background": "#ffffff",
                "surface": "#f8fafc",
                "text_primary": "#1f2937",
                "text_secondary": "#6b7280",
                "border": "#e2e8f0",
                "hover": "#f1f5f9",
                "active": "#2563eb",
                "disabled": "#9ca3af",
                "accent": "#7c3aed"
            }
        },
        
        "trading_pro": {
            "name": "트레이딩 프로",
            "description": "전문 트레이딩용 테마 - 고급스럽고 전문적인 디자인",
            "category": "전문",
            "colors": {
                "primary": "#0f172a",
                "secondary": "#1e293b",
                "success": "#22c55e",
                "danger": "#ef4444",
                "warning": "#f59e0b",
                "info": "#3b82f6",
                "background": "#020617",
                "surface": "#0f172a",
                "text_primary": "#f1f5f9",
                "text_secondary": "#94a3b8",
                "border": "#1e293b",
                "hover": "#334155",
                "active": "#3b82f6",
                "disabled": "#64748b",
                "accent": "#8b5cf6"
            }
        },
        
        "crypto_night": {
            "name": "크립토 나이트",
            "description": "암호화폐 트레이딩 전용 테마 - 네온 컬러와 다크 배경",
            "category": "크립토",
            "colors": {
                "primary": "#1a1a2e",
                "secondary": "#16213e",
                "success": "#00d4aa",
                "danger": "#ff6b6b",
                "warning": "#ffd93d",
                "info": "#6c5ce7",
                "background": "#0f0f23",
                "surface": "#1a1a2e",
                "text_primary": "#ffffff",
                "text_secondary": "#a0a0a0",
                "border": "#16213e",
                "hover": "#2d2d44",
                "active": "#6c5ce7",
                "disabled": "#6b7280",
                "accent": "#ff6b6b"
            }
        },
        
        "ocean_blue": {
            "name": "오션 블루",
            "description": "바다를 연상시키는 블루 계열 테마",
            "category": "자연",
            "colors": {
                "primary": "#1e3a8a",
                "secondary": "#3b82f6",
                "success": "#10b981",
                "danger": "#ef4444",
                "warning": "#f59e0b",
                "info": "#06b6d4",
                "background": "#0f172a",
                "surface": "#1e3a8a",
                "text_primary": "#f0f9ff",
                "text_secondary": "#94a3b8",
                "border": "#3b82f6",
                "hover": "#2563eb",
                "active": "#06b6d4",
                "disabled": "#64748b",
                "accent": "#06b6d4"
            }
        },
        
        "forest_green": {
            "name": "포레스트 그린",
            "description": "자연을 연상시키는 그린 계열 테마",
            "category": "자연",
            "colors": {
                "primary": "#14532d",
                "secondary": "#22c55e",
                "success": "#16a34a",
                "danger": "#ef4444",
                "warning": "#f59e0b",
                "info": "#3b82f6",
                "background": "#0f1419",
                "surface": "#14532d",
                "text_primary": "#f0fdf4",
                "text_secondary": "#9ca3af",
                "border": "#22c55e",
                "hover": "#16a34a",
                "active": "#22c55e",
                "disabled": "#6b7280",
                "accent": "#22c55e"
            }
        },
        
        "sunset_orange": {
            "name": "선셋 오렌지",
            "description": "일몰을 연상시키는 오렌지 계열 테마",
            "category": "자연",
            "colors": {
                "primary": "#c2410c",
                "secondary": "#f97316",
                "success": "#10b981",
                "danger": "#ef4444",
                "warning": "#f59e0b",
                "info": "#3b82f6",
                "background": "#1c1917",
                "surface": "#c2410c",
                "text_primary": "#fff7ed",
                "text_secondary": "#a3a3a3",
                "border": "#f97316",
                "hover": "#ea580c",
                "active": "#f97316",
                "disabled": "#6b7280",
                "accent": "#f97316"
            }
        },
        
        "purple_dream": {
            "name": "퍼플 드림",
            "description": "꿈을 연상시키는 퍼플 계열 테마",
            "category": "창의",
            "colors": {
                "primary": "#581c87",
                "secondary": "#8b5cf6",
                "success": "#10b981",
                "danger": "#ef4444",
                "warning": "#f59e0b",
                "info": "#3b82f6",
                "background": "#1e1b4b",
                "surface": "#581c87",
                "text_primary": "#faf5ff",
                "text_secondary": "#a78bfa",
                "border": "#8b5cf6",
                "hover": "#7c3aed",
                "active": "#8b5cf6",
                "disabled": "#6b7280",
                "accent": "#8b5cf6"
            }
        }
    }
    
    @classmethod
    def get_palette(cls, palette_name: str) -> Dict[str, str]:
        """특정 팔레트의 색상 반환"""
        if palette_name in cls.PALETTES:
            return cls.PALETTES[palette_name]["colors"]
        else:
            return cls.PALETTES["modern_dark"]["colors"]
    
    @classmethod
    def get_all_palettes(cls) -> Dict[str, Dict[str, Any]]:
        """모든 팔레트 반환"""
        return cls.PALETTES
    
    @classmethod
    def get_palettes_by_category(cls, category: str) -> Dict[str, Dict[str, Any]]:
        """카테고리별 팔레트 반환"""
        return {name: data for name, data in cls.PALETTES.items() 
                if data.get("category") == category}
    
    @classmethod
    def get_categories(cls) -> List[str]:
        """사용 가능한 카테고리 목록 반환"""
        categories = set()
        for data in cls.PALETTES.values():
            if "category" in data:
                categories.add(data["category"])
        return sorted(list(categories))
    
    @classmethod
    def create_custom_palette(cls, name: str, description: str, category: str, 
                            base_colors: Dict[str, str]) -> Dict[str, Any]:
        """사용자 정의 팔레트 생성"""
        # 기본 색상 구조 생성
        custom_palette = {
            "name": name,
            "description": description,
            "category": category,
            "colors": {}
        }
        
        # 기본 색상 키들
        required_keys = [
            "primary", "secondary", "success", "danger", "warning", "info",
            "background", "surface", "text_primary", "text_secondary",
            "border", "hover", "active", "disabled", "accent"
        ]
        
        # 기본 색상 설정
        for key in required_keys:
            if key in base_colors:
                custom_palette["colors"][key] = base_colors[key]
            else:
                # 기본값 설정
                custom_palette["colors"][key] = cls.PALETTES["modern_dark"]["colors"][key]
        
        return custom_palette
    
    @classmethod
    def generate_color_variations(cls, base_color: str, count: int = 5) -> List[str]:
        """기본 색상에서 다양한 변형 생성"""
        try:
            # HEX를 RGB로 변환
            hex_color = base_color.lstrip('#')
            r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            
            # RGB를 HSV로 변환
            h, s, v = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)
            
            variations = []
            for i in range(count):
                # 밝기 조정 (0.2 ~ 1.0)
                new_v = 0.2 + (i / (count - 1)) * 0.8
                new_r, new_g, new_b = colorsys.hsv_to_rgb(h, s, new_v)
                
                # RGB를 HEX로 변환
                hex_variation = "#{:02x}{:02x}{:02x}".format(
                    int(new_r * 255), int(new_g * 255), int(new_b * 255)
                )
                variations.append(hex_variation)
            
            return variations
            
        except Exception as e:
            print(f"색상 변형 생성 오류: {e}")
            return [base_color] * count
    
    @classmethod
    def get_contrast_color(cls, background_color: str) -> str:
        """배경색에 대비되는 텍스트 색상 반환"""
        try:
            # HEX를 RGB로 변환
            hex_color = background_color.lstrip('#')
            r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            
            # 밝기 계산 (0.299*R + 0.587*G + 0.114*B)
            brightness = (0.299 * r + 0.587 * g + 0.114 * b) / 255
            
            # 밝기에 따라 텍스트 색상 결정
            if brightness > 0.5:
                return "#000000"  # 어두운 텍스트
            else:
                return "#ffffff"  # 밝은 텍스트
                
        except Exception as e:
            print(f"대비 색상 계산 오류: {e}")
            return "#000000"
    
    @classmethod
    def validate_color(cls, color: str) -> bool:
        """색상 형식 검증"""
        if not color.startswith('#'):
            return False
        
        if len(color) != 7:
            return False
        
        try:
            int(color[1:], 16)
            return True
        except ValueError:
            return False
    
    @classmethod
    def get_color_info(cls, color: str) -> Dict[str, Any]:
        """색상 정보 반환"""
        try:
            hex_color = color.lstrip('#')
            r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            h, s, v = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)
            
            return {
                "hex": color,
                "rgb": (r, g, b),
                "hsv": (h, s, v),
                "brightness": (0.299 * r + 0.587 * g + 0.114 * b) / 255,
                "is_dark": (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5
            }
        except Exception as e:
            print(f"색상 정보 추출 오류: {e}")
            return {}
    
    @classmethod
    def create_gradient(cls, start_color: str, end_color: str, steps: int = 10) -> List[str]:
        """그라데이션 색상 생성"""
        try:
            # 시작 색상 RGB
            start_hex = start_color.lstrip('#')
            start_r, start_g, start_b = tuple(int(start_hex[i:i+2], 16) for i in (0, 2, 4))
            
            # 끝 색상 RGB
            end_hex = end_color.lstrip('#')
            end_r, end_g, end_b = tuple(int(end_hex[i:i+2], 16) for i in (0, 2, 4))
            
            gradient = []
            for i in range(steps):
                ratio = i / (steps - 1)
                r = int(start_r + (end_r - start_r) * ratio)
                g = int(start_g + (end_g - start_g) * ratio)
                b = int(start_b + (end_b - start_b) * ratio)
                
                hex_color = "#{:02x}{:02x}{:02x}".format(r, g, b)
                gradient.append(hex_color)
            
            return gradient
            
        except Exception as e:
            print(f"그라데이션 생성 오류: {e}")
            return [start_color, end_color]
