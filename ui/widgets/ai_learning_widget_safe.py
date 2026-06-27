#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 학습 위젯 (CustomTkinter) - 안전한 버전
AI 학습 과정과 데이터를 모니터링하는 전용 위젯
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import customtkinter as ctk
from customtkinter import CTkFrame, CTkLabel, CTkButton, CTkProgressBar, CTkScrollableFrame, CTkTextbox

class AILearningWidgetSafe(CTkFrame):
    """AI 학습 전용 위젯 (CustomTkinter) - 안전한 버전"""
    DEFAULT_COLORS: Dict[str, str] = {
        "text_primary": "#f9fafb",
        "text_secondary": "#9ca3af",
        "success": "#22c55e",
        "info": "#3b82f6",
        "danger": "#ef4444",
        "accent": "#9b59b6",
    }

    
    def __init__(self, parent=None, colors: Optional[Dict[str, str]] = None, **kwargs):
        super().__init__(parent, **kwargs)
        self.logger = logging.getLogger(__name__)
        self.colors = dict(colors) if colors and isinstance(colors, dict) else {}
        
        # 초기화 상태 플래그
        self.is_initialized = False
        
        try:
            self.init_ui()
            self.is_initialized = True
            print("✅ AI 학습 위젯 초기화 완료")
        except Exception as e:
            print(f"❌ AI 학습 위젯 초기화 실패: {e}")
            self.create_error_ui(str(e))
        
    def _color(self, key: str, fallback: Optional[str] = None) -> str:
        if fallback is None:
            fallback = self.DEFAULT_COLORS.get(key, "#9ca3af")
        try:
            value = self.colors.get(key) if isinstance(self.colors, dict) else None
            if value:
                return value
        except Exception:
            pass
        return fallback

    def init_ui(self):
        """UI 초기화 - 안전한 버전"""
        # 메인 레이아웃
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # 1. AI 학습 상태 섹션
        self.create_status_section()
        
        # 2. 학습 데이터 테이블 섹션
        self.create_data_section()
        
        # 3. AI 학습 통계 섹션
        self.create_performance_section()
        
        # 초기 데이터는 나중에 로드
        self.after(1000, self.load_learning_data_safe)
        
    def create_error_ui(self, error_msg):
        """오류 발생 시 표시할 UI"""
        error_frame = CTkFrame(self)
        error_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        error_frame.grid_columnconfigure(0, weight=1)
        error_frame.grid_rowconfigure(0, weight=1)
        
        error_label = CTkLabel(
            error_frame,
            text=f"❌ AI 학습 위젯 로드 실패\n{error_msg}",
            font=ctk.CTkFont(size=14),
            text_color=self._color("danger", "#ef4444")
        )
        error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        
    def create_status_section(self):
        """AI 학습 상태 섹션 생성"""
        status_frame = CTkFrame(self)
        status_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        status_frame.grid_columnconfigure(1, weight=1)
        
        # 제목
        title_label = CTkLabel(
            status_frame, 
            text="🧠 AI 학습 상태",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 5))
        
        # 현재 상태
        CTkLabel(status_frame, text="현재 상태:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.learning_status_label = CTkLabel(
            status_frame, 
            text="초기화 중...",
            font=ctk.CTkFont(weight="bold")
        )
        self.learning_status_label.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        # 진행률 표시
        self.learning_progress = CTkProgressBar(status_frame)
        self.learning_progress.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        self.learning_progress.set(0)
        
    def create_data_section(self):
        """학습 데이터 테이블 섹션 생성"""
        data_frame = CTkFrame(self)
        data_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        data_frame.grid_columnconfigure(0, weight=1)
        data_frame.grid_rowconfigure(1, weight=1)
        
        # 제목
        title_label = CTkLabel(
            data_frame, 
            text="📚 AI 학습 데이터",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))
        
        # 새로고침 버튼
        refresh_button = CTkButton(
            data_frame,
            text="🔄 새로고침",
            command=self.refresh_learning_data_safe,
            width=100,
            height=30
        )
        refresh_button.grid(row=0, column=0, sticky="e", padx=10, pady=(10, 5))
        
        # 스크롤 가능한 데이터 영역
        self.data_scroll = CTkScrollableFrame(data_frame)
        self.data_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.data_scroll.grid_columnconfigure(0, weight=1)
        
        # 헤더 생성
        self.create_data_headers()
        
        # 통계 정보
        self.create_stats_info()
        
    def create_data_headers(self):
        """데이터 테이블 헤더 생성"""
        headers = ["시간", "코인", "시그널", "신뢰도", "RSI", "MACD", "트렌드", "추론"]
        
        header_frame = CTkFrame(self.data_scroll)
        header_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        
        for i, header in enumerate(headers):
            header_label = CTkLabel(
                header_frame,
                text=header,
                font=ctk.CTkFont(weight="bold"),
                width=100 if i < 7 else 200
            )
            header_label.grid(row=0, column=i, padx=2, pady=5)
            header_frame.grid_columnconfigure(i, weight=1)
            
    def create_stats_info(self):
        """통계 정보 섹션 생성"""
        stats_frame = CTkFrame(self.data_scroll)
        stats_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        stats_frame.grid_columnconfigure(0, weight=1)
        
        # AI 학습 상태
        self.auto_learning_label = CTkLabel(
            stats_frame,
            text="🤖 AI 학습 초기화 중...",
            font=ctk.CTkFont(weight="bold"),
            text_color=self._color("success", "#27ae60")
        )
        self.auto_learning_label.grid(row=0, column=0, sticky="w", padx=10, pady=5)
        
        # 통계 정보들
        stats_info_frame = CTkFrame(stats_frame)
        stats_info_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        stats_info_frame.grid_columnconfigure(0, weight=1)
        
        self.today_stats_label = CTkLabel(
            stats_info_frame,
            text="📅 오늘: 0개",
            text_color=self._color("info", "#3498db")
        )
        self.today_stats_label.grid(row=0, column=0, sticky="w", padx=5, pady=2)
        
        self.weekly_stats_label = CTkLabel(
            stats_info_frame,
            text="📊 주간: 0개",
            text_color=self._color("danger", "#ef4444")
        )
        self.weekly_stats_label.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        
        self.signal_stats_label = CTkLabel(
            stats_info_frame,
            text="📈 신호: LONG(0) SHORT(0) HOLD(0)",
            text_color=self._color("accent", "#9b59b6")
        )
        self.signal_stats_label.grid(row=0, column=2, sticky="w", padx=5, pady=2)
        
    def create_performance_section(self):
        """AI 학습 통계 섹션 생성"""
        performance_frame = CTkFrame(self)
        performance_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        performance_frame.grid_columnconfigure(0, weight=1)
        
        # 제목
        title_label = CTkLabel(
            performance_frame, 
            text="📊 AI 학습 통계",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))
        
        # 통계 항목들
        self.performance_labels = {}
        performance_items = [
            ("총 분석 수", "total_analysis", "0"),
            ("LONG 신호", "long_signals", "0"),
            ("SHORT 신호", "short_signals", "0"),
            ("HOLD 신호", "hold_signals", "0"),
            ("평균 신뢰도", "avg_confidence", "0.0"),
            ("마지막 업데이트", "last_update", "N/A")
        ]
        
        for i, (label, key, default) in enumerate(performance_items):
            row = i // 2
            col = (i % 2) * 2
            
            CTkLabel(performance_frame, text=f"{label}:").grid(
                row=row+1, column=col, sticky="w", padx=10, pady=5
            )
            
            value_label = CTkLabel(
                performance_frame,
                text=default,
                font=ctk.CTkFont(weight="bold"),
                text_color=self._color("success", "#27ae60")
            )
            value_label.grid(row=row+1, column=col+1, sticky="w", padx=10, pady=5)
            
            self.performance_labels[key] = value_label
            
    def load_learning_data_safe(self):
        """학습 데이터 안전하게 로드 - 비동기 처리"""
        try:
            if not self.is_initialized:
                return
                
            # 로딩 상태 표시
            self.learning_status_label.configure(text="데이터 로딩 중...")
            self.learning_progress.set(0.1)
            
            # 비동기로 데이터 로드 (UI 블록 방지)
            self.after(100, self._load_data_async)
                
        except Exception as e:
            print(f"❌ AI 학습 데이터 로드 오류: {e}")
            self.learning_status_label.configure(text=f"오류: {str(e)[:20]}...")
            self.auto_learning_label.configure(text="🤖 AI 학습 오류")
    
    def _load_data_async(self):
        """비동기 데이터 로드"""
        try:
            # ai_learning_data.json에서 데이터 로드
            from path_utils import get_ai_learning_data_path
            data_file = get_ai_learning_data_path()
            if os.path.exists(data_file):
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 진행률 업데이트
                self.learning_progress.set(0.5)
                
                # 데이터 크기 관리
                self._manage_data_size(data_file, data)
                
                # 최근 100개만 표시 (성능 최적화)
                recent_data = data[-100:] if len(data) > 100 else data
                
                # 테이블에 데이터 표시
                self.update_learning_table_safe(recent_data)
                
                # 성능 지표 업데이트 (전체 데이터 사용)
                self.update_performance_indicators_safe(data)
                
                # 상태 업데이트
                self.learning_status_label.configure(text=f"데이터 로드 완료 ({len(data)}개 중 최근 {len(recent_data)}개 표시)")
                self.auto_learning_label.configure(text="🤖 AI 학습 활성화")
                self.learning_progress.set(1.0)
                
                print(f"✅ AI 학습 데이터 로드 완료: {len(data)}개 항목 (최근 {len(recent_data)}개 표시)")
            else:
                print("⚠️ AI 학습 데이터 파일을 찾을 수 없습니다.")
                self.learning_status_label.configure(text="데이터 파일 없음")
                self.auto_learning_label.configure(text="🤖 AI 학습 대기 중")
                self.learning_progress.set(0)
                
        except Exception as e:
            print(f"❌ AI 학습 데이터 로드 오류: {e}")
            self.learning_status_label.configure(text=f"오류: {str(e)[:20]}...")
            self.auto_learning_label.configure(text="🤖 AI 학습 오류")
            self.learning_progress.set(0)
    
    def _manage_data_size(self, data_file, data):
        """데이터 크기 관리"""
        try:
            # 파일 크기 확인
            file_size = os.path.getsize(data_file)
            file_size_mb = file_size / (1024 * 1024)
            
            # 5MB 이상이면 최근 2000개만 유지
            if file_size_mb > 5.0 or len(data) > 2000:
                print(f"⚠️ 데이터 크기 관리: {file_size_mb:.2f}MB, {len(data)}개 항목")
                
                # 최근 2000개만 유지
                if len(data) > 2000:
                    data = data[-2000:]
                    
                    # 백업 파일 생성
                    backup_file = data_file.replace('.json', '_backup.json')
                    with open(backup_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    
                    # 원본 파일 업데이트
                    with open(data_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    
                    print(f"✅ 데이터 크기 최적화 완료: {len(data)}개 항목 유지, 백업: {backup_file}")
                    
        except Exception as e:
            print(f"❌ 데이터 크기 관리 오류: {e}")
    
    def refresh_learning_data_safe(self):
        """AI 학습 데이터 안전하게 새로고침"""
        try:
            if not self.is_initialized:
                return
                
            self.learning_status_label.configure(text="새로고침 중...")
            self.load_learning_data_safe()
            
        except Exception as e:
            print(f"❌ AI 학습 데이터 새로고침 오류: {e}")
            self.learning_status_label.configure(text=f"오류: {str(e)[:20]}...")
    
    def update_learning_table_safe(self, data):
        """AI 학습 데이터 테이블 안전하게 업데이트"""
        try:
            if not self.is_initialized:
                return
                
            # 기존 데이터 행들 제거
            for widget in self.data_scroll.winfo_children():
                if isinstance(widget, CTkFrame) and widget.grid_info().get('row', 0) > 1:
                    widget.destroy()
            
            # 데이터 행들 추가
            for row, item in enumerate(data):
                self.create_data_row_safe(item, row + 2)
                
        except Exception as e:
            print(f"AI 학습 테이블 업데이트 오류: {e}")
    
    def create_data_row_safe(self, item, row):
        """데이터 행 안전하게 생성"""
        try:
            row_frame = CTkFrame(self.data_scroll)
            row_frame.grid(row=row, column=0, sticky="ew", padx=5, pady=2)
            row_frame.grid_columnconfigure(0, weight=1)
            
            # 시간 (timestamp)
            timestamp = item.get('timestamp', 'N/A')
            if isinstance(timestamp, str):
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_str = dt.strftime("%H:%M")
                except:
                    time_str = timestamp[:5] if len(timestamp) >= 5 else timestamp
            else:
                time_str = timestamp.strftime("%H:%M") if hasattr(timestamp, 'strftime') else str(timestamp)
            
            # 각 컬럼 데이터 표시
            columns = [
                time_str,
                str(item.get('symbol', 'N/A')),
                str(item.get('signal', 'N/A')),
                f"{item.get('confidence', 0):.1f}" if isinstance(item.get('confidence'), (int, float)) else str(item.get('confidence', 'N/A')),
                f"{item.get('rsi', 0):.1f}" if isinstance(item.get('rsi'), (int, float)) else str(item.get('rsi', 'N/A')),
                f"{item.get('macd', 0):.4f}" if isinstance(item.get('macd'), (int, float)) else str(item.get('macd', 'N/A')),
                str(item.get('trend', 'N/A')).replace('TrendDirection.', ''),
                str(item.get('reasoning', 'N/A'))[:50] + "..." if len(str(item.get('reasoning', 'N/A'))) > 50 else str(item.get('reasoning', 'N/A'))
            ]
            
            for i, col_data in enumerate(columns):
                label = CTkLabel(
                    row_frame,
                    text=col_data,
                    width=100 if i < 7 else 200,
                    anchor="w"
                )
                label.grid(row=0, column=i, padx=2, pady=2, sticky="w")
                row_frame.grid_columnconfigure(i, weight=1)
                
        except Exception as e:
            print(f"데이터 행 생성 오류: {e}")
    
    def update_performance_indicators_safe(self, data):
        """AI 학습 통계 안전하게 업데이트"""
        try:
            if not self.is_initialized or not data:
                return
                
            # 총 분석 데이터 수
            total = len(data)
            self.performance_labels['total_analysis'].configure(text=str(total))
            
            # 시그널별 개수 계산
            long_count = sum(1 for item in data if item.get('signal') == 'LONG')
            short_count = sum(1 for item in data if item.get('signal') == 'SHORT')
            hold_count = sum(1 for item in data if item.get('signal') == 'HOLD')
            
            self.performance_labels['long_signals'].configure(text=str(long_count))
            self.performance_labels['short_signals'].configure(text=str(short_count))
            self.performance_labels['hold_signals'].configure(text=str(hold_count))
            
            # 평균 신뢰도 계산
            confidences = [item.get('confidence', 0) for item in data if isinstance(item.get('confidence'), (int, float))]
            if confidences:
                avg_confidence = sum(confidences) / len(confidences)
                self.performance_labels['avg_confidence'].configure(text=f"{avg_confidence:.2f}")
            else:
                self.performance_labels['avg_confidence'].configure(text="0.0")
            
            # 마지막 업데이트
            self.performance_labels['last_update'].configure(text=datetime.now().strftime("%H:%M"))
            
        except Exception as e:
            print(f"AI 학습 통계 업데이트 오류: {e}")
