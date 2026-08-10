#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
실제 AI 리포트 위젯 (CustomTkinter)
실제 거래 데이터 기반 AI 리포트 생성 및 표시
"""

import json
import logging
import os
import sqlite3
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

import customtkinter as ctk
from customtkinter import CTkFrame, CTkLabel, CTkButton, CTkTextbox, CTkScrollableFrame, CTkTabview
from api.kpi_client import emit_kpi_event
from ui.visual_system import style_tabview
from utils.fixed_colors import build_widget_palette
from utils.trade_operating_metrics import (
    calculate_currency_financial_metrics,
    calculate_trade_operating_metrics,
    format_currency_amount,
    format_hold_duration,
    format_notional,
    infer_quote_currency,
)
from utils.report_formatting import format_champion_challenger_section

class AIReportWidget(CTkFrame):
    """실제 AI 리포트 위젯 (CustomTkinter) - 실제 데이터 기반"""
    
    def __init__(self, parent=None, colors=None, **kwargs):
        self.colors = build_widget_palette(
            colors if colors and isinstance(colors, dict) else None
        )
        kwargs.setdefault("fg_color", self.colors["content_bg"])
        kwargs.setdefault("corner_radius", 10)
        super().__init__(parent, **kwargs)
        self.logger = logging.getLogger(__name__)

        # after() 작업 추적 리스트는 UI 초기화보다 먼저 준비해야 한다.
        # (init_ui 내부에서 safe_after가 호출되는 경로를 방어)
        self.after_jobs = []
        self._disposed = False
        
        # 초기화 상태 플래그
        self.is_initialized = False
        
        # 데이터베이스 경로
        from path_utils import get_db_file_path
        self.db_path = get_db_file_path()
        
        # 리포트 저장 경로 (path_utils 사용)
        from path_utils import get_reports_dir
        self.reports_dir = get_reports_dir()
        
        try:
            self.init_ui()
            self.is_initialized = True
            print("실제 AI 리포트 위젯 초기화 완료")
        except Exception as e:
            print(f"실제 AI 리포트 위젯 초기화 실패: {e}")
            self.create_error_ui(str(e))
        
        # 초기 리포트 생성
        self.safe_after(1000, self.load_and_display_existing_reports)
        try:
            self.bind("<Destroy>", self._on_destroy, add="+")
        except Exception:
            pass
    
    def _color(self, key: str, fallback: str) -> str:
        try:
            if isinstance(self.colors, dict):
                value = self.colors.get(key)
                if value:
                    return value
        except Exception:
            pass
        return fallback

    def _card_frame(self, parent, **kwargs):
        """AI 커스텀·거래 통계와 같은 공통 카드 계층."""
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

    def _report_scroll(self, parent, **kwargs):
        kwargs.setdefault("fg_color", self._color("content_bg", "#0b1120"))
        kwargs.setdefault("border_color", self._color("border", "#273449"))
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("corner_radius", 10)
        kwargs.setdefault("scrollbar_button_color", self._color("surface_alt", "#172033"))
        kwargs.setdefault("scrollbar_button_hover_color", self._color("hover", "#334155"))
        return ctk.CTkScrollableFrame(parent, **kwargs)

    @staticmethod
    def _shade_color(hex_color: str, factor: float = 0.85) -> str:
        try:
            color = hex_color.lstrip('#')
            if len(color) != 6:
                return hex_color
            r = max(0, min(255, int(int(color[0:2], 16) * factor)))
            g = max(0, min(255, int(int(color[2:4], 16) * factor)))
            b = max(0, min(255, int(int(color[4:6], 16) * factor)))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color
    
    def safe_after(self, delay, func, *args, **kwargs):
        """안전한 after() 메서드 - 작업 추적"""
        try:
            if self._disposed or not self.winfo_exists():
                return None

            job_ref = {"id": None}

            def safe_callback():
                try:
                    if self._disposed or not self.winfo_exists():
                        return
                    func(*args, **kwargs)
                except tk.TclError:
                    return
                finally:
                    job_id = job_ref.get("id")
                    if job_id:
                        try:
                            self.after_jobs.remove(job_id)
                        except (ValueError, AttributeError):
                            pass

            job_id = self.after(delay, safe_callback)
            job_ref["id"] = job_id
            if not hasattr(self, 'after_jobs') or self.after_jobs is None:
                self.after_jobs = []
            self.after_jobs.append(job_id)
            return job_id
        except tk.TclError:
            return None
        except Exception:
            return None
    
    def cleanup_after_jobs(self):
        """모든 after() 작업 정리"""
        for job_id in list(getattr(self, 'after_jobs', []) or []):
            try:
                self.after_cancel(job_id)
            except:
                pass
        if hasattr(self, 'after_jobs') and self.after_jobs is not None:
            self.after_jobs.clear()

    def _on_destroy(self, event=None):
        try:
            if event is not None and getattr(event, 'widget', None) is not self:
                return
        except Exception:
            pass
        self._disposed = True
        self.cleanup_after_jobs()

    def destroy(self):
        self._disposed = True
        self.cleanup_after_jobs()
        return super().destroy()

    def _is_textbox_alive(self, widget) -> bool:
        try:
            return bool(widget is not None and widget.winfo_exists() and self.winfo_exists() and not self._disposed)
        except Exception:
            return False

    def _safe_set_text(self, widget, text: str):
        try:
            if not self._is_textbox_alive(widget):
                return
            widget.delete("1.0", "end")
            widget.insert("1.0", text)
        except tk.TclError:
            return
        
    def init_ui(self):
        """UI 초기화 (공간 최적화)"""
        # 메인 레이아웃
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # 탭에만 가중치 부여 (3번째 행)
        
        # 제목 (공간 최적화)
        title_label = ctk.CTkLabel(
            self,
            text="AI 자동 리포트",
            font=ctk.CTkFont(size=16, weight="bold")  # 크기 줄임
        )
        title_label.grid(row=0, column=0, pady=(5, 2))  # 여백 줄임
        
        # 설명 (공간 최적화)
        desc_label = ctk.CTkLabel(
            self,
            text="AI가 실제 거래 데이터를 분석하여 생성하는 리포트입니다.",
            font=ctk.CTkFont(size=10),  # 크기 줄임
            text_color=self._color('text_secondary', '#7f8c8d')
        )
        desc_label.grid(row=1, column=0, pady=(0, 5))  # 여백 줄임
        
        # 리포트 탭 위젯 (스크롤 추가)
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
        # 하단 상태바 공간 확보: 아래쪽 여백을 0으로
        self.report_tabs.grid(row=2, column=0, sticky="nsew", padx=5, pady=(2, 0))
        
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
        
        # 실시간 분석 탭 (최근 1시간)
        self.realtime_tab = self.report_tabs.add("실시간")
        self.realtime_tab.configure(fg_color=self._color("content_bg", "#0b1120"))
        self.create_realtime_analysis_tab()

        # 실행 품질 메트릭 탭 (바이낸스/unified 고급 계층)
        self.quality_tab = self.report_tabs.add("실행 품질")
        self.quality_tab.configure(fg_color=self._color("content_bg", "#0b1120"))
        self.create_execution_quality_tab()
        
        # 버튼/필터 프레임 (공간 최적화)
        button_frame = self._card_frame(self)
        # 버튼 프레임 하단 여백도 0으로 줄여 전체 높이를 축소
        button_frame.grid(row=3, column=0, pady=(5, 0), sticky="ew")  # 여백 줄임
        button_frame.grid_columnconfigure(0, weight=0)
        button_frame.grid_columnconfigure(1, weight=0)
        button_frame.grid_columnconfigure(2, weight=1)
        button_frame.grid_columnconfigure(3, weight=0)
        button_frame.grid_columnconfigure(4, weight=0)

        # 거래소 필터
        self.exchange_filter_var = ctk.StringVar(value="전체")
        try:
            options = self._load_exchange_options()
        except Exception:
            options = ["전체", "binance", "bybit", "okx", "bitget", "upbit", "bithumb"]
        if "전체" not in options:
            options = ["전체"] + options
        ctk.CTkLabel(button_frame, text="거래소:").grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")
        exchange_menu = ctk.CTkOptionMenu(
            button_frame,
            values=options,
            variable=self.exchange_filter_var,
            command=lambda _: self.auto_generate_reports(),
            fg_color=self._color("secondary", "#263a57"),
            button_color=self._color("primary", "#2563eb"),
            button_hover_color=self._color("primary_hover", "#1d4ed8"),
        )
        exchange_menu.grid(row=0, column=1, padx=(0, 10), pady=5, sticky="w")
        
        # 새로고침 버튼
        refresh_btn = ctk.CTkButton(
            button_frame,
            text="전체 새로고침",
            command=self.auto_generate_reports,
            width=120,
            height=30,  # 높이 줄임
            fg_color=self._color("primary", "#2563eb"),
            hover_color=self._color("primary_hover", "#1d4ed8"),
        )
        refresh_btn.grid(row=0, column=3, padx=5)
        
        # 실시간 분석 버튼
        danger_base = self._color('danger', '#ef4444')
        danger_hover = self._shade_color(danger_base, 0.8)
        realtime_btn = ctk.CTkButton(
            button_frame,
            text="실시간 분석",
            command=self.generate_realtime_analysis,
            width=120,
            height=30,  # 높이 줄임
            fg_color=danger_base,
            hover_color=danger_hover
        )
        realtime_btn.grid(row=0, column=4, padx=5)

    def _load_exchange_options(self) -> List[str]:
        """성과 원장과 실제 체결 원장을 합쳐 거래소 옵션을 로드한다."""
        if not os.path.exists(self.db_path):
            return ["전체"]
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT exchange FROM trade_log WHERE exchange IS NOT NULL")
            rows = list(cursor.fetchall())
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='exchange_execution_log'"
            )
            if cursor.fetchone() is not None:
                cursor.execute(
                    "SELECT DISTINCT exchange FROM exchange_execution_log WHERE exchange IS NOT NULL"
                )
                rows.extend(cursor.fetchall())
            conn.close()
            exchanges = sorted({r[0] for r in rows if r and r[0]})
            return ["전체"] + exchanges if exchanges else ["전체"]
        except Exception:
            return ["전체"]
        
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
            text_color=self._color('danger', '#ef4444')
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
        
    def create_realtime_analysis_tab(self):
        """실시간 분석 탭 생성 (최근 1시간) - 스크롤 추가"""
        # 스크롤 가능한 메인 프레임
        scroll_button = self._color('surface', '#2b2b2b')
        scroll_button_hover = self._shade_color(scroll_button, 1.1)
        scrollable_frame = self._report_scroll(
            self.realtime_tab,
            scrollbar_button_color=scroll_button,
            scrollbar_button_hover_color=scroll_button_hover,
        )
        scrollable_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 요약 정보
        summary_frame = self._card_frame(scrollable_frame)
        summary_frame.pack(fill="x", padx=5, pady=5)
        
        # 요약 제목
        summary_title = ctk.CTkLabel(
            summary_frame,
            text="실시간 거래 분석 (최근 1시간)",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        summary_title.pack(pady=10)
        
        # 요약 정보 표시
        self.realtime_summary = self._report_textbox(
            summary_frame,
            height=120,
            font=ctk.CTkFont(size=12)
        )
        self.realtime_summary.pack(fill="x", padx=10, pady=5)
        
        # 장단점 분석
        analysis_frame = self._card_frame(scrollable_frame)
        analysis_frame.pack(fill="x", padx=5, pady=5)
        
        # 장단점 제목
        analysis_title = ctk.CTkLabel(
            analysis_frame,
            text="현재 거래 상황 분석",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        analysis_title.pack(pady=10)
        
        # 장점/단점 표시
        self.analysis_detail = self._report_textbox(
            analysis_frame,
            height=120,
            font=ctk.CTkFont(size=11)
        )
        self.analysis_detail.pack(fill="x", padx=10, pady=5)
        
        # AI 어시스턴트 전달 버튼
        ai_transfer_frame = self._card_frame(scrollable_frame)
        ai_transfer_frame.pack(fill="x", padx=5, pady=5)
        
        # AI 전달 제목
        transfer_title = ctk.CTkLabel(
            ai_transfer_frame,
            text="AI 어시스턴트 연동",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        transfer_title.pack(pady=10)
        
        # AI 전달 내용
        self.ai_transfer_content = self._report_textbox(
            ai_transfer_frame,
            height=100,
            font=ctk.CTkFont(size=11)
        )
        self.ai_transfer_content.pack(fill="x", padx=10, pady=5)
        
        # AI 전달 버튼
        accent_base = self._color('accent', '#8b5cf6')
        accent_hover = self._shade_color(accent_base, 0.8)
        transfer_btn = ctk.CTkButton(
            ai_transfer_frame,
            text="AI 어시스턴트에 전달",
            command=self.transfer_to_ai_assistant,
            width=200,
            height=40,
            fg_color=accent_base,
            hover_color=accent_hover
        )
        transfer_btn.pack(pady=10)
        
    def create_execution_quality_tab(self):
        """실행 품질 메트릭 탭 — 바이낸스/unified cycle_execution_metrics 노출"""
        scrollable_frame = self._report_scroll(self.quality_tab)
        scrollable_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # 타이틀
        ctk.CTkLabel(
            scrollable_frame,
            text="실행 품질 메트릭 (고급 매매 계층)",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(10, 4))
        ctk.CTkLabel(
            scrollable_frame,
            text="최근 사이클의 quality_score, 슬리피지, 이상 감지 결과를 표시합니다.",
            font=ctk.CTkFont(size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
        ).pack(pady=(0, 10))

        # 새로고침 버튼
        ctk.CTkButton(
            scrollable_frame,
            text="메트릭 갱신",
            width=130, height=30,
            command=self._refresh_quality_metrics,
            fg_color=self._color("primary", "#2563eb"),
            hover_color=self._color("primary_hover", "#1d4ed8"),
        ).pack(pady=(0, 10))

        # 메트릭 표시 텍스트박스
        self._quality_textbox = self._report_textbox(
            scrollable_frame,
            height=420,
            font=ctk.CTkFont(family="Courier New", size=12),
        )
        self._quality_textbox.pack(fill="both", expand=True, padx=5, pady=5)

        # 초기 로드
        self.safe_after(500, self._refresh_quality_metrics)

    def _refresh_quality_metrics(self):
        """cycle_execution_metrics 를 trader/unified_trader 에서 읽어 표시"""
        try:
            lines: list = []
            lines.append("=" * 60)
            lines.append("  실행 품질 메트릭 — 최근 트레이딩 사이클")
            lines.append("=" * 60)

            loaded = False

            # ── Binance 경로 ──────────────────────────────────────
            try:
                from trading.trader import BinanceTrader
                import gc
                for obj in gc.get_objects():
                    if isinstance(obj, BinanceTrader) and hasattr(obj, "cycle_execution_metrics"):
                        metrics = obj.cycle_execution_metrics
                        if metrics:
                            lines.append("\n[Binance] cycle_execution_metrics")
                            lines.append(self._fmt_metrics(metrics))
                            loaded = True
                        break
            except Exception:
                pass

            # ── Unified (CCXT) 경로 ───────────────────────────────
            try:
                from trading.unified_trader import UnifiedTrader
                import gc
                for obj in gc.get_objects():
                    if isinstance(obj, UnifiedTrader) and hasattr(obj, "cycle_execution_metrics"):
                        metrics = obj.cycle_execution_metrics
                        if metrics:
                            lines.append("\n[Unified CCXT] cycle_execution_metrics")
                            lines.append(self._fmt_metrics(metrics))
                            loaded = True
                        break
            except Exception:
                pass

            # ── 로그 파일에서 최근 메트릭 보완 ──────────────────────
            log_metrics = self._load_metrics_from_log()
            if log_metrics:
                lines.append("\n[로그 파일 최근 품질 이벤트]")
                lines.extend(log_metrics)
                loaded = True

            if not loaded:
                lines.append("\n⏳ 아직 수집된 사이클 메트릭이 없습니다.")
                lines.append("  자동매매를 실행하면 여기에 데이터가 표시됩니다.")

            lines.append("\n" + "=" * 60)
            lines.append(f"  업데이트: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append("=" * 60)

            text = "\n".join(lines)
            if hasattr(self, "_quality_textbox"):
                self._quality_textbox.configure(state="normal")
                self._quality_textbox.delete("0.0", "end")
                self._quality_textbox.insert("0.0", text)
                self._quality_textbox.configure(state="disabled")
        except Exception as exc:
            if hasattr(self, "_quality_textbox"):
                self._quality_textbox.configure(state="normal")
                self._quality_textbox.delete("0.0", "end")
                self._quality_textbox.insert("0.0", f"메트릭 로드 오류: {exc}")
                self._quality_textbox.configure(state="disabled")

    @staticmethod
    def _fmt_metrics(metrics: dict) -> str:
        """cycle_execution_metrics dict를 읽기 좋게 포맷"""
        import json as _json
        lines = []
        for cycle_key, data in sorted(metrics.items(), key=lambda x: str(x[0]), reverse=True)[:10]:
            lines.append(f"\n  ▸ 사이클: {cycle_key}")
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, float):
                        lines.append(f"    {k}: {v:.4f}")
                    elif isinstance(v, (list, dict)):
                        lines.append(f"    {k}: {_json.dumps(v, ensure_ascii=False)[:120]}")
                    else:
                        lines.append(f"    {k}: {v}")
            else:
                lines.append(f"    {data}")
        return "\n".join(lines) if lines else "  (데이터 없음)"

    def _load_metrics_from_log(self) -> list:
        """logs/ 디렉터리에서 quality_score/anomaly 키워드가 포함된 최근 10줄 읽기"""
        try:
            import glob, os
            log_dir = __import__('pathlib').Path(__file__).resolve().parent.parent.parent / "data" / "logs"
            if not log_dir.exists():
                return []
            log_files = sorted(glob.glob(str(log_dir / "*.log")), key=os.path.getmtime, reverse=True)[:3]
            hits = []
            for lf in log_files:
                with open(lf, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if any(kw in line for kw in ("quality_score", "anomaly", "rollback", "ops_auto")):
                            hits.append(line.rstrip())
                            if len(hits) >= 20:
                                break
                if len(hits) >= 20:
                    break
            return hits[-10:] if hits else []
        except Exception:
            return []

    def auto_generate_reports(self):
        """자동 리포트 생성"""
        try:
            if not self.is_initialized:
                return

            # 비동기로 리포트 생성 (UI 블록 방지)
            self.safe_after(100, self._generate_reports_async)
            
        except Exception as e:
            print(f"AI 리포트 생성 오류: {e}")
    
    def _generate_reports_async(self):
        """비동기 리포트 생성"""
        try:
            # 오늘 리포트 생성
            self._generate_today_report()
            
            # 주간 리포트 생성 (7개 오늘 리포트 종합)
            self._generate_weekly_report()
            
            # 월간 리포트 생성 (4개 주간 리포트 종합)
            self._generate_monthly_report()
            
            print("실제 AI 리포트 생성 완료")
            
        except Exception as e:
            print(f"AI 리포트 생성 오류: {e}")
    
    def generate_realtime_analysis(self):
        """실시간 분석 생성 (최근 1시간)"""
        try:
            if not self.is_initialized:
                return
                
            # 비동기로 실시간 분석 생성
            self.safe_after(100, self._generate_realtime_analysis_async)
            
        except Exception as e:
            print(f"실시간 분석 생성 오류: {e}")
    
    def _generate_realtime_analysis_async(self):
        """비동기 실시간 분석 생성"""
        try:
            # 최근 1시간 거래 데이터 조회
            recent_data = self._get_recent_trading_data(1)  # 1시간
            operating_metrics_text = self._format_operating_metrics(recent_data)
            
            if not recent_data:
                # 데이터가 없으면 기본 메시지
                summary_text = (
                    "실시간 거래 분석 (최근 1시간)\n\n"
                    "최근 1시간 거래 데이터가 없습니다.\n\n"
                    f"{operating_metrics_text}\n\n"
                    "비용 영향:\n"
                    "- 거래 데이터가 없어 비용 지표를 계산할 수 없습니다.\n\n"
                    "AI 분석:\n"
                    "- 거래가 없어 분석할 데이터가 부족합니다.\n"
                    "- 시장 상황을 모니터링하고 거래 기회를 기다려주세요."
                )
                analysis_text = "현재 거래 상황 분석\n\n분석할 거래 데이터가 없습니다."
                ai_content = "현재 거래 데이터가 없어 AI 어시스턴트에게 전달할 분석 내용이 없습니다."
            else:
                # 실제 데이터 기반 실시간 분석
                analysis_result = self._analyze_realtime_performance(recent_data)
                
                summary_text = f"""실시간 거래 분석 (최근 1시간)

분석 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
총 거래 수: {analysis_result['total_trades']}건
수익 거래: {analysis_result['profitable_trades']}건
승률: {analysis_result['win_rate']:.1f}%
통화별 총 손익:
{analysis_result['pnl_text']}

{operating_metrics_text}

통화별 누적 Fee:
{analysis_result['fee_text']}
동일통화 Fee 대비 PnL 영향도:
{analysis_result['fee_impact_text']}
- 환율 정보 없이 KRW·USDT 등 서로 다른 통화는 합산하지 않습니다.

AI 실시간 분석:
{analysis_result['ai_summary']}
"""
                
                analysis_text = f"""현재 거래 상황 분석

장점:
{analysis_result['strengths']}

단점:
{analysis_result['weaknesses']}

주의사항:
{analysis_result['warnings']}

개선 제안:
{analysis_result['improvements']}
"""
                
                ai_content = f"""실시간 거래 분석 결과를 AI 어시스턴트에게 전달합니다:

분석 요약:
- 최근 1시간 거래 수: {analysis_result['total_trades']}건
- 승률: {analysis_result['win_rate']:.1f}%
- 통화별 총 손익:
{analysis_result['pnl_text']}
{operating_metrics_text}
- 통화별 누적 Fee:
{analysis_result['fee_text']}
- 동일통화 Fee 대비 PnL 영향도:
{analysis_result['fee_impact_text']}

주요 장점:
{analysis_result['strengths']}

개선이 필요한 부분:
{analysis_result['weaknesses']}

구체적인 개선 방안:
{analysis_result['improvements']}

위 분석을 바탕으로 거래 전략을 개선해주세요."""
            
            # UI 업데이트
            self._safe_set_text(self.realtime_summary, summary_text)
            self._safe_set_text(self.analysis_detail, analysis_text)
            self._safe_set_text(self.ai_transfer_content, ai_content)
            
            print("실시간 분석 생성 완료")
            
        except Exception as e:
            print(f"실시간 분석 생성 오류: {e}")
    
    def _get_recent_trading_data(self, hours: int = 1) -> List[Dict]:
        """최근 N시간 거래 데이터 조회"""
        try:
            if not os.path.exists(self.db_path):
                return []
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 최근 N시간 거래 데이터 조회 (청산 시점을 기준으로 최근 거래만 조회)
            base_sql = """
                SELECT * FROM trade_log 
                WHERE exit_time >= datetime('now', '-{} hours')
                AND exit_time IS NOT NULL
                AND LOWER(COALESCE(reason, '')) != 'binance_import'
            """.format(hours)
            params: List[Any] = []
            selected = (self.exchange_filter_var.get() if hasattr(self, 'exchange_filter_var') else '전체')
            if selected and selected != "전체":
                base_sql += " AND exchange = ?"
                params.append(selected)
            base_sql += " ORDER BY exit_time DESC"
            cursor.execute(base_sql, tuple(params))
            
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            
            data = []
            for row in rows:
                data.append(dict(zip(columns, row)))
            
            conn.close()
            return data
            
        except Exception as e:
            print(f"최근 거래 데이터 조회 오류: {e}")
            return []
    
    def _analyze_realtime_performance(self, trades: List[Dict]) -> Dict:
        """실시간 거래 성과 분석"""
        if not trades:
            return {
                'total_trades': 0,
                'profitable_trades': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'total_fees': 0.0,
                'avg_fee': 0.0,
                'fee_impact_percent': 0.0,
                'avg_trade_duration': 0.0,
                'ai_summary': "거래 데이터가 없어 분석할 수 없습니다.",
                'strengths': "분석할 데이터가 없습니다.",
                'weaknesses': "분석할 데이터가 없습니다.",
                'warnings': "특별한 주의사항이 없습니다.",
                'improvements': "더 많은 거래 데이터가 필요합니다."
            }
        
        total_trades = len(trades)
        profitable_trades = len([t for t in trades if t['pnl'] > 0])
        win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
        financials = self._format_currency_financials(trades)
        # 기존 분석 함수는 단일 통화일 때만 금액 스칼라를 받는다.
        total_pnl = (
            next(iter(financials['by_currency'].values()))['pnl']
            if not financials['mixed_currency'] and financials['by_currency']
            else 0.0
        )
        
        # 거래 시간 분석
        trade_durations = []
        for trade in trades:
            if trade['entry_time'] and trade['exit_time']:
                try:
                    entry_time = datetime.fromisoformat(trade['entry_time'].replace('Z', '+00:00'))
                    exit_time = datetime.fromisoformat(trade['exit_time'].replace('Z', '+00:00'))
                    duration = (exit_time - entry_time).total_seconds() / 60  # 분 단위
                    trade_durations.append(duration)
                except:
                    pass
        
        avg_trade_duration = sum(trade_durations) / len(trade_durations) if trade_durations else 0
        
        # AI 분석
        ai_summary = self._generate_realtime_ai_summary(trades, win_rate, total_pnl, avg_trade_duration)
        strengths = self._identify_strengths(trades, win_rate, total_pnl)
        weaknesses = self._identify_weaknesses(trades, win_rate, total_pnl)
        warnings = self._generate_warnings(trades, win_rate, total_pnl)
        improvements = self._suggest_improvements(trades, win_rate, total_pnl)
        if financials['mixed_currency']:
            ai_summary = (
                "KRW·USDT 등 결제통화가 함께 있어 금액 합산 평가는 보류합니다. "
                "승률과 통화별 손익을 각각 확인하세요."
            )
            warnings = (warnings + "\n• 서로 다른 통화의 금액은 환율 없이 비교할 수 없습니다.").strip()
        
        return {
            'total_trades': total_trades,
            'profitable_trades': profitable_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'pnl_by_currency': financials['by_currency'],
            'pnl_text': financials['pnl_text'],
            'fee_text': financials['fee_text'],
            'fee_impact_text': financials['fee_impact_text'],
            'mixed_currency': financials['mixed_currency'],
            'avg_trade_duration': avg_trade_duration,
            'ai_summary': ai_summary,
            'strengths': strengths,
            'weaknesses': weaknesses,
            'warnings': warnings,
            'improvements': improvements
        }
    
    def _generate_realtime_ai_summary(self, trades: List[Dict], win_rate: float, total_pnl: float, avg_duration: float) -> str:
        """실시간 AI 요약 생성"""
        if win_rate >= 80:
            return f"매우 우수한 성과! 승률 {win_rate:.1f}%는 전문가 수준입니다. 현재 전략을 유지하세요."
        elif win_rate >= 60:
            return f"좋은 성과를 보이고 있습니다. 승률 {win_rate:.1f}%는 시장 평균을 상회합니다."
        elif win_rate >= 40:
            return f"보통 수준의 성과입니다. 승률 {win_rate:.1f}%는 개선의 여지가 있습니다."
        else:
            return f"성과 개선이 필요합니다. 승률 {win_rate:.1f}%는 시장 평균 이하입니다."
    
    def _identify_strengths(self, trades: List[Dict], win_rate: float, total_pnl: float) -> str:
        """장점 식별"""
        strengths = []
        
        if win_rate >= 70:
            strengths.append(f"• 높은 승률 ({win_rate:.1f}%) - 안정적인 거래 전략")
        
        if total_pnl > 0:
            strengths.append(f"• 수익성 확보 - 총 {total_pnl:.2f} USDT 수익")
        
        # 거래 패턴 분석
        if len(trades) >= 3:
            recent_pnl = [t['pnl'] for t in trades[:3]]
            if all(pnl > 0 for pnl in recent_pnl):
                strengths.append("• 최근 거래 연속 수익 - 좋은 추세")
        
        # 레버리지 분석
        avg_leverage = sum(t['leverage'] for t in trades) / len(trades) if trades else 0
        if 1 <= avg_leverage <= 5:
            strengths.append(f"• 적절한 레버리지 사용 ({avg_leverage:.1f}배) - 리스크 관리 양호")
        
        if not strengths:
            strengths.append("• 분석할 데이터가 부족합니다.")
        
        return "\n".join(strengths)
    
    def _identify_weaknesses(self, trades: List[Dict], win_rate: float, total_pnl: float) -> str:
        """단점 식별"""
        weaknesses = []
        
        if win_rate < 50:
            weaknesses.append(f"• 낮은 승률 ({win_rate:.1f}%) - 전략 재검토 필요")
        
        if total_pnl < 0:
            weaknesses.append(f"• 손실 발생 ({total_pnl:.2f} USDT) - 리스크 관리 강화 필요")
        
        # 거래 빈도 분석
        if len(trades) > 10:
            weaknesses.append("• 과도한 거래 빈도 - 선별적 거래 필요")
        elif len(trades) < 2:
            weaknesses.append("• 거래 빈도 부족 - 기회 포착 능력 개선 필요")
        
        # 손실 거래 분석
        losing_trades = [t for t in trades if t['pnl'] < 0]
        if losing_trades:
            avg_loss = sum(t['pnl'] for t in losing_trades) / len(losing_trades)
            if avg_loss < -10:  # 평균 손실이 10 USDT 이상
                weaknesses.append(f"• 큰 손실 거래 ({avg_loss:.2f} USDT) - 손절 기준 강화 필요")
        
        if not weaknesses:
            weaknesses.append("• 현재 특별한 단점이 발견되지 않았습니다.")
        
        return "\n".join(weaknesses)
    
    def _generate_warnings(self, trades: List[Dict], win_rate: float, total_pnl: float) -> str:
        """주의사항 생성"""
        warnings = []
        
        if win_rate < 30:
            warnings.append("• 매우 낮은 승률 - 거래 중단 고려")
        
        if total_pnl < -50:
            warnings.append("• 큰 손실 누적 - 리스크 관리 긴급 점검 필요")
        
        # 연속 손실 분석
        if len(trades) >= 3:
            recent_trades = trades[:3]
            if all(t['pnl'] < 0 for t in recent_trades):
                warnings.append("• 연속 손실 거래 - 전략 재검토 필요")
        
        # 레버리지 경고
        high_leverage_trades = [t for t in trades if t['leverage'] > 10]
        if high_leverage_trades:
            warnings.append("• 고레버리지 거래 감지 - 리스크 주의")
        
        if not warnings:
            warnings.append("• 현재 특별한 주의사항이 없습니다.")
        
        return "\n".join(warnings)
    
    def _suggest_improvements(self, trades: List[Dict], win_rate: float, total_pnl: float) -> str:
        """개선 제안 생성"""
        improvements = []
        
        if win_rate < 50:
            improvements.append("• 기술적 분석 강화 - 더 정확한 진입/청산 시점 파악")
            improvements.append("• 손절 기준 명확화 - 손실 제한 규칙 설정")
        
        if total_pnl < 0:
            improvements.append("• 리스크 관리 개선 - 포지션 크기 조정")
            improvements.append("• 시장 상황 분석 강화 - 불리한 시장에서 거래 중단")
        
        # 거래 빈도 개선
        if len(trades) > 10:
            improvements.append("• 거래 빈도 조절 - 고품질 신호만 거래")
        elif len(trades) < 2:
            improvements.append("• 신호 감지 능력 향상 - 더 많은 거래 기회 포착")
        
        # 레버리지 개선
        avg_leverage = sum(t['leverage'] for t in trades) / len(trades) if trades else 0
        if avg_leverage > 10:
            improvements.append("• 레버리지 감소 - 안정성 우선")
        elif avg_leverage < 1:
            improvements.append("• 레버리지 활용도 개선 - 수익성 향상")
        
        if not improvements:
            improvements.append("• 현재 전략을 유지하면서 세부 조정 고려")
        
        return "\n".join(improvements)
    
    def transfer_to_ai_assistant(self):
        """AI 어시스턴트에 분석 결과 전달"""
        try:
            # AI 전달 내용 가져오기
            ai_content = self.ai_transfer_content.get("1.0", "end-1c")
            
            if not ai_content.strip():
                print("AI 어시스턴트에 전달할 내용이 없습니다.")
                return
            
            # AI 어시스턴트 탭으로 전환 (실제 구현에서는 대시보드의 AI 어시스턴트 탭으로 이동)
            print("AI 어시스턴트에 분석 결과 전달:")
            print("=" * 50)
            print(ai_content)
            print("=" * 50)
            
            # 성공 메시지 표시
            self._safe_set_text(
                self.ai_transfer_content,
                "AI 어시스턴트에 성공적으로 전달되었습니다!\n\n위 분석 내용이 AI 어시스턴트 탭에 표시됩니다."
            )
            
            print("AI 어시스턴트 전달 완료")
            
        except Exception as e:
            print(f"AI 어시스턴트 전달 오류: {e}")
    
    def _get_trading_data(self, days: int = 1) -> List[Dict]:
        """최근 N일의 청산 거래 데이터 조회."""
        try:
            if not os.path.exists(self.db_path):
                return []
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 최근 N일 거래 데이터 조회
            base_sql = """
                SELECT * FROM trade_log 
                WHERE date(exit_time) >= date('now', 'localtime', '-{} days')
                AND exit_time IS NOT NULL
                AND LOWER(COALESCE(reason, '')) != 'binance_import'
            """.format(days)
            params: List[Any] = []
            selected = (self.exchange_filter_var.get() if hasattr(self, 'exchange_filter_var') else '전체')
            if selected and selected != "전체":
                base_sql += " AND exchange = ?"
                params.append(selected)
            base_sql += " ORDER BY entry_time DESC"
            cursor.execute(base_sql, tuple(params))
            
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            
            data = []
            for row in rows:
                data.append(dict(zip(columns, row)))
            
            conn.close()
            return data
            
        except Exception as e:
            print(f"거래 데이터 조회 오류: {e}")
            return []

    def _get_execution_data(self, days: int = 1) -> List[Dict[str, Any]]:
        """최근 실제 체결을 손익 성과와 분리해 조회한다."""
        try:
            from trading.execution_views import load_execution_data

            selected = (
                self.exchange_filter_var.get()
                if hasattr(self, 'exchange_filter_var') else '전체'
            )
            return load_execution_data(
                self.db_path,
                days=days,
                exchange=selected,
            )
        except Exception as exc:
            print(f"실제 체결 데이터 조회 오류: {exc}")
            return []

    @staticmethod
    def _format_execution_detail(executions: List[Dict[str, Any]], limit: int = 30) -> str:
        from trading.execution_views import format_execution_detail

        return format_execution_detail(executions, limit=limit)

    def _format_operating_metrics(self, trades: List[Dict]) -> str:
        """리포트에 공통으로 표시할 통화별 체결금액·보유시간 문구."""
        metrics = calculate_trade_operating_metrics(trades)
        notionals = metrics.get("notional_by_currency", {}) or {}
        amount_lines = [
            f"- USDT: {format_notional('USDT', notionals.get('USDT', 0.0))}",
            f"- KRW: {format_notional('KRW', notionals.get('KRW', 0.0))}",
        ]
        for currency in sorted(notionals):
            if currency not in {"USDT", "KRW"}:
                amount_lines.append(
                    f"- {currency}: {format_notional(currency, notionals[currency])}"
                )

        closed_count = int(metrics.get("closed_count") or 0)
        valid_count = int(metrics.get("valid_hold_count") or 0)
        hold_text = format_hold_duration(metrics.get("avg_hold_minutes"))
        coverage_text = (
            f"유효 {valid_count:,}/{closed_count:,}건"
            if closed_count
            else "청산 기록 없음"
        )
        return (
            "실제 체결금액:\n"
            + "\n".join(amount_lines)
            + f"\n평균 보유시간: {hold_text} ({coverage_text})\n"
            + "- 체결금액은 기록된 체결가×체결수량 기준이며 통화별로 분리됩니다."
        )

    @staticmethod
    def _format_currency_financials(
        trades: List[Dict], *, period_divisor: Optional[float] = None
    ) -> Dict[str, Any]:
        """환산되지 않은 통화를 더하지 않고 화면용 손익·비용 문구를 만든다."""
        metrics = calculate_currency_financial_metrics(trades)
        pnl_lines = []
        avg_lines = []
        for currency in metrics["currencies"]:
            bucket = metrics["by_currency"][currency]
            divisor = period_divisor if period_divisor else max(bucket["trades"], 1)
            pnl_lines.append(
                f"- {format_currency_amount(currency, bucket['pnl'], signed=True)}"
            )
            avg_lines.append(
                f"- {format_currency_amount(currency, bucket['pnl'] / divisor, signed=True)}"
            )

        fee_lines = [
            f"- {format_currency_amount(currency, amount)}"
            for currency, amount in sorted(metrics["fees_by_currency"].items())
        ]
        impact_lines = []
        for currency, fee in sorted(metrics["fees_by_currency"].items()):
            pnl = float(metrics["by_currency"].get(currency, {}).get("pnl", 0.0) or 0.0)
            if abs(pnl) > 0:
                impact_lines.append(f"- {currency}: {fee / abs(pnl) * 100.0:.2f}%")

        pnl_values = [
            float(metrics["by_currency"][currency]["pnl"])
            for currency in metrics["currencies"]
        ]
        if pnl_values and all(value >= 0 for value in pnl_values) and any(value > 0 for value in pnl_values):
            pnl_state = "positive"
        elif pnl_values and all(value <= 0 for value in pnl_values) and any(value < 0 for value in pnl_values):
            pnl_state = "negative"
        elif pnl_values:
            pnl_state = "mixed"
        else:
            pnl_state = "empty"

        return {
            **metrics,
            "pnl_text": "\n".join(pnl_lines) if pnl_lines else "- 데이터 없음",
            "average_text": "\n".join(avg_lines) if avg_lines else "- 데이터 없음",
            "fee_text": "\n".join(fee_lines) if fee_lines else "- 기록된 Fee 없음",
            "fee_impact_text": "\n".join(impact_lines) if impact_lines else "- 계산 가능한 동일통화 PnL 없음",
            "pnl_state": pnl_state,
        }
    
    def _generate_today_report(self):
        """오늘 리포트 생성"""
        try:
            # 오늘 거래 데이터 조회
            today_data = self._get_trading_data(1)
            execution_data = self._get_execution_data(1)
            execution_count = len(execution_data)
            execution_detail = self._format_execution_detail(execution_data)
            
            if not today_data:
                # 데이터가 없으면 기본 메시지
                operating_metrics_text = self._format_operating_metrics([])
                summary_text = (
                    "오늘 거래 요약\n\n"
                    f"실제 체결: {execution_count}건\n"
                    "청산 완료 성과: 0건\n\n"
                    "실제 체결은 확인되지만 청산 완료 거래가 없어 승률·PnL은 아직 계산하지 않습니다.\n\n"
                    f"{operating_metrics_text}\n\n"
                    "비용 영향:\n"
                    "- 거래 데이터가 없어 비용 지표를 계산할 수 없습니다.\n\n"
                    "AI 분석:\n"
                    "- 거래가 없어 분석할 데이터가 부족합니다.\n"
                    "- 시장 상황을 모니터링하고 거래 기회를 기다려주세요."
                )
                detail_text = execution_detail
            else:
                # 실제 데이터 기반 분석
                total_trades = len(today_data)
                profitable_trades = len([t for t in today_data if t['pnl'] > 0])
                win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
                financials = self._format_currency_financials(today_data)
                operating_metrics_text = self._format_operating_metrics(today_data)
                
                # AI 분석
                ai_analysis = self._analyze_trading_performance(today_data)
                
                summary_text = f"""오늘 거래 요약 ({datetime.now().strftime('%Y-%m-%d')})

실제 체결: {execution_count}건
청산 완료 성과: {total_trades}건
수익 거래: {profitable_trades}건
승률: {win_rate:.1f}%
통화별 총 손익:
{financials['pnl_text']}
통화별 거래당 평균 손익:
{financials['average_text']}

{operating_metrics_text}

통화별 누적 Fee:
{financials['fee_text']}
동일통화 Fee 대비 PnL 영향도:
{financials['fee_impact_text']}
- 환율 정보 없이 KRW·USDT 등 서로 다른 통화는 합산하지 않습니다.

AI 분석:
{ai_analysis['summary']}

추천사항:
{ai_analysis['recommendations']}
"""
                
                # 상세 내역
                detail_text = "상세 거래 내역\n\n"
                for i, trade in enumerate(today_data[:20]):  # 최근 20건만 표시
                    entry_time = trade['entry_time'][:16] if trade['entry_time'] else 'N/A'
                    symbol = trade['symbol']
                    side = trade['side']
                    pnl = trade['pnl']
                    pnl_percent = trade['pnl_percent']
                    currency = infer_quote_currency(
                        trade.get('exchange'), symbol, trade.get('pnl_currency')
                    )
                    detail_text += f"{i+1:2d}. {entry_time} | {symbol:16s} | {side:4s} | {pnl:8.2f} {currency} ({pnl_percent:6.2f}%)\n"
                
                if len(today_data) > 20:
                    detail_text += f"\n... 및 {len(today_data) - 20}건 더"
                detail_text += f"\n\n{execution_detail}"
            
            # UI 업데이트
            self._safe_set_text(self.today_summary, summary_text)
            self._safe_set_text(self.today_detail, detail_text)
            
            # 오늘 리포트 저장
            self._save_daily_report(summary_text, detail_text)
            
        except Exception as e:
            print(f"오늘 리포트 생성 오류: {e}")
    
    def _generate_weekly_report(self):
        """주간 리포트 생성 (7개 오늘 리포트 종합)"""
        try:
            self._refresh_champion_challenger_report()
            weekly_operating_metrics = self._format_operating_metrics(
                self._get_trading_data(7)
            )

            # 최근 7일의 일일 리포트 로드
            daily_reports = self._load_daily_reports(7)
            
            if not daily_reports:
                summary_text = (
                    "주간 거래 요약\n\n주간 리포트 데이터가 없습니다.\n\n"
                    f"{weekly_operating_metrics}"
                )
                detail_text = "주간 상세 분석\n\n분석할 데이터가 부족합니다."
            else:
                # 7개 일일 리포트를 AI가 종합 분석
                weekly_analysis = self._analyze_weekly_reports(daily_reports)
                
                summary_text = f"""주간 거래 요약 (최근 7일)

분석 기간: {weekly_analysis['start_date']} ~ {weekly_analysis['end_date']}
총 거래 수: {weekly_analysis['total_trades']}건
수익 거래: {weekly_analysis['profitable_trades']}건
평균 승률: {weekly_analysis['avg_win_rate']:.1f}%
통화별 총 손익:
{weekly_analysis['pnl_text']}
통화별 일평균 손익:
{weekly_analysis['average_text']}

{weekly_operating_metrics}

AI 주간 분석:
{weekly_analysis['ai_summary']}

주간 추천사항:
{weekly_analysis['recommendations']}
"""
                
                detail_text = f"""주간 상세 분석

일별 성과:
{weekly_analysis['daily_breakdown']}

최고 성과 코인:
{weekly_analysis['top_performers']}

주의사항:
{weekly_analysis['warnings']}
"""

            cc_section = self._build_champion_challenger_section()
            if cc_section:
                detail_text += f"\n\n{cc_section}"
            
            # UI 업데이트
            self._safe_set_text(self.weekly_summary, summary_text)
            self._safe_set_text(self.weekly_detail, detail_text)
            
            # 주간 리포트 저장
            self._save_weekly_report(summary_text, detail_text)
            
        except Exception as e:
            print(f"주간 리포트 생성 오류: {e}")

    def _refresh_champion_challenger_report(self):
        """주간 리포트 생성 전에 7일 챔피언-챌린저 산출물을 자동 갱신합니다."""
        try:
            from scripts.generate_champion_challenger_7d_report import generate_report

            generate_report(db_path=Path(self.db_path), out_dir=Path(self.reports_dir))
        except Exception as e:
            print(f"챔피언-챌린저 자동 생성 실패: {e}")

    def _build_champion_challenger_section(self) -> str:
        """외부 생성된 7일 챔피언-챌린저 리포트를 주간 상세에 병합합니다."""
        try:
            latest_file = os.path.join(self.reports_dir, 'champion_challenger_7d_latest.json')
            if not os.path.exists(latest_file):
                return (
                    "7일 챔피언-챌린저\n"
                    "- 파일 없음: scripts/generate_champion_challenger_7d_report.py 실행 후 반영됩니다."
                )

            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return format_champion_challenger_section(data)
        except Exception as e:
            return f"7일 챔피언-챌린저\n- 로드 오류: {e}"
    
    def _generate_monthly_report(self):
        """월간 리포트 생성 (4개 주간 리포트 종합)"""
        try:
            monthly_operating_metrics = self._format_operating_metrics(
                self._get_trading_data(30)
            )
            # 최근 4개의 주간 리포트 로드
            weekly_reports = self._load_weekly_reports(4)
            
            if not weekly_reports:
                summary_text = (
                    "월간 거래 요약\n\n월간 리포트 데이터가 없습니다.\n\n"
                    f"{monthly_operating_metrics}"
                )
                detail_text = "월간 상세 분석\n\n분석할 데이터가 부족합니다."
            else:
                # 4개 주간 리포트를 AI가 종합 분석
                monthly_analysis = self._analyze_monthly_reports(weekly_reports)
                
                summary_text = f"""월간 거래 요약 (최근 30일)

분석 기간: {monthly_analysis['start_date']} ~ {monthly_analysis['end_date']}
총 거래 수: {monthly_analysis['total_trades']}건
수익 거래: {monthly_analysis['profitable_trades']}건
평균 승률: {monthly_analysis['avg_win_rate']:.1f}%
통화별 총 손익:
{monthly_analysis['pnl_text']}
통화별 주평균 손익:
{monthly_analysis['average_text']}

{monthly_operating_metrics}

AI 월간 분석:
{monthly_analysis['ai_summary']}

월간 추천사항:
{monthly_analysis['recommendations']}
"""
                
                detail_text = f"""월간 상세 분석

주별 성과:
{monthly_analysis['weekly_breakdown']}

성과 분석:
{monthly_analysis['performance_analysis']}

향후 전망:
{monthly_analysis['future_outlook']}
"""
            
            # UI 업데이트
            self._safe_set_text(self.monthly_summary, summary_text)
            self._safe_set_text(self.monthly_detail, detail_text)
            
            # 월간 리포트 저장
            self._save_monthly_report(summary_text, detail_text)
            
        except Exception as e:
            print(f"월간 리포트 생성 오류: {e}")
    
    def _analyze_trading_performance(self, trades: List[Dict]) -> Dict:
        """거래 성과 AI 분석"""
        if not trades:
            return {
                'summary': "거래 데이터가 없어 분석할 수 없습니다.",
                'recommendations': "시장 상황을 모니터링하고 거래 기회를 기다려주세요."
            }
        
        total_trades = len(trades)
        profitable_trades = len([t for t in trades if t['pnl'] > 0])
        win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
        financials = self._format_currency_financials(trades)
        
        # AI 분석 로직
        if win_rate >= 70:
            performance_level = "우수"
            summary = f"매우 좋은 성과를 보이고 있습니다. 승률 {win_rate:.1f}%는 전문가 수준입니다."
        elif win_rate >= 50:
            performance_level = "양호"
            summary = f"안정적인 성과를 보이고 있습니다. 승률 {win_rate:.1f}%는 시장 평균을 상회합니다."
        else:
            performance_level = "개선 필요"
            summary = f"성과 개선이 필요합니다. 승률 {win_rate:.1f}%는 시장 평균 이하입니다."
        
        # 추천사항
        recommendations = []
        if win_rate < 50:
            recommendations.append("거래 전략을 재검토하세요.")
            recommendations.append("리스크 관리 강화가 필요합니다.")
        elif win_rate >= 70:
            recommendations.append("현재 전략을 유지하세요.")
            recommendations.append("거래량을 점진적으로 늘려보세요.")
        else:
            recommendations.append("현재 전략을 유지하면서 세부 조정을 고려하세요.")
        
        if financials['pnl_state'] == 'negative':
            recommendations.append("손실을 최소화하는 방향으로 전략을 수정하세요.")
        elif financials['pnl_state'] == 'mixed':
            recommendations.append("결제통화별 손익을 분리해 전략을 검토하세요.")
        
        return {
            'summary': summary,
            'recommendations': "\n".join(f"- {rec}" for rec in recommendations)
        }
    
    def _analyze_weekly_reports(self, daily_reports: List[Dict]) -> Dict:
        """주간 리포트 AI 분석 (최근 7일, DB 기반 집계)"""
        try:
            start_dt = (datetime.now() - timedelta(days=6)).date()  # 오늘 포함 7일
            end_dt = datetime.now().date()

            # DB에서 최근 7일 거래 불러오기
            trades = self._get_trading_data(7)

            total_trades = len(trades)
            profitable_trades = len([t for t in trades if t.get('pnl', 0) > 0])
            win_rate = (profitable_trades / total_trades * 100) if total_trades else 0.0
            financials = self._format_currency_financials(trades, period_divisor=7.0)

            # 일별 브레이크다운
            by_day: Dict[str, Dict[str, Any]] = {}
            for t in trades:
                try:
                    day_key = t.get('entry_time', '')[:10]
                    if not day_key:
                        continue
                    d = by_day.setdefault(day_key, {'trades': 0, 'wins': 0, 'trades_data': []})
                    d['trades'] += 1
                    if t.get('pnl', 0) > 0:
                        d['wins'] += 1
                    d['trades_data'].append(t)
                except Exception:
                    pass

            # 날짜 순 정렬 및 요약 문자열 생성
            sorted_days = sorted(by_day.keys())
            daily_lines = []
            for day in sorted_days:
                d = by_day[day]
                wr = (d['wins'] / d['trades'] * 100) if d['trades'] else 0.0
                day_financials = self._format_currency_financials(d['trades_data'])
                compact_pnl = ", ".join(
                    format_currency_amount(currency, bucket['pnl'], signed=True)
                    for currency, bucket in day_financials['by_currency'].items()
                ) or "데이터 없음"
                daily_lines.append(f"- {day}: {d['trades']}건, 승률 {wr:.1f}%, PnL {compact_pnl}")
            daily_breakdown = "\n".join(daily_lines) if daily_lines else "최근 7일 거래 데이터가 없습니다."

            # 코인별 성과 (Top 5)
            by_symbol: Dict[tuple, float] = {}
            for t in trades:
                sym = t.get('symbol', 'N/A')
                currency = infer_quote_currency(t.get('exchange'), sym, t.get('pnl_currency'))
                key = (currency, sym)
                by_symbol[key] = by_symbol.get(key, 0.0) + float(t.get('pnl', 0.0))
            top_lines = []
            for currency in sorted({key[0] for key in by_symbol}):
                candidates = [
                    (symbol, pnl) for (item_currency, symbol), pnl in by_symbol.items()
                    if item_currency == currency
                ]
                for symbol, pnl in sorted(candidates, key=lambda item: item[1], reverse=True)[:5]:
                    top_lines.append(f"- [{currency}] {symbol}: {pnl:+.2f} {currency}")
            top_performers = "\n".join(top_lines) if top_lines else "데이터 없음"

            # 간단 AI 요약/권고/경고
            pnl_state = financials['pnl_state']
            if win_rate >= 65 and pnl_state == 'positive':
                ai_summary = "안정적인 우상향 흐름입니다. 현재 전략을 유지하세요."
                recommendations = "- 동일 전략 유지\n- 관측된 강세 코인에 비중 확대 검토"
            elif pnl_state == 'positive':
                ai_summary = "수익이 발생했지만 변동성이 있습니다. 리스크 관리에 유의하세요."
                recommendations = "- 손절/익절 규칙 재점검\n- 승률 낮은 코인 비중 축소"
            elif pnl_state == 'mixed':
                ai_summary = "결제통화별 손익 방향이 다릅니다. 환산 없이 통화별로 분리해 평가합니다."
                recommendations = "- KRW·USDT 전략을 각각 복기\n- 환율 기준을 정하기 전 통합 손익 판단 금지"
            else:
                ai_summary = "손실 구간입니다. 신호 품질과 거래 빈도를 조정하세요."
                recommendations = "- 거래 필터 강화(추세·거래량)\n- 포지션 크기 축소 및 복기"

            warnings = []
            if win_rate < 40:
                warnings.append("낮은 승률 - 전략 재검토 필요")
            if pnl_state == 'negative':
                warnings.append("통화별 손실 누적 - 리스크 관리 강화 필요")
            warnings_text = "\n".join(f"- {w}" for w in warnings) if warnings else "특별한 주의사항이 없습니다."

            return {
                'start_date': start_dt.strftime('%Y-%m-%d'),
                'end_date': end_dt.strftime('%Y-%m-%d'),
                'total_trades': total_trades,
                'profitable_trades': profitable_trades,
                'avg_win_rate': win_rate,
                'pnl_by_currency': financials['by_currency'],
                'pnl_text': financials['pnl_text'],
                'average_text': financials['average_text'],
                'mixed_currency': financials['mixed_currency'],
                'ai_summary': ai_summary,
                'recommendations': recommendations,
                'daily_breakdown': daily_breakdown,
                'top_performers': top_performers,
                'warnings': warnings_text
            }
        except Exception as e:
            print(f"주간 분석 오류: {e}")
            return {
                'start_date': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                'end_date': datetime.now().strftime('%Y-%m-%d'),
                'total_trades': 0,
                'profitable_trades': 0,
                'avg_win_rate': 0.0,
                'pnl_by_currency': {},
                'pnl_text': "- 데이터 없음",
                'average_text': "- 데이터 없음",
                'mixed_currency': False,
                'ai_summary': "주간 분석 중 오류가 발생했습니다.",
                'recommendations': "시스템 로그를 확인해주세요.",
                'daily_breakdown': "데이터를 불러올 수 없습니다.",
                'top_performers': "데이터 없음",
                'warnings': "데이터 없음"
            }
    
    def _analyze_monthly_reports(self, weekly_reports: List[Dict]) -> Dict:
        """월간 리포트 AI 분석 (최근 30일, DB 기반 집계)"""
        try:
            start_dt = (datetime.now() - timedelta(days=29)).date()  # 오늘 포함 30일
            end_dt = datetime.now().date()

            trades = self._get_trading_data(30)

            total_trades = len(trades)
            profitable_trades = len([t for t in trades if t.get('pnl', 0) > 0])
            win_rate = (profitable_trades / total_trades * 100) if total_trades else 0.0
            financials = self._format_currency_financials(
                trades, period_divisor=max(1.0, len({
                    (t.get('entry_time') or '')[:7] for t in trades if t.get('entry_time')
                }))
            )

            # 주별 브레이크다운 (ISO 주차)
            by_week: Dict[str, Dict[str, Any]] = {}
            for t in trades:
                try:
                    et = t.get('entry_time')
                    if not et:
                        continue
                    dt = datetime.fromisoformat(et.replace('Z', '+00:00'))
                    week_key = f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
                    w = by_week.setdefault(week_key, {'trades': 0, 'wins': 0, 'trades_data': []})
                    w['trades'] += 1
                    if t.get('pnl', 0) > 0:
                        w['wins'] += 1
                    w['trades_data'].append(t)
                except Exception:
                    pass

            sorted_weeks = sorted(by_week.keys())
            weekly_lines = []
            for wk in sorted_weeks:
                w = by_week[wk]
                wr = (w['wins'] / w['trades'] * 100) if w['trades'] else 0.0
                week_financials = self._format_currency_financials(w['trades_data'])
                compact_pnl = ", ".join(
                    format_currency_amount(currency, bucket['pnl'], signed=True)
                    for currency, bucket in week_financials['by_currency'].items()
                ) or "데이터 없음"
                weekly_lines.append(f"- {wk}: {w['trades']}건, 승률 {wr:.1f}%, PnL {compact_pnl}")
            weekly_breakdown = "\n".join(weekly_lines) if weekly_lines else "최근 4주 거래 데이터가 없습니다."

            # 성과 분석/전망
            pnl_state = financials['pnl_state']
            if pnl_state == 'positive' and win_rate >= 60:
                performance_analysis = "전반적으로 안정적인 수익 구간입니다. 손실 주는 주의 포지션을 축소하세요."
                future_outlook = "시장 변동성에 주의하면서 현재 전략을 유지하는 것이 유리합니다."
            elif pnl_state == 'positive':
                performance_analysis = "수익은 있으나 변동성이 큽니다. 리스크 관리가 핵심입니다."
                future_outlook = "보수적 접근과 신호 품질 필터 강화가 권장됩니다."
            elif pnl_state == 'mixed':
                performance_analysis = "결제통화별 손익 방향이 달라 환산 없는 합산 평가는 보류합니다."
                future_outlook = "KRW·USDT 등 결제통화별 전략과 위험 한도를 각각 검토하세요."
            else:
                performance_analysis = "손실 구간입니다. 진입 기준과 손절 규칙을 재정의하세요."
                future_outlook = "거래 빈도를 낮추고 확실한 추세에서만 참여하세요."

            # 요약/권고
            if win_rate >= 65 and pnl_state == 'positive':
                ai_summary = "월간 기준으로 견조한 성과입니다. 규율 있는 운영을 지속하세요."
                recommendations = "- 우세 신호 위주로 집중\n- 과도한 레버리지 금지\n- 손익비 1:2 이상 유지"
            elif pnl_state == 'positive':
                ai_summary = "긍정적인 성과지만 하방 리스크가 존재합니다."
                recommendations = "- 손절폭 축소\n- 포지션 크기 단계적 조절\n- 연속 손실 시 쿨다운 적용"
            elif pnl_state == 'mixed':
                ai_summary = "통화별 성과가 엇갈립니다. 통화별 분리 결과만 제공합니다."
                recommendations = "- 결제통화별 성과 검토\n- 환율 기준 없는 합산 금지\n- 거래소별 위험 한도 분리"
            else:
                ai_summary = "월간 손실입니다. 전략 복기와 개선이 필요합니다."
                recommendations = "- 거래 필터 재구성\n- 승률 낮은 패턴 제외\n- 연습 모드(페이퍼)로 재검증"

            return {
                'start_date': start_dt.strftime('%Y-%m-%d'),
                'end_date': end_dt.strftime('%Y-%m-%d'),
                'total_trades': total_trades,
                'profitable_trades': profitable_trades,
                'avg_win_rate': win_rate,
                'pnl_by_currency': financials['by_currency'],
                'pnl_text': financials['pnl_text'],
                'average_text': self._format_currency_financials(
                    trades, period_divisor=max(len(sorted_weeks), 1)
                )['average_text'],
                'mixed_currency': financials['mixed_currency'],
                'ai_summary': ai_summary,
                'recommendations': recommendations,
                'weekly_breakdown': weekly_breakdown,
                'performance_analysis': performance_analysis,
                'future_outlook': future_outlook
            }
        except Exception as e:
            print(f"월간 분석 오류: {e}")
            return {
                'start_date': (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
                'end_date': datetime.now().strftime('%Y-%m-%d'),
                'total_trades': 0,
                'profitable_trades': 0,
                'avg_win_rate': 0.0,
                'pnl_by_currency': {},
                'pnl_text': "- 데이터 없음",
                'average_text': "- 데이터 없음",
                'mixed_currency': False,
                'ai_summary': "월간 분석 중 오류가 발생했습니다.",
                'recommendations': "시스템 로그를 확인해주세요.",
                'weekly_breakdown': "데이터를 불러올 수 없습니다.",
                'performance_analysis': "데이터 없음",
                'future_outlook': "데이터 없음"
            }
    
    def _save_daily_report(self, summary: str, detail: str):
        """일일 리포트 저장"""
        try:
            date_str = datetime.now().strftime('%Y-%m-%d')
            report_data = {
                'date': date_str,
                'summary': summary,
                'detail': detail,
                'created_at': datetime.now().isoformat()
            }
            
            report_file = os.path.join(self.reports_dir, f'daily_report_{date_str}.json')
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)

            emit_kpi_event(
                event_type='report_file_saved',
                category='report',
                asset_class='crypto',
                status='success',
                source='noahai_client_report_widget',
                metric_value=float(len(detail or '')),
                metadata={
                    'report_scope': 'daily',
                    'report_date': date_str,
                    'file_name': f'daily_report_{date_str}.json',
                },
            )
                
        except Exception as e:
            print(f"일일 리포트 저장 오류: {e}")
            emit_kpi_event(
                event_type='report_file_saved',
                category='report',
                asset_class='crypto',
                status='failed',
                source='noahai_client_report_widget',
                metadata={
                    'report_scope': 'daily',
                    'reason': str(e),
                },
            )
    
    def _load_daily_reports(self, days: int) -> List[Dict]:
        """일일 리포트 로드"""
        try:
            reports = []
            for i in range(days):
                date_str = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                report_file = os.path.join(self.reports_dir, f'daily_report_{date_str}.json')
                
                if os.path.exists(report_file):
                    with open(report_file, 'r', encoding='utf-8') as f:
                        reports.append(json.load(f))
            
            return reports
        except Exception as e:
            print(f"일일 리포트 로드 오류: {e}")
            return []
    
    def _save_weekly_report(self, summary: str, detail: str):
        """주간 리포트 저장"""
        try:
            week_str = datetime.now().strftime('%Y-W%U')
            report_data = {
                'week': week_str,
                'summary': summary,
                'detail': detail,
                'created_at': datetime.now().isoformat()
            }
            
            report_file = os.path.join(self.reports_dir, f'weekly_report_{week_str}.json')
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)

            emit_kpi_event(
                event_type='report_file_saved',
                category='report',
                asset_class='crypto',
                status='success',
                source='noahai_client_report_widget',
                metric_value=float(len(detail or '')),
                metadata={
                    'report_scope': 'weekly',
                    'report_week': week_str,
                    'file_name': f'weekly_report_{week_str}.json',
                },
            )
                
        except Exception as e:
            print(f"주간 리포트 저장 오류: {e}")
            emit_kpi_event(
                event_type='report_file_saved',
                category='report',
                asset_class='crypto',
                status='failed',
                source='noahai_client_report_widget',
                metadata={
                    'report_scope': 'weekly',
                    'reason': str(e),
                },
            )
    
    def _load_weekly_reports(self, weeks: int) -> List[Dict]:
        """주간 리포트 로드"""
        try:
            reports = []
            for i in range(weeks):
                week_str = (datetime.now() - timedelta(weeks=i)).strftime('%Y-W%U')
                report_file = os.path.join(self.reports_dir, f'weekly_report_{week_str}.json')
                
                if os.path.exists(report_file):
                    with open(report_file, 'r', encoding='utf-8') as f:
                        reports.append(json.load(f))
            
            return reports
        except Exception as e:
            print(f"주간 리포트 로드 오류: {e}")
            return []
    
    def _save_monthly_report(self, summary: str, detail: str):
        """월간 리포트 저장"""
        try:
            month_str = datetime.now().strftime('%Y-%m')
            report_data = {
                'month': month_str,
                'summary': summary,
                'detail': detail,
                'created_at': datetime.now().isoformat()
            }
            
            report_file = os.path.join(self.reports_dir, f'monthly_report_{month_str}.json')
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)

            emit_kpi_event(
                event_type='report_file_saved',
                category='report',
                asset_class='crypto',
                status='success',
                source='noahai_client_report_widget',
                metric_value=float(len(detail or '')),
                metadata={
                    'report_scope': 'monthly',
                    'report_month': month_str,
                    'file_name': f'monthly_report_{month_str}.json',
                },
            )
                
        except Exception as e:
            print(f"월간 리포트 저장 오류: {e}")
            emit_kpi_event(
                event_type='report_file_saved',
                category='report',
                asset_class='crypto',
                status='failed',
                source='noahai_client_report_widget',
                metadata={
                    'report_scope': 'monthly',
                    'reason': str(e),
                },
            )
            
            
    def load_and_display_existing_reports(self):
        """기존 리포트 파일 로드 및 UI 표시"""
        try:
            if not self.is_initialized:
                return
            
            # 1. 오늘 리포트 로드 및 표시
            self._load_and_display_today_report()
            
            # 2. 주간 리포트 로드 및 표시  
            self._load_and_display_weekly_report()
            
            # 3. 월간 리포트 로드 및 표시
            self._load_and_display_monthly_report()
            
            print("기존 AI 리포트 로드 완료")
            
            # 4. 새로운 리포트 생성도 실행
            self.safe_after(2000, self.auto_generate_reports)
            
        except Exception as e:
            print(f"기존 리포트 로드 오류: {e}")
            # 로드 실패 시에도 새 리포트는 생성
            self.safe_after(2000, self.auto_generate_reports)
    
    def _load_and_display_today_report(self):
        """오늘 리포트 파일 로드 및 UI 표시"""
        try:
            today_str = datetime.now().strftime('%Y-%m-%d')
            report_file = os.path.join(self.reports_dir, f'daily_report_{today_str}.json')
            
            if os.path.exists(report_file):
                with open(report_file, 'r', encoding='utf-8') as f:
                    report_data = json.load(f)
                
                # UI 업데이트
                self._safe_set_text(self.today_summary, report_data.get('summary', ''))
                self._safe_set_text(self.today_detail, report_data.get('detail', ''))
                
                print(f"오늘 리포트 로드됨: {report_file}")
            else:
                print(f"오늘 리포트 파일 없음: {report_file}")
                
        except Exception as e:
            print(f"오늘 리포트 로드 오류: {e}")
    
    def _load_and_display_weekly_report(self):
        """주간 리포트 파일 로드 및 UI 표시"""
        try:
            week_str = datetime.now().strftime('%Y-W%U')
            report_file = os.path.join(self.reports_dir, f'weekly_report_{week_str}.json')
            
            if os.path.exists(report_file):
                with open(report_file, 'r', encoding='utf-8') as f:
                    report_data = json.load(f)
                
                # UI 업데이트
                self._safe_set_text(self.weekly_summary, report_data.get('summary', ''))
                self._safe_set_text(self.weekly_detail, report_data.get('detail', ''))
                
                print(f"주간 리포트 로드됨: {report_file}")
            else:
                print(f"주간 리포트 파일 없음: {report_file}")
                
        except Exception as e:
            print(f"주간 리포트 로드 오류: {e}")
    
    def _load_and_display_monthly_report(self):
        """월간 리포트 파일 로드 및 UI 표시"""
        try:
            month_str = datetime.now().strftime('%Y-%m')
            report_file = os.path.join(self.reports_dir, f'monthly_report_{month_str}.json')
            
            if os.path.exists(report_file):
                with open(report_file, 'r', encoding='utf-8') as f:
                    report_data = json.load(f)
                
                # UI 업데이트 (월간 탭이 있다면)
                if hasattr(self, 'monthly_summary'):
                    self._safe_set_text(self.monthly_summary, report_data.get('summary', ''))
                
                if hasattr(self, 'monthly_detail'):
                    self._safe_set_text(self.monthly_detail, report_data.get('detail', ''))
                
                print(f"월간 리포트 로드됨: {report_file}")
            else:
                print(f"월간 리포트 파일 없음: {report_file}")
                
        except Exception as e:
            print(f"월간 리포트 로드 오류: {e}")
