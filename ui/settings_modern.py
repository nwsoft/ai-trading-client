#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
현대적 설정 창 (CustomTkinter 기반)
고정 스킨 디자인 (테마 시스템 제거됨)
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import threading
import platform
import struct
import sys
import os
import subprocess
import webbrowser
import json
import re
import copy
from urllib import request as urllib_request
from urllib import error as urllib_error
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, Dict, List

# 고정 색상 import
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.fixed_colors import FIXED_COLORS
from api.binance_client import BinanceClient, BinanceConfig
from config.app_version import RELEASE_BUILD_LABEL
from ui.ai_custom_guidance import build_ai_custom_provider_guide
from ui.live_trading_guidance import build_live_trading_guide
from ui.visual_system import get_ui_icon, style_tabview
from trading.ai.model_registry import (
    model_record,
    model_status_text,
    selectable_models,
    validate_model_route,
)
from membership_policy import normalize_user_grade, referral_exchange_entitlement
import threading

class ModernSettingsWindow:
    """현대적 설정 창 - 고정 스킨 디자인"""

    _AI_MODEL_FALLBACKS = selectable_models("openai")
    _AI_PROVIDER_LABELS = {
        "OpenAI": "openai",
        "DeepSeek": "deepseek",
        "Kimi (Moonshot AI)": "kimi",
        "Anthropic Claude": "anthropic",
        "Google Gemini": "gemini",
    }
    _AI_PROVIDER_MODELS = {
        "openai": _AI_MODEL_FALLBACKS,
        "deepseek": selectable_models("deepseek"),
        "kimi": selectable_models("kimi"),
        "anthropic": selectable_models("anthropic"),
        "gemini": selectable_models("gemini"),
    }
    _AI_PROVIDER_BASE_URLS = {
        "openai": "",
        "deepseek": "https://api.deepseek.com",
        "kimi": "https://api.moonshot.ai/v1",
        "anthropic": "https://api.anthropic.com",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    }
    _AI_PROVIDER_CONSOLES = {
        "openai": "https://platform.openai.com/api-keys",
        "deepseek": "https://platform.deepseek.com/api_keys",
        "kimi": "https://platform.moonshot.ai/console/api-keys",
        "anthropic": "https://console.anthropic.com/settings/keys",
        "gemini": "https://aistudio.google.com/app/apikey",
    }

    _STOCK_BROKER_CHECKLIST_RELATIVE_PATH = os.path.join(
        'docs', 'STOCK_BROKER_WINDOWS_CONNECTION_CHECKLIST_20260611.md'
    )

    _STOCK_API_VERSION_OPTIONS = {
        'kiwoom': {
            'openapi_plus': ['pykiwoom'],
            'mock': ['mock'],
        },
        'shinhan': {
            'partner_rest': ['shinhan_openapi_v2'],
            'mock': ['mock'],
        },
        'miraeAsset': {
            'partner_rest': ['mirae_partner_profile'],
            'mock': ['mock'],
        },
        'koreaInvestment': {
            'rest': ['kis_openapi_v1'],
            'mock': ['mock'],
        },
    }

    _UPDATE_REPOSITORIES = [
        "nwsoft/ai-trading-clinet-pro",
        "nwosft/ai-trading-client",
        "nwsoft/ai-trading-client",
    ]

    def __init__(
        self,
        parent=None,
        current_settings=None,
        on_save_callback=None,
        ai_diagnosis_result=None,
        membership_user_grade=None,
        membership_policy=None,
    ):
        self.parent = parent
        # 대시보드에서 여는 설정은 프로세스 수명 동안 한 창만 재사용한다.
        # 30개가 넘는 CTk 드롭다운의 native tk.Menu를 매번 재할당하면
        # Windows USER/Menu 한도에 도달할 수 있다. 독립 실행 창만 닫을 때 파괴한다.
        self._reuse_on_close = parent is not None
        self.root = ctk.CTkToplevel(parent) if parent else ctk.CTk()
        self.root.title("NoahAI Trading - 설정")
        self.root.geometry("900x800")
        self.root.resizable(True, True)
        self._apply_window_branding(self.root)

        # 모달 창 설정
        if parent:
            self.root.transient(parent)

        # 설정 데이터
        self.current_settings = current_settings or {}
        self._ai_provider_key_buffer: Dict[str, str] = {}
        self._ai_discovered_models: Dict[str, List[str]] = {}
        self._closed = False
        self.ai_diagnosis_result = self._normalize_ai_diagnosis_result(ai_diagnosis_result)
        # Pylance 타입 에러 방지용 명시적 초기화
        self.exchange_var = None
        self.original_settings = copy.deepcopy(self.current_settings)
        self.on_save_callback = on_save_callback  # 콜백 함수 저장
        self.main_app = getattr(parent, 'main_app', None) if parent is not None else None
        self.membership_user_grade = normalize_user_grade(
            membership_user_grade
            if membership_user_grade is not None
            else getattr(self.main_app, 'current_user_grade', 'pro_coin')
        )
        self.membership_policy = dict(
            membership_policy
            if isinstance(membership_policy, dict)
            else getattr(self.main_app, 'current_membership_policy', {}) or {}
        )
        self._referral_status_labels: Dict[str, Any] = {}
        self._referral_api_controls: Dict[str, List[Any]] = {}
        self._referral_selection_controls: Dict[str, List[Any]] = {}
        # 설정 본문이 800px 창 밖으로 밀리지 않도록 상세 진단은 기본 접힘이다.
        self._ai_diagnosis_collapsed = True
        self._ai_diagnosis_body_frame = None

        # Pylance 에러 방지: 조건부 생성되는 UI 속성은 None으로 초기화
        self.margin_type_combo = None
        self.dynamic_mode_combo = None
        self.manual_regime_combo = None

        try:
            # UI 설정
            self.setup_ui()
            # 현재 설정 로드(어떤 방식으로 띄우든 값 주입)
            self.load_current_settings()
            self.refresh_referral_entitlements()

            # 창 닫기 이벤트 핸들러 설정
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
            self.root.bind("<Destroy>", self._mark_window_closed, add="+")

            # 중앙 정렬
            self.center_window()
        except Exception:
            # 생성 중 실패한 빈 Toplevel이 대시보드를 가로막지 않게 즉시 정리한다.
            try:
                self.root.destroy()
            except Exception:
                pass
            raise

        # 모든 위젯 생성이 끝난 뒤에만 모달 잠금을 건다.
        if parent:
            self.root.after_idle(self._activate_modal)

    def _activate_modal(self) -> None:
        """완전히 그려진 설정창만 모달로 활성화한다."""
        if not self._window_alive():
            return
        try:
            self.root.lift()
            self.root.grab_set()
            self.root.focus_force()
        except (tk.TclError, RuntimeError):
            pass

    def _color(self, key: str, fallback: str = "#9ca3af") -> str:
        """고정 색상 접근 헬퍼"""
        return FIXED_COLORS.get(key, fallback)

    def _current_membership_contract(self) -> tuple[str, Dict[str, Any]]:
        main_app = getattr(self, 'main_app', None)
        grade = normalize_user_grade(
            getattr(main_app, 'current_user_grade', self.membership_user_grade)
        )
        raw_policy = getattr(main_app, 'current_membership_policy', self.membership_policy)
        policy = dict(raw_policy or {}) if isinstance(raw_policy, dict) else {}
        self.membership_user_grade = grade
        self.membership_policy = policy
        return grade, policy

    def _referral_entitlement(self, exchange: str) -> Dict[str, Any]:
        grade, policy = self._current_membership_contract()
        return referral_exchange_entitlement(grade, exchange, policy)

    def _open_referral_url(self, exchange: str) -> None:
        entitlement = self._referral_entitlement(exchange)
        url = str(entitlement.get('referral_url') or '').strip()
        if not url.lower().startswith('https://'):
            messagebox.showwarning(
                "레퍼럴 가입 링크",
                "서버에서 검증된 HTTPS 가입 링크가 아직 준비되지 않았습니다.",
            )
            return
        webbrowser.open(url)

    @staticmethod
    def _open_referral_dashboard() -> None:
        webbrowser.open("https://daltrading.net/auth/dashboard")

    def _add_referral_entitlement_banner(self, parent, exchange: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="#0d1b2c", border_width=1, border_color="#31506f")
        row.pack(fill="x", padx=20, pady=(0, 12))
        entitlement = self._referral_entitlement(exchange)
        status = str(entitlement.get('status') or '')
        allowed = bool(entitlement.get('allowed'))
        color = "#34d399" if allowed or status == "paid_exempt" else "#fbbf24"
        if status in {"rejected", "expired"}:
            color = "#fb7185"
        label = ctk.CTkLabel(
            row,
            text=str(entitlement.get('label') or "레퍼럴 상태 확인 필요"),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=color,
        )
        label.pack(side="left", padx=10, pady=8)
        self._referral_status_labels[exchange] = label
        if self.membership_user_grade == "referral":
            ctk.CTkButton(
                row,
                text="가입 링크",
                width=86,
                height=28,
                command=lambda ex=exchange: self._open_referral_url(ex),
            ).pack(side="right", padx=(4, 8), pady=6)
            ctk.CTkButton(
                row,
                text="가입·상태",
                width=110,
                height=28,
                fg_color="#0f766e",
                command=self._open_referral_dashboard,
            ).pack(side="right", padx=4, pady=6)

    def _register_referral_api_controls(self, exchange: str, *widgets: Any) -> None:
        self._referral_api_controls.setdefault(exchange, []).extend(
            widget for widget in widgets if widget is not None
        )

    def _register_referral_selection_controls(self, exchange: str, *widgets: Any) -> None:
        self._referral_selection_controls.setdefault(exchange, []).extend(
            widget for widget in widgets if widget is not None
        )

    def _apply_referral_control_state(self, exchange: str) -> None:
        entitlement = self._referral_entitlement(exchange)
        grade = self.membership_user_grade
        allowed = bool(entitlement.get('allowed')) if grade == "referral" else True
        can_verify = bool(entitlement.get('can_verify_affiliation')) if grade == "referral" else True
        if not allowed:
            exchange_vars = getattr(self, 'exchange_vars', {}) or {}
            trade_vars = getattr(self, 'trade_exchange_vars', {}) or {}
            if exchange in exchange_vars:
                exchange_vars[exchange].set(False)
            if exchange in trade_vars:
                trade_vars[exchange].set(False)
        for widget in self._referral_api_controls.get(exchange, []):
            try:
                widget.configure(state="normal" if can_verify else "disabled")
            except Exception:
                pass
        for widget in self._referral_selection_controls.get(exchange, []):
            try:
                widget.configure(state="normal" if allowed else "disabled")
            except Exception:
                pass
        label = self._referral_status_labels.get(exchange)
        if label is not None:
            status = str(entitlement.get('status') or '')
            color = "#34d399" if allowed or status == "paid_exempt" else "#fbbf24"
            if status in {"rejected", "expired"}:
                color = "#fb7185"
            try:
                label.configure(text=entitlement.get('label', ''), text_color=color)
            except Exception:
                pass

    def refresh_referral_entitlements(self) -> None:
        for exchange in ("binance", "bybit", "okx", "bitget"):
            self._apply_referral_control_state(exchange)

    def _ensure_referral_api_allowed(self, exchange: str, status_var: Any) -> bool:
        entitlement = self._referral_entitlement(exchange)
        if (
            self.membership_user_grade != "referral"
            or bool(entitlement.get('allowed'))
            or bool(entitlement.get('can_verify_affiliation'))
        ):
            return True
        try:
            status_var.set(str(entitlement.get('label') or "레퍼럴 승인 후 사용할 수 있습니다."))
        except Exception:
            pass
        messagebox.showwarning(
            "레퍼럴 귀속 확인 필요",
            f"{str(entitlement.get('label') or '레퍼럴 승인 필요')}\n\n"
            "서버에서 이 거래소가 활성화되어야 API 키 검증과 레퍼럴 자동 확인을 진행할 수 있습니다.",
        )
        return False

    def _apply_auto_referral_result(self, exchange: str, result: Dict[str, Any], status_var: Any) -> None:
        status = str(result.get("status") or "pending").strip().lower()
        policy = result.get("membership_policy")
        if isinstance(policy, dict):
            self.membership_policy = dict(policy)
            main_app = getattr(self, 'main_app', None)
            apply_policy = getattr(main_app, 'apply_server_membership_policy', None)
            if callable(apply_policy):
                apply_policy("referral", policy)
        self.refresh_referral_entitlements()
        if status == "verified":
            status_var.set("API 검증 · 레퍼럴 자동 승인 완료")
        elif status == "rejected":
            status_var.set("API 검증 · 레퍼럴 귀속 불일치")
            messagebox.showwarning(
                "레퍼럴 귀속 불일치",
                "API 키는 유효하지만 NoahAI Affiliate 고객으로 확인되지 않아 거래 기능이 차단됩니다. "
                "공식 가입 링크와 거래소 계정을 확인하세요.",
            )
        else:
            status_var.set("API 검증 · 서버 자동 확인 대기")
            messagebox.showinfo(
                "레퍼럴 자동 확인 대기",
                "UID는 자동 제출되었습니다. 운영 서버의 Affiliate 조회 키가 준비되지 않았거나 거래소 응답을 "
                "재확인해야 하므로 거래 기능은 승인 전까지 차단됩니다.",
            )

    def _auto_verify_referral_after_api_check(
        self,
        exchange: str,
        api_key: str,
        secret_key: str,
        status_var: Any,
        passphrase: str = "",
    ) -> None:
        if self.membership_user_grade != "referral":
            self.root.after(0, lambda: status_var.set("검증 완료"))
            return
        try:
            from referral_account_proof import verify_and_submit

            result = verify_and_submit(exchange, api_key, secret_key, passphrase)
            self.root.after(
                0,
                lambda ex=exchange, payload=result, var=status_var: self._apply_auto_referral_result(
                    ex, payload, var
                ),
            )
        except Exception as exc:
            safe_message = str(exc)[:180] or "레퍼럴 자동 확인 실패"
            self.root.after(
                0,
                lambda msg=safe_message, var=status_var: var.set(f"API 검증 · {msg}"),
            )

    def _mark_window_closed(self, event=None) -> None:
        if event is None or getattr(event, "widget", None) is self.root:
            self._closed = True

    def _window_alive(self) -> bool:
        try:
            return not self._closed and bool(self.root.winfo_exists())
        except Exception:
            return False

    def show(self, *, ai_diagnosis_result=None) -> bool:
        """이미 생성된 설정 창을 다시 표시하고 같은 widget/menu 트리를 재사용한다."""
        if not self._window_alive():
            return False
        if ai_diagnosis_result is not None:
            self.ai_diagnosis_result = self._normalize_ai_diagnosis_result(
                ai_diagnosis_result
            )
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.after_idle(self._activate_modal)
            return True
        except (tk.TclError, RuntimeError):
            return False

    def _hide_or_destroy(self) -> None:
        """대시보드 소유 창은 숨기고, 독립 창은 완전히 종료한다."""
        try:
            self.root.grab_release()
        except Exception:
            pass
        if self._reuse_on_close and self._window_alive():
            try:
                self.root.withdraw()
                return
            except Exception:
                pass
        self.dispose()

    def dispose(self) -> None:
        """앱 종료 시 재사용 설정 창과 타이머를 명시적으로 파괴한다."""
        try:
            if getattr(self, '_ai_status_timer', None):
                self.root.after_cancel(self._ai_status_timer)
                self._ai_status_timer = None
        except Exception:
            pass
        try:
            self.root.grab_release()
        except Exception:
            pass
        try:
            if self.root.winfo_exists():
                self.root.destroy()
        except Exception:
            pass

    def _read_live_widget(self, attribute: str, default: Any = "") -> Any:
        """파괴 중인 설정 입력 위젯의 Tcl command를 다시 호출하지 않는다."""
        if not self._window_alive():
            return default
        widget = getattr(self, attribute, None)
        if widget is None or not hasattr(widget, "get"):
            return default
        try:
            if hasattr(widget, "winfo_exists") and not widget.winfo_exists():
                return default
            return widget.get()
        except (tk.TclError, RuntimeError):
            return default

    def _dispatch_window_result(self, callback) -> bool:
        """백그라운드 AI 조회 결과를 살아 있는 설정 창에만 전달한다."""
        if not self._window_alive():
            return False
        try:
            def guarded():
                if self._window_alive():
                    callback()

            self.root.after(0, guarded)
            return True
        except (tk.TclError, RuntimeError):
            return False

    def _apply_window_branding(self, window) -> None:
        """설정/확인창에 Python 기본 아이콘 대신 NoahAI 아이콘을 적용한다."""
        try:
            root_dir = Path(__file__).resolve().parents[1]
            ico_path = root_dir / "icon.ico"
            png_path = root_dir / "icon.png"
            if sys.platform.startswith("win") and ico_path.exists():
                window.iconbitmap(str(ico_path))
            if png_path.exists():
                photo = tk.PhotoImage(file=str(png_path))
                window.iconphoto(True, photo)
                refs = getattr(self, "_branding_image_refs", [])
                refs.append(photo)
                self._branding_image_refs = refs
        except Exception:
            pass

    def _add_tab_save_bar(self, tab, section_name: str) -> None:
        """긴 설정 탭에서 저장과 문맥 도움말을 즉시 찾을 수 있는 상단 바를 만든다."""
        bar = ctk.CTkFrame(
            tab, height=44, fg_color="#111827", corner_radius=10,
            border_width=1, border_color="#273449",
        )
        bar.pack(fill="x", padx=20, pady=(12, 0))
        ctk.CTkLabel(
            bar,
            text=f"{section_name} · 변경 후 저장을 눌러야 적용됩니다.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#a9bad0",
        ).pack(side="left", padx=14, pady=9)
        ctk.CTkButton(
            bar,
            text="현재 설정 저장",
            image=get_ui_icon("save", (15, 15), "#ffffff"),
            compound="left",
            width=150,
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=self._color("success", "#10b981"),
            hover_color="#059669",
            command=self.save_settings,
        ).pack(side="right", padx=8, pady=6)
        ctk.CTkButton(
            bar,
            text="AI에게 묻기",
            image=get_ui_icon("spark", (15, 15), "#ffffff"),
            compound="left",
            width=128,
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=self._color("primary", "#3b82f6"),
            hover_color="#2563eb",
            command=lambda name=section_name: self._ask_ai_about_settings(name),
        ).pack(side="right", padx=(4, 0), pady=6)

    def _ask_ai_about_settings(self, section_name: str) -> None:
        """현재 설정 탭의 목적·저장값·영향을 AI 어시스턴트에 질문한다."""
        try:
            dashboard = getattr(self, "parent", None)
            if dashboard is None:
                messagebox.showinfo(
                    "AI에게 묻기",
                    "대시보드가 연결되지 않아 AI 어시스턴트를 열 수 없습니다.",
                )
                return

            resolver = getattr(dashboard, "_get_live_ai_assistant", None)
            if callable(resolver):
                assistant = resolver()
            else:
                if hasattr(dashboard, "_ensure_ai_assistant_tab"):
                    dashboard._ensure_ai_assistant_tab()
                assistant = getattr(dashboard, "ai_assistant_widget", None)
            if assistant is None or not hasattr(assistant, "send_quick_question"):
                messagebox.showwarning(
                    "AI에게 묻기",
                    "AI 어시스턴트를 불러오지 못했습니다. 대시보드에서 다시 시도해 주세요.",
                )
                return

            prompt = (
                f"설정 → {section_name} 화면을 현재 저장 설정 기준으로 설명해줘. "
                "각 항목의 목적, 현재 상태, 변경 시 영향, 초보자 권장값과 주의사항을 "
                "구분해서 알려줘. API 키나 비밀값은 표시하지 말고, 설정을 직접 변경하지도 마."
            )

            if hasattr(dashboard, "tab_widget") and dashboard.tab_widget:
                dashboard.tab_widget.set("AI 어시스턴트")

            # 모달 설정 창이 대시보드 조작을 막지 않도록 값은 유지한 채 잠시 숨긴다.
            try:
                self.root.grab_release()
            except Exception:
                pass
            try:
                self.root.withdraw()
            except Exception:
                pass

            if not assistant.send_quick_question(prompt):
                raise RuntimeError("AI 어시스턴트 입력창이 활성 상태가 아닙니다.")
        except Exception as exc:
            messagebox.showerror(
                "AI에게 묻기",
                f"설정 도움말을 열 수 없습니다.\n\n오류: {exc}",
            )

    def _ask_save_on_close(self):
        """추가 CTkToplevel 없이 OS 표준 3상태 확인창을 사용한다.

        오류 화면의 빈 흰색 ``NoahAI 설정`` 창은 USER/Menu 자원이 부족한
        상태에서 별도 CTkToplevel의 본문 생성이 중간 실패한 결과였다.
        """
        return messagebox.askyesnocancel(
            "NoahAI 설정",
            "변경한 설정을 저장할까요?\n\n"
            "예: 저장 후 닫기\n아니오: 저장하지 않고 닫기\n취소: 계속 편집",
            parent=self.root,
        )

    @staticmethod
    def _shade_color(hex_color: str, factor: float = 0.85) -> str:
        """기본 색상에서 hover용 음영 색상을 계산한다."""
        try:
            color = (hex_color or '').lstrip('#')
            if len(color) != 6:
                return hex_color
            r = max(0, min(255, int(int(color[0:2], 16) * factor)))
            g = max(0, min(255, int(int(color[2:4], 16) * factor)))
            b = max(0, min(255, int(int(color[4:6], 16) * factor)))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color

    def _hover_from(self, color_hex: str, factor: float = 0.85) -> str:
        """버튼 hover 색상 계산 헬퍼."""
        return self._shade_color(color_hex, factor)

    def _get_python_runtime_summary(self) -> Dict[str, Any]:
        """현재 Python 런타임과 브로커별 권장 조합을 요약한다."""
        py_version = platform.python_version()
        py_bits = 64 if (8 * struct.calcsize("P")) == 64 else 32
        is_windows = sys.platform.startswith('win')
        executable = sys.executable or ""
        machine = (platform.machine() or '').lower()
        os_name = platform.system() or 'Unknown'
        os_release = platform.release() or ''
        os_version = platform.version() or ''
        os_bits = 64 if (
            bool(os.environ.get('ProgramFiles(x86)'))
            or '64' in machine
            or bool(os.environ.get('PROCESSOR_ARCHITEW6432'))
        ) else 32

        if is_windows:
            if py_bits == 32:
                recommendation = "현재 앱의 키움 OpenAPI+(ActiveX) 실연결 경로 기준으로 권장 조건(32비트 Python)을 충족합니다."
                install_hint = "현재 런타임은 키움 OpenAPI+ 기본 COM 경로와 정합합니다."
            else:
                recommendation = "현재 앱의 키움 OpenAPI+(ActiveX) 경로에서는 64비트 Python에서 바인딩 실패가 자주 발생합니다."
                install_hint = "키움 OpenAPI 경로를 계속 사용할 경우 Python 3.11.x 32비트로 재점검하세요."
        else:
            recommendation = "macOS/Linux에서는 키움 실연결이 불가하므로 현재 Python으로도 mock/REST 브로커 점검만 권장합니다."
            install_hint = "실제 키움 연결이 필요하면 Windows 환경으로 전환해야 합니다."

        broker_compatibility: List[str] = [
            "바이낸스: 지원",
            "업비트: 지원",
        ]
        if not is_windows:
            broker_compatibility.append("키움증권(OpenAPI+): Windows 전용")
        elif py_bits == 32:
            broker_compatibility.append("키움증권(OpenAPI+): 사용 가능 (32bit Python)")
        else:
            broker_compatibility.append("키움증권(OpenAPI+): 32bit Python 필요")

        return {
            "python_version": py_version,
            "python_bits": py_bits,
            "python_executable": executable,
            "is_windows": is_windows,
            "os_name": os_name,
            "os_release": os_release,
            "os_version": os_version,
            "os_machine": machine,
            "os_bits": os_bits,
            "recommendation": recommendation,
            "install_hint": install_hint,
            "broker_compatibility": broker_compatibility,
            "download_url": "https://www.python.org/downloads/windows/",
        }

    def _show_python_runtime_help_dialog(self):
        """Python 버전/비트수 권장 조합을 사용자에게 안내한다."""
        summary = self._get_python_runtime_summary()
        compatibility_text = "\n".join(f"- {line}" for line in summary.get('broker_compatibility', []))
        os_line = f"{summary.get('os_name', 'Unknown')} {summary.get('os_release', '')}".strip()
        messagebox.showinfo(
            "Python 런타임 안내",
            (
                f"현재 OS: {os_line} ({summary.get('os_bits', '?')}bit)\n"
                f"현재 Python: {summary['python_version']} ({summary['python_bits']}bit)\n"
                f"실행 파일: {summary['python_executable'] or '알 수 없음'}\n\n"
                f"브로커 호환성:\n{compatibility_text}\n\n"
                f"권장 안내:\n{summary['recommendation']}\n\n"
                f"설치/전환 힌트:\n{summary['install_hint']}\n\n"
                "설치 페이지는 버튼으로 바로 열 수 있습니다."
            ),
        )

    def _open_python_download_page(self):
        """Python 공식 다운로드 페이지를 연다."""
        try:
            webbrowser.open("https://www.python.org/downloads/windows/")
        except Exception:
            pass

    def _open_ai_api_architecture_guide(self):
        """OpenAI/호환 API 사용자 안내를 앱 내부 팝업으로 표시한다."""
        try:
            messagebox.showinfo(
                "OpenAI/호환 API 사용자 안내",
                (
                    "이 안내는 aitrading.exe 사용자 기준입니다.\n"
                    "개발 문서를 열지 않아도 앱 안에서 그대로 따라 할 수 있습니다.\n\n"
                    "1) OpenAI 공식 API 사용(기본)\n"
                    "- OpenAI API Key만 입력\n"
                    "- Base URL은 비워둠\n\n"
                    "2) OpenAI 호환 API 사용(선택)\n"
                    "- 예: DeepSeek / OpenRouter / 로컬 Ollama\n"
                    "- API Key + Base URL을 함께 입력\n\n"
                    "Base URL 예시\n"
                    "- DeepSeek: https://api.deepseek.com\n"
                    "- OpenRouter: https://openrouter.ai/api/v1\n"
                    "- Ollama(local): http://localhost:11434/v1\n\n"
                    "초보자 권장\n"
                    "- 모델: 계정에서 확인된 OpenAI 권장 모델\n"
                    "- Billing 한도: Hard 10~20달러 / Soft 5달러\n"
                    "- 키 이름(Name): NoahAI-Desktop\n\n"
                    "참고\n"
                    "- 'AI 설정 도우미 시작'은 키 발급 기능이 아니라\n"
                    "  키 입력 후 모델/적용값 최적화를 도와주는 기능입니다."
                ),
            )
        except Exception:
            pass

    @staticmethod
    def _normalize_version_text(version_text: str) -> tuple:
        """v3.8.9.24 같은 문자열을 비교 가능한 튜플로 변환한다."""
        if not version_text:
            return tuple()
        cleaned = str(version_text).strip().lower().lstrip('v')
        nums = re.findall(r'\d+', cleaned)
        return tuple(int(x) for x in nums)

    def _get_current_release_version(self) -> str:
        """앱의 현재 배포 버전을 반환한다."""
        try:
            from config.app_version import RELEASE_VERSION
            return str(RELEASE_VERSION).strip()
        except Exception:
            return "0.0.0"

    def _fetch_latest_release_from_github(self) -> Optional[Dict[str, str]]:
        """설정된 GitHub 저장소 목록에서 최신 릴리즈를 조회한다."""
        headers = {
            "User-Agent": "NoahAI-Client-UpdateCheck/1.0",
            "Accept": "application/vnd.github+json",
        }

        for repo in self._UPDATE_REPOSITORIES:
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            req = urllib_request.Request(url, headers=headers)
            try:
                with urllib_request.urlopen(req, timeout=8) as resp:
                    body = resp.read().decode('utf-8', errors='ignore')
                payload = json.loads(body)
                tag_name = str(payload.get('tag_name') or '').strip()
                html_url = str(payload.get('html_url') or '').strip()
                published_at = str(payload.get('published_at') or '').strip()
                if not tag_name:
                    continue
                return {
                    "repo": repo,
                    "latest_version": tag_name,
                    "release_url": html_url,
                    "published_at": published_at,
                }
            except urllib_error.HTTPError:
                continue
            except urllib_error.URLError:
                continue
            except Exception:
                continue

        return None

    def _check_github_client_update(self):
        """GitHub 릴리즈 기준으로 최신 버전을 확인하고 결과를 표시한다."""
        main_app = self.main_app
        auto_manager = getattr(main_app, 'auto_update_manager', None) if main_app is not None else None

        if auto_manager is not None:
            try:
                if hasattr(auto_manager, 'set_progress_callback'):
                    auto_manager.set_progress_callback(self._handle_auto_update_progress)

                # 설정창에서 즉시 변경한 자동업데이트 옵션을 반영해 체크한다.
                ui_settings = dict(self.current_settings.get('ui_settings', {}) or {})
                ui_settings.update(self._collect_auto_update_ui_settings())
                self.current_settings['ui_settings'] = ui_settings
                auto_manager.update_settings(self.current_settings)
                self._refresh_update_runtime_diagnostics_label()

                if hasattr(self, 'update_status_label') and self.update_status_label is not None:
                    self.update_status_label.configure(
                        text="업데이트 확인/다운로드 시작...",
                        text_color="#60a5fa",
                    )

                result = auto_manager.check_for_updates(manual=True)
                if not result.get('ok'):
                    reason = str(result.get("reason") or "latest_release_unavailable")
                    reason_text = self._auto_update_reason_text(reason)
                    if hasattr(self, 'update_status_label') and self.update_status_label is not None:
                        self.update_status_label.configure(
                            text=f"업데이트 확인 실패: {reason_text}",
                            text_color="#f59e0b",
                        )
                    messagebox.showwarning(
                        "업데이트 확인",
                        f"{reason_text}\n\n오류 코드: {reason}",
                    )
                    return

                self.latest_release_url = str(result.get('release_url', '') or '')
                latest_version = str(result.get('latest_version', '') or '')
                current_version = str(result.get('current_version', self._get_current_release_version()) or '')
                update_available = bool(result.get('update_available', False))
                downloaded = bool(result.get('downloaded', False))

                if update_available:
                    color = "#60a5fa"
                    suffix = " (다운로드 완료)" if downloaded else ""
                    download_error = str(result.get("download_error") or "")
                    status_text = f"새 버전 발견: {latest_version} (현재 v{current_version}){suffix}"
                    if download_error:
                        status_text += f" · {self._auto_update_reason_text(download_error)}"
                    if hasattr(self, 'update_status_label') and self.update_status_label is not None:
                        self.update_status_label.configure(text=status_text, text_color=color)

                    diagnostics = auto_manager.get_runtime_diagnostics() if hasattr(auto_manager, 'get_runtime_diagnostics') else {}
                    asset_path = str((auto_manager.pending_update or {}).get('asset_path', '') or '-')
                    messagebox.showinfo(
                        "업데이트 확인",
                        (
                            f"새 버전이 있습니다.\n\n"
                            f"- 현재 버전: v{current_version}\n"
                            f"- 최신 버전: {latest_version}\n"
                            f"- 다운로드 상태: {'완료' if downloaded else '미완료'}\n\n"
                            f"- 다운로드 파일: {asset_path}\n"
                            f"- 적용 대상 EXE: {diagnostics.get('install_target_exe', '-')}\n"
                            f"- 업데이트 캐시: {diagnostics.get('update_cache_dir', '-')}\n\n"
                            "다운로드 완료 시 '지금 업데이트 적용(재시작)' 버튼으로 즉시 반영할 수 있습니다."
                        ),
                    )
                    return

                if hasattr(self, 'update_status_label') and self.update_status_label is not None:
                    self.update_status_label.configure(
                        text=f"최신 상태입니다. (현재 v{current_version}, 원격 {latest_version})",
                        text_color="#22c55e",
                    )
                messagebox.showinfo(
                    "업데이트 확인",
                    f"현재 최신 버전을 사용 중입니다.\n\n- 현재 버전: v{current_version}\n- 원격 버전: {latest_version}",
                )
                return
            except Exception:
                # 매니저 경로에서 예외가 나면 기존 로직으로 폴백
                pass
            finally:
                try:
                    if hasattr(auto_manager, 'set_progress_callback'):
                        auto_manager.set_progress_callback(None)
                except Exception:
                    pass

        self._refresh_update_runtime_diagnostics_label()

        current_version = self._get_current_release_version()
        latest_info = self._fetch_latest_release_from_github()

        if not latest_info:
            if hasattr(self, 'update_status_label') and self.update_status_label is not None:
                self.update_status_label.configure(
                    text="업데이트 확인 실패: GitHub 릴리즈 정보를 가져오지 못했습니다.",
                    text_color="#f59e0b",
                )
            messagebox.showwarning(
                "업데이트 확인",
                "GitHub 릴리즈 정보를 가져오지 못했습니다.\n네트워크 상태 또는 저장소 경로를 확인해 주세요.",
            )
            return

        latest_version = latest_info.get("latest_version", "")
        current_tuple = self._normalize_version_text(current_version)
        latest_tuple = self._normalize_version_text(latest_version)
        update_available = bool(latest_tuple and latest_tuple > current_tuple)

        if hasattr(self, 'latest_release_url'):
            self.latest_release_url = latest_info.get("release_url", "")
        else:
            self.latest_release_url = latest_info.get("release_url", "")

        if update_available:
            status_text = (
                f"새 버전 발견: {latest_version} (현재 v{current_version}) | repo={latest_info.get('repo', '?')}"
            )
            if hasattr(self, 'update_status_label') and self.update_status_label is not None:
                self.update_status_label.configure(text=status_text, text_color="#60a5fa")
            messagebox.showinfo(
                "업데이트 확인",
                (
                    f"새 버전이 있습니다.\n\n"
                    f"- 현재 버전: v{current_version}\n"
                    f"- 최신 버전: {latest_version}\n"
                    f"- 저장소: {latest_info.get('repo', 'unknown')}\n\n"
                    "'최신 릴리즈 열기' 버튼으로 다운로드 페이지로 이동할 수 있습니다."
                ),
            )
            return

        status_text = (
            f"최신 상태입니다. (현재 v{current_version}, 원격 {latest_version})"
        )
        if hasattr(self, 'update_status_label') and self.update_status_label is not None:
            self.update_status_label.configure(text=status_text, text_color="#22c55e")
        messagebox.showinfo(
            "업데이트 확인",
            (
                f"현재 최신 버전을 사용 중입니다.\n\n"
                f"- 현재 버전: v{current_version}\n"
                f"- 원격 버전: {latest_version}\n"
                f"- 저장소: {latest_info.get('repo', 'unknown')}"
            ),
        )

    def _handle_auto_update_progress(self, payload: Dict[str, Any]):
        """자동업데이트 진행 이벤트를 설정 UI 라벨에 반영한다."""
        try:
            label = getattr(self, 'update_status_label', None)
            if label is None:
                return

            event = str(payload.get('event', '') or '').strip().lower()

            if event == 'download_start':
                file_name = str(payload.get('file_name', 'AITrading.new.exe') or 'AITrading.new.exe')
                text = f"업데이트 다운로드 시작: {file_name}"
                label.configure(text=text, text_color="#60a5fa")
                return

            if event == 'download_progress':
                percent = payload.get('percent', None)
                downloaded_bytes = int(payload.get('downloaded_bytes', 0) or 0)
                total_bytes = int(payload.get('total_bytes', 0) or 0)

                if percent is None or total_bytes <= 0:
                    mb = downloaded_bytes / (1024 * 1024)
                    text = f"업데이트 다운로드 중... {mb:.1f}MB"
                else:
                    done_mb = downloaded_bytes / (1024 * 1024)
                    total_mb = total_bytes / (1024 * 1024)
                    text = f"업데이트 다운로드 중... {percent}% ({done_mb:.1f}/{total_mb:.1f}MB)"
                label.configure(text=text, text_color="#60a5fa")
                return

            if event == 'download_completed':
                asset_path = str(payload.get('asset_path', '-') or '-')
                install_target = str(payload.get('install_target', '-') or '-')
                text = (
                    "다운로드 완료.\n"
                    f"파일: {asset_path}\n"
                    f"적용 대상: {install_target}"
                )
                label.configure(text=text, text_color="#22c55e")
                self._refresh_update_runtime_diagnostics_label()
                return

            if event == 'download_failed':
                reason = str(payload.get('reason', 'download_failed') or 'download_failed')
                label.configure(
                    text=f"업데이트 다운로드 실패: {self._auto_update_reason_text(reason)} ({reason})",
                    text_color="#f59e0b",
                )
                return
        except Exception:
            pass

    @staticmethod
    def _auto_update_reason_text(reason: str) -> str:
        return {
            "latest_release_unavailable": "GitHub 최신 릴리즈 정보를 가져오지 못했습니다.",
            "latest_version_missing": "릴리즈 버전 정보가 없습니다.",
            "release_manifest_or_sha256_missing": "검증 manifest 또는 필수 SHA-256이 없습니다.",
            "sha256_mismatch": "다운로드 파일의 SHA-256이 manifest와 다릅니다.",
            "untrusted_release_url": "GitHub HTTPS가 아닌 배포 주소라 차단했습니다.",
            "exe_asset_not_found": "릴리즈에서 Windows EXE를 찾지 못했습니다.",
            "download_failed": "파일 다운로드에 실패했습니다.",
            "stable_target_unavailable": "정상 설치 EXE 경로를 확인할 수 없습니다.",
            "shutdown_not_confirmed": "안전 종료가 확인되지 않아 적용하지 않았습니다.",
            "preflight_blocked": "열린 포지션·주문 안전 점검에서 적용이 보류됐습니다.",
            "pre_shutdown_approval_missing_or_expired": "종료 전에 받은 안전 승인이 없거나 만료되었습니다.",
            "staged_executable_missing": "다운로드한 임시 EXE를 찾을 수 없습니다.",
            "staged_sha256_invalid": "다운로드한 임시 EXE의 SHA-256 검증에 실패했습니다.",
            "install_target_is_update_cache": "업데이트 캐시를 설치 경로로 사용할 수 없습니다.",
            "install_target_missing": "교체할 설치 EXE를 찾을 수 없습니다.",
            "install_target_directory_not_writable": "설치 폴더에 쓰기 권한이 없어 자동 교체할 수 없습니다.",
            "installed_sha256_mismatch": "재시작한 EXE가 배포 SHA-256과 일치하지 않습니다.",
        }.get(str(reason or ""), str(reason or "알 수 없는 오류"))

    def _open_latest_release_page(self):
        """최근 확인된 릴리즈 페이지를 연다."""
        release_url = getattr(self, 'latest_release_url', '')
        if not release_url:
            messagebox.showinfo("릴리즈 열기", "먼저 '업데이트 확인' 버튼을 눌러 최신 릴리즈를 확인해 주세요.")
            return
        try:
            webbrowser.open(release_url)
        except Exception:
            messagebox.showwarning("릴리즈 열기", "브라우저를 열지 못했습니다. 네트워크/OS 설정을 확인해 주세요.")

    def _collect_auto_update_ui_settings(self) -> Dict[str, Any]:
        """업데이트 탭에서 변경한 자동업데이트 옵션을 수집한다."""
        values: Dict[str, Any] = {}
        try:
            values['auto_update_enabled'] = bool(self.auto_update_enabled_var.get()) if hasattr(self, 'auto_update_enabled_var') else True
            values['auto_update_auto_download'] = bool(self.auto_update_auto_download_var.get()) if hasattr(self, 'auto_update_auto_download_var') else True
            values['auto_update_auto_apply_on_exit'] = bool(self.auto_update_auto_apply_var.get()) if hasattr(self, 'auto_update_auto_apply_var') else True
            action_label = (
                self.auto_update_position_action_combo.get()
                if hasattr(self, "auto_update_position_action_combo")
                else "업데이트 연기(권장)"
            )
            values["auto_update_open_position_action"] = {
                "업데이트 연기(권장)": "defer",
                "포지션 유지(TP/SL 확인)": "keep_with_tp_sl",
                "전량 청산(체결 확인)": "close_all",
            }.get(action_label, "defer")
            if hasattr(self, 'auto_update_interval_entry'):
                interval_text = str(self.auto_update_interval_entry.get() or '').strip()
                interval_value = int(interval_text) if interval_text else 6
            else:
                interval_value = 6
            values['auto_update_check_interval_hours'] = max(1, min(interval_value, 72))
        except Exception:
            values['auto_update_enabled'] = True
            values['auto_update_auto_download'] = True
            values['auto_update_auto_apply_on_exit'] = True
            values['auto_update_check_interval_hours'] = 6
            values["auto_update_open_position_action"] = "defer"
        return values

    def _refresh_update_runtime_diagnostics_label(self):
        """업데이트 적용 대상/캐시 경로를 UI에 표시한다."""
        label = getattr(self, 'update_runtime_path_label', None)
        if label is None:
            return

        main_app = self.main_app
        auto_manager = getattr(main_app, 'auto_update_manager', None) if main_app is not None else None
        if auto_manager is None or not hasattr(auto_manager, 'get_runtime_diagnostics'):
            try:
                label.configure(
                    text="업데이트 런타임 정보: 업데이트 매니저를 초기화하지 못했습니다.",
                    text_color="#f59e0b",
                )
            except Exception:
                pass
            return

        try:
            info = auto_manager.get_runtime_diagnostics()
            installed_sha = str(info.get('installed_sha256') or '')
            expected_sha = str(info.get('expected_sha256') or '')
            phase = str(info.get('transaction_phase') or 'none')
            error = str(info.get('transaction_error') or '')
            text = (
                f"적용 대상 EXE: {info.get('install_target_exe', '-') }\n"
                f"현재 실행 EXE: {info.get('current_exe', '-') }\n"
                f"업데이트 캐시: {info.get('update_cache_dir', '-') }\n"
                f"적용 단계: {phase}"
                f"{' · ' + self._auto_update_reason_text(error) if error else ''}\n"
                f"현재 SHA: {installed_sha[:12] or '-'} · 배포 SHA: {expected_sha[:12] or '-'}"
            )
            sha_matches = bool(installed_sha and expected_sha and installed_sha == expected_sha)
            label.configure(
                text=text,
                text_color="#22c55e" if sha_matches else ("#f59e0b" if expected_sha else "#94a3b8"),
            )
        except Exception:
            try:
                label.configure(
                    text="업데이트 런타임 정보: 경로 진단 중 오류가 발생했습니다.",
                    text_color="#f59e0b",
                )
            except Exception:
                pass

    def _apply_downloaded_update_now(self):
        """다운로드된 업데이트가 있으면 즉시 적용을 예약하고 앱 종료를 유도한다."""
        main_app = self.main_app
        auto_manager = getattr(main_app, 'auto_update_manager', None) if main_app is not None else None
        if auto_manager is None:
            messagebox.showwarning("업데이트", "메인 앱 업데이트 매니저를 찾을 수 없습니다.")
            return

        ui_settings = dict(self.current_settings.get('ui_settings', {}) or {})
        ui_settings.update(self._collect_auto_update_ui_settings())
        self.current_settings['ui_settings'] = ui_settings
        auto_manager.update_settings(self.current_settings)

        if not auto_manager.has_pending_update():
            messagebox.showinfo("업데이트", "적용 가능한 다운로드 업데이트가 없습니다. 먼저 '업데이트 확인'을 실행해 주세요.")
            return

        preflight = auto_manager.authorize_pending_update()
        if not preflight.get("ok"):
            messagebox.showwarning(
                "업데이트 연기",
                "현재 실거래 상태에서는 안전하게 업데이트할 수 없어 적용을 연기했습니다.\n\n"
                f"사유: {preflight.get('reason', 'trading_state_unsafe')}\n"
                "포지션·미체결 주문을 확인하거나 업데이트 안전 정책을 변경해 주세요.",
            )
            return

        if not messagebox.askyesno(
            "업데이트 적용",
            "거래 상태 사전점검을 통과했습니다.\n안전 종료와 DB flush 후 업데이트를 적용하고 재시작할까요?",
        ):
            return
        try:
            if main_app is not None and hasattr(main_app, 'dashboard') and main_app.dashboard:
                main_app.dashboard.on_closing()
                return
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _run_kiwoom_runtime_diagnosis(self) -> Dict[str, Any]:
        """키움 OpenAPI+ 런타임을 즉시 진단한다. (Windows 전용)"""
        result: Dict[str, Any] = {
            "ok": False,
            "error": "",
            "details": {},
        }

        if not sys.platform.startswith('win'):
            result["error"] = "non_windows"
            return result

        try:
            import struct
            py_bits = 64 if (8 * struct.calcsize("P")) == 64 else 32
            result["details"]["python_bits"] = py_bits

            try:
                from PyQt5.QtWidgets import QApplication  # type: ignore
                from PyQt5.QAxContainer import QAxWidget  # type: ignore
            except Exception as exc:
                result["error"] = f"pyqt_import_failed:{exc}"
                return result

            try:
                app = QApplication.instance() or QApplication(sys.argv)
                _ = app
                probe = QAxWidget()
                control_ok = bool(probe.setControl("KHOPENAPI.KHOpenAPICtrl.1"))
                has_event = hasattr(probe, "OnReceiveTrData")

                result["details"]["setControl"] = control_ok
                result["details"]["has_OnReceiveTrData"] = has_event

                if control_ok and has_event:
                    result["ok"] = True
                else:
                    result["error"] = f"activex_binding_failed:control={control_ok},event={has_event}"
            except Exception as exc:
                result["error"] = f"qax_runtime_failed:{exc}"
        except Exception as exc:
            result["error"] = f"diagnosis_exception:{exc}"

        return result

    def _get_stock_broker_quick_diagnosis_text(self) -> str:
        """현재 입력값 기준으로 증권사 연결 1차 점검 요약을 생성한다."""
        lines = []

        is_windows = sys.platform.startswith('win')
        lines.append(f"- 실행 OS: {'Windows' if is_windows else 'Non-Windows'}")

        selected_brokers = []
        if hasattr(self, 'stock_broker_vars') and isinstance(self.stock_broker_vars, dict):
            for broker_key, broker_var in self.stock_broker_vars.items():
                try:
                    if bool(broker_var.get()):
                        selected_brokers.append(str(broker_key))
                except Exception:
                    continue

        if not selected_brokers:
            lines.append("- 선택 증권사: 없음 (키움/신한/미래에셋/한국투자증권 중 최소 1개 선택 필요)")
        else:
            lines.append(f"- 선택 증권사: {', '.join(selected_brokers)}")
            lines.append("- 안내: '지원'은 NoahAI 앱의 연동 경로 지원을 의미합니다. 실제 연결 가능 여부는 증권사 OpenAPI 권한(개인/법인/제휴 정책)에 따라 달라질 수 있습니다.")

        kiwoom_api_type = 'openapi_plus'
        if hasattr(self, 'kiwoom_api_type_combo') and self.kiwoom_api_type_combo is not None:
            try:
                kiwoom_api_type = str(self.kiwoom_api_type_combo.get()).strip().lower()
            except Exception:
                pass

        kiwoom_api_version = 'pykiwoom'
        if hasattr(self, 'kiwoom_api_version_combo') and self.kiwoom_api_version_combo is not None:
            try:
                kiwoom_api_version = str(self.kiwoom_api_version_combo.get()).strip()
            except Exception:
                pass

        shinhan_api_type = 'partner_rest'
        if hasattr(self, 'shinhan_api_type_combo') and self.shinhan_api_type_combo is not None:
            try:
                shinhan_api_type = str(self.shinhan_api_type_combo.get()).strip().lower()
            except Exception:
                pass

        shinhan_api_version = 'shinhan_openapi_v2'
        if hasattr(self, 'shinhan_api_version_combo') and self.shinhan_api_version_combo is not None:
            try:
                shinhan_api_version = str(self.shinhan_api_version_combo.get()).strip()
            except Exception:
                pass

        mirae_asset_api_type = 'partner_rest'
        if hasattr(self, 'mirae_asset_api_type_combo') and self.mirae_asset_api_type_combo is not None:
            try:
                mirae_asset_api_type = str(self.mirae_asset_api_type_combo.get()).strip().lower()
            except Exception:
                pass

        mirae_asset_api_version = 'mirae_partner_profile'
        if hasattr(self, 'mirae_asset_api_version_combo') and self.mirae_asset_api_version_combo is not None:
            try:
                mirae_asset_api_version = str(self.mirae_asset_api_version_combo.get()).strip()
            except Exception:
                pass

        korea_investment_api_type = 'rest'
        if hasattr(self, 'korea_investment_api_type_combo') and self.korea_investment_api_type_combo is not None:
            try:
                korea_investment_api_type = str(self.korea_investment_api_type_combo.get()).strip().lower()
            except Exception:
                pass

        korea_investment_api_version = 'kis_openapi_v1'
        if hasattr(self, 'korea_investment_api_version_combo') and self.korea_investment_api_version_combo is not None:
            try:
                korea_investment_api_version = str(self.korea_investment_api_version_combo.get()).strip()
            except Exception:
                pass

        if 'kiwoom' in selected_brokers:
            lines.append(f"- 키움 API 타입/버전: {kiwoom_api_type} / {kiwoom_api_version}")
        if 'shinhan' in selected_brokers:
            lines.append(f"- 신한 API 타입/버전: {shinhan_api_type} / {shinhan_api_version}")
        if 'miraeAsset' in selected_brokers:
            lines.append(f"- 미래에셋 API 타입/버전: {mirae_asset_api_type} / {mirae_asset_api_version}")
        if 'koreaInvestment' in selected_brokers:
            lines.append(f"- 한국투자증권 API 타입/버전: {korea_investment_api_type} / {korea_investment_api_version}")

        if 'kiwoom' in selected_brokers and kiwoom_api_type != 'mock' and not is_windows:
            lines.append("[Mac/Linux에서 키움 실연결 불가]")
            lines.append("- 키움 OpenAPI+는 Windows 전용 기술(COM/ActiveX)입니다.")
            lines.append("- Mac/Linux에서는 mock 모드로만 테스트 가능합니다.")
            lines.append("- 실거래가 필요하면 Windows PC에서 실행하거나 신한/미래에셋(REST API) 사용")

        shinhan_key = ''
        if hasattr(self, 'shinhan_id_entry') and self.shinhan_id_entry is not None:
            try:
                shinhan_key = str(self.shinhan_id_entry.get()).strip()
            except Exception:
                shinhan_key = ''

        shinhan_secret = ''
        if hasattr(self, 'shinhan_password_entry') and self.shinhan_password_entry is not None:
            try:
                shinhan_secret = str(self.shinhan_password_entry.get()).strip()
            except Exception:
                shinhan_secret = ''

        if 'shinhan' in selected_brokers and shinhan_api_type != 'mock' and (not shinhan_key or not shinhan_secret):
            lines.append("- 점검: 신한 app_key/app_secret(또는 대응 계정값) 누락 가능성이 있습니다.")

        mirae_asset_key = ''
        if hasattr(self, 'mirae_asset_id_entry') and self.mirae_asset_id_entry is not None:
            try:
                mirae_asset_key = str(self.mirae_asset_id_entry.get()).strip()
            except Exception:
                mirae_asset_key = ''

        mirae_asset_secret = ''
        if hasattr(self, 'mirae_asset_password_entry') and self.mirae_asset_password_entry is not None:
            try:
                mirae_asset_secret = str(self.mirae_asset_password_entry.get()).strip()
            except Exception:
                mirae_asset_secret = ''

        korea_investment_key = ''
        if hasattr(self, 'korea_investment_id_entry') and self.korea_investment_id_entry is not None:
            try:
                korea_investment_key = str(self.korea_investment_id_entry.get()).strip()
            except Exception:
                korea_investment_key = ''

        korea_investment_secret = ''
        if hasattr(self, 'korea_investment_password_entry') and self.korea_investment_password_entry is not None:
            try:
                korea_investment_secret = str(self.korea_investment_password_entry.get()).strip()
            except Exception:
                korea_investment_secret = ''

        # 키움 런타임 진단 (Windows 전용, 실연결 경우에만)
        if 'kiwoom' in selected_brokers and kiwoom_api_type != 'mock' and is_windows:
            runtime_diag = self._run_kiwoom_runtime_diagnosis()
            if runtime_diag.get("ok"):
                lines.append("- 키움 런타임: ActiveX 로딩/이벤트 바인딩 정상")
            else:
                error = runtime_diag.get("error", "unknown")
                details = runtime_diag.get("details", {})
                py_bits = details.get("python_bits", "?")
                lines.append(f"- 키움 런타임: 실패 (원인: {error})")
                if "activex_binding_failed" in str(error):
                    lines.append(f"  → OpenAPI+ OCX 로딩 실패. python_bits={py_bits}bit")
                    lines.append("  → 조치: OpenAPI+ 관리자 재설치 + KOA Studio 단독 로그인 성공 후 재시도")
                elif "pyqt_import_failed" in str(error):
                    lines.append("  → PyQt5 라이브러리 누락. pip install PyQt5 후 재시도")

        if 'miraeAsset' in selected_brokers and mirae_asset_api_type != 'mock' and (not mirae_asset_key or not mirae_asset_secret):
            lines.append("- 점검: 미래에셋 app_key/app_secret(또는 대응 계정값) 누락 가능성이 있습니다.")

        if 'koreaInvestment' in selected_brokers and korea_investment_api_type != 'mock' and (not korea_investment_key or not korea_investment_secret):
            lines.append("- 점검: 한국투자증권 app_key/app_secret(또는 대응 계정값) 누락 가능성이 있습니다.")

        runtime_issues = self._collect_stock_broker_runtime_issues_from_logs(selected_brokers)
        for issue in runtime_issues:
            lines.append(f"- 점검: {issue}")

        if selected_brokers and not runtime_issues and all('점검:' not in line for line in lines):
            lines.append("- 상태: 현재 입력값 기준 즉시 확인 가능한 치명 이슈는 보이지 않습니다.")
        elif runtime_issues:
            lines.append("- 상태: 최근 실행 로그 기준 즉시 조치가 필요한 연결 실패가 확인되었습니다.")

        lines.append("- 다음 단계: 상세 체크리스트 문서를 열어 5분 점검 순서를 진행하세요.")
        return "\n".join(lines)

    def _collect_stock_broker_runtime_issues_from_logs(self, selected_brokers: List[str]) -> List[str]:
        """최근 실행 로그를 기반으로 즉시 조치가 필요한 런타임 실패를 추출한다."""
        if not selected_brokers:
            return []

        try:
            recent_log_lines = self._get_recent_stock_broker_log_lines(limit=80)
        except Exception:
            return []

        joined_text = '\n'.join(recent_log_lines).lower()
        issues: List[str] = []

        if 'kiwoom' in selected_brokers:
            activex_fail = ('khopenapi activex 로딩 실패' in joined_text) or ('activex_control_probe_failed' in joined_text)
            if activex_fail:
                issues.append('키움 OpenAPI ActiveX 로딩 실패가 반복되었습니다(setControl=False/OnReceiveTrData=False). 입력값 문제가 아니라 PC 런타임(OCX 등록/설치/비트수) 이슈 가능성이 큽니다.')
                if 'python_bits=64' in joined_text:
                    issues.append('실패 로그에 python_bits=64가 확인되었습니다. 키움 OpenAPI+는 32비트 런타임 의존 이슈가 잦으므로 Windows 32비트 Python + OpenAPI+ 설치 조합에서 KOA Studio 연결 성공을 먼저 확인하세요.')

            if '키움증권 미연결' in joined_text:
                issues.append('키움 미연결 상태가 지속되어 주식/ETF 조회가 모두 차단되고 있습니다.')

        deduped: List[str] = []
        for issue in issues:
            if issue not in deduped:
                deduped.append(issue)
        return deduped[:3]

    @staticmethod
    def _has_stock_broker_quick_issue(quick_diagnosis_text: str) -> bool:
        """1차 진단 결과에 즉시 조치가 필요한 이슈가 포함됐는지 판별한다."""
        if not quick_diagnosis_text:
            return False
        return ('- 점검:' in quick_diagnosis_text) or ('선택 증권사: 없음' in quick_diagnosis_text)

    def _should_auto_show_stock_broker_diagnosis_after_save(self) -> bool:
        """저장 후 증권사 자동 점검 팝업 노출 여부를 반환한다."""
        try:
            if hasattr(self, 'auto_stock_broker_diagnosis_var') and self.auto_stock_broker_diagnosis_var is not None:
                return bool(self.auto_stock_broker_diagnosis_var.get())
        except Exception:
            pass
        return bool(self.current_settings.get('ui_settings', {}).get('auto_show_stock_broker_diagnosis_after_save', True))

    def _maybe_show_post_save_stock_broker_diagnosis(self):
        """저장 직후 필요한 경우 증권사 1차 진단을 안내한다. (비동기 실행으로 UI 블로킹 방지)"""
        try:
            if hasattr(self.root, 'after'):
                self.root.after(100, self._show_post_save_diagnosis_async)
        except Exception as e:
            print(f"저장 후 증권사 점검 안내 스케줄 실패: {e}")

    def _show_post_save_diagnosis_async(self):
        """저장 후 증권사 진단을 실제로 표시 (비동기)"""
        try:
            if not self._should_auto_show_stock_broker_diagnosis_after_save():
                return

            quick_diagnosis_text = self._get_stock_broker_quick_diagnosis_text()
            if not self._has_stock_broker_quick_issue(quick_diagnosis_text):
                return

            self._show_stock_broker_guided_checklist(
                title="저장 후 증권 연결 점검",
                quick_diagnosis_text=quick_diagnosis_text,
            )
        except Exception as e:
            print(f"저장 후 증권사 점검 안내 실패: {e}")

    def _on_click_stock_broker_connection_checklist(self):
        """증권사 연결 1차 진단 결과와 다음 조치를 앱 안에서 안내한다."""
        try:
            quick_diagnosis_text = self._get_stock_broker_quick_diagnosis_text()
            self._show_stock_broker_guided_checklist(
                title="증권 연결 점검",
                quick_diagnosis_text=quick_diagnosis_text,
            )
        except Exception as e:
            messagebox.showerror("연결 진단 실패", f"진단 안내를 표시하지 못했습니다:\n{e}")

    def _open_stock_broker_connection_checklist(self):
        """하위 호환: 점검 호출을 앱 내부 안내로 연결한다."""
        self._show_stock_broker_guided_checklist(
            title="증권 연결 점검",
            quick_diagnosis_text=self._get_stock_broker_quick_diagnosis_text(),
        )

    def _show_stock_broker_guided_checklist(self, title: str, quick_diagnosis_text: str):
        """증권 연결 점검 결과를 앱 안에서 사람이 읽기 쉬운 안내로 보여준다."""
        try:
            broker_names = []
            if hasattr(self, 'stock_broker_vars') and isinstance(self.stock_broker_vars, dict):
                for broker_key, broker_var in self.stock_broker_vars.items():
                    try:
                        if bool(broker_var.get()):
                            broker_names.append(str(broker_key))
                    except Exception:
                        continue

            broker_display_map = {
                'kiwoom': '키움증권',
                'shinhan': '신한증권',
                'miraeAsset': '미래에셋증권',
                'koreaInvestment': '한국투자증권',
            }
            broker_display = ', '.join(str(broker_display_map.get(name, name) or name) for name in broker_names) if broker_names else '선택 없음'
            os_display = 'Windows' if sys.platform.startswith('win') else 'macOS/Linux'

            actions: List[str] = []
            if not broker_names:
                actions.append('설정에서 사용할 증권사를 최소 1개 선택하세요.')
            if 'kiwoom' in broker_names:
                kiwoom_type = str(self.kiwoom_api_type_combo.get()).strip().lower() if hasattr(self, 'kiwoom_api_type_combo') else 'openapi_plus'
                if not sys.platform.startswith('win') and kiwoom_type != 'mock':
                    actions.append('키움 실연결은 Windows 전용입니다. 현재 환경에서는 mock으로 먼저 테스트하거나 Windows에서 실행하세요.')
                else:
                    actions.append('키움은 OpenAPI+ 설치와 KOA Studio 로그인 성공 여부를 먼저 확인하세요.')
            if 'shinhan' in broker_names:
                shinhan_id = str(self.shinhan_id_entry.get()).strip() if hasattr(self, 'shinhan_id_entry') else ''
                shinhan_pw = str(self.shinhan_password_entry.get()).strip() if hasattr(self, 'shinhan_password_entry') else ''
                if not shinhan_id or not shinhan_pw:
                    actions.append('신한증권은 ID/비밀번호를 먼저 입력하고 저장하세요. 현재 빌드에서는 이 값이 app_key/app_secret 대응값으로도 반영됩니다.')
            if 'miraeAsset' in broker_names:
                mirae_id = str(self.mirae_asset_id_entry.get()).strip() if hasattr(self, 'mirae_asset_id_entry') else ''
                mirae_pw = str(self.mirae_asset_password_entry.get()).strip() if hasattr(self, 'mirae_asset_password_entry') else ''
                if not mirae_id or not mirae_pw:
                    actions.append('미래에셋은 ID/비밀번호를 먼저 입력하고 저장하세요. 현재 빌드에서는 이 값이 app_key/app_secret 대응값으로도 반영됩니다.')
            if 'koreaInvestment' in broker_names:
                kis_id = str(self.korea_investment_id_entry.get()).strip() if hasattr(self, 'korea_investment_id_entry') else ''
                kis_pw = str(self.korea_investment_password_entry.get()).strip() if hasattr(self, 'korea_investment_password_entry') else ''
                if not kis_id or not kis_pw:
                    actions.append('한국투자증권은 앱 키/시크릿(또는 대응 ID/비밀번호)을 입력하고 저장하세요.')
            if not actions:
                actions.append('현재 입력값 기준 치명적인 누락은 보이지 않습니다. 저장 후 연결 상태와 조회 로그를 확인하세요.')

            support_report = self._build_stock_broker_support_report(quick_diagnosis_text)
            structured_checklist = self._build_stock_broker_user_checklist(
                broker_names=broker_names,
                os_display=os_display,
            )
            quick_3min_check = self._build_stock_broker_3min_checklist_text(
                broker_names=broker_names,
                os_display=os_display,
                quick_diagnosis_text=quick_diagnosis_text,
            )
            user_notice_text = self._build_stock_broker_user_notice_text(
                broker_names=broker_names,
                os_display=os_display,
                quick_diagnosis_text=quick_diagnosis_text,
            )

            guide_text = (
                '증권 연결 점검 결과\n\n'
                f'현재 OS: {os_display}\n'
                f'선택 증권사: {broker_display}\n\n'
                '앱이 지금 확인한 요약\n'
                f'{quick_diagnosis_text}\n\n'
                '지금 이 화면에서 먼저 할 일\n'
                + '\n'.join(f'{idx}. {item}' for idx, item in enumerate(actions, start=1))
                + '\n\n'
                + structured_checklist
                + '\n\n권장 순서\n'
                '1. mock 또는 기본 권장값으로 먼저 저장\n'
                '2. 저장 직후 다시 점검\n'
                '3. 조회가 정상일 때만 실주문 허용을 켜기\n'
                '4. 가드레일은 기본값 또는 더 보수적으로 유지\n\n'
                '중요\n'
                '- 이 안내는 사용자가 이해하기 쉬운 실행 안내입니다.\n'
                '- 기술지원용 마크다운 원문을 읽지 않아도 이 화면만으로 다음 행동을 알 수 있게 구성했습니다.\n'
                '- 아래 "지원요약 복사"를 누르면 현재 설정/환경/오류 후보가 복사되어 개발팀·서비스사 전달이 빨라집니다.'
            )

            dialog = ctk.CTkToplevel(self.root)
            dialog.title(title)
            dialog.geometry('760x640')
            dialog.transient(self.root)
            dialog.grab_set()

            frame = ctk.CTkFrame(dialog)
            frame.pack(fill='both', expand=True, padx=16, pady=16)

            ctk.CTkLabel(
                frame,
                text=title,
                font=ctk.CTkFont(family='Segoe UI', size=20, weight='bold'),
                text_color=self._color('text_primary', '#f9fafb')
            ).pack(anchor='w', padx=16, pady=(16, 8))

            ctk.CTkLabel(
                frame,
                text='개발자 문서를 여는 대신, 현재 설정을 기준으로 바로 필요한 조치만 안내합니다.',
                font=ctk.CTkFont(family='Segoe UI', size=12),
                text_color=self._color('text_secondary', '#9ca3af'),
                justify='left'
            ).pack(anchor='w', padx=16, pady=(0, 10))

            text_box = ctk.CTkTextbox(frame, font=ctk.CTkFont(family='Segoe UI', size=12), wrap='word')
            text_box.pack(fill='both', expand=True, padx=16, pady=(0, 12))
            text_box.insert('1.0', guide_text)
            text_box.configure(state='disabled')

            button_row = ctk.CTkFrame(frame, fg_color='transparent')
            button_row.pack(fill='x', padx=16, pady=(0, 12))

            ctk.CTkButton(
                button_row,
                text='지원요약 복사',
                width=130,
                fg_color=self._color('primary', '#2563eb'),
                hover_color='#1d4ed8',
                command=lambda: self._copy_text_to_clipboard(
                    support_report,
                    '증권 연결 지원요약이 클립보드에 복사되었습니다. 그대로 전달하면 원인 파악이 빨라집니다.'
                ),
            ).pack(side='left')

            ctk.CTkButton(
                button_row,
                text='파일로 저장',
                width=120,
                fg_color=self._color('secondary', '#334155'),
                hover_color=self._hover_from(self._color('secondary', '#334155')),
                command=lambda: self._save_text_to_file(
                    support_report,
                    default_name=f'stock_broker_support_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
                ),
            ).pack(side='left', padx=(8, 0))

            ctk.CTkButton(
                button_row,
                text='3분 점검본 저장',
                width=140,
                fg_color='#0f766e',
                hover_color='#115e59',
                command=lambda: self._save_text_to_file(
                    quick_3min_check,
                    default_name=f'stock_broker_3min_checklist_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
                ),
            ).pack(side='left', padx=(8, 0))

            ctk.CTkButton(
                button_row,
                text='사용자 안내문 저장',
                width=150,
                fg_color='#4338ca',
                hover_color='#3730a3',
                command=lambda: self._save_text_to_file(
                    user_notice_text,
                    default_name=f'stock_broker_user_notice_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
                ),
            ).pack(side='left', padx=(8, 0))

            ctk.CTkButton(
                button_row,
                text='사용자 안내문 복사',
                width=150,
                fg_color='#7c3aed',
                hover_color='#6d28d9',
                command=lambda: self._copy_text_to_clipboard(
                    user_notice_text,
                    '사용자 전달용 안내문이 복사되었습니다. 공지/메신저에 바로 붙여넣어 전달하세요.'
                ),
            ).pack(side='left', padx=(8, 0))

            ctk.CTkButton(
                button_row,
                text='닫기',
                width=100,
                command=dialog.destroy,
            ).pack(side='right')
        except Exception as e:
            messagebox.showerror("점검 안내 실패", f"증권 연결 점검 안내를 표시하지 못했습니다:\n{e}")

    def _build_stock_broker_3min_checklist_text(self, broker_names: List[str], os_display: str, quick_diagnosis_text: str) -> str:
        """사용자가 고객지원/개발 전달 전에 3분 내 실행 가능한 점검본을 생성한다."""
        runtime = self._get_python_runtime_summary()
        action_steps = self._build_stock_broker_action_steps(
            broker_names=broker_names,
            quick_diagnosis_text=quick_diagnosis_text,
        )
        lines: List[str] = []
        lines.append('[NoahAI 증권 연결 3분 점검본]')
        lines.append(f'- 생성 시각: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        lines.append(f'- 실행 OS: {os_display}')
        lines.append(f'- 선택 브로커: {", ".join(broker_names) if broker_names else "(none)"}')
        lines.append(f"- 현재 Python: {runtime.get('python_version', '?')} ({runtime.get('python_bits', '?')}bit)")
        lines.append('')
        lines.append('[1분] 설정 저장값 확인')
        lines.append('- enabled_stock_brokers에 대상 브로커가 포함됐는지 확인')
        lines.append('- stock_broker_configs.[broker].api_type/api_version 확인')
        lines.append('- 계정 ID/비밀번호/계좌번호 저장값이 비어있지 않은지 확인')
        lines.append('')
        lines.append('[1분] 연결 경로 확인')
        lines.append('- 앱에서 "증권 연결 점검" 실행')
        lines.append('- 최근 로그에서 "연결 성공" 또는 "연결 불가/실패" 문구 확인')
        lines.append('- mock만 성공하고 openapi만 실패하는지 여부 확인')
        lines.append('')
        lines.append('[1분] 브로커별 필수조건 확인')
        if 'kiwoom' in broker_names:
            lines.append('- 키움: Windows + OpenAPI+ + KOA Studio 로그인 성공 여부 확인')
        if 'shinhan' in broker_names:
            lines.append('- 신한: app_key/app_secret(or id/password) + account_no 저장 확인')
        if 'miraeAsset' in broker_names:
            lines.append('- 미래에셋: app_key/app_secret(or id/password) + account_no 저장 확인')
        if 'koreaInvestment' in broker_names:
            lines.append('- 한국투자증권: app_key/app_secret(or id/password) + account_no 저장 확인')
        if not broker_names:
            lines.append('- 최소 1개 브로커를 먼저 선택')
        lines.append('')
        lines.append('[현재 앱 진단 요약]')
        lines.append(quick_diagnosis_text.strip() or '- (진단 요약 없음)')
        lines.append('')
        lines.append('[즉시 조치 순서(자동 생성)]')
        for index, step in enumerate(action_steps, start=1):
            lines.append(f'{index}. {step}')
        lines.append(f"- Python 다운로드(Windows): {runtime.get('download_url', 'https://www.python.org/downloads/windows/')}")
        lines.append('- 키움 OpenAPI+ 다운로드/설치 안내: https://www1.kiwoom.com')
        lines.append('')
        lines.append('[개발팀 전달용 체크]')
        lines.append('- 이 파일 + 지원요약(stock_broker_support_report) + 시도 시각 전달')
        lines.append('- 연결 시도 직후 생성본으로 재전달')
        return '\n'.join(lines)

    def _build_stock_broker_user_notice_text(self, broker_names: List[str], os_display: str, quick_diagnosis_text: str) -> str:
        """사용자 공지/메신저 전달용 요약 안내문을 생성한다."""
        runtime_issues = self._collect_stock_broker_runtime_issues_from_logs(broker_names)
        has_activex_issue = any('activex' in str(issue).lower() or 'ocx' in str(issue).lower() for issue in runtime_issues)
        runtime = self._get_python_runtime_summary()
        action_steps = self._build_stock_broker_action_steps(
            broker_names=broker_names,
            quick_diagnosis_text=quick_diagnosis_text,
        )

        lines: List[str] = []
        lines.append('[NoahAI 증권 연결 사용자 안내]')
        lines.append(f'- 생성 시각: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        lines.append(f'- 실행 OS: {os_display}')
        lines.append(f'- 대상 브로커: {", ".join(broker_names) if broker_names else "(none)"}')
        lines.append('')

        if has_activex_issue and 'kiwoom' in broker_names:
            lines.append('- 현재 로그 기준으로 키움 입력값 문제가 아니라 ActiveX 런타임 실패가 반복되고 있습니다.')
            lines.append('- 조치 순서: OpenAPI+ 관리자 재설치 → KOA Studio 단독 로그인 성공 확인 → 비트수 정합 확인')
            lines.append('- 이후 앱에서 `증권 연결 점검` 실행 후 `지원요약`/`3분 점검본`을 다시 생성해 전달해 주세요.')
        else:
            lines.append('- 현재 로그와 설정 기준 점검 결과를 먼저 확인해 주세요.')
            lines.append('- 앱에서 `증권 연결 점검` 실행 후 안내된 순서대로 점검해 주세요.')

        lines.append('')
        lines.append('[앱 내 위치]')
        lines.append('1) 설정(거래소 API) → 증권 연결 점검')
        lines.append('2) 지원요약 복사 또는 파일로 저장')
        lines.append('3) 3분 점검본 저장')
        lines.append('')
        lines.append('[즉시 조치 순서]')
        for index, step in enumerate(action_steps, start=1):
            lines.append(f'{index}. {step}')
        lines.append(f"- 현재 Python: {runtime.get('python_version', '?')} ({runtime.get('python_bits', '?')}bit)")
        lines.append(f"- Python 다운로드(Windows): {runtime.get('download_url', 'https://www.python.org/downloads/windows/')}")
        lines.append('- 키움 OpenAPI+ 다운로드/설치 안내: https://www1.kiwoom.com')
        lines.append('')
        lines.append('[중요 안내]')
        lines.append('- NoahAI에서 "지원"은 앱 연동 경로가 구현되어 있다는 의미입니다.')
        lines.append('- 실제 실연결 가능 여부는 증권사 OpenAPI 정책(개인/법인/제휴 계정 권한)에 따라 달라질 수 있습니다.')
        lines.append('')
        lines.append('[현재 진단 요약]')
        lines.append(quick_diagnosis_text.strip() or '- (진단 요약 없음)')

        return '\n'.join(lines)

    def _copy_text_to_clipboard(self, text: str, success_message: str):
        """텍스트를 클립보드에 복사하고 결과를 알린다."""
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
            messagebox.showinfo('복사 완료', success_message)
        except Exception as e:
            messagebox.showerror('복사 실패', f'클립보드 복사에 실패했습니다:\n{e}')

    def _save_text_to_file(self, text: str, default_name: str):
        """텍스트를 사용자가 선택한 파일로 저장한다."""
        try:
            file_path = filedialog.asksaveasfilename(
                parent=self.root,
                title='지원요약 저장',
                defaultextension='.txt',
                initialfile=default_name,
                filetypes=[('텍스트 파일', '*.txt'), ('모든 파일', '*.*')],
            )
            if not file_path:
                return
            with open(file_path, 'w', encoding='utf-8') as file_handle:
                file_handle.write(text)
            messagebox.showinfo('저장 완료', f'지원요약을 저장했습니다.\n\n{file_path}')
        except Exception as e:
            messagebox.showerror('저장 실패', f'지원요약 저장에 실패했습니다:\n{e}')

    def _build_stock_broker_user_checklist(self, broker_names: List[str], os_display: str) -> str:
        """사용자가 이해하기 쉬운 증권 연결 체크리스트를 생성한다."""
        sections: List[str] = []
        sections.append('왜 코인과 다른가')
        sections.append('- 코인은 API Key/Secret 중심이라 비교적 단순합니다.')
        sections.append('- 증권사는 브로커별 인증, OS 제약, 전용 런타임, 주문 보호정책이 함께 걸립니다.')
        sections.append('- 그래서 설정만 맞는다고 바로 되는 구조가 아니라, 브로커 환경 조건도 함께 맞아야 합니다.')
        sections.append('')
        sections.append('공통 사전 점검')
        sections.append('- 설정 저장 후 다시 점검하세요.')
        sections.append('- 증권사 OpenAPI 신청/승인(계정 권한)이 완료된 계정인지 먼저 확인하세요.')
        sections.append('- 방화벽/백신이 앱 네트워크를 막지 않는지 확인하세요.')
        sections.append('- 현재 앱이 보는 OS: ' + os_display)

        if 'kiwoom' in broker_names:
            sections.append('')
            sections.append('키움증권 점검')
            sections.append('- 필수 조건: Windows 실행, OpenAPI+ 설치, KOA Studio 로그인 가능')
            sections.append('- 권장값: api_type=openapi_plus, api_version=pykiwoom')
            sections.append('- 실패 시: mock 성공 + openapi 실패면 설치/비트수/OCX 문제 가능성이 큽니다.')

        if 'shinhan' in broker_names:
            sections.append('')
            sections.append('신한증권 점검')
            sections.append('- 핵심 포인트: 토큰 발급에 app_key/app_secret이 필요합니다.')
            sections.append('- 중요: NoahAI는 신한 연동을 지원하지만, 계정의 OpenAPI 권한이 개인계정에 열려 있는지는 신한 정책/신청 상태에 따라 달라질 수 있습니다.')
            sections.append('- 현재 빌드는 입력한 ID/비밀번호를 app_key/app_secret 대응값으로도 동기화 저장합니다.')
            sections.append('- 권장값: api_type=partner_rest, api_version=shinhan_openapi_v2')
            sections.append('- 연결 전 확인: 증권사 고객센터/개발자 포털에서 내 계정이 API 사용 승인 상태인지 확인하세요.')

        if 'miraeAsset' in broker_names:
            sections.append('')
            sections.append('미래에셋증권 점검')
            sections.append('- 핵심 포인트: 인증 정보 저장값과 API 타입/버전 조합이 맞아야 합니다.')
            sections.append('- 중요: NoahAI는 미래에셋 연동을 지원하지만, OpenAPI 접근 권한은 계정 유형/신청 상태에 따라 제한될 수 있습니다.')
            sections.append('- 권장값: api_type=partner_rest, api_version=mirae_partner_profile')
            sections.append('- 연결 전 확인: 개인계정 API 사용 가능 여부와 발급된 app_key/app_secret 상태를 먼저 확인하세요.')

        if 'koreaInvestment' in broker_names:
            sections.append('')
            sections.append('한국투자증권 점검')
            sections.append('- 핵심 포인트: KIS 앱키/시크릿과 계좌번호가 저장되어야 인증/조회가 가능합니다.')
            sections.append('- 권장값: api_type=rest, api_version=kis_openapi_v1')
            sections.append('- 연결 전 확인: KIS Developers 앱 등록, 계정 API 권한 승인, 모의/실전 도메인 구분')

        sections.append('')
        sections.append('성공 기준')
        sections.append('- 연결 성공 로그가 보입니다.')
        sections.append('- 계좌 또는 잔고 조회가 최소 1회 성공합니다.')
        sections.append('- 실주문 허용 OFF 상태에서 조회 경로부터 먼저 검증합니다.')

        sections.append('')
        sections.append('그래도 실패하면')
        sections.append('- 아래 지원요약 복사 또는 파일 저장으로 현재 상태를 그대로 전달하세요.')
        sections.append('- 전달 내용: 앱 버전, 사용 브로커, api_type/api_version, 마스킹된 설정값, 최근 관련 로그')
        sections.append('- 증권사/거래소 확장 정책 안내 문구는 docs/BROKER_EXPANSION_ROADMAP.md를 기준으로 통일하세요.')
        return '\n'.join(sections)

    def _build_stock_broker_support_report(self, quick_diagnosis_text: str) -> str:
        """개발팀/서비스사 전달용 증권 연결 지원요약을 생성한다."""
        runtime = self._get_python_runtime_summary()
        action_steps = self._build_stock_broker_action_steps(
            broker_names=self._get_selected_stock_brokers(),
            quick_diagnosis_text=quick_diagnosis_text,
        )
        version_text = 'unknown'
        try:
            from config.app_version import RELEASE_VERSION
            version_text = str(RELEASE_VERSION)
        except Exception:
            pass

        broker_lines = self._collect_stock_broker_config_lines()
        recent_log_lines = self._get_recent_stock_broker_log_lines(limit=40)
        issue_candidates = self._infer_stock_broker_issue_candidates(recent_log_lines)
        dev_handoff_summary = self._build_stock_broker_dev_handoff_summary(
            quick_diagnosis_text=quick_diagnosis_text,
            issue_candidates=issue_candidates,
            recent_log_lines=recent_log_lines,
        )

        report_parts = [
            '[NoahAI 증권 연결 지원요약]',
            f'- 앱 버전: v{version_text}',
            f'- 실행 OS: {sys.platform}',
            '- 개발자 전달 핵심요약:',
            dev_handoff_summary,
            '',
            '- 현재 진단 요약:',
            quick_diagnosis_text.strip(),
            '',
            '- 자동 실행 가이드(현장 전달용):',
            '\n'.join(f'  {index}. {item}' for index, item in enumerate(action_steps, start=1)),
            f"  - 현재 Python: {runtime.get('python_version', '?')} ({runtime.get('python_bits', '?')}bit)",
            f"  - Python 다운로드(Windows): {runtime.get('download_url', 'https://www.python.org/downloads/windows/')}",
            '  - 키움 OpenAPI+ 다운로드/설치 안내: https://www1.kiwoom.com',
            '',
            '- 브로커 설정 요약:',
            '\n'.join(broker_lines) if broker_lines else '선택된 증권사 설정 없음',
            '',
            '- AI/규칙 기반 원인 후보:',
            '\n'.join(f'  {index}. {item}' for index, item in enumerate(issue_candidates, start=1)) if issue_candidates else '  1. 최근 로그에서 명확한 오류 후보를 찾지 못했습니다. 설정 저장 후 다시 점검이 필요합니다.',
            '',
            '- 최근 관련 로그 발췌(최대 40줄):',
            '\n'.join(recent_log_lines) if recent_log_lines else '최근 관련 로그 없음',
            '',
            '- 전달 가이드:',
            '  1. 이 요약을 그대로 개발팀/서비스사에 전달',
            '  2. 사용 브로커와 시도 시각을 함께 전달',
            '  3. 가능하면 저장 직후/연결 시도 직후 다시 복사해 최신 로그를 포함',
        ]
        return '\n'.join(report_parts)

    def _build_stock_broker_action_steps(self, broker_names: List[str], quick_diagnosis_text: str) -> List[str]:
        """진단 요약을 기반으로 사용자 전달용 즉시 조치 순서를 생성한다."""
        text = str(quick_diagnosis_text or '').lower()
        steps: List[str] = []

        if 'kiwoom' in broker_names and (
            'activex' in text
            or 'ocx' in text
            or 'binding_failed' in text
            or 'python_bits=64' in text
        ):
            steps.extend([
                'NoahAI를 종료합니다.',
                '키움 OpenAPI+를 관리자 권한으로 재설치합니다.',
                'KOA Studio를 단독 실행해 로그인 성공을 확인합니다.',
                '현재 앱의 키움 OpenAPI 경로를 사용할 경우 Windows 32bit Python 3.11.x 환경에서 NoahAI를 다시 실행합니다.',
                '설정 > 증권 연결 점검을 다시 실행하고 새 지원요약/3분 점검본을 생성해 전달합니다.',
            ])
            return steps

        if 'non-windows' in text and 'kiwoom' in broker_names:
            return [
                '키움 실연결은 Windows에서만 지원됩니다.',
                '현재 환경에서는 mock으로 점검하거나 Windows PC로 전환합니다.',
                'Windows 전환 후 증권 연결 점검을 다시 실행합니다.',
            ]

        return [
            '설정을 저장한 뒤 증권 연결 점검을 실행합니다.',
            '연결 성공/실패 로그를 확인합니다.',
            '실패 시 지원요약과 3분 점검본을 생성해 시도 시각과 함께 전달합니다.',
        ]

    def _get_selected_stock_brokers(self) -> List[str]:
        """현재 선택된 증권사 키 목록을 반환한다."""
        brokers: List[str] = []
        if not hasattr(self, 'stock_broker_vars') or not isinstance(self.stock_broker_vars, dict):
            return brokers
        for broker_key, broker_var in self.stock_broker_vars.items():
            try:
                if bool(broker_var.get()):
                    brokers.append(str(broker_key))
            except Exception:
                continue
        return brokers

    def _build_stock_broker_dev_handoff_summary(self, quick_diagnosis_text: str, issue_candidates: List[str], recent_log_lines: List[str]) -> str:
        """지원요약 상단에 넣을 개발자 전달용 핵심 문장을 생성한다."""
        summary_lines: List[str] = []
        quick_text = str(quick_diagnosis_text or '').strip()
        recent_joined = '\n'.join(recent_log_lines).lower()

        if '키움증권 연결 불가' in recent_joined:
            summary_lines.append('- 키움 연결 로직에서 OpenAPI/OCX/런타임 제약 문구가 감지되었습니다. 환경 의존 실패 가능성이 큽니다.')

        if '[kiwoom_portfolio]' in recent_joined and '(ex=binance)' in recent_joined:
            summary_lines.append('- 주식 컨텍스트 로그가 ex=binance로 찍힌 이력이 감지되었습니다(교차 태깅 이력).')

        if issue_candidates:
            summary_lines.append('- 자동 추정 원인 상위: ' + '; '.join(issue_candidates[:2]))

        if quick_text:
            summary_lines.append(f'- 진단 요약 원문: {quick_text}')

        if not summary_lines:
            summary_lines.append('- 현재 수집 로그만으로 단일 원인 확정은 어렵습니다. 연결 시도 직후 로그 재수집이 필요합니다.')

        return '\n'.join(summary_lines)

    def _collect_stock_broker_config_lines(self) -> List[str]:
        """선택된 증권사 설정을 민감정보 마스킹 상태로 요약한다."""
        lines: List[str] = []
        broker_display_map = {
            'kiwoom': '키움증권',
            'shinhan': '신한증권',
            'miraeAsset': '미래에셋증권',
            'koreaInvestment': '한국투자증권',
        }

        if not hasattr(self, 'stock_broker_vars') or not isinstance(self.stock_broker_vars, dict):
            return lines

        for broker_key, broker_var in self.stock_broker_vars.items():
            try:
                if not bool(broker_var.get()):
                    continue
            except Exception:
                continue

            broker_label = broker_display_map.get(str(broker_key), str(broker_key))
            config = self.current_settings.get('stock_broker_configs', {}).get(str(broker_key), {}) or {}

            api_type_attr = (
                'mirae_asset_api_type_combo' if broker_key == 'miraeAsset'
                else 'korea_investment_api_type_combo' if broker_key == 'koreaInvestment'
                else f'{broker_key}_api_type_combo'
            )
            api_type = self._safe_combo_value(api_type_attr, default=str(config.get('api_type', 'openapi_plus') or 'openapi_plus'))
            api_version_attr = (
                'mirae_asset_api_version_combo' if broker_key == 'miraeAsset'
                else 'korea_investment_api_version_combo' if broker_key == 'koreaInvestment'
                else f'{broker_key}_api_version_combo'
            )
            api_version = self._safe_combo_value(api_version_attr, default=str(config.get('api_version', '') or ''))

            if broker_key == 'kiwoom':
                login_id = self._safe_entry_value('kiwoom_id_entry')
                password = self._safe_entry_value('kiwoom_password_entry')
                account_number = self._safe_entry_value('kiwoom_account_entry')
            elif broker_key == 'shinhan':
                login_id = self._safe_entry_value('shinhan_id_entry')
                password = self._safe_entry_value('shinhan_password_entry')
                account_number = self._safe_entry_value('shinhan_account_entry')
            elif broker_key == 'koreaInvestment':
                login_id = self._safe_entry_value('korea_investment_id_entry')
                password = self._safe_entry_value('korea_investment_password_entry')
                account_number = self._safe_entry_value('korea_investment_account_entry')
            else:
                login_id = self._safe_entry_value('mirae_asset_id_entry')
                password = self._safe_entry_value('mirae_asset_password_entry')
                account_number = self._safe_entry_value('mirae_asset_account_entry')

            lines.append(
                f'- {broker_label}: api_type={api_type}, api_version={api_version}, '
                f'id={self._mask_sensitive(login_id)}, pw={self._mask_sensitive(password)}, account={self._mask_sensitive(account_number)}'
            )
        return lines

    def _safe_combo_value(self, attr_name: str, default: str = '') -> str:
        """콤보박스 값을 안전하게 읽는다."""
        combo = getattr(self, attr_name, None)
        try:
            if combo is not None:
                return str(combo.get()).strip()
        except Exception:
            pass
        return default

    def _safe_entry_value(self, attr_name: str) -> str:
        """입력값을 안전하게 읽는다."""
        entry = getattr(self, attr_name, None)
        try:
            if entry is not None:
                return str(entry.get()).strip()
        except Exception:
            pass
        return ''

    def _mask_sensitive(self, value: str) -> str:
        """민감값을 짧게 마스킹한다."""
        text = str(value or '').strip()
        if not text:
            return '(empty)'
        if len(text) <= 4:
            return '*' * len(text)
        return f'{text[:2]}***{text[-2:]} (len={len(text)})'

    def _get_recent_stock_broker_log_lines(self, limit: int = 40) -> List[str]:
        """최근 증권 연결 관련 로그를 수집한다."""
        try:
            from path_utils import get_log_dir
            log_dir = Path(get_log_dir())
        except Exception:
            return []

        if not log_dir.exists():
            return []

        keywords = [
            'kiwoom', 'shinhan', 'mirae', 'miraeasset', 'korea', 'koreainvestment', 'kis', '한국투자', '증권', 'broker', 'openapi',
            'solapi', 'miraemts', 'token', 'app_key', 'app_secret', 'qaxwidget',
            'ocx', 'koa', '로그인', '연결 실패', '인증', 'error', 'fail',
        ]
        candidate_paths = sorted(log_dir.glob('trading*.log'))
        matched_lines: List[str] = []

        for log_path in candidate_paths:
            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as file_handle:
                    file_lines = file_handle.readlines()
                for raw_line in reversed(file_lines[-400:]):
                    line = raw_line.strip()
                    line_lower = line.lower()
                    if any(keyword in line_lower for keyword in keywords):
                        matched_lines.append(f'[{log_path.name}] {line}')
                        if len(matched_lines) >= limit:
                            return list(reversed(matched_lines))
            except Exception:
                continue

        return list(reversed(matched_lines))

    def _infer_stock_broker_issue_candidates(self, log_lines: List[str]) -> List[str]:
        """최근 로그에서 증권 연결 이슈 후보를 추정한다."""
        joined_text = '\n'.join(log_lines).lower()
        issues: List[str] = []

        pattern_map = [
            (('qaxwidget', 'ocx', 'koa'), '키움 OpenAPI+/OCX/KOA 환경 문제 가능성이 큽니다. Windows 환경, OpenAPI+ 설치, KOA Studio 로그인 성공 여부를 우선 확인하세요.'),
            (('32-bit', '64-bit', 'bit mismatch', '비트'), '키움 실행 환경의 32/64비트 불일치 가능성이 있습니다. Python/브로커 런타임 비트수를 맞춰야 합니다.'),
            (('app_key', 'app_secret', 'token', '토큰'), '브로커 인증키 또는 토큰 발급 단계 실패 가능성이 있습니다. ID/비밀번호 또는 app_key/app_secret 저장값을 재확인하세요.'),
            (('timeout', 'timed out', '시간 초과'), '브로커 응답 지연 또는 네트워크 시간 초과 가능성이 있습니다. 재시도 전 네트워크/방화벽 상태를 확인하세요.'),
            (('unauthorized', 'forbidden', '401', '403', '인증 실패'), '인증 실패 가능성이 있습니다. 계정 정보 또는 API 권한 상태를 확인하세요.'),
            (('mock',), 'mock에서는 되지만 실연결에서만 실패하는 패턴인지 확인하세요. 이 경우 환경/브로커 런타임 제약일 가능성이 큽니다.'),
            (('[kiwoom_portfolio]', 'ex=binance', 'stock_trade_summary'), '주식 XAI 저장 로그에 ex=binance 교차 태깅 이력이 있습니다. recorder exchange 동기화 경로 점검이 필요합니다.'),
        ]

        for keywords, message in pattern_map:
            if any(keyword in joined_text for keyword in keywords):
                issues.append(message)

        if 'kiwoom' in joined_text and not sys.platform.startswith('win'):
            issues.append('현재 OS에서는 키움 실연결이 불가할 수 있습니다. macOS/Linux라면 mock 또는 Windows 환경 점검이 우선입니다.')

        deduped: List[str] = []
        for issue in issues:
            if issue not in deduped:
                deduped.append(issue)
        return deduped

    def _resolve_stock_broker_checklist_path(self) -> Optional[str]:
        """실행 환경(소스/패키징)에 따라 증권사 점검 문서의 실제 경로를 탐색한다."""
        candidate_paths: List[str] = []

        # 소스 실행 기준: <project_root>/docs/...
        project_root = os.path.dirname(os.path.dirname(__file__))
        candidate_paths.append(os.path.join(project_root, self._STOCK_BROKER_CHECKLIST_RELATIVE_PATH))

        # 현재 작업 디렉터리 기준
        candidate_paths.append(os.path.join(os.getcwd(), self._STOCK_BROKER_CHECKLIST_RELATIVE_PATH))

        # 패키징 실행 기준: 실행 파일 위치 주변
        executable_dir = os.path.dirname(sys.executable)
        candidate_paths.append(os.path.join(executable_dir, self._STOCK_BROKER_CHECKLIST_RELATIVE_PATH))
        candidate_paths.append(os.path.join(executable_dir, '_internal', self._STOCK_BROKER_CHECKLIST_RELATIVE_PATH))
        candidate_paths.append(os.path.join(executable_dir, 'resources', self._STOCK_BROKER_CHECKLIST_RELATIVE_PATH))

        for path in candidate_paths:
            try:
                if path and os.path.exists(path):
                    return path
            except Exception:
                continue

        return None

    def _normalize_ai_diagnosis_result(self, payload: Any) -> Dict[str, Any]:
        """대시보드 전달 포맷(dict/tuple) 차이를 흡수해 UI 표준 포맷으로 맞춘다."""
        if isinstance(payload, dict):
            normalized = dict(payload)
            normalized.setdefault('status', 'caution')
            normalized.setdefault('summary', 'AI 진단 결과가 전달되었습니다.')
            normalized.setdefault('issues', [])
            if not isinstance(normalized.get('issues'), list):
                normalized['issues'] = [str(normalized.get('issues'))]
            return normalized

        # 하위 호환: (action, title, lines) 튜플 포맷 지원
        if isinstance(payload, tuple) and len(payload) == 3:
            action, title, lines = payload
            lines_list = list(lines or [])
            warning_keywords = ('미준비', '확인 필요', '오류', '시간 초과', '없어', '없습니다')
            issues = []
            for line in lines_list:
                text = str(line).strip()
                if text.startswith('- '):
                    text = text[2:]
                if any(keyword in text for keyword in warning_keywords):
                    issues.append(text)
            status = 'ready' if not issues else 'caution'
            return {
                'status': status,
                'summary': f"{title} 결과입니다. 필요한 항목을 확인한 뒤 진행하세요.",
                'issues': issues,
                'action': action,
                'title': title,
                'plan_lines': lines_list,
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }

        return {}

    def _toggle_ai_diagnosis_panel(self):
        """AI 진단 상세 패널 접기/펼치기"""
        try:
            if self._ai_diagnosis_body_frame is None:
                return
            self._ai_diagnosis_collapsed = not self._ai_diagnosis_collapsed
            if self._ai_diagnosis_collapsed:
                self._ai_diagnosis_body_frame.pack_forget()
                if hasattr(self, '_ai_diagnosis_toggle_btn'):
                    self._ai_diagnosis_toggle_btn.configure(text='상세 보기')
            else:
                self._ai_diagnosis_body_frame.pack(fill='x', padx=15, pady=(0, 12))
                if hasattr(self, '_ai_diagnosis_toggle_btn'):
                    self._ai_diagnosis_toggle_btn.configure(text='접기')
        except Exception:
            pass

    def _create_ai_diagnosis_panel(self, parent):
        """AI 실행 준비도 진단 패널 생성"""
        diagnosis_frame = ctk.CTkFrame(parent, fg_color="#1a2540", corner_radius=8)
        diagnosis_frame.pack(fill="x", pady=(0, 15))

        # 진단 헤더
        header_frame = ctk.CTkFrame(diagnosis_frame, fg_color="#1a2540")
        header_frame.pack(fill="x", padx=15, pady=(12, 8))

        status = str(self.ai_diagnosis_result.get('status', 'caution'))
        status_color_map = {
            'ready': '#10b981',
            'caution': '#f59e0b',
            'not_ready': '#ef4444',
        }
        status_icon_map = {
            'ready': '',
            'caution': '',
            'not_ready': '',
        }
        status_color = status_color_map.get(status, '#f59e0b')
        status_icon = status_icon_map.get(status, '')
        
        header_label = ctk.CTkLabel(
            header_frame,
            text=f"{status_icon} AI 실행 준비도 진단",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=status_color
        )
        header_label.pack(side='left', fill='x', expand=True)

        toggle_button = ctk.CTkButton(
            header_frame,
            text='상세 보기' if self._ai_diagnosis_collapsed else '접기',
            command=self._toggle_ai_diagnosis_panel,
            font=ctk.CTkFont(family='Segoe UI', size=11, weight='bold'),
            width=80,
            height=26,
            fg_color='#334155',
            hover_color='#475569',
        )
        toggle_button.pack(side='right')
        self._ai_diagnosis_toggle_btn = toggle_button

        body_frame = ctk.CTkFrame(diagnosis_frame, fg_color="#1a2540")
        self._ai_diagnosis_body_frame = body_frame
        if not self._ai_diagnosis_collapsed:
            body_frame.pack(fill="x", padx=15, pady=(0, 12))

        generated_at = str(self.ai_diagnosis_result.get('generated_at', '') or '').strip()
        runtime_summary = self._get_python_runtime_summary()
        runtime_os = f"{runtime_summary.get('os_name', 'Unknown')} {runtime_summary.get('os_release', '')}".strip()
        runtime_text = (
            f"실행 환경: {runtime_os} ({runtime_summary.get('os_bits', '?')}bit)"
            f"  |  Python {runtime_summary.get('python_version', '?')} ({runtime_summary.get('python_bits', '?')}bit)"
        )

        runtime_label = ctk.CTkLabel(
            body_frame,
            text=runtime_text,
            font=ctk.CTkFont(family='Segoe UI', size=11),
            text_color='#94a3b8',
            justify='left',
        )
        runtime_label.pack(fill='x', padx=15, pady=(0, 4))

        if generated_at:
            meta_label = ctk.CTkLabel(
                body_frame,
                text=f"진단 시각(로컬): {generated_at}  |  마지막 준비도 점검 시점",
                font=ctk.CTkFont(family='Segoe UI', size=11),
                text_color='#94a3b8',
                justify='left',
            )
            meta_label.pack(fill='x', padx=15, pady=(0, 8))
        else:
            runtime_label.configure(text=f"{runtime_text}  |  진단 시각(로컬): -")

        # 진단 요약
        if 'summary' in self.ai_diagnosis_result:
            summary_label = ctk.CTkLabel(
                body_frame,
                text=self.ai_diagnosis_result['summary'],
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color="#d1d5db",
                justify="left",
                wraplength=650
            )
            summary_label.pack(fill="x", pady=(0, 8))

        # 문제점 목록
        issues = self.ai_diagnosis_result.get('issues', [])
        if not isinstance(issues, list):
            issues = [str(issues)]
        if issues:
            issues_frame = ctk.CTkFrame(body_frame, fg_color="#1a2540")
            issues_frame.pack(fill="x", pady=(0, 12))

            for issue in issues:
                issue_label = ctk.CTkLabel(
                    issues_frame,
                    text=f"• {issue}",
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color="#fca5a5",
                    justify="left",
                    wraplength=620
                )
                issue_label.pack(anchor="w", pady=2)

            # "수정하기" 버튼
            fix_button = ctk.CTkButton(
                body_frame,
                text="지금 수정하기",
                command=self._highlight_missing_settings,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                fg_color="#f97316",
                hover_color="#ea580c",
                height=32
            )
            fix_button.pack(fill="x", pady=(0, 4))

    def _highlight_missing_settings(self):
        """부족한 설정 항목으로 탭 이동 및 스크롤"""
        issues = self.ai_diagnosis_result.get('issues', [])
        if not isinstance(issues, list):
            issues = [str(issues)]
        if not issues:
            messagebox.showinfo("안내", "현재 자동으로 감지된 부족 항목이 없습니다.")
            return
            
        # 가장 첫 번째 문제 유형에 따라 해당 탭으로 이동
        first_issue = issues[0].lower()
        
        if any(x in first_issue for x in ['거래소', 'exchange']):
            # 거래소 탭으로 이동
            try:
                self.tabview.set("거래소 API 설정")
            except Exception:
                pass
        elif any(x in first_issue for x in ['증권', 'broker', 'stock']):
            # 증권사 선택 탭으로 이동
            try:
                self.tabview.set("증권사")
            except Exception:
                pass
        
        # 사용자 피드백
        messagebox.showinfo(
            "수정 안내",
            f"다음 항목을 확인/수정해주세요:\n\n" + "\n".join(issues[:3])
        )

    def _show_live_trading_readiness_dialog(self) -> None:
        """설정 중 언제든 열 수 있는 거래소·증권 실거래 필수 안내."""
        try:
            dialog = ctk.CTkToplevel(self.root)
            dialog.title(f"{RELEASE_BUILD_LABEL} 실거래 필수 안내")
            dialog.geometry("820x680")
            dialog.minsize(720, 560)
            dialog.transient(self.root)
            dialog.grab_set()

            frame = ctk.CTkFrame(
                dialog,
                fg_color="#0b1120",
                border_width=1,
                border_color="#f59e0b",
                corner_radius=14,
            )
            frame.pack(fill="both", expand=True, padx=12, pady=12)
            ctk.CTkLabel(
                frame,
                text="거래소·증권 실거래 시작 전 필수 안내",
                font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
                text_color="#fbbf24",
            ).pack(anchor="w", padx=16, pady=(14, 8))
            text_box = ctk.CTkTextbox(
                frame,
                wrap="word",
                fg_color="#101826",
                text_color="#e5edf6",
                border_width=1,
                border_color="#334155",
                corner_radius=10,
                font=ctk.CTkFont(family="Segoe UI", size=12),
            )
            text_box.pack(fill="both", expand=True, padx=16, pady=(0, 12))
            text_box.insert("1.0", build_live_trading_guide(RELEASE_BUILD_LABEL))
            text_box.configure(state="disabled")
            ctk.CTkButton(
                frame,
                text="닫기",
                width=110,
                height=36,
                command=dialog.destroy,
            ).pack(side="right", padx=16, pady=(0, 14))
        except Exception as exc:
            messagebox.showerror("실거래 필수 안내", f"안내를 열 수 없습니다.\n{exc}")

    def setup_ui(self):
        """UI 설정 (메인 컨테이너/제목/탭/하단 버튼)"""
        # 메인 컨테이너 (투명색 금지 정책: 고정 배경 적용)
        main_frame = ctk.CTkFrame(self.root, fg_color="#0b1120")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 제목
        self._title_label = ctk.CTkLabel(
            main_frame,
            text="설정",
            image=get_ui_icon("settings", (25, 25), "#60a5fa"),
            compound="left",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        self._title_label.pack(pady=(0, 20))

        ctk.CTkLabel(
            main_frame,
            text=(
                "권장 순서: ① 일반에서 운용 모드 확인 → ② 거래소 선택에서 분석 범위와 주문 권한 분리 "
                "→ ③ 필요한 연결만 설정 → ④ 고급 정책은 근거가 있을 때만 변경"
            ),
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#94a3b8"),
            justify="center",
            wraplength=1080,
        ).pack(pady=(0, 14))

        readiness_bar = ctk.CTkFrame(
            main_frame,
            fg_color="#2a1f0c",
            border_width=1,
            border_color="#f59e0b",
            corner_radius=10,
        )
        readiness_bar.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            readiness_bar,
            text=(
                f"{RELEASE_BUILD_LABEL} · LIVE는 별도 권한입니다 · "
                "PAPER OFF + 주문 대상/증권 LIVE + API 준비 + 가드레일"
            ),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#fde68a",
            justify="left",
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=12, pady=9)
        ctk.CTkButton(
            readiness_bar,
            text="실거래 필수 안내",
            width=132,
            height=30,
            fg_color="#d97706",
            hover_color="#b45309",
            command=self._show_live_trading_readiness_dialog,
        ).pack(side="right", padx=10, pady=7)
        
        # AI 진단 결과 표시 (있는 경우)
        if self.ai_diagnosis_result:
            self._create_ai_diagnosis_panel(main_frame)

        # 하단 버튼을 먼저 예약해야 큰 탭/진단 패널이 창 밖으로 밀어내지 않는다.
        self.create_button_area(main_frame)

        # 탭 뷰 생성 (고정 스킨)
        self.tabview = ctk.CTkTabview(
            main_frame,
            width=850,
            height=500
        )
        self.tabview.pack(fill="both", expand=True, pady=(0, 20))

        # 사용자 의사결정 순서로 배치한다. 탭 이름은 기존 바로가기 호환을 유지한다.
        self.create_general_tab()
        self.create_exchange_selection_tab()
        self.create_exchange_api_tab()
        self.create_openai_tab()
        self.create_advanced_layers_tab()
        self.create_alphaarena_tab()
        self.create_ai_settings_tab()
        self.create_update_info_tab()  # 자동업데이트/수동 업데이트 관리 탭 (가장 오른쪽)
        style_tabview(
            self.tabview,
            accent="#2563eb",
            bar_color="#111c2f",
            inactive="#2a3d58",
            font_size=11,
            height=34,
        )

    def create_openai_tab(self):
        """기존 OpenAI 설정과 호환되는 멀티 AI 엔진/API 탭."""
        tab = self.tabview.add("AI 엔진/API")
        self._add_tab_save_bar(tab, "4. AI 엔진 연결")

        # 스크롤 가능한 프레임
        scroll_frame = ctk.CTkScrollableFrame(tab)
        scroll_frame.pack(fill="both", expand=True, padx=14, pady=14)

        # OpenAI API 설정 그룹
        openai_group = ctk.CTkFrame(scroll_frame)
        openai_group.pack(fill="x", pady=(0, 20))

        # 그룹 제목
        openai_title = ctk.CTkLabel(
            openai_group,
            text="AI 엔진/API 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        openai_title.pack(pady=(20, 15), padx=20)

        _ai_models = list(self._AI_MODEL_FALLBACKS)

        provider_frame = ctk.CTkFrame(openai_group, fg_color="transparent")
        provider_frame.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkLabel(
            provider_frame,
            text="API 키를 설정할 엔진:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb"),
        ).pack(side="left")
        self.ai_provider_var = ctk.StringVar(value="OpenAI")
        self.ai_provider_combo = ctk.CTkComboBox(
            provider_frame,
            values=list(self._AI_PROVIDER_LABELS),
            variable=self.ai_provider_var,
            state="readonly",
            width=220,
            command=self._on_ai_provider_change,
        )
        self.ai_provider_combo.pack(side="right")

        quick_help_row = ctk.CTkFrame(openai_group, fg_color="transparent")
        quick_help_row.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkButton(
            quick_help_row,
            text="AI 설정 도우미 시작",
            width=170,
            height=32,
            fg_color=self._color("primary", "#3b82f6"),
            hover_color="#2563eb",
            command=self._launch_ai_onboarding_guide,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            quick_help_row,
            text="선택 제공사 키 발급",
            width=170,
            height=32,
            fg_color=self._color("secondary", "#4b5563"),
            hover_color=self._hover_from(self._color("secondary", "#4b5563")),
            command=self._open_selected_ai_provider_console,
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            quick_help_row,
            text="OpenAI/호환 API 사용자 안내",
            width=190,
            height=32,
            fg_color=self._color("secondary", "#334155"),
            hover_color=self._hover_from(self._color("secondary", "#334155")),
            command=self._open_ai_api_architecture_guide,
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            quick_help_row,
            text="초보자 모드(전체 3단계)",
            width=190,
            height=32,
            fg_color=self._color("secondary", "#1f2937"),
            hover_color=self._hover_from(self._color("secondary", "#1f2937")),
            command=self._show_beginner_mode_guide,
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            quick_help_row,
            text="공식 가격표 열기",
            width=180,
            height=32,
            fg_color=self._color("secondary", "#0f766e"),
            hover_color=self._hover_from(self._color("secondary", "#0f766e")),
            command=self._open_selected_ai_pricing,
        ).pack(side="left", padx=6)

        # 선택한 AI 제공사 API Key
        self.ai_api_key_label = ctk.CTkLabel(
            openai_group,
            text="OpenAI API Key:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        self.ai_api_key_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.openai_api_key_entry = ctk.CTkEntry(
            openai_group,
            placeholder_text="선택한 제공사의 API 키",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.openai_api_key_entry.pack(fill="x", padx=20, pady=(0, 15))

        # OpenAI 호환 Base URL
        openai_base_url_label = ctk.CTkLabel(
            openai_group,
            text="API Base URL:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        openai_base_url_label.pack(anchor="w", padx=20, pady=(2, 5))

        self.openai_base_url_entry = ctk.CTkEntry(
            openai_group,
            placeholder_text="제공사 선택 시 공식 주소가 자동 입력됩니다.",
            height=38,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8
        )
        self.openai_base_url_entry.pack(fill="x", padx=20, pady=(0, 12))

        openai_base_url_help = ctk.CTkLabel(
            openai_group,
            text=(
                "비워두면 OpenAI 공식 API를 사용합니다.\n"
                "DeepSeek/OpenRouter/Ollama처럼 OpenAI 호환 API를 쓰는 경우에만 입력하세요."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left",
            wraplength=660,
        )
        openai_base_url_help.pack(anchor="w", padx=20, pady=(0, 10))

        # API 키 표시 토글 (OpenAI)
        self.show_openai_api_var = ctk.BooleanVar(value=False)
        show_openai_chk = ctk.CTkCheckBox(
            openai_group,
            text="API 키 표시",
            variable=self.show_openai_api_var,
            command=lambda: self._apply_api_visibility(scope='openai'),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color=self._color("text_secondary", "#9ca3af")
        )
        show_openai_chk.pack(anchor="w", padx=20, pady=(0, 10))

        # AI 애널리스트 모델 (기존 설정 키 openai_model은 호환성 유지)
        trading_model_label = ctk.CTkLabel(
            openai_group,
            text="AI 애널리스트 모델:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        trading_model_label.pack(anchor="w", padx=20, pady=(10, 5))
        self.ai_analyst_provider_combo = ctk.CTkComboBox(
            openai_group,
            values=list(self._AI_PROVIDER_LABELS),
            state="readonly",
            height=34,
            command=lambda _value: self._on_assignment_provider_change("analyst"),
        )
        self.ai_analyst_provider_combo.set("OpenAI")
        self.ai_analyst_provider_combo.pack(fill="x", padx=20, pady=(0, 5))

        self.openai_model_combo = ctk.CTkComboBox(
            openai_group,
            values=_ai_models,
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            command=lambda _value: self._on_assignment_model_change("analyst"),
        )
        self.openai_model_combo.pack(fill="x", padx=20, pady=(0, 15))

        # AI 어시스턴트 모델
        assistant_model_label = ctk.CTkLabel(
            openai_group,
            text="AI 어시스턴트 모델:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        assistant_model_label.pack(anchor="w", padx=20, pady=(10, 5))
        self.ai_assistant_provider_combo = ctk.CTkComboBox(
            openai_group,
            values=list(self._AI_PROVIDER_LABELS),
            state="readonly",
            height=34,
            command=lambda _value: self._on_assignment_provider_change("assistant"),
        )
        self.ai_assistant_provider_combo.set("OpenAI")
        self.ai_assistant_provider_combo.pack(fill="x", padx=20, pady=(0, 5))

        self.assistant_ai_model_combo = ctk.CTkComboBox(
            openai_group,
            values=_ai_models,
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            command=lambda _value: self._on_assignment_model_change("assistant"),
        )
        self.assistant_ai_model_combo.pack(fill="x", padx=20, pady=(0, 20))

        catalog_row = ctk.CTkFrame(openai_group, fg_color="transparent")
        catalog_row.pack(fill="x", padx=20, pady=(0, 14))
        self.ai_catalog_status_label = ctk.CTkLabel(
            catalog_row,
            text="GPT-5.6 Sol/Terra/Luna 포함 · 계정별 사용 가능 모델은 API에서 확인",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
        )
        self.ai_catalog_status_label.pack(side="left")
        ctk.CTkButton(
            catalog_row,
            text="사용 가능 모델 새로고침",
            width=170,
            height=30,
            command=self._refresh_ai_model_catalog,
        ).pack(side="right")
        ctk.CTkButton(
            catalog_row,
            text="실제 API 기능 검증",
            width=150,
            height=30,
            command=self._run_ai_provider_preflight,
        ).pack(side="right", padx=(0, 6))
        self.ai_model_lifecycle_label = ctk.CTkLabel(
            openai_group,
            text="모델 상태: 권장 목록 · API 키 입력 후 계정 사용 가능 여부 확인",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left",
            wraplength=760,
        )
        self.ai_model_lifecycle_label.pack(fill="x", padx=20, pady=(0, 10))

        from trading.ai.provider_catalog import format_provider_price_guide
        self.ai_price_guide_label = ctk.CTkLabel(
            openai_group,
            text=format_provider_price_guide("openai"),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left",
            wraplength=760,
        )
        self.ai_price_guide_label.pack(fill="x", padx=20, pady=(0, 14))

        transcription_frame = ctk.CTkFrame(openai_group, fg_color=self._color("background", "#050a13"), corner_radius=10)
        transcription_frame.pack(fill="x", padx=20, pady=(0, 14))
        self.ai_custom_transcription_enabled_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            transcription_frame, text="AI 커스텀 · 무자막 YouTube 음성 전사",
            variable=self.ai_custom_transcription_enabled_var,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(12, 8))
        transcription_options = ctk.CTkFrame(transcription_frame, fg_color="transparent")
        transcription_options.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(
            transcription_options,
            text="전사 엔진 OpenAI(독립)",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        ).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(transcription_options, text="전사 모델", font=ctk.CTkFont(family="Segoe UI", size=11)).pack(side="left")
        self.ai_custom_transcription_model_combo = ctk.CTkComboBox(
            transcription_options,
            values=selectable_models("openai", capability="transcribe"),
            width=235,
            height=32,
        )
        self.ai_custom_transcription_model_combo.set("gpt-4o-mini-transcribe")
        self.ai_custom_transcription_model_combo.pack(side="left", padx=(6, 14))
        ctk.CTkLabel(transcription_options, text="최대 길이(분)", font=ctk.CTkFont(family="Segoe UI", size=11)).pack(side="left")
        self.ai_custom_transcription_minutes_combo = ctk.CTkComboBox(
            transcription_options, values=["15", "30", "45", "60"], width=75, height=32,
        )
        self.ai_custom_transcription_minutes_combo.set("45")
        self.ai_custom_transcription_minutes_combo.pack(side="left", padx=(6, 14))
        ctk.CTkLabel(transcription_options, text="최대 파일(MB)", font=ctk.CTkFont(family="Segoe UI", size=11)).pack(side="left")
        self.ai_custom_transcription_mb_combo = ctk.CTkComboBox(
            transcription_options, values=["10", "16", "24"], width=75, height=32,
        )
        self.ai_custom_transcription_mb_combo.set("24")
        self.ai_custom_transcription_mb_combo.pack(side="left", padx=6)
        ctk.CTkLabel(
            transcription_frame,
            text="자동 조절이 아닙니다. 공개 자막을 먼저 사용하고, 자막이 없을 때만 선택 모델·길이·용량 제한 안에서 전사합니다.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=self._color("text_secondary", "#9ca3af"), wraplength=650, justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 12))

        runtime_frame = ctk.CTkFrame(openai_group, fg_color=self._color("background", "#050a13"), corner_radius=10)
        runtime_frame.pack(fill="x", padx=20, pady=(0, 14))
        self.ai_custom_runtime_enabled_var = ctk.BooleanVar(value=False)
        self.ai_custom_limited_live_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(
            runtime_frame, text="AI 커스텀 전략을 실제 자동매매 엔진에서 사용",
            variable=self.ai_custom_runtime_enabled_var,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(12, 6))
        ctk.CTkSwitch(
            runtime_frame, text="자동검증 미통과 전략의 1배·최대 1% 제한운용 선택 허용",
            variable=self.ai_custom_limited_live_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
        ).pack(anchor="w", padx=14, pady=(0, 6))
        ctk.CTkLabel(
            runtime_frame,
            text="안전 기본값은 두 항목 모두 OFF입니다. OFF이면 저장된 전략은 유지되지만 주문 판단에서 제외됩니다. ON이어도 최종 적용한 전략만 실행되며 모든 공통 가드레일이 우선합니다.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=self._color("text_secondary", "#9ca3af"), wraplength=650, justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 12))

        feature_frame = ctk.CTkFrame(openai_group, fg_color=self._color("background", "#050a13"), corner_radius=10)
        feature_frame.pack(fill="x", padx=20, pady=(0, 14))
        profile_row = ctk.CTkFrame(feature_frame, fg_color="transparent")
        profile_row.pack(fill="x", padx=14, pady=(12, 8))
        ctk.CTkLabel(
            profile_row, text="AI 커스텀 사용 난이도", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).pack(side="left")
        self.ai_custom_feature_profile_combo = ctk.CTkComboBox(
            profile_row, values=["초보자", "일반", "고급", "실험실"], state="readonly", width=120, height=30,
            command=self._on_ai_custom_feature_profile_changed,
        )
        self.ai_custom_feature_profile_combo.set("일반")
        self.ai_custom_feature_profile_combo.pack(side="left", padx=10)
        ctk.CTkLabel(
            profile_row,
            text="처음에는 일반(권장) · 프로필은 화면 복잡도만 바꿉니다",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=self._color("text_secondary", "#9ca3af"),
        ).pack(side="left", padx=(2, 0))
        self.ai_custom_profile_help_label = ctk.CTkLabel(
            feature_frame,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#cbd5e1",
            justify="left",
            wraplength=700,
        )
        self.ai_custom_profile_help_label.pack(fill="x", padx=14, pady=(0, 8))

        advanced_toggle_row = ctk.CTkFrame(feature_frame, fg_color="transparent")
        advanced_toggle_row.pack(fill="x", padx=14, pady=(0, 8))
        self._ai_custom_advanced_features_visible = False
        self.ai_custom_advanced_toggle_button = ctk.CTkButton(
            advanced_toggle_row,
            text="개별 고급 기능 펼치기",
            width=170,
            height=30,
            fg_color="#334155",
            hover_color="#475569",
            command=self._toggle_ai_custom_advanced_features,
        )
        self.ai_custom_advanced_toggle_button.pack(side="left")
        ctk.CTkLabel(
            advanced_toggle_row,
            text="모르면 펼치지 않아도 됩니다. 선택한 프로필이 안전한 시작값을 자동 적용합니다.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=self._color("text_secondary", "#9ca3af"),
        ).pack(side="left", padx=10)
        self.ai_custom_feature_vars = {}
        self.ai_custom_feature_switches = {}
        feature_labels = {
            "replay_analytics": "과거 재생 요약(PnL·MDD)",
            "monthly_yearly_table": "월별·연별 수익률 표",
            "expression_graph": "Expression Graph 편집기",
            "user_indicator_language": "제한형 사용자 지표 언어",
            "strategy_package": ".noahstrategy 내보내기·가져오기",
            "team_sharing": "팀 공유 권한 메타데이터",
            "quality_report": "과최적화·PAPER 품질 리포트",
            "signed_webhook": "외부 TradingView 신호 검증(실험실 전용)",
            "b2b_audit": "B2B 감사 번들",
        }
        feature_grid = ctk.CTkFrame(feature_frame, fg_color="transparent")
        feature_grid.pack(fill="x", padx=14, pady=(0, 8))
        for index, (key, label) in enumerate(feature_labels.items()):
            variable = ctk.BooleanVar(value=False)
            self.ai_custom_feature_vars[key] = variable
            switch = ctk.CTkSwitch(
                feature_grid, text=label, variable=variable,
                font=ctk.CTkFont(family="Segoe UI", size=11),
            )
            switch.grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 18), pady=3)
            self.ai_custom_feature_switches[key] = switch
        self.ai_custom_feature_grid = feature_grid
        feature_grid.pack_forget()
        ctk.CTkLabel(
            feature_frame,
            text=(
                "웹훅은 지정 거래소 연결 방식이 아닙니다. TradingView 같은 외부 서비스의 알림을 NoahAI 전략 후보로 받는 "
                "실험실 입력 통로이며, 앱이 직접 전략을 계산하면 필요하지 않습니다. 운영 endpoint와 실제 E2E 전에는 사용하지 마세요.\n"
                "백테스트는 최소 필터이고 PAPER가 필수입니다. 유료 마켓은 결제·법무 준비 전 항상 잠깁니다."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=self._color("text_secondary", "#9ca3af"), wraplength=700, justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 12))
        self._on_ai_custom_feature_profile_changed("일반")

        # ── AI 모델 비용 티어 배치 ──────────────────────────────────────────
        tier_title_label = ctk.CTkLabel(
            openai_group,
            text="작업별 모델 배치 (선택 · 비용 최적화):",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        tier_title_label.pack(anchor="w", padx=20, pady=(6, 2))

        tier_desc_label = ctk.CTkLabel(
            openai_group,
            text="위 기본 모델과 겹치는 설정이 아니라, 특정 작업을 저비용·표준·정밀 모델로 보내는 선택형 배치입니다.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            wraplength=660,
            justify="left"
        )
        tier_desc_label.pack(anchor="w", padx=20, pady=(0, 8))

        _tier_models = list(_ai_models)

        tier_cheap_label = ctk.CTkLabel(
            openai_group,
            text="빈번 호출 (저비용 모델):",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self._color("text_secondary", "#9ca3af")
        )
        tier_cheap_label.pack(anchor="w", padx=20, pady=(0, 3))
        self.ai_role_cheap_provider_combo = ctk.CTkComboBox(
            openai_group,
            values=list(self._AI_PROVIDER_LABELS),
            state="readonly",
            height=32,
            command=lambda _value: self._on_assignment_provider_change("frequent_cheap"),
        )
        self.ai_role_cheap_provider_combo.set("OpenAI")
        self.ai_role_cheap_provider_combo.pack(fill="x", padx=20, pady=(0, 4))
        self.ai_role_cheap_combo = ctk.CTkComboBox(
            openai_group,
            values=_tier_models,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            command=lambda _value: self._on_assignment_model_change("frequent_cheap"),
        )
        self.ai_role_cheap_combo.set("gpt-5.6-luna")
        self.ai_role_cheap_combo.pack(fill="x", padx=20, pady=(0, 8))

        tier_standard_label = ctk.CTkLabel(
            openai_group,
            text="표준 분석 (표준비용 모델):",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self._color("text_secondary", "#9ca3af")
        )
        tier_standard_label.pack(anchor="w", padx=20, pady=(0, 3))
        self.ai_role_standard_provider_combo = ctk.CTkComboBox(
            openai_group,
            values=list(self._AI_PROVIDER_LABELS),
            state="readonly",
            height=32,
            command=lambda _value: self._on_assignment_provider_change("standard"),
        )
        self.ai_role_standard_provider_combo.set("OpenAI")
        self.ai_role_standard_provider_combo.pack(fill="x", padx=20, pady=(0, 4))
        self.ai_role_standard_combo = ctk.CTkComboBox(
            openai_group,
            values=_tier_models,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            command=lambda _value: self._on_assignment_model_change("standard"),
        )
        self.ai_role_standard_combo.set("gpt-5.6-terra")
        self.ai_role_standard_combo.pack(fill="x", padx=20, pady=(0, 8))

        tier_premium_label = ctk.CTkLabel(
            openai_group,
            text="정밀 진단·최적화 (고성능 모델):",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self._color("text_secondary", "#9ca3af")
        )
        tier_premium_label.pack(anchor="w", padx=20, pady=(0, 3))
        self.ai_role_premium_provider_combo = ctk.CTkComboBox(
            openai_group,
            values=list(self._AI_PROVIDER_LABELS),
            state="readonly",
            height=32,
            command=lambda _value: self._on_assignment_provider_change("premium"),
        )
        self.ai_role_premium_provider_combo.set("OpenAI")
        self.ai_role_premium_provider_combo.pack(fill="x", padx=20, pady=(0, 4))
        self.ai_role_premium_combo = ctk.CTkComboBox(
            openai_group,
            values=_tier_models,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            command=lambda _value: self._on_assignment_model_change("premium"),
        )
        self.ai_role_premium_combo.set("gpt-5.6-terra")
        self.ai_role_premium_combo.pack(fill="x", padx=20, pady=(0, 16))

        preset_title_label = ctk.CTkLabel(
            openai_group,
            text="원클릭 모델 프리셋:",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self._color("text_secondary", "#9ca3af")
        )
        preset_title_label.pack(anchor="w", padx=20, pady=(0, 4))

        preset_help_label = ctk.CTkLabel(
            openai_group,
            text=(
                "절약형: 비용 우선(빈번 호출 최소화) / 균형형: 기본 권장 / 정밀형: 진단 품질 우선\n"
                "프리셋 클릭 후 저장 전까지는 실제 반영되지 않습니다."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left",
            wraplength=660
        )
        preset_help_label.pack(anchor="w", padx=20, pady=(0, 8))

        preset_button_frame = ctk.CTkFrame(openai_group, fg_color="transparent")
        preset_button_frame.pack(fill="x", padx=20, pady=(0, 12))

        preset_save_btn = ctk.CTkButton(
            preset_button_frame,
            text="절약형",
            width=110,
            height=32,
            fg_color=self._color("secondary", "#4b5563"),
            hover_color=self._hover_from(self._color("secondary", "#4b5563")),
            command=lambda: self._apply_ai_model_preset("cost_save")
        )
        preset_save_btn.pack(side="left", padx=(0, 6))

        preset_balanced_btn = ctk.CTkButton(
            preset_button_frame,
            text="균형형",
            width=110,
            height=32,
            fg_color=self._color("secondary", "#4b5563"),
            hover_color=self._hover_from(self._color("secondary", "#4b5563")),
            command=lambda: self._apply_ai_model_preset("balanced")
        )
        preset_balanced_btn.pack(side="left", padx=6)

        preset_quality_btn = ctk.CTkButton(
            preset_button_frame,
            text="정밀형",
            width=110,
            height=32,
            fg_color=self._color("secondary", "#4b5563"),
            hover_color=self._hover_from(self._color("secondary", "#4b5563")),
            command=lambda: self._apply_ai_model_preset("quality")
        )
        preset_quality_btn.pack(side="left", padx=6)

        self.ai_preset_cost_badge_label = ctk.CTkLabel(
            openai_group,
            text="예상 비용 레벨: -",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self._color("text_secondary", "#9ca3af")
        )
        self.ai_preset_cost_badge_label.pack(anchor="w", padx=20, pady=(0, 10))

        response_mode_row = ctk.CTkFrame(openai_group, fg_color="transparent")
        response_mode_row.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkLabel(
            response_mode_row,
            text="AI 문답 정책:",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self._color("text_secondary", "#9ca3af"),
        ).pack(side="left")
        self.assistant_response_mode_combo = ctk.CTkComboBox(
            response_mode_row,
            values=["문답 절약형", "질문답변 표준형", "분석 정밀형"],
            state="readonly",
            width=190,
        )
        self.assistant_response_mode_combo.set("질문답변 표준형")
        self.assistant_response_mode_combo.pack(side="right")

        onboarding_button = ctk.CTkButton(
            openai_group,
            text="AI로 초기 설정하기 (5문항 가이드)",
            height=34,
            width=260,
            fg_color=self._color("primary", "#3b82f6"),
            hover_color="#2563eb",
            command=self._launch_ai_onboarding_guide
        )
        onboarding_button.pack(anchor="w", padx=20, pady=(0, 12))
        # ────────────────────────────────────────────────────────────────────

        apply_mode_label = ctk.CTkLabel(
            openai_group,
            text="AI 설정 적용 방식:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        apply_mode_label.pack(anchor="w", padx=20, pady=(4, 5))

        self.assistant_apply_mode_combo = ctk.CTkComboBox(
            openai_group,
            values=["사용자 최종확인"],
            height=36,
            width=220,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            state="readonly"
        )
        self.assistant_apply_mode_combo.set("사용자 최종확인")
        self.assistant_apply_mode_combo.pack(anchor="w", padx=20, pady=(0, 12))

        # AI 어시스턴트 음성 설정
        voice_title_label = ctk.CTkLabel(
            openai_group,
            text="AI 어시스턴트 음성 설정:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        voice_title_label.pack(anchor="w", padx=20, pady=(10, 8))

        self.assistant_voice_enabled_var = ctk.BooleanVar(value=False)
        voice_enabled_switch = ctk.CTkSwitch(
            openai_group,
            text="음성 모듈 활성화",
            variable=self.assistant_voice_enabled_var
        )
        voice_enabled_switch.pack(anchor="w", padx=20, pady=(0, 8))

        self.assistant_voice_auto_tts_var = ctk.BooleanVar(value=False)
        voice_auto_tts_switch = ctk.CTkSwitch(
            openai_group,
            text="AI 답변 자동 음성 읽기 (TTS)",
            variable=self.assistant_voice_auto_tts_var
        )
        voice_auto_tts_switch.pack(anchor="w", padx=20, pady=(0, 8))

        voice_rate_label = ctk.CTkLabel(
            openai_group,
            text="음성 속도:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self._color("text_secondary", "#9ca3af")
        )
        voice_rate_label.pack(anchor="w", padx=20, pady=(4, 4))

        self.assistant_voice_rate_combo = ctk.CTkComboBox(
            openai_group,
            values=["140", "160", "180", "200", "220", "240"],
            height=34,
            width=120,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            state="readonly"
        )
        self.assistant_voice_rate_combo.set("180")
        self.assistant_voice_rate_combo.pack(anchor="w", padx=20, pady=(0, 12))

        # 백엔드 설정은 사용자가 건드릴 필요 없음 - 제거됨

        # 안내 메시지
        info_text = f"""AI 엔진/API 설정 안내

• AI 애널리스트 모델: 시장 분석과 신호 후보를 만드는 기본 분석 모델
• AI 어시스턴트 모델: 사용자와의 대화 및 질의응답에 사용되는 AI 모델
• 위 엔진 선택은 API 키 편집 대상이며 실제 작업 배치는 각 Provider+모델 선택에서 정합니다
• OpenAI·DeepSeek·Claude·Gemini·Kimi를 작업별로 배치할 수 있습니다
• Kimi 일반 서비스와 개발자 API는 별개이며 API는 사용량 기반 과금입니다
• 작업별 모델 배치: 빈번 신호·손익 리포트·정밀 진단마다 서로 다른 Provider와 모델을 보낼 수 있습니다
  기존 모델 문자열은 같은 기존 Provider의 새 구조로 자동 변환됩니다
• 프리셋 선택 가이드:
    - 절약형: API 비용이 가장 중요할 때
    - 균형형: 초보/일반 사용자 기본 권장
    - 정밀형: 진단 정확도가 비용보다 중요할 때
• AI 설정 적용 방식: 거래 관련 변경은 항상 "사용자 최종확인" 2단계를 거칩니다
• 어시스턴트 대화로 모델 변경/티어 조정을 요청해도 변경 전/후 확인 없이 저장되지 않습니다
• API 키: 선택한 제공사의 공식 Console에서 발급한 별도 API 키를 입력하세요
• v3.9.0.4는 Windows 보안 저장소나 추가 패키지 없이 다른 API 키와 같은 사용자별 로컬 설정에 저장합니다
  설정·백업에는 민감정보가 있으므로 지원 전달 시 해당 파일을 포함하지 마세요
• ChatGPT 유료(Plus/Team)와 OpenAI API 과금은 별개입니다
• OpenAI 호환 Base URL(선택): OpenAI 기본 엔드포인트 대신 DeepSeek/OpenRouter/Ollama 등 호환 API를 사용할 때 입력합니다
• AI 설정 도우미: '키 발급' 도구가 아니라 키 발급 후 모델/적용정책을 도와주는 기능입니다
• AI 커스텀 무자막 전사는 분석 Provider와 분리된 OpenAI 전사 프로필을 사용합니다
• 모델은 권장·계정 확인·미리보기·비권장·종료로 구분되며 종료 모델은 저장할 수 없습니다

[AI 커스텀 Provider별 현재 연결 범위]
{build_ai_custom_provider_guide()}"""

        info_label = ctk.CTkLabel(
            scroll_frame,
            text=info_text,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        )
        info_label.pack(fill="x", pady=(0, 20))

    def _selected_ai_provider(self) -> str:
        label = self.ai_provider_var.get() if hasattr(self, "ai_provider_var") else "OpenAI"
        return self._AI_PROVIDER_LABELS.get(label, "openai")

    def _on_ai_provider_change(self, _selected_label: Optional[str] = None):
        """제공사 변경 시 키 버퍼·공식 Base URL·모델 목록을 안전하게 전환한다."""
        provider = self._selected_ai_provider()
        previous = str(getattr(self, "_active_ai_provider", "") or "")
        if previous and hasattr(self, "openai_api_key_entry"):
            self._ai_provider_key_buffer[previous] = self.openai_api_key_entry.get().strip()
        self._active_ai_provider = provider

        credentials = self.current_settings.get("ai_credentials", {})
        provider_cfg = credentials.get(provider, {}) if isinstance(credentials, dict) else {}
        existing_key = (
            self._ai_provider_key_buffer.get(provider)
            or (provider_cfg.get("api_key") if isinstance(provider_cfg, dict) else "")
            or (self.current_settings.get("openai_api_key", "") if provider == "openai" else "")
        )
        if hasattr(self, "openai_api_key_entry"):
            self.openai_api_key_entry.delete(0, "end")
            self.openai_api_key_entry.insert(0, str(existing_key or ""))
        if hasattr(self, "ai_api_key_label"):
            has_unresolved_reference = bool(
                isinstance(provider_cfg, dict)
                and provider_cfg.get("credential_ref")
                and not str(existing_key or "").strip()
            )
            suffix = " · v3.9.0.3 키 재입력 필요" if has_unresolved_reference else ""
            self.ai_api_key_label.configure(
                text=(
                    f"{self._AI_PROVIDER_LABELS_REVERSE().get(provider, provider)} "
                    f"API Key{suffix}:"
                )
            )
        if hasattr(self, "openai_base_url_entry"):
            base_url = (
                provider_cfg.get("base_url")
                if isinstance(provider_cfg, dict) and provider_cfg.get("base_url") is not None
                else self._AI_PROVIDER_BASE_URLS.get(provider, "")
            )
            self.openai_base_url_entry.delete(0, "end")
            self.openai_base_url_entry.insert(0, str(base_url or ""))

        if hasattr(self, "ai_catalog_status_label"):
            suffix = " · 정식 OpenAI 호환 API · 별도 사용량 과금" if provider == "kimi" else ""
            self.ai_catalog_status_label.configure(
                text=(
                    f"{self._AI_PROVIDER_LABELS_REVERSE().get(provider, provider)} API 자격증명 편집"
                    f"{suffix} · 모델 배치는 아래 작업별 엔진에서 선택"
                ),
                text_color="#38bdf8",
            )
        if hasattr(self, "ai_price_guide_label"):
            try:
                from trading.ai.provider_catalog import format_provider_price_guide
                self.ai_price_guide_label.configure(text=format_provider_price_guide(provider))
            except Exception:
                pass

    @classmethod
    def _AI_PROVIDER_LABELS_REVERSE(cls) -> Dict[str, str]:
        return {value: label for label, value in cls._AI_PROVIDER_LABELS.items()}

    @staticmethod
    def _assignment_widget_names(scope: str) -> tuple[str, str]:
        return {
            "analyst": ("ai_analyst_provider_combo", "openai_model_combo"),
            "assistant": ("ai_assistant_provider_combo", "assistant_ai_model_combo"),
            "frequent_cheap": ("ai_role_cheap_provider_combo", "ai_role_cheap_combo"),
            "standard": ("ai_role_standard_provider_combo", "ai_role_standard_combo"),
            "premium": ("ai_role_premium_provider_combo", "ai_role_premium_combo"),
        }[scope]

    def _assignment_provider(self, scope: str) -> str:
        provider_name, _ = self._assignment_widget_names(scope)
        combo = getattr(self, provider_name, None)
        label = combo.get() if combo is not None else "OpenAI"
        return self._AI_PROVIDER_LABELS.get(label, "openai")

    def _assignment_route(self, scope: str) -> Dict[str, str]:
        _, model_name = self._assignment_widget_names(scope)
        combo = getattr(self, model_name, None)
        provider = self._assignment_provider(scope)
        model = str(combo.get() if combo is not None else "").strip()
        if not model:
            models = self._AI_PROVIDER_MODELS.get(provider, self._AI_MODEL_FALLBACKS)
            model = str(models[0])
        return {"provider": provider, "model": model}

    def _on_ai_custom_feature_profile_changed(self, selected_label: Optional[str] = None):
        """숙련도 프로필을 개별 토글의 안전한 시작값으로 적용한다."""
        from trading.ai_custom_features import PROFILE_FEATURES

        label_to_profile = {"초보자": "beginner", "일반": "standard", "고급": "advanced", "실험실": "lab"}
        label = str(
            selected_label
            or (self.ai_custom_feature_profile_combo.get() if hasattr(self, "ai_custom_feature_profile_combo") else "일반")
        )
        profile = label_to_profile.get(label, "standard")
        for key, value in PROFILE_FEATURES[profile].items():
            variable = getattr(self, "ai_custom_feature_vars", {}).get(key)
            if variable is not None:
                variable.set(bool(value))
        webhook_switch = getattr(self, "ai_custom_feature_switches", {}).get("signed_webhook")
        if webhook_switch is not None:
            webhook_switch.configure(state="normal" if profile == "lab" else "disabled")
        help_texts = {
            "beginner": "초보자 · Level 1 요약, 원본 근거, PnL·MDD와 품질 경고만 우선 보여 줍니다.",
            "standard": "일반(권장) · Level 2 핵심값, 월·연도 성과표와 전략 패키지까지 사용합니다.",
            "advanced": "고급 · Level 3 전체 IR, Expression Graph와 제한형 사용자 지표를 직접 편집합니다.",
            "lab": "실험실 · 고급 기능에 외부 서명 신호 검증을 추가합니다. 운영 endpoint가 준비됐다는 뜻은 아닙니다.",
        }
        label_widget = getattr(self, "ai_custom_profile_help_label", None)
        if label_widget is not None:
            label_widget.configure(text=help_texts[profile])

    def _toggle_ai_custom_advanced_features(self):
        """프로필만 필요한 사용자가 개별 고급 토글에 압도되지 않도록 기본 접힘 처리한다."""
        grid = getattr(self, "ai_custom_feature_grid", None)
        button = getattr(self, "ai_custom_advanced_toggle_button", None)
        if grid is None or button is None:
            return
        visible = not bool(getattr(self, "_ai_custom_advanced_features_visible", False))
        self._ai_custom_advanced_features_visible = visible
        if visible:
            grid.pack(fill="x", padx=14, pady=(0, 8))
            button.configure(text="개별 고급 기능 접기")
        else:
            grid.pack_forget()
            button.configure(text="개별 고급 기능 펼치기")

    def _collect_ai_custom_feature_settings(self) -> Dict[str, Any]:
        from trading.ai_custom_features import PROFILE_FEATURES

        label_to_profile = {"초보자": "beginner", "일반": "standard", "고급": "advanced", "실험실": "lab"}
        label = self.ai_custom_feature_profile_combo.get() if hasattr(self, "ai_custom_feature_profile_combo") else "일반"
        profile = label_to_profile.get(str(label), "standard")
        overrides = {}
        for key, default in PROFILE_FEATURES[profile].items():
            variable = getattr(self, "ai_custom_feature_vars", {}).get(key)
            current = bool(variable.get()) if variable is not None else bool(default)
            if current != bool(default):
                overrides[key] = current
        return {"profile": profile, "overrides": overrides}

    def _on_assignment_provider_change(self, scope: str):
        provider = self._assignment_provider(scope)
        _, model_name = self._assignment_widget_names(scope)
        model_combo = getattr(self, model_name, None)
        if model_combo is None:
            return
        models = list(dict.fromkeys(
            list(self._AI_PROVIDER_MODELS.get(provider, self._AI_MODEL_FALLBACKS))
            + [
                model for model in self._ai_discovered_models.get(provider, [])
                if model_record(provider, model).get("status") != "retired"
            ]
        ))
        current = str(model_combo.get() or "")
        model_combo.configure(values=models)
        model_combo.set(current if current in models else models[0])
        self._on_assignment_model_change(scope)

    def _on_assignment_model_change(self, scope: str):
        if not hasattr(self, "ai_model_lifecycle_label"):
            return
        route = self._assignment_route(scope)
        discovered = (
            self._ai_discovered_models.get(route["provider"])
            if route["provider"] in self._ai_discovered_models
            else None
        )
        self.ai_model_lifecycle_label.configure(
            text=(
                f"{scope}: {self._AI_PROVIDER_LABELS_REVERSE().get(route['provider'], route['provider'])}"
                f" / {route['model']} · "
                f"{model_status_text(route['provider'], route['model'], account_models=discovered)}"
            ),
            text_color="#f59e0b" if "비권장" in model_status_text(
                route["provider"], route["model"], account_models=discovered
            ) else "#38bdf8",
        )

    def _validate_ai_routes_for_save(
        self,
        candidate: Dict[str, Any],
    ) -> tuple[List[str], List[str]]:
        """저장 직전 정적 capability와 실제 계정 모델 노출 여부를 검사한다."""
        routes: List[tuple[str, Dict[str, str], str]] = [
            ("AI 애널리스트", dict(candidate["ai_provider_profiles"]["analyst"]), "chat_json"),
            ("AI 어시스턴트", dict(candidate["ai_provider_profiles"]["assistant"]), "chat_text"),
        ]
        for tier, route in dict(candidate.get("ai_model_roles", {}) or {}).items():
            if isinstance(route, dict):
                routes.append((f"작업별 {tier}", dict(route), "chat_json"))
        transcription = dict(candidate.get("ai_custom_transcription", {}) or {})
        if transcription.get("enabled", True):
            routes.append((
                "AI 커스텀 음성 전사",
                {
                    "provider": str(transcription.get("provider") or "openai"),
                    "model": str(transcription.get("model") or "gpt-4o-mini-transcribe"),
                },
                "transcribe",
            ))

        errors: List[str] = []
        warnings: List[str] = []
        account_cache: Dict[tuple[str, str], Optional[List[str]]] = {}
        from trading.ai.credentials import hydrate_ai_credentials
        from trading.ai.provider_router import AIProviderRouter

        runtime = hydrate_ai_credentials(candidate)
        credentials = runtime.get("ai_credentials", {})
        for label, route, capability in routes:
            provider = str(route.get("provider") or "openai").lower()
            model = str(route.get("model") or "")
            static_result = validate_model_route(
                provider,
                model,
                capability=capability,
            )
            errors.extend(f"{label}: {item}" for item in static_result["errors"])
            warnings.extend(f"{label}: {item}" for item in static_result["warnings"])
            if static_result["errors"]:
                continue

            credential = credentials.get(provider, {}) if isinstance(credentials, dict) else {}
            api_key = str(credential.get("api_key") or "") if isinstance(credential, dict) else ""
            if not api_key:
                warnings.append(f"{label}: {provider} API 키가 없어 계정 사용 가능 여부는 테스터 검증 대기입니다.")
                continue
            cache_key = (provider, capability)
            if cache_key not in account_cache:
                try:
                    router = AIProviderRouter(
                        provider,
                        api_key=api_key,
                        model=model,
                        base_url=(
                            credential.get("base_url")
                            if isinstance(credential, dict)
                            else None
                        ),
                    )
                    discovered = router.list_models(
                        include_fallback=False,
                        capability=capability,
                    )
                    if discovered:
                        account_cache[cache_key] = discovered
                        if capability != "transcribe":
                            self._ai_discovered_models[provider] = list(discovered)
                    else:
                        account_cache[cache_key] = None
                        raw_error = router.adapter.client.get_last_error()
                        warnings.append(
                            f"{label}: 실제 모델 목록을 확인하지 못했습니다"
                            f"{': ' + str(raw_error.get('message')) if raw_error else ''}."
                        )
                except Exception as exc:
                    account_cache[cache_key] = None
                    warnings.append(f"{label}: 실제 API 확인을 완료하지 못했습니다: {exc}")
            account_models = account_cache.get(cache_key)
            if account_models is not None:
                live_result = validate_model_route(
                    provider,
                    model,
                    capability=capability,
                    account_models=account_models,
                )
                errors.extend(f"{label}: {item}" for item in live_result["errors"])
        return errors, list(dict.fromkeys(warnings))

    def _refresh_ai_model_catalog(self):
        """선택 제공사 계정에서 실제 허용된 모델 목록을 비동기로 조회한다."""
        if not self._window_alive():
            return
        api_key = str(self._read_live_widget("openai_api_key_entry", "") or "").strip()
        if not api_key:
            messagebox.showwarning("API 키 필요", "사용 가능 모델 조회를 위해 선택한 제공사의 API 키를 먼저 입력하세요.")
            return
        if hasattr(self, 'ai_catalog_status_label'):
            self.ai_catalog_status_label.configure(text="모델 카탈로그 조회 중...", text_color="#38bdf8")
        provider = self._selected_ai_provider()
        base_url = str(self._read_live_widget("openai_base_url_entry", "") or "").strip()

        def worker():
            try:
                from trading.ai.provider_router import AIProviderRouter
                router = AIProviderRouter(
                    provider,
                    api_key=api_key,
                    base_url=base_url or None,
                )
                discovered = router.list_models(include_fallback=False)
                self._dispatch_window_result(
                    lambda: self._apply_ai_model_catalog(discovered)
                )
            except Exception as exc:
                error = str(exc)
                self._dispatch_window_result(
                    lambda: self._apply_ai_model_catalog([], error=error)
                )

        threading.Thread(target=worker, daemon=True).start()

    def _run_ai_provider_preflight(self):
        """사용자가 선택한 실제 Provider 계약을 소액 호출로 검증한다."""
        if not self._window_alive():
            return
        audio_path = ""
        transcription_enabled = bool(
            self._read_live_widget("ai_custom_transcription_enabled_var", False)
        )
        if transcription_enabled:
            include_audio = messagebox.askyesno(
                "음성 전사 검증",
                "짧은 음성 파일까지 선택해 전사를 검증하시겠습니까?\n"
                "아니오를 선택하면 전사 모델 접근 권한까지만 확인합니다.",
            )
            if include_audio:
                audio_path = filedialog.askopenfilename(
                    title="전사 검증용 짧은 음성 파일",
                    filetypes=[
                        ("Audio", "*.mp3 *.m4a *.wav *.webm *.mp4"),
                        ("All files", "*.*"),
                    ],
                )
        candidate = copy.deepcopy(self.current_settings)
        try:
            active_provider = self._selected_ai_provider()
        except (tk.TclError, RuntimeError):
            return
        self._ai_provider_key_buffer[active_provider] = str(
            self._read_live_widget("openai_api_key_entry", "") or ""
        ).strip()
        credentials = copy.deepcopy(candidate.get("ai_credentials", {}) or {})
        for provider, api_key in self._ai_provider_key_buffer.items():
            cfg = dict(credentials.get(provider, {}) or {})
            if api_key:
                cfg["api_key"] = api_key
            if provider == active_provider:
                cfg["base_url"] = str(
                    self._read_live_widget("openai_base_url_entry", "") or ""
                ).strip()
            credentials[provider] = cfg
        candidate.update({
            "ai_provider": self._assignment_provider("analyst"),
            "ai_credentials": credentials,
            "ai_provider_profiles": {
                "analyst": self._assignment_route("analyst"),
                "assistant": self._assignment_route("assistant"),
                "transcription": {
                    "provider": "openai",
                    "model": self._read_live_widget(
                        "ai_custom_transcription_model_combo",
                        "gpt-4o-mini-transcribe",
                    ),
                },
            },
            "ai_model_roles": {
                "frequent_cheap": self._assignment_route("frequent_cheap"),
                "standard": self._assignment_route("standard"),
                "premium": self._assignment_route("premium"),
            },
            "ai_custom_transcription": {
                "enabled": transcription_enabled,
                "provider": "openai",
                "model": self._read_live_widget(
                    "ai_custom_transcription_model_combo",
                    "gpt-4o-mini-transcribe",
                ),
            },
        })
        self.ai_catalog_status_label.configure(
            text="실제 API 텍스트·JSON·사용량·오류·전사 계약 검증 중...",
            text_color="#38bdf8",
        )

        def worker():
            try:
                from trading.ai.preflight import run_ai_provider_preflight

                report = run_ai_provider_preflight(
                    candidate,
                    audio_path=audio_path or None,
                    perform_calls=True,
                )
                self._dispatch_window_result(
                    lambda: self._show_ai_preflight_result(report)
                )
            except Exception as exc:
                error = str(exc)
                self._dispatch_window_result(
                    lambda: messagebox.showerror("AI API 기능 검증 실패", error),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _show_ai_preflight_result(self, report: Dict[str, Any]):
        if not self._window_alive():
            return
        results = dict(report.get("results", {}) or {})
        lines = []
        for workload, item in results.items():
            status = str(item.get("status") or "failed")
            lines.append(
                f"• {workload}: {item.get('provider', '-')} / {item.get('model', '-')} · {status}"
            )
        ok = bool(report.get("ok"))
        self.ai_catalog_status_label.configure(
            text=f"실제 API 기능 검증 {'통과' if ok else '미통과'} · 상세 결과 창 확인",
            text_color="#22c55e" if ok else "#ef4444",
        )
        if ok:
            messagebox.showinfo("AI API 기능 검증 통과", "\n".join(lines))
        else:
            messagebox.showwarning(
                "AI API 기능 검증 미통과",
                "\n".join(lines)
                + "\n\nAPI 키·계정 모델 권한·시험 연동 상태 또는 음성 파일을 확인하세요.",
            )

    def _open_selected_ai_provider_console(self):
        provider = self._selected_ai_provider()
        label = self._AI_PROVIDER_LABELS_REVERSE().get(provider, provider)
        self._open_external_url(self._AI_PROVIDER_CONSOLES.get(provider, ""), f"{label} API 키")

    def _open_selected_ai_pricing(self):
        provider = self._selected_ai_provider()
        label = self._AI_PROVIDER_LABELS_REVERSE().get(provider, provider)
        try:
            from trading.ai.provider_catalog import OFFICIAL_PRICING_URLS
            url = OFFICIAL_PRICING_URLS.get(provider, "")
        except Exception:
            url = ""
        self._open_external_url(url, f"{label} 공식 가격")

    def _apply_ai_model_catalog(self, discovered: List[str], error: str = ''):
        provider = self._selected_ai_provider()
        if discovered:
            self._ai_discovered_models[provider] = list(dict.fromkeys(discovered))
        for scope in ("analyst", "assistant", "frequent_cheap", "standard", "premium"):
            if self._assignment_provider(scope) == provider:
                self._on_assignment_provider_change(scope)
        if hasattr(self, 'ai_catalog_status_label'):
            if discovered:
                self.ai_catalog_status_label.configure(
                    text=(
                        f"{self._AI_PROVIDER_LABELS_REVERSE().get(provider, provider)} API 계정에서 "
                        f"텍스트 모델 {len(discovered)}개 확인 · 권장/비권장 상태와 함께 적용"
                    ),
                    text_color="#22c55e",
                )
            else:
                self.ai_catalog_status_label.configure(
                    text=f"API 조회 실패 · 공식 기본 목록 유지{': ' + error if error else ''}",
                    text_color="#f59e0b",
                )

    def _apply_ai_model_preset(self, preset_name: str):
        """AI 엔진/API 탭의 모델 프리셋을 콤보 UI에 즉시 반영한다."""
        provider = self._selected_ai_provider()
        if provider == "deepseek":
            presets = {
                "cost_save": {
                    "openai_model": "deepseek-v4-flash", "assistant_ai_model": "deepseek-v4-flash",
                    "frequent_cheap": "deepseek-v4-flash", "standard": "deepseek-v4-flash",
                    "premium": "deepseek-v4-flash", "label": "절약형",
                    "desc": "DeepSeek V4 Flash 단일 구성입니다.", "cost_level": "낮음",
                },
                "balanced": {
                    "openai_model": "deepseek-v4-flash", "assistant_ai_model": "deepseek-v4-flash",
                    "frequent_cheap": "deepseek-v4-flash", "standard": "deepseek-v4-flash",
                    "premium": "deepseek-v4-pro", "label": "균형형",
                    "desc": "일반 호출은 Flash, 정밀 작업은 Pro를 사용합니다.", "cost_level": "중간",
                },
                "quality": {
                    "openai_model": "deepseek-v4-pro", "assistant_ai_model": "deepseek-v4-pro",
                    "frequent_cheap": "deepseek-v4-flash", "standard": "deepseek-v4-pro",
                    "premium": "deepseek-v4-pro", "label": "정밀형",
                    "desc": "정밀 작업을 DeepSeek V4 Pro로 배치합니다.", "cost_level": "높음",
                },
            }
        elif provider == "kimi":
            presets = {
                name: {
                    "openai_model": "kimi-k3",
                    "assistant_ai_model": "kimi-k2.6" if name == "cost_save" else "kimi-k3",
                    "frequent_cheap": "kimi-k2.6", "standard": "kimi-k2.6", "premium": "kimi-k3",
                    "label": label, "desc": "Kimi 정식 API를 작업별로 배치합니다. 일반 Kimi 서비스와 API 과금은 별개입니다.",
                    "cost_level": "중간",
                }
                for name, label in (("cost_save", "절약형"), ("balanced", "균형형"), ("quality", "정밀형"))
            }
        elif provider == "anthropic":
            presets = {
                "cost_save": {
                    "openai_model": "claude-haiku-4-5", "assistant_ai_model": "claude-haiku-4-5",
                    "frequent_cheap": "claude-haiku-4-5", "standard": "claude-haiku-4-5",
                    "premium": "claude-sonnet-5", "label": "절약형",
                    "desc": "빈번 호출은 Haiku, 정밀 작업은 Sonnet을 사용합니다.", "cost_level": "낮음",
                },
                "balanced": {
                    "openai_model": "claude-sonnet-5", "assistant_ai_model": "claude-sonnet-5",
                    "frequent_cheap": "claude-haiku-4-5", "standard": "claude-sonnet-5",
                    "premium": "claude-opus-5", "label": "균형형",
                    "desc": "일반 분석은 Sonnet, 정밀 작업은 Opus를 사용합니다.", "cost_level": "중간",
                },
                "quality": {
                    "openai_model": "claude-opus-5", "assistant_ai_model": "claude-opus-5",
                    "frequent_cheap": "claude-sonnet-5", "standard": "claude-opus-5",
                    "premium": "claude-opus-5", "label": "정밀형",
                    "desc": "복잡한 분석을 Opus 중심으로 배치합니다.", "cost_level": "높음",
                },
            }
        elif provider == "gemini":
            presets = {
                "cost_save": {
                    "openai_model": "gemini-3.5-flash-lite", "assistant_ai_model": "gemini-3.5-flash-lite",
                    "frequent_cheap": "gemini-3.5-flash-lite", "standard": "gemini-3.5-flash-lite",
                    "premium": "gemini-3.6-flash", "label": "절약형",
                    "desc": "Flash-Lite 중심의 고효율 구성입니다.", "cost_level": "낮음",
                },
                "balanced": {
                    "openai_model": "gemini-3.6-flash", "assistant_ai_model": "gemini-3.6-flash",
                    "frequent_cheap": "gemini-3.5-flash-lite", "standard": "gemini-3.6-flash",
                    "premium": "gemini-3.1-pro-preview", "label": "균형형",
                    "desc": "일반 호출은 Flash, 정밀 작업은 Pro Preview를 사용합니다.", "cost_level": "중간",
                },
                "quality": {
                    "openai_model": "gemini-3.1-pro-preview", "assistant_ai_model": "gemini-3.1-pro-preview",
                    "frequent_cheap": "gemini-3.6-flash", "standard": "gemini-3.1-pro-preview",
                    "premium": "gemini-3.1-pro-preview", "label": "정밀형",
                    "desc": "Pro Preview 중심이며 모델 상태와 가격을 공식 페이지에서 확인해야 합니다.", "cost_level": "높음",
                },
            }
        else:
            presets = {
                'cost_save': {
                'openai_model': 'gpt-5.6-luna',
                'assistant_ai_model': 'gpt-5.6-luna',
                'frequent_cheap': 'gpt-5.6-luna',
                'standard': 'gpt-5.6-luna',
                'premium': 'gpt-5.6-luna',
                'label': '절약형',
                'desc': 'API 비용을 최소화하려는 사용자에게 적합합니다.',
                'cost_level': '낮음',
            },
            'balanced': {
                'openai_model': 'gpt-5.6-luna',
                'assistant_ai_model': 'gpt-5.6-terra',
                'frequent_cheap': 'gpt-5.6-luna',
                'standard': 'gpt-5.6-luna',
                'premium': 'gpt-5.6-terra',
                'label': '균형형',
                'desc': '비용/품질 균형이 좋아 초보 포함 대부분 사용자에게 권장됩니다.',
                'cost_level': '중간',
            },
            'quality': {
                'openai_model': 'gpt-5.6-terra',
                'assistant_ai_model': 'gpt-5.6-sol',
                'frequent_cheap': 'gpt-5.6-luna',
                'standard': 'gpt-5.6-terra',
                'premium': 'gpt-5.6-sol',
                'label': '정밀형',
                'desc': '복잡한 진단 정확도를 우선할 때 적합하지만 비용이 증가할 수 있습니다.',
                'cost_level': '높음',
                },
            }
        selected = presets.get(preset_name)
        if not selected:
            return

        try:
            provider_label = self._AI_PROVIDER_LABELS_REVERSE().get(provider, "OpenAI")
            for combo_name in (
                "ai_analyst_provider_combo",
                "ai_role_cheap_provider_combo",
                "ai_role_standard_provider_combo",
                "ai_role_premium_provider_combo",
            ):
                combo = getattr(self, combo_name, None)
                if combo is not None:
                    combo.set(provider_label)
            for scope in ("analyst", "frequent_cheap", "standard", "premium"):
                self._on_assignment_provider_change(scope)
            if hasattr(self, "ai_assistant_provider_combo"):
                self.ai_assistant_provider_combo.set(provider_label)
                self._on_assignment_provider_change("assistant")
            if hasattr(self, 'openai_model_combo'):
                self.openai_model_combo.set(selected['openai_model'])
            if hasattr(self, 'assistant_ai_model_combo'):
                self.assistant_ai_model_combo.set(selected['assistant_ai_model'])
            if hasattr(self, 'ai_role_cheap_combo'):
                self.ai_role_cheap_combo.set(selected['frequent_cheap'])
            if hasattr(self, 'ai_role_standard_combo'):
                self.ai_role_standard_combo.set(selected['standard'])
            if hasattr(self, 'ai_role_premium_combo'):
                self.ai_role_premium_combo.set(selected['premium'])
            if hasattr(self, 'ai_preset_cost_badge_label') and self.ai_preset_cost_badge_label:
                cost_level = selected.get('cost_level', '-')
                color = {
                    '낮음': self._color('success', '#22c55e'),
                    '중간': self._color('warning', '#f59e0b'),
                    '높음': self._color('danger', '#ef4444'),
                }.get(cost_level, self._color('text_secondary', '#9ca3af'))
                self.ai_preset_cost_badge_label.configure(
                    text=f"예상 비용 레벨: {cost_level}",
                    text_color=color,
                )
            messagebox.showinfo(
                "모델 프리셋 적용",
                (
                    f"{selected['label']} 프리셋이 적용되었습니다.\n\n"
                    f"예상 비용 레벨: {selected.get('cost_level', '-')}\n"
                    f"적용 의미: {selected.get('desc', '')}\n"
                    "지금은 미리보기 상태이며, 하단 '설정 저장'을 눌러야 실제 반영됩니다."
                )
            )
        except Exception as e:
            messagebox.showerror("모델 프리셋", f"프리셋 적용 중 오류가 발생했습니다.\n\n오류: {e}")

    def _launch_ai_onboarding_guide(self):
        """설정 창에서 AI 어시스턴트 온보딩 가이드를 시작한다."""
        try:
            dashboard = getattr(self, 'parent', None)
            if not dashboard:
                messagebox.showinfo("초기 설정 가이드", "대시보드가 연결되지 않아 온보딩을 시작할 수 없습니다.")
                return

            # 공용 생명주기 해석기를 통해 파괴된 Tcl 위젯 재사용을 막는다.
            resolver = getattr(dashboard, '_get_live_ai_assistant', None)
            assistant = resolver() if callable(resolver) else None
            if hasattr(dashboard, 'tab_widget') and dashboard.tab_widget:
                try:
                    dashboard.tab_widget.set("AI 어시스턴트")
                except Exception:
                    pass

            if assistant and hasattr(assistant, 'start_initial_onboarding'):
                assistant.start_initial_onboarding(source='settings_openai')
                messagebox.showinfo(
                    "초기 설정 가이드 시작",
                    "AI 어시스턴트 탭에서 5문항 초기 설정 가이드를 시작했습니다.\n"
                    "질문에 답하면 최종 요약/확인 후 적용됩니다."
                )
                return

            messagebox.showwarning(
                "초기 설정 가이드",
                "AI 어시스턴트 위젯을 찾지 못했습니다.\n"
                "대시보드에서 'AI 어시스턴트' 탭을 먼저 열고 다시 시도해 주세요."
            )
        except Exception as e:
            messagebox.showerror("초기 설정 가이드", f"온보딩 시작 중 오류가 발생했습니다.\n\n오류: {e}")

    def _show_beginner_mode_guide(self):
        """초보자용 3단계 통합 안내를 단계형 모달로 보여준다."""
        try:
            steps = [
                {
                    'title': '1단계: OpenAI 연결',
                    'body': (
                        "- OpenAI API 키를 발급해 앱에 입력합니다.\n"
                        "- 초보 권장: 계정 확인된 최신 균형형 프리셋\n"
                        "- 결제 한도 권장: Hard 10~20달러 / Soft 5달러\n"
                        "- ChatGPT 구독과 OpenAI API 과금은 별개입니다."
                    ),
                    'action_text': 'OpenAI 발급 안내 열기',
                    'action': lambda: self._show_api_key_help_dialog(kind='openai'),
                },
                {
                    'title': '2단계: 거래소 API 연결',
                    'body': (
                        "- 거래소별 API Key/Secret을 공식 페이지에서 직접 발급합니다.\n"
                        "- 처음에는 출금 권한 OFF, 읽기/거래 권한만 권장합니다.\n"
                        "- 어려우면 실거래 전 mock/점검 경로를 먼저 확인하세요."
                    ),
                    'action_text': '거래소 발급 경로 열기',
                    'action': self._show_exchange_provider_links_dialog,
                },
                {
                    'title': '3단계: 증권사 연결(선택)',
                    'body': (
                        "- 키움/신한/미래에셋/한국투자 중 실제 사용하는 곳만 설정합니다.\n"
                        "- mock/점검 경로로 먼저 확인 후 실연결로 전환합니다.\n"
                        "- 마지막에만 실주문 허용 ON으로 바꾸세요."
                    ),
                    'action_text': '바로 점검 시작',
                    'action': self._on_click_stock_broker_connection_checklist,
                },
            ]

            dialog = ctk.CTkToplevel(self.root)
            dialog.title('초보자 모드 (전체 3단계)')
            dialog.geometry('720x520')
            dialog.transient(self.root)
            dialog.grab_set()

            container = ctk.CTkFrame(dialog)
            container.pack(fill='both', expand=True, padx=16, pady=16)

            step_index = tk.IntVar(value=0)

            title_label = ctk.CTkLabel(
                container,
                text='',
                font=ctk.CTkFont(family='Segoe UI', size=22, weight='bold'),
                text_color=self._color('text_primary', '#f9fafb')
            )
            title_label.pack(anchor='w', padx=20, pady=(20, 8))

            progress_label = ctk.CTkLabel(
                container,
                text='',
                font=ctk.CTkFont(family='Segoe UI', size=12),
                text_color=self._color('text_secondary', '#9ca3af')
            )
            progress_label.pack(anchor='w', padx=20, pady=(0, 8))

            body_box = ctk.CTkTextbox(container, font=ctk.CTkFont(family='Segoe UI', size=13), wrap='word')
            body_box.pack(fill='both', expand=True, padx=20, pady=(0, 12))

            footer_label = ctk.CTkLabel(
                container,
                text='중요: AI는 절차를 안내할 수는 있지만 키/인증을 대신 발급할 수는 없습니다.',
                font=ctk.CTkFont(family='Segoe UI', size=12),
                text_color='#f59e0b',
                justify='left'
            )
            footer_label.pack(anchor='w', padx=20, pady=(0, 12))

            button_row = ctk.CTkFrame(container, fg_color='transparent')
            button_row.pack(fill='x', padx=20, pady=(0, 20))

            prev_button = ctk.CTkButton(button_row, text='이전', width=90)
            prev_button.pack(side='left')

            next_button = ctk.CTkButton(button_row, text='다음', width=90)
            next_button.pack(side='left', padx=(8, 0))

            action_button = ctk.CTkButton(
                button_row,
                text='',
                width=190,
                fg_color=self._color('secondary', '#334155'),
                hover_color=self._hover_from(self._color('secondary', '#334155')),
            )
            action_button.pack(side='left', padx=(16, 0))

            ctk.CTkButton(button_row, text='닫기', width=100, command=dialog.destroy).pack(side='right')

            def render_step():
                index = step_index.get()
                current_step = steps[index]
                title_label.configure(text=current_step['title'])
                progress_label.configure(text=f'단계 {index + 1} / {len(steps)}')
                body_box.configure(state='normal')
                body_box.delete('1.0', 'end')
                body_box.insert(
                    '1.0',
                    '이 안내는 aitrading.exe 사용자 기준입니다.\n'
                    '개발 문서를 몰라도 순서대로 따라 하면 됩니다.\n\n'
                    + current_step['body']
                )
                body_box.configure(state='disabled')
                action_button.configure(text=current_step['action_text'], command=current_step['action'])
                prev_button.configure(state='normal' if index > 0 else 'disabled')
                next_button.configure(text='완료' if index == len(steps) - 1 else '다음')

            def go_prev():
                if step_index.get() > 0:
                    step_index.set(step_index.get() - 1)
                    render_step()

            def go_next():
                if step_index.get() >= len(steps) - 1:
                    dialog.destroy()
                    return
                step_index.set(step_index.get() + 1)
                render_step()

            prev_button.configure(command=go_prev)
            next_button.configure(command=go_next)
            render_step()
        except Exception as exc:
            messagebox.showerror('초보자 모드', f'초보자 안내를 표시하지 못했습니다.\n\n오류: {exc}')

    def _show_exchange_provider_links_dialog(self):
        """거래소 공식 API 발급 페이지를 버튼으로 안내한다."""
        providers = [
            ('Binance', 'https://www.binance.com/en/my/settings/api-management'),
            ('Bybit', 'https://www.bybit.com/app/user/api-management'),
            ('OKX', 'https://www.okx.com/account/my-api'),
            ('Bitget', 'https://www.bitget.com/account/newapi'),
            ('Upbit', 'https://upbit.com/mypage/open_api_management'),
            ('Bithumb', 'https://www.bithumb.com/myapi_management'),
        ]
        try:
            dialog = ctk.CTkToplevel(self.root)
            dialog.title('거래소 공식 발급 바로가기')
            dialog.geometry('560x420')
            dialog.transient(self.root)
            dialog.grab_set()

            frame = ctk.CTkFrame(dialog)
            frame.pack(fill='both', expand=True, padx=16, pady=16)

            ctk.CTkLabel(
                frame,
                text='거래소 공식 API 발급 바로가기',
                font=ctk.CTkFont(family='Segoe UI', size=20, weight='bold'),
                text_color=self._color('text_primary', '#f9fafb')
            ).pack(anchor='w', padx=20, pady=(20, 8))

            ctk.CTkLabel(
                frame,
                text='아래 버튼은 각 거래소의 공식 API 발급/관리 페이지를 브라우저에서 엽니다.\n로그인 상태와 지역/정책에 따라 화면 이름은 조금 다를 수 있습니다.',
                font=ctk.CTkFont(family='Segoe UI', size=12),
                text_color=self._color('text_secondary', '#9ca3af'),
                justify='left'
            ).pack(anchor='w', padx=20, pady=(0, 12))

            list_frame = ctk.CTkScrollableFrame(frame)
            list_frame.pack(fill='both', expand=True, padx=20, pady=(0, 12))

            for provider_name, provider_url in providers:
                row = ctk.CTkFrame(list_frame, fg_color='transparent')
                row.pack(fill='x', pady=4)
                ctk.CTkLabel(
                    row,
                    text=provider_name,
                    font=ctk.CTkFont(family='Segoe UI', size=13, weight='bold'),
                    text_color=self._color('text_primary', '#f9fafb')
                ).pack(side='left')
                ctk.CTkButton(
                    row,
                    text='공식 페이지 열기',
                    width=120,
                    fg_color=self._color('primary', '#2563eb'),
                    hover_color='#1d4ed8',
                    command=lambda url=provider_url, name=provider_name: self._open_external_url(url, name),
                ).pack(side='right')

            ctk.CTkButton(frame, text='닫기', width=100, command=dialog.destroy).pack(anchor='e', padx=20, pady=(0, 20))
        except Exception as exc:
            messagebox.showerror('거래소 발급 경로', f'거래소 발급 경로 안내를 표시하지 못했습니다.\n\n오류: {exc}')

    def _open_external_url(self, url: str, provider_name: str):
        """공식 외부 URL을 브라우저에서 연다."""
        try:
            webbrowser.open(url)
        except Exception as exc:
            messagebox.showerror(
                '브라우저 열기 실패',
                f'{provider_name} 공식 페이지를 열지 못했습니다.\n\n주소: {url}\n오류: {exc}'
            )

    def _show_stock_broker_provider_links_dialog(self):
        """증권사 공식 발급/안내 페이지를 버튼으로 안내한다."""
        providers = [
            ('키움증권', 'https://www1.kiwoom.com'),
            ('신한증권', 'https://www.shinhansec.com'),
            ('미래에셋증권', 'https://securities.miraeasset.com'),
            ('한국투자증권', 'https://securities.koreainvestment.com'),
        ]
        try:
            dialog = ctk.CTkToplevel(self.root)
            dialog.title('증권사 공식 발급 바로가기')
            dialog.geometry('560x380')
            dialog.transient(self.root)
            dialog.grab_set()

            frame = ctk.CTkFrame(dialog)
            frame.pack(fill='both', expand=True, padx=16, pady=16)

            ctk.CTkLabel(
                frame,
                text='증권사 공식 발급/안내 바로가기',
                font=ctk.CTkFont(family='Segoe UI', size=20, weight='bold'),
                text_color=self._color('text_primary', '#f9fafb')
            ).pack(anchor='w', padx=20, pady=(20, 8))

            ctk.CTkLabel(
                frame,
                text='브로커별 OpenAPI/개발자/안내 페이지는 정책에 따라 수시 변경될 수 있으므로, 우선 공식 메인/안내 경로를 엽니다.\n로그인 후 OpenAPI, 개발자센터, API, OpenAPI+ 메뉴를 찾으면 됩니다.',
                font=ctk.CTkFont(family='Segoe UI', size=12),
                text_color=self._color('text_secondary', '#9ca3af'),
                justify='left'
            ).pack(anchor='w', padx=20, pady=(0, 12))

            list_frame = ctk.CTkScrollableFrame(frame)
            list_frame.pack(fill='both', expand=True, padx=20, pady=(0, 12))

            for provider_name, provider_url in providers:
                row = ctk.CTkFrame(list_frame, fg_color='transparent')
                row.pack(fill='x', pady=4)
                ctk.CTkLabel(
                    row,
                    text=provider_name,
                    font=ctk.CTkFont(family='Segoe UI', size=13, weight='bold'),
                    text_color=self._color('text_primary', '#f9fafb')
                ).pack(side='left')
                ctk.CTkButton(
                    row,
                    text='공식 페이지 열기',
                    width=120,
                    fg_color=self._color('primary', '#2563eb'),
                    hover_color='#1d4ed8',
                    command=lambda url=provider_url, name=provider_name: self._open_external_url(url, name),
                ).pack(side='right')

            ctk.CTkButton(frame, text='닫기', width=100, command=dialog.destroy).pack(anchor='e', padx=20, pady=(0, 20))
        except Exception as exc:
            messagebox.showerror('증권사 발급 경로', f'증권사 발급 경로 안내를 표시하지 못했습니다.\n\n오류: {exc}')

    def _show_api_key_help_dialog(self, kind: str = 'openai'):
        """API 키 발급 경로와 AI 설정 도우미 위치를 짧게 안내한다."""
        try:
            if kind == 'openai':
                messagebox.showinfo(
                    "OpenAI 키 발급 안내",
                    (
                        "초심자용 OpenAI API 키 발급/입력 순서\n\n"
                        "[중요]\n"
                        "- ChatGPT 유료 구독(Plus/Team)과 OpenAI API 과금은 별개입니다.\n"
                        "- 이 앱은 OpenAI API 키가 필요합니다.\n\n"
                        "1) OpenAI 계정 만들기\n"
                        "   - https://platform.openai.com 에서 회원가입/로그인\n"
                        "2) 결제수단 + 사용한도 먼저 설정\n"
                        "   - Billing에서 카드/결제수단 등록\n"
                        "   - 권장: 월 Hard Limit 10~20달러, Soft Limit 5달러\n"
                        "   - 초보자는 작은 한도부터 시작 후 사용량 보고 상향\n"
                        "3) API 키 생성\n"
                        "   - API Keys 메뉴에서 'Create new secret key'\n"
                        "   - 키 이름(Name): 예) NoahAI-Desktop (구분용)\n"
                        "   - 생성 직후 키를 복사(다시 전체 조회 불가)\n"
                        "   - 참고: 보통 선충전 없이 사용 가능하며, 정책상 소액 결제 인증이 필요할 수 있습니다\n"
                        "4) 앱에 붙여넣기\n"
                        "   - 설정 > AI 엔진/API > OpenAI API Key에 붙여넣기\n"
                        "5) Base URL은 보통 비워두기\n"
                        "   - OpenAI 공식 API면 비워둡니다\n"
                        "   - DeepSeek/OpenRouter/Ollama 같은 호환 API일 때만 입력\n"
                        "6) 모델/프리셋 선택\n"
                        "   - 초보 기본 권장: 계정 확인된 최신 균형형 프리셋\n"
                        "7) 저장 후 테스트\n"
                        "   - AI 어시스턴트에서 간단 질문으로 연결 확인\n\n"
                        "참고 1) 'AI 설정 도우미 시작'은 키 발급 기능이 아니라\n"
                        "키 입력 이후 모델/적용방식 최적화를 도와주는 기능입니다.\n"
                        "참고 2) 앱 내부 안내 팝업: 'OpenAI/호환 API 사용자 안내' 버튼"
                    ),
                )
                return

            if kind == 'exchange':
                messagebox.showinfo(
                    "거래소 API 키 발급 안내",
                    (
                        "거래소 API 키는 앱에서 자동 발급되지 않습니다.\n"
                        "각 거래소 공식 페이지에서 발급 후 입력해야 합니다.\n\n"
                        "거래소별 발급 경로(요약)\n"
                        "- Binance: API Management\n"
                        "- Bybit: API Management\n"
                        "- OKX: API Key Management\n"
                        "- Bitget: API Key\n"
                        "- Upbit: Open API 관리\n"
                        "- Bithumb: API 관리\n\n"
                        "초보자 안전 설정\n"
                        "1) 읽기/거래 권한만 ON, 출금 권한은 반드시 OFF\n"
                        "2) 허용 IP를 사용할 수 있으면 등록 권장\n"
                        "3) Secret은 발급 직후 복사(재조회 제한)\n"
                        "4) 앱 입력 후 저장 -> 거래소 선택 탭에서 활성화\n"
                        "5) 대시보드에서 거래소별 '시작'으로 연결 검증\n\n"
                        "대안책\n"
                        "- 발급이 어렵거나 불안하면 실거래 전 mock/점검 경로로 먼저 검증하세요.\n"
                        "- AI는 발급 절차를 설명할 수 있지만 키를 대신 발급해주지는 못합니다.\n\n"
                        "추가 기능\n"
                        "- '거래소 공식 발급 바로가기' 버튼에서 거래소별 공식 페이지를 열 수 있습니다."
                    ),
                )
                return

            messagebox.showinfo(
                "AI 설정 도우미 위치 안내",
                (
                    "AI가 설정을 도와주는 기능 위치\n\n"
                    "1) 설정 > AI 엔진/API 탭\n"
                    "- 'AI 설정 도우미 시작'\n"
                    "- 'AI로 초기 설정하기 (5문항 가이드)'\n\n"
                    "2) 대시보드 > AI 어시스턴트 탭\n"
                    "- 설정관리에서 프리셋/온보딩 진행\n\n"
                    "참고: API 키 발급 자체는 외부(OpenAI/거래소)에서 해야 하며\n"
                    "앱은 발급된 키를 입력받아 검증/운용합니다."
                ),
            )
        except Exception:
            pass

    def _show_stock_broker_usage_help_dialog(self):
        """증권사 API 설정 항목의 의미와 권장 입력 순서를 안내한다."""
        messagebox.showinfo(
            "증권 설정 사용법",
            (
                "증권 설정은 '주문을 더 잘하게 만드는 숫자'가 아니라,\n"
                "어느 증권사에 어떤 방식으로 연결할지를 정하는 연결 설정입니다.\n\n"
                "핵심 항목\n"
                "1) 증권사 선택\n"
                "- 키움 / 신한 / 미래에셋 중 실제 사용할 곳만 켭니다.\n\n"
                "2) API 타입\n"
                "- openapi/rest: 실제 연결용\n"
                "- mock: 테스트용, 실제 주문 없음\n\n"
                "3) API 버전\n"
                "- 각 증권사 어댑터/라이브러리 종류입니다.\n"
                "- 모르면 기본값 유지가 권장됩니다.\n\n"
                "4) ID / 비밀번호 / 계좌번호\n"
                "- 증권사 로그인 또는 Open API 발급 정보입니다.\n"
                "- 현재 빌드에서는 일부 증권사에서 ID/비밀번호를 app_key/app_secret 대응값으로도 동기화 저장합니다.\n\n"
                "권장 순서\n"
                "- 1차: mock으로 연결 확인\n"
                "- 2차: openapi/rest로 전환\n"
                "- 3차: 저장 후 '연결 실패 5분 점검 가이드'로 진단\n"
                "- 4차: 마지막에만 실주문 허용 ON\n\n"
                "중요\n"
                "- 키움 실연결은 Windows 전용입니다.\n"
                "- 사용자는 배포 클라이언트 안에서 이해할 수 있어야 하므로, 이 화면과 사용자 매뉴얼의 설명이 정본입니다."
                "\n\n증권사별 발급/연결 경로(요약)\n"
                "- 키움: OpenAPI+ 신청/설치 -> HTS/KOA 로그인 확인 후 앱 입력\n"
                "- 신한/미래에셋/한국투자: 브로커 API 신청(개발자/오픈API 페이지) -> 발급 정보 앱 입력\n"
                "- 공통: 발급이 지연되면 mock/점검 경로로 먼저 UI/전략 동작 검증\n"
                "- '증권사 공식 발급 바로가기' 버튼으로 공식 안내 페이지를 바로 열 수 있습니다.\n"
                "\nAI 안내 관련\n"
                "- AI는 발급 절차 설명/체크리스트 제공은 가능하지만\n"
                "  증권사 인증/발급 자체를 대신 처리할 수는 없습니다."
            ),
        )

    def _show_stock_guardrail_help_dialog(self):
        """증권 주문 가드레일 숫자의 의미를 안내한다."""
        messagebox.showinfo(
            "증권 주문 가드레일 설명",
            (
                "이 숫자들은 AI 성능을 높이는 전략 파라미터가 아니라,\n"
                "실수·과대주문·오작동을 막는 주문 브레이크입니다.\n\n"
                "각 항목 의미\n"
                "- 가드레일 활성화: 모든 사전 안전검사를 켭니다.\n"
                "- 정규장 시간만 허용: 장외/비정상 시간 주문을 막습니다.\n"
                "- 시장가 허용: OFF면 급한 시장가 대신 더 보수적으로 제한합니다.\n"
                "- 최대 수량: 1회 주문에서 허용할 최대 주식 수량입니다.\n"
                "- 최대 금액(원): 1회 주문에서 허용할 최대 주문 금액입니다.\n"
                "- 일일 주문 한도: 하루 누적 주문 횟수 상한입니다.\n\n"
                "왜 수동인가\n"
                "- 이 값은 계좌 규모·운용 성향·브로커 정책에 따라 달라집니다.\n"
                "- AI가 임의로 크게 바꾸면 안전장치 역할이 약해질 수 있어 현재는 사용자가 통제합니다.\n\n"
                "권장 원칙\n"
                "- 모르면 기본값 유지\n"
                "- 실거래 전에는 더 작은 한도로 시작\n"
                "- 이 값을 자주 올리기보다, 실제 계좌 한도에 맞춘 보수적 상한으로 두기\n\n"
                "즉, 가드레일은 수익률 설정이 아니라 '과한 주문을 막는 안전벨트'입니다."
            ),
        )

    def _show_stock_auto_trading_help_dialog(self):
        """증권 자동매매 제어 항목의 의미를 안내한다."""
        messagebox.showinfo(
            "증권 자동매매 제어 설명",
            (
                "이 구역은 '언제 자동 흐름을 시작할지'와 '실제 주문을 허용할지'를 분리해 관리합니다.\n\n"
                "핵심 항목\n"
                "- 자동 시작(auto_start): 증권 탭 진입 시 자동 루프를 바로 시작할지 여부\n"
                "- 전역 실주문 허용(enable_stock_live_order): 모든 증권 LIVE의 1차 권한\n"
                "- 증권사별 LIVE 허용(allow_live_order): 선택한 증권사의 2차 권한\n"
                "- STOP 시 포지션 처리: 자동흐름 중지 시 기존 포지션을 유지할지 정리할지 기준\n\n"
                "왜 아직 수동 확인이 남아 있나\n"
                "- 증권 주문은 브로커 정책, 장시간, 계좌 상태, 실잔고 영향이 커서\n"
                "  사용자가 명시적으로 허용하는 단계가 안전합니다.\n"
                "- NoahAI 철학은 '몰래 자동화'가 아니라 '설명 → 확인 → 허용 범위 실행'입니다.\n\n"
                "권장 순서\n"
                "- 처음에는 auto_start OFF, 실주문 허용 OFF\n"
                "- 연결/로그/진단 확인 후 전역 LIVE와 해당 증권사 LIVE를 모두 ON\n"
                "- PAPER가 ON이면 두 LIVE 권한과 무관하게 외부 주문 없음\n"
                "- LIVE 권한 ON 후에도 연결 준비상태와 가드레일은 유지\n\n"
                "즉, 여기 값들은 AI 판단 품질 숫자가 아니라 실행 권한 스위치입니다."
            ),
        )

    def create_general_tab(self):
        """일반 설정 탭: 페이퍼 트레이딩 토글 등 공통 옵션"""
        tab = self.tabview.add("일반")
        self._add_tab_save_bar(tab, "1. 운용 모드")

        # 스크롤 가능한 프레임
        scroll_frame = ctk.CTkScrollableFrame(tab)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        try:
            from config.settings_contract import audit_settings_contract

            contract_report = audit_settings_contract(self.current_settings)
        except Exception:
            contract_report = {
                "schema_version": "확인 불가",
                "mode": "UNKNOWN",
                "mode_message": "설정 상태를 다시 불러와 주세요.",
                "archived_legacy_count": 0,
                "issues": [],
            }
        contract_group = ctk.CTkFrame(scroll_frame)
        contract_group.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(
            contract_group,
            text="설정 정리 상태",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb"),
        ).pack(anchor="w", padx=20, pady=(16, 6))
        ctk.CTkLabel(
            contract_group,
            text=(
                f"앱 {RELEASE_BUILD_LABEL} · 설정 스키마 {contract_report.get('schema_version')} · 현재 모드 "
                f"{contract_report.get('mode')} · 호환 보관 "
                f"{contract_report.get('archived_legacy_count', 0)}개 · "
                f"모순 {len(contract_report.get('issues', []))}건 · 주문 권한 확인 "
                f"{'완료' if contract_report.get('trade_scope_confirmed') else '미설정'}\n"
                f"{contract_report.get('mode_message')}\n"
                "화면에 없는 지표·캐시·주기 값은 서비스별 자동 정책이며 사용자가 직접 맞출 필요가 없습니다."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("info", "#60a5fa"),
            justify="left",
            wraplength=980,
        ).pack(anchor="w", padx=20, pady=(0, 16))

        # 일반 설정 그룹
        general_group = ctk.CTkFrame(scroll_frame)
        general_group.pack(fill="x", pady=(0, 20))

        title = ctk.CTkLabel(
            general_group,
            text="1. 운용 모드",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        title.pack(pady=(20, 15), padx=20)

        # 페이퍼 트레이딩 활성화 스위치
        current_val = bool(self.current_settings.get('paper_trading', False))
        self.paper_trading_var = ctk.BooleanVar(value=current_val)
        paper_switch = ctk.CTkSwitch(
            general_group,
            text="페이퍼 트레이딩 활성화",
            variable=self.paper_trading_var
        )
        paper_switch.pack(anchor="w", padx=20, pady=(4, 12))
        ctk.CTkLabel(
            general_group,
            text=(
                "실시간 시세·AI 분석·전략·가드레일은 그대로 실행하고 주문과 포지션만 내부에서 가상 체결합니다.\n"
                "저장 후 거래 시작을 누르면 선택된 모든 암호화폐 거래소와 증권사에 적용되며, "
                "'실제 주문 실행 거래소'를 선택하지 않아도 작동합니다. 실제 계좌·주문·실거래 KPI는 변경하지 않습니다."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("info", "#60a5fa"),
            justify="left",
            wraplength=980,
        ).pack(anchor="w", padx=20, pady=(0, 14))

        # 관리자 전용: 방송 리플레이 설정
        self.broadcast_replay_enabled_var = None
        self.broadcast_replay_source_entry = None

        # 상세 거래 로그 출력 스위치
        verbose_val = bool(self.current_settings.get('verbose_trade_logging', False))
        self.verbose_logging_var = ctk.BooleanVar(value=verbose_val)
        verbose_switch = ctk.CTkSwitch(
            general_group,
            text="상세 거래 로그 출력 (분석/전략/진입/모니터링/청산)",
            variable=self.verbose_logging_var
        )
        verbose_switch.pack(anchor="w", padx=20, pady=(4, 12))

        # 포지션 모드 설정 그룹
        position_mode_group = ctk.CTkFrame(scroll_frame)
        position_mode_group.pack(fill="x", pady=(0, 20))

        position_title = ctk.CTkLabel(
            position_mode_group,
            text="포지션 모드 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        position_title.pack(pady=(20, 15), padx=20)

        # 집중모드/다중포지션 모드 토글
        current_max_positions = self.current_settings.get('max_positions', 5)
        is_focus_mode = current_max_positions == 1

        self.position_mode_var = ctk.StringVar(value="focus" if is_focus_mode else "multi")

        # 모드 설명
        mode_info = ctk.CTkLabel(
            position_mode_group,
            text="• 집중모드: 한 번에 하나의 포지션만 허용 (리스크 집중 관리)\n• 다중포지션: 최대 3개까지 동시 포지션 허용 (포트폴리오 분산)",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        )
        mode_info.pack(anchor="w", padx=20, pady=(0, 10))

        # 모드 선택 라디오 버튼
        radio_frame = ctk.CTkFrame(position_mode_group)
        radio_frame.pack(fill="x", padx=20, pady=(0, 15))

        focus_radio = ctk.CTkRadioButton(
            radio_frame,
            text="집중모드 (max_positions = 1)",
            variable=self.position_mode_var,
            value="focus",
            command=self._on_position_mode_changed
        )
        focus_radio.pack(anchor="w", padx=10, pady=5)

        multi_radio = ctk.CTkRadioButton(
            radio_frame,
            text="다중포지션 모드 (max_positions = 3)",
            variable=self.position_mode_var,
            value="multi",
            command=self._on_position_mode_changed
        )
        multi_radio.pack(anchor="w", padx=10, pady=5)

        # 현재 활성 포지션 수 표시
        self.position_status_label = ctk.CTkLabel(
            position_mode_group,
            text="현재 활성 포지션: 0개",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#9ca3af")
        )
        self.position_status_label.pack(anchor="w", padx=20, pady=(0, 15))

        # 대시보드 항상 최상단 표시 스위치
        always_on_top_val = self.current_settings.get('ui_settings', {}).get('always_on_top', False)
        self.always_on_top_var = ctk.BooleanVar(value=always_on_top_val)
        always_on_top_switch = ctk.CTkSwitch(
            general_group,
            text="대시보드 항상 최상단 표시",
            variable=self.always_on_top_var
        )
        always_on_top_switch.pack(anchor="w", padx=20, pady=(4, 12))
        ctk.CTkLabel(
            general_group,
            text="ON이면 저장 즉시 대시보드 창에 적용되고, 다음 실행 때도 최상단 상태를 복원합니다. 기본값은 OFF입니다.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 14))

        # 관리자 전용 데모 모드 토글
        try:
            print("ModernSettingsWindow - 데모 모드 토글 생성 시작...")

            # 관리자 체크 (get_current_user_account 우선, 토큰 파일 폴백)
            is_admin = False
            current_user = ""

            # 방법 1: get_current_user_account 사용
            try:
                from path_utils import get_current_user_account
                current_user = get_current_user_account()
                print(f"ModernSettingsWindow - get_current_user_account 결과: '{current_user}'")
                if current_user:
                    from utils.admin_utils import is_admin_account
                    is_admin = is_admin_account(current_user)
                    print(f"ModernSettingsWindow - get_current_user_account로 관리자 확인: '{current_user}' -> {is_admin}")

                    # 개발환경에서 추가 확인
                    if is_admin:
                        print(f"ModernSettingsWindow - 개발환경에서 관리자 권한 확인: {current_user}")
            except Exception as e:
                print(f"ModernSettingsWindow - get_current_user_account 실패: {e}")

            # 방법 2: 토큰 파일에서 확인 (폴백) - path_utils 사용
            if not is_admin:
                try:
                    from path_utils import get_account_info_from_token

                    # path_utils의 get_account_info_from_token 함수 사용 (모든 경로 자동 확인)
                    token_user, token_path = get_account_info_from_token()
                    print(f"ModernSettingsWindow - path_utils로 토큰 파일 확인: 사용자='{token_user}', 경로={token_path}")

                    if token_user:
                        from utils.admin_utils import is_admin_account
                        user_id = token_user.lower()
                        is_admin = is_admin_account(user_id)
                        current_user = token_user
                        print(f"ModernSettingsWindow - 토큰 파일로 관리자 확인: '{current_user}' -> {is_admin}")

                        # 개발환경에서 추가 확인
                        if is_admin:
                            print(f"ModernSettingsWindow - 개발환경에서 토큰 파일로 관리자 권한 확인: {current_user}")
                    else:
                        print("ModernSettingsWindow - path_utils로도 토큰 파일을 찾을 수 없습니다.")

                except Exception as e:
                    print(f"ModernSettingsWindow - path_utils 토큰 파일 확인 실패: {e}")

            # 개발환경에서 강제 관리자 체크 제거 (보안상 위험)
            # if not is_admin and current_user:
            #     print(f"ModernSettingsWindow - 개발환경 디버깅: 사용자 '{current_user}'를 관리자로 강제 인식")
            #     is_admin = True
            #     print(f"ModernSettingsWindow - 강제 관리자 설정 완료: {is_admin}")

            print(f"ModernSettingsWindow - 최종 관리자 여부: {is_admin} (사용자: '{current_user}')")

            if is_admin:
                replay_group = ctk.CTkFrame(general_group)
                replay_group.pack(fill="x", padx=20, pady=(0, 12))

                ctk.CTkLabel(
                    replay_group,
                    text="방송 리플레이 설정 (관리자 전용)",
                    font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                    text_color=self._color("text_primary", "#f9fafb")
                ).pack(anchor="w", padx=10, pady=(10, 6))

                self.broadcast_replay_enabled_var = ctk.BooleanVar(
                    value=bool(self.current_settings.get('broadcast_replay_enabled', False))
                )
                ctk.CTkSwitch(
                    replay_group,
                    text="리플레이 읽기 소스 사용",
                    variable=self.broadcast_replay_enabled_var
                ).pack(anchor="w", padx=10, pady=(0, 8))

                source_row = ctk.CTkFrame(replay_group)
                source_row.pack(fill="x", padx=10, pady=(0, 10))

                ctk.CTkLabel(
                    source_row,
                    text="소스 계정"
                ).pack(side="left", padx=(0, 8))

                self.broadcast_replay_source_entry = ctk.CTkEntry(
                    source_row,
                    width=180,
                    placeholder_text="예: nwsoft"
                )
                self.broadcast_replay_source_entry.pack(side="left", padx=(0, 8))
                self.broadcast_replay_source_entry.insert(
                    0,
                    str(self.current_settings.get('broadcast_replay_source_account', '') or '')
                )

                ctk.CTkButton(
                    source_row,
                    text="소스 검증",
                    width=110,
                    command=self._validate_broadcast_replay_source
                ).pack(side="left")

                ctk.CTkLabel(
                    replay_group,
                    text="현재 계정 데이터는 유지되고, 대시보드 집계 조회만 소스 계정 기준으로 전환됩니다.",
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color=self._color("text_secondary", "#9ca3af"),
                    justify="left"
                ).pack(anchor="w", padx=10, pady=(0, 10))
        except Exception as e:
            print(f"ModernSettingsWindow - 데모 모드 토글 생성 실패: {e}")
            import traceback
            traceback.print_exc()

        # 안내 문구
        hint = (
            "실거래 없이 주문을 시뮬레이션합니다.\n"
            "- REAL 모드: 실제 거래소 API로 주문 전송\n"
            "- PAPER 모드: 네트워크 호출 없이 결과만 시뮬레이션"
        )
        ctk.CTkLabel(
            general_group,
            text=hint,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 8))

    def _on_capital_benchmark_change(self, value=None):
        """초기 자금 기준 변경 시 호출"""
        try:
            # 표시 레이블 업데이트
            if hasattr(self, 'capital_display_label') and hasattr(self, 'alpha_arena_capital_benchmark_var'):
                capital_benchmark_str = self.alpha_arena_capital_benchmark_var.get()
                try:
                    capital_benchmark = int(capital_benchmark_str)
                    if capital_benchmark == 10000:
                        display_text = "만불 ($10,000)"
                    elif capital_benchmark == 1000:
                        display_text = "천불 ($1,000)"
                    elif capital_benchmark == 100:
                        display_text = "백불 ($100)"
                    else:
                        display_text = f"${capital_benchmark:,}"
                    self.capital_display_label.configure(text=f"선택된 기준: {display_text}")
                except (ValueError, TypeError):
                    pass
            self._update_capital_warning()
        except Exception as e:
            print(f"초기 자금 기준 경고 업데이트 오류: {e}")

    def _validate_broadcast_replay_source(self):
        """방송 리플레이 소스 계정의 DB 경로 존재 여부를 확인한다."""
        try:
            if not hasattr(self, 'broadcast_replay_source_entry') or self.broadcast_replay_source_entry is None:
                messagebox.showwarning("검증 실패", "소스 계정 입력 필드를 찾을 수 없습니다.")
                return

            source_account = str(self.broadcast_replay_source_entry.get() or '').strip()
            if not source_account:
                messagebox.showwarning("검증 실패", "소스 계정을 입력하세요. 예: nwsoft")
                return

            from path_utils import get_db_file_path
            current_db_path = get_db_file_path()
            current_account_dir = os.path.dirname(current_db_path)
            data_root_dir = os.path.dirname(current_account_dir)
            source_db_path = os.path.join(data_root_dir, source_account, 'trading.db')

            if os.path.exists(source_db_path):
                messagebox.showinfo(
                    "소스 검증 성공",
                    f"소스 DB를 찾았습니다.\n\n계정: {source_account}\n경로: {source_db_path}"
                )
            else:
                messagebox.showwarning(
                    "소스 검증 실패",
                    f"소스 DB를 찾을 수 없습니다.\n\n계정: {source_account}\n경로: {source_db_path}"
                )
        except Exception as e:
            messagebox.showerror("검증 오류", f"소스 검증 중 오류가 발생했습니다.\n{e}")
    
    def _update_capital_warning(self):
        """초기 자금 기준에 따른 경고 메시지 업데이트"""
        try:
            if not hasattr(self, 'alpha_arena_capital_benchmark_var') or not hasattr(self, 'capital_warning_label'):
                return
            
            capital_benchmark_str = self.alpha_arena_capital_benchmark_var.get()
            try:
                capital_benchmark = int(capital_benchmark_str)
            except (ValueError, TypeError):
                capital_benchmark = 10000
            
            # 기준에 따른 표시 텍스트
            if capital_benchmark == 10000:
                display_text = "만불 ($10,000)"
            elif capital_benchmark == 1000:
                display_text = "천불 ($1,000)"
            elif capital_benchmark == 100:
                display_text = "백불 ($100)"
            else:
                display_text = f"${capital_benchmark:,}"
            
            warning_text = f"{display_text}는 Alpha Arena 판단용 벤치마크 기준입니다.\n실제 주문은 연결된 거래소 실잔고/주문가능금액/리스크 한도를 기준으로 처리됩니다.\n즉, 계좌 잔고를 {display_text}로 반드시 맞출 필요는 없습니다."
            self.capital_warning_label.configure(text=warning_text)
        except Exception as e:
            print(f"경고 메시지 업데이트 오류: {e}")

    def _on_position_mode_changed(self):
        """포지션 모드 변경 시 호출"""
        try:
            mode = self.position_mode_var.get()
            max_positions = 1 if mode == "focus" else 3

            # 현재 설정 업데이트
            self.current_settings['max_positions'] = max_positions

            # exchange_risk_overrides도 업데이트
            if 'exchange_risk_overrides' not in self.current_settings:
                self.current_settings['exchange_risk_overrides'] = {}

            # 모든 거래소에 적용
            exchanges = ['binance', 'bybit', 'okx', 'bitget', 'upbit', 'bithumb']
            for exchange in exchanges:
                if exchange not in self.current_settings['exchange_risk_overrides']:
                    self.current_settings['exchange_risk_overrides'][exchange] = {}
                self.current_settings['exchange_risk_overrides'][exchange]['max_positions'] = max_positions

            # 상태 업데이트
            mode_text = "집중모드" if mode == "focus" else "다중포지션 모드"
            print(f"포지션 모드 변경: {mode_text} (max_positions = {max_positions})")

        except Exception as e:
            print(f"포지션 모드 변경 실패: {e}")

    def create_exchange_api_tab(self):
        """거래소 API 설정 탭 - 기존 구조 정확히 재현"""
        tab = self.tabview.add("거래소 API")
        self._add_tab_save_bar(tab, "3. 거래 연결")

        # 스크롤 가능한 프레임
        scroll_frame = ctk.CTkScrollableFrame(tab)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 상단: API 키 표시 토글 (모든 거래소/OpenAI 포함)
        self.show_api_var = ctk.BooleanVar(value=False)
        show_api_chk = ctk.CTkCheckBox(
            scroll_frame,
            text="모든 API 키 표시",
            variable=self.show_api_var,
            command=lambda: self._apply_api_visibility(scope='all'),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color=self._color("text_secondary", "#9ca3af")
        )
        show_api_chk.pack(anchor="w", padx=20, pady=(0, 10))

        exchange_help_row = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        exchange_help_row.pack(fill="x", padx=20, pady=(0, 12))

        ctk.CTkButton(
            exchange_help_row,
            text="거래소 API 키 발급 안내",
            width=190,
            height=32,
            fg_color=self._color("secondary", "#4b5563"),
            hover_color=self._hover_from(self._color("secondary", "#4b5563")),
            command=lambda: self._show_api_key_help_dialog(kind='exchange'),
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            exchange_help_row,
            text="AI 설정 도우미 위치 안내",
            width=190,
            height=32,
            fg_color=self._color("secondary", "#4b5563"),
            hover_color=self._hover_from(self._color("secondary", "#4b5563")),
            command=lambda: self._show_api_key_help_dialog(kind='assistant_path'),
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            exchange_help_row,
            text="초보자 모드(전체 3단계)",
            width=190,
            height=32,
            fg_color=self._color("secondary", "#1f2937"),
            hover_color=self._hover_from(self._color("secondary", "#1f2937")),
            command=self._show_beginner_mode_guide,
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            exchange_help_row,
            text="거래소 공식 발급 바로가기",
            width=200,
            height=32,
            fg_color=self._color("secondary", "#0f766e"),
            hover_color=self._hover_from(self._color("secondary", "#0f766e")),
            command=self._show_exchange_provider_links_dialog,
        ).pack(side="left", padx=6)

        # 바이낸스 API 설정
        binance_group = ctk.CTkFrame(scroll_frame)
        binance_group.pack(fill="x", pady=(0, 20))

        binance_title = ctk.CTkLabel(
            binance_group,
            text="바이낸스 API 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        binance_title.pack(pady=(20, 15), padx=20)
        self._add_referral_entitlement_banner(binance_group, "binance")

        # API Key
        binance_api_label = ctk.CTkLabel(
            binance_group,
            text="API Key:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        binance_api_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.binance_api_key_entry = ctk.CTkEntry(
            binance_group,
            placeholder_text="바이낸스 API 키",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.binance_api_key_entry.pack(fill="x", padx=20, pady=(0, 15))

        # Secret Key
        binance_secret_label = ctk.CTkLabel(
            binance_group,
            text="Secret Key:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        binance_secret_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.binance_secret_key_entry = ctk.CTkEntry(
            binance_group,
            placeholder_text="바이낸스 시크릿 키",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.binance_secret_key_entry.pack(fill="x", padx=20, pady=(0, 20))
        # 검증 상태 표시 및 버튼 행
        binance_verify_row = ctk.CTkFrame(binance_group)
        binance_verify_row.pack(fill="x", padx=20, pady=(0, 6))
        self._binance_verify_status = ctk.StringVar(value="")
        self._binance_verify_label = ctk.CTkLabel(
            binance_verify_row,
            textvariable=self._binance_verify_status,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color=self._color("text_secondary", "#94a3b8")
        )
        self._binance_verify_label.pack(side="left", padx=(0, 10))
        self._binance_verify_button = ctk.CTkButton(
            binance_verify_row,
            text="검증",
            height=30,
            width=90,
            fg_color=self._color("primary", "#2563eb"),
            text_color="white",
            hover_color="#1d4ed8",
            command=self._on_click_verify_binance
        )
        self._binance_verify_button.pack(side="right")
        self._register_referral_api_controls(
            "binance",
            self.binance_api_key_entry,
            self.binance_secret_key_entry,
            self._binance_verify_button,
        )

        # 업비트 API 설정
        upbit_group = ctk.CTkFrame(scroll_frame)
        upbit_group.pack(fill="x", pady=(0, 20))

        upbit_title = ctk.CTkLabel(
            upbit_group,
            text="업비트 API 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        upbit_title.pack(pady=(20, 15), padx=20)

        # API Key
        upbit_api_label = ctk.CTkLabel(
            upbit_group,
            text="API Key:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        upbit_api_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.upbit_api_key_entry = ctk.CTkEntry(
            upbit_group,
            placeholder_text="업비트 API 키",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.upbit_api_key_entry.pack(fill="x", padx=20, pady=(0, 15))

        # Secret Key
        upbit_secret_label = ctk.CTkLabel(
            upbit_group,
            text="Secret Key:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        upbit_secret_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.upbit_secret_key_entry = ctk.CTkEntry(
            upbit_group,
            placeholder_text="업비트 시크릿 키",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.upbit_secret_key_entry.pack(fill="x", padx=20, pady=(0, 20))

        # 업비트 검증 상태 표시 및 버튼 행
        upbit_verify_row = ctk.CTkFrame(upbit_group)
        upbit_verify_row.pack(fill="x", padx=20, pady=(0, 6))
        self._upbit_verify_status = ctk.StringVar(value="")
        self._upbit_verify_label = ctk.CTkLabel(
            upbit_verify_row,
            textvariable=self._upbit_verify_status,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color=self._color("text_secondary", "#94a3b8")
        )
        self._upbit_verify_label.pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            upbit_verify_row,
            text="검증",
            height=30,
            width=90,
            fg_color=self._color("primary", "#2563eb"),
            text_color="white",
            hover_color="#1d4ed8",
            command=self._on_click_verify_upbit
        ).pack(side="right")

        # 빗썸 API 설정
        bithumb_group = ctk.CTkFrame(scroll_frame)
        bithumb_group.pack(fill="x", pady=(0, 20))

        bithumb_title = ctk.CTkLabel(
            bithumb_group,
            text="빗썸 API 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        bithumb_title.pack(pady=(20, 15), padx=20)

        # API Key
        bithumb_api_label = ctk.CTkLabel(
            bithumb_group,
            text="API Key:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        bithumb_api_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.bithumb_api_key_entry = ctk.CTkEntry(
            bithumb_group,
            placeholder_text="빗썸 API 키",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.bithumb_api_key_entry.pack(fill="x", padx=20, pady=(0, 15))

        # Secret Key
        bithumb_secret_label = ctk.CTkLabel(
            bithumb_group,
            text="Secret Key:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        bithumb_secret_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.bithumb_secret_key_entry = ctk.CTkEntry(
            bithumb_group,
            placeholder_text="빗썸 시크릿 키",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.bithumb_secret_key_entry.pack(fill="x", padx=20, pady=(0, 20))

        # 빗썸 검증 상태 표시 및 버튼 행
        bithumb_verify_row = ctk.CTkFrame(bithumb_group)
        bithumb_verify_row.pack(fill="x", padx=20, pady=(0, 6))
        self._bithumb_verify_status = ctk.StringVar(value="")
        self._bithumb_verify_label = ctk.CTkLabel(
            bithumb_verify_row,
            textvariable=self._bithumb_verify_status,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color=self._color("text_secondary", "#94a3b8")
        )
        self._bithumb_verify_label.pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            bithumb_verify_row,
            text="검증",
            height=30,
            width=90,
            fg_color=self._color("primary", "#2563eb"),
            text_color="white",
            hover_color="#1d4ed8",
            command=self._on_click_verify_bithumb
        ).pack(side="right")

        # 바이비트 API 설정
        bybit_group = ctk.CTkFrame(scroll_frame)
        bybit_group.pack(fill="x", pady=(0, 20))

        bybit_title = ctk.CTkLabel(
            bybit_group,
            text="바이비트 API 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        bybit_title.pack(pady=(20, 15), padx=20)
        self._add_referral_entitlement_banner(bybit_group, "bybit")

        # API Key
        bybit_api_label = ctk.CTkLabel(
            bybit_group,
            text="API Key:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        bybit_api_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.bybit_api_key_entry = ctk.CTkEntry(
            bybit_group,
            placeholder_text="바이비트 API 키",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.bybit_api_key_entry.pack(fill="x", padx=20, pady=(0, 15))

        # Secret Key
        bybit_secret_label = ctk.CTkLabel(
            bybit_group,
            text="Secret Key:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        bybit_secret_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.bybit_secret_key_entry = ctk.CTkEntry(
            bybit_group,
            placeholder_text="바이비트 시크릿 키",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.bybit_secret_key_entry.pack(fill="x", padx=20, pady=(0, 20))

        # 바이비트 검증 상태 표시 및 버튼 행
        bybit_verify_row = ctk.CTkFrame(bybit_group)
        bybit_verify_row.pack(fill="x", padx=20, pady=(0, 6))
        self._bybit_verify_status = ctk.StringVar(value="")
        self._bybit_verify_label = ctk.CTkLabel(
            bybit_verify_row,
            textvariable=self._bybit_verify_status,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color=self._color("text_secondary", "#94a3b8")
        )
        self._bybit_verify_label.pack(side="left", padx=(0, 10))
        self._bybit_verify_button = ctk.CTkButton(
            bybit_verify_row,
            text="검증",
            height=30,
            width=90,
            fg_color=self._color("primary", "#2563eb"),
            text_color="white",
            hover_color="#1d4ed8",
            command=self._on_click_verify_bybit
        )
        self._bybit_verify_button.pack(side="right")
        self._register_referral_api_controls(
            "bybit",
            self.bybit_api_key_entry,
            self.bybit_secret_key_entry,
            self._bybit_verify_button,
        )

        # OKX API 설정
        okx_group = ctk.CTkFrame(scroll_frame)
        okx_group.pack(fill="x", pady=(0, 20))

        okx_title = ctk.CTkLabel(
            okx_group,
            text="OKX API 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        okx_title.pack(pady=(20, 15), padx=20)
        self._add_referral_entitlement_banner(okx_group, "okx")

        # API Key
        okx_api_label = ctk.CTkLabel(
            okx_group,
            text="API Key:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        okx_api_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.okx_api_key_entry = ctk.CTkEntry(
            okx_group,
            placeholder_text="OKX API 키",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.okx_api_key_entry.pack(fill="x", padx=20, pady=(0, 15))

        # Secret Key
        okx_secret_label = ctk.CTkLabel(
            okx_group,
            text="Secret Key:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        okx_secret_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.okx_secret_key_entry = ctk.CTkEntry(
            okx_group,
            placeholder_text="OKX 시크릿 키",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.okx_secret_key_entry.pack(fill="x", padx=20, pady=(0, 15))

        # Passphrase
        okx_passphrase_label = ctk.CTkLabel(
            okx_group,
            text="Passphrase:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        okx_passphrase_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.okx_passphrase_entry = ctk.CTkEntry(
            okx_group,
            placeholder_text="OKX Passphrase",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.okx_passphrase_entry.pack(fill="x", padx=20, pady=(0, 20))

        # OKX 검증 상태 표시 및 버튼 행
        okx_verify_row = ctk.CTkFrame(okx_group)
        okx_verify_row.pack(fill="x", padx=20, pady=(0, 6))
        self._okx_verify_status = ctk.StringVar(value="")
        self._okx_verify_label = ctk.CTkLabel(
            okx_verify_row,
            textvariable=self._okx_verify_status,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color=self._color("text_secondary", "#94a3b8")
        )
        self._okx_verify_label.pack(side="left", padx=(0, 10))
        self._okx_verify_button = ctk.CTkButton(
            okx_verify_row,
            text="검증",
            height=30,
            width=90,
            fg_color=self._color("primary", "#2563eb"),
            text_color="white",
            hover_color="#1d4ed8",
            command=self._on_click_verify_okx
        )
        self._okx_verify_button.pack(side="right")
        self._register_referral_api_controls(
            "okx",
            self.okx_api_key_entry,
            self.okx_secret_key_entry,
            self.okx_passphrase_entry,
            self._okx_verify_button,
        )

        # 비트겟 API 설정
        bitget_group = ctk.CTkFrame(scroll_frame)
        bitget_group.pack(fill="x", pady=(0, 20))

        bitget_title = ctk.CTkLabel(
            bitget_group,
            text="비트겟 API 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        bitget_title.pack(pady=(20, 15), padx=20)
        self._add_referral_entitlement_banner(bitget_group, "bitget")

        # API Key
        bitget_api_label = ctk.CTkLabel(
            bitget_group,
            text="API Key:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        bitget_api_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.bitget_api_key_entry = ctk.CTkEntry(
            bitget_group,
            placeholder_text="비트겟 API 키",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.bitget_api_key_entry.pack(fill="x", padx=20, pady=(0, 15))

        # Secret Key
        bitget_secret_label = ctk.CTkLabel(
            bitget_group,
            text="Secret Key:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        bitget_secret_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.bitget_secret_key_entry = ctk.CTkEntry(
            bitget_group,
            placeholder_text="비트겟 시크릿 키",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.bitget_secret_key_entry.pack(fill="x", padx=20, pady=(0, 20))

        # Password (Bitget 전용)
        bitget_password_label = ctk.CTkLabel(
            bitget_group,
            text="Password:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        bitget_password_label.pack(anchor="w", padx=20, pady=(0, 5))

        self.bitget_password_entry = ctk.CTkEntry(
            bitget_group,
            placeholder_text="비트겟 비밀번호(패스프레이즈)",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.bitget_password_entry.pack(fill="x", padx=20, pady=(0, 20))

        # 비트겟 검증 상태 표시 및 버튼 행
        bitget_verify_row = ctk.CTkFrame(bitget_group)
        bitget_verify_row.pack(fill="x", padx=20, pady=(0, 6))
        self._bitget_verify_status = ctk.StringVar(value="")
        self._bitget_verify_label = ctk.CTkLabel(
            bitget_verify_row,
            textvariable=self._bitget_verify_status,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color=self._color("text_secondary", "#94a3b8")
        )
        self._bitget_verify_label.pack(side="left", padx=(0, 10))
        self._bitget_verify_button = ctk.CTkButton(
            bitget_verify_row,
            text="검증",
            height=30,
            width=90,
            fg_color=self._color("primary", "#2563eb"),
            text_color="white",
            hover_color="#1d4ed8",
            command=self._on_click_verify_bitget
        )
        self._bitget_verify_button.pack(side="right")
        self._register_referral_api_controls(
            "bitget",
            self.bitget_api_key_entry,
            self.bitget_secret_key_entry,
            self.bitget_password_entry,
            self._bitget_verify_button,
        )

        # Bitget 화이트리스트 등록을 위한 현재 공인 IP 표시
        bitget_ip_row = ctk.CTkFrame(bitget_group)
        bitget_ip_row.pack(fill="x", padx=20, pady=(0, 10))
        self._bitget_public_ip_status = ctk.StringVar(value="현재 공인 IP: 확인 중...")
        ctk.CTkLabel(
            bitget_ip_row,
            textvariable=self._bitget_public_ip_status,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color=self._color("text_secondary", "#94a3b8")
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            bitget_ip_row,
            text="IP 새로고침",
            height=28,
            width=100,
            fg_color=self._color("secondary", "#334155"),
            text_color=self._color("text_primary", "#f9fafb"),
            hover_color=self._hover_from(self._color("secondary", "#334155")),
            command=self._refresh_bitget_public_ip,
        ).pack(side="right")

        self._refresh_bitget_public_ip()

        broker_guide_row = ctk.CTkFrame(scroll_frame)
        broker_guide_row.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            broker_guide_row,
            text="증권사 연결이 안 되면 점검 가이드를 먼저 확인하세요.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#94a3b8")
        ).pack(side="left", padx=(12, 10), pady=8)

        ctk.CTkButton(
            broker_guide_row,
            text="증권 설정 사용법",
            height=30,
            fg_color=self._color("secondary", "#334155"),
            text_color=self._color("text_primary", "#f9fafb"),
            hover_color=self._hover_from(self._color("secondary", "#334155")),
            command=self._show_stock_broker_usage_help_dialog,
        ).pack(side="right", padx=(0, 8), pady=8)

        ctk.CTkButton(
            broker_guide_row,
            text="증권사 공식 발급 바로가기",
            height=30,
            fg_color=self._color("secondary", "#0f766e"),
            text_color=self._color("text_primary", "#f9fafb"),
            hover_color=self._hover_from(self._color("secondary", "#0f766e")),
            command=self._show_stock_broker_provider_links_dialog,
        ).pack(side="right", padx=(0, 8), pady=8)

        ctk.CTkButton(
            broker_guide_row,
            text="AI 연결 점검",
            height=30,
            fg_color=self._color("secondary", "#1f2937"),
            text_color=self._color("text_primary", "#f9fafb"),
            hover_color=self._hover_from(self._color("secondary", "#1f2937")),
            command=self._on_click_stock_broker_connection_checklist,
        ).pack(side="right", padx=12, pady=8)

        self.auto_stock_broker_diagnosis_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            scroll_frame,
            text="설정 저장 후 연결 위험이 보이면 자동으로 1차 진단 안내",
            variable=self.auto_stock_broker_diagnosis_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#94a3b8"),
            fg_color=self._color("primary", "#1f6feb")
        ).pack(anchor="w", padx=12, pady=(0, 14))

        # 키움증권 API 설정
        kiwoom_group = ctk.CTkFrame(scroll_frame)
        kiwoom_group.pack(fill="x", pady=(0, 20))

        kiwoom_title = ctk.CTkLabel(
            kiwoom_group,
            text="키움증권 API 설정 (Windows 전용)",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        kiwoom_title.pack(pady=(20, 5), padx=20)

        kiwoom_os_warning = ctk.CTkLabel(
            kiwoom_group,
            text="키움 OpenAPI+는 Windows 환경에서만 실제 연결됩니다. macOS/Linux에서는 mock 모드만 사용 가능합니다.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#f59e0b",
            justify="left",
            wraplength=600,
        )
        kiwoom_os_warning.pack(anchor="w", padx=20, pady=(0, 12))

        # 계정 ID
        kiwoom_id_label = ctk.CTkLabel(
            kiwoom_group,
            text="계정 ID:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        kiwoom_id_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.kiwoom_id_entry = ctk.CTkEntry(
            kiwoom_group,
            placeholder_text="키움증권 계정 ID",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8
        )
        self.kiwoom_id_entry.pack(fill="x", padx=20, pady=(0, 15))

        # 비밀번호
        kiwoom_password_label = ctk.CTkLabel(
            kiwoom_group,
            text="비밀번호:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        kiwoom_password_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.kiwoom_password_entry = ctk.CTkEntry(
            kiwoom_group,
            placeholder_text="키움증권 비밀번호",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.kiwoom_password_entry.pack(fill="x", padx=20, pady=(0, 15))

        # 공인인증서 비밀번호
        kiwoom_cert_label = ctk.CTkLabel(
            kiwoom_group,
            text="공인인증서 비밀번호:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        kiwoom_cert_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.kiwoom_cert_password_entry = ctk.CTkEntry(
            kiwoom_group,
            placeholder_text="공인인증서 비밀번호 (선택)",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.kiwoom_cert_password_entry.pack(fill="x", padx=20, pady=(0, 15))

        # 계좌번호
        kiwoom_account_label = ctk.CTkLabel(
            kiwoom_group,
            text="계좌번호:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        kiwoom_account_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.kiwoom_account_entry = ctk.CTkEntry(
            kiwoom_group,
            placeholder_text="계좌번호 (선택)",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8
        )
        self.kiwoom_account_entry.pack(fill="x", padx=20, pady=(0, 15))

        # API 타입 선택
        kiwoom_api_type_label = ctk.CTkLabel(
            kiwoom_group,
            text="API 연결 방식:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        kiwoom_api_type_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.kiwoom_api_type_combo = ctk.CTkComboBox(
            kiwoom_group,
            values=["openapi_plus", "mock"],
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            button_color=self._color("secondary", "#1f2937"),
            dropdown_fg_color=self._color("surface", "#0b1120"),
            dropdown_text_color=self._color("text_primary", "#f9fafb"),
            state="readonly"
        )
        self.kiwoom_api_type_combo.set("openapi_plus")
        self.kiwoom_api_type_combo.pack(fill="x", padx=20, pady=(0, 8))

        # API 버전 선택 (openapi 선택 시 활성화)
        kiwoom_api_version_label = ctk.CTkLabel(
            kiwoom_group,
            text="API 라이브러리/버전:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        kiwoom_api_version_label.pack(anchor="w", padx=20, pady=(5, 5))

        self.kiwoom_api_version_combo = ctk.CTkComboBox(
            kiwoom_group,
            values=["pykiwoom"],
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            button_color=self._color("secondary", "#1f2937"),
            dropdown_fg_color=self._color("surface", "#0b1120"),
            dropdown_text_color=self._color("text_primary", "#f9fafb"),
            state="readonly"
        )
        self.kiwoom_api_version_combo.set("pykiwoom")
        self.kiwoom_api_version_combo.pack(fill="x", padx=20, pady=(0, 5))

        kiwoom_api_hint = ctk.CTkLabel(
            kiwoom_group,
            text="pykiwoom: 키움 OpenAPI+ Windows 드라이버  |  mock: API 없이 테스트/데모\n실주문은 전역 LIVE와 키움 LIVE, OCX 로그인·계좌 준비상태, 가드레일을 모두 확인합니다.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left",
            wraplength=600,
        )
        kiwoom_api_hint.pack(anchor="w", padx=20, pady=(0, 20))

        # 신한증권 API 설정
        shinhan_group = ctk.CTkFrame(scroll_frame)
        shinhan_group.pack(fill="x", pady=(0, 20))

        shinhan_title = ctk.CTkLabel(
            shinhan_group,
            text="신한증권 API 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        shinhan_title.pack(pady=(20, 15), padx=20)

        # 앱 키(또는 계정 ID)
        shinhan_id_label = ctk.CTkLabel(
            shinhan_group,
            text="앱 키(app_key) 또는 계정 ID:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        shinhan_id_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.shinhan_id_entry = ctk.CTkEntry(
            shinhan_group,
            placeholder_text="신한 앱 키(app_key) 권장 (미입력 시 계정 ID 폴백)",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8
        )
        self.shinhan_id_entry.pack(fill="x", padx=20, pady=(0, 15))

        # 앱 시크릿(또는 비밀번호)
        shinhan_password_label = ctk.CTkLabel(
            shinhan_group,
            text="앱 시크릿(app_secret) 또는 비밀번호:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        shinhan_password_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.shinhan_password_entry = ctk.CTkEntry(
            shinhan_group,
            placeholder_text="신한 앱 시크릿(app_secret) 권장 (미입력 시 비밀번호 폴백)",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.shinhan_password_entry.pack(fill="x", padx=20, pady=(0, 15))

        # 공인인증서 비밀번호
        shinhan_cert_label = ctk.CTkLabel(
            shinhan_group,
            text="공인인증서 비밀번호:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        shinhan_cert_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.shinhan_cert_password_entry = ctk.CTkEntry(
            shinhan_group,
            placeholder_text="공인인증서 비밀번호 (선택)",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.shinhan_cert_password_entry.pack(fill="x", padx=20, pady=(0, 15))

        # 계좌번호
        shinhan_account_label = ctk.CTkLabel(
            shinhan_group,
            text="계좌번호:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        shinhan_account_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.shinhan_account_entry = ctk.CTkEntry(
            shinhan_group,
            placeholder_text="계좌번호 (선택)",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8
        )
        self.shinhan_account_entry.pack(fill="x", padx=20, pady=(0, 15))

        # API 타입 선택
        ctk.CTkLabel(
            shinhan_group, text="API 연결 방식:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(anchor="w", padx=20, pady=(10, 5))

        self.shinhan_api_type_combo = ctk.CTkComboBox(
            shinhan_group,
            values=["partner_rest", "mock"],
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            button_color=self._color("secondary", "#1f2937"),
            dropdown_fg_color=self._color("surface", "#0b1120"),
            dropdown_text_color=self._color("text_primary", "#f9fafb"),
            state="readonly"
        )
        self.shinhan_api_type_combo.set("partner_rest")
        self.shinhan_api_type_combo.pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkLabel(
            shinhan_group, text="API 라이브러리/버전:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(anchor="w", padx=20, pady=(5, 5))

        self.shinhan_api_version_combo = ctk.CTkComboBox(
            shinhan_group,
            values=["shinhan_openapi_v2"],
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            button_color=self._color("secondary", "#1f2937"),
            dropdown_fg_color=self._color("surface", "#0b1120"),
            dropdown_text_color=self._color("text_primary", "#f9fafb"),
            state="readonly"
        )
        self.shinhan_api_version_combo.set("shinhan_openapi_v2")
        self.shinhan_api_version_combo.pack(fill="x", padx=20, pady=(0, 5))

        ctk.CTkLabel(
            shinhan_group,
            text="shinhan_openapi_v2: 신한 공식 제휴 Open API 계약 프로필  |  mock: 테스트/데모\nXingAPI는 LS증권 API이므로 신한 선택지에서 제거했습니다. 제휴 URL·채널·엔드포인트는 계약 프로필로 적용됩니다.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 20))

        ctk.CTkLabel(
            shinhan_group, text="제휴 계약 프로필 JSON:",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb"),
        ).pack(anchor="w", padx=20, pady=(0, 5))
        self.shinhan_partner_profile_text = ctk.CTkTextbox(shinhan_group, height=150, wrap="word")
        self.shinhan_partner_profile_text.pack(fill="x", padx=20, pady=(0, 20))

        # 미래에셋 API 설정
        mirae_asset_group = ctk.CTkFrame(scroll_frame)
        mirae_asset_group.pack(fill="x", pady=(0, 20))

        mirae_asset_title = ctk.CTkLabel(
            mirae_asset_group,
            text="미래에셋 API 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        mirae_asset_title.pack(pady=(20, 15), padx=20)

        # 앱 키(또는 계정 ID)
        mirae_asset_id_label = ctk.CTkLabel(
            mirae_asset_group,
            text="앱 키(app_key) 또는 계정 ID:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        mirae_asset_id_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.mirae_asset_id_entry = ctk.CTkEntry(
            mirae_asset_group,
            placeholder_text="미래에셋 앱 키(app_key) 권장 (미입력 시 계정 ID 폴백)",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8
        )
        self.mirae_asset_id_entry.pack(fill="x", padx=20, pady=(0, 15))

        # 앱 시크릿(또는 비밀번호)
        mirae_asset_password_label = ctk.CTkLabel(
            mirae_asset_group,
            text="앱 시크릿(app_secret) 또는 비밀번호:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        mirae_asset_password_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.mirae_asset_password_entry = ctk.CTkEntry(
            mirae_asset_group,
            placeholder_text="미래에셋 앱 시크릿(app_secret) 권장 (미입력 시 비밀번호 폴백)",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.mirae_asset_password_entry.pack(fill="x", padx=20, pady=(0, 15))

        # 공인인증서 비밀번호
        mirae_asset_cert_label = ctk.CTkLabel(
            mirae_asset_group,
            text="공인인증서 비밀번호:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        mirae_asset_cert_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.mirae_asset_cert_password_entry = ctk.CTkEntry(
            mirae_asset_group,
            placeholder_text="공인인증서 비밀번호 (선택)",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.mirae_asset_cert_password_entry.pack(fill="x", padx=20, pady=(0, 15))

        # 계좌번호
        mirae_asset_account_label = ctk.CTkLabel(
            mirae_asset_group,
            text="계좌번호:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        mirae_asset_account_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.mirae_asset_account_entry = ctk.CTkEntry(
            mirae_asset_group,
            placeholder_text="계좌번호 (선택)",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8
        )
        self.mirae_asset_account_entry.pack(fill="x", padx=20, pady=(0, 15))

        # API 타입 선택
        ctk.CTkLabel(
            mirae_asset_group, text="API 연결 방식:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(anchor="w", padx=20, pady=(10, 5))

        self.mirae_asset_api_type_combo = ctk.CTkComboBox(
            mirae_asset_group,
            values=["partner_rest", "mock"],
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            button_color=self._color("secondary", "#1f2937"),
            dropdown_fg_color=self._color("surface", "#0b1120"),
            dropdown_text_color=self._color("text_primary", "#f9fafb"),
            state="readonly"
        )
        self.mirae_asset_api_type_combo.set("partner_rest")
        self.mirae_asset_api_type_combo.pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkLabel(
            mirae_asset_group, text="API 라이브러리/버전:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(anchor="w", padx=20, pady=(5, 5))

        self.mirae_asset_api_version_combo = ctk.CTkComboBox(
            mirae_asset_group,
            values=["mirae_partner_profile"],
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            button_color=self._color("secondary", "#1f2937"),
            dropdown_fg_color=self._color("surface", "#0b1120"),
            dropdown_text_color=self._color("text_primary", "#f9fafb"),
            state="readonly"
        )
        self.mirae_asset_api_version_combo.set("mirae_partner_profile")
        self.mirae_asset_api_version_combo.pack(fill="x", padx=20, pady=(0, 5))

        ctk.CTkLabel(
            mirae_asset_group,
            text="mirae_partner_profile: 미래에셋 제휴 계약에서 발급된 URL·인증·엔드포인트 적용\n한국투자 KIS 경로는 미래에셋에서 완전히 분리했습니다. mock은 테스트/데모 전용입니다.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 20))

        ctk.CTkLabel(
            mirae_asset_group, text="제휴 계약 프로필 JSON:",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb"),
        ).pack(anchor="w", padx=20, pady=(0, 5))
        self.mirae_partner_profile_text = ctk.CTkTextbox(mirae_asset_group, height=150, wrap="word")
        self.mirae_partner_profile_text.pack(fill="x", padx=20, pady=(0, 20))

        # 한국투자증권 API 설정
        korea_investment_group = ctk.CTkFrame(scroll_frame)
        korea_investment_group.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            korea_investment_group,
            text="한국투자증권 API 설정 (KIS)",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(pady=(20, 15), padx=20)

        ctk.CTkLabel(
            korea_investment_group,
            text="앱 키(app_key) 또는 계정 ID:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(anchor="w", padx=20, pady=(10, 5))

        self.korea_investment_id_entry = ctk.CTkEntry(
            korea_investment_group,
            placeholder_text="한국투자증권 앱 키(app_key) 권장 (미입력 시 계정 ID 폴백)",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8
        )
        self.korea_investment_id_entry.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            korea_investment_group,
            text="앱 시크릿(app_secret) 또는 비밀번호:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(anchor="w", padx=20, pady=(10, 5))

        self.korea_investment_password_entry = ctk.CTkEntry(
            korea_investment_group,
            placeholder_text="한국투자증권 앱 시크릿(app_secret) 권장 (미입력 시 비밀번호 폴백)",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.korea_investment_password_entry.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            korea_investment_group,
            text="공인인증서 비밀번호:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(anchor="w", padx=20, pady=(10, 5))

        self.korea_investment_cert_password_entry = ctk.CTkEntry(
            korea_investment_group,
            placeholder_text="공인인증서 비밀번호 (선택)",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8,
            show="*"
        )
        self.korea_investment_cert_password_entry.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            korea_investment_group,
            text="계좌번호:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(anchor="w", padx=20, pady=(10, 5))

        self.korea_investment_account_entry = ctk.CTkEntry(
            korea_investment_group,
            placeholder_text="계좌번호 (선택)",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8
        )
        self.korea_investment_account_entry.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            korea_investment_group,
            text="API 연결 방식:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(anchor="w", padx=20, pady=(10, 5))

        self.korea_investment_api_type_combo = ctk.CTkComboBox(
            korea_investment_group,
            values=["rest", "mock"],
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            button_color=self._color("secondary", "#1f2937"),
            dropdown_fg_color=self._color("surface", "#0b1120"),
            dropdown_text_color=self._color("text_primary", "#f9fafb"),
            state="readonly"
        )
        self.korea_investment_api_type_combo.set("rest")
        self.korea_investment_api_type_combo.pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkLabel(
            korea_investment_group,
            text="API 라이브러리/버전:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(anchor="w", padx=20, pady=(5, 5))

        self.korea_investment_api_version_combo = ctk.CTkComboBox(
            korea_investment_group,
            values=["kis_openapi_v1"],
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            button_color=self._color("secondary", "#1f2937"),
            dropdown_fg_color=self._color("surface", "#0b1120"),
            dropdown_text_color=self._color("text_primary", "#f9fafb"),
            state="readonly"
        )
        self.korea_investment_api_version_combo.set("kis_openapi_v1")
        self.korea_investment_api_version_combo.pack(fill="x", padx=20, pady=(0, 5))

        ctk.CTkLabel(
            korea_investment_group,
            text="KIS Developers 공식 REST 계약(토큰·헤더·TR ID·실전/모의 서버)을 사용합니다.\n실주문은 PAPER OFF + 전역 LIVE ON + 한국투자 LIVE ON이 모두 충족될 때만 실행됩니다.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 20))

        # api_type 변경 시 api_version 목록 동기화
        self._bind_stock_api_type_events()
        self._sync_stock_api_version_options('kiwoom', preserve_value=True)
        self._sync_stock_api_version_options('shinhan', preserve_value=True)
        self._sync_stock_api_version_options('miraeAsset', preserve_value=True)
        self._sync_stock_api_version_options('koreaInvestment', preserve_value=True)

        # 안내 메시지
        info_text = """거래소 API 설정 안내

• API 키: 각 거래소에서 발급받은 API 키를 입력하세요
• Secret Key: API 키와 함께 사용되는 비밀 키입니다
• Passphrase: OKX 거래소의 경우 추가로 Passphrase가 필요합니다
• 테스트넷: 실제 거래 전에 테스트넷에서 먼저 테스트해보세요"""

        info_label = ctk.CTkLabel(
            scroll_frame,
            text=info_text,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        )
        info_label.pack(fill="x", pady=(0, 20))

        # 기본값 되돌리기 그룹은 OpenAI 탭으로 이동됨

    def create_ai_settings_tab(self):
        """AI 설정 탭 - 안전한 정보만 표시 (위험한 설정 제거)"""
        tab = self.tabview.add("AI 시스템 상태")
        self._add_tab_save_bar(tab, "7. 자동 관리 상태·진단")

        # 스크롤 가능한 프레임
        scroll_frame = ctk.CTkScrollableFrame(tab)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # AI 시스템 상태 (배지 + 카드 스타일)
        ai_status_group = ctk.CTkFrame(scroll_frame)
        ai_status_group.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(
            ai_status_group,
            text="AI 시스템 상태",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(pady=(20, 10))

        badges = [
            ("AI 자동거래", "거래 자동 실행 준비 완료"),
            ("백엔드 AI 신호", "신호 파이프라인 정상 작동"),
            ("실시간 최적화", "지표/임계값 자동 조정"),
            ("리스크 관리", "포지션/자본 관리 활성"),
        ]
        badge_keys = ['auto_trading', 'backend_signal', 'realtime_opt', 'risk_mgmt']
        grid = ctk.CTkFrame(ai_status_group, fg_color=self._color("background", "#0b1220"))
        grid.pack(pady=(0, 10))
        self._ai_badges = {}
        for i, (text, sub) in enumerate(badges):
            cell = ctk.CTkFrame(grid, fg_color=self._color("surface", "#0b1120"), corner_radius=12)
            cell.grid(row=i // 2, column=i % 2, padx=8, pady=8, sticky="ew")
            lbl = ctk.CTkLabel(cell, text=f"⏳ {text}", text_color=self._color("text_secondary", "#94a3b8"), font=ctk.CTkFont(size=14, weight="bold"))
            lbl.pack(padx=14, pady=(10,2))
            sub_lbl = ctk.CTkLabel(cell, text=sub, text_color=self._color("text_secondary", "#94a3b8"), font=ctk.CTkFont(size=12))
            sub_lbl.pack(padx=14, pady=(0,10))
            self._ai_badges[badge_keys[i]] = (lbl, sub_lbl)

        # AI 자동 최적화 시스템 (카드)
        ai_auto_group = ctk.CTkFrame(scroll_frame, corner_radius=12)
        ai_auto_group.pack(fill="x", pady=(0, 20))

        ai_auto_title = ctk.CTkLabel(
            ai_auto_group,
            text="AI 자동 최적화 시스템",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        ai_auto_title.pack(pady=(20, 15))

        auto_info_text = (
            "AI가 자동으로 최적화하는 항목들:\n\n"
            "• 지표 기간 (RSI/MA/BB) — 실시간 조정\n"
            "• 모멘텀/거래량/신호 임계값 — 실시간 조정\n"
            "• 시장 국면별 전략 선택 — 실시간 조정\n\n"
            "이 항목들은 AI가 관리합니다 (수동 변경 금지)."
        )

        auto_info_label = ctk.CTkLabel(
            ai_auto_group,
            text=auto_info_text,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="normal"),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="center"
        )
        auto_info_label.pack(pady=(0, 20))

        # 경고 메시지 (카드)
        warning_group = ctk.CTkFrame(scroll_frame, corner_radius=12)
        warning_group.pack(fill="x", pady=(0, 20))

        warning_title = ctk.CTkLabel(
            warning_group,
            text="ℹ중요 안내",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        warning_title.pack(pady=(20, 15))

        warning_text = """초보자가 AI 분석 파라미터를 수동으로 변경하면:

AI 최적화 시스템과 충돌 발생
거래 성과 급격히 악화 가능
시스템 안정성 저하
예상치 못한 손실 발생 가능

안전한 사용법:
   - API 키만 정확히 입력
   - 거래소만 선택
   - 나머지는 AI가 자동 처리"""

        warning_label = ctk.CTkLabel(
            warning_group,
            text=warning_text,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="normal"),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="center"
        )
        warning_label.pack(pady=(0, 20))

        # 상태 타이머 시작 (설정창 내부 배지만 업데이트)
        try:
            self._start_ai_status_timer()
        except Exception:
            pass

        # 시장 국면 자동 보정 설정
        try:
            regime_group = ctk.CTkFrame(scroll_frame, corner_radius=12)
            regime_group.pack(fill="x", pady=(0, 20))

            regime_title = ctk.CTkLabel(
                regime_group,
                text="시장 국면 자동 보정",
                font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
                text_color=self._color("text_primary", "#f9fafb")
            )
            regime_title.pack(pady=(20, 10), padx=20, anchor="w")

            self.dynamic_thresholds_var = ctk.BooleanVar(value=True)
            dynamic_chk = ctk.CTkCheckBox(
                regime_group,
                text="시장 국면 자동 보정 활성화",
                variable=self.dynamic_thresholds_var,
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
                text_color=self._color("text_primary", "#f9fafb")
            )
            dynamic_chk.pack(anchor="w", padx=20, pady=(5, 10))

            regime_desc = ctk.CTkLabel(
                regime_group,
                text="LOW/NORMAL/HIGH 국면을 자동 판별해 진입 임계값을 조정합니다.\nHIGH 배율을 올리면 급변장에 더 보수적으로 진입하고, 내리면 진입 빈도가 증가할 수 있습니다.",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=self._color("text_secondary", "#9ca3af"),
                justify="left"
            )
            regime_desc.pack(anchor="w", padx=20, pady=(0, 10))

            # High 판정 배율 입력
            high_mult_label = ctk.CTkLabel(
                regime_group,
                text="HIGH 판정 배율 (기본 1.5):",
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                text_color=self._color("text_primary", "#f9fafb")
            )
            high_mult_label.pack(anchor="w", padx=20, pady=(0, 5))

            self.dynamic_high_mult_entry = ctk.CTkEntry(
                regime_group,
                placeholder_text="1.5",
                height=36,
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
                fg_color=self._color("background", "#050a13"),
                text_color=self._color("text_primary", "#f9fafb"),
                border_color=self._color("secondary", "#1f2937"),
                border_width=2,
                corner_radius=8
            )
            self.dynamic_high_mult_entry.pack(fill="x", padx=20, pady=(0, 10))

            # 기본값 되돌리기 (AI 탭 내 위치 이동)
            reset_card = ctk.CTkFrame(regime_group, corner_radius=12)
            reset_card.pack(fill="x", padx=20, pady=(10, 10))
            ctk.CTkLabel(
                reset_card,
                text="환경설정 기본값 되돌리기",
                font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                text_color=self._color("text_primary", "#f9fafb")
            ).pack(pady=(12, 4))
            ctk.CTkLabel(
                reset_card,
                text="AI 변경 등으로 설정이 꼬였을 때 초기값으로 복원합니다.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=self._color("text_secondary", "#9ca3af"),
                justify="center"
            ).pack()
            ctk.CTkButton(
                reset_card,
                text="기본값으로 되돌리기",
                height=36,
                width=200,
                fg_color=self._color("warning", "#f59e0b"),
                text_color="white",
                hover_color="#d97706",
                command=self.reset_settings
            ).pack(pady=(8, 8))
        except Exception as e:
            print(f"시장 국면 자동 보정 UI 생성 실패: {e}")

    # 테마 설정 탭 완전 제거 - 고정 스킨 사용으로 불필요

    def _start_ai_status_timer(self):
        """AI 상태 배지 실시간 갱신(1초 주기). 실패 시 조용히 무시"""
        try:
            if hasattr(self, '_ai_status_timer') and self._ai_status_timer:
                self.root.after_cancel(self._ai_status_timer)
        except Exception:
            pass
        self._ai_status_timer = self.root.after(1000, self._update_ai_status_badges)

    def _update_ai_status_badges(self):
        try:
            parent = getattr(self, 'parent', None)
            main_app = getattr(parent, 'main_app', None) if parent else None
            success = self._color('success', '#22c55e')
            danger = self._color('danger', '#ef4444')

            # 상태 수집 (널 가드 포함)
            # 1) 자동거래 추정
            auto_trading_enabled = True
            try:
                val = getattr(main_app, 'auto_trading_enabled', None)
                if isinstance(val, bool):
                    auto_trading_enabled = val
            except Exception:
                pass

            # 2) 백엔드 AI 신호 관리자 러닝 여부
            backend_running = False
            try:
                mgr = getattr(main_app, 'api_signal_manager', None)
                backend_running = bool(mgr and getattr(mgr, 'running', False))
            except Exception:
                backend_running = False

            # 3) 실시간 최적화(옵티마이저/UM 존재 여부)
            realtime_opt = False
            try:
                um = getattr(main_app, 'unified_manager', None)
                realtime_opt = bool(um)
            except Exception:
                realtime_opt = False

            # 4) 리스크 관리자 존재 여부
            risk_mgmt = False
            try:
                risk_mgmt = bool(getattr(main_app, 'risk_manager', None))
            except Exception:
                risk_mgmt = False

            states = {
                'auto_trading': auto_trading_enabled,
                'backend_signal': backend_running,
                'realtime_opt': realtime_opt,
                'risk_mgmt': risk_mgmt,
            }

            # 배지 컬러/텍스트 갱신
            for key, ok in states.items():
                lbl_pair = self._ai_badges.get(key)
                if not lbl_pair:
                    continue
                lbl, sub = lbl_pair
                try:
                    lbl.configure(text=(f"{lbl.cget('text').replace('⏳ ', '').replace('', '').replace('', '')}" if ok else f"{lbl.cget('text').replace('⏳ ', '').replace('', '').replace('', '')}"),
                                  text_color=(success if ok else danger))
                except Exception:
                    pass
        except Exception:
            pass
        # 재스케줄
        try:
            self._ai_status_timer = self.root.after(1000, self._update_ai_status_badges)
        except Exception:
            pass

    def create_exchange_selection_tab(self):
        """거래소 선택 탭 - 기존 구조 정확히 재현"""
        tab = self.tabview.add("거래소 선택")
        self._add_tab_save_bar(tab, "2. 운용 범위·주문 권한")

        # 스크롤 가능한 프레임
        scroll_frame = ctk.CTkScrollableFrame(tab)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 제목
        title_label = ctk.CTkLabel(
            scroll_frame,
            text="2. 운용 범위·주문 권한",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        title_label.pack(pady=(0, 20))

        # 설명
        description_text = """거래소 선택 안내

• 현재 지원: 바이낸스, 업비트, 빗썸, 바이비트, OKX, 비트겟
• 다중 선택: 여러 거래소를 동시에 선택할 수 있습니다
• API 키: 공개 시세·분석은 지원 거래소에서 키 없이 가능할 수 있으며, 실잔고·포지션·실주문에는 유효한 키가 필요합니다
• 선물 거래: 바이낸스, 바이비트, OKX, 비트겟
• 현물 거래: 업비트, 빗썸
• 핵심: 위 선택은 관찰·분석 범위이고, 아래 선택만 신규 실주문 권한입니다"""

        description_label = ctk.CTkLabel(
            scroll_frame,
            text=description_text,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        )
        description_label.pack(fill="x", pady=(0, 20))

        # 두 칼럼 컨테이너
        columns = ctk.CTkFrame(scroll_frame)
        columns.pack(fill="both", expand=True)

        # 국내 거래소 그룹 (좌측)
        domestic_group = ctk.CTkFrame(columns)
        domestic_group.pack(side="left", fill="both", expand=True, padx=(0,10), pady=(0, 20))

        domestic_title = ctk.CTkLabel(
            domestic_group,
            text="국내 거래소",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        domestic_title.pack(pady=(20, 15), padx=20)

        # 거래소 선택 (체크박스 - 다중 선택) - 초기값은 나중에 load_current_settings에서 설정
        self.exchange_vars = {
            'binance': ctk.BooleanVar(value=False),
            'upbit': ctk.BooleanVar(value=False),
            'bithumb': ctk.BooleanVar(value=False),
            'bybit': ctk.BooleanVar(value=False),
            'okx': ctk.BooleanVar(value=False),
            'bitget': ctk.BooleanVar(value=False)
        }

        # 업비트
        self.upbit_radio = ctk.CTkCheckBox(
            domestic_group,
            text="업비트 (Upbit)",
            variable=self.exchange_vars['upbit'],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            text_color=self._color("text_primary", "#f9fafb"),
            fg_color=self._color("primary", "#1f6feb")
        )
        self.upbit_radio.pack(anchor="w", padx=20, pady=8)

        # 빗썸
        self.bithumb_radio = ctk.CTkCheckBox(
            domestic_group,
            text="빗썸 (Bithumb)",
            variable=self.exchange_vars['bithumb'],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            text_color=self._color("text_primary", "#f9fafb"),
            fg_color=self._color("primary", "#1f6feb")
        )
        self.bithumb_radio.pack(anchor="w", padx=20, pady=8)

        # 해외 거래소 그룹 (우측)
        foreign_group = ctk.CTkFrame(columns)
        foreign_group.pack(side="left", fill="both", expand=True, padx=(10,0), pady=(0, 20))

        foreign_title = ctk.CTkLabel(
            foreign_group,
            text="해외 거래소",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        foreign_title.pack(pady=(20, 15), padx=20)

        # 바이낸스
        self.binance_radio = ctk.CTkCheckBox(
            foreign_group,
            text="바이낸스 (Binance) - 선물",
            variable=self.exchange_vars['binance'],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            text_color=self._color("text_primary", "#f9fafb"),
            fg_color=self._color("primary", "#1f6feb")
        )
        self.binance_radio.pack(anchor="w", padx=20, pady=8)
        self._register_referral_selection_controls("binance", self.binance_radio)

        # 바이비트
        self.bybit_radio = ctk.CTkCheckBox(
            foreign_group,
            text="바이비트 (Bybit) - 선물",
            variable=self.exchange_vars['bybit'],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            text_color=self._color("text_primary", "#f9fafb"),
            fg_color=self._color("primary", "#1f6feb")
        )
        self.bybit_radio.pack(anchor="w", padx=20, pady=8)
        self._register_referral_selection_controls("bybit", self.bybit_radio)

        # OKX
        self.okx_radio = ctk.CTkCheckBox(
            foreign_group,
            text="OKX - 선물",
            variable=self.exchange_vars['okx'],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            text_color=self._color("text_primary", "#f9fafb"),
            fg_color=self._color("primary", "#1f6feb")
        )
        self.okx_radio.pack(anchor="w", padx=20, pady=8)
        self._register_referral_selection_controls("okx", self.okx_radio)

        # 비트겟
        self.bitget_radio = ctk.CTkCheckBox(
            foreign_group,
            text="비트겟 (Bitget) - 선물",
            variable=self.exchange_vars['bitget'],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            text_color=self._color("text_primary", "#f9fafb"),
            fg_color=self._color("primary", "#1f6feb")
        )
        self.bitget_radio.pack(anchor="w", padx=20, pady=8)
        self._register_referral_selection_controls("bitget", self.bitget_radio)

        trade_scope_group = ctk.CTkFrame(scroll_frame)
        trade_scope_group.pack(fill="x", padx=0, pady=(0, 20))
        ctk.CTkLabel(
            trade_scope_group,
            text="실제 주문 실행 거래소 (신규 진입 허용)",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb"),
        ).pack(anchor="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(
            trade_scope_group,
            text=(
                "위의 ‘거래소 선택’만 체크해도 시작 후 시세 수집·코인 선정·AI 분석·학습·잔고/포지션 조회가 동작하며 "
                "신규 실주문은 0건입니다. 그중 신규 진입까지 허용할 거래소만 아래에서 추가 선택하세요. "
                "v3.9.0.4 최초 실행은 과도기 자동복사 여부를 알 수 없는 기존 주문 목록을 해제하므로, LIVE 사용자는 여기서 다시 선택하고 저장해야 합니다. "
                "기존 포지션 조회·보호와 API 키·회원등급·손실한도·주문 가드레일은 계속 적용됩니다."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left",
            wraplength=900,
        ).pack(anchor="w", padx=20, pady=(0, 8))
        trade_grid = ctk.CTkFrame(trade_scope_group, fg_color="transparent")
        trade_grid.pack(fill="x", padx=16, pady=(0, 14))
        self.trade_exchange_vars = {
            key: ctk.BooleanVar(value=False)
            for key in ("binance", "upbit", "bithumb", "bybit", "okx", "bitget")
        }
        trade_labels = {
            "binance": "Binance 주문",
            "bybit": "Bybit 주문",
            "okx": "OKX 주문",
            "bitget": "Bitget 주문",
            "upbit": "Upbit 주문",
            "bithumb": "Bithumb 주문",
        }
        self.trade_exchange_checks: Dict[str, Any] = {}
        for index, key in enumerate(("binance", "bybit", "okx", "bitget", "upbit", "bithumb")):
            checkbox = ctk.CTkCheckBox(
                trade_grid,
                text=trade_labels[key],
                variable=self.trade_exchange_vars[key],
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=self._color("text_primary", "#f9fafb"),
                fg_color=self._color("primary", "#1f6feb"),
            )
            checkbox.grid(row=index // 3, column=index % 3, sticky="w", padx=8, pady=6)
            self.trade_exchange_checks[key] = checkbox
            if key in {"binance", "bybit", "okx", "bitget"}:
                self._register_referral_selection_controls(key, checkbox)
        for column in range(3):
            trade_grid.grid_columnconfigure(column, weight=1)
        trade_actions = ctk.CTkFrame(trade_scope_group, fg_color="transparent")
        trade_actions.pack(fill="x", padx=20, pady=(0, 14))
        ctk.CTkButton(
            trade_actions,
            text="활성 거래소를 주문 대상으로 선택",
            width=230,
            height=32,
            command=self._select_enabled_trade_exchanges,
        ).pack(side="left")
        ctk.CTkButton(
            trade_actions,
            text="주문 선택 모두 해제",
            width=160,
            height=32,
            fg_color="#475569",
            hover_color="#64748b",
            command=self._clear_trade_exchanges,
        ).pack(side="left", padx=8)
        ctk.CTkLabel(
            trade_actions,
            text="아래를 비우면 모든 활성 거래소가 학습 전용으로 시작됩니다. ‘설정 저장’ 후 다음 실행부터 적용됩니다.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=self._color("warning", "#fbbf24"),
        ).pack(side="left", padx=8)

        multi_venue_row = ctk.CTkFrame(trade_scope_group, fg_color="#0f172a", corner_radius=10)
        multi_venue_row.pack(fill="x", padx=20, pady=(0, 14))
        ctk.CTkLabel(
            multi_venue_row,
            text="같은 투자 기회가 여러 거래소에서 발생할 때",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb"),
        ).pack(side="left", padx=(12, 8), pady=10)
        self.multi_venue_mode_combo = ctk.CTkComboBox(
            multi_venue_row,
            values=[
                "선택한 거래소에서 각각 실행 (권장)",
                "총위험을 거래소별로 분할",
                "우선순위 한 곳만 실행",
            ],
            width=270,
            height=34,
        )
        self.multi_venue_mode_combo.set("선택한 거래소에서 각각 실행 (권장)")
        self.multi_venue_mode_combo.pack(side="left", pady=10)
        ctk.CTkLabel(
            multi_venue_row,
            text=(
                "BTC 신호를 Bitget·OKX에서 각각 실행하는 것은 정상 병렬 실행입니다. "
                "같은 거래소·계좌에 같은 신호가 반복 제출될 때만 중복으로 차단합니다. "
                "한 곳만 실행은 저장된 비용 우선순위가 없으면 실제 주문 목록의 첫 번째 대상을 사용합니다."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#93c5fd",
            justify="left",
            wraplength=510,
        ).pack(side="left", padx=12, pady=10)

        # 주식/증권사 선택 섹션 (기존 거래소 선택 탭에 추가)
        stock_separator = ctk.CTkFrame(scroll_frame, height=2, fg_color=self._color("secondary", "#1f2937"))
        stock_separator.pack(fill="x", padx=20, pady=(20, 20))

        stock_title = ctk.CTkLabel(
            scroll_frame,
            text="주식/증권사 선택",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        stock_title.pack(pady=(0, 20))

        stock_description = ctk.CTkLabel(
            scroll_frame,
            text="증권사 선택 안내\n\n• 현재 구현: 키움증권, 신한증권, 미래에셋, 한국투자증권 (4개)\n• 다중 증권사 선택 가능 (동시 운영)\n• API 키는 각 증권사별 입력 필드에서 설정\n• 주식 및 ETF 거래를 지원합니다\n• 주식: 개별 기업 종목 거래 / ETF: 지수·섹터를 묶은 상품 거래\n• 주문 경로는 유사하지만, AI 분석 문맥(리스크/괴리율/NAV)은 다르게 처리됩니다\n• 실제 연결 가능 여부는 증권사 OpenAPI 권한(개인/법인/제휴 정책)에 따라 달라집니다\n• 아래 표시 모드에서 통합 / 주식만 / ETF만 보기를 선택할 수 있습니다",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        )
        stock_description.pack(fill="x", pady=(0, 20))

        quick_path_guide = ctk.CTkLabel(
            scroll_frame,
            text="빠른 위치 안내: ① 거래소 API 탭에서 증권사 API 입력/저장 → ② 현재 탭 아래 '증권 자동매매 제어'에서 실주문/STOP 정책 설정",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self._color("warning", "#f59e0b"),
            justify="left",
            wraplength=760
        )
        quick_path_guide.pack(fill="x", padx=20, pady=(0, 14))

        # 증권사 선택 (체크박스 - 다중 선택) - 초기값은 나중에 load_current_settings에서 설정
        self.stock_broker_vars = {
            'kiwoom': ctk.BooleanVar(value=False),
            'shinhan': ctk.BooleanVar(value=False),
            'miraeAsset': ctk.BooleanVar(value=False),
            'koreaInvestment': ctk.BooleanVar(value=False),
        }

        stock_brokers_frame = ctk.CTkFrame(scroll_frame)
        stock_brokers_frame.pack(fill="x", padx=20, pady=(0, 20))

        # 키움증권
        self.kiwoom_checkbox = ctk.CTkCheckBox(
            stock_brokers_frame,
            text="키움증권 (Kiwoom) - 주식/ETF",
            variable=self.stock_broker_vars['kiwoom'],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            text_color=self._color("text_primary", "#f9fafb"),
            fg_color=self._color("primary", "#1f6feb")
        )
        self.kiwoom_checkbox.pack(anchor="w", padx=20, pady=8)

        # 신한증권
        self.shinhan_checkbox = ctk.CTkCheckBox(
            stock_brokers_frame,
            text="신한증권 (Shinhan) - 주식/ETF",
            variable=self.stock_broker_vars['shinhan'],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            text_color=self._color("text_primary", "#f9fafb"),
            fg_color=self._color("primary", "#1f6feb")
        )
        self.shinhan_checkbox.pack(anchor="w", padx=20, pady=8)

        # 미래에셋
        self.mirae_asset_checkbox = ctk.CTkCheckBox(
            stock_brokers_frame,
            text="미래에셋 (MiraeAsset) - 주식/ETF",
            variable=self.stock_broker_vars['miraeAsset'],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            text_color=self._color("text_primary", "#f9fafb"),
            fg_color=self._color("primary", "#1f6feb")
        )
        self.mirae_asset_checkbox.pack(anchor="w", padx=20, pady=8)

        # 한국투자증권
        self.korea_investment_checkbox = ctk.CTkCheckBox(
            stock_brokers_frame,
            text="한국투자증권 (Korea Investment / KIS) - 주식/ETF",
            variable=self.stock_broker_vars['koreaInvestment'],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            text_color=self._color("text_primary", "#f9fafb"),
            fg_color=self._color("primary", "#1f6feb")
        )
        self.korea_investment_checkbox.pack(anchor="w", padx=20, pady=8)

        self.stock_broker_live_vars = {
            key: ctk.BooleanVar(value=False) for key in self.stock_broker_vars
        }
        ctk.CTkLabel(
            stock_brokers_frame,
            text="증권사별 LIVE 주문 권한 (전역 LIVE 권한과 모두 켜져야 실행)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#f59e0b",
        ).pack(anchor="w", padx=20, pady=(14, 6))
        for broker_key, broker_label in (
            ('kiwoom', '키움 LIVE 허용'),
            ('shinhan', '신한 LIVE 허용'),
            ('miraeAsset', '미래에셋 LIVE 허용'),
            ('koreaInvestment', '한국투자 KIS LIVE 허용'),
        ):
            ctk.CTkCheckBox(
                stock_brokers_frame,
                text=broker_label,
                variable=self.stock_broker_live_vars[broker_key],
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color="#f59e0b",
                fg_color="#d97706",
            ).pack(anchor="w", padx=40, pady=5)

        stock_mode_frame = ctk.CTkFrame(scroll_frame)
        stock_mode_frame.pack(fill="x", padx=20, pady=(0, 20))

        stock_mode_title = ctk.CTkLabel(
            stock_mode_frame,
            text="증권 표시 모드",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        stock_mode_title.pack(anchor="w", padx=20, pady=(16, 6))

        stock_mode_desc = ctk.CTkLabel(
            stock_mode_frame,
            text="종목 검색, 상단 종목 미리보기, AI 증권 컨텍스트에서 통합 / 주식만 / ETF만 보기를 적용합니다.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        )
        stock_mode_desc.pack(anchor="w", padx=20, pady=(0, 10))

        self.stock_asset_mode_var = ctk.StringVar(value="통합")
        stock_mode_combo = ctk.CTkComboBox(
            stock_mode_frame,
            values=["통합", "주식만", "ETF만"],
            variable=self.stock_asset_mode_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            width=220
        )
        stock_mode_combo.pack(anchor="w", padx=20, pady=(0, 16))

        # ===== 주문 가드레일 섹션 =====
        guardrail_frame = ctk.CTkFrame(scroll_frame)
        guardrail_frame.pack(fill="x", padx=20, pady=(0, 20))

        guardrail_title = ctk.CTkLabel(
            guardrail_frame,
            text="증권 주문 가드레일",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        guardrail_title.pack(anchor="w", padx=20, pady=(16, 6))

        ctk.CTkButton(
            guardrail_frame,
            text="숫자 설명",
            width=110,
            height=28,
            fg_color=self._color("secondary", "#334155"),
            text_color=self._color("text_primary", "#f9fafb"),
            hover_color=self._hover_from(self._color("secondary", "#334155")),
            command=self._show_stock_guardrail_help_dialog,
        ).pack(anchor="e", padx=20, pady=(0, 6))

        guardrail_desc = ctk.CTkLabel(
            guardrail_frame,
            text="주문 전 시장시간·수량·금액·일일한도를 검사하는 안전벨트입니다. 이 숫자는 AI 수익률 설정이 아니라 과대주문 방지용 브레이크입니다.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left",
            wraplength=700,
        )
        guardrail_desc.pack(anchor="w", padx=20, pady=(0, 10))

        g_row1 = ctk.CTkFrame(guardrail_frame, fg_color="transparent")
        g_row1.pack(fill="x", padx=20, pady=(0, 8))

        # 가드레일 활성화
        self.guardrail_enabled_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            g_row1,
            text="가드레일 활성화",
            variable=self.guardrail_enabled_var,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self._color("text_primary", "#f9fafb"),
            fg_color=self._color("primary", "#1f6feb")
        ).pack(side="left", padx=(0, 24))

        # 장시간 강제
        self.guardrail_market_hours_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            g_row1,
            text="정규장 시간만 허용",
            variable=self.guardrail_market_hours_var,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self._color("text_primary", "#f9fafb"),
            fg_color=self._color("primary", "#1f6feb")
        ).pack(side="left", padx=(0, 24))

        # 주문타입 허용
        self.guardrail_allow_market_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            g_row1,
            text="시장가 허용",
            variable=self.guardrail_allow_market_var,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self._color("text_primary", "#f9fafb"),
            fg_color=self._color("primary", "#1f6feb")
        ).pack(side="left")

        g_row2 = ctk.CTkFrame(guardrail_frame, fg_color="transparent")
        g_row2.pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkLabel(
            g_row2, text="최대 수량",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self._color("text_secondary", "#9ca3af"),
            width=80, anchor="w"
        ).pack(side="left")
        self.guardrail_max_qty_entry = ctk.CTkEntry(
            g_row2,
            placeholder_text="10000",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            width=100
        )
        self.guardrail_max_qty_entry.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(
            g_row2, text="최대 금액(원)",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self._color("text_secondary", "#9ca3af"),
            width=90, anchor="w"
        ).pack(side="left")
        self.guardrail_max_value_entry = ctk.CTkEntry(
            g_row2,
            placeholder_text="50000000",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            width=120
        )
        self.guardrail_max_value_entry.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(
            g_row2, text="일일 주문 한도",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self._color("text_secondary", "#9ca3af"),
            width=90, anchor="w"
        ).pack(side="left")
        self.guardrail_daily_limit_entry = ctk.CTkEntry(
            g_row2,
            placeholder_text="20",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            width=70
        )
        self.guardrail_daily_limit_entry.pack(side="left")

        # ===== 증권 자동매매 제어 섹션 =====
        stock_ctrl_sep = ctk.CTkFrame(scroll_frame, height=2, fg_color=self._color("secondary", "#1f2937"))
        stock_ctrl_sep.pack(fill="x", padx=20, pady=(20, 10))

        stock_ctrl_frame = ctk.CTkFrame(scroll_frame)
        stock_ctrl_frame.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkLabel(
            stock_ctrl_frame,
            text="증권 자동매매 제어",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(anchor="w", padx=20, pady=(16, 4))

        ctk.CTkButton(
            stock_ctrl_frame,
            text="제어 설명",
            width=110,
            height=28,
            fg_color=self._color("secondary", "#334155"),
            text_color=self._color("text_primary", "#f9fafb"),
            hover_color=self._hover_from(self._color("secondary", "#334155")),
            command=self._show_stock_auto_trading_help_dialog,
        ).pack(anchor="e", padx=20, pady=(0, 6))

        ctk.CTkLabel(
            stock_ctrl_frame,
            text="자동 시작 여부와 실제 주문 허용 여부를 분리해 관리합니다. 실주문 허용은 전략 숫자가 아니라 실행 권한 스위치입니다.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left",
            wraplength=700,
        ).pack(anchor="w", padx=20, pady=(0, 10))

        ctrl_row1 = ctk.CTkFrame(stock_ctrl_frame, fg_color="transparent")
        ctrl_row1.pack(fill="x", padx=20, pady=(0, 8))

        # auto_start 토글
        self.stock_auto_start_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            ctrl_row1,
            text="증권 탭 진입 시 자동 시작 (auto_start)",
            variable=self.stock_auto_start_var,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self._color("text_primary", "#f9fafb"),
            fg_color=self._color("primary", "#1f6feb")
        ).pack(side="left", padx=(0, 24))

        # enable_live_order 토글
        self.stock_live_order_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            ctrl_row1,
            text="실주문 허용 (enable_stock_live_order)",
            variable=self.stock_live_order_var,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#f59e0b",
            fg_color="#d97706"
        ).pack(side="left")

        ctk.CTkLabel(
            stock_ctrl_frame,
            text=(
                "실제 주문은 PAPER OFF + 전역 실주문 허용 ON + 해당 증권사 LIVE 허용 ON + API 준비상태 정상일 때만 나갑니다. "
                "조건이 하나라도 빠지면 분석·계획(LEARNING)만 수행하며, 페이퍼 트레이딩이 ON이면 내부 가상 주문(PAPER)으로 고정됩니다."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#f59e0b",
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 10))

        # 생활금융 데이터 경로 설정
        ctk.CTkLabel(
            stock_ctrl_frame,
            text="생활금융 데이터 경로",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(anchor="w", padx=20, pady=(4, 4))

        life_path_desc = ctk.CTkLabel(
            stock_ctrl_frame,
            text="동기화 경로/백업 경로를 설정하면 생활금융 데이터 파일을 안정적으로 동기화·백업할 수 있습니다.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        )
        life_path_desc.pack(anchor="w", padx=20, pady=(0, 6))

        life_sync_row = ctk.CTkFrame(stock_ctrl_frame, fg_color="transparent")
        life_sync_row.pack(fill="x", padx=20, pady=(0, 6))
        ctk.CTkLabel(
            life_sync_row,
            text="동기화 경로",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_primary", "#f9fafb"),
            width=90
        ).pack(side="left")
        self.life_finance_sync_dir_entry = ctk.CTkEntry(
            life_sync_row,
            placeholder_text="예: /Users/<name>/SynologyDrive/LifeFinanceSync",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            height=32
        )
        self.life_finance_sync_dir_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))

        life_backup_row = ctk.CTkFrame(stock_ctrl_frame, fg_color="transparent")
        life_backup_row.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(
            life_backup_row,
            text="백업 경로",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_primary", "#f9fafb"),
            width=90
        ).pack(side="left")
        self.life_finance_backup_dir_entry = ctk.CTkEntry(
            life_backup_row,
            placeholder_text="예: /Users/<name>/SynologyDrive/LifeFinanceBackup",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            height=32
        )
        self.life_finance_backup_dir_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))

        # STOP 포지션 정책
        ctk.CTkLabel(
            stock_ctrl_frame,
            text="STOP 시 기존 포지션 처리",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(anchor="w", padx=20, pady=(4, 4))

        ctk.CTkLabel(
            stock_ctrl_frame,
            text="• 유지(권장): 신규 진입만 차단, 기존 포지션은 TP/SL 조건 도달 시 자동 청산\n"
                 "• 즉시 청산: 신규 진입 차단 + 보유 중인 모든 포지션을 시장가로 즉시 청산",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 8))

        self.stock_stop_policy_var = ctk.StringVar(value="keep_with_tp_sl")
        stop_policy_frame = ctk.CTkFrame(stock_ctrl_frame, fg_color="transparent")
        stop_policy_frame.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkRadioButton(
            stop_policy_frame,
            text="유지 (TP/SL에 맡김) — 권장",
            variable=self.stock_stop_policy_var,
            value="keep_with_tp_sl",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self._color("text_primary", "#f9fafb"),
            fg_color=self._color("primary", "#1f6feb")
        ).pack(side="left", padx=(0, 30))
        ctk.CTkRadioButton(
            stop_policy_frame,
            text="즉시 전량 청산",
            variable=self.stock_stop_policy_var,
            value="close_all",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#ef4444",
            fg_color="#ef4444"
        ).pack(side="left")

    def create_button_area(self, parent):
        """하단 버튼 영역 생성"""
        # 하단 버튼 영역 배경도 고정 배경색으로 통일
        button_frame = ctk.CTkFrame(parent, fg_color="#0b1120")
        button_frame.pack(side="bottom", fill="x", pady=(0, 6))
        compact_button_font = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")

        # 저장 버튼
        save_button = ctk.CTkButton(
            button_frame,
            text="전체 설정 저장",
            image=get_ui_icon("save", (14, 14), "#ffffff"),
            compound="left",
            height=38,
            width=142,
            font=compact_button_font,
            fg_color=self._color("success", "#10b981"),
            text_color="white",
            hover_color="#059669",
            border_width=0,
            corner_radius=8,
            command=self.save_settings
        )
        save_button.pack(side="left", padx=(0, 6))

        # 취소 버튼
        cancel_button = ctk.CTkButton(
            button_frame,
            text="취소",
            image=get_ui_icon("close", (14, 14), "#ffffff"),
            compound="left",
            height=38,
            width=90,
            font=compact_button_font,
            fg_color=self._color("danger", "#ef4444"),
            text_color="white",
            hover_color="#dc2626",
            border_width=0,
            corner_radius=8,
            command=self.cancel_settings
        )
        cancel_button.pack(side="left", padx=(0, 6))

        # 백업 복구 버튼
        restore_button = ctk.CTkButton(
            button_frame,
            text="백업에서 복구",
            height=38,
            width=132,
            font=compact_button_font,
            fg_color="#334155",
            text_color="white",
            hover_color="#475569",
            border_width=0,
            corner_radius=8,
            command=self._show_backup_restore_dialog
        )
        restore_button.pack(side="left", padx=(0, 6))

        # 기본값 복원 버튼은 OpenAI 탭 카드로 이동

    def center_window(self):
        """창을 화면 중앙에 배치"""
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (900 // 2)
        y = (self.root.winfo_screenheight() // 2) - (800 // 2)
        self.root.geometry(f"900x800+{x}+{y}")

    def _execute_callback_safe(self, settings):
        """콜백을 안전하게 실행 (오류 처리)"""
        try:
            if self.on_save_callback:
                self.on_save_callback(settings)
                print("설정 저장 콜백 호출 완료")
        except Exception as e:
            print(f"설정 저장 콜백 오류: {e}")

    def _show_backup_restore_dialog(self):
        """설정 백업 목록을 표시하고 사용자가 선택해 복구할 수 있게 한다."""
        try:
            from config.settings import list_settings_backups

            backups = list_settings_backups(limit=3)
            if not backups:
                messagebox.showinfo("백업 복구", "복구 가능한 설정 백업이 없습니다.")
                return

            dialog = ctk.CTkToplevel(self.root)
            dialog.title("설정 백업 복구")
            dialog.geometry("620x360")
            dialog.transient(self.root)
            dialog.grab_set()

            container = ctk.CTkFrame(dialog, fg_color="#0b1120")
            container.pack(fill="both", expand=True, padx=16, pady=16)

            title = ctk.CTkLabel(
                container,
                text="최근 설정 백업 (최신 3개)",
                font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
                text_color=self._color("text_primary", "#f9fafb")
            )
            title.pack(anchor="w", pady=(4, 12))

            desc = ctk.CTkLabel(
                container,
                text="복구 시 현재 설정은 자동 백업된 후 선택한 백업으로 교체됩니다.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color="#94a3b8",
                justify="left"
            )
            desc.pack(anchor="w", pady=(0, 12))

            for idx, backup_path in enumerate(backups, start=1):
                row = ctk.CTkFrame(container, fg_color="#1a2540", corner_radius=8)
                row.pack(fill="x", pady=(0, 10))

                filename = os.path.basename(backup_path)
                ts = datetime.fromtimestamp(os.path.getmtime(backup_path)).strftime("%Y-%m-%d %H:%M:%S")

                label = ctk.CTkLabel(
                    row,
                    text=f"{idx}. {filename}\n   생성시각: {ts}",
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                    text_color="#d1d5db",
                    justify="left"
                )
                label.pack(side="left", fill="x", expand=True, padx=12, pady=10)

                btn = ctk.CTkButton(
                    row,
                    text="이 백업 복구",
                    width=120,
                    height=34,
                    fg_color="#2563eb",
                    hover_color="#1d4ed8",
                    command=lambda p=backup_path, d=dialog: self._restore_backup_and_reload(p, d)
                )
                btn.pack(side="right", padx=12)

            close_btn = ctk.CTkButton(
                container,
                text="닫기",
                width=100,
                height=36,
                fg_color="#374151",
                hover_color="#4b5563",
                command=dialog.destroy
            )
            close_btn.pack(anchor="e", pady=(8, 0))

        except Exception as e:
            messagebox.showerror("백업 복구", f"백업 목록을 불러오지 못했습니다.\n\n오류: {e}")

    def _restore_backup_and_reload(self, backup_path: str, dialog=None):
        """선택한 백업을 복구하고 설정 화면/콜백을 동기화한다."""
        try:
            filename = os.path.basename(backup_path)
            confirm = messagebox.askyesno(
                "백업 복구 확인",
                f"다음 백업으로 설정을 복구할까요?\n\n{filename}\n\n"
                "현재 설정은 자동 백업 후 복구됩니다."
            )
            if not confirm:
                return

            from config.settings import restore_settings_from_backup, load_settings

            if not restore_settings_from_backup(backup_path):
                messagebox.showerror("백업 복구", "설정 복구에 실패했습니다.")
                return

            # 복구된 설정으로 UI 재로드
            self.current_settings = load_settings()
            self.load_current_settings()

            # 상위 대시보드도 즉시 동기화
            self._execute_callback_safe(self.current_settings)

            if dialog is not None:
                try:
                    dialog.destroy()
                except Exception:
                    pass

            messagebox.showinfo("백업 복구", "설정이 백업에서 복구되었습니다.")
        except Exception as e:
            messagebox.showerror("백업 복구", f"복구 중 오류가 발생했습니다.\n\n오류: {e}")

    def _get_stock_api_versions(self, broker: str, api_type: str):
        """증권사/연결방식별 API 버전 후보 목록 반환"""
        broker_map = self._STOCK_API_VERSION_OPTIONS.get(broker, {})
        return broker_map.get((api_type or 'openapi_plus').lower(), [])

    def _sync_stock_api_version_options(self, broker: str, preserve_value: bool = True):
        """api_type 선택값에 맞춰 api_version 콤보 후보를 동기화"""
        try:
            if broker == 'kiwoom':
                type_combo = getattr(self, 'kiwoom_api_type_combo', None)
                version_combo = getattr(self, 'kiwoom_api_version_combo', None)
            elif broker == 'shinhan':
                type_combo = getattr(self, 'shinhan_api_type_combo', None)
                version_combo = getattr(self, 'shinhan_api_version_combo', None)
            elif broker == 'miraeAsset':
                type_combo = getattr(self, 'mirae_asset_api_type_combo', None)
                version_combo = getattr(self, 'mirae_asset_api_version_combo', None)
            elif broker == 'koreaInvestment':
                type_combo = getattr(self, 'korea_investment_api_type_combo', None)
                version_combo = getattr(self, 'korea_investment_api_version_combo', None)
            else:
                return

            if not type_combo or not version_combo:
                return

            selected_type = (type_combo.get() or 'openapi').lower()
            allowed_versions = self._get_stock_api_versions(broker, selected_type)
            if not allowed_versions:
                allowed_versions = ['mock'] if selected_type == 'mock' else ['default']

            current_version = version_combo.get() if preserve_value else ''
            version_combo.configure(values=allowed_versions)

            if current_version in allowed_versions:
                version_combo.set(current_version)
            else:
                version_combo.set(allowed_versions[0])
        except Exception as e:
            print(f"API 버전 옵션 동기화 실패({broker}): {e}")

    def _bind_stock_api_type_events(self):
        """api_type 변경 시 api_version 후보를 동적으로 제한"""
        try:
            if hasattr(self, 'kiwoom_api_type_combo'):
                self.kiwoom_api_type_combo.configure(
                    command=lambda _: self._sync_stock_api_version_options('kiwoom', preserve_value=False)
                )
            if hasattr(self, 'shinhan_api_type_combo'):
                self.shinhan_api_type_combo.configure(
                    command=lambda _: self._sync_stock_api_version_options('shinhan', preserve_value=False)
                )
            if hasattr(self, 'mirae_asset_api_type_combo'):
                self.mirae_asset_api_type_combo.configure(
                    command=lambda _: self._sync_stock_api_version_options('miraeAsset', preserve_value=False)
                )
            if hasattr(self, 'korea_investment_api_type_combo'):
                self.korea_investment_api_type_combo.configure(
                    command=lambda _: self._sync_stock_api_version_options('koreaInvestment', preserve_value=False)
                )
        except Exception as e:
            print(f"api_type 이벤트 바인딩 실패: {e}")

    def _select_enabled_trade_exchanges(self):
        """Copy the analysis scope into the live-order draft; saving remains explicit."""
        for key, trade_var in getattr(self, 'trade_exchange_vars', {}).items():
            enabled_var = getattr(self, 'exchange_vars', {}).get(key)
            try:
                trade_var.set(bool(enabled_var and enabled_var.get()))
            except Exception:
                pass

    def _clear_trade_exchanges(self):
        for trade_var in getattr(self, 'trade_exchange_vars', {}).values():
            try:
                trade_var.set(False)
            except Exception:
                pass

    def on_exchange_changed(self, *args):
        """거래소 변경 이벤트 핸들러"""
        try:
            if hasattr(self, 'exchange_var') and self.exchange_var is not None and hasattr(self.exchange_var, 'get'):
                selected_exchange = self.exchange_var.get()
            else:
                selected_exchange = None
            print(f"거래소 변경: {selected_exchange}")
            # ExchangeManager에 거래소 변경 알림
            if hasattr(self, 'on_save_callback') and self.on_save_callback:
                self.on_save_callback('exchange_changed', selected_exchange)
        except Exception as e:
            print(f"거래소 변경 처리 오류: {e}")

    def on_closing(self):
        """X 닫기에서도 저장/폐기/계속 편집을 명시적으로 선택한다."""
        try:
            print("설정 창 닫기")
            choice = self._ask_save_on_close()
            if choice is None:
                return

            if choice is True:
                self.save_settings()
            else:
                # 화면에서 바꾼 값만 폐기하고 저장 정본으로 되돌린 뒤 숨긴다.
                self.current_settings = copy.deepcopy(self.original_settings)
                self.load_current_settings()
                self._hide_or_destroy()

        except Exception as e:
            print(f"설정 창 닫기 처리 오류: {e}")
            # 닫기 확인 실패가 프로그램 전체 종료로 이어지지 않게 한다.

    def load_current_settings(self):
        """현재 설정을 UI에 로드 - 기존 PyQt5 설정 창과 동일한 로직"""
        try:
            print(f"설정 로드 시작: {len(self.current_settings)}개 설정")
            print(f"현재 설정: {list(self.current_settings.keys())}")

            # API 설정 복원 (기존과 동일)
            binance_key = self.current_settings.get('binance_api_key', '')
            binance_secret = self.current_settings.get('binance_secret_key', '')
            profiles = self.current_settings.get("ai_provider_profiles", {})
            analyst_profile = profiles.get("analyst", {}) if isinstance(profiles, dict) else {}
            assistant_profile = profiles.get("assistant", {}) if isinstance(profiles, dict) else {}
            primary_provider = str(self.current_settings.get("ai_provider") or "openai").lower()
            analyst_provider = str(
                (analyst_profile.get("provider") if isinstance(analyst_profile, dict) else "")
                or primary_provider
            ).lower()
            assistant_provider = str(
                (assistant_profile.get("provider") if isinstance(assistant_profile, dict) else "")
                or primary_provider
            ).lower()
            active_provider = analyst_provider
            provider_label = self._AI_PROVIDER_LABELS_REVERSE().get(active_provider, "OpenAI")
            if hasattr(self, "ai_provider_var"):
                self.ai_provider_var.set(provider_label)
            self._active_ai_provider = active_provider
            credentials = self.current_settings.get("ai_credentials", {})
            if isinstance(credentials, dict):
                for credential_provider, credential_value in credentials.items():
                    if isinstance(credential_value, dict):
                        self._ai_provider_key_buffer[str(credential_provider)] = str(
                            credential_value.get("api_key") or ""
                        )
            provider_cfg = credentials.get(active_provider, {}) if isinstance(credentials, dict) else {}
            openai_key = str(
                (provider_cfg.get("api_key") if isinstance(provider_cfg, dict) else "")
                or self.current_settings.get('openai_api_key', '')
                or ""
            )
            openai_base_url = str(
                (provider_cfg.get("base_url") if isinstance(provider_cfg, dict) else "")
                or self.current_settings.get('openai_base_url', '')
                or self._AI_PROVIDER_BASE_URLS.get(active_provider, "")
            ).strip()
            self._ai_provider_key_buffer[active_provider] = openai_key

            print(f"바이낸스 키: {'설정됨' if binance_key else '없음'}")
            print(f"{provider_label} API 키: {'설정됨' if openai_key else '없음'}")

            self.binance_api_key_entry.insert(0, binance_key)
            self.binance_secret_key_entry.insert(0, binance_secret)
            self.openai_api_key_entry.insert(0, openai_key)
            if hasattr(self, "ai_api_key_label"):
                has_unresolved_reference = bool(
                    isinstance(provider_cfg, dict)
                    and provider_cfg.get("credential_ref")
                    and not openai_key
                )
                suffix = " · v3.9.0.3 키 재입력 필요" if has_unresolved_reference else ""
                self.ai_api_key_label.configure(
                    text=f"{provider_label} API Key{suffix}:"
                )
                if has_unresolved_reference:
                    print(
                        f"⚠️ {provider_label}은 v3.9.0.3 보안 저장 참조만 남아 있습니다. "
                        "AI 기능을 사용하려면 API 키를 한 번 다시 입력해 주세요."
                    )
            if hasattr(self, "ai_price_guide_label"):
                try:
                    from trading.ai.provider_catalog import format_provider_price_guide
                    self.ai_price_guide_label.configure(text=format_provider_price_guide(active_provider))
                except Exception:
                    pass
            if hasattr(self, 'openai_base_url_entry'):
                self.openai_base_url_entry.delete(0, 'end')
                self.openai_base_url_entry.insert(0, openai_base_url)

            # 애널리스트·어시스턴트·작업별 Provider/모델 복원
            analyst_label = self._AI_PROVIDER_LABELS_REVERSE().get(analyst_provider, "OpenAI")
            assistant_label = self._AI_PROVIDER_LABELS_REVERSE().get(assistant_provider, "OpenAI")
            self.ai_analyst_provider_combo.set(analyst_label)
            self.ai_assistant_provider_combo.set(assistant_label)
            self._on_assignment_provider_change("analyst")
            self._on_assignment_provider_change("assistant")
            openai_model = str(
                (analyst_profile.get("model") if isinstance(analyst_profile, dict) else "")
                or self.current_settings.get('openai_model')
                or self._AI_PROVIDER_MODELS.get(analyst_provider, self._AI_MODEL_FALLBACKS)[0]
            )
            assistant_model = str(
                (assistant_profile.get("model") if isinstance(assistant_profile, dict) else "")
                or self.current_settings.get('assistant_ai_model')
                or self._AI_PROVIDER_MODELS.get(assistant_provider, self._AI_MODEL_FALLBACKS)[0]
            )
            self.openai_model_combo.set(openai_model)
            self.assistant_ai_model_combo.set(assistant_model)

            _ai_roles = self.current_settings.get('ai_model_roles', {})
            role_widgets = {
                "frequent_cheap": ("ai_role_cheap_provider_combo", "ai_role_cheap_combo"),
                "standard": ("ai_role_standard_provider_combo", "ai_role_standard_combo"),
                "premium": ("ai_role_premium_provider_combo", "ai_role_premium_combo"),
            }
            for tier, (provider_widget, model_widget) in role_widgets.items():
                raw_route = _ai_roles.get(tier) if isinstance(_ai_roles, dict) else None
                if isinstance(raw_route, dict):
                    role_provider = str(raw_route.get("provider") or analyst_provider).lower()
                    role_model = str(raw_route.get("model") or openai_model)
                else:
                    role_provider = analyst_provider
                    role_model = str(raw_route or openai_model)
                getattr(self, provider_widget).set(
                    self._AI_PROVIDER_LABELS_REVERSE().get(role_provider, "OpenAI")
                )
                self._on_assignment_provider_change(tier)
                allowed = list(self._AI_PROVIDER_MODELS.get(role_provider, self._AI_MODEL_FALLBACKS))
                getattr(self, model_widget).set(
                    role_model if role_model in allowed else allowed[0]
                )

            if hasattr(self, "assistant_response_mode_combo"):
                response_mode_label = {
                    "saver": "문답 절약형",
                    "standard": "질문답변 표준형",
                    "premium": "분석 정밀형",
                }.get(str(self.current_settings.get("assistant_response_mode") or "standard"), "질문답변 표준형")
                self.assistant_response_mode_combo.set(response_mode_label)

            transcription_cfg = self.current_settings.get('ai_custom_transcription', {}) or {}
            if hasattr(self, 'ai_custom_transcription_enabled_var'):
                self.ai_custom_transcription_enabled_var.set(bool(transcription_cfg.get('enabled', True)))
            if hasattr(self, 'ai_custom_transcription_model_combo'):
                self.ai_custom_transcription_model_combo.set(str(transcription_cfg.get('model', 'gpt-4o-mini-transcribe')))
            if hasattr(self, 'ai_custom_transcription_minutes_combo'):
                self.ai_custom_transcription_minutes_combo.set(str(int(transcription_cfg.get('max_duration_minutes', 45) or 45)))
            if hasattr(self, 'ai_custom_transcription_mb_combo'):
                self.ai_custom_transcription_mb_combo.set(str(int(transcription_cfg.get('max_file_mb', 24) or 24)))
            runtime_cfg = self.current_settings.get('ai_custom_runtime', {}) or {}
            if hasattr(self, 'ai_custom_runtime_enabled_var'):
                self.ai_custom_runtime_enabled_var.set(bool(runtime_cfg.get('enabled', False)))
            if hasattr(self, 'ai_custom_limited_live_var'):
                self.ai_custom_limited_live_var.set(bool(runtime_cfg.get('allow_limited_live', False)))
            if hasattr(self, 'ai_custom_feature_profile_combo'):
                from trading.ai_custom_features import resolve_ai_custom_features

                feature_state = resolve_ai_custom_features(self.current_settings)
                profile_label = {
                    'beginner': '초보자', 'standard': '일반',
                    'advanced': '고급', 'lab': '실험실',
                }.get(feature_state['profile'], '일반')
                self.ai_custom_feature_profile_combo.set(profile_label)
                for key, value in feature_state['features'].items():
                    variable = getattr(self, 'ai_custom_feature_vars', {}).get(key)
                    if variable is not None:
                        variable.set(bool(value))

            if hasattr(self, 'assistant_apply_mode_combo'):
                self.assistant_apply_mode_combo.set("사용자 최종확인")

            voice_cfg = self.current_settings.get('assistant_voice', {}) or {}
            if hasattr(self, 'assistant_voice_enabled_var'):
                self.assistant_voice_enabled_var.set(bool(voice_cfg.get('enabled', False)))
            if hasattr(self, 'assistant_voice_auto_tts_var'):
                self.assistant_voice_auto_tts_var.set(bool(voice_cfg.get('auto_tts', False)))
            if hasattr(self, 'assistant_voice_rate_combo'):
                rate_value = str(int(voice_cfg.get('rate', 180) or 180))
                allowed = {"140", "160", "180", "200", "220", "240"}
                self.assistant_voice_rate_combo.set(rate_value if rate_value in allowed else "180")

            # 백엔드 설정은 사용자가 건드릴 필요 없음 - 제거됨

            # 거래소 API 설정 (모든 거래소)
            self.upbit_api_key_entry.insert(0, self.current_settings.get('upbit_api_key', ''))
            self.upbit_secret_key_entry.insert(0, self.current_settings.get('upbit_secret_key', ''))
            self.bithumb_api_key_entry.insert(0, self.current_settings.get('bithumb_api_key', ''))
            self.bithumb_secret_key_entry.insert(0, self.current_settings.get('bithumb_secret_key', ''))

            # 새 거래소 API 설정
            self.bybit_api_key_entry.insert(0, self.current_settings.get('bybit_api_key', ''))
            self.bybit_secret_key_entry.insert(0, self.current_settings.get('bybit_secret_key', ''))
            self.okx_api_key_entry.insert(0, self.current_settings.get('okx_api_key', ''))
            self.okx_secret_key_entry.insert(0, self.current_settings.get('okx_secret_key', ''))
            self.okx_passphrase_entry.insert(0, self.current_settings.get('okx_passphrase', ''))
            self.bitget_api_key_entry.insert(0, self.current_settings.get('bitget_api_key', ''))
            self.bitget_secret_key_entry.insert(0, self.current_settings.get('bitget_secret_key', ''))
            self.bitget_password_entry.insert(0, self.current_settings.get('bitget_password', ''))

            # 키움증권 설정 로드
            stock_configs = self.current_settings.get('stock_broker_configs', {})
            kiwoom_config = stock_configs.get('kiwoom', {})
            if hasattr(self, 'kiwoom_id_entry'):
                self.kiwoom_id_entry.insert(0, kiwoom_config.get('id', ''))
            if hasattr(self, 'kiwoom_password_entry'):
                self.kiwoom_password_entry.insert(0, kiwoom_config.get('password', ''))
            if hasattr(self, 'kiwoom_cert_password_entry'):
                self.kiwoom_cert_password_entry.insert(0, kiwoom_config.get('cert_password', ''))
            if hasattr(self, 'kiwoom_account_entry'):
                self.kiwoom_account_entry.insert(0, kiwoom_config.get('account_no', ''))
            if hasattr(self, 'kiwoom_api_type_combo'):
                self.kiwoom_api_type_combo.set(kiwoom_config.get('api_type', 'openapi_plus'))
                self._sync_stock_api_version_options('kiwoom', preserve_value=False)
            if hasattr(self, 'kiwoom_api_version_combo'):
                self.kiwoom_api_version_combo.set(kiwoom_config.get('api_version', 'pykiwoom'))
                self._sync_stock_api_version_options('kiwoom', preserve_value=True)

            # 신한증권 설정 로드
            shinhan_config = stock_configs.get('shinhan', {})
            if hasattr(self, 'shinhan_id_entry'):
                self.shinhan_id_entry.insert(0, shinhan_config.get('id', ''))
            if hasattr(self, 'shinhan_password_entry'):
                self.shinhan_password_entry.insert(0, shinhan_config.get('password', ''))
            if hasattr(self, 'shinhan_cert_password_entry'):
                self.shinhan_cert_password_entry.insert(0, shinhan_config.get('cert_password', ''))
            if hasattr(self, 'shinhan_account_entry'):
                self.shinhan_account_entry.insert(0, shinhan_config.get('account_no', ''))
            if hasattr(self, 'shinhan_api_type_combo'):
                self.shinhan_api_type_combo.set(shinhan_config.get('api_type', 'partner_rest'))
                self._sync_stock_api_version_options('shinhan', preserve_value=False)
            if hasattr(self, 'shinhan_api_version_combo'):
                self.shinhan_api_version_combo.set(shinhan_config.get('api_version', 'shinhan_openapi_v2'))
                self._sync_stock_api_version_options('shinhan', preserve_value=True)
            if hasattr(self, 'shinhan_partner_profile_text'):
                self.shinhan_partner_profile_text.delete('1.0', 'end')
                self.shinhan_partner_profile_text.insert(
                    '1.0', json.dumps(shinhan_config.get('partner_profile', {}) or {}, ensure_ascii=False, indent=2)
                )

            # 미래에셋 설정 로드
            mirae_asset_config = stock_configs.get('miraeAsset', {})
            if hasattr(self, 'mirae_asset_id_entry'):
                self.mirae_asset_id_entry.insert(0, mirae_asset_config.get('id', ''))
            if hasattr(self, 'mirae_asset_password_entry'):
                self.mirae_asset_password_entry.insert(0, mirae_asset_config.get('password', ''))
            if hasattr(self, 'mirae_asset_cert_password_entry'):
                self.mirae_asset_cert_password_entry.insert(0, mirae_asset_config.get('cert_password', ''))
            if hasattr(self, 'mirae_asset_account_entry'):
                self.mirae_asset_account_entry.insert(0, mirae_asset_config.get('account_no', ''))
            if hasattr(self, 'mirae_asset_api_type_combo'):
                self.mirae_asset_api_type_combo.set(mirae_asset_config.get('api_type', 'partner_rest'))
                self._sync_stock_api_version_options('miraeAsset', preserve_value=False)
            if hasattr(self, 'mirae_asset_api_version_combo'):
                self.mirae_asset_api_version_combo.set(mirae_asset_config.get('api_version', 'mirae_partner_profile'))
                self._sync_stock_api_version_options('miraeAsset', preserve_value=True)
            if hasattr(self, 'mirae_partner_profile_text'):
                self.mirae_partner_profile_text.delete('1.0', 'end')
                self.mirae_partner_profile_text.insert(
                    '1.0', json.dumps(mirae_asset_config.get('partner_profile', {}) or {}, ensure_ascii=False, indent=2)
                )

            # 한국투자증권 설정 로드
            korea_investment_config = stock_configs.get('koreaInvestment', {})
            if hasattr(self, 'korea_investment_id_entry'):
                self.korea_investment_id_entry.insert(0, korea_investment_config.get('id', ''))
            if hasattr(self, 'korea_investment_password_entry'):
                self.korea_investment_password_entry.insert(0, korea_investment_config.get('password', ''))
            if hasattr(self, 'korea_investment_cert_password_entry'):
                self.korea_investment_cert_password_entry.insert(0, korea_investment_config.get('cert_password', ''))
            if hasattr(self, 'korea_investment_account_entry'):
                self.korea_investment_account_entry.insert(0, korea_investment_config.get('account_no', ''))
            if hasattr(self, 'korea_investment_api_type_combo'):
                self.korea_investment_api_type_combo.set(korea_investment_config.get('api_type', 'rest'))
                self._sync_stock_api_version_options('koreaInvestment', preserve_value=False)
            if hasattr(self, 'korea_investment_api_version_combo'):
                self.korea_investment_api_version_combo.set(korea_investment_config.get('api_version', 'kis_openapi_v1'))
                self._sync_stock_api_version_options('koreaInvestment', preserve_value=True)

            # AI 설정은 제거됨 - AI가 자동으로 최적화

            # 거래소 선택 상태 복원 (다중 선택)
            enabled = self.current_settings.get('enabled_exchanges', ['binance'])
            print(f"활성화된 거래소: {enabled}")

            # exchange_vars가 존재하는지 확인
            if hasattr(self, 'exchange_vars'):
                for key, var in self.exchange_vars.items():
                    is_enabled = key in enabled
                    var.set(is_enabled)
                    print(f"{key}: {'활성화' if is_enabled else '비활성화'}")
            else:
                print("exchange_vars가 존재하지 않음")
            if hasattr(self, 'trade_exchange_vars'):
                has_explicit_trade_scope = 'trade_enabled_exchanges' in self.current_settings
                configured_trade = self.current_settings.get('trade_enabled_exchanges', [])
                if not isinstance(configured_trade, list):
                    configured_trade = []
                if not configured_trade and not has_explicit_trade_scope:
                    selected_trade = str(
                        self.current_settings.get('selected_exchange', 'binance') or 'binance'
                    ).strip().lower()
                    configured_trade = [selected_trade]
                for key, var in self.trade_exchange_vars.items():
                    var.set(key in enabled and key in configured_trade)
            if hasattr(self, "multi_venue_mode_combo"):
                multi_mode = str(
                    (
                        self.current_settings.get("multi_venue_execution", {})
                        or {}
                    ).get("mode", "parallel")
                    or "parallel"
                ).lower()
                self.multi_venue_mode_combo.set({
                    "parallel": "선택한 거래소에서 각각 실행 (권장)",
                    "split": "총위험을 거래소별로 분할",
                    "best": "우선순위 한 곳만 실행",
                }.get(multi_mode, "선택한 거래소에서 각각 실행 (권장)"))

            # 증권사 선택 상태 복원 (다중 선택)
            enabled_brokers = self.current_settings.get('enabled_stock_brokers', [])
            print(f"활성화된 증권사: {enabled_brokers}")

            # stock_broker_vars가 존재하는지 확인
            if hasattr(self, 'stock_broker_vars'):
                for key, var in self.stock_broker_vars.items():
                    is_enabled = key in enabled_brokers
                    var.set(is_enabled)
                    print(f"증권사 {key}: {'활성화' if is_enabled else '비활성화'}")
            else:
                print("stock_broker_vars가 존재하지 않음")
            if hasattr(self, 'stock_broker_live_vars'):
                for key, var in self.stock_broker_live_vars.items():
                    cfg = stock_configs.get(key, {}) if isinstance(stock_configs, dict) else {}
                    var.set(bool(cfg.get('allow_live_order', False)))

            if hasattr(self, 'auto_stock_broker_diagnosis_var'):
                auto_diag = bool(
                    self.current_settings.get('ui_settings', {}).get(
                        'auto_show_stock_broker_diagnosis_after_save',
                        True
                    )
                )
                self.auto_stock_broker_diagnosis_var.set(auto_diag)

            stock_asset_mode = str(self.current_settings.get('stock_asset_mode', 'all') or 'all').lower()
            stock_asset_mode_map = {
                'all': '통합',
                'stock': '주식만',
                'etf': 'ETF만',
            }
            if hasattr(self, 'stock_asset_mode_var'):
                self.stock_asset_mode_var.set(stock_asset_mode_map.get(stock_asset_mode, '통합'))

            # 주문 가드레일 복원
            guardrails_cfg = self.current_settings.get('stock_order_guardrails', {})
            if isinstance(guardrails_cfg, dict):
                if hasattr(self, 'guardrail_enabled_var'):
                    self.guardrail_enabled_var.set(bool(guardrails_cfg.get('enabled', True)))
                if hasattr(self, 'guardrail_market_hours_var'):
                    self.guardrail_market_hours_var.set(bool(guardrails_cfg.get('enforce_market_hours', True)))
                if hasattr(self, 'guardrail_allow_market_var'):
                    self.guardrail_allow_market_var.set(bool(guardrails_cfg.get('allow_market_order', True)))
                if hasattr(self, 'guardrail_max_qty_entry'):
                    self.guardrail_max_qty_entry.delete(0, 'end')
                    self.guardrail_max_qty_entry.insert(0, str(int(guardrails_cfg.get('max_quantity', 10000))))
                if hasattr(self, 'guardrail_max_value_entry'):
                    self.guardrail_max_value_entry.delete(0, 'end')
                    self.guardrail_max_value_entry.insert(0, str(int(guardrails_cfg.get('max_order_value', 50000000))))
                if hasattr(self, 'guardrail_daily_limit_entry'):
                    self.guardrail_daily_limit_entry.delete(0, 'end')
                    self.guardrail_daily_limit_entry.insert(0, str(int(guardrails_cfg.get('daily_order_limit', 20))))

            # 증권 자동매매 제어 복원
            stock_auto_cfg = self.current_settings.get('stock_auto_trading', {})
            if isinstance(stock_auto_cfg, dict):
                if hasattr(self, 'stock_auto_start_var'):
                    self.stock_auto_start_var.set(bool(stock_auto_cfg.get('auto_start', stock_auto_cfg.get('enabled', False))))
            if hasattr(self, 'stock_live_order_var'):
                self.stock_live_order_var.set(bool(self.current_settings.get('enable_stock_live_order', False)))
            if hasattr(self, 'stock_stop_policy_var'):
                policy = str(
                    self.current_settings.get(
                        'asset_stop_position_policy',
                        self.current_settings.get('stock_stop_position_policy', 'keep_with_tp_sl')
                    )
                )
                self.stock_stop_policy_var.set(policy if policy in ('keep_with_tp_sl', 'close_all') else 'keep_with_tp_sl')

            # 생활금융 동기화/백업 경로 복원
            if hasattr(self, 'life_finance_sync_dir_entry'):
                self.life_finance_sync_dir_entry.delete(0, 'end')
                self.life_finance_sync_dir_entry.insert(0, str(self.current_settings.get('life_finance_sync_dir', '') or ''))
            if hasattr(self, 'life_finance_backup_dir_entry'):
                self.life_finance_backup_dir_entry.delete(0, 'end')
                self.life_finance_backup_dir_entry.insert(0, str(self.current_settings.get('life_finance_backup_dir', '') or ''))

            # 테마 설정 복원 (테마 시스템 제거됨 - 무시)
            # theme_var는 더 이상 존재하지 않음

            # 기본 마진 타입 복원
            if self.margin_type_combo is not None:
                margin_type = self.current_settings.get('default_margin_type', 'ISOLATED')
                try:
                    if margin_type not in ("ISOLATED", "CROSS"):
                        margin_type = 'ISOLATED'
                except Exception:
                    margin_type = 'ISOLATED'
                self.margin_type_combo.set(margin_type)

            # 시장 국면 자동 보정 UI 복원
            if hasattr(self, 'dynamic_thresholds_var'):
                self.dynamic_thresholds_var.set(bool(self.current_settings.get('dynamic_thresholds_enabled', True)))
            if hasattr(self, 'dynamic_high_mult_entry'):
                try:
                    val = str(self.current_settings.get('dynamic_thresholds_high_multiplier', 1.5))
                    self.dynamic_high_mult_entry.delete(0, 'end')
                    self.dynamic_high_mult_entry.insert(0, val)
                except Exception:
                    pass
            if self.dynamic_mode_combo is not None:
                mode = str(self.current_settings.get('dynamic_thresholds_mode', 'auto')).lower()
                self.dynamic_mode_combo.set('manual' if mode == 'manual' else 'auto')
            if self.manual_regime_combo is not None:
                regime = str(self.current_settings.get('dynamic_thresholds_manual_regime', 'NORMAL')).upper()
                if regime not in ('LOW', 'NORMAL', 'HIGH'):
                    regime = 'NORMAL'
                self.manual_regime_combo.set(regime)

            # 일반 설정 복원: 페이퍼 트레이딩, 데모 모드
            try:
                if hasattr(self, 'paper_trading_var'):
                    self.paper_trading_var.set(bool(self.current_settings.get('paper_trading', False)))
                if hasattr(self, 'verbose_logging_var'):
                    self.verbose_logging_var.set(bool(self.current_settings.get('verbose_trade_logging', False)))
                if hasattr(self, 'broadcast_replay_enabled_var') and self.broadcast_replay_enabled_var is not None:
                    self.broadcast_replay_enabled_var.set(bool(self.current_settings.get('broadcast_replay_enabled', False)))
                if hasattr(self, 'broadcast_replay_source_entry') and self.broadcast_replay_source_entry is not None:
                    self.broadcast_replay_source_entry.delete(0, 'end')
                    self.broadcast_replay_source_entry.insert(0, str(self.current_settings.get('broadcast_replay_source_account', '') or ''))
                # demo_mode_var 제거됨 - settings.json에서 직접 설정
            except Exception:
                pass

            # Alpha Arena 설정 복원 (새로운 alpha_arena 구조)
            try:
                alpha_arena = self.current_settings.get('alpha_arena', {})
                
                # 활성화
                if hasattr(self, 'alpha_arena_enabled_var'):
                    self.alpha_arena_enabled_var.set(bool(alpha_arena.get('enabled', False)))
                
                # 엔진
                if hasattr(self, 'alpha_arena_engine_var'):
                    engine = alpha_arena.get('engine', 'deepseek-v4-flash')
                    if engine in ('deepseek-3.1', 'deepseek-chat-v3.1', 'deepseek-chat'):
                        engine = 'deepseek-v4-flash'
                    self.alpha_arena_engine_var.set(engine)
                
                # API 키 (DeepSeek, Qwen3)
                if hasattr(self, 'alpha_arena_deepseek_api_key_var'):
                    # 레거시 키도 확인 (하위 호환성)
                    deepseek_key = alpha_arena.get('deepseek_api_key', '') or self.current_settings.get('alphaarena_deepseek_api_key', '')
                    self.alpha_arena_deepseek_api_key_var.set(deepseek_key)
                
                if hasattr(self, 'alpha_arena_qwen_api_key_var'):
                    # 레거시 키도 확인 (하위 호환성)
                    qwen_key = alpha_arena.get('qwen_api_key', '') or self.current_settings.get('alphaarena_alibaba_api_key', '')
                    self.alpha_arena_qwen_api_key_var.set(qwen_key)
                
                # 초기 자금 기준
                if hasattr(self, 'alpha_arena_capital_benchmark_var'):
                    capital_benchmark = alpha_arena.get('initial_capital_benchmark', 10000)
                    self.alpha_arena_capital_benchmark_var.set(str(capital_benchmark))
                    # 경고 메시지 업데이트
                    if hasattr(self, '_update_capital_warning'):
                        self._update_capital_warning()
            except Exception as e:
                print(f"Alpha Arena 설정 복원 실패: {e}")

            # 고급 매매 계층 ON/OFF 복원
            try:
                if hasattr(self, '_atl_vars') and self._atl_vars:
                    atl = self.current_settings.get("advanced_trading_layers", {})
                    for key, var in self._atl_vars.items():
                        var.set(bool(atl.get(key, {}).get("enabled", False)))
                    strategy_policy = dict(atl.get("strategy_engine", {}) or {})
                    if hasattr(self, '_atl_high_vol_action_var'):
                        high_vol_label = (
                            "평가 계속 (권장)"
                            if str(strategy_policy.get("high_vol_action", "evaluate")).lower() != "block"
                            else "항상 차단"
                        )
                        self._atl_high_vol_action_var.set(high_vol_label)
                    if hasattr(self, '_atl_consensus_threshold_var'):
                        self._atl_consensus_threshold_var.set(
                            str(strategy_policy.get("consensus_threshold", 0.60))
                        )
                    if hasattr(self, '_atl_cooldown_sec_var'):
                        self._atl_cooldown_sec_var.set(
                            str(strategy_policy.get("cooldown_sec", 60))
                        )
            except Exception as e:
                print(f"고급 매매 계층 설정 복원 실패: {e}")

            print("설정 로드 완료")

        except Exception as e:
            print(f"설정 로드 실패: {e}")


    def create_update_info_tab(self):
        """업데이트 정보 탭 - 버전 및 새로운 기능 안내"""
        tab = self.tabview.add("업데이트")
        self._add_tab_save_bar(tab, "8. 업데이트")

        # 스크롤 가능한 프레임
        scroll_frame = ctk.CTkScrollableFrame(tab)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 버전 정보 그룹
        version_group = ctk.CTkFrame(scroll_frame)
        version_group.pack(fill="x", pady=(0, 20))

        # 제목
        version_title = ctk.CTkLabel(
            version_group,
            text="버전 정보",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        version_title.pack(pady=(12, 8), padx=15, anchor="w")

        # 현재 버전 표시
        try:
            from config.app_version import RELEASE_VERSION
            version_text = f"현재 버전: v{RELEASE_VERSION}"
        except Exception:
            version_text = "현재 버전: v3.8.9.19"

        version_label = ctk.CTkLabel(
            version_group,
            text=version_text,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#60a5fa"
        )
        version_label.pack(pady=4, padx=20, anchor="w")

        # 업데이트 일자
        update_date_label = ctk.CTkLabel(
            version_group,
            text="후보 소스 기준일: 2026년 7월 29일 (Windows 배포 전)",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#9ca3af"
        )
        update_date_label.pack(pady=4, padx=20, anchor="w")

        self.update_status_label = ctk.CTkLabel(
            version_group,
            text="업데이트 상태: 아직 확인하지 않음",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#9ca3af",
        )
        self.update_status_label.pack(pady=4, padx=20, anchor="w")

        self.update_runtime_path_label = ctk.CTkLabel(
            version_group,
            text="업데이트 런타임 정보: 로딩 중...",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94a3b8",
            justify="left",
            wraplength=760,
        )
        self.update_runtime_path_label.pack(pady=(2, 8), padx=20, anchor="w")

        self._refresh_update_runtime_diagnostics_label()

        update_actions_row = ctk.CTkFrame(version_group, fg_color="transparent")
        update_actions_row.pack(fill="x", padx=20, pady=(8, 14))

        ctk.CTkButton(
            update_actions_row,
            text="업데이트 확인 (GitHub)",
            width=180,
            height=34,
            fg_color="#1f4ed8",
            hover_color="#1d4ed8",
            command=self._check_github_client_update,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            update_actions_row,
            text="최신 릴리즈 열기",
            width=160,
            height=34,
            fg_color="#0f766e",
            hover_color="#115e59",
            command=self._open_latest_release_page,
        ).pack(side="left")

        ctk.CTkButton(
            update_actions_row,
            text="지금 업데이트 적용(재시작)",
            width=210,
            height=34,
            fg_color="#7c3aed",
            hover_color="#6d28d9",
            command=self._apply_downloaded_update_now,
        ).pack(side="left", padx=(8, 0))

        auto_update_group = ctk.CTkFrame(scroll_frame)
        auto_update_group.pack(fill="x", pady=(0, 20))

        auto_title = ctk.CTkLabel(
            auto_update_group,
            text="자동업데이트 설정",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb"),
        )
        auto_title.pack(pady=(12, 8), padx=15, anchor="w")

        ui_settings = self.current_settings.get('ui_settings', {}) if isinstance(self.current_settings, dict) else {}
        if not isinstance(ui_settings, dict):
            ui_settings = {}

        self.auto_update_enabled_var = tk.BooleanVar(value=bool(ui_settings.get('auto_update_enabled', True)))
        self.auto_update_auto_download_var = tk.BooleanVar(value=bool(ui_settings.get('auto_update_auto_download', True)))
        self.auto_update_auto_apply_var = tk.BooleanVar(value=bool(ui_settings.get('auto_update_auto_apply_on_exit', True)))

        ctk.CTkCheckBox(
            auto_update_group,
            text="앱 실행 중 백그라운드 자동 체크 사용",
            variable=self.auto_update_enabled_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
        ).pack(anchor="w", padx=20, pady=3)

        ctk.CTkCheckBox(
            auto_update_group,
            text="새 버전 발견 시 자동 다운로드",
            variable=self.auto_update_auto_download_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
        ).pack(anchor="w", padx=20, pady=3)

        ctk.CTkCheckBox(
            auto_update_group,
            text="앱 종료 시 자동 적용(재시작)",
            variable=self.auto_update_auto_apply_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
        ).pack(anchor="w", padx=20, pady=3)

        interval_row = ctk.CTkFrame(auto_update_group, fg_color="transparent")
        interval_row.pack(fill="x", padx=20, pady=(6, 12))
        ctk.CTkLabel(
            interval_row,
            text="자동 체크 주기(시간):",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#d1d5db",
        ).pack(side="left")
        self.auto_update_interval_entry = ctk.CTkEntry(interval_row, width=80)
        self.auto_update_interval_entry.pack(side="left", padx=(8, 0))
        self.auto_update_interval_entry.insert(0, str(ui_settings.get('auto_update_check_interval_hours', 6)))

        ctk.CTkLabel(
            auto_update_group,
            text=(
                "실행 15초 뒤 최초 1회 확인하며 이후 위 주기를 사용합니다. "
                "인증서는 요구하지 않고 GitHub HTTPS + manifest SHA-256을 필수 검증합니다. "
                "무서명 EXE는 Windows 평판 경고가 나타날 수 있습니다."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#94a3b8",
            wraplength=760,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 10))

        ctk.CTkLabel(
            auto_update_group,
            text="열린 포지션·주문이 있을 때:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#d1d5db",
        ).pack(anchor="w", padx=20, pady=(0, 4))
        action_value = str(ui_settings.get("auto_update_open_position_action", "defer") or "defer")
        self.auto_update_position_action_combo = ctk.CTkComboBox(
            auto_update_group,
            values=["업데이트 연기(권장)", "포지션 유지(TP/SL 확인)", "전량 청산(체결 확인)"],
            state="readonly",
            width=260,
        )
        self.auto_update_position_action_combo.set({
            "defer": "업데이트 연기(권장)",
            "keep_with_tp_sl": "포지션 유지(TP/SL 확인)",
            "close_all": "전량 청산(체결 확인)",
        }.get(action_value, "업데이트 연기(권장)"))
        self.auto_update_position_action_combo.pack(anchor="w", padx=20, pady=(0, 6))
        ctk.CTkLabel(
            auto_update_group,
            text="기본값은 연기입니다. 유지 모드는 모든 포지션의 거래소 측 TP·SL 확인에 실패하면 중단하고, 청산 모드는 실제 포지션·미체결 주문이 0건임을 확인해야 진행합니다.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#94a3b8",
            wraplength=760,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 12))

        python_runtime_group = ctk.CTkFrame(scroll_frame)
        python_runtime_group.pack(fill="x", pady=(0, 20))

        python_runtime_title = ctk.CTkLabel(
            python_runtime_group,
            text="Python 런타임 정보",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        python_runtime_title.pack(pady=(12, 8), padx=15, anchor="w")

        python_summary = self._get_python_runtime_summary()
        compatibility_lines = python_summary.get('broker_compatibility', [])
        os_line = f"{python_summary.get('os_name', 'Unknown')} {python_summary.get('os_release', '')}".strip()
        python_lines = [
            f"현재 OS: {os_line} ({python_summary.get('os_bits', '?')}bit)",
            f"OS 플랫폼: {python_summary.get('os_machine', 'unknown')}",
            f"현재 Python: {python_summary['python_version']} ({python_summary['python_bits']}bit)",
            f"권장: {python_summary['recommendation']}",
            f"설치 힌트: {python_summary['install_hint']}",
            "브로커 호환성:",
        ]
        python_lines.extend([f"- {line}" for line in compatibility_lines])

        for line in python_lines:
            line_label = ctk.CTkLabel(
                python_runtime_group,
                text=line,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color="#d1d5db",
                justify="left",
                wraplength=700,
            )
            line_label.pack(anchor="w", padx=20, pady=2)

        python_action_row = ctk.CTkFrame(python_runtime_group, fg_color="transparent")
        python_action_row.pack(fill="x", padx=20, pady=(8, 14))

        ctk.CTkButton(
            python_action_row,
            text="Python 권장 안내",
            width=160,
            height=34,
            fg_color="#1f4ed8",
            hover_color="#1d4ed8",
            command=self._show_python_runtime_help_dialog,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            python_action_row,
            text="32bit Python 다운로드",
            width=170,
            height=34,
            fg_color="#0f766e",
            hover_color="#115e59",
            command=self._open_python_download_page,
        ).pack(side="left")

        ctk.CTkButton(
            python_action_row,
            text="설치 가이드 보기",
            width=180,
            height=34,
            fg_color="#334155",
            hover_color="#475569",
            command=self._open_stock_broker_connection_checklist,
        ).pack(side="left", padx=(8, 0))

        # 변경 이력 단일화 섹션
        changelog_group = ctk.CTkFrame(scroll_frame)
        changelog_group.pack(fill="x", pady=(0, 20))

        changelog_title = ctk.CTkLabel(
            changelog_group,
            text="변경 이력 경로(단일화)",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        changelog_title.pack(pady=(12, 8), padx=15, anchor="w")

        changelog_text = (
            "중복 안내를 방지하기 위해 버전별 최신 변경 상세는 설정 탭에 중복 표기하지 않습니다.\n"
            "공식 변경 이력은 대시보드 '사용자 매뉴얼 → 업데이트' 탭에서만 단일 관리됩니다.\n"
            "이 탭은 업데이트 확인/다운로드/적용과 런타임(Python·호환성) 점검 중심으로 유지됩니다."
        )

        changelog_label = ctk.CTkLabel(
            changelog_group,
            text=changelog_text,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#d1d5db",
            justify="left",
            wraplength=700
        )
        changelog_label.pack(anchor="w", padx=20, pady=(0, 12))

        # 상세 정보 섹션
        more_info_group = ctk.CTkFrame(scroll_frame)
        more_info_group.pack(fill="x", pady=(0, 20))

        more_title = ctk.CTkLabel(
            more_info_group,
            text="상세 정보",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        more_title.pack(pady=(12, 8), padx=15, anchor="w")

        info_text = "릴리스 노트: 각 버전의 변경 사항을 확인하세요\n사용 설명서: AI 실행 기능 단계별 가이드\n안전 정책: 2단계 확인, 자동 실행 금지"
        info_label = ctk.CTkLabel(
            more_info_group,
            text=info_text,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#9ca3af",
            justify="left"
        )
        info_label.pack(anchor="w", padx=20, pady=4)

        # 사용자 안내 섹션 (내부 개발 문서 경로 노출 금지)
        links_frame = ctk.CTkFrame(scroll_frame)
        links_frame.pack(fill="x", pady=(20, 0))

        # 사용자에게는 앱에서 바로 확인 가능한 경로만 안내
        links_label = ctk.CTkLabel(
            links_frame,
            text="사용자 안내:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        links_label.pack(pady=(8, 4), padx=15, anchor="w")

        docs = [
            "• 앱 내 '업데이트' 탭에서 최신 변경사항을 확인할 수 있습니다.",
            "• AI 설정/최적화 도움말은 'AI 어시스턴트 → 설정관리'에서 안내됩니다.",
            "• AI 실행은 '준비도 점검' 기능이며, 확인 전에는 자동 시작되지 않습니다.",
            "• 상세 문의는 운영 지원 채널 또는 관리자 안내를 이용해 주세요.",
        ]

        for doc in docs:
            doc_label = ctk.CTkLabel(
                links_frame,
                text=doc,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#94a3b8",
                justify="left"
            )
            doc_label.pack(anchor="w", padx=20, pady=2)

    def _read_stock_partner_profile(self, broker: str) -> Dict[str, Any]:
        widget_name = {
            'shinhan': 'shinhan_partner_profile_text',
            'miraeAsset': 'mirae_partner_profile_text',
        }[broker]
        widget = getattr(self, widget_name, None)
        current = dict(
            self.current_settings.get('stock_broker_configs', {}).get(broker, {}).get('partner_profile', {}) or {}
        )
        if widget is None:
            return current
        raw = str(widget.get('1.0', 'end') or '').strip()
        if not raw:
            return {}
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError(f'{broker} partner_profile은 JSON 객체여야 합니다.')
        return parsed

    def save_settings(self):
        """설정 저장 - 기존 PyQt5 설정 창과 동일한 로직"""
        try:
            shinhan_partner_profile = self._read_stock_partner_profile('shinhan')
            mirae_partner_profile = self._read_stock_partner_profile('miraeAsset')
            active_provider = self._selected_ai_provider()
            analyst_route = self._assignment_route("analyst")
            assistant_route = self._assignment_route("assistant")
            role_routes = {
                "frequent_cheap": self._assignment_route("frequent_cheap"),
                "standard": self._assignment_route("standard"),
                "premium": self._assignment_route("premium"),
            }
            analyst_provider = analyst_route["provider"]
            active_key = self.openai_api_key_entry.get().strip()
            self._ai_provider_key_buffer[active_provider] = active_key
            ai_credentials = copy.deepcopy(self.current_settings.get("ai_credentials", {}) or {})

            for provider_name in self._AI_PROVIDER_LABELS.values():
                provider_cfg = dict(ai_credentials.get(provider_name, {}) or {})
                if provider_name == active_provider:
                    provider_cfg["base_url"] = (
                        self.openai_base_url_entry.get().strip()
                        if hasattr(self, "openai_base_url_entry")
                        else self._AI_PROVIDER_BASE_URLS.get(provider_name, "")
                    )
                else:
                    provider_cfg.setdefault(
                        "base_url",
                        self._AI_PROVIDER_BASE_URLS.get(provider_name, ""),
                    )
                if provider_name in self._ai_provider_key_buffer:
                    buffered_key = str(
                        self._ai_provider_key_buffer.get(provider_name) or ""
                    ).strip()
                    if buffered_key:
                        provider_cfg["api_key"] = buffered_key
                        provider_cfg.pop("credential_ref", None)
                    elif not provider_cfg.get("credential_ref"):
                        # 로컬 키는 입력란을 비운 뒤 저장하면 실제로 삭제된다.
                        provider_cfg.pop("api_key", None)
                    else:
                        # v3.9.0.3 참조만 남은 설정은 사용자가 새 키를
                        # 입력하기 전까지 단서를 보존한다.
                        provider_cfg.pop("api_key", None)
                ai_credentials[provider_name] = provider_cfg
            provider_cfg = dict(ai_credentials.get(active_provider, {}) or {})
            response_mode = {
                "문답 절약형": "saver",
                "질문답변 표준형": "standard",
                "분석 정밀형": "premium",
            }.get(
                self.assistant_response_mode_combo.get()
                if hasattr(self, "assistant_response_mode_combo")
                else "질문답변 표준형",
                "standard",
            )

            enabled_exchange_values = [
                key for key, var in self.exchange_vars.items()
                if var is not None and hasattr(var, 'get') and var.get()
            ] if hasattr(self, 'exchange_vars') else list(
                self.current_settings.get('enabled_exchanges', []) or []
            )
            trade_exchange_values = [
                key for key, var in self.trade_exchange_vars.items()
                if var is not None and hasattr(var, 'get') and var.get()
                and key in enabled_exchange_values
            ] if hasattr(self, 'trade_exchange_vars') else list(
                self.current_settings.get('trade_enabled_exchanges', []) or []
            )

            # UI에서 설정 값 가져오기 (기존과 동일한 방식)
            new_settings = {
                # AI 제공사 설정. openai_*는 런타임 하위 호환 키로 유지한다.
                'ai_provider': analyst_provider,
                'ai_credentials': ai_credentials,
                'ai_provider_profiles': {
                    'analyst': dict(analyst_route),
                    'assistant': dict(assistant_route),
                    'transcription': {
                        'provider': 'openai',
                        'model': self.ai_custom_transcription_model_combo.get(),
                    },
                },
                'ai_models': {
                    'analyst': analyst_route["model"],
                    'assistant': assistant_route["model"],
                    'roles': copy.deepcopy(role_routes),
                },
                'assistant_response_mode': response_mode,
                'openai_api_key': (
                    str(self._ai_provider_key_buffer.get(analyst_provider) or "")
                    if analyst_provider in self._ai_provider_key_buffer
                    else str((ai_credentials.get(analyst_provider, {}) or {}).get("api_key") or "")
                ),
                'openai_base_url': (
                    str((ai_credentials.get(analyst_provider, {}) or {}).get("base_url") or "")
                ),
                'openai_model': analyst_route["model"],
                'assistant_ai_model': assistant_route["model"],
                'ai_model_roles': copy.deepcopy(role_routes),
                'ai_custom_transcription': {
                    'enabled': bool(self.ai_custom_transcription_enabled_var.get()) if hasattr(self, 'ai_custom_transcription_enabled_var') else True,
                    'provider': 'openai',
                    'model': self.ai_custom_transcription_model_combo.get() if hasattr(self, 'ai_custom_transcription_model_combo') else 'gpt-4o-mini-transcribe',
                    'max_duration_minutes': int(self.ai_custom_transcription_minutes_combo.get()) if hasattr(self, 'ai_custom_transcription_minutes_combo') else 45,
                    'max_file_mb': int(self.ai_custom_transcription_mb_combo.get()) if hasattr(self, 'ai_custom_transcription_mb_combo') else 24,
                },
                'ai_custom_runtime': {
                    'enabled': bool(self.ai_custom_runtime_enabled_var.get()) if hasattr(self, 'ai_custom_runtime_enabled_var') else False,
                    'allow_limited_live': bool(self.ai_custom_limited_live_var.get()) if hasattr(self, 'ai_custom_limited_live_var') else False,
                    'limited_max_leverage': 1,
                    'limited_max_position_size': 0.01,
                },
                'ai_custom_features': self._collect_ai_custom_feature_settings(),
                'assistant_apply_mode': 'user_confirm',
                'assistant_voice': {
                    'enabled': bool(self.assistant_voice_enabled_var.get()) if hasattr(self, 'assistant_voice_enabled_var') else False,
                    'auto_tts': bool(self.assistant_voice_auto_tts_var.get()) if hasattr(self, 'assistant_voice_auto_tts_var') else False,
                    'lang': 'ko-KR',
                    'rate': int(self.assistant_voice_rate_combo.get()) if hasattr(self, 'assistant_voice_rate_combo') else 180,
                },

                # 백엔드 설정은 사용자가 건드릴 필요 없음 - 제거됨

                # 거래소 API 설정 (모든 거래소 저장)
                'binance_api_key': self.binance_api_key_entry.get(),
                'binance_secret_key': self.binance_secret_key_entry.get(),
                'upbit_api_key': self.upbit_api_key_entry.get(),
                'upbit_secret_key': self.upbit_secret_key_entry.get(),
                'bithumb_api_key': self.bithumb_api_key_entry.get(),
                'bithumb_secret_key': self.bithumb_secret_key_entry.get(),

                # 새 거래소 API 설정
                'bybit_api_key': self.bybit_api_key_entry.get(),
                'bybit_secret_key': self.bybit_secret_key_entry.get(),
                'okx_api_key': self.okx_api_key_entry.get(),
                'okx_secret_key': self.okx_secret_key_entry.get(),
                'okx_passphrase': self.okx_passphrase_entry.get(),
                'bitget_api_key': self.bitget_api_key_entry.get(),
                'bitget_secret_key': self.bitget_secret_key_entry.get(),
                'bitget_password': self.bitget_password_entry.get(),

                # 키움증권 설정 저장
                'stock_broker_configs': {
                    'kiwoom': {
                        'enabled': self.stock_broker_vars['kiwoom'].get() if hasattr(self, 'stock_broker_vars') and 'kiwoom' in self.stock_broker_vars else False,
                        'api_type': self.kiwoom_api_type_combo.get() if hasattr(self, 'kiwoom_api_type_combo') else 'openapi_plus',
                        'api_version': self.kiwoom_api_version_combo.get() if hasattr(self, 'kiwoom_api_version_combo') else 'pykiwoom',
                        'id': self.kiwoom_id_entry.get() if hasattr(self, 'kiwoom_id_entry') else '',
                        'password': self.kiwoom_password_entry.get() if hasattr(self, 'kiwoom_password_entry') else '',
                        'cert_password': self.kiwoom_cert_password_entry.get() if hasattr(self, 'kiwoom_cert_password_entry') else '',
                        'account_no': self.kiwoom_account_entry.get() if hasattr(self, 'kiwoom_account_entry') else '',
                        'allow_live_order': bool(self.stock_broker_live_vars['kiwoom'].get()) if hasattr(self, 'stock_broker_live_vars') else False,
                        'asset_types': ['stock', 'etf']
                    },
                    'shinhan': {
                        'enabled': self.stock_broker_vars['shinhan'].get() if hasattr(self, 'stock_broker_vars') and 'shinhan' in self.stock_broker_vars else False,
                        'api_type': self.shinhan_api_type_combo.get() if hasattr(self, 'shinhan_api_type_combo') else 'partner_rest',
                        'api_version': self.shinhan_api_version_combo.get() if hasattr(self, 'shinhan_api_version_combo') else 'shinhan_openapi_v2',
                        'id': self.shinhan_id_entry.get() if hasattr(self, 'shinhan_id_entry') else '',
                        'password': self.shinhan_password_entry.get() if hasattr(self, 'shinhan_password_entry') else '',
                        'cert_password': self.shinhan_cert_password_entry.get() if hasattr(self, 'shinhan_cert_password_entry') else '',
                        'account_no': self.shinhan_account_entry.get() if hasattr(self, 'shinhan_account_entry') else '',
                        # app_key/app_secret 전용 입력 UI가 없는 동안에는 id/password를 동기화 저장
                        # (어댑터는 app_key/app_secret 우선 사용)
                        'app_key': (self.shinhan_id_entry.get() if hasattr(self, 'shinhan_id_entry') else '') or self.current_settings.get('stock_broker_configs', {}).get('shinhan', {}).get('app_key', ''),
                        'app_secret': (self.shinhan_password_entry.get() if hasattr(self, 'shinhan_password_entry') else '') or self.current_settings.get('stock_broker_configs', {}).get('shinhan', {}).get('app_secret', ''),
                        'allow_live_order': bool(self.stock_broker_live_vars['shinhan'].get()) if hasattr(self, 'stock_broker_live_vars') else False,
                        'partner_profile': shinhan_partner_profile,
                        'asset_types': ['stock', 'etf']
                    },
                    'miraeAsset': {
                        'enabled': self.stock_broker_vars['miraeAsset'].get() if hasattr(self, 'stock_broker_vars') and 'miraeAsset' in self.stock_broker_vars else False,
                        'api_type': self.mirae_asset_api_type_combo.get() if hasattr(self, 'mirae_asset_api_type_combo') else 'partner_rest',
                        'api_version': self.mirae_asset_api_version_combo.get() if hasattr(self, 'mirae_asset_api_version_combo') else 'mirae_partner_profile',
                        'id': self.mirae_asset_id_entry.get() if hasattr(self, 'mirae_asset_id_entry') else '',
                        'password': self.mirae_asset_password_entry.get() if hasattr(self, 'mirae_asset_password_entry') else '',
                        'cert_password': self.mirae_asset_cert_password_entry.get() if hasattr(self, 'mirae_asset_cert_password_entry') else '',
                        'account_no': self.mirae_asset_account_entry.get() if hasattr(self, 'mirae_asset_account_entry') else '',
                        # app_key/app_secret 전용 입력 UI가 없는 동안에는 id/password를 동기화 저장
                        'app_key': (self.mirae_asset_id_entry.get() if hasattr(self, 'mirae_asset_id_entry') else '') or self.current_settings.get('stock_broker_configs', {}).get('miraeAsset', {}).get('app_key', ''),
                        'app_secret': (self.mirae_asset_password_entry.get() if hasattr(self, 'mirae_asset_password_entry') else '') or self.current_settings.get('stock_broker_configs', {}).get('miraeAsset', {}).get('app_secret', ''),
                        'allow_live_order': bool(self.stock_broker_live_vars['miraeAsset'].get()) if hasattr(self, 'stock_broker_live_vars') else False,
                        'partner_profile': mirae_partner_profile,
                        'asset_types': ['stock', 'etf']
                    },
                    'koreaInvestment': {
                        'enabled': self.stock_broker_vars['koreaInvestment'].get() if hasattr(self, 'stock_broker_vars') and 'koreaInvestment' in self.stock_broker_vars else False,
                        'api_type': self.korea_investment_api_type_combo.get() if hasattr(self, 'korea_investment_api_type_combo') else 'rest',
                        'api_version': self.korea_investment_api_version_combo.get() if hasattr(self, 'korea_investment_api_version_combo') else 'kis_openapi_v1',
                        'id': self.korea_investment_id_entry.get() if hasattr(self, 'korea_investment_id_entry') else '',
                        'password': self.korea_investment_password_entry.get() if hasattr(self, 'korea_investment_password_entry') else '',
                        'cert_password': self.korea_investment_cert_password_entry.get() if hasattr(self, 'korea_investment_cert_password_entry') else '',
                        'account_no': self.korea_investment_account_entry.get() if hasattr(self, 'korea_investment_account_entry') else '',
                        'app_key': (self.korea_investment_id_entry.get() if hasattr(self, 'korea_investment_id_entry') else '') or self.current_settings.get('stock_broker_configs', {}).get('koreaInvestment', {}).get('app_key', ''),
                        'app_secret': (self.korea_investment_password_entry.get() if hasattr(self, 'korea_investment_password_entry') else '') or self.current_settings.get('stock_broker_configs', {}).get('koreaInvestment', {}).get('app_secret', ''),
                        'allow_live_order': bool(self.stock_broker_live_vars['koreaInvestment'].get()) if hasattr(self, 'stock_broker_live_vars') else False,
                        'sandbox': bool(self.current_settings.get('stock_broker_configs', {}).get('koreaInvestment', {}).get('sandbox', False)),
                        'asset_types': ['stock', 'etf']
                    }
                },

                # AI 설정은 제거됨 - AI가 자동으로 최적화

                # 거래소 선택 (다중 선택)
                'enabled_exchanges': enabled_exchange_values,
                'learning_enabled_exchanges': enabled_exchange_values,
                'trade_enabled_exchanges': trade_exchange_values,
                '_trade_scope_user_confirmed_v3905': True,
                'multi_venue_execution': {
                    **dict(self.current_settings.get('multi_venue_execution', {}) or {}),
                    'enabled': True,
                    'mode': {
                        '선택한 거래소에서 각각 실행 (권장)': 'parallel',
                        '총위험을 거래소별로 분할': 'split',
                        '우선순위 한 곳만 실행': 'best',
                    }.get(
                        self.multi_venue_mode_combo.get()
                        if hasattr(self, 'multi_venue_mode_combo')
                        else '',
                        'parallel',
                    ),
                },
                
                # 증권사 선택 (다중 선택)
                'enabled_stock_brokers': [k for k,v in self.stock_broker_vars.items() if v is not None and hasattr(v, 'get') and v.get()] if hasattr(self, 'stock_broker_vars') else [],
                'stock_asset_mode': {
                    '통합': 'all',
                    '주식만': 'stock',
                    'ETF만': 'etf',
                }.get(self.stock_asset_mode_var.get(), 'all') if hasattr(self, 'stock_asset_mode_var') else self.current_settings.get('stock_asset_mode', 'all'),
                'stock_order_guardrails': {
                    'enabled': bool(self.guardrail_enabled_var.get()) if hasattr(self, 'guardrail_enabled_var') else self.current_settings.get('stock_order_guardrails', {}).get('enabled', True),
                    'enforce_market_hours': bool(self.guardrail_market_hours_var.get()) if hasattr(self, 'guardrail_market_hours_var') else self.current_settings.get('stock_order_guardrails', {}).get('enforce_market_hours', True),
                    'allow_market_order': bool(self.guardrail_allow_market_var.get()) if hasattr(self, 'guardrail_allow_market_var') else self.current_settings.get('stock_order_guardrails', {}).get('allow_market_order', True),
                    'allow_limit_order': True,
                    'max_quantity': int(self.guardrail_max_qty_entry.get() or '10000') if hasattr(self, 'guardrail_max_qty_entry') else int(self.current_settings.get('stock_order_guardrails', {}).get('max_quantity', 10000)),
                    'max_order_value': float(self.guardrail_max_value_entry.get() or '50000000') if hasattr(self, 'guardrail_max_value_entry') else float(self.current_settings.get('stock_order_guardrails', {}).get('max_order_value', 50000000)),
                    'daily_order_limit': int(self.guardrail_daily_limit_entry.get() or '20') if hasattr(self, 'guardrail_daily_limit_entry') else int(self.current_settings.get('stock_order_guardrails', {}).get('daily_order_limit', 20)),
                },
                # 증권 자동매매 제어
                'enable_stock_live_order': bool(self.stock_live_order_var.get()) if hasattr(self, 'stock_live_order_var') else bool(self.current_settings.get('enable_stock_live_order', False)),
                'asset_stop_position_policy': self.stock_stop_policy_var.get() if hasattr(self, 'stock_stop_policy_var') else self.current_settings.get('asset_stop_position_policy', self.current_settings.get('stock_stop_position_policy', 'keep_with_tp_sl')),
                # 하위 호환: 구 키도 같이 저장
                'stock_stop_position_policy': self.stock_stop_policy_var.get() if hasattr(self, 'stock_stop_policy_var') else self.current_settings.get('stock_stop_position_policy', self.current_settings.get('asset_stop_position_policy', 'keep_with_tp_sl')),
                'life_finance_sync_dir': self.life_finance_sync_dir_entry.get().strip() if hasattr(self, 'life_finance_sync_dir_entry') else str(self.current_settings.get('life_finance_sync_dir', '') or '').strip(),
                'life_finance_backup_dir': self.life_finance_backup_dir_entry.get().strip() if hasattr(self, 'life_finance_backup_dir_entry') else str(self.current_settings.get('life_finance_backup_dir', '') or '').strip(),
                # 하위 호환 위해 유지
                'selected_exchange': 'binance' if not any(v is not None and hasattr(v, 'get') and v.get() for v in self.exchange_vars.values()) else (
                    next((k for k,v in self.exchange_vars.items() if v is not None and hasattr(v, 'get') and v.get()), 'binance')
                ),
                # 선물 기본 설정
                'default_margin_type': (self.margin_type_combo.get() if self.margin_type_combo is not None else
                                        self.current_settings.get('default_margin_type', 'ISOLATED'))
            }

            # 테마 설정 제거됨 - 고정 스킨 사용
            selected_theme = 'fixed_skin'
            new_settings['selected_theme'] = selected_theme
            new_settings['current_theme'] = selected_theme

            #  일반 설정 저장: 페이퍼 트레이딩, 데모 모드
            try:
                if hasattr(self, 'paper_trading_var') and self.paper_trading_var is not None and hasattr(self.paper_trading_var, 'get'):
                    new_settings['paper_trading'] = bool(self.paper_trading_var.get())
                else:
                    new_settings['paper_trading'] = bool(self.current_settings.get('paper_trading', False))
                if hasattr(self, 'verbose_logging_var') and self.verbose_logging_var is not None and hasattr(self.verbose_logging_var, 'get'):
                    new_settings['verbose_trade_logging'] = bool(self.verbose_logging_var.get())
                else:
                    new_settings['verbose_trade_logging'] = bool(self.current_settings.get('verbose_trade_logging', False))
                # demo_mode는 UI에서 변경하지 않고 settings.json에서 직접 설정
                new_settings['demo_mode'] = bool(self.current_settings.get('demo_mode', False))

                if hasattr(self, 'broadcast_replay_enabled_var') and self.broadcast_replay_enabled_var is not None and hasattr(self.broadcast_replay_enabled_var, 'get'):
                    new_settings['broadcast_replay_enabled'] = bool(self.broadcast_replay_enabled_var.get())
                else:
                    new_settings['broadcast_replay_enabled'] = bool(self.current_settings.get('broadcast_replay_enabled', False))

                # 방송 리플레이 토글과 화면 오버레이 토글을 항상 동일하게 유지
                new_settings['broadcast_display_override_enabled'] = bool(new_settings['broadcast_replay_enabled'])

                if hasattr(self, 'broadcast_replay_source_entry') and self.broadcast_replay_source_entry is not None and hasattr(self.broadcast_replay_source_entry, 'get'):
                    new_settings['broadcast_replay_source_account'] = str(self.broadcast_replay_source_entry.get() or '').strip()
                else:
                    new_settings['broadcast_replay_source_account'] = str(self.current_settings.get('broadcast_replay_source_account', '') or '').strip()
            except Exception:
                new_settings['paper_trading'] = bool(self.current_settings.get('paper_trading', False))
                new_settings['verbose_trade_logging'] = bool(self.current_settings.get('verbose_trade_logging', False))
                new_settings['broadcast_replay_enabled'] = bool(self.current_settings.get('broadcast_replay_enabled', False))
                new_settings['broadcast_display_override_enabled'] = bool(new_settings['broadcast_replay_enabled'])
                new_settings['broadcast_replay_source_account'] = str(self.current_settings.get('broadcast_replay_source_account', '') or '').strip()

            # UI 설정 저장: 항상 최상단 표시
            try:
                if hasattr(self, 'always_on_top_var') and self.always_on_top_var is not None and hasattr(self.always_on_top_var, 'get'):
                    # UI 설정이 없으면 새로 생성
                    if 'ui_settings' not in new_settings:
                        new_settings['ui_settings'] = {}
                    always_on_top_value = bool(self.always_on_top_var.get())
                    new_settings['ui_settings']['always_on_top'] = always_on_top_value
                    new_settings['ui_settings']['auto_show_stock_broker_diagnosis_after_save'] = bool(
                        self.auto_stock_broker_diagnosis_var.get()
                    ) if hasattr(self, 'auto_stock_broker_diagnosis_var') else bool(
                        self.current_settings.get('ui_settings', {}).get('auto_show_stock_broker_diagnosis_after_save', True)
                    )
                    new_settings['ui_settings'].update(self._collect_auto_update_ui_settings())
                    print(f"UI 설정 저장: always_on_top = {always_on_top_value}")
                else:
                    # 기본값 유지
                    if 'ui_settings' not in new_settings:
                        new_settings['ui_settings'] = {}
                    new_settings['ui_settings']['always_on_top'] = self.current_settings.get('ui_settings', {}).get('always_on_top', False)
                    new_settings['ui_settings']['auto_show_stock_broker_diagnosis_after_save'] = self.current_settings.get('ui_settings', {}).get('auto_show_stock_broker_diagnosis_after_save', True)
                    new_settings['ui_settings'].update(self._collect_auto_update_ui_settings())
                    print(f"UI 설정 기본값 유지: always_on_top = {self.current_settings.get('ui_settings', {}).get('always_on_top', False)}")
            except Exception as e:
                if 'ui_settings' not in new_settings:
                    new_settings['ui_settings'] = {}
                new_settings['ui_settings']['always_on_top'] = self.current_settings.get('ui_settings', {}).get('always_on_top', False)
                new_settings['ui_settings']['auto_show_stock_broker_diagnosis_after_save'] = self.current_settings.get('ui_settings', {}).get('auto_show_stock_broker_diagnosis_after_save', True)
                new_settings['ui_settings'].update(self._collect_auto_update_ui_settings())
                print(f"UI 설정 저장 오류: {e}")

            # 시장 국면 자동 보정 설정 반영
            try:
                if hasattr(self, 'dynamic_thresholds_var') and self.dynamic_thresholds_var is not None and hasattr(self.dynamic_thresholds_var, 'get'):
                    new_settings['dynamic_thresholds_enabled'] = bool(self.dynamic_thresholds_var.get())
                else:
                    new_settings['dynamic_thresholds_enabled'] = self.current_settings.get('dynamic_thresholds_enabled', True)
                if hasattr(self, 'dynamic_high_mult_entry') and self.dynamic_high_mult_entry is not None and hasattr(self.dynamic_high_mult_entry, 'get'):
                    txt = self.dynamic_high_mult_entry.get().strip()
                    if txt:
                        new_settings['dynamic_thresholds_high_multiplier'] = float(txt)
                if hasattr(self, 'dynamic_mode_combo') and self.dynamic_mode_combo is not None and hasattr(self.dynamic_mode_combo, 'get'):
                    new_settings['dynamic_thresholds_mode'] = self.dynamic_mode_combo.get().lower()
                if hasattr(self, 'manual_regime_combo') and self.manual_regime_combo is not None and hasattr(self.manual_regime_combo, 'get'):
                    new_settings['dynamic_thresholds_manual_regime'] = self.manual_regime_combo.get().upper()
            except Exception as e:
                print(f"시장 국면 보정 설정 반영 실패: {e}")

            # Alpha Arena 설정 저장 (새로운 alpha_arena 구조)
            try:
                # 기존 alpha_arena 설정 가져오기 (없으면 기본값)
                alpha_arena = self.current_settings.get('alpha_arena', {}).copy()
                
                # 활성화
                if hasattr(self, 'alpha_arena_enabled_var'):
                    alpha_arena['enabled'] = bool(self.alpha_arena_enabled_var.get())
                
                # 엔진
                if hasattr(self, 'alpha_arena_engine_var'):
                    alpha_arena['engine'] = self.alpha_arena_engine_var.get()
                
                # 초기 자금 기준 저장
                if hasattr(self, 'alpha_arena_capital_benchmark_var'):
                    capital_benchmark_str = self.alpha_arena_capital_benchmark_var.get()
                    try:
                        capital_benchmark = int(capital_benchmark_str)
                        alpha_arena['initial_capital_benchmark'] = capital_benchmark
                    except (ValueError, TypeError):
                        # 기본값 사용
                        alpha_arena['initial_capital_benchmark'] = 10000
                
                # API 키 저장
                if hasattr(self, 'alpha_arena_deepseek_api_key_var'):
                    deepseek_key = self.alpha_arena_deepseek_api_key_var.get().strip()
                    alpha_arena['deepseek_api_key'] = deepseek_key
                
                if hasattr(self, 'alpha_arena_qwen_api_key_var'):
                    qwen_key = self.alpha_arena_qwen_api_key_var.get().strip()
                    alpha_arena['qwen_api_key'] = qwen_key
                
                # 거래 설정은 내부 가드레일로만 사용 (기본값 유지)
                # 사용자가 조절하지 않으므로 기존 값 유지 또는 기본값 사용
                if 'tick_interval_sec' not in alpha_arena:
                    alpha_arena['tick_interval_sec'] = 60
                if 'leverage_min' not in alpha_arena:
                    alpha_arena['leverage_min'] = 10
                if 'leverage_max' not in alpha_arena:
                    alpha_arena['leverage_max'] = 20
                if 'max_risk_per_tick' not in alpha_arena:
                    alpha_arena['max_risk_per_tick'] = 1500.0
                if 'cooldown_sec_per_symbol' not in alpha_arena:
                    alpha_arena['cooldown_sec_per_symbol'] = 30
                if 'max_concurrent_positions' not in alpha_arena:
                    alpha_arena['max_concurrent_positions'] = 6
                
                # 기본값 보장
                if 'symbols' not in alpha_arena:
                    alpha_arena['symbols'] = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'BNBUSDT']
                if 'exchange' not in alpha_arena:
                    alpha_arena['exchange'] = 'binance-futures'
                if 'require_trading_decisions' not in alpha_arena:
                    alpha_arena['require_trading_decisions'] = False
                if 'echo_last_orders_to_llm' not in alpha_arena:
                    alpha_arena['echo_last_orders_to_llm'] = True
                if 'auto_insurance_tp_sl' not in alpha_arena:
                    alpha_arena['auto_insurance_tp_sl'] = False
                if 'workingType' not in alpha_arena:
                    alpha_arena['workingType'] = 'MARK_PRICE'
                if 'logging' not in alpha_arena:
                    alpha_arena['logging'] = {
                        'level': 'INFO',
                        'store_prompt_hash': True,
                        'prompt_version': 'alphaarena-v1'
                    }
                
                new_settings['alpha_arena'] = alpha_arena
            except Exception as e:
                print(f"Alpha Arena 설정 저장 실패: {e}")
                import traceback
                traceback.print_exc()

            # 고급 매매 계층 ON/OFF 저장
            try:
                if hasattr(self, '_atl_vars') and self._atl_vars:
                    existing_atl = copy.deepcopy(
                        getattr(
                            self,
                            '_atl_pending_policy',
                            self.current_settings.get("advanced_trading_layers", {}),
                        )
                    )
                    for key, var in self._atl_vars.items():
                        if key not in existing_atl:
                            existing_atl[key] = {}
                        existing_atl[key]["enabled"] = bool(var.get())
                    strategy_policy = existing_atl.setdefault("strategy_engine", {})
                    if hasattr(self, '_atl_high_vol_action_var'):
                        strategy_policy["high_vol_action"] = (
                            "block"
                            if self._atl_high_vol_action_var.get() == "항상 차단"
                            else "evaluate"
                        )
                    if hasattr(self, '_atl_consensus_threshold_var'):
                        raw_threshold = float(self._atl_consensus_threshold_var.get())
                        strategy_policy["consensus_threshold"] = max(0.10, min(0.95, raw_threshold))
                    if hasattr(self, '_atl_cooldown_sec_var'):
                        raw_cooldown = int(float(self._atl_cooldown_sec_var.get()))
                        strategy_policy["cooldown_sec"] = max(0, min(3600, raw_cooldown))
                    new_settings["advanced_trading_layers"] = existing_atl
                else:
                    new_settings["advanced_trading_layers"] = self.current_settings.get("advanced_trading_layers", {})
            except Exception as e:
                print(f"고급 매매 계층 설정 저장 실패: {e}")
                messagebox.showerror(
                    "전략 엔진 설정 확인",
                    "합의 임계값은 0.10~0.95, 심볼 쿨다운은 0~3600초의 숫자로 입력해 주세요.",
                )
                return

            ai_validation_errors, ai_validation_warnings = self._validate_ai_routes_for_save(
                new_settings
            )
            new_settings["ai_validation"] = {
                "checked_at": datetime.now().isoformat(timespec="seconds"),
                "ok": not ai_validation_errors,
                "errors": ai_validation_errors,
                "warnings": ai_validation_warnings,
            }
            if ai_validation_errors:
                messagebox.showerror(
                    "AI 엔진 설정 저장 차단",
                    "사용할 수 없는 모델 또는 기능이 포함되어 있습니다.\n\n"
                    + "\n".join(f"• {item}" for item in ai_validation_errors[:12]),
                )
                return
            if ai_validation_warnings and hasattr(self, "ai_catalog_status_label"):
                self.ai_catalog_status_label.configure(
                    text=(
                        f"설정 검증 완료 · 경고 {len(ai_validation_warnings)}건"
                        " (API 키 미설정 항목은 빌드 후 테스터 검증 대기)"
                    ),
                    text_color="#f59e0b",
                )

            # 기존 설정과 병합 (기존 방식과 동일)
            # stock_auto_trading.auto_start 업데이트
            if hasattr(self, 'stock_auto_start_var'):
                existing_sat = dict(self.current_settings.get('stock_auto_trading', {}))
                existing_sat['auto_start'] = bool(self.stock_auto_start_var.get())
                existing_sat['enabled'] = existing_sat['auto_start']
                new_settings['stock_auto_trading'] = existing_sat
            self.current_settings.update(new_settings)

            # ── api_type/api_version 조합 방어 검증 ──────────────────────────────
            try:
                from trading.exchanges.exchange_factory import ExchangeFactory
                broker_cfg = new_settings.get('stock_broker_configs', {})
                invalid_msgs = []
                for broker_name, cfg in broker_cfg.items():
                    if not cfg.get('enabled', False):
                        continue
                    ok, err = ExchangeFactory.validate_stock_broker_api_combo(
                        broker=broker_name,
                        api_type=cfg.get('api_type', ''),
                        api_version=cfg.get('api_version', ''),
                    )
                    if not ok:
                        invalid_msgs.append(err)
                if invalid_msgs:
                    messagebox.showerror(
                        "설정 오류",
                        "증권사 API 설정이 잘못되었습니다:\n\n" + "\n".join(invalid_msgs)
                    )
                    return
            except Exception as _ve:
                print(f"api_type/api_version 검증 오류: {_ve}")

            # 설정 파일에 저장 (기존 함수 사용)
            from config.settings import save_settings
            if save_settings(self.current_settings):
                # 1. 먼저 사용자에게 피드백
                messagebox.showinfo("성공", "설정이 저장되었습니다!")

                # 2. 저장 직후 필요한 경우 증권사 1차 진단 안내
                self._maybe_show_post_save_stock_broker_diagnosis()

                # 3. 대시보드 소유 창은 파괴하지 않고 숨겨 native menu를 재사용한다.
                self.original_settings = copy.deepcopy(self.current_settings)
                self._hide_or_destroy()

                # 4. 콜백은 창이 닫힌 후 백그라운드에서 실행
                if self.on_save_callback:
                    # after_idle을 사용하여 UI 스레드를 블로킹하지 않고 실행
                    if self.parent:
                        self.parent.after(100, lambda: self._execute_callback_safe(self.current_settings))
                    else:
                        try:
                            self.on_save_callback(self.current_settings)
                            print("설정 저장 콜백 호출 완료")
                        except Exception as e:
                            print(f"설정 저장 콜백 오류: {e}")
            else:
                messagebox.showerror(
                    "설정 저장 실패",
                    "설정 파일 저장에 실패했습니다.\n\n"
                    "1) 쓰기 권한\n"
                    "2) 설정 파일 경로\n"
                    "3) 디스크 여유 공간\n"
                    "을 확인한 뒤 다시 시도해주세요."
                )

        except Exception as e:
            messagebox.showerror(
                "설정 저장 오류",
                "설정 저장 중 예외가 발생했습니다.\n\n"
                f"오류: {str(e)}\n\n"
                "입력값 형식(API 키/숫자 항목)을 확인하고 다시 시도해주세요."
            )

    def cancel_settings(self):
        """설정 취소"""
        self.current_settings = copy.deepcopy(self.original_settings)
        self.load_current_settings()
        self._hide_or_destroy()

    def reset_settings(self):
        """설정을 기본값으로 복원 - 기존 PyQt5 설정 창과 동일한 로직"""
        reply = messagebox.askyesno(
            "기본값 초기화",
            "모든 설정을 기본값으로 초기화하시겠습니까?\n이 작업은 되돌릴 수 없습니다."
        )

        if reply:
            try:
                # 설정 파일을 템플릿 기반 기본값으로 재생성하고 다시 로드
                from config.settings import reset_settings as cfg_reset, reset_settings_with_options, load_settings
                try:
                    reset_ok = reset_settings_with_options(preserve_sensitive=True)
                except Exception:
                    reset_ok = cfg_reset()

                if reset_ok:
                    self.current_settings = load_settings()
                    self.load_current_settings()
                    messagebox.showinfo("성공", "설정이 기본값으로 복원되었습니다!")
                    # 런타임 반영 콜백
                    if self.on_save_callback:
                        try:
                            self.on_save_callback(self.current_settings)
                            print("설정 복원 콜백 호출 완료")
                        except Exception as e:
                            print(f"설정 복원 콜백 오류: {e}")
                else:
                    messagebox.showerror("오류", "설정 기본값 복원에 실패했습니다.")

            except Exception as e:
                messagebox.showerror("오류", f"설정 복원 중 오류가 발생했습니다: {str(e)}")

    def _apply_api_visibility(self, scope: str = 'all'):
        """API 키 표시/숨김 토글 적용"""
        try:
            def set_show(entry, visible: bool):
                if not entry:
                    return
                try:
                    entry.configure(show='' if visible else '*')
                except Exception:
                    pass

            visible_all = bool(self.show_api_var.get()) if hasattr(self, 'show_api_var') else False
            visible_openai = bool(self.show_openai_api_var.get()) if hasattr(self, 'show_openai_api_var') else visible_all

            if scope in ('all', 'openai') and hasattr(self, 'openai_api_key_entry'):
                set_show(self.openai_api_key_entry, visible_openai if scope == 'openai' else visible_all)

            if scope in ('all', 'exchanges'):
                v = visible_all
                # 모든 거래소 입력 필드에 적용
                for name in [
                    'binance_api_key_entry','binance_secret_key_entry','upbit_api_key_entry','upbit_secret_key_entry',
                    'bithumb_api_key_entry','bithumb_secret_key_entry','bybit_api_key_entry','bybit_secret_key_entry',
                    'okx_api_key_entry','okx_secret_key_entry','okx_passphrase_entry','bitget_api_key_entry',
                    'bitget_secret_key_entry','bitget_password_entry'
                ]:
                    if hasattr(self, name):
                        set_show(getattr(self, name), v)
        except Exception:
            pass

    def _on_click_verify_binance(self):
        """바이낸스 API 키 검증 버튼 핸들러(비동기)"""
        if not self._ensure_referral_api_allowed("binance", self._binance_verify_status):
            return
        try:
            api_key = self.binance_api_key_entry.get().strip() if hasattr(self, 'binance_api_key_entry') else ''
            secret_key = self.binance_secret_key_entry.get().strip() if hasattr(self, 'binance_secret_key_entry') else ''
            if not api_key or not secret_key:
                self._set_binance_status("키를 입력하세요")
                return
            self._set_binance_status("검증 중…")
            th = threading.Thread(target=self._verify_binance_keys_worker, args=(api_key, secret_key), daemon=True)
            th.start()
        except Exception:
            self._set_binance_status("검증 실패")

    def _set_binance_status(self, text: str, ok: Optional[bool] = None):
        try:
            if hasattr(self, '_binance_verify_status'):
                self._binance_verify_status.set(text)
            if hasattr(self, '_binance_verify_label') and self._binance_verify_label:
                if ok is None:
                    color = self._color("text_secondary", "#94a3b8")
                else:
                    color = self._color("success", "#22c55e") if ok else self._color("danger", "#ef4444")
                try:
                    self._binance_verify_label.configure(text_color=color)
                except Exception:
                    pass
        except Exception:
            pass

    def _verify_binance_keys_worker(self, api_key: str, secret_key: str):
        """실제 검증 로직(백그라운드 스레드)
        - 서버 시간 동기화 기반 타임스탬프 사용
        - recvWindow 기본값 활용
        - 가벼운 계정 조회로 유효성 확인
        - 오류 코드를 사용자 친화 메시지로 변환
        """
        try:
            config = BinanceConfig(api_key=api_key, secret_key=secret_key, testnet=False)
            client = BinanceClient(config)
            ok = False
            err_msg = None
            try:
                ts = client.get_synced_timestamp()
                rw = config.recv_window
                info = client.client.futures_account(timestamp=ts, recvWindow=rw)
                ok = bool(info and isinstance(info, dict))
            except Exception as e:
                msg = str(e)
                if "-1021" in msg:
                    err_msg = "시계 동기화 필요(-1021)"
                elif "403" in msg or "4033" in msg:
                    err_msg = "네트워크/IP 제한(403)"
                elif "-2014" in msg or "-2015" in msg:
                    err_msg = "키/권한 확인 필요(-2014/-2015)"
                elif "2022" in msg:
                    err_msg = "증거금/계정 상태 확인(2022)"
                else:
                    err_msg = "검증 실패"
            if ok:
                if self.membership_user_grade == "referral":
                    self.root.after(
                        0,
                        lambda: self._set_binance_status(
                            "API 검증 완료 · Binance Partner 조회 권한 대기", ok=None
                        ),
                    )
                else:
                    self.root.after(0, lambda: self._set_binance_status("검증 완료", ok=True))
            else:
                text = f"{err_msg}" if err_msg else "검증 실패"
                self.root.after(0, lambda: self._set_binance_status(text, ok=False))
        except Exception:
            try:
                self.root.after(0, lambda: self._set_binance_status("검증 실패", ok=False))
            except Exception:
                pass

    def _on_click_verify_upbit(self):
        """업비트 API 키 검증"""
        api_key = self.upbit_api_key_entry.get().strip()
        secret_key = self.upbit_secret_key_entry.get().strip()

        if not api_key or not secret_key:
            self._upbit_verify_status.set("API 키를 입력해주세요")
            return

        self._upbit_verify_status.set("검증 중...")

        # 백그라운드 스레드에서 검증
        threading.Thread(
            target=self._verify_upbit_keys_worker,
            args=(api_key, secret_key),
            daemon=True
        ).start()

    def _verify_upbit_keys_worker(self, api_key: str, secret_key: str):
        """업비트 API 키 검증 (백그라운드 스레드)"""
        try:
            from trading.exchanges.adapters.upbit_spot_adapter import UpbitSpotAdapter

            adapter = UpbitSpotAdapter(api_key, secret_key)
            success = adapter.connect()

            if success:
                self.root.after(0, lambda: self._upbit_verify_status.set("검증 완료"))
            else:
                self.root.after(0, lambda: self._upbit_verify_status.set("검증 실패"))

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                self.root.after(0, lambda: self._upbit_verify_status.set("API 키/권한 오류"))
            elif "403" in error_msg:
                self.root.after(0, lambda: self._upbit_verify_status.set("접근 제한"))
            else:
                self.root.after(0, lambda: self._upbit_verify_status.set("검증 실패"))

    def _on_click_verify_okx(self):
        """OKX API 키 검증"""
        if not self._ensure_referral_api_allowed("okx", self._okx_verify_status):
            return
        api_key = self.okx_api_key_entry.get().strip()
        secret_key = self.okx_secret_key_entry.get().strip()
        passphrase = self.okx_passphrase_entry.get().strip()

        if not api_key or not secret_key or not passphrase:
            self._okx_verify_status.set("API 키를 모두 입력해주세요")
            return

        self._okx_verify_status.set("검증 중...")

        # 백그라운드 스레드에서 검증
        threading.Thread(
            target=self._verify_okx_keys_worker,
            args=(api_key, secret_key, passphrase),
            daemon=True
        ).start()

    def _verify_okx_keys_worker(self, api_key: str, secret_key: str, passphrase: str):
        """OKX API 키 검증 (백그라운드 스레드)"""
        try:
            from trading.exchanges.adapters.okx_futures_adapter import OkxFuturesAdapter

            adapter = OkxFuturesAdapter(api_key, secret_key, passphrase=passphrase)
            success = adapter.connect()

            if success:
                self._auto_verify_referral_after_api_check(
                    "okx", api_key, secret_key, self._okx_verify_status, passphrase
                )
            else:
                raw_error = str(getattr(adapter, 'last_error', '') or '')
                guidance = str(getattr(adapter, 'last_auth_guidance', '') or '')
                hint = guidance or self._build_okx_verify_hint(raw_error)

                def _apply_okx_fail_hint():
                    self._okx_verify_status.set(hint.split('\n')[0])
                    try:
                        messagebox.showwarning("OKX 검증 가이드", hint)
                    except Exception:
                        pass

                self.root.after(0, _apply_okx_fail_hint)

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                self.root.after(0, lambda: self._okx_verify_status.set("API 키/권한 오류"))
            elif "403" in error_msg:
                self.root.after(0, lambda: self._okx_verify_status.set("접근 제한"))
            elif "passphrase" in error_msg.lower():
                self.root.after(0, lambda: self._okx_verify_status.set("Passphrase 오류"))
            else:
                hint = self._build_okx_verify_hint(error_msg)

                def _apply_okx_exception_hint():
                    self._okx_verify_status.set(hint.split('\n')[0])
                    try:
                        messagebox.showwarning("OKX 검증 가이드", hint)
                    except Exception:
                        pass

                self.root.after(0, _apply_okx_exception_hint)

    def _on_click_verify_bithumb(self):
        """빗썸 API 키 검증"""
        api_key = self.bithumb_api_key_entry.get().strip()
        secret_key = self.bithumb_secret_key_entry.get().strip()

        if not api_key or not secret_key:
            self._bithumb_verify_status.set("API 키를 입력해주세요")
            return

        self._bithumb_verify_status.set("검증 중...")

        # 백그라운드 스레드에서 검증
        threading.Thread(
            target=self._verify_bithumb_keys_worker,
            args=(api_key, secret_key),
            daemon=True
        ).start()

    def _verify_bithumb_keys_worker(self, api_key: str, secret_key: str):
        """빗썸 API 키 검증 (백그라운드 스레드)"""
        try:
            from trading.exchanges.adapters.bithumb_spot_adapter import BithumbSpotAdapter

            adapter = BithumbSpotAdapter(api_key, secret_key)
            success = adapter.connect()

            if success:
                self.root.after(0, lambda: self._bithumb_verify_status.set("검증 완료"))
            else:
                self.root.after(0, lambda: self._bithumb_verify_status.set("검증 실패"))

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                self.root.after(0, lambda: self._bithumb_verify_status.set("API 키/권한 오류"))
            elif "403" in error_msg:
                self.root.after(0, lambda: self._bithumb_verify_status.set("접근 제한"))
            else:
                self.root.after(0, lambda: self._bithumb_verify_status.set("검증 실패"))

    def _on_click_verify_bybit(self):
        """바이비트 API 키 검증"""
        if not self._ensure_referral_api_allowed("bybit", self._bybit_verify_status):
            return
        api_key = self.bybit_api_key_entry.get().strip()
        secret_key = self.bybit_secret_key_entry.get().strip()

        if not api_key or not secret_key:
            self._bybit_verify_status.set("API 키를 입력해주세요")
            return

        self._bybit_verify_status.set("검증 중...")

        # 백그라운드 스레드에서 검증
        threading.Thread(
            target=self._verify_bybit_keys_worker,
            args=(api_key, secret_key),
            daemon=True
        ).start()

    def _verify_bybit_keys_worker(self, api_key: str, secret_key: str):
        """바이비트 API 키 검증 (백그라운드 스레드)"""
        try:
            from trading.exchanges.adapters.bybit_futures_adapter import BybitFuturesAdapter

            adapter = BybitFuturesAdapter(api_key, secret_key)
            success = adapter.connect()

            if success:
                self._auto_verify_referral_after_api_check(
                    "bybit", api_key, secret_key, self._bybit_verify_status
                )
            else:
                raw_error = str(getattr(adapter, 'last_error', '') or '')
                guidance = str(getattr(adapter, 'last_auth_guidance', '') or '')
                hint = guidance or self._build_bybit_verify_hint(raw_error)

                def _apply_bybit_fail_hint():
                    self._bybit_verify_status.set(hint.split('\n')[0])
                    try:
                        messagebox.showwarning("Bybit 검증 가이드", hint)
                    except Exception:
                        pass

                self.root.after(0, _apply_bybit_fail_hint)

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                self.root.after(0, lambda: self._bybit_verify_status.set("API 키/권한 오류"))
            elif "403" in error_msg:
                self.root.after(0, lambda: self._bybit_verify_status.set("접근 제한"))
            else:
                hint = self._build_bybit_verify_hint(error_msg)

                def _apply_bybit_exception_hint():
                    self._bybit_verify_status.set(hint.split('\n')[0])
                    try:
                        messagebox.showwarning("Bybit 검증 가이드", hint)
                    except Exception:
                        pass

                self.root.after(0, _apply_bybit_exception_hint)

    def _on_click_verify_bitget(self):
        """비트겟 API 키 검증"""
        if not self._ensure_referral_api_allowed("bitget", self._bitget_verify_status):
            return
        api_key = self.bitget_api_key_entry.get().strip()
        secret_key = self.bitget_secret_key_entry.get().strip()
        password = self.bitget_password_entry.get().strip()

        if not api_key or not secret_key or not password:
            self._bitget_verify_status.set("API 키를 모두 입력해주세요")
            return

        self._bitget_verify_status.set("검증 중...")

        # 백그라운드 스레드에서 검증
        threading.Thread(
            target=self._verify_bitget_keys_worker,
            args=(api_key, secret_key, password),
            daemon=True
        ).start()

    @staticmethod
    def _get_public_ip_for_hint(timeout_sec: float = 1.8) -> str:
        try:
            with urllib_request.urlopen('https://api.ipify.org', timeout=timeout_sec) as resp:
                return resp.read().decode('utf-8').strip()
        except Exception:
            return "확인 실패"

    def _refresh_bitget_public_ip(self):
        try:
            if hasattr(self, '_bitget_public_ip_status') and self._bitget_public_ip_status is not None:
                self._bitget_public_ip_status.set("현재 공인 IP: 확인 중...")
        except Exception:
            pass

        threading.Thread(target=self._refresh_bitget_public_ip_worker, daemon=True).start()

    def _refresh_bitget_public_ip_worker(self):
        ip = self._get_public_ip_for_hint()
        text = f"현재 공인 IP: {ip}"
        try:
            self.root.after(0, lambda: self._bitget_public_ip_status.set(text))
        except Exception:
            pass

    def _build_bitget_verify_hint(self, error_msg: str) -> str:
        msg = str(error_msg or '')
        low = msg.lower()
        public_ip = self._get_public_ip_for_hint()

        if 'invalid ip' in low or 'code":"40018' in low or "code': '40018" in low:
            return (
                "Bitget IP 화이트리스트 오류\n"
                f"현재 공인 IP: {public_ip}\n"
                "Bitget API 키 설정에서 IP 화이트리스트에 위 IP를 등록한 뒤 다시 검증하세요."
            )

        if 'invalid header value' in low:
            return (
                "Bitget 헤더 값 오류\n"
                "API Key/Secret/Passphrase 앞뒤 공백·줄바꿈을 제거하고 다시 저장 후 검증하세요."
            )

        if 'password' in low or 'passphrase' in low:
            return "Bitget Passphrase 오류: 키 생성 시 입력한 passphrase 값을 다시 확인하세요."

        if '401' in low or 'unauthorized' in low:
            return "Bitget 인증 오류: API Key/Secret/Passphrase 및 선물 거래 권한을 확인하세요."

        return "Bitget 검증 실패: 입력값과 권한 설정을 확인한 뒤 다시 시도하세요."

    def _build_bybit_verify_hint(self, error_msg: str) -> str:
        msg = str(error_msg or '')
        low = msg.lower()
        public_ip = self._get_public_ip_for_hint()

        if 'unmatched ip' in low or 'bound ip' in low:
            return (
                "Bybit IP 화이트리스트 오류\n"
                f"현재 공인 IP: {public_ip}\n"
                "Bybit API 키의 bound IP 주소에 위 IP를 등록한 뒤 다시 검증하세요."
            )
        if '401' in low or 'unauthorized' in low:
            return "Bybit 인증 오류: API Key/Secret 및 선물 거래 권한을 확인하세요."
        return "Bybit 검증 실패: 입력값과 API 권한 설정을 확인한 뒤 다시 시도하세요."

    def _build_okx_verify_hint(self, error_msg: str) -> str:
        msg = str(error_msg or '')
        low = msg.lower()
        public_ip = self._get_public_ip_for_hint()

        if 'passphrase' in low:
            return "OKX Passphrase 오류: API 생성 시 설정한 passphrase를 다시 확인하세요."
        if '51010' in low or 'account mode' in low:
            return "OKX 계좌 모드 오류: 웹사이트에서 계좌 모드를 Single/Multi-currency margin으로 변경 후 다시 검증하세요."
        if 'invalid ip' in low:
            return (
                "OKX IP 제한 가능성\n"
                f"현재 공인 IP: {public_ip}\n"
                "OKX API 키의 IP 제한 설정을 확인하세요."
            )
        if '401' in low or 'unauthorized' in low:
            return "OKX 인증 오류: API Key/Secret/Passphrase 및 거래 권한을 확인하세요."
        return "OKX 검증 실패: 입력값과 계좌 모드/권한 설정을 확인한 뒤 다시 시도하세요."

    def _verify_bitget_keys_worker(self, api_key: str, secret_key: str, password: str):
        """비트겟 API 키 검증 (백그라운드 스레드)"""
        try:
            from trading.exchanges.adapters.bitget_futures_adapter import BitgetFuturesAdapter

            adapter = BitgetFuturesAdapter(api_key, secret_key, password)
            success = adapter.connect()

            if success:
                self._auto_verify_referral_after_api_check(
                    "bitget", api_key, secret_key, self._bitget_verify_status, password
                )
            else:
                raw_error = str(getattr(adapter, 'last_error', '') or '')
                guidance = str(getattr(adapter, 'last_auth_guidance', '') or '')
                hint = guidance or self._build_bitget_verify_hint(raw_error)

                def _apply_bitget_fail_hint():
                    one_line = hint.split('\n')[0]
                    self._bitget_verify_status.set(one_line)
                    try:
                        messagebox.showwarning("Bitget 검증 가이드", hint)
                    except Exception:
                        pass

                self.root.after(0, _apply_bitget_fail_hint)

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                self.root.after(0, lambda: self._bitget_verify_status.set("API 키/권한 오류"))
            elif "403" in error_msg:
                self.root.after(0, lambda: self._bitget_verify_status.set("접근 제한"))
            elif "password" in error_msg.lower():
                self.root.after(0, lambda: self._bitget_verify_status.set("Password 오류"))
            else:
                hint = self._build_bitget_verify_hint(error_msg)

                def _apply_bitget_exception_hint():
                    self._bitget_verify_status.set(hint.split('\n')[0])
                    try:
                        messagebox.showwarning("Bitget 검증 가이드", hint)
                    except Exception:
                        pass

                self.root.after(0, _apply_bitget_exception_hint)

    def create_advanced_layers_tab(self):
        """고급 매매 계층 설정 탭 - 프리셋 전환 + 개별 ON/OFF"""
        tab = self.tabview.add("고급 매매 계층")
        self._add_tab_save_bar(tab, "5. 고급 정책 (선택)")

        scroll_frame = ctk.CTkScrollableFrame(tab)
        scroll_frame.pack(fill="both", expand=True, padx=14, pady=14)

        # ── 현재 설정에서 advanced_trading_layers 읽기 ──────────────
        atl = self.current_settings.get("advanced_trading_layers", {})
        self._atl_pending_policy = copy.deepcopy(atl)

        # ── 타이틀 ─────────────────────────────────────────────────
        ctk.CTkLabel(
            scroll_frame,
            text="5. 고급 정책 (선택)",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb"),
        ).pack(pady=(10, 4))
        ctk.CTkLabel(
            scroll_frame,
            text=(
                "각 계층을 개별 ON/OFF 하거나, 프리셋 버튼으로 한 번에 전환하세요.\n"
                "표준 자동매매 경로(Binance·Bybit·OKX·Bitget·Upbit·Bithumb·증권)에 적용됩니다. "
                "학습 전용은 주문 계층을 실행하지 않으며 AlphaArena는 별도 실행 체계입니다."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left",
            wraplength=700,
        ).pack(fill="x", padx=14, pady=(0, 12))

        beginner_guide = ctk.CTkFrame(
            scroll_frame, fg_color="#0b2a20", corner_radius=12,
            border_width=1, border_color="#166534",
        )
        beginner_guide.pack(fill="x", pady=(0, 16))
        ctk.CTkLabel(
            beginner_guide,
            text=(
                "처음 사용하는 분: safe(권장)를 선택하고 저장한 뒤 LEARNING/PAPER에서 7~14일 관찰하세요.\n"
                "개별 임계값은 차단 로그와 충분한 종료 거래 표본이 있을 때만 바꾸고, aggressive는 숙련자 검증용입니다."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#bbf7d0", justify="left", wraplength=680,
        ).pack(fill="x", padx=16, pady=12)

        # ── 프리셋 전환 버튼 그룹 ──────────────────────────────────
        preset_group = ctk.CTkFrame(scroll_frame, corner_radius=12)
        preset_group.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            preset_group,
            text="프리셋 빠른 전환",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb"),
        ).pack(pady=(16, 8))

        ctk.CTkLabel(
            preset_group,
            text=(
                "전체 OFF: 개발·진단용(실거래 권장 아님)  |  safe: 신규 사용자 권장  |  "
                "aggressive: 더 낮은 통과 기준의 숙련자 검증용"
            ),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left", wraplength=680,
        ).pack(fill="x", padx=16, pady=(0, 10))

        btn_row = ctk.CTkFrame(preset_group, fg_color="transparent")
        btn_row.pack(pady=(0, 16))

        def _apply_preset(preset_name: str):
            try:
                from config.settings import load_settings_template
                template = load_settings_template()
                # advanced_trading_layers.presets 또는 advanced_trading_policy_presets 모두 지원
                presets = (
                    template.get("advanced_trading_layers", {}).get("presets") or
                    template.get("advanced_trading_policy_presets") or
                    {}
                )
            except Exception:
                # 템플릿 로드 실패 시 하드코딩 기본값
                presets = {
                    "dev": {k: {"enabled": False} for k in ["profitability_validation", "portfolio_orchestration", "strategy_engine", "execution_optimizer", "ops_automation"]},
                    "safe": {
                        "profitability_validation": {"enabled": True, "min_trades": 20, "min_win_rate": 0.45, "min_sharpe": 0.35, "max_mdd": 0.25, "min_walkforward_pass_rate": 0.45},
                        "portfolio_orchestration": {"enabled": True, "max_single_asset_weight": 0.25},
                        "strategy_engine": {"enabled": True, "consensus_threshold": 0.70, "cooldown_sec": 120},
                        "execution_optimizer": {"enabled": True, "max_retries": 2, "max_slippage_bps": 25},
                        "ops_automation": {"enabled": True, "quality_score_threshold": 55.0},
                    },
                    "aggressive": {
                        "profitability_validation": {"enabled": True, "min_win_rate": 0.35, "min_sharpe": 0.30, "max_mdd": 0.40},
                        "portfolio_orchestration": {"enabled": True},
                        "strategy_engine": {"enabled": True, "consensus_threshold": 0.35},
                        "execution_optimizer": {"enabled": True, "max_slippage_bps": 80},
                        "ops_automation": {"enabled": True, "quality_score_threshold": 25.0},
                    },
                }

            chosen = presets.get(preset_name, {})
            from trading.advanced_layer_config import deep_merge_policy, policy_changes
            before_policy = copy.deepcopy(self._atl_pending_policy)
            self._atl_pending_policy = deep_merge_policy(before_policy, chosen)
            changes = policy_changes(before_policy, self._atl_pending_policy)
            layer_keys = [
                "profitability_validation",
                "portfolio_orchestration",
                "strategy_engine",
                "execution_optimizer",
                "ops_automation",
            ]
            for key in layer_keys:
                if key in chosen and key in self._atl_vars:
                    self._atl_vars[key].set(bool(chosen[key].get("enabled", False)))
            strategy_choice = dict(chosen.get("strategy_engine", {}) or {})
            if strategy_choice:
                if "high_vol_action" in strategy_choice:
                    self._atl_high_vol_action_var.set(
                        "항상 차단"
                        if str(strategy_choice.get("high_vol_action")).lower() == "block"
                        else "평가 계속 (권장)"
                    )
                if "consensus_threshold" in strategy_choice:
                    self._atl_consensus_threshold_var.set(str(strategy_choice["consensus_threshold"]))
                if "cooldown_sec" in strategy_choice:
                    self._atl_cooldown_sec_var.set(str(strategy_choice["cooldown_sec"]))

            # 상태 레이블 업데이트
            colors = {"dev": "#94a3b8", "safe": "#22c55e", "aggressive": "#f59e0b"}
            self._preset_status_label.configure(
                text=f"프리셋 '{preset_name}' 적용됨 · 저장 대기 · 세부값 {len(changes)}개 변경",
                text_color=colors.get(preset_name, "#f9fafb"),
            )
            preview_items = [
                f"{item['path']}: {item['before']} → {item['after']}"
                for item in changes[:5]
            ]
            self._preset_preview_label.configure(
                text=(
                    "변경 미리보기: " + "  |  ".join(preview_items)
                    if preview_items
                    else "변경 미리보기: 현재 설정과 동일"
                )
            )

        ctk.CTkButton(
            btn_row, text="전체 OFF (개발·진단)", width=170, height=36,
            fg_color="#1e3a5f", hover_color="#1d4ed8",
            command=lambda: _apply_preset("dev"),
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            btn_row, text="safe (신규 권장)", width=160, height=36,
            fg_color="#14532d", hover_color="#15803d",
            command=lambda: _apply_preset("safe"),
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            btn_row, text="aggressive (숙련자)", width=180, height=36,
            fg_color="#78350f", hover_color="#d97706",
            command=lambda: _apply_preset("aggressive"),
        ).pack(side="left", padx=6)

        self._preset_status_label = ctk.CTkLabel(
            preset_group, text="", font=ctk.CTkFont(size=12),
            text_color=self._color("text_secondary", "#94a3b8"),
        )
        self._preset_status_label.pack(pady=(0, 8))
        self._preset_preview_label = ctk.CTkLabel(
            preset_group,
            text="프리셋을 누르면 저장 전 변경값을 여기에 표시합니다.",
            font=ctk.CTkFont(size=11),
            text_color=self._color("text_secondary", "#94a3b8"),
            wraplength=680,
            justify="left",
        )
        self._preset_preview_label.pack(padx=16, pady=(0, 14))

        # ── 개별 계층 ON/OFF 스위치 ────────────────────────────────
        layers_group = ctk.CTkFrame(scroll_frame, corner_radius=12)
        layers_group.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            layers_group,
            text="계층별 개별 설정",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb"),
        ).pack(pady=(16, 10))

        layer_defs = [
            ("profitability_validation",  "1⃣ 수익성 검증 (Profitability Gate)",
             "최근 거래 KPI(거래수·승률·샤프·워크포워드)를 검사합니다. 일반 미달은 1포지션·1배 회복 학습으로 표본을 더 모으고, Hard MDD는 신규 진입을 차단합니다."),
            ("portfolio_orchestration",   "2⃣ 포트폴리오 오케스트레이션",
             "코인·주식·ETF의 자본 비중, 단일 자산 집중도와 상관관계를 제한해 한 전략·한 종목 쏠림을 줄입니다."),
            ("strategy_engine",           "3⃣ 전략 엔진 (레짐 필터/합의)",
             "AI 진입 후보를 시장 국면·다중 신호 합의·재진입 쿨다운으로 한 번 더 거릅니다. 새로운 전략을 만드는 계층은 아닙니다."),
            ("execution_optimizer",       "4⃣ 실행 최적화 (슬리피지 제어)",
             "주문 재시도·시간 제한·허용 슬리피지를 관리하고 정책 안에서 시장가 대체 여부를 판단합니다."),
            ("ops_automation",            "5⃣ 운영 자동화 (이상 감지/롤백)",
             "거절률·슬리피지·품질 점수를 감시하고 이상 상태를 기록·롤백하며 운영 브리핑 근거를 만듭니다."),
        ]

        self._atl_vars: dict = {}
        for key, label_text, desc_text in layer_defs:
            row_frame = ctk.CTkFrame(layers_group, fg_color=self._color("surface", "#111827"), corner_radius=8)
            row_frame.pack(fill="x", padx=16, pady=4)

            saved_val = bool(atl.get(key, {}).get("enabled", False))
            var = ctk.BooleanVar(value=saved_val)
            self._atl_vars[key] = var

            ctk.CTkSwitch(
                row_frame, text=label_text, variable=var,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=self._color("text_primary", "#f9fafb"),
            ).pack(anchor="w", padx=16, pady=(10, 2))

            ctk.CTkLabel(
                row_frame, text=f"   {desc_text}",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=self._color("text_secondary", "#6b7280"),
                justify="left",
                wraplength=660,
            ).pack(anchor="w", padx=16, pady=(0, 10))

        strategy_detail_group = ctk.CTkFrame(scroll_frame, corner_radius=12)
        strategy_detail_group.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(
            strategy_detail_group,
            text="전략 엔진 세부 설정",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb"),
        ).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(
            strategy_detail_group,
            text=(
                "이 엔진은 새로운 매매전략을 만드는 기능이 아니라, AI가 만든 진입 후보를 한 번 더 거르는 후행 필터입니다.\n"
                "합의 임계값은 0.10~0.95이며 높을수록 진입이 보수적입니다(예: 0.60이면 합의점수 0.60 이상만 통과). "
                "심볼 쿨다운은 같은 종목의 재진입 최소 대기시간(0~3600초)입니다.\n"
                "이 합의·수익성 재평가는 기본 AI와 '기본 AI 후보 확인(권장)' 역할에 적용됩니다. "
                "'사용자 전략 독립 신호(숙련자)'는 전략값을 재심사하지 않고 시장국면·계좌·주문 안전만 통과합니다. "
                "고변동장 '평가 계속'도 무조건 진입을 뜻하지 않습니다."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left",
            wraplength=680,
        ).pack(anchor="w", padx=18, pady=(0, 12))

        strategy_policy = dict(atl.get("strategy_engine", {}) or {})
        policy_list = ctk.CTkFrame(strategy_detail_group, fg_color="transparent")
        policy_list.pack(fill="x", padx=18, pady=(0, 16))

        high_vol_row = ctk.CTkFrame(policy_list, fg_color="#111827", corner_radius=8)
        high_vol_row.pack(fill="x", pady=4)
        ctk.CTkLabel(high_vol_row, text="고변동장 처리", font=ctk.CTkFont(size=12, weight="bold")).pack(
            anchor="w", padx=12, pady=(9, 4)
        )
        self._atl_high_vol_action_var = ctk.StringVar(
            value=(
                "항상 차단"
                if str(strategy_policy.get("high_vol_action", "evaluate")).lower() == "block"
                else "평가 계속 (권장)"
            )
        )
        ctk.CTkComboBox(
            high_vol_row,
            values=["평가 계속 (권장)", "항상 차단"],
            variable=self._atl_high_vol_action_var,
            width=180,
            state="readonly",
        ).pack(anchor="w", padx=12)
        ctk.CTkLabel(
            high_vol_row,
            text=(
                "기본값 ‘평가 계속’: 변동성이 높아도 자동 진입하지 않고 합의·수익성·국면·계좌·주문 검사를 계속합니다. "
                "‘항상 차단’: 고변동장 신규 진입 후보를 모두 막습니다. 급등락 공포가 크거나 PAPER 초기에는 차단을 선택할 수 있습니다."
            ),
            font=ctk.CTkFont(size=10), text_color="#94a3b8", justify="left", wraplength=640,
        ).pack(fill="x", padx=12, pady=(5, 10))

        consensus_row = ctk.CTkFrame(policy_list, fg_color="#111827", corner_radius=8)
        consensus_row.pack(fill="x", pady=4)
        ctk.CTkLabel(consensus_row, text="합의 임계값", font=ctk.CTkFont(size=12, weight="bold")).pack(
            anchor="w", padx=12, pady=(9, 4)
        )
        self._atl_consensus_threshold_var = ctk.StringVar(
            value=str(strategy_policy.get("consensus_threshold", 0.60))
        )
        ctk.CTkEntry(
            consensus_row, textvariable=self._atl_consensus_threshold_var, width=120
        ).pack(anchor="w", padx=12)
        ctk.CTkLabel(
            consensus_row,
            text="허용 범위 0.10~0.95 · 현재 템플릿 기본값 0.60 · safe 권장값 0.70. 값이 높을수록 더 많은 신호 합의가 필요해 진입이 보수적입니다.",
            font=ctk.CTkFont(size=10), text_color="#94a3b8", justify="left", wraplength=640,
        ).pack(fill="x", padx=12, pady=(5, 10))

        cooldown_row = ctk.CTkFrame(policy_list, fg_color="#111827", corner_radius=8)
        cooldown_row.pack(fill="x", pady=4)
        ctk.CTkLabel(cooldown_row, text="심볼 쿨다운(초)", font=ctk.CTkFont(size=12, weight="bold")).pack(
            anchor="w", padx=12, pady=(9, 4)
        )
        self._atl_cooldown_sec_var = ctk.StringVar(
            value=str(strategy_policy.get("cooldown_sec", 60))
        )
        ctk.CTkEntry(
            cooldown_row, textvariable=self._atl_cooldown_sec_var, width=120
        ).pack(anchor="w", padx=12)
        ctk.CTkLabel(
            cooldown_row,
            text="같은 심볼 재진입 최소 대기시간입니다. 허용 범위 0~3600초 · 기본 60초 · safe 120초. 잦은 재진입과 수수료 누적을 줄입니다.",
            font=ctk.CTkFont(size=10), text_color="#94a3b8", justify="left", wraplength=640,
        ).pack(fill="x", padx=12, pady=(5, 10))

        # ── 도움말 ─────────────────────────────────────────────────
        help_group = ctk.CTkFrame(scroll_frame, corner_radius=12)
        help_group.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(
            help_group,
            text="수익성 검증 안내\n1) 일반 성과 미달은 1포지션·1배의 회복 학습으로 계속 표본을 수집합니다.\n2) 수수료 차감 순손익과 다음 재평가 거래 수를 확인하세요.\n3) Hard MDD 차단은 임의로 우회하지 말고 손실·체결 원인을 먼저 점검하세요.\n자세한 설명은 대시보드 > 사용자 메뉴얼 > '수익성 검증·회복 학습 대응' 절을 참조하세요.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("info", "#3b82f6"),
            justify="left", wraplength=660,
        ).pack(fill="x", padx=20, pady=16)

    def create_alphaarena_tab(self):
        """AlphaArena 모드 설정 탭 (새로운 alpha_arena 구조 적용)"""
        tab = self.tabview.add("AlphaArena")
        self._add_tab_save_bar(tab, "6. AlphaArena 실험실")

        # 스크롤 가능한 프레임
        scroll_frame = ctk.CTkScrollableFrame(tab)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 소개 섹션
        intro_group = ctk.CTkFrame(scroll_frame)
        intro_group.pack(fill="x", pady=(0, 20))

        intro_title = ctk.CTkLabel(
            intro_group,
            text="6. AlphaArena 실험실",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        intro_title.pack(pady=(20, 10), padx=20)

        intro_desc = ctk.CTkLabel(
            intro_group,
            text=(
                "숙련자용 독립 실험 모드 · 기본 OFF\n\n"
                "AlphaArena는 지정 거래소 전체를 쓰는 표준 자동매매가 아니라 Binance USDT 선물 전용 독립 실행 체계입니다. "
                "LLM 판단을 구조화해 주문 후보로 만들고 TP/SL 필수·레버리지·틱 위험·쿨다운·최대 포지션 게이트를 통과한 경우에만 주문합니다.\n\n"
                "표준 자동매매의 수익성·포트폴리오·전략 합의 계층 및 기존 TP/SL 보험·워치독과는 공유되지 않습니다. "
                "처음 사용자는 켜지 말고 표준 LEARNING/PAPER와 AI 커스텀부터 검증하세요."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left", wraplength=680,
        )
        intro_desc.pack(fill="x", pady=(0, 20), padx=20)

        # 활성화 스위치
        enable_group = ctk.CTkFrame(scroll_frame)
        enable_group.pack(fill="x", pady=(0, 20))

        enable_title = ctk.CTkLabel(
            enable_group,
            text="Alpha Arena 모드 활성화",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        enable_title.pack(anchor="w", padx=20, pady=(20, 10))

        self.alpha_arena_enabled_var = ctk.BooleanVar(value=False)
        enable_switch = ctk.CTkSwitch(
            enable_group,
            text="Alpha Arena 모드 활성화",
            variable=self.alpha_arena_enabled_var,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            onvalue=True,
            offvalue=False
        )
        enable_switch.pack(anchor="w", padx=20, pady=(0, 20))

        defaults_group = ctk.CTkFrame(scroll_frame, fg_color="#0b1120", corner_radius=12)
        defaults_group.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(
            defaults_group, text="현재 고정 가드레일과 기본값",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"), text_color="#38bdf8",
        ).pack(anchor="w", padx=20, pady=(16, 6))
        ctk.CTkLabel(
            defaults_group,
            text=(
                "거래소: Binance USDT 선물 · 판단 주기: 60초(최소 30초) · 기본 심볼: BTC/ETH/SOL/XRP/DOGE/BNB\n"
                "레버리지: 10~20배로 제한 · 진입마다 TP와 SL 필수 · 심볼별 쿨다운 30초 · 최대 동시 포지션 6개\n"
                "틱당 모델 제시 위험 합계 상한: $1,500. 이 값은 수익 보장이나 계좌 전체 손실 상한을 뜻하지 않습니다."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#cbd5e1",
            justify="left", wraplength=660,
        ).pack(fill="x", padx=20, pady=(0, 16))

        # AI 엔진 선택 섹션
        ai_group = ctk.CTkFrame(scroll_frame)
        ai_group.pack(fill="x", pady=(0, 20))

        ai_title = ctk.CTkLabel(
            ai_group,
            text="AI 엔진 선택",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        ai_title.pack(anchor="w", padx=20, pady=(20, 10))

        # AI 엔진 선택 (설계 문서에 맞게)
        engine_label = ctk.CTkLabel(
            ai_group,
            text="엔진:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        engine_label.pack(anchor="w", padx=20, pady=(5, 5))

        self.alpha_arena_engine_var = ctk.StringVar(value="deepseek-v4-flash")
        engine_combo = ctk.CTkComboBox(
            ai_group,
            values=["deepseek-v4-flash"],
            variable=self.alpha_arena_engine_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            width=200
        )
        engine_combo.pack(anchor="w", padx=20, pady=(0, 20))

        # API 키 입력 섹션
        api_key_group = ctk.CTkFrame(scroll_frame)
        api_key_group.pack(fill="x", pady=(0, 20))

        api_key_title = ctk.CTkLabel(
            api_key_group,
            text="API 키 설정",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        api_key_title.pack(anchor="w", padx=20, pady=(20, 10))

        # DeepSeek API Key
        deepseek_label = ctk.CTkLabel(
            api_key_group,
            text="DeepSeek API Key:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        deepseek_label.pack(anchor="w", padx=20, pady=(5, 5))

        self.alpha_arena_deepseek_api_key_var = ctk.StringVar(value="")
        deepseek_entry = ctk.CTkEntry(
            api_key_group,
            textvariable=self.alpha_arena_deepseek_api_key_var,
            placeholder_text="sk-...",
            height=35,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=self._color("background", "#050a13"),
            border_color=self._color("secondary", "#1f2937"),
            show="*"
        )
        deepseek_entry.pack(fill="x", padx=20, pady=(0, 15))

        # 레거시 설정 파일의 Qwen 키는 읽고 보존하되 현재 실행 UI에는 노출하지 않는다.
        self.alpha_arena_qwen_api_key_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            api_key_group,
            text="현재 실행 선택은 DeepSeek V4 Flash만 지원합니다. 기존 Qwen 키는 호환 보관되지만 새 실행에 사용되지 않습니다.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left", wraplength=660,
        ).pack(fill="x", padx=20, pady=(0, 20))

        # 초기 자금 기준 선택 섹션
        capital_group = ctk.CTkFrame(scroll_frame)
        capital_group.pack(fill="x", pady=(0, 20))

        capital_title = ctk.CTkLabel(
            capital_group,
            text="초기 자금 기준 선택",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        capital_title.pack(anchor="w", padx=20, pady=(20, 10))

        capital_desc = ctk.CTkLabel(
            capital_group,
            text="Alpha Arena 벤치마크에서 사용한 초기 자금 기준을 선택하세요.\n선택한 기준에 따라 LLM의 거래 판단이 달라집니다.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        )
        capital_desc.pack(anchor="w", padx=20, pady=(0, 10))

        capital_label = ctk.CTkLabel(
            capital_group,
            text="초기 자금 기준:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        capital_label.pack(anchor="w", padx=20, pady=(5, 5))

        self.alpha_arena_capital_benchmark_var = ctk.StringVar(value="10000")
        # 드롭다운 값은 숫자로 저장하되, 표시는 사용자 친화적으로
        capital_combo = ctk.CTkComboBox(
            capital_group,
            values=["10000", "1000", "100"],
            variable=self.alpha_arena_capital_benchmark_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            width=200,
            command=self._on_capital_benchmark_change
        )
        capital_combo.pack(anchor="w", padx=20, pady=(0, 10))
        
        # 드롭다운 값 변경 시 표시 텍스트 업데이트 (사용자 친화적)
        def format_capital_display(value):
            """드롭다운 표시 텍스트 포맷팅"""
            try:
                capital = int(value)
                if capital == 10000:
                    return "만불 ($10,000)"
                elif capital == 1000:
                    return "천불 ($1,000)"
                elif capital == 100:
                    return "백불 ($100)"
                else:
                    return f"${capital:,}"
            except (ValueError, TypeError):
                return value
        
        # 초기 표시 텍스트 설정
        try:
            initial_value = self.alpha_arena_capital_benchmark_var.get()
            # CTkComboBox는 values 배열의 인덱스를 사용하므로, 값으로 인덱스 찾기
            values = ["10000", "1000", "100"]
            if initial_value in values:
                idx = values.index(initial_value)
                # 표시 텍스트는 직접 변경할 수 없으므로, 설명 레이블로 대체
                capital_display_label = ctk.CTkLabel(
                    capital_group,
                    text=f"선택된 기준: {format_capital_display(initial_value)}",
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color=self._color("text_secondary", "#9ca3af")
                )
                capital_display_label.pack(anchor="w", padx=20, pady=(0, 5))
                self.capital_display_label = capital_display_label
        except Exception:
            pass

        # 선택한 기준에 따른 표시 레이블
        self.capital_warning_label = ctk.CTkLabel(
            capital_group,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=self._color("warning", "#f59e0b"),
            justify="left"
        )
        self.capital_warning_label.pack(anchor="w", padx=20, pady=(0, 20))
        # 초기 경고 메시지 설정
        self._update_capital_warning()

        # 주의사항 (카드 섹션)
        warning_card = ctk.CTkFrame(
            scroll_frame,
            fg_color=self._color("surface", "#1f2937"),
            corner_radius=12,
            border_width=2,
            border_color=self._color("danger", "#ef4444")
        )
        warning_card.pack(fill="x", pady=(0, 20))

        warning_title = ctk.CTkLabel(
            warning_card,
            text="주의사항",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("danger", "#ef4444")
        )
        warning_title.pack(anchor="w", padx=20, pady=(20, 10))

        warning_items = [
            "• 기본 OFF인 숙련자 실험 모드이며 표준 자동매매와 동시에 켜기 전에 별도 검증이 필요합니다",
            "• 기존 TP/SL 보험·워치독 대신 AlphaArena 자체 TP/SL 필수·주문 게이트가 동작합니다",
            "• LLM이 TP/SL을 지정하지 않거나 위험·쿨다운·포지션 한도를 넘으면 주문이 차단됩니다",
            "• 소스 자동 테스트 통과는 Windows 설치본·실계정 장시간 E2E 완료를 뜻하지 않습니다"
        ]

        for item in warning_items:
            item_label = ctk.CTkLabel(
                warning_card,
                text=item,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=self._color("text_primary", "#f9fafb"),
                justify="left", wraplength=650,
            )
            item_label.pack(anchor="w", padx=20, pady=(0, 5))

        help_label = ctk.CTkLabel(
            warning_card,
            text="• 대시보드 → 사용자 메뉴얼 → AlphaArena에서 실행 흐름·주의사항을 먼저 확인하거나 AI 어시스턴트에 ‘AlphaArena가 뭐야?’라고 질문하세요.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("info", "#3b82f6"),
            justify="left", wraplength=650,
        )
        help_label.pack(anchor="w", padx=20, pady=(10, 20))

    def _verify_alphaarena_api_key(self):
        """선택한 AI 엔진의 API 키 검증"""
        selected_ai = self.alphaarena_ai_var.get()

        # 선택한 AI에 따라 해당 API 키 가져오기
        if selected_ai in ("deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat-v3.1"):
            api_key = self.alphaarena_deepseek_key.get()
            provider = "DeepSeek"
        elif selected_ai == "gpt-4o":
            api_key = self.alphaarena_openai_key.get()
            provider = "OpenAI"
        elif selected_ai == "claude-sonnet-4-5":
            api_key = self.alphaarena_anthropic_key.get()
            provider = "Anthropic"
        elif selected_ai == "gemini-2-5-pro":
            api_key = self.alphaarena_google_key.get()
            provider = "Google"
        elif selected_ai == "grok-4":
            api_key = self.alphaarena_xai_key.get()
            provider = "xAI"
        elif selected_ai == "qwen3-max":
            api_key = self.alphaarena_alibaba_key.get()
            provider = "Alibaba"
        else:
            self.alphaarena_verify_status.configure(text="알 수 없는 AI 엔진")
            return

        if not api_key:
            self.alphaarena_verify_status.configure(
                text="API 키를 입력해주세요",
                text_color=self._color("danger", "#ef4444")
            )
            return

        self.alphaarena_verify_status.configure(
            text="검증 중...",
            text_color=self._color("info", "#3b82f6")
        )

        # 백그라운드 검증
        threading.Thread(
            target=self._verify_alphaarena_key_worker,
            args=(selected_ai, api_key, provider),
            daemon=True
        ).start()

    def _verify_alphaarena_key_worker(self, ai_type: str, api_key: str, provider: str):
        """API 키 검증 워커"""
        # 실제 검증 로직은 구현 예정
        # 지금은 디자인만
        self.root.after(0, lambda: self.alphaarena_verify_status.configure(
            text=f"{provider} API 키 형식 검증 완료 (실제 검증은 구현 예정)",
            text_color=self._color("success", "#22c55e")
        ))

    def run(self):
        """UI 실행"""
        # 현재 설정 로드
        self.load_current_settings()
        # mainloop() 대신 wait_window() 사용 (모달 방식)
        self.root.wait_window()

# 편의 함수
def show_settings_window(parent=None, current_settings=None):
    """설정 창 표시"""
    settings_window = ModernSettingsWindow(parent, current_settings)
    settings_window.run()
    return settings_window

if __name__ == "__main__":
    try:
        app = ModernSettingsWindow()
        app.run()
    except Exception as e:
        print(f"설정 창 실행 오류: {e}")
        import traceback
        traceback.print_exc()
