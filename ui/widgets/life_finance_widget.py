#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
생활금융 대시보드 위젯 (CustomTkinter)
"""

import tkinter as tk
from tkinter import messagebox, simpledialog
from datetime import datetime, date, timedelta
import threading
import math
import customtkinter as ctk
from customtkinter import CTkScrollableFrame
import json
from typing import Optional, Dict, Any

from trading.life_finance import LifeFinanceManager, TransactionType, FinanceGoal, Transaction
from trading.life_finance_assistant import LifeFinanceAssistant, FinanceIntentParser
from trading.life_finance_products import FinanceProductAdvisor
try:
    from ui.widgets.ai_voice_module import AIVoiceModule, VoiceConfig
except Exception:  # optional dependency path
    AIVoiceModule = None  # type: ignore
    VoiceConfig = None  # type: ignore
from config.settings import load_settings
from ui.visual_system import style_tabview
import asyncio
import logging


class LifeFinanceWidget(ctk.CTkFrame):
    """생활금융 대시보드 위젯"""
    
    def __init__(self, parent, *args, **kwargs):
        kwargs.setdefault("fg_color", "#0b1120")
        super().__init__(parent, *args, **kwargs)

        settings = {}
        try:
            settings = load_settings() or {}
        except Exception:
            settings = {}

        self.manager = LifeFinanceManager(
            external_sync_dir=str(settings.get('life_finance_sync_dir', '') or '').strip() or None,
            backup_dir=str(settings.get('life_finance_backup_dir', '') or '').strip() or None,
        )
        self.assistant = LifeFinanceAssistant(self.manager)
        self.product_advisor = FinanceProductAdvisor()
        self.logger = logging.getLogger(__name__)
        self.voice_module = None
        self._is_destroying = False
        self._after_jobs = []
        self._init_voice_module()
        
        self._setup_ui()
        try:
            self._refresh_display()
        except Exception as e:
            self.logger.warning(f"생활금융 위젯 초기 데이터 로드 실패 (UI는 정상): {e}")

    def _init_voice_module(self):
        """음성 입력 모듈 초기화"""
        if AIVoiceModule is None or VoiceConfig is None:
            self.voice_module = None
            self.logger.info("음성 모듈 비활성화: ai_voice_module import 실패")
            return
        try:
            self.voice_module = AIVoiceModule(VoiceConfig(enabled=True, auto_tts=False, lang='ko-KR', rate=180))
        except Exception as e:
            self.logger.warning(f"음성 모듈 초기화 실패(생활금융 위젯은 계속 사용 가능): {e}")
            self.voice_module = None

    def _is_widget_alive(self) -> bool:
        """위젯이 아직 유효한 상태인지 확인"""
        try:
            return (not self._is_destroying) and bool(self.winfo_exists())
        except Exception:
            return False

    def _safe_after(self, delay: int, callback, *args):
        """파괴 이후 실행되지 않도록 보호된 after 래퍼"""
        if not self._is_widget_alive():
            return None

        def _runner():
            if not self._is_widget_alive():
                return
            try:
                callback(*args)
            except Exception:
                pass

        try:
            job_id = self.after(delay, _runner)
            self._after_jobs.append(job_id)
            return job_id
        except Exception:
            return None

    def _cancel_after_jobs(self):
        """등록된 after 작업 정리"""
        while self._after_jobs:
            job_id = self._after_jobs.pop()
            try:
                self.after_cancel(job_id)
            except Exception:
                pass

    def destroy(self):
        """위젯 파괴 시 예약 콜백을 먼저 정리"""
        self._is_destroying = True
        self._cancel_after_jobs()
        try:
            super().destroy()
        except Exception:
            pass
    
    def _setup_ui(self):
        """UI 설정"""
        # 메인 컨테이너
        main_container = ctk.CTkFrame(self, fg_color="#0b1120")
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 타이틀
        title_frame = ctk.CTkFrame(
            main_container,
            fg_color="#111827",
            border_width=1,
            border_color="#334155",
            corner_radius=12,
        )
        title_frame.pack(fill="x", pady=(0, 10))
        
        title = ctk.CTkLabel(
            title_frame,
            text="생활금융 관리",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color="#f9fafb",
        )
        title.pack(side="left", padx=14, pady=12)
        
        # 빠른 명령 버튼
        quick_buttons_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        quick_buttons_frame.pack(side="right", fill="x", padx=10, pady=8)
        
        buttons = [
            ("대시보드", self._show_dashboard),
            ("지출 추가", self._open_add_expense),
            ("수입 추가", self._open_add_income),
            ("목표 관리", self._show_goals),
            ("금융상품", self._show_products),
        ]
        
        for label, command in buttons:
            btn = ctk.CTkButton(
                quick_buttons_frame,
                text=label,
                command=command,
                width=100,
                height=35,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                fg_color="#9a5b08",
                hover_color="#b45309",
                text_color="#ffffff",
                corner_radius=9,
            )
            btn.pack(side="left", padx=5)
        
        # 탭뷰
        self.tabview = ctk.CTkTabview(main_container, height=600, fg_color="#0b1120")
        self.tabview.pack(fill="both", expand=True)
        style_tabview(
            self.tabview,
            accent="#b45309",
            bar_color="#2b2115",
            inactive="#43321f",
            text_color="#fef3c7",
            font_size=11,
            height=34,
        )
        
        # 탭 추가
        self.dashboard_tab = self.tabview.add("대시보드")
        self.transactions_tab = self.tabview.add("거래")
        self.goals_tab = self.tabview.add("목표")
        self.analysis_tab = self.tabview.add("분석")
        self.charts_tab = self.tabview.add("차트")
        self.products_tab = self.tabview.add("금융상품")
        self.assistant_tab = self.tabview.add("AI 어시스턴트")
        for tab in (
            self.dashboard_tab,
            self.transactions_tab,
            self.goals_tab,
            self.analysis_tab,
            self.charts_tab,
            self.products_tab,
            self.assistant_tab,
        ):
            tab.configure(fg_color="#0b1120")
        
        # 각 탭 콘텐츠 설정
        self._setup_dashboard_tab()
        self._setup_transactions_tab()
        self._setup_goals_tab()
        self._setup_analysis_tab()
        self._setup_charts_tab()
        self._setup_products_tab()
        self._setup_assistant_tab()
    
    def _setup_dashboard_tab(self):
        """대시보드 탭"""
        self.dashboard_scroll = CTkScrollableFrame(self.dashboard_tab, fg_color="#0b1120")
        self.dashboard_scroll.pack(fill="both", expand=True, padx=10, pady=10)
    
    def _setup_transactions_tab(self):
        """거래 탭"""
        toolbar = ctk.CTkFrame(self.transactions_tab, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkButton(
            toolbar,
            text="+ 지출 추가",
            command=self._open_add_expense,
            width=120
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            toolbar,
            text="+ 수입 추가",
            command=self._open_add_income,
            width=120
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            toolbar,
            text="새로고침",
            command=self._refresh_display,
            width=120
        ).pack(side="left", padx=5)
        
        self.transactions_scroll = CTkScrollableFrame(self.transactions_tab, fg_color="#0b1120")
        self.transactions_scroll.pack(fill="both", expand=True, padx=10, pady=10)
    
    def _setup_goals_tab(self):
        """목표 탭"""
        toolbar = ctk.CTkFrame(self.goals_tab, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkButton(
            toolbar,
            text="+ 목표 추가",
            command=self._open_add_goal,
            width=120
        ).pack(side="left", padx=5)
        
        self.goals_scroll = CTkScrollableFrame(self.goals_tab, fg_color="#0b1120")
        self.goals_scroll.pack(fill="both", expand=True, padx=10, pady=10)
    
    def _setup_analysis_tab(self):
        """분석 탭"""
        self.analysis_scroll = CTkScrollableFrame(self.analysis_tab, fg_color="#0b1120")
        self.analysis_scroll.pack(fill="both", expand=True, padx=10, pady=10)

    def _setup_charts_tab(self):
        """고급 차트 탭"""
        self.charts_scroll = CTkScrollableFrame(self.charts_tab, fg_color="#0b1120")
        self.charts_scroll.pack(fill="both", expand=True, padx=10, pady=10)

    def _setup_products_tab(self):
        """금융상품 비교 탭 — Phase 3 전용 UI (커스텀 입력 + 시각적 비교 테이블)"""
        # ── 신용도/위험도 프로필 섹션 (Phase 1 신규) ────────────────
        profile_frame = ctk.CTkFrame(self.products_tab, fg_color="#1e293b", corner_radius=12)
        profile_frame.pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkLabel(
            profile_frame,
            text="개인화 프로필",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#f1f5f9",
        ).pack(anchor="w", padx=14, pady=(12, 8))

        profile_input_frame = ctk.CTkFrame(profile_frame, fg_color="transparent")
        profile_input_frame.pack(fill="x", padx=14, pady=(0, 12))

        # 신용도 선택
        ctk.CTkLabel(
            profile_input_frame,
            text="신용도",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        ).pack(side="left", padx=(0, 5))
        
        self._credit_score_var = tk.StringVar(value="보통 (650~750)")
        self._credit_combo = ctk.CTkComboBox(
            profile_input_frame,
            values=["좋음 (750~900)", "보통 (650~750)", "낮음 (~650)"],
            variable=self._credit_score_var,
            state="readonly",
            width=150,
            command=self._on_profile_changed
        )
        self._credit_combo.pack(side="left", padx=(0, 20))

        # 위험도 선택
        ctk.CTkLabel(
            profile_input_frame,
            text="위험도",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        ).pack(side="left", padx=(0, 5))
        
        self._risk_level_var = tk.StringVar(value="보수형")
        self._risk_combo = ctk.CTkComboBox(
            profile_input_frame,
            values=["회피형", "보수형", "공격형"],
            variable=self._risk_level_var,
            state="readonly",
            width=120,
            command=self._on_profile_changed
        )
        self._risk_combo.pack(side="left", padx=(0, 5))

        # ── 상단 조건 입력 패널 ────────────────────────────────────
        input_panel = ctk.CTkFrame(self.products_tab, fg_color="#0f172a", corner_radius=12)
        input_panel.pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkLabel(
            input_panel,
            text="금융상품 비교 조건 설정",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#f1f5f9",
        ).grid(row=0, column=0, columnspan=6, padx=14, pady=(12, 8), sticky="w")

        # 대출 조건
        ctk.CTkLabel(input_panel, text="대출 금액(만원)", font=ctk.CTkFont(size=11),
                     text_color="#94a3b8").grid(row=1, column=0, padx=(14, 4), sticky="w")
        self._loan_amount_entry = ctk.CTkEntry(input_panel, width=110, placeholder_text="예: 10000")
        self._loan_amount_entry.insert(0, "10000")
        self._loan_amount_entry.grid(row=1, column=1, padx=(0, 10), pady=4, sticky="w")

        ctk.CTkLabel(input_panel, text="대출 기간(개월)", font=ctk.CTkFont(size=11),
                     text_color="#94a3b8").grid(row=1, column=2, padx=(0, 4), sticky="w")
        self._loan_term_entry = ctk.CTkEntry(input_panel, width=80, placeholder_text="예: 24")
        self._loan_term_entry.insert(0, "24")
        self._loan_term_entry.grid(row=1, column=3, padx=(0, 10), pady=4, sticky="w")

        # 보험 조건
        ctk.CTkLabel(input_panel, text="보험 월 예산(원)", font=ctk.CTkFont(size=11),
                     text_color="#94a3b8").grid(row=2, column=0, padx=(14, 4), sticky="w")
        self._insurance_budget_entry = ctk.CTkEntry(input_panel, width=110, placeholder_text="예: 70000")
        self._insurance_budget_entry.insert(0, "70000")
        self._insurance_budget_entry.grid(row=2, column=1, padx=(0, 10), pady=4, sticky="w")

        ctk.CTkLabel(input_panel, text="보험 종류", font=ctk.CTkFont(size=11),
                     text_color="#94a3b8").grid(row=2, column=2, padx=(0, 4), sticky="w")
        self._insurance_cat_var = tk.StringVar(value="전체")
        ctk.CTkOptionMenu(
            input_panel, values=["전체", "종합", "건강", "가족"],
            variable=self._insurance_cat_var, width=90,
        ).grid(row=2, column=3, padx=(0, 10), pady=4, sticky="w")

        # 예적금 조건
        ctk.CTkLabel(input_panel, text="원금(만원)", font=ctk.CTkFont(size=11),
                     text_color="#94a3b8").grid(row=3, column=0, padx=(14, 4), sticky="w")
        self._savings_principal_entry = ctk.CTkEntry(input_panel, width=110, placeholder_text="예: 500")
        self._savings_principal_entry.insert(0, "500")
        self._savings_principal_entry.grid(row=3, column=1, padx=(0, 10), pady=4, sticky="w")

        ctk.CTkLabel(input_panel, text="기간(개월)", font=ctk.CTkFont(size=11),
                     text_color="#94a3b8").grid(row=3, column=2, padx=(0, 4), sticky="w")
        self._savings_term_entry = ctk.CTkEntry(input_panel, width=80, placeholder_text="예: 12")
        self._savings_term_entry.insert(0, "12")
        self._savings_term_entry.grid(row=3, column=3, padx=(0, 10), pady=4, sticky="w")

        # 조회 버튼들
        btn_frame = ctk.CTkFrame(input_panel, fg_color="transparent")
        btn_frame.grid(row=1, column=4, rowspan=3, padx=(10, 14), pady=4, sticky="ns")

        ctk.CTkButton(btn_frame, text="대출 비교", width=110,
                      command=self._run_loan_compare,
                      fg_color="#1d4ed8", hover_color="#1e40af").pack(pady=3)
        ctk.CTkButton(btn_frame, text="보험 비교", width=110,
                      command=self._run_insurance_compare,
                      fg_color="#065f46", hover_color="#064e3b").pack(pady=3)
        ctk.CTkButton(btn_frame, text="예적금 비교", width=110,
                      command=self._run_savings_compare,
                      fg_color="#7c3aed", hover_color="#6d28d9").pack(pady=3)
        ctk.CTkButton(btn_frame, text="전체 비교", width=110,
                      command=self._run_all_compare,
                      fg_color="#374151", hover_color="#1f2937").pack(pady=3)

        input_panel.grid_columnconfigure(4, weight=0)

        # ── 카탈로그 상태 바 ──────────────────────────────────────
        catalog_bar = ctk.CTkFrame(self.products_tab, fg_color="#1e293b", corner_radius=8)
        catalog_bar.pack(fill="x", padx=12, pady=(0, 4))

        self._catalog_status_label = ctk.CTkLabel(
            catalog_bar,
            text="상품 정보 확인 중...",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
            justify="left",
        )
        self._catalog_status_label.pack(side="left", padx=10, pady=6)

        ctk.CTkButton(
            catalog_bar,
            text="상품 정보 다시 읽기",
            width=110, height=26,
            fg_color="#1f2937", hover_color="#374151",
            font=ctk.CTkFont(size=11),
            command=self._manual_catalog_refresh,
        ).pack(side="right", padx=10, pady=4)

        # 상태 초기 업데이트
        self._safe_after(300, self._update_catalog_status_label)

        # ── 결과 스크롤 영역 ──────────────────────────────────────
        self.products_scroll = CTkScrollableFrame(self.products_tab, fg_color="#0b1120")
        self.products_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # 초기 전체 비교 실행
        self._safe_after(200, self._run_all_compare)
    
    def _setup_assistant_tab(self):
        """AI 어시스턴트 탭"""
        # 입력창
        input_frame = ctk.CTkFrame(self.assistant_tab, fg_color="transparent")
        input_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(input_frame, text="명령어 또는 질문:").pack(anchor="w", pady=(0, 5))
        
        self.assistant_input = ctk.CTkEntry(
            input_frame,
            placeholder_text="예: '카페에서 5천원 썼어' 또는 '이번 달 지출이 얼마야?'",
            height=40
        )
        self.assistant_input.pack(fill="x", pady=(0, 10))
        self.assistant_input.bind("<Return>", lambda e: self._process_assistant_command())
        
        # 버튼
        btn_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        btn_frame.pack(fill="x")
        
        ctk.CTkButton(
            btn_frame,
            text="전송",
            command=self._process_assistant_command,
            width=100
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            btn_frame,
            text="음성 입력",
            command=self._voice_input,
            width=100
        ).pack(side="left", padx=5)
        
        # 대화 이력
        ctk.CTkLabel(self.assistant_tab, text="대화 이력:").pack(anchor="w", padx=10, pady=(10, 5))
        
        self.assistant_chat = CTkScrollableFrame(self.assistant_tab)
        self.assistant_chat.pack(fill="both", expand=True, padx=10, pady=10)
    
    # ========== 대시보드 ==========
    
    def _show_dashboard(self):
        """대시보드 표시"""
        self._refresh_display()
        self.tabview.set("대시보드")

    def _show_goals(self):
        """목표 탭 표시"""
        self._update_goals()
        self.tabview.set("목표")

    def _show_products(self):
        """금융상품 탭 표시"""
        self._update_products()
        self.tabview.set("금융상품")
    
    def _refresh_display(self):
        """디스플레이 새로고침"""
        if not self._is_widget_alive():
            return
        self._update_dashboard()
        self._update_transactions()
        self._update_goals()
        self._update_analysis()
        self._update_charts()
        self._update_products()
    
    def _update_dashboard(self):
        """대시보드 업데이트"""
        # 기존 위젯 제거
        for widget in self.dashboard_scroll.winfo_children():
            widget.destroy()
        
        summary = self.manager.get_dashboard_summary()
        
        # 이번 달 요약
        this_month = summary['this_month']
        
        # 1. 월간 요약 카드
        summary_frame = ctk.CTkFrame(
            self.dashboard_scroll,
            fg_color="#111827",
            border_color="#273449",
            border_width=1,
            corner_radius=12,
        )
        summary_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(
            summary_frame,
            text=f"{this_month['date_str']} 월간 재무 요약",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#f9fafb",
        ).pack(anchor="w", padx=14, pady=(12, 8))
        
        # 3x2 그리드
        grid_frame = ctk.CTkFrame(summary_frame, fg_color="transparent")
        grid_frame.pack(fill="x", padx=9, pady=(0, 9))
        
        metrics = [
            ("수입", f"{this_month['total_income']:,}원"),
            ("지출", f"{this_month['total_expense']:,}원"),
            ("저축", f"{this_month['net_savings']:,}원"),
            ("저축률", f"{this_month['savings_rate']:.1f}%"),
            ("누적 수입", f"{summary['cumulative']['total_income']:,}원"),
            ("순 자산", f"{summary['cumulative']['net_position']:,}원"),
        ]
        
        for i, (label, value) in enumerate(metrics):
            row = i // 3
            col = i % 3
            
            card = ctk.CTkFrame(
                grid_frame,
                fg_color="#172033",
                border_color="#334155",
                border_width=1,
                corner_radius=10,
            )
            card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            
            ctk.CTkLabel(
                card,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#9ca3af",
            ).pack(anchor="w", padx=10, pady=(10, 2))
            ctk.CTkLabel(
                card,
                text=value,
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                text_color="#f9fafb",
            ).pack(anchor="w", padx=10, pady=(0, 10))
        
        grid_frame.columnconfigure((0, 1, 2), weight=1)
        
        # 2. 비교
        if summary['comparison']:
            comparison_frame = ctk.CTkFrame(self.dashboard_scroll)
            comparison_frame.pack(fill="x", padx=10, pady=10)
            
            ctk.CTkLabel(
                comparison_frame,
                text="이전 달과 비교",
                font=("Helvetica", 14, "bold")
            ).pack(anchor="w", pady=(0, 10))
            
            comp_data = summary['comparison']
            comparisons = [
                ("수입 변화", comp_data['income_change']),
                ("지출 변화", comp_data['expense_change']),
                ("저축 변화", comp_data['savings_change']),
            ]
            
            for label, value in comparisons:
                sign = "" if value > 0 else ""
                color = "green" if value > 0 else "red"
                ctk.CTkLabel(
                    comparison_frame,
                    text=f"{sign} {label}: {value:+,}원",
                    font=("Helvetica", 12)
                ).pack(anchor="w")
        
        # 3. 목표 진행
        goals = summary['goals']
        if goals['active_count'] > 0:
            goals_frame = ctk.CTkFrame(self.dashboard_scroll)
            goals_frame.pack(fill="x", padx=10, pady=10)
            
            ctk.CTkLabel(
                goals_frame,
                text=f"목표 진행 ({goals['active_count']}개 진행 중)",
                font=("Helvetica", 14, "bold")
            ).pack(anchor="w", pady=(0, 10))
            
            for goal in goals['top_goals']:
                self._draw_goal_card(goals_frame, goal)

        # 4. 알림
        alerts = summary.get('alerts', [])
        if alerts:
            alert_frame = ctk.CTkFrame(self.dashboard_scroll)
            alert_frame.pack(fill="x", padx=10, pady=10)

            ctk.CTkLabel(
                alert_frame,
                text="금융 알림",
                font=("Helvetica", 14, "bold")
            ).pack(anchor="w", pady=(0, 8))

            for alert in alerts[:5]:
                level = alert.get('level', 'info')
                icon = "" if level == 'critical' else "" if level == 'warning' else "ℹ"
                ctk.CTkLabel(
                    alert_frame,
                    text=f"{icon} {alert.get('title', '')}: {alert.get('message', '')}",
                    font=("Helvetica", 11),
                    wraplength=900,
                    justify="left"
                ).pack(anchor="w", pady=2)
    
    def _draw_goal_card(self, parent, goal_data):
        """목표 카드 그리기"""
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.pack(fill="x", pady=5)
        
        # 목표명
        ctk.CTkLabel(
            card,
            text=goal_data['name'],
            font=("Helvetica", 12, "bold")
        ).pack(anchor="w", padx=10, pady=(10, 5))
        
        # 진행바
        progress_frame = ctk.CTkFrame(card)
        progress_frame.pack(fill="x", padx=10, pady=5)
        
        # 진행 바
        progress = ctk.CTkProgressBar(progress_frame)
        progress.set(goal_data['progress_rate'] / 100)
        progress.pack(fill="x")
        
        # 진행률 텍스트
        ctk.CTkLabel(
            card,
            text=f"{goal_data['current_amount']:,}원 / {goal_data['target_amount']:,}원 "
                 f"({goal_data['progress_rate']:.1f}%)",
            font=("Helvetica", 10)
        ).pack(anchor="w", padx=10)
        
        # 남은 금액
        if goal_data['remaining_amount'] > 0:
            ctk.CTkLabel(
                card,
                text=f"남은 금액: {goal_data['remaining_amount']:,}원",
                font=("Helvetica", 10)
            ).pack(anchor="w", padx=10, pady=(0, 10))
    
    def _update_transactions(self):
        """거래 목록 업데이트"""
        for widget in self.transactions_scroll.winfo_children():
            widget.destroy()
        
        # 최근 7일
        start_date = date.today() - timedelta(days=7)
        txs = self.manager.get_transactions(start_date=start_date)
        
        if not txs:
            ctk.CTkLabel(
                self.transactions_scroll,
                text="거래 내역이 없습니다."
            ).pack(pady=20)
            return
        
        for tx in txs[:20]:  # 최근 20개
            self._draw_transaction_row(tx)
    
    def _draw_transaction_row(self, tx: Transaction):
        """거래 행 그리기"""
        row = ctk.CTkFrame(self.transactions_scroll, fg_color="transparent")
        row.pack(fill="x", pady=5)
        
        # 아이콘 및 정보
        icon = "" if tx.type == TransactionType.INCOME else ""
        sign = "+" if tx.type == TransactionType.INCOME else "-"
        
        info_frame = ctk.CTkFrame(row, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True)
        
        ctk.CTkLabel(
            info_frame,
            text=f"{icon} {tx.date} | {tx.category}",
            font=("Helvetica", 11, "bold")
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            info_frame,
            text=f"{tx.description}",
            font=("Helvetica", 10),
            text_color="gray"
        ).pack(anchor="w")
        
        # 금액
        amount_color = "green" if tx.type == TransactionType.INCOME else "red"
        ctk.CTkLabel(
            row,
            text=f"{sign}{tx.amount:,}원",
            font=("Helvetica", 12, "bold"),
            text_color=amount_color
        ).pack(side="right", padx=10)
        
        # 삭제 버튼
        def delete_tx():
            if messagebox.askyesno("확인", "삭제하시겠습니까?"):
                self.manager.delete_transaction(tx.id)
                self._refresh_display()
        
        ctk.CTkButton(
            row,
            text="삭제",
            width=48,
            height=30,
            command=delete_tx,
            fg_color="red",
            text_color="white"
        ).pack(side="right", padx=5)
    
    def _update_goals(self):
        """목표 목록 업데이트"""
        for widget in self.goals_scroll.winfo_children():
            widget.destroy()
        
        goals = self.manager.get_goals()
        
        # 완료되지 않은 목표
        active_goals = [g for g in goals if not g.is_completed]
        
        if not active_goals:
            ctk.CTkLabel(
                self.goals_scroll,
                text="활성 목표가 없습니다. 새로운 목표를 추가해보세요."
            ).pack(pady=20)
            return
        
        for goal in active_goals:
            self._draw_goal_widget(goal)
    
    def _draw_goal_widget(self, goal: FinanceGoal):
        """목표 위젯 그리기"""
        card = ctk.CTkFrame(self.goals_scroll, corner_radius=10)
        card.pack(fill="x", padx=5, pady=10)
        
        # 헤더
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 5))
        
        ctk.CTkLabel(
            header,
            text=goal.name,
            font=("Helvetica", 13, "bold")
        ).pack(side="left")
        
        # 버튼
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right")
        
        def add_savings():
            amount_str = simpledialog.askstring("저축 추가", "금액 (원):")
            if amount_str:
                try:
                    amount = float(amount_str)
                    self.manager.add_goal_savings(goal.id, amount)
                    self._refresh_display()
                except ValueError:
                    messagebox.showerror("오류", "올바른 금액을 입력하세요.")
        
        ctk.CTkButton(
            btn_frame,
            text="+ 저축",
            command=add_savings,
            width=80,
            height=30
        ).pack(side="left", padx=5)
        
        def delete_goal():
            if messagebox.askyesno("확인", "목표를 삭제하시겠습니까?"):
                self.manager.delete_goal(goal.id)
                self._refresh_display()
        
        ctk.CTkButton(
            btn_frame,
            text="삭제",
            command=delete_goal,
            width=60,
            height=30,
            fg_color="red"
        ).pack(side="left", padx=5)
        
        # 진행 정보
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(
            info_frame,
            text=f"{goal.current_amount:,}원 / {goal.target_amount:,}원",
            font=("Helvetica", 11)
        ).pack(anchor="w")
        
        # 진행 바
        progress = ctk.CTkProgressBar(card)
        progress.set(goal.progress_rate / 100)
        progress.pack(fill="x", padx=10, pady=5)
        
        # 상세 정보
        details = []
        details.append(f"진행률: {goal.progress_rate:.1f}%")
        if goal.days_until_deadline:
            details.append(f"남은 기간: {goal.days_until_deadline}일")
        if goal.monthly_target and goal.monthly_target > 0:
            details.append(f"월간 목표: {goal.monthly_target:,.0f}원")
        
        ctk.CTkLabel(
            card,
            text=" | ".join(details),
            font=("Helvetica", 10),
            text_color="gray"
        ).pack(anchor="w", padx=10, pady=(0, 10))
    
    def _update_analysis(self):
        """분석 업데이트"""
        for widget in self.analysis_scroll.winfo_children():
            widget.destroy()
        
        today = date.today()
        month_start = date(today.year, today.month, 1)
        
        # 카테고리 분석
        ctk.CTkLabel(
            self.analysis_scroll,
            text="이번 달 카테고리별 지출",
            font=("Helvetica", 14, "bold")
        ).pack(anchor="w", padx=10, pady=(10, 10))
        
        stats = self.manager.get_category_stats(start_date=month_start)
        
        if stats:
            total = sum(s['total'] for s in stats.values())
            
            for category, data in sorted(stats.items(), key=lambda x: x[1]['total'], reverse=True):
                percentage = (data['total'] / total) * 100 if total > 0 else 0
                
                row = ctk.CTkFrame(self.analysis_scroll, fg_color="transparent")
                row.pack(fill="x", padx=10, pady=5)
                
                # 카테고리명
                ctk.CTkLabel(
                    row,
                    text=f"{category}: {data['total']:,}원 ({percentage:.1f}%)",
                    font=("Helvetica", 11, "bold")
                ).pack(anchor="w")
                
                # 진행 바
                progress = ctk.CTkProgressBar(row)
                progress.set(percentage / 100)
                progress.pack(fill="x", pady=(0, 5))
        
        # 지출 추세
        ctk.CTkLabel(
            self.analysis_scroll,
            text="최근 6개월 지출 추세",
            font=("Helvetica", 14, "bold")
        ).pack(anchor="w", padx=10, pady=(20, 10))
        
        trend = self.manager.get_spending_trend(months=6)
        
        if trend:
            max_amount = max(trend.values()) if trend else 0
            
            for month, amount in trend.items():
                row = ctk.CTkFrame(self.analysis_scroll, fg_color="transparent")
                row.pack(fill="x", padx=10, pady=5)
                
                ctk.CTkLabel(
                    row,
                    text=month,
                    font=("Helvetica", 10),
                    width=60
                ).pack(side="left")
                
                if max_amount > 0:
                    bar_length = int((amount / max_amount) * 20)
                    bar_text = "█" * bar_length
                else:
                    bar_text = ""
                
                ctk.CTkLabel(
                    row,
                    text=bar_text,
                    font=("Helvetica", 10)
                ).pack(side="left", padx=5)
                
                ctk.CTkLabel(
                    row,
                    text=f"{amount:,}원",
                    font=("Helvetica", 10)
                ).pack(side="right")

    def _update_charts(self):
        """차트 탭 업데이트"""
        for widget in self.charts_scroll.winfo_children():
            widget.destroy()

        today = date.today()
        month_start = date(today.year, today.month, 1)
        stats = self.manager.get_category_stats(start_date=month_start)
        trend = self.manager.get_spending_trend(months=6)

        # 카테고리 도넛 차트
        donut_card = ctk.CTkFrame(self.charts_scroll)
        donut_card.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(donut_card, text="카테고리 비중", font=("Helvetica", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        donut_canvas = tk.Canvas(donut_card, width=420, height=280, bg="#1f1f1f", highlightthickness=0)
        donut_canvas.pack(fill="x", padx=10, pady=10)
        self._draw_donut_chart(donut_canvas, stats)

        # 월별 지출 라인 차트
        line_card = ctk.CTkFrame(self.charts_scroll)
        line_card.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(line_card, text="월별 지출 추세", font=("Helvetica", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        line_canvas = tk.Canvas(line_card, width=760, height=320, bg="#1f1f1f", highlightthickness=0)
        line_canvas.pack(fill="x", padx=10, pady=10)
        self._draw_line_chart(line_canvas, trend)

    def _draw_donut_chart(self, canvas: tk.Canvas, stats: Dict[str, Dict[str, float]]) -> None:
        total = sum(v.get('total', 0.0) for v in stats.values())
        if total <= 0:
            canvas.create_text(210, 140, text="데이터가 없습니다", fill="#cccccc", font=("Helvetica", 14))
            return

        colors = ['#4F46E5', '#0891B2', '#16A34A', '#CA8A04', '#DC2626', '#7C3AED', '#EA580C']
        start = 0.0
        center_x, center_y, radius = 140, 140, 95

        sorted_items = sorted(stats.items(), key=lambda x: x[1].get('total', 0), reverse=True)[:7]
        for idx, (name, data) in enumerate(sorted_items):
            value = float(data.get('total', 0))
            extent = (value / total) * 360.0
            color = colors[idx % len(colors)]
            canvas.create_arc(
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius,
                start=start,
                extent=extent,
                fill=color,
                outline=''
            )
            start += extent

        # 도넛 구멍
        inner_radius = 48
        canvas.create_oval(
            center_x - inner_radius,
            center_y - inner_radius,
            center_x + inner_radius,
            center_y + inner_radius,
            fill='#1f1f1f',
            outline=''
        )
        canvas.create_text(center_x, center_y - 8, text='총지출', fill='#cccccc', font=('Helvetica', 11))
        canvas.create_text(center_x, center_y + 10, text=f"{total:,.0f}원", fill='#ffffff', font=('Helvetica', 11, 'bold'))

        # 범례
        legend_x = 260
        legend_y = 40
        for idx, (name, data) in enumerate(sorted_items):
            y = legend_y + idx * 28
            color = colors[idx % len(colors)]
            value = float(data.get('total', 0))
            pct = (value / total) * 100
            canvas.create_rectangle(legend_x, y, legend_x + 14, y + 14, fill=color, outline='')
            canvas.create_text(
                legend_x + 20,
                y + 7,
                text=f"{name} {pct:.1f}% ({value:,.0f}원)",
                fill='#dddddd',
                font=('Helvetica', 10),
                anchor='w'
            )

    def _draw_line_chart(self, canvas: tk.Canvas, trend: Dict[str, float]) -> None:
        if not trend:
            canvas.create_text(380, 160, text="데이터가 없습니다", fill="#cccccc", font=("Helvetica", 14))
            return

        items = list(trend.items())
        values = [float(v) for _, v in items]
        labels = [k for k, _ in items]

        min_val = min(values)
        max_val = max(values)
        if math.isclose(max_val, min_val):
            max_val = min_val + 1.0

        left, top, right, bottom = 60, 30, 720, 260
        canvas.create_line(left, top, left, bottom, fill="#888888")
        canvas.create_line(left, bottom, right, bottom, fill="#888888")

        # 가이드 라인
        for i in range(5):
            y = top + (bottom - top) * (i / 4)
            val = max_val - ((max_val - min_val) * (i / 4))
            canvas.create_line(left, y, right, y, fill="#2f2f2f")
            canvas.create_text(left - 8, y, text=f"{val:,.0f}", fill="#aaaaaa", font=("Helvetica", 9), anchor='e')

        points = []
        for i, value in enumerate(values):
            x = left + ((right - left) * (i / max(1, len(values) - 1)))
            y = bottom - ((value - min_val) / (max_val - min_val)) * (bottom - top)
            points.append((x, y))

            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#4F46E5", outline='')
            canvas.create_text(x, bottom + 16, text=labels[i], fill="#aaaaaa", font=("Helvetica", 9))

        for i in range(1, len(points)):
            canvas.create_line(points[i - 1][0], points[i - 1][1], points[i][0], points[i][1], fill="#4F46E5", width=2)

    def _update_catalog_status_label(self) -> None:
        """카탈로그 파일 상태를 상태 바에 반영"""
        try:
            if not self._is_widget_alive():
                return
            if not hasattr(self, '_catalog_status_label'):
                return
            status = self.product_advisor.get_catalog_status()
            parts = []
            for pt, info in status.items():
                label = {"loan": "대출", "insurance": "보험", "savings": "예적금"}.get(pt, pt)
                source_kind = info.get("source_kind", "")
                source_label = {
                    "bundled_catalog": "앱 기본 비교 데이터(실시간 아님)",
                    "operator_catalog": "운영자 제공 비교 데이터",
                    "built_in_fallback": "앱 내장 예비 비교 데이터",
                }.get(source_kind, "확인 필요")
                parts.append(f"{label}: {source_label}")
            label_text = "  |  ".join(parts) if parts else "상품 정보 상태를 확인할 수 없습니다."
            self._catalog_status_label.configure(text=label_text)
        except Exception:
            pass

    def _manual_catalog_refresh(self) -> None:
        """수동 카탈로그 강제 재로드"""
        if not self._is_widget_alive():
            return
        try:
            if hasattr(self, '_catalog_status_label'):
                self._catalog_status_label.configure(text="상품 정보를 다시 읽는 중...")
            ok = self.product_advisor.force_refresh()
            if ok:
                self._run_all_compare()
            self._update_catalog_status_label()
        except Exception as exc:
            if hasattr(self, '_catalog_status_label'):
                self._catalog_status_label.configure(text=f"다시 읽기 실패: {exc}")

    def _run_all_compare(self):
        """전체 금융상품 비교 실행"""
        if not self._is_widget_alive():
            return
        self._run_loan_compare()
        self._run_insurance_compare()
        self._run_savings_compare()

    def _run_loan_compare(self):
        """대출 비교 실행 (신용도 기반 조정 포함)"""
        try:
            amount_wan = float(self._loan_amount_entry.get() or "10000")
            term = int(self._loan_term_entry.get() or "24")
            amount = amount_wan * 10000
        except ValueError:
            amount, term = 100_000_000, 24
        
        result = self.product_advisor.compare_loans(amount=amount, term_months=term)
        
        # 신용도 기반 조정 적용
        credit_score = self._credit_score_var.get()
        result = self.product_advisor.apply_credit_adjustment_to_loans(result, credit_score)
        summary = self._append_catalog_source(result)
        
        self._draw_product_comparison_table(
            section_id="loan",
            title=f"대출 비교  ({amount_wan:,.0f}만원 / {term}개월)",
            headers=["순위", "상품명", "제공사", "연이율(%)", f"총비용(원 / {term}개월)"],
            rows=[
                [str(i + 1), a["name"], a["provider"],
                 f"{a['annual_rate']:.2f}%", f"{a['total_cost']:,.0f}원"]
                for i, a in enumerate(result["alternatives"])
            ],
            best_idx=0,
            summary=summary,
            badge_color="#1d4ed8",
        )

    def _run_insurance_compare(self):
        """보험 비교 실행 (커스텀 입력값 적용)"""
        try:
            budget = float(self._insurance_budget_entry.get() or "70000")
        except ValueError:
            budget = 70000
        cat_raw = self._insurance_cat_var.get()
        category = None if cat_raw == "전체" else cat_raw
        result = self.product_advisor.compare_insurances(budget_monthly=budget, category=category)
        summary = self._append_catalog_source(result)
        self._draw_product_comparison_table(
            section_id="insurance",
            title=f"보험 비교  (월 {budget:,.0f}원 예산 / 종류: {cat_raw})",
            headers=["순위", "상품명", "제공사", "월보험료(원)", "보장점수", "자기부담금(원)"],
            rows=[
                [str(i + 1), a["name"], a["provider"],
                 f"{a['monthly_premium']:,.0f}원", f"{a['coverage_score']:.0f}/100",
                 f"{result['best'].get('deductible', 0):,.0f}원" if i == 0 else "–"]
                for i, a in enumerate(result["alternatives"])
            ],
            best_idx=0,
            summary=summary,
            badge_color="#065f46",
        )

    def _run_savings_compare(self):
        """예적금 비교 실행 (신용도 기반 조정 포함)"""
        try:
            principal_wan = float(self._savings_principal_entry.get() or "500")
            term = int(self._savings_term_entry.get() or "12")
            principal = principal_wan * 10000
        except ValueError:
            principal, term, principal_wan = 5_000_000, 12, 500
        
        result = self.product_advisor.compare_savings(principal=principal, term_months=term)
        
        # 신용도 기반 조정 적용
        credit_score = self._credit_score_var.get()
        result = self.product_advisor.apply_credit_adjustment_to_savings(result, credit_score)
        summary = self._append_catalog_source(result)
        
        self._draw_product_comparison_table(
            section_id="savings",
            title=f"예적금 비교  ({principal_wan:,.0f}만원 / {term}개월)",
            headers=["순위", "상품명", "제공사", "연이율(%)", "예상이자(원)", "비과세"],
            rows=[
                [str(i + 1), a["name"], a["provider"],
                 f"{a['annual_rate']:.2f}%", f"{a['expected_interest']:,.0f}원",
                 "" if result["best"].get("tax_free") and i == 0 else ("" if False else "–")]
                for i, a in enumerate(result["alternatives"])
            ],
            best_idx=0,
            summary=summary,
            badge_color="#7c3aed",
        )

    def _append_catalog_source(self, result: dict) -> str:
        base_summary = str(result.get("summary", ""))
        source_kind = str(result.get("catalog_source_kind", "")).strip()
        if not source_kind:
            return base_summary
        source_text = {
            "bundled_catalog": "앱에 포함된 기본 비교 데이터",
            "operator_catalog": "운영자가 제공한 비교 데이터",
            "built_in_fallback": "앱 내장 예비 비교 데이터",
        }.get(source_kind, "확인 가능한 비교 데이터")
        return (
            f"{base_summary}\n데이터 출처: {source_text}"
            "\n안내: 비교용 참고 정보이며 실제 금리·가입 조건은 금융사에서 최종 확인하세요."
        )

    def _draw_product_comparison_table(
        self,
        section_id: str,
        title: str,
        headers: list,
        rows: list,
        best_idx: int,
        summary: str,
        badge_color: str = "#1f2937",
    ) -> None:
        """금융상품 비교 결과를 시각적 테이블로 렌더링 (기존 섹션 재사용)"""
        if not self._is_widget_alive() or not hasattr(self, 'products_scroll'):
            return
        try:
            if not self.products_scroll.winfo_exists():
                return
        except Exception:
            return

        # 기존 섹션 프레임 찾거나 새로 생성
        attr = f"_product_section_{section_id}"
        old = getattr(self, attr, None)
        if old:
            try:
                old.destroy()
            except Exception:
                pass

        card = ctk.CTkFrame(self.products_scroll, fg_color="#1e293b", corner_radius=14,
                            border_width=1, border_color="#334155")
        card.pack(fill="x", padx=4, pady=8)
        setattr(self, attr, card)

        # 타이틀 행
        title_row = ctk.CTkFrame(card, fg_color=badge_color, corner_radius=10)
        title_row.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(title_row, text=title,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#f1f5f9").pack(anchor="w", padx=12, pady=8)

        # 테이블 컨테이너
        table_frame = ctk.CTkFrame(card, fg_color="transparent")
        table_frame.pack(fill="x", padx=10, pady=(6, 0))

        col_count = len(headers)
        for c in range(col_count):
            table_frame.grid_columnconfigure(c, weight=1)

        # 헤더 행
        for c, h in enumerate(headers):
            ctk.CTkLabel(
                table_frame, text=h,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#94a3b8",
                fg_color="#0f172a",
                corner_radius=0,
            ).grid(row=0, column=c, padx=2, pady=2, sticky="ew", ipady=5)

        # 데이터 행
        for r, row_data in enumerate(rows):
            is_best = (r == best_idx)
            row_bg = "#1d4ed810" if is_best else "transparent"
            for c, cell in enumerate(row_data):
                lbl = ctk.CTkLabel(
                    table_frame, text=cell,
                    font=ctk.CTkFont(size=11, weight="bold" if is_best else "normal"),
                    text_color="#fbbf24" if (is_best and c == 0) else ("#e2e8f0" if is_best else "#cbd5e1"),
                    fg_color="#1e3a5f" if is_best else "#111827",
                    corner_radius=0,
                )
                lbl.grid(row=r + 1, column=c, padx=2, pady=1, sticky="ew", ipady=4)

        # 최우수 상품 뱃지 + 요약
        summary_row = ctk.CTkFrame(card, fg_color="transparent")
        summary_row.pack(fill="x", padx=12, pady=(6, 10))
        ctk.CTkLabel(
            summary_row, text="추천",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#fbbf24",
            fg_color=badge_color, corner_radius=8,
        ).pack(side="left", padx=(0, 8), ipadx=6, ipady=3)
        ctk.CTkLabel(
            summary_row, text=summary,
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
            justify="left", wraplength=860,
        ).pack(side="left", fill="x", expand=True)

    # ── 하위 호환 래퍼 (LifeFinanceAssistant → products_scroll 사용 경로) ──
    def _compare_loan_products(self, show_header: bool = True):
        self._run_loan_compare()

    def _compare_insurance_products(self, show_header: bool = True):
        self._run_insurance_compare()

    def _compare_savings_products(self, show_header: bool = True):
        self._run_savings_compare()

    def _update_products(self):
        """금융상품 탭 업데이트 (show_other_investment_content 등에서 호출)"""
        self._run_all_compare()

    def _draw_product_result_card(self, title, best, alternatives, summary, show_header=True):
        """하위 호환 — 새 테이블 방식으로 위임 (직접 호출 시)"""
        # section_id를 title에서 추출 (대출/보험/예적금)
        if "대출" in title:
            sid = "loan"
        elif "보험" in title:
            sid = "insurance"
        else:
            sid = "savings"
        rows = [
            [str(i + 1), a.get("name", ""), a.get("provider", ""),
             f"{a.get('annual_rate', a.get('monthly_premium', 0)):.2f}", "–"]
            for i, a in enumerate(alternatives)
        ]
        self._draw_product_comparison_table(
            section_id=sid, title=title,
            headers=["순위", "상품명", "제공사", "주요지표", "비고"],
            rows=rows, best_idx=0, summary=summary,
        )
    
    # ========== 대화형 입력 ==========
    
    def _open_add_expense(self):
        """지출 추가 대화"""
        # 간단한 입력 창
        dialog = ctk.CTkToplevel(self)
        dialog.title("지출 추가")
        dialog.geometry("400x300")
        
        # 날짜
        ctk.CTkLabel(dialog, text="날짜:").pack(anchor="w", padx=20, pady=(20, 0))
        date_entry = ctk.CTkEntry(dialog, placeholder_text="YYYY-MM-DD (기본: 오늘)")
        date_entry.pack(fill="x", padx=20, pady=(0, 10))
        
        # 금액
        ctk.CTkLabel(dialog, text="금액 (원):").pack(anchor="w", padx=20)
        amount_entry = ctk.CTkEntry(dialog, placeholder_text="예: 5000")
        amount_entry.pack(fill="x", padx=20, pady=(0, 10))
        
        # 설명
        ctk.CTkLabel(dialog, text="설명:").pack(anchor="w", padx=20)
        desc_entry = ctk.CTkEntry(dialog, placeholder_text="카페, 점심, 택시 등")
        desc_entry.pack(fill="x", padx=20, pady=(0, 10))
        
        # 결제 수단
        ctk.CTkLabel(dialog, text="결제 수단:").pack(anchor="w", padx=20)
        method_var = tk.StringVar(value="카드")
        method_menu = ctk.CTkComboBox(
            dialog,
            values=["카드", "현금", "계좌이체", "기타"],
            variable=method_var
        )
        method_menu.pack(fill="x", padx=20, pady=(0, 20))
        
        def save():
            try:
                amount = float(amount_entry.get())
                desc = desc_entry.get() or "지출"
                method = method_var.get()
                
                # 날짜 파싱
                date_str = date_entry.get()
                if date_str:
                    tx_date = datetime.fromisoformat(date_str).date()
                else:
                    tx_date = date.today()
                
                self.manager.add_transaction(
                    date=tx_date,
                    amount=amount,
                    type_=TransactionType.EXPENSE,
                    description=desc,
                    method=method,
                    auto_classify=True,
                )
                
                messagebox.showinfo("성공", "지출이 등록되었습니다.")
                dialog.destroy()
                self._refresh_display()
            except Exception as e:
                messagebox.showerror("오류", str(e))
        
        ctk.CTkButton(dialog, text="저장", command=save).pack(pady=10)
    
    def _open_add_income(self):
        """수입 추가 대화"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("수입 추가")
        dialog.geometry("400x250")
        
        # 날짜
        ctk.CTkLabel(dialog, text="날짜:").pack(anchor="w", padx=20, pady=(20, 0))
        date_entry = ctk.CTkEntry(dialog, placeholder_text="YYYY-MM-DD (기본: 오늘)")
        date_entry.pack(fill="x", padx=20, pady=(0, 10))
        
        # 금액
        ctk.CTkLabel(dialog, text="금액 (원):").pack(anchor="w", padx=20)
        amount_entry = ctk.CTkEntry(dialog, placeholder_text="예: 3500000")
        amount_entry.pack(fill="x", padx=20, pady=(0, 10))
        
        # 설명
        ctk.CTkLabel(dialog, text="설명:").pack(anchor="w", padx=20)
        desc_entry = ctk.CTkEntry(dialog, placeholder_text="급여, 보너스, 투자 등")
        desc_entry.pack(fill="x", padx=20, pady=(0, 20))
        
        def save():
            try:
                amount = float(amount_entry.get())
                desc = desc_entry.get() or "수입"
                
                # 날짜 파싱
                date_str = date_entry.get()
                if date_str:
                    tx_date = datetime.fromisoformat(date_str).date()
                else:
                    tx_date = date.today()
                
                self.manager.add_transaction(
                    date=tx_date,
                    amount=amount,
                    type_=TransactionType.INCOME,
                    description=desc,
                    category="기타",
                    auto_classify=False,
                )
                
                messagebox.showinfo("성공", "수입이 등록되었습니다.")
                dialog.destroy()
                self._refresh_display()
            except Exception as e:
                messagebox.showerror("오류", str(e))
        
        ctk.CTkButton(dialog, text="저장", command=save).pack(pady=10)
    
    def _open_add_goal(self):
        """목표 추가 대화"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("목표 추가")
        dialog.geometry("400x350")
        
        # 목표명
        ctk.CTkLabel(dialog, text="목표명:").pack(anchor="w", padx=20, pady=(20, 0))
        name_entry = ctk.CTkEntry(dialog, placeholder_text="예: 여름 휴가")
        name_entry.pack(fill="x", padx=20, pady=(0, 10))
        
        # 목표 금액
        ctk.CTkLabel(dialog, text="목표 금액 (원):").pack(anchor="w", padx=20)
        amount_entry = ctk.CTkEntry(dialog, placeholder_text="예: 2000000")
        amount_entry.pack(fill="x", padx=20, pady=(0, 10))
        
        # 마감 기한
        ctk.CTkLabel(dialog, text="마감 기한 (선택):").pack(anchor="w", padx=20)
        deadline_entry = ctk.CTkEntry(dialog, placeholder_text="YYYY-MM-DD")
        deadline_entry.pack(fill="x", padx=20, pady=(0, 10))
        
        # 우선순위
        ctk.CTkLabel(dialog, text="우선순위:").pack(anchor="w", padx=20)
        priority_var = tk.StringVar(value="중간")
        priority_menu = ctk.CTkComboBox(
            dialog,
            values=["높음", "중간", "낮음"],
            variable=priority_var
        )
        priority_menu.pack(fill="x", padx=20, pady=(0, 10))
        
        # 설명
        ctk.CTkLabel(dialog, text="설명 (선택):").pack(anchor="w", padx=20)
        desc_entry = ctk.CTkEntry(dialog, placeholder_text="목표에 대한 설명")
        desc_entry.pack(fill="x", padx=20, pady=(0, 20))
        
        def save():
            try:
                name = name_entry.get()
                if not name:
                    messagebox.showerror("오류", "목표명을 입력하세요.")
                    return
                
                amount = float(amount_entry.get())
                
                # 마감 파싱
                deadline_str = deadline_entry.get()
                deadline = None
                if deadline_str:
                    deadline = datetime.fromisoformat(deadline_str).date()
                
                self.manager.add_goal(
                    name=name,
                    target_amount=amount,
                    deadline=deadline,
                    priority=priority_var.get(),
                    description=desc_entry.get(),
                )
                
                messagebox.showinfo("성공", "목표가 추가되었습니다.")
                dialog.destroy()
                self._refresh_display()
            except Exception as e:
                messagebox.showerror("오류", str(e))
        
        ctk.CTkButton(dialog, text="저장", command=save).pack(pady=10)
    
    # ========== AI 어시스턴트 ==========
    
    def _process_assistant_command(self):
        """AI 어시스턴트 명령 처리 (신용도 포함)"""
        user_input = self.assistant_input.get()
        if not user_input:
            return
        
        # 사용자 메시지 표시
        self._add_chat_message("user", user_input)
        self.assistant_input.delete(0, tk.END)
        
        # 신용도/위험도 추출
        credit_score = self._credit_score_var.get() if hasattr(self, '_credit_score_var') else None
        risk_level = self._risk_level_var.get() if hasattr(self, '_risk_level_var') else None
        
        # 비동기 처리
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.assistant.process_command(user_input, credit_score=credit_score, risk_level=risk_level)
            )
            loop.close()
            
            # 응답 표시
            self._add_chat_message("assistant", result['response'])
        except Exception as e:
            self._add_chat_message("error", f"오류: {str(e)}")
    
    def _add_chat_message(self, sender: str, message: str):
        """대화 메시지 추가"""
        frame = ctk.CTkFrame(self.assistant_chat, fg_color="transparent")
        frame.pack(fill="x", padx=10, pady=5)
        
        if sender == "user":
            # 사용자 메시지 (오른쪽)
            ctk.CTkLabel(
                frame,
                text=message,
                font=("Helvetica", 11),
                text_color="white",
                justify="left",
                wraplength=300
            ).pack(anchor="e", padx=10, pady=5, fill="x")
        elif sender == "assistant":
            # 어시스턴트 응답 (왼쪽)
            ctk.CTkLabel(
                frame,
                text=message,
                font=("Helvetica", 11),
                justify="left",
                wraplength=300
            ).pack(anchor="w", padx=10, pady=5, fill="x")
        else:
            # 오류
            ctk.CTkLabel(
                frame,
                text=message,
                font=("Helvetica", 10),
                text_color="red"
            ).pack(anchor="w", padx=10, pady=5)
        
        # 자동 스크롤
        self.assistant_chat.update()
        self.assistant_chat._parent_canvas.yview_moveto(1)
    
    def _voice_input(self):
        """음성 입력(STT)"""
        if not self.voice_module:
            messagebox.showwarning("음성 입력", "음성 모듈을 사용할 수 없습니다.")
            return

        if not self.voice_module.can_transcribe():
            messagebox.showwarning("음성 입력", "STT를 사용하려면 SpeechRecognition 및 마이크 환경이 필요합니다.")
            return

        self._add_chat_message("assistant", "음성 입력을 시작합니다. 말씀해 주세요...")
        threading.Thread(target=self._voice_input_worker, daemon=True).start()

    def _voice_input_worker(self):
        try:
            result = self.voice_module.transcribe_microphone(timeout=5, phrase_time_limit=12)
        except Exception as exc:
            result = {'status': 'error', 'text': '', 'reason': str(exc)}
        self._safe_after(0, self._on_voice_input_done, result)

    def _on_voice_input_done(self, result: Dict[str, Any]):
        status = result.get('status')
        text = str(result.get('text', '') or '').strip()
        reason = str(result.get('reason', '') or '')

        if status == 'ok' and text:
            self.assistant_input.delete(0, tk.END)
            self.assistant_input.insert(0, text)
            self._add_chat_message("assistant", f"인식 결과: {text}")
            self._process_assistant_command()
            return

        if status == 'not_available':
            if reason == 'voice_disabled':
                self._add_chat_message("error", "음성 기능이 꺼져 있습니다. 설정에서 AI 음성을 활성화해주세요.")
            elif reason == 'pyaudio_not_installed':
                self._add_chat_message("error", "마이크 입력을 위해 PyAudio 설치가 필요합니다.")
            else:
                self._add_chat_message("error", "음성 인식 엔진을 사용할 수 없습니다. SpeechRecognition 설치를 확인해주세요.")
            return

        self._add_chat_message("error", f"음성 입력 실패: {reason or '알 수 없는 오류'}")

    # ========== Phase 1: 신용도/위험도 기반 개인화 ==========
    
    def _on_profile_changed(self):
        """신용도/위험도가 변경될 때 호출 — 현재 비교 갱신"""
        self._run_all_compare()

    def _get_credit_adjustment(self) -> Dict[str, float]:
        """신용도에 따른 금리 조정값 반환
        
        반환:
            {"loan": -0.5, "insurance": 0.1, "savings": 0.3} 등
        """
        credit = self._credit_score_var.get()
        adjustments = {
            "좋음 (750~900)": {
                "loan": -0.5,        # 대출 금리 -0.5% 우대
                "insurance": 0.1,    # 보험료 거의 변화 없음
                "savings": 0.3       # 예적금 금리 +0.3% 우대
            },
            "보통 (650~750)": {
                "loan": 0.0,         # 표준 금리
                "insurance": 0.0,
                "savings": 0.0
            },
            "낮음 (~650)": {
                "loan": 0.5,         # 대출 금리 +0.5% (불리)
                "insurance": -0.1,   # 보험료 약간 인상
                "savings": -0.1      # 예적금 금리 -0.1% (불리)
            }
        }
        return adjustments.get(credit, {})

    def _format_credit_label(self) -> str:
        """신용도를 사용자 친화적 텍스트로 포맷"""
        credit = self._credit_score_var.get()
        if "좋음" in credit:
            return "좋음 "
        elif "낮음" in credit:
            return "낮음 "
        else:
            return "보통 "


if __name__ == "__main__":
    # 테스트
    import customtkinter as ctk
    
    root = ctk.CTk()
    root.title("생활금융 위젯 테스트")
    root.geometry("1000x700")
    
    widget = LifeFinanceWidget(root)
    widget.pack(fill="both", expand=True)
    
    root.mainloop()
