#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 어시스턴트 위젯 (CustomTkinter)
대시보드에서 분리된 AI 채팅 및 설정 관리 기능
"""

import sys
import os
import json
import copy
import re
import logging
import threading
from pathlib import Path
from uuid import uuid4
from datetime import datetime
from typing import Dict, List, Any, Optional

import customtkinter as ctk
from customtkinter import CTkFrame, CTkLabel, CTkButton, CTkTextbox, CTkEntry, CTkCheckBox, CTkScrollableFrame, CTkTabview
from tkinter import messagebox
from utils.fixed_colors import build_widget_palette

try:
    # 선택 위젯: 차트 스크린샷 분석기
    from ui.widgets.chart_screenshot_widget import ChartScreenshotWidget
except Exception:
    ChartScreenshotWidget = None  # type: ignore

try:
    from ui.widgets.ai_voice_module import AIVoiceModule, VoiceConfig
except Exception:
    AIVoiceModule = None  # type: ignore
    VoiceConfig = None  # type: ignore

# ThemeManager 제거 - 고정 색상 사용

class AIAssistantWidget(CTkFrame):
    """AI 어시스턴트 위젯 (CustomTkinter) - Modern 통합 버전"""

    DEFAULT_COLORS: Dict[str, str] = {
        "text_primary": "#f9fafb",
        "text_secondary": "#9ca3af",
        "surface": "#1f2937",
        "background": "#0f172a",
        "border": "#374151",
        "primary": "#3b82f6",
        "secondary": "#4b5563",
        "success": "#22c55e",
        "danger": "#ef4444",
        "warning": "#f59e0b",
        "info": "#3b82f6",
        "accent": "#8b5cf6",
    }
    SETTINGS_ACTION_REGISTRY: Dict[str, Dict[str, str]] = {
        "default_leverage": {"permission": "user_confirm", "risk": "high"},
        "default_tp": {"permission": "user_confirm", "risk": "high"},
        "default_sl": {"permission": "user_confirm", "risk": "high"},
        "risk_tolerance": {"permission": "user_confirm", "risk": "high"},
        "balance_utilization_limit": {"permission": "user_confirm", "risk": "high"},
        "assistant_apply_mode": {"permission": "user_confirm", "risk": "normal"},
        "openai_model": {"permission": "user_confirm", "risk": "normal"},
        "assistant_ai_model": {"permission": "user_confirm", "risk": "normal"},
        "ai_model_roles": {"permission": "user_confirm", "risk": "normal"},
        "strategy_engine_high_vol_action": {"permission": "user_confirm", "risk": "high"},
        "strategy_engine_consensus_threshold": {"permission": "user_confirm", "risk": "high"},
        "strategy_engine_cooldown_sec": {"permission": "user_confirm", "risk": "high"},
    }
    PROTECTED_ACTION_REGISTRY: Dict[str, Dict[str, Any]] = {
        "place_order": {
            "permission": "disabled",
            "risk": "critical",
            "required_gates": [
                "fresh_quote", "balance", "positions", "open_orders", "market_hours",
                "slippage", "loss_limits", "idempotency_key", "kill_switch",
            ],
        },
        "start_or_stop_trading": {
            "permission": "disabled",
            "risk": "critical",
            "required_gates": ["runtime_state", "open_positions", "pending_orders", "user_confirmation"],
        },
        "change_api_credentials": {
            "permission": "disabled",
            "risk": "critical",
            "required_gates": ["secure_settings_ui", "credential_validation", "user_confirmation"],
        },
        "withdraw_or_transfer": {
            "permission": "disabled",
            "risk": "critical",
            "required_gates": ["not_supported"],
        },
    }

    def __init__(self, parent=None, ai_manager=None, assistant_model_name: str | None = None, colors: Optional[Dict[str, str]] = None, **kwargs):
        palette = build_widget_palette(colors)
        kwargs.setdefault("fg_color", palette["content_bg"])
        kwargs.setdefault("corner_radius", 0)
        super().__init__(parent, **kwargs)
        self.logger = logging.getLogger(__name__)

        # AI 매니저 주입
        self.ai_manager = ai_manager
        # 어시스턴트용 모델명 (설정에서 주입 가능)
        # 설정 파일에서 직접 읽기 시도 (하드코딩 기본값 제거)
        raw_model_name = assistant_model_name
        if not raw_model_name:
            # 전달된 값이 없으면 설정 파일에서 직접 읽기
            try:
                from config.settings import load_settings
                current_settings = load_settings()
                raw_model_name = current_settings.get('assistant_ai_model')
                if raw_model_name:
                    self.logger.debug(f"설정 파일에서 어시스턴트 모델 로드: {raw_model_name}")
            except Exception as e:
                self.logger.warning(f"설정 파일에서 모델명 읽기 실패: {e}")

        # 모델명 정규화: 잘못된 모델명 자동 수정 (gpt4-4o → gpt-4o)
        # 최후의 fallback으로만 기본값 사용
        self.assistant_model_name = self._normalize_model_name(raw_model_name or 'gpt-4o-mini')

        # AI Manager가 없으면 위젯 비활성화
        if not self.ai_manager:
            self.logger.warning("AI Manager가 전달되지 않아 AI 기능이 비활성화됩니다")

        # 설정 변경 이력 추적
        self.settings_change_history = []
        self.max_history_size = 50
        try:
            from path_utils import get_app_data_dir
            assistant_data_dir = Path(get_app_data_dir()) / "assistant"
        except Exception:
            assistant_data_dir = Path(__file__).resolve().parents[2] / "data" / "assistant"
        self.settings_audit_path = assistant_data_dir / "settings_change_history.json"
        self._load_persistent_settings_history()

        # 현재 권장 설정
        self.current_recommended_settings = None

        # AI 채팅 활성화 상태
        self.ai_chat_enabled = False

        # 대시보드 참조 (거래 상황 수집용)
        self.parent_dashboard = None

        # 대화 내용 전체 로그 (복사/내보내기용)
        self._chat_history_log: List[str] = []
        # 최근 대화 맥락을 다음 답변에 전달한다. UI 알림까지 무한 누적하지 않도록
        # 실제 사용자/어시스턴트 메시지만 최근 16개로 제한한다.
        self._conversation_messages: List[Dict[str, str]] = []

        # v3.9.0.2 안전 계약: 과거 ai_auto 설정이 남아 있어도 최종 확인을 생략하지 않는다.
        self.require_final_settings_confirmation = True

        # 서비스 컨텍스트 (blockchain | stock | ...)
        self.assistant_service_context = "blockchain"
        self.quick_buttons_frame = None
        self.quick_questions_title_label = None

        # 초기 설정 온보딩 상태
        self._onboarding_active = False
        self._onboarding_step = 0
        self._onboarding_answers: Dict[str, str] = {}
        self._onboarding_source = ""

        # AI 커스텀·거래 통계와 같은 기능 탭 공통 팔레트 사용
        self.colors = palette

        # 음성 모듈 (기본 비활성, 설정값 기반)
        self.voice_module = None
        self._init_voice_module()

        self.init_ui()

    def _init_voice_module(self):
        """설정 기반으로 음성 모듈을 초기화한다 (미설정 시 비활성)."""
        try:
            if AIVoiceModule is None or VoiceConfig is None:
                return
            voice_enabled = False
            voice_auto_tts = False
            voice_rate = 180
            try:
                from config.settings import load_settings
                settings = load_settings() or {}
                voice_cfg = settings.get('assistant_voice') or {}
                voice_enabled = bool(voice_cfg.get('enabled', False))
                voice_auto_tts = bool(voice_cfg.get('auto_tts', False))
                voice_rate = int(voice_cfg.get('rate', 180) or 180)
            except Exception:
                pass

            self.voice_module = AIVoiceModule(
                VoiceConfig(enabled=voice_enabled, auto_tts=voice_auto_tts, rate=voice_rate)
            )
        except Exception as e:
            self.logger.debug(f"음성 모듈 초기화 실패: {e}")

    def init_ui(self):
        """UI 초기화"""
        # 메인 레이아웃
        self.grid_columnconfigure(0, weight=8)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)  # 본문(row=1)에 가중치 부여

        # AI Manager 상태 확인 및 경고 표시
        if not self.ai_manager:
            self.create_disabled_ui()
            return

        # 정상 UI 생성
        self.create_normal_ui()

    # --- Theme helpers ---------------------------------------------------
    # _ensure_palette 제거 - 고정 색상 사용

    def _color(self, key: str, fallback: Optional[str] = None) -> str:
        if fallback is None:
            fallback = self.DEFAULT_COLORS.get(key, "#9ca3af")
        try:
            if isinstance(self.colors, dict):
                value = self.colors.get(key)
                if value:
                    return value
        except Exception:
            pass
        return fallback

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

    def create_disabled_ui(self):
        """AI 기능 비활성화된 UI 생성"""
        # 경고 메시지
        warning_label = CTkLabel(
            self,
            text="AI 기능이 비활성화되었습니다.\nOpenAI API 키를 설정해주세요.",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self._color("danger")
        )
        warning_label.grid(row=0, column=0, pady=20, padx=20)

        # 안내 메시지
        info_label = CTkLabel(
            self,
            text="AI 기능을 사용하려면 OpenAI API 키를 설정하고\n프로그램을 재시작해주세요.",
            font=ctk.CTkFont(size=12),
            text_color=self._color("text_secondary")
        )
        info_label.grid(row=1, column=0, pady=10)

    def create_normal_ui(self):
        """정상 UI 생성"""
        # 설정 관리 버튼들은 모달창으로 통합됨

        # 상단 정보 바 (대화 복사·내보내기 도구)
        try:
            # 레이아웃 가중치 재설정: 헤더(0) 고정, 본문(1) 확장
            self.grid_rowconfigure(0, weight=0)
            self.grid_rowconfigure(1, weight=1)
            self.create_info_bar()
        except Exception:
            pass

        # AI 채팅 위젯
        self.create_chat_widget()

        # 자주 하는 질문 버튼들
        self.create_quick_question_buttons()

        # 전략 상태는 설정관리 모달창으로 이동됨

    def create_warning_frame(self):
        """경고 프레임 생성"""
        self.warning_frame = CTkFrame(
            self,
            fg_color=self._color("surface"),
            border_color=self._color("border"),
            border_width=1,
            corner_radius=12
        )
        self.warning_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)

        # 경고 제목
        warning_title = CTkLabel(
            self.warning_frame,
            text="고급 사용자 전용 기능",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self._color("danger")
        )
        warning_title.pack(pady=10)

        # 경고 내용
        warning_text = CTkLabel(
            self.warning_frame,
            text="""이 기능은 고급 사용자를 위한 AI 대화형 전략 조정 시스템입니다.

주의사항:
• AI의 제안은 참고용이며, 투자 손실에 대한 책임은 사용자에게 있습니다
• 과도한 레버리지나 포지션 크기는 큰 손실을 초래할 수 있습니다
• 시장 상황이 급변할 경우 AI 분석이 부정확할 수 있습니다
• 언제든지 기본 설정으로 복원할 수 있습니다

권장사항:
• 소액으로 먼저 테스트해보세요
• AI 제안을 맹신하지 말고 본인 판단을 우선하세요
• 손실 허용 범위 내에서만 거래하세요""",
            font=ctk.CTkFont(size=12),
            text_color=self._color("danger"),
            justify="left"
        )
        warning_text.pack(pady=5, padx=10)

        # AI 대화 활성화 체크박스
        self.ai_chat_enable_checkbox = CTkCheckBox(
            self.warning_frame,
            text="위 내용을 이해했으며 AI 대화 기능을 사용하겠습니다",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self._color("danger"),
            command=self.on_ai_chat_enable_changed
        )
        self.ai_chat_enable_checkbox.pack(pady=10)


    def create_chat_widget(self):
        """채팅 위젯 생성 (크기 최적화)"""
        self.chat_frame = CTkFrame(
            self,
            fg_color=self._color("surface"),
            border_color=self._color("border"),
            border_width=1,
            corner_radius=16
        )
        # 헤더가 있으므로 본문은 row=1에 배치
        self.chat_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.chat_frame.grid_rowconfigure(0, weight=1)
        self.chat_frame.grid_columnconfigure(0, weight=1)

        # 채팅 히스토리 (스크롤 가능, 크기 최적화)
        self.chat_history = CTkScrollableFrame(
            self.chat_frame,
            height=450,  # 크기 늘림 (빈공간 제거)
            fg_color=self._color("content_bg", "#0b1120"),
            border_color=self._color("border_strong", "#334155"),
            border_width=1,
            corner_radius=12,
            scrollbar_button_color=self._color("secondary"),
            scrollbar_button_hover_color=self._hover_from(self._color("secondary"))
        )
        self.chat_history.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # 채팅 메시지 컨테이너 (배경색 명확히)
        self.chat_messages_frame = CTkFrame(
            self.chat_history,
            fg_color=self._color("content_bg", "#0b1120")
        )
        self.chat_messages_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # 초기 메시지 (채팅창 안에 표시)
        self.add_ai_message("안녕하세요. NoahAI 공식 AI 어시스턴트입니다.")
        self.add_ai_message("사용법·현재 상태·설정 위치를 질문하거나, 변경할 값을 말하면 확인 후 도와드립니다.")

        # 사용자 입력 영역
        input_frame = CTkFrame(
            self.chat_frame,
            fg_color=self._color("content_bg", "#0b1120")
        )
        input_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 2))
        input_frame.grid_columnconfigure(0, weight=1)

        self.chat_input = CTkEntry(
            input_frame,
            placeholder_text=self._build_input_placeholder(),
            font=ctk.CTkFont(size=12),
            height=35,
            fg_color=self._color("input", "#0b1120"),
            border_color=self._color("border_strong", "#334155"),
            text_color=self._color("text_primary", "#f9fafb"),
        )
        self.chat_input.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.chat_input.bind("<Return>", lambda e: self.send_ai_message())

        send_button = CTkButton(
            input_frame,
            text="전송",
            command=self.send_ai_message,
            width=80,
            height=35,
            fg_color=self._color("primary"),
            hover_color=self._hover_from(self._color("primary"))
        )
        send_button.grid(row=0, column=1, padx=5, pady=5)

        self.voice_input_button = CTkButton(
            input_frame,
            text="음성입력",
            command=self.on_voice_input_clicked,
            width=100,
            height=35,
            fg_color=self._color("info"),
            hover_color=self._hover_from(self._color("info"))
        )
        self.voice_input_button.grid(row=0, column=2, padx=5, pady=5)

        settings_button = CTkButton(
            input_frame,
            text="설정관리",
            command=self.show_settings_management_modal,
            width=100,
            height=35,
            fg_color=self._color("secondary"),
            hover_color=self._hover_from(self._color("secondary"))
        )
        settings_button.grid(row=0, column=3, padx=5, pady=5)

        chart_button = CTkButton(
            input_frame,
            text="차트분석",
            command=self.open_chart_analyzer,
            width=120,
            height=35,
            fg_color=self._color("info"),
            hover_color=self._hover_from(self._color("info"))
        )
        chart_button.grid(row=0, column=4, padx=5, pady=5)


    def on_voice_input_clicked(self):
        """음성 입력(STT) 실행."""
        if not self.voice_module:
            self.add_ai_message("음성 모듈을 사용할 수 없습니다.")
            return

        try:
            if hasattr(self, 'voice_input_button') and self.voice_input_button:
                self.voice_input_button.configure(state='disabled', text='듣는 중...')
        except Exception:
            pass

        self.add_ai_message("음성 입력을 시작합니다. 말씀해 주세요...")
        thread = threading.Thread(target=self._voice_transcribe_worker, daemon=True)
        thread.start()

    def _voice_transcribe_worker(self):
        try:
            result = self.voice_module.transcribe_microphone(timeout=5, phrase_time_limit=12)
        except Exception as exc:
            result = {'status': 'error', 'text': '', 'reason': str(exc)}
        self.after(0, lambda: self._on_voice_transcribe_done(result))

    def _on_voice_transcribe_done(self, result: Dict[str, Any]):
        try:
            status = result.get('status')
            text = (result.get('text') or '').strip()
            reason = result.get('reason', '')

            if status == 'ok' and text:
                if self._is_settings_change_request(text):
                    risk_level, risk_reasons = self._classify_voice_command_risk(text)
                    risk_header = {
                        'high': '고위험 음성 명령 감지',
                        'elevated': '주의가 필요한 음성 명령',
                        'normal': '음성 명령 확인',
                    }.get(risk_level, '음성 명령 확인')
                    risk_block = ''
                    if risk_reasons:
                        risk_block = "\n\n" + "\n".join(f"- {r}" for r in risk_reasons)

                    confirm_message = (
                        "아래 음성 명령을 설정 변경 요청으로 인식했습니다.\n\n"
                        f"\"{text}\"\n"
                        f"{risk_block}\n\n"
                        "확인하면 입력창에 반영됩니다.\n"
                        "설정 저장 전에는 최종 확인 단계가 한 번 더 표시됩니다."
                    )
                    confirm = bool(messagebox.askyesno(risk_header, confirm_message))
                    if not confirm:
                        self.add_ai_message("↩음성 설정 변경 요청이 취소되었습니다.")
                        return

                self.chat_input.delete(0, 'end')
                self.chat_input.insert(0, text)
                self.add_ai_message(f"음성 인식 결과: {text}")
            elif status == 'not_available':
                if reason == 'voice_disabled':
                    self.add_ai_message("음성 기능이 비활성화되어 있습니다. 설정에서 AI 음성을 먼저 켜주세요.")
                elif reason == 'pyaudio_not_installed':
                    self.add_ai_message("마이크 인식 백엔드(PyAudio)가 없습니다. 배포 가이드의 음성 의존성 설치를 진행해주세요.")
                else:
                    self.add_ai_message("STT 엔진이 준비되지 않았습니다. SpeechRecognition 설치 후 다시 시도하세요.")
            else:
                self.add_ai_message(f"음성 인식 실패: {reason or '알 수 없는 오류'}")
        finally:
            try:
                if hasattr(self, 'voice_input_button') and self.voice_input_button:
                    self.voice_input_button.configure(state='normal', text='음성입력')
            except Exception:
                pass

    def _classify_voice_command_risk(self, text: str) -> tuple[str, list[str]]:
        """음성 설정 명령의 위험도를 간단 분류한다."""
        message = (text or '').lower()
        reasons: list[str] = []
        level = 'normal'

        high_patterns = [
            '레버리지 15', '레버리지 20', '최대 레버리지', '공격적으로',
            '잔고 40', '잔고 50', '전액', '풀매수', '몰빵',
        ]
        elevated_patterns = [
            '레버리지 높', '레버리지 올', '비중 높', '비중 늘',
            '추매', 'aggressive', '공격', '위험하게',
        ]

        if any(p in message for p in high_patterns):
            level = 'high'
            reasons.append('레버리지 또는 자금 노출이 과도해질 수 있습니다.')
        elif any(p in message for p in elevated_patterns):
            level = 'elevated'
            reasons.append('현재보다 공격적인 설정으로 변경될 가능성이 있습니다.')

        if '손절' in message and ('낮' in message or '줄' in message):
            if level == 'normal':
                level = 'elevated'
            reasons.append('손절 폭 축소는 변동성 구간에서 조기 청산을 늘릴 수 있습니다.')

        return level, reasons

    def create_info_bar(self):
        """상단 정보 바: 사용자용 대화 복사·내보내기 도구."""
        try:
            self.info_frame = CTkFrame(
                self,
                fg_color=self._color("content_bg", "#0b1120"),
                corner_radius=0,
            )
            self.info_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=(6, 0))
            self.info_frame.grid_columnconfigure(0, weight=1)
            # 모델은 설정·실행 계층에서 계속 관리하되 사용자 대화 화면에는
            # 내부 모델명을 상시 노출하지 않는다.
            self.model_caption = None

            # 전체 복사 버튼
            copy_all_btn = CTkButton(
                self.info_frame,
                text="전체 복사",
                command=self.copy_all_chat,
                width=90,
                height=24,
                font=ctk.CTkFont(size=11),
                fg_color=self._color("secondary"),
                hover_color=self._hover_from(self._color("secondary")),
            )
            copy_all_btn.grid(row=0, column=1, padx=(4, 2), pady=3, sticky="e")

            # TXT 저장 버튼
            export_txt_btn = CTkButton(
                self.info_frame,
                text="TXT 저장",
                command=self.export_chat_to_txt,
                width=90,
                height=24,
                font=ctk.CTkFont(size=11),
                fg_color=self._color("secondary"),
                hover_color=self._hover_from(self._color("secondary")),
            )
            export_txt_btn.grid(row=0, column=2, padx=(2, 6), pady=3, sticky="e")

        except Exception:
            # 대화 도구 표시 실패는 치명적이지 않으므로 무시
            self.model_caption = None

    def copy_all_chat(self):
        """전체 대화 내용을 클립보드에 복사"""
        try:
            if not self._chat_history_log:
                self.add_ai_message("ℹ복사할 대화 내용이 없습니다.")
                return
            text = "\n".join(self._chat_history_log)
            self.clipboard_clear()
            self.clipboard_append(text)
            self.add_ai_message(f"전체 대화 내용({len(self._chat_history_log)}줄)이 클립보드에 복사되었습니다.")
        except Exception as e:
            self.logger.error(f"전체 복사 오류: {e}")
            self.add_ai_message(f"복사 중 오류가 발생했습니다: {e}")

    def export_chat_to_txt(self):
        """전체 대화 내용을 TXT 파일로 저장"""
        try:
            if not self._chat_history_log:
                self.add_ai_message("ℹ저장할 대화 내용이 없습니다.")
                return

            from tkinter import filedialog
            from datetime import datetime as _dt
            default_name = f"AI분석_{_dt.now().strftime('%Y%m%d_%H%M%S')}.txt"
            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")],
                initialfile=default_name,
                title="AI 분석 결과 저장",
            )
            if not file_path:
                return  # 취소

            header = (
                f"NoahAI 어시스턴트 대화 내보내기\n"
                f"생성: {_dt.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"총 {len(self._chat_history_log)}줄\n"
                + "=" * 60 + "\n\n"
            )
            content = header + "\n".join(self._chat_history_log)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.add_ai_message(f"대화 내용이 저장되었습니다:\n{file_path}")
        except Exception as e:
            self.logger.error(f"TXT 저장 오류: {e}")
            self.add_ai_message(f"저장 중 오류가 발생했습니다: {e}")

    def create_quick_question_buttons(self):
        """자주 하는 질문 버튼들 생성"""
        try:
            # 서비스 전환 시 중복 패널이 생기지 않도록 기존 패널 제거
            try:
                if self.quick_buttons_frame is not None:
                    self.quick_buttons_frame.destroy()
            except Exception:
                pass

            buttons_frame = CTkFrame(
                self,
                fg_color=self._color("surface"),
                border_color=self._color("border"),
                border_width=1,
                corner_radius=12
            )
            buttons_frame.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)
            self.quick_buttons_frame = buttons_frame

            profile = self._get_service_profile(self.assistant_service_context)

            # 제목
            title_label = CTkLabel(
                buttons_frame,
                text=profile["quick_title"],
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=self._color("text_primary")
            )
            title_label.pack(anchor="w", padx=12, pady=(12, 8))
            self.quick_questions_title_label = title_label

            # 질문 버튼들
            questions_frame = CTkFrame(
                buttons_frame,
                fg_color=self._color("content_bg", "#0b1120"),
                corner_radius=10,
            )
            questions_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

            questions = profile["quick_questions"]

            for i, (button_text, question) in enumerate(questions):
                btn = CTkButton(
                    questions_frame,
                    text=button_text,
                    command=lambda q=question: self.send_quick_question(q),
                    width=140,
                    height=32,
                    fg_color=self._color("secondary"),
                    hover_color=self._hover_from(self._color("secondary")),
                    font=ctk.CTkFont(size=11)
                )
                btn.pack(fill="x", padx=4, pady=4)
        except Exception as e:
            self.logger.error(f"자주 하는 질문 버튼 생성 오류: {e}")

    def _build_input_placeholder(self) -> str:
        """서비스 컨텍스트에 맞는 입력창 안내 문구를 반환"""
        profile = self._get_service_profile(self.assistant_service_context)
        return profile["input_placeholder"]

    def _get_service_profile(self, service_name: str) -> Dict[str, Any]:
        """서비스별 AI 어시스턴트 문구/질문/프롬프트 프로필"""
        svc = (service_name or "blockchain").strip().lower()

        if svc == "stock":
            return {
                "label": "주식/ETF",
                "quick_title": "주식/ETF 자주 묻는 질문",
                "input_placeholder": "주식/ETF 관련 질문을 입력하세요... (예: 섹터 점검, ETF 비교, 리스크 점검)",
                "expert_role": "당신은 주식·ETF 투자 분석 전문가입니다.",
                "quick_questions": [
                    ("증권 연결 점검", "현재 증권사 연결/설정 상태를 점검하고 문제 가능성을 알려주세요"),
                    ("ETF vs 주식", "지금 상황에서 ETF와 개별 주식 중 어떤 접근이 적절한지 비교해 주세요"),
                    ("섹터 리스크", "현재 시장에서 주의해야 할 섹터 리스크를 정리해 주세요"),
                    ("변동성 대응", "변동성이 큰 장에서 손실을 줄이는 대응 전략을 제안해 주세요"),
                    ("포지션 점검", "현재 포지션 운용이 공격적인지 보수적인지 평가해 주세요"),
                    ("수익/손실 리뷰", "최근 성과를 기준으로 개선 포인트를 제안해 주세요"),
                    ("매수 타이밍", "분할매수 관점에서 지금 진입 타이밍을 어떻게 볼지 설명해 주세요"),
                    ("ETF 후보", "현 시점에 점검할 만한 ETF 유형과 체크 기준을 알려주세요"),
                    ("설정 권장", "현재 설정에서 주식/ETF 운용에 맞는 권장 설정을 제안해 주세요")
                ]
            }

        if svc in ("real_estate", "asset"):
            return {
                "label": "자산통합",
                "quick_title": "자산통합 AI 상담",
                "input_placeholder": "자산 배분, 부동산, 포트폴리오 관련 질문을 입력하세요...",
                "expert_role": "당신은 개인 자산관리(PB) 전문가로서 부동산·금융자산을 통합적으로 분석합니다.",
                "quick_questions": [
                    ("자산 진단", "현재 자산 구성을 분석하고 개선 포인트를 알려주세요"),
                    ("리밸런싱 제안", "현재 자산 배분에서 리밸런싱이 필요한 부분을 제안해 주세요"),
                    ("부동산 vs 금융자산", "현재 상황에서 부동산과 금융자산 비중을 어떻게 조정할지 조언해 주세요"),
                    ("리스크 브리핑", "보유 자산의 주요 리스크 요인을 정리해 주세요"),
                    ("목표 달성 예측", "현재 자산 증가 속도로 목표 달성까지 얼마나 걸릴지 추산해 주세요"),
                    ("세금 최적화", "보유 자산 기준으로 절세 전략을 간략히 안내해 주세요"),
                    ("인플레이션 대응", "인플레이션 상황에서 자산을 보호할 방법을 알려주세요"),
                    ("노후 준비 점검", "현재 자산으로 노후 준비가 충분한지 점검해 주세요"),
                    ("투자 우선순위", "현재 여유 자금이 생겼을 때 어디에 먼저 투자할지 조언해 주세요")
                ]
            }

        if svc in ("other_investment", "other", "life_finance"):
            return {
                "label": "생활금융",
                "quick_title": "생활금융 AI 상담",
                "input_placeholder": "대출·보험·적금·생활비 관련 질문을 입력하세요...",
                "expert_role": "당신은 생활금융 전문 상담사로서 대출·보험·저축·현금흐름을 분석합니다.",
                "quick_questions": [
                    ("대출 비교", "현재 이용 가능한 대출 상품을 비교하고 최적안을 추천해 주세요"),
                    ("보험 점검", "현재 가입 보험이 충분한지 보장 공백을 점검해 주세요"),
                    ("적금 추천", "목표 금액과 기간에 맞는 적금/예금 상품을 추천해 주세요"),
                    ("현금흐름 분석", "수입·지출 패턴을 분석하고 개선 방안을 제안해 주세요"),
                    ("비상자금 점검", "비상자금이 충분한지 확인하고 적정 수준을 알려주세요"),
                    ("금융 목표 설정", "나이와 소득에 맞는 금융 목표를 설정하는 방법을 안내해 주세요"),
                    ("지출 절감", "생활비 중 절감 가능한 항목과 방법을 제안해 주세요"),
                    ("신용 관리", "신용점수를 올리는 방법과 주의할 점을 알려주세요"),
                    ("금리 전망 대응", "금리 변화에 대응하는 저축/대출 전략을 제안해 주세요")
                ]
            }

        if svc == "ai_analyst":
            return {
                "label": "AI 애널리스트",
                "quick_title": "AI 애널리스트 질문",
                "input_placeholder": "시장 분석, 투자 아이디어, 종합 전략을 질문하세요...",
                "expert_role": "당신은 멀티에셋 AI 투자 애널리스트입니다.",
                "quick_questions": [
                    ("시장 종합 진단", "현재 글로벌 시장 상황을 종합적으로 진단해 주세요"),
                    ("투자 아이디어", "현 시점에서 주목할 만한 투자 아이디어를 3가지 제안해 주세요"),
                    ("포트폴리오 최적화", "멀티에셋 관점에서 포트폴리오 최적화 방향을 제안해 주세요"),
                    ("리스크 분석", "현재 시장의 주요 리스크 요인을 분석해 주세요"),
                    ("시나리오 점검", "Bull·Base·Bear 시나리오별 대응 전략을 정리해 주세요"),
                ]
            }

        return {
            "label": "암호화폐",
            "quick_title": "자주 하는 질문",
            "input_placeholder": "AI에게 질문하거나 요청사항을 입력하세요...",
            "expert_role": "당신은 암호화폐 거래 전문가입니다.",
                "quick_questions": [
                    ("High vol 설정", "high vol 차단이 지금 켜져 있는지와 설정 위치, 남아 있는 가드레일을 알려줘"),
                    ("AI 커스텀 사용법", "AI 커스텀에서 외부 전략을 분석한 뒤 실제 적용하기까지 순서와 확인 항목을 알려줘"),
                    ("게이트 원인 점검", "수익성 검증 차단 원인을 최근 로그와 설정 기준(min_trades, min_win_rate, min_sharpe, min_walkforward_pass_rate)으로 요약해줘"),
                ("게이트 임시 OFF", "수익성 게이트를 임시 OFF(dev)로 전환하는 절차를 단계별로 안내하고, 적용 후 무엇을 점검해야 하는지 알려줘"),
                ("게이트 기준 완화", "수익성 게이트 기준 완화안을 제안해줘. min_trades, min_win_rate, min_sharpe, min_walkforward_pass_rate를 보수/중립/공격 3단계로 보여줘"),
                ("거래 부재 원인", "왜 거래가 발생하지 않고 있나요? 원인을 분석해주세요"),
                ("수익률 개선", "현재 수익률을 개선할 방법을 제안해주세요"),
                ("리스크 점검", "현재 리스크 상황을 점검하고 위험 요소를 알려주세요"),
                ("전략 평가", "현재 거래 전략의 장단점을 평가해주세요"),
                ("레버리지 증가", "레버리지를 높여서 더 적극적으로 거래하고 싶어요"),
                ("안전 모드", "손실을 줄이고 싶어요. 보수적으로 거래하도록 설정해주세요"),
                ("시장 상황", "현재 암호화폐 시장 상황과 전망을 알려주세요"),
                ("코인 분석", "현재 선택된 코인들의 분석 결과를 보여주세요"),
                ("거래 성과", "최근 거래 성과와 통계를 요약해주세요")
            ]
        }

    def set_service_context(self, service_name: str, announce: bool = False):
        """대시보드 서비스 전환에 맞춰 어시스턴트 컨텍스트를 동기화"""
        try:
            prev = getattr(self, 'assistant_service_context', 'blockchain')
            self.assistant_service_context = (service_name or 'blockchain').strip().lower()

            # 입력창 placeholder 갱신
            if hasattr(self, 'chat_input') and self.chat_input is not None:
                self.chat_input.configure(placeholder_text=self._build_input_placeholder())

            # 퀵 질문 패널 갱신
            self.create_quick_question_buttons()

            if announce and prev != self.assistant_service_context:
                profile = self._get_service_profile(self.assistant_service_context)
                self.add_ai_message(f"AI 어시스턴트가 {profile['label']} 분석 모드로 전환되었습니다.")
        except Exception as e:
            self.logger.debug(f"서비스 컨텍스트 전환 실패: {e}")

    def send_quick_question(self, question: str):
        """빠른 질문 전송"""
        try:
            self.chat_input.delete(0, "end")
            self.chat_input.insert(0, question)
            self.send_ai_message()
        except Exception as e:
            self.logger.error(f"빠른 질문 전송 오류: {e}")

    def update_model_caption(self):
        """하위 호환용 no-op: 내부 모델명은 대화 화면에 노출하지 않는다."""
        self.model_caption = None

    def _get_onboarding_questions(self) -> List[Dict[str, Any]]:
        """초기 설정 가이드 질문 목록을 반환한다."""
        return [
            {
                'key': 'goal',
                'title': 'Q1/5 목표 성향',
                'prompt': '이번 주 운영 목표에 가장 가까운 선택을 입력해 주세요.',
                'options': ['1) 안정 우선', '2) 균형', '3) 성장 우선'],
                'hint': '예: 1 또는 안정',
            },
            {
                'key': 'risk',
                'title': 'Q2/5 리스크 허용도',
                'prompt': '허용 가능한 변동성/손실 수준을 선택해 주세요.',
                'options': ['1) 낮음', '2) 중간', '3) 높음'],
                'hint': '예: 2 또는 중간',
            },
            {
                'key': 'budget',
                'title': 'Q3/5 월 AI 예산 감각',
                'prompt': 'AI 비용 기준을 선택해 주세요.',
                'options': ['1) 절약', '2) 보통', '3) 정밀'],
                'hint': '예: 1 또는 절약',
            },
            {
                'key': 'apply_mode',
                'title': 'Q4/5 설정 반영 방식',
                'prompt': '거래 관련 설정은 항상 사용자 최종확인 후 반영됩니다.',
                'options': ['1) 사용자 최종확인(필수)'],
                'hint': '1 또는 최종확인',
            },
            {
                'key': 'recheck',
                'title': 'Q5/5 재검증 기준',
                'prompt': '언제 재조정할지 기준을 선택해 주세요.',
                'options': ['1) 7일 후 재검증', '2) 최소 거래 표본 충족 후 재검증'],
                'hint': '예: 1 또는 7일',
            },
        ]

    def _format_onboarding_question(self) -> str:
        """현재 스텝에 맞는 온보딩 질문 문자열을 생성한다."""
        questions = self._get_onboarding_questions()
        if self._onboarding_step < 0 or self._onboarding_step >= len(questions):
            return ""
        q = questions[self._onboarding_step]
        lines = [f"{q['title']}", q['prompt']] + [f"- {opt}" for opt in q['options']] + [f"입력 가이드: {q['hint']}"]
        return "\n".join(lines)

    def start_initial_onboarding(self, source: str = "assistant"):
        """초기 AI 온보딩(5문항)을 시작한다."""
        self._onboarding_active = True
        self._onboarding_step = 0
        self._onboarding_source = source
        self._onboarding_answers = {}

        self.add_ai_message("초기 AI 설정 가이드를 시작합니다. 총 5문항이며 1~2분 내 완료됩니다.")
        self.add_ai_message("ℹ진행 중에는 '취소' 또는 '중단' 입력으로 언제든 종료할 수 있습니다.")
        self.add_ai_message(self._format_onboarding_question())

    def _parse_onboarding_answer(self, key: str, message: str) -> Optional[str]:
        """온보딩 질문별 입력을 내부 코드값으로 변환한다."""
        raw = (message or '').strip().lower()
        compact = raw.replace(' ', '')

        aliases: Dict[str, Dict[str, str]] = {
            'goal': {
                '1': 'stable', '안정': 'stable', '안정우선': 'stable',
                '2': 'balanced', '균형': 'balanced',
                '3': 'growth', '성장': 'growth', '성장우선': 'growth',
            },
            'risk': {
                '1': 'low', '낮음': 'low', '보수': 'low',
                '2': 'mid', '중간': 'mid', '보통': 'mid',
                '3': 'high', '높음': 'high', '공격': 'high',
            },
            'budget': {
                '1': 'save', '절약': 'save',
                '2': 'balanced', '보통': 'balanced', '균형': 'balanced',
                '3': 'quality', '정밀': 'quality', '품질': 'quality',
            },
            'apply_mode': {
                '1': 'user_confirm', '최종확인': 'user_confirm', '사용자최종확인': 'user_confirm',
                '2': 'user_confirm', '자동적용': 'user_confirm', 'ai자동적용': 'user_confirm',
            },
            'recheck': {
                '1': 'days7', '7일': 'days7', '7일후': 'days7',
                '2': 'sample', '표본': 'sample', '최소표본': 'sample',
            },
        }

        lookup = aliases.get(key, {})
        if compact in lookup:
            return lookup[compact]

        # 숫자/문장형 입력의 선행 토큰 보정
        token = compact.split(',')[0].split('.')[0]
        if token in lookup:
            return lookup[token]

        return None

    def _finalize_initial_onboarding(self):
        """온보딩 응답을 기반으로 추천 설정을 계산하고 적용을 진행한다."""
        answers = dict(self._onboarding_answers)

        preset_map: Dict[str, Dict[str, Any]] = {
            'save': {
                'openai_model': 'gpt-4o-mini',
                'assistant_ai_model': 'gpt-4o-mini',
                'ai_model_roles': {
                    'frequent_cheap': 'gpt-4o-mini',
                    'standard': 'gpt-4o-mini',
                    'premium': 'gpt-4o',
                },
                'cost_level': '낮음',
            },
            'balanced': {
                'openai_model': 'gpt-4o-mini',
                'assistant_ai_model': 'gpt-4o',
                'ai_model_roles': {
                    'frequent_cheap': 'gpt-4o-mini',
                    'standard': 'gpt-4o',
                    'premium': 'gpt-4o',
                },
                'cost_level': '중간',
            },
            'quality': {
                'openai_model': 'gpt-4o',
                'assistant_ai_model': 'gpt-4o',
                'ai_model_roles': {
                    'frequent_cheap': 'gpt-4o-mini',
                    'standard': 'gpt-4o',
                    'premium': 'gpt-5',
                },
                'cost_level': '높음',
            },
        }

        goal_map = {
            'stable': {'default_leverage': 2, 'default_tp': 0.012, 'default_sl': 0.010},
            'balanced': {'default_leverage': 3, 'default_tp': 0.016, 'default_sl': 0.012},
            'growth': {'default_leverage': 4, 'default_tp': 0.020, 'default_sl': 0.014},
        }
        risk_map = {
            'low': {'risk_tolerance': 'CONSERVATIVE', 'balance_utilization_limit': 0.15},
            'mid': {'risk_tolerance': 'MODERATE', 'balance_utilization_limit': 0.22},
            'high': {'risk_tolerance': 'AGGRESSIVE', 'balance_utilization_limit': 0.30},
        }

        selected_preset = preset_map.get(answers.get('budget', 'balanced'), preset_map['balanced'])
        selected_goal = goal_map.get(answers.get('goal', 'balanced'), goal_map['balanced'])
        selected_risk = risk_map.get(answers.get('risk', 'mid'), risk_map['mid'])
        apply_mode = 'user_confirm'
        recheck_policy = answers.get('recheck', 'days7')

        staged_note = ""
        if answers.get('risk') == 'high':
            # 고위험 요청은 1차 적용을 완화하고 관찰 후 재조정한다.
            selected_risk = {'risk_tolerance': 'MODERATE', 'balance_utilization_limit': 0.25}
            selected_goal = {'default_leverage': 3, 'default_tp': 0.018, 'default_sl': 0.013}
            apply_mode = 'user_confirm'
            staged_note = "고위험 요청은 안전 정책에 따라 1차는 균형 모드로 적용하고 재검증 후 상향합니다."

        settings_payload: Dict[str, Any] = {
            'openai_model': selected_preset['openai_model'],
            'assistant_ai_model': selected_preset['assistant_ai_model'],
            'ai_model_roles': selected_preset['ai_model_roles'],
            'assistant_apply_mode': apply_mode,
            **selected_goal,
            **selected_risk,
        }

        recheck_text = '7일 후 재검증' if recheck_policy == 'days7' else '최소 거래 표본 충족 후 재검증'
        goal_label = {'stable': '안정 우선', 'balanced': '균형', 'growth': '성장 우선'}.get(answers.get('goal', 'balanced'), '균형')
        risk_label = {'low': '낮음', 'mid': '중간', 'high': '높음(요청)'}.get(answers.get('risk', 'mid'), '중간')

        explain_lines = [
            "초기 온보딩 결과 요약",
            f"- 목표: {goal_label}",
            f"- 리스크 허용도: {risk_label}",
            f"- 예상 비용 레벨: {selected_preset.get('cost_level', '-')}",
            "- 적용 방식: 사용자 최종확인(필수)",
            f"- 재검증 기준: {recheck_text}",
            "",
            "왜 이 설정인가:",
            "- 빈번 호출은 비용 효율 모델로, 진단은 상대적으로 고품질 모델로 분리해 비용/품질 균형을 맞춥니다.",
            "- 목표/리스크 응답을 바탕으로 레버리지·TP·SL·자금노출을 초기값으로 제한합니다.",
        ]
        if staged_note:
            explain_lines.append(f"- 안전 가드: {staged_note}")

        self.add_ai_message("\n".join(explain_lines))

        try:
            if not self._confirm_settings_apply(settings_payload):
                self.add_ai_message("↩초기 온보딩 적용이 취소되었습니다. 기존 설정은 유지됩니다.")
                return
            self._apply_settings_automatically(settings_payload, "초기 AI 온보딩")
            self.add_ai_message(f"초기 설정 가이드 적용이 완료되었습니다. 다음 점검 시점: {recheck_text}")
        except Exception as e:
            self.logger.error(f"초기 온보딩 적용 실패: {e}")
            self.add_ai_message(f"초기 온보딩 적용 중 오류가 발생했습니다: {e}")

    def _consume_onboarding_answer(self, message: str) -> bool:
        """온보딩 진행 중 사용자 입력을 처리한다."""
        if not self._onboarding_active:
            return False

        raw = (message or '').strip().lower()
        if raw in ('취소', '중단', '그만', 'cancel', 'stop'):
            self._onboarding_active = False
            self._onboarding_step = 0
            self._onboarding_answers = {}
            self.add_ai_message("↩초기 AI 설정 가이드를 중단했습니다. 기존 설정은 변경되지 않았습니다.")
            return True

        questions = self._get_onboarding_questions()
        if self._onboarding_step >= len(questions):
            self._onboarding_active = False
            return True

        current = questions[self._onboarding_step]
        parsed = self._parse_onboarding_answer(current['key'], message)
        if parsed is None:
            self.add_ai_message(f"입력을 이해하지 못했습니다. {current['hint']} 형태로 다시 입력해 주세요.")
            self.add_ai_message(self._format_onboarding_question())
            return True

        self._onboarding_answers[current['key']] = parsed
        self._onboarding_step += 1

        if self._onboarding_step < len(questions):
            self.add_ai_message(self._format_onboarding_question())
            return True

        self._onboarding_active = False
        self._finalize_initial_onboarding()
        return True

    @staticmethod
    def _normalize_model_name(model_name: str) -> str:
        """모델명 정규화: 잘못된 모델명을 올바른 형식으로 수정

        OpenAI 외 DeepSeek, Claude, Ollama 등 타사 모델도 그대로 통과시킵니다.
        명백히 오타로 판단되는 패턴만 수정합니다.

        Args:
            model_name: 정규화할 모델명 (None이거나 빈 문자열일 수 있음)

        Returns:
            정규화된 모델명 (빈 값이면 'gpt-4o' 반환)
        """
        if not model_name:
            return 'gpt-4o'

        model_name = model_name.strip()
        if not model_name:
            return 'gpt-4o'

        # 잘못된 모델명 패턴 수정 (사용자가 실수로 입력한 경우 대비)
        model_fixes = {
            'gpt4-4o': 'gpt-4o',
            'gpt4o': 'gpt-4o',
            'gpt-4-4o': 'gpt-4o',
            'gpt4': 'gpt-4o',
            'gpt-4': 'gpt-4o',
        }

        if model_name.lower() in model_fixes:
            return model_fixes[model_name.lower()]

        # 알려진 오타 외에는 그대로 통과 (DeepSeek, Claude, Ollama 등 지원)
        return model_name

    def set_assistant_model(self, model_name: str, announce: bool = True):
        """런타임에 어시스턴트 모델을 재설정하고 캡션을 갱신합니다."""
        try:
            model_name = (model_name or '').strip() or 'gpt-4o-mini'
            # 모델명 정규화 적용
            normalized_model = self._normalize_model_name(model_name)
            prev = getattr(self, 'assistant_model_name', None)
            self.assistant_model_name = normalized_model
            self.update_model_caption()
            if announce and prev and (prev != normalized_model):
                self.add_ai_message(f"어시스턴트 모델이 '{prev}' → '{normalized_model}' 로 변경되었습니다.")
        except Exception:
            pass

    def on_ai_chat_enable_changed(self):
        """AI 대화 기능 활성화/비활성화"""
        try:
            if hasattr(self, 'ai_chat_enable_checkbox') and self.ai_chat_enable_checkbox:
                self.ai_chat_enabled = bool(self.ai_chat_enable_checkbox.get())
            else:
                self.ai_chat_enabled = True
            if self.ai_chat_enabled:
                self.add_ai_message("AI 대화 기능이 활성화되었습니다. 자유롭게 질문해 보세요!")
            else:
                self.add_ai_message("AI 대화 기능이 비활성화되었습니다.")
        except Exception:
            pass

    def add_ai_message(self, message: str):
        """AI 메시지를 채팅 영역에 추가하고 스크롤을 하단으로 이동"""
        try:
            # 빈 줄은 구분선 역할
            if not (message or "").strip():
                label = CTkLabel(
                    self.chat_messages_frame,
                    text="─" * 50,
                    font=ctk.CTkFont(size=10),
                    text_color=self._color("text_secondary"),
                    justify="center"
                )
                label.pack(pady=2, padx=5, anchor="w")
            else:
                # 메시지 + 복사 버튼을 담는 행 컨테이너
                msg_row = CTkFrame(self.chat_messages_frame, fg_color="transparent")
                msg_row.pack(pady=2, padx=5, anchor="w", fill="x")
                msg_row.grid_columnconfigure(0, weight=1)

                label = CTkLabel(
                    msg_row,
                    text=f"{message}",
                    font=ctk.CTkFont(size=12),
                    text_color=self._color("text_primary"),
                    justify="left",
                    wraplength=410
                )
                label.grid(row=0, column=0, sticky="w", padx=(0, 4))

                # 복사 버튼 (클립보드에 메시지 전체 복사)
                def _copy_msg(msg=message):
                    try:
                        self.clipboard_clear()
                        self.clipboard_append(msg)
                    except Exception:
                        pass

                copy_btn = CTkButton(
                    msg_row,
                    text="복사",
                    width=46,
                    height=22,
                    font=ctk.CTkFont(size=11),
                    fg_color="transparent",
                    hover_color=self._color("hover", "#374151"),
                    command=_copy_msg,
                )
                copy_btn.grid(row=0, column=1, sticky="ne", padx=(0, 2), pady=(2, 0))

            try:
                self.chat_history.update()
                self.chat_history._parent_canvas.yview_moveto(1.0)
            except Exception:
                pass

            # 대화 로그 누적 (복사/내보내기용)
            if (message or '').strip():
                try:
                    from datetime import datetime as _dt
                    ts = _dt.now().strftime('%H:%M')
                    self._chat_history_log.append(f"[{ts}] AI: {message}")
                except Exception:
                    pass
                try:
                    if not hasattr(self, "_conversation_messages"):
                        self._conversation_messages = []
                    self._conversation_messages.append({"role": "assistant", "content": str(message)})
                    self._conversation_messages = self._conversation_messages[-16:]
                except Exception:
                    pass

            # 음성 출력은 설정으로 켜진 경우에만 수행
            try:
                if self.voice_module and getattr(self.voice_module, 'config', None):
                    if self.voice_module.config.auto_tts and message and message.strip():
                        speech_text = str(message).replace('AI 분석 결과:\n', '').strip()
                        self.voice_module.speak(speech_text)
            except Exception:
                pass
        except Exception:
            pass

    def send_ai_message(self):
        """AI 메시지 전송"""
        message = self.chat_input.get().strip()
        if not message:
            return

        # 첫 번째 실제 질문 시 초기 메시지들 제거
        if not hasattr(self, '_first_message_sent'):
            self._first_message_sent = True
            # 초기 메시지들 제거
            for widget in self.chat_messages_frame.winfo_children():
                widget.destroy()

        # AI 대화 기능은 항상 활성화됨 (체크박스 제거됨)

        # 사용자 메시지 추가
        user_message_label = CTkLabel(
            self.chat_messages_frame,
            text=f"사용자: {message}",
            font=ctk.CTkFont(size=12),
            text_color=self._color("success"),
            justify="left",
            wraplength=450  # 스크롤 영역에 맞게 조절
        )
        user_message_label.pack(pady=2, padx=5, anchor="w")

        # 스크롤을 맨 아래로 (안전한 방법)
        try:
            self.chat_history.update()
            self.chat_history._parent_canvas.yview_moveto(1.0)
        except:
            # 스크롤 실패 시 무시
            pass

        # 입력창 초기화
        self.chat_input.delete(0, "end")

        # 대화 로그에 사용자 메시지 누적
        try:
            from datetime import datetime as _dt
            ts = _dt.now().strftime('%H:%M')
            self._chat_history_log.append(f"[{ts}] 사용자: {message}")
        except Exception:
            pass
        try:
            if not hasattr(self, "_conversation_messages"):
                self._conversation_messages = []
            self._conversation_messages.append({"role": "user", "content": message})
            self._conversation_messages = self._conversation_messages[-16:]
        except Exception:
            pass

        # AI 응답 생성
        self.generate_ai_response(message)

    def _current_strategy_engine_policy(self) -> Dict[str, Any]:
        """현재 고급 전략 엔진 정책을 대시보드/설정 파일 순으로 읽는다."""
        settings: Dict[str, Any] = {}
        dashboard = getattr(self, "parent_dashboard", None)
        if dashboard is not None and isinstance(getattr(dashboard, "settings", None), dict):
            settings = dashboard.settings
        else:
            try:
                from config.settings import load_settings
                loaded = load_settings() or {}
                settings = loaded if isinstance(loaded, dict) else {}
            except Exception:
                settings = {}
        layers = settings.get("advanced_trading_layers", {})
        if not isinstance(layers, dict):
            return {}
        policy = layers.get("strategy_engine", {})
        return dict(policy) if isinstance(policy, dict) else {}

    @staticmethod
    def _is_high_vol_topic(message: str) -> bool:
        normalized = str(message or "").lower().replace("-", " ").replace("_", " ")
        return any(
            token in normalized
            for token in ("high vol", "highvol", "고변동", "높은 변동성", "변동성 차단")
        )

    def _build_high_vol_support(self, message: str) -> Optional[Dict[str, Any]]:
        """고변동장 설정 질문을 제품 실제값 기준으로 안내하거나 변경 제안한다."""
        if not self._is_high_vol_topic(message):
            return None

        raw = str(message or "")
        lower = raw.lower()
        policy = self._current_strategy_engine_policy()
        current_action = str(policy.get("high_vol_action", "evaluate") or "evaluate").lower()
        current_action = "block" if current_action == "block" else "evaluate"
        current_label = "항상 차단" if current_action == "block" else "평가 계속"
        engine_enabled = bool(policy.get("enabled", False))
        consensus = float(policy.get("consensus_threshold", 0.60) or 0.60)
        cooldown = int(policy.get("cooldown_sec", 60) or 0)

        wants_release = any(
            token in lower for token in ("차단 해제", "차단을 해제", "해제해", "열어줘", "평가 계속", "evaluate")
        )
        wants_block = any(
            token in lower for token in ("항상 차단", "차단해줘", "차단 해줘", "block으로", "block 으로")
        )
        asks_location = any(
            token in lower
            for token in ("어디서", "어디에", "방법", "어떻게", "설정하면", "설정 위치", "될까요", "하고 싶")
        )
        explicit_apply = any(
            token in lower for token in ("해제해줘", "해제해 줘", "차단해줘", "차단 해줘", "적용해줘", "바꿔줘")
        ) and not asks_location

        if wants_release and wants_block:
            return {
                "message": (
                    "NoahAI입니다. 요청에 ‘차단 해제’와 ‘항상 차단’이 함께 있어 방향을 확정할 수 없습니다.\n"
                    "고변동장도 합의 점수와 가드레일로 평가하려면 ‘평가 계속’, 전부 막으려면 ‘항상 차단’이라고 답해 주세요."
                )
            }

        status = (
            f"현재값: 전략 엔진 {'ON' if engine_enabled else 'OFF'} / 고변동장 {current_label} / "
            f"합의 임계값 {consensus:.2f} / 심볼 쿨다운 {cooldown}초"
        )
        route = (
            "설정 위치: 대시보드 상단 설정 → 고급 자동매매 → 전략 엔진 세부 설정 → 고변동장 처리"
        )
        safety = (
            "‘평가 계속’은 고변동장 주문을 무조건 허용하는 기능이 아닙니다. "
            "신호 합의 임계값, 수익성 검증, AI 커스텀 조건, 포지션·손실 한도와 주문 가드레일은 그대로 적용됩니다. "
            "OpenAI 최신 모델은 분석 품질을 보조하지만 이 가드레일을 대신 검증하거나 우회하지 않으며 거래 기회를 보장하지 않습니다."
        )

        if explicit_apply:
            target = "evaluate" if wants_release else ("block" if wants_block else "")
            if not target:
                return {
                    "message": (
                        f"NoahAI입니다. {status}\n"
                        "고변동장 처리를 ‘평가 계속’으로 바꿀지, ‘항상 차단’으로 바꿀지 한 번 더 알려 주세요."
                    )
                }
            if target == current_action:
                return {
                    "message": (
                        f"NoahAI입니다. {status}\n이미 요청한 상태라 설정을 바꿀 필요가 없습니다.\n"
                        f"{route}\n{safety}\n"
                        "거래 기회가 여전히 적다면 최근 로그에서 수익성 게이트, 합의 점수, 쿨다운, AI 커스텀 조건 중 "
                        "실제 차단 원인을 먼저 확인해 주세요."
                    )
                }
            return {
                "message": (
                    f"NoahAI입니다. {status}\n"
                    f"고변동장 처리를 ‘{'평가 계속' if target == 'evaluate' else '항상 차단'}’으로 제안합니다.\n"
                    f"{safety}\n아래 적용을 누른 뒤 최종 확인해야 저장됩니다."
                ),
                "proposal": {"strategy_engine_high_vol_action": target},
            }

        return {
            "message": (
                f"NoahAI입니다. {status}\n{route}\n{safety}\n"
                + (
                    "현재 이미 ‘평가 계속’이므로 high vol 일괄 차단은 해제된 상태입니다. "
                    "거래 기회를 더 보려면 차단 해제보다 실제 최근 로그의 차단 사유를 먼저 점검하는 것이 정확합니다."
                    if current_action == "evaluate"
                    else
                    "현재는 ‘항상 차단’입니다. 실제 변경을 원하면 ‘high vol 차단을 해제해줘’라고 요청하면 "
                    "변경 전/후를 보여드리고 2단계 확인 후 저장합니다."
                )
            )
        }

    def _build_ai_custom_support(self, message: str) -> Optional[str]:
        """AI 커스텀·XAI·외부 전략의 실제 적용 경계를 API 없이도 설명한다."""
        lower = str(message or "").lower().replace("-", " ")
        is_topic = any(
            token in lower
            for token in (
                "ai 커스텀", "ai커스텀", "xai", "외부 전략", "유튜브 전략",
                "youtube 전략", "tradingview 전략", "pine 전략",
            )
        )
        if not is_topic:
            return None

        settings: Dict[str, Any] = {}
        dashboard = getattr(self, "parent_dashboard", None)
        if dashboard is not None and isinstance(getattr(dashboard, "settings", None), dict):
            settings = dashboard.settings
        else:
            try:
                from config.settings import load_settings
                settings = load_settings() or {}
            except Exception:
                settings = {}
        runtime = settings.get("ai_custom_runtime", {})
        runtime_enabled = bool(runtime.get("enabled", False)) if isinstance(runtime, dict) else False

        return (
            "NoahAI입니다. NoahAI는 TradingView를 없애는 제품이 아니라, TradingView·영상·문서·Pine 전략을 "
            "AI가 이해하고 검증하여 시장국면에 맞게 안전하게 운용하는 상위 전략 운영 계층입니다.\n"
            f"현재 AI 커스텀 실자동매매 사용 스위치: {'ON' if runtime_enabled else 'OFF'}\n"
            "사용 순서: AI 커스텀 → 텍스트/Pine/PDF/차트/영상/YouTube/TradingView 입력 → "
            "AI 분석 및 전략 초안 → XAI의 출처 근거·진입/청산·손절/익절·위험예산·누락 조건 확인 → "
            "적용 범위·시장상황·전략 역할 선택 → 버전 저장 → 사용자 승인 → 자동검증 → 최종 적용 → 거래소/증권 시작.\n"
            "원본 전략이 바뀌면 자료를 다시 입력하고 기존 전략을 저장 대상으로 골라 새 버전을 만들면 됩니다. "
            "한 번의 자동검증 결과를 본 뒤 일반 운용 또는 허용된 1배·최대 1% 안전 시험은 사용자가 결정합니다.\n"
            "XAI의 ‘규칙’은 원문에서 구조화한 조건이고, ‘실행 엔진 적용값’은 주문 판단에 전달할 TP/SL·포지션·임계값입니다. "
            "현재 선언형 실행은 RSI·MACD·볼린저·SMA/EMA 20·50·200·ADX·ATR·거래량·시간 조건과 "
            "명시적 코인 청산 조건을 지원하며, 미지원 필드는 승인 전에 차단합니다. 자동검증은 진입·청산 양쪽 수수료, "
            "슬리피지와 스프레드를 분리해 총비용 반영 PnL·Profit Factor·기대값·국면별 결과를 보여줍니다.\n"
            "자막·화면·Pine 근거가 없거나 조건이 빠지면 추정하지 않고 승인·실행을 차단합니다.\n"
            "사용자가 원하는 장에는 모든 시장상황/상승/하락/횡보/고변동/저변동 중 선택해 적용할 수 있고 "
            "거래소·증권사별 범위도 고를 수 있습니다. 다만 지원하지 않는 지표·보호된 스크립트·불완전한 영상은 "
            "원문 보강이 필요합니다. 적용된 전략도 실제 주문 때 NoahAI 시장판단과 수익성·리스크·주문 가드레일을 다시 통과합니다."
        )

    @staticmethod
    def _build_financial_intelligence_support(message: str) -> Optional[str]:
        """금융 인텔리전스 메뉴 사용법을 API 없이도 정확히 안내한다."""
        raw = str(message or "")
        lower = raw.lower().replace(" ", "")
        topic_tokens = (
            "금융인텔리전스", "시장·섹터", "시장섹터", "코인탐색", "종목탐색",
            "지표탐색", "전략검증", "이벤트·속보", "이벤트속보", "기업분석",
            "가치평가", "기관동향", "코인정보",
        )
        if not any(token.replace(" ", "") in lower for token in topic_tokens):
            return None

        intro = (
            "NoahAI입니다. 금융 인텔리전스는 시장·종목·뉴스·전략을 분석하는 판단 보조 화면이며, "
            "조회 결과만으로 주문하거나 거래 설정을 바꾸지 않습니다.\n"
        )
        if "코인정보" in lower or "코인탐색" in lower:
            return intro + (
                "• 코인 정보: 내 계좌·현재 선택 코인·보유/운용 상태를 확인하는 화면입니다.\n"
                "• 코인 탐색: 여러 코인을 공개 시세와 조건으로 비교해 검토 후보를 찾는 시장 검색 화면입니다.\n"
                "사용 순서: 블록체인 → 금융 인텔리전스 → 코인 탐색 → 관심 코인을 쉼표로 입력 → "
                "최소 가격 선택 → 조건 검색 → 출처·기준시각·수집 오류 확인. 후보가 나와도 자동 주문되지는 않습니다."
            )
        if "전략검증" in lower:
            return intro + (
                "사용 순서: 금융 인텔리전스 → 전략 검증 → 종목과 빠른/느린 이동평균 입력 → 전략 검증 실행 → "
                "거래 수·수수료·슬리피지·최대낙폭을 함께 확인합니다. 이 화면은 간단한 이동평균 전략 비교용이며, "
                "AI 커스텀에서 승인한 외부 전략의 최종 실거래 적용 화면과는 역할이 다릅니다."
            )
        if "지표탐색" in lower:
            return intro + (
                "사용 순서: 금융 인텔리전스 → 지표 탐색 → 종목 입력 → 지표 조회 → "
                "가격 차트와 RSI·MACD·이동평균·볼린저밴드의 방향 및 신호 충돌을 함께 확인합니다."
            )
        if "시장·섹터" in raw or "시장섹터" in lower:
            return intro + (
                "사용 순서: 시장·섹터 → 주요/국내/미국/가상자산 프리셋 선택 → 시장 현황 조회 → "
                "출처·기준시각 → 수익률 → 변동성 순으로 읽습니다. 직접 입력을 고르면 관심 종목만 비교할 수 있습니다."
            )
        if "이벤트" in lower or "속보" in lower or "기관동향" in lower:
            return intro + (
                "조회 버튼을 누른 뒤 발생 시각·출처·보유자산 관련성을 확인하세요. "
                "'운영 데이터 연결 필요'는 사용자의 입력 오류가 아니라 허가된 공급자 연결 전 상태이며, "
                "NoahAI는 그때 임의 뉴스·공시·기관 수치를 만들지 않습니다."
            )
        if "기업분석" in lower or "가치평가" in lower or "종목탐색" in lower:
            return intro + (
                "기업 분석은 DART/SEC 공시 재무를, 가치평가는 입력한 현금흐름 가정의 범위를, "
                "종목 탐색은 여러 종목의 조건 통과 여부를 봅니다. 결과의 출처·기준시각·계산 가정을 먼저 확인하고 "
                "실제 주문 전 계좌 상태와 가드레일을 별도로 점검하세요."
            )
        return intro + (
            "기본 순서: 원하는 하위 메뉴 선택 → 종목/프리셋 입력 → 조회 → 출처·기준시각 확인 → "
            "수익·위험·오류 표시 확인. 각 화면 상단의 'AI에게 사용법 묻기'를 누르면 현재 메뉴에 맞춰 다시 설명합니다."
        )

    @staticmethod
    def _build_membership_support(message: str) -> Optional[str]:
        """레퍼럴 회원 정책과 관리 경계를 API 없이도 정확히 안내한다."""
        raw = str(message or "")
        lower = raw.lower().replace(" ", "")
        if not any(token in lower for token in (
            "레퍼럴", "리퍼럴", "referral", "무료회원", "회원등급",
        )):
            return None

        if any(token in lower for token in ("코드", "가입링크", "어디서관리", "어디서설정")):
            return (
                "NoahAI입니다. 레퍼럴 코드와 가입 URL은 클라이언트 파일에 넣지 않고 "
                "daltrading 관리자 포털의 ‘설정 → 레퍼럴 거래소 설정’에서 관리합니다. "
                "관리자가 활성화한 Binance·Bybit·OKX·Bitget만 서버 정책에 포함되며, "
                "사용자는 자신의 클라이언트에서 이 허용 목록을 임의로 늘릴 수 없습니다."
            )
        if any(token in lower for token in (
            "업비트", "빗썸", "국내거래소", "증권", "주식", "사용가능", "뭘쓸",
        )):
            return (
                "NoahAI입니다. 레퍼럴 등급은 관리자가 활성화한 해외 제휴 거래소 "
                "Binance·Bybit·OKX·Bitget만 사용할 수 있습니다. Upbit·Bithumb 같은 국내 거래소와 "
                "국내·해외 증권 기능은 사용할 수 없습니다. 등급이나 허용 목록이 줄어들면 새 주문 루프는 "
                "중지되지만, 안전을 위해 보유 포지션을 임의로 강제 청산하지는 않으므로 계좌 상태를 직접 확인하세요."
            )
        return (
            "NoahAI입니다. 레퍼럴 등급은 CD-Key 없이 가입하는 무료 회원등급이며, "
            "daltrading 서버 관리자가 활성화한 해외 제휴 거래소만 사용할 수 있습니다. "
            "현재 공식 범위는 Binance·Bybit·OKX·Bitget이고 국내 거래소와 증권 기능은 제외됩니다. "
            "등급과 허용 목록은 로그인 및 주기적 상태 확인으로 동기화됩니다."
        )

    @staticmethod
    def _build_identity_support(message: str) -> Optional[str]:
        lower = str(message or "").strip().lower().replace(" ", "")
        identity_patterns = {
            "너누구야", "누구세요", "누구야", "정체가뭐야", "너는뭐야",
            "노아ai야", "noahai야", "노아ai인가요", "noahai인가요",
        }
        if lower in identity_patterns:
            return (
                "저는 NoahAI입니다. 이 클라이언트의 사용법·현재 설정·로그·AI 커스텀 전략을 설명하고, "
                "허용된 설정은 변경 전/후와 위험을 보여 드린 뒤 사용자 확인을 거쳐 반영하도록 돕습니다."
            )
        return None

    def _build_settings_clarification(self, message: str) -> Optional[str]:
        """목표나 방향이 빠진 변경 요청은 추정 적용 대신 짧게 재질문한다."""
        lower = str(message or "").strip().lower()
        if not self._is_settings_change_request(message):
            return None
        if self._is_high_vol_topic(message):
            return None
        if any(token in lower for token in ("모델 바꿔", "모델 변경", "모델을 바꿔")) and not any(
            token in lower for token in ("어시스턴트", "애널리스트", "빈번", "표준", "정밀", "premium", "standard")
        ):
            return (
                "NoahAI입니다. 어떤 역할의 모델을 바꿀지 확인이 필요합니다. "
                "‘AI 어시스턴트(대화)’, ‘AI 애널리스트(시장 분석)’, 또는 ‘정밀 진단(premium)’ 중 하나와 "
                "원하는 모델명·비용 우선순위를 알려 주세요."
            )
        vague_only = {
            "설정 바꿔줘", "설정을 바꿔줘", "설정 변경해줘", "더 공격적으로", "더 보수적으로",
            "거래 기회를 늘려줘", "거래를 더 하게 해줘",
        }
        if lower in vague_only:
            return (
                "NoahAI입니다. 어떤 제약을 바꿀지 확정하기 어렵습니다. "
                "레버리지·잔고 활용·고변동장 처리·합의 임계값 중 원하는 항목을 말해 주세요. "
                "거래 기회 확대가 목적이면 먼저 최근 로그의 실제 차단 사유를 점검해 달라고 요청하는 것이 가장 안전합니다."
            )
        return None

    def _recent_conversation_for_prompt(self) -> str:
        """현재 질문 직전의 최근 대화만 짧게 직렬화한다."""
        history = list(getattr(self, "_conversation_messages", []) or [])
        if history and history[-1].get("role") == "user":
            history = history[:-1]
        lines: List[str] = []
        for item in history[-8:]:
            role = "사용자" if item.get("role") == "user" else "NoahAI"
            content = str(item.get("content") or "").strip().replace("\x00", "")
            if content:
                lines.append(f"{role}: {content[:700]}")
        return "\n".join(lines) if lines else "이전 대화 없음"

    def generate_ai_response(self, message: str):
        """AI 응답 생성"""
        try:
            # ── 로컬 명령어 인터셉트 ──────────────────────────────
            msg_lower = message.strip().lower()
            if msg_lower in ("초기 온보딩", "온보딩", "초기 설정", "ai로 초기 설정"):
                self.start_initial_onboarding(source="chat_command")
                return

            if self._onboarding_active:
                self._consume_onboarding_answer(message)
                return

            if msg_lower.startswith("지표 추가"):
                indicator_name = message.strip()[5:].strip()
                if indicator_name:
                    result = self._handle_add_custom_indicator(indicator_name)
                    self.add_ai_message(result)
                else:
                    self.add_ai_message("지표 이름을 입력해 주세요. 예: '지표 추가 RSI_14'")
                return
            if msg_lower.startswith("지표 삭제") or msg_lower.startswith("지표 제거"):
                indicator_name = message.strip()[5:].strip()
                result = self._handle_remove_custom_indicator(indicator_name)
                self.add_ai_message(result)
                return
            if msg_lower in ("지표 목록", "커스텀 지표", "내 지표"):
                result = self._handle_list_custom_indicators()
                self.add_ai_message(result)
                return

            protected_action_support = self._build_protected_action_support(message)
            if protected_action_support:
                self.add_ai_message(protected_action_support)
                return

            membership_support = self._build_membership_support(message)
            if membership_support:
                self.add_ai_message(membership_support)
                return

            financial_intelligence_support = self._build_financial_intelligence_support(message)
            if financial_intelligence_support:
                self.add_ai_message(financial_intelligence_support)
                return

            high_vol_support = self._build_high_vol_support(message)
            if high_vol_support:
                self.add_ai_message(str(high_vol_support.get("message") or ""))
                proposal = high_vol_support.get("proposal")
                if isinstance(proposal, dict) and proposal:
                    safe_proposal, notes = self._sanitize_settings_proposal(proposal)
                    if notes:
                        self.add_ai_message("안전 검증 결과:\n" + "\n".join(f"- {note}" for note in notes))
                    if safe_proposal:
                        self._insert_confirm_buttons(safe_proposal, message)
                return

            ai_custom_support = self._build_ai_custom_support(message)
            if ai_custom_support:
                self.add_ai_message(ai_custom_support)
                return

            identity_support = self._build_identity_support(message)
            if identity_support:
                self.add_ai_message(identity_support)
                return

            clarification = self._build_settings_clarification(message)
            if clarification:
                self.add_ai_message(clarification)
                return
            # ────────────────────────────────────────────────────

            if not self.ai_manager or not self.ai_manager.enabled():
                fallback = self._generate_local_fallback_response(message, "AI 매니저 비활성 또는 API 키 미설정")
                self.add_ai_message(fallback)
                return

            # 현재 거래 상황 데이터 수집
            context = self._get_current_trading_context()

            # 사용자 요청 의도 분석 (설정 변경 요청인지 확인)
            is_settings_change_request = self._is_settings_change_request(message)
            service_profile = self._get_service_profile(getattr(self, 'assistant_service_context', 'blockchain'))
            service_label = service_profile.get('label', '암호화폐')

            # AI 매니저를 통한 실제 응답 생성
            if is_settings_change_request:
                # 설정 변경 요청: AI가 먼저 현황 분석 + 추천값 + 이유를 설명하고
                # 실제 적용은 사용자가 확인 버튼을 누를 때만 수행
                system_prompt = """당신은 NoahAI(노아AI) 공식 제품·거래 분석 어시스턴트입니다.
사용자가 정체성을 물으면 첫 문장을 "저는 NoahAI입니다."로 답하고, 일반 답변에서도 다른 서비스의
범용 챗봇처럼 행동하지 말고 NoahAI의 실제 설정·로그·가드레일 범위 안에서만 설명하세요.

【핵심 원칙】
- 사용자의 자산을 보호하는 것이 최우선입니다.
- 현재 실제 거래 데이터(잔고, 승률, 포지션, 시장 상황)를 반드시 분석한 후에만 변경을 추천하세요.
- 요청이 위험하거나 현재 상황에 맞지 않으면 "분석 결과 현재 시점에서 이 변경은 권장하지 않습니다"라고
  명확히 밝히고, 이유와 더 안전한 대안을 제시하세요.
- 무조건적으로 사용자 요청을 수용하지 마세요.

역할: 사용자의 설정 변경 요청에 대해 **현재 상황을 분석한 뒤, 구체적인 추천값과 근거를 설명**하고,
반드시 아래 JSON 형식으로만 응답하세요. 설정은 직접 변경하지 않으며 사용자가 확인 후 적용합니다.

응답 형식 (반드시 준수):
```json
{
  "action": "settings_change",
  "analysis": "현재 상황 분석 (승률, 포지션, 잔고, 시장 국면 등 근거 2~4줄)",
  "recommendation": "추천 이유와 주의사항 — 위험한 경우 경고 포함 (1~3줄)",
  "message": "사용자에게 보여줄 요약 한 줄 (위험 시 경고 문구 포함)",
  "settings": {
    "변경할_키": 값
  },
  "reason": "핵심 변경 이유 한 줄 (또는 '현재 상황에서 변경 비권장: 이유')"
}
```

규칙:
- 현재 설정과 통계를 근거로 변경이 타당한지 먼저 판단하세요
- 위험한 설정(레버리지 15 이상, 잔고 활용 40% 초과, 손실 중 공격적 전환 등)은 analysis에 위험 경고 포함
- 수익이 나쁠 때 레버리지 증가 요청은 반드시 위험 경고와 함께 보수적 대안 제시
- 모델·표시 설정은 거래소 연결과 무관하게 저장할 수 있지만, 위험을 높이는 거래 설정은 현재 시장·성과·포지션
  데이터가 충분할 때만 제안하세요.
- 변경 가능 키: default_leverage(1-20), default_tp(0.001-0.1), default_sl(0.001-0.1),
    risk_tolerance("CONSERVATIVE"/"MODERATE"/"AGGRESSIVE"), balance_utilization_limit(0.05-0.5),
    openai_model, assistant_ai_model,
    ai_model_roles({"frequent_cheap":"...","standard":"...","premium":"..."}),
    strategy_engine_high_vol_action("evaluate"/"block"),
    strategy_engine_consensus_threshold(0.10-0.95),
    strategy_engine_cooldown_sec(0-3600)
- high vol의 evaluate는 무조건 진입 허용이 아니라 합의 점수와 모든 가드레일을 유지한 평가 계속입니다.
- OpenAI 모델 변경은 분석 품질/비용 선택이며 수익 검증 통과나 거래 기회를 보장하지 않습니다."""

                user_prompt = f"""사용자 요청: {message}
현재 서비스 컨텍스트: {service_label}

최근 대화:
{self._recent_conversation_for_prompt()}

현재 거래 상황:
{context}

위 데이터를 냉정하게 분석하여 요청이 현재 상황에 적절한지 먼저 판단하고,
추천값과 근거 또는 위험 경고를 JSON 형식으로 응답하세요.
사용자가 내용을 확인 후 직접 적용 여부를 결정합니다."""
            else:
                # 일반 분석/조언 질문
                system_prompt = f"""당신은 NoahAI(노아AI) 공식 제품 어시스턴트이며, {service_profile.get('expert_role', '금융 투자 분석 전문가입니다.')}
사용자가 정체성을 물으면 "저는 NoahAI입니다."라고 명확히 답하세요.
제품 기능·설정 경로를 모르면 추정하지 말고 필요한 화면·현재값을 재질문하세요.

【NoahAI 어시스턴트 핵심 철학】
당신은 사용자의 자산을 보호하는 것이 최우선입니다.
다음 원칙을 반드시 지키세요:

1. **현실 기반 분석**: 제공된 실제 잔고·포지션·거래 통계·시장 데이터를 근거로 답변하세요.
   데이터가 없으면 "현재 데이터를 확인할 수 없어 정확한 분석이 어렵습니다"라고 명시하세요.

2. **냉정한 리스크 진단**: 수익 가능성보다 손실 가능성을 먼저 언급하세요.
   현재 시장이 불리하거나 사용자의 포지션이 위험하다면 명확히 경고하세요.

3. **잘못된 요청 교정**: 사용자가 현재 상황에 맞지 않는 요청(예: 수익이 나빠 손실 중인데 레버리지 증가,
   하락장에서 공격적 매수 등)을 하면 동의하지 말고, 현재 데이터를 근거로 왜 위험한지 설명하고
   더 나은 대안을 제시하세요.

4. **시장 국면 필수 반영**: 현재 제공된 주요 코인 시장 데이터(BTC/ETH 등)를 보고
   상승장/하락장/횡보장을 판단하여 조언에 반영하세요.

5. **구체적·실행 가능한 조언**: 추상적 말 대신 "현재 승률 X%, 잔고 Y USDT 상황에서
   Z% 이상 활용은 위험합니다" 형태로 숫자를 활용하세요.

6. **설정 변경 신중론**: 단순 질문에서 설정 변경을 먼저 제안하지 마세요.
   현재 설정이 합리적이라면 "현재 설정이 적절합니다"라고 말하세요.

7. **의도 확인**: 목표·설정 항목·변경 방향 중 하나라도 불명확하면 임의 값을 만들지 말고
   한 번에 답하기 쉬운 짧은 재질문을 하세요.

	8. **제품 지식**:
	   - AI 커스텀은 소스 입력 → XAI 구조화 → 사용자 승인 → 자동검증 → 최종 적용 → 거래 시작 순서입니다.
	   - YouTube·TradingView 분석값은 초안이며 출처 근거와 누락 조건을 확인해야 합니다.
	   - 코인 정보는 내 계좌·선택 코인의 운용 상태이고, 코인 탐색은 여러 코인을 조건으로 비교하는 시장 검색입니다.
	   - 금융 인텔리전스의 시장·탐색·지표·검증 결과만으로 주문하거나 설정을 바꾸지 않습니다.
	   - 뉴스·공시·기관 데이터의 '운영 데이터 연결 필요'는 사용자 입력 오류가 아니며 임의 값을 만들지 않는 상태입니다.
	   - 고변동장 설정은 설정 → 고급 자동매매 → 전략 엔진 세부 설정 → 고변동장 처리입니다.
   - "평가 계속"도 수익성·합의·리스크·주문 가드레일을 우회하지 않습니다.
   - OpenAI 최신 모델이 자동으로 전략 수익성이나 high vol 진입을 보장한다고 설명하지 마세요.

【증권사 연결 FAQ — 기술 지원 지식】
사용자가 증권사 연결 오류나 설치 방법을 물어보면 아래 지식을 바탕으로 안내하세요.

■ 키움증권 OpenAPI+ 연결 오류 원인 순서
  ① OpenAPI+ 미설치 → 키움증권 홈페이지(www1.kiwoom.com) > 다운로드 > Open API 설치
  ② OCX 미등록 → 키움증권 OpenAPI+를 "관리자 권한으로 실행"하여 재설치
  ③ Windows 전용 제약 → macOS/Linux에서는 키움 연결 자체가 불가 (앱 제약이 아닌 키움 COM/ActiveX 자체 제약)
  ④ 32/64-bit 불일치 → KOA Studio를 먼저 실행하여 정상 연결되는지 확인; 안 되면 Python과 동일한 비트의 OpenAPI+ 재설치
  ⑤ 계정/인증서 문제 → 계정 ID, 비밀번호, 공인인증서 비밀번호, 계좌번호 재확인

■ 증권사별 지원 OS
  - 키움증권: Windows 전용 (OpenAPI+ COM 기반)
  - 신한증권(SOL), 미래에셋증권: Windows / macOS / Linux 모두 가능 (REST API)

■ 키움 mock 모드 전환 방법
    설정 → 거래소 API 탭 → 키움증권 → API 연결 방식: "mock" 으로 변경 → 저장
  mock 모드에서는 실제 주문 없이 연결 테스트 가능

■ 실주문 허용 설정 위치
    설정 → 거래소 선택 탭 → "증권 자동매매 제어" 섹션 → "실주문 허용 (enable_stock_live_order)" 체크박스
  OFF(기본값): 실제 주문 없음 / ON: 실제 매매 실행

■ pykiwoom / PyQt5 라이브러리 누락 시
  pip install pykiwoom PyQt5 (Windows 환경에서만 의미 있음)
  또는 pip install -r requirements_windows.txt 전체 재설치

응답 형식:
- 현재 상황 요약 (데이터 기반, 1~2줄)
- 분석/평가 (장단점, 리스크)
- 구체적 조언 또는 경고
- 필요 시에만 설정 변경 제안"""

                user_prompt = f"""사용자 요청: {message}
현재 서비스 컨텍스트: {service_label}

최근 대화:
{self._recent_conversation_for_prompt()}

현재 거래 상황:
{context}

위 실제 데이터를 근거로 냉정하고 현실적인 분석과 조언을 제공해주세요.
사용자 요청이 현재 상황에 맞지 않는다면 명확하게 교정해주세요."""

            # AI 어시스턴트용 모델 사용 (설정에서 전달된 모델 우선)
            assistant_model = getattr(self, 'assistant_model_name', None) or 'gpt-4o-mini'
            # 모델명 정규화 적용
            assistant_model = self._normalize_model_name(assistant_model)

            # 디버그 로그 추가 (빌드 환경 문제 진단용)
            self.logger.debug(f"AI 응답 생성 시도: 모델={assistant_model}, AI Manager 활성={self.ai_manager.enabled() if self.ai_manager else False}")

            # AI 매니저를 통한 응답 생성
            ai_response = self.ai_manager.chat_completion([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], model=assistant_model)

            if ai_response:
                if isinstance(ai_response, str) and (
                    "AI 기능이 비활성화" in ai_response or
                    "AI 응답을 생성할 수 없습니다" in ai_response or
                    "오류가 발생했습니다" in ai_response
                ):
                    fallback = self._generate_local_fallback_response(message, ai_response)
                    self.add_ai_message(fallback)
                    return

                # 설정 변경 요청인 경우 JSON 파싱 시도
                if is_settings_change_request:
                    parsed_settings = self._parse_settings_json_response(ai_response, message)
                    if parsed_settings:
                        # AI 분석 내용 먼저 표시 (즉시 적용 금지)
                        self._show_settings_proposal(ai_response, parsed_settings, message)
                    else:
                        # JSON 파싱 실패 → 텍스트 조언만 표시
                        self.add_ai_message(f"AI 분석 결과:\n{ai_response}")
                        recommended_settings = self._extract_recommended_settings(ai_response, message)
                        if recommended_settings:
                            self.current_recommended_settings = recommended_settings
                            self.add_ai_message("위 분석을 참고하여 설정관리 버튼에서 직접 변경하실 수 있습니다.")
                else:
                    # 일반 질문인 경우 기존 방식
                    self.add_ai_message(f"AI 분석 결과:\n{ai_response}")

                    # 설정 제안이 포함된 경우 권장 설정 생성
                    if "권장 설정" in ai_response or "설정" in ai_response:
                        recommended_settings = self._extract_recommended_settings(ai_response, message)
                        if recommended_settings:
                            self.current_recommended_settings = recommended_settings
            else:
                fallback = self._generate_local_fallback_response(message, "AI 응답 없음")
                self.add_ai_message(fallback)

        except Exception as e:
            self.logger.error(f"AI 응답 생성 오류: {e}")
            fallback = self._generate_local_fallback_response(message, f"AI 응답 생성 오류: {str(e)}")
            self.add_ai_message(fallback)

    # ── 커스텀 지표 관리 ──────────────────────────────────────────
    def _handle_add_custom_indicator(self, name: str) -> str:
        """커스텀 지표 등록 및 MarketTrendWidget에 반영"""
        try:
            if not hasattr(self, '_custom_indicators'):
                self._custom_indicators = []
            name = name.strip()
            if name in self._custom_indicators:
                return f"ℹ'{name}' 지표는 이미 등록되어 있습니다.\n현재 등록 지표: {', '.join(self._custom_indicators)}"
            self._custom_indicators.append(name)
            # MarketTrendWidget에 동기화
            self._sync_custom_indicators_to_trend_widget()
            return (
                f"커스텀 지표 '{name}'이(가) 등록되었습니다.\n"
                f"시장 트렌드 → AI 전략 상태 섹션에서 확인할 수 있습니다.\n"
                f"현재 등록 지표 ({len(self._custom_indicators)}개): {', '.join(self._custom_indicators)}"
            )
        except Exception as e:
            return f"지표 등록 중 오류 발생: {e}"

    def _handle_remove_custom_indicator(self, name: str) -> str:
        """커스텀 지표 삭제"""
        try:
            if not hasattr(self, '_custom_indicators'):
                self._custom_indicators = []
            name = name.strip()
            if name in self._custom_indicators:
                self._custom_indicators.remove(name)
                self._sync_custom_indicators_to_trend_widget()
                return f"'{name}' 지표가 삭제되었습니다.\n남은 지표 ({len(self._custom_indicators)}개): {', '.join(self._custom_indicators) or '없음'}"
            return f"ℹ'{name}' 지표를 찾을 수 없습니다.\n현재 등록 지표: {', '.join(self._custom_indicators) or '없음'}"
        except Exception as e:
            return f"지표 삭제 중 오류 발생: {e}"

    def _handle_list_custom_indicators(self) -> str:
        """등록된 커스텀 지표 목록 반환"""
        indicators = getattr(self, '_custom_indicators', [])
        if indicators:
            lines = "\n".join(f"  [{i+1}] {ind}" for i, ind in enumerate(indicators))
            return f"등록된 커스텀 지표 ({len(indicators)}개):\n{lines}\n\n삭제: '지표 삭제 [지표명]'"
        return "등록된 커스텀 지표가 없습니다.\n추가: '지표 추가 RSI_14' 형태로 입력하세요."

    def _sync_custom_indicators_to_trend_widget(self):
        """MarketTrendWidget._custom_indicators에 현재 목록 동기화"""
        try:
            dashboard = getattr(self, 'dashboard_ref', None)
            if dashboard is None:
                # dashboard_ref가 없으면 부모 체인 탐색
                try:
                    w = self.winfo_toplevel()
                    dashboard = getattr(w, 'dashboard', None) or w
                except Exception:
                    return
            trend_widget = getattr(dashboard, 'market_trend_widget', None)
            if trend_widget is not None:
                trend_widget._custom_indicators = list(getattr(self, '_custom_indicators', []))
        except Exception:
            pass
    # ─────────────────────────────────────────────────────────────

    def _generate_local_fallback_response(self, message: str, reason: str = "AI 응답 불안정") -> str:
        """AI 응답 실패 시 현재 앱에서 확인 가능한 정보로 안전하게 안내"""
        try:
            context = self._get_current_trading_context()
            message_lower = (message or "").lower()

            tips: List[str] = []
            if "거래" in message_lower and ("없" in message_lower or "부재" in message_lower):
                tips.append("- 거래 부재 문의입니다. 거래소 연결 상태, 잔고, 선택 코인, 활성 포지션부터 점검하세요.")
            if any(keyword in message_lower for keyword in ["포지션", "비중", "레버리지", "전략"]):
                tips.append("- 설정 조정형 요청은 거래소 연결과 무관하게 settings 저장으로 처리할 수 있습니다.")
            if "리스크" in message_lower or "위험" in message_lower:
                tips.append("- 현재 레버리지, TP/SL, 잔고 활용 한도를 우선 확인하는 것이 좋습니다.")

            if not tips:
                tips.append("- 현재 확인 가능한 거래 현황을 먼저 안내합니다.")

            short_context = "\n".join(context.splitlines()[:12]) if context else "거래 상황 요약을 불러오지 못했습니다."
            return (
                f"AI 실시간 응답이 일시적으로 불안정하여 로컬 진단으로 안내합니다.\n"
                f"사유: {reason}\n\n"
                + "\n".join(tips)
                + f"\n\n현재 확인된 정보:\n{short_context}"
            )
        except Exception:
            return f"AI 응답이 일시적으로 불안정합니다. 사유: {reason}"

    def _normalize_coins_for_analysis(self, coins: Any) -> List[Dict[str, str]]:
        """분석기에 전달할 코인 리스트를 표준 형태로 정규화합니다.
        - 허용 입력: ["BTCUSDT", ...] 또는 [{"symbol": "BTCUSDT"}, ...]
        - 반환 형식: [{"symbol": "..."}, ...]
        """
        normalized: List[Dict[str, str]] = []
        try:
            for c in (coins or []):
                if isinstance(c, dict):
                    sym = c.get('symbol') or c.get('Symbol') or c.get('coin') or c.get('ticker')
                    if sym:
                        normalized.append({'symbol': str(sym)})
                else:
                    s = str(c).strip()
                    if s:
                        normalized.append({'symbol': s})
        except Exception as e:
            try:
                self.logger.debug(f"코인 정규화 실패: {e}")
            except Exception:
                pass
        return normalized
    @classmethod
    def _logical_setting_values(cls, settings: dict, keys: Any) -> dict:
        """중첩 저장 구조를 어시스턴트의 타입형 작업 키로 읽는다."""
        source = dict(settings or {})
        prefs = dict(source.get("ai_trading_preferences", {}) or {})
        strategy = dict(
            (source.get("advanced_trading_layers", {}) or {}).get("strategy_engine", {}) or {}
        )
        values = {}
        for key in keys:
            if key in {"risk_tolerance", "balance_utilization_limit"}:
                values[key] = prefs.get(key)
            elif key in {
                "strategy_engine_high_vol_action",
                "strategy_engine_consensus_threshold",
                "strategy_engine_cooldown_sec",
            }:
                nested_key = {
                    "strategy_engine_high_vol_action": "high_vol_action",
                    "strategy_engine_consensus_threshold": "consensus_threshold",
                    "strategy_engine_cooldown_sec": "cooldown_sec",
                }[key]
                values[key] = strategy.get(nested_key)
            else:
                values[key] = copy.deepcopy(source.get(key))
        return values

    @classmethod
    def _merge_logical_setting_values(cls, settings: dict, values: dict) -> dict:
        """타입형 작업 키의 이전 값을 현재 전체 설정에 안전하게 병합한다."""
        merged = copy.deepcopy(settings or {})
        for key, value in dict(values or {}).items():
            if key not in cls.SETTINGS_ACTION_REGISTRY:
                continue
            if key in {"risk_tolerance", "balance_utilization_limit"}:
                merged.setdefault("ai_trading_preferences", {})[key] = value
            elif key in {
                "strategy_engine_high_vol_action",
                "strategy_engine_consensus_threshold",
                "strategy_engine_cooldown_sec",
            }:
                nested_key = {
                    "strategy_engine_high_vol_action": "high_vol_action",
                    "strategy_engine_consensus_threshold": "consensus_threshold",
                    "strategy_engine_cooldown_sec": "cooldown_sec",
                }[key]
                merged.setdefault("advanced_trading_layers", {}).setdefault(
                    "strategy_engine", {}
                )[nested_key] = value
            else:
                merged[key] = copy.deepcopy(value)
        return merged

    def _load_persistent_settings_history(self) -> None:
        try:
            if not self.settings_audit_path.exists():
                return
            payload = json.loads(self.settings_audit_path.read_text(encoding="utf-8"))
            entries = payload.get("entries", []) if isinstance(payload, dict) else []
            allowed = set(self.SETTINGS_ACTION_REGISTRY)
            loaded = []
            for entry in entries[-self.max_history_size:]:
                if not isinstance(entry, dict):
                    continue
                changed = {
                    key: value for key, value in dict(entry.get("settings", {}) or {}).items()
                    if key in allowed
                }
                before = {
                    key: value for key, value in dict(entry.get("before", {}) or {}).items()
                    if key in allowed
                }
                if changed and before:
                    loaded.append({
                        "action_id": str(entry.get("action_id") or uuid4().hex),
                        "timestamp": str(entry.get("timestamp") or ""),
                        "settings": changed,
                        "before": before,
                        "after": {
                            key: value for key, value in dict(entry.get("after", {}) or {}).items()
                            if key in allowed
                        },
                        "source": str(entry.get("source") or "assistant_confirmed_apply"),
                    })
            self.settings_change_history = loaded
        except Exception as exc:
            self.logger.warning(f"어시스턴트 설정 감사로그 로드 실패: {exc}")

    def _persist_settings_history(self) -> None:
        try:
            self.settings_audit_path.parent.mkdir(parents=True, exist_ok=True)
            entries = []
            for entry in self.settings_change_history[-self.max_history_size:]:
                entries.append({
                    "action_id": str(entry.get("action_id") or uuid4().hex),
                    "timestamp": str(entry.get("timestamp") or datetime.now().isoformat()),
                    "settings": copy.deepcopy(entry.get("settings", {}) or {}),
                    "before": copy.deepcopy(entry.get("before", {}) or {}),
                    "after": copy.deepcopy(entry.get("after", {}) or {}),
                    "source": str(entry.get("source") or "assistant_confirmed_apply"),
                })
            temp_path = self.settings_audit_path.with_suffix(".json.tmp")
            temp_path.write_text(
                json.dumps({"schema_version": 1, "entries": entries}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp_path.replace(self.settings_audit_path)
        except Exception as exc:
            self.logger.warning(f"어시스턴트 설정 감사로그 저장 실패: {exc}")

    def _append_settings_history(
        self,
        *,
        changes: dict,
        before_full: dict,
        after_full: dict,
        source: str,
    ) -> None:
        keys = [key for key in changes if key in self.SETTINGS_ACTION_REGISTRY]
        self.settings_change_history.append({
            "action_id": f"settings_{uuid4().hex}",
            "timestamp": datetime.now().isoformat(),
            "settings": {key: copy.deepcopy(changes[key]) for key in keys},
            "before": self._logical_setting_values(before_full, keys),
            "after": self._logical_setting_values(after_full, keys),
            "before_full": copy.deepcopy(before_full),
            "source": str(source),
        })
        if len(self.settings_change_history) > self.max_history_size:
            self.settings_change_history.pop(0)
        self._persist_settings_history()


    def undo_last_settings_change(self):
        """마지막 설정 변경 되돌리기"""
        if not self.settings_change_history:
            self.add_ai_message("되돌릴 설정 변경이 없습니다.")
            return

        last_change = self.settings_change_history[-1]
        before_settings = last_change.get('before')
        if not before_settings:
            self.add_ai_message("이전 설정 스냅샷이 없어 되돌릴 수 없습니다.\n(이 항목은 이전 버전에서 기록된 이력입니다)")
            return

        try:
            dashboard = getattr(self, 'parent_dashboard', None)
            if not dashboard:
                self.add_ai_message("대시보드에 연결되지 않아 설정을 적용할 수 없습니다.")
                return

            from config.settings import load_settings, save_settings
            current_full = load_settings() or copy.deepcopy(getattr(dashboard, "settings", {}) or {})
            restored_full = self._merge_logical_setting_values(current_full, before_settings)
            if save_settings(restored_full):
                persisted_settings = load_settings() or {}
                expected_values = self._logical_setting_values(restored_full, before_settings.keys())
                persisted_values = self._logical_setting_values(persisted_settings, before_settings.keys())
                if persisted_values != expected_values:
                    save_settings(current_full)
                    self.add_ai_message(
                        "되돌리기 저장 후 재조회 값이 이전 설정과 달라 현재 설정을 유지했습니다."
                    )
                    return
                if hasattr(dashboard, 'settings'):
                    dashboard.settings.clear()
                    dashboard.settings.update(copy.deepcopy(persisted_settings))
                if hasattr(dashboard, 'on_settings_changed'):
                    dashboard.on_settings_changed('settings_updated', persisted_settings)
                self.settings_change_history.pop()  # 되돌린 항목 제거
                self._persist_settings_history()
                self.update_strategy_status(getattr(dashboard, 'settings', {}))
                self._update_settings_modal_ui_state()
                self.add_ai_message("마지막 설정 변경을 성공적으로 되돌렸습니다.")
            else:
                self.add_ai_message("설정 저장에 실패했습니다.")
        except Exception as e:
            self.logger.error(f"undo_last_settings_change 오류: {e}")
            self.add_ai_message(f"되돌리기 중 오류가 발생했습니다: {e}")

    def show_settings_history(self):
        """설정 변경 이력 표시"""
        if not self.settings_change_history:
            self.add_ai_message("설정 변경 이력이 없습니다.")
            return

        history_text = "설정 변경 이력 (최근 5개):\n"
        for i, change in enumerate(self.settings_change_history[-5:], 1):
            ts = change.get('timestamp', '?')
            changed = change.get('settings') or change.get('changes') or {}
            count = len(changed)
            keys = ', '.join(str(k) for k in list(changed.keys())[:3])
            if len(changed) > 3:
                keys += ' ...'
            history_text += f"{i}. {ts[:19]}: {count}개 변경 ({keys})\n"

        self.add_ai_message(history_text)

    def restore_default_strategy(self):
        """기본 전략 복구"""
        try:
            import sys
            settings_module = sys.modules.get("config.settings")
            if settings_module is None:
                from config import settings as settings_module
            from tkinter import messagebox
            confirm = messagebox.askyesno(
                "기본 전략 복구",
                "모든 설정을 초기 기본값으로 되돌리겠습니까?\n거래 설정(레버리지, TP/SL 등)이 모두 초기화됩니다."
            )
            if not confirm:
                self.add_ai_message("ℹ기본 전략 복구가 취소되었습니다.")
                return

            self.add_ai_message("기본 전략으로 복구 중...")
            try:
                reset_with_options = getattr(settings_module, 'reset_settings_with_options', None)
                if callable(reset_with_options):
                    restored_ok = bool(reset_with_options(preserve_sensitive=True))
                else:
                    restored_ok = bool(settings_module.reset_settings())
            except TypeError:
                restored_ok = bool(settings_module.reset_settings())

            if restored_ok:
                restored = settings_module.load_settings()
                dashboard = getattr(self, 'parent_dashboard', None)
                if dashboard and hasattr(dashboard, 'settings'):
                    dashboard.settings.update(restored)
                    if hasattr(dashboard, 'on_settings_changed'):
                        dashboard.on_settings_changed('settings_updated', restored)
                self.update_strategy_status(restored)
                self._update_settings_modal_ui_state()
                self.add_ai_message(
                    f"기본 전략으로 복구 완료!\n"
                    f"  레버리지: {restored.get('default_leverage', '?')}x\n"
                    f"  익절: {restored.get('default_tp', 0)*100:.2f}%\n"
                    f"  손절: {restored.get('default_sl', 0)*100:.2f}%"
                )
            else:
                self.add_ai_message("기본 설정 저장에 실패했습니다.")
        except Exception as e:
            self.logger.error(f"restore_default_strategy 오류: {e}")
            self.add_ai_message(f"기본 전략 복구 중 오류가 발생했습니다: {e}")

    def update_strategy_status(self, settings: dict):
        """전략 상태 업데이트"""
        try:
            if not settings or not hasattr(self, 'strategy_status_label') or not self.strategy_status_label:
                return

            # AI 매니저 상태 확인
            ai_status = "활성" if self.ai_manager and self.ai_manager.enabled() else "비활성"
            ai_status_color = self._color("success") if ai_status == "활성" else self._color("danger")

            # 현재 설정에서 정보 추출
            leverage = settings.get('default_leverage', 1)
            tp = settings.get('default_tp', 0.18)
            sl = settings.get('default_sl', 0.20)
            preferences = settings.get('ai_trading_preferences', {}) if isinstance(settings.get('ai_trading_preferences', {}), dict) else {}
            risk_tolerance = str(preferences.get('risk_tolerance', 'MODERATE')).upper()
            risk_map = {'CONSERVATIVE': '보수', 'MODERATE': '균형', 'AGGRESSIVE': '적극'}
            strategy_mode = risk_map.get(risk_tolerance, risk_tolerance)
            balance_limit = preferences.get('balance_utilization_limit', 0.25)
            try:
                balance_limit_pct = float(balance_limit) * 100.0
            except Exception:
                balance_limit_pct = 25.0

            status_text = f"""전략: {strategy_mode} 모드
레버리지: {leverage}x
잔고 활용 한도: {balance_limit_pct:.0f}%
익절 목표: {tp*100:.1f}%
손절 라인: {sl*100:.1f}%
신호 임계값: 70점

AI 상태: {ai_status}"""

            self.strategy_status_label.configure(text=status_text, text_color=ai_status_color)

        except Exception as e:
            self.logger.error(f"전략 상태 업데이트 오류: {e}")

    def record_settings_change(self, new_settings: dict):
        """설정 변경 이력 기록"""
        try:
            # 변경 이력에 추가
            self.settings_change_history.append({
                'timestamp': datetime.now().isoformat(),
                'changes': new_settings,
                'total_changes': len(new_settings)
            })

            # 최대 이력 크기 유지
            if len(self.settings_change_history) > self.max_history_size:
                self.settings_change_history.pop(0)

        except Exception as e:
            self.logger.error(f"설정 변경 이력 기록 실패: {e}")

    def get_settings_change_history(self) -> list:
        """설정 변경 이력 조회"""
        return self.settings_change_history.copy()

    def _update_settings_modal_ui_state(self):
        """설정 관리 모달의 상태(되돌리기 가능 여부/설명 텍스트)를 최신화"""
        try:
            has_history = bool(self.settings_change_history)
            has_undoable = has_history and bool(
                self.settings_change_history[-1].get('before') or self.settings_change_history[-1].get('before_full')
            )
            history_status = (
                f"활성화 (이력 {len(self.settings_change_history)}개)" if has_undoable
                else "비활성화 (되돌릴 항목 없음)"
            )

            if hasattr(self, '_settings_modal_undo_btn') and self._settings_modal_undo_btn:
                self._settings_modal_undo_btn.configure(state="normal" if has_undoable else "disabled")

            if hasattr(self, '_settings_modal_info_text') and self._settings_modal_info_text:
                info_content = f"""설정 관리 기능 설명

1. 마지막 설정 되돌리기
   • AI가 제안한 마지막 설정 변경을 되돌립니다
   • 현재 상태: {history_status}

2. 설정 변경 이력
   • AI가 제안한 모든 설정 변경 내역을 확인할 수 있습니다
   • 최근 50개 변경 이력까지 저장됩니다

3. 기본 전략 복구
   • 모든 설정을 초기 기본값으로 되돌립니다
   • 확인 대화상자 표시 후 적용

4. AI 모델 프리셋 (초보자 추천)
    • 절약형: 비용 우선 (호출량이 많아도 비용 부담 최소화)
    • 균형형: 기본 권장 (대부분 사용자에게 무난)
    • 정밀형: 분석 품질 우선 (비용 증가 가능)
    • 프리셋 적용 후에도 최종 확인 단계에서 취소할 수 있습니다

내게 맞는 선택 방법:
• 사용 빈도가 높고 예산이 작다 → 절약형
• 아직 잘 모르겠다 → 균형형
• 진단 정확도를 가장 중시한다 → 정밀형

주의사항:
• 설정 변경은 거래에 직접적인 영향을 미칩니다
• 문제 발생 시 언제든지 기본 설정으로 복원 가능합니다"""
                self._settings_modal_info_text.configure(state="normal")
                self._settings_modal_info_text.delete("1.0", "end")
                self._settings_modal_info_text.insert("1.0", info_content)
                self._settings_modal_info_text.configure(state="disabled")
        except Exception as e:
            self.logger.debug(f"설정 모달 상태 갱신 실패: {e}")

    def show_settings_management_modal(self):
        """설정 관리 모달창 표시"""
        try:
            # 모달창 생성
            modal = ctk.CTkToplevel(self)
            modal.title("설정 관리")
            modal.geometry("600x500")
            # 모달을 최상위 윈도우에 종속시킵니다 (타입 안전)
            try:
                modal.transient(self.winfo_toplevel())
            except Exception:
                modal.transient(modal)
            modal.grab_set()

            # 창 중앙 배치
            modal.update_idletasks()
            x = (modal.winfo_screenwidth() // 2) - (600 // 2)
            y = (modal.winfo_screenheight() // 2) - (500 // 2)
            modal.geometry(f"600x500+{x}+{y}")

            # 메인 프레임
            main_frame = CTkFrame(modal)
            main_frame.pack(fill="both", expand=True, padx=20, pady=20)

            # 제목
            title_label = CTkLabel(
                main_frame,
                text="AI 설정 관리",
                font=ctk.CTkFont(size=18, weight="bold")
            )
            title_label.pack(pady=20)

            # 현재 전략 상태 표시
            status_frame = CTkFrame(
                main_frame,
                fg_color=self._color("surface"),
                border_color=self._color("border"),
                border_width=1,
                corner_radius=12
            )
            status_frame.pack(fill="x", padx=10, pady=10)

            status_title = CTkLabel(
                status_frame,
                text="현재 전략 상태",
                font=ctk.CTkFont(size=14, weight="bold")
            )
            status_title.pack(pady=5)

            self.strategy_status_label = CTkLabel(
                status_frame,
                text="",
                font=ctk.CTkFont(size=11, family="monospace"),
                justify="left"
            )
            self.strategy_status_label.pack(pady=5, padx=10)

            # 현재 설정으로 전략 상태 실시간 반영
            _dash = getattr(self, 'parent_dashboard', None)
            _s = (getattr(_dash, 'settings', None) or {}) if _dash else {}
            self.update_strategy_status(_s)

            # 기능 설명
            info_text = CTkTextbox(
                main_frame,
                font=ctk.CTkFont(size=11),
                height=150,
                fg_color=self._color("surface"),
                text_color=self._color("text_primary"),
                border_color=self._color("border"),
                border_width=1,
                corner_radius=12
            )
            info_text.pack(fill="x", padx=10, pady=5)

            self._settings_modal_info_text = info_text

            # 모델 프리셋 버튼 (대시보드 노출 없이 어시스턴트 내부에서만 사용)
            preset_frame = CTkFrame(
                main_frame,
                fg_color=self._color("surface"),
                border_color=self._color("border"),
                border_width=1,
                corner_radius=12
            )
            preset_frame.pack(fill="x", padx=10, pady=(6, 4))

            preset_title = CTkLabel(
                preset_frame,
                text="AI 모델 프리셋",
                font=ctk.CTkFont(size=13, weight="bold")
            )
            preset_title.pack(anchor="w", padx=10, pady=(8, 4))

            preset_desc = CTkLabel(
                preset_frame,
                text="절약형(비용), 균형형(기본 권장), 정밀형(품질). 프리셋 적용 후 최종 확인에서 취소 가능합니다.",
                font=ctk.CTkFont(size=11),
                text_color=self._color("text_secondary"),
                justify="left",
                wraplength=520
            )
            preset_desc.pack(anchor="w", padx=10, pady=(0, 6))

            self._assistant_preset_cost_badge_label = CTkLabel(
                preset_frame,
                text="예상 비용 레벨: -",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=self._color("text_secondary")
            )
            self._assistant_preset_cost_badge_label.pack(anchor="w", padx=10, pady=(0, 6))

            quick_action_row = CTkFrame(preset_frame, fg_color="transparent")
            quick_action_row.pack(fill="x", padx=10, pady=(0, 8))

            preview_btn = CTkButton(
                quick_action_row,
                text="미리보기만",
                width=130,
                height=30,
                fg_color=self._color("secondary"),
                hover_color=self._hover_from(self._color("secondary")),
                command=self._preview_optimization_without_apply
            )
            preview_btn.pack(side="left", padx=(0, 6))

            quick_apply_btn = CTkButton(
                quick_action_row,
                text="균형형 바로 적용",
                width=160,
                height=30,
                fg_color=self._color("primary"),
                hover_color=self._hover_from(self._color("primary")),
                command=lambda: self._apply_model_preset_from_assistant("balanced")
            )
            quick_apply_btn.pack(side="left", padx=6)

            preset_buttons_row = CTkFrame(preset_frame, fg_color="transparent")
            preset_buttons_row.pack(fill="x", padx=10, pady=(0, 10))

            save_btn = CTkButton(
                preset_buttons_row,
                text="절약형",
                width=110,
                height=32,
                fg_color=self._color("secondary"),
                hover_color=self._hover_from(self._color("secondary")),
                command=lambda: self._apply_model_preset_from_assistant("cost_save")
            )
            save_btn.pack(side="left", padx=(0, 6))

            balanced_btn = CTkButton(
                preset_buttons_row,
                text="균형형",
                width=110,
                height=32,
                fg_color=self._color("secondary"),
                hover_color=self._hover_from(self._color("secondary")),
                command=lambda: self._apply_model_preset_from_assistant("balanced")
            )
            balanced_btn.pack(side="left", padx=6)

            quality_btn = CTkButton(
                preset_buttons_row,
                text="정밀형",
                width=110,
                height=32,
                fg_color=self._color("secondary"),
                hover_color=self._hover_from(self._color("secondary")),
                command=lambda: self._apply_model_preset_from_assistant("quality")
            )
            quality_btn.pack(side="left", padx=6)

            onboarding_btn = CTkButton(
                preset_buttons_row,
                text="초기 온보딩 시작",
                width=150,
                height=32,
                fg_color=self._color("primary"),
                hover_color=self._hover_from(self._color("primary")),
                command=lambda: self.start_initial_onboarding(source="assistant_modal")
            )
            onboarding_btn.pack(side="right", padx=6)

            # 버튼들
            button_frame = CTkFrame(
                main_frame,
                fg_color=self._color("content_bg", "#0b1120")
            )
            button_frame.pack(fill="x", padx=10, pady=10)

            # 되돌리기 버튼
            undo_btn = CTkButton(
                button_frame,
                text="마지막 설정 되돌리기",
                command=lambda: self.undo_last_settings_change(),
                width=200,
                height=40,
                fg_color=self._color("secondary"),
                hover_color=self._hover_from(self._color("secondary")),
                state="disabled"
            )
            undo_btn.pack(side="left", padx=5, pady=5)
            self._settings_modal_undo_btn = undo_btn

            # 모달 생성 시점에 상태 동기화
            self._update_settings_modal_ui_state()

            # 이력 보기 버튼
            history_btn = CTkButton(
                button_frame,
                text="설정 변경 이력",
                command=lambda: self.show_settings_history(),
                width=200,
                height=40,
                fg_color=self._color("secondary"),
                hover_color=self._hover_from(self._color("secondary"))
            )
            history_btn.pack(side="left", padx=5, pady=5)

            # 기본 전략 복구 버튼
            restore_btn = CTkButton(
                button_frame,
                text="기본 전략 복구",
                command=lambda: self.restore_default_strategy(),
                width=200,
                height=40,
                fg_color=self._color("secondary"),
                hover_color=self._hover_from(self._color("secondary"))
            )
            restore_btn.pack(side="left", padx=5, pady=5)

            # 닫기 버튼
            close_btn = CTkButton(
                main_frame,
                text="닫기",
                command=modal.destroy,
                width=100,
                height=35,
                fg_color=self._color("secondary"),
                hover_color=self._hover_from(self._color("secondary"))
            )
            close_btn.pack(pady=20)

            self.logger.info("설정 관리 모달창 표시")

        except Exception as e:
            self.logger.error(f"설정 관리 모달창 오류: {e}")

    def _apply_model_preset_from_assistant(self, preset_name: str):
        """어시스턴트 설정관리 모달에서 모델 프리셋을 즉시 적용한다."""
        presets: Dict[str, Dict[str, Any]] = {
            'cost_save': {
                'openai_model': 'gpt-4o-mini',
                'assistant_ai_model': 'gpt-4o-mini',
                'ai_model_roles': {
                    'frequent_cheap': 'gpt-4o-mini',
                    'standard': 'gpt-4o-mini',
                    'premium': 'gpt-4o',
                },
                'label': '절약형',
                'cost_level': '낮음',
            },
            'balanced': {
                'openai_model': 'gpt-4o-mini',
                'assistant_ai_model': 'gpt-4o',
                'ai_model_roles': {
                    'frequent_cheap': 'gpt-4o-mini',
                    'standard': 'gpt-4o',
                    'premium': 'gpt-4o',
                },
                'label': '균형형',
                'cost_level': '중간',
            },
            'quality': {
                'openai_model': 'gpt-4o',
                'assistant_ai_model': 'gpt-4o',
                'ai_model_roles': {
                    'frequent_cheap': 'gpt-4o-mini',
                    'standard': 'gpt-4o',
                    'premium': 'gpt-5',
                },
                'label': '정밀형',
                'cost_level': '높음',
            },
        }

        selected = presets.get(preset_name)
        if not selected:
            return

        settings_payload: Dict[str, Any] = {
            'openai_model': selected['openai_model'],
            'assistant_ai_model': selected['assistant_ai_model'],
            'ai_model_roles': selected['ai_model_roles'],
        }

        try:
            if hasattr(self, '_assistant_preset_cost_badge_label') and self._assistant_preset_cost_badge_label:
                cost_level = selected.get('cost_level', '-')
                color = {
                    '낮음': self._color('success'),
                    '중간': self._color('warning'),
                    '높음': self._color('danger'),
                }.get(cost_level, self._color('text_secondary'))
                self._assistant_preset_cost_badge_label.configure(
                    text=f"예상 비용 레벨: {cost_level}",
                    text_color=color,
                )
        except Exception:
            pass

        try:
            if not self._confirm_settings_apply(settings_payload):
                self.add_ai_message("↩모델 프리셋 적용이 최종 확인에서 취소되었습니다.")
                return
            self._apply_settings_automatically(settings_payload, f"모델 프리셋 적용: {selected['label']}")
            self.add_ai_message(f"ℹ선택 프리셋: {selected['label']} (예상 비용 레벨: {selected.get('cost_level', '-')})")
        except Exception as e:
            self.logger.error(f"어시스턴트 모델 프리셋 적용 실패: {e}")
            self.add_ai_message(f"모델 프리셋 적용 중 오류가 발생했습니다: {e}")

    def _preview_optimization_without_apply(self):
        """설정 변경 없이 현재 최적화 안내만 표시한다."""
        try:
            self.add_ai_message(
                "미리보기 모드입니다. 현재는 설정을 저장하지 않았습니다. "
                "프리셋 버튼(절약형/균형형/정밀형 또는 균형형 바로 적용)을 누르면 최종 확인 후 적용됩니다."
            )
        except Exception:
            pass

    def _get_current_trading_context(self) -> str:
        """현재 거래 상황 데이터 수집 (CustomTkinter 버전)"""
        try:
            context_parts = []
            selected_exchange = 'binance'

            # 대시보드 참조를 통해 거래 상황 수집
            dashboard = getattr(self, 'parent_dashboard', None)
            if not dashboard:
                return "거래 상황 정보를 가져올 수 없습니다. 대시보드가 연결되지 않았습니다."

            current_service = getattr(dashboard, 'current_service', getattr(self, 'assistant_service_context', 'blockchain'))
            context_parts.append(f"현재 서비스: {current_service}")

            if str(current_service).lower() == 'stock':
                try:
                    settings = getattr(dashboard, 'settings', {}) or {}
                    brokers = settings.get('enabled_stock_brokers', []) or []
                    selected_broker = settings.get('selected_stock_broker', 'kiwoom')
                    stock_asset_mode = settings.get('stock_asset_mode', 'all')

                    context_parts.append("참고: 주식/ETF 모드에서는 시장시간·체결규칙·종목유형을 함께 고려해야 합니다.")
                    context_parts.append("주식/ETF 통합 관리: [주식] 개별 기업 분석 / [ETF] 추적오차·괴리율 모니터링")
                    context_parts.append(f"현재 증권 표시 모드: {stock_asset_mode}")

                    # StockAnalysisService 경유 — 브로커별 AI 컨텍스트 수집
                    try:
                        from trading.stock_analysis_service import StockAnalysisService
                        broker_candidates = [selected_broker] + [b for b in brokers if b != selected_broker]
                        for broker in broker_candidates:
                            adapter = None
                            try:
                                if hasattr(dashboard, '_get_stock_adapter'):
                                    adapter = dashboard._get_stock_adapter(broker)
                            except Exception:
                                pass
                            if not adapter:
                                continue
                            try:
                                if hasattr(adapter, 'is_connected') and not getattr(adapter, 'is_connected', False):
                                    if hasattr(adapter, 'connect'):
                                        adapter.connect()
                            except Exception:
                                pass
                            try:
                                svc = StockAnalysisService(adapter, broker_name=broker)
                                context_parts.append(svc.build_ai_context(asset_mode=stock_asset_mode))
                            except Exception:
                                pass
                    except ImportError:
                        # 분석 서비스 없을 때 폴백
                        if brokers:
                            context_parts.append(f"활성 증권사: {', '.join(str(b) for b in brokers)}")
                        context_parts.append(f"기준 증권사: {selected_broker}")
                except Exception:
                    pass

            # 1. 거래소 정보 및 연결 상태
            if hasattr(dashboard, 'exchange_manager') and dashboard.exchange_manager:
                exchange_manager = dashboard.exchange_manager
                selected_exchange = exchange_manager.settings.get('selected_exchange', 'binance')
                context_parts.append(f"현재 거래소: {selected_exchange}")

                # 거래소 연결 상태 확인 (개선된 버전)
                try:
                    is_connected = exchange_manager.validate_exchange_connection(selected_exchange)
                    connection_status = '연결됨' if is_connected else '연결 안됨'

                    # BinanceClient의 경우 추가 정보 제공
                    if selected_exchange == 'binance' and hasattr(exchange_manager, 'binance_client'):
                        binance_client = exchange_manager.binance_client
                        if binance_client and hasattr(binance_client, 'is_connected'):
                            if binance_client.is_connected:
                                connection_status = '연결됨 (API 검증 완료)'
                            else:
                                connection_status = '연결 안됨 (클라이언트 미연결)'

                    context_parts.append(f"거래소 연결 상태: {connection_status}")
                    # 중요: 설정 변경은 거래소 연결 상태와 무관하게 가능하다는 정보 추가
                    context_parts.append(
                        "참고: 모델·표시 설정은 오프라인 저장할 수 있지만 위험을 높이는 거래 설정은 "
                        "시장·성과·포지션 확인이 완료돼야 대화형 변경을 제안합니다."
                    )
                except Exception as e:
                    context_parts.append(f"거래소 연결 상태: 확인 불가 - {str(e)}")
                    context_parts.append("참고: 연결 상태를 확인할 수 없어 위험 확대형 대화 설정은 제안하지 않습니다.")

                # 2. 잔고 정보 (상세)
                try:
                    balance_result = exchange_manager.get_exchange_balance(selected_exchange)
                    if balance_result.get('status') == 'success':
                        balance = balance_result.get('balance', {})
                        if balance:
                            balance_info = []
                            total_usdt = 0.0
                            for currency, amount in balance.items():
                                numeric_amount = 0.0
                                if isinstance(amount, dict):
                                    numeric_amount = float(
                                        amount.get('wallet_balance', amount.get('walletBalance', amount.get('available_balance', amount.get('availableBalance', 0)))) or 0
                                    )
                                else:
                                    try:
                                        numeric_amount = float(amount or 0)
                                    except Exception:
                                        numeric_amount = 0.0

                                if numeric_amount > 0:
                                    if currency == 'USDT':
                                        total_usdt += numeric_amount
                                    balance_info.append(f"{currency}: {numeric_amount:.4f}")

                            if balance_info:
                                context_parts.append(f"잔고: {', '.join(balance_info)}")
                                context_parts.append(f"총 USDT 가치: {total_usdt:.2f} USDT")
                            else:
                                context_parts.append("잔고: 0 (거래 불가)")
                        else:
                            context_parts.append("잔고: 조회 실패")
                    else:
                        context_parts.append(f"잔고: {balance_result.get('error', balance_result.get('message', '조회 실패'))}")
                except Exception as e:
                    context_parts.append(f"잔고: 조회 오류 - {str(e)}")

            # 3. 현재 설정 정보 (상세)
            if hasattr(dashboard, 'settings') and dashboard.settings:
                settings = dashboard.settings
                context_parts.append(f"레버리지: {settings.get('default_leverage', 1)}x")
                context_parts.append(f"TP: {settings.get('default_tp', 0.15)*100:.1f}%")
                context_parts.append(f"SL: {settings.get('default_sl', 0.10)*100:.1f}%")
                context_parts.append(f"최소 거래 금액: {settings.get('min_trade_amount', 5)} USDT")

                # AI 거래 설정
                ai_prefs = settings.get('ai_trading_preferences', {})
                if ai_prefs:
                    context_parts.append(f"AI 리스크 허용도: {ai_prefs.get('risk_tolerance', 'MODERATE')}")
                    context_parts.append(f"잔고 활용 한도: {ai_prefs.get('balance_utilization_limit', 0.25)*100:.1f}%")

                # RSI 설정
                context_parts.append(f"RSI 기간: {settings.get('rsi_period', 14)}")
                context_parts.append(f"RSI 과매도: {settings.get('rsi_oversold', 30)}")
                context_parts.append(f"RSI 과매수: {settings.get('rsi_overbought', 70)}")

                # 변동성 설정
                context_parts.append(f"변동성 임계값: {settings.get('volatility_threshold', 0.02)*100:.2f}%")
                advanced_layers = settings.get('advanced_trading_layers', {})
                if isinstance(advanced_layers, dict):
                    strategy_policy = advanced_layers.get('strategy_engine', {})
                    if isinstance(strategy_policy, dict):
                        high_vol_action = str(strategy_policy.get('high_vol_action', 'evaluate')).lower()
                        context_parts.append(
                            "고변동장 처리: "
                            + ("항상 차단(block)" if high_vol_action == 'block' else "평가 계속(evaluate)")
                        )
                        context_parts.append(
                            f"전략 합의 임계값: {float(strategy_policy.get('consensus_threshold', 0.60) or 0.60):.2f}"
                        )
                        context_parts.append(
                            f"심볼 쿨다운: {int(strategy_policy.get('cooldown_sec', 60) or 0)}초"
                        )

                # AI 청산 설정
                ai_exit = settings.get('ai_exit_settings', {})
                if ai_exit:
                    context_parts.append(f"AI 수익 청산: {ai_exit.get('min_profit_for_exit', 0.0014)*100:.2f}% ~ {ai_exit.get('max_profit_for_exit', 0.0020)*100:.2f}%")
                    context_parts.append(f"AI 손실 청산: {ai_exit.get('min_loss_for_exit', -0.0015)*100:.2f}% ~ {ai_exit.get('max_loss_for_exit', -0.0005)*100:.2f}%")

            # 4. 거래 통계 (상세) + 최근 거래 내역
            if hasattr(dashboard, 'recorder') and dashboard.recorder:
                recorder = dashboard.recorder
                try:
                    stats = recorder.get_performance_stats(days=30)
                    if stats:
                        total_trades = stats.get('total_trades', 0)
                        winning_trades = stats.get('winning_trades', 0)
                        losing_trades = stats.get('losing_trades', 0)
                        win_rate = stats.get('win_rate', 0.0)
                        total_pnl = stats.get('total_pnl', 0.0)
                        avg_win = stats.get('avg_win', 0.0)
                        avg_loss = stats.get('avg_loss', 0.0)
                        max_drawdown = stats.get('max_drawdown', 0.0)
                        context_parts.append(f"총 거래(30일): {total_trades}회 (승리: {winning_trades}회, 패배: {losing_trades}회)")
                        context_parts.append(f"승률: {win_rate:.1f}%")
                        context_parts.append(f"총 수익: {total_pnl:.2f} USDT")
                        context_parts.append(f"평균 수익: {avg_win:.2f}% | 평균 손실: {avg_loss:.2f}%")
                        context_parts.append(f"최대 낙폭: {max_drawdown:.2f} USDT")
                        if total_trades > 0:
                            avg_profit_per_trade = total_pnl / total_trades
                            context_parts.append(f"거래당 평균 수익: {avg_profit_per_trade:.2f} USDT")
                    else:
                        context_parts.append("거래 통계: 기록 없음 (첫 거래 후 표시됩니다)")
                except Exception as e:
                    context_parts.append(f"거래 통계: 조회 오류 - {str(e)}")

                # 최근 거래 내역 (개별 거래 기록)
                try:
                    recent_trades = recorder.get_trade_history(days=7)
                    if recent_trades:
                        context_parts.append(f"최근 7일 거래 내역 ({min(len(recent_trades), 5)}건):")
                        for trade in recent_trades[:5]:
                            symbol = trade.get('symbol', '?')
                            side = trade.get('side', '?')
                            entry_price = float(trade.get('entry_price', 0) or 0)
                            exit_price = float(trade.get('exit_price', 0) or 0)
                            pnl = float(trade.get('pnl', 0) or 0)
                            exit_time = str(trade.get('exit_time', '') or '')
                            date_str = exit_time[:10] if exit_time else '날짜불명'
                            pnl_sign = "+" if pnl >= 0 else ""
                            context_parts.append(
                                f"  [{date_str}] {symbol} {side} "
                                f"진입:{entry_price:.4f}→청산:{exit_price:.4f} "
                                f"PnL: {pnl_sign}{pnl:.2f} USDT"
                            )
                    else:
                        context_parts.append("최근 거래 내역: 없음")
                except Exception as e:
                    context_parts.append(f"최근 거래 내역: 조회 오류 - {str(e)}")

            # 5. 현재 포지션 (상세)
            try:
                active_positions = {}

                # 바이낸스는 기존 trader 경로 우선
                if selected_exchange == 'binance' and hasattr(dashboard, 'trader') and dashboard.trader:
                    active_positions = getattr(dashboard.trader, 'active_positions', {}) or {}
                elif hasattr(dashboard, 'unified_trader') and dashboard.unified_trader:
                    unified_trader = dashboard.unified_trader
                    active_positions = getattr(unified_trader, 'active_positions', {}) or {}
                    if selected_exchange in active_positions and isinstance(active_positions.get(selected_exchange), dict):
                        active_positions = active_positions.get(selected_exchange, {}) or {}

                if active_positions:
                    position_info = []
                    total_position_value = 0.0
                    for symbol, position in active_positions.items():
                        if not isinstance(position, dict):
                            continue

                        try:
                            size = float(position.get('size', 0) or 0)
                        except Exception:
                            size = 0.0

                        if size <= 0:
                            continue

                        side = position.get('side', 'UNKNOWN')
                        entry_price = float(position.get('entry_price', 0) or 0)
                        current_price = float(position.get('current_price', 0) or 0)
                        pnl = float(position.get('pnl', 0) or 0)

                        position_str = f"{symbol}: {side} {size} @ {entry_price:.4f}"
                        if current_price > 0:
                            position_str += f" (현재: {current_price:.4f}, PnL: {pnl:.2f})"
                            total_position_value += abs(size * current_price)

                        position_info.append(position_str)

                    if position_info:
                        context_parts.append(f"활성 포지션: {', '.join(position_info)}")
                        context_parts.append(f"총 포지션 가치: {total_position_value:.2f} USDT")
                    else:
                        context_parts.append("활성 포지션: 없음")
                else:
                    context_parts.append("활성 포지션: 없음")
            except Exception as e:
                context_parts.append(f"포지션 정보: 조회 오류 - {str(e)}")

            # 6. 시장 데이터 (새로 추가)
            if hasattr(dashboard, 'exchange_manager') and dashboard.exchange_manager:
                try:
                    exchange_manager = dashboard.exchange_manager
                    selected_exchange = exchange_manager.settings.get('selected_exchange', 'binance')

                    # 주요 코인들의 시장 데이터 수집
                    major_coins = ['BTCUSDT', 'ETHUSDT', 'ADAUSDT', 'SOLUSDT', 'DOTUSDT']
                    market_data = []

                    for symbol in major_coins:
                        try:
                            ticker = exchange_manager.get_24h_ticker(symbol, selected_exchange)
                            if ticker and ticker.get('last', 0) > 0:
                                change_pct = ticker.get('percentage', 0)
                                volume = ticker.get('quoteVolume', 0)
                                market_data.append(f"{symbol}: ${ticker['last']:.4f} ({change_pct:+.2f}%) Vol: {volume:,.0f}")
                        except Exception as e:
                            self.logger.debug(f"{symbol} 시장 데이터 조회 실패: {e}")

                    if market_data:
                        context_parts.append("시장 데이터:")
                        context_parts.extend(market_data[:5])  # 상위 5개만 표시

                except Exception as e:
                    context_parts.append(f"시장 데이터: 조회 오류 - {str(e)}")

            # 7. 선택된 거래 코인 정보 및 분석 (새로 추가)
            if hasattr(dashboard, 'selected_coins') and dashboard.selected_coins:
                try:
                    selected_coins = dashboard.selected_coins
                    if selected_coins:
                        coin_list = []
                        for coin in selected_coins[:10]:  # 상위 10개만 표시
                            if isinstance(coin, dict):
                                symbol = coin.get('symbol', 'N/A')
                            else:
                                symbol = str(coin)
                            coin_list.append(symbol)

                        context_parts.append(f"선택된 거래 코인: {', '.join(coin_list)}")

                        # 코인 분석 수행 (UnifiedTrader가 있는 경우)
                        if hasattr(dashboard, 'unified_trader') and dashboard.unified_trader:
                            try:
                                unified_trader = dashboard.unified_trader
                                # 안전한 거래소 선택값 획득
                                selected_exchange_local = 'binance'
                                try:
                                    exm = getattr(dashboard, 'exchange_manager', None)
                                    if exm and hasattr(exm, 'settings') and isinstance(exm.settings, dict):
                                        selected_exchange_local = exm.settings.get('selected_exchange', 'binance')
                                except Exception:
                                    pass

                                # 코인 목록 정규화 후 분석 실행
                                normalized_coins = self._normalize_coins_for_analysis(selected_coins[:5])
                                if normalized_coins:
                                    analysis_results = unified_trader.analyze_coins_unified(selected_exchange_local, normalized_coins)
                                else:
                                    analysis_results = {}

                                if analysis_results:
                                    analysis_info = []
                                    for symbol, analysis in analysis_results.items():
                                        signal = analysis.get('signal', 'HOLD')
                                        confidence = analysis.get('confidence', 0)
                                        reason = analysis.get('reason', '')

                                        analysis_info.append(f"{symbol}: {signal} ({confidence:.2f}) - {reason}")

                                    if analysis_info:
                                        context_parts.append("코인 분석 결과:")
                                        context_parts.extend(analysis_info[:3])  # 상위 3개만 표시

                            except Exception as e:
                                context_parts.append(f"코인 분석: 실행 오류 - {str(e)}")
                    else:
                        context_parts.append("선택된 거래 코인: 없음")
                except Exception as e:
                    context_parts.append(f"거래 코인 정보: 조회 오류 - {str(e)}")

            # 8. AI 학습 데이터 (새로 추가)
            if hasattr(dashboard, 'unified_trader') and dashboard.unified_trader:
                try:
                    unified_trader = dashboard.unified_trader
                    ai_learning_data = getattr(unified_trader, 'ai_learning_data', {})
                    if ai_learning_data:
                        total_patterns = sum(len(patterns) for patterns in ai_learning_data.values())
                        context_parts.append(f"AI 학습 패턴: {total_patterns}개")

                        # 최근 학습된 패턴들
                        recent_patterns = []
                        for exchange, patterns in ai_learning_data.items():
                            if patterns:
                                recent_patterns.append(f"{exchange}: {len(patterns)}개")

                        if recent_patterns:
                            context_parts.append(f"거래소별 학습: {', '.join(recent_patterns)}")
                    else:
                        context_parts.append("AI 학습 데이터: 없음")
                except Exception as e:
                    context_parts.append(f"AI 학습 데이터: 조회 오류 - {str(e)}")

            # 9. 최근 로그 요약 (AI 로그 해석 정확도 보강)
            try:
                recent_log_lines = []
                log_widget = getattr(dashboard, 'realtime_log_widget', None)
                if log_widget and hasattr(log_widget, '_all_logs'):
                    recent_log_lines = list((getattr(log_widget, '_all_logs', []) or [])[-20:])

                if recent_log_lines:
                    context_parts.append("최근 로그 요약(최신 20줄):")
                    for line in recent_log_lines[-8:]:
                        context_parts.append(f"  {str(line).strip()[:220]}")
                else:
                    context_parts.append("최근 로그 요약: 로그 위젯에 아직 수집된 항목이 없습니다.")
            except Exception as e:
                context_parts.append(f"최근 로그 요약: 조회 오류 - {str(e)}")

            # 10. 시스템 상태 (새로 추가)
            try:
                import psutil
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                context_parts.append(f"시스템 상태: CPU {cpu_percent:.1f}%, 메모리 {memory.percent:.1f}%")
            except ImportError:
                context_parts.append("시스템 상태: 모니터링 불가")
            except Exception as e:
                context_parts.append(f"시스템 상태: 조회 오류 - {str(e)}")

            if not context_parts:
                return "거래 상황 정보를 가져올 수 없습니다. 대시보드가 제대로 연결되지 않았거나 거래 시스템이 초기화되지 않았습니다."

            # 디버깅 정보 추가
            self.logger.info(f"AI 어시스턴트 컨텍스트 수집 완료: {len(context_parts)}개 항목")
            for i, part in enumerate(context_parts):
                self.logger.debug(f"컨텍스트 {i+1}: {part}")

            return "\n".join(context_parts)

        except Exception as e:
            self.logger.error(f"거래 상황 수집 오류: {e}")
            return f"거래 상황 수집 중 오류가 발생했습니다: {str(e)}"

    # (중복된 고급 generate_ai_response는 제거되었습니다)

    def _show_settings_proposal(self, ai_response: str, parsed_settings: dict, user_message: str):
        """AI 분석 결과와 설정 변경 제안을 표시하고 Yes/No 확인 버튼을 삽입합니다."""
        try:
            import json as _json
            safe_settings, normalize_notes = self._sanitize_settings_proposal(parsed_settings)
            if not safe_settings:
                self.add_ai_message("AI 제안에 적용 가능한 설정 키가 없어 변경을 중단했습니다.")
                return

            # JSON에서 analysis/recommendation 필드 추출 시도
            analysis_text = ""
            recommendation_text = ""
            summary_message = ""
            reason_text = ""
            try:
                import re
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', ai_response, re.DOTALL)
                if not json_match:
                    json_match = re.search(r'\{.*?"action".*?\}', ai_response, re.DOTALL)
                if json_match:
                    raw = json_match.group(1) if json_match.lastindex else json_match.group(0)
                    parsed_full = _json.loads(raw)
                    analysis_text = parsed_full.get('analysis', '')
                    recommendation_text = parsed_full.get('recommendation', '')
                    summary_message = parsed_full.get('message', '')
                    reason_text = parsed_full.get('reason', '')
            except Exception:
                pass

            # 설정 변경 요약 텍스트 생성
            settings_lines = []
            for key, value in safe_settings.items():
                if key == 'default_leverage':
                    settings_lines.append(f"  • 레버리지: {value}x")
                elif key == 'default_tp':
                    settings_lines.append(f"  • 익절(TP): {value * 100:.2f}%")
                elif key == 'default_sl':
                    settings_lines.append(f"  • 손절(SL): {value * 100:.2f}%")
                elif key == 'risk_tolerance':
                    label_map = {'CONSERVATIVE': '보수적', 'MODERATE': '균형', 'AGGRESSIVE': '적극적'}
                    settings_lines.append(f"  • 리스크 성향: {label_map.get(value, value)}")
                elif key == 'balance_utilization_limit':
                    settings_lines.append(f"  • 잔고 활용 한도: {value * 100:.0f}%")
                elif key == 'strategy_engine_high_vol_action':
                    settings_lines.append(
                        "  • 고변동장 처리: " + ("항상 차단" if value == "block" else "평가 계속")
                    )
                elif key == 'strategy_engine_consensus_threshold':
                    settings_lines.append(f"  • 전략 합의 임계값: {float(value):.2f}")
                elif key == 'strategy_engine_cooldown_sec':
                    settings_lines.append(f"  • 심볼 쿨다운: {int(value)}초")
                else:
                    settings_lines.append(f"  • {key}: {value}")

            # 분석 내용 채팅에 표시
            msg_parts = ["AI 분석 결과:"]
            if analysis_text:
                msg_parts.append(f"\n현황 분석:\n{analysis_text}")
            if recommendation_text:
                msg_parts.append(f"\n추천 이유:\n{recommendation_text}")
            if reason_text and not recommendation_text:
                msg_parts.append(f"\n이유: {reason_text}")
            msg_parts.append(f"\n제안 변경 설정:\n" + "\n".join(settings_lines))
            if normalize_notes:
                msg_parts.append("\n안전 검증 결과:\n" + "\n".join(f"  • {note}" for note in normalize_notes))
            if summary_message:
                msg_parts.append(f"\n{summary_message}")
            msg_parts.append("\n적용 전 최종 확인 대화상자가 한 번 더 표시됩니다.")
            self.add_ai_message("\n".join(msg_parts))

            # 확인 버튼 프레임을 채팅 영역에 삽입
            self._insert_confirm_buttons(safe_settings, user_message)

        except Exception as e:
            self.logger.error(f"_show_settings_proposal 오류: {e}")
            # 오류 시 기존 방식으로 fallback
            self.add_ai_message(f"AI 분석 결과:\n{ai_response}")
            self.add_ai_message("위 설정을 적용하려면 설정관리 버튼을 이용해주세요.")

    def _insert_confirm_buttons(self, parsed_settings: dict, user_message: str):
        """채팅창 하단에 적용/취소 확인 버튼 프레임을 삽입합니다."""
        try:
            context_ok, context_reasons = self._validate_trading_change_context(parsed_settings)
            if not context_ok:
                self.add_ai_message(
                    "안전 정책으로 설정 제안을 적용 단계로 넘기지 않았습니다.\n"
                    + "\n".join(f"- {reason}" for reason in context_reasons)
                    + "\n시장·성과·포지션 데이터를 다시 수집한 뒤 재평가하거나 더 보수적인 변경을 요청해 주세요."
                )
                return

            confirm_frame = CTkFrame(
                self.chat_messages_frame,
                fg_color=self._color("surface"),
                border_color=self._color("primary"),
                border_width=1,
                corner_radius=10
            )
            confirm_frame.pack(fill="x", padx=5, pady=6, anchor="w")

            label = CTkLabel(
                confirm_frame,
                text="위 설정을 적용하시겠습니까?",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=self._color("text_primary")
            )
            label.pack(anchor="w", padx=10, pady=(8, 4))

            btn_row = CTkFrame(confirm_frame, fg_color="transparent")
            btn_row.pack(anchor="w", padx=10, pady=(0, 8))

            def on_apply():
                # 버튼 비활성화 (중복 클릭 방지)
                apply_btn.configure(state="disabled", text="적용 중...")
                cancel_btn.configure(state="disabled")

                # 제안 표시 후 시장·성과·포지션이 달라질 수 있으므로 클릭 시점에 다시 검증한다.
                latest_context_ok, latest_context_reasons = self._validate_trading_change_context(parsed_settings)
                if not latest_context_ok:
                    apply_btn.configure(state="normal", text="적용")
                    cancel_btn.configure(state="normal")
                    self.add_ai_message(
                        "적용 직전 안전 재검증에서 변경을 중단했습니다.\n"
                        + "\n".join(f"- {reason}" for reason in latest_context_reasons)
                    )
                    return

                # 2단계 확인: 채팅 버튼 클릭 후 최종 확인 대화상자를 한 번 더 보여준다.
                if not self._confirm_settings_apply(parsed_settings):
                    apply_btn.configure(state="normal", text="적용")
                    cancel_btn.configure(state="normal")
                    self.add_ai_message("↩최종 확인에서 취소되어 설정을 적용하지 않았습니다.")
                    return

                self._apply_settings_automatically(parsed_settings, user_message)
                confirm_frame.destroy()

            def on_cancel():
                confirm_frame.destroy()
                self.add_ai_message("↩설정 변경이 취소되었습니다.")

            apply_btn = CTkButton(
                btn_row,
                text="적용",
                command=on_apply,
                width=100,
                height=32,
                fg_color=self._color("success"),
                hover_color="#16a34a",
                font=ctk.CTkFont(size=12, weight="bold")
            )
            apply_btn.pack(side="left", padx=(0, 6))

            cancel_btn = CTkButton(
                btn_row,
                text="취소",
                command=on_cancel,
                width=100,
                height=32,
                fg_color=self._color("secondary"),
                hover_color=self._hover_from(self._color("secondary")),
                font=ctk.CTkFont(size=12)
            )
            cancel_btn.pack(side="left")

            # 스크롤 하단 이동
            try:
                self.chat_history.update()
                self.chat_history._parent_canvas.yview_moveto(1.0)
            except Exception:
                pass

        except Exception as e:
            self.logger.error(f"_insert_confirm_buttons 오류: {e}")

    def _sanitize_settings_proposal(self, settings: dict) -> tuple[dict, list[str]]:
        """AI 제안 설정을 허용 키/범위 기준으로 정규화한다."""
        safe: dict = {}
        notes: list[str] = []
        if not isinstance(settings, dict):
            return safe, ["설정 형식이 dict가 아니라 적용하지 않았습니다."]

        def _safe_model_name(raw_value: Any) -> Optional[str]:
            import re
            model_name = str(raw_value or "").strip()
            if not model_name or len(model_name) > 128:
                return None
            # API에서 새 모델이 추가돼도 코드 릴리스 없이 선택할 수 있게 하되,
            # 공백·제어문자·명령 문자열은 설정에 저장하지 않는다.
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model_name):
                return None
            return model_name

        # risk_tolerance와 balance_utilization_limit은 중첩/평탄 구조 모두 허용
        candidate = dict(settings)
        prefs = candidate.get('ai_trading_preferences')
        if isinstance(prefs, dict):
            if 'risk_tolerance' in prefs and 'risk_tolerance' not in candidate:
                candidate['risk_tolerance'] = prefs.get('risk_tolerance')
            if 'balance_utilization_limit' in prefs and 'balance_utilization_limit' not in candidate:
                candidate['balance_utilization_limit'] = prefs.get('balance_utilization_limit')

        for key, value in candidate.items():
            if key == 'default_leverage':
                try:
                    lv = int(value)
                except Exception:
                    notes.append("레버리지는 숫자가 아니어서 제외했습니다.")
                    continue
                clamped = max(1, min(20, lv))
                if clamped != lv:
                    notes.append(f"레버리지를 안전 범위(1~20)로 보정했습니다: {lv} -> {clamped}")
                safe[key] = clamped
            elif key in ('default_tp', 'default_sl'):
                try:
                    pct = float(value)
                except Exception:
                    notes.append(f"{key} 값이 숫자가 아니어서 제외했습니다.")
                    continue
                maximum = 0.05 if key == 'default_tp' else 0.03
                if pct <= 0 or pct > 5:
                    notes.append(f"{key} 값 {pct}은 비율 범위를 벗어나 제외했습니다.")
                    continue
                normalized = pct / 100.0 if pct > maximum else pct
                clamped = max(0.0005, min(maximum, normalized))
                if clamped != pct:
                    notes.append(
                        f"{key}를 fraction 단위로 보정했습니다: {pct} -> {clamped} "
                        f"({clamped * 100:.3f}%)"
                    )
                safe[key] = clamped
            elif key == 'risk_tolerance':
                allowed = {'CONSERVATIVE', 'MODERATE', 'AGGRESSIVE'}
                rt = str(value).upper()
                if rt not in allowed:
                    notes.append(f"risk_tolerance 값 '{value}'는 허용되지 않아 MODERATE로 보정했습니다.")
                    rt = 'MODERATE'
                safe[key] = rt
            elif key == 'balance_utilization_limit':
                try:
                    lim = float(value)
                except Exception:
                    notes.append("잔고 활용 한도 값이 숫자가 아니어서 제외했습니다.")
                    continue
                clamped = max(0.05, min(0.5, lim))
                if clamped != lim:
                    notes.append(f"잔고 활용 한도를 안전 범위(0.05~0.5)로 보정했습니다: {lim} -> {clamped}")
                safe[key] = clamped
            elif key == 'assistant_apply_mode':
                if str(value).strip().lower() not in {
                    'user_confirm', 'confirm', 'manual', '사용자 최종확인', '사용자확인'
                }:
                    notes.append(
                        "거래 관련 AI 자동적용은 지원하지 않아 assistant_apply_mode를 user_confirm으로 고정했습니다."
                    )
                safe[key] = 'user_confirm'
            elif key in ('openai_model', 'assistant_ai_model'):
                model_name = _safe_model_name(value)
                if not model_name:
                    notes.append(f"{key} 값 '{value}'는 안전한 모델명 형식이 아니어서 제외했습니다.")
                    continue
                safe[key] = model_name
            elif key == 'ai_model_roles':
                if not isinstance(value, dict):
                    notes.append("ai_model_roles는 dict 형식이 아니어서 제외했습니다.")
                    continue
                roles_safe = {}
                for tier in ('frequent_cheap', 'standard', 'premium'):
                    tier_model = str(value.get(tier, '')).strip()
                    if not tier_model:
                        continue
                    safe_tier_model = _safe_model_name(tier_model)
                    if not safe_tier_model:
                        notes.append(
                            f"ai_model_roles.{tier} 값 '{tier_model}'는 안전한 모델명 형식이 아니어서 제외했습니다."
                        )
                        continue
                    roles_safe[tier] = safe_tier_model
                if roles_safe:
                    safe[key] = roles_safe
            elif key == 'strategy_engine_high_vol_action':
                action_alias = {
                    'evaluate': 'evaluate',
                    '평가': 'evaluate',
                    '평가 계속': 'evaluate',
                    '차단 해제': 'evaluate',
                    'unblock': 'evaluate',
                    'block': 'block',
                    '차단': 'block',
                    '항상 차단': 'block',
                }
                resolved = action_alias.get(str(value).strip().lower())
                if not resolved:
                    notes.append(
                        f"strategy_engine_high_vol_action 값 '{value}'는 evaluate/block이 아니어서 제외했습니다."
                    )
                    continue
                safe[key] = resolved
            elif key == 'strategy_engine_consensus_threshold':
                try:
                    threshold = float(value)
                except Exception:
                    notes.append("전략 합의 임계값이 숫자가 아니어서 제외했습니다.")
                    continue
                clamped = max(0.10, min(0.95, threshold))
                if clamped != threshold:
                    notes.append(
                        f"전략 합의 임계값을 허용 범위(0.10~0.95)로 보정했습니다: {threshold} -> {clamped}"
                    )
                safe[key] = clamped
            elif key == 'strategy_engine_cooldown_sec':
                try:
                    cooldown = int(float(value))
                except Exception:
                    notes.append("심볼 쿨다운이 숫자가 아니어서 제외했습니다.")
                    continue
                clamped = max(0, min(3600, cooldown))
                if clamped != cooldown:
                    notes.append(f"심볼 쿨다운을 허용 범위(0~3600초)로 보정했습니다: {cooldown} -> {clamped}")
                safe[key] = clamped
            elif key == 'ai_trading_preferences':
                # 위에서 평탄화 처리했으므로 중복 적용 방지
                continue
            else:
                notes.append(f"허용되지 않은 설정 키 '{key}'는 제외했습니다.")

        return safe, notes

    def _build_settings_summary_lines(self, settings: dict) -> list[str]:
        """설정 변경 확인용 요약 문구를 생성한다."""
        lines = []
        for key, value in settings.items():
            if key == 'default_leverage':
                lines.append(f"- 레버리지: {value}x")
            elif key == 'default_tp':
                lines.append(f"- 익절(TP): {value * 100:.2f}%")
            elif key == 'default_sl':
                lines.append(f"- 손절(SL): {value * 100:.2f}%")
            elif key == 'risk_tolerance':
                label_map = {'CONSERVATIVE': '보수적', 'MODERATE': '균형', 'AGGRESSIVE': '적극적'}
                lines.append(f"- 리스크 성향: {label_map.get(str(value).upper(), value)}")
            elif key == 'balance_utilization_limit':
                lines.append(f"- 잔고 활용 한도: {float(value) * 100:.1f}%")
            elif key == 'assistant_apply_mode':
                mode_label = (
                    '사용자 최종확인'
                    if str(value).lower() == 'user_confirm'
                    else '지원 중단 값(사용자 최종확인으로 변환)'
                )
                lines.append(f"- AI 설정 적용 방식: {mode_label}")
            elif key == 'openai_model':
                lines.append(f"- AI 애널리스트 모델: {value}")
            elif key == 'assistant_ai_model':
                lines.append(f"- AI 어시스턴트 모델: {value}")
            elif key == 'ai_model_roles' and isinstance(value, dict):
                lines.append(
                    "- 역할별 모델 배치: "
                    f"frequent_cheap={value.get('frequent_cheap', '미설정')}, "
                    f"standard={value.get('standard', '미설정')}, "
                    f"premium={value.get('premium', '미설정')}"
                )
            elif key == 'strategy_engine_high_vol_action':
                lines.append("- 고변동장 처리: " + ("항상 차단" if value == "block" else "평가 계속"))
            elif key == 'strategy_engine_consensus_threshold':
                lines.append(f"- 전략 합의 임계값: {float(value):.2f}")
            elif key == 'strategy_engine_cooldown_sec':
                lines.append(f"- 심볼 쿨다운: {int(value)}초")
            else:
                lines.append(f"- {key}: {value}")
        return lines

    def _classify_settings_risk(self, settings: dict) -> tuple[str, list[str]]:
        """설정 변경의 위험 수준과 근거를 계산한다."""
        reasons: list[str] = []
        level = "normal"

        leverage = settings.get('default_leverage')
        if leverage is not None:
            try:
                leverage_value = int(leverage)
                if leverage_value >= 15:
                    level = "high"
                    reasons.append(f"레버리지 {leverage_value}x는 고위험 구간입니다.")
                elif leverage_value >= 10 and level != "high":
                    level = "elevated"
                    reasons.append(f"레버리지 {leverage_value}x는 변동성 확대 시 손실이 커질 수 있습니다.")
            except Exception:
                pass

        balance_limit = settings.get('balance_utilization_limit')
        if balance_limit is not None:
            try:
                balance_limit_value = float(balance_limit)
                if balance_limit_value >= 0.40:
                    level = "high"
                    reasons.append(f"잔고 활용 한도 {balance_limit_value * 100:.0f}%는 과도한 자금 노출일 수 있습니다.")
                elif balance_limit_value >= 0.30 and level == "normal":
                    level = "elevated"
                    reasons.append(f"잔고 활용 한도 {balance_limit_value * 100:.0f}%는 보수적 운용보다 공격적입니다.")
            except Exception:
                pass

        risk_tolerance = str(settings.get('risk_tolerance', '')).upper()
        if risk_tolerance == 'AGGRESSIVE' and level != "high":
            level = "elevated"
            reasons.append("리스크 성향이 적극적으로 변경됩니다.")

        high_vol_action = str(settings.get('strategy_engine_high_vol_action', '')).lower()
        if high_vol_action == 'evaluate' and level == "normal":
            level = "elevated"
            reasons.append("고변동장도 평가 대상으로 열리지만 기존 합의·수익성·리스크 가드레일은 유지됩니다.")
        try:
            consensus_threshold = float(settings.get('strategy_engine_consensus_threshold'))
            if consensus_threshold < 0.50:
                if level == "normal":
                    level = "elevated"
                reasons.append(f"전략 합의 임계값 {consensus_threshold:.2f}는 진입 후보를 늘릴 수 있습니다.")
        except Exception:
            pass
        try:
            cooldown_sec = int(settings.get('strategy_engine_cooldown_sec'))
            if cooldown_sec < 30:
                if level == "normal":
                    level = "elevated"
                reasons.append(f"심볼 쿨다운 {cooldown_sec}초는 반복 진입 가능성을 높일 수 있습니다.")
        except Exception:
            pass

        # 고성능 모델 사용은 비용 측면에서 주의 표시
        openai_model = str(settings.get('openai_model', '')).strip()
        assistant_model = str(settings.get('assistant_ai_model', '')).strip()
        role_models = settings.get('ai_model_roles', {}) if isinstance(settings.get('ai_model_roles'), dict) else {}
        all_models = [openai_model, assistant_model] + [str(role_models.get(k, '')).strip() for k in ('frequent_cheap', 'standard', 'premium')]
        high_cost_prefixes = ('gpt-5', 'gpt-4-turbo', 'o1', 'o3', 'o4')
        if any(m.lower().startswith(high_cost_prefixes) for m in all_models if m):
            if level == "normal":
                level = "elevated"
            reasons.append("고성능 모델 선택으로 API 비용이 증가할 수 있습니다.")

        tp = settings.get('default_tp')
        sl = settings.get('default_sl')
        try:
            if tp is not None and sl is not None and float(sl) >= float(tp):
                if level == "normal":
                    level = "elevated"
                reasons.append("손절 폭이 익절 폭 이상이라 손익비가 불리할 수 있습니다.")
        except Exception:
            pass

        return level, reasons

    def _validate_trading_change_context(self, settings: dict) -> tuple[bool, list[str]]:
        """위험 확대형 거래 설정은 충분한 현재 데이터가 있을 때만 적용 제안한다."""
        if not isinstance(settings, dict):
            return False, ["설정 제안 형식이 올바르지 않습니다."]

        trading_keys = {
            'default_leverage',
            'default_tp',
            'default_sl',
            'risk_tolerance',
            'balance_utilization_limit',
            'strategy_engine_high_vol_action',
            'strategy_engine_consensus_threshold',
            'strategy_engine_cooldown_sec',
        }
        if not trading_keys.intersection(settings):
            return True, []

        dashboard = getattr(self, 'parent_dashboard', None)
        current = getattr(dashboard, 'settings', {}) if dashboard is not None else {}
        current = current if isinstance(current, dict) else {}
        prefs = current.get('ai_trading_preferences', {})
        prefs = prefs if isinstance(prefs, dict) else {}
        layers = current.get('advanced_trading_layers', {})
        policy = layers.get('strategy_engine', {}) if isinstance(layers, dict) else {}
        policy = policy if isinstance(policy, dict) else {}

        risk_increase = False
        try:
            risk_increase |= int(settings.get('default_leverage', current.get('default_leverage', 1))) > int(
                current.get('default_leverage', 1)
            )
        except Exception:
            risk_increase = True
        try:
            risk_increase |= float(
                settings.get('balance_utilization_limit', prefs.get('balance_utilization_limit', 0.25))
            ) > float(prefs.get('balance_utilization_limit', 0.25))
        except Exception:
            risk_increase = True
        risk_rank = {'CONSERVATIVE': 0, 'MODERATE': 1, 'AGGRESSIVE': 2}
        if 'risk_tolerance' in settings:
            risk_increase |= risk_rank.get(str(settings.get('risk_tolerance')).upper(), 99) > risk_rank.get(
                str(prefs.get('risk_tolerance', 'MODERATE')).upper(), 1
            )
        if settings.get('strategy_engine_high_vol_action') == 'evaluate':
            risk_increase |= str(policy.get('high_vol_action', 'evaluate')).lower() == 'block'
        try:
            if 'strategy_engine_consensus_threshold' in settings:
                risk_increase |= float(settings['strategy_engine_consensus_threshold']) < float(
                    policy.get('consensus_threshold', 0.60)
                )
        except Exception:
            risk_increase = True
        try:
            if 'strategy_engine_cooldown_sec' in settings:
                risk_increase |= int(settings['strategy_engine_cooldown_sec']) < int(policy.get('cooldown_sec', 60))
        except Exception:
            risk_increase = True
        try:
            if 'default_sl' in settings:
                risk_increase |= float(settings['default_sl']) > float(current.get('default_sl', 0.01))
        except Exception:
            risk_increase = True

        if not risk_increase:
            return True, []
        if dashboard is None:
            return False, ["대시보드가 연결되지 않아 현재 시장·계좌·포지션을 확인할 수 없습니다."]

        context = self._get_current_trading_context()
        reasons: list[str] = []
        if not context or "거래 상황 정보를 가져올 수 없습니다" in context:
            reasons.append("현재 거래 상황을 수집하지 못했습니다.")
        if "시장 데이터:" not in context or "시장 데이터: 조회 오류" in context:
            reasons.append("현재 시장 데이터가 충분하지 않습니다.")
        if "거래 통계: 기록 없음" in context or "거래 통계: 조회 오류" in context:
            reasons.append("검증 가능한 최근 거래 성과가 없습니다.")
        if "총 수익: -" in context:
            reasons.append("최근 성과가 손실 구간이므로 위험을 높이는 변경을 대화로 적용하지 않습니다.")
        if 'default_leverage' in settings and "활성 포지션: 없음" not in context:
            reasons.append("열린 포지션이 있거나 포지션 상태가 불명확해 레버리지 확대를 차단합니다.")
        return (not reasons), reasons

    def _build_settings_diff_lines(self, settings: dict) -> list[str]:
        """현재 설정 대비 변경 전/후 diff를 생성한다."""
        lines: list[str] = []
        dashboard = getattr(self, 'parent_dashboard', None)
        current_settings = getattr(dashboard, 'settings', {}) or {}
        current_prefs = current_settings.get('ai_trading_preferences', {}) if isinstance(current_settings.get('ai_trading_preferences'), dict) else {}
        current_strategy_policy = (
            current_settings.get('advanced_trading_layers', {}).get('strategy_engine', {})
            if isinstance(current_settings.get('advanced_trading_layers'), dict)
            else {}
        )

        for key, value in settings.items():
            if key in ('risk_tolerance', 'balance_utilization_limit'):
                before_value = current_prefs.get(key)
            elif key == 'strategy_engine_high_vol_action':
                before_value = current_strategy_policy.get('high_vol_action', 'evaluate')
            elif key == 'strategy_engine_consensus_threshold':
                before_value = current_strategy_policy.get('consensus_threshold', 0.60)
            elif key == 'strategy_engine_cooldown_sec':
                before_value = current_strategy_policy.get('cooldown_sec', 60)
            else:
                before_value = current_settings.get(key)

            if key in ('default_tp', 'default_sl', 'balance_utilization_limit'):
                try:
                    before_text = f"{float(before_value) * 100:.2f}%" if before_value is not None else "미설정"
                    after_text = f"{float(value) * 100:.2f}%"
                except Exception:
                    before_text = str(before_value)
                    after_text = str(value)
            elif key == 'risk_tolerance':
                label_map = {'CONSERVATIVE': '보수적', 'MODERATE': '균형', 'AGGRESSIVE': '적극적'}
                before_text = label_map.get(str(before_value).upper(), str(before_value) if before_value is not None else '미설정')
                after_text = label_map.get(str(value).upper(), str(value))
            elif key == 'default_leverage':
                before_text = f"{before_value}x" if before_value is not None else "미설정"
                after_text = f"{value}x"
            elif key == 'assistant_apply_mode':
                mode_map = {
                    'user_confirm': '사용자 최종확인',
                    'ai_auto': '지원 중단 값(사용자 최종확인으로 변환)',
                }
                before_text = mode_map.get(str(before_value).lower(), str(before_value) if before_value is not None else '미설정')
                after_text = mode_map.get(str(value).lower(), str(value))
            elif key == 'strategy_engine_high_vol_action':
                action_map = {'evaluate': '평가 계속', 'block': '항상 차단'}
                before_text = action_map.get(str(before_value).lower(), str(before_value))
                after_text = action_map.get(str(value).lower(), str(value))
            elif key == 'strategy_engine_consensus_threshold':
                before_text = f"{float(before_value):.2f}"
                after_text = f"{float(value):.2f}"
            elif key == 'strategy_engine_cooldown_sec':
                before_text = f"{int(before_value)}초"
                after_text = f"{int(value)}초"
            elif key == 'ai_model_roles' and isinstance(value, dict):
                before_roles = before_value if isinstance(before_value, dict) else {}
                before_text = (
                    f"frequent_cheap={before_roles.get('frequent_cheap', '미설정')}, "
                    f"standard={before_roles.get('standard', '미설정')}, "
                    f"premium={before_roles.get('premium', '미설정')}"
                )
                after_text = (
                    f"frequent_cheap={value.get('frequent_cheap', '미설정')}, "
                    f"standard={value.get('standard', '미설정')}, "
                    f"premium={value.get('premium', '미설정')}"
                )
            else:
                before_text = str(before_value)
                after_text = str(value)

            lines.append(f"- {key}: {before_text} -> {after_text}")

        return lines

    def _confirm_settings_apply(self, settings: dict) -> bool:
        """설정 반영 전 최종 확인 대화상자(2차 게이트)를 표시한다."""
        try:
            summary = "\n".join(self._build_settings_summary_lines(settings))
            diff_lines = "\n".join(self._build_settings_diff_lines(settings))
            risk_level, risk_reasons = self._classify_settings_risk(settings)
            risk_header = {
                'high': '고위험 변경 감지',
                'elevated': '주의가 필요한 변경',
                'normal': '일반 변경',
            }.get(risk_level, '일반 변경')
            risk_block = ''
            if risk_reasons:
                risk_block = f"\n\n[{risk_header}]\n" + "\n".join(f"- {reason}" for reason in risk_reasons)
            message = (
                "아래 설정을 적용할까요?\n\n"
                f"[변경 요약]\n{summary}\n\n"
                f"[변경 전/후]\n{diff_lines}"
                f"{risk_block}\n\n"
                "확인 시 settings.json에 저장됩니다."
            )
            return bool(messagebox.askyesno("AI 설정 최종 확인", message))
        except Exception as e:
            self.logger.debug(f"최종 확인 대화상자 표시 실패: {e}")
            # 대화상자 실패 시 안전 우선으로 미적용
            return False

    def _is_settings_change_request(self, message: str) -> bool:
        """사용자 요청이 설정 변경 요청인지 판단.

        분석/조회형 키워드("점검", "알려줘", "보여줘", "분석", "평가", "원인", "왜")가
        포함되면 변경 요청이 아닌 일반 질문으로 분류합니다.
        """
        # 분석/조회형 패턴이 있으면 설정 변경 아님
        analysis_patterns = [
            "점검", "알려줘", "알려 줘", "알려주세요", "알려 주세요",
            "보여줘", "보여 줘", "보여주세요", "보여 주세요",
            "분석", "평가", "원인", "왜", "이유", "어떤지", "어때", "어떤가",
            "현황", "상황", "상태", "확인", "조회", "요약", "통계", "성과",
            "얼마인지", "얼마예요", "얼마인가요", "몇인지", "몇인가요",
        ]
        message_lower = message.lower()
        if any(p in message_lower for p in analysis_patterns):
            return False

        # 명확한 변경 의도 키워드
        change_keywords = [
            "레버리지 높", "레버리지 낮", "레버리지 올", "레버리지 내", "레버리지를",
            "leverage",
            "tp를", "sl를", "tp 높", "sl 낮", "tp 낮", "sl 높",
            "손절 낮", "손절 올", "손절 높", "익절 낮", "익절 올", "익절 높",
            "손절을", "익절을",
            "설정 변경", "설정해", "설정을 바꿔", "설정을 바꿔줘",
            "바꿔줘", "바꿔 줘", "변경해", "변경해줘",
            "조정해줘", "조정해 줘", "수정해줘",
            "보수적으로", "적극적으로", "공격적으로",
            "conservative", "aggressive", "moderate",
            "거래 성향 바", "거래 성향 변",
            "비중 높", "비중 낮", "비중 줄", "비중 늘",
            "포지션 크기", "포지션 비중",
            "안전 모드", "보수 모드",
            "추매", "추가 매수",
            "낮춰줘", "낮춰 줘", "높여줘", "높여 줘",
            "줄여줘", "줄여 줘", "늘려줘", "늘려 줘",
        ]
        return any(keyword in message_lower for keyword in change_keywords)

    def _parse_settings_json_response(self, ai_response: str, user_message: str) -> Optional[dict]:
        """AI 응답에서 JSON 형식의 설정 변경 정보 파싱"""
        try:
            import re
            import json

            # JSON 코드 블록 추출
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', ai_response, re.DOTALL)
            if not json_match:
                # 코드 블록 없이 JSON만 있는 경우
                json_match = re.search(r'\{.*"action".*"settings".*\}', ai_response, re.DOTALL)

            if json_match:
                json_str = json_match.group(1) if json_match.lastindex else json_match.group(0)
                parsed = json.loads(json_str)

                if parsed.get('action') == 'settings_change' and 'settings' in parsed:
                    return parsed.get('settings')

            return None
        except Exception as e:
            self.logger.debug(f"JSON 파싱 실패: {e}")
            return None

    def _apply_settings_automatically(self, settings: dict, user_message: str):
        """사용자 확인이 끝난 설정을 마지막 안전 검증 후 적용한다."""
        try:
            settings, normalize_notes = self._sanitize_settings_proposal(settings)
            if not settings:
                self.add_ai_message("적용 가능한 설정이 없어 저장을 중단했습니다.")
                return

            # UI 호출 외의 경로에서도 저장 직전 검증을 우회할 수 없게 한다.
            context_ok, context_reasons = self._validate_trading_change_context(settings)
            if not context_ok:
                self.add_ai_message(
                    "저장 직전 안전 재검증에서 설정 적용을 중단했습니다.\n"
                    + "\n".join(f"- {reason}" for reason in context_reasons)
                )
                return

            dashboard = getattr(self, 'parent_dashboard', None)
            if not dashboard:
                self.add_ai_message("대시보드에 연결되지 않아 설정을 적용할 수 없습니다.")
                return

            if not hasattr(dashboard, 'settings') or not dashboard.settings:
                self.add_ai_message("설정을 업데이트할 수 없습니다.")
                return

            # 현재 설정 가져오기
            current_settings = copy.deepcopy(dashboard.settings)

            # 설정 업데이트
            before_snapshot_full = copy.deepcopy(dashboard.settings)
            for key, value in settings.items():
                if key == 'risk_tolerance' or key == 'balance_utilization_limit':
                    # ai_trading_preferences 내부 설정
                    if 'ai_trading_preferences' not in current_settings:
                        current_settings['ai_trading_preferences'] = {}
                    current_settings['ai_trading_preferences'][key] = value
                elif key in {
                    'strategy_engine_high_vol_action',
                    'strategy_engine_consensus_threshold',
                    'strategy_engine_cooldown_sec',
                }:
                    layers = current_settings.setdefault('advanced_trading_layers', {})
                    strategy_policy = layers.setdefault('strategy_engine', {})
                    nested_key = {
                        'strategy_engine_high_vol_action': 'high_vol_action',
                        'strategy_engine_consensus_threshold': 'consensus_threshold',
                        'strategy_engine_cooldown_sec': 'cooldown_sec',
                    }[key]
                    strategy_policy[nested_key] = value
                else:
                    # 일반 설정
                    current_settings[key] = value

            # 설정 파일에 저장
            from config.settings import load_settings, save_settings
            if save_settings(current_settings):
                persisted_settings = load_settings() or {}
                expected_values = self._logical_setting_values(current_settings, settings.keys())
                persisted_values = self._logical_setting_values(persisted_settings, settings.keys())
                if persisted_values != expected_values:
                    save_settings(before_snapshot_full)
                    self.add_ai_message(
                        "저장 후 재조회 값이 변경안과 달라 설정을 이전 상태로 되돌렸습니다."
                    )
                    return
                # 대시보드 설정도 업데이트
                dashboard.settings.clear()
                dashboard.settings.update(persisted_settings)

                if 'assistant_apply_mode' in settings:
                    persisted_settings['assistant_apply_mode'] = 'user_confirm'
                    dashboard.settings['assistant_apply_mode'] = 'user_confirm'
                self.require_final_settings_confirmation = True

                self._append_settings_history(
                    changes=settings,
                    before_full=before_snapshot_full,
                    after_full=persisted_settings,
                    source="assistant_confirmed_apply",
                )

                # 성공 메시지
                settings_summary = []
                for key, value in settings.items():
                    if key == 'default_leverage':
                        settings_summary.append(f"레버리지: {value}x")
                    elif key == 'default_tp':
                        settings_summary.append(f"익절: {value*100:.2f}%")
                    elif key == 'default_sl':
                        settings_summary.append(f"손절: {value*100:.2f}%")
                    elif key == 'risk_tolerance':
                        settings_summary.append(f"리스크 허용도: {value}")
                    elif key == 'balance_utilization_limit':
                        settings_summary.append(f"잔고 활용 한도: {value*100:.1f}%")
                    elif key == 'assistant_apply_mode':
                        settings_summary.append("AI 설정 적용 방식: 사용자 최종확인")
                    elif key == 'openai_model':
                        settings_summary.append(f"AI 애널리스트 모델: {value}")
                    elif key == 'assistant_ai_model':
                        settings_summary.append(f"AI 어시스턴트 모델: {value}")
                    elif key == 'ai_model_roles' and isinstance(value, dict):
                        settings_summary.append(
                            "역할별 모델 배치: "
                            f"frequent_cheap={value.get('frequent_cheap', '미설정')}, "
                            f"standard={value.get('standard', '미설정')}, "
                            f"premium={value.get('premium', '미설정')}"
                        )
                    elif key == 'strategy_engine_high_vol_action':
                        settings_summary.append(
                            "고변동장 처리: " + ("항상 차단" if value == "block" else "평가 계속")
                        )
                    elif key == 'strategy_engine_consensus_threshold':
                        settings_summary.append(f"전략 합의 임계값: {float(value):.2f}")
                    elif key == 'strategy_engine_cooldown_sec':
                        settings_summary.append(f"심볼 쿨다운: {int(value)}초")
                    else:
                        settings_summary.append(f"{key}: {value}")

                if normalize_notes:
                    self.add_ai_message("안전 검증 결과:\n" + "\n".join(f"- {note}" for note in normalize_notes))

                self.add_ai_message(f"설정이 성공적으로 변경되었습니다!\n변경된 설정: {', '.join(settings_summary)}")

                # 대시보드에 설정 변경 알림
                if hasattr(dashboard, 'on_settings_changed'):
                    dashboard.on_settings_changed('settings_updated', persisted_settings)
                self.update_strategy_status(persisted_settings)
                self._update_settings_modal_ui_state()
            else:
                self.add_ai_message("설정 저장에 실패했습니다.")

        except Exception as e:
            self.logger.error(f"설정 자동 적용 오류: {e}")
            self.add_ai_message(f"설정 적용 중 오류가 발생했습니다: {str(e)}")

    def _build_protected_action_support(self, message: str) -> Optional[str]:
        """직접 실행 미개방 작업을 일반 상담과 분리해 실행된 것처럼 답하지 않는다."""
        normalized = re.sub(r"\s+", " ", str(message or "").strip().lower())
        if not normalized:
            return None
        question_markers = (
            "알려", "설명", "방법", "어떻게", "어디", "기준", "타이밍",
            "분석", "평가", "가능", "할 수", "해야", "인가", "인가요", "뭐",
        )
        if any(marker in normalized for marker in question_markers):
            return None

        action_id = ""
        understood = ""
        if any(token in normalized for token in ("출금", "송금", "이체", "withdraw", "transfer")):
            action_id = "withdraw_or_transfer"
            understood = "출금·송금 요청"
        elif (
            any(token in normalized for token in ("api 키", "api key", "시크릿", "secret", "passphrase"))
            and any(token in normalized for token in ("바꿔", "변경", "등록", "입력", "삭제", "교체"))
        ):
            action_id = "change_api_credentials"
            understood = "API 자격증명 변경 요청"
        elif (
            any(token in normalized for token in ("거래 시작", "자동매매 시작", "거래 중지", "거래 정지", "자동매매 중지"))
            and any(token in normalized for token in ("해줘", "시작", "중지", "정지", "꺼", "켜"))
        ):
            action_id = "start_or_stop_trading"
            understood = "거래 시작·중지 요청"
        elif (
            any(token in normalized for token in ("매수", "매도", "롱", "숏", "buy", "sell"))
            and any(token in normalized for token in ("해줘", "주문", "진입", "청산", "사줘", "팔아줘", "잡아줘"))
        ):
            action_id = "place_order"
            understood = "주문 실행 요청"
        if not action_id:
            return None

        gates = self.PROTECTED_ACTION_REGISTRY[action_id]["required_gates"]
        gate_labels = {
            "fresh_quote": "최신 시세", "balance": "잔고", "positions": "보유 포지션",
            "open_orders": "미체결 주문", "market_hours": "시장 운영시간",
            "slippage": "예상 슬리피지", "loss_limits": "손실 한도",
            "idempotency_key": "중복 주문 방지키", "kill_switch": "킬스위치",
            "runtime_state": "거래 엔진 상태", "pending_orders": "대기 주문",
            "user_confirmation": "강화 사용자 확인", "secure_settings_ui": "보안 설정 화면",
            "credential_validation": "자격증명 검증", "not_supported": "지원하지 않음",
        }
        required = ", ".join(gate_labels.get(item, item) for item in gates)
        return (
            f"요청을 ‘{understood}’으로 이해했습니다. 주문이나 상태 변경은 실행하지 않았습니다.\n\n"
            "현재 v3.9.0.2의 NoahAI 어시스턴트는 이 작업을 채팅에서 직접 실행하지 않습니다. "
            f"실행 권한을 열기 전에 {required} 검증이 필요합니다.\n"
            "지금은 현재 시장·포지션·설정의 위험을 분석하거나, 대시보드에서 사용자가 직접 실행할 "
            "정확한 위치와 확인 항목을 안내할 수 있습니다."
        )

    def _extract_recommended_settings(self, ai_response: str, user_message: str) -> dict:
        """AI 응답에서 권장 설정을 추출"""
        try:
            # 간단한 키워드 기반 설정 추출 (실제로는 더 정교한 파싱 필요)
            recommended_settings = {}

            # 레버리지 관련 표현 개선
            leverage_keywords = ["레버리지", "leverage"]
            leverage_increase = ["높이", "증가", "올려", "올리", "up", "increase", "raise"]
            leverage_decrease = ["낮추", "감소", "내려", "줄여", "down", "decrease", "lower", "reduce"]

            if any(kw in user_message.lower() or kw in ai_response.lower() for kw in leverage_keywords):
                user_lower = user_message.lower()
                if any(kw in user_lower for kw in leverage_decrease):
                    # 현재 레버리지 확인 후 감소
                    dashboard = getattr(self, 'parent_dashboard', None)
                    if dashboard and hasattr(dashboard, 'settings'):
                        current_leverage = dashboard.settings.get('default_leverage', 1)
                        recommended_settings['default_leverage'] = max(1, current_leverage - 1)
                    else:
                        recommended_settings['default_leverage'] = 1
                elif any(kw in user_lower for kw in leverage_increase):
                    dashboard = getattr(self, 'parent_dashboard', None)
                    if dashboard and hasattr(dashboard, 'settings'):
                        current_leverage = dashboard.settings.get('default_leverage', 1)
                        recommended_settings['default_leverage'] = min(20, current_leverage + 1)
                    else:
                        recommended_settings['default_leverage'] = 2

            # 포지션/비중 관련 표현 개선
            position_keywords = ["포지션", "비중", "사이즈", "규모", "수량", "추매", "포지션 늘려", "비중 높여"]
            if any(kw in user_message.lower() for kw in position_keywords):
                dashboard = getattr(self, 'parent_dashboard', None)
                current_limit = 0.25
                if dashboard and hasattr(dashboard, 'settings'):
                    current_limit = dashboard.settings.get('ai_trading_preferences', {}).get('balance_utilization_limit', 0.25)

                user_lower = user_message.lower()
                if any(kw in user_lower for kw in ["늘려", "높여", "증가", "확대", "추매"]):
                    recommended_settings['ai_trading_preferences'] = {
                        'risk_tolerance': 'AGGRESSIVE' if '공격' in user_lower or '적극' in user_lower else 'MODERATE',
                        'balance_utilization_limit': min(0.50, current_limit + 0.05)
                    }
                elif any(kw in user_lower for kw in ["줄여", "낮춰", "감소", "축소"]):
                    recommended_settings['ai_trading_preferences'] = {
                        'risk_tolerance': 'CONSERVATIVE' if '보수' in user_lower or '안전' in user_lower else 'MODERATE',
                        'balance_utilization_limit': max(0.10, current_limit - 0.05)
                    }

            # TP/SL 관련 표현 개선
            tp_sl_keywords = ["tp", "sl", "손절", "익절", "take profit", "stop loss"]
            if any(kw in user_message.lower() or kw in ai_response.lower() for kw in tp_sl_keywords):
                user_lower = user_message.lower()
                if "tp" in user_lower or "익절" in user_lower:
                    if any(kw in user_lower for kw in ["높이", "증가", "올려", "up", "increase"]):
                        dashboard = getattr(self, 'parent_dashboard', None)
                        if dashboard and hasattr(dashboard, 'settings'):
                            current_tp = dashboard.settings.get('default_tp', 0.0018)
                            recommended_settings['default_tp'] = min(0.1, current_tp * 1.2)
                        else:
                            recommended_settings['default_tp'] = 0.0025
                    elif any(kw in user_lower for kw in ["낮추", "감소", "내려", "down", "decrease"]):
                        dashboard = getattr(self, 'parent_dashboard', None)
                        if dashboard and hasattr(dashboard, 'settings'):
                            current_tp = dashboard.settings.get('default_tp', 0.0018)
                            recommended_settings['default_tp'] = max(0.001, current_tp * 0.8)
                        else:
                            recommended_settings['default_tp'] = 0.0015

                if "sl" in user_lower or "손절" in user_lower:
                    if any(kw in user_lower for kw in ["높이", "증가", "올려", "up", "increase"]):
                        dashboard = getattr(self, 'parent_dashboard', None)
                        if dashboard and hasattr(dashboard, 'settings'):
                            current_sl = dashboard.settings.get('default_sl', 0.002)
                            recommended_settings['default_sl'] = min(0.1, current_sl * 1.2)
                        else:
                            recommended_settings['default_sl'] = 0.0025
                    elif any(kw in user_lower for kw in ["낮추", "감소", "내려", "down", "decrease"]):
                        dashboard = getattr(self, 'parent_dashboard', None)
                        if dashboard and hasattr(dashboard, 'settings'):
                            current_sl = dashboard.settings.get('default_sl', 0.002)
                            recommended_settings['default_sl'] = max(0.001, current_sl * 0.8)
                        else:
                            recommended_settings['default_sl'] = 0.0015

                # 보수/적극 모드
                if "보수" in user_lower or "안전" in user_lower:
                    recommended_settings['default_tp'] = 0.0015
                    recommended_settings['default_sl'] = 0.0010
                elif "공격" in user_lower or "적극" in user_lower:
                    recommended_settings['default_tp'] = 0.0025
                    recommended_settings['default_sl'] = 0.0020

            # AI 청산 설정 추가
            if "AI 청산" in user_message or "수익 목표" in user_message or "청산 범위" in user_message:
                if "보수" in user_message or "안전" in user_message:
                    recommended_settings['ai_exit_settings'] = {
                        'min_profit_for_exit': 0.0020,    # 0.20% (수수료 + @)
                        'max_profit_for_exit': 0.0030,    # 0.30%
                        'min_loss_for_exit': -0.0010,     # -0.10%
                        'max_loss_for_exit': -0.0003      # -0.03%
                    }
                elif "공격" in user_message or "적극" in user_message:
                    recommended_settings['ai_exit_settings'] = {
                        'min_profit_for_exit': 0.0010,    # 0.10% (수수료 + @)
                        'max_profit_for_exit': 0.0015,    # 0.15%
                        'min_loss_for_exit': -0.0020,     # -0.20%
                        'max_loss_for_exit': -0.0010      # -0.10%
                    }
                elif "중간" in user_message or "균형" in user_message:
                    recommended_settings['ai_exit_settings'] = {
                        'min_profit_for_exit': 0.0014,    # 0.14% (수수료 + @)
                        'max_profit_for_exit': 0.0020,    # 0.20%
                        'min_loss_for_exit': -0.01,       # -1.0%
                        'max_loss_for_exit': -0.0005      # -0.05%
                    }

            # 리스크 허용도 관련 표현 개선
            risk_keywords = ["보수", "적극", "중간", "conservative", "aggressive", "moderate", "리스크", "risk"]
            if any(kw in user_message.lower() for kw in risk_keywords):
                user_lower = user_message.lower()
                if "보수" in user_lower or "conservative" in user_lower:
                    recommended_settings['ai_trading_preferences'] = {
                        'risk_tolerance': 'CONSERVATIVE',
                        'balance_utilization_limit': 0.10
                    }
                elif "적극" in user_lower or "aggressive" in user_lower:
                    recommended_settings['ai_trading_preferences'] = {
                        'risk_tolerance': 'AGGRESSIVE',
                        'balance_utilization_limit': 0.40
                    }
                elif "중간" in user_lower or "moderate" in user_lower or "균형" in user_lower:
                    recommended_settings['ai_trading_preferences'] = {
                        'risk_tolerance': 'MODERATE',
                        'balance_utilization_limit': 0.25
                    }

            if "RSI" in user_message or "기술적" in user_message:
                recommended_settings['rsi_period'] = 14
                if "보수" in user_message:
                    recommended_settings['rsi_oversold'] = 30
                    recommended_settings['rsi_overbought'] = 70
                else:
                    recommended_settings['rsi_oversold'] = 25
                    recommended_settings['rsi_overbought'] = 75

            return recommended_settings

        except Exception as e:
            self.logger.error(f"설정 추출 오류: {e}")
            return {}

    def apply_recommended_settings(self):
        """AI가 권장한 설정을 실제로 적용"""
        try:
            if not self.current_recommended_settings:
                self.add_ai_message("적용할 권장 설정이 없습니다.")
                return
            safe_settings, notes = self._sanitize_settings_proposal(self.current_recommended_settings)
            if notes:
                self.add_ai_message("권장안 안전 검증:\n" + "\n".join(f"- {note}" for note in notes))
            if not safe_settings:
                self.add_ai_message("허용된 타입형 설정이 없어 권장안 적용을 중단했습니다.")
                return
            if not self._confirm_settings_apply(safe_settings):
                self.add_ai_message("사용자가 권장 설정 적용을 취소했습니다.")
                return
            self.current_recommended_settings = None
            self._apply_settings_automatically(safe_settings, "AI 권장 설정")

        except Exception as e:
            self.logger.error(f"설정 적용 오류: {e}")
            self.add_ai_message(f"설정 적용 중 오류가 발생했습니다: {str(e)}")

    def reject_recommended_settings(self):
        """AI 권장 설정 거부"""
        try:
            self.current_recommended_settings = None
            self.add_ai_message("AI 권장 설정이 거부되었습니다.")
        except Exception as e:
            self.logger.error(f"설정 거부 오류: {e}")

    # 중복된 send_quick_question 정의 제거

    # 중복된 send_ai_message 정의 제거

    # --- Chart Screenshot Analyzer Integration ---
    def open_chart_analyzer(self):
        try:
            if ChartScreenshotWidget is None:
                messagebox.showwarning("기능 사용 불가", "차트 분석 위젯을 불러올 수 없습니다.")
                return

            # 기존 AI 세션 재사용
            ai_client = getattr(self.ai_manager, 'client', None)

            window = ctk.CTkToplevel(self)
            window.title("NoahAI 차트 스크린샷 분석기")
            window.geometry("880x720")
            # 화면 중앙 배치
            try:
                window.update_idletasks()
                x = (window.winfo_screenwidth() // 2) - (880 // 2)
                y = (window.winfo_screenheight() // 2) - (720 // 2)
                window.geometry(f"880x720+{x}+{y}")
            except Exception:
                pass

            widget = ChartScreenshotWidget(window, ai_client=ai_client)
            widget.pack(fill="both", expand=True)
        except Exception as e:
            try:
                self.logger.error(f"차트 분석기 열기 오류: {e}")
            except Exception:
                pass
            try:
                messagebox.showerror("차트 분석", f"차트 분석 창을 열 수 없습니다.\n{e}")
            except Exception:
                pass
