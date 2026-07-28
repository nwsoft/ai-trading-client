#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 리포트 위젯 (CustomTkinter) - 안전한 버전
자동 생성되는 거래 리포트를 표시하는 전용 위젯
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import customtkinter as ctk
from customtkinter import CTkFrame, CTkLabel, CTkButton, CTkTextbox, CTkScrollableFrame, CTkTabview
from ui.visual_system import style_tabview
from utils.fixed_colors import build_widget_palette

class AIReportWidgetSafe(CTkFrame):
    """AI 리포트 전용 위젯 (CustomTkinter) - 안전한 버전"""
    DEFAULT_COLORS: Dict[str, str] = {
        "text_primary": "#f9fafb",
        "text_secondary": "#9ca3af",
        "success": "#22c55e",
        "info": "#3b82f6",
        "danger": "#ef4444",
        "accent": "#9b59b6",
        "warning": "#f59e0b",
    }

    
    def __init__(self, parent=None, colors: Optional[Dict[str, str]] = None, **kwargs):
        self.colors = build_widget_palette(
            colors if colors and isinstance(colors, dict) else None
        )
        kwargs.setdefault("fg_color", self.colors["content_bg"])
        kwargs.setdefault("corner_radius", 10)
        super().__init__(parent, **kwargs)
        self.logger = logging.getLogger(__name__)
        self._after_jobs = []
        self._disposed = False
        
        # 초기화 상태 플래그
        self.is_initialized = False
        
        try:
            self.init_ui()
            self.is_initialized = True
            print("AI 리포트 위젯 초기화 완료")
        except Exception as e:
            print(f"AI 리포트 위젯 초기화 실패: {e}")
            self.create_error_ui(str(e))
        
        # 자동 리포트 생성 타이머
        self.report_timer = None
        self.last_report_generation = None
        self.bind("<Map>", self._on_map_visible, add="+")
        self.bind("<Unmap>", self._on_unmap_hidden, add="+")
        self.bind("<Destroy>", self._on_destroyed, add="+")
        
        # 초기 리포트 생성
        self._schedule_report_refresh(1000)

    def _safe_after(self, delay_ms, callback):
        if self._disposed:
            return None
        job_ref = {"id": None}

        def _runner():
            job_id = job_ref.get("id")
            if job_id in self._after_jobs:
                self._after_jobs.remove(job_id)
            if not self._disposed:
                callback()

        try:
            job_id = self.after(delay_ms, _runner)
            job_ref["id"] = job_id
            self._after_jobs.append(job_id)
            return job_id
        except Exception:
            return None

    def _schedule_report_refresh(self, delay_ms=0):
        if self._disposed or self.report_timer is not None:
            return
        self.report_timer = self._safe_after(delay_ms, self._run_visible_report_refresh)

    def _run_visible_report_refresh(self):
        self.report_timer = None
        try:
            if not self.winfo_exists() or not self.winfo_viewable():
                return
        except Exception:
            return
        self.auto_generate_reports()

    def _on_map_visible(self, event=None):
        if event is not None and getattr(event, "widget", None) is not self:
            return
        self._schedule_report_refresh(0)

    def _on_unmap_hidden(self, event=None):
        if event is not None and getattr(event, "widget", None) is not self:
            return
        if self.report_timer is not None:
            try:
                self.after_cancel(self.report_timer)
            except Exception:
                pass
            if self.report_timer in self._after_jobs:
                self._after_jobs.remove(self.report_timer)
            self.report_timer = None

    def _on_destroyed(self, event=None):
        if event is not None and getattr(event, "widget", None) is not self:
            return
        self.cleanup_after_jobs()

    def cleanup_after_jobs(self):
        self._disposed = True
        for job_id in list(self._after_jobs):
            try:
                self.after_cancel(job_id)
            except Exception:
                pass
        self._after_jobs.clear()
        self.report_timer = None

    def destroy(self):
        self.cleanup_after_jobs()
        return super().destroy()
        
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

    def _card_frame(self, parent, **kwargs):
        kwargs.setdefault("fg_color", self._color("surface", "#111827"))
        kwargs.setdefault("border_color", self._color("border", "#273449"))
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("corner_radius", 10)
        return ctk.CTkFrame(parent, **kwargs)

    def _report_textbox(self, parent, **kwargs):
        kwargs.setdefault("fg_color", self._color("input", "#0b1120"))
        kwargs.setdefault("border_color", self._color("border_strong", "#334155"))
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("text_color", self._color("text_primary", "#f9fafb"))
        kwargs.setdefault("corner_radius", 8)
        return ctk.CTkTextbox(parent, **kwargs)

    def init_ui(self):
        """UI 초기화"""
        # 메인 레이아웃
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        
        # 제목
        title_label = ctk.CTkLabel(
            self,
            text="AI 자동 리포트",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.grid(row=0, column=0, pady=(10, 5))
        
        # 설명
        desc_label = ctk.CTkLabel(
            self,
            text="AI가 자동으로 생성하는 거래 리포트입니다. 실시간으로 업데이트됩니다.",
            font=ctk.CTkFont(size=12),
            text_color=self._color("text_secondary", "#7f8c8d")
        )
        desc_label.grid(row=1, column=0, pady=(0, 10))
        
        # 리포트 탭 위젯
        self.report_tabs = ctk.CTkTabview(
            self,
            fg_color=self._color("content_bg", "#0b1120"),
        )
        style_tabview(
            self.report_tabs,
            accent=self._color("primary", "#2563eb"),
            bar_color=self._color("tabbar_bg", "#111c2f"),
            inactive=self._color("tab_inactive", "#263a57"),
            text_color=self._color("tab_text", "#dbe7f5"),
        )
        self.report_tabs.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        
        # 오늘 리포트 탭
        self.today_tab = self.report_tabs.add("오늘")
        self.today_tab.configure(fg_color=self._color("content_bg", "#0b1120"))
        self.create_today_report_tab()
        
        # 주간 리포트 탭
        self.weekly_tab = self.report_tabs.add("주간")
        self.weekly_tab.configure(fg_color=self._color("content_bg", "#0b1120"))
        self.create_weekly_report_tab()
        
        # 월간 리포트 탭
        self.monthly_tab = self.report_tabs.add("월간")
        self.monthly_tab.configure(fg_color=self._color("content_bg", "#0b1120"))
        self.create_monthly_report_tab()
        
        # 새로고침 버튼
        refresh_btn = ctk.CTkButton(
            self,
            text="새로고침",
            command=self.auto_generate_reports,
            width=120,
            height=35,
            fg_color=self._color("primary", "#2563eb"),
            hover_color=self._color("primary_hover", "#1d4ed8"),
        )
        refresh_btn.grid(row=3, column=0, pady=10)
        
    def create_error_ui(self, error_msg):
        """오류 발생 시 표시할 UI"""
        error_frame = self._card_frame(self)
        error_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        error_frame.grid_columnconfigure(0, weight=1)
        error_frame.grid_rowconfigure(0, weight=1)
        
        error_label = ctk.CTkLabel(
            error_frame,
            text=f"AI 리포트 위젯 로드 실패\n{error_msg}",
            font=ctk.CTkFont(size=14),
            text_color=self._color("danger", "#ef4444")
        )
        error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        
    def create_today_report_tab(self):
        """오늘 리포트 탭 생성"""
        # 요약 정보
        summary_frame = self._card_frame(self.today_tab)
        summary_frame.pack(fill="x", padx=10, pady=10)
        
        # 요약 제목
        summary_title = ctk.CTkLabel(
            summary_frame,
            text="오늘 거래 요약",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        summary_title.pack(pady=10)
        
        # 요약 정보 표시
        self.today_summary = self._report_textbox(
            summary_frame,
            height=150,
            font=ctk.CTkFont(size=12)
        )
        self.today_summary.pack(fill="x", padx=10, pady=5)
        
        # 상세 리포트
        detail_frame = self._card_frame(self.today_tab)
        detail_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 상세 제목
        detail_title = ctk.CTkLabel(
            detail_frame,
            text="상세 거래 내역",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        detail_title.pack(pady=10)
        
        # 상세 리포트 표시
        self.today_detail = self._report_textbox(
            detail_frame,
            font=ctk.CTkFont(size=11)
        )
        self.today_detail.pack(fill="both", expand=True, padx=10, pady=5)
        
    def create_weekly_report_tab(self):
        """주간 리포트 탭 생성"""
        # 요약 정보
        summary_frame = self._card_frame(self.weekly_tab)
        summary_frame.pack(fill="x", padx=10, pady=10)
        
        # 요약 제목
        summary_title = ctk.CTkLabel(
            summary_frame,
            text="주간 거래 요약",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        summary_title.pack(pady=10)
        
        # 요약 정보 표시
        self.weekly_summary = self._report_textbox(
            summary_frame,
            height=150,
            font=ctk.CTkFont(size=12)
        )
        self.weekly_summary.pack(fill="x", padx=10, pady=5)
        
        # 상세 리포트
        detail_frame = self._card_frame(self.weekly_tab)
        detail_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 상세 제목
        detail_title = ctk.CTkLabel(
            detail_frame,
            text="주간 상세 분석",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        detail_title.pack(pady=10)
        
        # 상세 리포트 표시
        self.weekly_detail = self._report_textbox(
            detail_frame,
            font=ctk.CTkFont(size=11)
        )
        self.weekly_detail.pack(fill="both", expand=True, padx=10, pady=5)
        
    def create_monthly_report_tab(self):
        """월간 리포트 탭 생성"""
        # 요약 정보
        summary_frame = self._card_frame(self.monthly_tab)
        summary_frame.pack(fill="x", padx=10, pady=10)
        
        # 요약 제목
        summary_title = ctk.CTkLabel(
            summary_frame,
            text="월간 거래 요약",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        summary_title.pack(pady=10)
        
        # 요약 정보 표시
        self.monthly_summary = self._report_textbox(
            summary_frame,
            height=150,
            font=ctk.CTkFont(size=12)
        )
        self.monthly_summary.pack(fill="x", padx=10, pady=5)
        
        # 상세 리포트
        detail_frame = self._card_frame(self.monthly_tab)
        detail_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 상세 제목
        detail_title = ctk.CTkLabel(
            detail_frame,
            text="월간 상세 분석",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        detail_title.pack(pady=10)
        
        # 상세 리포트 표시
        self.monthly_detail = self._report_textbox(
            detail_frame,
            font=ctk.CTkFont(size=11)
        )
        self.monthly_detail.pack(fill="both", expand=True, padx=10, pady=5)
        
    def auto_generate_reports(self):
        """자동 리포트 생성"""
        try:
            if not self.is_initialized:
                return
                
            # 비동기로 리포트 생성 (UI 블록 방지)
            self._safe_after(100, self._generate_reports_async)
            
        except Exception as e:
            print(f"AI 리포트 생성 오류: {e}")
    
    def _generate_reports_async(self):
        """비동기 리포트 생성"""
        try:
            # 데이터베이스에서 거래 데이터 로드
            trading_data = self._load_trading_data()
            
            # 오늘 리포트 생성
            self._generate_today_report(trading_data)
            
            # 주간 리포트 생성
            self._generate_weekly_report(trading_data)
            
            # 월간 리포트 생성
            self._generate_monthly_report(trading_data)
            
            print("AI 리포트 생성 완료")
            
        except Exception as e:
            print(f"AI 리포트 생성 오류: {e}")
    
    def _load_trading_data(self):
        """거래 데이터 로드"""
        try:
            # 데이터베이스에서 거래 로그 로드
            from path_utils import get_db_file_path
            db_path = get_db_file_path()
            if not os.path.exists(db_path):
                return []
            
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 최근 30일 거래 데이터 로드
            cursor.execute("""
                SELECT * FROM trade_log 
                WHERE timestamp >= datetime('now', '-30 days')
                ORDER BY timestamp DESC
            """)
            
            data = cursor.fetchall()
            conn.close()
            
            return data
            
        except Exception as e:
            print(f"거래 데이터 로드 오류: {e}")
            return []
    
    def _generate_today_report(self, trading_data):
        """오늘 리포트 생성"""
        try:
            today = datetime.now().date()
            today_data = [row for row in trading_data if datetime.fromisoformat(row[1]).date() == today]
            
            # 요약 정보
            total_trades = len(today_data)
            profitable_trades = len([row for row in today_data if row[4] > 0])  # profit > 0
            win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
            total_profit = sum(row[4] for row in today_data)  # total profit
            
            summary_text = f"""오늘 거래 요약 ({today.strftime('%Y-%m-%d')})

총 거래 수: {total_trades}건
수익 거래: {profitable_trades}건
승률: {win_rate:.1f}%
총 수익: {total_profit:.2f} USDT
⏰ 마지막 거래: {today_data[0][1] if today_data else 'N/A'}

AI 분석:
- 시장 상황: {'상승' if total_profit > 0 else '하락'}
- 거래 패턴: {'안정적' if win_rate > 50 else '불안정'}
- 추천: {'계속 거래' if total_profit > 0 else '거래 중단 고려'}
"""
            
            self.today_summary.delete("1.0", "end")
            self.today_summary.insert("1.0", summary_text)
            
            # 상세 내역
            detail_text = "상세 거래 내역\n\n"
            for i, row in enumerate(today_data[:20]):  # 최근 20건만 표시
                timestamp = row[1]
                symbol = row[2]
                side = row[3]
                profit = row[4]
                detail_text += f"{i+1:2d}. {timestamp[:16]} | {symbol:8s} | {side:4s} | {profit:8.2f} USDT\n"
            
            if len(today_data) > 20:
                detail_text += f"\n... 및 {len(today_data) - 20}건 더"
            
            self.today_detail.delete("1.0", "end")
            self.today_detail.insert("1.0", detail_text)
            
        except Exception as e:
            print(f"오늘 리포트 생성 오류: {e}")
    
    def _generate_weekly_report(self, trading_data):
        """주간 리포트 생성"""
        try:
            week_ago = datetime.now() - timedelta(days=7)
            weekly_data = [row for row in trading_data if datetime.fromisoformat(row[1]) >= week_ago]
            
            # 요약 정보
            total_trades = len(weekly_data)
            profitable_trades = len([row for row in weekly_data if row[4] > 0])
            win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
            total_profit = sum(row[4] for row in weekly_data)
            
            summary_text = f"""주간 거래 요약 (최근 7일)

총 거래 수: {total_trades}건
수익 거래: {profitable_trades}건
승률: {win_rate:.1f}%
총 수익: {total_profit:.2f} USDT
일평균: {total_profit/7:.2f} USDT

AI 분석:
- 주간 성과: {'우수' if total_profit > 100 else '보통' if total_profit > 0 else '부진'}
- 거래 빈도: {'높음' if total_trades > 50 else '보통' if total_trades > 20 else '낮음'}
- 추천: {'전략 유지' if win_rate > 60 else '전략 재검토'}
"""
            
            self.weekly_summary.delete("1.0", "end")
            self.weekly_summary.insert("1.0", summary_text)
            
            # 상세 분석
            detail_text = "주간 상세 분석\n\n"
            detail_text += f"분석 기간: {week_ago.strftime('%Y-%m-%d')} ~ {datetime.now().strftime('%Y-%m-%d')}\n\n"
            
            # 코인별 성과
            coin_performance = {}
            for row in weekly_data:
                symbol = row[2]
                profit = row[4]
                if symbol not in coin_performance:
                    coin_performance[symbol] = {'trades': 0, 'profit': 0}
                coin_performance[symbol]['trades'] += 1
                coin_performance[symbol]['profit'] += profit
            
            detail_text += "코인별 성과 (상위 10개):\n"
            sorted_coins = sorted(coin_performance.items(), key=lambda x: x[1]['profit'], reverse=True)
            for i, (symbol, data) in enumerate(sorted_coins[:10]):
                detail_text += f"{i+1:2d}. {symbol:8s} | {data['trades']:3d}건 | {data['profit']:8.2f} USDT\n"
            
            self.weekly_detail.delete("1.0", "end")
            self.weekly_detail.insert("1.0", detail_text)
            
        except Exception as e:
            print(f"주간 리포트 생성 오류: {e}")
    
    def _generate_monthly_report(self, trading_data):
        """월간 리포트 생성"""
        try:
            month_ago = datetime.now() - timedelta(days=30)
            monthly_data = [row for row in trading_data if datetime.fromisoformat(row[1]) >= month_ago]
            
            # 요약 정보
            total_trades = len(monthly_data)
            profitable_trades = len([row for row in monthly_data if row[4] > 0])
            win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
            total_profit = sum(row[4] for row in monthly_data)
            
            summary_text = f"""월간 거래 요약 (최근 30일)

총 거래 수: {total_trades}건
수익 거래: {profitable_trades}건
승률: {win_rate:.1f}%
총 수익: {total_profit:.2f} USDT
일평균: {total_profit/30:.2f} USDT

AI 분석:
- 월간 성과: {'우수' if total_profit > 500 else '보통' if total_profit > 0 else '부진'}
- 거래 안정성: {'높음' if win_rate > 60 else '보통' if win_rate > 40 else '낮음'}
- 추천: {'전략 확장' if total_profit > 1000 else '전략 유지' if total_profit > 0 else '전략 변경'}
"""
            
            self.monthly_summary.delete("1.0", "end")
            self.monthly_summary.insert("1.0", summary_text)
            
            # 상세 분석
            detail_text = "월간 상세 분석\n\n"
            detail_text += f"분석 기간: {month_ago.strftime('%Y-%m-%d')} ~ {datetime.now().strftime('%Y-%m-%d')}\n\n"
            
            # 주간별 성과
            weekly_profits = {}
            for row in monthly_data:
                week_start = datetime.fromisoformat(row[1]).date() - timedelta(days=datetime.fromisoformat(row[1]).weekday())
                week_key = week_start.strftime('%Y-%m-%d')
                if week_key not in weekly_profits:
                    weekly_profits[week_key] = 0
                weekly_profits[week_key] += row[4]
            
            detail_text += "주간별 수익 현황:\n"
            for week, profit in sorted(weekly_profits.items()):
                detail_text += f"  {week} ~ {profit:8.2f} USDT\n"
            
            self.monthly_detail.delete("1.0", "end")
            self.monthly_detail.insert("1.0", detail_text)
            
        except Exception as e:
            print(f"월간 리포트 생성 오류: {e}")
