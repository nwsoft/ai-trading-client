#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
실시간 로그 위젯 - 모듈화된 버전
기존 대시보드와 동일한 필터링 기능 제공
"""

import os
import sys
import customtkinter as ctk
import tkinter as tk  # TclError 사용을 위해 추가
from datetime import datetime
from typing import List, Dict, Optional, Callable
import threading
import time

# 고정 색상 사용 (테마 제거)
try:
    from utils.fixed_colors import FIXED_COLORS
except ImportError:
    FIXED_COLORS = {
        "text_primary": "#f9fafb",
        "text_secondary": "#9ca3af",
        "success": "#22c55e",
        "danger": "#ef4444",
        "info": "#3b82f6",
    }


class RealtimeLogWidget(ctk.CTkFrame):
    """실시간 로그 위젯 - 모듈화된 버전
    Draft v2 통합 준비: LogStreamService(옵션) 사용 가능
    기존 파일 tail 기반 로직은 유지 (점진적 마이그레이션)
    """

    def __init__(self, parent, logger, log_stream=None, stream_exchange: str | None = None, on_open_manual: Optional[Callable[[], None]] = None, **kwargs):
        """Realtime log widget
        kwargs are forwarded to CTkFrame to allow styling (e.g., corner_radius, fg_color, border).
        """
        super().__init__(parent, **kwargs)
        self.logger = logger

        self._max_all_logs = 5000
        self._max_pending_logs = 2000
        self._all_logs = []  # 모든 로그 저장 (필터링용)
        self._monitoring = False  # 모니터링 상태
        self._last_file_size = 0  # 마지막 파일 크기
        self._monitor_thread = None  # 모니터링 스레드
        self._after_jobs = []  # after 작업 추적
        self._disposed = False
        self._log_stream = log_stream  # LogStreamService 인스턴스 (있으면 구독)
        self._stream_exchange = stream_exchange  # 필터링용(전역 탭은 None)
        self._on_open_manual = on_open_manual
        self._stream_subscription = None
        # 이동된 드롭다운 초기화 (정적 분석기 경고 방지용)
        self.exchange_combo = None  # type: ignore[assignment]
        self.category_combo = None  # type: ignore[assignment]

        # UI 생성
        self.create_widgets()

        # 탭/프레임이 destroy될 때 구독 및 스레드를 반드시 해제
        try:
            self.bind("<Destroy>", self._on_destroy, add="+")
        except Exception:
            pass

        if self._log_stream is None:
            # 기존 파일 기반 동작
            self.refresh_logs()
            self.start_realtime_monitoring()
        else:
            # LogStream 구독 모드
            self._subscribe_stream()

        # 초기화 완료 후 대기 중인 로그 처리
        self.safe_after(100, self._process_pending_logs)

    # --- Theme helpers - 고정 색상만 사용
    def _color(self, key: str, fallback: Optional[str] = None) -> str:
        if fallback is None:
            fallback = FIXED_COLORS.get(key, "#9ca3af")
        return FIXED_COLORS.get(key, fallback)

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

    def _hover_from(self, color_hex: str, factor: float = 0.85) -> str:
        return self._shade_color(color_hex, factor)

    def create_widgets(self):
        """위젯 생성"""
        # 메인 컨테이너
        main_container = ctk.CTkFrame(self, fg_color="#0b1120")
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # 1. 로그 필터링 옵션 (요약 섹션 제거로 바로 필터부터 시작)
        self.create_filter_section(main_container)

        # 2. 실시간 로그 표시 영역
        self.create_log_display_section(main_container)

        # 3. 로그 제어 버튼들
        self.create_control_section(main_container)

    def create_summary_section(self, parent):
        """요약 섹션은 사용하지 않음(더미) - 레이아웃 단순화를 위해 제거"""
        return

    def create_filter_section(self, parent):
        """필터 섹션 생성 - 기존 대시보드와 동일하게 구현"""
        filter_frame = ctk.CTkFrame(parent, fg_color="#0b1120")
        filter_frame.pack(fill="x", pady=(0, 10))

        # 모든 필터 옵션을 한 줄에 배치
        options_frame = ctk.CTkFrame(filter_frame, fg_color="#0b1120")
        options_frame.pack(fill="x", padx=10, pady=5)

        # 체크박스 색상 제거 - 기본 CustomTkinter 색상 사용
        self.show_signals_only = ctk.CTkCheckBox(
            options_frame,
            text="거래 시그널만",
            command=self.filter_logs
        )
        self.show_signals_only.pack(side="left", padx=5, pady=5)

        self.show_analysis_only = ctk.CTkCheckBox(
            options_frame,
            text="분석 과정만",
            command=self.filter_logs
        )
        self.show_analysis_only.pack(side="left", padx=5, pady=5)

        self.show_all_logs = ctk.CTkCheckBox(
            options_frame,
            text="전체 로그",
            command=self.filter_logs
        )
        self.show_all_logs.pack(side="left", padx=5, pady=5)
        self.show_all_logs.select()  # 기본 선택

        self.hide_init_logs = ctk.CTkCheckBox(
            options_frame,
            text="초기화 로그 숨김",
            command=self.update_filter_settings
        )
        self.hide_init_logs.pack(side="left", padx=5, pady=5)

        self.hide_debug_logs = ctk.CTkCheckBox(
            options_frame,
            text="디버그 로그 숨김",
            command=self.update_filter_settings
        )
        self.hide_debug_logs.pack(side="left", padx=5, pady=5)

        self.hide_system_logs = ctk.CTkCheckBox(
            options_frame,
            text="시스템 로그 숨김",
            command=self.update_filter_settings
        )
        self.hide_system_logs.pack(side="left", padx=5, pady=5)
        # 기본값: 숨김 옵션 비활성화

        # ---- 컨텍스트별 기본값 조정 ----
        # 전역 탭(stream_exchange=None): 전체 로그 ON + 숨김 옵션 OFF (이미 설정됨)
        # 거래소 탭(stream_exchange!=None): 기본을 단순 모드로 유지(복잡한 숨김 옵션 미사용)
        try:
            if self._stream_exchange:
                # 거래소 탭에서는 사용성 단순화를 위해 '전체 로그' 기본 유지, 숨김 옵션은 OFF
                if hasattr(self, 'show_all_logs'):
                    self.show_all_logs.select()
                try:
                    self.hide_init_logs.deselect()
                    self.hide_debug_logs.deselect()
                    self.hide_system_logs.deselect()
                except Exception:
                    pass
                # '거래 시그널만' 체크박스를 '간략 로그'로 표기하여 2단계 토글 UX 제공
                try:
                    self.show_signals_only.configure(text="간략 로그")
                except Exception:
                    pass
        except Exception:
            pass

        # 거래소/카테고리 드롭다운은 컨트롤 섹션(하단)으로 이동하여 로그 레벨 옆에 배치

    def create_log_display_section(self, parent):
        """로그 표시 섹션 생성"""
        log_display_frame = ctk.CTkFrame(parent, fg_color="#0b1120")
        log_display_frame.pack(fill="both", expand=True, pady=(0, 10))

        # 로그 텍스트 위젯 - 고정 폰트 사용
        code_font = ctk.CTkFont(family="Consolas", size=11)

        self.realtime_log_display = ctk.CTkTextbox(
            log_display_frame,
            font=code_font,
            height=300,
            corner_radius=12,  # 대시보드와 통일 (8 → 12)
            # 투명 대신 표면색을 지정하여 텍스트박스 자체도 둥글게 보이도록 처리
            fg_color=self._color("surface", "#1f2937"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        self.realtime_log_display.pack(fill="both", expand=True, padx=5, pady=5)

    def create_control_section(self, parent):
        """제어 섹션 생성"""
        control_frame = ctk.CTkFrame(parent, fg_color="#0b1120")
        control_frame.pack(fill="x")

        # 고정 폰트 사용
        button_font = ctk.CTkFont(size=12)

        help_btn = ctk.CTkButton(
            control_frame,
            text="❓로그도움말",
            command=self.show_log_help,
            font=button_font,
            height=40,
            corner_radius=12
        )
        help_btn.pack(side="left", padx=5, pady=5)

        clear_btn = ctk.CTkButton(
            control_frame,
            text="🗑️로그지우기",
            command=self.clear_logs,
            font=button_font,
            height=40,
            corner_radius=12  # 대시보드와 통일 (8 → 12)
        )
        clear_btn.pack(side="left", padx=5, pady=5)

        refresh_btn = ctk.CTkButton(
            control_frame,
            text="🔄새로고침",
            command=self.refresh_logs,
            font=button_font,
            height=40,
            corner_radius=12  # 대시보드와 통일 (8 → 12)
        )
        refresh_btn.pack(side="left", padx=5, pady=5)

        # 로그 레벨 선택
        label_font = ctk.CTkFont(size=12)

        log_level_label = ctk.CTkLabel(
            control_frame,
            text="로그 레벨:",
            font=label_font
        )
        log_level_label.pack(side="left", padx=(20, 5), pady=5)

        self.log_level_combo = ctk.CTkComboBox(
            control_frame,
            values=["ALL", "INFO", "WARNING", "ERROR"],
            command=self.filter_logs_by_level,
            width=120
        )
        self.log_level_combo.pack(side="left", padx=5, pady=5)
        self.log_level_combo.set("ALL")

        # 거래소/카테고리 드롭다운: 거래소별 탭(stream_exchange 지정)에서는 불필요하므로 전역 탭에서만 생성
        try:
            from log_system.log_stream import get_log_stream  # 지연 임포트
            _ = get_log_stream() if self._log_stream is not None else None
            # 전역 로그 탭(stream_exchange=None)에서만 거래소 드롭다운 제공
            if self._log_stream is not None and self._stream_exchange is None:
                spacer = ctk.CTkLabel(control_frame, text="  ")
                spacer.pack(side="left")
                ctk.CTkLabel(control_frame, text="거래소:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10, 6), pady=5)
                self.exchange_combo = ctk.CTkComboBox(
                    control_frame,
                    values=["ALL"],
                    command=self.filter_stream_changed,
                    width=120
                )
                self.exchange_combo.pack(side="left", padx=(0, 10), pady=5)
                self.exchange_combo.set("ALL")

                ctk.CTkLabel(control_frame, text="카테고리:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 6), pady=5)
                self.category_combo = ctk.CTkComboBox(
                    control_frame,
                    values=["ALL"],
                    command=self.filter_stream_changed,
                    width=120
                )
                self.category_combo.pack(side="left", padx=(0, 5), pady=5)
                self.category_combo.set("ALL")
        except Exception:
            # 스트림 미사용 시 드롭다운 생성 생략
            pass

    def clear_logs(self):
        """로그 지우기"""
        self.realtime_log_display.delete("1.0", "end")
        self.logger.info("로그 지우기 완료")
        if hasattr(self, '_all_logs'):
            self._all_logs.clear()

    def show_log_help(self):
        """로그 해석 도움말 팝업"""
        try:
            help_window = ctk.CTkToplevel(self)
            help_window.title("로그 도움말")
            help_window.geometry("760x560")
            help_window.lift()
            help_window.attributes("-topmost", True)
            help_window.after(300, lambda: help_window.attributes("-topmost", False))

            container = ctk.CTkFrame(help_window, fg_color="#0b1120")
            container.pack(fill="both", expand=True, padx=14, pady=14)

            title = ctk.CTkLabel(
                container,
                text="실시간 로그 해석 가이드",
                font=ctk.CTkFont(size=16, weight="bold")
            )
            title.pack(anchor="w", padx=10, pady=(10, 6))

            guide = ctk.CTkTextbox(container, wrap="word")
            guide.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            guide.insert("1.0", (
                "[로그 레벨 의미]\n"
                "- INFO: 정상 동작/진행 상황 안내\n"
                "- WARNING: 즉시 중단은 아니지만 점검이 필요한 경고\n"
                "- ERROR: 기능 실패 또는 예외 발생\n\n"
                "[자주 나오는 항목]\n"
                "- 거래소 연결/인증: API 키, 네트워크, 권한 문제 확인\n"
                "- 주문/체결: 주문 요청, 체결 결과, 실패 사유\n"
                "- 전략/분석: 신호 생성 이유, 임계값 변화, 리스크 판단\n"
                "- 시스템: 스케줄러, 데이터 수집, 파일/DB I/O 상태\n\n"
                "[초심자 추천 읽는 순서]\n"
                "1. ERROR가 있는지 먼저 확인\n"
                "2. WARNING 원인을 확인\n"
                "3. 같은 시각의 INFO를 함께 읽어 전후 맥락 파악\n\n"
                "[빠른 질문 예시 - AI 어시스턴트]\n"
                "- '방금 ERROR 로그 원인과 조치 순서를 3단계로 알려줘'\n"
                "- '이 경고가 주문 실패와 연관 있는지 로그 기준으로 설명해줘'\n"
                "- '지금 상태에서 바로 확인할 설정 항목만 요약해줘'\n\n"
                "자세한 운영 정책/용어는 인앱 매뉴얼의 '실시간 거래 로그' 관련 안내에서도 확인할 수 있습니다."
            ))
            guide.insert("end", self._build_contextual_log_examples())
            guide.configure(state="disabled")

            action_frame = ctk.CTkFrame(container, fg_color="#0b1120")
            action_frame.pack(fill="x", padx=10, pady=(0, 8))

            open_manual_btn = ctk.CTkButton(
                action_frame,
                text="📖 사용자 매뉴얼(📅 업데이트) 열기",
                command=self._open_manual_from_help,
                height=36,
                corner_radius=12
            )
            open_manual_btn.pack(side="right")
        except Exception as e:
            try:
                self.logger.error(f"로그 도움말 팝업 오류: {e}")
            except Exception:
                pass

    def _open_manual_from_help(self):
        """로그 도움말에서 사용자 매뉴얼 업데이트 탭으로 이동"""
        try:
            if callable(self._on_open_manual):
                self._on_open_manual()
        except Exception as e:
            try:
                self.logger.error(f"매뉴얼 열기 콜백 오류: {e}")
            except Exception:
                pass

    def _build_contextual_log_examples(self) -> str:
        """현재 로그 컨텍스트(코인/증권)에 맞춘 예시 질문을 반환"""
        ex = str(self._stream_exchange or '').strip().lower()
        stock_brokers = {'kiwoom', 'shinhan', 'miraeasset', 'koreainvestment'}

        if ex in stock_brokers:
            return (
                "\n\n[증권 로그 질문 예시]\n"
                "- '방금 주문 거부 원인을 계좌/시간/종목 조건 기준으로 설명해줘'\n"
                "- '오늘 미체결 로그만 추려서 조치 순서 알려줘'\n"
                "- '실주문 허용 설정과 연결 상태가 정상인지 점검해줘'"
            )

        if ex:
            return (
                "\n\n[코인 로그 질문 예시]\n"
                "- '펀딩비/시장방향 로그와 진입 신호가 충돌했는지 점검해줘'\n"
                "- '거래소 인증 오류가 재시도 가능한지 즉시 조치 순서 알려줘'\n"
                "- '최근 청산 로그 기준으로 리스크 설정 조정 포인트를 알려줘'"
            )

        return (
            "\n\n[전역 로그 질문 예시]\n"
            "- '최근 ERROR만 거래소별로 묶어 우선순위 정리해줘'\n"
            "- 'WARNING 중 즉시 조치가 필요한 항목만 추려줘'\n"
            "- '서비스별(코인/증권) 공통 원인인지 분리해서 설명해줘'"
        )

    def _append_all_log(self, line: str):
        """메모리 폭증 방지를 위해 in-memory 로그 버퍼 상한을 유지한다."""
        try:
            if not hasattr(self, '_all_logs') or self._all_logs is None:
                self._all_logs = []
            self._all_logs.append(line)
            overflow = len(self._all_logs) - int(getattr(self, '_max_all_logs', 5000))
            if overflow > 0:
                del self._all_logs[:overflow]
        except Exception:
            pass

    def _append_pending_log(self, line: str):
        """UI 스레드가 밀려도 pending 로그 상한을 유지한다."""
        try:
            if not hasattr(self, '_pending_logs'):
                self._pending_logs = []
            self._pending_logs.append(line)
            overflow = len(self._pending_logs) - int(getattr(self, '_max_pending_logs', 2000))
            if overflow > 0:
                del self._pending_logs[:overflow]
        except Exception:
            pass

    def refresh_logs(self):
        """로그 새로고침 - 기존 대시보드와 동일한 필터링 적용"""
        try:
            if self._log_stream is not None:
                # 스트림 기반: 최근 300개 조회
                from log_system.log_stream import get_log_stream  # 안전: 내부 import
                stream = self._log_stream or get_log_stream()
                # 드롭다운 필터 적용
                sel_ex = None
                try:
                    ex_combo = getattr(self, 'exchange_combo', None)
                    if ex_combo is not None and ex_combo.get() != "ALL":
                        sel_ex = ex_combo.get()
                except Exception:
                    sel_ex = self._stream_exchange
                sel_cat = None
                try:
                    cat_combo = getattr(self, 'category_combo', None)
                    if cat_combo is not None and cat_combo.get() != "ALL":
                        sel_cat = cat_combo.get()
                except Exception:
                    sel_cat = None
                # 개별 위젯에 exchange가 지정된 경우 강제 적용
                if self._stream_exchange:
                    # 거래소별 탭은 특정 exchange만 질의하면 global/legacy 이벤트를 놓칠 수 있으므로
                    # 전체 이벤트에서 텍스트/메타 양쪽으로 재필터링한다.
                    sel_ex = None
                    events = stream.query(exchange=sel_ex, category=sel_cat, limit=500)
                else:
                    events = stream.query(exchange=sel_ex, category=sel_cat, limit=300)
                # 간소화: 거래소 탭은 "전체"(기본) 또는 "간략"(show_signals_only) 2단계만 제공
                show_compact = False
                try:
                    show_compact = bool(self.show_signals_only.get())
                except Exception:
                    show_compact = False

                show_lines = []
                lines_all = []
                for e in events:
                    line = e.format_line()+"\n"
                    lines_all.append(line)
                    # 거래소별 탭은 메타(exchange)와 텍스트 패턴을 모두 허용하여 누락을 줄인다.
                    if self._stream_exchange:
                        ev_ex = str(getattr(e, 'exchange', '') or '').strip().lower()
                        if ev_ex and ev_ex != self._stream_exchange and not self._matches_exchange(line):
                            continue
                        if not ev_ex and not self._matches_exchange(line):
                            continue
                    # 텍스트 기반 보조 필터(필요 최소 유지)
                    if self._should_filter_log(line):
                        continue
                    # 간략 모드: 핵심 카테고리만 노출
                    if show_compact:
                        if str(e.category) not in { 'trade', 'order', 'exit' }:
                            continue
                    show_lines.append(line)

                self._all_logs = list(lines_all[-int(getattr(self, '_max_all_logs', 5000)):])
                # 거래소 탭은 파일 로그를 항상 함께 병합하여,
                # 스트림에 global 이벤트만 잠깐 존재할 때 기존 거래소 로그가 가려지지 않게 한다.
                if self._stream_exchange:
                    fallback_lines: List[str] = []
                    try:
                        log_file = self.get_log_file_path()
                        if log_file and os.path.exists(log_file):
                            with open(log_file, 'r', encoding='utf-8') as f:
                                recent = f.readlines()[-200:]
                            for line in recent:
                                s = line.strip()
                                if not s:
                                    continue
                                if self._should_filter_log(s):
                                    continue
                                if not self._matches_exchange(s):
                                    continue
                                fallback_lines.append(line if line.endswith("\n") else line + "\n")
                    except Exception:
                        fallback_lines = []
                    if fallback_lines:
                        merged: List[str] = []
                        seen = set()
                        for ln in (fallback_lines + show_lines):
                            key = ln.strip()
                            if not key or key in seen:
                                continue
                            seen.add(key)
                            merged.append(ln)
                        show_lines = merged[-250:]

                self.realtime_log_display.delete("1.0", "end")
                for ln in show_lines:
                    self.realtime_log_display.insert("end", ln)
                self.realtime_log_display.see("end")
                self.update_log_summary(show_lines)
                # 필터 옵션 업데이트 (최신 이벤트 기준)
                self._update_stream_filter_options()
                return
            # 실제 로그 파일 경로 사용 (main.py에서 설정된 경로)
            log_file = self.get_log_file_path()
            if log_file and os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    recent_lines = lines[-100:]  # 최근 100줄

                # 로그 필터링 적용 (+ 거래소별 필터)
                filtered_lines = []
                for line in recent_lines:
                    s = line.strip()
                    if self._should_filter_log(s):
                        continue
                    if self._stream_exchange and not self._matches_exchange(s):
                        continue
                    filtered_lines.append(line)

                # 필터링된 로그 표시
                self.realtime_log_display.delete("1.0", "end")
                if filtered_lines:
                    for line in filtered_lines:
                        self.realtime_log_display.insert("end", line)
                else:
                    ex = self._stream_exchange or 'ALL'
                    self.realtime_log_display.insert("end", f"[{ex}] 해당 거래소 로그 없음\n")

                # 자동 스크롤을 맨 아래로
                self.realtime_log_display.see("end")

                # 요약 정보 업데이트
                self.update_log_summary(filtered_lines)

            else:
                # 로그 파일이 없으면 메시지 표시
                self.realtime_log_display.delete("1.0", "end")
                self.realtime_log_display.insert("1.0", f"📊 실시간 거래 로그\n\n로그 파일이 없습니다.\n경로: {log_file}")

            self.logger.info("로그 새로고침 완료")
        except Exception as e:
            self.logger.error(f"로그 새로고침 오류: {e}")

    def get_log_file_path(self):
        """실제 로그 파일 경로 가져오기 - 거래소별 탭에서는 해당 거래소 로그 파일 사용"""
        try:
            # path_utils를 통해 로그 파일 경로 가져오기
            from path_utils import get_log_file_path, get_exchange_log_file_path

            # 거래소별 탭인 경우 해당 거래소 로그 파일 사용
            if self._stream_exchange:
                return get_exchange_log_file_path(self._stream_exchange)
            else:
                # 전체 탭인 경우 메인 로그 파일 사용
                return get_log_file_path()
        except ImportError:
            # path_utils가 없으면 기본 경로 사용 (개발 환경)
            import os
            from datetime import datetime
            if getattr(sys, 'frozen', False):
                # 배포 환경: 사용자 폴더
                # path_utils 사용 실패 시 기본 경로 사용
                from path_utils import get_log_dir
                log_dir = get_log_dir()
            else:
                # 개발 환경: 프로젝트 폴더
                log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
            os.makedirs(log_dir, exist_ok=True)

            # 거래소별 탭인 경우 해당 거래소 로그 파일 사용
            if self._stream_exchange:
                return os.path.join(log_dir, f"trading_{self._stream_exchange}.log")
            else:
                return os.path.join(log_dir, "trading.log")
        except Exception as e:
            self.logger.error(f"로그 파일 경로 가져오기 오류: {e}")
            return None

    def _should_filter_log(self, log_message):
        """로그 메시지 필터링 여부 결정 - 기존 대시보드와 동일한 로직"""
        try:
            # 개발용 디버그 로그 필터링
            developer_debug_patterns = [
                "Optimizer in:", "Optimizer out:", "최종 실행 파라미터:", "최적화 완료:",
                "🔍 Trader 상태 확인:", "🔍 Trader logger 존재:", "🔍 trade_config 내용:",
                "🔍 최종 거래 파라미터:", "🔍 qty 값:", "🔍 포지션 정보:",
                "🔍 거래 실행 조건 충족", "🔍 BUY 참조가격:", "🔍 최종 주문 파라미터:",
                "🔍 _resolve_exchange_filters 시작", "🔍 binance_client 존재:",
                "🔍 get_symbol_info_direct 메서드 존재:", "🔍 get_symbol_info_direct 호출 시작",
                "🔍 get_symbol_info_direct 호출 완료", "🔍 정밀도 정보 조회 성공:",
                "🔍 step_size 기반 수량 조정", "🔍 거래 실행 조건 검증 시작", "🔍 수량 검증:"
            ]

            for pattern in developer_debug_patterns:
                if pattern in log_message:
                    return True

            # WARNING 레벨 로그 필터링 (중요한 WARNING은 유지)
            if " | WARNING " in log_message:
                debug_warning_patterns = [
                    "🔍 Trader 상태 확인:", "🔍 Trader logger 존재:", "🔍 trade_config 내용:",
                    "🔍 최종 거래 파라미터:", "🔍 qty 값:", "🔍 포지션 정보:",
                    "🔍 거래 실행 조건 충족", "🔍 BUY 참조가격:", "🔍 최종 주문 파라미터:"
                ]

                for pattern in debug_warning_patterns:
                    if pattern in log_message:
                        return True

            # 사용자 설정 기반 필터링
            if hasattr(self, 'show_signals_only') and self.show_signals_only.get():
                # 거래 시그널만 표시
                signal_patterns = ["거래 시그널", "거래 실행", "포지션", "분석 완료"]
                if not any(pattern in log_message for pattern in signal_patterns):
                    return True

            if hasattr(self, 'show_analysis_only') and self.show_analysis_only.get():
                # 분석 과정만 표시
                analysis_patterns = ["분석", "AI 학습", "코인 선정", "시그널"]
                if not any(pattern in log_message for pattern in analysis_patterns):
                    return True

            return False

        except Exception as e:
            try:
                self.logger.error(f"로그 필터링 오류: {e}")
            except Exception:
                import logging as _logging
                _logging.getLogger(__name__).error(f"로그 필터링 오류: {e}")
            return False

    def update_log_filter(self):
        """로그 필터 설정 변경 시 호출"""
        try:
            # 체크박스 상태 확인
            if hasattr(self, 'show_all_logs') and self.show_all_logs.get():
                # 전체 로그 선택 시 다른 옵션들 해제
                if hasattr(self, 'show_signals_only'):
                    self.show_signals_only.deselect()
                if hasattr(self, 'show_analysis_only'):
                    self.show_analysis_only.deselect()
            elif hasattr(self, 'show_signals_only') and self.show_signals_only.get():
                # 거래 시그널만 선택 시 다른 옵션들 해제
                if hasattr(self, 'show_all_logs'):
                    self.show_all_logs.deselect()
                if hasattr(self, 'show_analysis_only'):
                    self.show_analysis_only.deselect()
            elif hasattr(self, 'show_analysis_only') and self.show_analysis_only.get():
                # 분석 과정만 선택 시 다른 옵션들 해제
                if hasattr(self, 'show_all_logs'):
                    self.show_all_logs.deselect()
                if hasattr(self, 'show_signals_only'):
                    self.show_signals_only.deselect()

            # 로그 새로고침
            self.refresh_logs()

        except Exception as e:
            self.logger.error(f"로그 필터 업데이트 오류: {e}")

    def filter_logs_by_level(self, level):
        """로그 레벨별 필터링"""
        try:
            if self._log_stream is not None:
                # 스트림 모드에서는 구조화 필터 재적용
                return self.refresh_logs()
            if not hasattr(self, '_all_logs'):
                self._all_logs = []

            filtered_logs = []

            for log_entry in self._all_logs:
                if level == "ALL":
                    filtered_logs.append(log_entry)
                elif level in log_entry:
                    filtered_logs.append(log_entry)

            # 필터링된 로그 표시
            self.realtime_log_display.delete("1.0", "end")
            for log_entry in filtered_logs:
                self.realtime_log_display.insert("end", log_entry)

            self.add_log(f"🔍 로그 필터링 완료: {level} 레벨 ({len(filtered_logs)}개 항목)")

        except Exception as e:
            self.logger.error(f"로그 레벨 필터링 오류: {e}")

    def update_log_summary(self, filtered_lines):
        """요약 섹션 미사용 - 안전한 더미 처리"""
        try:
            return
        except Exception as e:
            # 무시
            pass

    def update_summary(self, summary_text):
        """요약 텍스트 업데이트"""
        # 요약 섹션 미사용 - 안전한 더미 처리
        try:
            return
        except Exception:
            pass

    def filter_logs(self):
        """로그 필터링 - 기존 대시보드와 동일한 기능"""
        try:
            if self._log_stream is not None:
                # 스트림 모드에서는 구조화 필터 재적용
                return self.refresh_logs()
            if not hasattr(self, '_all_logs'):
                return

            filtered_logs = []

            for log_entry in self._all_logs:
                should_show = True

                # 상단 필터 옵션 확인
                if self.show_signals_only.get():
                    if "시그널" not in log_entry and "SIGNAL" not in log_entry:
                        should_show = False
                elif self.show_analysis_only.get():
                    if "분석" not in log_entry and "ANALYSIS" not in log_entry:
                        should_show = False
                elif self.show_all_logs.get():
                    should_show = True

                # 하단 고급 필터 옵션 확인
                if should_show:
                    if self.hide_init_logs.get() and "초기화" in log_entry:
                        should_show = False
                    if self.hide_debug_logs.get() and "DEBUG" in log_entry:
                        should_show = False
                    if self.hide_system_logs.get() and "시스템" in log_entry:
                        should_show = False

                if should_show:
                    filtered_logs.append(log_entry)

            # 필터링된 로그 표시
            self.realtime_log_display.delete("1.0", "end")
            for log_entry in filtered_logs:
                self.realtime_log_display.insert("end", log_entry)

            self.logger.info(f"🔍 로그 필터링 완료: {len(filtered_logs)}개 항목")

        except Exception as e:
            self.logger.error(f"로그 필터링 오류: {e}")

    def update_filter_settings(self):
        """필터 설정 변경 시 호출되는 메서드 - 기존 대시보드와 동일"""
        try:
            hide_init = self.hide_init_logs.get()
            hide_debug = self.hide_debug_logs.get()
            hide_system = self.hide_system_logs.get()

            # 상호 배타 규칙 1: 전체 로그 체크 시 숨김 옵션 해제
            if hasattr(self, 'show_all_logs') and self.show_all_logs.get():
                try:
                    self.hide_init_logs.deselect()
                    self.hide_debug_logs.deselect()
                    self.hide_system_logs.deselect()
                    hide_init = False
                    hide_debug = False
                    hide_system = False
                except Exception:
                    pass
            # 상호 배타 규칙 2: 숨김 옵션 중 하나라도 체크 시 전체 로그 해제
            else:
                if any([hide_init, hide_debug, hide_system]):
                    try:
                        if hasattr(self, 'show_all_logs'):
                            self.show_all_logs.deselect()
                    except Exception:
                        pass

            filter_status = []
            if hide_init:
                filter_status.append("초기화 로그")
            if hide_debug:
                filter_status.append("디버그 로그")
            if hide_system:
                filter_status.append("시스템 로그")

            if filter_status:
                self.logger.info(f"🔍 로그 필터링 활성화: {', '.join(filter_status)} 숨김")
            else:
                self.logger.info("🔍 로그 필터링 비활성화: 모든 로그 표시")
            # 스트림 모드라면 즉시 재적용
            if self._log_stream is not None:
                self.refresh_logs()
            else:
                self.filter_logs()

        except Exception as e:
            self.logger.error(f"필터 설정 업데이트 오류: {e}")

    def start_realtime_monitoring(self):
        """실시간 로그 모니터링 시작 - CustomTkinter용"""
        try:
            if self._monitoring:
                return

            self._monitoring = True
            self._monitor_thread = threading.Thread(target=self._monitor_log_file, daemon=True)
            self._monitor_thread.start()
            self.logger.info("🔥 실시간 로그 모니터링 시작")

        except Exception as e:
            self.logger.error(f"실시간 모니터링 시작 오류: {e}")

    def stop_realtime_monitoring(self):
        """실시간 로그 모니터링 중지"""
        try:
            self._monitoring = False
            if self._monitor_thread:
                self._monitor_thread.join(timeout=1)
            self.logger.info("⏹️ 실시간 로그 모니터링 중지")
            if self._stream_subscription and self._log_stream:
                try:
                    self._log_stream.unsubscribe(self._stream_subscription)
                except Exception:
                    pass
                self._stream_subscription = None

        except Exception as e:
            self.logger.error(f"실시간 모니터링 중지 오류: {e}")

    def _monitor_log_file(self):
        """로그 파일 모니터링 스레드"""
        try:
            while self._monitoring:
                log_file = self.get_log_file_path()
                if log_file and os.path.exists(log_file):
                    current_size = os.path.getsize(log_file)

                    # 파일 크기가 변경되었으면 새 로그 읽기
                    if current_size > self._last_file_size:
                        self._read_new_logs(log_file, self._last_file_size)
                        self._last_file_size = current_size
                    elif current_size < self._last_file_size:
                        # 파일이 재생성되었으면 처음부터 읽기
                        self._last_file_size = 0
                        self.refresh_logs()

                time.sleep(1)  # 1초마다 체크

        except Exception as e:
            self.logger.error(f"로그 파일 모니터링 오류: {e}")

    def _read_new_logs(self, log_file, last_position):
        """새로운 로그만 읽어서 추가"""
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                f.seek(last_position)
                new_lines = f.readlines()

                for line in new_lines:
                    if line.strip():
                        self.add_log(line.strip(), "INFO")

        except Exception as e:
            self.logger.error(f"새 로그 읽기 오류: {e}")

    def add_log(self, message, level="INFO"):
        """로그 추가 - 기존 대시보드와 동일한 방식"""
        try:
            if self._log_stream is not None:
                # 외부에서 직접 add_log 호출 시 -> 단일 스트림 경로로 우회
                from log_system.log_stream import get_log_stream
                stream = self._log_stream or get_log_stream()
                stream.add_event(self._stream_exchange or '', level, 'legacy', message)
                return
            # 거래소 별 표시 필터(파일 기반 모드에서도 적용)
            if self._stream_exchange and not self._matches_exchange(str(message)):
                return
            # API 오류 필터링
            if "Invalid symbol" in message or "APIError" in message:
                return

            if "sma_short" in message or "sma_20" in message:
                return

            # 파일 로그와 동일한 형식으로 통일
            log_entry = f"{message}\n"

            # 모든 로그 저장 (필터링용)
            if not hasattr(self, '_all_logs'):
                self._all_logs = []
            self._append_all_log(log_entry)

            # 실시간 로그에 표시 (필터링 적용) - 직접 실행으로 안전성 보장
            if not self._should_filter_log(log_entry):
                if hasattr(self, 'realtime_log_display'):
                    # 직접 실행 (UI 스레드에서 호출되므로 안전)
                    self._safe_add_log(log_entry)

        except Exception as e:
            try:
                from log_system.log_adapter import log_exception
                log_exception('ui', '로그 추가 오류', exc=e)
            except Exception:
                pass

    def _safe_add_log(self, log_entry):
        """UI 스레드에서 안전하게 로그 추가"""
        try:
            # 위젯이 완전히 초기화되었는지 확인
            if not self._is_log_display_alive():
                # 위젯이 아직 준비되지 않음 - 로그 버퍼에 저장
                if not hasattr(self, '_pending_logs'):
                    self._pending_logs = []
                self._append_pending_log(log_entry)
                return

            # 스레드-세이프: 메인스레드로 위임 (안전한 after 사용)
            try:
                self.safe_after(0, self._append_log_on_main, log_entry)
            except tk.TclError:
                # 위젯이 삭제된 경우 무시
                return
        except Exception as e:
            # "main thread is not in main loop" 오류는 무시 (초기화 중 정상)
            if "main thread is not in main loop" not in str(e):
                try:
                    from log_system.log_adapter import log_exception
                    log_exception('ui', '로그 위임 실패', exc=e)
                except Exception:
                    pass
            else:
                # 로그 버퍼에 저장
                if not hasattr(self, '_pending_logs'):
                    self._pending_logs = []
                self._append_pending_log(log_entry)

    def _is_log_display_alive(self) -> bool:
        """로그 텍스트 위젯이 안전하게 접근 가능한지 확인한다."""
        try:
            if getattr(self, '_disposed', False):
                return False
            if not self.winfo_exists():
                return False
            widget = getattr(self, 'realtime_log_display', None)
            if widget is None:
                return False
            return bool(widget.winfo_exists())
        except Exception:
            return False

    def _append_log_on_main(self, log_entry):
        """메인 스레드에서만 실행되는 로그 추가"""
        try:
            if self._is_log_display_alive():
                self.realtime_log_display.insert("end", log_entry)
                try:
                    self.realtime_log_display.see("end")
                except tk.TclError:
                    return

                # 대기 중인 로그가 있으면 처리
                self._process_pending_logs()
        except Exception as e:
            self.logger.warning(f"UI 로그 추가 오류: {e}")

    def _process_pending_logs(self):
        """대기 중인 로그들을 처리"""
        try:
            pending = list(getattr(self, '_pending_logs', []) or [])
            if not pending:
                return

            if not self._is_log_display_alive():
                # 종료/초기화 경합 시 최근 로그만 유지
                self._pending_logs = pending[-int(getattr(self, '_max_pending_logs', 2000)):]
                return

            self._pending_logs.clear()
            self.realtime_log_display.insert("end", ''.join(pending))
            try:
                self.realtime_log_display.see("end")
            except tk.TclError:
                return
        except Exception as e:
            self.logger.warning(f"대기 로그 처리 오류: {e}")

    def _matches_exchange(self, log_line: str) -> bool:
        """거래소별 로그 필터링 - 단순하고 명확한 방식"""
        try:
            ex = (self._stream_exchange or '').strip().lower()
            if not ex:
                return True  # 전체 탭은 모든 로그 표시

            s = str(log_line).lower()

            # 거래소 로거 이름으로 직접 매칭
            if f"| {ex} |" in s:
                return True

            # 포맷 변형 대응: (ex=bitget), [bitget], exchange: bitget, 거래소: bitget
            exchange_markers = [
                f"(ex={ex})",
                f"[{ex}]",
                f"exchange: {ex}",
                f"exchange={ex}",
                f"거래소: {ex}",
                f"거래소={ex}",
            ]
            if any(marker in s for marker in exchange_markers):
                return True

            # 거래소별 특별 처리: 해당 거래소 관련 키워드 포함
            if ex == 'binance':
                # 바이낸스 관련 로그 표시
                # 1. 직접 바이낸스 로거에서 나온 로그
                if '| binance |' in s:
                    return True

                # 2. 바이낸스 관련 global 로그 (분석, 거래 실행 등)
                if '| global |' in s:
                    binance_global_keywords = [
                        'btcusdt', 'ethusdt', 'bnbusdt', 'solusdt', 'adausdt', 'dashusdt', 'kavausdt',
                        'algousdt', 'xmrusdt', 'trbusdt', 'vetusdt', 'sushiusdt', 'neousdt', 'compusdt', 'flmusdt',
                        'batusdt', 'rlcusdt', 'iotausdt', 'yfiusdt', 'iostusdt', 'thetausdt', 'xtzusdt', 'egldusdt',
                        '분석 과정 상세', '분석 완료', '거래 시그널', '시그널:', '신뢰도:', '트렌드:', '변동성:',
                        '지지 레벨:', '저항 레벨:', 'rsi:', 'macd:', '볼린저밴드', '이동평균', '추론:',
                        'coin processing', 'market analysis', 'trading signal', 'market data retrieval',
                        'market analysis started', 'volatility:', 'trend strength:', 'trend direction:',
                        'uptrend', 'downtrend', 'sideways', 'rsi:', 'analysis', 'retrieval completed',
                        '분석 과정 상세', '분석 완료', '시그널:', '신뢰도:', '트렌드:', '변동성:',
                        '지지 레벨:', '저항 레벨:', 'macd:', '볼린저밴드', '이동평균', '추론:'
                    ]
                    if any(keyword in s.lower() for keyword in binance_global_keywords):
                        return True
            elif ex == 'bybit':
                # 바이비트 관련 키워드 (필요시 추가)
                bybit_keywords = ['bybit', '바이비트']
                if any(keyword in s for keyword in bybit_keywords):
                    return True
            elif ex == 'okx':
                # OKX 관련 키워드 (필요시 추가)
                okx_keywords = ['okx', '오케이엑스']
                if any(keyword in s for keyword in okx_keywords):
                    return True
            elif ex == 'bitget':
                # 비트겟 관련 키워드 (필요시 추가)
                bitget_keywords = ['bitget', '비트겟']
                if any(keyword in s for keyword in bitget_keywords):
                    return True

            return False
        except Exception:
            return True

    # ---- LogStream 구독 모드 ----
    def _subscribe_stream(self):
        if self._log_stream is None:
            return
        def _on_event(ev):
            try:
                # 체크박스 기반 숨김 옵션 적용 (파일 모드와 일관)
                hide_init = False
                hide_debug = False
                hide_system = False
                try:
                    hide_init = bool(self.hide_init_logs.get())
                    hide_debug = bool(self.hide_debug_logs.get())
                    hide_system = bool(self.hide_system_logs.get())
                except Exception:
                    pass
                # 교차 경로 호환: 표준 logging → Stream 포워딩은 exchange가 공란일 수 있음
                # 이 경우 메시지 텍스트에 포함된 거래소명을 휴리스틱으로 매칭
                if self._stream_exchange:
                    formatted = ev.format_line()
                    ev_ex = str(getattr(ev, 'exchange', '') or '').strip().lower()
                    if ev_ex and ev_ex != self._stream_exchange and not self._matches_exchange(formatted):
                        return
                    if not ev_ex and not self._matches_exchange(formatted):
                        return
                    line = formatted + "\n"
                else:
                    line = ev.format_line()+"\n"
                # 텍스트 기반 보조 필터
                if self._should_filter_log(line):
                    return
                # 체크박스 기반 숨김 적용
                if hide_debug and str(ev.level).upper() == 'DEBUG':
                    return
                if hide_system and str(ev.category) == 'system':
                    return
                if hide_init and ('초기화' in str(ev.message)):
                    return
                self._append_all_log(line)
                self._safe_add_log(line)
            except Exception:
                pass
        self._stream_subscription = _on_event
        self._log_stream.subscribe(_on_event)
        # 초기 로드
        self.refresh_logs()

    def _update_stream_filter_options(self):
        """스트림 기반일 때 거래소/카테고리 콤보 값을 최신으로 갱신"""
        if self._log_stream is None:
            return
        try:
            from log_system.log_stream import get_log_stream
            stream = self._log_stream or get_log_stream()
            evs = stream.query(limit=500)
            exchanges = sorted({(e.exchange or '').strip() for e in evs if (e.exchange or '').strip()})
            categories = sorted({(e.category or '').strip() for e in evs if (e.category or '').strip()})
            ex_combo = getattr(self, 'exchange_combo', None)
            if ex_combo is not None:
                vals = ["ALL"] + exchanges
                try:
                    ex_combo.configure(values=vals)
                except Exception:
                    pass
            cat_combo = getattr(self, 'category_combo', None)
            if cat_combo is not None:
                vals = ["ALL"] + categories
                try:
                    cat_combo.configure(values=vals)
                except Exception:
                    pass
        except Exception as e:
            self.logger.warning(f"스트림 필터 옵션 갱신 실패: {e}")

    def filter_stream_changed(self, *_):
        """거래소/카테고리 콤보 변경 시 호출"""
        try:
            if self._log_stream is not None:
                self.refresh_logs()
        except Exception as e:
            self.logger.warning(f"스트림 필터 변경 처리 실패: {e}")

    def safe_after(self, delay, func, *args, **kwargs):
        """안전한 after() 메서드 - 작업 추적"""
        try:
            if getattr(self, '_disposed', False):
                return None
            if not self.winfo_exists():
                return None

            # 안전한 콜백 래핑
            def safe_callback():
                try:
                    if not self.winfo_exists():
                        return
                    if getattr(self, '_disposed', False):
                        return
                    func(*args, **kwargs)
                except tk.TclError as e:
                    if "invalid command name" in str(e) or "border_parts" in str(e):
                        return
                    else:
                        raise e
                except Exception as e:
                    if "invalid command name" not in str(e) and "TclError" not in str(e) and "border_parts" not in str(e):
                        print(f"⚠️ realtime_log_widget 콜백 오류: {e}")

            job = self.after(delay, safe_callback)
            if job:
                self._after_jobs.append(job)
            return job
        except tk.TclError as e:
            # 위젯이 삭제된 경우 무시
            error_msg = str(e)
            if "invalid command name" in error_msg or "border_parts" in error_msg or "find_withtag" in error_msg:
                return None
            raise e
        except Exception as e:
            # 종료 중 위젯 관련 모든 예외 무시
            error_msg = str(e)
            if "TclError" not in error_msg:
                print(f"⚠️ realtime_log_widget safe_after 오류: {e}")
            return None

    def cleanup_after_jobs(self):
        """after 작업 정리"""
        for job in getattr(self, "_after_jobs", []):
            try:
                self.after_cancel(job)
            except:
                pass
        self._after_jobs.clear()

    def _on_destroy(self, event=None):
        """위젯 파괴 시 백그라운드 작업/구독 해제."""
        try:
            if event is not None and getattr(event, 'widget', None) is not self:
                return
        except Exception:
            pass
        self._disposed = True
        try:
            self.stop_realtime_monitoring()
        except Exception:
            pass
        try:
            self.cleanup_after_jobs()
        except Exception:
            pass
        try:
            self._pending_logs = []
        except Exception:
            pass
