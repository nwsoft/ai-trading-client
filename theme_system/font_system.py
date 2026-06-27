#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
폰트 시스템
금융 앱에 적합한 전문적 폰트 시스템 구현
"""

import tkinter as tk
from typing import Dict, List, Optional, Tuple
import platform
import os

class FontSystem:
    """전문적 폰트 시스템 관리 클래스"""
    
    def __init__(self):
        self.system = platform.system()
        self.available_fonts = self._get_available_fonts()
        self.font_configs = self._create_font_configs()
        
    def _get_available_fonts(self) -> List[str]:
        """시스템에서 사용 가능한 폰트 목록 반환"""
        try:
            if self.system == "Windows":
                return self._get_windows_fonts()
            elif self.system == "Darwin":  # macOS
                return self._get_macos_fonts()
            else:  # Linux
                return self._get_linux_fonts()
        except Exception as e:
            print(f"폰트 목록 가져오기 오류: {e}")
            return ["Arial", "Helvetica", "Times New Roman"]
    
    def _get_windows_fonts(self) -> List[str]:
        """Windows 시스템 폰트 목록"""
        windows_fonts = [
            # 금융 앱에 적합한 전문 폰트들
            "Segoe UI",           # Windows 기본 UI 폰트
            "Segoe UI Semibold",  # 세미볼드
            "Segoe UI Light",     # 라이트
            "Segoe UI Semilight", # 세미라이트
            "Calibri",            # Office 기본 폰트
            "Arial",              # 클래식
            "Arial Black",        # 굵은 폰트
            "Tahoma",             # 작은 크기에도 선명
            "Verdana",            # 가독성 좋음
            "Trebuchet MS",       # 모던
            "Consolas",           # 모노스페이스 (코드용)
            "Courier New",        # 모노스페이스
            "Times New Roman",    # 세리프
            "Georgia",            # 세리프
            "Impact",             # 강조용
            "Franklin Gothic",    # 클래식
            "Century Gothic",     # 모던
            "Lucida Console",     # 모노스페이스
            "Microsoft Sans Serif", # 시스템
            "MS Sans Serif"       # 레거시
        ]
        return windows_fonts
    
    def _get_macos_fonts(self) -> List[str]:
        """macOS 시스템 폰트 목록"""
        macos_fonts = [
            "SF Pro Display",     # Apple 시스템 폰트
            "SF Pro Text",        # Apple 텍스트 폰트
            "Helvetica Neue",     # 클래식
            "Helvetica",          # 기본
            "Arial",              # 크로스 플랫폼
            "Arial Black",        # 굵은 폰트
            "Tahoma",             # 가독성
            "Verdana",            # 가독성
            "Trebuchet MS",       # 모던
            "Consolas",           # 모노스페이스
            "Courier New",        # 모노스페이스
            "Times New Roman",    # 세리프
            "Georgia",            # 세리프
            "Impact",             # 강조용
            "Franklin Gothic",    # 클래식
            "Century Gothic",     # 모던
            "Lucida Console",     # 모노스페이스
            "Menlo",              # Apple 모노스페이스
            "Monaco"              # Apple 모노스페이스
        ]
        return macos_fonts
    
    def _get_linux_fonts(self) -> List[str]:
        """Linux 시스템 폰트 목록"""
        linux_fonts = [
            "Ubuntu",             # Ubuntu 기본
            "Ubuntu Mono",        # Ubuntu 모노스페이스
            "Liberation Sans",    # 오픈소스
            "Liberation Serif",   # 오픈소스 세리프
            "Liberation Mono",    # 오픈소스 모노스페이스
            "DejaVu Sans",        # 오픈소스
            "DejaVu Serif",       # 오픈소스 세리프
            "DejaVu Sans Mono",   # 오픈소스 모노스페이스
            "Arial",              # 크로스 플랫폼
            "Helvetica",          # 크로스 플랫폼
            "Tahoma",             # 가독성
            "Verdana",            # 가독성
            "Trebuchet MS",       # 모던
            "Consolas",           # 모노스페이스
            "Courier New",        # 모노스페이스
            "Times New Roman",    # 세리프
            "Georgia",            # 세리프
            "Impact",             # 강조용
            "Franklin Gothic",    # 클래식
            "Century Gothic"      # 모던
        ]
        return linux_fonts
    
    def _create_font_configs(self) -> Dict[str, Dict[str, any]]:
        """폰트 설정 생성"""
        return {
            "trading_pro": {
                "name": "트레이딩 프로",
                "description": "전문 트레이딩용 폰트 설정",
                "fonts": {
                    "primary": "Segoe UI",
                    "secondary": "Segoe UI Light",
                    "bold": "Segoe UI Semibold",
                    "monospace": "Consolas",
                    "display": "Segoe UI",
                    "caption": "Segoe UI Light"
                },
                "sizes": {
                    "h1": 24,      # 대제목
                    "h2": 20,      # 중제목
                    "h3": 18,      # 소제목
                    "h4": 16,      # 섹션 제목
                    "body": 14,    # 본문
                    "caption": 12, # 캡션
                    "small": 10,   # 작은 텍스트
                    "code": 12     # 코드
                },
                "weights": {
                    "light": "normal",
                    "normal": "normal",
                    "medium": "normal",
                    "semibold": "bold",
                    "bold": "bold"
                }
            },
            "financial_classic": {
                "name": "금융 클래식",
                "description": "전통적인 금융 앱 폰트 설정",
                "fonts": {
                    "primary": "Arial",
                    "secondary": "Arial",
                    "bold": "Arial Black",
                    "monospace": "Courier New",
                    "display": "Arial Black",
                    "caption": "Arial"
                },
                "sizes": {
                    "h1": 22,
                    "h2": 18,
                    "h3": 16,
                    "h4": 14,
                    "body": 12,
                    "caption": 10,
                    "small": 9,
                    "code": 11
                },
                "weights": {
                    "light": "normal",
                    "normal": "normal",
                    "medium": "normal",
                    "semibold": "bold",
                    "bold": "bold"
                }
            },
            "modern_minimal": {
                "name": "모던 미니멀",
                "description": "현대적이고 깔끔한 폰트 설정",
                "fonts": {
                    "primary": "Segoe UI",
                    "secondary": "Segoe UI Light",
                    "bold": "Segoe UI Semibold",
                    "monospace": "Consolas",
                    "display": "Segoe UI",
                    "caption": "Segoe UI Light"
                },
                "sizes": {
                    "h1": 26,
                    "h2": 22,
                    "h3": 20,
                    "h4": 18,
                    "body": 15,
                    "caption": 13,
                    "small": 11,
                    "code": 13
                },
                "weights": {
                    "light": "normal",
                    "normal": "normal",
                    "medium": "normal",
                    "semibold": "bold",
                    "bold": "bold"
                }
            },
            "crypto_modern": {
                "name": "크립토 모던",
                "description": "암호화폐 트레이딩용 모던 폰트 설정",
                "fonts": {
                    "primary": "Segoe UI",
                    "secondary": "Segoe UI Light",
                    "bold": "Segoe UI Semibold",
                    "monospace": "Consolas",
                    "display": "Segoe UI",
                    "caption": "Segoe UI Light"
                },
                "sizes": {
                    "h1": 28,
                    "h2": 24,
                    "h3": 20,
                    "h4": 18,
                    "body": 16,
                    "caption": 14,
                    "small": 12,
                    "code": 14
                },
                "weights": {
                    "light": "normal",
                    "normal": "normal",
                    "medium": "normal",
                    "semibold": "bold",
                    "bold": "bold"
                }
            }
        }
    
    def get_font_config(self, config_name: str = "trading_pro") -> Dict[str, any]:
        """특정 폰트 설정 반환"""
        if config_name in self.font_configs:
            return self.font_configs[config_name]
        else:
            return self.font_configs["trading_pro"]
    
    def get_font(self, config_name: str, font_type: str, size: str = "body", weight: str = "normal") -> Tuple[str, int, str]:
        """폰트 정보 반환 (폰트명, 크기, 가중치)"""
        config = self.get_font_config(config_name)
        
        font_name = config["fonts"].get(font_type, config["fonts"]["primary"])
        font_size = config["sizes"].get(size, config["sizes"]["body"])
        font_weight = config["weights"].get(weight, config["weights"]["normal"])
        
        return font_name, font_size, font_weight
    
    def create_tkinter_font(self, config_name: str, font_type: str, size: str = "body", weight: str = "normal"):
        """Tkinter Font 객체 생성"""
        try:
            from tkinter import font
            font_name, font_size, font_weight = self.get_font(config_name, font_type, size, weight)
            
            return font.Font(
                family=font_name,
                size=font_size,
                weight=font_weight
            )
        except ImportError:
            print("Tkinter font 모듈을 가져올 수 없습니다.")
            return None
    
    def create_customtkinter_font(self, config_name: str, font_type: str, size: str = "body", weight: str = "normal"):
        """CustomTkinter Font 객체 생성"""
        try:
            import customtkinter as ctk
            font_name, font_size, font_weight = self.get_font(config_name, font_type, size, weight)
            
            return ctk.CTkFont(
                family=font_name,
                size=font_size,
                weight=font_weight
            )
        except ImportError:
            print("CustomTkinter가 설치되지 않았습니다.")
            return None
    
    def get_available_font_configs(self) -> List[str]:
        """사용 가능한 폰트 설정 목록 반환"""
        return list(self.font_configs.keys())
    
    def validate_font(self, font_name: str) -> bool:
        """폰트 사용 가능 여부 확인"""
        return font_name in self.available_fonts
    
    def get_font_hierarchy(self, config_name: str = "trading_pro") -> Dict[str, Dict[str, any]]:
        """폰트 계층 구조 반환"""
        config = self.get_font_config(config_name)
        
        hierarchy = {}
        for size_name, size_value in config["sizes"].items():
            hierarchy[size_name] = {
                "font": config["fonts"]["primary"],
                "size": size_value,
                "weight": config["weights"]["normal"]
            }
        
        return hierarchy
    
    def create_font_style_guide(self, config_name: str = "trading_pro") -> Dict[str, any]:
        """폰트 스타일 가이드 생성"""
        config = self.get_font_config(config_name)
        
        style_guide = {
            "config_name": config_name,
            "display_name": config["name"],
            "description": config["description"],
            "hierarchy": self.get_font_hierarchy(config_name),
            "usage_examples": {
                "headings": {
                    "h1": "메인 제목 (대시보드 제목)",
                    "h2": "섹션 제목 (탭 제목)",
                    "h3": "카드 제목",
                    "h4": "소제목"
                },
                "body": {
                    "body": "일반 텍스트 (설명, 내용)",
                    "caption": "캡션 (부가 정보)",
                    "small": "작은 텍스트 (시간, 상태)"
                },
                "special": {
                    "monospace": "코드, 로그, 데이터 표시",
                    "bold": "강조 텍스트",
                    "display": "큰 숫자, 통계"
                }
            }
        }
        
        return style_guide
    
    def get_font_recommendations(self, app_type: str = "trading") -> List[str]:
        """앱 유형별 폰트 추천"""
        recommendations = {
            "trading": [
                "Segoe UI",           # Windows 기본
                "Arial",              # 크로스 플랫폼
                "Tahoma",             # 가독성
                "Verdana",            # 가독성
                "Consolas"            # 모노스페이스
            ],
            "financial": [
                "Arial",              # 클래식
                "Arial Black",        # 강조
                "Tahoma",             # 가독성
                "Verdana",            # 가독성
                "Courier New"         # 모노스페이스
            ],
            "modern": [
                "Segoe UI",           # 모던
                "Segoe UI Light",     # 라이트
                "Segoe UI Semibold",  # 세미볼드
                "Consolas",           # 모노스페이스
                "Calibri"             # Office
            ],
            "crypto": [
                "Segoe UI",           # 모던
                "Arial",              # 크로스 플랫폼
                "Consolas",           # 모노스페이스
                "Courier New",        # 모노스페이스
                "Tahoma"              # 가독성
            ]
        }
        
        return recommendations.get(app_type, recommendations["trading"])
    
    def create_font_test_suite(self) -> Dict[str, any]:
        """폰트 테스트 스위트 생성"""
        test_suite = {
            "test_texts": {
                "korean": "안녕하세요! NoahAI Trading입니다.",
                "english": "Hello! Welcome to NoahAI Trading.",
                "numbers": "123,456.78 USDT",
                "symbols": "BTC/USDT +2.34% ↑",
                "mixed": "BTCUSDT: $45,678.90 (+2.34%)"
            },
            "test_sizes": ["h1", "h2", "h3", "h4", "body", "caption", "small"],
            "test_weights": ["light", "normal", "medium", "semibold", "bold"],
            "test_fonts": self.get_font_recommendations("trading")
        }
        
        return test_suite
